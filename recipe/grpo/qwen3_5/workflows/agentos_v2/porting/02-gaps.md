# Gaps: agentos_v2  (upstream buildermethods/agent-os@6a64951 = v2.1.1, process single-agent shape-spec → write-spec → create-tasks → implement-tasks, "other tools" install path)

## Setting

- One user message (instruction + SWE task text, issue in `<issue_description>`, repo at `/testbed`), an
  openhands-sdk 1.42.1 agent with Terminal / FileEditor / TaskTracker only
  (`rllm/harnesses/tools/openhands_sdk_runner.py:123-126`), one `send_message` + one `run()` (`:148-149`),
  cwd = the repo (`:92-94`), nobody answering, hidden tests graded afterwards (SWE-Gym `eval.sh` in the same
  container, `recipe/grpo/qwen3_5/scripts/prepare_swegym.py:184-213`). A turn without a tool call ends the
  session (`references/lessons.md`, "A text-only reply ends the session").
- Process and install path are fixed by the user (`01-survey.md`, "Process chosen", 2026-10-14). What the agent
  would read upstream is the rendered "other tools" output; every rendered file of the four commands and the
  15 standards was read in full (table at the end). The numbered PHASE files are byte-identical to the
  embedded PHASE bodies except for the `{{UNLESS compiled_single_command}}` blocks they keep (checked by
  `diff`), and every inlined workflow/standard is byte-identical to its source (checked by `diff`).
- Short names. Rendered (`R:` = `.../agentos-render/project/`): `R:shape` = `R:agent-os/commands/shape-spec/shape-spec.md`,
  `R:write` = `R:agent-os/commands/write-spec/write-spec.md`, `R:tasks` = `R:agent-os/commands/create-tasks/create-tasks.md`,
  `R:impl` = `R:agent-os/commands/implement-tasks/implement-tasks.md`, `R:std/x` = `R:agent-os/standards/x`;
  numbered files spelled out. Pre-render (upstream checkout): `cmd/<c>/x.md` =
  `profiles/default/commands/<c>/single-agent/x.md`, `wf/x` = `profiles/default/workflows/x`, `std/x` =
  `profiles/default/standards/x`. rllm: `runner` = `rllm/harnesses/tools/openhands_sdk_runner.py`, `harness` =
  `recipe/grpo/qwen3_5/workflow_harness.py`, `prepare_swegym.py` = `recipe/grpo/qwen3_5/scripts/prepare_swegym.py`,
  `_port.py` = `recipe/grpo/qwen3_5/workflows/_port.py`; "as bug/sdd/ospec Gx-n" = a row of that port's
  `03-decisions.md` (speckit_bug / speckit_sdd / openspec_ff).
- Line offsets rendered ← source (for converter edits): `R:shape` = `wf/specification/initialize-spec.md` + 10
  (lines 11-92), `wf/specification/research-spec.md` + 99 (100-361), `cmd/shape-spec/2-shape-spec.md:7-27` + 357
  (364-384); `R:write` = `wf/specification/write-spec.md` + 2 (3-101), `cmd/write-spec/write-spec.md:5-15` + 99;
  `R:tasks` = `cmd/create-tasks/1-get-spec-requirements.md:1-9` + 8, `wf/implementation/create-tasks-list.md` + 22
  (23-221), `cmd/create-tasks/2-create-tasks-list.md:5-15` + 219; `R:impl` = `cmd/implement-tasks/1-determine-tasks.md` + 12,
  `wf/implementation/implement-tasks.md` + 30, `cmd/implement-tasks/2-implement-tasks.md:5-23` + 44,
  `wf/implementation/verification/verify-tasks.md` + 96, `update-roadmap.md:1` → 110, `run-all-tests.md` + 114,
  `create-verification-report.md` + 123.
