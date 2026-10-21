"""AI-DLC's two pieces for ``workflow_scoring.ComplianceEvaluation``: what to collect, how to score.

``collect_artifacts`` reads the stage artifacts (``/tmp/swe-bench-pro/NN-*.md``) out of the
sandbox; the wrapper calls it **before** the verifier runs, so nothing the verifier does to the
machine can change them. ``score`` turns them and the episode into the ``aidlc/*`` signals: the six
compliance signals and their mean (``aidlc/compliance``, the workflow's reward signal), the
content checks (``aidlc/content*``, ``aidlc/check/*``) and diagnostics. Everything else -- running the verifier untouched, appending the signals, falling back
to the verifier's output when collection or scoring fails -- is ``workflow_scoring``'s.

Reading the files from the sandbox, rather than reconstructing them from the shell commands that
wrote them as the offline harbor scoring had to, removes that scoring's one measurement gap: a
heredoc or ``printf`` write whose text could not be recovered scored the stage 0.
"""

from __future__ import annotations

import base64

from recipe.grpo.qwen3_5.workflow_scoring import ComplianceEvaluation, ComplianceEvaluator

from .compliance import compliance
from .content_checks import content_checks, parsed_artifacts
from .episode import episode_to_run
from .rubric import artifacts as A

NAME = "AI-DLC"

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


def collect_artifacts(sandbox) -> dict[str, str]:
    """Container path -> content of each stage artifact the run left in the sandbox."""
    return parse_collected(sandbox.exec(_COLLECT, timeout=60, user="root"))


def artifacts_from_outputs(outputs: dict[str, str]) -> dict[str, str]:
    """``collect_artifacts``'s result from a saved episode's ``workflow_outputs`` (all of ``ARTIFACT_DIR``)."""
    return {path: text for path, text in outputs.items() if path in A.ARTIFACT_PATHS}


def score(task, episode, artifacts: dict[str, str]) -> dict[str, float]:
    """The ``aidlc/*`` signals for one episode, given the artifacts read out of its sandbox.

    ``aidlc/compliance`` and the six signals behind it are the rubric's (form and order). The
    ``aidlc/content*`` signals are the content checks (``content_checks.py``): whether the artifacts'
    claims hold against the trajectory, as family means and per check (``aidlc/check/<name>``, each
    1 / 0.5 / 0; a check nothing bears on is left out). Logged only, so far.
    """
    run = episode_to_run(episode, artifacts, instance_id=str(getattr(task, "id", "")))
    c = compliance(run)
    facts = c["facts"]
    cc = content_checks(run, parsed_artifacts(run))
    return {
        **{f"aidlc/{k}": float(v) for k, v in c["signals"].items()},
        "aidlc/compliance": float(c["mean"]),
        "aidlc/order_chain": float(c["order"]["chain"]),
        "aidlc/order_prefix": float(c["order"]["prefix"]),
        "aidlc/docs_read": float(len(facts["stage_docs_read"])),
        "aidlc/artifacts_written": float(len(artifacts)),
        "aidlc/ran_real_test": float(bool(facts["ran_real_test_suite"])),
        **({"aidlc/content": float(cc["content"])} if cc["content"] is not None else {}),
        **{f"aidlc/content_{fam}": float(v) for fam, v in cc["families"].items() if v is not None},
        "aidlc/content_contradictions": float(cc["contradictions"]),
        **{f"aidlc/check/{k}": float(v) for k, v in cc["checks"].items() if v is not None},
    }


class AidlcEvalComplianceEvaluator(ComplianceEvaluator):
    """The task's verifier with the ``aidlc/*`` signals appended."""

    def __init__(self, inner, sandbox):
        super().__init__(inner, sandbox, collect_artifacts, score, NAME)


class AidlcEvalEvaluation(ComplianceEvaluation):
    """The ``aidlc_v4_eval`` workflow's scorer (``workflows.WORKFLOWS["aidlc_v4_eval"].scorers``): aidlc_v4's signals plus the content checks."""

    def __init__(self):
        super().__init__(collect_artifacts, score, NAME, artifacts_from_outputs)
