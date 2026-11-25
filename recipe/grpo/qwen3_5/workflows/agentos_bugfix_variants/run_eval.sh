#!/bin/bash
# agentos_bugfix 지침 변형(또는 agentos_bugfix, none) 추론 평가. 2026-11 wf1121 평가(eval_results/wf1121_traj/eval/*/run_eval.sh)와
# 같은 설정: SWE-bench Verified 499 과제, step_limit 250, thinking on, instruction suffix, FinishTool 만 기본 도구, strict_tool_calls,
# --hide-git-history, --no-agent-network, --verify-network, sampling = recipe/eval/config/qwen3_5.yaml, 과제 i -> shard i % (endpoint 수).
# 모델은 다른 서버에 떠 있다고 보고 OpenAI 호환 endpoint 주소만 받는다. endpoint 하나에 shard 하나.
#
# usage: run_eval.sh <workflow> <run key> <served-model-name> <base-url[,base-url...]> [attempts=3] [task_indices]
#   workflow         agentos_bugfix_v0base | _v1result | _v2place | _v3pre | _v4docs | _v5all | _v2fplace (문장 변형)
#                    agentos_bugfix_s1report | _s2after | _s3tasks | _s4prompt (구조 변형) | agentos_bugfix_p1nofix (3차)
#                    agentos_bugfix (대조) | none (워크플로 없음)
#   run key          결과 폴더 이름에 붙는 모델 표시 (예: base, step27)
#   base-url         http://host:port/v1 형태. 쉼표로 여러 개 주면 그 수만큼 shard 로 나눠 동시에 돈다
#   task_indices     주면 그 과제만 첫 endpoint 로 돈다 (smoke 용, 예: 0,1,2). 결과 폴더 이름에 -smoke 가 붙는다
#                    결과 폴더 이름에는 과제 목록이 들어가지 않는다. 과제 목록이 다른 smoke 는 run key 를 달리한다
# 환경변수 (모두 선택):
#   RLLM_HOME  데이터셋(datasets/swebench_verified_all)과 결과가 놓이는 곳. 기본 ~/.rllm
#   REPO       코드 위치. 기본 이 스크립트가 든 저장소
#   PY         파이썬 실행 파일. 기본 $REPO/.venv/bin/python (같은 폴더의 rllm 명령을 씀)
#   CONC       endpoint 당 동시 실행 수. 기본 24
# 첫 실행 주의: 에이전트 이미지(rllm-agent-<hash>)가 없는 장비에서 여러 과제가 동시에 그 이미지를 빌드하면 일부가
#   "image already exists" 로 실패하고, 재시도 없이 오류로 남는다. 과제 하나짜리 실행으로 이미지를 먼저 만들어 둔다 (README).
set -uo pipefail
WF=$1; KEY=$2; SERVED=$3; URLS=$4; ATT=${5:-3}; IDX=${6:-}
HERE=$(dirname "$(readlink -f "$0")")
REPO=${REPO:-$(git -C "$HERE" rev-parse --show-toplevel)}
PY=${PY:-$REPO/.venv/bin/python}
RLLM_BIN=$(dirname "$PY")/rllm
[ -x "$PY" ] && [ -x "$RLLM_BIN" ] || { echo "python or rllm command not found: $PY, $RLLM_BIN (set PY)"; exit 2; }
CONC=${CONC:-24}
export RLLM_HOME=${RLLM_HOME:-$HOME/.rllm}
export RLLM_AGENT_IMAGE=auto
export PYTHONPATH=$REPO
NAME=${WF}__${KEY}_x${ATT}${IDX:+-smoke}
BASE=$RLLM_HOME/eval_results/wfvar/$NAME
export TMPDIR=$RLLM_HOME/tmp_wfvar/$NAME
mkdir -p "$BASE/results" "$BASE/logs" "$TMPDIR"
IFS=',' read -r -a EP <<< "$URLS"
N=${#EP[@]}
cd "$REPO"
# 같은 결과 폴더를 다른 과제 목록이나 다른 endpoint 수로 다시 쓰면 끝난 shard 를 건너뛰어 일부 과제가 안 돈다. 그 경우 멈춘다.
SIG="endpoints=$N indices=${IDX:-all}"
if [ -f "$BASE/run_sig.txt" ] && [ "$(cat "$BASE/run_sig.txt")" != "$SIG" ]; then
  echo "result folder $BASE was started with '$(cat "$BASE/run_sig.txt")' but this call is '$SIG'."
  echo "Use another run key, or the same number of endpoints and the same task indices."
  exit 3
fi
echo "$SIG" > "$BASE/run_sig.txt"
{
  echo "--- call at $(date -Is)"
  echo "workflow: $WF"; echo "run key: $KEY"; echo "served model: $SERVED"; echo "endpoints: $URLS"; echo "attempts: $ATT"
  echo "concurrency per endpoint: $CONC"; echo "task indices: ${IDX:-all 499}"; echo "repo: $REPO @ $(git rev-parse --short HEAD) ($(git status --short | wc -l) uncommitted paths)"
  echo "workflow fingerprint: $($PY -c "import sys; from recipe.grpo.qwen3_5.workflows import get_workflow; print('-' if sys.argv[1]=='none' else get_workflow(sys.argv[1]).fingerprint('openhands-sdk'))" "$WF")"
  echo "started: $(date -Is)"
} >> "$BASE/run_info.txt"
for u in "${EP[@]}"; do
  curl -sf -m 10 "$u/models" > /dev/null || { echo "endpoint not reachable: $u/models" | tee -a "$BASE/run_info.txt"; exit 2; }
done
echo "[$(date -Is)] start $NAME on $N endpoint(s)" | tee -a "$BASE/run.log"
PIDS=()
for g in $(seq 0 $((N - 1))); do
  if [ -n "$IDX" ]; then
    [ "$g" -gt 0 ] && break
    SH="$IDX"
  else
    SH=$(seq $g $N 498 | paste -sd,)
  fi
  OUT=$BASE/shards/s$g
  mkdir -p "$OUT"
  [ -f "$BASE/results/s$g.json" ] && { echo "[$(date -Is)] have shard s$g, skip" | tee -a "$BASE/run.log"; continue; }
  (
    $RLLM_BIN eval swebench_verified_all --split test --task-indices "$SH" \
      --agent recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow \
      --agent-image auto --sandbox-backend docker --hide-git-history --no-agent-network --verify-network \
      --concurrency "$CONC" --sandbox-concurrency "$CONC" --attempts "$ATT" --no-ui \
      --base-url "${EP[$g]}" --model "$SERVED" \
      --sampling-params @recipe/eval/config/qwen3_5.yaml \
      --agent-kwargs "workflow=$WF,step_limit=250,enable_thinking=true,instruction_position=suffix,include_default_tools=FinishTool,strict_tool_calls=true" \
      --output "$BASE/results/s$g.json" --episodes-dir "$OUT/episodes" > "$BASE/logs/s$g.log" 2>&1
    echo "[$(date -Is)] end shard s$g exit=$?" >> "$BASE/run.log"
  ) &
  PIDS+=($!)
  sleep 10
done
[ ${#PIDS[@]} -gt 0 ] && wait "${PIDS[@]}"
$PY - "$BASE" <<'PY' | tee -a "$BASE/run.log"
import json, glob, sys
tot = cor = err = 0
for p in sorted(glob.glob(sys.argv[1] + '/results/s*.json')):
    d = json.load(open(p)); tot += d['total']; cor += d['correct']; err += d.get('errors', 0)
print(f"ALL DONE: {cor}/{tot} resolved ({100 * cor / tot:.1f}%), errors {err}" if tot else "ALL DONE: no result files")
PY
