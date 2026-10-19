# 최종 요약 (smoke 2, 2026-10-16)

설정: Qwen3.5-9B (vLLM docker, reasoning parser qwen3), openhands-sdk 1.42.1, 150 turns, 262k ctx, condenser 없음,
T=1.0. `swegym293_aidlc` task 8개(MONAI-1884·2238·3384, conan-13721, moto-4950·7061·7365, dvc-4075) × think on ×
1회. **표본이 작음**: 건수로 읽을 것.

| 항목 | think on |
|---|---|
| 해결 | 7/8 (conan-13721 실패) |
| 진입 문서를 첫 행동으로 읽음 / 저장소 아래에서 찾음 | 8/8 / 0/8 |
| 명령 4개 순서대로 완료 | 8/8 |
| 텍스트 응답·조기 종료 | 0/8 |
| 저장소 오염 (patch에 workflow 파일) | 0/8 |
| spec 폴더 1개 (날짜 + 이름, G5-2) | 8/8 |
| issue 원문 `initialization.md` 저장 (새 행동 #1) | 8/8 |
| 재사용 질문을 저장소 경로로 답함 (새 행동 #3) | 7/8 |
| task group 반복 구현, 미체크 0 (새 행동 #6) | group 2개 이상 7/8, 미체크 0 8/8 |
| roadmap `⚠️ No Updates Needed` (새 행동 #9) | 7/8 |
| 보고서 절 번호 1·2·3 (G5-8) | 7/8 |
| `checks/` 테스트 스크립트 작성 | 4/8 |
| tasks.md에 테스트 작성 task | 2/8 |
| 전체 테스트 실행 시도 / 전체 수치 보고 | 1/8 / 0/8 |
| step 범위 | 41–77 |

## 남은 문제
- 테스트 먼저 작성(원문 task group의 x.1)이 드묾: tasks.md 2/8, 스크립트 4/8. 문서가 분명하므로 agent 잘못(G9-6) →
  학습 대상, compliance 채점기가 있어야 학습에서 오를 수 있음.
- 전체 테스트 실행을 대부분 바꾼 모듈 테스트로 대신함(G8-5) → 학습 대상. 실행이 안 되는 저장소가 많다는 점은 G8-2에서
  받아들임.
- 보고서 양식 이탈: 양식 밖 절 추가 2/8, 양식 무시 1/8(dvc) → 학습 대상.
- conan-13721은 smoke 1·2와 speckit_sdd 3회 모두 실패: workflow와 무관한 어려운 task로 보임(미확인).
- think off는 돌리지 않음(사용자 결정).

# Smoke: agentos_v2

## Smoke 1 (2026-10-16)

- 설정: Qwen3.5-9B, vLLM docker (`daink-speckit-vllm-thinkon`, :8232, reasoning parser qwen3, hermes_lenient2),
  openhands-sdk 1.42.1, 150 turns, 262k ctx, condenser 없음, T=1.0, top_p 0.95, 1 attempt. **think on만** (사용자).
- 데이터: `swegym293_aidlc`, `instruction_position=prefix`, git history 숨김. task 8개(bugfix 세트 + feature 세트
  합집합) = 1, 3, 9, 57, 103, 159, 168, 182 → MONAI-1884, MONAI-2238, MONAI-3384, conan-13721, moto-4950,
  moto-7061, moto-7365, dvc-4075. 동시 8.
- 문서: commit 직전 상태(workflow sha256 `cbf2c64b…`). G9-5(migrations 커밋 줄 삭제) 반영 전이며, 해당 standard는
  이 task들과 무관.
- 결과: `speckit_smoke/results/agentos_v2_thinkon_150t_20261016_164923/`. 분석 스크립트:
  `scratchpad/agentos-smoke/an.py` (episode의 tool call과 `artifacts.workflow_outputs`). 아래 수치는 원본 artifact
  2건 이상으로 확인함(괄호 안 확인한 rollout).
- **표본이 작음**: 건수로 읽을 것.

| 항목 | 결과 | 비고 |
|---|---|---|
| 해결 | 7/8 | conan-13721 실패 (speckit_sdd think on에서도 3/3 실패) |
| 진입 문서 첫 행동 | 8/8 (call 0이 7건, call 1이 1건) | `/testbed/agent-os` 참조 0/8 |
| 명령 4개 순서대로 열기 | 7/8 | dvc-4075는 write-spec을 건너뜀, `spec.md` 없음 (raw call 27-29) → G2-4 |
| tasks.md 작성 → 첫 `/testbed` 편집 순서 | 8/8 | |
| 텍스트 응답·조기 종료 | 0/8 | 모두 `finish`로 종료 |
| spec 폴더 개수 | 8/8이 1개 | 날짜 + agent가 지은 이름 (G5-2) |
| 저장소 오염 | 0/8 | patch는 소스 파일만. stray는 conan·dvc 테스트가 만든 `/tmp/tmp*` |
| step 범위 | 34–63 | rollout 237–632초 |

**새 행동 추가 (05-changes "agent 행동 변화")**

| # | 행동 | 발생 | 확인 |
|---|---|---|---|
| 1 | issue 원문을 `planning/initialization.md`로 저장 | 8/8 | MONAI-1884 (제목 줄 + 원문), moto-7061, moto-7365 |
| 3 | 재사용 질문을 저장소 검색으로 답함 | 7/8 ("Existing Code to Reference"에 저장소 경로) | MONAI-3384, moto-7061. MONAI-1884는 "Reusability Opportunities"만 씀 |
| 6 | 남은 task group 반복 구현 | 6/8에서 group 2개 이상, 8/8 미체크 0 | MONAI-2238(2), dvc-4075(3) |
| 9 | roadmap 없음 → `⚠️ No Updates Needed` | 8/8 | 전 보고서 3절(또는 번호를 바꾼 2절) |

**발견 (새 gap 행, open)**
- **G9-6 테스트 sub-task 누락**: tasks.md 6/8에 테스트 작성 sub-task가 없고, `checks/` 스크립트는 2/8(conan, moto-7061).
  MONAI-1884 tasks.md에 "Test changes are handled separately"라는 메모. task 메시지의 "테스트는 처리됨"이 원문
  템플릿의 "Write 2-8 focused tests"를 이긴 것으로 보임.
- **G8-5 전체 테스트**: 전체 실행 시도 1/8(conan, SDK terminal 300초 timeout 뒤 profile 테스트 22개로 대체), 전체
  수치를 보고한 경우 0/8. 나머지 7건은 바꾼 모듈의 테스트(2–488개)를 돌려 4절에 기록.
- **G2-4 write-spec 건너뜀**: 1/8 (dvc-4075).
- **G5-8 보고서 절 번호**: 2절 삭제(G5-6)로 1·3·4절이 된 양식을 3/8이 2·3절로 다시 번호를 매겼고, 4/8이 자체 절을
  추가. 번호로 찾는 채점기는 틀림.

**비교 (같은 서버, think on, 같은 task)**
- speckit_bug smoke(2026-10-12): MONAI-1884·2238·3384, moto-4950·7365 모두 해결, step 25–74. agentos_v2 같은 5개: 5/5.
- speckit_sdd smoke 3회(2026-10-14): MONAI-1884·3384, moto-7061 해결, conan-13721 3/3 실패, dvc-4075 2/3.
  agentos_v2 같은 5개: 4/5 (conan 실패), step 34–60 (sdd 21–137).

**판정 (smoke 1, 2026-10-16, 사용자 확인)**: 문서가 분명하고 실행 가능한데 벗어난 것은 agent 잘못으로 보고 문서를
고치지 않음(원칙 6).

**학습 대상** (채점기·compliance 보상이 있어야 학습에서 오를 수 있음)
- 테스트 작성 sub-task와 `S/checks/` 스크립트 (G9-6): tasks.md 1/8, 스크립트 2/8.
- 전체 테스트 실행 시도와 4절 수치 (G8-5): 시도 1/8, 보고 0/8.
- 명령 4개 모두 거치기 (G2-4): 7/8 (dvc가 write-spec 건너뜀).
- 보고서 양식 밖 절 추가: 4/8 ("Implementation Summary", "Manual Verification" 등). 양식은 core-workflow
  "Write each file in the structure its document gives".

**workflow 보완**: G5-8 보고서 절 번호 (우리 G5-6 편집이 만든 1·3·4 번호) → 1·2·3으로 다시 매김 (반영, smoke 2에서 확인).

## Smoke 2 (2026-10-16)

- 설정·task: smoke 1과 같음 (think on, 8개 동시). 문서: G9-5(migrations 커밋 줄 삭제), G5-8(보고서 절 1·2·3) 반영.
- 결과: `speckit_smoke/results/agentos_v2_thinkon_150t_20261016_174628/` (17:46–17:57). 원본 확인: conan 보고서 3절과
  전체 실행 출력, dvc 보고서, moto-4950 tasks.md.

| 항목 | smoke 2 | smoke 1 |
|---|---|---|
| 해결 | 7/8 (conan-13721 실패) | 7/8 |
| 진입 문서 첫 행동 (call 0–1) | 8/8 | 8/8 |
| 명령 4개 순서대로 | **8/8** | 7/8 |
| 텍스트 응답·조기 종료 / 저장소 오염 | 0/8 / 0/8 | 0/8 / 0/8 |
| spec 폴더 1개 | 8/8 | 8/8 |
| step 범위 | 41–77 | 34–63 |
| **보고서 절 번호가 양식대로 (G5-8)** | **7/8이 1·2·3** (dvc는 양식 자체를 따르지 않음) | 5/8이 1·3·4, 3/8이 스스로 번호 변경 |
| 양식 밖 절 추가 | 2/8 (MONAI-3384, moto-7061) + dvc | 4/8 |
| 새 행동 #1 initialization.md | 8/8 | 8/8 |
| 새 행동 #3 재사용을 저장소 경로로 | 7/8 (conan은 경로 없음) | 7/8 |
| 새 행동 #6 group 2개 이상 반복 | 7/8, 미체크 0 | 6/8 |
| 새 행동 #9 roadmap `⚠️ No Updates Needed` | 7/8 (dvc 양식 무시) | 8/8 |
| 학습 대상: tasks.md에 테스트 작성 task | 2/8 | 2/8 (같은 기준으로 재집계) |
| 학습 대상: `checks/` 스크립트 작성 | 4/8 (conan, moto-4950, moto-7061, dvc) | 2/8 |
| 학습 대상: 전체 테스트 실행 | 시도 1/8 (conan `timeout 300 pytest -x`, 첫 에러에서 멈춤 27초), 전체 수치 보고 0/8 | 시도 1/8, 보고 0/8 |

- G5-8 수정은 의도대로 동작: 양식을 따른 7개 보고서가 모두 1·2·3 번호.
- 새 workflow 보완 항목 없음. dvc-4075가 보고서 양식을 통째로 무시한 것(1/8)은 core-workflow "Write each file in the
  structure its document gives"가 분명하므로 agent 잘못(학습 대상).

## SWE-bench Verified 499 평가 (2026-10-16 18:33 – 10-17 06:25)

- 설정: `rllm-home/run_swebv499.sh swebv499_agentosv2_262k-150_think_t1 agentos_v2 150 8225 1.0 true` — Qwen3.5-9B think on,
  150 turns, 262k, condenser 없음, T=1.0 / top_p 0.95, instruction **suffix**, git history 숨기지 않음, 동시 8, 1회.
  다른 workflow의 swebv499 실행과 같은 조건. 결과: `rllm-home/eval_results/swebv499_agentosv2_262k-150_think_t1/`.
- 집계 스크립트: `scratchpad/agentos-smoke/agg.py` (episode tool call + `workflow_outputs`).

| workflow (같은 설정) | 해결 | agentos_v2만 해결 / 상대만 해결 | McNemar p |
|---|---|---|---|
| none | 300/499 (60.1%) | 27 / 77 | 9.7e-07 |
| aidlc_v4 | 282/499 (56.5%) | 42 / 74 | 0.004 |
| speckit_bug | 278/499 (55.7%) | 38 / 66 | 0.008 |
| openspec_ff + explore | 276/499 (55.3%) | 44 / 70 | 0.019 |
| **agentos_v2** | **250/499 (50.1%)** | — | — |
| speckit_sdd | 245/499 (49.1%) | 54 / 49 | 0.69 |
| openspec_ff | 242/499 (48.5%) | 58 / 50 | 0.50 |

| 따름 지표 | 결과 |
|---|---|
| 진입 문서를 call 0–2에 읽음 / `/testbed/agent-os` 참조 | 499/499 / 0 |
| 명령 4개 모두 열기 / 순서대로 | 426 / 424 |
| initialization.md · requirements.md · spec.md · tasks.md · 보고서 | 498 · 471 · 435 · 469 · 431 |
| 보고서 절 번호 1·2·3 / roadmap `No Updates Needed` | 405 / 404 |
| `checks/` 스크립트 | 191 |
| spec 폴더 1개 | 498 (0개 1) |
| step 중앙값 / p90 / 150 도달 | 71 / 115 / 14 |

끝난 방식별 (전체 / 해결):
- 체인 완료 후 `finish` 429 / 242 (56.4%)
- `finish`했지만 보고서 없음 28 / 5
- 텍스트 응답으로 종료 27 / 2 — 이 중 26은 **형식이 깨진 tool call**(`<tool_call><file_editor><parameter=…>`, `<function=terminal=command>`)이 텍스트로 처리된 것. 같은 패턴의 종료: none 14/499, speckit_sdd 31, aidlc_v4 28 → workflow 공통으로 늘어나는 parser·모델 문제.
- 150 step 도달 14 / 1

none 대비 잃은 77건: 체인 완료 후 오답 45, 깨진 tool call 종료 19, 보고서 없이 finish 6, step 한도 6, 기타 1. 저장소별 django 36, sympy 13, sphinx 10, xarray 8, matplotlib 5.
