"""G9: self-test of a generated rubric on an honest golden run and its mutations (DESIGN §10 G9, §9 ``selftest``).

A rubric is only as good as the runs it separates. G9 scores it, with its real weights and gates,
on the workflow's golden -- a synthetic honest run written from the documents
(``workflows/<wf>/selftest_golden.py``: ``golden(rubric, variant=None) -> (Run, Collected)`` and an
optional ``VARIANTS`` tuple of other honest runs) -- and on every mutation in
:data:`.mutations.MUTATIONS`. The build fails when

* the golden scores below ``honest_golden_min``, or the engine raised on it;
* an exploit scores above its bound: ``template_copy`` stage max, ``frontmatter_stub`` and
  ``x_fill`` / ``x_fill_bare`` compliance maxima (DESIGN §9), ``no_artifacts`` stage max, or -- for the local
  exploits -- a compliance drop smaller than ``<name>_min_drop`` (default :data:`.mutations.MIN_DROP`,
  0.005: about half of one failed must item; the rubric must notice, not tie);
* an honest variant or honest mutation falls more than its tolerance below the golden
  (``honest_tolerance`` 0.02 for variants, ``honest_edge_tolerance`` 0.0, ``honest_reformat_tolerance`` 0.02).

Bounds come from the rubric's ``scoring.selftest`` (copied from ``generator.yaml``), falling back to
:data:`DEFAULTS`. ``scoring.selftest.golden`` may name the golden (``module[:function]``); otherwise
it is ``recipe.grpo.qwen3_5.workflows.<package>.selftest_golden`` for the package holding the
generator config, then for the workflow name.

    run(rubric, cfg, manifest) -> {status: passed|failed, golden, results: [...], failures: [...], ...}

``Pipeline.build(run_selftest=True)`` stores the result in ``generated.selftest``; ``failed`` makes the
build exit non-zero. ``python -m recipe.grpo.qwen3_5.workflow_rubric.generator.selftest RUBRIC`` runs it
on a committed rubric.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import importlib
import json
import logging
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from .. import aggregate, engine
from .. import schema as S
from .config import GeneratorConfig
from .manifest import Manifest
from .mutations import MUTATIONS, Env, Mutation

logger = logging.getLogger(__name__)

RECIPE = Path(__file__).resolve().parents[2]  # recipe/grpo/qwen3_5
PACKAGE = "recipe.grpo.qwen3_5"
DEFAULTS: dict[str, float] = {"honest_golden_min": 0.95, "honest_tolerance": 0.02, **{m.key: m.default for m in MUTATIONS}}
EPS = 1e-9
N_WORST = 5

Golden = Callable[..., tuple]


# --------------------------------------------------------------------------------------------
# Thresholds and the golden
# --------------------------------------------------------------------------------------------
def thresholds_of(rubric: S.Rubric, cfg: GeneratorConfig | None = None) -> tuple[dict[str, float], str | None]:
    """(bounds, golden spec) from ``scoring.selftest`` of the rubric (else the config), over :data:`DEFAULTS`."""
    sel = dict((rubric.scoring or {}).get("selftest") or ((cfg.scoring or {}).get("selftest") if cfg else None) or {})
    spec = sel.pop("golden", None)
    out = dict(DEFAULTS)
    for k, v in sel.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            logger.warning("selftest: ignoring non-numeric bound %s=%r", k, v)
    return out, (str(spec) if spec else None)


def _candidates(spec: str | None, cfg: GeneratorConfig | None, manifest: Manifest | None, rubric: S.Rubric) -> list[str]:
    out = [spec] if spec else []
    for d in ([Path(cfg.path).parent] if cfg is not None and cfg.path else []) + ([Path(manifest.pkg_dir)] if manifest is not None else []):
        pkg = _workflow_package(d)
        if pkg:
            out.append(f"{PACKAGE}.workflows.{pkg}.selftest_golden")
    for name in ([cfg.workflow] if cfg is not None else []) + [rubric.workflow]:
        out.append(f"{PACKAGE}.workflows.{name}.selftest_golden")
    return list(dict.fromkeys(out))


def load_golden(spec: str) -> tuple[Golden, tuple[str, ...]]:
    """``module[:function]`` -> (golden function, its module's ``VARIANTS``). Raises ImportError / AttributeError."""
    mod_name, _, attr = spec.partition(":")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr or "golden")
    return fn, tuple(getattr(mod, "VARIANTS", ()) or ())


