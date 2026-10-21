"""aidlc_v4_gen compliance: the generated ``rubric.yaml`` interpreted by the common rubric engine.

The ``aidlc_gen/*`` signals come from the rubric (``aidlc_gen/compliance`` is the reward signal);
aidlc_v4's hand-written scorer runs next to it as an independent extra, so the legacy ``aidlc/*``
signals are logged on the same rollouts for comparison and neither scorer can take the other down.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation
from recipe.grpo.qwen3_5.workflows.aidlc_v4.reward.evaluator import collect_artifacts, score


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="aidlc_gen", plugins=[f"{__package__}.checks"], extra=[(collect_artifacts, score)])
