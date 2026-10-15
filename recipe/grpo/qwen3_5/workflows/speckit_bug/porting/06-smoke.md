# Smoke: speckit_bug  (2026-10-12)

Setting: Qwen3.5-9B, rllm openhands-sdk 1.42.1, 150 turns, 262k ctx, no condenser, T=1.0 / top_p 0.95,
no max_tokens; vLLM docker v0.25.1 (`hermes_lenient2`); `swegym293_aidlc`, `prefix`, hidden git history.
Tasks: 5 local-image SWE-Gym tasks (indices 1,3,9,103,168), 1 attempt, all solved by base no-think before.
Run dir: `/gpfs/home/daink/2026-2_DFM/speckit_smoke/`.

| | think off | think on |
|---|---|---|
| resolve | 5/5 | 5/5 |
| full workflow in order | 2 (MONAI-3384, moto-4950) | 2 (MONAI-1884, 2238) |
| reports written but after the fix | 1 (moto-7365) | 1 (moto-7365) |
| entry doc never read | 2 (1884 looked under /testbed; 2238 never looked) | 2 (3384, 4950 looked under /testbed) |
| first correct entry-doc read (median step) | 6 | 2 |
| steps | 55–114 | 25–74 |
| text-only / early finish | 0 | 0 |
| network | 0 | 0 |
| repo pollution | `/testbed/IMPLEMENTATION_SUMMARY.txt` (1884) | temp `/testbed/test_issue.py`, removed (7365) |
| rounds > 1 | 0 (all `verified` in round 1) | 0 |

Comparison (same setting, SWE-bench Verified 499, aidlc_v4): entry doc read correctly first 91.0% / 89.6%,
never found after a `/testbed` lookup 3.8% / 6.2%, first read at step 0.

Findings → gaps (open, user chose to stop here 2026-10-13):
- G10-4: entry path mis-resolved under `/testbed` when read late; instruction should make the read the
  first action and say `/speckit` is at the filesystem root, outside the repo.
- G5-2: stray files in the repo despite the report rules; make it explicit in `core-workflow.md`.
- The round loop is untested.

## Val check (2026-10-15) — checks before the change + stricter verdict (G9-5, G8-2)

SWE-bench Verified val set (`recipe/grpo/qwen3_5/val_tasks.txt`, 10 tasks) × 3 attempts, Qwen3.5-9B think
on, 150 steps, T=1.0 / top_p 0.95, instruction prefix, git history kept. `base` = the docs before this
change (run 2026-10-14), `new` = with it. Red → green = each check re-run on the base commit and on the
agent's patch in a fresh container.

| | base | new |
|---|---|---|
| resolved | 16/30 | 17/30 |
| a check run before the first repo edit | 8/30 | **28/30** |
| existing tests run before the first repo edit (baseline) | 4/30 | **22/30** |
| fix report has "Baseline: Existing Tests" / before-fail, after-pass recorded | 0 / 0 | 28 / 23 |
| checks red → green (re-run) | 20/29 (69%) | 23/32 (72%) |
| round-1 `verified` / of those unresolved | 27 / 13 | 28 / 12 |
| round 2 reached | 1 | 0 |
| mean steps | 56 | 58 |

- The new steps are followed, but the verdict and the loop do not change: the 12 wrong fixes pass all
  three conditions (their checks go red → green, no new failure against the baseline) because the
  agent's checks encode the same misreading of the issue as its fix.
- Of the 5 checks that pass before the change: 2 recorded "N/A" (not run before), 3 recorded "fail" but
  only print the error and exit 0.
- Kept for training: the behaviors now appear in most rollouts and the fix report records the evidence a
  reward can re-check (before/after per check, the baseline).
