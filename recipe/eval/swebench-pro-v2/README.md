# SWE-bench Pro V2 subset (`swebenchpro_v2_100`) 평가

- Scale AI의 SWE-bench Pro V2(공개 642개)에서 100개 subset을 만들고, `rllm eval`로 평가하기 위한 가이드.
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

## 왜 subset인가

- 642개 전체 평가 소요시간 과다
- 100개 subset에 대해 oracle test 검증 완료(Harbor·native 모두 100/100)
- 구성: v1 subset(`../swebench-pro/subset-ids.txt`)과 최대한 같은 instance를 쓴다.
  - v1 subset 100개 중 V2에 남은 **85개는 그대로 둔다.** 나머지 15개는 V2 검수에서 제외됐다.
  - 빠진 15개는 V2의 나머지 태스크에서 보충한다. 추출률(뽑힌 수 / V2 태스크 수)이 가장 낮은 저장소에 하나씩 채우는 방식이고, 저장소 안에서는 seed 0으로 무작위로 뽑는다. 그래서 11개 저장소를 모두 포함하고 추출률이 14.7~16.4%로 고르다(tutanota만 4개 중 1개).
  - 언어: go 39, python 37, js 23, ts 1. id 목록은 `subset-ids.txt` 참고.

| 저장소 | V2 전체 | 유지 | 보충 | subset |
| --- | --- | --- | --- | --- |
| ansible/ansible | 82 | 12 | 1 | 13 |
| internetarchive/openlibrary | 82 | 9 | 4 | 13 |
| flipt-io/flipt | 78 | 11 | 1 | 12 |
| qutebrowser/qutebrowser | 73 | 9 | 2 | 11 |
| gravitational/teleport | 68 | 9 | 1 | 10 |
| future-architect/vuls | 58 | 7 | 2 | 9 |
| protonmail/webclients | 55 | 7 | 2 | 9 |
| element-hq/element-web | 52 | 8 | 0 | 8 |
| navidrome/navidrome | 52 | 8 | 0 | 8 |
| NodeBB/NodeBB | 38 | 5 | 1 | 6 |
| tutao/tutanota | 4 | 0 | 1 | 1 |

유지한 85개도 instance id만 같고 내용은 V2판이다. 문제 설명, test patch, F2P 목록 등이 바뀌었으므로 v1 점수와 직접 비교하지 않는다.

## 1. 데이터셋 준비

```bash
# Host와 같은 경로로 마운트된 볼륨 (../README.md 0.3)
export RLLM_HOME=/raid/rllm-work/rllm-home

# Harbor harness 전용. (default=900)
export RLLM_HARBOR_SESSION_TIMEOUT_S=4200

# scaleapi/SWE-bench_Pro-os@v2.0.0에서 subset 태스크만 sparse clone -> v2/SHA256SUMS 확인
#   -> 사본 ($RLLM_HOME/datasets/swebenchpro_v2_100/) -> registry 등록
python recipe/eval/swebench-pro-v2/prepare_swebenchpro_v2_subset.py
```

- clone은 `$RLLM_HOME/datasets/_upstream/SWE-bench_Pro-os@v2.0.0/`에 남고(100개 기준 약 15 MB) 재실행 때 재사용한다. 처음 받을 때 약 2~3분 걸린다.
- tag가 다른 커밋으로 옮겨졌으면 스크립트가 멈춘다(`66f92766`에 고정).
- 받은 파일은 모두 V2의 `v2/SHA256SUMS`와 대조한다. V2에 없는 id나 내용이 다른 파일이 있으면 등록하지 않는다.
- 이미 받아 둔 checkout이 있으면 `--source <checkout>/v2/tasks`로 지정한다.

## 2. Oracle test (생략 가능, 권장)

정답 패치를 적용해 Verifier가 1.0을 주는지 확인한다. LLM을 호출하지 않지만 CLI가 provider 설정을 요구하므로 죽은 포트를 준다.

```bash
export RLLM_HOME=/path/to/rllm-home RLLM_HARBOR_SESSION_TIMEOUT_S=4200
rllm eval swebenchpro_v2_100 \
    --split test \
    --agent harbor:oracle \
    --evaluator harbor_reward_fn \
    --sandbox-backend docker \
    --concurrency 16 \
    --sandbox-concurrency 16 \
    --no-ui \
    --base-url http://127.0.0.1:1/v1 \
    --model oracle-dummy
```

- 100/100이 나와야 한다. 0점이나 Errors가 있으면 모델을 돌리기 전에 오류를 해결한다(자원, 이미지, 디스크).
- 동시 16개 기준 약 30분(태스크 이미지 100개 pull 포함).
- native harness(`--agent oracle`, `--evaluator` 생략, 동시 8)도 100/100, 약 34분.
  - element-web 1개가 이미지 pull이 몰린 시점에 한 번 0점이 나왔고, 단독 재실행에서는 1.0이었다. 0점이 한두 개 나오면 그 태스크만 다시 돌려 본다.

