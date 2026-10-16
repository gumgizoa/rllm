# Survey: Agent OS v2.1.1 (single-agent pipeline, "other tools" install path)

- Upstream: https://github.com/buildermethods/agent-os @ 6a6495111e9f7f9cdab3c172814a7476e83a8ec9 (tag `v2.1.1`, merge of PR #258 dated 2025-10-28; `CHANGELOG.md:6` says 2025-10-29; `config.yml:1` `version: 2.1.1`), license MIT (`LICENSE`, "Copyright (c) 2025 CasJam Media LLC (Builder Methods)": use/copy/modify/distribute permitted provided the copyright and permission notice are included in all copies or substantial portions, `LICENSE:3-13`)
- Checkout: `/tmp/claude-4011/-gpfs-home-daink-2026-2-DFM/5e4b9e70-5416-45b3-83af-4eafaaa1cd83/scratchpad/agentos-v2.1.1` (git archive of the tag, read-only). Full clone `/gpfs/home/daink/2026-2_DFM/agent-os` has HEAD `e892e61` = v3.x (tag `v3.0.0` = `809fb4e`, 2026-01-20, restructured with top-level `commands/`); v3 is not surveyed.
- Rendered tree (stage 2 input): `/tmp/claude-4011/-gpfs-home-daink-2026-2-DFM/5e4b9e70-5416-45b3-83af-4eafaaa1cd83/scratchpad/agentos-render/` — `home/agent-os/` = base install (v2.1.1 tree, `config.yml` edited to `claude_code_commands: false`, `agent_os_commands: true`), `project/agent-os/` = output of `project-install.sh`, `run-install.sh` = the exact command used. Below, `R:` = `.../agentos-render/project/`.

Upstream paths below are relative to the checkout; command text lives in `profiles/default/commands/<cmd>/single-agent/`, abbreviated `cmd/<cmd>/`; workflows in `profiles/default/workflows/`, abbreviated `wf/`.

## 파이프라인: 단일 에이전트 스펙 파이프라인 (shape-spec → write-spec → create-tasks → implement-tasks)

`S` = `agent-os/specs/<YYYY-MM-DD>-<이름>/`, `P` = `agent-os/product/`, `STD` = `agent-os/standards/` (설치 시 복사되는 15개 파일; 명령 본문에는 내용이 아니라 `@agent-os/standards/...` 참조 목록으로 들어감). 사람은 렌더된 `agent-os/commands/<명령>/<명령>.md` 를 채팅에 넣어 실행한다 **(inferred: 호출 방법은 외부 문서에만 있음)**.