def find_golden(spec: str | None, cfg, manifest, rubric) -> tuple[Golden | None, tuple[str, ...], str, list[str]]:
    tried: list[str] = []
    for cand in _candidates(spec, cfg, manifest, rubric):
        try:
            fn, variants = load_golden(cand)
        except ModuleNotFoundError as e:
            if cand == spec or (e.name and not cand.startswith(e.name)):
                tried.append(f"{cand}: {e}")
            else:
                tried.append(f"{cand}: not found")
            continue
        except (ImportError, AttributeError) as e:
            tried.append(f"{cand}: {type(e).__name__}: {e}")
            continue
        return fn, variants, cand, tried
    return None, (), "", tried


def _workflow_package(d: Path | None) -> str | None:
    try:
        rel = Path(d).resolve().relative_to(RECIPE / "workflows") if d else None
    except ValueError:
        return None
    return rel.parts[0] if rel is not None and len(rel.parts) >= 1 else None


def load_plugins(rubric: S.Rubric) -> list[str]:
    """Import the plugin module (``workflows/<pkg>/reward/checks.py``) of the rubric's package -- from
    ``rubric.path``, the workflow name, and each plugin kind's prefix -- until every kind the rubric
    uses is registered; returns the kinds still unknown (their items then fail as engine errors)."""
    from .. import checks

    checks.load_common()
    need = {it.check.kind for it in rubric.items if it.check.kind != "unimplemented" and it.check.kind not in checks.REGISTRY}
    if not need:
        return []
    pkgs = [_workflow_package(Path(rubric.path).parent.parent) if rubric.path else None, rubric.workflow, *sorted(k.split(".", 1)[0] for k in need if "." in k)]
    for pkg in dict.fromkeys(p for p in pkgs if p):
        try:
            importlib.import_module(f"{PACKAGE}.workflows.{pkg}.reward.checks")
        except ImportError:
            continue
        if all(k in checks.REGISTRY for k in need):
            break
    return sorted(k for k in need if k not in checks.REGISTRY)


def with_docs(rubric: S.Rubric, pkg_dir: str | Path | None) -> S.Rubric:
    """The rubric, pointed at ``pkg_dir`` (its sources' base) when its own path does not reach the documents:
    the engine reads document texts (read fingerprints) relative to ``rubric.path``."""
    srcs = [s for s in rubric.sources if s.container_path]

    def reaches(p: Path | None) -> bool:
        return p is not None and bool(srcs) and all((p.parent.parent / s.path).resolve().is_file() for s in srcs)

    if not srcs or reaches(rubric.path):
        return rubric
    cands = [Path(pkg_dir) / "reward" / "rubric.yaml"] if pkg_dir else []
    cands.append(RECIPE / "workflows" / rubric.workflow / "reward" / "rubric.yaml")
    for c in cands:
        if reaches(c):
            return dataclasses.replace(rubric, path=c)
    return rubric


# --------------------------------------------------------------------------------------------
# Scoring one run and judging it
# --------------------------------------------------------------------------------------------
def _max_stage(rep: engine.Report) -> float:
    vals = [s.score for s in rep.scores.stages.values() if s.n_items]
    return max(vals) if vals else 0.0


def _signals(rep: engine.Report) -> dict[str, float]:
    return {k: round(float(v), 4) for k, v in rep.scores.signals.items()}


def worst_items(rubric: S.Rubric, base: engine.Report | None, rep: engine.Report, n: int = N_WORST) -> list[str]:
    """Items that lost the most weighted score against ``base`` (or, without one, that failed), as short lines."""
    scoring = aggregate.scoring_of(rubric)
    rows = []
    for it in rubric.items:
        r = rep.results.get(it.id)
        if r is None or it.log_only:
            continue
        b = base.results.get(it.id) if base is not None else None
        before = b.score if b is not None and b.status in ("pass", "fail") else (1.0 if base is None else None)
        if before is None:
            continue
        after = r.score if r.status in ("pass", "fail") else before
        loss = before - after
        if loss > EPS:
            rows.append((loss * aggregate.weight(it, scoring), it.id, before, after, r.detail))
    rows.sort(key=lambda x: (-x[0], x[1]))
    return [f"{iid}: {b:.2f}->{a:.2f} ({(d or '').strip()[:90]})" for _, iid, b, a, d in rows[:n]]


def judge(m: Mutation, rep: engine.Report, golden: float, th: dict[str, float]) -> dict:
    """The metric the mutation is held to, its bound and whether it holds."""
    bound = float(th.get(m.key, m.default))
    c = float(rep.scores.compliance)
    if m.metric == "max_stage":
        value = _max_stage(rep)
        ok, op = value <= bound + EPS, "<="
    elif m.metric == "compliance":
        value, ok, op = c, c <= bound + EPS, "<="
    elif m.kind == "honest":
        value, ok, op = c, c >= golden - bound - EPS, ">="
        bound = golden - bound
    else:
        value, ok, op = c, c <= golden - bound + EPS, "<="
        bound = golden - bound
    return {"metric": "compliance" if m.metric == "drop" else m.metric, "value": round(value, 4), "op": op, "bound": round(bound, 4), "key": m.key, "ok": ok}


