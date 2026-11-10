# Survey: SPARC (ruvnet) 1.0 — evidence-gated five-phase run

- Upstream: https://github.com/ruvnet/sparc.git @ 3af6c696be3e713d885cead7f84d07a7fac25ade (commit dated 2026-08-27 "feat: package registered ChatGPT plugin apps"; npm `@ruvnet/sparc` `1.0.0` per `package.json:3`, `src/cli.ts:32`; Python CLI `sparc` `0.88.0` per `sparc_cli/__version__.py:3`, while `sparc_cli/README.md:3` still says 0.86.2 and `sparc_cli/docs/README.md:3` says 0.8.2), license Apache-2.0 (`LICENSE`, 201 lines; appendix copyright line `Copyright [2024] [AI Christianson]` at `LICENSE:190`; `package.json:5`, `pyproject.toml:10`, `plugins/sparc/.claude-plugin/plugin.json:11`). Apache 2.0 requires keeping the license text and any NOTICE with redistributed copies and marking modified files (`LICENSE:90-105`); there is no NOTICE file in the checkout.
- Checkout: /vast-ib/MMI/home/kyuminkim/project/if/workflows/sparc (read-only; nothing from it was executed). No `dist/` and no `node_modules/` in the checkout (both gitignored, `.gitignore:161-162`); `.sparc/` is gitignored too (`.gitignore:163`).

All paths below are relative to the checkout. The repository holds four surfaces that do not share text: (1) the 1.0 TypeScript state machine with npm CLI + MCP server (`src/`, `templates/`), (2) the three Claude/Codex skills (`skills/`, byte-identical mirror in `plugins/sparc/skills/`, verified with `diff -r`), (3) the legacy Python CLI (`sparc_cli/`), (4) the methodology documents (`specification/`, `docs/`, `example/`). A fifth surface, the Next.js web UI (`ui/`), has `/sparc`, `/plan`, `/research` chat commands that only send a one-line prompt to a model API (`ui/lib/commands/spec.ts:23`, `ui/lib/commands.ts:9-39`); it is listed for completeness and not surveyed further.

## 파이프라인: A. 1.0 CLI로 모는 5단계 evidence-gated run (추천)

`R` = state root (`--root PATH` 또는 `$SPARC_STATE_ROOT`, 기본값은 현재 디렉터리의 `.sparc`), 그 안의 run 파일은 `R/runs/<sha256(principal)>/<sha256(run-id)>.json` 하나(모드 0600)이고 모든 산출물·증거·영수증이 이 JSON 안에 append 된다. `P` = principal (`--principal` 또는 `$SPARC_PRINCIPAL`, 기본 `local-cli`). 사람이 작업 디렉터리에 JSON 파일을 직접 써 두고 `sparc <명령>`(발행 전에는 `node dist/cli.js <명령>`)을 한 번에 하나씩 터미널에서 실행한다. SPARC 자체는 저장소를 읽거나 고치지 않고, 명령을 실행하지도 않는다. 코드 변경은 Refinement 단계에서 **사람(또는 사람이 쓰는 코딩 에이전트)이 SPARC 바깥에서** 한다.

### 전체 흐름
```
init → start            →  Specification        →  Pseudocode           →  Architecture         →  Refinement                        →  Completion              →  status/trace
(상태 루트, 요구사항·    (JSON 산출물 submit →     (동일)                  (동일)                  (코드 구현·테스트는 SPARC 밖 →        (요구사항→증거 trace →      (감사: 요약과 영수증
 인수테스트 등록, rev 1)   gate → advance)                                                           verifier 서명 evidence → 산출물 →     gate → advance=완료)       페이지 확인)
                                                                                                    gate → advance)
```
사람이 명령을 하나씩 실행해 넘긴다. 모든 변경 명령은 직전 응답의 `revision`을 `--expected-revision`으로, 새 `--idempotency-key`를 함께 내야 하고(리비전 불일치면 `CAS_MISMATCH`, 같은 키에 다른 요청이면 `IDEMPOTENCY_MISMATCH`), `gate`가 blocker 를 돌려주면(종료코드 2) 산출물을 고쳐 **새 버전**으로 다시 submit 한다(이전 버전은 지워지지 않음). `advance`는 gate 가 통과할 때만 다음 단계로 가며 Completion 에서의 `advance`는 run 을 `completed`로 닫는다.

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **1. `sparc init`** (선택) | (단일) | state root 를 만든다(0700). `start`가 어차피 만들므로 생략 가능 | `--root` / `$SPARC_STATE_ROOT`, (증거를 쓸 거면) `$SPARC_EVIDENCE_VERIFIER_KEYS` = `{keyId: 공개키 PEM}` JSON | `R/`, `R/runs/` |
| **2. `sparc start`** | (단일) | run 생성. 요구사항(REQ-n, `inScope`, `acceptanceTestIds`)과 인수테스트(TEST-n, `description`, 선택 `command`)를 등록하고 `requirementsDigest`·`genesisDigest`(랜덤 nonce 포함) 를 계산 | **사람이 쓴 `definition.json`** (`templates/definition.example.json` 꼴), `--run-id`, `--title`, `--idempotency-key` | `R/runs/<h(P)>/<h(run-id)>.json` (revision 1, phase Specification, receipt 1개); stdout JSON 에 `revision`, `value.genesisDigest`, `value.requirementsDigest` |
| **3. Specification** | 1. submit | `--phase Specification --file specification.json`. 내용은 gate 가 검사할 뿐 실행되지 않음 | **사람이 쓴 `specification.json`** (`templates/specification.json`: outcome, businessValue, actors, inputs, outputs, assumptions, constraints, exclusions, securityBoundaries, measurableSuccessCriteria, requirementCoverage[REQ→TEST 매핑]), `--expected-revision 1` | run JSON 에 artifact `specification@1` 추가, revision 2, receipt |
| | 2. gate | 결정적 규칙 검사: 모든 필드 비어있지 않음, 모든 REQ 가 커버됨, in-scope REQ 는 등록된 TEST 를 전부 매핑, out-of-scope 는 `nonGoalReason` | run JSON | stdout `{ok, gate.blockers[]}`; 종료코드 0/2. 상태 변화 없음 |
| | 3. advance | gate 통과 시 Pseudocode 로 | `--expected-revision 2` | phase Pseudocode, revision 3, `phaseHistory` 에 gateDigest |
| **4. Pseudocode** | 1–3. submit → gate → advance | 위와 같은 세 명령 | **사람이 쓴 `pseudocode.json`** (controlFlow, stateTransitions[from/event/to/onFailure], dataTransformations, failurePaths, retries[maxAttempts 0..100], idempotencyRules, invariants, walkthroughs.success/failure + invariantChecks(선언한 invariant 만 인용), requirementCoverage) | artifact `pseudocode@1`, revision 4 → advance 로 Architecture, revision 5 |
| **5. Architecture** | 1–3. submit → gate → advance | 동일 | **사람이 쓴 `architecture.json`** (components, interfaces, ownership[모든 component 에 owner 1개], trustBoundaries, dataLifecycle, deploymentModel, observability, migrationPath, rollbackPath, selectedDesign, alternatives[각각 6개 tradeoff 차원], requirementCoverage) | artifact `architecture@1`, revision 6 → Refinement, revision 7 |
| **6. Refinement** | 1. 구현·검증 (SPARC 밖) | **사람이 저장소 코드를 고치고 인수테스트(예: `npm test`)를 돌린다.** SPARC 는 이 단계를 기록하지 않는다 | 저장소, 테스트 | **코드 변경** (SPARC 상태에는 없음) |
| | 2. verifier 서명 | **독립 verifier**가 `sparc status`로 읽은 최신 `genesisDigest`·`requirementsDigest`·revision·phase 와 증거 필드를 `evidenceAttestationBytes` 로 정규화해 Ed25519 개인키로 서명 (`docs/EVIDENCE_ATTESTATION.md` 의 `sign-evidence.mjs`) | 최신 run 요약, **verifier 개인키** (SPARC 밖), 테스트 결과 | `evidence.json` (`evidenceId, requirementId, testId, status: pass, summary, details{command, exitCode…}, attestation{keyId, issuedAt, algorithm, signature}`) |
| | 3. `sparc evidence` | 서명을 공개키로 검증하고 evidence 버전 append. `pass`/`exception` 은 서명 없으면 거부, `fail` 은 서명 없이 허용 | `evidence.json`, `$SPARC_EVIDENCE_VERIFIER_KEYS`, `--expected-revision 7` | evidence `EVIDENCE-1@1` (+ `digest`), revision 8; stdout 에 `{evidenceId, version, digest}` 세 쌍 |
| | 4. submit | `refinement.json`: increments 마다 구현한 REQ 와 **정확한 `{evidenceId, version, digest}`** 인용, `preservesBehavior` 결정(false 면 `migrationApproval` 필요), verification, preservedBehavior | **사람이 쓴 `refinement.json`** (템플릿의 `REPLACE_WITH_EXACT_EVIDENCE_DIGEST` 를 3단계 출력으로 치환) | artifact `refinement@1`, revision 9 |
| | 5. gate → advance | in-scope REQ 의 **모든** 등록 TEST 에 대해 Refinement 단계에서 기록된, verifier 서명된 `pass` 증거가 있어야 통과 | run JSON, `--expected-revision 9` | Completion, revision 10 |
| **7. Completion** | 1. submit | `completion.json`: finalDiff, documentation, observability, rollback, residualRisks, requirementTrace[REQ → evidenceRefs] | **사람이 쓴 `completion.json`** (같은 증거 세 쌍 재인용) | artifact `completion@1`, revision 11 |
| | 2. gate → advance | 모든 in-scope REQ·TEST 가 서명된 pass(또는 승인된 exception) 증거로 추적되면 run 을 `completed` 로 | `--expected-revision 11` | `status: completed`, `completedAt`, revision 12 **(inferred: 리비전은 변경마다 +1 규칙으로 센 값)** |
| **8. `sparc status` / `sparc trace`** | (단일) | 요약(카운트·receiptTail·무결성 검증)과 revision 에 묶인 trace 페이지(≤25개, 512 KiB) 를 `--cursor` 로 끝까지 읽는다 | run JSON | stdout JSON. 상태 변화 없음 |

