# swe_rl_v1 롤아웃 재시작 명세 - 하드닝된 채점기(swe_rl_v1_1) 적용

대상 호스트: raid-mmi (컨테이너 `rllm-synoh`, `RLLM_HOME=/raid/mmi/sy.noh/rllm-work/rllm-home`)
대상 데이터: swe_rl_v1 1,471건 -> oracle 통과 1,440건
모델/하네스: Qwen3.8-Flash-Next-FP8 + openhands-sdk(native), `--hide-git-history`

---

## 1. 왜 다시 도는가

기존 `rollout4_v1`(7배치, 896 롤아웃 완료)은 **구멍 있는 채점기**로 채점됐다.

SWE-Factory가 만든 `run_tests.sh` 는 test patch 적용 전 정리가 불완전하다.

| 상태 | v1 1,471건 실측 |
| --- | --- |
| 수정 대상 파일을 `git checkout <base> -- <paths>` 로 복원 | 1,454 (98.8%) |
| 복원 목록이 불완전 (일부 파일 누락) | 17 (1.2%) |
| test patch가 **새 파일을 만드는** 태스크 | 251 (17.1%) |
| 그 새 파일을 지우는 처리(`rm` / `git clean` / `git reset --hard`)가 있는 태스크 | **0** |

새 파일은 base 에 없으므로 `git checkout` 의 대상이 될 수 없다. 그래서 에이전트가 그 경로에 파일을
미리 만들어 두면 아무도 지우지 않고, `git apply` 가 "already exists" 로 실패하는데 스크립트에
`set -e` 가 없어 그대로 진행해 **에이전트가 쓴 테스트로 채점**된다.

**oracle 로는 이 구멍이 드러나지 않는다.** gold patch 는 소스만 바꾸고 테스트 파일은 건드리지 않으므로
test patch 가 깨끗이 적용된다. oracle 97.9% 통과와 무관하게 구멍은 그대로 있었다.

**이미 돈 롤아웃은 재채점할 수 없다.** 채점 직후 샌드박스가 삭제돼 에이전트가 남긴 파일 상태가 없다.
`rollout4_v1` 896 롤아웃 중 몇 개가 가짜 성공인지 사후에 알 방법이 없으므로 폐기하고 다시 돈다.
(별도 측정에서는 성공 롤아웃의 3~4%가 가짜였다.)

## 2. 무엇이 바뀌고 무엇이 그대로인가

에이전트의 동작, 프롬프트, 실행되는 테스트 범위, 리소스 설정은 **전부 그대로**다.
바뀌는 것은 에이전트가 끝난 뒤의 채점 순간뿐이다.

```
/tests/test.sh
  [1] restore_test_targets.sh        <- 추가
      test patch가 건드리는 경로마다 런타임 판정:
        untracked    -> rm -rf                       (에이전트가 만든 파일/디렉터리)
        base에 있음  -> git checkout <base> -- path  (에이전트 수정 되돌림)
        base에 없음  -> rm -rf                       (새로 생길 파일 자리 비우기)
      실패 -> reward 0, reason=test_target_restore_failed
  [2] git apply --check tests/test.patch   <- 추가
      실패 -> reward 0, reason=test_patch_apply_failed  (테스트를 돌리지 않음)
  [3] run_tests.sh                   <- SWE-Factory 원본, 한 줄도 안 바꿈
```

롤아웃 1회 기준 결과가 달라지는 경우:

| 에이전트가 한 일 | 기존 | 새 채점기 |
| --- | --- | --- |
| 소스만 고침 (대부분) | 정답 테스트로 채점 | 동일 ([1][2]가 no-op) |
| 기존 테스트 파일 수정 | 대부분 이미 복원됨 | 동일 + 누락 17건도 복원 |
| **새 테스트 파일 선생성** | 에이전트 테스트로 채점 -> **reward 1** | 정답 테스트로 채점 -> reward 0 |
| 복원 후에도 patch 적용 불가 | 조용히 진행 | reward 0 + 사유 기록 |

점수는 사실상 **1 -> 0 한 방향**으로만 움직인다. 없던 성공이 생기지는 않는다.

## 3. 준비 상태 (2026-10-16 기준)

| 항목 | 상태 |
| --- | --- |
| `prepare_swe_rl.py` 하드닝 (복원 스크립트 생성 + test.sh 2단계) | 완료 |
| 단위 테스트 `test_prepare_swe_rl.py` (분류/인용/런타임 분기/실제 패치 300건) | 6개 통과 |
| 데이터셋 `swe_rl_v1_1` 1,471건 생성·등록 | 완료 |
| 속이기 시험 표본 6건 (B/C1/C2, 신·구 채점기 비교) | 완료, 결과는 4장 |
| B 부분집합 oracle 252건 | 미완 (디스크 사고로 중단, 1청크 8/8 통과) |
| C1/C2 표본 90건 (언어별 30) | 미완 (3/90, 중단) |
| `swe_rl_v1_1_ok` 등록 | 대기 |
| 롤아웃 재시작 | 대기 |
| v2 차집합 번들 (9B 서버용) 갱신 | 완료 (sha256 `2ed037fd...`) |

