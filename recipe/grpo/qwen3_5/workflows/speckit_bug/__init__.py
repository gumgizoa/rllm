"""Spec Kit bug workflow: assess -> fix -> test (GitHub Spec Kit's ``bug`` extension), as a ``WorkflowSpec``.

    docs/              -> /speckit: core-workflow.md, stages/01-assess.md 02-fix.md 03-test.md
    build.py           regenerates docs/stages/ from spec-kit's extensions/bug/commands/ and names
                       every edit to the upstream text (``--list``; ``--check`` for drift)
    instruction.md     the pointer joined to the task text ("Follow the workflow defined in
                       /speckit/core-workflow.md ...")
    system-prompt.j2   openhands-sdk's system prompt with its procedure section rewritten
    LICENSE-spec-kit   upstream MIT license (spec-kit 0443760542e7, bug extension 1.0.1)

Spec Kit runs one command per turn with a person in between; here one session runs all of it, so
``core-workflow.md`` (hand-written, no upstream counterpart) strings the stages together. Reports go
to ``/tmp/speckit/bugs/issue/`` -- outside the repository, so neither the diff nor the agent's
``git clean`` reaches them -- with the slug fixed to ``issue``. A failed or partial test loops back
to fix, at most three rounds (``fix.md``/``test.md``, ``fix-2.md``/``test-2.md``, ``fix-3.md``/
``test-3.md``). The documents, the instruction and the system prompt name each other by absolute
path, so they are versioned together. No compliance scorer yet: resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent

SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/speckit",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=("/tmp/speckit",),
)
