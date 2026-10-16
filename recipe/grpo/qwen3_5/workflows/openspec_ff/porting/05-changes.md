# Changes: openspec_ff  (upstream Fission-AI/OpenSpec@9111a76, npm 1.14.1)

explore 단계 추가(2026-10-15)는 맨 아래 "Explore extension" 절. 아래 기존 기록은 ff → archive 부분.

원문: `skills/openspec-{new-change,ff-change,apply-change,verify-change}/SKILL.md`(stage 문서 4개),
`schemas/spec-driven/schema.yaml` + `templates/*.md`(CLI가 서빙하는 artifact 지침). 편집 목록은
`python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --list`.

## agent 행동 변화

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | ff (proposal·specs) | 기존 spec이 있으면 Modified Capabilities, MODIFIED·REMOVED delta 사용 | 모든 기능을 New Capabilities로, 버그 수정도 "고쳐진 동작"을 새 요구사항(ADDED)으로 작성 | `/openspec/specs/`가 비어 있음, upstream의 기존 프로젝트 첫 change 방식 (G7-5, G10-7) | 가능하지만 archive 검증 실패·우회 증가 (smoke run 2) |
| 2 | ff (design·tasks) | 계획을 바꾸는 Open Question은 사용자에게 확인 | agent가 직접 결정, design.md **Decisions**에 선택·근거 기록 | 답할 사람 없음 (G4-3) | 불가 (질문 = 종료) |
| 3 | ff (tasks) | task 그룹마다 자기 **테스트·문서 추가** | 기존 저장소 테스트 실행 또는 `checks/` 스크립트 작성·실행으로 검증, 테스트 파일 추가·수정 금지, 문서는 issue가 요구할 때만 | SWE task의 테스트 수정 금지·최소 수정과 충돌 (G9-1, G9-2) | 가능하지만 테스트 파일 수정·patch 오염 위험 |
| 4 | ff (tasks 예시) | 예시: 의존성 설치(1.2), 단위 테스트(2.2), 문서 작성(2.3) | **새 행동 유도**: 현재 코드에서 실패하는 check 먼저 작성(1.2), 기존 테스트+check 실행(2.2), 관련 테스트 모듈 회귀 확인(2.3) | 3번과 일치, 네트워크 없음 (G9-4) | 가능, 단 설치 task는 실행 불가 |
| 5 | apply | spec 밖 작업 필요 시 범위를 알리고 질문, 몰래 흡수 금지 | tasks.md(관찰 가능한 동작이면 delta spec에도)에 task로 추가 후 수행, 명세 축소 금지는 유지 | 답할 사람 없음 (G4-6) | 불가. 대안: 미체크 + 사유 |
| 6 | apply | 설계 문제 발견 시 artifact 수정 **제안** | design·specs·tasks를 직접 수정, 무엇을·왜 기록 | G4-5 | 불가 |
| 7 | apply | 완료 = 모든 task 체크, 막히면 멈춤 | 완료 = 모든 task 체크 또는 남은 미체크마다 한 줄 사유, 막힌 task만 남기고 계속 | G4-7 | 불가 (멈춤 = 종료) |
| 8 | verify | coverage = "테스트가 있는가", 권고 "테스트 추가" | coverage = 기존 테스트나 `checks/` 스크립트로 검증됐는가, 권고 "check 추가 또는 코드 수정" | 3번과 일관성 (G9-3) | 가능하지만 테스트 금지와 충돌 |
| 9 | verify | 보고서를 채팅으로 표시 | 보고서를 `verify.md` 파일로 작성 | 텍스트 응답 = 종료, 산출물 수집 (G5-3) | 불가 |
| 10 | archive | archive skill: 미완료 확인 질문 → sync 선택 → **agent가 delta spec을 main spec에 직접 병합**·구조 점검 → 폴더 이동 | **원래 행동 삭제**: `openspec archive issue --yes` 한 줄(CLI가 검증·병합·이동) | 질문 분기가 대부분, upstream CLI 경로 존재 (D-5) | 가능하지만 질문 분기 재제거 필요 |
| 11 | archive | 순서·실패 처리 제약 없음 | **새 행동 추가**: `verify.md`가 있을 때만 archive, 저장소 수정은 archive 전에 완료, 실패 시 오류가 지목한 delta spec만 고쳐 한 번 재실행, 재실패 시 archive 없이 종료, `--no-validate` 금지 | verify 생략 방지 (G2-9), 재시도 반복·우회 방지 (G8-3, G8-4) | 가능하지만 verify 생략·archive 반복 증가 (smoke run 2) |

- 삭제한 새 행동: verify → apply 반복(1회차 CRITICAL → apply → `verify-2.md`, G8-1). val ablation에서 1회차 CRITICAL 0/60으로 한 번도 발동하지 않아 2026-10-14 삭제(`06-smoke.md`).

**표에서 뺀 것**: 이름·경로 고정(`issue`, `/openspec`, `/opsx`, `checks/`), 다음 단계 문서 연결과 new 단계 제거, 질문 → "가장 타당한 해석 + 기록" 단순 대체(G4-2, G4-4), store 선택·frontmatter 삭제, 네트워크·설치 금지.

## 변경

