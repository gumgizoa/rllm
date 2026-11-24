"""rollout_metrics: the ``rollout/*`` episode metrics train.py's grouping hook writes.

pytest recipe/grpo/qwen3_5/tests/test_rollout_metrics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.rollout_metrics import annotate, behavior, test_evidence  # noqa: E402

test_evidence.__test__ = False  # a metric, not a test


def _step(*calls):
    tool_calls = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    return SimpleNamespace(chat_completions=[{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": tool_calls}])


def _episode(task_id, reward, correct, steps=(), compliance=None):
    signals = {} if compliance is None else {"speckit_bug/compliance": compliance}
    traj = SimpleNamespace(reward=reward, signals=signals, steps=list(steps))
    return SimpleNamespace(task_id=task_id, is_correct=correct, metrics={}, trajectories=[traj])


def test_behavior_counts_the_turns_before_the_first_edit():
    steps = [
        _step(("terminal", {"command": "grep -rn foo src/"})),
        _step(("file_editor", {"command": "view", "path": "/testbed/src/a.py"})),
        _step(("file_editor", {"command": "create", "path": "/tmp/speckit/bugs/issue/assessment.md", "file_text": "..."})),  # a document, not an edit
        _step(("terminal", {"command": "python -m pytest tests/test_a.py -q"})),
        _step(("file_editor", {"command": "str_replace", "path": "/testbed/src/a.py", "old_str": "a", "new_str": "b"})),
        _step(("terminal", {"command": "pytest -x"})),
    ]
    assert behavior(_episode("t", 1.0, True, steps)) == {"rollout/turns_before_edit": 4.0}


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
    assert behavior(_episode("t", 0.0, False, [SimpleNamespace(chat_completions=[]), SimpleNamespace(chat_completions=None)]))["rollout/turns_before_edit"] == 2.0


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
    assert all("rollout/turns_before_edit" in e.metrics for e in eps)
    assert all("rollout/test_runs" not in e.metrics for e in eps)  # a harness no front end reads: no test metric, not a zero


def test_annotate_ignores_trajectories_without_a_reward():
    eps = [_episode("t", None, True), _episode("t", 1.0, True)]
    annotate(eps)
    assert "rollout/solved_below_group_mean" not in eps[0].metrics
    assert eps[1].metrics["rollout/solved_below_group_mean"] == 0.0


# ---------------------------------------------------------------------------------------------
# test_evidence: the same two questions read the way the workflow scorers read test runs
# ---------------------------------------------------------------------------------------------
PASSED = "============================== 3 passed in 0.12s ===============================\n"
SRC = ("file_editor", {"command": "str_replace", "path": "/testbed/pkg/mod.py", "old_str": "a", "new_str": "b"}, "The file /testbed/pkg/mod.py has been edited.")
PYTEST = ("terminal", {"command": "cd /testbed && python -m pytest tests/test_mod.py -q"}, PASSED)
PATCH = "diff --git a/pkg/mod.py b/pkg/mod.py\n--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-a\n+b\n"


def _traced(calls, patch=PATCH, harness="openhands-sdk", workdir="/testbed"):
    """An episode as the training harness records it: each step's request carries the earlier tool results."""
    steps, history = [], []
    for i, (name, args, observation) in enumerate(calls):
        call = {"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
        steps.append(SimpleNamespace(chat_completions=[{"role": "user", "content": "x"}, *history, call]))
        history += [call, {"role": "tool", "tool_call_id": f"c{i}", "content": observation}]
    steps.append(SimpleNamespace(chat_completions=[{"role": "user", "content": "x"}, *history, {"role": "assistant", "content": "done"}]))
    traj = SimpleNamespace(name=harness, reward=1.0, signals={}, steps=steps)
    task = SimpleNamespace(metadata={"workdir": workdir} if workdir else {})
    return SimpleNamespace(task_id="t", is_correct=True, metrics={}, artifacts={"patch": patch} if patch else {}, task=task, trajectories=[traj])


def _sh(command, observation=""):
    return ("terminal", {"command": command}, observation)


def _after(calls, **kw):
    m = test_evidence(_traced(calls, **kw))
    return m.get("rollout/test_after_last_edit"), m.get("rollout/test_valid_after_last_edit")


def test_evidence_counts_runner_invocations_and_the_valid_ones_apart():
    m = test_evidence(
        _traced(
            [
                _sh("cat tox.ini", "[tox]"),  # names a runner, runs none
                _sh("pip install pytest", "Successfully installed pytest"),
                _sh("pytest --collect-only tests/test_mod.py", "collected 3 items"),  # an invocation that runs no test
                _sh("pytest /tmp/test_x.py", PASSED),  # a test outside the repository
                PYTEST,
            ],
            patch=None,
        )
    )
    assert m == {"rollout/test_runs": 3.0, "rollout/test_runs_valid": 1.0}  # no source change: nothing after it


def test_evidence_after_the_last_change_ignores_what_is_no_source_change():
    for tail in (
        _sh(r"sed -i 's/- \[ \] 1.3 /- [x] 1.3 /' /tmp/agent-os/specs/x/tasks.md"),  # a ticked task list
        _sh("git diff > /tmp/fix.patch"),
        _sh("echo done > /tmp/flag"),
        _sh("git stash list", ""),
        ("file_editor", {"command": "create", "path": "/tmp/agent-os/specs/x/final-verification.md", "file_text": "# report"}, "File created"),
    ):
        assert _after([SRC, PYTEST, tail]) == (1.0, 1.0), tail
    assert _after([SRC, PYTEST, tail], patch=None) == (1.0, 1.0)  # without a recorded patch: the trace's writes


def test_evidence_after_the_last_change_needs_a_run_of_the_changed_code():
    assert _after([PYTEST, SRC]) == (0.0, 0.0)
    assert _after([SRC]) == (0.0, 0.0)
    assert _after([SRC, _sh("cat tox.ini", "[tox]")]) == (0.0, 0.0)
    assert _after([SRC, _sh("pytest --collect-only tests/test_mod.py", "collected 3 items")]) == (1.0, 0.0)  # tried, ran nothing
    assert _after([SRC, _sh("pytest /tmp/test_x.py", PASSED)]) == (1.0, 0.0)
    # the change stashed away: the run tested the old code
    assert _after([SRC, _sh("cd /testbed && git stash -q && python -m pytest tests/test_mod.py -q; git stash pop -q", PASSED)]) == (0.0, 0.0)


def test_evidence_reads_the_order_inside_one_command():
    edit_then_test = _sh("cd /testbed && sed -i 's/a/b/' pkg/mod.py && python -m pytest tests/test_mod.py -q", PASSED)
    test_then_edit = _sh("cd /testbed && python -m pytest tests/test_mod.py -q; sed -i 's/a/b/' pkg/mod.py", PASSED)
    assert _after([edit_then_test]) == (1.0, 1.0)
    assert _after([test_then_edit]) == (0.0, 0.0)


def test_evidence_knows_the_runners_and_tool_names_the_scorers_know():
    django = _sh("cd /testbed && python tests/runtests.py queries", "Ran 3 tests in 0.012s\n\nOK\n")
    other_tool = ("execute_bash", {"command": "cd /testbed && python -m pytest tests/test_mod.py -q"}, PASSED)
    assert _after([SRC, django]) == (1.0, 1.0)
    assert _after([SRC, other_tool]) == (1.0, 1.0)


def test_evidence_is_empty_for_a_harness_without_a_front_end_and_never_raises():
    assert test_evidence(_traced([SRC, PYTEST], harness="some-other-agent")) == {}
    assert test_evidence(SimpleNamespace(trajectories=None)) == {}  # unreadable: logged, not raised
    m = test_evidence(_traced([SRC, PYTEST], workdir=None))  # the task names no repository root: counts only
    assert m == {"rollout/test_runs": 1.0, "rollout/test_runs_valid": 1.0}


def test_evidence_covers_go_and_javascript_runners():
    runs = lambda cmd: test_evidence(_traced([_sh(cmd, "ok")], patch=None, workdir="/app"))["rollout/test_runs"]
    for cmd in ("cd /app && go test ./pkg/... -run TestFoo", "npm test", "npm run test -- --watch=false", "yarn test src/a.test.ts", "pnpm test", "npx jest src/a.test.js", "npx vitest run"):
        assert runs(cmd) == 1.0, cmd
    for cmd in ("go build ./...", "npm install", "npm run build", "node scripts/gen.js", "grep -rn latest src/", "cat jest.config.js", "npm install --save-dev mocha"):
        assert runs(cmd) == 0.0, cmd


def test_annotate_writes_the_test_metrics():
    ep = _traced([SRC, PYTEST, _sh(r"sed -i 's/- \[ \] 1/- [x] 1/' /tmp/agent-os/specs/x/tasks.md")])
    annotate([ep])
    assert ep.metrics["rollout/test_after_last_edit"] == 1.0  # a ticked task list is no edit of the code
    assert ep.metrics["rollout/test_valid_after_last_edit"] == 1.0
    assert ep.metrics["rollout/test_runs"] == 1.0 and ep.metrics["rollout/test_runs_valid"] == 1.0
