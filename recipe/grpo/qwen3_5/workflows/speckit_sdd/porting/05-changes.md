# Changes: speckit_sdd  (upstream github/spec-kit@0443760, SDD 최소 체인 specify → plan → tasks → implement ⇄ converge)

## 구성 (`recipe/grpo/qwen3_5/workflows/speckit_sdd/`)

| 파일 | 출처 | 내용 |
|---|---|---|
| `docs/core-workflow.md` | 직접 작성 | 진입 문서: 5단계 순서, implement ⇄ converge 최대 2회, 입력 정의, 단계별로 고칠 수 있는 파일, "아무도 답하지 않음" 규칙 (97줄) |
| `docs/stages/01-specify.md` ~ `05-converge.md` | spec-kit 원문을 변환 | 단계별 절차와 산출물 양식 (명령 원문 5개 1,236줄 → 675줄) |
| `sandbox/specify/templates/{spec,plan,tasks,checklist}-template.md` | spec-kit 원문을 변환 | 에이전트가 복사해 채우는 산출물 양식. spec은 거의 원문 그대로(C-1), tasks는 MVP·병렬 예시 삭제, phase 범위 조건과 빈 phase의 `No tasks — <이유>` 규칙 추가, 테스트 task 예시 경로를 저장소 밖 `checks/`로 변경(TDD 문장은 원문 유지) (541줄 → 494줄) |
| `sandbox/specify/scripts/bash/*.sh` (4개) | spec-kit 원문 그대로 복사 | 경로 계산, 템플릿 복사, 선행 파일 확인. 바이트 단위로 원본과 같고 실행 권한 유지 |
| `sandbox/specify/memory/constitution.md` | spec-kit 원문 그대로 복사 | 빈 constitution 템플릿. 비어 있으면 검사 건너뜀(C-4) |
| `build.py` | 직접 작성 | 원문 → stages·템플릿 변환기, 스크립트 복사 확인. 편집마다 태그(env / semantic / loop)와 gap ID. `--list`, `--check` |
| `setup.sh` | 직접 작성 | 색상 없는 jq(`jq -M`) wrapper 설치 (G7-8) |
| `instruction.md` | 직접 작성 | "첫 행동으로 `/speckit-sdd/core-workflow.md` 열기, 문서는 저장소 밖 루트 경로". 다른 워크플로우와 다른 문장 |
| `system-prompt.j2` | SDK 기본 프롬프트 복사 | 절차 섹션만 새로 작성, 나머지 15개 섹션은 SDK 기본과 동일 |
| `__init__.py`, `LICENSE-spec-kit` | — | SPEC 등록 정보(문서 `/speckit-sdd`, `.specify` → `/tmp/speckit-sdd/.specify`, 산출물 경로, setup 스크립트), MIT 고지 |
| `porting/01~06-*.md` | 단계별 기록 | 조사·gap·결정·변경·smoke |

원문: `templates/commands/{specify,plan,tasks,implement,converge}.md`(stage 문서 5개, 1,236줄 → 675줄),
`templates/{spec,plan,tasks,checklist}-template.md`(sandbox 템플릿 4개), `scripts/bash/{common,check-prerequisites,setup-plan,setup-tasks}.sh`와
`templates/constitution-template.md`(무변경 복사). 편집 목록은 `python -m recipe.grpo.qwen3_5.workflows.speckit_sdd.build --list`
(stage 문서 87건: env 52 · semantic 30 · loop 5, 템플릿 24건: env 12 · semantic 12).

배치(03-decisions.md "G7-2 (b) feasibility" 그대로):
- `docs/` → `/speckit-sdd`: `core-workflow.md`(신규), `stages/01-specify.md` ~ `05-converge.md`.
- `sandbox/specify/` → `/tmp/speckit-sdd/.specify` (`WorkflowSpec.sandbox_files`): `scripts/bash/*.sh`(원문 바이트 동일, +x), `templates/*.md`(변환), `memory/constitution.md`(원문 placeholder 그대로). 이로써 `/tmp/speckit-sdd`가 Spec Kit project root.
- `output_dirs=("/tmp/speckit-sdd/specs", "/tmp/speckit-sdd/.specify/feature.json")`: 스크립트·템플릿은 수집 대상 아님.
- 요청된 배치에서 바꾼 점 없음.

## 수정한 내용

### 각 단계 수행 방식 변화

