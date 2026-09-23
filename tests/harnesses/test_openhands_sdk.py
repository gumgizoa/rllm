"""Unit tests for OpenHandsSdkHarness command construction."""

from __future__ import annotations

import re

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.types import AgentConfig, Task

from .test_cli_harness import FakeSandbox

# An SDK interpreter being run (``-c`` or the runner script) rather than named
# as an argument (``--python .../bin/python``, ``[ -x .../bin/python ]``).
_UNISOLATED_RUN = re.compile(r'(bin/python"?|"\$OH_PY") (?!-I )(-c|/opt/)')


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
    assert "-I -c 'import openhands.sdk'" in commands[-1]
    assert '"$OH_PY" -I /opt/openhands-sdk-runner.py' in commands[-1]
