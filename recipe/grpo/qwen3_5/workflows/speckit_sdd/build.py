"""Build ``docs/stages/`` and the shipped ``.specify/`` tree from a Spec Kit checkout (github/spec-kit).

    python -m recipe.grpo.qwen3_5.workflows.speckit_sdd.build --upstream /path/to/spec-kit
    python -m recipe.grpo.qwen3_5.workflows.speckit_sdd.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.speckit_sdd.build --list                   # the edits, by tag

Spec Kit's core spec-driven development commands are written for an agent app a person drives one slash
command at a time (``/speckit-specify <feature>``, review, ``/speckit-plan <stack>``, ...). A rollout here is
one user message and nobody in between, so the minimal chain specify -> plan -> tasks -> implement <->
converge becomes five stage documents, and ``docs/core-workflow.md`` (hand-written) strings them together.

Four outputs (porting/03-decisions.md, "G7-2 (b) feasibility"):

``STAGES``     ``templates/commands/{specify,plan,tasks,implement,converge}.md`` -> ``docs/stages/0N-<x>.md``,
               uploaded to /speckit-sdd/stages/.
``TEMPLATES``  ``templates/{spec,plan,tasks,checklist}-template.md`` -> ``sandbox/specify/templates/``. The
               agent copies the spec template itself; the scripts copy the plan template and return the
               tasks template, so the text the agent gets from them is changed here.
``SCRIPTS``    ``scripts/bash/{common,check-prerequisites,setup-plan,setup-tasks}.sh``, byte for byte, +x ->
               ``sandbox/specify/scripts/bash/``: the agent runs upstream's own scripts (D-3).
``MEMORY``     ``templates/constitution-template.md`` verbatim -> ``sandbox/specify/memory/constitution.md``,
               the state ``specify init`` leaves (G7-6).

``sandbox/specify/`` is uploaded to /tmp/speckit-sdd/.specify, which makes /tmp/speckit-sdd the Spec Kit
project root, outside the repository; the scripts find it from their own location.

Tags: ``env`` closes a gap between Spec Kit's setting and one unattended session without changing what is
asked; ``semantic`` changes what is asked; ``loop`` is the implement -> converge round rule (at most two
converge rounds, ``convergence.md`` / ``convergence-2.md``). Every note starts with the gap ID of
``porting/02-gaps.md`` / ``03-decisions.md``. An anchor that does not occur exactly once fails the build, so
an upstream rewording surfaces here. The engine is ``workflows/_port.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .._port import Copy, Edit, Port, Section, copy_build, copy_drift, copy_write, list_edits
from .._port import build as _build
from .._port import convert as _convert
from .._port import drift as _drift
from .._port import git_head as _git_head

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs" / "stages"
SANDBOX = HERE / "sandbox" / "specify"  # -> /tmp/speckit-sdd/.specify

# What every output was built from. Another commit only warns; the anchors decide.
UPSTREAM_COMMIT = "0443760542e7e5269724744a2ac55c4bd386d095"

DOCS_ROOT = "/speckit-sdd"
ENTRY_DOC = f"{DOCS_ROOT}/core-workflow.md"
PROJECT_ROOT = "/tmp/speckit-sdd"
SPECIFY_DIR = f"{PROJECT_ROOT}/.specify"
SCRIPT_DIR = f"{SPECIFY_DIR}/scripts/bash"
TEMPLATE_DIR = f"{SPECIFY_DIR}/templates"
CONSTITUTION = f"{SPECIFY_DIR}/memory/constitution.md"
FEATURE_JSON = f"{SPECIFY_DIR}/feature.json"
FEATURE_NAME = "001-issue"
FEATURE_DIR = f"{PROJECT_ROOT}/specs/{FEATURE_NAME}"
CHECKS_DIR = f"{FEATURE_DIR}/checks"  # G9-1 (rev2) / G5-5 (rev2): the test tasks' verification scripts

STAGES_IN_ORDER = ("specify", "plan", "tasks", "implement", "converge")
SOURCES: dict[str, tuple[str, str]] = {
    s: (f"templates/commands/{s}.md", f"{i:02d}-{s}.md") for i, s in enumerate(STAGES_IN_ORDER, start=1)
}
STAGE_DOCS = {s: f"{DOCS_ROOT}/stages/{out}" for s, (_, out) in SOURCES.items()}

TEMPLATE_SOURCES: dict[str, tuple[str, str]] = {
    t: (f"templates/{t}-template.md", f"{t}-template.md") for t in ("spec", "plan", "tasks", "checklist")
}
SCRIPT_NAMES = ("common", "check-prerequisites", "setup-plan", "setup-tasks")

# Left in a stage document, these mean an edit missed a case.
FORBIDDEN = (
    "$ARGUMENTS",
    "{ARGS}",
    "{SCRIPT}",
    "__SPECKIT_COMMAND_",
    "extensions.yml",
    "EXECUTE_COMMAND",
    "`/memory/",
    " /memory/",
    "`/contracts/`",
    " /contracts/",
    "ask the user",
    "Ask the user",
    "Wait for user",
    "warn user",
    "STOP and ask",
    "present options to user",
    "Report completion",
    "report status",
    "Display the table",
    "Halt execution",
    "Suggest next steps",
    "Suggested MVP scope",
    "Implementation strategy section",
    "arallel execution examples",
    "dispatch research agents",
    "coverage meets requirements",
    "tests/contract/",
    "tests/integration/",
    "tests/unit/",
    "Skip if project is purely internal",
    "Omit a Setup",
    "omitted if empty",
    "Project Setup Verification",
    "init-options.json",
    "branch_numbering",
    "GIT_BRANCH_NAME",
    "before_specify",
    "resolution stack",
    "No feature description provided",
    "Cannot determine user scenarios",
    "In-Session",
    "in-session",
    "Handoff",
    "opening a PR",
    "from repo root",
)

# Left in a shipped template, these mean an edit missed a case.
TEMPLATE_FORBIDDEN = (
    "$ARGUMENTS",
    "__SPECKIT_COMMAND_",
    "[###-feature",
    "`/specs/",
    "Commit after each task",
    "STOP and VALIDATE",
    "Stop at any checkpoint",
    "Parallel Example",
    "MVP First",
    "Deploy/demo",
    "Developer A",
    "tests/contract/",
    "tests/integration/",
    "tests/unit/",
    "only when Phase 1 applies",
)


def _script(name: str, args: str) -> str:
    return f"`{SCRIPT_DIR}/{name}.sh {args}`"


_ANY_CWD = f"(from any working directory: it finds the project root `{PROJECT_ROOT}` from its own location)"
# G7-3: the scripts' error hints name slash commands ("Run /speckit.tasks first"); the scripts stay
# byte-for-byte upstream, so the stage documents say what such an error means here.
_SCRIPT_ERROR = (
    "If the script exits non-zero because a file or the feature directory is not found (its hint names a "
    "`/speckit.<stage>` command), that stage has not run yet: carry it out first from its stage document "
    f"(listed in `{ENTRY_DOC}`), then run the script again."
)


def _next(stage: str, done: str) -> str:
    nxt = STAGES_IN_ORDER[STAGES_IN_ORDER.index(stage) + 1]
    return (
        "## Next Stage\n\n"
        "Nothing is reported at the end of this stage: no one reads a completion message, and a reply "
        f"without a tool call ends the session. {done} open `{STAGE_DOCS[nxt]}` and start the {nxt} stage.\n"
    )


def _done_next(stage: str) -> str:
    nxt = STAGES_IN_ORDER[STAGES_IN_ORDER.index(stage) + 1]
    return f"- [ ] The {nxt} stage (`{STAGE_DOCS[nxt]}`) opened next, with no report in between"


_HOOK_DONE = "- [ ] Extension hooks dispatched or skipped according to the rules in Mandatory Post-Execution Hooks above\n"

SECTIONS: tuple[Section, ...] = (
    # -- hooks: no .specify/extensions.yml is shipped; upstream skips silently without it.
    *(Section(s, "## Pre-Execution Checks", None, "env", "G7-1: extension hooks (no extensions.yml)") for s in STAGES_IN_ORDER),
    *(Section(s, "## Mandatory Post-Execution Hooks", None, "env", "G7-1: extension hooks (no extensions.yml)") for s in STAGES_IN_ORDER[:4]),
    Section("converge", "### 9. Check for extension hooks", None, "env", "G7-1: converge's post-hook step (a `###` step, cut separately)", level=3),
    # -- input: the task message instead of $ARGUMENTS.
    Section(
        "specify",
        "## User Input",
        "## Input\n\n"
        "The feature description is the issue in the task message, between `<issue_description>` and\n"
        "`</issue_description>`. It stays there for the whole session and nobody will add to it. Work from the\n"
        "issue text and the repository only: do not open links found in the issue and do not look anything up\n"
        "online. Where a link matters to the spec, quote it as it appears, marked `[UNVERIFIED — not fetched]`.\n",
        "semantic",
        "G1-1/G6-1: input = the issue; links recorded, not fetched",
    ),
    *(Section(s, "## User Input", None, "env", "G1-1: input section dropped (the issue stays in the task message)") for s in STAGES_IN_ORDER[1:]),
    # -- completion: "report to the user" would end the rollout after one stage.
    Section(
        "specify",
        "## Completion Report",
        _next("specify", "Once `SPEC_FILE` and `checklists/requirements.md` are written,"),
        "env",
        "G2-1/G7-4: next stage instead of the completion report (its branch-hook note goes with it)",
    ),
    Section(
        "plan",
        "## Completion Report",
        _next("plan", "Once plan.md, research.md and the Phase 1 files (data-model.md, contracts/, quickstart.md) are written,"),
        "env",
        "G9-4 (rev)/G2-1: next stage instead of the completion report, once the always-written Phase 1 files exist",
    ),
    Section(
        "tasks",
        "## Completion Report",
        "## Next Stage\n\n"
        "The tasks.md should be immediately executable - each task must be specific enough that an LLM can complete "
        "it without additional context. Before moving on, confirm ALL tasks follow the checklist format (checkbox, "
        "ID, labels, file paths).\n\n"
        "Nothing is reported at the end of this stage: no one reads a completion message, and a reply without a "
        f"tool call ends the session. Once tasks.md is written, open `{STAGE_DOCS['implement']}` and start the "
        "implement stage.\n",
        "env",
        "G2-1/G1-1/G4-6: next stage instead of the summary (MVP scope and {ARGS} go with it); format check and "
        "'immediately executable' kept",
    ),
    Section(
        "implement",
        "## Completion Report",
        _next(
            "implement",
            "This stage leaves no report of its own: the `[X]` marks in tasks.md and the converge stage's round "
            "report are the record. Once every task you can complete is marked,",
        ).replace("start the converge stage", "start this round's converge stage"),
        "env",
        "G2-1/D-5: next stage instead of the completion report; no per-round implement report",
    ),
)

TEMPLATE_SECTIONS: tuple[Section, ...] = (
    Section("tasks", "## Parallel Example: User Story 1", None, "semantic", "G7-7: parallel (team/multi-agent) example deleted; [P] markers kept"),
    Section("tasks", "## Implementation Strategy", None, "semantic", "G4-6: MVP-first / incremental / team strategy deleted"),
)

EDITS: tuple[Edit, ...] = (
    # ------------------------------------------------------------------ specify
    Edit(
        "specify",
        "The text the user typed after `__SPECKIT_COMMAND_SPECIFY__` in the triggering message **is** the feature "
        "description. Assume you always have it available in this conversation even if `{ARGS}` appears literally "
        "below. Do not ask the user to repeat it unless they provided an empty command.",
        "The issue (see **Input**) **is** the feature description.",
        "env",
        "G1-1: the issue is the feature description",
    ),
    Edit(
        "specify",
        "1. **Generate a concise short name** (2-4 words) for the feature:\n"
        "   - Analyze the feature description and extract the most meaningful keywords\n"
        "   - Create a 2-4 word short name that captures the essence of the feature\n"
        '   - Use action-noun format when possible (e.g., "add-user-auth", "fix-payment-bug")\n'
        "   - Preserve technical terms and acronyms (OAuth2, API, JWT, etc.)\n"
        "   - Keep it concise but descriptive enough to understand the feature at a glance\n"
        "   - Examples:\n"
        '     - "I want to add user authentication" → "user-auth"\n'
        '     - "Implement OAuth2 integration for the API" → "oauth2-api-integration"\n'
        '     - "Create a dashboard for analytics" → "analytics-dashboard"\n'
        '     - "Fix payment processing timeout bug" → "fix-payment-timeout"',
        f"1. **Feature name**: fixed. This run has one feature and its directory name is `{FEATURE_NAME}`; do not "
        "generate a short name or a number.",
        "env",
        "G5-2: feature dir fixed `001-issue`; short-name generation dropped",
    ),
    Edit(
        "specify",
        "2. **Branch creation** (optional, via hook):\n\n"
        "   If a `before_specify` hook ran successfully in the Pre-Execution Checks above, it will have created/switched "
        "to a git branch and output JSON containing `BRANCH_NAME` and `FEATURE_NUM`. Note these values for reference, "
        "but the branch name does **not** dictate the spec directory name.\n\n"
        "   If the user explicitly provided `GIT_BRANCH_NAME`, pass it through to the hook so the branch script uses the "
        "exact value as the branch name (bypassing all prefix/suffix generation).",
        f"2. **Branch**: no git branch is created. Where a template asks for the branch, write `{FEATURE_NAME}`.",
        "env",
        "G7-4/G7-1: no branch hook; Branch fields = `001-issue`",
    ),
    Edit(
        "specify",
        "   Specs live under the default `specs/` directory unless the user explicitly provides `SPECIFY_FEATURE_DIRECTORY`.\n\n"
        "   **Resolution order for `SPECIFY_FEATURE_DIRECTORY`**:\n"
        "   1. If the user explicitly provided `SPECIFY_FEATURE_DIRECTORY` (e.g., via environment variable, argument, or "
        "configuration), use it as-is\n"
        "   2. Otherwise, auto-generate it under `specs/`:\n"
        "      - Check `.specify/init-options.json` for `feature_numbering` (preferred) or `branch_numbering` (deprecated, "
        "migration only — will be removed in a future release)\n"
        "      - If `\"timestamp\"`: prefix is `YYYYMMDD-HHMMSS` (current timestamp)\n"
        "      - If `\"sequential\"` or absent: prefix is `NNN` (next available 3-digit number after scanning existing "
        "directories in `specs/`)\n"
        "      - Construct the directory name: `<prefix>-<short-name>` (e.g., `003-user-auth` or `20260319-143022-user-auth`)\n"
        "      - Set `SPECIFY_FEATURE_DIRECTORY` to `specs/<directory-name>`\n"
        "      - If `branch_numbering` was used (and `feature_numbering` was absent), emit a one-line warning: \"⚠️ "
        "`branch_numbering` in init-options.json is deprecated. Rename to `feature_numbering`.\"",
        f"   The Spec Kit project root is `{PROJECT_ROOT}`, outside the repository, and specs live under its `specs/` "
        f"directory. `SPECIFY_FEATURE_DIRECTORY` is `{FEATURE_DIR}`.",
        "env",
        "G5-1/G5-2: feature dir outside the repo, fixed; init-options / numbering / timestamp dropped",
    ),
    Edit(
        "specify",
        "   - Resolve the active `spec-template` through the Spec Kit preset/template resolution stack (equivalent to "
        "`specify preset resolve spec-template`)\n"
        "   - Copy the resolved `spec-template` file to `SPECIFY_FEATURE_DIRECTORY/spec.md` as the starting point",
        f"   - Copy `{TEMPLATE_DIR}/spec-template.md` to `SPECIFY_FEATURE_DIRECTORY/spec.md` as the starting point",
        "env",
        "G5-3: the template is copied from the shipped .specify/templates (no overrides or presets exist)",
    ),
    Edit(
        "specify",
        "   - Persist the resolved path to `.specify/feature.json`:\n"
        "     ```json\n"
        "     {\n"
        '       "feature_directory": "<resolved feature dir>"\n'
        "     }\n"
        "     ```\n"
        "     Write the actual resolved directory path value (for example, `specs/003-user-auth`), not the literal string "
        "`SPECIFY_FEATURE_DIRECTORY`.\n"
        "     This allows downstream commands (`__SPECKIT_COMMAND_PLAN__`, `__SPECKIT_COMMAND_TASKS__`, etc.) to locate the "
        "feature directory without relying on git branch name conventions.",
        f"   - Persist the feature directory to `{FEATURE_JSON}`:\n"
        "     ```json\n"
        "     {\n"
        f'       "feature_directory": "specs/{FEATURE_NAME}"\n'
        "     }\n"
        "     ```\n"
        f"     The value is relative to the project root `{PROJECT_ROOT}`.\n"
        "     This allows the later stages' scripts (plan, tasks, implement, converge) to locate the feature directory "
        "without relying on git branch name conventions.",
        "env",
        "G5-1/G5-2/G2-2: feature.json at the shipped project root; commands -> later stages",
    ),
    Edit(
        "specify",
        "   - You must only create one feature per `__SPECKIT_COMMAND_SPECIFY__` invocation\n"
        "   - The spec directory name and the git branch name are independent — they may be the same but that is the "
        "user's choice\n"
        "   - The spec directory and file are always created by this command, never by the hook",
        "   - Create only this one feature\n   - The spec directory and file are always created by this stage",
        "env",
        "G5-2/G7-4/G7-1: one fixed feature; branch and hook notes dropped",
    ),
    Edit(
        "specify",
        "4. Load the resolved active `spec-template` file to understand required sections.",
        f"4. Load the spec template (`{TEMPLATE_DIR}/spec-template.md`, now copied to `SPEC_FILE`) to understand "
        "required sections.",
        "env",
        "G5-3: no resolution stack",
    ),
    Edit(
        "specify",
        "    1. Parse user description from arguments\n       If empty: ERROR \"No feature description provided\"",
        "    1. Parse the feature description from the issue",
        "semantic",
        "G1-1/G1-2: no ERROR exit on an empty description",
    ),
    Edit(
        "specify",
        "       If no clear user flow: ERROR \"Cannot determine user scenarios\"",
        "       There is no ERROR exit here: the issue is a requirement the repository must meet, so derive its user "
        "scenarios from what it asks for",
        "semantic",
        "G1-2: no ERROR exit; the issue is a requirement the repository must meet",
    ),
    Edit(
        "specify",
        "concrete details derived from the feature description (arguments)",
        "concrete details derived from the feature description (the issue)",
        "env",
        "G1-1: arguments -> the issue",
    ),
    Edit(
        "specify",
        "using the checklist template structure with these validation items:",
        "using the structure below, with these validation items:",
        "env",
        "G2-3: the checklist template belongs to the out-of-scope checklist command; the structure is inline",
    ),
    Edit(
        "specify",
        "      - Items marked incomplete require spec updates before `__SPECKIT_COMMAND_CLARIFY__` or "
        "`__SPECKIT_COMMAND_PLAN__`",
        "      - Items marked incomplete require spec updates before the plan stage",
        "env",
        "G2-3: clarify is out of scope; plan -> the plan stage",
    ),
    Edit(
        "specify",
        "Mark checklist complete and proceed to the Mandatory Post-Execution Hooks section",
        "Mark checklist complete and proceed to **Next Stage** below",
        "env",
        "G7-1: no hooks section to proceed to",
    ),
    Edit(
        "specify",
        "        1. List the failing items and specific issues\n",
        "        1. List the failing items and specific issues in the checklist's Notes\n",
        "env",
        "G2-4: no plain-text output mid-workflow; the list goes into the checklist",
    ),
    Edit(
        "specify",
        "        4. If still failing after 3 iterations, document remaining issues in checklist notes and warn user",
        "        4. If still failing after 3 iterations, document remaining issues in checklist notes and continue",
        "env",
        "G4-3: 3-iteration loop kept; the warning is the checklist note",
    ),
    Edit(
        "specify",
        "        3. For each clarification needed (max 3), present options to user in this format:\n\n"
        "           ```markdown\n"
        "           ## Question [N]: [Topic]\n\n"
        "           **Context**: [Quote relevant spec section]\n\n"
        "           **What we need to know**: [Specific question from NEEDS CLARIFICATION marker]\n\n"
        "           **Suggested Answers**:\n\n"
        "           | Option | Answer | Implications |\n"
        "           |--------|--------|--------------|\n"
        "           | A      | [First suggested answer] | [What this means for the feature] |\n"
        "           | B      | [Second suggested answer] | [What this means for the feature] |\n"
        "           | C      | [Third suggested answer] | [What this means for the feature] |\n"
        "           | Custom | Provide your own answer | [Explain how to provide custom input] |\n\n"
        "           **Your choice**: _[Wait for user response]_\n"
        "           ```\n\n"
        "        4. **CRITICAL - Table Formatting**: Ensure markdown tables are properly formatted:\n"
        "           - Use consistent spacing with pipes aligned\n"
        "           - Each cell should have spaces around content: `| Content |` not `|Content|`\n"
        "           - Header separator must have at least 3 dashes: `|--------|`\n"
        "           - Test that the table renders correctly in markdown preview\n"
        "        5. Number questions sequentially (Q1, Q2, Q3 - max 3 total)\n"
        "        6. Present all questions together before waiting for responses\n"
        '        7. Wait for user to respond with their choices for all questions (e.g., "Q1: A, Q2: Custom - [details], '
        'Q3: B")\n'
        "        8. Update the spec by replacing each [NEEDS CLARIFICATION] marker with the user's selected or provided answer\n"
        "        9. Re-run validation after all clarifications are resolved",
        "        3. Nobody will answer a question about them. For each clarification needed (max 3), take the most "
        "plausible answer, replace the marker in the spec with it, and record the choice in the spec's "
        "`## Assumptions` section\n"
        "        4. Re-run validation after all clarifications are resolved",
        "semantic",
        "G4-1: most plausible reading written into the spec and its Assumptions; Q&A and table blocks dropped",
    ),
    Edit(
        "specify",
        "- DO NOT create any checklists that are embedded in the spec. That will be a separate command.",
        "- DO NOT create any checklists that are embedded in the spec.",
        "env",
        "G2-3: the separate checklist command is out of scope",
    ),
    Edit("specify", "When creating this spec from a user prompt:", "When creating this spec from the issue:", "env", "G1-1: the issue is the prompt"),
    Edit(
        "specify",
        _HOOK_DONE + "- [ ] Completion reported to user with feature directory, spec file path, and checklist results",
        _done_next("specify"),
        "env",
        "G7-1/G2-1: hook and report items -> next stage",
    ),
    # ------------------------------------------------------------------ plan
    Edit(
        "plan",
        "1. **Setup**: Run `{SCRIPT}` from repo root and parse JSON for FEATURE_SPEC, IMPL_PLAN, FEATURE_DIR, BRANCH.",
        f"1. **Setup**: Run {_script('setup-plan', '--json')} {_ANY_CWD} and parse JSON for FEATURE_SPEC, IMPL_PLAN, "
        f"FEATURE_DIR, BRANCH. {_SCRIPT_ERROR}",
        "env",
        "G7-2/G7-3: the shipped upstream script, absolute path; what its error hints mean here",
    ),
    Edit(
        "plan",
        '   - Fill Technical Context (mark unknowns as "NEEDS CLARIFICATION")',
        "   - Fill Technical Context from the repository - its build files, CI configuration and installed "
        'environment; nobody names a tech stack (mark unknowns as "NEEDS CLARIFICATION")',
        "env",
        "G1-3: no tech-stack input; Technical Context from the repository",
    ),
    Edit(
        "plan",
        "   - Fill Constitution Check section from constitution\n   - Evaluate gates (ERROR if violations unjustified)",
        "   - Fill Constitution Check section from constitution. If the constitution is an unfilled template "
        "(`[ALL_CAPS]` placeholders with `<!-- Example: ... -->` comments), it has no principles - its comments are "
        'examples, not rules: write "skipped — template" in Constitution Check and evaluate no gate\n'
        "   - Otherwise evaluate gates (ERROR if violations unjustified)",
        "semantic",
        "G7-6: converge's own placeholder rule given to plan: unfilled template -> 'skipped — template', no gate",
    ),
    Edit(
        "plan",
        "   - Phase 1: Generate data-model.md, contracts/, quickstart.md",
        "   - Phase 1: Generate data-model.md, contracts/, quickstart.md - always all three; data-model.md or "
        "quickstart.md with nothing to hold for this change has the one-line body `N/A — <reason>`; contracts/ with "
        "no contract is recorded in plan.md's Documentation tree as `contracts/  # N/A — <reason>`",
        "semantic",
        "G9-4 (rev2): Phase 1 always; N/A body for the two files, N/A line in plan.md's Documentation tree for contracts/",
    ),
    Edit(
        "plan",
        "2. **Generate and dispatch research agents**:\n\n"
        "   ```text\n"
        "   For each unknown in Technical Context:\n"
        '     Task: "Research {unknown} for {feature context}"\n'
        "   For each technology choice:\n"
        '     Task: "Find best practices for {tech} in {domain}"\n'
        "   ```",
        "2. **Research from the repository**: no sub-agents run here and nothing is looked up online. Resolve each "
        "unknown and each research task yourself by reading the repository and the installed environment (source, "
        "build and CI files, the installed versions of its dependencies). Do not fetch links from the issue; a link "
        "you rely on is recorded as `[UNVERIFIED — not fetched]`.",
        "semantic",
        "G6-1: research = the agent reading the repository and environment; no fetching or online lookup",
    ),
    Edit(
        "plan",
        "   - Alternatives considered: [what else evaluated]\n",
        "   - Alternatives considered: [what else evaluated]\n\n"
        "   An unknown the evidence does not settle is decided by the most plausible reading and recorded in the same "
        "format; nobody is asked.\n",
        "semantic",
        "G4-2: unresolved unknowns -> most plausible reading recorded in research.md",
    ),
    Edit(
        "plan",
        "**Prerequisites:** `research.md` complete",
        "**Prerequisites:** `research.md` complete\n\n"
        "**Always written**: data-model.md and quickstart.md are created every time; when nothing in one of them "
        "applies to this change, its whole body is one line `N/A — <reason>`. Contracts are recorded in plan.md's "
        "Documentation tree: the copied template has a `contracts/` line marked `<REPLACE in plan.md: …>`; replace it in "
        "plan.md with one line per contract file you write, or, when there is none, with `contracts/  # N/A — <reason>` "
        "and create no file.",
        "semantic",
        "G9-4 (rev2): Phase 1 always; contracts recorded in plan.md's Documentation tree (files listed, or N/A line)",
    ),
    Edit("plan", "→ `/contracts/`:", "→ `FEATURE_DIR/contracts/`:", "env", "G5-3: /contracts/ is the feature dir's"),
    Edit(
        "plan",
        "   - Skip if project is purely internal (build scripts, one-off tools, etc.)",
        "   - If project is purely internal (build scripts, one-off tools, etc.), write no contract file and record "
        "`contracts/  # N/A — <reason>` in plan.md's Documentation tree",
        "semantic",
        "G9-4 (rev2): contracts' own skip is recorded as the N/A tree line in plan.md",
    ),
    Edit("plan", "**Output**: data-model.md, /contracts/*, quickstart.md", "**Output**: data-model.md, FEATURE_DIR/contracts/*, quickstart.md", "env", "G5-3: /contracts/ is the feature dir's"),
    Edit(
        "plan",
        "- ERROR on gate failures or unresolved clarifications",
        "- Unresolved clarifications are not an error: Phase 0 resolves each from repository evidence or by the most "
        "plausible reading recorded in research.md\n"
        "- Gate failures: as in step 3 (an unfilled constitution template has no gates)",
        "semantic",
        "G4-2/G7-6: no ERROR exit on unknowns; gates per the placeholder rule",
    ),
    Edit(
        "plan",
        _HOOK_DONE + "- [ ] Completion reported to user with branch, plan path, and generated artifacts",
        _done_next("plan"),
        "env",
        "G7-1/G2-1: hook and report items -> next stage",
    ),
    # ------------------------------------------------------------------ tasks
    Edit(
        "tasks",
        "1. **Setup**: Run `{SCRIPT}` from repo root and parse FEATURE_DIR, TASKS_TEMPLATE_CONTENT, TASKS_TEMPLATE, and "
        "AVAILABLE_DOCS list.",
        f"1. **Setup**: Run {_script('setup-tasks', '--json')} {_ANY_CWD} and parse FEATURE_DIR, TASKS_TEMPLATE_CONTENT, "
        f"TASKS_TEMPLATE, and AVAILABLE_DOCS list. {_SCRIPT_ERROR}",
        "env",
        "G7-2/G7-3: the shipped upstream script, absolute path; what its error hints mean here",
    ),
    Edit("tasks", "   - Create parallel execution examples per user story\n", "", "semantic", "G7-7: parallel execution examples dropped"),
    Edit(
        "tasks",
        "   - Phase 1: Setup tasks (project initialization)\n"
        "   - Phase 2: Foundational tasks (blocking prerequisites for all user stories)\n"
        "   - Phase 3+: One phase per user story (in priority order from spec.md)\n"
        "   - Each phase includes: story goal, independent test criteria, tests (if requested), implementation tasks\n"
        "   - Final Phase: Polish & cross-cutting concerns",
        "   - Phase 1: Setup tasks - only what this change needs in the existing repository (no project "
        "initialization, dependency installation or tool configuration)\n"
        "   - Phase 2: Foundational tasks (prerequisites shared by this change's user stories)\n"
        "   - Phase 3+: One phase per user story (in priority order from spec.md)\n"
        "   - Each phase includes: story goal, independent test criteria, tests (if requested), implementation tasks\n"
        "   - Final Phase: Polish - cleanup this change needs (no repository-wide documentation, refactoring, "
        "performance or security work)\n"
        "   - Keep the Setup, Foundational and Polish phase headings even when a phase has no task; such a phase "
        "holds the one line `No tasks — <reason>`",
        "semantic",
        "G9-3 (rev): Setup / Foundational / Polish scoped to this change in an existing repository; headings always "
        "kept, an empty one holds `No tasks — <reason>`",
    ),
    Edit("tasks", "   - Parallel execution examples per story\n", "", "semantic", "G7-7: parallel execution examples dropped"),
    Edit("tasks", "\n   - Implementation strategy section (MVP first, incremental delivery)", "", "semantic", "G4-6: MVP-first strategy section deleted"),
    Edit(
        "tasks",
        "**Tests are OPTIONAL**: Only generate test tasks if explicitly requested in the feature specification or if user "
        "requests TDD approach.",
        "**Tests are OPTIONAL**: Only generate test tasks if explicitly requested in the feature specification or if user "
        "requests TDD approach. Here the task message is that request; if it says the tests are already taken care of, "
        "it means the grader's own tests, which you never see. So every user story gets test tasks under "
        "`### Tests for User Story N`, and their files are verification scripts under "
        f"`{CHECKS_DIR}/` (for example `{CHECKS_DIR}/test_[name].py`), never test files in the repository.",
        "semantic",
        "G9-1 (rev2): the task message is the test request; test tasks per user story, their files verification "
        "scripts under FEATURE_DIR/checks/, never repository test files",
    ),
    Edit(
        "tasks",
        "- **Phase 1**: Setup (project initialization)",
        "- **Phase 1**: Setup (only what this change needs in the existing repository; `No tasks — <reason>` if empty)",
        "semantic",
        "G9-3 (rev): the same Setup scope in the phase-structure list; kept when empty",
    ),
    Edit(
        "tasks",
        _HOOK_DONE + "- [ ] Completion reported to user with task count, story breakdown, and MVP scope",
        _done_next("tasks"),
        "env",
        "G7-1/G2-1/G4-6: hook, report and MVP-scope items -> next stage",
    ),
    # ------------------------------------------------------------------ implement
    Edit(
        "implement",
        "1. Run `{SCRIPT}` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list.",
        f"1. Run {_script('check-prerequisites', '--json --require-tasks --include-tasks')} {_ANY_CWD} and parse "
        f"FEATURE_DIR and AVAILABLE_DOCS list. {_SCRIPT_ERROR}",
        "env",
        "G7-2/G7-3: the shipped upstream script, absolute path; what its error hints mean here",
    ),
    Edit(
        "implement",
        "   - Treat checklist markers as a read-only gate: scan checkbox state, report status, and ask before proceeding "
        "when needed; do NOT modify checklist files or markers",
        "   - Treat checklist markers as a read-only check: scan checkbox state and proceed; do NOT modify checklist "
        "files or markers",
        "semantic",
        "G4-4: the scan stays read-only; no report, no question",
    ),
    Edit(
        "implement",
        "   - `checklists/requirements.md` is the built-in spec-quality checklist maintained by "
        "`__SPECKIT_COMMAND_SPECIFY__` and `__SPECKIT_COMMAND_CLARIFY__`; custom checklists generated by "
        "`__SPECKIT_COMMAND_CHECKLIST__` are reviewer-owned requirements-quality review artifacts\n"
        "   - For custom checklists, `[x]` means the reviewer determined the requirements-quality criterion is "
        "satisfied; it does NOT mean implementation work is complete",
        "   - `checklists/requirements.md` is the built-in spec-quality checklist maintained by the specify stage",
        "env",
        "G2-3: clarify / checklist commands and their custom checklists are out of scope",
    ),
    Edit(
        "implement",
        "   - **If any checklist has unchecked items**:\n"
        "     - Display the table with unchecked item counts\n"
        '     - **STOP** and ask: "Some checklists have unchecked items. Do you want to proceed with implementation '
        'anyway? (yes/no)"\n'
        "     - Wait for user response before continuing\n"
        '     - If user says "no" or "wait" or "stop", halt execution\n'
        '     - If user says "yes" or "proceed" or "continue", proceed to step 3',
        "   - **If any checklist has unchecked items**:\n"
        "     - The unchecked items stay recorded in the checklist itself; nobody is asked\n"
        "     - Proceed to step 3",
        "semantic",
        "G4-4: upstream's proceed branch taken; ask / wait / halt dropped",
    ),
    Edit(
        "implement",
        "     - Display the table showing all checklists passed\n",
        "",
        "env",
        "G2-4: no plain-text output mid-workflow",
    ),
    Edit(
        "implement",
        "4. **Project Setup Verification**:\n"
        "   - **REQUIRED**: Create/verify ignore files based on actual project setup:\n\n"
        "   **Detection & Creation Logic**:\n"
        "   - Check if the following command succeeds to determine if the repository is a git repo (create/verify "
        ".gitignore if so):\n\n"
        "     ```sh\n"
        "     git rev-parse --git-dir 2>/dev/null\n"
        "     ```\n\n"
        "   - Check if Dockerfile* exists or Docker in plan.md → create/verify .dockerignore\n"
        "   - Check if .eslintrc* exists → create/verify .eslintignore\n"
        "   - Check if eslint.config.* exists → ensure the config's `ignores` entries cover required patterns\n"
        "   - Check if .prettierrc* exists → create/verify .prettierignore\n"
        "   - Check if .npmrc or package.json exists → create/verify .npmignore (if publishing)\n"
        "   - Check if terraform files (*.tf) exist → create/verify .terraformignore\n"
        "   - Check if .helmignore needed (helm charts present) → create/verify .helmignore\n\n"
        "   **If ignore file already exists**: Verify it contains essential patterns, append missing critical patterns only\n"
        "   **If ignore file missing**: Create with full pattern set for detected technology\n\n"
        "   **Common Patterns by Technology** (from plan.md tech stack):\n"
        "   - **Node.js/JavaScript/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`\n"
        "   - **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`\n"
        "   - **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`\n"
        "   - **C#/.NET**: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`\n"
        "   - **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`\n"
        "   - **Ruby**: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`\n"
        "   - **PHP**: `vendor/`, `*.log`, `*.cache`, `*.env`\n"
        "   - **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`\n"
        "   - **Kotlin**: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`\n"
        "   - **C++**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`\n"
        "   - **C**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `*.dll`, `autom4te.cache/`, "
        "`config.status`, `config.log`, `.idea/`, `*.log`, `.env*`\n"
        "   - **Swift**: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`\n"
        "   - **R**: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`\n"
        "   - **Universal**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`\n\n"
        "   **Tool-Specific Patterns**:\n"
        "   - **Docker**: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`\n"
        "   - **ESLint**: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`\n"
        "   - **Prettier**: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`\n"
        "   - **Terraform**: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`\n"
        "   - **Kubernetes/k8s**: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`",
        "4. **Ignore files**: the repository's ignore files (`.gitignore`, `.dockerignore` and the like) are not part "
        "of the change; do not create or edit them.",
        "semantic",
        "G9-2: ignore-file setup deleted; ignore files are not part of the change",
    ),
    Edit(
        "implement",
        "6. Execute implementation following the task plan:\n",
        "6. Execute implementation following the task plan:\n"
        "   - **Round 2**: when the converge stage has appended a `## Phase N: Convergence` and sent you back here, "
        "execute only the unchecked tasks (normally that newest phase); do not redo `[X]` tasks or the setup tasks\n",
        "loop",
        "G8-2: round 2 executes only the unchecked tasks",
    ),
    Edit(
        "implement",
        "   - **Follow TDD approach**: Execute test tasks before their corresponding implementation tasks",
        "   - **Follow TDD approach**: Execute test tasks before their corresponding implementation tasks. The test tasks "
        "are the verification scripts in `FEATURE_DIR/checks/`: write and run them and confirm they fail, implement, then "
        "run them again and confirm they pass",
        "semantic",
        "G9-1 (rev2): upstream TDD line kept; test tasks = the checks/ scripts (fail first, pass after)",
    ),
    Edit(
        "implement",
        "   - **Validation checkpoints**: Verify each phase completion before proceeding",
        "   - **Validation checkpoints**: Verify each phase completion before proceeding, then continue: every phase of "
        "tasks.md is completed in this one pass",
        "semantic",
        "G4-6: validate at each checkpoint and continue; every phase in one pass",
    ),
    Edit(
        "implement",
        "   - **Setup first**: Initialize project structure, dependencies, configuration",
        "   - **Setup first**: Setup phase tasks (repository already initialized, no dependency installation)",
        "semantic",
        "G9-3: setup scoped to the existing repository",
    ),
    Edit(
        "implement",
        "   - **Tests before code**: If you need to write tests for contracts, entities, and integration scenarios",
        "   - **Tests before code**: If you need to write tests for contracts, entities, and integration scenarios, "
        "write them as verification scripts in `FEATURE_DIR/checks/`; the repository's test files are not written or "
        "edited. Before implementing, also run the existing repository tests related to the change and record the "
        "baseline; run them again after",
        "semantic",
        "G9-1 (rev2): upstream line kept, tests go to checks/ (no repository test files); existing repo tests run "
        "before (baseline) and after",
    ),
    Edit(
        "implement",
        "   - **Polish and validation**: Unit tests, performance optimization, documentation",
        "   - **Polish and validation**: Polish phase tasks, then run existing tests for changed modules",
        "semantic",
        "G9-3/G9-1: polish scoped; existing tests run, none written",
    ),
    Edit(
        "implement",
        "   - Report progress after each completed task\n",
        "   - Record progress only by marking each completed task [X] in tasks.md (see below); do not report progress in messages\n",
        "env",
        "G2-4: progress = [X] marks only",
    ),
    Edit(
        "implement",
        "   - Halt execution if any non-parallel task fails\n   - For parallel tasks [P], continue with successful tasks, report failed ones",
        "   - If a non-parallel task fails, leave it unchecked and continue with the tasks that do not depend on it\n"
        "   - For parallel tasks [P], continue with successful tasks, leave failed ones unchecked",
        "semantic",
        "G4-5: a failed task stays unchecked; continue with independent tasks",
    ),
    Edit(
        "implement",
        "   - Suggest next steps if implementation cannot proceed",
        "   - If implementation cannot proceed, go on to the converge stage: it re-checks every task whatever its "
        "checkbox and appends the remaining work",
        "semantic",
        "G4-5: then converge, which re-checks every task",
    ),
    Edit(
        "implement",
        "   - **IMPORTANT** For completed tasks, make sure to mark the task off as [X] in the tasks file.",
        "   - **IMPORTANT** For completed tasks, make sure to mark the task off as [X] in the tasks file.\n"
        "   - The checkboxes in tasks.md are the record of progress. A task-tracking tool, if you use one, is scratch "
        "only and never replaces marking tasks.md",
        "env",
        "G10-5: tasks.md checkboxes are the record; TaskTracker optional scratch",
    ),
    Edit(
        "implement",
        "   - Validate that tests pass and coverage meets requirements",
        "   - Validate that tests pass: the verification scripts in `FEATURE_DIR/checks/` and the existing repository "
        "tests related to the change",
        "semantic",
        "G9-1 (rev2): tests pass = the checks/ scripts and the related existing repo tests; coverage requirement dropped",
    ),
    Edit(
        "implement",
        "Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, "
        "suggest running `__SPECKIT_COMMAND_TASKS__` first to regenerate the task list.",
        "Note: This stage assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, "
        f"carry out the tasks stage (`{STAGE_DOCS['tasks']}`) first to regenerate the task list.",
        "env",
        "G2-2: suggest running X -> carry out X first",
    ),
    Edit(
        "implement",
        "- [ ] Implementation validated against specification, plan, and test coverage",
        "- [ ] Implementation validated against specification, plan, and tests (the `FEATURE_DIR/checks/` scripts and "
        "the existing repository tests related to the change)",
        "semantic",
        "G9-1 (rev2): test coverage -> the checks/ scripts and the related existing repo tests",
    ),
    Edit(
        "implement",
        _HOOK_DONE + "- [ ] Completion reported to user with summary of completed work",
        _done_next("implement"),
        "env",
        "G7-1/G2-1: hook and report items -> next stage",
    ),
    # ------------------------------------------------------------------ converge
    Edit(
        "converge",
        "**APPEND-ONLY, NEVER REWRITE**: The command's **only** write is appending a new\n"
        "`## Phase N: Convergence` section to `tasks.md`. It MUST NOT:",
        "**APPEND-ONLY, NEVER REWRITE**: The stage's **only** writes are its round report (step 6) and appending a new\n"
        "`## Phase N: Convergence` section to `tasks.md`. It MUST NOT:",
        "loop",
        "G8-1: the round report is the stage's second write",
    ),
    Edit(
        "converge",
        "When the codebase already satisfies everything, the command MUST leave `tasks.md`\n"
        "**byte-for-byte unchanged** (no empty Convergence header) and report a clean result.",
        "When the codebase already satisfies everything, the stage MUST leave `tasks.md`\n"
        "**byte-for-byte unchanged** (no empty Convergence header) and record a clean result in its round report.",
        "loop",
        "G8-1/G2-4: the clean result goes into the round report",
    ),
    Edit(
        "converge",
        "Run `{SCRIPT}` once from repo root and parse JSON for FEATURE_DIR and AVAILABLE_DOCS.",
        f"Run {_script('check-prerequisites', '--json --require-spec --require-tasks --include-tasks')} once "
        f"{_ANY_CWD} and parse JSON for FEATURE_DIR and AVAILABLE_DOCS.",
        "env",
        "G7-2: the shipped upstream script, absolute path",
    ),
    Edit(
        "converge",
        "If `spec.md`, `plan.md`, or `tasks.md` is missing, STOP with a clear, actionable message naming the\n"
        "prerequisite command to run (`__SPECKIT_COMMAND_SPECIFY__` for a missing spec, `__SPECKIT_COMMAND_PLAN__` for a "
        "missing plan,\n"
        "`__SPECKIT_COMMAND_TASKS__` for missing tasks). Do not produce partial output.",
        "If `spec.md`, `plan.md`, or `tasks.md` is missing (the script exits non-zero naming it), carry out the stage\n"
        f"that writes it first (`{STAGE_DOCS['specify']}` for a missing spec, `{STAGE_DOCS['plan']}` for a missing plan,\n"
        f"`{STAGE_DOCS['tasks']}` for missing tasks), then start this stage again. Do not produce partial output.",
        "env",
        "G2-2/G7-3: STOP naming a command -> carry out that stage first",
    ),
    Edit(
        "converge",
        "### 6. Present the In-Session Findings Summary\n\n"
        "Before appending anything, output a compact, severity-graded summary (no file writes yet):\n\n"
        "## Convergence Findings\n\n",
        "### 6. Write the Round Report\n\n"
        "Before appending anything, write a compact, severity-graded summary to this round's report:\n"
        f"`FEATURE_DIR/convergence.md` in round 1, `FEATURE_DIR/convergence-2.md` in round 2 (rounds:\n"
        f"`{ENTRY_DOC}`), with this structure:\n\n"
        "## Convergence Findings\n\n"
        "- **Round**: 1 | 2\n"
        "- **Outcome**: converged | tasks_appended\n\n",
        "loop",
        "G8-1/G2-4: the in-session summary becomes the round report file, with Round and Outcome fields",
    ),
    Edit(
        "converge",
        '- Report: **"✅ Converged — the implementation satisfies the spec, plan, and tasks."**',
        '- Write as the round report\'s last line: **"✅ Converged — the implementation satisfies the spec, plan, and tasks."**',
        "env",
        "G2-4: the converged outcome is recorded in the round report, not reported",
    ),
    Edit(
        "converge",
        "### 8. Provide Next Actions (Handoff)\n\n"
        "- On `tasks_appended`: state how many tasks were appended under which phase, and recommend\n"
        "  running `__SPECKIT_COMMAND_IMPLEMENT__` to complete them; note that a follow-up converge\n"
        "  run will find fewer or no remaining items.\n"
        "- On `converged`: recommend proceeding to review / opening a PR. No further implement pass\n"
        "  is needed for this feature's specified scope.",
        "### 8. Next Step (Rounds)\n\n"
        "No one reads a recommendation here: the outcome and the round decide what happens next (at most two\n"
        f"converge rounds, `{ENTRY_DOC}`).\n\n"
        f"- On `tasks_appended` in round 1: open the implement stage document (`{STAGE_DOCS['implement']}`)\n"
        "  again and complete the new Convergence phase's tasks (round 2), then return to this document and\n"
        "  write `convergence-2.md`.\n"
        "- On `converged`, in either round: no further implement pass is needed for this feature's specified\n"
        "  scope. The workflow is complete; finish the task.\n"
        "- Round 2, whatever the outcome: the workflow is complete; finish the task. What is left stays\n"
        "  recorded in `convergence-2.md` and in the unchecked tasks.",
        "loop",
        "G8-1: converged ends; tasks_appended in round 1 -> implement round 2; round 2 ends regardless (cap 2)",
    ),
    Edit(
        "implement",
        "   - **Phase-by-phase execution**: Complete each phase before moving to the next",
        "   - **Each user story starts with its test tasks**: before any code edit for a story, write that story's "
        "verification scripts in `FEATURE_DIR/checks/`, run them and see them fail; only then implement the story, "
        "and run them again to see them pass\n"
        "   - **Phase-by-phase execution**: Complete each phase before moving to the next",
        "semantic",
        "G9-7: the TDD order stated at the head of the execution rules (upstream order unchanged, placement only)",
    ),
)

# After the anchored edits: paths and names that recur in text the edits leave as is (G5-3, G2-2).
SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("`/memory/constitution.md`", f"`{CONSTITUTION}`"),
    (" /memory/constitution.md ", f" {CONSTITUTION} "),
    ("`__SPECKIT_COMMAND_IMPLEMENT__`", f"the implement stage (`{STAGE_DOCS['implement']}`)"),
    ("`__SPECKIT_COMMAND_TASKS__`", f"the tasks stage (`{STAGE_DOCS['tasks']}`)"),
    ("This command", "This stage"),
    ("this command", "this stage"),
)

TEMPLATE_EDITS: tuple[Edit, ...] = (
    # ------------------------------------------------------------------ spec-template
    Edit("spec", "**Feature Branch**: `[###-feature-name]`", f"**Feature Branch**: `{FEATURE_NAME}`", "env", "G7-4: Branch field = `001-issue`"),
    Edit("spec", '**Input**: User description: "$ARGUMENTS"', "**Input**: the issue in the task message", "env", "G1-1: input = the issue"),
    # ------------------------------------------------------------------ plan-template
    Edit("plan", "**Branch**: `[###-feature-name]` |", f"**Branch**: `{FEATURE_NAME}` |", "env", "G7-4: Branch field = `001-issue`"),
    Edit(
        "plan",
        "**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`",
        f"**Input**: Feature specification from `{FEATURE_DIR}/spec.md`",
        "env",
        "G5-1: the feature dir outside the repo",
    ),
    Edit(
        "plan",
        "**Note**: This template is filled in by the `__SPECKIT_COMMAND_PLAN__` command; its definition describes the "
        "execution workflow.",
        f"**Note**: This template is filled in by the plan stage; its stage document (`{STAGE_DOCS['plan']}`) "
        "describes the execution workflow.",
        "env",
        "G2-2: command -> stage document",
    ),
    Edit(
        "plan",
        "specs/[###-feature]/\n"
        "├── plan.md              # This file (__SPECKIT_COMMAND_PLAN__ command output)\n"
        "├── research.md          # Phase 0 output (__SPECKIT_COMMAND_PLAN__ command)\n"
        "├── data-model.md        # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)\n"
        "├── quickstart.md        # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)\n"
        "├── contracts/           # Phase 1 output (__SPECKIT_COMMAND_PLAN__ command)\n"
        "└── tasks.md             # Phase 2 output (__SPECKIT_COMMAND_TASKS__ command - NOT created by __SPECKIT_COMMAND_PLAN__)",
        f"{FEATURE_DIR}/\n"
        "├── plan.md              # This file (plan stage output)\n"
        "├── research.md          # Phase 0 output (plan stage)\n"
        "├── data-model.md        # Phase 1 output (plan stage; always, `N/A — <reason>` if nothing applies)\n"
        "├── quickstart.md        # Phase 1 output (plan stage; always, `N/A — <reason>` if nothing applies)\n"
        "├── contracts/           # <REPLACE in plan.md: one line per contract file you wrote, or `N/A — <reason>` and no file>\n"
        "└── tasks.md             # Phase 2 output (tasks stage - NOT created by the plan stage)",
        "semantic",
        "G9-4 (rev2)/G9-6/G5-1/G2-2: feature dir path, stages for commands, Phase 1 always; contracts line is a fill-in slot",
    ),
    Edit(
        "plan",
        "  real paths (e.g., apps/admin, packages/something). The delivered plan must\n  not include Option labels.\n-->",
        "  real paths (e.g., apps/admin, packages/something). The delivered plan must\n"
        "  not include Option labels. For an existing repository, list only the real\n"
        "  files and directories this change modifies or adds.\n-->",
        "semantic",
        "G9-3: Source Code lists the real files this change touches",
    ),
    # ------------------------------------------------------------------ tasks-template
    Edit(
        "tasks",
        '---\n\ndescription: "Task list template for feature implementation"\n---\n\n',
        "",
        "env",
        "G7-5: frontmatter stripped (setup-tasks.sh hands the file content to the agent as is)",
    ),
    Edit(
        "tasks",
        "**Input**: Design documents from `/specs/[###-feature-name]/`",
        f"**Input**: Design documents from `{FEATURE_DIR}/`",
        "env",
        "G5-1: the feature dir outside the repo",
    ),
    Edit(
        "tasks",
        "**Tests**: The examples below include test tasks. Tests are OPTIONAL - only include them if explicitly requested "
        "in the feature specification.",
        "**Tests**: The examples below include test tasks. Tests are OPTIONAL - only include them if explicitly requested "
        "in the feature specification. Here the task message is that request: every user story gets its test tasks, "
        f"and their files are verification scripts under `{CHECKS_DIR}/`, never test files in the repository.",
        "semantic",
        "G9-1 (rev2): the task message is the test request; test files = verification scripts under FEATURE_DIR/checks/",
    ),
    Edit(
        "tasks",
        "  The __SPECKIT_COMMAND_TASKS__ command MUST replace these with actual tasks based on:",
        "  The tasks stage MUST replace these with actual tasks based on:",
        "env",
        "G2-2: command -> stage",
    ),
    Edit(
        "tasks",
        "  DO NOT keep these sample tasks in the generated tasks.md file.\n",
        "  DO NOT keep these sample tasks in the generated tasks.md file.\n\n"
        "  DO keep the Setup, Foundational and Polish phase headings, even when a\n"
        "  phase has no task for this change: such a phase then holds the one line\n"
        "  `No tasks — <reason>`.\n",
        "semantic",
        "G9-3 (rev): Setup / Foundational / Polish headings always kept; an empty one holds `No tasks — <reason>`",
    ),
    Edit(
        "tasks",
        "- [ ] T010 [P] [US1] Contract test for [endpoint] in tests/contract/test_[name].py\n"
        "- [ ] T011 [P] [US1] Integration test for [user journey] in tests/integration/test_[name].py",
        f"- [ ] T010 [P] [US1] Contract test for [endpoint] in {CHECKS_DIR}/contract/test_[name].py\n"
        f"- [ ] T011 [P] [US1] Integration test for [user journey] in {CHECKS_DIR}/integration/test_[name].py",
        "semantic",
        "G9-1 (rev2): US1 test-task example paths -> FEATURE_DIR/checks/ (not repository tests/)",
    ),
    Edit(
        "tasks",
        "- [ ] T018 [P] [US2] Contract test for [endpoint] in tests/contract/test_[name].py\n"
        "- [ ] T019 [P] [US2] Integration test for [user journey] in tests/integration/test_[name].py",
        f"- [ ] T018 [P] [US2] Contract test for [endpoint] in {CHECKS_DIR}/contract/test_[name].py\n"
        f"- [ ] T019 [P] [US2] Integration test for [user journey] in {CHECKS_DIR}/integration/test_[name].py",
        "semantic",
        "G9-1 (rev2): US2 test-task example paths -> FEATURE_DIR/checks/ (not repository tests/)",
    ),
    Edit(
        "tasks",
        "- [ ] T024 [P] [US3] Contract test for [endpoint] in tests/contract/test_[name].py\n"
        "- [ ] T025 [P] [US3] Integration test for [user journey] in tests/integration/test_[name].py",
        f"- [ ] T024 [P] [US3] Contract test for [endpoint] in {CHECKS_DIR}/contract/test_[name].py\n"
        f"- [ ] T025 [P] [US3] Integration test for [user journey] in {CHECKS_DIR}/integration/test_[name].py",
        "semantic",
        "G9-1 (rev2): US3 test-task example paths -> FEATURE_DIR/checks/ (not repository tests/)",
    ),
    Edit(
        "tasks",
        "- [ ] TXXX [P] Additional unit tests (if requested) in tests/unit/",
        f"- [ ] TXXX [P] Additional unit tests (if requested) in {CHECKS_DIR}/unit/",
        "semantic",
        "G9-1 (rev2): Polish test-task example path -> FEATURE_DIR/checks/ (not repository tests/)",
    ),
    Edit("tasks", "- Commit after each task or logical group\n", "", "env", "G7-4: commit line dropped"),
    Edit(
        "tasks",
        "- Stop at any checkpoint to validate story independently",
        "- Validate at each checkpoint and continue",
        "semantic",
        "G4-6: validate at each checkpoint and continue",
    ),
    # ------------------------------------------------------------------ checklist-template
    Edit(
        "checklist",
        "**Note**: This custom checklist is generated by the `__SPECKIT_COMMAND_CHECKLIST__` command based on feature "
        "context and requirements.\n",
        "",
        "env",
        "G2-3: the checklist command is out of scope",
    ),
    Edit(
        "checklist",
        "  The __SPECKIT_COMMAND_CHECKLIST__ command MUST replace these with actual items based on:",
        "  These MUST be replaced with actual items based on:",
        "env",
        "G2-3: the checklist command is out of scope",
    ),
    Edit(
        "checklist",
        "- `__SPECKIT_COMMAND_IMPLEMENT__` reads checklist checkbox state as a gate and must not modify markers",
        f"- The implement stage (`{STAGE_DOCS['implement']}`) reads checklist checkbox state and must not modify markers",
        "semantic",
        "G2-2/G4-4: command -> stage; the scan is a read-only check, not a gate",
    ),
    Edit(
        "checklist",
        "- `checklists/requirements.md` has a separate built-in lifecycle maintained by `__SPECKIT_COMMAND_SPECIFY__` and "
        "`__SPECKIT_COMMAND_CLARIFY__`",
        "- `checklists/requirements.md` has a separate built-in lifecycle maintained by the specify stage",
        "env",
        "G2-3: clarify is out of scope",
    ),
)

STAGES = Port(
    sources=SOURCES,
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    sections=SECTIONS,
    edits=EDITS,
    substitutions=SUBSTITUTIONS,
    forbidden=FORBIDDEN,
    extra_tags=("loop",),
)

TEMPLATES = Port(
    sources=TEMPLATE_SOURCES,
    out_dir=SANDBOX / "templates",
    upstream_commit=UPSTREAM_COMMIT,
    sections=TEMPLATE_SECTIONS,
    edits=TEMPLATE_EDITS,
    forbidden=TEMPLATE_FORBIDDEN,
    frontmatter=False,  # only tasks-template has one; it is an edit above
)

SCRIPTS = Copy(files={f"scripts/bash/{n}.sh": f"scripts/bash/{n}.sh" for n in SCRIPT_NAMES}, out_dir=SANDBOX, executable=True)
MEMORY = Copy(files={"templates/constitution-template.md": "memory/constitution.md"}, out_dir=SANDBOX)

PORTS: dict[str, Port] = {"stages": STAGES, "templates": TEMPLATES}
COPIES: dict[str, Copy] = {"scripts": SCRIPTS, "memory": MEMORY}


def convert(key: str, upstream: str) -> str:
    """One stage document from its upstream command text."""
    return _convert(STAGES, key, upstream)


def convert_template(key: str, upstream: str) -> str:
    """One shipped template from its upstream text."""
    return _convert(TEMPLATES, key, upstream)


def build(upstream: Path) -> dict[str, str]:
    return _build(STAGES, upstream)


def build_templates(upstream: Path) -> dict[str, str]:
    return _build(TEMPLATES, upstream)


def expected_sandbox_files() -> set[str]:
    """Every file ``sandbox/specify/`` must hold, relative to it."""
    return {f"templates/{out}" for _, out in TEMPLATE_SOURCES.values()} | {out for c in COPIES.values() for out in c.files.values()}


def _strays() -> list[str]:
    stages = {p.name for p in OUT_DIR.glob("*") if p.is_file()} - {out for _, out in SOURCES.values()}
    sandbox = {p.relative_to(SANDBOX).as_posix() for p in SANDBOX.rglob("*") if p.is_file()} - expected_sandbox_files()
    return sorted({f"docs/stages/{n}" for n in stages} | {f"sandbox/specify/{n}" for n in sandbox})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", "--spec-kit", dest="upstream", type=Path, help="spec-kit checkout")
    ap.add_argument("--check", action="store_true", help="compare with the committed outputs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        for label, port in PORTS.items():
            print(f"== {label} -> {port.out_dir.relative_to(HERE)}/")
            list_edits(port)
        for label, c in COPIES.items():
            print(f"== {label} -> {c.out_dir.relative_to(HERE)}/ (verbatim{', +x' if c.executable else ''})")
            for src, out in c.files.items():
                print(f"  {src} -> {out}")
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    commit = _git_head(args.upstream)
    if commit != UPSTREAM_COMMIT:
        print(f"warning: upstream at {commit}, outputs pinned to {UPSTREAM_COMMIT}", file=sys.stderr)
    rc = 0
    for port in PORTS.values():
        built = _build(port, args.upstream)
        if args.check:
            for name in _drift(port, built):
                print(f"drift: {port.out_dir.relative_to(HERE)}/{name}", file=sys.stderr)
                rc = 1
            continue
        for name, text in built.items():
            dest = port.out_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            print(f"wrote {dest.relative_to(HERE)} ({text.count(chr(10))} lines)")
    for c in COPIES.values():
        built_bytes = copy_build(c, args.upstream)
        if args.check:
            for name in copy_drift(c, built_bytes):
                print(f"drift: {c.out_dir.relative_to(HERE)}/{name} (content or executable bit)", file=sys.stderr)
                rc = 1
            continue
        copy_write(c, built_bytes)
        for name in built_bytes:
            print(f"copied {(c.out_dir / name).relative_to(HERE)}{' (+x)' if c.executable else ''}")
    for name in _strays():
        print(f"{'drift' if args.check else 'warning'}: stray file {name} (not a build output)", file=sys.stderr)
        rc = 1 if args.check else rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
