"""speckit_bug compliance: ``rubric.yaml`` -- the SDLC IF study's scored rubric, maintained with ``../constraints.yaml``
(``sdlc_if/constraints.py``) -- interpreted by the common rubric engine.

The ``speckit_bug/*`` signals come from the rubric (``speckit_bug/compliance`` is the reward signal); the
``speckit_bug.*`` plugin kinds the rubric uses (the Checks Performed table, the check scripts, the report reads,
the repository's new files, URL fetches) live next to it in ``checks.py``.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="speckit_bug", plugins=[f"{__package__}.checks"])
