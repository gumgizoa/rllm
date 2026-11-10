# 06. 항목·템플릿·workflow 문서 대조 (Step A 결과)

> 작성: 2026-10-23 (effort: extra high)
> 대상: 네 workflow의 rubric 항목 1,009개 전체(AOS 205, OSF 248, SKB 329, AID 227), 구현 항목과 unimplemented 항목 모두
> 산출물 (`review/`)
> - `CRITERIA.md`: 검토 기준
> - `<wf>/judgments.jsonl`, `<wf>/report.md`: workflow별 판정과 보고서
> - `mapping.tsv`: 통합 대응표. 1행 = 1항목, 열은 항목 → 템플릿 → 기술 → (AID) 층 → 제안 층
> - `matrix.md`: 템플릿 × workflow 분포
> 재현: `scripts/packet.py`(검토 묶음 생성), `scripts/consolidate.py`(통합표와 재검토 반영)

## 0. 요약

1. **항목마다 템플릿·기술을 다시 정했다.**
   - 자동 배정(01의 `layer.py`)에서 바뀐 구현 항목은 151개다(AOS 28, OSF 27, SKB 78, AID 18).
   - 대부분은 S10 안의 정리다. 줄 하나만 보는 `item_format`은 T-FM3이 아니라 T-FM2로 옮겼다.
   - 기술(S)이 바뀐 것은 39개다.
2. **원문 대조 결과**
   - rubric이 인용한 원문 2,232개는 모두 인용한 줄과 일치한다.
   - 항목이 원문보다 좁게 보는 경우(narrower)는 115개, 넓게 보는 경우(broader)는 13개다.
   - **원문과 다른 것을 보거나 항상 통과하는 항목은 3개**다(3절).
3. **AI-DLC 층 판정 중 다섯 가지가 학습 쪽 노출과 맞지 않는다(4절).** 제안대로 바꾸면 평가 must 항목 수가 다음과 같이 바뀐다.
   - L1: 150 → 161
   - L1-충돌: 9 → 4
   - L2-먼: 13 → 6
   - L2-중간: 11 → 17
   - **순수 unseen(L2-먼)은 T-FM5(frontmatter)와 T-TR1b(Step→R 키별 대응) 두 템플릿뿐이다.**
4. **rubric을 고쳐야 할 곳이 있다(5절).** 평가 쪽 결함은 기준점 측정 전에 고쳐야 한다. 특히 반복 라벨의 첫 줄만 읽는 결함은 L2-중간 핵심 항목을 포함해 10개 항목에 영향을 준다.
5. **T-RD6:** 같은 stage 안에서 다시 읽어도 위반이다. 같은 step 예외는 원문 근거가 없다. AI-DLC 문서 자체에 BT:47과 CW:42의 충돌이 있다(6절).

## 1. 방법

1. **검토 묶음 만들기:** 항목마다 kind와 인자, 자동 템플릿, 원문 인용, (AID) 층을 담았다. 인용 2,232개는 스크립트로 인용한 줄과 대조했다.
2. **1차 검토:** workflow마다 독립 검토자 1명이 모든 항목을 원문, 검증 코드와 대조했다. 판정 항목은 다음과 같다.
   - 템플릿
   - 원문 규칙
   - 충실도
   - 원문의 요구 수준
   - 같은 workflow 문서 안의 충돌
   - unimplemented 분류
   - 학습 workflow의 경우 AI-DLC 감시 목록 W1~W18의 노출
3. **2차 검토:** 확신도가 낮거나 층에 영향이 있는 16개 묶음을 다른 검토자가 처음부터 다시 판정했다. 다섯 가지가 갈렸고, 리드가 다섯 가지 모두 2차 판정을 채택했다(2절).
4. **리드 직접 확인:** 층 판정을 바꾸는 주장 6개는 코드를 읽거나 실행해서 확인했다.
   - AOS `ticked_after_work`
   - OSF `tasks.verified`
   - OSF residue 항목이 항상 통과하는지
   - OSF delta의 블록별 검사
   - AID `no_test_target` 정규식
   - `M.field_value`가 첫 줄만 읽는지

## 2. 템플릿 배정: 확정한 규칙과 정정

