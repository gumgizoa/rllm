"""The episode -> contract conversion, without a GPU, a model or an eval run.

Run with the recipe installed (``pip install -e recipe/sft``), or straight from a
checkout - the fixture below puts the recipe root on ``sys.path`` either way::

    pytest recipe/sft/tests

Nothing here imports ``rllm``: the converter defers that to ``select_attempts``,
so the part that decides what a row *means* stays testable on its own.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

RECIPE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def converter():
    if str(RECIPE_ROOT) not in sys.path:
        sys.path.insert(0, str(RECIPE_ROOT))
    spec = importlib.util.spec_from_file_location("from_rllm_eval", RECIPE_ROOT / "converters" / "from_rllm_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a bash command",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
        },
    }
]


def episode(messages, name="agent"):
    """An episode dict shaped like ``Episode.to_dict()`` writes it to disk."""
    return {
        "id": "task-1:0",
        "trajectories": [{"name": name, "steps": [{"chat_completions": messages}]}],
    }


# --------------------------------------------------------------------------- #
# The wire format (gateway / native): structured tool calls, reasoning in its
# own key, tool results as role="tool".
# --------------------------------------------------------------------------- #

WIRE_MESSAGES = [
    {"role": "system", "content": "You are a SWE agent."},
    {"role": "user", "content": "Fix the failing test."},
    {
        "role": "assistant",
        "content": "Listing the repo.",
        "reasoning": "I should look around first.",
        "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": '{"command": "ls"}'}}],
    },
    {"role": "tool", "tool_call_id": "c1", "content": '{"returncode": 0, "output": "a.py"}'},
    {"role": "assistant", "content": "Done.", "reasoning": "The fix is in a.py."},
]


def test_wire_format_round_trips_into_the_contract(converter):
    sample = converter.build_sample(episode(WIRE_MESSAGES), None, TOOLS, {"instance_id": "task-1"})

    assert [m.role for m in sample.messages] == ["system", "user", "assistant", "tool", "assistant"]
    # arguments must be a mapping, or Qwen templates raise on |items
    assert sample.messages[2].tool_calls[0].function.arguments == {"command": "ls"}
    assert sample.messages[2].reasoning == "I should look around first."
    assert sample.tools == TOOLS
    # every assistant turn has reasoning, so thinking stays on
    assert sample.apply_chat_template_kwargs is None
    assert sample.metadata == {"instance_id": "task-1"}


def test_parquet_row_is_four_json_strings(converter):
    from swe_sft.dataset.utils.serde import parse_row

    sample = converter.build_sample(episode(WIRE_MESSAGES), None, TOOLS, {"instance_id": "task-1"})
    row = sample.to_parquet_row()
    assert set(row) == {"messages", "tools", "apply_chat_template_kwargs", "metadata"}
    assert all(v is None or isinstance(v, str) for v in row.values())
    assert row["apply_chat_template_kwargs"] is None, "absent must be a real null, not '' or 'null'"
    # and it decodes back through the one decode path the trainer uses
    assert parse_row(row).messages[2].tool_calls[0].function.arguments == {"command": "ls"}


# --------------------------------------------------------------------------- #
# Reasoning
# --------------------------------------------------------------------------- #


def test_inline_think_block_moves_into_the_reasoning_field(converter):
    """Without a reasoning parser the engine leaves <think> fused into content.

    The contract forbids control tokens in content, so this has to be split out
    rather than passed through.
    """
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "<think>reasoning here</think>the answer"},
    ]
    sample = converter.build_sample(episode(messages), None, None, {})
    assert sample.messages[1].reasoning == "reasoning here"
    assert sample.messages[1].content == "the answer"


def test_inline_split_takes_the_first_closing_tag(converter):
    assert converter.split_thinking("<think>r</think>answer with </think> in it") == (
        "r",
        "answer with </think> in it",
    )
    assert converter.split_thinking("just an answer") == ("", "just an answer")


def test_missing_reasoning_forces_enable_thinking_false(converter):
    """A turn with no reasoning must say so, or the template's forced </think>
    lands inside the supervised target."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "the answer"},
    ]
    sample = converter.build_sample(episode(messages), None, None, {})
    assert sample.messages[1].reasoning is None
    assert sample.apply_chat_template_kwargs == {"enable_thinking": False}


def test_conflicting_reasoning_is_refused_not_guessed(converter):
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "<think>inline</think>a", "reasoning": "separate"},
    ]
    with pytest.raises(converter.SkipRow, match="both inline and in its own field"):
        converter.build_sample(episode(messages), None, None, {})


# --------------------------------------------------------------------------- #
# The shape that must NOT silently pass
# --------------------------------------------------------------------------- #


def test_flattened_harbor_tool_call_is_refused(converter):
    """The ATIF bridge serializes tool calls into the message text. Such a row is
    contract-valid but would train the literal characters '<tool_call>', which no
    Qwen3.5 template renders."""
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": '<think>r</think>running it\n<tool_call>\n{"name": "bash", "arguments": {"command": "ls"}}\n</tool_call>',
        },
        {"role": "user", "content": "a.py"},
        {"role": "assistant", "content": "<think>r2</think>done"},
    ]
    with pytest.raises(converter.SkipRow, match="flattened <tool_call>"):
        converter.build_sample(episode(messages), None, None, {})


