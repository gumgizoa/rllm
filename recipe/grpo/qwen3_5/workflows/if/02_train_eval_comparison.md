# 02. 학습·평가 대조표 (설계 문서 9.1절 3단계 결과)

> 기준 문서: `/mnt/nas1/mmi/ks.lim/docs/sdlc_if_template_design.md`, 이전 단계: `01_template_layer.md`
> 작성: 2026-10-22 (effort: extra high)
> 입력
> - AI-DLC: `aidlc_v4/docs/core-workflow.md`, `docs/rule-details/01~05`, `instruction.md`, `system-prompt.j2` (전부 읽음)
> - 학습 workflow: rubric과 검증 코드(`checks.py`, `workflow_rubric/checks/actions.py`, `openspec_kinds.py`), 문서는 L2 후보 지시를 검색해 노출 여부를 확인
> - 학습 workflow의 `system-prompt.j2` (AI-DLC와 비교)

## 0. 이 문서가 한 일과 약어

**한 일:** AI-DLC 문서를 직접 읽고 검증 가능한 규칙(constraints)을 뽑았다. 각 규칙이 `01_template_layer.md`의 어느 템플릿에 해당하는지 정하고, 학습 workflow 세 개에 같은 것이 있는지 판정했다. 판정에는 학습 workflow의 rubric, 검증 코드, 문서, system prompt를 함께 봤다. 결과는 AI-DLC 규칙마다 "학습 때 본 것인가"다.

**템플릿 ID (T-xx):** T = Template, 뒤 두 글자는 영역이다.

| 접두어 | 뜻 | 기술 분류 |
|---|---|---|
| RD (ReaD) | 문서·파일 읽기 | S1 문서 따르기 |
| OR (ORder) | 단계 순서 | S2 단계 순서 |
| AW (Action Window) | 특정 구간에서 해야 하거나 하면 안 되는 행동 | S3 행동 허용 구간 |
| PR (PRohibition) | 금지 대상 | S4 금지 대상 |
| WD (Write Discipline) | 산출물 쓰기 규율 | S5 산출물 쓰기 규율 |
| RF (Record Fidelity) | 기록 = 실제 | S6 기록의 사실성 |
| PG (ProGress) | 진행 기록 | S7 진행 기록 |
| TR (TRace) | 산출물 사이 추적 | S8 산출물 간 추적 |
| SR (Self-Resolution) | 질문 대신 스스로 결정 | S9 질문 대신 스스로 결정 |
| FM (ForMat) | 산출물 형식 | S10 산출물 형식 |

**규칙 번호:**
- **G1~G18:** AI-DLC 공통 규칙(core-workflow.md)
- **Stg1a ~ Stg5i:** AI-DLC Stage 1~5 규칙(Stg = Stage). `S`만 붙은 S1~S10은 기술(Skill) 분류다.

**workflow:** AOS = agentos_v2, OSF = openspec_ff, SKB = speckit_bug, AID = AI-DLC(`aidlc_v4_gen` rubric 참고).

**문서 위치:** CW = core-workflow.md, RE / RA / CP / CG / BT = AI-DLC 단계 문서 01~05, SP = system prompt. 예: "RE 36" = 01-reverse-engineering.md 36행.

## 1. 판정 방법

AI-DLC 규칙마다 다음을 판정했다.

1. **대응 템플릿:** `01_template_layer.md`의 T-* 중 어느 것인지 정한다.
2. **학습과의 관계:** 아래 다섯 가지 중 하나로 판정한다.
   - **같음:** 같은 판정 로직이다(인스턴스 분리).
   - **가까운 변형:** 인자, 극성, 숫자만 다르다.
   - **중간:** 학습 템플릿 구조를 포함하거나 반복한 형태, 또는 학습 문서에 지시가 노출된 경우다.
   - **먼 변형:** 6절 판별 기준 1·2를 통과하고 노출도 없다.
   - **충돌:** 학습 규칙이나 문서 지시와 반대 방향이다.
3. **근거:** 학습 쪽 검증 함수와 인자, 또는 문서 위치를 적는다. 먼 변형과 중간은 반례를 함께 적는다. 반례는 학습 템플릿은 지키지만 이 규칙은 어기는 trajectory다.
4. **노출:** rubric에 없더라도 학습 문서나 system prompt에 같은 지시가 있으면 기록한다.
5. **측정:** 평가 scorer로 측정할 수 있는지 적는다.
   - `v4`: 현재 `aidlc_v4` scorer가 fact로 기록한다. 점수에 반영되지 않을 수 있다.
   - `gen`: `aidlc_v4_gen` rubric에 항목이 있다.
   - `없음`

