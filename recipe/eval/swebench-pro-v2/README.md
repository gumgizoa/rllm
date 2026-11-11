# SWE-bench Pro V2 평가 (`swebenchpro_v2_full`)

- Scale AI의 SWE-bench Pro V2(공개 642개) 평가 가이드.
- Harbor를 사용하지 않고, rllm native 방식을 통해 네트워크/Git 차단, Timeout, agent kwargs 등 세부 설정을 활용하여 편향 없는 평가를 수행한다.
- 스크립트는 `prepare_swebenchpro_v2.py` 하나다. 기본은 642개 전체이고, `--ids`로 subset을 만든다.
- 환경 설정: Docker Container 빌드, rLLM 패키지 설치 등 [`README.md`](../README.md) 0장 참고.

## SWE-bench Pro V2

- Scale이 2026-09-22에 공개한 검수판이다. v1 공개 731개 중 89개를 제외해 642개가 남았다. 저장소와 base commit은 v1과 같다.
- 문제 설명 529개를 다시 썼다. 채점되는 assertion마다 근거가 되는 문장이 설명에 있도록 했다.
- verifier를 642개 모두 보강했다. 숨은 테스트 경로를 복원하고, 에이전트가 고친 fixture와 snapshot을 되돌리고, 남은 bytecode를 지운다. test patch 214개와 gold patch 38개를 고쳤다.
- 이미지는 `ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`로 다시 빌드됐고 익명으로 받을 수 있다. git 기록은 정리돼 있다(정답 커밋, 남는 ref, stash, hook 없음).
- 배포처:
  - Harbor 태스크 형식: GitHub `scaleapi/SWE-bench_Pro-os`의 `v2/tasks` (tag `v2.0.0`)
  - HF: `ScaleAI/SWE-bench_Pro`의 `default` config(`v1` config가 원래 731개)
- **Harbor Registry에는 없다.** registry의 `swebenchpro`는 v1이다(`../swebench-pro`). 그래서 이 레시피는 GitHub의 태스크 디렉토리를 직접 받는다.
- 11개 저장소, 언어는 Go·Python·JavaScript·TypeScript다. 642개 중 77개(Go·JavaScript 5개 저장소)는 Alpine(musl) 이미지다.

## 1. 데이터셋 준비

```bash
# Host와 같은 경로로 마운트된 볼륨 (../README.md 0.3)
export RLLM_HOME=/raid/rllm-work/rllm-home

# 642개 전체: sparse clone(v2.0.0 고정) -> v2/SHA256SUMS 확인 -> 사본 -> base 이미지 libc 판별 -> registry 등록
python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py --agent-timeout 3600 --verifier-timeout 1000
```

- 사본은 `$RLLM_HOME/datasets/swebenchpro_v2_full/<instance_id>/`에 생기고 `swebenchpro_v2_full`(split `test`)로 등록된다. 원본을 고친 내용은 Appendix에 있다.
- base 이미지가 Alpine(musl)인지 보려고 642개 이미지를 모두 받아 한 번씩 실행한다(네트워크 없이). 처음에는 오래 걸리고 디스크를 많이 쓴다(Appendix). `--jobs`(기본 16)가 동시에 확인하는 이미지 수이고, 받기가 실패하면 4번까지 다시 시도한다. musl 태스크 목록은 `musl_tasks.txt`에 남는다.
- 이미 있는 태스크 폴더는 다시 복사하지 않고, `task.toml`과 Dockerfile 수정만 다시 적용한다. 원본을 다시 복사하려면 `--force`.
- `--agent-timeout`, `--verifier-timeout`을 빼면 V2 원래 값(둘 다 3000초)이 남는다. 쓴 값은 registry의 source 문자열(`agent_timeout=... verifier_timeout=...`)에도 남는다.

### 1.1 subset

같은 스크립트에 `--ids`(한 줄에 instance id 하나, `#` 주석 가능)와 `--name`을 준다. 처리는 전체와 같다.

