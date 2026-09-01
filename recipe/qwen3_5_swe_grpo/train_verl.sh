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
#   config/grpo_verl.yaml  rLLM side  (data lengths, sampling, gateway, GRPO)
#   config/verl_fsdp.yaml  verl side  (model, FSDP actor/ref, vLLM rollout)
#
# Prerequisites (see README.md):
#   source recipe/qwen3_5_swe_grpo/env.sh
#   uv pip install flash-linear-attention==0.5.2
#   bash recipe/qwen3_5_swe_grpo/scripts/apply_verl_patches.sh
#   rllm dataset pull harbor:swebench-verified
#   python recipe/qwen3_5_swe_grpo/scripts/prepare_datasets.py --train-limit 24
#
# Env:
#   MODEL_PATH        HF id or local path      (default: Qwen/Qwen3.5-4B)
#   SANDBOX_BACKEND   docker|modal|daytona     (default: docker)
#   RLLM_AGENT_IMAGE  auto|skip|repo:tag       (default: auto)
#   TRAIN_LOG         transcript destination
#   HF_HUB_OFFLINE    set 0 to consult the hub
#
# Hardware: 8x 80GB GPU, single node (config/verl_fsdp.yaml).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RECIPE_DIR="${REPO_ROOT}/recipe/qwen3_5_swe_grpo"
cd "${REPO_ROOT}"

# shellcheck source=/dev/null
source "${RECIPE_DIR}/env.sh"

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
TRAIN_LOG="${TRAIN_LOG:-${LOG_DIR}/train_$(date +%Y%m%d_%H%M%S).log}"
echo "Transcript: ${TRAIN_LOG}"

# No `exec`, so the pipeline survives; `set -o pipefail` above keeps python's
# exit status rather than tee's.
python "${RECIPE_DIR}/train.py" "$@" 2>&1 | tee -a "${TRAIN_LOG}"
