# Gaps: OpenSpec  (upstream Fission-AI/OpenSpec@9111a76 = npm `@fission-ai/openspec` 1.14.1; process new → ff → apply → verify → archive)

## Setting

- One user message (instruction + SWE task text, issue in `<issue_description>`, repo at `/testbed`), an
  openhands-sdk 1.42.1 agent running until `finish`, nobody answering, hidden tests graded afterwards.
  A message without a tool call ends the session (`.claude/skills/port-workflow/references/lessons.md`).
- **The real `openspec` CLI runs in the sandbox, and the planning root is initialized before the agent
  starts** (user decision 2026-10-13, `03-decisions.md` D-1/D-2). What that takes and what was verified is
  in "Sandbox setting" below. Consequence for this audit: everything the CLI computes or serves —
  status, paths, per-artifact instructions and templates, apply state, validation, archive — is used as
  upstream ships it, and the rows below are about the agent-facing text that remains a problem.
- Short names: `new`, `ff`, `apply`, `verify`, `archive`, `sync` = `skills/openspec-<x>[-change|-specs]/SKILL.md`
  (the committed renders; they differ from `src/core/templates/workflows/*.ts` only where optional-workflow
  blocks resolve with all workflows installed); `schema` = `schemas/spec-driven/schema.yaml`; `tpl/x.md` =
  `schemas/spec-driven/templates/x.md`. `sync` is part of the chain because archive step 4 runs it inline
  (`archive:147,213`).

## Gaps

