# Survey: OpenSpec (OPSX workflow)

- Upstream: https://github.com/Fission-AI/OpenSpec @ 9111a7654d7800391459431fff4eaf66e33a3d2e (npm `@fission-ai/openspec` 1.14.1, commit dated 2026-10-06), license MIT (`LICENSE`, "Copyright (c) 2024 OpenSpec Contributors": permission to use/copy/modify/distribute, provided the copyright and permission notice are included in all copies or substantial portions)
- Checkout: /gpfs/home/daink/2026-2_DFM/OpenSpec (read-only; `git remote` = origin above)

All paths below are relative to the checkout. `skills/<name>/SKILL.md` line numbers are used for the
agent text because they are the committed render of the templates (see "Agent-facing sources").

## Normal use

**Install / init.** Node >= 20.19 (`package.json` `engines`). `npm install -g @fission-ai/openspec@latest`
then `cd your-project && openspec init` (`README.md:130`, `README.md:143`). node/npm are not installed on
this host, so `openspec init` was not run; outputs below come from the generator source.

`openspec init` generates:
- `openspec/`, `openspec/specs/`, `openspec/changes/`, `openspec/changes/archive/` (`src/core/init.ts:899-905`)
  plus `.gitkeep` anchors (`src/core/init.ts:932-935`).
- `openspec/config.yaml` with `schema: spec-driven` and commented-out `context:`, `rules:`, operation
  guidance (`src/core/init.ts:1150-1167`, `src/core/config-prompts.ts:9-49`).
- Per selected AI tool (30+ adapters, `src/core/command-generation/adapters/`): one
  `<skillsDir>/skills/openspec-<workflow>/SKILL.md` per installed workflow (`src/core/init.ts:993-1008`;
  Claude Code `skillsDir` = `.claude`, `src/core/config.ts:53`) and/or slash commands, e.g.
  `.claude/commands/opsx/<id>.md` (`src/core/command-generation/adapters/claude.ts:20-22`). Delivery mode
  (`skills` / `commands` / `both`, default `both`) is global config (`src/core/init.ts:974`).
- Which workflows: profile `core` (default) = `propose, explore, apply, update, sync, archive`
  (`src/core/profiles.ts:14`); profile `custom` can add `new, continue, ff, bulk-archive, verify, onboard`
  (`src/core/profiles.ts:19-32`, `README.md:153`), selected via `openspec config profile` + `openspec update`.
- Skill frontmatter: `name`, `description`, `allowed-tools: Bash(openspec:*)`, `license`, `compatibility:
  Requires openspec CLI.`, `metadata.generatedBy` (`src/core/shared/skill-generation.ts:181-193`,
  `src/core/shared/allowed-tools.ts:11`).

**Driving it.** Two halves: the `openspec` CLI in a terminal sets up and validates; day-to-day work is
slash commands typed into the AI chat (`docs/how-commands-work.md:12-45`). Each skill makes the agent
call the CLI for deterministic scaffolding, status and per-artifact instructions, and the agent writes
the files (`docs/workflows.md:59-98`).

**Worked example** (`README.md:47-77`, `docs/workflows.md:62-98`):
1. `/opsx:explore` (optional) — chat about the idea, no code.
2. `/opsx:propose add-dark-mode` — agent runs `openspec new change add-dark-mode`, `openspec status
   --json`, `openspec instructions <artifact> --json` per artifact, and writes
   `openspec/changes/add-dark-mode/{proposal.md, specs/<capability>/spec.md, design.md, tasks.md}`; then
   stops for human review.
3. Human types `/opsx:apply` — agent reads the four artifacts, implements tasks, flips `- [ ]` to `- [x]`.
4. Human types `/opsx:archive` — agent offers to merge delta specs into `openspec/specs/`, then moves the
   change to `openspec/changes/archive/YYYY-MM-DD-add-dark-mode/`.

## Processes

The default artifact schema behind every process is `spec-driven`: proposal -> specs -> design -> tasks,
then apply (`schemas/spec-driven/schema.yaml:1-272`). Upstream frames these as "actions, not phases" that
can be invoked in any order (`docs/workflows.md:5`, `docs/opsx.md:46-57`).

