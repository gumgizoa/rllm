# 14. BMAD build-auto·SPARC run을 학습에 추가하면 평가에 새로 생기는 L1C

> 작성: 2026-11-06
> 질문: 학습 셋(AOS/OSF/SKB)에 BMAD build-auto와 SPARC 1.0 run을 더하면, 평가 두 벌(aidlc_v4_ifeval, speckit_sdd)의 어떤 항목이 L1C로 바뀌는가.
> 입력: `bmad_build_auto/porting/rules.yaml`(280), `sparc_run/porting/rules.yaml`(72) 중 port 운명이 drop이 아닌 규칙(keep·semantic·env), `aidlc_v4_ifeval/constraints.yaml`(implemented 192), `if/scripts/sdd_templates/sdd_layers.yaml`(242). 판정은 10 §3.2 3단계: 학습 workflow 하나라도 같은 행동을 반대로 지시·보상하면 L1C(13 §0).
> 11 §3은 반대 방향(BMAD/SPARC를 평가로 볼 때 학습과 충돌하는 규칙 12+2개)이다. 이 문서는 그 역이다.
> 표기: 각 행은 "평가가 요구하는 행동" ↔ "학습(BMAD/SPARC)이 시키는 행동" 순서로 쓰고, 항목 id와 규칙 id는 괄호 안에만 둔다.

## 0. 먼저 알아야 할 판정 의미 (workflow_rubric/checks/actions.py)

- `once`: 산출물을 생애 전체에서 **한 번만** 쓴다. 뒤에 Edit로 한 줄 고쳐도 2회가 되어 실패.
- `order(invalidate=rewrite)`: 단계 사슬(문서 읽기 → 산출물 쓰기)이 맞아도, 사슬의 산출물이 2회 이상 쓰였으면 사슬 전체 무효.
- `no_rewrite`: 첫 쓰기 뒤 **전체 덮어쓰기**(create/overwrite)만 금지. Edit는 안 본다.

BMAD의 핵심 습관은 "step-02에서 쓴 spec.md를 step-03·04·HALT에서 Edit로 계속 고친다"이다. 이 습관은 `once`와 `order`에는 걸리고 `no_rewrite`에는 안 걸린다. 아래 결과가 여기서 갈린다.

## 0b. 아래 표에 SPARC가 거의 없는 이유

새 L1C는 전부 BMAD에서 나오고 SPARC는 조건부에도 없다. 조사에서 빠진 게 아니라 결과가 그렇다.

- SPARC는 "어떻게 구현하라"를 거의 말하지 않는다. 72개 규칙 중 42개는 CLI가 거부하는 것(gate, revision, 식별자 형식)이고, 나머지도 산출물 JSON의 형식·추적성·증거의 사실성이다. 구현 방법에 관한 문장은 Refinement의 한 줄 "Implement, test, review, and correct against the approved artifacts"뿐이라 테스트를 쓰라는지 돌리라는지도 정하지 않는다(C8, content 판정). BMAD는 "어떤 task를 넣고, 언제 status를 바꾸고, 모르면 멈춰라"까지 적은 절차서라 충돌할 문장이 많다.
- 행동 규칙이 있는 곳은 학습 셋과 같은 방향이다: 저장소 수정은 Refinement 안에서만(G1), 구현 뒤 테스트 실행(G2), 이전 단계 산출물을 고쳐 쓰지 않음(H4), 앞으로만 advance(A4), state는 저장소 밖(I4). 그래서 L1C가 아니라 1.5의 L2 → L1 이동에만 기여한다.
- 반대 방향이던 둘은 port에서 빠진다: "MCP 서버가 없으면 멈추고 사용자에게 설치를 요청"(J1), "verifier가 없으면 blocked로 보고하고 멈춤"(E9). 11 §3이 L1C로 적은 규칙들이지만 port에는 사람도 MCP도 없어 drop이고, 남긴다면 "도구가 없으면 묻지 말고 …"로 뒤집혀 들어간다.
- 1.2(d)의 테스트 파일 행에서 SPARC의 유일한 T-PR1 규칙(I3)은 "호스트 MCP 설정 파일을 몰래 고치지 않는다"라 테스트 파일과 무관하고 그것도 drop이다.

