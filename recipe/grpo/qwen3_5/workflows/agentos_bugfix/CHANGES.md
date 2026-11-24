# agentos_bugfix — agentos_v2 대비 변경 내역

- 만든 이유: agentos_v2 문서를 줄 단위로 검토하던 중, 기능 기획용 단계가 버그 수정 과제와 무관하다는 판단
  (`tasks/2026-11-13-agentos-v2-resolve-review/`, 사용자 결정 2026-11-13).
- 방침: agentos_v2는 그대로 두고, 버그 수정에 필요 없는 단계만 뺀 워크플로우를 따로 둠. 뺀 것과 문구
  일반화 외에는 agentos_v2와 같음 (같은 upstream v2.1.1, 같은 편집, 같은 렌더 방식).
- 문서 분량: 명령 문서 4개 1,329줄 → 620줄, 진입 문서 93줄 → 94줄.

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
| T1 | 테스트 실행 범위 | 구현 중(implement-tasks PHASE 2, create-tasks 예시·제약): "자기가 쓴 테스트만 실행". 최종 검증(PHASE 3): "전체 테스트를 실행" | 두 곳 모두 "자기가 쓴 테스트 + 수정한 코드의 기존 테스트". 전체 테스트는 몇 분 안에 끝날 때만 추가로. 구현 중 문장에 "task가 바꾸라고 한 동작을 기대하는 기존 테스트는 실패하는 것이 맞으니 수정을 그대로 두고 그 테스트를 최종 보고서에 적는다"를 덧붙임. (2026-11-21 A-3: "최종 보고서의 Failed Tests에 적고, 예상된 실패(과제가 바꾸라는 동작을 단언함)라고 밝힌다"로 바꿈. 그 실패를 penalty 항목에서 빼는 규칙이 보고서의 말을 읽기 때문) "이 단계에서 전체 테스트를 돌리지 말 것"은 그대로 | 구현 중에는 기존 테스트가 안 돌고, 마지막의 전체 테스트는 거의 지켜지지 않음. 평가(wf-floor-tcx): 정답 test patch가 건드리는 파일을 실행한 런 73.8% → 58.9%, 편집 뒤 테스트 횟수 7.2 → 4.5, 전체 테스트를 돌린 런 6.8%(34런 중 시간 초과 12) |
| T2 | 테스트 작성 기준 | implement-tasks의 test-writing standard 7줄 | "개발 중 테스트는 최소로", "핵심 사용자 흐름만 테스트", "edge case 테스트는 미룸" 세 줄을 뺌. 나머지 4줄(동작을 테스트, 이름, mock, 속도)은 그대로 | 버그 수정은 특정 입력의 예외 동작이 대상인 경우가 많고, 그것을 재현하는 테스트가 곧 edge case 테스트임. 따로 잰 수치는 없음. create-tasks 예시의 "Skip exhaustive coverage of all methods and edge cases" 등 같은 취지의 4줄은 손대지 않음 |
| T3 | 구현 중에 찾은 작업 | 명령이 끝난 파일은 고치지 않음. tasks.md는 체크박스만 예외. "배정된 task만 구현" | 구현 중에 task에 없는 필요한 작업(고칠 다른 파일, 빠진 경우)을 찾으면 tasks.md에 먼저 추가한 뒤 배정된 task로 구현함. 줄 추가만 허용하고 있던 task는 고치거나 지우지 않음. spec.md·requirements.md는 그대로 고치지 않음 | 계획에 적힌 것이 곧 고쳐지는 범위임(평가 wf-floor-tcx: 계획이 정답 파일을 모두 담은 런은 정답 파일을 모두 고친 비율 89.5%, 다 담지 못한 런은 24.1%). 새로 찾은 작업을 정식으로 구현할 길을 둠. 모델이 이 길을 쓸지는 확인되지 않음 |
| T4 | 보고서의 전체 Status | 머리의 Status 칸에 세 값(Passed / Passed with Issues / Failed)만 있고 언제 무엇을 적는지 기준이 없음 | 보고서 양식 뒤에 기준을 적음: 두 절의 Status에서 정해짐. All Complete + All Passing이면 Passed, ⚠️로 표시한 task가 있거나 이 변경을 위해 쓴 것이 아닌 테스트가 실패하면(Some Failures) Passed with Issues, 이 변경을 위해 쓴 테스트가 실패하면(Critical Failures) Failed | 평가(wf-floor-tcx)에서 보고서의 96.2%가 Passed이고, 그중 61런은 마지막 검증이 실패, 42런은 같은 보고서의 Failing 칸이 1 이상. 해결률보다 보고서 정확도의 문제 |
| T5 | 실패한 테스트를 두고 체크함 | 구현 단계에 "테스트가 통과하도록 한다"만 있음 | "수정 때문에 테스트가 실패하면 고치고 다시 돌린 뒤에 task group의 마지막 하위 task를 체크한다. 두 번 시도해도 통과하지 못하면 체크 대신 ⚠️로 표시하고 넘어간다". ⚠️가 있어도 PHASE 3으로 넘어감. 2026-11-21 사용자 결정으로 "다섯 번까지 시도하고, 그래도 통과하지 못하면 ⚠️로 표시하고 넘어가며 여섯 번째 시도는 하지 않는다"("Make up to five attempts. If it still does not pass, mark that sub-task's checkbox with ⚠️ instead of ticking it, and go on; do not make a sixth attempt.")로 바꿈 | 평가(wf-floor-tcx)에서 구현 중 실패를 보고 체크한 뒤 검증 없이 끝낸 런 16개의 해결률 12.5%(같은 과제 미적용 52.1%). 모델마다 크기가 다르고 런 수가 작음 |
| T6 | 검증에서 실패를 보고도 끝냄 | PHASE 3: "실패한 테스트를 고치지 말고 기록만"(upstream 원문). upstream은 사람이 보고서를 읽고 다시 시킴 | 실패하면 수정 때문인지 확인(자기가 쓴 테스트면 그렇다, 기존 테스트면 `git stash -q && <테스트 명령>; git stash pop -q` 한 줄로 수정 없이 돌려 봄). 수정 때문이고 옛 동작을 기대하는 테스트가 아니면 PHASE 2로 한 번 돌아가 고치고 PHASE 3을 Step 1부터 다시 함. 한 번만. 그 밖의 실패는 그대로 기록만 | 평가(wf-floor-tcx)에서 마지막 검증이 실패인 채 끝난 런 6.1% → 14.1%, 손실 차이 −11.2. 그중 PHASE 3에서 실패를 본 런 50개(해결률 44.0%, 미적용 52.0%). 위험: 실패한 채로도 풀린 런이 있어 판단이 틀리면 옳은 수정을 망가뜨림. `git stash pop`을 빠뜨리면 수정이 사라지므로 한 줄 명령으로 지정함 |
| T7 | 수정 task에 고칠 파일을 적음 | create-tasks: "task는 구체적이고 확인 가능하게"만 있고, 예시의 수정 하위 task(1.2, 1.3)에는 파일 자리가 없음 | 제약에 한 줄을 넣음: "코드를 고치는 하위 task는 그 task 줄에 고칠 파일의 저장소 경로를 적는다. 구현 중에 추가하는 task도 같고, 그 파일을 고치기 전에 추가한다". 예시의 1.2, 1.3 줄을 `[First change to make] in [path of the file to change]` 꼴로 바꿈 | 평가(t6-full-floor27) 499런 중 31.9%(159런)가 수정 task에 파일을 하나도 적지 않음. 적은 파일과 실제 수정을 대조하는 채점(`ticked_after_work`, penalty 항목)은 파일이 적혀 있어야 판정할 수 있음. 파일을 적은 런의 해결률이 더 높다는 근거는 없음(난이도를 뺀 차이 +6.3, 구간 −1.1 ~ +13.9). 모델이 이 줄을 따를지는 확인되지 않음(이 문서로 돌린 런 없음) |
| T8 | 실패 뒤 고칠 대상에 자기 테스트를 넣음 | implement-tasks PHASE 2 (T5): "내 변경 때문에 테스트가 실패하면 변경을 고치고 테스트를 다시 돌린다" | "내 변경 때문에, 또는 내가 쓴 테스트 자체가 틀려서 실패하면 변경이나 그 테스트를 고치고 다시 돌린다"로 바꿈. 기존 테스트 줄은 바꾸지 않는다는 규칙(create-tasks)과 PHASE 3의 "PHASE 2로 한 번 돌아가 변경을 고친다"는 그대로 | 문서에는 테스트를 고치라는 말이 없었는데, 평가(t6-full-floor27)에서 PHASE 2에 실패를 본 런의 81%가 그 뒤에 테스트를 고침. 실패 뒤 소스 또는 테스트를 고친 런의 해결률이 안 고친 런보다 높음(49.7% 대 30.8%, 단순 비교). 이 문구로 돌린 런은 없음 |
| T9 | 구현 중 자기 테스트 실행 문장의 "(if any …)" | implement-tasks PHASE 2 (T1 문장): "Running the tests you've written (if any; they are check scripts …)" — 자기 테스트가 없을 수 있다고 읽힘 | "(each implementation task group writes them first, as its x.1 sub-task; they are check scripts …)"로 바꿈 | create-tasks의 "각 구현 그룹은 테스트 2–8개를 씀"(122행), "그룹은 테스트 작성(x.1)으로 시작함"(126행)과 어긋났음. 2026-11-20 사용자 결정 1: 항목은 그대로 두고 문서를 맞춤. 자기 테스트를 쓰지 않은 런(평가 102런)과 그룹 안에서 코드를 먼저 고친 런(104런)은 맞는 실패로 남음 |
| T10 | tasks.md의 절 | create-tasks: 예시 뒤 "Adapt this structure …"만 있고 절을 빼도 되는지 말하지 않음 | 그 목록 뒤에 한 문장: "Whatever you adapt, every tasks.md keeps the example's three sections: `## Overview` with its `Total Tasks:` line, `## Task List`, and `## Execution Order` …" | 실행 순서 계획(Core Responsibilities 2)이 적히는 곳은 Execution Order 절뿐인데, 평가 499런 중 41런이 절을 뺐고 "절이 있음" 항목이 문서에 없는 규칙으로 실패시켰음. 이 문장으로 항목이 문서가 말한 것을 봄. 저장된 평가 런은 이 문장을 받지 않았으므로 판정은 그대로 |
| T11 | 자기 테스트를 고치는 것 | implement-tasks PHASE 2 (T5, T8): "내가 쓴 테스트 자체가 틀려서 실패하면 그 테스트를 고친다"만 있고 무엇이 틀린 테스트인지, 어떻게 고치는지 말하지 않음 | 40행 끝에 두 문장: "A test you wrote is wrong only when it checks something the task does not ask for: then correct what it checks. Never make a failing test pass by loosening or removing what it checks." | 보상 검토 카드 7-7: 실패하는 자기 테스트를 늘 통과하게 고쳐 써도 만점이었고, 평가 499런 중 16런이 검증 단계에서 자기 check 스크립트를 고쳤음. 테스트를 약하게 했는지는 테스트의 뜻을 읽어야 알 수 있어 규칙으로 판정하지 않고 문서로만 정함. 저장된 평가 런은 이 문장을 받지 않았으므로 판정은 그대로 |

## 문구 일반화 (G)

데이터셋 한 가지 경우에 맞춰져 있던 문구를 바꿈 (해결률 영향과 별개, `agentos_v2/porting/later.md`).

| 바꾸기 전 | 바꾼 뒤 | 위치 |
|---|---|---|
| the issue in `<issue_description>` | the task description in the task message | shape-spec PHASE 1, core-workflow |
| the issue (입력을 가리킬 때) | the task description / the task | shape-spec PHASE 2, core-workflow, system prompt |
| The issue is your only input from outside | The task message is your only input from outside | core-workflow |
| the repository at `/testbed`, `/testbed` | the repository (you work in) | instruction, system prompt, core-workflow |

## 그대로 둔 것

- 확인 질문 4–8개와 자체 답변, 재사용 코드 검색: 수정하지 않기로 함.
- "끝난 산출물은 고치지 않음": tasks.md의 task 추가(T3)만 예외로 둠. spec.md와 requirements.md는 그대로 고치지 않음.
- 테스트 규칙(검사 스크립트 또는 기존 테스트 모듈에 함수 추가, 기존 테스트 줄 변경 금지): 일반적인 규칙이라
  데이터셋에 맞춘 문구로 보지 않고 그대로 둠.
- 남긴 standards 6개(global 5개, testing 1개)와 그 안의 웹 관련 줄(예: 서버·클라이언트 검증).
- 질문 양식의 "UI components", "page layouts" 같은 upstream 문구.

## 채점기 (1차, 2026-11-13)

- `derive_rubric.py`가 agentos_v2의 `reward/rubric.yaml`에서 만듦. 모델 호출 없음. agentos_v2 채점기나 이 워크플로우 문서가
  바뀌면 다시 돌림 (`--check`로 낡았는지 확인).
- 항목 207개 → 160개. 지운 47개 = 뺀 단계의 항목 19개(제품 맥락 읽기 4, 시안 5, roadmap 3, 사용자 스토리 4,
  `implementation/` 폴더와 빈 폴더 규칙 2, 후속 질문 1) + T1로 문서에서 없어진 요구 1개("PHASE 3에서 전체 테스트를 돌렸는가")
  + 검사 없이 문장만 기록하던 항목 중 그 문장이 문서에서 빠진 27개(standards 문장이 많음).
- 고친 설정값: requirements.md·spec.md의 허용 절 목록, 양식 자리표시 목록(빠진 것 39개 제거, 문구가 바뀐 것 1개는 새 문구로, 새 tasks 예시의 자리표시 9개 추가),
  보고서의 테스트 결과 절 이름(`3.` → `2.`).
- 나머지 항목은 검사 내용 그대로. 출처의 줄 번호와 인용문만 이 워크플로우 문서에 맞춤 (인용문 44개는 바뀐 문구로 다시 찾음,
  찾지 못한 출처 51개는 지움, 출처가 하나도 안 남은 항목은 없음).
- 전용 검사는 agentos_v2의 함수를 `agentos_bugfix.*` 이름으로 등록해 씀 (`reward/checks.py`). 이를 위해 agentos_v2의 보고서
  검사에 테스트 결과 절 이름을 받는 선택 설정값(`suite_section`)을 추가함 (agentos_v2 동작은 그대로).
- 기준 런(`selftest_golden.py`, agentos_v2 것에서 뺀 단계만 제거): 만점 1.0, 정직한 변형 10개도 0.99 이상(9개는 만점, 테스트 검토 group을 둔 변형 0.9913).
- 자체 점검 미달 2건 (2026-11-19에 해결, 아래 "자체 점검 미달 해결" 절):
  - "정직한 런의 서식을 바꾼 변형"이 0.9789로 기준 0.98에 0.0011 모자랐음 (agentos_v2는 0.9833). 같은 항목(requirements.md의
    In Scope 칸)에서 잃는 것은 agentos_v2와 같고, 항목 수가 줄어 한 항목의 비중이 커진 결과.
  - "편집 뒤 모든 테스트 실행을 전체 테스트로 바꾼 변형"이 0.9974로 기준 0.995 이하에 못 미쳤음(감점이 0.0026). T1로 기준 런이
    구현 중에 기존 테스트를 돌리게 되면서 이 변형이 처음 적용됨. 걸리는 항목은 "구현 중에는 전체 테스트를 돌리지 않음"인데
    agentos_v2에서 권고(should, 가중치 0.25)로 되어 있어 감점이 작음.
- T3에 따라 "tasks.md는 create-tasks 뒤에 체크만 한다" 항목이 줄 추가도 허용함(있던 줄을 고치거나 지우면 감점 그대로). 이를 위해
  agentos_v2의 tasks 검사에 선택 설정값(`additions`)을 추가함(agentos_v2 동작은 그대로). create-tasks 단계의 tasks.md 항목 3개
  (task 수, group 구성, 테스트 먼저)는 create-tasks가 끝난 시점의 tasks.md를 보도록 바꿈. 기준 런에 "구현 중에 task를 추가하는"
  정직한 변형을 넣었고 만점. 같은 런이 agentos_v2의 규칙으로는 0.9977.
- T4에 따라 항목 1개를 새로 넣음: 머리 Status가 두 절의 Status에서 정해지는 값과 같은가(필수). agentos_v2의 보고서 검사에 규칙
  `overall_status`를 추가해 구현함(agentos_v2 채점기는 이 규칙을 쓰지 않음). "Passed with Issues"나 "Failed"를 적는 것 자체는
  감점하지 않고, 적은 값이 절들과 맞는지만 봄. 항목 수 161개.
- T6에 따라 "모든 task를 체크한 뒤에는 저장소를 고치지 않는다" 항목이 수정 한 번을 허용함: 그 쓰기 앞에 실패한 테스트 실행이 있고
  뒤에 테스트 실행이 있어야 함. 보고서의 수치·실패 목록·Status 항목과 "PHASE 3에서 테스트를 돌렸는가"는 수정 뒤의 실행을 봄.
  agentos_v2의 검사에 선택 설정값(`fix_round`)으로 구현(agentos_v2 채점은 그대로). `git stash`로 내용을 되돌린 것은 수정으로 세지 않음.
  기준 런에 `fix_round` 변형을 넣었고 만점, 같은 런이 agentos_v2 규칙으로는 감점.
- T5에 따라 항목 2개를 새로 넣음(필수, 2026-11-14). 항목 수 164개.
  - `ticked_passing`: task group의 테스트 실행 하위 task(문구에 테스트와 실행이 있는 마지막 하위 task, 없으면 group의 마지막 하위
    task)를 `[x]`로 체크한 시점에, 마지막 코드 수정 뒤의 최근 테스트 결과가 실패가 아닌가. 테스트 결과는 검사 스크립트의 실행
    결과와 인정되는 테스트 실행(자기 스크립트든 기존 테스트든)을 함께 봄. 실패였더라도 보고서의 테스트 결과 절에 실패가 적혀
    있으면(Failing·Errors 수, Status, Failed Tests 목록 중 하나) 허용함: 과제가 바꾸라는 동작을 검사하는 기존 테스트는 실패한 채
    두고 보고서에 적으라는 것이 문서의 지시임. 마지막 코드 수정 뒤에 테스트 결과가 없는 group은 세지 않고, 그런 group뿐이면 해당 없음.
  - `warned_after_attempts`: 체크 대신 ⚠️로 표시한 테스트 실행 하위 task마다, 그 group 구간(앞 group이 끝난 뒤부터 표시까지)에서
    첫 코드 수정 뒤에 실패한 테스트 결과가 2회 이상 있고 그 사이에 코드 수정이 있는가. ⚠️가 없으면 해당 없음. 먼저 체크했다가
    나중에 ⚠️로 바꾼 것(PHASE 3 Step 1의 표시)은 대상이 아님.
  - 기존 항목 3개를 문서대로 한 런이 감점되지 않게 고침: "검사 스크립트가 마지막에 통과했는가"는 위 조건을 만족하는 ⚠️ 표시가
    그 스크립트의 실패한 실행 뒤에 있으면 실패한 채 둔 스크립트를 인정함(`warned`), 그리고 `git stash` / `stash pop`을 코드 수정으로
    세지 않음(`fix_round`; T6의 "수정 없이 돌려 보기" 뒤에 스크립트를 다시 돌리지 않아도 됨). "tasks.md의 task 줄 형식"은 `[⚠️]` 칸과
    ⚠️가 붙은 줄도 task 줄로 받음(agentos_v2에서는 ⚠️ 표시 한 줄이 형식 위반으로 잡힘).
  - 보지 않는 것: 두 번보다 많이 시도한 것, 실패한 테스트가 수정 때문인지.
- 자기가 쓴 검사 스크립트의 실패를 문서가 테스트 실패로 치는 두 곳에서 채점기도 그렇게 봄(2026-11-14). 전에는 테스트 실행기의 실행만 봤음.
  - 보고서의 테스트 결과 Status(`suite_status`): 실행기의 실행에 실패가 없어도, 검사 스크립트의 마지막 실행이 실패였으면
    "❌ Critical Failures"를 맞는 것으로 봄(T4: 이 변경을 위해 쓴 테스트가 실패한 경우의 Status). 반대 방향(스크립트가 실패했는데
    "All Passing"이라고 적음)은 여기서 판정하지 않음: 실패 여부를 종료 코드와 출력으로 읽는 것이라 틀릴 수 있고, 그런 런은
    "검사 스크립트가 마지막에 통과했는가"에서 이미 감점됨.
  - PHASE 3의 수정 한 번(`code_frozen`): PHASE 3에서 검사 스크립트가 실패한 것도 수정하러 돌아가는 근거로, 그 뒤의 스크립트
    실행도 다시 돌린 것으로 봄(T6: 자기가 쓴 테스트의 실패는 수정 때문).
  - 기준 런에 정직한 변형 `script_failing`(검사 스크립트가 두 번의 시도와 PHASE 3의 한 번을 거쳐도 실패: ⚠️, Critical Failures,
    Failed)을 넣었고 만점. 이 두 설정값을 빼면 각 항목에서 실패함을 테스트로 확인.
