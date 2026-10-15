# speckit_sdd: Spec Kit 명세 주도 개발(SDD) 워크플로우 파이프라인 안내

SWE task(issue 하나를 받아 저장소 코드를 고치는 과제)를 GitHub Spec Kit의 명세 주도 개발(Spec-Driven Development, SDD) 절차로 풀게 하는 rllm 워크플로우임.
이 문서는 파이프라인이 어떻게 구성되고 돌아가는지, rollout이 끝나면 무엇이 남는지를 정리함.
채점 방법은 다루지 않음.

## 1. 한눈에 보기

- 원본: [github/spec-kit](https://github.com/github/spec-kit), `specify-cli` 1.1.4.dev0 (commit `0443760`, 2026-10-09), MIT 라이선스.
  핵심 SDD 명령 5개(`templates/commands/{specify,plan,tasks,implement,converge}.md`)와 템플릿·스크립트를 씀.
- Spec Kit은 원래 사람이 agent 앱(Claude Code 등) 채팅창에 명령을 하나씩 입력하며 쓰는 도구임.
  - 사람이 먼저 `specify init`으로 프로젝트에 `.specify/`(스크립트, 템플릿, constitution)를 설치함.
  - 이어서 `/speckit-specify <기능 설명>` → `/speckit-plan <기술 스택>` → `/speckit-tasks` → `/speckit-implement` → `/speckit-converge`를 입력함.
  - 명령마다 agent가 따를 지침 문서가 있음. agent는 지침에 따라 `.specify/scripts/bash/*.sh`를 실행해 경로를 JSON으로 받고, 산출물과 코드는 직접 씀.
  - 명령이 끝날 때마다 agent가 결과를 보고하고 멈춤. 사람이 검토한 뒤 다음 명령을 입력함.
  - implement ⇄ converge는 converge가 "Converged"를 낼 때까지 사람이 반복함. 원본에는 반복 상한이 없음.
- 이 워크플로우는 같은 절차를 사람 없이 한 세션 안에서 끝내도록 바꾼 것임.
  - 명령별 지침 문서를 sandbox 안의 단계 문서로 바꾸고, agent가 순서대로 직접 엶.
  - 원본 스크립트 4개를 바이트 단위로 그대로 sandbox에 넣고 agent가 원본처럼 실행함(같은 원본을 옮긴 speckit_bug는 스크립트 없이 문서만 씀).
  - 사람이 하던 단계 연결·질문 답변·승인은 진입 문서의 규칙으로 대체함.
  - implement ⇄ converge 반복은 최대 2회로 제한함.
- 절차는 **specify → plan → tasks → implement ⇄ converge**.
  원본 quickstart의 짧은 경로(constitution → specify → plan → tasks → implement → converge)에서 constitution 명령을 뺀 형태임.
  선택 단계인 clarify, checklist, analyze는 넣지 않음. 셋 다 사람과의 문답이나 검토용 출력이 본업이기 때문임.
- **기능 개발 task 전용**임.
  - spec 작성 규칙(사용자 가치·비즈니스 관점, 기술 비종속 성공 기준)을 원문 그대로 두었기 때문임.
  - 버그 수정 task는 같은 원본의 bug 확장을 옮긴 `speckit_bug` 워크플로우가 맡음.

## 2. sandbox 구성

agent가 시작하기 전에 harness가 sandbox를 아래처럼 준비함.

| 경로 | 내용 | 누가 만드나 |
|---|---|---|
| `/testbed` | 고칠 저장소 (SWE-Gym task 이미지에 들어 있음) | task 이미지 |
| `/speckit-sdd/` | agent가 읽는 지침 문서: `core-workflow.md`, `stages/01-specify.md` ~ `05-converge.md` (6개) | harness 업로드 |
| `/tmp/speckit-sdd/.specify/` | Spec Kit 설치 상태: `scripts/bash/` 4개, `templates/` 4개, `memory/constitution.md` | harness 업로드 |
| `/tmp/speckit-sdd/.specify/feature.json` | feature 폴더 위치 기록 | agent (specify 단계) |
| `/tmp/speckit-sdd/specs/001-issue/` | feature 폴더(`FEATURE_DIR`). 모든 산출물이 여기 생김 | agent (specify 단계, `mkdir -p`) |
| `/tmp/speckit-sdd/specs/001-issue/checks/` | 검증 스크립트와 임시 파일 | agent |
| `/usr/local/bin/jq` | 색상 없는 jq wrapper | 준비 스크립트 |

- `/tmp/speckit-sdd`가 Spec Kit 프로젝트 루트(project root)임.
  - 스크립트는 현재 위치에서 위로 올라가며 `.specify/`를 찾고, 없으면 자기 파일 위치 기준으로 루트를 정함.
  - `/testbed` 위에는 `.specify/`가 없으므로, agent가 어느 디렉터리에서 실행해도 루트는 `/tmp/speckit-sdd`로 잡힘. 환경 변수는 쓰지 않음.
- 원본은 산출물을 저장소 안 `specs/<번호>-<이름>/`에 씀.
  저장소 안에 두면 patch에 섞이거나 agent의 `git clean`에 지워질 수 있어 저장소 밖으로 옮김.
- feature 폴더 이름은 `001-issue`로 고정함. 원본의 이름·번호 생성 규칙과 이를 담당하는 `create-new-feature.sh`는 쓰지 않음.

harness의 준비 순서는 아래와 같음.

1. `/speckit-sdd`를 비우고 지침 문서 업로드. `.md` 파일이 6개인지 세어 다르면 rollout 중단.
2. system prompt 기록.
3. `/tmp/speckit-sdd/.specify`를 지우고 통째로 업로드(tar 전송이라 점으로 시작하는 폴더 이름과 실행 권한이 유지됨).
4. 준비 스크립트(`setup.sh`)를 root로 실행. 종료 코드가 0이 아니면 rollout 중단.
5. 시작 표시 파일 기록. 이 파일의 시각이 "agent가 만든 파일"을 가르는 기준이고, 내용은 patch의 기준 commit임(7절).

준비 스크립트가 하는 일은 색상 없는 jq 설치 하나뿐임.

- agent의 터미널은 PTY(대화형 터미널)라서 task 이미지의 jq 1.6이 스크립트의 JSON 출력에 ANSI 색 코드를 붙임. jq 1.6은 `NO_COLOR`도 무시함.
- 원본 환경(agent 앱의 비대화형 셸)에서는 일반 JSON이 나오므로, `/usr/local/bin/jq`에 `exec <실제 jq> -M "$@"` wrapper를 써서 PATH상 `/usr/bin/jq`보다 앞에 둠.
- jq가 없으면 아무것도 하지 않음(스크립트가 jq 없이 동작하는 대체 경로를 가짐).
- 이미 wrapper가 있으면(재사용 sandbox) PATH의 다음 jq를 찾아 다시 씀. 여러 번 실행해도 결과가 같음.
- 스크립트와 단계 문서는 이 문제 때문에 고치지 않음.

### `.specify/`에 들어 있는 것과 원본 대비 차이

| 경로 | 원본 대비 |
|---|---|
| `scripts/bash/common.sh`, `check-prerequisites.sh`, `setup-plan.sh`, `setup-tasks.sh` | 바이트 동일, 실행 권한 유지. 범위 내 명령이 부르지 않는 `resolve-template.sh`, `create-new-feature.sh`는 없음 |
| `templates/spec-template.md` | 거의 원문. 이름·입력 표기만 바꿈: Branch 필드 `001-issue`, Input 줄 → "the issue in the task message" |
| `templates/plan-template.md` | 경로를 `/tmp/speckit-sdd/specs/001-issue/`로, 산출물 트리에 "항상 작성, 해당 없으면 `N/A — <이유>`" 표기, contracts 줄을 빈칸 양식으로 |
| `templates/tasks-template.md` | MVP 우선 전략·병렬 실행 예시 섹션 삭제, 테스트 task 예시 경로 `tests/…` → `checks/…`, 빈 phase의 `No tasks — <이유>` 규칙 추가 (252줄 → 207줄) |
| `templates/checklist-template.md` | 생성 명령 안내 삭제, 명령 표기를 단계 이름으로. 원본 설치 상태대로 넣었을 뿐 어느 단계 문서도 이 파일을 쓰게 하지 않음 |
| `memory/constitution.md` | 원본 `constitution-template.md` 그대로. `specify init` 직후 상태처럼 `[PRINCIPLE_1_NAME]` 같은 빈칸만 있음 |

- constitution은 프로젝트마다 사람이 한 번 정하는 비협상 원칙 문서임. 이 sandbox에는 정한 사람이 없으므로 빈 템플릿 상태를 그대로 둠.
- 원본 `specify init`이 만드는 `init-options.json`, `extensions.yml`(확장 hook 등록), `integration.json`, `workflows/` 정의는 넣지 않음.
- 스크립트·템플릿·constitution은 산출물 수집 대상이 아님(7절). 대신 agent가 실행 중에 고치면 `stray_files`에 나타남.

## 3. agent가 받는 입력

- **system prompt**: openhands-sdk 기본 프롬프트에서 절차 섹션(`<PROBLEM_SOLVING_WORKFLOW>`)만 이 워크플로우용으로 바꾼 것.
  - 요지: "평소 풀이 방식 대신 Spec Kit SDD 체인으로 푼다. 첫 행동으로 `/speckit-sdd/core-workflow.md`를 연다(`/testbed` 안이 아니라 루트에 있음). 단계마다 단계 문서를 먼저 열고, 문서가 시키면 Spec Kit 스크립트를 실행해 그 출력 경로를 쓴다. 아무도 답하지 않으니 직접 정하고 기록하며, 도구 호출 없이 턴을 끝내지 않고, 체인이 끝났을 때만 `finish`를 부른다."
  - 나머지 섹션(도구 사용 규칙 등)은 SDK 기본 그대로임. 그 안의 "사용자에게 묻기" 류 문구도 다른 워크플로우와 비교할 수 있게 그대로 둠.
- **사용자 메시지 1개**: 앞에 워크플로우 안내(`instruction.md`), 뒤에 SWE-Gym task 본문.
  - 안내 요지: "Spec Kit SDD 체인(specify, plan, tasks, implement, converge)으로 푼다. 저장소를 보기 전에 첫 행동으로 `/speckit-sdd/core-workflow.md`를 연다. `/speckit-sdd`는 저장소 밖 루트에 있고 `/testbed` 아래에서는 찾을 수 없다."
  - 경로 문장은 speckit_bug smoke에서 10개 중 3개가 문서를 `/testbed` 아래에서 찾다 포기한 결과를 반영한 것임.
  - task 본문은 SWE-Gym 기본 프롬프트에서 자체 6단계 절차를 뺀 버전(`swegym293_aidlc` 데이터셋)을 씀. 절차가 두 개면 agent가 워크플로우를 무시하는 경향이 있었기 때문임.
  - issue는 `<issue_description>` 태그 안에 있음.
- **도구**: openhands-sdk의 터미널(`terminal`), 파일 편집기(`file_editor`), task tracker 세 가지와 SDK 기본 `think`, `finish`. Spec Kit 스크립트는 별도 도구가 아니라 터미널로 실행하는 명령임.
- **step 예산**: 150 (설정에 따라 다름). 대화 압축(condenser)은 쓰지 않음.

## 4. 진행 흐름

```
specify ──► plan ──► tasks ──► implement ──► converge ──► finish
(명세)       (설계)    (작업 분해)  (구현)          (점검)
                                   ▲               │
                                   └─ tasks_appended (1회차만) ─┘
```

agent는 진입 문서 `/speckit-sdd/core-workflow.md`를 읽고, 단계마다 해당 단계 문서를 열어 따름.
각 단계 문서 끝의 `## Next Stage`가 "보고하지 말고 다음 단계 문서를 열어 계속"으로 되어 있어 사람 없이 이어짐.
스크립트는 모두 `/tmp/speckit-sdd/.specify/scripts/bash/`에 있고 `--json`으로 실행함.

| 단계 | 실행 스크립트 | 하는 일 | 남기는 것 (`FEATURE_DIR` 기준) |
|---|---|---|---|
| specify | 없음 (폴더 생성·템플릿 복사·feature.json 기록을 문서 지시대로 직접) | issue를 기능 명세로 정리, 품질 체크리스트로 자체 검증(최대 3회) | `spec.md`, `checklists/requirements.md`, `/tmp/speckit-sdd/.specify/feature.json` |
| plan | `setup-plan.sh` (plan 템플릿을 `plan.md`로 복사) | 저장소에서 기술 맥락 파악, 미정 사항 조사, 설계 산출물 작성 | `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`(있을 때만) |
| tasks | `setup-tasks.sh` (tasks 템플릿 내용을 JSON으로 반환) | user story별 phase로 작업 목록 작성 | `tasks.md` |
| implement | `check-prerequisites.sh --require-tasks --include-tasks` | story마다 검증 스크립트 작성·실패 확인 → 코드 수정 → 재실행·통과 확인, 완료 task에 `[X]` | `/testbed` 코드 변경, `checks/*`, `tasks.md`의 `[X]` |
| converge | `check-prerequisites.sh --require-spec --require-tasks --include-tasks` | spec·plan·tasks와 현재 코드를 대조해 남은 차이를 찾음 | `convergence.md`(2회차 `convergence-2.md`), 필요하면 `tasks.md` 끝에 `## Phase N: Convergence` 추가 |

단계 사이 규칙은 아래와 같음.

- specify, plan, tasks는 순서대로 1회씩 함.
- implement → converge는 최대 2회차까지 감.
  - 1회차: implement가 `tasks.md` 전체를 수행하고 converge가 `convergence.md`를 씀.
  - 보고서의 **Outcome**이 `converged`이면 종료.
  - `tasks_appended`이면 2회차: implement는 미체크 task(보통 새 Convergence phase)만 수행하고 `[X]` task와 setup은 다시 하지 않음. 이어 converge가 `convergence-2.md`를 씀.
  - 2회차 뒤에는 결과와 무관하게 종료. 남은 일은 `convergence-2.md`와 미체크 task로 남음.
- 원본 converge의 엄격도(요청에 없던 코드도 `unrequested`로 task를 만듦)는 그대로이고, 2회차 상한이 그 반복을 끊음.
- implement에서 실패한 task는 미체크로 두고, 그 task에 의존하지 않는 task를 계속함. 더 진행할 수 없으면 converge로 넘어감.
- 스크립트가 "Run /speckit.plan first" 같은 원본 안내와 함께 실패하면, 안내가 가리키는 단계를 먼저 수행한 뒤 스크립트를 다시 실행함.
  - 스크립트는 선행 파일 존재만 확인함: `setup-tasks.sh`는 `plan.md`·`spec.md`, `check-prerequisites.sh`는 항상 `plan.md`, 옵션에 따라 `spec.md`·`tasks.md`.
- 단계마다 고칠 수 있는 파일이 정해져 있음.

| `FEATURE_DIR` 안 파일 | 쓰는 단계 | 이후 변경 |
|---|---|---|
| `spec.md`, `checklists/requirements.md` | specify | 없음 |
| `plan.md`, `research.md`, Phase 1 파일 | plan | 없음 |
| `tasks.md` | tasks | implement의 `[X]` 표시, converge의 Convergence phase 추가만 |
| `convergence.md`, `convergence-2.md` | converge, 회차마다 1개 | 없음 |
| `checks/` | implement(검증 스크립트), 모든 단계(임시 파일) | 필요할 때 |

- 마지막에 `finish` 도구를 호출해 세션 종료.

## 5. 산출물 형식

모든 산출물은 `/tmp/speckit-sdd/specs/001-issue/` 아래에 생김(feature.json만 예외).
원본처럼 보관(archive) 단계가 없으므로 rollout이 어떻게 끝났든 위치는 같음.

| 파일 | 형식 요약 |
|---|---|
| `/tmp/speckit-sdd/.specify/feature.json` | `{"feature_directory": "specs/001-issue"}`. 이후 단계의 스크립트가 이 값으로 feature 폴더를 찾음 |
| `spec.md` | 머리: `# Feature Specification: <이름>`, Feature Branch `001-issue`, Created, Status, Input. 본문: `## User Scenarios & Testing` (`### User Story N - <제목> (Priority: PN)`, Why this priority, Independent Test, Acceptance Scenarios = `**Given** … **When** … **Then** …`, `### Edge Cases`), `## Requirements` (`**FR-001**: System MUST …`, Key Entities), `## Success Criteria` (`**SC-001**: …`), `## Assumptions` |
| `checklists/requirements.md` | Content Quality 4개, Requirement Completeness 8개, Feature Readiness 4개, 총 16개 `- [ ]` 항목과 `## Notes`. 통과한 항목을 agent가 체크함 |
| `plan.md` | `## Summary`, `## Technical Context`(언어, 의존성, 테스트, 플랫폼 등), `## Constitution Check`, `## Project Structure`(`### Documentation (this feature)` 트리, `### Source Code`), `## Complexity Tracking` |
| `research.md` | 미정 사항마다 Decision / Rationale / Alternatives considered |
| `data-model.md`, `quickstart.md` | 항상 작성. 해당 내용이 없으면 본문 전체가 한 줄 `N/A — <이유>` |
| `contracts/` | 외부 인터페이스 계약 파일. 없으면 파일을 만들지 않고, plan.md 문서 트리의 contracts 줄을 `contracts/  # N/A — <이유>`로 바꿈. 있으면 그 줄 아래에 파일을 나열 |
| `tasks.md` | 아래 설명 참고 |
| `convergence.md`, `convergence-2.md` | 아래 설명 참고 |
| `checks/*` | user story별 검증 스크립트와 임시 파일. 저장소 테스트 대신 여기에 씀 |

**tasks.md**

- task 한 줄 형식: `- [ ] T001 [P] [US1] <설명과 파일 경로>`.
  - `[P]`는 병렬 가능 표시, `[USn]`은 user story phase의 task에만 붙음.
  - 완료하면 implement가 `- [X]`로 바꿈.
- phase 구성: `## Phase 1: Setup` → `## Phase 2: Foundational` → story마다 `## Phase N: User Story k - <제목> (Priority: Pk)` → 마지막 `## Phase N: Polish & Cross-Cutting Concerns` → `## Dependencies & Execution Order`.
  - Setup, Foundational, Polish 제목은 비어도 남기고, 빈 phase에는 한 줄 `No tasks — <이유>`를 씀.
  - story phase마다 `### Tests for User Story k`(검증 스크립트 task, 파일 경로는 `checks/` 아래)와 `### Implementation for User Story k`가 있음. 템플릿 원문 제목에는 뒤에 `(OPTIONAL - only if tests requested) ⚠️`가 붙어 있어 agent가 그대로 두기도 함.
- converge가 task를 추가하면 맨 끝에 `## Phase N: Convergence`가 붙음.
  - 줄 형식: `- [ ] T042 <설명> per <근거 ID> (<gap type>)`. 근거 ID는 `FR-003`, `SC-002`, `US1/AC2`, `plan: <결정>` 등.
  - 기존 task는 번호·순서·내용 모두 그대로임.

**convergence.md / convergence-2.md** (원본은 채팅 출력이던 것을 파일로 바꾼 것)

```
## Convergence Findings

- **Round**: 1 | 2
- **Outcome**: converged | tasks_appended

| ID | Gap Type | Severity | Source | Evidence | Remaining Work |

**Summary metrics:** 확인한 요구사항·인수 기준 수, plan 결정 수, constitution 원칙 수(또는 "skipped — template"),
gap type별·severity별 finding 수
```

- `converged`이면 마지막 줄이 `✅ Converged — the implementation satisfies the spec, plan, and tasks.`이고 `tasks.md`는 한 글자도 바뀌지 않음.

산출물을 읽는 데 필요한 개념은 다음과 같음.

- **user story / FR / SC**: spec의 사용 시나리오(P1이 가장 중요), 기능 요구사항(`FR-###`), 측정 가능한 성공 기준(`SC-###`). tasks와 converge가 이 ID로 근거를 가리킴.
- **gap type**: converge가 찾은 차이의 종류. `missing`(코드에 없음), `partial`(일부만 충족), `contradicts`(의도와 충돌), `unrequested`(요청에 없던 코드).
- **severity**: CRITICAL / HIGH / MEDIUM / LOW. constitution의 MUST 위반이 가장 높음.
- **constitution 검사**: constitution이 빈 템플릿이면 원칙이 없는 것으로 보고 plan의 Constitution Check에 `skipped — template`을 쓰고 통과 여부를 따지지 않음. converge도 원본 규칙대로 검사를 건너뜀.

형식을 검사하는 도구는 없음.

- 스크립트는 선행 파일이 있는지만 확인하고 내용은 읽지 않음.
- converge의 판정은 agent 자신의 점검 결과이며 테스트 실행을 요구하지 않음.
- 형식이 지켜졌는지는 산출물 내용으로만 알 수 있음.

## 6. agent에게 주어진 규칙

진입 문서, 단계 문서, 템플릿, 스크립트 안내에 걸쳐 agent에게 주어지는 규칙을 모으면 아래와 같음.

- **사람이 없음**: 질문하거나 보고하려고 멈추지 않음. 도구 호출 없이 메시지만 내면 그 즉시 세션이 끝나기 때문임(openhands-sdk 동작).
  - 모호한 점은 가장 타당한 해석을 골라 해당 산출물에 기록함: spec의 `## Assumptions`, `research.md`의 결정, 체크리스트의 Notes.
  - specify의 `[NEEDS CLARIFICATION]` 표시는 최대 3개 규칙을 유지하되, 질문 대신 가장 타당한 답을 spec에 넣고 Assumptions에 기록함.
  - 체크리스트 자체 검증은 최대 3회. 그래도 남는 문제는 Notes에 기록하고 계속함.
  - implement는 체크리스트를 읽기만 하고, 미체크 항목이 있어도 원본의 "진행" 분기를 따름.
  - 단계의 끝은 요약이 아니라 다음 단계 문서를 여는 것임.
- **입력**: issue 본문이 유일한 입력. 본문 속 링크를 열지 않고(필요하면 `[UNVERIFIED — not fetched]`로 표기), 온라인에서 찾아보지 않음.
  - 원본 plan의 조사 단계(research agent 파견, best practice 조사)는 agent가 저장소와 설치 환경을 직접 읽는 것으로 바뀜.
- **환경**: 패키지 설치 금지. 기술 스택은 사람이 알려 주지 않으므로 저장소의 build 파일, CI 설정, 설치된 환경에서 읽음.
- **저장소**: implement 단계만 `/testbed`를 수정함.
  - 테스트 파일은 추가·수정하지 않음.
  - `.gitignore`, `.dockerignore` 등 ignore 파일은 만들거나 고치지 않음(원본 implement는 매번 만들거나 보완함).
  - spec 사본, 메모, 요약, 임시 스크립트를 저장소에 남기지 않음. `checks/` 밖(`/tmp/test_x.py`, `/testbed/repro.py` 등)에 쓴 스크립트는 규칙 위반이라고 명시됨.
- **테스트**: task 메시지가 곧 테스트 요청임.
  - task 본문의 "테스트는 이미 준비되어 있다"는 문장은 agent가 볼 수 없는 채점용 테스트를 뜻한다고 안내함.
  - user story마다 테스트 task를 만들고, 그 파일은 `checks/` 아래 검증 스크립트임.
  - 원본 TDD 순서를 지킴: 코드 수정 전에 검증 스크립트를 작성·실행해 실패를 확인하고, 구현한 뒤 다시 실행해 통과를 확인함.
  - 변경과 관련된 기존 저장소 테스트를 구현 전(기준선)과 후에 실행함.
  - 원본의 coverage 충족 요구는 없앰.
- **범위**: Setup은 기존 저장소에서 이번 변경에 필요한 것만(초기화·의존성 설치·도구 설정 없음), Polish는 이번 변경에 필요한 정리만(저장소 전체 문서·리팩터링·성능·보안 작업 없음).
  원본의 MVP 우선 전략(첫 story만 구현하고 멈춤)은 없앴고, implement는 모든 phase를 한 번에 끝냄.
- **spec 관점**: 원문 그대로 "무엇을, 왜"에 집중하고 구현 방법(기술 스택, API, 코드 구조)은 쓰지 않으며 비기술 이해관계자 대상으로 씀.
  issue의 API 이름 같은 기술 세부는 plan 단계가 issue에서 다시 가져옴.
- **이름과 경로**: feature 폴더 `001-issue`, Branch 필드 `001-issue`, git branch 생성과 commit 없음. `.specify/` 아래 스크립트·템플릿·constitution은 고치지 않음.
- **진행 기록**: `tasks.md`의 체크박스가 implement 진행 기록임. task tracker 도구는 보조로만 씀.
- **converge**: 쓸 수 있는 것은 회차 보고서와 `tasks.md` 끝의 Convergence phase 추가뿐임.
  spec·plan·코드·기존 task는 고치지 않고, 체크된 task도 "완료 표시는 증거가 아니다"는 원칙으로 다시 확인함.
- **단계 순서·반복·파일별 작성 주체**: 4절 참고.

## 7. rollout이 끝나면 남는 것

rollout이 끝나면 sandbox는 사라지고, 아래 두 가지가 episode JSON에 남음.
episode 최상위에는 `is_correct`, `termination_reason`(`env_done`, `max_turns_exceeded` 등), `trajectories`, `artifacts`가 있음.

**대화 기록** (`trajectories[0].steps[]`)

- step 하나가 LLM 호출 하나임.
- `model_output`에 agent가 낸 것이 들어 있음: `content`(텍스트), `reasoning`(thinking을 켠 경우), `tool_calls`(`name`과 `arguments`), `finish_reason`.
  - 터미널 명령은 `name: terminal`, `arguments.command`. Spec Kit 스크립트 실행도 여기에 `/tmp/speckit-sdd/.specify/scripts/bash/<x>.sh --json …`로 남음.
  - 파일 작성은 `name: file_editor`, `arguments.command`가 `create` / `str_replace` / `view` 등, `arguments.path`. 문서를 여는 것도 대개 `view`임.
  - 셸 heredoc(`cat > 파일 << 'EOF'`)으로 산출물을 쓰는 경우도 흔함.
  - 없는 도구 이름(`str_replace`, `command` 등)이 그대로 `name`에 기록되는 경우가 있음(smoke 3에서 10개 중 5개 rollout, 1회씩). 결과는 검증 오류 메시지임.
- `chat_completions`는 그 step의 응답까지 포함한 대화 전체임. 도구 실행 결과는 다음 step의 `chat_completions` 안 `role: tool` 메시지(`content: [{type: text, text}]`, `tool_call_id`, `name`)에 있음.
  - 터미널 결과 끝에 종료 코드가 붙음(`[Command finished with exit code N]`). 결과 앞에 터미널 제어 문자(`\u001b[?2004l` 등)가 섞여 있음.
- 도구 호출 형식이 깨진 응답으로 끝난 rollout은 마지막 step의 `tool_calls`가 비어 있고, `content`에 `<tool_call>…</tool_call>` 텍스트가 그대로 있으며, `termination_reason`은 `env_done`임.

**수집 산출물** (`artifacts`): agent가 끝난 직후, 채점 테스트가 저장소를 건드리기 전에 harness가 읽어 둠.

| 키 | 내용 |
|---|---|
| `workflow_outputs` | `/tmp/speckit-sdd/specs` 아래 모든 파일과 `/tmp/speckit-sdd/.specify/feature.json`의 경로 → 내용. 스크립트·템플릿·constitution은 제외 |
| `workflow_outputs_skipped` | 총 1MB를 넘어 내용을 담지 못한 파일의 경로 → 크기 |
| `patch`, `patch_base`, `patch_bytes`, `patch_truncated` | 시작 시점 대비 저장소 변경(`git diff --binary`, 새 파일 포함, `.gitignore` 반영). 채점 테스트가 평가한 그 변경. 1MB 초과분은 잘림. git 기록을 숨긴 실행에서는 `patch_base`가 대체 commit임 |
| `patch_error` | patch가 없을 때 그 이유 |
| `stray_files` | agent 실행 중 `/tmp`(수집 대상 경로 제외)나 `/speckit-sdd`에 생기거나 바뀐 파일의 경로 → 크기. 최대 500개, 넘으면 `stray_files_truncated` |
| `workflow` | 워크플로우 이름과 버전 해시(sha256: 문서·instruction·system prompt·`.specify/` 파일·준비 스크립트 기준) |

- 지금 reward는 숨겨진 테스트 통과 여부(`is_correct`)뿐임. 이 워크플로우에는 준수율 채점기가 아직 없음.
  trajectory의 `signals`에는 테스트 결과 세부(`f2p_success`, `f2p_total`, `p2p_success`, `p2p_total`, `test_patch_applied`)가 있음.
- 산출물 위치는 끝난 방식과 무관하게 항상 `/tmp/speckit-sdd/specs/001-issue/` 아래임. 차이는 무엇이 있느냐뿐임.
  - specify 단계를 시작하지 않았으면 `workflow_outputs`가 빈 dict임.
  - step 한도로 끊긴 rollout도 수집은 되며, 그때까지 쓴 파일만 있음.
- `workflow_outputs`에는 agent가 `checks/`에서 pytest를 돌리면 생기는 `.pytest_cache/`, `__pycache__/*.pyc`도 들어감. 바이너리는 UTF-8로 깨진 문자열이 됨.
- `.specify/` 아래 템플릿이나 스크립트를 agent가 고치면 수집 대상이 아니라 `stray_files`에 이름만 남음.
- `stray_files`에는 저장소 자체 테스트가 `/tmp`에 만드는 임시 폴더도 잡힘(smoke 3에서 2개 rollout이 500개 상한에 도달). pytest의 `/tmp/pytest-of-*`, `__pycache__`, 파일 편집기 undo 기록은 제외됨.

## 8. smoke에서 관찰된 실제 동작

기능 요청 SWE-Gym task 5개 × 1회, Qwen3.5-9B, 150 step, T=1.0 기준 마지막 실행(smoke 3, 2026-10-14) 결과임.
task 수가 적어 경향을 보는 수준이고, 같은 설정의 반복 실행 사이에도 차이가 큼(아래 진입 문서 행 참고).
5개 모두 워크플로우 없이 base 모델이 풀던 task라 해결률 차이는 볼 수 없음.

| | thinking 끔 | thinking 켬 |
|---|---|---|
| 해결 | 4/5 | 4/5 |
| 진입 문서를 읽음 | 2/5 | 4/5 |
| converge까지 완주 | 0 | 2 (+1개는 implement 문서를 건너뛰고 converge 보고서 작성) |
| 진입 문서를 읽고 converge 전에 멈춤 | 2 (implement 문서까지 1, tasks 문서까지 연 뒤 150 step 소진 1) | 1 (tasks 문서까지 연 뒤 implement 문서 없이 구현) |
| converge 보고서 작성 / `converged` / 2회차 실행 | 0 / 0 / 0 | 3 / 3 / 0 |
| converge 보고서가 정해진 형식을 따름 | — | 2/3 (1개는 1회차인데 `convergence-2.md`, `**Outcome**` 대신 `**Status**`) |
| Polish 제목 유지 (tasks.md를 쓴 경우) | 2/2 (번호 채움) | 4/4, 모두 템플릿의 `## Phase N:`을 번호 없이 그대로 둠 |
| contracts 줄을 채움 (plan.md를 쓴 경우) | 1/1 (`<reason>`을 글자 그대로 남김) | 3/4 |
| `checks/`에 검증 스크립트 작성 | 0 | 3 |
| 검증 스크립트를 `/tmp/*.py`에 작성 | 2 | 2 |
| 코드 수정 전 `checks/` 스크립트 실패 확인 | 0 | 1 |
| 코드 수정 전 관련 기존 테스트 실행 | 0 | 4 |
| 패키지 설치 | 0 | 1개 rollout에서 `pip install` 3회 |
| 형식이 깨진 도구 호출로 종료 | 0 | 0 |
| 사용한 step | 57–150 (1개 한도 도달) | 26–90 |

세 차례 smoke(smoke 1 → 문서 수정 → smoke 2 → 문서 수정 → smoke 3, 같은 task·설정)에 걸쳐 보인 동작은 아래와 같음.

- 진입 경로 안내는 효과가 있었음.
  - 문서를 `/testbed` 아래에서 찾은 경우가 3회 모두 0임(speckit_bug smoke 10개 중 3개).
  - 진입 문서를 읽은 비율은 9/10, 9/10, 6/10. smoke 3의 하락은 안내 문장이 그대로인 상태에서 thinking 끔 쪽만 2/5로 떨어진 것이라 T=1.0 표본 변동으로 봄. 이 경우 첫 행동은 저장소 `find`나 `think`였음.
- 스크립트는 원본 그대로 동작함.
  - 이식 단계에서 jq 색 코드 문제를 발견해 준비 스크립트로 해결했고, smoke 1의 스크립트 호출 19회는 오류 0, 색 코드 0이었음.
- smoke 1에서는 형식이 깨진 도구 호출로 10개 중 3개가 끝났고, 그중 2개가 미해결이었음.
  - `<function=…>` 없이 `<tool_call>` 안에 `<file_editor>`를 바로 쓰거나 `<function=terminal=command>`처럼 쓴 경우임. parser가 텍스트로 돌려주면 SDK가 세션을 끝냄.
  - smoke 2·3에서는 0/10, 0/10. 문서 변경으로 설명되는 변화는 아니며, parser·모델 쪽 문제로 남아 있음.
- 워크플로우를 건너뛰는 경향이 남아 있음.
  - smoke 1: specify 문서와 템플릿까지 읽고 산출물 없이 바로 푼 경우 3/10.
  - smoke 3: 진입 문서를 아예 열지 않은 경우 4/10.
  - 5개 중 1개 task는 3회 6개 rollout 모두 미해결이었음. 워크플로우를 끝까지 따른 rollout(smoke 2 thinking 켬)과 따르지 않은 rollout 모두 마찬가지임.
- converge까지 완주한 rollout은 3/10, 6/10, 2/10(+1)임. 작성된 converge 보고서는 모두 1회차 `converged`였고, 2회차는 한 번도 실행되지 않아 실제 동작이 확인되지 않음.
- converge 보고서 형식이 항상 지켜지지는 않음. smoke 1·3에서 각 1개가 정해진 `- **Outcome**:` 줄 형식을 따르지 않았고, smoke 3의 다른 1개는 `**Round**:` 줄 앞의 `- `를 뺐음. converge 문서를 읽고 보고서 없이 끝낸 경우도 smoke 1에 1개 있음.
- smoke 1 뒤 규칙을 바꿈.
  - plan의 Phase 1 파일(data-model, quickstart, contracts)을 "필요할 때만"에서 "항상, 해당 없으면 N/A 기록"으로, tasks의 Setup·Foundational·Polish 제목을 "비면 생략"에서 "항상 유지"로 바꿈. 산출물 구조를 일정하게 하려는 목적임.
  - 테스트 규칙을 "기존 테스트만 실행"으로 한 번 바꿨다가, 원본 TDD 순서를 살려 "`checks/` 검증 스크립트를 먼저 쓰고 실패 확인 → 구현 → 통과 확인"으로 다시 바꿈.
- smoke 2에서는 새 규칙이 일부만 지켜짐: contracts 줄을 템플릿 주석 그대로 둔 경우 5/7, `checks/` 스크립트 2/10, 실패 먼저 확인 0/10.
  - 규칙 내용은 그대로 두고 agent가 실제로 보는 위치로 옮김: plan 템플릿의 contracts 줄을 빈칸 양식으로, TDD 순서를 implement 실행 규칙 맨 앞과 진입 문서 단계 표로.
  - smoke 3에서 해당 단계에 도달한 rollout 기준으로 contracts 줄 4/5, `checks/` 스크립트 3/10, 실패 먼저 확인 1/10으로 늘었지만, TDD 순서는 여전히 소수임.
- Polish 제목은 smoke 2·3에서 tasks.md를 쓴 13개 모두 남아 있었음.
  - 대부분 템플릿의 `## Phase N: Polish & Cross-Cutting Concerns`를 번호 없이 그대로 둠. 실제 경향은 "phase 번호를 채우지 않음"임.
  - 처음 집계에서 번호 붙은 제목만 세어 0/7, 2/6으로 잘못 기록했고, 그 수치를 근거로 넣었던 Polish 안내 문구는 되돌림.
- spec 규칙을 원문(비즈니스 관점) 그대로 둔 영향은 이 task들에서 보이지 않았음. smoke 1에서 plan.md를 쓴 7개 모두 issue의 API 이름을 담았고, 체크리스트는 8개 중 5개가 전부 체크됨. 나머지 3개는 미체크로 두고 implement가 진행 분기를 탐.
- 금지 규칙 위반도 남아 있음.
  - 저장소 테스트 파일 수정: smoke 1에서 1건.
  - 패키지 설치(`pip install`): smoke 2·3에서 각 1개 rollout, 3회씩.
  - 검증 스크립트를 `checks/` 대신 `/tmp`에 쓰는 경우: smoke 2 3/10, smoke 3 4/10. 저장소 밖이라 patch에는 영향 없음.
- step 사용이 많음. smoke 2에서 137/150, smoke 3에서 150/150(한도 도달)까지 쓴 rollout이 각 1개 있음.

## 9. 파일 구성

| 경로 | 내용 |
|---|---|
| `docs/core-workflow.md` | 진입 문서 (직접 작성, 98줄) |
| `docs/stages/01-specify.md` ~ `05-converge.md` | 단계 문서. 원본 명령 문서 5개(1,236줄)를 `build.py`로 변환한 결과(675줄) |
| `sandbox/specify/scripts/bash/*.sh` | 원본 스크립트 4개 (바이트 동일, 실행 권한) |
| `sandbox/specify/templates/*.md` | 변환한 템플릿 4개 (원본 541줄 → 494줄) |
| `sandbox/specify/memory/constitution.md` | 원본 빈 constitution 템플릿 |
| `setup.sh` | 색상 없는 jq wrapper 설치 |
| `instruction.md`, `system-prompt.j2` | 사용자 메시지 앞 안내, system prompt |
| `build.py` | 원본 → 단계 문서·템플릿 변환과 스크립트·constitution 복사. `--list`로 원본 대비 바꾼 곳 전체 목록(단계 문서 87건, 템플릿 24건), `--check`로 생성 결과가 최신인지와 복사본이 원본과 같은지 확인 |
| `__init__.py` | 워크플로우 등록 정보 (문서 `/speckit-sdd`, `.specify` 업로드 위치, 수집 경로, 준비 스크립트) |
| `LICENSE-spec-kit` | 원본 MIT 라이선스 |
| `porting/` | 이식 기록: 원본 조사, 어긋나는 지점 목록, 결정 사항, 변경 요약, smoke 결과 |

- 원본 대비 바꾼 이유와 결정 과정은 `porting/03-decisions.md`(결정 표, smoke 뒤 개정 3회 포함)와 `porting/05-changes.md`(한국어 변경 요약)에 있음. 같은 항목이 여러 번 개정된 경우 뒤쪽 개정이 현재 상태임.
- smoke 실행별 상세 수치는 `porting/06-smoke.md`에 있음.
- 원본 Spec Kit 문서 중 동작 이해에 도움이 되는 것: 저장소 `README.md`(사용 예시), `docs/quickstart.md`(짧은 경로와 전체 경로), `docs/reference/agentic-sdd.md`(명령별 역할, implement ⇄ converge 반복), `docs/guides/existing-projects.md`(기존 저장소 도입 방침), `templates/commands/converge.md`(converge 판정 원문).
