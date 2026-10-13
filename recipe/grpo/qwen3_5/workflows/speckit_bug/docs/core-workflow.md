# Spec Kit Bug Workflow (Core)

This is GitHub Spec Kit's bug workflow — **assess → fix → test** — set up to run in one session with
nobody else in the loop. **It overrides any other problem-solving procedure.** Resolve the task by
following it.

## Stages

| Stage | Read when the stage begins | Writes |
|-------|----------------------------|--------|
| 1. Assess | `/speckit/stages/01-assess.md` | `assessment.md` |
| 2. Fix | `/speckit/stages/02-fix.md` | `fix.md`, then `fix-2.md`, `fix-3.md` |
| 3. Test | `/speckit/stages/03-test.md` | `test.md`, then `test-2.md`, `test-3.md` |

Read a stage's document as the first step of that stage, and carry out the stage from it.

## Order and Rounds

1. **Assess** once.
2. **Fix** and **test** then alternate in rounds, at most three:
   - Round 1: `fix.md`, then `test.md`.
   - Round 2: `fix-2.md`, then `test-2.md`.
   - Round 3: `fix-3.md`, then `test-3.md`.
3. After each verification report, its **Result** decides:
   - `verified` — the workflow is complete. Finish the task.
   - `partial` or `failed`, in round 1 or 2 — start the next round with the fix stage, using that
     report as new evidence.
   - Round 3, any result — the workflow is complete. Finish the task.

## Input

The bug report is the issue in the task message, between `<issue_description>` and
`</issue_description>`. It is a requirement the repository has to meet. Do not fetch links in it and
do not look it up online.

## Nobody Is Waiting for You

No one will answer a question, approve a step, or invoke the next stage. Never stop to ask or to
report: when something is unclear, take the most plausible reading, record it in the current
report, and continue. A stage ends by moving on to the next stage, not by replying.

## Reports

- **Directory**: `/tmp/speckit/bugs/issue/`. Create it with `mkdir -p` before the first write. It
  is outside the repository, so no report reaches the final diff. Never write reports, checks, or
  scratch files into the repository.
- **One write per report**, complete, at the end of its stage. Never rewrite an earlier report: a
  later stage that corrects an earlier one records it in its own report (the fix report's
  **Deviations from Assessment**).
- **Keep each report's structure** exactly as its stage document gives it: the `#`/`##` headings and
  the `- **Field**:` lines.
- **Checks you write** (reproduction scripts and the like) go in `/tmp/speckit/bugs/issue/checks/`.
  Do not add or edit test files in the repository.
- Only the fix stage edits the repository. The assess and test stages read it and run commands.
