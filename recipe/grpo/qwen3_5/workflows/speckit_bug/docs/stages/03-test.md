# Test Bug Fix

Validate that the fix recorded in this round's fix report actually resolves the bug described in `assessment.md`. The output is this round's verification report in `/tmp/speckit/bugs/issue/`.

## Round

The fix and test stages alternate in rounds, at most three (see `/speckit/core-workflow.md`).
This stage checks the fix report of the same round:

| Round | Fix report it checks | Verification report (`TEST_REPORT`) |
|-------|----------------------|-------------------------------------|
| 1 | `fix.md` | `test.md` |
| 2 | `fix-2.md` | `test-2.md` |
| 3 | `fix-3.md` | `test-3.md` |

## Prerequisites

- `BUG_DIR` is `/tmp/speckit/bugs/issue/`. `BUG_DIR/assessment.md` MUST exist.
- This round's fix report MUST exist. If not, carry out this round's fix stage first (`/speckit/stages/02-fix.md`).
- Write this round's `TEST_REPORT` once. Never rewrite the verification report of an earlier round.
- Read both `assessment.md` and this round's fix report in full so you know:
  - The original symptom and reproduction steps (from `assessment.md`).
  - The actual code changes and checks added (from this round's fix report).

## Execution

1. **Plan the validation**
   - Decide which checks prove the bug is gone:
     - Re-run the reproduction steps from the assessment (or their automated equivalent).
     - Run the checks added in the fix.
     - Run any broader regression suite that touches the changed files.
   - Decide which checks prove nothing was broken:
     - Existing test suites for the changed modules.
     - Lint / type-check if the project uses them.

2. **Run the checks**
   - Execute each planned check. Capture command, exit status, and a short excerpt of relevant output (last few lines, or the failing assertion).
   - If a check is destructive or network-dependent, skip it and record it as `skipped` with a reason. Running the repository's tests for the changed modules is neither, and is expected.
   - If you cannot run a check at all (missing tooling, no test framework configured), record it as `not-run` with a reason instead of fabricating a result.

3. **Judge the outcome**
   - Mark the fix as:
     - **verified** — only when all three hold: every check in the fix report passes now after failing before the change; every example from the issue behaves as the issue expects; the existing tests of the fix report's baseline show no new failure.
     - **partial** — none of those fails, but one of them was not run or is inconclusive.
     - **failed** — a check from the fix still fails, an example from the issue still shows the reported behavior, or an existing test that passed in the baseline now fails.
   - Do not over-claim. If reproduction was not actually performed (e.g., the bug required a production environment), say so explicitly.

4. **Write the verification report**

   Write to `BUG_DIR/` + `TEST_REPORT` (round 1: `test.md`) using this structure:

   ```markdown
   # Bug Verification: <short title>

   - **Slug**: issue
   - **Tested**: <ISO 8601 date>
   - **Assessment**: ./assessment.md
   - **Fix**: ./fix.md | ./fix-2.md | ./fix-3.md
   - **Round**: 1 | 2 | 3
   - **Result**: verified | partial | failed

   ## Summary

   <One or two sentences: does the bug reproduce, did the fix hold, were any regressions found.>

   ## Checks Performed

   | Check | Command / Action | Result | Notes |
   |-------|------------------|--------|-------|
   | Reproduction (post-fix) | <command or manual steps> | pass / fail / skipped / not-run | <short note> |
   | Checks from the fix | `<command>` | pass / fail | <short note> |
   | Regression suite | `<command>` | pass / fail / skipped | <short note> |
   | Lint / type-check | `<command>` | pass / fail / skipped | <short note> |

   ## Output Excerpts

   <Short snippets of relevant output (e.g., final summary line of a test run, the failing assertion). Keep it tight — no full logs.>

   ## Residual Risks

   - <known limitation, environment not covered, etc.>

   ## Recommendation

   <One paragraph. Examples:>
   - "Close the bug — verified end-to-end."
   - "Hold — reproduction inconclusive; <what the next round must establish>."
   - "Reopen — symptom still reproduces; <what the next round's fix must change>."
   ```

## Next Stage

Do not stop to report to the user: nobody is waiting for a report. Decide from this report's
**Result** and the round:

- `verified` — the workflow is complete; finish the task.
- `partial` or `failed` in round 1 or 2 — read `/speckit/stages/02-fix.md` again and begin the
  next round's fix stage, with this report as its new evidence.
- Round 3, any result — the workflow is complete; finish the task. What is still unresolved is
  recorded in this report.

## Guardrails

- This stage MUST NOT modify source code. It only runs checks and writes inside `/tmp/speckit/bugs/issue/`.
- Never rewrite an earlier round's verification report.
- Never mark a fix as `verified` based on tests alone if the original assessment listed a reproduction that you did not actually exercise — downgrade to `partial` and say so.
