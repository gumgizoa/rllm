"""bmad_build_auto compliance: the generated ``rubric.yaml`` interpreted by the common rubric engine, with the
evaluation layers of ``layers.yaml`` (``bmad/layer*/<L>`` signals). ``bmad/compliance`` is the rubric's mean.

The parent run is the orchestrator's conversation only (``workflow_rubric/trace/episode.py`` splits the
sub-agents off); the ``bmad.*`` kinds in ``checks.py`` read the ``task`` calls and the lenses' final messages.
"""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation

HERE = Path(__file__).resolve().parent


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(HERE / "rubric.yaml", prefix="bmad", plugins=[f"{__package__}.checks"], layers_path=HERE / "layers.yaml")
