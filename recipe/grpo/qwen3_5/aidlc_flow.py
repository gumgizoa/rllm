"""openhands-sdk harnesses for this recipe: a turn budget, and AI-DLC on top of it.

Two classes, selected by ``recipe.agent`` / ``recipe.aidlc.enable`` in
``config/config.yaml``:

``StepLimitedOpenHandsSdk``
    :class:`~rllm.harnesses.openhands_sdk.OpenHandsSdkHarness` plus a
    ``step_limit``. The engine reads that attribute to stamp
    ``MAX_TURNS_EXCEEDED`` (``agentflow_engine._turn_budget_termination_reason``)
    and the harness forwards it to the SDK as ``OPENHANDS_MAX_ITERATIONS``, so
    the budget the agent runs under and the one the reward shaping sees are the
    same number. Without it an agent that used every iteration is
    indistinguishable from one that finished -- ``ENV_DONE`` -- and the
    SWE-Master ``budget_reward_scale`` never applies.

``AidlcOpenHandsSdkHarness``
    The same agent made to follow the AI-DLC workflow. Three things go into the
    sandbox, mirroring what the Harbor experiment did with compose mounts and
    job-config knobs (``harbor-extension/experiments/aidlc``):

    1. the workflow documents, uploaded to ``/ai-dlc`` -- outside the
       repository, so ``git diff`` cannot pick them up and the verifier's
       cleanup cannot trip over them;
    2. an instruction suffix telling the agent where the documents are;
    3. a replacement system prompt. This one is not optional for
       openhands-sdk: its default prompt carries a ``<PROBLEM_SOLVING_WORKFLOW>``
       section that prescribes its own procedure, and that outranks anything
       appended to the user message -- the Harbor run without it ignored the
       instruction. The shipped template is the SDK 1.42.1 default with that
       one section rewritten; a different ``SDK_VERSION`` needs re-extraction.

    The documents, the instruction and the system prompt live together under
    ``aidlc/`` and are versioned with the recipe, because the three name each
    other by absolute path (``/ai-dlc/...``) and by what a stage produces
    (artifacts under ``/tmp/swe-bench-pro/``). A set copied from elsewhere at
    run time would let one of them drift from the other two.

Both return ``None`` from ``run()`` like every CLI harness: the gateway
captures the LLM calls and the engine builds the Episode.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Task

logger = logging.getLogger(__name__)

RECIPE_DIR = Path(__file__).resolve().parent
DEFAULT_DOCS_DIR = RECIPE_DIR / "aidlc"
DEFAULT_INSTRUCTION_FILE = DEFAULT_DOCS_DIR / "instruction.md"
DEFAULT_SYSTEM_PROMPT_FILE = DEFAULT_DOCS_DIR / "system-prompt.j2"

# Where the system prompt template lands in the sandbox. Next to the runner
# (``/opt/openhands-sdk-runner.py``), for the same reason: written per task,
# a few KB, never inside the task's repository.
_SYSTEM_PROMPT_REMOTE = "/opt/openhands-sdk-system-prompt.j2"


class StepLimitedOpenHandsSdk(OpenHandsSdkHarness):
    """openhands-sdk with an explicit iteration budget.

    One SDK iteration is one agent step (one LLM call, possibly several tool
    calls), and the gateway records one trace per LLM call, so the engine's
    trace count and the SDK's iteration count agree closely enough for the
    ``MAX_TURNS_EXCEEDED`` stamp.
    """

    step_limit: int = 50

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        env = super().build_env(task, config)
        if self.step_limit and int(self.step_limit) > 0:
            env["OPENHANDS_MAX_ITERATIONS"] = str(int(self.step_limit))
        return env


class AidlcOpenHandsSdkHarness(StepLimitedOpenHandsSdk):
    """openhands-sdk driven by the AI-DLC workflow documents.

    Attributes are the knobs ``train.py`` fills from ``recipe.aidlc``; the
    defaults point at the copies shipped in ``aidlc/`` so the class also works
    stand-alone (``rllm eval --agent recipe.grpo.qwen3_5.aidlc_flow:AidlcOpenHandsSdkHarness``).

    ``instruction_file`` / ``system_prompt_file`` may be ``None`` to switch that
    layer off for an ablation; the documents are always uploaded.

    ``name`` is deliberately left at ``"openhands-sdk"``: ``rllm.sandbox.agent_image``
    keys the agent-image mount on that string, and a renamed harness would
    silently fall back to a per-task SDK install. Runs are told apart by
    ``rllm.trainer.experiment_name``, not by the harness name.
    """

    docs_dir: str | Path = DEFAULT_DOCS_DIR
    container_dir: str = "/ai-dlc"
    instruction_file: str | Path | None = DEFAULT_INSTRUCTION_FILE
    system_prompt_file: str | Path | None = DEFAULT_SYSTEM_PROMPT_FILE

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docs_dir = Path(self.docs_dir)
        self.instruction_file = Path(self.instruction_file) if self.instruction_file else None
        self.system_prompt_file = Path(self.system_prompt_file) if self.system_prompt_file else None
        if not self.container_dir.startswith("/"):
            raise ValueError(f"recipe.aidlc.container_dir must be absolute, got {self.container_dir!r}")
        self._validate_local_files()

    # ------------------------------------------------------------------
    # Local side
    # ------------------------------------------------------------------

    def _validate_local_files(self) -> None:
        """Fail at construction, not on the first rollout.

        A rollout that starts without the documents is indistinguishable on the
        scoresheet from one that had them and ignored them (the SkyRL port
        learned this the hard way -- ``verl/workers/agentic/utils.py``), so
        every path is checked before a sandbox exists.
        """
        if not self.docs_dir.is_dir():
            raise FileNotFoundError(f"AI-DLC docs dir not found: {self.docs_dir}")
        if not (self.docs_dir / "core-workflow.md").is_file():
            raise FileNotFoundError(f"AI-DLC docs dir has no core-workflow.md: {self.docs_dir}")
        if not self._doc_entries():
            raise FileNotFoundError(f"AI-DLC docs dir has nothing to upload: {self.docs_dir}")
        for label, path in (("instruction_file", self.instruction_file), ("system_prompt_file", self.system_prompt_file)):
            if path is not None and not path.is_file():
                raise FileNotFoundError(f"AI-DLC {label} not found: {path}")

    def _excluded(self) -> set[Path]:
        """Files inside ``docs_dir`` that are prompt material, not workflow documents.

        The shipped names are excluded unconditionally, not just when selected:
        an ablation that sets ``instruction_file=null`` must not turn
        ``aidlc/instruction.md`` into a seventh document the agent can read.
        """
        excluded = {p.resolve() for p in (self.instruction_file, self.system_prompt_file) if p is not None}
        excluded |= {(self.docs_dir / DEFAULT_INSTRUCTION_FILE.name).resolve(), (self.docs_dir / DEFAULT_SYSTEM_PROMPT_FILE.name).resolve()}
        return excluded

    def _doc_entries(self) -> list[Path]:
        """Top-level entries of ``docs_dir`` that go into the container.

        Uploaded entry by entry rather than as one tree so the prompt files
        (which sit beside the documents for versioning) stay out, and so the
        layout is era-agnostic: SkyRL's v4 set is flat, v1 and this set keep
        the stage files under ``rule-details/``.
        """
        excluded = self._excluded()
        return sorted(p for p in self.docs_dir.iterdir() if p.resolve() not in excluded and not p.name.startswith("."))

    def _expected_doc_count(self) -> int:
        excluded = self._excluded()
        return sum(1 for p in self.docs_dir.rglob("*.md") if p.resolve() not in excluded)

    def instruction_suffix(self) -> str:
        return self.instruction_file.read_text(encoding="utf-8").strip() if self.instruction_file else ""

    # ------------------------------------------------------------------
    # Sandbox side
    # ------------------------------------------------------------------

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        env = super().build_env(task, config)
        if self.system_prompt_file is not None:
            env["OPENHANDS_SDK_SYSTEM_PROMPT_PATH"] = _SYSTEM_PROMPT_REMOTE
        return env

    def write_configs(
        self,
        sandbox: Sandbox,
        task: Task,
        config: AgentConfig,
        env: dict[str, str],
    ) -> None:
        super().write_configs(sandbox, task, config, env)
        self._upload_docs(sandbox)
        if self.system_prompt_file is not None:
            sandbox.exec(
                self._heredoc_write(_SYSTEM_PROMPT_REMOTE, self.system_prompt_file.read_text(encoding="utf-8")),
                timeout=60,
                user="root",
            )

    def _upload_docs(self, sandbox: Sandbox) -> None:
        """Put the workflow documents at ``container_dir`` and prove they arrived.

        The directory is cleared first: a warm or reused sandbox must not serve
        a previous document set, and the eras use different file names, so a
        leftover would survive an overwrite. The count check afterwards is the
        point of the whole method -- a partial upload has to stop the rollout
        here rather than surface later as a policy that "ignored the workflow".
        """
        target = self.container_dir.rstrip("/")
        sandbox.exec(f"rm -rf {shlex.quote(target)} && mkdir -p {shlex.quote(target)}", timeout=30, user="root")
        for entry in self._doc_entries():
            remote = f"{target}/{entry.name}"
            if entry.is_dir():
                sandbox.upload_dir(str(entry), remote)
            else:
                sandbox.upload_file(str(entry), remote)
        expected = self._expected_doc_count()
        found = sandbox.exec(
            f"find {shlex.quote(target)} -type f -name '*.md' | wc -l",
            timeout=30,
            user="root",
        )
        try:
            n = int(str(found).strip().splitlines()[-1])
        except (ValueError, IndexError) as e:
            raise RuntimeError(f"AI-DLC docs check: unreadable find output {found!r}") from e
        if n != expected:
            raise RuntimeError(f"AI-DLC docs check: expected {expected} .md files under {target}, found {n}")

    def build_invocation(
        self,
        instruction: str,
        task: Task,
        config: AgentConfig,
    ) -> str:
        suffix = self.instruction_suffix()
        if suffix:
            instruction = f"{instruction.rstrip()}\n\n{suffix}"
        return super().build_invocation(instruction, task, config)
