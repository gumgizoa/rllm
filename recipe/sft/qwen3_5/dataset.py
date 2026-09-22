"""SFT dataset for Qwen3.5 agentic (multi-turn, tool-calling) trajectories.

Why not :class:`~verl.utils.dataset.multiturn_sft_dataset.MultiTurnSFTDataset`?

That dataset renders every message *in isolation* and concatenates the token
ids, deriving the loss mask from the role of each rendered chunk. On Qwen3.5 it
does not even get that far: the template refuses a lone ``system`` message
("System message must be at the beginning.") once verl's fallback prepends a
dummy user turn.

Even where it runs, per-message rendering is not equivalent to rendering the
whole conversation, because the template is context sensitive:

* ``<think>...</think>`` is only emitted for assistant turns *after*
  ``ns.last_query_index`` (the last non-``<tool_response>`` user turn). Rendered
  alone, every assistant turn looks like the last one.
* ``tool`` messages are folded into a surrounding ``user`` turn, and the
  ``<|im_start|>user`` / ``<|im_end|>`` framing depends on the neighbouring
  roles.

Concatenating the pieces therefore produces token ids the model will never see
at inference time (verl detects this and asks you to set
``ignore_input_ids_mismatch=True``, which papers over the divergence).

This dataset instead renders the conversation **once**, tokenizes that exact
string, and recovers assistant spans by re-rendering prefixes and comparing
character offsets. The chat template stays the single source of truth, so a
template update cannot silently shift the loss mask: a prefix that no longer
matches raises instead.

Every assistant turn is supervised. A turn is only supervisable when the
conversation up to it plus ``add_generation_prompt=True`` is a prefix of the full
render - i.e. at inference the model would be asked to produce exactly those
tokens - and this dataset raises if that does not hold rather than quietly
dropping the turn.

That invariant is why ``data.chat_template_path`` matters: a stock Qwen3.5
template drops the reasoning of assistant turns before ``ns.last_query_index``,
which makes them unsupervisable. Point it at
``recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja``, which retains every turn's
reasoning, and the invariant holds for all of them. The override applies to every
render this dataset performs - full conversation, tokenization and prefixes -
so ids and mask cannot drift apart.

Reading rows and resolving template kwargs are *not* done here: they live in
``dataset/utils`` so that ``scripts/filter_sft_parquet.py`` measures a row's length
through the same code path that trains it.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F

# verl loads this file by path (importlib spec_from_file_location), which does not
# make it part of the swe_sft package - but swe_sft.* still resolves normally as
# long as it's installed (``pip install -e recipe/sft``), regardless of how this
# module itself was loaded.
from swe_sft.dataset.utils.render import active_template, render_text, resolve_kwargs
from swe_sft.dataset.utils.serde import parse_row
from verl.models.transformers.qwen2_vl import get_rope_index  # noqa: E402
from verl.utils.dataset.dataset_utils import DatasetPadMode  # noqa: E402
from verl.utils.dataset.multiturn_sft_dataset import MultiTurnSFTDataset  # noqa: E402

logger = logging.getLogger(__file__)
logger.setLevel(os.getenv("VERL_LOGGING_LEVEL", "WARN"))


class _LazyMessages(Sequence):
    """``dataset.messages[i]`` without holding every row's decoded messages.

    Decoding all rows up front costs ~35 GB of Python objects for a 58k-row
    trajectory dataset, and every dataloader worker inherits it. Tools that walk
    ``messages`` do so a few rows at a time, so decode on access instead.
    """

    def __init__(self, dataset: Qwen3_5_SFTDataset):
        self._dataset = dataset

    def __len__(self) -> int:
        return len(self._dataset.dataframe)

    def __getitem__(self, index: int):
        return self._dataset._decode(index)[0]


class Qwen3_5_SFTDataset(MultiTurnSFTDataset):
    """Qwen3.5 SFT dataset over the parquet contract in ``recipe/sft/swe_sft/schemas.py``.

    Reads the four JSON string columns (``messages``, ``tools``,
    ``apply_chat_template_kwargs``, ``metadata``) and renames ``reasoning`` to the
    ``reasoning_content`` key Qwen templates read. Any converter that satisfies the
    contract trains here without further changes; a different model family needs
    its own dataset (its template may name reasoning differently), not a different
    parquet.
    """

    def __init__(self, parquet_files, tokenizer, config, processor=None, max_samples: int = -1):
        # Read before super().__init__, which calls _read_files_and_process.
        self.chat_template_path = (config or {}).get("chat_template_path", None)
        self._tokenization_checked = False
        super().__init__(
            parquet_files=parquet_files,
            tokenizer=tokenizer,
            config=config,
            processor=processor,
            max_samples=max_samples,
        )

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def _read_files_and_process(self):
        # `string` carries int32 offsets, so any operation that concatenates chunks
        # (`pd.concat`, the `.take` behind `.iloc[list]`) overflows once a column holds
        # more than 2 GB - and `messages` is ~6.5 GB for a 58k-row trajectory mix.
        # `large_string` uses int64 offsets and is otherwise identical.
        table = pa.concat_tables([pq.read_table(path) for path in self.parquet_files])
        # Rebinding `table` drops the last reference to the narrow-offset chunks, so the two
        # representations are never both resident.
        table = table.cast(pa.schema([field.with_type(pa.large_string()) if field.type == pa.string() else field for field in table.schema]))
        self.dataframe = table.to_pandas(types_mapper=pd.ArrowDtype)

        total = len(self.dataframe)
        print(f"dataset len: {total}")

        if 0 < self.max_samples < total:
            if self.shuffle:
                rng = np.random.default_rng(*(self.seed,) if self.seed is not None else ())
                indices = rng.choice(total, size=self.max_samples, replace=False)
            else:
                indices = np.arange(self.max_samples)
            self.dataframe = self.dataframe.iloc[indices.tolist()]
            print(f"selected {self.max_samples} samples out of {total}")

        # Keep the columns as Arrow-backed strings and decode per row in
        # `_decode`; see _LazyMessages for why.
        self.dataframe = self.dataframe.reset_index(drop=True)
        self.messages = _LazyMessages(self)

        # A `chat_template` file overrides the model's own template for every
        # render this dataset performs - full conversation, tokenization and
        # prefixes alike - so the loss mask stays consistent with the ids.
        if self.chat_template_path:
            template = Path(self.chat_template_path).read_text()
            self.apply_chat_template_kwargs = {
                **self.apply_chat_template_kwargs,
                "chat_template": template,
            }
            # Also stamp it onto the renderer itself. verl saves this exact object into every
            # checkpoint (`processing_class.save_pretrained`, and
            # ``HFModelConfig.get_processor`` hands out the same processor/tokenizer this
            # dataset renders with), so without this the checkpoint ships the model's *stock*
            # template - which drops the reasoning of every assistant turn before
            # ``ns.last_query_index``. Serving that checkpoint would then feed the model a
            # prompt shape it was never trained on. Stamping it here keeps the promise the
            # module docstring makes: one template, used for ids, mask, and serving alike.
            renderer = self.processor if self.processor is not None else self.tokenizer
            renderer.chat_template = template
            print(f"chat_template overridden from {self.chat_template_path}")

        self._active_template = active_template(self.apply_chat_template_kwargs, self.tokenizer)

        # Fail on the first row rather than at step 1 of training: a wrong
        # `reasoning` spelling or a double-encoded column is a contract error.
        self._decode(0)

    def _cell(self, row, column: str) -> str | None:
        """One column of one row, with pandas' missing value spelled as ``None``.

        The pyarrow dtype backend returns ``pd.NA`` for a null string, which is
        neither ``None`` nor ``str``, so the contract decoder would reject it.
        """
        if column not in self.dataframe.columns:
            return None
        value = row[column]
        return None if value is None or value is pd.NA else value

    def get_sequence_lengths(self) -> list[int]:
        """Token count per row, used by ``data.balance_dp_token`` to assign rows to DP ranks.

        Read from the ``n_tokens`` that ``scripts/filter_sft_parquet.py`` already stamped into
        ``metadata``, not rendered here: rendering 57k trajectories just to place them on ranks
        would cost far more than the imbalance it removes.

        These are an upper bound on what the trainer actually forwards, because :meth:`_prepare`
        drops trailing user/tool turns that can never be supervised while ``count_tokens``
        measures the whole conversation. That only blunts the balance a little, and it cannot do
        worse: the lengths pick *which rank* gets a row, never any quantity that enters the loss
        (see ``TokenBalancedDistributedSampler``).
        """
        if "metadata" not in self.dataframe.columns:
            raise ValueError(
                "balance_dp_token needs per-row lengths, but this parquet has no `metadata` column. Re-filter it with scripts/filter_sft_parquet.py --max-tokens, which stamps `n_tokens`."
            )

        lengths: list[int] = []
        for position, value in enumerate(self.dataframe["metadata"]):
            if value is None or value is pd.NA:
                raise ValueError(f"row {position} has no metadata, so its length is unknown")
            n_tokens = json.loads(value).get("n_tokens")
            if n_tokens is None:
                raise ValueError(
                    f"row {position} has metadata without `n_tokens`. It was written by a "
                    "converter or a --max-tokens=0 filter run that did not measure length; "
                    "re-filter with --max-tokens to stamp it."
                )
            lengths.append(int(n_tokens))
        return lengths

    def _decode(self, index: int) -> tuple[list[dict[str, Any]], Any, dict[str, Any]]:
        """Decode and validate one row into render-ready objects."""
        row = self.dataframe.iloc[index]
        sample = parse_row(
            {
                "messages": self._cell(row, self.messages_key),
                "tools": self._cell(row, self.tools_key),
                "apply_chat_template_kwargs": self._cell(row, "apply_chat_template_kwargs"),
                "metadata": self._cell(row, "metadata"),
            }
        )
        return sample.to_render_inputs()

    # ------------------------------------------------------------------ #
    # Sample construction
    # ------------------------------------------------------------------ #

    def _prepare(self, index: int):
        """Everything a render needs for one row: ``(renderer, messages, tools, kwargs)``."""
        messages, tools, row_kwargs = self._decode(index)
        messages = self._build_messages({self.messages_key: messages})
        # Trailing user/tool messages can never be supervised, so they are pure
        # context cost - a trajectory that ends on a tool result is common.
        messages = messages[: self._final_assistant_index(messages) + 1]
        renderer = self.processor if self.processor is not None else self.tokenizer
        kwargs = resolve_kwargs(self.apply_chat_template_kwargs, row_kwargs, self._active_template)
        return renderer, messages, tools, kwargs

    def __getitem__(self, item):
        renderer, messages, tools, kwargs = self._prepare(item)

        rendered, input_ids, attention_mask, offset_mapping, multimodal = self._render(renderer, messages, tools, kwargs)
        loss_mask = self._loss_mask(renderer, messages, tools, kwargs, rendered, input_ids, offset_mapping)
        position_ids = self._position_ids(input_ids, attention_mask, multimodal)
        return self._pad_or_truncate(input_ids, attention_mask, position_ids, loss_mask)

    @staticmethod
    def _has_non_text_content(messages: list[dict[str, Any]]) -> bool:
        """Whether any turn carries an image or a video rather than plain text.

        The contract stores ``content`` as a string, so this is normally false: the
        parent's ``_build_messages`` only produces ``{"type": "image"}`` parts when the
        row has an image or video column. It is checked rather than assumed because a
        future converter could add one.
        """
        for message in messages:
            content = message.get("content")
            if isinstance(content, str) or content is None:
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") != "text":
                    return True
        return False

    def _render(self, renderer, messages, tools, kwargs):
        """The rendered string, its ids and offsets, and any multimodal tensors.

        Tokenizing the rendered string is not an extra step we could skip: character
        offsets are the only way to locate assistant spans, and only the tokenizer
        returns them. Those ids are therefore authoritative, and asking
        ``apply_chat_template(tokenize=True)`` for a second copy is 55% of this
        method for an answer we already have. ``verify_tokenization`` proves the two
        agree; the proof belongs in verification, not in every training step.

        A turn carrying an image is the exception: only the processor expands
        ``<|image_pad|>`` into per-patch tokens, and it is the only source of the
        grid tensors ``get_rope_index`` needs. Offsets cannot survive that expansion,
        so that path renders twice and refuses to guess if the two disagree.
        """
        rendered = render_text(renderer, messages=messages, tools=tools, kwargs=kwargs)
        offsets = self.tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
        input_ids = torch.tensor(offsets["input_ids"], dtype=torch.long)
        attention_mask = torch.ones_like(input_ids)

        if not self._has_non_text_content(messages):
            if not self._tokenization_checked:
                # Once per dataset instance, not once per sample: taking our own
                # tokenization as authoritative is only sound if the template's own
                # agrees, and that answer does not vary by row. One 310 ms render at
                # startup buys the guarantee; paying it 58k times a epoch does not.
                self._tokenization_checked = True
                theirs = renderer.apply_chat_template(
                    messages,
                    tools=tools,
                    add_generation_prompt=False,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt",
                    **kwargs,
                )["input_ids"][0].tolist()
                if theirs != offsets["input_ids"]:
                    raise ValueError(
                        f"tokenizer(rendered) gives {len(offsets['input_ids'])} ids but "
                        f"apply_chat_template gives {len(theirs)}. The character offsets therefore do "
                        "not describe the ids the template would emit, so the loss mask cannot be "
                        "trusted. This tokenizer needs the processor path."
                    )
            return rendered, input_ids, attention_mask, offsets["offset_mapping"], {}

        multimodal = dict(
            renderer.apply_chat_template(
                messages,
                tools=tools,
                add_generation_prompt=False,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                **kwargs,
            )
        )
        processor_ids = multimodal.pop("input_ids")[0]
        attention_mask = multimodal.pop("attention_mask")[0]
        if processor_ids.tolist() != offsets["input_ids"]:
            raise ValueError(
                "This sample carries an image or video, so the processor expands placeholder "
                "tokens and the character offsets no longer describe input_ids. Locating "
                "assistant spans by offset cannot work for multimodal rows."
            )
        return rendered, processor_ids, attention_mask, offsets["offset_mapping"], multimodal

    def _position_ids(self, input_ids, attention_mask, multimodal):
        if self.processor is not None and "Qwen2VLImageProcessor" in self.processor.image_processor.__class__.__name__:
            vision_position_ids = get_rope_index(
                self.processor,
                input_ids=input_ids,
                image_grid_thw=multimodal.get("image_grid_thw", None),
                video_grid_thw=multimodal.get("video_grid_thw", None),
                second_per_grid_ts=multimodal.get("second_per_grid_ts", None),
                attention_mask=attention_mask,
            )
            text_position_ids = torch.arange(input_ids.shape[0], dtype=torch.long).unsqueeze(0)
            return torch.cat((text_position_ids, vision_position_ids), dim=0)
        return torch.arange(input_ids.shape[0], dtype=torch.long)

    def _pad_or_truncate(self, input_ids, attention_mask, position_ids, loss_mask):
        sequence_length = input_ids.shape[0]

        if self.pad_mode == DatasetPadMode.RIGHT:
            if sequence_length < self.max_length:
                pad_length = self.max_length - sequence_length
                pad_token_id = self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else 0
                input_ids = torch.cat((input_ids, torch.full((pad_length,), pad_token_id, dtype=input_ids.dtype)))
                attention_mask = torch.cat((attention_mask, torch.zeros(pad_length, dtype=attention_mask.dtype)))
                loss_mask = torch.cat((loss_mask, torch.zeros(pad_length, dtype=loss_mask.dtype)))
                position_ids = F.pad(position_ids, (0, pad_length), value=0)
            elif sequence_length > self.max_length:
                if self.truncation == "left":
                    keep = slice(-self.max_length, None)
                elif self.truncation == "right":
                    keep = slice(None, self.max_length)
                elif self.truncation == "error":
                    raise ValueError(f"{sequence_length=} is larger than {self.max_length=}")
                else:
                    raise ValueError(f"Unknown truncation method {self.truncation}")
                input_ids = input_ids[keep]
                attention_mask = attention_mask[keep]
                loss_mask = loss_mask[keep]
                position_ids = position_ids[..., keep]

            return {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "position_ids": position_ids,
                "loss_mask": loss_mask,
            }

        if self.pad_mode == DatasetPadMode.NO_PADDING:
            if sequence_length > self.max_length:
                if self.truncation == "error":
                    raise ValueError(f"{sequence_length=} is larger than {self.max_length=}")
                input_ids = input_ids[: self.max_length]
                loss_mask = loss_mask[: self.max_length]
                position_ids = position_ids[..., : self.max_length]

            return {"input_ids": input_ids, "position_ids": position_ids, "loss_mask": loss_mask}

        raise ValueError(f"Unknown pad mode {self.pad_mode}")

    # ------------------------------------------------------------------ #
    # Loss mask
    # ------------------------------------------------------------------ #

    def _loss_mask(self, renderer, messages, tools, kwargs, rendered: str, input_ids, offset_mapping) -> torch.Tensor:
        """Supervise exactly the assistant turns, located by character offsets."""
        if len(offset_mapping) != input_ids.shape[0]:
            raise ValueError(f"{len(offset_mapping)} character offsets for {input_ids.shape[0]} tokens; the offsets do not describe input_ids and the mask would be misaligned.")
        token_starts = np.fromiter((s for s, _ in offset_mapping), dtype=np.int64, count=len(offset_mapping))
        token_ends = np.fromiter((e for _, e in offset_mapping), dtype=np.int64, count=len(offset_mapping))
        # Binary search below needs monotone offsets. They are, for a fast
        # tokenizer over one contiguous string - but say so rather than silently
        # producing a shifted mask if that ever stops holding.
        if np.any(np.diff(token_starts) < 0) or np.any(np.diff(token_ends) < 0):
            raise ValueError("Token offsets are not monotonically increasing; cannot map spans to tokens.")

        loss_mask = torch.zeros_like(input_ids)
        for start_char, end_char in self._assistant_target_spans(renderer=renderer, messages=messages, tools=tools, rendered=rendered, kwargs=kwargs):
            # Every token overlapping [start_char, end_char): the first with
            # end > start_char up to the first with start >= end_char.
            first = int(np.searchsorted(token_ends, start_char, side="right"))
            last = int(np.searchsorted(token_starts, end_char, side="left"))
            loss_mask[first:last] = 1
        return loss_mask

    @staticmethod
    def _final_assistant_index(messages: list[dict[str, Any]]) -> int:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "assistant":
                return index
        raise ValueError("No assistant message found in conversation.")

    def _assistant_target_spans(
        self,
        *,
        renderer,
        messages: list[dict[str, Any]],
        tools,
        rendered: str,
        kwargs: dict[str, Any],
    ) -> list[tuple[int, int]]:
        assistant_indices = [index for index, message in enumerate(messages) if message.get("role") == "assistant"]
        if not assistant_indices:
            raise ValueError("No assistant message found in conversation.")

        spans = []
        for index in assistant_indices:
            # The generation prompt is what the template forces at inference time
            # (`<|im_start|>assistant\n<think>\n`), so the target starts right
            # after it - and the fact that it *is* a prefix of the full render is
            # what proves this turn is rendered the way it will be prompted for.
            start = self._rendered_prefix_len(
                renderer=renderer,
                messages=messages[:index],
                tools=tools,
                add_generation_prompt=True,
                rendered=rendered,
                kwargs=kwargs,
            )
            # The conversation itself is append-only, so this must always match.
            end = self._rendered_prefix_len(
                renderer=renderer,
                messages=messages[: index + 1],
                tools=tools,
                add_generation_prompt=False,
                rendered=rendered,
                kwargs=kwargs,
            )
            if end > start:
                spans.append((start, end))
        return spans

    @staticmethod
    def _rendered_prefix_len(
        *,
        renderer,
        messages: list[dict[str, Any]],
        tools,
        add_generation_prompt: bool,
        rendered: str,
        kwargs: dict[str, Any],
    ) -> int:
        if not messages:
            return 0

        prefix = render_text(
            renderer,
            messages=messages,
            tools=tools,
            kwargs=kwargs,
            add_generation_prompt=add_generation_prompt,
        )
        if not rendered.startswith(prefix):
            raise ValueError(
                "A rendered message prefix is not a prefix of the full conversation, so assistant "
                "spans cannot be located. Either this chat template is not append-only, or it does "
                "not render an assistant turn the way it prompts for one - a stock Qwen3.5 template "
                "drops the reasoning of turns before last_query_index, and enable_thinking=False "
                "contradicts turns that do have reasoning. Set data.chat_template_path to "
                "recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja."
            )
        return len(prefix)
