"""``OpenHandsSdkHarness.enable_thinking`` reaches the SDK as a chat-template kwarg.

Turn 1 of an episode is rendered by vLLM's chat template from the request body, so the
thinking polarity has to travel with the request: harness attribute -> env var -> runner ->
``LLM(litellm_extra_body={"chat_template_kwargs": ...})``.
"""

from __future__ import annotations

import pytest

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.harnesses.tools import openhands_sdk_runner as runner
from rllm.types import AgentConfig, Task


def _task() -> Task:
    return Task(id="t", instruction="fix it", metadata={"workdir": "/testbed"})


def test_enable_thinking_reaches_the_runner_env_only_when_set() -> None:
    cfg = AgentConfig(model="m", base_url="http://gw/v1", session_uid="s")
    assert "OPENHANDS_SDK_ENABLE_THINKING" not in OpenHandsSdkHarness().build_env(_task(), cfg)
    assert OpenHandsSdkHarness(enable_thinking=False).build_env(_task(), cfg)["OPENHANDS_SDK_ENABLE_THINKING"] == "0"
    assert OpenHandsSdkHarness(enable_thinking=True).build_env(_task(), cfg)["OPENHANDS_SDK_ENABLE_THINKING"] == "1"


def test_runner_maps_the_env_to_chat_template_kwargs() -> None:
    assert runner._chat_template_kwargs_from_env({}) == {}
    assert runner._chat_template_kwargs_from_env({"OPENHANDS_SDK_ENABLE_THINKING": "0"}) == {"enable_thinking": False}
    assert runner._chat_template_kwargs_from_env({"OPENHANDS_SDK_ENABLE_THINKING": "true"}) == {"enable_thinking": True}
    with pytest.raises(ValueError):
        runner._chat_template_kwargs_from_env({"OPENHANDS_SDK_ENABLE_THINKING": "maybe"})
