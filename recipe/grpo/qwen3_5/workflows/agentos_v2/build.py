"""Build ``docs/commands/`` from Agent OS v2.1.1 (buildermethods/agent-os, tag ``v2.1.1``).

    python -m recipe.grpo.qwen3_5.workflows.agentos_v2.build --upstream /path/to/agent-os-v2.1.1
    python -m recipe.grpo.qwen3_5.workflows.agentos_v2.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.agentos_v2.build --list                   # the edits, by tag

``--upstream`` is a checkout of the tag, not the repository's ``main`` (v3, a different layout). From a clone
of https://github.com/buildermethods/agent-os, a worktree of the tag does it without touching the clone:

    git -C /path/to/agent-os worktree add --detach /path/to/agent-os-v2.1.1 v2.1.1
    git -C /path/to/agent-os-v2.1.1 rev-parse HEAD    # 6a6495111e9f7f9cdab3c172814a7476e83a8ec9

(``git -C /path/to/agent-os worktree remove /path/to/agent-os-v2.1.1`` when done.) The tests look for it
at ``../agent-os-v2.1.1`` beside the rllm repo, or ``AGENT_OS_V2_DIR``.

Agent OS ships its commands as templates (``{{PHASE N: @...}}``, ``{{workflows/...}}``, ``{{standards/*}}``,
``{{UNLESS ...}}``) that its installer compiles into one file per command. A person runs ``project-install.sh``
in a project and attaches ``agent-os/commands/<cmd>/<cmd>.md`` in an agent app (Cursor and the like), one
command per turn. Here one session runs all four (shape-spec -> write-spec -> create-tasks -> implement-tasks),
so the build does what that person's install does, with the decided edits (porting/03-decisions.md G7-1 render):

1. copy the tag tree to a temporary ``$HOME/agent-os`` (the base install);
2. apply the tagged :data:`EDITS` to the **pre-render** sources (``profiles/default/commands/*/single-agent/*``,
   ``workflows/**``, ``standards/**``) with ``_port.convert`` -- an anchor must occur exactly once;
3. delete :data:`REMOVED` (G7-6) and set the base ``config.yml`` to the "other tools" path
   (:data:`CONFIG`: ``claude_code_commands: false``, ``agent_os_commands: true``);
4. run upstream's own ``scripts/project-install.sh`` offline in an empty project (needs bash and perl);
5. keep only the four top-level compiled files (G7-1 shipped files) and, in each, :func:`finish`: the
   ``@agent-os/standards/<dir>/<file>.md`` lines become that installed file's text under its path (G7-3), the
   ``agent-os/specs/`` prefix becomes ``/tmp/agent-os/specs/`` (G5-1, G5-3 rev), blank-line runs collapse,
   and no :data:`FORBIDDEN` string may survive.

``docs/core-workflow.md`` (hand-written; upstream has no document that strings the commands together) is not
built here. Tags: ``env`` closes a gap between Agent OS's setting and an unattended sandbox run without
changing what is asked; ``semantic`` changes what is asked. Every note starts with its gap ID. The engine is
``workflows/_port.py`` (its public functions only; the render steps live here).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .._port import Edit, Port, list_edits
from .._port import convert as _convert
from .._port import drift as _drift
from .._port import git_head as _git_head

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs"

# What docs/commands was built from (tag v2.1.1). Another commit only warns; the anchors decide.
UPSTREAM_COMMIT = "6a6495111e9f7f9cdab3c172814a7476e83a8ec9"

PROFILE = "profiles/default"
CONTAINER_DIR = "/agent-os"
SPECS_DIR = "/tmp/agent-os/specs/"
COMMANDS = ("shape-spec", "write-spec", "create-tasks", "implement-tasks")
COMMAND_DOCS = {cmd: f"{CONTAINER_DIR}/commands/{cmd}/{cmd}.md" for cmd in COMMANDS}

_CMD = PROFILE + "/commands/{}/single-agent/{}.md"
_WF = PROFILE + "/workflows/{}.md"

# key -> (pre-render path in the checkout, the same path in the temporary base install). Every source that
# ends up in the four commands; the installer reads them from the base install after the edits.
_PRE: dict[str, str] = {
    "shape": _CMD.format("shape-spec", "shape-spec"),
    "shape-1": _CMD.format("shape-spec", "1-initialize-spec"),
    "shape-2": _CMD.format("shape-spec", "2-shape-spec"),
    "write": _CMD.format("write-spec", "write-spec"),
    "tasks": _CMD.format("create-tasks", "create-tasks"),
    "tasks-1": _CMD.format("create-tasks", "1-get-spec-requirements"),
    "tasks-2": _CMD.format("create-tasks", "2-create-tasks-list"),
    "impl": _CMD.format("implement-tasks", "implement-tasks"),
    "impl-1": _CMD.format("implement-tasks", "1-determine-tasks"),
    "impl-2": _CMD.format("implement-tasks", "2-implement-tasks"),
    "impl-3": _CMD.format("implement-tasks", "3-verify-implementation"),
    "wf/initialize-spec": _WF.format("specification/initialize-spec"),
    "wf/research-spec": _WF.format("specification/research-spec"),
    "wf/write-spec": _WF.format("specification/write-spec"),
    "wf/create-tasks-list": _WF.format("implementation/create-tasks-list"),
    "wf/implement-tasks": _WF.format("implementation/implement-tasks"),
    "wf/verify-tasks": _WF.format("implementation/verification/verify-tasks"),
    "wf/update-roadmap": _WF.format("implementation/verification/update-roadmap"),
    "wf/run-all-tests": _WF.format("implementation/verification/run-all-tests"),
    "wf/verification-report": _WF.format("implementation/verification/create-verification-report"),
    "std/global/coding-style": PROFILE + "/standards/global/coding-style.md",
    "std/global/conventions": PROFILE + "/standards/global/conventions.md",
    "std/backend/migrations": PROFILE + "/standards/backend/migrations.md",
}
SOURCES: dict[str, tuple[str, str]] = {key: (path, path) for key, path in _PRE.items()}

# G7-6: not installed, so it drops out of every {{standards/*}} list and is never inlined.
REMOVED = (PROFILE + "/standards/global/tech-stack.md",)

# G7-1 (render): the base config.yml of the "other tools" install path (as scratchpad/agentos-render/run-install.sh).
CONFIG = (
    ("\nclaude_code_commands: true\n", "\nclaude_code_commands: false\n"),
    ("\nagent_os_commands: false\n", "\nagent_os_commands: true\n"),
)

_SEQUENCE = (
    "Carefully read and execute the instructions in the following files IN SEQUENCE, following their numbered file names."
    "  Only proceed to the next numbered instruction file once the previous numbered instruction has been executed."
)
_PHASES_IN_ORDER = "Carefully carry out the PHASE sections below in order, finishing one before the next."


def _next(doc: str, done: str) -> str:
    """G2-2: the end of a command, in place of its "display ... next step" block."""
    return f"## Next step\n\n{done}, open `{doc}` and continue with that command."


EDITS: tuple[Edit, ...] = (
    # ---- top-level command files: the preamble points at numbered files that are inlined below (G7-2)
    *(
        Edit(key, _SEQUENCE, _PHASES_IN_ORDER, "env", "G7-2: the numbered files are the PHASE sections below")
        for key in ("shape", "tasks", "impl")
    ),
    # ---- shape-spec PHASE 1: workflows/specification/initialize-spec.md
    Edit(
        "wf/initialize-spec",
        "1. **Get the description of the feature:** Receive it from the user or check the product roadmap",
        "1. **Get the description of the feature:** Take it from the issue in `<issue_description>`",
        "env",
        "G1-1: the feature description is the issue (responsibility line)",
    ),
    Edit(
        "wf/initialize-spec",
        "IF you were given a description of the feature, then use that to initiate a new spec.\n"
        "\n"
        "OTHERWISE follow these steps to get the description:\n"
        "\n"
        "1. Check `@agent-os/product/roadmap.md` to find the next feature in the roadmap.\n"
        "2. OUTPUT the following to user and WAIT for user's response:\n"
        "\n"
        "```\n"
        "Which feature would you like to initiate a new spec for?\n"
        "\n"
        "- The roadmap shows [feature description] is next. Go with that?\n"
        "- Or provide a description of a feature you'd like to initiate a spec for.\n"
        "```\n"
        "\n"
        "**If you have not yet received a description from the user, WAIT until user responds.**",
        "You were given a description of the feature: the issue in `<issue_description>` of the task message. "
        "Use that to initiate a new spec.",
        "env",
        "G1-1: input = the issue; the roadmap OTHERWISE branch and its output/wait block dropped",
    ),
    Edit(
        "wf/initialize-spec",
        "- `$SPEC_PATH/implementation/`\n\nLeave this folder empty, for now.",
        "- `$SPEC_PATH/implementation/`\n- `$SPEC_PATH/verifications/`\n\nLeave these folders empty, for now.",
        "env",
        "G5-5 (folders): the \"2 folders\" are implementation/ and verifications/ (the report's folder)",
    ),
    Edit(
        "wf/initialize-spec",
        " Later, this folder will be populated with reports documented by implementation agents.",
        "",
        "semantic",
        "G5-6: per-task implementation reports (removed in v2.1.0) are never written",
    ),
    Edit(
        "wf/initialize-spec",
        "### Step 4: Output Confirmation\n"
        "\n"
        "Return or output the following:\n"
        "\n"
        "```\n"
        "Spec folder initialized: `[spec-path]`\n"
        "\n"
        "Structure created:\n"
        "- planning/ - For requirements and specifications\n"
        "- planning/visuals/ - For mockups and screenshots\n"
        "- implementation/ - For implementation documentation\n"
        "\n"
        "Ready for requirements research phase.\n"
        "```",
        "### Step 4: Save Raw Idea\n"
        "\n"
        "Write the issue text from `<issue_description>` to `$SPEC_PATH/planning/initialization.md` exactly as given, "
        "without modification. PHASE 2 reads the raw idea from this file.",
        "env",
        "G1-2: the \"Save Raw Idea\" responsibility gets its step (initialization.md); G2-1: the output block it replaces dropped",
    ),
    Edit(
        "wf/initialize-spec",
        "- Pass the exact spec path back to the orchestrator\n",
        "",
        "env",
        "G7-5 (1): orchestrator clause dropped (G2-1)",
    ),
    # ---- shape-spec PHASE 2: workflows/specification/research-spec.md
    Edit(
        "wf/research-spec",
        "3. **Ask Clarifying Questions**: Generate targeted questions WITH visual asset request AND reusability check",
        "3. **Ask Clarifying Questions**: Generate targeted questions WITH a reusability check, and answer them yourself",
        "semantic",
        "G4-1: questions kept and self-answered (responsibility line); G4-3: no visuals request",
    ),
    Edit(
        "wf/research-spec",
        "Before generating questions, understand the broader product context:",
        "Before generating questions, understand the broader product context. This project has no product documents "
        "(mission, roadmap, tech stack), so take that context from the repository itself:",
        "env",
        "G1-3: product context from the repository in place of agent-os/product/*",
    ),
    Edit(
        "wf/research-spec",
        "1. **Read Product Mission**: Load `agent-os/product/mission.md` to understand:",
        "1. **Read Product Mission**: Read the repository's README to understand:",
        "env",
        "G1-3: README in place of mission.md",
    ),
    Edit(
        "wf/research-spec",
        "2. **Read Product Roadmap**: Load `agent-os/product/roadmap.md` to understand:",
        "2. **Read Product Roadmap**: Read the repository's documentation index (e.g. the table of contents of its "
        "`docs/`) to understand:",
        "env",
        "G1-3: docs index in place of roadmap.md",
    ),
    Edit(
        "wf/research-spec",
        "3. **Read Product Tech Stack**: Load `agent-os/product/tech-stack.md` to understand:",
        "3. **Read Product Tech Stack**: Read the repository's packaging and build metadata (e.g. `pyproject.toml`, "
        "`setup.py`, `setup.cfg`, `package.json`) to understand:",
        "env",
        "G1-3: packaging/build metadata in place of tech-stack.md",
    ),
    Edit(
        "wf/research-spec",
        "### Step 3: Generate First Round of Questions WITH Visual Request AND Reusability Check",
        "### Step 3: Generate First Round of Questions WITH Reusability Check",
        "env",
        "G4-3: no visuals request to a person (heading)",
    ),
    Edit(
        "wf/research-spec",
        "**CRITICAL: Always include the visual asset request AND reusability question at the END of your questions.**",
        "**CRITICAL: Always include the reusability question at the END of your questions.**",
        "env",
        "G4-3: no visuals request to a person",
    ),
    Edit(
        "wf/research-spec",
        "**Required output format:**",
        "**Required format:**",
        "semantic",
        "G4-1: the questions are written down, not output to anyone (G2-1)",
    ),
    Edit(
        "wf/research-spec",
        "\n"
        "\n"
        "**Visual Assets Request:**\n"
        "Do you have any design mockups, wireframes, or screenshots that could help guide the development?\n"
        "\n"
        "If yes, please place them in: `[spec-path]/planning/visuals/`\n"
        "\n"
        "Use descriptive file names like:\n"
        "- homepage-mockup.png\n"
        "- dashboard-wireframe.jpg\n"
        "- lofi-form-layout.png\n"
        "- mobile-view.png\n"
        "- existing-ui-screenshot.png\n"
        "\n"
        "Please answer the questions above and let me know if you've added any visual files or can point to similar "
        "existing features.",
        "",
        "env",
        "G4-3: the visuals request and the closing request to the person dropped; folder and mandatory ls kept",
    ),
    Edit(
        "wf/research-spec",
        "**OUTPUT these questions to the orchestrator and STOP - wait for user response.**",
        "**Nobody will answer these questions, so do not send them as a message. Answer each one yourself with the most "
        "plausible reading of the issue and the repository, and note the basis of each answer. Answer the reusability "
        "question by looking in the repository yourself (Step 4).**",
        "semantic",
        "G4-1: self-answered from the issue and repository, no STOP (G7-5 (1) orchestrator dropped)",
    ),
    Edit(
        "wf/research-spec",
        "After receiving user's answers from the orchestrator:\n\n1. Store the user's answers for later documentation",
        "After answering the questions yourself:\n\n1. Store your answers, each with its basis, for later documentation",
        "semantic",
        "G4-1: the agent's own answers (G7-5 (1) orchestrator dropped)",
    ),
    Edit(
        "wf/research-spec",
        "4. IF user provided paths or names of similar features:\n"
        "   - Make note of these paths/names for spec-writer to reference\n"
        "   - DO NOT explore them yourself (to save time), but DO document their names for future reference by the "
        "spec-writer.",
        "4. Answer the reusability question by looking in the repository for similar features, components and backend "
        "logic:\n"
        "   - Make note of these paths/names for the write-spec stage to reference\n"
        "   - Record each as `(assumed) <path> — <basis>`; if you find none, record \"No similar existing features "
        "identified for reference.\"",
        "semantic",
        "G4-2: reuse answered by a repository search, \"DO NOT explore them yourself\" dropped; G7-5 (2) spec-writer -> write-spec stage",
    ),
    Edit(
        "wf/research-spec",
        "**Reusability follow-ups:**\n"
        "   - If user didn't provide similar features but the spec seems common: \"This seems like it might share "
        "patterns with existing features. Could you point me to any similar forms/pages/logic in your app?\"\n"
        "- If provided paths seem incomplete you can ask something like: \"You mentioned [feature]. Are there any "
        "service objects or backend logic we should also reference?\"\n"
        "\n",
        "",
        "semantic",
        "G4-2: the reuse follow-ups' ask dropped (the agent searched itself)",
    ),
    Edit(
        "wf/research-spec",
        "**If follow-ups needed, OUTPUT to orchestrator:**",
        "**If follow-ups needed, write them down in this format:**",
        "semantic",
        "G4-1: follow-ups written down, not output (G7-5 (1) orchestrator dropped)",
    ),
    Edit(
        "wf/research-spec",
        "**Then STOP and wait for responses.**",
        "**Then answer them yourself the same way, without sending them as a message.**",
        "semantic",
        "G4-1: follow-ups self-answered, no STOP",
    ),
    Edit(
        "wf/research-spec",
        "**Q1:** [First question asked]\n"
        "**Answer:** [User's answer]\n"
        "\n"
        "**Q2:** [Second question asked]\n"
        "**Answer:** [User's answer]",
        "**Q1:** [First question asked]\n"
        "**Answer:** (assumed) [your answer] — [its basis in the issue or the repository]\n"
        "\n"
        "**Q2:** [Second question asked]\n"
        "**Answer:** (assumed) [your answer] — [its basis in the issue or the repository]",
        "semantic",
        "G4-1: answers recorded as (assumed) <answer> — <basis>",
    ),
    Edit(
        "wf/research-spec",
        "**Follow-up 1:** [Question]\n**Answer:** [User's answer]",
        "**Follow-up 1:** [Question]\n**Answer:** (assumed) [your answer] — [its basis]",
        "semantic",
        "G4-1: follow-up answers recorded the same way",
    ),
    Edit(
        "wf/research-spec",
        "[Based on user's response about similar features]\n"
        "\n"
        "**Similar Features Identified:**\n"
        "- Feature: [Name] - Path: `[path provided by user]`\n"
        "- Components to potentially reuse: [user's description]\n"
        "- Backend logic to reference: [user's description]\n"
        "\n"
        "[If user provided no similar features]",
        "[Based on your search of the repository for similar features]\n"
        "\n"
        "**Similar Features Identified:**\n"
        "- Feature: [Name] - Path: (assumed) `[path]` — [basis]\n"
        "- Components to potentially reuse: [what you found]\n"
        "- Backend logic to reference: [what you found]\n"
        "\n"
        "[If your search found no similar features]",
        "semantic",
        "G4-2: Existing Code to Reference filled from the repository search",
    ),
    Edit(
        "wf/research-spec",
        "- [Components that might exist already based on user's input]",
        "- (assumed) `[path]` — [Components that might exist already, based on your repository search]",
        "semantic",
        "G4-2: Reusability Opportunities from the repository search",
    ),
    Edit(
        "wf/research-spec",
        "### Step 7: Output Completion\n"
        "\n"
        "Return to orchestrator:\n"
        "\n"
        "```\n"
        "Requirements research complete!\n"
        "\n"
        "✅ Processed [X] clarifying questions\n"
        "✅ Visual check performed: [Found and analyzed Y files / No files found]\n"
        "✅ Reusability opportunities: [Identified Z similar features / None identified]\n"
        "✅ Requirements documented comprehensively\n"
        "\n"
        "Requirements saved to: `[spec-path]/planning/requirements.md`\n"
        "\n"
        "Ready for specification creation.\n"
        "```\n"
        "\n",
        "",
        "env",
        "G2-1: \"Return to orchestrator\" output block dropped",
    ),
    Edit(
        "wf/research-spec",
        "- **MANDATORY**: Always run bash command to check visuals folder after receiving user answers",
        "- **MANDATORY**: Always run bash command to check visuals folder after answering the questions",
        "semantic",
        "G4-1: the visuals check follows the agent's own answers",
    ),
    Edit(
        "wf/research-spec",
        "- Save user's exact answers, not interpretations",
        "- Record each assumed answer and its basis",
        "semantic",
        "G4-1: \"exact answers\" -> the assumed answer and its basis",
    ),
    Edit(
        "wf/research-spec",
        "- Document paths to similar features for spec-writer to reference",
        "- Document paths to similar features for the write-spec stage to reference",
        "env",
        "G7-5 (2): spec-writer -> the write-spec stage",
    ),
    Edit(
        "wf/research-spec",
        "\n- OUTPUT questions and STOP to wait for orchestrator to relay responses",
        "",
        "semantic",
        "G4-1: no STOP (G7-5 (1) orchestrator dropped)",
    ),
    # ---- shape-spec end: commands/shape-spec/single-agent/2-shape-spec.md
    Edit(
        "shape-2",
        "## Display confirmation and next step\n"
        "\n"
        "Once you've completed your research and documented it, output the following message:\n"
        "\n"
        "```\n"
        "✅ I have documented this spec's research and requirements in `agent-os/specs/[this-spec]/planning`.\n"
        "\n"
        "Next step: Run the command, `1-create-spec.md`.\n"
        "```\n"
        "\n"
        "After all steps complete, inform the user:\n"
        "\n"
        "```\n"
        "Spec initialized successfully!\n"
        "\n"
        "✅ Spec folder created: `[spec-path]`\n"
        "✅ Requirements gathered\n"
        "✅ Visual assets: [Found X files / No files provided]\n"
        "\n"
        "👉 Run `/write-spec` to create the spec.md document.\n"
        "```",
        _next(COMMAND_DOCS["write-spec"], "Once you've completed your research and documented it in `planning/requirements.md`"),
        "env",
        "G2-2: next command's document in place of the confirmation/next-step messages (G2-1)",
    ),
    # ---- write-spec: commands/write-spec/single-agent/write-spec.md, workflows/specification/write-spec.md
    Edit(
        "write",
        "## Display confirmation and next step\n"
        "\n"
        "Display the following message to the user:\n"
        "\n"
        "```\n"
        "The spec has been created at `agent-os/specs/[this-spec]/spec.md`.\n"
        "\n"
        "Review it closely to ensure everything aligns with your vision and requirements.\n"
        "\n"
        "Next step: Run the command, 2-create-tasks-list.md\n"
        "```",
        _next(COMMAND_DOCS["create-tasks"], "Once the spec has been created at `agent-os/specs/[this-spec]/spec.md`"),
        "env",
        "G2-2: next command's document; G4-6: \"Review it closely\" dropped",
    ),
    Edit(
        "wf/write-spec",
        "- Requirements gathered by spec-shaper",
        "- Requirements gathered by the shape-spec stage",
        "env",
        "G7-5 (2): spec-shaper -> the shape-spec stage",
    ),
    # ---- create-tasks: commands/create-tasks/single-agent/*, workflows/implementation/create-tasks-list.md
    Edit(
        "tasks-1",
        "then ask user to provide direction on where to you can find them by outputting the following request then "
        "wait for user's response:\n"
        "\n"
        "\"I'll need a spec.md or requirements.md (or both) in order to build a tasks list.\n"
        "\n"
        "Please direct me to where I can find those.  If you haven't created them yet, you can run /shape-spec or "
        "/write-spec.\"",
        f"then find the spec folder under `{SPECS_DIR}` (this run creates one) and read the files there. If they do "
        f"not exist yet, carry out the shape-spec document (`{COMMAND_DOCS['shape-spec']}`) and the write-spec document "
        f"(`{COMMAND_DOCS['write-spec']}`) first.",
        "env",
        "G2-3 (rev): find the spec folder instead of asking; slash names dropped",
    ),
    Edit(
        "tasks-2",
        "## Display confirmation and next step\n"
        "\n"
        "Display the following message to the user:\n"
        "\n"
        "```\n"
        "The tasks list has created at `agent-os/specs/[this-spec]/tasks.md`.\n"
        "\n"
        "Review it closely to make sure it all looks good.\n"
        "\n"
        "NEXT STEP 👉 Run `/implement-tasks` (simple, effective) or `/orchestrate-tasks` (advanced, powerful) to start "
        "building!\n"
        "```",
        _next(COMMAND_DOCS["implement-tasks"], "Once the tasks list has been created at `agent-os/specs/[this-spec]/tasks.md`"),
        "env",
        "G2-2: next command's document, /orchestrate-tasks dropped; G4-6: \"Review it closely\" dropped",
    ),
    Edit(
        "wf/create-tasks-list",
        "    - Review the 2-8 tests written by database-engineer (Task 1.1)\n"
        "    - Review the 2-8 tests written by api-engineer (Task 2.1)\n"
        "    - Review the 2-8 tests written by ui-designer (Task 3.1)",
        "    - Review the 2-8 tests written in Task 1.1 (Data Models and Migrations)\n"
        "    - Review the 2-8 tests written in Task 2.1 (API Endpoints)\n"
        "    - Review the 2-8 tests written in Task 3.1 (UI Design)",
        "env",
        "G7-5 (3): v2.0.0 implementer role names -> the task number and group name",
    ),
    Edit(
        "wf/create-tasks-list",
        "- **Use a focused test-driven approach** where each task group starts with writing 2-8 tests (x.1 sub-task) "
        "and ends with running ONLY those tests (final sub-task)",
        "- **Use a focused test-driven approach** where each task group starts with writing 2-8 tests (x.1 sub-task) "
        "and ends with running ONLY those tests (final sub-task)\n"
        "- **Write these tests as check scripts outside the repository**: every test a task group writes (the x.1 "
        "sub-task, and the additional tests of a test-review group) is a script under "
        "`agent-os/specs/[this-spec]/checks/`, run on its own; do not add or change test files in the repository. "
        "The test-writing standard applies to these scripts.",
        "semantic",
        "G9-1: the tests are check scripts under S/checks/, never repository test files",
    ),
    # ---- implement-tasks: commands/implement-tasks/single-agent/*, workflows/implementation/**
    Edit(
        "impl-1",
        "Proceed to PHASE 2 to delegate implementation of those specified task group(s) to the **implementer** subagent.",
        "Proceed to PHASE 2 and carry out the implementation of those specified task group(s) yourself.",
        "env",
        "G7-4: no subagent; carry out PHASE 2 yourself",
    ),
    Edit(
        "impl-1",
        "then output the following message to the user and WAIT for their response:\n"
        "\n"
        "```\n"
        "Should we proceed with implementation of all task groups in tasks.md?\n"
        "\n"
        "If not, then please specify which task(s) to implement.\n"
        "```",
        "then proceed with implementation of all task groups in tasks.md, in order: carry out PHASE 2 yourself, "
        "starting with the first task group.",
        "semantic",
        "G4-4: every task group, in order (the branch the question proposes); no ask",
    ),
    Edit(
        "wf/implement-tasks",
        "Implement all tasks assigned to you and ONLY those task(s) that have been assigned to you.",
        "Implement all tasks assigned to you and ONLY those task(s) that have been assigned to you. The tasks assigned "
        "to you are those of the current task group: one task group per pass of PHASE 2.",
        "env",
        "G4-5: \"assigned\" = the current task group",
    ),
    Edit(
        "wf/implement-tasks",
        "- Running ONLY the tests you've written (if any) and ensuring those tests pass.",
        "- Running ONLY the tests you've written (if any; they are check scripts under "
        "`agent-os/specs/[this-spec]/checks/`, not repository test files) and ensuring those tests pass.",
        "semantic",
        "G9-1: the tests run are the check scripts",
    ),
    Edit(
        "wf/implement-tasks",
        "\n- IF your task involves user-facing UI, and IF you have access to browser testing tools, open a browser and "
        "use the feature you've implemented as if you are a user to ensure a user can use the feature in the intended way.",
        "",
        "env",
        "G6-2: browser-check line deleted (user decision)",
    ),
    Edit(
        "impl-2",
        "## Display confirmation and next step\n"
        "\n"
        "Display a summary of what was implemented.\n"
        "\n"
        "IF all tasks are now marked as done (with `- [x]`) in tasks.md, display this message to user:\n"
        "\n"
        "```\n"
        "All tasks have been implemented: `agent-os/specs/[this-spec]/tasks.md`.\n"
        "\n"
        "NEXT STEP 👉 Run `3-verify-implementation.md` to verify the implementation.\n"
        "```",
        "## Next step\n"
        "\n"
        "IF all tasks are now marked as done (with `- [x]`) in `agent-os/specs/[this-spec]/tasks.md`, continue with "
        "PHASE 3 below.",
        "env",
        "G2-2: continue with PHASE 3 in this document; G2-1: summary message dropped",
    ),
    Edit(
        "impl-2",
        "IF there are still tasks in tasks.md that have yet to be implemented (marked unfinished with `- [ ]`) then "
        "display this message to user:\n"
        "\n"
        "```\n"
        "Would you like to proceed with implementation of the remaining tasks in tasks.md?\n"
        "\n"
        "If not, please specify which task group(s) to implement next.\n"
        "```",
        "IF there are still tasks in tasks.md that have yet to be implemented (marked unfinished with `- [ ]`), repeat "
        "PHASE 2 for the next task group with unchecked tasks.",
        "env",
        "G4-5: repeat PHASE 2 per group until none remain; no ask",
    ),
    Edit(
        "wf/verify-tasks",
        "\n- Check for existence of an implementation report titled using this task's title in "
        "`agent-os/spec/[this-spec]/implementation/` folder.",
        "",
        "semantic",
        "G5-6: no implementation reports exist; the code spot check decides",
    ),
    Edit(
        "wf/update-roadmap",
        "by updating their checkbox(s) to `- [x]`.",
        "by updating their checkbox(s) to `- [x]`.\n"
        "\n"
        "This project has no `agent-os/product/roadmap.md` (plan-product is not part of this workflow): do not create "
        "it. In section 3 of the report, record Status `⚠️ No Updates Needed` with that reason in its Notes.",
        "env",
        "G7-8: no roadmap; section 3 records No Updates Needed",
    ),
    Edit(
        "wf/verification-report",
        "/verifications/final-verification.html`",
        "/verifications/final-verification.md`",
        "env",
        "G5-5 (report name): markdown report named .md",
    ),
    Edit(
        "wf/verification-report",
        "## 2. Documentation Verification\n"
        "\n"
        "**Status:** ✅ Complete | ⚠️ Issues Found\n"
        "\n"
        "### Implementation Documentation\n"
        "- [x] Task Group 1 Implementation: `implementations/1-[task-name]-implementation.md`\n"
        "- [x] Task Group 2 Implementation: `implementations/2-[task-name]-implementation.md`\n"
        "\n"
        "### Verification Documentation\n"
        "[List verification documents from area verifiers if applicable]\n"
        "\n"
        "### Missing Documentation\n"
        "[List any missing documentation, or note \"None\"]\n"
        "\n"
        "---\n"
        "\n",
        "",
        "semantic",
        "G5-6: report section 2 (implementation / area-verifier documents) deleted; sections 1, 3, 4 keep their numbers",
    ),
    # ---- standards (inlined into the commands, G7-3)
    Edit(
        "std/global/conventions",
        "- **Clear Documentation**: Maintain up-to-date README files with setup instructions, architecture overview, "
        "and contribution guidelines\n"
        "- **Version Control Best Practices**: Use clear commit messages, feature branches, and meaningful pull/merge "
        "requests with descriptions\n",
        "",
        "semantic",
        "G9-2: lines 4-5 (README upkeep; commits, branches, PRs) deleted",
    ),
    Edit(
        "std/global/conventions",
        "\n- **Dependency Management**: Keep dependencies up-to-date and minimal; document why major dependencies are used\n"
        "- **Code Review Process**: Establish a consistent code review process with clear expectations for reviewers "
        "and authors\n"
        "- **Testing Requirements**: Define what level of testing is required before merging (unit tests, integration "
        "tests, etc.)\n"
        "- **Feature Flags**: Use feature flags for incomplete features rather than long-lived feature branches\n"
        "- **Changelog Maintenance**: Keep a changelog or release notes to track significant changes and improvements",
        "",
        "semantic",
        "G9-2: lines 7-11 (dependencies, code review, merge testing, feature flags, changelog) deleted",
    ),
    Edit(
        "std/global/coding-style",
        "\n- **Remove Dead Code**: Delete unused code, commented-out blocks, and imports rather than leaving them as clutter\n"
        "- **Backward compatibility only when required:** Unless specifically instructed otherwise, assume you do not "
        "need to write additional code logic to handle backward compatibility.\n"
        "- **DRY Principle**: Avoid duplication by extracting common logic into reusable functions or modules",
        "",
        "semantic",
        "G9-3: lines 8-10 (dead code, backward compatibility, DRY) deleted",
    ),    Edit(
        "std/backend/migrations",
        "\n- **Version Control**: Always commit migrations to version control and never modify existing migrations "
        "after deployment",
        "",
        "semantic",
        "G9-5: line 9 (commit migrations to version control) deleted",
    ),
)

# Left in any shipped command document, these mean an edit missed something.
FORBIDDEN: tuple[str, ...] = (
    "@agent-os/",  # G7-3
    "{{",  # G7-1
    "numbered file names",  # G7-2
    "orchestrator",  # G7-5 (1), G2-1
    "spec-writer",  # G7-5 (2)
    "spec-shaper",
    "database-engineer",  # G7-5 (3)
    "api-engineer",
    "ui-designer",
    "subagent",  # G7-4
    "Display ",  # G2-1
    "NEXT STEP",  # G2-2
    "Run the command",
    "Run `/",
    "/orchestrate-tasks",
    "run /shape-spec",
    "Review it closely",  # G4-6
    "WAIT",  # G1-1, G4-4
    "STOP",  # G4-1
    "wait for",
    "User's answer",  # G4-1
    "exact answers",
    "Visual Assets Request",  # G4-3
    "DO NOT explore",  # G4-2
    "provided by user",
    "check the product roadmap",  # G1-1
    "agent-os/product/mission.md",  # G1-3
    "agent-os/product/tech-stack.md",
    "tech-stack.md",  # G7-6
    "browser",  # G6-2
    "agent-os/spec/",  # G5-6
    "implementation agents",
    "Documentation Verification",
    "final-verification.html",  # G5-5
    "Remove Dead Code",  # G9-3
    "Backward compatibility only",
    "DRY Principle",
    "Clear Documentation",  # G9-2
    "Version Control Best Practices",
    "Always commit migrations",  # G9-5
    "Dependency Management",
    "Code Review Process",
    "Testing Requirements",
    "Feature Flags",
    "Changelog Maintenance",
)

PORT = Port(
    sources=SOURCES,
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    edits=EDITS,
    frontmatter=False,  # no Agent OS source starts with a YAML block
)

_STANDARD_LINE = re.compile(r"^@agent-os/(standards/[\w./-]+\.md)$", re.M)
_SPECS_PREFIX = re.compile(r"(?<![\w/.@-])agent-os/specs/")


def convert(key: str, upstream: str) -> str:
    """One pre-render source with its edits applied (before the installer sees it)."""
    return _convert(PORT, key, upstream)


def inline_standards(text: str, standards: Path) -> str:
    """G7-3: each ``@agent-os/standards/<dir>/<file>.md`` line -> that file's text under its path as a label."""

    def one(m: re.Match) -> str:
        rel = m.group(1)
        body = (standards.parent / rel).read_text(encoding="utf-8").strip("\n")
        return f"**`agent-os/{rel}`**\n\n{body}\n"

    return _STANDARD_LINE.sub(one, text)