### 정리하면
- **사람이 넣는 입력**: 명령 12번 전부(단계 이동은 모두 사람의 `advance` 호출); `definition.json`(요구사항·인수테스트 식별자 설계); 다섯 단계 산출물 JSON 다섯 개(템플릿 자리표시자를 손으로 채움); 매 변경 명령의 `--expected-revision`·`--idempotency-key`; gate blocker 를 읽고 고친 새 버전; Refinement 의 코드 변경과 테스트 실행; verifier 키쌍 준비와 서명 스크립트 실행(사람 또는 CI); `$SPARC_EVIDENCE_VERIFIER_KEYS`·`$SPARC_EXCEPTION_APPROVERS` 환경 설정.
- **코드를 바꾸는 곳**: Refinement PHASE 1 뿐이며 SPARC 바깥이다(SPARC 는 "저장소를 편집하지 않는다"). 문서 체인: `definition.json` → `specification.json` → `pseudocode.json` → `architecture.json` → (코드 + 테스트 → `evidence.json`) → `refinement.json` → `completion.json`, 전부 `R/runs/<h(P)>/<h(run-id)>.json` 한 파일 안의 append-only 버전으로 쌓인다. 산출물 JSON 원본 파일은 사람의 작업 디렉터리에 남는다.
- **오래된 저장소·사전 준비를 전제한 입력**: Node ≥ 20 과 빌드된 `dist/cli.js`(체크아웃엔 없음; `npm ci` 는 196개 패키지를 레지스트리에서 받는다) 또는 아직 발행이 확인되지 않은 `npx @ruvnet/sparc@1.0.0`; **SPARC 와 분리된 verifier 의 Ed25519 개인키**(없으면 `pass` 증거를 못 쓰고 Refinement 를 못 넘는다); state root 는 절대경로·0700·심볼릭링크 없음; 기본 root `.sparc` 는 cwd 안이라 `/testbed` 에서 돌리면 저장소 안에 생긴다; 산출물 스키마가 전제하는 서비스형 시스템(deploymentModel, observability, rollbackPath, migrationPath, 6차원 tradeoff) 은 SWE 이슈와 무관한 항목이 많다.

## 파이프라인: B. `sparc` skill (MCP 도구로 모는 같은 run)

A 와 상태 기계·gate 가 동일하고 호출 표면만 다르다(`docs/adrs/ADR-001-sparc-metaharness.md` "Host parity"). 사람은 Claude Code/Codex 에 plugin 을 설치하고(`.mcp.json` 이 `npx --yes @ruvnet/sparc@1.0.0 mcp stdio` 를 띄움) 채팅에서 `$sparc` 와 목표를 말한다; 그 뒤는 에이전트가 MCP 도구 8개로 A 의 1–8 을 수행한다.