### 1.1 이번 단계에서 추가로 정한 판정 규칙

설계 문서 7.2절과 01의 `window` 규칙에 더해, 대조하면서 다음을 정했다.

| 규칙 | 판정 | 근거 사례 |
|---|---|---|
| 집합 관계의 방향을 뒤집는 것 (A⊆B ↔ B⊆A) | 인스턴스 | 피연산자만 바뀜 |
| 집합 관계를 `equal`로 바꾸는 것 | 중간 | 학습에 있는 두 방향 subset의 결합 |
| 기록한 주장의 극성 ("X를 했다" ↔ "X는 없다") | 인스턴스 | T-RF2와 T-RF1 |
| 금지·요구 대상을 고정 패턴 대신 **에이전트 자신의 산출물 필드**로 지정 (selector) | 중간 | T-AW4 (재현 스크립트 경로를 Stage 3 산출물에서 가져옴) |
| system prompt의 지시 | 모든 workflow에 공통 노출로 본다 | system prompt는 workflow 블록 외에는 네 workflow가 같다(아래 1.2) |
| kind 이름이 달라도 코드가 같은 판정을 함 | 같음 | `doc_read(no_read_ahead)`와 `order(invalidate=read_ahead)` |

### 1.2 system prompt 공통 노출

네 workflow의 `system-prompt.j2`는 `<PROBLEM_SOLVING_WORKFLOW>` 블록만 다르고 나머지는 OpenHands 기본 지침으로 같다. 따라서 다음 지침은 학습 workflow와 원본 모델 모두에 노출돼 있다.
- **같은 방향:** "NEVER create multiple versions of the same file with different suffixes", "임시 파일은 확인 후 삭제", "edit the file directly"
  - AI-DLC의 중복 파일 금지(T-PR2)와 같은 방향이다.
- **반대 방향:** `<ENVIRONMENT_SETUP>`의 "의존성이 없으면 설치하라"
  - AI-DLC·OpenSpec의 설치 금지(T-PR3)와 충돌한다.

## 2. AI-DLC 규칙 대조표

### 2.1 공통 규칙 (core-workflow.md, system prompt)

