"""Keep a task repository's git history away from the agent until the verifier runs.

SWE task images ship the upstream repository with more than the task's base
commit: branches and tags point past it (SWE-rebench, SWE-Gym, R2E-Gym carry
the upstream fix commit itself), and SWE-smith's bug commit sits directly on
top of the clean code, so ``git show HEAD`` prints the answer. An agent that
runs ``git log --all --grep=<issue>`` can copy the fix instead of writing it.

The verifier still needs that history (``git checkout <base_commit> -- tests``,
``git checkout HEAD~1 -- <tests>``), so the history is moved, not deleted:

* ``hide`` moves ``<workdir>/.git`` out of the sandbox to a host file and
  leaves a fresh repository holding a single commit of the current tree, so
  ``git status`` / ``git diff`` still work for the agent.
* ``restore`` puts the original ``.git`` back just before the verifier,
  leaving the agent's working-tree edits in place.
* ``discard`` removes the host copy; callers run it on teardown so an aborted
  rollout does not leak it.

The host copy never enters the container while the agent runs, which is the
point: the agent is root in its sandbox, so nothing inside it is out of reach.

Two front ends share the shell steps: :class:`GitHistoryVault` for rLLM
sandboxes (native ``rllm eval``, via :class:`rllm.hooks.SandboxTaskHooks`) and
:class:`AsyncGitHistoryVault` for Harbor environments (``--agent harbor:*``,
via Trial hooks in :mod:`rllm.integrations.harbor.trial_helper`).
"""

from __future__ import annotations

import os
import shlex
import tempfile

from rllm.sandbox.protocol import Sandbox

# Fixed identity for the stand-in commit; task images rarely configure one.
_COMMIT_ENV = "GIT_AUTHOR_NAME=rllm GIT_AUTHOR_EMAIL=rllm@localhost GIT_COMMITTER_NAME=rllm GIT_COMMITTER_EMAIL=rllm@localhost"
# Staging path for the Harbor front end, which moves files, not tar streams.
_REMOTE_TAR = "/tmp/rllm-git-history.tar"


def supports_git_history_vault(sandbox: Sandbox) -> bool:
    """Whether ``sandbox`` can move a directory out to the host and back."""
    return callable(getattr(sandbox, "download_archive", None)) and callable(getattr(sandbox, "upload_archive", None))


def _has_repo_cmd(workdir: str) -> str:
    return f"[ -d {shlex.quote(workdir)}/.git ] && echo yes || echo no"


def _stand_in_cmd(workdir: str) -> str:
    # safe.directory: images often own the workdir as another uid than the
    # agent's; without it every git call the agent makes fails.
    return (
        f"set -e; cd {shlex.quote(workdir)}; rm -rf .git; "
        "git config --global --add safe.directory '*' ; "
        "git init -q; git add -A; "
        f"env {_COMMIT_ENV} git commit -q --no-verify --allow-empty -m 'Initial commit'; "
        "echo commits=$(git rev-list --all | wc -l) refs=$(git for-each-ref | wc -l)"
    )


def _check_stand_in(workdir: str, out: str) -> None:
    # What makes this safe to rely on: if anything but the stand-in commit
    # survived, the rollout must not start.
    if "commits=1 refs=1" not in out:
        raise RuntimeError(f"stand-in repository in {workdir} is not a single commit: {out.strip()[-200:]}")


def _host_tar(tmp_dir: str | None) -> str:
    fd, path = tempfile.mkstemp(prefix="rllm-git-", suffix=".tar", dir=tmp_dir)
    os.close(fd)
    return path


def _unlink(path: str | None) -> None:
    if path is None:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


