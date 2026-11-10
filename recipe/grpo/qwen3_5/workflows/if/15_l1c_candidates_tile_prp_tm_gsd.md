# 15. 학습 후보 4종이 평가에 새로 만드는 L1C: SDD tile, PRP, Task Master, GSD

> 작성: 2026-11-08
> 질문: tesslio/spec-driven-development-tile, Wirasm/prp, eyaltoledano/claude-task-master, gsd-build/get-shit-done 를 학습 workflow로 추가하면 평가 두 벌(aidlc_v4_ifeval, speckit_sdd)의 어떤 항목이 L1C로 바뀌는가. 14 문서(BMAD·SPARC)와 같은 틀.
> 입력: 네 저장소의 checkout(`/vast-ib/MMI/home/kyuminkim/project/if/workflows/{spec-driven-development-tile,prp,claude-task-master,get-shit-done}`, 2026-11-08 clone, 커밋은 각 절 머리에). 규칙 조사는 네 개의 Explore agent가 했고, 판정을 가르는 인용 20여 개는 내가 원문에서 다시 확인했다. rules.yaml 수준의 포팅 전 인벤토리(11 문서)는 아직 없으므로 "확정"은 그 workflow의 핵심 경로가 그 행동을 지시한다는 뜻이고, port에서 그 문장을 빼면 사라진다.
> 표기: "평가가 요구하는 행동" ↔ "후보가 시키는 행동". 항목 id·파일 줄은 괄호 안.

## 0. 한눈에

| | SDD tile | PRP | Task Master | GSD | (참고) BMAD | (참고) SPARC |
|---|---|---|---|---|---|---|
| 에이전트 지시문 크기 | 480줄 | 주 흐름 5 skill 약 700줄 + 서브에이전트 11 | 규칙 3파일 1,430줄 + 플러그인 | workflows 35k줄 + agents 15k줄 | 1,045줄 | 코드 포함 72규칙 |
| 계획 산출물의 생애 | 리뷰·검증 때 계속 고침 | **한 번 쓰고 봉인**, 결과는 보고서에 | 구현 중 로그 덧붙임·상태 변경 | STATE/ROADMAP/REQUIREMENTS 계속 갱신 | status·로그 갱신 | append-only |
| 모호할 때 | 사람에게 한 번에 한 질문, 승인 전 코드 금지 | 제품 결정만 묻고 나머지는 기록 후 계속 | 핵심 규칙엔 없음; 플러그인은 질문 | 기본은 질문; `--auto`/`yolo`는 추천안 선택 후 기록 | 질문 적고 HALT | (drop) |
| 테스트 | 요구사항마다 테스트 파일 만들고 링크 | 회귀 테스트 작성, 전체 gate 실행 | "코드와 테스트 작성", `npm test` | TDD RED→GREEN, 테스트를 커밋, 전체 suite gate | edge case 단위 테스트 task | 명령 실행 안 함 |
| 산출물 위치 | 저장소 안 `specs/` | **저장소 밖** `~/.prp/` | 저장소 안 `.taskmaster/` (커밋) | 저장소 안 `.planning/` (커밋) | 저장소 안 `_bmad-output/` | 저장소 밖 |
| git | 읽기만 | 브랜치·커밋·PR | subtask마다 커밋 | task마다 커밋, worktree | diff만 | 없음 |
| 오프라인 포팅 장애 | 사람 승인 게이트가 핵심 | 서브에이전트·GitHub·gh | MCP/CLI + AI API 키 | 서브에이전트·gsd-sdk·MCP·hooks | 서브에이전트 | CLI |
| **ifeval L1C 5 →** (확정 / 전부) | 11 / 19 | 5 / 13 | 11 / 17 | 16 / 20 | 11 / 19 | 5 / 5 |
| **SDD L1C 3 →** (확정 / 전부) | 4 / 8 | 3 / 7 | 3 / 5 | 7 / 10 | 5 / 9 | 3 / 3 |

확정에 들어가는 것은 어디서나 같은 한 가지 습관이다: 계획 산출물을 뒤 단계에서 다시 쓴다. PRP만 이 습관이 없다. 조건부는 14 문서와 같은 세 결정(모르면 멈춤 유지 / 테스트를 저장소 파일로 / 산출물을 저장소 안에)에 git 결정 하나가 더해진다.

## 1. spec-driven-development-tile (b8fdff7, v2.0.1)

4개 skill, 3개 rule, 3개 doc. 단계는 gather → spec → approve → implement → review → verify인데 implement 단계 문서가 없다. 산출물은 `specs/*.spec.md` 하나(frontmatter `name/description/targets`, 요구사항 불릿, 인라인 `` `[@test] path` `` 링크).

### 1.1 확정 L1C

| 평가가 요구 | tile이 지시 | 걸리는 항목 |
|---|---|---|
| 산출물은 자기 단계 끝에 한 번 쓰고 봉인 | 리뷰 단계에서 "발견한 요구사항을 해당 spec에 추가하고 만든 테스트를 링크"(work-review:47-49), "targets·[@test] 링크 갱신"(:51-53); 검증 단계에서 "코드가 행동을 바꿨으면 spec을 먼저 고치고 재검증"(spec-verification:59-61); 스타일가이드 "spec을 구현과 동기화"(:9). 스펙은 살아 있는 문서 | ifeval `once` ×5, `order.stages`; SDD `spec_written_by_specify` |

→ ifeval 5 → 11, SDD 3 → 4.

### 1.2 조건부 L1C

| 평가가 요구 | tile이 지시 | 조건 |
|---|---|---|
| 질문 파일 없음, 입력 요청으로 끝내지 않음 (ifeval L2M ×2); 표식은 가장 타당한 답으로 해소 (SDD `clarifications_resolved`) | "한 메시지에 정확히 한 질문을 하고 답을 기다린다"(one-question-at-a-time:7, alwaysApply), "요구사항이 확인되기 전엔 구현 시작 금지"(requirement-gathering:25), "spec에 명시적 승인을 받기 전엔 코드 금지; 침묵은 승인이 아님"(spec-before-code:16,27-29) | 이것이 tile의 정체성이다. "멈춤"으로 남기면 L1C ×3. 빼면 1·3단계가 통째로 사라져 tile에는 spec 형식 + 리뷰만 남는다 |
| 테스트 파일을 만들지도 고치지도 않음 (ifeval ×5, SDD ×2) | 요구사항마다 테스트 파일 하나를 만들어 링크(spec-writer:50-51, styleguide:8 "요구사항별로 분리된 테스트 파일"), 리뷰에서 "새 테스트 추가"(work-review:70) | 저장소 `tests/`면 L1C ×7. `[@test]` 경로를 checks/로 돌리면 비충돌 |
| 저장소에 선언 안 된 파일 없음 (ifeval ×1, SDD ×1) | "spec은 프로젝트의 `specs/` 디렉터리에"(spec-format-compliance:44) | /tmp로 옮기면 비충돌 |

### 1.3 그 밖에

