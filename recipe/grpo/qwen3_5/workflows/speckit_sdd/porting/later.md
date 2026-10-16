# Later: speckit_sdd

Ideas the user agreed to keep for later. Not decisions: nothing here is implemented. Each entry is added
only after the user said yes to recording it.

## Rules the documents do not hold → compliance scorer (2026-10-14)

- **What**: treat as training signal (compliance scorer) the rules the agent follows only partly after three
  rounds of document changes: the contracts
  line of plan.md's Documentation tree filled (contract files listed, or `N/A — <reason>`), the `checks/`
  verification scripts run and seen failing before the code and passing after, staying in the workflow
  after the specify stage, and the converge report's format (`convergence.md` for round 1, the
  `- **Outcome**:` line).
- **Why**: smokes 2–3 moved each rule to where the agent looks, and compliance rose only partly — fail-first
  1/10, contracts line 4/5 with placeholder text left in some;
  documents alone do not make the behaviour reliable.
- **Open points when picked up**: what each rule is judged from (collected artifacts under
  `/tmp/speckit-sdd/specs/001-issue/` vs. the order of tool calls in the episode); how the signals combine
  with the verifier reward (`add` rather than `mul`, see the workflow guide's warning); whether a rollout
  that skipped the workflow entirely gets a separate signal.
- **Origin**: `02-gaps.md` G2-5, G8-5, G9-6, G9-7; `06-smoke.md` smokes 2–3.

## No path back to spec/plan: the chain certifies its own first reading (2026-10-16)

- **What**: give the chain the correction loop that upstream's human reviewer provided. Candidates, to be
  compared as ablations on the hard tasks rather than adopted together:
  1. converge judges against the issue text and a rerun of the issue's own example, not against
     `spec.md`/`plan.md`/`tasks.md` as the "sole source of intent";
  2. a mismatch found by `checks/` or converge may amend `spec.md`/`plan.md` (today both are
     "Changed later: no" and converge MUST NOT touch them);
  3. `checks/` must reproduce the issue's example verbatim, not only cases derived from the spec;
  4. specify → implement directly (no plan/tasks), to measure what the early written commitment costs.
- **Why**: SWE-bench Verified 499 (Qwen3.5-9B, think on, 150 turns, 262k, T=1.0, commit `7c88c420`):
  resolve 49.1% vs 60.1% without a workflow (84 tasks solved only without it, 29 only with it). The loss
  sits on long tasks: of the tasks the no-workflow run solved in ≥80 steps, 53% are lost (rerun control
  23%); under 40 steps, 6% (control 7%). Of the 84, 56 fail FAIL_TO_PASS on replay (10 break PASS_TO_PASS
  only, 17 leave no patch). A per-case judgement of the 56 (+29 solved controls) against gold patch and
  hidden tests:
  - spec misses or misstates a condition the tests need: 26/56 (controls 3/29);
  - plan picks the wrong approach or file: 31/56 (2/29), and implement carries the wrong plan out
    as written in 24 of those 31;
  - `checks/` do not exercise the required behaviour: 45/56 (9/29), since they are derived from the spec;
  - converge says `converged` while the hidden tests fail: 30/56; over all 499 runs converge appended
    tasks 5 times (305 `converged`), median 6 steps;
  - 25/56 end before converge (finish after implement, "already implemented", malformed tool call).
  The no-workflow agent revises after running code ~3.6 times on these tasks, the chain ~1.9: its
  verification points all compare the code with the agent's own artifacts, so an early misreading is
  locked in. Part design (faithful execution of converge/implement still fails), part execution
  (incomplete specs, wrong plans, stopping early); the design removes the loop that hides the latter.
- **Open points when picked up**: which of 1–4 recovers the most on the ≥80-step tasks (81 tasks); whether
  1 keeps the chain recognisably Spec Kit's converge; the 25 early stops need their own fix (stage
  compliance, see the entry above). The judgement knew the outcome, so its counts lean towards finding faults.
- **Origin**: `rllm-home/eval_results/swebv499_speckitsdd_262k-150_think_t1/` (episodes with patch and
  `/tmp/speckit-sdd/specs` collected); its `analysis_20261016/` holds the scripts, the 67 replay reports
  (`replay/`) and the 86 verdicts with their instructions (`judge_out/`, `judge/`).
