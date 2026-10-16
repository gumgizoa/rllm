# Decisions: OpenSpec  (upstream Fission-AI/OpenSpec@9111a76, process new → ff → apply → verify → archive)

Complete 2026-10-13 (G10-6 added and decided 2026-10-14): every row of `02-gaps.md` is decided or dropped.

| ID | Decision | Tag | Decided | Notes |
|---|---|---|---|---|
| D-1 | The real `openspec` CLI (npm `@fission-ai/openspec@1.14.1`, node v22) runs in the sandbox, and the planning root is created before the agent starts with `cd / && openspec init --tools none` | — | user 2026-10-13 | replaces inlining the CLI-served text; makes the root guard, paths, status/instructions, validation and archive upstream-verbatim (`02-gaps.md` "Upstream text that works as is") |
| D-2 | Delivery: a separate content-addressed agent image (openhands-sdk image + node/CLI bundle), used only by workflows that ask for it | — | user 2026-10-13 | other workflows keep their current image; needs the tag hash to cover the bundle |
| D-3 | Process: new → ff → apply → verify → archive (`docs/getting-started.md:47`), with sync run inline by archive | — | user 2026-10-13 | `01-survey.md` "Process chosen" |
| D-5 | Archive = the agent runs `openspec archive issue --yes` once after verify, then calls `finish` — upstream's CLI path ("skips confirmation prompts. It still validates, then applies any delta specs and archives", `docs/workflows.md:97`; verified `cli-probe/02`). The archive and sync skills are not shipped | — | user 2026-10-13 | drops G4-8..G4-11; revises G2-6, G2-8; failure rule pending |
| D-4 | Text the CLI serves from `schema.yaml` is changed through upstream's project-local schema (`openspec schema fork spec-driven <name>`, selected by `config.yaml` `schema:`), not by overriding it in the stage documents | — | user 2026-10-13 | applies to G4-3, G4-4, G9-1, G9-2, G9-4; edits tagged in `build.py` |
| G1-1 | input = the issue in `<issue_description>` (what to build or fix); the "ask what they want to build" branch dropped | env | user 2026-10-13 | batch A |
| G1-2 | auto-select of the single change kept; the ask-to-select branch and the "how to override (`/openspec-…-change <other>`)" hint dropped | env | user 2026-10-13 | batch A |
| G1-3 | default schema path kept (resolves to the fork via `config.yaml`); the choose-a-schema branch dropped | env | user 2026-10-13 | batch A |
| G2-1 | new: "once the change exists, open the ff stage document and continue"; STOP / prompt / "do not advance" lines replaced | env | user 2026-10-13 | batch B |
| G2-2 | ff: "after the last artifact, open the apply stage document and continue" | env | user 2026-10-13 | batch B |
| G2-3 | apply `blocked`: "go back to the ff stage document, create the missing artifacts, resume apply" | env | user 2026-10-13 | batch B |
| G2-4 | apply `all_done`: "open the verify stage document and continue" | env | user 2026-10-13 | batch B |
| G2-5 | verify's final assessment → "go to the archive step" (no round rule since G8-1 was dropped 2026-10-14) | env | user 2026-10-13, rev. 2026-10-14 | batch B |
| G2-6 | ~~archive summary written into the archived change dir, then `finish`~~ → superseded by D-5: the CLI prints the summary; the agent calls `finish` | env | user 2026-10-13 | batch B, revised by D-5 |
| G2-7 | entry document: progress notes go with a tool call or into the artifacts; no tool-less message before `finish` | env | user 2026-10-13 | batch B |
| G2-8 | ~~sync shipped as a stage document~~ → superseded by D-5: no archive or sync document is shipped | env | user 2026-10-13 | batch B, revised by D-5 |
| G4-1 | ff: "the target project is `/testbed`"; ask dropped, "state the limitation" kept | env | user 2026-10-13 | batch C |
| G4-12 | new: invalid-name ask dropped | env | user 2026-10-13 | batch C |
| G5-1 | change name fixed `issue` | env | user 2026-10-13 | batch D |
| G5-2 | documents at a filesystem-root directory distinct from `/openspec` | env | user 2026-10-13 | batch D; name pending (Q2) |
| G5-3 | verify report written to a file in the change dir | env | user 2026-10-13 | batch D; file names pending (Q3) |
| G7-1 | ff step 2 → "the change was created by the new stage; continue it"; "already exists → suggest continuing" guardrail dropped | env | user 2026-10-13 | batch E |
| G7-2 | skill frontmatter stripped | env | user 2026-10-13 | batch E |
| G7-3 | store paragraph handled per Q7 | env | user 2026-10-13 | batch E; keep/trim pending (Q7) |
| G7-4 | one statement that every delta is ADDED for a new capability; dead branches per Q7 | env | user 2026-10-13 | batch E; keep/trim pending (Q7), skip_specs (Q5) |
| G8-2 | per-task checkbox flow kept as upstream; step count measured in the smoke | env | user 2026-10-13 | batch F |
| G8-3 | archive last, then `finish`; entry document: repo change complete before archive | env | user 2026-10-13 | batch F |
| G4-2 | ff: take the most plausible reading, record it as an assumption in the artifact being written, continue | semantic | user 2026-10-13 | semantic ① |
| G4-3 | forked schema (design, tasks instructions): resolve plan-changing questions yourself, write the choice and its rationale under **Decisions**; Open Questions keeps only deferrable unknowns | semantic | user 2026-10-13 | semantic ①; replaces "ask the user instead of guessing" |
| G4-4 | apply document + forked schema apply instruction: implement the most plausible reading against specs/design, note it under the task in `tasks.md` (plain line, not a checkbox) | semantic | user 2026-10-13 | semantic ① |
| G4-5 | apply: update the affected artifact (design / specs / tasks) yourself, record what changed and why, continue | semantic | user 2026-10-13 | semantic ① |
| G4-6 | apply: add extra work as tasks in `tasks.md` (and to the delta spec when observable), then do it; never narrow specified behavior | semantic | user 2026-10-13 | semantic ① |
| G4-7 | apply: try to resolve; a task that stays impossible is left unchecked with a one-line reason, the rest continues; interrupt / pause blocks dropped | semantic | user 2026-10-13 | semantic ① |
| G8-4 | archive exit 1 → fix only what the error names in the delta spec (format; or write the missing spec), rerun `openspec archive issue --yes` once; still failing → `finish` without archive. No `--no-validate` (upstream: "not recommended"), no return to tasks/apply (the code is done; content is verify's job) | semantic | user 2026-10-13 | found in stage 3 |
| G6-1 | entry document: no opening links in the issue, no online lookups, no package installs. `schema:18` Impact ("Affected code, APIs, dependencies, or systems") kept verbatim — a record field, not an instruction; the `schema:245` example is handled with G9-4 | semantic | user 2026-10-13 | semantic ③ |
| G9-1 | forked schema, tasks instruction: keep "Each task MUST state how to verify completion"; replace "land the tests" with verification by existing repo tests or a check script under `/openspec/changes/issue/checks/`; no test files added or edited in `/testbed` (exact text below) | semantic | user 2026-10-13 | semantic ④ |
| G9-2 | same item: repository documentation (README, docs/, changelogs) changed only when the issue asks; comments/docstrings in changed code are part of the code (exact text below) | semantic | user 2026-10-13 | semantic ④ |
| G9-3 | verify document, scenario coverage: "tests exist" → "verified by an existing test or a `checks/` script"; recommendation → "add a check under `checks/` or fix the code" | semantic | user 2026-10-13 | semantic ④ |
| G9-4 | design "New external dependency" condition kept verbatim; tasks example lines 1.2 / 2.2 / 2.3 replaced (exact text below), export example and "… and verify …" form kept | semantic | user 2026-10-13 | semantic ④ |
| D-6 | One version for features and bug fixes: the agent reads the issue; no split by task kind (upstream handles both with one schema, `skip_specs` per change) | — | user 2026-10-13 | variants are the variation pipeline's job |
| Q1 (part) | checks directory = `/openspec/changes/issue/checks/` (verified: validate/archive pass, moves with the change, `cli-probe/04`) | — | user 2026-10-13 | fork schema name still open |

| G8-1 | ~~verify rounds: `verify.md`; any CRITICAL → back to apply for those items only → `verify-2.md`; at most 2 verify rounds~~ → **dropped 2026-10-14**: verify runs once, writes `verify.md`, then archive | — | user 2026-10-13, dropped 2026-10-14 | val ablation (`06-smoke.md`): round-1 CRITICAL 0/60, the loop never fired; verify judges against the agent's own tasks/specs, so a wrong fix still reads "no critical issues" |

| Q1 | fork schema name `spec-driven-sandbox` (no dataset names) | — | user 2026-10-13 | |
| Q2 | documents at `/opsx`; workflow name `openspec_ff` | — | user 2026-10-13 | G5-2 |
| Q5 | `skip_specs` rule kept verbatim (`schema:36-42`): only when no spec-level behavior changes; the agent decides | — | user 2026-10-13 | no edit |
| Q6 / G10-2 | SDK default "ask the user" / "confirm with the user" lines kept, for comparability | — | user 2026-10-13 | as speckit_bug |
| Q7 | store-selection paragraph dropped (conditional machinery, no-op here, like speckit's hooks); MODIFIED / REMOVED / RENAMED text kept verbatim (format semantics, partly CLI-served) | env | user 2026-10-13 | G7-3, G7-4 |
| G3-1 | hand-written `docs/core-workflow.md` | (new text) | user 2026-10-13 | |
| G10-1 | system prompt procedure section written fresh | — | user 2026-10-13 | |
| G10-3 | `swegym293_aidlc` + `instruction_position=prefix` | — | user 2026-10-13 | |
| G10-4 | instruction: first action = open `/opsx/core-workflow.md`; the directory is at the filesystem root, outside the repo | — | user 2026-10-13 | |
| G10-5 | sandbox setting (a) agent image with node + CLI, (b) setup: `openspec init --tools none` at `/`, fork schema installed + selected in `config.yaml`, wrapper with telemetry/update-check off, fail if `/testbed/openspec` exists, (c) `WorkflowSpec` fields + `output_dirs=("/openspec",)` | — | user 2026-10-13 | |

| G10-6 | the `openspec` wrapper sets `CI=1` (upstream's non-interactive switch); `setup.sh` checks `openspec new change` returns under a TTY (`script -qec`, 60 s) | env | user 2026-10-14 | found in stage 6 run 1 |

| G7-5 | forked schema: proposal Capabilities and specs instruction each say `/openspec/specs/` starts empty, so every capability is New and every delta is `## ADDED Requirements` (a fix states the corrected behavior as a new requirement); upstream's MODIFIED text kept | env | user 2026-10-14 | option 2 of three (pre-generated specs / assume none / add a spec-writing stage): upstream's own brownfield path (`docs/existing-projects.md:3,33,65,123`); option 1 noted in `later.md` |
| G2-9 | entry document: the verify row says no `openspec` command performs verify; archive only once `verify.md` exists | env | user 2026-10-14 | smoke run 2: agents read "Starts from `openspec status`" as the verify step |
| G8-5 | deferred: no rule change; re-check after G7-5 (every over-limit retry began with a MODIFIED failure) | env | user 2026-10-14 | if it persists: forbid deleting specs / `skip_specs` to get past archive |

| D-7 | Process revised to **ff → apply → verify → archive**: the new stage is not shipped. ff's own step 2 (upstream) runs `openspec new change "issue"`, so the change is created there; upstream documents new → ff only as an optional two-step split (`docs/getting-started.md:165`) | — | user 2026-10-14 | drops G1-3, G2-1, G4-12 (new-only rows); G7-1 reverts to upstream's ff step 2 (its "already exists → suggest continuing" line stays dropped: a hand-back that cannot fire in a fresh sandbox); G1-1 / G5-1 now apply to ff only; stage docs renumbered 01-ff, 02-apply, 03-verify |

| G7-6 | no change (option c). None of our edits points toward MODIFIED: the only edits touching delta kinds are G7-5's "ADDED" sentences, and upstream's own MODIFIED steps start from an existing requirement in `openspec/specs/`. The think-on agents misread both; they recover through the archive error under G8-4. G7-5 stays (it fixed think off: 2/3 → 0/3 first-archive failures) | env | user 2026-10-14 | the `docs/writing-specs.md` rule ("against the current spec") was considered and not added |

| G10-7 | option (a): `setup.sh` installs the package's `sandbox/openspec-config.yaml` as `/openspec/config.yaml` — `schema: spec-driven-sandbox`, a `context:` of environment facts (repo `/testbed`, planning home outside it, one issue, test files in place and not edited, no installs/network, checks dir, specs start empty) and `rules` for proposal and specs (G7-5's two sentences, moved out of the fork). No `operations` guidance. Written so nothing restates or contradicts the schema's instructions: apply's conflict branches (`02-apply.md` "report the conflict" / "explain why") have nothing to fire on and stay verbatim | env | user 2026-10-14 | verified with the CLI: context in every artifact + apply, rules only for proposal/specs, `operationGuidance` null, no config warnings; the fork now differs from upstream only by edits that delete or replace upstream sentences |

| G9-4 (rev.) | example 1.2 reworded to cover fixes and features alike: "…and verify it fails against the current code (it should pass once the change is in)" — replaces "…verify it runs against the current code (for a fix: verify it reproduces the reported failure first)" | semantic | user 2026-10-14 | a check written before the change fails for a missing feature as for a bug; matches the planned task-kind-neutral compliance signal |

## Behaviors the port adds

- Verify once: `verify.md` in `/openspec/changes/issue/`, then archive (the G8-1 round rule was dropped 2026-10-14).
- Archive (D-5, G8-4): the agent runs `openspec archive issue --yes` after verify; exit 1 → fix only what the error names in the delta spec (or write the missing spec), rerun once; still failing → `finish` without archive.

## Agreed text for the forked schema

Replaces `schema.yaml:230-236` (tasks instruction item):

```text
- Each task group MUST verify its own work as it lands: run the existing repository
  tests that cover it, or write a check script under /openspec/changes/issue/checks/
  and run it. Do NOT add or edit test files in the repository - the task's tests are
  already in place. Change repository documentation (README, docs/, changelogs) only
  when the issue asks for it; comments and docstrings in the code you change are part
  of that code. Do NOT collect verification into a final group - when a late group
  first exercises work from an early one, the failures cascade back through every
  group in between and force rework. A group whose work calls for no verification,
  such as scaffolding, carries none. A final group is for integration checks only.
```

Replaces the example lines 1.2, 2.2, 2.3 (`schema.yaml:245,249-250`); 1.1 and 2.1 unchanged:

```text
- [ ] 1.2 Write a check script at /openspec/changes/issue/checks/export_check.py that calls the export entry point and verify it fails against the current code (it should pass once the change is in)
- [ ] 2.2 Add CSV formatting utilities and verify the existing CSV tests and export_check.py pass with quoting and delimiters
- [ ] 2.3 Run the test module covering the export code and verify no existing test regresses
```

## Explore extension (stage 3, from 2026-10-15)

Process becomes explore → ff → apply → verify → archive (user 2026-10-15); explore's no-code rule kept as
upstream has it (user 2026-10-15). Rows from `02-gaps.md` "Explore extension". Upstream intent used as
evidence: `docs/existing-projects.md:41,51-57,90,99` (added at the user's request).

| ID | Decision | Tag | Decided | Notes |
|---|---|---|---|---|
| G1-4 | explore's input = the issue in `<issue_description>` ("User brings a specific problem", `explore:235-264`); the issue is source material for exploration (`docs/existing-projects.md:90`) | env | user 2026-10-15 | precedent openspec_ff G1-1 |
| G2-10 | every hand-off to `/openspec-propose` (`explore:14,162,318,335,345`) → "when exploration is done, open `/opsx/stages/01-ff.md` and continue: ff turns what you found into a change" | env | user 2026-10-15 | precedent openspec_ff G2-2; shares the `:14` / `:345` sentences with G4-16 (one edit per sentence, both IDs in the note) |
| G2-11 | every note, diagram and summary of explore rides in a turn that also makes a tool call (`core-workflow.md:49-50` rule) | env | user 2026-10-15 | precedent openspec_ff G2-7 |
| G3-2 | `core-workflow.md`: explore as the first action (actions table row, chain line `explore ──► ff ──► …`, the read/run line names explore with its no-code rule) | new text | user 2026-10-15 | precedent openspec_ff G3-1; wording follows G9-5's decision |
| G4-16 | `explore:14` "If the user asks you to implement something … point them at `/openspec-propose` …" → "The task asks you to implement a fix; that request is carried out later in this session by the ff and apply actions, not here: do not start it in explore mode. The work happens from the change ff creates, never from explore mode."; `explore:345` last sentence → "When exploration is done, open `/opsx/stages/01-ff.md` rather than starting to build: ff turns what you found into a change, and the work happens there." "NEVER write code or implement features" (`:14`, `:345`) unchanged | env | user 2026-10-15 | the task message itself asks to implement (`scripts/prepare_swegym.py:176`); a literal refusal is a text-only end. Wording final in 03-plan |
| G4-17 | drop the capture transition and "When a change exists" (`explore:150-195`) and the mid-implementation example (`:266-281`) | env | user 2026-10-15 | precedent openspec_ff G1-2; **conditional on G4-13 (a)** — revisit if G4-13 takes (b) |
| G7-7 | store paragraph (`explore:18`) dropped by the existing `_STORE` edit | env | user 2026-10-15 | precedent openspec_ff G7-3 |
| G7-8 | frontmatter stripped (`Port.frontmatter`) | env | user 2026-10-15 | precedent openspec_ff G7-2 |
| G7-9 | `openspec list --json` / `list --specs` / `show` and the raw config.yaml read (`explore:122-146`) kept verbatim; probe `openspec list --specs` (+ `--json`) on the empty tree under `script -qec` with the wrapper before the smoke | env | user 2026-10-15 | P5; probe result goes to `cli-probe/` |
| G10-8 | `instruction.md` and the system prompt's procedure section name explore first; first action stays "open `/opsx/core-workflow.md`" | — | user 2026-10-15 | precedent openspec_ff G10-1, G10-4; fresh text |
| G4-14 | keep `explore:48` verbatim ("Before asking a factual question … inspect … Do not ask the user to repeat facts you can verify"); a question only the person could answer → take the most plausible reading of the issue, mark it as an **assumption** in explore's summary, continue; ff writes it into the proposal | semantic | user 2026-10-15 | precedent openspec_ff G4-2, speckit_bug G4-3; `build.py` `FORBIDDEN` "ask the user" needs a per-source allowance for `explore:48` |
| G4-15 | the agent states its preferred option with alternatives and reasons (`explore:52` format) and carries it to ff, where design.md **Decisions** records choice, rationale, alternatives; a suggested spike → a specific open question for ff's discovery (`ff:78`) | semantic | user 2026-10-15 | precedent openspec_ff G4-3 |
| G4-13 | explore writes nothing: the offer ("Want me to create a proposal?") and the yes/no write question dropped; ff creates the change as now (D-7 unchanged) | semantic | user 2026-10-15 | upstream's outcome when no yes comes ("Silence is not acceptance", `explore:53`); P2, P4. User may revisit (b) — explore scaffolds the change as a capture request, ff step 2 changed — after the last smoke |
| G2-12 | explore always ends with upstream's "What We Figured Out" summary (`explore:323-339`) in the turn that opens the ff document: the problem, how the area works, where the change goes (preferred option + alternatives), assumptions, open questions — each with its evidence (`file:line` read, command output) | semantic | user 2026-10-15 | P2 (upstream's own output, made always), P3 (checkable in the trajectory); content follows `docs/existing-projects.md:51-57`. ff grounds proposal Why / design Context, Decisions in it |
| G8-6 | explore ends once the summary's problem and where-the-change-goes can be stated with evidence; open questions may stay open; no step cap | semantic | user 2026-10-15 | P2; explore's step count measured in the smoke (ff → archive took 53–111 steps) |
| G9-5 | allowed in explore: reading, searching, running existing code and existing tests, running the issue's own example exactly as given; not allowed: any code the agent composes (one-line `python -c` / stdin snippets included) and any file write (repo, `/tmp`, `checks/`, redirection, heredoc) | semantic | user 2026-10-15 | literal "NEVER write code" (`explore:14,345`) + "commands that write files" (`:349`); P2. Run by-products (`__pycache__`, `.pytest_cache`) are not the agent's writes. Varying the issue's example is left to ff/apply (`checks/`) |
| G4-18 | entry-point examples: keep only "User brings a specific problem" (`explore:235-264`); its closing question becomes the summary of G2-12; the other three dropped | semantic | user 2026-10-15 | P4; precedent speckit_sdd G7-7 |
| G2-13 | ff kept verbatim ("reuse findings for later artifacts and inspect more only as needed", `ff:74-78`); measure ff's inspection after explore in the smoke | env | user 2026-10-15 | P2; upstream's explore → propose path meets the same text (`propose:123`) |
| G5-4 | explore stage document = `docs/stages/00-explore.md`; 01–03 not renumbered | env | user 2026-10-15 | no path changes in build.py / tests / README for the existing stages |
| G10-9 | config `context` line → "From the ff action on, scripts written to reproduce or check behavior live in /openspec/changes/issue/checks/." | env | user 2026-10-15 | still a fact (G10-7); no conflict with G9-5 |
| G7-10 | drop explore's "Don't manually scaffold changes" guardrail (`explore:350`) together with the capture text (G4-17): explore never scaffolds a change, and the line would show `openspec new change "issue"` in a stage that writes nothing | env | user 2026-10-15 | found in stage 4; P4; `later.md` "Explore scaffolds the change itself" says to restore it if G4-13 (b) is taken |
| G4-19 | keep the "Planning a Change" example (`explore:57-64`), its scope question rewritten as an assumption drawn from evidence, with what changes if it is wrong: "… Nothing in the issue or the code needs state shared across devices, so I assume a single-device tool (assumption, with that evidence). On that reading I recommend keeping SQLite; if the assumption is wrong, shared state needs a separate sync design." | semantic | user 2026-10-15 | found in stage 4; P2 (inspect → evidence → conditional recommendation kept), consistent with G4-14; wording avoids a default-narrow assumption (cf. scikit-learn-25102 lock-in). Wording final in 03-plan |
| G9-6 | keep G9-5's boundary and make it harder to miss: name agent-composed code run through `python -c` or a heredoc/stdin piped to python as writing code, in 00-explore.md (the Stance sentence at `explore:14` and the Guardrails "Don't implement" line at `:345`) and in core-workflow's explore rule; reproduction is left to ff/apply (`checks/`), as upstream leaves experiments to tasks (spike task, `explore:280`; tests per task, `schema.yaml:225-231`) | semantic | user 2026-10-16 | found in stage 6 (run 5: composed code 7/7, `/tmp` scripts 1/7); P2 over P1 by the user's choice (fidelity to upstream explore); measure again in the next smoke |
| G2-14 | G2-12's placement sentence → the summary is written in a tool call (e.g. `think`) before the tool call that opens `/opsx/stages/01-ff.md`, not necessarily in the same turn | env | user 2026-10-16 | found in stage 6 (run 5: 5/6 summaries in a `think` call 1–14 turns earlier; the rule's reason, a text-only turn, does not arise); P3: checkable as "a tool call before the first 01-ff.md open holds the summary". Missing summaries (2/4 think on) watched in the next smoke |

Explore extension: every row decided 2026-10-15 (G7-10, G4-19 added from stage 4). Later idea recorded: `later.md` "Explore scaffolds the change itself".
