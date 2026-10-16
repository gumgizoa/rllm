# 최종 요약 (smoke 3, 2026-10-14)

설정: Qwen3.5-9B, openhands-sdk 1.42.1, 150턴, 262k, T=1.0. SWE-Gym 기능 요청형 task 5개 × think off/on × 1회.
**표본이 작음**: 건수로 읽을 것. 이전 회차는 아래 각 smoke 섹션 참고.

| 항목 | think off | think on |
|---|---|---|
| 해결 | 4/5 (conan 실패) | 4/5 (conan 실패) |
| 진입 문서 읽음 | 2/5 | 4/5 |
| 문서를 `/testbed` 아래에서 찾음 | 0 | 0 |
| converge까지 전체 체인 | 0 (moto는 implement까지, dvc는 tasks까지 하고 step 한도 도달) | 2 (MONAI-1884, MONAI-3384) + moto 부분 |
| 깨진 도구 호출로 종료 | 0 | 0 |
| 스크립트 호출 오류 | 0 | 0 |
| plan.md에 issue의 API 이름 (plan 작성분) | 1/1 | 4/4 |
| contracts 줄 채움 (plan 작성분) | 1/1 (`<reason>`을 그대로 남김) | 3/4 (1884는 `README.txt`도 만듦, 3384는 줄 삭제) |
| Polish 제목 유지 (tasks.md 작성분) | 2/2 | 4/4 |
| 검증 스크립트를 `checks/`에 작성 | 0 | 3 |
| 검증 스크립트를 `/tmp`에 작성 | 2 | 2 |
| 코드 수정 전 `checks/` 실패 확인 | 0 | 1 (dvc) |
| 코드 수정 전 기존 테스트 실행 | 0 | 4 |
| converge 결과 | 없음 | 3건 모두 1회차 converged (moto는 `convergence-2.md`로 저장, 형식 불일치) |
| step 범위 | 57–150 | 26–90 |
| 의존성 설치 | 0 | dvc `pip install` 3회 (수용) |

**새 행동 발생** (`05-changes.md` "agent 행동 변화"의 새 행동 추가 행, 해당 단계까지 간 rollout 기준):

| 행 | 새 행동 | think off | think on |
|---|---|---|---|
| 2 | constitution이 빈 템플릿이면 생략 기록 (plan 작성분) | 1/1 | 4/4 (dvc는 "Passed - Constitution is template-only (no gates)"로 다른 문구) |
| 3 | Phase 1 파일 모두 기록 (data-model·quickstart 둘 다, plan 작성분) | 1/1 | 4/4 |
| 3 | 그중 `N/A — <이유>` 사용 | 0/1 | 1/4 (1884 data-model만) |
| 4 | user story별 `### Tests for User Story N` (tasks.md 작성분) | 1/2 (dvc, 경로는 `checks/` 아님) | 4/4 (경로 `checks/` 4/4) |
| 5 | 빈 phase를 `No tasks — <이유>`로 유지 (tasks.md 작성분) | 1/2 | 4/4 |
| 8 | 구현 전 기존 테스트 실행 / 구현 후 재실행 | 0 / 미측정 | 4 / 미측정 |
| 10 | 실패 task를 미체크로 두고 계속 | 발생 확인 0 (dvc의 미체크는 150 step 도달) | 0 (미체크 task 남긴 rollout 0/4) |
| 11 | 회차 보고서 + `- **Outcome**:` 줄 | 0/5 | 2/5 형식 준수 + moto 형식 불일치 1 |
| 12 | `tasks_appended` → implement·converge 2회차 | 0/5 | **0/5** (moto의 `convergence-2.md`는 1회차 보고서 이름 오류) |

