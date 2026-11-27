#!/usr/bin/env bash
# SWE-bench Verified under several workflows against vLLM servers that are ALREADY RUNNING.
# The servers may be shared with other users, so this script never starts, stops or reconfigures one.
#
#   1. preflight: every endpoint serves MODEL_NAME (its context length and current load are printed),
#      docker answers, the dataset is there, the sandbox egress relay can be set up
#   2. for every workflow, one shard per endpoint (shard i -> endpoint i), all in parallel; each shard
#      runs its tasks as a sequence of small `rllm eval` calls (CHUNK_TASKS tasks each), so finished
#      chunks are on disk and progress is visible while the rest runs
#   3. every PROGRESS_EVERY seconds: per endpoint requests running/waiting, kv cache use and seconds per
#      request; per workflow episodes, resolved, agent_timeout. A warning when nothing has finished in 45 min
#   4. summary.md: resolve, termination reasons, LLM seconds per turn
#
# Harness settings are those of the earlier swebench_verified_all evaluations
# (recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow, step_limit 250, thinking on, FinishTool
# only, strict tool calls, hide-git-history, sampling from recipe/eval/config/qwen3_5.yaml).
#
#   # in a tmux window (the script tees itself to <run dir>/logs/launch.log)
#   export RLLM_HOME=<rllm home with datasets/swebench_verified_all>
#   export ENDPOINTS=http://<host>:<port>/v1,http://<host>:<port>/v1      # on another server: its own servers
#   TASK_LIMIT=3 bash recipe/grpo/qwen3_5/scripts/eval_sbv_endpoints.sh      # smoke first: 3 tasks per workflow, ~10 min
#   bash recipe/grpo/qwen3_5/scripts/eval_sbv_endpoints.sh                   # 499 tasks x 1, both variants
#   SANDBOX_PER_SHARD=6 CHUNK_TASKS=12 bash recipe/grpo/qwen3_5/scripts/eval_sbv_endpoints.sh   # servers otherwise idle
#
# The agent is cut off at 3000 s, so servers pushed past their capacity show up as agent_timeout and a
# resolve that cannot be compared. Seconds per request above ~10, requests waiting, or kv cache near 100%
# in the progress line mean SANDBOX_PER_SHARD is too high: stop, and resume with a lower value.
#
# Knobs (env):
#   ENDPOINTS         comma list of OpenAI base URLs            (default: the three :8070/:8072/:8075 servers)
#   MODEL_NAME        served-model-name on those servers        (default: speckit-step27)
#   RUN_TAG           name used in result directories           (default: speckit-pen03-fmtcut-step27)
#   WORKFLOWS         comma list                                (default: speckit_bug_repro,aidlc_v5_repro)
#   ATTEMPTS          rollouts per task                         (default: 1)
#   SANDBOX_PER_SHARD sandboxes per eval process                (default: 4 -> 2 wf x 3 endpoints x 4 = 24;
#                     that is 8 sandboxes, about 5-6 requests at a time, per endpoint on top of the other users)
#   CHUNK_TASKS       tasks per rllm eval call within a shard   (default: 7)
#   PROGRESS_EVERY    seconds between progress lines            (default: 300)
#   TASK_LIMIT        evaluate only the first N tasks (smoke)   (default: all)
#   RUN_TS            reuse a run's timestamp to RESUME it: chunks whose episodes are all on disk are skipped
#                     (keep CHUNK_TASKS as it was; SANDBOX_PER_SHARD may change)
#   DRY_RUN=1         print the commands, launch nothing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
RECIPE_DIR="${REPO_ROOT}/recipe/grpo/qwen3_5"
cd "${REPO_ROOT}"

