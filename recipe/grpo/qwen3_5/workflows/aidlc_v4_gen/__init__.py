"""AI-DLC with a generated verifier: aidlc_v4's documents, scored by a rubric generated from them.

Everything the agent sees -- the documents (/ai-dlc), the instruction and the openhands-sdk system
prompt -- is aidlc_v4's own files, referenced rather than copied: the point of this workflow is to
compare the generated rubric (``aidlc_gen/*`` signals) with aidlc_v4's hand-written scorer on the same
runs, which only holds if both read the same documents. ``reward/`` holds the generated rubric, whose
lock pins the aidlc_v4 files it was generated from.

Until ``reward/rubric.yaml`` exists the workflow has no scorer: runs report resolve rate only, and a
rewarded variant stops at start-up (train.py ``_workflow_reward``) instead of training without the signal.
"""

from __future__ import annotations

from pathlib import Path

from .. import aidlc_v4
from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.eval import Evaluation

    return Evaluation()


SPEC = WorkflowSpec(
    docs_dir=aidlc_v4.SPEC.docs_dir,
    container_dir=aidlc_v4.SPEC.container_dir,
    entry_doc=aidlc_v4.SPEC.entry_doc,
    instruction_file=aidlc_v4.SPEC.instruction_file,
    system_prompt=dict(aidlc_v4.SPEC.system_prompt),
    scorers={"openhands-sdk": _scorer} if (HERE / "reward" / "rubric.yaml").is_file() else {},
    reward_signal="aidlc_gen/compliance",
)
