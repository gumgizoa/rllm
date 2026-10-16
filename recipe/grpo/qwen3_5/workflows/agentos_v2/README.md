# agentos_v2: Agent OS 스펙 파이프라인 안내

SWE task(issue 하나를 받아 저장소 코드를 고치는 과제)를 Agent OS의 스펙 파이프라인으로 풀게 하는 rllm 워크플로우임.
이 문서는 파이프라인이 어떻게 구성되고 돌아가는지, rollout이 끝나면 무엇이 남는지를 정리함.
채점 방법은 다루지 않음.

## 1. 한눈에 보기

- 원본: [buildermethods/agent-os](https://github.com/buildermethods/agent-os) v2.1.1 (tag `v2.1.1`, commit `6a6495111e9f7f9cdab3c172814a7476e83a8ec9`), MIT 라이선스(`LICENSE-agent-os`).
  - 저장소의 `main`은 구조가 다른 v3이라 쓰지 않음.
- Agent OS는 원래 사람이 agent 앱(Cursor 등) 채팅에 명령 문서를 하나씩 붙여 넣으며 쓰는 도구임.
  - 사람이 `~/agent-os`를 설치하고 프로젝트에서 `project-install.sh`를 실행하면 `agent-os/commands/<명령>/<명령>.md`가 생김("다른 도구용" 설치 경로).
  - 사람이 명령 문서 하나와 기능 설명을 채팅에 넣으면, agent가 그 지침대로 계획 문서와 코드를 직접 파일로 씀.
  - shape-spec은 질문을 출력하고 멈춰서 사람의 답을 기다림. implement-tasks도 "전부 진행할까요?"를 묻고 기다림.
  - 명령이 끝나면 "다음 명령을 실행하라"는 안내를 출력하고 멈춤. 사람이 결과를 검토하고 다음 명령을 넣음.
  - 호출 방법 자체는 원본 저장소가 아닌 외부 문서에만 있어, 위 사용 방식은 설치 스크립트와 문서 내용에서 추정한 것임.
- 이 워크플로우는 네 명령을 사람 없이 한 세션 안에서 끝내도록 바꾼 것임.
  - 명령 문서는 원본 설치 스크립트를 그대로 돌려 미리 만들고(편집 반영), sandbox의 `/agent-os/`에 올림.
  - 원본에 없는 진입 문서(`core-workflow.md`)를 새로 써서 네 명령을 순서대로 잇게 함.
  - 사람이 하던 답변·승인·다음 명령 입력은 "스스로 답하고 기록", "다음 명령 문서를 열어 계속"으로 대체함.
  - 원본이 `@agent-os/standards/...` 참조로만 넣던 코딩 standards(규칙 문서)는 각 명령 문서 안에 내용째 펼쳐 넣음. openhands-sdk는 `@` 참조를 자동으로 펼치지 않기 때문임.
- 절차는 **shape-spec → write-spec → create-tasks → implement-tasks** 네 명령, 각 1회.
  원본 v2.1.1의 단일 agent 스펙 파이프라인 그대로이고, 반복 라운드는 없음.
  - 원본의 다른 명령 중 plan-product(제품 mission·roadmap·tech stack 작성)와 orchestrate-tasks(서브에이전트 위임)는 넣지 않음.
- 기능 추가와 버그 수정을 하나의 워크플로우로 다룸.
  진입 문서가 "feature = issue가 요구하는 변경(수정이든 추가든)"으로 정의함.

## 2. sandbox 구성

agent가 시작하기 전에 harness가 sandbox를 아래처럼 준비함.
별도 준비 스크립트, 추가 설치 도구, 추가 업로드 파일은 없음.

| 경로 | 내용 | 누가 만드나 |
|---|---|---|
| `/testbed` | 고칠 저장소 (SWE-Gym task 이미지). git history는 숨겨져 커밋 1개짜리 대체 저장소로 보임 | task 이미지, harness |
| `/agent-os/core-workflow.md` | 진입 문서 (92줄) | harness 업로드 |
| `/agent-os/commands/<명령>/<명령>.md` | 명령 문서 4개: shape-spec 359줄, write-spec 272줄, create-tasks 388줄, implement-tasks 310줄 | harness 업로드 |
| `/tmp/agent-os/specs/<YYYY-MM-DD>-<이름>/` | spec 폴더. 모든 계획 산출물이 여기 생김 | agent (shape-spec PHASE 1) |
| `/opt/openhands-sdk-system-prompt.j2` | 교체한 system prompt | harness |
| `/opt/rllm-collect-start` | 시작 시점 commit을 적은 표시 파일. 수정 시각이 agent 시작 시각 | harness |

harness가 하는 일은 네 가지임.

1. `/agent-os`를 지우고 다시 만든 뒤 `docs/` 내용을 올림.
   - 재사용 sandbox에 이전 문서가 남지 않게 하기 위함.
2. 올라간 `.md` 수를 세어 5개가 아니면 rollout 중단.
   - 문서 없이 돈 rollout이 "워크플로우를 무시한 rollout"처럼 기록되는 것을 막기 위함.
3. system prompt 파일을 쓰고, runner가 SDK 기본 프롬프트 대신 이 파일을 쓰게 함.
4. agent 시작 직전에 `/testbed`의 commit을 표시 파일에 기록함. 끝난 뒤 patch와 새로 생긴 파일을 이것 기준으로 찾음.

### 명령 문서를 만드는 방식

명령 문서는 손으로 쓰지 않고 `build.py`가 원본에서 생성함.

1. v2.1.1 tag tree를 임시 `$HOME/agent-os`로 복사(원본의 기본 설치 자리).
2. 렌더 전 원문(`profiles/default/commands/*/single-agent/*`, `workflows/**`, `standards/**`)에 편집 57건 적용(환경 맞춤 32, 의미 변경 25).
   - 편집마다 기준 문장이 원문에 정확히 1번 있어야 함. 원본이 바뀌면 build가 실패함.
3. `standards/global/tech-stack.md` 삭제, 기본 `config.yml`을 "다른 도구용" 경로로 설정(`claude_code_commands: false`, `agent_os_commands: true`).
   - tech-stack.md는 원본이 빈 양식으로 설치하는 파일이라 뺐음. standards는 15개 중 14개가 남음.
4. 원본 `scripts/project-install.sh`를 빈 프로젝트에서 오프라인으로 실행(bash, perl 필요).
5. 번호 없는 최상위 명령 파일 4개만 가져와 후처리함.
   - `@agent-os/standards/<dir>/<file>.md` 줄을 그 파일 내용으로 교체. shape-spec에는 global 5개, 나머지 셋에는 14개 전부.
   - `agent-os/specs/` 접두사를 `/tmp/agent-os/specs/`로 바꿈. spec 폴더를 저장소 밖으로 빼서 patch와 agent의 `git clean`이 닿지 않게 하기 위함.
   - 사람·서브에이전트를 가리키는 문구 같은 금지 문자열이 남으면 build 실패.

원본 렌더 기준 4개 문서 986줄이 standards를 펼친 뒤 1,329줄이 됨.

## 3. agent가 받는 입력

- **system prompt**: openhands-sdk 기본 프롬프트에서 절차 섹션(`<PROBLEM_SOLVING_WORKFLOW>`)만 이 워크플로우용으로 새로 씀.
  - 내용: 파이프라인 요약, 첫 행동은 `/agent-os/core-workflow.md` 열기, 명령 문서를 순서대로, 답·검토 없음, 매 턴 도구 호출, 최종 보고서 뒤 `finish`.
  - 나머지 15개 섹션은 SDK 기본 그대로임. 기본 섹션의 "ask the user", "confirm with the user" 문구도 다른 워크플로우와 비교할 수 있게 남겨 둠.
- **사용자 메시지 1개**: 앞에 워크플로우 안내(`instruction.md`), 뒤에 SWE-Gym task 본문.
  - 안내 요지: "Agent OS 명령 문서 4개를 이 세션에서 순서대로 직접 수행하라. 저장소를 보기 전에 `/agent-os/core-workflow.md`를 여는 것이 첫 행동이다. `/agent-os`는 루트 바로 아래이고 `/testbed` 안에 없다."
  - task 본문은 SWE-Gym 기본 프롬프트에서 자체 6단계 절차를 뺀 버전(`swegym293_aidlc` 데이터셋)을 씀. 이전 AI-DLC 실험에서 절차가 두 개면 86%가 워크플로우 문서를 열지 않았기 때문임.
  - task 본문에 남은 내용: 저장소는 `/testbed`, 테스트 파일 변경은 이미 처리됨("you DON'T have to modify … any of the tests"), 의존성 설치 완료, 테스트가 아닌 파일만 최소 변경.
  - issue는 `<issue_description>` 태그 안에 있음.
- **도구**: openhands-sdk의 터미널(`terminal`), 파일 편집기(`file_editor`), task tracker 세 가지. SDK가 기본으로 붙이는 `finish`, `think`도 쓰임.
- **step 예산**: 150 (`config/config.yaml`의 `agent_step_limit`, smoke도 같음). agent 시간 제한 3600초. 대화 압축(condenser)은 쓰지 않음.

## 4. 진행 흐름

```
shape-spec            ──►  write-spec   ──►  create-tasks   ──►  implement-tasks                         ──►  finish
 PHASE 1 폴더·issue 저장      spec.md          PHASE 1 spec 찾기     PHASE 1 전체 group 선택
 PHASE 2 질문·자체 답변                         PHASE 2 tasks.md      PHASE 2 group 하나 구현 ─┐ 미체크 남으면 반복
 → requirements.md                                                          ▲──────────────┘
                                                                     PHASE 3 검증·보고서 (1회)
```

agent는 진입 문서를 읽고, 명령마다 해당 명령 문서를 열어 PHASE 순서대로 따름.
각 명령 문서의 끝이 "다음 명령 문서를 열고 계속"으로 되어 있어 사람 없이 이어짐.
spec 폴더 이름은 고정이 아니라 오늘 날짜 + agent가 지은 kebab-case 이름임(원본 규칙 그대로).
아래에서 spec 폴더를 `S`라 씀.

| 단계 | 문서 | 하는 일 | 남기는 것 |
|---|---|---|---|
| shape-spec PHASE 1 | `/agent-os/commands/shape-spec/shape-spec.md` | bash(`date`, `mkdir -p`)로 spec 폴더 생성, issue 원문 저장 | `S/planning/`, `S/planning/visuals/`, `S/implementation/`, `S/verifications/`(빈 폴더), `S/planning/initialization.md` |
| shape-spec PHASE 2 | 같은 문서 | 저장소 README·문서 목차·패키징 정보로 맥락 파악 → 번호 질문 4–8개 + 재사용 질문 작성, 스스로 답함 → visuals 폴더 `ls`(필수) → 재사용 질문은 저장소 검색으로 답함 → 필요하면 후속 질문 1–3개 | `S/planning/requirements.md` |
| write-spec | `/agent-os/commands/write-spec/write-spec.md` | requirements 읽기, visuals `ls`, 재사용 코드 검색, spec 작성(코드 금지, 양식 외 절 금지) | `S/spec.md` |
| create-tasks PHASE 1 | `/agent-os/commands/create-tasks/create-tasks.md` | spec.md·requirements.md가 맥락에 없으면 `/tmp/agent-os/specs/` 아래에서 찾음. 없으면 shape-spec·write-spec부터 수행 | 없음 |
| create-tasks PHASE 2 | 같은 문서 | 의존 순서와 분야별로 task group 분해. group마다 "테스트 2–8개 작성 → 구현 → 그 테스트만 실행" | `S/tasks.md` |
| implement-tasks PHASE 1 | `/agent-os/commands/implement-tasks/implement-tasks.md` | tasks.md의 모든 group을 첫 group부터 순서대로 하기로 정함 | 없음 |
| implement-tasks PHASE 2 | 같은 문서 | 현재 group 하나 구현, 체크박스 `- [x]`, 자기가 쓴 check script만 실행 | `/testbed` 코드 변경, `S/tasks.md` 체크, `S/checks/*` |
| implement-tasks PHASE 3 | 같은 문서 | tasks.md 확인(미체크는 코드 spot check 후 체크 또는 ⚠️), roadmap 단계, 전체 테스트 실행(실패는 고치지 않고 기록), 보고서 작성 | `S/verifications/final-verification.md` |

단계 사이 규칙은 아래와 같음.

- 각 명령은 1회만 하고, 명령 사이로 되돌아가는 루프는 없음.
- 유일한 반복은 implement-tasks PHASE 2: 미체크 task가 남아 있으면 다음 group으로 PHASE 2를 다시 함. 횟수 상한은 없고 group 수만큼 돎.
- 모든 체크가 끝나면 PHASE 3을 1회 함.
- PHASE 3의 전체 테스트 실행은 범위·시간 제한 없이 원문 그대로임.
  - 이식 중 수정 전 이미지로 사전 조사한 결과, 5개 저장소는 전체 테스트가 수집 단계에서 멈추고, 끝까지 돈 8개 저장소는 모두 원래부터 실패가 있었음. 끝나는 데 7–17분 걸린 저장소도 있음.
  - 결과는 보고서에 기록만 하고 코드를 고치지 않음.
- roadmap 단계는 원문 문장을 남기고 "이 프로젝트에는 roadmap이 없으니 만들지 말고 보고서 2절에 `⚠️ No Updates Needed`와 이유를 적어라"를 덧붙임.
- 끝: `S/verifications/final-verification.md`를 쓰면 바로 `finish` 호출.
- 도구 호출 없이 텍스트만 내면 그 즉시 세션이 끝남(openhands-sdk 동작). 그래서 문서가 `finish` 전 텍스트 응답을 금지함.

## 5. 산출물 형식

모든 계획 산출물은 `S` = `/tmp/agent-os/specs/<YYYY-MM-DD>-<이름>/` 아래에 생기고, 끝날 때까지 그 자리에 있음(옮기는 단계 없음).
rollout 하나에 spec 폴더 하나를 전제로 함.

| 파일 | 쓰는 단계 | 형식 요약 |
|---|---|---|
| `planning/initialization.md` | shape-spec PHASE 1 | issue 원문 그대로 (원본은 이 파일을 읽기만 하고 쓰는 단계가 없어 새로 넣은 단계) |
| `planning/requirements.md` | shape-spec PHASE 2 | `# Spec Requirements:` → `## Initial Description`, `## Requirements Discussion`(`### First Round Questions`의 `**Q1:**` / `**Answer:** (assumed) <답> — <근거>`, `### Existing Code to Reference`, `### Follow-up Questions`), `## Visual Assets`, `## Requirements Summary`(`### Functional Requirements`, `### Reusability Opportunities`, `### Scope Boundaries`, `### Technical Considerations`). 재사용 항목은 `(assumed) <경로> — <근거>`, 없으면 "No similar existing features identified for reference." |
| `spec.md` | write-spec | `# Specification:` → `## Goal`, `## User Stories`(최대 3), `## Specific Requirements`(굵은 이름 + bullet 최대 8, 최대 10개), `## Visual Design`, `## Existing Code to Leverage`(최대 5), `## Out of Scope`(최대 10). 양식 외 절 추가 금지 |
| `tasks.md` | create-tasks, implement-tasks가 체크 | `# Task Breakdown:` → `## Overview`(Total Tasks), `## Task List` → `### <계층>` → `#### Task Group N: <이름>` + `**Dependencies:**` + `- [ ] N.0 …` 아래 `- [ ] N.1 …` + `**Acceptance Criteria:**`, 끝에 `## Execution Order`. 예시는 원문의 웹앱(DB → API → UI → 테스트 검토) 그대로이고 "기능에 맞게 바꿔라"는 문장이 붙음. 미완료로 판단한 task는 ⚠️ |
| `checks/*` | create-tasks가 계획, implement-tasks가 작성·실행 | group의 테스트(2–8개, 테스트 검토 group은 최대 10개 추가)를 저장소 테스트 파일 대신 여기에 스크립트로 씀. 임시 파일도 여기. 어느 명령도 폴더를 만들지 않아 처음 쓸 때 agent가 만듦 |
| `verifications/final-verification.md` | implement-tasks PHASE 3 | 머리(`**Spec:**`, `**Date:**`, `**Verifier:** implementation-verifier`, `**Status:** ✅ Passed \| ⚠️ Passed with Issues \| ❌ Failed`) → `## Executive Summary` → `## 1. Tasks Verification` → `## 2. Roadmap Updates` → `## 3. Test Suite Results`(Total / Passing / Failing / Errors, Failed Tests, Notes) |
| `planning/visuals/`, `implementation/` | shape-spec PHASE 1 | 빈 폴더로 남음. 시안을 넣을 사람이 없고, 원본 v2.1.0에서 task별 구현 보고서가 폐지됨 |

읽을 때 알아야 할 개념은 아래와 같음.

- **spec 폴더 자리표시**: 문서는 같은 폴더를 `[this-spec]`, `[current-spec]`, `[spec-path]`, `$SPEC_PATH` 네 가지로 부름. 진입 문서가 넷 다 같은 폴더라고 정의함.
- **standards**: 명령 문서 끝 "User Standards & Preferences Compliance" 아래 굵은 `agent-os/standards/...` 줄은 이름표일 뿐이고 sandbox에 그런 파일은 없음.
  - 원본에서 뺀 줄: conventions의 README 최신화·커밋/브랜치/PR·의존성 최신화·코드 리뷰·머지 전 테스트·feature flag·changelog 7줄, coding-style의 dead code 삭제·하위 호환 무시·DRY 3줄, migrations의 "migration을 version control에 커밋" 1줄. 팀 절차이거나 issue 밖 작업을 부르는 줄이라 뺌.
- **보고서 절 번호**: 원본 양식은 1·2·3·4절이었고, 이식에서 폐지된 구현 문서 확인 절(2절)을 지우고 1·2·3으로 다시 매김.
- **검증 도구 없음**: 이 워크플로우에는 산출물 형식을 검사하는 CLI가 없음. sandbox 안에서 형식을 확인하는 것은 아무것도 없고, harness는 문서 업로드 개수만 확인함. `build.py`의 금지 문자열 검사는 문서 생성 시점의 검사임.

## 6. agent에게 주어진 규칙

instruction, system prompt, 진입 문서, 명령 문서에 걸쳐 agent에게 주어지는 규칙을 모으면 아래와 같음.

- **사람이 없음**: 아무도 메시지를 읽거나 답하거나 검토하거나 다음 명령을 시작하지 않음.
  - 문서가 질문하라고 하면 양식대로 질문을 쓰고, issue와 저장소를 근거로 스스로 답해 `**Answer:** (assumed) <답> — <근거>`로 기록함. 답을 기다리지 않음.
  - 명령이 끝나면 요약하지 말고 바로 다음 명령 문서를 엶. `finish` 전에는 텍스트 메시지를 보내지 않음.
- **입력**: issue(`<issue_description>`과 `</issue_description>` 사이)가 외부에서 오는 유일한 입력. 나머지는 저장소에서 알아냄. 제품 문서(mission·roadmap·tech stack)가 없으니 제품 맥락은 저장소 README, 문서 목차, 패키징·빌드 정보에서 파악함.
- **진행 기록**: `S/tasks.md`의 체크박스가 구현 기록임. TaskTracker 도구는 개인 메모로만 쓰고 체크박스를 대신하지 않음.
- **저장소**: `/testbed`는 implement-tasks PHASE 2에서만 바꿈.
  - shape-spec, write-spec, create-tasks는 저장소를 읽고 명령을 실행할 수 있지만 바꾸지 않음. PHASE 3도 코드를 바꾸지 않으므로 코드 변경은 PHASE 3 전에 끝나야 함.
  - 저장소 테스트 파일은 추가·수정하지 않음. task가 요구하는 테스트는 `S/checks/`의 스크립트로 씀.
  - spec 파일, 메모, 요약, 임시 스크립트를 `/testbed`에 두지 않음. 모두 `S/`, 임시 파일은 `S/checks/`.
- **산출물**: 각 파일은 해당 문서의 양식대로 쓰고, 그 명령이 끝나면 `tasks.md` 체크박스 외에는 고치지 않음.
- **환경**: 네트워크·설치 금지 규칙은 문서에 넣지 않음. 원본에 네트워크를 쓰는 지시가 없고, task 본문이 "의존성은 설치되어 있다"고 말함. sandbox는 인터넷이 열려 있음(`allow_internet = true`).
- **이름과 경로**: 문서 `/agent-os/`, spec 폴더 `/tmp/agent-os/specs/<YYYY-MM-DD>-<이름>/`(날짜 폴더 이름 규칙 유지), 보고서 `S/verifications/final-verification.md`.
- **단계 순서·반복·종료**: 4절 참고.

## 7. rollout이 끝나면 남는 것

rollout이 끝나면 sandbox는 사라지고, 아래 두 가지가 episode JSON에 남음.

**대화 기록** (`trajectories[0].steps[]`)

- step 하나가 LLM 호출 하나임.
- `model_output`에 agent가 낸 것이 들어 있음: `content`(텍스트), `reasoning`(thinking을 켠 경우 문자열), `tool_calls`(`name`과 `arguments`, `arguments`는 dict).
  - 터미널 명령은 `name: terminal`, `arguments.command`.
  - 파일 작업은 `name: file_editor`, `arguments.command`가 `view` / `create` / `str_replace` 등, `arguments.path`.
  - 마지막은 `name: finish`, `arguments.message`(요약 텍스트).
- 도구 실행 결과는 다음 step의 `chat_completions` 안 `role: tool` 메시지에 있음(`tool_call_id`, `name`, `content: [{type: text, text}]`).
  - `chat_completions`는 system·user 메시지부터 그 step의 assistant 메시지까지 대화 전체를 담음. 그 안의 `function.arguments`는 dict가 아닌 JSON 문자열임.
  - 터미널 결과 끝에 종료 코드가 붙음(`[Command finished with exit code N]`).
- 경로와 파일 쓰기가 기록되는 모양은 여러 가지임(smoke에서 확인).
  - 파일을 셸 heredoc(`cat > 파일 << 'EOF'`)으로 쓰는 경우가 흔함(smoke 2에서 8개 중 6개).
  - shape-spec의 bash 블록이 `SPEC_PATH` 셸 변수를 정의하므로, 이후 명령에 실제 경로 대신 `$SPEC_PATH/...`만 나오기도 함(smoke 2에서 이 문자열이 나온 rollout 6/8).
  - 저장소 코드를 파일 편집 도구 없이 터미널(heredoc, `/tmp`의 파이썬 스크립트)로만 고친 rollout이 있음(smoke 2에서 2/8).
  - 도구 이름이 `str_replace`로 기록된 호출이 있음. 실제로는 `file_editor`로 실행되고 결과 메시지의 `name`은 `file_editor`임(smoke 2에서 1/8, smoke 1에서 2/8, 각 1회).

**수집 산출물** (`artifacts`): agent 실행이 끝난 직후, 채점 테스트가 저장소를 건드리기 전에 harness가 읽어 둠.

| 키 | 내용 |
|---|---|
| `workflow_outputs` | `/tmp/agent-os` 아래 모든 파일의 경로 → 내용. spec 폴더 산출물과 `checks/` 스크립트 포함. 빈 폴더(`planning/visuals/`, `implementation/`)는 나타나지 않음 |
| `workflow_outputs_skipped` | 총 1MB를 넘어 내용을 담지 못한 파일(경로 → 크기) |
| `patch`, `patch_base`, `patch_bytes`, `patch_truncated` | 시작 시점 대비 저장소 변경(`git diff`, 새 파일 포함). 채점 테스트가 평가한 그 변경. `patch_base`는 git history를 숨긴 대체 commit. 1MB 초과분은 잘림 |
| `patch_error` | patch를 못 얻은 이유(있을 때만) |
| `stray_files`, `stray_files_truncated` | agent 실행 중 `/tmp`(출력 폴더 제외)나 `/agent-os`에 생기거나 바뀐 파일(이름과 크기만, 최대 500개). pytest 임시 폴더, `__pycache__`, 편집기 되돌리기 기록은 제외 |
| `workflow` | 워크플로우 이름과 버전 해시(문서·instruction·system prompt 기준). 지금 패키지 = `0f91c41d…`(smoke 2와 같음), smoke 1은 `cbf2c64b…` |

- 지금 reward는 숨겨진 테스트 통과 여부(`is_correct`, trajectory `reward` 1.0 / 0.0)뿐임. `metrics`에 `f2p_success`/`f2p_total`, `p2p_success`/`p2p_total`, `steps_used`가 있음.
- 이 워크플로우에는 준수율 채점기가 아직 없음. 실행하면 "no compliance scorer … resolve rate only" 경고가 한 줄 나옴.
- 산출물 위치는 끝난 방식과 관계없이 항상 `S` 아래임(옮기는 단계가 없음). 중간에 끝났으면 그때까지 쓴 파일만 있고, spec 폴더를 만들기 전에 끝났으면 `workflow_outputs`가 비어 있음.
- spec 폴더 이름을 미리 알 수 없으므로 `/tmp/agent-os/specs/*/`로 찾아야 함.

## 8. smoke에서 관찰된 실제 동작

마지막 실행(smoke 2, 2026-10-16) 기준임.
Qwen3.5-9B, thinking 켬, 150 step, T=1.0, 버그 수정·기능 추가 task를 합친 SWE-Gym task 8개 × 1회.
**thinking 끔은 돌리지 않았음**(사용자 결정).
task 수가 적어 경향을 보는 수준이고, 비율이 아닌 건수로 읽어야 함.

| 항목 | thinking 켬 |
|---|---|
| 해결 | 7/8 (conan-13721 실패) |
| 진입 문서를 첫 행동(호출 0–1번째)으로 읽음 | 8/8 |
| 명령 문서 4개를 순서대로 엶 | 8/8 |
| 텍스트만 내고 종료 / 저장소에 워크플로우 파일 | 0/8 / 0/8 (모두 `finish`로 종료) |
| spec 폴더 1개 | 8/8 |
| `initialization.md`에 issue 저장 | 8/8 |
| 질문 답을 모두 `(assumed)`로 기록 | 7/8 (conan은 6개 중 5개) |
| 재사용 질문을 저장소 경로로 답함 | 7/8 |
| task group 2개 이상을 반복 구현 / 끝에 미체크 0 | 7/8 / 8/8 |
| 보고서가 양식 절(1·2·3) 사용 / 양식 밖 절 추가 / 양식 무시 | 7/8 / 2/8 / 1/8 (dvc-4075) |
| roadmap `⚠️ No Updates Needed` | 7/8 |
| 보고서 Status `✅ Passed` (Status 줄이 있는 보고서) | 7/7, 해결 못한 conan 포함 |
| `checks/` 스크립트 작성 | 4/8 |
| tasks.md에 테스트 작성 task | 2/8 |
| 전체 테스트 실행 시도 / 전체 수치 보고 | 1/8 / 0/8 |
| 사용한 step / rollout 시간 | 41–77 / 365–653초 |
| 명령별 step (문서를 연 때부터 다음 문서를 열 때까지) | shape-spec 11–29, write-spec 2–9, create-tasks 2–4, implement-tasks 16–45 |

여러 차례 고치면서 보였던 동작과 남은 경향은 아래와 같음.

- 보고서 절 번호 구멍: 이식에서 구현 문서 확인 절을 지우자 양식이 1·3·4절로 남았음.
  - smoke 1에서 8개 중 5개가 1·3·4를 그대로 쓰고 3개가 스스로 번호를 바꿈. 번호로 절을 찾으면 틀리는 상태였음.
  - 양식을 1·2·3으로 다시 매기고 roadmap 안내 문장도 "2절"로 고침 → smoke 2에서 양식을 따른 보고서 7개 모두 1·2·3.
- write-spec 건너뜀: smoke 1에서 1/8(dvc-4075, `spec.md` 없음) → smoke 2에서 0/8. 문서는 고치지 않음(순서가 분명히 적혀 있음).
- 아래 경향은 문서가 분명한데 agent가 벗어난 것으로 보고 문서를 고치지 않았고, 학습 대상으로 기록함(`porting/06-smoke.md`). 준수율 신호가 있어야 학습에서 오를 수 있음.
  - 테스트 먼저 작성(task group의 x.1)이 드묾: tasks.md에 테스트 task 2/8(두 실행 모두), `checks/` 스크립트 2/8 → 4/8.
    smoke 1의 한 tasks.md에 "Test changes are handled separately" 메모가 있어, task 본문의 "테스트는 이미 처리됨"이 원문 지시를 이긴 것으로 보임.
  - 전체 테스트 대신 바꾼 모듈의 테스트만 돌림: 시도 1/8(두 실행 모두 conan), 전체 수치 보고 0/8.
    smoke 1의 시도는 SDK 터미널 300초 timeout 뒤 일부 테스트로 대체, smoke 2의 시도는 `timeout 300 pytest -x`가 첫 에러에서 27초 만에 멈춤.
  - 보고서 양식 이탈: 양식 밖 절 추가 4/8 → 2/8, 양식 자체 무시 0/8 → 1/8.
- conan-13721은 smoke 1·2 모두 실패했고, 다른 워크플로우(speckit_sdd) smoke 3회에서도 3/3 실패함. 워크플로우와 무관하게 어려운 task로 보이나 확인하지 않음.
- conan 테스트가 `/tmp/tmp*`에 파일을 대량으로 만들어 `stray_files`가 500개 상한에 걸림(두 실행 모두). 저장소 밖이라 patch에는 영향 없음.

## 9. 파일 구성

| 경로 | 내용 |
|---|---|
| `docs/core-workflow.md` | 진입 문서 (직접 작성, 원본에 대응 문서 없음) |
| `docs/commands/{shape-spec,write-spec,create-tasks,implement-tasks}/<명령>.md` | 명령 문서. 원본을 `build.py`로 렌더한 결과 |
| `instruction.md`, `system-prompt.j2` | 사용자 메시지 앞 안내, system prompt |
| `build.py` | 원본 → 명령 문서 변환기. `--list`로 원본 대비 바꾼 곳 전체 목록, `--upstream <v2.1.1 checkout> --check`로 생성 결과가 최신인지 확인. tag checkout(worktree) 만드는 법은 docstring에 있음 |
| `__init__.py` | 워크플로우 등록 정보(`container_dir="/agent-os"`, `entry_doc`, `output_dirs=("/tmp/agent-os",)`, 채점기 없음) |
| `LICENSE-agent-os` | 원본 MIT 라이선스 고지 |
| `porting/` | 이식 기록: 원본 조사, 어긋나는 지점 목록, 결정 사항, 계획, 변경 요약, smoke 결과, 나중에 시도할 아이디어(`later.md`) |

- 원본 대비 바꾼 이유와 결정 과정은 `porting/03-decisions.md`(결정 표)와 `porting/05-changes.md`(한국어 변경 요약, agent 행동 변화 표)에 있음.
- smoke 실행별 상세 수치는 `porting/06-smoke.md`에 있음.
- 테스트는 패키지 밖 `recipe/grpo/qwen3_5/tests/test_agentos_v2.py`에 있음. 렌더 테스트는 원본 checkout(`../agent-os-v2.1.1` 또는 `AGENT_OS_V2_DIR`)이 없으면 건너뜀.
- 원본 문서 중 동작 이해에 도움이 되는 것(v2.1.1 tag 기준):
  - `CHANGELOG.md`의 2.1.0 절: 명령 6개의 역할, 폐지된 구현 문서·검증 agent.
  - `profiles/default/workflows/specification/research-spec.md`: 질문 생성 규칙과 requirements 양식.
  - `profiles/default/workflows/implementation/create-tasks-list.md`: tasks 양식과 테스트 작성 방침.
  - `profiles/default/workflows/implementation/verification/`: 검증 4단계와 보고서 양식.
  - `scripts/project-install.sh`, `scripts/common-functions.sh`: 템플릿 태그를 펼치는 설치 스크립트.
  - 원본 `README.md`는 외부 사이트 안내뿐이라 사용법 설명이 없음.
