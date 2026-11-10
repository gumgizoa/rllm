# Changes: bmad_build_auto  (upstream bmad-code-org/BMAD-METHOD@10db8f35 = v6.12.2, skill `bmad-build-auto`: step-01 clarify-and-route → step-02 plan → step-03 implement → step-04 review → HALT)

원문 링크 접두사 `U/` = `https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/`.
`IA` = `/tmp/bmad/implementation-artifacts/`, `spec_file` = `IA/spec-<slug>.md`, `diff_file` = `/tmp/bmad/diff/<slug>.diff`.
이 단계(4a)는 패키지(문서·instruction·system prompt·등록·테스트)까지다. `constraints.yaml`·`reward/`(rubric, layers)·채점기의 대화 분리는 4b, 러너의 도구 플래그는 하네스 작업으로 따로 간다.

## 계획 대비 달라진 점

| # | 항목 | 계획(03-plan.md) | 실제 구현 | 이유 |
|---|---|---|---|---|
| 1 | 서브에이전트 도구 | `delegate` 도구: `spawn` 으로 id(implementer, 렌즈 4개)를 등록한 뒤 `delegate` 로 작업을 넘김; 렌즈 4개 = spawn 4 id + delegate 한 번 | openhands-sdk/tools 1.42.1 이 LLM 에 노출하는 서브에이전트 도구는 **`task`** 하나(`openhands/tools/task/definition.py`; `openhands/tools/delegate` 에는 등록된 도구가 없음). 인자 `prompt`(전체 과제 텍스트), `subagent_type`(기본 `general-purpose`), `resume`(이전 Task ID → 같은 서브에이전트 대화 계속). 결과는 `Task ID: task_…` / `Subagent:` / `Status:` 뒤에 서브에이전트의 마지막 메시지. id 는 도구가 배정하므로 "spawn 으로 고른 id" 는 없다. 구현자 = `task` 1회(핸드오프 문장이 prompt), 렌즈 4개 = 한 턴에 `task` 4회(렌즈마다 customize.toml 지시가 prompt), patch = `resume`=구현자 Task ID 로 `task` | 조정자 정정(2026-11-10). 원문의 "한 메시지에 모두 띄우고 전부 기다린다" 는 "한 턴에 `task` 4회, 턴은 전부 돌아온 뒤 재개" 로 맞아떨어진다. SDK 의 `tool_concurrency_limit` 기본값 1 이라 4회는 순차 실행된다(한 턴 안에서) — "동시" 라고 쓰지 않고 "한 번에 띄워 모두 기다린다" 로 적음 |
| 2 | 진입 문서의 출처 | `core-workflow.md` 를 새로 작성 | upstream `workflow.md` 를 **변환**한 것이 `core-workflow.md`: HALT 프로토콜(folder+id 분기·on_complete 삭제), Subagents 규칙, READY 표준, Conventions, Workflow Execution, First Step 은 원문 그대로이고, `## On Activation`(훅 3개, 전부 `_None._`) 자리에 직접 쓴 **`## The setting of this run`**(단계 표, 의도 정의, 답할 사람 없음, 산출물 경로, `task` 도구, 실패 기록 규칙, 채점 대상, 읽는 순서, 종료)을 넣음 | 원문에 이미 진입 문서가 있다. 그 본문(HALT·READY 표준·서브에이전트 규칙)은 step-02 가 다시 읽는 문서라 손으로 바꿔 쓰기보다 태그 편집으로 남기는 것이 skill 규칙 4 에 맞다. 새로 쓴 것은 설정 절 하나 |
| 3 | spec 파일 소실 HALT | 언급 없음(D-2 의 실패 HALT 5개에 없음) | step-02 READY 게이트의 "If the file is missing: HALT … `planned spec file disappeared before implementation`"(S2:21)과 step-03 PRECONDITION 의 `missing spec_file before implementation`(S3:14)은 4단계에서 원문 그대로 뒀다가 **2026-11-10 삭제** | `02-gaps.md` G12 → 사용자 결정 "빼자"(D-8). build.py semantic edit 2건(step02 불릿, step03 PRECONDITION 절), 규칙 C30·D25 drop. 게이트의 디스크 재독·검증 문장은 유지 |
| 4 | triage 폭포식 문장 | intent_gap 라벨만 제거 | "If neither exists, process patch and defer normally" 의 "neither"(intent_gap·bad_spec 둘) → "Otherwise" | 라벨을 빼면 "둘 다 없으면" 이 틀린 말이 됨. 같은 편집(G81) 안에서 처리 |
| 5 | follow-up pass 문장 | 호출 모드 삭제(G1) 로 뭉뚱그림 | S4:33 "a loopback, a resumed review, or a follow-up pass on a `done` spec" → "a loopback"; S4:103 의 "On a first pass … On a follow-up pass (`{followup_pass}` = `true`) …" 문장 → 첫 패스 규칙만 남김; S2:22 의 `Halt after planning.` 절 삭제 | 모두 `done` spec 재투입·호출자 지시문 전제(G1). 계획의 "약 25곳" 에 포함되는 종류지만 자리를 명시해 둔다 |
| 6 | 문서 수·편집 수 | 문서 9개, 편집 약 60건 | 문서 **10개**(core 1 + stages 4 + spec-template 1 + review-prompts 2 + references 2), 태그 편집 **57건**(2026-11-10 D-8 뒤; env 39 = section 1 + edit 38, semantic 18 = section 1 + edit 17) + 렌더러 토큰 치환 9종(태그 없음) + customize.toml 인라인 2종(핸드오프 1, 렌즈 4) | 9 는 세다 빠뜨린 것. 토큰 치환은 `_port` 의 substitutions 로 처리해 편집 수에 안 들어감 |
| 7 | customize.toml 전개 방식 | "렌더러가 하던 일을 build.py 가 한다" | 핸드오프·렌즈 4개 본문을 `build.py` 상수로 **내장**하고, 빌드마다 체크아웃의 `customize.toml` 을 `tomllib` 로 읽어 상수와 대조(다르면 빌드 실패; 훅 3개·on_complete 가 비어 있지 않아도 실패) | `_port` 의 Edit 는 정적 문자열이라 다른 파일을 끌어올 수 없음. 대조로 상류 변경이 드러나게 함 |
| 8 | 러너 플래그 값 | `OPENHANDS_SDK_EXTRA_TOOLS=delegate` | `runner_env={"OPENHANDS_SDK_EXTRA_TOOLS": "task"}` (`__init__.py`; `WorkflowSpec.runner_env` 는 하네스 쪽에서 같은 날 추가됨) | #1 과 같음 |
| 9 | 원문 유지 중 결정 밖 문장 | 언급 없음 | 유지: Subagents 절의 "(e.g. `run_in_background: true`)" 와 "await a completion notification", step-03/04 의 `NO_VCS` 분기("if version control is unavailable"), 핸드오프의 "Load every file listed in its frontmatter `context:`"(spec-template 의 `context: []` 와 함께), step-03 의 Path formatting rule | 해로울 것 없는 원문이고 삭제 결정이 없음(원칙 2). `context:` 는 D-1 이 G3 규칙으로 '채점 제외' 했을 뿐 문장 삭제를 정한 것은 아니라고 읽음 — 비면 무동작 |

