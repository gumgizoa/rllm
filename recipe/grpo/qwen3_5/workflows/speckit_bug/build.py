"""Build ``docs/stages/`` from Spec Kit's bug extension (``extensions/bug/commands/``).

    python -m recipe.grpo.qwen3_5.workflows.speckit_bug.build --spec-kit /path/to/spec-kit
    python -m recipe.grpo.qwen3_5.workflows.speckit_bug.build --spec-kit ... --check   # exit 1 if docs/stages drifted
    python -m recipe.grpo.qwen3_5.workflows.speckit_bug.build --list                   # the edits, by tag

Spec Kit's three bug commands are written for an agent app a person drives one command at a time:
the person types ``/speckit-bug-assess <report> slug=x``, the app fills ``$ARGUMENTS``, the command
reports back and stops, and the person invokes the next one. A rollout here is one user message and
no person, so each command becomes a stage document and the person's part moves into the documents.
``docs/core-workflow.md`` (the order of the stages, the rounds, the artifact rules) is hand-written:
Spec Kit has no document that strings the commands together -- the person, or ``workflow.yml``
driving ``claude -p`` once per step, does that.

Every change to the upstream text is a named entry below, tagged:

``env``       closes a gap between Spec Kit's setting and an unattended sandbox run without changing
              what the stage asks for: no ``$ARGUMENTS`` / slug / hook machinery, absolute paths outside
              the repository, "go to the next stage" in place of "report back to the user".
``loop``      the bounded fix -> test loop (at most three rounds; ``fix.md``/``test.md``,
              ``fix-2.md``/``test-2.md``, ``fix-3.md``/``test-3.md``). Upstream ends a failed test
              with "re-run assess" for the person to act on.
``semantic``  changes what a stage asks the agent to do: no ``invalid`` exit, no stop on
              ``[NEEDS CLARIFICATION]`` or on a wrong assessment, no URL fetching, checks written
              outside the repository instead of repository tests, repository tests not "expensive".

An anchor that does not occur exactly once fails the build, so an upstream rewording surfaces here
instead of passing through unedited. The engine is ``workflows/_port.py``; this file is the edit table.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .._port import Edit, Port, Section
from .._port import build as _build
from .._port import convert as _convert
from .._port import main as _main

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs" / "stages"

# What docs/stages was built from. --check against another commit warns; the anchors decide.
UPSTREAM_COMMIT = "0443760542e7e5269724744a2ac55c4bd386d095"
EXTENSION_VERSION = "1.0.1"

BUG_DIR = "/tmp/speckit/bugs/issue/"
STAGE_DOCS = {
    "assess": "/speckit/stages/01-assess.md",
    "fix": "/speckit/stages/02-fix.md",
    "test": "/speckit/stages/03-test.md",
}
STAGES = {  # stage -> (upstream file, output file)
    "assess": ("speckit.bug.assess.md", "01-assess.md"),
    "fix": ("speckit.bug.fix.md", "02-fix.md"),
    "test": ("speckit.bug.test.md", "03-test.md"),
}

# Left in any stage document, these mean an edit missed something.
FORBIDDEN = (
    "$ARGUMENTS",
    "__SPECKIT_COMMAND_",
    ".specify",
    "extensions.yml",
    "slug=",
    "ask the user",
    "nteractive",
    "consent",
    "Report back",
    "invalid",
)


_NEXT_ROUND_TABLE_FIX = """\
| Round | Fix report (`FIX_REPORT`) | Verification report it answers |
|-------|---------------------------|--------------------------------|
| 1 | `fix.md` | — |
| 2 | `fix-2.md` | `test.md` |
| 3 | `fix-3.md` | `test-2.md` |"""

_NEXT_ROUND_TABLE_TEST = """\
| Round | Fix report it checks | Verification report (`TEST_REPORT`) |
|-------|----------------------|-------------------------------------|
| 1 | `fix.md` | `test.md` |
| 2 | `fix-2.md` | `test-2.md` |
| 3 | `fix-3.md` | `test-3.md` |"""

SECTIONS: tuple[Section, ...] = (
    # -- hooks: .specify/extensions.yml never exists here, and upstream skips silently without it.
    *(Section(s, "## Pre-Execution Checks", None, "env", "extension hooks: no extensions.yml in the sandbox") for s in STAGES),
    *(Section(s, "## Mandatory Post-Execution Hooks", None, "env", "extension hooks: no extensions.yml in the sandbox") for s in STAGES),
    # -- slug: one bug per sandbox, so the slug is the constant `issue`.
    *(Section(s, "## Slug Resolution", None, "env", "slug fixed to `issue`") for s in STAGES),
    # -- input: the task message instead of $ARGUMENTS.
    Section(
        "assess",
        "## User Input",
        "## Input\n\n"
        "The bug report is the issue in the task message, between `<issue_description>` and\n"
        "`</issue_description>`. It may describe a defect or a missing behavior; either way it is a\n"
        "requirement the repository has to meet, so assess it as a bug to fix.\n",
        "semantic",
        "input = the task's issue; it is a real requirement (replaces the `invalid` path)",
    ),
    Section(
        "fix",
        "## User Input",
        "## Round\n\n"
        "The fix and test stages alternate in rounds, at most three (see `/speckit/core-workflow.md`).\n"
        "The round decides the report names:\n\n" + _NEXT_ROUND_TABLE_FIX + "\n",
        "loop",
        "round table in place of slug input",
    ),
    Section(
        "test",
        "## User Input",
        "## Round\n\n"
        "The fix and test stages alternate in rounds, at most three (see `/speckit/core-workflow.md`).\n"
        "This stage checks the fix report of the same round:\n\n" + _NEXT_ROUND_TABLE_TEST + "\n",
        "loop",
        "round table in place of slug input",
    ),
    # -- URLs: the allowlist fetched github.com unprompted, i.e. the upstream fix PR.
    Section(
        "assess",
        "## Safety When Fetching URLs",
        "## Links in the Issue\n\n"
        "Do not fetch URLs found in the issue, and do not look the issue up online. Work from the\n"
        "issue text and the repository only. Record each link verbatim in `assessment.md` under\n"
        "**Report**, marked `[UNVERIFIED — not fetched]`.\n",
        "semantic",
        "no URL fetching (upstream fetches github.com etc. without asking)",
    ),
    # -- completion: "report back and stop" would end the rollout after one stage.
    Section(
        "assess",
        "## Completion Report",
        "## Next Stage\n\n"
        "Do not stop here and do not report to the user: nobody is waiting for a report. Once\n"
        "`assessment.md` is written, read `/speckit/stages/02-fix.md` and begin the fix stage (round 1).\n",
        "env",
        "next stage instead of report-and-stop",
    ),
    Section(
        "fix",
        "## Completion Report",
        "## Next Stage\n\n"
        "Do not stop here and do not report to the user: nobody is waiting for a report. Once this\n"
        "round's `FIX_REPORT` is written, read `/speckit/stages/03-test.md` and begin this round's test stage.\n",
        "env",
        "next stage instead of report-and-stop",
    ),
    Section(
        "test",
        "## Completion Report",
        "## Next Stage\n\n"
        "Do not stop to report to the user: nobody is waiting for a report. Decide from this report's\n"
        "**Result** and the round:\n\n"
        "- `verified` — the workflow is complete; finish the task.\n"
        "- `partial` or `failed` in round 1 or 2 — read `/speckit/stages/02-fix.md` again and begin the\n"
        "  next round's fix stage, with this report as its new evidence.\n"
        "- Round 3, any result — the workflow is complete; finish the task. What is still unresolved is\n"
        "  recorded in this report.\n",
        "loop",
        "verified ends; partial/failed loops back to fix, at most 3 rounds",
    ),
)

EDITS: tuple[Edit, ...] = (
    # ---------------------------------------------------------------- assess
    Edit(
        "assess",
        "downstream commands (`__SPECKIT_COMMAND_BUG_FIX__`, `__SPECKIT_COMMAND_BUG_TEST__`) consume.",
        f"the later stages (`{STAGE_DOCS['fix']}`, `{STAGE_DOCS['test']}`) consume.",
        "env",
        "commands -> stage documents",
    ),
    Edit(
        "assess",
        "- If `BUG_DIR/assessment.md` already exists, ask the user whether to overwrite it before continuing "
        "(in interactive mode); in automated mode, refuse and pick a new unique slug instead.",
        "- `BUG_DIR/assessment.md` is written once. If it already exists, do not rewrite it: the assessment "
        "is done, go on to the fix stage.",
        "env",
        "write once; no new slug",
    ),
    Edit(
        "assess",
        "   - If a URL is present, first apply the **URL Trust Policy** above to decide whether to fetch, prompt, "
        "or refuse. If the policy permits the fetch, retrieve the page and extract the relevant content (title, "
        "description, stack traces, reproduction steps, comments).\n"
        "   - Capture the verbatim source (URL or pasted block) so it can be quoted in the report.\n"
        "   - If a pasted report cannot be understood at all (empty, unrelated, spam), tell the user the verdict "
        "is `invalid` with a clear reason and stop immediately. Do not write `assessment.md`, run post-hooks, or "
        "proceed to the Completion Report. This early exit does not replace the URL Trust Policy's required "
        "recording above or the normal assessment of an intelligible report that turns out not to be a bug.",
        "   - Read the issue text: title, description, stack traces, reproduction steps. Links stay unfetched "
        "(see **Links in the Issue**).\n"
        "   - Capture the verbatim issue text so it can be quoted in the report.",
        "semantic",
        "no fetch, no `invalid` early exit",
    ),
    Edit(
        "assess",
        "     - **Invalid / not a bug** — misuse, expected behavior, duplicate, or out of scope. State why.\n",
        "",
        "semantic",
        "no `invalid` verdict",
    ),
    Edit(
        "assess",
        "   - Identify files to change and the shape of the change (without writing the patch yet — that is "
        "`__SPECKIT_COMMAND_BUG_FIX__`'s job).\n"
        "   - Call out tests that should exist or be added to lock the fix in.",
        "   - Identify files to change and the shape of the change (without writing the patch yet — that is "
        "the fix stage's job).\n"
        "   - Call out the checks that will prove the fix: a reproduction script to write under `BUG_DIR/checks/`, "
        "and the existing repository tests to run. Do not plan to add or edit test files in the repository: "
        "the task's tests are already in place.",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "assess",
        '   - **Source**: <URL or "pasted text">\n   - **Verdict**: valid | likely valid, needs reproduction | invalid',
        "   - **Source**: task issue description\n   - **Verdict**: valid | likely valid, needs reproduction",
        "semantic",
        "no `invalid` verdict; source is the task",
    ),
    Edit(
        "assess",
        "   <Quoted/condensed report content. If a URL was fetched, include the title and a short excerpt; link the URL.>",
        "   <Quoted/condensed issue text. List its links verbatim, each marked [UNVERIFIED — not fetched].>",
        "env",
        "no fetched page to quote",
    ),
    Edit(
        "assess",
        "   - `path/to/file.py`\n   - `path/to/test_file.py`\n\n   **Tests to add or update**:\n   - <test description>",
        "   - `path/to/file.py`\n\n   **Checks to run**:\n   - <reproduction script under BUG_DIR/checks/, or an existing repository test to run>",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "assess",
        "- Never overwrite an existing `assessment.md` without confirmation.\n"
        "- If the bug report cannot be understood at all (empty, unrelated, spam), set verdict to `invalid` "
        "with a clear reason and stop.",
        "- Never rewrite `assessment.md` once it is written.",
        "semantic",
        "write once; no `invalid` exit",
    ),
    # ---------------------------------------------------------------- fix
    Edit(
        "fix",
        "Apply the remediation that was proposed by `__SPECKIT_COMMAND_BUG_ASSESS__` and record the changes in a "
        "fix report at `.specify/bugs/<slug>/fix.md`. This command is **only** valid after an assessment exists "
        "for the given slug.",
        f"Apply the remediation proposed in the assessment (`{STAGE_DOCS['assess']}`) and record the changes in "
        f"this round's fix report in `{BUG_DIR}`. This stage is **only** valid after `assessment.md` exists.",
        "loop",
        "per-round fix report",
    ),
    Edit(
        "fix",
        "- `BUG_DIR/assessment.md` MUST exist. If it does not, stop and instruct the user to run "
        "`__SPECKIT_COMMAND_BUG_ASSESS__` first.\n"
        "- If `BUG_DIR/fix.md` already exists, ask the user whether to overwrite it before continuing "
        "(interactive mode) or refuse (automated mode).\n"
        "- Read `BUG_DIR/assessment.md` in full. Treat its **Proposed Remediation**, **Files likely to change**, "
        "**Tests to add or update**, and **Risks & Considerations** sections as the contract for this command.",
        f"- `BUG_DIR` is `{BUG_DIR}`. `BUG_DIR/assessment.md` MUST exist. If it does not, the assessment stage "
        f"has not run: carry it out first (`{STAGE_DOCS['assess']}`).\n"
        "- Write this round's `FIX_REPORT` once. Never rewrite the fix report of an earlier round.\n"
        "- Read `BUG_DIR/assessment.md` in full. Treat its **Proposed Remediation**, **Files likely to change**, "
        "**Checks to run**, and **Risks & Considerations** sections as the contract for this stage.\n"
        "- In rounds 2 and 3, also read the previous round's fix report and verification report in full: what "
        "failed there is the new evidence this round answers.",
        "loop",
        "self-recover instead of instructing the user; per-round reports",
    ),
    Edit(
        "fix",
        "   - If the assessment's verdict is `invalid`, stop — there is nothing to fix. Tell the user and exit.\n"
        "   - If the verdict is `likely valid, needs reproduction` and there are unresolved `[NEEDS CLARIFICATION]` "
        "items, flag them and ask the user whether to proceed in interactive mode, or stop in automated mode.",
        "   - If there are unresolved `[NEEDS CLARIFICATION]` items, flag them, choose the most plausible reading "
        "of each, record it under **Deviations from Assessment** as an assumption, and proceed.",
        "semantic",
        "no `invalid` exit; proceed on the most plausible reading instead of stopping",
    ),
    Edit(
        "fix",
        "2. **Apply the remediation**\n",
        "2. **Apply the remediation**\n"
        "   - **Before editing any code**, set up what will judge the fix and run it on the code as it is:\n"
        "     - Copy every example the issue gives (a code snippet, a command, an input with its expected output) "
        "verbatim into a check script under `BUG_DIR/checks/`, and script the assessment's reproduction too. A "
        "check exits non-zero while the reported behavior is present.\n"
        "     - Run each check now. It must fail: a check that already passes does not detect the bug, so rewrite "
        "it until it fails for the reported reason.\n"
        "     - Find the existing repository tests for each file you will change (test files named after it, or "
        "test files that import it), run them, and keep the result as the baseline.\n"
        "     - In rounds 2 and 3, round 1's baseline stands; a check added in a later round must fail on the code "
        "as it is before this round's change.\n",
        "semantic",
        "G9-5: checks from the issue's own examples, seen failing before the change; existing tests run first as the baseline",
    ),
    Edit(
        "fix",
        "   - Add or update the tests called out in the assessment so the bug cannot regress silently.",
        "   - The checks written before the change stay as they are; the change has to make them pass. Do not add "
        "or edit test files in the repository.",
        "semantic",
        "checks outside the repository instead of repository tests (G9-1); written before the change (G9-5)",
    ),
    Edit(
        "fix",
        "STOP modifying code, document the new finding in the fix report under **Deviations from Assessment**, "
        "and recommend re-running `__SPECKIT_COMMAND_BUG_ASSESS__`.",
        "document the new finding in the fix report under **Deviations from Assessment** and continue from the "
        "corrected root cause. Do not edit `assessment.md`.",
        "semantic",
        "continue instead of stopping for a re-assessment",
    ),
    Edit(
        "fix",
        "   - Do not run destructive or network-dependent suites without the user's consent.",
        "   - Do not run destructive or network-dependent suites.",
        "env",
        "no one to consent",
    ),
    Edit(
        "fix",
        "   Write to `BUG_DIR/fix.md` using this structure:",
        "   Write to `BUG_DIR/` + `FIX_REPORT` (round 1: `fix.md`) using this structure:",
        "loop",
        "per-round fix report",
    ),
    Edit(
        "fix",
        "   - **Assessment**: ./assessment.md\n   - **Status**",
        "   - **Assessment**: ./assessment.md\n"
        "   - **Round**: 1 | 2 | 3\n"
        "   - **Previous verification**: none | ./test.md | ./test-2.md\n"
        "   - **Status**",
        "loop",
        "round fields",
    ),
    Edit(
        "fix",
        "   | `path/to/test_file.py` | added test | <short note> |\n",
        "",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "fix",
        "   ## Tests Added or Updated\n\n   - `path/to/test_file.py::test_name` — <what it pins down>",
        "   ## Checks Added\n\n"
        "   | Check | What it pins down | Before the change | After the change |\n"
        "   |-------|-------------------|-------------------|------------------|\n"
        "   | `checks/<name>.py` | <issue example / reproduction> | fail: <one line of output> | pass / fail |\n\n"
        "   ## Baseline: Existing Tests\n\n"
        "   - Test files: <the existing tests for the changed files>\n"
        "   - `<command>` before the change: <N passed, M failed (names)>; after the change: <same, with any new failure named>",
        "semantic",
        "checks outside the repository instead of repository tests (G9-1); before/after results and the baseline (G9-5)",
    ),
    Edit(
        "fix",
        "- Never modify files outside the project workspace.",
        "- Never modify files outside the repository, except this workflow's reports and checks in `BUG_DIR`.",
        "env",
        "reports live outside the repository",
    ),
    Edit(
        "fix",
        "Record disagreements in `fix.md` under **Deviations from Assessment**.\n"
        "- Never delete files unless the assessment explicitly required it.\n"
        "- Never overwrite an existing `fix.md` without confirmation.",
        "Record disagreements in this round's fix report under **Deviations from Assessment**.\n"
        "- Never delete files unless the assessment explicitly required it.\n"
        "- Never rewrite an earlier round's fix report.",
        "loop",
        "per-round fix report",
    ),
    # ---------------------------------------------------------------- test
    Edit(
        "test",
        "Validate that the fix recorded by `__SPECKIT_COMMAND_BUG_FIX__` actually resolves the bug described by "
        "`__SPECKIT_COMMAND_BUG_ASSESS__`. The output is a verification report at `.specify/bugs/<slug>/test.md`.",
        "Validate that the fix recorded in this round's fix report actually resolves the bug described in "
        f"`assessment.md`. The output is this round's verification report in `{BUG_DIR}`.",
        "loop",
        "per-round verification report",
    ),
    Edit(
        "test",
        "- `BUG_DIR/assessment.md` MUST exist.\n"
        "- `BUG_DIR/fix.md` MUST exist. If not, stop and instruct the user to run `__SPECKIT_COMMAND_BUG_FIX__` first.\n"
        "- If `BUG_DIR/test.md` already exists, ask the user whether to overwrite it (interactive mode) or refuse "
        "(automated mode).\n"
        "- Read both `assessment.md` and `fix.md` in full so you know:",
        f"- `BUG_DIR` is `{BUG_DIR}`. `BUG_DIR/assessment.md` MUST exist.\n"
        f"- This round's fix report MUST exist. If not, carry out this round's fix stage first (`{STAGE_DOCS['fix']}`).\n"
        "- Write this round's `TEST_REPORT` once. Never rewrite the verification report of an earlier round.\n"
        "- Read both `assessment.md` and this round's fix report in full so you know:",
        "loop",
        "self-recover instead of instructing the user; per-round reports",
    ),
    Edit(
        "test",
        "  - The actual code changes and tests added (from `fix.md`).",
        "  - The actual code changes and checks added (from this round's fix report).",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "test",
        "     - Run the tests added or updated in the fix.",
        "     - Run the checks added in the fix.",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "test",
        "   - If a check is destructive, network-dependent, or expensive, skip it and record it as `skipped` with a "
        "reason; do not run it without explicit user consent.",
        "   - If a check is destructive or network-dependent, skip it and record it as `skipped` with a reason. "
        "Running the repository's tests for the changed modules is neither, and is expected.",
        "semantic",
        "repository tests are not a skippable 'expensive' check",
    ),
    Edit(
        "test",
        "     - **verified** — all critical checks pass and the original symptom no longer reproduces.\n"
        "     - **partial** — the original symptom is gone but unrelated regressions appeared, or some checks are "
        "inconclusive.\n"
        "     - **failed** — the symptom still reproduces or the regression suite is broken by the fix.",
        "     - **verified** — only when all three hold: every check in the fix report passes now after failing "
        "before the change; every example from the issue behaves as the issue expects; the existing tests of the "
        "fix report's baseline show no new failure.\n"
        "     - **partial** — none of those fails, but one of them was not run or is inconclusive.\n"
        "     - **failed** — a check from the fix still fails, an example from the issue still shows the reported "
        "behavior, or an existing test that passed in the baseline now fails.",
        "semantic",
        "G8-2: the verdict rests on the fix's before/after checks, the issue's examples and the baseline (G9-5)",
    ),
    Edit(
        "test",
        "   Write to `BUG_DIR/test.md` using this structure:",
        "   Write to `BUG_DIR/` + `TEST_REPORT` (round 1: `test.md`) using this structure:",
        "loop",
        "per-round verification report",
    ),
    Edit(
        "test",
        "   - **Fix**: ./fix.md\n",
        "   - **Fix**: ./fix.md | ./fix-2.md | ./fix-3.md\n   - **Round**: 1 | 2 | 3\n",
        "loop",
        "round fields",
    ),
    Edit(
        "test",
        "   | New / updated tests | `<command>` | pass / fail | <short note> |",
        "   | Checks from the fix | `<command>` | pass / fail | <short note> |",
        "semantic",
        "checks outside the repository instead of repository tests",
    ),
    Edit(
        "test",
        '   - "Hold — reproduction inconclusive; needs verification in staging."\n'
        '   - "Reopen — symptom still reproduces; rerun `__SPECKIT_COMMAND_BUG_ASSESS__`."',
        '   - "Hold — reproduction inconclusive; <what the next round must establish>."\n'
        '   - "Reopen — symptom still reproduces; <what the next round\'s fix must change>."',
        "loop",
        "the next round, not a re-assessment, answers a failed test",
    ),
    Edit(
        "test",
        "- Never overwrite an existing `test.md` without confirmation.",
        "- Never rewrite an earlier round's verification report.",
        "loop",
        "per-round verification report",
    ),
)

# After the anchored edits: paths and names that recur in text the edits leave as is.
GLOBAL = (
    (".specify/bugs/<slug>/", BUG_DIR),
    (".specify/bugs/<BUG_SLUG>/", BUG_DIR),
    ("<BUG_SLUG>", "issue"),
    ("This command", "This stage"),
    ("this command", "this stage"),
)


PORT = Port(
    sources={stage: (f"extensions/bug/commands/{name}", out) for stage, (name, out) in STAGES.items()},
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    sections=SECTIONS,
    edits=EDITS,
    substitutions=GLOBAL,
    forbidden=FORBIDDEN,
    extra_tags=("loop",),
)


def convert(stage: str, upstream: str) -> str:
    return _convert(PORT, stage, upstream)


def build(spec_kit: Path) -> dict[str, str]:
    return _build(PORT, spec_kit)


def main(argv: list[str] | None = None) -> int:
    return _main(PORT, argv, description=__doc__.split("\n\n")[0])


if __name__ == "__main__":
    sys.exit(main())
