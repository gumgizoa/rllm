# Decisions: bmad_build_auto  (upstream BMAD-METHOD @ 10db8f35 v6.12.2, process `bmad-build-auto`, **evaluation workflow**)

Scope: the whole `bmad-build-auto` chain (step-01 → 02 → 03 → 04 → HALT) as an *evaluation* workflow of the
SDLC instruction-following study (if/10 §3; precedents aidlc_v4_ifeval, speckit_sdd). Headline decisions by the
user, 2026-11-09 (chat: "서브에이전트 사용, 가정하고 진행, 저장소 테스트 파일, 루프, 재검증 유지, 산출물 밖으로, judge 일단 미사용").
Row-level consequences below follow those six; rows marked **(기본값, 확인 요망)** are my defaults under them.
Resulting layers: `if/scripts/bmad/decided_layers.py` (applies the table to `rules.yaml`).

| ID | Gap | Decision | Tag | Decided | Notes |
|---|---|---|---|---|---|
| D-1 | G1, G2, G3, G6, G7(drop 38 중 기계·VCS·epic 부분) | **삭제 유지**: 호출 모드·기존 spec·stories·draft 재개(G1 23), skill level(G2), epic 경로·epic 컴파일·`context:` 파일(G3 18), push(G6), 렌더러·활성화 훅(A1, A3a/b, A6-A8, G7, G10), VCS 점검·커밋(C24a/b, H7, H8, H10), 핸드오프 충돌 HALT(E5), 리뷰어 지시 파일 읽기 실패(G13), 퇴화 입력(G23, G25, G35), severity 무시(G57; G16이 이미 금지) | env | 2026-11-09 | 발동 조건이 샌드박스에 없거나 다른 결정이 대신함. C1(의도 = 이슈 본문)은 env로 남음 |
| D-2 | G4, G8 | **의도 불명확 문장 삭제** (2026-11-10, 전날의 "가정하고 진행"을 대체): 의도 불명확(C12)·의도 미확정 HALT(C23)·intent gap(D20)·matrix 모호(F7)·intent_gap 라우트(G84a, G84b, G84c)·intent_gap 판정(G72)을 drop. 대체 문장 없음(`## Assumptions` 절을 더하지 않음, spec-template 원문 유지). step-04 라우트 enum은 `bad_spec\|patch\|defer`가 되고 형식·폭포식·정의 문장(G71, G77, G81, G68, G74)에서 라벨만 지운다; intent-alignment 렌즈는 유지, 그 finding은 bad_spec/patch로 | semantic → drop | 2026-11-10 | 근거: 평가 데이터 SWE-bench Verified는 사람이 "무엇을 고칠지 명확한" 이슈만 남긴 500개라 발동 조건이 사실상 없다. L1C 영향 없음(네 개 모두 의도와 무관). code 157 → 152(T-SR1 L1 5 빠짐), judge 49 → 48. **(실패 HALT 부분은 기본값 → 2026-11-09 사용자 확정)** 실패 HALT 5개(D28 spec 기준 미달, F2 검증 실패, F10 patch 검증 실패, F8 matrix 감사 실패, G83 루프 상한)는 `status: blocked`와 사유를 frontmatter·Auto Run Result에 **기록하되 멈추지 않고** 최종 보고까지 진행 (rules.yaml 1b 노트, speckit 선례). 기록은 T-FM2/T-OR2로 그대로 채점 |
| D-3 | G9 | **저장소 테스트 파일**: D42(I/O Matrix edge case 단위 테스트 task)·F4·F5·G50(patch = 추가할 테스트 지명)을 상류대로 유지, 테스트는 저장소의 기존 테스트 파일에 추가 | semantic | 2026-11-09 | D42 L1C 유지 (ifeval T-PR1 `test_file_write` 금지와 정반대; 14 §6: SWE-Gym 293개에서 gold test patch 98%가 기존 테스트 파일 수정; 평가 데이터 SWE-bench Verified 500개에서는 미측정). 채점 충돌 <1% (SWE-bench 검증기도 gold test patch의 파일을 base commit으로 되돌린 뒤 적용, `rllm/sandbox/git_history.py:9-10`; 비율은 SWE-Gym 측정값). 학습 세 workflow의 checks/ 규칙과는 학습 내부 충돌 없음(평가 전용) |
| D-4 | G8 | **루프·재검증 유지**: bad_spec 루프백(G85c-f, G82, G81, G58 이월 행 대조, G73·G85a judge) 상류대로, 상한 5(G83) 유지, patch 뒤 diff 재생성·Verification 재실행(F11, F9) 유지 | semantic | 2026-11-09 | **(기본값 → 2026-11-09 사용자 확정)** bad_spec의 **코드 되돌리기(G85b)도 유지** (NEW-WD-revert, L2F +1; 11 §2의 '되돌리기'). 150턴 예산에서 루프 1회 이상 돌 확률은 smoke에서 측정 |
| D-5 | G5, G10 | **산출물 밖으로**: `{{.implementation_artifacts}}` → /testbed 밖 디렉터리(선례: speckit_sdd·openspec_ff의 artifact root; 위치는 4단계에서 roots에 고정), 문서 경로는 port 문서 경로로 치환(A2, A4, A5, A14, D6), slug는 인스턴스 id(C27), 언어 토큰 English(B1, B2), `path:line` 표기(B6) | env (batch) | 2026-11-09 | 규칙은 모두 남는다(15 env + 3 env). C28(기존 spec 충돌 시 `-2`) drop |
| D-6 | — | **judge 일단 미사용**: measure `judge` 규칙 49개는 rubric에 넣되 `log_only`/비활성, 층 점수는 code 152개로 | measure | 2026-11-09 | judge 끄면 빠지는 것: L1 6, L1C 1(G26), L2M 16, L2F 25. 나중에 `AIDLC_JUDGE_*` 엔드포인트로 켠다 |
| D-7 | G7, G11 | **서브에이전트 사용**: openhands-sdk 1.42.1의 `task` 도구(openhands-tools 1.42.1 `openhands.tools.task` TaskToolSet; 호출 1회 = 서브에이전트 1개를 끝까지 블로킹 실행, `resume=<Task ID>`로 같은 서브에이전트 재호출, 한 턴의 여러 호출은 턴이 재개되기 전 모두 수행 — SDK 기본 tool_concurrency_limit 1이라 순차)로 구현자 1 + 리뷰 렌즈 4를 상류대로 띄운다. (2026-11-10 정정: 처음 적은 `openhands.tools.delegate` DelegateTool은 1.42.1에 등록된 도구가 아님) 되살리는 규칙: I1, I3, D4, E11, G3, G86a, G86b (code) + E13, E3, E4, E9 (judge); 도구가 강제해 채점 제외: I2, I4, I5, E6, E10, E12, G12. G7 semantic 41 (렌즈 절차·형식·독립성, F12, G16, G56, G65, G79 …)는 상류 그대로 keep. E7(구현자 spec 통독)은 서브 대화 trace에서 잰다 | semantic | 2026-11-09 | 4단계 작업: ① 러너 tool 목록에 TaskToolSet 추가(`WorkflowSpec.runner_env` → `OPENHANDS_SDK_EXTRA_TOOLS=task`; 러너가 내장 서브에이전트 타입을 등록; 다른 workflow는 기존 3개 유지 — 2026-11-10 구현), ② 렌즈·구현자 프롬프트는 상류 customize.toml대로 `task`의 `prompt`로 전달(타입 general-purpose = terminal, file_editor, task_tracker), ③ 채점기 trace 전처리: step을 대화별로 분리(부모 대화 = 단계·순서·산출물 쓰기, 서브 대화 = E7, G19, G34, 렌즈 출력), ④ 서브에이전트 턴 수·컨텍스트 비용은 smoke에서 측정. 학습·베이스 모델 모두 `task` 도구를 본 적이 없으므로 "도구 호출 자체"가 측정에 섞인다 — I1이 그 지표 |
| D-8 | G12 | **spec 파일 소실 HALT 삭제** (2026-11-10 user "빼자"): step-02 READY 게이트의 "If the file is missing: HALT … `planned spec file disappeared before implementation`"(S2:21, D25)와 step-03 PRECONDITION "Verify `{spec_file}` resolves to a non-empty path and the file exists on disk …`missing spec_file before implementation`"(S3:14, C30)를 삭제(build.py semantic edit 2건). 이유: 부모 agent 가 같은 trajectory 에서 직접 쓴 파일을 다시 '있나' 확인하라는 지시는 혼란만 주고, 원문의 방어는 step 파일 간 `{spec_file}` 변수 전달용(이 설정에는 없음). 게이트의 'spec 을 디스크에서 다시 읽고 READY 표준 검증' 문장은 그대로. 층 영향: L2F −2 (NEW-WD-exists-after 는 학습 보상 없는 카탈로그 후보), L1/L1C/L2M 불변. |