ENV_FILE="${ENV_FILE:-${RECIPE_DIR}/.env}"
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
fi
: "${RLLM_HOME:?export RLLM_HOME (or set it in ${ENV_FILE})}"
if [ -z "${VIRTUAL_ENV:-}" ] || ! command -v python > /dev/null 2>&1; then  # VIRTUAL_ENV can be inherited without its PATH
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.venv/bin/activate"
fi
export RLLM_AGENT_IMAGE="${RLLM_AGENT_IMAGE:-auto}"
# `rllm eval --agent recipe.grpo.qwen3_5.workflow_harness:...` imports the recipe package, which is
# not installed: the `rllm` console script does not put the cwd on sys.path, so name the repo root.
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

ENDPOINTS="${ENDPOINTS:-http://27.122.129.140:8070/v1,http://27.122.129.140:8072/v1,http://27.122.129.140:8075/v1}"
MODEL_NAME="${MODEL_NAME:-speckit-step27}"
RUN_TAG="${RUN_TAG:-speckit-pen03-fmtcut-step27}"
WORKFLOWS="${WORKFLOWS:-speckit_bug_repro,aidlc_v5_repro}"
BENCH="${BENCH:-swebench_verified_all}"
SPLIT="${SPLIT:-test}"
ATTEMPTS="${ATTEMPTS:-1}"
SANDBOX_PER_SHARD="${SANDBOX_PER_SHARD:-4}"
CHUNK_TASKS="${CHUNK_TASKS:-7}"
PROGRESS_EVERY="${PROGRESS_EVERY:-300}"
STEP_LIMIT="${STEP_LIMIT:-250}"
SAMPLING="${SAMPLING:-${REPO_ROOT}/recipe/eval/config/qwen3_5.yaml}"
TASK_LIMIT="${TASK_LIMIT:-}"
DRY_RUN="${DRY_RUN:-0}"

IFS=',' read -r -a EP_LIST <<< "${ENDPOINTS}"
IFS=',' read -r -a WF_LIST <<< "${WORKFLOWS}"
NUM_EP="${#EP_LIST[@]}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d_%H%M%S)}"
RUN_DIR="${RUN_DIR:-${RLLM_ARTIFACT_DIR:-${RLLM_HOME}}/eval_runs/${RUN_TAG}_${RUN_TS}}"
LOG_DIR="${RUN_DIR}/logs"
mkdir -p "${LOG_DIR}"
# Keep a transcript beside the per-process logs so the tmux scrollback is not the only record.
exec > >(tee -a "${LOG_DIR}/launch.log") 2>&1
echo "run dir: ${RUN_DIR}"

# ---------------------------------------------------------------- 0. preflight
load() {  # requests running on one endpoint now, "?" when /metrics does not answer
    curl -s -m 8 "${1%/v1}/metrics" | awk '/^vllm:num_requests_running/ {s += $NF; f = 1} END {if (f) printf "%d", s; else printf "?"}'
}
ep_stat() {  # "<running>/<waiting> kv <cache %> <s per request since the previous call>" for endpoint $1, state kept under key $2
    local m now prev="${RUN_DIR}/.latency_$2"
    m="$(curl -s -m 8 "${1%/v1}/metrics" || true)"
    [ -n "${m}" ] || { printf "?"; return 0; }
    now="$(awk '/^vllm:e2e_request_latency_seconds_sum/ {s += $NF} /^vllm:e2e_request_latency_seconds_count/ {c += $NF} END {printf "%.3f %d", s, c}' <<< "${m}")"
    awk -v now="${now}" -v prev="$(cat "${prev}" 2>/dev/null || true)" '
        /^vllm:num_requests_running/ {r += $NF} /^vllm:num_requests_waiting/ {w += $NF} /^vllm:kv_cache_usage_perc/ {k = $NF}
        END {split(now, n, " "); split(prev, q, " "); lat = "-"
             if (prev != "" && n[2] > q[2]) lat = sprintf("%.1fs", (n[1] - q[1]) / (n[2] - q[2]))
             printf "%d/%d kv %d%% %s", r, w, 100 * k, lat}' <<< "${m}"
    echo "${now}" > "${prev}"
}
for ep in "${EP_LIST[@]}"; do
    info="$(curl -s -m 15 "${ep}/models" | python -c '
