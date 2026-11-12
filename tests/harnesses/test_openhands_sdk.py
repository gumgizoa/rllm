"""Unit tests for OpenHandsSdkHarness command construction."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.harnesses.tools import openhands_sdk_runner as runner
from rllm.types import AgentConfig, Task

from .test_cli_harness import FakeSandbox

# An SDK interpreter being run (``-c`` or the runner script) rather than named
# as an argument (``--python .../bin/python``, ``[ -x .../bin/python ]``).
_UNISOLATED_RUN = re.compile(r'(bin/python"?|"\$OH_PY") (?!-I )(-c|/opt/)')

_HARBOR_PATCH = Path(__file__).parents[2] / "recipe/eval/patches/harbor-0.3.0-openhands-sdk.patch"


def _task() -> Task:
    return Task(id="t-1", instruction="fix the bug", metadata={"workdir": "/testbed"})


def _config() -> AgentConfig:
    return AgentConfig(base_url="http://gw:8000/sessions/eval-0/v1", model="Qwen/Qwen3.5-4B", session_uid="eval-0")


def test_every_sdk_interpreter_run_is_isolated_from_the_task_repo():
    # Commands run from the task workdir, where ``python -c`` would import the
    # repo's own packages (/testbed/aiohttp, /testbed/pydantic) ahead of the
    # SDK's dependencies and fail both the mount probe and the fallback install.
    h = OpenHandsSdkHarness()
    sandbox = FakeSandbox()
    h.write_configs(sandbox, _task(), _config(), env={})
    commands = [c.command for c in sandbox.calls]
    commands += [h.install_script(), h.build_invocation("hi", _task(), _config())]

    for cmd in commands:
        assert not _UNISOLATED_RUN.findall(cmd), cmd
        # litellm appends the cwd to sys.path on import, so every import probe
        # leaves the workdir before importing.
        for probe in re.findall(r"-I -c '([^']*)'", cmd):
            assert probe.startswith("import os, tempfile; os.chdir(tempfile.mkdtemp()); import openhands.sdk"), probe
    assert "-I -c 'import os, tempfile; os.chdir(tempfile.mkdtemp()); import openhands.sdk'" in commands[-1]
    assert '"$OH_PY" -I /opt/openhands-sdk-runner.py' in commands[-1]


def test_runner_imports_the_sdk_away_from_the_workspace():
    source = (Path(runner.__file__)).read_text()
    chdir_away = source.index("os.chdir(tempfile.mkdtemp(")
    first_sdk_import = source.index("from openhands.sdk import")
    chdir_back = source.index("os.chdir(workspace)")
    assert source.index("workspace = os.getcwd()") < chdir_away < first_sdk_import < chdir_back


def test_llm_sends_past_reasoning_back():
    # Without it, Qwen3.x / GLM templates render past turns as an empty
    # <think></think> and the model stops thinking a few steps in.
    pytest.importorskip("openhands.sdk")
    from openhands.sdk import LLM, Agent
    from openhands.sdk.llm import Message, TextContent

    history = [
        Message(role="user", content=[TextContent(text="fix the bug")]),
        Message(role="assistant", content=[TextContent(text="looking")], reasoning_content="the bug is in f()"),
    ]
    kwargs = {"model": "openai/Qwen3.5-397B-A17B-FP8", "api_key": "k", "base_url": "http://gw/v1"}

    assert "reasoning_content" not in LLM(**kwargs).format_messages_for_llm(history)[1]  # the SDK default
    llm = runner.reasoning_replay_llm(LLM)(**kwargs)
    sent = llm.format_messages_for_llm(history)
    assert sent[1]["reasoning_content"] == "the bug is in f()"
    assert sent[1]["reasoning"] == "the bug is in f()"  # the field vLLM reads
    assert "reasoning_content" not in sent[0]
    assert "reasoning" not in sent[0]
    assert Agent(llm=llm, tools=[]).llm is llm  # the agent keeps the subclass


def _replay_methods(source: str) -> str:
    start = source.index("def _model_features")
    end = source.index("return dicts", start) + len("return dicts")
    # Back up to the line start so dedent sees the first line's indentation.
    return textwrap.dedent(source[source.rindex("\n", 0, start) + 1 : end])


def test_harbor_patch_replays_reasoning_like_the_native_runner():
    # harbor:openhands-sdk uploads Harbor's own runner, which cannot import
    # rLLM, so the patch carries a copy of the subclass. Keep the two equal.
    added = "\n".join(line[1:] for line in _HARBOR_PATCH.read_text().splitlines() if line.startswith("+") and not line.startswith("+++"))
    assert "llm = ReasoningReplayLLM(**llm_kwargs)" in added
    assert _replay_methods(added) == _replay_methods(Path(runner.__file__).read_text())


def test_agent_kwargs_reach_the_runner_environment():
    h = OpenHandsSdkHarness()
    leftovers = h.configure({"agent_kwargs": {"max_iterations": 150, "include_default_tools": ["FinishTool"]}, "sandbox_backend": "docker"})
    assert leftovers == {}
    env = h.build_env(_task(), _config())
    assert env["OPENHANDS_MAX_ITERATIONS"] == "150"
    assert env["OPENHANDS_DEFAULT_TOOLS"] == "FinishTool"
    assert runner.agent_kwargs_from_env(env) == {"include_default_tools": ["FinishTool"]}


def test_agent_kwargs_unset_keep_the_sdk_defaults():
    h = OpenHandsSdkHarness()
    h.configure({})
    env = h.build_env(_task(), _config())
    assert "OPENHANDS_MAX_ITERATIONS" not in env and "OPENHANDS_DEFAULT_TOOLS" not in env
    assert runner.agent_kwargs_from_env(env) == {}


def test_empty_default_tools_include_none():
    h = OpenHandsSdkHarness()
    h.configure({"agent_kwargs": {"include_default_tools": []}})
    env = h.build_env(_task(), _config())
    assert env["OPENHANDS_DEFAULT_TOOLS"] == ""
    assert runner.agent_kwargs_from_env(env) == {"include_default_tools": []}


def test_key_value_form_and_unknown_keys():
    h = OpenHandsSdkHarness()
    leftovers = h.configure({"agent_kwargs": {"include_default_tools": "FinishTool;ThinkTool", "max_iteration": 5}})
    assert h.include_default_tools == ["FinishTool", "ThinkTool"]
    assert h.max_iterations is None
    # A typo comes back unconsumed for the wiring layer to warn about (or for a
    # subclass with that attribute to take), not silently dropped.
    assert leftovers == {"agent_kwargs": {"max_iteration": 5}}


def test_step_limit_mirrors_max_iterations_for_the_engine():
    """The SDK stops on its iteration cap without telling the runner, so the
    engine stamps MAX_TURNS_EXCEEDED by counting traces against
    ``agent_flow.step_limit`` -- the GRPO recipe's budget penalty hangs off it."""
    from rllm.engine.agentflow_engine import AgentFlowEngine
    from rllm.workflows.workflow import TerminationReason

    h = OpenHandsSdkHarness()
    assert h.step_limit == 0  # no cap: never stamps
    h.configure({"agent_kwargs": {"max_iterations": 150}})
    assert h.step_limit == 150

    class _Engine:
        agent_flow = h

    stamp = AgentFlowEngine._turn_budget_termination_reason
    assert stamp(_Engine(), 150) is TerminationReason.MAX_TURNS_EXCEEDED
    assert stamp(_Engine(), 149) is None


