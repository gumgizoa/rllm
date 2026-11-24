"""agentos_bugfix / agentos_v2 workflow-code fixes from the 11-23 fresh reward review (crosscheck fix list items 20, 21):
each built from the review's real case, with an input that must keep its reading.

* item 20 (table row 12): a ``git checkout`` of an edited non-test file puts the change away until the run writes the
  repository again -- on the penalty side as on the compliance side, the checked-out file written again included
  (``s23_python__mypy-16781_2``: test-data file checked out at turn 61, written again, suite passed at turn 82).
* item 21 (table row 13): a task group titled like a verification group ("Basic Functionality Verification",
  "Integration Test for ...") whose task lines are all test work is no implementation group
  (``s1_conan-io__conan-10959_6``, ``s23_getmoto__moto-7365_6``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C  # noqa: E402

NAME = "agentos_bugfix"
WF = RECIPE / "workflows" / NAME
ITEMS = {it["id"].removeprefix(NAME + "."): it for it in yaml.safe_load((WF / "reward" / "rubric.yaml").read_text(encoding="utf-8"))["items"]}


def _params(suffix: str) -> dict:
    return next(it["check"]["params"] for i, it in ITEMS.items() if i.endswith(suffix))


# ---- item 20: a checked-out file written again brings the change back ------------------------------------------------


def _golden_with(*commands: str):
    """The golden run with shell commands put in after its second source edit (``replace textkit/slug.py``) and before
    the runner runs that follow it (PHASE 2's ``pytest tests/test_slug.py``, PHASE 3's whole suite)."""
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    rub = G.with_docs(S.load(WF / "reward" / "rubric.yaml"), WF)
    assert G.load_plugins(rub) == []
    run, col = golden.golden(rub, variant=None)
    edits = [n for n, st in enumerate(run.steps) if any(a.kind == "replace" and (a.path or "").endswith("textkit/slug.py") for a in st.actions)]
    at = edits[-1] + 1
    step, action = type(run.steps[0]), type(run.steps[0].actions[0])
    for k, c in enumerate(commands):
        run.steps.insert(at + k, step(0, [action("shell", "terminal", command=c, observation="[Command finished with exit code 0]")], ""))
    for n, st in enumerate(run.steps, 1):
        st.n = n
    return rub, run, col


def _penalty_tests(*commands: str) -> dict[str, float]:
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty

    rub, run, col = _golden_with(*commands)
    rep = engine.evaluate(rub, run, col)
    assert not rep.engine_errors
    return {k.split(".penalty.", 1)[1]: v for k, v in penalty.post(rep).items() if k.startswith("implement_tasks.penalty.")}


def _compliance_runs(*commands: str) -> list[int]:
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext

    rub, run, col = _golden_with(*commands)
    rep = engine.evaluate(rub, run, col)
    ctx = EvalContext(rubric=rub, run=run, collected=col, facts=rep.facts)
    return [int(r.step) for r in C.change_runs(ctx)]


DATA = "cd /testbed && printf 'hello--world\\n' >> textkit/data/edge_cases.txt"  # a repository file neither source nor test
CHECKOUT = "cd /testbed && git checkout textkit/data/edge_cases.txt"


def test_a_checked_out_data_file_written_again_leaves_the_later_runs_with_the_change():
    golden = _penalty_tests()
    assert golden["phase2_run.existing_and_own"] == golden["phase3_run.existing_and_own"] == 1.0
    # s23_python__mypy-16781_2: write a data file, check it out (turn 61), write it again (turn 80), run the suite (82)
    again = _penalty_tests(DATA, CHECKOUT, DATA)
    assert again == golden
    # the compliance side reads the same: every runner run after the second write is a run with the change in place
    golden_runs = _compliance_runs()
    assert _compliance_runs(DATA, CHECKOUT, DATA) == [s if s < golden_runs[1] else s + 3 for s in golden_runs]  # three steps put in


def test_a_checked_out_data_file_not_written_again_still_puts_the_change_away():
    # must keep its reading: without the second write the later runs ran with the change put away, on both sides
    away = _penalty_tests(DATA, CHECKOUT)
    assert away["phase2_run.existing_and_own"] == 0.0 and away["phase3_run.existing_and_own"] == 0.0
    assert len(_compliance_runs(DATA, CHECKOUT)) < len(_compliance_runs())


def test_the_penalty_ends_a_put_away_change_at_the_writes_the_compliance_side_ends_it_at():
    W = SimpleNamespace
    writes = [W(step=34, op="edit", path="mypy/stubgen.py", ok=True), W(step=38, op="unknown", path="mypy/stubgen.py", ok=None),
              W(step=44, op="edit", path="test-data/unit/stubgen.test", ok=True), W(step=66, op="edit", path="test-data/unit/stubgen.test", ok=True),
              W(step=70, op="edit", path="mypy/__pycache__/stubgen.cpython-312.pyc", ok=True), W(step=72, op="edit", path="mypy/x.py", ok=False)]
    ctx = SimpleNamespace(facts=SimpleNamespace(repo_writes=writes))
    # git putting content back (unknown), byproducts and failed writes are no authored write; the test-data write is
    assert C.authored_write_steps(ctx) == [34, 44, 66]
    # mypy's test-data/ is a test file since the shared reading fix (facts.is_test_path), so a checkout of it puts no
    # change away; a data file neither source nor test still does (DATA above)
    assert C.edited_sources(ctx) == {"mypy/stubgen.py"}
    writes[2].path = writes[3].path = "textkit/data/edge_cases.txt"
    assert C.edited_sources(ctx) == {"mypy/stubgen.py", "textkit/data/edge_cases.txt"}


# ---- item 21 (b): verification groups by title and task lines ---------------------------------------------------------


CONAN = """## Task List

