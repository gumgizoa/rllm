# 12. speckit_sdd의 템플릿 분포 (speckit_bug와 비교)

> 작성: 2026-11-06
> 입력: `workflows/speckit_sdd/reward/rubric.yaml`(생성기 출력, 2026-10-15, 287 항목), 비교 대상 `workflows/speckit_bug/constraints.yaml`(implemented 299). 카탈로그: `sdlc_if/templates.yaml`
> 재현 스크립트: `scripts/sdd_templates/sdd_templates.py` → 항목별 배정 `scripts/sdd_templates/sdd_assignment.yaml`(id, kind, template, basis). 실행: `python3 sdd_templates.py sdd_assignment.yaml`. 층 배정(4절): `sdd_layers.py sdd_assignment.yaml sdd_layers.yaml`
> 01 문서가 쓴 `scripts/layer.py`·`inventory.py`는 저장소 어느 브랜치에도 없어서, 네 workflow의 `constraints.yaml`(항목 id → 템플릿)을 kind+인자 서명 사전으로 삼아 분류를 다시 만들었다.

## 0. 요약

- speckit_sdd(SDD) 채점 항목 242개가 템플릿 27개(카탈로그 26 + 11 문서의 NEW-FM-internal)로 묶인다. unimplemented 45개 중 35개는 생성기의 "no majority among 2 samples" 자리표시자이고 규칙은 10개뿐이다.
- SKB와 같은 Spec Kit 계열이지만 분포는 다르다. SDD는 **기록의 사실성(T-RF1)이 0개**다(SKB 21). 대신 SKB에 없는 템플릿이 11개 있다: T-RD5 6, T-AW5 6, T-PG1 5, T-FM6 7, NEW-FM-internal 6, T-TR1 2, T-PR3·T-PR6·T-WD2·T-RF3·T-RF4 각 1.
- 이 11개는 지금의 학습 constraints 기준으로 모두 다른 학습 workflow가 보상한다(01 문서가 "AI-DLC 고유"로 둔 T-TR1·T-FM6도 현재는 AOS·OSF에 cross_ref·per_block 항목이 있다). 학습 셋에 전혀 없는 것은 NEW-FM-internal 6개뿐이다.
- **평가 workflow로 쓰면 L1 232 · L1-충돌 3 · L2-중간 1 · L2-먼 6**(4절). aidlc_v4_ifeval(L1 168 · 5 · 13 · 6, 192개)보다 L1 쏠림이 더 크다. L2 두 층을 합쳐 7개, 그중 6개가 산출물 내부 일관성 한 템플릿이라 먼 일반화 측정에는 쓸모가 적다.
- 형식(S10) 비중은 162/242(67%)로 SKB 224/299(75%)보다 조금 낮다. 행동 쪽은 S1 24, S3 21, S5 11, S2 8, S7 5가 차지한다.

## 1. 기술별 템플릿 대응표

숫자는 그 템플릿으로 판정되는 채점 항목 수. SDD의 must/should는 rubric의 `requirement`. SKB 열은 현재 `constraints.yaml`의 implemented 기준이라 01 문서(10월 22일 rubric) 표의 SKB 열과 다르다(04 문서의 rubric 축소 뒤 수치).