- **전체 suite 금지와 같은 방향인 첫 학습 후보.** "링크된 테스트를 실행"(work-review:36, spec-verification:40)만 하고 전체 suite 지시가 없다. ifeval `full_suite`(L1C, AOS 반대)에 처음으로 같은 편 학습 규칙이 생긴다. 라벨은 AOS 때문에 유지.
- 재독·복귀 반대 출처 추가: 리뷰·검증에서 targets 파일 재독(work-review:31, spec-verification:47), 구현 뒤 spec-writer로 복귀(spec-writer:19).
- 층 이동: ifeval `frontmatter` ×5 L2F → L1 (`name/description/targets` 필수 frontmatter).
- 수정 전 테스트 실행(baseline)·TDD·재현 스크립트·명령 기록 없음. 기록은 pass/fail 수뿐.
- 단계 문서 사슬이 없다(skill은 설명으로 트리거, rule은 항상 컨텍스트). T-RD1/2/3·T-OR1을 가르치려면 port가 사슬을 새로 만들어야 한다.

## 2. PRP (4352925)

주 흐름 `/prp-issue`: prp-plan → prp-implement → prp-review → 교정 → CI. 계획은 `~/.prp/<key>/plans/<name>.plan.md`(굵은 `**Key:**` 머리줄, 섹션, `None` 리터럴), 결과는 `reports/<plan>-report.md`, 리뷰는 `reviews/`. 옛 흐름(old-prp-commands)은 저장소 안 `PRPs/`에 두고 완료 시 `completed/`로 옮기는데, 저장소가 "참고용"이라 밝혀 현재 흐름만 본다.

### 2.1 확정 L1C: 없음

- 계획은 한 번 쓴다: "계획은 내구성 있는 구현 계약… 계획을 변경하거나 보관하지 않고 현재 진실을 복구한다"(plugins/prp-core/README:219), "계획을 옮기거나 보관하지 않는다"(prp-implement:110,191), "아무것도 유지하지 않는 상태 섹션을 넣지 않는다"(AGENTS:19). → ifeval `once`·SDD spec/plan 고정과 **같은 방향**. 네 후보 중 유일.
- 산출물은 저장소 밖(README:190). → 같은 방향.

### 2.2 조건부 L1C

| 평가가 요구 | PRP가 지시 | 조건 |
|---|---|---|
| 질문으로 끝내지 않음 (ifeval ×2), 표식 해소 (SDD ×1) | "모호함이 제품 계약을 바꾸거나 실질적으로 다른 계획을 낳을 때만 사용자에게 묻는다"(prp-plan:51), "현실이 의도를 모호하게 하면 멈추고 묻는다; 아니면 필요한 이탈을 기록하고 계속"(prp-implement:52), 다섯 조건의 설계 게이트(prp-plan:127-133) | BMAD보다 좁은 트리거지만 같은 분기. "멈춤" 유지면 L1C ×3; "기록하고 계속"만 남기면 T-SR1 같은 방향 |
| 테스트 파일 작성 금지 (ifeval ×5, SDD ×2) | "바뀐 행동을 증명하는 집중 테스트를 쓴다… 버그 수정에는 수정 전 실패하고 후에 통과하는 회귀 테스트"(prp-implement:101), task마다 **Tests** 절(plan-template:113-117), "task 수준 명령은 그 행동이 없으면 실패해야"(task-format:37) | 저장소 파일이면 L1C ×7; checks/로 돌리면 비충돌 |
| git 브랜치 만들지 않음 (SDD `git_branch`) | "기본 브랜치에 깨끗한 worktree로 있으면 집중 feature 브랜치를 만든다"(prp-implement:54), 커밋(prp-commit), PR(prp-pr) | GitHub 부분은 어차피 drop. 브랜치·커밋을 남기면 SDD L1C ×1 |
| 라운드마다 새 보고서 (SDD `report_written_once_per_round`) | "교정 패스는 이 보고서를 현재 진실로 갱신한다; 병렬 교정 산출물을 만들지 않는다"(prp-implement:149) | 교정 패스(리뷰 → 수정)를 port에 남기면 SDD L1C ×1. ifeval A5 `once`도 같은 이유로 걸리지만 ifeval엔 교정 라운드가 없어 약함 |

### 2.3 그 밖에

- 반대 출처 추가: 전체 gate 실행 "계획의 Validation 절의 모든 적용 가능한 명령(suite, lint, build)을 돌린다"(prp-implement:114-116) → `full_suite`에 AOS 다음 둘째 출처. "고치기 전에 버그를 재현한다"(:98) → ifeval 4단계 "스크립트는 쓰되 실행하지 않음"에 SKB 다음 둘째 출처. "파일 전체를 읽는다"(:44), 마지막에 "브랜치 diff·계획·보고서를 다시 읽는다"(:189) → no_reread; 계획이 낡으면 "/prp-plan을 다시 호출"(:46) → no_return.
- 같은 방향이 두드러진 곳: 기록의 사실성. "실제 명령 / passed|failed / 결정적 출력" 표(implementation-report:13-15), "실행하지 않은 검사는 `not run`이지 pass가 아니다"(review agents:89-90), "실제로 돈 검증만 보고"(prp-pr:165). T-RF1/RF2 보강. 템플릿을 "쓰기 전에 읽고 그 구조를 정확히 따른다"(:149) → T-RD2.
- 층 이동: ifeval T-RF3 ×3 L2M → L1 가능성(보고서에 바뀐 파일 목록이 있으나 "= diff" 규칙은 명시 없음, 확인 필요).
- 수정 전 테스트 실행 없음("편집 전에 기존 테스트를 읽는다"(:50)는 읽기지 실행이 아님).
- 포팅 비용: 계획 단계가 서브에이전트 3종을 "필수"로 띄우고(prp-plan:59-63) 리뷰도 서브에이전트, 발행·PR·CI는 GitHub. 주 흐름을 단일 에이전트 md 사슬로 바꿔야 한다.

## 3. Task Master (c0c98d3)

규칙 파일 3개(dev_workflow 423, taskmaster 572, AGENTS 435줄). 단계 문서 대신 도구 조회로 일한다: `show` → 탐색 → `update_subtask`로 계획 로그 → `show`로 확인 → `set-status in-progress` → 구현 중 `update_subtask` 반복 → `set-status done` → `git commit` → `next`. 산출물은 저장소 안 `.taskmaster/tasks/tasks.json`(+ task md 파일), PRD.

### 3.1 확정 L1C

| 평가가 요구 | Task Master가 지시 | 걸리는 항목 |
|---|---|---|
| 산출물은 한 번 쓰고 봉인 | 구현 전 계획을 subtask details에 타임스탬프 로그로 덧붙이고(dev_workflow:376-377), 구현 중 "**정기적으로** update_subtask로 새 발견을 덧붙인다"(:389), 상태를 pending → in-progress → done으로 바꾼다(:383, :404). 핵심 루프 자체 | ifeval `once` ×5, `order.stages` |

→ ifeval 5 → 11. SDD는 바뀌지 않는다: SDD `later_edits`는 체크 **또는 덧붙임**을 허용하므로 TM의 append 로그는 통과하고, TM에는 spec·plan에 해당하는 고정 산출물이 없다(PRD는 수정 지시 없음).

### 3.2 조건부 L1C

