"""FreshSandboxEvaluator's shell steps, run against a real git repo on the host.

The evaluator itself needs docker; what decides *what* reaches the fresh
sandbox is the snapshot / extract / apply shell, which these tests drive with
plain bash in a temp dir.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from rllm.sandbox import fresh_verify as fv

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _sh(script: str) -> str:
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _git(repo: Path, *args: str) -> None:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(repo)}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(fv, "_STAGE", str(tmp_path / "stage"))
    r = tmp_path / "testbed"
    (r / "src").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "src" / "calc.py").write_text("def div(a, b):\n    return a / b\n")
    (r / "tests" / "test_calc.py").write_text("def test_div(): pass\n")
    (r / ".gitignore").write_text("node_modules/\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    # Image build steps leave the tree off HEAD: a generated file and an edited lockfile.
    (r / "generated.txt").write_text("from the image build\n")
    (r / "src" / "calc.py").write_text("def div(a, b):\n    return a / b  # patched by build\n")
    return r


def _snapshot(repo: Path) -> str:
    return _sh(fv._snapshot_cmd(str(repo))).strip().splitlines()[-1]


def _extract(repo: Path, base: str, keep=()) -> tuple[str, str]:
    out = _sh(fv._extract_cmd(str(repo), base, 10, list(keep)))
    return out, (Path(fv._STAGE) / "agent.patch").read_text()


def test_patch_is_relative_to_the_pre_agent_tree(repo):
    base = _snapshot(repo)
    (repo / "src" / "calc.py").write_text("def div(a, b):\n    return a / b if b else 0\n")
    _, patch = _extract(repo, base)
    assert "return a / b if b else 0" in patch
    # Build-time changes are part of the base, not the agent's diff.
    assert "generated.txt" not in patch
    assert "-    return a / b\n" not in patch  # HEAD's line never appears


def test_agent_test_files_are_dropped_but_gold_paths_kept(repo):
    base = _snapshot(repo)
    (repo / "src" / "helper.py").write_text("X = 1\n")
    (repo / "tests" / "test_mine.py").write_text("def test_x(): pass\n")
    (repo / "tests" / "conftest.py").write_text("# hook\n")
    (repo / "web").mkdir()
    (repo / "web" / "a.test.ts").write_text("test('x', () => {})\n")
    (repo / "web" / "__tests__").mkdir()
    (repo / "web" / "__tests__" / "b.js").write_text("// x\n")
    (repo / "web" / "__snapshots__").mkdir()
    (repo / "web" / "__snapshots__" / "a.test.ts.snap").write_text("exports[`x 1`] = `1`;\n")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "zz_test.go").write_text("package pkg\n")
    (repo / "tests" / "test_gold_adds.py").write_text("# the gold patch adds this one\n")
    out, patch = _extract(repo, base, keep=["tests/test_gold_adds.py"])
    assert "src/helper.py" in patch
    assert "tests/test_gold_adds.py" in patch
    dropped_files = ("tests/test_mine.py", "tests/conftest.py", "web/a.test.ts", "web/__tests__/b.js", "web/__snapshots__/a.test.ts.snap", "pkg/zz_test.go")
    for dropped in dropped_files:
        assert dropped not in patch, dropped
        assert f"dropped agent test file: {dropped}" in out


def test_edits_to_existing_test_files_still_travel(repo):
    """Only *new* test files are dropped; edits to tracked ones go through and test.sh resets them."""
    base = _snapshot(repo)
    (repo / "tests" / "test_calc.py").write_text("def test_div(): assert True\n")
    _, patch = _extract(repo, base)
    assert "tests/test_calc.py" in patch


def test_patch_applies_to_a_copy_of_the_pre_agent_tree(repo, tmp_path):
    fresh = tmp_path / "fresh"
    shutil.copytree(repo, fresh)  # what the task image gives a new sandbox
    base = _snapshot(repo)
    (repo / "src" / "calc.py").write_text("def div(a, b):\n    return 0 if b == 0 else a / b\n")
    (repo / "src" / "new_mod.py").write_text("Y = 2\n")
    (repo / "generated.txt").unlink()
    _extract(repo, base)
    _sh(fv._apply_cmd(str(fresh)))
    assert (fresh / "src" / "calc.py").read_text() == (repo / "src" / "calc.py").read_text()
    assert (fresh / "src" / "new_mod.py").read_text() == "Y = 2\n"
    assert not (fresh / "generated.txt").exists()


def test_enabled_by_default(monkeypatch):
    monkeypatch.delenv("RLLM_FRESH_SANDBOX_VERIFY", raising=False)
    assert fv.fresh_verify_enabled()
    monkeypatch.setenv("RLLM_FRESH_SANDBOX_VERIFY", "0")
    assert not fv.fresh_verify_enabled()
