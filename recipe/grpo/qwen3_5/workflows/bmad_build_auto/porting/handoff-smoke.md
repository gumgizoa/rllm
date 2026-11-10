# 인계: bmad_build_auto 정식 smoke (6단계) 를 다른 서버에서 이어서 하기

작성 2026-11-10, 작성자 Claude(조정자, cns-bmai-02 세션). 읽는 사람: SWE-bench Verified 이미지가 있는 다른 서버에서 이 작업을
이어받는 Claude Code 세션과 사용자. 이전 세션의 대화·메모리는 그 서버에 없으므로, 이 문서와 `porting/` 의 다른 파일만으로
이어갈 수 있게 적는다. 사실마다 출처(파일·커밋·측정일)를 붙였고, 확인 안 된 것은 **미확인**으로 표시했다.

## 1. 지금 상태 (무엇이 끝났고 무엇이 남았나)

- 브랜치 **`feat/bmad-build-auto-eval`** (origin: `https://github.com/gumgizoa/rllm.git`). 팀 브랜치 `feat/aidlc-openhands-sdk-recipe`
  (6129d22b) 에서 분기했고, 그 위에 6+1 커밋: SDLC IF 평가 기반 4개(cherry-pick), BMAD 포트 + `task` 도구 연결 + 채점기 v1,
  probe 1 기록, 채점기 v2(c7af864a). 팀 브랜치로 **무충돌 머지 가능**(evaluation.py 는 `inputs`/`post` 와 `layers_path` 를
  모두 받도록 합쳐 둠). 이 문서를 쓰는 시점에 **push 는 하지 않았다** — 다른 서버에서 받으려면 먼저 push 해야 한다.
- port-workflow 7단계 중 1~5 완료(`01-survey.md`, `01b-rules.md`, `02-gaps.md`, `03-plan.md`, `03-decisions.md`, `05-changes.md`),
  6단계(smoke) 는 사전 probe 2건만(`06-smoke.md` Probe 0·1), 7단계(패키지 README) 미작성.
- 채점기: `reward/rubric.yaml` 217 항목 중 **108 구현**(L1 88 / L1C 3 / L2M 5 / L2F 12), judge 48 은 `log_only`(사용자 결정으로 보류).
  합성 정직 run 2개 compliance 1.0, 꼼수 40종 전부 검출, 항목마다 깨는 케이스 있음(`tests/test_bmad_build_auto_hacks.py`,
  `tests/test_bmad_build_auto_reward.py`). 자세한 것은 `05-changes.md` 4b·4c.
- **남은 것**: (a) 정식 smoke — `rllm eval` 로 Verified 2~3 task 를 돌려 gateway trace 와 채점 신호를 보는 것, (b) 그 trace 로
  실데이터 스냅샷·재료 검수(aidlc_v4_eval 의 `snapshot/` + `scripts/aidlc_v4_eval_snapshot.py` 방식), (c) F12·G27 (서브 대화
  미구현 2개), (d) 7단계 README, (e) 보류: judge, 팀 쪽 `kind_matrix` 집계용 `category` 부여.

## 2. 평가가 요구하는 것 (체크리스트)

