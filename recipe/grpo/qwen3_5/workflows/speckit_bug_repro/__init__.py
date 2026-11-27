"""speckit_bug with the reproduction run moved in front of the plan (see CHANGES.md in this directory).

    docs/    speckit_bug's documents with one of them edited: stages/01-assess.md has the agent run what
             the issue reports against the unchanged code before it proposes a remediation. core-workflow.md,
             stages/02-fix.md and stages/03-test.md are byte-identical to speckit_bug's
             (tests/test_repro_variants.py holds them to that)

Everything else is speckit_bug's own, taken from its ``SPEC`` rather than copied: the instruction, the system
prompt, the container directory (``/speckit``), the report directory and the scorer. The scorer therefore
still emits ``speckit_bug/*`` signals, scored against speckit_bug's rubric -- which has no item for the new
instruction, so compliance with it is read from the trajectories, not from a signal. The assessment keeps
speckit_bug's headings and field lines, so the rubric's items apply as they did.

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

SPEC = dataclasses.replace(speckit_bug.SPEC, docs_dir=HERE / "docs")
