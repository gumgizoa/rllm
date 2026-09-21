"""Tests for trace_converter: trace_record_to_step with tool_calls support."""

from rllm_model_gateway.models import TraceRecord

from rllm.engine.trace_converter import (
    REQUEST_TOOLS_KEY,
    _parse_openai_tool_calls,
    trace_record_to_step,
)

# ------------------------------------------------------------------
# _parse_openai_tool_calls
# ------------------------------------------------------------------


class TestParseOpenaiToolCalls:
    def test_basic_conversion(self):
        raw = [
            {
                "id": "call_0",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "London"}',
                },
            }
        ]
        result = _parse_openai_tool_calls(raw)
        assert len(result) == 1
        assert result[0].name == "get_weather"
        assert result[0].arguments == {"city": "London"}

    def test_multiple_tool_calls(self):
        raw = [
            {
                "id": "call_0",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            },
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "calc", "arguments": '{"expr": "1+1"}'},
            },
        ]
        result = _parse_openai_tool_calls(raw)
        assert len(result) == 2
        assert result[0].name == "search"
        assert result[1].name == "calc"
        assert result[1].arguments == {"expr": "1+1"}

    def test_invalid_json_arguments(self):
        raw = [
            {
                "id": "call_0",
                "type": "function",
                "function": {"name": "foo", "arguments": "not-json"},
            }
        ]
        result = _parse_openai_tool_calls(raw)
        assert result[0].name == "foo"
        assert result[0].arguments == {"raw": "not-json"}

    def test_dict_arguments(self):
        """Arguments already parsed as dict (e.g. from in-process handler)."""
        raw = [
            {
                "id": "call_0",
                "type": "function",
                "function": {"name": "bar", "arguments": {"x": 1}},
            }
        ]
        result = _parse_openai_tool_calls(raw)
        assert result[0].arguments == {"x": 1}

    def test_empty_list(self):
        assert _parse_openai_tool_calls([]) == []


# ------------------------------------------------------------------
# trace_record_to_step with tool_calls
# ------------------------------------------------------------------


class TestTraceRecordToStep:
    def _make_trace(self, **overrides) -> TraceRecord:
        defaults = {
            "trace_id": "t-001",
            "session_id": "s-001",
            "model": "test-model",
            "messages": [{"role": "user", "content": "hello"}],
            "prompt_token_ids": [1, 2, 3],
            "response_message": {
                "role": "assistant",
                "content": "Hi there!",
            },
            "completion_token_ids": [10, 11],
            "logprobs": [-0.5, -0.3],
            "finish_reason": "stop",
        }
        defaults.update(overrides)
        return TraceRecord(**defaults)

    def test_basic_step(self):
        trace = self._make_trace()
        step = trace_record_to_step(trace)

        assert step.id == "t-001"
        assert step.model_response == "Hi there!"
        assert step.model_output.content == "Hi there!"
        assert step.model_output.prompt_ids == [1, 2, 3]
        assert step.model_output.completion_ids == [10, 11]
        assert step.model_output.logprobs == [-0.5, -0.3]
        assert step.model_output.tool_calls is None

    def test_weight_version_propagated(self):
        trace = self._make_trace(weight_version=7)
        step = trace_record_to_step(trace)
        assert step.weight_version == 7
        assert step.model_output.weight_version == 7

    def test_weight_version_defaults_none(self):
        step = trace_record_to_step(self._make_trace())
        assert step.weight_version is None

    def test_step_with_tool_calls(self):
        trace = self._make_trace(
            response_message={
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_0",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "London"}',
                        },
                    },
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calculate",
                            "arguments": '{"expr": "2+2"}',
                        },
                    },
                ],
            },
            finish_reason="tool_calls",
        )
        step = trace_record_to_step(trace)

        assert step.model_output.tool_calls is not None
        assert len(step.model_output.tool_calls) == 2
        assert step.model_output.tool_calls[0].name == "get_weather"
        assert step.model_output.tool_calls[0].arguments == {"city": "London"}
        assert step.model_output.tool_calls[1].name == "calculate"
        assert step.model_output.tool_calls[1].arguments == {"expr": "2+2"}
        assert step.model_output.finish_reason == "tool_calls"

    def test_step_with_reasoning(self):
        trace = self._make_trace(
            response_message={
                "role": "assistant",
                "content": "42",
                "reasoning": "Let me think...",
            },
        )
        step = trace_record_to_step(trace)
        assert step.thought == "Let me think..."
        assert step.model_output.reasoning == "Let me think..."

    def test_step_with_reasoning_content_and_tool_call(self):
        """OpenAI-compatible GLM responses retain reasoning and tool calls."""
        trace = self._make_trace(
            response_message={
                "role": "assistant",
                "content": "I will inspect the repository.",
                "reasoning_content": "Let me think through this...",
                "tool_calls": [
                    {
                        "id": "call_0",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command": "find . -maxdepth 2 -type d"}',
                        },
                    }
                ],
            },
            finish_reason="tool_calls",
        )
        step = trace_record_to_step(trace)

        assert step.thought == "Let me think through this..."
        assert step.model_output.reasoning == "Let me think through this..."
        assert step.model_output.tool_calls is not None
        assert step.model_output.tool_calls[0].name == "bash"
        assert step.model_output.tool_calls[0].arguments == {"command": "find . -maxdepth 2 -type d"}

    def test_chat_completions_includes_response(self):
        trace = self._make_trace()
        step = trace_record_to_step(trace)
        assert len(step.chat_completions) == 2  # user msg + assistant msg
        assert step.chat_completions[-1]["role"] == "assistant"

    def test_no_tool_calls_key_means_none(self):
        """If response_message has no tool_calls key, model_output.tool_calls should be None."""
        trace = self._make_trace(
            response_message={"role": "assistant", "content": "just text"},
        )
        step = trace_record_to_step(trace)
        assert step.model_output.tool_calls is None


