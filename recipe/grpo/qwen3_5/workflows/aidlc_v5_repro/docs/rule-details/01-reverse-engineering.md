# Reverse Engineering

**Purpose**: Understand the parts of the existing codebase that the reported issue touches, observe the reported behavior on the unmodified code, and record a regression baseline before any code is modified

**Artifact**: `/tmp/swe-bench-pro/01-reverse-engineering.md`

## Prerequisites
- The task description (PR/issue text) is available
- The repository is available and can already be built and tested

## Execution Steps

### Step 1: Identify Affected Scope

- [ ] Locate the source files the issue refers to, using symbol names, keywords, error strings, or stack traces from the task description. If the task description names files or symbols directly, start from those
- [ ] Search the whole repository for the symbols, function and class names, and error strings the task description names (for example with `grep -rn`), and list every file that defines or references them. The issue may be fixed in more than one of these files
- [ ] Extend to files directly connected to those files (direct callers and callees) where the description implies it
- [ ] Decide which of the files found are in scope. For each referencing file left out, record why it does not need to change
- [ ] Record the module or package that owns those files, and its boundary within the repository
- [ ] Note the language and framework in use — this follows from the files identified; do not survey the repository to establish it
- [ ] Record every path in full, from the repository root, so that it is unambiguous in later stages

**Do NOT** enumerate or document packages the search did not reach; the scope is the files the issue touches, not the repository.

### Step 2: Observe the Reported Behavior

- [ ] Run what the task description reports against the unmodified code: the snippet, command, or input it gives, with a short command such as `python -c '...'`
- [ ] If the description gives nothing runnable, write the shortest call that should show the reported behavior and run that
- [ ] Record the command and what it printed — the last lines of output, or the error and where it was raised
- [ ] If it cannot be run in this environment, record why

**CRITICAL**: The later stages decide what to change from this observation as well as from the task description. The task description says what the code must do; this run shows what it does now, and a change planned from the description alone can target behavior the code does not have.

**Note**: This is a one-off command, not the reproduction script. The reproduction script is still planned in Stage 3, written in Stage 4, and executed in Stage 5. No source file is modified here

### Step 3: Identify Build and Test Commands

- [ ] Determine how the affected module is built or type-checked, if the language requires it
- [ ] Determine how its tests are invoked
- [ ] Express the test command so that it can target **the tests covering the affected scope**, not the whole suite
- [ ] Prefer output-reducing flags (for example `-q`, `--tb=short`) so that results remain readable

**Do NOT** plan dependency installation or environment setup — the environment can already build and test the project.

### Step 4: Identify Existing Tests and Record Baseline

- [ ] Locate the existing tests that cover the affected scope
- [ ] Read them to understand the contract the affected code must honor — expected signatures, return shapes, raised errors
- [ ] **MANDATORY**: Execute those tests once, **before any source file is modified**
- [ ] Record which of them pass and which already fail

**CRITICAL**: This baseline is the only means of later distinguishing a regression you introduced from a failure that already existed. A test that was already failing is outside the scope of this task; pursuing it spends effort on unrelated code and risks introducing a real regression. Once source files have changed, this distinction cannot be recovered.

**Note**: Existing tests are read and executed here. Their existing lines are **never modified**; a later stage may add new test functions to these modules, never change what is already there

### Step 5: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/01-reverse-engineering.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, and the field prefixes exactly as given. Replace only the bracketed text.

```markdown
---
stage: 1
name: reverse-engineering
---

## Affected Scope
- Files: [full paths from the repository root, one per line]
- Referencing files left out of scope: [full path — why it does not need to change, one per line | none]
- Owning module: [module or package, and its boundary in the repository]
- Language/framework: [as it follows from the files above]

## Observed Behavior
- Command: [verbatim command run against the unmodified code | not runnable — why]
- Output: [the last lines it printed, or the error and where it was raised]

## Build & Test Commands
- Build: [verbatim build or type-check command | not applicable]
- Test: [verbatim targeted test command for the covering tests]

## Existing Tests
- Path: [full path] — Contract: [signatures, return shapes, raised errors it enforces]

## Baseline
Recorded before any source file was modified.
- Passing: [test id, one per line | none]
- Failing: [test id, one per line | none]
```

## Completion Criteria
- Affected scope identified, with full paths and owning module, after a repository-wide search for the names the task uses; referencing files left out are listed with the reason
- Reported behavior run against the unmodified code, with the command and its output recorded — or the reason it cannot be run here
- Build/type-check command and a targeted test command known
- Existing covering tests located and read
- Baseline pass/fail state recorded **before** any modification, with each test named individually
- `/tmp/swe-bench-pro/01-reverse-engineering.md` written in the prescribed skeleton