import json, sys
want = sys.argv[1]
try:
    data = json.load(sys.stdin).get("data", [])
except Exception:
    data = []
hit = [m for m in data if m.get("id") == want]
print("max_model_len=" + str(hit[0].get("max_model_len")) if hit else "MISSING (serves: " + ", ".join(m.get("id", "?") for m in data) + ")")
' "${MODEL_NAME}")"
    echo "  ${ep}  ${MODEL_NAME}: ${info}  requests running now: $(load "${ep}")"
    case "${info}" in MISSING*) echo "endpoint ${ep} does not serve ${MODEL_NAME}" >&2; exit 1 ;; esac
done
if [ "${DRY_RUN}" != 1 ]; then
    docker info >/dev/null 2>&1 || { echo "docker daemon not reachable" >&2; exit 1; }
    [ -f "${RLLM_HOME}/datasets/${BENCH}/dataset.toml" ] || { echo "dataset ${BENCH} not under ${RLLM_HOME}/datasets" >&2; exit 1; }
    # Sandboxes reach the model through the egress relay. When its lock cannot be taken no sandbox
    # starts and the run sits at 0 episodes without an error, so find that out here.
    timeout 120 python -c 'from rllm.sandbox.backends import egress; print("  sandbox egress relay:", egress.ensure_relay())' \
        || { echo "the sandbox egress relay cannot be set up (lock $(ls -l /tmp/rllm-egress-relay.lock 2>&1))" >&2; exit 1; }
fi
python - "${WORKFLOWS}" <<'PY'
import sys
from recipe.grpo.qwen3_5.workflows import parse_workflows
parse_workflows(sys.argv[1].replace(",", "+"))  # an unknown workflow name stops the run here
PY

NUM_TASKS="$(python - "${RLLM_HOME}/datasets/${BENCH}/${SPLIT}.parquet" <<'PY'
import sys, pyarrow.parquet as pq
print(pq.read_metadata(sys.argv[1]).num_rows)
PY
)"
if [ -n "${TASK_LIMIT}" ] && [ "${TASK_LIMIT}" -lt "${NUM_TASKS}" ]; then NUM_TASKS="${TASK_LIMIT}"; fi
echo "benchmark: ${BENCH}/${SPLIT}, ${NUM_TASKS} tasks x ${ATTEMPTS} attempts, workflows: ${WORKFLOWS}"
echo "sandboxes at a time: ${#WF_LIST[@]} workflows x ${NUM_EP} endpoints x ${SANDBOX_PER_SHARD} = $(( ${#WF_LIST[@]} * NUM_EP * SANDBOX_PER_SHARD ))"

