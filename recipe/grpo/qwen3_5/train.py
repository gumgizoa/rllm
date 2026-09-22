"""Native rLLM SWE GRPO on verl — Qwen3.5 + a CLI harness in Docker sandboxes.

Not Harbor: the rollout is ``AgentFlowEngine`` → ``SandboxTaskHooks`` (Docker)
→ harness (the agent runs *inside* the task sandbox and calls back through the
rLLM model gateway) → ``ShellScriptEvaluator`` (``tests/test.sh`` writes
``/logs/verifier/reward.txt``). ``rllm.remote_runtime.enabled=false``.

The harness is chosen by ``recipe.agent``:

* ``mini-swe-agent`` (default) — ``StepLimitedMiniSweAgent`` below, Qwen3.5-4B.
* ``openhands-sdk`` — ``aidlc_flow.StepLimitedOpenHandsSdk``; with
  ``recipe.aidlc.enable=true`` it becomes ``AidlcOpenHandsSdkHarness``, which
  ships the AI-DLC workflow documents into the sandbox and swaps the SDK's
  system prompt. ``config/variant/`` holds ready-made selections::

    bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b          # 9B, no AI-DLC
    bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc    # 9B + AI-DLC

Datasets are the small locally-materialized benchmarks built by
``scripts/prepare_datasets.py``; both names are overridable from the CLI::

    python recipe/grpo/qwen3_5/train.py \\
        recipe.train_dataset=rllm_swesmith_small \\
        recipe.val_dataset=swebench_verified_local

Normally launched via ``train_verl.sh`` / ``smoke_test.sh``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import hydra
from omegaconf import DictConfig

from rllm.data.dataset import DatasetRegistry
from rllm.harnesses.mini_swe_agent import MiniSweAgentHarness
from rllm.trainer import AgentTrainer
from rllm.trainer.algorithms.transform import _default_traj_grouping_hook
from rllm.types import AgentConfig, Task
from rllm.workflows.workflow import TerminationReason

logger = logging.getLogger(__name__)

# SWE-Master's "budget exhaustion" terminations (arXiv 2602.03411, sec. 3.4.2:
# TIMEOUT, MAX_STEPS, MAX_TOKENS). The rollout is graded on whatever the
# agent left in the repo -- the verifier runs regardless of how the agent
# stopped, which is the paper's "forced submission" -- and its reward is then
# scaled by a constant below 1. Not in the set: VERIFIER_TIMEOUT and ERROR,
# which are infrastructure and are dropped by compact_filtering instead.
BUDGET_EXHAUSTED = frozenset(
    {
        TerminationReason.MAX_TURNS_EXCEEDED,  # paper's MAX_STEPS
        TerminationReason.MAX_PROMPT_LENGTH_EXCEEDED,  # paper's MAX_TOKENS: vLLM 400 on the cumulative prompt
        TerminationReason.AGENT_TIMEOUT,  # paper's TIMEOUT: task.toml [agent] timeout_sec
    }
)


def make_budget_scaled_grouping_hook(scale: float):
    """Return a ``traj_grouping_hook`` that applies SWE-Master's reward shaping.

    The hook runs before trajectory groups are built, so the scaled reward is
    what RLOO sees. ``is_correct`` is deliberately left alone: rejection
    sampling and the solve_all/solve_none metrics read it, and "solved but
    slowly" is still solved for those purposes.

    One caveat: the trainer runs the same hook over validation episodes, so
    ``val/reward_*`` is scaled too. ``val/accuracy`` is built from
    ``is_correct`` and is not affected.
    """
    if not 0.0 <= scale <= 1.0:
        raise ValueError(f"budget_reward_scale must be in [0, 1], got {scale}")

    def hook(episodes, transform_config, compact_filtering_config=None):
        if scale != 1.0:
            for episode in episodes:
                if episode.termination_reason not in BUDGET_EXHAUSTED:
                    continue
                for trajectory in episode.trajectories:
                    if trajectory.reward is not None:
                        trajectory.reward = trajectory.reward * scale
        return _default_traj_grouping_hook(episodes, transform_config, compact_filtering_config)

    return hook


# Episode logs are keyed by <project>/<experiment>, which is stable across runs,
# so two runs of this recipe wrote into the same train_step_N_epoch_0 directory:
# one merged 88 old episodes with 64 new ones, and the next silently *overwrote*
# the previous run's files, because the episode filename is a hash of the task
# plus the rollout index and both runs draw the same tasks in the same order.
# Post-hoc analysis then reads two runs as one. Stamp a run id so each launch
# owns its directory. Set before Hydra composes, since the config interpolates
# ``${oc.env:RLLM_RUN_ID}``; ``setdefault`` lets train_verl.sh pin the same id it
# puts on the transcript filename, and a bare ``python train.py`` still gets one.
os.environ.setdefault("RLLM_RUN_ID", time.strftime("%Y%m%d_%H%M%S"))


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


RECIPE_DIR = Path(__file__).resolve().parent


def _recipe_path(value: str | None) -> Path | None:
    """Resolve a ``recipe.aidlc.*`` path; relative paths are relative to this recipe dir."""
    if value is None:
        return None
    path = Path(str(value)).expanduser()
    return path if path.is_absolute() else RECIPE_DIR / path


def _build_agent_flow(recipe: DictConfig):
    """Pick the harness from ``recipe.agent`` and layer AI-DLC on it when asked.

    The two harnesses share one ``agent_step_limit`` so a run's turn budget
    means the same thing whichever agent is under it. AI-DLC is a property of
    the openhands-sdk harness only: it needs a system-prompt override to work
    at all, and mini-swe-agent has no equivalent seam.
    """
    agent = str(recipe.get("agent", "mini-swe-agent"))
    step_limit = int(recipe.agent_step_limit)
    aidlc = recipe.get("aidlc") or {}
    aidlc_enabled = bool(aidlc.get("enable", False))

    if agent == "mini-swe-agent":
        if aidlc_enabled:
            raise SystemExit(
                "recipe.aidlc.enable=true requires recipe.agent=openhands-sdk "
                "(mini-swe-agent has no system-prompt seam for the workflow). "
                "Use `variant=openhands_9b_aidlc` or set recipe.agent explicitly."
            )
        return StepLimitedMiniSweAgent(step_limit=step_limit)

    if agent == "openhands-sdk":
        # Imported lazily and by file location: the module sits beside this
        # script, and `python recipe/grpo/qwen3_5/train.py` puts that dir on
        # sys.path[0].
        from aidlc_flow import AidlcOpenHandsSdkHarness, StepLimitedOpenHandsSdk

        if not aidlc_enabled:
            return StepLimitedOpenHandsSdk(step_limit=step_limit)
        return AidlcOpenHandsSdkHarness(
            step_limit=step_limit,
            docs_dir=_recipe_path(aidlc.get("docs_dir", "aidlc")),
            container_dir=str(aidlc.get("container_dir", "/ai-dlc")),
            instruction_file=_recipe_path(aidlc.get("instruction_file")),
            system_prompt_file=_recipe_path(aidlc.get("system_prompt_file")),
        )

    raise SystemExit(f"recipe.agent must be 'mini-swe-agent' or 'openhands-sdk', got {agent!r}")


def _load(name: str, split: str, limit: int | None, kind: str):
    # as_tasks=True roots each row at its ``task_path`` and merges the per-task
    # ``task.toml``. Without it every Task lands on ``dataset_dir="."`` and the
    # per-task verifier auto-detection fails with "No verifier configured".
    dataset = DatasetRegistry.load_dataset(name, split, as_tasks=True)
    if dataset is None:
        raise SystemExit(f"{kind} dataset '{name}/{split}' is not registered.\nBuild it first:  python recipe/grpo/qwen3_5/scripts/prepare_datasets.py")
    if limit and limit > 0 and limit < len(dataset):
        dataset = dataset.select(range(limit))
    logger.info("%s dataset %s/%s: %d tasks", kind, name, split, len(dataset))
    return dataset


@hydra.main(config_path="config", config_name="config", version_base=None)
def main(config: DictConfig) -> None:
    recipe = config.recipe

    train_dataset = _load(recipe.train_dataset, recipe.train_split, recipe.get("train_limit"), "train")
    val_dataset = _load(recipe.val_dataset, recipe.val_split, recipe.get("val_limit"), "val")

    # `auto` mounts a pre-built agent image (mini-swe-agent or the openhands-sdk
    # venv, per harness) into the task sandbox instead of installing on every
    # rollout (Docker only). Same mechanism as `rllm eval --agent-image`.
    agent_image = os.environ.get("RLLM_AGENT_IMAGE", recipe.agent_image)
    os.environ["RLLM_AGENT_IMAGE"] = str(agent_image)

    agent_flow = _build_agent_flow(recipe)
    agent_flow.configure({"agent_image": agent_image})
    logger.info("agent flow: %s (step_limit=%s, aidlc=%s)", type(agent_flow).__name__, recipe.agent_step_limit, bool((recipe.get("aidlc") or {}).get("enable", False)))

    trainer = AgentTrainer(
        backend="verl",
        agent_flow=agent_flow,
        config=config,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        sandbox_backend=os.environ.get("SANDBOX_BACKEND", recipe.sandbox_backend),
        sandbox_concurrency=recipe.get("sandbox_concurrency"),
        # Passed through **kwargs to UnifiedTrainer (verl_launcher.py forwards them).
        traj_grouping_hook=make_budget_scaled_grouping_hook(float(recipe.budget_reward_scale)),
    )
    trainer.train()


if __name__ == "__main__":
    main()
