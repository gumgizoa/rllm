"""openspec_ff's log_only penalty items (``reward/penalty.py``) and the second score they give, ``openspec_ff/penalty``.

Each case is the golden run (``selftest_golden.py``: the tests run as the baseline, the code changed, the check script and
the tests run again in verify, then verify.md) with one thing changed, scored by the engine like any run.
"""

import copy
import re
from pathlib import Path

import pytest

from recipe.grpo.qwen3_5.workflow_rubric import engine
from recipe.grpo.qwen3_5.workflow_rubric import results as R
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


# what collect.py's exec 3 finds for the golden change online: the tests that cover tinyconf/values.py (R7 reads it;
# without it -- offline -- no_run_after_change is unavailable)
RELATED = {"tinyconf/values.py": ["tests/test_values.py"]}


def _score(rubric, run, col):
    if col.related_tests is None:
        col.related_tests = dict(RELATED)
    rep = engine.evaluate(rubric, run, col)
    out = P.post(rep)
    return {r: out.get(P.signal(r)) for r in P.RULES}, out, rep  # None: the item was unavailable


def _sh(command, observation=""):
    return Step(0, [Action("shell", "terminal", command=command, observation=observation)])


def test_the_golden_run_and_its_variants_pass_every_item(rubric):
    for v in (None, *SG.VARIANTS):
        got, out, _ = _score(rubric, *_golden(rubric, v))
        assert got == ALL, (v, got)
        assert out["penalty"] == 1.0 and out["penalty_unavailable"] == 0.0
        # the four rules the run was judged on, and the one it stands outside of with its condition not arisen:
        # nothing had to be CRITICAL because the tests were read and none failed -- worth 1
        assert {r: out[f"penalty_applies.{r}"] for r in P.RULES} == {**ALL, "critical_missing": 0.0}, v


def test_the_items_are_reported_and_never_scored(rubric):
    run, col = _golden(rubric)
    d = rubric.to_dict()
    ids = {P.item_id(r) for r in P.RULES}
    d["items"] = [i for i in d["items"] if i["id"] not in ids]
    without = selftest.with_docs(S.Rubric.from_dict(d), PKG)
    assert len(rubric.items) == len(without.items) + len(P.RULES)
    assert all(i.log_only for i in rubric.items if i.id in ids)
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
    assert out["penalty"] == pytest.approx(0.5)
    assert "tests/test_values.py" in rep.results[P.ITEM_PREFIX + "left_broken"].detail


def test_a_rerun_that_leaves_the_failing_test_out_does_not_clear_it(rubric):
    run, col = _golden(rubric)
    _fail_last_test(run)
    i = _step_of(run, _is_test)
    run.steps.insert(i + 1, _sh(SG.TEST_CMD + ' -k "not test_parse_bool_false"', "..                                                                       [100%]\n2 passed, 1 deselected in 0.02s" + SG.EXIT0))
    got, _, _ = _score(rubric, _renumber(run), col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def _is_edit(a):
    return a.kind == "replace" and (a.path or "").startswith("/testbed/")


def _tasks_writes(run, f):
    """Rewrite the text of every write of tasks.md (its creation in ff)."""
    for st in run.steps:
        for a in st.actions:
            if a.path == TASKS and a.kind == "create" and a.text:
                a.text = f(a.text)
    return run


def _files(col, f):
    col = copy.deepcopy(col)
    for path in [p for p in col.files if p.endswith("-issue/tasks.md")]:  # the archived change's task list
        col.files[path] = f(col.files[path])
    return col


def _fail_baseline(run, col, observation=FAILED, record=True):
    """The baseline: the tests as ff ran them, before any code change, now with a failure -- which tasks.md records
    under ``## Baseline`` (``record``), as the tasks instruction asks."""
    i = _step_of(run, _is_test, last=False)
    assert i < _step_of(run, _is_edit, last=False)
    for a in run.steps[i].actions:
        if _is_test(a):
            a.observation = observation
    if record:
        ids = ", ".join(f"`{x}`" for x in re.findall(r"(?m)^FAILED (\S+)", observation)) or "one test"
        listed = lambda text: text.replace("- Failing before the change: none", f"- Failing before the change: {ids}")  # noqa: E731
        return _tasks_writes(run, listed), _files(col, listed)
    return run, col


def test_a_test_that_failed_in_the_baseline_is_no_failure_of_the_change(rubric):
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col)
    got, out, rep = _score(rubric, _fail_last_test(run), col)
    # the same test fails before the first code change and after the last: the clean report is true, nothing is due
    # as CRITICAL and nothing is left broken
    assert got == ALL and out["penalty"] == 1.0
    assert "failed only as in the baseline" in rep.results[P.ITEM_PREFIX + "left_broken"].detail