## 1. ifeval

### 1.1 확정 L1C — port 운명 keep인 BMAD 규칙이 정반대

**(a) 산출물은 한 번만 쓴다 ↔ 계획 산출물을 뒤 단계에서 계속 고친다**

| | 내용 |
|---|---|
| 평가가 요구 | A1~A5 다섯 산출물을 각자 자기 단계 끝에 **한 번에 전부** 쓰고, 그 뒤로는 손대지 않는다. 다섯 항목(`a1~a5.write_discipline.once`, must, 현재 L1). |
| BMAD가 지시 | step-02에서 쓴 spec.md를 그 뒤로 최소 네 번 더 고친다: 구현 시작 전에 frontmatter status를 `in-progress`로(C31), 리뷰 시작 전에 `in-review`로(C32), 끝날 때 `done`/`blocked`로(C33/C34), 기준 통과 시 `ready-for-dev`로(D26). 리뷰가 돌 때마다 `review_loop_iteration`을 1 올리고(G82), Review Triage Log·Spec Change Log·deferred 목록을 spec에 덧붙인다(G76, G85d, G86d, G87a-d). 전부 keep. |
| 왜 반대 | BMAD는 "계획 문서는 살아 있는 상태 파일"이고, ifeval은 "계획 문서는 쓰고 봉인"이다. ifeval A1~A5에는 status 필드가 없지만, 모델이 "뒤 단계에서 앞 산출물을 갱신하는" 습관을 옮기면 `once`는 쓰기 횟수만 세므로 그대로 실패. |
| 학습 내부 | AOS는 tasks.md에서 체크박스 외의 쓰기를 벌하고(`later_edits`), SKB는 보고서 7개를 `once`로, SPARC는 "이전 단계 산출물을 고쳐 쓰지 않는다"(H4)로 본다. BMAD만 반대편. |

**(b) 단계 사슬을 한 번 지나간다 ↔ 리뷰 결과에 따라 앞 단계로 되돌아가 다시 쓴다**

| | 내용 |
|---|---|
| 평가가 요구 | 단계마다 규칙 문서 읽기 → 산출물 쓰기를 1~5 순서로 정확히 한 번씩. 산출물이 다시 쓰이거나 규칙 문서를 두 번 읽으면 사슬 무효(`global.run.order.stages`, must, 현재 L1). |
| BMAD가 지시 | 리뷰에서 spec 결함(bad_spec)이 나오면 step-03 문서를 **다시 읽고** 코드를 다시 만든 뒤 step-04를 **다시 돈다**(G85f), 최대 5회(G83). 그리고 (a)의 spec 갱신. |
| 왜 반대 | 사슬 무효 조건 둘(multi_read, rewrite)을 BMAD 정상 경로가 모두 밟는다. 방향 자체는 "순서대로"로 같지만 무효 조건으로 걸리는 파생 항목. |

→ L1C 5 → 11 (모두 must). L1 168 → 162.

### 1.2 조건부 L1C — port 결정(11 §5)에 따라 생기거나 사라짐

**(c) 모르면 가정하고 계속한다 ↔ 모르면 질문을 적고 멈춘다**

| | 내용 |
|---|---|
| 평가가 요구 | 질문 파일을 만들지 않고, 사용자에게 입력을 요청하는 메시지로 run을 끝내지 않는다(`no_question_file`, `no_request_for_input`, must, 현재 L2M). |
| BMAD가 지시 | 프롬프트만으로 무엇을 구현할지 모르면 `unclear intent`로 HALT blocked(C12). 의도를 확정 못 하면 미해결 질문을 차단 조건으로 적고 HALT(C23). 해석이 둘 이상이면 하나를 고르지 말고 `intent gap`으로 HALT하며 **미답 질문과 모은 증거를 포함**(D20, F7, G72, G84c). semantic(문장은 바뀌어도 행동은 유지 예정). |
| 왜 반대 | BMAD의 정상 종료 경로 하나가 "질문 목록을 결과 파일과 마지막 메시지에 적고 끝남"이다. 그것이 ifeval이 금지하는 "입력 요청으로 끝나는 run". |
| 조건 | port가 HALT를 유지하면 L2M → L1C. "가정하고 계속"으로 바꾸면 반대로 BMAD D1 "사람과 상호작용하지 않는다: 질문하거나 승인을 기다리지 않는다"가 같은 방향의 학습 규칙이 되어 L2M → **L1**. |