## 3. 모델 평가

검증한 harness는 **openhands-sdk**(native, Harbor 둘 다)다. 재현성을 위해 `../config/qwen3_5.yaml`의 sampling params를 그대로 사용한다. 다른 값을 쓰려면 해당 파일 수정 대신 새 yaml을 만들어 `--sampling-params @<경로>`로 지정한다.

**native rLLM harness (기준 결과).** SDK를 한 번 구워 mount하므로(`--agent-image auto`) 태스크마다 설치하지 않는다. 채점은 태스크의 `tests/test.sh`를 rLLM이 직접 실행한다. 학습(`recipe/grpo/qwen3_5`)과 같은 경로라 학습 전후 비교에 적합하다.

```bash
# vLLM (Qwen3.5-9B 예시; tool calling 필수)
export RLLM_HOME=/path/to/rllm-home RLLM_HARBOR_SESSION_TIMEOUT_S=4200 HF_HOME=/path/to/hf-cache
vllm serve Qwen/Qwen3.5-9B --port 8000 --served-model-name Qwen/Qwen3.5-9B --max-model-len 131072 \
    --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml \
    --enable-prefix-caching

rllm eval swebenchpro_v2_100 \
    --split test \
    --agent openhands-sdk \
    --agent-image auto \
    --sandbox-backend docker \
    --concurrency 16 \
    --sandbox-concurrency 16 \
    --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen3.5-9B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml
```

**Harbor harness.** 설치된 harbor에 레시피 patch를 먼저 적용해야 한다(`../README.md` 3.4). 이 patch에 과거 reasoning 재전송도 들어 있다.

```bash
bash recipe/eval/scripts/apply_harbor_patches.sh

rllm eval swebenchpro_v2_100 \
    --split test \
    --agent harbor:openhands-sdk \
    --evaluator harbor_reward_fn \
    --sandbox-backend docker \
    --concurrency 16 \
    --sandbox-concurrency 16 \
    --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen3.5-9B \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --agent-kwargs @recipe/eval/config/harbor-openhands-sdk.yaml
```

- `--evaluator harbor_reward_fn`은 필수다. 이름이 `harbor:`로 시작하지 않는 데이터셋에서 Harbor harness를 쓸 때 CLI가 Evaluator를 스스로 찾지 못한다.
- Harbor 경로는 태스크마다 컨테이너 안에서 SDK(약 510 MB)를 설치한다. 외부 다운로드가 느리면 Harbor의 agent setup 제한(360초)을 넘겨 `AgentSetupTimeoutError`가 난다. 이것은 인프라 오류이므로 해당 태스크만 다시 돌린다.
- **thinking 모델은 과거 reasoning 재전송이 필요하다.** openhands-sdk는 kimi·deepseek·minimax에만 이전 턴의 reasoning을 다시 보낸다. 그러면 Qwen3.5의 이전 턴이 빈 `<think></think>`로 렌더링되고, 모델이 닫히지 않은 think 안에 tool call을 써서 호출이 파싱되지 않는다. 두 harness 모두 rLLM 쪽에서 이를 보완한다. native는 `rllm/harnesses/tools/openhands_sdk_runner.py`, Harbor는 `../README.md` 3.4의 patch가 맡는다.
  - 이 보완은 `reasoning_content`와 `reasoning` 두 필드에 모두 담아 보낸다. vLLM 0.22 미만은 `reasoning`만 읽는다.
- pass@k가 필요하면 `--attempts 4`처럼 설정한다.
- vLLM은 tool calling을 켜서 띄운다: `--enable-auto-tool-choice --tool-call-parser qwen3_xml` (Qwen3/3.5).
- Qwen3.5는 hybrid 구조라 vLLM이 prefix caching을 기본으로 끈다. agent 평가는 턴마다 같은 앞부분을 다시 보내므로 `--enable-prefix-caching`으로 켜면 태스크 시간이 크게 준다. 다만 출력이 float 오차 수준에서 달라지므로 비교할 실행끼리는 같은 설정을 쓴다.
- mini-swe-agent, opencode 등 다른 harness는 `../README.md` 3장 방법을 따르면 된다. V2 subset에서는 검증하지 않았다.

**기준 결과 (참고).** Qwen3.5-9B(thinking ON), native openhands-sdk 1.42.1, vLLM 0.19.0 + `--enable-prefix-caching`, `qwen3_5.yaml`, GPU 1장, 동시 16:

| 해결 | 소요 시간 | 태스크 시간 중앙값 |
| --- | --- | --- |
| 52 / 100 (pass@1) | 2시간 35분 | 1,035초 |

- 언어별로는 python 21/37, go 21/39, js 9/23, ts 1/1이다.

## 4. 결과