def _result(name: str, kind: str, rep: engine.Report, verdict: dict, worst: list[str], note: str = "") -> dict:
    out = {
        "mutation": name,
        "kind": kind,
        "status": "ok" if verdict["ok"] else "fail",
        "compliance": round(float(rep.scores.compliance), 4),
        "signals": _signals(rep),
        "check": {k: v for k, v in verdict.items() if k != "ok"},
        "worst_items": worst,
    }
    if rep.engine_errors:
        out["engine_errors"] = rep.engine_errors
    if note:
        out["note"] = note
    return out


def _failure(r: dict) -> str:
    ch = r["check"]
    head = f"{r['mutation']}: {'honest run penalised' if r['kind'] == 'honest' else 'exploit not caught'}: {ch['metric']} {ch['value']:.4f} (bound {ch['op']} {ch['bound']:.4f}, {ch['key']})"
    if r["kind"] == "honest":
        return head + (f"; lost on {r['worst_items'][0]}" if r["worst_items"] else "")
    high = sorted(r["signals"].items(), key=lambda kv: -kv[1])[:3]
    return head + "; highest signals: " + ", ".join(f"{k} {v:.2f}" for k, v in high)


def check(
    rubric: S.Rubric,
    golden: Golden,
    *,
    thresholds: dict[str, float] | None = None,
    env: Env | None = None,
    variants: Iterable[str] = (),
    mutations: Iterable[Mutation] = MUTATIONS,
) -> dict:
    """Score the golden, its variants and every mutation; judge each against its bound."""
    th = {**DEFAULTS, **(thresholds or {})}
    unknown = load_plugins(rubric)
    failures: list[str] = [f"check kinds not registered (no plugin module found): {unknown}"] if unknown else []
    run0, col0 = golden(rubric)
    rep0 = engine.evaluate(rubric, run0, col0)
    g = float(rep0.scores.compliance)
    env = env or Env.build(rubric, run0)
    if rep0.engine_errors:
        failures.append(f"golden: {rep0.engine_errors} engine error(s): {rep0.errors[:2]}")
    if g < th["honest_golden_min"] - EPS:
        failures.append(f"golden: compliance {g:.4f} < honest_golden_min {th['honest_golden_min']}" + (f"; e.g. {worst_items(rubric, None, rep0)[0]}" if worst_items(rubric, None, rep0) else ""))
    results: list[dict] = []
    variant_m = Mutation("variant", golden, "honest", "drop", "honest_tolerance", DEFAULTS["honest_tolerance"])
    for v in variants:
        name = f"variant:{v}"
        try:
            rv, cv = golden(rubric, variant=v)
            rep = engine.evaluate(rubric, rv, cv)
        except Exception as e:  # noqa: BLE001 -- a broken fixture is reported, not raised
            results.append({"mutation": name, "kind": "honest", "status": "error", "error": f"{type(e).__name__}: {e}"})
            failures.append(f"{name}: golden variant raised {type(e).__name__}: {e}")
            continue
        r = _result(name, "honest", rep, judge(variant_m, rep, g, th), worst_items(rubric, rep0, rep))
        results.append(r)
        if r["status"] == "fail":
            failures.append(_failure(r))
    for m in mutations:
        try:
            out = m.fn(copy.deepcopy(run0), copy.deepcopy(col0), rubric, env=env)
        except Exception as e:  # noqa: BLE001
            logger.debug("mutation %s raised", m.name, exc_info=True)
            results.append({"mutation": m.name, "kind": m.kind, "status": "error", "error": f"{type(e).__name__}: {e}"})
            failures.append(f"{m.name}: mutation raised {type(e).__name__}: {e}")
            continue
        if out is None:
            results.append({"mutation": m.name, "kind": m.kind, "status": "n/a", "note": "nothing in the golden it applies to"})
            continue
        rep = engine.evaluate(rubric, *out)
        r = _result(m.name, m.kind, rep, judge(m, rep, g, th), worst_items(rubric, rep0, rep), m.doc)
        results.append(r)
        if r["status"] == "fail":
            failures.append(_failure(r))
    return {
        "status": "failed" if failures else "passed",
        "golden": round(g, 4),
        "golden_signals": _signals(rep0),
        "golden_failing": worst_items(rubric, None, rep0, n=10),
        "thresholds": {k: th[k] for k in sorted(th)},
        "results": results,
        "failures": failures,
    }