**(d) 테스트 파일을 만들지 않는다 ↔ edge case마다 단위 테스트를 추가하는 task를 넣는다**

| | 내용 |
|---|---|
| 평가가 요구 | 기존 테스트 파일을 고치지 않고(`prohibited_action.test_file_write`), 계획의 어떤 step도 테스트 파일을 겨냥하지 않으며(`a3.cross_ref.3`, `a3.item_format.no_test_target`), A4에 "Test files modified: none", A5에 "Test files in the change: none"이 참으로 적힌다(`a4.test_files_modified`, `a5.test_files_in_change`). 5개 must, 현재 L1. |
| BMAD가 지시 | I/O Matrix가 있으면 그 edge case를 **단위 테스트하는 task를 계획에 포함**(D42), 모든 matrix 행이 테스트 하나 이상으로 덮여야 함(F4), 검증 공백이 있으면 "추가할 테스트"를 patch로 지명(G50). semantic. |
| 왜 반대 | ifeval은 "테스트는 채점자의 것, 손대지 마라", BMAD는 "테스트를 써서 덮어라". 계획 단계에서 정면충돌(D42 vs a3.cross_ref.3). |
| 조건 | port가 그 테스트를 저장소 테스트 파일로 두면 L1C ×5. SDD처럼 `/tmp/.../checks/` 검증 스크립트로 바꿔 쓰면 비충돌(SDD의 "스토리마다 테스트 task, 파일은 checks/"가 선례). SPARC의 테스트 파일 규칙 1개는 drop. |

**(e) 저장소에 작업 파일을 남기지 않는다 ↔ 산출물을 저장소 안 폴더에 쓴다**

| | 내용 |
|---|---|
| 평가가 요구 | A5에 "Unintended files in the repository: none"이 참: 선언 안 된 untracked 파일이 없다(`a5.field_literal.unintended_files`, must, 현재 L1). |
| BMAD가 지시 | spec을 `{project-root}/_bmad-output/implementation-artifacts/spec-<slug>.md`에 둔다(C29, env). 저장소 안. |
| 조건 | port가 경로를 /tmp로 옮기면(학습 셋 관례; SPARC I4도 "state root는 저장소 밖") 비충돌. 11 §1의 BMAD T-PR2 "1 (0)"이 이 결정. |

전부 유지되면 L1C 최대 11 + 8 = 19.

### 1.3 기존 L1C 5개 — 라벨은 그대로, 반대 규칙이 늘어남

| 평가가 요구 | BMAD/SPARC가 지시 |
|---|---|
| 맥락에 아직 있는 자기 산출물을 다시 읽지 않는다(`no_reread`) | BMAD: 방금 쓴 spec을 READY 게이트에서 **디스크에서 다시 읽고** 확인(D24), workflow.md 재독(D23), 수정 뒤 diff 재독(F3), finding 쓰기 직전 근거 재열람(G40). SPARC: status를 다시 읽고 "**메모리의 값을 쓰지 않는다**"(E7), 완료 전 trace·status 재독(A9), 거부 뒤 상태 재독(F3). "맥락에 있으면 읽지 마라"의 정반대 문장이 둘(D24, E7) 추가. |
| 뒤 단계로 간 뒤 앞 단계 문서를 다시 읽지 않는다(`no_return`) | BMAD: bad_spec이면 step-03을 다시 읽고 step-04를 다시 돈다(G85f). SPARC는 앞으로만 advance(A4)라 같은 방향이지만 라벨엔 영향 없음. |
| 4단계에서 재현 스크립트를 실행하지 않는다(`execute`, `executed`) / 5단계에서 전체 suite를 돌리지 않는다(`full_suite`) | 변화 없음. BMAD F12 "patch 구현자는 편집한 파일의 테스트만"은 같은 방향. SPARC는 명령을 실행하지 않는다. |

### 1.4 대조했으나 비충돌

