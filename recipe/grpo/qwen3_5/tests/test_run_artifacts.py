"""run_artifacts: the collection script against a real git repository and a real bash.

The commands are what runs in the sandbox, so they are tested by running them, with the sandbox
replaced by a local shell and the marker / stray roots moved under ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipe.grpo.qwen3_5 import run_artifacts  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from rllm.harnesses.cli_harness import BaseCliHarness  # noqa: E402
from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness  # noqa: E402
from rllm.types import AgentConfig, Episode, Task  # noqa: E402

CONFIG = AgentConfig(base_url="http://127.0.0.1:8000/v1", model="m", session_uid="u")


class _Shell:
    """A sandbox that is this machine's bash."""

    def __init__(self):
        self.execs = []

    def exec(self, command, timeout=None, user=None):
        self.execs.append(command)
        return subprocess.run(["bash", "-c", command], check=True, capture_output=True, text=True, timeout=timeout).stdout


def _git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A repo at its base commit, an output dir, a stray root, and the marker under tmp_path."""
    repo = tmp_path / "testbed"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.py").write_text("x = 1\n")
    (repo / "c.py").write_text("gone = True\n")
    (repo / ".gitignore").write_text("*.log\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD").strip()

    (tmp_path / "opt").mkdir()
    monkeypatch.setattr(run_artifacts, "MARKER", str(tmp_path / "opt" / "start"))
    # pytest's own tmp_path is under /tmp/pytest-of-*, which the stray scan skips.
    monkeypatch.setattr(run_artifacts, "STRAY_IGNORED", ("*/__pycache__",))
    stray = tmp_path / "tmp"
    stray.mkdir()
    old = stray / "before.txt"
    old.write_text("there before the agent")
    os.utime(old, (time.time() - 100, time.time() - 100))
    return {"repo": repo, "base": base, "out": tmp_path / "out", "stray": stray, "tmp": tmp_path}


def _agent_works(b):
    """What an agent might leave: an edit, a new file, an ignored file, its own commit, a deletion."""
    repo = b["repo"]
    (repo / "a.py").write_text("x = 2\n")
    (repo / "new.py").write_text("print('repro')\n")
    (repo / "debug.log").write_text("ignored\n")
    (repo / "b.py").write_text("committed = 1\n")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-qm", "agent commit")
    (repo / "c.py").unlink()
    (b["out"] / "checks").mkdir(parents=True)
    (b["out"] / "assessment.md").write_text("# Assessment\n한글 ok\n")
    (b["out"] / "checks" / "one.md").write_text("check 1\n")
    (b["stray"] / "misplaced.md").write_text("a report in the wrong place\n")


def _collect(b, **kw):
    sh = _Shell()
    sh.exec(run_artifacts.start_command(str(b["repo"])))
    marker = Path(run_artifacts.MARKER)
    os.utime(marker, (time.time() - 10, time.time() - 10))  # strictly older than the agent's files
    _agent_works(b)
    cmd = run_artifacts.collect_command(str(b["repo"]), (str(b["out"]),), stray_roots=(str(b["stray"]),), stray_skip=(), **kw)
    return run_artifacts.parse(sh.exec(cmd))


def test_patch_is_the_whole_change_against_the_start_commit(box):
    art = _collect(box)
    patch = art["patch"]
    assert art["patch_base"] == box["base"]
    assert "patch_error" not in art and art["patch_truncated"] is False
    assert art["patch_bytes"] == len(patch.encode())
    assert "+x = 2" in patch  # tracked edit
    assert "new.py" in patch  # untracked file
    assert "b.py" in patch  # the agent's own commit
    assert "deleted file mode" in patch and "c.py" in patch
    assert "debug.log" not in patch  # .gitignore respected


def test_patch_applies_back_onto_the_base(box, tmp_path):
    patch = _collect(box)["patch"]
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(box["repo"]), str(clone)], check=True)
    _git(clone, "checkout", "-q", box["base"])
    (tmp_path / "p.diff").write_text(patch)
    _git(clone, "apply", str(tmp_path / "p.diff"))
    assert (clone / "a.py").read_text() == "x = 2\n" and (clone / "new.py").exists() and not (clone / "c.py").exists()


def test_the_repository_index_is_left_alone(box):
    _collect(box)
    status = _git(box["repo"], "status", "--porcelain")
    assert "?? new.py" in status  # still untracked: nothing was staged in the real index
    assert _git(box["repo"], "diff", "--cached", "--name-only") == ""


def test_outputs_in_the_scorer_shape_and_stray_files_by_name(box):
    art = _collect(box)
    out = str(box["out"])
    assert art["workflow_outputs"] == {f"{out}/assessment.md": "# Assessment\n한글 ok\n", f"{out}/checks/one.md": "check 1\n"}
    assert art["stray_files"] == {str(box["stray"] / "misplaced.md"): len("a report in the wrong place\n")}


def test_size_caps(box, monkeypatch):
    monkeypatch.setattr(run_artifacts, "MAX_PATCH_BYTES", 50)
    monkeypatch.setattr(run_artifacts, "MAX_OUTPUT_BYTES", 10)
    art = _collect(box)
    assert art["patch_truncated"] is True and len(art["patch"].encode()) == 50
    assert art["workflow_outputs"] == {f"{box['out']}/checks/one.md": "check 1\n"}
    assert list(art["workflow_outputs_skipped"]) == [f"{box['out']}/assessment.md"]


def test_no_repository_is_an_error_entry_not_a_failure(tmp_path, monkeypatch):
    (tmp_path / "opt").mkdir()
    monkeypatch.setattr(run_artifacts, "MARKER", str(tmp_path / "opt" / "start"))
    plain = tmp_path / "plain"
    plain.mkdir()
    sh = _Shell()
    sh.exec(run_artifacts.start_command(str(plain)))
    art = run_artifacts.parse(sh.exec(run_artifacts.collect_command(str(plain), (), stray_roots=(), stray_skip=())))
    assert art["patch_base"] is None and "no git repository" in art["patch_error"] and "patch" not in art


# --- the harness side --------------------------------------------------------------------------


@pytest.fixture
def harness_box(box, monkeypatch):
    """OpenHandsSdkWorkflow whose agent is _agent_works, in the local shell."""
    monkeypatch.setattr(OpenHandsSdkHarness, "write_configs", lambda *a, **k: None)
    monkeypatch.setattr(OpenHandsSdkHarness, "build_invocation", lambda *a, **k: "true")

    def exec_agent(self, sandbox, cmd, timeout=None, env=None):
        os.utime(run_artifacts.MARKER, (time.time() - 10, time.time() - 10))
        _agent_works(box)

    monkeypatch.setattr(BaseCliHarness, "_exec_agent", exec_agent)
    monkeypatch.setattr(OpenHandsSdkWorkflow, "stray_roots", (str(box["stray"]),))
    task = Task(id="t1", instruction="fix it", metadata={"workdir": str(box["repo"])})
    return box, task


def test_run_returns_the_artifacts_on_the_episode(harness_box, monkeypatch):
    box, task = harness_box
    h = OpenHandsSdkWorkflow(workflow="speckit_bug")
    h.workflow_spec = dataclasses.replace(h.workflow_spec, output_dirs=(str(box["out"]),))
    monkeypatch.setattr(h, "_upload_docs", lambda sandbox: None)
    monkeypatch.setattr(h, "_write_system_prompt", lambda sandbox, text: None)
    ep = h.run(task, CONFIG, env=_Shell())
    assert isinstance(ep, Episode) and ep.trajectories[0].name == "openhands-sdk"
    art = ep.artifacts
    assert art["workflow"] == {"name": "speckit_bug", "sha256": h.workflow_fingerprint}
    assert art["patch_base"] == box["base"] and "+x = 2" in art["patch"]
    assert f"{box['out']}/assessment.md" in art["workflow_outputs"]
    assert list(art["stray_files"]) == [str(box["stray"] / "misplaced.md")]


def test_no_workflow_still_collects_the_patch(harness_box):
    box, task = harness_box
    ep = OpenHandsSdkWorkflow().run(task, CONFIG, env=_Shell())
    assert ep.artifacts["workflow"] == {"name": None, "sha256": None}
    assert "workflow_outputs" not in ep.artifacts and "+x = 2" in ep.artifacts["patch"]


def test_collection_failure_never_fails_the_rollout(harness_box):
    _, task = harness_box

    class Broken(_Shell):
        def exec(self, command, timeout=None, user=None):
            if command.startswith("bash -c"):
                raise RuntimeError("container is gone")
            return super().exec(command, timeout, user)

    ep = OpenHandsSdkWorkflow().run(task, CONFIG, env=Broken())
    assert "container is gone" in ep.artifacts["patch_error"]


def test_collect_patch_off_is_the_plain_run(harness_box):
    _, task = harness_box
    sh = _Shell()
    h = OpenHandsSdkWorkflow()
    h.configure({"agent_kwargs": {"collect_patch": "false"}})
    assert h.collect_patch is False
    assert h.run(task, CONFIG, env=sh) is None
    assert sh.execs == []
