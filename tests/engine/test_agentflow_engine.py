import asyncio

import pytest

from rllm.agents.agent import Episode, Trajectory
from rllm.data.utils import task_from_row
from rllm.engine.agentflow_engine import AgentFlowEngine
from rllm.eval.types import EvalOutput
from rllm.workflows.workflow import TerminationReason


class _Agent:
    def __init__(self):
        self.config = None

    async def arun(self, task, config):
        self.config = config
        return Episode(
            id=task.id,
            termination_reason=TerminationReason.ERROR,
            trajectories=[Trajectory(name="solver")],
        )


class _Evaluator:
    def evaluate(self, task, episode):
        return EvalOutput(reward=0.0, is_correct=False)


class _Gateway:
    """Minimal gateway double; stocked traces are returned for every session."""

    def __init__(self, traces=None):
        self.created = None
        self.deleted = None
        self._traces = traces or []

    async def acreate_session(self, session_id, is_validation=False, sampling_params=None):
        self.created = (session_id, is_validation)

    def get_session_url(self, session_id, public=True):
        return f"http://gateway/{session_id}"

    async def aget_traces(self, session_id):
        return self._traces

    async def adelete_session(self, session_id):
        self.deleted = session_id

    async def adelete_sessions(self, session_ids):
        self.deleted = session_ids[-1] if session_ids else None


def test_run_single_passes_validation_flag_and_preserves_termination_reason():
    agent = _Agent()
    gateway = _Gateway()
    engine = AgentFlowEngine(
        agent_flow=agent,
        evaluator=_Evaluator(),
        gateway=gateway,
        model="test-model",
        n_parallel_tasks=1,
        val_sampling_params={"temperature": 0.1},
    )
    task = task_from_row({"question": "q"}, "task")

    try:
        episode = asyncio.run(engine._run_single(task, "task:0", is_validation=True))
    finally:
        engine.shutdown()

    assert gateway.created == ("task:0", True)
    assert agent.config.is_validation is True
    assert agent.config.session_uid == "task:0"
    assert episode.termination_reason == TerminationReason.ERROR


class _TimedOutAgent:
    """A CLI-style flow whose agent ran out of its wall-clock budget."""

    async def arun(self, task, config):
        return Episode(id=task.id, termination_reason=TerminationReason.AGENT_TIMEOUT, trajectories=[Trajectory(name="solver")])


class _TimedOutVerifier:
    def evaluate(self, task, episode):
        return EvalOutput(reward=0.0, is_correct=False, metadata={"termination_reason": "verifier_timeout"})


def _run(agent, evaluator):
    engine = AgentFlowEngine(agent_flow=agent, evaluator=evaluator, gateway=_Gateway(), model="m", n_parallel_tasks=1)
    try:
        return asyncio.run(engine._run_single(task_from_row({"question": "q"}, "task"), "task:0", is_validation=True))
    finally:
        engine.shutdown()


def test_agent_timeout_stamp_survives_a_healthy_verifier():
    """Budget exhaustion reported by the harness is kept when the grader worked:
    the repo state was graded, and the reason is what reward shaping keys on."""
    episode = _run(_TimedOutAgent(), _Evaluator())
    assert episode.termination_reason == TerminationReason.AGENT_TIMEOUT


def test_verifier_failure_overrides_agent_side_reason():
    """Infrastructure beats budget: an agent that timed out *and* whose grader
    then timed out has no usable reward, so the reason compact_filtering sees
    must be the verifier's, not the agent's."""
    episode = _run(_TimedOutAgent(), _TimedOutVerifier())
    assert episode.termination_reason == TerminationReason.VERIFIER_TIMEOUT


def test_legacy_timeout_marker_from_evaluator_maps_to_verifier_timeout():
    class _LegacyVerifier:
        def evaluate(self, task, episode):
            return EvalOutput(reward=0.0, is_correct=False, metadata={"termination_reason": "timeout"})

    episode = _run(_TimedOutAgent(), _LegacyVerifier())
    assert episode.termination_reason == TerminationReason.VERIFIER_TIMEOUT


def _empty_token_trace(session_id: str):
    from rllm_model_gateway.models import TraceRecord

    return TraceRecord(
        trace_id=f"t-{session_id}",
        session_id=session_id,
        model="m",
        messages=[{"role": "user", "content": "Q"}],
        response_message={"role": "assistant", "content": "A"},
        prompt_token_ids=[],  # empty → corrupts loss math if it reaches training
        completion_token_ids=[],
        logprobs=[],
        finish_reason="stop",
        metadata={},
    )


