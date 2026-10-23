"""Evaluation layers: per-run pass rates of groups of rubric items, reported next to the reward signals.

A layers file (``layers.yaml``) assigns items to the layers an evaluation reports on -- for the SDLC
instruction-following study: ``L1`` (a template the training workflows also reward), ``L1C`` (an
instruction that runs against a training workflow's rule or document), ``L2F`` / ``L2M`` (a template
no training workflow rewards; ``M`` when a training document shows it or it extends a trained
template). It never changes the rubric: ``compliance`` and the other signals stay exactly as the
rubric scores them, and items absent from the file belong to no layer::

    rubric_sha256: <sha256 of the rubric.yaml the file was built for>
    items:
      <item id>: {layer: L2F, requirement: must}
      <item id>: {layer: L2M, requirement: must, when: {section_is_none: {artifact: a4, section: Deviations from Plan}}}

``requirement`` is the item's level for the evaluation, which may differ from its reward weight in the
rubric; ``when`` excludes the item from the layer when false (``section_is_none``, or any refs predicate);
other keys (``template``) are carried for reading and not used here.
Signals per layer ``L``, from items scored ``pass`` / ``fail`` (score in [0, 1]), unweighted:

    {prefix}/layer/L          mean over the layer's must items
    {prefix}/layer_reached/L  the same over items whose stage the run reached (its artifact exists,
                              or its stage document was read; global items always count)
    {prefix}/layer_should/L   mean over the layer's should items (a diagnostic)

A layer with no scored item in a run is left out, as a signal is in ``aggregate``.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import yaml

from . import markdown as M
from . import refs
from .context import Collected, EvalContext, Result
from .schema import Rubric, RubricError
from .trace.model import Run

SCORED = ("pass", "fail")
REQUIREMENTS = ("must", "should")


def rubric_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: str | Path, rubric: Rubric, rubric_path: str | Path | None = None) -> dict[str, dict]:
    """The file's ``items``, checked against the rubric: every id exists, every requirement is known,
    and (with ``rubric_path``) the rubric is the one the file was built for."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    if rubric_path is not None and data.get("rubric_sha256") != rubric_sha256(rubric_path):
        raise RubricError(f"{path}: built for another rubric.yaml (rubric_sha256 differs); rebuild it")
    ids = {it.id for it in rubric.items}
    items = data.get("items") or {}
    errors = [f"{i}: not a rubric item" for i in items if i not in ids]
    errors += [f"{i}: requirement {v.get('requirement')!r}" for i, v in items.items() if v.get("requirement") not in REQUIREMENTS]
    errors += [f"{i}: no layer" for i, v in items.items() if not v.get("layer")]
    if errors:
        raise RubricError(f"{path}: " + "; ".join(errors[:10]))
    return items


def _section_is_none(ctx: EvalContext, arg: dict) -> bool:
    """The section's whole body says "nothing here" (a bare ``- none`` list item, as AI-DLC's
    ``## Deviations from Plan`` skeleton offers)."""
    text = ctx.artifact_text(arg["artifact"], arg.get("state", "final"))
    body = refs.section_of(text, arg["section"])
    if body is None:
        return False
    lines = [ln.strip().lstrip("-*+ ").strip() for ln in body.splitlines() if ln.strip()]
    return len(lines) == 1 and M.is_none(lines[0])


def _when(ctx: EvalContext, cond) -> bool:
    if not cond:
        return True
    if isinstance(cond, dict) and "section_is_none" in cond:
        return _section_is_none(ctx, cond["section_is_none"])
    return refs.predicate(ctx, cond)


def _reached(ctx: EvalContext, item) -> bool:
    if item.stage == "global":
        return True
    if item.target.type == "artifact" and ctx.facts.artifact_paths.get(item.target.ref):
        return True
    stage = next((s for s in ctx.rubric.stages if s.id == item.stage), None)
    if stage is None:
        return False
    if any(ctx.facts.artifact_paths.get(a) for a in stage.artifacts):
        return True
    return bool(stage.doc and ctx.facts.doc_reads.get(stage.doc))


def signals(rubric: Rubric, run: Run, collected: Collected, report, layers: dict[str, dict], prefix: str) -> dict[str, float]:
    """``{prefix}/layer*/<L>`` for one run's engine ``report`` (see the module docstring)."""
    ctx = EvalContext(rubric=rubric, run=run, collected=collected, facts=report.facts)
    by_id = {it.id: it for it in rubric.items}
    acc: dict[tuple[str, str], list[float]] = defaultdict(list)
    for iid, spec in layers.items():
        r: Result | None = report.results.get(iid)
        if r is None or r.status not in SCORED:
            continue
        try:
            if not _when(ctx, spec.get("when")):
                continue
            reached = _reached(ctx, by_id[iid])
        except Exception:  # noqa: BLE001 -- agent-written artifacts: a predicate that cannot be evaluated drops the item
            continue
        lay, req = str(spec["layer"]), str(spec["requirement"])
        score = float(r.score)
        if req == "must":
            acc[("layer", lay)].append(score)
            if reached:
                acc[("layer_reached", lay)].append(score)
        else:
            acc[("layer_should", lay)].append(score)
    return {f"{prefix}/{kind}/{lay}": sum(v) / len(v) for (kind, lay), v in sorted(acc.items()) if v}


__all__ = ["load", "rubric_sha256", "signals"]
