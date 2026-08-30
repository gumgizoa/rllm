"""Tests for pre-built CLI agent images (Option A mount)."""

from __future__ import annotations

import logging

from rllm.harnesses.aider import AiderHarness
from rllm.harnesses.claude_code import ClaudeCodeHarness
from rllm.harnesses.mini_swe_agent import MiniSweAgentHarness
from rllm.harnesses.opencode import OpenCodeHarness
from rllm.harnesses.oracle import OracleHarness
from rllm.harnesses.react import ReActHarness
from rllm.sandbox.agent_image import (
    SUPPORTED_AGENT_IMAGE_HARNESSES,
    _agent_mount_eligible,
    agent_image_tag,
    agent_path_prefix,
    docker_image_mount,
    flow_uses_agent_mount,
    resolve_agent_mount_image,
)


def test_agent_image_tag_is_stable():
    h = MiniSweAgentHarness()
    t1 = agent_image_tag(h.install_script())
    t2 = agent_image_tag(h.install_script())
    assert t1 == t2
    assert t1.startswith("rllm-agent-")


def test_docker_image_mount_uses_relative_subpath():
    spec = docker_image_mount("rllm-agent-deadbeef")
    assert spec["type"] == "image"
    assert spec["source"] == "rllm-agent-deadbeef"
    assert spec["target"] == "/opt/rllm/agent"
    assert spec["read_only"] is True
    assert spec["ImageOptions"]["Subpath"] == "opt/rllm/agent"


def test_supported_harnesses_eligible_on_docker():
    import os

    os.environ["RLLM_AGENT_IMAGE"] = "auto"
    for cls in (MiniSweAgentHarness, OpenCodeHarness, ClaudeCodeHarness):
        assert flow_uses_agent_mount(cls(), "docker") is True
        assert flow_uses_agent_mount(cls(), "modal") is False


def test_oracle_and_react_silent_skip():
    import os

    os.environ["RLLM_AGENT_IMAGE"] = "auto"
    from rllm.sandbox.agent_image import _WARNED_UNSUPPORTED

    _WARNED_UNSUPPORTED.clear()
    assert resolve_agent_mount_image(OracleHarness(), "docker") is None
    assert resolve_agent_mount_image(ReActHarness(), "docker") is None


def test_unsupported_harness_warns_and_skips():
    import logging
    import os

    os.environ["RLLM_AGENT_IMAGE"] = "auto"
    from rllm.sandbox.agent_image import _WARNED_UNSUPPORTED

    _WARNED_UNSUPPORTED.clear()
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("rllm.sandbox.agent_image")
    handler = _Capture()
    logger.addHandler(handler)
    try:
        assert resolve_agent_mount_image(AiderHarness(), "docker") is None
    finally:
        logger.removeHandler(handler)

    assert any("not implemented" in msg and "aider" in msg for msg in records)


def test_agent_path_prefix_includes_mount_and_fallback():
    mini = agent_path_prefix("mini-swe-agent")
    assert "/opt/rllm/agent/bin" in mini
    assert "$HOME/.local/bin" in mini
    opencode = agent_path_prefix("opencode")
    assert "/opt/rllm/agent/nvm/nvm.sh" in opencode
    claude = agent_path_prefix("claude-code")
    assert "/opt/rllm/agent/home/.local/bin" in claude


def test_supported_set():
    assert SUPPORTED_AGENT_IMAGE_HARNESSES == {"mini-swe-agent", "opencode", "claude-code"}


def test_agent_mount_eligible_respects_skip():
    import os

    os.environ["RLLM_AGENT_IMAGE"] = "skip"
    assert _agent_mount_eligible(MiniSweAgentHarness(), "docker") is False
