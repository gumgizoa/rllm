Now that the change has been studied, we will proceed with implementation of this spec by following this multi-phase process:

PHASE 1: Implement the change
PHASE 2: After the change is made and tested, write the tasks list of the change and tick it
PHASE 3: After the tasks list is written and ticked, produce the final verification report.

Carefully carry out the PHASE sections below in order, finishing one before the next.

Instructions to follow in sequence:

# PHASE 1: Implement the Change

Implement the change the task description asks for by following these instructions. In this run no tasks list exists while you implement: `/tmp/agent-os/specs/[this-spec]/tasks.md` is written in PHASE 2, after the change is made and tested.

## Implementation process:

1. Analyze the task description and the code you studied in create-tasks
2. Analyze patterns in the codebase according to its built-in workflow
3. Write 2-8 focused tests for the behavior to change, before you change the code
4. Implement the change according to requirements and standards

## Guide your implementation using:
- **The existing patterns** that you've found and analyzed in the codebase.
- **User Standards & Preferences** which are defined below.

## Self-verify and test your work by:
- Running the tests you've written (you write them first, before you change the code; they are check scripts under `/tmp/agent-os/specs/[this-spec]/verify/`, or test functions you added to an existing repository test module, run through that module with the test runner) and the existing tests of the code you changed, and ensuring they pass. An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test under Failed Tests in the final verification report, noting that it is an expected failure (it asserts the behavior the task asks to change).
- IF a test fails because of your change, or because a test you wrote is itself wrong, fix the change or that test and run the tests again before you go on to PHASE 2. Make up to five attempts. If it still does not pass, go on, and in PHASE 2 mark the task group's last sub-task with ⚠️ instead of ticking it; do not make a sixth attempt. A test you wrote is wrong only when it checks something the task does not ask for: then correct what it checks. Never make a failing test pass by loosening or removing what it checks.

## Next step

When the change is made and its tests have been run, continue with PHASE 2 (after the standards below).

## User Standards & Preferences Compliance

IMPORTANT: Ensure that the tasks list is ALIGNED and DOES NOT CONFLICT with the user's preferences and standards as detailed in the following files:

**`agent-os/standards/global/coding-style.md`**

## Coding style best practices

- **Consistent Naming Conventions**: Establish and follow naming conventions for variables, functions, classes, and files across the codebase
- **Automated Formatting**: Maintain consistent code style (indenting, line breaks, etc.)
- **Meaningful Names**: Choose descriptive names that reveal intent; avoid abbreviations and single-letter variables except in narrow contexts
- **Small, Focused Functions**: Keep functions small and focused on a single task for better readability and testability
- **Consistent Indentation**: Use consistent indentation (spaces or tabs) and configure your editor/linter to enforce it

**`agent-os/standards/global/commenting.md`**

## Code commenting best practices

- **Self-Documenting Code**: Write code that explains itself through clear structure and naming
- **Minimal, helpful comments**: Add concise, minimal comments to explain large sections of code logic.
- **Don't comment changes or fixes**: Do not leave code comments that speak to recent or temporary changes or fixes. Comments should be evergreen informational texts that are relevant far into the future.

**`agent-os/standards/global/conventions.md`**

## General development conventions

- **Consistent Project Structure**: Organize files and directories in a predictable, logical structure that team members can navigate easily
- **Environment Configuration**: Use environment variables for configuration; never commit secrets or API keys to version control

**`agent-os/standards/global/error-handling.md`**

## Error handling best practices

- **User-Friendly Messages**: Provide clear, actionable error messages to users without exposing technical details or security information
- **Fail Fast and Explicitly**: Validate input and check preconditions early; fail with clear error messages rather than allowing invalid state
- **Specific Exception Types**: Use specific exception/error types rather than generic ones to enable targeted handling
- **Centralized Error Handling**: Handle errors at appropriate boundaries (controllers, API layers) rather than scattering try-catch blocks everywhere
- **Graceful Degradation**: Design systems to degrade gracefully when non-critical services fail rather than breaking entirely
- **Retry Strategies**: Implement exponential backoff for transient failures in external service calls
- **Clean Up Resources**: Always clean up resources (file handles, connections) in finally blocks or equivalent mechanisms

