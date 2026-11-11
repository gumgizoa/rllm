#!/usr/bin/env python3
"""Build SWE-bench Pro V2 (all 642 tasks, or the ids in ``--ids``) for native-harness runs.

SWE-bench Pro V2 is not in the Harbor registry (``harbor:swebenchpro`` is v1).
Scale ships the 642 V2 tasks as Harbor task directories in
``github.com/scaleapi/SWE-bench_Pro-os`` under ``v2/tasks`` (tag ``v2.0.0``).
This script fetches them with a sparse, blobless clone pinned to that tag,
checks every fetched file against ``v2/SHA256SUMS``, copies the tasks into
``$RLLM_HOME/datasets/<name>/``, applies the changes below, and registers the
rows::

    python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py                       # -> swebenchpro_v2_full
    python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py \\
        --ids recipe/eval/swebench-pro-v2/subset-ids.txt --name swebenchpro_v2_100    # 100-task subset
    rllm eval swebenchpro_v2_full --split test --agent openhands-sdk --agent-image auto \\
        --hide-git-history --no-agent-network --verify-network --sandbox-backend docker ...

The clone stays in ``$RLLM_HOME/datasets/_upstream/`` and is reused; ids that
are not checked out yet are added to its sparse checkout. ``--source
<dir>/v2/tasks`` uses an existing checkout instead (its ``../SHA256SUMS`` is
still checked).

Changes to the copies (the checkout is left untouched):

* ``[environment] cpus`` / ``memory_mb`` -- V2 ships 1 CPU / 4 GiB. Scale's
  release gate passes at that size on Modal; on local Docker the v1 subset of
  the same repositories needed 4 CPUs / 16 GiB (``../swebench-pro``), so the
  copies get the same budget.
* ``[environment] workdir = "/app"`` -- ``--hide-git-history`` has to know where
  the repo is, and V2's task.toml names none (every V2 image's WORKDIR is
  ``/app``).
* ``environment/Dockerfile``: the apt ``Check-Valid-Until`` override of the v1
  recipe, for harnesses that run ``apt-get update`` in the task container.
  Harmless on images without apt; the oracle is unaffected.
* ``environment/Dockerfile``: a glibc runtime beside musl on the Alpine task
  images. The openhands-sdk agent image that ``--agent-image auto`` mounts is
  built on Debian bullseye (glibc 2.31; ``rllm/sandbox/agent_image.py``), so its
  python cannot start on a musl image (77 of the 642 tasks: five repos, Go and
  JavaScript). The harness then falls back to installing the SDK in the
  sandbox, which cannot download anything under ``--no-agent-network``, and
  every such rollout fails before the agent starts. The Dockerfile copies
  bullseye's loader and libraries into ``/lib64`` and
  ``/{,usr/}lib/x86_64-linux-gnu``, paths musl does not use, so the mounted SDK
  runs and the task's own toolchain and tests keep their musl libraries. Both
  lib dirs are needed: with only ``/lib/x86_64-linux-gnu`` the glibc loader
  falls back to Alpine's musl libraries and python segfaults. The SDK itself is
  not installed in the image; it still comes from the mount, so it cannot drift
  from the harness's version. Images are told apart by ``/lib/ld-musl-*``, by
  running each base image once (offline); the list goes to ``musl_tasks.txt``.
* Optionally ``[agent]`` / ``[verifier]`` ``timeout_sec`` (``--agent-timeout``,
  ``--verifier-timeout``). ``rllm eval`` takes these limits from task.toml before
  the ``RLLM_HARNESS_RUN_TIMEOUT_S`` / ``RLLM_VERIFIER_TIMEOUT_S`` env vars, and V2
  sets both to 3000 s, so this is how a run gets other limits (the GRPO recipe
  ``recipe/grpo/qwen3_5`` trains with agent 3600 / verifier 1000).

Kept as V2 ships them:

* ``tests/run_script.sh`` -- V2's own element-web verifier keeps Jest's
  ``--maxWorkers=1 --forceExit`` and passes Scale's release gate with it.
* ``task.toml`` per-phase ``network_mode`` -- rLLM does not read it; the native
  sandbox's network comes from ``--no-agent-network`` / ``--verify-network``.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tomllib

from rllm import paths
from rllm.data import DatasetRegistry

UPSTREAM_URL = "https://github.com/scaleapi/SWE-bench_Pro-os.git"
UPSTREAM_TAG = "v2.0.0"
UPSTREAM_COMMIT = "66f92766bba642462d4bbe5479e83f91f9211862"  # v2.0.0 at release (2026-09-22); a moved tag is refused

WORKDIR = "/app"
APT_NO_VALID_UNTIL = "RUN mkdir -p /etc/apt/apt.conf.d && echo 'Acquire::Check-Valid-Until \"false\";' > /etc/apt/apt.conf.d/99rllm-no-valid-until  # rllm: expired Debian Release files"


# ---------------------------------------------------------------- source


def read_ids(path: str) -> list[str]:
    """One instance id per line; blank lines and ``#`` comments ignored, duplicates dropped."""
    ids = []
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return list(dict.fromkeys(ids))


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def fetch_upstream(ids: list[str]) -> Path:
    """Sparse checkout of ``v2/SHA256SUMS`` and the listed task dirs at UPSTREAM_TAG; returns its ``v2/tasks``."""
    repo = Path(paths.rllm_path("datasets", "_upstream", f"SWE-bench_Pro-os@{UPSTREAM_TAG}"))
    patterns = ["/v2/SHA256SUMS", *(f"/v2/tasks/{iid}/" for iid in ids)]
    if not (repo / ".git").exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        print(f"cloning {UPSTREAM_URL} @ {UPSTREAM_TAG} (sparse, {len(ids)} tasks) -> {repo}", flush=True)
        git("clone", "--quiet", "--filter=blob:none", "--no-checkout", "--depth", "1", "--branch", UPSTREAM_TAG, UPSTREAM_URL, str(repo))
        git("sparse-checkout", "set", "--no-cone", *patterns, cwd=repo)
        git("checkout", "--quiet", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo)
    if head != UPSTREAM_COMMIT:
        sys.exit(f"{repo} is at {head}, expected {UPSTREAM_COMMIT} ({UPSTREAM_TAG}); remove it and rerun")
    have = set(git("sparse-checkout", "list", cwd=repo).splitlines())
    new = [p for p in patterns if p not in have]
    if new:
        print(f"adding {len(new)} paths to the sparse checkout in {repo}", flush=True)
        git("sparse-checkout", "add", *new, cwd=repo)
    return repo / "v2" / "tasks"


