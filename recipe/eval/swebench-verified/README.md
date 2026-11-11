# SWE-bench Verified 평가 (`swebench_verified_100`, 전체 `swebench_verified_all`)

- Harbor Registry의 `swebench-verified`(500개)를 받아 사본을 만들고, `rllm eval`의 **native harness**(openhands-sdk)로 평가하기 위한 가이드.
- Harbor harness는 쓰지 않는다(deprecated, [`../README.md`](../README.md) Appendix B). Harbor Registry는 **데이터 소스**로만 쓴다.
- 평가 전에 [`../README.md`](../README.md) **1장 체크리스트**(agent 네트워크 차단, git 기록 숨김, agent kwargs, timeout, generation kwargs)를 확인한다.
- 환경 설정: Docker Container 빌드, rLLM 패키지 설치 등 [`../README.md`](../README.md) 0장 참고.

## 왜 subset인가

- 500개 전체 평가 소요시간 과다
- 500개 중 100개 subset에 대해 oracle 검증 완료. 채점 불가로 알려진 `astropy__astropy-7606`(PASS_TO_PASS에 빈 pytest param id)은 뽑기 전에 제외(지금은 사본 보정으로 채점된다. 맨 아래 Appendix 참고)
- subset은 저장소 비율을 전체와 유사한 분포로 샘플링하여 구축 (seed 0; django 45, sympy 15, sphinx 9, matplotlib 7, scikit-learn 6, xarray 4, pytest 4, astropy 4, requests 2, pylint 2, flask 1, seaborn 1). id 목록은 `subset-ids.txt` 참고.

## 1. 데이터셋 준비

```bash
# Host와 같은 경로로 마운트된 볼륨 (../README.md 0.3)
export RLLM_HOME=/raid/rllm-work/rllm-home

# harbor:swebench-verified pull -> subset 추출 ($RLLM_HOME/datasets/swebench_verified_100/) -> registry 등록
# agent·verifier 상한은 학습(recipe/grpo/qwen3_5)과 같은 3600 / 1000초로 쓴다
python recipe/eval/swebench-verified/prepare_swebench_verified_subset.py --agent-timeout 3600 --verifier-timeout 1000

# 전체 평가: Verified 500 중 정답 패치로 채점되는 499개 (all-ids.txt 맨 위 주석에 제외 사유)
python recipe/eval/swebench-verified/prepare_swebench_verified_subset.py --agent-timeout 3600 --verifier-timeout 1000 \
    --ids recipe/eval/swebench-verified/all-ids.txt --name swebench_verified_all
```

- 처음 실행하면 `rllm dataset pull harbor:swebench-verified`(태스크 텍스트만, 이미지는 평가 때 받는다)를 먼저 한다. venv가 PATH에 있어야 한다(`source .venv/bin/activate`).
- 사본은 `$RLLM_HOME/datasets/<name>/<task_id>/`에 생긴다. Harbor 캐시(`~/.cache/harbor/tasks/`)는 그대로다. 원본을 고친 내용은 Appendix에 있다.
- **timeout은 환경변수로 바꿀 수 없다.** `rllm eval`은 agent·verifier 상한을 `task.toml` → 환경변수 순서로 정하고, 원본 `task.toml`에는 둘 다 3000초가 있다. 그래서 `--agent-timeout`, `--verifier-timeout`으로 사본에 쓴다(`../README.md` 1.3). 옵션을 빼면 3000초가 그대로 남는다.
- `--hide-git-history`에 필요한 저장소 위치는 Dockerfile의 `WORKDIR /testbed`에서 읽는다.
- 이미지(`swebench/sweb.eval.x86_64.*`)는 Ubuntu(glibc)라서 openhands-sdk agent image mount가 그대로 동작한다.
- `all-ids.txt`는 Appendix의 보정을 적용한 500개 사본에 Harbor oracle을 돌려 1.0이 나온 499개다. 빠진 것은 `django__django-10097` 하나다. 채점 대상 테스트 12개가 전체 suite를 함께 돌릴 때만 실패하고, 따로 돌리면 통과한다.

## 2. Oracle test (권장)

정답 패치를 적용해 verifier가 1.0을 주는지 확인한다. 모델 평가와 같은 sandbox 조건(git 기록 숨김, agent 단계 네트워크 차단, timeout)으로 돌린다. LLM을 호출하지 않지만 CLI가 provider 설정을 요구하므로 죽은 포트를 준다.

