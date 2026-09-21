"""The training chat template must keep every assistant turn's reasoning.

`Qwen3_5_SFTDataset` supervises a turn only when the conversation up to it plus
`add_generation_prompt=True` is a prefix of the full render, and raises when it
is not. Upstream's template breaks that for every assistant turn before
`ns.last_query_index` by dropping its `<think>` block, so the whole recipe rests
on `qwen3_5_train.jinja` removing that guard.

Rendering here is pure jinja2 - no tokenizer, no model - so this runs anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

sandbox = pytest.importorskip("jinja2.sandbox")

TEMPLATE = Path(__file__).resolve().parents[1] / "qwen3_5" / "chat_templates" / "qwen3_5_train.jinja"

# The single line the training template has where upstream has a conditional.
# Reconstructing the stock behaviour from it keeps the two in lockstep: if the
# training template is ever re-synced and this line moves, the assert below
# fails rather than the test quietly comparing a template to itself.
RETAIN_LINE = "        {{- '<|im_start|>' + message.role + '\\n<think>\\n' + reasoning_content + '\\n</think>\\n\\n' + content }}\n"
STOCK_GUARD = (
    "        {%- if loop.index0 > ns.last_query_index %}\n"
    "            {{- '<|im_start|>' + message.role + '\\n<think>\\n' + reasoning_content + '\\n</think>\\n\\n' + content }}\n"
    "        {%- else %}\n"
    "            {{- '<|im_start|>' + message.role + '\\n' + content }}\n"
    "        {%- endif %}\n"
)


def _render(source: str, messages, tools=None):
    env = sandbox.ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

    def raise_exception(message):
        raise ValueError(message)

    env.globals["raise_exception"] = raise_exception
    return env.from_string(source).render(messages=messages, tools=tools, add_generation_prompt=False)


@pytest.fixture(scope="module")
def templates():
    train = TEMPLATE.read_text()
    assert train.count(RETAIN_LINE) == 1, "the unconditional-reasoning line moved; re-derive STOCK_GUARD"
    return train, train.replace(RETAIN_LINE, STOCK_GUARD)


def turn(reasoning, command):
    return [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": reasoning,
            "tool_calls": [{"id": "c", "type": "function", "function": {"name": "bash", "arguments": {"command": command}}}],
        },
        {"role": "tool", "tool_call_id": "c", "content": json.dumps({"returncode": 0, "output": "ok"})},
    ]


SINGLE_USER = [
    {"role": "system", "content": "You are a helpful assistant that can interact with a computer."},
    {"role": "user", "content": "Please solve this issue: ..."},
    *turn("look around", "ls"),
    *turn("patch it", "sed -i s/a/b/ x.py"),
    {"role": "assistant", "content": "Done.", "reasoning_content": "finished"},
]

# mini-swe-agent injects its format_error_template as a plain user turn when the
# model malforms a tool call. Observed in 2 of 2 native SWE-bench Verified
# episodes, so this is the common shape, not an edge case.
FORMAT_ERROR_RETRY = [
    *SINGLE_USER[:-1],
    {"role": "user", "content": "Tool call error:\n\n<error>\nMissing 'command' argument in bash tool call.\n</error>"},
    {"role": "assistant", "content": "Retrying.", "reasoning_content": "use the command argument"},
]


def test_single_user_turn_renders_the_same_either_way(templates):
    """With one user turn `last_query_index` is that turn, so upstream already
    retains every assistant turn and the override is a no-op."""
    train, stock = templates
    assert _render(train, SINGLE_USER) == _render(stock, SINGLE_USER)


def test_a_second_user_turn_makes_upstream_drop_reasoning(templates):
    """This is the case the override exists for, and agent runs do hit it."""
    train, stock = templates
    n_assistant = sum(1 for m in FORMAT_ERROR_RETRY if m["role"] == "assistant")

    assert _render(train, FORMAT_ERROR_RETRY).count("<think>") == n_assistant
    assert _render(stock, FORMAT_ERROR_RETRY).count("<think>") == 1, "upstream keeps only the turn after the last user query"


def test_every_assistant_turn_is_reachable_by_a_generation_prompt(templates):
    """The invariant Qwen3_5_SFTDataset enforces: the render up to an assistant
    turn must be a prefix of the full render, or that turn cannot be supervised.
    """
    train, _ = templates
    full = _render(train, FORMAT_ERROR_RETRY)
    for i, message in enumerate(FORMAT_ERROR_RETRY):
        if message["role"] != "assistant":
            continue
        prefix = _render(train, FORMAT_ERROR_RETRY[:i])
        assert full.startswith(prefix), f"assistant turn {i} is not reachable, so it could not be supervised"


def test_tools_add_the_call_format_instruction(templates):
    """Why --tools / request_tools matters: the block carries the definition of
    the very syntax the assistant turns are rendered in."""
    train, _ = templates
    tools = [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}]

    with_tools = _render(train, SINGLE_USER, tools=tools)
    without = _render(train, SINGLE_USER)

    assert "<function=bash>" in without, "calls render in the XML form whether or not tools were declared"
    assert "# Tools" not in without
    assert "# Tools" in with_tools and "<function=example_function_name>" in with_tools