| Process | Stages (in order) | Reads / writes | Who advances | Agent-facing text | Human checkpoints |
|---|---|---|---|---|---|
| **A. Core quick path** (`core` profile, canonical) | explore (opt) -> propose -> [update]* -> apply -> sync (opt) -> archive (`docs/workflows.md:102-117`) | propose writes `openspec/changes/<name>/.openspec.yaml`, `proposal.md`, `specs/<cap>/spec.md`, `design.md` (conditional), `tasks.md`; apply edits project code + checkboxes in `tasks.md`; sync edits `openspec/specs/<cap>/spec.md`; archive moves change dir to `changes/archive/` | Person types each slash command; propose must stop after planning (`skills/openspec-propose/SKILL.md:14,168`) | propose 173 + apply 205 + sync 289 + archive 220 = 887 lines SKILL.md, plus CLI-served `schema.yaml` 272 + templates 79 | After propose (review, mandatory stop, `skills/openspec-propose/SKILL.md:14`); ambiguity questions (`:54`, `:139-141`); apply pauses on unclear/blocked (`skills/openspec-apply-change/SKILL.md:114-119`); archive confirm/sync choice (`skills/openspec-archive-change/SKILL.md:81-84,103-106,127-136`) |
| **B. Expanded step-wise** (`custom`) | new -> continue (one artifact per call, x4) -> apply -> verify -> sync -> archive (`docs/workflows.md:145-196`) | new: scaffolds change dir only; continue: writes ONE artifact then stops; verify: read-only report | Person re-invokes `/opsx:continue` per artifact (`skills/openspec-continue-change/SKILL.md:64,71`); new stops after scaffold (`skills/openspec-new-change/SKILL.md:71`) | new 87 + continue 134 + apply 205 + verify 219 + sync 289 + archive 220 = 1154 | After every artifact; verify reports CRITICAL/WARNING to the person (`skills/openspec-verify-change/SKILL.md:161-202`) |
| **C. Fast-forward** (`custom`) | ff (all planning artifacts) -> apply -> verify (opt) -> archive | Same artifacts as propose | Person invokes apply next, but ff has **no planning boundary** and says "prefer making reasonable decisions to keep momentum" (`skills/openspec-ff-change/SKILL.md:125`); its closing prompt is "Run apply or ask me to implement" (`:109`) | ff 127 + apply 205 (+ verify 219) | Only "critically unclear" questions (`skills/openspec-ff-change/SKILL.md:95,125`); apply pauses as in A |
| **D. Explore** | No fixed steps: "a stance, not a workflow" (`skills/openspec-explore/SKILL.md:16`) | Reads code; may write change artifacts only after a yes/no confirmation in a separate message (`:14`, `:349`) | Person | 353 | Every write; never implements (`:14`, `:345`) |
| **E. Update** | select change -> read/reconcile -> confirm+write one artifact at a time -> point to next step (`skills/openspec-update-change/SKILL.md:33-92`) | Planning artifacts only; never code (`:103`) | Person | 108 | Each revision written only after user confirms (`:82`) |
| **F. Onboard** | Preflight -> Welcome -> Task selection -> Explore demo -> Create change -> Proposal -> Specs -> ... (`skills/openspec-onboard/SKILL.md:29-293`) | Tutorial that walks a full change on a real small task, ~15-20 min (`:64`) | Person, with explicit **PAUSE** points (`:173`, `:263`) | 574 | Many |
| **G. Bulk archive** | list -> select -> batch validate -> detect spec conflicts -> resolve by code search -> confirm -> archive each (`skills/openspec-bulk-archive-change/SKILL.md:35-252`) | Main specs + archive dir for several changes | Person | 376 | Selection (`:41`) and batch confirm (`:169`) |
| **H. CLI-only archive** | `openspec archive <name> --yes` validates, applies deltas, archives with no prompts (`docs/workflows.md:97`, `src/core/archive.ts:186-189`) | Same as archive | CLI | 0 (CLI) | None with `--yes` |

## Agent-facing sources

