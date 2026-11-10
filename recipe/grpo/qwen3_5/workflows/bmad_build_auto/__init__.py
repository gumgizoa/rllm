"""bmad_build_auto: BMAD-METHOD's ``bmad-build-auto`` skill (one unattended build iteration), as a ``WorkflowSpec``.

    docs/              -> /bmad-build-auto: core-workflow.md (upstream workflow.md, with the run's setting written
                       for this port), stages/step-01..04 (clarify-and-route, plan, implement, review),
                       spec-template.md, review-prompts/{edge-case-hunter,verification-gap}.md and
                       references/{claims-check,deletion-check}.md -- the renderer's output, built once
    build.py           regenerates docs/ from the BMAD-METHOD checkout and names every edit (``--list``, ``--check``)
    instruction.md     joined to the task text; system-prompt.j2 has the SDK procedure section rewritten
    LICENSE-bmad-method  upstream MIT license + trademark notice (BMAD-METHOD v6.12.2, 10db8f35)
    porting/           the stage record (survey, rules, gaps, decisions, plan, changes)

An **evaluation** workflow of the SDLC instruction-following study: one spec -> implementation by a subagent ->
staged diff -> four review subagents -> triage, loopback (at most 5) or patches -> ``## Auto Run Result``. The
spec lives at ``/tmp/bmad/implementation-artifacts/spec-<slug>.md`` and the diff at ``/tmp/bmad/diff/<slug>.diff``,
outside the repository (porting/03-decisions.md D-5); ``/tmp/bmad`` is collected as the workflow's output. The
subagents are the openhands-sdk ``task`` tool, which the runner adds for this workflow only
(``runner_env`` -> ``OPENHANDS_SDK_EXTRA_TOOLS=task``, D-7). No scorer yet: ``reward/`` (constraints, rubric,
layers) is stage 4b; until ``reward/rubric.yaml`` exists the workflow reports resolve rate only.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec

HERE = Path(__file__).resolve().parent
ARTIFACTS_ROOT = "/tmp/bmad"  # build.ARTIFACTS_ROOT: implementation-artifacts/ and diff/ under it

def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.eval import Evaluation

    return Evaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/bmad-build-auto",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    output_dirs=(ARTIFACTS_ROOT,),
    runner_env={"OPENHANDS_SDK_EXTRA_TOOLS": "task"},  # D-7: the subagent tool, this workflow only
    scorers={"openhands-sdk": _scorer} if (HERE / "reward" / "rubric.yaml").is_file() else {},
    reward_signal="bmad/compliance",
)
