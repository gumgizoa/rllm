# SWE-bench Pro (v1) subset (`swebenchpro_100`) 평가

- Harbor Registry의 `swebenchpro`(v1, 731개)에서 100개 subset 사본을 만들고, `rllm eval`의 **native harness**(openhands-sdk)로 평가하기 위한 가이드.
- Harbor harness는 쓰지 않는다(deprecated, [`../README.md`](../README.md) Appendix B). Harbor Registry는 **데이터 소스**로만 쓴다.
- 평가 전에 [`../README.md`](../README.md) **1장 체크리스트**(agent 네트워크 차단, git 기록 숨김, agent kwargs, timeout, generation kwargs)를 확인한다.
- 검수판 V2(642개)는 [`../swebench-pro-v2/README.md`](../swebench-pro-v2/README.md)를 참고한다. v1과 V2 점수는 직접 비교하지 않는다(문제 설명, test patch, F2P 목록이 바뀌었다).
- 환경 설정: Docker Container 빌드, rLLM 패키지 설치 등 [`../README.md`](../README.md) 0장 참고.

## 왜 subset인가

- 731개 전체 평가 소요시간 과다
- 731개 중 100개 subset에 대해 oracle 검증 완료
- subset은 저장소, 언어 비율을 전체와 유사한 분포로 샘플링하여 구축 (go 38, python 36, js 23, ts 3; 11개 저장소). id 목록은 `subset-ids.txt` 참고.

## 1. 데이터셋 준비

```bash
# Host와 같은 경로로 마운트된 볼륨 (../README.md 0.3)
export RLLM_HOME=/raid/rllm-work/rllm-home

# harbor:swebenchpro pull -> subset 추출 ($RLLM_HOME/datasets/swebenchpro_100/) -> base 이미지 libc 판별 -> registry 등록
# agent·verifier 상한은 학습(recipe/grpo/qwen3_5)과 같은 3600 / 1000초로 쓴다
python recipe/eval/swebench-pro/prepare_swebenchpro_subset.py --agent-timeout 3600 --verifier-timeout 1000
```

- 처음 실행하면 `rllm dataset pull harbor:swebenchpro`(태스크 텍스트만)를 먼저 한다. venv가 PATH에 있어야 한다(`source .venv/bin/activate`).
- 사본은 `$RLLM_HOME/datasets/swebenchpro_100/<task_id>/`에 생긴다. Harbor 캐시(`~/.cache/harbor/tasks/`)는 그대로다. 원본을 고친 내용은 Appendix에 있다.
- **Alpine(musl) 이미지에 glibc를 넣는다.** openhands-sdk agent image는 Debian bullseye(glibc)에서 만들어져 musl 이미지에서는 python이 뜨지 않고, 그러면 harness가 sandbox 안에서 SDK를 설치하려 하는데 `--no-agent-network`에서는 받을 수 없어 agent가 시작도 못 한다. 그래서 base 이미지 100개(`jefzda/sweap-images:<tag>`)를 받아 한 번씩 오프라인으로 실행해 musl을 판별하고, 해당 Dockerfile에 glibc runtime을 추가한다(subset에서 11개: teleport 5, protonmail 4, vuls 2). 목록은 `musl_tasks.txt`에 남는다. 구현은 `prepare_swebenchpro_subset.py`의 `add_glibc_to_musl_images`.
- **timeout은 환경변수로 바꿀 수 없다.** `rllm eval`은 agent·verifier 상한을 `task.toml` → 환경변수 순서로 정하고, 원본 `task.toml`에는 둘 다 3000초가 있다. 그래서 `--agent-timeout`, `--verifier-timeout`으로 사본에 쓴다(`../README.md` 1.3). 옵션을 빼면 3000초가 그대로 남는다.
- `--hide-git-history`에 필요한 저장소 위치는 Dockerfile의 `WORKDIR /app`에서 읽는다.

## 2. Oracle test (권장)

