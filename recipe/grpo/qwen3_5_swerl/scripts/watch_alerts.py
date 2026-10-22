"""Relative alerts for a running qwen3_5_swerl training: compare each step with the run's own start.

Watches two signals, each against its baseline = mean of the first ``--baseline-steps`` steps:
  * text-only end ratio -- the last assistant turn has no tool call (from the episode logs);
    Run 3 drifted from ~10% to 20-26% while validation stalled;
  * ``offpolicy/training_ppl`` -- from the transcript's per-step ``step:N - ...`` line.
Alerts go to stdout and ``--out`` (one line each); exit status 2 when any alert fired.

    python recipe/grpo/qwen3_5_swerl/scripts/watch_alerts.py \\
        --log $RLLM_RUN_DIR/logs/train_<run id>.log \\
        --episodes $RLLM_HOME/episodes/<project>/<experiment>/<run id>/episodes
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time

STEP_LINE = re.compile(r"step:(\d+) - (.+)")
METRIC = re.compile(r"([A-Za-z0-9_/.\-]+):(?:np\.float64\()?([-0-9.e+]+)\)?")


def ppl_by_step(log: str) -> dict[int, float]:
    text = re.sub(r"\x1b\[[0-9;]*m", "", open(log, errors="replace").read())
    out = {}
    for step, rest in STEP_LINE.findall(text):
        m = dict(METRIC.findall(rest))
        if "offpolicy/training_ppl" in m:
            out[int(step)] = float(m["offpolicy/training_ppl"])
    return out


def text_end_by_step(episodes: str) -> dict[int, float]:
    out = {}
    for d in glob.glob(os.path.join(episodes, "train_step_*")):
        step = int(re.search(r"train_step_(\d+)_", d).group(1))
        n = text = 0
        for f in glob.glob(os.path.join(d, "episode_*.json")):
            ep = json.load(open(f))
            steps = (ep.get("trajectories") or [{}])[0].get("steps") or []
            chat = (steps[-1].get("chat_completions") if steps else None) or []
            assistant = [m for m in chat if m.get("role") == "assistant"]
            if not assistant:
                continue
            n += 1
            text += not assistant[-1].get("tool_calls")
        if n:
            out[step] = text / n
    return out


def check(name: str, series: dict[int, float], k: int, factor: float, min_abs: float) -> list[str]:
    steps = sorted(series)
    if len(steps) <= k:
        return []
    base = sum(series[s] for s in steps[:k]) / k
    alerts = []
    for s in steps[k:]:
        v = series[s]
        if v >= base * factor and v - base >= min_abs:
            alerts.append(f"[{time.strftime('%F %T')}] ALERT step {s}: {name} {v:.4f} vs start {base:.4f} (x{v / base:.2f})")
    return alerts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True, help="training transcript (train_verl.sh TRAIN_LOG)")
    ap.add_argument("--episodes", required=True, help="episode log dir containing train_step_N_epoch_E/")
    ap.add_argument("--baseline-steps", type=int, default=2)
    ap.add_argument("--text-end-factor", type=float, default=1.5)
    ap.add_argument("--text-end-min-abs", type=float, default=0.05, help="also require this absolute rise")
    ap.add_argument("--ppl-factor", type=float, default=1.10)
    ap.add_argument("--out", default=None, help="append alerts here")
    a = ap.parse_args()
    alerts = check("text_end_ratio", text_end_by_step(a.episodes), a.baseline_steps, a.text_end_factor, a.text_end_min_abs)
    alerts += check("training_ppl", ppl_by_step(a.log), a.baseline_steps, a.ppl_factor, 0.0)
    for line in alerts:
        print(line)
    if alerts and a.out:
        with open(a.out, "a") as f:
            f.write("\n".join(alerts) + "\n")
    return 2 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
