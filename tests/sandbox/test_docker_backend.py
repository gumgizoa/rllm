import sys
import types
from unittest.mock import MagicMock

from rllm.sandbox.backends import egress
from rllm.sandbox.backends.docker import _DOCKER_PIDS_LIMIT, DockerSandbox


def _sandbox(monkeypatch):
    client = MagicMock()
    monkeypatch.setitem(sys.modules, "docker", types.SimpleNamespace(from_env=lambda: client))
    monkeypatch.setattr(egress, "ensure_relay", lambda _client: "172.19.0.2")
    DockerSandbox(name="t", image="img", mem_limit="16384m", nano_cpus=4_000_000_000)
    _, kwargs = client.containers.run.call_args
    return kwargs


def test_container_runs_with_pids_limit(monkeypatch):
    kwargs = _sandbox(monkeypatch)
    assert kwargs["pids_limit"] == _DOCKER_PIDS_LIMIT == 4096
    assert kwargs["mem_limit"] == "16384m"


def test_container_is_isolated_behind_the_relay(monkeypatch):
    kwargs = _sandbox(monkeypatch)
    assert kwargs["network"] == egress.NETWORK
    assert kwargs["extra_hosts"] == {"host.docker.internal": "172.19.0.2"}


def test_network_opens_right_before_grading():
    calls = []

    class Sandbox:
        def open_network(self):
            calls.append("open")

    class Inner:
        script_path = "/tests/test.sh"

        def evaluate(self, task, episode):
            calls.append("grade")
            return "result"

    wrapped = egress.NetworkOpeningEvaluator(Inner(), Sandbox())
    assert calls == []
    assert wrapped.evaluate("task", "episode") == "result"
    assert calls == ["open", "grade"]
    assert wrapped.script_path == "/tests/test.sh"