## 구성 (`recipe/grpo/qwen3_5/workflows/bmad_build_auto/`)

| 파일 | 출처 | 내용 |
|---|---|---|
| `docs/core-workflow.md` | BMAD-METHOD `workflow.md` 원문을 변환 + 설정 절 직접 작성 | 진입 문서: HALT 프로토콜, 서브에이전트 규칙, READY 표준, Conventions, **The setting of this run**(단계 표·의도·경로·`task` 도구·실패 기록·채점 대상·읽는 순서·종료), 첫 단계 링크 (원문 104줄 → 76줄) |
| `docs/stages/step-01-clarify-and-route.md` … `step-04-review.md` | BMAD-METHOD 원문을 변환 | 단계별 절차 (84 → 28, 27 → 25, 48 → 51, 116 → 156줄; step-04 는 customize.toml 의 렌즈 4개가 본문으로 들어와 늘어남) |
| `docs/spec-template.md` | BMAD-METHOD 원문을 변환 | spec 양식; `{project-root}` 토큰만 `/testbed` 로 (96 → 96줄) |
| `docs/review-prompts/edge-case-hunter.md`, `verification-gap.md` | BMAD-METHOD 원문을 변환 | 리뷰 서브에이전트 2종의 지시문; edge-case-hunter 의 references 참조 3곳만 절대경로로 (112 → 109, 113 → 113줄) |
| `docs/references/claims-check.md`, `deletion-check.md` | BMAD-METHOD 원문 그대로(변환기 경유, 편집 0) | edge-case-hunter 의 4·5단계 보조 패스 (14, 14줄) |
| `build.py` | 직접 작성 | 원문 → docs 변환기(`workflows/_port.py` 위). 편집마다 태그(env / semantic)와 gap·결정 ID; customize.toml 값 내장 + 대조; `--list`, `--check` |
| `instruction.md` | 직접 작성 | 첫 행동 = `/bmad-build-auto/core-workflow.md` 읽기, 디렉터리는 파일시스템 루트(/testbed 밖). 다른 워크플로우와 다른 문장 |
| `system-prompt.j2` | SDK 기본 프롬프트 복사 | `<PROBLEM_SOLVING_WORKFLOW>` 절만 새로 작성(진입 문서·단계 연쇄·`task` 도구·답할 사람 없음·finish), 나머지 15개 절은 SDK 기본과 동일 |
| `__init__.py`, `LICENSE-bmad-method` | — | SPEC(container_dir `/bmad-build-auto`, entry_doc `core-workflow.md`, output_dirs `("/tmp/bmad",)`, runner_env `OPENHANDS_SDK_EXTRA_TOOLS=task`, scorer 없음); MIT 라이선스 + 상표 고지 |
| `porting/01-survey.md`, `01b-rules.md`, `rules.yaml`, `02-gaps.md`, `03-decisions.md`, `03-plan.md`, `05-changes.md` | 단계별 기록 | 조사·규칙 인벤토리·gap·결정·계획·변경 |
| `../../tests/test_bmad_build_auto.py` | 직접 작성 | 빌드 일치, 재문구·잔존 문구·절 누락 실패, 태그·ID, 상호 참조, 금지 문구, 산출물 경로, 결정 반영, `task` 서술 일관성, 손글 문장 고유성, 하네스 인식 |