| 기술 | 템플릿 | 내용 | SDD | must/should | SKB |
|---|---|---|---|---|---|
| S1 | T-RD1 | 개요 문서를 가장 먼저 읽기 | 1 | 1/0 | 1 |
| S1 | T-RD2 | 단계 시작 시 그 단계 문서 읽기 (SY, PL, TK, IM, CV, IM₂, CV₂) | 7 | 7/0 | 7 |
| S1 | T-RD4 | 이전 산출물을 지정 구간에 읽기 (`speckit.read`) | 10 | 8/2 | 6 |
| S1 | T-RD5 | 특정 파일 읽기 (constitution ×4, spec/plan 템플릿) | 6 | 6/0 | — |
| S2 | T-OR1 | 읽기·쓰기 순서 사슬 (`order` 4 + 라운드 보고서 뒤 tasks.md append 2) | 6 | 6/0 | 3 |
| S2 | T-OR2 | 결과 분기·라운드 상한 (최대 2라운드, converged 뒤 라운드 없음) | 2 | 2/0 | 1 |
| S3 | T-AW1 | implement 밖 저장소 수정 금지 (`repo_write` ×5, implement에 수정 존재 ×2) | 7 | 6/1 | 7 |
| S3 | T-AW2 | 첫 수정 전 검증 (baseline 테스트, checks `before_code`·`red_green`) | 3 | 3/0 | 4 |
| S3 | T-AW3 | 마지막 수정 뒤 검증 (`after_change` ×2, `pass_last` ×2, `tests_pass`) | 5 | 4/1 | 10 |
| S3 | T-AW5 | 지정 구간에 Spec Kit 스크립트 실행 (`setup-plan`, `setup-tasks`, `check-prerequisites` ×4; 인자 집합까지 봄) | 6 | 6/0 | — |
| S4 | T-PR1 | 테스트 파일 추가·수정 금지 | 2 | 2/0 | 2 |
| S4 | T-PR2 | 저장소에 작업 파일 금지 (scratch 패턴, ignore 파일) | 2 | 2/0 | 1 |
| S4 | T-PR3 | 설치 금지 | 1 | 1/0 | — |
| S4 | T-PR4 | URL 접근 금지 | 1 | 1/0 | 1 |
| S4 | T-PR6 | 특정 명령 금지 (`git branch`/`checkout -b`) | 1 | 1/0 | — |
| S5 | T-WD1 | 산출물을 한 번에 쓰기 | — | | 7 |
| S5 | T-WD2 | 이전 산출물 재작성 금지 (converge의 tasks.md `append_only`) | 1 | 1/0 | — |
| S5 | T-WD3 | 지정 위치에만 쓰기 (`paths_written`, shipped 트리 `untouched`, checks `written`) | 3 | 3/0 | 1 |
| S5 | T-WD4 | 끝난 파일 수정 금지 (단계 뒤 산출물 쓰기 없음 ×5, `later_edits`, plan 중 tasks.md 없음) | 7 | 7/0 | 3 |
| S6 | T-RF1 | 기록한 명령·결과가 실행과 일치 | — | | 21 |
| S6 | T-RF3 | 기록한 파일 목록 vs 실제 파일 (plan.md 트리의 contracts) | 1 | 1/0 | — |
| S6 | T-RF4 | 기록한 경로가 실제 존재 (`feature.json`의 feature_directory) | 1 | 1/0 | — |
| S7 | T-PG1 | 작업 뒤 체크 (`ticked` ×2, `ticked_after_work` ×2, 작성 시 미체크) | 5 | 5/0 | — |
| S8 | T-TR1 | 산출물 간 ID 커버리지 (spec의 User Story ↔ tasks의 phase, [USn]) | 2 | 0/2 | — |
| S10 | T-FM1 | 산출물 존재 | 11 | 11/0 | 7 |
| S10 | T-FM2 | 골격: 제목·라벨·필드·허용값 (단일 행 item_format 33 포함) | 103 | 88/15 | 191 |
| S10 | T-FM3 | 반복 항목 형식 (T### 연번, 개수, phase 순서, convergence 행) | 13 | 11/2 | 11 |
| S10 | T-FM4 | 자리표시자 잔존 금지 (`[NEEDS CLARIFICATION]` 포함) | 21 | 16/5 | 14 |
| S10 | T-FM6 | 블록마다 필드 (User Story 블록 ×3, story마다 task·test, finding 행) | 7 | 7/0 | — |
| S10 | T-FM8 | 도메인 형식 (링크 `[UNVERIFIED — not fetched]`) | 1 | 1/0 | 1 |
| S10 | NEW-FM-internal | 산출물 내부 일관성 ([USn]과 phase, [P] 파일 중복, phase 번호 = 최대+1, Outcome vs findings ×2) | 6 | 5/1 | — |
| | | **합계 (구현된 항목)** | **242** | | **299** |

기술별 합계 — SDD: S1 24 · S2 8 · S3 21 · S4 7 · S5 11 · S6 2 · S7 5 · S8 2 · S10 162. SKB: S1 14 · S2 4 · S3 21 · S4 4 · S5 11 · S6 21 · S10 224.

## 2. 관찰

1. **사실성 검사가 없다.** SKB 보상의 7%(21개)인 T-RF1(fix 보고서의 명령·결과 표가 실행과 일치)이 SDD에는 하나도 없다. SDD 문서가 실행 기록 표를 요구하지 않기 때문이다. S6에 남는 것은 plan.md 트리의 contracts 목록(T-RF3)과 feature.json 경로(T-RF4) 둘뿐이다. 반대로 converge 보고서의 findings는 코드 상태에 대한 주장인데 형식(T-FM6)과 내부 일관성(NEW-FM-internal)만 재고, 주장이 코드와 맞는지는 unimplemented다(`converge.convergence.unimplemented`).
2. **SKB에 없고 SDD에 있는 것 11개.** 현재 `constraints.yaml` 기준으로 T-RF3을 뺀 10개는 AOS나 OSF가 보상한다. T-TR1(AOS 1, OSF 2)과 T-FM6(AOS 4, OSF 4)도 그렇다. 01 문서가 둘을 "AI-DLC 고유"로 둔 것은 10월 22일 rubric 기준이고, 그 뒤 constraints 정리에서 학습 쪽 cross_ref·per_block 항목이 붙었다. 학습 셋 어디에도 없는 것은 NEW-FM-internal 6개뿐이다.
3. **단계 순서가 더 길다.** `order.round_1`은 읽기 5개·쓰기 5개 사슬 하나에 `invalidate: [read_ahead, multi_read]`가 붙는다(T-OR1이자 T-RD3). 두 라운드 구조는 T-OR2 2개(최대 2라운드, converged 뒤 라운드 없음)와 T-WD4 2개(converged면 tasks.md 불변)로 잡혀 있다. 11 문서 5절에서 "BMAD 리뷰 레이어를 빼면 speckit_sdd와 가까워진다"고 적었는데, 비교할 SDD 쪽 분포가 이 표다.
4. **unimplemented 45개 중 규칙은 10개.** 35개는 생성기가 두 샘플의 합의를 못 얻어 남긴 자리표시자(`no majority among 2 samples`)로, 규칙 문장이 없다. 규칙 10개는 모두 의미 판정이다: spec에 구현 세부 없음, 성공 기준이 측정 가능, 기술 중립, quickstart 내용, 절대 경로 사용, Polish 범위, finding의 id·근거, implement 끝 요약 메시지 등. BMAD의 NEW-J-content(11 문서)와 같은 J 축이다.
5. **S10 안의 구성이 다르다.** SKB는 T-FM2 191(64%)에 쏠려 있고, SDD는 T-FM2 103에 T-FM4 21·T-FM3 13·T-FM6 7·NEW-FM-internal 6이 붙는다. SDD의 산출물(spec, plan, tasks, research, data-model, quickstart, checklists, convergence ×2)이 9종으로 SKB(assessment, fix 보고서, test 보고서) 3종보다 많아서 존재(T-FM1 11)와 자리표시자(T-FM4 21) 항목이 늘었다.

## 3. 배정 근거와 한계

- 배정 근거는 `sdd_assignment.yaml`의 `basis` 열에 있다. `dict` 146개: 네 workflow의 서명 사전에서 유일하게 결정. `rule` 50개: SDD 고유 kind(`speckit_sdd.*`, `speckit.*`)를 `reward/checks.py`·`speckit_kinds.py`의 판정 로직으로 배정(스크립트의 주석이 각 규칙의 이유). `heur` 46개: `item_format`을 of_pattern·sequence·min>1·max=0이면 T-FM3, 아니면 단일 행 T-FM2로 나눈 휴리스틱. 라벨된 네 workflow에서도 같은 인자 모양이 T-FM2/T-FM3로 갈리므로(`min=1 pattern section`: 21 vs 17) 이 46개는 ±5 정도 흔들릴 수 있다.
- 판단이 갈릴 만한 배정: `speckit.holds` 7개를 "단계 뒤 산출물 쓰기 없음"으로 T-WD4에 묶었다(plan 중 tasks.md 없음은 극성·시점만 다른 인스턴스로 봄). `speckit_sdd.script` 6개는 T-AW5로 두었지만 인자 집합·키 검사는 11 문서의 NEW-S3-command-format에 해당한다. `checks.red_green`은 T-AW2에 두었다(수정 전 실패 확인이 변별점, 수정 뒤 통과는 `pass_last`가 따로 잼). `tasks.appended`는 보고서 뒤 append라는 순서로 T-OR1에 두었다.
- speckit_sdd는 생성기 출력 그대로다(`generator.yaml`, `rubric.lock`, `gen-cache`가 남아 있고 `constraints.yaml`이 없다). 학습 셋 세 개처럼 문서 원문과 대조한 fidelity 판정(faithful/narrower/broader)은 하지 않았다. 07 문서대로 연구 범위 밖이므로 학습·평가 어느 쪽에도 쓰이지 않는다는 전제 아래, 비교용 분포로만 쓴다.
- SKB 열은 현재 `constraints.yaml`이라 01 문서 표(T-FM2 117, T-FM3 82, T-RF1 24)와 수치가 다르다. 01 표를 현재 constraints로 다시 뽑는 일은 11 문서 6절의 한계와 같다.

## 4. speckit_sdd를 평가 workflow로 쓸 때의 층 분포

10 문서 3.2절 절차를 그대로 적용했다. 템플릿 기본 층(`templates.yaml` `eval.layer`) → 학습 세 workflow의 implemented 보상 여부 → 반대 방향 규칙 → 인스턴스 예외. 항목별 결과와 근거는 `scripts/sdd_templates/sdd_layers.yaml`(`layer`, `trained_in`, `layer_reason`).

| 층 | 항목 | must | should | 템플릿 (항목 수) |
|---|---|---|---|---|
| L1 | 232 | 204 | 28 | T-FM2 103, T-FM4 21, T-FM3 12, T-FM1 11, T-RD4 10, T-FM6 7, T-RD2 7, T-AW1 7, T-WD4 7, T-RD5 6, T-AW5 6, T-PG1 5, T-AW3 5, T-OR1 4, T-AW2 3, T-WD3 3, T-TR1 2, T-PR1 2, T-PR2 2, T-OR2 2, T-FM8·T-RF4·T-WD2·T-RD1·T-PR3·T-PR4·T-PR6 각 1 |
| L1-충돌 | 3 | 3 | 0 | converge의 tasks.md append 2 (T-OR1), spec의 N/A 절 금지 1 (T-FM3) |
| L2-중간 | 1 | 1 | 0 | T-RF3 (plan.md 트리의 contracts 목록) |
| L2-먼 | 6 | 5 | 1 | NEW-FM-internal 6 ([USn]↔phase, [P] 파일 중복, phase 번호, Outcome↔findings ×2) |
| 합계 | 242 | 213 | 29 | |

비교 — aidlc_v4_ifeval(`constraints.yaml` implemented 192): L1 168 · L1-충돌 5 · L2-중간 13 · L2-먼 6. 09의 aidlc_v4_eval 규칙 세트(채점 222): L1 159 · 5 · 18 · 15.

- **L1이 96%다.** ifeval 88%, 09 평가기 72%보다 높다. SDD 문서의 규칙이 Spec Kit 계열(SKB)과 OpenSpec·AgentOS가 이미 보상하는 템플릿으로 거의 다 덮이기 때문이다. "배운 것을 새 문서에서 지키나"는 잴 수 있지만 그게 전부다.
- **L2는 7개, 사실상 템플릿 둘.** 산출물 내부 일관성(NEW-FM-internal) 6개와 T-RF3 1개. ifeval의 L2-중간 13개(T-TR2 5, T-RF3 3, T-SR2 2, T-AW3, T-AW6, T-OR1)와 L2-먼 6개(T-FM5 5, T-TR1b 1) 같은 폭이 없다. 09 문서가 L2-먼의 대표로 꼽은 세 축(내부 일관성, 명령 형식, 키별 대응) 중 내부 일관성만 있고, 명령 형식은 T-AW5 스크립트 항목 6개 안에 인자 검사로 섞여 있어 따로 셀 수 없다.
- **충돌 층 3개는 모두 판단이 갈릴 수 있는 배정이다.** converge가 tasks.md에 phase를 append하는 것은 "끝난 산출물을 건드리지 않는" 학습 습관(SKB T-WD1 7, AOS·SKB T-WD4 6)과 반대라고 봤다. spec의 N/A 절 금지는 학습이 none 리터럴을 요구하는 것(SKB field_literal 9)과 반대 방향으로, 11 문서 3절이 BMAD D40에 적용한 기준이다. ifeval의 충돌 5개(T-AW4 지연 실행, T-RD6 재독 금지, T-OR3 복귀 금지, T-PR5, T-RF2)처럼 행동 자체가 반대인 것은 SDD에 없다. SDD의 2라운드 구조는 SKB의 fix 라운드와 같은 방향이라 T-OR3 류의 충돌이 생기지 않는다.
- **학습 rubric 버전에 상대적이다(10 §3.3).** step27은 T-RF3을 보상한 옛 SKB rubric으로 학습했으므로 그 checkpoint 기준으로는 L2-중간이 0이 되고 L2-먼 6개만 남는다.
- **기록 사실성은 어느 층에도 없다.** T-RF1이 0개라서, ifeval에서 가장 변별력이 컸던 축(08·09의 T-RF1 통과율 0.15→0.36, 0.80→0.83)을 SDD 평가로는 재지 못한다.

결론: speckit_sdd는 평가 workflow로 쓰면 L1 측정기다. L2 연구에 쓰려면 NEW-FM-internal 6개 외에 L2 항목을 새로 써야 하고(10 문서 6절의 holdout 방식으로 학습에서 템플릿을 빼는 쪽이 빠르다), 사실성 축은 문서에 실행 기록 표를 넣지 않는 한 생기지 않는다.

## 5. L1-충돌 방향 대조 (10 §3.2 3단계)

4절의 층은 2단계(학습 보상 여부)까지는 기계적으로, 3단계(반대 방향)는 예외 목록으로만 적용한 것이었다. 여기서는 SDD의 행동 규칙(S10 형식 제외, 80개)을 학습 세 workflow의 implemented 규칙과 문서(AOS CW·commands, OSF CW·stages, SKB CW·stages)에 대고 방향을 하나씩 대조했다. 판정 어휘는 02 문서 1절(같음 / 가까운 변형 / 충돌)을 쓴다. 결과는 `sdd_layers.py`의 `EXC`(충돌)와 `CHECKED`(대조했으나 충돌 아님)에 기록했다.

**원칙.** 템플릿이 학습에 있으면 L1 *후보*일 뿐이다. 같은 템플릿 안에서도 인스턴스의 극성·구간·지시가 학습과 반대면 L1-충돌이고(ifeval의 T-PR5: 같은 템플릿에 L1 2 + L1C 1), 학습 workflow 셋 중 하나라도 반대 방향을 보상·지시하면 충돌로 둔다(ifeval T-PR5는 AOS implement가 같은 방향인데도 AOS verify의 whole_suite 때문에 충돌). 즉 기준은 "하나라도 같으면 L1"이 아니라 "하나라도 반대면 L1C"다.

### 5.1 충돌로 판정한 것 (3)

| SDD 규칙 | SDD 지시 | 반대 방향의 학습 규칙 | 반대 방향의 학습 문서 | 판정 |
|---|---|---|---|---|
| `converge.tasks.appended`, `converge_2.tasks.appended` (T-OR1 must ×2) | converge는 보고서를 쓴 뒤 tasks.md 끝에 `## Phase N: Convergence`를 append한다 (05-converge.md:17 "APPEND-ONLY, NEVER REWRITE", :155) | AOS `global.tasks.later_edits` (must): create_tasks 뒤 tasks.md 쓰기는 체크박스 외 변경이 있으면 실패 (`_norm_box` 비교, append도 실패). OSF `archive.run.paths_written.tasks_after_verify` (must): verify.md 뒤 tasks.md 쓰기 금지. SKB `order(invalidate=rewrite)` 3개 | AOS CW:63 "leave a file alone once its command is over, except for the checkboxes in tasks.md". OSF CW:105 "do not reopen tasks or apply". SKB CW:47 "Never rewrite an earlier report" | **충돌**. 끝난 산출물에 내용을 더하는 행동 자체가 학습 셋 셋 다에서 벌점이다 |
| `specify.spec.item_format.no_na_section` (T-FM3 must) | spec.md에 `N/A`만 적힌 줄 없음 (01-specify.md:147 "remove it entirely, don't leave as N/A") | AOS `final_verification.report.incomplete_listed`·`failed_listed`: 해당 없음을 "None" 한 줄로 적는 것을 보상. SKB `fix.field_literal` ×9: `Previous verification: none` 등 리터럴 요구 | AOS implement-tasks.md:279 "note \"None\" if all complete", :306 "None - all tests passing". SKB 02-fix.md:55, :90 "Empty if none" | **충돌(약함)**. 리터럴(None vs N/A)과 위치(필드 vs 절)가 달라 가장 약하다. 11 문서 3절이 BMAD D40에 같은 기준을 적용했으므로 일관성 위해 유지. SDD 자체도 plan 산출물에는 `N/A — <reason>` 본문을 요구해(02-plan.md:43) 문서 안에서 방향이 갈린다 |

### 5.2 대조했으나 충돌이 아닌 것 (후보였던 것 포함)

| SDD 규칙 | 학습 쪽 대응 | 판정 |
|---|---|---|
| `global.prohibited_action.git_branch` (T-PR6) | 학습 문서·규칙 어디에도 git branch 지시 없음(grep `git|branch`: OSF explore의 "Skip branches"는 결정 분기). OSF T-PR6은 `init`·`--schema`·`--no-validate` 금지 | 같은 템플릿, 다른 명령. L1 |
| `tasks.item_format.unchecked_when_written` (T-PG1) | AOS `create_tasks.item_format.unchecked` (should, `[x]` 0개), OSF `ff.tasks.unchecked_at_plan` (must) | 같음. L1 |
| `*.doc_read.constitution` ×4 (T-RD5) | AOS CW:32 "there are no separate standards files to open"은 AOS의 표준이 문서 안에 있다는 설명이지 파일 읽기 금지가 아님. AOS README·packaging·config 읽기 보상은 같은 방향 | 같음. L1. 습관 위험("표준 파일은 찾지 않는다")은 있으나 반대 *지시*는 아님 |
| `implement_2.doc_read.im`, `converge_2.doc_read.cv` (T-RD2) | SKB fix_2/fix_3 `doc_read.fx`, test_2/test_3 `doc_read.ts`가 라운드마다 재독을 보상 | 같음. L1. 반대 규칙(T-OR3 복귀 금지)은 ifeval에만 있고 학습 셋에는 없다 |
| `global.speckit_holds.at_most_two_rounds` (T-OR2) | SKB는 3라운드까지 허용(CW:20), `no_round_after_verified` 보상 | 가까운 변형(상한 2 vs 3). 수치는 인스턴스 값(`templates.yaml` 머리말). L1 |
| `global.speckit_holds.no_round_after_converged` (T-OR2) | SKB `no_round_after_verified` | 같음(트리거 리터럴만 다름). L1 |
| `converge.tasks.write_discipline.append_only` (T-WD2) | OSF `tasks_after_verify`, AOS `later_edits` | tasks.md를 안 쓰면 통과하므로 학습 습관이 그대로 만족. 충돌은 `appended`가 진다. L1 |
| `converge*.speckit_holds.tasks_unchanged_when_converged` (T-WD4) | 위와 같음 | 같음. L1 |
| `implement.checks.red_green` (T-AW2) | SKB 03-test.md:43 "passes now after failing before the change", SKB `check_scripts.before_change`, AOS `checks.before_code` | 같음. L1 |
| `implement.speckit_holds.tests_pass` (T-AW3 should) | AOS `verify(whole_suite)`는 마지막 실행을 전체 스위트로 만들어 기존 실패가 섞이면 이 항목을 떨어뜨릴 수 있음 | 반대 *지시*는 아님(실패를 보상하는 규칙 없음). L1. 습관 위험으로만 기록 |
| `implement.exec_evidence.baseline` (T-AW2) | SKB `fix.exec_evidence.baseline`(start..첫 수정), AOS `before_code` | 같음(구간 시작점만 다름). L1 |
| `global.untouched.shipped` (T-WD3) | OSF CW:34 "Never run openspec init again", 00-explore.md:18 "do not hand-create openspec/ files" | 같음. L1 |
| `global.prohibited_action.ignore_files` (T-PR2) | 학습에 ignore 파일 언급 없음. T-PR2 scratch 패턴은 같은 방향 | 같음. L1 |

ifeval의 충돌 네 유형(T-AW4 지연 실행, T-RD6 재독 금지, T-OR3 복귀 금지, T-PR5 전체 스위트 금지)에 해당하는 규칙은 SDD에 없다. SDD는 Spec Kit 계열이라 라운드·재독·체크 즉시 실행이 SKB와 같은 방향이고, 유일하게 반대인 것은 "끝난 산출물(tasks.md)에 append"다. 3단계를 전수로 돌린 뒤에도 4절의 층 수치는 그대로다(L1 232 / L1C 3 / L2M 1 / L2F 6).