## 4. 지금까지의 검증 결과

표본 6건 (python 2, go 2, js 2 / 새 파일 유·무 섞음). 정답 소스는 적용하지 않고 테스트만 조작.

| 태스크 | 시험 | 기존 채점기 | 새 채점기 |
| --- | --- | --- | --- |
| xarray-spatial-2475 | C2 새 테스트 파일 선생성 | **1.0** | 0.0 |
| stylelint-8669 | C2 새 테스트 파일 선생성 | **1.0** | 0.0 |
| kin-openapi-1250 | C1 / C2 | 0.0 (채점 불가) | 0.0 |
| Gymnasium-1672, cel-go-525, mirador-4481 | C1 기존 테스트 덮어쓰기 | 0.0 | 0.0 |

B(정답 -> 1, 무변경 -> 0)와 반복 실행은 6건 모두 기대대로, 플레이크 0.

## 5. 실행 순서

호스트 루트 디스크를 다른 사용자와 공유하고, 우리 가용분이 ~100-230G 뿐이다.
**아래 단계는 하나씩 돌린다.** (동시 실행으로 루트를 0G 까지 채운 사고가 있었다.)

### 5.0 전제 확인

```bash
df --output=avail -BG / | tail -1                 # 160G 이상 권장
docker ps --format '{{.Image}}' | grep -c '^rllm-task'   # 0 이어야 함
docker exec rllm-synoh pgrep -fc 'rllm eval'             # 0 이어야 함
```
디스크 가드는 호스트에서 상시 1개만:
`MIN_FREE_GB=100 CACHE_PRUNE_BELOW_GB=100 MIN_AGE_MIN=30 IDLE_IMAGE_MIN_AGE_MIN=20 INTERVAL=120 nohup bash recipe/eval/swe-rl/disk_guard_rllm.sh watch >> /raid/mmi/sy.noh/rllm-work/disk_guard.log 2>&1 &`

### 5.1 B 검증 - 하드닝이 정답 채점을 깨지 않는지 (예상 6~10시간)

하드닝 영향이 있는 252건(경로 없는 checkout 74 ∪ 새 파일 생성 251)만 `swe_rl_v1_1` 로 oracle 을 돌린다.
전수 1,471건을 다시 돌리지 않는 근거: 나머지 1,219건은 [1][2]가 no-op 이고 `run_tests.sh` 는 동일하다.

```bash
docker exec -d rllm-synoh bash -c 'bash /raid/mmi/sy.noh/rllm-work/run_b_subset.sh > /raid/mmi/sy.noh/rllm-work/b_subset.log 2>&1'
# 8개씩 32청크. 진행: tail -f /raid/mmi/sy.noh/rllm-work/b_subset.log
```
판정: 252건 중 기존 oracle(`oracle_v1/oracle_verdicts.jsonl`) 과 결과가 달라진 태스크를 전부 나열하고 원인을 적는다.
- 기존 pass -> 새 fail: 복원/적용 단계가 정당하게 막은 것인지 확인. 정당하면 `_ok` 에서 제외.
- 기존 fail -> 새 pass: 있어서는 안 된다. 나오면 멈추고 보고.

### 5.2 C 검증 - 구멍이 실제로 막혔는지 (예상 4~8시간)

```bash
cat /raid/mmi/sy.noh/rllm-work/cheat_30_ids.txt | xargs -P 2 -I{} \
  bash -c 'bash /raid/mmi/sy.noh/rllm-work/cheat_test.sh {} >> /raid/mmi/sy.noh/rllm-work/cheat_30.log 2>&1'
```
언어별 30건(총 90). 완료 기준: **새 채점기의 C1·C2 가 1점 0건**, 기존 채점기의 1점 비율은 기록(구멍의 직접 증거).

### 5.3 `swe_rl_v1_1_ok` 등록 (5분)

5.1 에서 제외할 태스크가 나오면 그만큼 뺀 목록을 쓴다.