| # | AI-DLC 규칙 (위치) | 템플릿 | 학습과의 관계 | 근거 / 반례 | 노출 | 측정 |
|---|---|---|---|---|---|---|
| G1 | 핵심 문서를 가장 먼저 읽기 (CW, SP 1) | T-RD1 | 같음 | 세 학습 workflow 모두 `doc_read_first` | 모든 학습 문서 | v4, gen |
| G2 | 단계 시작 시 단계 문서 읽기 (CW "MANDATORY: Rule Details Loading") | T-RD2 | 같음 | 세 학습 workflow `doc_read` | 모든 학습 문서 | v4, gen |
| G3 | 한 번에 하나씩, 이전 단계 완료 전에 다음 단계 문서 미리 읽지 않기 (CW, SP 3) | T-RD3 | 같음 | AID `doc_read(no_read_ahead)` = 학습 `order(invalidate=read_ahead)`. 코드상 같은 조건: 첫 열람이 이전 단계 산출물 쓰기보다 앞서면 실패 | AOS·OSF·SKB rubric | v4(order_v6 prefix), gen |
| G4 | 5단계 고정 순서 (CW "Core Principle") | T-OR1 | 같음 | 세 학습 workflow `order(chain)` | 모든 학습 문서 | v4(order_v6), gen |
| G5 | 이전 단계로 돌아가지 않음 (CW "Stage Flow", BT 58) | T-OR1 + T-WD2 | **같음(구현) / 충돌(문서)** | 판정 가능한 부분인 이전 단계 문서 재열람·산출물 재작성은 `order(invalidate=multi_read, rewrite)`로 OSF·SKB에 있음. 그러나 OSF 문서는 "apply may send you back to ff"이고, SKB는 fix/test 라운드를 반복함 | OSF CW:26 (반대) | gen(order) |
| G6 | 단계마다 산출물을 지정 경로에 쓰기 (CW "Stage Artifacts") | T-FM1 | 같음 | 학습 `artifact_exists` | 모든 학습 문서 | v4, gen |
| G7 | 한 번에 전체 내용으로 쓰기, 추가 쓰기·자리표시자 금지 (CW "Artifact Rules") | T-WD1, T-FM4 | 같음 | SKB `write_discipline(once)` 7개, 학습 `no_template_residue` | SKB CW "One write per report" | v4(rewrites), gen |
| G8 | 이전 단계 산출물 재작성 금지 (CW) | T-WD2 | **같음(SKB) / 충돌(OSF)** | SKB `order(invalidate=rewrite)`(산출물이 2회 이상 쓰이면 무효), SKB CW "Never rewrite an earlier report". 반대로 OSF apply:103은 "design issue → update the affected artifact (design, specs or tasks) yourself" (04 7절에서 정정) | SKB 문서(같은 방향), OSF apply(반대) | v4(rewrites), gen |
| G9 | 골격(제목·필드 접두어) 그대로 유지 (CW) | T-FM2 | 같음 | 학습 `section_present`, `label_present` 등 | SKB CW "Keep each report's structure exactly" | v4(missing_fields), gen |
| G10 | frontmatter는 `stage`, `name` 두 키만 (CW) | T-FM5 | **먼 변형** | 학습 rubric에 frontmatter 항목이 없고, 학습 문서에도 frontmatter 지시가 없음(`---`는 구분선뿐). 반례: 학습 형식 규칙을 모두 지키고 frontmatter 없이 쓴 산출물 | 없음 | v4(frontmatter_valid, 단계 점수 gate), gen |
| G11 | 아직 보이는 산출물은 다시 읽지 않기, 복구할 때만 읽기 (CW "Artifact Rules") | 신규 T-RD6 | **충돌** | 학습 T-RD4는 이전 산출물을 단계 구간에 **읽어야** 함(AOS `read`, SKB `read`, OSF `read_files`). OSF ff 문서는 "always re-read them from disk, even if you saw them earlier" | OSF ff:56, ff:107, SKB fix:20-21 "in full" (반대). AOS create-tasks:13 "대화 맥락에 없으면 읽어라"는 같은 방향의 부분 노출(04 7절) | 없음 (unimplemented) |
| G12 | 식별자(R1, 단계 번호, 경로)를 그대로 인용, 재번호 금지 (CW) | T-TR1 일부 | 중간 | 산출물 간 ID 대응은 OSF `openspec.capabilities`에 있음(2.3절 Stg3b) | SKB "verbatim" 지시(링크·예시 인용) | gen(cross_ref) |
| G13 | 사람에게 묻지 않음: 질문 파일 금지, 승인 요청 금지 (CW "Execution Context") | T-SR1 | 같음 (문서) | 세 학습 workflow 모두 "질문하지 말고 가정을 기록"(AOS는 질문을 쓰고 스스로 답함) | 모든 학습 문서, 학습 SP | 없음 |
| G14 | 환경 설정·의존성 설치 금지 (CW, RE 30, BT 20) | T-PR3 | 같음 / **충돌(SP)** | OSF `prohibited_action(install)`. system prompt `<ENVIRONMENT_SETUP>`은 설치를 지시 | OSF 문서(같은 방향), SP(반대) | gen |
| G15 | 무한 반복 금지, 진전이 없으면 멈추고 미해결로 기록 (CW "Termination", BT 56) | T-OR2 | 중간 | OSF archive 재시도 1회 상한, SKB 라운드 3회 상한은 횟수 상한이고, AI-DLC는 "진전 없음"이라는 조건부 종료라 판정이 모호함 | OSF·SKB 문서 | v4(max_identical_command_repeats 기록) |
| G16 | 소스만 수정, 테스트 파일 수정 금지 (CW, CP 78, CG 30) | T-PR1 | 같음 | 세 학습 workflow `prohibited_action(test_file_write)` | 모든 학습 문서 | v4(diff_test_files), gen |
| G17 | 쓰기 전 파일 존재 확인, 제자리 수정, 중복 변형 파일 금지 (CW "File Modification") | T-PR2 | 같음 | 학습 `created_files(pattern)`(같은 템플릿, 패턴만 다름). system prompt의 중복 파일 금지 | SP (공통) | v4(diff_backup_files), gen |
| G18 | 계약 보존: 이전에 통과하던 테스트가 계속 통과 (CW) | T-AW3 + 결과 | 같음 | 결과 지표에 가까움 (회귀 여부) | SKB 문서 | 결과(resolve)로 측정 |

### 2.2 Stage 1 Reverse Engineering