| 평가가 요구 | Task Master가 지시 | 조건 |
|---|---|---|
| tasks.md는 체크·덧붙임만 (SDD `later_edits`) | "구현이 계획과 크게 달라지면 `update --from=<futureTaskId>`로 미래 task들을 다시 쓴다"(:243-247) | 드리프트 때만 발동. 남기면 SDD L1C ×1 |
| 테스트 파일 작성 금지 (ifeval ×5, SDD ×2) | 기본 루프 "사용자가 코드와 테스트를 쓴다"(:20), 플러그인 executor "task의 테스트 전략을 구현"(task-executor:31), loop 프리셋 "구현과 함께 테스트를 쓴다"(presets/default.ts:13) | 저장소 파일이면 L1C ×7 |
| 저장소에 파일 없음 (ifeval ×1, SDD ×1) | `.taskmaster/`는 저장소 안이고 기본값으로 git에 저장(init.js:377) | /tmp로 옮기면 비충돌 |
| 질문으로 끝내지 않음 | 핵심 규칙 3파일엔 질문 규칙이 없다. 플러그인 executor "요구가 모호하면 설명을 요청"(task-executor:59); loop 프리셋 "막히면 `<loop-blocked>REASON</loop-blocked>` 출력"(default.ts:25) | 플러그인을 쓰지 않으면 해당 없음. loop의 blocked 센티널은 질문이 아니라 약함 → 비충돌로 둠 |

### 3.3 그 밖에

- 반대 출처 추가: "로그가 덧붙여졌는지 `show`를 **다시 실행해 확인**"(:380) → no_reread에 BMAD D24와 같은 꼴의 둘째 출처. `npm test`(default.ts:15) → `full_suite`.
- 단계 문서가 없다. 읽기 규칙은 전부 도구 조회(`show`, `next`)라 T-RD1/2/3·T-OR1을 가르칠 문서 사슬을 port가 새로 써야 한다. 기록 규칙은 checker 보고의 `tests_run: command/result/output`(task-checker:98-101)뿐.
- 포팅 문제가 구조적이다. tasks.json 변경은 "절대 수동 편집하지 말고 명령을 쓴다"(AGENTS:408)인데, parse-prd·expand·update-subtask는 AI 공급자 키가 필요하다(taskmaster.mdc:13). 오프라인 port는 모델이 tasks.json을 직접 쓰는 방식이 되어 그 규칙이 뒤집히고, 서버가 강제하던 것(상태 enum, done task 수정 거부, autopilot RED/GREEN)도 사라진다. 남는 학습 내용은 "로그 덧붙임 + 상태 변경 + subtask마다 커밋"이라 ifeval 기준으론 L1C를 만드는 습관이 대부분이다.
- 문서 자체 모순(규칙 파일이 서로 다르게 말함): task 파일 자동 재생성 여부(dev_workflow:340 vs taskmaster.mdc:410), 상태 enum에 `blocked` 포함 여부(AGENTS:282-287 vs 코드), 수동 편집 금지 vs "수동 변경 뒤 generate"(AGENTS:408 vs 411).

## 4. GSD (bdcaab2)

workflows 106파일 35k줄, agents 33파일 15k줄. 주 흐름 new-project → discuss-phase → plan-phase → execute-phase → verify-work → complete-milestone. 산출물은 전부 저장소 안 `.planning/`: PROJECT·REQUIREMENTS·ROADMAP·STATE.md, 단계마다 CONTEXT·PLAN(YAML frontmatter + XML 태그)·SUMMARY·VERIFICATION.md. 가장 작은 흐름 `/gsd:fast`(105줄)는 PLAN·SUMMARY를 안 쓰고, `/gsd:quick`은 ROADMAP과 서브에이전트가 필요하다.

### 4.1 확정 L1C

| 평가가 요구 | GSD가 지시 | 걸리는 항목 |
|---|---|---|
| 산출물은 한 번 쓰고 봉인 | 계획 하나 끝날 때마다 STATE 전진·진행률·결정 기록, ROADMAP 진행률, REQUIREMENTS 체크(gsd-executor:665-703); SUMMARY에 `## Self-Check: PASSED/FAILED` 덧붙임(:656); 단계 완료 시 "STATE를 다음 단계로 전진"(execute-phase:1588-1595), PROJECT.md의 요구사항을 Active → Validated로 이동(:1676-1679) | ifeval `once` ×5, `order.stages`; SDD `spec_written_by_specify`(REQUIREMENTS.md 체크), `plan_docs_written_by_plan`(ROADMAP 갱신) |
| 테스트 파일을 만들지도 고치지도 않음 | 계획: "모든 `<verify>`에 `<automated>`; 테스트가 없으면 `MISSING — Wave 0 must create {test_file} first`로 적고 **스캐폴드를 만든다**"(gsd-planner:218). 실행: "RED: 테스트 파일을 만들고 실패하는 테스트를 쓰고 실행(반드시 실패), 커밋 `test(...)`; GREEN: 통과시키는 최소 코드, 커밋"(gsd-executor:366-370). 별도 `add-tests` 흐름 | ifeval T-PR1 ×3 + 기록판 ×2; SDD `test_file_write`, `created_files.tests`. BMAD·PRP·tile의 "테스트 작성"이 계획 문장인 데 비해 GSD는 테스트 파일 생성·실행·커밋이 실행 규칙에 박혀 있어 checks/로 돌리기 어렵다. 확정으로 둔다 |

→ ifeval 5 → 16, SDD 3 → 7.

### 4.2 조건부 L1C

| 평가가 요구 | GSD가 지시 | 조건 |
|---|---|---|
| 질문으로 끝내지 않음 (ifeval ×2), 표식 해소 (SDD ×1) | 기본은 묻는다: discuss 단계는 AskUserQuestion, executor Rule 4 "STOP → checkpoint, 사용자 결정 필요"(gsd-executor:211), "정말 모르겠으면 Rule 4"(:218). 그러나 `--auto`는 "추천 옵션을 AskUserQuestion 없이 고르고 선택을 인라인에 기록"(discuss-phase/modes/auto.md:20-26), `mode: yolo`는 "프롬프트 없이 자율 실행"(planning-config:230), `auto_advance`는 human-verify 자동 승인·decision 첫 옵션 선택(:296-300) | port가 yolo/auto를 쓰면 **같은 방향**(L2M → L1). 기본 모드를 남기면 L1C ×3 |
| 설치 금지 (ifeval·SDD `install`) | 패키지 설치는 "자동 수정 대상이 아니다; 사람 확인 checkpoint를 반환"(:180-184) → 같은 방향. 단 TDD는 "필요하면 테스트 프레임워크 설치"(:364) | TDD 문장을 남기면 L1C ×2 |
| 저장소에 파일 없음 (ifeval ×1, SDD ×1) | `.planning/`은 저장소 안이고 커밋한다(`commit_docs` 기본 true); "생성 파일을 untracked로 두지 않는다"(:528) | /tmp로 옮기고 커밋을 빼면 비충돌 |
| git 브랜치 없음 (SDD `git_branch`) | `branching_strategy` 기본 `none`(planning-config:31)이지만 `use_worktrees` 기본 true, executor는 `worktree-agent-*` 브랜치에 있어야 함(:469); task마다 커밋(git-integration:20) | worktree·커밋을 빼면 비충돌 |

### 4.3 그 밖에