### 전체 흐름
```
shape-spec            →  write-spec          →  create-tasks          →  implement-tasks
(질문·답변으로 요구사항)    (requirements→spec.md)   (spec→tasks.md 체크리스트)  (구현 + 전체 테스트 + 검증 보고서)
```
사람이 명령 파일을 하나씩 넣어 다음 단계로 넘기며, 각 단계는 "다음에 실행할 명령"을 알려주는 확인 메시지로 끝난다(단계 안의 PHASE 는 한 파일에 합쳐져 있어 에이전트가 이어서 수행하되, WAIT/STOP 지점에서는 사람 답을 기다림).

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **1. shape-spec** | 1. Initialize Spec | 기능 설명을 받아 날짜 + kebab-case 이름으로 spec 폴더 생성 (bash `date`, `mkdir -p`) | **사람의 기능 설명** (없으면 `P/roadmap.md` 의 다음 항목을 제안하고 **사람 확인**을 기다림) | `S/planning/`, `S/planning/visuals/`, `S/implementation/` (빈 폴더). 책임 목록의 "원문 아이디어 저장"은 실제 단계가 없어 `initialization.md` 를 쓰지 않음; "2개 폴더 생성"이라 하고 1개만 나열, "Verification 폴더"도 만들지 않음 |
| | 2. Shape Spec | 제품 문서를 읽고 "I'm assuming X, 맞나요?" 형식의 번호 질문 4–8개 + 재사용할 기존 코드 질문 + 시안 요청을 출력하고 **멈춤** → 답을 받으면 visuals 폴더 `ls` (필수), 필요하면 후속 질문 1–3개 후 다시 **멈춤** → 요구사항 저장. 사람이 알려준 유사 기능 경로는 직접 열어 보지 말고 이름만 기록하라고 함 | `S/planning/initialization.md` (**어느 단계도 쓰지 않는 파일**), `P/mission.md`, `P/roadmap.md`, `P/tech-stack.md`, **사람의 답변**, **사람이 넣은 시안 이미지** (`S/planning/visuals/`), **사람이 알려준 유사 기능 경로**, `STD/global/*` 6개 | `S/planning/requirements.md` (고정 템플릿: 질문·답변 원문, 재사용 후보, 시안 분석, 기능 요구사항, 범위 In/Out, 기술 고려사항). 끝 메시지가 없는 파일 `1-create-spec.md` 와 이 경로에 없는 슬래시 명령 `/write-spec` 을 안내함 |
| **2. write-spec** | (단일) | 요구사항·시안을 분석하고 코드베이스에서 재사용할 컴포넌트·패턴을 검색한 뒤 spec 작성 (코드 작성 금지, 템플릿 외 섹션 금지) | `S/planning/requirements.md`, `S/planning/visuals/`, 저장소 코드, `STD/*` 15개. spec 폴더를 찾는 단계는 없음 (대화 맥락의 `[current-spec]` 전제) | `S/spec.md` (Goal, User Stories ≤3, Specific Requirements ≤10, Visual Design, Existing Code to Leverage ≤5, Out of Scope). 끝 메시지가 `2-create-tasks-list.md` 를 안내해 create-tasks PHASE 1 을 건너뛰게 함 |
| **3. create-tasks** | 1. Get Spec Requirements | spec.md / requirements.md 가 대화 맥락에 있는지 확인, 없으면 **사람에게 위치를 묻고** 대기 | `S/spec.md` 그리고/또는 `S/planning/requirements.md`, (없을 때) **사람이 알려주는 경로** | (없음) |
| | 2. Create Tasks List | 의존 순서와 전문 분야(DB/API/UI…)별 task group 으로 분해. 각 그룹은 "테스트 2–8개 작성 → 구현 → 그 테스트만 실행", 마지막 테스트 보강 그룹은 최대 10개 추가 | 위 두 파일, `STD/*` 15개 | `S/tasks.md` (`- [ ]` 체크리스트, 그룹별 Dependencies·Acceptance Criteria; 예시는 웹앱 DB→API→UI→테스트). 끝 메시지가 슬래시 명령 `/implement-tasks` 또는 `/orchestrate-tasks` 를 안내 |
| **4. implement-tasks** | 1. Determine Tasks | 구현할 task group 지시가 있으면 PHASE 2 로, 없으면 tasks.md 를 읽고 "전부 진행할까요?"를 묻고 대기 | `S/tasks.md`, **사람의 그룹 선택/승인** | (없음). 문구에 "implementer subagent 에 위임"이 남아 있으나 이 경로엔 서브에이전트가 없음 |
| | 2. Implement Tasks | spec·requirements·시안·코드 패턴을 분석해 할당된 그룹만 구현, 자기가 쓴 테스트만 실행, (도구가 있으면) 브라우저로 UI 확인, 끝난 항목을 `- [x]` 로 갱신 | `S/spec.md`, `S/planning/requirements.md`, `S/planning/visuals/`, `S/tasks.md`, 저장소, `STD/*` 15개 | **코드 변경** (+ 새 테스트), `S/tasks.md` 체크 갱신. 남은 항목이 있으면 "계속할까요?"(**사람 답변**), 다 끝나면 `3-verify-implementation.md` 를 실행하라고 안내 (같은 파일에 PHASE 3 이 이미 이어짐) |
| | 3. Verify Implementation | tasks.md 전부 `[x]` 인지 확인(미완료면 코드 spot check 후 체크 또는 ⚠️), 로드맵 항목 체크, **전체 테스트 스위트 실행 — 실패는 고치지 말고 기록만**, 최종 보고서 작성 | `S/tasks.md`, `agent-os/spec/[this-spec]/implementation/` 의 구현 보고서 (경로가 `spec/` 로 오타이고 **어느 단계도 쓰지 않음**), `P/roadmap.md`, 테스트 실행 결과 | `S/verifications/final-verification.html` (내용은 markdown 템플릿; `verifications/` 폴더를 만드는 단계 없음), `P/roadmap.md` 체크 갱신 |

