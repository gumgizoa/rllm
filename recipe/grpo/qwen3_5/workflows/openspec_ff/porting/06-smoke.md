# Smoke: openspec_ff

Setting (same as speckit_bug's smoke): Qwen3.5-9B, rllm openhands-sdk 1.42.1, 150 turns, 262k ctx, no
condenser, T=1.0 / top_p 0.95, no max_tokens; vLLM docker v0.25.1 (`hermes_lenient2`; GPU6 :8231 think off,
GPU7 :8232 think on); `swegym293_aidlc`, `prefix`, hidden git history; agent image `rllm-agent-f268c8df48c7`.
Tasks: the 5 local-image SWE-Gym tasks (indices 1,3,9,103,168), 1 attempt each. Run dir
`/gpfs/home/daink/2026-2_DFM/openspec_smoke/`.

## Run 1 (2026-10-13) — invalid: the CLI hung under the agent's TTY

| | think off | think on |
|---|---|---|
| resolve | 1/5 | 0/5 |
| AGENT_TIMEOUT (3600 s) | 4 | 5 |
| LLM steps | 4–44 | 2–7 |
| last call before the hang | `openspec new change "issue"` (4/4) | `openspec new change "issue"` (4/5), `C-c` after `openspec status` (1/5) |

- The one solve (think off, moto-4950) never opened `/opsx` and never ran `openspec` — no workflow.
- Every rollout that reached `openspec new change` hung there: the agent's terminal is a TTY, and the CLI in
  interactive mode creates the change but never exits (spinner left up). Reproduced with
  `script -qec 'openspec new change issue'` (timeout at 15 s); with `CI=1` the same sequence takes 0.9 s.
  The probes in `cli-probe/` ran without a TTY and missed it.
- What did work: setup, `/opsx` docs, the entry doc read at step 1–2 in the think-on runs, `cat /opsx/stages/01-new.md`
  before the first CLI call.
- → gap G10-6 (`02-gaps.md`, open).

## Run 2 (2026-10-14) — after G10-6 (`CI=1` in the wrapper)

Results: `openspec_smoke/results/openspec_ff_think{off,on}_150t_20261014_*`; per-episode view
`openspec_smoke/analyze_openspec.py` (tool calls + the collected `/openspec` tree).

| | think off | think on |
|---|---|---|
| resolve | 5/5 | 4/5 (moto-4950 not solved) |
| timeouts / text-only ends | 0 / 0 | 0 / 0 |
| steps | 45–111 | 54–71 |
| entry doc read (step) | 4/5 (0, 2, 3, 6; moto-4950 never) | 5/5 (0 ×4, 2) |
| under-`/testbed` lookups of `/opsx` or `/openspec` | 1 episode (1884, then read correctly) | 1 episode (moto-4950) |
| ran the CLI chain (new → … → archive) | 3/5 (3384 read the docs then dropped the workflow; 4950 never opened it) | 5/5 |
| `tasks.md` written before the first repo edit (where measurable) | 2/2 | 4/4 |
| `verify.md` written | 1/3 of the archiving runs | 4/5 |
| archived | 3/5 | 5/5 |
| **first archive failed: "MODIFIED/REMOVED/RENAMED operations require an existing spec"** | 2/3 | 4/5 |
| archive called more than twice (rule G8-4: rerun once) | 2 (3 and 6 calls) | 2 (3 and 4 calls) |
| specs deleted + `skip_specs: true` to get past archive | 0 | 2 (2238, 3384) |
| repo test files in the patch / network / stray files in `/testbed` | 0 / 0 / 0 | 0 / 0 / 0 |
| scratch scripts left in `/tmp` (outside the repo) | 3 episodes | 3 episodes |
| verify rounds > 1 | 0 | 0 |

Findings → new gap rows (open): G7-5 (first delta written as MODIFIED although the entry document says
every delta is ADDED), G8-5 (archive retried past the rule, specs deleted and `skip_specs` set to get
through), G2-9 (verify skipped before archive, mostly think off).
For comparison on the same 5 tasks: speckit_bug smoke 5/5 + 5/5, base no-think 5/5.

## Run 3 (2026-10-14) — after G7-5 (specs start empty → ADDED) and G2-9 (verify gate)

| | think off (run 2 → 3) | think on (run 2 → 3) |
|---|---|---|
| resolve | 5/5 → 5/5 | 4/5 → 4/5 |
| ran the CLI chain | 3/5 → 4/5 (moto-4950 again never opened the docs) | 5/5 → 4/5 (moto-7365: shell stuck, below) |
| first spec contains MODIFIED/REMOVED | 2/3 → 1/4 | 4/5 → **5/5** |
| first archive failed on "require an existing spec" | 2/3 → 0/3 | 4/5 → **4/4** |
| `verify.md` before archive (archiving runs) | 1/3 → 3/3 | 4/5 → 3/4 (3384 archived without it) |
| archive called > 2 times | 2 → 0 | 2 → 2 (1884, 4950: 4 calls each) |
| specs deleted / `skip_specs` to get past archive | 0 → 0 | 2 → 0 |
| repo test files in patch / network / stray files in `/testbed` | 0 / 0 / 0 | 0 / 0 / 0 |

- G7-5 worked for think off, not for think on: think-on agents read `openspec instructions specs` (with the
  new sentence) and still added a `## MODIFIED Requirements` section describing the old, wrong behavior next
  to the ADDED one (e.g. MONAI-2238: "**Reason**: Previous implementation incorrectly assigned…"). Every
  think-on run then fixed it to ADDED-only and archived. → gap G7-6 (open).
- G2-9 worked (think off 3/3 wrote verify.md before archiving).
- G8-5: no workaround (delete specs / `skip_specs`) any more; the over-limit retries left are think-on runs
  that hit the MODIFIED failure.
- think off moto-7365 finished right after apply (no verify, no archive); think on MONAI-2238 ended on a
  text message after a successful archive.
- think on moto-7365 (not solved): a shell heredoc with nested quotes left the terminal waiting for input at
  step 24; the next 55 steps were C-c / C-d / empty commands. Not specific to this port (agent shell quoting).

## Run 4 (2026-10-14) — after D-7 (no new stage), G7-6 (no change), G10-7 (config.yaml context + rules)

| | think off (run 3 → 4) | think on (run 3 → 4) |
|---|---|---|
| resolve | 5/5 → 4/5 (MONAI-3384 not solved) | 4/5 → **5/5** |
| entry doc read | 4/5 → 4/5 (moto-7365 never opened it) | 5/5 → 5/5 |
| ran the CLI chain from ff | 4/5 → 4/5 | 4/5 → 5/5 |
| first spec contains MODIFIED | 1/4 → **0/4** (REMOVED in 1) | 5/5 → **0/5** (REMOVED in 1) |
| first archive failed on "require an existing spec" | 0/3 → 0/4 | 4/4 → **0/4** |
| archive called > 2 times | 0 → 0 | 2 → **0** |
| `tasks.md` before the first repo edit (measurable) | — → 1/2 (3384 coded at step 48, planned at 81) | — → 5/5 |
| `verify.md` before archive (archiving runs) | 3/3 → **1/4** | 3/4 → 4/4 |
| archived | 3/5 → 4/5 | 4/5 → 4/5 (2238 wrote verify.md, then called finish instead of archive; tasks left unchecked) |
| text-only ends / timeouts / network / repo test edits / stray files in `/testbed` | 0 / 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 |
| steps | 61–102 | 53–83 |

- D-7: ff's own `openspec new change "issue"` ran in every rollout that followed the workflow; nothing broke.
- G10-7: MODIFIED is gone in both arms (the `rules` reach the agent at `instructions proposal|specs`); apply's
  context-conflict branch never fired (no "report the conflict" message, no text-only end).
- Open observation (no gap filed): think off skips the verify stage — in 3/4 archiving runs it never wrote
  `verify.md`; MONAI-1884 read only `core-workflow.md` and none of the stage documents. The G2-9 gate is in
  the entry document only. Think on followed it 4/4.

## Val ablation (2026-10-14) — verify → apply round rule (G8-1) on / off

SWE-bench Verified val set (`recipe/grpo/qwen3_5/val_tasks.txt`, 10 tasks) × 3 attempts per arm, Qwen3.5-9B
think on, 150 steps, T=1.0 / top_p 0.95, instruction prefix, git history kept. `loop` = the docs as they
were; `noloop` = the same docs with the round rule taken out (verify once → archive), byte-identical
otherwise. Each arm on its own vLLM server with identical flags.

| | loop | noloop |
|---|---|---|
| resolved | 16/30 | 19/30 |
| pass@3 | 70% | 70% |
| `verify.md` written | 20/30 | 27/30 |
| **round-1 CRITICAL ≥ 1** | **0/30** | **0/30** |
| `verify-2.md` written / repo edits after verify | 0 / 0 | 0 / 0 |
| all tasks checked | 25/30 | 28/30 |
| archived | 26/30 | 28/30 |
| mean steps | 72 | 71 |

- The loop never fired: verify's CRITICAL criteria (incomplete tasks, missing requirements) are checked
  against the agent's own tasks and specs, so every report said "no critical issues" — the 17 unsolved
  rollouts with a report included.
- The resolve gap is not the loop: most of it is sphinx-8593 (1/3 vs 3/3), where two loop-arm rollouts
  never wrote any planning artifact.
- Decision: G8-1 dropped; the committed docs are now the `noloop` docs.

## Run 5 (2026-10-15) — explore before ff (Explore extension)

Same setting as runs 2–4 (5 tasks × think off/on, 150 steps). vLLM: think off :8231, think on :8233 (reused,
one request each confirmed thinking off/on). Results: `openspec_smoke/results/openspec_ff_think{off,on}_150t_20261015_203601`;
counts from `explore_smoke` scans of the tool calls, then checked by hand on MONAI-2238 (on), MONAI-1884 (off),
moto-7365 (on, off).

| | think off | think on |
|---|---|---|
| resolve | 5/5 | 5/5 |
| entry doc read / never | 4/5 (moto-4950 never) | 4/5 (moto-4950 never) |
| explore entered | 3/5 (MONAI-3384 read the entry doc, then no workflow; moto-4950) | 4/5 |
| explore steps (open 00-explore → open 01-ff) | 13, 17, ~63 (moto-7365: never opened 01-ff, ran `openspec new change` at 67) | 22, 17, 25, 32 |
| "What We Figured Out" summary written | 3/3 | 2/4 (MONAI-1884, moto-7365: one-line note, no summary) |
| … in the turn that opens 01-ff (G2-12) | 1/3 (others: a `think` tool call one turn earlier) | 0/2 (`think` call 1 or 14 turns earlier) |
| composed code run during explore (G9-5: not allowed) | **3/3** (`python -c` / `python3 << EOF` 2, 2, 16×) | **4/4** (1 each) |
| files written during explore (G9-5: not allowed) | 0/3 | **1/4** (moto-7365: `cat > /tmp/test_decimal_issue.py`, `/tmp/test_sub_issue.py`) |
| existing code/tests run during explore | 1/3 | 3/4 |
| ff opened after explore | 2/3 | 4/4 |
| design.md cites explore findings (by hand, 2 checked) | MONAI-1884: line 678-679 and the numpy/torch single-item results from explore steps 14-15 | MONAI-2238: the loop-order analysis of explore step 19 |
| design.md Decisions with an alternative | 3/3 | 4/4 |
| steps | 38–121 | 21–85 |

- explore ran and fed ff: the designs restate what explore found, with code locations and run results.
- The no-code boundary does not hold: every explore run composed and ran code (one-line `python -c` or a
  heredoc piped to `python3`), and one wrote reproduction scripts to `/tmp`. → G9-6 (open).
- The summary lands in a `think` tool call one turn before the ff document is opened, not in that turn (5/6
  summaries). It is still in the trajectory; → G2-14 (open).
- Workflow skipped as in earlier runs: moto-4950 never opens the entry document (both arms, runs 2–5);
  think-off MONAI-3384 reads it and works without the workflow.

## Run 6 (2026-10-16) — after G9-6 (composed code named in the guardrail) and G2-14 (summary in a tool call before ff)

Same setting as run 5 (:8231 off, :8233 on). Results: `openspec_smoke/results/openspec_ff_think{off,on}_150t_20261016_120157`.
Explore window = from opening `00-explore.md` to opening `01-ff.md` or writing the proposal; checked by hand on
moto-7365 (off, on) and MONAI-3384 (on).

| | think off | think on |
|---|---|---|
| resolve | 5/5 | 5/5 |
| explore entered | 4/5 (MONAI-3384: entry doc at step 17, no explore, no workflow) | 4/5 (MONAI-3384: entry doc, then straight into the code, ff later; design at 49) |
| summary written (in a tool call or message before ff/proposal) | 3/4 (moto-7365 none) | 2/4 (MONAI-2238, moto-7365 none) |
| clean explore (no composed code, no file) | **0/4** | **2/4** (MONAI-1884, moto-4950) |
| composed code during explore | 4/4 (2, 3, 17, 6 calls) | 2/4 (1, 17) |
| files written during explore | 3/4 (moto-7365: repro scripts in `/testbed`, removed before the end) | 1/4 (moto-7365: `/tmp` scripts, one of them a fix script for `dynamo_type.py` at step 38) |
| 01-ff.md opened after explore | 1/4 | 3/4 |
| change archived | 2/5 (moto-4950, moto-7365 left the workflow after explore; MONAI-3384 never in it) | **5/5** |
| repo files in the final patch other than source | 0 | 0 |
| steps | 48–102 | 52–100 |

- G9-6's wording did not stop composed code: think off 4/4 (run 5: 3/3), think on 2/4 (run 5: 4/4).
- think off moto-7365 and moto-4950: explore turns into debugging and fixing, and the planning chain never
  starts. think on moto-7365 does the same until step 82, then writes the artifacts afterwards (fix first, plan later).
- think on: two fully clean explore runs (MONAI-1884, moto-4950: reading only, summary in `think`, ff at 11).