| Before (upstream spec-kit) | After (rllm) |
|---|---|
| 1. **사람**이 `specify init`으로 프로젝트에 `.specify/`(스크립트·템플릿·constitution)를 설치합니다.<br>2. **사람**이 agent 앱 채팅창에 `/speckit-specify <기능 설명>`을 입력합니다.<br>3. **agent 앱**이 그 명령에 연결된 SKILL.md를 불러오고, 입력 텍스트를 `$ARGUMENTS` 자리에 넣어 지침으로 씁니다.<br>4. agent(LLM)가 지침을 읽고 작업합니다.<br>  • 터미널로 스크립트를 실행합니다: `.specify/scripts/bash/setup-plan.sh --json` 등<br>  • 스크립트 출력(JSON)에서 feature 폴더와 템플릿 경로를 받습니다.<br>  • 산출물(spec.md, plan.md, tasks.md …)과 코드 수정은 **agent가 직접 파일로 씁니다**.<br>  • 모호하면 사용자에게 묻고 답을 기다립니다.<br>5. 단계가 끝나면 agent가 결과를 보고하고 멈춥니다.<br>6. **사람**이 결과를 보고 다음 명령(`/speckit-plan`, `/speckit-tasks`, `/speckit-implement`, `/speckit-converge`)을 입력합니다. implement ⇄ converge는 Converged가 나올 때까지 사람이 반복합니다. | 1. 처음 받는 task 메시지가 사람의 입력을 대신합니다(instruction + SWE task 본문(issue)). `.specify/`는 harness가 `/tmp/speckit-sdd/.specify`에 미리 넣어 둡니다.<br>2. agent가 `core-workflow.md`를 먼저 읽고, 단계마다 해당 stage 문서(`/speckit-sdd/stages/*.md`)를 읽습니다.<br>3. agent(LLM)가 지침을 읽고 작업합니다.<br>  • 터미널로 **upstream 스크립트를 그대로** 실행합니다: `/tmp/speckit-sdd/.specify/scripts/bash/setup-plan.sh --json` 등<br>  • JSON에서 경로를 받습니다(feature 폴더는 `/tmp/speckit-sdd/specs/001-issue`로 고정).<br>  • 산출물과 코드 수정은 **agent가 직접 파일로 씁니다**.<br>  • 모호하면 묻지 않고, 가장 타당한 해석을 산출물에 기록한 뒤 진행합니다.<br>4. 단계가 끝나면 agent가 멈추지 않고 **다음 단계 문서를 열어 계속합니다**. implement → converge는 최대 2회이고, `converged`이면 종료합니다. |

### 수정 사항