- 알려진 어긋남: "코드가 바뀌는 동안에는 전체 테스트를 돌리지 않음"(권고) 항목은 마지막 코드 변경까지를 구현 중으로 봄. PHASE 3에서 전체
  테스트를 돌린 뒤 수정하러 돌아간 정직한 런은 이 권고 항목에서 감점됨(가중치 0.25).
- T1에 따라 항목 1개를 새로 넣음(필수, 2026-11-14): `phase2_run` — 구현 단계(모든 task가 체크되기 전)에서, 마지막 코드 수정
  뒤에 저장소의 기존 테스트를 실행한 인정되는 기록이 1회 이상 있는가. 통과 여부는 보지 않음. 코드 수정이 없으면 해당 없음. 체크
  시점을 알 수 없으면 보고서를 쓰기 전까지를 봄. 그 테스트가 수정한 파일의 테스트인지는 보지 않음(파일 이름이나 폴더로 맞추면
  대응이 안 되는 저장소에서 문서대로 한 런이 감점되므로 넣지 않기로 함).
- 위 세 규칙은 agentos_v2의 검사 함수에 규칙과 선택 설정값으로 넣었고 agentos_v2의 rubric은 쓰지 않음(agentos_v2의 기준 런과 변형
  40개 점수 동일). 기준 런에 정직한 변형 2개(`expected_failure`: 과제가 바꾸라는 동작을 검사하는 기존 테스트를 실패한 채 두고
  보고서에 적음, `warn_attempts`: 두 번 시도 뒤 ⚠️, PHASE 3에서 한 번 더 시도, 남은 실패를 보고서에 적음)를 넣었고 둘 다 만점.
  규칙이 잡아야 하는 런 3개(`DISHONEST`: 구현 중 기존 테스트 실행 없음, 실패한 채 체크하고 보고서에는 모두 통과, 시도 없이 ⚠️)는
  테스트에서 해당 항목이 실패하는지 확인함.
- T7에 따라 tasks.md의 양식 글자 검사(`no_template_residue` 2개)에 `[path of the file to change]`를 넣음(2026-11-18). 항목 수는 164개 그대로.
  create-tasks.md에 한 줄이 늘어 그 뒤 줄을 인용하는 출처 13곳의 줄 번호가 1씩 밀림.
- rubric 밖의 penalty 항목 4개(2026-11-18, `reward/penalty.py`): tasks.md 수정 task에 적은 파일을 최종 patch, 과제의 정답 patch와 대조함.
  `agentos_bugfix/penalty`와 항목별 신호로 기록만 하고 compliance와 학습 reward에는 들어가지 않음.
  - `named`: 수정 task에 파일을 하나도 적지 않으면 감점. `named_equals_patch`: 적은 파일과 최종 patch의 파일이 다르면 감점.
    `named_covers_gold`: 적은 파일에 정답 파일이 빠지면 감점. `patch_covers_gold`: 최종 patch에 정답 파일이 빠지면 감점(다른 파일이 더 있는 것은 허용). (두 항목은 2026-11-21 C-2에서 뺌: 아래 "테스트 실패 다루기와 계획한 파일" 절)
  - 적은 파일은 tasks.md의 모든 버전에서 모음. 한 번 적으면 지워도 남고, 이미 고친 뒤에 처음 적은 파일은 세지 않음. 파일을 적지 않은 런은 앞의 세 항목이 모두 감점.
- T8에 따라 `ticked_passing` 항목의 인용문과 근거 문구를 새 문장으로 바꿈(2026-11-19). 판정은 그대로, 항목 수 164개 그대로.
  `warned_after_attempts`는 두 실패 사이의 저장소 코드 수정뿐 아니라 checks/ 스크립트 수정도 시도로 셈(T8: 자기 테스트가 고칠 대상일 수 있음).
- rubric 밖의 penalty 항목 7개를 더함(2026-11-19, `reward/penalty_tests.py`): implement-tasks의 테스트 행동. 이름은 `agentos_bugfix.implement_tasks.penalty.<묶음>.<규칙>`.
  앞의 4개와 같이 기록만 하고 compliance와 학습 reward에는 들어가지 않음. 정답 patch나 정답 테스트 파일은 읽지 않음(런이 알 수 있는 것만 봄).
  - PHASE 2(첫 소스 수정부터 PHASE 3 시작까지)
    - `phase2_run.existing_and_own`: 마지막 소스 수정 뒤에 저장소 테스트의 유효한 러너 실행과 자기 테스트(checks/ 스크립트, 자기가 쓴 테스트 파일) 실행이 둘 다 없으면 감점.
    - `phase2_fail.edited_after_fail`: 실패 결과를 본 뒤 고치지 않으면 감점. task group이 모두 체크된 시점으로 구간을 나누고, 실패가 있는 구간마다 그 구간의 마지막 실패 뒤 체크 전에 소스 또는 테스트 수정이 있어야 함.
    - `phase2_fail.last_result_pass`: 실패했던 테스트가 각자의 마지막 실행에서 통과하지 않으면 감점(스크립트는 경로, 러너 실행은 대상 테스트 파일 단위).
  - PHASE 3(마지막 task를 체크한 쓰기부터 보고서 첫 쓰기까지)
    - `phase3_run.existing_and_own`: PHASE 3 안에 위와 같은 두 실행이 둘 다 없으면 감점.
    - `phase3_fail.cause_checked`: 러너 실행이 실패했는데 그 뒤에 `git stash` 명령이 없으면 감점.
    - `phase3_fail.edited_after_fail`: 고쳐야 하는 실패(자기 테스트만 실패했거나, `git stash` 안에서 돌린 러너가 통과해 내 변경이 원인임이 확인됨)를 본 뒤 소스 또는 테스트를 고치지 않으면 감점. 원인이 아님이 확인됐거나 판별하지 않은 실패는 이 항목의 대상이 아님.
    - `phase3_fail.last_result_pass`: 실패 결과를 봤는데 보고서 전 마지막 결과가 통과가 아니면 감점.
  - 대상이 아닌 런: 실패 관련 5개는 1.0(실패를 본 적이 없으면 감점 없음), 실행 2개는 0.0(소스를 고치지 않았거나 PHASE 3 구간을 잡을 수 없음). 어느 쪽인지는 `penalty_applies.<묶음>.<규칙>`에 기록.
  - `agentos_bugfix/penalty`는 파일 항목(해당하는 것)과 테스트 항목 7개의 평균이 됨. 묶음별 평균은 `penalty_plan_files`, `penalty_tests`.
  - 결과로 읽지 않는 실행 두 가지(2026-11-19 코드 검토 뒤 수정). 원인 판별 실행: 변경을 stash로 뺀 동안의 러너 실행. `git stash`부터 다음 `git stash pop`/`apply`까지이고,
    한 명령이든 여러 명령이든 같음. pop 없이 다시 고치기 시작하면 그 수정부터는 새 변경으로 봄. `git stash list`/`show`/`drop`과 저장할 것이 없던 `git stash`는 세지 않음.
    수정 적용용 스크립트: checks/ 밖의 스크립트 중 실행한 단계에 저장소 파일이 바뀐 것(`fix.py` 등). 그 실행은 테스트 결과가 아니고, 그 작성은 테스트 수정이 아님.
  - `phase3_fail.cause_checked`는 `git stash` 글자가 아니라 변경을 뺀 동안의 러너 실행이 있어야 1.0. 그 실행은 기존 테스트 실행으로 세지 않음.
  - 자기 테스트 파일의 러너 실행은 그 파일에 처음 쓴 뒤의 실행만 자기 테스트 실행으로 셈. 경로 표기와 점 표기(`tests/queries/test_q.py`, `queries.test_q`)는 같은 테스트로 봄.
  - 새로 만든 파일을 런의 스크립트로 보는 이름 규칙(`check_*`, `repro_*` 등)은 저장소 최상위 파일과 최종 patch에 남지 않은 파일에만 적용. 패키지 안에 만들어 최종 patch에 남은 파일은 소스.
  - 저장소에 새로 만든 테스트 파일의 러너 실행은 읽지 않음(문서가 허용하지 않는 형태이고 compliance의 `created_files.tests`가 봄).
  - 테스트 항목 계산이 실패하면 테스트 7개만 0.0으로 두고 `penalty_tests_errors` 1.0을 기록. 파일 항목은 그대로 기록.
  - 문서가 허용하는 "두 번 시도 뒤 ⚠️" 경로는 실패를 남긴 채 끝나므로 PHASE 2의 두 실패 항목에서 감점됨(기준 런 변형 `warn_attempts`, `expected_failure`, `script_failing`).
  - 채점 엔진: `Report`에 판정 맥락(`ctx`)과 재생에 쓴 shell 변수(`shell_vars`)를 넣음. penalty가 채점 뒤에 명령을 다시 읽기 위함. rubric 판정은 바뀌지 않음.
  - 코드 파일만 셈(테스트 파일, 생성 파일, 런이 만든 임시 스크립트 제외). 정답 patch는 과제 폴더에서 읽고 sandbox에는 올라가지 않음.
- 셸 변수(2026-11-18): shape-spec이 spec 폴더를 `$SPEC_PATH`에 담게 하는데 기록 재생은 명령마다 변수 없이 시작해서, 변수로 쓴 쓰기·읽기·실행이 보이지 않았음.
  sandbox에 남은 spec 폴더에서 변수 값을 알아내 한 번 더 재생하도록 고침(agentos_v2도 같음). 평가 499런 중 48런의 compliance가 0.574 → 0.762(나머지 451런 0.760), 내려간 런 없음.
  항목 단위로는 `later_edits` 14런, `suite_run` 6런 등 "안 보여서 통과"되던 것이 실패로 바뀜. 이 수정 전후의 compliance는 변수를 쓴 런에서 직접 비교할 수 없음.
- 검사 스크립트 결과 읽기(2026-11-18): 스크립트 출력의 요약 줄 "6 passed, 0 failed", "0 errors"를 실패 문구로 읽어, 종료 코드 0으로
  통과한 실행이 실패로 판정됐음. 개수가 1 이상일 때만 실패 문구로 보도록 고침(agentos_v2도 같은 함수를 씀). 평가 499런 중 12런이 바뀜:
  `pass_last` 12런, `ticked_passing` 8런이 실패에서 통과로. 그 12런의 compliance 0.788 → 0.804, 전체 평균 0.7603 → 0.7607, 내려간 런 없음.
  - 고치지 않은 것: 종료 코드 0인 실행의 출력에 환경 경고의 Traceback이 섞인 경우(예: site-packages의 .pth 처리 경고)는 여전히 실패로 읽음.
  - "스크립트가 실패했는데 All Passing이라고 적음"은 계속 판정하지 않음(위 2026-11-14 항목). 해당하던 11런을 확인하니 3런은 이런 잘못 읽기였고,
    8런은 스크립트가 설정 오류(`No module named 'tests.settings'` 등)로 실행되지 못한 경우였음.
- 없는 것: `rubric.md`(사람이 읽는 항목 표).
- 항목의 근거 메모(`modality_evidence`)에 적힌 줄 번호는 agentos_v2 문서의 것 그대로임. 출처(`sources`)의 줄 번호와 인용문은 이 워크플로우 문서의 것.

## 평가 (2026-11-13 ~ 11-14)

- SWE-bench Verified 499과제, wf-floor-tcx-step27 모델(agentos_v2로 학습), 코드 bee66a2d(T1·T5 채점 항목을 넣기 전):
  해결 252/499 = 50.5%. 같은 모델의 agentos_v2 적용 52.7%(차이는 구분되지 않음, p 0.30), 미적용 58.4%. 채점 오류 0.
  결과는 `rllm-home/eval_results/agentos_bugfix/t6-full-floor27/`.
- 그 499런의 궤적에 지금 채점기를 다시 적용한 결과(오프라인 재채점, 채점 오류 0):

  | 항목 | 통과 | 실패 | 해당 없음 |
  |---|---|---|---|
  | `phase2_run` | 250 | 240 | 9 |
  | `ticked_passing` | 318 | 67 | 114 |
  | `warned_after_attempts` | 1 | 0 | 498 |

  `ticked_passing`의 실패 67개 중 31개는 tasks.md가 없거나 내용을 따라갈 수 없는 런이고, 통과 318개 중 23개는 실패한 채 체크했지만
  보고서에 실패가 적힌 경우. 기존 항목은 "검사 스크립트가 마지막에 통과했는가" 13런, "task 줄 형식" 2런, "PHASE 3의 수정 한 번" 3런이
  실패에서 통과로 바뀜. "❌ Critical Failures"를 적은 런은 없어 `suite_status`의 판정은 그대로.

## penalty 항목 통일 (2026-11-19)

speckit_bug·openspec_ff와 같은 규칙으로 맞춤. 문서는 바꾸지 않음.

- penalty 항목 11개(파일 4, 테스트 7. 2026-11-21 C-2 뒤 9개: 파일 2, 테스트 7)를 `post` 밖 계산에서 rubric의 `log_only` 항목으로 옮김 (`derive_rubric.py`의
  `PENALTY`, kind `agentos_bugfix.penalty`). compliance에는 들어가지 않으며, 다시 만든 rubric에서 golden과 변이 실행의
  compliance는 이전과 같음. 엔진 `Report`에 더했던 `collected`, `ctx`, `shell_vars` 필드는 없앰 (항목이 엔진 안에서
  판정되므로 `$SPEC_PATH` 값을 다시 설정할 필요가 없음).
- 소스 변경 시점, 임시 스크립트 판정, 실패한 테스트의 재통과 판정, 스크립트 실행 결과 읽기, 파일 이름 대조를 공통
  함수로 바꿈 (`workflow_rubric/facts.py`의 `source_change_steps`·`is_run_script`·`same_file`,
  `workflow_rubric/results.py`). 달라지는 판정: 소스 변경에 코드·설정 확장자 조건이 붙음; 좁힌 재실행(`-k`, 다른
  `::id`)으로는 실패가 해소되지 않음; 임시 스크립트 이름 규칙이 하나로 됨(파일 항목에서 최상위의 임의 새 `.py`를
  스크립트로 보던 규칙은 없어지고, 최상위의 임시 이름이거나 최종 변경에 남지 않은 새 스크립트만 해당).
- 점수를 합치는 규칙이 공통 `workflow_rubric/penalty.py`로 바뀜. 테스트 항목의 해당 없음 값이 달라짐: 전제 행동(코드
  변경, 그 구간의 테스트 실행, PHASE 3 도달)을 안 했으면 0, 했는데 실패가 없었으면 1 (이전에는 실패 조건 항목이 항상
  1). 정답 패치가 없는 태스크의 정답 항목과 workdir을 모르는 실행의 테스트 항목은 판정 불가로 평균에서 빠짐
  (`/testbed` 기본값은 없앰).
- 최종 변경 파일은 `facts.change_paths`로 읽음. 저장된 에피소드의 patch는 엔진(`evaluation.py`)이 diff로 채움.
- 신호 이름: 항목별 값이 `agentos_bugfix/<stage>.penalty.<이름>`으로 바뀜 (이전에는 workflow 이름이 한 번 더 붙음).
  `penalty_applies.<이름>`은 판정 불가가 아닌 항목마다 나옴 (판정 불가 항목은 값도 `penalty_applies`도 없고
  `penalty_unavailable`에 개수만 셈). `penalty_errors`, `penalty_tests_errors`는 없앰 (판정 중 오류는
  엔진 규칙대로 그 항목 실패와 `engine_errors`). `__init__.py`에 `penalty_signal` 지정.

## 자체 점검 미달 해결 (2026-11-19)

자체 점검 상태가 `failed`에서 `passed`가 됨. 항목과 가중치는 바꾸지 않음.

- 서식을 바꾼 변형 (0.9789 → 1.0): 라벨 줄 다음에 빈 줄이 있으면 그 아래 목록을 값으로 읽지 못하던 것을 고침
  (`workflow_rubric/markdown.py`의 `_continuation`). 라벨 줄에 값이 없을 때만, 빈 줄 뒤에 오는 목록과 항목 사이에 빈 줄이
  있는 목록을 그 라벨의 값으로 읽음. 빈 줄 뒤에 다른 라벨, 제목, 문단이 오면 이전처럼 빈 값. 공통 코드라 모든 워크플로의
  라벨 칸 항목에 적용됨: 자체 점검에서 바뀐 것은 이 변형뿐 (agentos_v2 0.9833 → 1.0, speckit_bug·speckit_sdd·openspec_ff 변화
  없음).
- 전체 테스트로 바꾼 변형 (점수 0.9974 그대로): 이 변형에 요구하는 최소 감점을 0.005에서 0.00125로 낮춤
  (`derive_rubric.py`의 `SELFTEST` → rubric의 `scoring.selftest.full_suite_rerun_min_drop`). 0.005는 필수 항목 하나가 걸릴
  때를 가정한 값인데 이 변형에 걸리는 항목은 권고 하나뿐이라서, 권고 항목만 걸리는 변이가 쓰는 값(`mutations.SHOULD_DROP`)에
  맞춤. 항목을 필수로 올리는 방법은 쓰지 않음 (학습 reward에서 이 항목의 비중이 4배가 됨).

## PHASE 3 실패 항목의 해당 없음 값 (2026-11-20)

PHASE 3에서 실패를 보지 않은 실행이 PHASE 3 실패 항목 3개(`phase3_fail.cause_checked`, `phase3_fail.edited_after_fail`,
`phase3_fail.last_result_pass`)에서 받는 값을 바꿈.

- 이전: PHASE 3 안에서 테스트를 돌렸으면 1, 안 돌렸거나 PHASE 3 구간을 잡을 수 없으면 0.
- 이후: 최종 코드에 테스트 결과가 있으면 1, 없으면 0. "결과가 있다"는 PHASE 3 안에서 테스트를 돌렸거나, 마지막 소스 수정
  뒤부터 보고서 전(보고서가 없으면 실행 끝)까지 어느 단계에서든 테스트를 돌렸다는 뜻. PHASE 3 구간을 잡을 수 없는 실행도
  같은 기준으로 봄.
- 이유: PHASE 2에서 마지막 수정 뒤에 테스트를 돌리고 PHASE 3에서 반복하지 않은 실행은, 한 번 더 돌려도 새로 볼 실패가 없음.
  이런 실행이 한 번도 테스트하지 않은 실행과 똑같이 4개 항목을 잃고 있었음. 반복하지 않은 대가는 `phase3_run` 1개로 남김.
- `phase3_run.existing_and_own`과 PHASE 2 항목 3개, 실패가 판정되는 경우의 규칙은 그대로.
- 평가 에피소드 499개(t6-full-floor27) 재채점: PHASE 3에서 테스트를 돌리지 않은 322개 중 247개가 항목 3개를 되찾고 75개는
  0 그대로. penalty 평균 0.456 → 0.591 (통일 이전 0.669). compliance가 바뀐 에피소드는 없음.

## 보상 검토 반영: 단계 구간·순서와 산출물 형식 (2026-11-21)

`tasks/2026-11-20-agentos-bugfix-reward-fixes/03-D-E-G-계획.md`의 문제를 하나씩 고침. 문서는 바꾸지 않음.
rubric의 바뀐 값은 모두 `derive_rubric.py`의 `_review_fixes`가 넣음. 공용 코드에 둔 새 설정값은 기본값이 지금 동작이라
agentos_v2와 다른 워크플로의 판정은 바뀌지 않음.

- D-2 순서 항목의 품질 문턱: 순서 항목(`global.run.order.commands`)이 산출물의 쓰기를 "없음"으로 세는 품질 점수의 문턱을
  0.5에서 0.1로 낮춤(`params.substantive`). 필수 항목 하나가 실패해 단계 점수가 0.1로 묶인 산출물(자리표시 하나, "..." 줄 하나)도
  쓴 것으로 셈. 그 형식 문제는 그 산출물의 단계 점수가 이미 깎음. 0.1 미만(빈 파일, 단계 점수를 0으로 만드는 필수 항목 실패)은
  지금처럼 없음. 평가 499런: 순서 항목이 실패에서 통과로 바뀐 런 114개(실패 207런에서 93런). 자체 점검의 template_copy 변이
  준수율 0.1204에서 0.2315(상한은 단계 점수 0.10이라 지킴), frontmatter_stub 0.0469 그대로.
