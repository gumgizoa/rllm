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
