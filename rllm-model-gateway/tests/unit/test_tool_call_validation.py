"""tool_call_validation: what counts as a malformed tool call, and what drop/log do with it.

Blocks are the shapes seen in the Qwen3.5-9B GRPO runs (20261019_050357,
20261108_171417) and in raw re-generations from the step-19 checkpoint.
"""

from __future__ import annotations

import json
import os
import re

import pytest
from rllm_model_gateway import tool_call_validation as tcv
from rllm_model_gateway.models import GatewayConfig
from rllm_model_gateway.server import create_app

base = pytest.importorskip("renderers.base")

# openhands-sdk 1.42.1's tool schemas, trimmed to what validation reads.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}, "command": {"type": "string"}, "is_input": {"type": "boolean"}, "timeout": {"type": "number"}, "reset": {"type": "boolean"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_editor",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "command": {"type": "string", "enum": ["view", "create", "str_replace", "insert", "undo_edit"]},
                    "path": {"type": "string"},
                    "file_text": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                    "insert_line": {"type": "integer"},
                    "view_range": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["command", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_tracker",
            "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "command": {"type": "string", "enum": ["view", "plan"]}, "task_list": {"type": "array"}}},
        },
    },
    {
        "type": "function",
        "function": {"name": "finish", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "message": {"type": "string"}}, "required": ["message"]}},
    },
]
INDEX = tcv.tool_index(TOOLS)

_PARAM_RE = re.compile(r"<parameter=([^>]+)>\n?(.*?)\n?</parameter>", re.DOTALL)


def parse_block(block: str) -> base.ParsedToolCall:
    """What renderers' Qwen3.5/3.6 parser makes of one block (name: first <function=...>)."""
    m = re.search(r"<function=([^>]+)>", block)
    if not m:
        return base.ParsedToolCall(raw=block, status=base.ToolCallParseStatus.MALFORMED_STRUCTURE)
    args = {pm.group(1): pm.group(2).strip() for pm in _PARAM_RE.finditer(block)}
    return base.ParsedToolCall(raw=block, name=m.group(1), arguments=args, status=base.ToolCallParseStatus.INVALID_JSON)


def codes(block: str) -> list[str]:
    return sorted({v.code for v in tcv.check_parsed_call(parse_block(block), INDEX)})


def blk(name: str, *params: tuple[str, str], close: bool = True) -> str:
    body = "".join(f"<parameter={k}>\n{v}\n</parameter>\n" for k, v in params)
    return f"\n<function={name}>\n{body}{'</function>' if close else ''}\n"


VALID = {
    "command+summary": blk("terminal", ("command", "ls -la"), ("summary", "List files")),
    "command only": blk("terminal", ("command", "cd /testbed && grep -rn foo .")),
    "summary first": blk("terminal", ("summary", "List files"), ("command", "ls")),
    "no newlines": "<function=terminal><parameter=command>ls</parameter></function>",
    "security_risk": blk("terminal", ("command", "ls"), ("security_risk", "LOW")),
    "str_replace": blk("file_editor", ("command", "str_replace"), ("path", "/testbed/a.py"), ("old_str", "x = 1"), ("new_str", "x = 2")),
    "file text mentions tags inline": blk("file_editor", ("command", "create"), ("path", "/tmp/a.md"), ("file_text", "Use <parameter=command> and <function=terminal> tags.")),
    "file text with html": blk("file_editor", ("command", "create"), ("path", "/tmp/a.html"), ("file_text", "<div>\n<p>hi</p>\n</div>")),
    "task_tracker no args": "\n<function=task_tracker>\n</function>\n",
    "finish": blk("finish", ("message", "Fixed the bug; tests pass.")),
    "multiline command": blk("terminal", ("command", "python - <<'EOF'\nprint(1)\nEOF")),
}

