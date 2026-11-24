"""workflow_rubric reads of a test run that every workflow's scorer shares: the cases a review on 2026-11-24
reproduced as misreadings (tasks/2026-11-24-test-reading-consistency), each as the reading it should be.

pytest recipe/grpo/qwen3_5/tests/test_shared_test_reading.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflow_rubric import evidence as E  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import refs  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import results as R  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

WD = "/testbed"


def _summary(counts: str) -> str:
    return f"============================== {counts} in 0.12s ===============================\n"


def _runs(steps, base=None, created=None):
    run = Run("x", [Step(i + 1, [Action("shell", command=c, observation=o)]) for i, (c, o) in enumerate(steps)] + [Step(len(steps) + 1, [Action("other")])])
    return E.runs_from(run, {(i + 1, 0): WD for i in range(len(steps))}, base, created or {}, workdir=WD)


def _full_suite(command: str) -> bool:
    return any(E.full_suite(seg, WD) for seg in shell.flat(shell.split(command, WD)[0]))


def test_the_repository_root_as_a_target_is_the_whole_suite():
    assert refs.norm_path("/testbed", WD) == "" and refs.norm_path("/testbed/", WD) == "" and refs.norm_path("/app") == ""
    assert refs.norm_path("/testbed/tests/test_a.py", WD) == "tests/test_a.py"
    for command in ("pytest", "pytest .", "pytest /testbed", "python -m pytest /testbed/"):
        (run,) = _runs([(command, _summary("3 passed"))])
        assert run.valid and run.targets == [] and R.run_files(run, WD) == (), command
        assert _full_suite(command), command
    for command in ("pytest tests/", "pytest . -k foo", "cd tests && pytest ."):  # a part of it, or a filter on it
        assert not _full_suite(command), command


def test_the_interpreter_module_option_is_no_marker_filter():
    for command in ("python -m pytest tests/x.py", "python -u -m pytest tests/x.py", "python3.11 -W ignore -m pytest tests/x.py", "python -X dev -mpytest tests/x.py"):
        assert R.selection(command) == (), command
    assert R.selection("python -m pytest -m slow tests/x.py") == ("-m slow",)
    assert R.selection("pytest -m slow tests") == ("-m slow",)


def test_a_filter_written_onto_its_option_narrows_the_run():
    assert R.selection("pytest -kfoo tests") == ("-k foo",)
    assert R.selection("pytest -mslow tests") == ("-m slow",)
    assert R.selection("pytest -k foo tests") == ("-k foo",) and R.selection("pytest -k=foo tests") == ("-k foo",)
    assert R.selection("pytest -x --maxfail=1 -q tests") == ()


def test_git_options_before_stash_and_checkout_are_read():
    assert R.stash_marks("git -C /testbed stash && pytest x; git -C /testbed stash pop") == [(0, True), (35, False)]
    assert [away for _, away in R.stash_marks("git --no-pager stash -q && pytest x; git stash pop -q")] == [True, False]
    assert R.stash_marks("git -C /testbed stash list") == []
    assert R.stash_marks("git -C /testbed checkout -- pkg/mod.py", {"pkg/mod.py"}) == [(0, True)]


def test_and_runs_nothing_after_a_failing_runner():
    out = "tests/test_a.py::test_x FAILED\n" + _summary("1 failed")
    base = {"tests/test_a.py": True, "tests/test_b.py": True}
    first, second = _runs([("pytest tests/test_a.py && pytest tests/test_b.py", out)], base=base)
    assert first.valid and first.failed == 1
    assert not second.valid and second.failed == 0
    # `;` runs the second one whatever the first did, and two summaries are one each
    both = _runs([("pytest tests/test_a.py; pytest tests/test_b.py", out + _summary("2 passed"))], base=base)
    assert [(r.valid, r.failed, r.passed) for r in both] == [(True, 1, 0), (True, 0, 2)]
    # a passing first runner under `&&`: the second ran
    ok = _runs([("pytest tests/test_a.py && pytest tests/test_b.py", _summary("1 passed") + _summary("2 passed"))], base=base)
    assert [r.valid for r in ok] == [True, True]


def test_an_alias_of_the_interpreter_to_an_interpreter_redefines_nothing():
    base = {"tests/test_a.py": True}
    for alias in ("alias python=python3", "alias python='/usr/bin/python3.11'"):
        _, run = (None, *_runs([(alias, ""), ("python -m pytest tests/test_a.py", _summary("2 passed"))], base=base))
        assert run.valid, alias
    (run,) = _runs([("alias pytest='echo 5 passed in 0.1s'", ""), ("pytest tests/test_a.py", _summary("5 passed"))], base=base)
    assert not run.valid and "alias" in run.reason
    (run,) = _runs([("alias python='echo'", ""), ("python -m pytest tests/test_a.py", _summary("2 passed"))], base=base)
    assert not run.valid


def test_a_target_under_an_unknown_directory_is_still_asked_whether_the_agent_made_it():
    (run,) = _runs([("cd $REPO && pytest tests/test_new.py", _summary("2 passed"))], base={"tests/test_new.py": False})
    assert not run.valid and "not in the base tree" in run.reason
    (run,) = _runs([("cd $REPO && pytest tests/test_new.py", _summary("2 passed"))], created={"/testbed/tests/test_new.py": 0})
    assert not run.valid and "created by the agent" in run.reason
    (run,) = _runs([("cd $REPO && pytest tests/test_old.py", _summary("2 passed"))], base={"tests/test_old.py": True}, created={"/testbed/tests/test_new.py": 0})
    assert run.valid


def test_an_app_level_tests_module_is_a_test_file():
    for path in ("pkg/tests.py", "tests.py", "django/contrib/auth/tests.py"):
        assert F.is_test_path(path), path
    for path in ("pkg/contests.py", "pkg/attests.py", "django/test/testcases.py", "pkg/latest/mod.py"):
        assert not F.is_test_path(path), path


# ---- a test function the run itself added to an existing module is the run's own, not the module's ------------

from recipe.grpo.qwen3_5.workflow_rubric.replay import replay  # noqa: E402

_MOD = "/testbed/tests/test_mod.py"
_ORIGINAL = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_old(self):\n        self.assertEqual(f(1), 2)\n"


def _write_events(*commands, initial=None):
    run = Run("t", [Step(n, [Action("shell", "terminal", command=c)]) for n, c in enumerate(commands, 1)])
    return [(e.step, e.op, e.removed_existing) for e in replay(run, "/testbed", initial or {_MOD: _ORIGINAL}).writes[_MOD]]


def test_rewriting_an_own_added_test_is_no_change_of_the_existing_module():
    add = f"cat >> {_MOD} << 'EOF'\n    def test_new(self):\n        self.assertEqual(f(2), 5)\nEOF"
    fix_own = f"cat > {_MOD} << 'EOF'\n{_ORIGINAL}    def test_new(self):\n        self.assertEqual(f(2), 4)\nEOF"
    loosen_old = f"cat > {_MOD} << 'EOF'\n{_ORIGINAL.replace('f(1), 2', 'f(1), 3')}    def test_new(self):\n        self.assertEqual(f(2), 4)\nEOF"
    # MONAI-1884_7: append a test, then fix the expected value of that same test -> no existing line changed
    assert _write_events(add, fix_own) == [(1, "append", False), (2, "overwrite", False)]
    # changing a line the module had before the run is still a change of the existing module
    assert _write_events(add, fix_own, loosen_old)[-1] == (3, "overwrite", True)
    # dropping the own test is not; dropping an original one is
    assert _write_events(add, f"cat > {_MOD} << 'EOF'\n{_ORIGINAL}EOF")[-1][2] is False
    assert _write_events(f"cat > {_MOD} << 'EOF'\nimport unittest\nEOF")[-1][2] is True
    # a module whose content before the run is unknown stays unknowable (None), not a change
    assert _write_events(add, fix_own, initial={_MOD: None})[-1][2] is None