| ID | Type | Upstream location | What the text does | Why it breaks in rllm (evidence) | Proposed handling | Tag | Status |
|---|---|---|---|---|---|---|---|
| G1-1 | G1 input | `new:27-38`, `ff:27-38` | input = "the user's request" (a change name or what to build); "If no clear input provided, ask what they want to build … Do NOT proceed without understanding" | the only input is the issue in `<issue_description>` (`scripts/prepare_swegym.py:166-180`); an ask ends the session | "input = the issue in `<issue_description>`: what to build or fix"; ask branch dropped | env | decided |
| G1-2 | G1 input | `apply:27-38`, `verify:27-42`, `archive:29-43`, `sync:31-44` | select the change: given name / infer / "Auto-select if only one active change exists" / "If ambiguous … ask the user to select one"; "Always announce: 'Using change: <name>' and how to override (e.g. `/openspec-apply-change <other>`)" | auto-select works as is — `openspec list --json` returns exactly one change (verified, `cli-probe/03`); the ask branch is unreachable but still invites a question; the override hint names slash commands nobody can type | keep auto-select; drop the ask branch and the override hint; the announcement goes with a tool call (G2-7) | env | decided |
| G1-3 | G1 input | `new:40-48,54,87` | schema: default unless the user names one; "show workflows" → `openspec schemas --json` and let them choose | no user to choose; the default already resolves to the configured schema (`config.yaml` `schema:` → `.openspec.yaml` `schema: swe-driven`, verified `cli-probe/03`) | keep the default path; drop the choose-a-schema branch | env | dropped (D-7) |
| G2-1 | G2 hand-off | `new:71-86` | step 6 "STOP and wait for user direction"; closing prompt "Ready to create the first artifact? … or ask me to continue"; guardrails "Do NOT create any artifacts yet", "Do NOT advance beyond showing the first artifact template" | the stop is a text-only reply → the session ends with only a scaffold | "new writes no artifact; once the change exists, open the ff stage document and continue" (`docs/getting-started.md:47` is the next step upstream) | env | dropped (D-7) |
| G2-2 | G2 hand-off | `ff:103-109` | closing summary + "Run `/openspec-apply-change` or ask me to implement to start working on the tasks." | same; the command cannot be typed | "after the last artifact, open the apply stage document and continue" | env | decided |
| G2-3 | G2 hand-off | `apply:66-67` | state `blocked` (artifacts missing) → "suggest using `/openspec-continue-change` to create them" | `continue` is not in the chosen chain and is a slash command | "go back to the ff stage document, create the missing artifacts, then resume apply" | env | decided |
| G2-4 | G2 hand-off | `apply:68,122-128,144-160` | `all_done` / completion: "report … and suggest review or verification as appropriate before archiving"; "You can archive this change with `/openspec-archive-change`" | a report ends the session before verify and archive | "when every task is checked, open the verify stage document and continue" | env | decided |
| G2-5 | G2 hand-off | `verify:196-202` | Final Assessment addressed to the person ("Fix before archiving", "Ready for archive") | upstream the person decides what is next | route on the written report by the round rule (G8-1) | env | decided |
| G2-6 | G2 hand-off | `archive:185-205` | "Display summary" / "Output On Success" | the natural end; whether the rllm engine treats a text-only end differently from `finish` is **(unverified)** | write the summary into the archived change dir, then call `finish` | env | decided |
| G2-7 | G2 hand-off | `ff:82,90`, `apply:38,96-102,107`, `verify:42`, `sync:44,283` | "Show brief progress: ✓ Created <artifact-id>", "Display …", "Show which task is being worked on", "Tell the user", "Show what you're changing as you go" | any message without a tool call ends the session | entry document: progress notes ride along with a tool call or go into the artifacts; no tool-less message before `finish` | env | decided |
| G2-8 | G2 hand-off | `archive:147,213` | "run the `openspec-sync-specs` workflow inline … and wait for it to finish. Do not delegate it to a background task" | the sandbox has no skill loader and no subagents (Terminal / FileEditor / TaskTracker only, `rllm/harnesses/tools/openhands_sdk_runner.py:123-127`) | ship `sync` as a stage document that archive opens at that point; "inline, no delegation" kept | env | decided |
| G3-1 | G3 entry document | none — the person types `/opsx:new`, `/opsx:ff`, … in order (`docs/getting-started.md:47`); upstream calls them "actions, not phases" (`docs/workflows.md:5`) | nothing agent-facing strings the five actions together | `WorkflowSpec.entry_doc` must exist and be named by the instruction and the system prompt (`recipe/grpo/qwen3_5/workflow_harness.py:270-284`) | hand-written `docs/core-workflow.md` (see "New text") | (new text) | decided |
| G4-1 | G4 interactive | `ff:76` | "Identify the target project … If the target is unclear, ask … If source is unavailable, state the limitation and ask when it materially affects the plan" | target and source are always `/testbed`; an ask ends the session | "the target project is `/testbed`"; ask dropped, "state the limitation" kept (in the proposal) | env | decided |
| G4-2 | G4 interactive | `ff:94-96,125` | "If an artifact requires user input (critically unclear context): Ask the user to clarify, then continue"; guardrail "If context is critically unclear, ask the user - but prefer making reasonable decisions to keep momentum" | ask = end | take the most plausible reading, record it as an assumption in the artifact being written, continue (ff's own preference made absolute) | semantic | decided |
| G4-3 | G4 interactive | `schema:182-187` (design `instruction`), `schema:205-207` (tasks `instruction`) — served verbatim by `openspec instructions design|tasks` | design Open Questions: "If a question would change the specs, the chosen approach, or the task breakdown, resolve it now - ask the user instead of guessing"; tasks: "If any of them would change what gets built, resolve them with the user first - do not bake an unstated assumption" | no user; the CLI serves this text, so a stage-document edit cannot remove it | edit the **forked schema** (see "Sandbox setting"): resolve it yourself, write the choice and its rationale under **Decisions**, keep Open Questions for deferrable unknowns only | semantic | decided |
| G4-4 | G4 interactive | `apply:116,185,189`; `schema:270-272` (apply `instruction`, served by `openspec instructions apply`: "Pause if you hit blockers or need clarification", verified `cli-probe/02`) | task unclear → "ask for clarification", "pause and ask before implementing", "don't guess" | pause = end | stage document and forked schema: take the most plausible reading against specs/design, note it under the task in `tasks.md` (plain line, not a checkbox), implement | semantic | decided |
| G4-5 | G4 interactive | `apply:117,186,205` | implementation reveals a design issue → "suggest updating artifacts" / "pause and suggest artifact updates" | a suggestion to a person = end | update the affected artifact yourself, record what changed and why, continue (upstream "not phase-locked, work fluidly", `apply:205`) | semantic | decided |
| G4-6 | G4 interactive | `apply:118,190-191` | work beyond the spec/tasks, or a pull to "drop, narrow, defer, or accept exceptions" → "surface the added scope and ask; do not absorb it silently" | ask = end | add the extra work as tasks in `tasks.md` (and to the delta spec when observable), then do it; never narrow specified behavior | semantic | decided |
| G4-7 | G4 interactive | `apply:119-120,128,162-180` | error or blocker → "report and wait for guidance"; "User interrupts"; Output On Pause with options + "What would you like to do?" | waiting = end; no interrupts exist | try to resolve; if a task stays impossible, leave it unchecked with a one-line reason and continue with the rest; interrupt and pause blocks dropped | semantic | decided |
| G4-8 | G4 interactive | `archive:81-84,103-106,210` | incomplete artifacts or tasks → "Display warning … Ask the user to confirm they want to proceed"; "Don't block archive on warnings - just inform and confirm" | confirm = end; the change is never archived | proceed and list the warnings in the archive summary | semantic | dropped (D-5) |
| G4-9 | G4 interactive | `archive:127-136` | sync choice: blocked → "Archive without syncing" / "Cancel"; needs sync → "Sync now (recommended)" / "Archive without syncing"; synced → "Archive now" / "Sync anyway" / "Cancel"; otherwise ask again | only a person picks | fixed routing: needs sync → Sync now (upstream's recommendation); blocked → Archive without syncing; synced → Archive now; never Cancel | semantic | dropped (D-5) |
| G4-10 | G4 interactive | `archive:96-99,149-151,166`; `sync:72-75,83,93-94` | lookup / validation / sync failure → "report the problem and stop before syncing or archiving … the user can fix … and start the archive again" | a stop leaves the change unarchived; with the CLI present these failures are possible (e.g. `openspec validate` rejecting a main spec) | fix the main spec once and re-check; if it still fails, archive without syncing and record why | semantic | dropped (D-5) |
| G4-11 | G4 interactive | `sync:144-153,282` | retirement blocked → "tell the user how to resolve it"; "If something is unclear, ask for clarification" | ask = end; retirement cannot arise on an empty main-spec tree (G7-4) | retirement paragraphs dropped; unclear merge → most plausible merge, recorded in the archive summary | semantic | dropped (D-5) |
| G4-12 | G4 interactive | `new:85-86` | name not kebab-case → "ask for a valid name" | unreachable with a fixed valid name (G5-1) | dropped | env | dropped (D-7) |
| G5-1 | G5 paths & IDs | `new:36`, `ff:36`; name rules `src/utils/change-utils.ts:67-97` | derive a kebab-case change name from the description (`add-user-auth`) | stage documents and a scorer need one predictable name; the archive dir is `<date>-<name>` | fixed name `issue` | env | decided |
| G5-2 | G5 paths & IDs | (rllm side) | — | the planning root is `/openspec` (Sandbox setting), so the documents need another directory, outside the repo; late entry-doc reads mis-resolve under `/testbed` (lessons "Doc path misresolution") | documents at a filesystem-root directory, e.g. `/opsx` (Q2) | env | decided |
| G5-3 | G5 paths & IDs | `verify:161-219` | the verification report is a chat message, never a file | a message ends the session and leaves nothing to route on or score | write `verify.md` (round 2: `verify-2.md`) into `/openspec/changes/issue/`, archived with the change (Q3) | env | decided |
| G6-1 | G6 network | `schema:18` ("Impact: … dependencies"), `schema:245` (example "Add dependencies to package.json and verify package installation succeeds") | nothing tells the agent to fetch, but installs are suggested | tasks run with `allow_internet = true` and issue links point at the fix PR (lessons "Leaks"); CLI telemetry and update check are switched off by the setting | entry document: no fetching links in the issue, no looking anything up online, no installing packages | semantic | decided |
| G7-1 | G7 machinery | `ff:40-44`, `ff:126` | ff step 2 runs `openspec new change "<name>"`; guardrail "If a change with that name already exists, suggest continuing that change instead" | after `new`, the call fails — `✖ Error: Change 'issue' already exists` (exit 1, verified `cli-probe/03`) — and the guardrail hands back to a person | ff step 2 → "the change was created by the new stage; continue it"; guardrail line dropped | env | decided |
| G7-2 | G7 machinery | frontmatter of every skill (`allowed-tools: Bash(openspec:*)`, `compatibility: Requires openspec CLI.`, `metadata.generatedBy`) | agent-app metadata | no agent app reads it | strip (`Port.frontmatter`, `workflows/_port.py`) | env | decided |
| G7-3 | G7 machinery | **Store selection** paragraph in all six (`new:14` … `sync:16`; `src/core/templates/workflows/store-selection.ts:7`) | `openspec store list --json`, sticky `--store <id>` | works: returns `{"stores": [], "status": []}` (verified); costs a call per stage and describes a feature the setting never uses | keep verbatim or drop (Q7) | env | decided |
| G7-4 | G7 machinery | MODIFIED / REMOVED / RENAMED and retirement branches: `schema:96-100,126-133`; `verify:103-117,121`; `archive:119-123`; `sync:109-114,122-160` | delta operations against existing main specs | `/openspec/specs/` starts empty in every sandbox, so only `## ADDED Requirements` of a new capability can apply; a MODIFIED delta is sync-blocked (`archive:120`) | state once that every delta is ADDED for a new capability; keep the dead branches verbatim or trim them (Q7); bug fixes and `skip_specs` → Q5 | env | decided |
| G8-1 | G8 loops & ends | `verify:161-202`, `verify:61` (verify never implements) | CRITICAL ("Must fix before archive": incomplete tasks, requirement not found) / WARNING / SUGGESTION; the person decides | nobody reads it; upstream's loop is the person running apply again | rounds: CRITICAL in `verify.md` → back to apply for those issues, then `verify-2.md`; at most 2 verify rounds, then archive regardless with what is left recorded; WARNING/SUGGESTION do not loop (Q3) | loop | decided |
| G8-2 | G8 loops & ends | `apply:104-113,183`; every CLI step | per task: edit, flip the checkbox, rerun `openspec instructions apply`; plus `status`/`instructions` per artifact | one session, `agent_step_limit: 150` (`recipe/grpo/qwen3_5/config/config.yaml:68`); the chain plus the CLI calls is longer than speckit_bug's 55–114 steps (**unverified** count) | no change; measure in the smoke | env | decided |
| G8-3 | G8 loops & ends | `archive:168-183` | archive moves the change into `changes/archive/` and updates the project's main specs | the session ends right after; nothing the verifier grades changes; the files survive only as collected outputs (`recipe/grpo/qwen3_5/run_artifacts.py`) | keep as the last stage (user's choice), then `finish`; the entry document says the repo change must be complete before archive | env | decided |
| G8-4 | G8 loops & ends | `src/core/archive.ts:1540-1567` (validation), `:1849` (`archive_spec_update_failed`) | `openspec archive` exits 1 on delta-spec validation errors ("Please fix the errors before archiving") or a failed merge (e.g. MODIFIED against an empty main spec) | found in stage 3 with D-5: the agent runs the archive and must know what to do on exit 1; nobody fixes it for them | fix only what the error names in the delta spec (or write the missing spec), rerun once; still failing → `finish` without archive; no `--no-validate`; no return to tasks/apply | semantic | decided |
| G9-1 | G9 task conflicts | `schema:225-236,249-250` (tasks `instruction` and example) | "Each task MUST state how to verify completion (a test …)"; "Each task group MUST land the tests … its own work calls for"; example "verify unit tests cover quoting and delimiters" | the task text says the test files are already handled and not to be changed (`scripts/prepare_swegym.py:177`); hidden tests grade | forked schema: verification = running existing repo tests or a check script under `/openspec/changes/issue/checks/`; no test files added or edited in `/testbed` | semantic | decided |
| G9-2 | G9 task conflicts | `schema:230-236,251` | "… land the tests and documentation its own work calls for"; example "Document the export API in docs/export.md" | "minimal changes to non-test files" (`scripts/prepare_swegym.py:179`); doc edits widen the patch | forked schema: no documentation changes unless the issue asks for them | semantic | decided |
| G9-3 | G9 task conflicts | `verify:132-138` | scenario coverage: "Check if tests exist covering the scenario"; WARNING "Scenario not covered" → "Add test or implementation for scenario" | adding repo tests conflicts with the task text; the hidden test for the issue is not in the repo yet, so most scenarios read "uncovered" | coverage = the code path handles it and a check ran; recommendation "add a check under `checks/` or fix the code" | semantic | decided |
| G9-4 | G9 task conflicts | `schema:172,245` | design section for "New external dependency"; example task "Add dependencies to package.json …" | the environment is fixed (`/opt/miniconda3/envs/testbed`); installs need the network (G6-1) | forked schema: no new dependencies; example replaced or kept (Q7) | semantic | decided |
| G10-1 | G10 harness & dataset | SDK default `<PROBLEM_SOLVING_WORKFLOW>` | prescribes its own procedure | outranks an instruction in the user message (lessons) | `system-prompt.j2` with the procedure section written fresh for this workflow | — | decided |
| G10-2 | G10 harness & dataset | SDK prompt lines ~48 "ask the user for clarification", ~171 "confirm with the user before proceeding" | ask / confirm | contradict "nobody is waiting" | keep for comparability with `none` / aidlc_v4 / speckit_bug, or drop (Q6) | — | decided |
| G10-3 | G10 harness & dataset | SWE-Gym default prompt's six-step procedure (`scripts/prepare_swegym.py:103-153`) | competes with the workflow | with the instruction as suffix, 86% never opened the workflow (lessons) | `swegym293_aidlc` + `instruction_position: prefix` | — | decided |
| G10-4 | G10 harness & dataset | instruction | — | late entry-doc reads mis-resolve under `/testbed` (speckit_bug smoke 3/10) | the instruction makes reading `<docs dir>/core-workflow.md` the first action and says the directory is at the filesystem root, outside the repo | — | decided |
| G10-5 | G10 harness & dataset | (rllm side) the CLI in the sandbox | — | neither task images nor the openhands-sdk agent image carry node (verified) | see "Sandbox setting" (a)–(c) | — | decided |
| G10-6 | G10 harness & dataset | (rllm side) the agent's terminal is a TTY; `src/utils/interactive.ts:25-31` | with a TTY on stdin and no `CI` in the environment the CLI runs interactive: `openspec new change issue` creates the change, then leaves its spinner up and never exits | found in stage 6: 9/10 smoke rollouts hung on that call until the 3600 s agent timeout (reproduced under `script -qec`: 15 s timeout without `CI`, 0.9 s with `CI=1`); the probes ran without a TTY and missed it | the `openspec` wrapper in `setup.sh` sets `CI=1` (upstream's own non-interactive switch: prompts error out instead of waiting; telemetry, update check and completion tip also off); setup checks a TTY run returns | env | decided |
| G7-5 | G7 machinery | `schema.yaml` proposal `instruction` (Capabilities: "Modified Capabilities … existing capabilities whose REQUIREMENTS are changing") and specs `instruction` (MODIFIED / REMOVED / RENAMED formats), served by the CLI | the agent describes a bug fix or a change to existing code as a *modified* capability and writes `## MODIFIED Requirements` | found in stage 6 run 2: the first `openspec archive` failed with "MODIFIED/REMOVED/RENAMED operations require an existing spec" in 6/8 archiving rollouts (think on 4/5, off 2/3); the entry document's "every delta is ADDED" did not reach the moment of writing the spec | forked schema: one sentence in the proposal Capabilities item and in the specs instruction stating that this project has no existing specs (`/openspec/specs/` is empty), so every capability goes under New Capabilities with an `## ADDED Requirements` delta | env | decided |
| G8-5 | G8 loops & ends | entry document "Archive, Then Finish" (G8-4 rule) | — | found in stage 6 run 2: archive called 3–6 times in 4/8 archiving rollouts; 2 (think on) deleted the delta specs and set `skip_specs: true` to get past validation — against upstream's "Use `skip_specs: true` only when no spec-level behavior changes" (`schema:36-42`) and G8-4 "correct only what the error names" | mostly downstream of G7-5; re-check after it, or restate the limit in the archive step | env | deferred |
| G2-9 | G2 hand-off | entry document "Actions" table, apply → verify pointer (G2-4) | — | found in stage 6 run 2: of the rollouts that archived, verify.md exists in 1/3 (think off) and 4/5 (think on); think off 2238 never opened `04-verify.md`, 7365 read it ahead at step 4 and wrote none | entry document: archive only once `verify.md` (or `verify-2.md`) exists | env | decided |
| G7-6 | G7 machinery | forked schema specs `instruction` (after G7-5); upstream MODIFIED guidance kept (Q7) | the agent writes the corrected behavior as ADDED **and** a `## MODIFIED Requirements` section describing the old, wrong behavior | found in stage 6 run 3: think on 5/5 first specs still had MODIFIED (4/4 first archives failed) although each agent read the G7-5 sentence first; think off fixed (0/3 failures) | options: (a) one more sentence naming the pattern — do not add MODIFIED/REMOVED to describe what the code did before; the corrected behavior alone is the ADDED requirement; (b) trim the MODIFIED/REMOVED/RENAMED format text from the fork (reverses Q7); (c) accept: every run recovered to ADDED-only and archived | env | decided |
| G10-7 | G10 harness & dataset | `docs/existing-projects.md:126` ("Give the AI context … fill in `openspec/config.yaml`'s `context:`"); `docs/customization.md` Project Configuration (context in every artifact and in apply/archive instructions, `rules` per artifact) | upstream's own channel for project facts and constraints; `setup.sh` leaves `config.yaml` with init's commented template | found in review 2026-10-14: our environment facts sit in the entry document (read once, at step 0) and in fork-schema text (G7-5); runs 2–3 showed facts not reaching the moment they apply (G7-5, G2-9) | (a) `setup.sh` writes a short `context:` (repo `/testbed`, tests already in place, no installs/network, checks dir, specs start empty) and `rules` for proposal/specs (G7-5's sentences move there from the fork; the fork keeps only edits that must delete upstream text); watch apply/verify's "context or guidance conflicts → report and explain" branches; (b) keep as is | env | decided |

## Upstream text that works as is in this setting

Verified with the CLI in a task image (`cli-probe/`); no edit needed:
- The **project-root guard** in all six skills (`src/core/templates/workflows/project-root.ts:28-37`):
  `openspec list --json` reports `"root": {"path": "/", "source": "nearest"}` from `/testbed`, so the
  stop-and-ask branch never fires.
- Every path the skills take from CLI JSON (`planningHome`, `changeRoot`, `artifactPaths.*`,
  `resolvedOutputPath`): all under `/openspec/changes/issue/`.
- `openspec status --change --json` (artifact states, build order), `openspec instructions <artifact>`
  (instruction + template), `openspec instructions apply` (context files, checkbox progress, `ready` →
  `all_done`), `openspec instructions archive|specs` (advisory lookups), `openspec validate --strict`
  (delta format), `.openspec.yaml` flags, and the archive target `changes/archive/<date>-issue/`.
- ff's "if the instruction delegates to a skill, invoke it" (`ff:79,114`) — spec-driven delegates nothing.
- ff's todo list (`ff:57`) — `TaskTrackerTool` is registered (`openhands_sdk_runner.py:126`).
- apply's "Keep changes minimal and focused" (`apply:109,187`) agrees with the task text.

## Sandbox setting (what rllm must provide)

Verified offline (`--network none`) in `xingyaoww/sweb.eval.x86_64.getmoto_s_moto-7365` (Ubuntu 22.04,
glibc 2.35) and `debian:bullseye-slim` (glibc 2.31); probes and the bundle recipe in `cli-probe/`.

- **(a) node + CLI.** node v22.23.3 + `@fission-ai/openspec@1.14.1` (138 MB) runs on glibc 2.31–2.35;
  needs only libstdc++/libgcc_s, present in the images. Delivery: a separate content-addressed agent
  image that adds the bundle to the openhands-sdk one, used only when the workflow asks for it (D-2);
  the tag is hashed from the install script alone (`rllm/sandbox/agent_image.py:46-49`), so the recipe
  must change the hashed text.
- **(b) setup step before the agent**, as root:
  1. `cd / && openspec init --tools none` — creates upstream's `openspec/{config.yaml, specs/,
     changes/archive/}`. An empty `/openspec/` is **not** recognized as a root (`no_openspec_root`).
     The root is "nearest ancestor of cwd holding `openspec/`" (`src/core/planning-home.ts:59-89`), so
     it is found from `/testbed`, `/tmp`, anywhere.
  2. the forked schema: upstream's customization mechanism is a project-local schema
     (`openspec schema fork spec-driven <name>` → `openspec/schemas/<name>/`, `docs/customization.md:165-192`),
     selected by `config.yaml` `schema:`. Verified: with `schema: swe-driven`, `new change` records
     `schema: swe-driven` and `instructions design` serves the edited text. The fork's edits (G4-3, G4-4,
     G9-1, G9-2, G9-4) are tagged `Edit`s in `build.py` on `schema.yaml`; the built fork ships with the
     package (outside `docs/`) and is copied to `/openspec/schemas/<name>/` at setup.
  3. an `openspec` wrapper on `PATH` that sets `OPENSPEC_TELEMETRY=0` and `OPENSPEC_NO_UPDATE_CHECK=1`
     (`src/core/version-check.ts:36-38`) and runs the bundled CLI.
- **(c) `WorkflowSpec`** fields for (a) and (b), and `output_dirs=("/openspec",)` so the planning tree is
  collected (`recipe/grpo/qwen3_5/workflows/spec.py`, `run_artifacts.py`).
- Throughout the probes `git -C /testbed status --porcelain` stayed empty and nothing was written under
  `$HOME`. The agent runs as root in these tasks (`agent_user` unset).
- Risk: a repository with its own `openspec/` directory would be found first (none in the three images
  checked; a setup-time check can fail the rollout if `/testbed/openspec` exists).

## New text the port must write

- `docs/core-workflow.md`: the five stages in order (document to open, what each produces); input =
  the issue; nobody is waiting (no question, no tool-less message before `finish`, assume and record);
  fixed names (change `issue`, planning root `/openspec`, checks dir); the verify ↔ apply round rule;
  archive last, then `finish`; no fetching / online lookups / installs; no test or documentation edits
  and no stray files in `/testbed`.
- Stage documents for new, ff, apply, verify, archive and sync, from the skill renders, edited per the
  rows above.
- The forked schema (`schema.yaml` + four templates), edited per G4-3, G4-4, G9-1, G9-2, G9-4.
- `instruction.md` and the system prompt's procedure section, written fresh (lessons "Generalization").
- `__init__.py`, `build.py`, the MIT notice (`LICENSE`, "Copyright (c) 2024 OpenSpec Contributors").

## Open questions for the user

1. Fork schema name (e.g. `swe-driven`) and the checks directory (`/openspec/changes/issue/checks/`).
2. Names: documents directory (e.g. `/opsx`); workflow name `openspec_ff` or one naming the full chain
   (e.g. `openspec_opsx`).
3. Verify rounds (G8-1, G5-3): loop on CRITICAL only, at most 2 rounds? `verify.md` / `verify-2.md`
   inside the change dir?
4. Archive (G4-8, G4-9, G4-10): fixed routing and archiving with warnings recorded — OK?
5. Specs for bug fixes (G7-4): always an ADDED delta for a new capability (upstream: specs whenever
   behavior changes), or allow `skip_specs: true` for fixes?
6. SDK "ask the user" / "confirm with the user" lines (G10-2): keep for comparability, as in speckit_bug?
7. Text that never applies here (G7-3 store paragraph, G7-4 MODIFIED/REMOVED/RENAMED and retirement,
   G9-4 package.json example): keep verbatim or trim?

## Sources read

| File | Lines |
|---|---|
| `skills/openspec-new-change/SKILL.md` | 87 |
| `skills/openspec-ff-change/SKILL.md` | 127 |
| `skills/openspec-apply-change/SKILL.md` | 205 |
| `skills/openspec-verify-change/SKILL.md` | 219 |
| `skills/openspec-archive-change/SKILL.md` | 220 |
| `skills/openspec-sync-specs/SKILL.md` | 289 |
| `schemas/spec-driven/schema.yaml` | 272 |
| `schemas/spec-driven/templates/{proposal,spec,design,tasks}.md` | 34 + 13 + 21 + 11 |
| `src/core/templates/workflows/{project-root,store-selection,new-change,ff-change}.ts` | 37 + 7 + 178 + 263 |
| `src/core/templates/workflows/{apply-change,verify-change,archive-change,sync-specs}.ts` | compared to the renders |
| `src/core/planning-home.ts`, `src/core/version-check.ts`, `docs/customization.md`, `docs/agent-contract.md` | relevant parts |

## Explore extension (stage 2, 2026-10-15)

Scope: upstream's **explore** stage added before ff in the same session (user, 2026-10-15). Already decided
by the user and not reopened here: the position (explore → ff → apply → verify → archive) and explore's
no-code rule kept as upstream has it. Upstream checked at `9111a7654d7800391459431fff4eaf66e33a3d2e`
(`git rev-parse HEAD`, nothing checked out). Short names as above, plus `explore` =
`skills/openspec-explore/SKILL.md` (committed render, 353 lines) and `explore.ts` =
`src/core/templates/workflows/explore.ts` (skill body `:80-392`, command body `:405-606`).

What the CLI serves for explore at run time: **nothing**. `openspec instructions` serves artifacts and
apply; the only operation ids are `apply`, `archive` (`src/core/project-config.ts:8`); the schema has no
explore entry (`grep -i explore schemas/spec-driven/schema.yaml`: no hit). Explore reads
`<root.path>/openspec/config.yaml` itself (`explore:142-146`), not through `instructions` JSON. So every
edit for explore is a stage-document edit; the fork needs none.

Coupling between explore and the planning actions, as upstream writes it:
- Hand-off target is **propose** (`explore:14,162,318,335,345`; `docs/explore.md:3,89-98`;
  `docs/workflows.md:38-40,115,143`), or `/opsx:new` in the expanded set (`docs/explore.md:104`,
  `docs/commands.md:101`; `docs/workflows.md:202` explore → new → continue). Upstream never pairs explore
  with **ff**; ff is for "Clear requirements" / "If you can describe the full scope upfront"
  (`docs/workflows.md:408-416`). The hand-off lines are optional-workflow conditionals on `propose` /
  `apply` (`explore.ts:40-74`), resolved in the render with every workflow installed.
- Findings travel in the **conversation**: "Track decisions in the conversation, not in files"
  (`explore:53`); "the AI carries the context from your conversation into the artifacts"
  (`docs/explore.md:91,98`); "Creating proposal based on our exploration… [Writes proposal incorporating
  investigation insights]" (`docs/workflows.md:234-235`).
- Writes: only OpenSpec change artifacts, only after a yes/no confirmation in a separate message or the
  person's own capture request (`explore:14,155,349`; `docs/explore.md:30,36`); the capture path runs
  `openspec new change "<name>"` itself (`explore:157`). Code: never, "on any path, capture included"
  (`docs/explore.md:34`).

| ID | Type | Upstream location | What the text does | Why it breaks in rllm (evidence) | Proposed handling | Tag | Status |
|---|---|---|---|---|---|---|---|
| G1-4 | G1 input | `explore.ts:415-420` (command variant only: "The argument after `/opsx:explore` is whatever the user wants to think about … Nothing (just enter explore mode)"); skill: `explore:70` "Depending on what the user brings", entry points `explore:210-310` | input = whatever the person brings; the skill render states no input | the only input is the issue (`scripts/prepare_swegym.py:166-180`); nobody brings anything more | add "**Input**: the issue in `<issue_description>`: the problem to understand" — upstream's entry point "User brings a specific problem" (`explore:235-264`) (P2). precedent: openspec_ff G1-1 | env | decided |
| G2-10 | G2 hand-off | `explore:14` ("point them at `/openspec-propose`"), `:162` ("stop there and name where the work continues: `/openspec-propose` … `/openspec-apply-change` …"), `:318`, `:335`, `:345` ("name the handoff rather than starting") | explore never moves on by itself; it names the next command for the person, and that command is propose | "stop and name" = a text-only reply = end (lessons); propose is not shipped and `/openspec-` is in `FORBIDDEN` (`build.py:80`; 7 hits in `explore`, counted); the render's "propose not installed" fallbacks are offers to the person (`explore.ts:43,49,61,67,73`) | every hand-off → "when exploration is done (G8-6), open `/opsx/stages/01-ff.md` and continue: ff writes the planning artifacts from what you found". ff stands in for propose: same artifact loop in one go (`01-survey.md:185-187`); the user fixed the order (P2). precedent: openspec_ff G2-2 | env | decided |
| G2-11 | G2 hand-off | `explore:12,37,90-109,351` (visualize, ASCII diagrams), `:48` "Summarize relevant findings", `:160` "Tell the user about a deliberate conditional skip", `:206` (need not "Be brief"), `:323-339` summary | explore's whole output is prose and diagrams addressed to the person | a message without a tool call ends the session (lessons); explore writes no file, so all its output is message text — more tool-less temptation than any other stage | the rule the other stages already follow (`core-workflow.md:49-50`): every note, diagram and summary rides in a turn that also makes a tool call (P2). precedent: openspec_ff G2-7 | env | decided |
| G2-12 | G2 hand-off | `explore:53` ("Track decisions in the conversation, not in files"); `docs/explore.md:91,98`; `docs/workflows.md:234-235`; optional summary `explore:323-339` | findings reach the proposal through the conversation; nothing is written unless the person says yes (`docs/explore.md:36`) | the context does survive (one session, no condenser, `06-smoke.md:3`), but leaves nothing checkable (P3), and core-workflow's "write the assumption into the artifact at hand" (`core-workflow.md:51-53`) has no artifact during explore | options: (a) conversation only, upstream as is; (b) upstream's "What We Figured Out" summary (`explore:325-337`) made always, written in the turn that opens the ff document; ff grounds proposal/design in it (P2: upstream's own output; P3: always); (c) a file — departs from `explore:345` and `docs/explore.md:36`; (d) capture path — see G4-13 (b). Proposed (b). → Q-E2 | semantic | decided |
| G2-13 | G2 hand-off | ff `:74-78` (port `01-ff.md:56-60`): "re-read them from disk … (the user may have edited them)"; "Inspect the relevant project before drafting … reuse findings for later artifacts and inspect more only as needed"; "Distinguish observed behavior from assumptions" | ff runs its own discovery before each artifact and reuses what it found | after explore, "findings" include explore's; a literal agent may count explore as ff's discovery and draft the proposal at once, so the commitment point (proposal/design) is still the end of investigation, now fed by explore's conclusion (unverified for explore; in openspec_ff runs investigation nearly stopped after the proposal, user's analysis) | keep ff verbatim: upstream's own explore → propose path meets the same discovery text (`skills/openspec-propose/SKILL.md:123`, same lines as ff) (P2); measure ff's inspection after explore in the smoke. Alternative: one sentence in core-workflow (Q-E3) | env | decided |
| G3-2 | G3 entry document | none: upstream draws explore as optional before propose (`docs/workflows.md:38-40,115`) | — | `core-workflow.md:7` (chain), `:15-22` (actions table) and `:62` ("Only the apply action edits `/testbed`. ff and verify read it and run commands in it") name ff → archive only | explore becomes the first action: table row (open the explore document; starts from `openspec list --json`, `explore:126`; leaves: nothing on disk, the findings summary per G2-12); chain line `explore ──► ff ──► …`; the read-only line names explore with its no-code rule (G9-5) (P2). precedent: openspec_ff G3-1 | (new text) | decided |
| G4-13 | G4 interactive | `explore:14` ("Before the first write-capable action, name the artifacts or files … ask a direct yes/no question, and wait for the user's confirmation in a separate message"), `:349` (same, "including `openspec new change`"), `:53` ("Silence is not acceptance"), `:150-152` (offer "Want me to create a proposal?"), `docs/explore.md:36` | explore writes nothing on its own; a write needs a yes in a separate message, or the person's own capture request (`explore:14` last sentence, `:155`) | nobody answers: the offer or the yes/no question ends the session (lessons); the yes never arrives | (a) explore writes nothing — upstream's outcome when no yes comes ("Silence is not acceptance"); the offer and the yes/no question dropped; ff creates the change as now (P2, P4). (b) core-workflow acts as the person's capture request, scope "scaffold the change" — then ff step 2 `openspec new change "issue"` exits 1 "already exists" (`02-gaps.md:51`, verified `cli-probe/03`), against D-7. Proposed (a). → Q-E5 | semantic | decided |
| G4-14 | G4 interactive | `explore:12` ("Follow the conversation"), `:35-36`, `:46-55` (focused discovery questions, one at a time), `:73`; `:52` ("Do not invent intent, priorities, or external constraints: ask the user when only they can answer"); `:48` ("state that limitation and ask only for the clarification needed"); dialogs ending in a question `:232,263,287,309` | the person's answers fix scope and intent | ask = end (lessons); the issue is the only statement of intent | keep `:48`'s investigation rule verbatim ("Before asking a factual question … inspect … Do not ask the user to repeat facts you can verify"); a question only the person could answer → take the most plausible reading of the issue, mark it as an assumption (not as confirmed intent) in the summary (G2-12), continue; ff writes it into the proposal (P2). precedent: openspec_ff G4-2, speckit_bug G4-3 | semantic | decided |
| G4-15 | G4 interactive | `explore:52` ("state your preferred option and why … with alternatives and their tradeoffs"), `:55` ("Let them pause, pivot, or defer a decision"), `:84-88` ("Recommend a path (if asked)"), `:114` ("Suggest spikes or investigations"), `:195` ("The user decides"); `docs/explore.md:70-79` (the person picks the option) | explore lays out options; the person chooses | nobody chooses; a suggestion to a person is an end | the agent states its preferred option with the alternatives and reasons (`:52`'s own format) and carries it to ff, where design.md **Decisions** records choice, rationale and alternatives (G4-3 as decided; `tpl/design.md:15-17` "decisions with rationale and alternatives considered"); a suggested spike → a specific open question for ff's discovery (`ff:78` "Keep any necessary follow-up investigation specific to an unresolved question") (P2). precedent: openspec_ff G4-3 | semantic | decided |
| G4-16 | G4 interactive | `explore:14` ("If the user asks you to implement something, do not start it here: say that explore mode does not implement, and point them at `/openspec-propose`"), `:345` | refuse in words and name the command | the task message itself asks to implement ("Can you help me implement the necessary changes…", `scripts/prepare_swegym.py:176`) and the instruction says to solve it (`instruction.md:1`); a literal reading replies with a text-only refusal → end | explore document: the task's request to implement is carried out by ff → apply later in this session; explore does not start it and, when done, opens the ff document (G2-10) (P2) | env | decided |
| G4-17 | G4 interactive | `explore:150-162` (capture transition: "ask before expanding the capture" `:158,160`, "stop after scaffolding and show its status" `:162`), `:164-195` ("When a change exists": offers, "The user decides"), `:266-281` (mid-implementation example) | branches for a person who asks to capture, or for a change already in flight | before ff no change exists (ff creates it, D-7); under G4-13 (a) capture is never entered; their asks/stops would end the session; mid-change explore (`docs/explore.md:112`) is outside the decided order | drop both branches (unreachable; ask/stop text) (P4). precedent: openspec_ff G1-2 (unreachable ask branch dropped). Under G4-13 (b): keep the capture transition, scaffold only, and change ff step 2 | env | decided |
| G4-18 | G4 interactive | `explore:210-310` ("Handling Different Entry Points": four dialogs ending on a question to the person — "Where's your head at?", "Which one's burning?", "Want to update the design…?", "What's the context?"); `explore:199-206` ("What You Don't Have To Do") | illustrations of the stance | they model ending a turn on a question; a question without a tool call ends the session (lessons); whether Qwen3.5 imitates them is (unverified) | (a) keep verbatim, G2-11 covers it; (b) keep only "User brings a specific problem" (`:235-264`, the one an issue matches) without its closing question; (c) drop all (P4). Related: speckit_sdd G7-7 (examples that do not apply deleted). → Q-E6 | semantic | decided |
| G5-4 | G5 paths & IDs | (rllm side) `/opsx/stages/01-ff.md` … `03-verify.md` (`build.py:50-61`) | — | the new stage needs a document path; renumbering touches `STAGE_DOCS`, the G2-3/G2-4 edit texts (`build.py:212,221,276`), tests and README | (a) `00-explore.md` (nothing renumbered); (b) renumber 01-explore … 04-verify as D-7 did. If any capture text stays, the `"<name>"` → `"issue"` substitution (`build.py:407-410`) covers its 9 hits (P3). precedent: openspec_ff D-7, G5-2 | env | decided |
| G7-7 | G7 machinery | `explore:18` (Store selection; `explore.ts:86`) | sticky `--store <id>` | no store is registered (G7-3) | dropped by the existing `_STORE` edit applied to every source (`build.py:134`); `explore:18` matches it exactly once (checked) (P4). precedent: openspec_ff G7-3/Q7 | env | decided |
| G7-8 | G7 machinery | `explore:1-10` (frontmatter `allowed-tools`, `compatibility`, `metadata`) | agent-app metadata | no app reads it | strip (`Port.frontmatter`). precedent: openspec_ff G7-2 | env | decided |
| G7-9 | G7 machinery | `explore:122-146` ("Check for context": `openspec list --json`, `openspec list --specs` (+`--json`), `openspec show "<spec-id>" --type spec …`, then read `<root.path>/openspec/config.yaml` directly) | inventory of active changes and capabilities, then the project's `context` and `rules` | `/openspec/specs/` starts empty (G7-5), so `list --specs` lists nothing and `show` has no id; what `list --specs` prints on an empty tree, and under the TTY with `CI=1`, is (unverified) — no node on this host, not probed; config.yaml is read raw, so explore sees `context` and both `rules` entries (`sandbox/openspec-config.yaml`), told they apply "only when you write that artifact" (`explore:144`) | keep verbatim (upstream machinery, P5); probe `openspec list --specs` / `--specs --json` under `script -qec` with the wrapper before the smoke (lessons "CLIs inside the sandbox") | env | decided |
| G8-6 | G8 loops & ends | `explore:16` ("a stance, not a workflow … no fixed steps, no required sequence, no mandatory outputs"), `:199-206` (need not "Reach a conclusion"), `:314-321` ("There's no required ending": proposal / artifact updates / just clarity / continue later), `:39` ("Patient"), `:347` ("Don't rush"), `:55` ("Stop asking when the user has enough clarity") | the person ends explore by typing the next command | one session, `agent_step_limit: 150` (`config/config.yaml:68`); ff → archive took 53–111 steps in the smoke (`06-smoke.md:36,94`), 71 on average in the val ablation (`06-smoke.md:119`); with no end condition explore may run into the limit with no patch, or end at once with nothing explored | (a) end condition from upstream's crystallization summary: explore ends once "The problem" and "The approach" (`explore:327-330`) can be stated from what was read and run ("Open questions" may stay open); of the four endings only "flow into a proposal" applies (P4); (b) (a) plus a stated step cap (no upstream counterpart; P3 checkable); (c) no condition. Proposed (a). → Q-E4 | semantic | decided |
| G9-5 | G9 task conflicts | `explore:14` ("run read-only commands or tools without confirmation, but you must NEVER write code"), `:345` ("Creating or updating OpenSpec change artifacts … is fine, writing anything else is not"), `:349` ("Read-only commands and tools need no confirmation. Before the first write-capable action—including `openspec new change` or another command that writes files…"), `:114` ("Suggest spikes"), `docs/explore.md:26,34` | no code written; read-only commands run freely; the text draws the operational line at commands that write files | the agent's own runs are the only check of behavior here (principles, standing fact); the baseline ran code 7.0× before its first edit vs 3.1× before design in openspec_ff (user's analysis); the port sends reproduction scripts to `checks/` (`core-workflow.md:34`, config `context`), a file explore may not write. The rule stays (user decision); the open point is the boundary | literal line from `:349`: a command is read-only when it writes no file. Allowed: read, grep, run existing tests and existing code, run the issue's own example as given. Not allowed: create or edit any file (repo, `/tmp`, `checks/`), incl. shell redirection or heredoc into a file. Not settled by the text: agent-composed `python -c` / stdin snippets ("NEVER write code" vs "read-only command") → Q-E1 (P1, P2; P3: "no file written during explore" is checkable from the trajectory) | semantic | decided |
| G10-8 | G10 harness & dataset | `instruction.md:1-2` ("taken through ff, apply, verify and archive"); `system-prompt.j2:61-63` ("planned in artifacts, implemented, verified and archived"), `:68-71` | — | both name the chain without explore; an agent going by them may open ff first | rewrite both to name explore first (fresh text, lessons "Generalization"); keep the first action = open `/opsx/core-workflow.md` (G10-4) (P5). precedent: openspec_ff G10-1, G10-4 | — | decided |
| G10-9 | G10 harness & dataset | (rllm side) `sandbox/openspec-config.yaml` `context:` "Scripts written to reproduce or check behavior live in /openspec/changes/issue/checks/" (G10-7); `core-workflow.md:34` | — | explore reads config.yaml itself (`explore:142-146`), so the line reaches explore and points at a script it may not write, in a directory that does not exist before ff's `openspec new change` | (a) keep: a fact, true from ff on; the explore document says scripts start with ff (G9-5); (b) reword to "From the ff action on, scripts …" — G10-7 kept config to plain facts (P3) | env | decided |
| G4-19 | G4 interactive | `explore:57-64` ("For example, after inspecting the relevant code:" — a message that states what the code shows, then asks "Is sharing state across devices in scope? That determines whether local storage is enough.", then gives a conditional recommendation "If this stays a single-device tool, I recommend keeping SQLite …") | the one worked example of "Planning a Change" (`explore:44-64`): inspect first (`:48`), then ask the person the scope question only they can answer, with a grounded recommendation (`:52`) | found in stage 4 (2026-10-15): no row cites `:57-64` (G4-14 covers `:46-55`, G4-18 the entry-point dialogs `:210-310`). Under G4-14 a question only the person could answer becomes an assumption, but this example models asking it; a question in a message is harmless only when the turn also calls a tool (G2-11), and whether Qwen3.5 imitates the example is (unverified) | options: (a) keep verbatim; the G4-14 rule written beside it turns its question into an assumption; (b) reword the example so the scope question becomes a stated assumption with the same inspect-then-recommend shape (`:52`'s format, G4-15); (c) drop it, as G4-18 dropped three examples. Closest precedent: G4-18 (an example's closing question rewritten into the decided behavior) | semantic | decided (found in stage 4) |
| G7-10 | G7 machinery | `explore:350` ("**Don't manually scaffold changes** - Never create a new change directory under `openspec/changes/` by hand. Always use `openspec new change "<name>"` (with `--store <id>` when applicable) so required metadata such as `.openspec.yaml` is created before writing artifacts.") | the scaffolding guardrail of the capture path | found in stage 4 (2026-10-15): no row cites `:350`. Under G4-13 (a) explore never scaffolds, so the line cannot fire; after the `"<name>"` → `"issue"` substitution (`build.py:407-410`) it reads "Always use `openspec new change "issue"`" in a document that otherwise says explore writes nothing and ff runs that command | (a) keep verbatim: still true from ff on, no ask or stop in it (like the project-root guard, "Upstream text that works as is"); (b) drop with the capture text it belongs to (G4-17's "unreachable" reasoning; Q7 dropped the no-op store paragraph). Revisit with G4-13 (b) (`later.md`) either way | env | decided (found in stage 4) |
| G9-6 | G9 task conflicts | port `docs/stages/00-explore.md` (G9-5 sentence; `explore:14,345` "NEVER write code") | explore may run existing code, existing tests and the issue's example as given; no composed code, no file | found in stage 6 (run 5, 2026-10-15): composed code run in 7/7 explore runs (`python -c`, `python3 << EOF`), reproduction scripts written to `/tmp` in 1/7 (think-on moto-7365); checked by hand on MONAI-1884 off steps 14-15, moto-7365 on steps 21-34 | (a) make the boundary harder to miss in 00-explore.md (e.g. one line in the Stance and in Guardrails naming `python -c` / heredoc-to-python as writing code) and in core-workflow; (b) take G9-5's option (b): any command that writes no file is allowed, composed snippets included (departs from "NEVER write code"); (c) accept and keep measuring | semantic | decided (found in stage 6) |
| G2-14 | G2 hand-off | port `00-explore.md` (G2-12 sentence "write this summary in the same turn as the tool call that opens /opsx/stages/01-ff.md") | the summary rides in the turn that opens ff | found in stage 6 (run 5): 5/6 summaries are in a `think` tool call 1–14 turns before ff is opened; 2/4 think-on explore runs wrote no summary | (a) accept: a `think` call is a tool call and stays in the trajectory (the reason for the rule, a text-only turn, does not arise); (b) reword to "in a tool call before you open 01-ff.md"; (c) keep and push harder | env | decided (found in stage 6) |

### G2-12
- 원래 행동: explore에서 알아낸 것(원인, 선택지, 결정)은 파일이 아니라 대화에만 남는다. 사람이 이어서 `/opsx:propose`를 치면 AI가 그 대화 내용을 proposal에 반영한다. 사람이 "저장해" 또는 yes라고 하지 않으면 아무것도 쓰지 않는다.
- 예시: smoke 과제(예: MONAI-2238)에서 explore가 원인 코드를 찾고 두 가지 수정안을 비교했다면, 그 비교는 대화에만 있고 ff가 proposal.md의 Why와 design.md의 Decisions를 쓸 때 대화를 보고 옮겨 적는다. (b)안이면 ff 문서를 여는 tool call과 같은 turn에 "What We Figured Out"(문제·접근·남은 질문) 요약을 매번 남긴다.
- 원문: [explore:53](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L53), [explore:323-339](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L323-L339), [docs/explore.md:89-98](../../../../../../../OpenSpec/docs/explore.md#L89-L98), [docs/workflows.md:232-235](../../../../../../../OpenSpec/docs/workflows.md#L232-L235)

### G2-13
- 원래 행동: ff는 artifact마다 쓰기 전에 관련 코드·테스트를 읽기 전용으로 살펴보고(discovery), 이미 알아낸 것은 다음 artifact에 재사용하며 필요할 때만 더 본다.
- 예시: explore에서 원인 함수를 찾은 뒤 ff에 들어가면, agent가 "이미 찾았다"며 추가 확인 없이 바로 proposal을 쓰고 design에서 원인·범위를 확정할 수 있다. openspec_ff에서 본 계획 고정(plan lock-in)이 explore 결론을 그대로 받아 같은 지점에서 일어날 수 있다는 뜻.
- 원문: [ff:74-78](../../../../../../../OpenSpec/skills/openspec-ff-change/SKILL.md#L74-L78), [propose:123](../../../../../../../OpenSpec/skills/openspec-propose/SKILL.md#L123) (explore → propose 경로에서도 같은 문장)

### G4-13
- 원래 행동: explore는 change artifact(proposal·design·specs)만 쓸 수 있는데, 그것도 쓰기 전에 "무엇을 쓸지" 말하고 yes/no를 물은 뒤 사람의 별도 답을 기다린다. 사람이 먼저 "change로 만들어"라고 요청하면 그 요청이 승인이 된다(capture = 탐색 결과를 change로 저장하는 것).
- 예시: smoke 과제에서 explore가 "proposal 만들까요?"라고 물으면 그 메시지로 rollout이 끝난다. (a)안은 아예 쓰지 않고 ff로 넘어감, (b)안은 진입 문서를 "change 만들어" 요청으로 보고 explore가 `openspec new change "issue"`를 실행 — 그러면 ff 2단계의 같은 명령이 "already exists"로 실패한다.
- 원문: [explore:14](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L14), [explore:150-157](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L150-L157), [explore:349](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L349), [docs/explore.md:36](../../../../../../../OpenSpec/docs/explore.md#L36)

### G4-14
- 원래 행동: 계획 중인 사람에게 한 번에 하나씩 질문해 범위와 의도를 좁힌다. 코드로 확인할 수 있는 사실은 묻지 말고 직접 찾으며, 사람만 답할 수 있는 의도·우선순위는 지어내지 말고 묻는다.
- 예시: issue가 "옵션 X가 무시된다"고만 하고 기본값을 바꿀지 말하지 않으면, upstream은 사람에게 묻는다. 여기서는 issue 문장에 가장 맞는 해석을 고르고 "가정"으로 요약에 표시한 뒤, ff가 proposal에 옮긴다.
- 원문: [explore:46-55](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L46-L55), [explore:35-36](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L35-L36), [explore:73](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L73)

### G4-15
- 원래 행동: 선택지를 비교해 추천안과 이유를 말하되, 어느 쪽으로 갈지는 사람이 정한다. "spike"(구현 전에 가능성만 시험해 보는 짧은 조사·시제품) 제안도 사람에게 한다.
- 예시: 수정 위치가 호출부와 내부 함수 두 곳 가능할 때, agent가 추천안과 대안을 적고 ff의 design.md Decisions에 선택·근거·대안을 기록한다. spike 제안은 ff discovery에서 풀 구체적 질문으로 넘긴다.
- 원문: [explore:52](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L52), [explore:84-88](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L84-L88), [explore:114](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L114), [explore:195](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L195), [docs/explore.md:70-79](../../../../../../../OpenSpec/docs/explore.md#L70-L79)

### G4-16
- 원래 행동: 사람이 explore 중에 "구현해 줘"라고 하면 시작하지 않고, explore는 구현하지 않는다고 말한 뒤 propose 명령을 알려 준다.
- 예시: SWE task 메시지 자체가 "implement the necessary changes"라고 요청하므로, 문자 그대로 읽으면 explore가 첫 응답으로 "explore는 구현하지 않습니다, propose를 쓰세요"라고 쓰고 끝난다. 처리안은 "구현 요청은 이 세션의 ff → apply가 수행, explore는 끝나면 ff 문서를 연다".
- 원문: [explore:14](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L14), [explore:345](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L345)

### G4-18
- 원래 행동: 사람이 들고 오는 상황 네 가지(막연한 아이디어, 구체적 문제, 구현 중 막힘, 선택지 비교)에 대한 대화 예시. 모두 AI가 다이어그램을 그린 뒤 사람에게 질문하며 끝난다.
- 예시: 모델이 "Which one's burning?" 같은 마무리를 따라 하면 tool call 없는 질문으로 rollout이 끝난다. issue에 맞는 예시는 "구체적 문제" 하나뿐.
- 원문: [explore:210-310](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L210-L310), [explore:199-206](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L199-L206)

### G7-9
- 원래 행동: 시작할 때 진행 중인 change 목록(`openspec list --json`)과 프로젝트가 이미 가진 capability(기능 단위 spec) 목록(`openspec list --specs`)을 보고, 관련 spec은 `openspec show`로 전부 읽은 뒤 `openspec/config.yaml`의 context·rules를 직접 읽는다.
- 예시: 이 sandbox에서는 change도 spec도 없으므로 목록 두 개가 비어 나오고 `show`는 호출할 대상이 없다. config.yaml에서는 우리가 넣은 환경 사실(checks 디렉터리 포함)을 읽는다. `list --specs`의 빈 출력과 TTY 동작은 아직 확인 안 됨.
- 원문: [explore:122-146](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L122-L146)

### G8-6
- 원래 행동: explore는 절차가 아니라 태도(stance)라서 정해진 단계·순서·산출물·끝이 없다. 서두르지 말고, 결론에 꼭 도달할 필요도 없다. 끝내는 것은 사람이 다음 명령을 칠 때.
- 예시: 150 step 예산에서 ff → archive가 이미 53–111 step을 쓴다. 끝 조건이 없으면 explore가 코드 탐색을 계속하다 patch 없이 step 한도에 걸리거나, 반대로 `openspec list` 한 번 보고 바로 ff로 갈 수 있다. (a)안은 upstream 요약의 "문제"와 "접근"을 근거와 함께 말할 수 있으면 끝.
- 원문: [explore:16](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L16), [explore:199-206](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L199-L206), [explore:314-339](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L314-L339), [explore:347](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L347)

### G9-5
- 원래 행동: explore는 생각하는 단계라 코드를 쓰지도 구현하지도 않는다. 파일 읽기·검색·읽기 전용 명령 실행은 승인 없이 할 수 있고, 파일을 쓰는 명령은 승인이 필요한 쓰기 행동이다. 쓸 수 있는 것은 change artifact뿐이며 그 밖의 파일은 안 된다.
- 예시: issue의 재현 예시를 `python -c`로 그대로 실행하거나 기존 테스트 `pytest tests/test_x.py -k y`를 돌리는 것은 파일을 만들지 않는다(실행 부산물 `__pycache__`·`.pytest_cache` 제외). `/tmp/repro.py`나 `checks/repro.py`를 만드는 것은 파일 쓰기라 금지. agent가 직접 짠 여러 줄 snippet을 stdin으로 실행하는 것은 원문만으로는 판정 불가.
- 원문: [explore:14](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L14), [explore:345](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L345), [explore:349](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L349), [explore:114](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L114), [docs/explore.md:26-36](../../../../../../../OpenSpec/docs/explore.md#L26-L36)

### G10-9
- 원래 행동: (upstream 없음) openspec_ff가 G10-7로 config.yaml `context`에 넣은 환경 사실 중 "재현·확인 스크립트는 checks/에 둔다"는 줄.
- 예시: explore가 config.yaml을 직접 읽고 이 줄을 보면 "재현 스크립트를 checks/에 쓰라"는 뜻으로 받아들여 금지된 파일 쓰기를 하거나, 아직 없는 디렉터리를 만들 수 있다.
- 원문: [explore:142-146](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L142-L146)

### G4-19
- 원래 행동: "Planning a Change"의 유일한 예시. 코드를 먼저 확인해 사실을 말한 뒤, 사람만 답할 수 있는 범위 질문("여러 기기 간 상태 공유가 범위에 들어가나요?")을 하고, 그 답에 따라 달라지는 추천안을 붙인다.
- 예시: issue가 "옵션 X가 무시된다"고만 할 때 agent가 이 예시를 따라 "기본값도 바꿔야 하나요?"라고 묻는 메시지를 쓰면, tool call이 없으면 rollout이 끝나고, 있으면 질문이 답 없이 남는다. G4-14 규칙대로라면 "issue는 기본값을 말하지 않으므로 유지한다고 가정"으로 기록해야 하는데 예시는 반대로 질문을 보여 준다.
- 원문: [explore:44-64](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L44-L64)

### G7-10
- 원래 행동: change 디렉터리를 손으로 만들지 말고 항상 `openspec new change`로 만들라는 guardrail. capture 경로(사람이 저장을 요청한 경우)에서 쓰인다.
- 예시: explore 문서 끝 guardrail에 "Always use `openspec new change "issue"`"가 남으면, 아무것도 쓰지 않는다는 문장과 나란히 change 생성 명령이 보인다. 발동 조건(capture)은 G4-13 (a)로 없어졌다.
- 원문: [explore:350](../../../../../../../OpenSpec/skills/openspec-explore/SKILL.md#L350)

### New text the port must write (explore)

- **Explore stage document** (`docs/stages/00-explore.md` or renumbered, G5-4), built by `build.py` from
  `explore` (add to `SOURCES`; tagged `Edit`s): Input line (G1-4); the five hand-offs → "open the ff
  document" (G2-10); write rule = "writes nothing" (G4-13 a); questions → assumptions (G4-14);
  recommendation instead of the person's choice (G4-15); "the task's request to implement is done by ff →
  apply" (G4-16); capture and "When a change exists" dropped (G4-17); examples per Q-E6 (G4-18); the
  read-only boundary sentence (G9-5); the end condition (G8-6). Store paragraph and frontmatter go by the
  existing mechanisms (G7-7, G7-8).
- **What explore leaves** (no code, no file): the "What We Figured Out" summary — problem, approach with
  alternatives, assumptions, open questions — in the turn that opens the ff document (G2-12 b, G2-11).
- **How it reaches ff**: ff unchanged (G2-13); it reads the summary from the conversation and grounds
  proposal **Why** / design **Context**, **Decisions** (alternatives considered) in it
  (`tpl/proposal.md:3-5`, `tpl/design.md:3,15-17`); explore's assumptions become stated assumptions in the
  proposal (core-workflow "No One Will Answer", `core-workflow.md:51-53`).
- **`core-workflow.md`**: chain line, actions row, "explore reads `/testbed` and runs commands, writes no
  file anywhere" next to `:62`, and where checks scripts start (G10-9) (G3-2).
- **`instruction.md`, `system-prompt.j2` procedure section** naming explore first (G10-8).
- `build.py` / tests / README / `__init__.py` docstring: new source, `STAGE_DOCS`, and a `FORBIDDEN`
  exception (next bullet).

### Harness notes (explore)

- `FORBIDDEN` "ask the user" (`build.py:70`) also hits `explore:48` "Do not ask the user to repeat facts
  you can verify" — a prohibition to keep (G4-14); the build fails unless it is reworded or allowed per
  source. `explore:52` is the other hit (handled by G4-14).
- Skill vs command variant: the port uses skill renders (`01-survey.md:6-7`). The command body adds
  `**Input**` (`explore.ts:415-420`) and "If the user mentioned a specific change name, read its
  artifacts" (`explore.ts:519`), and replaces the summary block with one line (`explore.ts:592`). The
  summary used by G2-12 (b) / G8-6 (a) exists in the skill only.
- The SDK default "ask the user for clarification" / "confirm with the user" lines stay
  (`system-prompt.j2:48,174`; Q6). Explore puts many more "ask" lines in front of the agent before any
  edit; G4-14's edits carry the weight.
- Leak exposure: a longer investigation phase widens the reach to answer routes (git history was kept in
  the val ablation, `06-smoke.md:106`; newer package copies, lessons "Leaks"); G6-1's rule covers the
  network only. (unverified that explore makes this more likely)
- Run side effects: test runs leave `__pycache__` / `.pytest_cache`; the SWE-bench Pro verifier cleans
  untracked runtime files before applying the patch (`rllm/data/swebench_pro_builder.py:320-332`); for
  SWE-Gym / SWE-bench Verified (unverified).
- Which task template the 60.1% no-workflow baseline used is (unverified): the SkyRL template carries
  "EXPLORATION" and "TEST CREATION: … create a script to reproduce" (`scripts/prepare_swegym.py:120-135`),
  the AI-DLC one does not (`:166-180`). That bears on how much of the reproduction gap a no-code explore
  can close.

### Open questions for the user (explore)

1. **Q-E1 (a) What counts as "writing code"** (G9-5). Upstream literally allows "read files, search code,
   investigate the codebase, and run read-only commands or tools" (`explore:14`) and forbids "NEVER write
   code" (`explore:14,345`) and any file except change artifacts (`explore:345`); its operational line is
   "another command that writes files" (`explore:349`). By that: reading tests, grep, running existing tests
   and existing code, running the issue's example as given = allowed; a script file anywhere (`/tmp`,
   `checks/`) = not allowed. Not settled by the text: agent-composed `python -c` or stdin snippets. Choose:
   (i) only existing code and the issue's own example; (ii) any command that writes no file, composed
   snippets included; (iii) stricter: no code execution at all, reading only.
2. **Q-E2 (b) Where explore's findings are recorded** (G2-12): (a) conversation only, as upstream; (b)
   upstream's summary always, in the turn that opens ff (proposed); (c) a file (departs from "writes
   nothing"); (d) capture as the person's request (collides with ff step 2 / D-7).
3. **Q-E3 (c) ff's "reuse findings … inspect more only as needed"** (G2-13): keep ff verbatim and measure
   (proposed; upstream's explore → propose meets the same text), or add one core-workflow sentence (e.g.
   ff re-checks explore's conclusion against the code before the proposal) — the latter adds an action
   upstream does not have (P2).
4. **Q-E4 (d) How explore ends unattended** (G8-6): (a) when "The problem" and "The approach" of the
   summary can be stated from evidence (proposed); (b) (a) plus a step cap — which number; (c) no
   condition.
5. **Q-E5 Explore's writes** (G4-13): (a) writes nothing, ff creates the change (proposed), or (b) core-
   workflow requests a capture (scaffold only) and ff step 2 changes.
6. **Q-E6 Entry-point examples and document name** (G4-18, G5-4): keep / keep one / drop; `00-explore.md`
   or renumber.
7. **Q-E7 Config line on `checks/`** (G10-9): keep as a fact, or reword to "from the ff action on".

### Conflicts with existing openspec_ff decisions

- **D-7 / G7-1**: ff step 2 runs `openspec new change "issue"` and the "already exists → continue" line is
  dropped. Any explore write path that scaffolds the change (G4-13 b, the capture transition) makes ff's
  step 2 exit 1.
- **G10-7** (config `context`) and `core-workflow.md:34`: "scripts to reproduce or check behavior live in
  `checks/`" reaches explore (it reads config.yaml itself) and invites the script explore may not write
  (G9-5, G10-9).
- **G4-2 / `core-workflow.md:51-53`** "record the assumption in the artifact at hand": explore has no
  artifact, and upstream says to track decisions "in the conversation, not in files" (`explore:53`).
- **`core-workflow.md:62`** lists ff and verify as the read-and-run actions; explore must be added with a
  stricter rule (no file at all).
- **`build.py` `FORBIDDEN`** "ask the user" vs `explore:48`'s prohibition (harness notes).

### Upstream intent for explore on existing code (`docs/existing-projects.md`, added at the user's request 2026-10-15)

Person-facing guide, not agent-facing text (nothing here is uploaded); it states what explore is for on a
brownfield repository, which bears on several rows above.
- Purpose and position: "Let the AI read the relevant area. This is where `/opsx:explore` earns its keep on
  an unfamiliar or large codebase … let it map how things work **before proposing anything**"
  (`docs/existing-projects.md:41`); the thirty-second flow puts it first, optional (`:19`); "the key habit
  for understanding code before you change it" (`:130`). A SWE task repository is that case (G3-2, the
  order the user fixed).
- What explore produces: the example traces the request flow, states the current structure and "the
  cleanest insertion point", then offers to scope it (`:51-54`); "the AI now understands your actual
  structure, so the proposal it writes will fit your code, not a generic template" (`:57`). Bears on
  G2-12 (what is left for ff: how the area works + where the change goes), G8-6 (an end the summary can
  state), G2-13 (ff's proposal should rest on it). The closing offer "Want me to scope it?" is the
  question G4-13 / G4-18 handle.
- Input as source material: existing documents are "source material for exploration, not … specs to
  convert … paste or point the AI at the relevant section" (`:90`); the example "reads it, asks clarifying
  questions, then helps scope a change" (`:99`). The issue plays that role (G1-4); the clarifying questions
  are G4-14's.

### Sources read (explore)

| File | Lines |
|---|---|
| `skills/openspec-explore/SKILL.md` | 353 (all) |
| `src/core/templates/workflows/explore.ts` | 608 (all; skill vs command bodies compared) |
| `docs/explore.md` | 127 (all) |
| `docs/existing-projects.md` | 134 (all; added 2026-10-15 at the user's request) |
| `docs/workflows.md` | 1-60, 100-262, 395-552 (every explore mention, `grep -n -i explore`) |
| `docs/commands.md` | 79-115 |
| `docs/concepts.md` | 165-185 |
| `src/core/templates/optional-workflow.ts` | 187 (all) |
| `src/core/project-config.ts` | 8-64, 101-160 |
| `skills/openspec-ff-change/SKILL.md`, `skills/openspec-propose/SKILL.md` | discovery lines (ff 74-78, propose 123) |
| `schemas/spec-driven/templates/{proposal,design}.md` | 34 + 21 |
| rllm: `openspec_ff/{porting/*, docs/*, instruction.md, system-prompt.j2 (60-75, 48, 174), build.py, __init__.py, sandbox/openspec-config.yaml}`, `scripts/prepare_swegym.py:100-182`, `config/config.yaml:61-68`, `workflow_harness.py:265-290`, `rllm/harnesses/tools/openhands_sdk_runner.py:99-126`, `rllm/data/swebench_pro_builder.py:305-335`, `speckit_bug` / `speckit_sdd` `03-decisions.md` | as listed |
