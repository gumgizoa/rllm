"""AI-DLC as the held-out workflow of the SDLC instruction-following study: its own copy of aidlc_v4's
documents, scored by aidlc_v4_gen's rubric (re-anchored to the copy) plus per-layer pass rates.

    docs/, instruction.md, system-prompt.j2   aidlc_v4's files with the edits below; the container
                                              paths (/ai-dlc, /tmp/swe-bench-pro) are unchanged
    reward/                                   rubric, layers and the build that derives them

The copy removes contradictions inside AI-DLC that a run following the text literally would be
penalised for (study doc ``06_item_template_audit.md``): a re-read the stage documents asked for
against core-workflow's "do not re-read" (BT:47, CG:17), the final-change check placed after the
single write of the Stage 5 artifact (BT Steps 6-7 swapped), the change list against Stage 5 fixes
(BT:103), the reproduction script under Changed Files (CG:54), "nowhere else" against Unmet
requirements and Regressions (CW:40, BT:98), and three generic system-prompt instructions the workflow
forbids (explore the whole codebase, install dependencies, confirm a plan with the user).
aidlc_v4 and aidlc_v4_gen keep the original files.

What ``reward/`` adds: one ``log_only`` item (no re-read of the agent's own artifacts) and
``layers.yaml``, which assigns items to the evaluation layers -- seen template (L1), conflict with a
training workflow (L1C), unseen template (L2F, L2M) -- and reports a must-only pass rate per layer
(``aidlc_ifeval/layer*/<L>``).
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
    docs_dir=HERE / "docs",
    container_dir=aidlc_v4.SPEC.container_dir,
    entry_doc=aidlc_v4.SPEC.entry_doc,
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer} if (HERE / "reward" / "rubric.yaml").is_file() else {},
    reward_signal="aidlc_ifeval/compliance",
    output_dirs=aidlc_v4.SPEC.output_dirs,
)