- **재독 금지와 같은 방향인 첫 학습 후보.** "frontmatter로 충분하면 파일 본문을 다시 읽지 않는다", "다른 단계의 PLAN 전체를 절대 읽지 않는다"(universal-anti-patterns:18-20), "`<interfaces>`가 있으면 소스를 다시 읽지 않는다"(execute-plan:155), auto 모드 "자기 CONTEXT.md를 공백 찾으려 다시 읽지 않는다"(auto.md:34-39), "Edit/Write/Bash 없이 Read/Grep 5회 연속이면 STOP"(gsd-executor:248). ifeval `no_reread`(L1C)에 처음으로 같은 편 규칙이 생긴다. 반대편도 있다: "모든 작업 전에 STATE.md를 읽는다"(execute-plan:6), "read_first의 모든 파일을 편집 전에 읽는다; 이미 안다고 건너뛰지 않는다"(:174). 라벨은 AOS·SKB·OSF 때문에 유지.
- 반대 출처 추가: `full_suite` ← wave마다 전체 test gate(post-merge-gate:8-80) + "이전 단계들의 suite를 돌려 교차 회귀를 잡는다"(execute-phase:1301). 4단계 실행 금지 ← RED 실행(수정 전 테스트 실행). `no_return` ← "검증 실패 → plan-phase --gaps → 재실행 → 재검증"(execute-phase:1581).
- 같은 방향이 두드러진 곳: 증거 요구. "SUMMARY의 주장을 믿지 않는다; SUMMARY는 Claude가 했다고 **말한** 것"(gsd-verifier:21), "코드베이스 증거가 증명할 때까지 목표 미달성으로 가정"(:26), 실패 probe는 stdout/stderr 필수(:520); executor 자가 점검 "만든 파일 존재·커밋 존재 확인, 실패하면 상태 갱신으로 가지 않음"(:644-658). T-RF1/RF2/RF3 보강. 읽기 규율 "에이전트 정의 파일을 절대 읽지 않는다"(context-budget:15), "플래그가 없으면 모드 파일을 읽지 않는다"(discuss-phase:33) → T-RD3.
- 층 이동: ifeval `frontmatter` ×5 L2F → L1(PLAN·SUMMARY·VERIFICATION frontmatter), T-RF3 L2M → L1(SUMMARY `key-files` vs 실제 파일·커밋 자가 점검).
- 포팅 비용이 가장 크다. 거의 모든 상태 변경이 `gsd-sdk query` CLI를 거치고("STATE.md·ROADMAP.md를 Write/Edit로 직접 바꾸지 않는다", anti-patterns:37), 실행은 planner·executor·verifier 서브에이전트와 worktree 병렬 wave, 문서 조회는 Context7 MCP, 커밋 메시지는 hook이 검사한다. 단일 에이전트·오프라인으로 줄이면 execute-phase 1,802줄 중 orchestrator 규칙(단일 작성자, checkpoint 반환, worktree 단언)이 대부분 빠진다. 가장 작은 `fast`는 산출물이 STATE 표 한 줄뿐이라 채점할 것이 없다.

## 5. 네 후보를 가르는 축

1. **계획 산출물을 다시 쓰는가.** tile·TM·GSD·BMAD는 쓴다(ifeval `once` ×5 + `order.stages`가 확정 L1C). PRP·SPARC만 안 쓴다. 이 축이 확정 L1C의 전부다.
2. **테스트를 쓰는가.** 넷 다 쓴다. tile·PRP·TM은 계획 문장이라 checks/로 돌릴 수 있고, GSD는 RED 커밋이 실행 규칙이라 돌리기 어렵다.
3. **모르면 어떻게 하는가.** tile은 묻는 것이 정체성(빼면 남는 게 없음), PRP·GSD는 묻는 모드와 기록하는 모드가 둘 다 있어 port가 고를 수 있음, TM은 핵심 규칙에 없음.
4. **어디에 쓰고 git을 만지는가.** PRP만 저장소 밖. tile은 git을 안 만지고, PRP·TM·GSD는 브랜치나 커밋을 만든다(SDD `git_branch`, ifeval `unintended_files`).
5. **평가 편에 서는 규칙이 있는가.** tile은 "링크된 테스트만 실행"으로 `full_suite` 편, GSD는 "다시 읽지 않는다" 다섯 문장으로 `no_reread` 편. 둘 다 라벨은 못 바꾸지만(AOS·SKB·OSF가 남음) 학습 습관의 혼합비를 바꾼다. 11·13·14 문서에서 이 두 항목은 학습 안에 같은 편이 하나도 없던 것들이다.

## 6. 정리

- 확정 L1C 증가분(ifeval / SDD): tile +6 / +1, PRP 0 / 0, TM +6 / 0, GSD +11 / +4. BMAD +6 / +2, SPARC 0 / 0.
- 조건부까지 전부 유지하면: tile 19 / 8, PRP 13 / 7, TM 17 / 5, GSD 20 / 10.
- L1C를 가장 안 늘리는 후보는 PRP다. 계획 봉인·저장소 밖 산출물·기록 사실성이 평가와 같은 방향이고, 반대는 전부 port가 고를 수 있는 분기(묻기, 테스트 위치, 브랜치, 교정 패스)에 있다. 대신 서브에이전트·GitHub를 단일 md 사슬로 바꾸는 비용이 든다.
- L1C를 가장 늘리는 후보는 GSD다. 상태 파일 갱신과 TDD 커밋이 실행 규칙이라 확정이 11개고, 포팅 비용도 가장 크다. 반면 `no_reread` 편의 유일한 학습 규칙과 가장 강한 증거 규율을 갖고 있어, L1C k를 **의도적으로** 키우면서도 평가 항목 일부에 같은 편을 세우고 싶다면 가치가 있다.
- tile은 작아서 포팅이 쉽지만, 사람 승인 게이트를 빼면 spec 형식과 리뷰 재독만 남는다. TM은 단계 문서가 없고 도구·API 키 의존이라 오프라인 port가 원형과 멀어진다.
- 이 문서의 숫자는 rules.yaml 없이 핵심 경로 문장으로 판정한 것이다. 후보를 고르면 11 문서처럼 규칙 인벤토리를 만들고 1단계 조사 → 2단계 gap 감사를 거쳐 확정/조건부를 다시 센다. constraints.yaml·sdd_layers.yaml은 바꾸지 않았다.

## 7. L2-먼과의 관계

L2-먼은 "평가 항목의 템플릿을 학습이 보상도 노출도 하지 않음"이므로 학습 workflow를 추가하면 줄어들 수만 있다. 두 방향으로 센다.

### 7.1 학습에 넣었을 때 평가의 L2-먼이 얼마나 남는가

현재 L2-먼: ifeval 6(frontmatter ×5, 계획 step과 같은 요구 id 인용 ×1), SDD 6(산출물 내부 일관성).

| 추가 | ifeval 6 → | SDD 6 → | 이유 |
|---|---|---|---|
| PRP, Task Master, SPARC(CLI) | 6 | 6 | 두 평가의 L2-먼 템플릿을 건드리지 않음 |
| tile, BMAD, GSD | 1 | 6 | frontmatter 필수 → ifeval frontmatter ×5가 L1 |
| SPARC(md) | 0 | 0 | 키별 대응(ifeval 1) + "인용 ⊆ 선언" 내부 일관성(SDD 6)이 학습에 들어옴 |

