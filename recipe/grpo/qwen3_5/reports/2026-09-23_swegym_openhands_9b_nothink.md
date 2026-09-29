# SWE-Gym × openhands-sdk × Qwen3.5-9B GRPO — run 1 (no-think, AI-DLC 없음)

- 실행: 2026-09-23 05:57 ~ 09-24 07:43 (컨테이너 시각, 약 26시간), H200-9 (8× H200 141 GB), slurm salloc
- wandb: project `qwen3_5-swe-grpo`, run `qwen3_5-9b-openhands-sdk-swegym293` (`1h7hzv5q`)
- 코드: 브랜치 `feat/aidlc-openhands-sdk-recipe`, `recipe/grpo/qwen3_5`, variant `openhands_9b_swegym` (커밋 84555e3d 시점 설정)
- run id: `20260923_055723` (transcript, checkpoint, episode 로그 경로에 공통으로 붙음)

## 1. 요약

| | 값 |
| --- | --- |
| train reward (step 1 → 27) | 0.27 → 0.87 |
| validation pass@1 (23 task, 학습 전 → 후) | 8/23 (0.35) → 10/23 (0.43) |
| validation 평균 turn | 66 → 54 |
| 학습 안정성 | 27 step 모두 완료, error/OOM 없음, log-prob 일치도(pearson) 0.9965~0.9996 |
| reward hacking 감사 | **git 히스토리 누출 있음**: train episode의 12.6%가 정답 커밋을 `git show`로 읽음. 학습 중 감소(18% → 7%). 길이/turn 증가 없음, 테스트 조작 없음 |

validation 개선은 23개 기준 ±2 task가 노이즈라 **유의미하다고 말하기 어렵다.** train reward 상승에는 3 epoch 반복 학습에 의한 암기가 섞여 있다. 다음 run 전에 이미지의 미래 git 히스토리 제거와 네트워크 차단이 필요하다.

## 2. 실험 세팅

### 2.1 모델·harness·데이터

| 항목 | 설정 |
| --- | --- |
| 정책 | `Qwen/Qwen3.5-9B` (`/vast-ib/MMI/home/kyuminkim/weights/Qwen3.5-9B`), bf16 |
| thinking | **no-think**. `rllm.gateway.renderer_kwargs.enable_thinking=false` 한 키로 turn 1(vLLM chat template, `chat_template_kwargs`)과 turn 2+(gateway `qwen3.6` renderer)를 함께 제어. episode 로그에서 reasoning 0건 확인 |
| agent | openhands-sdk 1.42.1 (`StepLimitedOpenHandsSdk`), tool: terminal / file_editor / task_tracker, condenser 없음, SDK 기본 system prompt |
| agent 이미지 | `rllm-agent-a085c9c81fef` (uv + Python 3.12 + SDK venv), 모든 task 컨테이너에 `/opt/rllm/agent` read-only 마운트 |
| train 데이터 | SWE-Gym `SkyRL-v0-293-data/train.parquet` 293 instance → `swegym293/train` |
| val 데이터 | `validation.parquet` 23 instance → `swegym_val23/test`. parquet의 `data_source` 라벨은 `swe-gym`이지만 실제로는 **SWE-bench Lite `dev` split 23개 전체**(id 완전 일치; sqlfluff·pvlib·astroid·pydicom·marshmallow·pyvista). train과 repo 미중복. SWE-bench Verified/test 아님 |
| task 이미지 | `xingyaoww/sweb.eval.x86_64.<owner>_s_<repo>-<n>:latest`, `/testbed`, cpu 4 / mem 16 GB per sandbox, `allow_internet=true` |
| instruction | SkyRL-v0 SWE-Gym 프롬프트(`/workspace/<repo>` → `/testbed`) |
| verifier | swegym `eval_script` 재현(`tests/eval.sh`, 원본과 316/316 byte-identical) + `grade.py`. F2P·P2P 전부 통과 시 1.0, 아니면 0.0 |
| reward shaping | SWE-Master: turn/context/agent-timeout으로 끝난 rollout은 채점 후 ×0.5(`budget_reward_scale`), verifier timeout/error는 drop |

