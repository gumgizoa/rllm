"""OpenHandsSdkHarness: runs the OpenHands Software Agent SDK inside the sandbox.

openhands-sdk is a library, not a CLI, so this harness ships
``tools/openhands_sdk_runner.py`` into the sandbox and runs it with the SDK's
own interpreter. The SDK talks to the model through litellm, which reads
``LLM_BASE_URL`` / ``LLM_API_KEY`` / ``LLM_MODEL`` -- the same names Harbor's
openhands-sdk scaffold uses.

Two things about the install are not optional. openhands-sdk requires Python
>=3.12 while task images commonly ship 3.8-3.11, and several of them carry a
``pip.conf`` pinning ``index-url`` at a build-time local mirror that no longer
answers. Both are sidestepped by installing through uv, which brings its own
interpreter and ignores pip's configuration files.

``run()`` returns ``None``; the gateway captures every LLM call and the engine
builds the trajectory.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

from rllm.env import env_str
from rllm.harnesses.cli_harness import BaseCliHarness
from rllm.sandbox.agent_image import agent_mount_target
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Task

# openhands-sdk and openhands-tools are released together and must match.
# The agent-image bake recipe in :mod:`rllm.sandbox.agent_image` reads these
# too, so a mounted venv and a per-task install cannot drift apart.
SDK_VERSION = env_str("RLLM_OPENHANDS_SDK_VERSION", "1.42.1")
# Interpreter uv fetches for the SDK venv, independent of the task's python.
PYTHON_VERSION = env_str("RLLM_OPENHANDS_PYTHON_VERSION", "3.12")

_VENV = "/opt/openhands-sdk-venv"
_UV_DIR = "/opt/openhands-sdk-uv"
_RUNNER_PATH = "/opt/openhands-sdk-runner.py"

_RUNNER_SOURCE = Path(__file__).parent / "tools" / "openhands_sdk_runner.py"
# Printed by the install guard so the log says which path a task took.
_FALLBACK_MARKER = "rllm-openhands-sdk-per-task-install"

logger = logging.getLogger(__name__)


def _install_script(mount_venv: str) -> str:
    return rf"""
set -e
export DEBIAN_FRONTEND=noninteractive

# Nothing to do when a baked agent image already carries the venv, or when a
# warm sandbox installed it earlier.
for candidate in {shlex.quote(mount_venv)} {shlex.quote(_VENV)}; do
    if [ -x "$candidate/bin/python" ] && "$candidate/bin/python" -c "import openhands.sdk" 2>/dev/null; then
        exit 0
    fi
done

# curl bootstraps uv. Task images do not all ship it (SWE-bench Pro's
# qutebrowser images have no curl) and they are not all Debian (the teleport
# images are Alpine), so try whichever package manager is present.
if ! command -v curl >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        # Check-Valid-Until off: the bullseye-based images have expired
        # Release metadata and ``apt-get update`` otherwise fails outright.
        apt-get update -qq -o Acquire::Check-Valid-Until=false \
            && apt-get install -y -qq --no-install-recommends curl ca-certificates
    elif command -v apk >/dev/null 2>&1; then
        apk add --no-cache curl ca-certificates
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y curl ca-certificates
    elif command -v yum >/dev/null 2>&1; then
        yum install -y curl ca-certificates
    fi
fi
command -v curl >/dev/null 2>&1 \
    || {{ echo "openhands-sdk install: failed to bootstrap curl in sandbox" >&2; exit 1; }}

# One dropped wheel out of ~180 would otherwise fail the whole task, and a
# 100-task run pulls roughly 50 GB from PyPI.
retry() {{ n=0; until "$@"; do n=$((n+1)); [ "$n" -ge 3 ] && return 1; sleep $((n * 10)); done; }}

# uv lands in its own directory rather than reusing what is on PATH: task
# images bake in their own uv (SWE-bench Pro pins 0.7.13) and the harness
# should not inherit a task image's installer version.
export UV_INSTALL_DIR={shlex.quote(_UV_DIR)} UV_NO_MODIFY_PATH=1 UV_HTTP_TIMEOUT=120
retry curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh
sh /tmp/uv-install.sh
export PATH={shlex.quote(_UV_DIR)}:"$PATH"

