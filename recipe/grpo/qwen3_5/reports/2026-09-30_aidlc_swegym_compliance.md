# AI-DLC × SWE-Gym × Qwen3.5-9B GRPO — run 2 컴플라이언스 분석 (compliance 미보상 arm)

- 실행: 2026-09-29 08:47 ~ 09-30 01:23, AWS 8× H200, run id `20260929_084716`, variant `openhands_9b_aidlc_swegym` (agent_step_limit 100, hide_git_history on, no-think)
- 21/27 step 완료 시점에 중단(step 22 rollout 도중 vLLM 500/ReadError, 직후 01:25에 `openhands_9b_aidlc_swegym_reward` 시작)
- 에피소드 로그: `/opt/dlami/nvme/work/artifacts/episodes/qwen3_5-swe-grpo/qwen3_5-9b-openhands-sdk-aidlc-swegym293/20260929_084716/episodes/` (train 21 step × 128 + val 7회 × 23 = 2,849 episode)
- 분석 스크립트/중간 결과: `outputs/aidlc_compliance_audit/` (`extract.py` → `facts_*.jsonl`, `agg.py`). 궤적에서 rubric(`aidlc_reward.rubric`)을 재실행해 실패 원인을 복원했고, 로그된 `aidlc/compliance`와 99.9%가 0.01 이내로 일치한다.

## 1. 요약

| | 값 |
| --- | --- |
| aidlc/compliance 평균 (train 전체) | **0.020**; episode의 90.7%가 정확히 0 |
| val compliance | 7회 중 6회 0.000 (step 12만 0.061) |
| core-workflow.md를 읽은 episode | 393 / 2,849 (**13.8%**) |
| 5개 stage 문서를 모두 읽은 episode | 34 (1.2%) — 이들의 compliance 평균은 **0.85** |
| stage artifact를 1개 이상 쓴 episode | 97 (3.4%) |
| train reward (verifier) | 0.35 → 0.85~0.95, val pass@1 0.22 → 0.43 (run 1과 같은 궤적) |

compliance는 이 run의 reward에 들어가지 않았으므로 21 step 동안 개선되지 않은 것은 예상대로다(0.018 → 0.016). 문제는 **출발점이 0에 가깝다**는 것이고, 원인은 rubric의 세부 항목이 아니라 그 앞 단계에 있다.

## 2. 실패 지점 — 깔때기

```
2,849 episode
 ├─ 2,456 (86.2%)  /ai-dlc/core-workflow.md를 열지 않음            → 6개 신호 전부 0
 └─   393 (13.8%)  core 읽음
      ├─ 143       core만 읽고 stage 문서 없음                    → order 0, s1~s5 0
      ├─ 190       core + 01만 읽음 (대부분 artifact 0개)          → compliance 0.011 (prefix 1)
      └─  60       stage 문서 2개 이상
           └─ 34   5개 전부 → compliance 0.85, artifact 4~5개
```

### 2.1 (지배적) 워크플로우 진입 실패 — 86%

시스템 프롬프트 `<PROBLEM_SOLVING_WORKFLOW>`와 user 메시지 말미 4줄이 모두 `/ai-dlc/core-workflow.md`를 먼저 읽으라고 지시하지만, 모델은 첫 turn에 "Let's start by exploring the repository structure"로 시작해 SkyRL SWE-Gym instruction의 6단계 절차(EXPLORATION → ANALYSIS → TEST CREATION → IMPLEMENTATION → VERIFICATION → FINAL REVIEW)를 따른다. 그 절차는 issue 바로 아래 ~1,400 토큰 분량으로 구체적이고, AI-DLC 지시는 그 뒤에 4줄로 붙어 있다. 스모크 2회(각 12 episode)와 오늘 reward run의 step 0 val(23 episode)도 docs_read 0.04~0.08로 동일해서, 학습 이전 base model의 성향이다.

- 읽은 393 episode 중 core를 turn 1에 읽은 것은 3개뿐, 대부분 turn 2~4(`find /ai-dlc -name core-workflow.md` 후 view).
- core를 읽은 episode는 task가 몰려 있지 않고(316 task 중 189 task에 분산) 정답률도 비슷하다(0.84 vs 0.79). 특정 task의 문제가 아니라 샘플링 확률의 문제다.

### 2.2 (2차) 워크플로우 이탈 — core를 읽은 뒤 5 turn 안에 버림

