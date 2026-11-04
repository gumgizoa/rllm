"""Rollout time limits: the whole rollout (agent + verifier), the agent, the verifier.

Each limit resolves to the first value that is set:

============  ==========================================================  ==============================
limit         train                                                       eval (``rllm eval``)
============  ==========================================================  ==============================
rollout       ``rllm.timeouts.rollout`` -> ``$RLLM_ROLLOUT_TIMEOUT_S``     ``$RLLM_ROLLOUT_TIMEOUT_S``
agent         ``rllm.timeouts.agent`` -> task.toml ``[agent].timeout_sec``   task.toml -> env
              -> ``$RLLM_HARNESS_RUN_TIMEOUT_S`` (default 1800)
verifier      ``rllm.timeouts.verifier`` -> task.toml                      task.toml -> env
              ``[verifier].timeout_sec`` -> ``$RLLM_VERIFIER_TIMEOUT_S``
              (default 600)
============  ==========================================================  ==============================

``rllm eval`` has no experiment config, so its overrides are always ``None``. The
rollout limit has no default: unset means the agent and verifier limits are the only
clocks. Whatever the source, a limit must be more than 0 seconds; zero and negative
values raise ``ValueError`` instead of being read as "unset" or "no limit".

The rollout limit is a budget, not a watchdog. Its clock starts when the agent flow
starts (sandbox setup is not counted). The verifier's limit is reserved out of the
budget before the agent starts, so the agent runs under ``min(agent limit, budget -
verifier limit)`` and the verifier under ``min(verifier limit, remaining)``. A budget
that leaves the agent no time at all (``budget - verifier limit`` under
:data:`MIN_EXEC_TIMEOUT_S`) is a configuration error and raises ``ValueError``. Both
limits are enforced by the sandbox exec timeouts that already bound each phase, so a
rollout that runs out is ended the same way a phase that runs out of its own limit
is: ``AGENT_TIMEOUT``, after which the verifier still grades the repo in its reserved
time, or ``VERIFIER_TIMEOUT``. Less than :data:`MIN_EXEC_TIMEOUT_S` left counts as
nothing left: the sandbox backends hand exec a whole number of seconds, and GNU
``timeout 0`` means no limit at all.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from rllm.env import env_float

if TYPE_CHECKING:
    from rllm.types import AgentConfig, Task

AGENT_TIMEOUT_ENV = "RLLM_HARNESS_RUN_TIMEOUT_S"
VERIFIER_TIMEOUT_ENV = "RLLM_VERIFIER_TIMEOUT_S"
ROLLOUT_TIMEOUT_ENV = "RLLM_ROLLOUT_TIMEOUT_S"
DEFAULT_AGENT_TIMEOUT_S = 1800.0
DEFAULT_VERIFIER_TIMEOUT_S = 600.0
# The shortest exec timeout worth handing a sandbox backend (see module docstring).
MIN_EXEC_TIMEOUT_S = 1.0


def _positive(source: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{source} must be more than 0 seconds, got {value!r}")
    return value


def _resolve(sources: tuple[tuple[str, object], ...], env_name: str, default: float) -> float:
    """The first set value in ``sources`` (as ``(name, value)`` pairs), else ``$env_name``, else ``default``."""
    for source, value in sources:
        if value is not None:
            return _positive(source, float(value))  # type: ignore[arg-type]
    return _positive(f"${env_name}", env_float(env_name, default))


def resolve_agent_timeout(task: Task, override: float | None = None) -> float:
    """Agent wall clock: ``override`` (train config) -> task.toml -> env -> 1800 s."""
    sources = (("rllm.timeouts.agent", override), ("task.toml [agent].timeout_sec", task.metadata.get("agent_timeout")))
    return _resolve(sources, AGENT_TIMEOUT_ENV, DEFAULT_AGENT_TIMEOUT_S)


def resolve_verifier_timeout(task: Task, override: float | None = None) -> float:
    """Verifier wall clock: ``override`` (train config) -> task.toml -> env -> 600 s."""
    sources = (("rllm.timeouts.verifier", override), ("task.toml [verifier].timeout_sec", task.metadata.get("verifier_timeout")))
    return _resolve(sources, VERIFIER_TIMEOUT_ENV, DEFAULT_VERIFIER_TIMEOUT_S)


def resolve_rollout_timeout(override: float | None = None) -> float | None:
    """Whole-rollout budget: ``override`` (train config) -> env -> none."""
    if override is not None:
        return _positive("rllm.timeouts.rollout", float(override))
    if os.environ.get(ROLLOUT_TIMEOUT_ENV):
        return _positive(f"${ROLLOUT_TIMEOUT_ENV}", env_float(ROLLOUT_TIMEOUT_ENV, 0.0))
    return None


def check_rollout_budget(budget: float | None, verifier_limit: float) -> None:
    """Raise ``ValueError`` when ``budget`` leaves the agent no time once ``verifier_limit`` is reserved."""
    if budget is not None and budget - verifier_limit < MIN_EXEC_TIMEOUT_S:
        raise ValueError(f"rollout budget {budget:g} s leaves the agent no time after reserving {verifier_limit:g} s for the verifier; raise the rollout limit or lower the verifier limit")


def agent_timeout_for(task: Task, config: AgentConfig) -> float:
    """The agent limit a sandboxed flow runs under.

    The engine resolves it once per rollout, already cut to the rollout budget,
    and passes it as ``config.agent_timeout``. A flow run outside the engine
    (eval tooling, tests) gets ``None`` there and resolves the limit itself.
    """
    return config.agent_timeout if config.agent_timeout is not None else resolve_agent_timeout(task)


class RolloutClock:
    """The whole-rollout budget of one rollout, shared by the engine and its evaluator."""

    def __init__(self) -> None:
        self._deadline: float | None = None

    def start(self, limit: float | None) -> None:
        self._deadline = None if limit is None else time.monotonic() + limit

    def remaining(self) -> float | None:
        """Seconds left, ``None`` when no budget was set; never negative."""
        if self._deadline is None:
            return None
        return max(self._deadline - time.monotonic(), 0.0)

    def cap(self, limit: float, reserve: float = 0.0) -> float:
        """``limit`` shortened to what is left of the budget, keeping ``reserve`` seconds back for a later phase."""
        remaining = self.remaining()
        return limit if remaining is None else min(limit, max(remaining - reserve, 0.0))