def all_ids(tasks_dir: Path) -> list[str]:
    """Every task listed in ``v2/SHA256SUMS`` (the release's 642)."""
    ids = set()
    for line in (tasks_dir.parent / "SHA256SUMS").read_text().splitlines():
        parts = line.split(None, 1)[1].lstrip("*").split("/")
        if len(parts) >= 3 and parts[0] == "tasks":
            ids.add(parts[1])
    return sorted(ids)


def verify_checksums(tasks_dir: Path, ids: list[str]) -> None:
    """Every file of the listed tasks must match ``v2/SHA256SUMS`` (paths there are relative to ``v2/``)."""
    sums_file = tasks_dir.parent / "SHA256SUMS"
    if not sums_file.exists():
        sys.exit(f"{sums_file} not found; --source must point at <checkout>/v2/tasks")
    expected: dict[str, dict[str, str]] = {}
    for line in sums_file.read_text().splitlines():
        digest, rel = line.split(None, 1)
        parts = rel.lstrip("*").split("/", 2)
        if len(parts) == 3 and parts[0] == "tasks":
            expected.setdefault(parts[1], {})[rel.lstrip("*")] = digest
    bad = []
    for iid in ids:
        if iid not in expected:
            bad.append(f"{iid}: not a V2 task (absent from SHA256SUMS)")
            continue
        for rel, digest in expected[iid].items():
            f = tasks_dir.parent / rel
            if not f.is_file():
                bad.append(f"{rel}: missing")
            elif hashlib.sha256(f.read_bytes()).hexdigest() != digest:
                bad.append(f"{rel}: checksum mismatch")
    if bad:
        sys.exit(f"{len(bad)} problems against {sums_file}:\n  " + "\n  ".join(bad[:20]))


# ---------------------------------------------------------------- task.toml


def set_resources(task_toml: Path, cpus: int, memory_mb: int) -> None:
    text = task_toml.read_text()
    text = re.sub(r"^cpus\s*=.*$", f"cpus = {cpus}", text, flags=re.M)
    text = re.sub(r"^memory_mb\s*=.*$", f"memory_mb = {memory_mb}", text, flags=re.M)
    task_toml.write_text(text)


def set_workdir(task_toml: Path, workdir: str) -> None:
    """Declare ``workdir`` under ``[environment]`` (replacing one already there)."""
    text = re.sub(r"^workdir\s*=.*\n", "", task_toml.read_text(), flags=re.M)
    text = re.sub(r"^\[environment\]\s*$", f'[environment]\nworkdir = "{workdir}"', text, count=1, flags=re.M)
    task_toml.write_text(text)


# ---------------------------------------------------------------- Dockerfile


def patch_dockerfile(dockerfile: Path) -> bool:
    """Append the apt Check-Valid-Until override once (no-op on images without apt)."""
    text = dockerfile.read_text()
    if "99rllm-no-valid-until" in text:
        return False
    dockerfile.write_text(text.rstrip("\n") + "\n" + APT_NO_VALID_UNTIL + "\n")
    return True


