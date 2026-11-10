# 16. 학습 workflow 포트(AOS·OSF·SKB)에서 빠지거나 바뀐 upstream 규칙 중 되살리면 L1C가 되는 것

질문: 학습 workflow 셋(agent-os → agentos_v2, OpenSpec → openspec_ff, spec-kit bug → speckit_bug)은 학습에 쓰기 좋게 포팅하면서
upstream 규칙을 지우거나 바꿨다. 그중 되살리면 평가(aidlc_v4_ifeval, speckit_sdd)와 반대 방향이 되어 L1C를 만드는 것이 무엇인가.
근거: 각 포트의 `porting/02-gaps.md`, `03-decisions.md`, `later.md`; upstream 원문은 agent-os 6a64951(v2.1.1), OpenSpec 9111a76,
spec-kit 0443760(bug extension 1.0.1). 평가 항목은 `aidlc_v4_ifeval/constraints.yaml`, `speckit_sdd/reward/rubric.yaml`.
층 판정은 10 §3.2대로: 학습 workflow 하나라도 반대를 지시하면 L1C.

## 0. 요약

| | 되살릴 규칙 (출처) | 평가 항목과 왜 반대인가 | ifeval L1C 증가 | SDD L1C 증가 | 되살릴 수 있나 |
|---|---|---|---|---|---|
| A | 테스트를 **저장소 테스트 파일로** 쓴다 (세 포트 모두 `checks/` 스크립트로 바꿈) | 평가는 "테스트 파일을 만들지도 고치지도 않는다"(ifeval 5, SDD 2~3) | +5 | +2~3 | 있음. 채점기와 충돌 확인 필요 |
| B | 산출물을 **저장소 안에** 둔다 (SKB `.specify/bugs/`, AOS `agent-os/specs/` → `/tmp`로 옮김) | 평가는 "저장소에 미선언 파일·재현 스크립트가 남지 않는다"(ifeval 2, SDD 1) | +2 | +1 | 있음. 패치에 섞이는 비용 |
| C | **의존성 갱신·설치** (AOS conventions 7행 삭제, OSF tasks 예시 1.2 교체) | 평가는 "설치·환경 설정 금지"(ifeval 1) | +1 | 0 | 있음. 드물게 발동, 환경 깨뜨릴 위험 |
| D | **feature branch·커밋** (AOS conventions 5행, migrations 9행 삭제) | SDD는 "git branch 금지"(1) | 0 | +1 | 있음. 패치는 시작 커밋 대비 diff라 커밋해도 남음 |
| E | **질문하고 멈춘다** (세 포트 모두 "가장 타당한 답을 가정하고 기록"으로 바꿈) | 평가는 "질문 파일 없음·입력 요청으로 끝내지 않음"(ifeval 2, L2M), "표식을 해소"(SDD 1) | +2 | +1 | 명목상만. 멈추면 패치가 없어 SWE 보상 0 → 모델이 지시와 반대로 학습 |
| F | **이슈의 github.com 링크를 묻지 않고 fetch** (SKB URL Trust Policy → "열지 않음") | SDD는 "이슈 링크 fetch 금지"(1) | 0 | +1 | 명목상만. 링크가 수정 PR로 이어져 누출 |
| 합계 (A~D) | | | 5 → **13** | 3 → **8** | |
| 합계 (A~F) | | | 5 → 15 | 3 → 10 | |

비교: BMAD를 학습에 추가하면 확정 +6/+2 (14 문서). A 하나만 되살려도 +5/+2~3이라, 새 workflow 없이 비슷한 양이 나온다.

## 1. 확정 후보 (되살릴 수 있고, 반대 방향이 분명한 것)

### A. 테스트를 저장소 테스트 파일로 쓴다 — 세 포트 모두 바꾼 것

