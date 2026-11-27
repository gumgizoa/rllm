import os
import sys
import types
from unittest.mock import MagicMock

import pytest

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


def test_relay_lock_opens_a_file_another_user_created(monkeypatch, tmp_path):
    # as left by another account: no write bit for us, and O_CREAT refused (fs.protected_regular)
    lock = tmp_path / "rllm-egress-relay.lock"
    lock.touch()
    monkeypatch.setattr(egress, "_LOCK_PATH", str(lock))
    real_open = os.open

    def guarded(path, flags, *a, **kw):
        if path == str(lock) and flags & (os.O_CREAT | os.O_RDWR | os.O_WRONLY):
            raise PermissionError(13, "Permission denied", path)
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(egress.os, "open", guarded)
    with egress._ProcessLock():
        pass
    with egress._ProcessLock():  # and it was released
        pass


def test_relay_lock_is_not_left_held_when_the_file_cannot_be_opened(monkeypatch, tmp_path):
    monkeypatch.setattr(egress, "_LOCK_PATH", str(tmp_path / "missing-dir" / "x.lock"))
    for _ in range(2):  # the second attempt used to block forever on the thread lock
        with pytest.raises(OSError):
            with egress._ProcessLock():
                pass
    assert egress._thread_lock.acquire(blocking=False)
    egress._thread_lock.release()


def test_relay_lock_file_is_created_readable_by_everyone(monkeypatch, tmp_path):
    lock = tmp_path / "rllm-egress-relay.lock"
    monkeypatch.setattr(egress, "_LOCK_PATH", str(lock))
    old = os.umask(0o077)
    try:
        with egress._ProcessLock():
            pass
    finally:
        os.umask(old)
    assert lock.stat().st_mode & 0o444 == 0o444
