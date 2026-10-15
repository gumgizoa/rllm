## Outline

1. **Setup**: Run `/tmp/speckit-sdd/.specify/scripts/bash/setup-plan.sh --json` (from any working directory: it finds the project root `/tmp/speckit-sdd` from its own location) and parse JSON for FEATURE_SPEC, IMPL_PLAN, FEATURE_DIR, BRANCH. If the script exits non-zero because a file or the feature directory is not found (its hint names a `/speckit.<stage>` command), that stage has not run yet: carry it out first from its stage document (listed in `/speckit-sdd/core-workflow.md`), then run the script again. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **Load context**: Read FEATURE_SPEC and `/tmp/speckit-sdd/.specify/memory/constitution.md`. Load IMPL_PLAN template (already copied).

3. **Execute plan workflow**: Follow the structure in IMPL_PLAN template to:
   - Fill Technical Context from the repository - its build files, CI configuration and installed environment; nobody names a tech stack (mark unknowns as "NEEDS CLARIFICATION")
   - Fill Constitution Check section from constitution. If the constitution is an unfilled template (`[ALL_CAPS]` placeholders with `<!-- Example: ... -->` comments), it has no principles - its comments are examples, not rules: write "skipped — template" in Constitution Check and evaluate no gate
   - Otherwise evaluate gates (ERROR if violations unjustified)
   - Phase 0: Generate research.md (resolve all NEEDS CLARIFICATION)
   - Phase 1: Generate data-model.md, contracts/, quickstart.md - always all three; data-model.md or quickstart.md with nothing to hold for this change has the one-line body `N/A — <reason>`; contracts/ with no contract is recorded in plan.md's Documentation tree as `contracts/  # N/A — <reason>`
   - Re-evaluate Constitution Check post-design

## Next Stage

Nothing is reported at the end of this stage: no one reads a completion message, and a reply without a tool call ends the session. Once plan.md, research.md and the Phase 1 files (data-model.md, contracts/, quickstart.md) are written, open `/speckit-sdd/stages/03-tasks.md` and start the tasks stage.

## Phases

### Phase 0: Outline & Research

1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Research from the repository**: no sub-agents run here and nothing is looked up online. Resolve each unknown and each research task yourself by reading the repository and the installed environment (source, build and CI files, the installed versions of its dependencies). Do not fetch links from the issue; a link you rely on is recorded as `[UNVERIFIED — not fetched]`.

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

   An unknown the evidence does not settle is decided by the most plausible reading and recorded in the same format; nobody is asked.

**Output**: research.md with all NEEDS CLARIFICATION resolved

### Phase 1: Design & Contracts

**Prerequisites:** `research.md` complete

**Always written**: data-model.md and quickstart.md are created every time; when nothing in one of them applies to this change, its whole body is one line `N/A — <reason>`. Contracts are recorded in plan.md's Documentation tree: the copied template has a `contracts/` line marked `<REPLACE in plan.md: …>`; replace it in plan.md with one line per contract file you write, or, when there is none, with `contracts/  # N/A — <reason>` and create no file.

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Define interface contracts** (if project has external interfaces) → `FEATURE_DIR/contracts/`:
   - Identify what interfaces the project exposes to users or other systems
   - Document the contract format appropriate for the project type
   - Examples: public APIs for libraries, command schemas for CLI tools, endpoints for web services, grammars for parsers, UI contracts for applications
   - If project is purely internal (build scripts, one-off tools, etc.), write no contract file and record `contracts/  # N/A — <reason>` in plan.md's Documentation tree

3. **Create quickstart validation guide** → `quickstart.md`:
   - Document runnable validation scenarios that prove the feature works end-to-end
   - Include prerequisites, setup commands, test/run commands, and expected outcomes
   - Use links or references to contracts and data model details instead of duplicating them
   - Do not include full implementation code, model/service/controller bodies, migrations, or complete test suites
   - Keep this artifact as a validation/run guide; implementation details belong in `tasks.md` and the implementation phase

**Output**: data-model.md, FEATURE_DIR/contracts/*, quickstart.md

## Key rules

- Use absolute paths for filesystem operations; use project-relative paths for references in documentation
- Unresolved clarifications are not an error: Phase 0 resolves each from repository evidence or by the most plausible reading recorded in research.md
- Gate failures: as in step 3 (an unfilled constitution template has no gates)

## Done When

- [ ] Plan workflow executed and design artifacts generated
- [ ] The tasks stage (`/speckit-sdd/stages/03-tasks.md`) opened next, with no report in between
