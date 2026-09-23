"""The SDK import probes must not see the task's cwd on sys.path.

SWE-Gym's pydantic tasks check the repository out at /testbed/pydantic, and every
probe runs from /testbed. Without PYTHONSAFEPATH ``python -c 'import openhands.sdk'``
resolves ``pydantic`` to the checked-out repo, fails, and a working agent-image mount
is reported as unusable (measured on xingyaoww/sweb.eval.x86_64.pydantic_s_pydantic-8567).
"""

from __future__ import annotations

import re

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.types import AgentConfig, Task

PROBE_RE = re.compile(r"PYTHONSAFEPATH=1 \S+ -c ['\"]import openhands\.sdk")


def _task() -> Task:
    return Task(id="t", instruction="fix it", metadata={"workdir": "/testbed"})


def test_install_script_probes_and_verifies_with_safe_path() -> None:
    script = OpenHandsSdkHarness().install_script()
    # the early-exit guard over both venv candidates, and the final import check
    assert 'PYTHONSAFEPATH=1 "$candidate/bin/python" -c "import openhands.sdk"' in script
    assert re.search(r"PYTHONSAFEPATH=1 /opt/openhands-sdk-venv/bin/python -c 'import openhands\.sdk", script)


def test_invocation_probe_uses_safe_path_and_runner_does_not() -> None:
    harness = OpenHandsSdkHarness()
    cmd = harness.build_invocation("fix it", _task(), AgentConfig(model="m", base_url="http://gw/v1", session_uid="s"))
    assert cmd.startswith("cd /testbed && ")
    assert PROBE_RE.search(cmd), cmd
    # The runner itself is a script and keeps its normal sys.path.
    runner_part = cmd.split("/opt/openhands-sdk-runner.py", 1)[0].rsplit(";", 1)[-1]
    assert "PYTHONSAFEPATH" not in runner_part