- E-2 재사용 코드의 (assumed) 표기: Reusability Opportunities 줄 형식 항목이 `shape-spec.md` 130행의 표기(`(assumed) <경로> — <근거>`,
  경로에 백틱 없음)와 템플릿 175행의 표기(백틱)를 둘 다 받고, 찾은 것이 없을 때의 130행 문장("No similar existing features identified
  for reference.")과 없음만 적은 줄(None, None found, N/A, "No similar … identified")도 받음. 130행이 표기 전체를 코드 구간 하나로
  보여 주므로 `` `(assumed) <경로>` — <근거>``처럼 (assumed)와 경로를 한 코드 구간에 넣은 줄도 받음. Existing Code to Reference 줄 형식
  항목도 같은 표기들을 받음 (같은 130행을 인용함). 평가 499런: Reusability Opportunities 항목 59런, Existing Code to Reference 항목 18런이
  실패에서 통과, 통과에서 실패 0런.
- E-4 행 4 Existing Code to Reference의 모든 Feature 줄: 줄 형식 항목이 (assumed) 표기 줄 하나만 있으면 통과하던 것을, 템플릿 160행의
  `- Feature: … - Path: …` 줄이 모두 그 표기여야 통과하게 함(그 줄들에 대한 비율 점수). 템플릿 161 ~ 162행의 다른 줄은 보지 않음.
  공용 `item_format`에 선택 설정값 `each_of`를 더해 구현함(없으면 지금 동작). 평가 499런: 11런이 통과에서 실패(Feature 줄에 (assumed)가 없음).
- E-4 행 5 문서의 자리표시: 잔재 항목(필수, 단계 점수 상한 0.1)에 문서가 쓰는 자리표시를 더함. tasks.md·spec.md·requirements.md·보고서에
  `[this-spec]`, `[current-spec]`, `[spec-path]`(core-workflow.md 44 ~ 45행: 모두 spec 폴더 하나를 뜻함), requirements.md에 shape-spec Step 2 질문
  틀의 `[specific assumption]`, `[specific approach]`, `[Continue with numbered questions...]`, `[Last numbered question about exclusions]`.
  평가 499런: 9런이 통과에서 실패 (tasks.md 7, spec.md 1, requirements.md 1).
- E-1 과제 문장의 "..." 줄: initialization.md와 requirements.md의 빈칸 표시 항목(필수)이, 과제 문장(task의 `instruction`. `<issue_description>`
  태그가 있으면 그 안)의 줄과 같은 줄(공백을 하나로, 앞의 목록 기호를 떼고 비교)을 빼고 판정함. 문서가 과제 문장을 그대로 옮기라고 하므로
  트레이스백의 `    ...` 줄은 빈칸이 아님. 새 kind `agentos_bugfix.task_residue`(`reward/task_text.py`), 과제 문장을 받지 못하면 지금 규칙.
  평가 499런: initialization.md 28런, requirements.md 23런이 실패에서 통과.
- E-4 행 2 initialization.md의 과제 문장: 형식 항목(`shape_spec.initialization.item_format.text`, 필수)이 라틴 글자 셋이 든 줄만 보던 것을,
  과제 문장의 낱말 가운데 절반 이상이 initialization.md에 같은 순서로 있어야 통과하게 함(새 kind `agentos_bugfix.task_text`, difflib의
  일치 구간). 요약하거나 앞부분만 옮긴 파일이 실패함. 실패의 점수는 그 비율 ÷ 0.5라서, 요약한 파일도 순서 항목에는 쓴 파일로 남음
  (0점이면 산출물 품질이 0이 되어 순서 항목이 두 쌍을 더 깎았음: 평가 499런 중 23런). 과제 문장을 받지 못하면 지금 규칙.
  평가 499런: 27런이 통과에서 실패.
- E-3 보고서와 spec.md 글머리 (1-4의 행 10, 12, 13, 15, 그리고 1-7 행 12)
  - Tasks Verification의 Issues Found: 열린(또는 ⚠️) task가 없어도 Incomplete or Issues 절에 None이 아닌 줄이 있으면 맞음
    (템플릿이 그 절에 "have issues"인 task도 적으라고 함). 보고서 규칙의 선택 설정값 `issues_listed`
  - Notes 절: 어느 수준에도 없으면 해당 없음, 다른 수준에 있으면 지금처럼 실패. 공용 `section_present`의 선택 설정값 `optional`
  - spec.md 블록의 글머리: 블록의 첫 글머리보다 깊게 들여쓴 하위 글머리는 세지 않고, 굵은 이름 블록이 있는 절에서 첫 이름 앞의
    글머리는 이름 없는 블록 하나로 셈(1-7 행 12). 블록 규칙의 선택 설정값 `top_level`
  - 맨 위 Status: 1절 Issues Found와 2절 Critical Failures가 함께면 Failed와 Passed with Issues를 모두 맞는 것으로 봄(문서 196 ~ 198행이
    둘이 겹칠 때를 정하지 않음). 이 규칙은 agentos_bugfix만 써서 설정값 없이 고침
  - 평가 499런: Tasks Verification 6런 실패에서 통과, Notes 5런 실패에서 해당 없음, 블록 4런 실패에서 통과와 1런(첫 이름 앞 글머리 10개)
    통과에서 실패, 맨 위 Status 1런 실패에서 통과
- E-4 행 14 Status 값의 섞음: 보고서 Status 칸 세 항목(앞부분 일치 허용)이, 두 허용 값을 섞은 값(`✅ Passed with Issues`: 이모지는 Passed,
  낱말은 Passed with Issues)과 첫 값(Passed, All Complete, All Passing) 뒤에 실패를 덧붙인 값(`✅ All Passing (excluding pre-existing
  failures)`, 바로 앞 세 낱말에 no·0·zero·without가 없는 fail·error·issue·exclud·except)을 실패로 봄. 설명만 덧붙인 값은 그대로 통과.
  공용 `field_enum`의 선택 설정값 `strict_prefix`. 평가 499런: 7런이 통과에서 실패(섞음 3, 실패 덧붙임 4).
- E-4 행 6 답의 근거: requirements.md의 답 항목이 `(assumed) <답> — <근거>` 꼴만 보던 것을, 근거가 출처를 대지 않는 답(경로·코드 구간·식별자·
  출처 낱말(task, issue, description, repository, codebase, grep, search, traceback, error, test, docs)이 없고, 낱말 셋 이하이거나
  "Standard testing practice" 같은 일반론뿐)을 맞지 않은 답으로 셈(비율 점수). 문서 core-workflow.md 71 ~ 72행, shape-spec.md 149행:
  근거는 과제 설명이나 저장소에서 옴. requirements 규칙의 선택 설정값 `basis_check`. 평가 499런: 9런이 통과에서 실패(답 10개).
- E-4 행 8 requirements.md의 ### 절: 절 제목 항목(`shape_spec.requirements.cross_ref.2`)이 ## 제목만 보던 것을, Initial Description 밖의
  ##·### 제목이 모두 템플릿의 이름이어야 통과하게 함(## 제목은 지금처럼 ## 셋, ### 제목은 템플릿의 아홉 이름 가운데 하나)(shape-spec.md 136행 "Include ONLY the items
  specified"). 공용 `headings` 선택자에 `levels`, `skip_sections`, `tag_level`을 더함(없으면 지금 동작). 평가 499런: 3런이 통과에서 실패.
- E-4 행 7 spec 폴더 날짜: 라이브 수집(`workflow_rubric/collect.py`의 task_info 셸 조각)이 롤아웃 시작 때 샌드박스의 날짜(`date +%Y-%m-%d`)를
  `TaskInfo.today` → `Collected.today`로 넘기고, 폴더 이름 항목(`shape_spec.spec_dir.path_match.dated`)은 그 날짜를 알면 폴더 이름의 날짜가
  그날이거나 다음 날(자정을 넘긴 런)이어야 통과함(core-workflow.md 44행, shape-spec.md 33행: 오늘 날짜). 날짜를 모르면(오프라인 재채점,
  그 줄이 없는 옛 수집 출력) 지금처럼 꼴만 봄. 공용 `path_match`의 선택 설정값 `today`. 저장된 평가 499런은 오프라인이라 판정이 바뀌지 않음.
  날짜 2026-11-13(평가일)을 넣어 다시 채점하면 4런이 통과에서 실패(2024·2025년 날짜의 폴더).
- E-4 행 9 verifications 폴더: 폴더 항목(`shape_spec.verifications_dir.artifact_exists`)을 런 끝이 아니라 shape-spec 구간 끝 기준으로 봄
  (shape-spec.md 52행: shape-spec에서 만듦). 기록 재생이 폴더가 처음 생긴 단계(`mkdir`, 파일 쓰기로 생긴 부모 폴더)를
  `Replay.dir_steps` → `Facts.dir_steps`로 남기고, 폴더 산출물의 구간 끝 판정(`_dir_at_stage_end`)이 그 단계와, 재생이 풀지 못한
  `$(date ...)`·변수를 아무 글자로 읽은 `mkdir` 명령의 단계도 봄. 폴더 산출물을 구간 끝으로
  보는 항목은 다른 워크플로에 없음. 평가 499런: 3런이 통과에서 실패(django__django-16527은 shape-spec 중 날짜가 다른 둘째 폴더에만
  verifications를 만들고, 끝에 남은 폴더의 것은 34단계에 처음 만듦).
- E-5 임시 파일과 최종 변경의 소스 파일 (1-8의 행 10, 11, 18)
  - /tmp의 스크래치 파일: `scratch_outside_checks` 항목의 패턴을 spec 폴더 밖 /tmp의 모든 파일과 spec 폴더 안 checks/ 밖의 스크립트로 넓힘
    (core-workflow.md 56행, 89행: 스크래치 파일은 S/checks/로)
  - 저장소의 임시 파일: `workflow_files` 항목이 이름 패턴 외에 런의 스크립트(`facts.is_run_script`)와 런이 만들었다가 스스로 지운(`rm`, `mv`)
    파일도 셈.
    테스트 경로에 새로 만들어 최종 변경에 남긴 설정 파일은 세지 않음(문서가 정하지 않음, 1-4 행 9와 같은 경우). 선택 설정값 `scratch`
  - 코드 변경: 필수 항목 `code_change`가 최종 변경의 소스 파일(테스트·백업·런의 스크립트가 아닌 코드·설정 파일, `facts.source_paths`)에
    대한 편집을 요구함. 공용 `repo_edit` 사실에 거르개 `source`를 더함(없으면 지금 동작)
  - 평가 499런: /tmp 스크래치 19런, 저장소 임시 파일 8런, 코드 변경 4런(소스 변경이 구현 단계 밖에만 있는 sympy__sympy-23413 포함)이
    통과에서 실패
- D-4 없는 산출물의 읽기 항목: 산출물 읽기 항목(`agentos_bugfix.read`)이 나열한 산출물이 끝에 없으면 해당 없음이던 것을, 없는 산출물은
  읽지 않은 것으로 셈(나열한 산출물 전체에 대한 비율, 하나도 없으면 실패). 쓰지 않은 런이 읽기 항목의 실패를 피하지 않게 함.
  읽기 규칙의 선택 설정값 `absent_unread`. 평가 499런: 6런에서 해당 없음에서 실패 23개(구현 단계 spec_inputs 4개 포함, 이 항목은 F-1이 뺌),
  spec.md만 없는 7런의 create-tasks 읽기 항목이 통과에서 실패(점수 0.5).
  예외 (2026-11-21 사용자 결정): create-tasks 단계의 읽기 항목(`create_tasks.run.agentos_bugfix_read.spec_inputs`)에는 켜지 않음. 이 항목은
  전처럼 만들지 않은 문서를 읽어야 할 문서에서 빼고, 둘 다 만들지 않았으면 해당 없음. 문서를 만들지 않은 잘못은 쓰는 단계의 필수 항목이
  이미 깎으므로 여기서 한 번 더 깎지 않음. 위의 create-tasks 쪽 판정 변화는 되돌아감.
- D-5 저장소를 바꾸지 않은 런의 순서 항목 (1-4의 행 11): 되돌림 (2026-11-21 사용자 결정). 순서 사슬의 `first_repo_write`가 일어나지 않은
  런은 고치기 전처럼 그 앞뒤 쌍을 잃음. 버그를 고치는 워크플로에서 저장소를 한 번도 고치지 않은 런은 구현 단계를 하지 않은 것이고, 하지 않은
  일을 해당 없음이 아니라 실패로 보는 D-4와 방향을 맞춤. 넣었던 공용 `order`의 선택 설정값 `skip_if_absent`와 그 설정은 지움.
- D-3 다음 명령 문서를 일찍 연 런의 단계 구간: rubric `scoring.close_on_artifact`(새 키, 기본 거짓). 단계의 닫는 산출물(requirements.md 등)이
  다음 단계 문서를 연 뒤에 처음 쓰였으면, 그 단계 구간을 그 산출물의 마지막 쓰기(다음 단계 산출물의 첫 쓰기, 그 뒤 단계 문서의 첫 읽기,
  첫 저장소 쓰기 가운데 이른 것 전) 다음 단계까지 늘림. 다음 단계의 시작은 그대로라 두 구간이 겹침. 문서를 일찍 연 것은 순서 항목이 셈.
  `workflow_rubric/facts.py`의 `_close_on_artifact`. 같은 구간 규칙을 쓰는 agentos_v2·openspec_ff·speckit_sdd는 키가 없어 그대로.
  평가 499런: 60런에서 판정 134개가 실패에서 통과(`shape_files_left_alone` 58런, initialization 읽기 35런, 재사용 검색 32런 등).
- D-1 보고서 항목과 `suite_run`의 비교 대상 실행 (1-9)
  - 대신 구간: 모든 task가 체크된 쓰기가 없거나 보고서보다 늦어 PHASE 3 구간이 없으면, 보고서 첫 쓰기 전의 마지막 코드 변경과 tasks.md의
    마지막 쓰기 가운데 늦은 것 다음 단계부터 보고서 첫 쓰기 전까지를 비교 구간으로 씀(`fallback_window`, `comparison_window`,
    `comparison_runs`). 모든 task를 체크한 런과 같이, 그 뒤에 테스트를 돌려야 함. `code_frozen`과 penalty는 지금처럼 `phase3_start`를 씀.
    선택 설정값 `phase3_fallback`(보고서 세 규칙과 `suite_run`)
  - 스크립트 결과: 비교 구간에 유효한 저장소 테스트 실행이 없고 checks/ 스크립트 실행만 있으면, 보고서 세 규칙을 스크립트들의 구간 안
    마지막 결과와 비교함(`comparison_script_results`, `_report_on_scripts`). Status는 모두 통과일 때만 All Passing, Failing + Errors가 0인지가
    모두 통과인지와 맞아야 함(Total·Passing은 보지 않음), 실패한 스크립트는 이름이 보고서에 있어야 함. `suite_run`은 스크립트를 세지 않음
    (바꾼 코드의 테스트 모듈을 돌리지 않은 것은 그 항목이 셈). 선택 설정값 `script_results`
  - 평가 499런: 58런에서 판정 167개가 바뀜(실패에서 통과 116개: Status 53, 개수 44, `suite_run` 16, 실패 목록 3. 실패에서 해당 없음 51개:
    실패 목록), 통과에서 실패 0개


## 보상 검토 반영: tasks.md의 계획과 체크, 문서가 허용하는 다른 방식 (2026-11-21)

`tasks/2026-11-20-agentos-bugfix-reward-fixes/04-B-F-계획.md`의 문제(묶음 B·F)와 미뤄 둔 D-6 행 12·21을 하나씩 고침.
rubric의 바뀐 값은 `derive_rubric.py`가 넣음. 공용 규칙 함수에 둔 새 설정값은 기본값이 지금 동작이라 agentos_v2와 다른 워크플로의
판정은 바뀌지 않음 (예외는 그 줄에 적음).

- F-1 구현 단계의 spec.md·requirements.md 읽기 항목을 뺌(`DROP`, 2026-11-20 사용자 결정 2): 두 파일은 런이 같은 대화의 앞 단계에서 직접
  쓴 것이라 다시 여는 명령이 "분석했는가"를 알려 주지 못하고, 평가 499런 모두 실패함. 문서 29행은 그대로. 항목 수 164개에서 163개.

- F-3 결정 1의 문서 고침 (T9): implement-tasks.md 39행의 "(if any; …)"를 "(each implementation task group writes them first, as its x.1
  sub-task; …)"로 바꿈(`build.py`의 T1 항목). `derive_rubric.py`의 `REWORD`에 같은 바꿈을 넣어 그 줄을 인용하는 출처를 다시 찾음.
  판정은 바뀌지 않음.

- B-6 행 5 tasks.md의 Execution Order 절 (T10): create-tasks.md 116행에 "tasks.md는 예시의 세 절(Overview와 Total Tasks 줄, Task List,
  Execution Order)을 남긴다"는 문장을 더함(`build.py`의 `_KEEP_SECTIONS`). 절 항목(`create_tasks.tasks.section_present.execution_order`)의
  출처에 이 문장을 더함(`derive_rubric.py`의 `KEEP_SECTIONS_QUOTE`, 문장이 없으면 derive가 멈춤). create-tasks.md가 두 줄 늘어
  그 뒤를 인용하는 출처의 줄 번호가 밀림. 저장된 평가 499런의 판정은 바뀌지 않음.

- B-2 create-tasks 단계의 tasks.md 형식 항목 9개(절 둘, 줄 형식 다섯, 잔재 둘)가 런 끝이 아니라 create-tasks가 끝났을 때의 tasks.md를 읽음
  (T3 때 바꾼 `total`·`group_parts`·`test_first`와 같게). 구현 단계에서 task를 더하거나 줄을 고친 것은 `later_edits` 한 곳에서만 판정됨.
  `artifact_exists`(단계 점수를 0으로 만드는 존재 항목)는 런 끝 그대로. 평가 499런: 14런에서 판정 17개가 실패에서 통과(체크박스 줄 10,
  Execution Order 3, 하위 task 2, 그룹 제목 1, 그 결과로 순서 항목 1), 3런에서 5개가 통과에서 실패(create-tasks 끝에는 자리표시
  `[details]`가 남아 있다가 구현 중에 지운 2런, create-tasks 끝에는 형식 밖 체크박스 줄이 16개였다가 줄인 1런).

- B-4 task를 예시보다 잘게 나눈 tasks.md: 체크박스 줄 형식 항목이 `1.2.1`처럼 더 깊은 번호와, 번호 있는 task 줄 아래 들여쓴 번호 없는
  체크박스(그 task의 단계)를 형식에 맞는 줄로 봄. create-tasks.md 111 ~ 114행이 구조를 과제에 맞게 바꾸라고 하고 더 나눈 줄을 막지 않음
  (잘게 나눈 런의 해결률이 더 높았음, 카드 6-1). 맨 바깥의 번호 없는 체크박스는 그대로 형식 밖. 공용 `item_format`에 선택 설정값
  `nested_under`를 더함(없으면 지금 동작). 평가 499런: 50런이 실패에서 통과.

- B-7 그룹마다의 하위 task: 하위 task 항목(`create_tasks.tasks.item_format.subtasks`, 필수)이 파일 어디에든 `N.M` 줄이 하나 있으면 통과하던
  것을, task group마다 하위 task 줄이 있는지의 비율로 봄(create-tasks.md 26행: "groups with sub-tasks"). agentos_v2의 tasks 검사에 규칙
  `group_subtasks`를 더하고 이 항목의 kind를 바꿈(id는 그대로). 그룹마다의 Acceptance Criteria는 `group_parts`가 이미 봄.
  평가 499런: 11런이 통과에서 실패(x.0 줄만 있는 검증·문서 그룹).

- B-3 "그룹은 테스트 작성으로 시작하고 테스트 실행으로 끝남"(`test_first`, 필수)의 낱말: 문서는 예시 문구만 주고(create-tasks.md 58, 67, 77행)
  구조를 바꾸라고 하므로(111행) 넓게 읽음. 판정에서 빼는 그룹에 테스트 검증 그룹(제목에 test와 verify·validation, 또는 Verify로 시작)과
  코드 변경을 말하지 않는 문서 그룹을 더함(122행 "implementation task group"). 첫 하위 task는 "Test that …", "Extend tests …"(동사 extend·update
  추가)도 테스트 작성. 마지막 하위 task는 "Test the …"와 세부 줄에 적은 테스트 실행도 실행. 테스트 낱말에서 단수 `check`는 뺌("Add check for …"는
  코드 변경). 선택 설정값 `wide_words`. 평가 499런: 37런이 실패에서 통과, 8런이 통과에서 실패(x.1이 "Add … check …" 꼴의 코드 변경).

- B-6 행 3 Total Tasks의 셈: 문서는 "Total Tasks: [count]"만 줌(create-tasks.md 48행). 받아 주는 세 셈(task 줄 수, x.0을 뺀 줄 수, 그룹 수)에
  테스트 검토·검증 그룹을 뺀 같은 세 셈을 더함(구현 그룹만 센 런). 선택 설정값 `impl_counts`. 평가 499런: 55런이 실패에서 통과. 받는 값이
  여섯이 되어 작은 수에서 우연히 맞을 수 있음.

