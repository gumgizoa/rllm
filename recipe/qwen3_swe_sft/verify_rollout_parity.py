#!/usr/bin/env python3
"""Check that the SFT text rLLM will train on equals the prompt the SkyRL-OpenHands
rollout will feed the model, turn by turn.

Training side (rLLM ``cumulative`` in rllm/trainer/verl/sft_dataset.py):
    text = "".join(QwenChatTemplateParser.parse([m]) for m in messages)
    loss on assistant segments ("<|im_start|>assistant\\n{content}<|im_end|>\\n")

Rollout side (SkyRL verl/workers/agentic/codeact.py::OnlineCodeActAgent.step):
    prompt_k = tokenizer.apply_chat_template(messages[:k], add_generation_prompt=True,
                                             enable_thinking=False)
    followed by the model generating messages[k]["content"] + "<|im_end|>".

For every assistant turn k this script asserts

    prompt_k == training_text[: offset of turn k's content] + "<think>\\n\\n</think>\\n\\n"

i.e. the only difference is the empty think block that enable_thinking=False puts in
the generation prompt (the model's history turns never contain it, and SkyRL's RL
re-tokenization drops it too).

Needs `transformers` and the rllm repo on sys.path (run from the repo root).

    python recipe/qwen3_swe_sft/verify_rollout_parity.py data/sft/train.jsonl \\
        --tokenizer /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EMPTY_THINK = "<think>\n\n</think>\n\n"
ASSISTANT_HEADER = "<|im_start|>assistant\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--max-records", type=int, default=None)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from transformers import AutoTokenizer

    from rllm.parser.chat_template_parser import ChatTemplateParser

    tok = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    parser = ChatTemplateParser.get_parser(tok)
    print(f"parser: {type(parser).__name__}")

    n_ok = n_bad = 0
    for i, line in enumerate(open(args.jsonl, encoding="utf-8")):
        if args.max_records is not None and i >= args.max_records:
            break
        msgs = json.loads(line)["messages"]

        # --- training text exactly as RLLMSFTDataset._tokenize_and_mask_cumulative concatenates it
        segs = [parser.parse([m], is_first_msg=(j == 0), add_generation_prompt=False) for j, m in enumerate(msgs)]
        train_text = "".join(segs)
        offsets = []
        pos = 0
        for m, s in zip(msgs, segs):
            if m["role"] == "assistant":
                assert s.startswith(ASSISTANT_HEADER), repr(s[:40])
                offsets.append(pos + len(ASSISTANT_HEADER))
            pos += len(s)

        # --- native full render (what the RL trainer / vLLM would render for the same history)
        native_full = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        # Qwen3 puts an empty think block on the *last* assistant turn only; strip it for comparison.
        last_hdr = native_full.rfind(ASSISTANT_HEADER)
        native_cmp = native_full[: last_hdr + len(ASSISTANT_HEADER)] + native_full[last_hdr + len(ASSISTANT_HEADER) :].replace(EMPTY_THINK, "", 1)
        full_ok = native_cmp == train_text

        # --- per-turn rollout prompt parity
        bad_turns = []
        k_asst = 0
        for j, m in enumerate(msgs):
            if m["role"] != "assistant":
                continue
            prompt = tok.apply_chat_template(msgs[:j], tokenize=False, add_generation_prompt=True, enable_thinking=False)
            expected = train_text[: offsets[k_asst]] + EMPTY_THINK
            if prompt != expected:
                # locate first diff
                d = next((x for x in range(min(len(prompt), len(expected))) if prompt[x] != expected[x]), min(len(prompt), len(expected)))
                bad_turns.append((j, d, prompt[max(0, d - 40) : d + 40], expected[max(0, d - 40) : d + 40]))
            k_asst += 1

        n_tok = len(tok.encode(train_text, add_special_tokens=False))
        status = "OK " if (full_ok and not bad_turns) else "BAD"
        print(f"[{status}] record {i}: assistant turns={k_asst} tokens={n_tok} full-render match={full_ok} rollout-prompt mismatches={len(bad_turns)}")
        for j, d, a, b in bad_turns[:3]:
            print(f"      turn at msg {j}: first diff @{d}\n        rollout : {a!r}\n        training: {b!r}")
        if full_ok and not bad_turns:
            n_ok += 1
        else:
            n_bad += 1
    print(f"\n{n_ok} records identical (modulo the enable_thinking=False empty think block), {n_bad} with differences")
    sys.exit(1 if n_bad else 0)


if __name__ == "__main__":
    main()