## 결정 후 층 분포 (decided_layers.py, 2026-11-10)

비-drop·측정 가능 198 = code 150 + judge 48. 채점 대상은 code 150. (D-8 전: 200 = 152 + 48)

| | L1 | L1C | L2M | L2F | 계 |
|---|---|---|---|---|---|
| code (채점) | 116 | 4 | 7 | 23 | 150 |
| judge (미채점) | 5 | 1 | 16 | 25 | 47 (+1 템플릿 없음) |

결정 전(1b 추정, 15 §7.6) code 149 = L1 115 / L1C 9 / L2M 7 / L2F 18. 바뀐 것: L1C 9 → 4 (D-2로 C12, C23, D20, F7, G84c 삭제), L2F 18 → 25 (D-7로 NEW-AW-subagent 4 → 10, D-4로 NEW-WD-revert +1), L1 115 → 116 (E11 +1), 합계 149 → 152; D-8 (2026-11-10)로 L2F 25 → 23 (C30, D25 삭제), 합계 150.

code L1C 4: D40 빈 절에 `None` 금지(T-FM2) · D42 edge case 단위 테스트 task(T-TR1) · F12 patch 구현자는 편집 파일 테스트만, 전체 검증은 부모(T-PR5) · G16 리뷰어 출력에 severity 없음(T-FM2).