```bash
docker exec rllm-synoh bash -c 'source /raid/mmi/sy.noh/rllm-work/env.sh && \
  python recipe/eval/swe-rl/prepare_swe_rl.py --name swe_rl_v1_1_ok \
    --ids $RLLM_HOME/eval_results/oracle_v1/oracle_pass_ids.txt \
    /raid/mmi/sy.noh/swe-factory/upload/swe_rl_v1/python_680.jsonl \
    /raid/mmi/sy.noh/swe-factory/upload/swe_rl_v1/go_605.jsonl \
    /raid/mmi/sy.noh/swe-factory/upload/swe_rl_v1/javascript_186.jsonl'
# 기대: 1,440 tasks (python 657, go 598, javascript 185)
```

### 5.4 롤아웃 재시작

명령은 기존과 **데이터셋 이름과 런 이름만** 다르다.

```bash
docker exec -d rllm-synoh bash -c 'source /raid/mmi/sy.noh/rllm-work/env.sh && \
  DATASET=swe_rl_v1_1_ok BATCH=16 CONCURRENCY=24 MIN_FREE_GB=120 \
  bash recipe/eval/swe-rl/run_batches.sh rollout4_v1_1 openhands-sdk \
    --attempts 4 --agent-image auto --hide-git-history \
    --base-url http://27.122.136.11:30000/v1 --model Qwen/Qwen3.8-Flash-Next-FP8 \
    --sampling-params @recipe/eval/config/qwen3_8_flash_next.yaml \
  >> /raid/mmi/sy.noh/rllm-work/rollout4_v1_1.out 2>&1'
```
- `BATCH=16`: 32 는 이미지가 60~140GB 까지 가서 이 호스트의 루트 여유를 넘겼다. 16 으로 내린다.
- `attempts`: 4 유지(기존 결정). 8 로 올리면 기간이 2배가 된다. 바꾸려면 여기서 결정한다.
- 90배치. 배치당 1~2.5시간이므로 **5~8일**.
- 중단/재개: `START_BATCH=<번호>`. 완료 배치는 `results.json` 존재로 자동 스킵.
- 러너를 죽일 때 `pkill -f run_batches` 는 자기 셸까지 죽인다. PID 로 죽인다.

### 5.5 집계

```bash
docker exec rllm-synoh bash -c 'source /raid/mmi/sy.noh/rllm-work/env.sh && \
  python recipe/eval/swe-rl/tabulate_attempts.py \
    $RLLM_HOME/eval_results/rollout4_v1_1/batch_*/results.json \
    $RLLM_HOME/eval_results/rollout4_v1_1/retry_*/results.json \
    --dataset swe_rl_v1_1_ok --csv /raid/mmi/sy.noh/rllm-work/rollout4_v1_1_per_task.csv'
```
0/4 ~ 4/4 히스토그램(전체·언어별), pass@1, pass@4, 에러 수, per-task CSV.
`reward.json` 의 `reason` 으로 "채점 불가 0점"(`test_patch_apply_failed`)과 "풀지 못한 0점"(`tests_failed`)을 구분할 수 있다.

## 5.6 다른 노드에서 돌릴 때 (3번 서버: 9B 학습용 롤아웃)

이 호스트(`/raid`)는 로컬 디스크라 다른 노드에서 보이지 않는다. 공유 NAS 번들로 시작한다.

```bash
ls /mnt/nas1/sy.noh/swe_rl_bundle            # 안 보이면 findmnt -t nfs,gpfs 로 마운트 경로 확인
BUNDLE=/mnt/nas1/sy.noh/swe_rl_bundle        # 디렉터리 그대로 써도 되고 tar.gz 를 풀어도 된다
```
`RUNBOOK_v2diff_qwen3_5_9b.md` 의 1~3장(컨테이너 + venv + buildx + env.sh)을 그대로 따르되,
**`RLLM_HOME` 은 그 노드의 로컬 큰 디스크**에 둔다. NFS 에 두면 verifier bind-mount 와 이미지 I/O 가
느리고 락 문제가 난다.

데이터셋은 v1 jsonl 로 만든다(차집합이 아니라 전체).

```bash
python recipe/eval/swe-rl/prepare_swe_rl.py --name swe_rl_v1_1   $BUNDLE/data/v1/python_680.jsonl $BUNDLE/data/v1/go_605.jsonl $BUNDLE/data/v1/javascript_186.jsonl
# 기대: 1,471 tasks (python 680, go 605, javascript 186)

# oracle 통과 목록은 번들에 들어 있다(raid-mmi 에서 2026-10-14 측정, 1,440건).
# 그 노드에서 이미지를 새로 빌드하면 환경이 달라 결과가 다를 수 있으므로 참고용이다.
# 시간이 있으면 oracle 을 다시 돌리고, 아니면 이 목록을 그대로 쓴다.
python recipe/eval/swe-rl/prepare_swe_rl.py --name swe_rl_v1_1_ok   --ids $BUNDLE/data/v1/oracle_pass_ids.txt   $BUNDLE/data/v1/python_680.jsonl $BUNDLE/data/v1/go_605.jsonl $BUNDLE/data/v1/javascript_186.jsonl
```

