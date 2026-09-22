#!/usr/bin/env bash
# Native rLLM SWE GRPO on verl — Qwen/Qwen3.5-4B + mini-swe-agent in Docker sandboxes.
#
# NOT Harbor: MiniSweAgentHarness + SandboxTaskHooks + gateway traces
# (rllm.remote_runtime.enabled=false).
#
# This script only sets up the environment and launches; every training knob
# lives in config/ so that one decision is not split across two files:
#
#   config/config.yaml     Hydra entry + recipe.* (datasets, turn budget, sandbox)
#   config/rllm_grpo.yaml  rLLM side  (data lengths, sampling, gateway, GRPO)
#   config/verl_trainer.yaml  verl side  (model, FSDP actor/ref, vLLM rollout)
#
# Prerequisites (see README.md):
#   cp recipe/grpo/qwen3_5/.env.example recipe/grpo/qwen3_5/.env  # then edit
#   source .venv/bin/activate
#   uv pip install flash-linear-attention==0.5.2
#   bash recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh
#   rllm dataset pull harbor:swebench-verified
#   python recipe/grpo/qwen3_5/scripts/prepare_datasets.py --train-limit 24
#
# Env:
#   ENV_FILE          dotenv to source         (default: <recipe>/.env)
#   MODEL_PATH        HF id or local path      (default: Qwen/Qwen3.5-4B)
#   SANDBOX_BACKEND   docker|modal|daytona     (default: docker)
#   RLLM_AGENT_IMAGE  auto|skip|repo:tag       (default: auto)
#   TRAIN_LOG         transcript destination
#   HF_HUB_OFFLINE    set 0 to consult the hub
#
# Hardware: 8x 80GB GPU, single node (config/verl_trainer.yaml).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RECIPE_DIR="${REPO_ROOT}/recipe/grpo/qwen3_5"
cd "${REPO_ROOT}"

# `set -a` makes every assignment in the file an export; a value you exported
# yourself before launching is overwritten by the file, so override on the
# command line (`RLLM_HOME=... bash train_verl.sh`) or edit the file.
ENV_FILE="${ENV_FILE:-${RECIPE_DIR}/.env}"
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
fi

# The README's setup steps -- `rllm dataset pull`, prepare_datasets.py -- run in
# your own shell, so they read whatever RLLM_HOME *that* shell had. If it is not
# the one training uses, the run does not fail with "dataset not found"; it
# trains on a *different* dataset. Stop here instead.
: "${RLLM_HOME:?set RLLM_HOME in ${ENV_FILE} (cp .env.example .env), or export it}"
: "${HF_HOME:?set HF_HOME in ${ENV_FILE}}"
# Nothing puts the venv on PATH any more (`source .venv/bin/activate` does, and
# it is the documented way to run anything here -- see LEARN.md). Without it the
# first symptom is a ModuleNotFoundError several hundred lines into a traceback.
: "${VIRTUAL_ENV:?activate the venv first: source .venv/bin/activate}"

unset ROCR_VISIBLE_DEVICES 2>/dev/null || true
export VLLM_ALLREDUCE_USE_SYMM_MEM=0
# Eight FSDP workers, eight vLLM servers and the gateway each resolve the model
# id on startup. Unauthenticated, that blows through the Hub's 500-requests /
# 300s IP budget and the loser gets "Unable to load vocabulary from file" -- a
# rate-limit error wearing a corrupted-cache costume. The snapshot is already
# in $HF_HOME by this point, so read it from disk.
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export RLLM_AGENT_IMAGE="${RLLM_AGENT_IMAGE:-auto}"
# Stale sockets from a previous colocated run make vLLM's ZMQ handshake hang.
rm -f /tmp/rl-colocate-zmq-*.sock

# Metrics reach stdout only (rllm.trainer.logger=['console']) and most are
# printed from inside a Ray actor, so Hydra's own train.log captures almost
# nothing -- a few hundred bytes. Keep a full transcript instead: a multi-hour
# run whose pearson_corr / pg_loss / groups.* numbers scrolled off the terminal
# cannot be reasoned about afterwards.
LOG_DIR="${RLLM_RUN_DIR:-${REPO_ROOT}/outputs}/logs"
mkdir -p "${LOG_DIR}"
export RLLM_RUN_ID="${RLLM_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
TRAIN_LOG="${TRAIN_LOG:-${LOG_DIR}/train_${RLLM_RUN_ID}.log}"
echo "Transcript: ${TRAIN_LOG}"

# No `exec`, so the pipeline survives; `set -o pipefail` above keeps python's
# exit status rather than tee's.
python "${RECIPE_DIR}/train.py" "$@" 2>&1 | tee -a "${TRAIN_LOG}"
