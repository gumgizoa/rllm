# Agent OS: From Verified Change to Written Record

This run uses Agent OS (v2.1.1), a spec workflow, as the written record of a change you have already
made. First you solve the task the way you normally would: explore the repository, see the reported
behavior for yourself, change the code and test the change. Only when the change is made and tested do
you carry out Agent OS's four command documents: they write down the requirements, the specification
and the task list of that change, check the work against the list, and verify the result. With Agent OS
a developer attaches one command document per chat turn and reads the result before attaching the next.
Here you carry out all four command documents yourself, one after another, in this single session.

The workflow's documents are in `/agent-os/`, a directory directly under the filesystem root `/`. It is
not part of the repository you work in, and nothing of it exists inside the repository.

## First: the change

Solve the task before you open any command document. No rule of the command documents applies to this
part: work as you normally would, and write nothing under `/tmp/agent-os/` yet. This part is over when
the change is in the repository and you have tested it.

## Then: the four commands

Open each command document when you reach it, and work from that document rather than from memory:

1. **shape-spec**: `/agent-os/commands/shape-spec/shape-spec.md`
   PHASE 1 creates the spec folder and saves the task description in it. PHASE 2 writes its clarifying
   questions and your answers to them, and saves the requirements. You answer from what you learned
   while making the change.
2. **write-spec**: `/agent-os/commands/write-spec/write-spec.md`
   Writes the specification. It specifies the change you made.
3. **create-tasks**: `/agent-os/commands/create-tasks/create-tasks.md`
   Breaks the specification into task groups of checkbox tasks. They list the work of the change you
   made.
4. **implement-tasks**: `/agent-os/commands/implement-tasks/implement-tasks.md`
   PHASE 1 and PHASE 2 go through every task group in order, one group per pass of PHASE 2. A task your
   change already covers is ticked without changing the code again; a task it does not cover yet is
   implemented, then ticked. PHASE 3 verifies the result and writes the final verification report.

Each command runs once, in this order, and its document ends by naming the next one; implement-tasks ends
with its report. There are no repeat rounds, with one exception inside implement-tasks: PHASE 3 sends
you back to PHASE 2 once when a test fails because of your change.

The command documents are written for a change that is still to be made ("a new feature", "to be
built", "write tests first"). Read them as describing the change you have made. Where a task group
calls for tests to be written first (its x.1 sub-task), the tests you wrote or ran while making the
change count; write more only where the change has no test yet.

The coding standards apply where code is written: the implement-tasks document contains them, written
out under "User Standards & Preferences Compliance". The bold `agent-os/standards/...` lines there only
name each standard; there are no separate standards files to open.

## What "the feature" is

The command documents speak of "a new feature", "the user's description" and "your idea". In this run
the description is the task description in the task message: the report of what is wrong or what is
wanted. The feature is the change that description asks for. The task message is your only input from
outside; everything else you learn from the repository.

## The spec folder

shape-spec creates the spec folder once, as `/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`: today's date and a
short kebab-case name you choose for the change. The documents call it `[this-spec]`, `[current-spec]`,
`[spec-path]` or `$SPEC_PATH`; each of these means that one folder, and every later command works in it.
Below it is written `S`.

```
S/
├── planning/
│   ├── initialization.md      shape-spec PHASE 1: the task description, unchanged
│   └── requirements.md        shape-spec PHASE 2: questions with your assumed answers, reuse findings
├── spec.md                    write-spec
├── tasks.md                   create-tasks; implement-tasks ticks its checkboxes and may add tasks
├── verify/                    tests the commands write as scripts; their scratch files
└── verifications/
    └── final-verification.md  implement-tasks PHASE 3
```

No command creates `S/verify/`; make it the first time you need it. Write each file in the structure its
document gives, and leave a file alone once its command is over. `tasks.md` is the one exception:
implement-tasks ticks its checkboxes, and adds a task when the change needs work no task covers.

## Nobody is on the other side

No person reads your messages, answers a question, reviews a result or starts the next command, and a
reply that calls no tool ends the session at once, with the work unfinished. So:

- Where a document has you ask questions, write them as it describes, then answer each one yourself from
  the task description and the repository, and record the answer with its basis where the document says
  (`**Answer:** (assumed) <answer> — <basis>` in `requirements.md`). Never wait for a reply.
- When the change is made and tested, open the first command document right away, and when a command is
  done, open the next one right away instead of summing up. Send no plain-text message at all before
  `finish`.
- Progress of the commands is kept in the files. The checkboxes in `S/tasks.md` are the record of what
  has been implemented; the TaskTracker tool may serve as a private scratch list, but it does not
  replace ticking `tasks.md`.

## The repository

- The first part changes the repository as the task needs. Once the commands have begun, only
  implement-tasks PHASE 2 changes it, and only for a task the change does not cover yet or, when PHASE 3
  sends you back, to fix a test failure your change causes. shape-spec, write-spec and create-tasks read
  the repository and may run commands in it, but change nothing.
- Tests written while the commands run are scripts in `S/verify/`, or new test functions added to the
  existing repository test module that covers the changed code.
- Nothing that belongs to the workflow goes into the repository: no spec files, notes or summaries. They
  go to `S/`, the commands' scratch files to `S/verify/`.

## Finishing

The run ends with implement-tasks PHASE 3. As soon as `S/verifications/final-verification.md` is written,
call `finish`.
