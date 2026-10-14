"""Build ``docs/stages/`` and the forked schema from an OpenSpec checkout (Fission-AI/OpenSpec).

    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --upstream /path/to/OpenSpec
    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --list                   # the edits, by tag

Two outputs, one ``_port.Port`` each:

``STAGES``  the four OPSX skills the chain new -> ff -> apply -> verify uses
            (``skills/openspec-<x>-change/SKILL.md``, the committed renders) -> ``docs/stages/0N-<x>.md``,
            uploaded to ``/opsx/stages/``. Archive is the CLI's ``openspec archive issue --yes``, so the
            archive and sync skills are not shipped (porting/03-decisions.md D-5).
``FORK``    ``schemas/spec-driven/`` (``schema.yaml`` + four templates) -> ``sandbox/schemas/spec-driven-sandbox/``,
            what ``openspec schema fork spec-driven spec-driven-sandbox`` writes (the ``name:`` set and the
            yaml library's ``[ tasks ]`` spacing; checked against the CLI 1.14.1 output) plus the decided
            edits. The setup step copies it to ``/openspec/schemas/`` and selects it in ``config.yaml``
            (D-4): the CLI serves the per-artifact instructions from it, so the text the agent gets from
            ``openspec instructions`` is changed here and nowhere else.

The other text the agent meets -- status, paths, validation, apply state, archive -- comes from the
real CLI as upstream ships it (D-1). ``docs/core-workflow.md`` (hand-written) strings the stages together.

Tags: ``env`` closes a gap between OpenSpec's setting (a person typing ``/opsx:*`` commands in an agent
app) and one unattended session without changing what is asked; ``semantic`` changes what is asked.
Every note starts with the gap ID of ``porting/02-gaps.md`` / ``03-decisions.md``. An anchor that does not occur exactly once fails the
build, so an upstream rewording surfaces here. The engine is ``workflows/_port.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .._port import Edit, Port, list_edits
from .._port import build as _build
from .._port import convert as _convert
from .._port import drift as _drift
from .._port import git_head as _git_head

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs" / "stages"
FORK_NAME = "spec-driven-sandbox"
FORK_DIR = HERE / "sandbox" / "schemas" / FORK_NAME

# What both outputs were built from (npm @fission-ai/openspec 1.14.1). Another commit only warns.
UPSTREAM_COMMIT = "9111a7654d7800391459431fff4eaf66e33a3d2e"

CHANGE_DIR = "/openspec/changes/issue/"
STAGE_DOCS = {
    "ff": "/opsx/stages/01-ff.md",
    "apply": "/opsx/stages/02-apply.md",
    "verify": "/opsx/stages/03-verify.md",
}
ENTRY_DOC = "/opsx/core-workflow.md"

SOURCES: dict[str, tuple[str, str]] = {
    "ff": ("skills/openspec-ff-change/SKILL.md", "01-ff.md"),
    "apply": ("skills/openspec-apply-change/SKILL.md", "02-apply.md"),
    "verify": ("skills/openspec-verify-change/SKILL.md", "03-verify.md"),
}

FORK_SOURCES: dict[str, tuple[str, str]] = {
    "schema": ("schemas/spec-driven/schema.yaml", "schema.yaml"),
    **{f"tpl-{t}": (f"schemas/spec-driven/templates/{t}.md", f"templates/{t}.md") for t in ("proposal", "spec", "design", "tasks")},
}

# Left in a stage document, these mean an edit missed a case.
FORBIDDEN = (
    "ask the user",
    "Ask the user",
    "ask what they want",
    "ask for clarification",
    "ask for a valid name",
    "ask me to",
    "pause and ask",
    "wait for guidance",
    "What would you like to do?",
    "STOP and wait",
    "/openspec-",
    "**Store selection:**",
    "openspec store list",
    "suggest continuing that change",
    "Output On Pause",
    "MUST prompt",
    "When prompting",
    "verify-2.md",
)

# Left in the forked schema, these mean an edit missed a case.
FORK_FORBIDDEN = (
    "ask the user",
    "resolve them with the user",
    "Pause if you hit blockers",
    "land the tests",
    "package.json",
    "docs/export.md",
    "verify unit tests cover",
    "name: spec-driven\n",
)

_STORE = (
    "**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) "
    "or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass "
    "`--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, "
    "`list`, `show`, `validate`, `archive`, `doctor`, `context`, `schemas`, `view`). Once selected, treat "
    "`--store <id>` as sticky for the rest of the workflow. Every unscoped example of those commands below is "
    'shorthand: before running it, append the flag. For example, run `openspec status --change "<name>" --json '
    '--store "<id>"`, not the unscoped form shown below. Other commands do not take the flag. Hints printed by '
    "commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local "
    "`openspec/` root.\n\n"
)

_ASK_INPUT = (
    "1. **If no clear input provided, ask what they want to build**\n\n"
    "   Ask the user (open-ended, no preset options):\n"
    '   > "What change do you want to work on? Describe what you want to build or fix."\n\n'
    "   From their description, derive a kebab-case name (e.g., \"add user authentication\" → `add-user-auth`).\n\n"
    "   **IMPORTANT**: Do NOT proceed without understanding what the user wants to build."
)

_INPUT_UPSTREAM = (
    "**Input**: The user's request should include a change name (kebab-case) OR a description of what they want to build."
)
_INPUT_ISSUE = (
    "**Input**: The issue in the task message, between `<issue_description>` and `</issue_description>`: what to "
    "build or fix. The change name is fixed: `issue`."
)

_SELECT_ASK = "   - If ambiguous, run `openspec list --json` to get available changes and ask the user to select one\n"

EDITS: tuple[Edit, ...] = (
    # ------------------------------------------------------------------ all three
    *(Edit(s, _STORE, "", "env", "G7-3/Q7: store-selection paragraph dropped (no store is ever registered here)") for s in SOURCES),
    # ------------------------------------------------------------------ ff
    Edit("ff", _INPUT_UPSTREAM, _INPUT_ISSUE, "env", "G1-1/G5-1: input = the issue; change name fixed `issue`"),
    Edit(
        "ff",
        _ASK_INPUT,
        "1. **Read the issue**\n\n"
        "   Read the issue in full: every artifact below plans what it asks for. Nobody will describe it further.",
        "env",
        "G1-1: ask-what-to-build branch dropped; the name is not derived (G5-1)",
    ),
    Edit(
        "ff",
        "        - Identify the target project from the request and project context; the planning home may be separate "
        "from the code. If the target is unclear, ask. For greenfield or non-code changes, inspect the available "
        "structure and relevant documents. If source is unavailable, state the limitation and ask when it materially "
        "affects the plan.",
        "        - The target project is the repository at `/testbed`; the planning home (`/openspec`) is separate from "
        "the code. For greenfield or non-code changes, inspect the available structure and relevant documents. If "
        "source is unavailable, state the limitation.",
        "env",
        "G4-1: target fixed to /testbed; ask dropped, \"state the limitation\" kept",
    ),
    Edit(
        "ff",
        "   c. **If an artifact requires user input** (critically unclear context):\n"
        "      - Ask the user to clarify\n"
        "      - Then continue with creation",
        "   c. **If an artifact meets critically unclear context**:\n"
        "      - Take the most plausible reading and record it as an assumption in the artifact being written\n"
        "      - Then continue with creation",
        "semantic",
        "G4-2: most plausible reading, recorded as an assumption, in place of asking",
    ),
    Edit(
        "ff",
        '- Prompt: "Run `/openspec-apply-change` or ask me to implement to start working on the tasks."',
        f"\nAfter the last artifact, open the apply stage document (`{STAGE_DOCS['apply']}`) and continue: "
        "implementation starts in this same session.",
        "env",
        "G2-2: hand-off to apply in place of the closing prompt",
    ),
    Edit(
        "ff",
        "- If context is critically unclear, ask the user - but prefer making reasonable decisions to keep momentum",
        "- If context is critically unclear, take the most plausible reading, record it as an assumption in the "
        "artifact, and keep momentum",
        "semantic",
        "G4-2: the guardrail's own preference made absolute",
    ),
    Edit(
        "ff",
        "- If a change with that name already exists, suggest continuing that change instead\n",
        "",
        "env",
        "D-7: \"already exists → suggest continuing\" hands back to a person; cannot fire in a fresh sandbox",
    ),
    # ------------------------------------------------------------------ apply
    Edit(
        "apply",
        "**Input**: Optionally specify a change name (e.g., `/openspec-apply-change add-auth`). If omitted, check if it "
        "can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.",
        "**Input**: Optionally specify a change name (here: `issue`). If omitted, check if it can be inferred from "
        "conversation context.",
        "env",
        "G1-2/G5-1: slash-command example and the prompt-for-changes branch dropped",
    ),
    Edit("apply", _SELECT_ASK, "", "env", "G1-2: ask-to-select branch dropped (auto-select kept)"),
    Edit(
        "apply",
        '   Always announce: "Using change: <name>" and how to override (e.g., `/openspec-apply-change <other>`).',
        '   Always announce: "Using change: issue".',
        "env",
        "G1-2: override hint dropped",
    ),
    Edit(
        "apply",
        "     - If `missingArtifacts` is non-empty: suggest using `/openspec-continue-change` to create them.",
        f"     - If `missingArtifacts` is non-empty: go back to the ff stage document (`{STAGE_DOCS['ff']}`), create "
        "the missing artifacts, then resume this stage.",
        "env",
        "G2-3: blocked -> back to ff, then resume apply",
    ),
    Edit(
        "apply",
        '   - If `state: "all_done"`: report that all tracked tasks are complete and suggest review or verification '
        "as appropriate before archiving",
        '   - If `state: "all_done"`: all tracked tasks are complete; open the verify stage document '
        f"(`{STAGE_DOCS['verify']}`) and continue",
        "env",
        "G2-4: all_done -> verify",
    ),
    Edit(
        "apply",
        "   **Pause if:**\n   - Task is unclear → ask for clarification",
        "   **When a task does not go as planned** (nobody will answer; decide, record, continue):\n"
        "   - Task is unclear → implement the most plausible reading against the specs and design, and note that "
        "reading under the task in `tasks.md` as a plain line (not a checkbox)",
        "semantic",
        "G4-4: unclear task -> most plausible reading, noted under the task",
    ),
    Edit(
        "apply",
        "   - Implementation reveals a design issue → suggest updating artifacts",
        "   - Implementation reveals a design issue → update the affected artifact (design, specs or tasks) yourself, "
        "record what changed and why, and continue",
        "semantic",
        "G4-5: update the artifact yourself in place of suggesting it",
    ),
    Edit(
        "apply",
        "   - A task needs work beyond what the spec and tasks describe, or you are tempted to drop, narrow, defer, or "
        "accept exceptions to specified behavior to make it fit → surface the added scope and ask; do not absorb it "
        "silently",
        "   - A task needs work beyond what the spec and tasks describe → add that work as tasks in `tasks.md` (and to "
        "the delta spec when it is observable behavior), then do it; never drop, narrow, defer, or accept exceptions "
        "to specified behavior to make it fit",
        "semantic",
        "G4-6: extra work becomes tasks; specified behavior is never narrowed",
    ),
    Edit(
        "apply",
        "   - Error or blocker encountered → report and wait for guidance\n   - User interrupts",
        "   - Error or blocker encountered → try to resolve it; if a task stays impossible, leave it unchecked with a "
        "one-line reason under it and continue with the rest",
        "semantic",
        "G4-7: resolve or leave unchecked with a reason; interrupts dropped",
    ),
    Edit(
        "apply",
        "7. **On completion or pause, show status**\n\n"
        "   Display:\n"
        "   - Tasks completed this session\n"
        '   - Overall progress: "N/M tasks complete"\n'
        "   - If all done: report that tracked tasks are complete and suggest review or verification as appropriate "
        "before archiving\n"
        "   - If paused: explain why and wait for guidance",
        "7. **On completion, show status**\n\n"
        "   Completion: every task is checked, or the only unchecked ones carry their one-line reason.\n\n"
        "   Display:\n"
        "   - Tasks completed this session\n"
        '   - Overall progress: "N/M tasks complete"\n'
        f"   - Then open the verify stage document (`{STAGE_DOCS['verify']}`) and continue",
        "env",
        "G2-4/G4-7: completion -> verify; the pause branch dropped",
    ),
    Edit(
        "apply",
        "All tracked tasks are complete. Review or verify the change as appropriate\n"
        "before archiving. You can archive this change with `/openspec-archive-change`.",
        "All tracked tasks are complete. Next: the verify stage.",
        "env",
        "G2-4: completion output names verify, not the archive command",
    ),
    Edit(
        "apply",
        "**Output On Pause (Issue Encountered)**\n\n"
        "```\n"
        "## Implementation Paused\n\n"
        "**Change:** <change-name>\n"
        "**Schema:** <schema-name>\n"
        "**Progress:** 4/7 tasks complete\n\n"
        "### Issue Encountered\n"
        "<description of the issue>\n\n"
        "**Options:**\n"
        "1. <option 1>\n"
        "2. <option 2>\n"
        "3. Other approach\n\n"
        "What would you like to do?\n"
        "```\n",
        "",
        "semantic",
        "G4-7: pause output dropped",
    ),
    Edit(
        "apply",
        "- If task is ambiguous, pause and ask before implementing",
        "- If task is ambiguous, implement the most plausible reading and note it under the task in `tasks.md`",
        "semantic",
        "G4-4: guardrail follows the unclear-task rule",
    ),
    Edit(
        "apply",
        "- If implementation reveals issues, pause and suggest artifact updates",
        "- If implementation reveals issues, update the affected artifacts yourself and record what changed and why",
        "semantic",
        "G4-5: guardrail follows the design-issue rule",
    ),
    Edit(
        "apply",
        "- Pause on errors, blockers, or unclear requirements - don't guess",
        "- On errors or blockers, try to resolve them; a task that stays impossible is left unchecked with a one-line "
        "reason. On unclear requirements, take the most plausible reading and record it",
        "semantic",
        "G4-4/G4-7: guardrail follows the unclear-task and blocker rules",
    ),
    Edit(
        "apply",
        "- When a task needs work beyond what the spec describes, surface the added scope and pause - never silently "
        "narrow, defer, or simplify away specified behavior",
        "- When a task needs work beyond what the spec describes, add it as tasks in `tasks.md` (and to the delta spec "
        "when observable) and do it - never silently narrow, defer, or simplify away specified behavior",
        "semantic",
        "G4-6: guardrail follows the extra-work rule",
    ),
    Edit(
        "apply",
        "- **Allows artifact updates**: If implementation reveals design issues, suggest updating artifacts - not "
        "phase-locked, work fluidly",
        "- **Allows artifact updates**: If implementation reveals design issues, update the artifacts yourself - not "
        "phase-locked, work fluidly",
        "semantic",
        "G4-5: update in place of suggest",
    ),
    # ------------------------------------------------------------------ verify
    Edit(
        "verify",
        "**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation "
        "context. If vague or ambiguous you MUST prompt for available changes.",
        "**Input**: Optionally specify a change name (here: `issue`). If omitted, check if it can be inferred from "
        "conversation context.",
        "env",
        "G1-2/G5-1: the prompt-for-changes branch dropped",
    ),
    Edit(
        "verify",
        _SELECT_ASK + "\n"
        '   When prompting, show all active changes returned by the list, including changes with `status: "no-tasks"`.\n'
        "   Include the schema used for each change if available.\n"
        '   Mark changes with incomplete tasks as "(In Progress)".\n',
        "",
        "env",
        "G1-2: ask-to-select branch and its prompt format dropped (auto-select kept)",
    ),
    Edit(
        "verify",
        '   Always announce: "Using change: <name>" and how to override (e.g., `/openspec-verify-change <other>`).',
        '   Always announce: "Using change: issue".',
        "env",
        "G1-2: override hint dropped",
    ),
    Edit(
        "verify",
        "     - Check if tests exist covering the scenario",
        f"     - Check if the scenario is verified by an existing repository test or by a check script under `{CHANGE_DIR}checks/`",
        "semantic",
        "G9-3: coverage = an existing test or a checks/ script",
    ),
    Edit(
        "verify",
        '       - Recommendation: "Add test or implementation for scenario: <description>"',
        '       - Recommendation: "Add a check under `checks/` or fix the code for scenario: <description>"',
        "semantic",
        "G9-3: no repository test to add",
    ),
    Edit(
        "verify",
        "8. **Generate Verification Report**\n",
        "8. **Generate Verification Report**\n\n"
        f"   Write the report to a file in the change directory: `{CHANGE_DIR}verify.md`.\n",
        "env",
        "G5-3: the report is a file in the change dir",
    ),
    Edit(
        "verify",
        "   - Include the suggestion count when nonzero in every final assessment.\n",
        "   - Include the suggestion count when nonzero in every final assessment.\n\n"
        f"   **Next step**: go to the archive step in `{ENTRY_DOC}`. What is left stays recorded in this report.\n",
        "env",
        "G2-5: hand-off to archive; G8-1's verify -> apply round dropped (never triggered in the val ablation)",
    ),
)

SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ('"<name>"', '"issue"'),  # G5-1: the change name is fixed
    ("<change-name>", "issue"),
)

STAGES = Port(
    sources=SOURCES,
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    edits=EDITS,
    substitutions=SUBSTITUTIONS,
    forbidden=FORBIDDEN,
)

# ---------------------------------------------------------------------- the forked schema

# porting/03-decisions.md "Agreed text for the forked schema", verbatim (indented into the YAML block).
AGREED_TASKS_ITEM = """\
- Each task group MUST verify its own work as it lands: run the existing repository
  tests that cover it, or write a check script under /openspec/changes/issue/checks/
  and run it. Do NOT add or edit test files in the repository - the task's tests are
  already in place. Change repository documentation (README, docs/, changelogs) only
  when the issue asks for it; comments and docstrings in the code you change are part
  of that code. Do NOT collect verification into a final group - when a late group
  first exercises work from an early one, the failures cascade back through every
  group in between and force rework. A group whose work calls for no verification,
  such as scaffolding, carries none. A final group is for integration checks only.
