"""openspec_ff compliance: ``rubric.train.yaml`` -- the generated ``rubric.yaml`` with the SDLC IF study's changes
(``../constraints.yaml``, built by ``sdlc_if/build.py``) -- interpreted by the common rubric engine.

The ``openspec_ff/*`` signals come from the rubric (``openspec_ff/compliance`` is the reward signal); the plugin
kinds the rubric uses live next to it in ``checks.py``: the ``openspec_ff.*`` kinds (the CLI calls and their
outcome, the archive step, ADDED-only deltas, the verify report, test / check-script evidence) and the
``openspec.*`` format kinds it imports from ``workflows/openspec`` (delta specs, capabilities, main specs, tasks,
file reads).
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.train.yaml"), prefix="openspec_ff", plugins=[f"{__package__}.checks"])
