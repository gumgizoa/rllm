"""collect.py exec 3: the repository's existing tests related to the changed source files
(``Collected.related_tests``), read from the sandbox with a shell the checks never run themselves.

    pytest recipe/grpo/qwen3_5/tests/test_related_tests_collect.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5.workflow_rubric import collect as C  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout


def _sh(script: str) -> str:
    return subprocess.run(["sh", "-c", C._command(script)], check=True, capture_output=True, text=True, timeout=60).stdout


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A package whose public name is re-exported, tests reaching it three ways, and one unrelated test."""
    r = tmp_path / "testbed"
    for d in ("pkg/sub", "tests/queries", "src", "pkg/test"):
        (r / d).mkdir(parents=True)
    (r / "pkg/sub/query.py").write_text("class QuerySet:\n    def union(self):\n        return 1\n")
    (r / "pkg/sub/__init__.py").write_text("from pkg.sub.query import QuerySet\n")
    (r / "tests/queries/tests.py").write_text("import pkg.sub\n\ndef test_union():\n    assert pkg.sub.QuerySet().union() == 1\n")  # by symbol
    (r / "tests/test_query.py").write_text("from pkg.sub import query\n")  # by name and by import
    (r / "tests/test_other.py").write_text("x = 1\n")  # unrelated
    (r / "pkg/test/utils.py").write_text("def helper(): pass\n")  # a package's test framework, not a test
    (r / "src/util.py").write_text("def helper(): pass\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r, _git(r, "rev-parse", "HEAD").strip()


def test_related_tests_by_name_import_and_symbol(repo):
    r, base = repo
    (r / "pkg/sub/query.py").write_text("class QuerySet:\n    def union(self):\n        return 2\n")
    (r / "pkg/brand_new.py").write_text("def newmod(): pass\n")  # untracked: its own text supplies the symbols
    changed = ["pkg/sub/query.py", "pkg/brand_new.py", "src/util.py"]
    c = Collected(workdir=str(r), base_sha=base)
    C.parse_related(_sh(C.related_script(str(r), base, changed)), c, changed)
    assert c.errors == []
    assert c.related_tests == {"pkg/sub/query.py": ["tests/queries/tests.py", "tests/test_query.py"], "pkg/brand_new.py": [], "src/util.py": []}


def test_related_tests_only_existing_tracked_tests_count(repo):
    r, base = repo
    (r / "tests/test_query_new.py").write_text("from pkg.sub import query\n")  # agent-made, untracked
    (r / "pkg/sub/query.py").write_text("class QuerySet:\n    pass\n")
    c = Collected(workdir=str(r), base_sha=base)
    C.parse_related(_sh(C.related_script(str(r), base, ["pkg/sub/query.py"])), c, ["pkg/sub/query.py"])
    assert c.related_tests == {"pkg/sub/query.py": ["tests/queries/tests.py", "tests/test_query.py"]}


def test_related_tests_step_failures_leave_none(tmp_path):
    c = Collected(workdir=str(tmp_path / "missing"), base_sha="0" * 40)
    C.parse_related(_sh(C.related_script(str(tmp_path / "missing"), "0" * 40, ["a.py"])), c, ["a.py"])
    assert c.related_tests is None
    assert any("cannot cd" in e for e in c.errors)
    c2 = Collected(workdir="/x", base_sha="0" * 40)
    C.parse_related("", c2, ["a.py"])
    assert c2.related_tests is None and any("no output" in e for e in c2.errors)
    c3 = Collected(workdir="/x", base_sha="0" * 40)
    C.parse_related(f"{C._MARK} BEGIN\n{C._MARK} REL YS5weQ==\n\n", c3, ["a.py"])  # cut before END
    assert c3.related_tests == {"a.py": []} and any("cut short" in e for e in c3.errors)


def test_changed_sources_are_the_diffs_python_code_paths():
    c = Collected(diff={"pkg/a.py": "M", "tests/test_a.py": "M", "pkg/__pycache__/a.pyc": "?", "README.md": "M", "pkg/new.py": "?", "lib.pyx": "A"})
    assert C.changed_sources(c) == ["lib.pyx", "pkg/a.py", "pkg/new.py"]
    assert C.changed_sources(Collected()) == []


def test_module_parts_follow_python_import_names():
    assert C._module_parts("pandas/core/arrays/string_arrow.py") == ("string_arrow", "pandas.core.arrays.string_arrow", "pandas.core.arrays")
    assert C._module_parts("django/db/models/__init__.py") == ("models", "django.db.models", "django.db")
    assert C._module_parts("src/_pytest/setuponly.py") == ("setuponly", "_pytest.setuponly", "_pytest")
    assert C._module_parts("pandas/_libs/lib.pyx") == ("lib", "pandas._libs.lib", "pandas._libs")
