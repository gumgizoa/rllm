I want you to create a tasks breakdown from the task description for a new feature using the following MULTI-PHASE process and instructions.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Initialize the Spec Folder and Study the Change

The FIRST STEP is to create the spec folder. Determine a kebab-case spec name from the task description, then create the folder:

```bash
# Get today's date in YYYY-MM-DD format
TODAY=$(date +%Y-%m-%d)

# Determine kebab-case spec name from the task description
SPEC_NAME="[kebab-case-name]"

# Store this path for output
SPEC_PATH="/tmp/agent-os/specs/${TODAY}-${SPEC_NAME}"

# Create the spec folder and the folder for its verification report
mkdir -p $SPEC_PATH/verifications

echo "Created spec folder: $SPEC_PATH"
```

Then study the change: read the task description in the task message again and explore the code it is about in the repository, until you know what has to change and where.

# PHASE 2: Create Tasks List

Now that you know what the change has to achieve, please break that down into an actionable tasks list with strategic grouping and ordering, by following these instructions:

# Task List Creation

## Core Responsibilities

1. **Analyze the task description and the code**: Read and analyze the task description and the code it is about to inform the tasks list you will create.
2. **Plan task execution order**: Break the requirements into a list of tasks in an order that takes their dependencies into account.
3. **Group tasks by specialization**: Group tasks that require the same skill or stack specialization together (backend, api, ui design, etc.)
4. **Create Tasks list**: Create the markdown tasks list broken into groups with sub-tasks.

## Workflow

### Step 1: Analyze the Task Description & the Code

Go over the task description and the code you studied in PHASE 1 to understand the requirements for this feature implementation.

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
  - [ ] 1.2 Change the code so that [the behavior to change] holds
  - [ ] 1.3 Ensure the tests of this group pass
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

Whatever you adapt, every tasks.md keeps the example's three sections: `## Overview` with its `Total Tasks:` line, `## Task List`, and `## Execution Order` (the order in which the task groups are implemented).

## Important Constraints

- **Create tasks that are specific and verifiable**
- **Leave the code change out of the tasks list**: a task says which behavior has to hold and which tests show it. No task names the file, function, condition or value to change, in code or in words; the code change is decided in implement-tasks PHASE 2, with the code open.
- **Group related tasks:** For example, group back-end engineering tasks together and front-end UI tasks together.
- **Limit test writing during development**:
  - Each implementation task group should write 2-8 focused tests maximum
  - Tests should cover only critical behaviors, not exhaustive coverage
  - Test verification should run the newly written tests and the existing tests of the changed code, not the entire suite
  - If there is a dedicated test coverage group for filling in gaps in test coverage, this group should add only a maximum of 10 additional tests IF NECESSARY to fill critical gaps
- **Use a focused test-driven approach** where each task group starts with writing 2-8 tests (x.1 sub-task) and ends with running those tests and the existing tests of the changed code (final sub-task)
- **Write these tests as check scripts or as additions to an existing test module**: every test a task group writes (the x.1 sub-task, and the additional tests of a test-review group) is a script under `/tmp/agent-os/specs/[this-spec]/verify/`, run on its own, or a new test function added to the existing repository test module that covers the changed code; never change or remove an existing test line. The test-writing standard applies to these tests.
- **Include acceptance criteria** for each task group

## Next step

Once the tasks list has been created at `/tmp/agent-os/specs/[this-spec]/tasks.md`, open `/agent-os/commands/implement-tasks/implement-tasks.md` and continue with that command.
