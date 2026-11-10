# Smoke: bmad_build_auto

## Probe 0 (2026-11-10, apptainer, gateway 없음) — `task` 도구 사용 확인

정식 smoke(`rllm eval`, docker, gateway trace)에 앞서 이 호스트에서 돌린 사전 확인. 설정: SWE-bench Verified 이미지 `swebench/sweb.eval.x86_64.psf_1776_requests-1142`를 apptainer SIF 로, 호스트 venv 의 openhands-sdk 1.42.1 + `task` 도구, 문서는 `/bmad-build-auto` 에 바인드(치환 없음), 모델 `wf-tcx-step27`(학습 ckpt, think 켬), 부모 턴 상한 60. 드라이버 `scratchpad/probe/run_in_container.sh`. **표본 1건**.

| 항목 | 값 |
|---|---|
| 소요 | 738 s, 부모 도구 호출 60 (terminal 37, file_editor 16, task 6, think 1) |
| `task` 호출 | 6: 구현자 1, blind 1, edge-case 2(첫 호출의 서브에이전트가 지시 파일 경로를 `/tmp/bmad/…`로 잘못 찾아 실패 보고 → 부모가 재호출), verification-gap 1, intent-alignment 1 |
| 렌즈 4개를 한 턴에 | **아니오**: 턴 48·49·52·53·54 에 하나씩(I3 위반). 구현자는 턴 32 |
| `resume` 사용 | 0 (patch 라우트 없음) |
| spec | `/tmp/bmad/implementation-artifacts/spec-requests-get-content-length.md` 생성 1회 + str_replace 15회 |
| diff | `git diff HEAD > /tmp/bmad/diff/….diff` 뒤 `git diff <baseline> > …`로 재작성; 미추적 파일 미포함(E14a 의 "untracked included" 위반 가능성) |
| 작업 트리 | requests/api.py, models.py, sessions.py, test_requests.py 수정(+73 −16), `build/` 디렉터리 생김(테스트 실행 부산물) |
| 금지 | `git add`·commit 없음 |

판정 후보(표본 1 → 2건 이상 확인 뒤 gap 행으로): (1) 렌즈 순차 실행 — 문서는 "four `task` calls in one assistant turn" 으로 명시(S4:25), 모델이 한 턴에 도구 호출을 하나만 냄 → **agent 잘못(학습 대상)**. 병렬 tool-call 지원은 확인됨(2026-11-10): (a) 같은 probe 의 응답 `chatcmpl-b63…` 이 한 응답에 도구 호출 2개(file_editor view + terminal cat)를 냈고 SDK 가 둘 다 ActionEvent 로 실행 → vLLM 파서·SDK 경로 모두 복수 호출 통과; (b) 엔드포인트에 직접 보낸 2도시 날씨 테스트(temperature 0, tool 1개)에서 `tool_calls` 2개 반환(finish_reason tool_calls). SDK 의 `tool_concurrency_limit` 기본 1 은 실행만 순차로 할 뿐 한 턴 4회 호출 자체는 trace 에 남으므로 I3 판정에는 영향 없음; (2) edge-case 서브에이전트의 경로 오해 — 프롬프트는 `/bmad-build-auto/review-prompts/edge-case-hunter.md` 를 정확히 줬고 서브에이전트가 `/tmp/bmad` 아래를 뒤짐 → agent 잘못; (3) `git diff` 에 미추적 파일 누락 — 문서 문장은 명확(S3:41) → agent 잘못 후보.

제약: 이 probe 는 SDK 대화 기록만 남기고(서브에이전트 대화는 SDK 가 종료 시 삭제) gateway trace 가 없어 채점기에 넣을 수 없다. `/tmp/bmad` 는 컨테이너 종료와 함께 사라져 spec·diff 본문을 못 읽었다(다음 실행부터 호스트 디렉터리에 바인드하도록 스크립트 수정).
