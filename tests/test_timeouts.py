"""Rollout time limits: resolution order, the rollout budget, and where each limit is applied."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from rllm.agents.agent import Episode, Trajectory
from rllm.data.utils import task_from_row
from rllm.engine.agentflow_engine import AgentFlowEngine, TaskContext
from rllm.eval.script_evaluator import ShellScriptEvaluator
from rllm.eval.types import EvalOutput
from rllm.tasks.loader import BenchmarkLoader
from rllm.timeouts import (
    AGENT_TIMEOUT_ENV,
    ROLLOUT_TIMEOUT_ENV,
    VERIFIER_TIMEOUT_ENV,
    RolloutClock,
    agent_timeout_for,
    check_rollout_budget,
    resolve_agent_timeout,
    resolve_rollout_timeout,
    resolve_verifier_timeout,
)
from rllm.types import AgentConfig, Task


@pytest.fixture(autouse=True)
def _no_timeout_env(monkeypatch):
    for name in (AGENT_TIMEOUT_ENV, VERIFIER_TIMEOUT_ENV, ROLLOUT_TIMEOUT_ENV):
        monkeypatch.delenv(name, raising=False)


def _task(**metadata) -> Task:
    return Task(id="t", instruction="", metadata=metadata)


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------


def test_agent_timeout_order_is_config_then_task_toml_then_env_then_default(monkeypatch):
    assert resolve_agent_timeout(_task()) == 1800.0
    monkeypatch.setenv(AGENT_TIMEOUT_ENV, "1200")
    assert resolve_agent_timeout(_task()) == 1200.0
    assert resolve_agent_timeout(_task(agent_timeout=3600)) == 3600.0
    assert resolve_agent_timeout(_task(agent_timeout=3600), override=900) == 900.0


def test_verifier_timeout_order_is_config_then_task_toml_then_env_then_default(monkeypatch):
    assert resolve_verifier_timeout(_task()) == 600.0
    monkeypatch.setenv(VERIFIER_TIMEOUT_ENV, "300")
    assert resolve_verifier_timeout(_task()) == 300.0
    assert resolve_verifier_timeout(_task(verifier_timeout=1800)) == 1800.0
    assert resolve_verifier_timeout(_task(verifier_timeout=1800), override=120) == 120.0


def test_rollout_timeout_is_config_then_env_and_unset_means_no_budget(monkeypatch):
    assert resolve_rollout_timeout() is None
    monkeypatch.setenv(ROLLOUT_TIMEOUT_ENV, "3600")
    assert resolve_rollout_timeout() == 3600.0
    assert resolve_rollout_timeout(override=1000) == 1000.0


def test_env_is_read_per_call_not_at_import(monkeypatch):
    """The resolvers run per rollout, so an operator's export reaches a long-lived process."""
    assert resolve_agent_timeout(_task()) == 1800.0
    monkeypatch.setenv(AGENT_TIMEOUT_ENV, "60")
    assert resolve_agent_timeout(_task()) == 60.0


def test_malformed_env_value_fails_loudly(monkeypatch):
    monkeypatch.setenv(VERIFIER_TIMEOUT_ENV, "ten minutes")
    with pytest.raises(ValueError):
        resolve_verifier_timeout(_task())


@pytest.mark.parametrize("value", [0, -5, "0", "-5.5"])
def test_zero_or_negative_limits_are_rejected_from_every_source(monkeypatch, value):
    """A zero is a mistake, not "unset" and not "no limit": every source fails the same way."""
    with pytest.raises(ValueError, match="rllm.timeouts.agent"):
        resolve_agent_timeout(_task(), override=value)
    with pytest.raises(ValueError, match=r"task.toml \[verifier\].timeout_sec"):
        resolve_verifier_timeout(_task(verifier_timeout=value))
    with pytest.raises(ValueError, match="rllm.timeouts.rollout"):
        resolve_rollout_timeout(override=value)
    monkeypatch.setenv(AGENT_TIMEOUT_ENV, str(value))
    with pytest.raises(ValueError, match=AGENT_TIMEOUT_ENV):
        resolve_agent_timeout(_task())
    monkeypatch.setenv(ROLLOUT_TIMEOUT_ENV, str(value))
    with pytest.raises(ValueError, match=ROLLOUT_TIMEOUT_ENV):
        resolve_rollout_timeout()


def test_agent_timeout_for_prefers_the_engines_resolution():
    """The engine's value is already cut to the rollout budget; outside the engine the flow resolves it itself."""
    task = _task(agent_timeout=3600)
    assert agent_timeout_for(task, AgentConfig(base_url="", model="m", session_uid="t:0", agent_timeout=120.0)) == 120.0
    assert agent_timeout_for(task, AgentConfig(base_url="", model="m", session_uid="t:0")) == 3600.0


# ---------------------------------------------------------------------------
# RolloutClock
# ---------------------------------------------------------------------------


def test_clock_without_budget_leaves_limits_alone():
    clock = RolloutClock()
    clock.start(None)
    assert clock.remaining() is None
    assert clock.cap(1800.0) == 1800.0


