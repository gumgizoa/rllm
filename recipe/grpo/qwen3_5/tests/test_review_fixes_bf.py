"""Item-rule and document fixes of groups B and F (tasks/2026-11-20-agentos-bugfix-reward-fixes/04-B-F-계획.md) and the
deferred D-6 rows 12 and 21, checked on small synthetic artifacts and runs. Every new parameter of shared code is also
shown to leave the default behaviour as it was.
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
from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C  # noqa: E402

WF = RECIPE / "workflows" / "agentos_bugfix"
RUBRIC = yaml.safe_load((WF / "reward" / "rubric.yaml").read_text(encoding="utf-8"))
ITEMS = {it["id"].removeprefix("agentos_bugfix."): it for it in RUBRIC["items"]}


def _item_params(suffix: str) -> dict:
    return next(it["check"]["params"] for i, it in ITEMS.items() if i.endswith(suffix))


def _item(params: dict, ref: str = "tasks", state: str = "final", iid: str = "x", stage: str = "implement_tasks"):
    return SimpleNamespace(id=iid, stage=stage, check=SimpleNamespace(params=params), target=SimpleNamespace(ref=ref, state=state, type="artifact"))


# ---- F-1: the implement-tasks read of spec.md and requirements.md is not scored -----------------------------------


def test_the_implement_stage_spec_read_is_dropped():
    assert "implement_tasks.run.agentos_bugfix_read.spec_inputs" not in ITEMS
    assert "create_tasks.run.agentos_bugfix_read.spec_inputs" in ITEMS


# ---- F-3, decision 1: implement-tasks no longer says a task group may write no tests ------------------------------


def test_implement_tasks_says_every_implementation_group_writes_its_tests_first():
    it = (WF / "docs" / "commands" / "implement-tasks" / "implement-tasks.md").read_text(encoding="utf-8")
    assert "(if any" not in it.split("## Self-verify")[1].split("## Next step")[0]
    assert "each implementation task group writes them first, as its x.1 sub-task;" in it
    src = next(s for s in ITEMS["implement_tasks.run.agentos_bugfix_checks.pass_last"]["sources"] if "Running the tests" in s["quote"])
    assert "each implementation task group writes them first" in src["quote"]


# ---- B-6 row 5: create-tasks says tasks.md keeps its three sections ----------------------------------------------


def test_create_tasks_says_the_sections_stay_and_the_section_item_cites_it():
    ct = (WF / "docs" / "commands" / "create-tasks" / "create-tasks.md").read_text(encoding="utf-8")
    assert "every tasks.md keeps the example's three sections" in ct
    quotes = [s["quote"] for s in ITEMS["create_tasks.tasks.section_present.execution_order"]["sources"]]
    assert D.KEEP_SECTIONS_QUOTE in quotes


# ---- B-2: create-tasks' format items read tasks.md as create-tasks left it -----------------------------------------


def test_create_tasks_format_items_read_the_stage_end_file():
    for i, it in ITEMS.items():
        if i.startswith("create_tasks.tasks.") and it["check"]["kind"] != "unimplemented":
            want = "final" if i.endswith(".artifact_exists") else "stage_end"
            assert it["target"]["state"] == want, i


# ---- B-4: a task split finer than the example is in format ----------------------------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.checks import artifacts as A  # noqa: E402

FINER = """## Task List
#### Task Group 1: Fix
- [ ] 1.0 Complete the fix
  - [ ] 1.1 Write 2-8 focused tests
    - [ ] Test the empty input
    - [ ] Test the long input
  - [ ] 1.2 Change parse in src/a.py
    - [ ] 1.2.1 Handle the empty input
  - [ ] 1.3 Ensure the tests of this group pass