### 2.1 일괄 규칙

| 규칙 | 해당 | 근거 |
|---|---|---|
| 줄 하나의 존재나 형식만 보는 `item_format`(`min: 1`, 반복·개수 조건 없음) → **T-FM2** | AOS 14, OSF 5, SKB 74, AID 1 | 판정 대상이 반복 항목이 아니라 골격의 한 줄이다 |
| `none_allowed`의 조건이 실행 사실인 `field_filled` → **T-RF2** | AID 7 | "없음" 주장이 실행으로 반박되는 구조다(2차 검토에서 채택) |
| `created_files.tests`(테스트 파일 추가 금지) → **T-PR1** | AOS, OSF, SKB 각 1 | T-PR1의 "추가" 쪽이다 |
| 금지 규칙을 기록 내용(계획 필드, 기록한 명령)에 적용한 것 → **같은 금지 템플릿의 가까운 변형** | AID `test_selection`, `a5.field_type.command`(T-PR5), `no_test_target`, `a3.cross_ref.3`(T-PR1), `plan.5`(T-PR2) | 02의 Stg3d 처리와 같다 |
| "상태가 X이면 보고서에 Y를 기록"이 형식 kind 안에 들어 있는 것 → **T-RF1** | OSF verify 조건부 4 | 형식 kind 안에 숨은 기록 사실성 규칙이다 |
| 블록마다 필수 부분이 있는지를 비율로 보는 것 → **T-FM6** | OSF `delta.requirement_text/scenario/when_then`, `tasks.verification`(모두 must), AOS `group_parts`(should), `test_first`(must) | 2차 검토에서 채택. 라벨 대신 하위 제목·키워드를 쓰는 것은 기록 형식 차이라 인스턴스 수준이다 |

### 2.2 신규 템플릿 후보 (NEW)

| 후보 | 위치 | 상태 |
|---|---|---|
| NEW:PG1-per-unit (작업 단위별 체크 순서) | AOS `groups_in_order`(must) | 구현됨. W18(작업 직후 기록)과 같은 축이지만 일부만 다룬다. 작업 직후라는 시점은 고정하지 않는다 |
| NEW:per-event-immediacy (작업마다 즉시 체크, U2) | OSF unimplemented 2 (AP:153, SCHEMA:275) | 구현 후보 |
| NEW:CQ (diff로 판정하는 코드 위생) | AOS unimplemented 19 | U13. 대부분 공통 system prompt와 겹친다 |
| NEW:post-write-existence-check, NEW:task-tracker-use | OSF unimplemented 각 1 | U4, U7 |
| NEW:exists-check-before-write | AID unimplemented 1 (CW:145) | 가치 낮음 |

### 2.3 `layer.py`(템플릿)와 `build.py`(층 사유) 불일치 정리 (AID)

| 항목 | layer.py | build.py | 확정 |
|---|---|---|---|
| `read_tests` | T-RD4 | T-RF1 | **T-RD4** |
| `repro_not_left` | T-RF3 | T-PR2 | **T-PR2** |
| `a4.field_literal.executed` | T-RF2 | T-AW4 | **T-RF2**. 실패는 T-AW4 사실(Stage 4 실행)에서만 생기므로 L1-충돌 배정은 유지한다 |
| `a3.cross_ref.3` | T-RF3 | T-PR1 | **T-PR1** |
| `plan_execution_tags` | T-TR1 | T-TR1b | **T-TR1b** |
| `repro_written` | T-AW3 | T-RF1 | **T-TR2** (둘 다 틀림) |
| `build_run` | T-RF1 | (kind 이름) | **T-TR2** |
| `sequence` | T-AW3 | (Stg5c 설명) | **T-OR1** (실행의 순서 사슬. 대상은 자기 산출물에서 고른다) |

두 스크립트가 따로 판정해서 생긴 문제다. 앞으로는 `mapping.tsv`를 하나의 기준으로 쓰고, `build.py`가 이 표를 따르게 한다(5절).

## 3. workflow별 템플릿 구성

통합 분포는 `review/matrix.md`에 있다. 기술 단위로 요약하면 다음과 같다(구현 항목 수 / 서로 다른 템플릿 수).