# --------------------------------------------------------------------------- #
# Trajectory shape
# --------------------------------------------------------------------------- #


def test_trailing_tool_messages_are_dropped(converter):
    """Context after the last assistant turn can never be supervised."""
    messages = WIRE_MESSAGES + [{"role": "tool", "tool_call_id": "c2", "content": "late output"}]
    sample = converter.build_sample(episode(messages), None, None, {})
    assert sample.messages[-1].role == "assistant"
    assert len(sample.messages) == len(WIRE_MESSAGES)


def test_named_trajectory_is_selected(converter):
    ep = {
        "id": "t:0",
        "trajectories": [
            {"name": "planner", "steps": [{"chat_completions": [{"role": "user", "content": "plan"}, {"role": "assistant", "content": "p"}]}]},
            {"name": "coder", "steps": [{"chat_completions": [{"role": "user", "content": "code"}, {"role": "assistant", "content": "c"}]}]},
        ],
    }
    assert converter.build_sample(ep, "coder", None, {}).messages[0].content == "code"
    assert converter.build_sample(ep, None, None, {}).messages[0].content == "plan", "default is the first"
    with pytest.raises(converter.SkipRow, match="named trajectory not found"):
        converter.build_sample(ep, "reviewer", None, {})


def test_last_step_with_chat_completions_wins(converter):
    """Steps accumulate the conversation; the last one holds all of it."""
    ep = {
        "id": "t:0",
        "trajectories": [
            {
                "name": "agent",
                "steps": [
                    {"chat_completions": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a1"}]},
                    {"chat_completions": WIRE_MESSAGES},
                    {"chat_completions": None},
                ],
            }
        ],
    }
    assert len(converter.build_sample(ep, None, None, {}).messages) == len(WIRE_MESSAGES)


@pytest.mark.parametrize(
    "messages, match",
    [
        ([{"role": "user", "content": "hi"}], "no assistant turn"),
        ([{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"}], "no user query"),
        ([{"role": "user", "content": "hi"}, {"role": "wizard", "content": "a"}], "unexpected role"),
        (
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": [{"type": "text", "text": "a"}]}],
            "non-string content",
        ),
    ],
)
def test_unusable_conversations_are_skipped(converter, messages, match):
    with pytest.raises(converter.SkipRow, match=match):
        converter.build_sample(episode(messages), None, None, {})


# --------------------------------------------------------------------------- #
# Tool calls
# --------------------------------------------------------------------------- #


def test_unparsable_arguments_are_skipped_not_wrapped(converter):
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "reasoning": "r",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": "{not json"}}],
        },
    ]
    with pytest.raises(converter.SkipRow, match="unparsable tool call arguments"):
        converter.build_sample(episode(messages), None, None, {})


def test_empty_assistant_content_with_a_tool_call_is_valid(converter):
    """A tool-call-only turn is normal for an agent and must survive."""
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "reasoning": "r",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": {"command": "ls"}}}],
        },
    ]
    sample = converter.build_sample(episode(messages), None, TOOLS, {})
    assert sample.messages[1].content == ""
    assert sample.messages[1].tool_calls[0].function.name == "bash"


def test_bare_function_shape_is_accepted(converter):
    """Some engines emit {"name", "arguments"} without the "function" wrapper."""
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "reasoning": "r", "tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}]},
    ]
    sample = converter.build_sample(episode(messages), None, TOOLS, {})
    assert sample.messages[1].tool_calls[0].function.arguments == {"command": "ls"}


def test_load_tools_rejects_a_non_list(converter, tmp_path):
    path = tmp_path / "tools.json"
    path.write_text(json.dumps({"name": "bash"}))
    with pytest.raises(SystemExit, match="must hold a JSON array"):
        converter.load_tools(str(path))
    assert converter.load_tools(None) is None

    path.write_text(json.dumps(TOOLS))
    assert converter.load_tools(str(path)) == TOOLS


# --------------------------------------------------------------------------- #
# Agents that never call tools (upstream mini-swe-agent)
# --------------------------------------------------------------------------- #


def test_markdown_bash_trajectory_converts_with_no_tools(converter):
    """mini-swe-agent asks for a ```bash block and feeds the output back as a user
    turn. There are no tool calls and no schemas - and that is exactly what the
    policy saw, so it is what gets trained."""
    messages = [
        {"role": "system", "content": "Respond with a bash block."},
        {"role": "user", "content": "Fix the test."},
        {"role": "assistant", "content": "```bash\nls\n```", "reasoning": "look first"},
        {"role": "user", "content": "a.py"},
        {"role": "assistant", "content": "```bash\necho done\n```", "reasoning": "finish"},
    ]
    sample = converter.build_sample(episode(messages), None, None, {})
    assert sample.tools is None
    assert not any(m.tool_calls for m in sample.messages)
    assert sample.apply_chat_template_kwargs is None
