# agentos_bugfix — agentos_v2 대비 변경 내역

- 만든 이유: agentos_v2 문서를 줄 단위로 검토하던 중, 기능 기획용 단계가 버그 수정 과제와 무관하다는 판단
  (`tasks/2026-11-13-agentos-v2-resolve-review/`, 사용자 결정 2026-11-13).
- 방침: agentos_v2는 그대로 두고, 버그 수정에 필요 없는 단계만 뺀 워크플로우를 따로 둠. 뺀 것과 문구
  일반화 외에는 agentos_v2와 같음 (같은 upstream v2.1.1, 같은 편집, 같은 렌더 방식).
- 문서 분량: 명령 문서 4개 1,329줄 → 832줄, 진입 문서 93줄 → 91줄.

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

## 아직 없는 것

- 채점기(`reward/`): agentos_v2의 채점기를 복사해 뺀 단계의 항목을 지우고 고치는 방식으로 만들 예정.
  그때까지 이 워크플로우는 해결률만 보고함.
- 평가 결과: 아직 한 번도 돌리지 않음.

## 확인

- `python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream <v2.1.1 worktree> --check`
- `pytest recipe/grpo/qwen3_5/tests/test_agentos_bugfix.py` (뺀 단계의 단어가 문서에 남지 않았는지, Step·절
  번호, 남긴 standards 목록, 문서 5개 업로드)