**1. 실제 openspec CLI를 sandbox에서 실행** (agent-image-extra.Dockerfile, setup.sh, \_\_init\_\_.py) — D-1, D-2, G10-5
- 원문은 사용자가 설치한 `openspec` CLI가 상태·경로·artifact 지침·검증·archive를 담당하는 구조. 다른 port처럼 CLI 출력을 문서에 옮겨 적지 않고 CLI 자체를 sandbox에 설치.
- node v22.23.3 + `@fission-ai/openspec@1.14.1`을 `/opt/rllm/agent/node`에 설치하는 Dockerfile 줄을 openhands-sdk agent image 레시피 끝에 추가(`agent_image_extra`). image tag가 이 줄까지 hash하므로 이 workflow만 별도 image 사용.
- setup.sh(agent 시작 전, root): telemetry·update check를 끈 `/usr/local/bin/openspec` wrapper 작성, `cd / && openspec init --tools none`으로 planning root `/openspec` 생성, `/testbed/openspec`이 있으면 실패 처리, 마지막에 `/testbed`에서 root가 `/`인지·fork가 project schema로 보이는지·`schema validate` 통과하는지 확인 후 아니면 rollout 중단.
- wrapper에 `CI=1` 추가(G10-6, smoke run 1에서 발견). agent 터미널이 TTY라 CLI가 대화형 모드로 동작하고 `new change`가 끝나지 않는 문제 대응. setup 마지막에 TTY 환경(`script -qec`)에서 `new change`가 60초 안에 끝나는지 확인.
- `output_dirs=("/openspec",)`로 planning tree 전체 수집.
- 결과적으로 project-root guard, CLI JSON 경로, `status`/`instructions`/`validate`/`archive` 동작은 원문 그대로 유지.

**2. schema fork로 CLI 지침 변경** (sandbox/schemas/spec-driven-sandbox/, setup.sh, \_\_init\_\_.py) — D-4, Q1
- 원문 CLI는 `schema.yaml`의 artifact 지침을 그대로 서빙하므로 stage 문서 편집으로는 바뀌지 않는 구조. upstream의 사용자 정의 방식(`openspec schema fork` + `config.yaml`의 `schema:`)으로 변경.
- fork 이름 `spec-driven-sandbox`. 산출물은 `openspec schema fork spec-driven spec-driven-sandbox` 결과(이름 변경, `requires: [ tasks ]` 공백)와 바이트 단위 동일 + 아래 3·10번 편집만 추가(CLI 1.14.1 실제 fork 결과와 diff로 확인).
- package 안 `sandbox/schemas/`에 두고 `/opt/rllm/openspec_ff/`로 upload, setup에서 `/openspec/schemas/`로 복사 후 `config.yaml`에서 선택. 템플릿 4개는 무변경.

**3. 질문·중단 분기 삭제** (02-ff.md, 03-apply.md, schema.yaml, core-workflow.md, system-prompt.j2) — G4-1~G4-7, G4-12 — **semantic 포함**
- 원문은 판단이 필요한 지점에서 사용자에게 묻거나 멈추고 지시를 기다리는 구조. rllm에서는 tool call 없는 응답이 곧 실행 종료이므로 해당 분기 전부 변경.
- ff: 대상 프로젝트를 `/testbed`로 고정하고 묻는 문장 삭제, "한계 명시"는 유지(G4-1, env). 맥락이 불명확하면 가장 타당한 해석을 택해 작성 중인 artifact에 가정으로 기록(G4-2).
- schema.yaml: design·tasks의 "계획을 바꾸는 질문은 사용자에게 확인"을 "직접 결정하고 선택과 근거를 **Decisions**에 기록"으로 변경, Open Questions는 미뤄도 되는 항목만(G4-3).
- apply 문서와 schema.yaml apply 지침: 불명확한 task는 specs/design 기준으로 가장 타당한 해석을 구현하고 `tasks.md`의 해당 task 아래 일반 줄로 기록(G4-4). 설계 문제는 artifact를 직접 갱신하고 변경 내용·이유 기록(G4-5). 범위 밖 작업은 `tasks.md`(관찰 가능한 동작이면 delta spec에도)에 task로 추가 후 수행, 명세 동작 축소 금지(G4-6). 오류·막힘은 해결 시도, 끝내 불가능한 task는 한 줄 사유와 함께 미체크로 두고 나머지 진행, "사용자 중단"과 Output On Pause 블록 삭제(G4-7).
- new: 잘못된 이름 재질문·기존 이름 안내 삭제(G4-12, env).
- 진행 상황 표시·보고는 tool call과 같은 turn에 두거나 artifact에 기록, `finish` 전 tool 없는 메시지 금지 명시(G2-7, core-workflow.md, system-prompt.j2).

**4. 사용자 입력을 issue 본문으로 대체** (01-new.md, 02-ff.md, 03-apply.md, 04-verify.md) — G1-1, G1-2, G1-3, G5-1
- 원문은 사람이 입력한 요청(change 이름 또는 설명)을 받고, 없으면 묻는 구조. 입력을 task 메시지의 `<issue_description>` 본문으로 명시하고 질문 단계 삭제.
- change 선택: 단일 change 자동 선택은 유지, 모호할 때 선택을 묻는 분기와 slash command 재지정 안내(`/openspec-apply-change <other>`) 삭제.
- schema 선택: 기본값(= config.yaml의 fork) 유지, 사용자에게 고르게 하는 분기와 `--schema` 관련 안내 삭제.

**5. 다음 명령 안내를 다음 단계 문서로 연결** (01-new.md, 02-ff.md, 03-apply.md, 04-verify.md) — G2-1~G2-5, D-3
- 원문은 각 action 끝에 멈추고 사람이 다음 slash command를 입력하는 구조(`STOP and wait`, "Run `/openspec-apply-change`…").
- new: artifact를 만들지 않는 점은 유지, change 생성 후 ff 문서로 이동(G2-1). ff: 마지막 artifact 후 apply 문서로 이동(G2-2).
- apply: `blocked`(artifact 누락) 시 ff 문서로 돌아가 보완 후 재개(G2-3), `all_done`·완료 시 verify 문서로 이동하고 archive 명령 안내 삭제(G2-4).
- verify: 최종 판정 뒤 회차 규칙(7번)에 따른 다음 단계 추가(G2-5).

