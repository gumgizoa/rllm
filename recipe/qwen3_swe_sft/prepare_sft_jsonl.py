#!/usr/bin/env python3
"""Convert OpenHands function-calling trajectories into the exact text the
SkyRL-OpenHands rollout (``verl/workers/agentic/codeact.py``) feeds the model.

Input rows (one per line)::

    {"messages": [...], "tools": [...], "instance_id": "...", "n_tokens": 12345}

``messages`` are OpenAI function-calling messages as OpenHands' ``llm_completions``
logs them: ``content`` is a list of ``{"type": "text", "text": ...}`` parts,
assistant turns carry ``tool_calls``, tool turns carry ``tool_call_id``/``name``.

Output rows are what ``rllm sft --train-file out.jsonl`` expects::

    {"messages": [{"role": system|user|assistant, "content": "<str>"}], "instance_id": ...}

How the rollout builds its prompt (OnlineCodeActAgent.step)
------------------------------------------------------------
1. ``LLM.format_messages_for_llm``: model="dummy" -> no native function calling
   -> ``Message._string_serializer``: text parts joined with "\\n".
2. ``convert_fncall_messages_to_non_fncall_messages(messages, get_tools(...))``:
   * system  += SYSTEM_PROMPT_SUFFIX (tool descriptions, <function=...> format rules)
   * first user = IN_CONTEXT_LEARNING_EXAMPLE_PREFIX + text + ..._SUFFIX
   * assistant  = content + "\\n\\n" + "<function=name>\\n<parameter=..>..</parameter>\\n</function>"
   * tool       -> role user, "EXECUTION RESULT of [name]:\\n" + text
3. ``tokenizer.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False)``

This script runs steps 1-2 with the scaffold's *own* code (imported from
``--openhands-root`` with stdlib stubs, so no litellm/browsergym install is
needed) and the scaffold's own ``get_tools()``.  Step 3 is what rLLM's
``cumulative`` tokenizer reproduces at training time (see verify_rollout_parity.py).

The first user message can optionally be rebuilt with SkyRL's
``verl/workers/agentic/utils.get_instruction`` template (``--instruction skyrl``),
because teacher runs may have used a different task instruction.  Pass
``--aidlc-docs-dir`` to append that workflow's ``instruction.md`` exactly as the
rollout does.

Example::

    python recipe/qwen3_swe_sft/prepare_sft_jsonl.py trajectories/*.jsonl \\
        -o data/sft/train.jsonl --instruction skyrl \\
        --tokenizer /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B --max-tokens 65536
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import random
import re
import sys
import types
from collections import Counter
from pathlib import Path

DEFAULT_OPENHANDS_ROOT = "/vast-ib/MMI/home/kyuminkim/project/if/SkyRL/SkyRL-OpenHands"

# --------------------------------------------------------------------------
# SkyRL instruction template.
# Verbatim from SkyRL/verl/workers/agentic/utils.py::get_instruction (the
# f-string body), with the trailing "{_aidlc_instruction()}\n" made optional.
# --------------------------------------------------------------------------
SKYRL_INSTRUCTION_TEMPLATE = """
<uploaded_files>
/workspace/{workspace_dir_name}
</uploaded_files>

I've uploaded a python code repository in the directory {workspace_dir_name}. Consider the following issue description:

<issue_description>
{problem_statement}
</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?
I've already taken care of all changes to any of the test files described in the <issue_description>. This means you DON'T have to modify the testing logic or any of the tests in any way!
Also the development Python environment is already set up for you (i.e., all dependencies already installed), so you don't need to install other packages.
Your task is to make the minimal changes to non-test files in the /workspace/{workspace_dir_name} directory to ensure the <issue_description> is satisfied.
"""
# get_instruction() continues with "\n{_aidlc_instruction()}\n"
SKYRL_AIDLC_TAIL = "\n{aidlc_instruction}\n"

_UPLOADED_RE = re.compile(r"<uploaded_files>\n(.*?)\n</uploaded_files>", re.S)
_ISSUE_RE = re.compile(r"<issue_description>\n(.*?)\n</issue_description>", re.S)


class SkipRecord(Exception):
    """Raised to drop a record with a reason string."""


# --------------------------------------------------------------------------
# Load the scaffold's converter + tool set with stdlib-only stubs
# --------------------------------------------------------------------------


def _stub_module(name: str, **attrs):
    class _Any:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, n):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

    m = types.ModuleType(name)
    m.__getattr__ = lambda n: _Any  # type: ignore[attr-defined]
    # A real spec keeps importlib.util.find_spec() (used by transformers' optional-dependency
    # probes) from raising on these fake modules.
    m.__spec__ = importlib.machinery.ModuleSpec(name, None)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _load_file(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def load_scaffold(openhands_root: str):
    """Return (convert_fn, tools, converter_module) from the SkyRL-OpenHands checkout."""
    root = Path(openhands_root)
    conv_path = root / "openhands/llm/fn_call_converter.py"
    fc_path = root / "openhands/agenthub/codeact_agent/function_calling.py"
    for p in (conv_path, fc_path):
        if not p.is_file():
            sys.exit(f"scaffold file not found: {p} (check --openhands-root)")

    if "openhands" not in sys.modules or not hasattr(sys.modules["openhands"], "__file__"):
        # Only stub when the real package is not importable.
        class FunctionCallConversionError(Exception):
            pass

        class FunctionCallValidationError(Exception):
            pass

        class FunctionCallNotExistsError(Exception):
            pass

        for n in (
            "browsergym", "browsergym.core", "browsergym.core.action",
            "openhands", "openhands.core", "openhands.events", "openhands.events.action",
            "openhands.events.event", "openhands.events.tool",
        ):
            _stub_module(n)
        _stub_module(
            "openhands.core.exceptions",
            FunctionCallConversionError=FunctionCallConversionError,
            FunctionCallValidationError=FunctionCallValidationError,
            FunctionCallNotExistsError=FunctionCallNotExistsError,
        )

        class _HLAS:  # browsergym HighLevelActionSet stand-in (browser tool is not used)
            def __init__(self, *a, **k):
                self.action_set = {}

            def describe(self, *a, **k):
                return ""

        _stub_module("browsergym.core.action.highlevel", HighLevelActionSet=_HLAS)
        _stub_module("litellm", ChatCompletionToolParam=dict, ChatCompletionToolParamFunctionChunk=dict, ModelResponse=object)

    conv = _load_file(str(conv_path), "oh_fn_call_converter")
    fc = _load_file(str(fc_path), "oh_function_calling")
    # Same flags as OnlineCodeActAgent.__init__ in SkyRL codeact.py
    tools = fc.get_tools(codeact_enable_browsing=False, codeact_enable_jupyter=False, codeact_enable_llm_editor=False)
    tools = json.loads(json.dumps(tools))
    return conv.convert_fncall_messages_to_non_fncall_messages, tools, conv


# --------------------------------------------------------------------------
# Step 1: Message._string_serializer semantics
# --------------------------------------------------------------------------


def flatten_content(content, stats: Counter) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text") or "")
            else:
                stats["dropped_non_text_parts"] += 1
        return "\n".join(texts)
    return str(content)


def to_string_messages(raw_msgs: list[dict], stats: Counter) -> list[dict]:
    """Normalize to the dicts OpenHands' string serializer would emit."""
    out = []
    for m in raw_msgs:
        role = m.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            raise SkipRecord(f"unknown_role:{role}")
        d = {"role": role, "content": flatten_content(m.get("content"), stats)}
        if role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                norm = []
                for k, tc in enumerate(tcs):
                    fn = tc.get("function") or {}
                    args = fn.get("arguments", "{}")
                    if not isinstance(args, str):
                        args = json.dumps(args, ensure_ascii=False)
                    norm.append({"id": tc.get("id") or f"call_{k}", "type": "function", "function": {"name": fn.get("name"), "arguments": args}})
                d["tool_calls"] = norm
            if m.get("reasoning_content") or m.get("reasoning"):
                stats["assistant_msgs_with_reasoning_dropped"] += 1
            if not d["content"].strip() and not tcs:
                stats["dropped_empty_assistant_msgs"] += 1
                continue
        elif role == "tool":
            d["tool_call_id"] = m.get("tool_call_id")
            d["name"] = m.get("name") or "function"
        out.append(d)
    return out


# --------------------------------------------------------------------------
# Optional: rebuild the first user message with SkyRL's instruction
# --------------------------------------------------------------------------


