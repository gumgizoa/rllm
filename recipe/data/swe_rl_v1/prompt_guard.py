"""Runtime pin for the swe_rl_v1 prompt contract.

``build_tasks.py`` guarantees at build time that ``instruction.md`` is the row's
``problem_statement`` and nothing else. This module makes the *training / eval
process* refuse to run a task whose instruction drifted from that -- an edited
task dir, a re-materialized dataset, a template someone added, a row whose
``instruction`` column was built from a different field.

Usage in a training script::

    from recipe.data.swe_rl_v1.prompt_guard import PromptGuard, GuardedOpenHandsSdkHarness

    guard = PromptGuard.from_dataset_dir("$RLLM_HOME/datasets/swe_rl_v1")
    agent_flow = GuardedOpenHandsSdkHarness(guard=guard, step_limit=100)

The guard checks three things on every ``run()``:

1. ``sha256(normalized, stripped instruction)`` equals the manifest entry for the
   task (``prompt_sha256.json``, keyed by ``task.toml`` ``[task].name``; the
   ``task_id`` metadata is accepted as a fallback key);
2. the instruction carries none of the verifier / patch markers that could only
   come from a forbidden field;
3. ``task.metadata`` carries none of the forbidden row fields.

A violation raises :class:`PromptContractError`, which ``AgentFlowEngine`` records
as an ``error`` episode after its retries -- loud in the logs and dropped by
``compact_filtering`` -- instead of silently training on a leaked prompt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Episode, Task

logger = logging.getLogger(__name__)

FORBIDDEN_FIELDS = ("patch", "test_patch", "hints_text", "eval_script", "eval_script_skeleton", "link_context")
# Strings that cannot occur in an issue text we accept, only in the eval script /
# test patch heredoc / skeleton.
FORBIDDEN_MARKERS = ("OMNIGRIL_EXIT_CODE", "[CONTENT OF TEST PATCH]", "EOF_114329324912")


class PromptContractError(RuntimeError):
    """The task's instruction is not the pinned problem_statement."""


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def prompt_sha256(instruction: str) -> str:
    """Same hash ``build_tasks.py`` writes into prompt_sha256.json / manifest.jsonl."""
    return hashlib.sha256(normalize_newlines(instruction).strip().encode("utf-8")).hexdigest()


def _instruction_text(task: Task) -> str:
    inst = task.instruction
    if isinstance(inst, list):  # multimodal content blocks -- not used by this dataset
        inst = "\n".join(str(b.get("text", "")) for b in inst if isinstance(b, dict))
    return str(inst)


class PromptGuard:
    """Holds the pinned hashes and verifies a :class:`Task` against them."""

    def __init__(self, hashes: dict[str, str], source: str = ""):
        if not hashes:
            raise ValueError("PromptGuard needs at least one pinned hash")
        self.hashes = dict(hashes)
        self.source = source
        # Fallback index by bare task_id (manifest keys are '<dataset>/<task_id>').
        self._by_task_id = {k.rsplit("/", 1)[-1]: v for k, v in self.hashes.items()}

    @classmethod
    def from_dataset_dir(cls, dataset_dir: str | os.PathLike) -> PromptGuard:
        path = Path(dataset_dir).expanduser() / "prompt_sha256.json"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found -- build the dataset with recipe/data/swe_rl_v1/build_tasks.py")
        return cls(json.loads(path.read_text(encoding="utf-8")), source=str(path))

    @classmethod
    def from_env(cls, var: str = "SWE_RL_V1_DATASET_DIR") -> PromptGuard:
        value = os.environ.get(var)
        if not value:
            raise RuntimeError(f"set {var} to the swe_rl_v1 benchmark dir (holds prompt_sha256.json)")
        return cls.from_dataset_dir(value)

    def expected_for(self, task: Task) -> str | None:
        if task.id in self.hashes:
            return self.hashes[task.id]
        tid = (task.metadata or {}).get("task_id") or (task.metadata or {}).get("instance_id")
        if tid and tid in self._by_task_id:
            return self._by_task_id[tid]
        return self._by_task_id.get(str(task.id).rsplit("/", 1)[-1])

    def verify(self, task: Task) -> None:
        """Raise :class:`PromptContractError` unless *task* satisfies the contract."""
        expected = self.expected_for(task)
        if expected is None:
            raise PromptContractError(f"{task.id}: no pinned prompt hash in {self.source or 'the manifest'}")
        text = _instruction_text(task)
        actual = prompt_sha256(text)
        if actual != expected:
            raise PromptContractError(f"{task.id}: instruction hash {actual[:12]} != pinned {expected[:12]} (instruction is not the problem_statement the dataset was built from)")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                raise PromptContractError(f"{task.id}: instruction contains forbidden marker {marker!r}")
        leaked = [f for f in FORBIDDEN_FIELDS if (task.metadata or {}).get(f)]
        if leaked:
            raise PromptContractError(f"{task.id}: task metadata carries forbidden fields {leaked}")

    def verify_all(self, tasks) -> int:
        """Verify every task up front (dataset load time); returns the count checked."""
        n = 0
        for task in tasks:
            self.verify(task)
            n += 1
        logger.info("prompt contract: %d tasks verified against %s", n, self.source or "pinned hashes")
        return n