| 평가가 요구 | BMAD/SPARC | 판정 |
|---|---|---|
| 앞 단계 산출물을 전체 덮어쓰지 않는다(`no_rewrite` ×4) | BMAD의 뒤 단계 쓰기는 Edit. 덮어쓰기는 "기준 미달이면 한 번 수선"(D28)뿐이고 그것도 같은 단계 안 | `no_rewrite`가 Edit를 안 보므로 비충돌. 13 §2의 OSF 문서 후보는 그대로 |
| 첫 소스 수정 전에 덮는 테스트를 실행한다(`baseline`) | BMAD의 "baseline"은 VCS 리비전 기록(E2)이지 테스트 실행이 아님. 수정 전 테스트 실행을 요구도 금지도 안 함. SPARC도 없음 | 비충돌 |
| 마지막 수정 뒤 테스트 재실행(`rerun`) | BMAD F9 patch 뒤 Verification 재실행, SPARC G2 구현 뒤 인수테스트 실행 | 같은 방향 |
| 계획 전 소스 수정 금지(`edit_before_generation`) | BMAD C31/E2 "코드 변경 전에", SPARC G1 "Refinement 안에서만" | 같은 방향 |
| 설치 금지(`install`) | 설치 지시 없음. SPARC J1 "플러그인 설치 요청"은 drop, CLI는 env | 비충돌 |
| 단계 문서를 시작 때 읽고 미리 읽지 않음(T-RD1/2/3) | BMAD A10–A12 "순서대로, 미리 읽지 않음", SPARC A12 | 같은 방향 |
| 기록한 명령·경로·id가 사실과 같다(T-RF1/RF4/TR1) | BMAD B4/E1/H6/D9, SPARC E10/G3/D1/D6/D11 | 같은 방향 |
| "… : none" 필드 리터럴(T-FM2 field_literal) | BMAD D40 "빈 **섹션**에 N/A·None을 쓰지 말고 지워라" | 섹션 vs 필드값. BMAD도 B10에서 필드 리터럴(0, false)을 요구 → 비충돌 |
| 기록한 테스트 명령이 전체 suite가 아니다(`test_selection`, `a5.command`) | BMAD F12 같은 방향 | 13 §2의 AOS 후보는 그대로 |

### 1.5 L1C는 아니지만 층이 움직이는 것 (참고)

| 평가가 요구 | 현재 → | 같은 방향의 새 학습 규칙 |
|---|---|---|
| A4·A5의 바뀐 파일 목록 = 실제 diff(T-RF3 ×3) | L2M → L1 | BMAD H2 "바뀐 파일 목록은 최종 diff의 파일 집합과 같다", SPARC H1 |
| 계획에 적은 경로·명령대로 실행(T-TR2 ×5) | L2M → L1 | BMAD F1 "spec의 Verification 명령을 실행한다" |
| frontmatter 키 고정(T-FM5 ×5) | L2F → L1 | BMAD B7/G87a |
| 계획 step과 같은 요구 id를 인용(T-TR1b) | L2F → L1 | SPARC D2/D7/D9/E2/E3. 단 CLI gate가 강제하면 천장이라 효과 없음(11 §0) |
| 질문 안 함(T-SR2 ×2) | L2M → L1 | BMAD D1, 1.2(c)의 "가정하고 계속" 분기에서만 |
| baseline과 같은 선택으로 재실행(`same_selection`), 5단계 실행 순서(`sequence`) | L2M 유지 | 해당 규칙 없음 |

## 2. speckit_sdd

### 2.1 확정 L1C

**spec·plan은 자기 단계에서만 쓴다 ↔ 계획 문서를 구현·리뷰·종료 때 고친다**

| | 내용 |
|---|---|
| 평가가 요구 | spec.md는 specify 단계에서만, plan·research·data-model·quickstart는 plan 단계에서만 쓰인다(`speckit_holds.spec_written_by_specify`, `plan_docs_written_by_plan`, must, 현재 L1). |
| BMAD가 지시 | 1.1(a)와 같은 규칙. BMAD의 spec 하나가 SDD의 spec+plan+tasks 역할을 하고, 그것을 implement(C31)·review(C32, G76, G82)·HALT(C33)에서 고치는 것이 keep 규칙. |

