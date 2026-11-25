"""Per-rollout training metrics that the reward curves hide: ``rollout/*`` in ``episode.metrics``.

Written by train.py's grouping hook after the reward is shaped, so ``batch/rollout/*`` (train) and
the validation summaries average them over the episodes that carry each one:

* ``rollout/turns_before_edit`` -- steps before the first repository edit (every step when none):
  how much the policy explores before it changes code;
* ``rollout/test_runs`` / ``rollout/test_runs_valid`` -- test-runner invocations as the workflow scorers
  read them (:func:`test_evidence`): every one, and the ones whose own output shows tests of the repository
  ran. The gap between the two is tests the policy tried to run and did not;
* ``rollout/test_after_last_edit`` / ``rollout/test_valid_after_last_edit`` -- on rollouts that changed
  source code: 1 when such an invocation / a valid one comes after the last source change, 0 when the
  final code was never tested. A rollout without a source change does not carry them, so the batch mean
  is over the rollouts that changed code;
* ``rollout/compliance_solved`` / ``rollout/compliance_unsolved`` -- the workflow's compliance
  signal, split by the verifier's verdict. Compliance in unsolved rollouts rising toward the
  solved ones' is form-filling, not following the workflow;
* ``rollout/solved_below_group_mean`` -- on solved rollouts: 1 when the shaped reward is under the
  mean of its GRPO group (same task), i.e. a solve pushed down by the compliance term.

``turns_before_edit`` is read off each step's raw response (``chat_completions[-1].tool_calls``), the
form the training harness records. An edit there is a ``file_editor`` create / str_replace / insert on
a non-document path, or a shell write (``sed -i``, ``git apply``, a redirect or ``tee`` into a
non-document path) -- the patterns ``tasks/2026-10-28-if-reward-resolve-gap`` used on the evaluation
episodes.

The test metrics were pattern matches until 2026-11-24 (a command naming a runner counted: ``cat
tox.ini``, ``pip install pytest``; ``sed -i`` on a task list, ``git stash`` or a redirect into ``/tmp``
counted as an edit). Under the same names they are now the scorers' reading, so ``rollout/test_runs``
and ``rollout/test_after_last_edit`` of a run logged before that date are not comparable with later ones.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

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
    first_edit = next((i for i, step in enumerate(steps) if any(_edits_code(name, args) for name, args in _tool_calls(step))), None)
    return {"rollout/turns_before_edit": float(len(steps) if first_edit is None else first_edit)}


def _workdir(episode: Any) -> str | None:
    """The repository root the task declares (``task.metadata["workdir"]``), read as the scorers read it."""
    from recipe.grpo.qwen3_5.workflow_rubric.evaluation import _task_workdir

    return _task_workdir(getattr(episode, "task", None))


def test_evidence(episode: Any) -> dict[str, float]:
    """The ``rollout/test_*`` metrics read the way the workflow scorers read test runs (``workflow_rubric``), for
    any rollout -- a workflow's or the plain harness's. Empty when the episode cannot be read (a harness without a
    trace front end, or anything that raises): a metric is never worth a training step.

    The trace goes through the scorers' own path (``trace.episode_to_run`` -> ``facts.build`` with a rubric that
    holds nothing), so a test run here is ``evidence.runs_from``'s: the runner is the verb of a command segment.
    ``valid`` adds what the scorers ask of evidence -- the runner's own summary in the output with at least one
    test run, targets that existed before the agent wrote them, inside the repository. The last change is
    ``facts.source_change_steps``: the last authored write to a source file of the final change (the recorded patch
    when the episode has one), so a test file, a report, a ticked task list or ``git stash`` is no change. A run of
    the change's own command counts when the write comes first in it; a run made while the change was stashed away
    (``results.stash_states``) tested the old code and does not.
    """
    try:
        from recipe.grpo.qwen3_5.workflow_rubric import facts as F
        from recipe.grpo.qwen3_5.workflow_rubric import results as R
        from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, Collected, EvalContext
        from recipe.grpo.qwen3_5.workflow_rubric.evaluation import _episode_diff
        from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric
        from recipe.grpo.qwen3_5.workflow_rubric.trace.episode import episode_to_run

        try:
            run = episode_to_run(episode)
        except ValueError:  # a harness with no trace front end: its tool calls are not read by another's profile
            return {}
        rubric = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
        collected = Collected(workdir=_workdir(episode), diff=_episode_diff(episode), mode="offline")
        facts = F.build(rubric, run, collected)
        ctx = EvalContext(rubric=rubric, run=run, collected=collected, facts=facts)
        runs = [r for r in facts.runs if r.kind == "test"]
        out = {"rollout/test_runs": float(len(runs)), "rollout/test_runs_valid": float(sum(1 for r in runs if r.valid))}
        last = F.last_change_write(ctx)
        if collected.workdir is None or last is None or last is UNKNOWN:
            return out  # no source change the trace shows: nothing to have tested after
        authored = [e for e in facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_generated(e.path)]
        before, marks = R.stash_states(facts.commands, sorted({int(e.step) for e in authored}), {e.path for e in authored if not F.is_test_path(e.path)})
        after = [r for r in runs if (r.step > last or (r.step == last and r.after_write_same_call)) and not R.run_stashed(r, before, marks)]
        out["rollout/test_after_last_edit"] = 1.0 if after else 0.0
        out["rollout/test_valid_after_last_edit"] = 1.0 if any(r.valid for r in after) else 0.0
        return out
    except Exception:  # noqa: BLE001 -- the grouping hook must not fail on a metric
        logger.warning("rollout/test_* metrics skipped for %s", getattr(episode, "task_id", "?"), exc_info=True)
        return {}


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
        ep.metrics.update(test_evidence(ep))
        c = _compliance(ep)
        if c is not None:
            ep.metrics["rollout/compliance_solved" if ep.is_correct else "rollout/compliance_unsolved"] = c
        rewards = [float(t.reward) for t in ep.trajectories if t.reward is not None]
        if ep.is_correct and rewards and groups[ep.task_id]:
            mean = sum(groups[ep.task_id]) / len(groups[ep.task_id])
            ep.metrics["rollout/solved_below_group_mean"] = 1.0 if min(rewards) < mean else 0.0
