"""AI-DLC v5 for evaluation: aidlc_v4_eval with the rules that the inference-time resolve-drop analysis tied
to the drop loosened or reverted toward the original AWS AI-DLC (see CHANGES.md in this directory), scored by
the workflow's atomic rules (``reward/rubric.yaml``) on the common rubric engine.

    docs/, instruction.md, system-prompt.j2
        aidlc_v4_eval's (= aidlc_v4's) with the v5 document edits (CHANGES.md); instruction.md and
        system-prompt.j2 are byte-identical to aidlc_v4_eval's
    reward/
        the verifier, copied from ``workflows/aidlc_v4_eval/reward`` and moved to the v5 documents: the
        rule set (``reward/ruleset.yaml``) follows the edited lines, the rules v5 reverses are re-judged
        (test files: add only; stage 5 also reruns the modules covering the changed files) and the rules
        v5 adds are new judgments (CHANGES.md, "채점기"). Its headline is ``aidlc/score``, the kind x stage
        matrix's total (``aidlc/cat/*``, ``aidlc/kind/*``)
    legacy/
        the milestone-1 scoring as aidlc_v4_eval keeps it (``aidlc/compliance``, ``aidlc/rubric``), with
        v5's one scorer edit (the hygiene penalty keys on existing test lines changed, not on a test file
        touched), for comparison with the v5 evaluations reported before this package became a verifier;
        reward/ never imports it

Do not import from ``aidlc_v4_eval`` here: a change there must not move the numbers measured with this
package, and the other way round.

Use it where aidlc_v4_eval would be used (``recipe.workflow.name=aidlc_v5``, ``--agent-kwargs
workflow=aidlc_v5``, ``rescore_compliance.py --workflow aidlc_v5``). The reward signal (and
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