| 출처 | upstream 지시 (말로) | 포트가 바꾼 것 |
|---|---|---|
| AOS `create-tasks-list.md:41-58`, `implement-tasks.md:15`, `standards/testing/test-writing.md` | task group마다 "1.1 집중 테스트 2~8개를 쓴다", 구현 뒤 "1.1에서 쓴 테스트만 돌린다", Group 4는 "전략적 테스트 10개까지 추가". 테스트는 저장소의 테스트 파일이다 | G9-1: 순서는 두되 테스트를 `S/checks/` 스크립트로 쓰고 저장소 테스트 파일은 절대 쓰지 않는다 |
| OSF `schema.yaml:225-236`, verify `SKILL.md:132-138` | "각 task group은 자기 일이 요구하는 테스트와 문서를 함께 land한다"(테스트를 마지막 group에 모으지 말 것); verify는 "시나리오를 덮는 테스트가 있는지" 보고 없으면 "테스트 추가" 권고 | G9-1·G9-3: fork schema에서 "기존 저장소 테스트를 돌리거나 `checks/` 스크립트"로, "테스트 파일 추가·편집 금지"; verify 권고는 "checks/에 추가" |
| SKB `speckit.bug.assess.md:149`, `speckit.bug.fix.md:49` | assess가 "추가·갱신할 테스트"를 적고, fix가 "그 테스트를 추가·갱신해 회귀가 조용히 지나가지 못하게 한다" | G9-1: `BUG_DIR/checks/`에 체크를 쓰고 저장소 테스트는 기존 것만 돌린다; assess 문서에 "저장소에 테스트 파일을 추가·편집할 계획을 세우지 말 것" 추가 |

반대가 되는 평가 항목 (평가가 요구하는 것):
- ifeval: 계획 단계가 테스트 파일을 대상으로 잡지 않는다 (`a3.item_format.no_test_target`, `a3.cross_ref.3`); 기존 테스트 파일을 고치지 않는다 (`global.run.prohibited_action.test_file_write`); 생성 기록의 "Test files modified: none"이 참이다 (`a4.field_literal.test_files_modified`); 최종 diff에 테스트 경로가 없다 (`a5.field_literal.test_files_in_change`). 5개, 지금 전부 L1.
- SDD: 테스트 파일 쓰기 금지 (`global.run.prohibited_action.test_file_write`), 생성 파일에 테스트 경로 없음 (`speckit_sdd_created_files.tests`); 그리고 story의 테스트 task가 `checks/` 아래 파일을 가리켜야 한다는 `tasks.story_tests` — 학습이 저장소 테스트를 쓰게 하면 테스트 task가 저장소 경로를 가리키게 되므로 반대. 2~3개.

되살리는 방법과 비용: 11 §5의 두 번째 포팅 결정("테스트를 저장소 테스트 파일로 vs checks/ 스크립트로")을 저장소 쪽으로 바꾸면 된다. 비용은 채점기: SWE-Gym `eval.sh`는 테스트 패치가 건드리는 테스트 파일을 복원한 뒤 패치를 적용하는데, 에이전트가 **같은 경로에 새 테스트 파일을 만들어 두면** `git apply`가 실패해 보상 0이 된다(테스트 패치가 새 파일을 추가하는 instance 비율을 재야 함). 기존 테스트 파일을 고친 경우는 패치가 복원하므로 채점에 영향 없음. 포트 당시의 근거(`prepare_swegym.py:177` "테스트 파일은 처리돼 있으니 고치지 말라"는 task 문구)는 과제 메시지이지 workflow 규칙이 아니므로, 메시지를 바꾸거나 workflow가 우선한다고 적어야 한다.

### B. 산출물을 저장소 안에 둔다

| 출처 | upstream | 포트 |
|---|---|---|
| SKB assess/fix/test 전체 | 모든 보고서와 체크는 `.specify/bugs/<slug>/`(저장소 안) | G5-1: `/tmp/speckit/bugs/issue/`; G9-2 "project workspace 밖 수정 금지"를 "저장소 밖 수정 금지, 보고서·체크 예외"로 |
| AOS `initialize-spec.md:46` 등 | `agent-os/specs/<date>-<name>/`(저장소 안), 구현 보고·검증 보고도 그 아래 | G5-1·G5-7: `/tmp/agent-os/specs/…`; "workflow의 어떤 것도 `/testbed`에 쓰지 않는다" |

