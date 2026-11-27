# aidlc_v5_repro — aidlc_v5 대비 변경 내역

- 기준: **aidlc_v5** 그대로. 문서 세 개만 고침 (`docs/core-workflow.md`, `docs/rule-details/01-reverse-engineering.md`,
  `docs/rule-details/03-code-generation-planning.md`).
  instruction, system prompt, container 경로(`/ai-dlc`), 산출물 경로, 채점기는 aidlc_v5 의 `SPEC` 을 그대로 씀
- 목적: "계획(Stage 3)을 쓰기 전에 보고된 동작을 실행해 보면 resolve 가 오르는가"를 확인하는 실험용 변형
- 원본 aidlc_v5 는 건드리지 않음

## 변경표

| # | 위치 | aidlc_v5 | aidlc_v5_repro |
|---|---|---|---|
| 1 | 01 Step 2 (신규), 이후 Step 번호 +1 | 재현은 Stage 3 에서 계획, Stage 4 에서 스크립트 작성, Stage 5 (편집 후) 에 처음 실행 | **Step 2: Observe the Reported Behavior**: 과제 설명의 예시(없으면 가장 짧은 호출)를 수정 전 코드에 `python -c` 같은 짧은 명령으로 실행하고 명령과 출력을 기록. 실행할 수 없으면 이유를 기록 |
| 2 | 01 산출물 골격·완료 기준; Purpose | 4개 절 | `## Observed Behavior` 절 추가 (`- Command:`, `- Output:`). 기존 4개 절은 그대로 |
| 3 | 03 Prerequisites·Step 1 | — | **MANDATORY — plan from what was observed**: 각 변경은 과제 설명의 문장만이 아니라 Stage 1 의 Observed Behavior 를 설명해야 함 |
| 4 | core Stage Flow·Stage 1 2항/5항·Stage 2 Consumes·Stage 3 2항 | — | Stage 1 이 내는 것에 Observed Behavior 를 명시, Stage 3 계획이 그것을 설명하도록 한 줄 추가 |

바꾸지 않은 것

- 재현 **스크립트**는 그대로 Stage 3 계획 → Stage 4 작성 → Stage 5 실행. Step 2 는 일회성 명령이라고 문서에 명시
- "과제 설명이 authoritative" (02 Step 1): 과제 설명은 코드가 해야 할 일을, 관찰은 지금 하는 일을 말한다고 적어 충돌을 피함
- baseline 실행, 편집 가능 stage, 테스트 파일 규칙 등 나머지 전부

## 근거 (SWE-bench Verified 485 instance × 3, 2026-11-26 분석)

- workflow 가 틀리고 nowf 가 맞힌 instance 의 실패 episode 74건 판독: 82% 는 계획에 이미 정답과 다른 수정이 적혀 있었고
  patch 가 그것을 따름. 계획이 정답과 같은 수정이었던 것은 11% (resolve 된 대조 36건은 69%)
- aidlc_v5 는 계획 전 테스트 실행은 71~76% 지만 (Stage 1 baseline), 계획 전에 재현을 실행한 episode 는 ft 55%, base 68%.
  nowf 는 첫 편집 전에 73~76% 가 재현함
- 같은 instance 안에서 계획 전 재현 실행 여부에 따른 resolve 차이: ft aidlc +5.5pp (−0.1, +11.0),
  ft speckit + ft aidlc 합산 +5.7pp (+1.3, +10.0)
- **base 모델에서는 이 관계가 보이지 않음**: base aidlc −3.5pp (−11.3, +4.2). base 에서는 효과가 없을 수 있음
- 차이는 `python -c` 로 직접 돌려 본 쪽에서 나옴. 계획 전에 스크립트를 작성해 돌린 경우는 차이 없음
  → 재현 스크립트의 위치는 그대로 두고 "짧은 명령으로 실행"만 추가함
- 편집 stage 제한과 "Stage 4 실행 금지"는 근거가 없어 그대로 둠 (계획 전 편집 +2.1pp (−6.1, +10.6), Stage 4 실행 +0.1pp (−2.9, +3.3))

## 읽을 때 주의

- 근거는 관찰 자료임. 재현부터 하는 시도가 원래 더 신중했을 가능성은 이 변형의 eval 로만 가려짐
- 채점기는 aidlc_v5 것이라 `aidlc/*` signal 이 그대로 나옴. `## Observed Behavior` 는 Stage 1 골격이 모르는 절이라
  `unknown_sections` 에만 기록되고 점수에는 들어가지 않음 (감점도 없음). 새 Step 의 준수 여부는 trajectory 에서 직접 세어야 함
- 원본 문서가 바뀌면 `tests/test_repro_variants.py` 가 실패하므로 그때 같이 옮길 것
