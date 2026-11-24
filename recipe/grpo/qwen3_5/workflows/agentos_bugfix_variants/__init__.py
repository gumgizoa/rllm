"""Instruction variants of agentos_bugfix, one ``WorkflowSpec`` each, for the resolve-rate experiment of 2026-11-24.

``build.py`` writes ``variants/<name>/`` from agentos_bugfix's documents with a set of candidate changes applied
(the candidates and what each one changes are listed there). A variant has agentos_bugfix's layout in the sandbox
(``/agent-os`` documents, spec folder under ``/tmp/agent-os``) and no compliance scorer: it reports resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent
VARIANTS = HERE / "variants"


def _spec(root: Path) -> WorkflowSpec:
    return WorkflowSpec(
        docs_dir=root / "docs",
        container_dir="/agent-os",
        entry_doc="overview.md",
        instruction_file=root / "instruction.md",
        system_prompt={"openhands-sdk": root / "system-prompt.j2"},
        output_dirs=("/tmp/agent-os",),
    )


SPECS: dict[str, WorkflowSpec] = {p.name: _spec(p) for p in sorted(VARIANTS.iterdir()) if (p / "docs" / "overview.md").is_file()} if VARIANTS.is_dir() else {}
