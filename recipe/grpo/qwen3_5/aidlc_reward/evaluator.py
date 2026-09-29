"""Score AI-DLC compliance next to the task verifier, from inside the live sandbox.

``AidlcEvaluation`` is an evaluation policy for ``SandboxTaskHooks``: it resolves the task's own
verifier exactly as the default policy does and wraps it. The wrapper

1. reads the stage artifacts (``/tmp/swe-bench-pro/NN-*.md``) out of the sandbox **before** the
   verifier runs, so nothing the verifier does to the machine can change them;
2. runs the verifier untouched -- its ``reward``, ``is_correct`` and ``metadata`` (which carries
   the evaluator-failure ``termination_reason`` the engine reads) pass through unchanged;
3. appends the compliance signals as ``aidlc/*`` ``Signal``s.

It never changes the reward. Signals land in ``trajectory.signals`` and ``episode.metrics``;
``train.py``'s grouping hook decides whether the compliance mean enters the reward
(``recipe.aidlc.reward``), so the same evaluator serves a logged-only arm and a rewarded one.

Reading the files from the sandbox, rather than reconstructing them from the shell commands that
wrote them as the offline harbor scoring had to, removes that scoring's one measurement gap: a
heredoc or ``printf`` write whose text could not be recovered scored the stage 0.

A failure to compute compliance is logged and the verifier's output is returned as-is: an
episode without ``aidlc/compliance`` gets no compliance term, rather than a wrong one.
"""

from __future__ import annotations

import base64
import logging

from rllm.eval.types import EvalOutput, Signal
from rllm.hooks import FromTaskEvaluation

from .compliance import compliance
from .episode import episode_to_run
from .rubric import artifacts as A

logger = logging.getLogger(__name__)

_MARK = "@@AIDLC "
# base64 keeps the files intact through exec's text channel; `; true` because exec raises on a
# non-zero exit and a run that wrote no artifact is not an error.
_COLLECT = f'for f in {A.ARTIFACT_DIR}/0[1-5]-*.md; do [ -f "$f" ] || continue; printf \'{_MARK}%s\\n\' "$f"; base64 -w0 "$f"; printf \'\\n\'; done; true'


def parse_collected(output: str) -> dict[str, str]:
    files, path = {}, None
    for line in (output or "").splitlines():
        if line.startswith(_MARK):
            path = line[len(_MARK) :].strip()
            continue
        if path is not None:
            if path in A.ARTIFACT_PATHS:
                files[path] = base64.b64decode(line.strip() or b"").decode("utf-8", errors="replace")
            path = None
    return files


class AidlcComplianceEvaluator:
    def __init__(self, inner, sandbox):
        self.inner = inner
        self.sandbox = sandbox

    def _collect_artifacts(self) -> dict[str, str] | None:
        try:
            return parse_collected(self.sandbox.exec(_COLLECT, timeout=60, user="root"))
        except Exception as e:
            logger.warning("AI-DLC artifact collection failed: %s", e)
            return None

    def evaluate(self, task, episode) -> EvalOutput:
        artifacts = self._collect_artifacts()
        out = self.inner.evaluate(task, episode)
        if artifacts is None:
            return out
        try:
            c = compliance(episode_to_run(episode, artifacts, instance_id=str(getattr(task, "id", ""))))
        except Exception:
            logger.warning("AI-DLC compliance scoring failed for %s", getattr(task, "id", "?"), exc_info=True)
            return out
        facts = c["facts"]
        signals = [Signal(f"aidlc/{k}", float(v)) for k, v in c["signals"].items()]
        signals += [
            Signal("aidlc/compliance", float(c["mean"])),
            Signal("aidlc/order_chain", float(c["order"]["chain"])),
            Signal("aidlc/order_prefix", float(c["order"]["prefix"])),
            Signal("aidlc/docs_read", float(len(facts["stage_docs_read"]))),
            Signal("aidlc/artifacts_written", float(len(artifacts))),
            Signal("aidlc/ran_real_test", float(bool(facts["ran_real_test_suite"]))),
        ]
        return EvalOutput(reward=out.reward, is_correct=out.is_correct, signals=list(out.signals) + signals, metadata=out.metadata)


class AidlcEvaluation(FromTaskEvaluation):
    """``FromTaskEvaluation`` with the verifier wrapped; tasks with no sandbox are left alone."""

    def resolve(self, task, sandbox, kind, config):
        inner = super().resolve(task, sandbox, kind, config)
        return inner if sandbox is None else AidlcComplianceEvaluator(inner, sandbox)