- F-2 자기 테스트의 형태: 문서는 자기 테스트를 checks/ 스크립트이거나 기존 저장소 테스트 모듈에 더한 테스트 함수로 쓰게 함(create-tasks.md 127행,
  core-workflow.md 85행). 준수율의 테스트 항목 셋(`checks.written`, `before_code`, `pass_last`)이 기준 커밋에 있던 테스트 모듈에 테스트 함수(`def test_…`,
  `class Test…`)를 더한 쓰기도 자기 테스트로 봄. 더한 이름은 그 호출이 넣은 글(편집기의 새 글에서 옛 글을 뺀 것, 만든 파일, `cat >> … <<EOF` 같은
  셸 명령)에서 읽고, 기존 줄을 바꾸거나 지운 쓰기(`removed_existing`)는 세지 않음. `pass_last`는 그 모듈을 고르는(경로, 위 디렉터리, 점 표기,
  전체) 변경이 제자리에 있는 유효 실행 가운데 마지막 것이 마지막 코드 변경 뒤에 있고, 실패가 없거나 실패한 테스트 id에 더한 함수 이름이 없어야
  맞음. `before_code`의 구간 끝은 첫 비테스트 최종 변경(`test_paths: false`)이 됨. 선택 설정값 `module_tests`, 공개 함수 `test_names`,
  `added_test_functions`, `module_tests`. 평가 499런: `written` 63런, `pass_last` 35런, `before_code` 7런이 실패에서 통과, 통과에서 실패 0.

- F-2 앞 단계 산출물 다시 읽기 (2026-11-20 사용자 결정 2): create-tasks의 spec.md·requirements.md 읽기 항목이, 런이 create-tasks 구간 전에
  직접 쓴(내용 쓰기) 파일은 읽은 것으로 봄(create-tasks.md 13행: 대화에 없을 때만 읽음). 쓰지 않은 파일은 읽어야 할 문서에서 뺌(D-4의 예외, 2026-11-21 사용자 결정). 읽기 규칙의
  선택 설정값 `written_before`. 평가 499런: 392런이 실패에서 통과.

- B-1과 B-8 행 2 "작업을 한 뒤에 체크했는가"(`ticked_after_work`, 필수): task 줄에서 뽑은 이름 가운데 알려진 확장자(py, rst, txt, cfg 등)로
  끝나는 것만 파일로 봄(`subprocess.run`, `content_type.save`는 코드 이름). 파일은 경로 뒤쪽이 같으면 같은 파일(`table.py`는
  `astropy/table/table.py`). 읽기 동사(Review, Analyze 등)로 시작하는 task는 그 파일을 읽은 것도 근거. 파일을 적지 않은 task는 체크 시점만 보던
  것을, 구현 단계 시작부터 체크까지 일(저장소 쓰기, checks/ 쓰기, 테스트·스크립트·인터프리터 실행)이 하나라도 있어야 통과하게 함.
  내용을 모르는 tasks.md 쓰기 뒤에 처음 보인 체크는 그 체크가 있었을 수 있는 가장 이른 단계까지의 근거를 봄(`tick_bounds`). 선택 설정값
  `name_files`, 공개 이름 `FILE_EXT`, `READ_VERB`, `named_files`, `file_evidence_steps`, `work_steps`, `tick_bounds`.
  평가 499런: 204런이 실패에서 통과, 1런(django__django-13449: 코드를 모두 구현 단계 전에 고치고 구현 단계에서 체크만 함)이 통과에서 실패.

- B-8 행 3 그룹마다 한 번의 구현 (`groups_in_order`, 필수): 이웃한 두 그룹의 체크 순서만 보던 것을, 앞 그룹의 마지막 체크 뒤부터 다음 그룹의
  마지막 `[x]` 체크까지 일(저장소·checks/ 쓰기, 테스트·스크립트·인터프리터 실행)이 하나라도 있어야 그 쌍이 맞게 함(implement-tasks.md 25행
  "one task group per pass of PHASE 2", 46행). 구현을 모두 끝낸 뒤 그룹 체크만 이어 쓴 런이 잡힘. 다음 그룹이 모두 ⚠️(구현하지 않았다고
  표시)이면 일은 묻지 않음. 선택 설정값 `work_between`. 평가 499런: 47런이 통과에서 실패.

- B-8 행 1 테스트를 돌리지 않고 체크한 테스트 하위 task (`ticked_passing`, agentos_bugfix 전용 규칙): 테스트 하위 task마다 그 체크 전의
  마지막 코드 변경(그룹 구간이 아니라 구현 단계 전체에서) 뒤부터 체크까지의 테스트 결과를 봄. 결과가 하나도 없는데 그 하위 task의 문구가
  테스트 실행을 말하면(B-3과 같은 판별) 틀린 체크로 셈(implement-tasks.md 40행). 전에는 그런 그룹이 판정에서 빠졌음. 같은 호출 안에서 고치고
  돌린 실행(`sed -i … && pytest`)은 변경 뒤의 결과로 셈(H-6의 `after_write_same_call`). 보고서의 테스트 결과에 실패가 적혀 있으면 봐주는 예외는
  실패 결과 위의 체크에만 적용하고, 결과 없는 체크에는 적용하지 않음. 새 함수 `timed_results`. 평가 499런: 100런이 해당 없음에서 실패,
  36런이 통과에서 실패. 뒤이어 "마지막 코드 변경"을 최종 변경의 모든 쓰기가 아니라 소스 변경(`facts.source_change_steps`: 테스트 파일,
  문서(CHANGES.rst), 실행이 남긴 부산물(.fits), 런의 스크립트 제외)으로 좁힘. 평가 499런: 5런이 실패에서 통과, 다른 판정 변화 0.

- B-8 행 13 구현 중 tasks.md에 더한 줄 (`later_edits`의 `additions` 갈래, agentos_bugfix만 켬): 있던 줄이 모두 순서대로 남으면 무엇을 더해도
  통과하던 것을, 더한 줄이 task 목록의 줄일 때만 통과하게 함(implement-tasks.md 25행: 빠진 것은 "new sub-task" 또는 "new task group at the
  end"로 더함). 받는 줄은 빈 줄, `Total Tasks` 줄, task 줄, `Task Group` 머리글, 더한 task 줄이나 머리글 바로 뒤에 이어 더한 줄(세부 글머리,
  Dependencies, Acceptance Criteria), Execution Order 절의 번호 줄. 있던 task 밑에 붙인 메모, 상태 절, 요약은 "adds lines that are no task"로
  나쁜 쓰기. 비교할 쓰기 고르기(H-9 `_known_before`)는 그대로. 새 함수 `added_lines_ok`, 설정값은 이미 있던 `additions`.
  평가 499런: 4런이 통과에서 실패(django__django-11066, django__django-13315, django__django-16429, psf__requests-1142), 이미 실패였던 8런의
  비율이 낮아짐. 카드의 6런 가운데 2런(matplotlib__matplotlib-23314, psf__requests-5414)은 새 하위 task 줄과 그 세부 줄을 더한 것이라 통과로 남음.

- B-5 ⚠️ 표시의 두 뜻과 열린 task의 보고: (1) `warned_after_attempts`(agentos_bugfix 전용 규칙)는 ⚠️를 단 테스트 하위 task마다 두 번의 실패와
  그 사이의 수정을 요구했음. 이제 그 그룹 구간에 첫 코드 변경 뒤의 실패한 테스트 결과가 하나도 없으면 그 ⚠️는 "테스트가 통과하지 못해 단
  ⚠️"(implement-tasks.md 40행)가 아니라 "미완료로 드러난 task의 ⚠️"(127행)로 보고 이 규칙의 대상에서 뺌. 실패가 하나라도 있으면 전처럼
  두 번의 시도를 물음(A-5의 "고쳐 보지 않고 바로 ⚠️"는 계속 실패, 자체 점검의 `warn_no_attempt`도 실패 그대로). (2) `incomplete_listed`는
  ⚠️ task가 있을 때만 판정했음. 선택 설정값 `open_tasks`(agentos_bugfix만 켬)를 켜면 체크되지 않은 task(체크박스가 있는 줄)도 미완료로 보고,
  그런 task가 있는데 Incomplete or Issues 절이 "None"이면 실패(127행). 체크박스 없는 글머리("- 0.009125 formats as …")는 열린 task로 보지
  않음. 평가 499런: `incomplete_listed` 38런이 해당 없음에서 실패, 6런이 해당 없음에서 통과. `warned_after_attempts` 1런
  (sphinx-doc__sphinx-8459: 모든 변경을 `git checkout`으로 되돌린 뒤 모든 task에 ⚠️)이 실패에서 해당 없음.
  2026-11-21 덧붙임 (사용자 결정): (1)의 ⚠️가 127행의 표시로 빠지려면 실패 결과가 없을 뿐 아니라 그 ⚠️가 PHASE 3에서, 또는 PHASE 3을 여는
  쓰기(모든 task가 처음 체크나 ⚠️로 보이는 쓰기, `phase3_start`)에서 처음 나타나야 함. 그보다 앞서 나타난 ⚠️는 실패 결과가 없어도 40행의 표시로
  보아 시도를 묻고 실패함(⚠️가 처음 나타난 단계를 모르면 실패 결과 조건만 봄). 평가 499런: 판정 변화 0(⚠️가 있는 런이 2개뿐이고 sphinx-doc__sphinx-8459의
  ⚠️는 PHASE 3을 여는 155단계 쓰기에서 처음 나타나 해당 없음 그대로).
  2026-11-21 보강: PHASE 3을 여는 쓰기는 그 쓰기 하나만이 아니라, 그 바로 앞의 tasks.md 쓰기들 가운데 사이에 작업(저장소 쓰기, checks/ 쓰기,
  테스트나 스크립트 실행)이 없는 것까지 함께 봄(`_phase3_opening`). 미완료 task의 ⚠️를 한 줄씩 나눠 적은 런이 한 번에 적은 런과 같은 판정을
  받게 함(`warned_after_attempts`와 `ticked_after_work`의 `not_done_out`이 같이 씀). 평가 499런: 판정 변화 0.
  2026-11-21 덧붙임 (사용자 결정): `ticked_after_work`는 선택 설정값 `not_done_out`(agentos_bugfix만 켬)을 켜면 위와 같은 정의로 127행의
  "미완료로 드러난 task" ⚠️를 단 task(새 함수 `found_not_done`)를 작업 근거를 묻는 대상에서 뺌. 실패 결과가 있는 그룹의 ⚠️(40행)는 전처럼 판정.
  평가 499런: 판정 변화 0(그런 task가 있는 런은 sphinx-doc__sphinx-8459 하나이고, 빼기 전에도 아홉 task 모두 작업 근거가 있어 통과).
  2026-11-21 덧붙임 (사용자 결정): 보고서의 `tasks_status`도 `open_tasks`(agentos_bugfix만 켬)를 켜면 `incomplete_listed`와 같이 체크박스가 있는
  줄 가운데 체크하지 않은 것과 ⚠️를 단 것만 열린 task로 셈. 평가 499런: astropy__astropy-14508(모든 task 체크, 체크박스 없는 글머리
  "- 0.009125 formats as …") 한 런이 실패에서 통과, 그 밖의 판정 변화 0.

- F-3 행 14 `git checkout`으로 변경을 치우고 돌린 테스트 (공용 `workflow_rubric/results.py`): "변경이 치워진 상태"는 `git stash`(push 꼴)부터
  `pop`·`apply` 또는 다음 저장소 편집까지였음. 이제 `git checkout [<rev>] [--] <경로>`와 `git restore [--source=…] <경로>`도 그 경로 가운데
  하나가 런이 직접 편집한 테스트 아닌 저장소 파일이거나 그 위 폴더(`.` 포함)일 때 치우는 표시로 셈(implement-tasks.md 135행은 `git stash`를
  변경 없이 테스트를 돌리는 한 예로 듦). 브랜치 전환(`-b`, `-B`, `--orphan`, `--detach`, `-`)과 `git restore --staged`(작업 사본은 그대로)는
  세지 않음. 계획은 "최종 변경의 소스 경로"였으나 checkout으로 버린 파일이 최종 변경에 남지 않을 수 있어 편집한 파일로 함. `stash_marks`와
  `stash_states`의 선택 인자 `checkout_paths`(기본값 없음 = 전과 같음)를 agentos_v2의 `change_runs`(agentos_v2와 agentos_bugfix 공용)와
  penalty의 `penalty_tests`가 넘김(새 함수 `checks.edited_sources`). 평가 499런: scikit-learn__scikit-learn-13124 한 런에서
  `phase3_fail.cause_checked` 실패에서 통과(72단계 checkout, 78단계에 실패하던 테스트를 옛 코드로 돌림), 같은 런의
  `phase3_fail.edited_after_fail` 해당 없음에서 통과(옛 코드에서 통과했으므로 변경이 고칠 실패가 됨). penalty 평균 0.59719에서 0.59738.
  저장된 agentos_v2 평가 499런의 재채점: 판정 변화 0.

- F-3 행 16 검증 단계의 정리 (`_phase3_edits`, `code_frozen`의 `fix_round` 갈래만 씀, agentos_bugfix만): PHASE 3이 시작된 뒤의 저장소 쓰기는
  모두 코드 변경으로 셌음. 이제 런이 만든 파일(`facts.is_new_path`)이고 최종 변경에 남지 않은 경로를 지우는 쓰기(op `delete`, `move_out`)는
  정리로 보고 세지 않음(core-workflow.md 88 ~ 89행: 워크플로의 것은 저장소에 두지 않음). 저장소에 파일을 만든 것은 전처럼 `created_files`
  항목이 잡음. 평가 499런: django__django-13569(54단계에 자기가 만든 tests/test_fix.py를 지움) 한 런의 `code_frozen`이 실패에서 통과, 다른 판정 변화 0.

- D-6 행 12 그룹마다 테스트를 먼저 (`before_code`, 필수): 구현 단계의 첫 코드 변경 전에 자기 테스트가 하나라도 있으면 통과였음. 이제 그 조건을
  통과한 런에서 task group 구간마다 더 봄(create-tasks.md 126행 "each task group starts with writing 2-8 tests (x.1 sub-task)", implement-tasks.md
  39행). 그룹 끝은 최종 tasks.md에서 그 그룹의 마지막 하위 task(x.0 제외)가 체크된 단계, 구간은 앞 그룹 끝 다음부터 이 그룹 끝까지(첫 그룹은 구현
  단계 시작부터, 마지막 그룹 끝 뒤는 보지 않음). 소스 변경(`facts.source_change_steps`)이 있는 구간마다 그 구간의 첫 소스 변경 전에, 같은 구간
  안에 자기 테스트의 첫 쓰기(checks/ 스크립트의 첫 쓰기, F-2의 기존 테스트 모듈에 더한 첫 함수)가 있어야 함. 그룹 끝을 하나도 모르면 전의 규칙만 씀.
  점수는 통과 또는 실패. 선택 설정값 `per_group`, 새 함수 `group_end_steps`(penalty의 `_group_ends`가 이것을 부름, 같은 값), `own_test_first_writes`.
  평가 499런: 12런(해결한 런 5)이 통과에서 실패. 묶음 D 계획의 시험 채점(`dg/rescore_d6_groups.jsonl`)이 낸 12런과 같은 런들임. penalty 변화 0.

- D-6 행 21 판정 없는 탐색 스크립트 (`before_code`만): checks/ 아래에 쓴 스크립트는 내용과 상관없이 자기 테스트로 셌음. 이제 마지막으로 아는
  내용에 판정 구문(`assert`, `raise`, `sys.exit(`, 0 아닌 `exit(`, `unittest`, `pytest`, `def test_`, PASS·FAIL·OK 출력)이 있을 때만 셈
  (implement-tasks.md 39행 "ensuring they pass": 통과·실패가 나올 수 있어야 테스트). 내용을 모르는 스크립트는 셈. 그룹별 판정(행 12)의 첫 쓰기에도
  같은 기준을 씀. 선택 설정값 `verdict`(`checks.written`·`pass_last`에는 켜지 않음), 새 함수 `has_verdict`. 평가 499런:
  matplotlib__matplotlib-21568 한 런이 통과에서 실패(checks/ 스크립트 test_datetime_spacing.py가 값을 출력만 함). 이 런의 implement_tasks 단계
  점수는 이미 0이라 준수율은 그대로.

