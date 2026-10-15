"""Item results -> stage scores -> signals, by the rubric's ``scoring`` block.

The block's shape is shared; its values are the workflow's own::

    scoring:
      item_weight: {must: 1.0, should: 0.25}
      stage: {formula: sigma_kappa}        # sigma_kappa (default) | linear | band8_5_2 (legacy AI-DLC)
      substantive_threshold: 0.5           # an artifact write counts for order only above this quality
      signals: [order, process, "stage:*"]
      compliance: mean                     # the reward signal = mean of the signals present

``sigma_kappa``: s_k = min(cap_k, sigma_k * kappa_k), where sigma_k is the weighted pass rate of the
stage's ``structure`` items (a multiplier: headings and labels alone earn nothing), kappa_k that of
its ``content`` and ``evidence`` items, and cap_k the smallest ``cap_stage`` among its failed gate
items; a failed ``zero_stage`` gate makes the stage 0. Gate items are gates only -- they do not
also count in sigma or kappa. ``not_applicable`` and ``unavailable`` items leave both numerator
and denominator.

``log_only`` items are evaluated and reported (``log_only_rate``, ``adapter_rate``) but never scored.
Global items (``stage: global``) feed two signals: ``order`` (kind ``order``) and ``process``
(everything else global). A signal with no applicable items is left out of the mean.

``process_scale: stage_mean`` makes ``process`` the global items' pass rate times the mean stage
score. Most global items are prohibitions and write rules that a run doing nothing satisfies; scaled,
they act like the structure items -- a multiplier on the work they govern, never credit by
themselves (a frontmatter stub would otherwise keep a whole signal, 1/7 of the reward, for not
installing anything). The unscaled rate is the ``process_rate`` diagnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .context import Result
from .schema import Item, Rubric

DEFAULT_SCORING = {
    "item_weight": {"must": 1.0, "should": 0.25},
    "stage": {"formula": "sigma_kappa"},
    "substantive_threshold": 0.5,
    "signals": ["order", "process", "stage:*"],
    "compliance": "mean",
}
SCORED = ("pass", "fail")


def scoring_of(rubric: Rubric) -> dict:
    s = {**DEFAULT_SCORING, **(rubric.scoring or {})}
    s["item_weight"] = {**DEFAULT_SCORING["item_weight"], **(rubric.scoring or {}).get("item_weight", {})}
    s["stage"] = {**DEFAULT_SCORING["stage"], **(rubric.scoring or {}).get("stage", {})}
    return s


def weight(item: Item, scoring: dict) -> float:
    return float(item.weight) * float(scoring["item_weight"].get(item.requirement, 1.0))


def _wmean(pairs: list[tuple[float, float]]) -> float | None:
    den = sum(w for _, w in pairs)
    return None if den <= 0 else sum(s * w for s, w in pairs) / den


@dataclass
class StageScore:
    score: float
    sigma: float | None
    kappa: float | None
    cap: float
    zeroed: bool
    n_items: int


def group_score(items: list[Item], results: dict[str, Result], scoring: dict) -> StageScore:
    """Score one group of items (a stage, or the items targeting one artifact)."""
    formula = scoring["stage"].get("formula", "sigma_kappa")
    struct, cont, cap, zeroed, n = [], [], 1.0, False, 0
    for it in items:
        r = results.get(it.id)
        if it.log_only or r is None or r.status not in SCORED:
            continue
        n += 1
        w = weight(it, scoring)
        if it.gate:
            if r.status == "fail":
                if it.gate.get("zero_stage"):
                    zeroed = True
                if it.gate.get("cap_stage") is not None:
                    cap = min(cap, float(it.gate["cap_stage"]))
            continue
        (struct if it.cls == "structure" else cont).append((r.score, w))
    sigma, kappa = _wmean(struct), _wmean(cont)
    if n == 0:
        return StageScore(0.0, None, None, cap, zeroed, 0)
    if formula == "linear":
        base = _wmean(struct + cont) or 0.0
    elif formula == "band8_5_2":
        failed = sum(1 for it in items if not it.gate and it.cls != "structure" and results.get(it.id) and results[it.id].status == "fail")
        base = 1.0 if failed == 0 else 4 / 7 if failed == 1 else 2 / 7
    else:
        base = (1.0 if sigma is None else sigma) * (1.0 if kappa is None else kappa)
    score = 0.0 if zeroed else min(cap, base)
    return StageScore(score, sigma, kappa, cap, zeroed, n)


def artifact_quality(rubric: Rubric, results: dict[str, Result]) -> dict[str, float]:
    """Artifact id -> structure x content score of the non-order items targeting it."""
    scoring = scoring_of(rubric)
    out = {}
    for aid in rubric.artifacts:
        items = [i for i in rubric.items if i.target.type == "artifact" and i.target.ref == aid and i.check.kind != "order" and i.cls != "evidence" and not i.log_only]
        out[aid] = group_score(items, results, scoring).score if items else 0.0
    return out


@dataclass
class Scores:
    signals: dict[str, float]
    compliance: float
    stages: dict[str, StageScore]
    diagnostics: dict[str, float] = field(default_factory=dict)


def score(rubric: Rubric, results: dict[str, Result], engine_errors: int = 0) -> Scores:
    scoring = scoring_of(rubric)
    stages = {st.id: group_score(rubric.items_for(st.id), results, scoring) for st in rubric.stages}
    glob = [i for i in rubric.items_for("global") if not i.log_only]
    signals: dict[str, float] = {}
    process_rate = None
    for name in scoring["signals"]:
        if name == "stage:*":
            for sid, s in stages.items():
                if s.n_items:
                    signals[f"stage.{sid}"] = s.score
        elif name == "order":
            pairs = [(results[i.id].score, weight(i, scoring)) for i in glob if i.check.kind == "order" and results.get(i.id) and results[i.id].status in SCORED]
            v = _wmean(pairs)
            if v is not None:
                signals["order"] = v
        elif name == "process":
            pairs = [(results[i.id].score, weight(i, scoring)) for i in glob if i.check.kind != "order" and results.get(i.id) and results[i.id].status in SCORED]
            v = process_rate = _wmean(pairs)
            if v is not None:
                signals["process"] = v * _process_scale(scoring, stages)
        elif name.startswith("stage:"):
            sid = name[6:]
            if sid in stages and stages[sid].n_items:
                signals[f"stage.{sid}"] = stages[sid].score
    compliance = sum(signals.values()) / len(signals) if signals else 0.0

    def rate(req: str | None = None, pick=None) -> float:
        its = [i for i in rubric.items if (req is None or i.requirement == req) and (pick is None or pick(i))]
        rs = [results[i.id] for i in its if results.get(i.id) and results[i.id].status in SCORED]
        return sum(r.score for r in rs) / len(rs) if rs else 0.0

    diag = {
        "must_rate": rate("must"),
        "should_rate": rate("should"),
        "adapter_rate": rate(pick=lambda i: i.derived_by == "adapter"),
        "log_only_rate": rate(pick=lambda i: i.log_only),
        "unavailable": float(sum(1 for r in results.values() if r.status == "unavailable")),
        "not_applicable": float(sum(1 for r in results.values() if r.status == "not_applicable")),
        "engine_errors": float(engine_errors),
        "items_scored": float(sum(1 for r in results.values() if r.status in SCORED)),
    }
    if process_rate is not None:
        diag["process_rate"] = process_rate
    return Scores(signals, compliance, stages, diag)


def _process_scale(scoring: dict, stages: dict[str, StageScore]) -> float:
    """The factor on the ``process`` signal: 1, or the mean stage score with ``process_scale: stage_mean``
    (``schema.validate`` rejects other values at load time)."""
    if scoring.get("process_scale") != "stage_mean":
        return 1.0
    vals = [s.score for s in stages.values() if s.n_items]
    return sum(vals) / len(vals) if vals else 0.0
