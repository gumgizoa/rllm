# Changes: agentos_v2  (upstream buildermethods/agent-os@6a64951 = v2.1.1, shape-spec → write-spec → create-tasks → implement-tasks, "other tools" 설치 경로)

원문 링크 접두사 `U/` = `https://github.com/buildermethods/agent-os/blob/6a6495111e9f7f9cdab3c172814a7476e83a8ec9/profiles/default/`.
`S` = spec 폴더 `/tmp/agent-os/specs/<YYYY-MM-DD>-<이름>/`.

## 계획 대비 달라진 점

| # | 항목 | 계획(03-plan.md) | 실제 구현 | 이유 |
|---|---|---|---|---|
| 1 | standards 펼쳐 넣는 형식 | `@agent-os/standards/...` 참조 목록을 파일 내용으로 펼쳐 넣음 (형식 미지정) | `@agent-os/standards/<dir>/<file>.md` 한 줄을 굵은 이름표 `` **`agent-os/standards/<dir>/<file>.md`** `` + 빈 줄 + 파일 본문으로 교체. 본문의 `## ` 제목은 그대로(한 단계 내리지 않음). 이름표는 저장소 기준 상대 경로라 문서 간 참조 검사 대상이 아님 | G7-3 "each under its path as a label"의 해석. `@` 확장 도구가 보여 주는 모양에 가깝게, 편집 없이 |
| 2 | 진입 문서에 추가한 설명 | 명령 순서, 입력 정의, 자체 답변 규칙, 산출물 위치, checks, tasks.md 체크 기록, 텍스트 응답 금지, finish | 계획 항목 전부 + (a) 자리표시 `[this-spec]`·`[current-spec]`·`[spec-path]`·`$SPEC_PATH`는 모두 같은 spec 폴더 하나, (b) 굵은 `agent-os/standards/...` 줄은 이름일 뿐 열 파일이 없음, (c) `S/checks/`는 어느 명령도 만들지 않으니 처음 필요할 때 생성, (d) 각 파일은 문서의 양식대로 쓰고 그 명령이 끝나면 tasks.md 체크박스 외에는 고치지 않음, (e) `/testbed`를 바꾸는 곳은 implement-tasks PHASE 2뿐이고 PHASE 3은 코드를 바꾸지 않음 | stage 4 지침의 진입 문서 항목(보고서 규칙: 한 번 쓰기, 구조 유지, 편집 단계 외 저장소 불변)과 G5-3 (rev)·G7-3·G8-1에서 나온 환경 사실. 원문 동작을 바꾸지 않는 설명 |
| 3 | G1-2 initialization.md 단계 위치 | PHASE 1에 issue 원문 저장 단계 추가 | PHASE 1의 Step 4 "Output Confirmation"(G2-1로 삭제되는 출력 블록) 자리를 "Step 4: Save Raw Idea"로 교체. 단계 번호 유지 | 삭제되는 단계 자리에 넣어 번호를 바꾸지 않음 |
| 4 | G4-1 질문 양식 주변 | 질문 생성 유지, 자체 답변, STOP 없음 | 계획 범위 + 추가로 손댄 줄: 책임 목록 3번("WITH a reusability check, and answer them yourself"), "**Required output format:**" → "**Required format:**", 후속 질문 블록 머리 "OUTPUT to orchestrator" → "write them down in this format". 질문 양식 안의 사람에게 하는 말("Based on your idea…", "Please provide file/folder paths…", "Please provide these additional details.")은 양식 원문으로 유지. 첫 질문 양식 끝의 "Please answer the questions above and let me know if you've added any visual files…"는 시안 요청과 함께 삭제(G4-3) | "output"이 텍스트 응답(세션 종료)을 부를 수 있어 G4-1·G2-1 범위에서 정리. 양식 자체는 G4-1 "same format" |
| 5 | G4-3 Step 3 제목 | 시안 요청 삭제 | 본문의 요청 블록 + Step 3 제목의 "WITH Visual Request" + CRITICAL 줄의 "visual asset request"도 삭제 | 같은 요청을 가리키는 문구 |
| 6 | G5-5 폴더 문장 | `verifications/` 폴더도 생성 | 목록에 `verifications/` 추가, "Leave this folder empty" → "Leave these folders empty" | 폴더가 2개가 되어 문장 수만 맞춤 |
| 7 | G4-4·G7-4 PHASE 1 구조 | "모든 group을 순서대로" | "사용자가 지시했나" 분기 구조는 원문대로 둠. HAS 분기 → "PHASE 2를 직접 수행"(G7-4), NOT 분기 → 질문 대신 "모든 group을 순서대로, PHASE 2를 직접, 첫 group부터"(G4-4) | 최소 편집. 어느 분기든 PHASE 2로 가고, G4-5 반복 규칙이 나머지 group을 처리 |
| 8 | G4-5 "assigned" 정의 | "assigned" = 현재 group | 첫 문장 뒤에 한 문장 추가("The tasks assigned to you are those of the current task group: one task group per pass of PHASE 2."). 원문 "assigned" 표현은 유지 | 정의를 한 번만 두고 3번 줄 "the assigned task group"도 그대로 읽히게 |
| 9 | G9-1 적용 위치 | group의 테스트 2–8개와 마지막 group 최대 10개를 `S/checks/` 스크립트로 | tasks 예시(G9-4 원문 유지)는 그대로, create-tasks-list "Important Constraints"에 한 항목 추가("Write these tests as check scripts outside the repository … The test-writing standard applies to these scripts."), implement "Self-verify" 줄에 괄호 한 구절 추가. test-writing 표준 파일은 무변경 | G9-4가 예시 원문 유지를 정했으므로 예시 밖 두 곳에 둠 |
| 10 | G1-3 문구 | 제품 맥락을 README, 패키징·빌드 정보, 문서 목차에서 | 세 항목의 굵은 이름(Read Product Mission / Roadmap / Tech Stack)과 하위 bullet은 원문 유지, "Load `agent-os/product/X.md`"만 교체: mission → README, roadmap → 문서 목차(`docs/` 차례), tech stack → `pyproject.toml`·`setup.py`·`setup.cfg`·`package.json`. 앞 문장에 "product 문서가 없으니 저장소에서" 한 문장 추가 | 세 파일 ↔ 세 출처 대응은 해석. 경로를 남기지 않아 에이전트가 없는 파일을 찾지 않게 |
| 11 | G1-1 "user's description" | 입력 = issue | Step 1 문장과 책임 목록 1번만 교체. Step 2의 "from the user's description"(문장·bash 주석)과 첫 줄 "You are helping me…"는 원문 유지, 진입 문서가 "user's description" = issue라고 정의 | 최소 편집 |
| 12 | G7-8 문구 | roadmap 만들지 말고 3절(G5-8 후 2절) `⚠️ No Updates Needed` + 이유 | 원문 Step 2 문장 유지 + 바로 뒤 한 단락 추가. 원문 문장 속 `agent-os/product/roadmap.md` 경로는 남음 | 결정이 "keep the step, add one line" |
| 13 | 엔진(`_port.py`) | 렌더 단계 필요 시 공용 변경 또는 build.py에서 구동, 4단계에 기록 | `_port.py` 무변경. build.py가 `_port.convert`(태그 편집·anchor 검사) → upstream `project-install.sh` 실행 → 4개 파일 수집·후처리를 직접 구동하고, `--list`/`--check`용 `main`을 자체 정의(openspec_ff와 같은 방식). `drift`는 `docs/commands/` 아래 남는 파일까지 검사 | 다른 port 소유 공용 엔진을 건드리지 않음 |
| 14 | 공백 정규화 | (언급 없음) | 편집한 원문과 최종 문서 모두 `_port.convert`와 같은 규칙으로 빈 줄 3개 이상을 2개로, 끝 개행 1개로 정리. 편집 없이 렌더하면 참조 렌더(`scratchpad/agentos-render`)와 바이트 동일(create-tasks만 빈 줄 하나 차이)함을 확인 | 다른 port와 같은 정규화, 의미 변화 없음 |
| 15 | "missing-section" 테스트 | stage 4 표준 테스트 | 이 port는 `Section`을 쓰지 않으므로, 대신 `{{workflows/...}}` 참조가 풀리지 않는 upstream(파일명 변경)이면 build가 실패하는지 검사 | gaps "Harness / build notes"대로 `Edit`만 사용 |
| 16 | 렌더 테스트용 upstream 위치 | — | 테스트 기본 경로 `../agent-os-v2.1.1`(rllm 옆) 또는 `AGENT_OS_V2_DIR`. 없으면 렌더 테스트 3개는 skip. 이번 검증은 `scratchpad/agentos-v2.1.1-wt`(tag worktree, HEAD = 고정 commit)로 실행 | 전체 clone의 HEAD는 v3이라 그대로 쓸 수 없음. worktree 생성법은 `build.py` docstring |
| 17 | 줄 수 | standards 펼침으로 약 +400줄, 편집 약 50건 | 4개 문서 986줄 → 1,329줄(+343). 렌더 전 편집 57건(env 32, semantic 25) + 렌더 단계 5건 | 실제 값 (G9-5, G5-8 반영 후) |
| 18 | backend migrations 표준 9줄 | (계획에 없음) | "Always commit migrations to version control …" 줄 삭제 | 4단계에서 발견한 새 gap G9-5, 사용자 결정(2026-10-16). G9-2의 커밋·브랜치 줄과 같은 종류 |
| 19 | 보고서 절 번호 | 2절 삭제(G5-6), 1·3·4절 번호 유지 | 3·4절 → 2·3절로 번호 다시 매김, roadmap 안내 문장의 "section 3" → "section 2 (Roadmap Updates)" | smoke 1에서 발견한 G5-8(3/8이 스스로 번호를 바꿈), 사용자 결정 |