def test_without_a_baseline_run_every_failure_counts(rubric):
    run, col = _golden(rubric)
    _fail_last_test(run)
    del run.steps[_step_of(run, _is_test, last=False)]  # the tests were never run before the first code change
    got, _, rep = _score(rubric, _renumber(run), col)
    # tasks.md still names the command under ``## Baseline``: a run it claims and never made
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0, "false_baseline": 0.0}
    assert "no baseline run" in rep.results[P.ITEM_PREFIX + "left_broken"].detail
    assert "was not run" in rep.results[P.item_id("false_baseline")].detail


def test_a_new_failure_beside_a_baseline_failure_counts(rubric):
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col)
    two = FAILED.replace("F..", "FF.").replace("\n1 failed, 2 passed", "\nFAILED tests/test_values.py::test_parse_int_strips\n2 failed, 1 passed")
    assert "2 failed, 1 passed" in two
    for a in run.steps[_step_of(run, _is_test)].actions:
        if _is_test(a):
            a.observation = two
    got, _, _ = _score(rubric, run, col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def test_another_test_failing_than_the_baseline_s_counts(rubric):
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col, FAILED.replace("test_parse_bool_false", "test_parse_int_strips"))
    got, _, _ = _score(rubric, _fail_last_test(run), col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def test_a_failure_the_output_does_not_name_is_not_excused(rubric):
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col)
    for a in run.steps[_step_of(run, _is_test)].actions:  # the summary counts a failure, no line says which test
        if _is_test(a):
            a.observation = "F..                                                                      [100%]\n1 failed, 2 passed in 0.02s" + SG.EXIT1
    got, _, _ = _score(rubric, run, col)
    assert got == {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def test_the_baseline_section_says_what_the_baseline_run_showed(rubric):
    FB = P.item_id("false_baseline")
    # the run showed a failure, the section says none
    run, col = _golden(rubric)
    got, out, rep = _score(rubric, *_fail_baseline(run, col, record=False))
    assert got == {**ALL, "false_baseline": 0.0} and "not listed: test_parse_bool_false" in rep.results[FB].detail

    # the section lists a test the run did not show failing
    add = lambda text: text.replace("- Failing before the change: none", "- Failing before the change: `tests/test_values.py::test_parse_bool_yes`")  # noqa: E731
    run, col = _golden(rubric)
    got, _, rep = _score(rubric, _tasks_writes(run, add), _files(col, add))
    assert got == {**ALL, "false_baseline": 0.0} and "listed, not failing: test_parse_bool_yes" in rep.results[FB].detail

    # the failure recorded as it was: true, whatever comes after
    run, col = _golden(rubric)
    got, _, _ = _score(rubric, *_fail_baseline(run, col))
    assert got["false_baseline"] == 1.0

    # no section: the run stands outside the rule, worth 0
    drop = lambda text: text.replace(f"## Baseline\n\n- Command: `{SG.TEST_CMD}`\n- Failing before the change: none\n\n", "")  # noqa: E731
    run, col = _golden(rubric)
    got, out, _ = _score(rubric, _tasks_writes(run, drop), _files(col, drop))
    assert got == {**ALL, "false_baseline": 0.0} and out["penalty_applies.false_baseline"] == 0.0

    # the summary counts a failure the output does not name: what failed cannot be read
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col, "F..                                                                      [100%]\n1 failed, 2 passed in 0.02s" + SG.EXIT1, record=False)
    _, out, rep = _score(rubric, run, col)
    assert rep.results[FB].status == "unavailable" and out["penalty_unavailable"] == 1.0 and P.signal("false_baseline") not in out


