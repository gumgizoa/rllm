"""speckit_bug's D term: the log-only ``*.penalty.*`` item (gold source files named by the reports), the
``post`` hook that folds it into ``speckit_bug/penalty``, and train.py subtracting it from unsolved rollouts.

    pytest recipe/grpo/qwen3_5/tests/test_speckit_bug_penalty.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_aidlc_reward import _call, episode, train_module  # noqa: E402,F401  (fixture re-exported)

from recipe.grpo.qwen3_5.workflows import speckit_bug  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug.reward import checks  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug.reward.eval import Evaluation  # noqa: E402

BUG = "/tmp/speckit/bugs/issue"
GOLD = json.loads((speckit_bug.HERE / "reward" / "gold_files.json").read_text())
TASK = "pytest-dev__pytest-7205"  # SWE-bench Verified; gold = src/_pytest/setuponly.py

ASSESSMENT = """# Bug Assessment: x

## Proposed Remediation

**Preferred**: use saferepr.

**Files likely to change**:
- `/testbed/src/_pytest/setuponly.py`

**Checks to run**:
- `python -m pytest /tmp/speckit/bugs/issue/checks/repro.py`
"""

FIX = """# Fix Report

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/_pytest/setuponly.py` | modified | saferepr |
| `src/_pytest/other.py` | modified | extra |

## Deviations from Assessment

- Also touched `src/_pytest/other.py`: the helper the assessment pointed at lives there.
"""

FIX_UNACKNOWLEDGED = FIX.replace("- Also touched `src/_pytest/other.py`: the helper the assessment pointed at lives there.", "None")
FIX_ONE_ROW = FIX.replace("| `src/_pytest/other.py` | modified | extra |\n", "")


def _ev() -> Evaluation:
    return Evaluation()



def test_gold_table_has_both_datasets_with_source_files_only():
    assert GOLD[TASK] == {"src": ["src/_pytest/setuponly.py"], "tests": ["testing/test_setuponly.py"]}
    assert "getmoto__moto-4986" in GOLD  # SWE-Gym (the training set)
    assert all(v["src"] for v in GOLD.values())
    assert not any(p.endswith((".rst", ".md")) or "/tests/" in p or p.startswith("doc/") for v in GOLD.values() for p in v["src"])
    # F2P test files the task adds are left out: a few tasks keep no visible test file at all
    assert all(not p.endswith(".rst") for v in GOLD.values() for p in v["tests"])
    assert 0 < sum(1 for v in GOLD.values() if not v["tests"]) < 100


def test_named_files_joins_the_assessment_list_and_the_changes_table():
    assert checks.named_files(ASSESSMENT, FIX, "/testbed") == {"src/_pytest/setuponly.py", "src/_pytest/other.py"}
    assert checks.named_files(ASSESSMENT, None, "/testbed") == {"src/_pytest/setuponly.py"}
    assert checks.named_files(None, FIX, None) == {"src/_pytest/setuponly.py", "src/_pytest/other.py"}
    assert checks.named_files("# no sections", "# none", None) == set()


def test_inputs_resolve_the_instance_id_from_the_task():
    assert checks.inputs(SimpleNamespace(id=TASK), None) == {"gold_files": ["src/_pytest/setuponly.py"], "gold_tests": ["testing/test_setuponly.py"]}
    assert checks.inputs(SimpleNamespace(id=f"{TASK}:0"), None)["gold_files"] == ["src/_pytest/setuponly.py"]
    assert checks.inputs(SimpleNamespace(id="", metadata={"metadata": {"instance_id": TASK}}), None)["gold_files"] == ["src/_pytest/setuponly.py"]
    assert checks.inputs(SimpleNamespace(id="not-a-task"), None) == {"gold_files": None, "gold_tests": None}


def test_penalty_is_the_mean_score_of_the_penalty_items():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    clean = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs(FILES))
    assert clean["speckit_bug/penalty"] == 1.0  # gold file named, F2P file run after the edits, reports match the change
    missed = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs({k: v.replace("setuponly", "elsewhere") for k, v in FILES.items()}))
    # gold_files 0 (setuponly never named); scope_consistency 1/3 (setuponly unrecorded, elsewhere a phantom row); f2p 1
    assert missed["speckit_bug/penalty"] == pytest.approx((0 + 1 / 3 + 1) / 3)
    # a task without a gold entry: the gold items are not applicable, the consistency item still counts
    unknown = ev.score(SimpleNamespace(id="unknown__task-1", metadata=META), _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs(FILES))
    assert unknown["speckit_bug/penalty"] == 1.0


def test_scope_consistency_wants_the_reports_to_describe_the_change():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    clean = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs(FILES))
    # an edit the Changes table leaves out, and no deviation recorded for the file beyond the assessment's list: 1/3
    unrecorded = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs({**FILES, f"{BUG}/fix.md": FIX_ONE_ROW.replace("- Also touched `src/_pytest/other.py`: the helper the assessment pointed at lives there.", "None")}))
    assert unrecorded["speckit_bug/penalty"] == pytest.approx((1 + 1 / 3 + 1) / 3)
    # a Changes row for a file that was never changed: 2/3
    phantom = ev.score(task, _trace(EDIT, RUN_F2P), ev.from_outputs(FILES))
    assert phantom["speckit_bug/penalty"] == pytest.approx((1 + 2 / 3 + 1) / 3)
    # the expansion made but not acknowledged: 2/3
    silent = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs({**FILES, f"{BUG}/fix.md": FIX_UNACKNOWLEDGED}))
    assert silent["speckit_bug/penalty"] == pytest.approx((1 + 2 / 3 + 1) / 3)
    # the compliance twin moves the fix stage score; the penalty items do not
    assert unrecorded["speckit_bug/stage.fix"] < clean["speckit_bug/stage.fix"]
    only_f2p = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_OTHER), ev.from_outputs(FILES))
    assert only_f2p["speckit_bug/compliance"] == pytest.approx(clean["speckit_bug/compliance"])


def test_gold_files_item_is_a_recall_over_several_gold_files(monkeypatch):
    monkeypatch.setattr(checks, "_GOLD", {"t": {"src": ["a/one.py", "a/two.py", "a/three.py"], "tests": []}})
    ev = _ev()
    fix = "# Fix\n\n## Changes\n\n| File | Change | Notes |\n|---|---|---|\n| `a/one.py` | modified | - |\n| `a/two.py` | modified | - |\n"
    edits = [("file_editor", {"command": "str_replace", "path": f"/testbed/a/{n}.py", "old_str": "a", "new_str": "b"}, "edited") for n in ("one", "two")]
    s = ev.score(SimpleNamespace(id="t", metadata=META), _trace(*edits), ev.from_outputs({f"{BUG}/fix.md": fix}))
    # gold recall 2/3; consistency 1 (no assessment list to expand beyond); f2p not applicable (no visible test file)
    assert s["speckit_bug/penalty"] == pytest.approx((2 / 3 + 1) / 2)


def test_the_items_are_log_only_and_routed_by_their_id():
    rub = _ev().rubric
    pen = [i for i in rub.items if i.id.split(".")[2] == "penalty"]
    assert sorted(i.id for i in pen) == ["speckit_bug.fix.penalty.gold_files.named", "speckit_bug.fix.penalty.scope_consistency.recorded", "speckit_bug.test.penalty.f2p_test_run.after_last_edit"]
    # the consistency rule is scored on both sides: once for compliance, once for D
    assert any(i.id == "speckit_bug.fix.fix.speckit_bug_scope_consistency.recorded" and not i.log_only for i in rub.items)
    assert not any(i.id == "speckit_bug.fix.fix.cross_ref.changes" for i in rub.items)
    assert all(i.log_only for i in pen)
    assert speckit_bug.SPEC.penalty_signal == "speckit_bug/penalty"


def _trace(*turns):
    """The last call's observation never reaches the model (as live), so a trailing look-up closes the trace."""
    turns = [*turns, ("file_editor", {"command": "view", "path": "/speckit/core-workflow.md"}, "# core")]
    return episode([(_call(i, name, **args), obs) for i, (name, args, obs) in enumerate(turns)])


META = {"workdir": "/testbed"}  # what a saved task records; the offline replay takes the code root from it


EDIT = ("file_editor", {"command": "str_replace", "path": "/testbed/src/_pytest/setuponly.py", "old_str": "a", "new_str": "b"}, "The file /testbed/src/_pytest/setuponly.py has been edited.")
EDIT_OTHER = ("file_editor", {"command": "str_replace", "path": "/testbed/src/_pytest/other.py", "old_str": "a", "new_str": "b"}, "The file /testbed/src/_pytest/other.py has been edited.")
RUN_F2P = ("terminal", {"command": "cd /testbed && python -m pytest testing/test_setuponly.py -q"}, "....\n4 passed in 0.20s\n[Command finished with exit code 0]")
RUN_OTHER = ("terminal", {"command": "cd /testbed && python -m pytest testing/test_main.py -q"}, "..\n2 passed in 0.10s\n[Command finished with exit code 0]")
FILES = {f"{BUG}/assessment.md": ASSESSMENT, f"{BUG}/fix.md": FIX}


def test_f2p_item_wants_the_f2p_file_run_after_the_last_source_edit():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    ok = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), ev.from_outputs(FILES))
    assert ok["speckit_bug/penalty"] == 1.0
    before = ev.score(task, _trace(RUN_F2P, EDIT, EDIT_OTHER), ev.from_outputs(FILES))
    assert before["speckit_bug/penalty"] == pytest.approx(2 / 3)  # run only before the edits: the f2p item fails, the other two pass
    other = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_OTHER), ev.from_outputs(FILES))
    assert other["speckit_bug/penalty"] == pytest.approx(2 / 3)  # a test run, but not the F2P file
    again = ev.score(task, _trace(RUN_F2P, EDIT, EDIT_OTHER, RUN_OTHER, RUN_F2P), ev.from_outputs(FILES))
    assert again["speckit_bug/penalty"] == 1.0
    for k in ("speckit_bug/compliance", "speckit_bug/stage.test"):
        assert ok[k] == pytest.approx(before[k])  # log_only


def test_f2p_item_is_not_applicable_when_the_f2p_files_are_new(monkeypatch):
    monkeypatch.setattr(checks, "_GOLD", {"t": {"src": ["src/_pytest/setuponly.py"], "tests": []}})
    ev = _ev()
    s = ev.score(SimpleNamespace(id="t", metadata=META), _trace(EDIT, EDIT_OTHER), ev.from_outputs(FILES))
    assert s["speckit_bug/penalty"] == 1.0  # gold_files and scope_consistency pass; f2p not applicable


def _eps(verifier: float, compliance: float | None, penalty: float | None):
    from rllm.workflows.workflow import TerminationReason as TR

    signals = {}
    if compliance is not None:
        signals["speckit_bug/compliance"] = compliance
    if penalty is not None:
        signals["speckit_bug/penalty"] = penalty
    traj = SimpleNamespace(reward=verifier, signals=signals, steps=[])
    return [SimpleNamespace(termination_reason=TR.ENV_DONE, trajectories=[traj], task_id="t", is_correct=verifier > 0, metrics={})], traj


def test_hook_folds_the_penalty_in_as_a_weighted_term(train_module):
    def reward(verifier, compliance, penalty, w=0.2, gate="all", mode="mul", floor=0.7):
        eps, traj = _eps(verifier, compliance, penalty)
        train_module.make_budget_scaled_grouping_hook(1.0, mode, 0.2, "speckit_bug/compliance", floor, 0.3, "speckit_bug/penalty", w, gate)(eps, None)
        return traj.reward

    # reward = 0.8 * solve * (0.7 + 0.3 c) + 0.2 * penalty, penalty = 1 when every penalty rule was kept
    assert reward(1.0, 0.5, 1.0) == pytest.approx(0.8 * 0.85 + 0.2)  # solved, clean: 0.88
    assert reward(1.0, 0.5, 0.0) == pytest.approx(0.8 * 0.85)  # solved, every penalty item failed: 0.68
    assert reward(0.0, 0.5, 1.0) == pytest.approx(0.2)  # unsolved but clean
    assert reward(0.0, 0.5, 0.5) == pytest.approx(0.1)
    assert reward(0.0, 0.5, 0.0) == 0.0
    assert reward(0.0, 0.5, None) == pytest.approx(0.2)  # no signal: P = 1, a constant within the group
    assert reward(1.0, 0.5, 0.0, gate="unsolved") == pytest.approx(0.88)  # gated: a solve keeps the full w
    assert reward(0.0, 0.5, 0.0, gate="unsolved") == 0.0
    assert reward(0.0, None, 0.0, mode=None, floor=0.0) == 0.0  # independent of the compliance mode
    assert reward(1.0, 0.5, 0.0, w=0.0) == pytest.approx(0.85)  # off by default: the mul reward alone


def test_hook_rejects_a_penalty_without_its_signal_or_out_of_range(train_module):
    with pytest.raises(ValueError, match="penalty_weight"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, None, 0.2)
    with pytest.raises(ValueError, match="penalty_weight"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, "speckit_bug/penalty", 1.0)
    with pytest.raises(ValueError, match="penalty_gate"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, "speckit_bug/penalty", 0.2, "solved")