code L2F 23 (템플릿별): NEW-AW-subagent 10 (I1, I3, D4, G3, G4, G6, G8, G11, G86a, G86b) · NEW-FM-internal 6 (D22, G66, G80, H3, H4, H5) · NEW-WD-exists-after 1 (G87e; C30, D25 는 D-8 로 삭제) · NEW-FM-language 2 (B1, B2) · T-FM5 2 (B7, G87a) · NEW-WD-revert 1 (G85b) · T-TR1b 1 (G58).

code L2M 7: B5, B6 (T-FM2 경로 표기) · D1, H15 (T-SR2) · D23 (T-RD2 workflow.md 재독) · F1 (T-TR2 Verification 명령 실행) · H2 (T-RF3 바뀐 파일 목록 = diff).

## 결정 대기 (user 확인 필요 — 이 절만 보면 됨)

(없음. 2026-11-10 G12 는 "빼자"로 결정 → D-8.)

## Open before stage 4

1. ~~D-2·D-4 기본값~~ — 2026-11-09 사용자 "기본값으로 진행"으로 확정.
2. 산출물 디렉터리의 실제 경로(선례 확인 뒤 roots에 고정), spec slug 규칙.
3. ~~DelegateTool 변형을 러너에 넣는 방식과 기본 general-purpose 서브에이전트의 도구 집합.~~ — 2026-11-10 해결: `WorkflowSpec.runner_env` + 러너의 `OPENHANDS_SDK_EXTRA_TOOLS=task`; general-purpose = terminal, file_editor, task_tracker.
4. ~~(4단계에서 발견) G12: spec 파일 소실 HALT 두 곳~~ — 2026-11-10 사용자 "빼자" → D-8 로 삭제.

