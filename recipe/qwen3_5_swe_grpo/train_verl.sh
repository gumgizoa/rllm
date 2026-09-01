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

# Metrics reach stdout only (rllm.trainer.logger=['console']) and most are
# printed from inside a Ray actor, so Hydra's own train.log captures almost
# nothing -- a few hundred bytes. Keep a full transcript instead: a multi-hour
# run whose pearson_corr / pg_loss / groups.* numbers scrolled off the terminal
# cannot be reasoned about afterwards. Override with TRAIN_LOG=/path.
LOG_DIR="${RLLM_RUN_DIR:-${REPO_ROOT}/outputs}/logs"
mkdir -p "${LOG_DIR}"
TRAIN_LOG="${TRAIN_LOG:-${LOG_DIR}/train_$(date +%Y%m%d_%H%M%S).log}"
echo "Transcript: ${TRAIN_LOG}"

# No `exec`, so the pipeline survives; `set -o pipefail` above keeps python's
# exit status rather than tee's.
python "${RECIPE_DIR}/train.py" \
    rllm/backend=verl \
    +model.name="${MODEL_PATH}" \
    actor_rollout_ref.model.path="${MODEL_PATH}" \
    actor_rollout_ref.model.trust_remote_code=true \
    `# fsdp2 (per-parameter DTensor sharding) beats fsdp1 on every axis measured` \
    `# here: 22.8 vs 27.1 GB peak, 215 vs 210 tok/s, update_actor 46.9 vs 62.8 s,` \
    `# pearson 0.999745 vs 0.999662, and none of FSDP1's state_dict deprecation` \
    `# warnings. verl also patches this model's vision tower specifically for the` \
    `# fsdp2 cpu_offload path.` \
    actor_rollout_ref.actor.strategy=fsdp2 \
    actor_rollout_ref.ref.strategy=fsdp2 \
    `# Sequence parallelism is NOT usable with this model. ulysses_sp>1 slices` \
    `# inputs_embeds without padding while verl's fused head pads-then-slices the` \
    `# labels, so it dies in flash_attn cross_entropy on a shape mismatch; and even` \
    `# past that, the 24 GatedDeltaNet layers would each restart from a zero` \
    `# recurrent state (measured 10.9% error on the op). Long context is handled by` \
    `# raising max_model_len instead -- 73.5K sequences train at 36 GB/GPU.` \
    actor_rollout_ref.actor.ulysses_sequence_parallel_size=1 \
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
    `# ...and ONE sequence per micro-batch is what makes that packing safe.` \
    `# The packed forward is input_ids.values().unsqueeze(0) -> (1, total_nnz)` \
    `# (verl fsdp/transformer_impl.py), so sequence boundaries survive only in` \
    `# position_ids. Full attention recovers them via cu_seqlens; Qwen3.5's` \
    `# GatedDeltaNet layers (24 of 32) cannot -- HF's forward signature is` \
    `# (hidden_states, cache_params, attention_mask) and its fla call passes no` \
    `# cu_seqlens -- so a recurrent layer carries state across the boundary.` \
    `#` \
    `# This does NOT crash. Measured at ppo_micro_batch_size_per_gpu=2:` \
    `#   rollout_actor_probs_pearson_corr  0.9998 -> 0.9697` \
    `#   rollout_probs_diff_max            0.23   -> 1.00` \
    `# i.e. the actor's log-probs stop matching what the policy sampled, while` \
    `# throughput barely moves (193 -> 203 tok/s). Silent corruption for ~5%.` \
    `# Same constraint applies to ref/rollout log_prob_micro_batch_size_per_gpu:` \
    `# all three forwards share this model-level packing setting.` \
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
    "$@" 2>&1 | tee -a "${TRAIN_LOG}"
