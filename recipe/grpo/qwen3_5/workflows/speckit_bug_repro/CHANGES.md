# speckit_bug_repro — speckit_bug 대비 변경 내역

- 기준: **speckit_bug** 그대로. 문서 하나(`docs/stages/01-assess.md`)만 고침.
  instruction, system prompt, container 경로(`/speckit`), 보고서 경로, 채점기는 speckit_bug 의 `SPEC` 을 그대로 씀
- 목적: "계획(assessment)을 쓰기 전에 재현을 실행하면 resolve 가 오르는가"를 확인하는 실험용 변형
- 원본 speckit_bug 는 건드리지 않음

## 변경표

| # | 위치 | speckit_bug | speckit_bug_repro |
|---|---|---|---|
| 1 | 01-assess Execution 2 | **Summarize the symptom**: 증상을 한두 문장으로 서술, 재현 절차는 "발견 가능하면 나열" | **Reproduce the symptom**: issue 의 예시(없으면 가장 짧은 호출)를 수정 전 코드에 `python -c` 같은 짧은 명령으로 실행하고, 명령과 출력을 남김. 실행할 수 없으면 이유를 적음 |
| 2 | 01-assess Execution 4 (Verdict) | Valid = "reproducible or clearly grounded" / Likely valid = "plausible but unverified" | Valid = 2번 실행에서 증상이 나왔거나 코드로 명확함 / Likely valid = 2번을 실행할 수 없었거나 증상이 안 나옴. enum 값은 그대로 |
| 3 | 01-assess Execution 5 | — | 첫 항목 추가: root cause 와 remediation 은 issue 문장만이 아니라 2번에서 관찰한 출력을 설명해야 함 |
| 4 | 01-assess 보고서 `## Reproduction` | `1. <step>` 3줄 | `1. <실행한 명령>` `2. <출력 또는 오류>`. 번호 목록 형식과 heading 은 그대로 |
| 5 | 01-assess Guardrails | — | "2번을 실행했거나 실행 불가로 기록하기 전에는 remediation 을 제안하지 않는다" 추가 |

바꾸지 않은 것

- check script 작성·실행과 baseline 테스트는 그대로 fix 단계(02-fix Execution 2). 2번은 일회성 명령이라고 문서에 명시
- "fix 단계만 repository 를 편집한다" (core-workflow) 와 round 구조
- 보고서의 heading 과 `- **Field**:` 줄 → speckit_bug rubric 의 항목이 그대로 적용됨

## 근거 (SWE-bench Verified 485 instance × 3, 2026-11-26 분석)

- workflow 가 틀리고 nowf 가 맞힌 instance 의 실패 episode 74건 판독: 82% 는 계획에 이미 정답과 다른 수정이 적혀 있었고
  patch 가 그것을 따름. 계획이 정답과 같은 수정이었던 것은 11% (resolve 된 대조 36건은 69%)
- ft speckit 은 계획을 step 19 (중앙값) 에 쓰고 그 전 실행이 2.7회. ft nowf 는 첫 편집(step 26) 전 실행이 5.7회.
  계획 전에 재현을 실행한 episode 는 51%
- 같은 instance 안에서 계획 전 재현 실행 여부에 따른 resolve 차이: ft speckit +6.0pp (−0.9, +13.1),
  ft speckit + ft aidlc 합산 +5.7pp (+1.3, +10.0). 계획이 gold 함수를 지목하는 비율 +4.3pp (+1.1, +7.5)
- 차이는 `python -c` 로 직접 돌려 본 쪽에서 나옴 (+3.7pp). 계획 전에 스크립트를 작성해 돌린 경우는 −0.2pp
  → check script 를 assess 로 옮기지 않고 "짧은 명령으로 실행"만 추가함
- 편집 stage 제한은 근거가 없어 그대로 둠 (검증 stage 편집 −1.9pp (−8.0, +4.0), 편집→실행 반복 횟수는 nowf 와 동일)

## 읽을 때 주의

- 근거는 관찰 자료임. 재현부터 하는 시도가 원래 더 신중했을 가능성은 이 변형의 eval 로만 가려짐
- 채점기는 speckit_bug 것이라 `speckit_bug/*` signal 이 그대로 나옴. 새 지시(계획 전 실행)를 재는 항목은 없으므로
  준수 여부는 trajectory 에서 직접 세어야 함 (assessment.md 작성 step 이전의 실행 횟수)
- 학습에 쓰려면 reward 에 assess 단계 실행 항목이 필요함. 지금은 eval 용
- `docs/stages/` 는 speckit_bug 것을 손으로 고친 것이고 `speckit_bug/build.py` 의 관리 대상이 아님.
  원본 문서가 바뀌면 `tests/test_repro_variants.py` 가 실패하므로 그때 같이 옮길 것