## 남은 문제
- 코드 수정 전 실패 확인, `checks/` 위치, contracts 줄의 실제 사유 기록: 일부만 지켜짐 → compliance scorer로 넘김(`later.md`).
- think off의 진입 문서 미열람 3/5: instruction은 smoke 2와 같으므로 변동으로 판단.
- converge 보고서 형식 불일치 → scorer 설계 때 다룸.
- **2회차 반복(행 12)과 실패 task 계속(행 10)은 smoke에서 한 번도 발동하지 않음** → 검증되지 않은 규칙. SWE-bench Verified 499에서도 2회차는 거의 없음(아래 "참고"), converge가 사실상 항상 `converged`를 냄 → `later.md` "No path back to spec/plan".
- conan-13721은 smoke 1–3 모두 미해결.

## 참고: SWE-bench Verified 499 (smoke 아님, 2026-10-15)

설정: smoke와 같은 모델·harness·150턴·262k·T=1.0, think on, `instruction_position=suffix`, git history 공개, 커밋 `7c88c420`.
결과 `rllm-home/eval_results/swebv499_speckitsdd_262k-150_think_t1/`. resolve 245/499 (workflow 없음 300/499).
새 행동 발생 (각 산출물을 쓴 rollout 기준):

| 행 | 새 행동 | 발생 |
|---|---|---|
| 2 | constitution 생략 기록 ("skipped — template" 문구) | 282/488 |
| 3 | data-model·quickstart 둘 다 기록 | 417/488 |
| 4 | user story별 Tests 소절 / 테스트 task 경로 `checks/` | 456/477 / 463/477 |
| 5 | 빈 phase `No tasks — <이유>` | 302/477 |
| 11 | `convergence.md` 작성 / `- **Outcome**:` 줄 형식 준수 | 335/499 / 269/334 |
| 12 | Convergence phase 추가 / `convergence-2.md` 작성 | **16/477 / 4/499** |

---

# Smoke: speckit_sdd  (2026-10-14)

Setting: Qwen3.5-9B, rllm openhands-sdk 1.42.1, 150 turns, 262k ctx, no condenser, T=1.0 / top_p 0.95, no
max_tokens; vLLM docker v0.25.1 (`hermes_lenient2`), think off :8231 / on :8232; `swegym293_aidlc`, `prefix`,
hidden git history. Tasks: 5 feature-request SWE-Gym tasks (sorted indices 1, 9, 57, 159, 182 = MONAI-1884,
MONAI-3384, conan-13721, moto-7061, dvc-4075), 1 attempt each; all 5 solved by base no-think 80t/131k before.
Run dir: `/gpfs/home/daink/2026-2_DFM/speckit_smoke/` (`results/speckit_sdd_think{off,on}_150t_20261014_*`,
`analyze_sdd.py`).

| | think off | think on |
|---|---|---|
| resolve | 4/5 (3384 ✗) | 3/5 (conan ✗, dvc ✗) |
| entry doc read at the real path | 4/5 (step 1–3; conan never) | 5/5 (step 0–3) |
| looked under `/testbed/speckit-sdd` | 0 | 0 |
| full chain through converge | 1 (moto-7061) | 2 (MONAI-1884, moto-7061) |
| chain through tasks/implement, no converge report | 2 (3384, dvc — both cut by a malformed tool call) | 1 (3384: all 11 tasks `[X]`, converge doc read, no `convergence.md`) |
| read 01-specify, then solved without the workflow | 1 (1884) | 2 (conan; dvc cut at step 20) |
| tasks.md written before the first repo edit (where edits detectable) | 2/2 | 2/2 |
| script calls ok / error / colour codes | 7 / 0 / 0 | 12 / 0 / 0 |
| spec checklist fully ticked | 3/4 | 2/4 (1884, 7061 left all 16 unchecked → implement took the proceed branch) |
| issue's API names in plan.md (C-1 verbatim check) | 3/3 | 4/4 |
| converge outcome | 7061: written, Outcome line not in the decided format | 1884, 7061: `converged` round 1 |
| round 2 | 0 | 0 |
| ended by a malformed tool call (text-only turn) | 2 (3384 → unsolved; dvc, still solved) | 1 (dvc at step 20 → unsolved) |
| steps | 67–83 | 21–88 |
| network | 0 | 0 |
| repo test files in the patch | 1 (dvc: `tests/unit/command/test_imp_url.py`, against G9-1) | 0 |
| stray files | only test temp dirs under `/tmp/tmp*` | none |

