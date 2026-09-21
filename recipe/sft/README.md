# Agentic SFT on verl, from `rllm eval` trajectories

Train a model on the trajectories an eval run already produced, without going
through `rllm sft`. A shared parquet contract (`swe_sft/schemas.py`) is the only
thing a data source and a model family have to agree on: converting a new source
means writing one converter that emits the contract, and supporting a new model
family means writing one dataset class that renders it. Neither side needs to know
the other exists.

```
rllm eval                                  full trajectories -> ~/.rllm/eval_results/<run_id>/
  |
  |  converters/from_rllm_gateway.py        eval_results -> contract parquet   (shape + eval-level selection)
  v
  |  scripts/filter_sft_parquet.py          contract -> a named train/valid mix (training-level selection)
  v
  |  qwen3_5/run_megatron_sft.sh            verl SFT, Megatron
  v
checkpoints/
```

```
swe_sft/schemas.py                      THE FORMAT CONTRACT (pydantic + pyarrow schema) - model/data agnostic
swe_sft/dataset/utils/serde.py          parquet row <-> SFTSample (one decode path)      - model/data agnostic
swe_sft/dataset/utils/parquet.py        input shards, streaming read/write, readback     - model/data agnostic
swe_sft/dataset/utils/render.py         chat-template rendering, token counts, masks     - model/data agnostic
converters/from_rllm_gateway.py         gateway-traced eval runs -> contract             - one converter per episode shape
scripts/filter_sft_parquet.py           raw -> a named train/valid mix (selection)       - model/data agnostic
scripts/inspect_loss_mask.py            see what a dataset actually supervises           - model/data agnostic
qwen3_5/dataset.py                      Qwen3_5_SFTDataset: renders the contract         - one dataset class per model family
qwen3_5/chat_templates/qwen3_5_train.jinja  training-purpose chat template (see 3)       - one template per model family, if needed
qwen3_5/run_megatron_sft.sh             launcher for the Qwen3.5 + Megatron example
tests/                                  the conversion rules, no GPU required
```

Install the package once (editable, so edits under `swe_sft/` take effect immediately):

```bash
pip install -e recipe/sft
```

This makes `swe_sft` importable from anywhere. Only the contract and its utilities
are installed; `qwen3_5/dataset.py` is loaded by file path (verl's
`data.custom_cls`), which is what keeps one model family's quirks out of the
shared package.

Every render in the project goes through `swe_sft/dataset/utils/render.py`. That is
why `--max-tokens` in the filter measures exactly what the trainer will see.

## Why not `rllm sft`

`rllm sft` exists and is the right tool for a plain conversation dataset. For
tool-calling agent trajectories it is not, and the failures are quiet:

- `rllm sft --backend verl` writes only the `messages` column to the parquet it
  hands verl (`rllm/trainer/sft/verl_backend.py`, `_write_messages_parquet`), so
  per-row `tools` and `apply_chat_template_kwargs` cannot reach the trainer at all.
- Its default `--tokenize-method cumulative` renders tool calls with
  `QwenChatTemplateParser`'s hardcoded Qwen2.5/3 JSON form
  (`<tool_call>{...}</tool_call>`). Qwen3.5's template emits `<function=...>` XML,
  so SFT teaches a syntax the serving-side parser rejects - without raising.
- `--tokenize-method hf_template` uses the real template but has no way to pass a
  chat template override, and raises `Can only get item pairs from a mapping` on
  rows whose `tool_calls[].function.arguments` is a JSON string.
- Its default `--max-length 2048` with `truncation: right` silently truncates SWE
  trajectories, which run 50k-130k tokens.

None of that is fixed here; this recipe routes around it. If you are training a
tool-calling agent, use this pipeline. If you change `rllm sft` instead, these are
the four things to fix.

## 0. The format contract

Four JSON string columns, defined and enforced in `swe_sft/schemas.py`:

| column | required | holds |
| --- | --- | --- |
| `messages` | yes | array of message objects |
| `tools` | no (`null`) | array of OpenAI tool schemas |
| `apply_chat_template_kwargs` | no (`null`) | per-row kwargs, e.g. `{"enable_thinking": false}` |
| `metadata` | no (`null`) | dataset-specific provenance, never read during training |

```jsonc
{"role": "system",    "content": str}
{"role": "user",      "content": str}
{"role": "assistant", "content": str,        // "" allowed (tool-call-only turn)
                      "reasoning": str,      // OMIT for a non-thinking turn
                      "tool_calls": [{"type": "function",
                                      "function": {"name": str,
                                                   "arguments": {…}}}]}   // mapping!
{"role": "tool",      "content": str, "tool_call_id": str}
```

Every rule below exists because breaking it fails **silently** - the render is
wrong but nothing raises. `SFTSample` rejects all of them.

