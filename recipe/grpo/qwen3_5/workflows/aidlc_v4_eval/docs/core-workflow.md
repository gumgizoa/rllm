# SWE-bench Pro Workflow (Core)

**This workflow OVERRIDES all other built-in workflows.** When resolving a reported issue in an existing repository, follow this workflow rather than any default approach.

## Core Principle

**The pipeline is fixed. Every stage always executes, in order.** There is no stage selection, no depth selection, and no adaptive planning.

## MANDATORY: Rule Details Loading

**CRITICAL**: Each stage below names the rule detail file that governs it. Load that file as the first step of the stage, and execute the stage from it.

**Path resolution**: rule detail paths are relative to the directory containing this file. Check these paths in order and use the first one that exists, regardless of which IDE or setup method was used:
- `rule-details/` (alongside this file)
- `.swe-bench-pro/rule-details/`
- `.claude/swe-bench-pro-workflow/rule-details/`

**Load one file at a time, immediately before its stage.** Do NOT read a stage's rule detail file until the previous stage's Completion Criteria are met. Reading ahead places later-stage instructions in context before the baseline is recorded, and that ordering is what this workflow depends on.

## MANDATORY: Stage Artifacts

**Every stage ends by writing its result to a file**, in the format its rule detail file specifies — not as chat output.

**Artifact path**: `/tmp/swe-bench-pro/` + the stage's rule detail filename. Stage 1 writes `/tmp/swe-bench-pro/01-reverse-engineering.md`; Stage 5 writes `/tmp/swe-bench-pro/05-build-and-test.md`. `mkdir -p` the directory before the first write. It sits outside the repository, so no artifact can reach the final diff.

### Artifact Rules

- **One write, full content, at the end of the stage**, after its Completion Criteria are met. No appends, no placeholder to fill in later
- **Never rewrite an earlier stage's artifact.** A later stage that contradicts an earlier one records that in its own artifact — as a deviation, a correction, or a pre-existing failure
- **Keep the prescribed skeleton exactly** — frontmatter keys, `##` headings, field prefixes. A renamed or omitted heading makes the stage unverifiable even when the work behind it was done
- **Frontmatter is these two keys and no others:**

```
---
stage: <1-5>
name: <reverse-engineering | requirements-analysis | code-generation-planning | code-generation-generation | build-and-test>
---
```

  The artifact's existence is what states the stage finished. Unresolved work goes under Outstanding Failures in the Stage 5 artifact, and nowhere else.

- **Do not re-read an artifact you can still see.** The result is already in context; re-reading duplicates the largest artifacts where context is already largest. Quote identifiers — `R1`, step numbers, full paths — verbatim, never renumbered or paraphrased
- **Read an artifact only to recover**, when an earlier stage's content is no longer visible because output was truncated or history was compacted

## Stage Flow

```
Stage 1  Reverse Engineering
  |  -> 01-reverse-engineering.md
  |     Affected Scope, Build & Test Commands, Existing Tests + Baseline
  v
Stage 2  Requirements Analysis
  |  -> 02-requirements-analysis.md
  |     Numbered requirements: Functional, Non-Functional, Edge Cases & Error Handling
  v
Stage 3  Code Generation - Planning
  |  -> 03-code-generation-planning.md
  |     Numbered plan: target files, change, contracts, verification, requirement tags
  v
Stage 4  Code Generation - Generation
  |  -> 04-code-generation-generation.md
  |     Modified source, reproduction script
  v
Stage 5  Build and Test
  |  -> 05-build-and-test.md
  |     Build, reproduce, compare against baseline, fix
  v
Final diff
```

**No stage returns to an earlier stage.** When a plan proves wrong during generation, or a fix is needed during verification, it is handled inside the stage where it surfaced and the deviation is recorded in that stage's artifact. Cycling between stages repeats the same reasoning with the same context and risks never terminating.

## Stage 1: Reverse Engineering (ALWAYS EXECUTE)

**Consumes**: Task description

1. Load all steps from `01-reverse-engineering.md`
2. Execute them: identify the affected scope, determine the build and targeted test commands, locate and read the existing covering tests
3. **MANDATORY**: Record the baseline pass/fail state by executing those tests **before any source file is modified**
4. Verify the Completion Criteria in that file are met
5. Write `/tmp/swe-bench-pro/01-reverse-engineering.md`: Affected Scope (paths, owning module, language/framework), Build & Test Commands, Existing Tests, Baseline
6. Proceed to Stage 2