| # | 규칙 | 템플릿 | 관계 | 근거 / 반례 | 노출 | 측정 |
|---|---|---|---|---|---|---|
| Stg1a | 영향 범위 파일을 저장소 루트 기준 전체 경로로 기록 (RE 19) | T-RF4 | 같음 | AOS `cross_ref(기록 경로 ⊆ base_paths)` | AOS 문서 | gen |
| Stg1b | 이슈와 무관한 패키지를 나열하거나 저장소를 넓게 훑지 않기 (RE 21) | (신규, 판정 모호) | 충돌(약함) | AOS는 저장소 검색을 **요구**(`holds: exists grep/find`) | AOS 문서 (반대) | 없음 |
| Stg1c | 테스트 명령은 관련 테스트만 대상으로, 전체 스위트 금지 (RE 27) | T-PR5 + 기록 형식 | 같음 | AOS "Do NOT run the entire test suite at this stage". AID는 **기록한 명령**의 형식(`field_type: test_selection`)도 봄 | AOS 문서 | gen |
| Stg1d | 관련 기존 테스트를 찾아 읽기 (RE 34-35) | T-RF1 계열 | 가까운 변형 | "기록한 대상에 실제로 그 행동을 했는가"(`aidlc.executed: read_of`)는 SKB `checks_table(commands_run)`과 같은 구조이고, 행동만 다름(읽기 vs 실행) | SKB 문서 | gen |
| Stg1e | **소스 수정 전에** 관련 테스트를 실행 (RE 36, CW Stage 1-3) | T-AW2 (T0) | 같음 | SKB `exec_evidence(window: start → 첫 수정)`, SKB `check_scripts(before_change)`, `checks_added(baseline_run)` | SKB fix:33 | v4(baseline_before_first_write), gen |
| Stg1f | 통과·실패 테스트를 각각 이름으로 기록, 실제 실행과 일치 (RE 37, 69-70) | T-RF1 | 같음 | SKB `checks_added`, `field_type(command_run)`. AID는 `test_id`/`failed_test_id` 타입 | SKB 문서 | gen |
| Stg1g | 산출물 골격과 한 번에 쓰기 (RE 43-71) | T-FM2, T-WD1, T-FM5 | 같음 (T-FM5 제외) | 2.1절 G7·G9·G10 | | v4, gen |

### 2.3 Stage 2 Requirements Analysis / Stage 3 Planning

| # | 규칙 | 템플릿 | 관계 | 근거 / 반례 | 노출 | 측정 |
|---|---|---|---|---|---|---|
| Stg2a | 요구사항을 R1, R2…로 세 범주에 걸쳐 하나의 연번, 고유 (RA 20-22) | T-FM3 (sequence+unique) | 같음 | AOS `item_format(sequence)`(번호 연속) | AOS 문서 | gen |
| Stg2b | 세 범주 제목 모두 존재, 누락은 미평가로 간주 (RA 24, 65) | T-FM2 | 같음 | | | v4, gen |
| Stg2c | 질문 대신 가정을 기록 (RA 61-62, 70) | T-SR1 / T-FM2 | 같음 | AOS `requirements(answers)` | AOS·OSF 문서 | gen(field) |
| Stg3a | 계획의 각 Step 블록마다 Target·Change·Contract·Verification 기록 (CP 15-21, 45-55) | T-FM6 | **중간** | AOS `blocks`(블록 수와 블록당 불릿 수)와 같은 "반복 블록 내부 구조" 범주. AID는 블록마다 필드 존재를 봄(T-FM2의 블록별 반복). 반례: AOS 블록 규칙(불릿 1~N개)은 지키지만 Step 블록에 Contract 필드가 없는 계획 | 없음 | v4(Stage 3 점수에 반영: Step마다 네 필드와 태그), gen(per_block) |
| Stg3b | 모든 Step에 요구사항 태그, 모든 요구사항이 하나 이상의 Step에 대응, Coverage 절이 R 전부를 나열 (CP 21, 61-67, 84-86) | T-TR1 | **중간** | OSF `openspec.capabilities(listed_have_specs, specs_listed)`: proposal에 나열한 ID ↔ delta spec 파일을 양방향 대응. AID는 요구사항 문서의 R ↔ 계획 Step 태그 ↔ Coverage 절을 텍스트 ID로 대응(selector 차이 = 인스턴스). 다만 학습에는 **세 산출물에 걸친 연쇄**와 **Step→R 쌍 대응**이 없음(아래 Stg4b) | OSF verify:105-112 "Requirement Implementation Mapping"(delta spec 요구사항 ↔ 구현 근거, 04 7절에서 추가) | v4(Step 태그 존재는 점수 반영, Coverage 절은 추출만), gen(cross_ref 7) |
| Stg3c | 재현 스크립트 계획과 경로 기록, Exercises ⊇ 예외 상황 요구사항 (CP 25-29, 57-59) | T-FM2 + T-TR1 | 중간 | Stg3b와 같음 (superset 방향 = 인스턴스) | | gen |
| Stg3d | 계획의 Target에 테스트 파일 없음 (CP 78, 93) | T-PR1을 계획 내용에 적용 | 가까운 변형 | 행동 금지(T-PR1)를 **계획 필드**로 옮긴 것. SKB assess 문서 "Do not plan to add or edit test files"가 같은 지시 | SKB assess:45 | gen(cross_ref disjoint) |
| Stg3e | 존재하는 파일은 "modify in place", 새 파일만 "create" (CP 81) | T-RF4 | 같음 | 기록 경로와 base 존재 여부 관계. AOS `cross_ref ⊆ base_paths`. disjoint 방향 = 인스턴스 | SP (제자리 수정) | gen |

