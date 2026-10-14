"""Sandbox tooling a workflow can declare (``agent_image_extra``, ``sandbox_files``, ``setup_script``):
its own agent image, uploads and a setup step before the agent, and no change for workflows without it.

    pytest recipe/grpo/qwen3_5/tests/test_workflow_tooling.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import _SETUP_RC, OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows import WorkflowSpec  # noqa: E402
from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness  # noqa: E402
from rllm.sandbox import agent_image  # noqa: E402
from rllm.types import AgentConfig  # noqa: E402

CONFIG = AgentConfig(base_url="http://127.0.0.1:8000/v1", model="m", session_uid="u")
TASK = SimpleNamespace(id="t", metadata={"workdir": "/testbed"})


class _Sandbox:
    """Records execs and uploads; answers the docs count and the setup exit code."""

    def __init__(self, md_count: int, setup_rc: int = 0, setup_out: str = "ok"):
        self.md_count, self.setup_rc, self.setup_out = md_count, setup_rc, setup_out
        self.execs: list[str] = []
        self.uploads: list[tuple[str, str]] = []

    def exec(self, command, timeout=None, user=None):
        self.execs.append(command)
        if command.startswith("find "):
            return f"{self.md_count}\n"
        if _SETUP_RC in command:
            return f"{self.setup_out}\n{_SETUP_RC}{self.setup_rc}\n"
        return ""

    def upload_file(self, local, remote):
        self.uploads.append((local, remote))

    upload_dir = upload_file


@pytest.fixture
def no_runner(monkeypatch):
    monkeypatch.setattr(OpenHandsSdkHarness, "write_configs", lambda *a, **k: None)


@pytest.fixture
def tooled(tmp_path, monkeypatch):
    root = tmp_path / "tooled"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "entry.md").write_text("start")
    (root / "instruction.md").write_text("Open /tooled/entry.md first.")
    (root / "files" / "schemas").mkdir(parents=True)
    (root / "files" / "schemas" / "s.yaml").write_text("name: s")
    (root / "setup.sh").write_text("echo setting up\n")
    spec = WorkflowSpec(
        docs_dir=root / "docs",
        container_dir="/tooled",
        entry_doc="entry.md",
        instruction_file=root / "instruction.md",
        agent_image_extra="RUN echo extra",
        sandbox_files={"/opt/tooled/schemas": root / "files" / "schemas"},
        setup_script=root / "setup.sh",
    )
    monkeypatch.setitem(workflows.WORKFLOWS, "tooled", spec)
    return spec


def test_extra_changes_the_tag_and_empty_keeps_it():
    script = "install things"
    assert agent_image.agent_image_tag(script) == agent_image.agent_image_tag(script, "")
    assert agent_image.agent_image_tag(script, "RUN x") != agent_image.agent_image_tag(script)
    base = agent_image.dockerfile_for_install(script, "openhands-sdk")
    assert agent_image.dockerfile_for_install(script, "openhands-sdk", "") == base
    with_extra = agent_image.dockerfile_for_install(script, "openhands-sdk", "RUN echo extra")
    assert with_extra.startswith(base.rstrip()) and with_extra.rstrip().endswith("RUN echo extra")


def test_resolve_passes_the_flow_extra_to_the_build(monkeypatch, tooled):
    seen = {}
    monkeypatch.setattr(agent_image, "build_agent_image", lambda script, name, **kw: seen.update(kw) or "tag")
    monkeypatch.setattr(agent_image, "agent_image_mode", lambda: "auto")
    assert agent_image.resolve_agent_mount_image(OpenHandsSdkWorkflow(workflow="tooled"), "docker") == "tag"
    assert seen["extra"] == "RUN echo extra"
    assert agent_image.resolve_agent_mount_image(OpenHandsSdkWorkflow(), "docker") == "tag"
    assert seen["extra"] == ""  # no workflow: the plain image


def test_existing_workflows_declare_no_tooling_and_keep_their_fingerprint():
    for name in ("aidlc_v4", "speckit_bug"):
        spec = workflows.WORKFLOWS[name]
        assert not spec.agent_image_extra and not spec.sandbox_files and spec.setup_script is None
        assert OpenHandsSdkWorkflow(workflow=name).agent_image_extra == ""


def test_fingerprint_covers_the_tooling(tooled, tmp_path):
    before = tooled.fingerprint("openhands-sdk")
    (tooled.setup_script).write_text("echo changed\n")
    assert tooled.fingerprint("openhands-sdk") != before
    after_setup = tooled.fingerprint("openhands-sdk")
    (tooled.sandbox_files["/opt/tooled/schemas"] / "s.yaml").write_text("name: t")
    assert tooled.fingerprint("openhands-sdk") != after_setup


def test_uploads_then_setup_then_start_marker(tooled, no_runner):
    h = OpenHandsSdkWorkflow(workflow="tooled", instruction_position="prefix")
    sb = _Sandbox(md_count=1)
    h.write_configs(sb, TASK, CONFIG, {})
    assert ("/opt/tooled/schemas" in [r for _, r in sb.uploads])
    i_setup = next(i for i, c in enumerate(sb.execs) if _SETUP_RC in c)
    i_upload_write = next(i for i, c in enumerate(sb.execs) if "/opt/rllm-workflow-setup.sh" in c and _SETUP_RC not in c)
    assert i_upload_write < i_setup
    assert any("rm -rf /opt/tooled/schemas" in c for c in sb.execs[:i_setup])
    # run_artifacts' start marker is the last write, after setup
    assert i_setup < len(sb.execs) - 1


def test_failed_setup_stops_the_rollout_with_its_output(tooled, no_runner):
    h = OpenHandsSdkWorkflow(workflow="tooled")
    with pytest.raises(RuntimeError, match=r"setup failed \(exit 3\)[\s\S]*no root here"):
        h.write_configs(_Sandbox(md_count=1, setup_rc=3, setup_out="no root here"), TASK, CONFIG, {})


def test_missing_tooling_files_fail_at_construction(tooled, monkeypatch):
    import dataclasses

    bad = dataclasses.replace(tooled, setup_script=tooled.docs_dir / "nope.sh")
    monkeypatch.setitem(workflows.WORKFLOWS, "tooled", bad)
    with pytest.raises(FileNotFoundError, match="setup_script"):
        OpenHandsSdkWorkflow(workflow="tooled")
    rel = dataclasses.replace(tooled, sandbox_files={"relative/path": tooled.docs_dir})
    monkeypatch.setitem(workflows.WORKFLOWS, "tooled", rel)
    with pytest.raises(ValueError, match="absolute"):
        OpenHandsSdkWorkflow(workflow="tooled")