### conans/model/info.py Implementation

#### Task Group 1: Add Missing Package ID Mode Methods to PythonRequireInfo
**Dependencies:** None

- [ ] 1.0 Add `unrelated_mode()` method to `PythonRequireInfo` class
  - Set `_name`, `_version`, `_user`, `_channel`, `_revision` to `None`
- [ ] 1.1 Add `semver_direct_mode()` method to `PythonRequireInfo` class
- [ ] 1.2 Add `base_mode()` method to `PythonRequireInfo` class
- [ ] 1.3 Add `full_package_mode()` method to `PythonRequireInfo` class
- [ ] 1.4 Add `package_revision_mode()` method to `PythonRequireInfo` class
- [ ] 1.5 Verify existing tests still pass
  - Run existing tests in `python_requires_package_id_test.py`

### Testing

#### Task Group 2: Basic Functionality Verification
**Dependencies:** Task Group 1

- [ ] 2.0 Verify the bug is fixed
  - Test that `default_python_requires_id_mode=unrelated_mode` no longer throws AttributeError
"""

MOTO = """## Overview
Total Tasks: 2

#### Task Group 1: Fix DynamoType arithmetic to use Decimal
**Dependencies:** None

- [ ] 1.0 Fix floating-point arithmetic in `DynamoType.__add__()` and `__sub__()` in `/testbed/moto/dynamodb/models/dynamo_type.py`
  - [ ] 1.1 Write tests for `Decimal` arithmetic in `__add__()` and `__sub__()`
  - [ ] 1.2 Modify `DynamoType.__add__()` method to use `decimal.Decimal` for arithmetic
  - [ ] 1.3 Modify `DynamoType.__sub__()` method to use `decimal.Decimal` for arithmetic
  - [ ] 1.4 Run tests for Decimal arithmetic operations

#### Task Group 2: Integration Test for DynamoDB ADD Expression
**Dependencies:** Task Group 1

- [ ] 2.0 Review and verify integration tests for DynamoDB `ADD` expression
  - [ ] 2.1 Review existing tests in `/testbed/tests/test_dynamodb/`
    - [ ] Look for existing tests that use `ADD` expression with `update_item`
  - [ ] 2.2 Write integration test for the floating-point precision bug
  - [ ] 2.3 Run integration tests
"""


def _tasks_rule(text: str, params: dict):
    item = SimpleNamespace(id="x", stage="create_tasks", check=SimpleNamespace(params=params), target=SimpleNamespace(ref="tasks", state="stage_end", type="artifact"))
    return C.tasks(item, SimpleNamespace(artifact_text=lambda aid, state="final": text))


def test_a_verification_group_named_by_its_title_and_task_lines_is_no_implementation_group():
    first, total = _params("agentos_bugfix_tasks.test_first"), _params("agentos_bugfix_tasks.total")
    assert first.get("wide_words") is True and total.get("wide_words") is True and total.get("impl_counts") is True
    # s23_getmoto__moto-7365_6: group 2 reviews, writes and runs tests -- only group 1 is judged test-first
    r = _tasks_rule(MOTO, first)
    assert r.status == "pass" and r.detail == "1 groups test first, run last"
    # s1_conan-io__conan-10959_6: group 2 only verifies; Total Tasks 6 counts group 1's six task lines
    r = _tasks_rule("## Overview\nTotal Tasks: 6\n\n" + CONAN, total)
    assert r.status == "pass"
    r = _tasks_rule(CONAN, first)
    assert r.score == 0.5 and "group 2" not in r.detail  # group 1 still writes no tests first
    # the default (narrow) reading is as before: titles only
    assert _tasks_rule(MOTO, {"rule": "test_first"}).score == 0.75


def test_a_title_naming_a_check_over_code_work_stays_an_implementation_group():
    titles = ("Basic Functionality Verification", "Integration Test for DynamoDB ADD Expression")
    tests_only = ["Review existing tests in tests/", "Write integration test for the bug", "Run integration tests"]
    assert all(C.check_group(t, True, tests_only) and not C.implementation_group(t, True, tests_only) for t in titles)
    assert C.check_group("Basic Functionality Verification", True, ["Verify the bug is fixed"])
    # a code change among the task lines, or a "verify" line that fixes too: an implementation group
    assert C.implementation_group("Integration Test for DynamoDB ADD Expression", True, [*tests_only, "Modify DynamoType.__add__ to use Decimal"])
    assert C.implementation_group("Basic Functionality Verification", True, ["Verify and fix the parser in src/a.py"])
    # a title that names no check, test lines or not; no task line; or the narrow reading: as before
    assert C.implementation_group("Fix DynamoType arithmetic", True, tests_only)
    assert C.implementation_group("Input Validation", True, ["Write tests for the validation", "Run the tests"])
    assert C.implementation_group("Basic Functionality Verification", True) and C.implementation_group("Basic Functionality Verification", False, tests_only)
    assert not C.implementation_group("Test Verification", True) and not C.implementation_group("Test Review & Gap Analysis")
