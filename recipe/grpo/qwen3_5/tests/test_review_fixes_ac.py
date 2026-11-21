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