## 구성 (`recipe/grpo/qwen3_5/workflows/agentos_v2/`)

| 파일 | 출처 | 내용 |
|---|---|---|
| `docs/core-workflow.md` | 직접 작성 | 진입 문서: 4개 명령 순서와 문서 경로, "feature" = issue가 요구하는 변경, spec 폴더 구조와 명령별 산출물, 자체 답변·텍스트 응답 금지, tasks.md 체크 기록, 저장소 규칙(`checks/`), `final-verification.md` 뒤 `finish` (92줄) |
| `docs/commands/{shape-spec,write-spec,create-tasks,implement-tasks}/<명령>.md` | Agent OS 원문을 변환 | upstream 설치 스크립트로 렌더한 명령 문서 4개, standards 내용 포함 (렌더 원문 395 / 134 / 254 / 203줄 → 359 / 273 / 389 / 311줄; 렌더 전 원문: 명령 11개 213줄, workflow 9개 753줄, standards 14개 132줄) |
| `build.py` | 직접 작성 | 원문 → docs 변환기: tag tree 복사 → 렌더 전 원문에 태그 편집 54건 → `tech-stack.md` 삭제·config 설정 → upstream `project-install.sh` 실행 → 4개 파일 수집 → standards 펼침·경로 접두사 → 금지 문구 검사. 편집마다 태그(env / semantic)와 gap ID. `--list`, `--check`. tag worktree 만드는 법을 docstring에 기록 |
| `instruction.md` | 직접 작성 | 첫 행동 = `/agent-os/core-workflow.md` 열기, `/agent-os`는 루트 바로 아래이며 `/testbed` 안에 없음. 다른 워크플로우와 다른 문장 |
| `system-prompt.j2` | SDK 기본 프롬프트 복사 | `<PROBLEM_SOLVING_WORKFLOW>` 섹션만 새로 작성(파이프라인 요약, 첫 행동, 명령 문서 순서, 답·검토 없음, 매 턴 도구 호출, 보고서 뒤 finish), 나머지 15개 섹션은 SDK 기본과 동일 |
| `__init__.py` | — | SPEC 등록 정보: `container_dir="/agent-os"`, `entry_doc="core-workflow.md"`, `output_dirs=("/tmp/agent-os",)`, sandbox_files·setup_script·agent_image_extra 없음, 채점기 없음 |
| `LICENSE-agent-os` | Agent OS 원문 그대로 복사 | MIT 고지 (`LICENSE`, CasJam Media LLC) |
| `porting/01-survey.md` ~ `03-plan.md`, `05-changes.md`, `later.md` | 단계별 기록 | 조사·gap·결정·계획·변경, 나중에 시도할 아이디어 |