# ---------------------------------------------------------------- 1. rllm eval, sharded
EVAL_PIDS=()
per=$(( (NUM_TASKS + NUM_EP - 1) / NUM_EP ))
for wf in "${WF_LIST[@]}"; do
    kw="${RUN_DIR}/agent_kwargs_${wf}.yaml"
    {
        echo "workflow: ${wf}"
        echo "step_limit: ${STEP_LIMIT}"
        echo "enable_thinking: true"
        echo "include_default_tools: [FinishTool]"
        echo "strict_tool_calls: true"
    } > "${kw}"
    for i in $(seq 0 $((NUM_EP - 1))); do
        shard_start=$((i * per)); shard_end=$((shard_start + per - 1))
        [ "${shard_end}" -ge "${NUM_TASKS}" ] && shard_end=$((NUM_TASKS - 1))
        [ "${shard_start}" -gt "${shard_end}" ] && continue
        ep="${EP_LIST[$i]}"
        # One background worker per shard: its chunks run one after another on endpoint i.
        (
            k=0
            for ((start = shard_start; start <= shard_end; start += CHUNK_TASKS)); do
                end=$((start + CHUNK_TASKS - 1)); [ "${end}" -gt "${shard_end}" ] && end="${shard_end}"
                out="${RLLM_HOME}/eval_results/${BENCH}_${RUN_TAG}_${wf}_${RUN_TS}_s${i}_c${k}"
                want=$(( (end - start + 1) * ATTEMPTS ))
                have=0  # find on a directory that does not exist yet exits 1, which pipefail would turn into the end of this worker
                [ -d "${out}/episodes" ] && have="$(find "${out}/episodes" -name '*.json' | wc -l)"
                if [ "${have}" -ge "${want}" ]; then k=$((k + 1)); continue; fi  # resumed run: this chunk is done
                cmd=(rllm eval "${BENCH}" --split "${SPLIT}"
                     --agent recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow
                     --agent-kwargs "@${kw}" --agent-image "${RLLM_AGENT_IMAGE}"
                     --sandbox-backend docker --hide-git-history
                     --attempts "${ATTEMPTS}" --task-indices "${start}-${end}"
                     --concurrency "${SANDBOX_PER_SHARD}" --sandbox-concurrency "${SANDBOX_PER_SHARD}" --no-ui
                     --base-url "${ep}" --model "${MODEL_NAME}"
                     --sampling-params "@${SAMPLING}" --episodes-dir "${out}")
                if [ "${DRY_RUN}" = 1 ]; then echo "+ ${cmd[*]}"; k=$((k + 1)); continue; fi
                if ! "${cmd[@]}" > "${LOG_DIR}/eval_${wf}_s${i}_c${k}.log" 2>&1; then
                    echo "${wf} shard ${i} chunk ${k} tasks ${start}-${end} -> ${LOG_DIR}/eval_${wf}_s${i}_c${k}.log" >> "${RUN_DIR}/failed_chunks.txt"
                fi
                k=$((k + 1))
            done
        ) &
        EVAL_PIDS+=("$!")
        [ "${DRY_RUN}" = 1 ] || sleep 3
    done
done
# Always wait on explicit pids: a bare `wait` also waits for the `exec > >(tee ...)` process
# substitution above, which cannot end while this script holds its stdout -- a deadlock.
if [ "${DRY_RUN}" = 1 ]; then
    for p in "${EVAL_PIDS[@]}"; do wait "${p}" || true; done
    echo "dry run: ${#WF_LIST[@]} workflows x ${NUM_EP} shards, ${per} tasks per shard, ${CHUNK_TASKS} per rllm eval call"
    exit 0
fi

# ---------------------------------------------------------------- progress, in this window
TOTAL_PER_WF=$((NUM_TASKS * ATTEMPTS))
progress() {
    local wf dirs n ok to pct ep loads="" seen=0
    local i=0
    for ep in "${EP_LIST[@]}"; do loads="${loads} | $(ep_stat "${ep}" "${i}")"; i=$((i + 1)); done
    # s per request above ~10 s, requests waiting, or kv near 100%: the servers are over their capacity and agent_timeout follows
    echo "[$(date +%H:%M)] shard workers alive: ${alive}   endpoints (running/waiting, kv cache, s per request since the last line):${loads# |}"
    if grep -lq "Could not open gateway port" "${LOG_DIR}"/eval_*.log 2>/dev/null; then
        echo "  !! a gateway port was not opened to the sandboxes (see $(grep -l 'Could not open gateway port' "${LOG_DIR}"/eval_*.log | head -1)): those calls cannot finish, stop this run"
    fi
    for wf in "${WF_LIST[@]}"; do
        dirs=("${RLLM_HOME}/eval_results/${BENCH}_${RUN_TAG}_${wf}_${RUN_TS}"_s*/episodes)
        n=0; ok=0; to=0
        if [ -d "${dirs[0]}" ]; then
            n="$({ find "${dirs[@]}" -name '*.json' 2>/dev/null || true; } | wc -l)"
            ok="$({ find "${dirs[@]}" -name '*.json' -print0 2>/dev/null || true; } | { xargs -0 -r grep -l '"is_correct": true' 2>/dev/null || true; } | wc -l)"
            to="$({ find "${dirs[@]}" -name '*.json' -print0 2>/dev/null || true; } | { xargs -0 -r grep -l '"termination_reason": "agent_timeout"' 2>/dev/null || true; } | wc -l)"
        fi
        pct="-"; [ "${n}" -gt 0 ] && pct="$(awk -v o="${ok}" -v n="${n}" 'BEGIN{printf "%.1f%%", 100*o/n}')"
        printf "  %-18s episodes %4d/%d   resolved %4d (%s)   agent_timeout %d\n" "${wf}" "${n}" "${TOTAL_PER_WF}" "${ok}" "${pct}" "${to}"
        seen=$((seen + n))
    done
    if [ "${seen}" -eq 0 ] && [ $(( $(date +%s) - STARTED )) -gt 2700 ]; then
        echo "  !! no episode after $(( ($(date +%s) - STARTED) / 60 )) min: an episode takes about 10. Look at ${LOG_DIR}/eval_*.log and at 'docker ps | grep rllm-sandbox'"
    fi
}