core를 읽은 393개 중 296개(75%)는 artifact를 하나도 쓰지 않았다. 전형적 궤적(`Project-MONAI__MONAI-4745`, `getmoto__moto-5582`):

```
t2  find /ai-dlc -name core-workflow.md
t4  view /ai-dlc/core-workflow.md
t5  "Now let's read the Stage 1 rule detail file" → view 01-reverse-engineering.md
t6  "Now let's explore the issue" → view /testbed/...        ← 여기서부터 SWE-Gym 절차로 복귀
...
t87 finish   (artifact 0개, /tmp/swe-bench-pro 미생성)
```

01을 읽고 Stage 1의 실제 작업(scope 파악)을 시작하면 그 뒤 60~90 turn 동안 "artifact를 써야 한다"가 다시 등장하지 않는다. baseline을 소스 수정 전에 기록한 episode는 163개(6%)뿐이고 2,414개는 수정 후에 테스트를 처음 돌렸다(SWE-Gym 절차의 순서).

### 2.3 (3차) artifact를 썼지만 해당 stage 문서를 읽지 않음 → band 2

stage별로 "그 stage의 rule detail을 읽었는가"가 band를 거의 완전히 갈라놓는다:

| stage | 문서 읽고 작성 → band 8 / 5 / 2 | 문서 안 읽고 작성 → band 8 / 5 / 2 | 안 읽었을 때 모델이 쓴 heading |
| --- | --- | --- | --- |
| S1 | 69 / 7 / 1 | 0 / 0 / 16 | `## Existing Tests + Baseline`, `## Issue Analysis` |
| S2 | 56 / 0 / 0 | 0 / 6 / 27 | `## Requirements` 아래 `###`로 3분류 (rubric은 `##`만 인식) |
| S3 | 48 / 1 / 0 | 0 / 0 / 41 | `## Implementation Plan`, `## Contracts to Preserve` (`### Step n` 블록 없음) |
| S4 | 7 / **24** / 0 | 0 / 0 / 36 | `## Modified Files`, `## Created Files`, `## Deviations` |
| S5 | 35 / 1 / 0 | 0 / 0 / 48 | `## Build Result`, `## Reproduction Result`, `## Regression Verdict`, `## Summary` |

- 문서를 읽지 않고 쓴 경우 모델은 **core-workflow.md의 Stage Flow 요약 문구**("build result, reproduction result, regression verdict, outstanding failures")를 그대로 heading으로 만든다. 내용은 있지만 strict skeleton에 걸려 band 2. 이것이 stage 4·5 writer의 절반 이상(36/67, 48/84)이다. 5개 문서를 다 읽으라는 규칙을 "01만 읽고 나머지는 core 요약으로 대체"하는 형태로 어기는 것이다.
- 문서를 읽고 쓴 경우는 S2·S3·S5가 거의 전부 band 8. 유일한 체계적 손실은 **S4의 `- Created:`** (31개 중 24개 band 5): 생성 파일이 없을 때 모델이 그 줄을 생략한다. rubric은 `- Created: none`을 허용하지만(`allow_none`) 04 skeleton에 `none` 선택지가 표기되어 있지 않다. 문서와 rubric의 불일치이며 s4 만점 비율이 0.2%에 그친 직접 원인이다.
- S1에서 `baseline` 누락 7건은 문서를 읽었는데도 `- Passing:`/`- Failing:` 대신 산문으로 적은 경우.
- frontmatter는 작성된 모든 artifact에서 유효했고(383/383), 코드펜스로 감싼 경우와 파싱 불가 shell write는 각 stage 1~2건이라 측정 갭은 무시할 수준이다.

### 2.4 order 신호

order 평균 0.020, 91%가 0. 문서를 읽지 않으니 사슬(r1<w1<r2<…)이 성립할 수 없다. 5개를 다 읽은 34개에서는 order 평균 0.85로, 순서 자체(읽기 → 쓰기 → 다음 읽기)는 모델이 지킬 수 있다. 여러 stage 문서를 한 명령으로 몰아서 읽는 경우(invalid multi-read)는 0건. 실제 테스트 미실행으로 s1/s5가 capped된 writer도 2건뿐이다.

## 3. 현재 돌아가는 reward run(`…_reward`, mode=mul)에 대한 함의

run 2 데이터로 4-rollout 그룹(672개)에 reward식을 적용해 보면:

| reward | 그룹 전체 0 | 그룹 내 분산 0 (advantage 0) | 평균 reward |
| --- | --- | --- | --- |
| verifier만 (run 1·2) | 4.5% | 52.4% | 0.751 |
| **mul: verifier × compliance** | **73.7%** | **73.7%** | 0.018 |
| add: verifier + 0.2 × compliance | 3.4% | 37.5% | 0.755 |

mul에서는 그룹의 74%가 학습 신호를 전혀 만들지 못하고, 남은 신호의 대부분은 0.011(core+01만 읽음)이다. 한 그룹 안에서 compliance>0인 rollout이 나올 확률이 낮아 GRPO가 "문서를 읽는 행동"을 강화할 기회가 step당 30그룹 정도에 그치고, 그마저 정답이어야 한다. 더 나쁜 것은 정답이지만 workflow를 안 따른 rollout(전체의 77%)이 오답과 똑같이 0을 받아 coding 신호가 사라진다는 점이다. 오늘 reward run의 step 0 val에서 compliance는 23개 모두 0이었다.

## 4. 제안 (우선순위순)

1. **진입 확률을 올리는 프롬프트 수정** — SWE-Gym 6단계 절차와 AI-DLC 지시가 충돌한다. instruction에서 6단계 절차를 제거하거나 AI-DLC 4줄을 issue 직후·절차 앞으로 옮기고, 첫 turn의 행동을 명시("첫 tool call은 `view /ai-dlc/core-workflow.md`"). 이것만으로 13.8% → 대폭 상승이 기대되며, 이 arm의 base rate가 0에 가까운 상태에서 어떤 reward 설계도 작동하지 않는다.
2. **reward 결합은 add(lam 0.2~0.5)로 시작**하고, compliance>0 비율이 30~50%로 올라온 뒤 mul을 검토. 또는 mul을 쓰되 compliance에 floor(예: 0.2 + 0.8·c)를 둔다.
3. **04 skeleton에 `- Created: none` 표기 추가**(rubric은 이미 허용). s4 만점 비율이 즉시 회복된다.
4. (선택) 이탈 대책: core-workflow.md에 각 stage의 첫 tool call과 마지막 tool call(artifact 쓰기)을 한 줄 체크리스트로 재기술. 현재는 01을 읽은 뒤 60+ turn 동안 artifact 언급이 컨텍스트에 없다.

## 5. 첫 turn 진입 프로브 (base model, 2026-09-30)

`scripts/aidlc_entry_probe.py`로 base Qwen3.5-9B(vLLM 0.22.1, no-think, T=1.0, top_p 0.95)에 run 2와 같은 system prompt·tool schema로 첫 turn만 샘플링했다. train 20 task × 8 sample = 배치당 160회. `entry` = 첫 tool call이 `/ai-dlc/core-workflow.md`를 읽음, `touch` = `/ai-dlc` 디렉터리를 view(다음 turn에 읽는 전형적 패턴), `repo_search` = repo 안에서 workflow 파일을 find/grep, `repo` = 바로 코드 탐색, `meta` = `think` 호출만.

| 배치 | entry | touch | entry+touch | repo_search | repo | meta |
| --- | --- | --- | --- | --- | --- | --- |
| skyrl+suffix (run 2 그대로) | 1.2% | 0.6% | **1.9%** | 4.4% | 58.8% | 35.0% |
| skyrl+prefix (순서만 변경) | 6.9% | 5.0% | 11.9% | 14.4% | 29.4% | 44.4% |
| aidlc+suffix (6단계만 제거) | 26.9% | 19.4% | 46.2% | 13.8% | 20.0% | 20.0% |
| **aidlc+prefix (둘 다)** | 26.2% | 45.0% | **71.2%** | 6.9% | 7.5% | 14.4% |
| skyrl+none (user 메시지에 지시 없음) | 0.0% | 0.0% | 0.0% | 0.6% | 70.0% | 29.4% |