### 7.2 새 L2-먼 재료(카탈로그·학습에 없는 템플릿)를 얼마나 가져오는가 — 평가 쪽이나 템플릿 공급원으로 쓸 때

| 후보 | 새 템플릿 후보 | 내용 |
|---|---|---|
| GSD | 5~6 | 읽기 깊이 규칙(frontmatter만 읽기, 본문 재독 금지, S1 확장), Read/Grep 5회 연속이면 STOP(행동 비율 창), task마다 커밋 + conventional 메시지 형식(hook 강제 가능), SUMMARY 주장을 증거로 치지 않고 probe 재실행(기록 vs 재실행), Self-Check 덧붙임, `must_haves` frontmatter |
| SPARC(CLI) | 6 (11 §2) | revision 전달, idempotency key, 명령 옵션 형식, 서명된 증거, 산출물 내부 집합·키별 대응. md 재표현이면 뒤의 둘만 남아 2 |
| BMAD | 5 (11 §2) | 서브에이전트 창, 산출물 내부 일관성, 언어, 되돌리기, judge 축 |
| PRP | 약 3 | 라운드를 넘어 finding id 보존(carried), 마지막 줄 센티널 `VALIDATION: GREEN`, 자기 점수·커버리지 목표 금지(부정형 item_format), HTML 주석 frontmatter |
| Task Master | 약 3 | 의존성은 더 낮은 id만(내부 일관성), task 상태기계 pending → in-progress → done, subtask마다 커밋 |
| tile | 0~1 | 요구사항↔테스트 파일 인라인 링크(기록 vs 파일 존재, T-RF4 변형). 나머지는 기존 템플릿 |

GSD가 가장 많다. 특히 "다시 읽지 않는다·읽기만 계속하지 않는다" 계열은 어느 학습 workflow에도 없는 새 기술이다. SPARC는 CLI 형태일 때만 많다. 이 표는 조사 보고서 기준 추정이며 rules.yaml 인벤토리는 BMAD·SPARC에만 있다.

### 7.3 평가 workflow로 추가할 때의 L2-먼 (현재 학습 AOS/OSF/SKB 기준)

BMAD·SPARC는 rules.yaml의 layer_candidate(drop 제외)로 셌고, 나머지 넷은 조사 보고서로 추정했다.

| 평가로 추가 | L2-먼 항목 (code / judge) | 무엇이 L2-먼인가 | 비고 |
|---|---|---|---|
| BMAD | 18 / 23 (non-drop 196 중 41, 21%) | 산출물 내부 일관성 6, frontmatter 2, 쓰기 뒤 존재 확인 3, 서브에이전트 창 4, 언어 2, 키별 carried 1; judge 23은 리뷰 4레이어 내용 규칙 | judge 23은 리뷰 레이어를 단일 에이전트로 남길 때만 산다(11 §5). J축은 10 §2.5대로 따로 센다 |
| GSD | 약 12~16 / 있음 | frontmatter 약 5, 읽기 깊이·재독 금지 2~3, Read/Grep 5회 연속 STOP 1, task마다 커밋 + 메시지 형식 2~3, 요구사항 id 키별 대응 1~2, stub·TBD 차단 2 | 추정. rules.yaml을 만들면 BMAD와 순서가 바뀔 수 있다 |
| PRP | 약 6~8 | finding id 라운드 간 보존 2, 마지막 줄 센티널 1, 자기 점수·커버리지 목표 금지 2, 안정 plan ID 1, HTML 주석 frontmatter 1~3 | 절반이 교정 패스에 걸림 |
| SPARC(md) | 약 5 | 키별 대응 4, 컴포넌트 ↔ ownership 1:1 | CLI 형태면 11개가 전부 강제라 측정 0 |
| Task Master | 약 3~4 | 의존성은 더 낮은 id만, 상태기계, subtask마다 커밋 | 단계 문서가 없어 총 항목이 적음 |
| tile | 약 3 | frontmatter name/description/targets | 나머지는 L1 |

비교: ifeval 192 중 L2-먼 6(3%), SDD 242 중 6(2.5%). BMAD가 가장 많고 GSD가 다음이다. 둘 다 L1C도 1·2위인데, 평가용이면 L1C는 충돌 층 k로 쓰이므로 장점이다. 같은 workflow를 학습에도 넣으면 그 L2-먼이 다른 평가에서 L1으로 바뀌므로 평가용·학습용 후보는 겹치지 않게 고른다.

### 7.4 BMAD가 평가에 가져오는 L2-먼 템플릿 — 하나씩 (bmad_build_auto/porting/rules.yaml, drop 제외)

code 18 = 산출물 내부 일관성 6 + 서브에이전트 창 4 + 쓰기 뒤 존재 확인 3 + 언어 2 + frontmatter 2 + 키별 carried 1. judge 23은 리뷰·triage 내용 규칙 한 묶음.