## Findings
1. **Entry path fix works.** 9/10 opened `/speckit-sdd/core-workflow.md` at step 0–3; zero `/testbed` lookups
   (speckit_bug smoke: 3/10 looked under `/testbed`). The fresh instruction states first action + root path.
2. **Scripts work as shipped.** 19 calls, no errors, no escape codes (G7-8 jq wrapper).
3. **C-1 verbatim is fine on these tasks.** Every plan.md names the issue's API (TileOnGrid, ConcatItemsd,
   describe_tags, no-exec/import-url); 5/8 checklists fully ticked; the rest left unticked and proceeded.
4. **Malformed tool calls end 3/10 rollouts** (`<tool_call>\n<file_editor>\n<parameter=…>` without
   `<function=…>`, or `<function=terminal=command>`): the parser returns text, the SDK finishes. 2 of the 3
   failures. Not seen in the speckit_bug smoke (0/10). Parser/model issue (G10), not document text; may grow
   with context length (SDD writes long heredoc artifacts) **(inferred)**.
5. **Drop-out after the specify document**: 3/10 read 01-specify (and the spec template) and then solved
   directly, writing nothing. Both conan rollouts are among the non-followers.
6. **Converge**: reached in 3/10; `converged` in round 1 twice; one report lacks the `- **Outcome**:` field
   format; one rollout read 05-converge and finished without writing the report. Round 2 untested.
7. One repo test file edited (dvc off) despite G9-1.

## New gap rows (open)
- G2-5: drop-out after 01-specify (finding 5).
- G8-5: converge report missing / Outcome format not followed (finding 6).
- G10-6: malformed tool-call endings (finding 4) — harness/parser side.

# Smoke 2: speckit_sdd after the 2026-10-14 revisions  (same setting and tasks)