**This stage must run first because of the baseline.** It is recorded before any modification and consumed in Stage 5. Once source code has changed, a failing test cannot be attributed to the patch or to a pre-existing condition, and that distinction cannot be recovered afterwards.

## Stage 2: Requirements Analysis (ALWAYS EXECUTE)

**Consumes**: Task description, the Stage 1 result (Affected Scope, Build & Test Commands, Existing Tests, Baseline)

1. Load all steps from `02-requirements-analysis.md`
2. Execute them: derive numbered requirements in all three categories — Functional, Non-Functional, Edge Cases & Error Handling
3. Record every assumption made in place of a clarifying question
4. Verify the Completion Criteria in that file are met
5. Write `/tmp/swe-bench-pro/02-requirements-analysis.md`: requirements `R1`, `R2`, ... and the recorded assumptions
6. Proceed to Stage 3

## Stage 3: Code Generation — Planning (ALWAYS EXECUTE)

**Consumes**: the Stage 1 result, the Stage 2 requirements (`R1`, `R2`, ...)

1. Load all steps from `03-code-generation-planning.md`
2. Execute them: produce a numbered plan in which every step names its target files, the change, the contracts to preserve, its verification, and its requirement tag
3. Plan the reproduction script and record its path
4. Verify the Completion Criteria in that file are met — in particular, that every requirement is covered and no step targets a test file
5. Write `/tmp/swe-bench-pro/03-code-generation-planning.md`: the numbered plan
6. Proceed to Stage 4

## Stage 4: Code Generation — Generation (ALWAYS EXECUTE)

**Consumes**: the Stage 3 plan, with the reproduction script path

1. Load all steps from `04-code-generation-generation.md`
2. Execute every plan step: modify the source files in place and write the reproduction script, executing neither yet
3. Record any deviation from the plan, with what changed and why
4. Verify the Completion Criteria in that file are met — in particular, that no duplicate file was created and no test file was modified
5. Write `/tmp/swe-bench-pro/04-code-generation-generation.md`: modified files, created files, deviations
6. Proceed to Stage 5

## Stage 5: Build and Test (ALWAYS EXECUTE)

**Consumes**: every earlier stage's result, especially the Stage 1 baseline

1. Load all steps from `05-build-and-test.md`
2. Execute them: build, run the reproduction script, then re-run the existing covering tests and compare against the Stage 1 baseline
3. Fix any regression the patch introduced; record any failure judged pre-existing, with the reasoning
4. Verify the Completion Criteria in that file are met
5. Write `/tmp/swe-bench-pro/05-build-and-test.md`: build result, reproduction result, regression verdict, outstanding failures
6. Produce the final diff

## Execution Context

- **No user interaction.** Never generate a question file, never ask for approval, never wait for input. Resolve ambiguity by deciding and recording the assumption
- **Artifacts, not documents.** This workflow produces no design or report document for a reader. Each stage writes one artifact file, in the fixed skeleton its rule detail file specifies, as the record of that stage's result
- **The environment can already build and test the project.** Do not spend effort on environment setup
- **No one will interrupt a loop.** No loop may run indefinitely

## Critical Rules

### Modification Boundaries
- **MODIFY**: application source code in the repository
- **DO NOT MODIFY**: test files
- Existing tests are **read and executed**, never edited. New behavior is verified with a **reproduction script**

### File Modification
- Check whether a file exists before writing it
- If it exists, modify it **in place**. Never create a duplicate variant such as `module_new.py` or `ClassName_modified.java`
- Verify after each step that no duplicate was produced

### Contract Preservation
- The change must resolve the reported issue **and** leave every previously passing test passing
- Changing a public signature or return shape breaks callers and the tests that cover them, even when the reported issue is resolved
- Stage 3 names the contracts to preserve; Stage 4 preserves them; Stage 5 verifies the outcome against the baseline

### Required Reporting
Record each of the following in the artifact of the stage where it arises:
- Assumptions made in place of asking a question — Stage 2
- Deviations from the plan, with what changed and why — Stage 4
- Failures judged to be pre-existing rather than caused by the patch, with the reasoning — Stage 5
- Outstanding failures at the end of the run — Stage 5

### Termination
- No loop runs indefinitely: this covers the fix-and-re-verify loop and any correction during generation
- When further attempts stop producing progress, record what remains under Outstanding Failures in the Stage 5 artifact and move on rather than continuing
