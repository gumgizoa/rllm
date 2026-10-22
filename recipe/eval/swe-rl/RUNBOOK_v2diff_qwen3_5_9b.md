# swe_rl_v2 차집합(740건) x 8 롤아웃 실행 명세 - Qwen3.5-9B 서버 호스트용

대상: v2 \ v1 = 740 태스크 (python 43, go 108, typescript 589), openhands-sdk(native) + Qwen/Qwen3.5-9B, attempts 4.
목적: **학습용**. 8회 중 한 번이라도 reward 를 받는 태스크를 골라내고(0/4 는 학습 신호가 없어 버린다)
그 성공 궤적을 SFT/RL 데이터로 쓴다. 시도 수가 곧 건져지는 태스크 수이자 궤적 수이지만, 시간 때문에 4 로 간다(아래 표).
순서: 환경 구성 -> 데이터셋 변환/등록 -> oracle 전수 -> 통과분으로 `_ok` 등록 -> 스모크 -> 8회 롤아웃 -> 집계.
v1 롤아웃(2026-10-14~16, 호스트 raid-mmi)에서 겪은 문제의 해결책이 전부 들어 있으니 순서대로 따르면 됩니다.

번들: `v2diff_bundle.tar.gz` (rllm 패치 + 새 스크립트 + v2 jsonl 3개 + 차집합 id 목록). 아래 `$BUNDLE` 은 압축을 푼 디렉터리.

---

## 0. 호스트 사전 확인 (10분)

```bash
nproc; free -g                      # 샌드박스 1개 = 4 CPU / 32 GB 상한. 동시 32면 128 CPU
docker info | grep -E "Root Dir|Storage Driver|driver-type"
df -h / $(docker info -f '{{.DockerRootDir}}')
```
- **이미지가 어느 디스크에 쌓이는지**가 가장 중요합니다. `driver-type: io.containerd.snapshotter.v1` 이면 Docker Root Dir 설정과 무관하게 `/var/lib/containerd`(루트 디스크)에 쌓일 수 있습니다. 확인법: 아무 이미지나 1개 pull 하고 `df` 변화가 어느 마운트에 나타나는지 봅니다.
  - 큰 디스크에 쌓이면: 배치 정리 없이 이미지를 캐시해도 됩니다 (`run_batches.sh` 의 `KEEP_IMAGES=1`, 아래 참조). oracle 때 만든 이미지가 롤아웃에 재사용돼 시간이 크게 줍니다.
  - 루트 디스크에 쌓이면: 반드시 `run_batches.sh`(배치 종료 시 이미지 삭제) + `disk_guard_rllm.sh`(가드)를 씁니다. v1에서는 배치 32개 이미지가 140 GB까지 갔습니다.
- LLM 서버는 이 호스트에서 접근만 되면 됩니다 (에이전트 컨테이너는 rllm 게이트웨이를 거침). 검증: `curl http://27.122.129.140:8222/v1/models` (사내망 `http://10.10.20.20:8222/v1`).
- 다른 사용자가 같은 docker 데몬을 쓰는 공용 호스트면 **절대 `docker system prune -a` / `image prune -a`** 금지 (아래 스크립트는 우리 이미지만 지웁니다).

## 1. rllm 컨테이너 (20분)

공유 디렉터리는 호스트와 컨테이너에서 **같은 경로**여야 합니다 (verifier bind-mount를 호스트 데몬이 해석). 예시는 `/data/rllm-work`.

```bash
WORK=/data/rllm-work                      # 큰 디스크 위, 호스트/컨테이너 동일 경로
mkdir -p $WORK/rllm-home
git clone <rllm repo> $WORK/rllm          # 팀 레포, main (base: $BUNDLE/rllm_patch/BASE_COMMIT)

docker run -d --name rllm-v2 --network host \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $WORK:$WORK --shm-size 32g -w $WORK/rllm \
  pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel sleep infinity
# GPU 불필요 (--gpus 생략). 다른 베이스 이미지도 python3.12+docker CLI만 되면 무방.

docker exec rllm-v2 bash -c '
set -e; export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq curl git patch docker.io docker-compose-v2 docker-buildx
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12 && uv venv --python 3.12 '$WORK'/venv
source '$WORK'/venv/bin/activate && cd '$WORK'/rllm && uv pip install -e ".[harbor]"
docker buildx version && docker ps >/dev/null && rllm --version'
```
- `docker-buildx` **필수**: legacy builder는 같은 레포 Dockerfile을 병렬 빌드할 때 레이어 레이스("content digest not found")가 납니다. BuildKit은 `/etc/hosts` 쓰기를 금지하는데, 변환기가 그 RUN 줄을 `[rllm].setup_commands`로 옮겨서 처리합니다.
- harbor 패치(`apply_harbor_patches.sh`)는 harbor 하네스 전용이라 **native 경로에는 불필요**합니다.

