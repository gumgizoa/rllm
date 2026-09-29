"""Harness classes for evaluating a trained checkpoint with ``rllm eval`` under the
training-time settings, which ``--agent-kwargs`` cannot set on a native harness.

    rllm eval swegym_val23 --split test \
        --agent recipe.grpo.qwen3_5.eval_harness:SwegymOpenHandsEval \
        --agent-image auto --sandbox-backend docker --no-ui \
        --base-url http://127.0.0.1:8000/v1 --model step9

Run from the repo root so ``recipe.grpo.qwen3_5`` imports. The values mirror
``config/variant/openhands_9b_aidlc_swegym.yaml``: 80 iterations and no-think
(``enable_thinking=False`` reaches vLLM as ``chat_template_kwargs`` on every
request, since eval renders every turn with the chat template).
"""

from __future__ import annotations

from recipe.grpo.qwen3_5.aidlc_flow import AidlcOpenHandsSdkHarness, StepLimitedOpenHandsSdk


class SwegymOpenHandsEval(StepLimitedOpenHandsSdk):
    """openhands-sdk, SDK's own workflow, as trained by ``variant=openhands_9b_swegym``."""

    step_limit: int = 80
    enable_thinking: bool | None = False


class SwegymAidlcEval(AidlcOpenHandsSdkHarness):
    """openhands-sdk + AI-DLC documents, as trained by ``variant=openhands_9b_aidlc_swegym``."""

    step_limit: int = 80
    enable_thinking: bool | None = False
