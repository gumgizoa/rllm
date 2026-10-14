# openspec_ff: OpenSpec 워크플로우 파이프라인 안내

SWE task(issue 하나를 받아 저장소 코드를 고치는 과제)를 OpenSpec 방식으로 풀게 하는 rllm 워크플로우임.
이 문서는 파이프라인이 어떻게 구성되고 돌아가는지, rollout이 끝나면 무엇이 남는지를 정리함.
채점 방법은 다루지 않음.

## 1. 한눈에 보기

- 원본: [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec), npm `@fission-ai/openspec` 1.14.1 (commit `9111a76`), MIT 라이선스.
- OpenSpec은 원래 사람이 Claude Code 같은 agent 앱에서 `/opsx:ff`, `/opsx:apply` 같은 명령을 하나씩 입력하며 쓰는 도구임.
  - 명령마다 agent에게 줄 지침 문서가 있음.
  - agent는 지침에 따라 `openspec` CLI(Node 프로그램)를 실행하고, 계획 문서와 코드를 직접 씀.
  - 단계가 끝나면 사람에게 보고하고 멈춤. 다음 명령은 사람이 입력함.
- 이 워크플로우는 같은 일을 사람 없이 한 세션 안에서 끝내도록 바꾼 것임.
  - 지침 문서는 sandbox 안의 파일로 제공하고, agent가 순서대로 직접 엶.
  - CLI는 실제로 sandbox에 설치되어 원본과 똑같이 동작함.
  - 사람이 하던 단계 연결·질문 답변·승인은 진입 문서의 규칙으로 대체함.
- 절차는 **ff → apply → verify → archive** 네 단계.
  원본 문서가 소개하는 확장 경로(`/opsx:new → /opsx:ff → /opsx:apply → /opsx:verify → /opsx:archive`)에서 new를 뺀 형태임.
  ff가 change(작업 단위 폴더) 생성을 직접 하므로 new가 따로 필요 없음.
- 기능 추가와 버그 수정을 구분하지 않음. 원본도 같은 절차로 둘 다 다룸.

## 2. sandbox 구성

agent가 시작하기 전에 harness가 sandbox를 아래처럼 준비함.

| 경로 | 내용 | 누가 만드나 |
|---|---|---|
| `/testbed` | 고칠 저장소 (SWE-Gym task 이미지에 들어 있음) | task 이미지 |
| `/opsx/` | agent가 읽는 지침 문서: `core-workflow.md`, `stages/01-ff.md`, `02-apply.md`, `03-verify.md` | harness 업로드 |
| `/openspec/` | OpenSpec 계획 폴더(planning root). change, spec, 설정, 스키마가 모두 여기 생김 | 준비 스크립트 |
| `/opt/rllm/agent/node/` | node v22.23.3 + openspec CLI 1.14.1 | 전용 agent 이미지(읽기 전용 마운트) |
| `/usr/local/bin/openspec` | CLI 실행 스크립트 | 준비 스크립트 |

준비 스크립트(`setup.sh`)가 하는 일은 다섯 가지임.

1. 저장소에 이미 `openspec/` 폴더가 있으면 실패 처리.
   - CLI는 현재 위치에서 위로 올라가며 가장 가까운 `openspec/` 폴더를 루트로 쓰기 때문에, 저장소에 있으면 그쪽이 먼저 잡힘.
2. `/usr/local/bin/openspec` 실행 스크립트 작성.
   - `CI=1`로 비대화형 모드 강제. agent의 터미널은 TTY(대화형 터미널)라서, 이 값이 없으면 `openspec new change`가 진행 표시를 띄운 채 끝나지 않음.
   - 텔레메트리와 업데이트 확인 끔(네트워크 사용 없음).
3. `cd / && openspec init --tools none`으로 `/openspec/` 생성.
   - `/` 아래에 만들기 때문에 agent가 `/testbed`에서 CLI를 실행해도 루트는 `/`로 잡히고, 모든 계획 파일은 저장소 밖에 생김.
