# Qwen3.5-4B Native SWE GRPO (verl)

GRPO training for a **native rLLM** SWE agent — `AgentFlowEngine`, not the Harbor runtime.

|                       | `examples/harbor_swe`             | This recipe                                                        |
| --------------------- | --------------------------------- | ------------------------------------------------------------------ |
| Engine                | `RemoteAgentFlowEngine`           | `AgentFlowEngine`                                                    |
| Sandbox / agent / verifier | Harbor `Trial.run()`         | `SandboxTaskHooks` + `MiniSweAgentHarness` + `ShellScriptEvaluator`  |
| Backend               | tinker                            | **verl**                                                             |
| Train data            | `harbor:swesmith`                 | `rllm_swesmith_small` (SWE-smith slice)                              |
| Val data              | `harbor:swebench-verified`        | `swebench_verified_local` (SWE-bench Verified, local-image subset)   |

`rllm.remote_runtime.enabled=false` throughout. `harbor:swebench-verified` is used **only as a
source of task directories** (`task.toml` + `environment/Dockerfile` + `tests/test.sh`); the
Harbor runtime, Harbor agent scaffolds and `harbor:mini-swe-agent` are not involved.

Rollout path per task:

```
SandboxTaskHooks       docker run <task image> (+ agent-image mount)
MiniSweAgentHarness    mini-swe-agent CLI *inside* the sandbox
  └─ litellm ────────► rLLM model gateway (host.docker.internal) ──► vLLM (verl rollout)
GatewayManager         captures prompt/completion token ids + logprobs
ShellScriptEvaluator   /tests/test.sh → /logs/verifier/reward.txt → reward
```

## Setup

```bash
# RLLM_SCRATCH should point at a large volume: the model snapshot is ~9 GB and
# the SWE task images run to tens of GB more. Defaults to $HOME/rllm-work.
RLLM_SCRATCH=/mnt/big/rllm-work source recipe/qwen3_5_swe_grpo/env.sh

# Fused kernels for Qwen3.5's linear-attention layers -- not optional, see below.
uv pip install flash-linear-attention==0.5.2

rllm dataset pull harbor:swebench-verified            # 500 task dirs (text only)
python recipe/qwen3_5_swe_grpo/scripts/prepare_datasets.py --train-limit 24
xargs -a "$RLLM_HOME/datasets/rllm_swesmith_small/images.txt" -P 4 -I{} docker pull {}
```

`prepare_datasets.py` registers two small benchmarks under `$RLLM_HOME/datasets`:

* **`swebench_verified_local/test`** — every SWE-bench Verified task whose
  `swebench/sweb.eval.x86_64.*` base image is already in the local Docker daemon. The full
  500-task set needs ~2 TB of images, so validation is pinned to what is pre-pulled. Task dirs
  are copied out of the Harbor cache so this recipe owns their timeouts.
* **`rllm_swesmith_small/train`** — a round-robin slice of `kylemontgomery/swesmith-filtered`,
  one task per repo, so a smoke run sees repo diversity without pulling all ~4.7K images.

For both, the script patches `[agent].timeout_sec=900` / `[verifier].timeout_sec=1800` into
each `task.toml` (upstream ships 3000/3000, which at `rollout.n=8` makes one batch take hours).

### Screen the data with the oracle first

The oracle harness runs `solution/solve.sh` and then the real verifier, with no LLM. It is the
cheapest way to prove that a task's image, verifier and reward file all work before spending
rollouts on it:

```bash
rllm eval swebench_verified_local --agent oracle --sandbox-backend docker \
    --split test --concurrency 3 --no-ui \
    --base-url http://127.0.0.1:1/v1 --model oracle-dummy
```

A task that scores 0 here can never be solved by a policy either. `prepare_datasets.py` drops
the ones found that way — see `UNSCORABLE` (currently `astropy__astropy-7606`, whose
`PASS_TO_PASS` list names `test_compose_roundtrip[]`, a pytest param id that never appears in
the classic-style output the SWE-bench log parser reads).

Measured on this setup: SWE-bench Verified subset 4/4, SWE-smith 1/1.

## Run