| 기술 | AOS | OSF | SKB | AID |
|---|---|---|---|---|
| S1 문서 따르기 | 16 / 4 | 11 / 4 | 14 / 3 | 8 / 4 |
| S2 단계 순서 | 1 / 1 | 2 / 2 | 4 / 2 | 2 / 1 |
| S3 행동 허용 구간 | 12 / 5 | 24 / 3 | 21 / 3 | 6 / 5 |
| S4 금지 대상 | 4 / 3 | 9 / 5 | 4 / 3 | 10 / 4 |
| S5 산출물 쓰기 규율 | 8 / 2 | 5 / 2 | 11 / 3 | 9 / 2 |
| S6 기록의 사실성 | 8 / 3 | 5 / 1 | 21 / 1 | 29 / 4 |
| S7 진행 기록 | 3 / 1 (+NEW 1) | 4 / 2 | 0 | 0 |
| S8 산출물 간 추적 | 1 / 1 | 2 / 1 | 0 | 12 / 3 |
| S9 질문 대신 스스로 결정 | 1 / 1 | 1 / 1 | 0 | 0 |
| S10 산출물 형식 | 100 / 6 | 78 / 6 | 224 / 5 | 113 / 6 |

- **AI-DLC에만 구현된 템플릿:** T-RD3(학습에서는 `order`의 invalidate 요소), T-RD6, T-AW4, T-AW6, T-RF3, T-TR1b, T-TR2, T-FM5.
  - 이 중 학습 쪽에서 요소나 문서 노출로 나타나는 것은 4절에서 다룬다.
- **학습에만 구현된 템플릿:** T-RD2, T-RD5, T-OR2, T-AW5, T-AW7, T-PR4, T-PR6, T-WD3, T-WD4, T-PG1, T-PG2, T-SR1, T-FM7, T-FM8, NEW:PG1-per-unit.
  - AID의 `doc_read` 5개는 T-RD3으로 분류했고, T-RD2도 함께 판정한다.
- **unimplemented 223개:** duplicate 114, candidate 46, domain_specific 32, vague 22, display 11.
  - candidate는 OSF 19, AOS 14, SKB 7, AID 5다(`mapping.tsv`의 `unimpl_class` 열).

## 4. AI-DLC 층 재판정 (제안, 결정 필요)

학습 workflow 세 개에서 AI-DLC 감시 목록이 어떻게 노출되는지 확인했다(각 `report.md` 6절). 그 결과로 다음을 제안한다.

| 템플릿 (AID 항목) | 현재 | 제안 | 근거 |
|---|---|---|---|
| **T-FM6** Step 블록별 필드 (`a3.field_filled.{target,change,contract,verification}`, 4) | L2-먼 | **L1** | 학습 보상에 이미 있다. OSF `delta.requirement_text/scenario/when_then`, `tasks.verification`(모두 must, 블록마다 필수 부분), AOS `group_parts`(should), `test_first`(must). 5단계에서 AOS `blocks` 2개를 뺀 것만으로는 L2-먼이 되지 않는다 |
| **T-RF3** 기록 목록 = 실제 (`a5.cross_ref` equal, `a4.cross_ref.4`, `a4.cross_ref.changed_files`, 3) | L2-먼 | **L2-중간** | SKB 보상 항목은 뺐지만 fix 보고서의 Changes 표(FX:62-66, FX:3 "record the changes")가 기록 쪽을 보여 준다. 약한 문서 노출이다. "every/exactly"라는 표현은 없어서 L2-먼으로 둘 여지도 있다 |
| **T-TR2** `repro_written`, `build_run` (2) | L1 (라벨 오류) | **L2-중간** | 템플릿을 정정한 결과(2.3절)이고, 같은 T-TR2 항목들과 같은 층이다 |
| **T-WD2 / G8** 이전 산출물 재작성 금지 (`global.a{1..4}.write_discipline.no_rewrite`, 4) | L1-충돌 | **L1** | 세 학습 workflow 모두 **같은 방향으로 보상**한다. AOS `shape_files_left_alone`·`spec_left_alone`·`later_edits`(must), SKB `write_discipline.once`와 order rewrite, OSF `tasks_after_verify`(T-WD2, must). 반대 방향은 OSF apply 문서(AP:103, AP:151)에만 있다. 학습된 습관과 지시가 충돌하는 상황이 아니다 |
| **T-PR3** 설치 금지 (1) | L1-충돌 | **L1** | OSF가 같은 방향으로 보상한다(must). 반대 방향인 system prompt `<ENVIRONMENT_SETUP>`은 AI-DLC 평가에도 똑같이 들어간다. 따라서 이것은 학습과 평가 사이의 충돌이 아니라 평가 workflow 안의 충돌이다 |