## 수정한 내용

### 각 단계 수행 방식 변화

| Before (upstream bmad-build-auto, Claude Code 등 서브에이전트가 되는 도구) | After (rllm) |
|---|---|
| 1. **사람**이 `_bmad/` 를 설치(config.toml, render_skill.py, uv)하고 저장소를 깨끗한 트리·알맞은 브랜치로 둡니다.<br>2. **사람**이 채팅에 `bmad-build-auto <의도>` 를 넣습니다.<br>3. **agent 앱**이 SKILL.md 를 불러오고, agent 가 `uv run render_skill.py` 를 한 번 실행해 스냅샷 `R/` 을 만든 뒤 `R/workflow.md` → `step-01` → … 를 읽어 따릅니다.<br>4. agent(LLM)가 지침을 읽고 작업합니다.<br>  • step-01: 의도·VCS 점검, 기존 spec/stories 분기, 의도 불명확이면 `blocked` HALT.<br>  • step-02: 조사(깊은 탐색은 서브에이전트), spec 작성, READY 게이트, intent gap 이면 `blocked` HALT.<br>  • step-03: 구현 **서브에이전트**에 핸드오프, 임시 파일에 diff 생성, Verification 실행, matrix 감사.<br>  • step-04: 리뷰 **서브에이전트 4개** 동시 실행, triage, intent_gap/bad_spec/patch/defer 라우팅, 루프백.<br>5. HALT: spec 에 status·Auto Run Result 를 쓰고 리뷰된 diff 를 **로컬 커밋**, 트리가 깨끗한지 확인. 사람은 끝에서 결과를 받습니다. | 1. 처음 받는 task 메시지가 의도를 대신합니다(SWE task 본문의 issue + instruction). 문서 10개는 sandbox 의 `/bmad-build-auto/`(저장소 밖)에 미리 올라가 있고, 렌더 토큰은 build 때 치환돼 있습니다. 러너는 Terminal·FileEditor·TaskTracker 에 **`task` 도구**를 더해 띄웁니다(이 workflow 만).<br>2. agent 가 첫 행동으로 `/bmad-build-auto/core-workflow.md` 를 읽고, `stages/step-01…04.md` 를 차례로 엽니다.<br>3. agent(LLM)가 지침을 읽고 작업합니다.<br>  • step-01: VCS 점검·기존 spec 분기·의도 불명확 HALT 없음. slug 를 정하고 `spec_file` = `IA/spec-<slug>.md`, `diff_file` = `/tmp/bmad/diff/<slug>.diff` 로 고정.<br>  • step-02: 조사(깊은 탐색은 서브에이전트에 맡겨도 됨), spec 작성, READY 게이트; intent gap 항목 없음; 기준 미달이면 `status: blocked` 기록 후 진행.<br>  • step-03: `task`(prompt = 핸드오프 문장) 1회 → 돌아오면 diff 를 `diff_file` 에 쓰고 Verification·matrix 감사; 실패해도 기록 후 진행. 단위 테스트는 **저장소 테스트 파일**에 추가(원문).<br>  • step-04: 한 턴에 `task` 4회(렌즈마다 지시 전문이 prompt) → 결과를 Triage Log 에 옮겨 verdict·route(bad_spec/patch/defer); bad_spec 이면 되돌리고 spec 고쳐 step-03 부터(상한 5, 초과 시 기록 후 Finalize); patch 는 `resume`=구현자 Task ID 로 `task`; intent_gap 라우트는 없음.<br>4. HALT: spec 에 status(`done`, 또는 기록된 `blocked`)·Auto Run Result 를 쓰고 **멈춥니다**. 커밋 없음; 작업 트리의 diff 가 채점 대상입니다. |

### 수정 사항