Rendering: every skill and command body is a TypeScript template string. At generation time
(a) optional-workflow conditionals `[[opsx:if-workflow X]]...[[opsx:else]]...[[opsx:end]]` are resolved
against the installed workflow set (`src/core/templates/optional-workflow.ts:1-40`,
`src/core/shared/skill-generation.ts:98-107`), and (b) canonical `/opsx:<id>` references are rewritten
per tool (`src/utils/command-references.ts:38-47`), e.g. to `/openspec-apply-change` for the skills.sh
copy (`src/utils/command-references.ts:139`). Skill vs command variants of the same workflow differ
only in a few lines (e.g. `**Input**` wording, `src/core/templates/workflows/propose.ts:57` vs `:222`;
handoff wording, `:20-30`). Commands for a few tools get `$ARGUMENTS` injected by their adapter
(`src/core/command-generation/adapters/opencode.ts:23`, `command-code.ts:22`); Claude's command adapter
injects none (`claude.ts:24-34`). `skills/*/SKILL.md` is a committed render with **all** workflows
installed and skill-style references (`scripts/generate-skillssh.mjs:36-46`,
`src/core/shared/skill-generation.ts:54-58`), kept in sync by a parity test (`skills/README.md:17-19`).

Per-artifact text (proposal/specs/design/tasks instructions + templates) is **not** in the skills: the
agent gets it at run time from `openspec instructions <id> --change <name> --json`, which the CLI builds
from `schema.yaml` `instruction`, the schema template file, and `openspec/config.yaml` `context`/`rules`
(`src/core/artifact-graph/instruction-loader.ts:333-335,396-415`). Apply's "dynamic instruction" and
`blocked`/`all_done` state also come from the CLI (`src/commands/workflow/instructions.ts:635-682`).

| File (upstream path) | Role | Generated? | Lines |
|---|---|---|---|
| `src/core/templates/workflows/propose.ts` | propose skill + command source | Source (pre-render; TS string) | 356 |
| `src/core/templates/workflows/apply-change.ts` | apply source (`getApplyInstructions`, one body for both surfaces) | Source | 246 |
| `src/core/templates/workflows/ff-change.ts` | ff source | Source | 263 |
| `src/core/templates/workflows/verify-change.ts` | verify source | Source | 425 |
| `src/core/templates/workflows/archive-change.ts` | archive source | Source | 495 |
| `src/core/templates/workflows/sync-specs.ts` | sync source | Source | 566 |
| `src/core/templates/workflows/{new-change,continue-change,update-change,explore,onboard,bulk-archive-change}.ts` | other workflow sources | Source | 178 / 276 / 269 / 608 / 634 / 760 |
| `src/core/templates/workflows/project-root.ts` | `PROJECT_ROOT_GUARD`, interpolated into every workflow | Source | 37 |
| `src/core/templates/workflows/store-selection.ts` | `STORE_SELECTION_GUIDANCE`, interpolated into every workflow | Source | 7 |
| `src/core/templates/workflows/feedback.ts` | feedback skill; not in `ALL_WORKFLOWS`, used by CLI `feedback` only (`src/cli/index.ts`) | Source | 116 |
| `skills/openspec-*/SKILL.md` (12 files) | rendered skills (all-workflow, skill references, no `generatedBy`) | Generated, committed | 87-574 each; propose 173, apply 205, ff 127, verify 219, archive 220, sync 289 |
| `schemas/spec-driven/schema.yaml` | artifact graph + per-artifact `instruction` + `apply` block | Used as is (served via CLI) | 272 |
| `schemas/spec-driven/templates/{proposal,spec,design,tasks}.md` | artifact skeletons | Used as is (served via CLI) | 34 / 13 / 21 / 11 |
| `openspec/config.yaml` (in user project) | `schema`, optional `context`, `rules`, operation guidance | Generated by init | ~50 (comments) |

A converter should read the `src/core/templates/workflows/*.ts` strings (or, simpler, the committed
`skills/*/SKILL.md` renders) **plus** `schemas/spec-driven/schema.yaml` and its four templates, because
the skills alone do not contain the artifact instructions.

## Machinery the text relies on

- **Scripts / CLI**: every workflow drives the `openspec` Node CLI: `openspec list --json` (root check,
  `skills/openspec-propose/SKILL.md:30`), `openspec context --json` (`:58`), `openspec new change "<name>"`
  (`:82`), `openspec status --change --json` (`:93`), `openspec instructions <id> --change --json`
  (`:109`), `openspec instructions apply --json` (`skills/openspec-apply-change/SKILL.md:51`),
  `openspec list --specs`, `openspec show <spec> --type spec` (`schemas/spec-driven/schema.yaml:22-33`),
  `openspec validate --specs` (`skills/openspec-sync-specs/SKILL.md:179`), `openspec instructions archive`
  (`skills/openspec-archive-change/SKILL.md:49`). JSON shapes and exit codes are documented in
  `docs/agent-contract.md:47-105`. `openspec new change` scaffolds `openspec/specs/`,
  `openspec/changes/archive/`, writes `openspec/config.yaml` if missing and `.openspec.yaml`
  (`schema`, `created`) in the change dir (`src/utils/change-utils.ts:163-199`). Archive itself is a
  plain `mkdir -p` + `mv` the agent runs (`skills/openspec-archive-change/SKILL.md:170-183`).
