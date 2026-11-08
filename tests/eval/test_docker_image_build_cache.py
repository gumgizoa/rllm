"""``_build_docker_image`` builds a task image once per process (rllm/eval/_resolution.py).

One rollout resolves its image several times (the warm queue's claim and pop,
``get_sandbox``, the sandbox create). Each call used to rerun ``docker build``,
10-70 s even with every layer cached. ``docker`` is faked here: no daemon needed.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from rllm.eval import _resolution


class _FakeDocker:
    def __init__(self, build_s: float = 0.0) -> None:
        self.builds = 0
        self.images: dict[str, str] = {}
        self.build_s = build_s
        self._lock = threading.Lock()

    def run(self, cmd, cwd=None, capture_output=True, text=True):
        if cmd[:2] == ["docker", "build"]:
            time.sleep(self.build_s)
            with self._lock:
                self.builds += 1
                self.images[cmd[3]] = f"sha256:{self.builds}"
            return _Result(0, "", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            image = self.images.get(cmd[-1])
            return _Result(0, image + "\n", "") if image else _Result(1, "", "No such image")
        raise AssertionError(f"unexpected command {cmd}")


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


@pytest.fixture
def docker(monkeypatch):
    fake = _FakeDocker()
    monkeypatch.setattr("subprocess.run", fake.run)
    monkeypatch.setattr(_resolution, "_built_images", {})
    monkeypatch.setattr(_resolution, "_build_locks", {})
    return fake


@pytest.fixture
def context(tmp_path: Path) -> Path:
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\nRUN echo hi\n")
    (tmp_path / "setup.sh").write_text("true\n")
    return tmp_path


def test_builds_once_per_context(docker, context):
    tags = {_resolution._build_docker_image(context, "swe_feat/Repo__x-1") for _ in range(5)}
    assert tags == {"rllm-task-swe_feat-repo__x-1"}
    assert docker.builds == 1


def test_rebuilds_when_a_context_file_changes(docker, context):
    _resolution._build_docker_image(context, "t")
    dockerfile = context / "Dockerfile"
    dockerfile.write_text("FROM python:3.12\nRUN echo changed\n")
    st = dockerfile.stat()
    os.utime(dockerfile, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    _resolution._build_docker_image(context, "t")
    assert docker.builds == 2


def test_rebuilds_when_the_image_is_gone_or_retagged(docker, context):
    _resolution._build_docker_image(context, "t")
    docker.images.pop("rllm-task-t")  # docker rmi
    _resolution._build_docker_image(context, "t")
    assert docker.builds == 2
    docker.images["rllm-task-t"] = "sha256:other"  # tag moved by someone else
    _resolution._build_docker_image(context, "t")
    assert docker.builds == 3


def test_concurrent_callers_share_one_build(docker, context):
    docker.build_s = 0.2
    threads = [threading.Thread(target=_resolution._build_docker_image, args=(context, "t")) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert docker.builds == 1


def test_failed_build_raises_and_is_not_cached(docker, context, monkeypatch):
    real = docker.run

    def failing(cmd, **kw):
        if cmd[:2] == ["docker", "build"]:
            return _Result(1, "", "boom")
        return real(cmd, **kw)

    monkeypatch.setattr("subprocess.run", failing)
    with pytest.raises(RuntimeError, match="Docker build failed"):
        _resolution._build_docker_image(context, "t")
    monkeypatch.setattr("subprocess.run", real)
    _resolution._build_docker_image(context, "t")
    assert docker.builds == 1
