"""openspec_ff's log_only penalty items (``reward/penalty.py``) and the second score they give, ``openspec_ff/penalty``.

Each case is the golden run (``selftest_golden.py``: code changed at step 40, the check script and the tests run again in
verify, then verify.md) with one thing changed, scored by the engine like any run.
"""

import copy
from pathlib import Path

import pytest

from recipe.grpo.qwen3_5.workflow_rubric import engine
from recipe.grpo.qwen3_5.workflow_rubric import schema as S
from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Step
from recipe.grpo.qwen3_5.workflows.openspec_ff import selftest_golden as SG
from recipe.grpo.qwen3_5.workflows.openspec_ff.reward import penalty as P
from recipe.grpo.qwen3_5.workflows.openspec_ff.reward.eval import Evaluation

PKG = Path(SG.__file__).parent
ALL = dict.fromkeys(P.RULES, 1.0)
FAILED = "F..                                                                      [100%]\nFAILED tests/test_values.py::test_parse_bool_false\n1 failed, 2 passed in 0.02s" + SG.EXIT1
VERIFY = "/openspec/changes/issue/verify.md"
TASKS = "/openspec/changes/issue/tasks.md"


@pytest.fixture(scope="module")
def rubric():
    return selftest.with_docs(Evaluation().rubric, PKG)


def _golden(rubric, variant=None):
    run, col = SG.golden(rubric) if variant is None else SG.golden(rubric, variant=variant)
    return copy.deepcopy(run), col


def _renumber(run):
    for n, st in enumerate(run.steps, 1):
        st.n = n
    return run


def _step_of(run, pred, last=True):
    hits = [i for i, st in enumerate(run.steps) if any(pred(a) for a in st.actions)]
    assert hits
    return hits[-1] if last else hits[0]


def _is_test(a):
    return a.kind == "shell" and (a.command or "").startswith(SG.TEST_CMD)


def _is_check(a):
    return a.kind == "shell" and (a.command or "").startswith("python /openspec/changes/issue/checks/")


def _writes(path):
    return lambda a: a.path == path and a.kind in ("create", "replace")


def _score(rubric, run, col):
    rep = engine.evaluate(rubric, run, col)
    out = P.post(rep)
    return {r: out[f"verify.penalty.{r}"] for r in P.RULES}, out, rep


def _sh(command, observation=""):
    return Step(0, [Action("shell", "terminal", command=command, observation=observation)])


def test_the_golden_run_and_its_variants_pass_every_item(rubric):
    for v in (None, *SG.VARIANTS):
        got, out, _ = _score(rubric, *_golden(rubric, v))
        assert got == ALL, (v, got)
        assert out["penalty"] == 1.0 and out["penalty_applicable"] == 1.0


def test_the_items_are_reported_and_never_scored(rubric):
    run, col = _golden(rubric)
    d = rubric.to_dict()
    d["items"] = [i for i in d["items"] if not i["id"].startswith(P.ITEM_PREFIX)]
    without = selftest.with_docs(S.Rubric.from_dict(d), PKG)
    assert len(rubric.items) == len(without.items) + len(P.RULES)
    assert all(i.log_only for i in rubric.items if i.id.startswith(P.ITEM_PREFIX))
    for mutate in (lambda r: r, lambda r: _fail_last_test(r)):
        a, b = engine.evaluate(rubric, mutate(copy.deepcopy(run)), col), engine.evaluate(without, mutate(copy.deepcopy(run)), col)
        assert a.scores.compliance == b.scores.compliance
        assert {k: v for k, v in a.scores.signals.items()} == {k: v for k, v in b.scores.signals.items()}


def _fail_last_test(run):
    st = run.steps[_step_of(run, _is_test)]
    for a in st.actions:
        if _is_test(a):
            a.observation = FAILED
    return run


def test_a_failed_run_behind_a_clean_report(rubric):
    run, col = _golden(rubric)
    got, out, rep = _score(rubric, _fail_last_test(run), col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}
    assert out["penalty"] == pytest.approx(0.4)
    assert "tests/test_values.py" in rep.results[P.ITEM_PREFIX + "left_broken"].detail


