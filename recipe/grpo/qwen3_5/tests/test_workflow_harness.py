"""A workflow on a harness: chosen by name, ``None`` for the plain harness, and the compliance
scorer ``rllm eval`` picks up from it.

    pytest recipe/grpo/qwen3_5/tests/test_workflow_harness.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5 import run_artifacts, workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow, StepLimitedOpenHandsSdk, WorkflowMixin  # noqa: E402
from recipe.grpo.qwen3_5.workflows import WorkflowSpec  # noqa: E402
from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness  # noqa: E402
from rllm.types import AgentConfig  # noqa: E402

AIDLC = workflows.WORKFLOWS["aidlc_v4"]
CONFIG = AgentConfig(base_url="http://127.0.0.1:8000/v1", model="m", session_uid="u")
PROMPT_ENV = "OPENHANDS_SDK_SYSTEM_PROMPT_PATH"


class _Sandbox:
    """Records what the workflow side puts in the sandbox; answers the docs count check."""

    def __init__(self, md_count: int = 0):
        self.md_count, self.execs, self.uploads = md_count, [], []

    def exec(self, command, timeout=None, user=None):
        self.execs.append(command)
        return f"{self.md_count}\n" if command.startswith("find ") else ""

    def upload_file(self, local, remote):
        self.uploads.append(remote)

    upload_dir = upload_file


@pytest.fixture
def no_runner(monkeypatch):
    """Skip the SDK runner shipping/probing, so only the workflow side touches the sandbox."""
    monkeypatch.setattr(OpenHandsSdkHarness, "write_configs", lambda *a, **k: None)


@pytest.fixture
def wf2(tmp_path, monkeypatch):
    # The workflows/<name>/ layout: docs/ holds documents only, the instruction sits beside it.
    root = tmp_path / "wf2"
    docs = root / "docs"
    (docs / "rules").mkdir(parents=True)
    (docs / "README.md").write_text("start here")
    (docs / "rules" / "a.md").write_text("rule a")
    (root / "instruction.md").write_text("Follow /wf2/README.md.")
    spec = WorkflowSpec(docs_dir=docs, container_dir="/wf2", entry_doc="README.md", instruction_file=root / "instruction.md")
    monkeypatch.setitem(workflows.WORKFLOWS, "wf2", spec)
    return spec


def test_no_workflow_is_the_plain_harness(no_runner):
    h = OpenHandsSdkWorkflow(instruction_position="prefix")
    assert h.workflow is None and h.workflow_spec is None and h.docs_dir is None
    assert h.compose_instruction("TASK") == "TASK"
    assert h.evaluation_policy is None
    assert PROMPT_ENV not in h.build_env(SimpleNamespace(metadata={}), CONFIG)
    sb = _Sandbox()
    h.write_configs(sb, SimpleNamespace(metadata={}), CONFIG, {})
    # Nothing of a workflow; only the patch-collection marker (run_artifacts.start_command).
    assert sb.uploads == [] and len(sb.execs) == 1 and run_artifacts.MARKER in sb.execs[0]


@pytest.mark.parametrize("spelling", ["none", "null", "", "None"])
def test_cli_null_spellings_switch_the_workflow_off(spelling):
    h = OpenHandsSdkWorkflow(workflow="aidlc_v4")
    h.configure({"agent_kwargs": {"workflow": spelling}})
    assert h.workflow is None and h.workflow_spec is None and h.evaluation_policy is None


def test_aidlc_by_name_injects_and_scores(no_runner):
    h = OpenHandsSdkWorkflow(workflow="aidlc_v4", instruction_position="prefix")
    assert h.docs_dir == AIDLC.docs_dir and h.container_dir == "/ai-dlc"
    assert h.system_prompt_file == AIDLC.system_prompt["openhands-sdk"]
    assert h.compose_instruction("TASK").endswith("\n\nTASK") and "/ai-dlc/core-workflow.md" in h.compose_instruction("TASK")
    assert h.build_env(SimpleNamespace(metadata={}), CONFIG)[PROMPT_ENV] == "/opt/openhands-sdk-system-prompt.j2"
    assert type(h.evaluation_policy).__name__ == "AidlcEvaluation"
    sb = _Sandbox(md_count=h._expected_doc_count())
    h.write_configs(sb, SimpleNamespace(metadata={}), CONFIG, {})
    assert "/ai-dlc/core-workflow.md" in sb.uploads
    assert not any(u.endswith(("instruction.md", "system-prompt.j2")) for u in sb.uploads)  # prompt files stay out
    assert any("/opt/openhands-sdk-system-prompt.j2" in c for c in sb.execs)


def test_switching_workflow_rereads_the_spec(wf2, no_runner):
    h = OpenHandsSdkWorkflow(workflow="aidlc_v4")
    h.configure({"agent_kwargs": {"workflow": "wf2", "instruction_position": "prefix"}})
    assert h.docs_dir == wf2.docs_dir and h.container_dir == "/wf2"
    assert h.compose_instruction("TASK") == "Follow /wf2/README.md.\n\nTASK"
    # No openhands-sdk template and no scorer for wf2: default prompt, resolve rate only.
    assert h.system_prompt_file is None and h.evaluation_policy is None
    sb = _Sandbox(md_count=2)
    h.write_configs(sb, SimpleNamespace(metadata={}), CONFIG, {})
    assert sorted(sb.uploads) == ["/wf2/README.md", "/wf2/rules"]
    assert not any("system-prompt" in c for c in sb.execs)


def test_spec_paths_cannot_be_overridden_per_run():
    h = OpenHandsSdkWorkflow(workflow="aidlc_v4")
    for key in ("docs_dir", "container_dir", "instruction_file", "system_prompt_file"):
        with pytest.raises(AttributeError):
            h.configure({"agent_kwargs": {key: None}})
    with pytest.raises(AttributeError):
        OpenHandsSdkWorkflow(workflow="aidlc_v4", docs_dir=str(AIDLC.docs_dir))


def test_unknown_workflow_rejected():
    with pytest.raises(ValueError, match="unknown workflow 'v9'"):
        OpenHandsSdkWorkflow(workflow="v9")


def test_missing_entry_doc_rejected(wf2):
    (wf2.docs_dir / "README.md").unlink()
    with pytest.raises(FileNotFoundError, match="no README.md"):
        OpenHandsSdkWorkflow(workflow="wf2")


def test_prompt_files_must_point_at_the_uploaded_entry_doc(wf2):
    wf2.instruction_file.write_text("Follow /elsewhere/README.md.")  # stale path
    with pytest.raises(ValueError, match="instruction_file never mentions /wf2/README.md"):
        OpenHandsSdkWorkflow(workflow="wf2")


def test_moved_container_dir_is_caught(monkeypatch):
    # A container_dir that the AI-DLC instruction and system prompt do not name.
    monkeypatch.setitem(workflows.WORKFLOWS, "aidlc_moved", dataclasses.replace(AIDLC, container_dir="/moved"))
    with pytest.raises(ValueError, match="never mentions /moved/core-workflow.md"):
        OpenHandsSdkWorkflow(workflow="aidlc_moved")


def test_harness_without_a_system_prompt_seam():
    class Bare(WorkflowMixin, StepLimitedOpenHandsSdk):
        pass

    with pytest.raises(ValueError, match="cannot replace its system prompt"):
        Bare(workflow="aidlc_v4")


def test_mixin_brings_agent_kwargs_to_any_cli_harness(wf2):
    """No openhands-specific base needed: the mixin alone takes --agent-kwargs on another harness."""
    from rllm.harnesses.mini_swe_agent import MiniSweAgentHarness

    class MiniWorkflow(WorkflowMixin, MiniSweAgentHarness):
        pass

    h = MiniWorkflow()
    h.configure({"agent_kwargs": {"workflow": "wf2", "instruction_position": "prefix"}})
    assert h.workflow_spec is wf2 and h.compose_instruction("TASK") == "Follow /wf2/README.md.\n\nTASK"
    with pytest.raises(ValueError, match="no attribute"):
        h.configure({"agent_kwargs": {"turn_budget": 3}})


def test_rllm_eval_loads_it_by_import_path_and_uses_its_scorer(monkeypatch):
    """The ``rllm eval --agent`` path: package import, CLI kwargs, policy handed to the hooks."""
    monkeypatch.syspath_prepend(str(REPO))
    from rllm.eval.agent_loader import load_agent
    from rllm.eval.runner import _evaluation_policy
    from rllm.hooks import FixedEvaluation

    agent = load_agent("recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow")
    assert _evaluation_policy(agent, None) is None
    agent.configure({"agent_kwargs": {"workflow": "aidlc_v4", "step_limit": 100, "enable_thinking": 0}})
    assert type(_evaluation_policy(agent, None)).__name__ == "AidlcEvaluation"
    explicit = SimpleNamespace(evaluate=lambda task, episode: None)  # --evaluator still wins
    assert isinstance(_evaluation_policy(agent, explicit), FixedEvaluation)