@pytest.mark.parametrize("is_validation", [False, True])
def test_strict_enrichment_follows_is_validation(is_validation):
    """Training rollouts must reject empty token IDs (EnrichMismatchError →
    retry); validation tolerates them (evaluators read message text). The old
    ``strict = hooks is None`` proxy silently disabled this for sandboxed
    training, which always has hooks."""

    @__import__("rllm").rollout(name="noop")
    def noop_flow(task, config):
        return None

    gateway = _Gateway(traces=[_empty_token_trace("task:0")])
    engine = AgentFlowEngine(
        agent_flow=noop_flow,
        evaluator=_Evaluator(),
        gateway=gateway,
        model="test-model",
        n_parallel_tasks=1,
        retry_limit=1,
    )
    task = task_from_row({"question": "q"}, "task")

    try:
        if is_validation:
            episode = asyncio.run(engine._run_single(task, "task:0", is_validation=True))
            assert episode is not None
        else:
            from rllm.engine.agentflow_engine import EnrichMismatchError

            with pytest.raises(EnrichMismatchError):
                asyncio.run(engine._run_single(task, "task:0", is_validation=False))
    finally:
        engine.shutdown()


def test_needs_env_flow_must_declare_env_param():
    """Binding a needs_env flow whose run() lacks the keyword-only ``env``
    parameter fails at construction, not mid-rollout."""
    from rllm.sandbox.sandboxed_flow import SandboxedAgentFlow

    class _LegacyFlow(SandboxedAgentFlow):
        def run(self, task, config):  # no env param
            return None

    with pytest.raises(TypeError, match="keyword-only 'env'"):
        AgentFlowEngine(
            agent_flow=_LegacyFlow(),
            evaluator=_Evaluator(),
            gateway=_Gateway(),
            model="test-model",
            n_parallel_tasks=1,
        )


def test_env_flow_receives_sandbox_and_container_url():
    """A needs_env flow gets the hook-provisioned sandbox as ``env`` and, when
    its LLM client runs in-sandbox on docker, a container-reachable URL."""
    from rllm.sandbox.sandboxed_flow import SandboxedAgentFlow

    seen = {}

    class _EnvFlow(SandboxedAgentFlow):
        llm_inside_env = True

        def run(self, task, config, *, env):
            seen["env"] = env
            seen["base_url"] = config.base_url
            return None

    sandbox = object()

    class _Hooks:
        def setup(self, task, agent_flow, uid):
            from rllm.engine.agentflow_engine import TaskContext

            return TaskContext(evaluator=_Evaluator(), env=sandbox, env_backend="docker")

    class _LoopbackGateway(_Gateway):
        def get_session_url(self, session_id, public=True):
            return f"http://127.0.0.1:9131/sessions/{session_id}/v1"

    engine = AgentFlowEngine(
        agent_flow=_EnvFlow(),
        evaluator=None,
        gateway=_LoopbackGateway(),
        model="test-model",
        n_parallel_tasks=1,
        hooks=_Hooks(),
    )
    task = task_from_row({"question": "q"}, "task")
    try:
        asyncio.run(engine._run_single(task, "task:0", is_validation=True))
    finally:
        engine.shutdown()

    assert seen["env"] is sandbox
    assert seen["base_url"].startswith("http://host.docker.internal:9131/")


# --- failed upstream calls in harnesses that record no agent steps ----------
#
# mini-swe-agent and openhands-sdk return no Steps; the engine builds the
# episode from gateway traces. A vLLM 400 leaves a trace with no tokens that
# the gateway marks with ``upstream_error`` (classify_upstream_error).


def _answered_trace(session_id: str, i: int):
    from rllm_model_gateway.models import TraceRecord

    return TraceRecord(
        trace_id=f"t-{session_id}-{i}",
        session_id=session_id,
        model="m",
        messages=[{"role": "user", "content": f"Q{i}"}],
        response_message={"role": "assistant", "content": f"A{i}"},
        prompt_token_ids=[1, 2, 3 + i],
        completion_token_ids=[10 + i, 11 + i],
        logprobs=[-0.1, -0.2],
        finish_reason="stop",
        metadata={},
    )


def _failed_trace(session_id: str, kind: str, *, eval_path: bool = False, i: int = 0):
    bad = _empty_token_trace(session_id)
    bad.trace_id = f"t-{session_id}-failed-{kind}-{i}"
    bad.metadata = {"upstream_error": {"kind": kind, "status": 400}}
    return bad