# ---------------------------------------------------------------- main


# The openhands-sdk agent image's base (rllm/sandbox/agent_image.py), so the copied glibc is the one its venv was built for.
GLIBC_IMAGE = "debian:bullseye-slim"
GLIBC_MARKER = "rllm: glibc beside musl"
GLIBC_STAGE_NAME = "rllm-glibc"
# The comment gets a line of its own: the legacy builder rejects one trailing a FROM.
GLIBC_STAGE = f"# {GLIBC_MARKER}: the openhands-sdk agent mount is glibc-built\nFROM {GLIBC_IMAGE} AS {GLIBC_STAGE_NAME}\n"
GLIBC_COPY = (
    f"# {GLIBC_MARKER}: loader + libraries in paths musl does not use, so the mounted SDK runs\n"
    f"COPY --from={GLIBC_STAGE_NAME} /lib64/ld-linux-x86-64.so.2 /lib64/ld-linux-x86-64.so.2\n"
    f"COPY --from={GLIBC_STAGE_NAME} /lib/x86_64-linux-gnu/ /lib/x86_64-linux-gnu/\n"
    f"COPY --from={GLIBC_STAGE_NAME} /usr/lib/x86_64-linux-gnu/ /usr/lib/x86_64-linux-gnu/\n"
)
PULL_ATTEMPTS = 4


def set_timeout(task_toml: Path, section: str, seconds: float) -> None:
    """Set ``timeout_sec`` in the ``[section]`` table (``agent`` or ``verifier``), replacing any value there."""
    if seconds <= 0:
        raise ValueError(f"--{section}-timeout must be more than 0 seconds, got {seconds!r}")
    lines = task_toml.read_text().splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == f"[{section}]"), None)
    if start is None:
        raise ValueError(f"{task_toml}: no [{section}] table")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    body = [line for line in lines[start + 1 : end] if not re.match(r"\s*timeout_sec\s*=", line)]
    task_toml.write_text("".join([*lines[: start + 1], f"timeout_sec = {float(seconds)}\n", *body, *lines[end:]]))
    if tomllib.loads(task_toml.read_text())[section]["timeout_sec"] != float(seconds):
        raise RuntimeError(f"{task_toml}: [{section}] timeout_sec did not take")


def set_timeouts(task_toml: Path, agent: float | None, verifier: float | None) -> None:
    """Apply ``--agent-timeout`` / ``--verifier-timeout``; ``None`` keeps the value already there."""
    if agent is not None:
        set_timeout(task_toml, "agent", agent)
    if verifier is not None:
        set_timeout(task_toml, "verifier", verifier)


def timeouts_note(agent: float | None, verifier: float | None) -> str:
    """`` agent_timeout=... verifier_timeout=...`` for the registry source string (empty when unchanged)."""
    return "".join(f" {k}_timeout={v:g}" for k, v in (("agent", agent), ("verifier", verifier)) if v is not None)


def base_image(dockerfile: Path) -> str:
    """The task's own ``FROM`` image (not the glibc stage this module adds)."""
    for line in dockerfile.read_text().splitlines():
        if line.startswith("FROM ") and not line.rstrip().endswith(f" AS {GLIBC_STAGE_NAME}"):
            return line.split()[1]
    raise ValueError(f"{dockerfile}: no FROM line")


