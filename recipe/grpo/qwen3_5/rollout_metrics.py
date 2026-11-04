"""Per-rollout training metrics that the reward curves hide: ``rollout/*`` in ``episode.metrics``.

Written by train.py's grouping hook after the reward is shaped, so ``batch/rollout/*`` (train) and
the validation summaries average them over the episodes that carry each one:

* ``rollout/turns_before_edit`` -- steps before the first repository edit (every step when none):
  how much the policy explores before it changes code;
* ``rollout/test_runs`` -- terminal commands that run a test runner;
* ``rollout/compliance_solved`` / ``rollout/compliance_unsolved`` -- the workflow's compliance
  signal, split by the verifier's verdict. Compliance in unsolved rollouts rising toward the
  solved ones' is form-filling, not following the workflow;
* ``rollout/solved_below_group_mean`` -- on solved rollouts: 1 when the shaped reward is under the
  mean of its GRPO group (same task), i.e. a solve pushed down by the compliance term.

Edits and test runs are read off each step's raw response (``chat_completions[-1].tool_calls``),
the form the training harness records. An edit is a ``file_editor`` create / str_replace / insert
on a non-document path, or a shell write (``sed -i``, ``git apply``, a redirect or ``tee`` into a
non-document path). The patterns are the ones ``tasks/2026-10-28-if-reward-resolve-gap`` used on
the evaluation episodes, so training curves read against that analysis.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

TEST_RE = re.compile(r"\b(pytest|py\.test|python[0-9.]* -m pytest|tox\b|runtests\.py|python[0-9.]* .*tests?/|unittest|nosetests|make test)")
REDIRECT_RE = re.compile(r"(?<![0-9&])>>?\s*['\"]?([^\s'\"|;&<>]+)")
TEE_RE = re.compile(r"\btee\s+(?:-a\s+)?['\"]?([^\s'\"|;&]+)")
INPLACE_RE = re.compile(r"\b(sed|perl)\s+(-[a-zA-Z]*i|-i)")
APPLY_RE = re.compile(r"\b(git apply|patch\s+-p|git checkout --|git stash)")
DOC_EXT = (".md", ".txt", ".rst", ".yaml", ".yml", ".json")
EDIT_COMMANDS = ("str_replace", "insert", "create", "undo_edit")


def _is_doc(path: str) -> bool:
    return path.endswith(DOC_EXT) and "/test" not in path


def _tool_calls(step: Any) -> list[tuple[str, dict]]:
    """``(name, arguments)`` of the step's tool calls, from its raw response message."""
    messages = getattr(step, "chat_completions", None) or []
    response = messages[-1] if messages else None
    if not isinstance(response, dict):
        return []
    out = []
    for tc in response.get("tool_calls") or []:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"command": args}
        out.append((str(fn.get("name") or ""), args if isinstance(args, dict) else {}))
    return out


def _edits_code(name: str, args: dict) -> bool:
    if name == "file_editor":
        return args.get("command") in EDIT_COMMANDS and not _is_doc(str(args.get("path") or ""))
    if name != "terminal":
        return False
    cmd = str(args.get("command") or "")
    if INPLACE_RE.search(cmd) or APPLY_RE.search(cmd):
        return True
    targets = [m.group(1) for m in REDIRECT_RE.finditer(cmd)] + [m.group(1) for m in TEE_RE.finditer(cmd)]
    targets = [t for t in targets if t != "/dev/null"]
    return bool(targets) and not all(_is_doc(t) for t in targets)


def behavior(episode: Any) -> dict[str, float]:
    steps = [s for traj in episode.trajectories for s in traj.steps]
    first_edit, tests = None, 0
    for i, step in enumerate(steps):
        for name, args in _tool_calls(step):
            if name == "terminal" and TEST_RE.search(str(args.get("command") or "")):
                tests += 1
            if first_edit is None and _edits_code(name, args):
                first_edit = i
    return {"rollout/turns_before_edit": float(len(steps) if first_edit is None else first_edit), "rollout/test_runs": float(tests)}


def _compliance(episode: Any) -> float | None:
    for traj in episode.trajectories:
        for name, value in (traj.signals or {}).items():
            if name.endswith("/compliance"):
                return float(value)
    return None


def annotate(episodes: list[Any]) -> None:
    """Write the ``rollout/*`` metrics into each episode's ``metrics`` (rewards already shaped)."""
    groups: dict[str, list[float]] = defaultdict(list)
    for ep in episodes:
        for traj in ep.trajectories:
            if traj.reward is not None:
                groups[ep.task_id].append(float(traj.reward))
    for ep in episodes:
        ep.metrics.update(behavior(ep))
        c = _compliance(ep)
        if c is not None:
            ep.metrics["rollout/compliance_solved" if ep.is_correct else "rollout/compliance_unsolved"] = c
        rewards = [float(t.reward) for t in ep.trajectories if t.reward is not None]
        if ep.is_correct and rewards and groups[ep.task_id]:
            mean = sum(groups[ep.task_id]) / len(groups[ep.task_id])
            ep.metrics["rollout/solved_below_group_mean"] = 1.0 if min(rewards) < mean else 0.0