def _run_stepless(traces, *, is_validation=False, step_limit=None):
    @__import__("rllm").rollout(name="noop")
    def noop_flow(task, config):
        return None

    if step_limit is not None:
        noop_flow.step_limit = step_limit
    engine = AgentFlowEngine(
        agent_flow=noop_flow,
        evaluator=_Evaluator(),
        gateway=_Gateway(traces=traces),
        model="test-model",
        n_parallel_tasks=1,
        retry_limit=1,
    )
    task = task_from_row({"question": "q"}, "task")
    try:
        return asyncio.run(engine._run_single(task, "task:0", is_validation=is_validation))
    finally:
        engine.shutdown()


def _n_steps(episode):
    return sum(len(t.steps) for t in episode.trajectories)


def test_overflow_on_the_last_call_is_kept_and_budget_stamped():
    """mini-swe-agent / openhands-sdk abort on ContextWindowExceededError, so
    the rejected call is the last trace. The rollout must be graded with the
    turns before it, not resampled."""
    traces = [_answered_trace("task:0", 0), _answered_trace("task:0", 1), _failed_trace("task:0", "context_length_exceeded")]
    episode = _run_stepless(traces)
    assert _n_steps(episode) == 2
    assert episode.termination_reason == TerminationReason.MAX_PROMPT_LENGTH_EXCEEDED


def test_overflow_mid_rollout_is_dropped_wherever_it_sits():
    """An agent that carries on after the 400 (condenser) leaves it in the middle."""
    traces = [_answered_trace("task:0", 0), _failed_trace("task:0", "context_length_exceeded"), _answered_trace("task:0", 1)]
    episode = _run_stepless(traces)
    assert _n_steps(episode) == 2
    assert episode.termination_reason == TerminationReason.MAX_PROMPT_LENGTH_EXCEEDED


def test_overflow_is_stamped_on_the_eval_path_without_token_ids():
    """The eval gateway does not ask for token ids, so every trace looks
    malformed; the marker is what tells the overflow apart."""
    traces = [_empty_token_trace("task:0"), _failed_trace("task:0", "context_length_exceeded")]
    episode = _run_stepless(traces, is_validation=True)
    assert _n_steps(episode) == 1
    assert episode.termination_reason == TerminationReason.MAX_PROMPT_LENGTH_EXCEEDED


def test_failure_on_the_first_call_still_retries():
    from rllm.engine.agentflow_engine import EnrichMismatchError

    with pytest.raises(EnrichMismatchError):
        _run_stepless([_failed_trace("task:0", "context_length_exceeded")])


def test_infrastructure_error_at_the_end_wins_over_an_earlier_overflow():
    """Infrastructure beats budget: compact_filtering must drop this rollout."""
    traces = [_answered_trace("task:0", 0), _failed_trace("task:0", "context_length_exceeded"), _answered_trace("task:0", 1), _failed_trace("task:0", "upstream_error")]
    episode = _run_stepless(traces)
    assert episode.termination_reason == TerminationReason.ERROR


def test_transient_error_the_agent_recovered_from_stamps_nothing():
    """litellm resent the request and it went through: the data is intact."""
    traces = [_answered_trace("task:0", 0), _failed_trace("task:0", "upstream_error"), _answered_trace("task:0", 1)]
    episode = _run_stepless(traces)
    assert _n_steps(episode) == 2
    assert episode.termination_reason == TerminationReason.ENV_DONE


def test_unmarked_empty_trace_still_raises_in_training():
    """No marker means the cause is unknown; keep resampling those."""
    from rllm.engine.agentflow_engine import EnrichMismatchError

    with pytest.raises(EnrichMismatchError):
        _run_stepless([_answered_trace("task:0", 0), _empty_token_trace("task:0")])


def test_failed_calls_do_not_count_as_turns():
    """Resent requests leave one trace each; counting them would stamp
    MAX_TURNS_EXCEEDED on a rollout that used fewer turns than its budget."""
    traces = [_answered_trace("task:0", 0), _failed_trace("task:0", "upstream_error", i=0), _failed_trace("task:0", "upstream_error", i=1), _answered_trace("task:0", 1)]
    episode = _run_stepless(traces, step_limit=3)
    assert episode.termination_reason == TerminationReason.ENV_DONE
    assert episode.metrics["n_turns"] == 2.0