| # | 범주 | 내용 |
|---|---|---|
| 1 | **사람 피드백이 필요한 부분 삭제** | 원문에 질문 지점은 없다(무인 설계). 의도 관련 "멈춤" 5곳을 삭제, 대체 문장 없음: 의도 불명확(S1:42), 의도 미확정(S1:73 뒷절; "Do not fantasize or leave open questions" 는 유지), intent gap 항목(S2:14 전체), matrix 모호(S3:44 절), triage intent_gap 라우트(S4:71)와 라벨(S4:49·56-59·67·70). |
| 2 | **보고 후 멈춤 → 다음 단계로 진행** | 실패 HALT 5곳(S2:23 READY 미달, S3:40 검증 실패, S3:44 matrix 감사 실패, S4:70 루프 상한, S4:83 patch 검증 실패)을 "`status: blocked` + 사유를 frontmatter·`## Auto Run Result` 에 기록하고 계속" 으로. Finalize 는 기록된 `blocked` 를 최종 status 로 유지. 각 step 끝의 `Read fully and follow …` 는 포트 경로로 유지(원문과 같음). |
| 3 | **이름·경로 고정** | `{{.implementation_artifacts}}` → `/tmp/bmad/implementation-artifacts`; `{diff_file}`(임시 파일) → `/tmp/bmad/diff/<slug>.diff`(step-01 에서 정함); `[[bmad-snapshot:*]]`·`{skill-root}` → `/bmad-build-auto/…`(`workflow.md` → `core-workflow.md`); `{project-root}` → `/testbed`; 언어 토큰 3종 → "Write files in English"; edge-case-hunter 의 `references/*.md` 3곳 → 절대경로. |
| 4 | **실행 환경 구성** | build.py 가 render_skill.py 를 대신해 토큰을 치환하고 customize.toml 의 핸드오프·렌즈 4개를 본문에 넣음(값은 내장, 체크아웃과 대조); 문서 10개를 `/bmad-build-auto/` 에 업로드; `output_dirs=("/tmp/bmad",)`; `runner_env` 로 `OPENHANDS_SDK_EXTRA_TOOLS=task`(러너의 도구 목록 플래그는 하네스 작업). |
| 5 | **agent 앱 전용 요소 삭제** | SKILL.md 의 `uv run render_skill.py` 단계(문서로 쓰지 않음), 활성화 훅 prepend/persistent_facts/append 와 `on_complete`(모두 비어 있음), `customize.toml` 오버라이드·skip 레이어·"customized instruction" 문장, "서브에이전트 못 쓰면 `no subagents` HALT", `{skill-root}` 전개 지시, step-01 frontmatter 의 런타임 변수 4개. 서브에이전트 호출 문장은 원문 유지하고 `task` 도구와의 대응을 core-workflow.md 설정 절과 step-03/04 에 한 문장씩 덧붙임. |
| 6 | **SWE task 조건에 맞춤** | VCS 점검·`git add --refresh`·브랜치 확인(S1:74), 핸드오프 충돌 HALT(S3:26), Finalize 의 로컬 커밋과 clean 확인(S4:109-116) 삭제; "커밋·stash·clean 금지, 작업 트리가 채점 대상" 명시. `baseline_revision` = HEAD 기록은 원문 유지. 테스트는 저장소 테스트 파일(원문 유지). |
| 7 | **절차 구조 변경** | intent_gap 라우트 삭제로 triage 범주가 bad_spec/patch/defer 셋, 폭포식은 "bad_spec 있으면 나머지 무의미, 아니면 patch·defer". 그 밖의 라우팅·루프백·되돌리기·상한 5·patch 재호출 메시지는 원문 그대로. step-01 항목 번호 1-4, step-02 항목 번호 1-4 로 당김. |
| 8 | **환경 사실 명시** | core-workflow.md 설정 절: 의도 = task 메시지(issue), 계획 문서·epic·stories·기존 spec 없음 → 항상 freeform 경로; 질문할 사람 없음(텍스트만 보내면 세션 종료); 산출물·diff 위치와 디렉터리 생성; `task` 도구의 인자·결과 형식·`resume`·서브에이전트의 도구와 한계; 실패 기록 규칙; 채점 대상 = 작업 트리; 읽는 순서; 종료(HALT 뒤 `finish`). step-01 항목 1 에 "계획 산출물 없음 → freeform" 을 한 번 더. |
| 9 | **harness·데이터셋 설정** | `workflows/__init__.py` 등록; system prompt 절차 절 새로 작성; `tests/test_bmad_build_auto.py`. 평가용 `constraints.yaml`·`reward/rubric.yaml`·`reward/layers.yaml` 과 채점기의 대화 분리는 **4b 로 이월**(SPEC 은 scorer 없음 → resolve rate 만). |
| 10 | **범위·방식 결정** | 호출 모드 셋 중 freeform 만(기존 spec 재개·folder+id 삭제), epic 경로·epic 컴파일·`compile-epic-context.md` 삭제, skill level 삭제, follow-up pass·`Halt after planning.` 삭제, 커스텀 리뷰 레이어 오버라이드 삭제. |
| 11 | **원문 유지** | 구현·리뷰의 서브에이전트 분업과 네 렌즈의 지시 전문; 리뷰어 지시 문서 2종과 references 2종(참조 경로 외 그대로); spec-template 전체(I/O Matrix·edge case 단위 테스트 task, `context: []` 포함); READY 표준과 게이트의 1회 수선·재독; Triage Log·Auto Run Result 형식과 합계 규칙; bad_spec 되돌리기·KEEP·Spec Change Log·상한 5; patch 재호출 메시지 전문; defer frontmatter 규칙; 1600 토큰 oversized 경고; "No human interaction"; Subagents 절의 "한 메시지에 모두, 백그라운드 금지"; `NO_VCS` 분기; Path formatting rule; spec 소실 HALT 2곳(G12 open). |

**적용 위치** (범주와 별개)
- **단계 문서 편집**: `build.py` 가 upstream `workflow.md`, `step-01…04.md`, `review-prompts/edge-case-hunter.md` 를 변환할 때 태그 편집 57건(env 39, semantic 18 — D-8 의 G12 2건 포함; `--list`). 범주 1, 2, 3, 5, 6, 7, 10
- **렌더러 토큰 치환**: substitutions 9종(snapshot 참조 6, `{skill-root}`, `{{.implementation_artifacts}}`, `{project-root}`) + customize.toml 인라인(핸드오프 → step-03, 렌즈 4 → step-04). 범주 3, 4
- **환경 파일**: `__init__.py`(container_dir, entry_doc, output_dirs, runner_env), `LICENSE-bmad-method`. 범주 4
- **새로 작성**: core-workflow.md 의 설정 절, instruction.md, system prompt 절차 절, 테스트. 범주 8, 9 와 범주 1·2 의 규칙 설명

