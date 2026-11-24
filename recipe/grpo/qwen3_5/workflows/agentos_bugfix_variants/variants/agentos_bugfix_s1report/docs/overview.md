# Agent OS: A Verified Change

This run uses one part of Agent OS (v2.1.1): its final verification report. You solve the task the way
you normally would: explore the repository, see the reported behavior for yourself, change the code and
test the change. When the change is made and tested, you write the report described below and call
`finish`. No other document is written in this run: no requirements, no specification, no task list.

This file is the only workflow document. `/agent-os/` is a directory directly under the filesystem root
`/`. It is not part of the repository you work in, and nothing of it exists inside the repository.

## The task

The description of the change is the task description in the task message: the report of what is wrong
or what is wanted. The task message is your only input from outside; everything else you learn from the
repository.

## The report folder

When the change is made and tested, create the folder
`/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/verifications/`: today's date and a short kebab-case name you
choose for the change. Below, `/tmp/agent-os/specs/<YYYY-MM-DD>-<name>` is written `S`.

```
S/
└── verifications/
    └── final-verification.md  the report
```

The report does not go into the repository.

## The report

Before you write the report, run the tests of the changed code once more: the test modules that cover
the files you changed, and the tests you wrote. Verify how many tests are passing and how many have
failed or produced errors.

Then create `S/verifications/final-verification.md` with this structure:

```markdown
# Verification Report: [Title of the change]

**Date:** [Current Date]
**Status:** ✅ Passed | ⚠️ Passed with Issues | ❌ Failed

---

## Executive Summary

[Brief 2-3 sentence overview of the change and of the verification results]

---

## Test Suite Results

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

## Nobody is on the other side

No person reads your messages, answers a question or reviews a result, and a reply that calls no tool
ends the session at once, with the work unfinished. Never wait for a reply, and send no plain-text
message at all before `finish`.

## Finishing

As soon as `S/verifications/final-verification.md` is written, call `finish`.
