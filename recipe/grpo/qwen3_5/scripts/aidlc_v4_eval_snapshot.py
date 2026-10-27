"""aidlc_v4_eval's verdicts on the saved evaluation runs, kept as a snapshot the next change is diffed against.

    uv run --no-sync python recipe/grpo/qwen3_5/scripts/aidlc_v4_eval_snapshot.py check [--from NAME=JSONL ...]
    uv run --no-sync python recipe/grpo/qwen3_5/scripts/aidlc_v4_eval_snapshot.py make  [--from NAME=JSONL ...]

The snapshot (``workflows/aidlc_v4_eval/snapshot/``) holds, for every saved run of the datasets it names, the
value of every scored item (``aidlc/atom/*``, ``check/*``, ``proc/*``, ``form/*``, ``rule/*``, ``run/*``), the
kind scores and the total; and ``audited.json``, the cells an independent reviewer confirmed against the
trajectory (the audits of tasks/2026-10-21, their result files), with the value they confirmed.

``check`` rescores the datasets (``rescore_compliance.py``, judge off; or reads rescored jsonl given with
``--from``), prints every cell whose value differs from the snapshot -- audited cells first -- and exits 1
when any does. A verifier change is committed with a reason for each line it prints, then ``make`` writes
the new snapshot. Datasets are read from the local disks the snapshot names; where they are missing the
check skips them and says so. The snapshot cannot test what no saved run violates (19 methods at the time
of writing): the synthetic cases (tests/test_aidlc_v4_eval_cases.py) do that.
"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
SNAP = RECIPE / "workflows" / "aidlc_v4_eval" / "snapshot"
TASK = REPO / "tasks" / "2026-10-21-aidlc-v4-eval-verifier"
DATASETS = {
    "swebv100": "/gpfs/home/daink/2026-2_DFM/rllm-home/eval_results/swebv100_aidlcv4_262k-150_think_t1_prefix/episodes",
    "step24": "/mnt/nas1/mmi/gwan7801/rllm-home/eval_results/swebench_verified_500_qwen3_5-9b-aidlc-reward-swegym293-v2-step24_20261015_004741/episodes",
}
KEPT = ("aidlc/atom/", "aidlc/check/", "aidlc/proc/", "aidlc/form/", "aidlc/rule/", "aidlc/run/", "aidlc/kind/", "aidlc/score")
AUDITS = ("out/rule_logic_audit/result_*.json", "out/rule_logic_audit_new/result_*.json", "out/rule_logic_audit_6/result_*.json")  # (data, episode, item, verdict)


def load_jsonl(path: Path) -> dict[str, dict[str, float]]:
    out = {}
    for line in open(path):
        r = json.loads(line)
        out[r["episode"]] = {k: v for k, v in r["signals"].items() if k.startswith(KEPT)}
    return out


def rescore(name: str, out_dir: Path) -> Path | None:
    src = DATASETS[name]
    if not Path(src).is_dir():
        print(f"{name}: no data at {src}, skipped")
        return None
    out = out_dir / f"{name}.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIDLC_JUDGE_")}
    cmd = [sys.executable, str(RECIPE / "scripts" / "rescore_compliance.py"), src, "--workflow", "aidlc_v4_eval", "--out", str(out)]
    subprocess.run(cmd, check=True, env=env, cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def signals(args) -> dict[str, dict[str, dict[str, float]]]:
    given = dict(pair.split("=", 1) for pair in args.from_ or [])
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name in DATASETS:
            path = Path(given[name]) if name in given else rescore(name, Path(tmp))
            if path is not None:
                out[name] = load_jsonl(path)
    return out


def audited() -> list[dict]:
    rows = []
    for pat in AUDITS:
        for f in sorted(glob.glob(str(TASK / pat))):
            for r in json.load(open(f)):
                rows.append({"data": r["data"], "episode": r["episode"], "item": r["item"], "verdict": r["verdict"], "audit": Path(f).parent.name})
    return rows


def make(args) -> int:
    values = signals(args)
    SNAP.mkdir(exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    meta = {"written": str(date.today()), "commit": commit, "datasets": {n: {"dir": DATASETS[n], "runs": len(v)} for n, v in values.items()}}
    with gzip.open(SNAP / "signals.json.gz", "wt") as f:
        json.dump({"meta": meta, "values": values}, f, separators=(",", ":"))
    rows = []
    for a in audited():
        v = values.get(a["data"], {}).get(a["episode"], {}).get(f"aidlc/{a['item']}")
        rows.append({**a, "expected": v})
    (SNAP / "audited.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0) + "\n")
    print(f"snapshot written: {meta}; audited cells {len(rows)}")
    return 0


def check(args) -> int:
    with gzip.open(SNAP / "signals.json.gz", "rt") as f:
        snap = json.load(f)
    old, meta = snap["values"], snap["meta"]
    new = signals(args)
    flagged = {(a["data"], a["episode"], a["item"]): a for a in json.load(open(SNAP / "audited.json"))}
    diffs = []
    for name, runs in new.items():
        if name not in old:
            print(f"{name}: not in the snapshot, skipped")
            continue
        for ep, sig in runs.items():
            before = old[name].get(ep, {})
            for k in sorted(set(before) | set(sig)):
                if before.get(k) != sig.get(k):
                    item = k.removeprefix("aidlc/")
                    diffs.append((bool(flagged.get((name, ep, item))), name, ep, item, before.get(k), sig.get(k)))
    diffs.sort(key=lambda d: (not d[0], d[1], d[2], d[3]))
    print(f"snapshot {meta['written']} @ {meta['commit']}; datasets checked {sorted(new)}; cells differing {len(diffs)}")
    for aud, name, ep, item, a, b in diffs:
        tag = f"  AUDITED({flagged[(name, ep, item)]['verdict']})" if aud else ""
        print(f"  {name} {ep[8:14]} {item}: {a} -> {b}{tag}")
    return 1 if diffs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["make", "check"])
    ap.add_argument("--from", dest="from_", action="append", metavar="NAME=JSONL", help="rescored signals to use instead of rescoring (rescore_compliance.py output)")
    args = ap.parse_args()
    return make(args) if args.command == "make" else check(args)


if __name__ == "__main__":
    sys.exit(main())
