# Agent OS: From Task to Verified Change

This run follows Agent OS (v2.1.1), a spec-first workflow: the change is shaped into requirements, worked
out as a specification, broken into a task list, and only then implemented and verified. With Agent OS a
developer attaches one command document per chat turn and reads the result before attaching the next.
Here you carry out all four command documents yourself, one after another, in this single session. That
sequence is how this task is solved; the steps of the procedure in your system prompt are carried out inside it.

In this run the planning is done in your reasoning, not on paper. shape-spec, write-spec and create-tasks
are carried out in full, but none of them writes a file: no `initialization.md`, no `requirements.md`,
no `spec.md`, no `tasks.md`. The only document of the run is the final verification report.

The workflow's documents are in `/agent-os/`, a directory directly under the filesystem root `/`. It is
not part of the repository you work in, and nothing of it exists inside the repository.

## The four commands

Open each command document when you reach it, and work from that document rather than from memory:

1. **shape-spec**: `/agent-os/commands/shape-spec/shape-spec.md`
   PHASE 1 settles the name of the spec folder. PHASE 2 studies the change, forms its clarifying
   questions and your answers to them, and settles the requirements. Nothing is saved.
2. **write-spec**: `/agent-os/commands/write-spec/write-spec.md`
   Searches the repository for code to reuse and works out the specification. Nothing is saved.
3. **create-tasks**: `/agent-os/commands/create-tasks/create-tasks.md`
   Breaks the specification into task groups of tasks. Nothing is saved.
4. **implement-tasks**: `/agent-os/commands/implement-tasks/implement-tasks.md`
   PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 3
   verifies the result and writes the final verification report.

Each command runs once, in this order, and its document ends by naming the next one; implement-tasks ends
with its report. There are no repeat rounds, with one exception inside implement-tasks: PHASE 3 sends
you back to PHASE 2 once when a test fails because of your change.

The coding standards apply where code is written: the implement-tasks document contains them, written
out under "User Standards & Preferences Compliance". The bold `agent-os/standards/...` lines there only
name each standard; there are no separate standards files to open.

## Reading the documents without writing

The command documents are written for a run that saves each result to a file. Read them like this:

- Do every step a document describes: read the task description again, explore the repository, form the
  questions and answer them, search for code to reuse, decide the requirements, the specification and
  the task groups, each in the structure its document gives.
- Where a document says to create, write or save a file under the spec folder, or to create the folder
  itself, do not: go through what the file would hold, section by section, in your reasoning, and move
  on. Do not put that content anywhere else either: no file in another place, no `echo` or `cat` of it
  in the terminal, no TaskTracker entry that restates it.
- Where a later document says to read `initialization.md`, `requirements.md`, `spec.md` or `tasks.md`,
  go back in your reasoning to what you settled for that file. The file does not exist; do not look for it.
- In implement-tasks, the task groups are the ones you settled in create-tasks. Where the document says
  to tick a checkbox in `tasks.md`, note to yourself that the task is done. PHASE 3 Step 1 becomes: go
  over the task groups and make sure each one is implemented. The report's "Tasks Verification" section
  lists those task groups from your reasoning.

## What "the feature" is

The command documents speak of "a new feature", "the user's description" and "your idea". In this run
the description is the task description in the task message: the report of what is wrong or what is
wanted. The feature is the change that description asks for. The task message is your only input from
outside; everything else you learn from the repository.

## The spec folder

The spec folder is `/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/`: today's date and a short kebab-case name
you choose for the change. The documents call it `[this-spec]`, `[current-spec]`, `[spec-path]` or
`$SPEC_PATH`; each of these means that one folder. Below it is written `S`. In this run it holds only
this:

```
S/
├── verify/                    the task groups' tests that are written as scripts; any scratch file
└── verifications/
    └── final-verification.md  implement-tasks PHASE 3
```

No command creates these folders in this run; make `S/verify/` the first time you need it, and
`S/verifications/` when you write the report. Nothing else is written under `S/`.

## Nobody is on the other side

No person reads your messages, answers a question, reviews a result or starts the next command, and a
reply that calls no tool ends the session at once, with the work unfinished. So:

- Where a document has you ask questions, form them as it describes, then answer each one yourself from
  the task description and the repository, in your reasoning. Never wait for a reply.
- When a command is done, open the next command document right away instead of summing up. Send no
  plain-text message at all before `finish`.
- Every turn still includes a tool call. While you plan, that call is one that reads: opening the next
  command document, reading code, searching the repository or running a command in it.

## The repository

- Only implement-tasks PHASE 2 changes the repository. shape-spec, write-spec and create-tasks read the
  repository and may run commands in it, but change nothing. implement-tasks PHASE 3 runs tests and writes
  its report and changes no code itself; when a test fails because of your change it sends you back to
  PHASE 2 once, and that is the only code change after PHASE 3 has begun.
- The tests the task groups call for are scripts in `S/verify/`, or new test functions added to the
  existing repository test module that covers the changed code. No existing test line in the repository
  is changed or removed.
- Nothing that belongs to the workflow goes into the repository: no spec files, notes, summaries or temporary
  scripts. Scratch files go to `S/verify/`.

## Finishing

The run ends with implement-tasks PHASE 3. As soon as `S/verifications/final-verification.md` is written,
call `finish`.
