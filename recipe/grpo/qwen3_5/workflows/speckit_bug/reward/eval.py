"""speckit_bug compliance: the generated ``rubric.yaml`` interpreted by the common rubric engine.

The ``speckit_bug/*`` signals come from the rubric (``speckit_bug/compliance`` is the reward signal); the
``speckit_bug.*`` plugin kinds the rubric uses (the Checks Performed table, the check scripts, the report reads,
the repository's new files, URL fetches) live next to it in ``checks.py``, with the ``inputs`` hook that
looks up the task's gold source files. The ``post`` hook is the common one (``workflow_rubric/penalty.py``): it folds
the log-only ``*.penalty.*`` items into ``speckit_bug/penalty`` (never part of ``speckit_bug/compliance``).
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation

from . import checks


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="speckit_bug", plugins=[f"{__package__}.checks"], inputs=checks.inputs, post=checks.post)