"""


def _ctx_text(text):
    return SimpleNamespace(artifact_text=lambda aid, state="final": text)


def test_finer_numbers_and_steps_under_a_task_line_are_in_format():
    p = _item_params("create_tasks.tasks.item_format.checkbox_lines")
    assert A.item_format(_item(p), _ctx_text(FINER)).score == 1.0
    top = FINER + "- [ ] Clean up afterwards\n"  # an unnumbered checkbox at the top level is still out of format
    r = A.item_format(_item(p), _ctx_text(top))
    assert r.status == "fail" and round(r.score, 4) == round(7 / 8, 4)


def test_nested_under_off_keeps_item_format_as_it_was():
    p = {k: v for k, v in _item_params("create_tasks.tasks.item_format.checkbox_lines").items() if k != "nested_under"}
    r = A.item_format(_item(p), _ctx_text(FINER))
    assert r.status == "fail" and round(r.score, 4) == round(5 / 7, 4)  # the two unnumbered steps
    p["pattern"] = D.BOX_NEW
    assert round(A.item_format(_item(p), _ctx_text(FINER)).score, 4) == round(4 / 7, 4)  # and 1.2.1


# ---- B-7: every task group has a sub-task ---------------------------------------------------------------------------


def _tasks_rule(text: str, params: dict, state: str = "stage_end"):
    ctx = SimpleNamespace(artifact_text=lambda aid, state="final": text)
    return C.tasks(_item(params, state=state, stage="create_tasks"), ctx)


def test_a_group_without_a_sub_task_is_counted():
    p = _item_params("create_tasks.tasks.item_format.subtasks")
    assert p == {"rule": "group_subtasks"}
    two = "#### Task Group 1: Fix\n- [ ] 1.0 Fix\n  - [ ] 1.1 Write tests\n#### Task Group 2: Verify Documentation Updates\n- [ ] 2.0 Check the docs\n"
    r = _tasks_rule(two, p)
    assert r.status == "fail" and r.score == 0.5
    assert _tasks_rule(two + "  - [ ] 2.1 Read docs/a.rst\n", p).status == "pass"
    assert _tasks_rule("- [ ] 1.1 x\n", p).status == "fail"  # no group heading


# ---- B-3: test_first reads the plan's wording widely ---------------------------------------------------------------


def _groups(*groups):
    return "\n".join(f"#### Task Group {n}: {title}\n- [ ] {n}.0 Do it\n" + "".join(f"  - [ ] {n}.{k} {line}\n" for k, line in enumerate(lines, 1)) for n, (title, lines) in enumerate(groups, 1))


def test_test_first_takes_other_wordings_and_leaves_out_check_and_docs_groups():
    p = _item_params("create_tasks.tasks.agentos_bugfix_tasks.test_first")
    assert p.get("wide_words") is True
    impl = ("Fix the parser", ["Test that the parser keeps the sign", "Change parse in src/a.py", "Test the implementation"])
    verify = ("Test Verification", ["Run tests for tests/test_a.py"])
    docs = ("Update documentation", ["Edit docs/a.rst"])
    assert _tasks_rule(_groups(impl, verify, docs), p).status == "pass"
    assert _tasks_rule(_groups(impl, verify, docs), {"rule": "test_first"}).score < 1.0  # as before: three groups judged, two wordings missed
    details = _groups(("Fix", ["Extend tests in tests/test_a.py", "Change src/a.py", "Make the group pass"])) + "    - Run tests/test_a.py with pytest\n"
    assert _tasks_rule(details, p).status == "pass"  # the run is named in the details of the last sub-task
    code_check = _groups(("Fix", ["Add check for db_table in src/a.py", "Run the tests"]))
    assert _tasks_rule(code_check, p).status == "fail"  # "Add check for ..." is code, not a test
    assert _tasks_rule(code_check, {"rule": "test_first"}).status == "pass"  # as before


def test_wide_words_off_keeps_the_word_lists():
    assert C.writes_tests("Write 2-8 focused tests") and not C.writes_tests("Test that x holds")
    assert C.writes_tests("Test that x holds", wide=True) and not C.writes_tests("Add check for x", wide=True)
    assert C.implementation_group("Test Verification") and not C.implementation_group("Test Verification", wide=True)
    assert not C.implementation_group("Test Review & Gap Analysis")


# ---- B-6 row 3: Total Tasks may count the implementation groups only -------------------------------------------------


def test_total_tasks_may_leave_the_review_group_out():
    p = _item_params("create_tasks.tasks.agentos_bugfix_tasks.total")
    assert p.get("impl_counts") is True
    text = "Total Tasks: {}\n" + _groups(("Fix", ["Write tests", "Change src/a.py", "Run the tests"]), ("Test Review & Gap Analysis", ["Review tests", "Run tests"]))
    # task lines 7, sub-tasks 5, groups 2; the implementation group alone: 4 lines, 3 sub-tasks, 1 group
    for n in (7, 5, 2, 4, 3, 1):
        assert _tasks_rule(text.format(n), p).status == "pass", n
    assert _tasks_rule(text.format(6), p).status == "fail"
    assert _tasks_rule(text.format(3), {"rule": "total"}).status == "fail"  # as before: only the three counts


# ---- F-2: a test function added to an existing test module is the run's own test ------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, WriteEvent  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

ADDED = "    def test_keeps_sign(self):\n        self.assertEqual(parse('-1'), -1)\n"


def _module_ctx(old="    def test_old(self):\n        pass\n", removed=False):
    run = Run("t", [Step(5, [Action("replace", "file_editor", path="/testbed/tests/test_a.py", old=old, text=old + ADDED)]),
                    Step(6, [Action("shell", "terminal", command="cat >> /testbed/tests/test_b.py <<'EOF'\ndef test_b_new():\n    assert 1\nEOF")])])
    writes = [WriteEvent(path="tests/test_a.py", step=5, op="edit", action_index=0, removed_existing=removed),
              WriteEvent(path="tests/test_b.py", step=6, op="append", action_index=0),
              WriteEvent(path="tests/test_new.py", step=7, op="create", content="def test_x():\n    pass\n")]
    facts = SimpleNamespace(repo_writes=writes, _created={"/testbed/tests/test_new.py": 7})
    return SimpleNamespace(run=run, facts=facts, collected=Collected(workdir="/testbed"), cache={})


def test_a_test_function_added_to_an_existing_module_counts():
    mods = C.module_tests(_module_ctx())
    assert mods == {"tests/test_a.py": (5, {"test_keeps_sign"}), "tests/test_b.py": (6, {"test_b_new"})}  # not the new test file
    assert C.module_tests(_module_ctx(removed=True)).keys() == {"tests/test_b.py"}  # an edit that changed an existing line adds none
    assert C.test_names("class TestX:\n    async def test_y(self): ...\n") == {"TestX", "test_y"}


def test_the_checks_items_take_module_tests():
    for suffix in ("agentos_bugfix_checks.written", "agentos_bugfix_checks.before_code", "agentos_bugfix_checks.pass_last"):
        assert _item_params(suffix).get("module_tests") is True, suffix
    first = _item_params("agentos_bugfix_checks.before_code")["window"][1][0]["first"]
    assert first["fact"] == "repo_edit" and first["test_paths"] is False


# ---- F-2: create-tasks need not reread the files the run wrote itself ----------------------------------------------


def test_a_file_written_before_create_tasks_counts_as_read(monkeypatch):
    spec = "/tmp/agent-os/specs/s/spec.md"
    monkeypatch.setattr(C, "_window", lambda item, ctx: (30, 40))
    f = SimpleNamespace(artifact_paths={"spec": spec, "requirements": None}, writes={spec: [WriteEvent(path=spec, step=12, op="create", content="x")]}, n_steps=50)
    ctx = SimpleNamespace(facts=f, run=SimpleNamespace(steps=[]), collected=SimpleNamespace(workdir="/testbed"))
    p = {"artifacts": ["spec", "requirements"], "absent_unread": True}
    r = C.read(_item(dict(p), ref="run"), ctx)
    assert r.status == "fail" and r.score == 0.0  # as before: spec.md not read in the window, requirements.md absent
    r = C.read(_item({**p, "written_before": True}), ctx)
    assert r.status == "fail" and r.score == 0.5  # spec.md is in the conversation; requirements.md was never written (D-4)
    assert _item_params("create_tasks.run.agentos_bugfix_read.spec_inputs").get("written_before") is True


# ---- B-1 / B-8 row 2: ticked_after_work reads file names, path suffixes, reads and work -----------------------------

import pytest  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric.context import CommandFact, Facts  # noqa: E402

TASKS = "/tmp/agent-os/specs/2026-11-13-x/tasks.md"


def _tick_ctx(tasks_writes, repo_writes=(), commands=(), steps=()):
    f = Facts(n_steps=100)
    f.artifact_paths = {"tasks": TASKS}
    f.writes = {TASKS: [WriteEvent(path=TASKS, step=s, op="overwrite" if k else "create", content=c) for k, (s, c) in enumerate(tasks_writes)]}
    f.repo_writes = list(repo_writes)
    f.commands = list(commands)
    final = next((c for _, c in reversed(tasks_writes) if c is not None), "")
    return SimpleNamespace(facts=f, run=Run("t", list(steps)), collected=Collected(workdir="/testbed", files={TASKS: final}), cache={},
                           artifact_text=lambda aid, state="final": final, rubric=SimpleNamespace(artifacts={}))


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setattr(C, "_window", lambda item, ctx: (10, 100))


TICK_PLAN = "#### Task Group 1: Fix\n- [{b}] 1.0 Fix\n  - [{b}] 1.1 Replace subprocess.check_call with subprocess.run\n  - [{b}] 1.2 Add FutureWarning at table.py line 12\n"


def test_code_names_are_not_files_and_a_path_suffix_is_the_same_file(window):
    plan = lambda b: TICK_PLAN.format(b=b)  # noqa: E731
    ctx = _tick_ctx([(5, plan(" ")), (40, plan("x"))], repo_writes=[WriteEvent(path="astropy/table/table.py", step=20, op="edit")])
    p = {"rule": "ticked_after_work"}
    assert C.tasks(_item(dict(p)), ctx).status == "fail"  # as before: subprocess.run and table.py at the top are not found
    assert C.tasks(_item({**p, "name_files": True}), ctx).status == "pass"
    early = _tick_ctx([(5, plan(" ")), (15, plan("x"))], repo_writes=[WriteEvent(path="astropy/table/table.py", step=20, op="edit")])
    r = C.tasks(_item({**p, "name_files": True}), early)
    assert r.status == "fail" and "1.2" in r.detail  # ticked before the file was written; 1.0 and 1.1 had no work either
    assert "1.0" in r.detail


def test_a_reading_task_is_done_by_reading_its_file(window, monkeypatch):
    plan = "#### Task Group 1: Fix\n- [{b}] 1.1 Review `tests/test_a.py`\n"
    ctx = _tick_ctx([(5, plan.format(b=" ")), (40, plan.format(b="x"))])
    monkeypatch.setattr(C, "_repo_reads", lambda ctx, w: [(30, "tests/test_a.py")])
    assert C.tasks(_item({"rule": "ticked_after_work", "name_files": True}), ctx).status == "pass"
    monkeypatch.setattr(C, "_repo_reads", lambda ctx, w: [])
    assert C.tasks(_item({"rule": "ticked_after_work", "name_files": True}), ctx).status == "fail"


def test_a_task_naming_no_file_needs_some_work_before_its_tick(window):
    plan = "#### Task Group 1: Fix\n- [{b}] 1.1 Make the parser keep the sign\n"
    idle = _tick_ctx([(5, plan.format(b=" ")), (40, plan.format(b="x"))])
    assert C.tasks(_item({"rule": "ticked_after_work"}), idle).status == "pass"  # as before: only the tick time
    assert C.tasks(_item({"rule": "ticked_after_work", "name_files": True}), idle).status == "fail"
    worked = _tick_ctx([(5, plan.format(b=" ")), (40, plan.format(b="x"))], commands=[CommandFact(step=30, action_index=0, command="python -c 'import a'", cwd="/testbed")])
    assert C.tasks(_item({"rule": "ticked_after_work", "name_files": True}), worked).status == "pass"


def test_a_tick_after_an_unreplayable_write_is_placed_at_its_earliest_step(window):
    plan = "#### Task Group 1: Fix\n- [{b}] 1.1 Change `src/a.py`\n"
    ctx = _tick_ctx([(5, plan.format(b=" ")), (30, None), (40, plan.format(b="x"))], repo_writes=[WriteEvent(path="src/a.py", step=20, op="edit")])
    assert C.tick_bounds(ctx, "tasks") == {"1.1": (30, 40)}
    assert C.tasks(_item({"rule": "ticked_after_work"}), ctx).status == "fail"  # as before: UNKNOWN
    assert C.tasks(_item({"rule": "ticked_after_work", "name_files": True}), ctx).status == "pass"


# ---- B-8 row 3: some work between one task group's ticks and the next one's -----------------------------------------


def test_groups_ticked_in_a_row_after_all_the_work_fail_with_work_between(window):
    plan = "#### Task Group 1: A\n- [{a}] 1.1 Change `src/a.py`\n#### Task Group 2: B\n- [{b}] 2.1 Change `src/b.py`\n"
    writes = [WriteEvent(path="src/a.py", step=20, op="edit"), WriteEvent(path="src/b.py", step=25, op="edit")]
    batch = _tick_ctx([(5, plan.format(a=" ", b=" ")), (40, plan.format(a="x", b=" ")), (41, plan.format(a="x", b="x"))], repo_writes=writes)
    p = {"rule": "groups_in_order"}
    assert C.tasks(_item(dict(p)), batch).status == "pass"  # as before: the ticks are in group order
    assert C.tasks(_item({**p, "work_between": True}), batch).status == "fail"
    passes = _tick_ctx([(5, plan.format(a=" ", b=" ")), (22, plan.format(a="x", b=" ")), (41, plan.format(a="x", b="x"))], repo_writes=writes)
    assert C.tasks(_item({**p, "work_between": True}), passes).status == "pass"
    warned = _tick_ctx([(5, plan.format(a=" ", b=" ")), (40, plan.format(a="x", b=" ")), (41, plan.format(a="x", b="⚠️"))], repo_writes=writes)
    assert C.tasks(_item({**p, "work_between": True}), warned).status == "pass"  # group 2 marked not done: no work asked for


# ---- B-8 row 1: a test sub-task ticked with no test result of the code it ticks -------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.context import RunFact  # noqa: E402


def _run(step, failed=0, same_call=False):
    return RunFact(step=step, action_index=0, command="python -m pytest tests/test_a.py", segment="python -m pytest tests/test_a.py", runner="pytest",
                   kind="test", valid=True, passed=3, failed=failed, after_write_same_call=same_call)


def _passing_ctx(runs, code=(20,)):
    plan = "#### Task Group 1: Fix\n- [{b}] 1.1 Write tests\n- [{b}] 1.2 Change `src/a.py`\n- [{b}] 1.3 Ensure the tests of this group pass\n"
    ctx = _tick_ctx([(5, plan.format(b=" ")), (40, plan.format(b="x"))], repo_writes=[WriteEvent(path="src/a.py", step=s, op="edit") for s in code])
    ctx.facts.runs = list(runs)
    ctx.collected.diff = {"src/a.py": "M"}
    return ctx


def test_a_test_sub_task_ticked_without_running_the_tests_fails(window):
    p = _item_params("implement_tasks.tasks.agentos_bugfix_tasks.ticked_passing")
    item = _item({k: v for k, v in p.items() if k != "dir"})
    assert C.tasks(item, _passing_ctx([_run(30)])).status == "pass"
    r = C.tasks(item, _passing_ctx([_run(15)]))  # the only run came before the code change
    assert r.status == "fail" and "no test result" in r.detail
    assert C.tasks(item, _passing_ctx([_run(30, failed=1)])).status == "fail"  # as before: ticked over a failure
    assert C.tasks(item, _passing_ctx([_run(20, same_call=True)])).status == "pass"  # sed -i ... && pytest in one call
    assert C.tasks(item, _passing_ctx([_run(20)])).status == "fail"  # the same step without the order known
