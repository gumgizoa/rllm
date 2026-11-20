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
| T1 | 테스트 실행 범위 | 구현 중(implement-tasks PHASE 2, create-tasks 예시·제약): "자기가 쓴 테스트만 실행". 최종 검증(PHASE 3): "전체 테스트를 실행" | 두 곳 모두 "자기가 쓴 테스트 + 수정한 코드의 기존 테스트". 전체 테스트는 몇 분 안에 끝날 때만 추가로. 구현 중 문장에 "task가 바꾸라고 한 동작을 기대하는 기존 테스트는 실패하는 것이 맞으니 수정을 그대로 두고 그 테스트를 최종 보고서에 적는다"를 덧붙임. "이 단계에서 전체 테스트를 돌리지 말 것"은 그대로 | 구현 중에는 기존 테스트가 안 돌고, 마지막의 전체 테스트는 거의 지켜지지 않음. 평가(wf-floor-tcx): 정답 test patch가 건드리는 파일을 실행한 런 73.8% → 58.9%, 편집 뒤 테스트 횟수 7.2 → 4.5, 전체 테스트를 돌린 런 6.8%(34런 중 시간 초과 12) |
| T2 | 테스트 작성 기준 | implement-tasks의 test-writing standard 7줄 | "개발 중 테스트는 최소로", "핵심 사용자 흐름만 테스트", "edge case 테스트는 미룸" 세 줄을 뺌. 나머지 4줄(동작을 테스트, 이름, mock, 속도)은 그대로 | 버그 수정은 특정 입력의 예외 동작이 대상인 경우가 많고, 그것을 재현하는 테스트가 곧 edge case 테스트임. 따로 잰 수치는 없음. create-tasks 예시의 "Skip exhaustive coverage of all methods and edge cases" 등 같은 취지의 4줄은 손대지 않음 |
| T3 | 구현 중에 찾은 작업 | 명령이 끝난 파일은 고치지 않음. tasks.md는 체크박스만 예외. "배정된 task만 구현" | 구현 중에 task에 없는 필요한 작업(고칠 다른 파일, 빠진 경우)을 찾으면 tasks.md에 먼저 추가한 뒤 배정된 task로 구현함. 줄 추가만 허용하고 있던 task는 고치거나 지우지 않음. spec.md·requirements.md는 그대로 고치지 않음 | 계획에 적힌 것이 곧 고쳐지는 범위임(평가 wf-floor-tcx: 계획이 정답 파일을 모두 담은 런은 정답 파일을 모두 고친 비율 89.5%, 다 담지 못한 런은 24.1%). 새로 찾은 작업을 정식으로 구현할 길을 둠. 모델이 이 길을 쓸지는 확인되지 않음 |
| T4 | 보고서의 전체 Status | 머리의 Status 칸에 세 값(Passed / Passed with Issues / Failed)만 있고 언제 무엇을 적는지 기준이 없음 | 보고서 양식 뒤에 기준을 적음: 두 절의 Status에서 정해짐. All Complete + All Passing이면 Passed, ⚠️로 표시한 task가 있거나 이 변경을 위해 쓴 것이 아닌 테스트가 실패하면(Some Failures) Passed with Issues, 이 변경을 위해 쓴 테스트가 실패하면(Critical Failures) Failed | 평가(wf-floor-tcx)에서 보고서의 96.2%가 Passed이고, 그중 61런은 마지막 검증이 실패, 42런은 같은 보고서의 Failing 칸이 1 이상. 해결률보다 보고서 정확도의 문제 |
| T5 | 실패한 테스트를 두고 체크함 | 구현 단계에 "테스트가 통과하도록 한다"만 있음 | "수정 때문에 테스트가 실패하면 고치고 다시 돌린 뒤에 task group의 마지막 하위 task를 체크한다. 두 번 시도해도 통과하지 못하면 체크 대신 ⚠️로 표시하고 넘어간다". ⚠️가 있어도 PHASE 3으로 넘어감 | 평가(wf-floor-tcx)에서 구현 중 실패를 보고 체크한 뒤 검증 없이 끝낸 런 16개의 해결률 12.5%(같은 과제 미적용 52.1%). 모델마다 크기가 다르고 런 수가 작음 |
| T6 | 검증에서 실패를 보고도 끝냄 | PHASE 3: "실패한 테스트를 고치지 말고 기록만"(upstream 원문). upstream은 사람이 보고서를 읽고 다시 시킴 | 실패하면 수정 때문인지 확인(자기가 쓴 테스트면 그렇다, 기존 테스트면 `git stash -q && <테스트 명령>; git stash pop -q` 한 줄로 수정 없이 돌려 봄). 수정 때문이고 옛 동작을 기대하는 테스트가 아니면 PHASE 2로 한 번 돌아가 고치고 PHASE 3을 Step 1부터 다시 함. 한 번만. 그 밖의 실패는 그대로 기록만 | 평가(wf-floor-tcx)에서 마지막 검증이 실패인 채 끝난 런 6.1% → 14.1%, 손실 차이 −11.2. 그중 PHASE 3에서 실패를 본 런 50개(해결률 44.0%, 미적용 52.0%). 위험: 실패한 채로도 풀린 런이 있어 판단이 틀리면 옳은 수정을 망가뜨림. `git stash pop`을 빠뜨리면 수정이 사라지므로 한 줄 명령으로 지정함 |
| T7 | 수정 task에 고칠 파일을 적음 | create-tasks: "task는 구체적이고 확인 가능하게"만 있고, 예시의 수정 하위 task(1.2, 1.3)에는 파일 자리가 없음 | 제약에 한 줄을 넣음: "코드를 고치는 하위 task는 그 task 줄에 고칠 파일의 저장소 경로를 적는다. 구현 중에 추가하는 task도 같고, 그 파일을 고치기 전에 추가한다". 예시의 1.2, 1.3 줄을 `[First change to make] in [path of the file to change]` 꼴로 바꿈 | 평가(t6-full-floor27) 499런 중 31.9%(159런)가 수정 task에 파일을 하나도 적지 않음. 적은 파일과 실제 수정을 대조하는 채점(`ticked_after_work`, penalty 항목)은 파일이 적혀 있어야 판정할 수 있음. 파일을 적은 런의 해결률이 더 높다는 근거는 없음(난이도를 뺀 차이 +6.3, 구간 −1.1 ~ +13.9). 모델이 이 줄을 따를지는 확인되지 않음(이 문서로 돌린 런 없음) |
| T8 | 실패 뒤 고칠 대상에 자기 테스트를 넣음 | implement-tasks PHASE 2 (T5): "내 변경 때문에 테스트가 실패하면 변경을 고치고 테스트를 다시 돌린다" | "내 변경 때문에, 또는 내가 쓴 테스트 자체가 틀려서 실패하면 변경이나 그 테스트를 고치고 다시 돌린다"로 바꿈. 기존 테스트 줄은 바꾸지 않는다는 규칙(create-tasks)과 PHASE 3의 "PHASE 2로 한 번 돌아가 변경을 고친다"는 그대로 | 문서에는 테스트를 고치라는 말이 없었는데, 평가(t6-full-floor27)에서 PHASE 2에 실패를 본 런의 81%가 그 뒤에 테스트를 고침. 실패 뒤 소스 또는 테스트를 고친 런의 해결률이 안 고친 런보다 높음(49.7% 대 30.8%, 단순 비교). 이 문구로 돌린 런은 없음 |

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
    `named_covers_gold`: 적은 파일에 정답 파일이 빠지면 감점. `patch_covers_gold`: 최종 patch에 정답 파일이 빠지면 감점(다른 파일이 더 있는 것은 허용).
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

- penalty 항목 11개(파일 4, 테스트 7)를 `post` 밖 계산에서 rubric의 `log_only` 항목으로 옮김 (`derive_rubric.py`의
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


## 확인

- `python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream <v2.1.1 worktree> --check`
- `pytest recipe/grpo/qwen3_5/tests/test_agentos_bugfix.py` (뺀 단계의 단어가 문서에 남지 않았는지, Step·절
  번호, 남긴 standards 목록, 문서 5개 업로드, 채점기가 derive 결과와 같은지, 기준 런 점수)