- `$RLLM_HOME/eval_results/swebenchpro_v2_100_<model>_<timestamp>/`에 `results.json`과 `episodes/`가 생긴다.
- 콘솔의 `Errors`는 인프라 실패(타임아웃, 이미지 빌드 실패)이고 0점과 다르다.
- native 실행은 LLM 호출이 0번인 에피소드(`No traces found`)를 Errors가 아닌 0점으로 집계한다. 에피소드의 step 수가 0이면 인프라 실패로 보고 다시 돌린다.
- Harbor harness는 trial 로그를 `$RLLM_HOME/harbor_trials/<task>-<n>__<실행태그>/`에 추가로 남긴다(실행마다 쌓이므로 주기적으로 지우는 것을 권장한다).

## Appendix. 자원과 시간

- 동시 실행 수 × (CPU 4, 메모리 16 GB)가 호스트 여유 안에 들어야 한다. 동시 16이면 CPU 64, 메모리 256 GB.
- 처음 실행 때 태스크별 이미지(`ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`)를 받는다. native가 빌드하는 `rllm-task-<instance_id>` 이미지는 중앙값 약 2.8 GB, 최대 약 15 GB다. 지우지 않으면 재실행은 빠르다.
- V2 verifier는 태스크에 들어 있는 `parser.py`로 채점하므로, Verified와 달리 채점용 패키지를 받지 않는다. V2 문서에 따르면 일부 Go 태스크는 테스트할 때 모듈을 받는다.
- Harbor harness는 태스크별 파생 이미지를 만들고 정상 종료 시 지운다. 프로세스를 강제 종료하면 컨테이너·네트워크·이미지가 남으니 `docker ps -a | grep -- -main-1`, `docker images | grep -- -main` 으로 확인한다.

## Appendix. 공식 V2 protocol과의 차이

Scale이 점수 보고용으로 정한 "locked protocol"(`v2/README.md`)과 이 레시피는 다음이 다르다. 외부 점수와 비교할 때 함께 적는다.

| 항목 | 공식 V2 | 이 레시피 |
| --- | --- | --- |
| 에이전트 단계 네트워크 | 차단, 모델 endpoint만 허용(`task.toml`의 단계별 `network_mode`, Harbor ≥0.22 + Modal) | **열려 있다.** rLLM이 고정한 Harbor 0.3.0은 `network_mode`를 무시하고, native sandbox에는 단계별 네트워크 정책이 없다. |
| 채점 위치 | 에이전트의 `git diff`만 깨끗한 이미지에 적용해 채점(`patch_replay`) | 에이전트가 작업한 같은 컨테이너에서 채점 |
| 자원 | CPU 1, 메모리 4 GB | CPU 4, 메모리 16 GB |
| harness | 공식 locked harness(mini-swe-agent, Claude Code, Codex) | openhands-sdk 등 rLLM harness |
| 시간 제한 | 50분 | 3000초(`task.toml`, 같음) |

이미지(git 기록 정리), verifier(`tests/test.sh`), 에이전트 실행 중 `/tests`·`/solution`이 보이지 않는 점은 공식과 같다.

## Appendix. subset vs original V2 tasks

사본(`$RLLM_HOME/datasets/swebenchpro_v2_100/`)만 바뀌고 clone은 그대로다.

| 변경 | 원본 | 사본 | 이유 |
| --- | --- | --- | --- |
| `task.toml` `[environment].cpus` | 1 | 4 | V2 release gate는 Modal에서 1 CPU로 통과했지만 로컬 Docker에서는 검증되지 않았다. 같은 저장소의 v1 subset은 로컬 Docker의 1 CPU에서 Go verifier가 3000초를 넘기고 ansible 워커가 죽었다(`../swebench-pro`). 같은 예산으로 맞춘다. |
| `task.toml` `[environment].memory_mb` | 4096 | 16384 | 같은 이유. v1 subset은 4 GB에서 100개 중 13개가 OOM으로 정답 패치도 실패했다. |
| `environment/Dockerfile` | - | apt `Acquire::Check-Valid-Until "false"` 설정 한 줄 추가 | 컨테이너 안에서 `apt-get update`를 실행하는 harness(Harbor mini-swe-agent 등)가 Release 파일이 만료된 Debian 이미지에서 실패하는 것을 막는다(v1 subset에서 실측). apt가 없는 이미지에서는 아무 일도 하지 않고, oracle에는 영향이 없다. |
| element-web 8개의 `tests/run_script.sh` | Jest에 `--maxWorkers=1 --forceExit` | 변경 없음 | V2 자체 verifier의 설정이고 Scale의 release gate를 통과했다. subset의 정답 패치 8개 모두 이 설정으로 통과한다. v1 레시피는 registry 어댑터가 추가한 같은 플래그를 지운다(instance `aec454dd`). V2판은 그대로 둬도 통과한다. |
| `task.toml` 단계별 `network_mode` | `agent = "no-network"` 등 | 변경 없음 | Harbor 0.3.0이 무시한다(위 Appendix). |
