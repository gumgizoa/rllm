# rLLM Recipes

Ready-to-run training recipes built on top of `examples/` and `cookbooks/`, with opinionated defaults for specific model + task combinations.

| Recipe | Backend | Task | Model |
|--------|---------|------|-------|
| [qwen3_5_swe_grpo](./qwen3_5_swe_grpo/) | verl (GRPO) | Native SWE (`mini-swe-agent`) | `Qwen/Qwen3.5-4B` |

Each recipe folder contains a `README.md`, `train.py`, launch script(s), and config helpers. Recipes are prepared for launch but are not executed automatically.

## Supervised fine-tuning

[`sft/`](./sft/) turns the trajectories an `rllm eval` run already produced into SFT training data, over a model- and data-agnostic parquet contract:

```
rllm eval  ->  sft/converters/from_rllm_gateway.py  ->  sft/scripts/filter_sft_parquet.py  ->  sft/qwen3_5/run_megatron_sft.sh
```

It deliberately does not go through `rllm sft`, which drops per-row `tools` on the way to verl and renders tool calls in a syntax Qwen3.5 does not use. [`sft/README.md`](./sft/README.md) has the four specific reasons and what to fix if you would rather change `rllm sft` instead.

| Piece | Scope |
|-------|-------|
| `sft/swe_sft/` | The parquet contract and its utilities. Model- and data-agnostic. |
| `sft/converters/` | One converter per data source. |
| `sft/qwen3_5/` | One dataset class, training chat template and launcher per model family. |

## Evaluation

[`eval/`](./eval/) holds the `rllm eval` guide for SWE-bench, with both the native rLLM harness and the Harbor harness (`--agent harbor:*`).

| Guide | Dataset | Contents |
|-------|---------|----------|
| [eval/README.md](./eval/README.md) | — | Setup, native vs Harbor harness, model connection, troubleshooting |
| [eval/swebench-pro](./eval/swebench-pro/) | `swebenchpro_100` (100 of 731) | Subset script, oracle test, evaluation commands |
| [eval/swebench-verified](./eval/swebench-verified/) | `swebench_verified_100` (100 of 500) | Same layout as swebench-pro |

Shared sampling params live in [`eval/config/`](./eval/config/) (`qwen3_5.yaml`).