| 필요 | 확인 방법 | 비고 |
|---|---|---|
| docker 데몬 접근(docker 그룹) + dood 컨테이너 | `docker ps` 가 됨; 컨테이너는 `recipe/eval/README.md` 0.1 (소켓·`--network host`·공유 경로 마운트) | GPU 불필요(모델은 외부 엔드포인트) |
| repo 체크아웃 + venv | `cd <repo> && .venv/bin/python -c "import rllm"`; 없으면 `uv venv --python 3.12 && uv pip install -e .` (+ `pytest`). 0.2 절 참고 | 이 세션의 venv 는 `/vast-ib/MMI/home/kyuminkim/project/if/rllm/.venv` (같은 파일시스템이 마운트돼 있으면 그대로 사용) |
| `RLLM_HOME` (공유 경로) | `export RLLM_HOME=<host 와 컨테이너에서 같은 경로>`; 0.3 절 | 이 세션 것은 `/data/MMI/kyuminkim/rllm-work/rllm-home` (swegym293·swegym_val23 만 있음) |
| 데이터셋 `swebench_verified_all` | `ls $RLLM_HOME/datasets/swebench_verified_all` | 없으면 `python recipe/eval/swebench-verified/prepare_swebench_verified_subset.py --ids recipe/eval/swebench-verified/all-ids.txt --name swebench_verified_all` (Harbor 레지스트리에서 500개 받아 499개 등록; `~/.cache/harbor/tasks` 에 task 디렉터리) |
| Verified 이미지 | `docker images --format '{{.Repository}}' \| grep -c '^swebench/sweb.eval'` | 공식 이름 `swebench/sweb.eval.x86_64.<owner>_1776_<repo>-<n>:latest`, 약 4 GB/장. `xingyaoww/…_s_…` 는 SWE-Gym 이미지라 **전혀 다른 것**(저장소도 안 겹침). 없으면 첫 실행 때 task 마다 자동 pull |
| agent 이미지 | `--agent-image auto` 가 만듦(`rllm-agent-<hash>`, 약 850 MB) | openhands-sdk 1.42.1 이 들어감 |
| 모델 엔드포인트 | `curl http://27.122.129.139:8001/v1/models` (학습 모델 `wf-tcx-step27`), `…:8007/v1/models` (base `Qwen3.5-9B`) | 두 모델 모두 병렬 tool call 을 냄(2026-11-10 직접 확인). 그 서버에서 이 IP 가 열려 있는지는 **미확인** |

## 3. smoke 실행

repo 루트에서(그래야 `recipe.grpo.qwen3_5` 가 import 됨), 컨테이너 안에서:

```bash
export RLLM_HOME=/path/shared/rllm-home          # host 와 같은 경로
cd <repo>; source .venv/bin/activate

# 1) 학습 모델, task 2~3개: 작은 데이터셋을 따로 만드는 편이 깔끔하다(ids 파일에 instance id 한 줄씩).
#    python recipe/eval/swebench-verified/prepare_swebench_verified_subset.py --ids /tmp/ids3.txt --name swebench_verified_smoke3
#    (대안: 전체 데이터셋에 --max-examples 3 또는 --task-indices 0,1,2 — 어느 task 가 뽑히는지는 parquet 순서에 달림)
rllm eval swebench_verified_smoke3 --split test \
  --agent recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow \
  --agent-kwargs workflow=bmad_build_auto,step_limit=100,enable_thinking=true,instruction_position=prefix \
  --agent-image auto --sandbox-backend docker --hide-git-history \
  --concurrency 3 --sandbox-concurrency 3 --no-ui \
  --base-url http://27.122.129.139:8001/v1 --model wf-tcx-step27 \
  --sampling-params @recipe/eval/config/qwen3_5.yaml --episodes-dir $RLLM_HOME/episodes/bmad_smoke_step27

# 2) base 모델: --base-url http://27.122.129.139:8007/v1 --model Qwen3.5-9B 로 같은 명령
# 3) 비교군: workflow=none (같은 하네스, 워크플로우 없이)
```

- dood 컨테이너 생성 명령의 예는 `recipe/grpo/qwen3_5/scripts/run_container.sh`(이 세션의 `rllm-train`; 경로만 그 서버에 맞게).
- 추천 task: `psf__requests-1142`(probe 0·1 과 같은 것), `psf__requests-1724`, `pallets__flask-5014`, `mwaskom__seaborn-3069`
  (작은 저장소, 이미지 작음). 이 넷의 issue 텍스트는 probe 때 HF `princeton-nlp/SWE-bench_Verified` 에서 받았다.
- `step_limit=100` 은 **부모 턴 상한**이고, SDK 1.42.1 의 서브에이전트는 이 값을 그대로 **상속**한다(`task/manager.py`; probe 1 에서
  base 의 구현자가 60 턴을 다 써 `Agent reached maximum iterations limit (60)` 으로 돌아옴). 엔진의 MAX_TURNS 스탬프는 부모+서브
  trace 전체를 세지만 강제하지 않는다(`workflow_harness.py` 모듈 docstring).
