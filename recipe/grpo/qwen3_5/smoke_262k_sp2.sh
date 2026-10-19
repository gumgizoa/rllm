#!/usr/bin/env bash
# Smoke test for the long-context arm: does one real training step fit on
# 8 x H200 at a 262144-token window with Ulysses sequence parallelism 2?
#
# What it runs: variant=openhands_9b_aidlc_swegym_v2_reward (the arm with a
# compliance scorer), with the three length knobs of
# openhands_9b_speckit_openspec_swegym_reward (250 turns, 16384 + 245760 =
# 262144) and its thinking-on setting, on 4 tasks x 4 rollouts = 16
# trajectories, one optimizer update, no validation, no checkpoint.
#
# What it measures (read from the transcript afterwards, see the tail of this
# file): perf/max_memory_allocated_gb on the actor update, against the 91-93 GB
# the 131072 run reached (reserved 107 GB) with sp=1. The peak only reflects the
# longest row actually sampled, so read response_length/max next to it: a run
# whose longest row stayed far below 245760 has not answered the OOM question.
#
# Ulysses SP: 8 GPUs / sp 2 = 4 data-parallel ranks, so train_batch_size x n
# must divide by 4 (16 does) and ppo_mini_batch_size = train_batch_size keeps
# the one-update-per-step rule of the variant. SP needs the backported verl
# patch (scripts/apply_verl_patches.sh); README "Long context, sequence
# parallelism, and FSDP version" has the measurements (3x slower update_actor,
# ~30% less activation memory at 4B).
#
#   source /data/MMI/kyuminkim/venvs/rllm/bin/activate
#   bash recipe/grpo/qwen3_5/smoke_262k_sp2.sh
#   bash recipe/grpo/qwen3_5/smoke_262k_sp2.sh rllm.gateway.renderer_kwargs.enable_thinking=false   # no-think
#   bash recipe/grpo/qwen3_5/smoke_262k_sp2.sh actor_rollout_ref.actor.ulysses_sequence_parallel_size=1  # sp=1 for comparison
set -euo pipefail

RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${RECIPE_DIR}/../../.." && pwd)"

: "${VIRTUAL_ENV:?activate the venv first: source /data/MMI/kyuminkim/venvs/rllm/bin/activate}"

# 1. The SP path crashes in the fused head without the backported patch.
if bash "${RECIPE_DIR}/scripts/apply_verl_patches.sh" --check | grep -q "NOT APPLIED"; then
    echo "verl patch not applied; run: bash ${RECIPE_DIR}/scripts/apply_verl_patches.sh" >&2
    exit 1
fi

# 2. Every card must be free: another job's 72 GB would masquerade as our OOM.
busy="$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2 > 2000 {print "gpu"$1"="$2"MiB"}')"
if [ -n "${busy}" ]; then
    echo "GPUs not free: ${busy}" >&2
    exit 1
fi

# 3. The datasets the v2 variant reads must be registered under this RLLM_HOME.
ENV_FILE="${ENV_FILE:-${RECIPE_DIR}/.env}"
# shellcheck source=/dev/null
rllm_home="$(set -a; source "${ENV_FILE}"; set +a; echo "${RLLM_HOME:-}")"
for ds in swegym293_aidlc swegym_val23_aidlc; do
    if [ ! -d "${rllm_home}/datasets/${ds}" ]; then
        echo "${rllm_home}/datasets/${ds} missing; run prepare_swegym.py --instruction aidlc" >&2
        exit 1
    fi
done

export RLLM_RUN_ID="${RLLM_RUN_ID:-smoke262k_$(date +%Y%m%d_%H%M%S)}"

"${RECIPE_DIR}/train_verl.sh" \
    variant=openhands_9b_aidlc_swegym_v2_reward \
    rllm.trainer.experiment_name=smoke-262k-sp2-aidlc-v2-reward \
    rllm.trainer.logger='[console]' \
    `# --- the long-context arm's settings (openhands_9b_speckit_openspec_swegym_reward) ---` \
    recipe.agent_step_limit=250 \
    rllm.data.max_prompt_length=16384 \
    rllm.data.max_response_length=245760 \
    actor_rollout_ref.rollout.max_model_len=262144 \
    rllm.gateway.renderer_kwargs.enable_thinking=true \
    `# --- what is under test ---` \
    actor_rollout_ref.actor.ulysses_sequence_parallel_size=2 \
    `# --- one small step: 4 tasks x 4 = 16 trajectories, one update, 16 live sandboxes ---` \
    recipe.train_limit=4 \
    recipe.val_limit=1 \
    rllm.data.train_batch_size=4 \
    rllm.rollout.n=4 \
    actor_rollout_ref.actor.ppo_mini_batch_size=4 \
    rllm.workflow.n_parallel_tasks=16 \
    recipe.sandbox_concurrency=16 \
    rllm.trainer.total_batches=1 \
    rllm.trainer.total_epochs=1 \
    rllm.trainer.val_before_train=false \
    rllm.trainer.test_freq=-1 \
    rllm.trainer.save_freq=-1 \
    `# faster vLLM startup; CUDA graphs are off in this smoke only` \
    actor_rollout_ref.rollout.enforce_eager=true \
    "$@"

LOG="${RLLM_RUN_DIR:-${REPO_ROOT}/outputs}/logs/train_${RLLM_RUN_ID}.log"
echo
echo "=== smoke 262k / sp2: what to read (${LOG}) ==="
grep -oE "(perf/max_memory_(allocated|reserved)_gb|response_length/max|prompt_length/max|rollout_actor_probs_pearson_corr|timing_s/(update_actor|old_log_probs|step)|termination_reason/[a-z_]+|batch/n_turns)[^,}]*[0-9.]+" "${LOG}" \
    | sed -E "s/['\": ]+/ /" | sort -u || true