### 정리하면
- **사람이 넣는 입력**: 명령 파일 4번 호출(단계 이동 전부); shape-spec 의 기능 설명(없으면 로드맵 항목 승인); 1차 질문 4–8개 답변 + 유사 기능 경로 + 시안 이미지; 후속 질문 답변(있을 때); create-tasks 에서 spec 위치(맥락에 없을 때); implement-tasks 에서 구현할 task group 선택/승인과 남은 그룹 계속 여부; 각 단계 끝의 "검토하세요" 리뷰(형식상 권고).
- **코드를 바꾸는 곳**: implement-tasks PHASE 2 만 (PHASE 3 은 테스트 실행·체크박스·보고서만, 실패 수정 금지). 문서 체인: (기능 설명) → `S/planning/requirements.md` → `S/spec.md` → `S/tasks.md` → 코드 + `S/tasks.md` 체크 → `S/verifications/final-verification.html`.
- **오래된 저장소·사전 준비를 전제한 입력**: `P/mission.md`·`P/roadmap.md`·`P/tech-stack.md` (plan-product 산출물 — SWE 저장소엔 없음); `STD/` (설치로 생기지만 `global/tech-stack.md` 는 빈 템플릿이고 나머지는 일반론); `S/planning/initialization.md` 와 구현 보고서 (쓰는 단계가 없음); 시안 이미지와 유사 기능 경로를 알려줄 사람; 웹앱 계층(DB/API/UI)을 전제한 tasks 예시; 단계 사이에 `[this-spec]` 을 기억하는 같은 대화 맥락.

## 파이프라인: 스펙 파이프라인 + orchestrate-tasks (implement-tasks 대신)

`S`, `P`, `STD` 는 위와 같음. 1–3 단계는 위 표와 동일하고 마지막 단계만 다르다.

### 전체 흐름
```
shape-spec  →  write-spec  →  create-tasks  →  orchestrate-tasks
(위와 동일)     (위와 동일)     (위와 동일)      (task group 별 위임 계획 + 위임)
```
사람이 `agent-os/commands/orchestrate-tasks/orchestrate-tasks.md` 를 넣어 시작하고, 위임할 대상과 표준을 사람이 답한 뒤 에이전트가 그룹별로 위임하며 끝난다(검증 단계 없음).

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **4. orchestrate-tasks** | 1. Get tasks.md | 어떤 spec 인지 알고 tasks.md 가 있으면 다음으로, 아니면 **사람에게 tasks.md 위치를 요청** | `S/tasks.md` | (없음) |
| | 2. Create orchestration.yml | tasks.md 의 task group 이름으로 계획 파일 생성 | `S/tasks.md` | `S/orchestration.yml` |
| | 3. Assign subagents | 그룹별 서브에이전트 이름을 **사람에게 묻고** 기록 (이 렌더에서 포함됨: 기본 `use_claude_code_subagents: true` 가 그대로 남기 때문) | **사람이 정한 서브에이전트 이름** | `S/orchestration.yml` (`claude_code_subagent`) |
| | 4. Assign standards | 그룹별 표준(`all`, `global/*`, 파일, `none`)을 **사람에게 묻고** 기록 | **사람의 표준 선택** | `S/orchestration.yml` (`standards`) |
| | 5. Delegate | 각 그룹을 지정된 서브에이전트에 위임(그룹 내용, spec.md, 표준 `@` 목록 전달), 서브에이전트가 구현하고 체크 — 이 경로의 도구엔 서브에이전트가 없음. 서브에이전트를 끄면 대신 그룹별 프롬프트 파일을 만들어 사람이 하나씩 넣게 하는 분기가 있으나 이 렌더에는 빠짐 | `S/orchestration.yml`, `S/tasks.md`, `S/spec.md`, `STD/*` | (위임받은 쪽이) **코드 변경**, `S/tasks.md` 체크. (프롬프트 분기라면 `S/implementation/prompts/<n>-<그룹>.md`) |