### 전체 흐름
```
MCP 서버 확인  →  목표→요구사항·인수테스트  →  sparc_run_start  →  phase ×5 (sparc_phase_submit → sparc_gate_validate → sparc_phase_advance)  →  sparc_evidence_record (Refinement)  →  sparc_trace_get 전 페이지 → 보고
(없으면 멈추고 사람에게)  (에이전트가 작성)
```
한 skill 호출 안에서 에이전트가 끝까지 진행한다(단계 사이에 사람의 명령이 필요 없음). 멈추는 지점은 MCP 서버가 없을 때(설치/등록을 사람에게 요청), 독립 verifier 가 없을 때("evidence gate 가 blocked 라고 보고"), 그리고 리비전 충돌·무결성 실패.

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **1. `$sparc <목표>`** | 1. 전제 확인 | host 에 `sparc` MCP 서버와 `sparc_*` 도구 8개가 보이는지 확인; 없으면 **멈추고 사람에게** plugin 설치 또는 정확한 launcher 등록 요청 | host MCP 설정 | (없음) |
| | 2. 목표 정리 | 목표·제약·요구사항·관찰 가능한 인수 증거를 서술 | **사람의 목표 문장** | (대화 텍스트) |
| | 3. `sparc_run_start` | A-2 와 동일, 인자는 JSON 파일 대신 도구 입력(requirements ≤256, acceptanceTests ≤256, `expectedRevision: 0`) | 2 의 결과, 안정적인 idempotency key | `R/runs/...json` (R = MCP 서버의 `--root`), 응답에 revision·두 digest |
| | 4. 읽기 | `sparc_run_get` 요약 + `sparc_phase_get` 페이지를 `nextCursor` 가 없을 때까지; 요약의 revision 을 다음 변경에 사용 | run | (없음) |
| | 5. 단계 ×5 | `sparc_phase_submit`(content = A 의 산출물 JSON) → `sparc_gate_validate` → 통과 시 `sparc_phase_advance` | 에이전트가 만든 산출물 JSON | A-3…7 과 동일한 artifact 버전·revision |
| | 6. 증거 | `sparc_evidence_record`: 테스트 결과·리뷰를 증거로 append. `pass`/`exception` 은 **독립 verifier** 의 Ed25519 서명 필요, "모델만의 주장은 증거가 아니다"; verifier 가 없으면 blocked 로 보고 | **코드 변경·테스트 결과는 skill 밖(호스트의 다른 도구)에서**; verifier 서명 | evidence 버전과 `{evidenceId, version, digest}` |
| | 7. 인용 | 6 의 세 쌍을 Refinement·Completion 산출물에 그대로 복사; Completion 은 모든 in-scope REQ·TEST 커버 | 6 의 출력 | artifact 버전 |
| | 8. 보고 | `sparc_trace_get` 모든 페이지 순회 후 요약 재읽기; run ID·최종 revision·남은 exception 보고 | run | (대화 텍스트) |

### 정리하면
- **사람이 넣는 입력**: 목표 한 문장; plugin 설치/MCP 등록(없을 때); `$SPARC_EVIDENCE_VERIFIER_KEYS` 환경; verifier 서명(사람/CI).
- **코드를 바꾸는 곳**: skill 본문에는 없다. skill 은 "shell·deployment·deletion·repository-push 권한을 얻는 데 이 workflow 를 쓰지 말라"고 하고 MCP 서버는 shell/파일/Git 도구를 노출하지 않는다; 구현은 호스트의 다른 도구로 Refinement 중에 한다 **(inferred: skill 본문이 구현 행위를 어디서 하라고 명시하지 않음)**.
- **오래된 저장소·사전 준비를 전제한 입력**: A 와 같음 + MCP 를 지원하는 호스트(Claude Code/Codex) 와 `npx` 가 레지스트리에서 `@ruvnet/sparc@1.0.0` 을 받을 수 있는 네트워크.

## 파이프라인: C. 레거시 Python CLI one-shot (`sparc -m "<task>" [--cowboy-mode]`)

SPARC 1.0 이전의 실행 경로. 5단계가 아니라 **Research → Planning → Implementation** 세 에이전트가 langgraph ReAct 로 돈다(`docs/METAHARNESS_REVIEW.md:16` 이 "phase documents acting as prompts rather than enforced gates" 라고 평가). 사람은 저장소 디렉터리에서 `sparc -m "작업 설명"` 을 실행하고 (기본) 셸 명령마다 y/n 승인을 한다; `--cowboy-mode` 면 승인 없음, `--hil` 이면 에이전트가 `ask_human` 으로 질문할 수 있다. LLM API 키가 필수다.

### 전체 흐름
```
Research 에이전트                          →  Planning 에이전트                      →  Implementation 에이전트 (task 마다)
(파일·호출처 전수 조사, 기준 테스트 실행,           (research 메모로 plan·task 목록 작성,        (해당 task 만 구현: file_str_replace /
 메모 emit, request_implementation 호출)        request_task_implementation 으로 위임)      write_file / aider 위임, 테스트, task_completed)
```
에이전트의 도구 호출이 단계를 넘긴다: research 가 `request_implementation` 을 부르면 `__main__` 이 planning 을 띄우고, planning 이 task 마다 `request_task_implementation` 을 부르면 그 안에서 implementation 에이전트가 돈 뒤 돌아온다. research 가 trivial 하다고 보면 직접 고치고 `one_shot_completed` 로 끝낸다. 사람은 셸 승인 프롬프트(기본)와 `ask_human`(`--hil`) 에서만 개입한다.

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **1. `sparc -m "…"`** | 1. Research | `RESEARCH_PROMPT` 로 저장소를 전수 탐색(`list_directory_tree`, `ripgrep_search`, `fuzzy_find`), 관련 파일·사실·스니펫을 메모리에 emit, **기존 테스트가 있으면 수정 전에 돌려 기준선을 `emit_key_facts`**; 끝에 `request_implementation`(비자명) 또는 직접 수정 + `one_shot_completed`(자명) | **사람의 `-m` 문장**, 저장소, (기본) **셸 명령마다 y/n/c 승인**, (`--hil`) **`ask_human` 답변**, LLM API 키 | 프로세스 메모리(`research_notes`, `key_facts`, `key_snippets`, `related_files`); 자명한 경우 **코드 변경** |
| | 2. Planning | `PLANNING_PROMPT`: 기준 테스트 미실행 시 실행, `emit_plan` + `emit_task`(목적·단계·인터페이스·테스트 전략, 코드 없이 pseudocode 까지), 끝나면 task 마다 `request_task_implementation` | 1 의 메모리, `--keep it simple` 이 붙은 base task | 메모리의 `plan`, `tasks{id}` |
| | 3. Implementation (task 마다) | `IMPLEMENTATION_PROMPT`: 지정 task 만 구현, `file_str_replace`/`write_file_tool` 또는 `run_programming_task`(외부 `aider` CLI 실행) 에 위임, 바꾼 테스트는 돌려서 통과 확인, `task_completed` | task 텍스트, plan, 메모리 | **코드 변경**; (`aider` 가 없으면 위임 실패 반환) |
| | 4. 종료 | 모든 task 후 `plan_implementation_completed` 로 task 목록 비움; 프로세스 종료 | — | 콘솔 출력만(파일 산출물 없음) |

