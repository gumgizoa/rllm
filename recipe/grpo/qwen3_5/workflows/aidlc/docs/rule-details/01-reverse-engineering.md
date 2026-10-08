# Reverse Engineering

**Purpose**: Understand the parts of the existing codebase that the reported issue touches, and record a regression baseline before any code is modified

**Artifact**: `/tmp/swe-bench-pro/01-reverse-engineering.md`

## Prerequisites
- The task description (PR/issue text) is available
- The repository is available and can already be built and tested

## Execution Steps

### Step 1: Identify Affected Scope

- [ ] Locate the source files the issue refers to, using symbol names, keywords, error strings, or stack traces from the task description. If the task description names files or symbols directly, start from those
- [ ] Extend to files directly connected to those files (direct callers and callees) where the description implies it
- [ ] Record the module or package that owns those files, and its boundary within the repository
- [ ] Note the language and framework in use — this follows from the files identified; do not survey the repository to establish it
- [ ] Record every path in full, from the repository root, so that it is unambiguous in later stages

**Do NOT** enumerate packages unrelated to the issue, or survey the repository beyond the files identified above.

### Step 2: Identify Build and Test Commands

- [ ] Determine how the affected module is built or type-checked, if the language requires it
- [ ] Determine how its tests are invoked
- [ ] Express the test command so that it can target **the tests covering the affected scope**, not the whole suite
- [ ] Prefer output-reducing flags (for example `-q`, `--tb=short`) so that results remain readable

**Do NOT** plan dependency installation or environment setup — the environment can already build and test the project.

### Step 3: Identify Existing Tests and Record Baseline

- [ ] Locate the existing tests that cover the affected scope
- [ ] Read them to understand the contract the affected code must honor — expected signatures, return shapes, raised errors
- [ ] **MANDATORY**: Execute those tests once, **before any source file is modified**
- [ ] Record which of them pass and which already fail

**CRITICAL**: This baseline is the only means of later distinguishing a regression you introduced from a failure that already existed. A test that was already failing is outside the scope of this task; pursuing it spends effort on unrelated code and risks introducing a real regression. Once source files have changed, this distinction cannot be recovered.

**Note**: Existing tests are read and executed here. They are **never modified**

### Step 4: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/01-reverse-engineering.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, and the field prefixes exactly as given. Replace only the bracketed text.

```markdown
---
stage: 1
name: reverse-engineering
---

## Affected Scope
- Files: [full paths from the repository root, one per line]
- Owning module: [module or package, and its boundary in the repository]
- Language/framework: [as it follows from the files above]

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
- Affected scope identified, with full paths and owning module
- Build/type-check command and a targeted test command known
- Existing covering tests located and read
- Baseline pass/fail state recorded **before** any modification, with each test named individually
- `/tmp/swe-bench-pro/01-reverse-engineering.md` written in the prescribed skeleton