```bash
bash recipe/qwen3_5_swe_grpo/smoke_test.sh    # 1 batch, 2 tasks x 4 rollouts — "does it run?"
bash recipe/qwen3_5_swe_grpo/train_verl.sh    # 24 tasks x 8 rollouts, 1 epoch
```

Any Hydra override passes through:

```bash
bash recipe/qwen3_5_swe_grpo/train_verl.sh \
    rllm.rollout.n=16 \
    rllm.trainer.logger="['console','wandb']" \
    recipe.val_limit=2
```

Env knobs: `RLLM_SCRATCH` (storage root), `SANDBOX_BACKEND` (default `docker`),
`RLLM_AGENT_IMAGE` (`auto` | `skip` | `repo:tag`), `MODEL_PATH`, `RLLM_RUN_DIR`,
`HF_HUB_OFFLINE`.

## Why the config looks like this

### Qwen3.5-4B is a hybrid-attention VLM

`Qwen3_5ForConditionalGeneration`: a vision tower plus a text stack that interleaves
`Qwen3_5GatedDeltaNet` **linear-attention** layers with full-attention layers (3:1). Two
consequences:

* **`ppo_micro_batch_size_per_gpu=1`, `use_dynamic_bsz=false`.** Packing several sequences into
  one flat batch is fine for full-attention layers (`cu_seqlens`) but a gated-delta-net layer
  would carry recurrent state straight across the sample boundary. One sequence per
  micro-batch sidesteps that entirely, which is also what makes `use_remove_padding=true` safe
  here (see the memory section — the packed layout is not optional). Raising the micro-batch
  size or switching on token-budget batching needs that checked first.