**6. core-workflow 신규 작성** (core-workflow.md, instruction.md, system-prompt.j2, \_\_init\_\_.py) — G3-1, G10-1, G10-3, G10-4
- 원문에는 다섯 action을 잇는 agent용 문서가 없고 사람이 순서대로 입력하는 구조(`/opsx:new ──► /opsx:ff ──► /opsx:apply ──► /opsx:verify ──► archive`).
- 내용: action 표(열 문서, 시작 CLI 명령, 산출물), "actions, not phases" 설명, 고정 이름, 입력, 응답자 없음, 저장소 규칙, verify 회차, archive 후 finish.
- instruction.md와 system-prompt.j2 `<PROBLEM_SOLVING_WORKFLOW>`에 `/opsx/core-workflow.md`를 첫 행동으로 열 것, `/opsx`가 저장소 밖 filesystem root라는 점, `openspec` CLI가 단계를 진행한다는 점 명시. 나머지 system prompt 섹션은 SDK 기본값 그대로.
- SDK 기본 프롬프트의 "ask the user"·"confirm with the user" 줄은 비교 가능성을 위해 유지(Q6/G10-2).
- 평가 설정은 `swegym293_aidlc` + `instruction_position=prefix`(G10-3, 실행 설정 사항).

**7. ~~verify ↔ apply 반복 추가 (최대 2회)~~ — 2026-10-14 삭제, 아래 "추가" 참고** (04-verify.md, core-workflow.md) — G8-1, G5-3
- 원문 verify는 채팅으로 보고서를 보여주고 다음 행동은 사람이 판단하는 구조.
- 보고서를 change 디렉터리 파일로 작성: 1회차 `verify.md`, 2회차 `verify-2.md`(G5-3).
- 1회차에 CRITICAL이 있으면 그 항목만 apply로 돌아가 처리(미완료 task 완료, 구현 누락 요구사항은 task 추가 후 구현) 후 2회차 verify. 2회차 후에는 결과와 무관하게 archive, 남은 문제는 보고서에 기록. WARNING·SUGGESTION은 반복 사유 아님.

**8. archive를 CLI 한 번 실행으로 대체, archive·sync 문서 미포함** (core-workflow.md) — D-5, G8-3, G8-4 — **semantic 포함**
- 원문 archive skill은 미완료 확인, sync 여부 선택, 실패 시 사람에게 보고하는 대화형 구조(sync skill을 inline 실행).
- upstream CLI 경로 `openspec archive issue --yes`(검증, delta spec 병합, 이동을 확인 없이 수행)로 대체하고 archive·sync skill은 싣지 않음(G4-8~G4-11 drop, G2-6·G2-8 수정).
- 저장소 변경은 archive 전에 완료, archive 후 `finish`(G8-3).
- exit 1이면 오류가 지목한 delta spec 부분(형식 또는 누락 spec)만 고쳐 한 번 재실행, 다시 실패하면 archive 없이 `finish`. `--no-validate` 금지, tasks/apply로 복귀 금지(G8-4, semantic).

**9. 저장소 테스트·문서 추가 대신 checks 스크립트** (schema.yaml, 04-verify.md, core-workflow.md) — G9-1~G9-4 — **semantic**
- 원문 tasks 지침은 각 task 그룹이 자기 테스트와 문서를 함께 추가하도록 요구하는 구조. SWE task의 "테스트 파일 수정 금지, 비테스트 파일 최소 변경"과 충돌.
- schema.yaml tasks 지침: "각 task는 검증 방법을 명시"는 유지, 검증은 기존 저장소 테스트 실행 또는 `/openspec/changes/issue/checks/` 스크립트로, 테스트 파일 추가·수정 금지, 저장소 문서는 issue가 요구할 때만(합의 문안 그대로, G9-1·G9-2).
- 예시 task 1.2·2.2·2.3을 합의 문안으로 교체(의존성 설치·문서 작성 예시 제거), 1.1·2.1과 design의 "New external dependency" 조건은 유지(G9-4).
- verify scenario coverage: "테스트 존재 여부"를 "기존 테스트 또는 `checks/` 스크립트로 검증됐는지"로, 권고를 "`checks/`에 check 추가 또는 코드 수정"으로 변경(G9-3).

**10. 외부 접근 금지** (core-workflow.md) — G6-1 — **semantic**
- 원문 workflow 자체는 네트워크를 요구하지 않으나 issue의 링크가 정답 PR로 이어질 수 있는 환경.
- issue 링크 열기, 온라인 검색, 패키지 설치 금지 명시. CLI telemetry·update check는 wrapper에서 차단(1번). schema의 Impact 항목("dependencies")은 기록 필드라 유지.

**11. 이름·경로 고정** (01-new.md ~ 04-verify.md, core-workflow.md, \_\_init\_\_.py) — G5-1, G5-2, Q2
- 원문은 설명에서 kebab-case change 이름을 만들고 planning home을 저장소 안 `openspec/`에 두는 구조.
- change 이름 `issue` 고정(`"<name>"`, `<change-name>` 치환), planning root `/openspec`(저장소 밖), 문서 업로드 위치 `/opsx`, checks 디렉터리 `/openspec/changes/issue/checks/`.