## 2. rllm 패치 적용 (5분)

```bash
cd $WORK/rllm
git apply $BUNDLE/rllm_patch/rllm_core.diff          # base와 다르면 git apply -3
cp -r $BUNDLE/rllm_patch/swe-rl recipe/eval/
cp $BUNDLE/rllm_patch/qwen3_8_flash_next.yaml recipe/eval/config/   # 참고용, 9B는 qwen3_5.yaml 사용
```
패치 내용 (모두 v1 런에서 실제로 발생한 문제):

| 파일 | 내용 | 없으면 |
| --- | --- | --- |
| `rllm/eval/_resolution.py` | 같은 태그 `docker build` 를 태그별 락으로 직렬화 + 이미지 있으면 재사용 | `--attempts N` 에서 N개 롤아웃이 동시에 같은 이미지를 빌드 -> 1개 빼고 전부 "already exists"로 에러 |
| `rllm/sandbox/backends/docker.py` | docker-py 클라이언트 타임아웃 `RLLM_DOCKER_CLIENT_TIMEOUT` (기본 60 유지) | 데몬이 1분 멈추면 배치의 롤아웃 10여 개가 ReadTimeout 에러 |
| `rllm/harnesses/openhands_sdk.py`, `tools/openhands_sdk_runner.py` | `RLLM_OPENHANDS_REASONING_EFFORT` 를 샌드박스로 전달 | 서버가 SDK 기본값 "high"를 거부하면 전 롤아웃 0점. **9B vLLM은 모두 허용하므로 설정 불필요** |
| `rllm/sandbox/git_history.py` | `--hide-git-history` 의 `git config --global` 실패를 비치명적으로 | HOME이 디렉터리가 아닌 이미지(ggshield 3건)에서 에러 |

## 3. 환경 파일

```bash
cat > $WORK/env.sh <<EOF
source $WORK/venv/bin/activate
export RLLM_HOME=$WORK/rllm-home
export RLLM_HARBOR_SESSION_TIMEOUT_S=4200
export RLLM_DOCKER_CLIENT_TIMEOUT=300
cd $WORK/rllm
EOF
```
모든 명령은 `docker exec rllm-v2 bash -c 'source $WORK/env.sh && ...'` 로 컨테이너 안에서 실행합니다. 컨테이너가 만든 파일은 root 소유이므로 결과 디렉터리 조작도 컨테이너 안에서 합니다.

## 4. 데이터셋 변환/등록 (5분)

