"""AI-DLC for evaluation: ``aidlc_v4``'s documents, instruction and system prompt, scored by its rubric
bands plus the artifacts' claims against the trajectory (``reward/content_checks.py``).

    docs/, instruction.md, system-prompt.j2, reward/{rubric/, episode.py}
        copied byte-identical from ``workflows/aidlc_v4`` at commit 4c3ee52c, so the agent sees the
        same workflow (``SPEC.fingerprint`` equals aidlc_v4's) and the rubric parses runs the same way
    reward/compliance.py
        copied from aidlc_v4, with the stage gate's "a real test suite ran" read by ``evidence.py``
    reward/{evidence.py, content_checks.py, _claims.py, evaluator.py}
        the evaluation verifier's own evidence readings, the content checks (commit 1b68a8e7) and the
        scorer that adds them and the milestone-1 evaluation rubric's items

The copy is the point: this is the evaluation verifier, fixed apart from the training one, so a change
to ``aidlc_v4`` (its documents, its reward) does not move the numbers measured with this package. Do
not import from ``aidlc_v4`` here, and do not edit the copied files to follow it. Where this verifier
reads a run differently from the vendored rubric, the change is in ``reward/evidence.py``.

Use it where aidlc_v4 would be used (``recipe.workflow.name=aidlc_v4_eval``, ``--agent-kwargs
workflow=aidlc_v4_eval``, ``rescore_compliance.py --workflow aidlc_v4_eval``) to get the
``aidlc/content*`` / ``aidlc/check/*`` signals next to ``aidlc/*``. The reward signal is unchanged
(``aidlc/compliance``).
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec
from .reward.rubric.artifacts import ARTIFACT_DIR

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric or the checks.
    from .reward.evaluator import AidlcEvalEvaluation

    return AidlcEvalEvaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/ai-dlc",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer},
    reward_signal="aidlc/compliance",
    output_dirs=(ARTIFACT_DIR,),
)
