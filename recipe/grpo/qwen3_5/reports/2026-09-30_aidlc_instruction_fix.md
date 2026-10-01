# AI-DLC 워크플로우 진입 실패 — 원인, 대응, 전후 비교 (2026-09-30)

대상: `variant=openhands_9b_aidlc_swegym` (Qwen3.5-9B + openhands-sdk + AI-DLC, SWE-Gym 293).
상세 분석은 `2026-09-30_aidlc_swegym_compliance.md`, 코드 변경은 브랜치 `feat/aidlc-openhands-sdk-recipe` working tree(미커밋).

## 1. 문제

run 2(2026-09-29, 21 step, 2,849 episode)에서 `aidlc/compliance` 평균이 **0.020**, episode의 90.7%가 0이었다. rubric 항목의 문제가 아니라 그 앞 단계에서 무너졌다.

| 단계 | episode | 비율 |
| --- | --- | --- |
| `/ai-dlc/core-workflow.md`를 한 번도 열지 않음 | 2,456 | **86.2%** |
| core는 읽었으나 artifact 0개 | 296 | 10.4% |
| stage 문서 5개를 모두 읽음 | 34 | 1.2% (이들의 compliance는 0.85) |

## 2. 원인

모델이 받는 user 메시지는 두 조각이다.

```
<uploaded_files>/testbed</uploaded_files>
I've uploaded a python code repository in the directory /testbed. ...
<issue_description> ... </issue_description>
...
Follow these steps to resolve the issue:
1. EXPLORATION: First, thoroughly explore the repository structure using tools like `find` and `grep`.
2. ANALYSIS ...  3. TEST CREATION ...  4. IMPLEMENTATION ...  5. VERIFICATION ...
6. FINAL REVIEW: ... compare your changes with the base commit <sha>.
Be thorough in your exploration, testing, and reasoning. ...
                                                   ← 여기까지 task instruction (SkyRL-v0가 쓴 OpenHands SWE-bench 프롬프트)
Follow the workflow defined in /ai-dlc/core-workflow.md.
Read /ai-dlc/core-workflow.md first. ...            ← AI-DLC 지시 4줄 (suffix)
```

1. **경쟁하는 절차.** task instruction 전체(6단계 포함)는 OpenHands의 SWE-bench 평가 프롬프트(`evaluation/benchmarks/swe_bench/run_infer.py` `get_instruction`, 0.15~0.30 확인)이고, SkyRL-v0 코드(`verl/workers/agentic/utils.py`, 커밋 `a0d50c48`)가 이를 byte 단위로 그대로 가져와 rollout 때 붙이던 것이다. 6단계는 OpenHands가 자기 에이전트용으로 쓴 절차로, AI-DLC의 5 stage와 같은 일을 더 구체적으로 지시한다. 모델은 이슈 바로 아래에 있는 이 절차를 따라 "Let's start by exploring the repository"로 시작하고, 맨 끝의 4줄은 무시한다. 첫 tool call이 `/testbed` 탐색인 비율 99%.
2. **경로 오해.** 진입한 393개 중 70%는 먼저 repo 안에서 `find . -name "*.md" | grep workflow`를 쳤고, 실패 후 절대경로를 시도해 우연히 진입했다. 비진입 중 약 390개는 `/testbed/ai-dlc/…`를 찾다가 포기했다. SDK system prompt의 "파일 경로를 받으면 먼저 파일 시스템을 탐색해 위치를 찾아라"가 이를 부추긴다.
3. **진입 후 이탈.** 01 rule을 읽은 뒤 Stage 1 작업(탐색·테스트)을 시작하면 SWE-Gym 습관으로 복귀해 artifact를 쓰지 않는다(01 읽은 250개 중 02까지 간 비율 24%).

## 3. 대응

문서(`aidlc/core-workflow.md`, `rule-details/`)는 수정하지 않았다. 프롬프트 배치와 데이터 생성만 바꿨다.

| # | 변경 | 파일 |
| --- | --- | --- |
| 1 | task instruction에서 6단계 절차·마무리 문장·base_commit sha 제거 (`--instruction aidlc`, 데이터셋 `swegym293_aidlc` / `swegym_val23_aidlc`). repo 위치, 테스트 파일 처리됨, 환경 준비됨, non-test 최소 수정은 유지. 2,764자 → 820자 | `scripts/prepare_swegym.py` |
| 2 | AI-DLC 지시를 task 텍스트 **앞**에 배치 (`recipe.aidlc.instruction_position: prefix`, 기본값; 기존 variant는 `suffix`로 고정해 run 2 재현) | `aidlc_flow.py`, `train.py`, `config/config.yaml` |
| 3 | 지시문에 "`/ai-dlc`는 repo 밖 절대경로, repo 안에서 찾지 말 것" 추가 | `aidlc/instruction.md` |
| 4 | 새 variant `openhands_9b_aidlc_swegym_v2`, `…_v2_reward` | `config/variant/` |
| 5 | 검증 도구: 첫 turn 프로브(`scripts/aidlc_entry_probe.py`), `rllm eval`이 `--agent-kwargs`를 받도록 harness 수정, 테스트 5개 추가 | `scripts/`, `eval_harness.py`, `tests/test_aidlc_prompt.py` |

