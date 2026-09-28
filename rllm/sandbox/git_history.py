"""Keep a task repository's git history away from the agent until the verifier runs.

SWE task images ship the upstream repository with more than the task's base
commit: branches and tags point past it (SWE-rebench, SWE-Gym, R2E-Gym carry
the upstream fix commit itself), and SWE-smith's bug commit sits directly on
top of the clean code, so ``git show HEAD`` prints the answer. An agent that
runs ``git log --all --grep=<issue>`` can copy the fix instead of writing it.

The verifier still needs that history (``git checkout <base_commit> -- tests``,
``git checkout HEAD~1 -- <tests>``), so the history is moved, not deleted:

* :meth:`GitHistoryVault.hide` streams ``<workdir>/.git`` out of the sandbox
  to a host file and leaves a fresh repository holding a single commit of the
  current tree, so ``git status`` / ``git diff`` still work for the agent.
* :meth:`GitHistoryVault.restore` puts the original ``.git`` back just before
  the verifier, leaving the agent's working-tree edits in place.
* :meth:`GitHistoryVault.discard` removes the host copy; the hooks call it on
  teardown so an aborted rollout does not leak it.

The host copy never enters the container while the agent runs, which is the
point: the agent is root in its sandbox, so nothing inside it is out of reach.
"""

from __future__ import annotations

import os
import shlex
import tempfile

from rllm.sandbox.protocol import Sandbox

# Fixed identity for the stand-in commit; task images rarely configure one.
_COMMIT_ENV = "GIT_AUTHOR_NAME=rllm GIT_AUTHOR_EMAIL=rllm@localhost GIT_COMMITTER_NAME=rllm GIT_COMMITTER_EMAIL=rllm@localhost"


def hide_git_history_from_env() -> bool:
    """``RLLM_HIDE_GIT_HISTORY``: the default when no caller decides."""
    return os.environ.get("RLLM_HIDE_GIT_HISTORY", "0").strip().lower() in ("1", "true", "yes", "on")


def supports_git_history_vault(sandbox: Sandbox) -> bool:
    """Whether ``sandbox`` can move a directory out to the host and back."""
    return callable(getattr(sandbox, "download_archive", None)) and callable(getattr(sandbox, "upload_archive", None))


class GitHistoryVault:
    """Move one sandbox's ``<workdir>/.git`` to the host and back."""

    def __init__(self, sandbox: Sandbox, workdir: str, tmp_dir: str | None = None):
        if not supports_git_history_vault(sandbox):
            raise RuntimeError(f"hiding git history needs a sandbox backend with archive transfer (docker); {type(sandbox).__name__} has none")
        self.sandbox = sandbox
        self.workdir = workdir.rstrip("/") or "/"
        self.tmp_dir = tmp_dir
        self._archive: str | None = None

    def hide(self) -> bool:
        """Swap ``<workdir>/.git`` for a one-commit repository. Returns False when there is no repository."""
        wd = shlex.quote(self.workdir)
        present = self.sandbox.exec(f"[ -d {wd}/.git ] && echo yes || echo no", timeout=30, user="root").strip()
        if present.endswith("no"):
            return False

        fd, path = tempfile.mkstemp(prefix="rllm-git-", suffix=".tar", dir=self.tmp_dir)
        os.close(fd)
        try:
            self.sandbox.download_archive(f"{self.workdir}/.git", path)  # type: ignore[attr-defined]
        except BaseException:
            os.unlink(path)
            raise
        self._archive = path

        # safe.directory: images often own /testbed as another uid than the
        # agent's; without it every git call the agent makes fails. The final
        # count check is what makes this safe to rely on: if anything but the
        # stand-in commit survived, the rollout must not start.
        out = self.sandbox.exec(
            f"set -e; cd {wd}; rm -rf .git; "
            "git config --global --add safe.directory '*' ; "
            "git init -q; git add -A; "
            f"env {_COMMIT_ENV} git commit -q --no-verify --allow-empty -m 'Initial commit'; "
            "echo commits=$(git rev-list --all | wc -l) refs=$(git for-each-ref | wc -l)",
            timeout=600,
            user="root",
        )
        if "commits=1 refs=1" not in out:
            raise RuntimeError(f"stand-in repository in {self.workdir} is not a single commit: {out.strip()[-200:]}")
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
        if self._archive is None:
            return
        try:
            os.unlink(self._archive)
        except FileNotFoundError:
            pass
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


__all__ = ["GitHistoryRestoringEvaluator", "GitHistoryVault", "hide_git_history_from_env", "supports_git_history_vault"]
