# Fix Bug

Apply the remediation proposed in the assessment (`/speckit/stages/01-assess.md`) and record the changes in this round's fix report in `/tmp/speckit/bugs/issue/`. This stage is **only** valid after `assessment.md` exists.

## Round

The fix and test stages alternate in rounds, at most three (see `/speckit/core-workflow.md`).
The round decides the report names:

| Round | Fix report (`FIX_REPORT`) | Verification report it answers |
|-------|---------------------------|--------------------------------|
| 1 | `fix.md` | — |
| 2 | `fix-2.md` | `test.md` |
| 3 | `fix-3.md` | `test-2.md` |

## Prerequisites

- `BUG_DIR` is `/tmp/speckit/bugs/issue/`. `BUG_DIR/assessment.md` MUST exist. If it does not, the assessment stage has not run: carry it out first (`/speckit/stages/01-assess.md`).
- Write this round's `FIX_REPORT` once. Never rewrite the fix report of an earlier round.
- Read `BUG_DIR/assessment.md` in full. Treat its **Proposed Remediation**, **Files likely to change**, **Checks to run**, and **Risks & Considerations** sections as the contract for this stage.
- In rounds 2 and 3, also read the previous round's fix report and verification report in full: what failed there is the new evidence this round answers.

## Execution

1. **Confirm the plan**
   - Restate, in 3–6 bullets, what you are about to change and where, based on the assessment.
   - If there are unresolved `[NEEDS CLARIFICATION]` items, flag them, choose the most plausible reading of each, record it under **Deviations from Assessment** as an assumption, and proceed.

2. **Apply the remediation**
   - **Before editing any code**, set up what will judge the fix and run it on the code as it is:
     - Copy every example the issue gives (a code snippet, a command, an input with its expected output) verbatim into a check script under `BUG_DIR/checks/`, and script the assessment's reproduction too. A check exits non-zero while the reported behavior is present.
     - Run each check now. It must fail: a check that already passes does not detect the bug, so rewrite it until it fails for the reported reason.
     - Find the existing repository tests for each file you will change (test files named after it, or test files that import it), run them, and keep the result as the baseline.
     - In rounds 2 and 3, round 1's baseline stands; a check added in a later round must fail on the code as it is before this round's change.
   - Make the code changes described by the preferred remediation. Stay within the files listed by the assessment unless newly discovered evidence requires expanding scope (in which case, log the expansion explicitly in the report).
   - The checks written before the change stay as they are; the change has to make them pass. Do not add or edit test files in the repository.
   - Keep the change minimal — do not refactor unrelated code, do not introduce dependencies that the assessment did not call for.
   - If you discover the assessment was wrong (the proposed fix does not work, the root cause is elsewhere), document the new finding in the fix report under **Deviations from Assessment** and continue from the corrected root cause. Do not edit `assessment.md`.

3. **Run local checks**
   - If the project has obvious test commands (e.g., `pytest`, `npm test`, `cargo test`), run the tests that exercise the changed paths. Capture pass/fail and key output.
   - Do not run destructive or network-dependent suites.

4. **Write the fix report**

   Write to `BUG_DIR/` + `FIX_REPORT` (round 1: `fix.md`) using this structure:

   ```markdown
   # Bug Fix: <short title>

   - **Slug**: issue
   - **Fixed**: <ISO 8601 date>
   - **Assessment**: ./assessment.md
   - **Round**: 1 | 2 | 3
   - **Previous verification**: none | ./test.md | ./test-2.md
   - **Status**: applied | partial | not-applied

   ## Summary

   <One or two sentences describing what was changed and why.>

   ## Changes

   | File | Change | Notes |
   |------|--------|-------|
   | `path/to/file.py` | <added / modified / removed> | <short note> |

   ## Diff Highlights (optional)

   <Short, illustrative snippets of the most important hunks — not a full diff dump.>

   ## Checks Added

   | Check | What it pins down | Before the change | After the change |
   |-------|-------------------|-------------------|------------------|
   | `checks/<name>.py` | <issue example / reproduction> | fail: <one line of output> | pass / fail |

   ## Baseline: Existing Tests

   - Test files: <the existing tests for the changed files>
   - `<command>` before the change: <N passed, M failed (names)>; after the change: <same, with any new failure named>

   ## Local Verification

   - Commands run: `<command>` → <result, brief>
   - Manual checks: <what was verified by hand, if anything>

   ## Deviations from Assessment

   <Empty if none. Otherwise, list any places where the actual fix departed from the proposed remediation and why.>

   ## Follow-ups

   - <suggested cleanup, monitoring, doc update, etc.>
   ```

## Next Stage

Do not stop here and do not report to the user: nobody is waiting for a report. Once this
round's `FIX_REPORT` is written, read `/speckit/stages/03-test.md` and begin this round's test stage.

## Guardrails

- Never modify files outside the repository, except this workflow's reports and checks in `BUG_DIR`.
- Never edit `assessment.md` — it is the contract you are working against. Record disagreements in this round's fix report under **Deviations from Assessment**.
- Never delete files unless the assessment explicitly required it.
- Never rewrite an earlier round's fix report.
