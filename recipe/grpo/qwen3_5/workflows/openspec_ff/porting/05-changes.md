# Changes: openspec_ff  (upstream Fission-AI/OpenSpec@9111a76, npm 1.14.1)

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
