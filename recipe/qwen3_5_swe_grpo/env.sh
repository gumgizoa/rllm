# Shared environment for the qwen3_5_swe_grpo recipe. Source it before anything else.
#
# Every variable is overridable: export it before sourcing and that value wins.
# The defaults hang everything off RLLM_SCRATCH because this recipe is storage
# hungry -- the model snapshot is ~9 GB and the SWE task images run to tens of
# GB more, which is usually more than a container's root filesystem has. Point
# RLLM_SCRATCH at a large volume:
#
#     RLLM_SCRATCH=/mnt/big/rllm-work source recipe/qwen3_5_swe_grpo/env.sh

_RECIPE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export RLLM_SCRATCH="${RLLM_SCRATCH:-$HOME/rllm-work}"
export HF_HOME="${HF_HOME:-$RLLM_SCRATCH/hf}"
export RLLM_HOME="${RLLM_HOME:-$RLLM_SCRATCH/rllm-home}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

export VENV="${VENV:-$_RECIPE_REPO_ROOT/.venv}"
export PATH="$VENV/bin:$PATH"

mkdir -p "$HF_HOME" "$RLLM_HOME"
unset _RECIPE_REPO_ROOT
