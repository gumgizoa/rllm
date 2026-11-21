"""Item-rule and document fixes of groups A and C (tasks/2026-11-20-agentos-bugfix-reward-fixes/05-A-C-계획.md): how a
failing test is handled, and the files tasks.md plans to change. Checked on small synthetic artifacts and runs; every new
parameter of shared code is also shown to leave the default behaviour as it was.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from recipe.grpo.qwen3_5.workflows.agentos_bugfix import derive_rubric as D  # noqa: E402

WF = RECIPE / "workflows" / "agentos_bugfix"
RUBRIC = yaml.safe_load((WF / "reward" / "rubric.yaml").read_text(encoding="utf-8"))
ITEMS = {it["id"].removeprefix("agentos_bugfix."): it for it in RUBRIC["items"]}
IT_DOC = (WF / "docs" / "commands" / "implement-tasks" / "implement-tasks.md").read_text(encoding="utf-8")


def _item_params(suffix: str) -> dict:
    return next(it["check"]["params"] for i, it in ITEMS.items() if i.endswith(suffix))


def _item(params: dict, ref: str = "tasks", state: str = "final", iid: str = "x", stage: str = "implement_tasks"):
    return SimpleNamespace(id=iid, stage=stage, check=SimpleNamespace(params=params), target=SimpleNamespace(ref=ref, state=state, type="artifact"))


# ---- A-6: a test the run wrote is corrected, never loosened -----------------------------------------------------------


def test_implement_tasks_says_a_test_you_wrote_is_corrected_not_loosened():
    line = next(ln for ln in IT_DOC.splitlines() if "instead of ticking it, and go on." in ln)
    assert line.endswith("A test you wrote is wrong only when it checks something the task does not ask for: then correct what it checks. "
                         "Never make a failing test pass by loosening or removing what it checks.")
    # the T5 quotes of the derived items are still found in that line
    assert D._T5_FIX in line and D._T5_WARN in line


# ---- C-2: no penalty item reads the task's reference fix ---------------------------------------------------------------


def test_the_two_reference_fix_items_are_gone_and_nine_penalty_items_remain():
    pen = [i for i in ITEMS if ".penalty." in i]
    assert len(pen) == 9
    assert not any(i.endswith(("named_covers_gold", "patch_covers_gold")) for i in pen)
    assert {i for i in pen if ".plan_files." in i} == {"global.penalty.plan_files.named", "global.penalty.plan_files.named_equals_patch"}
    # the task still reaches the kinds that read its description (task_text.py)
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty

    task = SimpleNamespace(id="t")
    assert penalty.inputs(task, None) == {"task": task}


# ---- C-1: every sub-task that changes code names its file's path on its task line ----------------------------------


def test_which_task_lines_change_code():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty as P

    md = "\n".join([
        "- [x] 1.0 Complete the fix in pkg/a.py",
        "  - [x] 1.1 Write 2-8 focused tests in tests/test_a.py",
        "  - [x] 1.2 Change the parser in pkg/a.py",
        "    - Reuse pattern from: pkg/b.py",
        "  - [x] 1.3 Run tests in tests/test_a.py",  # the dot of a file name no longer ends the phrase: a test task
        "  - [x] 1.4 Review how pkg/c.py calls the parser",  # reading
        "  - [x] 1.5 Verify the edge case",  # checking
        "  - [x] **1.6** Update the docstring",  # a bold number is a number
        "    - [x] 1.6.1 Rewrite the summary in pkg/a.py",  # a step of 1.6, not a sub-task of its own
    ])
    assert P.change_lines(md) == ["Change the parser in pkg/a.py", "Update the docstring"]


def test_named_needs_a_path_on_every_change_line_and_reads_the_last_tasks_md():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty as P

    one = "- [ ] 1.2 Change parse in pkg/a.py\n- [ ] 1.3 Update the caller\n"
    lines, _ = P.named_files([(10, one)], {}, "/testbed", set())
    assert lines == [{"pkg/a.py"}, set()] and P.judge(lines, {"pkg/a.py"}, ["pkg/a.py"])["named"] == 0.0
    both = "- [ ] 1.2 Change parse in pkg/a.py\n- [ ] 1.3 Update the caller in `pkg/b.py`\n"
    lines, _ = P.named_files([(10, one), (12, both)], {"pkg/b.py": 20}, "/testbed", set())
    assert P.judge(lines, {"pkg/a.py", "pkg/b.py"}, ["pkg/a.py", "pkg/b.py"]) == {"named": 1.0, "named_equals_patch": 1.0}
    # a file name without its path is no path unless the file is at the repository's top level; any extension counts
    assert P.line_paths("Change parse in slug.py", "/testbed", set()) == set()
    assert P.line_paths("Describe sep in README.rst and docs/usage.rst", "/testbed", {"README.rst"}) == {"README.rst", "docs/usage.rst"}
    # no sub-task that changes code: nothing named
    assert P.judge([], set(), ["pkg/a.py"]) == {"named": 0.0, "named_equals_patch": 0.0}


# ---- R1: failure units, test by test where the output names the failed tests ----------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric import results as R  # noqa: E402


def _r(step, passed, *keys, sel=(), ids=(), runner=True):
    return R.TestResult(step, passed, runner, keys or (R.WHOLE,), tuple(sel), tuple(ids))


def test_failed_ids_drop_a_section_header_name_that_a_full_id_names_and_need_the_whole_count():
    out = "FAILED lib/t/test_image.py::test_huge[png] - AssertionError\n___ test_huge[png] ___\n1 failed, 3 passed"
    assert R.run_failed_ids(1, 0, out) == ("lib/t/test_image.py::test_huge[png]",)
    assert R.run_failed_ids(2, 0, out) == ()  # fewer ids than failures: judged by its files
    assert R.run_failed_ids(0, 0, out) == ()


def test_a_failure_with_ids_is_one_unit_per_test_else_one_per_file():
    fail = _r(10, False, "tests/test_a.py", ids=("tests/test_a.py::test_x", "tests/test_a.py::test_y"))
    assert R.failure_units(fail) == [("test", "tests/test_a.py::test_x"), ("test", "tests/test_a.py::test_y")]
    assert R.failure_units(_r(10, False, "tests/test_a.py")) == [("key", "tests/test_a.py")]
    assert R.failure_units(_r(10, False, "/s/check.py", runner=False)) == [("key", "/s/check.py")]
    assert R.failure_units(_r(10, True, "tests/test_a.py")) == []


def test_runs_test_reads_targets_ids_k_deselect_ignore_and_m():
    tid = "tests/test_a.py::test_x[1]"
    assert R.runs_test(_r(1, True, "tests/test_a.py"), tid)
    assert R.runs_test(_r(1, True, "tests"), tid) and R.runs_test(_r(1, True), tid)
    assert not R.runs_test(_r(1, True, "tests/test_b.py"), tid)
    assert R.runs_test(_r(1, True, "tests/test_a.py", sel=("tests/test_a.py::test_x",)), tid)  # the failed test picked out
    assert R.runs_test(_r(1, True, "tests/test_a.py", sel=("/testbed/tests/test_a.py::test_x[1]",)), tid)
    assert not R.runs_test(_r(1, True, "tests/test_a.py", sel=("tests/test_a.py::test_y",)), tid)
    assert R.runs_test(_r(1, True, "tests/test_a.py", sel=("-k test_x",)), tid)
    assert not R.runs_test(_r(1, True, "tests/test_a.py", sel=("-k not test_x",)), tid)  # left out
    assert R.runs_test(_r(1, True, "tests/test_a.py", sel=("-k (x or y) and not z",)), tid)
    assert not R.runs_test(_r(1, True, "tests/test_a.py", sel=("-k x == y",)), tid)  # cannot be read: left out
    assert not R.runs_test(_r(1, True, "tests", sel=("--deselect tests/test_a.py::test_x",)), tid)
    assert not R.runs_test(_r(1, True, "tests", sel=("--ignore tests/test_a.py",)), tid)
    assert R.runs_test(_r(1, True, "tests", sel=("--ignore tests/test_b.py",)), tid)
    assert not R.runs_test(_r(1, True, "tests/test_a.py", sel=("-m slow",)), tid)
    assert not R.runs_test(_r(1, True, "/s/check.py", runner=False), tid)
    # a dotted label above a unittest id
    assert R.runs_test(_r(1, True, "queries.test_q"), "queries.test_q.QTests.test_x")
    assert not R.runs_test(_r(1, True, "queries.test_q.QTests.test_y"), "queries.test_q.QTests.test_x")


def test_standing_units_rerunning_the_failed_test_clears_it_and_leaving_it_out_does_not():
    ids = ("tests/test_a.py::test_x",)
    fail = _r(10, False, "tests/test_a.py", ids=ids)
    assert R.standing_units([fail, _r(12, True, "tests/test_a.py", sel=("tests/test_a.py::test_x",))]) == []  # A-7 row 8
    left = R.standing_units([fail, _r(12, True, "tests/test_a.py", sel=("--deselect tests/test_a.py::test_x",))])
    assert [u for u, _ in left] == [("test", "tests/test_a.py::test_x")]  # A-2
    # the old rule (kept for the other workflows) does not clear a narrowed rerun
    assert R.standing_failures([fail, _r(12, True, "tests/test_a.py", sel=("tests/test_a.py::test_x",))]) == ["tests/test_a.py"]
    # a whole-file failure without ids, then a narrowed failure and a narrowed pass: the whole failure still stands
    whole = _r(10, False, "tests/test_a.py")
    narrow_f = _r(11, False, "tests/test_a.py", sel=("tests/test_a.py::test_x",))
    narrow_p = _r(12, True, "tests/test_a.py", sel=("tests/test_a.py::test_x",))
    assert [u for u, _ in R.standing_units([whole, narrow_f, narrow_p])] == [("key", "tests/test_a.py")]
    assert R.standing_units([whole, narrow_f, narrow_p, _r(13, True, "tests/test_a.py")]) == []
    # at one step a failure is read last; `until` stops the reading
    assert [u for u, _ in R.standing_units([_r(10, True, "tests/test_a.py"), fail])] == [("test", ids[0])]
    assert R.standing_units([fail, _r(12, True, "tests")], until=11)[0][1] is fail


# ---- helpers: the golden run with steps put in, scored by the engine; the context the items saw ---------------------


def _golden_rubric():
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G

    rub = G.with_docs(S.load(WF / "reward" / "rubric.yaml"), WF)
    assert G.load_plugins(rub) == []
    return rub


def _golden_with(variant=None, insert=None, edit=None):
    """The golden run (or a variant) with ``insert(steps) -> steps`` applied to its list of steps (renumbered after),
    and ``edit(collected)`` to what was collected; (rubric, report, ctx)."""
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric.generator.mutations import simulate
    from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Run, Step
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    rub = _golden_rubric()
    run, col = golden.golden(rub, variant=variant)
    if insert is not None:
        steps = insert(list(run.steps))
        run = Run(instance_id=run.instance_id, steps=[Step(n, st.actions, st.message) for n, st in enumerate(steps, 1)])
        base = {"README.md": golden.README, "setup.cfg": golden.SETUP_CFG, "docs/index.rst": golden.DOCS_INDEX, "textkit/__init__.py": golden.INIT_PY, "textkit/slug.py": golden.SLUG_PY}
        col = simulate(run, workdir=golden.WORKDIR, base_sha=golden.BASE_SHA, base_tree=golden.BASE_TREE, artifact_dirs=(golden.SPECS,), base_files=base)
    if edit is not None:
        edit(col)
    got = {}
    orig = engine.evaluate_item

    def capture(item, ctx, errors):
        got["ctx"] = ctx
        return orig(item, ctx, errors)

    engine.evaluate_item = capture
    try:
        rep = engine.evaluate(rub, run, col)
    finally:
        engine.evaluate_item = orig
    assert not rep.engine_errors, rep.errors[:2]
    return rub, rep, got["ctx"]


def _shell(command, observation, code):
    from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Step
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    return Step(0, [Action("shell", "terminal", command=command, observation=observation + "\n" + golden._exit(code))], "")


def _create(path, text):
    from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Step

    return Step(0, [Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}")], "")


def _after(steps, pred, *new):
    """``steps`` with ``new`` put right after the first step whose action satisfies ``pred``."""
    at = next(i for i, st in enumerate(steps) if any(pred(a) for a in st.actions))
    return steps[: at + 1] + list(new) + steps[at + 1 :]


# ---- A-9 row 8 (R3): a script outside checks/ is no test --------------------------------------------------------------


def test_a_script_outside_checks_is_no_result_and_writing_it_no_test_edit():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty_tests as T

    slug_edit = lambda a: a.kind == "replace" and (a.path or "").endswith("textkit/slug.py")  # noqa: E731
    repro = [_create("/tmp/repro.py", "from textkit import slugify\nassert slugify('a!') == 'a'\n"),
             _shell("cd /testbed && python /tmp/repro.py", "Traceback (most recent call last):\nAssertionError", 1)]
    _, _rep, ctx = _golden_with(insert=lambda s: _after(s, slug_edit, *repro))
    tl = T.timeline(ctx)
    steps = {st.n for st in ctx.run.steps if any("/tmp/repro.py" in (a.command or a.path or "") for a in st.actions)}
    assert len(steps) == 2 and not steps & {r.step for r in tl.results} and not steps & set(tl.test_edits)
    assert all(v == 1.0 for k, (v, _) in T.judge(tl).items())


# ---- A-9 row 20: a run of only the run's own tests is no run of the existing tests -----------------------------------


def test_a_run_of_only_added_test_functions_or_created_test_files_is_no_existing_run():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty_tests as T

    ctx = SimpleNamespace(collected=SimpleNamespace(diff={"tests/test_new.py": "A", "tests/test_slug.py": "M"}, base_present=None, workdir="/testbed"), facts=SimpleNamespace(_created={}))
    run = lambda seg: SimpleNamespace(segment=seg)  # noqa: E731
    added = {"test_sep_kw", "TestSep"}
    slug = ("tests/test_slug.py",)
    assert T.only_own_tests(ctx, run("python -m pytest tests/test_slug.py::test_sep_kw -q"), slug, False, added)
    assert T.only_own_tests(ctx, run("pytest /testbed/tests/test_slug.py::TestSep::test_a[1]"), slug, False, added)
    assert not T.only_own_tests(ctx, run("pytest tests/test_slug.py::test_sep_kw tests/test_slug.py::test_old"), slug, False, added)
    assert not T.only_own_tests(ctx, run("pytest tests/test_slug.py"), slug, False, added)  # the whole module: its existing tests too
    assert not T.only_own_tests(ctx, run("pytest tests/test_slug.py::test_sep_kw tests/test_wrap.py"), slug + ("tests/test_wrap.py",), False, added)
    assert T.only_own_tests(ctx, run("pytest tests/test_new.py"), ("tests/test_new.py",), False, added)  # a test file the run created
    assert not T.only_own_tests(ctx, run("pytest"), (), True, added)  # the whole suite


# ---- R2 and A-3: failures the documents do not ask the run to fix ------------------------------------------------------


def test_implement_tasks_says_the_expected_failure_is_listed_under_failed_tests_as_one():
    assert ("leave your change as it is and list that test under Failed Tests in the final verification report, noting that it is an "
            "expected failure (it asserts the behavior the task asks to change).") in IT_DOC.replace("\n", " ")
    quotes = [s["quote"] for s in ITEMS["implement_tasks.tasks.agentos_bugfix_tasks.ticked_passing"]["sources"]]
    assert D._T1_EXPECTED in quotes
    # the report written as the document says always carries the third wording
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    assert any(rx.search("noting that it is an expected failure") for rx in C.EXPECTED_WORDS)


def _penalty_of(rep):
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty

    got = penalty.post(rep)
    return got["penalty"], {k.split(".penalty.", 1)[1] for k, v in got.items() if ".penalty." in k and not k.startswith("penalty") and v == 0.0}


def test_an_existing_test_of_the_old_behaviour_left_failing_and_reported_as_such_is_excused():
    _, rep, ctx = _golden_with("expected_failure")
    assert _penalty_of(rep) == (1.0, set())
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    tid = golden.EDGE_TEST[0]
    assert C.reported_as_expected(ctx, tid)
    # the report names it but gives no reason: the failure stands, the four items are lost as before
    def plain(col):
        path = next(p for p in col.files if p.endswith("final-verification.md"))
        col.files[path] = col.files[path].replace("It asserts the edge hyphen this task removes, so the change was left as it is.", "The change was left as it is.")

    _, rep, ctx = _golden_with("expected_failure", edit=plain)
    assert not C.reported_as_expected(ctx, tid)
    pen, zero = _penalty_of(rep)
    assert {"phase2_fail.edited_after_fail", "phase2_fail.last_result_pass", "phase3_fail.last_result_pass"} <= zero


def test_a_failure_the_change_stashed_away_also_shows_is_excused_and_one_it_does_not_is_not():
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    tid = "tests/test_a.py::test_x"
    fail = R.TestResult(10, False, True, ("tests/test_a.py",), (), (tid,))
    ctx = SimpleNamespace(cache={"agentos_v2.stashed_results": [R.TestResult(12, False, True, ("tests/test_a.py",), (), (tid,))]},
                          collected=SimpleNamespace(workdir="/testbed", diff={}, base_present=None, files={}), facts=SimpleNamespace(_created={}, repo_writes=[]),
                          rubric=SimpleNamespace(artifacts={}))
    assert C.excused_failures(ctx, [(("test", tid), fail)]) == {("test", tid)}
    assert C.excused_failures(ctx, [(("test", "tests/test_a.py::test_y"), fail)]) == set()
    ctx.cache["agentos_v2.stashed_results"] = [R.TestResult(12, False, True, ("tests",))]
    assert C.excused_failures(ctx, [(("key", "tests/test_a.py"), fail)]) == {("key", "tests/test_a.py")}
    ctx.cache["agentos_v2.stashed_results"] = [R.TestResult(12, True, True, ("tests",))]
    assert C.excused_failures(ctx, [(("key", "tests/test_a.py"), fail)]) == set()


# ---- A-4 and A-9 row 7: one or two attempts at a failure, never three ------------------------------------------------


def _p2(results, src=(10,), test_edits=(), group_ends=(), p2_end=40, **kw):
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty_tests as T

    got = T.judge(T.Timeline(src=list(src), test_edits=list(test_edits), results=list(results), group_ends=list(group_ends), p2_end=p2_end, **kw))
    return {k.split(".penalty.", 1)[1]: v for k, v in got.items()}


def test_attempts_at_a_failure_while_implementing():
    edited = "phase2_fail.edited_after_fail"
    tid = "tests/test_a.py::test_x"
    f = lambda s: _r(s, False, "tests/test_a.py", ids=(tid,))  # noqa: E731
    ok = lambda s: _r(s, True, "tests/test_a.py")  # noqa: E731
    # fixed and passing after one attempt; two attempts that do not pass, then go on (⚠️)
    assert _p2([f(12), ok(14)], src=(10, 13))[edited] == (1.0, True)
    assert _p2([f(12), f(14), f(16)], src=(10, 13, 15))[edited] == (1.0, True)
    # a third attempt is beyond the document, whether it passes or not
    assert _p2([f(12), f(14), f(16), ok(18)], src=(10, 13, 15, 17))[edited] == (0.0, True)
    # no attempt: not fixed, or fixed and not run again (an edit right before the mark)
    assert _p2([f(12)], src=(10,))[edited] == (0.0, True)
    assert _p2([f(12)], src=(10,), test_edits=(13,))[edited] == (0.0, True)
    # a test written first fails before the code it tests: that failure asks for no fix
    script = lambda s, p: _r(s, p, "/s/checks/c.py", runner=False)  # noqa: E731
    assert _p2([script(12, True), script(14, False), script(16, True)], src=(10, 15), group_ends=(13,))[edited] == (1.0, True)
    # each stretch on its own: a failure of group 1 left there is not fixed by group 2's attempts
    assert _p2([f(12), f(22), ok(24)], src=(10, 20, 23), group_ends=(15,))[edited] == (0.0, True)
    # a run of the same call after its write is a run after the edit
    assert _p2([f(12), ok(14)], src=(10, 14), results_late={14})[edited] == (1.0, True)


# ---- A-9 row 17: a failure passes again inside its own task group, or the group is marked ⚠️ -----------------------


def test_a_failure_left_when_its_group_is_ticked_is_not_undone_by_a_later_group():
    last = "phase2_fail.last_result_pass"
    f = lambda s: _r(s, False, "/s/checks/a.py", runner=False)  # noqa: E731
    ok = lambda s: _r(s, True, "/s/checks/a.py", runner=False)  # noqa: E731
    # group 1 (ends 15) leaves a.py failing; it passes only in group 2's stretch
    assert _p2([f(12), ok(22)], src=(10, 20), group_ends=(15, 30))[last] == (0.0, True)
    assert _p2([f(12), ok(14)], src=(10, 13), group_ends=(15, 30))[last] == (1.0, True)
    # ... unless group 1 is marked ⚠️
    assert _p2([f(12), ok(22)], src=(10, 20), group_ends=(15, 30), group_marked={15: True})[last] == (1.0, True)
    # everything ticked in one write: one stretch, as before
    assert _p2([f(12), ok(22)], src=(10, 20), group_ends=(30,))[last] == (1.0, True)


# ---- A-7 row 8 and A-2 (PHASE 2): picking the failed test out clears it, leaving it out does not ---------------------


def test_a_narrowed_rerun_of_the_failed_test_clears_it_and_one_that_leaves_it_out_does_not():
    last = "phase2_fail.last_result_pass"
    tid = "tests/test_a.py::test_x"
    fail = _r(12, False, "tests/test_a.py", ids=(tid,))
    picked = _r(14, True, "tests/test_a.py", sel=(tid,))
    left_out = _r(14, True, "tests/test_a.py", sel=(f"--deselect {tid}",))
    assert _p2([fail, picked], src=(10, 13))[last] == (1.0, True)
    assert _p2([fail, left_out], src=(10, 13))[last] == (0.0, True)
    # a failure the output named no test of: the file has to pass again, not one test of it
    whole = _r(12, False, "tests/test_a.py")
    assert _p2([whole, picked], src=(10, 13))[last] == (0.0, True)
    assert _p2([whole, _r(14, True, "tests")], src=(10, 13))[last] == (1.0, True)


# ---- A-1 and A-2 (PHASE 3): every failure is judged, not the last run ---------------------------------------------------


def _p3(results, src=(10,), **kw):
    kw.setdefault("p2_end", 30)
    kw.setdefault("p3", 30)
    kw.setdefault("report", 50)
    return _p2(results, src=src, **kw)


def test_the_last_run_of_phase_3_does_not_decide():
    last = "phase3_fail.last_result_pass"
    a, b = "tests/test_a.py::test_x", "tests/test_b.py::test_y"
    full = _r(32, False, "tests", ids=(a, b))
    stash = [_r(33, False, "tests", ids=(a, b))]  # both fail without the change as well: not the change's
    own = _r(34, True, "/s/checks/c.py", runner=False)
    # the whole suite last, or the run's own test last: the same verdict (both failures were there before the change)
    pre = {("test", a), ("test", b)}  # what checks.excused_failures finds from those stashed runs (R2)
    assert _p3([full], stash_results=stash, check_runs=[33], excused=pre)[last] == (1.0, False)
    assert _p3([full, own], stash_results=stash, check_runs=[33], excused=pre)[last] == (1.0, False)
    # never checked: the failures stand whatever ran last
    assert _p3([full, own])[last] == (0.0, True)
    # left out of a later passing run: still standing (A-2)
    assert _p3([full, _r(36, True, "tests", sel=(f"--deselect {a}", f"--deselect {b}"))])[last] == (0.0, True)
    # the change causes one (it passes with the change stashed away): fixed once and run again, still failing -- reported
    caused = [_r(33, True, "tests/test_a.py")]
    one = _r(32, False, "tests/test_a.py", ids=(a,))
    assert _p3([one, _r(36, False, "tests/test_a.py", ids=(a,))], src=(10, 35), stash_results=caused, check_runs=[33])[last] == (1.0, True)
    assert _p3([one], src=(10,), stash_results=caused, check_runs=[33])[last] == (0.0, True)  # not fixed
    assert _p3([one], src=(10, 35), stash_results=caused, check_runs=[33])[last] == (0.0, True)  # fixed, not run again


# ---- A-9 row 22: each failure the change causes is fixed; the ones that were there before are not asked -------------


def test_each_failure_the_change_causes_is_fixed_by_a_source_change():
    edited = "phase3_fail.edited_after_fail"
    a, b = "tests/test_a.py::test_x", "tests/test_b.py::test_y"
    both = _r(32, False, "tests", ids=(a, b))
    # a passes without the change (the change causes it), b fails without it as well (there before: R2)
    stash = [_r(33, False, "tests", ids=(b,))]
    kw = dict(stash_results=stash, check_runs=[33], excused={("test", b)})
    assert _p3([both], src=(10,), **kw)[edited] == (0.0, True)  # a not fixed
    assert _p3([both], src=(10,), test_edits=(34,), test_edits_of={"tests/test_a.py": [34]}, **kw)[edited] == (0.0, True)  # an existing test: only a source change fixes it
    assert _p3([both], src=(10, 35), **kw)[edited] == (1.0, True)
    # nothing the change causes: not judged
    assert _p3([both], src=(10,), stash_results=[_r(33, False, "tests", ids=(a, b))], check_runs=[33], excused={("test", a), ("test", b)})[edited] == (1.0, False)
    # a check script of the run's own: its own edit fixes it
    own = _r(32, False, "/s/checks/c.py", runner=False)
    assert _p3([own], src=(10,), test_edits=(34,), test_edits_of={"/s/checks/c.py": [34]})[edited] == (1.0, True)


# ---- report items (A-2, A-7 row 7, A-8) -----------------------------------------------------------------------------


def _report_rule(rule, runs, report_text, **params):
    """``agentos_v2.report`` rule ``rule`` on PHASE 3 runs ``runs`` and the report ``report_text``."""
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    ctx = SimpleNamespace(collected=SimpleNamespace(workdir="/testbed"), artifact_text=lambda aid, state="final": report_text, cache={})
    orig = C.comparison_runs
    C.comparison_runs = lambda ctx, after_fix=False, fallback=False: runs
    try:
        return C.report(_item({"rule": rule, "suite_section": "2. Test Suite Results", **params}, ref="final_verification"), ctx)
    finally:
        C.comparison_runs = orig


def _run(step, segment, failed=0, passed=5, observation="", targets=("tests/test_a.py",)):
    return SimpleNamespace(step=step, segment=segment, command=segment, targets=list(targets), failed=failed, errors=0, passed=passed, skipped=0, collected=passed + failed, observation=observation)


REPORT = """# Verification Report

## 2. Test Suite Results

**Status:** ✅ All Passing

### Test Summary
- **Total Tests:** 5
- **Passing:** 5
- **Failing:** 0
- **Errors:** 0

### Failed Tests
None - all tests passing

### Notes
{notes}
"""


def test_all_passing_needs_no_failure_left_standing():
    fail = _run(10, "pytest tests/test_a.py", failed=1, passed=4, observation="FAILED tests/test_a.py::test_x - assert 1\n1 failed, 4 passed")
    left_out = _run(12, "pytest tests/test_a.py --deselect tests/test_a.py::test_x", passed=4)
    rerun = _run(12, "pytest tests/test_a.py::test_x", passed=1)
    text = REPORT.format(notes="")
    assert _report_rule("suite_status", [fail, left_out], text).status == "pass"  # the best match alone: as before
    assert _report_rule("suite_status", [fail, left_out], text, standing=True).status == "fail"
    assert _report_rule("suite_status", [fail, rerun], text, standing=True).status == "pass"