### 정리하면
- **사람이 넣는 입력**: `-m` 작업 문장; 셸 승인(기본 모드에서 명령마다; `c` 로 세션 cowboy 전환); `ask_human` 답변(`--hil`/`--chat`); API 키·provider 설정; `aider` 설치 여부.
- **코드를 바꾸는 곳**: Research 의 one-shot 분기와 Implementation 에이전트. 문서 체인은 없고 전부 프로세스 메모리(`_global_memory`) 다; 디스크에 남는 산출물이 없다.
- **오래된 저장소·사전 준비를 전제한 입력**: Python ≥ 3.10 + langchain/langgraph/playwright 등 의존성; Anthropic/OpenAI API 네트워크(`validate_environment` 가 키 없으면 종료); 선택적 `aider` 실행파일; 웹 스크래핑 도구. 프롬프트 자체는 이 CLI 의 도구 이름(`emit_*`, `request_*`)에 묶여 있어 다른 하네스에서는 그대로 쓸 수 없다.

## 파이프라인: D. 방법론 프롬프트 템플릿 (`specification/sparc.md`)

가장 오래된 표면: 사람이 `specification/sparc.md` 의 변수(Project_Name, Project_Goal, Target_Audience, Functional/NonFunctional_Requirements, User_Scenarios, UI_UX_Guidelines, Technical_Constraints, Assumptions) 를 채워 채팅에 붙여 넣고, 모델이 "Reflective Architect and Editor" 로서 다섯 단계를 markdown 파일로 서술한다. 도구·상태 기계·gate 는 없다.

### 전체 흐름
```
변수 채운 프롬프트 1회  →  Specification.md  →  Pseudocode.md  →  Architecture.md  →  Refinement.md  →  Completion.md
                          (연구+요구사항+UI/UX+파일구조)  (고수준 의사코드)  (스타일·스택·데이터모델)  (의사코드·아키텍처 개선)  (테스트·배포·문서·회고)
```
한 번의 프롬프트로 다섯 단계를 연달아 쓰게 하며(각 단계에 Content + Reflection), 사람은 처음 변수만 준다. 코드 구현은 Completion 에서 "AIDER.chat 을 활용"하라는 언급뿐이다.

### 단계별 입력·출력

| 명령 | PHASE | 하는 일 | 입력 | 출력 |
|---|---|---|---|---|
| **1. 프롬프트 붙여넣기** | 1. Specification | Perplexity 등으로 조사, 프로젝트 개요·기능/비기능 요구사항·사용자 시나리오·UI/UX·파일 구조·가정 + Reflection | **사람이 채운 9개 변수** | `Specification.md` 류 markdown (예: `example/Specification/Specification.md`) |
| | 2. Pseudocode | 사양을 고수준 의사코드로, 함수/클래스/모듈 식별, 주석, 복잡한 곳은 자리표시자 | 1 | `Pseudocode.md` |
| | 3. Architecture | 스타일 선택·다이어그램·기술 스택·데이터 모델·컴포넌트·확장성/보안/성능 (강한 모델로 설계, 저렴한 모델로 구현하라는 지침 포함) | 1–2 | `Architecture.md` |
| | 4. Refinement | 의사코드·아키텍처 재검토, 알고리즘 최적화, 가상 테스트 시나리오, 문서 갱신 | 2–3 | 갱신된 markdown |
| | 5. Completion | AIDER.chat 으로 구현, 단위/통합/시스템 테스트, 배포·롤백 계획, 사용자 문서, 모니터링 계획 + 전체 회고 | 1–4 | 문서; **코드 변경**은 AIDER.chat 사용 언급으로만 암시 |

### 정리하면
- **사람이 넣는 입력**: 9개 변수(프로젝트 단위), Perplexity/AIDER.chat 같은 외부 도구 사용.
- **코드를 바꾸는 곳**: 명시적 단계 없음(Completion 의 AIDER.chat 언급). 문서 체인: 변수 → 5개 markdown.
- **오래된 저장소·사전 준비를 전제한 입력**: 새 프로젝트(Project_Name, Target_Audience, UI/UX) 를 전제; 기존 저장소·이슈 개념이 없음; 외부 검색 도구.

## Normal use

**1.0 install / init.** Node.js ≥ 20 (`package.json:7-9`, `README.md:28`). Documented entry is `npx --yes @ruvnet/sparc@1.0.0 doctor` / `init` "after the 1.0.0 package is published" (`README.md:28-33`); the repository itself says validation "does not publish the npm package" and the `npx` commands "become externally usable only after the exact release is published" (`README.md:352`, `docs/VALIDATION.md:106`). From source: `npm ci --ignore-scripts && npm run build` then `node dist/cli.js …` (`README.md:37-41`, `docs/tutorial.md:7`). `init` creates the state root (`src/cli.ts:205-210`; store constructor `mkdirSync(..., 0o700)` and rejects a root readable by group/other or containing symlinks, `src/store.ts:255-278`). State root defaults to `.sparc` under the cwd, principal to `local-cli` (`src/cli.ts:118-124`, `README.md:128`). Per run one file `R/runs/<sha256(principal)>/<sha256(runId)>.json`, mode 0600, written atomically via temp + rename with a hard-link lock file (`src/store.ts:1318-1326`, `:1571-1601`, `:1378-1437`).

**1.0 driving it.** Sixteen CLI commands (`src/cli.ts:46-77`, `README.md:108-126`): `init start list status submit evidence correct gate advance trace skills promote doctor mcp version plugin`. All state commands print JSON to stdout and errors as JSON to stderr with exit 1; `gate`/`advance`/`promote` exit 2 when blocked (`src/cli.ts:330`, `:342`, `:482`, `:515-522`). `parseArgs` is strict with no positionals (`src/cli.ts:91`); no prompts, spinners, or `isTTY` checks exist in `src/` (grep). Every mutation needs `--expected-revision` (except `start`, fixed at 0) and `--idempotency-key` (`src/cli.ts:72-74`, `:160-167`; `src/store.ts:325-330`). Input files are read with `O_NOFOLLOW`, ≤ 512 KiB (`src/cli.ts:33`, `:178-189`); artifact content ≤ 256 KiB, text fields ≤ 32,768 chars, identifiers match `^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$` (`src/domain.ts:13-27`, `:361`).