INVALID = {
    # The floor run's collapse: parameter tag written as a function tag.
    "function tag for parameter": ("\n<function=terminal>\n<function=command>\ngrep -n X a.py\n</parameter>\n<parameter=summary>\nFind X\n</parameter>\n</function>\n", ["A1", "S2"]),
    "function> variant": ("\n<function=terminal>\n<function>command>\nls\n</parameter>\n</function>\n", ["A1", "S2"]),
    "summary only": (blk("terminal", ("summary", "Quick simple test")), ["A1"]),
    "no arguments": ("\n<function=terminal>\n</function>\n", ["A1"]),
    "finish without message": (blk("finish", ("summary", "Fix the bug")), ["A1"]),
    "finish empty": ("\n<function=finish>\n</function>\n", ["A1"]),
    "last parameter unclosed": ("\n<function=terminal>\n<parameter=summary>\nList\n</parameter>\n<parameter=command>\nls -la\n</function>\n", ["A1", "S3"]),
    "only parameter unclosed": ("\n<function=terminal>\n<parameter=command>\nls -la\n</function>\n", ["A1", "S3"]),
    "first parameter unclosed": ("\n<function=terminal>\n<parameter=command>\nls -la\n<parameter=summary>\nList\n</parameter>\n</function>\n", ["S3"]),
    "missing </function>": (blk("terminal", ("command", "ls"), close=False), ["S3"]),
    "text between parameters": ("\n<function=terminal>\n<parameter=command>\nls\n</parameter>\nand then\n</function>\n", ["S3"]),
    "duplicate parameter": (blk("terminal", ("command", "ls"), ("command", "pwd")), ["S4"]),
    "spliced name": ("\n<function=terminal=command>\n</function>\n", ["N1"]),
    # The renderer's name pattern runs across the newline, so the name itself is the fault.
    "spliced name with xml": ("\n<function=term\n</parameter>\n</function>\n", ["N1"]),
    "undeclared tool": (blk("str_replace", ("path", "/a.py"), ("old_str", "x"), ("new_str", "y")), ["N2"]),
    "undeclared argument": (blk("terminal", ("command", "ls"), ("path", "/testbed")), ["A2"]),
    "enum violation": (blk("file_editor", ("command", "str_replace>\n# Implement tasks"), ("path", "/a.py")), ["A3"]),
    "file_editor missing path": (blk("file_editor", ("command", "view")), ["A1"]),
    "tag line inside a value": (blk("file_editor", ("command", "create"), ("path", "/a.md"), ("file_text", "intro\n<parameter=command>\nrest")), ["S3"]),
}


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_calls_pass(name):
    assert codes(VALID[name]) == []


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_calls_are_caught(name):
    block, expected = INVALID[name]
    assert codes(block) == expected


@pytest.mark.parametrize("status", ["UNCLOSED_BLOCK", "MALFORMED_STRUCTURE", "MISSING_NAME"])
def test_unparseable_blocks(status):
    tc = base.ParsedToolCall(raw="<function=terminal", name=None, arguments=None, status=base.ToolCallParseStatus[status])
    assert [v.code for v in tcv.check_parsed_call(tc, INDEX)] == ["S1"]


def test_without_tools_only_name_shape_is_checked():
    tc = parse_block(blk("str_replace", ("path", "/a.py")))
    assert tcv.check_parsed_call(tc, None) == []
    tc = parse_block("\n<function=terminal=command>\n</function>\n")
    assert [v.code for v in tcv.check_parsed_call(tc, None)] == ["N1"]


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        ({"function": {"name": "terminal", "arguments": '{"command": "ls"}'}}, []),
        ({"function": {"name": "terminal", "arguments": '{"summary": "x"}'}}, ["A1"]),
        ({"function": {"name": "terminal", "arguments": ""}}, ["A1"]),
        ({"function": {"name": "terminal=command", "arguments": "{}"}}, ["N1"]),
        ({"function": {"name": "str_replace", "arguments": "{}"}}, ["N2"]),
        ({"function": {"name": "terminal", "arguments": '{"command": ls'}}, ["S1"]),
        ({"function": {"name": "file_editor", "arguments": '{"command": "open", "path": "/a"}'}}, ["A3"]),
        ({"function": {"name": "task_tracker", "arguments": "{}"}}, []),
    ],
)
def test_chat_tool_calls(call, expected):
    assert sorted({v.code for v in tcv.check_chat_tool_call(call, INDEX)}) == expected


# ---------------------------------------------------------------------------
# Real tokenizer: the renderer parses the same text the checks above assume.
# ---------------------------------------------------------------------------

_TOKENIZER = os.environ.get("RLLM_TEST_QWEN35_TOKENIZER")


@pytest.mark.skipif(not _TOKENIZER, reason="set RLLM_TEST_QWEN35_TOKENIZER to a Qwen3.5/3.6 checkpoint dir")
@pytest.mark.parametrize("name", sorted(VALID) + sorted(INVALID))
def test_real_renderer_parse_agrees(name):
    transformers = pytest.importorskip("transformers")
    from renderers.parsing import _parse_xml_tool_calls

    tok = transformers.AutoTokenizer.from_pretrained(_TOKENIZER)
    block, expected = (VALID[name], []) if name in VALID else INVALID[name]
    ids = tok.encode(f"<tool_call>{block}</tool_call>", add_special_tokens=False)
    tc_id = tok.convert_tokens_to_ids("<tool_call>")
    tc_end = tok.convert_tokens_to_ids("</tool_call>")
    specs = [{"name": t["function"]["name"], "parameters": t["function"]["parameters"]} for t in TOOLS]
    from renderers.parsing import _build_param_type_index

    (tc,) = _parse_xml_tool_calls(tok, ids, tc_id, tc_end, section_offset=0, param_index=_build_param_type_index(specs))
    assert sorted({v.code for v in tcv.check_parsed_call(tc, INDEX)}) == expected


# ---------------------------------------------------------------------------
# Proxy: drop / log on cumulative turns and on the chat path
# ---------------------------------------------------------------------------