- run 2 배치의 첫 turn 진입 1.9%는 실제 run 2의 turn-1 진입(9/2,849 = 0.3%)과 같은 수준이다.
- 두 변경은 독립적으로 기여한다: 6단계 제거가 크고(1.9 → 46.2%), 순서 변경은 그 위에서 추가로 작동한다(46.2 → 71.2%). 순서 변경만으로는 11.9%에 그친다.
- 20 task 전부에서 aidlc+prefix가 skyrl+suffix보다 높았다(task별 38~100%).
- 남은 실패의 대부분은 `think`만 호출한 turn(14%)과 여전히 `/testbed` 안에서 `core-workflow.md`를 찾는 경우(7%)다. 후자는 instruction.md에 "repo 밖 절대경로" 문구를 넣은 뒤에도 남아 있다.
- 첫 turn만 보는 프록시다. run 2에서 진입 후 이탈(core 읽은 393개 중 75%가 artifact 0개)은 이 프로브가 측정하지 않으므로, 다음 run의 `aidlc/docs_read`·`artifacts_written`으로 확인해야 한다.
- 원자료: `outputs/aidlc_compliance_audit/probe_base_qwen3.5-9b.jsonl`. 1차 실행(`*_run1_tmpcwd.jsonl`)은 tool schema fixture에 덤프 당시 임시 cwd가 남아 있어 폐기했고, 수치는 위와 비슷했다(aidlc+prefix 75.0%).

## 6. 40-turn 전체 rollout 비교 (base model, run 2 step 1의 32 task × 4)

`rllm eval swegym293_aidlc --agent eval_harness:SwegymAidlcEval --agent-kwargs step_limit=40` (prefix, 6단계 제거, hide_git_history, T=1.0/top_p 0.95, no-think), 정책은 base Qwen3.5-9B(외부 vLLM). 비교 대상은 run 2 train step 1의 실제 rollout 128개를 40 turn 시점에서 자른 값(같은 32 task, 같은 base model, skyrl+suffix).

| | run 2 step 1 (skyrl+suffix, t≤40) | 새 배치 (aidlc+prefix, 40 turn) |
| --- | --- | --- |
| core-workflow.md 읽음 | 13.3% | **90.6%** |
| 01 rule 읽음 | 7.8% | 90.6% |
| 02 / 03 rule 읽음 | 1.6% / 1.6% | 39.1% / 35.2% |
| artifact 1 / 2 / 3 작성 | 1.6% / 1.6% / 1.6% | **45.3%** / 43.0% / 39.8% |
| artifact 1 작성 \| 01 읽음 | 10.0% | 50.0% |
| 02 읽음 \| artifact 1 작성 | 50.0% | 81.0% |
| core 첫 읽기 turn (중앙값) | 5 | 2 |
| 테스트 실행 (≤40) | 36.7% | 65.6% |
| verifier 정답 (40 turn) | – (100 turn: 0.35) | 0.43 |
| compliance 평균 (rubric 재계산) | – | 0.247 (order 0.28, s1 0.42, s2 0.38, s3 0.34, s4 0.05, s5 0.02) |

- 진입은 해결됐다: 116/128이 core를 읽고 그 직후(t2 중앙값) 01을 읽는다. 32 task 전부에서 4개 중 최소 1개는 진입했다. 진입 못 한 12개는 여전히 "Let's start by exploring the repository"로 시작해 문서를 한 번도 찾지 않았다(정답률은 8/12로 오히려 높다).
- 남은 병목은 여전히 **Stage 1 → artifact 1**: 01을 읽은 116개 중 58개만 40 turn 안에 artifact 1을 썼다. 쓴 경우 작성 turn 중앙값은 23(01 읽기 후 20 turn), 8개는 t35 이후라 40 turn 상한에 걸린 것도 있다. 못 쓴 58개 중 27개는 소스 수정을 먼저 시작했고(수정 시작 중앙값 t27), 22개는 탐색만 하다 끝났다. 즉 "탐색 → 수정"의 SWE-Gym 습관이 Stage 1 안에서 재발한다.
- artifact가 일단 쓰이면 품질은 좋다: S1 band 8이 54/58, S2 44/55, S3 40/51. run 2에서 보였던 heading 오기재(band 2)는 rule 문서를 읽지 않고 쓴 경우에만 남아 있다(S3 11개).
- 40 turn이라 S4·S5는 거의 도달하지 못했다(artifact 4~5는 각 4개 미만). 100 turn 결과는 다음 학습 run의 step 1 `aidlc/*` 지표로 확인한다.
- 정답률: artifact 1까지 쓴 58개 0.48, core는 읽었으나 못 쓴 58개 0.33, 진입 안 한 12개 0.67. 표본이 작아 방향만 참고.
- 원자료: `outputs/aidlc_compliance_audit/eval_step1_aidlc_prefix_40t/` (episodes/, facts.jsonl, results.json), 비교 스크립트 `compare_step1.py`.
