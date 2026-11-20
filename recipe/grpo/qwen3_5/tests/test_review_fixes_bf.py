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