- **`arguments` is a mapping, never a JSON string.** Templates iterate it with
  Jinja `|items`; a string raises `TypeError: Can only get item pairs from a mapping`.
- **Parse, then dump once.** Upstream fields are often already JSON strings;
  `json.dumps` on one of those double-encodes, and the reader gets a `str` where
  it expected a list (`ValueError: Tools should either be a JSON schema, ...`).
- **Only fixed positions hold JSON text**: the four columns and `arguments`.
  `content` is *never* parsed - tool output is frequently valid JSON, and parsing
  it turns a string into a dict the template rejects. Never decide what to parse
  by sniffing whether a string looks like JSON.
- **Reasoning goes in `reasoning`** (vLLM's field name). Templates read
  `reasoning_content`; the dataset does that rename. Writing `reasoning_content`
  into the parquet would work for Qwen and silently drop reasoning elsewhere.
- **A non-thinking turn omits `reasoning`** (not `""`) *and* the row sets
  `enable_thinking: false`. Without the flag the generation prompt stops at
  `<think>\n`, so the forced `</think>` lands inside the supervised target.
- **`content` carries no `<think>` / `</think>` and no control tokens.**
- **The last message is `assistant`**, and at least one `user` message exists.
- **Absent means a real `null`**, not `""` and not `"null"`.

Kwargs precedence, lowest to highest:

```
data.apply_chat_template_kwargs   (config default)
  → the row's apply_chat_template_kwargs   (the row records how it was produced)
    → data.chat_template_path              (the template itself)
```

Validation is not a separate step. The converter validates every sample as it
builds it, reads the finished parquet back and validates it again (`--no-check`
skips the readback); the filter re-validates every row it touches; the dataset
validates each row as it decodes it.

## 1. Build the parquet files

Two stages, deliberately separate. Conversion decides *shape* and runs once per
eval; filtering decides *selection* and runs as often as you want a different mix.

```bash
# 1) eval trajectories -> contract, one row per surviving attempt
python recipe/sft/converters/from_rllm_gateway.py <run_id> [<run_id> ...] \
    --filter "solved" --select correct \
    --output-dir recipe/sft/data/swe/raw

# 2) contract -> a named training mix, split into train/valid
python recipe/sft/scripts/filter_sft_parquet.py recipe/sft/data/swe/raw/data.parquet \
    --require-reasoning --max-tokens 131072 \
    --model Qwen/Qwen3.5-4B \
    --chat-template-path recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja
# -> recipe/sft/data/swe/reasoning__max131072/{train,valid}.parquet
```

`RUNS` are run ids under `~/.rllm/eval_results` or paths to run dirs; pooling
several runs is just passing several.

### What the converter does

It reads `results.json` for the per-attempt rewards and `episodes/*.json` for the
conversations. Selection (which task, which attempt) reuses
`rllm.eval.curation`'s filter DSL and pass@k aggregation, so `--filter` /
`--select` / `--metric` mean exactly what they mean in `rllm dataset from-eval`.

| flag | effect |
| --- | --- |
| `--filter EXPR` | Task-level filter over aggregates: `solved` (default), `0 < avg < 1`, `pass@4 >= 0.5`. |
| `--select correct\|best\|all` | Which attempts to keep per surviving task (default: `correct`). |
| `--max-per-task N` | Cap attempts kept per task. |
| `--metric` / `--min-reward` | What `avg`/`best` aggregate, and the per-attempt passing threshold. |
| `--trajectory NAME` | Which trajectory to extract from a multi-agent flow (default: the first). |
| `--tools FILE` | OpenAI tool schemas, written to every row's `tools` column. |

It does **not** go through `rllm dataset from-eval`. That command's
`_clean_message` keeps only `role`/`content`/`tool_calls`/`tool_call_id`/`name`,
so `reasoning` is dropped - and it is the one field that cannot be reconstructed
afterwards. Without it every row has to be `enable_thinking: false`, i.e. the
model is trained to answer without thinking.

`metadata` gets `instance_id` (the task id), `run_id`, `attempt`, `eval_idx`,
`reward`, `score` and `is_correct`, which is what makes `--group-key` and
`--metadata-eq` work downstream.

### Two episode shapes, one converter each

An eval run's `chat_completions` is written by one of two components, and they do
not produce the same thing. That is why the converters are named after what
recorded the episode rather than after `rllm eval`:

| Invocation | Recorded by | Shape | Converter |
| --- | --- | --- | --- |
| `rllm eval <ds> --agent <native>` | gateway traces -> `engine/trace_converter.py` | OpenAI wire format | `from_rllm_gateway.py` |
| `rllm eval <ds> --agent harbor:<scaffold>` | `integrations/harbor/atif_trajectory_bridge.py` | flattened into strings | `from_harbor_atif.py` |

- **Gateway** (`engine/trace_converter.py:63`): `chat_completions` is
  `trace.messages + trace.response_message`, i.e. exactly what the agent put on
  the wire. Structured `tool_calls`, reasoning in its own key, tool results as
  `role: "tool"`. Each call resends the whole conversation, so the last step with
  `chat_completions` holds all of it.
- **Harbor / ATIF** (`atif_trajectory_bridge.py:124`): every step is flattened
  into a string - reasoning as `<think>...</think>`, each tool call as a
  `<tool_call>{json}</tool_call>` block *inside* `content`, the observation as a
  `user` turn. Those rows are contract-*valid* but wrong: the model would be
  trained to emit the literal characters `<tool_call>`. `from_rllm_gateway.py`
  **refuses** them (they show up under `skipped`), because nothing downstream can
  tell the difference.

A Harbor converter should **not** parse that flattened text. `_build_step`
(`atif_trajectory_bridge.py:255`) keeps the structured originals on the same
`Step`, and `Step.to_dict` writes all of them to disk:

| `Step` field | holds |
| --- | --- |
| `action` | `[{"name", "arguments"}]` - tool calls, arguments already a dict |
| `thought` | `reasoning_content`, with no `<think>` tags |
| `model_response` | the message text, no `<think>`, no `<tool_call>` |
| `observation` | the tool output |

So `from_harbor_atif.py` is a step-to-message mapping, not a parser. The only
thing ATIF does not carry through is `tool_call_id`, which the contract treats as
optional and Qwen templates do not render.

### Agents that do not call tools

Upstream `mini-swe-agent` asks for a markdown ` ```bash ` block and feeds the
output back as a `user` turn. Its episodes have no `tool_calls`, no `role: "tool"`
and no schemas, so `--tools` is not applicable and rows carry `tools: null`. That
is not a defect to repair: it is what the policy saw, so it is what it should be
trained on. The converter only warns about a missing `--tools` when rows actually
contain tool calls.

### Filters

| flag | effect |
| --- | --- |
| `--metadata-eq KEY=VALUE[,VALUE]` | Keep rows whose `metadata.KEY` matches. Repeatable; conditions AND together. |
| `--require-reasoning` | Drop rows where any assistant turn has no `reasoning`. Keeping them trains the model to emit an *empty* reasoning block. |
| `--max-tokens N` | Drop rows longer than N once rendered. Must match `data.max_length` while `data.truncation=error`, or training dies on the first long sample. This renders and tokenizes every row, so it is the slow part. Requires `--model` and, unless the model's own template is what you want, `--chat-template-path`. |
| `--val-fraction` / `--group-key` | Split hashed on `metadata.instance_id` by default, so all attempts of one task land on the same side. A row-level split leaks near-duplicate trajectories. |

The output directory name states which filters produced it, and `filter.json`
records the exact arguments, the git commit (and whether the tree was dirty), and
the resulting counts, so two mixes can never be confused.

Rows stay in source order. The trainer's `DistributedSampler` shuffles, so this is
harmless - but with `data.train_max_samples` also set `data.shuffle=True` or you
get a single-source prefix.

## 2. Why a custom dataset (the Qwen3.5 example)

Every model family gets its own dataset class, because chat templates differ in how
they render reasoning, tool calls, and multi-turn context - the same reason a new
data source gets its own converter.

verl's `MultiTurnSFTDataset` renders each message *in isolation* and concatenates
the token ids. That does not work for Qwen3.5:

* It crashes outright - the template rejects a lone `system` or `assistant`
  message (`System message must be at the beginning.`).
* Even where it runs, the result diverges from the real conversation, because
  the template is context sensitive: `<think>` blocks are only emitted for
  assistant turns after `ns.last_query_index`, and `tool` messages are folded
  into a surrounding `user` turn whose framing depends on neighbouring roles.
  verl detects the divergence and asks for `ignore_input_ids_mismatch=True`,
  which papers over it.

`Qwen3_5_SFTDataset` renders the conversation **once**, tokenizes that exact
string, and recovers assistant spans by re-rendering prefixes and comparing
character offsets. The chat template stays the single source of truth, so a
template change cannot silently shift the mask - a prefix that stops matching
raises instead.

Cost: `2 + 2N` template evaluations for N assistant turns. A 91-turn / 51k-token
trajectory is about 0.6 s. With `data.num_workers: 8` that stays well ahead of the
GPU step.

The full render is tokenized **once**, by the tokenizer, because character offsets
are the only way to locate spans and only the tokenizer returns them. Taking our
own tokenization as authoritative is only sound if the template's own agrees, so
the dataset checks that **once per instance** and raises if they differ.

None of this is Qwen3.5-specific in shape: render the full conversation once,
recover each assistant turn's span by comparing prefix renders, and raise instead
of guessing when a turn is not actually reachable via `add_generation_prompt=True`.

## 3. The training chat template

Only needed if a model family's stock template drops information (here, reasoning
on turns before the last user turn) that section 2's invariant depends on. For
Qwen3.5, `qwen3_5/chat_templates/qwen3_5_train.jinja` is what the dataset renders
with:

```bash
+data.chat_template_path=recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja
```

It is a standalone template, not a mutation of the model's own, and it differs
from upstream in **exactly one place** - the change the Qwen maintainers recommend
for retaining prior reasoning:

```diff
-        {%- if loop.index0 > ns.last_query_index %}
-            {{- '<|im_start|>' + message.role + '\n<think>\n' + reasoning_content + '\n</think>\n\n' + content }}
-        {%- else %}
-            {{- '<|im_start|>' + message.role + '\n' + content }}
-        {%- endif %}
+        {{- '<|im_start|>' + message.role + '\n<think>\n' + reasoning_content + '\n</think>\n\n' + content }}
```

For agent-shaped conversations the two templates are **byte-identical**: tool
results carry role `"tool"`, so upstream's `last_query_index` is the single task
message and it already renders every assistant turn with reasoning. The templates
diverge only once a second real `user` turn exists.

> **Serving must use this same template** (vLLM: `--chat-template`), or the extra
> reasoning in the context becomes a train/serve mismatch.

### There is no loss-mask strategy

Every assistant turn is supervised. A turn is supervisable only when the
conversation up to it plus `add_generation_prompt=True` is a prefix of the full
render - i.e. at inference the model would be asked to produce exactly those
tokens - and the dataset **raises** when that does not hold instead of quietly
dropping the turn.

### Mixing thinking and non-thinking samples

Because `enable_thinking` is untouched, both shapes work:

| `enable_thinking` | assistant turn | generation prompt | supervised |
| --- | --- | --- | --- |
| true / unset | `<think>\n{reasoning}\n</think>\n\n{content}` | `<\|im_start\|>assistant\n<think>\n` | reasoning + content |
| false | `<think>\n\n</think>\n\n{content}` | `<\|im_start\|>assistant\n<think>\n\n</think>\n\n` | content only |

With `false` the template closes the empty `<think>` block itself, so it lands in
the generation prompt and is excluded from the target. `false` against a turn that
*does* carry reasoning is a contradiction and raises rather than silently trimming.
It is one flag per render, so a row is entirely thinking or entirely not.

The converter never drops such rows - it marks them `enable_thinking: false` and
leaves the choice to the filter's `--require-reasoning`.

## 4. Look at the loss mask

```bash
python recipe/sft/scripts/inspect_loss_mask.py \
    --data recipe/sft/data/swe/reasoning__max131072/valid.parquet \
    --model Qwen/Qwen3.5-4B \
    --dataset-path recipe/sft/qwen3_5/dataset.py \
    --dataset-name Qwen3_5_SFTDataset \
    --chat-template-path recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja
```

It loads the data through that dataset class exactly as the trainer does
(`load_extern_object`, the same call behind `data.custom_cls`) and prints the
decoded sample with supervised regions highlighted. With no `--index` it loops.

| flag | |
| --- | --- |
| `--index N` | one row, then exit |
| `--mode target` | supervised text only |
| `--mode stats --num-samples N` | numbers over N rows, no text |

Expect roughly 20-40% of tokens supervised, and one span per assistant turn.

## 5. Train

`qwen3_5/run_megatron_sft.sh` is the launcher for the Qwen3.5 + Megatron example.
`data.custom_cls.path`, `model.path` and the engine's 3D-parallelism layout are all
specific to that model, so a different model family needs its own launcher.

```bash
cp recipe/sft/qwen3_5/.env.example recipe/sft/qwen3_5/.env   # then fill it in
ENV_FILE=recipe/sft/qwen3_5/.env NUM_GPUS=8 bash recipe/sft/qwen3_5/run_megatron_sft.sh
```

## 6. Tests

```bash
pytest recipe/sft/tests
```

Covers the conversion rules - reasoning normalization, tool-call argument
handling, the refused Harbor shape, trajectory trimming - with synthetic episodes.
No GPU, no model, no eval run, and no `rllm` import.

## Adding to this

- **A new episode shape or data source**: one converter under `converters/`,
  named after whatever recorded it, that emits the contract. It gets the filter,
  the inspector and every model family's dataset class for free.
- **A new model family**: one dataset class under `<family>/`, plus a training
  template if its stock one drops reasoning. The parquet does not change.
- **Neither** should require editing anything under `swe_sft/`.
