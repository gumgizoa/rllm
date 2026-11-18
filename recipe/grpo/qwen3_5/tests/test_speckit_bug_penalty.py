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

None
"""


def _ev() -> Evaluation:
    return Evaluation()


def _score(ev: Evaluation, task_id: str, files: dict[str, str]) -> dict[str, float]:
    ep = episode([(_call(0, "file_editor", command="view", path="/speckit/core-workflow.md"), "# core")])
    return ev.score(SimpleNamespace(id=task_id, metadata={}), ep, ev.from_outputs(files))


def test_gold_table_has_both_datasets_with_source_files_only():
    assert GOLD[TASK] == ["src/_pytest/setuponly.py"]
    assert "getmoto__moto-4986" in GOLD  # SWE-Gym (the training set)
    assert all(v for v in GOLD.values())
    assert not any(p.endswith((".rst", ".md")) or "/tests/" in p or p.startswith("doc/") for v in GOLD.values() for p in v)


def test_named_files_joins_the_assessment_list_and_the_changes_table():
    assert checks.named_files(ASSESSMENT, FIX, "/testbed") == {"src/_pytest/setuponly.py", "src/_pytest/other.py"}
    assert checks.named_files(ASSESSMENT, None, "/testbed") == {"src/_pytest/setuponly.py"}
    assert checks.named_files(None, FIX, None) == {"src/_pytest/setuponly.py", "src/_pytest/other.py"}
    assert checks.named_files("# no sections", "# none", None) == set()


def test_inputs_resolve_the_instance_id_from_the_task():
    assert checks.inputs(SimpleNamespace(id=TASK), None) == {"gold_files": ["src/_pytest/setuponly.py"]}
    assert checks.inputs(SimpleNamespace(id=f"{TASK}:0"), None)["gold_files"] == ["src/_pytest/setuponly.py"]
    assert checks.inputs(SimpleNamespace(id="", metadata={"metadata": {"instance_id": TASK}}), None)["gold_files"] == ["src/_pytest/setuponly.py"]
    assert checks.inputs(SimpleNamespace(id="not-a-task"), None) == {"gold_files": None}


def test_penalty_signal_is_the_unnamed_share_and_never_enters_compliance():
    ev = _ev()
    both = _score(ev, TASK, {f"{BUG}/assessment.md": ASSESSMENT, f"{BUG}/fix.md": FIX})
    assert both["speckit_bug/penalty"] == 0.0  # the gold file is named
    missed = _score(ev, TASK, {f"{BUG}/assessment.md": ASSESSMENT.replace("setuponly", "elsewhere"), f"{BUG}/fix.md": FIX.replace("setuponly", "elsewhere")})
    assert missed["speckit_bug/penalty"] == 1.0  # one gold file, not named
    # log_only: the item changes neither compliance nor the fix stage score
    for k in ("speckit_bug/compliance", "speckit_bug/stage.fix"):
        assert both[k] == pytest.approx(missed[k])
    # a task without a gold entry: the item is not applicable and the signal is absent
    assert "speckit_bug/penalty" not in _score(ev, "unknown__task-1", {f"{BUG}/assessment.md": ASSESSMENT, f"{BUG}/fix.md": FIX})


def test_penalty_is_a_recall_over_several_gold_files(monkeypatch):
    monkeypatch.setattr(checks, "_GOLD", {"t": ["a/one.py", "a/two.py", "a/three.py"]})
    ev = _ev()
    fix = "# Fix\n\n## Changes\n\n| File | Change | Notes |\n|---|---|---|\n| `a/one.py` | modified | - |\n| `a/two.py` | modified | - |\n"
    assert _score(ev, "t", {f"{BUG}/fix.md": fix})["speckit_bug/penalty"] == pytest.approx(1 / 3)


def test_the_item_is_log_only_and_routed_by_its_id():
    rub = _ev().rubric
    pen = [i for i in rub.items if i.id.split(".")[2] == "penalty"]
    assert [i.id for i in pen] == ["speckit_bug.fix.penalty.gold_files.named"]
    assert all(i.log_only for i in pen)
    assert speckit_bug.SPEC.penalty_signal == "speckit_bug/penalty"


def _eps(verifier: float, compliance: float | None, penalty: float | None):
    from rllm.workflows.workflow import TerminationReason as TR

    signals = {}
    if compliance is not None:
        signals["speckit_bug/compliance"] = compliance
    if penalty is not None:
        signals["speckit_bug/penalty"] = penalty
    traj = SimpleNamespace(reward=verifier, signals=signals, steps=[])
    return [SimpleNamespace(termination_reason=TR.ENV_DONE, trajectories=[traj], task_id="t", is_correct=verifier > 0, metrics={})], traj


def test_hook_subtracts_the_penalty_from_unsolved_rollouts_only(train_module):
    def reward(verifier, compliance, penalty, mode="mul", floor=0.7, lam_d=0.3):
        eps, traj = _eps(verifier, compliance, penalty)
        train_module.make_budget_scaled_grouping_hook(1.0, mode, 0.2, "speckit_bug/compliance", floor, 0.3, "speckit_bug/penalty", lam_d)(eps, None)
        return traj.reward

    assert reward(0.0, 0.5, 1.0) == pytest.approx(-0.3)  # unsolved, no gold file named: -lam_d
    assert reward(0.0, 0.5, 0.5) == pytest.approx(-0.15)  # half the gold files named
    assert reward(0.0, 0.5, 0.0) == 0.0  # unsolved but every gold file named: untouched
    assert reward(1.0, 0.5, 1.0) == pytest.approx(0.85)  # solved: the mul reward alone, D never bites
    assert reward(0.0, 0.5, None) == 0.0  # no penalty signal: left alone
    assert reward(0.0, None, 1.0, mode=None, floor=0.0) == pytest.approx(-0.3)  # independent of the compliance mode
    assert reward(0.0, 0.5, 1.0, lam_d=0.0) == 0.0  # off by default


def test_hook_rejects_a_penalty_without_its_signal(train_module):
    with pytest.raises(ValueError, match="penalty_lam"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, None, 0.3)
    with pytest.raises(ValueError, match="penalty_lam"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, "speckit_bug/penalty", -0.1)