class GitHistoryVault:
    """Move one rLLM sandbox's ``<workdir>/.git`` to the host and back."""

    def __init__(self, sandbox: Sandbox, workdir: str, tmp_dir: str | None = None):
        if not supports_git_history_vault(sandbox):
            raise RuntimeError(f"hiding git history needs a sandbox backend with archive transfer (docker); {type(sandbox).__name__} has none")
        self.sandbox = sandbox
        self.workdir = workdir.rstrip("/") or "/"
        self.tmp_dir = tmp_dir
        self._archive: str | None = None

    def hide(self) -> bool:
        """Swap ``<workdir>/.git`` for a one-commit repository. Returns False when there is no repository."""
        if self.sandbox.exec(_has_repo_cmd(self.workdir), timeout=30, user="root").strip().endswith("no"):
            return False
        path = _host_tar(self.tmp_dir)
        try:
            self.sandbox.download_archive(f"{self.workdir}/.git", path)  # type: ignore[attr-defined]
        except BaseException:
            _unlink(path)
            raise
        self._archive = path
        _check_stand_in(self.workdir, self.sandbox.exec(_stand_in_cmd(self.workdir), timeout=600, user="root"))
        return True

    def restore(self) -> None:
        """Put the original ``.git`` back, dropping the stand-in. No-op when nothing is hidden."""
        if self._archive is None:
            return
        wd = shlex.quote(self.workdir)
        self.sandbox.exec(f"mkdir -p {wd} && rm -rf {wd}/.git", timeout=120, user="root")
        self.sandbox.upload_archive(self._archive, self.workdir)  # type: ignore[attr-defined]
        self.discard()

    def discard(self) -> None:
        """Delete the host copy. Safe to call more than once."""
        _unlink(self._archive)
        self._archive = None


class AsyncGitHistoryVault:
    """Same moves over a Harbor environment (``exec`` / ``download_file`` / ``upload_file``, async).

    ``.git`` is tarred inside the container and only the tar file crosses:
    Harbor's docker ``download_dir`` chowns the source tree to the host user
    first, which would leave the restored history owned by someone else.
    """

    def __init__(self, environment, workdir: str, tmp_dir: str | None = None):
        self.env = environment
        self.workdir = workdir.rstrip("/") or "/"
        self.tmp_dir = tmp_dir
        self._archive: str | None = None

    async def _run(self, command: str, timeout: int) -> str:
        res = await self.env.exec(command, timeout_sec=timeout, user="root")
        if res.return_code != 0:
            raise RuntimeError(f"git history step failed ({res.return_code}): {command[:80]}: {(res.stderr or res.stdout or '').strip()[-300:]}")
        return res.stdout or ""

    async def hide(self) -> bool:
        if (await self._run(_has_repo_cmd(self.workdir), 30)).strip().endswith("no"):
            return False
        wd = shlex.quote(self.workdir)
        await self._run(f"tar -C {wd} -cf {_REMOTE_TAR} .git", 600)
        path = _host_tar(self.tmp_dir)
        try:
            await self.env.download_file(_REMOTE_TAR, path)
        except BaseException:
            _unlink(path)
            raise
        self._archive = path
        # The staging tar holds the full history: gone before the agent starts.
        _check_stand_in(self.workdir, await self._run(f"rm -f {_REMOTE_TAR}; {_stand_in_cmd(self.workdir)}", 600))
        return True

    async def restore(self) -> None:
        if self._archive is None:
            return
        wd = shlex.quote(self.workdir)
        await self.env.upload_file(self._archive, _REMOTE_TAR)
        await self._run(f"mkdir -p {wd} && rm -rf {wd}/.git && tar -C {wd} -xf {_REMOTE_TAR} && rm -f {_REMOTE_TAR}", 600)
        self.discard()

    def discard(self) -> None:
        _unlink(self._archive)
        self._archive = None


class GitHistoryRestoringEvaluator:
    """Evaluator wrapper: restore the hidden history, then grade as usual."""

    def __init__(self, inner, vault: GitHistoryVault):
        self.inner = inner
        self.vault = vault

    def evaluate(self, task, episode):
        self.vault.restore()
        return self.inner.evaluate(task, episode)

    def __getattr__(self, name):
        # Callers read evaluator attributes (e.g. sandbox, script_path); keep
        # the wrapper transparent to them.
        return getattr(self.inner, name)


__all__ = ["AsyncGitHistoryVault", "GitHistoryRestoringEvaluator", "GitHistoryVault", "supports_git_history_vault"]
