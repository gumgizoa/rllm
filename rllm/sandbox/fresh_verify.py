"""Grade the agent's *patch* in a fresh sandbox, not the sandbox it worked in.

The agent is root in its sandbox, so anything the verifier relies on there --
the installed test runner, ``site-packages`` / ``node_modules``, binaries on
``PATH``, background processes, the reward files -- is the agent's to change.
SWE-bench avoids this by grading a patch: take the diff of the repository,
apply it to a clean container built from the task image, run the tests there.
:class:`FreshSandboxEvaluator` does the same for ``sandbox-shell`` verifiers.

What carries over is ``git diff --binary`` between two snapshots of the
workdir taken with ``git add -A`` into a scratch index: one before the agent
starts (:meth:`FreshSandboxEvaluator.snapshot`), one at grading time.
``.gitignore`` is respected, so installed dependencies and build output do
not carry over, nor do new test files the agent wrote (grading uses only the
hidden test patch; gold-patch paths excepted) or new files over
``RLLM_FRESH_VERIFY_MAX_FILE_MB``.
Everything outside the workdir is discarded. Wrap order matters: this sits
*inside* :class:`~rllm.sandbox.git_history.GitHistoryRestoringEvaluator`, so
the original ``.git`` (whose config the agent never touched) is back before
the diff is taken.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import tempfile
from pathlib import Path

from rllm.eval.types import EvalOutput

logger = logging.getLogger(__name__)

_STAGE = "/tmp/rllm-agent-patch"
# Git as the grader runs it: no global/system config (the agent owns
# ~/.gitconfig), no hooks, no external diff or textconv drivers.
_GIT = "env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -c safe.directory='*'"


def _snapshot_cmd(workdir: str) -> str:
    """Record the workdir as a git tree *before* the agent starts; print its id.

    Task images are not clean checkouts of HEAD: their build steps create and
    modify files (dependency installs, lockfile rewrites, mode changes). A
    diff against HEAD would carry those too and then fail to apply on a fresh
    container that already has them. The snapshot's objects go into ``.git``,
    which ``--hide-git-history`` moves out of the agent's reach.
    """
    wd = shlex.quote(workdir)
    return f"""
set -eu
cd {wd}
export GIT_INDEX_FILE=/tmp/rllm-base-index
rm -f "$GIT_INDEX_FILE"
# Seeded from the repo's own index: its stat data lets `add -A` skip
# re-hashing unchanged files, which dominates the cost on large trees.
cp "$(env -u GIT_INDEX_FILE {_GIT} rev-parse --git-path index)" "$GIT_INDEX_FILE" 2>/dev/null || true
{_GIT} add -A . >/dev/null
{_GIT} write-tree
rm -f "$GIT_INDEX_FILE"
"""


def _extract_cmd(workdir: str, base_tree: str, max_file_mb: int, keep: list[str] = ()) -> str:
    wd = shlex.quote(workdir)
    base = shlex.quote(base_tree)
    keep_arr = " ".join(shlex.quote(k) for k in keep)
    return f"""
set -u
rm -rf {_STAGE} && mkdir -p {_STAGE} || exit 3
cd {wd} || exit 2
# A throwaway index: the repo's own index is left as the agent had it.
export GIT_INDEX_FILE={_STAGE}/index
# Seeded from the restored repo index (stat cache), as in the snapshot.
cp "$(env -u GIT_INDEX_FILE {_GIT} rev-parse --git-path index)" "$GIT_INDEX_FILE" 2>/dev/null \\
    || {_GIT} read-tree {base} || exit 4
{_GIT} add -A . >/dev/null 2>{_STAGE}/add.err || {{ cat {_STAGE}/add.err >&2; exit 4; }}
# New files that stay behind:
#  * test files the agent wrote. Grading only uses the hidden test patch, and
#    a test file that runs under a whole-suite command (npm test) could tamper
#    with the runner. Files the gold patch itself adds are kept.
#  * large files (build output the agent forgot to ignore).
KEEP=({keep_arr})
is_kept() {{ local k; for k in ${{KEEP[@]+"${{KEEP[@]}}"}}; do [ "$k" = "$1" ] && return 0; done; return 1; }}
{_GIT} diff --cached --name-only --diff-filter=A -z {base} > {_STAGE}/added
while IFS= read -r -d '' f; do
    is_kept "$f" && continue
    case "/$f" in
      */__tests__/*|*/test_*.py|*_test.py|*_test.go|*/conftest.py|*.test.[cm][jt]s|*.test.[jt]s|*.test.[jt]sx|*.spec.[cm][jt]s|*.spec.[jt]s|*.spec.[jt]sx)
        {_GIT} rm -q --cached -- "$f" && echo "dropped agent test file: $f"; continue ;;
    esac
    if [ -f "$f" ] && [ "$(stat -c %s -- "$f" 2>/dev/null || echo 0)" -gt $(( {max_file_mb} * 1048576 )) ]; then
        {_GIT} rm -q --cached -- "$f" && echo "skipped large untracked file: $f"
    fi