### 2.2 GRPO / verl

| 항목 | 설정 |
| --- | --- |
| batch | 32 task × 4 rollout = 128 trajectory / step, 9 step / epoch, **3 epoch = 27 step** |
| advantage | RLOO, std 정규화 없음, clip-higher 0.28, KL 0(reference worker 없음), `seq-mean-token-sum` |
| update | `ppo_mini_batch_size=32` × 4 = 128 → step당 optimizer update 1회(on-policy), lr 1e-6, micro-batch 1 sequence |
| context | `max_prompt_length` 16384 + `max_response_length` 114688 = `max_model_len` **131072** |
| turn 예산 | `OPENHANDS_MAX_ITERATIONS` = 80 (`agent_step_limit`) |
| sampling | train T=1.0 top_p 0.95, val T=0.6 top_p 0.9, per-turn max_tokens 8192, val 1 rollout/task |
| actor | **FSDP1** (`strategy: fsdp`; untied lm_head + verl #7520 회피), fused kernels(torch) + remove_padding, gradient checkpointing, param/optim offload, flash-linear-attention 0.5.2 + verl PR #6660 backport |
| rollout | vLLM 0.22.1 async, tp 1(GPU당 서버 1), `gpu_memory_utilization` 0.5, `reasoning_parser=qwen3`, `tool_call_parser=qwen3_xml` |
| gateway | cumulative token mode(turn N+1 prompt = turn N의 raw token id 확장), renderer `qwen3.6` + `preserve_thinking` |
| sandbox | docker, 32개 동시(`sandbox_concurrency`, `n_parallel_tasks`), agent timeout 3600 s, verifier timeout 1800 s |
| validation | step 0 + 3 step마다 + 학습 종료 후 1회 |
| checkpoint | 매 step, 삭제 없음 (27개 × 106 GB = 2.8 TB) |

### 2.3 인프라

- H200-9 driver 550(CUDA 12.4) vs 학습 스택 CUDA 13(torch 2.11.0+cu130, vLLM cu13): 컨테이너 `pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel`에 `cuda-compat-13-0` 설치 + `LD_LIBRARY_PATH=/usr/local/cuda-13.0/compat` (driver API 13000)
- venv `/data/MMI/kyuminkim/venvs/rllm`(노드 로컬), `RLLM_HOME=/data/.../rllm-home`(데이터셋), checkpoint·episode는 `RLLM_ARTIFACT_DIR=/vast-ib/MMI/home/kyuminkim/rllm-artifacts`

```bash
python recipe/grpo/qwen3_5/scripts/prepare_swegym.py --parquet-dir /vast-ib/MMI/home/kyuminkim/datasets/swe/SkyRL-v0-293-data
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_swegym
```

### 2.4 사전 검증(스모크 2회)에서 고친 것

1. openhands-sdk 첫 turn은 task 텍스트 전에 약 7.4K 토큰(system prompt + tool schema + 환경 정보)이라 기본 `max_prompt_length` 8192를 넘었고, transform이 **에러 없이 왼쪽을 잘라** 학습했다(pearson 0.9907). → 16384로 상향, clip 0, pearson 0.9986.
2. context 초과 시 vLLM 400 → step을 기록하지 않는 CLI harness에서는 `EnrichMismatchError`로 3회 재시도 후 error drop. → 엔진이 꼬리 malformed trace를 버리고 `MAX_PROMPT_LENGTH_EXCEEDED`로 채점(reward ×0.5)하도록 수정.
3. pydantic task에서 `/testbed/pydantic`이 SDK의 pydantic 의존성을 가려 agent 이미지 probe가 실패 → probe에 `PYTHONSAFEPATH=1`.
4. `[verifier] module`이 `task_path` 행에서 무시되던 코어 버그 수정(hybrid reward용 seam).

## 3. 결과

### 3.1 학습 곡선 (train, step당 128 rollout)

| step | reward | solve none / partial / all (task 비율) | 평균 turn | env_done / turn 초과 / ctx 초과 | pearson | step 시간 | peak mem/GPU |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.27 | 0.22 / 0.72 / 0.06 | 61 | 0.54 / 0.45 / 0.00 | 0.9988 | 44분 | 69 GB |
| 3 | 0.51 | 0.06 / 0.50 / 0.44 | 69 | 0.44 / 0.56 / 0.00 | 0.9996 | 46분 | 78 GB |
| 6 | 0.61 | 0.00 / 0.38 / 0.62 | 76 | 0.34 / 0.66 / 0.00 | 0.9989 | 59분 | 91 GB |
| 9 | 0.59 | 0.06 / 0.25 / 0.69 | 72 | 0.45 / 0.55 / 0.00 | 0.9989 | 59분 | 91 GB |
| 12 | 0.71 | 0.00 / 0.38 / 0.62 | 68 | 0.61 / 0.36 / 0.03 | 0.9981 | 40분 | 91 GB |
| 15 | 0.77 | 0.00 / 0.31 / 0.69 | 65 | 0.75 / 0.25 / 0.00 | 0.9965 | 50분 | 91 GB |
| 18 | 0.75 | 0.03 / 0.31 / 0.66 | 63 | 0.73 / 0.27 / 0.00 | 0.9987 | 50분 | 91 GB |
| 21 | 0.79 | 0.09 / 0.19 / 0.72 | 59 | 0.84 / 0.16 / 0.00 | 0.9989 | 37분 | 91 GB |
| 24 | 0.88 | 0.03 / 0.16 / 0.81 | 59 | 0.88 / 0.12 / 0.00 | 0.9983 | 38분 | 91 GB |
| 27 | 0.87 | 0.06 / 0.12 / 0.81 | 54 | 0.93 / 0.07 / 0.00 | 0.9975 | 60분 | 91 GB |

- error termination 0(step 1의 1%뿐), context 초과 최대 3%.
- 27 step 전체 시간 약 25시간 + validation 11회. step당 update_actor 4~6.5분, 나머지는 rollout.
- 같은 293 task를 3번 보므로 epoch 1(step 10~)부터의 상승은 암기 성분을 포함한다.

### 3.2 길이·엔트로피 추이

| step | turn당 생성 token | episode token(평균) | entropy |
| --- | --- | --- | --- |
| 1 | 176 | 43K | 2435 |
| 6 | 217 | 57K | 2398 |
| 15 | 240 | 56K | 1566 |
| 27 | 255 | 51K | 2222 |

turn 수는 step 6까지 늘고 이후 감소, turn당 token은 완만히 증가. 단조 증가하는 길이 지표는 없다.

### 3.3 Validation (23 task, 1 rollout/task, T=0.6)

| step | 0 | 3 | 6 | 9 | 12 | 15 | 18 | 21 | 24 | 27 | 종료 후 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pass@1 | .35 | .35 | .43 | .35 | .35 | .30 | .30 | .35 | .30 | .39 | **.43** |
| 평균 turn | 66 | 75 | 75 | 77 | 76 | 70 | 66 | 68 | 61 | 56 | 54 |

- wandb 키: `val/unknown/pass@1`(= accuracy, `is_correct` 평균), `val/reward/openhands-sdk/mean`(budget scaling 적용). `unknown`은 row에 `data_source` 필드가 없어 붙은 이름.
- step 27 validation과 종료 후 validation은 **같은 weight**로 두 번 샘플링한 것이다(9/23 vs 10/23, task 5개가 뒤집힘). 즉 ±2 task는 샘플링 노이즈.
- 학습 전 8/23 → 후 9~10/23. 개선 방향은 맞지만 유의미하다고 보기 어렵다. turn 감소(66 → 54)는 일관된 변화.

### 3.4 산출물

| | 경로 |
| --- | --- |
| transcript | `<repo>/outputs/logs/train_20260923_055723.log` |
| checkpoint (FSDP shard) | `/vast-ib/MMI/home/kyuminkim/rllm-artifacts/checkpoints/qwen3_5-swe-grpo/qwen3_5-9b-openhands-sdk-swegym293/20260923_055723/global_step_{1..27}/` |
| step 27 HF 변환본 | `/vast-ib/MMI/home/kyuminkim/rllm-artifacts/hf/qwen3_5-9b-openhands-sdk-swegym293-step27/` (18 GB, bf16; verl merger가 vision tower를 `model.language_model.visual.*`로 저장한 것을 `model.visual.*`로 복원, `mtp.*` 15개는 제외. **vLLM 로드는 아직 미검증**) |
| episode 로그 | `/vast-ib/MMI/home/kyuminkim/rllm-artifacts/episodes/qwen3_5-swe-grpo/qwen3_5-9b-openhands-sdk-swegym293/20260923_055723/episodes/` (31 GB, train 27 step + val 11회) |
| reward hacking 감사 | `<repo>/outputs/reward_hack_audit/` (`scan.py`, `refine.py`, `summary.txt`, `refined.json`) |

## 4. Reward hacking 감사

3,709 episode(train 3,456 + val 253)의 모든 tool call을 스캔했다.

### 4.1 git 히스토리 누출 — 있음

`xingyaoww` 이미지는 `/testbed`를 base_commit에 checkout했을 뿐 `.git`에는 **이후 커밋과 태그가 그대로** 있다. `git log --all`을 치면 정답 커밋이 보이고(커밋 메시지에 PR 번호 포함), `git show <sha>`가 gold patch를 그대로 돌려준다.

| | episode |
| --- | --- |
| `git log --all` / `branch -a`로 base 이후 커밋을 본 | 887 / 3,709 |
| 그중 정답 커밋을 `git show`(gold patch 50%+ 노출) | 444 |
| train: 정답 커밋을 읽은 episode | 436 / 3,456 (12.6%), 156 task |

| epoch | solved rate | 누출 episode | solved 중 누출 | 누출 제외 solved rate |
| --- | --- | --- | --- | --- |
| 0 | 0.74 | 18.3% | 20.7% | 0.41(step 1) → 0.79(step 9) |
| 1 | 0.86 | 12.2% | 13.0% | ~0.85 |
| 2 | 0.89 | 7.4% | 7.5% | ~0.89 |

정책이 hack을 학습한 것은 아니다(비율이 계속 감소). 누출을 제외해도 train reward 상승은 유지된다. 다만 학습 신호의 약 14%가 오염됐고, validation도 라운드마다 0~5 episode가 누출을 봤다(마지막 두 라운드 0~1). SkyRL-v0도 같은 이미지로 학습했으므로 같은 조건이다.

### 4.2 네트워크 — 경미

`allow_internet=true`라 curl이 가능했다. 46 episode / 98회, 대부분 mypy·MONAI task가 외부 예제 코드를 받은 것. 1건(conan-14795, step 2)이 upstream `develop` 브랜치의 수정된 파일을 curl로 받아 gold patch와 100% 겹쳤으나 그 episode는 실패했다.

### 4.3 테스트 조작 — 없음

- `/tests`, `/solution`, `/logs`, `eval.sh`, `gold.patch` 접근 0건(verifier 파일은 평가 시점에만 업로드됨).
- conftest / pytest.ini / sitecustomize 조작 0건.
- repo 기존 테스트 파일 편집 106 episode(solve 92% vs 전체 80%)는 eval.sh가 test patch 대상 파일을 base_commit으로 되돌린 뒤 gold test를 적용하므로 채점에 영향 없음.

## 5. 한계와 다음 단계

1. **이미지 히스토리 정리**: sandbox 시작 시 HEAD 외 ref 삭제 + `git reflog expire` + `git gc --prune=now`, 또는 정리된 이미지를 다시 굽기. `prepare_swegym.py`의 task.toml `setup_commands`로 넣을 수 있음.
2. **`allow_internet=false`**. verifier의 `pip install -e .`가 네트워크를 쓰는 repo가 있는지 확인 후.
3. **평가 세트 확대**: 23개로는 ±9%p 노이즈. SWE-bench Verified 일부 등에서 base vs step 27 비교. `n_val>1`로 분산 축소.
4. 1~2 적용 후 재학습, 그리고 AI-DLC arm(`variant=openhands_9b_aidlc_swegym`)과 hybrid reward(IF eval.py) 실험.
5. step 27 HF 변환본의 vLLM 로드 검증(slurm 할당 안에서).
