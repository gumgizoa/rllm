# Later: speckit_bug

Ideas the user agreed to keep for later. Not decisions: nothing here is implemented. Each entry is added
only after the user said yes to recording it.

## Reward for noticing a wrong fix (2026-10-15)

- **What**: `reward = R × C + (1 − R) × λ·D` in place of `R × C` (R = resolved, C = compliance), with every
  term re-checked in the sandbox at reward time, never read from the reports:
  - C, check discriminativeness: the fix's checks re-run on the base commit and on the patch; + for at
    least one red → green check.
  - C, honest record: the fix report's before/after results match the re-run; − for "fail" recorded on a
    check that exits 0 before the change, or "N/A".
  - C, baseline: the existing tests of the changed files re-run before and after; + for no new failure.
  - D (unresolved only): the verdict is not `verified` and the re-run confirms an objective failure — a
    check that fails on the base commit and still fails on the final patch, or a new failure against the
    baseline. Optionally more when round 2 actually edits code.
  - T, check correctness against the gold patch (unresolved via `(1 − R) × λ·T`, and inside C on solved
    rollouts): each check re-run on the base commit, the task's gold patch and the agent's patch. + for at
    least one right check (fails on base, passes on gold); − for a misread check (fails on gold, passes
    only on the agent's patch); 0 when every check passes on base. The gold patch is used at reward time
    only and never shown to the agent.
  - λ small (e.g. 0.1) so a solve always outweighs the bonus; no verdict term in C (on solved rollouts it
    would only punish doubt and teach "always `verified`").
- **Why**: under `R × C` an unresolved rollout scores 0 whatever it noticed, and an all-unresolved GRPO
  group has no gradient, so detection is never rewarded. Measured (SWE-bench Verified 499, think on):
  `verified` is right 63% of the time, equal to the base rate; 3% of wrong fixes were doubted; 44% of
  checks go red → green; 15% of rollouts end with their own check still failing (resolved 36%). With the
  G9-5 / G8-2 docs (val 10 × 3) the evidence is in the trajectories: checks before the first edit 28/30,
  baseline 22/30. T separates better than red → green (699 checks of 450 rollouts re-run on base / gold /
  agent, 2026-10-16): a right check in 57% of resolved vs 25% of unresolved rollouts, a misread check in
  8% vs 26%. Among unresolved: misread 26%, only non-discriminating checks 22%, right but too narrow 22%,
  every check failing on all three 29%; a right check that the agent's patch fails: 3 checks in all.
- **Open points when picked up**:
  - Reach of D: about a quarter of unresolved rollouts at most. Re-grading the 203 unresolved patches
    (2026-10-14): 76% fail only F2P (the issue was misread, and every signal the agent can see says
    success), 24% also break existing tests. In the val check 2026-10-15 all 12 wrong `verified` fixes were
    of the first kind, so D would have been 0 for each. Low priority on its own; T reaches about half of the
    unresolved (misread 26% penalized, non-discriminating 22% at 0).
  - T's path to self-correction: agents fix until their own checks pass, so a right check almost never
    fails on the agent's patch (3 of 699). Once training turns misread checks into right ones, a wrong fix
    leaves a right check failing, which is the in-session signal the fix ↔ test loop needs.
  - T, open: "right but too narrow" (22% of unresolved) passes T; it needs a coverage term such as the lines
    the gold patch changes. Misread on solved rollouts (8%) looks like checks fitted to the agent's own names
    or messages; separate assertion failures from import / name errors before penalizing. "Fails on all
    three" (21% of checks) mixes broken checks with re-run environment gaps (django settings, cwd): the
    reward's check runner must match the agent's environment. Three re-runs per rollout.
  - Anti-gaming: D needs re-run evidence, not a verdict; a failing check must also fail on the base commit.
  - Re-running checks and tests adds tens of seconds to minutes per rollout.
  - Exit codes misread checks that print instead of asserting.
  - D stays near 0 for misread issues (about 80% of unresolved: only F2P fails). Privileged training signal
    (part of F2P shown to the agent, reward on the rest, annealed away) was considered and is not planned
    (user, 2026-10-15). Self-correction would also need
    repair tasks that start from a wrong patch (the 203 unresolved patches re-graded 2026-10-14, SWE-smith
    mutations).
  - Implementation: a speckit_bug `ComplianceEvaluation` in `workflow_scoring.py` and a new
    `compliance_reward.mode` in `config.yaml`, both currently being edited by another session.
- **Origin**: fix ↔ test loop analysis 2026-10-14/15 (G8-1 fired 7/499; G8-2, G9-5 in `03-decisions.md`;
  `06-smoke.md` val check 2026-10-15); gold-patch check re-run 2026-10-16.