class GuardedOpenHandsSdkHarness(OpenHandsSdkHarness):
    """``openhands-sdk`` harness with the prompt pin and an explicit turn budget.

    * ``run()`` verifies the task against :class:`PromptGuard` first.
    * ``step_limit`` is exported as ``OPENHANDS_MAX_ITERATIONS`` (the SDK default is
      500) and read by ``AgentFlowEngine._turn_budget_termination_reason`` to stamp
      ``MAX_TURNS_EXCEEDED`` when the agent used its whole budget.
    """

    step_limit: int = 100

    def __init__(self, *args, guard: PromptGuard | None = None, step_limit: int | None = None, unguarded_ids: set[str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        # Task ids that are rolled out through this harness but never trained on (an external
        # validation benchmark such as swebenchpro_v2_100): they have no pinned hashes, and the
        # contract -- "the policy is trained on problem_statement only" -- does not apply to them.
        # Keyed by task id, not dataset name: Harbor-sourced rows carry no data_source field.
        self.unguarded_ids = set(unguarded_ids or ())
        # ``rllm eval --agent recipe.data.swe_rl_v1.prompt_guard:GuardedOpenHandsSdkHarness`` builds
        # the harness without arguments; the pinned hashes then come from the benchmark dir(s)
        # named in SWE_RL_V1_DATASET_DIR (colon-separated), e.g. the train and val dirs.
        if guard is None and os.environ.get("SWE_RL_V1_DATASET_DIR"):
            hashes: dict[str, str] = {}
            for d in os.environ["SWE_RL_V1_DATASET_DIR"].split(":"):
                if d.strip():
                    hashes.update(PromptGuard.from_dataset_dir(d.strip()).hashes)
            guard = PromptGuard(hashes, source=os.environ["SWE_RL_V1_DATASET_DIR"])
        self.guard = guard
        if step_limit is None:
            step_limit = int(os.environ.get("SWE_RL_V1_STEP_LIMIT", self.step_limit))
        self.step_limit = int(step_limit)

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        env = super().build_env(task, config)
        if self.step_limit and self.step_limit > 0:
            env["OPENHANDS_MAX_ITERATIONS"] = str(int(self.step_limit))
        return env

    def run(self, task: Task, config: AgentConfig, *, env: Sandbox) -> Episode | None:
        if self.guard is None:
            raise PromptContractError("GuardedOpenHandsSdkHarness needs a PromptGuard (guard=...)")
        if task.id not in self.unguarded_ids:
            self.guard.verify(task)
        return super().run(task, config, env=env)


__all__ = [
    "FORBIDDEN_FIELDS",
    "FORBIDDEN_MARKERS",
    "GuardedOpenHandsSdkHarness",
    "PromptContractError",
    "PromptGuard",
    "prompt_sha256",
]