패키지 밖: `recipe/grpo/qwen3_5/tests/test_agentos_v2.py`(신규, 11개 테스트), `workflows/__init__.py`(등록 한 줄),
`recipe/grpo/qwen3_5/README.md`(workflow 표 한 줄), `docs/guides/workflows/adding-a-workflow.md`(등록 목록 문장).

편집 목록: `python -m recipe.grpo.qwen3_5.workflows.agentos_v2.build --list` (렌더 전 편집 54건: env 30 · semantic 24, 렌더 단계 5건).

## 수정한 내용

### 각 단계 수행 방식 변화

| Before (upstream Agent OS v2.1.1, "다른 도구용" 설치) | After (rllm) |
|---|---|
| 1. **사람**이 `~/agent-os`를 설치하고 프로젝트에서 `project-install.sh`를 실행합니다(`agent_os_commands: true`). `agent-os/commands/<명령>/`에 명령 파일, `agent-os/standards/`에 standards 15개가 생깁니다.<br>2. **사람**이 agent 앱(Cursor 등) 채팅에 `@agent-os/commands/shape-spec/shape-spec.md <기능 설명>`을 넣습니다.<br>3. **agent 앱**이 파일과 그 안의 `@agent-os/standards/...` 참조 내용을 함께 불러옵니다.<br>4. agent(LLM)가 지침을 읽고 작업합니다.<br>  • shape-spec은 질문 4–8개를 출력하고 **멈춰서 사람의 답**을 기다립니다(후속 질문도 같음).<br>  • 산출물(`agent-os/specs/<날짜>-<이름>/` 아래)과 코드 수정은 **agent가 직접 파일로 씁니다**.<br>5. 명령이 끝나면 agent가 확인 메시지와 "다음 명령을 실행하라"는 안내를 출력하고 멈춥니다.<br>6. **사람**이 결과를 검토하고 다음 명령(write-spec → create-tasks → implement-tasks)을 넣습니다. implement-tasks는 "전부 진행할까요?", "남은 것도 할까요?"를 물을 때마다 **사람이 답합니다**. | 1. 처음 받는 task 메시지가 사람의 입력을 대신합니다(instruction + SWE task 본문의 issue). build가 upstream 설치 스크립트로 미리 렌더한 문서 5개가 sandbox의 `/agent-os/`(파일시스템 루트, 저장소 밖)에 올라가 있습니다.<br>2. agent가 첫 행동으로 `/agent-os/core-workflow.md`를 읽고, 4개 명령 문서(`/agent-os/commands/<명령>/<명령>.md`)를 순서대로 엽니다.<br>3. agent(LLM)가 지침을 읽고 작업합니다.<br>  • 질문은 원문 양식대로 만들되 **issue와 저장소를 근거로 스스로 답해** requirements.md에 `**Answer:** (assumed) <답> — <근거>`로 기록합니다. 재사용 질문은 저장소를 직접 검색해 답합니다.<br>  • standards 내용은 각 명령 문서 안에 이미 들어 있습니다.<br>  • 산출물은 `/tmp/agent-os/specs/<날짜>-<이름>/`(저장소 밖)에, 코드 수정은 `/testbed`에 씁니다. 테스트는 `S/checks/`의 스크립트로 씁니다.<br>4. 명령이 끝나면 agent가 멈추지 않고 **다음 명령 문서를 열어 계속합니다**. implement-tasks는 미체크 group이 없을 때까지 PHASE 2를 group마다 반복하고, 검증(전체 테스트 실행, 보고서)을 한 번 한 뒤 `final-verification.md`를 쓰고 `finish`합니다. 반복 라운드는 없습니다. |