정답 패치를 적용해 verifier가 1.0을 주는지 확인한다. 모델 평가와 같은 sandbox 조건(git 기록 숨김, agent 단계 네트워크 차단, timeout)으로 돌린다. LLM을 호출하지 않지만 CLI가 provider 설정을 요구하므로 죽은 포트를 준다.

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
export RLLM_ROLLOUT_TIMEOUT_S=4800

rllm eval swebenchpro_100 \
    --split test \
    --agent oracle \
    --concurrency 24 \
    --sandbox-concurrency 24 \
    --hide-git-history \
    --no-agent-network \
    --verify-network \
    --sandbox-backend docker \
    --no-ui \
    --base-url http://127.0.0.1:1/v1 \
    --model oracle-dummy
```

- 100/100이 나와야 한다. 이전 검증: Harbor oracle 100/100(동시 8, 약 30~40분). glibc 추가, `--hide-git-history`·`--no-agent-network`·agent 3600 / verifier 1000 조건으로는 다시 측정하지 않았다. 같은 저장소의 V2 full set은 이 조건에서 642/642였다(`../swebench-pro-v2/README.md`).
- 0점이나 Errors가 있으면 모델을 돌리기 전에 원인을 해결한다(자원, 이미지, 디스크).

## 3. 모델 평가

[`../README.md`](../README.md) 1.2 표준 명령과 같다. 재현성을 위해 `../config/qwen3_5.yaml`의 sampling params와 `../config/openhands-sdk.yaml`의 agent kwargs를 그대로 사용한다. 다른 값을 쓰려면 해당 파일 수정 대신 새 yaml을 만들어 지정한다.

```bash
# vLLM (Qwen3.5-9B 예시; tool calling, reasoning parser 필수)
export RLLM_HOME=/raid/rllm-work/rllm-home HF_HOME=/path/to/hf-cache
vllm serve Qwen/Qwen3.5-9B --port 8000 --served-model-name Qwen/Qwen3.5-9B --max-model-len 262144 \
    --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml --enable-prefix-caching

# rollout(agent + verifier) 전체 예산. task.toml의 verifier 몫(1000초)을 먼저 떼고 남은 시간이 agent 상한이 된다
export RLLM_ROLLOUT_TIMEOUT_S=4800
export RLLM_HARNESS_RUN_TIMEOUT_S=3600 RLLM_VERIFIER_TIMEOUT_S=1000

rllm eval swebenchpro_100 \
    --split test \
    --agent openhands-sdk \
    --agent-image auto \
    --agent-kwargs @recipe/eval/config/openhands-sdk.yaml \
    --sampling-params @recipe/eval/config/qwen3_5.yaml \
    --attempts 2 \
    --concurrency 16 \
    --sandbox-concurrency 16 \
    --hide-git-history \
    --no-agent-network \
    --verify-network \
    --sandbox-backend docker \
    --no-ui \
    --base-url http://127.0.0.1:8000/v1 \
    --model Qwen/Qwen3.5-9B
