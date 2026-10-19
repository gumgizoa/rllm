#!/usr/bin/env bash
# Smoke test for variant=openhands_9b_speckit_openspec_swegym_reward: does one real
# training step fit on 8 x H200 at its 262144-token window with Ulysses sequence
# parallelism 2 -- measured on rows that actually reach the window.
#
# The first smoke (smoke_262k_sp2.sh, 2026-10-16) ran the first four swegym293 tasks:
# all moto, all solved in 16-110 turns, so no row came near 245760 tokens and the
# peak said nothing. This one trains on swegym_long4_aidlc, four tasks the 9B run of
# 2026-09-23 (80 turns, no-think) solved 0-25% of the time and mostly ended on
# max_turns_exceeded at 65-90K tokens of context:
#
#   iterative__dvc-3576   speckit_bug   0/12 solved, 73K mean context
#   iterative__dvc-4778   openspec_ff   0/12 solved, 70K
#   python__mypy-16906    openspec_ff   0/12 solved, 65K
#   python__mypy-10424    speckit_bug   3/12 solved, 67K
#
# With 250 turns and thinking on, a rollout that does not solve its task runs into
# the context window first (MAX_PROMPT_LENGTH_EXCEEDED, a budget reason: kept and
# graded), and that row is exactly max_response_length long -- the case the actor
# update has to survive. The workflow column is assign_workflow(seed=0), so both
# mixed workflows and both new rubric scorers run.
#
# Registered with (inside the training container, .env exported):
#   python recipe/grpo/qwen3_5/scripts/prepare_swegym.py --parquet-dir <SkyRL-v0-293-data> \
#       --train-only --instruction aidlc --train-name swegym_long4_aidlc \
#       --ids iterative__dvc-3576,iterative__dvc-4778,python__mypy-16906,python__mypy-10424
#
# Everything else -- 250 turns, 16384 + 245760 = 262144, thinking on, the two
# workflows with reward = verifier * <workflow>/compliance -- comes from the variant.
# Under test here: actor.ulysses_sequence_parallel_size=2 (8 GPUs -> 4 DP ranks, so
# train_batch_size x n = 16 divides; ppo_mini_batch_size = train_batch_size keeps one
# update per step). SP needs the backported verl patch (scripts/apply_verl_patches.sh).
#
#   source /data/MMI/kyuminkim/venvs/rllm/bin/activate
#   bash recipe/grpo/qwen3_5/smoke_262k_sp2_speckit.sh
#   bash recipe/grpo/qwen3_5/smoke_262k_sp2_speckit.sh actor_rollout_ref.actor.ulysses_sequence_parallel_size=1  # sp=1 control
#
# Read afterwards (printed at the end): perf/max_memory_allocated_gb against the
# 91-93 GB (reserved 107) of the 131072 run; response_length/max should be at or
# near 245760, or the question is still open; termination_reason/* shows how many
# rows hit the window; speckit_bug/* and openspec_ff/* engine_errors must be 0.
#
# Wall clock: rollouts up to task.toml's 3600 s agent timeout (one wave of 16),
# then old_log_probs + update_actor on 245K rows with sp=2 -- expect 1-1.5 h.
set -euo pipefail

RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${RECIPE_DIR}/../../.." && pwd)"

: "${VIRTUAL_ENV:?activate the venv first: source /data/MMI/kyuminkim/venvs/rllm/bin/activate}"

TRAIN_DATASET="${TRAIN_DATASET:-swegym_long4_aidlc}"

# 1. The SP path crashes in the fused head without the backported patch.
if bash "${RECIPE_DIR}/scripts/apply_verl_patches.sh" --check | grep -q "NOT APPLIED"; then
    echo "verl patch not applied; run: bash ${RECIPE_DIR}/scripts/apply_verl_patches.sh" >&2
    exit 1
fi

# 2. Every card must be free: another job's memory would masquerade as our OOM.
busy="$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | awk -F', ' '$2 > 2000 {print "gpu"$1"="$2"MiB"}')"
if [ -n "${busy}" ]; then
    echo "GPUs not free: ${busy}" >&2
    exit 1
fi

# 3. The datasets must be registered under this RLLM_HOME, and the task images present.
ENV_FILE="${ENV_FILE:-${RECIPE_DIR}/.env}"
# shellcheck source=/dev/null
rllm_home="$(set -a; source "${ENV_FILE}"; set +a; echo "${RLLM_HOME:-}")"
for ds in "${TRAIN_DATASET}" swegym_val23_aidlc; do
    if [ ! -d "${rllm_home}/datasets/${ds}" ]; then
        echo "${rllm_home}/datasets/${ds} missing; see the header for the prepare_swegym.py call" >&2
        exit 1
    fi
done
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
    missing="$(comm -23 <(sort "${rllm_home}/datasets/${TRAIN_DATASET}/images.txt") <(docker images --format '{{.Repository}}:{{.Tag}}' | sort))"
    if [ -n "${missing}" ]; then
        echo "task images not in the local docker daemon:" >&2
        echo "${missing}" >&2
        echo "pull with:  xargs -a ${rllm_home}/datasets/${TRAIN_DATASET}/images.txt -P 4 -I{} docker pull {}" >&2
        exit 1
    fi
fi

export RLLM_RUN_ID="${RLLM_RUN_ID:-smoke262k_speckit_$(date +%Y%m%d_%H%M%S)}"

"${RECIPE_DIR}/train_verl.sh" \
    variant=openhands_9b_speckit_openspec_swegym_reward \
    rllm.trainer.experiment_name=smoke-262k-sp2-speckit-openspec \
    rllm.trainer.logger='[console]' \
    recipe.train_dataset="${TRAIN_DATASET}" \
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
echo "=== smoke 262k / sp2 / speckit+openspec: what to read (${LOG}) ==="
grep -oE "(perf/max_memory_(allocated|reserved)_gb|response_length/(max|mean)|prompt_length/max|rollout_actor_probs_pearson_corr|timing_s/(update_actor|old_log_probs|step)|termination_reason/[a-z_]+|batch/n_turns|(speckit_bug|openspec_ff)/(compliance|engine_errors|collect_errors)|workflow/[a-z_]+/resolved)[^,}]*[0-9.]+" "${LOG}" \
    | sed -E "s/['\": ]+/ /" | sort -u || true
