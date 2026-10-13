# Decisions: speckit_bug  (upstream github/spec-kit@0443760, bug extension 1.0.1)

This port was done in conversation (2026-10-12) before the staged procedure existed, so there is no
01-survey.md / 02-gaps.md. Gap IDs use these types: G1 input, G2 hand-off, G3 entry document,
G4 interactive branches, G5 paths & IDs, G6 network, G7 machinery, G8 loops & ends, G9 task conflicts,
G10 harness & dataset.
All rows decided by the user, 2026-10-12.

| Gap ID | Upstream | Decision | Tag |
|---|---|---|---|
| G1-1 | `## User Input` / `$ARGUMENTS` in all three commands | assess: input = the issue in `<issue_description>`; fix/test: section replaced by the round table | env |
| G1-2 | "Invalid / not a bug" path | the issue is a requirement to meet; no `invalid` verdict or exit | semantic |
| G2-1 | `## Completion Report` "Report back … next suggested step" | "do not report; read the next stage document and continue" | env |
| G2-2 | `__SPECKIT_COMMAND_*__` references; "stop and instruct the user to run X first" | stage document paths; "carry out X first" | env |
| G3-1 | no agent-facing document strings the commands together (person / `workflow.yml` does) | hand-written `docs/core-workflow.md` | (new text) |
| G4-1 | slug: ask the user / generate / disambiguate | slug fixed `issue`; sections dropped | env |
| G4-2 | overwrite: ask / pick a new slug / refuse | each report written once; corrections go to the fix report's Deviations | env |
| G4-3 | fix: `[NEEDS CLARIFICATION]` → ask or stop | take the most plausible reading, record it as an assumption, proceed | semantic |
| G4-4 | fix: wrong assessment → STOP, recommend re-assess | record under Deviations, continue from the corrected cause | semantic |
| G4-5 | test: skip destructive / network / **expensive** checks without consent | only destructive / network skipped; repo tests for changed modules expected | semantic |
| G4-6 | `review-assessment` gate (`workflows/bugfix/workflow.yml`) | none (no approver) | env |
| G5-1 | `.specify/bugs/<slug>/` inside the repo | `/tmp/speckit/bugs/issue/`; docs at `/speckit` | env |
| G6-1 | URL Trust Policy: github.com etc. fetched without asking | no fetching or online lookup; links recorded `[UNVERIFIED — not fetched]` | semantic |
| G7-1 | `## Pre-Execution Checks` / `## Mandatory Post-Execution Hooks` (`.specify/extensions.yml`) | dropped (no-op without the file; 216 lines) | env |
| G8-1 | test `failed` → "re-run assess" for the person | fix↔test rounds, at most 3 | loop |
| G9-1 | fix: add/update repository tests | write checks under `/tmp/speckit/bugs/issue/checks/`; run existing repo tests only | semantic |
| G9-2 | fix guardrail "never modify files outside the project workspace" | "outside the repository, except this workflow's reports and checks" | env |
| G10-1 | SDK default `<PROBLEM_SOLVING_WORKFLOW>` | rewritten (paraphrased, not aidlc_v4 wording) | — |
| G10-2 | SDK default "confirm with the user" / "ask the user for clarification" | kept for comparability with `none` / aidlc_v4 | — |
| G10-3 | SWE-Gym prompt's six-step procedure | `swegym293_aidlc` + `instruction_position=prefix` | — |

## Behaviors the port adds
- Rounds: after `test*.md`, `verified` ends; `partial`/`failed` in round 1–2 → next fix; round 3 ends
  regardless. Files: `fix.md`/`test.md`, `fix-2.md`/`test-2.md`, `fix-3.md`/`test-3.md`; fix reports
  carry `Round` and `Previous verification` fields.

## Names and paths
- workflow `speckit_bug`; `container_dir=/speckit`; reports `/tmp/speckit/bugs/issue/`; checks
  `/tmp/speckit/bugs/issue/checks/`; slug `issue`.

## Answered questions
1. Process: bug extension first (SDD later, if ever) — closest to SWE tasks, ~630 upstream lines.
2. Fidelity: keep upstream text, remove noise; hand-written text only where upstream has none.
3. Instruction and procedure section paraphrased so they do not share aidlc_v4's wording (generalization).
