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
| G2-5 | verify's final assessment routes by the round rule (G8-1) | env | user 2026-10-13 | batch B; rule itself pending |
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

| G8-1 | verify rounds: `verify.md`; any CRITICAL → back to apply for those items only → `verify-2.md`; at most 2 verify rounds, then archive regardless with what is left recorded; WARNING/SUGGESTION never loop | loop | user 2026-10-13 | semantic ⑤; Q3 answered |

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
| G2-9 | entry document: the verify row says no `openspec` command performs verify; archive only once `verify.md` / `verify-2.md` exists | env | user 2026-10-14 | smoke run 2: agents read "Starts from `openspec status`" as the verify step |
| G8-5 | deferred: no rule change; re-check after G7-5 (every over-limit retry began with a MODIFIED failure) | env | user 2026-10-14 | if it persists: forbid deleting specs / `skip_specs` to get past archive |

| D-7 | Process revised to **ff → apply → verify → archive**: the new stage is not shipped. ff's own step 2 (upstream) runs `openspec new change "issue"`, so the change is created there; upstream documents new → ff only as an optional two-step split (`docs/getting-started.md:165`) | — | user 2026-10-14 | drops G1-3, G2-1, G4-12 (new-only rows); G7-1 reverts to upstream's ff step 2 (its "already exists → suggest continuing" line stays dropped: a hand-back that cannot fire in a fresh sandbox); G1-1 / G5-1 now apply to ff only; stage docs renumbered 01-ff, 02-apply, 03-verify |

| G7-6 | no change (option c). None of our edits points toward MODIFIED: the only edits touching delta kinds are G7-5's "ADDED" sentences, and upstream's own MODIFIED steps start from an existing requirement in `openspec/specs/`. The think-on agents misread both; they recover through the archive error under G8-4. G7-5 stays (it fixed think off: 2/3 → 0/3 first-archive failures) | env | user 2026-10-14 | the `docs/writing-specs.md` rule ("against the current spec") was considered and not added |

| G10-7 | option (a): `setup.sh` installs the package's `sandbox/openspec-config.yaml` as `/openspec/config.yaml` — `schema: spec-driven-sandbox`, a `context:` of environment facts (repo `/testbed`, planning home outside it, one issue, test files in place and not edited, no installs/network, checks dir, specs start empty) and `rules` for proposal and specs (G7-5's two sentences, moved out of the fork). No `operations` guidance. Written so nothing restates or contradicts the schema's instructions: apply's conflict branches (`02-apply.md` "report the conflict" / "explain why") have nothing to fire on and stay verbatim | env | user 2026-10-14 | verified with the CLI: context in every artifact + apply, rules only for proposal/specs, `operationGuidance` null, no config warnings; the fork now differs from upstream only by edits that delete or replace upstream sentences |

| G9-4 (rev.) | example 1.2 reworded to cover fixes and features alike: "…and verify it fails against the current code (it should pass once the change is in)" — replaces "…verify it runs against the current code (for a fix: verify it reproduces the reported failure first)" | semantic | user 2026-10-14 | a check written before the change fails for a missing feature as for a bug; matches the planned task-kind-neutral compliance signal |

## Behaviors the port adds

- Verify rounds (G8-1): at most 2; files `verify.md`, `verify-2.md` in `/openspec/changes/issue/`; loop only on CRITICAL, on the CRITICAL items only; after round 2, archive regardless.
- Archive (D-5, G8-4): the agent runs `openspec archive issue --yes` after the last verify; exit 1 → fix only what the error names in the delta spec (or write the missing spec), rerun once; still failing → `finish` without archive.

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
