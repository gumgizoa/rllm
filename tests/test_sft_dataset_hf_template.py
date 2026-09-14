"""hf_template tokenization must render exactly what the inference server rendered:
tool schemas in the system block, dict tool-call arguments, and prefixes the
template refuses (no user turn yet) merged into the next segment."""

import json
import sys
import types

import pytest


@pytest.fixture(scope="module")
def sft_dataset_module():
    # verl is an optional heavy dependency; stub the base class so the module imports.
    if "verl" not in sys.modules:
        du = types.ModuleType("verl.utils.dataset.dataset_utils")
        mt = types.ModuleType("verl.utils.dataset.multiturn_sft_dataset")

        class DatasetPadMode:
            NO_PADDING = "no_padding"

        class MultiTurnSFTDataset:
            pass

        du.DatasetPadMode = DatasetPadMode
        mt.MultiTurnSFTDataset = MultiTurnSFTDataset
        for name, mod in {
            "verl": types.ModuleType("verl"),
            "verl.utils": types.ModuleType("verl.utils"),
            "verl.utils.dataset": types.ModuleType("verl.utils.dataset"),
            "verl.utils.dataset.dataset_utils": du,
            "verl.utils.dataset.multiturn_sft_dataset": mt,
        }.items():
            sys.modules.setdefault(name, mod)
    from rllm.trainer.verl import sft_dataset

    return sft_dataset


class FakeQwen35Tokenizer:
    """Mimics the parts of Qwen3.5's template that matter here: tools land in the
    system block, tool_calls[].function.arguments must be a mapping, and a prefix
    without a user turn is rejected."""

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False, tools=None):
        if not any(m["role"] == "user" for m in messages):
            raise ValueError("No user query found in messages.")
        out = ""
        for i, m in enumerate(messages):
            body = m.get("content") or ""
            if i == 0 and tools:
                body = "# Tools\n" + json.dumps(tools) + "\n\n" + body
            for tc in m.get("tool_calls") or []:
                args = tc["function"]["arguments"]
                if not isinstance(args, dict):
                    raise TypeError("Can only get item pairs from a mapping.")
                body += "<tool_call>" + "".join(f"<{k}>{v}</{k}>" for k, v in args.items()) + "</tool_call>"
            out += f"<|im_start|>{m['role']}\n{body}<|im_end|>\n"
        return out

    def encode(self, text, add_special_tokens=False):
        return list(text.encode("utf-8"))

    def decode(self, ids):
        return bytes(ids).decode("utf-8")


TOOLS = [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}}]
MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Fix the bug."},
    {"role": "assistant", "content": "Looking.", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": json.dumps({"command": "ls"})}}]},
    {"role": "tool", "tool_call_id": "c1", "content": '{"returncode": 0, "output": "a.py"}'},
    {"role": "assistant", "content": "Done."},
]


def _dataset(mod, tools):
    ds = object.__new__(mod.RLLMSFTDataset)
    ds.tokenizer = FakeQwen35Tokenizer()
    ds.tools = tools
    ds.tokenize_and_mask_method = "hf_template"
    return ds


def test_normalize_tool_call_arguments_parses_json_strings(sft_dataset_module):
    out = sft_dataset_module.normalize_tool_call_arguments(MESSAGES)
    assert out[2]["tool_calls"][0]["function"]["arguments"] == {"command": "ls"}
    assert isinstance(MESSAGES[2]["tool_calls"][0]["function"]["arguments"], str), "input must not be mutated"


def test_load_tools_accepts_list_path_and_bare_function(sft_dataset_module, tmp_path):
    mod = sft_dataset_module
    assert mod.load_tools(None) is None and mod.load_tools([]) is None
    p = tmp_path / "tools.json"
    p.write_text(json.dumps(TOOLS))
    assert mod.load_tools(str(p)) == TOOLS
    assert mod.load_tools([{"name": "bash", "parameters": {}}]) == [{"type": "function", "function": {"name": "bash", "parameters": {}}}]
    with pytest.raises(FileNotFoundError):
        mod.load_tools(str(tmp_path / "missing.json"))


def test_hf_template_matches_one_shot_render_with_tools(sft_dataset_module):
    mod = sft_dataset_module
    ds = _dataset(mod, TOOLS)
    tokens, mask = ds._tokenize_and_mask_hf_template(MESSAGES)
    text = ds.tokenizer.decode(tokens)
    expected = ds.tokenizer.apply_chat_template(mod.normalize_tool_call_arguments(MESSAGES), tools=TOOLS)
    assert text == expected, "segment concatenation must equal what the serving template renders"
    assert "# Tools" in text and "<command>ls</command>" in text
    assert len(tokens) == len(mask)
    # loss only on the two assistant segments
    loss_text = bytes(t for t, m in zip(tokens, mask, strict=True) if m).decode("utf-8")
    assert loss_text.startswith("<|im_start|>assistant\nLooking.") and loss_text.endswith("Done.<|im_end|>\n")
    assert "Fix the bug." not in loss_text and "returncode" not in loss_text


def test_hf_template_without_tools_still_renders(sft_dataset_module):
    ds = _dataset(sft_dataset_module, None)
    tokens, _ = ds._tokenize_and_mask_hf_template(MESSAGES)
    assert "# Tools" not in ds.tokenizer.decode(tokens)


def test_hf_template_raises_if_refused_prefix_holds_assistant(sft_dataset_module):
    ds = _dataset(sft_dataset_module, None)
    with pytest.raises(ValueError):
        ds._tokenize_and_mask_hf_template([{"role": "assistant", "content": "hi"}, {"role": "user", "content": "x"}])