- **Config**: agent reads `openspec/config.yaml` `context` (<= 51,200 bytes) as constraints
  (`skills/openspec-propose/SKILL.md:60-64`); `rules` per artifact arrive inside `instructions` JSON.
  `.openspec.yaml` flags `skip_specs`, `retire_capabilities` change behavior
  (`schemas/spec-driven/schema.yaml:36-42`, `skills/openspec-sync-specs/SKILL.md:141`).
- **Validation format rules**: delta specs need `## ADDED/MODIFIED/REMOVED/RENAMED Requirements`,
  `### Requirement:`, exactly `#### Scenario:` with WHEN/THEN, SHALL/MUST
  (`schemas/spec-driven/schema.yaml:96-108`); a change with zero deltas fails `openspec validate` unless
  `skip_specs: true` (`:36-42`). tasks.md checkbox grammar is parsed by the CLI (`:209-213`,
  `src/utils/task-progress.ts:8-21`).
- **Hooks / extensions**: none in the workflow text. Customisation is by alternative schemas
  (`docs/opsx.md:577-629`) and "stores" (separate planning repo, `--store <id>`) whose guidance paragraph
  is prepended to every skill (`src/core/templates/workflows/store-selection.ts:7`).
- **Network**: CLI telemetry to `https://edge.openspec.dev` (`src/telemetry/index.ts:32`), disabled by
  `OPENSPEC_TELEMETRY=0`, `DO_NOT_TRACK=1`, or `CI` set (`src/telemetry/index.ts:68-70`); npm version
  check against `registry.npmjs.org` (`src/core/version-check.ts:15`). The workflow text itself needs no
  network.
- **Git**: no branch or commit operations in any workflow. Only mentions: onboard runs `git log --oneline
  -10` (`skills/openspec-onboard/SKILL.md:87`); sync suggests a `git checkout` recovery line
  (`skills/openspec-sync-specs/SKILL.md:152`). Git is used by the stores feature only (`src/core/store/git.ts`).
- **Interactive points** (the agent is told to ask and wait): missing/unclear input
  (`skills/openspec-propose/SKILL.md:47`); material ambiguity before creating the change (`:54`);
  "artifact requires user input" (`:139-141`); existing change name (`:172`); no `openspec/` root ->
  explicit request "stop before writing and ask", auto-selected "stop using OpenSpec"
  (`skills/openspec-propose/SKILL.md:34-39`, source `src/core/templates/workflows/project-root.ts:28-37`);
  design Open Questions that change the plan must be resolved with the user
  (`schemas/spec-driven/schema.yaml:185-187`, `:205-207`); apply change selection
  (`skills/openspec-apply-change/SKILL.md:35`) and pauses (`:114-119`, guardrail `:184`); archive confirms
  incomplete artifacts/tasks and offers sync choices (`skills/openspec-archive-change/SKILL.md:81-84,
  103-106,127-136`); explore/update confirmations (`skills/openspec-explore/SKILL.md:349`,
  `skills/openspec-update-change/SKILL.md:82`); onboard PAUSEs (`skills/openspec-onboard/SKILL.md:173,263`).
- **Stop points that end a turn**: propose "After the planning artifacts are complete, stop. Do not start
  implementation in the same response" (`skills/openspec-propose/SKILL.md:14`); new "STOP and wait"
  (`skills/openspec-new-change/SKILL.md:71`); continue writes one artifact then stops
  (`skills/openspec-continue-change/SKILL.md:64,71`).

## Fit for SWE tasks

Common to all: the target repo has no `openspec/` root, and the root guard says to stop/ask instead of
creating one (`skills/openspec-propose/SKILL.md:30-39`); all bookkeeping goes through a Node CLI that
**(inferred)** is not present in SWE-Gym images; artifacts default to `openspec/changes/<name>/` inside
the repo (`src/utils/change-utils.ts:163`), so **(inferred)** they would land in `/testbed` and in the
patch unless relocated; the specs layer assumes a library of capability specs under `openspec/specs/`
that SWE repos do not have, so every delta would be a new ADDED capability or `skip_specs`
(`schemas/spec-driven/schema.yaml:36-42`).

