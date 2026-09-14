import copy
import json
import logging
from pathlib import Path

import torch
from verl.utils.dataset.dataset_utils import DatasetPadMode
from verl.utils.dataset.multiturn_sft_dataset import MultiTurnSFTDataset

from rllm.parser import ChatTemplateParser

logger = logging.getLogger(__name__)


def load_tools(tools) -> list[dict] | None:
    """Resolve ``data.rllm.tools`` into a list of OpenAI-style tool schemas.

    Accepts ``None``, an already-parsed list of dicts, or a path to a JSON file
    holding such a list (``[{"type": "function", "function": {...}}, ...]``).
    """
    if tools is None:
        return None
    if isinstance(tools, str):
        path = Path(tools)
        if not path.is_file():
            raise FileNotFoundError(f"data.rllm.tools points to a missing file: {tools}")
        tools = json.loads(path.read_text())
    tools = list(tools)
    if not tools:
        return None
    out = []
    for t in tools:
        t = dict(t)
        # Accept bare function schemas ({"name", "parameters", ...}) as well.
        if "type" not in t and "function" not in t and "name" in t:
            t = {"type": "function", "function": t}
        out.append(t)
    return out


def normalize_tool_call_arguments(messages: list[dict]) -> list[dict]:
    """Return a copy of ``messages`` whose ``tool_calls[].function.arguments`` are dicts.

    OpenAI-compatible traces (and ``rllm dataset from-eval`` rows) carry
    ``arguments`` as a JSON string; HF chat templates such as Qwen3.5's iterate
    over it as a mapping and raise ``Can only get item pairs from a mapping``.
    Strings that are not valid JSON are left untouched.
    """
    out = copy.deepcopy(messages)
    for m in out:
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") if isinstance(tc, dict) else None
            target = fn if isinstance(fn, dict) else tc
            args = target.get("arguments") if isinstance(target, dict) else None
            if isinstance(args, str):
                try:
                    target["arguments"] = json.loads(args)
                except json.JSONDecodeError:
                    pass
    return out


def _has_tool_calls(messages: list[dict]) -> bool:
    return any(m.get("tool_calls") for m in messages if isinstance(m, dict))