- 워크플로우 문서·지시·system prompt 는 `WorkflowSpec`(`bmad_build_auto/__init__.py`)이 올린다: 문서 `/bmad-build-auto/`, 산출물
  `/tmp/bmad/{implementation-artifacts,diff}`, 러너 env `OPENHANDS_SDK_EXTRA_TOOLS=task`(러너가 `TaskToolSet` + 내장 agent 등록).
- 결과: `$RLLM_HOME/eval_results/<dataset>_<model>_<timestamp>/{results.json,episodes/}`. 콘솔 `Errors` 는 인프라 실패(0점과 다름).

## 4. 결과에서 볼 것 (06-smoke.md 에 적을 것)

1. **`task` 사용**: `python -I recipe/grpo/qwen3_5/workflows/if/scripts/bmad/subagent_usage.py <episodes_dir> --per-episode`
   — 부모/서브 step 수, task 호출(new/resume), 오류 관찰 수, 한 번도 안 부른 episode 비율. probe 결과(표본 1씩): 학습 모델 6회
   (구현자 + 렌즈 4 + 재호출 1, **턴마다 하나씩**), base 1회(구현자만, 상한 초과) + 리뷰 렌즈 0.
2. **채점 신호**: `results.json` 의 `signal_averages` 에 `bmad/compliance`, `bmad/layer/*`(L1·L1C·L2M·L2F), 항목별 `bmad/…`.
   서브에이전트 항목(`…bmad_subagent.*` 10개)은 gateway trace 에 서브 대화가 있을 때 처음 실제 값이 나온다(probe 는 SDK 가 서브
   대화를 지워서 못 봄). **부모가 렌즈를 띄웠는데 서브 대화가 trace 에 없으면 fail 이 나오도록 돼 있으니**, 그런 fail 이 보이면
   trace 캡처(`Step.metadata["request_tools"]`) 를 먼저 의심할 것.
3. **재채점**: `python recipe/grpo/qwen3_5/scripts/rescore_compliance.py <episodes_dir> --workflow bmad_build_auto --compare`
   (저장된 episode + artifacts 만으로 같은 점수가 나오는지; `--compare` 가 라이브 신호와 대조).
4. **판정 후보 → gap 행**: probe 에서 본 것(렌즈 순차 실행 = I3 위반, `git diff` 에 미추적 파일 누락 = E14a, edge 서브에이전트의
   지시 파일 경로 오해, base 의 spec 형식 위반·`baseline: NO_VCS` 오기·`finish` 로 종료) 이 2건 이상 재현되면 `02-gaps.md` 에
   agent 잘못/문서 잘못/환경 잘못으로 나눠 행을 추가한다.
5. **실데이터 스냅샷**(다음 단계): aidlc_v4_eval 의 `snapshot/audited.json` + `scripts/aidlc_v4_eval_snapshot.py check/make` 를
   본떠 `bmad_build_auto/snapshot/` 를 만들고, 사람이 trajectory 와 대조해 확인한 셀을 적는다.

## 5. 결정·규칙 (바꾸지 말 것 / 바꿀 때 절차)

- 결정 D-1~D-8 은 `03-decisions.md`(사용자 승인 2026-11-10). 특히 D-2 의도 불명확 HALT 문장 **삭제**(대체 없음), D-8 spec 소실
  HALT 두 문장 삭제(G12 closed), 실패 HALT 5개는 `status: blocked` 기록 후 계속, 마지막 commit 없음, 서브에이전트는 SDK `task`
  도구. 사용자 결정이 더 필요한 항목은 `03-decisions.md` 맨 위 "결정 대기" 절 **한 곳**에만 적는다(사용자 요청).
- upstream 문서 변경은 **항상 `build.py` 의 태그 편집**(`Edit(source, old, new, tag, note)`) 으로 하고 `docs/` 를 손으로 고치지
  않는다. 재생성: `python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.build --upstream <BMAD-METHOD 체크아웃>`; 드리프트
  검사 `--check`. 체크아웃은 `https://github.com/bmad-code-org/BMAD-METHOD.git` @ `10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8`
  (v6.12.2) — 이 세션에서는 `/vast-ib/MMI/home/kyuminkim/project/if/workflows/BMAD-METHOD`; 다른 서버에 없으면 그 커밋을 clone.
