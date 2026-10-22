"""vLLM's own chat parsers for cumulative-mode turns.

Cumulative token mode sends turn 2+ to ``/v1/completions``, so vLLM's reasoning
and tool-call parsers never see those turns; the renderer parses them instead.
For Qwen3.5 the two disagree on the same completion (measured on 400 Run-3
states of a 9B checkpoint):

* the renderer is not told the prompt ended in ``<think>``, so the reasoning
  lands in ``content`` together with ``</think>`` (397/400);
* a ``<tool_call>`` left unclosed before the next one swallows the following
  calls into its last argument, where vLLM closes it and keeps them (9/400) --
  the agent's action is silently dropped in training but runs in eval;
* argument values lose leading indentation and a trailing newline (14/400).

Eval talks to vLLM's chat endpoint, so running the same parser classes here
makes a training turn look exactly like an eval turn to the agent. The tokens
the policy is trained on are unaffected either way.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class VllmChatParser:
    """Shape raw completion text the way vLLM's ``/v1/chat/completions`` does.

    Mirrors the non-streaming path of ``OpenAIServingChat`` with auto tool
    choice: the reasoning parser splits ``reasoning`` from ``content``, then the
    tool parser extracts calls from the content only. Needs ``vllm`` importable
    in the gateway's environment.
    """

    def __init__(self, tokenizer: Any, reasoning_parser: str | None, tool_call_parser: str | None) -> None:
        from vllm.reasoning import ReasoningParserManager
        from vllm.tool_parsers import ToolParserManager

        self.tokenizer = tokenizer
        self.reasoning_parser_cls = ReasoningParserManager.get_reasoning_parser(reasoning_parser) if reasoning_parser else None
        self.tool_parser_cls = ToolParserManager.get_tool_parser(tool_call_parser) if tool_call_parser else None
        logger.info("Cumulative turns parsed with vLLM parsers: reasoning=%s tool_call=%s", reasoning_parser, tool_call_parser)

    def _request(self, request_body: dict[str, Any]) -> Any:
        from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest

        # The parsers read only tools / tool_choice / chat_template_kwargs; the
        # history is not needed (and validating it is wasted work).
        fields = {"model": request_body.get("model") or "gateway", "messages": [{"role": "user", "content": ""}]}
        for key in ("tools", "tool_choice", "chat_template_kwargs"):
            if request_body.get(key) is not None:
                fields[key] = request_body[key]
        return ChatCompletionRequest.model_validate(fields)

    def parse(self, text: str, request_body: dict[str, Any]) -> dict[str, Any]:
        request = self._request(request_body)

        reasoning, content = None, text
        if self.reasoning_parser_cls is not None:
            parser = self.reasoning_parser_cls(self.tokenizer, chat_template_kwargs=request.chat_template_kwargs or {})
            reasoning, content = parser.extract_reasoning(text, request=request)

        tool_calls: list[dict[str, Any]] = []
        if self.tool_parser_cls is not None and request.tools and request.tool_choice in (None, "auto"):
            info = self.tool_parser_cls(self.tokenizer, request.tools).extract_tool_calls(content if content is not None else "", request=request)
            if info is not None and info.tools_called:
                tool_calls = [
                    {
                        "id": tc.id or f"chatcmpl-tool-{uuid.uuid4().hex}",
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in info.tool_calls
                ]
                content = info.content
                if content and content.strip() == "":
                    content = None

        message: dict[str, Any] = {"role": "assistant", "content": content, "reasoning": reasoning}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message
