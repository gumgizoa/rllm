# Later: agentos_v2

Ideas the user agreed to keep for later. Not decisions: nothing here is implemented. Each entry is added
only after the user said yes to recording it.

## Filled tech-stack standard variant (2026-10-16)

- **What**: a variant that ships `standards/global/tech-stack.md` again, filled with the repository's stack
  (language, test framework, packaging, …), and restores its line in the four commands' standards lists
  (`{{standards/*}}` / `{{standards/global/*}}`, `R:shape:394`, `R:write:132`, `R:tasks:252`, `R:impl:85`).
- **Why**: upstream's commands all ask the agent to stay aligned with the person's default stack written
  in this file; the base port ships no file (G7-6) because upstream installs it as an unfilled template
  and nobody fills it here.
- **Open points when picked up**: who fills it (the pipeline offline per task instance vs the agent at
  the start); its content must not hint at the fix (leak); upstream's role is the person's *default*
  stack, while the project's own stack is `product/tech-stack.md` written by plan-product PHASE 4
  (`create-product-tech-stack.md:1,11-16`) — decide which of the two the variant models.
- **Origin**: `03-decisions.md` G7-6 (file deleted in the base port).

## plan-product variant for feature tasks (2026-10-16)

- **What**: a feature-task variant that runs plan-product before shape-spec: the agent writes
  `product/{mission,roadmap,tech-stack}.md` from the repository and the issue, with the issue's feature as a
  roadmap item, so upstream's "pick the next roadmap feature" (shape-spec) and "tick the finished feature"
  (verification Step 2) run as written.
- **Why**: the base port leaves plan-product out (Answered question 2) and reads product context from the
  repository (G1-3); the roadmap step only records `⚠️ No Updates Needed` (G7-8).
- **Open points when picked up**: plan-product asks for at least 3 key features (`gather-product-info.md:14`),
  so invented items mix in; about 240 more lines and four more PHASEs; not for bugfix tasks.
- **Origin**: `03-decisions.md` Answered question 2, G7-8.

## Real-development conventions variant (2026-10-16)

- **What**: a variant that ships the two global standards with the lines the base port deleted:
  `conventions.md` lines 4 (README upkeep), 5 (commits / branches / PRs), 7 (dependencies up-to-date),
  8 (code review), 9 (testing requirements before merging), 10 (feature flags), 11 (changelog), and
  `coding-style.md` lines 8 (remove dead code), 9 (backward compatibility only when required), 10 (DRY).
- **Why**: these are real development practice (e.g. pandas expects a whatsnew entry with a change); the base
  port deleted them as team process or work outside the issue (G9-2, G9-3, P4). A variant shows how much
  following them changes the patch and the reward.
- **Open points when picked up**: the task text asks for minimal changes to non-test files
  (`prepare_swegym.py:179`) and grading is hidden tests only, so README / changelog edits earn nothing and
  enlarge the patch; "dependencies up-to-date" can trigger installs or upgrades over the network (no network
  rule in the entry document, G6-1); "no backward compatibility" can break existing behavior the hidden tests
  check; branches / PRs / review have no counterpart after the session — decide whether those lines come back
  at all or only the code-level ones.
- **Origin**: `03-decisions.md` G9-2, G9-3.

## Fix round after verification (2026-10-16)

- **What**: when the verification test run shows failures the agent's own change caused, go back to
  implement-tasks PHASE 2 once to fix them, re-run, then write the report (a `loop`-tagged addition).
- **Why**: upstream verification only reports failures ("DO NOT attempt to fix any failing tests",
  `run-all-tests.md:5`), so a regression the agent introduced is graded as is (G8-3 kept verbatim).
- **Open points when picked up**: how the agent tells its own regressions from failures that were there
  before (needs a before-change test run, which upstream does not have); at most one round; earlier loops
  rarely fired — speckit_bug fix↔test 7/499, openspec_ff verify→apply 0/60 (dropped) — so measure firing rate
  first; upstream's intent is likely to keep pre-existing failures out of scope.
- **Origin**: `03-decisions.md` G8-3 (option b, not chosen).

## Dataset-neutral wording of the task conditions (2026-11-13)

- **What**: rewrite every sentence that assumes one dataset's task conditions so it holds for any SWE task
  source (SWE-Gym, SWE-bench Verified, SWE-Factory, SWE-rebench, feature-development tasks). The user's
  decision: all of them are to be generalized; this is separate from any effect on resolve rate.
- **Where** (rows of `rllm/tasks/2026-11-13-agentos-v2-resolve-review/review/`, column 비고):
  - the `<issue_description>` tag of the SWE-Gym task message: `core-workflow.md:36-38`, `shape-spec.md:15,25,61`
  - "the issue" as the form of the input: system prompt line 62, `core-workflow.md:16,51,70`,
    `shape-spec.md:152,223`
  - "The issue is your only input from outside": `core-workflow.md:39`
  - the repository at `/testbed`: `instruction.md:4-6`, system prompt line 68, `core-workflow.md:9-10,81,87`
  - Python packaging files as the example: `shape-spec.md:108`
  - the test rule that assumes hidden-test grading: `core-workflow.md:84-86`, `create-tasks.md:215`,
    `implement-tasks.md:39`
- **Why**: the port was written against the SWE-Gym message (`scripts/prepare_swegym.py`
  `INSTRUCTION_TEMPLATE_AIDLC`: tagged issue plus four condition lines). The SWE-bench Verified evaluation
  message is the bare issue text with no tag and none of those lines (checked in one episode each of
  `swebv499_agentosv2_262k-150_think_t1` and `wf_floor_tcx/…_swebv_agentos-v2_x1`), so the documents already
  point at a tag the evaluation does not have. speckit_bug, speckit_sdd and openspec_ff refer to the same tag
  (4 / 3 / 4 lines); aidlc_v4 and aidlc_v5 do not.
- **Open points when picked up**: one neutral wording for all datasets ("the task description in the task
  message") versus one paragraph of task conditions swapped per dataset (needs a slot in `workflows/spec.py`,
  which today only swaps the system prompt per harness); what feature-development tasks give as input; whether
  the test rule belongs to the workflow or to the dataset's conditions; the same change in the other three ports.
- **Origin**: review of 2026-11-13 (task `2026-11-13-agentos-v2-resolve-review`, LOG 16:05 and 16:40).
