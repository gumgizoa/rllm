"""Workflows a harness can be made to follow, by name.

A workflow is what goes into the sandbox on top of the task -- documents, an instruction joined
to the task text, a replacement system prompt -- plus how to score whether the agent followed it.
:class:`workflow_harness.WorkflowMixin` reads a :class:`WorkflowSpec` from :data:`WORKFLOWS` by
the harness's ``workflow`` attribute (``--agent-kwargs workflow=<name>``); adding a workflow is an
entry here, not a harness class.

Two fields are keyed by harness name (``OpenHandsSdkHarness.name`` etc.), because what they hold
is specific to one agent:

``system_prompt``
    The replacement is the harness's own default prompt with its procedure section rewritten,
    so each (workflow, harness) pair needs its own template.
``scorers``
    A compliance scorer parses the agent's tool calls, whose names and arguments differ per
    harness (the AI-DLC rubric has an openhands front end only). A harness with no entry gets
    resolve rate only, never a score computed by the wrong parser.

AI-DLC
    The documents, the instruction and the system prompt live together under ``aidlc/`` and are
    versioned with the recipe, because the three name each other by absolute path
    (``/ai-dlc/...``) and by what a stage produces (artifacts under ``/tmp/swe-bench-pro/``). A
    set copied from elsewhere at run time would let one of them drift from the other two. The
    openhands-sdk template is the SDK 1.42.1 default with its ``<PROBLEM_SOLVING_WORKFLOW>``
    section rewritten; a different ``SDK_VERSION`` needs re-extraction.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RECIPE_DIR = Path(__file__).resolve().parent
AIDLC_DIR = RECIPE_DIR / "aidlc"


@dataclass(frozen=True)
class WorkflowSpec:
    """One workflow: what to put in the sandbox and how to score compliance.

    docs_dir          documents uploaded to ``container_dir`` (prompt files beside them stay out)
    container_dir     absolute path the instruction and the system prompt point at
    entry_doc         a file ``docs_dir`` must hold, checked before any sandbox exists
    instruction_file  joined to the task text (before or after it); ``None`` = task text alone
    system_prompt     harness name -> template replacing that harness's system prompt
    scorers           harness name -> factory of an evaluation policy for ``SandboxTaskHooks``
    reward_signal     the scorers' signal in [0, 1] that train.py folds into the reward
                      (``recipe.workflow.compliance_reward``); the others are logged only
    """

    docs_dir: Path
    container_dir: str
    entry_doc: str
    instruction_file: Path | None = None
    system_prompt: Mapping[str, Path] = field(default_factory=dict)
    scorers: Mapping[str, Callable[[], Any]] = field(default_factory=dict)
    reward_signal: str | None = None


def _aidlc_scorer():
    # Imported on use, under whichever name this module was loaded by: ``workflows`` when
    # train.py has the recipe directory on sys.path, ``recipe.grpo.qwen3_5.workflows`` under
    # ``rllm eval --agent recipe.grpo.qwen3_5.workflow_harness:...``.
    if __package__:
        from .aidlc_reward.evaluator import AidlcEvaluation
    else:
        from aidlc_reward.evaluator import AidlcEvaluation
    return AidlcEvaluation()


WORKFLOWS: dict[str, WorkflowSpec] = {
    "aidlc": WorkflowSpec(
        docs_dir=AIDLC_DIR,
        container_dir="/ai-dlc",
        entry_doc="core-workflow.md",
        instruction_file=AIDLC_DIR / "instruction.md",
        system_prompt={"openhands-sdk": AIDLC_DIR / "system-prompt.j2"},
        scorers={"openhands-sdk": _aidlc_scorer},
        reward_signal="aidlc/compliance",
    ),
}


def get_workflow(name: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise ValueError(f"unknown workflow {name!r}; registered: {sorted(WORKFLOWS)}") from None
