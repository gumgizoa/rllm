"""G8: grounded candidates -> ``rubric.yaml`` (+ ``rubric.md``, ``rubric.lock``, ``eval.py``).

Deterministic bookkeeping that turns a bag of accepted candidates into one rubric:

    scope       ``common`` iff the kind is a common kind that instantiates a common-rubric template
                (C-A*/C-F*, :data:`vocab.COMMON_TEMPLATE`); ``specific`` for plugin kinds and for
                requirements no template expresses (``exec_evidence``, ``field_type``, a trace-bound
                ``none_allowed: {if: ...}``) -- the CONTRACT rule, decided mechanically
    dedup       identical items merge their sources; a specific item and a common item checking the
                same field on the same cited line, in the same role, keep only the specific one (a
                ``field_type`` check skips none values, so it never replaces the field's ``field_filled``;
                a grounded none policy an extracted ``field_type`` carries moves to that ``field_filled``)
    precedence  items that contradict each other (same field, different value set or none policy;
                pairs G7 flagged) are resolved by the workflow's precedence rules, never relaxing a
                value set the template fixed (P3); what precedence cannot settle is kept as both
                readings where that is expressible (enum union, the more permissive none policy) and
                recorded under ``conflicts``
    ids         ``<wf>.<stage>.<target>.<kind>[.<what>][.<n>]``, stable for the same inputs: manual ids
                as written, then compiled (template / stage model) items take the base ids, extracted
                ones the numbered variants -- a gate keyed on an id glob reaches the same item whatever
                the model extracted

The rubric is validated by ``schema.validate`` and the check registry (``checks.validate_params``,
or the static CONTRACT table while the registry is not importable) and re-loaded after writing.
``rubric.md`` is the human review surface: one line per item, ``[must|should] <what to do> --
<file>:<lines>``, grouped by stage, plus the adapter-derived, unimplemented and conflict tables and
the appendix of MAY / implicit / unitemized sentences.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .. import schema as S
from . import TOOL, VERSION
from . import items as I
from .config import GeneratorConfig
from .manifest import Manifest
from .parse import modality
from .vocab import COMMON_TEMPLATE, KindSpec, check_params

ORIGIN_RANK = {"manual": 0, "template": 1, "stage": 2, "llm": 3, "critic": 4}
CONFLICT_KINDS = ("field_enum", "field_literal", "field_filled", "frontmatter", "label_present", "section_present", "write_discipline", "path_match")
KIND_ORDER = [
    "artifact_exists", "path_match", "frontmatter", "section_present", "label_present", "field_literal", "field_enum", "field_filled", "field_type",
    "item_format", "no_template_residue", "not_template_copy", "cross_ref", "doc_read_first", "doc_read", "order", "write_discipline",
    "exec_evidence", "prohibited_action",
]  # fmt: skip

EVAL_STUB = '''"""{wf} compliance: the generated ``rubric.yaml`` interpreted by the common rubric engine."""

from pathlib import Path

from recipe.grpo.qwen3_5.workflow_rubric.evaluation import RubricEvaluation


class Evaluation(RubricEvaluation):
    def __init__(self):
        super().__init__(Path(__file__).with_name("rubric.yaml"), prefix="{prefix}"{plugins})
'''


@dataclass
class Inputs:
    cfg: GeneratorConfig
    manifest: Manifest
    model: dict
    accepted: list[I.Cand]
    kinds: dict[str, KindSpec]
    kinds_origin: str = "static"
    rejected: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    may_items: list[dict] = field(default_factory=list)
    implicit_items: list[dict] = field(default_factory=list)
    unitemized: list[dict] = field(default_factory=list)
    sp_generic: list[dict] = field(default_factory=list)
    llm: dict = field(default_factory=dict)
    cache_dir: str = ""
    selftest: dict | None = None


# ----------------------------------------------------------------------------------------------
def stage_cands(model: dict, cfg: GeneratorConfig, manifest: Manifest) -> list[I.Cand]:
    """``artifact_exists`` per non-optional artifact of the stage model, cited from the line that names it (C-F1)."""
    out = []
    derived = "manual" if model.get("origin") == "fixed" else "llm_extract"
    owner = {a: s["id"] for s in model.get("stages", []) for a in s.get("artifacts", [])}
    for aid, a in model.get("artifacts", {}).items():
        if a.get("optional") or not a.get("sources"):
            continue
        srcs = [S.SourceRef.from_dict(r) for r in a["sources"]]
        m, ev = max((modality(r.quote) for r in srcs), key=lambda x: {"prohibition": 4, "must": 4, "should": 2}.get(x[0], 0))
        req = "must" if m in ("must", "prohibition") else "should"
        out.append(
            I.make(
                f"{cfg.workflow}.{owner.get(aid, 'global')}.{aid}.artifact_exists",
                "artifact_exists",
                {},
                stage=owner.get(aid, "global"),
                target=("artifact", aid, "final"),
                requirement=req,
                sources=srcs,
                cls="structure",
                origin="stage",
                derived_by=derived,
                modality_evidence=f"stage model ({model.get('origin')}); dict {m}" + (f" ('{ev}')" if ev else ""),
                downgrade_reason="" if req == "must" else f"dictionary {m}",
            )
        )
    return out


def manual_cands(cfg: GeneratorConfig, manifest: Manifest) -> list[I.Cand]:
    """generator.yaml ``manual`` items (sources by path) -> candidates with ``derived_by: manual`` (or ``adapter``
    when the reviewer marked the item as resting only on adapter text; G6 then applies P1a to it)."""
    out = []
    for d in cfg.manual:
        srcs = []
        for s in d["sources"]:
            e = manifest.resolve(str(s.get("path") or s.get("doc")))
            lines = s.get("lines") or [1, 1]
            lines = [lines, lines] if isinstance(lines, int) else lines
            srcs.append(S.SourceRef(doc=e.id if e else str(s.get("path") or s.get("doc")), lines=(int(lines[0]), int(lines[-1])), quote=str(s.get("quote", ""))))
        t = d.get("target") or {"type": "action", "ref": "run"}
        chk = d["check"]
        c = I.make(
            str(d["id"]),
            str(chk["kind"]),
            dict(chk.get("params") or {}),
            stage=str(d.get("stage", "global")),
            target=(str(t.get("type", "action")), str(t.get("ref", "run")), str(t.get("state", "final"))),
            requirement=str(d.get("requirement", "should")),
            sources=srcs,
            cls=str(d.get("class", "content")),
            origin="manual",
            derived_by=str(d.get("derived_by") or "manual"),
            none_allowed=d.get("none_allowed", "-"),
            applies_when=d.get("applies_when"),
            modality_evidence=str(d.get("modality_evidence", "manual")),
            availability=list(d.get("availability") or ["sandbox_file"]),
            note=str(d.get("note", "")),
            impl_refs=[str(x) for x in d.get("impl_refs") or []],
        )
        c.item.weight = float(d.get("weight", 1.0))
        c.item.log_only = bool(d.get("log_only", False))  # reported, never scored (e.g. a CLI-only key set, DESIGN §11.2)
        if d.get("gate"):
            c.item.gate = dict(d["gate"])
        out.append(c)
    return out


def scope_of(it: S.Item, kinds: dict[str, KindSpec]) -> str:
    ks = kinds.get(it.check.kind)
    if it.check.kind == "unimplemented" or ks is None or not ks.common or "." in it.check.kind:
        return "specific"
    if it.check.kind not in COMMON_TEMPLATE:
        return "specific"
    if isinstance(it.none_allowed, dict) and "if" in it.none_allowed:
        return "specific"
    return "common"


# ----------------------------------------------------------------------------------------------
def compile_rubric(inp: Inputs) -> tuple[S.Rubric, dict]:
    cfg, kinds = inp.cfg, inp.kinds
    report: dict = {"dedup": [], "precedence": [], "conflicts": [*({"type": "documented", **c} for c in cfg.conflicts), *inp.conflicts]}
    cands = [c for c in inp.accepted]
    for c in cands:
        c.item.scope = scope_of(c.item, kinds)
        tpl = COMMON_TEMPLATE.get(c.item.check.kind)
        if c.item.scope == "common" and tpl:
            c.item.template = tpl
    cands = _exclude(cands, cfg, report)
    cands = _content_required(cands, cfg, inp.manifest, report)
    cands = _type_none_policies(cands, report)
    cands = _dedup_exact(cands, report)
    cands = _dedup_scope(cands, report)
    cands = _precedence(cands, inp, report)
    cands = _critic_conflicts(cands, inp, report)
    cands = _supersede(cands, report)
    cands = _covered_unimplemented(cands, report)
    _order(cands, inp.model)
    _ids(cands, cfg)
    for c in cands:
        for key, gate in cfg.gates.items():
            if key == c.item.check.kind or fnmatch.fnmatch(c.item.id, key):
                c.item.gate = dict(gate)
        if c.item.check.kind == "unimplemented":
            c.item.weight = 0.0
    _optional_targets(cands, inp.model, report)
    model = inp.model
    rub = S.Rubric(
        workflow=cfg.workflow,
        sources=inp.manifest.to_sources(),
        roots=dict(model.get("roots", {})),
        stages=[
            S.Stage(id=s["id"], doc=s.get("doc"), artifacts=list(s.get("artifacts", [])), order_artifact=s.get("order_artifact"), requires=list(s.get("requires", []))) for s in model.get("stages", [])
        ],
        artifacts={
            aid: S.Artifact(id=aid, **{k: v for k, v in a.items() if k in ("locations", "exclusive", "template", "write_event", "optional", "kind")}) for aid, a in model.get("artifacts", {}).items()
        },
        items=[c.item for c in cands],
        scoring=dict(cfg.scoring),
        vars={k: S.Var(name=k, **{kk: vv for kk, vv in v.items() if kk in ("under", "regex", "bind", "exclude")}) for k, v in model.get("vars", {}).items()},
        generated={
            "tool": f"{TOOL} {VERSION}",
            "llm": dict(inp.llm),
            "cache": inp.cache_dir,
            "at": date.today().isoformat(),
            "kinds": inp.kinds_origin,
            "stage_model": model.get("origin", ""),
            **({"selftest": inp.selftest} if inp.selftest else {}),
        },
        conflicts=report["conflicts"],
        appendix={
            "may_items": [_strip(m) for m in inp.may_items],
            "implicit_items": inp.implicit_items,
            "sp_generic_unitemized": inp.sp_generic,
            "unimplemented": [c.item.id for c in cands if c.item.check.kind == "unimplemented"],
            "unitemized_statements": inp.unitemized,
        },
    )
    S.validate(rub)
    validate_kinds(rub, kinds, inp.kinds_origin)
    report["n_items"] = len(rub.items)
    report["by_origin"] = _count(c.origin for c in cands)
    report["by_requirement"] = _count(c.item.requirement for c in cands)
    report["by_scope"] = _count(c.item.scope for c in cands)
    report["by_derived_by"] = _count(c.item.derived_by for c in cands)
    return rub, report


def _optional_targets(cands: list[I.Cand], model: dict, report: dict) -> None:
    """Items about an optional artifact (OpenSpec's design.md, "create only if any apply") apply only when it
    exists: a run that rightly skips it fails none of them, and its existence is never required (stage_cands)."""
    opt = {aid for aid, a in (model.get("artifacts") or {}).items() if a.get("optional")}
    for c in cands:
        it = c.item
        if it.target.type != "artifact" or it.target.ref not in opt or it.check.kind in ("artifact_exists", "unimplemented"):
            continue
        cond = {"artifact_exists": it.target.ref}
        cur = it.applies_when
        if cur == cond or (isinstance(cur, dict) and cond in (cur.get("all") or [])):
            continue
        it.applies_when = cond if cur is None else {"all": [cond, cur]}
        report.setdefault("optional_artifacts", []).append(it.id)


def validate_kinds(rub: S.Rubric, kinds: dict[str, KindSpec], origin: str) -> None:
    """The registry's ``validate_params`` when importable, else the static table (same rules)."""
    if origin == "registry":
        from ..checks import validate_params

        validate_params(rub)
        return
    errs = []
    for it in rub.items:
        e = check_params(it.check.kind, it.check.params, kinds)
        if e:
            errs.append(f"{it.id}: {'; '.join(e)}")
        ks = kinds.get(it.check.kind)
        if ks is not None and not ks.common and it.scope != "specific":
            errs.append(f"{it.id}: plugin kind must be scope specific")
    if errs:
        raise S.RubricError("; ".join(errs[:20]))


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _count(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return dict(sorted(out.items()))


def _dedup_exact(cands: list[I.Cand], report: dict) -> list[I.Cand]:
    out: dict[str, I.Cand] = {}
    for c in sorted(cands, key=lambda c: (ORIGIN_RANK.get(c.origin, 9), c.item.requirement != "must")):  # a must reading of the same check wins
        k = c.key()
        if k in out:
            keep = out[k]
            keep.item.sources = _merge_sources(keep.item.sources, c.item.sources)
            if c.item.requirement == "must" and keep.item.requirement == "should" and not keep.downgrade_reason:
                keep.item.requirement = "must"
            report["dedup"].append({"kept": keep.id, "dropped": c.id, "why": "identical check"})
        else:
            out[k] = c
    order = {id(c): i for i, c in enumerate(cands)}
    return sorted(out.values(), key=lambda c: order[id(c)])


def _exclude(cands: list[I.Cand], cfg: GeneratorConfig, report: dict) -> list[I.Cand]:
    """Extracted items a reviewer dropped (generator.yaml ``exclude``: statement id, kind, stage, reason)."""
    report.setdefault("excluded", [])
    if not cfg.exclude:
        return cands
    out = []
    for c in cands:
        it, hit = c.item, None
        if c.origin in ("llm", "critic") and c.statement:
            hit = next((x for x in cfg.exclude if fnmatch.fnmatch(c.statement, x["statement"]) and x.get("kind", it.check.kind) == it.check.kind and x.get("stage", it.stage) == it.stage), None)
        if hit:
            row = {"id": c.id, "statement": c.statement, "kind": it.check.kind, "stage": it.stage, "reason": hit["reason"], "sources": [s.to_dict() for s in it.sources]}
            report["excluded"].append({**row, "_cand": c, "_into": hit.get("merge_into")})
        else:
            out.append(c)
    for x in report["excluded"]:
        c, into = x.pop("_cand", None), x.pop("_into", None)
        target = _merge_target(out, c, into) if c is not None and into else None
        if target is not None:
            target.item.sources = _merge_sources(target.item.sources, c.item.sources)
            x["merged_into"] = target.id
    return out


def _merge_target(out: list[I.Cand], c: I.Cand, into: str) -> I.Cand | None:
    """The item an excluded duplicate folds into: one from statement ``into`` (glob) of the same kind, or, for
    ``template``, the template item of the same kind / artifact / section whose parameters share most words."""
    kind, ref, sec = c.item.check.kind, c.item.target.ref, c.item.check.params.get("section")
    if into != "template":
        return next((t for t in out if t.statement and fnmatch.fnmatch(t.statement, into) and t.item.check.kind == kind), None)

    def words(d) -> set[str]:
        return set(re.findall(r"[A-Za-z]{3,}", json.dumps(d, sort_keys=True)))

    pool = [t for t in out if t.origin == "template" and t.item.check.kind == kind and t.item.target.ref == ref and t.item.check.params.get("section") == sec]
    mine = words(c.item.check.params)
    return max(pool, key=lambda t: len(words(t.item.check.params) & mine), default=None)


_FIELD_KINDS = ("label_present", "field_filled", "field_enum", "field_literal")


def _subject(it: S.Item) -> tuple | None:
    """What an item is about, for kinds whose subject is unambiguous; None: compare whole items only."""
    k, p = it.check.kind, it.check.params
    art = p.get("artifact") or it.target.ref
    low = lambda v: str(v or "").strip().lower()  # noqa: E731
    if k == "path_match":  # one artifact's path may carry several rules (OpenSpec: kebab-case name, archived, one date)
        return (k, art, it.target.state, str(p.get("pattern")))
    if k in ("artifact_exists", "frontmatter"):
        return (k, art, it.target.state)
    if k == "section_present":
        return (k, art, low(p.get("heading")))
    if k in _FIELD_KINDS:
        return (k, art, low(p.get("section")), low(p.get("label")))
    if k == "field_type":
        return (k, art, low(p.get("section")), low(p.get("label")), p.get("type"))
    if k in ("doc_read", "doc_read_first"):
        return (k, p.get("doc"))
    if k == "write_discipline":
        return (k, art, p.get("mode"))
    if k == "exec_evidence":
        return (k, it.stage, p.get("kind", "test"), "command_in" in p)
    if k == "order":
        return (k,)
    if k == "prohibited_action":
        return (k, p.get("action"), p.get("pattern") if p.get("action") in ("repo_write", "command") else None)
    return None


def _value_set(it: S.Item) -> str:
    """The parameters that fix *what value* a field must hold (an enum, a literal, frontmatter keys/values)."""
    p = it.check.params
    norm = lambda v: re.sub(r"\s+", " ", str(v)).strip().rstrip(".").lower()  # noqa: E731
    if it.check.kind == "field_enum":
        return json.dumps(sorted(norm(v) for v in p.get("values") or []))
    if it.check.kind == "field_literal":
        return json.dumps(sorted(norm(v) for v in (p["text"] if isinstance(p.get("text"), list) else [p.get("text")])))
    if it.check.kind == "frontmatter":
        return json.dumps([p.get("keys"), {k: norm(v) for k, v in (p.get("values") or {}).items()}] if p.get("values") else [p.get("keys")], sort_keys=True, default=str)
    return ""


_NONE_RANK = {"yes": 0, "-": 0, "unspecified": 1, "no": 3}


def _none_rank(v) -> int:
    return 4 if isinstance(v, dict) else _NONE_RANK.get(str(v), 1)


def _supersede(cands: list[I.Cand], report: dict) -> list[I.Cand]:
    """One item per subject (same requirement extracted from several lines): a manual item (a reviewed
    decision) over a template / stage-model item over extracted ones; among extracted ones, must over should.
    The survivor keeps every source. For ``field_filled`` the strictest none policy an extracted item grounds
    (a trace condition, then "no") replaces the template's default ("unspecified", faithfulness: a field the
    template leaves open becomes required only where a line says so); a template literal gains the
    refutations of its same-text variants."""
    groups: dict[tuple, list[I.Cand]] = {}
    for c in cands:
        sub = _subject(c.item)
        if sub is not None:
            groups.setdefault(sub, []).append(c)
    drop: set[int] = set()
    for sub, grp in groups.items():
        if len(grp) < 2 or len({_value_set(c.item) for c in grp}) > 1:  # differing value sets are _precedence's (P3)
            continue
        ranked = sorted(grp, key=lambda c: (ORIGIN_RANK.get(c.origin, 9), c.item.requirement != "must", -len(c.item.sources)))
        # several manual items on one subject are separate reviewed decisions (a document read in several stages, two
        # order pairs): each stays. An item scores in its stage, so the others fold into a keeper of their own stage, or
        # a global one (or are a global one); an item of another stage (neither global) is that stage's requirement.
        keepers = [c for c in ranked if c.origin == "manual"] or ranked[:1]
        into: dict[int, I.Cand] = {}
        for c in ranked:
            if any(c is k for k in keepers):
                continue
            tgt = next((k for k in keepers if k.item.stage == c.item.stage), None) or next((k for k in keepers if "global" in (k.item.stage, c.item.stage)), None)
            if tgt is not None:
                into[id(c)] = tgt
        for keep in keepers:
            rest = [c for c in ranked if into.get(id(c)) is keep]
            if rest:
                _fold(sub, keep, rest, drop, report)
    return [c for c in cands if id(c) not in drop]


def _fold(sub: tuple, keep: I.Cand, rest: list[I.Cand], drop: set[int], report: dict) -> None:
    """``rest`` folds into ``keep`` (same subject, see :func:`_supersede`): sources, none policy, refutations, must."""
    if sub[0] == "field_filled" and keep.origin in ("template", "stage"):
        best = max(rest, key=lambda c: _none_rank(c.item.none_allowed))
        if _none_rank(best.item.none_allowed) > _none_rank(keep.item.none_allowed) and best.origin in ("llm", "critic"):
            keep.item.none_allowed = best.item.none_allowed
            keep.item.modality_evidence += f"; none policy from {best.id} ({best.statement})"
    if sub[0] == "field_literal" and keep.origin != "manual":  # a manual literal's refutation (its window) is the reviewed decision
        _merge_refutations(keep, rest)
    if any(c.item.requirement == "must" and c.origin == keep.origin for c in rest) and keep.item.requirement == "should" and not keep.downgrade_reason:
        keep.item.requirement = "must"
    for c in rest:
        keep.item.sources = _merge_sources(keep.item.sources, c.item.sources)
        drop.add(id(c))
        report["dedup"].append({"kept": keep.id, "dropped": c.id, "why": f"same subject {list(sub)} ({keep.origin} over {c.origin})"})


def _covered_unimplemented(cands: list[I.Cand], report: dict) -> list[I.Cand]:
    """An ``unimplemented`` placeholder whose lines an implemented item already cites adds nothing to report."""
    cited = {ln for c in cands if c.item.check.kind != "unimplemented" for ln in c.lines()}
    out = []
    for c in cands:
        if c.item.check.kind == "unimplemented" and c.lines() and c.lines() <= cited:
            report["dedup"].append({"kept": "(implemented items citing the same lines)", "dropped": c.id, "why": "unimplemented statement already implemented"})
            continue
        out.append(c)
    return out


def _dedup_scope(cands: list[I.Cand], report: dict) -> list[I.Cand]:
    """Specific wins over common on the same target line (same field of the same artifact, overlapping citations) --
    except over a manual item: a generator.yaml item is a reviewed decision (e.g. a field required only under a
    condition, P3), and an extracted rival for the same field is dropped instead."""
    drop: set[int] = set()
    specific = [c for c in cands if c.item.scope == "specific" and c.subject()]
    for c in cands:
        if c.item.scope != "common" or not c.subject():
            continue
        for s in specific:
            if id(s) in drop:
                continue
            same_line = bool(s.lines() & c.lines())
            same_field = c.item.check.kind == s.item.check.kind == "field_filled" and isinstance(s.item.none_allowed, dict)  # a trace-bound none policy for this very field
            if s.item.target.ref == c.item.target.ref and s.subject() == c.subject() and (same_line or same_field) and _same_family(s.item.check.kind, c.item.check.kind):
                if c.origin == "manual" and s.origin != "manual":
                    drop.add(id(s))
                    report["dedup"].append({"kept": c.id, "dropped": s.id, "why": "manual decision over an extracted item on the same field"})
                    continue
                drop.add(id(c))
                report["dedup"].append({"kept": s.id, "dropped": c.id, "why": "specific over common on the same target line"})
                break
    return [c for c in cands if id(c) not in drop]


def _same_family(a: str, b: str) -> bool:
    # field_type is its own role: it checks a value against the run and skips none values, so the field's
    # presence / none policy (field_filled) must survive next to it
    fam = {"field_filled": "value", "field_enum": "value", "field_literal": "value"}
    return a == b or (fam.get(a) is not None and fam.get(a) == fam.get(b)) or "." in a


def _field_key(it: S.Item) -> tuple[str, str, str]:
    p = it.check.params
    return (str(p.get("artifact") or it.target.ref), str(p.get("section") or "").strip().lower(), str(p.get("label") or "").strip().lower())


def _content_required(cands: list[I.Cand], cfg: GeneratorConfig, manifest: Manifest, report: dict) -> list[I.Cand]:
    """generator.yaml ``content_required``: a template field with no none alternative whose prose demands
    content ("Record every path in full") gets ``none_allowed: no`` and the demanding lines as sources;
    a quote that does not match its lines is an infrastructure error (the config is wrong)."""
    from .ground import quote_matches

    for spec in cfg.content_required:
        srcs = []
        for r in spec["sources"]:
            e = manifest.resolve(r["path"])
            a, b = r["lines"]
            if e is None or not quote_matches(r["quote"], "\n".join(e.lines()[a - 1 : b])):
                raise S.RubricError(f"content_required {spec['section']}/{spec['label']}: quote not at {r['path']}:{a}-{b}")
            srcs.append(S.SourceRef(doc=e.id, lines=(a, b), quote=r["quote"]))
        key = (spec["artifact"], spec["section"].strip().lower(), spec["label"].strip().lower())
        hit = False
        for c in cands:
            it = c.item
            if it.check.kind == "field_filled" and c.origin in ("template", "stage") and _field_key(it) == key and not isinstance(it.none_allowed, dict) and it.none_allowed in ("unspecified", "-"):
                it.none_allowed = "no"
                it.sources = _merge_sources(it.sources, srcs)
                it.modality_evidence += "; content required: " + "; ".join(f"{s.doc}:{s.lines[0]} '{s.quote[:60]}'" for s in srcs)
                report.setdefault("none_policy", []).append({"item": it.id, "from": "content_required", "none_allowed": "no"})
                hit = True
        if not hit:
            report.setdefault("none_policy", []).append({"item": None, "from": "content_required", "unmatched": f"{spec['artifact']} {spec['section']}/{spec['label']}"})
    return cands


def _type_none_policies(cands: list[I.Cand], report: dict) -> list[I.Cand]:
    """A grounded none policy ("no", or a trace condition) that an extracted ``field_type`` item carries
    for a field becomes the policy of the field's compiled ``field_filled`` item when the template is
    silent ("unspecified"): ``field_type`` skips none values, so on its own item the policy is never
    applied. A template that offers a none alternative ("yes") keeps it."""
    best: dict[tuple, I.Cand] = {}
    for c in cands:
        na = c.item.none_allowed
        if c.item.check.kind != "field_type" or c.origin not in ("llm", "critic") or not (isinstance(na, dict) or na == "no"):
            continue
        k = _field_key(c.item)
        if k not in best or _none_rank(na) > _none_rank(best[k].item.none_allowed):
            best[k] = c
    for c in cands:
        it = c.item
        if it.check.kind != "field_filled" or c.origin not in ("template", "stage") or isinstance(it.none_allowed, dict) or it.none_allowed not in ("unspecified", "-"):
            continue
        b = best.get(_field_key(it))
        if b is not None:
            it.none_allowed = b.item.none_allowed
            it.modality_evidence += f"; none policy from {b.id} ({b.statement})"
            it.sources = _merge_sources(it.sources, b.item.sources)
            report.setdefault("none_policy", []).append({"item": it.id, "from": b.id, "statement": b.statement, "none_allowed": b.item.none_allowed})
    return cands


def _rank(c: I.Cand, inp: Inputs) -> int:
    """Lower is stronger: the position of the item's best source in the applicable precedence order."""
    cls = "procedure" if c.item.cls == "evidence" else "content"
    best = 10_000
    for rule in inp.cfg.precedence:
        if rule.applies_to not in ("all", cls):
            continue
        for s in c.item.sources:
            e = inp.manifest.by_id(s.doc)
            if e is None:
                continue
            keys = [e.id, e.role]
            if e.role == "system_prompt":
                keys.append(f"system_prompt:{e.section_role(s.lines[0])}")
            for i, k in enumerate(rule.order):
                if k in keys:
                    best = min(best, i)
        break
    return best


def _precedence(cands: list[I.Cand], inp: Inputs, report: dict) -> list[I.Cand]:
    groups: dict[tuple, list[I.Cand]] = {}
    for c in cands:
        it = c.item
        if it.check.kind not in CONFLICT_KINDS:
            continue
        p = it.check.params
        k = (
            it.check.kind,
            it.target.ref,
            it.target.state,
            str(p.get("section", p.get("heading", ""))).lower(),
            str(p.get("label", "")).lower(),
            json.dumps(p.get("per_block"), sort_keys=True),
            str(p.get("mode", "")),  # write_discipline: once / no_rewrite are different requirements, not rival readings
            str(p.get("pattern", "")) if it.check.kind == "path_match" else "",  # several path rules on one artifact (see _subject)
        )
        groups.setdefault(k, []).append(c)
    drop: set[int] = set()
    for k, grp in groups.items():
        variants = {json.dumps([g.item.check.params, g.item.none_allowed], sort_keys=True, default=str) for g in grp}
        if len(grp) < 2 or len(variants) < 2:
            continue
        kind = k[0]
        tpl = [g for g in grp if g.item.derived_by == "template_compiler" and kind in ("field_enum", "field_literal")]
        manual = [g for g in grp if g.origin == "manual"]
        ids = [g.id for g in grp]
        if manual:
            # a generator.yaml item is a reviewed decision with its own cited lines (e.g. both readings of a
            # documented gap, P3); it replaces the compiled / extracted variants of the same field
            keep, why = manual[0], "manual decision in generator.yaml (its cited lines)"
            for g in grp:
                if g is not keep:
                    keep.item.sources = _merge_sources(keep.item.sources, g.item.sources)
        elif tpl:
            keep, why = tpl[0], "template value set is not relaxed (P3)"
            if kind == "field_literal":
                why += _merge_refutations(keep, [g for g in grp if g is not keep])
        else:
            ranks = sorted((_rank(g, inp), ORIGIN_RANK.get(g.origin, 9), i, g) for i, g in enumerate(grp))
            if ranks[0][0] < ranks[1][0]:
                keep = ranks[0][3]
                rule = next((r for r in inp.cfg.precedence), None)
                why = f"precedence: {rule.authority.path}:{rule.authority.lines[0]} '{rule.authority.quote[:80]}'" if rule and rule.authority else "precedence"
            else:
                keep = ranks[0][3]
                why = _merge_readings(keep, [g for g in grp if g is not keep])
                report["conflicts"].append({"type": "unresolved", "items": ids, "kept": keep.id, "description": f"{kind} on {k[1]} '{k[3]}' '{k[4]}': {why}"})
                for g in grp:
                    if g is not keep:
                        drop.add(id(g))
                continue
        for g in grp:
            if g is not keep:
                drop.add(id(g))
        report["precedence"].append({"kept": keep.id, "dropped": [g.id for g in grp if g is not keep], "why": why})
        report["conflicts"].append({"type": "resolved", "items": ids, "kept": keep.id, "description": why})
    return [c for c in cands if id(c) not in drop]


def _merge_refutations(keep: I.Cand, others: list[I.Cand]) -> str:
    """A variant of a template literal with the same text that only adds ``refuted_by`` tightens it
    (DESIGN §8: a fixed phrase the run contradicts is false) -- keep the template's value, add the refutation."""
    p = keep.item.check.params

    def same(o: I.Cand) -> bool:
        q = o.item.check.params
        norm = lambda v: sorted(re.sub(r"\s+", " ", str(x)).strip().rstrip(".").lower() for x in (v if isinstance(v, list) else [v]))  # noqa: E731
        return norm(q.get("text")) == norm(p.get("text")) and str(q.get("label") or "").lower() == str(p.get("label") or "").lower() and q.get("refuted_by") is not None

    preds = [p["refuted_by"]] if p.get("refuted_by") is not None else []
    added = 0
    for o in others:
        if same(o) and o.item.check.params["refuted_by"] not in preds:
            preds.append(o.item.check.params["refuted_by"])
            keep.item.sources = _merge_sources(keep.item.sources, o.item.sources)
            added += 1
    if not added:
        return ""
    keep.item.check.params = {**p, "refuted_by": preds[0] if len(preds) == 1 else {"any": preds}}
    return f"; refuted_by added from {added} same-text variant(s)"


def _merge_readings(keep: I.Cand, others: list[I.Cand]) -> str:
    """Both readings allowed where expressible: enum union, the most permissive none policy."""
    it = keep.item
    notes = []
    if it.check.kind == "field_enum":
        vals = list(it.check.params.get("values", []))
        for o in others:
            vals += [v for v in o.item.check.params.get("values", []) if v not in vals]
        it.check.params["values"] = vals
        notes.append("enum values united")
    order = {"yes": 0, "unspecified": 1, "no": 3}
    every = list(others)
    if not isinstance(it.none_allowed, dict) and it.none_allowed in ("unspecified", "-"):  # silent: any grounded reading replaces it
        grounded = [o for o in others if isinstance(o.item.none_allowed, dict) or o.item.none_allowed not in ("unspecified", "-")]
        if grounded:
            it.none_allowed = max(grounded, key=lambda o: 2 if isinstance(o.item.none_allowed, dict) else order.get(o.item.none_allowed, 2)).item.none_allowed
            notes.append(f"none_allowed -> {it.none_allowed} (grounded over silent)")
    others = [o for o in others if isinstance(o.item.none_allowed, dict) or o.item.none_allowed not in ("unspecified", "-")]
    for o in others:
        a = order.get(it.none_allowed, 2) if not isinstance(it.none_allowed, dict) else 2
        b = order.get(o.item.none_allowed, 2) if not isinstance(o.item.none_allowed, dict) else 2
        if b < a:
            it.none_allowed = o.item.none_allowed
            notes.append(f"none_allowed -> {o.item.none_allowed}")
    for o in every:
        it.sources = _merge_sources(it.sources, o.item.sources)
    return "; ".join(notes) or "kept the first reading; others recorded"


def _critic_conflicts(cands: list[I.Cand], inp: Inputs, report: dict) -> list[I.Cand]:
    by_id = {c.id: c for c in cands}
    drop: set[str] = set()
    for cf in inp.conflicts:
        if cf.get("type") != "critic":
            continue
        grp = [by_id[i] for i in cf.get("items", []) if i in by_id and i not in drop]
        if len(grp) < 2:
            continue
        if len({_subject(g.item) or g.id for g in grp}) > 1:  # different checks: a model's claim, not a value conflict on one field
            cf["resolution"] = "kept both (different subjects; recorded for review)"
            continue
        ranks = sorted((_rank(g, inp), ORIGIN_RANK.get(g.origin, 9), i, g) for i, g in enumerate(grp))
        if ranks[0][0] < ranks[1][0] or ranks[0][1] < ranks[1][1]:
            keep = ranks[0][3]
            for g in grp:
                if g is not keep:
                    drop.add(g.id)
            cf["resolution"] = f"kept {keep.id} (precedence/origin)"
        else:
            cf["resolution"] = "unresolved: both kept"
    return [c for c in cands if c.id not in drop]


def _order(cands: list[I.Cand], model: dict) -> None:
    stage_pos = {s["id"]: i for i, s in enumerate(model.get("stages", []))}
    art_pos = {a: i for i, a in enumerate(model.get("artifacts", {}))}
    kind_pos = {k: i for i, k in enumerate(KIND_ORDER)}

    def key(c: I.Cand):
        it = c.item
        first = min((s.lines[0] for s in it.sources), default=0)
        return (stage_pos.get(it.stage, len(stage_pos)), art_pos.get(it.target.ref, len(art_pos)), kind_pos.get(it.check.kind, len(kind_pos)), first, it.id)

    cands.sort(key=key)


def _ids(cands: list[I.Cand], cfg: GeneratorConfig) -> None:
    taken: dict[str, int] = {}
    for c in cands:
        if c.origin == "manual":
            taken[c.item.id] = 1
    compiled = [c for c in cands if c.origin in ("template", "stage")]
    extracted = [c for c in cands if c.origin not in ("manual", "template", "stage")]
    for c in [*compiled, *extracted]:
        it = c.item
        p = it.check.params
        what = p.get("label") or p.get("heading") or p.get("section") or p.get("doc") or p.get("mode") or p.get("action") or p.get("type") or ""
        if it.check.kind == "item_format" and not what:
            what = "line"
        parts = [cfg.workflow, it.stage, _slug(it.target.ref), it.check.kind.replace(".", "_")] + ([_slug(str(what))] if what else [])
        base = ".".join(parts)
        n = taken.get(base, 0)
        it.id = base if n == 0 else f"{base}.{n + 1}"
        taken[base] = n + 1


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "x"


def _merge_sources(a: list[S.SourceRef], b: list[S.SourceRef]) -> list[S.SourceRef]:
    out = list(a)
    seen = {(s.doc, s.lines, s.quote) for s in a}
    for s in b:
        if (s.doc, s.lines, s.quote) not in seen:
            seen.add((s.doc, s.lines, s.quote))
            out.append(s)
    return out


# ----------------------------------------------------------------------------------------------
# outputs
# ----------------------------------------------------------------------------------------------
def write_outputs(rub: S.Rubric, out_dir: Path, inp: Inputs, report: dict, force_eval: bool = False) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {"rubric": out_dir / "rubric.yaml", "md": out_dir / "rubric.md", "lock": out_dir / "rubric.lock", "eval": out_dir / "eval.py"}
    rub.dump(paths["rubric"])
    S.load(paths["rubric"])  # round trip: what we wrote is what the engine will read
    paths["md"].write_text(render_md(rub, inp, report))
    paths["lock"].write_text(json.dumps(lock(rub, inp, paths["rubric"]), indent=1, sort_keys=True) + "\n")
    if force_eval or not paths["eval"].exists():
        plugins = ', plugins=[f"{__package__}.checks"]' if (out_dir / "checks.py").is_file() else ""
        paths["eval"].write_text(EVAL_STUB.format(wf=inp.cfg.workflow, prefix=inp.cfg.signal_prefix, plugins=plugins))
    return {k: str(v) for k, v in paths.items()}


def lock(rub: S.Rubric, inp: Inputs, rubric_path: Path) -> dict:
    cfg_sha = hashlib.sha256(inp.cfg.path.read_bytes()).hexdigest() if inp.cfg.path and inp.cfg.path.is_file() else ""
    return {
        "generator": f"{TOOL} {VERSION}",
        "config": {"path": inp.cfg.path.name if inp.cfg.path else "", "sha256": cfg_sha},
        "sources": {e.path: e.sha256 for e in inp.manifest.entries},
        "rubric_sha256": hashlib.sha256(rubric_path.read_bytes()).hexdigest(),
        "llm": dict(inp.llm),
        "kinds": inp.kinds_origin,
    }


def _art(rub: S.Rubric, aid: str) -> str:
    """An artifact as the agent names it: its file name (``01-reverse-engineering.md``), else its id."""
    a = rub.artifacts.get(aid)
    if a is None or not a.locations:
        return aid
    name = a.locations[0].rstrip("/").rsplit("/", 1)[-1]
    return name if name and "{" not in name else a.locations[0]


def _doc(rub: S.Rubric, sid: str) -> str:
    """A source as the agent sees it: its container path, else its package path."""
    for s in rub.sources:
        if s.id == sid:
            return s.container_path or re.sub(r"^(?:\.\./)+", "", s.path)
    return str(sid)


def _event(rub: S.Rubric, ev, end: bool = False) -> str:
    if isinstance(ev, (list, tuple)):
        return ("the earliest of " if end else "the later of ") + " and ".join(_event(rub, x) for x in ev)
    if isinstance(ev, dict) and len(ev) == 1:
        ((which, q),) = ev.items()
        q = q if isinstance(q, dict) else {}
        name = {"repo_edit": "repository edit", "valid_run": "valid test run", "artifact_write": "artifact write"}.get(str(q.get("fact")), str(q.get("fact")))
        others = q.get("paths_not_in") if isinstance(q.get("paths_not_in"), list) else [q.get("paths_not_in")]
        flt = [
            f
            for f, on in (
                ("of a file that existed at BASE_SHA", q.get("created") is False),
                ("of a new file", q.get("created") is True),
                ("of a test file", q.get("test_paths") is True),
                ("of a non-test file", q.get("test_paths") is False),
                ("in the final change", bool(q.get("final"))),
                ("other than " + " / ".join(_sel(x, rub) for x in others), "paths_not_in" in q),
            )
            if on
        ]
        return f"the {which} {name}" + (f" ({', '.join(flt)})" if flt else "")
    ev = str(ev)
    fixed = {
        "start": "the start of the run",
        "end": "the end of the run",
        "first_repo_write": "the first repository edit",
        "last_repo_write": "the last repository edit",
        "last_change_write": "the last edit to a non-test code file of the final change",
    }
    if ev in fixed:
        return fixed[ev]
    kind, _, arg = ev.partition(":")
    if kind == "read":
        return f"reading {_doc(rub, arg)}"
    if kind in ("write", "first_write", "last_write"):
        return f"{'' if kind == 'write' else kind.split('_')[0] + ' '}writing {_art(rub, arg)}"
    if kind in ("stage_start", "stage_end"):
        return f"the {'start' if kind == 'stage_start' else 'end'} of {arg}"
    return ev


def _window(rub: S.Rubric, w, stage: str) -> str:
    if w is None:
        return f"during {stage}" if stage != "global" else "anywhere in the run"
    if isinstance(w, str):
        return f"during {w[6:]}" if w.startswith("stage:") else w
    if isinstance(w, (list, tuple)) and len(w) == 2:
        return f"between {_event(rub, w[0])} and {_event(rub, w[1], end=True)}"
    return str(w)


def _sel(s, rub: S.Rubric | None = None) -> str:
    """A selector in words: which field / ids / run fact it reads."""
    if isinstance(s, list):
        return " or ".join(_sel(x, rub) for x in s)
    if not isinstance(s, dict):
        return str(s)
    k = next((x for x in s if x not in ("normalize", "window")), "?")
    v = s.get(k)
    art = lambda a: _art(rub, a) if rub is not None else str(a)  # noqa: E731
    if isinstance(v, dict) and k in ("field", "field_list"):
        return f"`{v.get('label')}` under `{v.get('section')}` of {art(v.get('artifact'))}"
    if isinstance(v, dict) and k in ("section_text", "section_lines"):
        return f"`{v.get('section')}` of {art(v.get('artifact'))}"
    if isinstance(v, dict) and k == "ids":
        return f"ids `{v.get('pattern')}`" + (f" in `{v.get('section')}`" if v.get("section") else "") + f" of {art(v.get('artifact'))}"
    if isinstance(v, dict) and k == "headings":
        return f"level-{v.get('level')} headings `{v.get('pattern')}` of {art(v.get('artifact'))}"
    if isinstance(v, dict) and k == "keyed_ids":
        return f"(key, ids) pairs `{v.get('pattern')}`" + (f" in `{v.get('section')}`" if v.get("section") else "") + f" of {art(v.get('artifact'))}"
    if k == "fact":
        name = v.get("name") if isinstance(v, dict) else v
        w = v.get("window") if isinstance(v, dict) else s.get("window")
        final = " (those in the final change)" if isinstance(v, dict) and v.get("final") else ""
        return f"the run's {name}{final}" + (f" {_window(rub, w, 'global')}" if w is not None and rub is not None else "")
    if k == "literal":
        return f"{v}"
    return f"{k}({v})"


def _listed(v) -> list:
    """A parameter that is one value or a list of them (``before: write:plan`` or ``before: [read:A, read:B]``)."""
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def what(it: S.Item, rub: S.Rubric) -> str:
    """One imperative line saying what the item asks of the agent."""
    p = it.check.params
    art = _art(rub, it.target.ref) if it.target.type == "artifact" else ""
    k = it.check.kind
    cond = " (conditional)" if it.applies_when is not None else ""
    if k == "artifact_exists":
        a = rub.artifacts.get(it.target.ref)
        loc = " | ".join(x.replace("{artifact}", rub.roots.get("artifact", "{artifact}")) for x in a.locations) if a else art
        return f"write {loc}" + (" before the stage ends" if it.target.state == "stage_end" else "") + cond
    if k == "path_match":
        return f"name {art} to match `{p.get('pattern')}`" + cond
    if k == "frontmatter":
        vals = ", ".join(f"{a}: {b}" for a, b in (p.get("values") or {}).items())
        return f"start {art} with frontmatter keys {p.get('keys')}" + (" (exactly these)" if p.get("exact") else "") + (f" [{vals}]" if vals else "") + cond
    if k == "section_present":
        return f"keep heading `{'#' * int(p.get('level') or 2)} {p.get('heading')}` in {art}" + cond
    if k == "label_present":
        return f"keep label `{p.get('label')}:` under `{p.get('section')}` in {art}" + cond
    if k == "field_literal":
        ref = " -- and make it true: the run must not refute it" if p.get("refuted_by") is not None else ""
        return f"write `{(p.get('label') + ': ') if p.get('label') else ''}{p.get('text')}` under `{p.get('section')}` in {art}{ref}" + cond
    if k == "field_filled":
        na = it.none_allowed
        none = "only if the run agrees" if isinstance(na, dict) else {"yes": "allowed", "no": "not allowed", "unspecified": "accepted (the documents are silent)"}.get(str(na), str(na))
        pb = p.get("per_block")
        blk = (f" in every `{pb.get('heading_pattern')}` block" if isinstance(pb, dict) and pb.get("heading_pattern") else " in every sub-block") if pb else ""
        vocab = f" as {p.get('none_vocab')}" if p.get("none_vocab") else ""
        return f"fill `{p.get('label') or '(the section)'}` under `{p.get('section')}`{blk} in {art} (none: {none}{vocab})" + cond
    if k == "field_enum":
        return f"set `{p.get('label')}` under `{p.get('section')}` in {art} to one of {p.get('values')}" + (" (prefix)" if p.get("prefix_ok") else "") + cond
    if k == "field_type":
        if p.get("type") == "test_selection":
            return f"record in `{p.get('label')}` under `{p.get('section')}` of {art} a test command that selects the tests (not the whole suite)" + cond
        t = {
            "command_run": "the command of a valid test run" if p.get("run_kind") == "test" else "a command actually run",
            "repo_path": "repository paths that exist",
            "test_id": "test ids that appear in a valid run",
            "failed_test_id": "test ids that failed in a valid run" + (f" (or are listed in {_sel(p['listed_in'], rub)})" if p.get("listed_in") else ""),
        }.get(str(p.get("type")), str(p.get("type")))
        return f"record in `{p.get('label')}` under `{p.get('section')}` of {art} {t} {_window(rub, p.get('window'), it.stage)}" + cond
    if k == "item_format":
        rng = f" (at least {p.get('min')})" if p.get("min") else ""
        of = f" (every line matching `{p.get('of_pattern')}`)" if p.get("of_pattern") else ""
        return f"write lines matching `{p.get('pattern')}`" + (f" under `{p.get('section')}`" if p.get("section") else "") + f" in {art}{rng}{of}" + cond
    if k == "no_template_residue":
        return f"replace every template placeholder in {art} ({len(p.get('patterns', []))} patterns)" + cond
    if k == "not_template_copy":
        return f"do not keep the template's sample lines under `{p.get('section')}` in {art}" + cond
    if k == "cross_ref":
        return f"{_sel(p.get('left'), rub)} must be {p.get('relation')} {_sel(p.get('right'), rub)}" + (f" [{p.get('normalize')}]" if p.get("normalize") else "") + cond
    if k == "doc_read_first":
        return f"read {_doc(rub, p.get('doc'))} before any other action"
    if k == "doc_read":
        extra = [x for x, on in (("one document per step", p.get("single_doc")), ("not before the previous stage's artifact is written", p.get("no_read_ahead"))) if on]
        return f"read {_doc(rub, p.get('doc'))} {_window(rub, p.get('window'), it.stage)}" + (f" ({'; '.join(extra)})" if extra else "")
    if k == "order":
        inv = f" (voided by: {', '.join(_listed(p.get('invalidate')))})" if p.get("invalidate") else ""
        if not p.get("chain") and (p.get("before") or p.get("after")):  # every `before` event precedes every `after` event
            return " and ".join(_event(rub, x) for x in _listed(p.get("before"))) + " before " + " and ".join(_event(rub, x) for x in _listed(p.get("after"))) + inv
        return "in this order: " + " -> ".join(_event(rub, x) for x in _listed(p.get("chain"))) + inv
    if k == "write_discipline":
        mode = {"once": "in one full write", "append_only": "append-only", "no_rewrite": "without rewriting it"}.get(str(p.get("mode")), p.get("mode"))
        return f"write {_art(rub, p.get('artifact') or it.target.ref)} {mode} {_window(rub, p.get('window'), it.stage)}"
    if k == "exec_evidence":
        cmd = f" with {_sel(p.get('command_in'), rub)}" if p.get("command_in") else ""
        return f"run the {p.get('kind', 'test')}s (>= {p.get('min_count', 1)} valid run{cmd}) {_window(rub, p.get('window'), it.stage)}" + cond
    if k == "prohibited_action":
        verbs = {
            "execute": "run tests or execute",
            "repo_write": "edit the repository",
            "source_write": "edit a file that existed at BASE_SHA",
            "test_file_write": "edit test files",
            "install": "install packages",
            "full_suite": "run the whole test suite",
            "command": "run commands matching",
        }
        what_ = verbs.get(str(p.get("action")), p.get("action"))
        sel = f" {_sel(p.get('selector'), rub)}" if p.get("selector") else ""
        pat = f" `{p.get('pattern')}`" if p.get("pattern") else ""
        return f"do not {what_}{sel}{pat} {_window(rub, p.get('window'), it.stage)}" + cond
    if k == "unimplemented":
        return f"(unimplemented) {it.note}"
    if "." in k and isinstance(p.get("steps"), list):  # plugin kinds with a step list (aidlc.executed)
        steps = []
        for st in p["steps"]:
            key = next((x for x in st if x != "optional_if_none"), "?")
            v = st.get(key)
            desc = {"exec_of": "execute", "command_in": "run", "valid_run": "a valid run of", "read_of": "read", "write_of": "write"}.get(key, key)
            if key == "valid_run" and isinstance(v, dict) and (v.get("command_in") or v.get("same_selection_as")):
                target = f"the tests selected by {_sel(v['same_selection_as'], rub)}" if v.get("same_selection_as") else _sel(v.get("command_in"), rub)
            else:
                target = _sel(v, rub) if key != "valid_run" else f"{(v or {}).get('kind', 'test')}s"
            steps.append(f"{desc} {target}" + (" (unless none)" if st.get("optional_if_none") else ""))
        return ("in order: " if p.get("in_order") else "") + ", then ".join(steps) + f" {_window(rub, p.get('window'), it.stage)}" + cond
    return f"{k} {json.dumps(p, default=str)}"


def render_md(rub: S.Rubric, inp: Inputs, report: dict) -> str:
    src = {s.id: s for s in rub.sources}

    def cite(it: S.Item) -> str:
        parts = []
        for s in it.sources[:3]:
            parts.append(f"{_doc(rub, s.doc)}:{s.lines[0]}" + (f"-{s.lines[1]}" if s.lines[1] != s.lines[0] else ""))
        return "; ".join(parts) + (f" (+{len(it.sources) - 3})" if len(it.sources) > 3 else "")

    out = [f"# {rub.workflow}: rubric (what the agent is asked to do)", ""]
    g = rub.generated
    llm = g.get("llm", {})
    out.append(f"Generated by {g.get('tool')} on {g.get('at')}; LLM {llm.get('backend', '-')} {llm.get('model', '')}; kinds from the {g.get('kinds')} table; stage model {g.get('stage_model')}.")
    out.append(f"{len(rub.items)} items: {report.get('by_requirement')} | scope {report.get('by_scope')} | derived_by {report.get('by_derived_by')}.")
    out.append("")
    for st in [*rub.stages, None]:
        sid = st.id if st else "global"
        its = rub.items_for(sid)
        if not its:
            continue
        doc = f" — governed by {src[st.doc].container_path or src[st.doc].path}" if st and st.doc and st.doc in src else ""
        out += [f"## {sid}{doc}", ""]
        for it in its:
            flag = "" if it.weight else " _(weight 0)_"
            flag += " _(log only)_" if it.log_only else ""
            note = f" ({it.note})" if it.derived_by == "manual" and it.note else ""
            out.append(f"- [{it.requirement}] {what(it, rub)}{note} — {cite(it)}{flag}")
        out.append("")
    adapter = [it for it in rub.items if it.derived_by == "adapter"]
    out += ["## Adapter-derived items", ""]
    if adapter:
        out += ["| id | what | cited | weight |", "|---|---|---|---|"]
        out += [f"| `{it.id}` | {what(it, rub)} | {cite(it)} | {it.weight:g} |" for it in adapter]
    else:
        out.append("(none)")
    out += ["", "## Unimplemented", ""]
    un = [it for it in rub.items if it.check.kind == "unimplemented"]
    if un:
        out += ["| id | statement | cited | why |", "|---|---|---|---|"]
        out += [f"| `{it.id}` | {it.sources[0].quote[:100]} | {cite(it)} | {it.note} |" for it in un]
    else:
        out.append("(none)")
    out += ["", "## Excluded on review (generator.yaml `exclude`)", ""]
    exc = report.get("excluded") or []
    if exc:
        out += ["| statement | kind | cited | reason |", "|---|---|---|---|"]
        for x in exc:
            src0 = x["sources"][0] if x.get("sources") else {}
            where = f"{_doc(rub, src0.get('doc', ''))}:{(src0.get('lines') or [0])[0]}" if src0 else ""
            out.append(f"| {x['statement']} | {x['kind']} | {where} | {x['reason']} |")
    else:
        out.append("(none)")
    out += ["", "## Conflicts", ""]
    if rub.conflicts:
        out += ["| type | items | description |", "|---|---|---|"]

        def where(c: dict) -> str:
            return "; ".join(f"{_doc(rub, inp.manifest.resolve(r['path']).id if inp.manifest.resolve(r['path']) else r['path'])}:{r['lines'][0]}" for r in c.get("sources") or [])

        out += [
            f"| {c.get('type', '')} | {', '.join(c.get('items', [])) or where(c)} | {c.get('description', '')} {('-> ' + c['resolution']) if c.get('resolution') else ''} |".replace("\n", " ")
            for c in rub.conflicts
        ]
    else:
        out.append("(none)")
    out += _selftest_md(rub.generated.get("selftest"))
    out += ["", "## Appendix", "", "### MAY / optional (no item)", ""]
    out += [f"- {_cite_d(m, src)}: {m.get('quote', '')[:140]} — {m.get('reason', '')}" for m in rub.appendix.get("may_items", [])] or ["(none)"]
    out += ["", "### Implicit (capped at should)", ""]
    out += [f"- `{m.get('id')}` {m.get('reason', '')}" for m in rub.appendix.get("implicit_items", [])] or ["(none)"]
    out += ["", "### Statements not itemized", ""]
    out += [f"- {_cite_d(m, src)}: {m.get('quote', '')[:140]} — {m.get('reason', '')}" for m in rub.appendix.get("unitemized_statements", [])] or ["(none)"]
    out += ["", "### System-prompt sentences not itemized (generic harness sections: allowed context)", ""]
    out += [f"- {_cite_d(m, src)} [{m.get('modality', '')}]: {m.get('text', '')[:140]}" for m in rub.appendix.get("sp_generic_unitemized", [])] or ["(none)"]
    if inp.rejected:
        out += ["", "## Rejected candidates (G6/G7)", "", "| id | origin | reason | detail |", "|---|---|---|---|"]
        out += [f"| `{r['id']}` | {r['origin']} | {r['reason']} | {str(r.get('detail', ''))[:160].replace('|', '/')} |" for r in inp.rejected]
    return "\n".join(out) + "\n"


def _selftest_md(st: dict | None) -> list[str]:
    """The G9 result (``generated.selftest``) as a table: each mutation, its score and the bound it is held to."""
    if not st:
        return []
    out = ["", "## Self-test (G9)", "", f"Status **{st.get('status')}**; golden {st.get('golden')} ({st.get('golden_fixture', '')}).", ""]
    out += ["| mutation | kind | compliance | bound | status |", "|---|---|---|---|---|"]
    for r in st.get("results") or []:
        ch = r.get("check") or {}
        bound = f"{ch.get('metric', '')} {ch.get('op', '')} {ch.get('bound', '')}" if ch else str(r.get("note") or r.get("error") or "")
        out.append(f"| {r.get('mutation')} | {r.get('kind')} | {r.get('compliance', '')} | {bound} | {r.get('status')} |")
    out += [f"- FAIL {f}" for f in st.get("failures") or []]
    return out


def _cite_d(m: dict, src: dict) -> str:
    d = m.get("doc", "")
    p = (src[d].container_path or re.sub(r"^(?:\.\./)+", "", src[d].path)) if d in src else d
    ln = m.get("lines") or [m.get("line_start"), m.get("line_end")]
    return f"{p}:{ln[0]}" + (f"-{ln[1]}" if ln and len(ln) > 1 and ln[1] != ln[0] else "")


# ----------------------------------------------------------------------------------------------
def check(rubric_path: Path, manifest: Manifest | None = None) -> list[str]:
    """Problems with a committed rubric: schema / params, stale lock, quotes that no longer match."""
    from .ground import quote_matches
    from .vocab import kinds as kind_table

    probs: list[str] = []
    try:
        rub = S.load(rubric_path)
    except S.RubricError as e:
        return [f"rubric: {e}"]
    table, origin = kind_table(rub.workflow)
    try:
        validate_kinds(rub, table, origin)
    except S.RubricError as e:
        probs.append(f"params: {e}")
    for it in rub.items:
        if it.scope == "common" and not it.template:
            probs.append(f"{it.id}: common item without a C-xx template")
    lock_path = rubric_path.with_name("rubric.lock")
    if not lock_path.is_file():
        probs.append("rubric.lock missing")
    else:
        lk = json.loads(lock_path.read_text())
        if lk.get("rubric_sha256") != hashlib.sha256(rubric_path.read_bytes()).hexdigest():
            probs.append("rubric.yaml changed after generation (lock sha mismatch)")
        conf = lk.get("config") or {}
        conf_path = rubric_path.parent.parent / conf["path"] if conf.get("path") else None
        if conf_path is not None and conf_path.is_file() and conf.get("sha256") and hashlib.sha256(conf_path.read_bytes()).hexdigest() != conf["sha256"]:
            probs.append(f"{conf['path']} changed after generation (regenerate)")
        if manifest is not None:
            now = {e.path: e.sha256 for e in manifest.entries}
            for p, sha in lk.get("sources", {}).items():
                if p not in now:
                    probs.append(f"source removed: {p}")
                elif now[p] != sha:
                    probs.append(f"source changed: {p} (regenerate)")
            for p in now:
                if p not in lk.get("sources", {}):
                    probs.append(f"source added: {p} (regenerate)")
    if manifest is not None:
        for it in rub.items:
            for s in it.sources:
                e = manifest.by_id(s.doc)
                if e is None:
                    probs.append(f"{it.id}: source {s.doc} not in the manifest")
                elif not quote_matches(s.quote, e.text(*s.lines)):
                    probs.append(f"{it.id}: quote no longer matches {e.path}:{s.lines[0]}-{s.lines[1]}")
    return probs
