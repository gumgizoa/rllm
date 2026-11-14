I want you to create a tasks breakdown from a given spec and requirements for a new feature using the following MULTI-PHASE process and instructions.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Get Spec Requirements

The FIRST STEP is to make sure you have ONE OR BOTH of these files to inform your tasks breakdown:
- `/tmp/agent-os/specs/[this-spec]/spec.md`
- `/tmp/agent-os/specs/[this-spec]/planning/requirements.md`

IF you don't have ONE OR BOTH of those files in your current conversation context, then find the spec folder under `/tmp/agent-os/specs/` (this run creates one) and read the files there. If they do not exist yet, carry out the shape-spec document (`/agent-os/commands/shape-spec/shape-spec.md`) and the write-spec document (`/agent-os/commands/write-spec/write-spec.md`) first.

# PHASE 2: Create Tasks List

Now that you have the spec.md AND/OR requirements.md, please break those down into an actionable tasks list with strategic grouping and ordering, by following these instructions:

# Task List Creation

## Core Responsibilities

1. **Analyze spec and requirements**: Read and analyze the spec.md and/or requirements.md to inform the tasks list you will create.
2. **Plan task execution order**: Break the requirements into a list of tasks in an order that takes their dependencies into account.
3. **Group tasks by specialization**: Group tasks that require the same skill or stack specialization together (backend, api, ui design, etc.)
4. **Create Tasks list**: Create the markdown tasks list broken into groups with sub-tasks.

## Workflow

### Step 1: Analyze Spec & Requirements

Read each of these files (whichever are available) and analyze them to understand the requirements for this feature implementation:
- `/tmp/agent-os/specs/[this-spec]/spec.md`
- `/tmp/agent-os/specs/[this-spec]/planning/requirements.md`

Use your learnings to inform the tasks list and groupings you will create in the next step.

### Step 2: Create Tasks Breakdown

Generate `/tmp/agent-os/specs/[current-spec]/tasks.md`.

**Important**: The exact tasks, task groups, and organization will vary based on the feature's specific requirements. The following is an example format - adapt the content of the tasks list to match what THIS feature actually needs.

```markdown
# Task Breakdown: [Feature Name]

## Overview
Total Tasks: [count]

## Task List

### [Area of the change]

#### Task Group 1: [Name of the area]
**Dependencies:** None

- [ ] 1.0 Complete [the change in this area]
  - [ ] 1.1 Write 2-8 focused tests for [the behavior to change]
    - Limit to 2-8 highly focused tests maximum
    - Test only critical behaviors
    - Skip exhaustive coverage of all methods and edge cases
  - [ ] 1.2 [First change to make]
    - [details]
    - Reuse pattern from: [existing code if applicable]
  - [ ] 1.3 [Next change to make]
    - [details]
  - [ ] 1.4 Ensure the tests of this group pass
    - Run the 2-8 tests written in 1.1 and the existing tests of the changed code
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 and the existing tests of the changed code pass
- [what works once this group is done]

### Testing

#### Task Group 2: Test Review & Gap Analysis
**Dependencies:** Task Group 1

- [ ] 2.0 Review existing tests and fill critical gaps only
  - [ ] 2.1 Review tests from Task Group 1
    - Review the 2-8 tests written in Task 1.1
  - [ ] 2.2 Analyze test coverage gaps for THIS feature only
    - Identify critical user workflows that lack test coverage
    - Focus ONLY on gaps related to this spec's feature requirements
    - Do NOT assess entire application test coverage
    - Prioritize end-to-end workflows over unit test gaps
  - [ ] 2.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new tests to fill identified critical gaps
    - Focus on integration points and end-to-end workflows
    - Do NOT write comprehensive coverage for all scenarios
    - Skip edge cases and performance tests unless business-critical
  - [ ] 2.4 Run feature-specific tests only
    - Run ONLY tests related to this spec's feature (tests from 1.1 and 2.3, and the existing tests of the changed code)
    - Do NOT run the entire application test suite
    - Verify critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass
- Critical user workflows for this feature are covered
- No more than 10 additional tests added when filling in testing gaps
- Testing focused exclusively on this spec's feature requirements

## Execution Order

Recommended implementation sequence:
1. [Area of the change] (Task Group 1)
2. Test Review & Gap Analysis (Task Group 2)
```

**Note**: Adapt this structure based on the actual feature requirements. Some features may need:
- Different task groups (e.g., email notifications, payment processing, data migration)
- Different execution order based on dependencies
- More or fewer sub-tasks per group

## Important Constraints

- **Create tasks that are specific and verifiable**
- **Group related tasks:** For example, group back-end engineering tasks together and front-end UI tasks together.
- **Limit test writing during development**:
  - Each implementation task group should write 2-8 focused tests maximum
  - Tests should cover only critical behaviors, not exhaustive coverage
  - Test verification should run the newly written tests and the existing tests of the changed code, not the entire suite
  - If there is a dedicated test coverage group for filling in gaps in test coverage, this group should add only a maximum of 10 additional tests IF NECESSARY to fill critical gaps
- **Use a focused test-driven approach** where each task group starts with writing 2-8 tests (x.1 sub-task) and ends with running those tests and the existing tests of the changed code (final sub-task)
- **Write these tests as check scripts or as additions to an existing test module**: every test a task group writes (the x.1 sub-task, and the additional tests of a test-review group) is a script under `/tmp/agent-os/specs/[this-spec]/checks/`, run on its own, or a new test function added to the existing repository test module that covers the changed code; never change or remove an existing test line. The test-writing standard applies to these tests.
- **Include acceptance criteria** for each task group

## Next step

Once the tasks list has been created at `/tmp/agent-os/specs/[this-spec]/tasks.md`, open `/agent-os/commands/implement-tasks/implement-tasks.md` and continue with that command.
