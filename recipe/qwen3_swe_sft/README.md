# Qwen3-8B SWE SFT (verl) from OpenHands trajectories, matched to the SkyRL rollout

Supervised fine-tuning of `Qwen3-8B` on rejection-sampled OpenHands trajectories with the
built-in `rllm sft` CLI (verl FSDP backend), producing training text that is byte-identical
to what the **SkyRL-OpenHands rollout** (`SkyRL/verl/workers/agentic/codeact.py`) feeds the
model.

```
OpenHands llm_completions jsonl ──prepare_sft_jsonl.py──► SFT jsonl ({"messages": [...]})
   (native tool_calls, content parts)        │                 (plain system/user/assistant text,
                                             │                  <function=...> format)
                                             ▼
                              verify_rollout_parity.py  (turn-by-turn == rollout prompt)
                                             │
                                   rllm sft --backend verl ──► verl FSDP SFT (torchrun)
```

## What the rollout actually feeds the model

`OnlineCodeActAgent.step` (SkyRL `codeact.py`):

1. `LLM(LLMConfig(model="dummy")).format_messages_for_llm` → no native function calling,
   so `Message._string_serializer`: content parts joined with `"\n"`.
2. `convert_fncall_messages_to_non_fncall_messages(messages, get_tools(browsing=False,
   jupyter=False, llm_editor=False))` (`openhands/llm/fn_call_converter.py`):
   * system prompt += tool descriptions + `<function=...>` format rules (≈5k chars)
   * first user message = in-context example (≈5.5k chars) + task + reminder suffix
   * assistant = text + `\n\n<function=name>\n<parameter=..>..</parameter>\n</function>`
   * tool result → **user** turn, `EXECUTION RESULT of [name]:\n` + text
3. `tokenizer.apply_chat_template(msgs, add_generation_prompt=True, enable_thinking=False)`
   → Qwen3 template from `tokenizer_config.json`, generation prompt ends with
   `<|im_start|>assistant\n<think>\n\n</think>\n\n`.

The script runs steps 1–2 with the scaffold's own code (imported from `--openhands-root`
with stdlib stubs; no litellm/browsergym install needed). rLLM's `cumulative` tokenizer
(`QwenChatTemplateParser`) reproduces step 3 for the whole conversation; the only difference
is the empty think block in the generation prompt, which the model's history turns never
contain and which SkyRL's RL re-tokenization also drops.

## Teacher trajectories vs. rollout: what differed and how it is handled

| Item | Teacher jsonl | SkyRL rollout | Handling |
|---|---|---|---|
| system prompt | `system_prompt.j2` (585 chars) | same | identical |
| tool set / schemas | execute_bash, finish, str_replace_editor | same descriptions and parameters | script uses the scaffold's `get_tools()` |
| tool rendering | native API `tools=` + `tool_calls` | non-native `<function=...>` text | converted by the scaffold's converter |
| tool results | role `tool` | role `user` with `EXECUTION RESULT of [..]:` prefix | converter |
| fake user replies | `codeact_user_response` text | same | identical |
| observation format | `[Current working directory..] [Python interpreter..] [Command finished with exit code N]` | same (0.25 `to_agent_observation`) | identical |
| first user message | old SWE-Gym style 5-step instruction | `utils.get_instruction()` + `AIDLC_DOCS_DIR/instruction.md` | `--instruction skyrl [--aidlc-docs-dir ...]` rebuilds it from the `<uploaded_files>` path and `<issue_description>` body |
| observation truncation | teacher run setting (OpenHands default 30000 chars) | `max_message_chars=32768` | not reproducible after the fact; negligible |
| thinking | no reasoning in data | `enable_thinking=False` | train without think block (same as SkyRL RL) |

**Decision needed:** with `--aidlc-docs-dir` the SFT prompt tells the agent to follow the
`/aidlc` workflow, but the teacher trajectories never did. Without it, the SFT prompt is
missing a paragraph the rollout always adds. Pick based on what the RL stage will use.

## 1. Install (verl SFT backend)

Do this on the GPU node (flash-attn needs nvcc).

```bash
cd /vast-ib/MMI/home/kyuminkim/project/if/rllm && source .venv/bin/activate
export CUDA_HOME=/usr/local/cuda-12.8
uv sync --extra verl --no-install-package flash-attn
python -c "import torch; print(torch.__version__, torch.version.cuda)"   # must be 12.x
uv pip install ninja psutil
TORCH_CUDA_ARCH_LIST="9.0" MAX_JOBS=32 uv pip install flash-attn==2.8.3 --no-build-isolation
uv pip install wandb && export WANDB_MODE=offline
python -c "import verl, flash_attn; print(verl.__version__, flash_attn.__version__)"
```

## 2. Convert + verify

`--instruction keep` (default) leaves the first user message exactly as logged; the converter
only wraps it with the in-context example, as the rollout does. Use `--instruction skyrl`
(optionally with `--aidlc-docs-dir`) only when the teacher run used a different task
instruction than the rollout will.

```bash
python recipe/qwen3_swe_sft/prepare_sft_jsonl.py trajectories/*.jsonl \
    -o data/sft/train.jsonl --val-out data/sft/val.jsonl --val-ratio 0.05 \
    --instruction keep \
    --tokenizer /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B --max-tokens 65536

python recipe/qwen3_swe_sft/verify_rollout_parity.py data/sft/train.jsonl \
    --tokenizer /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B
```

