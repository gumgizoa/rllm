"""Native rLLM SWE GRPO on verl — Qwen3.5-4B + mini-swe-agent.

Not Harbor: the rollout is ``AgentFlowEngine`` → ``SandboxTaskHooks`` (Docker)
→ ``MiniSweAgentHarness`` (the CLI runs *inside* the task sandbox and calls
back through the rLLM model gateway) → ``ShellScriptEvaluator`` (``tests/test.sh``
writes ``/logs/verifier/reward.txt``). ``rllm.remote_runtime.enabled=false``.

Datasets are the small locally-materialized benchmarks built by
``scripts/prepare_datasets.py``; both names are overridable from the CLI::

    python recipe/qwen3_5_swe_grpo/train.py \\
        recipe.train_dataset=rllm_swesmith_small \\
        recipe.val_dataset=swebench_verified_local

Normally launched via ``train_verl.sh`` / ``smoke_test.sh``.
"""

from __future__ import annotations

import logging
import os

import hydra
from omegaconf import DictConfig

from rllm.data.dataset import DatasetRegistry
from rllm.harnesses.mini_swe_agent import MiniSweAgentHarness
from rllm.trainer import AgentTrainer
from rllm.types import AgentConfig, Task

logger = logging.getLogger(__name__)


class StepLimitedMiniSweAgent(MiniSweAgentHarness):
    """mini-swe-agent with an explicit turn budget.

    Upstream defaults to ``agent.step_limit: 0`` (unlimited) and guards runtime
    with ``cost_limit`` instead — which is inert here, because the gateway-routed
    model has no litellm cost table and the harness sets
    ``MSWEA_COST_TRACKING=ignore_errors``. Left unbounded, the cumulative prompt
    keeps growing until vLLM rejects the turn with "maximum context length is N
    tokens", the agent's retries all fail, and the whole episode is thrown away
    as an error instead of being scored.

    ``-c`` normally *replaces* the default config rather than layering on it, so
    the builtin ``mini.yaml`` has to be named again before the override.
    """

    step_limit: int = 50

    def build_invocation(self, instruction: str, task: Task, config: AgentConfig) -> str:
        invocation = super().build_invocation(instruction, task, config)
        return invocation.replace(
            "mini-swe-agent --yolo ",
            f"mini-swe-agent --yolo -c mini.yaml -c agent.step_limit={int(self.step_limit)} ",
            1,
        )


def _load(name: str, split: str, limit: int | None, kind: str):
    # as_tasks=True roots each row at its ``task_path`` and merges the per-task
    # ``task.toml``. Without it every Task lands on ``dataset_dir="."`` and the
    # per-task verifier auto-detection fails with "No verifier configured".
    dataset = DatasetRegistry.load_dataset(name, split, as_tasks=True)
    if dataset is None:
        raise SystemExit(
            f"{kind} dataset '{name}/{split}' is not registered.\n"
            f"Build it first:  python recipe/qwen3_5_swe_grpo/scripts/prepare_datasets.py"
        )
    if limit and limit > 0 and limit < len(dataset):
        dataset = dataset.select(range(limit))
    logger.info("%s dataset %s/%s: %d tasks", kind, name, split, len(dataset))
    return dataset


# Measured on SWE-smith with this policy: a merged training row grows by roughly
# this much per mini-swe-agent turn (observation delta + sampled action).
TOKENS_PER_TURN = 1150


def _check_length_budget(config: DictConfig) -> None:
    """Fail fast when the turn budget and the length budget disagree.

    Three numbers have to line up and they live in three files, so they drift.
    Overrunning ``max_model_len`` mid-rollout is not a truncation: vLLM answers
    400, litellm's retries hit the same wall, and the episode is discarded whole.
    One run lost 28% of its rollouts that way before this check existed.
    """
    prompt = config.rllm.data.max_prompt_length
    response = config.rllm.data.max_response_length
    max_model_len = config.actor_rollout_ref.rollout.max_model_len
    row = prompt + response

    if max_model_len < row:
        raise SystemExit(
            f"max_model_len ({max_model_len}) is below the training row width "
            f"({prompt} + {response} = {row}). Rollouts that fill the row would be "
            f"rejected by vLLM and lost. Raise max_model_len to at least {row}."
        )

    steps = config.recipe.agent_step_limit
    needed = prompt + TOKENS_PER_TURN * steps
    if needed > max_model_len:
        raise SystemExit(
            f"agent_step_limit={steps} implies about {needed} tokens by the final turn "
            f"({prompt} prompt + ~{TOKENS_PER_TURN}/turn), over max_model_len "
            f"({max_model_len}). Either lower agent_step_limit to "
            f"{(max_model_len - prompt) // TOKENS_PER_TURN}, or raise "
            f"max_response_length / max_model_len together."
        )
    logger.info(
        "length budget: row=%d (prompt %d + response %d), max_model_len=%d, "
        "agent_step_limit=%d needs ~%d",
        row, prompt, response, max_model_len, steps, needed,
    )


@hydra.main(config_path="config", config_name="config", version_base=None)
def main(config: DictConfig) -> None:
    recipe = config.recipe
    _check_length_budget(config)

    train_dataset = _load(recipe.train_dataset, recipe.train_split, recipe.get("train_limit"), "train")
    val_dataset = _load(recipe.val_dataset, recipe.val_split, recipe.get("val_limit"), "val")

    # `auto` mounts a pre-built mini-swe-agent image into the task sandbox
    # instead of running `uv tool install` on every rollout (Docker only).
    # Same mechanism as `rllm eval --agent-image`.
    agent_image = os.environ.get("RLLM_AGENT_IMAGE", recipe.agent_image)
    os.environ["RLLM_AGENT_IMAGE"] = str(agent_image)

    agent_flow = StepLimitedMiniSweAgent(step_limit=recipe.agent_step_limit)
    agent_flow.configure({"agent_image": agent_image})

    trainer = AgentTrainer(
        backend="verl",
        agent_flow=agent_flow,
        config=config,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        sandbox_backend=os.environ.get("SANDBOX_BACKEND", recipe.sandbox_backend),
        sandbox_concurrency=recipe.get("sandbox_concurrency"),
    )
    trainer.train()


if __name__ == "__main__":
    main()