def test_a_rerun_that_leaves_the_failing_test_out_does_not_clear_it(rubric):
    run, col = _golden(rubric)
    _fail_last_test(run)
    i = _step_of(run, _is_test)
    run.steps.insert(i + 1, _sh(SG.TEST_CMD + ' -k "not test_parse_bool_false"', "..                                                                       [100%]\n2 passed, 1 deselected in 0.02s" + SG.EXIT0))
    got, _, _ = _score(rubric, _renumber(run), col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def test_the_same_run_passing_again_clears_the_failure(rubric):
    run, col = _golden(rubric)
    _fail_last_test(run)
    i = _step_of(run, _is_test)
    run.steps.insert(i + 1, _sh(SG.TEST_CMD, SG.PYTEST_OK + SG.EXIT0))
    got, _, _ = _score(rubric, _renumber(run), col)
    assert got == ALL


def test_nothing_run_after_the_last_code_change(rubric):
    run, col = _golden(rubric)
    edit = _step_of(run, lambda a: a.kind == "replace" and (a.path or "").startswith("/testbed/"))
    for st in run.steps[edit + 1 :]:
        st.actions = [Action("shell", "terminal", command="git status --short", observation=" M tinyconf/values.py" + SG.EXIT0) if _is_test(a) or _is_check(a) else a for a in st.actions]
    got, _, _ = _score(rubric, run, col)
    # nothing had to be CRITICAL and nothing stands failed; the report still says all checks passed
    assert got == {**ALL, "no_run_after_change": 0.0, "false_clean_claim": 0.0}


def test_no_report(rubric):
    run, col = _golden(rubric)
    del run.steps[_step_of(run, _writes(VERIFY))]
    got, _, _ = _score(rubric, _renumber(run), col)
    assert got == {**ALL, "false_clean_claim": 0.0, "task_count_mismatch": 0.0, "critical_missing": 0.0}


def test_code_changed_after_the_report_was_written(rubric):
    run, col = _golden(rubric)
    i = _step_of(run, _writes(VERIFY))
    edit = copy.deepcopy(run.steps[_step_of(run, lambda a: a.kind == "replace" and (a.path or "").startswith("/testbed/"))])
    for a in edit.actions:  # a second edit of the same file: put the old text back in and take it out again
        a.old, a.text = a.text, a.text + "\n"
    run.steps.insert(i + 1, edit)
    got, _, _ = _score(rubric, _renumber(run), col)
    assert got["false_clean_claim"] == got["task_count_mismatch"] == got["critical_missing"] == 0.0
    assert got["no_run_after_change"] == 0.0  # nothing was run after that edit either


def test_an_open_task_behind_a_report_that_counts_every_task_done(rubric):
    run, col = _golden(rubric)
    i = _step_of(run, _writes(TASKS))  # the last tick: drop it, so one box stays open
    run.steps[i].actions = [Action("shell", "terminal", command="git status --short", observation=SG.EXIT0)]
    got, _, rep = _score(rubric, run, col)
    assert got == {**ALL, "false_clean_claim": 0.0, "task_count_mismatch": 0.0, "critical_missing": 0.0, "left_broken": 0.0}
    assert "open task" in rep.results[P.ITEM_PREFIX + "left_broken"].detail


def test_post_with_nothing_applicable():
    class R:  # a run that changed no code: every item not applicable
        results = {P.ITEM_PREFIX + r: type("X", (), {"status": "not_applicable", "score": 0.0})() for r in P.RULES}

    out = P.post(R())
    assert out["penalty"] == 0.0 and out["penalty_applicable"] == 0.0 and all(out[f"verify.penalty.{r}"] == 0.0 for r in P.RULES)


def test_checkboxes_are_read_leniently():
    assert P._boxes("- [x] a\n- [ x] b\n-[X] c\n- [DONE] d\n- [ ] e\n- [TODO] f\n- [link](u) g\n<!-- - [ ] h -->") == (4, 6)


def test_what_narrows_a_test_run():
    assert P._selection("python -m pytest tests/a.py -q") == ()
    assert P._selection('python -m pytest tests/a.py -k "not test_x"') == ("-k not test_x",)
    assert P._selection("pytest tests/a.py::T::t --deselect tests/a.py::T::u") == ("--deselect tests/a.py::T::u", "tests/a.py::T::t")
    runs = [(1, "test tests/a.py", False, ()), (2, "test tests/a.py", True, ("-k not t",)), (3, "test tests/b.py", False, ())]
    assert P._standing(runs, 9) == {"test tests/a.py": False, "test tests/b.py": False}  # the narrower pass clears nothing
    assert P._standing([*runs, (4, "test tests", True, ())], 9) == {"test tests": True}  # the whole directory passing clears both
    assert P._standing([*runs, (4, "test tests", True, ())], 3) == {"test tests/a.py": False, "test tests/b.py": False}  # as of step 3


def test_a_critical_heading_with_items_counts_as_listed():
    assert P.lists_critical("### CRITICAL\n- tests/test_values.py fails\n### WARNING\nNone")
    assert not P.lists_critical("### CRITICAL\nNone\n### WARNING\n- x")
    assert not P.lists_critical("1. **CRITICAL** (Must fix before archive): None")