def test_recipe_config_matches_the_harness_keys():
    from rllm.cli._sampling import parse_mapping_spec

    cfg = Path(__file__).parents[2] / "recipe/eval/config/openhands-sdk.yaml"
    h = OpenHandsSdkHarness()
    assert h.configure({"agent_kwargs": parse_mapping_spec(f"@{cfg}", flag="--agent-kwargs")}) == {}
    assert h.max_iterations == 250
    assert h.include_default_tools == ["FinishTool"]
    assert h.strict_tool_calls is False


def test_sdk_agent_accepts_the_default_tools_kwarg():
    pytest.importorskip("openhands.sdk")
    from openhands.sdk import LLM, Agent

    llm = LLM(model="openai/m", api_key="k", base_url="http://gw/v1")
    agent = Agent(llm=llm, tools=[], **runner.agent_kwargs_from_env({"OPENHANDS_DEFAULT_TOOLS": "FinishTool"}))
    assert agent.include_default_tools == ["FinishTool"]


def test_qwen3_8_sampling_params_keep_the_server_accepted_reasoning_effort():
    # The gateway writes these over every request, so the SDK's default
    # reasoning_effort "high" (rejected by the Qwen3.8 server) never reaches it.
    from rllm.cli._sampling import SamplingConfig, parse_mapping_spec

    cfg = Path(__file__).parents[2] / "recipe/eval/config/qwen3_8-flash-next.yaml"
    sp = SamplingConfig.from_obj(parse_mapping_spec(f"@{cfg}")).as_dict()
    assert sp["reasoning_effort"] in ("xhigh", "medium", "low")
    assert sp["chat_template_kwargs"] == {"enable_thinking": True}
    assert sp["temperature"] == 1.0