* **`flash-linear-attention` must be installed.** 24 of the 32 layers are linear attention, and
  HF's `Qwen3_5GatedDeltaNet` falls back to a pure-PyTorch `torch_chunk_gated_delta_rule` when
  the fused kernels are missing. It is correct but slow, and it dominates the training step.
  Installing it (`uv pip install flash-linear-attention==0.5.2`, triton-only, no CUDA
  toolchain needed) is measured below.

  The companion [`causal-conv1d`](https://github.com/Dao-AILab/causal-conv1d) ships as an sdist
  and needs `nvcc`, which this image does not have — so it stays uninstalled. That is fine:
  the four kernels bind **independently**
  (`self.chunk_gated_delta_rule = chunk_gated_delta_rule or torch_chunk_gated_delta_rule`), so
  the expensive delta-rule op is fused while only the cheap depthwise conv falls back to
  `F.silu(self.conv1d(...))`. **The `"The fast path is not available"` warning still prints**,
  because `is_fast_path_available` is an all-or-nothing `all(...)` over all four — ignore it
  and check `perf/throughput` instead.

verl 0.8.0 does support the architecture (`verl/models/transformers/qwen3_5.py`, plus a
`monkey_patch.py` branch for `model_type in ("qwen3_5", "qwen3_5_moe")`).

### preserve_thinking, and why it is not just a chat template

Qwen3.5 uses **interleaved thinking**: its chat template keeps `<think>` blocks only for turns
after the last user query and strips the rest. `rllm.gateway.cumulative_token_mode=true` avoids
re-tokenizing history by extending the previous turn's raw token ids, and the `renderers` bridge
refuses to do that whenever the policy would have re-rendered — which, under the default
`tool_cycle` retention, is **every new user message**. mini-swe-agent feeds each shell result
back as a user message, so without `preserve_thinking` every single turn falls back to a full
re-render: historical reasoning dropped, prompt growing O(T²), and the prefix-extension chain
broken into one batch row per turn.

```
qwen3.5  {}                            bridge=None (full re-render)
qwen3.6  {}                            bridge=None (full re-render)
qwen3.6  {preserve_thinking: True}     bridge=OK, prefix-extension holds
```

Hence `renderer_family: qwen3.6` + `renderer_kwargs: {preserve_thinking: true}`.
`Qwen36Renderer` subclasses `Qwen35Renderer` and differs only in tool-argument JSON
serialization and this flag, so it is token-identical for this workload. (The Qwen3.6-27B
*Jinja* template likewise differs from Qwen3.5-4B's in exactly two lines — the
`preserve_thinking` gate and the `tojson` change — so shipping it as
`custom_chat_template` buys nothing here and is left out.)

Health check for all of this: `training/rollout_actor_probs_pearson_corr` in the step metrics.
It compares the actor's recomputed log-probs against the ones sampled during rollout, and sits
at **0.9995** on this recipe. A low value means the token stream that reached training is not
the one the policy sampled.

### Tool calling

mini-swe-agent v2 requires the model to answer with a **`bash` tool call** ("Your response MUST
include AT LEAST ONE bash tool call"), and its litellm client always sends `tool_choice="auto"`.
vLLM rejects that unless auto tool choice is on, so the rollout gets
`enable_auto_tool_choice=true` + `tool_call_parser=qwen3_xml` (which matches Qwen3.5's
`<tool_call><function=..><parameter=..>` template markup) alongside `reasoning_parser=qwen3`.

### Batch sizes

verl asserts `data.train_batch_size * rollout.n % n_gpus == 0` (FSDP `minimal_bsz = n_gpus`),
and rLLM multiplies `actor.ppo_mini_batch_size` by `rollout.n` to get the mini-batch of
trajectories. With 8 GPUs:

| | tasks/batch | `rollout.n` | trajectories | `ppo_mini_batch_size` | updates/batch |
|---|---|---|---|---|---|
| `train_verl.sh` | 4 | 8 | 32 | 4 | 1 (on-policy) |
| `smoke_test.sh` | 2 | 4 | 8  | 2 | 1 |

### Memory: the vocabulary is the wall

Qwen3.5's vocabulary is **248320 tokens**. Materializing logits for a single merged trajectory
of ~23K tokens in fp32 is one **21 GB** allocation, and with FSDP param/optimizer offload
already in play an 80 GB card still dies with
`torch.OutOfMemory: Tried to allocate 21.48 GiB`. Neither micro-batch size nor offloading helps
— it is one tensor for one sequence.

`actor_rollout_ref.model.use_fused_kernels=true` +
`fused_kernel_options.impl_backend=torch` is the fix: verl's `FusedLinearForPPO` computes
`log_probs` / `entropy` in chunks straight off the hidden states and never builds the logits
tensor (verl has a Qwen3.5-specific `forward_with_torch_backend`). Everything else — sequence
length, `ppo_micro_batch_size_per_gpu`, offload — is a second-order knob next to this one.

The fused path consumes the **packed** layout, so `use_remove_padding=true` comes with it;
without it rLLM's `no_padding_2_padding` fails on
`assert sequence_offsets[-1].item() == values.shape[0]`. That is safe here only because a
micro-batch holds exactly one sequence — see the hybrid-attention note above.

### Turn budget

Upstream mini-swe-agent defaults to `agent.step_limit: 0` (unlimited) and relies on
`cost_limit` instead — which is inert here, since the gateway-routed model has no litellm cost
table and the harness sets `MSWEA_COST_TRACKING=ignore_errors`. Left unbounded, the cumulative
prompt keeps growing until vLLM rejects a turn with *"This model's maximum context length is N
tokens"*; the agent's retries all fail and rLLM discards the episode with an
`EnrichMismatchError` instead of scoring it.

`train.py` therefore wraps the harness in `StepLimitedMiniSweAgent`, which passes
`-c mini.yaml -c agent.step_limit=<recipe.agent_step_limit>` (naming `mini.yaml` again is
required: `-c` *replaces* the default config rather than layering on it). Size the limit against
`max_model_len` — roughly **620 prompt tokens per turn** measured on SWE-smith with this policy,
so 50 turns ≈ 33K tokens under the 40960 ceiling.

### Lengths

An AgentFlow batch row is one **merged trajectory**: the prompt is turn 1's prompt and the
response accumulates every later turn's observation + action delta. So `max_response_length`
(24576) has to cover a whole episode, while `rllm.rollout.train.max_tokens` (4096) caps a single
turn. `rllm.compact_filtering` zeroes the loss on trajectories that were truncated or timed out
rather than finished, so those don't get learned as if they were policy choices.

### HuggingFace rate limits

Eight FSDP workers, eight vLLM servers and the gateway each resolve `Qwen/Qwen3.5-4B` on
startup. Unauthenticated that exceeds the Hub's 500-requests / 300s per-IP budget, and the
throttled process reports it as `OSError: Unable to load vocabulary from file` — a rate-limit
error wearing a corrupted-cache costume. `train_verl.sh` therefore defaults to
`HF_HUB_OFFLINE=1` (the snapshot is already in `$HF_HOME` by launch time). Export `HF_TOKEN`,
or `HF_HUB_OFFLINE=0`, if you actually want the hub consulted.

## What a healthy step looks like

`train_verl.sh` defaults on 8x A100-80GB — 4 SWE-smith tasks x `rollout.n=8`, untrained
Qwen3.5-4B. Learning-signal numbers are from a step that happened to contain a solve;
performance numbers are from a steady-state step (second step of a run, triton kernels cached).

**Is the plumbing right?**

| metric | why it matters | observed |
| --- | --- | --- |
| `training/rollout_actor_probs_pearson_corr` | actor's recomputed log-probs vs. what the policy actually sampled. The single best check that cumulative-token mode, `preserve_thinking` and the trace pipeline all line up. | **0.9997** (`probs_diff_mean` 0.0026) |
| `batch/merge_compression_ratio` | turns folded into one batch row by prefix extension. Equal to `batch/n_turns` means the whole episode merged; **1.0 means prefix extension is broken** and every turn became its own row. | **36.4** (= `n_turns`) |
| `batch/termination_reason/error` | rollouts that died instead of finishing — usually the context ceiling. | **0.0** (was 0.125 at `max_model_len=32768`) |

**Is there a learning signal?**

| metric | why it matters | observed |
| --- | --- | --- |
| `reward/mini-swe-agent/{mean,max,std}` | is the verifier reachable at all by the policy? | 0.031 / 1.0 / 0.17 |
| `batch/mini-swe-agent/fractions/{too_hard,effective}` | groups with no reward spread vs. groups that carry signal. | 0.75 / **0.25** |
| `advantage/mini-swe-agent/std` | non-zero means GRPO has something to push on. | **0.50** (max 2.65, min -0.38) |
| `actor/pg_loss`, `grad_norm` | the actual update. | **0.031**, **0.312** |

`pg_loss = 0` with `grad_norm = 0` and `too_hard = 1.0` is **not** a broken optimizer: GRPO
normalizes reward within a group, so a group where every rollout scores 0 contributes exactly
zero advantage. That is a normal first-step picture; the gradient appears as soon as one rollout
in a group solves its task. If it never does, the training set is too hard for the starting
policy rather than misconfigured.

**Is it fast enough?** A clean A/B — same config, only `flash-linear-attention` differs:

| | torch fallback | with fla | |
| --- | --- | --- | --- |
| `timing_s/update_actor` | 344.3 s over 718K tokens | 62.8 s over 947K tokens | |
| ⤷ per token | 479 µs | **66 µs** | **7.2x** |
| `timing_s/old_log_probs` | 34.3 s | 24.9 s | |
| `perf/throughput` (incl. rollout) | 120 tok/s | **210 tok/s** | 1.75x |
| `perf/max_memory_allocated_gb` | 41.9 | **27.1** | |
| `rollout_actor_probs_pearson_corr` | 0.999602 | **0.999662** | |

Two things worth noting. First, the **first** step after installing fla is slower than steady
state (`update_actor` 145 s) while triton compiles and autotunes the kernels; the cache is on
disk, so it is a one-time cost per machine. Second, the fused path does not just run faster —
it agrees with vLLM's rollout slightly *better* than the torch fallback does. A standalone
forward comparison of the two implementations shows ~0.28 max logit difference on a bf16 model
(different reduction order), which sounds alarming in isolation; the pearson metric is the one
that answers whether it matters, and it moved the right way.

## Agent image mount

`RLLM_AGENT_IMAGE=auto` (the default) bakes mini-swe-agent into a small local image once and
mounts it read-only at `/opt/rllm/agent` in every task sandbox (Docker `type=image` mount), so
no rollout pays for `uv tool install`. Same mechanism as `rllm eval --agent-image`.

* Docker backend only. `modal` / `daytona` fall back to a per-task install.
* `RLLM_AGENT_IMAGE=skip` forces the per-task install path.
* Building the image needs network on the *host*; the sandbox itself does not install anything.

## Sandbox network isolation — still not supported

`DockerSandbox` / `ModalSandbox` / `DaytonaSandbox` expose no `network_mode` or egress policy,
and the task sandboxes here **do** need the network:

| setting | internet | gateway (LLM) | result |
|---|---|---|---|
| `network_mode=none` | blocked | **blocked** | every rollout fails — the agent's LLM calls go out through `host.docker.internal` |
| default bridge (today) | allowed | allowed | reward hacking is possible (web search, external APIs, `pip install`) |
| selective egress (not implemented) | blocked | host-only allow | what you actually want |

Both verifiers also need the network at runtime: SWE-bench Verified's `test.sh` runs
`uv run parser.py` (pulls `swebench`, `datasets`, `fastcore`), and SWE-smith's runs
`apt-get install` + `uv add pytest swebench datasets swesmith`. Blocking egress means
pre-baking those into the task images first.

## Fixes this recipe required in rLLM

Each of these was a hard failure of the native training path, not a tuning choice:

1. **`rllm/trainer/unified_trainer.py`** — the training warm queue created sandboxes without the
   agent-image mount while `SandboxTaskHooks` still marked the CLI as pre-provisioned, so every
   rollout died with `mini-swe-agent: command not found` (zero traces, reward 0). Now passes
   `agent_mount_image=`, mirroring `rllm/eval/runner.py`.
2. **`rllm-model-gateway` `proxy.py`** — cumulative token mode rewrites turn 2+ to
   `/v1/completions`, which has no reasoning or tool-call parser, and the old code handed the raw
   text back as `content`. A tool-calling agent then saw no `tool_calls` on any turn past the
   first and stalled after ~4 turns. The cumulative handler now parses the completion with the
   same renderer that built the prompt (`_completion_to_chat_message`), recovering `content`,
   `reasoning_content` and `tool_calls`. Turn count went 4 → 34 on the same task.

   The same applies to **streaming**: these tool calls are markup, so they cannot be recognised
   from a partial text delta without a per-family incremental parser. A streaming request that
   carries `tools` is therefore routed to `_handle_cumulative_buffered_stream`, which takes the
   completion non-streaming, runs it through the shared `_cumulative_completion` core, and
   re-emits it as well-formed `chat.completion.chunk` frames. The client keeps its SSE contract
   and gets the same message the JSON path would return; only the incrementality is lost.
   Requests without tools keep the true incremental path.
   Covered by `tests/integration/test_cumulative_tool_calls.py` (JSON + SSE).
3. **`rllm-model-gateway` `models.py` / `server.py` + `rllm/gateway/manager.py` +
   `rllm/trainer/config/rllm/base.yaml`** — new `gateway.renderer_kwargs`, so a renderer family's
   config can be overridden (`preserve_thinking`). Previously only the bare family name could be
   set, and `config_from_name("qwen3.6")` defaults `preserve_thinking=False`.
4. **`train.py`** uses `DatasetRegistry.load_dataset(..., as_tasks=True)`. Without it every row
   becomes a `Task` rooted at `dataset_dir="."` and verifier auto-detection fails with
   `No verifier configured for task ...`.

## Files

```
recipe/qwen3_5_swe_grpo/
├── README.md
├── env.sh                        # RLLM_SCRATCH / HF_HOME / RLLM_HOME / venv
├── train.py                      # Hydra entry → unified AgentTrainer(agent_flow=..., backend="verl")
├── train_verl.sh                 # verl/vLLM/FSDP knobs + hardware assumptions
├── smoke_test.sh                 # 1 batch, minimal everything
├── config/
│   ├── config.yaml               # Hydra primary: rllm/base + rllm/backend=verl + grpo_verl
│   └── grpo_verl.yaml            # rLLM-side defaults (data, rollout, gateway, GRPO, filtering)
└── scripts/prepare_datasets.py   # builds + registers the train/val benchmarks
```
