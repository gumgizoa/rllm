"""Unit tests for OpenHandsSdkHarness command construction."""

from __future__ import annotations

import re
from pathlib import Path

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.harnesses.tools import openhands_sdk_runner as runner
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
