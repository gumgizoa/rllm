# Survey: GitHub Spec Kit — core Spec-Driven Development (SDD)

- Upstream: https://github.com/github/spec-kit @ `0443760542e7e5269724744a2ac55c4bd386d095` (2026-10-09,
  `specify-cli` 1.1.4.dev0 per `pyproject.toml:3`; bundled `speckit` workflow 1.0.1 per
  `workflows/speckit/workflow.yml:4`), license MIT, "Copyright GitHub, Inc." (`LICENSE:1-3`)
- Checkout: `/gpfs/home/daink/2026-2_DFM/spec-kit` (read-only)
- Scope: core SDD only. The `bug` extension (3 commands, 634 lines; already ported as `speckit_bug`) and
  the `assess` extension (5 commands, 486 lines) are separate processes and are out of scope here.
  `taskstoissues` is in scope but deprecated.

## Normal use

**Install / init.** `uv tool install specify-cli`, then `specify init <proj> --integration <key>`
(`README.md:45-46`, `docs/quickstart.md:57-59`). Init copies the bundled assets into the project, with no
network needed (`src/specify_cli/command_init.py:359-368`). A `--integration claude` init (rendered demo,
inspected) creates:
- `.claude/skills/speckit-<cmd>/SKILL.md`, one per command (13 incl. the bug extension in the demo)
- `.specify/templates/{spec,plan,tasks,checklist,constitution}-template.md`
- `.specify/scripts/bash/{common,check-prerequisites,setup-plan,setup-tasks,resolve-template,create-new-feature}.sh`
- `.specify/memory/constitution.md` = **verbatim copy of `constitution-template.md`** (placeholders only;
  `command_init.py:211-253`; demo file is byte-identical to `templates/constitution-template.md`)
- `.specify/workflows/speckit/workflow.yml`, `.specify/init-options.json` (`feature_numbering:
  "sequential"`), `.specify/integration.json`, `.specify/extensions.yml` (`hooks: {}` unless an
  extension registers some)

Git is **not** set up by default. Branching and commits come from the opt-in `git` extension
(`docs/reference/core.md:24-25`, `docs/guides/existing-projects.md:29-32`).

**Driving it.** A person types each skill in the agent chat, **one at a time, reviewing the result before
the next** (`README.md:61-64`, `docs/quickstart.md:18-20`). Nothing chains the commands automatically.
Frontmatter `handoffs:` (e.g. `templates/commands/specify.md:3-10`) are UI suggestion buttons, and skills
rendering drops them (inferred from the rendered `speckit-plan/SKILL.md` frontmatter). There is also a
CLI engine: `specify workflow run speckit -i spec="…"` (`docs/reference/workflows.md:21`). It runs
specify → [gate] → plan → [gate] → tasks → implement, without clarify, analyze or converge
(`workflows/speckit/workflow.yml:33-74`).

**Two official paths** (`docs/quickstart.md:29-50`):
- Shorter: constitution (once per project), then specify → plan → tasks → implement → converge.
- Full: constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge.
- "only `/speckit.specify` is strictly required before `/speckit.plan`. The clarify, checklist, and
  analyze commands are quality gates" (`docs/reference/agentic-sdd.md:5`, table rows 34-36 "optional
  quality gate").
- "Repeat **implement → converge** until convergence reports **Converged**" (`README.md:89`).

**Worked example** (`README.md:82-87`):
```
/speckit-constitution Create principles focused on code quality, testing, and maintainability.
/speckit-specify Build a photo organizer with albums grouped by date and a tile preview of each album.
/speckit-plan Use Vite with vanilla JavaScript. Keep images local and store metadata in SQLite.
/speckit-tasks
/speckit-implement
/speckit-converge
```
This writes `.specify/memory/constitution.md`, `.specify/feature.json` → `specs/001-photo-albums/`,
which then holds `spec.md`, `checklists/requirements.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/`, `quickstart.md` and `tasks.md`, plus the application code. Converge then either appends
`## Phase N: Convergence` tasks (run implement again) or prints "✅ Converged".

For brownfield repos (closest to SWE tasks), `docs/guides/existing-projects.md` says: `specify init --here
--force`, a constitution built only from rules already true for the repo ("Do not invent standards",
`:51-54`), then one bounded change. "The new `spec.md` defines the change you intend to make, not a
retroactive specification" (`:71-73`).

## Processes