```bash
# 100개 subset (subset-ids.txt)
python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2.py --agent-timeout 3600 --verifier-timeout 1000 \
    --ids recipe/eval/swebench-pro-v2/subset-ids.txt --name swebenchpro_v2_100
```

- `subset-ids.txt`(100개)는 v1 subset(`../swebench-pro/subset-ids.txt`)과 최대한 같은 instance를 쓴다.
  - v1 subset 100개 중 V2에 남은 **85개는 그대로 둔다.** 나머지 15개는 V2 검수에서 제외됐다.
  - 빠진 15개는 V2의 나머지 태스크에서 보충한다. 추출률(뽑힌 수 / V2 태스크 수)이 가장 낮은 저장소에 하나씩 채우는 방식이고, 저장소 안에서는 seed 0으로 무작위로 뽑는다. 그래서 11개 저장소를 모두 포함하고 추출률이 14.7~16.4%로 고르다(tutanota만 4개 중 1개).
  - 언어: go 39, python 37, js 23, ts 1. musl 이미지는 10개다.
  - 유지한 85개도 instance id만 같고 내용은 V2판이다. 문제 설명, test patch, F2P 목록 등이 바뀌었으므로 v1 점수와 직접 비교하지 않는다.
- 이 스크립트로 만든 subset의 태스크는 같은 id의 full set 사본과 파일이 모두 같다(100개 확인).
- 학습 validation에 쓰는 `swebenchpro_v2_strat50`도 같은 방식(`--ids <50개 목록> --name swebenchpro_v2_strat50`)으로 만든다.

| 저장소 | V2 전체 | subset |
| --- | --- | --- |
| ansible/ansible | 82 | 13 |
| internetarchive/openlibrary | 82 | 13 |
| flipt-io/flipt | 78 | 12 |
| qutebrowser/qutebrowser | 73 | 11 |
| gravitational/teleport | 68 | 10 |
| future-architect/vuls | 58 | 9 |
| protonmail/webclients | 55 | 9 |
| element-hq/element-web | 52 | 8 |
| navidrome/navidrome | 52 | 8 |
| NodeBB/NodeBB | 38 | 6 |
| tutao/tutanota | 4 | 1 |

## 2. Oracle test (권장)

정답 패치를 적용해 verifier가 1.0을 주는지 확인한다. 모델 평가와 같은 sandbox 조건(git 기록 숨김, agent 단계 네트워크 차단, timeout)으로 돌린다. LLM을 호출하지 않지만 CLI가 provider 설정을 요구하므로 죽은 포트를 준다.

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
export RLLM_ROLLOUT_TIMEOUT_S=4800

rllm eval swebenchpro_v2_full \
    --split test \
    --agent oracle \
    --concurrency 48 \
    --sandbox-concurrency 48 \
    --hide-git-history \
    --no-agent-network \
    --verify-network \
    --sandbox-backend docker \
    --no-ui \
    --base-url http://127.0.0.1:1/v1 \
    --model oracle-dummy
```

- **642/642**가 나와야 한다(측정: 642/642, Errors 0. agent 3600 / verifier 1000초 사본, 동시 48, 약 25분. task 이미지가 이미 빌드된 상태이고, 처음이면 빌드 시간이 더 든다).
- verifier 시간은 중앙값 30초, p95 142초, 최대 717초(protonmail/webclients 1개)로 모두 verifier 상한 1000초 안에 든다.
- 0점이나 Errors가 있으면 모델을 돌리기 전에 원인을 해결한다(자원, 이미지, 디스크). 0점이 한두 개면 그 태스크만 다시 돌려 본다. 부하가 몰릴 때만 실패하는 경우가 있다(subset에서 element-web 1개).
- oracle 실행이 태스크 이미지(`rllm-task-<instance_id>`)를 미리 빌드해 두므로, 모델 평가의 첫 rollout이 빨라진다.

## 3. 모델 평가

### 3.1 vLLM

```bash
export HF_HOME=/path/to/hf-cache
# Qwen3.5-9B 계열을 GPU 8장에 data parallel로. 학습과 같은 256K context
vllm serve <model-or-checkpoint-dir> --port 8000 --served-model-name <served-model-name> \
    --data-parallel-size 8 --max-model-len 262144 --gpu-memory-utilization 0.90 \
    --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml \
    --enable-prefix-caching
