# Decisions: speckit_sdd  (upstream github/spec-kit@0443760, SDD minimal chain)

Scope (01-survey.md, "Scope decided", user 2026-10-13): minimal chain specify → plan → tasks → implement ⇄
converge; plan Phase 1 kept, conditional.

| Gap ID | Decision | Tag | Decided | Notes |
|---|---|---|---|---|
| G1-1 | specify: input = the issue in `<issue_description>`; other stages: input section dropped; `tpl/spec:9` → "the issue in the task message" | env | user 2026-10-13 (env batch) | as speckit_bug G1-1 |
| G1-3 | plan: no input; Technical Context filled from the repository (build files, CI config, installed env) | env | user 2026-10-13 (env batch) | |
| G2-1 | Completion Report → "do not report; open the next stage document and continue" | env | user 2026-10-13 (env batch) | as bug G2-1 |
| G2-2 | `__SPECKIT_COMMAND_*__` → stage document paths; "STOP / suggest running X first" → "carry out X first" | env | user 2026-10-13 (env batch) | as bug G2-2 |
| G2-3 | references to clarify / checklist / analyze dropped; requirements.md "maintained by the specify stage"; `:146` → "using the structure below" | env | user 2026-10-13 (env batch) | scope |
| G2-4 | no plain-text output mid-workflow; converge writes findings, metrics and outcome to its round report; implement progress = `[X]` only; specify warnings → checklist Notes | env | user 2026-10-13 (env batch) | new vs bug |
| G3-2 | entry doc lists only the minimal chain | env | user 2026-10-13 (env batch) | scope |
| G4-3 | specify's 3-iteration self-validation kept; "warn user" → record in checklist Notes and continue | env | user 2026-10-13 (env batch) | new vs bug |
| G4-7 | workflow.yml review gates: none | env | user 2026-10-13 (env batch) | as bug G4-6 |
| G5-1 | artifacts outside the repo (FEATURE_DIR under the workflow's `/tmp/...` root, D-4) | env | user 2026-10-13 (env batch) | as bug G5-1; root name in D-4 |
| G5-2 | feature dir fixed `001-issue`; name/number generation, init-options, timestamp dropped; create-new-feature.sh not shipped | env | user 2026-10-13 (env batch) | differs from bug (numbered dir, not slug) |
| G5-3 | `/memory/constitution.md` → `<docs root>/memory/constitution.md`; `/contracts/` → `FEATURE_DIR/contracts/`; template = copy from `<docs root>/templates/` (no resolution stack) | env | user 2026-10-13 (env batch) | pre-render paths |
| G5-4 | entry doc states who writes what; after their stage spec.md / plan.md are not rewritten; tasks.md changes only by `[X]` (implement) and appended Convergence phases (converge) | env | user 2026-10-13 (env batch) | bug's write-once rule does not carry over |
| G5-5 | entry doc: scratch/check scripts go to `FEATURE_DIR/checks/`; nothing of the workflow is written into `/testbed` | env | user 2026-10-13 (env batch) | bug smoke finding (open in bug) |
| G7-1 | hook blocks dropped, incl. converge's `### 9.` step (separate cut, not a `##` section) | env | user 2026-10-13 (env batch) | as bug G7-1 |
| G7-2 | scripts not shipped — **pending D-3**; if (a): each stage doc states FEATURE_DIR and does the script's job in prose | env | user 2026-10-13 (env batch, variant pending D-3) | |
| G7-3 | script error hints: none under (a) | env | user 2026-10-13 (env batch) | follows D-3 |
| G7-4 | Branch fields = `001-issue`; commit line dropped | env | user 2026-10-13 (env batch) | |
| G7-5 | build.py strips frontmatter and does the renderer's substitutions; `forbidden` catches leftovers | env | user 2026-10-13 (env batch) | |
| G8-3 | converge strictness kept; bounded by the round cap (D-1); count `unrequested`-only rounds in smoke | env | user 2026-10-13 (env batch) | |
| G10-4 | instruction: opening the entry doc is the first action; the docs dir is at the filesystem root, outside the repository | env | user 2026-10-13 (env batch) | bug smoke finding (open in bug) |
| G10-5 | stage doc: tasks.md checkboxes are the record; TaskTracker is optional scratch | env | user 2026-10-13 (env batch) | |
| G1-2 | no ERROR exits in specify; the issue is a requirement the repository must meet | semantic | user 2026-10-13 (B-1) | as bug G1-2 |
| G4-1 | specify questions → take the most plausible reading, write it into the spec and its `## Assumptions`, proceed; Q&A / table blocks dropped; ≤3-marker rule kept | semantic | user 2026-10-13 (B-2) | as bug G4-3 |
| G4-2 | plan unknowns resolved from repository evidence; otherwise the most plausible reading, recorded in research.md (Decision / Rationale / Alternatives); no ERROR exit | semantic | user 2026-10-13 (B-3) | as bug G4-3; gate part = G7-6 |
| G4-5 | implement: a failed task stays unchecked, continue with tasks that do not depend on it, then converge | semantic | user 2026-10-13 (B-4) | same kind as bug G4-4 |
| G6-1 | research = the agent reading the repository and environment; no fetching or online lookup; issue links recorded `[UNVERIFIED — not fetched]` | semantic | user 2026-10-13 (B-5) | as bug G6-1 |
| G9-1 | no repository test-file tasks; verification scripts in `FEATURE_DIR/checks/`; implement validation runs existing repo tests for changed modules; "coverage meets requirements" dropped | semantic | user 2026-10-13 (B-6) | as bug G9-1 |

| G1-4 | **keep upstream verbatim** (product/business-framed spec, checklist and success-criteria rules unchanged); no reading rule | — (no edit) | user 2026-10-13 (C-1) | speckit_sdd is for **feature-development tasks only**; spec = WHAT/WHY, plan recovers API detail from the issue (still in the task message). Smoke must check: spec checklist passes, issue's API names reach plan.md. Fallback if not: add the "users are the code's callers" reading rule (semantic) |

| G7-6 | ship `tpl/constitution` verbatim at `<docs root>/memory/constitution.md` (the upstream post-init state); plan gets converge's own rule: an unfilled template has no principles (its comments are examples) → Constitution Check "skipped — template", no gate; converge's existing skip rule kept | semantic | user 2026-10-13 (C-4) | user chose the placeholder over a fixed constitution (closer to upstream) |

| G4-4 | implement's checklist scan kept read-only (do not modify checklist files); with unchecked items take upstream's "proceed" branch (`cmd/implement.md:84`); the ask/wait/halt text dropped | semantic | user 2026-10-13 (C-2) | |
| G4-6 | **delete** `tpl/tasks` `## Implementation Strategy` (`:213-243`), the "Implementation strategy section (MVP first, incremental delivery)" item (`cmd/tasks.md:93`) and the completion report's "Suggested MVP scope"; checkpoint lines → "validate at each checkpoint and continue"; implement completes every phase in one pass | semantic | user 2026-10-13 (C-3, as section deletion) | deletion instead of rewording |
| G9-2 | delete implement step 4 (Project Setup Verification / ignore files); add "the repository's ignore files are not part of the change; do not create or edit them" | semantic | user 2026-10-13 (C-5) | |
| G9-3 | phases kept, scoped: `cmd/tasks.md:84-88` Setup = only what this change needs in the existing repository (no init, dependency install, tool config), Foundational = prerequisites shared by this change's stories, Polish = cleanup this change needs (no repo-wide docs/refactor/performance/security); each omitted if empty. `cmd/implement.md:156,161` → "Setup phase tasks (repository already initialized, no dependency installation)", "Polish phase tasks, then run existing tests for changed modules". `tpl/plan:59-64` comment + "existing repository: list only the real files and directories this change modifies or adds". Sample tasks (`tpl/tasks:44` "DO NOT keep") unchanged | semantic | user 2026-10-13 (C-6) | |
| G7-7 | delete `tpl/tasks` `## Parallel Example` (`:199-212`) and "Parallel execution examples per story" (`cmd/tasks.md`); `[P]` markers kept | semantic | user 2026-10-13 (R-1) | found in stage 3; multi-agent/team content |
| G9-1 (scope) | B-6 also deletes implement's "Follow TDD approach" (`cmd/implement.md:152`) and "Tests before code" (`:158`) | semantic | user 2026-10-13 (R-3) | found in stage 3 |

Usage note (user 2026-10-13): speckit_sdd will be used on feature-development tasks only; smoke should use a
feature dataset, not SWE-Gym bug tasks.

| G8-1 | rounds: implement → converge; `converged` ends; `tasks_appended` in round 1 → round 2; **round 2 ends regardless** (cap 2). Each converge writes `convergence.md` / `convergence-2.md` in FEATURE_DIR (step-6 findings table + summary metrics + `- **Round**:` / `- **Outcome**: converged \| tasks_appended`); tasks.md append unchanged | loop | user 2026-10-13 (D-1) | cap 2 (bug: 3) because of 5 stages vs step budget 150; revisit after smoke |
| G8-2 | round 2 implement executes only unchecked tasks (normally the new Convergence phase); does not redo `[X]` tasks or setup | loop | user 2026-10-13 (D-2) | |
| G7-2 | **(b) ship the scripts**: upstream `scripts/bash/*.sh` the in-scope commands call, run by the agent as upstream does; root/feature-dir arrangement decided in stage 4 after a feasibility check; failure → back-edge (new gap) | env | user 2026-10-13 (D-3) | chosen for diversity: the only port whose agent runs workflow-provided tools; supersedes the (a) default recorded above |
| D-4 | docs `container_dir=/speckit-sdd`; artifacts under `/tmp/speckit-sdd/` (`output_dirs`), FEATURE_DIR `/tmp/speckit-sdd/specs/001-issue/` | env | user 2026-10-13 (D-4) | separate from speckit_bug |
| D-5 | no per-round implement report; unchecked tasks + convergence reports are the record | — | user 2026-10-13 (D-5) | |

All rows decided (2026-10-13).

| G7-8 | (c) `setup.sh` (`WorkflowSpec.setup_script`, run as root before the agent) writes `/usr/local/bin/jq` = `exec <real jq> -M "$@"`, ahead of `/usr/bin` on the task images' PATH; idempotent; no-op without jq. Scripts and stage docs unchanged | env | user 2026-10-14 | found in stage 4; verified in the MONAI image under `script -qec`: plain JSON, wrapper rerun-safe |

## G7-2 (b) feasibility — verified 2026-10-13

Arrangement: the spec-kit **project root is `/tmp/speckit-sdd/`** (outside the repo), shipped with
`WorkflowSpec.sandbox_files={"/tmp/speckit-sdd/.specify": <pkg>/sandbox/specify}` holding
`scripts/bash/*.sh` (upstream, +x), `templates/{spec,plan,tasks,checklist}-template.md` (converted by
build.py) and `memory/constitution.md` (upstream placeholder, G7-6). The docker backend's `upload_dir` is a
tar (`rllm/sandbox/backends/docker.py:256-266`), so the dot directory and modes survive (unlike `docs/`,
whose top-level dot entries are skipped, `workflow_harness.py:320`).

Probe in `xingyaoww/sweb.eval.x86_64.project-monai_s_monai-3384` (root, cwd `/testbed`, upstream scripts
unmodified): specify's own prose steps (mkdir `specs/001-issue`, copy spec template, write
`.specify/feature.json` = `{"feature_directory":"specs/001-issue"}`) → `setup-plan.sh --json` copied the plan
template and returned FEATURE_DIR `/tmp/speckit-sdd/specs/001-issue`, BRANCH `001-issue` (exit 0);
`check-prerequisites.sh --json --paths-only` → REPO_ROOT `/tmp/speckit-sdd` (root found by the script-location
fallback, `sh/common.sh:56-73`, since nothing above `/testbed` has `.specify`); `setup-tasks.sh --json` returned
the tasks template content; `check-prerequisites.sh --require-tasks` exited 1 with "Run /speckit.tasks first"
before tasks.md existed and 0 after. **No file written outside `/tmp/speckit-sdd/`; `/testbed` git status
clean.**