### 수정 사항

| # | 범주 | 내용 |
|---|---|---|
| 1 | **사람 피드백이 필요한 부분 삭제** | shape-spec 질문 출력 후 STOP(2회)을 자체 답변(`(assumed) <답> — <근거>`) 기록으로 교체, "사용자 답 원문 저장" → "가정한 답과 근거 기록". 재사용 질문은 agent가 저장소를 검색해 답하고 "직접 열지 말 것"과 재사용 후속 질문 삭제. 시안 요청과 "답해 달라" 맺음말 삭제(폴더·필수 `ls`·"시안 없음" 문구는 유지). create-tasks의 "spec 위치를 알려 달라" 대신 `/tmp/agent-os/specs/` 아래 폴더 찾기, 없으면 shape-spec·write-spec 먼저. implement-tasks의 "전부 진행?"을 "모든 group 순서대로"로, "남은 것도?"를 group 반복으로 교체. "Review it closely" 삭제. roadmap 다음 항목을 제안하고 기다리는 분기 삭제 |
| 2 | **보고 후 멈춤 → 다음 단계로 진행** | 명령 끝 "Display confirmation and next step" 블록 4개를 "## Next step: … 다음 명령 문서를 열고 계속"으로 교체(슬래시 명령·틀린 파일명 안내, `/orchestrate-tasks` 삭제). orchestrator에게 출력·반환하는 블록(Step 4 Output Confirmation, Step 7 Output Completion) 삭제, 구현 요약 표시 삭제. implement PHASE 2 끝의 "`3-verify-implementation.md` 실행"을 "아래 PHASE 3으로 계속"으로 교체. 진입 문서: 텍스트 응답 금지, 최종 보고서 뒤 `finish` |
| 3 | **이름·경로 고정** | spec 폴더 위치를 `agent-os/specs/`에서 `/tmp/agent-os/specs/`로 이동(날짜 + agent가 지은 이름 규칙, "Always use dated folder names", 자리표시 `[this-spec]`·`[current-spec]`·`[spec-path]`·`$SPEC_PATH`는 원문 유지). 최종 보고서 `final-verification.html` → `.md`. PHASE 1에서 `verifications/` 폴더도 생성("2 folders"가 실제로 2개) |
| 4 | **실행 환경 구성** | build가 v2.1.1 tag tree를 임시 `$HOME/agent-os`로 복사하고 원문 설치 스크립트(`project-install.sh`, config `claude_code_commands: false`, `agent_os_commands: true`)를 오프라인으로 실행해 렌더. top-level 명령 파일 4개만 수집, 번호 붙은 PHASE 파일은 미배포. 문서 5개(`core-workflow.md` + 명령 4개)를 `/agent-os/`에 업로드. `output_dirs=("/tmp/agent-os",)` |
| 5 | **agent 앱 전용 요소 삭제** | `@agent-os/standards/...` 참조 목록을 각 파일 내용으로 펼쳐 넣음(shape-spec 5개, 나머지 14개). 첫머리 "번호 붙은 파일을 순서대로 읽고 실행" → "아래 PHASE를 순서대로, 하나를 끝내고 다음". implementer 서브에이전트 위임 → 직접 수행. orchestrator 언급 삭제, spec-writer·spec-shaper → "the write-spec stage"·"the shape-spec stage", tasks 예시의 폐지된 역할 이름(database-engineer 등) → task 번호와 group 이름. 브라우저 확인 문장 삭제 |
| 6 | **SWE task 조건에 맞춤** | task group마다 쓰는 테스트 2–8개와 테스트 검토 group의 추가 테스트를 저장소 테스트 파일이 아닌 `S/checks/` 아래 스크립트로 작성·실행(create-tasks 제약 한 항목, implement 자체 검증 줄). 진입 문서: 작업·임시 파일은 `S/`·`S/checks/`, `/testbed`에는 워크플로우 파일을 두지 않음, 저장소 테스트 파일 추가·수정 금지 |
| 7 | **절차 구조 변경** | implement-tasks를 "호출 한 번에 group 하나"에서 "미체크 group이 남으면 PHASE 2 반복, 모두 체크되면 PHASE 3 한 번"으로 변경("assigned" = 현재 group). shape-spec PHASE 1에 issue 원문을 `planning/initialization.md`로 저장하는 Step 4 추가(원문 책임 목록에 있으나 단계가 없던 것) |
| 8 | **환경 사실 명시** | product 문서(mission·roadmap·tech-stack)가 없으므로 제품 맥락은 저장소의 README, 문서 목차, 패키징·빌드 정보에서 파악. roadmap은 만들지 말고 보고서 2절(Roadmap Updates)에 `⚠️ No Updates Needed`와 이유 기록. 진입 문서·instruction·system prompt: `/agent-os`는 루트 바로 아래이며 저장소 밖, 자리표시 4종은 같은 spec 폴더, standards 이름표는 열 파일이 아님, tasks.md 체크박스가 기록(TaskTracker는 보조) |
| 9 | **harness·데이터셋 설정** | `swegym293_aidlc` + instruction prefix, `--hide-git-history`(실행 설정, 문서 변경 없음). system prompt의 SDK 절차 섹션을 agentos_v2용으로 새로 작성, SDK의 "ask the user"·"confirm with the user" 문구는 유지 |
| 10 | **범위·방식 결정** | bugfix·feature 모두 한 workflow로("feature = issue가 요구하는 변경, 수정이든 추가든"). plan-product 제외. standards 정리: `tech-stack.md`(빈 양식) 미설치, conventions 7줄(README 최신화·커밋/브랜치/PR·의존성 최신화·코드 리뷰·머지 전 테스트·feature flag·changelog) 삭제, coding-style 3줄(dead code 삭제·하위 호환 무시·DRY) 삭제. 폐지된 구현 보고서 흔적 삭제(보고서 폴더 설명, 보고서 존재 확인, 보고서 2절). 네트워크·설치 금지 규칙은 추가하지 않음 |
| 11 | **원문 유지** | 검증 단계의 "테스트 전체 실행"과 "실패는 고치지 말고 기록만"; requirements·spec 템플릿(User Stories 포함); tasks의 웹앱 예시 구조와 "Group tasks by specialization"; 보고서 머리 `Verifier: implementation-verifier`; "Use Read tool", "THINK HARD"; 날짜 + 이름 폴더 규칙과 자리표시; visuals 폴더, 필수 `ls`, 시안 관련 후속 질문·템플릿; 질문 양식 문장; write-spec의 코드 검색 단계; 나머지 standards 11개 파일 전체 |

