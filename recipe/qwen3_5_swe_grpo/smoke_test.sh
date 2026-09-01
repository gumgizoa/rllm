#!/usr/bin/env bash
# Smoke test: does the whole native SWE GRPO loop run end to end?
#
# One tiny training batch, one validation task, short episodes. Enough to
# exercise rollout -> gateway traces -> reward -> advantage -> optimizer step
# without waiting on a real run.
set -euo pipefail

RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec "${RECIPE_DIR}/train_verl.sh" \
    recipe.train_limit=2 \
    recipe.val_limit=1 \
    recipe.agent_step_limit=25 \
    rllm.data.train_batch_size=2 \
    rllm.rollout.n=4 \
    rllm.rollout.train.max_tokens=2048 \
    rllm.rollout.val.max_tokens=2048 \
    rllm.data.max_prompt_length=8192 \
    rllm.data.max_response_length=12288 \
    rllm.workflow.n_parallel_tasks=4 \
    recipe.sandbox_concurrency=4 \
    rllm.trainer.total_batches=1 \
    rllm.trainer.total_epochs=1 \
    rllm.trainer.val_before_train=false \
    rllm.trainer.test_freq=-1 \
    rllm.trainer.save_freq=-1 \
    actor_rollout_ref.actor.ppo_mini_batch_size=2 \
    actor_rollout_ref.rollout.max_model_len=32768 \
    actor_rollout_ref.rollout.enforce_eager=true \
    "$@"
