"""Chat-template rendering, token counting and loss-mask checks.

Every render in this project goes through here. That is the point: the filter
measures a row's length with the same kwargs resolution the training dataset uses,
so a length that passed ``--max-tokens`` cannot blow past ``data.max_length`` at
step 1. When the two had separate implementations they agreed only by accident.

Nothing here knows about a specific model. Callers pass the tokenizer or processor
and, if they want to override it, the chat template.
"""

from __future__ import annotations

import re
from typing import Any

from swe_sft.schemas import SFTSample


def template_reads(template: str, variable: str) -> bool:
    """Whether a Jinja template actually reads ``variable``.

    Comments are stripped first: a template that *documents* a variable it
    deliberately ignores would otherwise look like it uses one, and transformers
    logs a warning for every kwarg the template never consumes.
    """
    return variable in re.sub(r"\{#.*?#\}", "", template, flags=re.DOTALL)


def active_template(kwargs: dict[str, Any], renderer: Any) -> str:
    """The template that will actually be used: an explicit override, else the model's."""
    return kwargs.get("chat_template") or getattr(renderer, "chat_template", "") or ""


def resolve_kwargs(defaults: dict[str, Any], row_kwargs: dict[str, Any], template: str) -> dict[str, Any]:
    """Merge template kwargs and drop the ones this template never reads.

    Precedence: config defaults < the row's own kwargs. The row wins because it
    records how the sample was actually produced, and the config is a fallback for
    rows that say nothing.
    """
    merged = {**defaults, **row_kwargs}
    return {key: value for key, value in merged.items() if key == "chat_template" or template_reads(template, key)}


def render_text(
    renderer: Any,
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    kwargs: dict[str, Any],
    add_generation_prompt: bool = False,
) -> str:
    """Render a conversation to the exact string that will be tokenized."""
    return renderer.apply_chat_template(
        messages,
        tools=tools,
        add_generation_prompt=add_generation_prompt,
        tokenize=False,
        **kwargs,
    )


def count_tokens(tokenizer: Any, sample: SFTSample, chat_template: str | None = None) -> int:
    """Length of one sample as the trainer will see it. ``-1`` if the template rejects it.

    A rejected row is a real outcome, not an error: a stock template refuses
    conversations whose earlier reasoning it would have to drop. The caller decides
    whether that means "drop this row" or "fix the template".
    """
    messages, tools, row_kwargs = sample.to_render_inputs()
    defaults = {"chat_template": chat_template} if chat_template else {}
    kwargs = resolve_kwargs(defaults, row_kwargs, active_template(defaults, tokenizer))
    try:
        rendered = render_text(tokenizer, messages=messages, tools=tools, kwargs=kwargs)
    except Exception:
        return -1
    return len(tokenizer(rendered, add_special_tokens=False)["input_ids"])


def mask_spans(loss_mask: list[int]) -> list[tuple[int, int]]:
    """Maximal ``[start, end)`` runs of ``loss_mask == 1``."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(loss_mask):
        if value and start is None:
            start = index
        elif not value and start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(loss_mask)))
    return spans