**12. 쓰이지 않는 장치 정리** (01-new.md ~ 04-verify.md, core-workflow.md) — G7-1, G7-2, G7-3, G7-4, Q7
- skill frontmatter(`allowed-tools`, `compatibility` 등) 삭제(G7-2).
- 네 문서 공통 store 선택 단락 삭제: 등록된 store가 없어 실행되지 않는 조건부 장치(G7-3).
- ff의 `openspec new change` 재실행 단계와 "같은 이름이 있으면 이어가라고 제안" 삭제: new에서 이미 만든 change를 이어서 진행(G7-1).
- `/openspec/specs/`가 비어 있으므로 모든 delta는 새 capability의 `## ADDED Requirements`라는 문장을 core-workflow.md에 추가. MODIFIED/REMOVED/RENAMED 관련 원문은 형식 설명이라 그대로 유지(G7-4). `skip_specs` 규칙도 원문 그대로(Q5).

**원문 그대로 둔 부분**: project-root guard 단락(root가 `/`로 잡혀 분기가 발동하지 않음), CLI JSON 경로, apply의 checkbox 흐름(G8-2, 단계 수는 smoke에서 측정), verify의 판정 절차와 heuristics, 템플릿 4개.

**원문 없이 새로 쓴 문서**: `docs/core-workflow.md`, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션, `setup.sh`, `agent-image-extra.Dockerfile`.

**추가 (smoke run 2 이후, 2026-10-14)**
- 기존 spec이 없다는 사실을 CLI 지침에 명시(schema.yaml, G7-5): proposal Capabilities 항목과 specs 지침에 "`/openspec/specs/`가 비어 있으므로 모든 기능은 New, 모든 delta는 ADDED" 한 문장씩 추가. upstream의 기존 프로젝트 첫 change 방식(`docs/existing-projects.md`)과 동일. MODIFIED 설명 원문은 유지.
- verify 단계 오해 수정(core-workflow.md, G2-9): 단계 표의 verify 행에 "verify를 수행하는 `openspec` 명령은 없음, 직접 점검" 명시. archive 조건에 "`verify.md`가 있을 때만" 추가.

- new 단계 제거(D-7): 절차를 ff → apply → verify → archive로 변경. ff가 원문 2단계(`openspec new change "issue"`)로 change를 직접 생성. new 문서와 관련 편집(G1-3, G2-1, G4-12) 삭제, ff의 change 생성 단계는 upstream 원문으로 복원(G7-1 되돌림). 단계 문서 번호를 01-ff, 02-apply, 03-verify로 변경. 진입 문서와 instruction에서 new 삭제.
- 프로젝트 설정 사용(G10-7): upstream이 권하는 `config.yaml`의 `context:`와 `rules:`로 환경 사실을 전달. CLI가 모든 산출물 지침과 apply 지침에 context를, proposal과 specs 지침에 rules를 붙여 줌. G7-5 문장은 fork 본문에서 rules로 이동. operations guidance는 쓰지 않음. apply의 충돌 보고 분기가 생기지 않도록 사실만 적음(sandbox/openspec-config.yaml, setup.sh, \_\_init\_\_.py).
- tasks 예시 1.2 문장을 버그 수정·기능 추가 공통 표현으로 변경(G9-4 수정): "현재 코드에서 실패하는지 확인(변경 후에는 통과해야 함)". 기존 "(버그 수정이면 보고된 실패가 재현되는지 먼저 확인)" 대체.

**추가 (val ablation 이후, 2026-10-14)**
- verify ↔ apply 반복 삭제(G8-1 drop, 7번 대체): verify는 1회, `verify.md` 작성 후 결과와 무관하게 archive. 남은 문제는 보고서에 기록. 03-verify.md의 다음 단계는 "archive 단계로 이동" 한 줄(G2-5), 보고서 파일은 `verify.md` 하나(G5-3). core-workflow.md의 "Verify Rounds"를 "Verify Once"로 교체, archive 조건에서 `verify-2.md` 삭제. `loop` 태그 제거, `verify-2.md`를 FORBIDDEN에 추가(build.py, tests/test_openspec_ff.py, README.md).


# Explore extension (2026-10-15)  (upstream `skills/openspec-explore/SKILL.md`@9111a76)

근거: `03-decisions.md` "Explore extension", 승인된 계획 `03-plan.md`. 편집 목록은 `build.py --list`의 `explore` 줄.

## 계획 대비 달라진 점