### 2.4 Stage 4 Generation

| # | 규칙 | 템플릿 | 관계 | 근거 / 반례 | 노출 | 측정 |
|---|---|---|---|---|---|---|
| Stg4a | 계획에 기록한 경로를 그대로 사용, 계획대로 실행 (CG 16, 21) | T-TR2 | **중간** | SKB fix 문서 "Stay within the files listed by the assessment"가 같은 방향의 지시. SKB rubric은 이를 "쓴 파일 ⊆ fix 보고서 목록"(T-RF3)으로만 구현해서, 이전 산출물(계획)에 대한 이행은 학습 rubric에 없음. 반례: fix 보고서에는 쓴 파일을 다 적었지만 계획에 없던 파일을 수정 | SKB fix:35 | gen(cross_ref Plan Target ⊆ 쓴 파일) |
| Stg4b | 실행 기록의 Step→R 대응이 계획의 Step→R과 일치 (CG 72-73) | T-TR1b (신규 분리) | **먼 변형** | 학습 `cross_ref`는 모두 집합 관계이고, **키별 값 대응**(keyed_ids)은 없음. 반례: Step 집합은 같지만 Step 2의 요구사항 태그를 바꿔 적은 실행 기록 | 없음 | gen(should 1) |
| Stg4c | 재현 스크립트를 쓰되 **이 단계에서 실행하지 않기**, "Executed: no" (CG 28, 69, 86) | T-AW4 (+ T-RF2) | **중간 + 충돌** | 구간 안 실행 금지는 OSF `prohibited_action(command: python -c, explore 구간)`과 같은 구조. 새 요소는 실행 대상이 **자신의 산출물 필드**(Stage 3의 Path)라는 것(1.1 규칙). SKB는 반대로 "Run each check now. It must fail"(수정 전 즉시 실행)을 학습시킴 | SKB fix:31-34 (반대) | v4(repro_executed_steps), gen |
| Stg4d | 계획이 틀리면 이 단계 안에서 조정하고 편차를 기록, Planning으로 돌아가지 않음 (CG 32-37) | T-FM2 + G5 | 같음(형식) / 충돌(OSF) | 편차 기록 필드는 SKB fix "Deviations from Assessment"와 같음. 복귀 금지는 G5 | SKB CW(같은 방향), OSF CW(반대) | gen(field) |
| Stg4e | Changed Files 목록 = 실제 수정·생성 파일 (CG 62-65, 89) | T-RF3 | 같음 / 중간(equal) | SKB `cross_ref(쓴 파일 ⊆ 보고서 목록)`. AID는 양방향(subset + 역방향)이라 equal에 해당 | SKB 문서 | gen |
| Stg4f | Checks: "Duplicate files created: none", "Test files modified: none"이 사실과 일치 (CG 78-80) | T-RF2 | **가까운 변형** | 주장 대 사실의 일치는 T-RF1(SKB `checks_table(consistent)`, AOS `report(failed_listed)`)이고, "없음" 주장은 극성만 다름(1.1 규칙) | | gen(refuted_by) |

### 2.5 Stage 5 Build and Test

