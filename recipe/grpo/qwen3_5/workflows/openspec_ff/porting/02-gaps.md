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