- Proposed names used below (stage 3 decides, open question 1): documents at `container_dir=/agent-os`
  (`core-workflow.md`, `commands/<cmd>/<cmd>.md`, `standards/**`, mirroring upstream's `agent-os/` layout);
  spec folder `S` = `/tmp/agent-os/specs/issue/`; `output_dirs=("/tmp/agent-os",)`.

## Gaps

| ID | Type | Upstream location | What the text does | Why it breaks in rllm (evidence) | Proposed handling | Tag | Status |
|---|---|---|---|---|---|---|---|
| G1-1 | G1 input | `R:shape:15,23-39` (`wf/specification/initialize-spec.md:5,13-29`): "Receive it from the user or check the product roadmap"; "IF you were given a description … use that"; OTHERWISE read `roadmap.md`, "OUTPUT … and WAIT"; `R:shape:43,49` (`:33,39`) "kebab-case spec name from user's description" | takes the feature from what the person typed with the command; if none, proposes the next roadmap item and waits | nothing is typed with a command; the only input is the issue (`prepare_swegym.py:172-179`). The OTHERWISE branch is an ask = end of rollout (lessons) | "the feature description is the issue in `<issue_description>`"; OTHERWISE branch and its output block dropped (unreachable once the input is fixed). P2 | env (precedent: bug G1-1; ospec G1-1) | decided |
| G1-2 | G1 input | `R:shape:17` (`initialize-spec.md:7`) "Save Raw Idea: Document the user's exact description without modification" — no step does it; `R:shape:104,113-115` (`research-spec.md:5,14-16`) "Read the raw idea from `[spec-path]/planning/initialization.md`"; `R:shape:258-259` (`:159-160`) Initial Description "from initialization.md" | Phase 2 starts by reading a file Phase 1 is supposed to write but never writes (upstream inconsistency, survey) | literally, Step 1 of Phase 2 opens a missing file; the agent then guesses, searches the repo for it, or creates it ad hoc **(inferred)** | Phase 1 writes the issue text verbatim to `S/planning/initialization.md` (the responsibility upstream lists, mapped to the one step it lacks); Phase 2 reads it as written. P2, P3 (fixed file a verifier can check) | env | decided |
| G1-3 | G1 input | `R:shape:105,117-142` (`research-spec.md:6,18-43`) read `agent-os/product/mission.md`, `roadmap.md`, `tech-stack.md` | product context from plan-product's outputs | plan-product is not in the process (survey, process C) and SWE repos have no `agent-os/product/` → three missing files | product context comes from the repository itself (README, packaging/build metadata, docs index) in place of the three files, which do not exist in this project. P2 (nearest action) | env (precedent: sdd G1-3, tech context from the repository) | decided |
| G1-4 | G1 input | `R:write:57-93` (`wf/specification/write-spec.md:55-91`) spec template: Goal, "As a [user type], I want…" User Stories, Visual Design, Out of Scope; `R:shape:256-331` requirements template (Functional Requirements, "User actions enabled", Scope In/Out) | product/feature framing of a spec | SWE issues are code-level; unlike spec-kit, Agent OS lets requirement bullets carry "the technical approach to take" (`R:write:72`), so no rule forbids naming APIs. Only the user-story line reads oddly for a bug | keep verbatim (no edit). P2 | — (precedent: sdd G1-4, keep verbatim) | decided |
| G2-1 | G2 hand-off | in-command outputs: `R:shape:72-85` (Step 4 "Return or output the following"), `:90` ("Pass the exact spec path back to the orchestrator"), `:191`, `:237-247`, `:333-348` (Step 7 "Return to orchestrator"), `:361`; `R:impl:51` ("Display a summary of what was implemented") | prints confirmations/summaries to the person or "orchestrator" mid-pipeline | any tool-less message ends the session (lessons); in the compiled file PHASE 2 follows Step 4 directly, so a literal reply ends after the folder is made | "never answer in plain text before `finish`; the content these blocks report is already in the files"; blocks dropped. P1-P2 | env (precedent: sdd G2-4; ospec G2-7) | decided |
| G2-2 | G2 hand-off | end-of-command next steps: `R:shape:364-384` (`cmd/shape-spec/2-shape-spec.md:7-27`: "Run the command, `1-create-spec.md`", "Run `/write-spec`"); `R:write:104-114` (`cmd/write-spec/write-spec.md:5-15`: "Run the command, 2-create-tasks-list.md"); `R:tasks:224-234` (`cmd/create-tasks/2-create-tasks-list.md:5-15`: "Run `/implement-tasks` … or `/orchestrate-tasks`"); `R:impl:53-59` (`cmd/implement-tasks/2-implement-tasks.md:9-15`: "Run `3-verify-implementation.md`" while PHASE 3 follows in the same file) | tells the person which command to run next (three of four names wrong or absent on this path) | nobody runs commands; the text-only message ends the rollout; wrong names send the agent looking for files that are not shipped | each command ends "open `/agent-os/commands/<next>/<next>.md` and continue"; implement's PHASE 2 ends "continue with PHASE 3 below"; `/orchestrate-tasks` dropped (not in the process). P2 | env (precedent: bug G2-1, G2-2) | decided |
| G2-3 | G2 hand-off | `R:tasks:9-17` (`cmd/create-tasks/1-get-spec-requirements.md:1-9`): "IF you don't have … in your current conversation context, then ask user … wait"; "you can run /shape-spec or /write-spec" | spec location carried by chat context; asks when missing | one session, so context normally holds it, but an ask = end; slash names do not exist here | PHASE 1 reads the fixed paths `S/spec.md` and `S/planning/requirements.md`; if missing, "carry out the shape-spec / write-spec document first". P2 | env (precedent: bug G2-2) | decided |
| G3-1 | G3 entry document | none: the person attaches each command file in turn (survey, "Driving it", inferred) | no agent-facing text strings the four commands together | `WorkflowSpec.entry_doc` must exist and be named by instruction and system prompt (`harness:288-295`) | hand-written `docs/core-workflow.md` (see "New text") | (new text) (precedent: bug G3-1) | decided |
| G4-1 | G4 interactive | `R:shape:106-108,144-191` (`research-spec.md:7-9,45-92`): 4-8 numbered "I'm assuming X, is that correct?" questions, "OUTPUT … and STOP - wait for user response"; `R:shape:218-247` (`:119-148`) follow-ups, "Then STOP and wait"; `:357-358` (`:258-259`) "Keep follow-ups minimal", "Save user's exact answers, not interpretations"; template Q/Answer `R:shape:263-289` (`:164-189`) | the person answers the agent's assumption questions (twice at most) | each STOP is a text turn = end (lessons) | keep the question generation (same format, 4-8 + the exclusions question; follow-ups 1-3 only if needed) and answer each with the most plausible reading of the issue and repository, recorded as `**Answer:** (assumed) <answer> — <basis>` in requirements.md; "exact answers" → "record the assumed answer and its basis"; no STOP. P2 (action kept), P3 | semantic (precedent: bug G4-3; sdd G4-1; ospec G4-2) | decided |
| G4-2 | G4 interactive | `R:shape:167-174` (`research-spec.md:68-75`) "Existing Code Reuse: … Please provide file/folder paths"; `R:shape:214-216` (`:115-117`) "IF user provided paths … DO NOT explore them yourself (to save time), but DO document their names for … the spec-writer"; `:228-230` (`:129-131`) reuse follow-ups; template `R:shape:273-282` (`:174-183`) | a person names similar features; the agent records names only and leaves the search to write-spec | no person; with G4-1's self-answer the agent would either explore the repo here (against "DO NOT explore") or invent paths | answer the reuse question only from names/paths the issue itself mentions, recorded under Similar Features without opening them; none → the template's own line "No similar existing features identified for reference." The codebase search stays in write-spec Step 2 (`R:write:30-47`). P2 | semantic | decided |
| G4-3 | G4 interactive | visuals: request `R:shape:176-188` (`research-spec.md:77-89`); MANDATORY `ls … visuals/ … \|\| echo "No visual files found"` `R:shape:199-212` (`:100-113`, "Use Read tool to analyze EACH visual file"); visual follow-ups `:222-226`; template `:290-304`; write-spec Visual Design `R:write:21,76-82,98`; tasks "Match mockup" `R:tasks:140`, "Reference visual assets" `:221`; implement "visuals (if any)" `R:impl:35` | a person drops mockups into `planning/visuals/`; every stage reads them | nobody adds files; the `ls` runs fine in the sandbox and prints "No visual files found", for which every template has its own fallback ("No visual assets provided.", "[If mockups provided]") | keep the folder, the mandatory `ls` and every fallback verbatim; drop only the request addressed to the person (it is part of the G4-1 output block). P2, P5 | env | decided |
| G4-4 | G4 interactive | `R:impl:13-25` (`cmd/implement-tasks/1-determine-tasks.md:1-13`): "check if the user has already provided instructions about which task group(s)"; else read tasks.md, "Should we proceed with implementation of all task groups … WAIT" | the person picks the task groups | no instructions exist; the ask = end | "implement every task group in tasks.md, in order" — the answer the question itself proposes; ask dropped. P2 | semantic (precedent: sdd G4-4, take upstream's proceed branch) | decided |
| G4-5 | G4 interactive | `R:impl:61-67` (`cmd/implement-tasks/2-implement-tasks.md:17-23`): unchecked tasks remain → "Would you like to proceed with implementation of the remaining tasks?"; `R:impl:31,37` (`wf/implementation/implement-tasks.md:1,7`) "Implement … ONLY those task(s) that have been assigned", "the assigned task group" | one group per invocation, the person re-invokes for the rest | ask = end after the first group, leaving a partial change | "repeat PHASE 2 for the next group with unchecked tasks until none remain, then PHASE 3"; "assigned" = the current group. P2 | env | decided |
| G4-6 | G4 interactive | `R:write:111` ("Review it closely to ensure everything aligns with your vision"), `R:tasks:231` ("Review it closely to make sure it all looks good") | human review between commands | no reviewer | dropped with G2-2's message blocks. P4 | env (precedent: bug G4-6; sdd G4-7) | decided |
| G5-1 | G5 paths & IDs | `R:shape:56` (`initialize-spec.md:46`) `SPEC_PATH="agent-os/specs/$DATED_SPEC_NAME"` and every `agent-os/specs/…` path (`R:write:18,21,51`, `R:tasks:10-11,37-38,45`, `R:impl:19,38,97,124`) | spec artifacts inside the project | relative to the runner's cwd `/testbed` (`runner:92-94`) → `/testbed/agent-os/specs/…`, inside the repo: lands in the patch / wiped by `git clean` (lessons, "Artifacts inside the repo") | `S` = `/tmp/agent-os/specs/issue/`, absolute everywhere; `output_dirs=("/tmp/agent-os",)`. P1 | env (precedent: bug G5-1) | decided |
| G5-2 | G5 paths & IDs | `R:shape:43-62` (`initialize-spec.md:33-52`) `TODAY=$(date +%Y-%m-%d)`, `SPEC_NAME="[kebab-case-name]"`; `R:shape:89` (`:79`) "Always use dated folder names (YYYY-MM-DD-spec-name)" | generates the folder name from the date and a name the agent picks | a generated name makes every downstream path and any scorer path rollout-dependent | fixed `issue` (no date): Step 2 reduces to `mkdir -p /tmp/agent-os/specs/issue/planning/visuals`; the dated-name constraint dropped. Alternative: keep `date` → `/tmp/agent-os/specs/<YYYY-MM-DD>-issue/` (closer to upstream, scorer globs). P3 vs P2 (open question 1) | env (same kind as sdd G5-2; bug G4-1) | decided |
| G5-3 | G5 paths & IDs | placeholders `[this-spec]` (`R:shape:369`, `R:write:109`, `R:tasks:10-11,229`, `R:impl:19,38,56,97,101,124`), `[current-spec]` (`R:write:18,21,51`, `R:tasks:45`), `[spec-path]` (`R:shape:77,109,115,179,205,251,345,353,379`), `$SPEC_PATH` (`R:shape:56-68`) | the spec's identity lives in chat context and four spellings | with G5-1/G5-2 the path is fixed; leftover placeholders invite the agent to re-derive or ask | substitute the literal `S` everywhere (build substitution + `forbidden` list). P3 | env (precedent: sdd G5-3, path substitutions) | decided |
| G5-4 | G5 paths & IDs | `@agent-os/standards/…` lists (`R:shape:390-395`, `R:write:120-134`, `R:tasks:240-254`, `R:impl:73-87`), `@agent-os/product/roadmap.md` (`R:shape:29`), `agent-os/product/*` (`R:shape:121,127,133`, `R:impl:110`) | references into the project's `agent-os/` folder | relative to `/testbed` they resolve to nothing; documents live at `container_dir` | `@agent-os/standards/` → `/agent-os/standards/` (absolute); product paths handled by G1-3 / G7-8. P1-P2 | env (precedent: sdd G5-3) | decided |
| G5-5 | G5 paths & IDs | `R:shape:18` (`initialize-spec.md:8`) "Create Implementation & Verification Folders"; `R:shape:65-70` (`:55-60`) "Create 2 folders:" lists only `implementation/`; `R:impl:124` (`wf/implementation/verification/create-verification-report.md:1`) report at `verifications/final-verification.html` with markdown content (`R:impl:128`) | the report's folder is never created; markdown saved under `.html` (upstream inconsistencies, survey) | creating a file in a missing folder fails once with FileEditor **(unverified)** and costs a step; a scorer needs one fixed report path | Phase 1 creates `implementation/` and `verifications/` (the "2 folders" and responsibility 4); keep the report name `final-verification.html` verbatim. Alternative: rename to `.md`. P2, P3 | env | decided |
| G5-6 | G5 paths & IDs | `R:shape:70,82` (`initialize-spec.md:60,72`) implementation folder "populated with reports documented by implementation agents"; `R:impl:101` (`verify-tasks.md:5`) check for an implementation report in `agent-os/spec/[this-spec]/implementation/` (singular `spec/`); report section 2 `R:impl:160-172` (`create-verification-report.md:37-49`: `implementations/1-[task-name]-implementation.md`, "verification documents from area verifiers") | multi-agent remnants: v2.1.0 removed per-task implementation docs and specialized verifiers (`CHANGELOG.md:82-86`) but the text still reads/lists them | no stage writes these files; the typo path does not exist either way; the report's section 2 can only say "missing" | delete the report-check bullet (`R:impl:101`) and section 2's Implementation / Verification Documentation subsections; keep the empty `implementation/` folder (upstream structure). Alternative: keep verbatim, agent records "None". P4 | semantic | decided |
| G5-7 | G5 paths & IDs | (no upstream line) tests and scratch scripts the tasks call for (G9-1) | — | stray repo files (`IMPLEMENTATION_SUMMARY.txt`, temp `test_issue.py`) in earlier smokes (lessons, "Agents still leave stray files") | entry doc: check scripts and scratch files go under `S/checks/`; nothing of the workflow is written into `/testbed`. P1 | env (precedent: sdd G5-5 rev2) | decided |
| G6-1 | G6 network | none in the pipeline text; the issue may carry links | — | `allow_internet = true` (`prepare_swegym.py:248`); links and online lookups reach the fix (lessons, "Leaks") | entry doc: no fetching or online lookup, no package installs; links in the issue are not opened. P1 | semantic (precedent: bug G6-1; ospec G6-1) | decided |
| G6-2 | G6 network | `R:impl:46` (`wf/implementation/implement-tasks.md:16`) "IF your task involves user-facing UI, and IF you have access to browser testing tools, open a browser" | optional browser check of UI | no browser tool (`runner:123-126`); both conditions are false for a Python repo | keep verbatim (conditional no-op). P2, P4 | env | decided |
| G7-1 | G7 machinery (render) | template tags in every target source: `{{PHASE N: @…}}` (`cmd/shape-spec/shape-spec.md:7,9`, `cmd/create-tasks/create-tasks.md:7,9`, `cmd/implement-tasks/implement-tasks.md:11-15`), `{{workflows/…}}`, `{{standards/*}}`, `{{UNLESS …}}` (survey, "How template tags resolve") | the installer compiles each command into one file; the numbered files are also written standalone with `{{UNLESS compiled_single_command}}` blocks kept (`R:agent-os/commands/shape-spec/1-initialize-spec.md:86-95` "Run the command, 2-research-spec.md"; `R:agent-os/commands/create-tasks/1-get-spec-requirements.md:11-19`) | `_port.py` has no template step (`_port.py:146-161`: read, edit, sections, substitutions); shipping raw sources leaves `{{…}}` the agent cannot resolve; shipping the standalone numbered files duplicates text and adds wrong next-step lines | build renders as the installer does (Harness / build notes), and ships the **four top-level compiled files** only, as `/agent-os/commands/<cmd>/<cmd>.md` (what the person attaches upstream); numbered standalone files not shipped. P2, P5 | env (same kind as sdd G7-5: build does the renderer's job) | decided |
| G7-2 | G7 machinery | `R:shape:3-5`, `R:tasks:3-5`, `R:impl:7-9` (`cmd/*/<cmd>.md:3-5,7-9`) "Carefully read and execute the instructions in the following files IN SEQUENCE, following their numbered file names" — the files are already inlined below as `# PHASE N` | points at numbered files that are not separate here | the agent may look for `…/1-initialize-spec.md` etc. (not shipped, G7-1) **(inferred)** | "the PHASE sections below, in order; finish one before starting the next". P2 | env | decided |
| G7-3 | G7 machinery | the `@`-path standards lists (G5-4) under "IMPORTANT: Ensure that … is ALIGNED and DOES NOT CONFLICT with the user's preferences and standards as detailed in the following files" (`R:shape:386-388`, `R:write:116-118`, `R:tasks:236-238`, `R:impl:69-71`) | in a tool that expands `@path`, the 6 or 15 standards arrive as context with the command | openhands-sdk does not expand `@` paths (no such code in `openhands/sdk`, grep in `rllm-agent-f268c8df48c7`), and a path inside a document is never expanded anyway: the agent sees a list of names and decides whether to open them | (a) ship the 15 standards verbatim at `/agent-os/standards/`, list them by absolute path, keep the sentence (the agent opens them as needed). (b) inline each command's standards under the sentence (what an `@`-expanding tool shows; 163 lines × 3 + 6 files). P2 vs budget (open question 3) | env | decided |
| G7-4 | G7 machinery | `R:impl:15` (`cmd/implement-tasks/1-determine-tasks.md:3`) "Proceed to PHASE 2 to delegate implementation … to the **implementer** subagent"; `R:impl:31` "tasks assigned to you" | delegates to a Claude Code subagent | no subagent tool (`runner:123-126`); on this install path no subagent exists either (survey, process D) | "carry out PHASE 2 yourself". P2, P4 | env | decided |
| G7-5 | G7 machinery | role names of the multi-agent path: "orchestrator" (`R:shape:90,191,195,237,335,361`), "spec-writer" (`:214-216,360`), "spec-shaper" (`R:write:26`), "implementation agents" (`R:shape:70`), "database-engineer / api-engineer / ui-designer" (`R:tasks:170-172`), "Verifier: implementation-verifier" (`R:impl:133`) | addresses or names agents that relay answers or own work | no other agent; lines that send output to the orchestrator are G2-1; the rest are labels | drop the orchestrator clauses with G2-1; "spec-writer" → "the write-spec stage"; the example's engineer names and the Verifier label kept verbatim (labels, no action). P4, P2 | env | decided |
| G7-6 | G7 machinery (config) | `R:std/global/tech-stack.md:1-31` (`std/global/tech-stack.md`) placeholder "[e.g., Rails, Django, …]" in every list (shape-spec 6 + 15) | the project's stack, meant to be filled in by the person | upstream installs it unfilled (copied verbatim, survey); a reader may treat placeholders as facts or try to fill it **(inferred)** | ship verbatim (upstream post-install state); no rule — the lists only ask for alignment, and the stack comes from the repository (G1-3). Alternative: one line "an unfilled template states no stack". P2 | env (same kind as sdd G7-6, placeholder shipped verbatim; their extra rule not proposed) | decided |
| G7-7 | G7 machinery | Claude Code wording: "Use Read tool to analyze EACH visual file" (`R:shape:209`), "THINK HARD" (`R:write:15`) | tool name / extended-thinking keyword of Claude Code | no `Read` tool (FileEditor `view` instead); the visuals branch is unreachable (G4-3); "THINK HARD" has no mechanical effect on Qwen **(inferred)** | keep verbatim. P2 | env | decided |
| G7-8 | G7 machinery (config) | `R:impl:108-110` (`update-roadmap.md:1`) "Open `agent-os/product/roadmap.md` … mark matching items `- [x]`"; report section 3 `R:impl:176-184` (`create-verification-report.md:53-61`) | ticks the product roadmap | no roadmap exists (G1-3); the agent may create one to tick it **(inferred)** | keep the step and section; "this project has no roadmap.md (plan-product was not run): do not create it; section 3 status `⚠️ No Updates Needed` with that note" (the template's own status). P2, P3. Alternative: delete step 2 + section 3 (P4) | env | decided |
| G8-1 | G8 loops & ends | upstream ends after the report (`R:impl:122-203`); the person reads it | — | the session must end with `finish`, not a text reply | entry doc: after `S/verifications/final-verification.html` exists, call `finish`; repo change complete before PHASE 3. P2 | env (precedent: ospec G8-3) | decided |
| G8-2 | G8 loops & ends | `R:impl:113-117` (`run-all-tests.md:1-3`) "Run the entire tests suite for the application so that ALL tests run", counts in the report | full-suite regression run | SWE-Gym repos (pandas, moto, dask, MONAI, …) have suites that can exceed the 3600 s agent timeout (`prepare_swegym.py:84`) and the step budget **(inferred per repo)**; a timed-out rollout ends unfinished | (a) run the test modules/directories covering the changed code, record counts (nearest feasible; as bug G4-5 / sdd G9-1 "existing tests related to the change"); (b) run the entire suite under a time cap (e.g. `timeout 900`) and record whether it completed; (c) verbatim. Proposed (a). P1-P3 | semantic (precedent: bug G4-5; sdd G9-1 rev2) | decided |
| G8-3 | G8 loops & ends | `R:impl:119` (`run-all-tests.md:5`) "DO NOT attempt to fix any failing tests. Just note their failures"; ⚠️ for incomplete tasks `R:impl:105` | verification only reports; no return to implementation | consistent with the task (no test edits, `prepare_swegym.py:177`); a regression the agent caused stays unfixed → 0 reward, but that is upstream's design | keep verbatim, no round. Alternative: one fix round when a failure is caused by the change (loop tag; as bug G8-1 — ospec dropped its verify loop as never firing, ospec G8-1). P2 | — | decided |
| G8-4 | G8 loops & ends | the chain: init + Q&A + requirements + spec + tasks + per-group implement + full verification | — | `agent_step_limit` 150 (`recipe/grpo/qwen3_5/config/config.yaml:68`), 100 in the AI-DLC SWE-Gym variant (`config/variant/openhands_9b_aidlc_swegym.yaml:66`); standards reading (G7-3) and the suite run (G8-2) add steps | no text change; measure steps per command in the smoke. P3 | — (precedent: sdd G8-4) | decided |
| G9-1 | G9 task conflicts | tasks template: each group "x.1 Write 2-8 focused tests", "x.n Ensure … tests pass: Run ONLY the 2-8 tests" (`R:tasks:63-80,94-111,125-155`), Group 4 "Write up to 10 additional strategic tests" (`:163-194`), constraints `:214-219` ("focused test-driven approach") (`create-tasks-list.md:41-58,72-89,103-133,141-172,192-197`); implement "Running ONLY the tests you've written" `R:impl:45` (`implement-tasks.md:15`); `R:std/testing/test-writing.md:3-9` | writes new tests in the repo, test-first per group | the task says test files are handled and not to be modified, change non-test files only (`prepare_swegym.py:177-179`); the grader applies the test patch (`git apply` fails if a new file already exists) and restores test files (`:184-187`) | test sub-tasks write their tests as check scripts under `S/checks/` (never repository test files) and run only those, as upstream; Group 4's gap tests likewise; the standard applies to those scripts. No fail-first step added (upstream does not state one). P1, P2 | semantic (precedent: sdd G9-1 rev2; ospec G9-1) | decided |
| G9-2 | G9 task conflicts | `R:std/global/conventions.md:4-11`: README upkeep, "clear commit messages, feature branches, … pull/merge requests", "Keep dependencies up-to-date", code review process, testing requirements before merging, feature flags, changelog maintenance | team/project process norms | read as instructions they ask for README/changelog edits, branches, dependency upgrades (network, G6-1) beyond "minimal changes to non-test files" (`prepare_swegym.py:179`) | (a) keep the file verbatim; entry doc: "standards describe how code is written; they do not add work — no README/changelog/dependency/branch changes unless the issue asks" (as ospec G9-2). (b) delete those lines (P4: team process). P1, P2 vs P4 | semantic (same kind as ospec G9-2) | decided |
| G9-3 | G9 task conflicts | `R:std/global/coding-style.md:8-10` "Remove Dead Code: Delete unused code, commented-out blocks, and imports", "Backward compatibility only when required: … assume you do not need … backward compatibility", "DRY: … extracting common logic" | code-scope norms | invite cleanup and refactors outside the issue; dropping backward compatibility can break callers the hidden tests exercise **(inferred)** | (a) keep verbatim, covered by G9-2(a)'s line ("apply them to the code the issue requires you to change"); (b) no change. P1 vs P2 | semantic | decided |
| G9-4 | G9 task conflicts | tasks example: Database Layer (models, migrations), API Layer (controller, auth), Frontend (responsive breakpoints, animations) (`R:tasks:49-203`), "Group tasks by specialization (backend, api, ui design)" `R:tasks:29,213` | web-app sample structure | a literal follower adds layers a Python library issue does not need **(inferred)**; the text says "example format - adapt" (`R:tasks:47,205-208`) | keep verbatim; measure in the smoke (task groups vs issue size). P2 | env (same kind as sdd G9-3's "sample tasks unchanged") | decided |
| G10-1 | G10 harness & dataset | SDK default `<PROBLEM_SOLVING_WORKFLOW>` (`workflows/speckit_bug/system-prompt.j2:60-72`) | competes with the workflow | the SDK section wins over a user-message instruction unless replaced (lessons) | rewrite for agentos_v2, worded fresh. P5 | — (precedent: bug G10-1) | decided |
| G10-2 | G10 harness & dataset | SDK "ask the user for clarification" / "confirm with the user" (`workflows/speckit_bug/system-prompt.j2:48,171`) | invites questions | an ask ends the session | keep for comparability | — (precedent: bug G10-2; ospec Q6) | decided |
| G10-3 | G10 harness & dataset | SWE-Gym prompt's six-step procedure (`prepare_swegym.py:118-152`) | competing procedure | 86% never opened the workflow with it (lessons, "Task text") | `swegym293_aidlc` + `instruction_position=prefix` | — (precedent: bug G10-3) | decided |
| G10-4 | G10 harness & dataset | (instruction text, port-written) | — | late or mis-resolved entry-doc reads (lessons, "Doc path misresolution"); here also: every upstream path says `agent-os/…`, inviting `/testbed/agent-os/` | instruction: opening `/agent-os/core-workflow.md` is the first action; `/agent-os` is at the filesystem root, outside the repository | env (precedent: sdd G10-4) | decided |
| G10-5 | G10 harness & dataset | `R:impl:38,97` (`implement-tasks.md:8`, `verify-tasks.md:1`) `- [x]` in tasks.md is the progress record | — | the SDK's TaskTracker tool (`runner:126`) can replace tasks.md ticks; PHASE 3 reads the checkboxes **(inferred)** | entry doc: tasks.md checkboxes are the record; TaskTracker is optional scratch | env (precedent: sdd G10-5) | decided |
| G9-5 | G9 task conflicts (found in stage 4) | `std/backend/migrations.md:9` (inlined into write-spec, create-tasks, implement-tasks, G7-3) | "**Version Control**: Always commit migrations to version control and never modify existing migrations after deployment" | the same kind of team process as conventions line 5 (commits / branches, deleted by G9-2); a `git commit` in the sandbox is work outside the issue (P4) | delete the line | semantic | decided |

Counts: 44 rows. G1 4, G2 3, G3 1, G4 6, G5 7, G6 2, G7 8, G8 4, G9 4, G10 5.
Tags: env 28, semantic 9, new text 1, — 6.

### G1-2
- 원래 행동: shape-spec 1단계 책임 목록에 "사용자가 준 기능 설명을 그대로 저장"이 있지만 실제로 저장하는 단계가 없고, 2단계는 그 파일(`planning/initialization.md`)을 읽는 것으로 시작한다(업스트림 자체의 누락).
- 예시: SWE-Gym 이슈 본문을 `/tmp/agent-os/specs/issue/planning/initialization.md`에 그대로 써 두고, 2단계와 requirements.md 의 "Initial Description"이 그 파일을 읽는다.
- 원문: [wf/specification/initialize-spec.md#L7](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L7), [wf/specification/research-spec.md#L14-L16](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L14-L16)

### G4-1
- 원래 행동: 에이전트가 "X 라고 가정하는데 맞나요?" 형식의 번호 질문 4–8개(마지막은 제외 범위 질문)를 사람에게 출력하고 멈춰 답을 기다린다. 답을 받은 뒤 필요하면 후속 질문 1–3개를 또 묻고 멈춘다. 답은 requirements.md 에 질문·답 원문으로 기록한다.
- 예시: "`to_csv`가 빈 DataFrame 에서 헤더를 쓰지 않는다" 이슈 → 질문 "빈 DataFrame 에서도 헤더 한 줄을 쓰는 것으로 가정하는데 맞나요?" 를 만들고, 답을 `(assumed) 예 — 이슈의 기대 출력 예시` 로 스스로 채워 기록한 뒤 바로 진행.
- 원문: [wf/specification/research-spec.md#L45-L92](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L45-L92), [#L119-L148](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L119-L148), [#L251-L262](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L251-L262)

### G4-2
- 원래 행동: "재사용할 만한 비슷한 기존 기능이 있으면 경로를 알려 달라"고 사람에게 묻고, 사람이 알려준 경로는 이 단계에서 직접 열어 보지 말고 이름만 기록해 다음 단계(write-spec, 여기서 코드베이스 검색을 함)에 넘긴다.
- 예시: 이슈가 `pandas/io/formats/csvs.py`를 언급하면 그 경로를 Similar Features 에 이름만 기록하고, 언급이 없으면 템플릿의 "No similar existing features identified for reference." 를 쓴다. 실제 검색은 write-spec Step 2 에서.
- 원문: [wf/specification/research-spec.md#L68-L75](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L68-L75), [#L115-L117](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L115-L117), [#L174-L183](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L174-L183)

### G4-3
- 원래 행동: 사람에게 시안 이미지(mockup·wireframe)를 `planning/visuals/`에 넣어 달라고 요청하고, 답과 상관없이 그 폴더를 `ls` 로 반드시 확인한다. 파일이 없으면 각 템플릿의 "시안 없음" 문구를 쓴다.
- 예시: 폴더는 비어 있으므로 `ls … || echo "No visual files found"` 가 "No visual files found" 를 출력 → requirements.md 에 "No visual assets provided.", spec.md 의 Visual Design 은 "[If mockups provided]" 조건에 따라 비움.
- 원문: [wf/specification/research-spec.md#L77-L113](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L77-L113), [wf/specification/write-spec.md#L74-L80](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/write-spec.md#L74-L80)

### G4-4
- 원래 행동: implement-tasks 시작 시 사람이 "어떤 task group 을 구현할지" 지정했는지 보고, 없으면 "tasks.md 의 모든 task group 을 진행할까요?"라고 묻고 기다린다. task group = tasks.md 의 "Task Group 1: …" 같은 묶음(테스트 작성 → 구현 → 그 테스트 실행).
- 예시: 질문 대신 tasks.md 의 Task Group 1, 2, … 를 순서대로 모두 구현.
- 원문: [cmd/implement-tasks/1-determine-tasks.md#L1-L13](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/implement-tasks/single-agent/1-determine-tasks.md#L1-L13)

### G4-5
- 원래 행동: 한 번 호출에 할당된 group 하나만 구현하고, 남은 항목이 있으면 "남은 task 를 계속 구현할까요?"라고 물어 사람이 다시 호출하게 한다. 모두 끝나면 PHASE 3(검증)으로.
- 예시: Group 1 구현·체크 → 묻지 않고 Group 2 로 → 미체크 항목이 없을 때 PHASE 3.
- 원문: [cmd/implement-tasks/2-implement-tasks.md#L9-L23](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/implement-tasks/single-agent/2-implement-tasks.md#L9-L23), [wf/implementation/implement-tasks.md#L1-L8](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/implement-tasks.md#L1-L8)

### G5-2
- 원래 행동: spec 폴더 이름을 `date` 로 얻은 오늘 날짜 + 에이전트가 정한 kebab-case 이름으로 만든다(예: `2026-10-14-csv-export`), "항상 날짜 붙인 이름" 제약이 있다.
- 예시: 제안 (a) `/tmp/agent-os/specs/issue/` 고정 — 경로가 모든 rollout 에서 같다. 대안 (b) `date` 를 유지해 `/tmp/agent-os/specs/2026-10-14-issue/` — 업스트림 동작에 더 가깝지만 채점기는 `*-issue` 로 찾아야 한다.
- 원문: [wf/specification/initialize-spec.md#L31-L53](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L31-L53), [#L79](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L79)

### G5-5
- 원래 행동: 1단계가 "구현·검증 폴더 2개 생성"이라 하면서 `implementation/` 하나만 나열하고, 최종 보고서는 만든 적 없는 `verifications/` 폴더에 markdown 내용을 `.html` 이름으로 저장하라고 한다.
- 예시: 1단계에서 `mkdir -p …/issue/implementation …/issue/verifications` 를 함께 하고, 마지막에 `/tmp/agent-os/specs/issue/verifications/final-verification.html` 에 템플릿대로 markdown 을 쓴다.
- 원문: [wf/specification/initialize-spec.md#L8](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L8), [#L55-L60](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L55-L60), [wf/implementation/verification/create-verification-report.md#L1](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/create-verification-report.md#L1)

### G5-6
- 원래 행동: 검증 단계가 "구현 에이전트들이 남긴 task 별 구현 보고서"(오타 경로 `agent-os/spec/…`)를 찾아보고, 보고서 2절에 그 문서들과 "영역별 검증자" 문서를 나열하게 한다. v2.1.0 에서 이 문서들은 없어졌다(CHANGELOG).
- 예시: 제안대로면 보고서는 1절(Tasks)·3절(Roadmap)·4절(Test Suite)만 남고, 미완료 판단은 코드 spot check 로만 한다.
- 원문: [wf/implementation/verification/verify-tasks.md#L3-L5](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/verify-tasks.md#L3-L5), [create-verification-report.md#L37-L49](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/create-verification-report.md#L37-L49), [CHANGELOG.md#L80-L88](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/CHANGELOG.md#L80-L88)

### G6-1
- 원래 행동: 파이프라인 문서에는 인터넷 조회 지시가 없다. 추가하는 것은 "이슈의 링크를 열지 말고, 온라인 조회·패키지 설치를 하지 말라"는 entry doc 한 줄(업스트림에 없는 금지).
- 예시: 이슈에 GitHub PR 링크가 있어도 열지 않는다.
- 원문: (업스트림 대응 줄 없음) 근거 [scripts/prepare_swegym.py](../../../scripts/prepare_swegym.py) `allow_internet = true`

### G6-2
- 원래 행동: "UI 를 바꿨고 브라우저 테스트 도구가 있으면 브라우저로 직접 써 보라"는 조건부 문장.
- 예시: Python 라이브러리 이슈 + 브라우저 도구 없음 → 조건이 거짓이라 아무 일도 하지 않는다.
- 원문: [wf/implementation/implement-tasks.md#L16](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/implement-tasks.md#L16)

### G7-1
- 원래 행동: 설치 스크립트가 명령 파일의 `{{PHASE …}}`, `{{workflows/…}}`, `{{standards/*}}`, `{{UNLESS …}}` 태그를 풀어 명령마다 한 파일로 합친다. "other tools" 경로는 합친 파일과 번호 붙은 PHASE 파일을 둘 다 만들고, 번호 파일에는 틀린 "다음 명령" 안내(`2-research-spec.md`)가 남는다.
- 예시: 배포하는 문서는 `/agent-os/commands/shape-spec/shape-spec.md` 등 합친 4개(+ standards 15개)뿐.
- 원문: [commands/shape-spec/single-agent/shape-spec.md#L1-L9](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/shape-spec/single-agent/shape-spec.md#L1-L9), [commands/shape-spec/single-agent/1-initialize-spec.md#L5-L15](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/shape-spec/single-agent/1-initialize-spec.md#L5-L15), [scripts/common-functions.sh#L966-L1019](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/scripts/common-functions.sh#L966-L1019)

### G7-2
- 원래 행동: 합친 파일 맨 앞에 "다음 파일들을 번호 순서대로 읽고 실행하라"는 문장이 남아 있지만, 그 파일들은 이미 아래에 `# PHASE N` 으로 들어와 있다.
- 예시: 에이전트가 `/agent-os/commands/shape-spec/1-initialize-spec.md` 를 찾지 않고 아래 PHASE 1 → PHASE 2 를 차례로 수행.
- 원문: [commands/shape-spec/single-agent/shape-spec.md#L3-L5](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/shape-spec/single-agent/shape-spec.md#L3-L5), [commands/implement-tasks/single-agent/implement-tasks.md#L7-L9](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/implement-tasks/single-agent/implement-tasks.md#L7-L9)

### G7-3
- 원래 행동: 각 명령 끝에 "다음 표준(standards) 파일들과 어긋나지 않게 하라"며 `@agent-os/standards/…` 경로를 나열한다. Cursor 같은 도구는 `@경로`를 그 파일 내용으로 붙여 주므로, 사람이 쓸 때는 표준 내용이 함께 들어간다. standards = 코딩 스타일·주석·에러 처리·테스트 작성 등 일반 지침 15개 파일.
- 예시: (a) 문서에는 `/agent-os/standards/global/coding-style.md` 같은 절대 경로 목록만 두고 에이전트가 필요하면 연다. (b) 각 명령 문서에 해당 표준 내용을 직접 넣는다(shape-spec 6개, 나머지 15개).
- 원문: [commands/write-spec/single-agent/write-spec.md#L17-L23](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/write-spec/single-agent/write-spec.md#L17-L23), [commands/shape-spec/single-agent/2-shape-spec.md#L29-L35](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/shape-spec/single-agent/2-shape-spec.md#L29-L35)

### G7-4
- 원래 행동: "사용자가 group 을 지정했으면 PHASE 2 로 가서 implementer 서브에이전트에게 위임하라" — Claude Code 다중 에이전트 경로의 흔적. 이 설치 경로에는 서브에이전트가 없다.
- 예시: 에이전트가 PHASE 2 를 직접 수행.
- 원문: [cmd/implement-tasks/1-determine-tasks.md#L3](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/commands/implement-tasks/single-agent/1-determine-tasks.md#L3)

### G7-5
- 원래 행동: 문서가 "orchestrator 에게 결과를 넘겨라", "spec-writer 가 참고하도록", "database-engineer 가 쓴 테스트" 처럼 다른 에이전트를 부르거나 이름을 쓴다(다중 에이전트 경로에서 옮겨 온 문장).
- 예시: "Pass the exact spec path back to the orchestrator" 는 삭제(G2-1), "for the spec-writer" → "for the write-spec stage", tasks 예시의 "database-engineer" 는 그대로.
- 원문: [wf/specification/initialize-spec.md#L80](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/initialize-spec.md#L80), [wf/specification/research-spec.md#L92-L96](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L92-L96), [wf/implementation/create-tasks-list.md#L148-L150](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/create-tasks-list.md#L148-L150)

### G7-6
- 원래 행동: `standards/global/tech-stack.md` 는 "[예: Rails, Django …]" 자리표시만 있는 빈 양식으로 설치되고, 모든 명령이 이 파일과 "어긋나지 말라"고 참조한다.
- 예시: 양식 그대로 배포. 에이전트는 실제 스택을 저장소(setup.py, pyproject 등)에서 파악한다(G1-3).
- 원문: [standards/global/tech-stack.md#L1-L31](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/standards/global/tech-stack.md#L1-L31)

### G7-7
- 원래 행동: Claude Code 전용 표현 — "Read tool 로 각 시안 파일을 분석하라", 확장 사고를 켜는 키워드 "THINK HARD".
- 예시: 그대로 둔다. 시안 분기는 도달하지 않고(G4-3), Qwen 에서 "THINK HARD"는 일반 문장일 뿐.
- 원문: [wf/specification/research-spec.md#L110](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/research-spec.md#L110), [wf/specification/write-spec.md#L13](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/specification/write-spec.md#L13)

### G7-8
- 원래 행동: 검증 2단계에서 제품 로드맵 파일(`agent-os/product/roadmap.md`, plan-product 가 만드는 제품 기능 목록)을 열어 이번 spec 과 맞는 항목을 `[x]`로 체크한다.
- 예시: 로드맵이 없으므로 만들지 않고, 보고서 3절에 `⚠️ No Updates Needed — no roadmap.md (plan-product not run)` 을 쓴다.
- 원문: [wf/implementation/verification/update-roadmap.md#L1](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/update-roadmap.md#L1), [create-verification-report.md#L53-L61](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/create-verification-report.md#L53-L61)

### G8-2
- 원래 행동: 구현이 끝나면 애플리케이션의 테스트 전체를 돌려 통과·실패·에러 개수와 실패 목록을 보고서에 적는다.
- 예시: pandas 이슈라면 전체 스위트 대신 (a) 바꾼 모듈을 다루는 `pandas/tests/io/formats/` 를 돌려 개수를 기록, (b) 전체를 `timeout 900` 안에서 돌리고 완료 여부 기록.
- 원문: [wf/implementation/verification/run-all-tests.md#L1-L5](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/run-all-tests.md#L1-L5)

### G8-3
- 원래 행동: 전체 테스트에서 실패가 나와도 "고치려 하지 말고 보고서에 적기만 하라". 검증은 보고로 끝나고 구현으로 돌아가지 않는다.
- 예시: 제안은 그대로(보고 후 `finish`). 대안은 "내 변경이 만든 실패면 PHASE 2 로 한 번 돌아가 고친다"(업스트림에 없는 루프).
- 원문: [wf/implementation/verification/run-all-tests.md#L5](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/verification/run-all-tests.md#L5)

### G9-1
- 원래 행동: tasks.md 의 각 task group 이 "집중 테스트 2–8개 먼저 작성 → 구현 → 그 테스트만 실행"으로 짜이고, 마지막 group 이 빈틈 테스트를 최대 10개 더 쓴다(test-driven). 테스트는 저장소 안에 쓴다.
- 예시: Group 1 의 1.1 은 `/tmp/agent-os/specs/issue/checks/test_to_csv_header.py` 를 쓰고, 1.n 에서 그 스크립트만 실행. `/testbed/pandas/tests/…` 는 건드리지 않는다.
- 원문: [wf/implementation/create-tasks-list.md#L41-L58](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/create-tasks-list.md#L41-L58), [#L141-L172](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/create-tasks-list.md#L141-L172), [#L192-L197](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/create-tasks-list.md#L192-L197), [standards/testing/test-writing.md](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/standards/testing/test-writing.md#L1-L9)

### G9-2
- 원래 행동: conventions 표준이 README 최신 유지, 커밋 메시지·feature branch·PR, 의존성 최신화, 코드 리뷰, feature flag, changelog 관리 같은 팀 개발 관례를 나열한다.
- 예시: (a) 파일은 그대로 두고 entry doc 에 "표준은 코드 작성 방식이지 추가 작업이 아니다 — 이슈가 요구하지 않으면 README/changelog/의존성/브랜치를 바꾸지 않는다". (b) 해당 줄 삭제.
- 원문: [standards/global/conventions.md#L3-L11](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/standards/global/conventions.md#L3-L11)

### G9-3
- 원래 행동: coding-style 표준이 "안 쓰는 코드·주석 블록·import 는 지워라", "따로 지시가 없으면 하위 호환은 신경 쓰지 말라", "중복은 공통 함수로 빼라"고 한다.
- 예시: 이슈와 무관한 dead import 정리나 기존 함수 시그니처 변경이 패치에 섞이지 않도록, (a) G9-2(a) 한 줄에 "표준은 이슈가 요구하는 변경 범위의 코드에 적용"을 포함.
- 원문: [standards/global/coding-style.md#L8-L10](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/standards/global/coding-style.md#L8-L10)

### G9-4
- 원래 행동: tasks.md 예시가 웹앱 계층(DB 모델·마이그레이션 → API 컨트롤러·인증 → UI 컴포넌트·반응형)으로 짜여 있고, "예시일 뿐이니 이 기능에 맞게 바꾸라"고 적혀 있다.
- 예시: Python 라이브러리 버그라면 group 이 1–2개(예: "CSV writer 수정")로 줄어드는지 smoke 에서 본다.
- 원문: [wf/implementation/create-tasks-list.md#L25-L186](https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/workflows/implementation/create-tasks-list.md#L25-L186)

## New text the port must write

- `docs/core-workflow.md` (G3-1): the four commands in order and their documents
  (`/agent-os/commands/<cmd>/<cmd>.md`); `S = /tmp/agent-os/specs/issue/` and what each command writes there
  (`planning/initialization.md`, `planning/requirements.md`, `spec.md`, `tasks.md` + ticks,
  `verifications/final-verification.html`, `checks/`); input = the issue (G1-1); "nobody is waiting: answer
  your own questions as recorded assumptions" (G4-1); no plain-text message before `finish` (G2-1); no
  fetching/installs (G6-1); nothing of the workflow in `/testbed` (G5-7); standards scope line (G9-2/G9-3, if
  chosen); tasks.md checkboxes are the record (G10-5); `finish` after the report (G8-1). Written fresh, not a
  paraphrase of speckit/openspec/aidlc entry docs (P5).
- Replacement lines inside the command documents (each tagged in build.py): next-command endings (G2-2),
  create-tasks PHASE 1 (G2-3), the self-answer rule and `(assumed)` answer form (G4-1), reuse-from-issue rule
  (G4-2), implement PHASE 1 "all groups" and PHASE 2 repeat rule (G4-4, G4-5), preamble wording (G7-2),
  product-context-from-repository (G1-3), initialization.md write (G1-2), `verifications/` folder (G5-5),
  roadmap-absent note (G7-8), test-suite scope (G8-2), `checks/` test sub-tasks (G9-1).
- `instruction.md` and `system-prompt.j2` procedure section (G10-1, G10-4), worded fresh.
- `LICENSE-agent-os` (MIT notice, `LICENSE:3-13`, required in copies; as `LICENSE-spec-kit`).

## Harness / dataset notes

- **Template render step (build).** `_port.py` reads each source and applies edits → sections → substitutions
  (`_port.py:146-161`); it has no `{{…}}` resolution. Options: (i) build.py copies the tag tree, applies the
  tagged `Edit`s to the **pre-render** sources (`cmd/*`, `wf/*`), runs upstream's own `project-install.sh`
  with `HOME=<tmp>` and the base `config.yml` edited as in `run-install.sh` (needs bash + perl,
  `scripts/common-functions.sh:664-687`; installer offline), then collects the four top-level files and the 15
  standards — exact upstream render, edits stay small (a shared workflow is edited once); (ii) re-implement the
  four tag kinds in build.py (`process_conditionals`, `process_workflows`, `process_standards`,
  `process_phase_tags`, `scripts/common-functions.sh:626-1019`) — no shell dependency, a second renderer to
  keep right; (iii) treat the rendered tree as `--upstream` and edit rendered text — simplest, but
  `git_head` on the render dir is not the tag (only a warning, `_port.py:233-235`) and every edit anchors on
  generated text. The survey recommends reading pre-render sources or reusing the installer logic (survey,
  "Agent-facing sources"). The engine change (a render hook between `convert` and output) is a shared
  `_port.py` change; record it in stage 4.
- **`frontmatter=False` is required.** `Port.frontmatter` defaults to True (`_port.py:82`) and
  `strip_frontmatter` raises `ValueError("no frontmatter")` when a file has none (`_port.py:94-98`); no Agent OS
  command, workflow or standard starts with `---` (e.g. `cmd/shape-spec/shape-spec.md:1`, `std/global/*.md:1`).
- **Section cuts are hazardous on these files** (`split_sections`, `_port.py:101-114`, splits only on unindented
  `## ` / `### `): (a) `R:shape` has `## Core Responsibilities` (R:13, R:102), `## Workflow` (R:21, R:111) and
  `## Important Constraints` (R:87, R:350) twice, and `apply_sections` matches by heading text
  (`_port.py:120-129`), so one `Section` cuts both; (b) `# PHASE N:` lines are not split points, so cutting
  `## User Standards & Preferences Compliance` at `R:impl:69` runs through `# PHASE 3: Verify Implementation`
  (`R:impl:89-91`) to `R:impl:93`, and cutting `## Important Constraints` at `R:shape:87` swallows
  `# PHASE 2: Shape Spec` (`R:shape:94-98`); (c) template headings inside unindented fences are split points
  (`R:shape:256-331`, `R:write:59-93`, `R:tasks:49-203`, `R:impl:128-203`). Use `Edit` anchors (or edit the
  pre-render sources, where the duplicates and PHASE lines do not exist yet). On pre-render sources the same
  heading occurs once per file, except the `{{UNLESS}}`-wrapped display blocks.
- `WorkflowSpec(docs_dir, container_dir="/agent-os"?, entry_doc="core-workflow.md", instruction_file,
  system_prompt={"openhands-sdk": …}, output_dirs=("/tmp/agent-os",))`, registered in
  `recipe/grpo/qwen3_5/workflows/__init__.py:21-28`. docs = 1 entry + 4 commands + 15 standards = 20 `.md`,
  checked at upload (`harness:323,385-394`). `container_dir` is a stray root (`harness:451`), so the spec
  folder must live elsewhere (proposed `/tmp/agent-os/`). No scripts, no `sandbox_files`, no `setup_script`,
  no agent-image extras needed (only `date`, `mkdir`, `ls`, `grep`, which the task images have).
- Run with `--hide-git-history`, `swegym293_aidlc`, `prefix` (lessons).
- Dataset fit: shape-spec frames the input as "a new feature" (`R:shape:1`); speckit_sdd, the other
  feature-shaped port, is used on feature tasks only (sdd usage note). Which dataset the smoke uses is a user
  decision (open question 10).
- No compliance scorer yet; the fixed paths make one possible later: `initialization.md`, `requirements.md`
  (Q/Answer pairs marked `(assumed)`), `spec.md` sections, `tasks.md` ticks, `checks/`, the report's four
  status lines.

## Open questions for the user

1. Names (G5-1, G5-2): documents at `/agent-os`, spec folder `/tmp/agent-os/specs/issue/`? Drop the date
   (fixed path, proposed) or keep `date` → `<YYYY-MM-DD>-issue`?
2. Shipped commands (G7-1): only the four compiled top-level files (proposed), or also the numbered PHASE files
   as separate documents?
3. Standards (G7-3): absolute-path list the agent opens as needed (proposed a), or inline the content into each
   command document (b)?
4. Product docs (G1-3, G7-8): read product context from the repository and record "no roadmap" (proposed), or
   delete shape-spec Step 2 / verification Step 2 as not applicable?
5. Q&A (G4-1, G4-2): self-answered questions recorded as `(assumed) <answer> — <basis>` (proposed); reuse
   question answered from the issue's own names only?
6. Full test suite (G8-2): changed-module tests (a, proposed), entire suite under a time cap (b), or verbatim
   (c)?
7. "DO NOT fix failing tests" (G8-3): end after the report (proposed), or one fix round for failures the change
   caused?
8. Standards conflicts (G9-2, G9-3): keep files verbatim + one scope line in the entry doc (proposed), or delete
   the team-process lines?
9. Implementation-report remnants (G5-6): delete the check and report section 2 (proposed), or keep verbatim?
10. Dataset for the smoke: SWE-Gym (bug-heavy) or a feature dataset, given shape-spec's "new feature" framing?
11. Report name (G5-5): keep `final-verification.html` verbatim (proposed) or `.md`?
12. Build (Harness notes): render by running upstream's installer (i, proposed), re-implement the tags (ii), or
    edit the rendered tree (iii)?

## Lines read

Rendered (`R:agent-os/`), all read line by line:

| File | Lines | Read |
|---|---|---|
| `commands/shape-spec/shape-spec.md` | 395 | all |
| `commands/shape-spec/1-initialize-spec.md` | 95 | all (1-85 = `R:shape:9-93` by diff; 86-95 own block) |
| `commands/shape-spec/2-shape-spec.md` | 300 | identical to `R:shape:96-395` (diff) |
| `commands/write-spec/write-spec.md` | 134 | all |
| `commands/create-tasks/create-tasks.md` | 254 | all |
| `commands/create-tasks/1-get-spec-requirements.md` | 19 | all |
| `commands/create-tasks/2-create-tasks-list.md` | 234 | identical to `R:tasks:21-254` (diff) |
| `commands/implement-tasks/implement-tasks.md` | 203 | all |
| `commands/implement-tasks/1-determine-tasks.md` | 13 | all (= `R:impl:13-25`, diff) |
| `commands/implement-tasks/2-implement-tasks.md` | 59 | all (= `R:impl:29-87`, diff) |
| `commands/implement-tasks/3-verify-implementation.md` | 113 | all (= `R:impl:91-203`, diff) |
| `standards/**` (15 files) | 163 | all |
| `config.yml` | 13 | all |
| **Σ rendered** | **1,995** | |

Pre-render sources (upstream checkout): `cmd/shape-spec/{shape-spec,1-initialize-spec,2-shape-spec}.md`
9+15+35, `cmd/write-spec/write-spec.md` 23, `cmd/create-tasks/{create-tasks,1-get-spec-requirements,2-create-tasks-list}.md`
9+21+23, `cmd/implement-tasks/{implement-tasks,1-determine-tasks,2-implement-tasks,3-verify-implementation}.md`
15+13+31+19 — all read (213). Workflows `wf/specification/{initialize-spec,research-spec,write-spec}.md`
82+262+99, `wf/implementation/create-tasks-list.md` 199, `implement-tasks.md` 16,
`verification/{verify-tasks,update-roadmap,run-all-tests,create-verification-report}.md` 9+1+5+80 (753):
initialize-spec, implement-tasks and the three short verification files read directly; all nine confirmed
byte-identical to their rendered spans by `diff`, so read through the rendered files; research-spec also
read directly at `:1-50,88-160,230-262` for line numbers. `std/**` identical to the rendered copies (`diff -r`).
`CHANGELOG.md:80-90`.

rllm side read: `.claude/skills/port-workflow/stages/2-gaps.md`, `references/{checklist,lessons,principles}.md`;
`workflows/{speckit_bug,speckit_sdd,openspec_ff}/porting/03-decisions.md`, `speckit_sdd/porting/02-gaps.md`;
`workflows/_port.py` (all 247), `workflows/spec.py` (all 84), `workflows/__init__.py:21-28`,
`workflows/speckit_bug/system-prompt.j2` (grep: `:48,60-72,171`), `workflows/speckit_sdd/build.py:177-236`
(Section use), `workflows/speckit_sdd/docs/core-workflow.md:1-30`; `prepare_swegym.py:84,105-116,155-213,248`;
`harness:249-250,288-323,367-401,443-451` (grep); `runner:92-149` (grep); `config/config.yaml:68`,
`config/variant/openhands_9b_aidlc_swegym.yaml:66`; openhands-sdk in `rllm-agent-f268c8df48c7` (grep for `@`
expansion, read-only).