def ensure_image(image: str) -> None:
    """Pull ``image`` unless it is local, retrying: one registry timeout among hundreds of pulls must not end the run."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0:
        return
    err = ""
    for attempt in range(1, PULL_ATTEMPTS + 1):
        r = subprocess.run(["docker", "pull", "--quiet", image], capture_output=True, text=True)
        if r.returncode == 0:
            return
        err = r.stderr.strip()[-300:]
        if attempt < PULL_ATTEMPTS:
            time.sleep(15 * attempt)
    raise RuntimeError(f"cannot pull {image} after {PULL_ATTEMPTS} attempts: {err}")


def is_musl(image: str) -> bool:
    """True when the image's libc is musl (Alpine). Pulls the image if it is not local."""
    ensure_image(image)
    r = subprocess.run(
        ["docker", "run", "--rm", "--pull", "never", "--network", "none", "--entrypoint", "/bin/sh", image, "-c", 'for f in /lib/ld-musl-*; do [ -e "$f" ] && exit 0; done; exit 1'],
        capture_output=True,
        text=True,
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(f"cannot inspect {image}: {r.stderr.strip()[-300:]}")
    return r.returncode == 0


def add_glibc(dockerfile: Path) -> bool:
    """Put the glibc stage before the task's FROM and the copies right after it, once."""
    text = dockerfile.read_text()
    if GLIBC_MARKER in text:
        return False
    lines = text.splitlines(keepends=True)
    i = next(n for n, line in enumerate(lines) if line.startswith("FROM "))
    dockerfile.write_text("".join([GLIBC_STAGE, *lines[: i + 1], GLIBC_COPY, *lines[i + 1 :]]))
    return True


def add_glibc_to_musl_images(task_dirs: Iterable[Path], jobs: int = 16) -> list[Path]:
    """Add the glibc runtime to every task whose base image is musl; returns those task dirs.

    Each distinct base image is pulled (if missing) and run once offline, ``jobs`` at a time.
    """
    task_dirs = list(task_dirs)
    images = {d: base_image(d / "environment" / "Dockerfile") for d in task_dirs}
    distinct = sorted(set(images.values()))
    with ThreadPoolExecutor(jobs) as pool:
        musl_by_image = dict(zip(distinct, pool.map(is_musl, distinct), strict=True))
    musl = [d for d in task_dirs if musl_by_image[images[d]]]
    for d in musl:
        add_glibc(d / "environment" / "Dockerfile")
    return musl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", help="Text file with one instance id per line (default: all V2 tasks)")
    ap.add_argument("--source", help="Existing <checkout>/v2/tasks directory (default: sparse clone of the pinned tag)")
    ap.add_argument("--name", default="swebenchpro_v2_full")
    ap.add_argument("--split", default="test")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=16384)
    ap.add_argument("--agent-timeout", type=float, help="Write [agent].timeout_sec, seconds (default: keep the release's 3000)")
    ap.add_argument("--verifier-timeout", type=float, help="Write [verifier].timeout_sec, seconds (default: keep the release's 3000)")
    ap.add_argument("--jobs", type=int, default=16, help="Base images inspected at once")
    ap.add_argument("--force", action="store_true", help="Re-copy task dirs that already exist")
    args = ap.parse_args()

    if args.ids:
        want = read_ids(args.ids)
        if not want:
            sys.exit(f"no instance ids in {args.ids}")
        tasks_dir = Path(args.source).resolve() if args.source else fetch_upstream(want)
    else:
        # The id list comes from SHA256SUMS, which the first fetch brings in; a second fetch adds the task dirs.
        tasks_dir = Path(args.source).resolve() if args.source else fetch_upstream([])
        want = all_ids(tasks_dir)
        if not args.source:
            fetch_upstream(want)
    verify_checksums(tasks_dir, want)

    out = Path(paths.rllm_path("datasets", args.name))
    out.mkdir(parents=True, exist_ok=True)
    for iid in want:
        dst = out / iid
        if dst.exists() and args.force:
            shutil.rmtree(dst)
        if not dst.exists():
            shutil.copytree(tasks_dir / iid, dst)
        set_resources(dst / "task.toml", args.cpus, args.memory_mb)
        set_workdir(dst / "task.toml", WORKDIR)
        set_timeouts(dst / "task.toml", args.agent_timeout, args.verifier_timeout)
        patch_dockerfile(dst / "environment" / "Dockerfile")

    musl_dirs = add_glibc_to_musl_images((out / iid for iid in want), jobs=args.jobs)
    musl = [d.name for d in musl_dirs]

    rows = []
    for iid in want:
        instruction = (out / iid / "instruction.md").read_text()
        rows.append({"id": iid, "task_id": iid, "instruction": instruction, "question": instruction, "task_path": str(out / iid), "design_id": iid})
    timeouts = timeouts_note(args.agent_timeout, args.verifier_timeout)
    ids_note = f" ids from {Path(args.ids).name}" if args.ids else ""
    source = f"github:scaleapi/SWE-bench_Pro-os@{UPSTREAM_TAG} v2/tasks" if not args.source else f"{tasks_dir}"
    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=args.split,
        source=f"{source}{ids_note}; cpus={args.cpus} memory_mb={args.memory_mb} workdir={WORKDIR}{timeouts}; glibc beside musl on {len(musl)} Alpine images",
        description=f"SWE-bench Pro V2 ({len(rows)} tasks) from Scale's Harbor task tree, for native harnesses with the agent offline",
        category="agentic",
    )
    (out / "musl_tasks.txt").write_text("".join(f"{iid}\n" for iid in musl))
    print(f"{args.name}/{args.split}: {len(rows)} tasks -> {out} (files checked against v2/SHA256SUMS)")
    print(f"  task.toml: cpus={args.cpus} memory_mb={args.memory_mb} workdir={WORKDIR}{timeouts}; Dockerfile apt Check-Valid-Until off")
    print(f"  glibc beside musl: {len(musl)} Alpine tasks (listed in {out / 'musl_tasks.txt'})")


if __name__ == "__main__":
    main()