"""
AGREED_EXAMPLE = {
    "1.2": "- [ ] 1.2 Write a check script at /openspec/changes/issue/checks/export_check.py that calls the export entry "
    "point and verify it fails against the current code (it should pass once the change is in)",
    "2.2": "- [ ] 2.2 Add CSV formatting utilities and verify the existing CSV tests and export_check.py pass with quoting and delimiters",
    "2.3": "- [ ] 2.3 Run the test module covering the export code and verify no existing test regresses",
}


def _indent(text: str, n: int) -> str:
    return "".join(" " * n + line if line.strip() else line for line in text.splitlines(keepends=True))


FORK_EDITS: tuple[Edit, ...] = (
    Edit("schema", "name: spec-driven\n", f"name: {FORK_NAME}\n", "env", "D-4/Q1: the fork's name, as `openspec schema fork` sets it"),
    Edit("schema", "  requires: [tasks]\n", "  requires: [ tasks ]\n", "env", "D-4: flow-list spacing as `openspec schema fork` re-serializes it (yaml Document API)"),
    Edit(
        "schema",
        "      the task breakdown, resolve it now - ask the user instead of guessing.\n",
        "      the task breakdown, resolve it now yourself - take the most plausible\n"
        "      option and write the choice and its rationale under **Decisions**.\n",
        "semantic",
        "G4-3: design Open Questions that change the plan are resolved and recorded under Decisions",
    ),
    Edit(
        "schema",
        "      Before writing tasks, check design.md for Open Questions. If any of them\n"
        "      would change what gets built, resolve them with the user first - do not\n"
        "      bake an unstated assumption into the task list.\n",
        "      Before writing tasks, check design.md for Open Questions. If any of them\n"
        "      would change what gets built, resolve them yourself first - write the\n"
        "      choice and its rationale under **Decisions** in design.md; do not\n"
        "      bake an unstated assumption into the task list.\n",
        "semantic",
        "G4-3: tasks resolve plan-changing questions themselves, recorded under Decisions",
    ),
    Edit(
        "schema",
        "      - Each task group MUST land the tests and documentation its own work\n"
        "        calls for. Do NOT collect testing or documentation into a final group -\n"
        "        when a late group first exercises work from an early one, the failures\n"
        "        cascade back through every group in between and force rework. A group\n"
        "        whose work calls for neither, such as scaffolding or dependency setup,\n"
        "        carries neither. A final group is for integration checks only, not for\n"
        "        the tests and docs an earlier group owed.\n",
        _indent(AGREED_TASKS_ITEM, 6),
        "semantic",
        "G9-1/G9-2: verification by repo tests or checks/ scripts, no test files, docs only when asked (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 1.2 Add dependencies to package.json and verify package installation succeeds\n",
        _indent(AGREED_EXAMPLE["1.2"] + "\n", 6),
        "semantic",
        "G9-4/G9-1: example 1.2 is a check script, not a dependency install (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 2.2 Add CSV formatting utilities and verify unit tests cover quoting and delimiters\n",
        _indent(AGREED_EXAMPLE["2.2"] + "\n", 6),
        "semantic",
        "G9-1: example 2.2 runs existing tests and the check (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 2.3 Document the export API in docs/export.md and verify the documented command runs as written\n",
        _indent(AGREED_EXAMPLE["2.3"] + "\n", 6),
        "semantic",
        "G9-2: example 2.3 runs the covering tests, no documentation task (agreed text)",
    ),
    Edit(
        "schema",
        "    Pause if you hit blockers or need clarification.",
        "    When a task is unclear, implement the most plausible reading against the\n"
        "    specs and design and note it under the task in tasks.md (a plain line,\n"
        "    not a checkbox). When a blocker stays unresolved, leave that task\n"
        "    unchecked with a one-line reason and continue with the rest.",
        "semantic",
        "G4-4/G4-7: the apply instruction the CLI serves decides and records instead of pausing",
    ),
)

FORK = Port(
    sources=FORK_SOURCES,
    out_dir=FORK_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    edits=FORK_EDITS,
    forbidden=FORK_FORBIDDEN,
    frontmatter=False,
)

PORTS: dict[str, Port] = {"stages": STAGES, "fork": FORK}


def convert(key: str, upstream: str) -> str:
    """One stage document from its upstream text."""
    return _convert(STAGES, key, upstream)


def convert_fork(key: str, upstream: str) -> str:
    """One file of the forked schema from its upstream text."""
    return _convert(FORK, key, upstream)


def build(upstream: Path) -> dict[str, str]:
    return _build(STAGES, upstream)


def build_fork(upstream: Path) -> dict[str, str]:
    return _build(FORK, upstream)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", type=Path, help="OpenSpec checkout")
    ap.add_argument("--check", action="store_true", help="compare with the committed outputs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        for label, port in PORTS.items():
            print(f"== {label} -> {port.out_dir.relative_to(HERE)}/")
            list_edits(port)
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
    return rc


if __name__ == "__main__":
    sys.exit(main())