| # | 규칙 | 템플릿 | 관계 | 근거 / 반례 | 노출 | 측정 |
|---|---|---|---|---|---|---|
| Stg5a | baseline과 테스트 명령은 다시 만들지 않음. 01 산출물은 보이지 않을 때만 읽고, baseline을 재구성하려고 테스트를 다시 돌리지 않음 (BT 11) | T-RD6 + (판정 모호) | 충돌 | G11과 같음. "재구성용 재실행"은 판정 기준을 정의하기 어려움 | OSF ff (반대) | 없음 |
| Stg5b | Stage 1에 기록한 빌드 명령을 그대로 실행 (BT 17) | T-TR2 / T-AW6 | 중간 | 이전 산출물에 기록한 명령 ↔ 실제 실행. SKB fix 양식 "after the change: <same...>" 노출 | SKB fix:81 | gen(cross_ref equal command) |
| Stg5c | Stage 3·4에 기록한 경로의 재현 스크립트를 실행 (BT 26) | T-AW3 + selector | 중간 | 사후 실행(T-AW3)은 같고, 대상이 자신의 산출물 필드라는 점이 새로움(1.1) | | v4(repro_executed_steps), gen |
| Stg5d | **baseline과 같은 테스트 범위로** 재실행하고 baseline과 비교 (BT 35-37) | T-AW6 | **중간** | 학습 rubric에는 실행 간 범위 일치 항목이 없음. 그러나 SKB fix 양식에 "`<command>` before the change …; after the change: <same, with any new failure named>"와 baseline 대비 판정(test:43-45)이 있음. 반례: 사후 재실행은 했지만(T-AW3 충족) baseline과 다른 테스트 선택으로 돌림 | SKB fix:81, test:43 | v4(regression_rerun_after_last_write만), gen(aidlc.executed same_selection_as) |
| Stg5e | 전체 테스트 스위트 실행 금지 (BT 39) | T-PR5 | 같음 / **충돌** | AOS 구현 단계의 전체 스위트 금지와 같음. 그러나 AOS 검증 단계는 전체 스위트를 **요구**(`verify(whole_suite)`), SKB test는 "Run any broader regression suite" | AOS create-tasks(같은 방향), AOS implement PHASE 3·SKB test:31 (반대) | gen |
| Stg5f | baseline에서도 실패한 테스트는 고치지 않고 이유를 기록 (BT 49) | E2 계열 (조건부) | 같음(SKB 문서) | SKB 문서에 같은 분류가 있음. 발동 조건(baseline 실패)이 드묾(설계 문서 8절 6단계) | SKB test:45 | gen(field) |
| Stg5g | 테스트가 아니라 소스를 고침 (BT 53) | T-PR1 | 같음 | | 모든 학습 문서 | v4, gen |
| Stg5h | 미해결 항목은 Outstanding Failures에만 기록, 남은 실패가 있으면 "none" 금지 (BT 98) | T-RF2 | 가까운 변형 | AOS `report(failed_listed, incomplete_listed)`: 실패·미완료가 있으면 보고서에 나열해야 함 | AOS 문서 | gen(field) |
| Stg5i | Final Change: 변경 파일 = Stage 4 목록, 의도치 않은 파일 없음, 테스트 파일 없음 (BT 92-104) | T-RF3, T-PR2, T-RF2 | 같음 / 중간(equal) | Stg4e·G17·Stg4f와 같음 | | v4(diff_*), gen |

## 3. 01 대응표 정정

이번 대조로 `01_template_layer.md`의 "AI-DLC 고유" 판정 중 다음이 바뀐다.

| 템플릿 | 01 판정 | 정정 | 이유 |
|---|---|---|---|
| T-RD3 미리 읽기 금지 | 고유 → (01에서 이미 정정) | 같음 | `order(invalidate=read_ahead)`와 같은 코드 조건 |
| T-WD2 재작성 금지 | 고유 → (01에서 이미 정정) | 같음 | SKB `order(invalidate=rewrite)` |
| T-AW4 지연 실행 | 고유 | **중간 + 충돌** | 구간 실행 금지는 OSF explore에 있음. 대상이 자신의 산출물 필드인 점만 새로움. SKB 습관과 반대 |
| T-AW6 같은 범위 재실행 | 고유 | **중간** | SKB fix 양식에 같은 명령 재실행 노출 |
| T-RF2 "없음" 주장 반박 | 고유(형식상) | **가까운 변형** | T-RF1의 극성 변형 |
| T-TR1 산출물 간 ID 대응 | 고유 | **중간** (Stg3b) / **먼 변형** (Stg4b keyed, T-TR1b로 분리) | OSF `openspec.capabilities`가 산출물 간 ID 대응. 키별 대응만 학습에 없음 |
| T-TR2 계획 이행 | 고유 | **중간** | SKB fix 문서 "Stay within the files listed by the assessment" 노출 |
| T-FM5 frontmatter 고정 | 고유 | **먼 변형** (유지) | rubric과 문서 모두 없음 |
| T-FM6 블록별 필드 | 고유(형식상) | **중간** | AOS `blocks`와 같은 범주, T-FM2의 블록별 반복 |
| (신규) T-RD6 보이는 산출물 재독 금지 | — | **충돌** | 학습 T-RD4(읽어야 함)와 OSF 문서(항상 다시 읽어라)와 반대. 검증 함수 없음 |

학습 workflow 사이 대조에서도 다음이 바뀐다(workflow 고유 템플릿 확인, 9.0.1).