| # | 범주 | 내용 |
|---|---|---|
| 1 | **사람 피드백이 필요한 부분 삭제** | 질문·확인·중단 분기를 지우고 "가장 타당한 해석을 산출물에 기록한 뒤 진행"으로 교체. 해당 분기: specify 질문(최대 3개), specify ERROR 종료, plan의 불명확 사항 ERROR, implement 체크리스트 STOP 질문(확인만 하고 proceed), task 실패 시 중단·다음 행동 제안 |
| 2 | **보고 후 멈춤 → 다음 단계로 진행** | 각 단계 끝의 "결과 보고, 다음 명령 안내"를 "다음 단계 문서를 열어 계속"으로 교체. converge·implement의 채팅 출력은 파일(`convergence.md`)과 `[X]` 표시로 대체. 도구 호출 없는 메시지 금지 |
| 3 | **이름·경로 고정** | feature 폴더 `001-issue`로 고정(이름·번호 생성 삭제). spec-kit 프로젝트 루트는 저장소 밖 `/tmp/speckit-sdd`, 문서는 `/speckit-sdd`. constitution·템플릿은 upstream 렌더링 후 경로(`.specify/memory`, `.specify/templates`) 그대로. 워크플로우 이름 `speckit_sdd` |
| 4 | **실행 환경 구성** | `.specify/`를 sandbox에 업로드(upstream 스크립트 4개는 원본 그대로, 템플릿은 변환본, constitution은 빈 템플릿). setup 스크립트로 색상 없는 jq(`jq -M`) 설치(TTY에서 JSON 색상 코드 방지). 산출물 수집(`output_dirs`) |
| 5 | **agent 앱 전용 요소 삭제** | frontmatter(handoffs·scripts), `$ARGUMENTS`·`{SCRIPT}`·슬래시 명령 참조, extension hook 블록(약 345줄), git branch·커밋 지시, 범위 밖 명령(clarify·checklist·analyze) 언급 |
| 6 | **SWE task 조건에 맞춤** | 테스트 task는 user story마다 생성하되 파일은 저장소 밖 `FEATURE_DIR/checks/`의 검증 스크립트(저장소 테스트 파일 작성·수정 금지, 예시 경로 `tests/…` → `checks/…`). implement는 원문 TDD 순서(검증 스크립트 실행·실패 확인 → 구현 → 재실행·통과 확인) 유지, 구현 전후 관련 기존 테스트 실행 한 문장 추가, 완료 검증은 검증 스크립트와 관련 기존 테스트 통과(coverage 요구 삭제). ignore 파일 수정 단계 삭제. Setup·Foundational·Polish는 이번 변경에 필요한 것만(의존성 설치·리팩터·문서 금지). plan 기술 스택은 저장소에서 읽음. 온라인 조사·링크 열기 금지 |
| 7 | **절차 구조 변경** | implement ⇄ converge 최대 2회(`converged`면 종료, 2회차는 미완료 task만). plan Phase 1 산출물은 항상 작성: data-model·quickstart는 해당 없으면 본문 한 줄 `N/A — <이유>`, contracts는 plan.md의 Documentation 트리에 계약 파일 목록 또는 `contracts/  # N/A — <이유>`. tasks.md의 Setup·Foundational·Polish 제목은 항상 유지, 빈 phase는 한 줄 `No tasks — <이유>`. MVP 후 멈춤·병렬 예시 섹션 삭제. 단계별로 고칠 수 있는 파일 지정(이후 단계는 tasks.md의 `[X]`와 Convergence phase 추가만 허용) |
| 8 | **환경 사실 명시** | task 메시지가 곧 테스트 요청이며, 그 안의 "tests are already taken care of"는 agent가 볼 수 없는 채점용 테스트를 뜻함. 스크립트 오류가 슬래시 명령을 안내하면 해당 단계를 먼저 수행. tasks.md 체크박스가 진행 기록(TaskTracker 도구는 보조). constitution이 빈 템플릿이면 검사 건너뜀 |
| 9 | **harness·데이터셋 설정** | 진입 문서·instruction·system prompt 절차 섹션 새로 작성(첫 행동은 진입 문서 열기, `/speckit-sdd`는 저장소 밖 루트 경로). 데이터셋 `swegym293_aidlc`, instruction 위치 `prefix` |
| 10 | **범위·방식 결정** | 절차는 최소 체인(specify → plan → tasks → implement ⇄ converge)만, clarify·checklist·analyze·constitution 명령 제외. 스크립트는 빼지 않고 원본 그대로 실행(다양성). feature 개발 task 전용 |
| 11 | **원문 유지** | 고치지 않기로 결정한 것: tasks·implement의 TDD 문장("Write these tests FIRST, ensure they FAIL", "Follow TDD approach", "Tests before code"), spec의 비즈니스 관점 지침·체크리스트, 빈 constitution 템플릿, converge의 엄격한 판정, specify의 자체 검증 3회, SDK의 "ask the user" 문구(비교 가능성), upstream 스크립트 |

**적용 위치** (범주와 별개)
- **단계 문서 편집**: `build.py`가 upstream `templates/commands/*.md`를 변환할 때 태그 편집으로 적용(87건). 범주 1·2·5·6·7·8
- **템플릿 편집**: `build.py`가 `templates/*-template.md`를 sandbox용으로 변환할 때 적용(24건). 범주 5·6·7(MVP·병렬 예시 삭제, phase 범위와 빈 phase 표기, Phase 1 N/A 표기, 테스트 요청 문장과 테스트 task 예시 경로, plan Source Code 안내)
- **환경 파일**: `sandbox/specify/`(스크립트 원본·템플릿·constitution), `setup.sh`, `__init__.py`. 범주 3·4
- **새로 작성**: 진입 문서, instruction, system prompt 절차 섹션, converge 보고서 양식. 범주 2·3·7·9의 규칙 대부분

## 변경

**1. user argument를 issue 본문으로 대체** (01-specify.md, 02-plan.md ~ 05-converge.md, spec-template.md) — G1-1, G1-3
- 원문은 사람이 slash command 뒤에 입력한 텍스트(`$ARGUMENTS`, `{ARGS}`)로 feature 설명을 받는 구조. specify의 `## User Input`을 `## Input`으로 바꿔 task 메시지의 `<issue_description>` 본문이 feature 설명이라고 명시.
- 나머지 4개 stage의 `## User Input` 섹션 삭제(issue는 task 메시지에 계속 남음). tasks의 "Context for task generation: {ARGS}" 삭제.
- plan: 사람이 정하던 tech stack 입력 없음. Technical Context는 저장소(build 파일, CI 설정, 설치 환경)에서 채우도록 명시(G1-3).
- spec-template `Input: User description: "$ARGUMENTS"` → `the issue in the task message`.