Consequences for stage 4:
- `{SCRIPT}` → absolute `/tmp/speckit-sdd/.specify/scripts/bash/<x>.sh --json …` (any cwd). FEATURE_DIR is the
  upstream default `<root>/specs/001-issue` — no env vars.
- `output_dirs=("/tmp/speckit-sdd/specs", "/tmp/speckit-sdd/.specify/feature.json")` so scripts/templates are
  not collected as outputs and feature.json is not a stray file.
- G7-3: script error hints name slash commands ("Run /speckit.tasks first"); handle in the stage docs ("a
  script error naming a missing file means carry out that stage first") rather than patching the scripts —
  keeps the scripts upstream byte-for-byte. (env, follows the decided G7-3 "wrap or patch")
- G5-3 paths become upstream's post-render ones: constitution `/tmp/speckit-sdd/.specify/memory/constitution.md`,
  templates `/tmp/speckit-sdd/.specify/templates/`.
- Not yet exercised: `resolve-template.sh` overrides/presets path (no overrides exist), non-root agent user. G9-4 decided by scope. G3-1 = new text; G8-4, G10-1..3 = operational (as bug).

## Revisions after smoke 1 (user, 2026-10-14) — implemented 2026-10-14

| Gap ID | Revised decision | Tag | Reason |
|---|---|---|---|
| G9-4 (rev) | plan Phase 1 files `data-model.md`, `contracts/`, `quickstart.md` are **always** created; when nothing applies the body is one line `N/A — <reason>` (replaces "write only when …") | semantic | a future verifier can check presence + (content or N/A reason) objectively; closer to upstream, which always writes them (contracts' own "skip if purely internal" becomes an N/A line) |
| G9-3 (rev) | Setup / Foundational / Polish phase headings are **always** kept in tasks.md; an empty phase holds one line `No tasks — <reason>` (replaces "omitted if empty"); the scope limits (no init / dependency / repo-wide docs·refactor) stay | semantic | same: objective structure check, upstream's phase structure kept |
| G9-1 (rev) | tests: existing repository tests are run (upstream's "validate tests pass", kept); repository test files are not written or edited (kept); upstream's TDD order ("write tests first, ensure they fail", "execute test tasks before implementation") → "before implementing, run the existing tests related to the change and record the baseline; run them again after"; **no `checks/` verification scripts** (the addition is removed); coverage requirement stays dropped | semantic | user: keep upstream's test actions, swap only what cannot hold (new-behaviour tests arrive with the verifier's test patch, so "ensure they fail" is not reproducible with existing tests) |
| G5-5 (rev) | location rule only: scratch files the agent chooses to create (repro scripts, notes) go under `FEATURE_DIR/checks/` (`/tmp/speckit-sdd/specs/001-issue/checks/`), never into `/testbed`; no instruction to write verification scripts | env | follows G9-1 (rev); stray repo files seen in both smokes |
| G4-6 (confirmed) | `## Implementation Strategy` stays deleted (MVP First / Incremental Delivery / Parallel Team): deployment is not part of these runs; execution order is still set by the kept `## Dependencies & Execution Order`, phase Checkpoints and implement's phase-by-phase rules | semantic | user 2026-10-14, after weighing (a) Incremental-only / (b) MVP→Incremental |

## Revision 2 (user, 2026-10-14) — supersedes G9-1 (rev) and G5-5 (rev)

| Gap ID | Revised decision | Tag | Reason |
|---|---|---|---|
| G9-1 (rev2) | **Tests are written, outside the repository.** The task message counts as the test request (its "tests are already taken care of" means the grader's tests, which the agent never sees). tasks: each user story's `### Tests for User Story N` holds test tasks whose files are verification scripts under `FEATURE_DIR/checks/` (never repository test files). implement keeps upstream TDD order: run those test tasks first and confirm they FAIL, then implement, then run them again and confirm they pass. Existing repository tests related to the change run before implementing (baseline) and after. Repository test files are not written or edited. Coverage requirement stays dropped | semantic | original SWE-Gym prompt asks for TEST CREATION (repro script, confirm failure) and VERIFICATION; upstream TDD is "write tests first, ensure they fail"; the fail-to-pass tests are hidden by design, so the agent's own scripts are the only check of new behaviour; outside the repo they cannot collide with the grader's test patch (`git apply` fails when a new file already exists) or pollute the patch |
| G5-5 (rev2) | `FEATURE_DIR/checks/` holds the verification scripts above and any scratch files; nothing of the workflow is written into `/testbed` | env | follows G9-1 (rev2) |
| G9-4 (rev2) | contracts/ N/A is recorded in plan.md's `### Documentation (this feature)` tree (upstream's own list of the feature's outputs): each contract file written is listed under `contracts/`, or the line reads `contracts/  # N/A — <reason>` and no file is created. data-model.md and quickstart.md keep the `N/A — <reason>` body | semantic | user 2026-10-14; avoids a placeholder file with an arbitrary name; a verifier reads the tree line and checks the listed files exist. Implemented 2026-10-14 |

## Revision 3 (user, 2026-10-14) — smoke 2 findings G9-5, G9-6, G9-7: put the rules where the agent looks — implemented 2026-10-14

| Gap ID | Decision | Tag | Notes |
|---|---|---|---|
| G9-5 (based on a measurement error; **reverted** by the user 2026-10-15) | the `No tasks — <reason>` note is attached to every phase line of the tasks doc's Phase Structure list (Setup, Foundational, Polish), and the template's Polish section says under its heading that the heading stays (with `No tasks — <reason>`) when the sample tasks are removed | semantic | smoke 2: Polish heading 0/7; the note sat only on the Setup line, and the Polish section held only sample tasks the template says to delete |
| G9-6 | the plan template's contracts tree line becomes a fill-in slot (`contracts/  # <contract files listed below, or N/A — <reason>>`); the plan doc says to replace that line in plan.md | semantic | smoke 2: 5/7 left the pre-filled comment line untouched |
| G9-7 | the TDD order is stated where each stage starts, not only in implement's rule list: implement's execution starts each user-story phase with its test tasks (write the `checks/` script, run it, see it fail) before any code edit for that story; core-workflow's stage table row for implement says the same; scratch/verification files outside `checks/` (e.g. `/tmp/*.py`) are named as a violation | semantic | smoke 2: scripts in `checks/` 2/10, `/tmp` 3/10, fail-first 0/10. Upstream TDD order unchanged (principle 2); only its placement |