## 4. 전후 비교

정책은 모두 base Qwen3.5-9B(vLLM 0.22.1, no-think, T=1.0, top_p 0.95). 문서는 동일.

### 4.1 첫 turn 프로브 (20 task × 8 sample, 배치당 160회)

| 배치 | core 바로 읽음 | `/ai-dlc` 디렉터리 확인 | 합계 | repo 안에서 검색 |
| --- | --- | --- | --- | --- |
| skyrl + suffix (run 2) | 1.2% | 0.6% | **1.9%** | 4.4% |
| skyrl + prefix (순서만) | 6.9% | 5.0% | 11.9% | 14.4% |
| aidlc + suffix (6단계만 제거) | 26.9% | 19.4% | 46.2% | 13.8% |
| **aidlc + prefix (v2)** | 26.2% | 45.0% | **71.2%** | 6.9% |

6단계 제거가 주 효과, 순서 변경이 그 위에 더해진다. 20 task 전부에서 v2가 앞섰다.

### 4.2 40-turn 전체 rollout (run 2 step 1의 32 task × 4 = 128)

run 2 열은 실제 학습 rollout을 40 turn 시점에서 자른 값.

| | run 2 step 1 (skyrl+suffix) | **v2 (aidlc+prefix)** |
| --- | --- | --- |
| core-workflow.md 읽음 | 13.3% | **90.6%** |
| 01 rule 읽음 | 7.8% | 90.6% |
| 02 / 03 rule 읽음 | 1.6% / 1.6% | 39.1% / 35.2% |
| artifact 1 / 2 / 3 작성 | 1.6% / 1.6% / 1.6% | **45.3%** / 43.0% / 39.8% |
| artifact 1 작성 ｜ 01 읽음 | 10.0% | 50.0% |
| core 첫 읽기 turn (중앙값) | 5 | 2 |
| verifier 정답 | 0.35 (100 turn) | 0.43 (40 turn) |
| compliance 평균 | 0.018 (100 turn) | 0.247 (40 turn, S4·S5 미도달이라 하한) |

- 32 task 모두에서 진입 rollout이 나왔다. artifact 품질은 S1 band 8이 54/58, S2 44/55, S3 40/51.
- 남은 병목은 Stage 1 → artifact 1(01 읽은 116개 중 58개). 못 쓴 58개 중 27개는 artifact 없이 소스 수정을 시작, 22개는 탐색만 하다 40 turn 종료, 8개는 t35 이후 작성으로 상한에 걸렸다.

## 5. 다음 run

```bash
set -a; source recipe/grpo/qwen3_5/.env; set +a
python recipe/grpo/qwen3_5/scripts/prepare_swegym.py --parquet-dir /opt/dlami/nvme/work/datasets/SkyRL-v0-293-data --instruction aidlc
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc_swegym_v2          # compliance 로그만
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc_swegym_v2_reward   # + reward (mul)
```

step 1의 `aidlc/docs_read`, `aidlc/artifacts_written`, `aidlc/compliance`를 run 2 step 1(0.13 / 0.16 / 0.018)과 비교한다. 참고로 run 2 배치 그대로 돌린 reward run(`…-aidlc-reward-swegym293`, mul)도 6 step 만에 compliance 0.017 → 0.278로 올랐으므로, v2에서는 시작점이 높은 만큼 더 빨리 수렴할 것으로 본다.

## 6. 원자료

- run 2 분석: `outputs/aidlc_compliance_audit/facts_20260929_084716.jsonl`, `extract.py`, `agg.py`
- 첫 turn 프로브: `outputs/aidlc_compliance_audit/probe_base_qwen3.5-9b.jsonl`
- 40-turn rollout: `outputs/aidlc_compliance_audit/eval_step1_aidlc_prefix_40t/`, `compare_step1.py`
- 프롬프트 원본: OpenHands `evaluation/benchmarks/swe_bench/run_infer.py` (0.30.0에서 대조); SkyRL-v0 사본은 NovaSky-AI/SkyRL 커밋 `a0d50c482436af7fac8caffa4533616a78431d66`, `verl/workers/agentic/utils.py` (두 블록 동일)