def test_compiled_dependencies_install_from_wheels():
    # On glibc 2.23 images (Ubuntu 16.04) the newest tiktoken / pillow have no
    # usable wheel; building them from source fails (no Rust compiler).
    script = OpenHandsSdkHarness().install_script()
    assert "--only-binary tiktoken" in script
    assert "--only-binary pillow" in script


def test_strict_tool_calls_is_an_agent_kwarg_that_reaches_the_runner():
    h = OpenHandsSdkHarness()
    assert h.configure({"agent_kwargs": {"strict_tool_calls": True}}) == {}
    assert "--strict-tool-calls" in h.build_invocation("fix", _task(), _config())
    for off in (False, "false", "off", "0"):
        h.configure({"agent_kwargs": {"strict_tool_calls": off}})
        assert "--strict-tool-calls" not in h.build_invocation("fix", _task(), _config())
    h.configure({"agent_kwargs": {"strict_tool_calls": "on"}})
    assert h.strict_tool_calls is True
    with pytest.raises(ValueError, match="strict_tool_calls must be true or false"):
        h.configure({"agent_kwargs": {"strict_tool_calls": "sometimes"}})


def test_strict_tool_calls_off_by_default():
    assert "--strict-tool-calls" not in OpenHandsSdkHarness().build_invocation("fix", _task(), _config())


def _sdk_agent_module():
    """Stand-in for ``openhands.sdk.agent.agent`` with the SDK's repairing helpers."""
    import types

    return types.SimpleNamespace(
        normalize_tool_call=lambda name, args, tools: ("file_editor", {"command": "str_replace", **args}),
        fix_malformed_tool_arguments=lambda args, action_type: {**args, "view_range": [1, 5]},
        parse_tool_call_arguments=lambda raw: {"repaired": True},
    )


def test_strict_tool_calls_runs_calls_as_written():
    mod = _sdk_agent_module()
    runner.strict_tool_calls(mod)
    # A wrong tool name stays wrong, so the SDK's "Tool ... not found" path answers.
    assert mod.normalize_tool_call("str_replace", {"old_str": "a"}, {"file_editor", "terminal"}) == ("str_replace", {"old_str": "a"})
    assert mod.normalize_tool_call("str_replace </parameter", {}, {"str_replace"}) == ("str_replace </parameter", {})
    # Arguments are neither decoded nor completed.
    assert mod.fix_malformed_tool_arguments({"view_range": "[1, 5]"}, object) == {"view_range": "[1, 5]"}
    assert mod.parse_tool_call_arguments('{"path": "/a", "x": null, "security_rort": "LOW"}') == {"path": "/a", "x": None, "security_rort": "LOW"}


def test_strict_tool_calls_rejects_what_the_sdk_would_sanitize():
    import json

    mod = _sdk_agent_module()
    runner.strict_tool_calls(mod)
    with pytest.raises(json.JSONDecodeError):
        mod.parse_tool_call_arguments('{"command": "echo a\nb"}')  # raw control character
    with pytest.raises(ValueError, match="must be a JSON object"):
        mod.parse_tool_call_arguments("[1, 2]")


def test_strict_tool_calls_refuses_an_sdk_without_the_helpers():
    import types

    with pytest.raises(RuntimeError, match="the SDK changed"):
        runner.strict_tool_calls(types.SimpleNamespace(normalize_tool_call=None))


# ---------------------------------------------------------------------------
# end_on_invalid_tool_call: the runner backstop for gateway tool_call_validation
# ---------------------------------------------------------------------------


def _sdk_agent_with_error_paths():
    """Stand-in for ``openhands.sdk.agent.agent`` with Agent's error/execute methods."""
    import enum
    import types

    class Status(enum.Enum):
        RUNNING = "running"
        FINISHED = "finished"

    calls = []

    class Agent:
        def _emit_tool_error(self, *, error, tool_name, span_name, conversation, tool_call, llm_response_id, on_event, **_):
            calls.append(("error", tool_name))

        def _execute_actions(self, conversation, action_events, on_event):
            calls.append(("execute", len(action_events)))

        async def _aexecute_actions(self, conversation, action_events, on_event):
            calls.append(("aexecute", len(action_events)))

    return types.SimpleNamespace(Agent=Agent, ConversationExecutionStatus=Status), calls


