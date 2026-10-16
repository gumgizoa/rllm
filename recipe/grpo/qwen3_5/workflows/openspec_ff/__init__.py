"""OpenSpec OPSX workflow: explore -> ff -> apply -> verify -> archive (Fission-AI/OpenSpec), as a ``WorkflowSpec``.

    docs/              -> /opsx: core-workflow.md (hand-written), stages/00-explore.md 01-ff.md 02-apply.md
                       03-verify.md (explore writes nothing; its summary feeds ff, porting/03-decisions.md
                       "Explore extension")
    sandbox/schemas/   the forked schema ``spec-driven-sandbox`` (schema.yaml + templates), uploaded beside
                       the documents and installed into /openspec/schemas/ by setup.sh
    build.py           regenerates docs/stages/ and the fork from the OpenSpec checkout and names every
                       edit to the upstream text (``--list``; ``--check`` for drift)
    setup.sh           before the agent: ``openspec`` wrapper on PATH, ``openspec init --tools none`` at /,
                       the fork selected in /openspec/config.yaml, refuses a repo with its own openspec/
    agent-image-extra.Dockerfile
                       node + ``@fission-ai/openspec@1.14.1`` under /opt/rllm/agent/node, baked into an
                       agent image of this workflow's own
    instruction.md     joined to the task text; system-prompt.j2 has the SDK procedure section rewritten
    LICENSE-openspec   upstream MIT license (OpenSpec 9111a7654d78, npm 1.14.1)

Unlike the other ports, the upstream CLI runs in the sandbox (porting/03-decisions.md D-1): status,
paths, per-artifact instructions, validation and archive are OpenSpec's own, and the text it serves
from ``schema.yaml`` is changed through upstream's project-local schema fork (D-4). The planning tree
``/openspec`` sits outside the repository and is collected as the workflow's output; the change is
always ``issue``. ``reward/`` holds the generated compliance rubric (``openspec_ff/*`` signals); until
``reward/rubric.yaml`` exists the workflow has no scorer and reports resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent
FORK_NAME = "spec-driven-sandbox"
FORK_STAGED = f"/opt/rllm/openspec_ff/{FORK_NAME}"  # setup.sh copies it into /openspec/schemas/
CONFIG_STAGED = "/opt/rllm/openspec_ff/config.yaml"  # setup.sh installs it as /openspec/config.yaml


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.eval import Evaluation

    return Evaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/opsx",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=("/openspec",),
    agent_image_extra=(HERE / "agent-image-extra.Dockerfile").read_text(encoding="utf-8"),
    sandbox_files={
        FORK_STAGED: HERE / "sandbox" / "schemas" / FORK_NAME,
        CONFIG_STAGED: HERE / "sandbox" / "openspec-config.yaml",  # G10-7: becomes /openspec/config.yaml
    },
    setup_script=HERE / "setup.sh",
    scorers={"openhands-sdk": _scorer} if (HERE / "reward" / "rubric.yaml").is_file() else {},
    reward_signal="openspec_ff/compliance",
)
