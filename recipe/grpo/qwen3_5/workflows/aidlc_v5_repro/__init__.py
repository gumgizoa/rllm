"""aidlc_v5 with the reported behavior run in Stage 1, before the plan (see CHANGES.md in this directory).

    docs/    aidlc_v5's documents with three of them edited: rule-details/01-reverse-engineering.md has the
             agent run what the task description reports against the unmodified code and record it
             (``## Observed Behavior``); rule-details/03-code-generation-planning.md has the plan account for
             it; core-workflow.md names it where it lists what Stage 1 produces. The other three rule detail
             files are byte-identical to aidlc_v5's (tests/test_repro_variants.py holds them to that)

Everything else is aidlc_v5's own, taken from its ``SPEC`` rather than copied: the instruction, the system
prompt, the container directory (``/ai-dlc``), the artifact directory and the scorer. The scorer therefore
still emits ``aidlc/*`` signals, scored against aidlc_v5's rule set -- which has no rule for the new step, so
compliance with it is read from the trajectories, not from a signal. ``## Observed Behavior`` is a section
the Stage 1 skeleton does not know: it is listed under ``unknown_sections`` and neither scored nor penalized.

Use it where aidlc_v5 would be used (``recipe.workflow.name=aidlc_v5_repro``, ``--agent-kwargs
workflow=aidlc_v5_repro``). ``SPEC.fingerprint`` differs from aidlc_v5's, so episodes of the two are told
apart by ``artifacts["workflow"]``.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from .. import aidlc_v5

HERE = Path(__file__).resolve().parent

SPEC = dataclasses.replace(aidlc_v5.SPEC, docs_dir=HERE / "docs")
