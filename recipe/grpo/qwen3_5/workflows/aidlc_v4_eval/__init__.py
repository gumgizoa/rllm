"""AI-DLC with content checks: ``aidlc_v4``'s documents, instruction and system prompt, scored by its rubric
bands plus the artifacts' claims against the trajectory (``reward/content_checks.py``).

Use it where aidlc_v4 would be used (``recipe.workflow.name=aidlc_v4_eval``, ``--agent-kwargs
workflow=aidlc_v4_eval``) to get the ``aidlc/content*`` / ``aidlc/check/*`` signals next to ``aidlc/*``.
The reward signal is unchanged (``aidlc/compliance``).
"""

from __future__ import annotations

from pathlib import Path

from ..aidlc_v4 import HERE as AIDLC_V4
from ..aidlc_v4.reward.rubric.artifacts import ARTIFACT_DIR
from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric or the checks.
    from .reward.evaluator import AidlcEvalEvaluation

    return AidlcEvalEvaluation()


SPEC = WorkflowSpec(
    docs_dir=AIDLC_V4 / "docs",
    container_dir="/ai-dlc",
    entry_doc="core-workflow.md",
    instruction_file=AIDLC_V4 / "instruction.md",
    system_prompt={"openhands-sdk": AIDLC_V4 / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer},
    reward_signal="aidlc/compliance",
    output_dirs=(ARTIFACT_DIR,),
)
