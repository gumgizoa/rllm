#!/usr/bin/env python3
"""Build the SWE-bench Verified evaluation subset from the Harbor registry dataset.

Pulls ``harbor:swebench-verified`` if it is not registered yet, copies the task
directories listed in ``subset-ids.txt`` (one instance id per line; blank lines
and ``#`` comments ignored) into ``$RLLM_HOME/datasets/<name>/``, applies the
fixes below, and registers the rows so the subset runs under either harness::

    rllm eval swebench_verified_100 --split test --agent harbor:mini-swe-agent --evaluator harbor_reward_fn ...
    rllm eval swebench_verified_100 --split test --agent mini-swe-agent ...

Fixes applied to the copies (the Harbor cache itself is left untouched):

* ``[environment] cpus`` / memory -- the registry ships 1 CPU / 4 GiB
  (``memory = '4G'``, the deprecated string form). The verifier runs
  ``pip install -e .`` and a pytest file per task; 1 CPU works for the Python
  repos but is slow, and the same 4 CPU / 16 GiB budget as the Pro subset
  keeps the two subsets comparable. Written as ``memory_mb``.
* ``environment/Dockerfile`` -- appends an apt config that disables
  ``Check-Valid-Until``. Harbor's mini-swe-agent scaffold runs ``apt-get update``
  in the task container before installing itself; images whose Debian/Ubuntu
  release metadata has lapsed fail that step and the agent never starts.
  Harmless on images without apt. The oracle harness is unaffected.
* ``environment/Dockerfile`` -- ``ENV OMP_NUM_THREADS=<cpus>``. Inside the task
  container ``os.cpu_count()`` reports the host's cores (256 on our hosts), so
  OpenMP code (scikit-learn's HistGradientBoosting, ...) starts that many
  threads on a 4-CPU quota and slows to a crawl: the ``scikit-learn-14710``
  verifier never finishes in 3000 s even with the reference patch, while the
  stalled tests take 2.4 s at 4 threads. Set in the image so the agent's own
  test runs get the same cap.
* ``tests/test.sh`` -- ``git clean -fd`` is narrowed to the paths the test patch
  touches. Unrestricted, it deletes every untracked file the solution created,
  so a correct fix that adds a module fails (``astropy-13398``: the reference
  patch's new ``itrs_observed_transforms.py`` is removed, the test module no
  longer imports, 0 / 72 tests). The clean still removes stray files at test
  patch paths, which is what keeps ``git apply`` of the test patch from failing.
* per-task fixes (``TASK_FIXES``) for tasks whose reference patch does not
  resolve under the Harbor verifier:

  - ``astropy__astropy-7606``: PASS_TO_PASS lists
    ``test_compose_roundtrip[]``, but current pytest names that parameter
    ``[unit0]`` (the only one of the 97 ids that differs), so the passing test
    is never matched. Renamed in ``tests/config.json``.
  - ``sphinx-doc__sphinx-9711``: the test runs through tox without ``-rA``, so
    pytest prints no per-test ``PASSED`` lines and the SWE-bench parser finds
    nothing although the test passes. ``-rA`` is passed via tox posargs.

* ids: matched case-insensitively against the registry ids.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from rllm import paths
from rllm.data import DatasetRegistry

HARBOR_DATASET = "swebench-verified"  # registered by `rllm dataset pull harbor:swebench-verified`
HARBOR_SPLIT = "default"


def read_ids(path: str) -> list[str]:
    ids = []
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return list(dict.fromkeys(ids))


def ensure_harbor_source():
    src = DatasetRegistry.load_dataset(HARBOR_DATASET, HARBOR_SPLIT)
    if src is None:
        print(f"'{HARBOR_DATASET}' not registered -- pulling harbor:{HARBOR_DATASET} ...", flush=True)
        subprocess.run(["rllm", "dataset", "pull", f"harbor:{HARBOR_DATASET}"], check=True)
        src = DatasetRegistry.load_dataset(HARBOR_DATASET, HARBOR_SPLIT)
    if src is None:
        sys.exit(f"could not load '{HARBOR_DATASET}/{HARBOR_SPLIT}' after pull")
    return src


def set_resources(task_toml: Path, cpus: int, memory_mb: int) -> None:
    text = task_toml.read_text()
    text = re.sub(r"^cpus\s*=.*$", f"cpus = {cpus}", text, flags=re.M)
    # swebench-verified writes the deprecated ``memory = '4G'`` form; replace either spelling.
    text, n = re.subn(r"^memory(_mb)?\s*=.*$", f"memory_mb = {memory_mb}", text, flags=re.M)
    if n == 0:
        text = text.replace("[environment]", f"[environment]\nmemory_mb = {memory_mb}", 1)
    task_toml.write_text(text)


APT_NO_VALID_UNTIL = "RUN mkdir -p /etc/apt/apt.conf.d && echo 'Acquire::Check-Valid-Until \"false\";' > /etc/apt/apt.conf.d/99rllm-no-valid-until  # rllm: expired Release files"


def patch_dockerfile(dockerfile: Path) -> bool:
    """Append the apt Check-Valid-Until override once (no-op on images without apt)."""
    text = dockerfile.read_text()
    if "99rllm-no-valid-until" in text:
        return False
    dockerfile.write_text(text.rstrip("\n") + "\n" + APT_NO_VALID_UNTIL + "\n")
    return True


def limit_threads(dockerfile: Path, cpus: int) -> None:
    """Cap OpenMP threads at the task's CPU quota (``os.cpu_count()`` sees the host)."""
    text = dockerfile.read_text()
    env = f"ENV OMP_NUM_THREADS={cpus}"
    if re.search(r"^ENV OMP_NUM_THREADS=\d+$", text, flags=re.M):
        text = re.sub(r"^ENV OMP_NUM_THREADS=\d+$", env, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n# rllm: os.cpu_count() reports the host's cores; cap OpenMP at the task's CPU quota\n" + env + "\n"
    dockerfile.write_text(text)


GIT_CLEAN_ALL = re.compile(r"^(\s*)git clean -fd\s*$", flags=re.M)


def narrow_git_clean(test_sh: Path) -> bool:
    """Limit ``git clean -fd`` to the test patch's paths so files the solution added survive."""
    text = test_sh.read_text()
    paths = sorted({p for pair in re.findall(r"diff --git a/(\S+) b/(\S+)", text) for p in pair})
    if not paths:
        return False
    text, n = GIT_CLEAN_ALL.subn(lambda m: f"{m.group(1)}git clean -fd -- {' '.join(shlex.quote(p) for p in paths)}", text, count=1)
    if n:
        test_sh.write_text(text)
    return bool(n)


def _fix_astropy_7606(task_dir: Path) -> None:
    cfg_path = task_dir / "tests" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    p2p = json.loads(cfg["PASS_TO_PASS"])
    p2p = [t.replace("::test_compose_roundtrip[]", "::test_compose_roundtrip[unit0]") for t in p2p]
    cfg["PASS_TO_PASS"] = json.dumps(p2p)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")


def _fix_sphinx_9711(task_dir: Path) -> None:
    test_sh = task_dir / "tests" / "test.sh"
    test_sh.write_text(test_sh.read_text().replace("tox --current-env -epy39 -v -- tests/test_extension.py", "tox --current-env -epy39 -v -- -rA tests/test_extension.py"))


# instance id -> fix applied to the copied task dir (idempotent); see the module docstring
TASK_FIXES = {
    "astropy__astropy-7606": _fix_astropy_7606,
    "sphinx-doc__sphinx-9711": _fix_sphinx_9711,
}


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default=str(here / "subset-ids.txt"), help="Text file with one instance id per line")
    ap.add_argument("--name", default="swebench_verified_100")
    ap.add_argument("--split", default="test")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=16384)
    ap.add_argument("--force", action="store_true", help="Re-copy task dirs that already exist")
    args = ap.parse_args()

    want = read_ids(args.ids)
    if not want:
        sys.exit(f"no instance ids in {args.ids}")
    src = ensure_harbor_source()
    by_id = {row["task_id"].lower(): row for row in src}

    out = Path(paths.rllm_path("datasets", args.name))
    out.mkdir(parents=True, exist_ok=True)
    rows, missing, fixed = [], [], []
    for iid in want:
        row = by_id.get(iid.lower())
        if row is None:
            missing.append(iid)
            continue
        src_dir = Path(row["task_path"])
        dst = out / src_dir.name
        if dst.exists() and args.force:
            shutil.rmtree(dst)
        if not dst.exists():
            shutil.copytree(src_dir, dst)
        set_resources(dst / "task.toml", args.cpus, args.memory_mb)
        patch_dockerfile(dst / "environment" / "Dockerfile")
        limit_threads(dst / "environment" / "Dockerfile", args.cpus)
        narrow_git_clean(dst / "tests" / "test.sh")
        if src_dir.name in TASK_FIXES:
            TASK_FIXES[src_dir.name](dst)
            fixed.append(src_dir.name)
        instruction = row.get("instruction") or (dst / "instruction.md").read_text()
        rows.append({"id": src_dir.name, "task_id": src_dir.name, "instruction": instruction, "question": instruction, "task_path": str(dst), "design_id": iid})

    if missing:
        sys.exit(f"{len(missing)} ids not found in '{HARBOR_DATASET}': {missing[:5]}")

    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=args.split,
        source=(
            f"harbor:{HARBOR_DATASET} subset from {Path(args.ids).name}; cpus={args.cpus} memory_mb={args.memory_mb}; "
            f"OMP_NUM_THREADS={args.cpus}; git clean narrowed; task fixes: {', '.join(fixed) or 'none'}"
        ),
        description=f"SWE-bench Verified subset ({len(rows)} tasks) from the Harbor registry with resource and verifier fixes",
        category="agentic",
    )
    print(f"{args.name}/{args.split}: {len(rows)} tasks -> {out}")
    print(f"  task.toml: cpus={args.cpus} memory_mb={args.memory_mb}; Dockerfile apt Check-Valid-Until off, OMP_NUM_THREADS={args.cpus}")
    print(f"  tests/test.sh: git clean -fd limited to test patch paths; task fixes: {', '.join(fixed) or 'none'}")
    print(f"  harbor harness: rllm eval {args.name} --split {args.split} --agent harbor:mini-swe-agent --evaluator harbor_reward_fn --sandbox-backend docker ...")
    print(f"  native harness: rllm eval {args.name} --split {args.split} --agent mini-swe-agent --sandbox-backend docker --agent-image auto ...")


if __name__ == "__main__":
    main()
