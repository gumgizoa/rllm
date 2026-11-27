# 계획 전 재현 penalty 학습: 인계

2026-11-27. 학습 서버에서 이 실험을 돌리는 사람(또는 Claude)에게 넘기는 문서입니다. 배경은 `12-plan-edit-stage-20261126.md`,
직전 평가 결과는 `14-repro-resut.md`, 항목의 정의는 `workflows/speckit_bug_repro/CHANGES.md`의 "penalty 항목" 절에 있습니다.

## 1. 무엇을 하는 실험인가

- workflow를 `speckit_bug`에서 `speckit_bug_repro`로 바꿔 학습합니다. assess 단계가 remediation을 제안하기 전에 이슈의 증상을
  실제로 실행해 보게 한 변형입니다.
- reward 식과 weight는 이전 pen03 run과 같습니다.
  `reward = 0.7 * verifier * (0.7 + 0.3 * compliance) + 0.3 * speckit_bug/penalty`
- 달라지는 것은 `speckit_bug/penalty`의 구성입니다. 기존 3개 항목에 "계획 전에 저장소 코드를 실행했는가"가 더해져 4개의
  평균이 됩니다 (항목당 0.25, reward의 0.075).
- 새 항목의 signal 이름: `speckit_bug/assess.penalty.reproduction.before_remediation`

## 2. 코드

```bash
git fetch origin && git checkout feat/repro-penalty
```

이 브랜치는 `feat/repro-before-plan-variants` 위에 커밋 하나(항목, 테스트, 학습 설정)와 이 문서를 얹은 것입니다.

## 3. 돌릴 것

순서대로입니다. 1번과 2번은 GPU가 필요 없습니다.

### 3-1. 테스트 (1분)

```bash
python -m pytest recipe/grpo/qwen3_5/tests/test_repro_penalty.py recipe/grpo/qwen3_5/tests/test_repro_variants.py \
    recipe/grpo/qwen3_5/tests/test_speckit_bug_penalty.py -q
```

### 3-2. 직전 평가를 새 항목으로 다시 채점 (선택, 몇 분)

`14-repro-resut.md`의 재현 비율(78.6%)은 다른 정의로 센 것입니다. 이 서버에 있는 그 평가의 episode를 새 항목으로 다시
채점하면, 학습 시작 시점의 모델이 이 항목을 얼마나 지키는지 알 수 있습니다. chunk 디렉터리마다 프로세스 하나씩 병렬로 돕니다.

```bash
export PYTHONPATH=$PWD
R=$RLLM_HOME/eval_results/swebench_verified_all_speckit-pen03-fmtcut-step27_speckit_bug_repro_20261127_025343
ls -d ${R}_s*_c*/episodes | xargs -P 24 -I{} sh -c \
    'python recipe/grpo/qwen3_5/scripts/rescore_compliance.py {} --out {}/../rescore_penalty.jsonl > /dev/null'
python - <<'EOF'
import glob, json, os
R = os.environ["RLLM_HOME"] + "/eval_results/swebench_verified_all_speckit-pen03-fmtcut-step27_speckit_bug_repro_20261127_025343"
K = "speckit_bug/assess.penalty.reproduction.before_remediation"
rows = [json.loads(l) for f in glob.glob(R + "_s*_c*/rescore_penalty.jsonl") for l in open(f)]
s = [r["signals"] for r in rows if "signals" in r]
print("episodes", len(rows), "scored", len(s))
print("reproduction item  %.3f" % (sum(x.get(K, 0.0) for x in s) / len(s)))
print("penalty (offline)  %.3f" % (sum(x.get("speckit_bug/penalty", 0.0) for x in s) / len(s)))
for flag in (1.0, 0.0):
    g = [r for r in rows if "signals" in r and r["signals"].get(K, 0.0) == flag]
    print("item = %d: n = %d, resolve %.1f%%" % (flag, len(g), 100 * sum(bool(r["is_correct"]) for r in g) / max(1, len(g))))
EOF
```

오프라인 채점에서는 `related_test_run` 항목이 판정 불가라 평균에서 빠집니다. 그래서 여기의 `penalty`는 3개 항목의 평균이고,
학습 중의 값(4개 평균)과 직접 비교할 수 없습니다. 새 항목의 값 자체는 같습니다.

### 3-3. 학습

```bash
bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_speckit_repro_swegym_reward_floor_penalty_fmtcut \
    rllm.workflow.n_parallel_tasks=64 recipe.sandbox_concurrency=64 trainer.max_actor_ckpt_to_keep=5
```

- 준비물(.env, SWE-Gym 293 dataset, verl patch, 이미지)은 이전 pen03 run(`openhands_9b_speckit_swegym_reward_floor_penalty_fmtcut`)과
  같습니다. 새 설정 파일은 그 설정을 상속하고 workflow 이름과 experiment 이름만 바꿉니다.
- experiment 이름: `qwen3_5-9b-openhands-sdk-think-swegym293-speckit-repro-floor07-pen03-fmtcut-topp1`
- 어느 checkpoint에서 시작할지는 설정에 넣지 않았습니다. 이전 run과 같은 방식(같은 `MODEL_PATH`)이면 그대로 두면 됩니다.

## 4. 첫 step에서 반드시 확인할 것

