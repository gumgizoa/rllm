"""speckit_bug: what a verification report's rows and Result are held to, on the self-test golden run.

* a row naming a repository test run records what the runner printed (``checks_table`` rule ``outcome``);
* a failure the same tests already had before the change is not a new one (rule ``consistent``, 03-test.md:43);
* a verified Result with the existing tests not run again fails (rule ``unrun``);
* a round never begun is one missing report, not two zeroed stages;
* rounds 2 and 3 run the checks again after their change;
* a bare file name names no gold file.

    pytest recipe/grpo/qwen3_5/tests/test_speckit_bug_verdict_rules.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5.workflow_rubric import engine  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.evaluation import rubric_signals  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.generator.mutations import simulate  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug import selftest_golden as G  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug.reward import checks  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug.reward.eval import Evaluation  # noqa: E402

RUBRIC = Evaluation().rubric
BUG = G.BUG
TEST_MD = f"{BUG}/test.md"
BASE_FILES = {"setup.py": "x\n", "tinyconf/__init__.py": G.INIT_PY, "tinyconf/values.py": G.VALUES_PY, "tests/test_values.py": G.TESTS_PY, "tinyconf/extra.py": "X = 1\n"}
BASE_TREE = (*G.BASE_TREE, "tinyconf/extra.py")
SUMMARY = "=========================== short test summary info ============================\n"
FAILS_LEGACY = f".F.                                                                      [100%]\n{SUMMARY}FAILED tests/test_values.py::test_legacy - AssertionError\n1 failed, 2 passed in 0.03s"
FAILS_OTHER = FAILS_LEGACY.replace("test_legacy", "test_other")
P = "speckit_bug.test.test.speckit_bug_checks_table."


def _actions(variant=None):
    run, _ = G.golden(variant=variant)
    return [a for s in run.steps for a in s.actions]


def _index(acts, path):
    return next(i for i, a in enumerate(acts) if a.kind == "create" and a.path == path)


def _score(acts, gold=("tinyconf/values.py",)):
    if not (acts[-1].kind == "other" and acts[-1].name == "finish"):
        acts = [*acts, Action("other", "finish")]
    run = Run(instance_id="test/speckit_bug", steps=[Step(i + 1, [a]) for i, a in enumerate(acts)])
    col = simulate(run, workdir=G.WORKDIR, base_sha=G.BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(BUG,), base_files=BASE_FILES)
    col.inputs = {"gold_files": list(gold)}
    col.related_tests = {"tinyconf/values.py": ["tests/test_values.py"]}
    report = engine.evaluate(RUBRIC, run, col)
    return rubric_signals(RUBRIC, run, col, "speckit_bug", checks.post), {k: r.status for k, r in report.results.items()}


def _retext(acts, path, fn):
    out = list(acts)
    i = _index(out, path)
    a = out[i]
    out[i] = Action("create", a.name, path=a.path, text=fn(a.text), status="ok", observation=a.observation)
    return out


def _row(result, note="x"):
    def swap(text):
        lines = text.splitlines()
        k = next(i for i, ln in enumerate(lines) if ln.startswith("| Regression suite"))
        lines[k] = f"| Regression suite | `{G.TEST_CMD}` | {result} | {note} |" if result != "skipped" else "| Regression suite | not run | skipped | not needed |"
        return "\n".join(lines) + "\n"

    return swap


def _suite_prints(acts, before=None, after=None):
    """The golden with the existing tests' output replaced before / after the first repository edit."""
    edit = next(i for i, a in enumerate(acts) if a.kind == "replace")
    out = []
    for k, a in enumerate(acts):
        obs = before if k < edit else after
        if a.kind == "shell" and a.command == G.TEST_CMD and obs is not None:
            a = Action("shell", a.name, command=a.command, observation=obs)
        out.append(a)
    return out


def test_the_golden_runs_keep_every_rule():
    for variant in (None, "two_rounds"):
        sig, status = _score(_actions(variant))
        assert sig["speckit_bug/compliance"] == 1.0
        assert status[P + "outcome"] == "pass"