```bash
docker exec rllm-v2 bash -c "source $WORK/env.sh && python recipe/eval/swe-rl/prepare_swe_rl.py \
  --name swe_rl_v2_diff --ids $BUNDLE/data/v2_minus_v1_ids.txt \
  $BUNDLE/data/python_723.jsonl $BUNDLE/data/go_713.jsonl $BUNDLE/data/typescript_589.jsonl"
# 기대: swe_rl_v2_diff: 740 tasks ... per language: {'python': 43, 'go': 108, 'typescript': 589}
```
- 언어는 파일명 접두어로 판정하므로 파일명을 바꾸지 마세요. `SHA256SUMS`가 같은 디렉터리에 있으면 자동 검증.
- 생성물: `$RLLM_HOME/datasets/swe_rl_v2_diff/<instance_id>/{task.toml, instruction.md, environment/Dockerfile, tests/{test.sh,run_tests.sh,config.json}, solution/{solve.sh,gold.patch}}` + `dataset.toml` + parquet 등록.
- task.toml: cpus=4, memory_mb=32768, workdir=/testbed, agent 1800s, verifier 5400s. 바꾸려면 `--cpus/--memory-mb/--agent-timeout/--verifier-timeout`.
- `tests/test.sh` 가 `PYTEST_XDIST_AUTO_NUM_WORKERS=4` 를 export 합니다 (`pytest -n auto` 가 호스트 코어 수만큼 워커를 띄워 OOM 루프에 빠지는 것 방지).
- **채점기 하드닝 (2026-10-16, 이 번들부터).** SWE-Factory가 만든 `run_tests.sh` 는 test patch 적용 전 정리가 불완전해서, 에이전트가 테스트 파일을 고치거나 test patch가 만들 파일을 미리 만들어 두면 `git apply` 가 실패하고도 그대로 진행해 **에이전트가 쓴 테스트로 채점**된다 (v1 실측: 새 파일을 만드는 태스크 251건 중 정리 처리가 있는 것 0건). 변환기가 이를 막는다.
  - `tests/test.patch` (원본 test patch)와 `tests/restore_test_targets.sh` 를 태스크마다 생성한다. 후자는 test patch가 건드리는 모든 경로에 대해 untracked면 `rm -rf`, base에 있으면 `git checkout <base> -- <path>`, base에 없으면 `rm -rf` 를 런타임에 판정해 수행한다.
  - `tests/test.sh` 가 `run_tests.sh` 실행 **전에** 복원 스크립트를 돌리고 `git apply --check tests/test.patch` 로 정답 test patch가 실제로 적용 가능한지 확인한다. 복원이나 확인이 실패하면 테스트를 돌리지 않고 reward 0 (`test_target_restore_failed` / `test_patch_apply_failed`).
  - `run_tests.sh` 자체는 한 줄도 바꾸지 않는다 (실행되는 테스트 범위 동일). `config.json` 에 `restore_paths`/`remove_paths`/`grader_version` 이 기록된다.
  - **oracle 로는 이 구멍이 드러나지 않는다.** gold patch 는 소스만 바꾸고 테스트는 건드리지 않아 test patch 가 깨끗이 적용되기 때문이다. 아래 6장의 속이기 시험으로 확인한다.

## 5. oracle 전수 (예상 1~2일, TS 빌드가 무거움)

```bash
docker exec -d rllm-v2 bash -c "source $WORK/env.sh && DATASET=swe_rl_v2_diff BATCH=16 CONCURRENCY=16 MIN_FREE_GB=160 \
  bash recipe/eval/swe-rl/run_batches.sh oracle_v2diff oracle --base-url http://127.0.0.1:1/v1 --model oracle-dummy \
  > $WORK/oracle_v2diff.out 2>&1"
# 이미지가 큰 디스크에 쌓이는 호스트면 KEEP_IMAGES=1 을 앞에 붙여 이미지를 남깁니다 (롤아웃에서 재사용).
```
- 진행: `tail $RLLM_HOME/eval_results/oracle_v2diff/batches.log` (배치별 Accuracy/Errors). 배치 로그 `batch_NNNN.log`.
- 디스크 가드(루트에 쌓이는 호스트만): 호스트에서
  `MIN_FREE_GB=100 CACHE_PRUNE_BELOW_GB=100 MIN_AGE_MIN=30 IDLE_IMAGE_MIN_AGE_MIN=20 INTERVAL=120 nohup bash $WORK/rllm/recipe/eval/swe-rl/disk_guard_rllm.sh watch >> $WORK/disk_guard.log 2>&1 &`
  (여유 < 100G 일 때만 빌드 캐시 전량 prune + 20분 이상 유휴인 우리 태스크 이미지 삭제. 데몬 전체 빌드 캐시가 지워지므로 공용 호스트면 다른 사용자에게 알리세요.)
