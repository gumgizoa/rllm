# Spec-Driven Development with Spec Kit: the Core Chain

You are taking one issue through GitHub Spec Kit's spec-driven development (SDD) chain. Upstream, a
person types five slash commands one after another and reviews each result before typing the next.
Here there is no such person: you run all five stages yourself, back to back, in this session. This
chain is how the task gets solved, and it takes precedence over any procedure you would follow otherwise.

## Where Everything Lives

| What | Path |
|------|------|
| This document and the stage documents | `/speckit-sdd/`, a directory right under the filesystem root `/` and not part of the repository |
| The repository you change | `/testbed` |
| The Spec Kit project, already initialized | `/tmp/speckit-sdd/`; its `.specify/` holds the scripts, the templates and the constitution |
| The feature directory (`FEATURE_DIR`) | `/tmp/speckit-sdd/specs/001-issue/` |
| Verification scripts (the files of the test tasks) and any scratch files | `/tmp/speckit-sdd/specs/001-issue/checks/` |

The files under `/tmp/speckit-sdd/.specify/scripts/`, `templates/` and `memory/` are Spec Kit's own;
leave them as they are. The feature directory does not exist yet: the specify stage creates it.

## The Five Stages

| # | Stage | Open first | Script the stage runs | What it produces in `FEATURE_DIR` |
|---|-------|------------|-----------------------|-----------------------------------|
| 1 | specify | `/speckit-sdd/stages/01-specify.md` | none; the stage sets the feature up itself | `spec.md`, `checklists/requirements.md` (and `/tmp/speckit-sdd/.specify/feature.json`) |
| 2 | plan | `/speckit-sdd/stages/02-plan.md` | `setup-plan.sh --json` | `plan.md`, `research.md`, `data-model.md`, `quickstart.md` (both always; body `N/A — <reason>` when nothing applies), contract files under `contracts/` (listed in plan.md's Documentation tree, or `contracts/  # N/A — <reason>` there and no file) |
| 3 | tasks | `/speckit-sdd/stages/03-tasks.md` | `setup-tasks.sh --json` | `tasks.md` |
| 4 | implement | `/speckit-sdd/stages/04-implement.md` | `check-prerequisites.sh --json --require-tasks --include-tasks` | per user story, first its verification scripts in `checks/` (run, seen failing), then the code change in `/testbed`, then the scripts again (passing); `[X]` marks in `tasks.md` |
| 5 | converge | `/speckit-sdd/stages/05-converge.md` | `check-prerequisites.sh --json --require-spec --require-tasks --include-tasks` | `convergence.md` (round 2: `convergence-2.md`), and possibly a new Convergence phase in `tasks.md` |

The scripts sit in `/tmp/speckit-sdd/.specify/scripts/bash/`, and each stage document spells out the
full command. Begin every stage by opening its document, and carry the stage out from that document
rather than from memory.

## Running Order

1. specify, plan and tasks run once each, in that order.
2. implement and converge then alternate, in at most two rounds:
   - Round 1: implement works through the whole of `tasks.md`; converge writes `convergence.md`.
   - If that report's **Outcome** is `tasks_appended`, round 2 follows: implement does only the
     unchecked tasks (the new `## Phase N: Convergence`), and converge writes `convergence-2.md`.
3. The chain is over as soon as a converge round records `converged`, or after round 2 whatever it
   found. Then call `finish`.

## What the Feature Is

The issue in the task message, the text between `<issue_description>` and `</issue_description>`, is the
feature description for the specify stage and stays the reference for every later stage. Use only that
text, the repository and what is already installed. Links in the issue stay closed (where one matters,
note it as `[UNVERIFIED — not fetched]`), nothing is searched for online, and no package is installed.

## Working Without a Reviewer

Nobody reviews a stage, answers a question or types the next command, and every message you send
without a tool call ends the session on the spot. So:

- go from one stage straight into the next; a stage ends by opening the next document, not with a summary;
- if you catch yourself about to ask something, decide it instead: take the most plausible reading and
  write it down where it belongs (the spec's `## Assumptions`, a decision in `research.md`, the notes of
  `checklists/requirements.md`);
- the checkboxes in `tasks.md` are the record of implement's progress; a task-tracking tool is optional
  scratch beside them, never a substitute.

## Who Writes What

| File in `FEATURE_DIR` | Written by | Changed later |
|-----------------------|------------|---------------|
| `spec.md`, `checklists/requirements.md` | specify | no |
| `plan.md`, `research.md`, Phase 1 files | plan | no |
| `tasks.md` | tasks | only by implement's `[X]` marks and by converge appending a `## Phase N: Convergence` |
| `convergence.md`, `convergence-2.md` | converge, one per round | no |
| `checks/` | implement, for the verification scripts of the test tasks; any stage, for scratch files | as needed |

## The Repository

- implement is the only stage that edits `/testbed`; the other stages only read it and run commands in it.
- No test file is added or changed there. The tests this workflow writes are the verification scripts
  in `FEATURE_DIR/checks/`: each is run and seen failing before the code it covers exists, and passing
  once it does. The existing tests related to the change are run before implementing, for a baseline,
  and again afterwards.
- Ignore files (`.gitignore`, `.dockerignore` and so on) stay untouched.
- Nothing of the workflow lands in `/testbed`: no spec copies, notes, summaries or scratch scripts. All of
  that belongs in `FEATURE_DIR`, with verification scripts and scratch files under `FEATURE_DIR/checks/`.
  A script written anywhere else — `/tmp/test_x.py`, `/testbed/repro.py` — breaks this rule.

## When a Script Fails

The scripts are Spec Kit's own and print Spec Kit's hints, written for someone typing slash commands. An
error like "plan.md not found ... Run /speckit.plan first" means that the stage named in the hint has not
produced its file yet:

| The hint names | Carry out first |
|----------------|-----------------|
| `/speckit.specify`, or "Feature directory not found" | `/speckit-sdd/stages/01-specify.md` |
| `/speckit.plan` | `/speckit-sdd/stages/02-plan.md` |
| `/speckit.tasks` | `/speckit-sdd/stages/03-tasks.md` |

After that, run the failing script again. The scripts work from any directory, `/testbed` included.