| # | 항목 | 계획(03-plan.md) | 실제 구현 | 이유 |
|---|---|---|---|---|
| 1 | 단계 문서 편집 수 | 약 25건 | 30건: Edit 28(store 단락 공통 편집 포함) + Section 2. env 8, semantic 22 | 요약 블록, 끝맺음 4개, guardrail 문장마다 anchor를 따로 둠. "Planning a Change"의 질문 문장(`:46`, `:51`, `:52`, `:53`, `:73`)에도 G4-14를 문장별로 적용 |
| 2 | `/openspec-propose` 안내 5곳 (G2-10) | 5곳 모두 "`01-ff.md`를 열고 계속"으로 변경 | 4곳(`:14`, `:318`, `:335`, `:345`) 변경. `:162`는 capture 전환과 함께 삭제 | `:162`는 G4-17이 지우는 `:150-162` 안에 있음 |
| 3 | capture 전환 삭제 범위 (G4-17) | `explore:150-195` | `### When no change exists`(`:148`) 제목과 `:150` "Think freely"까지 포함해 두 소절 전체 삭제. 소절 사이 구분선 `---` 하나는 유지 | 제목만 남으면 빈 소절이 됨 |
| 4 | 질문 → 가정 (G4-14) 적용 위치 | "범위·의도 질문은 가정 기록으로" | `:46`을 규칙 문단으로 바꿈(사람만 답할 질문 → 가정, 요약에 표시, ff가 proposal에 옮김). `:51`, `:52`, `:53`, `:73`은 그 규칙에 맞춰 수정. Stance의 `:35-36`("Ask questions that emerge naturally" 등)과 `:48` 끝 문장("ask only for the clarification needed")은 원문 유지 | `:48`은 결정상 원문 그대로. `:35-36`은 질문을 지시하지 않는 태도 서술이라 바로 위 규칙 문단으로 충분하다고 판단 |
| 5 | 요약을 필수 산출물로 만드는 범위 (G2-12, G8-6) | 끝 조건과 요약 블록 | `:16` "no mandatory outputs"와 `:204` "Reach a conclusion"도 변경 | 요약이 필수라는 결정과 정면으로 충돌하는 문장 |
| 6 | G9-5 경계 문장 | 허용·금지 목록 | 결정 note의 "issue 예시를 변형하는 일은 ff·apply(`checks/`)가 함"까지 한 문장 추가 | 결정 행 Notes에 적힌 내용 |
| 7 | `core-workflow.md` | 행동 표 행, 흐름 줄, 읽기/실행 규칙 | 그 밖에 "From Explore to ff" 절(끝 조건, 요약, ff가 요약을 근거로 씀), Fixed Names의 checks 줄("From the ff action on … Explore writes none"), Input 줄(explore와 ff), "No One Will Answer"의 가정 기록 위치에 explore 요약 추가 | `02-gaps.md` "New text the port must write (explore)"와 "Conflicts"(`core-workflow.md:34`, `:51-53`)에 적힌 항목 |
| 8 | system prompt 절차 섹션 | explore를 첫 단계로 명시 | 3번 항목의 가정 기록 위치에도 "explore's summary" 추가 | explore에는 artifact가 없음(G4-14) |
| 9 | 금지어 검사 `explore:48` 예외 | `FORBIDDEN` 예외 | 공용 엔진(`workflows/_port.py`)은 그대로 두고 `build.py`에 `FORBIDDEN_ALLOWED`와 `forbidden_left()`를 추가. 허용 문장은 explore에서만, 정확히 1회일 때만 면제. 나머지 문서는 "ask the user"까지 전부 검사. 이를 위해 stage 문서 `build()`가 `_port.build` 대신 `convert()`를 거침(`BUILDERS`) | 패키지 밖 파일은 수정하지 않는다는 작업 제약 |
| 10 | 삭제 문구 금지어 | — | `FORBIDDEN`에 8개 추가("Want me to", "yes/no question", 세 예시의 마무리 질문, "capture the exploration", "Don't manually scaffold", "this summary is optional") | 지운 문장이 upstream 변경으로 되살아나면 build가 실패하도록 |
| 11 | G4-16 문장 | "The task asks you to implement a fix; …" | 결정 문안 그대로 | 기능 추가 task에도 "a fix"로 읽힘(D-6). 문안은 결정대로 두고 기록만 함 |
| 12 | 공용 README | — | `recipe/grpo/qwen3_5/README.md` workflow 표의 openspec_ff 행을 "explore → ff → …"로 변경 | 단계 목록이 적힌 행 |
| 13 | `__init__.py` docstring | explore 반영 | 오래된 "new → ff, 01-new … 04-verify" 표기도 같이 고침 | D-7 이후 갱신이 빠져 있었음 |
| 14 | G7-9 probe | smoke 전에 시험 | stage 4에서 시험함(`cli-probe/05`): 빈 트리에서 `list --json` → `changes: []`, `list --specs` → `No specs found.`, `--json` → `specs: []`. TTY 유무와 관계없이 모두 exit 0, 약 245 ms. 아무것도 쓰지 않음 | 로컬 agent image(`rllm-agent-f268c8df48c7`)가 있어서 가능 |

## 구성 (explore로 바뀐 파일)

| 파일 | 출처 | 내용 |
|---|---|---|
| `docs/stages/00-explore.md` | OpenSpec 원문을 변환 | explore 단계 문서: 입력, 읽기 전용 경계, 쓰기 없음, 질문 → 가정, 끝 조건, "What We Figured Out" 요약, ff로 넘어가기 (원문 353줄 → 222줄) |
| `docs/core-workflow.md` | 직접 작성 | explore 행·흐름 줄·"From Explore to ff" 절·explore 실행 규칙 추가 (91줄 → 105줄) |
| `instruction.md`, `system-prompt.j2` | 직접 작성 / SDK 기본 프롬프트 복사 | explore를 ff 앞에 명시. 첫 행동은 그대로 `/opsx/core-workflow.md`. 나머지 15개 섹션 동일 |
| `sandbox/openspec-config.yaml` | 직접 작성 | `context`의 checks 줄을 "From the ff action on, …"으로 |
| `build.py` | 직접 작성 | `SOURCES`·`STAGE_DOCS`에 explore, explore 편집 30건, `FORBIDDEN_ALLOWED`·`forbidden_left`, `BUILDERS` |
| `__init__.py`, `README.md` | — / 직접 작성 | docstring과 안내서에 explore 반영 |
| `porting/cli-probe/05-*` | 단계별 기록 | G7-9 probe 스크립트와 출력 |
| `tests/test_openspec_ff.py` | 직접 작성 | 문서 5개, 금지어 예외의 범위, explore의 hand-off·쓰기 없음·요약·G4-19 문장, config 줄 |

## 수정한 내용

### 각 단계 수행 방식 변화 (explore)