**2. 보고 후 종료를 다음 stage 문서로 연결** (01-specify.md ~ 05-converge.md, plan-template.md, tasks-template.md, checklist-template.md) — G2-1, G2-2, G2-4, D-5
- 원문은 각 명령 끝에 사용자에게 Completion Report를 출력하고 사람이 다음 명령을 입력하는 구조. 01~04의 `## Completion Report`를 `## Next Stage`(보고 없이 다음 stage 문서를 열고 진행)로 대체, Done When의 "Completion reported to user" 항목도 같은 내용으로 변경.
- tasks 보고 섹션 중 "tasks.md는 바로 실행 가능해야 함"과 checklist 형식 확인은 규칙이라 유지, 집계 출력과 Suggested MVP scope는 삭제.
- `__SPECKIT_COMMAND_*__` → stage 문서 경로, "STOP … 명령 실행 안내"·"suggest running X first" → "X stage를 먼저 수행"(G2-2). 템플릿의 command 표기도 stage로 변경.
- stage 중간 텍스트 출력 제거(G2-4): specify 실패 항목은 checklist Notes에 기록, implement checklist 표 "Display" 삭제·진행 상황은 `[X]` 표시로만, converge 결과는 회차 보고서 파일에 기록.
- implement는 별도 회차 보고서 없음. `[X]` 표시와 converge 보고서가 기록(D-5).

**3. 범위 밖 명령 참조 삭제** (01-specify.md, 04-implement.md, checklist-template.md) — G2-3, G3-2
- 원문은 선택 단계인 clarify·checklist·analyze를 가리키는 문장을 포함하는 구조. 이번 port 범위(최소 체인) 밖이므로 해당 이름 삭제.
- specify: "checklist template 구조 사용" → "아래 구조 사용"(구조가 본문에 있음), "clarify 또는 plan 전" → "plan stage 전", "별도 명령" 문구 삭제.
- implement: `requirements.md`는 "specify stage가 관리", custom checklist(reviewer 소유) 설명 삭제.
- checklist-template: 생성 명령 note 삭제, 나머지 command 표기를 stage로 변경(파일 자체는 upstream post-init 상태대로 탑재, 어느 문서도 직접 가리키지 않음).

**4. core-workflow 신규 작성** (core-workflow.md, instruction.md, system-prompt.j2, \_\_init\_\_.py) — G3-1, G3-2, G5-4, G5-5, G10-1, G10-4, G10-5
- 원문에는 다섯 명령을 잇는 agent용 문서가 없고 사람이 순서대로 입력·검토하는 구조(engine `workflow.yml`도 converge 미포함).
- 내용: 위치 표(`/speckit-sdd`, `/testbed`, `/tmp/speckit-sdd`, FEATURE_DIR, 검증 스크립트·임시 파일용 checks), stage 표(열 문서, 실행 스크립트, 산출물), 실행 순서와 회차, 입력 정의, 응답자 없음, 파일별 작성 주체(G5-4), 저장소 규칙(G5-5), 스크립트 오류 대응표(G7-3).
- 파일별 작성 주체: spec·checklist는 specify 이후, plan·research는 plan 이후 재작성 금지. tasks.md는 implement의 `[X]`와 converge의 Convergence phase 추가로만 변경(G5-4).
- `FEATURE_DIR/checks/`는 테스트 task의 검증 스크립트와 임시 파일 위치, `/testbed`에는 워크플로우 파일을 남기지 않음(G5-5 rev2). 저장소 규칙에 "저장소 테스트 파일 추가·수정 없음, 검증 스크립트는 구현 전 실패·구현 후 통과 확인, 관련 기존 테스트는 구현 전후 실행" 명시.
- tasks.md checkbox가 진행 기록이고 TaskTracker는 선택 보조 수단(G10-5, 04-implement.md에도 명시).
- instruction.md와 system-prompt.j2 `<PROBLEM_SOLVING_WORKFLOW>`: `/speckit-sdd/core-workflow.md`를 첫 행동으로 열 것, `/speckit-sdd`가 filesystem root에 있고 저장소(`/testbed`) 밖이라는 점 명시(G10-4). 나머지 system prompt 섹션은 SDK 기본값 그대로(speckit_bug와 바이트 동일).
- `__init__.py`에서 진입 문서 등록(`entry_doc="core-workflow.md"`, `container_dir="/speckit-sdd"`).