- 채점기 변경은 `reward/build.py` 의 `ITEMS`/`UNIMPLEMENTED_NOTE` 와 `reward/checks.py` 에서 하고
  `python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward.build` 로 `rubric.yaml`·`constraints.yaml`·`layers.yaml` 을
  재생성한다(`--check` 로 드리프트). 층(L1/L1C/L2M/L2F) 은 `workflows/if/scripts/bmad/decided_layers.py` 가 정한다.
- 검증 명령(전부 통과해야 함): `.venv/bin/python -m pytest -q recipe/grpo/qwen3_5/tests tests/harnesses` (2026-11-10: 940 passed),
  두 `--check`, `python -c "from recipe.grpo.qwen3_5.sdlc_if import constraints; print(constraints.check('bmad_build_auto'))"` → `[]`.
- 보고 문체: 한국어, 표에서는 말로 설명하고 id 는 괄호, 미확인 사실은 **미확인** 표기, 숫자는 표나 한 줄로.
- 조직 규칙: 응답에 고객(LG CNS 외 회사명이 붙은) 자료·데이터를 넣지 않는다. 이 작업에는 고객 데이터가 없다.

## 6. 이 세션에서 확인한 사실 (다시 재지 않아도 되는 것)

- openhands-sdk/tools 1.42.1: LLM 이 보는 서브에이전트 도구는 **`task`** (`openhands.tools.task.TaskToolSet`; 인자 prompt,
  subagent_type 기본 general-purpose, description, resume). `openhands.tools.delegate` 에는 등록된 도구가 없다. 한 호출 = 블로킹
  서브에이전트 1개(새 LocalConversation, 부모 LLM 복사, 같은 workspace). 한 턴에 여러 호출이면 병렬 executor 를 타지만
  `Agent.tool_concurrency_limit` 기본 1 이라 **실행은 순차**(trace 에는 한 턴 복수 호출로 남으므로 I3 채점엔 영향 없음). 내장
  agent 유형(general-purpose·code-explorer·bash-runner) 은 `register_builtins_agents(enable_browser=False)` 로 앱이 등록해야 하며
  러너가 한다. 서브 대화의 첫 사용자 메시지는 프롬프트 그대로(`send_message(prompt, sender=…)`) → 렌즈 식별은 프롬프트 서명.
- vLLM 두 엔드포인트 모두 한 응답에 `tool_calls` 2개를 돌려준다(2도시 날씨 테스트, base 3/3). 렌즈를 턴마다 하나씩 띄운 것은
  모델 선택이다.
- SWE-bench Verified 채점: base commit 의 테스트 파일을 checkout 한 뒤 gold test patch 적용(`rllm/sandbox/git_history.py:9-10`).
  "gold test patch 의 98% 가 기존 테스트 파일 수정" 통계는 SWE-Gym 측정치이고 Verified 는 **미측정**.
- cns-bmai-02(로그인 노드) 에는 docker 가 없고 apptainer 1.5.3 만 있다. probe 는 거기서 SIF 로 돌렸고 산출물은 그 세션의 scratchpad
  에만 있다(repo 밖; 06-smoke.md 의 표가 요약). H200-9 는 ssh·docker 그룹 OK, Verified 이미지 0, SWE-Gym 이미지 339, 디스크 632 GB;
  H200-10 은 docker 그룹 없음; H200-7/8 은 접근 불가(2026-11-10).

## 7. 이어받는 Claude 에게 (첫 10분)

1. `git fetch && git checkout feat/bmad-build-auto-eval`, 위 §5 검증 명령 네 개를 돌려 환경이 같은지 본다(BMAD 체크아웃이 없으면
   docs `--check` 만 건너뛰고 그 사실을 적는다).
2. §2 표를 위에서부터 채운다. 모르는 칸은 **미확인**으로 두고 사용자에게 한 번에 묻는다.
3. §3 의 smoke 를 학습 모델 → base → `workflow=none` 순으로 돌리고, §4 를 `06-smoke.md` 에 "Smoke 1" 절로 적는다(표본 수 명시).
4. 끝나면 `05-changes.md` 에 바뀐 점, `02-gaps.md` 에 새 gap 행, 필요하면 `03-decisions.md` "결정 대기" 에 질문을 적고 커밋한다.