# --------------------------------------------------------------------------------------------
# The build hook
# --------------------------------------------------------------------------------------------
def run(rubric: S.Rubric, cfg: GeneratorConfig, manifest: Manifest) -> dict:
    """G9 for a freshly compiled rubric (``Pipeline.build(run_selftest=True)``)."""
    th, spec = thresholds_of(rubric, cfg)
    fn, variants, origin, tried = find_golden(spec, cfg, manifest, rubric)
    if fn is None:
        return {"status": "failed", "golden": None, "results": [], "failures": [f"no golden fixture: {'; '.join(tried) or 'nothing to try'}"], "thresholds": th}
    rub = with_docs(rubric, manifest.pkg_dir if manifest is not None else None)
    env = Env.build(rub, None, manifest, cfg)
    try:
        res = check(rub, fn, thresholds=th, env=env, variants=variants)
    except Exception as e:  # noqa: BLE001 -- the golden itself is broken: report, do not crash the build
        logger.warning("selftest golden %s raised", origin, exc_info=True)
        return {"status": "failed", "golden": None, "results": [], "failures": [f"golden {origin} raised {type(e).__name__}: {e}"], "thresholds": th}
    res["golden_fixture"] = origin
    return res


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def _table(res: dict) -> str:
    rows = [f"golden {res.get('golden')}  ({res.get('golden_fixture', '')})  status {res['status']}"]
    rows += [f"  golden loses: {w}" for w in res.get("golden_failing", [])[:5]]
    for r in res["results"]:
        ch = r.get("check") or {}
        bound = f"{ch.get('metric', '')} {ch.get('value', ''):>7} {ch.get('op', '')} {ch.get('bound', '')}" if ch else r.get("note", r.get("error", ""))
        rows.append(f"{r['status']:5} {r['kind']:7} {r['mutation']:24} {r.get('compliance', ''):>7}  {bound}")
        if r.get("worst_items") and r["kind"] == "exploit":
            rows.append(f"{'':38}caught by: {r['worst_items'][0][:110]}")
        elif r.get("worst_items"):
            rows.append(f"{'':38}lost on: {r['worst_items'][0][:110]}")
    rows += [f"FAIL {f}" for f in res["failures"]]
    return "\n".join(rows)


def package_env(rubric: S.Rubric, pkg: str | Path | None = None) -> Env | None:
    """The mutations' ``Env`` as the build makes it (:func:`run`): from the generator.yaml of the rubric's package
    (``pkg``, else the directory above ``reward/``), so a skeleton the config cuts out of a document (a block of
    lines, not a fenced one) is the one the build's G9 used. None (the guessed skeletons) when there is no config."""
    from .config import load as load_config
    from .manifest import build as build_manifest
    from .manifest import load_spec

    d = Path(pkg) if pkg else (Path(rubric.path).resolve().parent.parent if rubric.path else None)
    if d is None or not (d / "generator.yaml").is_file():
        return None
    try:
        cfg = load_config(d / "generator.yaml")
        spec, spec_dir = load_spec(cfg)
        return Env.build(rubric, None, build_manifest(spec, cfg, spec_dir), cfg)
    except Exception:  # noqa: BLE001 -- a config that does not load leaves the guessed skeletons
        logger.warning("selftest: %s/generator.yaml did not load; skeletons are guessed", d, exc_info=True)
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m recipe.grpo.qwen3_5.workflow_rubric.generator.selftest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rubric", help="rubric.yaml")
    ap.add_argument("--golden", help="module[:function] of the golden (default: scoring.selftest.golden, then workflows/<workflow>/selftest_golden.py)")
    ap.add_argument("--pkg", help="workflow package directory the rubric's source paths are relative to")
    ap.add_argument("--only", help="comma-separated mutation names")
    ap.add_argument("--json", help="write the full result here")
    a = ap.parse_args(argv)
    rub = S.load(a.rubric)
    th, spec = thresholds_of(rub)
    fn, variants, origin, tried = find_golden(a.golden or spec, None, None, rub)
    if fn is None:
        print(f"no golden fixture: {'; '.join(tried)}", file=sys.stderr)
        return 2
    rub = with_docs(rub, a.pkg)
    muts = MUTATIONS if not a.only else tuple(m for m in MUTATIONS if m.name in set(a.only.split(",")))
    res = check(rub, fn, thresholds=th, env=package_env(rub, a.pkg), variants=variants if not a.only else (), mutations=muts)
    res["golden_fixture"] = origin
    print(_table(res))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    return 0 if res["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