| 템플릿 | 무엇을 재는가 | BMAD 규칙 (말로) | 왜 카탈로그·학습에 없나 | 포팅 뒤 |
|---|---|---|---|---|
| NEW-FM-internal ×6 (새) | 한 산출물 안의 두 부분이 서로 맞는가: 한 필드가 같은 문서의 다른 부분에서 계산되는 값과 같다 | spec이 1600 토큰을 넘으면 frontmatter warnings에 `oversized`가 있어야 함(D22); verdict가 false인 행은 route가 reject(G66); Triage Log의 `<total>`은 행 수이자 다섯 verdict 수의 합, 묶인 finding도 각자 행(G80); Auto Run Result의 patch/defer/reject 수·reject 이유가 Triage Log 행과 일치(H3); 후속 리뷰 권고 true/false는 "첫 패스: high patch 1개 이상 또는 medium patch 2개 이상"으로 계산(H4); frontmatter `followup_review_recommended`가 그 계산값과 같음(H5) | 학습의 모든 검사는 산출물 ↔ 트레이스/레포/다른 산출물 비교(T-RF·T-TR)거나 고정 골격(T-FM2)이다. 같은 문서의 두 부분을 대조하는 항목이 없다 | 6개 모두 keep(H4는 env: 첫 패스만). 전부 code로 측정 가능 |
| NEW-AW-subagent ×4 (새) | 위임 호출(서브에이전트 띄우기)이 창 안에서 요구·금지되고, 넘기는 인자가 정해져 있는가 | 리뷰 레이어마다 맥락 없는 서브에이전트를 지정 프롬프트로 띄운다(G11); 모든 레이어를 띄운 뒤에야 결과를 읽고 triage한다(G8); spec 경로는 edge-case 레이어에만, 그 레이어도 추적을 끝낸 뒤 읽고 다른 레이어는 spec을 보지 않는다(G4); intent 레이어에 넘기는 의도 원문은 step-01에서 받은 그대로다(G6) | 학습의 행동 창(S3)은 테스트 실행·편집 시점뿐이다. 위임 호출이 있는 학습 workflow가 없다 | 4개 모두 semantic(G7): 단일 에이전트면 레이어가 인라인 패스가 된다. 남는 건 순서(네 렌즈를 다 돌린 뒤 triage, edge-case 렌즈는 추적 뒤에 spec 읽기)와 "diff를 issue 원문과 대조". 서브에이전트가 없는 환경이면 창 자체는 사라지고 순서 규칙(T-OR1 변형)만 남는다 |
| NEW-WD-exists-after ×3 (카탈로그 후보, 항목 0) | 자기 산출물을 쓴 뒤 그것이 있는지(파싱되는지) 확인한다 | 구현 단계 전제: spec 파일이 비어 있지 않은 경로로 디스크에 있어야 한다(C30); 게이트에서 spec이 사라졌으면 blocked로 멈춘다(D25); deferred를 다 붙인 뒤 frontmatter 전체를 YAML로 파싱해 `deferred`가 기존+새 항목을 담은 하나의 리스트인지 확인한다(G87e) | 카탈로그에 후보로만 있고 어느 workflow에도 항목이 없다 | 셋 다 keep. C30·D25는 "쓴 직후 읽기/stat"으로 재며 거의 항상 통과(외부 행위자 없이는 못 깨짐). 실제 변별력은 G87e(파싱 확인 여부) |
| NEW-FM-language ×2 (새) | 산출물(또는 메시지)의 언어가 설정 언어와 같다 | 문서는 document_output_language(기본 English)로 쓴다(B1); 대화는 communication_language로 한다(B2) | 세 학습 workflow에 언어 규칙이 없다(grep English/language: 없음) | env(G10): 빌드 때 토큰을 English로 고정. 언어 판별로 측정 |
| T-FM5 frontmatter ×2 (카탈로그 L2F) | frontmatter 키 집합이 고정 | spec frontmatter 키는 title·type·created·status·review_loop_iteration·followup_review_recommended·context·warnings·deferred(B7); `deferred`는 하나뿐인 리스트로 없으면 빈 리스트 추가, 있으면 뒤에 붙이고 두 번째 `deferred:` 키를 만들지 않는다(G87a) | 학습 산출물에 frontmatter가 없다(templates.yaml 사유) | keep. ifeval frontmatter ×5와 같은 템플릿이므로 BMAD를 학습에도 넣으면 ifeval 쪽이 L1로 바뀐다(§7.1) |
| T-TR1b 키별 대응 ×1 (카탈로그 L2F) | 두 기록 사이의 키별 1:1 대응 | 루프백·재개 때 새 finding을 Triage Log의 기존 행과 위치·주장으로 맞춰, 같으면 verdict·route를 유지하고 증거 앞에 `carried`를 붙여 다시 쓰며 재검증·재patch하지 않는다(G58) | 학습의 cross_ref는 전부 집합 관계(⊆, =)다 | semantic(G8): 루프백이 살아남을 때만 |
| NEW-J-content ×23 (judge, J축) | 내용 적절성. 코드로 못 재고 LLM judge 질문으로 잰다 | spec 품질: AC는 가장 바깥 표면을 관찰(D16), 공백 없음(D18), 모순 없음(D19), task는 파일당 하나(D41), AC가 I/O Matrix와 중복 안 됨(D43), 목표가 여럿이면 `multiple-goals` 경고(C25). 리뷰 방법: 서브에이전트 보고가 아니라 diff로 판단(E16), edge-case 렌즈는 빠진 경로만 나열(G21), verification-gap 렌즈의 절차 6개 — 행동 바꾸는 부분만 고르기, 관찰 경계까지 1–3 hop 추적, 최소 회귀 지명, 그 회귀를 잡는 단언이 있는지, 인정되는 테스트, 보고하지 않는 것(G43–G48), intent 렌즈는 기술적으로만(G54). triage: gap finding은 사전 검증으로 받음(G59), 수정안이 아니라 문제의 실재를 판단(G61), low+침습적 수정은 reject(G67), 범위 밖은 의도가 배제할 때만(G68), spec 고치는 finding은 reject(G69), 같은 결함끼리만 묶음(G70), patch 조건 4개(G74), 되돌리기 전 KEEP 목록(G85a) | 내용 판단은 S1~S10에 없다(10 §2.5: J축 별도). 학습 workflow 셋은 judge 항목이 없다 | 리뷰 레이어를 단일 에이전트 인라인으로 남길 때만 산다(11 §5). judge 엔드포인트가 없으면 unavailable |

같은 종류지만 포팅에서 죽어 0이 되는 것: **NEW-WD-exists-before** (쓰기 전에 epic 컨텍스트 캐시가 유효한지 확인하고 유효하면 원본을 읽지 않음 C17; 같은 slug의 spec이 있으면 draft일 때만 재개, 아니면 `-2`를 붙임 C28 — rollout마다 빈 산출물 디렉터리라 발동 불가), **NEW-WD-revert** (intent_gap·bad_spec이면 코드 변경을 baseline으로 되돌림 G84b/G85b — 되돌린 트리는 실패한 과제라 포트는 시도를 남기고 gap만 기록). 11 §2의 "되돌리기"는 이것이다.

### 7.5 SPARC(md)를 평가로 추가할 때의 L2-먼 — 하나씩 (sparc_run/porting/rules.yaml, 14 §5의 md 재표현 기준)

md로 바꾸면 CLI 프로토콜 규칙(revision 전달 F1, idempotency key F2, 명령 형식 F4, Ed25519 서명 E4–E8, digest 참조 C9/D7, 서명·단계 조건 D8, 버전 간 키 고정 E3)은 비교할 대상이 없어 사라진다. 남는 L2-먼은 **키별 대응 4 + 산출물 내부 키별 대응 1 = 5**, 전부 code 측정.

가정하는 md 산출물: definition.md(REQ 표: id·문장·inScope·인수테스트 id 목록; TEST 표: id·설명·명령), specification.md(REQ별 coverage 표), architecture.md(components 표 + ownership 표), refinement.md(increment마다 REQ id 목록 + evidence 표: evidence id·REQ·TEST·명령·결과), completion.md(REQ별 trace 표: evidence id 목록).

| 항목 | 평가가 요구하는 것 (말로) | 왜 L2-먼인가 | 원 규칙 |
|---|---|---|---|
| REQ별 인수테스트 집합 일치 (T-TR1b) | specification의 coverage 표에서 in-scope REQ **하나하나**에 적힌 TEST 집합이 definition에서 그 REQ에 등록된 TEST 집합과 정확히 같다. 빠진 TEST도 등록 안 된 TEST도 없음 | 학습의 cross_ref는 전부 "A의 id 집합 ⊆/= B의 id 집합"(T-TR1). "키 k마다 A[k] = B[k]"는 보상도 노출도 없다 | D2 |
| REQ×TEST 증거 완전 커버 (T-TR1b) | in-scope REQ마다, 그 REQ에 등록된 **모든** TEST에 대해 그 TEST를 가리키는 pass evidence가 인용돼 있다. TEST 없는 evidence나 그 REQ에 등록되지 않은 TEST를 가리키는 evidence는 불인정 | 집합이 아니라 (REQ, TEST) 쌍 단위의 완전 대응. SPARC의 중심 gate. ifeval `plan_execution_tags`(계획 step ↔ 요구 id)와 같은 템플릿의 두 번째 실례 | D10 |
| evidence의 REQ와 인용처의 REQ 일치 (T-TR1b) | refinement에서 어떤 increment가 인용한 evidence는 그 increment의 REQ 목록에 있는 REQ를 가져야 하고, completion에서 trace 행이 인용한 evidence는 그 행의 REQ를 가져야 한다 | 참조를 따라간 뒤 양쪽 키가 같은지 보는 교차 일관성. 학습에 "참조 대상의 필드 = 참조하는 쪽의 필드" 항목이 없다 | D9 |
| evidence의 REQ→TEST 등록 관계 (T-TR1b) | evidence 표의 각 행에서 REQ는 in-scope로 등록된 것이고, TEST가 적혀 있으면 definition에서 **그 REQ**에 등록된 TEST다 | TEST가 등록돼 있는가(집합)가 아니라 그 REQ의 TEST인가(키별) | E2 |
| 컴포넌트 ↔ ownership 1:1 (NEW-S8-intra-keyed) | architecture 안에서 components 표의 모든 이름에 ownership 행이 **정확히 하나** 있고, ownership 행은 선언된 컴포넌트만 가리킨다 | 한 산출물 안의 두 표 사이 키별 1:1 대응. SDD의 NEW-FM-internal 6개와 같은 과(산출물 내부 일관성)이되 형태는 keyed | D5 |

