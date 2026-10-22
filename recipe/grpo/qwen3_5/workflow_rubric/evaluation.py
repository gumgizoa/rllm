"""``RubricEvaluation``: the ``workflow_scoring.ComplianceEvaluation`` a generated verifier's ``eval.py`` subclasses.

A workflow's ``reward/eval.py`` is two lines::

    class Evaluation(RubricEvaluation):
        def __init__(self):
            super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="spec_kit")

Why not ``ComplianceEvaluation(collect, score, name)`` as AI-DLC's hand-written scorer does:

* ``collect(sandbox)`` gets neither the task nor the run, and this collector needs both: the
  workdir and base SHA (to diff the repository and ask what existed before the agent), and the
  paths the run used (runner scripts, test targets) to ask about. The base SHA has to be read at
  ``resolve`` time -- before ``hide_git_history`` swaps ``.git`` for a one-commit stand-in and
  before the agent can commit -- so ``resolve`` builds a :class:`RubricEvaluator` per rollout
  carrying that rollout's :class:`~.collect.TaskInfo`. The policy object is shared by every
  rollout and holds only the rubric.
* A scorer that fails returns the verifier's output without the signal, and in ``mul`` mode a
  missing signal leaves the verifier reward untouched -- an escape from the compliance term for
  any agent that can make scoring throw. Here everything after the episode is parsed is
  fail-safe: a failure emits ``{prefix}/compliance`` 0.0 and ``{prefix}/engine_errors`` 1.0. The
  only case that leaves the output alone is a harness with no trace front end, an
  infrastructure error the agent cannot cause.

As in ``workflow_scoring``, the verifier's ``reward``, ``is_correct`` and ``metadata`` pass through
unchanged; the signals are appended. ``extra`` runs legacy ``(collect, score)`` scorers alongside
(e.g. the hand-written ``aidlc/*`` next to the generated ``aidlc_gen/*``), each in its own
``try`` so neither can take the other down.
"""

from __future__ import annotations

import importlib
import logging
import math
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from recipe.grpo.qwen3_5.workflow_scoring import ComplianceEvaluation, ComplianceEvaluator
from rllm.eval.types import EvalOutput, Signal
from rllm.hooks import FromTaskEvaluation

from . import checks, schema
from . import collect as C
from .collect import TaskInfo
from .context import Collected
from .schema import Rubric
from .trace.model import Run

logger = logging.getLogger(__name__)

# A legacy scorer run next to the rubric: (collect(sandbox), score(task, episode, data)[, from_outputs(outputs)]).
Extra = tuple
# The hooks a workflow's evaluation may pass: what the task and episode give its checks, and the signals it
# derives from a finished report (``Report.cache`` holds what its checks computed).
Inputs = Callable[[Any, Any], dict[str, Any]]
Post = Callable[[Any], dict[str, float]]


def _engine():
    """The engine module (imported on use: it pulls in every check kind)."""
    from . import engine

    return engine


def _episode():
    """The rLLM-episode front end (``trace.episode``)."""
    from .trace import episode

    return episode


class UnknownHarness(ValueError):
    """The episode came from a harness with no trace front end: an infrastructure error."""


def failure_signals(prefix: str, total: str = "compliance") -> dict[str, float]:
    """What a run gets when scoring it failed: the reward signal at 0, the failure counted."""
    return {f"{prefix}/{total}": 0.0, f"{prefix}/engine_errors": 1.0}


def total_name(rubric: Rubric) -> str:
    """The reward signal's name: ``compliance``, or ``scoring.total`` under the ``kind_matrix`` aggregate."""
    s = rubric.scoring or {}
    return (s.get("total") or "score") if s.get("aggregate") == "kind_matrix" else "compliance"


def _finite(v: Any) -> float:
    f = float(v)
    return f if math.isfinite(f) else 0.0


def parse_run(episode: Any, instance_id: str = "") -> Run:
    """Episode -> Run; :class:`UnknownHarness` when no front end parses this harness's tool calls."""
    E = _episode()
    frontend_for = getattr(E, "frontend_for", None)
    if frontend_for is not None:
        try:
            frontend_for(episode)
        except ValueError as e:
            raise UnknownHarness(str(e)) from None
        return E.episode_to_run(episode, instance_id=instance_id)
    try:
        return E.episode_to_run(episode, instance_id=instance_id)
    except ValueError as e:  # no frontend_for to ask first: the contract's ValueError is the unknown harness
        raise UnknownHarness(str(e)) from None


