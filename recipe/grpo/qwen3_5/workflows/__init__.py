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

Several workflows in one run: ``workflow`` names more than one (a list, or ``a+b`` from
``--agent-kwargs``, which splits on commas), ``none`` among them for the plain harness. Each task then
runs under one of them -- the one its ``metadata[WORKFLOW_KEY]`` names, else
:func:`assign_workflow`'s pick.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from . import agentos_v2, aidlc_v4, aidlc_v4_gen, openspec_ff, speckit_bug, speckit_sdd
from .spec import WorkflowSpec

# The plain harness as a member of a mix: nothing uploaded, the task text untouched.
NONE = "none"
# Task metadata naming the workflow a task must run under (train.py pins the validation set with it).
WORKFLOW_KEY = "recipe_workflow"

WORKFLOWS: dict[str, WorkflowSpec] = {
    "aidlc_v4": aidlc_v4.SPEC,
    "aidlc_v4_gen": aidlc_v4_gen.SPEC,
    "speckit_bug": speckit_bug.SPEC,
    "openspec_ff": openspec_ff.SPEC,
    "speckit_sdd": speckit_sdd.SPEC,
    "agentos_v2": agentos_v2.SPEC,
}


def get_workflow(name: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise ValueError(f"unknown workflow {name!r}; registered: {sorted(WORKFLOWS)}") from None


def parse_workflows(value) -> tuple[str, ...]:
    """``workflow`` as a caller gives it -> registered names in order, :data:`NONE` for the plain harness.

    ``None`` / ``""`` -> ``()``; ``"aidlc_v4"`` -> one name; a list (or ListConfig), or a string joining
    names with ``+``, -> several. ``none`` / ``null`` (any case) is :data:`NONE`. An unknown or repeated
    name is an error.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return ()
    items = value.split("+") if isinstance(value, str) else list(value)
    names: list[str] = []
    for item in items:
        name = NONE if item is None or str(item).strip().lower() in ("", "none", "null") else str(item).strip()
        if name != NONE:
            get_workflow(name)
        if name in names:
            raise ValueError(f"workflow {name!r} named twice in {value!r}")
        names.append(name)
    return tuple(names)


def assign_workflow(task_id: str, names: Sequence[str], seed: int = 0) -> str:
    """One of ``names`` for ``task_id``: uniform, i.i.d. across tasks, and fixed for the run.

    A hash of ``seed`` and the id, not ``random``: the same task gets the same workflow in every epoch,
    after a resume and in every one of its rollouts, so a GRPO group shares one workflow. ``names`` is
    taken as a set, so listing them in another order changes nothing.
    """
    pool = sorted(names)
    digest = hashlib.sha256(f"{seed}:{task_id}".encode()).digest()
    return pool[int.from_bytes(digest[:8], "big") % len(pool)]


__all__ = ["NONE", "WORKFLOWS", "WORKFLOW_KEY", "WorkflowSpec", "assign_workflow", "get_workflow", "parse_workflows"]
