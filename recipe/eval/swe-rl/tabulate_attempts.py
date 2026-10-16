#!/usr/bin/env python3
"""Histogram of per-task successes (0/N .. N/N) from an ``rllm eval --attempts N`` run.

``results.json`` holds one item per rollout with ``idx`` (task index in the
dataset split) and ``attempt``; this script groups them by task, joins the
task id and language from the registered parquet, and prints the k/N
distribution overall and per language. ``--csv`` additionally writes one row
per task (instance_id, language, n_attempts, n_correct, n_errors).

Usage::

    python recipe/eval/swe-rl/tabulate_attempts.py $RLLM_HOME/eval_results/<run>/results.json \
        --dataset swe_rl_v1 --split test [--csv per_task.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


def load_task_order(dataset: str, split: str) -> list[dict]:
    import pandas as pd

    home = Path(os.environ.get("RLLM_HOME") or Path.home() / ".rllm").expanduser()
    df = pd.read_parquet(home / "datasets" / dataset / f"{split}.parquet")
    return df.to_dict("records")


def load_idx_map_from_episodes(episodes_dir: Path) -> dict[int, dict]:
    """``rollout_idx -> {task_id, language}`` from ``episodes/episode_<rollout_idx>_<task>_<attempt>.json``.

    The eval engine's task order is not guaranteed to match the parquet row
    order (``--task-indices`` subsets, for one), so the episode files are the
    authoritative join key when they were saved.
    """
    out: dict[int, dict] = {}
    for f in sorted(episodes_dir.glob("episode_*.json")):
        try:
            e = json.loads(f.read_text())
        except Exception:
            continue
        idx = e.get("eval_idx")
        if idx is None:
            idx = int(f.name.split("_")[1])
        task = e.get("task") or {}
        meta = task.get("metadata") or {}
        out.setdefault(int(idx), {"task_id": meta.get("instance_id") or task.get("task", {}).get("name"), "language": meta.get("language", "?")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path, nargs="+", help="results.json file(s); batch runs pass all batch_*/results.json")
    ap.add_argument("--dataset", default="swe_rl_v1")
    ap.add_argument("--split", default="test")
    ap.add_argument("--csv", type=Path, default=None)
    args = ap.parse_args()

    # Keyed by instance_id so several results.json (one per batch, each with
    # its own idx space) aggregate into one table. Files are processed in
    # sorted order and a task seen again in a later file (a retry pass named
    # to sort after batch_*) replaces its earlier attempts instead of adding
    # to them, so a retried task still has exactly N attempts.
    per_task: dict[str, dict] = defaultdict(lambda: {"language": "?", "n": 0, "correct": 0, "errors": 0})
    task_source: dict[str, str] = {}
    n_attempts = 0
    tasks = None
    for res in sorted(args.results):
        data = json.loads(res.read_text())
        items = data.get("items") or data
        n_attempts = max(n_attempts, int(data.get("attempts") or max((it.get("attempt", 0) for it in items), default=0) + 1))
        episodes_dir = res.parent / "episodes"
        idx_map = load_idx_map_from_episodes(episodes_dir) if episodes_dir.is_dir() else {}
        if not idx_map and tasks is None:
            tasks = load_task_order(args.dataset, args.split)
        n_att = int(data.get("attempts") or 1)
        for it in items:
            idx = int(it["idx"])
            # Episode files are numbered per rollout: task_idx * attempts + attempt
            # (the engine expands each task into `attempts` adjacent rollouts).
            rollout_idx = idx * n_att + int(it.get("attempt", 0))
            meta = idx_map.get(rollout_idx) or (tasks[idx] if tasks and idx < len(tasks) else {})
            key = meta.get("task_id") or f"{res.parent.name}:idx{idx}"
            if task_source.get(key) not in (None, str(res)):
                per_task[key] = {"language": "?", "n": 0, "correct": 0, "errors": 0}  # later file replaces earlier
            task_source[key] = str(res)
            t = per_task[key]
            t["language"] = meta.get("language", "?")
            t["n"] += 1
            t["correct"] += 1 if it.get("is_correct") else 0
            t["errors"] += 1 if it.get("error") else 0

    rows = [{"instance_id": k, "language": t["language"], "n_attempts": t["n"], "n_correct": t["correct"], "n_errors": t["errors"]} for k, t in sorted(per_task.items())]

    def histogram(subset: list[dict]) -> Counter:
        return Counter(r["n_correct"] for r in subset)

    def print_hist(title: str, subset: list[dict]) -> None:
        h = histogram(subset)
        total = len(subset)
        print(f"\n{title}  (tasks={total}, attempts/task={n_attempts})")
        print(f"  {'k/N':>6} {'tasks':>6} {'share':>7}")
        for k in range(n_attempts + 1):
            c = h.get(k, 0)
            print(f"  {k:>3}/{n_attempts:<2} {c:>6} {c / total * 100 if total else 0:>6.1f}%")
        solved_any = sum(1 for r in subset if r["n_correct"] > 0)
        rollouts = sum(r["n_attempts"] for r in subset)
        passed = sum(r["n_correct"] for r in subset)
        errs = sum(r["n_errors"] for r in subset)
        print(f"  pass@1 (mean)={passed / rollouts * 100 if rollouts else 0:.1f}%  pass@{n_attempts} (any)={solved_any / total * 100 if total else 0:.1f}%  errors={errs}/{rollouts}")

    print_hist("ALL", rows)
    for lang in sorted({r["language"] for r in rows}):
        print_hist(lang, [r for r in rows if r["language"] == lang])

    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nper-task csv -> {args.csv}")


if __name__ == "__main__":
    main()