4. 수정한 스키마와 프로젝트 설정 설치.
   - 스키마 `spec-driven-sandbox`: 원본 `spec-driven` 스키마를 OpenSpec의 사용자 정의 방식(`openspec schema fork`)으로 복사한 뒤 일부 문장만 바꾼 것.
   - 설정 `/openspec/config.yaml`: 위 스키마를 기본으로 지정하고, 환경 사실(`context`)과 산출물별 규칙(`rules`)을 담음.
5. agent가 보게 될 상태 점검: 루트가 `/`인지, 스키마가 인식되는지, TTY에서 CLI가 정상 종료되는지. 하나라도 틀리면 rollout 중단.

### 스키마와 설정이 하는 역할

- **스키마** (`schema.yaml`): 산출물 종류(proposal, specs, design, tasks), 작성 순서, 산출물별 작성 지침과 템플릿을 정의함.
  agent는 이 파일을 직접 읽지 않고, `openspec instructions <산출물>`을 실행하면 CLI가 해당 부분을 출력해 줌.
- 원본 대비 바꾼 문장은 원본이 사람에게 묻거나 멈추라고 한 부분과 SWE task 조건과 충돌하는 부분뿐임.
  - "열린 질문은 사용자에게 물어라" → "직접 결정하고 design의 Decisions에 근거를 기록하라"
  - "막히면 멈추고 물어라" → "가장 타당한 해석으로 진행하고 tasks.md에 기록, 끝내 안 되는 task는 이유를 남기고 넘어감"
  - "task 묶음마다 테스트와 문서를 작성하라" → "기존 테스트 실행이나 확인 스크립트로 검증, 저장소 테스트 파일은 수정 금지, 문서는 issue가 요구할 때만"
  - tasks 예시 중 의존성 설치·단위 테스트 추가·문서 작성 예시를 이 환경에 맞는 예시로 교체
- **설정** (`config.yaml`)의 `context`는 모든 산출물 지침과 apply 지침에, `rules`는 해당 산출물 지침에만 CLI가 붙여서 보여 줌.
  - `context`: 고칠 저장소는 `/testbed`, 계획 폴더는 그 밖, 테스트 파일은 이미 준비됨(수정 금지), 설치·네트워크 없음, 확인 스크립트는 `checks/`, 기존 spec 없음.
  - `rules`: proposal과 specs에 "기존 spec이 없으니 모든 기능은 New Capabilities로, 모든 delta는 `## ADDED Requirements`로".

## 3. agent가 받는 입력

- **system prompt**: openhands-sdk 기본 프롬프트에서 절차 섹션(`<PROBLEM_SOLVING_WORKFLOW>`)만 이 워크플로우용으로 바꾼 것.
  나머지 섹션(도구 사용 규칙 등)은 기본 그대로임.
- **사용자 메시지 1개**: 앞에 워크플로우 안내(`instruction.md`), 뒤에 SWE-Gym task 본문.
  - 안내 요지: "OpenSpec change로 풀어라. 첫 행동으로 `/opsx/core-workflow.md`를 열어라. `/opsx`는 저장소 밖 최상위 디렉터리다."
  - task 본문은 SWE-Gym 기본 프롬프트에서 자체 6단계 절차를 뺀 버전(`swegym293_aidlc` 데이터셋)을 씀. 절차가 두 개면 agent가 워크플로우를 무시하는 경향이 있었기 때문임.
  - issue는 `<issue_description>` 태그 안에 있음.
- **도구**: openhands-sdk의 터미널, 파일 편집기, task tracker 세 가지. `openspec`은 별도 도구가 아니라 터미널로 실행하는 명령임.
- **step 예산**: 150 (설정에 따라 다름). 대화 압축(condenser)은 쓰지 않음.

## 4. 진행 흐름

```
/opsx:ff  ──►  /opsx:apply  ──►  /opsx:verify  ──►  archive  ──►  finish
(계획 작성)     (코드 구현)        (구현 점검)          (마무리)
```

agent는 진입 문서 `/opsx/core-workflow.md`를 읽고, 단계마다 해당 단계 문서를 열어 따름.
각 단계 문서의 끝이 "다음 단계 문서를 열어 계속"으로 되어 있어 사람 없이 이어짐.
change 이름은 항상 `issue`로 고정이고, change 폴더는 `/openspec/changes/issue/`임.

