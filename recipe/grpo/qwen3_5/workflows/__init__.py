"""Workflows a harness can be made to follow, by name.

A workflow is what goes into the sandbox on top of the task -- documents, an instruction joined
to the task text, a replacement system prompt -- plus how to score whether the agent followed it.
:class:`workflow_harness.WorkflowMixin` reads a :class:`WorkflowSpec` from :data:`WORKFLOWS` by
the harness's ``workflow`` attribute (``recipe.workflow.name`` / ``--agent-kwargs workflow=``).

Each workflow is a package here, ``workflows/<name>/``, holding everything of its own and
exposing its ``SPEC``:

    docs/              the documents, uploaded as they are to the spec's ``container_dir``
    instruction*.md    joined to the task text
    system-prompt.j2   per harness, replacing that harness's system prompt
    reward/            its compliance scorer (``workflow_scoring.ComplianceEvaluation``)

Adding a workflow is such a package and one entry in :data:`WORKFLOWS`; no harness class.
"""

from __future__ import annotations

from . import aidlc_v4, openspec_ff, speckit_bug, speckit_sdd
from .spec import WorkflowSpec

WORKFLOWS: dict[str, WorkflowSpec] = {
    "aidlc_v4": aidlc_v4.SPEC,
    "speckit_bug": speckit_bug.SPEC,
    "openspec_ff": openspec_ff.SPEC,
    "speckit_sdd": speckit_sdd.SPEC,
}


def get_workflow(name: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise ValueError(f"unknown workflow {name!r}; registered: {sorted(WORKFLOWS)}") from None


__all__ = ["WORKFLOWS", "WorkflowSpec", "get_workflow"]