| Before (upstream explore) | After (rllm) |
|---|---|
| 1. **사람**이 (선택) agent 앱 채팅창에 `/opsx:explore`를 입력하고 바꿀 영역이나 문제를 말합니다.<br>2. **agent 앱**이 `openspec-explore` SKILL.md를 지침으로 불러옵니다.<br>3. agent가 `openspec list`·`list --specs`·`show`와 `config.yaml`로 현황을 보고, 코드를 읽고 읽기 전용 명령을 실행합니다.<br>  • 다이어그램과 선택지를 보여 주며 **사람에게 한 번에 하나씩 질문**합니다.<br>  • 코드는 쓰지 않습니다. change 문서는 **사람의 yes 뒤에만** 씁니다.<br>4. 정해진 끝이 없습니다. **사람**이 `/opsx:propose`를 입력하면 끝나고, 대화 내용이 proposal로 옮겨집니다. | 1. task 메시지(instruction + issue)가 탐색 주제입니다.<br>2. agent가 `core-workflow.md`를 읽고 **`/opsx/stages/00-explore.md`를 먼저** 엽니다.<br>3. agent가 `openspec list --json`, `list --specs`(빈 트리: `No specs found.`)와 `config.yaml`을 보고, 코드를 읽고 검색합니다.<br>  • 실행은 **기존 코드·기존 테스트, issue 예시를 그대로**만 합니다. 직접 짠 코드(한 줄 `python -c` 포함)와 파일 쓰기는 하지 않습니다.<br>  • 사람만 답할 수 있는 질문은 **가정**으로 요약에 기록하고, 선택은 agent가 추천안과 대안으로 정합니다.<br>4. 문제와 바꿀 위치를 근거와 함께 말할 수 있으면 **"What We Figured Out" 요약**(문제, 동작 방식, 바꿀 위치·대안, 가정, 남은 질문)을 쓰고 같은 turn에 `01-ff.md`를 엽니다.<br>5. ff부터는 기존과 같습니다. ff는 요약을 근거로 proposal과 design을 씁니다. |

### 수정 사항

| # | 범주 | 내용 |
|---|---|---|
| 1 | **사람 피드백이 필요한 부분 삭제** | 쓰기 전 yes/no 질문, "Want me to create a proposal?" 제안, 질문으로 끝나는 예시 대화 삭제. 범위·의도 질문은 요약의 가정으로, "Planning a Change" 예시의 범위 질문은 근거에서 끌어낸 가정과 틀렸을 때의 대안으로, 사람의 선택은 agent의 추천안·대안으로 대체 |
| 2 | **보고 후 멈춤 → 다음 단계로 진행** | `/openspec-propose` 안내 4곳을 "`/opsx/stages/01-ff.md`를 열고 계속"으로 변경(5번째는 capture 전환과 함께 삭제). 구현 요청 거절 문장을 "구현은 이 세션의 ff·apply가 수행"으로 변경 |
| 3 | **이름·경로 고정** | explore 단계 문서 `00-explore.md`(기존 01–03 유지). change 이름은 기존대로 ff의 `issue` |
| 4 | **실행 환경 구성** | 해당 없음(CLI·이미지 그대로). 빈 spec 트리의 `openspec list --specs` 동작을 probe로 확인 |
| 5 | **agent 앱 전용 요소 삭제** | explore의 frontmatter, store 선택 문단 삭제 |
| 6 | **SWE task 조건에 맞춤** | 해당 없음(explore는 원래 파일을 쓰지 않음) |
| 7 | **절차 구조 변경** | ff 앞에 explore 단계 추가(선택 → 항상). 끝 조건은 요약의 문제·바꿀 위치를 근거와 함께 말할 수 있을 때, 요약은 필수. capture 전환, "When a change exists", 손으로 change를 만들지 말라는 guardrail, 상황별 예시 4개 중 3개 삭제 |
| 8 | **환경 사실 명시** | config `context`와 진입 문서의 checks 문장을 "From the ff action on, …"으로 변경 |
| 9 | **harness·데이터셋 설정** | `instruction.md`와 system prompt 절차 섹션에 explore를 ff 앞에 명시. build.py 금지어 검사에 explore의 `:48` 문장 1회 예외 |
| 10 | **범위·방식 결정** | "코드 작성"의 경계: 기존 코드·테스트와 issue 예시를 그대로 실행하는 것만 허용, 직접 짠 코드와 파일 쓰기 금지. explore는 change 문서도 쓰지 않음 |
| 11 | **원문 유지** | "NEVER write code"(`:14`, `:345`), 사실 확인 문장 `:48`, Stance 목록, 현황 명령과 config 읽기(`:122-146`), project-root guard, "Visualize"와 ASCII 규칙, 원문 ff 문서 전체("reuse findings … inspect more only as needed" 포함) |

**적용 위치**
- **단계 문서 편집**: `build.py`가 `skills/openspec-explore/SKILL.md`를 `00-explore.md`로 변환할 때 태그 편집 30건(env 8, semantic 22). 범주 1, 2, 5, 7, 10
- **환경 파일**: `sandbox/openspec-config.yaml` 1줄. 범주 8
- **새로 작성**: `core-workflow.md`(행동 표 행, 흐름 줄, "From Explore to ff", explore 실행 규칙, checks 줄), `instruction.md`, system prompt 절차 섹션. 범주 7, 8, 9, 10
- **build·test**: `build.py`의 `SOURCES`·`STAGE_DOCS`·`FORBIDDEN`(+8)·`FORBIDDEN_ALLOWED`, 테스트, README, `__init__.py` docstring

## agent 행동 변화 (explore)

