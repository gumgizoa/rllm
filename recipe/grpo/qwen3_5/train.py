"""Native rLLM SWE GRPO on verl - Qwen3.5-9B + openhands-sdk or mini-swe-agent.

Not Harbor: the rollout is ``AgentFlowEngine`` → ``SandboxTaskHooks`` (Docker)
→ the harness ``recipe.harness`` names (``MiniSweAgentHarness`` or
``OpenHandsSdkHarness``; the agent runs *inside* the task sandbox and calls
back through the rLLM model gateway) → ``ShellScriptEvaluator`` (``tests/test.sh``
writes ``/logs/verifier/reward.txt``). ``rllm.remote_runtime.enabled=false``.

The harness is chosen by ``recipe.harness`` and the workflow on it by
``recipe.workflow.name`` (``workflows.WORKFLOWS``; null = none):

* ``mini-swe-agent`` — ``StepLimitedMiniSweAgent`` below; no workflow.
* ``openhands-sdk`` (default) — ``workflow_harness.OpenHandsSdkWorkflow``; with
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
from omegaconf import DictConfig, ListConfig, OmegaConf

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


COMPLIANCE_MODES = ("mul", "add", "wsum")
PENALTY_GATES = ("all", "unsolved")


def make_budget_scaled_grouping_hook(
    scale: float,
    compliance_mode: str | None = None,
    compliance_lam: float = 0.2,
    compliance_signals: str | tuple[str, ...] | None = None,
    compliance_floor: float = 0.0,
    compliance_weight: float = 0.3,
    penalty_signals: str | tuple[str, ...] | None = None,
    penalty_weight: float = 0.0,
    penalty_gate: str = "all",
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

    * ``"mul"``: ``reward = verifier * (floor + (1 - floor) * compliance)`` -- an
      unsolved rollout stays at 0 however well it followed the workflow, and a
      solved one earns at least ``compliance_floor`` and the rest as it complied.
      With the default floor 0 this is ``verifier * compliance``, where a solved
      rollout with low compliance scores about like an unsolved one and RLOO
      pushes against it; a floor keeps every solve above every failure;
    * ``"add"``: ``reward = verifier + lam * compliance`` -- compliance is a bonus
      of at most ``lam``, earned whether or not the task was solved;
    * ``"wsum"``: ``reward = (1 - weight) * verifier + weight * compliance`` -- a
      weighted sum in [0, 1]; an unsolved rollout earns up to ``weight`` for
      following the workflow, a solved one at least ``1 - weight``, so with
      weight < 0.5 every solve still outranks every failure. RLOO here does not
      divide by the group std, so this is not ``"add"`` rescaled: the same ratio
      under ``"add"`` (lam = weight / (1 - weight)) gives advantages 1 / (1 - weight)
      times larger;
    * ``None``: the verifier reward alone.

    ``penalty_signals`` / ``penalty_weight`` (w) fold in a penalty term after the mode above and
    before the budget scale::

        reward = (1 - w) * <mode reward> + w * P

    ``P`` is the workflow's ``penalty_signal`` in [0, 1], 1 when every penalty rule was kept
    (``WorkflowSpec.penalty_signal``, e.g. ``speckit_bug/penalty``: the mean of its log-only
    ``*.penalty.*`` rubric items -- gold files named, a related existing test run after the last edit,
    reports that describe the change). With ``penalty_gate="unsolved"`` a solved rollout is given
    P = 1, so only failures are told apart by it (``verifier`` is the reward before shaping, 0 or 1
    for a pass/fail verifier). A rollout without the signal counts as P = 1 (the group shares the
    task, so this is a constant shift within it, and every group keeps the same ``1 - w`` scale).
    ``penalty_weight`` 0 (the default) leaves the mode reward alone; with w = 0.2 and ``mul`` floor
    0.7 a solve earns 0.56..0.8 from the first term and every rollout 0..0.2 from the second.

    The budget scale then applies to the result, so following the workflow
    cannot buy back what running out of turns costs. A trajectory without the
    signal (no workflow scorer, or its scoring failed) keeps the verifier
    reward alone under ``"mul"`` / ``"add"`` -- in ``"mul"`` it is not zeroed for a
    scoring failure. Under ``"wsum"`` it counts as compliance 0, i.e.
    ``(1 - weight) * verifier``, so a rollout the scorer failed on never outranks
    a scored one; ``rollout/compliance_missing`` (1 on such a rollout, else 0)
    logs how often that happens. ``_workflow_reward`` refuses ``"wsum"`` with a
    ``none`` route, whose rollouts carry no signal by design.

    One caveat: the trainer runs the same hook over validation episodes, so
    ``val/reward_*`` is scaled -- and carries the compliance term -- too.
    ``val/accuracy`` is built from ``is_correct`` and is not affected.

    After shaping, ``rollout_metrics.annotate`` writes the ``rollout/*`` episode
    metrics (exploration turns, test runs, compliance split by verdict, solved
    rollouts under their group mean); the trainer averages them after this hook.
    """
    from recipe.grpo.qwen3_5.rollout_metrics import annotate
    if not 0.0 <= scale <= 1.0:
        raise ValueError(f"budget_reward_scale must be in [0, 1], got {scale}")
    if compliance_mode is not None and compliance_mode not in COMPLIANCE_MODES:
        raise ValueError(f"recipe.workflow.compliance_reward.mode must be one of {COMPLIANCE_MODES}, got {compliance_mode!r}")
    signals = (compliance_signals,) if isinstance(compliance_signals, str) else tuple(compliance_signals or ())
    if compliance_mode is not None and not signals:
        raise ValueError("a compliance mode needs the signal it reads (WorkflowSpec.reward_signal)")
    if compliance_mode == "add" and compliance_lam < 0.0:
        raise ValueError(f"recipe.workflow.compliance_reward.lam must be >= 0, got {compliance_lam}")
    if not 0.0 <= compliance_floor <= 1.0:
        raise ValueError(f"recipe.workflow.compliance_reward.floor must be in [0, 1], got {compliance_floor}")
    if compliance_mode != "mul" and compliance_floor != 0.0:
        raise ValueError(f"recipe.workflow.compliance_reward.floor applies to mode=mul only, got floor={compliance_floor} with mode={compliance_mode!r}")
    if not 0.0 <= compliance_weight <= 1.0:
        raise ValueError(f"recipe.workflow.compliance_reward.weight must be in [0, 1], got {compliance_weight}")
    if not 0.0 <= penalty_weight < 1.0:
        raise ValueError(f"recipe.workflow.compliance_reward.penalty_weight must be in [0, 1), got {penalty_weight}")
    if penalty_gate not in PENALTY_GATES:
        raise ValueError(f"recipe.workflow.compliance_reward.penalty_gate must be one of {PENALTY_GATES}, got {penalty_gate!r}")
    penalties = (penalty_signals,) if isinstance(penalty_signals, str) else tuple(penalty_signals or ())
    if penalty_weight > 0.0 and not penalties:
        raise ValueError("compliance_reward.penalty_weight > 0 needs the signal it reads (WorkflowSpec.penalty_signal)")

    def hook(episodes, transform_config, compact_filtering_config=None):
        for episode in episodes:
            exhausted = episode.termination_reason in BUDGET_EXHAUSTED
            missing = False
            for trajectory in episode.trajectories:
                if trajectory.reward is None:
                    continue
                carried = trajectory.signals or {}
                verifier = float(trajectory.reward)
                c = next((carried[name] for name in signals if name in carried), None) if compliance_mode else None
                if compliance_mode == "wsum":
                    missing = missing or c is None
                    trajectory.reward = (1.0 - compliance_weight) * trajectory.reward + compliance_weight * (0.0 if c is None else float(c))
                elif c is not None:
                    if compliance_mode == "mul":
                        trajectory.reward = trajectory.reward * (compliance_floor + (1.0 - compliance_floor) * float(c))
                    else:
                        trajectory.reward = trajectory.reward + compliance_lam * float(c)
                if penalty_weight > 0.0:
                    kept = float(next((carried[name] for name in penalties if name in carried), 1.0))
                    if penalty_gate == "unsolved":
                        kept = 1.0 - (1.0 - verifier) * (1.0 - kept)
                    trajectory.reward = (1.0 - penalty_weight) * trajectory.reward + penalty_weight * kept
                if exhausted and scale != 1.0:
                    trajectory.reward = trajectory.reward * scale
            if compliance_mode == "wsum":
                episode.metrics["rollout/compliance_missing"] = 1.0 if missing else 0.0
        annotate(episodes)
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