def test_clock_cuts_a_limit_to_the_remaining_budget():
    clock = RolloutClock()
    clock.start(100.0)
    assert clock.cap(1800.0) <= 100.0
    assert clock.cap(10.0) == 10.0


def test_clock_never_goes_negative():
    clock = RolloutClock()
    clock.start(0.01)
    time.sleep(0.03)
    assert clock.remaining() == 0.0
    assert clock.cap(600.0) == 0.0


def test_clock_keeps_a_reserve_back_for_a_later_phase():
    clock = RolloutClock()
    clock.start(100.0)
    assert 59.0 < clock.cap(1800.0, reserve=40.0) <= 60.0
    assert clock.cap(10.0, reserve=40.0) == 10.0
    assert clock.cap(1800.0, reserve=100.0) == 0.0
    clock.start(None)
    assert clock.cap(1800.0, reserve=40.0) == 1800.0


def test_a_budget_must_leave_the_agent_time_after_the_verifier_reserve():
    check_rollout_budget(None, 600.0)
    check_rollout_budget(601.0, 600.0)
    for budget in (600.0, 600.5, 100.0):
        with pytest.raises(ValueError, match="leaves the agent no time"):
            check_rollout_budget(budget, 600.0)


# ---------------------------------------------------------------------------
# task.toml lifting
# ---------------------------------------------------------------------------


def _harbor_task(root: Path, name: str, toml_body: str) -> None:
    d = root / name
    (d / "tests").mkdir(parents=True)
    (d / "tests" / "test.sh").write_text("#!/bin/sh\n")
    (d / "instruction.md").write_text("do it\n")
    (d / "task.toml").write_text(toml_body)


def test_loader_lifts_timeouts_only_when_declared(tmp_path):
    """An undeclared timeout must stay absent, or the env fallback can never apply."""
    bench = tmp_path / "bench"
    _harbor_task(bench, "declared", "[agent]\ntimeout_sec = 3600\n\n[verifier]\ntimeout_sec = 1800\n")
    _harbor_task(bench, "undeclared", "[metadata]\nrepo = 'x'\n")

    tasks = {t.id.split("/")[-1]: t for t in BenchmarkLoader.load(str(bench)).tasks}

    assert tasks["declared"].metadata["agent_timeout"] == 3600
    assert tasks["declared"].metadata["verifier_timeout"] == 1800
    assert "agent_timeout" not in tasks["undeclared"].metadata
    assert "verifier_timeout" not in tasks["undeclared"].metadata


# ---------------------------------------------------------------------------
# Verifier: ShellScriptEvaluator under the rollout budget
# ---------------------------------------------------------------------------


class _RecordingSandbox:
    def __init__(self):
        self.verifier_timeouts: list[float | None] = []

    def exec(self, cmd: str, timeout: float | None = None, user: str | None = None) -> str:
        if cmd.startswith("chmod +x /tests/"):
            self.verifier_timeouts.append(timeout)
        if cmd.startswith("test -f "):
            return "no"
        if "echo clean" in cmd:
            return "clean"
        return ""

    def upload_dir(self, src: str, dst: str) -> None:
        pass


def _verifier_task(tmp_path: Path) -> Task:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test.sh").write_text("#!/bin/sh\n")
    return Task(id="t", instruction="", metadata={}, dataset_dir=tmp_path)


def _episode() -> Episode:
    return Episode(id="t:0", trajectories=[Trajectory(name="x")])


def test_verifier_runs_under_its_own_limit_without_a_budget(tmp_path):
    sb = _RecordingSandbox()
    ShellScriptEvaluator(sandbox=sb, verifier_timeout=1800.0, clock=RolloutClock()).evaluate(_verifier_task(tmp_path), _episode())
    assert sb.verifier_timeouts == [1800.0]


def test_verifier_limit_is_cut_to_what_the_agent_left(tmp_path):
    sb = _RecordingSandbox()
    clock = RolloutClock()
    clock.start(100.0)
    ShellScriptEvaluator(sandbox=sb, verifier_timeout=1800.0, clock=clock).evaluate(_verifier_task(tmp_path), _episode())
    assert len(sb.verifier_timeouts) == 1 and sb.verifier_timeouts[0] <= 100.0


def test_exhausted_budget_skips_the_verifier_and_reports_verifier_timeout(tmp_path):
    """No time left means no grading: the reward is not a measurement, so it must be dropped, not scored 0."""
    sb = _RecordingSandbox()
    clock = RolloutClock()
    clock.start(0.0)
    out = ShellScriptEvaluator(sandbox=sb, verifier_timeout=1800.0, clock=clock).evaluate(_verifier_task(tmp_path), _episode())
    assert sb.verifier_timeouts == []
    assert out.metadata.get("termination_reason") == "verifier_timeout"