**적용 위치** (범주와 별개)
- **렌더 전 원문 편집**: `build.py`가 v2.1.1의 `commands/*/single-agent/*.md`(11건), `workflows/**`(40건), `standards/global/{conventions,coding-style}.md`(3건)에 태그 편집 적용, 총 54건(`--list`). 범주 1, 2, 3, 5, 6, 7, 8, 10
- **렌더 단계**: `standards/global/tech-stack.md` 삭제(범주 10), base `config.yml` 두 줄(범주 4), upstream 설치 스크립트 실행·4개 파일 수집(범주 4, 5), `@agent-os/standards/...` 줄 → 파일 내용(범주 5), `agent-os/specs/` → `/tmp/agent-os/specs/`(범주 3)
- **환경 파일**: `__init__.py`(container_dir `/agent-os`, entry_doc, output_dirs), `LICENSE-agent-os`. 범주 4
- **새로 작성**: `core-workflow.md`(명령 순서, 입력 정의, spec 폴더와 산출물, 자체 답변, 텍스트 응답 금지, tasks.md 기록, 저장소 규칙, finish), `instruction.md`, system prompt 절차 섹션. 범주 1, 2, 6, 8, 9

## agent 행동 변화

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | shape-spec PHASE 1 | 책임 목록에 "**Save Raw Idea**: Document the user's exact description without modification"이 있으나 실행 단계가 없어 아무것도 저장하지 않음 (`U/workflows/specification/initialize-spec.md#L7`) | **새 행동 추가**: Step 4 "Save Raw Idea"에서 issue 원문을 `$SPEC_PATH/planning/initialization.md`에 그대로 저장. PHASE 2 Step 1이 그 파일을 읽음 | 원문이 읽는 파일을 쓰는 단계가 없음 (G1-2) | 가능하지만 PHASE 2가 없는 파일을 읽음 |
| 2 | shape-spec PHASE 2 Step 2 | "Load `agent-os/product/mission.md` / `roadmap.md` / `tech-stack.md`" (`U/workflows/specification/research-spec.md#L22-L37`) | 같은 세 항목을 **저장소의 README, 문서 목차(`docs/`), 패키징·빌드 정보(`pyproject.toml` 등)**에서 파악 | product 문서 없음, plan-product 제외 (G1-3) | 불가 (파일 없음) |
| 3 | shape-spec PHASE 2 (질문) | 질문 4–8개 + 재사용 질문 + 시안 요청을 사람에게 출력하고 STOP, 후속 질문도 STOP (`research-spec.md#L45-L92`, `#L138-L148`) | 같은 양식으로 질문을 쓰되 **보내지 않고 스스로 답함**. 답은 `**Answer:** (assumed) [답] — [근거]`로 requirements.md에 기록, 후속 질문(1–3개)도 같은 방식. 시안 요청은 삭제, 시안 폴더 `ls`는 그대로 | 답할 사람 없음, 질문 생성 행동은 유지 (G4-1, G4-3) | 불가 (STOP = 세션 종료) |
| 4 | shape-spec PHASE 2 (재사용) | 사람에게 비슷한 기능 경로를 묻고, 알려 준 경로는 "**DO NOT explore them yourself (to save time)**", 이름만 기록; 알려 주지 않으면 다시 물음 (`research-spec.md#L68-L75`, `#L115-L117`, `#L129-L131`) | **새 행동 추가**: agent가 **저장소를 검색**해 비슷한 기능·컴포넌트·backend 로직을 찾아 `(assumed) <path> — <basis>`로 기록, 없으면 "No similar existing features identified for reference." **원래 행동 삭제**: "직접 열지 말 것", 재사용 후속 질문 | 코드베이스를 아는 사람의 역할을 agent가 맡음, G4-1과 일관 (G4-2) | 불가 (답할 사람 없음) |
| 5 | create-tasks, implement PHASE 2 | group마다 "x.1 **Write 2-8 focused tests**" → 구현 → 그 테스트만 실행, 테스트 검토 group "Write up to 10 additional strategic tests". 테스트는 저장소 안 (`U/workflows/implementation/create-tasks-list.md#L41`, `#L157`, `#L197`) | **새 행동 유도**: 같은 순서로, 테스트를 `S/checks/` 아래 스크립트로 작성·실행(create-tasks 제약 항목, implement 자체 검증 줄). 저장소 테스트 파일은 추가·수정하지 않음 | SWE task의 테스트 수정 금지, 채점 시 test patch 충돌 (G9-1) | 가능하지만 patch 오염·채점 충돌 위험 |
| 6 | implement PHASE 1 | 지정된 group이 없으면 "**Should we proceed with implementation of all task groups in tasks.md?**" 묻고 대기 (`U/commands/implement-tasks/single-agent/1-determine-tasks.md#L7-L13`) | tasks.md의 **모든 group을 순서대로**, 첫 group부터 PHASE 2를 직접 수행 (질문이 제안한 쪽) | 답할 사람 없음 (G4-4) | 불가 (답할 사람 없음) |
| 7 | implement PHASE 2 | "Implement … **ONLY those task(s) that have been assigned to you**", 남으면 "**Would you like to proceed with implementation of the remaining tasks?**" (`U/workflows/implementation/implement-tasks.md#L1`, `U/commands/implement-tasks/single-agent/2-implement-tasks.md#L17-L23`) | **새 행동 추가**: 한 번에 현재 group 하나, 미체크 task가 남으면 다음 group으로 PHASE 2 반복, 모두 체크되면 PHASE 3 | 사람이 다시 호출하던 반복을 agent가 이어 감 (G4-5) | 불가 (첫 group 뒤 세션 종료) |
| 8 | implement PHASE 2 | "IF your task involves user-facing UI, and IF you have access to browser testing tools, open a browser…" (`implement-tasks.md#L16`) | **원래 행동 삭제** | 사용자 결정 (G6-2) | 가능 (도구가 없어 조건이 거짓) |
| 9 | implement PHASE 3 Step 1, 보고서 | 미완료 task는 "Check for existence of an implementation report … in `agent-os/spec/[this-spec]/implementation/`", 보고서 2절 "Documentation Verification" (`U/workflows/implementation/verification/verify-tasks.md#L5`, `create-verification-report.md#L37-L49`) | **원래 행동 삭제**: 보고서 확인 항목과 2절. 미완료 판단은 원문의 코드 spot check로만. 보고서는 1·2·3절(G5-8로 번호 다시 매김) | v2.1.0에서 폐지된 구현 보고서의 흔적 (G5-6) | 가능하지만 항상 "없음" |
| 10 | implement PHASE 3 Step 2 | "Open `agent-os/product/roadmap.md` and check … mark … `- [x]`" (`U/workflows/implementation/verification/update-roadmap.md#L1`) | **새 행동 추가**: 원문 문장 뒤 "이 프로젝트에는 roadmap이 없으니 만들지 말고, 보고서 2절 Status `⚠️ No Updates Needed`, Notes에 이유" | roadmap 없음, plan-product 제외 (G7-8) | 가능하지만 없는 파일을 열거나 만들 위험 |
| 11 | 모든 명령 (standards) | conventions: README 최신 유지, 커밋·feature branch·PR, 의존성 최신화, 코드 리뷰, 머지 전 테스트, feature flag, changelog (`U/standards/global/conventions.md#L4-L11`) | **원래 행동 삭제**: 7줄 삭제 (3·6줄만 유지) | 팀 절차·issue 밖 작업, 의존성 최신화의 네트워크 사용 (G9-2) | 가능 (`later.md`의 실제 개발 관례 변형) |
| 12 | 모든 명령 (standards) | coding-style: "Remove Dead Code", "Backward compatibility only when required: … assume you do not need …", "DRY Principle" (`U/standards/global/coding-style.md#L8-L10`) | **원래 행동 삭제**: 3줄 삭제 | issue 밖 정리·리팩터링, 기존 동작 파손 위험 (G9-3) | 가능 (같은 변형) |