**5. 질문·중단 분기 삭제** (01-specify.md, 02-plan.md, 04-implement.md, checklist-template.md, core-workflow.md, system-prompt.j2) — G1-2, G4-1~G4-5, G4-7 — **semantic 포함**
- 원문은 판단이 필요한 지점에서 사람에게 묻거나 ERROR로 멈추는 구조. rllm에서는 tool call 없는 응답이 곧 실행 종료이므로 분기 변경.
- specify: "No feature description"·"Cannot determine user scenarios" ERROR 종료 삭제, issue를 저장소가 충족해야 할 요구사항으로 명시(G1-2).
- specify: 남은 `[NEEDS CLARIFICATION]`은 Q1~Q3 질문 표와 대기 대신 가장 타당한 답을 spec에 반영하고 `## Assumptions`에 기록, 최대 3개 규칙은 유지(G4-1).
- specify: 3회 자체 검증 유지, "warn user" → checklist Notes에 기록 후 계속(G4-3, env).
- plan: unknown은 저장소 근거로 해소, 근거가 없으면 가장 타당한 해석을 research.md(Decision/Rationale/Alternatives)에 기록, Key rules의 "ERROR on … unresolved clarifications" 삭제(G4-2).
- implement: checklist 검사는 읽기 전용으로 유지, 미체크 항목이 있으면 원문의 "proceed" 분기 선택, 질문·대기·중단 문구 삭제. checklist-template의 "as a gate" 삭제(G4-4).
- implement: 실패 task는 미체크로 두고 의존하지 않는 task 계속, 진행 불가 시 converge로 이동("Halt execution", "Suggest next steps" 대체)(G4-5).
- workflow.yml의 review gate 없음(G4-7, env, 문서 변경 없음).

**6. 경로·이름 고정, 산출물 저장소 밖으로 이동** (01-specify.md ~ 05-converge.md, spec/plan/tasks-template.md, core-workflow.md, \_\_init\_\_.py) — G5-1, G5-2, G5-3, G7-4, D-4
- 원문은 project root(=저장소) 아래 `specs/<NNN>-<short-name>/`을 만들고 이름·번호를 생성하는 구조(`init-options.json`, timestamp 옵션 포함). 저장소 안 산출물은 patch 혼입·`git clean` 삭제 위험.
- feature dir `/tmp/speckit-sdd/specs/001-issue` 고정, short name 생성·번호 규칙·init-options·timestamp·deprecated 경고 삭제(G5-2). `create-new-feature.sh`는 미탑재.
- specify가 `/tmp/speckit-sdd/.specify/feature.json`에 `{"feature_directory": "specs/001-issue"}` 기록, 이후 stage의 스크립트가 이 값으로 feature dir을 찾음.
- pre-render 경로 변환(G5-3): `/memory/constitution.md` → `/tmp/speckit-sdd/.specify/memory/constitution.md`, `/contracts/` → `FEATURE_DIR/contracts/`, spec template은 resolution stack 대신 `/tmp/speckit-sdd/.specify/templates/spec-template.md` 복사.
- git branch 생성(hook) 문구 삭제, 템플릿의 Branch 필드 `001-issue`, tasks-template의 "Commit after each task" 삭제(G7-4).
- 템플릿의 `/specs/[###-feature-name]/` → `/tmp/speckit-sdd/specs/001-issue/`.

**7. upstream 스크립트를 sandbox에 탑재해 agent가 실행** (sandbox/specify/, 02-plan.md ~ 05-converge.md, core-workflow.md, \_\_init\_\_.py, build.py) — G7-2(b), G7-3, G7-5, D-3
- 원문은 renderer가 `{SCRIPT}`를 `.specify/scripts/bash/<x>.sh …`로 바꾸고 agent가 project root에서 실행하는 구조. 이 port는 스크립트를 바꾸지 않고 그대로 실행하는 유일한 port.
- `common.sh`, `check-prerequisites.sh`, `setup-plan.sh`, `setup-tasks.sh`를 원문 바이트 그대로 +x로 탑재(`--check`가 내용과 실행 비트 확인). 범위 내 명령이 호출하지 않는 `resolve-template.sh`, `create-new-feature.sh`는 미탑재.
- `{SCRIPT}` → 절대 경로(`/tmp/speckit-sdd/.specify/scripts/bash/<x>.sh --json …`), "from repo root" → "작업 디렉터리 무관, 스크립트가 자기 위치로 project root를 찾음". 환경 변수 불필요.
- 스크립트 오류 안내는 slash command 이름(`Run /speckit.plan first`)을 출력하지만 스크립트는 수정하지 않고, 각 stage 문서와 core-workflow.md의 대응표에서 "해당 stage를 먼저 수행 후 재실행"으로 해석(G7-3).
- 템플릿 4개는 build.py가 변환해 탑재: plan-template은 `setup-plan.sh`가 복사하고 tasks-template은 `setup-tasks.sh`가 내용을 JSON으로 반환하므로 agent가 받는 텍스트는 여기서 변경. tasks-template frontmatter 삭제(G7-5). frontmatter 제거와 renderer 치환은 build.py가 수행, 잔여 문구는 `forbidden`으로 검사.