롤아웃은 모델과 런 이름만 다르다.

```bash
DATASET=swe_rl_v1_1_ok BATCH=16 CONCURRENCY=32 MIN_FREE_GB=160 bash recipe/eval/swe-rl/run_batches.sh rollout4_v1_1_9b openhands-sdk   --attempts 4 --agent-image auto --hide-git-history   --base-url http://27.122.129.140:8222/v1 --model Qwen/Qwen3.5-9B   --sampling-params @recipe/eval/config/qwen3_5.yaml
```
- `--attempts 4`. 성공 궤적 수가 그대로 학습 데이터 양이지만 8 회는 기간이 2배가 된다(아래 표).
- 9B 서버를 2번 서버(v2 차집합)와 공유하므로 동시성 합계가 서버 처리량을 넘지 않게 한다.
  한 단어 프로브가 15초를 넘거나 `/metrics` 의 `vllm:num_requests_waiting` 이 계속 양수면 줄인다.
- 궤적은 `$RLLM_HOME/eval_results/<run>/episodes/*.json` 에 남는다. 학습에 쓰려면 이 디렉터리를
  NAS 로 복사한다(결과 JSON 은 작지만 개수가 많으므로 tar 로 묶는 쪽이 빠르다).

세 서버의 역할이 다르므로 결과를 **합치지 않는다**.

| 서버 | 데이터 | 모델 | 목적 | attempts |
| --- | --- | --- | --- | --- |
| raid-mmi | v1_1 1,440 | Flash-Next | 난이도 분포 측정 (teacher 기준) | 4 |
| 2번 | v2-v1 차집합 740 | Qwen3.5-9B | **학습용** - reward 받는 태스크 선별 + 궤적 | 4 |
| 3번 | v1_1 1,440 | Qwen3.5-9B | **학습용** - 동일 | 4 |

모델과 목적이 다르므로 세 결과를 **합치지 않는다**.

학습용 두 서버는 끝난 뒤 다음을 산출한다.

```bash
# 한 번이라도 푼 태스크(0/4 는 학습 신호가 없어 버린다)
awk -F, 'NR>1 && $4>0 {print $1}' <per_task.csv> > trainable_ids.txt
# 성공 궤적
grep -l '"is_correct": true' $RLLM_HOME/eval_results/<run>/batch_*/episodes/*.json > success_episodes.txt
```
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

**궤적 용량**: v1 실측 평균 11 MB/에피소드(최대 66 MB). 1,440 x 4 = 5,760 에피소드면 **약 65 GB** 다.
`RLLM_HOME` 디스크 여유를 확보하고, 끝나면 tar 로 묶어 NAS 로 옮긴다.

## 6. 폐기 대상 처리

- `rollout4_v1` (7배치, 896 롤아웃): 결과를 학습에 쓰지 않는다. 비교용으로 디렉터리는 남긴다.
  새 결과가 나오면 **같은 태스크에서 기존 1점이 새 0점으로 바뀐 비율**을 세어 구멍의 실제 영향을 보고한다
  (롤아웃마다 에이전트 행동이 달라지므로 엄밀한 비교는 아니지만 규모는 확인된다).
- `_rollout8_v1_aborted` (8회 시도분): 동일하게 폐기.

## 7. 완료 기준

1. B: 252건에서 기존 oracle 과 결과가 다른 태스크가 모두 설명됨. "기존 fail -> 새 pass" 0건.
2. C: 새 채점기의 C1·C2 1점 **0건** (90건 표본). 기존 채점기의 1점 비율이 기록됨.
3. 롤아웃: 90배치 완료, 에러 태스크는 재실행 후 집계에서 대체됨.
4. 실행되는 테스트 명령·범위가 기존과 동일함이 `run_tests.sh` diff 로 확인됨 (현재 0 바이트 차이).

## 8. 주의

- 동시 실행 금지. 검증(5.1/5.2)과 롤아웃(5.4)을 같이 돌리지 않는다.
- 루트 디스크는 공용이다. `docker system prune -a` / `image prune -a` 금지.
- 7일 이상 된 dangling `/testbed` 이미지(우리 swe-factory 잔재)는 정리 완료. 다른 사용자 이미지는 건드리지 않는다.
- Dockerfile 핀이 없어 시간이 지나면 빌드가 깨지는 태스크가 있다(`@latest`, 핀 없는 pytest/pyarrow/uv).
  oracle 통과 후에도 롤아웃에서 빌드 실패가 날 수 있고, 이는 재실행으로 복구되지 않는다. 제외 처리한다.