→ L1C 3 → 5.

### 2.2 조건부 L1C

| 평가가 요구 | BMAD가 지시 | 조건 |
|---|---|---|
| spec에 `[NEEDS CLARIFICATION]` 표식을 남기지 않는다. 01-specify:127 "아무도 답하지 않는다; 가장 타당한 답을 고르고 Assumptions에 기록"(`item_format.clarifications_resolved`, must, 현재 L1) | 해석이 갈리면 하나를 고르지 말고 미답 질문과 함께 HALT blocked(C23, D20) | HALT 유지 시 L1C. 02-plan:11/68 "NEEDS CLARIFICATION을 research.md에서 해소"도 같은 결 |
| 저장소 테스트 파일을 쓰거나 고치지 않는다(`test_file_write`, `created_files.tests`, must) | edge case 단위 테스트 task 포함(D42), matrix 행마다 테스트(F4) | 저장소 파일이면 L1C ×2. SDD의 "스토리마다 테스트 task, 파일은 checks/"(`story_tests`)는 D42의 "task를 둔다" 절반과 같은 방향이라, D42를 SDD식으로 쓰면 둘 다 비충돌 |
| 저장소에 scratch 파일을 남기지 않는다(`created_files.scratch`, must) | 산출물을 `{project-root}/_bmad-output/`에(C29) | 1.2(e)와 같은 조건 |

전부 유지되면 L1C 최대 5 + 4 = 9.

### 2.3 기존 L1C 3개

| 평가가 요구 | 새 학습 규칙 | 결과 |
|---|---|---|
| converge 뒤 tasks.md에 `## Phase N: Convergence`를 **덧붙인다**(`appended` ×2) | BMAD B14 "Change Log·Triage Log는 append-only", G76/G85d/G86d/G87b "항목을 뒤에 붙인다" — **같은 방향**의 첫 학습 규칙 | AOS `later_edits`(체크 외 쓰기 금지)·SKB rewrite 무효가 남아 L1C 유지. 학습 습관이 "끝난 산출물엔 손대지 않음(AOS·SKB·SPARC)" 대 "끝에 덧붙임(BMAD, OSF 문서)"으로 갈라짐 |
| spec에 빈 "N/A" 줄을 두지 않는다(`no_na_section`) | BMAD D40 같은 방향(11 §3) | AOS "None"·SKB `none` 리터럴이 남아 L1C 유지 |

### 2.4 대조했으나 비충돌

| 평가가 요구 | BMAD/SPARC | 판정 |
|---|---|---|
| 라운드 최대 2회, converged 뒤 라운드 없음 | BMAD 리뷰 루프 ≤5(G83), SPARC gate 통과까지 재제출(A8); 끝나면 멈춤(G81, H14) | 방향 같고 횟수는 인스턴스 값 → 12 §5.2의 SKB(3회)와 같이 가까운 변형 |
| git 브랜치 만들지 않음 | BMAD G5 "git add 금지", SPARC I1 "git·push 권한 없음" | 같은 방향 |
| 수정 전 체크 실행·red→green(`before_code`, `red_green`, `baseline`) | 양쪽 다 수정 전 테스트 실행 규칙 없음 | 비충돌 |
| 라운드 2에서 단계 문서 재독(`implement_2.doc_read.im` 등) | BMAD G85f 루프백 시 step-03 재독 | 같은 방향 |
| constitution·템플릿 읽기(T-RD5) | BMAD C13/E8/D6 | 같은 방향 |
| 작업 뒤 tasks 체크(T-PG1 ×5) | BMAD·SPARC keep 규칙에 tick 없음 | 변화 없음 |
| converge의 tasks.md 쓰기는 append-only | BMAD B14, SPARC H4 | 같은 방향 |

## 3. 학습 내부에 새로 생기는 반대 방향 (13 §3에 추가)

