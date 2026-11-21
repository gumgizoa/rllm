"""speckit_bug's penalty term: the log-only ``*.penalty.*`` items (gold source files named by the reports, a
related existing test run after the last edit, reports consistent with the change), the ``post`` hook that folds
them into ``speckit_bug/penalty``, and train.py mixing it into the reward.

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
    assert GOLD[TASK] == {"src": ["src/_pytest/setuponly.py"]}
    assert "getmoto__moto-4986" in GOLD  # SWE-Gym (the training set)
    assert all(set(v) == {"src"} and v["src"] for v in GOLD.values())
    assert not any(p.endswith((".rst", ".md")) or "/tests/" in p or p.startswith("doc/") for v in GOLD.values() for p in v["src"])


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


def test_penalty_is_the_mean_score_of_the_penalty_items():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    clean = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, FILES))
    assert clean["speckit_bug/penalty"] == 1.0  # gold file named, a related test run after the edits, reports match the change
    missed = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, {k: v.replace("setuponly", "elsewhere") for k, v in FILES.items()}))
    # gold_files 0 (setuponly never named); scope_consistency 1/3 (setuponly unrecorded, elsewhere a phantom row); related test 1
    assert missed["speckit_bug/penalty"] == pytest.approx((0 + 1 / 3 + 1) / 3)
    # a task without a gold entry: the gold item cannot be judged and is left out of the mean, the other two still count
    unknown = ev.score(SimpleNamespace(id="unknown__task-1", metadata=META), _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, FILES))
    assert unknown["speckit_bug/penalty"] == 1.0
    assert unknown["speckit_bug/penalty_unavailable"] == 1.0
    assert "speckit_bug/fix.penalty.gold_files.named" not in unknown
    # each item is reported under its own name, with whether it was judged on the run
    assert clean["speckit_bug/fix.penalty.gold_files.named"] == 1.0
    assert clean["speckit_bug/penalty_applies.related_test_run.after_last_edit"] == 1.0


def test_a_run_that_changes_no_code_keeps_no_penalty_rule():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    idle = ev.score(task, _trace(RUN_F2P), _data(ev, {}))
    # no report names the gold file (0), no fix report (0), and no source change for a test run to verify: outside the
    # item, worth 0 -- every item stays in the mean, so doing nothing is not the way to a high penalty score
    assert idle["speckit_bug/penalty"] == 0.0
    assert idle["speckit_bug/penalty_applies.related_test_run.after_last_edit"] == 0.0
    assert idle["speckit_bug/test.penalty.related_test_run.after_last_edit"] == 0.0


def test_a_scratch_script_written_after_the_test_run_is_no_source_change():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    repro = ("file_editor", {"command": "create", "path": "/testbed/repro_issue.py", "file_text": "print(1)\n"}, "File created successfully at: /testbed/repro_issue.py")
    readme = ("file_editor", {"command": "str_replace", "path": "/testbed/README.rst", "old_str": "a", "new_str": "b"}, "The file /testbed/README.rst has been edited.")
    files = {**FILES, f"{BUG}/fix.md": FIX.replace("| `src/_pytest/other.py` | modified | extra |\n", "| `src/_pytest/other.py` | modified | extra |\n| `repro_issue.py` | added | script |\n| `README.rst` | modified | note |\n")}
    s = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P, repro, readme), _data(ev, files))
    # the last source change is still the edit before the run: a throwaway script at the repository root and a README
    # edit do not make the earlier test run stale
    assert s["speckit_bug/test.penalty.related_test_run.after_last_edit"] == 1.0


def test_scope_consistency_wants_the_reports_to_describe_the_change():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    clean = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, FILES))
    # an edit the Changes table leaves out, and no deviation recorded for the file beyond the assessment's list: 1/3
    unrecorded = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, {**FILES, f"{BUG}/fix.md": FIX_ONE_ROW.replace("- Also touched `src/_pytest/other.py`: the helper the assessment pointed at lives there.", "None")}))
    assert unrecorded["speckit_bug/penalty"] == pytest.approx((1 + 1 / 3 + 1) / 3)
    # a Changes row for a file that was never changed: 2/3
    phantom = ev.score(task, _trace(EDIT, RUN_F2P), _data(ev, FILES))
    assert phantom["speckit_bug/penalty"] == pytest.approx((1 + 2 / 3 + 1) / 3)
    # the expansion made but not acknowledged: 2/3
    silent = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, {**FILES, f"{BUG}/fix.md": FIX_UNACKNOWLEDGED}))
    assert silent["speckit_bug/penalty"] == pytest.approx((1 + 2 / 3 + 1) / 3)
    # the compliance twin moves the fix stage score; the penalty items do not
    assert unrecorded["speckit_bug/stage.fix"] < clean["speckit_bug/stage.fix"]
    only_f2p = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_OTHER), _data(ev, FILES))
    assert only_f2p["speckit_bug/compliance"] == pytest.approx(clean["speckit_bug/compliance"])


def test_gold_files_item_wants_every_gold_file_named(monkeypatch):
    monkeypatch.setattr(checks, "_GOLD", {"t": {"src": ["a/one.py", "a/two.py", "a/three.py"]}})
    ev = _ev()
    fix = "# Fix\n\n## Changes\n\n| File | Change | Notes |\n|---|---|---|\n| `a/one.py` | modified | - |\n| `a/two.py` | modified | - |\n"
    edits = [("file_editor", {"command": "str_replace", "path": f"/testbed/a/{n}.py", "old_str": "a", "new_str": "b"}, "edited") for n in ("one", "two")]
    s = ev.score(SimpleNamespace(id="t", metadata=META), _trace(*edits), _data(ev, {f"{BUG}/fix.md": fix}, related={"a/one.py": [], "a/two.py": []}))
    # two of three gold files named: 0, not 2/3; consistency 1 (no assessment list to expand beyond); the related-test
    # item stands outside the run with its condition not arisen (the code changed, no related test exists): worth 1
    assert s["speckit_bug/fix.penalty.gold_files.named"] == 0.0
    assert s["speckit_bug/penalty"] == pytest.approx((0 + 1 + 1) / 3)
    assert s["speckit_bug/penalty_applies.related_test_run.after_last_edit"] == 0.0
    all_three = fix + "| `a/three.py` | modified | - |\n"
    edits3 = [*edits, ("file_editor", {"command": "str_replace", "path": "/testbed/a/three.py", "old_str": "a", "new_str": "b"}, "edited")]
    s = ev.score(SimpleNamespace(id="t", metadata=META), _trace(*edits3), _data(ev, {f"{BUG}/fix.md": all_three}, related={"a/one.py": [], "a/two.py": [], "a/three.py": []}))
    assert s["speckit_bug/fix.penalty.gold_files.named"] == 1.0
    assert s["speckit_bug/penalty"] == 1.0


def test_the_items_are_log_only_and_routed_by_their_id():
    rub = _ev().rubric
    pen = [i for i in rub.items if i.id.split(".")[2] == "penalty"]
    assert sorted(i.id for i in pen) == ["speckit_bug.fix.penalty.gold_files.named", "speckit_bug.fix.penalty.scope_consistency.recorded", "speckit_bug.test.penalty.related_test_run.after_last_edit"]
    # the consistency rule is scored on both sides: once for compliance, once for the penalty
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
RUN_DIR = ("terminal", {"command": "cd /testbed && python -m pytest testing -q"}, "......\n6 passed in 0.30s\n[Command finished with exit code 0]")
FILES = {f"{BUG}/assessment.md": ASSESSMENT, f"{BUG}/fix.md": FIX}
RELATED = {"src/_pytest/setuponly.py": ["testing/test_setuponly.py"], "src/_pytest/other.py": []}  # what collect.py's exec 3 found


def _data(ev, files, related=RELATED):
    """``from_outputs`` plus the sandbox-only listing the related-tests item reads (None: offline, not collected)."""
    collected, extra = ev.from_outputs(files)
    collected.related_tests = related
    return collected, extra


def test_related_item_wants_a_related_test_run_after_the_last_source_edit():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    ok = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_F2P), _data(ev, FILES))
    assert ok["speckit_bug/penalty"] == 1.0
    before = ev.score(task, _trace(RUN_F2P, EDIT, EDIT_OTHER), _data(ev, FILES))
    assert before["speckit_bug/penalty"] == pytest.approx(2 / 3)  # run only before the edits: the item fails, the other two pass
    other = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_OTHER), _data(ev, FILES))
    assert other["speckit_bug/penalty"] == pytest.approx(2 / 3)  # a test run, but not a related test
    again = ev.score(task, _trace(RUN_F2P, EDIT, EDIT_OTHER, RUN_OTHER, RUN_F2P), _data(ev, FILES))
    assert again["speckit_bug/penalty"] == 1.0
    whole_dir = ev.score(task, _trace(EDIT, EDIT_OTHER, RUN_DIR), _data(ev, FILES))
    assert whole_dir["speckit_bug/penalty"] == 1.0  # the directory holding the related test counts
    for k in ("speckit_bug/compliance", "speckit_bug/stage.test"):
        assert ok[k] == pytest.approx(before[k])  # log_only


def test_related_item_is_not_applicable_without_related_tests_and_unavailable_offline():
    ev = _ev()
    task = SimpleNamespace(id=TASK, metadata=META)
    none_related = ev.score(task, _trace(EDIT, EDIT_OTHER), _data(ev, FILES, related={"src/_pytest/setuponly.py": [], "src/_pytest/other.py": []}))
    assert none_related["speckit_bug/penalty"] == 1.0  # gold_files and scope_consistency pass; nothing to run -> not applicable
    offline = ev.score(task, _trace(EDIT, EDIT_OTHER), _data(ev, FILES, related=None))
    assert offline["speckit_bug/penalty"] == 1.0  # not collected (offline replay): unavailable, left out of the mean
    assert offline["speckit_bug/unavailable"] >= 1.0


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


def test_hook_pays_a_solved_rollout_by_the_mean_without_the_reference_fix_items(train_module):
    # a workflow with items judged against the reference fix gives <penalty>_solved beside <penalty>
    def reward(verifier, penalty, solved, gate="all"):
        eps, traj = _eps(verifier, 0.5, penalty)
        if solved is not None:
            traj.signals["speckit_bug/penalty_solved"] = solved
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.7, 0.3, "speckit_bug/penalty", 0.3, gate)(eps, None)
        return traj.reward

    # solved, the reference-fix item failed (0.9) but every other rule kept (1.0): nothing is lost
    assert reward(1.0, 0.9, 1.0) == pytest.approx(0.7 * 0.85 + 0.3)
    # solved, a test rule broken as well (0.8 / 0.9): the solve still pays for that one
    assert reward(1.0, 0.8, 0.9) == pytest.approx(0.7 * 0.85 + 0.3 * 0.9)
    # unsolved: paid by the mean with the reference-fix item in it
    assert reward(0.0, 0.8, 0.9) == pytest.approx(0.3 * 0.8)
    # without the second mean the hook is as before
    assert reward(1.0, 0.8, None) == pytest.approx(0.7 * 0.85 + 0.3 * 0.8)
    # the whole-mean gate still waives everything for a solve
    assert reward(1.0, 0.8, 0.9, gate="unsolved") == pytest.approx(0.7 * 0.85 + 0.3)


def test_hook_rejects_a_penalty_without_its_signal_or_out_of_range(train_module):
    with pytest.raises(ValueError, match="penalty_weight"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, None, 0.2)
    with pytest.raises(ValueError, match="penalty_weight"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, "speckit_bug/penalty", 1.0)
    with pytest.raises(ValueError, match="penalty_gate"):
        train_module.make_budget_scaled_grouping_hook(1.0, "mul", 0.2, "speckit_bug/compliance", 0.0, 0.3, "speckit_bug/penalty", 0.2, "solved")