def test_a_sub_second_remainder_counts_as_exhausted(tmp_path):
    """Backends hand exec whole seconds, and GNU ``timeout 0`` is no limit: 0.5 s left must not become unbounded."""
    sb = _RecordingSandbox()
    clock = RolloutClock()
    clock.start(0.5)
    out = ShellScriptEvaluator(sandbox=sb, verifier_timeout=1800.0, clock=clock).evaluate(_verifier_task(tmp_path), _episode())
    assert sb.verifier_timeouts == []
    assert out.metadata.get("termination_reason") == "verifier_timeout"


# ---------------------------------------------------------------------------
# Engine: agent budget
# ---------------------------------------------------------------------------


class _Gateway:
    async def acreate_session(self, session_id, is_validation=False, sampling_params=None):
        pass

    def get_session_url(self, session_id, public=True):
        return f"http://gateway/{session_id}"

    async def aget_traces(self, session_id):
        return []

    async def adelete_session(self, session_id):
        pass

    async def adelete_sessions(self, session_ids):
        pass


class _Evaluator:
    def evaluate(self, task, episode):
        return EvalOutput(reward=0.0, is_correct=False)


class _Hooks:
    """Provisions nothing; hands the engine the clock a sandbox verifier would read."""

    def __init__(self):
        self.clocks: list[RolloutClock] = []

    def setup(self, task, agent_flow, uid):
        ctx = TaskContext(evaluator=_Evaluator())
        self.clocks.append(ctx.clock)
        return ctx


class _RecordingAgent:
    def __init__(self):
        self.agent_timeouts: list[float | None] = []

    async def arun(self, task, config):
        self.agent_timeouts.append(config.agent_timeout)
        return Episode(id=task.id, trajectories=[Trajectory(name="solver")])


def _engine(agent, hooks=None, **kwargs) -> AgentFlowEngine:
    return AgentFlowEngine(agent_flow=agent, evaluator=None, gateway=_Gateway(), model="m", n_parallel_tasks=4, hooks=hooks or _Hooks(), **kwargs)


def _run_one(engine, task):
    try:
        return asyncio.run(engine._run_single(task, "t:0", is_validation=True))
    finally:
        engine.shutdown()


def test_engine_gives_the_agent_its_resolved_limit():
    agent = _RecordingAgent()
    _run_one(_engine(agent), task_from_row({"question": "q", "agent_timeout": 3600}, "t"))
    assert agent.agent_timeouts == [3600.0]


def test_engine_config_overrides_win_over_task_toml():
    agent = _RecordingAgent()
    _run_one(_engine(agent, agent_timeout=900), task_from_row({"question": "q", "agent_timeout": 3600}, "t"))
    assert agent.agent_timeouts == [900.0]


def test_rollout_budget_caps_the_agent_with_the_verifier_limit_reserved():
    """The agent gets the budget minus the verifier's share; the clock keeps running for the verifier."""
    agent = _RecordingAgent()
    hooks = _Hooks()
    task = task_from_row({"question": "q", "agent_timeout": 3600, "verifier_timeout": 40}, "t")
    _run_one(_engine(agent, hooks=hooks, rollout_timeout=100), task)
    assert 59.0 < agent.agent_timeouts[0] <= 60.0
    assert hooks.clocks[0].remaining() is not None and hooks.clocks[0].remaining() <= 100.0


def test_verifier_reserve_follows_the_train_config_override():
    agent = _RecordingAgent()
    task = task_from_row({"question": "q", "agent_timeout": 3600, "verifier_timeout": 600}, "t")
    _run_one(_engine(agent, rollout_timeout=100, verifier_timeout=30), task)
    assert 69.0 < agent.agent_timeouts[0] <= 70.0


def test_agent_limit_below_the_reserved_budget_is_left_alone():
    agent = _RecordingAgent()
    task = task_from_row({"question": "q", "agent_timeout": 20, "verifier_timeout": 40}, "t")
    _run_one(_engine(agent, rollout_timeout=100), task)
    assert agent.agent_timeouts == [20.0]


def test_rollout_budget_comes_from_env_in_eval(monkeypatch):
    monkeypatch.setenv(ROLLOUT_TIMEOUT_ENV, "50")
    agent = _RecordingAgent()
    _run_one(_engine(agent), task_from_row({"question": "q", "agent_timeout": 3600, "verifier_timeout": 20}, "t"))
    assert 29.0 < agent.agent_timeouts[0] <= 30.0


def test_budget_that_leaves_the_agent_no_time_fails_at_engine_construction():
    """Config and env values are known up front; the mistake is reported before any rollout."""
    with pytest.raises(ValueError, match="leaves the agent no time"):
        _engine(_RecordingAgent(), rollout_timeout=600, verifier_timeout=600)


def test_budget_that_leaves_the_agent_no_time_under_task_toml_fails_the_rollout():
    """task.toml is only known per rollout; the engine raises there (an ERROR episode in eval, a crash in training)."""
    agent = _RecordingAgent()
    task = task_from_row({"question": "q", "agent_timeout": 3600, "verifier_timeout": 100}, "t")
    with pytest.raises(ValueError, match="leaves the agent no time"):
        _run_one(_engine(agent, rollout_timeout=100), task)
    assert agent.agent_timeouts == []
