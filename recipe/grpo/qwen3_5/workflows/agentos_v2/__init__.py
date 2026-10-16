"""Agent OS v2.1.1 spec pipeline: shape-spec -> write-spec -> create-tasks -> implement-tasks, as a ``WorkflowSpec``.

    docs/              -> /agent-os: core-workflow.md + commands/<cmd>/<cmd>.md for the four commands
    build.py           renders docs/commands/ with upstream's own installer from the v2.1.1 tag, after the
                       tagged edits to the pre-render sources (``--list``; ``--check`` for drift)
    instruction.md     joined to the task text
    system-prompt.j2   openhands-sdk's system prompt with its procedure section rewritten
    LICENSE-agent-os   upstream MIT license (buildermethods/agent-os 6a6495111e9f, tag v2.1.1)
    porting/           the stage record (survey, gaps, decisions, changes, smoke)

Upstream, a person attaches one compiled command document per chat turn and answers the agent's questions
in between; here one session runs the four commands, and ``core-workflow.md`` (hand-written, no upstream
counterpart) strings them together. The coding standards are written out inside each command document,
so they are not shipped separately. Spec files go to ``/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`` --
upstream's dated folder with the name the agent picks, moved outside the repository so neither the diff
nor the agent's ``git clean`` reaches it. No rounds, no compliance scorer yet: resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent

SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/agent-os",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=("/tmp/agent-os",),
)