| # | 단계 | upstream 원래 행동 | 지금 행동 | 바꾼 이유 | 원문으로 되돌리면 |
|---|---|---|---|---|---|
| 1 | explore | 선택 단계. 사람이 `/opsx:explore`를 부를 때만 실행 | **새 행동 추가**: 매 rollout에서 ff 전에 항상 실행(진입 문서의 흐름 줄과 행동 표 첫 행, instruction, system prompt) | 재현 전에 design을 확정하는 계획 고착을 줄이려고 사용자가 순서를 정함 (G3-2) | 가능 (explore 없는 기존 openspec_ff) |
| 2 | explore | "run read-only commands or tools … NEVER write code". 직접 짠 snippet 실행 여부는 원문상 불명확 | **원래 행동 삭제**(불명확한 부분): 기존 코드·테스트와 issue 예시를 그대로 실행하는 것만 허용, 한 줄 `python -c`를 포함한 직접 짠 코드와 모든 파일 쓰기 금지 | "NEVER write code"를 문자 그대로 적용 (G9-5) | 가능 (snippet 허용 시 재현은 늘지만 원문 규칙과 충돌) |
| 3 | explore | 끝이 없음("There's no required ending"), 사람의 명령으로 끝남 | **새 행동 추가**: 요약의 문제·바꿀 위치를 근거와 함께 말할 수 있으면 끝내고 ff로 감. 남은 질문은 열어 둠 | 끝낼 사람이 없음 (G8-6) | 불가 (무인 실행에 끝이 없음) |
| 4 | explore | 결정은 대화에 남김. 요약은 선택 | **새 행동 추가**: "What We Figured Out" 요약을 항상 작성(문제, 동작 방식, 바꿀 위치·대안, 가정, 남은 질문 + `file:line`·명령 출력 근거), ff 문서를 여는 turn에 둠 | 확인 가능한 기록, ff의 근거 (G2-12, G2-11) | 가능하지만 근거가 대화에 흩어짐 |
| 5 | explore | yes를 받으면 change 문서 작성, capture 요청 시 change 생성 | **원래 행동 삭제**: 아무것도 쓰지 않음. change는 ff가 만듦 | 답할 사람이 없고, ff의 `new change`와 충돌 (G4-13, G4-17, G7-10) | 가능하지만 ff 2단계 변경 필요 (`later.md`) |
| 6 | explore | 추천안을 말하고 사람이 고름("The user decides"). spike는 사람에게 제안 | **새 행동 추가**: agent가 추천안·대안·이유를 요약의 "Where the change goes"에 쓰고 ff가 design.md Decisions에 기록. spike는 ff 조사에서 풀 구체적 질문으로 넘김 | 고를 사람이 없음 (G4-15) | 불가 (선택할 사람 없음) |
| 7 | explore | 예시: 코드 확인 후 사람에게 범위 질문("Is sharing state across devices in scope?") | **새 행동 유도**: 같은 예시가 근거에서 가정을 끌어내고("Nothing in the issue or the code needs state shared across devices, so I assume …") 틀렸을 때의 대안을 함께 적음 | G4-14 규칙과 같은 행동을 예시로 보임 (G4-19) | 가능하지만 예시가 질문하는 행동을 보임 |
| 8 | ff | explore 대화를 보고 proposal을 씀 | **새 행동 유도**: 요약을 근거로 proposal Why·design Context·Decisions를 쓰고 가정을 proposal에 옮김(explore 문서와 진입 문서에 명시). ff 문서는 원문 그대로 | explore 결과를 계획에 반영 (G2-12, G2-13) | 가능 |

**표에서 뺀 것**: 입력 = issue(G1-4), propose 안내 → ff 문서 열기(G2-10), 구현 요청 문장(G4-16), 질문 → 가정 기록 단순 대체(G4-14), 메시지는 tool call과 같은 turn에(G2-11), frontmatter·store 삭제(G7-7, G7-8), 질문으로 끝나는 예시 3개 삭제(G4-18), 현황 명령 유지(G7-9), config·진입 문서의 checks 문장(G10-9).

**smoke에서 반드시 확인할 것** (새 행동 추가 행 1, 3, 4, 6): explore가 매번 실행되는지, explore 중 파일 쓰기와 직접 짠 코드가 0인지, 끝 조건에 맞춰 요약을 쓰고 같은 turn에 ff로 가는지, 요약의 추천안이 design Decisions에 기록되는지. 함께 측정: explore와 ff의 step 수, ff 조사량(G2-13), 계획 고착 사례 수.

## 변경 (explore)

**E1. explore 단계 문서 추가** (00-explore.md, build.py, core-workflow.md) — G5-4, G3-2, G7-7, G7-8
- 원문은 사람이 원할 때 부르는 선택 단계. `skills/openspec-explore/SKILL.md`를 `docs/stages/00-explore.md`로 변환해 ff 앞에 추가, 기존 01–03 번호는 유지.
- frontmatter 삭제, store 선택 문단은 기존 공통 편집으로 삭제.

**E2. 입력을 issue로 명시** (00-explore.md, core-workflow.md) — G1-4
- 원문은 사람이 가져오는 주제가 입력. `**Input**` 줄로 `<issue_description>`의 issue를 탐색 자료로 명시, 진입 문서의 입력 절에 explore 추가.

**E3. 읽기 전용 경계와 쓰기 없음** (00-explore.md, core-workflow.md, openspec-config.yaml) — G9-5, G4-13, G7-10, G10-9 — **semantic 포함**
- 원문은 읽기 전용 명령은 자유, 코드는 금지, change 문서는 사람의 yes 뒤에 작성하는 구조.
- 읽기 전용 = 기존 코드·기존 테스트·issue 예시를 그대로 실행하고 파일을 쓰지 않는 것으로 명시. 직접 짠 코드(한 줄 `python -c`, stdin snippet)와 모든 파일 쓰기(저장소, `/tmp`, `checks/`, redirection, heredoc) 금지, 실행 부산물은 예외(G9-5, semantic).
- change 문서 작성 허용 문장, yes/no 확인 절차, auto-capture guardrail을 "explore는 아무것도 쓰지 않음, `openspec new change`는 ff의 첫 명령"으로 변경(G4-13, semantic). 손으로 change를 만들지 말라는 guardrail 삭제(G7-10).
- config `context`와 진입 문서 Fixed Names의 checks 문장에 "From the ff action on" 추가(G10-9).