def _renderer_enable_thinking(config: DictConfig | None) -> bool | None:
    """``rllm.gateway.renderer_kwargs.enable_thinking`` when set, else ``None``.

    Turn 1 of an openhands-sdk episode is rendered by vLLM's chat template,
    turns 2+ by the gateway's renderer. Both take an ``enable_thinking`` switch
    and they must agree, or the policy is trained on a different shape than it
    sampled from. The renderer kwarg is the single source of truth; the
    harness forwards the same value to the SDK as a chat-template kwarg.
    """
    if config is None:
        return None
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

def _workflow_reward(recipe: DictConfig, agent_flow) -> tuple[tuple[str, ...] | None, str | None, float, float, float, tuple[str, ...], float, str]:
    """(signals folded into the reward, "mul" / "add" / "wsum", lam for "add", floor for "mul", weight for "wsum",
    penalty signals, penalty_weight, penalty_gate); ``(None, None, 0.0, 0.0, 0.0, (), 0.0, "all")`` when off.

    ``compliance_reward.penalty_weight`` > 0 folds each workflow's ``penalty_signal`` (P, 1 = every penalty rule
    kept) into the reward as ``(1 - w) * reward + w * P``; a workflow in the mix without one counts as P = 1.

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
    than ``none``'s. ``wsum`` refuses a ``none`` route: it scores a missing
    signal as compliance 0, so ``none``'s solves would all be cut to ``1 - weight``.
    """
    reward = (recipe.get("workflow") or {}).get("compliance_reward") or {}
    if not bool(reward.get("enable", False)):
        return None, None, 0.0, 0.0, 0.0, (), 0.0, "all"
    routes = agent_flow.routes() if hasattr(agent_flow, "routes") else {}
    flows = {name: flow for name, flow in routes.items() if flow.workflow_spec is not None}
    if not flows:
        logger.warning("recipe.workflow.compliance_reward.enable is set but there is no workflow; training on the verifier reward alone")
        return None, None, 0.0, 0.0, 0.0, (), 0.0, "all"
    for name, flow in flows.items():
        if flow.workflow_spec.reward_signal is None or flow.evaluation_policy is None:
            raise SystemExit(f"recipe.workflow.compliance_reward.enable=true: workflow {name!r} has no compliance scorer for recipe.harness={flow.name!r}")
    mode = str(reward.get("mode", "mul"))
    if len(flows) < len(routes):
        if mode == "wsum":
            raise SystemExit(
                "recipe.workflow.compliance_reward.mode=wsum cannot train a 'none' route: its rollouts carry no compliance "
                f"signal, which wsum scores as 0, cutting every solve to 1 - weight (routes: {sorted(routes)})"
            )
        logger.warning("recipe.workflow.compliance_reward: the 'none' route trains on the verifier reward alone, beside %s", sorted(flows))
    penalty_weight = float(reward.get("penalty_weight", 0.0))
    penalty_gate = str(reward.get("penalty_gate", "all"))
    penalties = tuple(flow.workflow_spec.penalty_signal for flow in flows.values() if flow.workflow_spec.penalty_signal)
    if penalty_weight > 0.0 and not penalties:
        raise SystemExit(f"recipe.workflow.compliance_reward.penalty_weight={penalty_weight}: no workflow in {sorted(flows)} has a penalty_signal")
    return (
        tuple(flow.workflow_spec.reward_signal for flow in flows.values()),
        mode,
        float(reward.get("lam", 0.2)),
        float(reward.get("floor", 0.0)),
        float(reward.get("weight", 0.3)),
        penalties,
        penalty_weight,
        penalty_gate,
    )


