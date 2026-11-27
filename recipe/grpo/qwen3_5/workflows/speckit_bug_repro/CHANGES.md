# speckit_bug_repro — speckit_bug 대비 변경 내역

- 기준: **speckit_bug** 그대로. 문서 하나(`docs/stages/01-assess.md`)만 고침.
  instruction, system prompt, container 경로(`/speckit`), 보고서 경로, 채점기는 speckit_bug 의 `SPEC` 을 그대로 씀
- 목적: "계획(assessment)을 쓰기 전에 재현을 실행하면 resolve 가 오르는가"를 확인하는 실험용 변형
- 원본 speckit_bug 는 건드리지 않음 (rubric.yaml 포함)
- 2026-11-27 추가: 채점기를 따로 둠(`reward/`). speckit_bug rubric 에 penalty 항목 하나를 더한 것 (아래 "penalty 항목")

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
- signal 이름은 speckit_bug 것 그대로(`speckit_bug/*`). 새 지시(계획 전 실행)는 아래 penalty 항목이 잼
- `docs/stages/` 는 speckit_bug 것을 손으로 고친 것이고 `speckit_bug/build.py` 의 관리 대상이 아님.
  원본 문서가 바뀌면 `tests/test_repro_variants.py` 가 실패하므로 그때 같이 옮길 것

## penalty 항목 (2026-11-27)

`speckit_bug.assess.penalty.reproduction.before_remediation` — `reward/items.yaml`, 판정은 `reward/checks.py`.
`speckit_bug/penalty` 는 항목 평균이므로 이 변형에서는 4개 항목이 각각 0.25 (원본 speckit_bug 는 3개 그대로).

- 계획 시점: `assessment.md` 의 쓰기 중 `## Proposed Remediation` 에 내용이 들어간 첫 쓰기. 그런 쓰기가 없으면 첫 쓰기
- 그 step 보다 앞에서 아래 중 하나가 있으면 1, 없으면 0. `assessment.md` 를 쓰지 않은 run 은 0
  1. 유효 테스트 실행 (`evidence.runs_from` 의 valid, 기존 penalty 와 같은 규칙. 무엇을 골랐는지, 통과했는지는 안 봄)
  2. run 이 만든 파일 실행 (`python repro.py`, 직접 쓴 테스트 파일에 대한 pytest 등). python 파일이면 3번의 조건을 같이 봄
  3. 저장소 패키지를 import 하고 import·조회 외의 문장이 있는 inline python (`python -c`, heredoc)
  4. 저장소 자체의 명령행 (`python -m <패키지>`, `<패키지> ...`, `<패키지>-build ...`; `--help`/`--version` 제외)
- 세지 않는 것: import 만 있는 코드, `__version__`/`inspect.getsource`/`help()`/`dir()` 조회, 파일 읽기·쓰기만 하는 python,
  저장소에 원래 있던 스크립트 실행, 유효하지 않은 러너 호출(0건 수집, import 실패 등)
- 저장소 패키지 이름: `speckit_bug/reward/gold_files.json` 의 경로에서 저장소별로 뽑음 (23개 저장소). 표에 없는 저장소는
  run 이 바꾼 경로의 최상위 디렉터리
- `issue_terms` (이슈 본문의 식별자가 실행 코드에 있어야 함) 는 구현돼 있으나 **꺼 둠**: 기존 speckit_bug 평가 1,455건에서
  이 조건으로 0 이 되는 것이 780건 중 9건이고, 읽어 본 것은 대부분 실제 재현이었음 (이슈가 `Min()`, `S(0.0)` 처럼 짧은
  이름만 적은 경우). 켜려면 `items.yaml` 의 `issue_terms: true`
- 한계: `python -c "import django; print(1)"` 처럼 저장소를 import 하고 아무 문장이나 있으면 통과함. 실행한 것이 이슈와
  관련 있는지, 증상을 봤는지는 보지 않음. `## Reproduction` 에 적은 명령과 실행한 명령이 같은지도 보지 않음
- 테스트: `tests/test_repro_penalty.py`