```bash
export RLLM_HOME=/raid/rllm-work/rllm-home
export RLLM_ROLLOUT_TIMEOUT_S=4800

rllm eval swebench_verified_100 \
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

- 100/100이 나와야 한다. 이전 검증: native(`--agent oracle`, 동시 8) 100/100 약 17분, Harbor oracle 100/100 약 30분(베이스 이미지 100개 pull 포함, trial 시간 중앙값 82초, 최대 412초). 둘 다 `--hide-git-history`·`--no-agent-network`·agent 3600 / verifier 1000 조건 이전의 측정이다.
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

rllm eval swebench_verified_100 \
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

- `--verify-network`는 필수다. verifier(`tests/test.sh`)가 `uv run`으로 `swebench` 등을 받는다.
- proprietary model은 `rllm model setup`으로 provider와 키를 등록하고 `--base-url` 없이 `--model`만 준다(`../README.md` 0.4).
- 설정별 의미(agent image mount, 네트워크, git 기록, timeout, agent kwargs, sampling)는 `../README.md` 1장과 3.2를 따른다.
- mini-swe-agent로 평가하려면 `--agent mini-swe-agent --agent-image auto`로 바꾸고 `--agent-kwargs`를 뺀다. mini-swe-agent v2는 `tool_choice: auto`를 보내므로 vLLM에 tool calling 옵션이 없으면 모든 호출이 400으로 실패한다.

## 4. 결과

- `$RLLM_HOME/eval_results/swebench_verified_100_<model>_<timestamp>/`에 `meta.json`, `results.json`, `episodes/`가 생긴다. 콘솔에는 Accuracy, Errors, pass@k가 찍힌다.
- 콘솔의 `Errors`는 인프라 실패(이미지 빌드 실패, verifier timeout 등)이고 0점과 다르다.
- LLM 호출이 0번인 에피소드(`No traces found`)는 Errors가 아닌 0점으로 집계된다. 에피소드의 step 수가 0이면 인프라 실패로 보고 다시 돌린다.

## Appendix. 자원과 시간

- 동시 실행 수 × (CPU 4, 메모리 16 GB)가 호스트 여유 안에 들어야 한다. 동시 16이면 CPU 64, 메모리 256 GB.
- 처음 실행 때 태스크별 베이스 이미지(`swebench/sweb.eval.x86_64.<repo>_1776_<instance>:latest`, 약 4 GB × 100)를 받는다. native가 빌드하는 `rllm-task-<task_id>` 이미지도 지우지 않으므로 재실행은 빠르다.
- verifier는 네트워크가 필요하다(`test.sh`가 `uv run`으로 `swebench` 등을 받는다).

## Appendix. subset vs original Harbor dataset

사본(`$RLLM_HOME/datasets/swebench_verified_100/`)만 바뀌고 Harbor 캐시(`~/.cache/harbor/tasks/`)는 그대로다.

| 변경 | 원본 | 사본 | 이유 |
| --- | --- | --- | --- |
| `task.toml` `[environment].cpus` | 1 | 4 | Python 저장소라 1 CPU로도 채점되지만(20개 실측) 검증기의 `pip install -e .`가 느리다. Pro subset과 같은 예산으로 맞춘다. |
| `task.toml` `[environment].memory` | `'4G'` (deprecated 문자열 표기) | `memory_mb = 16384` | Pro subset과 동일. rLLM은 `memory_mb`를 우선 읽는다. |
| `task.toml` `[agent]`/`[verifier]` `timeout_sec` | 3000 / 3000 | `--agent-timeout`/`--verifier-timeout` 값(권장 3600 / 1000) | `rllm eval`은 이 값을 환경변수보다 먼저 쓴다. 옵션을 빼면 원래 값 그대로다. |
| `tests/run_script.sh` | - | 변경 없음 | Verified 어댑터의 검증 스크립트는 업스트림 SWE-bench harness 흐름을 그대로 따른다. |
| `environment/Dockerfile` | - | apt `Acquire::Check-Valid-Until "false"` 설정 한 줄 추가 | 컨테이너 안에서 `apt-get update`를 실행하는 harness가 배포판 archive의 Release 파일이 만료된 이미지에서 실패하는 것을 막는다(Pro subset에서 실측). apt가 없는 이미지에서는 아무 일도 하지 않고, oracle에는 영향 없음. |
| `environment/Dockerfile` | - | `ENV OMP_NUM_THREADS=<cpus>` 추가 | 컨테이너 안의 `os.cpu_count()`는 호스트 코어 수(256)를 보고한다. 그래서 OpenMP 코드가 CPU 4개 할당에서 256개 스레드를 띄워 극도로 느려진다. `scikit-learn-14710`은 정답 패치로도 verifier가 3000초를 넘겼는데, 멈추던 테스트가 스레드 4개로는 2.4초에 끝난다. 이미지에 넣었으므로 agent의 테스트 실행에도 같이 적용된다. |
| `tests/test.sh` | `git clean -fd` | `git clean -fd -- <test patch가 건드리는 경로>` | 제한 없이 실행하면 solution이 새로 만든 파일이 모두 지워진다. 그래서 모듈을 추가하는 올바른 수정이 틀림으로 채점된다(`astropy-13398`: 정답 패치의 새 모듈이 삭제돼 테스트 72개 전부 실패). test patch 경로의 잔여 파일은 계속 지우므로 `git apply`가 막히지 않는다. |
| `tests/config.json` (`astropy__astropy-7606`) | P2P에 `test_compose_roundtrip[]` | `test_compose_roundtrip[unit0]` | 현재 pytest는 이 파라미터 이름을 `[unit0]`으로 만든다(97개 id 중 유일하게 다름). 원래 이름으로는 통과한 테스트가 매칭되지 않는다. |
| `tests/test.sh` (`sphinx-doc__sphinx-9711`) | `tox ... -- tests/test_extension.py` | `tox ... -- -rA tests/test_extension.py` | tox 경유 pytest에 `-rA`가 없어 테스트별 `PASSED` 줄이 출력되지 않는다. 그래서 테스트가 통과해도 SWE-bench 파서가 결과를 찾지 못한다. |