class RLLMSFTDataset(MultiTurnSFTDataset):
    def __init__(self, parquet_files: str | list[str], tokenizer, config=None, processor=None, max_samples=-1):
        super().__init__(parquet_files, tokenizer, config, processor=processor, max_samples=max_samples)

        self.tokenize_and_mask_method = config.rllm.tokenize_and_mask_method
        logger.info(f"Using {self.tokenize_and_mask_method} tokenization and masking method")

        # Tool schemas the policy saw at inference (the ``tools=`` argument of the
        # chat-completions request). ``hf_template`` passes them to
        # ``apply_chat_template`` so the rendered system block matches what the
        # inference server rendered; the string-assembling parsers ignore them.
        self.tools = load_tools(config.rllm.get("tools", None))
        if self.tools:
            logger.info(f"Rendering {len(self.tools)} tool schema(s) into the chat template")
            if self.tokenize_and_mask_method != "hf_template":
                logger.warning("data.rllm.tools is only honoured by tokenize_and_mask_method='hf_template'; the '%s' parser will not render the tool schemas", self.tokenize_and_mask_method)
        self._warned_parser_tool_calls = False

        self.parser = ChatTemplateParser.get_parser(tokenizer)

    def _tokenize_and_mask(self, messages):
        if self.tokenize_and_mask_method == "cumulative":
            return self._tokenize_and_mask_cumulative(messages)
        elif self.tokenize_and_mask_method == "stepwise":
            return self._tokenize_and_mask_stepwise(messages)
        elif self.tokenize_and_mask_method == "hf_template":
            return self._tokenize_and_mask_hf_template(messages)
        else:
            raise ValueError(f"Unknown tokenize_and_mask_method {self.tokenize_and_mask_method}")

    def _warn_parser_tool_calls(self, messages):
        if self._warned_parser_tool_calls or not _has_tool_calls(messages):
            return
        self._warned_parser_tool_calls = True
        logger.warning(
            "Messages contain tool_calls but tokenize_and_mask_method='%s' renders them with %s's hardcoded "
            "format, which may differ from the tokenizer's chat template (e.g. Qwen3.5 uses <function=...> XML, "
            "not the Qwen2.5/3 JSON form). Use --tokenize-method hf_template (with --tools) to train on exactly "
            "what the inference server renders.",
            self.tokenize_and_mask_method,
            type(self.parser).__name__,
        )

    def _tokenize_and_mask_cumulative(self, messages):
        self._warn_parser_tool_calls(messages)
        tokens = []
        loss_mask = []

        for i in range(len(messages)):
            parsed_msg = self.parser.parse([messages[i]], is_first_msg=(i == 0), add_generation_prompt=False)
            ids = self.tokenizer.encode(parsed_msg, add_special_tokens=False)
            if messages[i]["role"] == "assistant":
                loss_mask.extend([1] * len(ids))
            else:
                loss_mask.extend([0] * len(ids))
            tokens.extend(ids)

        return tokens, loss_mask

    def _apply_chat_template(self, messages):
        kwargs = {"tokenize": False, "add_generation_prompt": False}
        if self.tools:
            kwargs["tools"] = self.tools
        return self.tokenizer.apply_chat_template(messages, **kwargs)

    def _tokenize_and_mask_hf_template(self, messages):
        """Use HF tokenizer.apply_chat_template for native tool call rendering.

        Renders incrementally: messages[0:i] vs messages[0:i+1] to isolate each
        message's tokens, then applies loss mask only on assistant tokens.

        ``tool_calls[].function.arguments`` are coerced from JSON strings to
        dicts first (Qwen3.5's template requires a mapping), and the tool
        schemas from ``data.rllm.tools`` are passed as ``tools=`` so the
        rendered system prompt carries the same tool block the inference
        server produced.
        """
        messages = normalize_tool_call_arguments(messages)
        full_text = self._apply_chat_template(messages)

        # Build prefix lengths to find boundaries. Some templates refuse to
        # render a prefix with no user turn yet (Qwen3.5: "No user query found
        # in messages"); such a prefix is merged into the next renderable
        # segment, which is safe because everything before the first user turn
        # is loss-masked anyway (asserted below).
        prefix_lengths: list[int | None] = [0]  # char offset where each message starts
        for i in range(len(messages)):
            try:
                prefix_text = self._apply_chat_template(messages[: i + 1])
            except Exception as exc:  # jinja2 TemplateError from raise_exception
                if messages[i]["role"] == "assistant" or i == len(messages) - 1:
                    raise
                logger.debug("chat template refused prefix of %d message(s) (%s); merging into next segment", i + 1, exc)
                prefix_lengths.append(None)
                continue
            prefix_lengths.append(len(prefix_text))
        for i in range(len(prefix_lengths) - 1, 0, -1):  # forward-fill from the right
            if prefix_lengths[i] is None:
                prefix_lengths[i] = prefix_lengths[i + 1]

        # Tokenize each segment and assign loss mask
        tokens = []
        loss_mask = []
        for i in range(len(messages)):
            segment = full_text[prefix_lengths[i] : prefix_lengths[i + 1]]
            seg_ids = self.tokenizer.encode(segment, add_special_tokens=False)

            if messages[i]["role"] == "assistant":
                loss_mask.extend([1] * len(seg_ids))
            else:
                loss_mask.extend([0] * len(seg_ids))
            tokens.extend(seg_ids)

        return tokens, loss_mask

    def _tokenize_and_mask_stepwise(self, messages):
        self._warn_parser_tool_calls(messages)
        tokens = []
        loss_mask = []

        # Find the index of the last assistant message
        last_assistant_idx = -1
        for i in range(len(messages)):
            if messages[i]["role"] == "assistant":
                last_assistant_idx = i
        assert last_assistant_idx != -1, "No assistant message found in chat_completions"

        for i in range(len(messages)):
            parsed_msg = self.parser.parse([messages[i]], is_first_msg=(i == 0), add_generation_prompt=False)
            ids = self.tokenizer.encode(parsed_msg, add_special_tokens=False)
            if i == last_assistant_idx and messages[i]["role"] == "assistant":
                loss_mask.extend([1] * len(ids))
            else:
                loss_mask.extend([0] * len(ids))
            tokens.extend(ids)

        return tokens, loss_mask

    def __getitem__(self, item):
        messages = self.messages[item]

        tokens, loss_mask = self._tokenize_and_mask(messages)

        input_ids = torch.tensor(tokens, dtype=torch.long)
        loss_mask = torch.tensor(loss_mask, dtype=torch.long)

        # verl 0.8.0 keys the loss path off ``pad_mode`` (injected into the batch
        # by SFTTrainer). ``no_padding`` (the SFT default) expects each sample as
        # an *unpadded* 1-D ``{input_ids, position_ids, loss_mask}`` that the
        # SFTTensorCollator nests + flattens; ``sft_loss`` reads ``loss_mask``
        # directly. ``right`` pads to ``max_length`` and the loss reads
        # ``response_mask``. We mirror ``MultiTurnSFTDataset.__getitem__`` for
        # both so the loss mask always lands on the assistant tokens this class
        # computed.
        if self.pad_mode == DatasetPadMode.NO_PADDING:
            sequence_length = input_ids.shape[0]
            if sequence_length > self.max_length:
                if self.truncation == "error":
                    raise ValueError(f"{sequence_length=} is larger than {self.max_length=}")
                # left/right truncation both keep the head here, matching verl's
                # no_padding branch (it only right-truncates).
                input_ids = input_ids[: self.max_length]
                loss_mask = loss_mask[: self.max_length]
            position_ids = torch.arange(input_ids.shape[0], dtype=torch.long)
            return {
                "input_ids": input_ids,
                "position_ids": position_ids,
                "loss_mask": loss_mask,
            }

        attention_mask = torch.tensor([1] * len(tokens), dtype=torch.long)

        # Handle sequence length (pad_mode == "right")
        sequence_length = input_ids.shape[0]
        if sequence_length < self.max_length:
            # Pad sequences
            pad_token_id = self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else 0
            padded_input_ids = torch.full((self.max_length - sequence_length,), pad_token_id, dtype=input_ids.dtype)
            padded_attention_mask = torch.zeros((self.max_length - sequence_length,), dtype=attention_mask.dtype)
            padded_loss_mask = torch.zeros((self.max_length - sequence_length,), dtype=loss_mask.dtype)

            input_ids = torch.cat((input_ids, padded_input_ids))
            attention_mask = torch.cat((attention_mask, padded_attention_mask))
            loss_mask = torch.cat((loss_mask, padded_loss_mask))

        elif sequence_length > self.max_length:
            if self.truncation == "left":
                input_ids = input_ids[-self.max_length :]
                attention_mask = attention_mask[-self.max_length :]
                loss_mask = loss_mask[-self.max_length :]
            elif self.truncation == "right":
                input_ids = input_ids[: self.max_length]
                attention_mask = attention_mask[: self.max_length]
                loss_mask = loss_mask[: self.max_length]
            elif self.truncation == "error":
                raise ValueError(f"{sequence_length=} is larger than {self.max_length=}")
            else:
                raise ValueError(f"Unknown truncation method {self.truncation}")

        # Create position IDs
        position_ids = torch.arange(len(input_ids), dtype=torch.long)
        # Zero out position IDs for padding
        position_ids = position_ids * attention_mask

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "position_ids": position_ids,
            "loss_mask": loss_mask,
            # verl 0.8.0's right/left_right sft_loss reads ``response_mask``;
            # ours is the assistant-token loss mask.
            "response_mask": loss_mask,
        }
