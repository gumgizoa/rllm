# Code Generation — Part 2: Generation

**Purpose**: Execute the plan to modify source code and write the reproduction script

**Artifact**: `/tmp/swe-bench-pro/04-code-generation-generation.md`

**Note**: "Generate" means **modify the existing file** when one exists, not create a variant alongside it.

## Prerequisites
- Code Generation Planning is complete: the numbered plan and the reproduction script path are established, and recorded in `/tmp/swe-bench-pro/03-code-generation-planning.md`

## Execution Steps

### Step 1: Take the Next Step from the Plan

- [ ] Work through the plan in order
- [ ] Load the target files, change, contract obligations, verification, and requirement tag for the step at hand

### Step 2: Execute the Current Step

- [ ] Use the path recorded in the plan
- [ ] Check whether the target file exists
  - **If it exists**: modify it in place. Never create `module_new.py`, `ClassName_modified.java`, or any similar duplicate
  - **If it does not exist**: create it
- [ ] Modify **application source code**; in test files, **only add** (see below)
- [ ] **Preserve the interfaces and contracts** the plan names as preserved
- [ ] Satisfy the requirement (`Rx`) the step is tagged with
- [ ] Write the reproduction script at the path the plan records, and **do not execute it in this stage**
- [ ] If the plan names an added test, append the new test function to that existing module (or create the new module), and **do not execute it in this stage**

**MANDATORY — never modify or remove an existing test line.** Existing tests are the specification the change must satisfy; editing one removes the independent check that the change is correct and leaves false confidence that the work is verified. Adding a new test function to an existing module is allowed and is the preferred place for the new behavior's test, because it runs under the module's fixtures and beside the tests that already cover the code.

#### When the Plan Proves Wrong

The plan is executed as written. When implementation reveals that the plan cannot be followed, adjust it **within this stage** and record what changed and why in this stage's artifact. Do not return to Planning.

A deviation is the normal way a plan gets corrected, not a failure. When the code, an import, an error message, or a test points to a file the plan does not name, open that file and read the relevant part before deciding; if it also needs the change, add it to the change and record the addition as a local correction. Do not leave a location unchanged only because the plan did not list it.

- **Local correction** — the approach holds and only a detail is wrong, such as a function residing in a different file than the plan states. Note the correction and proceed
- **Structural invalidation** — the approach itself does not work, for example a requirement cannot be satisfied while preserving a contract the plan marked as preserved, or several steps become invalid at once. State which steps are invalidated, why, and what supersedes them

### Step 3: Record Progress

- [ ] Note that the step is complete, and which requirement it satisfied
- [ ] **Verify no duplicate file was created** — no `module_new.py` beside `module.py`
- [ ] Confirm no existing test line was modified or removed (additions to test files are allowed)

### Step 4: Continue or Complete

- [ ] If steps remain, return to Step 1
- [ ] If every step is complete, write the artifact and proceed to Build and Test

### Step 5: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/04-code-generation-generation.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, and the field prefixes exactly as given. Replace only the bracketed text.

```markdown
---
stage: 4
name: code-generation-generation
---

## Changed Files
- Modified: [full path] [requirement tags]
- Modified: [full path] [requirement tags]
- Created: [full path] [requirement tags]

## Reproduction Script
- Path: [full path as written, matching the planned path]
- Executed: no

## Added Test
- Module: [full path of the test module the new test was added to | none]
- Test: [name of the new test function | none]
- Executed: no

## Plan Execution
- Step 1 [R1]: complete
- Step 2 [R2, R4]: complete

## Deviations from Plan
- [none | local correction: what changed and why | structural invalidation: which steps are invalid, why, and what supersedes them]

## Checks
- Duplicate files created: none
- Existing test lines modified or removed: none
- Test files with additions: [full paths | none]
```

## Completion Criteria
- Every plan step executed
- Every requirement (`R1`, `R2`, ...) implemented
- Source code modified and the reproduction script (and the added test, if planned) written, with none of them executed yet
- No duplicate files created
- No existing test line modified or removed
- `/tmp/swe-bench-pro/04-code-generation-generation.md` written in the prescribed skeleton, listing modified and created files and any deviation from the plan