def _proxy(mode, parsed_calls=None):
    app = create_app(GatewayConfig(store_worker="memory", health_check_interval=999, tool_call_validation=mode))
    proxy = app.state.proxy
    if parsed_calls is not None:

        class _ParsingRenderer:
            def parse_response(self, token_ids, *, tools=None):
                return base.ParsedResponse(content="", tool_calls=parsed_calls)

        proxy.renderer = _ParsingRenderer()
    return proxy


GOOD = VALID["command+summary"]
BAD = INVALID["function tag for parameter"][0]


def test_drop_forwards_a_clean_turn():
    meta: dict = {}
    msg = _proxy("drop", [parse_block(GOOD), parse_block(VALID["str_replace"])])._completion_to_chat_message("RAW", [1], TOOLS, meta_out=meta)
    assert [tc["function"]["name"] for tc in msg["tool_calls"]] == ["terminal", "file_editor"]
    assert meta == {}


def test_drop_turns_a_mixed_turn_into_text():
    meta: dict = {}
    msg = _proxy("drop", [parse_block(GOOD), parse_block(BAD)])._completion_to_chat_message("RAW", [1], TOOLS, meta_out=meta)
    assert "tool_calls" not in msg
    assert msg["content"] == "RAW"
    v = meta["tool_call_violation"]
    assert v["action"] == "dropped" and v["codes"] == ["A1", "S2"] and v["n_calls"] == 2


def test_drop_keeps_non_blank_content_from_the_parse():
    class _R:
        def parse_response(self, token_ids, *, tools=None):
            return base.ParsedResponse(content="Let me check.", tool_calls=[parse_block(BAD)])

    proxy = _proxy("drop")
    proxy.renderer = _R()
    msg = proxy._completion_to_chat_message("RAW", [1], TOOLS, meta_out={})
    assert "tool_calls" not in msg and msg["content"] == "Let me check."


def test_log_records_but_forwards_as_before():
    meta: dict = {}
    msg = _proxy("log", [parse_block(BAD)])._completion_to_chat_message("RAW", [1], TOOLS, meta_out=meta)
    assert [tc["function"]["name"] for tc in msg["tool_calls"]] == ["terminal"]
    assert meta["tool_call_violation"]["action"] == "logged"


def test_off_records_nothing():
    meta: dict = {}
    _proxy("off", [parse_block(BAD)])._completion_to_chat_message("RAW", [1], TOOLS, meta_out=meta)
    assert meta == {}


def test_renderer_failure_with_a_tool_call_is_recorded():
    class _Broken:
        def parse_response(self, token_ids, *, tools=None):
            raise RuntimeError("boom")

    proxy = _proxy("drop")
    proxy.renderer = _Broken()
    meta: dict = {}
    msg = proxy._completion_to_chat_message("<tool_call>x</tool_call>", [1], TOOLS, meta_out=meta)
    assert msg == {"role": "assistant", "content": "<tool_call>x</tool_call>"}
    assert meta["tool_call_violation"]["codes"] == ["S1"]


def _chat_response(tool_calls, content=None):
    return {"choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}]}


def test_chat_path_drop_rewrites_the_turn():
    proxy = _proxy("drop")
    resp = _chat_response([{"id": "a", "type": "function", "function": {"name": "terminal", "arguments": '{"summary": "x"}'}}])
    meta = proxy._validate_chat_response({"tools": TOOLS}, resp)
    choice = resp["choices"][0]
    assert "tool_calls" not in choice["message"]
    assert choice["message"]["content"].strip()
    assert choice["finish_reason"] == "stop"
    assert meta["tool_call_violation"]["turn"] == "chat" and meta["tool_call_violation"]["codes"] == ["A1"]


def test_chat_path_raw_structure_via_renderer():
    """vLLM's parse looks fine; the raw block (re-parsed from token ids) does not."""
    proxy = _proxy("drop", [parse_block(INVALID["missing </function>"][0])])
    resp = _chat_response([{"id": "a", "type": "function", "function": {"name": "terminal", "arguments": '{"command": "ls"}'}}])
    resp["choices"][0]["token_ids"] = [1, 2, 3]
    meta = proxy._validate_chat_response({"tools": TOOLS}, resp)
    assert meta["tool_call_violation"]["codes"] == ["S3"]
    assert "tool_calls" not in resp["choices"][0]["message"]
    assert "<tool_call>" in resp["choices"][0]["message"]["content"]


def test_chat_path_clean_turn_untouched():
    proxy = _proxy("drop")
    resp = _chat_response([{"id": "a", "type": "function", "function": {"name": "terminal", "arguments": '{"command": "ls"}'}}])
    before = json.dumps(resp, sort_keys=True)
    assert proxy._validate_chat_response({"tools": TOOLS}, resp) is None
    assert json.dumps(resp, sort_keys=True) == before


def test_validation_marker():
    assert _proxy("off")._validation_marker() is None
    assert _proxy("drop")._validation_marker() == {"tool_call_validation": "drop"}


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        GatewayConfig(store_worker="memory", tool_call_validation="strict")
