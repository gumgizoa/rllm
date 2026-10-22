"""AI-DLC for evaluation: ``aidlc_v4``'s documents, instruction and system prompt, scored by the workflow's
atomic rules (``reward/rubric.yaml``) on the common rubric engine.

    docs/, instruction.md, system-prompt.j2
        copied byte-identical from ``workflows/aidlc_v4`` at commit 4c3ee52c, so the agent sees the same
        workflow (``SPEC.fingerprint`` equals aidlc_v4's) and aidlc_v4 runs can be rescored with this
    reward/
        the verifier: ``rubric.yaml`` (the rules, each with its category, stage and document lines),
        ``checks.py`` (their check kinds), ``eval.py``, and the readings they use (see reward/__init__.py).
        Its headline is ``aidlc/score``, the kind x stage matrix's total (``aidlc/cat/*``, ``aidlc/kind/*``)
    legacy/
        the milestone-1 scoring (aidlc_v4's vendored rubric and compliance signals, ``aidlc/compliance``,
        ``aidlc/rubric``), run beside it for comparison with earlier evaluations; reward/ never imports it

The copy is the point: this is the evaluation verifier, fixed apart from the training one, so a change
to ``aidlc_v4`` (its documents, its reward) does not move the numbers measured with this package. Do
not import from ``aidlc_v4`` here.

Use it where aidlc_v4 would be used (``recipe.workflow.name=aidlc_v4_eval``, ``--agent-kwargs
workflow=aidlc_v4_eval``, ``rescore_compliance.py --workflow aidlc_v4_eval``). The reward signal (and
``workflow/compliance`` in a mixed evaluation) is ``aidlc/score``.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec
from .reward.skeleton import ARTIFACT_DIR

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric or the checks. The milestone-1
    # signals (legacy/) ride along as an extra scorer, for comparison with earlier evaluations.
    from .legacy.score import SCORER as MILESTONE1
    from .reward.eval import Evaluation

    return Evaluation(extra=[MILESTONE1])


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/ai-dlc",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer},
    reward_signal="aidlc/score",
    output_dirs=(ARTIFACT_DIR,),
)