**표에서 뺀 것**: spec 폴더 위치(`/tmp/agent-os/specs/`), 보고서 `.md`, `verifications/` 폴더 생성, 다음 명령 문서 연결과 `finish`, 출력·반환 블록 삭제(G2-1), create-tasks의 위치 질문 → 폴더 찾기(G2-3 rev), roadmap 다음 항목 제안 분기 삭제(G1-1), "Review it closely" 삭제(G4-6), 서브에이전트 위임 → 직접 수행(G7-4), 호칭·역할 이름 정리(G7-5), 첫머리 PHASE 안내(G7-2), standards 펼쳐 넣기(G7-3), `tech-stack.md` 빈 양식 삭제(G7-6).

**6단계 smoke에서 발생을 확인할 새 행동 추가**: #1 initialization.md 작성, #4 재사용 저장소 검색과 `(assumed) <path>` 기록, #7 group 반복, #10 roadmap `⚠️ No Updates Needed`. 함께 볼 것: #3 `(assumed)` 답 기록 여부와 텍스트 응답으로 끝나는 비율, spec 폴더 개수(G5-2), 전체 테스트 실행 시간과 세션 정지 여부(G8-2), task group 수(G9-4), 명령별 step 수(G8-4), `S/checks/` 사용과 저장소 테스트 파일 변경 여부(G9-1).

## 변경

