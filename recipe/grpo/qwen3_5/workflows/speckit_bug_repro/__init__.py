"""speckit_bug with the reproduction run moved in front of the plan (see CHANGES.md in this directory).

    docs/    speckit_bug's documents with one of them edited: stages/01-assess.md has the agent run what
             the issue reports against the unchanged code before it proposes a remediation. core-workflow.md,
             stages/02-fix.md and stages/03-test.md are byte-identical to speckit_bug's
             (tests/test_repro_variants.py holds them to that)

    reward/  the scorer: speckit_bug's rubric with one item added (``items.yaml``), the penalty item for the new
             instruction -- the repository's code was run before the assessment proposed a remediation
             (``checks.py``). It is the fourth item of ``speckit_bug/penalty``; compliance is speckit_bug's

Everything else is speckit_bug's own, taken from its ``SPEC`` rather than copied: the instruction, the system
prompt, the container directory (``/speckit``) and the report directory. The signals keep speckit_bug's names
(``speckit_bug/*``). The assessment keeps speckit_bug's headings and field lines, so the rubric's items apply as
they did.

``docs/stages/`` is edited by hand from speckit_bug's and is not covered by ``speckit_bug/build.py``.

Use it where speckit_bug would be used (``recipe.workflow.name=speckit_bug_repro``, ``--agent-kwargs
workflow=speckit_bug_repro``). ``SPEC.fingerprint`` differs from speckit_bug's, so episodes of the two are
told apart by ``artifacts["workflow"]``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import speckit_bug

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.eval import Evaluation

    return Evaluation()


SPEC = dataclasses.replace(speckit_bug.SPEC, docs_dir=HERE / "docs", scorers={"openhands-sdk": _scorer} if speckit_bug.SPEC.scorers else {})