live 학습 경로는 이 브랜치에서 돌려 보지 못했습니다 (hydra compose 미실행, 이 서버에 verl 없음). 첫 train step의 rollout이
저장되면 아래를 확인합니다.

```bash
# <run dir>: 학습 run의 episode 디렉터리가 있는 곳 (.../<experiment 이름>/<시작 시각>/episodes)
python - "<run dir>/episodes/train_step_1_epoch_0" <<'EOF'
import glob, json, sys
D = sys.argv[1]
K = ["speckit_bug/assess.penalty.reproduction.before_remediation", "speckit_bug/penalty", "speckit_bug/penalty_unavailable",
     "speckit_bug/engine_errors", "speckit_bug/compliance"]
vals = {k: [] for k in K}
for f in glob.glob(D + "/episode_*.json"):
    r = json.load(open(f))
    sig = dict(r.get("metrics") or {})
    for t in r.get("trajectories") or []:
        sig.update(t.get("signals") or {})
    for k in K:
        if k in sig:
            vals[k].append(float(sig[k]))
for k, v in vals.items():
    print("%-62s n=%4d  mean=%s" % (k, len(v), "%.3f" % (sum(v) / len(v)) if v else "MISSING"))
EOF
```

- 새 항목의 signal이 **모든 rollout에 있어야** 합니다. `MISSING`이면 workflow가 `speckit_bug_repro`로 잡히지 않은 것입니다.
- `engine_errors`는 0이어야 합니다. 0이 아니면 새 채점 함수가 예외를 낸 것이고, 그 rollout의 compliance는 0으로 들어갑니다.
- `penalty_unavailable`은 gold 표에 없는 task에서만 1입니다. 대부분 0이어야 합니다.

## 5. 학습 중 볼 것

- 새 항목의 평균. 기준선: 이전 run의 학습 rollout(원본 `speckit_bug`, 2,302건 표본)을 이 항목으로 채점하면 53.2%였습니다.
  변형 문서는 재현을 지시하므로 시작값은 이보다 높을 것입니다 (3-2의 결과가 그 값입니다).
- 저장소별 차이가 큽니다. 같은 표본에서 pandas 82%, dask 82%, pydantic 84%, MONAI 50%, mypy 48%, moto 39%, dvc 21%, conan 5%,
  bokeh 0%(17건)였습니다. 0으로 판정된 것 35건을 읽었는데 모두 계획 전에 저장소 코드를 실행하지 않은 경우였습니다.
- 이 차이는 실행 환경 문제가 아닙니다. 계획 전에 0이던 rollout도 계획 뒤에는 98~100%가 같은 sandbox에서 저장소 코드를
  실행했고, conan·bokeh·moto의 0 판정은 거의 전부 계획 전에 실행을 시도조차 하지 않은 경우였습니다. 갈리는 것은 이슈 본문에
  바로 돌릴 예제가 있는가입니다: 본문에 저장소 패키지를 import하는 코드가 있으면 85.2%, 명령행 한 줄만 있으면 60.6%, 둘 다
  없으면 31.9% (rollout 기준, 계획 문서가 있는 2,126건). conan·dvc·mypy는 본문에 python 예제가 0~8%뿐입니다.
  따라서 이 항목이 올릴 수 있는 부분은 "본문에 예제가 없는 이슈"이고, 거기서 모델이 직접 짧은 호출을 써서 돌리는지가 볼 점입니다.
- resolve와 compliance가 이전 pen03 run의 같은 step과 비교해 떨어지지 않는지.
- 항목이 싸게 채워지는지. `python -c "import pandas; print(1)"`처럼 저장소를 import하고 아무 문장이나 있으면 통과합니다.
  항목 평균이 빨리 1에 붙으면 rollout 몇 개의 계획 전 명령을 직접 읽어 보는 것이 좋습니다.

## 6. 항목 정의 요약

`assessment.md`의 쓰기 중 `## Proposed Remediation`에 내용이 들어간 첫 쓰기를 계획 시점으로 봅니다 (없으면 첫 쓰기).
그 step보다 앞에서 아래 중 하나가 있으면 1, 없으면 0, `assessment.md`가 없으면 0입니다.

1. 유효 테스트 실행 (기존 penalty와 같은 규칙)
2. run이 만든 파일 실행
3. 저장소 패키지를 import하고 import·조회 외의 문장이 있는 inline python
4. 저장소 자체의 명령행 (`python -m mypy x.py`, `dvc ...` 등. `--help`, `--version` 제외)

이슈 본문의 식별자가 실행 코드에 있어야 한다는 조건(`issue_terms`)은 구현돼 있고 꺼져 있습니다. 켜려면
`workflows/speckit_bug_repro/reward/items.yaml`의 `issue_terms: true`입니다.

## 7. 확인되지 않은 것

- hydra compose와 verl 학습 경로 (4절로 확인)
- 검증 수치는 커밋되지 않은 `workflow_rubric/evidence.py` 수정이 있는 작업 트리에서 잰 것입니다. 그 수정은 유효 테스트 판정에만
  영향을 주고, 1로 판정된 것 중 7% 미만이 유효 테스트로 판정된 경우입니다. 이 브랜치에는 그 수정이 없습니다.