L2-먼은 아니지만 함께 오는 L2-가까운(L2M) 둘: "REQ가 인용한 TEST id는 모두 TEST 표에 있다"(B4), "walkthrough가 인용한 invariant 문장은 모두 invariants 목록에 선언돼 있고 문자열이 같다"(D4) — 한 산출물 안의 두 섹션 사이 집합 관계로, T-TR1의 구조 확장이라 L2M.

md가 되면 사라지는 것: digest 세 값 일치(D7)는 "인용한 evidence id가 evidence 표에 있다"로 내려앉아 T-TR1(집합) L1이 되고, 서명 검증(D8/E6)과 버전 고정(E3)은 대상이 없다. 따라서 CLI 형태의 L2-먼 후보 11개(14 §5.1) → md 5개.

비고: 이 5개는 ifeval의 T-TR1b 1개, SDD의 NEW-FM-internal 6개와 템플릿이 겹친다. SPARC(md)를 **학습**에 넣으면 그 7개가 L1로 바뀌고(§7.1), **평가**에 넣으면 같은 L2-먼 템플릿을 세 번째 평가에서 다시 재는 셈이다.

### 7.6 BMAD를 평가로 쓸 때의 층별 분포 (rules.yaml drop 제외 196, 현재 학습 AOS/OSF/SKB 기준)

규칙(문장) 단위이지 구현된 항목 단위가 아니다. fate: keep 104, semantic 65, env 27.


템플릿 × 층 (규칙 수). 세로로 더하면 층 합계, 가로로 더하면 템플릿 합계.

| 기술 | 템플릿 | L1 | L1C | L2M | L2F | 계 | 측정 |
|---|---|---|---|---|---|---|---|
| S1 | T-RD1 | 1 |  |  |  | 1 | code |
| S1 | T-RD2 | 7 |  | 1 |  | 8 | code |
| S1 | T-RD3 | 3 |  |  |  | 3 | code |
| S1 | T-RD4 | 10 |  |  |  | 10 | code |
| S1 | T-RD5 | 4 |  |  |  | 4 | code |
| S2 | T-OR1 | 6 |  |  |  | 6 | code |
| S2 | T-OR2 | 8 | 5 |  |  | 13 | code |
| S3 | NEW-AW-subagent |  |  |  | 4 | 4 | code |
| S3 | T-AW1 | 2 |  |  |  | 2 | code |
| S3 | T-AW3 | 3 |  |  |  | 3 | code |
| S3 | T-AW5 | 2 |  |  |  | 2 | code |
| S4 | T-PR1 | 1 |  |  |  | 1 | code |
| S4 | T-PR5 |  | 1 |  |  | 1 | code |
| S4 | T-PR6 | 1 |  |  |  | 1 | code |
| S5 | NEW-WD-exists-after |  |  |  | 3 | 3 | code |
| S5 | T-WD3 | 2 |  |  |  | 2 | code |
| S5 | T-WD4 | 3 |  |  |  | 3 | code |
| S6 | T-RF1 | 6 |  |  |  | 6 | code |
| S6 | T-RF2 | 2 |  |  |  | 2 | code |
| S6 | T-RF3 |  |  | 1 |  | 1 | code |
| S6 | T-RF4 | 2 |  |  |  | 2 | code |
| S8 | T-TR1 | 2 | 1 |  |  | 3 | code/judge |
| S8 | T-TR1b |  |  |  | 1 | 1 | code |
| S8 | T-TR2 |  |  | 1 |  | 1 | code |
| S9 | T-SR2 |  |  | 2 |  | 2 | code |
| S10 | NEW-FM-internal |  |  |  | 6 | 6 | code |
| S10 | NEW-FM-language |  |  |  | 2 | 2 | code |
| S10 | T-FM1 | 5 |  |  |  | 5 | code |
| S10 | T-FM2 | 24 | 2 | 2 |  | 28 | code/judge |
| S10 | T-FM3 | 11 |  |  |  | 11 | code |
| S10 | T-FM4 | 2 |  |  |  | 2 | code |
| S10 | T-FM5 |  |  |  | 2 | 2 | code |
| S10 | T-FM6 | 9 |  |  |  | 9 | code/judge |
| S10 | T-FM7 | 1 |  |  |  | 1 | code |
| S10 | T-FM8 | 2 |  |  |  | 2 | code |
| J | NEW-J-content |  | 2 | 16 | 23 | 41 | judge |
| - | None |  |  |  |  | 2 | none |
| | **계** | **119** | **11** | **23** | **41** | **196** | |
| | code만 | 115 | 9 | 7 | 18 | 149 | |

층별 내용은 아래 표.

| 층 | 전체 | code | judge | 비율 | 템플릿 |
|---|---|---|---|---|---|
| L1 | 119 | 115 | 4 | 61% | T-FM2 24, T-FM3 11, T-RD4 10, T-FM6 9, T-OR2 8, T-RD2 7, T-OR1 6, T-RF1 6, T-FM1 5, T-RD5 4, T-RD3/WD4/AW3 각 3, T-RF4/WD3/AW1/FM4/AW5/TR1/FM8/RF2 각 2, T-RD1/FM7/PR1/PR6 각 1 |
| L1C | 11 | 9 | 2 | 6% | T-OR2 5 (HALT blocked: unclear intent C12, 미해결 질문 C23, intent gap D20/G84c, matrix ambiguity F7), T-FM2 2 (빈 섹션에 N/A·None 금지 D40; 리뷰어 출력에 severity 금지 G16), T-TR1 1 (I/O Matrix edge case를 단위 테스트하는 task D42), T-PR5 1 (patch 구현자는 편집 파일의 테스트만 F12), judge 2 (edge case 전수 G26, 의도 추론 금지 G72) |
| L2M | 23 | 7 | 16 | 12% | judge 내용 규칙 16; code: 링크·경로 상대 형식 B5/B6 (T-FM2), 사람과 상호작용 안 함 D1·HALT로만 턴 종료 H15 (T-SR2), READY 게이트에서 workflow.md 재독 D23 (T-RD2), spec Verification 명령 실행 F1 (T-TR2), 바뀐 파일 목록 = diff H2 (T-RF3) |
| L2F | 41 | 18 | 23 | 21% | judge 23; code: NEW-FM-internal 6, NEW-AW-subagent 4, NEW-WD-exists-after 3, NEW-FM-language 2, T-FM5 2, T-TR1b 1 (§7.4) |
| 템플릿 없음 | 2 | | | | C1 호출 프롬프트가 의도, D12 READY 자기 점검 (측정 없음) |
| 합계 | 196 | 149 | 45 | | |