- D-6 행 12 보강: 그룹별 판정이 기존 테스트 모듈에 대해서는 모듈마다 첫 함수 추가만 "테스트를 처음 쓴 기록"으로 셌음. 그래서 그룹 2가 그룹 1이
  쓴 모듈에 자기 테스트 함수를 더하는 F-2의 문서 허용 형태가 실패했음(가짜 런 `branches_implement.py` 분기 지점 5·20·22의 "기존 테스트 모듈에 함수로
  추가함" 준수율 0.9893). 함수 하나하나가 자기 테스트이므로, 전에 더하지 않은 이름의 테스트 함수를 더한 쓰기마다 그 테스트의 첫 쓰기로 셈.
  checks/ 스크립트는 그대로 스크립트마다 첫 쓰기. 평가 499런: 판정 변화 0. 그 가짜 런 선택지는 준수율 1.0이 됨.

## 보상 검토 반영: 테스트 실패 다루기와 계획한 파일 (2026-11-21)

`tasks/2026-11-20-agentos-bugfix-reward-fixes/05-A-C-계획.md`의 문제(묶음 A·C)를 하나씩 고침. rubric의 바뀐 값은 `derive_rubric.py`가 넣고,
문서는 `build.py`로 다시 만듦. 공용 규칙 함수에 둔 새 설정값은 기본값이 지금 동작이라 agentos_v2와 다른 워크플로의 판정은 바뀌지 않음
(예외는 그 줄에 적음). 평가 499런의 수는 커밋마다 다시 채점해 바로 앞 커밋과 비교한 값임.

- A-6 자기 테스트를 고치는 것 (T11): implement-tasks.md 40행 끝에 "자기 테스트는 과제가 묻지 않는 것을 확인할 때만 틀린 것이고, 그때는 확인하는
  것을 바로잡는다. 확인을 느슨하게 하거나 지워서 실패하는 테스트를 통과시키지 않는다"를 더함(`build.py`의 implement-tasks 항목). 규칙은 바꾸지
  않음. 40행 앞 두 문장을 인용하는 출처(`_T5_FIX`, `_T5_WARN`)는 그대로 찾아짐. 평가 499런: 판정 변화 0.

- C-2 정답 패치를 보는 penalty 항목 둘을 뺌 (`plan_files.named_covers_gold`, `plan_files.patch_covers_gold`): 두 항목은 과제의 정답 패치(에이전트가 볼 수
  없는 것)를 기준으로 판정해, 바꾼 파일을 그대로 적고 고쳤어도 정답 패치가 다른 파일을 고쳤으면 실패했음(카드 1-6). 항목 안에서 고칠 수 없어 뺌.
  `penalty.py`에서 정답 패치 읽기(`gold_patch`, `patch_files`)와 `penalty_gold_unknown` 신호를 지움. `inputs`는 과제를 `task_text.py`(E-1)에 넘기므로
  그대로 둠. penalty 항목은 11개에서 9개(파일 2, 테스트 7)가 되어, penalty 가중치 0.3에서 항목 하나의 보상 크기가 0.3 × 1/11 = 0.0273에서
  0.3 × 1/9 = 0.0333이 됨. 파일 항목의 무게는 penalty 점수의 4/11에서 2/9로, 테스트 항목은 7/11에서 7/9로 바뀜. 평가 499런: 두 항목의 판정 998개가
  없어짐(통과였던 것 617개, 실패였던 것 381개). 다른 항목의 판정 변화 0. penalty 점수 평균 0.59738에서 0.59274 (점수가 바뀐 런 479개).

- C-1 계획한 파일 (`plan_files.named`, `plan_files.named_equals_patch`): 전에는 tasks.md의 모든 판에서 테스트가 아닌 task와 그 아래 줄(세부 줄,
  "Reuse pattern from" 줄, N.0 줄)에서 소스 파일 이름(맨 이름, 점 표기 모듈 이름 포함)을 모아, 하나라도 있으면 `named` 통과였음. 이제
  create-tasks.md 119행("every sub-task that changes code names, on its task line, the path in the repository of the file it changes")대로 읽음:
  런이 남긴 마지막 tasks.md에서 x.y 번호(x.0이 아님, x.y.z는 x.y의 단계)의 task 줄 가운데 테스트 작업(쓰기·실행·검토)이 아니고 읽기·확인 동사
  (B-1의 `READ_VERB`와 verify, confirm, check, ensure, validate, test, run)로 시작하지 않는 줄이 코드를 바꾸는 하위 task. 이름은 그 줄에서만 뽑고,
  `/`가 있고 끝 부분에 확장자가 있는 토큰이거나 저장소 최상위 파일(런이 쓴 것, 최종 변경에 있는 것)의 맨 이름만 경로로 셈. 점 표기 모듈 이름은
  세지 않음. 테스트 작업 판별은 줄의 경로를 지운 뒤에 함("Run tests in foo.py"의 마침표가 `[^.]*`를 끊던 것). `named`는 그런 줄이 하나 이상이고
  모든 줄이 경로를 하나 이상 적어야 통과(줄마다 확장자는 묻지 않음), `named_equals_patch`는 그 이름 중 소스 파일과 최종 변경의 소스 파일이 같아야
  통과. 이름이 처음 나온 판과 늦은 이름(파일을 고친 뒤 처음 적은 이름) 판정은 전과 같음. 새 함수 `change_lines`, `line_paths`. 평가 499런: `named`
  288런이 통과에서 실패(해결 152), `named_equals_patch` 160런이 통과에서 실패(해결 91)와 15런이 실패에서 통과("Reuse pattern from" 줄의 파일을
  더는 세지 않음). `named` 통과는 340런에서 52런. 평가 런은 119행 문장(2026-11-18에 들어감)을 받지 않았으므로 이 수는 위반 건수가 아님.

- R1 실패 단위 (공용 `workflow_rubric/results.py`, 새 함수만): 실패한 결과가 남기는 "다시 통과해야 할 것"을 테스트 하나하나로 셈. 유효한 러너 실행의
  출력이 실패한 테스트 id를 실패·오류 수만큼 이상 적으면 id마다 단위(`run_failed_ids`: pytest 실패 구역 머리 줄의 맨 이름 `test_x[png]`은 같은 끝
  이름의 온전한 id가 있으면 버림), 아니면 지금처럼 파일마다, 스크립트는 그 경로(`failure_units`). 통과가 테스트 단위를 지우는 조건은 그 테스트를
  돌린 유효 러너 실행일 것(`runs_test`: 대상이 그 테스트를 덮고, `file::test` id·`-k`(낱말 포함으로 계산, 못 읽으면 뺀 것)·`--deselect`·`--ignore`가
  그 테스트를 빼지 않으며, `-m`은 뺀 것으로 봄). 파일 단위는 지금 규칙(`clears`). `standing_units`는 단위마다 실패한 실행을 모두 들고 있어, 파일
  전체의 실패 뒤에 좁힌 실패와 좁힌 통과가 와도 앞의 넓은 실패가 지워지지 않음. `TestResult`에 칸 `failed_ids`(기본 빈 값). 기존
  `standing_failures`는 그대로라 openspec_ff와 다른 워크플로는 바뀌지 않음. 이 커밋만으로는 판정 변화 0 (평가 499런).

- A-9 행 8 (R3) checks/ 밖 스크립트 (`penalty_tests.py`의 `timeline`): 런이 쓴 스크립트는 checks/ 밖(저장소 최상위, /tmp)이어도 실행 결과를
  테스트 결과로, 쓰기를 테스트 편집으로 셌음(저장소를 고치는 스크립트만 뺐음). 이제 결과와 테스트 편집에는 spec 폴더 checks/ 아래 스크립트와 저장소
  테스트 파일만 넣음. 자기 테스트의 자리는 checks/ 스크립트이거나 기존 테스트 모듈에 더한 함수임(core-workflow.md 85 ~ 89행, create-tasks.md 127행).
  쓸 데가 없어진 `fix_scripts`와 `_WRITES_FILES`를 지움. 평가 499런 (penalty 항목, 해당 없음을 1점·0점으로 나눠 셈): 검증 단계 `cause_checked`
  17런, `edited_after_fail`·`last_result_pass` 각 14런이 해당 없음 1점에서 0점(남은 결과가 없어 최종 코드를 테스트하지 않은 것이 됨), 구현 단계
  `edited_after_fail`·`last_result_pass` 각 14런이 실패·통과·해당 없음 1점에서 해당 없음 0점, `last_result_pass` 4런과 `edited_after_fail` 1런이
  실패에서 통과, 각 3런이 실패에서 해당 없음 1점, `edited_after_fail` 구현 단계 2런과 검증 단계 1런이 통과에서 실패(실패 뒤의 편집이 /tmp의 테스트
  스크립트 쓰기뿐이었음). 대부분 django 런(저장소 밖 스크립트로 확인함). 준수율 변화 0, penalty 점수 평균 0.49633에서 0.48475.

- A-9 행 20 기존 테스트 실행 (`penalty_tests.py`의 `existing_runs`, `phase2_run`·`phase3_run`의 "기존 테스트 실행"): 변경을 치우지 않은 유효
  러너 실행은 모두 저장소의 기존 테스트 실행으로 셌음. 이제 런이 쓴 테스트만 고른 실행은 빼고 자기 테스트 실행으로만 셈: 이름한 파일이 모두
  `file::name` id로 이름되고 그 이름이 모두 런이 기존 모듈에 더한 테스트 함수·클래스(F-2의 `module_tests`)인 실행, 또는 이름한 파일이 모두 런이 만든
  테스트 파일(`facts.is_new_path`)인 실행. implement-tasks.md 39행 "the existing tests of the code you changed". 새 함수 `only_own_tests`. `-k`로 고른
  실행은 보지 않음. 평가 499런: astropy__astropy-13398 한 런의 `phase2_run.existing_and_own`이 통과에서 실패(구현 단계의 실행이 모두 런이 더한 함수의
  id만 고름). 준수율 변화 0.

- R2와 A-3 문서가 고치라고 하지 않는 실패 (`agentos_v2/reward/checks.py`의 새 함수 `excused_failures`, agentos_v2의 rubric은 쓰지 않음; `penalty_tests.py`):
  penalty의 실패 항목 넷(구현 단계 `edited_after_fail`·`last_result_pass`, 검증 단계 `edited_after_fail`·`last_result_pass`)은 모든 실패를 고칠 대상으로
  봤음. 이제 두 가지 실패 단위(R1)를 뺌. (1) 과제가 바꾸라는 동작을 단언하는 기존 테스트(implement-tasks.md 39행, 137행): 러너 실행의 테스트 단위이고,
  런이 만든 테스트 파일도 런이 더한 테스트 함수도 아니며, 최종 보고서의 Failed Tests 절에 그 이름이 있고 그 줄이나 Notes에서 그 이름·파일을 담은
  문단이 "옛 동작을 단언함"을 말함(`EXPECTED_WORDS`의 네 문구, `reported_as_expected`). (2) 변경 없이도 실패하는 테스트(135, 138행): 변경을 치운
  유효 러너 실행(`stashed_results`)이 그 테스트를 실패 id로 냈거나 그 파일을 돌려 실패함. 시점은 보지 않음. 실패 단위가 모두 빠진 결과는 네 항목에서
  실패가 아니고, 빼고 나서 실패가 없으면 해당 없음(테스트를 돌렸으므로 1점). `cause_checked`는 그대로(모든 러너 실패에 원인 확인을 물음). 문서도
  맞춤(T1 행): 39행 끝을 "list that test under Failed Tests in the final verification report, noting that it is an expected failure (it asserts
  the behavior the task asks to change)."로 바꿔(`build.py`; `derive_rubric.py`의 `_T1_EXPECTED`와 `REWORD`), 문서대로 쓴 보고서가 늘 셋째 문구에
  맞게 함. 새 함수 `runner_result`, `stashed_results`, `reported_as_expected`. 기준 런의 `expected_failure` 변형의 penalty가 0.5556에서 1.0.
  평가 499런: 14런. 구현 단계 `edited_after_fail` 6런·`last_result_pass` 5런이 실패에서 통과, 각 5런이 실패에서 해당 없음 1점, 각 1런이 실패에서
  해당 없음 0점(django__django-15037: 남은 결과가 없음), 검증 단계 `last_result_pass` 3런이 실패에서 해당 없음 1점, 1런이 통과에서 해당 없음 1점.
  빠진 단위는 22런의 47개(변경을 치운 실행으로 41개, 보고서의 말로 6개: django__django-15315, matplotlib__matplotlib-22871, pylint-dev__pylint-4661,
  scikit-learn__scikit-learn-26194. 넷 다 보고서가 그 테스트를 옛 동작이나 버그를 단언한다고 적음). 준수율 변화 0, penalty 점수 평균 0.48452에서 0.48987.

- A-4와 A-9 행 7 실패 뒤의 시도 (`phase2_fail.edited_after_fail`): task group 구간마다 "마지막 실패 결과 뒤, 체크 전에 편집이 있음"을 봤음. 그래서
  문서대로 두 번 고쳐 보고 ⚠️로 넘어간 런은 마지막 실패 뒤 편집이 없어 실패하고, ⚠️ 직전의 뜻 없는 편집 하나로 되찾았음. 이제 구간마다, 그 구간의
  첫 소스 변경 뒤에 실패한 실패 단위(R1, R2로 빠진 것 제외)마다 시도 수를 셈: 그 단위의 실패한 결과 뒤, 그 단위의 다음 결과 전에 편집(소스 변경이나
  테스트 편집)이 있고 다음 결과가 그 구간 안에 있는 것. 같은 호출 안에서 고치고 돌린 실행은 편집 뒤의 결과(H-6, checks/ 스크립트는 명령 글에서 쓴 경로가
  스크립트 경로보다 앞에 있으면). 단위가 맞으려면 시도가 2번 이하이고, 구간 안에서 다시 통과했거나 시도가 1번 이상(implement-tasks.md 40행 "fix ... and
  run the tests again ... After two attempts that do not get it to pass, mark ... ⚠️ ... and go on"). 그룹의 첫 소스 변경 전의 실패(먼저 쓴 테스트가
  코드보다 먼저 실패하는 것)는 고칠 실패가 아님(`warned_groups`와 같음). 새 함수 `outcome_for`, `attempts`, `_attempts_ok`, `_stretches`.
  평가 499런: 101런이 통과에서 실패(해결 46; 시도 3번 이상인 단위가 있는 런 83, 편집 뒤 다시 돌리지 않은 단위가 있는 런 21, 겹침 있음; 시도 3번 이상
  단위 101개 가운데 63개가 checks/ 스크립트), 9런이 실패에서 통과(해결 7). 기준 런의 `warn_attempts`·`script_failing` 변형이 이 항목을 지킴.
  2026-11-21 사용자 결정: 시도 상한을 두 번에서 다섯 번으로 올림(여섯 번째 시도가 실패). 문서 40행을 "Make up to five attempts. If it still does not
  pass, mark ... ⚠️ ... and go on; do not make a sixth attempt."로 바꾸고, `penalty_tests.py`의 상한은 상수 `MAX_ATTEMPTS = 5`. ⚠️ 전의 최소 시도
  (한 번)와 `warned_groups`의 "두 실패 결과와 그 사이의 시도"는 그대로. 자체 점검에 DISHONEST `warn_six_attempts`(여섯 번 시도 뒤 ⚠️)를 더함.
  평가 499런: 이 항목에서 65런이 실패에서 통과(해결 31). 그 밖의 판정 변화 0, 준수율 변화 0.

- A-9 행 17 그룹 안에서 다시 통과 (`phase2_fail.last_result_pass`): 구현 단계 전체에서 실패한 테스트가 뒤에 다시 통과했는지만 봤음. 그래서 앞 그룹의
  실패를 남긴 채 그 그룹을 체크하고 뒤 그룹에서 통과시켜도 지켰음. 이제 task group 구간마다, 그 구간에서 실패한 것(R2로 빠진 것 제외)이 그 구간이
  끝나기 전에 다시 통과하거나, 그 구간을 끝낸 그룹의 task 줄에 ⚠️가 있어야 함(implement-tasks.md 40행: 체크 전에 고쳐 다시 돌리고, 두 번 해도 안 되면
  ⚠️). 한 쓰기로 모든 그룹을 체크한 런은 구간이 하나. 새 함수 `checks.group_end_marks`(그룹 끝 단계마다 ⚠️ 여부, 공용 파일에 더하나 agentos_v2는 쓰지
  않음), `Timeline.group_marked`. 평가 499런: 4런이 통과에서 실패(django__django-11239, django__django-12155, matplotlib__matplotlib-20826,
  pytest-dev__pytest-10356; 해결 2). 기준 런 `warn_attempts`가 이 항목을 지킴.

- A-7 행 8과 A-2(구현 단계 penalty) 실패한 테스트의 재통과 (`phase2_fail.last_result_pass`): 실패를 파일 단위로 보고, 실패한 실행과 같은 범위이거나
  범위를 좁히지 않은 통과만 그 실패를 지웠음(같은 파일의 실패가 다시 나오면 앞 실패의 범위를 덮어씀). 이제 R1의 실패 단위로 판정함(`standing_units`):
  출력이 실패한 테스트를 모두 적었으면 테스트마다, 그 테스트를 돌린 유효 러너 실행의 통과가 지움. 실패한 테스트를 `file::test`나 `-k`로 골라 다시 돌린
  통과는 지우고, `--deselect`·`-k "not …"`·`--ignore`·`-m`으로 뺀 통과는 지우지 않음. 파일 단위는 실패한 실행을 모두 들고 있어 넓은 실패를 좁힌 실패와
  통과가 지우지 못함. R2로 빠진 단위는 보지 않음. 평가 499런: astropy__astropy-13236 한 런이 통과에서 실패(57단계 파일 전체 실행에서
  `test_skycoord_representation`이 실패하고, 뒤의 통과는 `::test_ndarray_mixin`만 고른 실행). 앞 task의 행 8 목록(실패한 테스트와 다른 테스트를
  고르거나 `-k "not …"`로 뺀 실행이 대부분)의 런 가운데 이 커밋에서 통과로 바뀐 것은 없음.

- A-1과 A-2(검증 단계 penalty) 검증 단계의 실패 (`phase3_fail.last_result_pass`): 검증 단계에 실패가 있으면 보고서 전 마지막 결과 하나가 통과인지만
  봤음. 그래서 같은 일을 하고 같은 보고를 해도 전체 테스트를 마지막에 돌리면 잃고, 자기 테스트를 마지막에 돌리면 지켰음. 이제 검증 단계의 실패 단위(R1,
  R2로 빠진 것 제외)마다 봄: 보고서 전에 그 단위를 지우는 통과(`clears`: 그 테스트를 돌린 실행, 뺀 실행은 아님)가 있거나, 변경 탓인 실패(A-9 행 22의
  정의: 자기 테스트, 또는 변경을 치운 실행에서 통과한 테스트)이고 첫 실패 뒤에 고침(소스 변경, 자기 테스트는 그 테스트의 편집도)이 있고 마지막 고침 뒤에
  그 단위를 돌린 결과(통과든 실패든)가 있으면 맞음(implement-tasks.md 137행: 한 번 돌아가 고치고 PHASE 3을 다시 함, 남은 실패는 보고서에 적음).
  모두 맞으면 1.0. 원인 확인을 하지 않은 실패는 R2에 들지 않아 남음. 새 함수 `own_test`, `change_caused`, `fix_edits`, `_p3_left_right`. 기준 런
  `warn_attempts`의 penalty가 1.0이 됨. 평가 499런: 12런이 통과에서 실패(해결 6; 마지막 결과는 통과였으나 앞의 실패가 남은 런. 예:
  django__django-11815는 39단계 `tests/migrations` 실패를 원인 확인도 재실행도 하지 않고 58단계 자기 스크립트 통과로 끝냄).

