"""aidlc_v4_ifeval compliance: aidlc_v4_gen's rubric on this workflow's copy of the documents (+ the
no-re-read item, + the judging fixes of ``build.py``) with per-layer pass rates.

The evaluation reads the ``aidlc_ifeval/layer*/<L>`` signals (``workflow_rubric/layers.py``);
``aidlc_ifeval/compliance`` is the rubric's usual mean. aidlc_v4's hand-written scorer runs next to it,
as in aidlc_v4_gen, so the legacy ``aidlc/*`` signals are logged on the same rollouts.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation
from recipe.grpo.qwen3_5.workflows.aidlc_v4.reward.evaluator import collect_artifacts, score

HERE = Path(__file__).resolve().parent


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(HERE / "rubric.yaml", prefix="aidlc_ifeval", plugins=[f"{__package__}.checks"], extra=[(collect_artifacts, score)], layers_path=HERE / "layers.yaml")
