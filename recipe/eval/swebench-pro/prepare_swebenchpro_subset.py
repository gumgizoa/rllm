#!/usr/bin/env python3
"""Build the SWE-bench Pro evaluation subset from the Harbor registry dataset.

Pulls ``harbor:swebenchpro`` if it is not registered yet, copies the task
directories listed in ``subset-ids.txt`` (one instance id per line; blank lines
and ``#`` comments ignored) into ``$RLLM_HOME/datasets/<name>/``,
applies the fixes below, and registers the rows for the native path::

    rllm eval swebenchpro_100 --split test --agent openhands-sdk --agent-image auto \\
        --hide-git-history --no-agent-network --verify-network --sandbox-backend docker ...

Fixes applied to the copies (the Harbor cache itself is left untouched):

* ``[environment] cpus`` / ``memory_mb`` -- the registry ships 1 CPU / 4 GiB.
  ``pytest -n auto`` (ansible), ``go test ./...`` (flipt, teleport, vuls,
  navidrome) and Jest (element-web, tutanota) size their parallelism by the
  host's nproc (256 here), so on 1 CPU they crawl past the verifier timeout
  and in 4 GiB the OOM killer takes out compilers and test workers
  (``signal: killed``, ``Killed``, pytest-xdist ``BrokenPipeError``). With
  4 CPUs / 16 GiB every task in the 100-task subset grades its gold patch;
  4 GiB was re-tested and fails 13 of them (2026-09-09).
* element-web ``tests/run_script.sh`` -- the registry adapter adds
  ``--maxWorkers=1 --forceExit`` to Jest (upstream SWE-bench_Pro-os never had
  it). In-band Jest lets ``@matrix-org/matrix-wysiwyg`` WASM state leak across
  test files and instance aec454dd then fails its own gold patch. The flags
  are the only difference from upstream, so they are removed.
* ``environment/Dockerfile`` -- appends an apt config that disables
  ``Check-Valid-Until``. Harbor's mini-swe-agent scaffold runs ``apt-get update``
  in the task container before installing itself; the Debian bullseye images
  (nodebb, element-web) fail that with ``Release file ... is expired`` since
  bullseye's archive metadata lapsed, so the agent never starts
  (``NonZeroAgentExitCodeError`` exit 100). The oracle harness is unaffected.
* ``environment/Dockerfile`` -- a glibc runtime beside musl on the Alpine images
  (teleport), so the openhands-sdk agent mount (``--agent-image auto``) runs there
  under ``--no-agent-network`` (``add_glibc_to_musl_images``). Each distinct base
  image is pulled and run once offline to tell musl apart.
* optionally ``[agent]`` / ``[verifier]`` ``timeout_sec`` (``--agent-timeout``,
  ``--verifier-timeout``): ``rllm eval`` reads these before the env vars, and the
  registry ships 3000 s for both (``set_timeout``).
* ids: the registry lower-cases some instance ids (``instance_nodebb__...``);
  the id list is matched case-insensitively.

The workdir comes from each Dockerfile's ``WORKDIR /app``, which
``--hide-git-history`` needs.
"""

from __future__ import annotations

import argparse
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

HARBOR_DATASET = "swebenchpro"  # registered by `rllm dataset pull harbor:swebenchpro`
HARBOR_SPLIT = "default"
JEST_FLAGS = re.compile(r" --maxWorkers=1 --forceExit\b")


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


def strip_jest_flags(run_script: Path) -> bool:
    text = run_script.read_text()
    new = JEST_FLAGS.sub("", text)
    if new != text:
        run_script.write_text(new)
        return True
    return False


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
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default=str(here / "subset-ids.txt"), help="Text file with one instance id per line")
    ap.add_argument("--name", default="swebenchpro_100")
    ap.add_argument("--split", default="test")
    ap.add_argument("--cpus", type=int, default=4)
    ap.add_argument("--memory-mb", type=int, default=16384)
    ap.add_argument("--agent-timeout", type=float, help="Write [agent].timeout_sec, seconds (default: keep the registry's 3000)")
    ap.add_argument("--verifier-timeout", type=float, help="Write [verifier].timeout_sec, seconds (default: keep the registry's 3000)")
    ap.add_argument("--jobs", type=int, default=16, help="Base images inspected at once (musl check)")
    ap.add_argument("--force", action="store_true", help="Re-copy task dirs that already exist")
    args = ap.parse_args()

    want = read_ids(args.ids)
    if not want:
        sys.exit(f"no instance ids in {args.ids}")
    src = ensure_harbor_source()
    by_id = {row["task_id"].lower(): row for row in src}

    out = Path(paths.rllm_path("datasets", args.name))
    out.mkdir(parents=True, exist_ok=True)
    rows, missing, patched = [], [], 0
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
        set_timeouts(dst / "task.toml", args.agent_timeout, args.verifier_timeout)
        if strip_jest_flags(dst / "tests" / "run_script.sh"):
            patched += 1
        patch_dockerfile(dst / "environment" / "Dockerfile")
        instruction = row.get("instruction") or (dst / "instruction.md").read_text()
        rows.append({"id": src_dir.name, "task_id": src_dir.name, "instruction": instruction, "question": instruction, "task_path": str(dst), "design_id": iid})

    if missing:
        sys.exit(f"{len(missing)} ids not found in '{HARBOR_DATASET}': {missing[:5]}")

    musl = [d.name for d in add_glibc_to_musl_images((Path(r["task_path"]) for r in rows), jobs=args.jobs)]
    (out / "musl_tasks.txt").write_text("".join(f"{t}\n" for t in musl))
    timeouts = timeouts_note(args.agent_timeout, args.verifier_timeout)

    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=args.split,
        source=(
            f"harbor:{HARBOR_DATASET} subset from {Path(args.ids).name}; cpus={args.cpus} memory_mb={args.memory_mb}{timeouts}; jest flags stripped; glibc beside musl on {len(musl)} Alpine images"
        ),
        description=f"SWE-bench Pro subset ({len(rows)} tasks) from the Harbor registry with resource and run_script fixes",
        category="agentic",
    )
    print(f"{args.name}/{args.split}: {len(rows)} tasks -> {out}")
    print(f"  task.toml: cpus={args.cpus} memory_mb={args.memory_mb}{timeouts}; run_script.sh jest flags stripped in {patched} tasks; Dockerfile apt Check-Valid-Until off")
    print(f"  glibc beside musl: {len(musl)} Alpine tasks (listed in {out / 'musl_tasks.txt'})")
    print(f"  rllm eval {args.name} --split {args.split} --agent openhands-sdk --agent-image auto --hide-git-history --no-agent-network --verify-network --sandbox-backend docker ...")


if __name__ == "__main__":
    main()