@pytest.mark.parametrize("result", ["fail", "pass"])
def test_a_failure_the_baseline_already_had_does_not_stand_against_verified(result):
    sig, status = _score(_retext(_suite_prints(_actions(), FAILS_LEGACY, FAILS_LEGACY), TEST_MD, _row(result, "test_legacy failed in the baseline too")))
    assert status[P + "consistent"] == "pass" and status[P + "outcome"] == "pass"
    assert sig["speckit_bug/compliance"] == 1.0


def test_a_pass_row_over_a_new_failure_is_caught():
    sig, status = _score(_retext(_suite_prints(_actions(), None, FAILS_LEGACY), TEST_MD, _row("pass", "3 passed")))
    assert status[P + "outcome"] == "fail"
    assert sig["speckit_bug/compliance"] < 1.0


def test_a_new_failure_recorded_as_fail_still_contradicts_verified():
    for before in (None, FAILS_OTHER):  # no failure before, or another test's
        _, status = _score(_retext(_suite_prints(_actions(), before, FAILS_LEGACY), TEST_MD, _row("fail", "pre-existing")))
        assert status[P + "consistent"] == "fail"
        assert status[P + "outcome"] == "pass"  # the row itself says what the run printed


def test_a_fail_row_over_a_clean_run_is_not_what_the_run_printed():
    _, status = _score(_retext(_actions(), TEST_MD, _row("fail", "pre-existing")))
    assert status[P + "outcome"] == "fail" and status[P + "consistent"] == "fail"


def test_verified_with_the_existing_tests_not_run_again_fails():
    _, status = _score(_retext(_actions(), TEST_MD, _row("skipped")))
    assert status[P + "unrun"] == "fail"
    assert status[P + "outcome"] == "not_applicable"  # no row names a test run: nothing to hold to its output


def test_a_round_never_begun_is_one_missing_report():
    two = _actions("two_rounds")
    sig, status = _score(two[: _index(two, TEST_MD) + 1])  # Result failed, then nothing
    assert sig["speckit_bug/stage.fix_2"] == 0.0
    assert "speckit_bug/stage.test_2" not in sig
    assert status["speckit_bug.test_2.test_2.artifact_exists"] == "not_applicable"
    assert sig["speckit_bug/compliance"] == pytest.approx((1 + 1 + 1 + 0 + 0.5 + 0.75) / 6)


def test_a_begun_round_without_its_verification_report_still_zeroes_the_test_stage():
    two = _actions("two_rounds")
    sig, status = _score(two[: _index(two, f"{BUG}/fix-2.md") + 1])
    assert status["speckit_bug.test_2.test_2.artifact_exists"] == "fail"
    assert sig["speckit_bug/stage.test_2"] == 0.0


def test_round_2_runs_the_checks_again_after_its_change():
    two = _actions("two_rounds")
    item = "speckit_bug.fix_2.run.speckit_bug_check_scripts.run_after_change"
    assert _score(two)[1][item] == "pass"
    edit = [i for i, a in enumerate(two) if a.kind == "replace"][-1]
    report = _index(two, f"{BUG}/fix-2.md")
    sig, status = _score([a for k, a in enumerate(two) if not (edit < k < report and a.kind == "shell" and a.command == G.CHECK_CMD)])
    assert status[item] == "fail"
    assert sig["speckit_bug/stage.fix_2"] < 1.0


def test_a_bare_file_name_names_no_gold_file():
    assert checks._names({"pkg/mod.py"}, "src/pkg/mod.py") and checks._names({"/work/src/pkg/mod.py"}, "src/pkg/mod.py")
    assert checks._names({"setup.py"}, "setup.py")
    assert not checks._names({"mod.py"}, "src/pkg/mod.py") and not checks._names({"__init__.py"}, "pkg/__init__.py")
    listed = lambda name: _retext(_actions(), f"{BUG}/assessment.md", lambda t: t.replace("- `tinyconf/values.py`\n", f"- `tinyconf/values.py`\n- `{name}`\n"))  # noqa: E731
    assert _score(listed("extra.py"), gold=("tinyconf/extra.py",))[0]["speckit_bug/fix.penalty.gold_files.named"] == 0.0
    assert _score(listed("tinyconf/extra.py"), gold=("tinyconf/extra.py",))[0]["speckit_bug/fix.penalty.gold_files.named"] == 1.0