- 계획 산출물을 뒤 단계에서 고침: BMAD(status·log) vs AOS `later_edits`, SKB `once`/rewrite 무효, SPARC H4. 13 §3의 "끝난 산출물 고치기"가 문서 수준(OSF)에서 규칙 수준(BMAD keep)으로 올라온다.
- intent gap 처리: BMAD "질문 적고 HALT"(semantic) vs AOS `requirements.answers`, OSF `note.summary`(T-SR1 보상), SKB CW:38-40 "가장 타당한 해석으로 계속".
- 테스트 작성: BMAD D42/F4 vs AOS·OSF·SKB `test_file_write` 금지 (port 조건).
- 전체 suite: BMAD F12가 SKB 03-test 편에 서서 AOS `whole_suite`와의 기존 반대가 2:1이 된다.
- 재독: BMAD D24·SPARC E7이 "디스크에서 다시 읽음" 진영을 두껍게 한다. no_reread 편은 여전히 학습에 없음.

## 4. 정리

- 확정: ifeval L1C 5 → 11 (`once` ×5, `order.stages`), SDD L1C 3 → 5 (`spec_written_by_specify`, `plan_docs_written_by_plan`). 모두 한 가지 습관(계획 산출물의 status·log를 뒤 단계에서 고침)에서 나온다.
- 조건부: HALT 유지 → ifeval T-SR2 ×2, SDD `clarifications_resolved`; 저장소 테스트 파일 → ifeval ×5, SDD ×2; 저장소 안 출력 경로 → ifeval ×1, SDD ×1. 세 결정 모두 11 §5의 port 결정표에 있고, 반대로 결정하면 T-SR2는 오히려 L1이 된다.
- 기존 L1C 5+3개는 라벨이 바뀌지 않지만, no_reread·no_return은 반대 규칙이 늘고 SDD `appended`·`no_na_section`은 같은 방향 규칙이 처음 생긴다.
- SPARC 단독으로는 새 L1C가 없다. 규칙들이 append-only·앞으로만 진행·저장소 밖 상태 디렉터리 등 학습 셋과 같은 방향이고, 반대 방향이던 J1(MCP 없으면 사용자에게 설치 요청)·E9(verifier 없으면 멈춤)는 drop이다. 대신 1.5의 L2 → L1 이동에 기여한다.
- 숫자는 BMAD/SPARC 규칙이 port 후 채점 항목으로 남는다는 가정이다(rules.yaml의 추정 운명). 2단계 gap 감사 뒤 fate가 바뀌면 1.2·2.2의 조건부 항목부터 다시 본다. constraints.yaml·sdd_layers.yaml은 바꾸지 않았다.

## 5. SPARC 산출물을 JSON+CLI 대신 md 문서로 재표현하면 (11 §5 세 번째 결정)

### 5.1 SPARC 자신이 어떻게 달라지나

| | JSON + CLI (현재 rules.yaml 가정) | md 문서 (다른 학습 workflow처럼) |
|---|---|---|
| CLI가 거부하던 42개 규칙(gate, 단계 순서, 식별자 형식, 집합·키별 대응) | 모델이 어길 수 없어 채점 천장 | 모델이 어길 수 있는 보통 항목이 됨: T-OR1 다섯 단계 순서, T-TR1 집합 관계 3, T-TR1b 키별 대응(REQ마다 인수테스트 집합 일치, REQ×TEST마다 증거), T-FM2/3/6 형식, NEW-S8-intra-set(인용 ⊆ 선언) |
| 프로토콜 규칙: revision 전달(F1), idempotency key(F2), Ed25519 attestation(E4-E7), digest 참조(C9, D7), 명령 옵션 형식(F4) | 측정 가능하지만 학습 셋 어디에도 없는 L2-먼 후보 11개 | 사라짐. md에는 revision도 서명도 없다. 11 §2의 새 템플릿 후보 6개 중 NEW-S8-intra-set/keyed 둘만 남음 |
| status 재독 규칙(A3, A9, E7 "메모리의 값을 쓰지 않는다") | 1.3의 no_reread 반대 진영을 두껍게 함 | 사라짐(읽을 CLI 상태가 없다). no_reread 라벨엔 영향 없음 |
| 산출물 형식 | JSON 객체. md 산출물 다섯을 요구하는 ifeval·SDD의 T-FM2(각 77·103개)와 형식이 다름 | md 섹션·표·라벨. 학습 셋과 같은 형식이라 전이 위험 없음 |

