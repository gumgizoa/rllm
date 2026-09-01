#!/usr/bin/env python3
"""Materialize the small train/val benchmarks this recipe trains on.

Both splits are *native* rLLM sandbox benchmarks (task-per-directory:
``task.toml`` + ``environment/Dockerfile`` + ``tests/test.sh``), so the run
goes through ``AgentFlowEngine`` → ``SandboxTaskHooks`` →
``MiniSweAgentHarness`` → ``ShellScriptEvaluator``. The Harbor *runtime* is
never involved; ``harbor:swebench-verified`` is only a source of task
directories.

Val — ``swebench_verified_local``
    SWE-bench Verified tasks whose ``swebench/sweb.eval.x86_64.*`` base image
    is already present in the local Docker daemon. Validating all 500 would
    need ~2 TB of images, so the subset is pinned to what is pre-pulled. Task
    dirs are copied out of the Harbor cache so this recipe owns their
    timeouts.

Train — ``rllm_swesmith_small``
    A round-robin slice of ``kylemontgomery/swesmith-filtered`` (one task per
    repo), so a smoke run exercises the real training path without pulling
    all ~4.7K SWE-smith images.

Usage::

    python recipe/qwen3_5_swe_grpo/scripts/prepare_datasets.py --train-limit 24
    xargs -a "$RLLM_HOME/datasets/rllm_swesmith_small/images.txt" -P 4 -I{} docker pull {}
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VAL_SOURCE = "swebench-verified"  # `rllm dataset pull harbor:swebench-verified`
VAL_NAME = "swebench_verified_local"
VAL_SPLIT = "test"

SWESMITH_BENCH = "rllm-swesmith"  # raw builder output
TRAIN_NAME = "rllm_swesmith_small"
TRAIN_SPLIT = "train"

# SWE-bench Verified instances whose Harbor verifier cannot score even the
# gold patch, so they would pin val reward at 0 regardless of the policy.
# Screened with: rllm eval swebench_verified_local --agent oracle.
UNSCORABLE = {
    # PASS_TO_PASS lists `test_compose_roundtrip[]` (the dimensionless unit's
    # empty pytest param id). That name never appears in the classic-style
    # pytest output, so swebench's log parser always records it as missing.
    "astropy__astropy-7606",
}

# Wall-clock budgets, in seconds. Upstream ships 3000s for both phases, which
# at rollout.n=8 makes a single training batch take hours. These are sized for
# a 4B policy: enough for a few dozen mini-swe-agent turns, and enough for the
# verifier's `pip install -e .` / `uv add` step plus the test file.
AGENT_TIMEOUT_SEC = 900.0
VERIFIER_TIMEOUT_SEC = 1800.0

_FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.MULTILINE)


def local_images() -> set[str]:
    out = subprocess.check_output(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], text=True)
    return {ln.strip() for ln in out.splitlines() if ln.strip() and "<none>" not in ln}


def base_image(task_dir: Path) -> str | None:
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.exists():
        return None
    m = _FROM_RE.search(dockerfile.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return None
    img = m.group(1)
    return img if ":" in img.rsplit("/", 1)[-1] else f"{img}:latest"


def _set_toml_key(text: str, section: str, key: str, value: float) -> str:
    """Set ``key`` under ``[section]`` in a TOML document, preserving the rest.

    A hand-rolled rewrite rather than tomlkit (not a dependency of the venv):
    these task.toml files are flat, comment-heavy tables, so a section-scoped
    line replacement is both sufficient and non-destructive.
    """
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    if start is None:
        return text.rstrip("\n") + f"\n\n{header}\n{key} = {value}\n"

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = i
            break

    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i in range(start + 1, end):
        if key_re.match(lines[i]):
            lines[i] = f"{key} = {value}"
            return "\n".join(lines) + "\n"

    lines.insert(end, f"{key} = {value}")
    return "\n".join(lines) + "\n"


def set_timeouts(task_dir: Path, *, agent: float, verifier: float) -> None:
    """Rewrite ``[agent].timeout_sec`` / ``[verifier].timeout_sec`` in task.toml.

    ``rllm.tasks.loader`` lifts both into ``task.metadata``, where
    ``BaseCliHarness`` and ``ShellScriptEvaluator`` read them.
    """
    path = task_dir / "task.toml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    text = _set_toml_key(text, "agent", "timeout_sec", agent)
    text = _set_toml_key(text, "verifier", "timeout_sec", verifier)
    path.write_text(text, encoding="utf-8")


def read_val_ids(spec: str | None) -> list[str] | None:
    """Parse --val-ids: a comma-separated list, or a file with one id per line."""
    if not spec:
        return None
    path = Path(spec)
    if path.exists():
        lines = (ln.split("#", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines())
        ids = [ln for ln in lines if ln]
    else:
        ids = [t.strip() for t in spec.split(",") if t.strip()]
    if not ids:
        sys.exit(f"--val-ids {spec!r} yielded no task ids.")
    return ids


def build_val(out_root: Path, limit: int | None, keep_unscorable: bool, pinned: list[str] | None, name: str) -> int:
    from rllm.data import DatasetRegistry

    src = DatasetRegistry.load_dataset(VAL_SOURCE, "default")
    if src is None:
        sys.exit(f"'{VAL_SOURCE}' not found. Run: rllm dataset pull harbor:{VAL_SOURCE}")

    have = local_images()
    wanted = set(pinned) if pinned else None
    picked: list[tuple[str, Path, str]] = []
    missing_image: list[str] = []
    for row in src:
        task_id = row["task_id"]
        if wanted is not None and task_id not in wanted:
            continue
        if task_id in UNSCORABLE and not keep_unscorable:
            continue
        cached = Path(row["task_path"])
        img = base_image(cached)
        if not img:
            continue
        if img in have:
            picked.append((task_id, cached, img))
        elif wanted is not None:
            missing_image.append(f"docker pull {img}   # {task_id}")

    # A pinned set is a promise about *which* tasks the run validates on, so a
    # missing image is an error rather than a silently smaller val set. Without
    # a pin the set is "whatever is pulled", which is fine for exploring but
    # means adding one image quietly changes what the numbers mean.
    if wanted is not None:
        unknown = wanted - {t for t, _, _ in picked} - {m.rsplit("# ", 1)[-1] for m in missing_image}
        if unknown:
            sys.exit(f"--val-ids names tasks that are not in '{VAL_SOURCE}': {sorted(unknown)}")
        if missing_image:
            sys.exit("Pinned val tasks whose base image is not local:\n  " + "\n  ".join(missing_image))

    picked.sort()
    if limit is not None:
        picked = picked[:limit]
    if not picked:
        sys.exit(
            "No SWE-bench Verified task has its base image locally. Pull one, e.g.\n"
            "  docker pull swebench/sweb.eval.x86_64.astropy_1776_astropy-7606:latest"
        )

    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    rows = []
    for task_id, cached, img in picked:
        dst = out / task_id
        shutil.copytree(cached, dst)
        set_timeouts(dst, agent=AGENT_TIMEOUT_SEC, verifier=VERIFIER_TIMEOUT_SEC)
        rows.append(
            {
                "id": task_id,
                "task_id": task_id,
                "task_path": str(dst),
                "instruction": row_instruction(dst),
                "question": row_instruction(dst),
                "docker_image": img,
                "data_source": "swebench_verified",
            }
        )

    DatasetRegistry.register_dataset(
        name=name,
        data=rows,
        split=VAL_SPLIT,
        source=f"harbor:{VAL_SOURCE} (local-image subset)",
        description="SWE-bench Verified subset restricted to locally available Docker images",
        category="agentic",
    )
    print(f"[val] {name}/{VAL_SPLIT}: {len(rows)} tasks -> {out}")
    for r in rows:
        print(f"       {r['task_id']}  <- {r['docker_image']}")
    return len(rows)


def row_instruction(task_dir: Path) -> str:
    p = task_dir / "instruction.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def build_train(out_root: Path, limit: int, rebuild: bool, name: str = TRAIN_NAME) -> int:
    from rllm.data.swesmith_builder import build_benchmark

    bench = out_root / SWESMITH_BENCH
    if rebuild or not bench.exists():
        build_benchmark(
            name=SWESMITH_BENCH,
            split=TRAIN_SPLIT,
            out_dir=bench,
            limit=limit,
            clean=rebuild,
            register=False,
        )

    from rllm.data import DatasetRegistry

    task_dirs = sorted(d for d in bench.iterdir() if d.is_dir() and (d / "task.toml").exists())[:limit]
    if not task_dirs:
        sys.exit(f"No SWE-smith tasks built under {bench}")

    out = out_root / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    rows = []
    for src in task_dirs:
        dst = out / src.name
        shutil.copytree(src, dst)
        set_timeouts(dst, agent=AGENT_TIMEOUT_SEC, verifier=VERIFIER_TIMEOUT_SEC)
        rows.append(
            {
                "id": src.name,
                "task_id": src.name,
                "task_path": str(dst),
                "instruction": row_instruction(dst),
                "question": row_instruction(dst),
                "docker_image": base_image(dst),
                "data_source": "rllm-swesmith",
            }
        )

    DatasetRegistry.register_dataset(
        name=name,
        data=rows,
        split=TRAIN_SPLIT,
        source="kylemontgomery/swesmith-filtered",
        description=f"SWE-smith slice ({len(rows)} tasks, round-robin across repos) for smoke-scale GRPO",
        category="agentic",
    )

    images = sorted({r["docker_image"] for r in rows if r["docker_image"]})
    (out / "images.txt").write_text("\n".join(images) + "\n", encoding="utf-8")
    missing = [i for i in images if i not in local_images()]
    print(f"[train] {name}/{TRAIN_SPLIT}: {len(rows)} tasks -> {out}")
    print(f"[train] base images: {len(images)} total, {len(missing)} not yet pulled")
    if missing:
        print(f"[train] pull them with:\n        xargs -a {out / 'images.txt'} -P 4 -I{{}} docker pull {{}}")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--val-limit", type=int, default=None, help="Cap the val subset (default: every locally available, oracle-scorable task).")
    ap.add_argument("--train-limit", type=int, default=24, help="Number of SWE-smith training tasks.")
    ap.add_argument(
        "--train-name",
        default=TRAIN_NAME,
        help=(
            f"Registry name for the training split (default: {TRAIN_NAME}). Use a distinct name to "
            "keep several sizes side by side -- rebuilding a name deletes its task dirs, which would "
            "break a run already pointing at them."
        ),
    )
    ap.add_argument("--rebuild-train", action="store_true", help="Re-download and rebuild the SWE-smith benchmark dir.")
    ap.add_argument("--keep-unscorable", action="store_true", help="Keep val tasks that even the oracle cannot score.")
    ap.add_argument(
        "--val-name",
        default=VAL_NAME,
        help=(
            f"Registry name for the val split (default: {VAL_NAME}). Rebuilding a name deletes and "
            "recopies its task dirs, so a run already pointing at them loses the task dirs mid-flight "
            "-- build a variant under a distinct name instead."
        ),
    )
    ap.add_argument(
        "--val-ids",
        default=None,
        help=(
            "Pin the val split to an explicit task-id list: either a comma-separated list or a path "
            "to a file with one id per line (blank lines and '#' comments ignored). Without it the "
            "split is 'every locally pulled task', so pulling one more image silently changes what "
            "the val numbers mean. A pinned id whose image is missing is a hard error."
        ),
    )
    ap.add_argument("--val-only", action="store_true")
    ap.add_argument("--train-only", action="store_true")
    args = ap.parse_args()

    from rllm import paths

    out_root = Path(paths.datasets_dir())
    out_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, int] = {}
    if not args.train_only:
        summary["val"] = build_val(out_root, args.val_limit, args.keep_unscorable, read_val_ids(args.val_ids), args.val_name)
    if not args.val_only:
        summary["train"] = build_train(out_root, args.train_limit, args.rebuild_train, args.train_name)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