**8. hook 섹션 삭제** (01-specify.md ~ 05-converge.md) — G7-1
- 원문 각 명령 앞뒤의 extension hook 검사(`.specify/extensions.yml`)는 해당 파일을 싣지 않아 "skip silently"만 남는 구조이므로 삭제.
- `## Pre-Execution Checks` 5개, `## Mandatory Post-Execution Hooks` 4개, converge의 `### 9. Check for extension hooks` 단계(`##` 섹션이 아니라 별도 절단), Done When의 hook 항목 삭제.

**9. constitution placeholder 탑재, plan에 미작성 template 규칙 추가** (sandbox/specify/memory/constitution.md, 02-plan.md) — G7-6 — **semantic**
- 원문 `specify init` 후 상태는 `[PRINCIPLE_1_NAME]` 같은 placeholder만 있는 constitution. converge만 "미작성 template이면 constitution 검사 생략" 규칙이 있고 plan에는 없는 구조.
- `constitution-template.md`를 그대로 `memory/constitution.md`로 탑재(바이트 동일).
- plan의 Constitution Check: 미작성 template이면 원칙이 없고 주석은 예시일 뿐이므로 "skipped — template" 기록 후 gate 평가 없음. 그 외 경우의 원문 "Evaluate gates (ERROR if violations unjustified)"는 그대로 둠(실제로는 도달 불가).
- converge의 원래 생략 규칙은 유지.

**10. implement ⇄ converge 반복 추가 (최대 2회)** (04-implement.md, 05-converge.md, core-workflow.md) — G8-1, G8-2, G8-3 — **loop**
- 원문은 사람이 "Converged"가 나올 때까지 implement와 converge를 반복하는 구조(상한 없음), converge 결과는 채팅 출력이고 `converged`면 파일 기록도 없음.
- converge step 6의 in-session 요약을 회차 보고서 파일로 변경: 1회차 `convergence.md`, 2회차 `convergence-2.md`, findings 표 + summary metrics + `- **Round**:` / `- **Outcome**: converged | tasks_appended` 필드. `converged`면 "✅ Converged …" 줄을 보고서에 기록. "유일한 쓰기" 제약에 보고서 추가.
- step 8 handoff → 회차 규칙: `converged`면 종료, 1회차 `tasks_appended`면 implement 2회차 후 converge 2회차, 2회차 후에는 결과와 무관하게 종료(G8-1).
- implement 2회차는 미체크 task(보통 새 Convergence phase)만 수행, `[X]` task와 setup 재수행 금지(G8-2).
- converge의 엄격도(`unrequested`도 task 생성)는 원문 유지, 상한으로 제한(G8-3).

