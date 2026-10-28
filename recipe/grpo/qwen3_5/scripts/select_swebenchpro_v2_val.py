#!/usr/bin/env python3
"""Pick the validation set: N Python tasks of SWE-bench Pro V2, stratified by repository.

V2's Harbor task dirs (``scaleapi/SWE-bench_Pro-os`` ``v2/tasks``, tag ``v2.0.0``) carry no
language field, so the language comes from the HF ``ScaleAI/SWE-bench_Pro`` ``default``
config (V2, 642 rows, ``repo_language``). Every V2 Python task is in one of a few repos, and
the set takes from each in proportion to its share of them (largest-remainder rounding), with
a seeded random draw inside a repo. Only the id list is written here; the tasks are fetched,
checksum-checked, resized and registered by the eval recipe's builder::

    python recipe/grpo/qwen3_5/scripts/select_swebenchpro_v2_val.py      # -> val_tasks_swebenchpro_v2_py50.txt
    python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2_subset.py \\
        --ids recipe/grpo/qwen3_5/val_tasks_swebenchpro_v2_py50.txt --name swebenchpro_v2_py50
"""

from __future__ import annotations

import argparse
import collections
import math
import random
from pathlib import Path

HF_REPO_ID = "ScaleAI/SWE-bench_Pro"
HF_CONFIG = "default"  # V2; the original 731-task release is the "v1" config


def allocate(sizes: dict[str, int], total: int) -> dict[str, int]:
    """Largest-remainder apportionment of ``total`` over ``sizes``."""
    pool = sum(sizes.values())
    quotas = {k: total * n / pool for k, n in sizes.items()}
    alloc = {k: math.floor(q) for k, q in quotas.items()}
    for k in sorted(quotas, key=lambda k: (quotas[k] - alloc[k], k), reverse=True)[: total - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def main() -> None:
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--language", default="python")
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(here / "val_tasks_swebenchpro_v2_py50.txt"))
    args = ap.parse_args()

    from datasets import load_dataset

    rows = load_dataset(HF_REPO_ID, HF_CONFIG, split="test")
    by_repo: dict[str, list[str]] = collections.defaultdict(list)
    for r in rows:
        if r["repo_language"] == args.language:
            by_repo[r["repo"]].append(r["instance_id"])
    alloc = allocate({repo: len(ids) for repo, ids in by_repo.items()}, args.n)

    rng = random.Random(args.seed)
    picked = []
    lines = [
        f"# SWE-bench Pro V2 ({HF_REPO_ID} '{HF_CONFIG}', = SWE-bench_Pro-os v2/tasks @ v2.0.0): {args.n} {args.language} tasks,",
        f"# stratified by repo (largest remainder), random.Random({args.seed}).sample within a repo. select_swebenchpro_v2_val.py",
    ]
    for repo in sorted(by_repo):
        ids = sorted(by_repo[repo])
        take = sorted(rng.sample(ids, alloc[repo]))
        picked += take
        lines.append(f"# {repo}: {alloc[repo]} of {len(ids)}")
    Path(args.out).write_text("\n".join(lines + picked) + "\n", encoding="utf-8")
    print(f"{len(picked)} ids -> {args.out}  ({', '.join(f'{alloc[r]}/{len(by_repo[r])}' for r in sorted(by_repo))} per repo)")


if __name__ == "__main__":
    main()