retry uv python install {PYTHON_VERSION}
uv venv {shlex.quote(_VENV)} --python {PYTHON_VERSION}
retry uv pip install --python {shlex.quote(_VENV)}/bin/python \
    openhands-sdk=={SDK_VERSION} openhands-tools=={SDK_VERSION}
{shlex.quote(_VENV)}/bin/python -c 'import openhands.sdk; print(openhands.sdk.__version__)'
"""


class OpenHandsSdkHarness(BaseCliHarness):
    """Run the OpenHands Software Agent SDK inside the sandbox."""

    name = "openhands-sdk"
    use_agent_mount = True
    sandbox_backend = "docker"
    stdout_log_path = "/tmp/openhands-sdk.log"

    def install_script(self) -> str:
        return _install_script(f"{agent_mount_target()}/openhands-sdk-venv")

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        # litellm needs ``provider/model``; rllm setup hands out bare names.
        _, _, qualified = self.ensure_provider_prefix(config.model)
        return {
            "LLM_MODEL": qualified,
            "LLM_BASE_URL": config.base_url,
            "LLM_API_KEY": self.gateway_api_key(config, "OPENAI_API_KEY"),
            # The SDK prints a release banner on import; stderr is teed into
            # the same log as the run, so keep it out.
            "OPENHANDS_SUPPRESS_BANNER": "1",
        }

    def write_configs(
        self,
        sandbox: Sandbox,
        task: Task,
        config: AgentConfig,
        env: dict[str, str],
    ) -> None:
        """Ship the runner script, and install the SDK when the mount cannot serve it.

        The runner is written per task rather than baked in: it is a few KB,
        and keeping it next to the harness means the two cannot drift apart.

        The mount does not serve every image: it is built on glibc, so its
        interpreter cannot run on a musl task image (SWE-bench Pro's teleport
        images are Alpine), and a venv's compiled wheels only load on the
        glibc generation they were resolved for. rLLM skips the install hook
        whenever the mount is present (``hooks.py`` records it as
        ``baked_install``), which would leave such a task with no working
        interpreter, so probe by importing the SDK through the mounted python
        and fall back to a per-task install. The install script exits early
        when a usable venv is already there, so the probe costs nothing on
        images the mount does serve.
        """
        self._exec_agent(
            sandbox,
            self._heredoc_write(_RUNNER_PATH, _RUNNER_SOURCE.read_text()),
        )
        probe = f"{shlex.quote(self._mount_python())} -c 'import openhands.sdk' 2>/dev/null"
        out = sandbox.exec(
            f"if ! {probe}; then\n  echo {_FALLBACK_MARKER}\n{self.install_script()}\nfi",
            timeout=self.install_timeout,
            user="root",
        )
        if _FALLBACK_MARKER in (out or ""):
            # Warning, not info: the CLI hides info, and a silent fallback is
            # how a broken mount once looked like a working one. It also means
            # this task ran an install the baked image was supposed to cover.
            logger.warning("%s: agent mount cannot serve %s; installed the SDK per task instead", self.name, task.id)
        else:
            logger.debug("%s: agent mount serves %s; skipped the install", self.name, task.id)

    @staticmethod
    def _mount_python() -> str:
        return f"{agent_mount_target()}/openhands-sdk-venv/bin/python"

    def build_invocation(
        self,
        instruction: str,
        task: Task,
        config: AgentConfig,
    ) -> str:
        # Probe by importing the SDK, not by testing the file or starting the
        # interpreter: on a musl image the mounted python cannot run at all,
        # and on an older-glibc image it starts but its extension modules
        # refuse to load. Both have to land on the per-task install.
        return (
            f"{self._cd_prefix(task)}"
            f"OH_PY={shlex.quote(self._mount_python())}; "
            f"\"$OH_PY\" -c 'import openhands.sdk' 2>/dev/null || OH_PY={shlex.quote(_VENV)}/bin/python; "
            f'"$OH_PY" {shlex.quote(_RUNNER_PATH)} '
            f"--instruction={shlex.quote(instruction)} "
            f"2>&1 | tee {shlex.quote(self.stdout_log_path)}"
        )
