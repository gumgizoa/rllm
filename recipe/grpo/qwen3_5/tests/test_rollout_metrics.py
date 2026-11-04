"""rollout_metrics: the ``rollout/*`` episode metrics train.py's grouping hook writes.

pytest recipe/grpo/qwen3_5/tests/test_rollout_metrics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.rollout_metrics import annotate, behavior  # noqa: E402


def _step(*calls):
    tool_calls = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    return SimpleNamespace(chat_completions=[{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": tool_calls}])


def _episode(task_id, reward, correct, steps=(), compliance=None):
    signals = {} if compliance is None else {"speckit_bug/compliance": compliance}
    traj = SimpleNamespace(reward=reward, signals=signals, steps=list(steps))
    return SimpleNamespace(task_id=task_id, is_correct=correct, metrics={}, trajectories=[traj])


def test_behavior_counts_exploration_and_test_runs():
    steps = [
        _step(("terminal", {"command": "grep -rn foo src/"})),
        _step(("file_editor", {"command": "view", "path": "/testbed/src/a.py"})),
        _step(("file_editor", {"command": "create", "path": "/tmp/speckit/bugs/issue/assessment.md", "file_text": "..."})),  # a document, not an edit
        _step(("terminal", {"command": "python -m pytest tests/test_a.py -q"})),
        _step(("file_editor", {"command": "str_replace", "path": "/testbed/src/a.py", "old_str": "a", "new_str": "b"})),
        _step(("terminal", {"command": "pytest -x"})),
    ]
    assert behavior(_episode("t", 1.0, True, steps)) == {"rollout/turns_before_edit": 4.0, "rollout/test_runs": 2.0}


def test_shell_writes_count_as_edits_unless_they_target_documents():
    edit = lambda cmd: behavior(_episode("t", 1.0, True, [_step(("terminal", {"command": cmd}))]))["rollout/turns_before_edit"]
    assert edit("sed -i 's/a/b/' src/a.py") == 0.0
    assert edit("git apply /tmp/fix.patch") == 0.0
    assert edit("cat > src/a.py <<'EOF'\nx\nEOF") == 0.0
    assert edit("echo '# notes' > /tmp/notes.md") == 1.0  # a document: still no code edit
    assert edit("pytest -q > /dev/null") == 1.0


def test_no_edit_means_every_turn_was_before_the_edit():
    steps = [_step(("terminal", {"command": "ls"})), _step(("finish", {}))]
    assert behavior(_episode("t", 0.0, False, steps))["rollout/turns_before_edit"] == 2.0


def test_steps_without_a_response_message_are_skipped():
    assert behavior(_episode("t", 0.0, False, [SimpleNamespace(chat_completions=[]), SimpleNamespace(chat_completions=None)]))["rollout/test_runs"] == 0.0


def test_annotate_splits_compliance_by_verdict_and_flags_solves_under_the_group_mean():
    # one group: three solved at 0.9 / 0.9 / 0.2 (mul reward), one unsolved at 0 -> mean 0.5
    eps = [
        _episode("t1", 0.9, True, compliance=0.9),
        _episode("t1", 0.9, True, compliance=0.9),
        _episode("t1", 0.2, True, compliance=0.2),
        _episode("t1", 0.0, False, compliance=0.7),
        _episode("t2", 1.0, True),  # no compliance scorer: verifier reward alone
    ]
    annotate(eps)
    assert [e.metrics.get("rollout/solved_below_group_mean") for e in eps] == [0.0, 0.0, 1.0, None, 0.0]
    assert [e.metrics.get("rollout/compliance_solved") for e in eps] == [0.9, 0.9, 0.2, None, None]
    assert eps[3].metrics["rollout/compliance_unsolved"] == 0.7
    assert "rollout/compliance_unsolved" not in eps[0].metrics
    assert all("rollout/turns_before_edit" in e.metrics and "rollout/test_runs" in e.metrics for e in eps)


def test_annotate_ignores_trajectories_without_a_reward():
    eps = [_episode("t", None, True), _episode("t", 1.0, True)]
    annotate(eps)
    assert "rollout/solved_below_group_mean" not in eps[0].metrics
    assert eps[1].metrics["rollout/solved_below_group_mean"] == 0.0