- 끝나면 집계 + 통과 목록:
```bash
docker exec rllm-v2 bash -c "source $WORK/env.sh && R=\$RLLM_HOME/eval_results/oracle_v2diff && \
  python recipe/eval/swe-rl/summarize_oracle.py \$R && \
  grep -v -x -f \$R/oracle_fail_ids.txt \$R/ids_sorted.txt > \$R/oracle_pass_ids.txt && wc -l \$R/oracle_pass_ids.txt"
```
- **에러(Errors)와 실패(0.0)는 다릅니다.** 에러는 인프라(빌드 레이스, 데몬 타임아웃, 네트워크)일 수 있으니 에러 난 태스크만 모아 한 번 재실행합니다:
  `rllm eval swe_rl_v2_diff --split test --agent oracle --sandbox-backend docker --task-indices <idx,idx,...> --concurrency 16 --sandbox-concurrency 16 --no-ui --base-url http://127.0.0.1:1/v1 --model oracle-dummy --episodes-dir $RLLM_HOME/eval_results/oracle_v2diff/retry_0001`
  인덱스는 `ids_sorted.txt`(task_id 코드포인트 정렬) 의 0-based 줄 번호. `retry_*` 디렉터리는 집계에서 `batch_*` 결과를 덮어씁니다.
- v1 실측: 1,471건 중 oracle 통과 97.9%. 실패 유형은 환경 드리프트(핀 없는 pytest/pyarrow/uv, `@latest`)가 절반, flaky 테스트, gold/test 불일치. 재현 안 되는 0.0도 있으니 실패 원인 분석은 선택.

## 6. 통과분 등록 + 스모크 (30분)

```bash
docker exec rllm-v2 bash -c "source $WORK/env.sh && python recipe/eval/swe-rl/prepare_swe_rl.py \
  --name swe_rl_v2_diff_ok --ids \$RLLM_HOME/eval_results/oracle_v2diff/oracle_pass_ids.txt \
  $BUNDLE/data/python_723.jsonl $BUNDLE/data/go_713.jsonl $BUNDLE/data/typescript_589.jsonl"

# 스모크: 3태스크 x 2회. 첫 실행은 openhands-sdk 에이전트 이미지(rllm-agent-*)를 굽습니다.
# BuildKit에서 동시 bake 가 충돌하므로 첫 스모크는 반드시 --concurrency 1 로 한 태스크부터.
docker exec rllm-v2 bash -c "source $WORK/env.sh && rllm eval swe_rl_v2_diff_ok --split test --agent openhands-sdk --agent-image auto \
  --sandbox-backend docker --attempts 1 --task-indices 0 --concurrency 1 --sandbox-concurrency 1 --hide-git-history --no-ui \
  --base-url http://27.122.129.140:8222/v1 --model Qwen/Qwen3.5-9B --sampling-params @recipe/eval/config/qwen3_5.yaml \
  --episodes-dir \$RLLM_HOME/eval_results/smoke_bake"
docker exec rllm-v2 bash -c "source $WORK/env.sh && rllm eval swe_rl_v2_diff_ok --split test --agent openhands-sdk --agent-image auto \
  --sandbox-backend docker --attempts 2 --task-indices 0,300,700 --concurrency 6 --sandbox-concurrency 6 --hide-git-history --no-ui \
  --base-url http://27.122.129.140:8222/v1 --model Qwen/Qwen3.5-9B --sampling-params @recipe/eval/config/qwen3_5.yaml \
  --episodes-dir \$RLLM_HOME/eval_results/smoke_rollout"
```
확인할 것: Errors 0, 각 롤아웃 로그에 `[llm=NNNs/K steps]` 에서 K가 1보다 크고 llm 시간이 0이 아닐 것 (0이면 LLM 호출이 전부 실패한 것 - 에피소드 JSON의 `metadata.upstream_error` 확인).

### 6.1 채점기 속이기 시험 (권장, 언어별 표본 몇 건)

oracle 과 스모크는 채점기 구멍을 잡지 못한다. 표본 태스크에서 아래 둘이 **0점**이어야 한다.

```bash
# C1: 정답 소스 없이, test patch 가 수정하는 파일을 무조건 통과하는 테스트로 덮어쓴다
# C2: 정답 소스 없이, test patch 가 새로 만드는 파일을 같은 경로에 미리 만든다
# (config.json 의 restore_paths / remove_paths 가 각각의 대상이다)
```
컨테이너에서 해당 파일을 덮어쓴 뒤 `/tests/test.sh` 를 돌려 `/tmp/rllm/reward.json` 을 본다.
기대: `reward 0.0`, reason 이 `test_patch_apply_failed` 또는 `tests_failed`.
같은 조작을 하드닝 전 태스크로 하면 C2 에서 1.0 이 나온다(구멍의 직접 증거).