- A-9 행 22 변경 탓인 실패를 고침 (`phase3_fail.edited_after_fail`): 검증 단계에 러너 실패가 있으면 변경을 치운 실행이 모두 통과할 때만 판정했고, 첫
  실패 뒤 아무 편집(소스든 테스트든)이 있으면 지켰음. 그래서 변경 탓인 실패와 원래 있던 실패가 섞이면 판정하지 않았음. 이제 실패 단위마다 원인을 봄:
  변경 탓인 단위(R2가 아니고, 자기 테스트(checks/ 스크립트, 런이 만든 테스트 파일, 런이 더한 테스트 함수)이거나 변경을 치운 유효 러너 실행이 그 단위를
  돌려 통과한 것)가 하나라도 있으면 판정하고, 단위마다 첫 실패 뒤 보고서 전에 고침이 있어야 함. 기존 테스트는 소스 변경만(implement-tasks.md 137행 "fix
  the change"), 자기 테스트는 소스 변경이나 그 테스트의 편집(40행). 변경 탓인 단위가 없으면 해당 없음. 평가 499런: 해당 없음 1점에서 통과 4런, 통과에서
  실패 2런(astropy__astropy-13236: 변경 탓인 기존 테스트 실패 뒤 테스트 파일만 고침; django__django-13658: 실패한 자기 스크립트를 고치지 않고 다른
  스크립트만 고침), 해당 없음 1점에서 실패 1런, 실패에서 해당 없음 1점 1런.

- A-2 보고서의 All Passing (`implement_tasks.final_verification.agentos_bugfix_report.suite_status`, 공용 `report` 규칙의 선택 설정값 `standing`,
  agentos_bugfix만 켬): Status가 All Passing이면 보고서와 개수가 가장 잘 맞는 실행 하나에 실패가 없는지만 봤음. 그래서 실패한 테스트를 빼고
  (`--deselect`, `-k "not …"`) 다시 돌린 통과를 내세워 All Passing으로 적어도 맞았음. 이제 그에 더해 검증 단계 러너 실행(고침 뒤의 것, 변경을 치운
  실행 제외)의 실패 단위(R1)가 모두 다시 통과했어야 함(implement-tasks.md 133행: 보고서의 실패 목록과 상태). Some Failures·Critical Failures 갈래와
  `test_counts`는 그대로. 평가 499런: 12런이 통과에서 실패(해결 6). 예: astropy__astropy-8707(69단계 `-k card`의 실패를 다시 돌리지 않음),
  matplotlib__matplotlib-24149(56단계 `test_cbook.py`의 18개 실패를 `-k safe_first_finite or flatiter`로만 다시 돌림).

- A-7 행 7 보고서의 Failed Tests (`implement_tasks.final_verification.agentos_bugfix_report.failed_listed`, `report`의 선택 설정값 `standing`,
  agentos_bugfix만 켬): 검증 단계에서 실패한 실행 가운데 마지막 것 하나의 실패 id와만 대조했음. 이제 검증 단계 러너 실행 전체의 실패 단위(R1) 가운데
  고친 뒤 다시 통과하지 않은 것을 모두 적어야 함(implement-tasks.md 133행). "고친 뒤 다시 통과"는 실패 뒤 저장소나 checks/ 스크립트에 쓰기가 있고 그
  뒤의 통과가 그 단위를 지움(`clears`). 아무것도 바꾸지 않고 다시 돌려 통과한 실패(흔들리는 테스트)는 실패한 테스트로 적어야 함. 남은 것이 없으면
  해당 없음, id를 읽지 못한 실패만 남았으면 Failed Tests 절에 무엇이든 적혀 있으면 통과. 새 함수 `_left_unfixed`. 계획은 "남은 실패"(standing)만
  말했으나 그대로 넣으면 자체 점검 변이 `hidden_failure`(마지막 실행 직전에 같은 명령이 한 번 실패하고 다시 돌린 통과가 뒤따름)를 잡는 항목이 없어져
  자체 점검이 실패함. 고친 실패를 적지 않아도 된다는 계획의 뜻은 그대로 두고 고치지 않은 실패는 적게 함. `test_counts`는 그대로. 평가 499런:
  matplotlib__matplotlib-20488 한 런이 실패에서 통과(실패 id가 온전한 id와 pytest 실패 구역 머리 줄의 맨 이름으로 두 번 읽히던 것이 R1에서 하나로 됨).

- A-8 실패한 테스트는 Failed Tests 절에 (`failed_listed`, `report`의 선택 설정값 `in_section`, agentos_bugfix만 켬): 실패한 테스트의 이름을 보고서
  어디에서든 찾았음. 그래서 Failed Tests에 "None - all tests passing"을 적고 Notes에만 "무관한 실패"로 적은 보고서가 통과했음. 이제 Failed Tests 절
  안에서만 찾고, 그 절이 없으면 Test Suite Results 절에서 찾음(implement-tasks.md 133행, 보고서 양식 188 ~ 189행). 평가 499런: astropy__astropy-8707,
  astropy__astropy-8872 두 런이 통과에서 실패(둘 다 해결한 런). 기준 런 `suite_failures` 변형은 그대로 만점.

- A-5 실패 위의 체크 (`ticked_passing`, agentos_bugfix 전용 규칙): 테스트 하위 task를 실패 결과 위에 체크해도, 보고서의 테스트 결과에 실패가 적혀
  있으면 항목 전체를 통과로 봤음. 그래서 변경 탓인 실패 위에 체크하고 보고서에 적은 런이 문서대로 ⚠️로 표시한 런과 같은 점수였음. 이제 예외를 그룹마다
  R2로 좁힘: 체크 직전의 마지막 결과가 실패인 그룹은, 그 실패 결과의 실패 단위가 모두 문서가 고치라고 하지 않는 실패(R2: 옛 동작을 단언한다고 보고서에
  적은 기존 테스트, 변경 없이도 실패하는 테스트)일 때만 맞음. 보고서에 실패가 적혀 있다는 것만으로는 맞지 않음(implement-tasks.md 40행). 결과 없는
  체크(B-8 행 1)에는 그대로 예외가 없음. `_report_failures`는 쓸 데가 없어 지움, 새 함수 `_failing_results_at`. 평가 499런: 19런이 통과에서 실패(해결 7),
  2런이 실패에서 통과(matplotlib__matplotlib-14623, sphinx-doc__sphinx-7440: 체크 위의 실패가 변경 없이도 실패하는 테스트였는데 보고서에 적지 않아
  전에는 예외를 받지 못했음).

- R2 보강 Failed Tests의 항목: R2의 첫째(옛 동작을 단언하는 기존 테스트)가 보고서의 이유 문구를 그 테스트 이름이 있는 줄에서만 찾았음. 이유를 이름 줄
  아래에 들여 이어 적은 보고서("- `…::test_m`" 아래 "  - **Reason:** Test was asserting the buggy behavior")는 빠지지 않았음. 이제 이름 줄과 그 아래
  더 깊이 들여 쓴 줄까지를 그 항목으로 읽음(`_entries`). 평가 499런: sphinx-doc__sphinx-9698 한 런(해결)의 `ticked_passing`이 실패에서 통과,
  penalty 항목 셋이 실패에서 해당 없음 1점.

- A-9 행 9 그룹마다 테스트 (`implement_tasks.run.agentos_bugfix_verify.phase2_run`, agentos_bugfix 전용 규칙): 구현 단계의 마지막 코드 변경 뒤에 유효한
  러너 실행이 하나 있으면 통과였음. 그래서 앞 그룹은 테스트 없이 체크하고 마지막 그룹 뒤에만 한 번 돌린 런도 통과했음. 이제 그에 더해, 그룹 끝(`group_end_steps`)
  으로 자른 구간 가운데 코드 변경이 있는 그룹마다 그 그룹의 마지막 코드 변경 뒤, 다음 코드 변경 그룹의 첫 코드 변경 전(마지막 그룹은 PHASE 3 전)에 유효
  러너 실행이 있어야 함(implement-tasks.md 39 ~ 40행: 그룹의 마지막 하위 task가 테스트를 돌림). 마지막 그룹이 맞지 않으면 전처럼 실패, 맞으면 맞는 그룹 수
  ÷ 코드 변경 그룹 수. B·F 계획은 이 행을 B-8 행 1(`ticked_passing`의 결과 없음)로 처리하라고 했으나, 그 규칙은 테스트 실행을 말하는 하위 task만 보아 이
  행의 런 대부분을 잡지 못함(05 계획). 평가 499런: 18런이 통과에서 비율(실패)로(해결 9). 예: django__django-11095(27단계 그룹 1의 코드, 28단계 체크,
  30단계 그룹 2의 코드, 그 사이 테스트 없음).

- A-9 행 14 검증 단계의 고침은 한 번 (`code_frozen`의 `fix_round` 갈래, agentos_bugfix 전용): PHASE 3이 시작된 뒤의 쓰기는 앞에 실패한 실행, 뒤에 다시
  돌린 실행이 있으면 몇 번이든 받았음. 이제 그 쓰기(F-3 행 16의 정리 삭제 제외)가 테스트 결과로 나뉘지 않은 한 묶음이어야 함. 나누는 결과는 변경이
  제자리에 있는 유효 러너 실행과 checks/ 스크립트 실행(변경을 치운 원인 확인 실행은 나누지 않음). implement-tasks.md 137행 "Go back once only",
  core-workflow.md 29행. 평가 499런: 7런이 통과에서 실패(해결 0). 앞 task의 "묶음 2개 이상" 6런 가운데 5런과, django__django-16612,
  django__django-16950(검증 단계에 테스트 파일을 두 번 다시 쓰고 그 사이에 테스트를 돌림). 그 6런의 django__django-15554는 151 ~ 154단계 쓰기 사이의
  152단계 `runtests.py` 실행이 유효한 실행으로 읽히지 않아 한 묶음으로 남음.

- A-9 행 19 돌리지 않은 자기 테스트 (`implement_tasks.run.agentos_bugfix_checks.pass_last`, `checks` 규칙의 선택 설정값 `unrun`, agentos_bugfix만 켬):
  구현 단계에서 돌린 checks/ 스크립트(와 F-2의 모듈)만 모집단에 넣었음. 그래서 써 놓고 한 번도 돌리지 않은 테스트는 판정에서 빠졌음. 이제 창 안에 쓴
  checks/ 스크립트 가운데 한 번도 돌리지 않았고 마지막 내용에 판정 구문이 있는 것(D-6 행 21의 `has_verdict`)과, 기존 테스트 모듈에 테스트 함수를 더한 뒤
  그 모듈을 고른 유효 러너 실행이 없는 모듈(F-2)을 "통과하지 않은 테스트"로 모집단에 넣음(implement-tasks.md 39행 "ensuring they pass"). 뒤에 옮기거나
  지운 스크립트(`head … > x_fixed.py && mv x_fixed.py x.py`의 임시 파일)는 넣지 않음. 평가 499런: django__django-13346 한 런이 통과에서 비율로(실패)
  (`tests/model_fields/test_jsonfield.py`에 `test_key_in`을 더하고 그 모듈의 유효 실행이 없음).

## 이름 두 개 바꿈 (2026-11-21)

같이 학습하는 세 워크플로(speckit_bug, openspec_ff, agentos_bugfix)가 같은 이름을 쓰게 하려고 이 워크플로에서만 두 이름을 바꿈(사용자 결정,
`tasks/2026-11-20-agentos-bugfix-reward-fixes/12-세워크플로-공통점.md`). agentos_v2와 다른 워크플로의 문서, rubric, 판정은 그대로임.

- 진입 문서 `core-workflow.md`를 `overview.md`로 바꿈(`/agent-os/overview.md`). `docs/core-workflow.md`를 `git mv`로 옮기고 instruction,
  시스템 프롬프트, `__init__.py`의 `entry_doc`도 바꿈.
- spec 폴더의 자기 테스트 스크립트 폴더 `checks/`를 `verify/`로 바꿈(`/tmp/agent-os/specs/<spec>/verify/`). `overview.md`의 네 곳은 손으로,
  명령 문서 두 곳(create-tasks.md 129행, implement-tasks.md 39행)은 `build.py`의 `RENAME`으로 바꿈. 렌더한 명령 문서에 `checks/`가 남으면
  build가 멈춤(`FORBIDDEN`).
- rubric: `derive_rubric.py`가 agentos_v2의 rubric 글에 `RENAME`(진입 문서 이름, `/`가 뒤따르는 `checks`, `{SPEC}/checks`)을 적용함.
  출처 `CW`의 경로와 컨테이너 경로, `dir` 설정값 9개, 스크래치 패턴과 note, 인용문과 근거 글이 바뀜. 항목 id와 규칙 이름(`agentos_bugfix_checks`,
  `scratch_outside_checks`, `checks` 규칙)은 그대로 둠. 보고서 항목 6개에 `scripts_dir`을 줌.
- 같이 쓰는 코드(`agentos_v2/reward/checks.py`): `checks`가 글자로 박힌 세 곳을 설정값으로 바꿈. task 줄의 상대 경로는 `dir` 폴더의 이름으로
  읽고, 실패 뒤 고친 스크립트 쓰기와 보고서의 스크립트 결과 비교는 `report`의 새 선택 설정값 `scripts_dir`(기본값 `{artifact}/{SPEC}/checks`)을
  씀. agentos_v2의 `dir`은 모두 `{artifact}/{SPEC}/checks`이고 `scripts_dir`을 쓰지 않으므로 agentos_v2의 판정은 같음.
- 이 워크플로의 채점 코드: `penalty_tests.py`의 자기 테스트 스크립트 폴더(`OWN_TESTS_DIR`)와 `penalty.py`의 task 줄 경로 제외(`/verify/`)를 바꿈.
- `verify/`와 upstream의 `verifications/`: 문서에서 두 폴더는 늘 끝의 `/`까지 적혀 서로 다른 줄에 나오고, 채점기의 패턴은 `verify/`를 `/`까지
  맞추므로(`(?!verify/)`, `"/verify/"`, 폴더 이름의 마지막 부분 비교) `verifications/`와 섞이지 않음. `verif\w*` 정규식은 task 그룹 제목에만
  쓰이고 경로에는 쓰이지 않음. 스크래치 패턴 시험에 `verifications/` 안의 스크립트를 넣음.
- 평가 499런: 저장된 런은 옛 이름으로 돌았으므로, 재채점 때만 에피소드 글의 옛 이름을 새 이름으로 바꿔 읽음(채점기에는 그런 대응이 없음).
  판정 변화 0. 대응 방법과 수는 `tasks/2026-11-20-agentos-bugfix-reward-fixes/13-이름-변경-구현.md`.

## 기존 테스트 줄의 수정을 최종 patch로도 판정 (2026-11-21)

`global.run.prohibited_action.test_file_write`(규칙 `prohibited_action`, `action: test_file_modify`)는 trace의 편집기 쓰기로 다시 만든
전후 내용만 봤음. 그래서 기존 테스트 줄을 편집기로 바꾸면 실패하고, 같은 수정을 `sed`나 python 스크립트로 하면 쓴 내용을 몰라 세지 않아
통과했음. 문서는 도구와 관계없이 막음(create-tasks.md 129행 "never change or remove an existing test line", implement-tasks.md 39행).
사용자 결정으로 지금 판정은 그대로 두고, 런이 끝났을 때의 patch가 base commit에 있던 테스트 파일의 줄을 바꾸거나 지우면 이 항목도 실패하게 함.

- 공통 코드: `prohibited_action`에 선택 설정값 `final_patch`(기본값 꺼짐, `test_file_modify`에서만 읽음)를 더함. 줄 비교는 새 모듈
  `workflow_rubric/patch.py`의 `changed_lines`임. 한 파일의 patch 부분에서 `-` 줄마다 공백을 모두 뺀 글을 만들고, 빈 줄이면 세지 않으며,
  같은 파일의 `+` 줄 가운데 공백을 뺀 글이 같은 줄이 남아 있으면 그 줄 하나와 짝지어 세지 않음(들여쓰기·줄 끝 공백만 바뀐 줄과 파일 안에서
  옮긴 줄). 짝이 없는 `-` 줄이 하나라도 있으면 실패함. 줄만 더한 파일과 런이 만든 파일(base에 없던 파일)은 대상이 아님. 테스트 파일은
  규칙이 이미 쓰는 `facts.is_test_path`임.
- patch 본문이 규칙에 닿는 길: 하네스가 런이 끝날 때 모든 워크플로에서 이미 `episode.artifacts["patch"]`에 patch를 기록하고(검증기보다 먼저),
  저장된 런에도 같은 칸이 있음. 이 워크플로의 `reward/penalty.inputs`가 그 patch에서 테스트 파일 부분만 골라 `Collected.inputs["test_patch"]`로
  넘김(라이브와 재채점이 같은 길). 다른 워크플로는 이 입력을 만들지 않으므로 더 모으는 것도 판정이 바뀌는 것도 없음.
- 크기 한도: 테스트 파일 부분을 patch 순서대로 모두 합쳐 256 KiB까지 넘기고, 넘치는 파일은 판정하지 않음(그 파일은 trace만으로 지금처럼
  판정). 하네스가 patch를 1 MB에서 자른 경우 마지막 파일 부분은 버리고, 머리글의 줄 수와 맞지 않는 hunk가 있는 파일도 판정하지 않음.
  patch가 없으면 이 입력이 없고 항목은 지금과 같게 판정함.
- 자체 점검: `selftest_golden.py`에 DISHONEST 변형 `sed_test_line`(기존 테스트의 기대값을 `sed`로 바꾸고 patch에만 보임)을 더함.
- 평가 499런: 이 항목이 통과에서 실패로 바뀐 런 28개, 반대 방향 0개, 다른 항목의 변화 0개. 28런 모두 기존 테스트 줄을 실제로 바꾸거나
  지운 런이었음(`tasks/2026-11-20-agentos-bugfix-reward-fixes/14-기존-테스트-수정-판정-구현.md`).

## 정답 패치 항목 하나를 못 푼 롤아웃에만 적용해 되살림 (2026-11-21)

C-2에서 뺀 두 항목 가운데 `plan_files.named_covers_gold`(tasks.md가 적은 소스 파일에 정답 패치의 소스 파일이 모두 있음)를 되살림.
C-2의 문제(정답과 다른 파일을 고쳐 정당하게 푼 런이 감점됨)는 항목을 빼는 대신 **푼 롤아웃에는 이 항목을 적용하지 않는 것**으로 막음.

- 신호가 둘이 됨: `agentos_bugfix/penalty`는 10개 항목의 평균(이 항목은 판정대로), `agentos_bugfix/penalty_solved`는 이 항목을 1로 둔
  평균. `train.py`는 verifier가 1인 롤아웃에 `penalty_solved`를, 0인 롤아웃에 `penalty`를 씀(`workflow_rubric/penalty.py`의
  `post(unsolved_only=...)`, `reward/penalty.py`의 `UNSOLVED_ONLY`). 나머지 9개 항목(파일 2, 테스트 7)은 푼 롤아웃에도 그대로 적용됨.
- `compliance_reward.penalty_gate`는 그대로 `all`. `unsolved`로 두면 평균 전체가 면제되어, 풀었지만 테스트 규칙을 어긴 런이 만점을
  받음. 이 변경은 항목 하나에만 거는 면제임.
- 과제에 정답 패치가 없으면 이 항목은 판정 불가로 평균에서 빠짐(`penalty_gold_unknown` = 1).
- `patch_covers_gold`는 되살리지 않음: 못 푼 롤아웃에서 `named_covers_gold`와 거의 같은 것을 말함.
- penalty 항목은 9개에서 10개(파일 3, 테스트 7)가 되어, penalty 가중치 0.3에서 항목 하나의 보상 크기가 0.3 × 1/9 = 0.0333에서
  0.3 × 1/10 = 0.03이 됨. 푼 롤아웃의 penalty 점수는 9개 항목이 그대로이고 열 번째가 1이라, 어긴 항목 수가 같으면 전보다 높아짐
  (하나 어김: 8/9 = 0.889에서 9/10 = 0.9).
- 평가 499런으로 다시 채점한 수치는 아직 없음.

## 보상 검토 반영 요약 (2026-11-21)

### 변경 내역

`b0152ada` 뒤의 커밋을 문제(`tasks/2026-11-20-agentos-bugfix-reward-fixes/`의 문제 번호)마다 한 행에 하나씩 적음. H-1 ~ H-10은 여러 워크플로가 같이 쓰는 관측 코드(`workflow_rubric/`)를 고친 것임.

| 문제 | 바꾼 것 | 커밋 |
|---|---|---|
| H-1 | 하네스가 거부해 실행되지 않은 도구 호출을 아무 행동도 아닌 것으로 읽음. | `dcbee819` |
| H-1 보강 | 거부 머리 문구와 거부 문구 사이에 앞 명령의 출력이 끼어도 거부로 읽음. | `99160721` |
| H-2 | python 안에서 `unittest.TextTestRunner`로 돌린 테스트를 테스트 실행으로 셈. | `179fcbda` |
| H-3 | 요약 줄이 잘린 unittest·sympy 출력은 테스트별 결과 줄을 세어 요약을 만듦. | `cae4d242` |
| H-4 | check 스크립트의 결과를 알 수 있으면 스크립트 자신의 종료 코드로 읽고, .pth 오류 묶음은 빼고 읽음. | `d0df7c3b` |
| H-5 | 변경을 `git stash`로 치운 사이의 실행을 보고서 비교, 체크 시점의 결과, 테스트 실행 항목에서 뺌. | `a9a30d51` |
| H-6 | 한 호출 안에서 저장소를 고친 뒤 돌린 테스트를 고친 뒤의 실행으로 셈. | `15179724` |
| H-7 | trace에 쓰기 기록이 없는 저장소 변경을 그 파일 이름을 적은 첫 명령의 단계에 기록하고 `.orig`·`.rej`는 편집으로 세지 않음. | `de53cf60` |
| H-7 보강 | 첫 명령으로 시점을 정하는 경로를 이 변경이 만든 파일로 좁힘. | `b134a774` |
| H-8 | 같은 파일로의 두 번째 `mv`를 디렉터리 안으로의 이동이 아닌 그 파일의 쓰기로 읽음. | `5b6ad79d` |
| H-9 | 내용을 모르는 tasks.md 쓰기는 건너뛰고 아는 내용끼리 비교하며, 마지막 쓰기의 내용은 샌드박스 파일로 채움. | `bb347609` |
| H-10 | 도구 이름 `str_replace`처럼 하네스가 편집기로 돌린 호출을 편집으로 읽음. | `a425043e` |
| D-1 | 모든 상자를 체크한 쓰기가 없으면 마지막 코드 변경과 tasks.md 마지막 쓰기 가운데 늦은 것 다음 단계부터 보고서의 첫 쓰기 전까지를 보고서 항목과 `suite_run`의 비교 구간으로 쓰고, 그 구간에 checks/ 스크립트 결과만 있으면 보고서 항목을 그 결과와 비교함. | `475b9a17` |
| D-2 | 순서 항목이 산출물의 쓰기를 없는 것으로 보는 품질 문턱을 0.5에서 0.1로 낮춤. | `f65d0fa6` |
| D-3 | 다음 명령 문서를 일찍 열어도 앞 단계는 그 닫는 산출물을 쓸 때까지 이어짐. | `11248db8` |
| D-4 | 런이 만들지 않은 산출물은 읽기 항목에서 읽지 않은 것으로 셈. | `93d0188c` |
| D-4 예외 | create-tasks의 읽기 항목만 만들지 않은 산출물을 D-4 전처럼 읽어야 할 목록에서 뺌. | `67f39c31` |
| D-5 | 저장소를 한 번도 고치지 않은 런의 순서 항목에서 "첫 저장소 쓰기"를 사슬에서 뺌. | `78880006` |
| D-5 되돌림 | 사용자 결정으로 D-5를 되돌려 저장소를 고치지 않은 런의 순서 항목이 다시 실패함. | `2ffc7330` |
| D-6 행 12 | 코드를 바꾼 task group마다 그 그룹의 첫 코드 변경 전에 그 그룹의 테스트를 써야 `before_code`가 통과함. | `5d6e9f77` |
| D-6 행 12 보강 | 기존 테스트 모듈에 더한 테스트 함수는 함수마다 그 테스트의 첫 쓰기로 셈. | `909d02c4` |
| D-6 행 21 | 판정 구문이 있는 checks/ 스크립트만 테스트를 쓴 것으로 셈. | `901680d7` |
| E-1 | 과제 문장에 있는 "..." 줄은 템플릿 빈칸으로 보지 않음. | `361b0c3e` |
| E-2 | 재사용 코드 줄의 (assumed) 표기를 백틱 없는 경로, 한 코드 구간, "찾은 것이 없음" 문장까지 받음. | `7c214b6c` |
| E-3 | 보고서의 Issues Found와 겹친 전체 상태를 받고, Notes 절이 없으면 해당 없음, spec.md 글머리 한도에서 하위 글머리는 세지 않음. | `380a58b0` |
| E-4 행 2 | initialization.md에 과제 문장의 낱말 절반 이상이 순서대로 있어야 통과함. | `6b8949cf` |
| E-4 행 4 | Existing Code to Reference의 Feature 줄이 모두 (assumed) 표기여야 하고 맞는 줄의 비율이 점수임. | `bcccf14f` |
| E-4 행 5 | 문서의 폴더 자리표시와 질문 틀이 남으면 잔재 항목이 실패함. | `db9dc7f4` |
| E-4 행 6 | 답의 근거에 경로·코드 이름·출처가 없으면 틀린 답으로 셈. | `41f1dbe8` |
| E-4 행 7 | spec 폴더 날짜가 런을 돌린 날이어야 통과하고, 날짜를 모르는 저장된 런은 꼴만 봄. | `9b48ab24` |
| E-4 행 8 | requirements.md의 ### 절 이름도 템플릿의 이름이어야 함. | `159ade80` |
| E-4 행 9 | verifications 폴더가 shape-spec 단계가 끝났을 때 있어야 통과함. | `dc2c54ce` |
| E-4 행 12 | spec.md에서 첫 굵은 이름 앞의 글머리들을 블록 하나로 세어 한도에 넣음. | `380a58b0` |
| E-4 행 14 | Status 값에 다른 허용 값을 섞거나 실패를 덧붙이면 실패함. | `4c1b7162` |
| E-5 | spec 폴더 밖 /tmp의 모든 파일과 저장소에 만들었다 지운 임시 파일을 잡고, 코드 변경 항목은 소스 파일 변경을 요구함. | `73e13534` |
| F-1 | 구현 단계에서 spec.md와 requirements.md를 다시 여는지 보는 항목을 채점에서 뺌. | `ec8b9ab3` |
| F-2 (자기 테스트의 형태) | 기존 테스트 모듈에 더한 테스트 함수도 런의 자기 테스트로 셈. | `2fa3ff98` |
| F-2 (다시 읽기) | create-tasks에서 런이 앞 단계에 직접 쓴 문서는 다시 읽지 않아도 읽은 것으로 봄. | `d26d0633` |
| F-3 (문서) | implement-tasks.md 39행의 "(if any;"를 구현 그룹마다 x.1 하위 task로 테스트를 먼저 쓴다는 말로 바꿈. | `81fc0437` |
| F-3 행 14 | 런이 고친 파일을 `git checkout`이나 `git restore`로 되돌린 것도 변경을 치운 것으로 봄. | `364312bc` |
| F-3 행 16 | 런이 만들었고 최종 변경에 남지 않는 파일을 검증 단계에서 지우는 것은 코드 변경으로 세지 않음. | `f4d56587` |
| B-1, B-8 행 2 | `ticked_after_work`가 task 줄의 파일 이름을 알려진 확장자와 경로 뒤쪽으로 맞추고, 파일 없는 task는 구현 단계 안의 일을 근거로 봄. | `cee90f83` |
| B-2 | create-tasks의 tasks.md 형식 항목 9개가 create-tasks 단계가 끝났을 때의 tasks.md를 봄. | `07f02abe` |
| B-3 | `test_first`가 테스트 하위 task의 다른 낱말을 받고 문서 그룹과 테스트 확인 그룹을 뺌. | `0665466c` |
| B-4 | 세 단계 이상의 번호와 번호 있는 task 줄 아래의 번호 없는 체크박스도 맞는 줄로 봄. | `8f201d03` |
| B-5 | 그룹에 실패 결과가 없는 ⚠️는 두 번 고쳐 본 기록을 요구하지 않고, 열린 task가 있으면 ⚠️가 없어도 미완료 보고를 판정함. | `80b23fce` |
| B-5 보강 (⚠️가 처음 나타난 때) | 실패 결과가 없는 ⚠️도 검증 단계나 그것을 여는 쓰기에서 처음 나타나야 미완료 표시로 봄. | `cacff4b2` |
| B-5 보강 (`ticked_after_work`) | 미완료로 드러나 ⚠️를 단 task에는 작업 근거를 묻지 않음. | `611b6367` |
| B-5 보강 (`tasks_status`) | 보고서의 tasks Status 항목이 체크박스가 있는 줄만 열린 task로 셈. | `a37faeef` |
| B-5 보강 (한 줄씩 단 ⚠️) | 검증 단계를 여는 쓰기 바로 앞의, 사이에 작업이 없는 tasks.md 쓰기들도 여는 쓰기로 봄. | `d4549e61` |
| B-6 행 3 | Total Tasks가 테스트 검토 그룹을 빼고 센 값이어도 통과함. | `dbdda80b` |
| B-6 행 5 (문서) | create-tasks.md에 tasks.md가 Overview, Task List, Execution Order 세 절을 남긴다는 문장을 더함. | `49e0c677` |
| B-7 | task group마다 하위 task 줄이 있는지 보고 그 비율을 점수로 줌. | `d9a11f15` |
| B-8 행 1 | 테스트 실행을 말하는 하위 task를 마지막 코드 변경 뒤 테스트 결과 없이 체크하면 `ticked_passing`이 실패함. | `af260be3` |
| B-8 행 1 보강 | `ticked_passing`의 마지막 코드 변경을 소스 변경으로 좁힘. | `606401c2` |
| B-8 행 3 | 앞 그룹을 체크한 뒤 다음 그룹을 체크하기 전에 일이 있어야 `groups_in_order`가 통과함. | `144651da` |
| B-8 행 13 | 구현 중 tasks.md에 더한 줄이 task 줄, 그 세부 줄, 새 그룹 제목이 아니면 task를 바꾼 것으로 봄. | `6c05c0ab` |
| C-1 | 코드를 바꾸는 하위 task마다 그 task 줄에 저장소 경로가 있어야 계획한 파일 penalty 항목이 통과함. | `45a20841` |
| C-2 | 정답 패치와 비교하던 penalty 항목 둘을 빼 penalty 항목이 9개가 됨. (그 뒤 `named_covers_gold`는 못 푼 롤아웃에만 적용하는 항목으로 되살려 10개: 위 절) | `e79b0476` |
| R1 | 실패를 테스트 하나하나의 단위로 보고, 그 단위를 돌린 통과만 실패를 지우는 공용 함수를 더함. | `b2450cae` |
| A-9 행 8 (R3) | penalty 테스트 항목이 checks/ 스크립트와 저장소 테스트 파일만 테스트 결과와 테스트 편집으로 셈. | `34ce790e` |
| A-9 행 20 | 런이 더한 자기 테스트만 고른 러너 실행은 기존 테스트 실행으로 세지 않음. | `a69057c2` |
| A-3 (R2) | 변경을 치워도 실패하는 테스트와 보고서가 예상된 실패라고 밝힌 테스트를 penalty의 고쳐야 할 실패에서 빼고, 문서 39행을 그에 맞춤. | `43ea15ee` |
| A-4, A-9 행 7 | 실패한 테스트마다 고치고 다시 돌린 횟수를 세어 한 번에서 두 번이면 맞음으로 봄. | `c5aba7d4` |
| A-9 행 17 | 그룹을 체크하기 전에 그 그룹의 실패가 다시 통과했거나 그룹에 ⚠️가 있어야 함. | `2c85b468` |
| A-7 행 8, A-2 (구현 단계 penalty) | 실패한 테스트는 그 테스트를 돌린 실행의 통과로만 해결되고, 빼고 돌린 통과는 해결로 치지 않음. | `625ee3a2` |
| A-1, A-2 (검증 단계 penalty) | 검증 단계의 실패를 테스트마다 따로 보아, 다시 통과했거나 변경 탓인 실패를 고치고 다시 돌렸으면 맞음으로 봄. | `cc6eafd3` |
| A-9 행 22 | 검증 단계의 변경 탓인 실패마다 그것을 고친 편집이 있는지 봄. | `61f6fc3f` |
| A-2 (`suite_status`) | Status를 All Passing으로 적었으면 검증 단계에 해결되지 않은 실패가 없어야 통과함. | `b95b76bc` |
| A-7 행 7 | Failed Tests를 검증 단계에서 고치고 다시 통과하지 않은 실패 전부와 대조해 적힌 비율을 점수로 줌. | `9bb67666` |
| A-8 | 실패한 테스트 이름이 Failed Tests 절 안에 있어야 적은 것으로 봄. | `d57863be` |
| A-5 | 실패한 채로 한 체크는 그 실패가 모두 고칠 필요 없는 실패일 때만 맞음으로 봄. | `9a1ca32f` |
| R2 보강 | 예상된 실패의 이유 문구를 Failed Tests 항목의 들여 쓴 이어지는 줄에서도 찾음. | `ea9bba61` |
| A-9 행 9 | 코드를 바꾼 그룹마다 다음 그룹의 코드를 고치기 전에 테스트 실행이 있어야 하고 맞는 그룹의 비율이 점수임. | `08efdde7` |
| A-9 행 14 | 검증 단계의 코드 고침은 사이에 테스트 결과가 끼지 않은 한 묶음이어야 함. | `c2afaf14` |
| A-9 행 19 | 써 놓고 돌리지 않은 판정 있는 checks/ 스크립트와 돌리지 않은 자기 테스트 모듈을 통과하지 못한 것으로 셈. | `c1ecf1f0` |
| A-6 (문서) | implement-tasks.md 40행에 자기 테스트는 확인을 느슨하게 하거나 지워서 통과시키지 않는다는 두 문장을 더함. | `6b7a276b` |
| A-4, A-9 행 7 (시도 상한 5) | 사용자 결정으로 시도 상한을 두 번에서 다섯 번으로 올리고 여섯 번째 시도를 실패로 보며 문서 40행도 고침. | `cb377258` |
| 학습 설정 | agentos_bugfix의 penalty 항목 9개를 넣은 보상식(바닥 0.7, penalty 가중치 0.3)의 학습 설정 파일을 더함. | `51d0e77d` |
| 이름 변경 (공통 코드) | agentos_v2와 같이 쓰는 규칙 코드에서 check 스크립트 폴더 이름을 설정값으로 바꿈(기본값은 `checks`). | `0a8cc464` |
| 이름 변경 | 진입 문서를 `overview.md`로, spec 폴더의 자기 테스트 폴더를 `verify/`로 바꾸고 rubric과 채점 코드를 맞춤. | `c827a623` |
| 기존 테스트 수정 | 런이 끝났을 때의 patch가 기존 테스트 파일의 줄을 바꾸거나 지우면 도구와 관계없이 기존 테스트 수정 항목이 실패함. | `39ee1977` |

### 문서 변경

`git diff b0152ada HEAD -- docs`의 문장 단위 변경임. 위치는 `workflows/agentos_bugfix/` 아래의 새 글의 줄임.

| 문서 위치 | 전 | 후 |
|---|---|---|
| `docs/commands/create-tasks/create-tasks.md:116` | 없음 | "Whatever you adapt, every tasks.md keeps the example's three sections: `## Overview` with its `Total Tasks:` line, `## Task List`, and `## Execution Order` (the order in which the task groups are implemented)." |
| `docs/commands/implement-tasks/implement-tasks.md:39` | "Running the tests you've written (if any; they are check scripts under `/tmp/agent-os/specs/[this-spec]/checks/`, or test functions you added to an existing repository test module, run through that module with the test runner) and the existing tests of the code you changed, and ensuring they pass." | "Running the tests you've written (each implementation task group writes them first, as its x.1 sub-task; they are check scripts under `/tmp/agent-os/specs/[this-spec]/checks/`, or test functions you added to an existing repository test module, run through that module with the test runner) and the existing tests of the code you changed, and ensuring they pass." |
| `docs/commands/implement-tasks/implement-tasks.md:39` | "An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test in the final verification report." | "An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test under Failed Tests in the final verification report, noting that it is an expected failure (it asserts the behavior the task asks to change)." |
| `docs/commands/implement-tasks/implement-tasks.md:40` | "After two attempts that do not get it to pass, mark that sub-task's checkbox with ⚠️ instead of ticking it, and go on." | "Make up to five attempts. If it still does not pass, mark that sub-task's checkbox with ⚠️ instead of ticking it, and go on; do not make a sixth attempt." |
| `docs/commands/implement-tasks/implement-tasks.md:40` | 없음 | "A test you wrote is wrong only when it checks something the task does not ask for: then correct what it checks. Never make a failing test pass by loosening or removing what it checks." |
| `docs/overview.md` (파일) | `docs/core-workflow.md` | `docs/overview.md` |
| `docs/overview.md:56` | "├── checks/                    the task groups' tests that are written as scripts; any scratch file" | "├── verify/                    the task groups' tests that are written as scripts; any scratch file" |
| `docs/overview.md:61` | "No command creates `S/checks/`; make it the first time you need it." | "No command creates `S/verify/`; make it the first time you need it." |
| `docs/overview.md:85` | "The tests the task groups call for are scripts in `S/checks/`, or new test functions added to the existing repository test module that covers the changed code." | "The tests the task groups call for are scripts in `S/verify/`, or new test functions added to the existing repository test module that covers the changed code." |
| `docs/overview.md:89` | "They go to `S/`, scratch files to `S/checks/`." | "They go to `S/`, scratch files to `S/verify/`." |
| `docs/commands/create-tasks/create-tasks.md:129` | "... is a script under `/tmp/agent-os/specs/[this-spec]/checks/`, run on its own, or a new test function added to the existing repository test module that covers the changed code; ..." | "... is a script under `/tmp/agent-os/specs/[this-spec]/verify/`, run on its own, or a new test function added to the existing repository test module that covers the changed code; ..." |
| `docs/commands/implement-tasks/implement-tasks.md:39` | "... they are check scripts under `/tmp/agent-os/specs/[this-spec]/checks/`, or test functions you added to an existing repository test module, ..." | "... they are check scripts under `/tmp/agent-os/specs/[this-spec]/verify/`, or test functions you added to an existing repository test module, ..." |
| `instruction.md:4` | "Before you look at the repository, open /agent-os/core-workflow.md; that is your first action." | "Before you look at the repository, open /agent-os/overview.md; that is your first action." |
| `instruction.md:6` | "core-workflow.md gives the path of each command document, the spec folder the commands write to, and the point at which you call finish." | "overview.md gives the path of each command document, the spec folder the commands write to, and the point at which you call finish." |
| `system-prompt.j2:68` | "1. The first thing you do is open /agent-os/core-workflow.md." | "1. The first thing you do is open /agent-os/overview.md." |

### rubric 변경

`reward/rubric.yaml`을 `b0152ada`와 `HEAD`에서 항목 id마다 비교한 것이고, 출처의 줄 번호만 바뀐 항목과 `generated:` 자체 점검 값은 넣지 않음. 항목 밖의 변경은 `scoring.close_on_artifact: true`(D-3) 하나임.

| 항목 id | 처리 | 내용 |
|---|---|---|
| `shape_spec.spec_dir.path_match.dated` | 설정값을 바꿈 | `today: true`를 더해 폴더 날짜를 런을 돌린 날과 대조함 (E-4 행 7). |
| `shape_spec.verifications_dir.artifact_exists` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (E-4 행 9). |
| `shape_spec.initialization.item_format.text` | 규칙을 바꿈 | kind를 `agentos_bugfix.task_text`로, `min_share: 0.5`를 더하고 note를 바꿈 (E-4 행 2). |
| `shape_spec.initialization.no_template_residue.fill_marks` | 규칙을 바꿈 | kind를 `agentos_bugfix.task_residue`로 바꿔 과제 문장에 있는 줄을 빈칸으로 보지 않음 (E-1). |
| `shape_spec.requirements.no_template_residue.fill_marks` | 규칙을 바꿈 | kind를 `agentos_bugfix.task_residue`로 바꿈 (E-1). |
| `shape_spec.requirements.no_template_residue` | 설정값을 바꿈 | `patterns`에 폴더 자리표시 셋과 질문 틀 넷을 더함 (E-4 행 5). |
| `shape_spec.requirements.agentos_bugfix_requirements.answers` | 설정값을 바꿈 | `basis_check: true`를 더함 (E-4 행 6). |
| `shape_spec.requirements.cross_ref.2` | 설정값을 바꿈 | `levels`, `skip_sections`, `tag_level`과 ### 절 이름을 더하고 note를 바꿈 (E-4 행 8). |
| `shape_spec.requirements.item_format.existing_code` | 설정값을 바꿈 | `pattern`을 넓히고 (E-2) `each_of`로 모든 Feature 줄을 봄 (E-4 행 4). |
| `shape_spec.requirements.item_format.reusability_opportunities` | 설정값을 바꿈 | `pattern`이 백틱 없는 경로, 한 코드 구간, "찾은 것이 없음" 줄을 받음 (E-2). |
| `shape_spec.run.agentos_bugfix_read.initialization` | 설정값을 바꿈 | `absent_unread: true`를 더함 (D-4). |
| `write_spec.run.agentos_bugfix_read.requirements` | 설정값을 바꿈 | `absent_unread: true`를 더함 (D-4). |
| `write_spec.spec.no_template_residue` | 설정값을 바꿈 | `patterns`에 폴더 자리표시 셋을 더함 (E-4 행 5). |
| `write_spec.spec.agentos_bugfix_blocks.existing_code` | 설정값을 바꿈 | `top_level: true`를 더함 (E-3, E-4 행 12). |
| `write_spec.spec.agentos_bugfix_blocks.specific_requirements` | 설정값을 바꿈 | `top_level: true`를 더함 (E-3, E-4 행 12). |
| `create_tasks.run.agentos_bugfix_read.spec_inputs` | 설정값을 바꿈 | `written_before: true`를 더함 (F-2), D-4의 `absent_unread`는 켜지 않음 (D-4 예외). |
| `create_tasks.tasks.agentos_bugfix_tasks.test_first` | 설정값을 바꿈 | `wide_words: true`를 더함 (B-3). |
| `create_tasks.tasks.agentos_bugfix_tasks.total` | 설정값을 바꿈 | `impl_counts: true`, `wide_words: true`를 더함 (B-6 행 3). |
| `create_tasks.tasks.item_format.acceptance_criteria` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.item_format.checkbox_lines` | 설정값을 바꿈 | `pattern`이 세 단계 이상의 번호를 받고 `nested_under: true`를 더하며 (B-4) 대상 상태를 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.item_format.groups` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.item_format.subtasks` | 규칙을 바꿈 | kind를 `agentos_bugfix.tasks`(`rule: group_subtasks`)로 바꾸고 note를 바꾸며 (B-7) 대상 상태를 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.item_format.title` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.no_template_residue` | 설정값을 바꿈 | `patterns`에 폴더 자리표시 셋을 더하고 (E-4 행 5) 대상 상태를 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.no_template_residue.fill_marks` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (B-2). |
| `create_tasks.tasks.section_present.execution_order` | 설정값을 바꿈 | 대상 상태를 `stage_end`로 바꾸고 (B-2) 출처에 create-tasks.md 116행의 새 문장을 더함 (B-6 행 5). |
| `create_tasks.tasks.section_present.task_list` | 설정값을 바꿈 | 대상 상태를 `final`에서 `stage_end`로 바꿈 (B-2). |
| `implement_tasks.run.agentos_bugfix_read.spec_inputs` | 뺌 | 구현 단계의 spec.md·requirements.md 다시 읽기 항목을 채점에서 뺌 (F-1). |
| `implement_tasks.run.agentos_bugfix_read.tasks` | 설정값을 바꿈 | `absent_unread: true`를 더함 (D-4). |
| `implement_tasks.run.agentos_bugfix_read.tasks_phase3` | 설정값을 바꿈 | `absent_unread: true`를 더함 (D-4). |
| `implement_tasks.run.agentos_bugfix_checks.written` | 설정값을 바꿈 | `module_tests: true`를 더함 (F-2). |
| `implement_tasks.run.agentos_bugfix_checks.before_code` | 설정값을 바꿈 | 구간 끝 `repo_edit`에 `test_paths: false`, `module_tests: true`를 더하고 (F-2) `per_group: true` (D-6 행 12), `verdict: true` (D-6 행 21)를 더함. |
| `implement_tasks.run.agentos_bugfix_checks.pass_last` | 설정값을 바꿈 | `unrun: true` (A-9 행 19), `module_tests: true` (F-2)를 더하고 note의 "after two attempts"를 "after the attempts"로 바꿈 (A-4 상한 5). |
| `implement_tasks.run.agentos_bugfix_verify.phase2_run` | 설명만 바꿈 | note에 그룹마다 다음 그룹의 코드 전에 테스트했는지의 비율을 적음 (A-9 행 9). |
| `implement_tasks.run.agentos_bugfix_verify.suite_run` | 설정값을 바꿈 | `phase3_fallback: true`를 더함 (D-1). |
| `implement_tasks.run.code_change` | 설정값을 바꿈 | `repo_edit`에 `source: true`를 더하고 note를 바꿈 (E-5 행 18). |
| `implement_tasks.tasks.agentos_bugfix_tasks.groups_in_order` | 설정값을 바꿈 | `work_between: true`와 `dir`를 더함 (B-8 행 3). |
| `implement_tasks.tasks.agentos_bugfix_tasks.ticked_after_work` | 설정값을 바꿈 | `name_files: true` (B-1)와 `not_done_out: true` (B-5 보강)를 더함. |
| `implement_tasks.tasks.agentos_bugfix_tasks.ticked_passing` | 설명만 바꿈 | 출처 인용문을 문서 39행의 새 문장으로 바꿈 (A-3). |
| `implement_tasks.tasks.agentos_bugfix_tasks.warned_after_attempts` | 설명만 바꿈 | `modality_evidence`와 출처 인용문을 "Make up to five attempts" 문장으로 바꿈 (A-4 상한 5). |
| `implement_tasks.final_verification.agentos_bugfix_report.test_counts` | 설정값을 바꿈 | `phase3_fallback: true`, `script_results: true`를 더함 (D-1). |
| `implement_tasks.final_verification.agentos_bugfix_report.failed_listed` | 설정값을 바꿈 | `phase3_fallback`, `script_results` (D-1), `standing` (A-7 행 7), `in_section` (A-8)을 더함. |
| `implement_tasks.final_verification.agentos_bugfix_report.suite_status` | 설정값을 바꿈 | `phase3_fallback`, `script_results` (D-1)와 `standing` (A-2)을 더함. |
| `implement_tasks.final_verification.agentos_bugfix_report.tasks_status` | 설정값을 바꿈 | `issues_listed: true` (E-3)와 `open_tasks: true` (B-5 보강)를 더함. |
| `implement_tasks.final_verification.agentos_bugfix_report.incomplete_listed` | 설정값을 바꿈 | `open_tasks: true`를 더함 (B-5). |
| `implement_tasks.final_verification.field_enum.status` | 설정값을 바꿈 | `strict_prefix: true`를 더함 (E-4 행 14). |
| `implement_tasks.final_verification.field_enum.suite_status` | 설정값을 바꿈 | `strict_prefix: true`를 더함 (E-4 행 14). |
| `implement_tasks.final_verification.field_enum.tasks_status` | 설정값을 바꿈 | `strict_prefix: true`를 더함 (E-4 행 14). |
| `implement_tasks.final_verification.no_template_residue` | 설정값을 바꿈 | `patterns`에 폴더 자리표시 셋을 더함 (E-4 행 5). |
| `implement_tasks.final_verification.section_present.notes` | 설정값을 바꿈 | `optional: true`를 더함 (E-3). |
| `implement_tasks.penalty.phase2_fail.edited_after_fail` | 설명만 바꿈 | note를 실패마다 최대 다섯 번의 시도로 바꾸고 출처에 문서 40행의 새 문장을 더함 (A-4, A-9 행 7, 규칙은 `reward/penalty_tests.py`). |
| `implement_tasks.penalty.phase2_fail.last_result_pass` | 설명만 바꿈 | note를 그룹마다 그 테스트를 돌린 실행의 재통과나 ⚠️로 바꿈 (A-7 행 8, A-9 행 17, 규칙은 `reward/penalty_tests.py`). |
| `implement_tasks.penalty.phase3_fail.edited_after_fail` | 설명만 바꿈 | note를 변경 탓인 실패마다 고쳤는지로 바꿈 (A-9 행 22, 규칙은 `reward/penalty_tests.py`). |
| `implement_tasks.penalty.phase3_fail.last_result_pass` | 설명만 바꿈 | note를 실패마다 다시 통과했거나 고치고 다시 돌렸는지로 바꿈 (A-1, A-2, 규칙은 `reward/penalty_tests.py`). |
| `global.run.order.commands` | 설정값을 바꿈 | `substantive: 0.1`을 더함 (D-2). D-5의 `skip_if_absent`는 되돌려 남지 않음. |
| `global.run.agentos_bugfix_created_files.workflow_files` | 설정값을 바꿈 | `scratch: true`를 더함 (E-5 행 11). |
| `global.run.agentos_bugfix_paths_written.scratch_outside_checks` | 설정값을 바꿈 | `pattern`을 spec 폴더 밖 /tmp의 모든 파일과 spec 폴더 안 checks/ 밖 스크립트로 넓히고 note를 바꿈 (E-5 행 10). |
| `global.penalty.plan_files.named` | 설명만 바꿈 | note를 코드를 바꾸는 하위 task 줄마다 경로를 적는 규칙으로 바꿈 (C-1, 규칙은 `reward/penalty.py`). |
| `global.penalty.plan_files.named_equals_patch` | 설명만 바꿈 | note를 그 task 줄이 적은 소스 파일로 바꿈 (C-1, 규칙은 `reward/penalty.py`). |
| `global.penalty.plan_files.named_covers_gold` | 뺐다가 되살림 | 정답 패치와 비교하던 penalty 항목을 뺌 (C-2). 푼 롤아웃에는 적용하지 않는 항목으로 되살림 (`agentos_bugfix/penalty_solved`). |
| `global.penalty.plan_files.patch_covers_gold` | 뺌 | 정답 패치와 비교하던 penalty 항목을 뺌 (C-2). |
| 출처 `CW` (항목 밖) | 설정값을 바꿈 | `path`를 `docs/overview.md`로, `container_path`를 `/agent-os/overview.md`로 바꿈 (이름 변경). |
| `dir` 설정값이 있는 항목 9개 (`agentos_bugfix_tasks`의 `groups_in_order`·`ticked_after_work`·`ticked_passing`·`warned_after_attempts`, `agentos_bugfix_checks`의 `written`·`pass_last`·`before_code`, `agentos_bugfix_verify.code_frozen`, `agentos_bugfix_report.suite_status`) | 설정값을 바꿈 | `dir`을 `{artifact}/{SPEC}/checks`에서 `{artifact}/{SPEC}/verify`로 바꿈 (이름 변경). |
| `agentos_bugfix_report`의 항목 6개 (`test_counts`, `failed_listed`, `suite_status`, `tasks_status`, `incomplete_listed`, `spec_name`) | 설정값을 바꿈 | `scripts_dir: '{artifact}/{SPEC}/verify'`를 더함 (이름 변경). |
| `global.run.agentos_bugfix_paths_written.scratch_outside_checks` (이름 변경) | 설정값을 바꿈 | `pattern`의 `(?!checks/)`를 `(?!verify/)`로, note와 근거 글의 `checks/`를 `verify/`로 바꿈. |
| 인용문이나 근거 글이 옛 이름을 적은 항목 (`agentos_bugfix_checks.written`·`pass_last`, `doc_read_first.cw`, `prohibited_action.test_file_write`, `unimplemented.5`, `agentos_bugfix_created_files.tests`·`workflow_files`) | 설명만 바꿈 | 인용문, note, 근거 글의 `core-workflow.md`를 `overview.md`로, `checks/`를 `verify/`로 바꿈 (이름 변경). 부록과 충돌 목록의 인용문도 같음. |
| `global.run.prohibited_action.test_file_write` | 설정값을 바꿈 | `final_patch: true`를 더하고 note를 최종 patch의 줄 비교를 포함하게 바꿈 (기존 테스트 수정). |

## RLOO 검토 반영 (2026-11-22)

### 변경 내역

`5946117a` 뒤의 커밋을 결정(2026-11-22 RLOO 검토 `tasks/2026-11-22-agentos-bugfix-rloo-reward-audit/`의 결정 번호)마다 한 행에 적음. D2(자기 테스트를 느슨하게 고친 것의 판정), D7(형식만 보는 판정의 강화), D8(advantage의 표준편차 정규화)은 바꾸지 않기로 함.

| 결정 | 바꾼 것 | 커밋 |
|---|---|---|
| D1 | 학습 variant `config/variant/openhands_9b_agentos_bugfix_swegym_reward_floor06_pen01_fmtcut.yaml`을 더함. 바닥값 0.7 → 0.6, penalty 가중치 0.3 → 0.1이고 나머지는 `..._floor_pen03_fmtcut.yaml`과 같음. 그 파일은 그대로 둠. | `e24d27ca` |
| D5 | `scoring.item_signals: true`가 단계 집계(sigma_kappa)에서도 채점된 항목마다 신호를 냄(`workflow_rubric/aggregate.py`). agentos_bugfix rubric에서 켬. 보상(준수율, penalty)은 이 신호를 읽지 않음. | `d118f17b` |
| D6 | implement-tasks PHASE 2·3의 테스트 실행 문장 뒤에, 저장소의 테스트 실행 방법을 먼저 찾아 그 실행기를 쓰라는 문장을 넣음. 저장소 이름은 적지 않음. | `7d7b4624` |
| D3·D4 | implement-tasks PHASE 2에 코드를 바꾸기 전에 자기 테스트를 돌려 실패를 확인하라는 문장을 넣고, 그것을 보는 penalty 항목 `phase2_own.reproduced`를 더함(penalty 항목 9개 → 10개. 아래 합치기 뒤 11개). golden의 지키지 않는 변형 2개(`no_repro_run`, `repro_passes`)와 테스트를 더함. 문장의 "the issue"를 "the behavior the task asks to change"로 고침. | `42108ce9`, `170dc653` |
| 합침 | 원격 `fix/agentos-bugfix-reward-fixes`의 `616c75b0`(`plan_files.named_covers_gold`를 못 푼 롤아웃에만 적용하는 항목으로 되살림)과 `11c018b5`(wf1121 학습 variant)를 합침. penalty 항목은 11개(파일 3, 테스트 8)가 됨. 항목 하나가 바꾸는 보상은 penalty 가중치 0.1에서 0.1 × 1/11 = 0.0091, 0.3에서 0.3 × 1/11 = 0.027. 푼 롤아웃은 `agentos_bugfix/penalty_solved`(`named_covers_gold`를 1로 둔 평균)로 받고, `phase2_own.reproduced`는 푼 롤아웃에도 적용됨. 충돌은 항목 수를 적은 문장과 테스트의 기대값뿐이었고 `rubric.yaml`·`rubric.lock`은 `derive_rubric.py`로 다시 만듦. | 이 합치기 커밋 |

### 문서 변경

`git diff 5946117a HEAD -- docs`의 문장 단위 변경임. 위치는 `workflows/agentos_bugfix/` 아래의 새 글의 줄임. 줄 수가 바뀌지 않아 기존 인용문의 줄 번호는 그대로임.

| 문서 위치 | 전 | 후 |
|---|---|---|
| `docs/commands/implement-tasks/implement-tasks.md:39` ("... and ensuring they pass." 뒤) | 없음 | "Find out how this repository runs its tests before you run them (its contributing guide, `tox.ini`, `setup.cfg` / `pyproject.toml`, or a test script in the repository), and use that runner; do not assume pytest." |
| `docs/commands/implement-tasks/implement-tasks.md:39` (위 문장 뒤) | 없음 | "Before you change the code, run the tests you wrote and confirm they fail; a test that passes on the unchanged code does not show the behavior the task asks to change, so correct it before you go on." |
| `docs/commands/implement-tasks/implement-tasks.md:131` ("... and the tests you wrote." 뒤) | 없음 | "Find out how this repository runs its tests before you run them (its contributing guide, `tox.ini`, `setup.cfg` / `pyproject.toml`, or a test script in the repository), and use that runner; do not assume pytest." |

### rubric 변경

`reward/rubric.yaml`을 `5946117a`와 `HEAD`에서 항목 id마다 비교한 것임. `generated:` 자체 점검 값은 넣지 않음.

| 항목 id | 처리 | 내용 |
|---|---|---|
| `global.penalty.plan_files.named_covers_gold` | 합치면서 들어옴 | `616c75b0`이 되살린 penalty 항목. tasks.md가 적은 소스 파일에 정답 패치의 소스 파일이 모두 있으면 1. 못 푼 롤아웃만 이 값으로 받고, 푼 롤아웃의 `penalty_solved`에서는 1. 정답 패치가 없는 과제에서는 판정 불가로 평균에서 빠짐. |
| `implement_tasks.penalty.phase2_own.reproduced` | 더함 | penalty 항목(log_only, kind `agentos_bugfix.penalty`). 자기 테스트를 썼고 소스를 바꾼 런에서, 첫 소스 변경 전의 자기 테스트 결과 중 실패가 있고 소스 변경 뒤의 자기 테스트 결과 중 통과가 있으면 1. 자기 테스트가 없거나 소스를 바꾸지 않은 런은 해당 없음이고 0. 근거는 implement-tasks.md:39의 새 문장. |
| `scoring.item_signals` (항목 밖) | 더함 | `true`. 채점된 항목마다 `agentos_bugfix/<항목 id>` 신호를 냄. 기록용이고 준수율에 들어가지 않음. |

## PHASE 3가 마지막 변경 뒤의 테스트 실행을 다시 돌리지 않음 (2026-11-23)

### 변경 내역

wf1121 학습 분석(`rllm-home/eval_results/wf1121_traj/analysis-2026-11-23/REPORT.md`의 N-1)에 따른 변경임. 원본 agent-os v2.1.1은 PHASE 2에서 자기 테스트만, PHASE 3에서 전체 테스트를 돌림. T1(`1099e424`)이 기존 테스트 실행을 PHASE 2로 앞당기면서 PHASE 3에 같은 테스트를 한 번 더 돌리라는 문장이 남았고, wf1121 step 23에서 PHASE 3을 정할 수 있는 200개 중 176개가 이미 마지막 변경 뒤에 그 테스트를 돌린 상태였음.

| 결정 | 바꾼 것 | 커밋 |
|---|---|---|
| N-1 | implement-tasks PHASE 3의 테스트 단계가, 마지막 코드·테스트 변경 뒤에 이미 돌린 실행이 있으면 그 결과를 쓰고 없을 때만 돌리라고 말함(`build.py` T1 편집). 최종 검증 실행을 보는 준수율 항목 4개가 PHASE 3 구간 대신 마지막 변경 뒤부터 보고서 전까지의 실행을 봄(`agentos_v2/reward/checks.py`의 새 설정값 `final_code`, 기본값은 지금 동작이라 agentos_v2는 그대로). 같은 테스트를 PHASE 3에서 다시 돌리라던 penalty 항목 `phase3_run.existing_and_own`을 뺌: 바뀐 기준에서는 `phase2_run.existing_and_own`과 같은 것을 봄. penalty 항목은 10개(파일 3, 테스트 7). PHASE 3 실패 처리 항목 3개와 `code_frozen`은 그대로 PHASE 3 구간을 봄. | 이 커밋 |

### 문서 변경

`workflows/agentos_bugfix/` 아래 새 글의 줄임. 줄 수는 바뀌지 않음.

| 문서 위치 | 전 | 후 |
|---|---|---|
| `docs/commands/implement-tasks/implement-tasks.md:131` (PHASE 3 Step 2 첫 문장) | "Run the tests of the changed code once more: the test modules that cover the files you changed, and the tests you wrote." | "The tests of the changed code are the test modules that cover the files you changed, and the tests you wrote. If you ran them after your last change to the code or the tests, take the results of that run; otherwise run them now." |

### rubric 변경

| 항목 id | 처리 | 내용 |
|---|---|---|
| `implement_tasks.run.agentos_bugfix_verify.suite_run` | 설정값을 바꿈 | `final_code: true`. 마지막 코드·테스트 변경 뒤부터 보고서 전까지 유효한 테스트 실행이 있으면 통과(PHASE 2든 PHASE 3든). 변경이 없는 런은 전처럼 PHASE 3 구간을 봄. 인용문을 새 문장으로 바꿈. |
| `implement_tasks.final_verification.agentos_bugfix_report.test_counts` | 설정값을 바꿈 | `final_code: true`. 보고서의 수치를 위 실행들과 비교함. |
| `implement_tasks.final_verification.agentos_bugfix_report.failed_listed` | 설정값을 바꿈 | `final_code: true`. 위 실행들의 실패를 보고서가 적었는지 봄. |
| `implement_tasks.final_verification.agentos_bugfix_report.suite_status` | 설정값을 바꿈 | `final_code: true`. 위 실행들에 실패가 없을 때만 All Passing. |
| `implement_tasks.penalty.phase3_run.existing_and_own` | 뺌 | PHASE 3 안에서 기존 테스트와 자기 테스트를 다시 돌렸는지 보던 penalty 항목. |

## 실패한 기존 테스트는 테스트가 아니라 코드로 고침 (2026-11-23)

### 변경 내역

wf1121 학습 분석(`REPORT.md`의 N-3)에 따른 변경임. 문서는 기존 테스트 줄의 수정을 금지하지만(overview.md 86-87, create-tasks.md 129), PHASE 2 실패 처리 penalty 항목 두 개는 실패한 기존 테스트의 기대값을 바꿔 통과시킨 것도 "고치고 다시 돌려 통과"로 인정했음. 금지는 준수율에만 있어, 준수율이 곱해지지 않는 못 푼 rollout에서는 비용이 없었음. 예: wf1121 step 23 moto-6159 4번 rollout은 바꾼 에러 메시지 때문에 기존 테스트가 실패하자 테스트의 기대 메시지를 바꿔 통과시켰고, 숨은 테스트는 원래 메시지를 확인해 못 푼 것으로 판정됨.

| 결정 | 바꾼 것 | 커밋 |
|---|---|---|
| N-3 | `phase2_fail.edited_after_fail`과 `phase2_fail.last_result_pass`에서, 기존 저장소 테스트 파일의 원래 줄을 바꾸거나 지운 수정은 그 파일의 실패한 테스트에 대한 수정 시도로 세지 않고, 그 수정 뒤의 통과는 다시 통과로 세지 않음(`reward/penalty_tests.py`의 `pass_after_loosening`). 원래 줄을 바꿨는지는 준수율 항목 `test_file_write`와 같은 근거로 판정함(trace의 쓰기가 원래 줄을 지웠는지, 최종 patch가 원래 줄을 바꾸는지). 소스로 고친 통과, 변경 없이도 실패하는 것으로 확인한 실패, 보고서의 expected failure, ⚠️는 그대로 인정함. 기록용 신호 `agentos_bugfix/penalty_expected_failure_claims`(보고서가 expected failure라고 적어 면제된 실패 수)와 `agentos_bugfix/penalty_loosened_test_files`(원래 줄이 바뀐 기존 테스트 파일 수)를 더함. 보상은 이 둘을 읽지 않음. PHASE 3 실패 처리 항목은 그대로 둠. | 이 커밋 |

### 문서 변경

없음. 문서는 이미 기존 테스트 줄의 수정을 금지함.

### rubric 변경

| 항목 id | 처리 | 내용 |
|---|---|---|
| `implement_tasks.penalty.phase2_fail.edited_after_fail` | 설명만 바꿈 | note에 "기존 테스트 파일의 원래 줄을 바꾼 수정은 그 파일의 실패한 테스트에 대한 시도가 아니고, 그 뒤의 통과는 세지 않음"을 더함. 규칙은 `reward/penalty_tests.py`. |
| `implement_tasks.penalty.phase2_fail.last_result_pass` | 설명만 바꿈 | 위와 같음. |

## compliance를 측정 대상별 신호 3개로 계산 (2026-11-24)

### 변경 내역

compliance 식을 바꿈. 보상식(`0.7 · verifier · (0.7 + 0.3 · compliance) + 0.3 · penalty`)과 penalty 항목은 그대로임.

| 결정 | 바꾼 것 |
|---|---|
| 신호 3개 | `compliance = 0.3 · form + 0.3 · accuracy + 0.4 · action`. 각 신호는 속한 항목의 가중 통과율(must 1.0, should 0.25). 단계별 structure × content 곱셈, 신호 6개(단계 4개, order, process)의 평균을 없앰(`workflow_rubric/aggregate.py`의 `three_signals`, rubric의 `scoring.aggregate: three_signals`). |
| 항목의 신호 | accuracy는 문서 내용을 과제·저장소·실행 기록과 대조하는 15개 항목(`derive_rubric.py`의 `ACCURACY`). action은 class가 evidence인 나머지 항목과 금지 규칙 2개(`ACTION`), 그리고 아래 미리 읽기 항목. form은 그 밖의 항목(파일, 절 제목, 라벨, 필드 채움과 형식). |
| 게이트 | 게이트 15개(단계 점수 0, 상한 0.1)를 조건으로 쓰지 않음. 일반 항목으로 채점됨. |
| 단계 수행 여부 | 단계는 명령 문서 하나와 그 산출물 하나의 쌍임(shape-spec.md와 requirements.md, write-spec.md와 spec.md, create-tasks.md와 tasks.md, implement-tasks.md와 저장소 수정). 수행한 단계는 세 조건을 모두 만족함: 산출물이 있고 자기 내용이 50단어 이상, 산출물을 처음 쓰기 전에 그 단계의 명령 문서를 읽음, 앞 단계 산출물 중 쓰인 것은 모두 자기 산출물보다 먼저 쓰임. 수행하지 않은 단계의 항목은 모두 0점이고, global 항목은 수행한 단계의 비율만큼만 인정됨(`reward/stages.py`의 `agentos_bugfix.stage_done`). |
| 자기 내용 | 산출물에서 제목 줄, 명령 문서에 그대로 있는 줄, 명령 문서의 대괄호 문구, 굵은 라벨, 채움 표시만 있는 줄을 빼고 남은 단어 수(`stages.own_words`). 템플릿 복사와 머리말만 쓴 문서는 0단어임. |
| order 항목 | 채점하지 않음(판정과 기록은 계속함). 읽고 씀과 산출물 순서는 단계 수행 여부가 맡음. |
| 미리 읽기 | 다음 단계 문서를 앞 단계 산출물을 쓰기 전에 읽은 것은 단계를 무효로 하지 않고, action 신호의 항목 1개로 감점함. 점수는 write-spec.md, create-tasks.md, implement-tasks.md 중 미리 읽지 않은 문서의 비율, 가중치 8(`agentos_bugfix.read_ahead`). |
| 자체 검증 기준값 | `template_copy_stage_max` 0.1을 0.76으로, `no_artifacts_stage_max` 0.0을 0.22로 바꿈. 계획 문서가 템플릿 복사이거나 없어도 implement-tasks.md를 읽고 저장소를 고쳤으면 구현 단계는 수행한 것으로 보기 때문임. 계획 세 단계는 0점이고 compliance는 각각 0.29, 0.11임. |

### 문서 변경

없음.

### rubric 변경

| 항목 id | 처리 | 내용 |
|---|---|---|
| `global.run.order.commands` | 채점에서 뺌 | `log_only: true`. 판정 결과는 항목 신호로 계속 기록됨. |
| `global.run.read_ahead` | 더함 | 미리 읽지 않은 문서의 비율. evidence, must, 가중치 8. |
| `shape_spec.stage.carried_out` | 더함 | 단계 수행 여부. `log_only: true`(집계가 읽기만 함). 문서 SS, 산출물 requirements. |
| `write_spec.stage.carried_out` | 더함 | 위와 같음. 문서 WS, 산출물 spec. |
| `create_tasks.stage.carried_out` | 더함 | 위와 같음. 문서 CT, 산출물 tasks. |
| `implement_tasks.stage.carried_out` | 더함 | 위와 같음. 문서 IT, 산출물은 저장소의 첫 수정. |

## 확인

- `python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream <v2.1.1 worktree> --check`
- `pytest recipe/grpo/qwen3_5/tests/test_agentos_bugfix.py` (뺀 단계의 단어가 문서에 남지 않았는지, Step·절
  번호, 남긴 standards 목록, 문서 5개 업로드, 채점기가 derive 결과와 같은지, 기준 런 점수)