```

- tool calling은 필수다: `--enable-auto-tool-choice --tool-call-parser qwen3_xml`(Qwen3/3.5). reasoning은 `--reasoning-parser qwen3`.
- Qwen3.5는 hybrid 구조라 vLLM이 prefix caching을 기본으로 끈다. agent 평가는 턴마다 같은 앞부분을 다시 보내므로 `--enable-prefix-caching`으로 켜면 태스크 시간이 크게 준다. 다만 출력이 float 오차 수준에서 달라지므로 비교할 실행끼리는 같은 설정을 쓴다.
- 학습 checkpoint(verl FSDP)는 HF 형식으로 변환한 디렉터리를 그대로 준다.

### 3.2 평가 실행

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home HF_HOME=/path/to/hf-cache
# rollout(agent + verifier) 전체 예산. task.toml의 verifier 몫을 먼저 떼고 남은 시간이 agent 상한이 된다
export RLLM_ROLLOUT_TIMEOUT_S=4800
# task.toml에 timeout이 없는 태스크에만 쓰인다(V2 사본에는 항상 있다). 학습과 같은 값으로 둔다
export RLLM_HARNESS_RUN_TIMEOUT_S=3600 RLLM_VERIFIER_TIMEOUT_S=1000

rllm eval swebenchpro_v2_full \
    --split test \
    --agent openhands-sdk \
    --agent-image auto \
    --agent-kwargs @recipe/eval/config/openhands-sdk.yaml \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --attempts 2 \
    --concurrency 48 \
    --sandbox-concurrency 48 \
    --hide-git-history \
    --no-agent-network \
    --verify-network \
    --sandbox-backend docker \
    --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model <served-model-name>
```

실행이 시작되면 콘솔 상단 표에 적용된 조건(git 기록, 네트워크, sampling)이 찍힌다. 의도와 다르면 바로 멈춘다.

### 3.3 설정별 설명

| 설정 | 값 | 효과 |
| --- | --- | --- |
| agent image mount | `--agent-image auto` | openhands-sdk(파이썬 venv)를 한 번 이미지로 구워 모든 sandbox의 `/opt/rllm/agent`에 읽기 전용으로 mount한다. 태스크마다 설치하지 않으므로 agent 단계 네트워크를 끌 수 있다. |
| agent 단계 네트워크 | `--no-agent-network` | agent는 LLM gateway 말고는 나갈 곳이 없다(공식 V2 protocol과 같음). 저장소의 upstream(다음 release, `git clone`)에서 정답을 받아 오는 것을 막는다. |
| verifier 단계 네트워크 | `--verify-network` | agent가 끝난 뒤 verifier에게만 네트워크를 연다. 일부 Go 태스크는 테스트할 때 모듈을 받는다. |
| git 기록 | `--hide-git-history` | agent가 실행되는 동안 `/app/.git`을 숨기고 verifier 전에 되돌린다. V2 이미지는 git 기록이 이미 정리돼 있지만 학습과 같은 조건으로 둔다. `task.toml`의 `workdir = "/app"`이 필요하다(1장에서 넣는다). |
| timeout | `task.toml` agent 3600 / verifier 1000 + `RLLM_ROLLOUT_TIMEOUT_S=4800` | 학습과 같은 상한이다. agent는 `min(3600, 4800 - 1000) = 3600`초, verifier는 1000초를 받는다. 아래 참고. |
| agent kwargs | `@recipe/eval/config/openhands-sdk.yaml` | `max_iterations: 250`(agent step 상한), `include_default_tools: [FinishTool]`(ThinkTool 제외: reasoning 모델은 이미 턴마다 생각한다), `strict_tool_calls: false`. |
| sampling | `@recipe/eval/config/qwen3_5.yaml` | temperature 1.0, top_p 0.95, top_k 20, max_tokens 16384. gateway가 강제한다. 다른 값을 쓰려면 이 파일을 고치지 말고 새 yaml을 만들어 지정한다. |
| 반복 | `--attempts 2` | 태스크마다 독립 rollout 2개. pass@1(평균)과 pass@2가 나온다. 같은 태스크의 rollout은 태스크 이미지를 함께 쓴다. |
| 동시 실행 | `--concurrency 48 --sandbox-concurrency 48` | sandbox 48개면 CPU 192, 메모리 768 GB가 필요하다(태스크당 CPU 4, 16 GB). |