| Process | Stages (in order) | Reads / writes | Who advances | Agent-facing text | Human checkpoints |
|---|---|---|---|---|---|
| **SDD, shorter path** | constitution (once) → specify → plan → tasks → implement ⇄ converge | `.specify/memory/constitution.md`; `specs/NNN-x/{spec.md, checklists/requirements.md, plan.md, research.md, data-model.md, contracts/, quickstart.md, tasks.md}`; app code; `.specify/feature.json` | person (or the `specify workflow` engine for specify→implement only) | 1,415 lines (5 commands + constitution), 927 without hook and frontmatter boilerplate; plus 546 template lines (spec, plan, tasks, constitution) | review after every command (`README.md:63`); specify ≤3 questions; implement checklist STOP; workflow gates `review-spec`, `review-plan` |
| **SDD, full path** | + clarify (after specify), checklist (after plan), analyze (after tasks) | adds spec.md `## Clarifications`, `checklists/<domain>.md`; analyze writes nothing | person | 2,340 lines (9 commands), 1,624 without boilerplate; plus 591 template lines | + clarify ≤5 sequential Q&A; checklist ≤5 questions; analyze ends with "Would you like me to suggest…" |
| taskstoissues (deprecated) | after tasks | reads tasks.md; creates GitHub issues via MCP | person | 114 (39 without boilerplate) | GitHub-remote check |
| bug extension (out of scope) | assess → [gate] → fix → test | `.specify/bugs/<slug>/` | person / `workflows/bugfix` | 634 | review-assessment gate |
| assess extension (out of scope) | intake → research → define → shape → decide → [gate] | — | person / `workflows/assess` | 486 | review-verdict gate |

### Per-command detail (SDD)

"Hooks" = the `## Pre-Execution Checks` and `## (Mandatory) Post-Execution Hooks/Checks` blocks. They
only act when `.specify/extensions.yml` registers hooks. "Body" = total minus frontmatter minus hooks.
Counts are from `wc -l` plus a section scan.

| Command | Status (docs) | Script it runs (`scripts:` frontmatter) | Writes | Total | Front | Hooks | Body |
|---|---|---|---|---|---|---|---|
| constitution | once per project (`agentic-sdd.md:40`) | `resolve-template.sh constitution-template --json` (`constitution.md:8`) | `.specify/memory/constitution.md` only (`:127`, `:146`); Sync Impact Report HTML comment at the top (`:112-119`) | 179 | 11 | 67 | 101 |
| specify | required | none; the agent does mkdir, template copy and feature.json in prose (`specify.md:80-106`) | `specs/<NNN>-<short>/spec.md` (`:97`), `.specify/feature.json` (`:99-105`), `checklists/requirements.md` (`:146`) | 345 | 11 | 69 | 265 |
| clarify | optional gate | `check-prerequisites.sh --json --paths-only` (`clarify.md:8`) | spec.md `## Clarifications / ### Session <date>` + section edits (`:182-208`); toggles marks in `checklists/requirements.md` (`:210-227`) | 291 | 11 | 69 | 211 |
| plan | required | `setup-plan.sh --json` (`plan.md:12`) | plan.md (template pre-copied by the script), research.md (Phase 0), data-model.md, contracts/, quickstart.md (Phase 1) (`:66-72`, `:114-159`) | 170 | 15 | 69 | 86 |
| checklist | optional gate | `check-prerequisites.sh --json --template checklist-template` (`checklist.md:4`), which errors without plan.md (`check-prerequisites.sh:145-149`) | `checklists/<domain>.md`, append-only, all items `[ ]` (`:139-148`, `:35`) | 379 | 7 | 67 | 305 |
| tasks | required | `setup-tasks.sh --json` (`tasks.md:13`) | `tasks.md` (`:82-93`); format `- [ ] T001 [P] [US1] desc path` (`:149-179`) | 220 | 16 | 69 | 135 |
| analyze | optional gate | `check-prerequisites.sh --json --require-spec --require-tasks --include-tasks` (`analyze.md:4`) | nothing ("STRICTLY READ-ONLY", `:58`); report printed in chat | 255 | 7 | 67 | 181 |
| implement | required | `check-prerequisites.sh --json --require-tasks --include-tasks` (`implement.md:4`) | app code; **creates or extends `.gitignore`/`.dockerignore`/`.eslintignore`/… in the repo** (`:99-141`); marks `[X]` in tasks.md (`:169`) | 222 | 7 | 69 | 146 |
| converge | required in README path; "Run it only after `/speckit.implement`" (`agentic-sdd.md:150`) | same as analyze (`converge.md:4`) | appends `## Phase N: Convergence` to tasks.md, or no write (`:73-83`, `:202-232`) | 279 | 7 | 78 | 194 |
| taskstoissues | deprecated (`taskstoissues.md:2`, `:10-16`) | `check-prerequisites.sh --json --require-tasks --include-tasks` | GitHub issues (MCP `issue_write`) | 114 | 8 | 67 | 39 |
| **Σ 10 commands** | | | | **2,454** | 100 | 691 | **1,663** |