def rebuild_instruction(user_text: str, aidlc_instruction: str | None, stats: Counter) -> str:
    m_path = _UPLOADED_RE.search(user_text)
    m_issue = _ISSUE_RE.search(user_text)
    if not (m_path and m_issue):
        raise SkipRecord("instruction_unparseable")
    workspace_dir_name = os.path.basename(m_path.group(1).strip())
    problem_statement = m_issue.group(1)
    text = SKYRL_INSTRUCTION_TEMPLATE.format(workspace_dir_name=workspace_dir_name, problem_statement=problem_statement)
    if aidlc_instruction:
        text += SKYRL_AIDLC_TAIL.format(aidlc_instruction=aidlc_instruction)
    stats["instruction_rebuilt"] += 1
    return text


# --------------------------------------------------------------------------
# Record conversion
# --------------------------------------------------------------------------


def convert_record(rec: dict, *, convert_fn, tools: list[dict], instruction: str, aidlc_instruction: str | None, trim_trailing: bool, stats: Counter) -> dict:
    raw = rec.get("messages")
    if not isinstance(raw, list) or not raw:
        raise SkipRecord("no_messages")

    if rec.get("tools") and rec["tools"] != tools:
        stats["records_with_tools_differing_from_scaffold"] += 1

    msgs = to_string_messages(raw, stats)

    # exactly one tool call per assistant turn (converter raises otherwise)
    for m in msgs:
        if m["role"] == "assistant" and len(m.get("tool_calls", [])) > 1:
            raise SkipRecord("multiple_tool_calls_in_one_turn")

    if instruction == "skyrl":
        idx = next((i for i, m in enumerate(msgs) if m["role"] == "user"), None)
        if idx is None:
            raise SkipRecord("no_user_message")
        msgs[idx]["content"] = rebuild_instruction(msgs[idx]["content"], aidlc_instruction, stats)

    if trim_trailing:
        while msgs and msgs[-1]["role"] != "assistant":
            msgs.pop()
            stats["trimmed_trailing_msgs"] += 1
    if not any(m["role"] == "assistant" for m in msgs):
        raise SkipRecord("no_assistant_turn")

    try:
        converted = convert_fn(msgs, tools)
    except Exception as e:  # FunctionCallConversionError from the scaffold
        raise SkipRecord(f"converter_error:{type(e).__name__}") from e

    # Converter output should be plain role/content with str content.
    for m in converted:
        if not isinstance(m["content"], str):
            m["content"] = flatten_content(m["content"], stats)
    out = [{"role": m["role"], "content": m["content"]} for m in converted]

    # role alternation after conversion: system, user, assistant, user, assistant, ...
    roles = [m["role"] for m in out]
    if roles[0] != "system" or roles[1] != "user":
        raise SkipRecord("bad_role_prefix")
    for a, b in zip(roles[1:], roles[2:]):
        if a == b:
            stats["consecutive_same_role_pairs"] += 1

    row = {"messages": out}
    if rec.get("instance_id") is not None:
        row["instance_id"] = rec["instance_id"]
    return row


# --------------------------------------------------------------------------
# Token counting (exact, optional): the rollout prompt is
# apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False)
# --------------------------------------------------------------------------


