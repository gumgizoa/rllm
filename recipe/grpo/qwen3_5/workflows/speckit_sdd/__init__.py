"""Spec Kit's core spec-driven development chain (github/spec-kit), as a ``WorkflowSpec``.

    docs/              -> /speckit-sdd: core-workflow.md (hand-written) and stages/01-specify.md 02-plan.md
                       03-tasks.md 04-implement.md 05-converge.md (from templates/commands/*.md)
    sandbox/specify/   -> /tmp/speckit-sdd/.specify: upstream's own scripts/bash/*.sh (byte for byte, +x),
                       the spec/plan/tasks/checklist templates (converted) and memory/constitution.md (the
                       unfilled template ``specify init`` leaves). /tmp/speckit-sdd is the Spec Kit project
                       root; the scripts find it from their own location, whatever the agent's cwd
    build.py           regenerates docs/stages/ and sandbox/specify/ from the spec-kit checkout and names
                       every edit to the upstream text (``--list``; ``--check`` for drift)
    instruction.md     joined to the task text; system-prompt.j2 has the SDK procedure section rewritten
    LICENSE-spec-kit   upstream MIT license (spec-kit 0443760542e7)
    porting/           the stage record (survey, gaps, decisions, changes)

The minimal chain specify -> plan -> tasks -> implement <-> converge (at most two converge rounds), for
feature-development tasks (porting/03-decisions.md, usage note). The feature directory is fixed,
``/tmp/speckit-sdd/specs/001-issue``, outside the repository; it and ``.specify/feature.json`` are the
workflow's outputs (the shipped scripts and templates are not). No compliance scorer yet: resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = "/tmp/speckit-sdd"  # build.PROJECT_ROOT; the Spec Kit project root the scripts resolve

SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/speckit-sdd",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=(f"{PROJECT_ROOT}/specs", f"{PROJECT_ROOT}/.specify/feature.json"),
    sandbox_files={f"{PROJECT_ROOT}/.specify": HERE / "sandbox" / "specify"},
    setup_script=HERE / "setup.sh",  # G7-8: colourless jq on the agent's PTY
)