**1. 사람이 입력하던 기능 설명 → issue** (shape-spec.md, core-workflow.md)
- 원문은 명령과 함께 사람이 입력한 기능 설명을 받고, 없으면 roadmap 다음 항목을 제안하고 기다림. 책임 목록 1번과 Step 1을 "issue in `<issue_description>`"으로 교체, OTHERWISE 분기와 출력·대기 블록 삭제 (G1-1, env).
- 진입 문서에 "feature = issue가 요구하는 변경(수정이든 추가든)", "user's description" = issue 명시 (G1-1).
- PHASE 1 Step 4 "Save Raw Idea" 신설: issue 원문을 `planning/initialization.md`에 그대로 저장, 원문 Step 4 Output Confirmation 자리 (G1-2, env).

**2. 제품 문서 → 저장소** (shape-spec.md, implement-tasks.md)
- 원문은 `agent-os/product/{mission,roadmap,tech-stack}.md`를 읽음. 세 항목의 읽는 대상을 README, 문서 목차, 패키징·빌드 정보로 교체하고 "product 문서 없음" 한 문장 추가 (G1-3, env).
- 검증 Step 2(roadmap 체크)는 원문 유지, "roadmap 없음, 만들지 말 것, 2절 `⚠️ No Updates Needed` + 이유" 한 단락 추가 (G7-8, env).

**3. 사람에게 묻고 기다리기 → 스스로 답하고 기록** (shape-spec.md, create-tasks.md, implement-tasks.md) — **semantic** 포함
- shape-spec 질문: 생성 규칙·양식 유지, "Required output format" → "Required format", "OUTPUT … and STOP" → "보내지 말고 issue·저장소로 스스로 답하고 근거를 남김", 후속 질문 머리·"Then STOP" 교체, Step 4 "receiving user's answers from the orchestrator" → "after answering the questions yourself", 제약 "Save user's exact answers" → "Record each assumed answer and its basis", 마지막 제약 "OUTPUT questions and STOP" 삭제, 템플릿 `**Answer:** [User's answer]` 3곳 → `(assumed) [your answer] — [its basis…]` (G4-1, **semantic**).
- 재사용: Step 4의 "IF user provided paths … DO NOT explore them yourself" → "저장소를 검색해 답하고 `(assumed) <path> — <basis>`로 기록, 없으면 'No similar existing features identified for reference.'", 재사용 후속 질문 삭제, 템플릿 "Existing Code to Reference"·"Reusability Opportunities"를 검색 결과 기준으로 변경 (G4-2, **semantic**).
- 시안: 요청 블록, 맺음말 요청, Step 3 제목·CRITICAL 줄의 시안 요청 문구 삭제, 폴더·필수 `ls`·fallback 유지 (G4-3, env).
- create-tasks PHASE 1: "ask user … wait" → "`/tmp/agent-os/specs/` 아래 spec 폴더를 찾아 읽고, 없으면 shape-spec·write-spec 문서 먼저", 슬래시 명령 삭제 (G2-3 rev, env).
- implement PHASE 1: "Should we proceed with all task groups? … WAIT" → "모든 group을 순서대로, 첫 group부터 PHASE 2" (G4-4, **semantic**).
- implement PHASE 2 끝: "remaining tasks?" 질문 → "미체크 task가 남으면 다음 group으로 PHASE 2 반복", 첫 문장 뒤 "assigned = 현재 group" 정의 (G4-5, env).
- 진입 문서: 아무도 답하지 않음, 질문은 스스로 답해 기록, 텍스트 응답 금지 (G4-1, G2-1).

**4. 보고 후 멈춤 → 다음 명령 문서로** (네 명령 문서 전부, core-workflow.md)
- 원문 "Display confirmation and next step" 블록(틀린 파일명 `1-create-spec.md`·`2-create-tasks-list.md`, 슬래시 명령 `/write-spec`·`/implement-tasks`·`/orchestrate-tasks`)을 "## Next step — Once …, open `/agent-os/commands/<다음>/<다음>.md` and continue with that command."로 교체 (G2-2, env), "Review it closely" 함께 삭제 (G4-6, env).
- implement PHASE 2: "Display a summary", "Run `3-verify-implementation.md`" → "continue with PHASE 3 below" (G2-2, G2-1, env).
- orchestrator에게 출력·반환하는 PHASE 1 Step 4와 PHASE 2 Step 7 블록 삭제 (G2-1, env), "Pass the exact spec path back to the orchestrator" 삭제 (G7-5 ①, env).
- 진입 문서: `S/verifications/final-verification.md`가 쓰이면 `finish` (G8-1).