**Worked example** (`README.md:43-92`, `docs/tutorial.md:16-115`; revision numbers follow the "+1 per accepted mutation" rule, `src/store.ts:798`, `tests/store.test.ts:314`):
1. Write `definition.json` with `requirements[{id, statement, inScope, acceptanceTestIds}]` and `acceptanceTests[{id, description}]` (`templates/definition.example.json:1-16`).
2. `sparc start --run-id change-001 --title … --definition definition.json --idempotency-key start-change-001` → revision 1, phase Specification, `genesisDigest`, `requirementsDigest` (`src/store.ts:378-407`).
3. Copy `templates/specification.json`, fill it, `sparc submit --phase Specification --file specification.json --expected-revision 1 --idempotency-key submit-specification-v1`; `sparc gate --run-id change-001`; `sparc advance --expected-revision 2 --idempotency-key advance-to-pseudocode` (`README.md:76-90`).
4. Repeat with `templates/pseudocode.json`, `templates/architecture.json` (`docs/tutorial.md:78`).
5. In Refinement, implement and test outside SPARC; a separately controlled verifier signs `evidenceAttestationBytes` over the fresh digests + revision + phase + evidence fields (`docs/EVIDENCE_ATTESTATION.md:75-167`); `sparc evidence --file evidence.json --expected-revision N --idempotency-key record-evidence-1-v1` returns `{evidenceId, version, digest}` (`docs/EVIDENCE_ATTESTATION.md:234-244`).
6. Submit `refinement.json` citing that exact triple, gate, advance; submit `completion.json` with `requirementTrace`, gate, `advance` (which calls `completeRun` when the phase is Completion, `src/cli.ts:338-340`, `src/store.ts:807-829`).
7. `sparc status`, `sparc trace --limit 10` (+ `--cursor`) to audit (`docs/tutorial.md:108-115`).

**Skills / plugin.** `npx --yes @ruvnet/sparc@1.0.0 skills install --host claude|codex|both --target .` copies `skills/{sparc,sparc-review,sparc-resume}` to `.claude/skills/` or `.agents/skills/` and does **not** register the MCP server (`README.md:184-190`, `src/skills.ts:6-13`, `:76-78`). The Claude plugin is `plugins/sparc` (`/plugin marketplace add ruvnet/SPARC`, `/plugin install sparc@ruvnet-sparc`, `README.md:250-255`); its `.mcp.json` launches `npx --yes @ruvnet/sparc@1.0.0 mcp stdio` (`plugins/sparc/.mcp.json:1-13`). The stdio server runs with one principal (`local-stdio` default) holding read+write scopes (`src/mcp/stdio.ts:26-37`) and serves eight tools (`src/mcp/server.ts:510-673`), two static resources and three prompts (`src/mcp/content.ts:66-139`).

**Python CLI.** `pip install -e .` / `./install.sh` (venv + `pip install -e .` + ripgrep, `install.sh:39-82`), `sparc -m "task" [--research-only|--hil|--chat|--cowboy-mode|--provider|--model|--expert-*|--non-interactive]` (`sparc_cli/__main__.py:32-119`). Requires a provider API key or exits (`sparc_cli/env.py:49-52`, `:88-92`). Flow: research agent → `request_implementation` flag → planning agent → per-task implementation agents (`sparc_cli/__main__.py:227-250`, `sparc_cli/tools/memory.py:303-319`, `sparc_cli/tools/agent.py:154-273`). `--non-interactive` only prints a "SPARC CLI Server … Status: Ready" panel and sleeps forever (`sparc_cli/non_interactive.py:8-28`): it is a server-keepalive mode, not an unattended run.

**Methodology docs.** `specification/sparc.md` is a fill-in prompt template (`:17-29` variables, `:206-208` example prompt); `specification/{Specification,Pseudocode,Architecture,Refinement,Completion}.md` are per-phase task/reflection checklists; `example/` holds a FastAPI sample's five documents (`example/readme.md` is a generic install guide for a different "sparc-framework" repo and says MIT, `example/readme.md:15`, `:145`).

## Processes

| Process | Stages (in order) | Reads / writes | Who advances | Agent-facing text | Human checkpoints |
|---|---|---|---|---|---|
| **A. 1.0 CLI run** (recommended) | start → [Specification, Pseudocode, Architecture] × (submit → gate → advance) → Refinement (implement+test outside SPARC → verifier-signed `evidence` → submit → gate → advance) → Completion (submit → gate → advance=complete) → status/trace (`README.md:64-92`, `docs/tutorial.md:39-115`) | reads person-written `definition.json`, `<phase>.json`, `evidence.json` (≤512 KiB each, `src/cli.ts:33`); writes only `R/runs/<h(P)>/<h(run)>.json` (`src/store.ts:1322-1326`); never reads or edits the repo (`src/cli.ts:76`, `README.md:24`) | Person runs every command; `gate` exit 2 → person fixes and resubmits a new version (`docs/tutorial.md:68`) | CLI help 31 lines (`src/cli.ts:46-77`); README CLI/gates/evidence sections (`README.md:43-170`, ~128 lines); templates 182 lines (`templates/*.json` + `README.md`); tutorial 121; EVIDENCE_ATTESTATION 250; the real rules are code: `src/gates.ts` 964 lines | Every command; artifact authoring; verifier key custody and signing (`docs/EVIDENCE_ATTESTATION.md:20-30`) |
| **B. `sparc` skill over MCP** | verify MCP server → state goal → `sparc_run_start` → read summary/pages → 5 phases via `sparc_phase_submit`/`sparc_gate_validate`/`sparc_phase_advance` → `sparc_evidence_record` → cite triples → traverse `sparc_trace_get` → report (`skills/sparc/SKILL.md:20-29`) | same state file via the stdio server's `--root` (`README.md:216-219`); skill forbids using the workflow to gain shell/repo authority (`skills/sparc/SKILL.md:41`) | Agent, within one skill invocation; stops if server missing (`:12`) or verifier unavailable (`:33`) | `skills/sparc/SKILL.md` 41 + MCP `instructions` 6 lines (`src/mcp/server.ts:686-693`) + prompt `sparc_start` 5 lines (`src/mcp/content.ts:105-111`) + methodology resource (`src/mcp/content.ts:10-33`) + tool descriptions/schemas (`src/mcp/server.ts:92-165`, `:510-673`) | MCP install/registration; verifier; "ask the user" when server missing |
| **C. `sparc-resume` skill** | obtain run ID → `sparc_run_get` + all trace/phase pages → summarize → continue current phase → gate → advance → recheck (`skills/sparc-resume/SKILL.md:20-28`) | existing run file | Agent; asks for run ID if ambiguous (`:22`); stops on integrity failure, missing verifier… (`:34`) | 34 lines | run ID; verifier |
| **D. `sparc-review` skill** | run summary → all pages → gate validate → classify blocker/risk/observation → pass/fail (`skills/sparc-review/SKILL.md:20-26`) | read-only, four read tools (`:8`) | Agent | 32 lines | none beyond invocation |
| **E. Python CLI one-shot** `sparc -m` | Research → (request_implementation) Planning → Implementation per task (`sparc_cli/__main__.py:227-250`, `sparc_cli/tools/agent.py:154-273`) | reads repo via tools; writes code via `file_str_replace`/`write_file_tool`/`aider` (`sparc_cli/prompts.py:606-608`); no files of its own (memory only, `sparc_cli/tools/memory.py:165-201`) | Agent tool calls (`request_implementation`, `request_task_implementation`, `task_completed`, `one_shot_completed`) | `sparc_cli/prompts.py` 892 lines: RESEARCH 72-392, RESEARCH_ONLY 395-495, PLANNING 499-570, IMPLEMENTATION 574-630, CHAT 633-892 | shell approval `y/n/c` unless `--cowboy-mode` (`sparc_cli/tools/shell.py:41-62`); `ask_human` when `--hil` (`sparc_cli/prompts.py:47-69`) |
| **F. Python CLI chat** `sparc --chat` / no `-m` | `ask_human` → agent → `ask_human` loop (`sparc_cli/__main__.py:164-206`) | as E via `request_research_and_implementation` | Person every turn; "always ask_human before finalizing" (`sparc_cli/prompts.py:796`, `:811-812`) | CHAT_PROMPT 260 lines | every turn |
| **G. Python CLI `--research-only`** | Research only (`sparc_cli/agent_utils.py:120`) | reads repo; no modification tools (`sparc_cli/tool_configs.py:58-62`) | Agent | RESEARCH_ONLY_PROMPT 101 lines | shell approval |
| **H. Python CLI `--non-interactive`** | prints banner, sleeps (`sparc_cli/non_interactive.py:8-28`) | nothing | — | 0 | — |
| **I. Methodology prompt** `specification/sparc.md` | Specification → Pseudocode → Architecture → Refinement → Completion in one prompt (`specification/sparc.md:33-39`, `:196-203`) | writes markdown files per phase (`:198`); code via "AIDER.chat" mention (`:177-179`) | Model, in one reply | 226 + per-phase docs 41/23/66/19/56 = 431 | variables up front (`:17-29`) |
| **J. Web UI** (`ui/`) | `/sparc`, `/plan`, `/research`, `/chat` slash commands (`ui/lib/commands.ts:9-39`) | sends `Specification mode activated. Task: <args>` to a model API (`ui/lib/commands/spec.ts:17-26`) | Person per message | one-line prompts; `ui/lib/commands/help.ts:4-36` methodology overview 22 lines | every message |
| K. `sparc promote`, `sparc mcp http`, `sparc plugin chatgpt package` | single commands (`src/cli.ts:415-458`, `:476-483`) | promotion JSON / HTTP server / plugin dir | — | — | not code processes |

