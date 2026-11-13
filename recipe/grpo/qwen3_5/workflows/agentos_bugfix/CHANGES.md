# agentos_bugfix — agentos_v2 대비 변경 내역

- 만든 이유: agentos_v2 문서를 줄 단위로 검토하던 중, 기능 기획용 단계가 버그 수정 과제와 무관하다는 판단
  (`tasks/2026-11-13-agentos-v2-resolve-review/`, 사용자 결정 2026-11-13).
- 방침: agentos_v2는 그대로 두고, 버그 수정에 필요 없는 단계만 뺀 워크플로우를 따로 둠. 뺀 것과 문구
  일반화 외에는 agentos_v2와 같음 (같은 upstream v2.1.1, 같은 편집, 같은 렌더 방식).
- 문서 분량: 명령 문서 4개 1,329줄 → 611줄, 진입 문서 93줄 → 91줄.

## 뺀 것

| # | 대상 | 위치 (agentos_v2 문서 기준) | 이유 |
|---|---|---|---|
| B1 | 제품 맥락 조사 | shape-spec PHASE 2 Step 2 (README, 문서 목차, 패키징 정보 읽기)와 책임 목록의 해당 줄. 뒤 Step 번호를 당김 | 버그의 위치·원인과 무관한 읽기 |
| B2 | 시안 | `planning/visuals/` 폴더 생성, 필수 `ls`, 시안 분석, 시안 후속 질문, requirements.md의 Visual Assets 절, spec.md의 Visual Design 절, 시안을 참조하라는 줄 전부 | 시안은 항상 없음 |
| B3 | roadmap | implement-tasks PHASE 3의 roadmap 갱신 Step, 보고서의 Roadmap Updates 절. 뒤 Step·절 번호를 당김 | roadmap이 없어 항상 "갱신 없음"만 적음 |
| B4 | standards 8개 | backend 4개(api, migrations, models, queries), frontend 4개(accessibility, components, css, responsive) | 웹 UI·REST·DB 기준 |
| B5 | 사용자 스토리 | spec.md의 User Stories 절 | 기능 기획용 칸 |
| B6 | `implementation/` 폴더 | shape-spec PHASE 1 Step 3 (verifications/ 폴더만 만듦) | 아무도 쓰지 않는 폴더 |
| B7 | 웹앱 tasks 예시 | create-tasks의 DB·API·UI group 예시 → 같은 뼈대의 group 1개 + 테스트 검토 group | 예시의 내용이 웹앱 전용. 뼈대(테스트 2–8개 작성 → 변경 → 그 테스트만 실행)는 유지 |
| B8 | 후속 질문 | shape-spec PHASE 2의 후속 질문 Step, requirements.md의 Follow-up Questions 절, "후속 질문은 1–3개" 제약 | 답할 사람이 없어 되물을 일이 없음. 실제로 후속 질문을 쓴 런은 평가 4–7%, 학습 5–8% (`tasks/2026-11-13-agentos-v2-resolve-review/analysis/q2_q4_q5.csv`) |
| B9 | shape-spec·write-spec·create-tasks의 standards | 세 문서 끝의 "User Standards & Preferences Compliance" 블록(문서마다 54–66줄). implement-tasks에는 그대로 둠 | 코딩 기준이라 코드를 쓰는 단계에서만 쓰임. 파일로 따로 배포하지 않음("필요하면 읽어라"는 모델 판단에 맡기는 지시라 넣지 않음) |

## 바꾼 것