| Process | Fit | Main mismatch |
|---|---|---|
| A. propose -> apply (-> sync -> archive) | Medium | propose forbids implementing in the same response and requires a new user turn to start apply (`skills/openspec-propose/SKILL.md:14,168`) — under one-message/no-reply this ends the session with no patch; sync/archive only reshuffle `openspec/` files |
| B. new -> continue x4 -> apply -> verify | Low | Designed to stop after every artifact (`skills/openspec-continue-change/SKILL.md:64,71`, `skills/openspec-new-change/SKILL.md:71`) |
| C. ff -> apply -> verify | **High (closest)** | Same artifact loop as propose but no planning boundary and "prefer reasonable decisions" (`skills/openspec-ff-change/SKILL.md:125`); remaining mismatches are CLI calls, "ask/pause" branches in apply, and tasks.md's "each task states how to verify" (`schemas/spec-driven/schema.yaml:225-229`) which aligns well with running tests |
| D. explore | None | Never writes code (`skills/openspec-explore/SKILL.md:14,345`) |
| E. update | None | Planning artifacts only, confirms each write (`skills/openspec-update-change/SKILL.md:82,103`) |
| F. onboard | None | Human tutorial with PAUSEs (`skills/openspec-onboard/SKILL.md:64,173`) |
| G. bulk-archive | None | Operates on multiple finished changes; no code output |
| H. CLI archive | None | Bookkeeping only |

## Recommendation

Port **the spec-driven artifact chain run straight through as one unattended session: plan (proposal ->
specs -> design-if-needed -> tasks) -> apply -> verify**, taking the artifact loop and "no boundary"
stance from `ff` (process C) and the apply/verify bodies as is, with the per-artifact instructions and
templates inlined from `schemas/spec-driven/schema.yaml` + `templates/*.md` (since the CLI that serves
them will not be available). Reasons: it is the only upstream process whose text already allows planning
and implementation in one go; its tasks.md rule that every task names its verification maps onto running
the repo's tests; verify adds a self-check of requirements/scenarios against code before `finish`.
sync/archive are skipped (they only move planning files). Note that the upstream *default* entry point is
`propose` (process A); its artifact steps are textually the same as ff apart from the planning boundary
and the ambiguity-question step (`skills/openspec-propose/SKILL.md:14,45-74` vs
`skills/openspec-ff-change/SKILL.md:31-40`).

Proposed workflow name: `openspec_ff` (if the user prefers to label it by the canonical default,
`openspec_propose`).

Open questions for the user:
1. Base the port on `ff` (no planning boundary, upstream "expanded" profile) or on `propose` (upstream
   default, but its explicit "stop before implementing" rule must be overridden)?
2. Keep `verify` as a final stage (219 lines, keyword-search based report) or end at apply?
3. Keep the delta-spec format (`## ADDED Requirements` / `#### Scenario:` WHEN/THEN) as the specs
   artifact, or allow `skip_specs`-style bug fixes where no behavior spec is written?
4. Where should artifacts go — upstream path `openspec/changes/<name>/` inside `/testbed` (enters the
   patch) or a location outside the repo?

## Process chosen (user, 2026-10-13)

**new → ff → apply → verify → archive** — the expanded-profile path upstream documents in
`docs/getting-started.md:47` (`/opsx:new ──► /opsx:ff ──► /opsx:apply ──► /opsx:verify ──► /opsx:archive`).
Unlike the recommendation above, `new` and `archive` stay in: `new` scaffolds the change, `ff` writes all
planning artifacts, `archive` closes the change (sync of delta specs into main specs is part of archive's
flow). Agent-facing sources for stage 2: `skills/openspec-{new-change,ff-change,apply-change,verify-change,
archive-change}/SKILL.md` (with their `src/core/templates/workflows/*.ts` sources), plus
`schemas/spec-driven/schema.yaml` and `schemas/spec-driven/templates/*.md` (served by the CLI at run time),
and any sync text archive pulls in. Proposed workflow name: `openspec_ff` (to confirm in stage 3).

**Revised (user, 2026-10-14):** the new stage is dropped — the chain is **ff → apply → verify → archive**; ff creates the change itself (`03-decisions.md` D-7).