def finish(name: str, text: str, standards: Path) -> str:
    """A compiled command file -> the shipped document."""
    text = inline_standards(text, standards)
    text = _SPECS_PREFIX.sub(SPECS_DIR, text)  # G5-1, G5-3 (rev): only the prefix; placeholders stay
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"
    left = [w for w in FORBIDDEN if w in text]
    if left:
        raise ValueError(f"{name}: upstream wording left after conversion: {left}")
    if "{{" in text or "}}" in text:
        raise ValueError(f"{name}: unresolved template tag")
    return text


def install(upstream: Path, home: Path, project: Path) -> Path:
    """Steps 1-4 of the module docstring; returns the project's ``agent-os/`` folder."""
    base = home / "agent-os"
    shutil.copytree(upstream, base, ignore=shutil.ignore_patterns(".git"))
    for key, (src, dest) in SOURCES.items():
        (base / dest).write_text(convert(key, (upstream / src).read_text(encoding="utf-8")), encoding="utf-8")
    for rel in REMOVED:
        (base / rel).unlink()
    cfg = base / "config.yml"
    text = cfg.read_text(encoding="utf-8")
    for old, new in CONFIG:
        if text.count(old) != 1:
            raise ValueError(f"config.yml: {old.strip()!r} occurs {text.count(old)} times (want 1)")
        text = text.replace(old, new)
    cfg.write_text(text, encoding="utf-8")
    project.mkdir(parents=True)
    env = {**os.environ, "HOME": str(home)}
    run = subprocess.run(
        ["bash", str(base / "scripts" / "project-install.sh")],
        cwd=project, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    if run.returncode != 0:
        raise RuntimeError(f"project-install.sh exited {run.returncode}:\n{run.stdout}\n{run.stderr}")
    if "⚠️ This workflow file was not found" in "".join(
        p.read_text(encoding="utf-8") for p in (project / "agent-os" / "commands").rglob("*.md")
    ):
        raise RuntimeError("project-install.sh: a {{workflows/...}} reference did not resolve")
    return project / "agent-os"


def build(upstream: Path) -> dict[str, str]:
    """Output path (relative to ``docs/``) -> text of the four shipped command documents."""
    with tempfile.TemporaryDirectory(prefix="agentos_v2-build-") as tmp:
        installed = install(upstream, Path(tmp) / "home", Path(tmp) / "project")
        out = {}
        for cmd in COMMANDS:
            name = f"commands/{cmd}/{cmd}.md"
            out[name] = finish(name, (installed / name).read_text(encoding="utf-8"), installed / "standards")
        return out


def drift(built: dict[str, str]) -> list[str]:
    """Shipped documents that differ from ``built``, plus any stray file under ``docs/commands/``."""
    bad = _drift(PORT, built)
    shipped = {p.relative_to(OUT_DIR).as_posix() for p in (OUT_DIR / "commands").rglob("*") if p.is_file()}
    return bad + sorted(shipped - set(built))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", type=Path, help="checkout of agent-os at tag v2.1.1")
    ap.add_argument("--check", action="store_true", help="compare a fresh render with the committed docs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        list_edits(PORT)
        print("[render]")
        print(f"  removed    {', '.join(REMOVED)}: G7-6 not shipped, drops out of the standards lists")
        print("  config     claude_code_commands: false, agent_os_commands: true: G7-1 other-tools install path")
        print(f"  collect    {', '.join(f'commands/{c}/{c}.md' for c in COMMANDS)}: G7-1 the four top-level files only")
        print("  standards  @agent-os/standards/... lines -> file text under its path: G7-3")
        print(f"  prefix     agent-os/specs/ -> {SPECS_DIR}: G5-1, G5-3 (rev)")
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    commit = _git_head(args.upstream)
    if commit != UPSTREAM_COMMIT:
        print(f"warning: upstream at {commit}, docs pinned to {UPSTREAM_COMMIT}", file=sys.stderr)
    built = build(args.upstream)
    if args.check:
        bad = drift(built)
        for name in bad:
            print(f"drift: docs/{name}", file=sys.stderr)
        return 1 if bad else 0
    for name, text in built.items():
        dest = OUT_DIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(HERE)} ({text.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