**E4. 질문을 가정·추천안으로 대체** (00-explore.md, system-prompt.j2) — G4-14, G4-15, G4-19 — **semantic**
- 원문은 사람에게 한 번에 하나씩 묻고, 추천안을 말하되 사람이 고르는 구조.
- "Planning a Change" 첫 문단을 규칙으로 변경: 질문은 issue·코드·테스트에 던지고, 사람만 답할 질문은 가장 타당한 해석을 가정으로 요약에 표시, ff가 proposal에 옮김. `:51`, `:52`(금지어 "ask the user" 포함), `:53`, `:73`을 같은 규칙에 맞춤. `:48`은 원문 그대로(G4-14).
- "Recommend a path (if asked)" → 대안과 이유를 붙여 항상 추천, spike 제안 → ff 조사용 구체적 질문, "Let them pause, pivot, or defer" → 끝 조건과 열린 질문(G4-15).
- 예시(`:57-64`)의 범위 질문을 결정 문안대로 근거 기반 가정 + 틀렸을 때의 대안으로 변경, 첫 문장은 유지(G4-19).

**E5. 끝 조건과 필수 요약** (00-explore.md, core-workflow.md) — G8-6, G2-12, G2-11, G2-10 — **semantic**
- 원문은 끝이 없고 요약은 선택, 끝맺음은 propose 명령 안내 등 4가지.
- "no mandatory outputs" → 요약이 유일한 필수 산출물, "Reach a conclusion" → 열린 질문만 남겨도 됨.
- 끝맺음 4개를 "ff로 넘어감" 하나로: 요약의 문제와 바꿀 위치를 근거와 함께 말할 수 있으면 끝.
- 요약 필드를 문제 / 동작 방식 / 바꿀 위치(추천안·대안) / 가정 / 남은 질문으로 변경, 각 항목에 `file:line`·명령 출력 근거, ff 문서를 여는 tool call과 같은 turn에 작성. "this summary is optional" → ff가 proposal Why·design Context·Decisions를 이 요약 위에 씀.
- 진입 문서에 "From Explore to ff" 절 추가.

**E6. propose 안내를 ff 문서로 연결** (00-explore.md) — G2-10, G4-16
- 원문은 구현 요청을 말로 거절하고 `/openspec-propose`를 안내하는 구조. task 메시지 자체가 구현 요청이라 문자 그대로면 텍스트 응답으로 종료.
- `:14`의 거절 문장을 "구현은 이 세션의 ff·apply가 수행, explore에서는 시작하지 않음"으로, `:318`·`:335`·`:345`의 propose 안내를 "`/opsx/stages/01-ff.md`를 열고 계속"으로 변경. `:162`는 E7에서 삭제.

**E7. 쓰이지 않는 분기와 예시 삭제** (00-explore.md) — G4-17, G4-18 — **semantic 포함**
- capture 전환(`### When no change exists`)과 `### When a change exists` 소절 삭제(ff 전에는 change가 없음, G4-17). 구현 중 예시 삭제(G4-17).
- 상황별 예시는 "User brings a specific problem"만 유지하고, 마무리 질문 "Which one's burning?"을 "요약을 쓰고 같은 turn에 ff 문서를 엶"으로 변경. 막연한 아이디어·선택지 비교 예시 삭제(G4-18, semantic).

**E8. 첫 단계 명시와 금지어 검사** (instruction.md, system-prompt.j2, build.py, tests) — G10-8, G4-14
- instruction과 절차 섹션에 "explore 먼저, 아무것도 쓰지 않음, 그다음 ff → archive" 명시. 첫 행동은 그대로 `/opsx/core-workflow.md` 열기, 나머지 15개 섹션 동일.
- `FORBIDDEN_ALLOWED`: explore의 "Do not ask the user to repeat facts you can verify."만 1회 면제, 다른 문서와 두 번째 등장은 실패. 지운 explore 문구 8개를 `FORBIDDEN`에 추가.

**원문 그대로 둔 부분 (explore)**: "NEVER write code" 두 곳, `:48` 사실 확인 문장 전체, Stance 목록, "Follow dependencies", Visualize와 ASCII 규칙, OpenSpec Awareness(`list --json`, `list --specs`, `show`, config 읽기), project-root guard, Guardrails의 나머지 항목, ff 문서 전체.

**원문 없이 새로 쓴 문서 (explore 관련)**: `docs/core-workflow.md`의 explore 부분, `instruction.md`, `system-prompt.j2`의 `<PROBLEM_SOLVING_WORKFLOW>` 섹션.

### Explore extension — stage 6 back-edges (2026-10-16)

- **G9-6** (semantic, user): `00-explore.md` Guardrails "Don't implement" names composed code (`python -c "..."`,
  a heredoc piped to `python3`) as writing code and sends variants of the issue's example to ff as open
  questions; `core-workflow.md` explore rule names the same plus scripts in `/tmp`. Edit note `G4-13/G9-6`.
- **G2-14** (env, user): the summary goes inside a tool call (e.g. `think`) before the tool call that opens
  `01-ff.md`, no longer "in the same turn"; `00-explore.md` (edit note `G2-12/G2-11/G2-14`), `core-workflow.md`
  actions-table row and "From Explore to ff".
- Verified: `build --check` rc=0; recipe tests 136 passed (test_openspec_ff updated for both).