**11. 테스트는 저장소 밖 검증 스크립트로 작성, 원문 TDD 순서 유지** (03-tasks.md, 04-implement.md, tasks-template.md, core-workflow.md) — G9-1, G9-1 (rev2), G5-5 (rev2) — **semantic**
- 원문은 "요청 시에만 테스트" 규칙과 TDD(테스트 먼저 작성, 실패 확인 후 구현) 구조. 테스트 파일 경로 예시는 저장소의 `tests/contract/`, `tests/integration/`, `tests/unit/`.
- tasks: 원문 "Tests are OPTIONAL … only if requested" 유지 후 "이 task 메시지가 그 요청"이라는 문장 추가. task 메시지의 "tests are already taken care of"는 agent가 볼 수 없는 채점용 테스트를 뜻한다고 명시. user story마다 `### Tests for User Story N`에 테스트 task 생성, 그 파일은 `/tmp/speckit-sdd/specs/001-issue/checks/`의 검증 스크립트이고 저장소 테스트 파일이 아님. tasks-template의 Tests 줄에도 같은 내용 추가.
- tasks-template 테스트 task 예시 7줄(US1~3의 contract·integration, Polish의 unit)의 경로 `tests/…` → `/tmp/speckit-sdd/specs/001-issue/checks/{contract,integration,unit}/…`. "Write these tests FIRST, ensure they FAIL", "Tests (if included) MUST be written and FAIL", "Verify tests fail before implementing"은 원문 그대로(rev 1의 baseline 문장 교체를 되돌림).
- implement: "Follow TDD approach: Execute test tasks before …" 원문 유지 후 "테스트 task = `FEATURE_DIR/checks/` 검증 스크립트: 작성·실행해 실패 확인 → 구현 → 재실행해 통과 확인" 추가. "Tests before code" 원문 유지 후 "`checks/`에 작성, 저장소 테스트 파일은 작성·수정 안 함" 및 "구현 전 관련 기존 저장소 테스트 실행·baseline 기록, 구현 후 재실행" 한 문장 추가.
- implement 완료 검증: "Validate that tests pass" 유지, 대상은 `checks/` 검증 스크립트와 변경 관련 기존 저장소 테스트, "coverage meets requirements" 삭제. Done When의 "test coverage"도 같은 대상으로 변경.
- 근거: 새 동작의 fail-to-pass 테스트는 설계상 agent에게 숨겨져 있어 agent 자신의 스크립트가 유일한 확인 수단. 저장소 밖이므로 채점용 test patch와 충돌(`git apply`는 같은 새 파일이 있으면 실패)하거나 patch를 오염시키지 않음.
- 그대로 둔 부분: tasks의 "If tests requested" 조건문들(이제 요청이 있으므로 발동), tasks-template Path Conventions의 "`src/`, `tests/` at repository root"와 plan-template Source Code 구조 예시의 `tests/`(저장소 구성 서술이며 파일 작성 지시 아님).
- `forbidden`: rev 1의 "Follow TDD"·"ensure they FAIL"·"MUST be written and FAIL"·"Verify tests fail"·"check script"·"checks/` pass" 제거, 저장소 테스트 경로 `tests/contract/`·`tests/integration/`·`tests/unit/` 추가(stage 문서·템플릿 모두).

**12. ignore 파일 설정 단계 삭제** (04-implement.md, core-workflow.md) — G9-2 — **semantic**
- 원문 implement step 4는 `.gitignore`·`.dockerignore` 등을 매번 생성·보완하는 필수 단계. issue와 무관한 저장소 파일 변경이 되고, `.gitignore` 패턴 추가는 patch 수집에도 영향.
- step 4 전체(약 43줄)를 "저장소 ignore 파일은 변경 대상이 아니므로 생성·수정 금지"로 대체.

**13. Setup·Foundational·Polish 범위를 이번 변경으로 한정** (03-tasks.md, 04-implement.md, plan-template.md, tasks-template.md) — G9-3, G9-3 (rev) — **semantic**
- 원문은 새 프로젝트 기준(초기화, 의존성 설치, lint 설정, 문서·리팩터링·성능·보안 작업) 단계 구성.
- tasks: Setup은 기존 저장소에서 이번 변경에 필요한 것만(초기화·의존성 설치·도구 설정 없음), Foundational은 이번 변경의 story 공통 선행 작업, Polish는 이번 변경에 필요한 정리만. 세 phase 제목은 비어도 유지하고 한 줄 `No tasks — <이유>` 기록(rev, tasks-template 주석에도 명시). Phase Structure 목록의 Setup 설명도 동일하게 변경.
- implement: "Setup first" → 초기화된 저장소, 의존성 설치 없음. "Polish and validation" → Polish task 후 변경 모듈의 기존 테스트 실행.
- plan-template Source Code 주석에 "기존 저장소면 이번 변경이 수정·추가하는 실제 파일만 기재" 추가. tasks-template 샘플 task는 테스트 task 경로(11번) 외 무변경.

**14. plan Phase 1 파일 항상 작성, 해당 없으면 N/A 기록** (02-plan.md, plan-template.md, core-workflow.md) — G9-4 (rev, rev2) — **semantic**
- 원문은 매번 data-model.md, contracts/, quickstart.md를 생성하는 구조.
- data-model.md, quickstart.md는 매번 작성, 해당 내용이 없으면 본문 한 줄 `N/A — <이유>`(step 3, Phase 1 섹션의 **Always written**).
- contracts/는 plan.md의 `### Documentation (this feature)` 트리(원문의 산출물 목록)에 기록: 작성한 계약 파일을 `contracts/` 아래에 나열하거나, 없으면 `contracts/  # N/A — <이유>`로 적고 파일은 만들지 않음. 원문의 "purely internal이면 skip"도 이 N/A 줄로 기록. plan-template 문서 트리와 core-workflow.md stage 표에 같은 규칙 표기.

