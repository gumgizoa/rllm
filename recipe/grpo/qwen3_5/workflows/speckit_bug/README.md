# speckit_bug: Spec Kit 버그 수정 워크플로우 파이프라인 안내

SWE task(issue 하나를 받아 저장소 코드를 고치는 과제)를 GitHub Spec Kit의 버그 수정 절차로 풀게 하는 rllm 워크플로우임.
이 문서는 파이프라인이 어떻게 구성되고 돌아가는지, rollout이 끝나면 무엇이 남는지를 정리함.
채점 방법은 다루지 않음.

## 1. 한눈에 보기

- 원본: [github/spec-kit](https://github.com/github/spec-kit)의 bug 확장 1.0.1 (commit `0443760`), MIT 라이선스.
- Spec Kit은 원래 사람이 agent 앱(Claude Code 등) 채팅창에 명령을 하나씩 입력하며 쓰는 도구임.
  - 버그 수정은 `/speckit-bug-assess "<버그 설명>" slug=<이름>` → `/speckit-bug-fix` → `/speckit-bug-test` 세 명령으로 진행함.
  - 명령마다 agent가 따를 지침 문서(Markdown)가 있고, 단계가 끝나면 agent가 결과를 보고하고 멈춤.
  - 다음 명령 입력, 질문 답변, 진행 승인은 사람이 함.
- 이 워크플로우는 같은 절차를 사람 없이 한 세션 안에서 끝내도록 바꾼 것임.
  - 명령별 지침 문서를 sandbox 안의 단계 문서로 바꾸고, agent가 순서대로 직접 엶.
  - 사람이 하던 단계 연결·질문 답변·승인은 진입 문서의 규칙으로 대체함.
  - 원본은 test가 실패하면 사람에게 재분석을 권하고 끝나는데, 여기서는 fix ↔ test를 최대 3회 반복하도록 추가함.
- 절차는 **assess → fix → test**. 별도 CLI나 도구 설치가 없고, 모든 산출물은 agent가 직접 쓰는 Markdown 보고서임.
- 원본 이름처럼 버그 수정용이지만, issue를 "해결해야 할 요구사항"으로 다루도록 바꿔서 기능 요청 task도 같은 절차로 진행함.

## 2. sandbox 구성

다른 워크플로우와 같은 openhands-sdk agent 이미지를 씀.
준비 스크립트나 추가 설치는 없고, harness가 지침 문서만 업로드함.

| 경로 | 내용 | 누가 만드나 |
|---|---|---|
| `/testbed` | 고칠 저장소 (SWE-Gym task 이미지에 들어 있음) | task 이미지 |
| `/speckit/` | agent가 읽는 지침 문서: `core-workflow.md`, `stages/01-assess.md`, `02-fix.md`, `03-test.md` | harness 업로드 |
| `/tmp/speckit/bugs/issue/` | agent가 쓰는 보고서 디렉터리. `checks/`에는 확인 스크립트 | agent (`mkdir -p`로 직접 생성) |

- 원본은 보고서를 저장소 안 `.specify/bugs/<slug>/`에 씀.
  - 저장소 안에 두면 patch에 섞이거나 agent의 `git clean`에 지워질 수 있어 `/tmp/speckit/`로 옮김.
- 원본의 slug(버그별 폴더 이름)는 `issue`로 고정함. sandbox에는 버그가 하나뿐이기 때문임.

## 3. agent가 받는 입력

- **system prompt**: openhands-sdk 기본 프롬프트에서 절차 섹션(`<PROBLEM_SOLVING_WORKFLOW>`)만 이 워크플로우용으로 바꾼 것.
  - 요지: "이 세션의 task는 Spec Kit 버그 워크플로우로 푼다. 먼저 `/speckit/core-workflow.md`를 열고, 단계마다 단계 문서를 먼저 연다. 보고서를 쓰면 바로 다음 단계로 간다. 아무도 답하지 않으니 묻지 말고 가정을 기록하고 계속한다."
  - 나머지 섹션(도구 사용 규칙 등)은 기본 그대로임.
- **사용자 메시지 1개**: 앞에 워크플로우 안내(`instruction.md`), 뒤에 SWE-Gym task 본문.
  - 안내 요지: "Spec Kit 버그 워크플로우(assess, fix, test)로 푼다. 먼저 `/speckit/core-workflow.md`를 연다. 단계마다 그 단계 문서를 먼저 연다."
  - task 본문은 SWE-Gym 기본 프롬프트에서 자체 6단계 절차를 뺀 버전(`swegym293_aidlc` 데이터셋)을 씀. 절차가 두 개면 agent가 워크플로우를 무시하는 경향이 있었기 때문임.
  - issue는 `<issue_description>` 태그 안에 있음.
- **도구**: openhands-sdk의 터미널, 파일 편집기, task tracker 세 가지.
- **step 예산**: 150 (설정에 따라 다름). 대화 압축(condenser)은 쓰지 않음.

## 4. 진행 흐름

```
assess  ──►  fix  ──►  test  ──►  finish
(분석)       (수정)     (검증)
              ▲          │
              └─ partial / failed ─┘  (fix ↔ test 최대 3회)
```

agent는 진입 문서 `/speckit/core-workflow.md`를 읽고, 단계마다 해당 단계 문서를 열어 따름.
각 단계 문서의 끝이 "다음 단계 문서를 열어 계속"으로 되어 있어 사람 없이 이어짐.

| 단계 | 하는 일 | 저장소 수정 | 남기는 것 |
|---|---|---|---|
| assess (1회) | issue를 읽고 증상 정리, 의심 코드 경로 탐색, 원인 가설과 수정 방안 작성 | 안 함 | `assessment.md` |
| fix (회차마다) | 수정 방안대로 코드 수정, 확인 스크립트 작성, 관련 테스트 실행 | **함** | `fix.md` → `fix-2.md` → `fix-3.md`, `checks/*` |
| test (회차마다) | 재현 단계·확인 스크립트·관련 테스트를 실행해 결과 판정 | 안 함 | `test.md` → `test-2.md` → `test-3.md` |

단계 사이 규칙은 아래와 같음.

- test 보고서의 **Result**가 다음을 결정함.
  - `verified`: 워크플로우 종료.
  - `partial` 또는 `failed`이고 1·2회차: 그 보고서를 새 근거로 삼아 다음 회차 fix로 감.
  - 3회차: 결과와 무관하게 종료.
- 2·3회차 fix는 이전 회차의 fix 보고서와 test 보고서를 모두 읽고 시작함.
- assess가 틀렸음을 fix 중에 알게 되면 `assessment.md`는 고치지 않고, fix 보고서의 **Deviations from Assessment**에 기록한 뒤 바뀐 원인 기준으로 계속함.
- 마지막에 `finish` 도구를 호출해 세션 종료.

## 5. 산출물 형식

모든 보고서는 `/tmp/speckit/bugs/issue/` 아래에 있고, 각 보고서는 한 번만 씀(이전 회차 보고서를 고쳐 쓰지 않음).
보고서 맨 위의 `- **필드**: 값` 줄과 `##` 헤딩 구조는 단계 문서가 정한 그대로 유지하게 되어 있음.

| 파일 | 머리 필드 | 본문 섹션 |
|---|---|---|
| `assessment.md` | Slug, Created, Source, **Verdict** (`valid` / `likely valid, needs reproduction`), **Severity** (`critical` / `high` / `medium` / `low`) | Report, Symptom, Reproduction, Suspected Code Paths, Root Cause Hypothesis, Proposed Remediation(Files likely to change, Checks to run 포함), Risks & Considerations, Open Questions |
| `fix.md`, `fix-2.md`, `fix-3.md` | Slug, Fixed, Assessment, **Round** (1/2/3), Previous verification, **Status** (`applied` / `partial` / `not-applied`) | Summary, Changes(표), Diff Highlights, Checks Added, Local Verification, Deviations from Assessment, Follow-ups |
| `test.md`, `test-2.md`, `test-3.md` | Slug, Tested, Assessment, Fix, **Round**, **Result** (`verified` / `partial` / `failed`) | Summary, Checks Performed(표: 재현·추가 확인·회귀 테스트·lint 각각 pass / fail / skipped / not-run), Output Excerpts, Residual Risks, Recommendation |
| `checks/*` | — | 재현·확인 스크립트. 저장소 테스트 대신 여기에 씀 |

- 원본의 판정 중 `invalid`(버그 아님)는 없앰. issue는 항상 해결해야 할 요구사항으로 다룸.
- 실제로 수행하지 않은 확인은 `verified`로 쓰지 않고 `partial`로 낮추라는 원본 규칙은 그대로임.
- 보고서 형식을 검사하는 도구는 없음. 형식이 지켜졌는지는 보고서 내용으로만 알 수 있음.

## 6. agent에게 주어진 규칙

진입 문서와 단계 문서에 걸쳐 agent에게 주어지는 규칙을 모으면 아래와 같음.

- **사람이 없음**: 질문하거나 보고하려고 멈추지 않음. 도구 호출 없이 메시지만 내면 그 즉시 세션이 끝나기 때문임(openhands-sdk 동작).
  - 모호한 부분은 가장 타당한 해석으로 진행하고 그 가정을 보고서에 기록함.
  - 원본의 "확인이 안 되면 멈춤", "비용이 큰 검사는 동의를 받고 실행" 같은 분기는 모두 이 규칙으로 바뀜.
- **입력**: issue 본문이 유일한 입력. 본문 속 링크를 열거나 온라인에서 찾아보지 않음(원본은 github.com 등은 묻지 않고 가져오게 되어 있었으나 정답 PR 유출 경로라 금지함).
- **저장소**: fix 단계만 `/testbed`를 수정함.
  - 테스트 파일은 추가·수정하지 않음. task가 테스트를 이미 준비해 두었다고 하기 때문임.
  - 보고서, 확인 스크립트, 임시 파일을 저장소에 쓰지 않음.
- **테스트 실행**: 파괴적이거나 네트워크가 필요한 검사만 `skipped`로 둘 수 있음. 변경된 모듈의 저장소 테스트는 실행 대상임.
- **이름과 경로**: slug `issue`, 보고서 `/tmp/speckit/bugs/issue/`, 확인 스크립트 `/tmp/speckit/bugs/issue/checks/`.
- **단계 순서와 반복**: 4절 참고.

## 7. rollout이 끝나면 남는 것

rollout이 끝나면 sandbox는 사라지고, 아래 두 가지가 episode JSON에 남음.

**대화 기록** (`trajectories[0].steps[]`)

- step 하나가 LLM 호출 하나임.
- `model_output`에 agent가 낸 것이 들어 있음: `content`(텍스트), `reasoning`(thinking을 켠 경우), `tool_calls`(`name`과 `arguments`).
  - 터미널 명령은 `name: terminal`, `arguments.command`.
  - 파일 작성은 `name: file_editor`, `arguments.command`가 `create` / `str_replace` / `view` 등, `arguments.path`.
  - 셸 heredoc(`cat > 파일 << 'EOF'`)으로 보고서를 쓰는 경우도 흔함.
- 도구 실행 결과는 다음 step의 `chat_completions` 안 `role: tool` 메시지에 있음. 터미널 결과 끝에 종료 코드가 붙음.

**수집 산출물** (`artifacts`): agent가 끝난 직후, 채점 테스트가 저장소를 건드리기 전에 harness가 읽어 둠.

| 키 | 내용 |
|---|---|
| `workflow_outputs` | `/tmp/speckit` 아래 모든 파일의 경로 → 내용. 보고서와 확인 스크립트 |
| `workflow_outputs_skipped` | 총 1MB를 넘어 내용을 담지 못한 파일 목록 |
| `patch`, `patch_base`, `patch_bytes`, `patch_truncated` | 시작 시점 대비 저장소 변경(`git diff`, 새 파일 포함). 채점 테스트가 평가한 그 변경. 1MB 초과분은 잘림 |
| `stray_files` | agent 실행 중 `/tmp`(`/tmp/speckit` 제외)나 `/speckit`에 생기거나 바뀐 파일(이름과 크기만) |
| `workflow` | 워크플로우 이름과 버전 해시(문서·instruction·system prompt 기준) |

- 지금 reward는 숨겨진 테스트 통과 여부(`is_correct`)뿐임. 이 워크플로우에는 준수율 채점기가 아직 없음.
- 아래 8절의 smoke는 산출물 수집 기능이 들어오기 전에 돌린 것이라, 그 episode들에는 `workflow_outputs`가 없음.

## 8. smoke에서 관찰된 실제 동작

SWE-Gym task 5개 × 1회, Qwen3.5-9B, 150 step 기준임(2026-10-12).
task 수가 적어 경향을 보는 수준이고, 5개 모두 워크플로우 없이도 base 모델이 풀던 task라 해결률 차이는 볼 수 없음.

| | thinking 끔 | thinking 켬 |
|---|---|---|
| 해결 | 5/5 | 5/5 |
| 워크플로우를 순서대로 따름 (진입 문서 → 코드 수정 전 assessment → fix → test) | 2/5 | 2/5 |
| 보고서는 썼지만 코드를 다 고친 뒤 몰아서 작성 | 1/5 | 1/5 |
| 진입 문서를 끝내 읽지 않음 | 2/5 | 2/5 |
| 진입 문서를 처음 올바르게 읽은 step (중앙값) | 6 | 2 |
| 사용한 step | 55–114 | 25–74 |
| 텍스트만 내고 종료 / 네트워크 사용 | 0 / 0 | 0 / 0 |
| 저장소에 남긴 파일 | `IMPLEMENTATION_SUMMARY.txt` 1건 | 임시 `test_issue.py` 1건(나중에 삭제) |
| fix ↔ test 2회차 이상 | 0 (모두 1회차에 `verified`) | 0 |

관찰된 동작과 남은 한계는 아래와 같음.

- 진입 문서를 읽지 못한 경우의 주된 원인은 경로 오해였음(10개 중 3개).
  - 저장소를 먼저 탐색한 뒤 늦게 문서를 찾으면서 `/speckit/core-workflow.md`를 `/testbed/speckit/...`로 찾고, 없자 워크플로우 없이 바로 풂.
  - 같은 설정의 AI-DLC 워크플로우(SWE-bench Verified 499개)에서도 같은 실수로 문서를 못 찾은 비율이 thinking 끔 3.8%, 켬 6.2%였음.
  - AI-DLC는 약 90%가 첫 step에 문서를 열었는데, 이 워크플로우는 중앙값 2~6 step으로 늦었음.
  - 이 문제에 대한 대응(첫 행동을 더 구체적으로 지시, `/speckit`이 저장소 밖임을 명시)은 아직 반영하지 않음.
- 진입 문서가 저장소에 파일을 남기지 말라고 하지만, 요약 파일이나 임시 테스트 파일을 저장소에 만든 경우가 있었음.
- fix ↔ test 반복은 한 번도 실행되지 않아 실제 동작이 확인되지 않음.
- 비교를 위해 같은 task와 설정으로 돌린 OpenSpec 워크플로우(`openspec_ff`) 결과는 그 폴더의 README에 있음.

## 9. 파일 구성

| 경로 | 내용 |
|---|---|
| `docs/core-workflow.md` | 진입 문서 (직접 작성) |
| `docs/stages/01-assess.md`, `02-fix.md`, `03-test.md` | 단계 문서. 원본 명령 문서 3개(634줄)를 `build.py`로 변환한 결과(319줄) |
| `instruction.md`, `system-prompt.j2` | 사용자 메시지 앞 안내, system prompt |
| `build.py` | 원본 → 단계 문서 변환기. `--list`로 원본 대비 바꾼 곳 전체 목록, `--check`로 생성 결과가 최신인지 확인 |
| `__init__.py` | 워크플로우 등록 정보 (문서 `/speckit`, 수집 경로 `/tmp/speckit`) |
| `LICENSE-spec-kit` | 원본 MIT 라이선스 |
| `porting/` | 이식 기록: 결정 사항(`03-decisions.md`), 변경 요약(`05-changes.md`), smoke 결과(`06-smoke.md`) |

- 원본에서 줄어든 315줄 중 216줄은 이 환경에서 아무 동작도 하지 않는 확장 hook 검사 섹션임.
- 원본 대비 바꾼 이유와 결정 과정은 `porting/03-decisions.md`(결정 표)와 `porting/05-changes.md`(한국어 변경 요약)에 있음.
- 이 워크플로우는 단계별 이식 절차가 정리되기 전에 만들어져 원본 조사와 어긋나는 지점 목록 문서가 따로 없음.
- 원본 Spec Kit 문서 중 참고할 것: 저장소 `README.md`(사용법), `extensions/bug/README.md`(bug 확장 설명), `spec-driven.md`(방법론).