## agent 행동 변화

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | 활성화 | `uv run … render_skill.py` 로 스냅샷 생성, 실패 시 HALT ([SKILL.md#L6-L13](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/SKILL.md#L6-L13)) | **원래 행동 삭제**: 첫 행동은 `/bmad-build-auto/core-workflow.md` 읽기; 토큰은 build 때 치환 | uv·설치물 없음 (G7, G5) | 불가 (렌더러 없음) |
| 2 | step-01 | `git add --refresh -- .` 후 clean·브랜치 확인, 아니면 HALT ([step-01#L74](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md#L74)) | **원래 행동 삭제** | 샌드박스 트리는 깨끗하고 브랜치는 과제가 정함 (D-1) | 가능하지만 index 를 건드림 |
| 3 | step-01 | 의도 불충분이면 `unclear intent` HALT, 확정 못 하면 미해결 질문으로 HALT ([#L42](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md#L42), [#L73](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md#L73)) | **원래 행동 삭제**: 두 문장을 지우고 대체하지 않음 | 평가 데이터 SWE-bench Verified 는 명확한 이슈만 (D-2) | 가능 (문장 복원) |
| 4 | step-02 | intent gap 이면 해석을 고르지 말고 `intent gap` HALT ([step-02#L14](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-02-plan.md#L14)) | **원래 행동 삭제**: 항목 전체 삭제, 대체 없음 | 같음 (D-2) | 가능 (문장 복원) |
| 5 | step-02 | READY 미달: 한 번 수선·재독, 그래도 미달이면 HALT ([step-02#L23](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-02-plan.md#L23)) | **새 행동 추가**: 수선·재독은 유지, 미달이면 `status: blocked` + 실패 기준을 기록하고 **step-03 으로 진행** | 결과물 없는 종료 방지 (D-2 확정 기본값) | 가능 (즉시 종료) |
| 6 | step-03 | "Launch a subagent with no prior conversation context, with this prompt: …" ([customize.toml#L39-L45](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/customize.toml#L39-L45)) | **원문 유지, 도구 지정**: `task` 1회, prompt = 핸드오프 문장(spec 경로 치환), `subagent_type` = general-purpose; 돌아온 Task ID 를 보관 | 서브에이전트 유지 결정 (D-7); SDK 의 도구가 `task` | 해당 없음 (같은 행동) |
| 7 | step-03 | diff 를 "a uniquely-named file in the system temp directory" 에 ([step-03#L38](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-03-implement.md#L38)); 검증·matrix 감사 실패면 HALT, matrix 행 모호면 HALT ([#L40](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-03-implement.md#L40), [#L44](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-03-implement.md#L44)) | diff 는 `/tmp/bmad/diff/<slug>.diff` 에; 검증·감사 실패는 `status: blocked` + 사유 기록 후 **step-04 로 진행**; matrix 모호 분기는 삭제(코드를 고친다는 앞절만 남음) | 채점기가 diff 파일을 읽어야 함 (D-5); 결과물 없는 종료 방지 (D-2) | 경로는 가능; HALT 는 가능(즉시 종료) |
| 8 | step-04 | "Spawn every reviewer subagent before reading or reacting to any of their output" ([step-04#L25](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L25)); 렌즈마다 "Launch a context-free subagent with this prompt" ([customize.toml#L58](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/customize.toml#L58)) | **원문 유지, 도구 지정**: 한 턴에 `task` 4회(렌즈 지시 전문이 prompt); 턴은 넷이 다 돌아온 뒤 재개; 각 결과(마지막 메시지)를 triage 입력으로 | 서브에이전트 유지 (D-7); "한 메시지에 모두 띄운다" = 한 턴에 4회 | 해당 없음 |
| 9 | step-04 | intent_gap 라우트: patch 파일 저장·되돌리기·HALT ([step-04#L71](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L71)); 정의·형식·폭포식의 intent_gap ([#L49](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L49), [#L57-L59](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L57-L59), [#L67](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L67), [#L70](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L70)) | **원래 행동 삭제**: 라우트와 라벨을 지움; 범위 밖 판단은 bad_spec 으로, patch 조건 미달은 bad_spec 으로 | 발동 조건 없음 (D-2); 되돌리면 patch 없음 | 불가 (되돌리면 patch 없음) |
| 10 | step-04 | bad_spec: 되돌리고 spec 고쳐 step-03 재도출; 상한 5 초과면 HALT ([step-04#L70-L72](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L70-L72)) | **원문 유지**(되돌리기·KEEP·재도출·상한 5); 상한 초과만 `status: blocked` 기록 후 **Finalize 로 진행** | 루프·되돌리기 유지 (D-4), 종료 방지 (D-2) | 상한 HALT 만 가능 |
| 11 | step-04 | patch: "Re-engage the step-03 implementation subagent — the same one, addressed by the name or id its launch returned" ([step-04#L73-L83](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L73-L83)); patch 검증 실패면 HALT | **원문 유지, 도구 지정**: `task` 에 `resume` = 구현자 Task ID, prompt = 원문 메시지; 검증 실패는 `status: blocked` 기록 후 패스를 마저 끝냄 | D-7, D-2 | HALT 만 가능 |
| 12 | HALT | 리뷰된 diff 를 커밋, clean 확인, 아니면 `finalization left repository dirty` HALT ([step-04#L109-L116](https://github.com/bmad-code-org/BMAD-METHOD/blob/10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8/src/bmm-skills/ship/bmad-build-auto/step-04-review.md#L109-L116)) | **원래 행동 삭제**: 커밋·clean 확인 없음; `done`(또는 기록된 `blocked`) 로 HALT, Auto Run Result 작성 후 종료 | 작업 트리 diff 가 채점 대상 (D-1) | 불가 (정반대) |

**표에서 뺀 것**: 경로·토큰 치환(D-5), 언어 English, 호출 모드·기존 spec·stories·epic 경로·follow-up pass·`Halt after planning.` 삭제(G1·G3; 발동 조건 없음), skill level, `no subagents` HALT 삭제(도구 있음), 핸드오프 충돌 HALT 삭제(고정 문장), 활성화 훅 `_None._`, 커스텀 리뷰 레이어 오버라이드, `on_complete`, 항목 번호 당김.

**새 행동 추가 행(5, 7, 10, 11 의 기록 후 진행)은 6단계 smoke 에서 발생을 확인할 것**; 발생하지 않으면 그 자체가 소견이다. 도구 지정 행(6, 8, 11)은 `task` 호출 성공률·Task ID 보관·`resume` 사용을 본다.

## 변경

**1. 활성화·렌더러 삭제** (core-workflow.md, 모든 docs)
- 원문은 SKILL.md 가 `uv run render_skill.py` 를 한 번 실행해 토큰을 치환한 스냅샷을 만들고 그 `workflow.md` 를 따르게 한다(SK:6-13). 포트는 build.py 가 같은 치환을 하고 결과를 `/bmad-build-auto/` 에 올린다; SKILL.md 는 문서로 쓰지 않는다(G7, G5).
- `## On Activation` 의 훅 3개(prepend·persistent_facts·append; customize.toml 기본값 모두 빈 목록 = `_None._`)와 HALT 의 `### On Complete`(`on_complete` = "") 삭제(G7). `**CRITICAL:** … another snapshot file` → `another workflow document`; Conventions 의 snapshot 경로·`{project-root}` 문장을 포트 경로 문장으로(G5).
- 토큰: `[[bmad-snapshot:*]]` 6종 → `/bmad-build-auto/…`, `{skill-root}` → `/bmad-build-auto`, `{{.implementation_artifacts}}` → `/tmp/bmad/implementation-artifacts`, `{project-root}` → `/testbed`, 언어 토큰 3종 → English(G2·G10; B1·B2 규칙 유지).

**2. 호출 모드 하나로 축소** (core-workflow.md, step-01, step-02, step-04) — `env`
- 원문 step-01 은 (a) 기존 spec 파일 재개(`draft`/`ready-for-dev`/`in-review`/`blocked`/`done` 별 EARLY EXIT), (b) folder+id dispatch(`stories.yaml`, `SPEC.md`, 스토리 파일 매칭, 누적 컨텍스트), (c) freeform 의 세 입력을 받는다(S1:18-42). 포트는 (c) 만: "Use the invocation prompt as the intent" + "여기서 호출 프롬프트는 이 런의 task 메시지(issue)이며 재개할 spec·폴더·스토리 목록은 없다"(G1).
- 같은 이유로 삭제: step-01 frontmatter 의 런타임 변수 4개, EARLY EXIT 규칙, Route 의 folder+id 분기와 `draft` 재개·`-2` 접미(C28), step-02 의 Draft resume check 와 `{preserved_intent_contract}` 치환, READY 게이트의 `Halt after planning.` 절, step-04 의 "resumed review / follow-up pass" 분기·`{verbatim_intent}` 의 기존 spec 절·`{followup_pass}` 규칙, HALT 의 folder+id write-back 분기(G1).
- step-01 항목 1 "Load context": 계획 산출물 목록·epic 경로 A(에픽 컨텍스트 캐시·컴파일·이전 스토리 연속성)·freeform 경로 B 의 파일 패턴 스캔 → "IA 를 나열; 계획 산출물·에픽 없음 → freeform, 의도와 저장소 코드가 컨텍스트"(G1·G3). `compile-epic-context.md` 는 배포하지 않음.

**3. 의도 불명확 HALT 삭제** (step-01, step-02, step-03, step-04) — `semantic`
- `unclear intent`(S1:42), 의도 미확정 HALT 절(S1:73 뒷절), intent gap 항목(S2:14), `matrix ambiguity` 절(S3:44), intent_gap 라우트(S4:71)와 그 라벨(S4:49 범위 밖 판단, S4:56 "first three", S4:57 정의, S4:59 patch 정의의 분기, S4:67 행 형식, S4:70 폭포식) 삭제. 대체 문장 없음, spec-template 에 `## Assumptions` 를 더하지 않음(D-2, 2026-11-10). intent-alignment 렌즈와 그 지시문은 유지; 그 finding 은 bad_spec/patch 로 간다.

**4. 실패 HALT → 기록 후 진행** (step-02, step-03, step-04, core-workflow.md) — `semantic`
- 다섯 곳(S2:23 READY 미달, S3:40 검증 실패, S3:44 matrix 감사 실패, S4:70 루프 상한 초과, S4:83 patch 검증 실패)의 `HALT with status blocked, blocking condition X` → "`{spec_file}` frontmatter `status: blocked`, `## Auto Run Result` 에 X 와 증거를 기록하고 계속(다음 단계 / Finalize)". Finalize 의 `status: done` 은 기록된 `blocked` 를 덮지 않는다(D-2, G8). core-workflow.md 설정 절에 규칙을 한 번 설명.
- spec 소실 HALT 2곳(S2:21, S3:14)은 2026-11-10 삭제(G12 → D-8); 10 docs/57 edits.

**5. 서브에이전트 = `task` 도구** (core-workflow.md, step-03, step-04) — `env`
- 원문은 agent 앱의 서브에이전트 기능을 전제하고 없으면 `no subagents` HALT(WF:53). 포트는 그 문장을 "`task` 도구로 띄운다" 로 바꾸고(D-7), 설정 절에 도구의 인자(`prompt`, `subagent_type`=general-purpose, `resume`)·결과 형식(`Task ID` / `Subagent` / `Status` + 마지막 메시지)·서브에이전트의 도구(terminal·file_editor·task_tracker)와 한계(부모 맥락 없음, 자체 서브에이전트 불가)·한 턴 여러 호출·`resume` 를 적는다.
- step-03: 핸드오프 본문(customize.toml `implementation_handoff`) 뒤에 "`task` 1회, prompt = 위 문장, Task ID 보관" 한 문단; "If the platform allows, keep the subagent available" → "`resume` 로 재호출"; `run_in_background` 괄호 삭제(도구에 없음). 핸드오프 충돌 HALT(S3:26) 삭제(D-1 E5: 고정 문장).
- step-04: "Announce skipped layers … For any other customized instruction" 삭제(레이어 4개 고정), "Parallel means several blocking calls awaited together in this turn" 뒤에 "한 턴에 `task` 4회, 렌즈마다 prompt" 추가; `{workflow.review_layers}` → 렌즈 4개 본문(`#### Name (`id`)` 형식); patch 재호출에 "(`task`, `resume` = 구현자 Task ID)" 추가(G86a). `{skill-root}` 전개 지시 삭제(이미 절대경로).

**6. 경로 고정** (step-01, step-03, step-04, core-workflow.md) — `env`
- `spec_file` = `/tmp/bmad/implementation-artifacts/spec-{slug}.md`(원문 `{{.implementation_artifacts}}/spec-{slug}.md`), `diff_file` = `/tmp/bmad/diff/{slug}.diff` 를 step-01 Route 에서 함께 정함(원문: step-03 이 임시 디렉터리에 유일 이름 파일, S3:38; step-04 재작성 S4:15). HALT 의 fallback 결과 파일도 IA 아래(D-5). 디렉터리는 처음 필요할 때 생성.
- edge-case-hunter.md 의 `references/deletion-check.md`·`claims-check.md` 3곳 → `/bmad-build-auto/references/…`(서브에이전트에는 skill 디렉터리가 없음, G5).

**7. VCS·커밋 삭제** (step-01, step-04, core-workflow.md) — `env` (D-1), 최종 status 유지는 `semantic` (D-2)
- step-01 항목 3(VCS sanity check: clean tree, 브랜치, `git add --refresh`) 삭제, 항목 번호 당김. Finalize 의 "커밋·clean 확인·`finalization left repository dirty` HALT"(S4:109-116) → "`status: done`(기록된 `blocked` 는 유지) 후 HALT; 커밋·stash·clean 금지, `/testbed` 작업 트리가 채점 대상". `baseline_revision` 캡처와 `NO_VCS` 분기는 원문 유지.

**8. 직접 쓴 문서** (upstream 대응 없음)
- `core-workflow.md` 의 `## The setting of this run` 절(단계 표, 의도, 답할 사람 없음, 파일 위치, 서브에이전트 도구, 실패 기록, 채점 대상, 읽는 순서, 종료) — 나머지 절은 `workflow.md` 변환.
- `instruction.md`, `system-prompt.j2` 의 `<PROBLEM_SOLVING_WORKFLOW>` 절.
- `tests/test_bmad_build_auto.py`, `build.py`.

## 하네스 쪽 변경 (2026-11-10, 조정자)

패키지 밖에서 이 workflow 가 요구한 것. 모두 다른 workflow 에는 영향이 없다(테스트 `test_workflow_runner_env.py::test_existing_workflows_declare_no_runner_env`).

| 파일 | 변경 | 이유 |
|---|---|---|
| `recipe/grpo/qwen3_5/workflows/spec.py` | `WorkflowSpec.runner_env: Mapping[str, str]` 추가, fingerprint 에 포함(비어 있으면 전과 같은 값) | 워크플로우가 러너 환경 변수를 선언하는 자리 (D-7 ①) |
| `recipe/grpo/qwen3_5/workflow_harness.py` | `build_env` 가 `workflow_spec.runner_env` 를 마지막에 합침 | 선언한 값이 기본값을 이김 |
| `rllm/harnesses/tools/openhands_sdk_runner.py` | `OPENHANDS_SDK_EXTRA_TOOLS`(쉼표 목록, 지금은 `task` 만 허용) 파싱; `task` 면 `register_builtins_agents(enable_browser=False)` 뒤 `Tool(name=TaskToolSet.name)` 추가; 모르는 이름은 종료 코드 2 | SDK 는 내장 서브에이전트 타입을 자동 등록하지 않아 러너가 해야 첫 `task` 호출이 general-purpose 를 찾는다 |
| `docs/guides/workflows/adding-a-workflow.md` | §4 에 `runner_env` 항목 | 가이드 |
| `tests/harnesses/test_openhands_sdk_extra_tools.py`, `recipe/grpo/qwen3_5/tests/test_workflow_runner_env.py` | 파싱·전달·fingerprint·기존 workflow 무영향 | |
| `recipe/grpo/qwen3_5/workflows/if/scripts/bmad/subagent_usage.py` | episode 에서 `task` 호출 수·`resume`·오류·부모/서브 step 수를 세는 스크립트(부모 step = 요청 도구 목록에 `task` 가 있는 step) | 6단계 smoke 와 base/학습 모델 비교의 측정 도구 |

남은 하네스 질문(결정 필요 없음, smoke 에서 확인): SDK `Agent.tool_concurrency_limit` 기본 1 → 한 턴의 `task` 4회가 순차 실행된다(원문은 "동시"). 올리려면 러너에서 `task` 가 켜질 때만 값을 주면 되는데, 같은 턴의 terminal·file_editor 호출도 함께 병렬이 된다. 서브에이전트는 부모의 `max_iteration_per_run` 을 각자 상속하고 엔진은 전체 trace 수로 MAX_TURNS 를 표시만 한다(막지 않음).

## 4b: 채점기 v1 (2026-11-10, 조정자)

aidlc_v4 평가 verifier와 같은 방식(규칙 → 항목 → 범용 엔진, 합성 run 검증)으로 만든 첫 판. 항목 수는 결정 문서의 200개 전부를 rubric 에 올리되, 지금 코드로 판정하는 것은 99개다.

| 파일 | 내용 |
|---|---|
| `reward/build.py` | `porting/rules.yaml` + `if/scripts/bmad/decided_layers.py`(결정) + `ITEMS` 표 → `reward/rubric.yaml`(219 항목), `reward/layers.yaml`(99), `constraints.yaml`(219). 인용은 포트의 토큰 치환을 거쳐 포트 문서에 재고정(`QUOTE_SUBS`), 문장이 바뀐 30개는 `ANCHOR_OVERRIDE` 로 포트 문장을 지정. `--check` 로 드리프트 검사 |
| `reward/checks.py` | `bmad.*` kind 14개: frontmatter 값, 정규식 횟수, 단어 수, `<intent-contract>` 불변, 로그 append-only, spec 파일 수, diff 파일 형식, 산출물 읽기·쓰기, Code Map 경로 열람, 명령 실행, 리뷰어 문서 미열람, **`task` 호출 규칙**(띄움·한 턴 4회·렌즈 4종·프롬프트 형식·resume), **렌즈 출력 형식**(JSON 배열·필드·문장), triage 합계 일관성, 마지막 메시지 질문 없음 |
| `reward/eval.py` | `RubricEvaluation(prefix="bmad", layers)`; `__init__.py` 가 scorer 와 `reward_signal="bmad/compliance"` 를 등록 |
| `workflow_rubric/trace/episode.py`, `trace/openhands.py` | 공통 엔진 변경: 요청 도구 목록에 `task` 가 있는 step 만 부모 run 으로, 나머지는 `Run.meta["subagent_runs"]` 로 분리(대화 = 첫 user 메시지). `task` 호출은 prompt·subagent_type·resume 을 Action 에 보존. `task` 가 없는 episode 는 전과 동일(테스트 `test_trace_subagents.py`) |
| `sdlc_if/templates.yaml` | NEW-AW-subagent, NEW-FM-internal, NEW-FM-language, NEW-WD-revert, NEW-J-content 추가 |
| `tests/test_bmad_build_auto_reward.py` | 빌드 일치, 스키마·파라미터, constraints 일치, 층 커버, 빈 run(금지 항목 3개만 통과), **합성 정직 run**(문서를 글자대로 따른 19 step: 읽기 순서, spec 1회 쓰기, 구현 `task`, diff, 렌즈 4회 한 턴, triage log) 에서 fail 0 |

항목 분포 (결정 198 → 구현 98; D-8 전 200 → 99): L1 139→78, L1C 5→3 (D40 빈 절 None 금지, D42 matrix→테스트 task, G16 리뷰어 출력 severity 없음), L2M 23→5, L2F 49→12. 미구현 119 중 judge 48 은 `log_only`, 나머지 72 의 사유는 `constraints.yaml` 의 `class_note`(서브 대화가 필요한 것 15, 루프백·patch 경로 13, 기록된 차단 조건 6, 중복 9, 모호 7 …).

아직 안 한 것(aidlc verifier 절차 기준): 재료 검수(실데이터 대조), 꼼수·정직 변형과 단조성(golden 은 1개), 실데이터 감사, judge. 서브에이전트 대화 안의 규칙(E7, F12, G18~G41 …)은 `subagent_runs` 가 생겼으니 다음 판에서 구현 가능.