반대가 되는 평가 항목: ifeval "Unintended files in the repository: none"이 참 = 미선언 untracked 파일이 없고 재현 스크립트가 남지 않음 (`a5.field_literal.unintended_files`), 재현 스크립트가 저장소 안에 남지 않음 (`build_and_test.run.cross_ref.repro_not_left`; 체크 스크립트가 `.specify/bugs/issue/checks/`에 있으면 저장소 안이다). SDD 생성 파일에 spec/plan/tasks/repro/check 류 이름이 없음 (`speckit_sdd_created_files.scratch`; 패턴이 경로 어디서든 그 이름을 잡는다).

비용: 포팅 교훈대로 산출물이 패치에 섞이거나 `git clean`에 지워진다(lessons "Artifacts inside the repo"). 채점에는 영향 없다(hidden test는 untracked 파일을 보지 않음).

### C. 의존성 갱신·설치

| 출처 | upstream | 포트 |
|---|---|---|
| AOS `standards/global/conventions.md:7` | "의존성을 최신·최소로 유지한다" | G9-2: 삭제 (유일한 네트워크 유발 줄) |
| OSF `schema.yaml:245`, `:172` | tasks 예시 "1.2 package.json에 의존성을 추가하고 설치가 성공하는지 확인"; design 작성 조건 "새 외부 의존성" | G9-4: 예시 1.2를 체크 스크립트 예시로 교체; design 조건은 유지 |

반대가 되는 평가 항목: ifeval "의존성 설치·환경 설정 금지" (`global.run.prohibited_action.install`). 1개.
비용: 과제 환경은 고정이고(`/opt/miniconda3/envs/testbed`) 설치가 환경을 깨뜨릴 수 있다. 발동도 드물다(새 의존성이 필요한 이슈가 적음) → 습관으로 자리잡기 어려운 약한 L1C.

### D. feature branch · 커밋

| 출처 | upstream | 포트 |
|---|---|---|
| AOS `conventions.md:5` | "명확한 커밋 메시지, feature branch, 설명 있는 PR" | G9-2: 삭제 |
| AOS `standards/backend/migrations.md:9` | "migration은 항상 버전 관리에 커밋" | G9-5: 삭제 |

반대가 되는 평가 항목: SDD "git branch 만들기 금지" (`global.run.prohibited_action.git_branch`; `git checkout -b`, `git switch -c`, `git branch <name>` 패턴). 1개. ifeval에는 git 항목이 없다.
비용: 작다. 패치는 "시작 커밋 대비 workdir diff"(`run_artifacts.py:9`)라 커밋해도 변경이 남는다. branch 전환은 `/testbed` 안이라 채점에 무관. GSD·PRP(15 문서)처럼 "git 작업을 둘 것인가"가 네 번째 포팅 결정이 된다.

## 2. 명목상 후보 (지시는 되살릴 수 있지만 보상이 반대로 밀어낸다)

### E. 질문하고 멈춘다 — 세 포트가 모두 "가정하고 기록"으로 바꾼 것

| 출처 | upstream | 포트 |
|---|---|---|
| AOS `research-spec.md:45-92,119-148` | "X라고 가정하는데 맞나요?" 질문 4~8개를 출력하고 STOP, 답을 받은 뒤 후속 1~3개를 또 묻고 STOP; `1-determine-tasks.md:1-13` "모든 task group을 진행할까요?"; `2-implement-tasks.md:17-23` 한 group 끝나면 "남은 task 계속할까요?" | G4-1·G4-4·G4-5: 질문은 만들되 스스로 답해 `(assumed) <답> — <근거>`로 기록, 묻지 않음; 모든 group을 순서대로 |
| OSF `ff:94-96`, `schema:182-187,205-207`, `apply:116,185,189` | "맥락이 매우 불분명하면 사용자에게 묻는다"; design Open Questions "spec·접근·task를 바꿀 질문이면 추측 말고 사용자에게 묻는다"; apply "불분명하면 멈추고 묻는다, 추측 금지" | G4-2·G4-3·G4-4: 가장 타당한 해석을 택해 Decisions/tasks에 기록하고 계속 |
| SKB `speckit.bug.fix.md:45`, `assess.md:81,127` | `[NEEDS CLARIFICATION]`이 남아 있으면 interactive면 묻고, automated면 stop | G4-3: 가장 타당한 해석을 가정으로 기록하고 진행 |

