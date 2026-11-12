"""AI-DLC v5: aidlc_v4 with the rules that the inference-time resolve-drop analysis tied to the
drop loosened or reverted toward the original AWS AI-DLC (see CHANGES.md in this directory).

Changes vs aidlc_v4 (docs/ only, plus one scorer fact):
  * test files: ADD-only instead of a total ban (new test function in an existing module, or a
    new module); existing test lines are still never modified or removed
  * Stage 5 reruns the baseline selection PLUS the test modules covering every changed file
  * Stage 5 report records the command AND the runner's output line for each run;
    "Regressions: none" without a recorded run is invalid
  * Stage 1 does a repository-wide symbol/error-string search and lists referencing files left out
  * Stage 4 states that a recorded deviation is the normal way a plan is corrected; a file the
    code points to is opened and checked, not skipped because the plan omitted it
  * core: the run ends only after Stage 5 (a stage-boundary progress report is not an end);
    artifacts are written with the file-editing tool, not a shell heredoc
  * scorer: hygiene penalty keys on ``diff_test_files_modified`` (existing test lines changed),
    not on any test file being touched

AI-DLC: the five-stage workflow (reverse engineering -> build and test), as a ``WorkflowSpec``.

    docs/              -> /ai-dlc: core-workflow.md, rule-details/01..05-*.md
    instruction.md     the pointer joined to the task text ("Follow the workflow defined in
                       /ai-dlc/core-workflow.md ..."), as in the Harbor runs
                       (harbor-extension experiments/aidlc/variants/ai-dlc.md)
    system-prompt.j2   openhands-sdk's system prompt with its procedure section rewritten
    reward/            compliance scoring: order_v6 + stage bands s1..s5, mean aidlc/compliance

The documents, the instruction and the system prompt are versioned together because the three
name each other by absolute path (``/ai-dlc/...``) and by what a stage produces (artifacts under
``/tmp/swe-bench-pro/``); a set copied from elsewhere at run time would let one of them drift
from the other two. The openhands-sdk template is the SDK 1.42.1 default with its
``<PROBLEM_SOLVING_WORKFLOW>`` section rewritten; a different ``SDK_VERSION`` needs re-extraction.
"""

from __future__ import annotations

from pathlib import Path

from ..spec import WorkflowSpec
from .reward.rubric.artifacts import ARTIFACT_DIR

HERE = Path(__file__).resolve().parent


def _scorer():
    # Imported on use: a run without the workflow never loads the rubric.
    from .reward.evaluator import AidlcEvaluation

    return AidlcEvaluation()


SPEC = WorkflowSpec(
    docs_dir=HERE / "docs",
    container_dir="/ai-dlc",
    entry_doc="core-workflow.md",
    instruction_file=HERE / "instruction.md",
    system_prompt={"openhands-sdk": HERE / "system-prompt.j2"},
    scorers={"openhands-sdk": _scorer},
    reward_signal="aidlc/compliance",
    output_dirs=(ARTIFACT_DIR,),
)
