#!/usr/bin/env python3
"""Build SWE-bench Pro V2 (all 642 tasks by default) for native-harness runs with the agent offline.

Same source, checksums and fixes as ``prepare_swebenchpro_v2_subset.py`` (whose
functions this reuses; that script and the subsets it built are left as they
are), plus what a full run needs:

* ``[environment] workdir = "/app"`` always -- ``--hide-git-history`` has to know
  where the repo is, and V2's task.toml names none (every V2 image's WORKDIR is
  ``/app``).
* A glibc runtime beside musl on the Alpine task images. The openhands-sdk agent
  image that ``--agent-image auto`` mounts is built on Debian bullseye (glibc
  2.31; ``rllm/sandbox/agent_image.py``), so its python cannot start on a musl
  image (77 of the 642 tasks: five repos, Go and JavaScript). The harness then
  falls back to installing the SDK in the sandbox, which cannot download
  anything under ``--no-agent-network``, and every such rollout fails before
  the agent starts. The Dockerfile copies bullseye's loader and libraries into
  ``/lib64`` and ``/{,usr/}lib/x86_64-linux-gnu``, paths musl does not use, so the
  mounted SDK runs and the task's own toolchain and tests keep their musl
  libraries. Both lib dirs are needed: with only ``/lib/x86_64-linux-gnu`` the
  glibc loader falls back to Alpine's musl libraries and python segfaults.
  The SDK itself is not installed in the image; it still comes from the mount,
  so it cannot drift from the harness's version. Images are told apart by
  ``/lib/ld-musl-*``, by running each base image once (offline).

::

    python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py            # -> swebenchpro_v2_full
    rllm eval swebenchpro_v2_full --split test --agent openhands-sdk --agent-image auto \\
        --hide-git-history --no-agent-network --verify-network --sandbox-backend docker ...
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from prepare_swebenchpro_v2_subset import (
    UPSTREAM_TAG,
    fetch_upstream,
    patch_dockerfile,
    read_ids,
    set_resources,
    set_workdir,
    verify_checksums,
)

from rllm import paths
from rllm.data import DatasetRegistry

WORKDIR = "/app"
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


def all_ids(tasks_dir: Path) -> list[str]:
    """Every task listed in ``v2/SHA256SUMS`` (the release's 642)."""
    ids = set()
    for line in (tasks_dir.parent / "SHA256SUMS").read_text().splitlines():
        parts = line.split(None, 1)[1].lstrip("*").split("/")
        if len(parts) >= 3 and parts[0] == "tasks":
            ids.add(parts[1])
    return sorted(ids)


def base_image(dockerfile: Path) -> str:
    for line in dockerfile.read_text().splitlines():
        if line.startswith("FROM ") and not line.rstrip().endswith(f" AS {GLIBC_STAGE_NAME}"):
            return line.split()[1]
    raise ValueError(f"{dockerfile}: no FROM line")


def is_musl(image: str) -> bool:
    """True when the image's libc is musl (Alpine). Pulls the image if it is not local."""
    r = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/sh", image, "-c", 'for f in /lib/ld-musl-*; do [ -e "$f" ] && exit 0; done; exit 1'],
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", help="Text file with one instance id per line (default: all V2 tasks)")
    ap.add_argument("--source", help="Existing <checkout>/v2/tasks directory (default: sparse clone of the pinned tag)")
    ap.add_argument("--name", default="swebenchpro_v2_full")
    ap.add_argument("--split", default="test")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=16384)
    ap.add_argument("--jobs", type=int, default=16, help="Base images inspected at once")
    ap.add_argument("--force", action="store_true", help="Re-copy task dirs that already exist")
    args = ap.parse_args()

    if args.ids:
        want = read_ids(args.ids)
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
        patch_dockerfile(dst / "environment" / "Dockerfile")

    images = {iid: base_image(out / iid / "environment" / "Dockerfile") for iid in want}
    with ThreadPoolExecutor(args.jobs) as pool:
        musl_by_image = dict(zip(sorted(set(images.values())), pool.map(is_musl, sorted(set(images.values()))), strict=True))
    musl = [iid for iid in want if musl_by_image[images[iid]]]
    for iid in musl:
        add_glibc(out / iid / "environment" / "Dockerfile")

    rows = []
    for iid in want:
        instruction = (out / iid / "instruction.md").read_text()
        rows.append({"id": iid, "task_id": iid, "instruction": instruction, "question": instruction, "task_path": str(out / iid), "design_id": iid})
    source = f"github:scaleapi/SWE-bench_Pro-os@{UPSTREAM_TAG} v2/tasks" if not args.source else f"{tasks_dir}"
    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=args.split,
        source=f"{source}{f' ids from {Path(args.ids).name}' if args.ids else ''}; cpus={args.cpus} memory_mb={args.memory_mb} workdir={WORKDIR}; glibc beside musl on {len(musl)} Alpine images",
        description=f"SWE-bench Pro V2 ({len(rows)} tasks) from Scale's Harbor task tree, for native harnesses with the agent offline",
        category="agentic",
    )
    (out / "musl_tasks.txt").write_text("".join(f"{iid}\n" for iid in musl))
    print(f"{args.name}/{args.split}: {len(rows)} tasks -> {out} (files checked against v2/SHA256SUMS)")
    print(f"  task.toml: cpus={args.cpus} memory_mb={args.memory_mb} workdir={WORKDIR}; Dockerfile apt Check-Valid-Until off")
    print(f"  glibc beside musl: {len(musl)} tasks on {sum(musl_by_image.values())} Alpine images (listed in {out / 'musl_tasks.txt'})")


if __name__ == "__main__":
    main()