**`agent-os/standards/global/validation.md`**

## Validation best practices

- **Validate on Server Side**: Always validate on the server; never trust client-side validation alone for security or data integrity
- **Client-Side for UX**: Use client-side validation to provide immediate user feedback, but duplicate checks server-side
- **Fail Early**: Validate input as early as possible and reject invalid data before processing
- **Specific Error Messages**: Provide clear, field-specific error messages that help users correct their input
- **Allowlists Over Blocklists**: When possible, define what is allowed rather than trying to block everything that's not
- **Type and Format Validation**: Check data types, formats, ranges, and required fields systematically
- **Sanitize Input**: Sanitize user input to prevent injection attacks (SQL, XSS, command injection)
- **Business Rule Validation**: Validate business rules (e.g., sufficient balance, valid dates) at the appropriate application layer
- **Consistent Validation**: Apply validation consistently across all entry points (web forms, API endpoints, background jobs)

**`agent-os/standards/testing/test-writing.md`**

## Test coverage best practices

- **Test Behavior, Not Implementation**: Focus tests on what the code does, not how it does it, to reduce brittleness
- **Clear Test Names**: Use descriptive names that explain what's being tested and the expected outcome
- **Mock External Dependencies**: Isolate units by mocking databases, APIs, file systems, and other external services
- **Fast Execution**: Keep unit tests fast (milliseconds) so developers run them frequently during development

# PHASE 2: Write the Tasks List

Now that the change is made and tested, please write it down as a tasks list with strategic grouping and ordering, by following these instructions. The instructions are written for a change that is still to be made ("write tests", "change to make"); read them as describing the change you have made: the tasks are the work the change consisted of, and the tests of an x.1 sub-task are the tests you wrote in PHASE 1.

# Task List Creation

## Core Responsibilities

1. **Analyze the task description and the code**: Read and analyze the task description and the code it is about to inform the tasks list you will create.
2. **Plan task execution order**: Break the requirements into a list of tasks in an order that takes their dependencies into account.
3. **Group tasks by specialization**: Group tasks that require the same skill or stack specialization together (backend, api, ui design, etc.)
4. **Create Tasks list**: Create the markdown tasks list broken into groups with sub-tasks.

## Workflow

### Step 1: Analyze the Task Description & the Code

Go over the task description and the change you made in PHASE 1 to understand the requirements for this feature implementation.

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
  - [ ] 1.2 [First change to make] in [path of the file to change]
    - [details]
    - Reuse pattern from: [existing code if applicable]
  - [ ] 1.3 [Next change to make] in [path of the file to change]
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

Whatever you adapt, every tasks.md keeps the example's three sections: `## Overview` with its `Total Tasks:` line, `## Task List`, and `## Execution Order` (the order in which the task groups are implemented).

## Important Constraints

- **Create tasks that are specific and verifiable**
- **Name the file each change is made in**: every sub-task that changes code names, on its task line, the path in the repository of the file it changes. A task added while implementing does the same, and is added before that file is edited.
- **Group related tasks:** For example, group back-end engineering tasks together and front-end UI tasks together.
- **Limit test writing during development**:
  - Each implementation task group should write 2-8 focused tests maximum
  - Tests should cover only critical behaviors, not exhaustive coverage
  - Test verification should run the newly written tests and the existing tests of the changed code, not the entire suite
  - If there is a dedicated test coverage group for filling in gaps in test coverage, this group should add only a maximum of 10 additional tests IF NECESSARY to fill critical gaps
- **Use a focused test-driven approach** where each task group starts with writing 2-8 tests (x.1 sub-task) and ends with running those tests and the existing tests of the changed code (final sub-task)
- **Write these tests as check scripts or as additions to an existing test module**: every test a task group writes (the x.1 sub-task, and the additional tests of a test-review group) is a script under `/tmp/agent-os/specs/[this-spec]/verify/`, run on its own, or a new test function added to the existing repository test module that covers the changed code; never change or remove an existing test line. The test-writing standard applies to these tests.
- **Include acceptance criteria** for each task group