def _conversation(status):
    import types

    return types.SimpleNamespace(state=types.SimpleNamespace(execution_status=status.RUNNING))


def test_end_on_invalid_tool_call_finishes_and_skips_the_turn(tmp_path):
    import asyncio
    import json

    mod, calls = _sdk_agent_with_error_paths()
    marker = tmp_path / "marker.json"
    marker.write_text("stale\n")
    runner.end_on_invalid_tool_call(mod, marker_path=str(marker))
    assert not marker.exists()  # a stale marker from a reused sandbox is cleared

    agent = mod.Agent()
    clean = _conversation(mod.ConversationExecutionStatus)
    agent._execute_actions(clean, [1, 2], None)
    assert calls == [("execute", 2)]
    assert clean.state.execution_status is mod.ConversationExecutionStatus.RUNNING

    conv = _conversation(mod.ConversationExecutionStatus)
    kw = dict(span_name="X", tool_call=None, llm_response_id="r", on_event=None)
    agent._emit_tool_error(error="Error validating tool 'terminal': command Field required", tool_name="terminal", conversation=conv, **kw)
    assert conv.state.execution_status is mod.ConversationExecutionStatus.FINISHED
    agent._execute_actions(conv, [1], None)
    asyncio.run(agent._aexecute_actions(conv, [1], None))
    assert calls == [("execute", 2), ("error", "terminal")]  # the turn's other actions did not run
    (line,) = marker.read_text().splitlines()
    assert json.loads(line)["tool_name"] == "terminal"


def test_end_on_invalid_tool_call_refuses_an_sdk_without_the_methods():
    import types

    with pytest.raises(RuntimeError, match="the SDK changed"):
        runner.end_on_invalid_tool_call(types.SimpleNamespace(Agent=object, ConversationExecutionStatus=object))


def test_end_on_invalid_tool_call_patches_the_real_sdk_names():
    """The names patched exist in the pinned SDK (skipped where it is not installed)."""
    agent_mod = pytest.importorskip("openhands.sdk.agent.agent")
    for name in ("_emit_tool_error", "_execute_actions", "_aexecute_actions"):
        assert hasattr(agent_mod.Agent, name)
    assert hasattr(agent_mod, "ConversationExecutionStatus")


def test_end_on_invalid_tool_call_kwarg_requires_strict():
    h = OpenHandsSdkHarness()
    with pytest.raises(ValueError, match="requires strict_tool_calls"):
        h.configure({"agent_kwargs": {"end_on_invalid_tool_call": True}})
    h = OpenHandsSdkHarness()
    assert h.configure({"agent_kwargs": {"strict_tool_calls": True, "end_on_invalid_tool_call": "on"}}) == {}
    cmd = h.build_invocation("fix", _task(), _config())
    assert "--strict-tool-calls" in cmd and "--end-on-invalid-tool-call" in cmd
    assert "--end-on-invalid-tool-call" not in OpenHandsSdkHarness().build_invocation("fix", _task(), _config())


@pytest.mark.parametrize(("marker", "fired"), [("", 0.0), ('{"tool_name": "terminal", "error": "x"}\n', 1.0)])
def test_run_reports_the_backstop(monkeypatch, marker, fired):
    from rllm.harnesses.cli_harness import BaseCliHarness

    monkeypatch.setattr(BaseCliHarness, "run", lambda self, task, config, *, env: None)
    h = OpenHandsSdkHarness(strict_tool_calls=True, end_on_invalid_tool_call=True)
    episode = h.run(_task(), _config(), env=FakeSandbox(stdout=marker))
    assert episode.metrics["format/backstop"] == fired


def test_run_without_backstop_is_unchanged(monkeypatch):
    from rllm.harnesses.cli_harness import BaseCliHarness

    monkeypatch.setattr(BaseCliHarness, "run", lambda self, task, config, *, env: None)
    sandbox = FakeSandbox()
    assert OpenHandsSdkHarness().run(_task(), _config(), env=sandbox) is None
    assert sandbox.calls == []