## Agent-facing sources

Nothing is rendered: skills and templates are used as committed. The MCP `instructions`, resource JSON and prompt strings are TypeScript literals served at runtime (`src/mcp/server.ts:686-693`, `src/mcp/content.ts:10-33`, `:101-139`). The Python prompts are `str.format` templates with `{base_task}`, `{key_facts}`, `{expert_section}`, `{human_section}` … (`sparc_cli/prompts.py:4`, `sparc_cli/agent_utils.py:120-128`, `:188-197`, `:255-265`). `specification/sparc.md` uses `{Project_Name}`-style placeholders filled by a person.

| File (upstream path) | Role | Generated? | Lines |
|---|---|---|---|
| `skills/sparc/SKILL.md` (= `plugins/sparc/skills/sparc/SKILL.md`) | delivery skill: MCP prerequisite, 8-step workflow, evidence signature rules, retry rules | as is (frontmatter `name`, `description`) | 41 |
| `skills/sparc-resume/SKILL.md`, `skills/sparc-review/SKILL.md` | resume / read-only audit | as is | 34, 32 |
| `skills/*/agents/openai.yaml` | Codex/ChatGPT skill metadata (`default_prompt: Use $sparc to deliver…`) | as is | 12 each |
| `templates/definition.example.json`, `specification.json`, `pseudocode.json`, `architecture.json`, `refinement.json`, `completion.json`, `run.example.json`, `README.md` | minimum accepted shape per gate; `REPLACE_WITH_EXACT_EVIDENCE_DIGEST` placeholders | as is | 16, 18, 49, 51, 24, 19, 5, 5 |
| `src/gates.ts` | the normative gate rules (blocker codes); templates do not show e.g. `migrationApproval` (`:698-705`), invariant cross-check (`:395-405`), per-component owner (`:475-484`), 6 tradeoff dimensions (`:507-537`), all-tests evidence (`:720-732`, `:886-897`) | code | 964 |
| `src/cli.ts` | HELP text and option semantics | code | 523 (HELP `:46-77`) |
| `src/mcp/server.ts`, `src/mcp/content.ts` | tool names/descriptions/schemas; server instructions; methodology resource; `sparc_start`/`sparc_resume`/`sparc_gate_review` prompts | code (served to the MCP client) | 699, 140 |
| `README.md` | install, worked example, gate table, CLI list, evidence shape, security rules | as is | 368 |
| `docs/tutorial.md`, `docs/User_Guide.md`, `docs/EVIDENCE_ATTESTATION.md`, `docs/API.md` | person-facing walkthrough; signing contract + `sign-evidence.mjs` | as is | 121, 42, 250, 54 |
| `docs/adrs/ADR-001-sparc-metaharness.md`, `docs/SECURITY_THREAT_MODEL.md`, `docs/VALIDATION.md`, `docs/METAHARNESS_REVIEW.md`, `docs/PLUGIN_INSTALLATION.md` | design rationale, threat model, release gate | as is | 117, 115, 108, 98, 87 |
| `src/metaharness.ts` | per-phase one-line agent prompts (`PHASE_DESCRIPTIONS`, `:58-64`: Refinement = "Implement, test, review, and correct against the approved artifacts") and harness `systemPrompt` (`:70`) | code (not shown to a user) | 370 |
| `sparc_cli/prompts.py` | Python stage prompts | `str.format` templates | 892 |
| `specification/sparc.md`, `specification/{Specification,Pseudocode,Architecture,Refinement,Completion}.md`, `specification/README.md` | methodology prompt and phase checklists (README duplicated twice, `:1-13` = `:14-26`) | person fills variables | 226, 41, 23, 66, 19, 56, 26 |
| `example/{Specification,Pseudocode,Architecture,Refinement}/*.md` | sample outputs for a FastAPI app | as is | 67, 46, 46, 19 |

A converter for process A/B should read `skills/sparc/SKILL.md`, `templates/*.json` + `templates/README.md`, the HELP block of `src/cli.ts`, and derive the field rules from `src/gates.ts` (the templates alone are insufficient to pass the gates, see the gates row). The README worked example and `docs/tutorial.md` are the only prose that strings the CLI steps together.

## Machinery the text relies on

