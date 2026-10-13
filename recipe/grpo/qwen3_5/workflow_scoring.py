"""Score a workflow's compliance next to the task verifier, from inside the live sandbox.

Every workflow scorer has the same shape; only two functions are the workflow's own:

    collect(sandbox) -> data
        Read what the workflow left in the sandbox (stage artifacts, ...). Runs **before** the
        verifier, so nothing the verifier does to the machine can change it.
    score(task, episode, data) -> {name: value}
        The compliance signals, each in [0, 1] and named ``<workflow>/...``; one of them is the
        workflow's ``WorkflowSpec.reward_signal``.
    from_outputs(workflow_outputs) -> data   (optional)
        ``collect``'s result rebuilt from a saved episode's ``artifacts["workflow_outputs"]``
        (``run_artifacts.py``), so ``scripts/rescore_compliance.py`` scores a finished run the way
        the live sandbox was scored.

:class:`ComplianceEvaluation` is an evaluation policy for ``SandboxTaskHooks``: it resolves the
task's own verifier exactly as the default policy does and wraps it with those two functions
(:class:`ComplianceEvaluator`). The wrapper never changes the reward -- the verifier's ``reward``,
``is_correct`` and ``metadata`` (which carries the evaluator-failure ``termination_reason`` the
engine reads) pass through unchanged and the signals are appended. Signals land in
``trajectory.signals`` and ``episode.metrics``; train.py's grouping hook decides whether
``reward_signal`` enters the reward (``recipe.workflow.compliance_reward``), so the same scorer
serves a logged-only arm, a rewarded one, and ``rllm eval``.

A failure to collect or to score is logged and the verifier's output is returned as-is: an episode
without the signals gets no compliance term, rather than a wrong one.

A workflow plugs in as ``ComplianceEvaluation(collect, score, name[, from_outputs])`` registered in
``workflows.WORKFLOWS[...].scorers`` (see ``workflows/aidlc_v4/reward/evaluator.py``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rllm.eval.types import EvalOutput, Signal
from rllm.hooks import FromTaskEvaluation

logger = logging.getLogger(__name__)

Collect = Callable[[Any], Any]
Score = Callable[[Any, Any, Any], dict[str, float]]


class ComplianceEvaluator:
    """The task's verifier with a workflow's compliance signals appended."""

    def __init__(self, inner, sandbox, collect: Collect, score: Score, name: str):
        self.inner = inner
        self.sandbox = sandbox
        self.collect = collect
        self.score = score
        self.name = name

    def evaluate(self, task, episode) -> EvalOutput:
        try:
            data, collected = self.collect(self.sandbox), True
        except Exception as e:
            logger.warning("%s compliance: collection failed: %s", self.name, e)
            data, collected = None, False
        out = self.inner.evaluate(task, episode)
        if not collected:
            return out
        try:
            signals = self.score(task, episode, data)
        except Exception:
            logger.warning("%s compliance: scoring failed for %s", self.name, getattr(task, "id", "?"), exc_info=True)
            return out
        appended = [Signal(name, float(value)) for name, value in signals.items()]
        return EvalOutput(reward=out.reward, is_correct=out.is_correct, signals=list(out.signals) + appended, metadata=out.metadata)


class ComplianceEvaluation(FromTaskEvaluation):
    """``FromTaskEvaluation`` with the verifier wrapped; tasks with no sandbox are left alone."""

    def __init__(self, collect: Collect, score: Score, name: str, from_outputs: Callable[[dict[str, str]], Any] | None = None):
        self.collect = collect
        self.score = score
        self.name = name
        self.from_outputs = from_outputs

    def resolve(self, task, sandbox, kind, config):
        inner = super().resolve(task, sandbox, kind, config)
        return inner if sandbox is None else ComplianceEvaluator(inner, sandbox, self.collect, self.score, self.name)
