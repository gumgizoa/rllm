"""Native rLLM SWE GRPO on verl — Qwen3.5 + a CLI harness in Docker sandboxes.

Not Harbor: the rollout is ``AgentFlowEngine`` → ``SandboxTaskHooks`` (Docker)
→ harness (the agent runs *inside* the task sandbox and calls back through the
rLLM model gateway) → ``ShellScriptEvaluator`` (``tests/test.sh`` writes
``/logs/verifier/reward.txt``). ``rllm.remote_runtime.enabled=false``.

The harness is chosen by ``recipe.agent`` and the workflow on it by
``recipe.workflow.name`` (``workflows.WORKFLOWS``; null = none):

* ``mini-swe-agent`` (default) — ``StepLimitedMiniSweAgent`` below, Qwen3.5-4B;
  no workflow.
* ``openhands-sdk`` — ``workflow_harness.OpenHandsSdkWorkflow``; with
  ``recipe.workflow.name=aidlc_v4`` it ships the AI-DLC workflow documents into
  the sandbox, swaps the SDK's system prompt, and scores compliance beside the
  verifier. A list (``recipe.workflow.name=[none,aidlc_v4,speckit_bug]``) gives
  each task one of them, fixed per task (``recipe.workflow.seed``), and
  ``recipe.workflow.val_name`` pins the whole validation set to one.
  ``config/variant/`` holds ready-made selections::

    bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b          # 9B, no AI-DLC
    bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc    # 9B + AI-DLC
    bash recipe/grpo/qwen3_5/train_verl.sh variant=openhands_9b_aidlc_swegym  # 9B + AI-DLC on SWE-Gym

Datasets are the small locally-materialized benchmarks built by
``scripts/prepare_datasets.py`` (SWE-smith / SWE-bench Verified) or
``scripts/prepare_swegym.py`` (SWE-Gym, SkyRL-v0-293-data); both names are
overridable from the CLI::

    python recipe/grpo/qwen3_5/train.py \\
        recipe.train_dataset=rllm_swesmith_small \\
        recipe.val_dataset=swebench_verified_local

Normally launched via ``train_verl.sh`` / ``smoke_test.sh``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import hydra
from omegaconf import DictConfig, ListConfig

from rllm.data.dataset import DatasetRegistry
from rllm.harnesses.mini_swe_agent import MiniSweAgentHarness
from rllm.trainer import AgentTrainer
from rllm.trainer.algorithms.transform import _default_traj_grouping_hook
from rllm.types import AgentConfig, Task
from rllm.workflows.workflow import TerminationReason

logger = logging.getLogger(__name__)

# This recipe's modules are imported by package path (``recipe.grpo.qwen3_5.*``), the
# name ``rllm eval --agent`` uses too, so a process never holds two copies of them (two
# ``WORKFLOWS`` registries, two classes for one harness). ``python .../train.py`` puts
# only this directory on sys.path; Ray hands the driver's sys.path to its workers,
# which unpickle the harness and hooks by the same name.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


COMPLIANCE_MODES = ("mul", "add")


def make_budget_scaled_grouping_hook(
    scale: float,
    compliance_mode: str | None = None,
    compliance_lam: float = 0.2,
    compliance_signals: str | tuple[str, ...] | None = None,
):
    """Return a ``traj_grouping_hook`` that applies SWE-Master's reward shaping.

    The hook runs before trajectory groups are built, so the scaled reward is
    what RLOO sees. ``is_correct`` is deliberately left alone: rejection
    sampling and the solve_all/solve_none metrics read it, and "solved but
    slowly" is still solved for those purposes.

    ``compliance_mode`` folds in the workflow's compliance signal
    (``compliance_signals``, in [0, 1], e.g. ``aidlc/compliance`` set by
    ``workflows/aidlc_v4/reward``'s ``AidlcComplianceEvaluator``) before the budget scale.
    A run mixing workflows passes each one's signal; they are named per
    workflow, so a trajectory carries at most one of them:

    * ``"mul"``: ``reward = verifier * compliance`` -- an unsolved rollout stays
      at 0 however well it followed the workflow, and a solved one earns only
      as much of the 1 as it complied;
    * ``"add"``: ``reward = verifier + lam * compliance`` -- compliance is a bonus
      of at most ``lam``, earned whether or not the task was solved;
    * ``None``: the verifier reward alone.

    The budget scale then applies to the result, so following the workflow
    cannot buy back what running out of turns costs. A trajectory without the
    signal (no workflow scorer, or its scoring failed) keeps the verifier
    reward alone -- in ``"mul"`` it is not zeroed for a scoring failure.

    One caveat: the trainer runs the same hook over validation episodes, so
    ``val/reward_*`` is scaled -- and carries the compliance term -- too.
    ``val/accuracy`` is built from ``is_correct`` and is not affected.
    """
    if not 0.0 <= scale <= 1.0:
        raise ValueError(f"budget_reward_scale must be in [0, 1], got {scale}")
    if compliance_mode is not None and compliance_mode not in COMPLIANCE_MODES:
        raise ValueError(f"recipe.workflow.compliance_reward.mode must be one of {COMPLIANCE_MODES}, got {compliance_mode!r}")
    signals = (compliance_signals,) if isinstance(compliance_signals, str) else tuple(compliance_signals or ())
    if compliance_mode is not None and not signals:
        raise ValueError("a compliance mode needs the signal it reads (WorkflowSpec.reward_signal)")
    if compliance_mode == "add" and compliance_lam < 0.0:
        raise ValueError(f"recipe.workflow.compliance_reward.lam must be >= 0, got {compliance_lam}")

    def hook(episodes, transform_config, compact_filtering_config=None):
        for episode in episodes:
            exhausted = episode.termination_reason in BUDGET_EXHAUSTED
            for trajectory in episode.trajectories:
                if trajectory.reward is None:
                    continue
                carried = trajectory.signals or {}
                c = next((carried[name] for name in signals if name in carried), None) if compliance_mode else None
                if c is not None:
                    if compliance_mode == "mul":
                        trajectory.reward = trajectory.reward * float(c)
                    else:
                        trajectory.reward = trajectory.reward + compliance_lam * float(c)
                if exhausted and scale != 1.0:
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


def _renderer_enable_thinking(config: DictConfig) -> bool | None:
    """``rllm.gateway.renderer_kwargs.enable_thinking`` when set, else ``None``.

    Turn 1 of an openhands-sdk episode is rendered by vLLM's chat template,
    turns 2+ by the gateway's renderer. Both take an ``enable_thinking`` switch
    and they must agree, or the policy is trained on a different shape than it
    sampled from. The renderer kwarg is the single source of truth; the
    harness forwards the same value to the SDK as a chat-template kwarg.
    """
    kwargs = ((config.get("rllm") or {}).get("gateway") or {}).get("renderer_kwargs") or {}
    value = kwargs.get("enable_thinking")
    return None if value is None else bool(value)


def _workflow_names(recipe: DictConfig) -> tuple[tuple[str, ...], str | None]:
    """(``recipe.workflow.name`` as registered names, ``recipe.workflow.val_name``); ``none`` = the plain harness."""
    from recipe.grpo.qwen3_5.workflows import parse_workflows

    workflow = recipe.get("workflow") or {}
    name = workflow.get("name")
    pool = parse_workflows(list(name) if isinstance(name, ListConfig) else name)
    val = parse_workflows(workflow.get("val_name"))
    if len(val) > 1:
        raise SystemExit(f"recipe.workflow.val_name names one workflow, got {list(val)}")
    return pool, (val[0] if val else None)


def _build_agent_flow(recipe: DictConfig, config: DictConfig):
    """Pick the harness from ``recipe.agent`` and the workflow on it from ``recipe.workflow.name``.

    The two harnesses share one ``agent_step_limit`` so a run's turn budget
    means the same thing whichever agent is under it. A workflow needs a
    system-prompt override to work at all, and mini-swe-agent has no
    equivalent seam, so a workflow there is refused rather than run without it.
    ``recipe.workflow.name: null`` is the plain harness; a list is a mix, each
    task routed to one of them (``workflow_harness.WorkflowMixin``), and
    ``val_name`` is routed too, for the validation tasks ``_pin_workflow`` marks.
    """
    agent = str(recipe.get("agent", "mini-swe-agent"))
    step_limit = int(recipe.agent_step_limit)
    workflow = recipe.get("workflow") or {}
    pool, val_name = _workflow_names(recipe)
    name = pool[0] if len(pool) == 1 else (list(pool) or None)

    if agent == "mini-swe-agent":
        if any(n != "none" for n in (*pool, *((val_name,) if val_name else ()))):
            raise SystemExit(
                f"recipe.workflow.name={name!r} requires recipe.agent=openhands-sdk "
                "(mini-swe-agent has no system-prompt seam for the workflow). "
                "Use `variant=openhands_9b_aidlc` or set recipe.agent explicitly."
            )
        return StepLimitedMiniSweAgent(step_limit=step_limit)

    if agent == "openhands-sdk":
        # Imported lazily: the harness pulls in the openhands-sdk harness and,
        # for a workflow with a scorer, its evaluator.
        from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow

        return OpenHandsSdkWorkflow(
            step_limit=step_limit,
            enable_thinking=_renderer_enable_thinking(config),
            workflow=name,
            workflow_seed=int(workflow.get("seed", 0)),
            pinned_workflows=(val_name,) if val_name else (),
            instruction_position=str(workflow.get("instruction_position", "suffix")),
        )

    raise SystemExit(f"recipe.agent must be 'mini-swe-agent' or 'openhands-sdk', got {agent!r}")


def _workflow_reward(recipe: DictConfig, agent_flow) -> tuple[tuple[str, ...] | None, str | None, float]:
    """(signals folded into the reward, "mul" / "add", lam for "add"); ``(None, None, 0.0)`` when off.

    Scoring itself follows the harness: a workflow with a scorer for it is
    always scored -- and logged as ``<workflow>/*`` episode metrics -- so the
    verifier-only arm shows the same curves as the rewarded one. The signal
    enters the reward only with ``recipe.workflow.compliance_reward.enable``.

    With no workflow there is nothing to fold in, so ``compliance_reward.enable`` is
    ignored (a rewarded variant run with ``recipe.workflow.name=null`` is its
    verifier-only baseline). A workflow without a scorer for this harness,
    asked to reward, is an error rather than a silent verifier-only run.

    In a mix every workflow is held to that, and ``none`` trains on the
    verifier reward. RLOO here does not divide by the group's std
    (``norm_adv_by_std_in_grpo: false``), so a group's advantages scale with
    its rewards: under ``mul`` a low-compliance workflow's groups pull far less
    than ``none``'s.
    """
    reward = (recipe.get("workflow") or {}).get("compliance_reward") or {}
    if not bool(reward.get("enable", False)):
        return None, None, 0.0
    routes = agent_flow.routes() if hasattr(agent_flow, "routes") else {}
    flows = {name: flow for name, flow in routes.items() if flow.workflow_spec is not None}
    if not flows:
        logger.warning("recipe.workflow.compliance_reward.enable is set but there is no workflow; training on the verifier reward alone")
        return None, None, 0.0
    for name, flow in flows.items():
        if flow.workflow_spec.reward_signal is None or flow.evaluation_policy is None:
            raise SystemExit(f"recipe.workflow.compliance_reward.enable=true: workflow {name!r} has no compliance scorer for recipe.agent={flow.name!r}")
    if len(flows) < len(routes):
        logger.warning("recipe.workflow.compliance_reward: the 'none' route trains on the verifier reward alone, beside %s", sorted(flows))
    return tuple(flow.workflow_spec.reward_signal for flow in flows.values()), str(reward.get("mode", "mul")), float(reward.get("lam", 0.2))


def _build_hooks(agent_flow, sandbox_backend: str, hide_git_history: bool = False):
    """``SandboxTaskHooks`` with the harness's workflow scorer, or ``None`` to let AgentTrainer auto-wire.

    The scorer is the harness's ``evaluation_policy`` -- the same one
    ``rllm eval`` hands its hooks -- so training and evaluation measure
    compliance the same way.

    ``hide_git_history`` has to reach hooks built here: AgentTrainer only wires
    it into the hooks it builds itself, and refuses caller-built hooks that lack
    it (a workflow arm with ``recipe.hide_git_history=true`` would otherwise fail
    at startup rather than run with the history in place).
    """
    evaluation = getattr(agent_flow, "evaluation_policy", None)
    if evaluation is None:
        return None
    from rllm.hooks import SandboxTaskHooks

    return SandboxTaskHooks(evaluation=evaluation, sandbox_backend=sandbox_backend, hide_git_history=hide_git_history)


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


def _pin_workflow(dataset, name: str | None) -> None:
    """Mark every task of ``dataset`` to run under workflow ``name`` (``recipe.workflow.val_name``)."""
    if name is None:
        return
    from recipe.grpo.qwen3_5.workflows import WORKFLOW_KEY

    for task in dataset.get_data():
        task.metadata[WORKFLOW_KEY] = name


def _log_workflow_split(agent_flow, train_dataset, val_dataset) -> None:
    """How many tasks of each set run under each workflow, from the harness's own routing."""
    if not hasattr(agent_flow, "workflow_for") or len(agent_flow.routes()) < 2:
        return
    from collections import Counter

    for kind, dataset in (("train", train_dataset), ("val", val_dataset)):
        counts = Counter(agent_flow.workflow_for(task) for task in dataset.get_data())
        logger.info("workflow mix, %s tasks: %s", kind, dict(sorted(counts.items())))


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

    agent_flow = _build_agent_flow(recipe, config)
    agent_flow.configure({"agent_image": agent_image})
    _pin_workflow(val_dataset, _workflow_names(recipe)[1])
    _log_workflow_split(agent_flow, train_dataset, val_dataset)
    reward_signal, compliance_mode, compliance_lam = _workflow_reward(recipe, agent_flow)
    sandbox_backend = os.environ.get("SANDBOX_BACKEND", recipe.sandbox_backend)
    hooks = _build_hooks(agent_flow, sandbox_backend, bool(recipe.hide_git_history))
    logger.info(
        "agent flow: %s (step_limit=%s, workflow=%s, enable_thinking=%s, compliance scored=%s, reward=%s mode=%s lam=%s)",
        type(agent_flow).__name__,
        recipe.agent_step_limit,
        getattr(agent_flow, "workflow", None),
        getattr(agent_flow, "enable_thinking", None),
        hooks is not None,
        reward_signal,
        compliance_mode,
        compliance_lam if compliance_mode == "add" else "-",
    )

    trainer = AgentTrainer(
        backend="verl",
        agent_flow=agent_flow,
        config=config,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        hooks=hooks,
        sandbox_backend=sandbox_backend,
        sandbox_concurrency=recipe.get("sandbox_concurrency"),
        # Same mechanism as `rllm eval --hide-git-history`.
        hide_git_history=bool(recipe.hide_git_history),
        # Passed through **kwargs to UnifiedTrainer (verl_launcher.py forwards them).
        traj_grouping_hook=make_budget_scaled_grouping_hook(float(recipe.budget_reward_scale), compliance_mode, compliance_lam, reward_signal),
    )
    trainer.train()


if __name__ == "__main__":
    main()