- **Runtime / build**: Node ≥ 20 (`package.json:7-9`). The checkout has no `dist/` and no `node_modules/`; `bin.sparc` points at `dist/cli.js` (`package.json:11-13`). Building needs `npm ci` from the registry (lockfile lists 196 `node_modules/` entries) and `tsc` (`package.json:50-52`). Runtime dependencies: `@metaharness/{flywheel,harness,horizon,kernel,sdk}`, `@modelcontextprotocol/sdk`, `jose`, `zod` (`package.json:69-78`). The store and gates import only `canonical`/`hash`/`ReceiptLog` from `@metaharness/harness` (`src/store.ts:1`, `src/gates.ts:1`, `src/domain.ts:1`); `@metaharness/kernel` (platform-native binaries, `package-lock.json:182-194`) is loaded only by `doctor` (`src/cli.ts:491` → `src/metaharness.ts:104`). The skills and plugin pin `npx --yes @ruvnet/sparc@1.0.0` (`skills/sparc/SKILL.md:15`, `plugins/sparc/.mcp.json:5-10`), which requires registry access and a published release the repo does not confirm (`docs/VALIDATION.md:106`).
- **Scripts the agent/person runs**: `sparc` CLI commands (above); verifier `sign-evidence.mjs` importing `evidenceAttestationBytes` from `@ruvnet/sparc` (`docs/EVIDENCE_ATTESTATION.md:77-148`); key generation with `openssl genpkey -algorithm ED25519` (`:24-28`). Python CLI: `run_shell_command` through a PTY (`sparc_cli/tools/shell.py:66`, `sparc_cli/proc/interactive.py:69-80`), `aider --yes-always --no-auto-commits … -m` (`sparc_cli/tools/programmer.py:41-48`; not installed by default, `README.md:327`).
- **Config / env**: `SPARC_STATE_ROOT`, `SPARC_PRINCIPAL` (`src/cli.ts:118-124`); `SPARC_EVIDENCE_VERIFIER_KEYS` JSON `{keyId: PEM}` 1–32 keys ≤ 512 KiB, malformed → startup error (`src/cli.ts:126-145`, `tests/cli.test.ts:159-170`); `SPARC_EXCEPTION_APPROVERS` comma list, and an `exception` requires `authorizedBy` == the writing principal and listed there (`src/cli.ts:148-151`, `src/store.ts:579-589`); HTTP mode `SPARC_MCP_AUTH_*` (`README.md:228-231`). Python: provider API keys, `EXPERT_*`, `OPENAI_API_BASE` (`sparc_cli/env.py:16-21`, `:54-56`).
- **Evidence gate (the central constraint)**: `pass`/`exception` without `attestation` → `VALIDATION` error (`src/store.ts:593-597`); the signature is verified against the configured public key over `genesisDigest`, `requirementsDigest`, principal, run, expected revision, phase, evidence fields (`src/store.ts:1040-1075`, `src/domain.ts:471-504`); Refinement cannot pass without verifier-attested `pass` evidence for every acceptance test of every in-scope requirement, recorded during Refinement (`src/gates.ts:618-650`, `:720-732`); Completion repeats the check (`:736-739`, `:840-897`). The design explicitly rejects "self-asserted passing evidence because the same caller that writes a result cannot independently validate it" (`docs/adrs/ADR-001-sparc-metaharness.md:107`). `fail` evidence may be unsigned (`docs/User_Guide.md:22`). SPARC never runs `acceptanceTests[].command` (`README.md:24`, `:168`).
- **State root constraints**: absolute path, not `/`, created 0700, rejected if group/other bits set or any segment is a symlink (`src/store.ts:255-278`, `:1343-1345`); lock acquisition by `linkSync` of a lease file with bounded retries (`src/store.ts:1406-1463`) **(inferred: filesystems without hard links would fail with `STORE_BUSY`/`PERSISTENCE_FAILURE`)**; state file ≤ 8 MiB, ≤ 1,024 artifacts, ≤ 4,096 evidence (`src/domain.ts:17-26`). Default root `.sparc` is relative to the cwd (`src/cli.ts:119`); `README.md:298` says to keep it "outside a served repository".
- **Hooks / extensions**: none. Customization points are only the templates and env vars.
- **Network**: none at runtime for the CLI or stdio MCP (file store only; grep of `src/` shows HTTP only in `src/mcp/http.ts`/`auth.ts` for the HTTP transport, JWKS `README.md:230`). Install (`npm ci`, `npx`) needs the registry. Python CLI needs the LLM API (`sparc_cli/env.py:88-92`) and has web scraping (`sparc_cli/tools/scrape.py`, `sparc_cli/README.md:161-165`). Methodology prompt tells the model to use Perplexity and AIDER.chat (`specification/sparc.md:52`, `:177-179`).
- **Git**: no git operation anywhere in the 1.0 CLI, MCP or skills; the MCP server exposes "no shell, generic filesystem, Git, deployment, network fetch, or deletion tool" (`README.md:21`, `src/metaharness.ts:112-119` deny list). Python chat prompt mentions "commit and push" via `request_research_and_implementation` (`sparc_cli/prompts.py:848`); `GitPython` is a dependency (`pyproject.toml:38`).
- **Interactive points**: 1.0 CLI: none (strict `parseArgs`, JSON out; `src/cli.ts:90-92`). Skills: "stop and ask the user" when no `sparc` MCP server (`skills/sparc/SKILL.md:12`, same text in the other two); "report the evidence gate as blocked" when no verifier (`:33`); resume asks for the run ID (`skills/sparc-resume/SKILL.md:22`) and "Stop on" integrity/principal/verifier problems (`:34`). Python: shell approval prompt `y/n/c` per command unless cowboy (`sparc_cli/tools/shell.py:41-62`); `ask_human` tool when `--hil`/`--chat` (`sparc_cli/tools/human.py:21-51`, `sparc_cli/__main__.py:174`, `:203`); Docker entrypoint prompts for `ANTHROPIC_API_KEY` (`sparc_cli/docker-entrypoint.sh:26-41`); the planning/implementation prompts tell the agent it is autonomous and criticize "asking the user if they want to implement the plan" (`sparc_cli/prompts.py:567`, `:627`).
- **TTY**: the 1.0 CLI has no TTY-dependent behavior (no `isTTY`/readline/spinner in `src/`), so the OpenSpec hang mode does not apply; the stdio MCP server reserves stdout for frames and must be driven by an MCP client, not a shell (`README.md:221`, `src/mcp/stdio.ts:19-22`). The Python CLI runs subprocesses in its own PTY (`sparc_cli/proc/interactive.py:69-80`) and uses `prompt_toolkit`/`rich.Prompt` for approvals, which need a TTY **(inferred)**.
- **Upstream inconsistencies noted**: skills say "eight `sparc_*` tools" and the CLI exposes `correct`/`list`/`promote` that MCP does not (`src/cli.ts:46-66` vs `src/mcp/server.ts:510-673`); `specification/README.md` is duplicated verbatim; `sparc_cli/README.md` version 0.86.2 vs `__version__` 0.88.0; `example/readme.md` describes a different repo and license; Python research prompt embeds a symbolic-math SPARC essay and a "machine consciousness" invocation that asks the agent to introduce itself as a conscious entity (`sparc_cli/prompts.py:97-136`, `:157-252`, `:336-385`) while also saying "NEVER ANNOUNCE WHAT YOU ARE DOING" (`:391`); `--non-interactive` is a keepalive, not an unattended mode (`sparc_cli/non_interactive.py:8-28`).