Revisions in effect: Phase 1 always written (N/A body / contracts in plan.md's tree), phase headings always
kept (`No tasks —`), tests as `checks/` scripts that fail then pass + existing tests before/after.
Runs: `results/speckit_sdd_think{off,on}_150t_20261014_1624*`.

| | smoke 1 off / on | smoke 2 off | smoke 2 on |
|---|---|---|---|
| resolve | 4/5 · 3/5 | 4/5 (conan ✗) | 4/5 (conan ✗) |
| entry doc read | 4/5 · 5/5 | 4/5 (3384 never) | 5/5 |
| full chain through converge | 1 · 2 | 1 (1884) | **5** |
| ended by malformed tool call | 2 · 1 | 0 | 0 |
| converge outcome | — | 1884 converged r1 | 5× converged r1; round 2 never |
| Phase 1: data-model + quickstart written (plans written) | — | 2/2 (1884 both N/A, 7061 data-model N/A) | 4/5 (dvc: no quickstart); all with content |
| contracts recorded in plan.md tree (N/A or list) | — | 0/2 (template comment left) | 2/5 (conan, dvc; dvc also made `contracts/README.md`) |
| Setup / Foundational headings kept | — | 2/2 | 4/5 |
| Polish heading kept (corrected 2026-10-14) | — | 2/2 | 5/5 |
| `No tasks —` line used | — | 2/2 | 4/5 |
| test tasks pointing at `checks/` in tasks.md | — | 2/2 | 2/5 |
| verification scripts written under `checks/` | — | 1 (moto, after the first repo edit) | 1 (dvc) |
| verification scripts written to `/tmp/*.py` instead | — | 2 (3384, conan) | 1 (moto `/tmp/new_describe_tags.py`) |
| fail-first run of a `checks/` script before the code | — | 0 observed | 0 observed |
| existing tests run before the first repo edit (baseline) | — | 1 (1884) | 3 (1884, 3384, dvc) |
| network / install | 0 · 0 | dvc: `pip install networkx` ×3 | 0 (2 hits were quickstart text) |
| steps | 67–83 · 21–88 | 60–125 | 57–137 (dvc 137/150) |

## Findings
1. Think on now follows the whole chain 5/5 (smoke 1: 2/5); no malformed-call endings in 10 rollouts
   (smoke 1: 3/10). Resolve 8/10 (smoke 1: 7/10). Small n; the malformed-call change is not explained by
   a document change.
2. The new rules are followed partly: Phase 1 files yes; `No tasks —` yes; Polish heading kept 7/7 (first counted as dropped — analyzer missed `Phase N`);
   **contracts tree line left as the template comment in 5/7**; **TDD not observed** — scripts mostly not in
   `checks/`, none run to fail before the code.
3. Think off still drops out (3384 never opened the entry doc; conan read only 01; dvc wrote only spec.md).
4. One dependency install (dvc off, `pip install networkx`), against G9-3.
5. dvc on used 137/150 steps.

New gap rows (open): G9-5 Polish heading dropped (later found to be a measurement error); G9-6 contracts tree not filled; G9-7 checks/ TDD not
followed (scripts to /tmp, no fail-first); G6-2 pip install.

# Smoke 3: after Revision 3 (rules moved where the agent looks)  (same setting and tasks)

Runs: `results/speckit_sdd_think{off,on}_150t_20261014_1655*`. Instruction and system prompt unchanged since
smoke 2; only stage docs / templates / core-workflow rows changed.

| | smoke 2 off · on | smoke 3 off | smoke 3 on |
|---|---|---|---|
| resolve | 4 · 4 | 4/5 (conan ✗) | 4/5 (conan ✗) |
| entry doc read | 4 · 5 | **2/5** (1884, 3384, conan never) | 4/5 (conan never) |
| full chain through converge | 1 · 5 | 0 (moto to implement; dvc hit 150 steps) | 2 (1884, 3384) + moto (skipped 04 doc, converge report as `convergence-2.md`) |
| Polish heading kept (tasks.md written; corrected) | 2/2 · 5/5 | 2/2 | 4/4 |
| **contracts line filled** (plans written) | 0/2 · 2/5 | 1/1 (left literal `<reason>`) | **3/4** (1884 also made `contracts/README.txt`; 3384 deleted the line) |
| verification scripts under `checks/` | 1 · 1 | 0 | **3** (1884, moto, dvc) |
| scripts in `/tmp/*.py` | 2 · 1 | 2 (3384, moto) | 2 (moto, dvc) |
| **checks/ script run and seen failing before the code** | 0 · 0 | 0 | **1** (dvc); moto ran its checks 4× before the code, no failure seen in the output |
| existing tests before the first repo edit | 1 · 3 | 0 | 4 |
| network / install | dvc ×3 · 0 | 0 | dvc `pip install` ×3 (accepted, G6-2) |
| steps | 60–125 · 57–137 | 57–150 (dvc hit the limit) | 26–90 |

## Findings
1. The moved rules help where the agent reaches the stage: contracts line filled 4/5 plans (smoke 2: 2/7),
   `checks/` scripts 3/10 (2/10), first fail-first run 1/10 (0/10). Still minority behaviour for TDD.
   Polish was never dropped (7/7, 6/6): the earlier 0/7 was an analyzer error (`Phase N` not counted).
2. Think off skipped the entry doc in 3/5 although the instruction is unchanged (smoke 2: 1/5) — T=1.0
   variance on n=5; the first action was `find`/`think` on the repository.
3. conan-13721 unsolved in all 6 rollouts of smokes 1–3, with or without the workflow.
4. Converge report: one off-format (`convergence-2.md` in round 1, `**Status**:` instead of `Outcome`) —
   G8-5 still open.
