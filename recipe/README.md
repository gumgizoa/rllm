# rLLM Recipes

Ready-to-run training recipes built on top of `examples/` and `cookbooks/`, with opinionated defaults for specific model + task combinations.

| Recipe | Backend | Task | Model |
|--------|---------|------|-------|
| [qwen3_5_swe_grpo](./qwen3_5_swe_grpo/) | verl (GRPO) | Native SWE (`mini-swe-agent`) | `Qwen/Qwen3.5-4B` |

Each recipe folder contains a `README.md`, `train.py`, launch script(s), and config helpers. Recipes are prepared for launch but are not executed automatically.
