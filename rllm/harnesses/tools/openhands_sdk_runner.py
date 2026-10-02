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
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import tempfile


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an openhands-sdk agent on one task")
    parser.add_argument("--instruction", required=True, help="Task instruction")
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

    os.chdir(workspace)

    model = os.environ.get("LLM_MODEL")
    if not model:
        print("openhands-sdk runner: LLM_MODEL is not set", file=sys.stderr)
        return 2

    # Sampling params are the gateway's job -- it rewrites them on the way
    # through -- so the LLM is configured with routing only.
    llm = reasoning_replay_llm(LLM)(
        model=model,
        api_key=os.environ.get("LLM_API_KEY", "sk-rllm-gateway"),
        base_url=os.environ.get("LLM_BASE_URL"),
    )

    tools = [
        Tool(name=TerminalTool.name),
        Tool(name=FileEditorTool.name),
        Tool(name=TaskTrackerTool.name),
    ]
    agent = Agent(llm=llm, tools=tools)

    conversation_kwargs: dict[str, object] = {"agent": agent, "workspace": workspace}
    max_iterations = os.environ.get("OPENHANDS_MAX_ITERATIONS")
    if max_iterations:
        conversation_kwargs["max_iteration_per_run"] = int(max_iterations)
    conversation = Conversation(**conversation_kwargs)  # type: ignore[arg-type]

    print(f"openhands-sdk runner: model={model} workspace={workspace}", flush=True)
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
