# 13. L1-충돌 방향 대조: ifeval과 학습 세 workflow

> 작성: 2026-11-06. 앞 단계: `10_handover_templates_layers.md` §3.2(3단계 "방향"), `12_speckit_sdd_templates.md` §5(SDD 쪽 대조).
> 입력: `aidlc_v4_ifeval/constraints.yaml`(implemented 192), 학습 세 workflow의 `constraints.yaml`과 `docs/`, `aidlc_v4_ifeval/docs/`.
> 약어: AOS = agentos_v2, OSF = openspec_ff, SKB = speckit_bug, CW = core-workflow.md. "AOS impl:237"은 `agentos_v2/docs/commands/implement-tasks/implement-tasks.md` 237행.

## 0. 원칙

10 §3.2의 2단계(같은 템플릿을 학습이 보상하나)는 L1 *후보*를 고르는 단계이고, 3단계(학습 규칙·문서가 반대 방향인가)가 L1과 L1-충돌을 가른다. 두 판정은 독립이다.

- 같은 템플릿 안에서 인스턴스마다 층이 갈릴 수 있다. ifeval T-PR5: 기록한 명령의 형태 2개는 L1, 전체 suite 실행 금지 1개는 L1C.
- 템플릿이 학습에 없어도 L1C가 된다. ifeval T-RD6(재독 금지)은 학습에 같은 템플릿이 없지만 학습 T-RD4(읽어야 함)가 반대 방향이라 L2가 아니라 L1C다.
- 학습 workflow 셋 중 **하나라도** 반대면 충돌이다. T-PR5는 AOS implement 단계가 같은 방향(should)인데도 AOS verify 단계의 `whole_suite`(must) 때문에 충돌이다. L1C가 묻는 것은 "습관이 현재 문서를 이기나"이고, 습관은 어느 학습 workflow에서든 생기기 때문이다.

## 1. ifeval의 L1-충돌 5개: 무엇과 충돌하나

| ifeval 항목 | ifeval 지시 | 반대 방향의 학습 규칙 (implemented) | 반대 방향의 학습 문서 |
|---|---|---|---|
| `code_generation_generation.run.prohibited_action.execute` (T-AW4 must) | 4단계는 재현 스크립트를 **쓰되 실행하지 않는다** (CG:28, CW:113) | SKB `fix.run.check_scripts.before_change` (must): 수정 전에 체크를 **실행**해야 함. AOS `implement_tasks.run.checks.before_code` + create-tasks의 "Run ONLY the 2-8 tests written" (작성 즉시 실행이 과업 구조) | SKB 02-fix.md:30-32 "Before editing any code … Run each check now. It must fail". AOS create-tasks.md:73,104,148 |
| `code_generation_generation.a4.field_literal.executed` (T-RF2 must) | `Executed: no`를 적고, 실제로 실행했으면 반박됨 | 위와 같은 사실(T-AW4)을 기록 쪽에서 본 것 | 위와 같음 |
| `global.run.no_reread` (T-RD6 must) | 아직 보이는 자기 산출물을 다시 읽지 않는다 (CW:42-43) | AOS `*.run.agentos_v2_read.*` (must ×3, should ×2), SKB `*.run.speckit_bug_read.reports` (must ×7), OSF `*.read_files.*` (must ×5): 단계 구간 안에 이전 산출물을 **읽어야** 함 | OSF 01-ff.md:56 "always re-read them from disk, even if you saw them earlier", :107 "re-read from disk, not from conversation memory". SKB 02-fix.md:20-21 "Read assessment.md in full … also read the previous round's fix report and verification report in full". AOS create-tasks:13은 "맥락에 없으면 읽어라"로 부분적으로 같은 방향(04 §7) |
| `global.run.no_return` (T-OR3 must) | 이전 단계로 돌아가지 않는다. 이전 단계 문서를 다시 열지 않는다 (CW:71, BT:58) | SKB `fix_2/fix_3.run.doc_read.fx`, `test_2/test_3.run.doc_read.ts` (must): 라운드마다 같은 단계 문서를 **다시** 읽어야 함. SKB `order.round_2/3` | OSF CW:26 "apply may send you back to ff", 02-apply.md:52 "go back to the ff stage document … then resume this stage". SKB CW:20-27 fix→test→fix 라운드 |
| `build_and_test.run.prohibited_action.full_suite` (T-PR5 must) | 5단계는 전체 테스트 suite를 돌리지 않는다 (RE:27 "not the whole suite", BT) | AOS `implement_tasks.run.verify.whole_suite` (must), `verify.suite_run` (must): 검증 단계에서 **전체 suite를 한 번** 돌려야 함 | AOS impl:237-239 "Step 3: Run entire tests suite … so that ALL tests run". SKB 03-test.md:31 "Run any broader regression suite that touches the changed files" (문서만, 규칙 없음) |

