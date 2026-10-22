#!/usr/bin/env python3
"""Build the SWE-bench Pro V2 evaluation subset from Scale's Harbor task tree.

SWE-bench Pro V2 is not in the Harbor registry (``harbor:swebenchpro`` is v1).
Scale ships the 642 V2 tasks as Harbor task directories in
``github.com/scaleapi/SWE-bench_Pro-os`` under ``v2/tasks`` (tag ``v2.0.0``).
This script fetches only the task directories listed in ``subset-ids.txt``
(one instance id per line; blank lines and ``#`` comments ignored) with a
sparse, blobless clone pinned to that tag, checks every fetched file against
``v2/SHA256SUMS``, copies the tasks into ``$RLLM_HOME/datasets/<name>/``,
applies the fixes below, and registers the rows so the subset runs under
either harness::

    rllm eval swebenchpro_v2_100 --split test --agent openhands-sdk --agent-image auto ...
    rllm eval swebenchpro_v2_100 --split test --agent harbor:openhands-sdk --evaluator harbor_reward_fn ...

The clone stays in ``$RLLM_HOME/datasets/_upstream/`` and is reused; ids that
are not checked out yet are added to its sparse checkout. ``--source
<dir>/v2/tasks`` uses an existing checkout instead (its ``../SHA256SUMS`` is
still checked).

Fixes applied to the copies (the checkout is left untouched):

* ``[environment] cpus`` / ``memory_mb`` -- V2 ships 1 CPU / 4 GiB, like the
  v1 registry. Scale's release gate passes at that size on Modal; on local
  Docker the v1 subset of the same repositories needed 4 CPUs / 16 GiB
  (``../swebench-pro``), so the copies get the same budget.
* ``environment/Dockerfile`` -- the apt ``Check-Valid-Until`` override of the
  v1 recipe, for harnesses that run ``apt-get update`` in the task container.
  Harmless on images without apt; the oracle is unaffected.

Kept as V2 ships them:

* ``tests/run_script.sh`` -- V2's own element-web verifier keeps Jest's
  ``--maxWorkers=1 --forceExit`` and passes Scale's release gate with it.
  Every gold patch in the subset grades with the flags, including aec454dd,
  for which the v1 recipe has to strip them from the registry adapter.
* ``task.toml`` per-phase ``network_mode`` -- Harbor 0.3.0 ignores it and
  native rLLM sandboxes have no per-phase network policy (README, Appendix).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rllm import paths
from rllm.data import DatasetRegistry

UPSTREAM_URL = "https://github.com/scaleapi/SWE-bench_Pro-os.git"
UPSTREAM_TAG = "v2.0.0"
UPSTREAM_COMMIT = "66f92766bba642462d4bbe5479e83f91f9211862"  # v2.0.0 at release (2026-09-22); a moved tag is refused


def read_ids(path: str) -> list[str]:
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


def set_resources(task_toml: Path, cpus: int, memory_mb: int) -> None:
    text = task_toml.read_text()
    text = re.sub(r"^cpus\s*=.*$", f"cpus = {cpus}", text, flags=re.M)
    text = re.sub(r"^memory_mb\s*=.*$", f"memory_mb = {memory_mb}", text, flags=re.M)
    task_toml.write_text(text)


APT_NO_VALID_UNTIL = "RUN mkdir -p /etc/apt/apt.conf.d && echo 'Acquire::Check-Valid-Until \"false\";' > /etc/apt/apt.conf.d/99rllm-no-valid-until  # rllm: expired Debian Release files"


def patch_dockerfile(dockerfile: Path) -> bool:
    """Append the apt Check-Valid-Until override once (no-op on images without apt)."""
    text = dockerfile.read_text()
    if "99rllm-no-valid-until" in text:
        return False
    dockerfile.write_text(text.rstrip("\n") + "\n" + APT_NO_VALID_UNTIL + "\n")
    return True


def main() -> None:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default=str(here / "subset-ids.txt"), help="Text file with one instance id per line")
    ap.add_argument("--source", help="Existing <checkout>/v2/tasks directory (default: sparse clone of the pinned tag)")
    ap.add_argument("--name", default="swebenchpro_v2_100")
    ap.add_argument("--split", default="test")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=16384)
    ap.add_argument("--force", action="store_true", help="Re-copy task dirs that already exist")
    args = ap.parse_args()

    want = read_ids(args.ids)
    if not want:
        sys.exit(f"no instance ids in {args.ids}")
    tasks_dir = Path(args.source).resolve() if args.source else fetch_upstream(want)
    verify_checksums(tasks_dir, want)

    out = Path(paths.rllm_path("datasets", args.name))
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for iid in want:
        dst = out / iid
        if dst.exists() and args.force:
            shutil.rmtree(dst)
        if not dst.exists():
            shutil.copytree(tasks_dir / iid, dst)
        set_resources(dst / "task.toml", args.cpus, args.memory_mb)
        patch_dockerfile(dst / "environment" / "Dockerfile")
        instruction = (dst / "instruction.md").read_text()
        rows.append({"id": iid, "task_id": iid, "instruction": instruction, "question": instruction, "task_path": str(dst), "design_id": iid})

    source = f"github:scaleapi/SWE-bench_Pro-os@{UPSTREAM_TAG} v2/tasks" if not args.source else f"{tasks_dir}"
    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=args.split,
        source=f"{source} subset from {Path(args.ids).name}; cpus={args.cpus} memory_mb={args.memory_mb}",
        description=f"SWE-bench Pro V2 subset ({len(rows)} tasks) from Scale's Harbor task tree with resource fixes",
        category="agentic",
    )
    print(f"{args.name}/{args.split}: {len(rows)} tasks -> {out} (files checked against v2/SHA256SUMS)")
    print(f"  task.toml: cpus={args.cpus} memory_mb={args.memory_mb}; Dockerfile apt Check-Valid-Until off; run_script.sh unchanged")
    print(f"  native harness: rllm eval {args.name} --split {args.split} --agent openhands-sdk --agent-image auto --sandbox-backend docker ...")
    print(f"  harbor harness: rllm eval {args.name} --split {args.split} --agent harbor:openhands-sdk --evaluator harbor_reward_fn --sandbox-backend docker ...")


if __name__ == "__main__":
    main()