def test_one_name_for_a_test_however_it_is_printed():
    n, same = P.name_of, P._same_test
    assert n("tests/test_io.py::TestA::test_x[a.b]") == (("tests", "test_io"), "TestA.test_x[a.b]")
    assert n("tests.test_io.TestA.test_x") == (("tests", "test_io"), "TestA.test_x")
    assert n("TestA.test_x") == ((), "TestA.test_x") and n("test_x") == ((), "test_x")
    assert same(n("tests/test_io.py::test_download"), n("test_download"))  # the section form names no file
    assert same(n("test_io.py::test_download"), n("tests/test_io.py::test_download"))  # run from inside tests/
    assert same(n("tests.test_io.TestA.test_x"), n("pkg/tests/test_io.py::TestA::test_x"))
    assert not same(n("tests/test_io.py::test_download"), n("tests/test_net.py::test_download"))  # another file's test
    assert not same(n("tests/test_io.py::TestA::test_x"), n("tests/test_io.py::TestB::test_x"))


BASE_REC = "openspec_ff.ff.tasks.openspec_ff_tasks.baseline_recorded"
BASE_RUN = "openspec_ff.ff.run.openspec_ff_evidence.baseline_run"


def test_the_baseline_is_recorded_in_tasks_md_and_was_run_before_the_first_code_change(rubric):
    run, col = _golden(rubric)
    rep = engine.evaluate(rubric, run, col)
    assert rep.results[BASE_REC].status == rep.results[BASE_RUN].status == "pass"

    # the section names the command, but ff never ran it: recorded, not run
    run, col = _golden(rubric)
    del run.steps[_step_of(run, _is_test, last=False)]
    rep = engine.evaluate(rubric, _renumber(run), col)
    assert rep.results[BASE_REC].status == "pass" and rep.results[BASE_RUN].status == "fail" and rep.scores.compliance < 1.0

    # the same run made right after the first code change is no baseline
    run, col = _golden(rubric)
    step = run.steps.pop(_step_of(run, _is_test, last=False))
    run.steps.insert(_step_of(run, _is_edit, last=False) + 1, step)
    assert engine.evaluate(rubric, _renumber(run), col).results[BASE_RUN].status == "fail"

    # the tests were run, tasks.md has no Baseline section: neither item passes
    drop = lambda text: text.replace(f"## Baseline\n\n- Command: `{SG.TEST_CMD}`\n- Failing before the change: none\n\n", "")  # noqa: E731
    run, col = _golden(rubric)
    rep = engine.evaluate(rubric, _tasks_writes(run, drop), _files(col, drop))
    assert "## Baseline" not in next(v for k, v in _files(col, drop).files.items() if k.endswith("-issue/tasks.md"))
    assert rep.results[BASE_REC].status == rep.results[BASE_RUN].status == "fail"

    # the section names another command than the one that was run
    other = lambda text: text.replace(f"- Command: `{SG.TEST_CMD}`", "- Command: `python -m pytest tests/test_other.py -q`")  # noqa: E731
    run, col = _golden(rubric)
    rep = engine.evaluate(rubric, _tasks_writes(run, other), _files(col, other))
    assert rep.results[BASE_REC].status == "pass" and rep.results[BASE_RUN].status == "fail"


def test_a_baseline_run_made_during_explore_counts(rubric):
    run, col = _golden(rubric, "explore_runs_tests")
    i = [k for k, st in enumerate(run.steps) if any(_is_test(a) for a in st.actions)]
    del run.steps[i[1]]  # ff does not run it again: the run explore made is the one tasks.md records
    rep = engine.evaluate(rubric, _renumber(run), col)
    assert rep.results[BASE_RUN].status == "pass" and rep.scores.compliance == 1.0


def test_the_baseline_run_verifies_no_task(rubric):
    # every box ticked as tasks.md is written: the task that names the test command has only the baseline run before
    # its tick, which says nothing of the change
    VERIFIED = "openspec_ff.apply.tasks.tasks.verified"
    run, col = _golden(rubric)
    assert engine.evaluate(rubric, run, col).results[VERIFIED].status == "pass"
    rep = engine.evaluate(rubric, _tasks_writes(run, lambda text: text.replace("- [ ]", "- [x]")), col)
    assert rep.results[VERIFIED].status == "fail"