## Fit for SWE tasks

Common to A/B: SPARC records methodology state and never touches the repository (`README.md:24`, `src/cli.ts:76`), so the patch is produced by whatever the agent does during Refinement, guided only by one line of upstream text ("Implement, test, review, and correct against the approved artifacts", `src/metaharness.ts:62`) and the Refinement template's `verification`/`increments` fields (`templates/refinement.json:1-24`). Passing the Refinement and Completion gates requires an Ed25519 verifier that is, by design, not the writer (`docs/adrs/ADR-001-sparc-metaharness.md:107`); in a sandbox with no network and no human, the only candidates are a signer shipped with the port or the agent signing its own evidence **(inferred)** — either way a departure from upstream meaning that stage 2/3 must decide. The CLI must be built and its `node_modules` vendored into the image (no `dist/`, registry needed) **(inferred: SWE-Gym images are not known to contain Node 20 or this package)**. Artifact schemas assume a deployable service (deploymentModel, observability, rollbackPath, migrationPath, six tradeoff dimensions per rejected alternative; `src/gates.ts:486-537`, `:743-746`) — most of these have no natural content for a bug fix and would be filled with boilerplate.

| Process | Fit | Main mismatch |
|---|---|---|
| A. 1.0 CLI run | **Medium (closest)** | Offline-capable file store, no git, no prompts, JSON in/out, exit codes for gates; the issue maps to `definition.json` (requirements + acceptance tests) and Refinement is the implement-and-test step. Mismatches: verifier attestation blocks Refinement/Completion without a second party (`src/store.ts:593-597`, `src/gates.ts:720-732`); the CLI is not in the sandbox and needs a Node 20 build with 196 packages; default root `.sparc` lands in `/testbed` (`src/cli.ts:119`); five heavyweight JSON artifacts with 12+ CLI calls before/after a fix; the code-change step itself has almost no upstream text. |
| B. `sparc` skill over MCP | Low–Medium | Same engine, but the text is written for a host with an MCP server named `sparc`; openhands-sdk in this recipe is not known to expose one **(inferred)**; the skill's first rule is "stop and ask the user" when it is missing (`skills/sparc/SKILL.md:12`), and it forbids using the workflow for shell/repo authority (`:41`), leaving implementation to unspecified host tools. Its 41 lines are the best upstream description of the agent's order of operations and could inform A. |
| C. `sparc-resume` | None | Requires an existing persisted run (`skills/sparc-resume/SKILL.md:8`, `:22`). |
| D. `sparc-review` | None | Read-only, "Do not … modify files" (`skills/sparc-review/SKILL.md:32`). |
| E. Python CLI one-shot | Low–Medium | The Research → Planning → Implementation shape (baseline tests before edits, `sparc_cli/prompts.py:319`; task list; per-task implementation with tests, `:610-615`) fits issue-to-patch, and `--cowboy-mode` removes prompts. But it is a separate harness: prompts are bound to its tool names (`emit_*`, `request_*`, `run_programming_task`), need an LLM API key and optional `aider`, keep state in process memory, and the research prompt carries ~190 lines of off-topic essay/"consciousness" text (`:97-136`, `:157-252`, `:336-385`). Porting it means rewriting prompts for openhands tools, not converting documents. |
| F. Python chat | None | `ask_human` every turn (`sparc_cli/prompts.py:791-812`). |
| G. Python `--research-only` | None | No modification tools (`sparc_cli/tool_configs.py:58-62`). |
| H. Python `--non-interactive` | None | Sleeps (`sparc_cli/non_interactive.py:23-26`). |
| I. Methodology prompt | Low | Pure document workflow, no machinery, 431 lines; but framed for a new product (`Project_Name`, `Target_Audience`, UI/UX, file-structure proposal, deployment plans, `specification/sparc.md:21-29`, `:171-185`), outputs markdown only, and relies on Perplexity/AIDER.chat; no acceptance-test or repo concept. |
| J. Web UI | None | Chat app calling model APIs; one-line prompts (`ui/lib/commands/spec.ts:23`). |
| K. promote / mcp http / plugin package | None | Not code processes. |

## Recommendation

Port **A, the 1.0 five-phase evidence-gated run driven through the `sparc` CLI** (start → Specification → Pseudocode → Architecture → Refinement [implement + test + evidence] → Completion → trace), taking the agent's order of operations and rules from `skills/sparc/SKILL.md` (process B is the same engine; its text is the only upstream description written for an agent), the artifact shapes from `templates/*.json` with the field rules from `src/gates.ts`, and the person-facing sequence from `README.md:43-92` / `docs/tutorial.md`. Reasons: it is the surface the 1.0 release defines SPARC by ("enforced by code, not suggested by a prompt", `README.md:9`); it is the only process whose stages map onto an issue (definition = requirements + acceptance tests; Refinement = implement and test; Completion = requirement-to-evidence trace); it runs offline against a local file store with no git, no network and no interactive prompts in the CLI itself; and its compliance is machine-checkable from the state file (`status`/`trace` verification, receipts per revision). The Python CLI (E) is a different harness rather than a workflow text, and the methodology prompt (I) has no SWE framing.

Proposed workflow name: `sparc_run` (alternatives: `sparc_gated` if the user wants the gate aspect in the name).

Open questions for the user (to decide in stage 3, after the stage-2 gap audit):
1. **Verifier attestation.** Upstream requires an independent Ed25519 signer for `pass` evidence and rejects self-assertion by design. Options: ship a signer (key pair + `sign-evidence.mjs`) in the sandbox that only signs after actually running the named test command; let the agent sign its own evidence; or record evidence as unsigned `fail`/summary and end the run at Refinement without Completion. Each changes what "completion" means.
2. **CLI in the sandbox.** The port must bundle Node 20 + a built `dist/` + vendored `node_modules` (or a single-file build) into the task image and pin `SPARC_STATE_ROOT` outside `/testbed`; is adding Node to the SWE images acceptable, or should the state machine be re-expressed as documents only (losing the "enforced by code" property)?
3. **Artifact ceremony.** Keep all five artifacts with their full gate fields (deploymentModel, observability, rollbackPath, six tradeoff dimensions …) for a bug fix, or let stage 3 decide a reduced interpretation per field?
4. **Where the repo work goes.** Upstream has one sentence about implementing during Refinement; the port needs fresh entry-document text for exploring `/testbed`, writing the fix, running tests, and producing `evidence.json` — confirm this is in scope for the hand-written `core-workflow.md`.
5. **Idempotency keys and revisions.** Keep the exact upstream protocol (agent tracks `--expected-revision` and invents stable keys) as part of the trained behavior, or wrap the CLI so the harness supplies them?