def rubric_signals(rubric: Rubric, run: Run, collected: Collected, prefix: str, post: Post | None = None) -> dict[str, float]:
    """The engine's signals for one run, the reward signal clamped to [0, 1], plus collection diagnostics
    and what ``post`` derives from the report (never overriding the engine's)."""
    eng = _engine()
    report = eng.evaluate(rubric, run, collected)
    out = {str(k): _finite(v) for k, v in eng.signals(report, prefix).items()}
    key = f"{prefix}/{total_name(rubric)}"
    out[key] = min(1.0, max(0.0, out.get(key, 0.0)))
    if post is not None:
        for k, v in post(report).items():
            out.setdefault(f"{prefix}/{k}", _finite(v))
    out[f"{prefix}/collect_errors"] = float(len(collected.errors))
    return out


class RubricEvaluator(ComplianceEvaluator):
    """One rollout's verifier with the rubric's ``{prefix}/*`` signals appended; holds that rollout's task info."""

    def __init__(self, inner, sandbox, rubric: Rubric, prefix: str, info: TaskInfo, extra: Iterable[Extra] = (), inputs: Inputs | None = None, post: Post | None = None):
        super().__init__(inner, sandbox, self._collect, self._score, prefix)
        self.rubric = rubric
        self.prefix = prefix
        self.info = info
        self.extra = list(extra)
        self.inputs = inputs
        self.post = post

    # The (collect, score) pair ComplianceEvaluator expects, for callers that use it directly;
    # evaluate() below runs the same steps with the parsed run available to collect.
    def _collect(self, sandbox) -> Collected:
        return C.collect(sandbox, self.rubric, self.info, None)

    def _score(self, task, episode, collected: Collected) -> dict[str, float]:
        if self.inputs is not None:
            collected.inputs = self.inputs(task, episode)
        return rubric_signals(self.rubric, parse_run(episode, str(getattr(task, "id", "") or "")), collected, self.prefix, self.post)

    def evaluate(self, task, episode) -> EvalOutput:
        tid = str(getattr(task, "id", "") or "")
        run: Run | None = None
        collected: Collected | None = None
        try:
            run = parse_run(episode, tid)
        except UnknownHarness as e:
            logger.warning("%s compliance: %s; verifier output only", self.name, e)
            return self.inner.evaluate(task, episode)
        except Exception:
            logger.warning("%s compliance: episode of %s could not be parsed; compliance 0", self.name, tid, exc_info=True)
        if run is not None:
            try:
                collected = C.collect(self.sandbox, self.rubric, self.info, run)
            except Exception:  # collect never raises by design; a bug there still scores 0, not "no signal"
                logger.warning("%s compliance: collection raised for %s; compliance 0", self.name, tid, exc_info=True)
        extra_data = self._collect_extra()
        out = self.inner.evaluate(task, episode)
        signals = failure_signals(self.prefix, total_name(self.rubric))
        if run is not None and collected is not None:
            try:
                if self.inputs is not None:
                    collected.inputs = self.inputs(task, episode)
                signals = rubric_signals(self.rubric, run, collected, self.prefix, self.post)
            except Exception:
                logger.warning("%s compliance: scoring failed for %s; compliance 0", self.name, tid, exc_info=True)
        for name, value in self._score_extra(task, episode, extra_data).items():
            signals.setdefault(name, value)
        appended = [Signal(name, float(value)) for name, value in signals.items()]
        return EvalOutput(reward=out.reward, is_correct=out.is_correct, signals=list(out.signals) + appended, metadata=out.metadata)

    def _collect_extra(self) -> list[tuple[bool, Any]]:
        data = []
        for collect, *_rest in self.extra:
            try:
                data.append((True, collect(self.sandbox)))
            except Exception as e:
                logger.warning("%s compliance: extra scorer collection failed: %s", self.name, e)
                data.append((False, None))
        return data

    def _score_extra(self, task, episode, data: list[tuple[bool, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for (_collect, score, *_rest), (ok, d) in zip(self.extra, data, strict=True):
            if not ok:
                continue
            try:
                got = {str(k): float(v) for k, v in score(task, episode, d).items()}
            except Exception:
                logger.warning("%s compliance: extra scorer failed for %s", self.name, getattr(task, "id", "?"), exc_info=True)
                continue
            for k, v in got.items():
                out.setdefault(k, v)
        return out


def _per_rollout(*_args, **_kwargs):
    raise TypeError("RubricEvaluation scores through the per-rollout RubricEvaluator its resolve() returns")


class RubricEvaluation(ComplianceEvaluation):
    """A workflow's rubric verifier as an evaluation policy for ``SandboxTaskHooks``.

    rubric_path  the workflow's ``reward/rubric.yaml``; loaded and validated here (schema and every
                 item's kind parameters), so a malformed rubric fails at construction
    prefix       signal name prefix (``spec_kit`` -> ``spec_kit/compliance``)
    plugins      module names (or modules) whose import registers the workflow's ``<wf>.<name>``
                 check kinds, imported before validation
    extra        legacy ``(collect, score[, from_outputs])`` scorers run independently next to the rubric
    inputs       ``(task, episode) -> dict`` put in ``Collected.inputs`` before scoring, for the workflow's
                 own checks (the issue text, the recorded patch, ...)
    post         ``report -> {name: value}``: signals the workflow derives from the finished report

    A saved episode is scored offline (``scripts/rescore_compliance.py``) through ``from_outputs`` and
    ``score``: the collected ``workflow_outputs`` stand for the sandbox's files (online semantics: a
    file missing there is missing), and each extra scorer with a ``from_outputs`` gets its own data.
    """

    def __init__(self, rubric_path: str | Path, prefix: str, plugins: Iterable[Any] = (), extra: Iterable[Extra] = (), inputs: Inputs | None = None, post: Post | None = None):
        super().__init__(_per_rollout, _per_rollout, prefix)
        self.rubric_path = Path(rubric_path)
        self.prefix = prefix
        self.extra = tuple(extra)
        self.inputs = inputs
        self.post = post
        self.from_outputs = self._from_outputs
        self.score = self._offline_score
        # Kept by name: the registration has to be repeated wherever this object lands (see
        # ``_load_plugins``), and a module object would not pickle anyway.
        self.plugins = tuple(p if isinstance(p, str) else p.__name__ for p in plugins)
        self._load_plugins()
        self.rubric = schema.load(self.rubric_path)
        checks.validate_params(self.rubric)
        _engine()  # a missing module is an error now, not a 0 on every rollout
        _episode()

    def _from_outputs(self, outputs: dict[str, str]) -> tuple[Collected, list[tuple[bool, Any]]]:
        extra = []
        for e in self.extra:
            try:
                extra.append((len(e) > 2 and e[2] is not None, e[2](outputs) if len(e) > 2 and e[2] is not None else None))
            except Exception as err:
                logger.warning("%s compliance: extra scorer from_outputs failed: %s", self.prefix, err)
                extra.append((False, None))
        return Collected(files=dict(outputs)), extra

    def _offline_score(self, task, episode, data) -> dict[str, float]:
        """A saved episode's signals: the rubric's, then each extra scorer's (never overriding)."""
        collected, extra = data
        if self.inputs is not None:
            collected.inputs = self.inputs(task, episode)
        out = rubric_signals(self.rubric, parse_run(episode, str(getattr(task, "id", "") or "")), collected, self.prefix, self.post)
        for e, (ok, d) in zip(self.extra, extra, strict=True):
            if ok:
                for k, v in e[1](task, episode, d).items():
                    out.setdefault(str(k), float(v))
        return out

    def _load_plugins(self) -> None:
        """Register the workflow's ``<wf>.*`` check kinds in *this* process.

        ``checks.REGISTRY`` is a module global, filled as a side effect of importing the plugin
        module. Training pickles the evaluation policy into the Ray actor that runs the sandbox
        hooks (``SandboxTaskHooks`` -> ``VerlTaskRunner``), and unpickling does not run
        ``__init__``, so without this the actor scores every plugin-kind item as an engine error
        (``checks.get`` raises ``RubricError``): measured 2026-10-16, speckit_bug 19 and openspec_ff
        61-63 errors on every rollout, exactly the unconditional plugin items. Importing an
        already-imported module is a dict lookup, so calling this on every resolve is free.
        """
        for p in self.plugins:
            importlib.import_module(p)

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._load_plugins()

    def resolve(self, task, sandbox, kind, config):
        self._load_plugins()
        inner = FromTaskEvaluation.resolve(self, task, sandbox, kind, config)
        if sandbox is None:
            return inner
        return RubricEvaluator(inner, sandbox, self.rubric, self.prefix, C.task_info(sandbox, task), self.extra, self.inputs, self.post)


__all__ = ["RubricEvaluation", "RubricEvaluator", "UnknownHarness", "failure_signals", "parse_run", "rubric_signals", "total_name"]