| 템플릿 | 01 판정 | 정정 | 이유 |
|---|---|---|---|
| T-AW7 검증 단계 코드 고정 (AOS) | AOS 고유 | `code_frozen`은 T-AW1(구간 내 저장소 수정 금지)의 인스턴스. `whole_suite`만 AOS 고유이고 AI-DLC와 충돌 | 같은 `repo_write` 금지 구조 |
| T-PR6 특정 명령 금지 (OSF) | OSF 고유 | 구간 실행 금지 템플릿으로, T-AW4의 학습 쪽 근거 | explore의 `python -c` 금지 |
| T-FM7 섹션 추가 금지 (AOS) | AOS 고유 | 학습에서는 AOS 고유가 맞음. AI-DLC 문서("headings exactly")에도 같은 지시가 있고 v4가 `unknown_sections`를 기록 | AI-DLC 쪽은 gen rubric 미구현 |
| T-RD5, T-AW5, T-PG2 | 고유 | 유지 | 다른 workflow에 같은 판정 로직 없음 |

## 4. 결과 요약

### 4.1 AI-DLC 규칙의 분포

**먼 변형 (순수 unseen): 2개.** 둘 다 조건 없이 발동한다.

| AI-DLC 규칙 | 어느 단계 | 템플릿 |
|---|---|---|
| 산출물 frontmatter는 `stage`, `name` 두 키만 | 모든 단계 (G10) | T-FM5 |
| Stage 4 실행 기록의 "Step n [R…]" 대응이 Stage 3 계획의 대응과 일치 (should 1개) | Stage 4 (Stg4b) | T-TR1b |

**중간: 학습 구조를 확장하거나 학습 문서에 노출된 것.**

| AI-DLC 규칙 | 어느 단계 | 템플릿 | 학습 쪽 근거 |
|---|---|---|---|
| 계획의 Step 블록마다 Target·Change·Contract·Verification 기록 | Stage 3 (Stg3a) | T-FM6 | AOS 블록 구조 검사 |
| 모든 요구사항이 계획 Step에 대응하고 Coverage 절에 나열됨 | Stage 3 (Stg3b, Stg3c), 공통 (G12) | T-TR1 | OSF proposal ↔ spec 대응 |
| 계획에 기록한 경로와 명령을 그대로 사용 | Stage 4 (Stg4a), Stage 5 (Stg5b) | T-TR2 | SKB "assessment가 나열한 파일 안에서 수정" |
| 기록한 경로의 재현 스크립트를 실행 | Stage 5 (Stg5c) | T-AW3 확장 | 학습의 사후 재실행 |
| baseline과 같은 테스트 범위로 재실행 | Stage 5 (Stg5d) | T-AW6 | SKB 보고서 양식 "after the change: <same…>" |
| 변경 파일 목록 = 실제 수정 파일 (양방향) | Stage 4 (Stg4e), Stage 5 (Stg5i) | T-RF3 | SKB "쓴 파일 ⊆ 보고서 목록" (한 방향) |
| 진전이 없으면 멈추고 미해결로 기록 | 공통 (G15) | T-OR2 | OSF 재시도 1회, SKB 라운드 3회 상한 |

**충돌: 학습 규칙이나 문서와 반대 방향. 습관이 아니라 현재 지시를 따르는지를 본다.**

| AI-DLC 규칙 | 어느 단계 | 반대 방향인 학습 쪽 |
|---|---|---|
| 재현 스크립트를 작성만 하고 이 단계에서는 실행하지 않음 | Stage 4 (Stg4c) | SKB "수정 전에 바로 실행해서 실패 확인" |
| 아직 보이는 산출물은 다시 읽지 않음 | 공통 (G11), Stage 5 (Stg5a) | 학습 "이전 산출물을 단계 시작 시 읽어라", OSF "항상 디스크에서 다시 읽어라" |
| 전체 테스트 스위트 실행 금지 | Stage 5 (Stg5e) | AOS 검증 단계 "전체 스위트 실행", SKB "broader regression suite 실행" |
| 이전 단계로 돌아가지 않음 | 공통 (G5) | OSF "apply에서 ff로 돌아갈 수 있음", SKB fix/test 라운드 반복 |
| 이전 단계 산출물을 다시 쓰지 않고 편차는 현재 산출물에 기록 | 공통 (G8) | OSF "구현 중 설계 문제가 드러나면 design·specs·tasks를 직접 수정" (SKB는 같은 방향) |
| 의존성 설치·환경 설정 금지 | 공통 (G14) | system prompt "의존성이 없으면 설치하라" |
| 이슈와 무관한 부분까지 저장소를 넓게 훑지 않음 | Stage 1 (Stg1b) | AOS "저장소를 검색해서 재사용할 코드를 찾아라" |

**같음 / 가까운 변형:** 나머지 전부(L1, seen). 문서 읽기, 단계 순서, 산출물 한 번에 쓰기, 테스트 파일 수정 금지, 수정 전 baseline, 기록 = 실제, 골격 등이다.

