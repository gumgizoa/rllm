# Build Auto Workflow

**Goal:** Turn intent into a hardened, reviewable artifact, without human interaction.

**CRITICAL:** If a step directs you to another workflow document, read it fully and follow it. No exceptions.

## HALT

To HALT with a final status and optional blocking condition:

1. If `{spec_file}` is known and exists, update `status` in frontmatter and append missing result details under `## Auto Run Result`.
2. If `{spec_file}` is unknown or missing, create `/tmp/bmad/implementation-artifacts/bmad-build-auto-result-<slug-or-timestamp>.md` with:
   ```markdown
   ---
   status: <final status>
   ---

   # BMad Build Auto Result

   Status: <final status>
   Blocking condition: <blocking condition, if any>
   ```
3. Stop the workflow. Nothing follows a HALT except ending the session.

## Subagents

Using subagents when instructed is mandatory. A subagent is launched with the `task` tool (see **The setting of this run** below): one `task` call runs one subagent to completion and returns its final message.

Launch all the subagents a step calls for in **one message** — several **blocking** calls awaited together in the same turn — then wait for all their results before continuing; a step that calls for one subagent is that same message with one call. Never split a step's launches across messages, and never run one detached. Never run a subagent in the background / detached / async (e.g. `run_in_background: true`), and never end your turn to "await a completion notification." This workflow runs unattended: there is no event loop to resume a yielded turn, so a backgrounded subagent never hands control back and the run stalls. The only sanctioned way to end a turn is the HALT protocol above with an explicit terminal `status`.

## READY FOR DEVELOPMENT STANDARD

A specification is "Ready for Development" when:

- **Actionable**: Every task has a file path and specific action.
- **Logical**: Tasks ordered by dependency.
- **Testable**: All ACs use Given/When/Then.
- **Surface-anchored**: ACs observe the outermost surface the intent references — never a more internal proxy for it.
- **Complete**: No placeholders or TBDs.
- **Sufficient**: No known requirement, acceptance, dependency, or implementation gaps remain unresolved.
- **Coherent**: No unresolved ambiguities or internal contradictions.

## Conventions

- Every operational cross-file reference in this workflow is an absolute path under `/bmad-build-auto/`. Open it directly.
- The project root is the repository `/testbed`; repository paths resolve from there.
- Write documents in English.
- Whenever this workflow captures or records a version-control revision, obtain the full canonical identifier directly from version control and preserve it verbatim.

## The setting of this run

This workflow runs unattended, inside a sandbox, on one task. What that means for each step:

| Step | Document | What it produces |
|---|---|---|
| 1 | `/bmad-build-auto/stages/step-01-clarify-and-route.md` | the slug, `{spec_file}` and `{diff_file}` |
| 2 | `/bmad-build-auto/stages/step-02-plan.md` | the spec, filled from `/bmad-build-auto/spec-template.md`, through the READY gate |
| 3 | `/bmad-build-auto/stages/step-03-implement.md` | the implementation (by the implementation subagent), the staged diff, verification |
| 4 | `/bmad-build-auto/stages/step-04-review.md` | four review layers (subagents), the triage log, patches or a loopback to step 3, `## Auto Run Result`, HALT |

- **Intent.** The task message that opened this conversation is the invocation intent: an issue against the repository at `/testbed`, which is the project root. Nothing else arrives — no planning artifacts, no epic, no story list, no earlier spec — so step 1 always takes the freeform path and every run plans from scratch.
- **Nobody answers.** No person reads this conversation while it runs. A question, a request for approval or a plain text reply with no tool call ends the session with nothing graded. Settle open points yourself, inside the step that raised them, and write the choice into the spec.
- **Where files go.** Everything the workflow writes for itself lives outside the repository: the spec at `/tmp/bmad/implementation-artifacts/spec-{slug}.md`, the diff at `/tmp/bmad/diff/{slug}.diff`, a fallback result file under `/tmp/bmad/implementation-artifacts/`. Create `/tmp/bmad/implementation-artifacts/` and `/tmp/bmad/diff/` when they are first needed. The only writes into `/testbed` are the implementation itself — the source and test files the spec's tasks name — and the review patches. Scratch files, notes, copies of these documents and the diff do not belong in `/testbed`.
- **Subagents.** "Launch a subagent" means one call of the `task` tool. Its `prompt` must carry everything the subagent needs — it starts with no memory of this conversation, so put the spec path, the diff path and the full instruction text into the prompt. Leave `subagent_type` at `general-purpose`: a subagent of that type has the terminal, the file editor and the task tracker, and works in the same `/testbed`; it cannot launch subagents of its own. The call blocks until the subagent finishes. Its result opens with `Task ID: task_…`, `Subagent: …` and `Status: …`, followed by the subagent's final message — that message is the "report" or "findings" the steps refer to. Several `task` calls issued in one assistant turn are all carried out before that turn resumes — the turn waits for every one of them; that is how step 4 runs its four review layers as one launch. A `task` call with `resume` set to an earlier Task ID continues that same subagent's conversation; that is how step 4 hands the implementation subagent its fixes. The subagent's name is the Task ID the tool assigns — keep the implementation subagent's Task ID from step 3 for step 4.
- **A failed check does not end the run.** Where a step says to set `status: blocked` and record a blocking condition, write both into `{spec_file}` — `status` in the frontmatter and a line under `## Auto Run Result` — and carry on with the next instruction. The run still reaches Finalize and HALT, with `blocked` as its final status.
- **What is graded.** The working tree of `/testbed` after HALT. Do not commit, stash, reset or clean the repository: a commit would take the change out of the graded diff.
- **Reading order.** This document first, then `/bmad-build-auto/stages/step-01-clarify-and-route.md` and the steps it chains to. Open each document when its step begins, not before. The spec template and the reviewer prompts are under `/bmad-build-auto/` too; the reviewer prompts are read by the review subagents, not by you.
- **End.** The run ends with HALT — `done`, or `blocked` when a blocking condition was recorded — after `## Auto Run Result` is written. Then call `finish`.

## Workflow Execution

Follow the step files in order. Read one step fully, execute it, then load the next step only when directed. Do not skip, reorder, or pre-load steps.

## First Workflow Step

Read fully and follow: `/bmad-build-auto/stages/step-01-clarify-and-route.md`.
