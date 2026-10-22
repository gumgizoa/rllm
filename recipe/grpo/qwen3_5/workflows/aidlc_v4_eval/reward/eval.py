"""aidlc_v4_eval's verifier: ``rubric.yaml`` interpreted by the common rubric engine (``workflow_rubric``).

The rubric's items are the workflow's atomic rules, each with the document lines it comes from, its
category (P procedure, F form, E execution, C consistency, R forbidden action, Q content, A report
accuracy) and its stage; ``checks.py`` registers the kinds that measure them. The engine's
``kind_matrix`` aggregate turns the items into ``aidlc/cat/<C><n>``, ``aidlc/kind/<C>`` and the total
``aidlc/score`` (the reward signal); each scored item is also reported under its id
(``aidlc/check/*``, ``aidlc/rule/*``, ``aidlc/atom/*``, ``aidlc/form/*``, ``aidlc/proc/*``,
``aidlc/run/*``, ``aidlc/judge/*``), and ``checks.post`` adds the diagnostics. ``extra`` scorers run
beside it: the workflow's spec passes the milestone-1 one (``legacy/score.py``), so nothing here
imports ``legacy/``.
"""

from __future__ import annotations

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation

from . import checks


class Evaluation(RubricEvaluation):
    def __init__(self, extra=()):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="aidlc", plugins=[f"{__package__}.checks"], extra=extra, inputs=checks.inputs, post=checks.post)