남는 SPARC는 "다섯 단계 md 산출물 + Refinement에서만 코드 수정 + 구현 뒤 테스트 실행 + 기록의 사실성 + 단계 간 추적성 + append-only"다. 사실상 SDD와 같은 과의 workflow가 되어 대부분 L1 보강이다.

### 5.2 평가 층에 미치는 영향

| 평가 항목 | CLI일 때 | md일 때 |
|---|---|---|
| ifeval 계획 step과 같은 요구 id 인용(T-TR1b `plan_execution_tags`, L2F) | SPARC 규칙이 천장이라 사실상 L2F 유지 | **L2F → L1** (SPARC D2/D7/D9가 실제 채점 항목) |
| SDD 산출물 내부 일관성 6개(NEW-FM-internal: 스토리 라벨, outcome 행 수 등, L2F) | L2F | **L2F → L1 또는 L2M**: SPARC B4/D4(인용 ⊆ 선언), D5(1:1 keyed) 가 "한 산출물 안의 두 부분 대조"의 첫 학습 항목. 09가 찾던 L2-먼 템플릿이 학습으로 들어감 |
| ifeval T-RF3 ×3(바뀐 파일 = diff) | L2M → L1 (SPARC H1) | 같음 |
| ifeval·SDD 형식 항목(T-FM2/3/6, 각 90·120여 개) | 라벨은 L1이지만 JSON 습관의 전이 위험 | 위험 제거 |

### 5.3 md 재표현이 새로 만들 수 있는 L1C — port 문장에 달림

CLI가 하던 두 가지를 문장으로 옮길 때 생긴다. 둘 다 BMAD 1.1(a)와 같은 "끝난 산출물을 다시 쓴다" 계열이다.

| CLI 동작 | md로 옮기는 두 가지 방법 | 결과 |
|---|---|---|
| gate blocker → 산출물을 고쳐 새 버전으로 재제출(A8) | (가) "산출물을 쓰기 전에 체크리스트를 스스로 확인하고, 통과한 내용만 한 번 쓴다" | 비충돌. ifeval `once`와 같은 방향 |
| | (나) "산출물을 쓰고, 체크리스트를 확인하고, 미달이면 고쳐서 다시 쓴다" (BMAD D28, SDD specify 검증 루프와 같은 꼴) | ifeval `once` ×5에 두 번째 반대 출처(BMAD 다음). SKB `once` ×7과도 반대. SDD는 단계 안 재작성을 허용하므로 SDD엔 영향 없음 |
| 이전 단계 산출물의 오류 → `correct` 레코드(H4: 원본은 고치지 않음) | (가) 별도 `corrections.md`에 적는다 | 비충돌. 오히려 H4가 T-WD2 `no_rewrite`·SDD `spec_written_by_specify`와 같은 방향의 규칙으로 남음 |
| | (나) 해당 산출물 끝에 `## Corrections`를 덧붙인다 | ifeval `once` ×5·`order.stages`, SDD `spec_written_by_specify`·`plan_docs_written_by_plan`에 BMAD와 같은 반대 출처 추가. SDD `appended`와는 같은 방향 |

(가)를 고르면 md 재표현은 새 L1C를 하나도 만들지 않는다. (나)를 고르면 라벨은 이미 BMAD로 L1C가 된 항목들이라 수가 늘지는 않지만, "끝난 산출물을 고치는" 학습 습관이 BMAD 하나에서 둘로 늘어 충돌 압력이 커진다.

### 5.4 정리

- md 재표현은 IF 연구에 유리하다: 천장 42개가 채점 항목이 되고, T-TR1b와 산출물 내부 일관성이 처음으로 학습에 들어가며(ifeval 1개·SDD 6개가 L2F에서 올라옴), JSON 형식의 전이 위험이 없어진다.
- 잃는 것은 프로토콜 템플릿(revision, idempotency, attestation, digest)이다. 이것들은 학습 셋 어디에도 없어 L2-먼 후보였지만, 평가 두 벌에도 없으므로 층 측정에는 쓰이지 않던 것이다.
- 새 L1C는 port 문장 둘로 막을 수 있다: 체크는 쓰기 전에 하고 산출물은 한 번 쓴다; 정정은 별도 파일에 적는다. 이 둘을 지키면 SPARC-md의 모든 행동 규칙이 학습 셋·평가와 같은 방향이다.

