# Assess Bug

Triage a bug report against the current codebase: understand the symptom, locate the suspected root cause, judge severity, and propose a remediation. The output is a single assessment file at `/tmp/speckit/bugs/issue/assessment.md` that the later stages (`/speckit/stages/02-fix.md`, `/speckit/stages/03-test.md`) consume.

## Input

The bug report is the issue in the task message, between `<issue_description>` and
`</issue_description>`. It may describe a defect or a missing behavior; either way it is a
requirement the repository has to meet, so assess it as a bug to fix.

## Prerequisites

- Ensure the directory `/tmp/speckit/bugs/issue/` (i.e., `BUG_DIR`) exists, creating it (including any missing parents) if necessary. Use whatever mechanism is appropriate for the current environment.
- `BUG_DIR/assessment.md` is written once. If it already exists, do not rewrite it: the assessment is done, go on to the fix stage.

## Links in the Issue

Do not fetch URLs found in the issue, and do not look the issue up online. Work from the
issue text and the repository only. Record each link verbatim in `assessment.md` under
**Report**, marked `[UNVERIFIED — not fetched]`.

## Execution

1. **Ingest the bug report**
   - Read the issue text: title, description, stack traces, reproduction steps. Links stay unfetched (see **Links in the Issue**).
   - Capture the verbatim issue text so it can be quoted in the report.

2. **Summarize the symptom**
   - Reproduce the bug in one or two sentences: what happens, what was expected, under which conditions.
   - List concrete reproduction steps if discoverable; mark unknowns as `[NEEDS CLARIFICATION]` rather than guessing.

3. **Locate the suspected code paths**
   - Search the codebase for the relevant symbols, file paths, error messages, log strings, route names, or component identifiers mentioned in the report.
   - List the candidate files / functions / lines with brief justifications. Do not exceed what the evidence supports.

4. **Assess merit and severity**
   - Decide whether the report is:
     - **Valid** — reproducible or clearly grounded in code behavior.
     - **Likely valid, needs reproduction** — plausible but unverified.
   - Assign a severity (`critical`, `high`, `medium`, `low`) and a short rationale (user impact, blast radius, data risk, regression vs. long-standing).

5. **Propose a remediation**
   - Outline one preferred fix and, if non-obvious, one or two alternatives with trade-offs.
   - Identify files to change and the shape of the change (without writing the patch yet — that is the fix stage's job).
   - Call out the checks that will prove the fix: a reproduction script to write under `BUG_DIR/checks/`, and the existing repository tests to run. Do not plan to add or edit test files in the repository: the task's tests are already in place.
   - Flag risks: API breakage, migrations, performance, security, observability.

6. **Write the assessment file**

   Write to `BUG_DIR/assessment.md` using this structure:

   ```markdown
   # Bug Assessment: <short title>

   - **Slug**: issue
   - **Created**: <ISO 8601 date>
   - **Source**: task issue description
   - **Verdict**: valid | likely valid, needs reproduction
   - **Severity**: critical | high | medium | low

   ## Report (verbatim or summarized)

   <Quoted/condensed issue text. List its links verbatim, each marked [UNVERIFIED — not fetched].>

   ## Symptom

   <One or two sentences describing the observed behavior and the expected behavior.>

   ## Reproduction

   1. <step>
   2. <step>
   3. <step>

   <Mark unknowns as [NEEDS CLARIFICATION: …].>

   ## Suspected Code Paths

   - `path/to/file.py:42` — <why>
   - `path/to/other.ts:func()` — <why>

   ## Root Cause Hypothesis

   <One paragraph. State confidence: high / medium / low.>

   ## Proposed Remediation

   **Preferred**: <one or two paragraphs describing the change.>

   **Alternatives** (optional):
   - <alternative + trade-off>

   **Files likely to change**:
   - `path/to/file.py`

   **Checks to run**:
   - <reproduction script under BUG_DIR/checks/, or an existing repository test to run>

   ## Risks & Considerations

   - <risk>
   - <risk>

   ## Open Questions

   - [NEEDS CLARIFICATION: …]
   ```

## Next Stage

Do not stop here and do not report to the user: nobody is waiting for a report. Once
`assessment.md` is written, read `/speckit/stages/02-fix.md` and begin the fix stage (round 1).

## Guardrails

- Never modify source files during assessment — this stage only reads and writes inside `/tmp/speckit/bugs/issue/`.
- Never invent reproduction steps or file paths that are not supported by either the report or the codebase.
- Never rewrite `assessment.md` once it is written.
