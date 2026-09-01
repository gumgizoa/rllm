#!/usr/bin/env python3
"""Verify the renderer + cumulative-token path from real rollout traces.

Capture traces first, then point this at the db::

    bash recipe/qwen3_5_swe_grpo/smoke_test.sh \\
        rllm.gateway.store=sqlite \\
        rllm.gateway.db_path="$RLLM_SCRATCH/traces/verify.db"
    python recipe/qwen3_5_swe_grpo/scripts/verify_cumulative.py

Reads the gateway's sqlite trace store and checks, per session, the invariants
the training pipeline depends on:

  A. enable_thinking  - the generation prompt opens a <think> block and the
                        sampled completion closes it.
  B. prefix extension - turn N's prompt_ids literally begins with
                        turn N-1's (prompt_ids + completion_ids). This is what
                        cumulative token mode exists to guarantee; if it holds,
                        training sees the exact tokens the policy sampled.
  C. preserve_thinking- earlier turns' <think> blocks are still present in
                        turn N's prompt (they would be dropped by Qwen3.5's
                        interleaved-thinking template on a re-render).
  D. loss mask        - replay rllm/trainer/verl/transform.py's merge and check
                        that mask==1 covers exactly the sampled completions and
                        mask==0 exactly the observation deltas.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("RLLM_SCRATCH", os.path.expanduser("~/rllm-work")), "traces", "verify.db"
)
MODEL = "Qwen/Qwen3.5-4B"


def load_sessions(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT ts.session_id, t.data, t.created_at "
        "FROM traces t JOIN trace_sessions ts ON ts.trace_id = t.trace_id "
        "ORDER BY t.created_at"
    ).fetchall()
    sessions = defaultdict(list)
    for sid, data, created in rows:
        d = json.loads(data)
        sessions[sid].append(
            {
                "created": created,
                "prompt_ids": d.get("prompt_token_ids") or [],
                "completion_ids": d.get("completion_token_ids") or [],
                "logprobs": d.get("logprobs") or [],
                "messages": d.get("messages") or [],
                "response": d.get("response_message") or {},
            }
        )
    for sid in sessions:
        sessions[sid].sort(key=lambda t: t["created"])
    return sessions


def merge_like_trainer(turns):
    """Replay transform.py: merge prefix-extending turns into one row."""
    segments = []
    seg = None
    for t in turns:
        p, a = list(t["prompt_ids"]), list(t["completion_ids"])
        if seg is not None and len(p) >= len(seg["full"]) and p[: len(seg["full"])] == seg["full"]:
            delta = p[len(seg["full"]):]
            seg["response"] += delta + a
            seg["mask"] += [0] * len(delta) + [1] * len(a)
            seg["full"] += delta + a
            seg["actions"].append(a)
            seg["deltas"].append(delta)
        else:
            if seg is not None:
                segments.append(seg)
            seg = {
                "prompt": p, "response": list(a), "mask": [1] * len(a),
                "full": p + a, "actions": [a], "deltas": [],
            }
    if seg is not None:
        segments.append(seg)
    return segments


def main():
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    think_open = tok.convert_tokens_to_ids("<think>")
    think_close = tok.convert_tokens_to_ids("</think>")

    sessions = load_sessions(DB)
    multi = {s: t for s, t in sessions.items() if len(t) > 1}
    print(f"sessions: {len(sessions)} total, {len(multi)} multi-turn\n")
    if not multi:
        print("NO MULTI-TURN SESSION YET — rerun once rollouts have progressed")
        return 1

    failures = []
    checked = 0

    for sid, turns in sorted(multi.items())[:6]:
        print(f"=== session {sid[:44]} — {len(turns)} turns ===")
        checked += 1

        # A. enable_thinking
        opens = sum(1 for t in turns if t["prompt_ids"][-2:] and think_open in t["prompt_ids"][-3:])
        closes = sum(1 for t in turns if think_close in t["completion_ids"])
        print(f"  A enable_thinking : prompt opens <think> {opens}/{len(turns)}, completion closes </think> {closes}/{len(turns)}")
        if closes == 0:
            failures.append(f"{sid[:20]}: no completion contains </think>")

        # B. prefix extension
        extends = 0
        for prev, cur in zip(turns, turns[1:]):
            base = list(prev["prompt_ids"]) + list(prev["completion_ids"])
            if len(cur["prompt_ids"]) >= len(base) and list(cur["prompt_ids"][: len(base)]) == base:
                extends += 1
        print(f"  B prefix extension: {extends}/{len(turns)-1} transitions hold")
        if extends != len(turns) - 1:
            failures.append(f"{sid[:20]}: prefix extension broken on {len(turns)-1-extends} transition(s)")

        # C. preserve_thinking - count think blocks visible in the last prompt
        last_prompt = turns[-1]["prompt_ids"]
        n_open = sum(1 for i in last_prompt if i == think_open)
        n_close = sum(1 for i in last_prompt if i == think_close)
        print(f"  C preserve_thinking: final prompt holds {n_open} <think> / {n_close} </think>  (turns={len(turns)})")
        if len(turns) > 2 and n_close < len(turns) - 1:
            failures.append(f"{sid[:20]}: final prompt has {n_close} </think>, expected >= {len(turns)-1}")

        # D. loss mask
        segs = merge_like_trainer(turns)
        print(f"  D loss mask       : {len(segs)} segment(s) for {len(turns)} turns "
              f"(1 = fully merged)")
        for si, seg in enumerate(segs):
            assert len(seg["response"]) == len(seg["mask"])
            ones = [i for i, m in enumerate(seg["mask"]) if m == 1]
            n_one, n_zero = len(ones), seg["mask"].count(0)
            sampled = sum(len(a) for a in seg["actions"])
            obs = sum(len(d) for d in seg["deltas"])
            ok_counts = (n_one == sampled) and (n_zero == obs)
            # the masked-in tokens must be exactly the concatenated completions
            masked_in = [seg["response"][i] for i in ones]
            expected = [x for a in seg["actions"] for x in a]
            ok_ids = masked_in == expected
            print(f"      seg{si}: mask1={n_one} (sampled={sampled}) mask0={n_zero} (obs={obs}) "
                  f"counts={'OK' if ok_counts else 'MISMATCH'} ids={'OK' if ok_ids else 'MISMATCH'}")
            if not ok_counts or not ok_ids:
                failures.append(f"{sid[:20]} seg{si}: loss mask does not align with sampled tokens")
            if si == 0 and ok_ids:
                dec_in = tok.decode(masked_in[:60])
                dec_out = tok.decode([seg["response"][i] for i, m in enumerate(seg["mask"]) if m == 0][:60])
                print(f"      mask=1 head: {dec_in[:90]!r}")
                print(f"      mask=0 head: {dec_out[:90]!r}")
        print()

    print("=" * 72)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1
    print(f"ALL CHECKS PASSED over {checked} multi-turn session(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