### 4.2 해석

- **순수 unseen(먼 변형)은 2개로 매우 얇습니다.** 01에서 "AI-DLC 고유"로 본 7개 중 5개가, 판정 로직과 문서 노출을 확인하면 중간이나 가까운 변형으로 바뀌었습니다. 설계 문서 4.3절의 "대부분 인스턴스 분리" 결론이 더 강해집니다.
- **대신 "충돌" 규칙이 7개 있고(5단계 문서 검토로 G8 추가), 이것이 이 실험에서 가장 판별력 있는 평가 문항이 될 수 있습니다.** 학습이 "지시를 따르는 능력"이 아니라 "학습 workflow의 습관"을 심었다면 이 규칙들의 준수율은 오히려 떨어질 것입니다. 원본 모델 대비 학습 모델의 충돌 규칙 준수율 변화는 일반화와 과적합을 가르는 직접적인 신호입니다.
- **"중간" 규칙은 해석에 주의하되 L2에 포함할 수 있습니다.** 대부분 학습에 있는 구조를 **산출물 사이 연결**(계획 → 실행, 기록 → 실행)로 확장한 것입니다. AI-DLC의 성격(단계 산출물이 다음 단계의 근거가 됨)이 드러나는 부분입니다.

### 4.3 측정 가능성

현재 `aidlc_v4` scorer가 fact로 기록하는 것과 아닌 것을 나누면 이렇습니다.

| 구분 | 규칙 |
|---|---|
| v4가 점수에 반영하는 것 | frontmatter 유효성(단계 점수 gate), 산출물 골격, 계획 Step 블록별 필드와 태그(T-FM6), 문서 읽기·산출물 쓰기 순서(order_v6) |
| v4가 기록만 하는 것 (점수 미반영) | 재현 스크립트 실행 시점(T-AW4·Stg5c), baseline 선행, 사후 재실행, 산출물 재작성, diff의 테스트·백업 파일, 반복 명령, Requirement Coverage 절 |
| v4에 없고 gen rubric에만 있는 것 | 같은 범위 재실행(T-AW6), 요구사항 ID 대응 검사(T-TR1, T-TR1b), 계획 이행(T-TR2), 목록 = 실제(equal), "없음" 주장 반박(T-RF2) |
| 둘 다 없는 것 (새 검증 함수 필요) | 산출물 재독 금지(T-RD6), 넓게 훑지 않기(Stg1b), 진전 없을 때 종료(G15) |

L2와 충돌 규칙을 항목 단위로 보고하려면 평가 scorer를 `aidlc_v4_gen` 형식으로 맞추고, T-RD6 검증 함수를 새로 만들어야 합니다(9.1절 6단계, Future work 10.2).

## 5. 4단계(L2 선정)로 넘길 결정 사항

> **결정 (2026-10-23):** 아래 1~4 모두 권장안으로 확정했다.
> 1. L2에 "중간"을 포함하고, "중간" 표시와 함께 따로 보고한다.
> 2. 충돌 규칙은 별도 층(L1-충돌)으로 둔다.
> 3. 충돌의 원인인 학습 쪽 workflow 고유 행동은 학습에 남긴다.
> 4. T-RD6(보이는 산출물 재독 금지) 검증 함수 구현을 앞당긴다. 교차 검증은 첫 학습 결과를 보고 정한다.

1. **L2의 범위:** 순수 unseen(먼 변형) 2개만 둘지, "중간"까지 포함할지 정한다. 포함한다면 "중간" 표시와 함께 보고한다.
2. **충돌 규칙의 위치:** 별도 층(L1-충돌)으로 둘지, L2에 포함할지 정한다. 이 문서의 권장은 **별도 층**이다. 해석 방향이 다르기 때문이다(학습 습관을 이겨야 함).
3. **충돌의 원인을 학습 쪽에서 남겨 둘지:** 예를 들어 SKB의 "수정 전 체크 즉시 실행", OSF의 "항상 다시 읽기", AOS의 "검증 단계 전체 스위트"를 그대로 둘지 정한다. 그대로 두어야 충돌 문항이 의미가 있다. 이들은 각 workflow 고유의 lifecycle 행동이므로 유지하는 것이 9.0.1 원칙과도 맞다.
4. **L2 보강 방법 선택:** 먼 변형이 2개뿐이므로 Future work 10.2의 방법을 앞당길지 정한다. 후보는 학습 workflow 교차 검증, 공통 템플릿 일부 제외, T-RD6 같은 unimplemented 규칙의 검증 함수 구현이다.