def make_token_counter(tokenizer_path: str | None):
    if not tokenizer_path:
        return None
    try:
        from transformers import AutoTokenizer
    except ImportError:
        sys.exit("--tokenizer requires `transformers`")
    tok = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)

    def count(row: dict) -> int:
        text = tok.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=False)
        return len(tok.encode(text, add_special_tokens=False))

    return count


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def iter_jsonl(paths: list[Path]):
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield p, ln, json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"[warn] {p}:{ln}: bad json ({e}); skipped", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path, help="OpenHands trajectory jsonl file(s)")
    ap.add_argument("-o", "--output", required=True, type=Path, help="Output SFT jsonl (train split)")
    ap.add_argument("--openhands-root", default=DEFAULT_OPENHANDS_ROOT, help="SkyRL-OpenHands checkout (converter + tools are imported from here)")
    ap.add_argument("--instruction", choices=["keep", "skyrl"], default="keep", help="keep the teacher's first user message, or rebuild it with SkyRL get_instruction()")
    ap.add_argument("--aidlc-docs-dir", default=None, help="With --instruction skyrl: append <dir>/instruction.md like the rollout does (e.g. SkyRL/examples/sky/aidlc-v4)")
    ap.add_argument("--val-out", type=Path, default=None)
    ap.add_argument("--val-ratio", type=float, default=0.0, help="Fraction of rows for --val-out (split by instance_id)")
    ap.add_argument("--max-tokens", type=int, default=None, help="Drop rows longer than this (needs --tokenizer)")
    ap.add_argument("--tokenizer", default=None, help="HF tokenizer path for exact token counts (e.g. /path/Qwen3-8B)")
    ap.add_argument("--no-trim-trailing", action="store_true", help="Keep trailing user/tool messages after the last assistant turn")
    ap.add_argument("--dedup", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    # Import transformers before the scaffold stubs land in sys.modules.
    counter = make_token_counter(args.tokenizer)
    convert_fn, tools, _conv = load_scaffold(args.openhands_root)
    aidlc_instruction = None
    if args.aidlc_docs_dir:
        p = Path(args.aidlc_docs_dir) / "instruction.md"
        if not p.is_file():
            sys.exit(f"instruction.md not found under {args.aidlc_docs_dir}")
        aidlc_instruction = p.read_text(encoding="utf-8").strip()  # utils._aidlc_instruction() strips
        if args.instruction != "skyrl":
            sys.exit("--aidlc-docs-dir requires --instruction skyrl")

    stats: Counter = Counter()
    skip_reasons: Counter = Counter()
    token_lens: list[int] = []
    rows: list[dict] = []
    seen: set[str] = set()

    for _path, _ln, rec in iter_jsonl(args.inputs):
        stats["records_in"] += 1
        try:
            row = convert_record(rec, convert_fn=convert_fn, tools=tools, instruction=args.instruction, aidlc_instruction=aidlc_instruction, trim_trailing=not args.no_trim_trailing, stats=stats)
        except SkipRecord as e:
            skip_reasons[str(e)] += 1
            continue
        if counter:
            n = counter(row)
            row["n_tokens"] = n
            token_lens.append(n)
            if args.max_tokens is not None and n > args.max_tokens:
                skip_reasons[f"over_max_tokens({args.max_tokens})"] += 1
                continue
        elif args.max_tokens is not None:
            sys.exit("--max-tokens requires --tokenizer (the input n_tokens field is from another tokenizer/format)")
        if args.dedup:
            h = hashlib.sha1(json.dumps(row["messages"], ensure_ascii=False).encode()).hexdigest()
            if h in seen:
                skip_reasons["duplicate"] += 1
                continue
            seen.add(h)
        rows.append(row)

    train, val = rows, []
    if args.val_out and args.val_ratio > 0 and rows:
        rng = random.Random(args.seed)
        keyed = sorted(rows, key=lambda r: str(r.get("instance_id", "")))
        rng.shuffle(keyed)
        n_val = max(1, int(round(len(keyed) * args.val_ratio)))
        val, train = keyed[:n_val], keyed[n_val:]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if args.val_out and val:
        args.val_out.parent.mkdir(parents=True, exist_ok=True)
        with args.val_out.open("w", encoding="utf-8") as f:
            for r in val:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"scaffold tools        : {[t['function']['name'] for t in tools]}  (from {args.openhands_root})")
    print(f"instruction           : {args.instruction}" + (f" + aidlc {args.aidlc_docs_dir}" if aidlc_instruction else ""))
    print(f"records in            : {stats['records_in']}")
    print(f"rows written (train)  : {len(train)} -> {args.output}")
    if args.val_out:
        print(f"rows written (val)    : {len(val)} -> {args.val_out}")
    if skip_reasons:
        print("skipped               :")
        for k, v in skip_reasons.most_common():
            print(f"  {k}: {v}")
    for k in sorted(stats):
        if k != "records_in":
            print(f"{k:<40}: {stats[k]}")
    if token_lens:
        token_lens.sort()
        q = lambda p: token_lens[min(len(token_lens) - 1, int(p * len(token_lens)))]  # noqa: E731
        print(f"rendered length (tokens): min={token_lens[0]} p50={q(0.5)} p90={q(0.9)} max={token_lens[-1]}")
    print(f"assistant turns (train): {sum(1 for r in train for m in r['messages'] if m['role'] == 'assistant')}")


if __name__ == "__main__":
    main()