### 정리하면
- **사람이 넣는 입력**: 1–3 단계의 입력 전부 + tasks.md 위치(필요 시), 그룹별 서브에이전트 이름, 그룹별 표준 선택, (프롬프트 분기라면) 프롬프트 파일을 하나씩 넣는 일.
- **코드를 바꾸는 곳**: PHASE 5 에서 위임받은 에이전트. 문서 체인: … → `S/tasks.md` → `S/orchestration.yml` → 코드 + `S/tasks.md` 체크. 전체 테스트·검증 보고서 단계는 없음.
- **오래된 저장소·사전 준비를 전제한 입력**: 1–3 단계와 동일 + 미리 만들어 둔 전문 서브에이전트(Claude Code 기능); "other tools" 렌더인데도 서브에이전트 분기가 들어가는 설정 불일치.

## Normal use

**Base install.** `base-install.sh` creates `~/agent-os` (`scripts/base-install.sh:12`, `:606`) and downloads every repo file except `.github/*` etc. from branch `main` via the GitHub tree API and raw URLs (`scripts/base-install.sh:9`, `:84`, `:100`, `:127-140`). Running it today would therefore install v3, not v2.1.1 **(inferred from `main` = v3 in the clone)**; the render used a copy of the tag tree as `~/agent-os` instead. Base config defaults: `claude_code_commands: true`, `agent_os_commands: false`, `use_claude_code_subagents: true`, `standards_as_claude_code_skills: false`, `profile: default` (`config.yml:15,24,34,45,56`). The "other tools" use is `agent_os_commands: true` ("Cursor, Windsurf, etc. … install commands in your project's agent-os/commands/ folder", `config.yml:18-24`).

**Project install.** `cd <project> && ~/agent-os/scripts/project-install.sh` (`scripts/base-install.sh:626-627`), optional flags override the base config (`scripts/project-install.sh:47-58`, `:150-155`). With `claude_code_commands: false`, `agent_os_commands: true`:
- `validate_config` only warns about `use_claude_code_subagents` (it is *not* reset; `scripts/common-functions.sh:1227-1231`) and forces `standards_as_claude_code_skills` to false (`:1235-1242`). Both warnings appeared in the run.
- Writes `agent-os/config.yml` (13 lines, compiled settings; `scripts/common-functions.sh:1252-1275`).
- Copies all 15 standards to `agent-os/standards/` (`scripts/project-install.sh:174-201`).
- `install_agent_os_commands` compiles **every** `commands/*/single-agent/*` file — top-level and numbered — plus `orchestrate-tasks.md`, all in `embed` mode, preserving the numbered names under `agent-os/commands/<cmd>/` (`scripts/project-install.sh:328-357`). (The Claude Code embed path instead skips numbered files and writes flat `.claude/commands/agent-os/<cmd>.md`, `:264-272`.) No `.claude/` files, no skills, no `improve-skills` (`:446-459` gated on `claude_code_commands`).
- Re-running in an installed project execs `project-update.sh` (`scripts/project-install.sh:539-546`).

**Rendered output on this path** (`R:agent-os/`, from the run on 2026-10-14):

| Rendered file | Lines | | Rendered file | Lines |
|---|---|---|---|---|
| `commands/shape-spec/shape-spec.md` | 395 | | `commands/plan-product/plan-product.md` | 241 |
| `commands/shape-spec/1-initialize-spec.md` | 95 | | `commands/plan-product/1-product-concept.md` | 53 |
| `commands/shape-spec/2-shape-spec.md` | 300 | | `commands/plan-product/2-create-mission.md` | 78 |
| `commands/write-spec/write-spec.md` | 134 | | `commands/plan-product/3-create-roadmap.md` | 73 |
| `commands/create-tasks/create-tasks.md` | 254 | | `commands/plan-product/4-create-tech-stack.md` | 46 |
| `commands/create-tasks/1-get-spec-requirements.md` | 19 | | `commands/orchestrate-tasks/orchestrate-tasks.md` | 180 |
| `commands/create-tasks/2-create-tasks-list.md` | 234 | | `standards/**` (15 files, copied verbatim) | 163 |
| `commands/implement-tasks/implement-tasks.md` | 203 | | `config.yml` | 13 |
| `commands/implement-tasks/1-determine-tasks.md` | 13 | | | |
| `commands/implement-tasks/2-implement-tasks.md` | 59 | | | |
| `commands/implement-tasks/3-verify-implementation.md` | 113 | | | |

