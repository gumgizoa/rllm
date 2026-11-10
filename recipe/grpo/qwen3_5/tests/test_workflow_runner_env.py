"""``WorkflowSpec.runner_env``: a workflow's extra environment for the harness runner.

The variables reach ``build_env`` (so the sandboxed agent process sees them), are part of the
workflow fingerprint, and are absent for workflows that declare none.
"""

from __future__ import annotations

import dataclasses

import pytest

from recipe.grpo.qwen3_5 import workflows
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow
from recipe.grpo.qwen3_5.workflows.spec import WorkflowSpec
from rllm.types import AgentConfig, Task


@pytest.fixture
def with_task_tool(tmp_path, monkeypatch):
    root = tmp_path / "subagents"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "entry.md").write_text("start")
    (root / "instruction.md").write_text("Open /subagents/entry.md first.")
    spec = WorkflowSpec(
        docs_dir=root / "docs",
        container_dir="/subagents",
        entry_doc="entry.md",
        instruction_file=root / "instruction.md",
        runner_env={"OPENHANDS_SDK_EXTRA_TOOLS": "task"},
    )
    monkeypatch.setitem(workflows.WORKFLOWS, "subagents", spec)
    return spec


def _config() -> AgentConfig:
    return AgentConfig(model="m", base_url="http://gw/v1", session_uid="s")


def test_runner_env_reaches_the_agent_environment(with_task_tool):
    env = OpenHandsSdkWorkflow(workflow="subagents").build_env(Task(id="t", instruction="fix", metadata={"workdir": "/testbed"}), _config())
    assert env["OPENHANDS_SDK_EXTRA_TOOLS"] == "task"
    plain = OpenHandsSdkWorkflow().build_env(Task(id="t", instruction="fix", metadata={"workdir": "/testbed"}), _config())
    assert "OPENHANDS_SDK_EXTRA_TOOLS" not in plain


def test_runner_env_is_in_the_fingerprint_and_empty_keeps_it(with_task_tool):
    with_env = with_task_tool.fingerprint("openhands-sdk")
    without = dataclasses.replace(with_task_tool, runner_env={}).fingerprint("openhands-sdk")
    other = dataclasses.replace(with_task_tool, runner_env={"OPENHANDS_SDK_EXTRA_TOOLS": "task,other"}).fingerprint("openhands-sdk")
    assert len({with_env, without, other}) == 3


def test_existing_workflows_declare_no_runner_env():
    for name in ("aidlc_v4", "speckit_bug", "openspec_ff", "agentos_v2", "speckit_sdd", "aidlc_v4_ifeval"):
        assert not workflows.WORKFLOWS[name].runner_env, name