**15. MVP 우선 전략·병렬 실행 예시 삭제** (03-tasks.md, 04-implement.md, tasks-template.md) — G4-6, G7-7 — **semantic**
- 원문 tasks-template은 US1만 구현 후 "STOP and VALIDATE"·배포하는 MVP 전략, 팀/여러 agent의 병렬 실행 예시를 포함하는 구조. 한 번의 session에서 중간 종료나 부분 구현으로 이어질 수 있음.
- tasks-template `## Implementation Strategy`, `## Parallel Example: User Story 1` 섹션 삭제, Notes의 "Stop at any checkpoint" → "각 checkpoint 검증 후 계속". tasks 문서의 "Implementation strategy section", "parallel execution examples" 항목 삭제. `[P]` 표시는 유지.
- implement: 각 phase 검증 후 계속, 모든 phase를 한 번에 완료하도록 명시.
- 그대로 둔 부분: phase 제목의 "🎯 MVP" 표기, checkpoint 문장들(정지 지시가 아닌 상태 서술), spec-template의 MVP 언급.

**16. 외부 접근 금지** (01-specify.md, 02-plan.md, core-workflow.md) — G6-1 — **semantic**
- 원문 plan Phase 0은 research agent 파견과 "best practices" 조사를 지시하는 구조(sub-agent·온라인 조회 전제). 온라인 조회는 정답 PR 유출 경로.
- research는 agent가 직접 저장소와 설치 환경을 읽는 것으로 변경, 온라인 조회 금지. issue 링크는 열지 않고 필요 시 `[UNVERIFIED — not fetched]`로 기록(specify Input, plan Phase 0, core-workflow.md). 패키지 설치 금지는 core-workflow.md에 명시.

**원문 그대로 둔 부분**: spec 작성 규칙의 제품·비즈니스 관점(WHAT/WHY, 비즈니스 이해관계자 대상, 기술 비종속 success criteria, checklist 항목 — G1-4, smoke에서 checklist 통과 여부와 issue의 API 이름이 plan.md까지 전달되는지 확인 필요), converge의 판정 절차(intent inventory, gap type, severity, append 규칙), tasks의 checklist 형식, 스크립트 4개와 constitution.

**engine 확장** (workflows/\_port.py, tests/test_port.py): `Section(level=3)`(converge의 `### 9.` 단계 절단), `Copy`(바이트 동일 복사 + 실행 비트, `--check` 대상). 기존 `##` 분할 동작은 그대로라 speckit_bug·openspec_ff 재빌드 결과 무변경.

**17. 색상 없는 jq 설치 (G7-8)** (setup.sh, \_\_init\_\_.py) — stage 4 발견, user 2026-10-14 결정 (c)
- agent terminal은 PTY(`TERM=xterm-256color`, task·agent image 모두 tmux 없음)라 jq 1.6이 스크립트 JSON 출력에 ANSI 색 코드를 붙이는 구조. jq 1.6은 `NO_COLOR`도 무시.
- `setup_script`로 `/usr/local/bin/jq`에 `jq -M` wrapper 설치. PATH상 `/usr/bin/jq`보다 앞. upstream 스크립트와 stage 문서는 무변경.
- MONAI image에서 `script -qec` 아래 일반 JSON 출력, 재실행 시에도 동일 결과 확인.

**18. smoke 2에서 안 지켜진 규칙의 위치 조정** (03-tasks.md, 04-implement.md, tasks-template.md, plan-template.md, 02-plan.md, core-workflow.md) — G9-6, G9-7 (G9-5 되돌림) — **semantic** (규칙 내용은 그대로, 위치·형식만 변경)
- G9-5: smoke 2 집계 오류(Polish 제목은 실제로 7/7 유지)에 근거한 수정이었으므로 되돌림(user 2026-10-15). 원문 그대로.
- G9-6: plan 템플릿 Documentation 트리의 contracts 줄을 빈칸 양식 `<REPLACE in plan.md: one line per contract file you wrote, or N/A — <reason> and no file>`으로 변경. plan 문서에 "복사된 템플릿의 이 줄을 plan.md에서 바꿀 것" 명시.
- G9-7: implement 실행 규칙 맨 앞에 "user story마다 코드 수정 전에 `checks/` 검증 스크립트 작성·실행해 실패 확인, 그다음 구현, 다시 실행해 통과 확인" 배치(원문 TDD 순서 그대로, 위치만 앞으로). 진입 문서 단계 표의 implement 행에 같은 순서 명시, `/tmp/test_x.py`처럼 `checks/` 밖에 쓰는 스크립트는 규칙 위반으로 명시.

**원문 없이 새로 쓴 문서**: `docs/core-workflow.md`, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션, stage 문서의 `## Input`(specify)·`## Next Stage`(01~04)·converge step 8 회차 규칙.
