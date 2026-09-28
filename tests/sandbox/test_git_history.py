"""GitHistoryVault against a real git repository.

The sandbox runs commands on the host in a temp dir and moves archives with
tarfile, so the test exercises the same shell the docker backend would.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile

import pytest

from rllm.sandbox.git_history import GitHistoryRestoringEvaluator, GitHistoryVault, supports_git_history_vault

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


class HostSandbox:
    """Runs commands on the host; ``HOME`` is isolated so ``git config --global`` stays in the test."""

    def __init__(self, home: str):
        self.env = {**_ENV, "HOME": home}
        self.commands: list[str] = []

    def exec(self, command: str, timeout: float | None = None, user: str | None = None) -> str:
        self.commands.append(command)
        return subprocess.run(["bash", "-c", command], env=self.env, capture_output=True, text=True, check=True, timeout=timeout).stdout

    def download_archive(self, remote_path: str, local_tar_path: str) -> None:
        with tarfile.open(local_tar_path, "w") as tar:
            tar.add(remote_path, arcname=os.path.basename(remote_path))

    def upload_archive(self, local_tar_path: str, remote_parent: str) -> None:
        with tarfile.open(local_tar_path) as tar:
            tar.extractall(remote_parent, filter="tar")


def _git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], env=_ENV, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """Base commit on main, plus a later 'fix' commit reachable only from a branch and a tag."""
    r = tmp_path / "testbed"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "lib.py").write_text("def f():\n    return 1  # bug\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD")
    _git(r, "checkout", "-qb", "upstream")
    (r / "lib.py").write_text("def f():\n    return 2  # fix\n")
    _git(r, "commit", "-qam", "Fix f (#42)")
    _git(r, "tag", "v2")
    _git(r, "checkout", "-q", "main")
    return r, base


def test_agent_sees_one_commit_and_no_fix(tmp_path, repo):
    r, _ = repo
    vault = GitHistoryVault(HostSandbox(str(tmp_path)), str(r), tmp_dir=str(tmp_path))

    assert vault.hide() is True

    assert _git(r, "rev-list", "--all").count("\n") == 0  # exactly one commit
    assert _git(r, "log", "--all", "--oneline", "--grep=#42") == ""
    assert _git(r, "for-each-ref", "--format=%(refname)") == "refs/heads/" + _git(r, "branch", "--show-current")
    assert "return 1" in (r / "lib.py").read_text()
    assert _git(r, "status", "--porcelain") == ""  # the stand-in commit is the current tree


def test_restore_brings_history_back_and_keeps_agent_edits(tmp_path, repo):
    r, base = repo
    vault = GitHistoryVault(HostSandbox(str(tmp_path)), str(r), tmp_dir=str(tmp_path))
    vault.hide()

    (r / "lib.py").write_text("def f():\n    return 2  # agent\n")
    _git(r, "commit", "-qam", "agent work")  # the agent may commit into the stand-in

    vault.restore()

    assert _git(r, "rev-parse", "HEAD") == base
    assert _git(r, "log", "--all", "--oneline", "--grep=#42") != ""
    assert "agent" in (r / "lib.py").read_text()
    assert _git(r, "diff", "--name-only", base) == "lib.py"  # what the verifier diffs against
    assert list(tmp_path.glob("rllm-git-*.tar")) == []  # host copy removed


def test_discard_on_abort_leaves_no_host_copy(tmp_path, repo):
    r, _ = repo
    vault = GitHistoryVault(HostSandbox(str(tmp_path)), str(r), tmp_dir=str(tmp_path))
    vault.hide()
    assert len(list(tmp_path.glob("rllm-git-*.tar"))) == 1

    vault.discard()
    vault.discard()

    assert list(tmp_path.glob("rllm-git-*.tar")) == []
    vault.restore()  # nothing hidden any more: no-op


def test_no_repository_is_not_an_error(tmp_path):
    (tmp_path / "work").mkdir()
    vault = GitHistoryVault(HostSandbox(str(tmp_path)), str(tmp_path / "work"), tmp_dir=str(tmp_path))
    assert vault.hide() is False
    assert list(tmp_path.glob("rllm-git-*.tar")) == []


def test_backend_without_archive_transfer_is_refused(tmp_path):
    class ExecOnly:
        def exec(self, command, timeout=None, user=None):
            return ""

    assert not supports_git_history_vault(ExecOnly())
    with pytest.raises(RuntimeError, match="archive transfer"):
        GitHistoryVault(ExecOnly(), "/testbed")


def test_evaluator_sees_restored_history(tmp_path, repo):
    r, base = repo
    vault = GitHistoryVault(HostSandbox(str(tmp_path)), str(r), tmp_dir=str(tmp_path))
    vault.hide()

    class Inner:
        script_path = "tests/test.sh"

        def evaluate(self, task, episode):
            return _git(r, "rev-parse", "HEAD")

    wrapped = GitHistoryRestoringEvaluator(Inner(), vault)

    assert wrapped.evaluate(None, None) == base
    assert wrapped.script_path == "tests/test.sh"