## Behaviors the port adds
- No intent HALT (D-2, 2026-11-10): the three intent sentences (step-01 unclear intent, step-01 unresolved
  intent, step-02 intent gap), the matrix-ambiguity HALT and the step-04 intent_gap route are deleted, not
  replaced; the spec template stays as upstream wrote it. Not a behaviour the port adds, but the one deletion
  that is not forced by the environment.
- Record-and-continue (D-2 default, confirmed): the five failure HALTs write `status: blocked` + the blocking
  condition into the spec frontmatter and `## Auto Run Result`, then the run still produces its final report;
  the working tree is never reverted for a failure end.
- Sub-agents through the SDK `task` tool (D-7, corrected 2026-11-10): step-03 one `task` call whose prompt is the
  handoff text; step-04 four `task` calls in one assistant turn, one per lens, each prompt = that lens's
  customize.toml instruction (G8 "all before triage" = one turn); patch = `task` with `resume` = the
  implementer's Task ID (G86a). Lens output = the sub-agent's
  final message, which the parent copies verbatim into `## Review Triage Log` input rows (G65/G79) so a
  function can count them.
- Loopback kept as written (D-4): bad_spec → KEEP notes, revert code to `baseline_revision`, amend spec,
  re-read step-03, re-run step-04; `review_loop_iteration` cap 5.
- Repository tests (D-3): the spec's unit-test task adds tests to the repository's existing test files; the
  Verification Gap `patch` disposition names a test to add there.

## Names and paths
- Workflow `bmad_build_auto` (evaluation); upstream bmad-code-org/BMAD-METHOD v6.12.2 @ 10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8, MIT.
- `container_dir` = `/bmad-build-auto` (filesystem root, outside the repo); `entry_doc` = `core-workflow.md`;
  shipped documents: `core-workflow.md`, `stages/step-01-clarify-and-route.md … step-04-review.md`,
  `spec-template.md`, `review-prompts/{edge-case-hunter,verification-gap}.md`,
  `references/{claims-check,deletion-check}.md` (the rendered snapshot `R/` of the survey, built once by build.py).
- Artifact root `IA` = `/tmp/bmad/implementation-artifacts/` (upstream `{{.implementation_artifacts}}`);
  `spec_file` = `IA/spec-<slug>.md` (slug rule as upstream S1:80); `diff_file` = `/tmp/bmad/diff/<slug>.diff`
  (upstream: a temp file, fixed here so the rubric can read it); `output_dirs=("/tmp/bmad",)`.
- Sub-agent ids: `implementer`, `blind-hunter`, `edge-case-hunter`, `verification-gap`, `intent-alignment`
  (the upstream `review_layers` ids); agent type default `general-purpose` (terminal, file_editor,
  task_tracker — openhands-tools preset/subagents/default.md).
- Language tokens → English; `{project-root}` → `/testbed`.

## Answered questions
1. Sub-agents possible in openhands-sdk 1.42.1? Yes: the `task` tool (`openhands.tools.task` TaskToolSet; one
   blocking sub-agent per call, `resume` continues one) + `openhands.sdk.subagent`; the `openhands.tools.delegate`
   package has no registered tool (first answer corrected 2026-11-10). Not wired in rllm's runner until
   2026-11-10 (`OPENHANDS_SDK_EXTRA_TOOLS`) → D-7.
2. Which HALTs survive? None ends the run early. Every HALT becomes a recorded terminal status plus the
   final report; the only early end is the normal `done`.
3. Judge? Off for now (D-6): judge rules are kept in rubric.yaml as `log_only`.
4. Do the intent HALTs matter for the eval data? No: SWE-bench Verified keeps only issues human-rated as
   well specified, so the sentences would fire on the agent's hesitation, not on real gaps → deleted (D-2).
