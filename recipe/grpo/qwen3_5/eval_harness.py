"""Harness classes for evaluating a trained checkpoint with ``rllm eval`` under the
training-time settings, which ``--agent-kwargs`` cannot set on a native harness.

    PYTHONPATH=$PWD rllm eval swegym_val23 --split test \
        --agent recipe.grpo.qwen3_5.eval_harness:SwegymOpenHandsEval \
        --agent-image auto --sandbox-backend docker --hide-git-history --no-ui \
        --base-url http://127.0.0.1:8000/v1 --model step9

Run with the repo root on ``PYTHONPATH`` so ``recipe.grpo.qwen3_5`` imports.
The values mirror ``config/variant/openhands_9b_aidlc_swegym.yaml``: 100
iterations and no-think (``enable_thinking=False`` reaches vLLM as
``chat_template_kwargs`` on every request, since eval renders every turn with
the chat template). ``--agent-kwargs step_limit=15,instruction_position=suffix``
overrides any attribute for a run (``StepLimitedOpenHandsSdk.configure``).
"""

from __future__ import annotations

from recipe.grpo.qwen3_5.aidlc_flow import AidlcOpenHandsSdkHarness, StepLimitedOpenHandsSdk


class SwegymOpenHandsEval(StepLimitedOpenHandsSdk):
    """openhands-sdk, SDK's own workflow, as trained by ``variant=openhands_9b_swegym``."""

    step_limit: int = 100
    enable_thinking: bool | None = False


class SwegymAidlcEval(AidlcOpenHandsSdkHarness):
    """openhands-sdk + AI-DLC documents, as trained by ``variant=openhands_9b_aidlc_swegym``
    since run 2: the AI-DLC instruction before the task text (config.yaml
    ``instruction_position: prefix``). Pair it with ``swegym293_aidlc`` /
    ``swegym_val23_aidlc`` (``prepare_swegym.py --instruction aidlc``); for run 2's
    arrangement use ``swegym293`` and ``--agent-kwargs instruction_position=suffix``."""

    step_limit: int = 100
    enable_thinking: bool | None = False
    instruction_position: str = "prefix"