| 단계 | 시작 명령 | 하는 일 | 남기는 것 |
|---|---|---|---|
| ff | `openspec new change "issue"` → `openspec status` → 산출물마다 `openspec instructions <산출물>` | issue와 저장소 코드를 읽고 계획 산출물 작성 | `proposal.md`, `specs/<기능>/spec.md`, `design.md`(필요할 때만), `tasks.md` |
| apply | `openspec instructions apply` | tasks.md의 작업을 하나씩 구현하고 체크박스 갱신. 확인 스크립트 작성·실행 | `/testbed` 코드 변경, `tasks.md`의 `- [x]`, `checks/*.py` |
| verify | `openspec status`로 맥락 확인 후 직접 점검 (verify를 대신하는 CLI 명령은 없음) | 구현을 산출물과 대조해 완전성·정확성·일관성 점검 | `verify.md` |
| archive | `openspec archive issue --yes` | delta spec 형식 검증 → 메인 spec에 병합 → change 폴더 보관 | `/openspec/specs/<기능>/spec.md`, `/openspec/changes/archive/<날짜>-issue/` |

단계 사이 규칙은 아래와 같음.

- verify는 1회만 함. 보고서 결과와 관계없이 다음은 archive이고, 남은 문제는 보고서에 기록됨.
- archive는 `verify.md`가 있을 때만 실행함.
- archive가 실패하면(종료 코드 1) 오류가 가리키는 delta spec 형식만 고쳐 한 번 더 실행함.
  - 그래도 실패하면 archive 없이 끝냄.
  - 검증을 끄는 `--no-validate`는 쓰지 않음.
  - tasks나 apply로 돌아가지 않음(코드는 이미 끝난 상태).
- 마지막에 `finish` 도구를 호출해 세션 종료.

## 5. 산출물 형식

모든 계획 산출물은 `/openspec/changes/issue/` 아래에 생기고, archive가 성공하면 change 폴더째 `/openspec/changes/archive/<YYYY-MM-DD>-issue/`로 옮겨짐.

| 파일 | 형식 요약 |
|---|---|
| `.openspec.yaml` | `schema: spec-driven-sandbox`, `created: <날짜>`. CLI가 생성 |
| `proposal.md` | `## Why`, `## What Changes`, `## Capabilities`(New / Modified Capabilities), `## Impact` |
| `specs/<기능>/spec.md` | delta spec: `## ADDED Requirements` → `### Requirement: <이름>` (SHALL·MUST 문장) → `#### Scenario: <이름>` (`- **WHEN**`, `- **THEN**`) |
| `design.md` | 원본 조건(여러 모듈에 걸침, 새 의존성, 보안·성능, 모호함 등)에 해당할 때만. Context, Goals, Decisions, Risks 등 |
| `tasks.md` | `## 1. <묶음>` 아래 `- [ ] 1.1 <작업과 확인 방법>`. 완료 시 `[x]`. 작업 해석 메모는 체크박스가 아닌 일반 줄 |
| `verify.md` | Summary 표(Completeness / Correctness / Coherence), Issues by Priority(CRITICAL / WARNING / SUGGESTION), Final Assessment |
| `checks/*.py` 등 | 재현·확인 스크립트. 저장소 테스트 대신 여기에 씀 |

spec과 delta spec의 관계는 다음과 같음.

- **메인 spec** (`/openspec/specs/<기능>/spec.md`): 시스템의 현재 동작을 적은 기준 문서. agent가 직접 쓰지 않고 archive가 delta를 병합해서 만듦.
- **delta spec** (change 안의 `specs/`): 이번 change가 바꾸는 부분만 적은 문서. ADDED, MODIFIED, REMOVED, RENAMED 네 섹션이 있음.
- sandbox의 메인 spec은 항상 빈 상태로 시작함. 원본 문서도 기존 프로젝트에 처음 도입할 때 spec을 미리 채우지 말라고 권함.
  - 고칠 기존 요구사항이 없으므로 MODIFIED·REMOVED·RENAMED는 archive에서 "require an existing spec" 오류가 남.
  - 그래서 버그 수정도 고친 동작을 새 요구사항(ADDED)으로 씀.