def test_a_run_made_only_before_the_code_change_is_no_run_after_it(rubric):
    AFTER = "openspec_ff.verify.run.openspec_ff_evidence.run_after_change"
    run, col = _golden(rubric)
    col.related_tests = dict(RELATED)
    assert engine.evaluate(rubric, run, col).results[AFTER].status == "pass"
    edit = _step_of(run, _is_edit)
    assert any(_is_check(a) or _is_test(a) for st in run.steps[:edit] for a in st.actions)  # the check script and the baseline, before the change
    for st in run.steps[edit + 1 :]:
        st.actions = [Action("shell", "terminal", command="git status --short", observation=" M tinyconf/values.py" + SG.EXIT0) if _is_test(a) or _is_check(a) else a for a in st.actions]
    rep = engine.evaluate(rubric, run, col)
    assert rep.results[AFTER].status == "fail" and rep.scores.signals["stage.verify"] < 1.0
    assert rep.results[BASE_RUN].status == "pass"


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
    # the report still says all checks passed. Nothing had to be CRITICAL and nothing stands failed -- because nothing
    # was run: the run stands outside those two rules without having done what they are about, worth 0, so running
    # no test is never the way to keep a rule
    assert got == {**ALL, "no_run_after_change": 0.0, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0}


def test_a_check_script_whose_outcome_cannot_be_read_ran_and_is_no_passing_result(rubric):
    run, col = _golden(rubric)
    edit = _step_of(run, lambda a: a.kind == "replace" and (a.path or "").startswith("/testbed/"))
    for st in run.steps[edit + 1 :]:
        acts = []
        for a in st.actions:
            if _is_test(a):
                a = Action("shell", "terminal", command="git status --short", observation=" M tinyconf/values.py" + SG.EXIT0)
            elif _is_check(a):
                a = Action("shell", "terminal", command=a.command, observation="done")  # no exit code, no pass / failure text
            acts.append(a)
        st.actions = acts
    got, out, rep = _score(rubric, run, col)
    # only the check script ran after the change: no run of the tests that cover the change (no_run_after_change, R7 of
    # the 11-24 review: a check script alone is no such run); nothing is known to stand failed (left_broken) and
    # nothing had to be CRITICAL -- but no readable result says the checks passed, so the clean claim is unsupported
    assert got == {**ALL, "false_clean_claim": 0.0, "no_run_after_change": 0.0}
    assert "runs not_run" in rep.results[P.ITEM_PREFIX + "false_clean_claim"].detail


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
    class Rep:  # a run that changed no code: every item not applicable, worth 0
        results = {P.item_id(r): type("X", (), {"status": "not_applicable", "score": 0.0})() for r in P.RULES}

    out = P.post(Rep())
    assert out["penalty"] == 0.0 and all(out[P.signal(r)] == 0.0 and out[f"penalty_applies.{r}"] == 0.0 for r in P.RULES)

    class Blind:  # nothing could be read: no penalty signal at all, rather than a made-up 0 or 1
        results = {P.item_id(r): type("X", (), {"status": "unavailable", "score": 0.0})() for r in P.RULES}

    out = P.post(Blind())
    assert "penalty" not in out and out["penalty_unavailable"] == float(len(P.RULES))


def test_checkboxes_are_read_leniently():
    assert P._boxes("- [x] a\n- [ x] b\n-[X] c\n- [DONE] d\n- [ ] e\n- [TODO] f\n- [link](u) g\n<!-- - [ ] h -->") == (4, 6)


def test_what_narrows_a_test_run():
    assert P._selection("python -m pytest tests/a.py -q") == ()
    assert P._selection('python -m pytest tests/a.py -k "not test_x"') == ("-k not test_x",)
    assert P._selection("pytest tests/a.py::T::t --deselect tests/a.py::T::u") == ("--deselect tests/a.py::T::u", "tests/a.py::T::t")
    T = R.TestResult
    runs = [T(1, False, True, ("tests/a.py",)), T(2, True, True, ("tests/a.py",), ("-k not t",)), T(3, False, True, ("tests/b.py",))]
    assert R.standing_failures(runs, 9) == ["tests/a.py", "tests/b.py"]  # the narrower pass clears nothing
    assert R.standing_failures([*runs, T(4, True, True, ("tests",))], 9) == []  # the whole directory passing clears both
    assert R.standing_failures([*runs, T(4, True, True, ("tests",))], 3) == ["tests/a.py", "tests/b.py"]  # as of step 3
    assert R.standing_failures([*runs, T(4, True, True, (R.WHOLE,))]) == []  # so does the whole suite
    assert R.standing_failures([T(1, False, True, ("tests/a.py",)), T(2, True, True, ("tests/a.py",), ("tests/a.py::t_other",))]) == ["tests/a.py"]  # another test of the file
    assert R.standing_failures([T(1, False, True, ("tests/a.py",), ("tests/a.py::t",)), T(2, True, True, ("tests/a.py",), ("tests/a.py::t",))]) == []  # the very test that failed
    assert R.standing_failures([T(1, False, True, ("tests/a.py", "tests/b.py")), T(2, True, True, ("tests/a.py",))]) == ["tests/b.py"]  # one of two files
    assert R.standing_failures([T(1, False, True, ("queries.test_q",)), T(2, True, True, ("queries",))]) == []  # a dotted label above it


