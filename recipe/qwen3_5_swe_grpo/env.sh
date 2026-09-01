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

# train_verl.sh re-sources this file, so sourcing twice must not pin stale
# paths: a plain ${HF_HOME:-...} would keep whatever the first sourcing
# exported even after RLLM_SCRATCH changed. Recompute a value this script
# derived itself; leave an explicitly set one alone.
# The sentinel records that *this script* derived the value, so a path you set
# yourself is never recomputed while a derived one always tracks RLLM_SCRATCH.
if [ -z "${HF_HOME:-}" ] || [ "${HF_HOME:-}" = "${_RLLM_ENV_HF_HOME:-}" ]; then
    export HF_HOME="$RLLM_SCRATCH/hf"
    export _RLLM_ENV_HF_HOME="$HF_HOME"
else
    unset _RLLM_ENV_HF_HOME
fi
if [ -z "${RLLM_HOME:-}" ] || [ "${RLLM_HOME:-}" = "${_RLLM_ENV_RLLM_HOME:-}" ]; then
    export RLLM_HOME="$RLLM_SCRATCH/rllm-home"
    export _RLLM_ENV_RLLM_HOME="$RLLM_HOME"
else
    unset _RLLM_ENV_RLLM_HOME
fi
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-0}"

export VENV="${VENV:-$_RECIPE_REPO_ROOT/.venv}"
export PATH="$VENV/bin:$PATH"

# Ray puts its session dir, logs and object-store spill under /tmp by default.
# A container root filesystem is usually far smaller than the scratch volume,
# and raylet starts refusing work at 95% full ("is over 95% full" in the log),
# so keep Ray on the scratch volume too.
export RAY_TMPDIR="${RAY_TMPDIR:-$RLLM_SCRATCH/ray}"

# Same reasoning for the other defaults that land on the container's writable
# layer rather than a mounted volume: torch.compile writes /tmp/torchinductor_*,
# uv caches wheels under ~/.cache. In a container both of those are the small
# filesystem. Check any path with: findmnt -no SOURCE,FSTYPE -T <path>
export TMPDIR="${TMPDIR:-$RLLM_SCRATCH/tmp}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$RLLM_SCRATCH/uv}"
mkdir -p "$RAY_TMPDIR" "$TMPDIR" "$UV_CACHE_DIR"

mkdir -p "$HF_HOME" "$RLLM_HOME"
unset _RECIPE_REPO_ROOT