def _build_hooks(
    agent_flow,
    sandbox_backend: str,
    hide_git_history: bool = False,
    *,
    agent_network: bool = False,
    verify_network: bool = False,
    verifier_timeout: float | None = None,
):
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

    # The auto-wired hooks get these from AgentTrainer; caller-built ones must carry them
    # themselves, or the verifier runs offline and under task.toml's limit instead of
    # recipe.verify_network / rllm.timeouts.verifier.
    if getattr(evaluation, "verifier_timeout", None) is None:
        evaluation.verifier_timeout = verifier_timeout
    return SandboxTaskHooks(
        evaluation=evaluation,
        sandbox_backend=sandbox_backend,
        hide_git_history=hide_git_history,
        agent_network=agent_network,
        verify_network=verify_network,
        verifier_timeout=verifier_timeout,
    )

def make_agent_flow(recipe: DictConfig, config: DictConfig | None = None):
    """Pick the harness from ``recipe.harness`` and the workflow on it from ``recipe.workflow.name``.

    ``config`` is the whole Hydra config, read for the renderer's ``enable_thinking``;
    without it the harness leaves the SDK's thinking switch alone.

    The two harnesses share one ``agent_step_limit`` so a run's turn budget
    means the same thing whichever agent is under it. A workflow needs a
    system-prompt override to work at all, and mini-swe-agent has no
    equivalent seam, so a workflow there is refused rather than run without it.
    ``recipe.workflow.name: null`` is the plain harness; a list is a mix, each
    task routed to one of them (``workflow_harness.WorkflowMixin``), and
    ``val_name`` is routed too, for the validation tasks ``_pin_workflow`` marks.
    """
    harness = str(recipe.get("harness", "openhands-sdk"))
    step_limit = int(recipe.agent_step_limit)
    workflow = recipe.get("workflow") or {}
    pool, val_name = _workflow_names(recipe)
    name = pool[0] if len(pool) == 1 else (list(pool) or None)

    if harness == "mini-swe-agent":
        if any(n != "none" for n in (*pool, *((val_name,) if val_name else ()))):
            raise SystemExit(
                f"recipe.workflow.name={name!r} requires recipe.harness=openhands-sdk "
                "(mini-swe-agent has no system-prompt seam for the workflow). "
                "Use `variant=openhands_9b_aidlc` or set recipe.harness explicitly."
            )
        return StepLimitedMiniSweAgent(step_limit=step_limit)

    if harness == "openhands-sdk":
        from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow

        return OpenHandsSdkWorkflow(
            step_limit=step_limit,
            enable_thinking=_renderer_enable_thinking(config),
            workflow=name,
            workflow_seed=int(workflow.get("seed", 0)),
            pinned_workflows=(val_name,) if val_name else (),
            instruction_position=str(workflow.get("instruction_position", "suffix")),
            # main이 추가한 SDK 옵션 (config.yaml openhands_default_tools / openhands_strict_tool_calls)
            include_default_tools=[str(t) for t in recipe.openhands_default_tools],
            strict_tool_calls=bool(recipe.openhands_strict_tool_calls),
            end_on_invalid_tool_call=bool(recipe.get("openhands_end_on_invalid_tool_call", False)),
        )

    raise SystemExit(f"recipe.harness must be 'mini-swe-agent' or 'openhands-sdk', got {harness!r}")


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

    # `auto` mounts a pre-built image of the agent into the task sandbox
    # instead of installing it on every rollout (Docker only). Same mechanism
    # as `rllm eval --agent-image`.
    agent_image = os.environ.get("RLLM_AGENT_IMAGE", recipe.agent_image)
    os.environ["RLLM_AGENT_IMAGE"] = str(agent_image)

    agent_flow = make_agent_flow(recipe, config)
    agent_flow.configure({"agent_image": agent_image})
    _pin_workflow(val_dataset, _workflow_names(recipe)[1])
    _log_workflow_split(agent_flow, train_dataset, val_dataset)
    reward_signal, compliance_mode, compliance_lam, compliance_floor, compliance_weight, penalty_signal, penalty_weight, penalty_gate = _workflow_reward(recipe, agent_flow)
    sandbox_backend = os.environ.get("SANDBOX_BACKEND", recipe.sandbox_backend)
    hooks = _build_hooks(
        agent_flow,
        sandbox_backend,
        bool(recipe.hide_git_history),
        agent_network=bool(recipe.agent_network),
        verify_network=bool(recipe.verify_network),
        verifier_timeout=OmegaConf.select(config, "rllm.timeouts.verifier"),
    )
    logger.info(
        "agent flow: %s (step_limit=%s, workflow=%s, enable_thinking=%s, compliance scored=%s, reward=%s mode=%s lam=%s floor=%s weight=%s penalty=%s penalty_weight=%s penalty_gate=%s)",
        type(agent_flow).__name__,
        recipe.agent_step_limit,
        getattr(agent_flow, "workflow", None),
        getattr(agent_flow, "enable_thinking", None),
        hooks is not None,
        reward_signal,
        compliance_mode,
        compliance_lam if compliance_mode == "add" else "-",
        compliance_floor if compliance_mode == "mul" else "-",
        compliance_weight if compliance_mode == "wsum" else "-",
        penalty_signal if penalty_weight > 0.0 else "-",
        penalty_weight if penalty_weight > 0.0 else "-",
        penalty_gate if penalty_weight > 0.0 else "-",
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
        # Same mechanisms as `rllm eval --agent-network` / `--verify-network`.
        agent_network=bool(recipe.agent_network),
        verify_network=bool(recipe.verify_network),
        # Passed through **kwargs to UnifiedTrainer (verl_launcher.py forwards them).
        traj_grouping_hook=make_budget_scaled_grouping_hook(float(recipe.budget_reward_scale), compliance_mode, compliance_lam, reward_signal, compliance_floor, compliance_weight, penalty_signal, penalty_weight, penalty_gate),
    )
    trainer.train()


if __name__ == "__main__":
    main()
