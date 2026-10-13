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
