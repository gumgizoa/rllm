"""Evaluate every rubric item against one run: Run + Collected -> results -> scores.

Two passes, because order checks need to know whether an artifact write was substantive:

1. every item except ``order`` kinds; then the quality of each artifact (structure x content of the
   items targeting it, :func:`aggregate.artifact_quality`);
2. the ``order`` items, with that quality in ``ctx.quality``.

Per item: ``applies_when`` false -> ``not_applicable``; an input the mode cannot have (offline: no
diff / base tree) -> ``unavailable``; otherwise the kind's function. A check that raises is
``fail`` and counted in ``engine_errors`` -- nothing the agent writes can make scoring throw.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import aggregate, checks, refs
from . import facts as F
from .context import Collected, EvalContext, Facts, Result
from .schema import Item, Rubric
from .trace.model import Run

logger = logging.getLogger(__name__)

SECOND_PASS = {"order"}


@dataclass
class Report:
    results: dict[str, Result]
    scores: aggregate.Scores
    facts: Facts
    engine_errors: int = 0
    errors: list[str] = field(default_factory=list)
    cache: dict = field(default_factory=dict)  # the checks' shared state (``EvalContext.cache``)


def _offline_missing(item: Item, ctx: EvalContext) -> str | None:
    c = ctx.collected
    need = set(item.availability) | set(checks.get(item.check.kind).availability if item.check.kind != "unimplemented" else ())
    if "diff" in need and c.diff is None:
        return "no diff"
    if "base_tree" in need and c.base_present is None:
        return "no base tree"
    if "sandbox_file" in need and _unreplayable(item, ctx):
        return "artifact written but its content cannot be replayed"
    return None


def _unreplayable(item: Item, ctx: EvalContext) -> bool:
    """Offline only: the trace wrote the item's artifact, yet its final content is unknown to the replay.

    An artifact the run never wrote is absent exactly as it would be online, so its items fail; only a
    write the replay cannot reconstruct (an unparsed heredoc, a computed path) leaves nothing to judge.
    """
    if ctx.mode != "offline" or item.target.type != "artifact":
        return False
    art = ctx.rubric.artifacts.get(item.target.ref)
    if art is None or ctx.facts.artifact_paths.get(art.id):
        return False
    for path in F.location_paths(ctx.rubric, ctx.facts, ctx.collected, art):
        if any(path == r or path.startswith(r.rstrip("/") + "/") for r in ctx.collected.snapshot):
            continue
        evs = ctx.facts.writes.get(path) or []
        if evs and evs[-1].content is None and evs[-1].op not in ("delete", "move_out"):
            return True
    return False


def evaluate_item(item: Item, ctx: EvalContext, errors: list[str]) -> Result:
    if item.check.kind == "unimplemented":
        return Result.not_applicable(item, "unimplemented kind")
    try:
        if item.applies_when is not None and not refs.predicate(ctx, item.applies_when):
            return Result.not_applicable(item, "applies_when false")
        missing = _offline_missing(item, ctx)
        if missing:
            if ctx.mode == "offline":
                return Result.unavailable(item, missing)
            return Result.no(item, f"input missing online: {missing}")
        res = checks.get(item.check.kind).fn(item, ctx)
        res.score = max(0.0, min(1.0, float(res.score)))
        return res
    except Exception as e:  # noqa: BLE001 -- see module docstring
        errors.append(f"{item.id}: {type(e).__name__}: {e}")
        logger.debug("check %s raised", item.id, exc_info=True)
        return Result.no(item, f"engine error: {type(e).__name__}")


def evaluate(rubric: Rubric, run: Run, collected: Collected) -> Report:
    errors: list[str] = []
    try:
        facts = F.build(rubric, run, collected)
    except Exception as e:  # noqa: BLE001
        logger.warning("facts failed for %s", run.instance_id, exc_info=True)
        errors.append(f"facts: {type(e).__name__}: {e}")
        facts = Facts(n_steps=len(run.steps))
    ctx = EvalContext(rubric=rubric, run=run, collected=collected, facts=facts)
    results: dict[str, Result] = {}
    for it in rubric.items:
        if it.check.kind not in SECOND_PASS:
            results[it.id] = evaluate_item(it, ctx, errors)
    ctx.quality = aggregate.artifact_quality(rubric, results)
    for it in rubric.items:
        if it.check.kind in SECOND_PASS:
            results[it.id] = evaluate_item(it, ctx, errors)
    scores = aggregate.score(rubric, results, engine_errors=len(errors))
    return Report(results=results, scores=scores, facts=facts, engine_errors=len(errors), errors=errors, cache=ctx.cache)


def signals(report: Report, prefix: str) -> dict[str, float]:
    """``{prefix}/compliance`` (the reward signal; ``{prefix}/<scoring.total>`` under ``kind_matrix``), one
    per signal, diagnostics, and with ``item_signals`` every scored item under its id."""
    out = {f"{prefix}/{report.scores.total_name}": float(report.scores.compliance)}
    out.update({f"{prefix}/{k}": float(v) for k, v in report.scores.signals.items()})
    out.update({f"{prefix}/{k}": float(v) for k, v in report.scores.diagnostics.items()})
    out.update({f"{prefix}/{k}": float(v) for k, v in report.scores.items.items()})
    return out
