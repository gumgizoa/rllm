# Code Generation — Part 1: Planning

**Purpose**: Produce an explicit, numbered plan that resolves every requirement, and that can be executed step by step without further interpretation

**Artifact**: `/tmp/swe-bench-pro/03-code-generation-planning.md`

## Prerequisites
- Reverse Engineering is complete: Affected Scope, Build & Test Commands, Existing Tests, and Baseline are established, and recorded in `/tmp/swe-bench-pro/01-reverse-engineering.md`
- Requirements Analysis is complete: the numbered requirements `R1`, `R2`, ... are established, and recorded in `/tmp/swe-bench-pro/02-requirements-analysis.md`

## Execution Steps

### Step 1: Create the Numbered Plan

**MANDATORY**: Create one or more explicit steps for each requirement. Number the steps sequentially. For every step, record:

- [ ] **Target file(s)** — full path, and whether the file is modified in place or newly created.
- [ ] **Change** — what is added, altered, or removed
- [ ] **Interfaces and contracts** — the existing public signatures and return shapes that must be **preserved**, and any new interface this step introduces for later steps to use. If the task description specifies names, signatures, or file paths, use them exactly as given rather than choosing your own
- [ ] **Verification** — what the reproduction script must exercise to demonstrate this step is correct
- [ ] **Requirement tag** — which requirement (`R1`, `R2`, ...) the step satisfies

**CRITICAL — contract preservation**: Naming the contract each step must preserve is what makes it checkable during generation. A step that leaves it unstated can silently change a signature or return shape, and the work then fails even though the reported issue is resolved.

### Step 2: Plan the Reproduction Script

- [ ] Plan a script that reproduces the issue before the fix and demonstrates correct behavior after it
- [ ] Include the conditions from the Edge Cases & Error Handling requirements
- [ ] Record the path where the script will be written

### Step 3: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/03-code-generation-planning.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, the `### Step n [satisfies Rx]` step headings, and the field prefixes exactly as given. Replace only the bracketed text.

```markdown
---
stage: 3
name: code-generation-planning
---

## Plan

### Step 1 [satisfies R1]
- Target: [full path] (modify in place | create)
- Change: [what changes]
- Contract: [signatures/return shapes to preserve; new interfaces introduced]
- Verification: [what the reproduction script exercises]

### Step 2 [satisfies R2, R4]
- Target: [full path] (modify in place | create)
- Change: [what changes]
- Contract: [signatures/return shapes to preserve; new interfaces introduced]
- Verification: [what the reproduction script exercises]

## Reproduction Script
- Path: [full path where Stage 4 will write it]
- Exercises: [the requirements it covers, by identifier]

## Requirement Coverage
- R1: Step 1
- R2: Step 2
- R4: Step 2
```

The Requirement Coverage section lists every requirement from Requirements Analysis against the steps that satisfy it. It is the check that no requirement was dropped between the two artifacts, and it must account for every identifier that artifact defines.

## Critical Rules

### Plan Authority
- The plan is the **single source of truth** for generation
- The plan must be executable step by step without further interpretation. Generation executes only what is written here, so any gap in the plan is a gap in the implementation

### Code Location Rules
- Follow the existing repository structure
- Record full paths from the repository root
- Application source code only; never test files. They are the specification the change must satisfy

### File Modification Rules
- If the target file exists, plan to modify it **in place**
- Never plan a duplicate such as `module_new.py` or `ClassName_modified.java`

### Requirement Traceability
- Every step carries the requirement tag it satisfies
- Every requirement is satisfied by at least one step

## Completion Criteria
- A numbered plan exists in which every step names target files, change, contract obligations, verification, and requirement tag
- Every requirement from Requirements Analysis appears in the Requirement Coverage section, against at least one step
- The steps are ordered so that each is executable when reached
- The reproduction script is planned, with its path recorded
- No step targets a test file
- `/tmp/swe-bench-pro/03-code-generation-planning.md` written in the prescribed skeleton