Target pipeline, top-level files only: 395 + 134 + 254 + 203 = **986 lines**. Standards are referenced, not inlined.

**How template tags resolve on this path** (order in `compile_agent`: conditionals → workflows → standards → PHASE, `scripts/common-functions.sh:966-1019`):
- `{{PHASE N: @agent-os/commands/<cmd>/<file>.md}}` (only in top-level files) → replaced by `# PHASE N: <Title from filename>` + the fully compiled content of `commands/<cmd>/single-agent/<file>.md` (`scripts/common-functions.sh:771-782`, `:841`). E.g. `R:agent-os/commands/shape-spec/shape-spec.md:7`, `:94`. The preamble "read and execute the instructions in the following files IN SEQUENCE, following their numbered file names" is kept even though the files are now inlined (`R:agent-os/commands/shape-spec/shape-spec.md:3`).
- `{{UNLESS compiled_single_command}}` → block **dropped** inside embedded PHASE content (`compiled_single_command=true`, `scripts/common-functions.sh:790-791`), **kept** in the standalone numbered files (`false`, `:965-966`). So `R:agent-os/commands/shape-spec/1-initialize-spec.md:94` keeps "NEXT STEP 👉 Run the command, 2-research-spec.md" (wrong filename), while the top-level file does not. Display blocks not wrapped in this tag (`cmd/shape-spec/2-shape-spec.md:7-27`, `cmd/write-spec/write-spec.md:5-15`, `cmd/create-tasks/2-create-tasks-list.md:5-15`, `cmd/implement-tasks/2-implement-tasks.md:5-23`) survive in the top-level files (`R:agent-os/commands/shape-spec/shape-spec.md:371,383`, `R:agent-os/commands/implement-tasks/implement-tasks.md:58`).
- `{{UNLESS standards_as_claude_code_skills}}` → kept (flag forced false, `scripts/common-functions.sh:1241`), so every "User Standards & Preferences Compliance" section is present.
- `{{workflows/<path>}}` → full text of `profiles/default/workflows/<path>.md`, recursive, with a cycle guard; a missing file inserts a ⚠️ warning line (`scripts/common-functions.sh:626-702`). No warnings in the render.
- `{{standards/*}}` → sorted list of `@agent-os/standards/<dir>/<file>.md` lines for all 15 files; `{{standards/global/*}}` → the 6 `global/` files (`scripts/common-functions.sh:705-737`; `R:agent-os/commands/write-spec/write-spec.md:120-134`, `R:agent-os/commands/shape-spec/shape-spec.md:390-395`).
- `{{IF/UNLESS use_claude_code_subagents}}` → only in `orchestrate-tasks.md`; evaluated with the un-reset `true`, so the subagent branch is rendered (`R:agent-os/commands/orchestrate-tasks/orchestrate-tasks.md:38-50`, `:137-180`) and the non-Claude prompt-file branch (`profiles/default/commands/orchestrate-tasks/orchestrate-tasks.md:162-237`) is dropped.
- No unresolved `{{` remains in `R:agent-os/commands/`.

**Driving it.** The rendered files address the person with "NEXT STEP 👉 Run the command, `<file>`" (`R:agent-os/commands/create-tasks/1-get-spec-requirements.md:18`) or slash names (`/write-spec`, `/implement-tasks`, `cmd/shape-spec/2-shape-spec.md:26`, `cmd/create-tasks/2-create-tasks-list.md:14`). In a non-Claude tool a person attaches/mentions the top-level file (or each numbered file in turn) in chat with their request **(inferred: the installer only points to external docs, `scripts/project-install.sh:480`; v2.1.0 notes say these phases can be used "all or pick and choose", `CHANGELOG.md:94-109`)**.

**Worked example (inferred from the text).** Person: `@agent-os/commands/shape-spec/shape-spec.md Add CSV export to the reports page`. Agent creates `agent-os/specs/2026-10-14-csv-export/{planning/visuals,implementation}` (`wf/specification/initialize-spec.md:35-60`), reads `agent-os/product/*.md`, prints 4–8 assumption questions + reuse + visuals request and stops (`wf/specification/research-spec.md:47-92`); person answers; agent lists `planning/visuals/`, maybe asks 1–3 follow-ups, writes `planning/requirements.md` (`:100-152`). Person: `@agent-os/commands/write-spec/write-spec.md` → `spec.md`. Person: `@agent-os/commands/create-tasks/create-tasks.md` → `tasks.md`. Person: `@agent-os/commands/implement-tasks/implement-tasks.md` → "proceed with all task groups?" → "yes" → code + tests, boxes ticked, full test run, `verifications/final-verification.html`.

