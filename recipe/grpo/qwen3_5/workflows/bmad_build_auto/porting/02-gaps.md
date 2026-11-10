# Gaps: bmad_build_auto  (upstream bmad-code-org/BMAD-METHOD @ 10db8f35 v6.12.2, process `bmad-build-auto`)

## Setting

- One user message (instruction + SWE task text, issue in `<issue_description>`, repo at `/testbed`), an
  openhands-sdk 1.42.1 agent with Terminal / FileEditor / TaskTracker tools (rllm/harnesses/tools/openhands_sdk_runner.py:124-126),
  no network, hidden tests grade the final `git diff` of the working tree (run_artifacts.py:9), no commits.
- Upstream assumes: a rendered skill snapshot made by `uv run render_skill.py` (SK:6-9), `_bmad/config.toml`,
  planning artifacts (`PA/*`, epics, `stories.yaml`), a tool that spawns sub-agents (WF: "HALT `blocked / no subagents`"),
  a clean git tree on the right branch (S1), local commits at HALT (S4/HALT).
- Source of every row: `rules.yaml` (stage 1b; 280 rules, each with `port.gap` = the gap ID below and `port.fate`
  = the stage-1b estimate keep / semantic / env / drop). Counts here are rules per gap.

## Gap table

| ID | 단계 | upstream이 요구하는 것 | 여기서 빠지거나 다른 것 | Tag | 규칙 수 (1b 추정: keep/semantic/env/drop) | 상태 |
|---|---|---|---|---|---|---|
| G1 | 1, 2, halt | 호출 프롬프트가 기존 spec·`stories.yaml` 항목·draft를 가리키면 status로 분기하고 재개한다 (S1:20-60, S2 draft 재개) | 매 rollout이 새 의도(이슈 본문)에서 시작한다; 기존 spec·stories·draft가 없다 | env | 24 (0/0/1/23) | decided (03 D-1) |
| G2 | 0 | 설명 수준을 `{{.user_skill_level}}`에 맞춘다 (MB) | 읽는 사람이 없다 | env | 1 (0/0/0/1) | decided (03 D-1) |
| G3 | 1, 3 | epic 경로: `IA/epic-<N>-context.md`를 서브에이전트로 컴파일하고 이전 story spec·`PA/*` 계획 문서를 맥락으로 읽는다 (S1, CE) | 계획 문서·epics 파일이 없다; 항상 freeform 경로 | env | 18 (0/0/0/18) | decided (03 D-1) |
| G4 | 1, 2, 3, 4 | 의도가 불명확하거나 intent gap(복수 해석)이면 고르지 않고 `blocked`로 HALT (S1:73, S2, S3 matrix ambiguity, S4 intent_gap) | 멈추면 patch가 없다 = 과제 실패; 평가 데이터 SWE-bench Verified는 명확한 이슈만이라 발동 조건이 없다; 학습 세 workflow는 가정을 기록하고 진행하라고 보상 (T-SR1) | semantic | 5 (0/5/0/0) + G8의 C12 | decided (03 D-2) |
| G5 | 0, 1, 2, 4, halt | 렌더 스냅샷 절대경로를 따라 문서를 읽고, `{{.implementation_artifacts}}` (= `{project-root}/_bmad-output/...`)에 spec·patch·result를 쓴다 | 렌더러·uv 없음 → port가 문서 경로를 고정; 산출물 디렉터리가 /testbed 안이면 diff·stray에 섞인다 | env | 16 (0/0/15/1) | decided (03 D-5) |
| G6 | halt | push하지 않는다 (HALT) | 네트워크·원격 없음 | env | 1 (0/0/0/1) | decided (03 D-1) |
| G7 | 0, 1, 2, 3, 4, halt | 구현 1 + 리뷰 렌즈 4 (+ 선택: epic 컴파일·깊은 탐색)를 맥락 없는 서브에이전트로 동기·동시에 띄우고 결과를 메시지로 받는다; 없으면 `no subagents`로 HALT (WF, S3, S4, CT) | rllm 러너가 서브에이전트 도구를 붙이지 않았다(2026-11-10 `OPENHANDS_SDK_EXTRA_TOOLS=task` 로 해결); SDK 1.42.1의 서브에이전트 도구는 `task`(TaskToolSet; 호출 1회 = 블로킹 1개, `resume` 재호출) — 처음 적은 DelegateTool 은 등록된 도구가 아님(정정) | semantic | 84 (0/41/5/38) | decided (03 D-1, D-7) |
| G8 | 0, 1, 2, 3, 4, halt | 검증 실패·spec 기준 미달·루프 상한 초과는 `blocked`로 HALT; bad_spec이면 코드를 baseline으로 되돌리고 spec을 고쳐 step-03부터 다시 (상한 5); intent_gap이면 되돌리고 patch 파일 저장 (S4) | blocked 종료는 patch 없음; 되돌리기·재도출은 턴 예산을 크게 쓴다 (150턴) | semantic | 19 (0/14/3/2) | decided (03 D-2, D-4) |
| G9 | 2, 3, 4 | I/O Matrix edge case마다 단위 테스트를 추가하는 task; 행마다 실행·통과한 테스트; Verification Gap patch = 추가할 테스트 지명 (S2, S3, VG) | 학습 세 workflow는 테스트 파일 쓰기를 금지(checks/ 대체); 숨은 테스트 채점은 gold test patch의 파일을 base commit으로 되돌린 뒤 적용한다 (SWE-bench 검증기, `rllm/sandbox/git_history.py:9-10`; 충돌 <1%는 14 §6의 SWE-Gym 측정값, Verified 미측정) | semantic | 5 (0/5/0/0) | decided (03 D-3) |
| G10 | 0, 3 | 문서·대화 언어 토큰 `{{.document_output_language}}` 등; 경로 표기 `path:line` | 토큰은 build 때 English로 치환; 메시지는 채점 안 함 | env | 3 (0/0/3/0) | decided (03 D-5) |
| G11 | — | (port 쪽) 서브에이전트가 돌면 LLM 호출이 대화 여러 개로 갈라진다 | 게이트웨이는 모든 호출을 trace로 잡고 단계 없는 하네스는 전부 step으로 흡수한다 (agentflow_engine.py:215-262); rubric 채점기는 step들을 한 대화로 읽고 replay한다 (workflow_rubric/trace/episode.py:10-12) → 대화 분리 전처리 필요 **(미확인: 실행 전)** | env | 측정 쪽; 규칙 아님 | decided (03 D-7), 4단계 작업 |
| G12 | 2, 3 | spec 파일이 사라졌거나(S2:21 `planned spec file disappeared before implementation`) step-03 진입 시 `{spec_file}`이 비어 있으면(S3:14 `missing spec_file before implementation`) `blocked`로 HALT | D-2의 실패 HALT 5개(D28, F2, F8, F10, G83)에도, D-1의 삭제 목록에도 없음. 에이전트가 방금 쓴 파일이라 실제로는 거의 발동하지 않음. 4단계에서는 원문 그대로 뒀다가 2026-11-10 사용자 결정 "빼자"로 두 문장 삭제(D-8; build.py semantic edit 2건, C30·D25 drop) | semantic | 2 (0/2/0/0) | closed (D-8, 2026-11-10) |

Gap of the measurement, not of the workflow: judge-only rules (measure `judge`, 49 after decisions) need a vLLM judge endpoint
(`AIDLC_JUDGE_*`); decided 03 D-6.
