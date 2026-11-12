#!/usr/bin/env python3
"""Drive an openhands-sdk agent over one task inside an rLLM sandbox.

openhands-sdk is a library rather than a CLI, so :class:`~rllm.harnesses.openhands_sdk.OpenHandsSdkHarness`
ships this script into the sandbox and runs it with the SDK's own
interpreter. Unlike Harbor's runner it writes no trajectory file: rLLM's
gateway sits in front of every LLM call, so the engine builds the Episode
from wire-level traces and this script only has to drive the agent and
leave a readable log behind.

Configuration arrives through the environment, matching the names the
Harbor scaffold uses so a trajectory from either path looks the same:

``LLM_MODEL``        provider-qualified model name (litellm form)
``LLM_BASE_URL``     gateway session URL
``LLM_API_KEY``      gateway bearer token, or a placeholder on loopback
``OPENHANDS_MAX_ITERATIONS``  optional cap on agent steps per run
``OPENHANDS_SDK_SYSTEM_PROMPT_PATH``  optional absolute path to a Jinja
                     template that replaces the SDK's default system prompt
                     (same name Harbor's openhands-sdk scaffold uses)
``OPENHANDS_DEFAULT_TOOLS``   optional comma-separated SDK built-in tools to
                             include (default FinishTool and ThinkTool); set
                             but empty includes none
``OPENHANDS_SDK_ENABLE_THINKING``  optional ``enable_thinking`` chat-template
                             kwarg sent with every request (see below)
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import tempfile

# Thinking on/off is a chat-template kwarg for Qwen3-family models, and the
# first turn of every conversation is rendered by vLLM's chat template (the
# gateway forwards that request body verbatim), so it has to travel with the
# request: litellm's ``extra_body`` lands top-level in the JSON and vLLM reads
# ``chat_template_kwargs`` from there. Later turns are rendered by the
# gateway's renderer, whose ``enable_thinking`` kwarg the harness sets from the
# same source (see rllm/harnesses/openhands_sdk.py); the two must agree or
# turn 1 and turns 2+ are shaped differently.
_ENABLE_THINKING_ENV = "OPENHANDS_SDK_ENABLE_THINKING"


def _chat_template_kwargs_from_env(environ=os.environ) -> dict[str, object]:
    """``{"enable_thinking": bool}`` from ``OPENHANDS_SDK_ENABLE_THINKING``, or ``{}`` when unset."""
    raw = environ.get(_ENABLE_THINKING_ENV)
    if raw is None or raw.strip() == "":
        return {}
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return {"enable_thinking": True}
    if value in ("0", "false", "no", "off"):
        return {"enable_thinking": False}
    raise ValueError(f"{_ENABLE_THINKING_ENV} must be a boolean-ish string, got {raw!r}")


def reasoning_replay_llm(llm_cls):
    """Subclass the SDK's ``LLM`` so every request carries past turns' reasoning.

    The SDK sends an assistant turn's ``reasoning_content`` back only for a
    hardcoded model list (kimi, deepseek, minimax), and ``capability_overrides``
    cannot change that. Qwen3.x and GLM chat templates render a past turn
    without it as an empty ``<think></think>``; after a couple of those the
    model stops thinking for the rest of the rollout. Templates that do not use
    the field ignore it, so it is always sent.

    The SDK names the field ``reasoning_content``, but vLLM before 0.22 reads a
    past turn's reasoning only from ``reasoning`` and drops ``reasoning_content``
    before the template sees it, so the value is copied to ``reasoning`` too.

    Takes the class rather than importing it: the SDK must be imported from an
    empty cwd (see ``main``).
    """

    class ReasoningReplayLLM(llm_cls):
        def _model_features(self):
            return dataclasses.replace(super()._model_features(), send_reasoning_content=True)

        def _to_chat_dicts(self, messages):
            dicts = super()._to_chat_dicts(messages)
            for d in dicts:
                if d.get("reasoning_content") and not d.get("reasoning"):
                    d["reasoning"] = d["reasoning_content"]
            return dicts

    return ReasoningReplayLLM


def strict_tool_calls(agent_module) -> None:
    """Run tool calls as the model wrote them, so a wrong one comes back as an error.

    The SDK quietly repairs tool calls before running them
    (``openhands.sdk.agent.utils``): it renames unknown tools
    (``str_replace``/``str_replace_editor`` -> ``file_editor``, ``bash``/``command``/...
    -> ``terminal``), cuts XML fragments off malformed names, turns bare shell
    names into terminal commands, infers ``file_editor``'s missing ``command``,
    decodes list/dict arguments sent as JSON strings, joins chunked strings,
    escapes raw control characters, fixes ``security_risk`` typos and drops
    ``None`` arguments. The call then succeeds, the model's next prompt still
    holds the call as it sampled it, and a policy trained on such rollouts is
    rewarded for the wrong call and never told otherwise.

    With every repair replaced, the SDK's own error paths answer instead:
    ``Tool 'str_replace' not found. Available: [...]`` for a wrong name, and a
    validation error naming the parameters for wrong arguments. Rebinds the
    names ``agent_module`` (``openhands.sdk.agent.agent``) imported, and fails
    loudly if an SDK release renamed them, rather than run unpatched.
    """
    import json

    names = ("normalize_tool_call", "fix_malformed_tool_arguments", "parse_tool_call_arguments")
    missing = [n for n in names if not hasattr(agent_module, n)]
    if missing:
        raise RuntimeError(f"openhands-sdk runner: strict tool calls cannot patch {missing}; the SDK changed")

    def normalize_tool_call(tool_name, arguments, available_tools):
        return tool_name, dict(arguments)

    def fix_malformed_tool_arguments(arguments, action_type):
        return arguments

    def parse_tool_call_arguments(raw_arguments):
        parsed = json.loads(raw_arguments)
        if not isinstance(parsed, dict):
            raise ValueError(f"tool arguments must be a JSON object, got {type(parsed).__name__}")
        return parsed

    agent_module.normalize_tool_call = normalize_tool_call
    agent_module.fix_malformed_tool_arguments = fix_malformed_tool_arguments
    agent_module.parse_tool_call_arguments = parse_tool_call_arguments


# Written by end_on_invalid_tool_call, read back by the harness (OpenHandsSdkHarness.run).
INVALID_TOOL_CALL_MARKER = "/tmp/openhands-sdk-invalid-tool-call.json"


def end_on_invalid_tool_call(agent_module, marker_path: str = INVALID_TOOL_CALL_MARKER) -> None:
    """End the conversation at the first tool call the SDK rejects.

    Backstop for the gateway's ``tool_call_validation: drop``, which ends the
    episode at a malformed call by handing the turn back as text. Anything the
    gateway lets through but the SDK still rejects -- an unknown tool or a
    failed argument validation (types, nested fields) -- lands in
    ``Agent._emit_tool_error``, the only place the SDK reports those two (tool
    *execution* errors take another path and are left alone). The wrapper keeps
    the SDK's error event, marks the conversation FINISHED so the run loop stops
    after this step, skips the turn's remaining actions, and appends a line to
    ``marker_path`` so the harness can report the backstop firing.
    Use together with :func:`strict_tool_calls`, or the SDK repairs most such
    calls before they ever reach validation.
    """
    import json

    agent_cls = getattr(agent_module, "Agent", None)
    status_cls = getattr(agent_module, "ConversationExecutionStatus", None)
    names = ("_emit_tool_error", "_execute_actions", "_aexecute_actions")
    missing = [n for n in names if agent_cls is None or not hasattr(agent_cls, n)]
    if agent_cls is None or status_cls is None or missing:
        raise RuntimeError(f"openhands-sdk runner: end_on_invalid_tool_call cannot patch {missing or ['Agent/ConversationExecutionStatus']}; the SDK changed")
    try:
        os.remove(marker_path)
    except FileNotFoundError:
        pass

    orig_emit = agent_cls._emit_tool_error
    orig_exec = agent_cls._execute_actions
    orig_aexec = agent_cls._aexecute_actions
    # Conversations that hit an invalid call (by id: no attribute is set on the
    # SDK's objects, whatever their model config allows).
    ended: set[int] = set()

    def _emit_tool_error(self, *args, **kwargs):
        orig_emit(self, *args, **kwargs)
        conversation = kwargs.get("conversation")
        if conversation is not None:
            conversation.state.execution_status = status_cls.FINISHED
            ended.add(id(conversation))
        record = {"tool_name": kwargs.get("tool_name"), "error": str(kwargs.get("error", ""))[:500]}
        with open(marker_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        print(f"openhands-sdk runner: invalid tool call, ending the episode: {record['error'][:200]}", flush=True)

    def _execute_actions(self, conversation, *args, **kwargs):
        if id(conversation) in ended:
            return None
        return orig_exec(self, conversation, *args, **kwargs)

    async def _aexecute_actions(self, conversation, *args, **kwargs):
        if id(conversation) in ended:
            return None
        return await orig_aexec(self, conversation, *args, **kwargs)

    agent_cls._emit_tool_error = _emit_tool_error
    agent_cls._execute_actions = _execute_actions
    agent_cls._aexecute_actions = _aexecute_actions


def agent_kwargs_from_env(environ) -> dict:
    """Extra ``Agent`` kwargs from the environment (``include_default_tools``)."""
    tools = environ.get("OPENHANDS_DEFAULT_TOOLS")
    if tools is None:
        return {}
    return {"include_default_tools": [t for t in tools.split(",") if t]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an openhands-sdk agent on one task")
    parser.add_argument("--instruction", required=True, help="Task instruction")
    parser.add_argument("--strict-tool-calls", action="store_true", help="Do not repair tool calls; report wrong ones to the model (strict_tool_calls)")
    parser.add_argument("--end-on-invalid-tool-call", action="store_true", help="End the conversation at the first tool call the SDK rejects (end_on_invalid_tool_call)")
    args = parser.parse_args()

    # The task's repo is the cwd: the harness cd's into ``[environment].workdir``
    # when the task declares one, otherwise the image's own WORKDIR applies.
    workspace = os.getcwd()
    # litellm appends the cwd to ``sys.path`` on import, after which the SDK's
    # optional imports resolve into the repo (/testbed/tornado breaks
    # tenacity). Import from an empty directory, then go back.
    os.chdir(tempfile.mkdtemp(prefix="openhands-sdk-import-"))
    from openhands.sdk import LLM, Agent, Conversation, Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    if args.strict_tool_calls or args.end_on_invalid_tool_call:
        import openhands.sdk.agent.agent as agent_module

        if args.strict_tool_calls:
            strict_tool_calls(agent_module)
        if args.end_on_invalid_tool_call:
            end_on_invalid_tool_call(agent_module)
    os.chdir(workspace)

    model = os.environ.get("LLM_MODEL")
    if not model:
        print("openhands-sdk runner: LLM_MODEL is not set", file=sys.stderr)
        return 2

    # Sampling params are the gateway's job -- it rewrites them on the way
    # through -- so the LLM is configured with routing only.
    llm_kwargs: dict[str, object] = {
        "model": model,
        "api_key": os.environ.get("LLM_API_KEY", "sk-rllm-gateway"),
        "base_url": os.environ.get("LLM_BASE_URL"),
    }
    chat_template_kwargs = _chat_template_kwargs_from_env()
    if chat_template_kwargs:
        llm_kwargs["litellm_extra_body"] = {"chat_template_kwargs": chat_template_kwargs}
    llm = reasoning_replay_llm(LLM)(**llm_kwargs)  # type: ignore[arg-type]

    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    # ``include_default_tools`` from OPENHANDS_DEFAULT_TOOLS (FinishTool / ThinkTool).
    extra = agent_kwargs_from_env(os.environ)
    agent_kwargs: dict[str, object] = {"llm": llm, "tools": tools, **extra}
    # The SDK's default system prompt prescribes its own problem-solving
    # procedure, which outranks any workflow the task instruction asks for.
    # A harness that needs a different procedure ships a template and points
    # here; the SDK renders it in place of the default.
    system_prompt_path = os.environ.get("OPENHANDS_SDK_SYSTEM_PROMPT_PATH")
    if system_prompt_path:
        if not os.path.isabs(system_prompt_path) or not os.path.isfile(system_prompt_path):
            print(f"openhands-sdk runner: OPENHANDS_SDK_SYSTEM_PROMPT_PATH must be an existing absolute path, got {system_prompt_path!r}", file=sys.stderr)
            return 2
        agent_kwargs["system_prompt_filename"] = system_prompt_path
    agent = Agent(**agent_kwargs)  # type: ignore[arg-type]

    conversation_kwargs: dict[str, object] = {"agent": agent, "workspace": workspace}
    max_iterations = os.environ.get("OPENHANDS_MAX_ITERATIONS")
    if max_iterations:
        conversation_kwargs["max_iteration_per_run"] = int(max_iterations)
    conversation = Conversation(**conversation_kwargs)  # type: ignore[arg-type]

    print(
        f"openhands-sdk runner: model={model} workspace={workspace} "
        f"chat_template_kwargs={chat_template_kwargs or None} "
        f"system_prompt={system_prompt_path or 'sdk default'} "
        f"default_tools={extra.get('include_default_tools', 'sdk default')} "
        f"max_iterations={conversation_kwargs.get('max_iteration_per_run', 'sdk default')} "
        f"strict_tool_calls={args.strict_tool_calls} "
        f"end_on_invalid_tool_call={args.end_on_invalid_tool_call}",
        flush=True,
    )
    conversation.send_message(args.instruction)
    conversation.run()

    usage = llm.metrics.accumulated_token_usage
    if usage is not None:
        print(
            f"openhands-sdk runner: done, prompt_tokens={usage.prompt_tokens} completion_tokens={usage.completion_tokens}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
