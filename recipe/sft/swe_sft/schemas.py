"""The SFT parquet contract: data models only.

One row is one training sample, stored as **four JSON string columns**:

===========================  =========================================================
``messages``                 required. JSON array of message objects (below).
``tools``                    ``null`` or a JSON array of OpenAI tool schemas.
``apply_chat_template_kwargs``  ``null`` or a JSON object forwarded to
                             ``apply_chat_template`` for this row (e.g.
                             ``{"enable_thinking": false}``).
``metadata``                 ``null`` or a JSON object of dataset-specific
                             provenance. Never read during training.
===========================  =========================================================

Message objects::

    {"role": "system",    "content": str}
    {"role": "user",      "content": str}
    {"role": "assistant", "content": str,          # "" allowed (tool-call-only turn)
                          "reasoning": str,        # OMIT for a non-thinking turn
                          "tool_calls": [...]}     # optional
    {"role": "tool",      "content": str, "tool_call_id": str}   # id optional

Rules that exist because breaking them fails *silently*:

* ``tool_calls[*].function.arguments`` is a **mapping**, never a JSON string. Chat
  templates iterate it (Jinja ``|items``); a string raises
  ``TypeError: Can only get item pairs from a mapping``.
* Only these positions ever hold JSON text: the four columns above and
  ``arguments``. ``content`` is **never** parsed - tool output is frequently valid
  JSON, and parsing it turns a string into a dict the template rejects. Never
  decide what to parse by sniffing whether a string looks like JSON.
* Serialize by parsing the upstream value to a native object first, then dumping
  **once**. Dumping an already-JSON string double-encodes it, and the reader gets
  a ``str`` where it expected a list.
* Reasoning lives in ``reasoning``, matching vLLM's field name. Chat templates
  read ``reasoning_content``; :meth:`SFTSample.to_chat_messages` does that rename.
  Writing ``reasoning_content`` straight into the parquet would work for Qwen and
  break for anything else, so it is rejected here.
* A non-thinking assistant turn **omits** ``reasoning`` (not ``""``) *and* the row
  must set ``enable_thinking: false``. Without the flag the template's generation
  prompt stops at ``<think>\\n``, so the forced ``</think>`` lands inside the
  supervised target and the model is trained to close an empty reasoning block it
  never actually emits.

This module holds the models and nothing else. Reading rows back out of parquet is
``dataset.utils.serde``; rendering them is ``dataset.utils.render``. The dependency
runs one way only: ``utils`` imports ``schemas``, never the reverse.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, model_validator

COLUMNS = ("messages", "tools", "apply_chat_template_kwargs", "metadata")

PARQUET_SCHEMA = pa.schema([pa.field(name, pa.string()) for name in COLUMNS])

# Chat templates read this; the parquet stores `reasoning`.
TEMPLATE_REASONING_KEY = "reasoning_content"

# Substrings that must never appear in message text: they would tokenize as
# control tokens and let data impersonate turn boundaries.
FORBIDDEN_IN_CONTENT = (
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "<think>",
    "</think>",
)


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    # A mapping, never a JSON string - see the module docstring.
    arguments: dict[str, Any] = {}


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: FunctionCall
    type: Literal["function"] = "function"
    id: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    reasoning: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Message:
        if self.role != "assistant":
            for field in ("reasoning", "tool_calls"):
                if getattr(self, field) is not None:
                    raise ValueError(f"{field!r} is only valid on an assistant message, got role={self.role!r}")
        if self.role != "tool" and self.tool_call_id is not None:
            raise ValueError(f"'tool_call_id' is only valid on a tool message, got role={self.role!r}")
        if self.reasoning is not None and not self.reasoning.strip():
            raise ValueError("'reasoning' must be non-empty; omit the field entirely for a non-thinking turn")
        for marker in FORBIDDEN_IN_CONTENT:
            if marker in self.content:
                raise ValueError(f"content must not contain {marker!r} (reasoning belongs in 'reasoning')")
        return self

    def to_chat_message(self) -> dict[str, Any]:
        """Render-ready dict: ``reasoning`` renamed, empty optionals dropped."""
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.reasoning is not None:
            out[TEMPLATE_REASONING_KEY] = self.reasoning
        if self.tool_calls:
            out["tool_calls"] = [call.model_dump(exclude_none=True) for call in self.tool_calls]
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        return out


class SFTSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[Message]
    tools: list[dict[str, Any]] | None = None
    apply_chat_template_kwargs: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check(self) -> SFTSample:
        if not self.messages:
            raise ValueError("messages must not be empty")
        if not any(m.role == "user" for m in self.messages):
            # Qwen-style templates hard-fail without a non-tool user query.
            raise ValueError("at least one 'user' message is required")
        if self.messages[-1].role != "assistant":
            # Anything after the last assistant turn can never be supervised.
            raise ValueError(f"the last message must be 'assistant', got {self.messages[-1].role!r}")

        thinking = (self.apply_chat_template_kwargs or {}).get("enable_thinking")
        without_reasoning = [i for i, m in enumerate(self.messages) if m.role == "assistant" and m.reasoning is None]
        if without_reasoning and thinking is not False:
            raise ValueError(
                f"assistant message(s) {without_reasoning} have no 'reasoning', which requires "
                "apply_chat_template_kwargs={'enable_thinking': False}; otherwise the template's "
                "forced </think> is trained as if the model had produced it"
            )
        if thinking is False and any(m.reasoning is not None for m in self.messages):
            raise ValueError("enable_thinking=False contradicts an assistant message that carries 'reasoning'")
        return self

    def to_chat_messages(self) -> list[dict[str, Any]]:
        return [m.to_chat_message() for m in self.messages]

    def to_render_inputs(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None, dict[str, Any]]:
        """The three things ``apply_chat_template`` needs, in its own vocabulary.

        Every caller that renders a row goes through here, so the training path and
        the token counter cannot disagree about what a row means.
        """
        return self.to_chat_messages(), self.tools, dict(self.apply_chat_template_kwargs or {})

    def to_parquet_row(self) -> dict[str, str | None]:
        """Serialize to the four columns. Dumps once, from native objects."""
        return {
            "messages": _dumps([m.model_dump(exclude_none=True) for m in self.messages]),
            "tools": _dumps(self.tools),
            "apply_chat_template_kwargs": _dumps(self.apply_chat_template_kwargs),
            "metadata": _dumps(self.metadata),
        }


def _dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)