반대가 되는 평가 항목: ifeval 질문 파일을 만들지 않음 (`global.run.no_question_file`), 입력 요청 메시지로 끝내지 않음 (`global.run.no_request_for_input`) — 둘 다 지금 L2M; SDD 표식을 해소함 (`item_format.clarifications_resolved`).
왜 명목상인가: 여기는 답할 사람이 없다. 텍스트만 보내고 멈추면 세션이 끝나 패치가 없고(lessons "A text-only reply ends the session") SWE 보상이 0이다. "질문을 파일에 쓰고 blocked로 끝낸다"로 포팅하면(BMAD HALT 형태, 14 §1.2(c)) 지시는 남지만, 그 rollout은 R=0이라 GRPO가 묻지 않는 쪽으로 민다. 즉 문서는 반대를 지시하되 보상은 평가와 같은 방향 → 학습된 습관은 생기지 않는다. 11 §5의 첫 번째 결정(HALT vs 가정)과 같은 문제.

### F. 이슈의 github.com 링크를 묻지 않고 fetch

| 출처 | upstream | 포트 |
|---|---|---|
| SKB `speckit.bug.assess.md:47-63,76` | URL Trust Policy: github.com·gitlab.com 등은 "묻지 않고 fetch"가 "이 workflow가 설계된 편한 경로"; 그 밖의 host는 automated면 fetch 않고 `[UNVERIFIED — fetch skipped]` | G6-1: fetch·온라인 조회 금지, 링크는 `[UNVERIFIED — not fetched]`로 기록 |

반대가 되는 평가 항목: SDD 이슈 링크를 열지 않음 (`speckit_sdd_no_fetch.issue_links`). ifeval에는 fetch 항목 없음.
왜 명목상인가: SWE 이슈의 링크는 수정 PR로 이어진다(lessons "Leaks"). 되살리면 정답 누출이라 학습 자체가 망가진다. 네트워크를 막으면 지시는 남지만 실행이 안 돼 습관이 생기지 않는다.

## 3. 되살려도 L1C가 되지 않는 것 (반대로 보이지만 평가 항목과 안 맞음)

