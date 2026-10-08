"""Names kept for train.py, eval_harness.py and existing run commands.

The harnesses live in ``workflow_harness.py`` and the AI-DLC set is registered
in ``workflows.py``. New code selects the workflow by name instead:

    --agent recipe.grpo.qwen3_5.workflow_harness:OpenHandsSdkWorkflow \\
    --agent-kwargs workflow=aidlc
"""

from __future__ import annotations

# Loaded as ``aidlc_flow`` by train.py (recipe directory on sys.path) and as
# ``recipe.grpo.qwen3_5.aidlc_flow`` by ``rllm eval --agent``.
if __package__:
    from .workflow_harness import OpenHandsSdkWorkflow, StepLimitedOpenHandsSdk
else:
    from workflow_harness import OpenHandsSdkWorkflow, StepLimitedOpenHandsSdk

__all__ = ["AidlcOpenHandsSdkHarness", "StepLimitedOpenHandsSdk"]


class AidlcOpenHandsSdkHarness(OpenHandsSdkWorkflow):
    """``OpenHandsSdkWorkflow`` following AI-DLC unless told otherwise."""

    workflow = "aidlc"
