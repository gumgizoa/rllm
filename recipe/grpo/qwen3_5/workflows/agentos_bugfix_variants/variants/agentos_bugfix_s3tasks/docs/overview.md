# Agent OS: From Task to Verified Change

This run follows part of Agent OS (v2.1.1): the change is broken into a task list, and only then
implemented and verified. With Agent OS a developer attaches one command document per chat turn and
reads the result before attaching the next. Here you carry out the two command documents yourself, one
after the other, in this single session. No requirements document and no specification are written in
this run: the task description and the repository take their place.

The workflow's documents are in `/agent-os/`, a directory directly under the filesystem root `/`. It is
not part of the repository you work in, and nothing of it exists inside the repository.

## The two commands

Open each command document when you reach it, and work from that document rather than from memory:

1. **create-tasks**: `/agent-os/commands/create-tasks/create-tasks.md`
   PHASE 1 creates the spec folder and studies the change. PHASE 2 breaks the change into task groups
   of checkbox tasks.
2. **implement-tasks**: `/agent-os/commands/implement-tasks/implement-tasks.md`
   PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 3
   verifies the result and writes the final verification report.

Each command runs once, in this order; create-tasks ends by naming implement-tasks, and implement-tasks
ends with its report. There are no repeat rounds, with one exception inside implement-tasks: PHASE 3
sends you back to PHASE 2 once when a test fails because of your change.

The coding standards apply where code is written: the implement-tasks document contains them, written
out under "User Standards & Preferences Compliance". The bold `agent-os/standards/...` lines there only
name each standard; there are no separate standards files to open.

## What "the feature" is

The command documents speak of "a new feature" and "the spec". In this run the description is the task
description in the task message: the report of what is wrong or what is wanted. The feature is the
change that description asks for. The task message is your only input from outside; everything else you
learn from the repository.

## The spec folder

create-tasks creates the spec folder once, as `/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`: today's date and
a short kebab-case name you choose for the change. The documents call it `[this-spec]` or
`[current-spec]`; each of these means that one folder, and implement-tasks works in it too. Below it is
written `S`.

```
S/
├── tasks.md                   create-tasks; implement-tasks ticks its checkboxes and may add tasks
├── verify/                    the task groups' tests that are written as scripts; any scratch file
└── verifications/
    └── final-verification.md  implement-tasks PHASE 3
```

No command creates `S/verify/`; make it the first time you need it. Write each file in the structure its
document gives. implement-tasks ticks the checkboxes of `tasks.md`, and adds a task when the change
needs work no task covers.

## Nobody is on the other side

No person reads your messages, answers a question, reviews a result or starts the next command, and a
reply that calls no tool ends the session at once, with the work unfinished. So:

- Never wait for a reply. What the task description leaves open you decide yourself from the repository.
- When create-tasks is done, open the implement-tasks document right away instead of summing up. Send no
  plain-text message at all before `finish`.
- Progress is kept in the files. The checkboxes in `S/tasks.md` are the record of what has been
  implemented; the TaskTracker tool may serve as a private scratch list, but it does not replace ticking
  `tasks.md`.

## The repository

- Only implement-tasks PHASE 2 changes the repository. create-tasks reads the repository and may run
  commands in it, but changes nothing. implement-tasks PHASE 3 runs tests and writes its report and
  changes no code itself; when a test fails because of your change it sends you back to PHASE 2 once,
  and that is the only code change after PHASE 3 has begun.
- The tests the task groups call for are scripts in `S/verify/`, or new test functions added to the
  existing repository test module that covers the changed code. No existing test line in the repository
  is changed or removed.
- Nothing that belongs to the workflow goes into the repository: no spec files, notes, summaries or temporary
  scripts. They go to `S/`, scratch files to `S/verify/`.

## Finishing

The run ends with implement-tasks PHASE 3. As soon as `S/verifications/final-verification.md` is written,
call `finish`.