| 삭제·변경된 규칙 | 왜 L1C가 아닌가 |
|---|---|
| AOS `coding-style.md:8-10` 죽은 코드 삭제·역호환 불필요·DRY, `conventions.md:4,11` README·changelog 갱신, OSF `schema:251` "docs/export.md에 문서화" (모두 삭제·교체) | 계획 밖 편집을 늘리지만, ifeval의 계획 준수 항목(T-TR2)은 "계획한 Target이 모두 쓰였는가"(계획 ⊆ 쓰기)라서 추가 편집은 위반이 아니다. 기록 대조(T-RF3)도 추가 편집을 기록하면 통과. 반대가 되는 것은 과제 문구 "non-test 파일 최소 변경"뿐이고 그것은 평가 항목이 아니다 |
| AOS `update-roadmap.md` roadmap `- [x]` 체크 (이 프로젝트에는 roadmap 없음으로 처리), later.md plan-product 변형 | 체크박스 체크는 카탈로그의 예외(T-WD4)라 "한 번 쓰기"(`once`)와 반대로 치지 않는다. 13 문서에서 AOS tasks.md 체크를 같은 이유로 비충돌로 판정 |
| SKB `test.md:56` "비싼 체크는 건너뛴다" ("expensive" 삭제) | 허용이지 지시가 아니다. ifeval의 "첫 편집 전 테스트 실행"(T-AW2)·"마지막 편집 뒤 실행"(T-AW3)과 반대 방향의 지시가 되려면 "돌리지 말라"여야 한다 |
| SKB `fix.md:51` "assessment이 틀렸으면 STOP, re-assess 권고", OSF verify→apply 루프(G8-1, 0/60 발동으로 삭제), AOS later.md "검증 뒤 수정 라운드" | 앞 단계로 돌아가기 = ifeval `no_return`과 반대인데, 그 항목은 SKB fix↔test 라운드 때문에 이미 L1C다. 보강이지 증가가 아님 |
| SKB `assess.md:91,173` "invalid / not a bug" 판정 후 중단 (삭제) | 평가 항목에 대응물 없음. 이슈를 invalid로 판정하면 패치가 없어 보상 0 |
| AOS `research-spec.md:115-117` "유사 기능 경로를 직접 탐색하지 말라(시간 절약)" (삭제) | ifeval·SDD에 "저장소 파일을 읽지 말라"와 반대인 읽기 요구 항목이 없다 (SDD T-RD5는 constitution·README 류) |
| OSF explore "결정은 파일이 아니라 대화에 남긴다"(G2-12, think 호출 요약으로 변경), 포착 경로 삭제(G4-13), "수동 scaffold 금지" 삭제(G7-10) | 평가 산출물과 무관 |
| OSF MODIFIED/REMOVED 델타가 발동 안 함(빈 main spec; later.md brownfield 변형) | 평가 workflow에 델타 spec이 없다 |
| AOS `tech-stack.md` 미배포(G7-6, later.md 채운 변형) | 지시가 아니라 정보 |

## 4. 포트가 **추가**해서 이미 L1C를 만든 것 (참고)

- SKB G9-5(포트 추가, upstream에 없음): 코드 편집 전에 이슈 예시를 체크로 옮겨 **즉시 실행해 실패를 확인**한다. ifeval의 "주어진 파일을 창 안에서 실행하지 않는다(지연 실행)"(T-AW4)가 L1C인 이유의 하나(templates.yaml 사유: "SKB rewards running each check at once before the edit"). 되살리기와 반대로, 이것을 빼면 L1C가 하나 줄어든다.
- OSF G4-5·G4-6(변경): 구현 중 설계 문제가 드러나면 design/spec/tasks를 **스스로 고치고** 계속; 범위 밖 작업은 tasks.md에 task로 추가. upstream은 "멈추고 사용자에게 제안"이었다. 조건부라 13 문서에서 ifeval `once`/`order(rewrite)`의 반대로 치지 않았다. 조건을 떼어 "task마다 design Decisions 갱신"처럼 무조건으로 만들면 BMAD식으로 `once` ×5 + `order.stages`가 L1C가 되지만, 그것은 되살리기가 아니라 새로 만드는 것이다.

## 5. 정리

- 되살려서 실제로 L1C가 되는 것은 네 가지(A~D), ifeval 5 → 13, SDD 3 → 8. 셋 모두에서 지운 것은 A(저장소 테스트)와 E(질문)이고, A가 가장 크다(+5/+2~3).
- A·B는 11 §5의 포팅 결정 둘(테스트 위치, 산출물 위치)을 뒤집는 것이고, D는 GSD·PRP 때 나온 네 번째 결정(git 작업)이다. 어느 것이든 포트 전체에 걸친 결정이라 한 workflow만 바꾸면 학습 내부 충돌(AOS는 저장소 테스트, SKB는 checks/)이 생긴다. 셋을 같이 바꾸거나, 의도적으로 하나만 바꿔 학습 내부 충돌을 만들지 정해야 한다.
- E·F는 지시만 되살아나고 보상이 반대라 L1C로 세어도 습관이 생기지 않는다.
- 삭제된 conventions·coding-style 줄은 "실제 개발 관행"(later.md)이지만 평가 항목과는 반대가 아니다.