| # | 대상 | agentos_v2 | agentos_bugfix | 이유 |
|---|---|---|---|---|
| T1 | 테스트 실행 범위 | 구현 중(implement-tasks PHASE 2, create-tasks 예시·제약): "자기가 쓴 테스트만 실행". 최종 검증(PHASE 3): "전체 테스트를 실행" | 두 곳 모두 "자기가 쓴 테스트 + 수정한 코드의 기존 테스트". 전체 테스트는 몇 분 안에 끝날 때만 추가로. 구현 중 문장에 "task가 바꾸라고 한 동작을 기대하는 기존 테스트는 실패하는 것이 맞으니 수정을 그대로 두고 그 테스트를 최종 보고서에 적는다"를 덧붙임. "이 단계에서 전체 테스트를 돌리지 말 것"은 그대로 | 구현 중에는 기존 테스트가 안 돌고, 마지막의 전체 테스트는 거의 지켜지지 않음. 평가(wf-floor-tcx): 정답 test patch가 건드리는 파일을 실행한 런 73.8% → 58.9%, 편집 뒤 테스트 횟수 7.2 → 4.5, 전체 테스트를 돌린 런 6.8%(34런 중 시간 초과 12) |
| T2 | 테스트 작성 기준 | implement-tasks의 test-writing standard 7줄 | "개발 중 테스트는 최소로", "핵심 사용자 흐름만 테스트", "edge case 테스트는 미룸" 세 줄을 뺌. 나머지 4줄(동작을 테스트, 이름, mock, 속도)은 그대로 | 버그 수정은 특정 입력의 예외 동작이 대상인 경우가 많고, 그것을 재현하는 테스트가 곧 edge case 테스트임. 따로 잰 수치는 없음. create-tasks 예시의 "Skip exhaustive coverage of all methods and edge cases" 등 같은 취지의 4줄은 손대지 않음 |
| T3 | 구현 중에 찾은 작업 | 명령이 끝난 파일은 고치지 않음. tasks.md는 체크박스만 예외. "배정된 task만 구현" | 구현 중에 task에 없는 필요한 작업(고칠 다른 파일, 빠진 경우)을 찾으면 tasks.md에 먼저 추가한 뒤 배정된 task로 구현함. 줄 추가만 허용하고 있던 task는 고치거나 지우지 않음. spec.md·requirements.md는 그대로 고치지 않음 | 계획에 적힌 것이 곧 고쳐지는 범위임(평가 wf-floor-tcx: 계획이 정답 파일을 모두 담은 런은 정답 파일을 모두 고친 비율 89.5%, 다 담지 못한 런은 24.1%). 새로 찾은 작업을 정식으로 구현할 길을 둠. 모델이 이 길을 쓸지는 확인되지 않음 |
| T4 | 보고서의 전체 Status | 머리의 Status 칸에 세 값(Passed / Passed with Issues / Failed)만 있고 언제 무엇을 적는지 기준이 없음 | 보고서 양식 뒤에 기준을 적음: 두 절의 Status에서 정해짐. All Complete + All Passing이면 Passed, ⚠️로 표시한 task가 있거나 이 변경을 위해 쓴 것이 아닌 테스트가 실패하면(Some Failures) Passed with Issues, 이 변경을 위해 쓴 테스트가 실패하면(Critical Failures) Failed | 평가(wf-floor-tcx)에서 보고서의 96.2%가 Passed이고, 그중 61런은 마지막 검증이 실패, 42런은 같은 보고서의 Failing 칸이 1 이상. 해결률보다 보고서 정확도의 문제 |

## 문구 일반화 (G)

데이터셋 한 가지 경우에 맞춰져 있던 문구를 바꿈 (해결률 영향과 별개, `agentos_v2/porting/later.md`).

| 바꾸기 전 | 바꾼 뒤 | 위치 |
|---|---|---|
| the issue in `<issue_description>` | the task description in the task message | shape-spec PHASE 1, core-workflow |
| the issue (입력을 가리킬 때) | the task description / the task | shape-spec PHASE 2, core-workflow, system prompt |
| The issue is your only input from outside | The task message is your only input from outside | core-workflow |
| the repository at `/testbed`, `/testbed` | the repository (you work in) | instruction, system prompt, core-workflow |

## 그대로 둔 것

- 확인 질문 4–8개와 자체 답변, 재사용 코드 검색, 최종 검증의 전체 테스트 실행과 "실패를 고치지 말 것",
  "끝난 산출물은 고치지 않음": 검토에서 판정이 아직 안 났거나 따로 판단하기로 한 항목.
- 테스트 규칙(검사 스크립트 또는 기존 테스트 모듈에 함수 추가, 기존 테스트 줄 변경 금지): 숨겨진
  테스트로 채점하는 과제를 전제한 문구지만, 워크플로우 규칙인지 데이터셋 조건인지 정해지지 않아 일반화하지 않음.
- 남긴 standards 6개(global 5개, testing 1개)와 그 안의 웹 관련 줄(예: 서버·클라이언트 검증).
- 질문 양식의 "UI components", "page layouts" 같은 upstream 문구.

## 채점기 (1차, 2026-11-13)

- `derive_rubric.py`가 agentos_v2의 `reward/rubric.yaml`에서 만듦. 모델 호출 없음. agentos_v2 채점기나 이 워크플로우 문서가
  바뀌면 다시 돌림 (`--check`로 낡았는지 확인).
