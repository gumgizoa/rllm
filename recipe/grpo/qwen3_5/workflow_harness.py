"""Harnesses for this recipe: a turn budget, and a workflow on top of any harness.

``AgentKwargsMixin``
    ``rllm eval --agent-kwargs key=value,...`` for any CLI harness: each key
    must be an attribute the harness already has, then ``_after_configure``
    re-validates. Both classes below build on it.

``StepLimitedOpenHandsSdk``
    :class:`~rllm.harnesses.openhands_sdk.OpenHandsSdkHarness` plus a
    ``step_limit``. The engine reads that attribute to stamp
    ``MAX_TURNS_EXCEEDED`` (``agentflow_engine._turn_budget_termination_reason``)
    and the harness forwards it to the SDK as ``OPENHANDS_MAX_ITERATIONS``, so
    the budget the agent runs under and the one the reward shaping sees are the
    same number. Without it an agent that used every iteration is
    indistinguishable from one that finished -- ``ENV_DONE`` -- and the
    SWE-Master ``budget_reward_scale`` never applies.

``WorkflowMixin``
    Makes a CLI harness follow a workflow from :mod:`workflows`, chosen by
    name (``workflow``; ``None`` = no workflow, the plain harness). Three
    things go into the sandbox, mirroring what the Harbor experiment did with
    compose mounts and job-config knobs (``harbor-extension/experiments/aidlc``):

    1. the workflow documents, uploaded to ``container_dir`` -- outside the
       repository, so ``git diff`` cannot pick them up and the verifier's
       cleanup cannot trip over them;
    2. an instruction telling the agent where the documents are, placed
       before the task text (``instruction_position: prefix``) or after it
       (``suffix``, the Harbor arrangement);
    3. a replacement system prompt. This one is not optional for
       openhands-sdk: its default prompt carries a ``<PROBLEM_SOLVING_WORKFLOW>``
       section that prescribes its own procedure, and that outranks anything
       appended to the user message -- the Harbor run without it ignored the
       instruction.

    1 and 2 go through ``BaseCliHarness``'s ``write_configs`` /
    ``build_invocation`` and work for any CLI harness. 3 is the one
    harness-specific seam: a harness class sets ``supports_system_prompt`` and
    implements ``_system_prompt_env`` / ``_write_system_prompt``. The mixin
    also exposes the workflow's compliance scorer as ``evaluation_policy``,
    which ``rllm eval`` hands to ``SandboxTaskHooks`` (``rllm/eval/runner.py``).

``OpenHandsSdkWorkflow``
    The mixin on ``StepLimitedOpenHandsSdk``. Another harness gets the same
    one-class treatment (``class OpenCodeWorkflow(WorkflowMixin, ...)``); a
    workflow never needs a class.

All return ``None`` from ``run()`` like every CLI harness: the gateway
captures the LLM calls and the engine builds the Episode.
"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Task

from .workflows import WorkflowSpec, get_workflow

logger = logging.getLogger(__name__)

# Where the system prompt template lands in the sandbox. Next to the runner
# (``/opt/openhands-sdk-runner.py``), for the same reason: written per task,
# a few KB, never inside the task's repository.
_SYSTEM_PROMPT_REMOTE = "/opt/openhands-sdk-system-prompt.j2"


def _null(value):
    """No workflow: ``None``, or a ``none``/``null``/empty string from a caller that passes text."""
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null"):
        return None
    return value


class AgentKwargsMixin:
    """Honour ``rllm eval --agent-kwargs key=value,...`` on a CLI harness.

    ``SandboxedAgentFlow.configure`` consumes only the sandbox flags and
    returns the rest, so ``agent_kwargs`` would otherwise be warned about and
    dropped. Each key must be an attribute this harness already has
    (``step_limit``, ``enable_thinking``, ``workflow``, ``instruction_position``
    ...); an unknown one is an error rather than a silent no-op. Subclasses
    re-validate in ``_after_configure`` and call ``super()`` there.
    """

    def configure(self, overrides: dict) -> dict:
        leftovers = super().configure(overrides)
        kwargs = leftovers.pop("agent_kwargs", None) or {}
        for key, value in dict(kwargs).items():
            if not hasattr(self, key):
                raise ValueError(f"--agent-kwargs: {type(self).__name__} has no attribute {key!r}")
            setattr(self, key, value)
        self._after_configure()
        return leftovers

    def _after_configure(self) -> None:
        pass


class StepLimitedOpenHandsSdk(AgentKwargsMixin, OpenHandsSdkHarness):
    """openhands-sdk with an explicit iteration budget.

    One SDK iteration is one agent step (one LLM call, possibly several tool
    calls), and the gateway records one trace per LLM call, so the engine's
    trace count and the SDK's iteration count agree closely enough for the
    ``MAX_TURNS_EXCEEDED`` stamp.
    """

    step_limit: int = 50

    def _after_configure(self) -> None:
        super()._after_configure()
        self.step_limit = int(self.step_limit)

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        env = super().build_env(task, config)
        if self.step_limit and int(self.step_limit) > 0:
            env["OPENHANDS_MAX_ITERATIONS"] = str(int(self.step_limit))
        return env


class WorkflowMixin(AgentKwargsMixin):
    """A CLI harness made to follow the workflow named by ``workflow``.

    ``workflow`` is a key of :data:`workflows.WORKFLOWS`; ``None`` (or
    ``none``/``null`` from the CLI) runs the plain harness: nothing uploaded,
    the task text untouched, the harness's own system prompt, resolve rate
    only. Baseline and workflow arms thereby share one class and differ in
    this one attribute.

    ``docs_dir`` / ``container_dir`` / ``instruction_file`` /
    ``system_prompt_file`` are the spec's, read-only, the same in training
    and in ``rllm eval``.

    ``instruction_position`` says where the instruction goes relative to the
    task text: ``"prefix"`` puts it first, ``"suffix"`` (the default, as in the
    Harbor experiment) appends it. In run 2 (2026-09-29, suffix) the SWE-Gym
    prompt's six-step procedure (OpenHands' SWE-bench prompt, reused by
    SkyRL-v0) sat between the issue and the four-line
    AI-DLC suffix, and 86% of rollouts never opened the workflow document
    (reports/2026-09-30_aidlc_swegym_compliance.md); the recipe config sets
    ``prefix`` so the first thing after the issue-independent preamble the
    model reads is the workflow pointer.

    ``name`` is deliberately left at the harness's own (``"openhands-sdk"``):
    ``rllm.sandbox.agent_image`` keys the agent-image mount on that string,
    and a renamed harness would silently fall back to a per-task install. It
    is also the key into the spec's ``system_prompt`` and ``scorers``.

    ``workflow`` and ``instruction_position`` may be set per run through
    ``configure`` (``--agent-kwargs``, from ``AgentKwargsMixin``), on whatever
    CLI harness the mixin sits on.
    """

    workflow: str | None = None
    instruction_position: str = "suffix"
    INSTRUCTION_POSITIONS = ("prefix", "suffix")

    # Set by a harness class that can replace its agent's system prompt.
    supports_system_prompt: bool = False

    # Resolved by _resolve_workflow; None when there is no workflow.
    workflow_spec: WorkflowSpec | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._resolve_workflow()

    def _after_configure(self) -> None:
        super()._after_configure()
        self._resolve_workflow()

    # What the sandbox side reads, straight from the spec. Read-only, so an
    # ``--agent-kwargs docs_dir=...`` fails instead of being silently replaced.

    @property
    def docs_dir(self) -> Path | None:
        return self.workflow_spec.docs_dir if self.workflow_spec is not None else None

    @property
    def container_dir(self) -> str | None:
        return self.workflow_spec.container_dir if self.workflow_spec is not None else None

    @property
    def instruction_file(self) -> Path | None:
        return self.workflow_spec.instruction_file if self.workflow_spec is not None else None

    @property
    def system_prompt_file(self) -> Path | None:
        return self.workflow_spec.system_prompt.get(self.name) if self.workflow_spec is not None else None

    def _resolve_workflow(self) -> None:
        """``workflow`` -> its spec; fail before any sandbox exists."""
        self.workflow = _null(self.workflow)
        if self.instruction_position not in self.INSTRUCTION_POSITIONS:
            raise ValueError(f"instruction_position must be one of {self.INSTRUCTION_POSITIONS}, got {self.instruction_position!r}")
        if self.workflow is None:
            self.workflow_spec = None
            return

        spec = get_workflow(str(self.workflow))
        if not spec.container_dir.startswith("/"):
            raise ValueError(f"workflow {self.workflow!r}: container_dir must be absolute, got {spec.container_dir!r}")
        template = spec.system_prompt.get(self.name)
        if template is not None and not self.supports_system_prompt:
            raise ValueError(f"workflow {self.workflow!r}: {type(self).__name__} cannot replace its system prompt; register the workflow without one for harness {self.name!r}")
        if template is None:
            logger.warning("workflow %r has no system prompt for harness %r; the harness's own prompt stays", self.workflow, self.name)
        if self.name not in spec.scorers:
            logger.warning("workflow %r has no compliance scorer for harness %r; rllm eval reports resolve rate only", self.workflow, self.name)

        self.workflow_spec = spec
        self._validate_local_files()

    @property
    def evaluation_policy(self):
        """The workflow's compliance scorer for this harness, or ``None`` (per-task verifier alone).

        Read by ``rllm eval`` (``rllm/eval/runner.py``) and by train.py's
        ``_build_hooks``, so both score compliance the same way.
        """
        factory = self.workflow_spec.scorers.get(self.name) if self.workflow_spec is not None else None
        return factory() if factory is not None else None

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
        label = f"workflow {self.workflow!r}"
        if not self.docs_dir.is_dir():
            raise FileNotFoundError(f"{label}: docs dir not found: {self.docs_dir}")
        if not (self.docs_dir / self.workflow_spec.entry_doc).is_file():
            raise FileNotFoundError(f"{label}: docs dir has no {self.workflow_spec.entry_doc}: {self.docs_dir}")
        if not self._doc_entries():
            raise FileNotFoundError(f"{label}: docs dir has nothing to upload: {self.docs_dir}")
        # The instruction and the system prompt send the agent to the documents by
        # absolute path; one naming another location (a copied set, a changed
        # container_dir) would leave the uploaded documents where nothing points.
        entry = f"{self.container_dir.rstrip('/')}/{self.workflow_spec.entry_doc}"
        for name, path in (("instruction_file", self.instruction_file), ("system_prompt_file", self.system_prompt_file)):
            if path is None:
                continue
            if not path.is_file():
                raise FileNotFoundError(f"{label}: {name} not found: {path}")
            if entry not in path.read_text(encoding="utf-8"):
                raise ValueError(f"{label}: {name} never mentions {entry}, where the documents are uploaded: {path}")

    def _doc_entries(self) -> list[Path]:
        """Top-level entries of ``docs_dir`` that go into the container: all of it.

        ``docs_dir`` holds documents only (``workflows/<name>/docs``); the
        instruction and the system prompts sit beside it, not in it. Uploaded
        entry by entry so the layout is free: flat, or stage files under a
        subdirectory (``rule-details/``).
        """
        return sorted(p for p in self.docs_dir.iterdir() if not p.name.startswith("."))

    def _expected_doc_count(self) -> int:
        return sum(1 for p in self.docs_dir.rglob("*.md"))

    def instruction_text(self) -> str:
        return self.instruction_file.read_text(encoding="utf-8").strip() if self.instruction_file else ""

    def compose_instruction(self, task_instruction: str) -> str:
        """The user message: the workflow instruction before or after the task text."""
        text = self.instruction_text()
        if not text:
            return task_instruction
        if self.instruction_position == "prefix":
            return f"{text}\n\n{task_instruction.strip()}"
        return f"{task_instruction.rstrip()}\n\n{text}"

    # ------------------------------------------------------------------
    # Sandbox side
    # ------------------------------------------------------------------

    def build_env(self, task: Task, config: AgentConfig) -> dict[str, str]:
        env = super().build_env(task, config)
        if self.system_prompt_file is not None:
            env.update(self._system_prompt_env())
        return env

    def write_configs(
        self,
        sandbox: Sandbox,
        task: Task,
        config: AgentConfig,
        env: dict[str, str],
    ) -> None:
        super().write_configs(sandbox, task, config, env)
        if self.workflow_spec is None:
            return
        self._upload_docs(sandbox)
        if self.system_prompt_file is not None:
            self._write_system_prompt(sandbox, self.system_prompt_file.read_text(encoding="utf-8"))

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
            raise RuntimeError(f"workflow {self.workflow!r} docs check: unreadable find output {found!r}") from e
        if n != expected:
            raise RuntimeError(f"workflow {self.workflow!r} docs check: expected {expected} .md files under {target}, found {n}")

    def build_invocation(
        self,
        instruction: str,
        task: Task,
        config: AgentConfig,
    ) -> str:
        return super().build_invocation(self.compose_instruction(instruction), task, config)

    # ------------------------------------------------------------------
    # Harness-specific seam: the replacement system prompt
    # ------------------------------------------------------------------

    def _system_prompt_env(self) -> dict[str, str]:
        raise NotImplementedError(f"{type(self).__name__} cannot replace its system prompt")

    def _write_system_prompt(self, sandbox: Sandbox, text: str) -> None:
        raise NotImplementedError(f"{type(self).__name__} cannot replace its system prompt")


class OpenHandsSdkWorkflow(WorkflowMixin, StepLimitedOpenHandsSdk):
    """openhands-sdk with a turn budget, following ``workflow`` (``None``: the plain harness).

    The runner swaps the SDK's system prompt for the Jinja template at
    ``OPENHANDS_SDK_SYSTEM_PROMPT_PATH`` (``rllm/harnesses/tools/openhands_sdk_runner.py``).
    """

    supports_system_prompt = True

    def _system_prompt_env(self) -> dict[str, str]:
        return {"OPENHANDS_SDK_SYSTEM_PROMPT_PATH": _SYSTEM_PROMPT_REMOTE}

    def _write_system_prompt(self, sandbox: Sandbox, text: str) -> None:
        sandbox.exec(self._heredoc_write(_SYSTEM_PROMPT_REMOTE, text), timeout=60, user="root")
