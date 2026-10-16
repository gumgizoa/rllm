# Agent OS: From Issue to Verified Change

This run follows Agent OS (v2.1.1), a spec-first workflow: the change is shaped into requirements, written
up as a specification, broken into a task list, and only then implemented and verified. With Agent OS a
developer attaches one command document per chat turn and reads the result before attaching the next.
Here you carry out all four command documents yourself, one after another, in this single session. That
sequence is how this task is solved; it replaces any procedure you would otherwise follow.

The workflow's documents are in `/agent-os/`, a directory directly under the filesystem root `/`. It is
not part of the repository at `/testbed`, and nothing of it exists under `/testbed`.

## The four commands

Open each command document when you reach it, and work from that document rather than from memory:

1. **shape-spec**: `/agent-os/commands/shape-spec/shape-spec.md`
   PHASE 1 creates the spec folder and saves the issue in it. PHASE 2 studies the change, writes its
   clarifying questions and your answers to them, and saves the requirements.
2. **write-spec**: `/agent-os/commands/write-spec/write-spec.md`
   Searches the repository for code to reuse and writes the specification.
3. **create-tasks**: `/agent-os/commands/create-tasks/create-tasks.md`
   Breaks the specification into task groups of checkbox tasks.
4. **implement-tasks**: `/agent-os/commands/implement-tasks/implement-tasks.md`
   PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 3
   verifies the result and writes the final verification report.

Each command runs once, in this order, and its document ends by naming the next one; implement-tasks ends
with its report. There are no repeat rounds.

Each command document already contains the coding standards it applies, written out under "User
Standards & Preferences Compliance". The bold `agent-os/standards/...` lines there only name each
standard; there are no separate standards files to open.

## What "the feature" is

The command documents speak of "a new feature", "the user's description" and "your idea". In this run
the description is the issue in the task message, the text between `<issue_description>` and
`</issue_description>`, and the feature is the change that issue asks for, whether a fix or an addition.
The issue is your only input from outside; everything else you learn from the repository.

## The spec folder

shape-spec creates the spec folder once, as `/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`: today's date and a
short kebab-case name you choose for the change. The documents call it `[this-spec]`, `[current-spec]`,
`[spec-path]` or `$SPEC_PATH`; each of these means that one folder, and every later command works in it.
Below it is written `S`.

```
S/
├── planning/
│   ├── initialization.md      shape-spec PHASE 1: the issue text, unchanged
│   ├── requirements.md        shape-spec PHASE 2: questions with your assumed answers, reuse findings
│   └── visuals/               made by shape-spec PHASE 1; stays empty, nobody adds mockups
├── spec.md                    write-spec
├── tasks.md                   create-tasks; implement-tasks ticks its checkboxes
├── checks/                    the tests the task groups call for, as scripts; any scratch file
├── implementation/            made by shape-spec PHASE 1; stays empty
└── verifications/
    └── final-verification.md  implement-tasks PHASE 3
```

No command creates `S/checks/`; make it the first time you need it. Write each file in the structure its
document gives, and leave a file alone once its command is over, except for the checkboxes in `tasks.md`.

## Nobody is on the other side

No person reads your messages, answers a question, reviews a result or starts the next command, and a
reply that calls no tool ends the session at once, with the work unfinished. So:

- Where a document has you ask questions, write them as it describes, then answer each one yourself from
  the issue and the repository, and record the answer with its basis where the document says
  (`**Answer:** (assumed) <answer> — <basis>` in `requirements.md`). Never wait for a reply.
- When a command is done, open the next command document right away instead of summing up. Send no
  plain-text message at all before `finish`.
- Progress is kept in the files. The checkboxes in `S/tasks.md` are the record of what has been
  implemented; the TaskTracker tool may serve as a private scratch list, but it does not replace ticking
  `tasks.md`.

## The repository

- Only implement-tasks PHASE 2 changes `/testbed`. shape-spec, write-spec and create-tasks read the
  repository and may run commands in it, but change nothing. implement-tasks PHASE 3 runs tests and writes
  its report without changing code, so the code change is complete before PHASE 3 begins.
- The tests the task groups call for are scripts in `S/checks/`. No test file in the repository is added
  or edited.
- Nothing that belongs to the workflow goes into `/testbed`: no spec files, notes, summaries or temporary
  scripts. They go to `S/`, scratch files to `S/checks/`.

## Finishing

The run ends with implement-tasks PHASE 3. As soon as `S/verifications/final-verification.md` is written,
call `finish`.