def test_a_critical_heading_with_items_counts_as_listed():
    assert P.lists_critical("### CRITICAL\n- tests/test_values.py fails\n### WARNING\nNone")
    assert not P.lists_critical("### CRITICAL\nNone\n### WARNING\n- x")
    assert not P.lists_critical("1. **CRITICAL** (Must fix before archive): None")


def test_a_run_that_could_not_be_scored_keeps_no_penalty_rule(rubric, monkeypatch):
    """The trainer reads a rollout without the penalty signal as P = 1, so a failed scoring says 0 itself."""
    from types import SimpleNamespace

    from recipe.grpo.qwen3_5.workflow_rubric import evaluation as EV
    from rllm.eval.types import EvalOutput

    assert EV.failure_signals("openspec_ff", "compliance", rubric) == {"openspec_ff/compliance": 0.0, "openspec_ff/engine_errors": 1.0, "openspec_ff/penalty": 0.0}
    assert "openspec_ff/penalty" not in EV.failure_signals("openspec_ff")  # no rubric with penalty items: nothing said of them

    def boom(*a, **k):
        raise RuntimeError("the episode cannot be parsed")

    monkeypatch.setattr(EV, "parse_run", boom)
    inner = SimpleNamespace(name="verifier", evaluate=lambda task, episode: EvalOutput(reward=1.0, is_correct=True, signals=[], metadata={}))
    for post, want in ((P.post, 0.0), (None, None)):  # None: an evaluation with no penalty hook reports no penalty at all
        ev = EV.RubricEvaluator(inner, None, rubric, "openspec_ff", None, post=post)
        out = ev.evaluate(SimpleNamespace(id="t"), SimpleNamespace())
        got = {s.name: s.value for s in out.signals}
        assert out.reward == 1.0 and got["openspec_ff/compliance"] == 0.0 and got["openspec_ff/engine_errors"] == 1.0
        assert got.get("openspec_ff/penalty") == want


def test_the_baseline_is_one_reading_for_the_compliance_item_the_claim_and_the_excused_failures(rubric):
    FB, LB = P.item_id("false_baseline"), P.ITEM_PREFIX + "left_broken"
    broken = {**ALL, "false_clean_claim": 0.0, "critical_missing": 0.0, "left_broken": 0.0, "false_baseline": 0.0}

    # the command recorded without the -q it was run with: the same runner on the same file is that run
    bare = lambda text: text.replace(f"- Command: `{SG.TEST_CMD}`", f"- Command: `{SG.TEST_CMD.removesuffix(' -q')}`")  # noqa: E731
    run, col = _golden(rubric)
    run, col = _tasks_writes(run, bare), _files(col, bare)
    assert engine.evaluate(rubric, run, col).results[BASE_RUN].status == "pass"
    got, _, _ = _score(rubric, run, col)
    assert got == ALL

    # a test fails before the first code change and after the last, and tasks.md has no Baseline section: the run
    # recorded no baseline, so nothing is excused -- the failure counts like any other
    drop = lambda text: text.replace(f"## Baseline\n\n- Command: `{SG.TEST_CMD}`\n- Failing before the change: none\n\n", "")  # noqa: E731
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col, record=False)
    got, _, rep = _score(rubric, _tasks_writes(_fail_last_test(run), drop), _files(col, drop))
    assert got == broken and "no baseline run" in rep.results[LB].detail

    # the section names another command than the one that was run: the same
    other = lambda text: text.replace(f"- Command: `{SG.TEST_CMD}`", "- Command: `python -m pytest tests/test_other.py -q`")  # noqa: E731
    run, col = _golden(rubric)
    run, col = _fail_baseline(run, col, record=False)
    got, _, rep = _score(rubric, _tasks_writes(_fail_last_test(run), other), _files(col, other))
    assert got == broken and "was not run" in rep.results[FB].detail