```

- proprietary model은 `rllm model setup`으로 provider와 키를 등록하고 `--base-url` 없이 `--model`만 준다(`../README.md` 0.4).
- 설정별 의미(agent image mount, 네트워크, git 기록, timeout, agent kwargs, sampling)는 `../README.md` 1장과 3.2를 따른다.
- mini-swe-agent로 평가하려면 `--agent mini-swe-agent --agent-image auto`로 바꾸고 `--agent-kwargs`를 뺀다. mini-swe-agent v2는 `tool_choice: auto`를 보내므로 vLLM에 tool calling 옵션이 없으면 모든 호출이 400으로 실패한다.
- 전체 731개는 rLLM builder dataset `swebench_pro`(`rllm dataset pull swebench_pro`)로 평가한다(`../README.md` 2.2). Harbor의 `harbor:swebenchpro`는 CPU 1, 4 GB라서 Go 저장소의 verifier가 시간 안에 끝나지 않는다.

## 4. 결과

- `$RLLM_HOME/eval_results/swebenchpro_100_<model>_<timestamp>/`에 `meta.json`, `results.json`, `episodes/`가 생긴다. 콘솔에는 Accuracy, Errors, pass@k가 찍힌다.
- 콘솔의 `Errors`는 인프라 실패(이미지 빌드 실패, verifier timeout 등)이고 0점과 다르다.
- LLM 호출이 0번인 에피소드(`No traces found`)는 Errors가 아닌 0점으로 집계된다. 에피소드의 step 수가 0이면 인프라 실패로 보고 다시 돌린다.

## Appendix. 자원과 시간

- 동시 실행 수 × (CPU 4, 메모리 16 GB)가 호스트 여유 안에 들어야 한다. 동시 16이면 CPU 64, 메모리 256 GB.
- 1장에서 태스크별 베이스 이미지(`jefzda/sweap-images:<tag>`, 약 4 GB × 100)를 받는다. native가 빌드하는 `rllm-task-<task_id>` 이미지도 지우지 않으므로 재실행은 빠르다.

## Appendix. subset vs original Harbor dataset

사본(`$RLLM_HOME/datasets/swebenchpro_100/`)만 바뀌고 Harbor 캐시(`~/.cache/harbor/tasks/`)는 그대로다.

| 변경 | 원본 | 사본 | 이유 |
| --- | --- | --- | --- |
| `task.toml` `[environment].cpus` | 1 | 4 | `pytest -n auto`(ansible), `go test ./...`(Go 4개 저장소), Jest가 호스트 nproc(256)만큼 병렬로 뜬다. CPU 1에서는 Go 검증기가 3000초를 넘기고(정답 패치도 0점) ansible 워커가 죽는다. |
| `task.toml` `[environment].memory_mb` | 4096 | 16384 | 같은 병렬도에서 4 GB는 OOM(`signal: killed`, `Killed`, pytest `BrokenPipeError`). 4 GB로 재검증 시 100개 중 13개 실패, 16 GB에서 전부 통과. |
| `task.toml` `[agent]`/`[verifier]` `timeout_sec` | 3000 / 3000 | `--agent-timeout`/`--verifier-timeout` 값(권장 3600 / 1000) | `rllm eval`은 이 값을 환경변수보다 먼저 쓴다. 옵션을 빼면 원래 값 그대로다. |
| element-web 8개의 `tests/run_script.sh` | Jest에 `--maxWorkers=1 --forceExit` | 두 플래그 제거 (업스트림 `SWE-bench_Pro-os`와 동일) | Harbor 어댑터가 추가한 플래그. 단일 워커에서는 테스트 파일 간에 WASM(`matrix-wysiwyg`) 상태가 공유되어 instance `aec454dd`의 정답 패치가 항상 0점. 업스트림에는 이 플래그가 없다. |
| `environment/Dockerfile` | - | apt `Acquire::Check-Valid-Until "false"` 설정 한 줄 추가 | 컨테이너 안에서 `apt-get update`를 실행하는 harness가 Debian bullseye 기반 이미지(nodebb, element-web)에서 `E: Release file ... is expired`로 실패하는 것을 막는다. apt가 없는 이미지에서는 아무 일도 하지 않고, oracle에는 영향 없음. |
| `environment/Dockerfile` (Alpine 11개) | - | Debian bullseye의 glibc loader·라이브러리를 `/lib64`, `/{,usr/}lib/x86_64-linux-gnu`에 복사 | mount되는 openhands-sdk venv는 bullseye(glibc 2.31)에서 만들어져 musl 이미지에서는 python이 뜨지 않는다. musl이 쓰지 않는 경로라 태스크의 toolchain과 테스트는 그대로 musl을 쓴다. |
| instance id 매칭 | 일부 소문자 (`instance_nodebb__...`) | `subset-ids.txt`의 원본 표기 | 대소문자 무시로 매핑. 등록 행에는 사본 디렉토리 이름과 원본 id 둘 다 남긴다. |
