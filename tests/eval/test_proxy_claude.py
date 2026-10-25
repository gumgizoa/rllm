"""Proxy params and the tool-message cache placement used for Claude."""

from __future__ import annotations

from pathlib import Path

from rllm.cli._sampling import parse_mapping_spec
from rllm.eval.proxy import EvalProxyManager

CFG = Path(__file__).parents[2] / "recipe/eval/config/claude-opus-5-5-proxy.yaml"


def test_proxy_params_are_merged_into_litellm_params():
    extra = parse_mapping_spec(f"@{CFG}", flag="--proxy-params")
    pm = EvalProxyManager("anthropic", "claude-opus-5-5", "os.environ/ANTHROPIC_API_KEY", extra_litellm_params=extra)
    params = pm.build_proxy_config()["model_list"][0]["litellm_params"]
    assert params["model"] == "anthropic/claude-opus-5-5"
    assert params["api_key"] == "os.environ/ANTHROPIC_API_KEY"  # the key itself stays in the environment
    assert params["thinking"] == {"type": "adaptive"}
    assert {"temperature", "top_p", "top_k", "reasoning_effort"} <= set(params["additional_drop_params"])
    assert {"location": "message", "index": -1} in params["cache_control_injection_points"]


def test_no_proxy_params_keeps_the_config_unchanged():
    pm = EvalProxyManager("anthropic", "claude-opus-5-5", "k")
    assert set(pm.build_proxy_config()["model_list"][0]["litellm_params"]) == {"model", "api_key"}


def test_cache_breakpoint_goes_on_the_tool_message_not_its_content():
    from litellm.integrations.anthropic_cache_control_hook import AnthropicCacheControlHook as Hook

    import rllm.eval._litellm_server  # noqa: F401  (installs the patch)

    tool = {"role": "tool", "tool_call_id": "t1", "content": [{"type": "text", "text": "out"}]}
    Hook._safe_insert_cache_control_in_message(tool, {"type": "ephemeral"})
    assert tool["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in tool["content"][0]
    user = {"role": "user", "content": [{"type": "text", "text": "x"}]}
    Hook._safe_insert_cache_control_in_message(user, {"type": "ephemeral"})
    assert user["content"][0]["cache_control"] == {"type": "ephemeral"}
