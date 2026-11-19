"""agentos_bugfix compliance: ``rubric.yaml`` interpreted by the common rubric engine.

The rubric is agentos_v2's with the items of the cut steps removed (``../derive_rubric.py``); the ``agentos_bugfix/*``
signals come from it (``agentos_bugfix/compliance`` is the reward signal). Its plugin kinds are agentos_v2's, registered
under ``agentos_bugfix.*`` in ``checks.py``.

Beside the rubric, ``penalty.py`` reports ``agentos_bugfix/penalty`` and its items: four about the files tasks.md names
(against the final patch and the task's reference fix) and seven about the test behaviour of implement-tasks
(``penalty_tests.py``). They are logged, not part of ``compliance``.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation

from . import penalty


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="agentos_bugfix", plugins=[f"{__package__}.checks"], inputs=penalty.inputs, post=penalty.post)