- 항목 207개 → 160개. 지운 47개 = 뺀 단계의 항목 19개(제품 맥락 읽기 4, 시안 5, roadmap 3, 사용자 스토리 4,
  `implementation/` 폴더와 빈 폴더 규칙 2, 후속 질문 1) + T1로 문서에서 없어진 요구 1개("PHASE 3에서 전체 테스트를 돌렸는가")
  + 검사 없이 문장만 기록하던 항목 중 그 문장이 문서에서 빠진 27개(standards 문장이 많음).
- 고친 설정값: requirements.md·spec.md의 허용 절 목록, 양식 자리표시 목록(빠진 것 40개 제거, 새 tasks 예시의 자리표시 9개 추가),
  보고서의 테스트 결과 절 이름(`3.` → `2.`).
- 나머지 항목은 검사 내용 그대로. 출처의 줄 번호와 인용문만 이 워크플로우 문서에 맞춤 (인용문 40개는 바뀐 문구로 다시 찾음,
  찾지 못한 출처 51개는 지움, 출처가 하나도 안 남은 항목은 없음).
- 전용 검사는 agentos_v2의 함수를 `agentos_bugfix.*` 이름으로 등록해 씀 (`reward/checks.py`). 이를 위해 agentos_v2의 보고서
  검사에 테스트 결과 절 이름을 받는 선택 설정값(`suite_section`)을 추가함 (agentos_v2 동작은 그대로).
- 기준 런(`selftest_golden.py`, agentos_v2 것에서 뺀 단계만 제거): 만점 1.0, 정직한 변형 6개도 0.99 이상.
- 알려진 미달 2건 (기준은 바꾸지 않음):
  - "정직한 런의 서식을 바꾼 변형"이 0.9789로 기준 0.98에 0.0011 모자람 (agentos_v2는 0.9833). 같은 항목(requirements.md의
    In Scope 칸)에서 잃는 것은 agentos_v2와 같고, 항목 수가 줄어 한 항목의 비중이 커진 결과.
  - "편집 뒤 모든 테스트 실행을 전체 테스트로 바꾼 변형"이 0.9969로 기준 0.995 이하에 못 미침(감점이 0.0031). T1로 기준 런이
    구현 중에 기존 테스트를 돌리게 되면서 이 변형이 처음 적용됨. 걸리는 항목은 "구현 중에는 전체 테스트를 돌리지 않음"인데
    agentos_v2에서 권고(should, 가중치 0.25)로 되어 있어 감점이 작음. 필수(must)로 올리면 기준을 넘음: 사용자 결정 필요.
- T3에 따라 "tasks.md는 create-tasks 뒤에 체크만 한다" 항목이 줄 추가도 허용함(있던 줄을 고치거나 지우면 감점 그대로). 이를 위해
  agentos_v2의 tasks 검사에 선택 설정값(`additions`)을 추가함(agentos_v2 동작은 그대로). create-tasks 단계의 tasks.md 항목 3개
  (task 수, group 구성, 테스트 먼저)는 create-tasks가 끝난 시점의 tasks.md를 보도록 바꿈. 기준 런에 "구현 중에 task를 추가하는"
  정직한 변형을 넣었고 만점. 같은 런이 agentos_v2의 규칙으로는 0.9977.
- T4에 따라 항목 1개를 새로 넣음: 머리 Status가 두 절의 Status에서 정해지는 값과 같은가(필수). agentos_v2의 보고서 검사에 규칙
  `overall_status`를 추가해 구현함(agentos_v2 채점기는 이 규칙을 쓰지 않음). "Passed with Issues"나 "Failed"를 적는 것 자체는
  감점하지 않고, 적은 값이 절들과 맞는지만 봄. 항목 수 161개.
- T1의 새 요구("수정한 코드의 기존 테스트를 돌렸는가")를 직접 보는 항목은 아직 없음. 검사 코드를 새로 써야 함.
- 없는 것: `rubric.md`(사람이 읽는 항목 표), 실제 런으로의 확인.

## 아직 없는 것

- 평가 결과: 아직 한 번도 돌리지 않음. 채점기도 기준 런으로만 확인했고 실제 런에 적용해 보지 않음.

## 확인

- `python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream <v2.1.1 worktree> --check`
- `pytest recipe/grpo/qwen3_5/tests/test_agentos_bugfix.py` (뺀 단계의 단어가 문서에 남지 않았는지, Step·절
  번호, 남긴 standards 목록, 문서 5개 업로드, 채점기가 derive 결과와 같은지, 기준 런 점수)
