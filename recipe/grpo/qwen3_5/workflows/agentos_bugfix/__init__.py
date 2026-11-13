"""Agent OS v2.1.1 spec pipeline for fixes: agentos_v2 with the steps a fix does not need cut out, as a ``WorkflowSpec``.

Cut from agentos_v2 (``CHANGES.md``, ``build.py``): the product-context step, everything about visuals, the roadmap
step and report section, the frontend and backend standards, the user-stories section, the empty
``implementation/`` folder; the web-application tasks example is one group plus the test-review group. The
wording that held for one dataset only (``<issue_description>``, "the issue", ``/testbed``) is neutral. The rest is
agentos_v2's:

    docs/              -> /agent-os: core-workflow.md + commands/<cmd>/<cmd>.md for the four commands
    build.py           agentos_v2's render plus this workflow's cuts (``--list``; ``--check`` for drift)
    instruction.md     joined to the task text
    system-prompt.j2   openhands-sdk's system prompt with its procedure section rewritten
    LICENSE-agent-os   upstream MIT license (buildermethods/agent-os 6a6495111e9f, tag v2.1.1)
    CHANGES.md         what differs from agentos_v2, and why

Upstream, a person attaches one compiled command document per chat turn and answers the agent's questions
in between; here one session runs the four commands, and ``core-workflow.md`` (hand-written, no upstream
counterpart) strings them together. The coding standards are written out inside each command document,
so they are not shipped separately. Spec files go to ``/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`` --
upstream's dated folder with the name the agent picks, moved outside the repository so neither the diff
nor the agent's ``git clean`` reaches it. No rounds. ``reward/`` holds the generated compliance rubric
(``agentos_bugfix/*`` signals); until ``reward/rubric.yaml`` exists the workflow has no scorer and reports resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.eval import Evaluation

    return Evaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/agent-os",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=("/tmp/agent-os",),
    scorers={"openhands-sdk": _scorer} if (HERE / "reward" / "rubric.yaml").is_file() else {},
    reward_signal="agentos_bugfix/compliance",
)