## 7. 8회 롤아웃 (예상 3~6일)

```bash
docker exec -d rllm-v2 bash -c "source $WORK/env.sh && DATASET=swe_rl_v2_diff_ok BATCH=32 CONCURRENCY=32 MIN_FREE_GB=160 \
  bash recipe/eval/swe-rl/run_batches.sh rollout4_v2diff openhands-sdk --attempts 4 --agent-image auto --hide-git-history \
  --base-url http://27.122.129.140:8222/v1 --model Qwen/Qwen3.5-9B --sampling-params @recipe/eval/config/qwen3_5.yaml \
  > $WORK/rollout4_v2diff.out 2>&1"
```
- 배치 = 32태스크 x 4 = 128 롤아웃. 740건이면 24배치.
- **동시성은 LLM 지연으로 정합니다.** 롤아웃 중 아래 프로브가 15초를 넘으면 포화입니다 (v1: 동시 48에서 62초 -> 스텝당 1분 -> 1800초 제한에 70% 걸림, 24에서 13초). 서버가 DP=2 9B라 32~48이 가능할 것으로 봅니다. `/metrics` 의 `vllm:num_requests_waiting` 이 계속 양수면 줄이세요.
  `curl -s -o /dev/null -w "%{time_total}\n" http://27.122.129.140:8222/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"Qwen/Qwen3.5-9B","messages":[{"role":"user","content":"Reply ok."}],"max_tokens":32}'`
- 동시성 변경은 배치 경계에서: `batches.log` 에 `batch_NNNN images removed` 가 찍힌 직후 러너를 죽이고 `START_BATCH=<다음 번호>` 로 재시작 (완료 배치는 `results.json` 존재로 자동 스킵). 러너를 죽일 때 `pkill -f run_batches` 는 자기 셸을 같이 죽일 수 있으니 PID로 죽이세요.
- 롤아웃 시간은 대부분 테스트 실행(tool) 시간이라 모델이 빨라도 롤아웃당 10~15분 밑으로 잘 안 내려갑니다. 1800초 타임아웃 비율은 레포에 따라 20~75%였고, 타임아웃이어도 그 전에 고친 코드로 verifier가 통과하는 경우가 많습니다.
- 자주 보는 에러 유형: `Docker build failed ... @latest requires go >= X` (Dockerfile 핀 없음, oracle 이후 드리프트 -> 제외), `ImageNotFound` (가드가 이미지를 지운 직후 샌드박스 생성 -> 재실행), `ReadTimeout` (데몬 부하 -> 재실행). 에러 태스크는 끝난 뒤 `--task-indices` 로 attempts 4 재실행하면 집계에서 대체됩니다 (디렉터리 이름이 `batch_*` 뒤에 정렬되게, 예 `retry_0001`).

## 8. 집계

```bash
docker exec rllm-v2 bash -c "source $WORK/env.sh && python recipe/eval/swe-rl/tabulate_attempts.py \
  \$RLLM_HOME/eval_results/rollout4_v2diff/batch_*/results.json \$RLLM_HOME/eval_results/rollout4_v2diff/retry_*/results.json \
  --dataset swe_rl_v2_diff_ok --csv $WORK/rollout4_v2diff_per_task.csv"
```
출력: 전체/언어별 0/4~4/4 히스토그램, pass@1(평균), pass@4(any), 에러 수, per-task CSV(instance_id, language, n_attempts, n_correct, n_errors). 에러가 남은 태스크는 n_attempts < 4 이므로 통계에서 빼거나 재실행하세요.

**attempts 를 4 로 줄였다 (2026-10-16 결정).** 8 회는 기간이 2배라 4 로 간다. 비용은
"풀 수 있는데 4회 안에 못 건진" 태스크가 생기는 것이다. 성공률 p 인 태스크가 한 번도 성공하지 못할 확률:

| 태스크 성공률 | 4회 | 8회 |
| --- | --- | --- |
| p=0.5 | 6% | 0% |
| p=0.25 | 32% | 10% |
| p=0.125 | 59% | 34% |

raid-mmi 의 attempts=4 실측(224 태스크)은 0/4 가 14.3%, 한 번이라도 성공이 85.7% 였다.
**0 점으로 끝난 태스크만 나중에 4회 더 돌리면** 전체를 8회 돌리는 것의 ~15% 비용으로 8회에 가깝게 건진다.

```bash
awk -F, 'NR>1 && $4==0 {print $1}' <per_task.csv> > zero_ids.txt   # 0점 태스크
# zero_ids.txt 의 id 를 ids_sorted.txt 에서 찾아 0-based 줄번호로 바꾼 뒤 --task-indices 로 전달
rllm eval <dataset> --split test --agent openhands-sdk --agent-image auto --sandbox-backend docker \
  --attempts 4 --task-indices <idx,...> --concurrency 24 --sandbox-concurrency 24 --no-ui \
  --hide-git-history --base-url <url> --model <model> --sampling-params @recipe/eval/config/qwen3_5.yaml \
  --episodes-dir $RLLM_HOME/eval_results/<run>/retry_zero_0001
```
집계에서 `retry_*` 는 해당 태스크의 이전 시도를 **대체**한다(8회로 합산되지 않는다). 8회 통계가
필요하면 두 디렉터리를 따로 집계해 더한다.

### 8.1 학습용 산출물 추리기

```bash
# 한 번이라도 푼 태스크 = 학습에 쓸 수 있는 태스크
awk -F, 'NR>1 && $4>0 {print $1}' $WORK/rollout4_v2diff_per_task.csv > $WORK/trainable_ids.txt
wc -l < $WORK/trainable_ids.txt
# 성공 궤적 = reward 1 로 끝난 에피소드 JSON
grep -l '"is_correct": true' $RLLM_HOME/eval_results/rollout4_v2diff/batch_*/episodes/*.json > $WORK/success_episodes.txt
```
- 궤적은 `episodes/episode_<rollout_idx>_<task_id>_<attempt>.json` 에 있고 `chat_completions` 에
  `reasoning_content` 까지 들어 있다(thinking 학습에 필요).
- **용량 주의.** v1 실측 평균 11 MB/에피소드(최대 66 MB). 740 x 4 = 2,960 에피소드면 **약 33 GB**다.
  `RLLM_HOME` 이 있는 디스크에 그만큼 여유를 두고, 끝나면 tar 로 묶어 NAS 로 옮긴다
  (파일 수가 많아 개별 복사는 느리다).
- 궤적이 필요 없다면 `--no-save-episodes` 로 끌 수 있지만, 학습용 롤아웃에서는 끄지 않는다.

## 부록 A. run_batches.sh 환경변수

| 변수 | 기본 | 의미 |
| --- | --- | --- |
| `DATASET` / `SPLIT` | swe_rl_v1 / test | 등록된 데이터셋 이름 |
| `BATCH` | 16 | 배치당 태스크 수 (이미지 수 = 디스크 피크) |
| `CONCURRENCY` | 16 | `--concurrency`/`--sandbox-concurrency` |
| `MIN_FREE_GB` | 100 | 배치 시작 전 요구 여유(`GUARD_PATH=/`). 미달이면 유휴 이미지 정리 후 2분 간격 대기 |
| `CACHE_PRUNE_BELOW_GB` | 180 | 배치 종료 정리 때 이 미만이면 `docker builder prune -af` |
| `START_BATCH` / `END_BATCH` | 0 / 끝 | 재개 범위 |
| `KEEP_IMAGES` | (없음) | 1이면 배치 종료 시 태스크 이미지를 지우지 않음 (큰 디스크에 쌓이는 호스트용) |

## 부록 B. v1 참고 수치 (Qwen3.8-Flash-Next, attempts 4, 6배치 192태스크 시점)
pass@1 66.9%, pass@4 83.9%, 0/4 16%, 4/4 43%. 배치(128 롤아웃)당 1h45m~2h25m, 동시 24~32.