### Agent text totals (commands + templates)

| Set | Raw lines | Without frontmatter and hooks |
|---|---|---|
| Everything (10 commands + 5 templates) | 2,454 + 591 = **3,045** | 1,663 + 591 = **2,254** |
| Full path (9 commands, no taskstoissues) + 5 templates | 2,340 + 591 = 2,931 | 1,624 + 591 = 2,215 |
| Shorter path incl. constitution + 4 templates (spec, plan, tasks, constitution) | 1,415 + 546 = 1,961 | 927 + 546 = 1,473 |
| **Minimal chain**: specify, plan, tasks, implement, converge + spec/plan/tasks templates | 1,236 + 496 = **1,732** | 826 + 496 = **1,322** |
| (reference) speckit_bug upstream | 634 | — |

The hook blocks are about 67-78 lines per command (691 in all, 28%). They are identical across commands
except for the hook key. In the minimal chain, the largest single parts are tasks-template (252 lines,
mostly sample tasks it says to delete: `tasks-template.md:29-46`), the specify validation and
clarification block (`specify.md:144-234`, ~90 lines) and implement's ignore-file catalogue
(`implement.md:99-141`, ~43 lines).

## Agent-facing sources

Pre-render sources (what a converter should read) are `templates/commands/*.md` and `templates/*.md`.
Rendered skills differ only mechanically (see the "Rendering" bullet in the Machinery section).

| File (upstream path) | Role | Generated? | Lines |
|---|---|---|---|
| `templates/commands/constitution.md` | constitution command | source (rendered to `.claude/skills/speckit-constitution/SKILL.md`, 182) | 179 |
| `templates/commands/specify.md` | specify | source (rendered 348) | 345 |
| `templates/commands/clarify.md` | clarify | source (294) | 291 |
| `templates/commands/plan.md` | plan | source (169) | 170 |
| `templates/commands/checklist.md` | checklist | source (386) | 379 |
| `templates/commands/tasks.md` | tasks | source (218) | 220 |
| `templates/commands/analyze.md` | analyze | source (262) | 255 |
| `templates/commands/implement.md` | implement | source (229) | 222 |
| `templates/commands/converge.md` | converge | source (285) | 279 |
| `templates/commands/taskstoissues.md` | deprecated GitHub issues | source (120) | 114 |
| `templates/spec-template.md` | spec.md skeleton: User Stories P1-P3 + Given/When/Then, Edge Cases, FR-###, Key Entities, SC-###, Assumptions | used as is (copied) | 131 |
| `templates/plan-template.md` | plan.md skeleton: Summary, Technical Context, Constitution Check (GATE), Project Structure, Complexity Tracking | used as is (`setup-plan.sh:46`) | 113 |
| `templates/tasks-template.md` | tasks.md skeleton: Setup / Foundational / US phases / Polish, deps, MVP strategy | used as is (passed as JSON `TASKS_TEMPLATE_CONTENT`) | 252 |
| `templates/checklist-template.md` | custom checklist skeleton | used as is | 45 |
| `templates/constitution-template.md` | constitution skeleton, `[ALL_CAPS]` placeholders | used as is; seeds `.specify/memory/constitution.md` | 50 |
| `workflows/speckit/workflow.yml` | engine definition (not read by the agent) | — | 74 |
| `.specify/memory/constitution.md` (in the spec-kit checkout) | spec-kit's **own** dogfooding constitution v1.0.0 for the specify-cli codebase (`:34`, `:42-194`), not shipped to users | — | 214 |
| `spec-driven.md`, `docs/concepts/sdd.md`, `docs/reference/agentic-sdd.md`, `docs/quickstart.md`, `docs/guides/existing-projects.md` | human docs, not read by the agent | — | 418 / 57 / 187 / 189 / 112 |
| Generator: `src/specify_cli/integrations/base.py:858-969` (`process_template`), `src/specify_cli/agents.py` (`rewrite_project_relative_paths`), `src/specify_cli/integrations/claude/__init__.py` (skill frontmatter) | rendering | — | — |

