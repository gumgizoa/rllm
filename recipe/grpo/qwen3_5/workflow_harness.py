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

    A workflow that needs tools in the sandbox (OpenSpec's CLI) also declares
    ``agent_image_extra`` (baked into an agent image of its own, read here as
    ``agent_image_extra``), ``sandbox_files`` and a ``setup_script``; they are
    uploaded and run after 1, before the agent starts, and a failed setup stops
    the rollout like a failed document upload does.

    1 and 2 go through ``BaseCliHarness``'s ``write_configs`` /
    ``build_invocation`` and work for any CLI harness. 3 is the one
    harness-specific seam: a harness class sets ``supports_system_prompt`` and
    implements ``_system_prompt_env`` / ``_write_system_prompt``. The mixin
    also exposes the workflow's compliance scorer as ``evaluation_policy``,
    which ``rllm eval`` hands to ``SandboxTaskHooks`` (``rllm/eval/runner.py``),
    and (``collect_patch``) returns what the run left in the sandbox -- the
    patch, the workflow's reports -- in ``episode.artifacts``, so compliance can
    be scored again from the saved episode (``run_artifacts.py``).

    Several workflows at once (``workflow=[none, aidlc_v4]``) route each task
    to a copy of the harness holding one of them; see the class docstring.

``OpenHandsSdkWorkflow``
    The mixin on ``StepLimitedOpenHandsSdk``. Another harness gets the same
    one-class treatment (``class OpenCodeWorkflow(WorkflowMixin, ...)``); a
    workflow never needs a class.

Like every CLI harness, the gateway captures the LLM calls and the engine
builds the trajectory; ``run()`` returns an Episode only to carry the
artifacts (``None`` with ``collect_patch`` off).
"""

from __future__ import annotations

import copy
import logging
import shlex
from pathlib import Path

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness
from rllm.sandbox.protocol import Sandbox
from rllm.types import AgentConfig, Episode, Task, Trajectory

from . import run_artifacts
from .workflows import NONE, WORKFLOW_KEY, WorkflowSpec, assign_workflow, get_workflow, parse_workflows

logger = logging.getLogger(__name__)

# Where the system prompt template lands in the sandbox. Next to the runner
# (``/opt/openhands-sdk-runner.py``), for the same reason: written per task,
# a few KB, never inside the task's repository.
_SYSTEM_PROMPT_REMOTE = "/opt/openhands-sdk-system-prompt.j2"
# A workflow's setup script, same reasoning; run once per task before the agent.
_SETUP_REMOTE = "/opt/rllm-workflow-setup.sh"
_SETUP_RC = "__RLLM_WORKFLOW_SETUP_RC="


def _flag(value) -> bool:
    """A boolean attribute set from ``--agent-kwargs`` text or from a config."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


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

    ``collect_patch`` (on by default, with or without a workflow) puts the
    patch, the files under the spec's ``output_dirs``, files written elsewhere
    under ``/tmp`` / ``container_dir`` and the workflow's ``fingerprint`` into
    ``episode.artifacts``; see :mod:`run_artifacts`. A failure to collect is
    recorded there (``patch_error``) and never fails the rollout.

    ``workflow``, ``instruction_position`` and ``collect_patch`` may be set per
    run through ``configure`` (``--agent-kwargs``, from ``AgentKwargsMixin``),
    on whatever CLI harness the mixin sits on.

    Several workflows (``workflow=[none, aidlc_v4, ...]``, ``none+aidlc_v4``
    from the CLI) make this harness a router. The engine shares one harness
    across concurrent rollouts, so the workflow cannot be an attribute switched
    per task; instead each workflow gets a copy of this harness holding that one
    workflow (``_routes``), built by the single-workflow path above, and
    ``run`` hands each task to the copy ``workflow_for(task)`` names: the
    task's ``metadata[WORKFLOW_KEY]`` when set, else ``assign_workflow`` over
    ``workflow`` with ``workflow_seed``. ``pinned_workflows`` adds copies for
    workflows only metadata may name (the validation set's), outside the random
    pool. What the hooks read off the harness before any task is known stays
    here: ``agent_image_extra`` (every copy's, joined) and
    ``evaluation_policy`` (``workflow_scoring.RoutedEvaluation``).
    """

    workflow: str | tuple[str, ...] | None = None
    workflow_seed: int = 0
    pinned_workflows: tuple[str, ...] = ()
    instruction_position: str = "suffix"
    INSTRUCTION_POSITIONS = ("prefix", "suffix")
    collect_patch: bool = True
    # Where a file the agent wrote outside the repository and the output dirs is looked for,
    # besides ``container_dir``.
    stray_roots: tuple[str, ...] = ("/tmp",)

    # Set by a harness class that can replace its agent's system prompt.
    supports_system_prompt: bool = False

    # Resolved by _resolve_workflow; None when there is no workflow, or several.
    workflow_spec: WorkflowSpec | None = None
    workflow_fingerprint: str | None = None
    # Route name -> the copy of this harness that runs it; empty for a single workflow.
    _routes: dict = {}

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

    @property
    def agent_image_extra(self) -> str:
        """The spec's extra bake lines, read by ``rllm.sandbox.agent_image`` when it builds the mount image.

        A workflow with extras gets an image of its own (the tag hashes them); no workflow, or one
        without extras, keeps the harness's plain image. A mix mounts one image for every task, so it
        carries every routed workflow's extras.
        """
        if self._routes:
            extras: list[str] = []
            for name in sorted(self._routes):
                extra = self._routes[name].agent_image_extra
                if extra and extra not in extras:
                    extras.append(extra)
            return "\n".join(extras)
        return self.workflow_spec.agent_image_extra if self.workflow_spec is not None else ""

    def _resolve_workflow(self) -> None:
        """``workflow`` -> its spec, or one copy per workflow for a mix; fail before any sandbox exists."""
        self.collect_patch = _flag(self.collect_patch)
        self.workflow_seed = int(self.workflow_seed)
        if self.instruction_position not in self.INSTRUCTION_POSITIONS:
            raise ValueError(f"instruction_position must be one of {self.INSTRUCTION_POSITIONS}, got {self.instruction_position!r}")
        pool = parse_workflows(self.workflow) or (NONE,)
        routes = (*pool, *(n for n in parse_workflows(self.pinned_workflows) if n not in pool))
        self._routes = {}
        if len(routes) > 1:
            self.workflow = pool
            self.workflow_spec = None
            self.workflow_fingerprint = None
            self._routes = {name: self._route_copy(name) for name in routes}
            return
        self.workflow = None if routes[0] == NONE else routes[0]
        if self.workflow is None:
            self.workflow_spec = None
            self.workflow_fingerprint = None
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
        self.workflow_fingerprint = spec.fingerprint(self.name)

    def _route_copy(self, name: str):
        """This harness, as configured so far, holding the one workflow ``name`` (``none``: no workflow)."""
        route = copy.copy(self)
        route.workflow = None if name == NONE else name
        route.pinned_workflows = ()
        route._resolve_workflow()
        return route

    def routes(self) -> dict:
        """Route name -> the harness that runs it; ``{name: self}`` for a single workflow (``none`` for none)."""
        return dict(self._routes) if self._routes else {self.workflow or NONE: self}

    def workflow_for(self, task) -> str:
        """The route ``task`` runs under: its ``metadata[WORKFLOW_KEY]``, else the hash pick over the pool.

        A task pinned to a workflow this harness does not route is an error, not a silent reroute.
        """
        pinned = (getattr(task, "metadata", None) or {}).get(WORKFLOW_KEY)
        if not self._routes:
            name = self.workflow or NONE
            if pinned is not None and pinned != name:
                raise ValueError(f"task {getattr(task, 'id', '?')!r} is pinned to workflow {pinned!r}, but this harness runs only {name!r}")
            return name
        if pinned is not None:
            if pinned not in self._routes:
                raise ValueError(f"task {getattr(task, 'id', '?')!r} is pinned to workflow {pinned!r}; routed: {sorted(self._routes)}")
            return pinned
        return assign_workflow(str(task.id), self.workflow, self.workflow_seed)

    @property
    def evaluation_policy(self):
        """The workflow's compliance scorer for this harness, or ``None`` (per-task verifier alone).

        Read by ``rllm eval`` (``rllm/eval/runner.py``) and by train.py's
        ``_build_hooks``, so both score compliance the same way. A mix
        always routes (``RoutedEvaluation``), so every task carries
        ``workflow/<name>/resolved``.
        """
        if self._routes:
            from .workflow_scoring import RoutedEvaluation

            return RoutedEvaluation(
                {name: route.evaluation_policy for name, route in self._routes.items()},
                self.workflow_for,
                reward_signals={name: (route.workflow_spec.reward_signal if route.workflow_spec is not None else None) for name, route in self._routes.items()},
            )
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
        for remote, local in self.workflow_spec.sandbox_files.items():
            if not remote.startswith("/"):
                raise ValueError(f"{label}: sandbox_files target must be absolute, got {remote!r}")
            if not local.exists():
                raise FileNotFoundError(f"{label}: sandbox_files source not found: {local}")
        setup = self.workflow_spec.setup_script
        if setup is not None and not setup.is_file():
            raise FileNotFoundError(f"{label}: setup_script not found: {setup}")

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
        if self.workflow_spec is not None:
            self._upload_docs(sandbox)
            if self.system_prompt_file is not None:
                self._write_system_prompt(sandbox, self.system_prompt_file.read_text(encoding="utf-8"))
            self._upload_sandbox_files(sandbox)
            self._run_setup(sandbox)
        # Last write before the agent starts: the marker's mtime separates the agent's files
        # from ours, and it holds the commit the patch is taken against.
        if self.collect_patch:
            sandbox.exec(run_artifacts.start_command(task.metadata.get("workdir")), timeout=60, user="root")

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

    def _upload_sandbox_files(self, sandbox: Sandbox) -> None:
        """The spec's ``sandbox_files``, each target replaced as a whole (a warm sandbox keeps nothing stale)."""
        for remote, local in sorted(self.workflow_spec.sandbox_files.items()):
            target = remote.rstrip("/")
            parent = target.rsplit("/", 1)[0] or "/"
            sandbox.exec(f"rm -rf {shlex.quote(target)} && mkdir -p {shlex.quote(parent)}", timeout=30, user="root")
            if local.is_dir():
                sandbox.upload_dir(str(local), target)
            else:
                sandbox.upload_file(str(local), target)

    def _run_setup(self, sandbox: Sandbox) -> None:
        """Run the spec's ``setup_script`` as root; a non-zero exit stops the rollout.

        Same reasoning as the documents check: a rollout whose tools never came up would score as a
        policy that ignored the workflow. The script's own output tail goes into the error.
        """
        setup = self.workflow_spec.setup_script
        if setup is None:
            return
        sandbox.exec(self._heredoc_write(_SETUP_REMOTE, setup.read_text(encoding="utf-8")), timeout=60, user="root")
        out = str(sandbox.exec(f"bash {shlex.quote(_SETUP_REMOTE)} 2>&1; echo {_SETUP_RC}$?", timeout=300, user="root") or "")
        head, _, rc = out.rpartition(_SETUP_RC)
        if rc.strip() != "0":
            tail = head.strip()[-1500:]
            raise RuntimeError(f"workflow {self.workflow!r} setup failed (exit {rc.strip() or '?'}):\n{tail}")

    def build_invocation(
        self,
        instruction: str,
        task: Task,
        config: AgentConfig,
    ) -> str:
        return super().build_invocation(self.compose_instruction(instruction), task, config)

    def run(self, task: Task, config: AgentConfig, *, env: Sandbox) -> Episode | None:
        """The harness's run, then what it left in the sandbox, before the verifier sees it.

        A mix hands the whole rollout to the copy holding the task's workflow.
        """
        if self._routes:
            return self._routes[self.workflow_for(task)].run(task, config, env=env)
        episode = super().run(task, config, env=env)
        if not self.collect_patch:
            return episode
        if episode is None:
            episode = Episode(task=task.metadata, trajectories=[Trajectory(name=self.name, steps=[])])
        episode.artifacts.update(self._collect_run_artifacts(env, task))
        return episode

    def _collect_run_artifacts(self, sandbox: Sandbox, task: Task) -> dict:
        spec = self.workflow_spec
        output_dirs = spec.output_dirs if spec is not None else ()
        workdir = task.metadata.get("workdir")
        art: dict = {"workflow": {"name": self.workflow, "sha256": self.workflow_fingerprint}}
        if spec is not None:
            art["workflow_outputs"] = {}
        command = run_artifacts.collect_command(
            workdir,
            output_dirs,
            stray_roots=(*self.stray_roots, *((self.container_dir,) if spec is not None else ())),
            stray_skip=(self.stdout_log_path, *((workdir,) if workdir else ())),
        )
        try:
            art.update(run_artifacts.parse(sandbox.exec(command, timeout=180, user="root")))
        except Exception as e:
            logger.warning("%s: collecting the run's artifacts failed for %s: %s", type(self).__name__, getattr(task, "id", "?"), e)
            art["patch_error"] = f"collection failed: {e}"[:500]
        return art

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
