"""OpenHands harness for external benchmarks (SWE-bench Verified / Pro), matching the training rollouts.

``GuardedOpenHandsSdkHarness`` refuses tasks whose prompt is not pinned in a training dataset's
``prompt_sha256.json``; external benchmarks have no such pins. This subclass keeps everything else --
the ``OPENHANDS_MAX_ITERATIONS`` step budget from ``SWE_RL_V1_STEP_LIMIT`` -- and skips only the pin
check, so an eval run differs from training by the tasks alone::

    SWE_RL_V1_STEP_LIMIT=150 rllm eval swebench_verified_all \\
        --agent recipe.data.swe_rl_v1.eval_harness:UnpinnedOpenHandsSdkHarness ...
"""

from __future__ import annotations

from recipe.data.swe_rl_v1.prompt_guard import GuardedOpenHandsSdkHarness
from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Episode, Task


class UnpinnedOpenHandsSdkHarness(GuardedOpenHandsSdkHarness):
    """``GuardedOpenHandsSdkHarness`` without the training prompt pin (external benchmarks only)."""

    def run(self, task: Task, config: AgentConfig, *, env: Sandbox) -> Episode | None:
        return OpenHandsSdkHarness.run(self, task, config, env=env)


__all__ = ["UnpinnedOpenHandsSdkHarness"]
