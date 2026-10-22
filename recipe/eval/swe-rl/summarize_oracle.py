#!/usr/bin/env python3
"""Merge the per-batch oracle results of a run_batches.sh run into one verdict per task.

Each batch directory (``b16_*``, ``b32_*``, ``batch_*``, ``retry_*``) holds a
``results.json`` whose ``idx`` is local to that batch, so tasks are joined on
instance_id via the saved episodes. When a task appears in several
directories (a retry pass after an infra error), the directory that sorts
last wins, so name retry passes so they sort after ``batch_*``.

Prints pass/fail/error counts overall and per language and writes:
  <run_dir>/oracle_verdicts.jsonl   one line per task: instance_id, language, reward, error, source
  <run_dir>/oracle_fail_ids.txt     instance ids with reward < 1 or an error (exclude from rollouts)

Usage::

    python recipe/eval/swe-rl/summarize_oracle.py $RLLM_HOME/eval_results/oracle_v1
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_dir(d: Path) -> dict[str, dict]:
    res = d / "results.json"
    if not res.exists():
        return {}
    data = json.loads(res.read_text())
    idx_map: dict[int, dict] = {}
    for f in (d / "episodes").glob("episode_*.json"):
        try:
            e = json.loads(f.read_text())
        except Exception:
            continue
        idx = e.get("eval_idx")
        if idx is None:
            idx = int(f.name.split("_")[1])
        meta = (e.get("task") or {}).get("metadata") or {}
        idx_map[int(idx)] = {"task_id": meta.get("instance_id"), "language": meta.get("language", "?")}
    out = {}
    for it in data.get("items", []):
        m = idx_map.get(int(it["idx"]))
        if not m or not m["task_id"]:
            continue
        out[m["task_id"]] = {
            "instance_id": m["task_id"],
            "language": m["language"],
            "reward": float(it.get("reward") or 0.0),
            "error": it.get("error"),
            "source": d.name,
        }
    return out


def main() -> None:
    run_dir = Path(sys.argv[1])
    verdict: dict[str, dict] = {}
    dirs = sorted(p for p in run_dir.iterdir() if p.is_dir() and (p / "results.json").exists())
    for d in dirs:
        verdict.update(load_dir(d))  # later directories override earlier ones

    by_lang: dict[str, Counter] = defaultdict(Counter)
    for v in verdict.values():
        state = "error" if v["error"] else ("pass" if v["reward"] >= 1.0 else "fail")
        by_lang[v["language"]][state] += 1
        by_lang["ALL"][state] += 1

    print(f"{'lang':<12}{'tasks':>7}{'pass':>7}{'fail':>7}{'error':>7}{'pass%':>8}")
    for lang in sorted(by_lang, key=lambda k: (k != "ALL", k)):
        c = by_lang[lang]
        n = sum(c.values())
        print(f"{lang:<12}{n:>7}{c['pass']:>7}{c['fail']:>7}{c['error']:>7}{c['pass'] / n * 100 if n else 0:>7.1f}%")

    with (run_dir / "oracle_verdicts.jsonl").open("w") as f:
        for v in sorted(verdict.values(), key=lambda x: x["instance_id"]):
            f.write(json.dumps(v) + "\n")
    bad = sorted(k for k, v in verdict.items() if v["error"] or v["reward"] < 1.0)
    (run_dir / "oracle_fail_ids.txt").write_text("\n".join(bad) + ("\n" if bad else ""))
    print(f"\n{len(dirs)} result dirs merged, {len(verdict)} tasks; {len(bad)} failing ids -> {run_dir / 'oracle_fail_ids.txt'}")


if __name__ == "__main__":
    main()