**바꾸지 않지만 근거를 보강하거나 다시 확인할 것**
- **L1-충돌로 남는 것:** T-RD6, T-AW4(`prohibited_action.execute`, `field_literal.executed`), T-PR5(`full_suite`). 세 학습 workflow가 반대 방향을 보상하고 있다.
  - T-RD6: AOS read must 3개, SKB "in full" must, OSF "re-read from disk" must 5개
  - T-AW4: SKB `check_scripts.before_change` must, AOS·OSF 문서는 작성 직후 실행
  - T-PR5: AOS `whole_suite` must
- **T-TR2(L2-중간) 유지:** AOS `ticked_after_work`(must)와 OSF `tasks.verified`(should)가 "자기 계획에 적은 경로나 명령을 실제로 실행"이라는 **요소**를 보상한다. 다만 작업(tick)마다 반복되고 구간이 tick에 고정된다는 점이 템플릿 수준의 차이라서(2차 검토), 같은 템플릿은 아니다. 그래서 L2-중간에 둔다.
- **Stg5c(재현 스크립트를 기록한 경로에서 실행) 유지:** 위와 같은 이유로 L2-중간에 둔다. "자기 산출물 필드로 대상 고르기"(02 1.1)는 이제 학습에도 요소로 있으므로, 근거는 "구조 확장형"으로 고친다.
- **T-TR1(L2-중간, 6개)은 다시 판단해야 한다.**
  - 항목 하나하나는 두 산출물 사이의 ID 집합 관계이고, OSF `capabilities.listed_have_specs`(must)·`specs_listed`(should)와 같은 판정 로직이다.
  - 02에서 "중간"으로 둔 근거는 세 산출물에 걸친 연쇄였는데, 연쇄는 항목 하나의 성질이 아니라 항목들 전체의 성질이다.
  - 항목 단위로 엄격하게 보면 L1이다. L2로 쓰려면 Future work 10.2의 leave-one-category-out(OSF `capabilities` 제외)이 필요하다.
- **AOS `blocks` 제외(5단계 P1):** T-FM6이 L1이 되면 뺀 이유가 없어진다. 학습 다양성을 위해 되돌리기를 권한다.
  - SKB `cross_ref` 제외는 유지한다. 빼 두면 AID의 subset 방향 항목이 L1이 아니라 L2-중간이 된다.

**기술별 L2 현황 (제안 반영)**

| 기술 | L2-먼 | L2-중간 | L1-충돌 |
|---|---|---|---|
| S1 | | | T-RD6 |
| S2 | | (G15 항목 없음), `sequence` | |
| S3 | | T-AW6, Stg5c | T-AW4 |
| S4 | | | T-PR5 |
| S5 | | | (G8 → L1) |
| S6 | | T-RF3 | |
| S8 | T-TR1b | T-TR1(재판단), T-TR2 | |
| S10 | T-FM5 | | |

L2-먼은 6개 항목, 템플릿 2개뿐이다. 그래서 L2 평가의 대부분은 L2-중간에 기대게 된다. 순수 unseen을 늘리려면 Future work 10.2(leave-one-workflow-out, leave-one-category-out)가 사실상 필요하다.

## 5. rubric 수정 목록 (B단계 입력)

### 5.1 평가(AI-DLC): 기준점 채점 전에 필요

`aidlc_v4_gen`은 동료가 작업 중이므로 직접 고치지 않는다. 대신 `aidlc_v4_ifeval/reward/build.py`에서 복사본을 변환해 고치고, 같은 내용을 동료에게 전달한다.

