"""speckit_sdd compliance: the generated ``rubric.yaml`` interpreted by the common rubric engine.

The ``speckit_sdd/*`` signals come from the rubric (``speckit_sdd/compliance`` is the reward signal); the plugin kinds
the rubric uses -- the shipped scripts' runs, the verification scripts' red / green runs, tasks.md's ticks and appended
Convergence phase, the converge round reports -- live next to it in ``checks.py``, which also registers spec_kit's
``speckit.*`` kinds.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="speckit_sdd", plugins=[f"{__package__}.checks"])
