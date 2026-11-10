"""``OPENHANDS_SDK_EXTRA_TOOLS`` adds tools to the runner's agent beyond the three defaults.

A workflow asks for a tool through ``WorkflowSpec.runner_env`` (recipe side); the runner reads
the variable and wires the tool. Only names it knows are accepted, so a typo fails the rollout at
start instead of silently running without the tool.
"""

from __future__ import annotations

import pytest

from rllm.harnesses.tools import openhands_sdk_runner as runner


def test_unset_or_blank_means_no_extra_tools() -> None:
    assert runner._extra_tools_from_env({}) == ()
    assert runner._extra_tools_from_env({"OPENHANDS_SDK_EXTRA_TOOLS": ""}) == ()
    assert runner._extra_tools_from_env({"OPENHANDS_SDK_EXTRA_TOOLS": " , "}) == ()


def test_task_is_known_and_listed_once() -> None:
    assert runner._extra_tools_from_env({"OPENHANDS_SDK_EXTRA_TOOLS": "task"}) == ("task",)
    assert runner._extra_tools_from_env({"OPENHANDS_SDK_EXTRA_TOOLS": " task , task "}) == ("task",)


def test_unknown_tool_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown tool 'delegate'"):
        runner._extra_tools_from_env({"OPENHANDS_SDK_EXTRA_TOOLS": "task,delegate"})


def test_the_runner_registers_sub_agent_types_when_task_is_enabled() -> None:
    # The SDK registers no sub-agent type on its own; the runner has to, or the tool's
    # ``general-purpose`` default would be unknown at the first call.
    source = runner.__file__
    text = open(source, encoding="utf-8").read()
    assert "register_builtins_agents(enable_browser=False)" in text
    assert "Tool(name=TaskToolSet.name)" in text
