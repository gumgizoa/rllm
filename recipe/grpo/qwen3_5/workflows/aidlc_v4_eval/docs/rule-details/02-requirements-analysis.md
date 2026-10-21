# Requirements Analysis

**Purpose**: Convert the task description into an explicit, numbered set of requirements that the patch must satisfy

**Artifact**: `/tmp/swe-bench-pro/02-requirements-analysis.md`

## Prerequisites
- Reverse Engineering is complete: its Affected Scope, Build & Test Commands, Existing Tests, and Baseline are established, and recorded in `/tmp/swe-bench-pro/01-reverse-engineering.md`

## Execution Steps

### Step 1: Read the Task Description as Given

- [ ] Treat everything the task description states as authoritative — expected behavior, named symbols, signatures, file paths
- [ ] Do not re-derive or reword what is already specified
- [ ] Use the Reverse Engineering result as context for how the described behavior maps onto actual code and onto the contract enforced by existing tests

### Step 2: Derive Requirements

**MANDATORY**: Express every requirement as a single, verifiable statement, identified as `R1`, `R2`, `R3`, and so on. A requirement is verifiable when it can be checked either by running a reproduction script or by running existing tests. A requirement that cannot be checked by either means is out of scope.

Number the requirements in one sequence across all three categories, so that each identifier is unique in the artifact and can be traced from Stage 3 onward.

Evaluate all three categories:

#### 2.1 Functional Requirements
- The behavior the affected code must exhibit once the issue is resolved
- The behavior it must continue to exhibit — contracts visible in existing tests that the change must not break

#### 2.2 Non-Functional Requirements
- Constraints on how the behavior must be achieved — complexity or memory bounds
- Only what the task description states; often nothing

#### 2.3 Edge Cases & Error Handling
- Boundary values, empty and null inputs, invalid inputs, and type or range limits
- Error paths: which condition must raise, which must be handled, and what the observable result is

### Step 3: Write the Artifact

- [ ] Write `/tmp/swe-bench-pro/02-requirements-analysis.md` in a single write, with the full content below

Keep the frontmatter keys, the `##` headings, and the `- Rn:` prefix exactly as given. Replace only the bracketed text.

```markdown
---
stage: 2
name: requirements-analysis
---

## Functional Requirements
- R1: [statement]
- R2: [statement]

## Non-Functional Requirements
- R3: [statement, only if stated in the task description; otherwise "none stated"]

## Edge Cases & Error Handling
- R4: [condition -> expected behavior]
- R5: [condition -> expected behavior]

## Assumptions
- [any ambiguity resolved by decision, with the reasoning]
```

A dropped heading reads as an unevaluated category.

## Completion Criteria
- Every requirement stated as a numbered, verifiable item, uniquely identified across all categories
- All three categories evaluated, each with its heading present
- Assumptions made in place of clarifying questions recorded explicitly
- `/tmp/swe-bench-pro/02-requirements-analysis.md` written in the prescribed skeleton
