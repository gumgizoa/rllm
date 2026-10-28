#!/usr/bin/env python3
"""Build the swe_feat training split for the Qwen3.5-9B run from Qwen3.5-9B's own pass counts.

swe_feat is a set of Python feature-implementation tasks in the native sandbox layout
(``task.toml`` + ``environment/Dockerfile`` + ``tests/test.sh``). Each task was rolled out
with Qwen3.5-9B (openhands-sdk, the same harness this run trains) 4 times, and the tasks
that went 0/4 got 4 more attempts. The split keeps the tasks where the policy has room
to learn:

* 1-3 successes out of the first 4: some groups will carry reward spread.
* 0 out of the first 4 but at least one success in the next 4: solvable, rarely.

Tasks solved 4/4 are left out (every group would score 1.0, so RLOO gives them zero
advantage), and so are tasks never solved in 8 attempts.

The pass counts come in as two TSV files (``task_id<TAB>successes<TAB>rollouts``): the
first 4 attempts for every task, and the extra 4 for the 0/4 tasks. Task images are built
locally from each task's Dockerfile under the tag in ``task.toml`` (``rllm-task-<id>``),
which is also the tag rLLM builds at rollout time; a task whose image is missing, or whose
``docker_image`` is not that tag, stops the build rather than failing in the middle of
training.

Usage::

    python recipe/grpo/qwen3_5/scripts/prepare_swefeat.py \\
        --source "$RLLM_HOME/datasets/swe_feat" \\
        --first4 pass_dist_first4.tsv --extra4 zero4_status.tsv
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

NAME = "swefeat_9b_train"
SPLIT = "train"


def read_counts(path: str) -> dict[str, int]:
    counts = {}
    for line in open(path):
        if line.strip():
            task_id, successes, *_ = line.rstrip("\n").split("\t")
            counts[task_id] = int(successes)
    return counts


def rllm_image_tag(task_id: str) -> str:
    """The tag rllm/eval/_resolution.py builds a task's Dockerfile under."""
    return "rllm-task-" + re.sub(r"[^a-zA-Z0-9_.-]", "-", f"swe_feat/{task_id}").lower()


def image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="the swe_feat task tree (one directory per task)")
    ap.add_argument("--first4", required=True, help="TSV: successes over the first 4 attempts, every task")
    ap.add_argument("--extra4", required=True, help="TSV: successes over the 4 extra attempts of the 0/4 tasks")
    ap.add_argument("--name", default=NAME)
    args = ap.parse_args()

    from rllm import paths
    from rllm.data import DatasetRegistry

    source = Path(args.source)
    first4, extra4 = read_counts(args.first4), read_counts(args.extra4)
    picked = sorted(t for t, s in first4.items() if 1 <= s <= 3) + sorted(t for t, s in first4.items() if s == 0 and extra4.get(t, 0) > 0)
    if not picked:
        sys.exit("no task matched")

    problems = []
    for task_id in picked:
        toml_path = source / task_id / "task.toml"
        if not toml_path.exists():
            problems.append(f"{task_id}: no task dir under {source}")
            continue
        image = tomllib.loads(toml_path.read_text())["environment"]["docker_image"]
        if image != rllm_image_tag(task_id):
            problems.append(f"{task_id}: task.toml docker_image {image!r} is not the tag rLLM builds ({rllm_image_tag(task_id)!r})")
        elif not image_exists(image):
            problems.append(f"{task_id}: image {image} is not built (build it from environment/Dockerfile)")
    if problems:
        sys.exit(f"{len(problems)} of {len(picked)} tasks are not ready:\n  " + "\n  ".join(problems))

    out = Path(paths.datasets_dir()) / args.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for extra in ("dataset.toml",):
        if (source / extra).exists():
            shutil.copy2(source / extra, out / extra)

    rows = []
    for task_id in picked:
        dst = out / task_id
        shutil.copytree(source / task_id, dst)
        instruction = (dst / "instruction.md").read_text(encoding="utf-8")
        rows.append(
            {
                "id": task_id,
                "task_id": task_id,
                "task_path": str(dst),
                "instruction": instruction,
                "question": instruction,
                "docker_image": rllm_image_tag(task_id),
                "data_source": "swe_feat",
            }
        )
    DatasetRegistry.register_dataset(
        name=args.name,
        data=rows,
        split=SPLIT,
        source=f"swe_feat ({source}), Qwen3.5-9B pass counts",
        description=f"swe_feat tasks Qwen3.5-9B solved at least once but not 4/4 ({len(rows)} tasks)",
        category="agentic",
    )
    (out / "images.txt").write_text("\n".join(r["docker_image"] for r in rows) + "\n", encoding="utf-8")
    n_first = sum(1 for t in picked if 1 <= first4[t] <= 3)
    print(f"{args.name}/{SPLIT}: {len(rows)} tasks -> {out}  ({n_first} with 1-3/4 first, {len(rows) - n_first} solved only in the extra 4); all images present")


if __name__ == "__main__":
    main()