code만 보면 149 중 L1 115 (77%), L1C 9 (6%), L2M 7 (5%), L2F 18 (12%). 비교: ifeval 192 항목 중 L1 168 (88%), L1C 5 (2.6%), L2M 13 (7%), L2F 6 (3%); SDD 242 중 L1 232 (96%), L1C 3, L2M 1, L2F 6 (2.5%). BMAD는 L1C가 2~4배, L2F가 4~8배 두텁다.

포팅 결정에 따라 움직이는 것:
- HALT를 "가정하고 계속"으로 바꾸면 L1C의 T-OR2 5개(C12/C23/D20/F7/G84c)와 judge G72가 사라지거나 L1이 되어 L1C 11 → 5. 반대로 HALT를 두면 D1·H15(T-SR2, L2M)는 L2M 그대로다.
- 테스트를 checks/로 돌리면 D42는 L1C가 아니라 L1(T-PR1 같은 방향)이 되고, 리뷰 레이어를 인라인 단일 에이전트로 남겨야 judge 45와 NEW-AW-subagent 4가 산다(11 §5).
- semantic 65·env 27은 뜻이 바뀌어 살아남는 규칙이라 구현 뒤 재분류가 필요하다.

### 7.7 서브에이전트 구조를 빼면 BMAD에 무엇이 남는가 (rules.yaml gap=G7 기준)

BMAD upstream의 분업: 오케스트레이터가 step-01(의도·VCS), step-02(조사·spec·READY 게이트 자체 점검), step-04의 triage·라우팅·루프백·HALT를 직접 한다. 서브에이전트는 step-03 구현자 1, step-04 리뷰 렌즈 4(Blind Hunter, Edge Case Hunter, Verification Gap, Intent Alignment), 그리고 선택적으로 epic 컨텍스트 컴파일·깊은 탐색·patch 재호출이다. upstream 자신은 서브에이전트를 못 띄우는 도구에서는 시작 직후 `blocked / no subagents`로 끝낸다(workflow.md I2, survey:12).

G7 태그 규칙 84개 중 38개는 이미 drop(서브에이전트 호출·핸드오프·커밋), 46개는 semantic/env로 살아 있다(stage 4에 42, stage 3에 4). 비-drop 196개를 넷으로 나누면:

| 구분 | 규칙 수 | 무엇 | 층 영향 |
|---|---|---|---|
| ① 서브에이전트와 무관 (upstream에서도 오케스트레이터 자신의 일) | 150 | stage 0·1·2·halt 전부(84), stage 3의 비-G7(15), stage 4의 triage·라우팅 쪽(51): Triage Log 형식·합계, verdict·route 열거값, 폭포식 처리, bad_spec 루프백·카운터·상한, intent_gap HALT, defer frontmatter, patch 뒤 Verification 재실행, status 전환, baseline·diff 생성 | L1C 10/11, L2F code 14/18, L2M code 7/7 전부 여기 |
| ② 독립성이 전제인 규칙 — 단일 에이전트면 껍데기만 남음 | 약 10 | 맥락 없는 서브에이전트로 띄움(G11), 모든 레이어를 띄운 뒤 triage(G8·G56), spec은 edge-case 렌즈에만·추적 뒤에 읽기(G4·G19·G34), 의도 원문 그대로 전달(G6), 치환된 프롬프트만 전달(G9), "보고가 아니라 diff로 판단"(E16), 리뷰어 출력에 severity 없음(G16: 맥락 없는 리뷰어는 등급을 못 매긴다는 이유), 행은 레이어 보고 순서(G79) | NEW-AW-subagent 4(L2F) 사실상 0; G16 L1C는 형식 규칙으로는 남지만 근거 소멸 |
| ③ 리뷰 렌즈 네 개의 절차·출력 형식 — 자기 리뷰 체크리스트로 바뀜 | 약 30 (judge 16, code 14) | Blind Hunter 하한 산식 N=min(⌊√kB⌋+1,10)·0건이면 재점검, Edge Case Hunter 6단계·diff hunk만·피호출자 선언 읽기·JSON 4필드, Deletion/Claims Check, Verification Gap 6단계·gap 블록·`No verification gaps found.`, Intent Alignment 보고 3부 | judge L2F 23·L2M 16은 그대로 셀 수 있으나 "저자가 자기 코드를 리뷰"가 됨. 출력이 부모에게 보내던 메시지라 측정하려면 파일로 써야 함 |
| ④ 분업 자체가 규칙인 것 — 단일 에이전트면 다른 규칙에 흡수 | 3 | patch 구현자는 편집 파일 테스트만, 전체 검증은 부모(F12 → F9에 흡수), 구현자가 구현 전 spec을 끝까지 읽음(E7 → 자기 spec 재독), 실패 수정 뒤 diff 재생성·재독(F3) | F12의 L1C(T-PR5) 소멸 → L1C 11 → 10. E7·F3은 no_reread 반대 진영(14 §1.3)에 남되 "의식적 재독"이 됨 |

따라서 "남는 것": 완전히 뜻이 남는 규칙 150 (77%), 체크리스트 형태로 남는 규칙 약 30, 껍데기 약 10, 흡수 3. 층별로는 L1C 11 → 10, L2F code 18 → 14 (judge 23은 자기 리뷰 조건부), L2M 변화 없음.

사용자 지적에 대한 답:
- **review**: 절반(triage·라우팅 51)은 upstream에서도 오케스트레이터가 직접 하므로 그대로 남는다. 다른 절반(렌즈 42)이 서브에이전트 몫이고, 그중 독립성 규칙 10개는 단일 에이전트에서 의미가 없다. 렌즈 절차 30개는 "다른 눈"이 아니라 "같은 눈의 체크리스트"가 된다.
- **자기가 쓴 산출물 확인**: step-02의 READY 게이트 자체 점검(D12, D24~D28)과 defer 뒤 frontmatter 파싱(G87e), spec 존재 확인(C30·D25)은 upstream에서도 저자 자신이 한다. 포트 때문에 자기 확인으로 바뀌는 것은 구현자의 spec 통독(E7)과 리뷰어의 diff·spec·테스트 읽기(G20·G34·G40)뿐이다.
- 평가용 비교에 미치는 영향: BMAD의 code L2F 18 → 14가 되면 GSD 추정 12~16과 비슷해진다. judge 23을 세려면 렌즈 출력을 파일로 남기는 포트 결정과 judge 엔드포인트가 필요하다.

> **2026-11-09 결정 반영.** §7.6·§7.7의 분포는 1b 추정 기준이다. 사용자 결정(서브에이전트 사용·의도 불명확 문장 삭제(2026-11-10; 처음의 "가정하고 진행"을 대체)·저장소 테스트 파일·루프와 재검증 유지·산출물 밖으로·judge 일단 미사용) 뒤의 분포는 `bmad_build_auto/porting/03-decisions.md`와 `if/scripts/bmad/decided_layers.py`: code 152 = L1 116 / L1C 4 / L2M 7 / L2F 25.
