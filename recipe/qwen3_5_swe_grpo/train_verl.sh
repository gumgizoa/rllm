#!/usr/bin/env bash
# Native rLLM SWE GRPO on verl — Qwen/Qwen3.5-4B + mini-swe-agent in Docker sandboxes.
#
# NOT Harbor: MiniSweAgentHarness + SandboxTaskHooks + gateway traces
# (rllm.remote_runtime.enabled=false).
#
# Prerequisites (see README.md):
#   source recipe/qwen3_5_swe_grpo/env.sh
#   rllm dataset pull harbor:swebench-verified
#   python recipe/qwen3_5_swe_grpo/scripts/prepare_datasets.py --train-limit 24
#   xargs -a "$RLLM_HOME/datasets/rllm_swesmith_small/images.txt" -P 4 -I{} docker pull {}
#
# Env:
#   SANDBOX_BACKEND=docker|modal|daytona   (default: docker)
#   RLLM_AGENT_IMAGE=auto|skip|repo:tag    (default: auto — pre-built mini-swe-agent mount)
#
# Hardware: 8x 80GB GPU, single node.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RECIPE_DIR="${REPO_ROOT}/recipe/qwen3_5_swe_grpo"
cd "${REPO_ROOT}"

# shellcheck source=/dev/null
source "${RECIPE_DIR}/env.sh"

MODEL_PATH="${MODEL_PATH:-Qwen/Qwen3.5-4B}"

unset ROCR_VISIBLE_DEVICES 2>/dev/null || true
export VLLM_ALLREDUCE_USE_SYMM_MEM=0
# Eight FSDP workers, eight vLLM servers and the gateway each resolve the model
# id on startup. Unauthenticated, that blows through the Hub's 500-requests /
# 300s IP budget and the loser gets "Unable to load vocabulary from file" -- a
# rate-limit error wearing a corrupted-cache costume. The snapshot is already
# in $HF_HOME by this point, so read it from disk. Set HF_HUB_OFFLINE=0 (or
# export HF_TOKEN) if you deliberately want the hub consulted.
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export RLLM_AGENT_IMAGE="${RLLM_AGENT_IMAGE:-auto}"
# Stale sockets from a previous colocated run make vLLM's ZMQ handshake hang.
rm -f /tmp/rl-colocate-zmq-*.sock

exec python "${RECIPE_DIR}/train.py" \
    rllm/backend=verl \
    +model.name="${MODEL_PATH}" \
    actor_rollout_ref.model.path="${MODEL_PATH}" \
    actor_rollout_ref.model.trust_remote_code=true \
    actor_rollout_ref.model.enable_gradient_checkpointing=true \
    actor_rollout_ref.hybrid_engine=true \
    `# Qwen3.5's vocab is 248320 tokens: one 23K-token sequence's logits in fp32` \
    `# is a single ~21 GB allocation and OOMs an 80 GB card. The fused` \
    `# linear+log-prob kernel computes log_probs/entropy in chunks off the hidden` \
    `# states and never builds the logits tensor. It consumes the packed` \
    `# (remove-padding) layout, so the two flags go together.` \
    actor_rollout_ref.model.use_fused_kernels=true \
    actor_rollout_ref.model.fused_kernel_options.impl_backend=torch \
    actor_rollout_ref.model.use_remove_padding=true \
    `# ...and ONE sequence per micro-batch is what makes that packing safe here:` \
    `# Qwen3.5 interleaves GatedDeltaNet (linear-attention) layers with full` \
    `# attention, and a recurrent layer would carry state straight across a` \
    `# packed sample boundary. Full attention has cu_seqlens; linear attention` \
    `# does not. Do not raise ppo_micro_batch_size_per_gpu or turn on dynamic` \
    `# (token-budget) batching without checking that first.` \
    actor_rollout_ref.actor.use_dynamic_bsz=false \
    actor_rollout_ref.actor.ppo_micro_batch_size_per_gpu=1 \
    actor_rollout_ref.actor.ppo_mini_batch_size=4 \
    actor_rollout_ref.actor.optim.lr=1e-6 \
    actor_rollout_ref.actor.entropy_coeff=0.0 \
    actor_rollout_ref.actor.fsdp_config.param_offload=true \
    actor_rollout_ref.actor.fsdp_config.optimizer_offload=true \
    actor_rollout_ref.ref.log_prob_micro_batch_size_per_gpu=1 \
    actor_rollout_ref.ref.fsdp_config.param_offload=true \
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.mode=async \
    actor_rollout_ref.rollout.tensor_model_parallel_size=1 \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.50 \
    `# max_prompt_length + max_response_length. A 40-turn SWE-smith episode runs` \
    `# ~900 prompt tokens/turn, and anything that overruns this comes back as an` \
    `# HTTP 400 mid-rollout rather than a truncation -- the episode is then lost` \
    `# entirely, not just clipped. Keep it >= the training row width.` \
    actor_rollout_ref.rollout.max_model_len=49152 \
    actor_rollout_ref.rollout.enforce_eager=false \
    actor_rollout_ref.rollout.free_cache_engine=true \
    actor_rollout_ref.rollout.log_prob_micro_batch_size_per_gpu=1 \
    actor_rollout_ref.rollout.val_kwargs.do_sample=true \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.reasoning_parser=qwen3 \
    `# mini-swe-agent v2 requires the model to answer with a 'bash' TOOL CALL,` \
    `# and its litellm client always sends tool_choice="auto" -- which vLLM` \
    `# rejects unless auto tool choice is on. qwen3_xml matches Qwen3.5's` \
    `# <tool_call><function=..><parameter=..> template markup.` \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.enable_auto_tool_choice=true \
    +actor_rollout_ref.rollout.engine_kwargs.vllm.tool_call_parser=qwen3_xml \
    trainer.n_gpus_per_node=8 \
    trainer.nnodes=1 \
    trainer.default_hdfs_dir=null \
    trainer.resume_mode=disable \
    "$@"