done < {_STAGE}/added
after="$({_GIT} write-tree)" || exit 5
{_GIT} diff --binary --no-color --no-ext-diff --no-textconv {base} "$after" > {_STAGE}/agent.patch || exit 5
rm -f {_STAGE}/index {_STAGE}/add.err {_STAGE}/added
echo "patch_bytes=$(stat -c %s {_STAGE}/agent.patch)"
"""


def _apply_cmd(workdir: str) -> str:
    wd = shlex.quote(workdir)
    return f"""
set -u
cd {wd} || exit 2
[ -s {_STAGE}/agent.patch ] || {{ echo "empty patch"; exit 0; }}
{_GIT} apply --binary --whitespace=nowarn {_STAGE}/agent.patch || exit 6
rm -rf {_STAGE}
echo applied
"""


class FreshSandboxEvaluator:
    """Move the agent's diff into a new sandbox and run ``inner`` there."""

    def __init__(self, inner, task, agent_sandbox, sandbox_backend: str | None):
        self.inner = inner
        self.task = task
        self.agent_sandbox = agent_sandbox
        self.sandbox_backend = sandbox_backend
        self.max_file_mb = int(os.environ.get("RLLM_FRESH_VERIFY_MAX_FILE_MB", "10"))
        self.base_tree: str | None = None

    def snapshot(self) -> None:
        """Record the pre-agent tree. Call after environment setup, before the agent and before hiding git history."""
        workdir = self.task.metadata.get("workdir")
        if not workdir:
            return
        out = self.agent_sandbox.exec(_snapshot_cmd(workdir), timeout=900, user="root")
        tree = (out or "").strip().splitlines()[-1].strip() if out else ""
        if len(tree) not in (40, 64) or any(c not in "0123456789abcdef" for c in tree):
            raise RuntimeError(f"fresh-sandbox verify: bad base tree for {self.task.id}: {out[-200:]!r}")
        self.base_tree = tree

    @staticmethod
    def _keep_paths(task) -> list[str]:
        """Paths the gold patch touches (tests/config.json ``harness_keep_paths``): never dropped."""
        cfg = Path(task.task_dir) / "tests" / "config.json"
        try:
            return list(json.loads(cfg.read_text()).get("harness_keep_paths") or [])
        except (OSError, ValueError):
            return []

    def _fail(self, reason: str, detail: str = "") -> EvalOutput:
        logger.warning("fresh-sandbox verify %s: %s %s", self.task.id, reason, detail[-500:])
        # Not the agent's fault when the harness cannot move the patch: mark it
        # so compact filtering drops the episode instead of training on a 0.
        return EvalOutput(reward=0.0, is_correct=False, metadata={"reason": reason, "detail": detail[-2000:], "termination_reason": "error"})

    def evaluate(self, task, episode):
        from rllm.eval._resolution import _create_sandbox_for_task, _setup_task_environment

        workdir = task.metadata.get("workdir")
        if not workdir:
            return self._fail("fresh_verify_no_workdir")
        if not self.base_tree:
            return self._fail("fresh_verify_no_base_tree")
        try:
            out = self.agent_sandbox.exec(_extract_cmd(workdir, self.base_tree, self.max_file_mb, self._keep_paths(task)), timeout=900, user="root")
        except Exception as e:  # noqa: BLE001
            return self._fail("agent_patch_extract_failed", str(e))

        fd, tar_path = tempfile.mkstemp(prefix="rllm-agent-patch-", suffix=".tar")
        os.close(fd)
        fresh = None
        try:
            self.agent_sandbox.download_archive(_STAGE, tar_path)
            fresh = _create_sandbox_for_task(task, self.sandbox_backend)
            _setup_task_environment(task, fresh)
            fresh.exec(f"rm -rf {_STAGE}", timeout=30, user="root")
            fresh.upload_archive(tar_path, os.path.dirname(_STAGE))
            try:
                fresh.exec(_apply_cmd(workdir), timeout=600, user="root")
            except Exception as e:  # noqa: BLE001
                # The patch came from this very image's tree; failing to apply
                # it back is a harness problem, not an unsolved task.
                return self._fail("agent_patch_apply_failed", f"{out}\n{e}")
            self.inner.sandbox = fresh
            result = self.inner.evaluate(task, episode)
            result.metadata = {**(result.metadata or {}), "graded_in": "fresh_sandbox", "agent_patch": (out or "").strip()[-1000:]}
            return result
        except Exception as e:  # noqa: BLE001
            return self._fail("fresh_verify_failed", f"{type(e).__name__}: {e}")
        finally:
            if fresh is not None:
                try:
                    fresh.close()
                except Exception:
                    logger.exception("fresh sandbox close failed")
            try:
                os.unlink(tar_path)
            except FileNotFoundError:
                pass

    def __getattr__(self, name):
        return getattr(self.inner, name)


def fresh_verify_enabled() -> bool:
    """On unless RLLM_FRESH_SANDBOX_VERIFY is set to 0/false/no/off.

    Default-on on purpose: a training run that forgets the variable would
    otherwise grade in the agent's sandbox, which is exactly where RL learns
    to look for holes.
    """
    return os.environ.get("RLLM_FRESH_SANDBOX_VERIFY", "1").strip().lower() not in {"0", "false", "no", "off"}


__all__ = ["FreshSandboxEvaluator", "fresh_verify_enabled"]