**5. 렌더 방식과 배포 문서** (build.py, docs/commands/*)
- upstream 설치 스크립트를 임시 폴더에서 그대로 실행해 렌더, top-level 명령 파일 4개만 `/agent-os/commands/<명령>/<명령>.md`로 배포, 번호 붙은 PHASE 파일 미배포 (G7-1, env).
- 첫머리 "read and execute the instructions in the following files IN SEQUENCE, following their numbered file names …" 두 문장 → "Carefully carry out the PHASE sections below in order, finishing one before the next." (shape-spec·create-tasks·implement-tasks, G7-2, env).
- `@agent-os/standards/<dir>/<file>.md` 줄 → 이름표 + 파일 내용, 앞 문장("Ensure that … is ALIGNED and DOES NOT CONFLICT …")은 유지. standards 별도 배포 없음 (G7-3, env). G5-4는 이로 대체됨.
- `standards/global/tech-stack.md` 설치 전 삭제 → 목록과 펼친 내용에서 빠짐 (G7-6, **semantic**).

**6. 경로·폴더** (네 명령 문서, core-workflow.md, `__init__.py`)
- `agent-os/specs/` 접두사 → `/tmp/agent-os/specs/` (렌더 후 치환, 자리표시와 날짜 + 이름 규칙 유지) (G5-1, G5-2, G5-3 rev, env). `output_dirs=("/tmp/agent-os",)`.
- PHASE 1 "Create 2 folders"에 `verifications/` 추가, "Leave these folders empty" (G5-5, env). 보고서 `final-verification.html` → `.md` (G5-5, env).
- "Later, this folder will be populated with reports documented by implementation agents", 보고서 존재 확인 항목(오타 경로 `agent-os/spec/`), 보고서 2절 Documentation Verification 삭제 (G5-6, **semantic**).
- 진입 문서: spec 폴더 구조와 명령별 산출물, 자리표시 4종은 같은 폴더, `S/checks/`는 필요할 때 생성 (G5-2, G5-3 rev, G5-7).

**7. 다른 에이전트·도구 흔적** (shape-spec.md, write-spec.md, create-tasks.md, implement-tasks.md)
- "delegate … to the **implementer** subagent" → "carry out … yourself" (G7-4, env).
- "for spec-writer" → "for the write-spec stage"(2곳), "gathered by spec-shaper" → "by the shape-spec stage", tasks 예시 "written by database-engineer / api-engineer / ui-designer (Task N.1)" → "written in Task 1.1 (Data Models and Migrations)" / "Task 2.1 (API Endpoints)" / "Task 3.1 (UI Design)" (G7-5 ②③, env). `**Verifier:** implementation-verifier` 유지 (G7-5 ④).
- 브라우저 확인 문장 삭제 (G6-2, env). "Use Read tool", "THINK HARD" 유지 (G7-7).

**8. 테스트는 저장소 밖 스크립트로** (create-tasks.md, implement-tasks.md, core-workflow.md) — **semantic**
- create-tasks "Important Constraints"에 "Write these tests as check scripts outside the repository …, under `S/checks/` … The test-writing standard applies to these scripts." 추가, implement 자체 검증 줄에 "they are check scripts under `S/checks/`, not repository test files" 추가. 예시 템플릿(group 구조, 2–8개, 최대 10개)은 원문 유지 (G9-1, **semantic**; G9-4).
- 진입 문서: 저장소 테스트 파일 추가·수정 금지, 워크플로우 파일은 `/testbed`에 두지 않음 (G9-1, G5-7).

**9. standards 내용 정리** (네 명령 문서의 펼친 standards) — **semantic**
- conventions 4·5·7·8·9·10·11줄 삭제(README·버전 관리·의존성·코드 리뷰·머지 전 테스트·feature flag·changelog), 1·3·6줄 유지 (G9-2, **semantic**).
- coding-style 8·9·10줄 삭제(dead code·하위 호환·DRY), 1–7줄 유지 (G9-3, **semantic**).
- backend/migrations 9줄 삭제(migration을 version control에 커밋), 1–8줄 유지 (G9-5, **semantic**).
- 최종 보고서 절 번호를 1·2·3으로 다시 매김(Tasks Verification, Roadmap Updates, Test Suite Results), roadmap 안내 문장도 2절로 (G5-8, env).

**10. 원문 유지로 결정한 것** (문서 변경 없음)
- 검증 Step 3 전체 테스트 실행과 "DO NOT attempt to fix any failing tests" (G8-2, G8-3), requirements·spec 템플릿 (G1-4), 웹앱 tasks 예시 (G9-4), 명령별 step 수 측정은 smoke (G8-4), 네트워크·설치 규칙 없음 (G6-1).

**11. harness 설정** (instruction.md, system-prompt.j2, `__init__.py`)
- instruction: 첫 행동 `/agent-os/core-workflow.md`, `/agent-os`는 루트 바로 아래이며 `/testbed` 밖 (G10-4).
- system prompt 절차 섹션 새로 작성, 나머지 15개 섹션은 SDK 기본, SDK의 "ask the user" 문구 유지 (G10-1, G10-2). 실행 설정 `swegym293_aidlc`, `prefix`, `--hide-git-history` (G10-3). tasks.md 체크박스가 기록, TaskTracker 보조 (G10-5, 진입 문서).

새로 쓴 문서(upstream 대응 없음): `docs/core-workflow.md`, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션.

## 검증 (2026-10-16)

- `python -m recipe.grpo.qwen3_5.workflows.agentos_v2.build --upstream <v2.1.1 worktree> --check` → exit 0 (렌더 약 2.5초, bash + perl).
- 편집 없이 렌더한 4개 파일 = 참조 렌더 `scratchpad/agentos-render/project/agent-os/commands/` (빈 줄 정규화 기준 4/4 동일).
- `pytest recipe/grpo/qwen3_5/tests/` → 147 passed (`AGENT_OS_V2_DIR` 지정). `test_agentos_v2.py` 11개 중 렌더 3개는 upstream 없으면 skip.
- guide §8 빠른 점검: 업로드 항목 `commands/`, `core-workflow.md`, `.md` 5개; instruction이 task 앞에 붙음; 채점기 없음(resolve rate만, 경고 1줄).
