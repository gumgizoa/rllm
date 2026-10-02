"""Unit tests for OpenHandsSdkHarness command construction."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.harnesses.tools import openhands_sdk_runner as runner
from rllm.types import AgentConfig, Task

from .test_cli_harness import FakeSandbox

# An SDK interpreter being run (``-c`` or the runner script) rather than named
# as an argument (``--python .../bin/python``, ``[ -x .../bin/python ]``).
_UNISOLATED_RUN = re.compile(r'(bin/python"?|"\$OH_PY") (?!-I )(-c|/opt/)')

_HARBOR_PATCH = Path(__file__).parents[2] / "recipe/eval/patches/harbor-0.3.0-openhands-sdk.patch"


def _task() -> Task:
    return Task(id="t-1", instruction="fix the bug", metadata={"workdir": "/testbed"})


def _config() -> AgentConfig:
    return AgentConfig(base_url="http://gw:8000/sessions/eval-0/v1", model="Qwen/Qwen3.5-4B", session_uid="eval-0")


def test_every_sdk_interpreter_run_is_isolated_from_the_task_repo():
    # Commands run from the task workdir, where ``python -c`` would import the
    # repo's own packages (/testbed/aiohttp, /testbed/pydantic) ahead of the
    # SDK's dependencies and fail both the mount probe and the fallback install.
    h = OpenHandsSdkHarness()
    sandbox = FakeSandbox()
    h.write_configs(sandbox, _task(), _config(), env={})
    commands = [c.command for c in sandbox.calls]
    commands += [h.install_script(), h.build_invocation("hi", _task(), _config())]

    for cmd in commands:
        assert not _UNISOLATED_RUN.findall(cmd), cmd
        # litellm appends the cwd to sys.path on import, so every import probe
        # leaves the workdir before importing.
        for probe in re.findall(r"-I -c '([^']*)'", cmd):
            assert probe.startswith("import os, tempfile; os.chdir(tempfile.mkdtemp()); import openhands.sdk"), probe
    assert "-I -c 'import os, tempfile; os.chdir(tempfile.mkdtemp()); import openhands.sdk'" in commands[-1]
    assert '"$OH_PY" -I /opt/openhands-sdk-runner.py' in commands[-1]


def test_runner_imports_the_sdk_away_from_the_workspace():
    source = (Path(runner.__file__)).read_text()
    chdir_away = source.index("os.chdir(tempfile.mkdtemp(")
    first_sdk_import = source.index("from openhands.sdk import")
    chdir_back = source.index("os.chdir(workspace)")
    assert source.index("workspace = os.getcwd()") < chdir_away < first_sdk_import < chdir_back


def test_llm_sends_past_reasoning_back():
    # Without it, Qwen3.x / GLM templates render past turns as an empty
    # <think></think> and the model stops thinking a few steps in.
    pytest.importorskip("openhands.sdk")
    from openhands.sdk import LLM, Agent
    from openhands.sdk.llm import Message, TextContent

    history = [
        Message(role="user", content=[TextContent(text="fix the bug")]),
        Message(role="assistant", content=[TextContent(text="looking")], reasoning_content="the bug is in f()"),
    ]
    kwargs = {"model": "openai/Qwen3.5-397B-A17B-FP8", "api_key": "k", "base_url": "http://gw/v1"}

    assert "reasoning_content" not in LLM(**kwargs).format_messages_for_llm(history)[1]  # the SDK default
    llm = runner.reasoning_replay_llm(LLM)(**kwargs)
    sent = llm.format_messages_for_llm(history)
    assert sent[1]["reasoning_content"] == "the bug is in f()"
    assert sent[1]["reasoning"] == "the bug is in f()"  # the field vLLM reads
    assert "reasoning_content" not in sent[0]
    assert "reasoning" not in sent[0]
    assert Agent(llm=llm, tools=[]).llm is llm  # the agent keeps the subclass


def _replay_methods(source: str) -> str:
    start = source.index("def _model_features")
    end = source.index("return dicts", start) + len("return dicts")
    # Back up to the line start so dedent sees the first line's indentation.
    return textwrap.dedent(source[source.rindex("\n", 0, start) + 1 : end])


def test_harbor_patch_replays_reasoning_like_the_native_runner():
    # harbor:openhands-sdk uploads Harbor's own runner, which cannot import
    # rLLM, so the patch carries a copy of the subclass. Keep the two equal.
    added = "\n".join(line[1:] for line in _HARBOR_PATCH.read_text().splitlines() if line.startswith("+") and not line.startswith("+++"))
    assert "llm = ReasoningReplayLLM(**llm_kwargs)" in added
    assert _replay_methods(added) == _replay_methods(Path(runner.__file__).read_text())
