import sys
import types
from unittest.mock import MagicMock

from rllm.sandbox.backends.docker import _DOCKER_PIDS_LIMIT, DockerSandbox


def test_container_runs_with_pids_limit(monkeypatch):
    client = MagicMock()
    monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=lambda: client))

    DockerSandbox(name="t", image="img", mem_limit="16384m", nano_cpus=4_000_000_000)

    _, kwargs = client.containers.run.call_args
    assert kwargs["pids_limit"] == _DOCKER_PIDS_LIMIT == 4096
    assert kwargs["mem_limit"] == "16384m"
