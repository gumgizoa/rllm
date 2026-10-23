"""agentos_v2 compliance: ``rubric.train.yaml`` -- the generated ``rubric.yaml`` with the SDLC IF study's changes
(``../constraints.yaml``, built by ``sdlc_if/build.py``) -- interpreted by the common rubric engine.

The ``agentos_v2/*`` signals come from the rubric (``agentos_v2/compliance`` is the reward signal); the ``agentos_v2.*``
plugin kinds the rubric uses (requirements.md's assumed answers, tasks.md's task groups and ticks, the check scripts
under the spec folder's ``checks/``, implement-tasks PHASE 3 and its report against the test runs, the spec folder,
the repository's new files) live next to it in ``checks.py``.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.train.yaml"), prefix="agentos_v2", plugins=[f"{__package__}.checks"])