`spec-driven.md` describes an older design: "Nine Articles", "Phase -1" Simplicity / Anti-Abstraction
gates (`spec-driven.md:206-225`, `:278-378`) and branch auto-creation (`:126-129`). The current
plan-template has only `[Gates determined based on constitution file]` (`plan-template.md:43`), and
branching moved to the git extension **(inferred: the doc is stale)**.

## Machinery the text relies on

- **Rendering** (`integrations/base.py:864-874`, `:908-967`):
  - `{SCRIPT}` → `.specify/scripts/bash/<x>.sh …`
  - `scripts:` frontmatter stripped
  - `{ARGS}`/`$ARGUMENTS` → `$ARGUMENTS` (Claude)
  - `scripts/`, `memory/`, `templates/` → `.specify/…`, so `/memory/constitution.md` becomes
    `.specify/memory/constitution.md` (the demo `speckit-plan` diff confirms it)
  - `__SPECKIT_COMMAND_X__` → `/speckit-x`
  - skills mode adds one line per hook block: "replace dots with hyphens" (`integrations/base.py:41`)

- **Scripts** (all source `common.sh`; none runs git):
  - **Project root** `get_repo_root` (`common.sh:56-73`): `$SPECIFY_INIT_DIR` (must contain `.specify/`,
    `:38-52`), else walk up from cwd to the first dir containing `.specify/` (`:6-25`), else the script
    location `../../..`.
  - **Feature dir** `get_feature_paths` (`common.sh:163-238`): `$SPECIFY_FEATURE_DIRECTORY` (relative
    paths are joined to the root; persisted to `.specify/feature.json` unless `--no-persist` or
    `SPECIFY_FEATURE_NO_PERSIST`, `:192-200`), else `.specify/feature.json` `feature_directory`
    (`:201-211`), else ERROR "Feature directory not found" (`:212-215`). It emits `REPO_ROOT`,
    `CURRENT_BRANCH` (= `$SPECIFY_FEATURE` or the feature dir basename; never git, `:79-88`, `:221-224`),
    `FEATURE_DIR`, `FEATURE_SPEC`, `IMPL_PLAN`, `TASKS`, `RESEARCH`, `DATA_MODEL`, `QUICKSTART` and
    `CONTRACTS_DIR` (`:228-237`).
  - **Template resolution** (`common.sh:511-516`, `:620-…`): `.specify/templates/overrides/` → presets
    (by `.registry` priority, uses python3) → extensions → core `.specify/templates/`. Uses `jq` or
    `python3` when available, with grep/sed/awk fallbacks.
  - `setup-plan.sh`: `mkdir -p FEATURE_DIR`. It copies the resolved plan-template to plan.md only if
    plan.md is absent (`:36-65`) and prints JSON `FEATURE_SPEC, IMPL_PLAN, FEATURE_DIR, BRANCH`
    (`:68-79`). It does not check that spec.md exists.
  - `setup-tasks.sh`: requires plan.md and spec.md (`:31-41`). It lists the available docs (`:44-50`)
    and returns `TASKS_TEMPLATE` plus `TASKS_TEMPLATE_CONTENT`, failing hard if the template is missing
    (`:52-60`). It does not create tasks.md.
  - `check-prerequisites.sh`: `--paths-only` gives the paths and does no persist (`:102-136`). Otherwise
    it requires FEATURE_DIR and **plan.md always** (`:139-149`), plus spec.md and tasks.md when asked
    (`:152-163`). It prints `AVAILABLE_DOCS` (`:166-182`) and, with `--template`, `TEMPLATE_CONTENT`
    (`:184-190`).
  - `resolve-template.sh <name> --json`: prints `TEMPLATE_CONTENT` (`:37-57`).
  - `create-new-feature.sh` (504 lines): **no core command calls it**. specify does the same work in
    prose. It is a helper for direct use (`docs/reference/core.md` "Naming Features with the Helper
    Scripts"). It creates `specs/NNN-name/`, copies the spec template and persists feature.json
    (`:279-281`, `:441-466`).

- **Config the text reads:**
  - `.specify/init-options.json` (`feature_numbering`: sequential/timestamp, `specify.md:87-92`)
  - `.specify/feature.json`
  - `.specify/memory/constitution.md` (loaded by every command; see the Constitution section below)
  - `.specify/extensions.yml` (hooks)
  - `.specify/integration.json` (invoke separator for error hints, `common.sh:245-355`)

- **Hooks:** every command opens with `## Pre-Execution Checks` and closes with post hooks. The agent
  reads `.specify/extensions.yml` → `hooks.before_<cmd>` / `after_<cmd>`. A mandatory hook means emitting
  `EXECUTE_COMMAND:` and actually running it (e.g. `specify.md:21-54`, `:236-268`); an optional hook
  means printing a suggestion. With no file or no hooks the block is "skip silently" (`specify.md:54`).
  The default init has `hooks: {}`, so these blocks are 691 no-op lines. The git extension registers
  `before_specify: speckit.git.feature` as mandatory and `speckit.git.commit` before and after every
  command as optional (`extensions/git/extension.yml:42-126`).

- **Network:**
  - taskstoissues: GitHub MCP `list_issues`/`issue_write` (`taskstoissues.md:3`, `:75-79`)
  - plan Phase 0 "Generate and dispatch research agents… Find best practices for {tech}"
    (`plan.md:121-128`), which implies sub-agents or web lookup **(inferred)**
  - no URL-trust policy (unlike the bug extension)

- **Git:**
  - none in the core scripts
  - implement runs `git rev-parse --git-dir` to decide whether to create or verify `.gitignore`
    (`implement.md:103-107`)
  - taskstoissues runs `git config --get remote.origin.url` (`taskstoissues.md:66-73`)
  - tasks-template Notes say "Commit after each task or logical group" (`tasks-template.md:250`)
  - converge: "no git, no branch comparison, no history" (`converge.md:68-69`)
  - branches only via the git extension hook (`specify.md:74-78`, `:278`)

- **Interactive points** (every stop/ask/gate):
  1. constitution: ask when unclear whether the input is constitution content (`constitution.md:33-34`);
     ratification date "ask or mark TODO" (`:99`); "propose reasoning" if the version bump is ambiguous
     (`:104`); stop if template resolution fails (`:86-87`); final summary with suggested commit message
     (`:129-133`).
  2. specify:
     - ERROR "No feature description provided" (`specify.md:119`); ERROR "Cannot determine user
       scenarios" (`:131`)
     - ≤3 `[NEEDS CLARIFICATION]`; when they remain, present Q1–Q3 option tables and **"Wait for user to
       respond"** (`:199-232`)
     - validation loop with at most 3 iterations, then "warn user" (`:196-197`)
     - Completion Report to the user (`:270-276`)
  3. clarify:
     - abort if the script JSON fails (`clarify.md:68`); if the spec is missing, tell the user to run
       specify (`:232`)
     - **one question at a time, up to 5, wait for each answer**, honor "done/stop" (`:140-180`, `:233-235`)
     - warn if the user skips clarify before plan (`:60`)
  4. plan: "ERROR on gate failures or unresolved clarifications" (`plan.md:164`, `:69`); Constitution
     Check is a GATE before Phase 0 and again after Phase 1 (`plan-template.md:41`).
  5. checklist: up to 3 (+2) clarifying questions (`checklist.md:90-120`). It is the **only** command
     with "Defaults when interaction impossible" (Standard depth, Reviewer audience, top-2 focus,
     `:115-118`). Items must stay `[ ]`, "checkbox state belongs to the reviewer" (`:148`, `:35`).
  6. tasks: no question; Completion Report (`tasks.md:129-137`).
  7. analyze: abort if artifacts are missing (`analyze.md:72`); ends by asking "Would you like me to
     suggest concrete remediation edits…?" (`:200-202`).
  8. implement:
     - **checklist gate**: any unchecked item in `checklists/*.md` means "**STOP** and ask … (yes/no)"
       (`implement.md:79-84`)
     - "Halt execution if any non-parallel task fails" (`:165`)
     - "Report progress after each completed task" (`:164`)
     - if tasks are missing, suggest running tasks (`:177`)
  9. converge: STOP if spec, plan or tasks is missing (`converge.md:100-102`); reports findings before
     writing (`:184-200`); the Next Actions handoff goes to the user (`:234-240`).
  10. taskstoissues: proceed only if the remote is a GitHub URL (`taskstoissues.md:72-73`, `:80-81`).
  11. Engine gates: `review-spec` and `review-plan`, approve/reject, reject = abort
      (`workflows/speckit/workflow.yml:44-49`, `:56-61`).
  12. All commands end in a "Completion Report" / "Report … to the user" plus a `## Done When` checklist
      (e.g. `specify.md:341-345`, `implement.md:213-222`).

### Constitution: role and placeholder behavior

- **Role:** non-negotiable project principles that later phases are checked against. It is created once
  per project (`agentic-sdd.md:40`). analyze treats a conflict as automatically CRITICAL
  (`analyze.md:60`, `:249`); converge treats a MUST violation as the top-severity remediation task
  (`converge.md:85-88`, `:176-177`, `:223-224`); plan fills "Constitution Check" and errors on
  unjustified violations, which are tracked in plan-template "Complexity Tracking" (`plan.md:68-69`,
  `plan-template.md:106-113`).
- **Placeholder:** after `specify init` the file *exists* but holds only `[PRINCIPLE_1_NAME]`-style
  tokens (`constitution-template.md:1-50`).
  - specify, clarify, tasks and implement load it "IF EXISTS" (`specify.md:115`, `clarify.md:71`,
    `tasks.md:68`, `implement.md:96`), so they read a placeholder file.
  - plan reads it unconditionally (`plan.md:64`).
  - Only converge says what to do with a placeholder: "If the constitution is an unfilled template, skip
    constitution checks gracefully" (`converge.md:87-88`; also `:129`, `:198` "skipped — template").
  - analyze, plan and the plan-template have no placeholder rule, so the model decides how gates behave
    against a placeholder **(inferred)**.
  - The brownfield guide says not to invent standards (`existing-projects.md:51-54`).

### implement ⇄ converge loop

- implement runs every task phase by phase, respects `[P]` and dependencies, runs TDD order if tests
  exist, marks `[X]`, then validates the result against spec, plan and tests (`implement.md:143-175`).
  It has no "skip already-`[X]` tasks" rule; re-running it after converge relies on the model picking
  the unchecked Convergence tasks **(inferred)**.
- converge treats `spec.md`, `plan.md` and `tasks.md` as the "sole source of intent" (`converge.md:59-66`).
  "Completion claims are not evidence": it checks behavior for every task, including `[X]` ones
  (`:147-151`). Each gap is classified missing / partial / contradicts / unrequested (`:156-163`) with
  severity CRITICAL…LOW (`:174-182`). Its scope is bounded to the files named in plan and tasks plus a
  keyword search (`:140-143`). Converge never edits spec, plan, code or old tasks (`:73-80`). It does
  not explicitly run tests **(inferred: the text says "inspect the current code")**.
- **Outcome `tasks_appended`**: a new `## Phase N: Convergence` with IDs `T{M+1:03d}…` and the form
  `- [ ] T042 <desc> per <source-ref> (<gap-type>)`, constitution tasks first; old phases are never
  touched (`:204-226`). Handoff: "recommend running implement" (`:236-238`).
- **Outcome `converged`**: tasks.md is left byte-for-byte unchanged and it prints "✅ Converged — the
  implementation satisfies the spec, plan, and tasks." (`:82-83`, `:228-232`). Handoff: review or PR
  (`:239-240`).
- **End condition:** the loop ends when the person sees `converged` ("Repeat … until it reports
  converged", `agentic-sdd.md:159`; `README.md:89`). **There is no iteration cap** anywhere in the
  upstream text, and the engine workflow does not include converge (`workflow.yml:33-74`).
  `unrequested` findings always produce a task ("review/justify or remove", `converge.md:161-163`), so a
  legitimate extra could keep the loop open **(inferred)**.

## Fit for SWE tasks

rllm setting: one user message with the issue in `<issue_description>`, repo at `/testbed`, unattended
until `finish`, a text-only reply ends the session, hidden tests grade `/testbed`, docs at an absolute
path outside the repo.

| Process | Fit | Main mismatch |
|---|---|---|
| SDD minimal chain (specify→plan→tasks→implement⇄converge) | **medium** | Built for greenfield product features: tech-agnostic user stories and success criteria "for business stakeholders" (`specify.md:282-285`, `:318-339`), plan artifacts (data-model, contracts, quickstart) mostly irrelevant to an issue fix. Every command ends by reporting to the user (text-only turn ends the run). Artifacts go to `specs/` and `.specify/` **inside the repo** (they pollute /testbed). implement edits repo ignore files (`implement.md:99-141`). Tests are optional "only if explicitly requested" (`tasks.md:147`) while grading is by hidden tests. The converge loop has no cap. |
| SDD full path (+clarify, checklist, analyze) | **low** | clarify is a sequential human Q&A loop by design. Checklist items are reviewer-owned, never checked by the agent, and feed implement's STOP gate (`implement.md:79-84`). analyze is read-only chat output ending in a question. These add about 700 body lines of "requirements quality" work with no effect on /testbed. |
| constitution | **none / substitute** | Per-project governance written once by a person from agreed rules. In SWE runs there is none: the init placeholder is the realistic state, and only converge handles it. |
| taskstoissues | none | Deprecated; needs network and GitHub MCP. |
| (bug, assess) | — | Out of scope (bug already ported; assess ends in a go/no-go verdict, not a patch). |

Decisions from `speckit_bug/porting/03-decisions.md` that likely carry over (to be confirmed in stage 2):
- G1-1: input = `<issue_description>`, replacing `## User Input`/`$ARGUMENTS`.
- G2-1/G2-2: "do not report; read the next stage document", and `__SPECKIT_COMMAND_*__` → stage doc
  paths.
- G3-1: a hand-written entry doc that chains the stages.
- G4-1: fixed slug and feature dir (no NNN numbering or feature.json).
- G4-3: `[NEEDS CLARIFICATION]` → most plausible reading recorded as an assumption. This covers specify
  Q1–Q3, clarify, and plan's "ERROR on unresolved clarifications".
- G4-6: no engine gates.
- G5-1: artifacts under `/tmp/speckit/...` and docs at `/speckit`, not `specs/`.
- G6-1: no fetching, which affects plan's "research agents".
- G7-1: drop the hook blocks (691 lines).
- G8-1: bounded rounds, the natural analog for implement⇄converge (bug used 3).
- G9-2: guardrail wording for out-of-repo artifacts.
- G10-x: SDK prompt handling.

SDD-specific items with no bug-port precedent:
- constitution (placeholder, drop, or generate)
- implement's ignore-file setup
- the checklist gate
- the tests-optional rule
- the product-centric spec template
- `check-prerequisites.sh` requiring plan.md, which blocks checklist before plan
- whether to keep scripts at all, or have docs state paths directly, as specify already does in prose

## Recommendation

Port the **shorter path** first, as the minimal chain specify → plan → tasks → implement ⇄ converge, under
workflow name **`speckit_sdd`**:
- It is the documented default for smaller features (`docs/quickstart.md:32-38`) and what `README.md:76-89`
  shows.
- Its body is about 1,322 lines with templates (826 command lines), about twice the bug port.
- converge gives a built-in self-check loop that maps onto bounded rounds.

Treat constitution as absent or placeholder, which upstream already handles in converge. Leave clarify,
checklist and analyze out of the first port; they are optional upstream and inherently interactive or
review-only.

Open questions for the user:
1. Minimal chain only, or also self-run clarify/analyze?
2. Constitution: none, the placeholder, or a fixed generic one?
3. Cap for implement⇄converge rounds (bug used 3)?
4. Keep plan Phase 1 artifacts (data-model, contracts, quickstart) or only plan.md and research.md?
5. Keep "tests OPTIONAL unless requested" verbatim, or align with speckit_bug's G9-1 (checks outside the
   repo, run existing repo tests)?

## Scope decided (user, 2026-10-13)

1. **Minimal chain**: specify → plan → tasks → implement ⇄ converge. clarify, checklist, analyze,
   taskstoissues and constitution-as-a-command are out of scope.
2. **plan Phase 1 kept, conditional**: write data-model.md / contracts/ / quickstart.md only when the change
   introduces new entities or external interfaces; otherwise record N/A in plan.md. Reason: feature-
   development tasks will be added later, and tasks/implement already treat these files as optional /
   IF EXISTS (`templates/commands/tasks.md:67`, `templates/commands/implement.md:93-97`).
Questions 2, 3, 5 above (constitution, round cap, tests rule) are left for stage 3.