## Processes

| Process | Stages (in order) | Reads / writes | Who advances | Agent-facing text | Human checkpoints |
|---|---|---|---|---|---|
| **A. Spec pipeline, single-agent (target)** | shape-spec (1 Initialize Spec, 2 Shape Spec) → write-spec → create-tasks (1 Get Spec Requirements, 2 Create Tasks List) → implement-tasks (1 Determine Tasks, 2 Implement Tasks, 3 Verify Implementation) (`CHANGELOG.md:98-107`; `cmd/*/<cmd>.md`) | writes `S/planning/requirements.md` (`wf/specification/research-spec.md:152`), `S/spec.md` (`wf/specification/write-spec.md:49`), `S/tasks.md` (`wf/implementation/create-tasks-list.md:23`), code + tasks checkboxes (`wf/implementation/implement-tasks.md:7-8`), `S/verifications/final-verification.html` (`wf/implementation/verification/create-verification-report.md:1`), `P/roadmap.md` checkboxes (`wf/implementation/verification/update-roadmap.md:1`) | Person invokes each command; PHASEs within a file run in sequence (`cmd/shape-spec/shape-spec.md:3`) | Rendered top-level 986 lines (above). Pre-render: commands 59+23+53+78 = 213, workflows 82+262+99+199+16+9+1+5+80 = 753, standards 163 (referenced) | Feature description if not given (`wf/specification/initialize-spec.md:15-29`); Q&A STOP (`wf/specification/research-spec.md:92`); follow-up STOP (`:148`); spec location if missing (`cmd/create-tasks/1-get-spec-requirements.md:5-9`); which task groups (`cmd/implement-tasks/1-determine-tasks.md:5-13`); continue remaining groups (`cmd/implement-tasks/2-implement-tasks.md:17-23`); "review it closely" after write-spec / create-tasks (`cmd/write-spec/write-spec.md:12`, `cmd/create-tasks/2-create-tasks-list.md:12`) |
| **B. A with orchestrate-tasks** | shape-spec → write-spec → create-tasks → orchestrate-tasks (get tasks.md, orchestration.yml, assign subagents, assign standards, delegate / generate prompts) (`CHANGELOG.md:109`) | writes `S/orchestration.yml` (`profiles/default/commands/orchestrate-tasks/orchestrate-tasks.md:26`); prompt branch writes `S/implementation/prompts/*.md` (`:167-174`) | Person; delegation to Claude Code subagents (`:141-160`) or person pastes prompts one by one (`:233`) | Rendered 180 lines; source 237 + `wf/implementation/compile-implementation-standards.md` 28 | Subagent assignment (`:41`), standards assignment (`:83`), tasks.md location (`:13-22`) |
| **C. plan-product** | 1 Product Concept → 2 Create Mission → 3 Create Roadmap → 4 Create Tech Stack (`cmd/plan-product/plan-product.md:12-18`) | writes `P/mission.md`, `P/roadmap.md`, `P/tech-stack.md` (`wf/planning/create-product-mission.md:1`, `wf/planning/create-product-roadmap.md:1`, `wf/planning/create-product-tech-stack.md:1`) | Person; PHASE 1 says "WAIT for me to give you specific instructions" even in the compiled single file (`cmd/plan-product/1-product-concept.md:7`, `R:agent-os/commands/plan-product/plan-product.md:45`) | Rendered 241 lines | Product idea / ≥3 features / users / tech stack (`wf/planning/gather-product-info.md:12-25`); review of each doc |
| **D. Claude Code variants** (multi-agent commands, subagents, skills, `improve-skills`) | same phases via `.claude/commands/agent-os/` and `.claude/agents/agent-os/` | — | — | not installed on this path (`scripts/project-install.sh:446-459`) | — |

## Agent-facing sources