## Tick the tasks list

Once `/tmp/agent-os/specs/[this-spec]/tasks.md` is written, go through it task by task. A task the change covers is ticked (`- [x]`) without changing the code again. A sub-task whose tests could not be made to pass in five attempts is marked with ⚠️ instead of being ticked.

Once every task is ticked or marked with ⚠️, continue with PHASE 3 below.

# PHASE 3: Verify Implementation

Now that we've implemented all tasks in tasks.md, we must run final verifications and produce a verification report using the following MULTI-PHASE workflow:

## Workflow

### Step 1: Ensure tasks.md has been updated

Check `/tmp/agent-os/specs/[this-spec]/tasks.md` and ensure that all tasks and their sub-tasks are marked as completed with `- [x]`.

If a task is still marked incomplete, then verify that it has in fact been completed by checking the following:
- Run a brief spot check in the code to find evidence that this task's details have been implemented

IF you have concluded that this task has been completed, then mark it's checkbox and its' sub-tasks checkboxes as completed with `- [x]`.

IF you have concluded that this task has NOT been completed, then mark this checkbox with ⚠️ and note it's incompleteness in your verification report.

### Step 2: Run the tests of the changed code

Run the tests of the changed code once more: the test modules that cover the files you changed, and the tests you wrote. Run the entire tests suite as well only if it finishes within a few minutes.  Verify how many tests are passing and how many have failed or produced errors.

Include these counts and the list of failed tests in your final verification report.

IF a test fails, find out whether your change causes it. A test you wrote for this change: it does. An existing test: run it once without your change, in one command (`git stash -q && <the test command>; git stash pop -q`); if it fails there as well, your change does not cause it.

- Your change causes the failure, and the test is not one that asserts the behavior the task asks to change: go back to PHASE 1 once, fix the change, then carry out PHASE 3 again from Step 1. Go back once only; a failure that is still there afterwards is noted in the report.
- Any other failure: DO NOT attempt to fix it.  Just note it in your final verification report.

### Step 3: Create final verification report

Create your final verification report in `/tmp/agent-os/specs/[this-spec]/verifications/final-verification.md`.

The content of this report should follow this structure:

```markdown
# Verification Report: [Spec Title]

**Spec:** `[spec-name]`
**Date:** [Current Date]
**Verifier:** implementation-verifier
**Status:** ✅ Passed | ⚠️ Passed with Issues | ❌ Failed

---

## Executive Summary

[Brief 2-3 sentence overview of the verification results and overall implementation quality]

---

## 1. Tasks Verification

**Status:** ✅ All Complete | ⚠️ Issues Found

### Completed Tasks
- [x] Task Group 1: [Title]
  - [x] Subtask 1.1
  - [x] Subtask 1.2
- [x] Task Group 2: [Title]
  - [x] Subtask 2.1

### Incomplete or Issues
[List any tasks that were found incomplete or have issues, or note "None" if all complete]

---

## 2. Test Suite Results

**Status:** ✅ All Passing | ⚠️ Some Failures | ❌ Critical Failures

### Test Summary
- **Total Tests:** [count]
- **Passing:** [count]
- **Failing:** [count]
- **Errors:** [count]

### Failed Tests
[List any failing tests with their descriptions, or note "None - all tests passing"]

### Notes
[Any additional context about test results, known issues, or regressions]
```

The **Status** at the top of the report follows from the two sections below it:
- `✅ Passed`: Tasks Verification is `✅ All Complete` and Test Suite Results is `✅ All Passing`.
- `⚠️ Passed with Issues`: a task is marked ⚠️ (Tasks Verification `⚠️ Issues Found`), or a test fails that is not one you wrote for this change (Test Suite Results `⚠️ Some Failures`).
- `❌ Failed`: a test you wrote for this change fails (Test Suite Results `❌ Critical Failures`).