`verify_rollout_parity.py` renders every assistant turn's rollout prompt with the Qwen3
template and asserts it equals the rLLM training text up to that turn plus the empty think
block. On the 3-sample pilot file all 275 turns matched.

Lengths after conversion (Qwen3 tokenizer, pilot file): 47.7k–66.5k tokens per trajectory.
The teacher-side `n_tokens` field is from another tokenizer and format; ignore it.

## 3. Train (sequence parallel, fused head, HF export)

`rllm sft` exposes no sequence-parallel / fused-kernel / offload knobs, so use the launcher,
which builds an `SFTSpec(overrides=...)` for verl 0.8.0's `sft_trainer_engine` and runs
`AgentSFTTrainer(..., backend="verl")` (torchrun is spawned for you):

```bash
python recipe/qwen3_swe_sft/train_sft.py \
    --train-file data/sft/train.jsonl --val-file data/sft/val.jsonl \
    --model /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B \
    --gpus 8 --sp 2 --max-length 65536 \
    --batch-size 16 --epochs 2 --lr 1e-5 --lr-schedule cosine \
    --experiment qwen3-8b-swe-sft-v1 --output /data/MMI/kyuminkim/rllm-work/sft_runs/v1
# --dry-run prints dp, micro-batch budget, steps and the override dict without importing rllm/verl
```

What the launcher sets (verl 0.8.0 keys):

| knob | key | value / reason |
|---|---|---|
| sequence parallel | `engine.ulysses_sequence_parallel_size` | `--sp`; needs `use_remove_padding` (rLLM sets it). dp = gpus/sp |
| micro-batch budget | `data.max_token_len_per_gpu` | default `ceil(max_length/sp)`, so one longest sample per SP group. verl asserts `budget*sp >= longest sample` |
| fused head | `model.use_fused_kernels=True`, `fused_kernel_options.impl_backend=torch` | log-probs from hidden states in chunks; no `[tokens x 151936]` logits. Without it 64k OOMs (≈100 GB of logits+grad) |
| sharding | `engine.strategy=fsdp` (FSDP1) | FSDP2 + untied lm_head + fused kernels + grad accumulation hits verl #7520 |
| offload | `engine.param_offload`, `engine.optimizer_offload` | off by default; `--optimizer-offload` halves sharded state (host has ~2 TB RAM) |
| HF export | `checkpoint.save_contents += hf_model` | writes `<ckpt>/global_step_N/huggingface/` usable as SkyRL `SFT_MODEL_PATH` |
| logger | `trainer.logger` | `console` by default (`--logger wandb` to add wandb) |

### Memory and batch size

Global `--batch-size` (samples per optimizer step) is **not** memory bound: verl packs samples
into micro-batches of `max_token_len_per_gpu*sp` tokens and accumulates gradients. Constraints
are only divisibility (`batch_size % dp == 0`) and dataset size (`drop_last`; rows >= batch).
Memory decides the micro-batch token budget, i.e. how many samples share one forward/backward.

Estimate (`estimate_memory.py`, 0.55 MB/token activations: Qwen3.5-4B measured 0.30 GB/1K tok
under the same settings, scaled by hidden 1.6x and layers 36/32; 10 % fragmentation reserve):

| node | sp | dp | sharded states | act. @ one 64k sample | total | free | longest samples per micro-batch |
|---|---|---|---|---|---|---|---|
| 8x H200 141 GB | 1 | 8 | 15.3 | 35.2 | 73 | 68 | 2.9 |
| 8x H200 141 GB | 2 | 4 | 15.3 | 17.6 | 56 | 86 | 5.9 |
| 8x H200 141 GB | 4 | 2 | 15.3 | 8.8 | 47 | 94 | 11.7 |
| 4x H100 96 GB | 1 | 4 | 30.5 | 35.2 | 84 | 12 | 1.3 |
| 4x H100 96 GB | 2 | 2 | 30.5 | 17.6 | 66 | 30 | 2.7 |

(GB per GPU.) At a pessimistic 0.75 MB/token the 8x H200 sp=1 case still has 55 GB free.

Recommendation for 8x H200: `--sp 2`, keep the default budget (one 64k sample per SP group,
4 samples in flight per micro-batch across the node), `--batch-size 16` → 16 samples ≈ 1M
tokens per step. With N training rows that is `N/16` steps per epoch; raise `--batch-size`
to 32 only if N is in the thousands. On 4x H100 use `--sp 2` or `--sp 4`; sp=1 is too tight.

Calibrate the activation constant on the real node before a long run:

```bash
CUDA_VISIBLE_DEVICES=0 python recipe/qwen3_swe_sft/mem_scaling.py 16384 32768 65536
python recipe/qwen3_swe_sft/estimate_memory.py --gpus 8 --gpu-mem-gb 141 --act-mb-per-token <GB/1K tok>
```

Notes:

* `cumulative` = loss on every assistant turn (`<|im_start|>assistant\n{content}<|im_end|>\n`).
  Do not use `hf_template`: it slices prefix renderings and the Qwen3 template renders the
  last assistant turn differently from the same turn mid-conversation.
* `Qwen3-8B` ships `max_position_embeddings: 40960`; SkyRL RL runs used
  `max_prompt_length=31232 + max_response_length=1536`. Trajectories longer than that can
  never be reproduced at rollout. Either filter with `--max-tokens 32768`, or enable YaRN in a
  copy of the model dir (`rope_scaling: {rope_type: yarn, factor: 2.0,
  original_max_position_embeddings: 32768}`) and raise both the SFT `--max-length` and the RL
  prompt length.