Converter should read the pre-render sources (or reuse the installer's compile logic); the rendered tree above is the ground truth for what the agent sees.

| File (upstream path) | Role | Generated? | Lines |
|---|---|---|---|
| `profiles/default/commands/shape-spec/single-agent/shape-spec.md` | top-level command, 2 PHASE tags | source → rendered `R:agent-os/commands/shape-spec/shape-spec.md` (395) | 9 |
| `.../shape-spec/single-agent/1-initialize-spec.md`, `2-shape-spec.md` | PHASE bodies (`{{workflows/...}}`, display, standards) | source → embedded + standalone (95, 300) | 15, 35 |
| `.../write-spec/single-agent/write-spec.md` | single-phase command | source → 134 | 23 |
| `.../create-tasks/single-agent/create-tasks.md`, `1-get-spec-requirements.md`, `2-create-tasks-list.md` | command + PHASE bodies | source → 254 (19, 234) | 9, 21, 23 |
| `.../implement-tasks/single-agent/implement-tasks.md`, `1-determine-tasks.md`, `2-implement-tasks.md`, `3-verify-implementation.md` | command + PHASE bodies | source → 203 (13, 59, 113) | 15, 13, 31, 19 |
| `profiles/default/workflows/specification/initialize-spec.md` | spec folder creation | inlined | 82 |
| `profiles/default/workflows/specification/research-spec.md` | Q&A + requirements.md template | inlined | 262 |
| `profiles/default/workflows/specification/write-spec.md` | code search + spec.md template | inlined | 99 |
| `profiles/default/workflows/implementation/create-tasks-list.md` | tasks.md template | inlined | 199 |
| `profiles/default/workflows/implementation/implement-tasks.md` | implementation rules | inlined | 16 |
| `profiles/default/workflows/implementation/verification/{verify-tasks,update-roadmap,run-all-tests,create-verification-report}.md` | final verification | inlined | 9, 1, 5, 80 |
| `profiles/default/standards/{global,backend,frontend,testing}/*.md` | standards, copied to `agent-os/standards/`, referenced by `@` path | copied verbatim | 163 total (15 files) |
| `profiles/default/commands/orchestrate-tasks/orchestrate-tasks.md` (+ `wf/implementation/compile-implementation-standards.md`) | process B | source → 180 | 237 (+28) |
| `profiles/default/commands/plan-product/single-agent/*.md` + `wf/planning/*.md` | process C | source → 241 | 18+27+25+25+23; 25+52+47+20 |
| `profiles/default/workflows/specification/verify-spec.md`, `profiles/default/agents/*.md`, `commands/*/multi-agent/*.md` | Claude Code subagent path only | not rendered on this path | 282; 202; 205 |
| `scripts/common-functions.sh` (`process_conditionals`, `process_workflows`, `process_standards`, `process_phase_tags`, `compile_agent`) | renderer | — | 1468 |

## Machinery the text relies on

- **Scripts**: none shipped for the agent. Inline bash the agent is told to run: spec folder creation with `date` + `mkdir -p` (`wf/specification/initialize-spec.md:35-53`); mandatory `ls -la .../planning/visuals/ | grep -E '\.(png|jpg|...)$'` (`wf/specification/research-spec.md:102-107`); `cat requirements.md` + `ls visuals` (`wf/specification/write-spec.md:14-20`). "Run the entire tests suite" with no command given (`wf/implementation/verification/run-all-tests.md:1`). Installer needs bash + perl (`scripts/common-functions.sh:664-687`).
- **Config / context files the agent reads**: `agent-os/product/{mission,roadmap,tech-stack}.md` (`wf/specification/research-spec.md:22-37`, `wf/specification/initialize-spec.md:19`, `wf/implementation/verification/update-roadmap.md:1`); `agent-os/standards/**` via `@` reference lists (all compliance sections); `[spec-path]/planning/initialization.md` (`wf/specification/research-spec.md:16`) — never written by any stage (`wf/specification/initialize-spec.md:7` lists "Save Raw Idea" but no step does it). Whether a non-Claude tool auto-loads `@path` lines embedded in a file is tool-dependent **(inferred)**.
- **Spec identity across commands**: carried only by conversation context; placeholders vary (`[this-spec]`, `[current-spec]`, `[spec-path]`; `wf/specification/write-spec.md:16`, `wf/implementation/create-tasks-list.md:15,23`); only create-tasks asks if missing (`cmd/create-tasks/1-get-spec-requirements.md:5`).
- **Hooks / extensions**: none on this path.
- **Network**: none in pipeline text; optional "browser testing tools" for UI (`wf/implementation/implement-tasks.md:16`). Installer: base install downloads from GitHub `main` (`scripts/base-install.sh:37,84,140`); project install is offline.
- **Git**: no git operations in any pipeline text; the conventions standard mentions feature branches and commit messages generally (`profiles/default/standards/global/conventions.md:5`).
- **Interactive points**: listed in Processes row A. Text also speaks to an "orchestrator" relaying answers (multi-agent remnant: `wf/specification/research-spec.md:92,96,138,236,262`, `wf/specification/initialize-spec.md:80`) and to an "implementer subagent" (`cmd/implement-tasks/1-determine-tasks.md:3`).
- **Testing policy**: per group write 2–8 tests first and run only those (`wf/implementation/create-tasks-list.md:192-197`); standard says write minimal tests, skip edge cases (`profiles/default/standards/testing/test-writing.md:3-5`); verification runs the full suite and must not fix failures (`wf/implementation/verification/run-all-tests.md:1-5`).
- **Upstream inconsistencies on the target path**: wrong next-step names `2-research-spec.md` (`cmd/shape-spec/1-initialize-spec.md:13`), `1-create-spec.md` (`cmd/shape-spec/2-shape-spec.md:14`), `2-create-tasks-list.md` after write-spec (`cmd/write-spec/write-spec.md:14`); "Create 2 folders" lists one (`wf/specification/initialize-spec.md:57-58`); implementation reports read at `agent-os/spec/...` (singular) and listed as `implementations/` but no stage writes them and v2.1.0 removed per-task docs (`wf/implementation/verification/verify-tasks.md:5`, `wf/implementation/verification/create-verification-report.md:42-43`, `CHANGELOG.md:85`); markdown report saved as `.html` in a never-created `verifications/` (`wf/implementation/verification/create-verification-report.md:1`); "Run `3-verify-implementation.md`" printed although PHASE 3 follows in the same file (`R:agent-os/commands/implement-tasks/implement-tasks.md:58,89`); tasks example names "database-engineer / api-engineer / ui-designer" (`wf/implementation/create-tasks-list.md:148-150`).

## Fit for SWE tasks

| Process | Fit | Main mismatch |
|---|---|---|
| A. Spec pipeline, single-agent | Low–Medium | Issue text can serve as the feature description (`wf/specification/initialize-spec.md:15`) and write-spec/implement do search and edit the repo, but shape-spec is built around a person answering 4–8 questions + follow-ups and supplying visuals/reuse paths, and tells the agent not to open the reuse paths a person names, only record them (`wf/specification/research-spec.md:47-148`, `:115-117`); it presumes `agent-os/product/*` docs and web-app feature framing; it writes new tests and `agent-os/specs/**` files into the repo; verification forbids fixing failures. |
| B. A + orchestrate-tasks | Low | Needs pre-built Claude Code subagents and per-group human assignment; rendered branch delegates to subagents a non-Claude tool lacks; no verification phase. |
| C. plan-product | None | Product mission/roadmap/tech-stack only; no code change. |
| D. Claude Code variants | n/a | Not produced on the chosen install path. |

## Recommendation

Port **A** (single-agent spec pipeline: shape-spec → write-spec → create-tasks → implement-tasks) from the "other tools" render: it is the only process that ends in a code change with verification, it is the path the user chose, and its agent text is fully determined by the rendered files in `.../agentos-render/project/agent-os/commands/` (986 lines for the four top-level files). Workflow name: `agentos_v2` (user-chosen; the stage convention would give `agentos_spec`). plan-product's outputs are inputs that A reads but a SWE repo will not have — stage 2 must decide how to treat them.

## Process chosen (user, 2026-10-14)

v2.1.1 single-agent pipeline (shape-spec → write-spec → create-tasks → implement-tasks), "other tools" install path (`config.yml`: `agent_os_commands: true`, `claude_code_commands: false`; rendered by `install_agent_os_commands` into `agent-os/commands/<cmd>/`), workflow name `agentos_v2`.
