## Outline

1. Run `/tmp/speckit-sdd/.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` (from any working directory: it finds the project root `/tmp/speckit-sdd` from its own location) and parse FEATURE_DIR and AVAILABLE_DOCS list. If the script exits non-zero because a file or the feature directory is not found (its hint names a `/speckit.<stage>` command), that stage has not run yet: carry it out first from its stage document (listed in `/speckit-sdd/core-workflow.md`), then run the script again. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **Check checklists status** (if FEATURE_DIR/checklists/ exists):
   - Treat checklist markers as a read-only check: scan checkbox state and proceed; do NOT modify checklist files or markers
   - `checklists/requirements.md` is the built-in spec-quality checklist maintained by the specify stage
   - Scan all checklist files in the checklists/ directory
   - For each checklist, count:
     - Total items: All lines matching `- [ ]` or `- [X]` or `- [x]`
     - Checked items: Lines matching `- [X]` or `- [x]`
     - Unchecked items: Lines matching `- [ ]`
   - Create a status table:

     ```text
     | Checklist | Total | Checked | Unchecked | Status |
     |-----------|-------|---------|-----------|--------|
     | ux.md     | 12    | 12      | 0         | ✓ PASS |
     | test.md   | 8     | 5       | 3         | ✗ FAIL |
     | security.md | 6   | 6       | 0         | ✓ PASS |
     ```

   - Calculate overall status:
     - **PASS**: All checklists have 0 unchecked items
     - **FAIL**: One or more checklists have unchecked items

   - **If any checklist has unchecked items**:
     - The unchecked items stay recorded in the checklist itself; nobody is asked
     - Proceed to step 3

   - **If all checklists are checked**:
     - Automatically proceed to step 3

3. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read /tmp/speckit-sdd/.specify/memory/constitution.md for governance constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

4. **Ignore files**: the repository's ignore files (`.gitignore`, `.dockerignore` and the like) are not part of the change; do not create or edit them.

5. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Execution flow**: Order and dependency requirements

6. Execute implementation following the task plan:
   - **Round 2**: when the converge stage has appended a `## Phase N: Convergence` and sent you back here, execute only the unchecked tasks (normally that newest phase); do not redo `[X]` tasks or the setup tasks
   - **Each user story starts with its test tasks**: before any code edit for a story, write that story's verification scripts in `FEATURE_DIR/checks/`, run them and see them fail; only then implement the story, and run them again to see them pass
   - **Phase-by-phase execution**: Complete each phase before moving to the next
   - **Respect dependencies**: Run sequential tasks in order, parallel tasks [P] can run together
   - **Follow TDD approach**: Execute test tasks before their corresponding implementation tasks. The test tasks are the verification scripts in `FEATURE_DIR/checks/`: write and run them and confirm they fail, implement, then run them again and confirm they pass
   - **File-based coordination**: Tasks affecting the same files must run sequentially
   - **Validation checkpoints**: Verify each phase completion before proceeding, then continue: every phase of tasks.md is completed in this one pass

7. Implementation execution rules:
   - **Setup first**: Setup phase tasks (repository already initialized, no dependency installation)
   - **Tests before code**: If you need to write tests for contracts, entities, and integration scenarios, write them as verification scripts in `FEATURE_DIR/checks/`; the repository's test files are not written or edited. Before implementing, also run the existing repository tests related to the change and record the baseline; run them again after
   - **Core development**: Implement models, services, CLI commands, endpoints
   - **Integration work**: Database connections, middleware, logging, external services
   - **Polish and validation**: Polish phase tasks, then run existing tests for changed modules

8. Progress tracking and error handling:
   - Record progress only by marking each completed task [X] in tasks.md (see below); do not report progress in messages
   - If a non-parallel task fails, leave it unchecked and continue with the tasks that do not depend on it
   - For parallel tasks [P], continue with successful tasks, leave failed ones unchecked
   - Provide clear error messages with context for debugging
   - If implementation cannot proceed, go on to the converge stage: it re-checks every task whatever its checkbox and appends the remaining work
   - **IMPORTANT** For completed tasks, make sure to mark the task off as [X] in the tasks file.
   - The checkboxes in tasks.md are the record of progress. A task-tracking tool, if you use one, is scratch only and never replaces marking tasks.md

9. Completion validation:
   - Verify all required tasks are completed
   - Check that implemented features match the original specification
   - Validate that tests pass: the verification scripts in `FEATURE_DIR/checks/` and the existing repository tests related to the change
   - Confirm the implementation follows the technical plan

Note: This stage assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, carry out the tasks stage (`/speckit-sdd/stages/03-tasks.md`) first to regenerate the task list.

## Next Stage

Nothing is reported at the end of this stage: no one reads a completion message, and a reply without a tool call ends the session. This stage leaves no report of its own: the `[X]` marks in tasks.md and the converge stage's round report are the record. Once every task you can complete is marked, open `/speckit-sdd/stages/05-converge.md` and start this round's converge stage.

## Done When

- [ ] All tasks in tasks.md completed and marked `[X]`
- [ ] Implementation validated against specification, plan, and tests (the `FEATURE_DIR/checks/` scripts and the existing repository tests related to the change)
- [ ] The converge stage (`/speckit-sdd/stages/05-converge.md`) opened next, with no report in between