다섯 개 모두 "같은 템플릿이 학습에 있다"와 무관하게 결정됐다. T-AW4·T-RD6·T-OR3은 학습에 같은 템플릿이 없고(ifeval 전용 kind), T-PR5·T-RF2는 같은 템플릿이 학습에 있는데도 인스턴스가 반대라 충돌이다.

## 2. ifeval의 L1 행동 규칙 대조: 추가 후보 2개

ifeval의 L1 행동 규칙(S10 형식 제외, 60개)을 같은 방식으로 대조했다. 대부분은 같은 방향이다(T-WD1 once ×5 = SKB once ×7; T-RD3 no_read_ahead = 학습 `order(invalidate=read_ahead)`; T-AW2 baseline = SKB baseline; T-PR1·T-PR2·T-PR3·T-RF1·T-RF4·T-TR1·T-AW1·T-AW3·T-RD1·T-RD4 모두 같은 방향). T-PR3(설치 금지)은 02 문서가 system prompt `<ENVIRONMENT_SETUP>`과 충돌로 봤으나, 현재 네 workflow의 system-prompt.j2 어디에도 설치 지시가 없다(남은 것은 보안 정책 문장). 반대 방향이 보이는 것은 둘이다.

| ifeval 항목 (현재 층) | 반대 방향의 학습 쪽 | 판단 |
|---|---|---|
| `global.a1~a4.write_discipline.no_rewrite` (T-WD2 must ×4, L1) | **OSF 문서**: 02-apply.md:103 "Implementation reveals a design issue → update the affected artifact (design, specs or tasks) yourself", :151 같은 문장. OSF 규칙은 없다(`tasks_after_verify`는 verify 뒤만 막음). 같은 방향: SKB `order(invalidate=rewrite)` ×3, SKB CW:47, AOS CW:63 | 02 문서 G8과 04 §7이 이미 "같음(SKB) / 충돌(OSF)"로 적었는데 constraints.yaml은 템플릿 기본값 L1을 그대로 썼다. 0절 원칙(하나라도 반대면 충돌)대로면 **L1C 후보**. 다만 반대가 문서뿐이고 규칙 보상이 없어, ifeval 다른 L1C 넷(규칙 보상이 반대)보다 약하다. 옮기면 L1C가 5→9, L1이 168→164 |
| `build_and_test.a5.field_type.command` (T-PR5 must, L1, 이유 "기록한 명령의 형태") | AOS `verify.whole_suite` 습관은 5단계의 마지막 테스트 명령을 전체 suite로 만들고, 그 명령을 그대로 적으면 `test_selection` 판정에 걸린다 | `full_suite` 항목과 **같은 행동**을 기록 쪽에서 보는 것이라, T-RF2 `executed`가 T-AW4의 기록판으로 L1C인 것과 같은 논리가 선다. 1단계의 `a1.field_type.test_selection`은 다르다. 1단계에는 AOS 전체 suite 습관이 작용하지 않고 SKB baseline(바꿀 파일의 테스트만)이 같은 방향이라 L1이 맞다 |

둘 다 constraints.yaml을 고치지는 않았다. 08·09의 층별 수치가 현재 라벨로 계산돼 있어, 라벨을 바꾸면 그 문서들의 L1C 행을 다시 뽑아야 한다. 바꾼다면 `layer_reason`에 위 근거를 적고 `reward/build.py`로 layers.yaml을 재생성하면 된다(10 §3.4).

## 3. 학습 세 workflow끼리의 반대 방향