echo "${#EVAL_PIDS[@]} shard workers running; per-call logs in ${LOG_DIR}"
STARTED="$(date +%s)"
while :; do
    alive=0
    for p in "${EVAL_PIDS[@]}"; do kill -0 "${p}" 2>/dev/null && alive=$((alive + 1)); done
    progress || true  # the display must never end the run
    [ "${alive}" -eq 0 ] && break
    sleep "${PROGRESS_EVERY}"
done
for p in "${EVAL_PIDS[@]}"; do wait "${p}" || true; done
if [ -f "${RUN_DIR}/failed_chunks.txt" ]; then
    echo "chunks that exited non-zero (resume with RUN_TS=${RUN_TS}):"; cat "${RUN_DIR}/failed_chunks.txt"
else
    echo "every chunk exited 0"
fi

# ---------------------------------------------------------------- summary
python - "${RLLM_HOME}/eval_results" "${BENCH}_${RUN_TAG}" "${RUN_TS}" "${WORKFLOWS}" "${RUN_DIR}/summary.md" <<'PY'
import collections, glob, json, os, sys
root, prefix, ts, workflows, out = sys.argv[1:6]
lines = [f"# {prefix} {ts}", "", "| workflow | tasks | episodes | resolve (pass@1) | pass@any | LLM s/turn | termination |", "|---|---|---|---|---|---|---|"]
for wf in workflows.split(","):
    per_task = collections.defaultdict(list); term = collections.Counter(); n = 0; llm = turns = 0.0
    for d in sorted(glob.glob(f"{root}/{prefix}_{wf}_{ts}_s*")):
        for f in glob.glob(f"{d}/episodes/*.json"):
            try:
                e = json.load(open(f))
            except Exception:
                term["unreadable"] += 1; continue
            n += 1
            tid = e.get("task", {}).get("id") if isinstance(e.get("task"), dict) else None
            tid = tid or os.path.basename(f).rsplit("_", 1)[0]
            per_task[tid].append(bool(e.get("is_correct")))
            term[e.get("termination_reason") or "?"] += 1
            m = e.get("metrics") or {}
            if m.get("time/agentflow_llm_sum_s") and m.get("n_turns"):
                llm += float(m["time/agentflow_llm_sum_s"]); turns += float(m["n_turns"])
    if not n:
        lines.append(f"| {wf} | 0 | 0 | - | - | - | - |"); continue
    p1 = sum(sum(v) / len(v) for v in per_task.values()) / len(per_task)
    pk = sum(any(v) for v in per_task.values()) / len(per_task)
    lat = f"{llm / turns:.1f}" if turns else "-"
    lines.append(f"| {wf} | {len(per_task)} | {n} | {p1:.3f} | {pk:.3f} | {lat} | {', '.join(f'{k} {v}' for k, v in term.most_common())} |")
text = "\n".join(lines) + "\n"
open(out, "w").write(text); print(text)
PY
echo "summary: ${RUN_DIR}/summary.md"