# ------------------------------------------------------------------
# request tools
# ------------------------------------------------------------------


class TestRequestTools:
    """Tool schemas are a request field, not a message.

    The server renders them into the system block at inference (Qwen3.5: the
    ``# Tools`` section plus the ``<function=...>`` call-format instruction), so
    ``chat_completions`` alone cannot reproduce what the policy saw. Anything
    that re-renders those messages later - SFT above all - needs the array, and
    ``raw_request`` is the only place it exists.
    """

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Execute a bash command",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
            },
        }
    ]

    def _make_trace(self, **overrides) -> TraceRecord:
        defaults = {
            "trace_id": "t-001",
            "session_id": "s-001",
            "messages": [{"role": "user", "content": "hello"}],
            "response_message": {"role": "assistant", "content": "hi"},
        }
        defaults.update(overrides)
        return TraceRecord(**defaults)

    def test_tools_are_copied_from_raw_request(self):
        trace = self._make_trace(raw_request={"model": "m", "messages": [], "tools": self.TOOLS})
        assert trace_record_to_step(trace).metadata[REQUEST_TOOLS_KEY] == self.TOOLS

    def test_absent_when_the_request_declared_none(self):
        for raw_request in (None, {}, {"messages": []}, {"tools": []}, {"tools": None}, {"tools": "bash"}):
            step = trace_record_to_step(self._make_trace(raw_request=raw_request))
            assert REQUEST_TOOLS_KEY not in (step.metadata or {}), raw_request

    def test_existing_metadata_is_preserved_and_not_mutated(self):
        original = {"session": "abc"}
        trace = self._make_trace(metadata=original, raw_request={"tools": self.TOOLS})
        step = trace_record_to_step(trace)

        assert step.metadata["session"] == "abc"
        assert step.metadata[REQUEST_TOOLS_KEY] == self.TOOLS
        assert original == {"session": "abc"}, "the caller's dict must not be mutated"

    def test_gateway_metadata_wins_on_collision(self):
        trace = self._make_trace(
            metadata={REQUEST_TOOLS_KEY: ["already set"]},
            raw_request={"tools": self.TOOLS},
        )
        assert trace_record_to_step(trace).metadata[REQUEST_TOOLS_KEY] == ["already set"]