학습 셋은 층을 매기지 않지만, 셋 사이(또는 한 workflow의 단계 사이)에 반대 방향 규칙이 있으면 그것이 L1-충돌의 원천이고, 모델은 "문서를 보고 고르는" 쪽으로 학습된다. 발견한 것은 다섯 가지다.

| 행동 | 한쪽 | 반대쪽 | 비고 |
|---|---|---|---|
| 전체 suite 실행 | AOS implement PHASE 2: `prohibited_action.full_suite_phase2` (should), create-tasks "Run ONLY the newly written tests, not the entire suite" (:212) | AOS implement PHASE 3: `verify.whole_suite` (must), impl:237 "Run entire tests suite". SKB 03-test.md:31 "broader regression suite" | **한 workflow 안에서 단계별로 반대**. ifeval T-PR5 충돌의 원천 |
| 이전 단계로 돌아가기 | AOS CW:27 "Each command runs once … There are no repeat rounds". SKB·OSF `order(invalidate=multi_read)`: 라운드 1에서 단계 문서를 두 번 읽으면 무효 | OSF CW:26, 02-apply.md:52 "go back to the ff stage document". SKB 라운드 2·3: `fix_2.doc_read.fx` (must)가 같은 문서 재독을 **보상** | SKB는 같은 행동(FX 재독)을 라운드 1에서는 벌하고 라운드 2에서는 보상한다. ifeval T-OR3 충돌의 원천 |
| 끝난 산출물 고치기 | SKB `order(invalidate=rewrite)`, `write_discipline.once` ×7, CW:47 "Never rewrite an earlier report". AOS `holds.spec_left_alone`·`shape_files_left_alone` (must), CW:63 | OSF 02-apply.md:103,151 "update the affected artifact (design, specs or tasks) yourself" (문서만) | ifeval T-WD2(2절 후보)와 SDD `appended`(12 §5) 충돌의 원천 |
| tasks.md에 체크 외의 쓰기 | AOS `global.tasks.later_edits` (must): 체크박스 외 변경은 실패 | OSF 02-apply.md:102 "note that reading under the task in tasks.md as a plain line (not a checkbox)", CW:55 | OSF 규칙은 verify 뒤 쓰기만 막음(`tasks_after_verify`). SDD converge의 phase append는 OSF 문서와 부분적으로 같은 방향이라, 12 §5.1의 첫 충돌은 "AOS·SKB 규칙 + OSF 문서(verify 뒤)와 반대, OSF 문서(apply 중)와는 부분 일치"로 읽어야 정확하다 |
| 체크를 쓰고 바로 실행 | SKB 02-fix.md:32 "Run each check now. It must fail", `check_scripts.before_change` (must) | 학습 안에는 반대가 없다 | ifeval T-AW4(지연 실행)만 반대. 학습 셋이 한 방향이라 가장 순수한 "습관 vs 지시" 항목이고, 08·09에서 base→step27 변화가 가장 컸던 충돌 항목(0.59→0.77, 0.55→0.66) |

재독(T-RD4)과 설치 금지(T-PR3), 테스트 파일 수정 금지(T-PR1), 저장소 밖 산출물(T-WD3·T-PR2)은 학습 셋이 모두 같은 방향이다. 재독은 ifeval T-RD6과만 반대이고, 나머지 셋은 어느 평가와도 반대가 없다.

## 4. 정리

- ifeval의 L1C 5개는 모두 구체적인 학습 규칙(must)과 반대다. 템플릿 일치 여부로 결정된 것은 하나도 없다.
- 전수 대조에서 나온 추가 후보는 T-WD2 `no_rewrite` ×4(OSF 문서와 반대, 규칙 보상은 없음)와 `a5.field_type.command`(T-PR5 기록판)다. 전자는 02·04 문서가 이미 충돌로 적은 것을 constraints가 반영하지 않은 것이고, 후자는 T-RF2 `executed`와 같은 논리다. 라벨을 바꿀지는 08·09 재계산 비용과 함께 정해야 한다.
- 학습 셋 안의 반대 방향은 다섯 가지이고, 그중 넷이 ifeval·SDD 충돌 항목의 원천이다. 02 §10의 권장("충돌의 원인인 학습 쪽 고유 행동은 학습에 남긴다")이 유지되는 한 이 표가 충돌 항목의 근거 목록이다.