**timeout은 환경변수만으로 바꿀 수 없다.** `rllm eval`은 agent·verifier 상한을 `task.toml` → 환경변수 순서로 정한다(`rllm/timeouts.py`, `../README.md` 2.4). V2 원본 `task.toml`에는 둘 다 3000초가 있어서 `RLLM_HARNESS_RUN_TIMEOUT_S`, `RLLM_VERIFIER_TIMEOUT_S`가 쓰이지 않는다. 다른 상한은 1장에서 `--agent-timeout`, `--verifier-timeout`으로 사본에 쓴다.
- 이렇게 하지 않고 `RLLM_ROLLOUT_TIMEOUT_S=4800`만 주면, verifier 3000초를 먼저 떼고 agent는 `min(3000, 4800 - 3000) = 1800`초만 받는다.
- agent가 상한을 넘기면(`AGENT_TIMEOUT`) 그 시점의 상태를 verifier가 남겨 둔 시간 안에 채점한다. verifier가 상한을 넘기면 `VERIFIER_TIMEOUT`(인프라 실패)이다.

**agent kwargs의 `strict_tool_calls`.** 학습(`recipe/grpo/qwen3_5`)은 `true`로 돌린다. 모델이 잘못 쓴 tool call(`str_replace` 등)을 SDK가 고쳐 주지 않고 에러로 돌려준다. 평가 yaml의 `false`는 SDK 기본값이고, 이전 결과들이 이 값으로 측정됐다. 학습 중 validation과 같은 조건이 필요하면 `strict_tool_calls: true`인 yaml을 따로 만들어 쓴다.

**thinking 모델은 과거 reasoning 재전송이 필요하다.** openhands-sdk는 kimi·deepseek·minimax에만 이전 턴의 reasoning을 다시 보낸다. 그러면 Qwen3.5의 이전 턴이 빈 `<think></think>`로 렌더링되고, 모델이 닫히지 않은 think 안에 tool call을 써서 호출이 파싱되지 않는다. native harness는 `rllm/harnesses/tools/openhands_sdk_runner.py`가 이를 보완한다. `reasoning_content`와 `reasoning` 두 필드에 모두 담아 보낸다(vLLM 0.22 미만은 `reasoning`만 읽는다).

**agent venv에 소스가 없다.** agent 이미지의 site-packages는 `.py` 없이 `.pyc`만 담는다(`rllm/sandbox/strip_py_sources.py`). openhands-sdk가 의존하는 패키지(fastmcp, starlette 등)와 같은 저장소를 다루는 태스크에서 agent가 `grep`으로 정답을 찾지 못하게 하기 위해서다.

## 4. 결과

- `$RLLM_HOME/eval_results/swebenchpro_v2_full_<model>_<timestamp>/`에 `meta.json`, `results.json`, `episodes/`가 생긴다. 콘솔에는 Accuracy, Errors, pass@k가 찍힌다.
- 콘솔의 `Errors`는 인프라 실패(이미지 빌드 실패, verifier timeout 등)이고 0점과 다르다. 0이 아니면 원인부터 확인한다.
- LLM 호출이 0번인 에피소드(`No traces found`)는 Errors가 아닌 0점으로 집계된다. 에피소드의 step 수가 0이면 인프라 실패로 보고 다시 돌린다.
- 같은 태스크의 rollout 2개는 `<instance_id>:0`, `<instance_id>:1`로 구분된다.

**참고 결과.**

Qwen3.5-9B GRPO checkpoint(`recipe/grpo/qwen3_5`, `swe_mix_go_train` step 24, HF 변환본), 3.2 명령 그대로(`--attempts 2`, 동시 48), vLLM 0.22.1(data parallel 8, H200 8장, `--enable-prefix-caching`), openhands-sdk 1.42.1:

| pass@1 | pass@2 | Errors | 소요 시간 |
| --- | --- | --- | --- |
| 56.3% (723 / 1284) | 68.7% (441 / 642) | 1 | 약 6시간 |

| 저장소 | pass@1 |
| --- | --- |
| qutebrowser/qutebrowser | 93 / 146 (0.64) |
| protonmail/webclients | 68 / 110 (0.62) |
| internetarchive/openlibrary | 100 / 164 (0.61) |
| ansible/ansible | 96 / 164 (0.59) |
| flipt-io/flipt | 86 / 156 (0.55) |
| NodeBB/NodeBB | 41 / 76 (0.54) |
| navidrome/navidrome | 56 / 104 (0.54) |
| future-architect/vuls | 60 / 116 (0.52) |
| gravitational/teleport | 68 / 136 (0.50) |
| element-hq/element-web | 52 / 104 (0.50) |
| tutao/tutanota | 3 / 8 (0.38) |

- 종료 사유: 정상 1256, prompt 길이 초과 14, step 상한(250) 9, verifier timeout 2, error 2, agent timeout 1.
- Errors 1건은 `--hide-git-history`의 stand-in 저장소 확인 실패다(`stand-in repository in /app is not a single commit`, 출력 없음). 같은 task의 다른 rollout과, 같은 이미지에서 같은 명령을 다시 실행한 것은 정상이었다. 평가 초반 이미지 빌드가 몰린 시점의 일시 실패로 보고 해당 task만 다시 돌린다.
- verifier timeout 2건은 reward 1.0으로 집계됐다. 두 task 모두 정답 patch의 verifier는 8초, 48초에 끝나므로 agent가 바꾼 코드가 테스트를 오래 끌게 한 경우다.
- 같은 조건으로 측정한 base model 결과가 있어야 학습 효과를 비교할 수 있다. 이 결과에서 100개 subset만 떼면 pass@1 0.49, `swebenchpro_v2_strat50`만 떼면 0.51이다.

## Appendix. 자원과 시간

- 동시 실행 수 × (CPU 4, 메모리 16 GB)가 호스트 여유 안에 들어야 한다. 동시 48이면 CPU 192, 메모리 768 GB.
- 1장에서 base 이미지(`ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`) 642개를 받는다. native가 빌드하는 `rllm-task-<instance_id>` 이미지는 중앙값 약 2.8 GB, 최대 약 15 GB다. 지우지 않으면 재실행은 빠르다.
- V2 verifier는 태스크에 들어 있는 `parser.py`로 채점하므로, Verified와 달리 채점용 패키지를 받지 않는다. V2 문서에 따르면 일부 Go 태스크는 테스트할 때 모듈을 받는다(`--verify-network`).
- 시간(측정, 9B, H200 8장에 vLLM data parallel 8, 동시 48): 1,284 rollout(642 × 2)에 약 6시간. task 이미지를 처음 빌드하는 첫 1시간은 시간당 약 180 rollout, 이후 230~260 rollout. 마지막 몇 개는 agent 상한(3600초) 가까이 도는 rollout이라 꼬리가 길다. oracle(642개)은 이미지가 빌드된 뒤 약 25분.
- 1장의 준비(base 이미지 642개 pull + libc 판별)는 처음 한 번 약 1시간 반이 걸렸다(`--jobs 16`). registry 응답이 늦으면 이미지마다 4번까지 다시 받는다.

## Appendix. 공식 V2 protocol과의 차이

Scale이 점수 보고용으로 정한 "locked protocol"(`v2/README.md`)과 이 레시피는 다음이 다르다. 외부 점수와 비교할 때 함께 적는다.