- `openspec validate`(archive 첫 단계에서도 실행)는 Markdown 형식만 검사함. 코드나 테스트는 실행하지 않음.
  - ERROR 예: 요구사항에 `#### Scenario:`가 없음(`###`로 쓰면 인식 안 됨), delta가 하나도 없음.
  - WARNING 예: 요구사항 문장에 SHALL·MUST가 없음.

## 6. agent에게 주어진 규칙

진입 문서, 단계 문서, CLI 지침에 걸쳐 agent에게 주어지는 규칙을 모으면 아래와 같음.

- **사람이 없음**: 질문하거나 보고하려고 멈추지 않음. 도구 호출 없이 메시지만 내면 그 즉시 세션이 끝나기 때문임(openhands-sdk 동작).
  불명확한 점은 가장 타당한 해석을 골라 해당 산출물에 기록하고 진행함.
- **입력**: issue 본문이 유일한 입력. 본문 속 링크를 열거나 온라인에서 찾아보지 않음.
- **저장소**: apply 단계만 `/testbed`를 수정함.
  - 테스트 파일은 추가·수정하지 않음.
  - README, `docs/`, changelog는 issue가 요구할 때만 수정함.
  - 메모, 요약, 임시 스크립트를 저장소에 남기지 않음.
- **환경**: 패키지 설치와 네트워크 사용 금지.
- **이름과 경로**: change `issue`, 계획 폴더 `/openspec`, 확인 스크립트 `/openspec/changes/issue/checks/`.
- **spec**: 모든 delta는 ADDED. 기능은 New Capabilities로 나열.
- **단계 순서·반복·archive 규칙**: 4절 참고.

## 7. rollout이 끝나면 남는 것

rollout이 끝나면 sandbox는 사라지고, 아래 두 가지가 episode JSON에 남음.

**대화 기록** (`trajectories[0].steps[]`)

- step 하나가 LLM 호출 하나임.
- `model_output`에 agent가 낸 것이 들어 있음: `content`(텍스트), `reasoning`(thinking을 켠 경우), `tool_calls`(`name`과 `arguments`).
  - 터미널 명령은 `name: terminal`, `arguments.command`.
  - 파일 작성은 `name: file_editor`, `arguments.command`가 `create` / `str_replace` / `view` 등, `arguments.path`.
  - 셸 heredoc(`cat > 파일 << 'EOF'`)으로 파일을 쓰는 경우도 흔함.
- 도구 실행 결과는 다음 step의 `chat_completions` 안 `role: tool` 메시지에 있음. 터미널 결과 끝에 종료 코드가 붙음(`[Command finished with exit code N]`).

**수집 산출물** (`artifacts`): agent가 끝난 직후, 채점 테스트가 저장소를 건드리기 전에 harness가 읽어 둠.

| 키 | 내용 |
|---|---|
| `workflow_outputs` | `/openspec` 아래 모든 파일의 경로 → 내용. change 산출물, archive 결과, 메인 spec, 설정, 스키마 포함 |
| `workflow_outputs_skipped` | 총 1MB를 넘어 내용을 담지 못한 파일 목록 |
| `patch`, `patch_base`, `patch_bytes`, `patch_truncated` | 시작 시점 대비 저장소 변경(`git diff`, 새 파일 포함). 채점 테스트가 평가한 그 변경. 1MB 초과분은 잘림 |
| `stray_files` | agent 실행 중 `/tmp`나 `/opsx`에 생기거나 바뀐 파일(이름과 크기만) |
| `workflow` | 워크플로우 이름과 버전 해시(문서·instruction·system prompt·스키마·설정·준비 스크립트 기준) |

- 지금 reward는 숨겨진 테스트 통과 여부(`is_correct`)뿐임. 이 워크플로우에는 준수율 채점기가 아직 없음.
- archive가 성공했으면 산출물은 `.../changes/archive/<날짜>-issue/` 아래에, 실패했거나 안 했으면 `.../changes/issue/` 아래에 있음.

## 8. smoke에서 관찰된 실제 동작

SWE-Gym task 5개 × 1회, Qwen3.5-9B, 150 step 기준 마지막 실행 결과임.
task 수가 적어 경향을 보는 수준이고, 5개 중 기능 요청은 1개(나머지는 버그 수정)임.