1. **반복 라벨의 첫 줄만 읽힘 (10개)**
   - 해당 항목: `a1.field_type.path`, `a1.cross_ref`, `a3.field_type.target`, `a3.cross_ref.3`, `code_generation_generation.a3.cross_ref`(T-TR2, must+WHEN), `a4.cross_ref{,.2,.3,.5}`, `a4.cross_ref.4`(T-RF3, must)
   - 원인: `refs.select({field|field_list})`와 `field_type`이 `M.field_value`를 쓰는데, 이 함수는 첫 번째 라벨 줄만 돌려준다(리드가 실행해서 재현).
   - 수정: 모든 줄을 읽는 `ids` 선택자로 바꾼다.
2. **`a3.item_format.no_test_target`가 항상 통과한다.**
   - 원인: `[\s*`]*`가 0글자로 역추적하면서 부정 lookahead가 무력해진다(리드가 재현).
   - 수정: 소유 수량자(`*+`, Python 3.11 이상)나 경로 토큰을 명시적으로 잡는 패턴으로 바꾼다. `test_*.py` 같은 경로를 놓치는 문제도 함께 고친다.
3. **평가 요구 수준 must 추가 (5개):** `exercises_edge_cases`, `a4.field_filled.modified`, `a4.cross_ref`, `a4.cross_ref.2`, `a5.field_type.command`
4. **`build.py` 정리**
   - 층 규칙이 `mapping.tsv`의 템플릿을 따르게 한다(2.3절).
   - 4절에서 결정한 층을 반영한다.
   - REQUIREMENT 근거로 인용한 줄 3곳을 고친다.
     - `a3.cross_ref`: CW:42, CP:21
     - `a5.cross_ref.build_command`: BT:17, BT:74
     - `a5.cross_ref`: BT:93, BT:102-104
5. **T-RD6를 엄격판과 민감도판 두 가지로 바꾼다(6절).**

### 5.2 학습 rubric

| workflow | 수정 | 성격 |
|---|---|---|
| OSF | `ff.spec.no_template_residue.template`, `ff.tasks.no_template_residue`(must)가 항상 통과한다. 패턴이 HTML 주석인데, 검사 전에 주석을 지운다(리드가 재현) | 결함 |
| OSF | `new_capabilities` kebab-case와 TPL_TASKS 제목 3개가 should인데 원문은 must다 | 요구 수준 |
| SKB | `fix.*.section_present.local_verification`(×3)이 should인데 CW:50-51에 따라 must다 | 요구 수준 |
| SKB | `assess.field_filled.reproduction`이 `[NEEDS CLARIFICATION]` 표시만 있으면 실패한다. AS:30은 이를 허용한다 | broader |
| SKB | `checks_table.consistent`가 lint 실패나 baseline부터 있던 실패에도 verified를 실패시킨다. `unrun`은 Regression suite 행을 빼먹는다 | broader / narrower |
| AOS | `group_parts`가 should인데 CT:216 "for each task group"에 따라 must다. 그 밖에 요구 수준 불일치 7개 | 요구 수준 |
| AOS | `blocks` 2개 복원 (4절 결정에 따름) | 5단계 되돌림 |
| 공통 | 학습 rubric에도 반복 라벨을 `field`로 읽는 항목이 있는지 확인한다(5.1의 1번 결함) | 확인 필요 |
| 공통 | 문서에 있지만 `conflicts`에 기록되지 않은 충돌을 기록한다. AOS 테스트 먼저(CT:214)와 표준(CT:382), SKB SP:171과 CW:38, OSF AP:169-170, AID BT:47과 CW:42 | 기록 |

### 5.3 unimplemented 후보 갱신 (04 6절의 U 목록)

- **새로 확인한 후보**
  - SKB 라운드 상한 종료(T-OR2): FX:7, CW:28, TS:99
  - AID 이전 단계 복귀 금지(G5): CW:71
  - AID 질문 파일 금지: CW:132
  - OSF 그룹별 즉시 검증(T-AW3 반복형): SCHEMA:232
- **U2(작업 직후 체크)의 위치가 분명해졌다.** OSF에는 unimplemented 2개뿐이고, AOS `groups_in_order`는 그룹 단위로 일부만 다룬다. 구현하면 S7에 반복형 템플릿이 생긴다(AI-DLC에는 대응 규칙이 없어서 L2 판정에는 영향이 없다).

## 6. T-RD6 (`aidlc_ifeval.no_reread`) 판정

1. **같은 stage 안에서 다시 읽어도 위반이다.**
   - CW:42-43에는 stage 구분이 없다. 예외는 "잘렸거나 압축돼서 더 이상 보이지 않을 때"뿐이다.
   - 하네스에 condenser가 없으므로, 에이전트가 쓴 산출물은 실행 내내 맥락에 남아 있다.
2. **같은 step 예외(쓰기와 같은 호출 안의 읽기)는 원문 근거가 없다.** 엄격판에서는 이 예외를 없애고, 민감도판에서만 허용한다.
3. **AI-DLC 문서 안에 충돌이 있다.**
   - BT:47 "Re-read the requirement and correct the source"의 requirement는 A2의 Rn이다. 문서는 "requirement"를 R id에만 쓰고, 이슈는 언제나 "task description"이라고 부른다.
   - CG:17 "Load the … change, contract obligations …"와 BT:48 "check the interfaces the plan marked as preserved"도 약하게 같은 방향이다.
   - BT:11("only if that content is no longer visible")은 CW:43과 맞는다.
4. **제안:** 엄격판(CW:42 그대로)을 L1-충돌 점수로 쓰고, 민감도판도 함께 기록한다. 민감도판은 다음 세 가지 읽기를 면제한다.
   - 재현 실패 뒤 Stage 5에서 A2 읽기
   - Stage 4에서 A3 읽기
   - 같은 step에서 쓰기와 함께 한 읽기

## 7. 결정 (2026-10-23)

- T-TR1 → **L1** (항목 단위 판정 로직이 OSF `capabilities`와 같음)
- AOS `blocks` **복원** (AOS 고유 항목이었음) → T-FM6는 L1
- 평가 rubric 수정은 동료에게 따로 알리지 않는다. 이 작업 결과를 새 기준으로 삼는다(rubric과 constraint를 분리해서 다른 부서에 공유할 수 있게 하는 것이 목적)
- T-RF3 → **L2-중간**
- G8은 L1에 둔다. AOS·SKB 항목을 빼도 OSF `tasks_after_verify`(T-WD2, must)가 남는다. SKB는 T-WD1(`once`)과 분리할 수 없다
- **할 일 (나중에):** T-PR3. 네 workflow의 `system-prompt.j2`에서 `<ENVIRONMENT_SETUP>`의 설치 지시를 뺀다. 그다음 rubric lock(SP sha)을 다시 만들고, 원본 모델 기준점도 바뀐 prompt로 측정한다. 이렇게 하면 T-PR3은 L1이 된다
- AI-DLC 문서는 평가 workflow의 사본(`aidlc_v4_ifeval/docs`)에서 고친다.
  - A1 수정
  - system prompt에서는 A2~A4만 뺀다. 그 밖의 SP는 수정하지 않는다
  - B는 L2를 살리고 보상에 악영향이 없는 것만 고친다: B1~B4
  - B7은 기존 scorer가 그 표기에 의존해서 하지 않는다
  - T-RD6는 사본 문서를 명시된 대로(CW:42-43) 엄격하게 판정한다
- 새 기준 구조: `sdlc_if/templates.yaml`, workflow마다 `constraints.yaml`, `rubric.yaml`. 브랜치에 커밋하고 push는 나중에 한다
- 실행 결과는 `07_new_standard.md`에 있다

### 처음 제시한 결정 사항

1. 4절의 층 재판정 다섯 가지(T-FM6 → L1, T-RF3 → L2-중간, T-TR2 라벨, G8 → L1, T-PR3 → L1)
2. T-TR1을 L2-중간에 둘지 L1로 바꿀지
3. AOS `blocks` 복원
4. T-RD6를 엄격판과 민감도판으로 나눌지
5. 5.1의 평가 rubric 결함을 `aidlc_v4_ifeval` 빌드 단계에서 고치고 동료에게 알릴지
