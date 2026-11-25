"""The rules every workflow's scorer reads test behaviour by (tasks/2026-11-24-test-reading-consistency/통일-검토.md,
R1-R7, ``workflow_rubric/testread.py``) and the workflow readings moved onto them: each with an input the change
reads differently and one that must keep its reading.

pytest recipe/grpo/qwen3_5/tests/test_test_reading_rules_1124.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import results as R  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import testread as T  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, EvalContext  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

WD = "/testbed"
OK = "\n[The command completed with exit code 0.]"
BAD = "\n[The command completed with exit code 1.]"
SRC = f"{WD}/pkg/mod.py"


def _summary(counts: str) -> str:
    return f"============================== {counts} in 0.12s ===============================\n"


PASS = "tests/test_mod.py .\n" + _summary("1 passed")


def sh(command: str, observation: str = OK) -> Action:
    return Action("shell", "terminal", command=command, observation=observation)


def edit(path: str = SRC) -> Action:
    return Action("replace", "file_editor", path=path, old="a = 1", text="a = 2", status="ok", observation=f"The file {path} has been edited.")


def _ctx(actions, related=None, base=("pkg/mod.py", "tests/test_mod.py", "tests/test_other.py")):
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)] + [Step(len(actions) + 1, [Action("other")])])
    rub = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
    col = Collected(workdir=WD, diff={"pkg/mod.py": "M"}, mode="online", base_present={p: True for p in base})
    col.related_tests = related
    fx = F.build(rub, run, col)
    return EvalContext(rubric=rub, run=run, collected=col, facts=fx)


# ---- R1 / R2: the change is a source write; in one call its place in the text decides ------------------------------
def test_a_run_after_the_write_in_one_call_is_after_it_and_one_before_it_before_it():
    after = _ctx([edit(), sh("sed -i 's/a = 2/a = 3/' pkg/mod.py && python -m pytest tests/test_mod.py", PASS + OK)])
    (r,) = after.facts.runs
    assert T.after_change(after, T.run_mark(r)) and not T.before_change(after, T.run_mark(r))
    before = _ctx([sh(f"python -m pytest tests/test_mod.py; sed -i 's/a = 1/a = 3/' {SRC}", PASS + OK)])
    (r,) = before.facts.runs
    assert T.before_change(before, T.run_mark(r)) and not T.after_change(before, T.run_mark(r))
    # must keep its reading: a run in a later call is after, an earlier call before
    plain = _ctx([sh("python -m pytest tests/test_mod.py", PASS + OK), edit(), sh("python -m pytest tests/test_mod.py", PASS + OK)])
    first, last = plain.facts.runs
    assert T.before_change(plain, T.run_mark(first)) and T.after_change(plain, T.run_mark(last))


def test_a_test_file_written_is_no_code_change():
    ctx = _ctx([edit(), sh("python -m pytest tests/test_mod.py", PASS + OK), edit(f"{WD}/tests/test_mod.py")])
    (r,) = ctx.facts.runs
    assert T.change_steps(ctx) == [1]  # the test edit at step 3 is not a change (R1)
    assert T.after_change(ctx, T.run_mark(r))


# ---- R3: the change put away ------------------------------------------------------------------------------------------
def test_a_reverse_applied_patch_puts_the_change_away_and_applying_it_brings_it_back():
    assert [on for _, on in R.stash_marks("git apply -R /tmp/fix.patch && pytest tests; git apply /tmp/fix.patch")] == [True, False]
    assert [on for _, on in R.stash_marks("patch -p1 -R < /tmp/fix.patch && pytest")] == [True]
    # must keep its reading: no patch run, a dry check, a git stash as before
    assert R.stash_marks("git diff > /tmp/fix.patch && echo apply the patch") == []
    assert R.stash_marks("git apply --check /tmp/fix.patch") == []
    assert [on for _, on in R.stash_marks("git stash && pytest; git stash pop")] == [True, False]


def test_a_run_with_the_change_put_away_is_no_change_run():
    ctx = _ctx([edit(), sh("git diff > /tmp/p.diff && git apply -R /tmp/p.diff && python -m pytest tests/test_mod.py; git apply /tmp/p.diff", PASS + OK),
                sh("python -m pytest tests/test_mod.py", PASS + OK)])
    assert [r.step for r in T.change_runs(ctx)] == [3] and [r.step for r in T.stash_runs(ctx)] == [2]
    flags, after = T.stash_flags("git stash && pytest x; git stash pop", ["git stash", "pytest x", "git stash pop"])
    assert flags == [False, True, True] and after is False


# ---- R4: a script of the run's own, as it stands ------------------------------------------------------------------------
def test_a_scripts_result_counts_only_after_its_last_write():
    chk = "/tmp/checks/check_a.py"
    acts = [Action("create", "file_editor", path=chk, text="assert 1\n", status="ok", observation="File created"), sh(f"python {chk}", "ok" + OK),
            Action("create", "file_editor", path=chk, text="assert 0\n", status="ok", observation="File created")]
    ctx = _ctx(acts)
    runs = T.script_runs(ctx, {chk})[chk]
    assert [x.outcome for x in runs] == ["pass"]
    assert T.last_result(runs, T.own_writes(ctx, chk)) is None  # rewritten after its last run: the test as it stands never ran
    ctx2 = _ctx([*acts, sh(f"python {chk}", "Traceback (most recent call last):\nAssertionError" + BAD)])
    runs2 = T.script_runs(ctx2, {chk})[chk]
    assert T.last_result(runs2, T.own_writes(ctx2, chk)).outcome == "fail"


# ---- R5 / R6: failing names and the baseline ---------------------------------------------------------------------------
def _res(step, passed, keys=("tests/test_a.py",), ids=()):
    return R.TestResult(step, passed, True, keys, (), ids)


def test_a_failure_is_old_only_when_the_last_baseline_run_that_ran_it_failed_it_by_name():
    tid = "tests/test_a.py::test_x"
    assert T.preexisting(tid, [_res(1, False, ids=(tid,))])
    # the last baseline run that ran it passed it: new (it was failing once, then not)
    assert not T.preexisting(tid, [_res(1, False, ids=(tid,)), _res(2, True)])
    # a baseline run that failed without naming its failures names nothing (R5)
    assert not T.preexisting(tid, [_res(1, False)])
    # another test failed in the baseline: new (by count both runs fail one test)
    assert T.new_failures((tid,), [_res(1, False, ids=("tests/test_a.py::test_y",))]) == [tid]
    # a run that fails tests it does not name: every failure new
    assert T.new_failures(None, [_res(1, False, ids=(tid,))]) is None
    # unittest's dotted form and pytest's node id are one test
    assert T.same_test("tests/test_a.py::T::test_x", "tests.test_a.T.test_x")


# ---- R7: the existing tests of the changed code ------------------------------------------------------------------------
def test_a_whole_suite_run_runs_the_related_tests():
    acts = [edit(), sh("cd /testbed && python -m pytest", PASS + OK)]
    ctx = _ctx(acts, related={"pkg/mod.py": ["tests/test_mod.py"]})
    assert T.related_run(ctx, T.change_runs(ctx))[0] == "hit"
    other = _ctx([edit(), sh("cd /testbed && python -m pytest tests/test_other.py", "tests/test_other.py .\n" + _summary("1 passed") + OK)], related={"pkg/mod.py": ["tests/test_mod.py"]})
    assert T.related_run(other, T.change_runs(other))[0] == "miss"
    assert T.related_run(_ctx(acts, related=None), [])[0] == "unavailable"
    assert T.related_run(_ctx(acts, related={"pkg/mod.py": []}), [])[0] == "none"


# ---- agentos_bugfix: a failure there without the change (R5 / R6 on the stash runs) -----------------------------------
def test_agentos_excuses_a_failure_only_by_the_last_stash_run_that_ran_it():
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    tid = "tests/test_a.py::test_x"
    ctx = SimpleNamespace(cache={"agentos_v2.stashed_results": [_res(3, False, ids=(tid,)), _res(5, True)]}, collected=SimpleNamespace(workdir=WD, diff={}, base_present={"tests/test_a.py": True}),
                          rubric=SimpleNamespace(artifacts={}), facts=SimpleNamespace(repo_writes=[]))
    failing = _res(9, False, ids=(tid,))
    assert C.excused_failures(ctx, [(("test", tid), failing)]) == set()  # it passed in the last stash run: the change's
    ctx.cache["agentos_v2.stashed_results"] = [_res(3, False, ids=(tid,))]
    assert C.excused_failures(ctx, [(("test", tid), failing)]) == {("test", tid)}  # must keep: failed by name without the change
    # a file unit (the output named no test) cannot be matched: the change's, whatever the stash run showed (R5)
    assert C.excused_failures(ctx, [(("key", "tests/test_a.py"), _res(9, False))]) == set()


# ---- aidlc: item 23 and R5 in the regression reading ------------------------------------------------------------------
def test_aidlc_regressions_are_not_judged_without_a_valid_baseline_and_unnamed_failures_are_new():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import measures as M4
    from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward import measures as M5

    fail_x = "FAILED tests/test_a.py::test_x - AssertionError\n" + _summary("1 failed, 3 passed")
    fail_y = "FAILED tests/test_a.py::test_y - AssertionError\n" + _summary("1 failed, 3 passed")
    no_test = "ImportError while loading conftest\n" + _summary("no tests ran")
    for M in (M4, M5):
        # step24 000123: the baseline executed no test -- no baseline, regressions are not applicable (item 23)
        assert M._regressed(fail_x, None, [(1, "pytest", no_test)]) is None
        assert M._regressed(fail_x, None, []) is None
        # another test failing than the baseline's: a regression (count comparison would have said none)
        assert M._regressed(fail_y, None, [(1, "pytest", fail_x)]) is True
        # a failure the output does not name is new
        assert M._regressed(_summary("1 failed, 3 passed"), None, [(1, "pytest", fail_x)]) is True
        # must keep: the same test failing before and after is no regression; a clean run neither
        assert M._regressed(fail_x, None, [(1, "pytest", fail_x)]) is False
        assert M._regressed(_summary("4 passed"), None, [(1, "pytest", fail_x)]) is False
        # a reverse-applied patch is the change put away (R3), as git stash is
        assert M.on_stash("git apply -R /tmp/p.diff && python -m pytest tests/test_a.py; git apply /tmp/p.diff")
        assert M.on_stash("git stash && pytest tests/test_a.py; git stash pop") and not M.on_stash("pytest tests/test_a.py && git stash list")


# ---- speckit_sdd: the existing tests related to the change, before and after (R7, the new speckit_sdd.exec kind) ------
def _sdd(related):
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.speckit_sdd import selftest_golden as SG
    from recipe.grpo.qwen3_5.workflows.speckit_sdd.reward.eval import Evaluation

    rub = G.with_docs(Evaluation().rubric, Path(SG.__file__).parent)
    run, col = SG.golden(rub)
    col.related_tests = related
    res = engine.evaluate(rub, run, col).results
    return {k.rsplit(".", 1)[1]: res[f"speckit_sdd.implement.run.exec_evidence.{k.rsplit('.', 1)[1]}"].status for k in ("x.baseline", "x.after_change")}


def test_speckit_sdd_wants_a_run_of_the_tests_related_to_the_change():
    # must keep: the golden runs tests/test_text.py, the test module of strkit/text.py, before and after its change
    assert _sdd({"strkit/text.py": ["tests/test_text.py"]}) == {"baseline": "pass", "after_change": "pass"}
    # a run of other tests than the ones of the changed code is no such run (R7)
    assert _sdd({"strkit/text.py": ["tests/test_other_module.py"]}) == {"baseline": "fail", "after_change": "fail"}
    # offline (no listing): the test modules named after the changed file that the run saw near it (D5 of the 11-25
    # merge): the golden's tests/test_text.py
    assert _sdd(None) == {"baseline": "pass", "after_change": "pass"}


# ---- speckit_bug: a check is seen failing before the change, by its own run (R4) ---------------------------------------
def test_speckit_bug_holds_the_check_to_failing_before_the_change():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import test_speckit_bug_verdict_rules as V

    from recipe.grpo.qwen3_5.workflows.speckit_bug import selftest_golden as G

    _, status = V._score(V._actions())
    item = "speckit_bug.fix.run.speckit_bug_check_scripts.before_change"
    assert status[item] == "pass"  # must keep: the golden's check fails before the change
    acts = V._actions()
    first = next(i for i, a in enumerate(acts) if a.kind == "shell" and a.command == G.CHECK_CMD)
    a = acts[first]
    acts[first] = Action("shell", a.name, command=a.command, observation="all 12 checks ok\n[The command completed with exit code 0.]")
    _, status = V._score(acts)
    assert status[item] == "fail"  # run before the change, but passing: not the check seen failing (02-fix.md:32)
    assert status["speckit_bug.fix.fix.speckit_bug_checks_added.before_run"] == "fail"  # the report's "fail" is not what it printed