| 항목 | 공식 V2 | 이 레시피 |
| --- | --- | --- |
| 에이전트 단계 네트워크 | 차단, 모델 endpoint만 허용(`task.toml`의 단계별 `network_mode`, Harbor ≥0.22 + Modal) | 같다. `--no-agent-network`로 LLM gateway만 허용. verifier 단계는 `--verify-network`로 열린다. |
| 채점 위치 | 에이전트의 `git diff`만 깨끗한 이미지에 적용해 채점(`patch_replay`) | 에이전트가 작업한 같은 컨테이너에서 채점 |
| 자원 | CPU 1, 메모리 4 GB | CPU 4, 메모리 16 GB |
| harness | 공식 locked harness(mini-swe-agent, Claude Code, Codex) | rLLM native openhands-sdk |
| 시간 제한 | 50분 | agent 3600초, verifier 1000초, rollout 전체 4800초(1장 `--agent-timeout`/`--verifier-timeout`, 3.3) |

이미지(git 기록 정리), verifier(`tests/test.sh`), 에이전트 실행 중 `/tests`·`/solution`이 보이지 않는 점은 공식과 같다.

## Appendix. 원본 V2 태스크와 사본의 차이

사본(`$RLLM_HOME/datasets/<name>/`)만 바뀌고 clone은 그대로다.

| 변경 | 원본 | 사본 | 이유 |
| --- | --- | --- | --- |
| `task.toml` `[environment].cpus` | 1 | 4 | V2 release gate는 Modal에서 1 CPU로 통과했지만 로컬 Docker에서는 검증되지 않았다. 같은 저장소의 v1 subset은 로컬 Docker의 1 CPU에서 Go verifier가 3000초를 넘기고 ansible 워커가 죽었다(`../swebench-pro`). 같은 예산으로 맞춘다. |
| `task.toml` `[environment].memory_mb` | 4096 | 16384 | 같은 이유. v1 subset은 4 GB에서 100개 중 13개가 OOM으로 정답 패치도 실패했다. |
| `task.toml` `[environment].workdir` | 없음 | `"/app"` | `--hide-git-history`가 저장소 위치를 알아야 한다. 모든 V2 이미지의 WORKDIR이 `/app`이다. |
| `task.toml` `[agent]`/`[verifier]` `timeout_sec` | 3000 / 3000 | `--agent-timeout`/`--verifier-timeout` 값(권장 3600 / 1000) | `rllm eval`은 이 값을 환경변수보다 먼저 쓴다(3.3). 옵션을 빼면 원래 값 그대로다. |
| `environment/Dockerfile` | - | apt `Acquire::Check-Valid-Until "false"` 설정 한 줄 추가 | 컨테이너 안에서 `apt-get update`를 실행하는 harness가 Release 파일이 만료된 Debian 이미지에서 실패하는 것을 막는다(v1 subset에서 실측). apt가 없는 이미지에서는 아무 일도 하지 않고, oracle에는 영향이 없다. |
| `environment/Dockerfile` (Alpine 77개) | - | Debian bullseye의 glibc loader·라이브러리를 `/lib64`, `/{,usr/}lib/x86_64-linux-gnu`에 복사 | mount되는 openhands-sdk venv는 bullseye(glibc 2.31)에서 만들어져 musl 이미지에서는 python이 뜨지 않는다. 그러면 harness가 sandbox 안에 SDK를 설치하려 하는데 `--no-agent-network`에서는 받을 수 없어 agent가 시작도 못 한다. musl이 쓰지 않는 경로라 태스크의 toolchain과 테스트는 그대로 musl을 쓴다. 두 lib 경로가 다 필요하다(하나만 있으면 glibc loader가 Alpine의 musl 라이브러리를 집어 python이 segfault한다). |
| element-web의 `tests/run_script.sh` | Jest에 `--maxWorkers=1 --forceExit` | 변경 없음 | V2 자체 verifier의 설정이고 Scale의 release gate를 통과했다. v1 레시피는 registry 어댑터가 추가한 같은 플래그를 지운다(instance `aec454dd`). V2판은 그대로 둬도 통과한다. |
| `task.toml` 단계별 `network_mode` | `agent = "no-network"` 등 | 변경 없음 | rLLM은 읽지 않는다. native sandbox의 네트워크는 `--no-agent-network`/`--verify-network`가 정한다. |
