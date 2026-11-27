"""speckit_bug_repro compliance: speckit_bug's rubric, plus the items this workflow adds (``items.yaml``).

The signals keep speckit_bug's names (``speckit_bug/compliance``, ``speckit_bug/penalty`` ...), so a run of the
variant is read with the same keys as a run of the original. What differs is ``speckit_bug/penalty``: the mean of
four items here (speckit_bug's three and ``assess.penalty.reproduction.before_remediation``), of three there.
speckit_bug's own ``rubric.yaml`` is read as it is and not written to.
"""

from pathlib import Path

import yaml

from recipe.grpo.qwen3_5.workflow_rubric import checks as registry
from recipe.grpo.qwen3_5.workflow_rubric import schema
from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation

from ...speckit_bug.reward import eval as base
from . import checks

ITEMS = Path(__file__).with_name("items.yaml")


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(base.__file__).with_name("rubric.yaml"), prefix="speckit_bug", plugins=[base.checks.__name__, checks.__name__], inputs=checks.inputs, post=checks.post)
        self.rubric.items.extend(schema.Item.from_dict(d) for d in yaml.safe_load(ITEMS.read_text())["items"])
        schema.validate(self.rubric)
        registry.validate_params(self.rubric)
