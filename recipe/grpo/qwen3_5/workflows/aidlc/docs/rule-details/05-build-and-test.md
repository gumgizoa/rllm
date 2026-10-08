# Build and Test

**Purpose**: Build the change, verify that it resolves the issue, and confirm that it introduces no regression

**Artifact**: `/tmp/swe-bench-pro/05-build-and-test.md`

## Prerequisites
- Code Generation is complete: source modified and the reproduction script written but not executed, recorded in `/tmp/swe-bench-pro/04-code-generation-generation.md`
- Reverse Engineering is complete: the build and test commands and the baseline — which covering tests passed, and which already failed — recorded in `/tmp/swe-bench-pro/01-reverse-engineering.md`

**The baseline and the test command are established, not re-derived.** Use them as Reverse Engineering recorded them. Read `/tmp/swe-bench-pro/01-reverse-engineering.md` only if that content is no longer visible — never re-run the tests to reconstruct a baseline, because the source has since changed and the result would no longer be a baseline.

## Execution Steps

### Step 1: Build

- [ ] Run the build or type-check command Reverse Engineering recorded
- [ ] Confirm it succeeds

**Do NOT** install dependencies or set up the environment — it can already build and test the project.

**CRITICAL**: A build or compilation failure means no test can run at all. Resolve it before any other verification.

### Step 2: Verify the Issue Is Resolved

- [ ] Execute the reproduction script at the path Code Generation recorded
- [ ] Confirm the behavior the Functional Requirements describe
- [ ] Confirm the conditions the Edge Cases & Error Handling requirements describe
- [ ] Confirm the constraints the Non-Functional Requirements state, where any are stated

The reproduction script is the only direct evidence that the reported behavior is now correct.

### Step 3: Verify No Regression

- [ ] Re-run the existing covering tests identified in Reverse Engineering
- [ ] Run the **same selection** that produced the baseline
- [ ] **MANDATORY**: Compare the result against the recorded baseline

**Do NOT** run the full repository test suite. It is not comparable to the baseline, and its failures are dominated by conditions unrelated to the change.

### Step 4: Classify Any Failure Before Fixing It

If the build succeeded and both Step 2 and Step 3 passed, nothing has failed — skip to Step 6 and write the artifact. Steps 4 and 5 apply only to a failure.

| Failure | Response |
|---|---|
| **Reproduction script failure** | The patch logic is wrong. Re-read the requirement and correct the source |
| **Existing test failure, but it passed in the baseline** | A regression. Suspect a broken contract first — check the interfaces the plan marked as preserved |
| **Existing test failure that also failed in the baseline** | A pre-existing failure. **Do not fix it.** Record the reasoning that identifies it as pre-existing |

### Step 5: Fix and Re-verify

- [ ] Correct the source code, never the tests
- [ ] Re-run the affected verification
- [ ] Record what was changed and why
- [ ] **MANDATORY**: Do not retry indefinitely. When further attempts stop producing progress, write the artifact with the outstanding failures and stop

**CRITICAL**: Fix within this stage; do not return to Planning or Generation. Repeating verification indefinitely, or cycling between stages, may never terminate, and nothing will interrupt it.

### Step 6: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/05-build-and-test.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, and the field prefixes exactly as given. Replace only the bracketed text.

```markdown
---
stage: 5
name: build-and-test
---

## Build
- Result: [success | failure]
- Command: [the command run, verbatim]

## Reproduction Script
- Result: [pass | fail]
- Unmet requirements: [none | which requirement is unmet and how it fails]

## Existing Tests vs Baseline
- Command: [the command run, verbatim — the same selection as the baseline]
- Verdict: [unchanged | regression resolved | pre-existing failures only]
- Regressions: [none | test id -> what broke it -> how it was resolved]
- Pre-existing failures: [none | test id -> the reasoning that identifies it as pre-existing]

## Fixes Applied
- [none | what changed and why]

## Outstanding Failures
- [none | what remains, and why it was not resolved]

## Final Change
- Files in the change: [full paths]
- Unintended files in the repository: none
- Test files in the change: none
```

Outstanding Failures is the only place unresolved work is recorded. When Step 5 stopped short, it names what remains and why; it is never left as `none` to make the run look clean.

### Step 7: Confirm the Final Change

- [ ] **MANDATORY**: Confirm no unintended file is part of the change — no temporary script, scratch file, or debug output inside the repository
- [ ] Confirm the files in the change are exactly those Code Generation listed as modified or created
- [ ] Confirm no test file appears in the change

Artifacts are not part of this check. They live under `/tmp/swe-bench-pro/`, outside the repository, and cannot reach the change. The reproduction script can, if it was written inside the repository — that is what this step exists to catch.

## Completion Criteria
- Build succeeds
- Reproduction script demonstrates the issue is resolved, including the edge cases and any stated constraints
- Existing covering tests compared against the baseline, with any regression resolved and any pre-existing failure recorded with its reasoning
- `/tmp/swe-bench-pro/05-build-and-test.md` written in the prescribed skeleton
- Repository contains no unintended file, and no test file was modified
