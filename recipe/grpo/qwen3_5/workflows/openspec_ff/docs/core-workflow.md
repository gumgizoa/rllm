# OpenSpec in One Session

OpenSpec turns a request into a **change**: a folder of planning **artifacts** (proposal, specs, design,
tasks) that the code is then written against. Its expanded path is

```
/opsx:ff ──► /opsx:apply ──► /opsx:verify ──► archive
```

Upstream, a person types each of these actions in turn. Here no one types them: you take every action
yourself, in this order, within this one session. This document (`/opsx/core-workflow.md`) and the
stage documents beside it live in `/opsx`, a top-level directory of the filesystem; the repository you
change is `/testbed`, a different place.

## Actions

| Action | Open this first | Starts from | Leaves |
|--------|-----------------|-------------|--------|
| ff | `/opsx/stages/01-ff.md` | `openspec new change "issue"` | the change and every planning artifact |
| apply | `/opsx/stages/02-apply.md` | `openspec instructions apply --change "issue" --json` | the code change, tasks checked |
| verify | `/opsx/stages/03-verify.md` | `openspec status --change "issue" --json`, then your own review: no `openspec` command performs verify or writes its report | `verify.md` (round 2: `verify-2.md`) |
| archive | this document, below | `openspec archive issue --yes` | the archived change |

OpenSpec calls these actions, not phases: apply may send you back to ff for a missing artifact, and
verify may send you back to apply. Each stage document says where to go next. The `openspec` command
is installed and does the bookkeeping. What it prints as JSON (paths, artifact order, the instruction
and template for each artifact, task progress) outranks your own guesses.

## Fixed Names

- Planning root: `/openspec`, already set up with `openspec init`, with its schema already chosen in
  `/openspec/config.yaml`. Never run `openspec init` again and never pass `--schema`.
- The change is called `issue` and lives in `/openspec/changes/issue/`.
- Scripts you write to reproduce or check behavior go in `/openspec/changes/issue/checks/`.

## The Input

The input to the ff action is the issue, the text between `<issue_description>` and
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
  artifact at hand (the proposal, design's **Decisions**, a plain line under the task in `tasks.md`),
  and keep going.

## Specs Here

`/openspec/specs/` starts out empty, so this project has no capability yet for a change to modify. Any
delta spec you write is therefore an `## ADDED Requirements` delta for a new capability.

## The Repository

- Only the apply action edits `/testbed`. ff and verify read it and run commands in it.
- Do not add or edit test files there; the tests for this task already exist. Touch README, `docs/`
  or changelogs only if the issue asks for it.
- Leave nothing else behind in `/testbed`: no notes, summaries or scratch scripts. Those belong under
  `/openspec/changes/issue/`.

## Verify Rounds

1. Round 1 of verify writes `/openspec/changes/issue/verify.md`.
2. If that report lists a CRITICAL issue, go back to apply for those CRITICAL items only, then verify
   again and write `/openspec/changes/issue/verify-2.md`.
3. There are at most two verify rounds. After round 2 move on to archive whatever it found; the
   report records what is still open. WARNING and SUGGESTION items never trigger a round.

## Archive, Then Finish

The code change must be complete before this step, and so must the verify report: archive only once
`/openspec/changes/issue/verify.md` (or `verify-2.md`) exists. If it does not, open
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
