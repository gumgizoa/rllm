# OpenSpec in One Session

OpenSpec turns a request into a **change**: a folder of planning **artifacts** (proposal, specs, design,
tasks) that the code is then written against. In this session the path is

```
/opsx:explore ──► /opsx:ff ──► /opsx:apply ──► /opsx:verify ──► archive
```

Upstream, a person types each of these actions in turn and may leave out explore. Here no one types
them: you take every action yourself, in this order, within this one session, and explore always
comes first. This document (`/opsx/core-workflow.md`) and the
stage documents beside it live in `/opsx`, a top-level directory of the filesystem; the repository you
change is `/testbed`, a different place.

## Actions

| Action | Open this first | Starts from | Leaves |
|--------|-----------------|-------------|--------|
| explore | `/opsx/stages/00-explore.md` | `openspec list --json` | no file: only the "What We Figured Out" summary, in a tool call before the ff document is opened |
| ff | `/opsx/stages/01-ff.md` | `openspec new change "issue"` | the change and every planning artifact |
| apply | `/opsx/stages/02-apply.md` | `openspec instructions apply --change "issue" --json` | the code change, tasks checked |
| verify | `/opsx/stages/03-verify.md` | `openspec status --change "issue" --json`, then your own review: no `openspec` command performs verify or writes its report | `verify.md` |
| archive | this document, below | `openspec archive issue --yes` | the archived change |

OpenSpec calls these actions, not phases: apply may send you back to ff for a missing artifact. Each
stage document says where to go next. The `openspec` command
is installed and does the bookkeeping. What it prints as JSON (paths, artifact order, the instruction
and template for each artifact, task progress) outranks your own guesses.

## Fixed Names

- Planning root: `/openspec`, already set up with `openspec init`, with its schema already chosen in
  `/openspec/config.yaml`. Never run `openspec init` again and never pass `--schema`.
- The change is called `issue` and lives in `/openspec/changes/issue/`.
- From the ff action on, scripts you write to reproduce or check behavior go in
  `/openspec/changes/issue/checks/`. Explore writes none.

## The Input

The input to explore, and after it to ff, is the issue, the text between `<issue_description>` and
`</issue_description>` in the task message. It says what to build or what to fix. Work from that text,
the repository and the installed environment only: do not open links found in the issue, do not search
for anything online, and do not install packages.

## No One Will Answer

Nobody reads your messages before the session is over, and a reply without a tool call ends the session
on the spot. So, until you call `finish`:

- never ask a question and never stop to report;
- whenever a stage document says to show, display, announce or tell something, put that note in a turn
  that also makes a tool call, or write it into an artifact;
- when something is unclear, pick the most plausible reading, write it down as an assumption in the
  artifact at hand (explore's summary, the proposal, design's **Decisions**, a plain line under the task in `tasks.md`),
  and keep going.

## From Explore to ff

Explore investigates the issue against the code before anything is planned. It is over once you can
state the problem and where the change goes, each backed by what you read or ran; open questions may
remain. It leaves no file. What it leaves is the "What We Figured Out" summary, written inside a tool
call (the `think` tool, for example) before you open `/opsx/stages/01-ff.md`. ff then writes the proposal and the design
from that summary: the proposal's Why and the design's Context and **Decisions** (choice, rationale,
alternatives) rest on it, and its assumptions go into the proposal.

## Specs Here

`/openspec/specs/` starts out empty, so this project has no capability yet for a change to modify. Any
delta spec you write is therefore an `## ADDED Requirements` delta for a new capability.

## The Repository

- Only the apply action edits `/testbed`. ff and verify read it and run commands in it.
- Explore reads it too, but runs only what is already there: existing code, existing tests, and the
  issue's own example exactly as given. It composes no code of its own: not a one-line
  `python -c`, not a heredoc piped to `python3`, not a script in `/tmp`. It writes no file anywhere,
  inside the repository or outside it. A variant worth trying becomes an open question for ff.
- Do not add or edit test files there; the tests for this task already exist. Touch README, `docs/`
  or changelogs only if the issue asks for it.
- Leave nothing else behind in `/testbed`: no notes, summaries or scratch scripts. Those belong under
  `/openspec/changes/issue/`.

## Verify Once

Verify runs once and writes `/openspec/changes/issue/verify.md`. Whatever it finds, move on to
archive; the report records what is still open.

## Archive, Then Finish

The code change must be complete before this step, and so must the verify report: archive only once
`/openspec/changes/issue/verify.md` exists. If it does not, open
`/opsx/stages/03-verify.md` and write it first. Then run once:

```bash
openspec archive issue --yes
```

It validates the change, merges its delta specs into `/openspec/specs/` and moves the change to
`/openspec/changes/archive/<date>-issue/`.

- Exit code 0: call `finish`.
- Exit code 1: correct only what the error message names in the delta spec (its format, or a spec file
  that is missing), then run the same command one more time. If it fails again, call `finish` without
  archiving. Never add `--no-validate`, and do not reopen tasks or apply: the code is done, and judging
  it was verify's job.
