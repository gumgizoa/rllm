#!/usr/bin/env bash
# Run `rllm eval` over a materialised dataset in index batches, deleting each
# batch's task images afterwards.
#
# Why: the native docker backend builds one image per task (rllm-task-<id>,
# 1.5-2 GB each) and never removes it. On this host the containerd
# snapshotter stores image layers on the root disk regardless of the Docker
# data-root, so 1,471 images would fill / long before the run ends. A batch
# only needs its images alive while its rollouts run (all --attempts of a task
# share one image), so build -> run -> rmi per batch keeps the footprint at
# BATCH x ~2 GB.
#
# Task indices follow rllm's order (task_id sorted, case-sensitive); the id
# list is derived from the registered parquet so the rmi step targets exactly
# the images this batch built. Batches whose results.json exists are skipped,
# so the script can be re-run to resume.
#
#   bash recipe/eval/swe-rl/run_batches.sh <run_name> <agent> [extra rllm eval args...]
#
#   RUN=oracle_v1  bash run_batches.sh oracle_v1 oracle \
#       --base-url http://127.0.0.1:1/v1 --model oracle-dummy
#   bash run_batches.sh rollout8_v1 openhands-sdk --attempts 8 --agent-image auto \
#       --base-url http://<vllm-host>:8000/v1 --model Qwen/Qwen3.5-9B \
#       --sampling-params @recipe/eval/config/qwen3_5.yaml --hide-git-history
#
# Env: DATASET (swe_rl_v1) SPLIT (test) BATCH (16) CONCURRENCY (16)
#      MIN_FREE_GB (100, on GUARD_PATH=/) CACHE_PRUNE_BELOW_GB (180) START_BATCH (0) END_BATCH (all)
#      KEEP_IMAGES (0): 1 keeps task images after each batch (hosts with image storage on a big disk)

set -uo pipefail

RUN_NAME="${1:?run name}"; shift
AGENT="${1:?agent name}"; shift
EXTRA_ARGS=("$@")

DATASET="${DATASET:-swe_rl_v1}"
SPLIT="${SPLIT:-test}"
BATCH="${BATCH:-16}"
CONCURRENCY="${CONCURRENCY:-16}"
MIN_FREE_GB="${MIN_FREE_GB:-100}"
CACHE_PRUNE_BELOW_GB="${CACHE_PRUNE_BELOW_GB:-180}"
GUARD_PATH="${GUARD_PATH:-/}"
START_BATCH="${START_BATCH:-0}"
END_BATCH="${END_BATCH:-}"

: "${RLLM_HOME:?RLLM_HOME must be set}"
RUN_DIR="$RLLM_HOME/eval_results/$RUN_NAME"
mkdir -p "$RUN_DIR"
IDS="$RUN_DIR/ids_sorted.txt"
LOG="$RUN_DIR/batches.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
free_gb() { df --output=avail -BG "$GUARD_PATH" | tail -1 | tr -dc '0-9'; }

if [ ! -s "$IDS" ]; then
    python - "$RLLM_HOME/datasets/$DATASET/$SPLIT.parquet" "$IDS" <<'PY'
import sys, pandas as pd
ids = sorted(pd.read_parquet(sys.argv[1]).task_id)
open(sys.argv[2], "w").write("\n".join(ids) + "\n")
PY
fi
mapfile -t ALL_IDS < "$IDS"
TOTAL=${#ALL_IDS[@]}
N_BATCHES=$(( (TOTAL + BATCH - 1) / BATCH ))
END_BATCH="${END_BATCH:-$((N_BATCHES - 1))}"
log "run=$RUN_NAME agent=$AGENT tasks=$TOTAL batch=$BATCH batches=$N_BATCHES [$START_BATCH..$END_BATCH] concurrency=$CONCURRENCY extra=(${EXTRA_ARGS[*]})"

cleanup_batch_images() {
    # $@ = task ids of this batch. Remove their sandboxes (if any survived)
    # and images, then the dangling build cache they left behind.
    local tags=() id
    for id in "$@"; do tags+=("rllm-task-$(echo "$id" | tr 'A-Z' 'a-z')"); done
    for t in "${tags[@]}"; do
        docker ps -a --filter "ancestor=$t" -q | xargs -r docker rm -f >/dev/null 2>&1
    done
    if [ "${KEEP_IMAGES:-0}" = "1" ]; then
        # Host stores images on a big disk: keep them so a later run (oracle ->
        # rollout) reuses them instead of rebuilding.
        log "KEEP_IMAGES=1: leaving ${#tags[@]} task images in place"
        return
    fi
    docker rmi -f "${tags[@]}" >/dev/null 2>&1
    # The untagged twin each build leaves behind holds the layers; see disk_guard_rllm.sh.
    MIN_AGE_MIN=0 bash "$(dirname "${BASH_SOURCE[0]}")/disk_guard_rllm.sh" sweep | tee -a "$LOG"
    # BuildKit keeps a full build cache next to the image (measured: 146 GB for
    # one batch of 32 4-GB images) and `prune -f` reclaims almost none of it
    # once the image is gone. `prune -af` is daemon-wide (other users lose
    # rebuild speed, never images or containers), so only do it under pressure.
    if [ "$(free_gb)" -lt "$CACHE_PRUNE_BELOW_GB" ]; then
        timeout 600 docker builder prune -af 2>&1 | tail -1 | sed 's/^/[builder prune -af] /' | tee -a "$LOG"
    fi
}

wait_for_disk() {
    local f
    f=$(free_gb)
    while [ "$f" -lt "$MIN_FREE_GB" ]; do
        log "disk guard: $GUARD_PATH free ${f}G < ${MIN_FREE_GB}G, sweeping stale rllm-task images and waiting"
        # Any rllm-task image not used by a running container is stale here
        # (this script is the only producer of them in this RLLM_HOME).
        docker images --format '{{.Repository}}' | grep '^rllm-task-' | while read -r img; do
            [ -z "$(docker ps -q --filter "ancestor=$img")" ] && docker rmi -f "$img" >/dev/null 2>&1
        done
        timeout 300 docker builder prune -f >/dev/null 2>&1
        sleep 120
        f=$(free_gb)
    done
}

for (( b=START_BATCH; b<=END_BATCH; b++ )); do
    start=$(( b * BATCH ))
    [ "$start" -ge "$TOTAL" ] && break
    end=$(( start + BATCH - 1 )); [ "$end" -ge "$TOTAL" ] && end=$(( TOTAL - 1 ))
    tag=$(printf 'batch_%04d' "$b")
    out="$RUN_DIR/$tag"
    ids=("${ALL_IDS[@]:$start:$((end - start + 1))}")

    if [ -s "$out/results.json" ]; then
        log "$tag [$start..$end] already done, skipping"
        cleanup_batch_images "${ids[@]}"
        continue
    fi

    wait_for_disk
    indices=$(seq -s, "$start" "$end")
    log "$tag [$start..$end] start (free $(free_gb)G)"
    rllm eval "$DATASET" --split "$SPLIT" --agent "$AGENT" --sandbox-backend docker \
        --task-indices "$indices" --concurrency "$CONCURRENCY" --sandbox-concurrency "$CONCURRENCY" \
        --no-ui --episodes-dir "$out" "${EXTRA_ARGS[@]}" > "$out.log" 2>&1
    rc=$?
    summary=$(tr '\r' '\n' < "$out.log" | grep -E "Accuracy|Errors" | tr -s ' ' | tr '\n' ' ')
    log "$tag done rc=$rc $summary"
    cleanup_batch_images "${ids[@]}"
    log "$tag images removed (free $(free_gb)G)"
done
log "all batches finished"