| | thinking 끔 | thinking 켬 |
|---|---|---|
| 해결 | 4/5 | 5/5 |
| 진입 문서를 읽음 | 4/5 | 5/5 |
| CLI 절차를 ff부터 따름 | 4/5 | 5/5 |
| 코드 수정 전에 tasks.md까지 작성 (측정 가능한 경우) | 1/2 | 5/5 |
| archive 전에 verify.md 작성 (archive한 경우) | 1/4 | 4/4 |
| archive 성공 | 4/5 | 4/5 |
| 첫 archive가 MODIFIED로 실패 | 0/4 | 0/4 |
| 텍스트만 내고 종료 / 시간 초과 / 네트워크 사용 / 저장소 테스트 수정 | 모두 0 | 모두 0 |
| 사용한 step | 61–102 | 53–83 |

여러 차례 고치면서 보였던 동작과 남은 경향은 아래와 같음.

- 초기에는 CLI가 TTY에서 끝나지 않아 10개 중 9개가 1시간 시간 초과로 끝났음 → 실행 스크립트에 `CI=1`을 넣어 해결.
- spec을 MODIFIED로 쓰는 경향이 강했음(archive한 8개 중 6개가 첫 archive 실패) → 진입 문서 안내만으로는 줄지 않았고, 같은 사실을 설정의 `rules`로 산출물 지침에 붙이자 0으로 줄었음.
- thinking을 끈 agent는 단계 문서를 건너뛰는 경향이 있음.
  - 진입 문서만 읽고 CLI 출력만 따라 archive까지 가거나, verify를 건너뛰고 archive함(마지막 실행에서 4개 중 3개).
  - 문서를 아예 열지 않고 바로 고치는 경우(5개 중 1개), 코드를 먼저 고치고 계획을 나중에 쓰는 경우도 있음.
- 확인 스크립트·임시 파일을 `checks/`가 아니라 `/tmp`에 두는 경우가 흔함(`stray_files`에 나타남). 저장소 밖이라 patch에는 영향 없음.
- 저장소 코드를 `/tmp`의 파이썬 스크립트로 고치는 경우가 있음. 이때 대화 기록에는 파일 편집 도구 호출 없이 터미널 명령만 남음.
- 셸 heredoc의 따옴표가 꼬여 터미널이 입력 대기 상태에 빠진 rollout이 한 번 있었음. 이후 55 step을 중단 키 입력에만 씀. 워크플로우와 무관한 agent 실수임.

## 9. 파일 구성

| 경로 | 내용 |
|---|---|
| `docs/core-workflow.md` | 진입 문서 (직접 작성) |
| `docs/stages/01-ff.md`, `02-apply.md`, `03-verify.md` | 단계 문서. 원본 skill 문서를 `build.py`로 변환한 결과 |
| `sandbox/schemas/spec-driven-sandbox/` | 수정 스키마와 템플릿 4개. `build.py`로 생성 |
| `sandbox/openspec-config.yaml` | `/openspec/config.yaml`로 설치되는 프로젝트 설정 (직접 작성) |
| `setup.sh` | agent 시작 전 sandbox 준비 스크립트 |
| `agent-image-extra.Dockerfile` | agent 이미지에 node와 CLI를 추가하는 줄 |
| `instruction.md`, `system-prompt.j2` | 사용자 메시지 앞 안내, system prompt |
| `build.py` | 원본 → 단계 문서·스키마 변환기. `--list`로 원본 대비 바꾼 곳 전체 목록, `--check`로 생성 결과가 최신인지 확인 |
| `__init__.py` | 워크플로우 등록 정보 |
| `porting/` | 이식 기록: 원본 조사, 어긋나는 지점 목록, 결정 사항, 변경 요약, smoke 결과 |

- 원본 대비 바꾼 이유와 결정 과정은 `porting/03-decisions.md`(결정 표)와 `porting/05-changes.md`(한국어 변경 요약)에 있음.
- smoke 실행별 상세 수치는 `porting/06-smoke.md`에 있음.
- 원본 OpenSpec 문서 중 동작 이해에 도움이 되는 것: `docs/concepts.md`(spec과 delta 개념), `docs/writing-specs.md`(ADDED·MODIFIED 판단 기준), `docs/customization.md`(스키마와 설정), `docs/existing-projects.md`(기존 프로젝트 도입 방침).