## 6. 보충: 1.2(d) "테스트 파일 추가" L1C가 SWE-Gym 학습에서 실제로 성립하는가 (2026-11-09)

데이터: SkyRL-v0-293-data `train.parquet` 293개(학습), `validation.parquet` 23개. 스크립트: scratchpad `testpatch_stats.py`. 채점기: `scripts/swegym_eval.py:71-73` — gold test patch가 건드리는 파일을 `git checkout <base> <files>`로 되돌린 뒤 `git apply`로 test patch를 적용하고 그 테스트를 돌린다.

| 질문 | 학습 293 | 검증 23 |
|---|---|---|
| gold test patch가 **기존 테스트 파일을 수정** | 287 (98%; 수정만 283, 새 파일도 4) | 21 (91%) |
| gold test patch가 **새 테스트 파일을 추가** | 10 (3%; 새 파일 11개, 예: moto `tests/test_kms/test_kms_encrypt.py`, hydra yaml 3) | 3 (13%) |
| 새 테스트 함수를 하나도 안 넣고 기존 테스트만 고침 (parametrize 행·단언 추가) | 113 (39%) | — |
| 기존 테스트의 단언·기대값 줄을 바꿈 | 30 (10%) | — |
| FAIL_TO_PASS 중 parametrize id (`[...]`) | 184/732 (25%) | — |
| 이슈 본문에 edge case 어휘 (None·empty·NaN·null·overflow·duplicate·negative·zero·boundary·edge case) | 132 (45%; None 99가 대부분이라 과대) | 8 (35%) |
| FAIL_TO_PASS 개수 | 중앙값 1, 1개인 instance 193 (66%), 5개 이상 16 | 중앙값 1 |

해석:
1. **edge case는 있다.** 이슈의 절반 가까이가 경계값 어휘를 담고, F2P의 1/4이 parametrize 행이라 BMAD의 I/O & Edge-Case Matrix(D38, 선택 섹션 D39)가 채워질 과제가 상당수다. 그때 D42("matrix가 있으면 그 edge case를 단위 테스트하는 task")와 F4("모든 행이 테스트로 덮임")가 발동한다. 반대로 F2P 1개짜리 단순 버그(66%)에서는 matrix가 비어 D42가 발동하지 않는 경우도 많다 → L1C는 과제의 대략 절반에서만 학습된다.
2. **upstream 관행은 "기존 테스트 파일에 추가"다.** gold가 그렇게 한 과제가 98%, 새 파일은 3%. BMAD를 그대로 두면 에이전트도 기존 테스트 파일에 case를 덧붙이게 된다. 이것이 ifeval `test_file_write`("기존 테스트 파일을 고치지 않는다")·`test_files_modified: none`·`test_files_in_change: none`·`no_test_target` ×2의 정확한 반대다. 1.2(d)의 조건부 L1C는 **matrix가 채워지는 과제에서 확정**.
3. **채점 충돌은 작다.** gold patch가 건드린 테스트 파일에 에이전트가 쓴 것은 `git checkout`으로 되돌아가고, 다른 테스트 파일에 쓴 것은 F2P/P2P 목록에 없어 실행되지 않는다. 깨지는 경우는 에이전트가 **gold가 새로 만드는 경로와 같은 이름**의 파일을 먼저 만들었을 때뿐이다(`git apply` "already exists" → 보상 0). 그 경로는 293 중 10개 instance에만 있고 이름까지 같아야 하므로 1% 미만. 16 문서 A의 "측정 필요"는 이것으로 답이 됨: 저장소 테스트를 되살려도 채점 비용은 무시할 수준.
4. 단, 포트 결정이 D42를 `checks/`로 돌리면(현재 rules.yaml fate: semantic, G9) 이 L1C는 사라지고 D42는 L1(T-PR1 같은 방향)이 된다. L1C로 쓰려면 BMAD 포트가 테스트를 저장소 테스트 파일에 두어야 하고, 그러면 AOS/OSF/SKB의 `checks/` 규칙과 학습 내부 충돌이 생긴다(16 §5).
