"""G6: every candidate item is checked against the files the agent sees, by rule (DESIGN P1-P6).

A model proposes; this module decides. A candidate is rejected, or its requirement lowered, for
reasons a reviewer can re-check by reading the cited lines:

    kind/params     the kind exists and gets exactly its parameters; stage/target/state are defined
    quotes          every cited quote matches its lines after whitespace normalisation ("..." elides)
    overrides       a generator.yaml override drops the statement or re-grounds it on an adapter line
    system prompt   generic harness sections are context, never a source (§10.3)
    adapters        an item resting only on text we wrote: the lines must be whitelisted, the kind may not
                    be frontmatter/section/field_literal/field_enum/prohibited_action, at most should,
                    weight ``adapter_weight`` (0 = log only); ``derived_by: adapter``
    parameters      literal parameters (headings, labels, enum values, regex literals) appear in the cited
                    lines or the artifact's template; a parameter only an implementation shows is a
                    tightening ``impl_refs`` may not introduce; doc parameters name a cited or stage doc
    modality        the dictionary modality of the cited sentences (:func:`parse.modality`): MAY ->
                    no item; implicit or SHOULD -> at most should; MUST -> must unless the model lowered it
                    with a reason (a ``downgrade_reason``, or its note saying the rule is inferred: P2,
                    an inferred rule is never must, whatever the cited sentence's own modality)
    evaluability    windows, events, selectors and predicates are in the refs language; an enumerated
                    parameter takes a value the kind implements (``choices``: a plugin's rule names); a
                    ``path_match`` pattern fully matches some path of its artifact (a model's fragment
                    such as ``/archive`` would fail every run)
    anchors         a cross_ref with no side the agent did not write is downgraded to should

Every rejection and change is logged with its reason; nothing is fixed up silently.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from ..schema import AVAILABILITY, STATES, SourceRef
from . import items as I
from .config import GeneratorConfig
from .manifest import Manifest
from .parse import Parsed, modality, strength
from .vocab import ADAPTER_FORBIDDEN, KindSpec, check_event, check_params, check_predicate, check_selector, check_window, is_anchor

_WS = re.compile(r"\s+")
_INFERRED = re.compile(r"\b(?:inferred|implicit(?:ly)?|not (?:explicitly )?stated)\b", re.I)


def ws(s: str) -> str:
    return _WS.sub(" ", s or "").strip()


def quote_matches(quote: str, text: str) -> bool:
    """``quote`` occurs in ``text`` after whitespace normalisation; ``...``/``…`` may elide text between parts (in order)."""
    q, t = ws(quote), ws(text)
    if not q:
        return False
    parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", q) if p]
    pos = 0
    for p in parts:
        i = t.find(p, pos)
        if i < 0:
            return False
        pos = i + len(p)
    return True


def regex_literals(rx: str) -> list[str]:
    """Literal fragments (>= 3 chars, with a letter) a regex can only match by containing."""
    out: list[str] = []
    cur: list[str] = []

    def flush():
        if cur:
            out.append("".join(cur))
            cur.clear()

    i, n = 0, len(rx)
    while i < n:
        c = rx[i]
        if c == "\\" and i + 1 < n:
            nx = rx[i + 1]
            if nx in "dDsSwWbBAZz" or nx.isdigit() or nx in "nrtfv":
                flush()
            else:
                cur.append(nx)
            i += 2
            continue
        if c == "[":
            flush()
            j = i + 1
            if j < n and rx[j] == "^":
                j += 1
            if j < n and rx[j] == "]":
                j += 1
            while j < n and rx[j] != "]":
                j += 2 if rx[j] == "\\" else 1
            i = j + 1
            continue
        if c == "(":
            flush()
            if rx[i + 1 : i + 2] == "?":
                m = re.match(r"\(\?(?:[:=!]|<[=!]|P<\w+>|[aiLmsux]+\)|[aiLmsux-]+:)", rx[i:])
                i += len(m.group(0)) if m else 2
            else:
                i += 1
            continue
        if c in ")|^$.":
            flush()
            i += 1
            continue
        if c in "*+?":
            if cur:
                cur.pop()
            flush()
            i += 1
            continue
        if c == "{":
            m = re.match(r"\{\d+(?:,\d*)?\}", rx[i:])
            if m:
                if cur:
                    cur.pop()
                flush()
                i += len(m.group(0))
                continue
        cur.append(c)
        i += 1
    flush()
    return [s for s in (x.strip() for x in out) if len(s) >= 3 and re.search(r"[A-Za-z]", s)]


@dataclass
class GroundResult:
    accepted: list[I.Cand] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    may_items: list[dict] = field(default_factory=list)
    implicit_items: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


class Grounder:
    def __init__(self, cfg: GeneratorConfig, manifest: Manifest, parsed: dict[str, Parsed], model: dict, kinds: dict[str, KindSpec]):
        self.cfg = cfg
        self.m = manifest
        self.parsed = parsed
        self.model = model
        self.kinds = kinds
        self.stages = {s["id"] for s in model.get("stages", [])}
        self.artifacts = set(model.get("artifacts", {}))
        self.sources = {e.id for e in manifest.entries}

    # ------------------------------------------------------------------------------------------
    def run(self, cands: list[I.Cand]) -> GroundResult:
        res = GroundResult()
        for c in cands:
            try:
                reason = self.one(c, res)
            except (TypeError, ValueError, KeyError, AttributeError, IndexError) as e:  # a shape no check above foresaw: the model's output never stops G6
                reason = "malformed", f"{type(e).__name__}: {e}"[:200]
            if reason:
                res.rejected.append({"id": c.id, "origin": c.origin, "statement": c.statement, "kind": c.item.check.kind, "reason": reason[0], "detail": reason[1]})
                res.log.append(f"reject {c.id}: {reason[0]} {reason[1]}".rstrip())
            else:
                res.accepted.append(c)
        return res

    def one(self, c: I.Cand, res: GroundResult) -> tuple[str, str] | None:
        it = c.item
        kind = it.check.kind
        errs = check_params(kind, it.check.params, self.kinds)
        if errs:
            return "params", "; ".join(errs)
        if it.stage != "global" and not (isinstance(it.stage, str) and it.stage in self.stages):
            return "stage", f"{it.stage!r} is not a stage"
        if it.target.type not in ("artifact", "action") or it.target.state not in STATES:
            return "target", f"{it.target}"
        if it.target.type == "artifact" and not (isinstance(it.target.ref, str) and it.target.ref in self.artifacts):
            return "target", f"artifact {it.target.ref!r} undefined"
        if not it.sources:
            return "sources", "no sources"
        # quotes ------------------------------------------------------------------------------
        fixed = []
        for s in it.sources:
            e = self.m.resolve(s.doc)
            if e is None:
                return "sources", f"{s.doc!r} is not in the manifest"
            if not (1 <= s.lines[0] <= s.lines[1] <= len(e.lines())):
                return "sources", f"{e.path}:{s.lines[0]}-{s.lines[1]} outside the file ({len(e.lines())} lines)"
            text = e.text(*s.lines)
            if not quote_matches(s.quote, text):
                where = self._find(e, s.quote)
                return "quote mismatch", f"{e.path}:{s.lines[0]}-{s.lines[1]} {s.quote[:80]!r}" + (f" (found at {where})" if where else "")
            fixed.append(SourceRef(doc=e.id, lines=s.lines, quote=s.quote))
        it.sources = fixed
        # overrides ---------------------------------------------------------------------------
        for o in self.cfg.overrides:
            hit = next((s for s in it.sources if o.matches(self.m.by_id(s.doc).path, s.quote + " " + self.m.by_id(s.doc).text(*s.lines))), None)
            if hit is None:
                continue
            if o.action == "drop":
                return "override", f"dropped: {o.reason}"
            e = self.m.resolve(o.adapter.path) if o.adapter else None
            if e is None:
                return "override", f"replace target {o.adapter.path if o.adapter else '?'} not in the manifest"
            it.sources = [s for s in it.sources if s is not hit] + [SourceRef(doc=e.id, lines=o.adapter.lines, quote=o.adapter.quote or e.text(*o.adapter.lines).strip())]
            c.log.append(f"override: {o.reason}")
        # roles -------------------------------------------------------------------------------
        sp_generic = [s for s in it.sources if self.m.by_id(s.doc).role == "system_prompt" and self.m.by_id(s.doc).section_role(s.lines[0]) != "workflow"]
        grounding = [s for s in it.sources if s not in sp_generic]
        if not grounding:
            return "system prompt", "only generic system-prompt sections cited (context, not a source)"
        upstream = [s for s in grounding if self.m.by_id(s.doc).role not in self.cfg.adapter_roles]
        manual = c.origin == "manual"
        if (not upstream and it.derived_by != "manual") or (manual and it.derived_by == "adapter"):
            if kind in ADAPTER_FORBIDDEN:
                return "adapter", f"adapter-only {kind} item (P1a)"
            for s in grounding:
                e = self.m.by_id(s.doc)
                if e.role not in self.cfg.adapter_roles:  # an upstream line beside the adapter text (a reviewed item)
                    continue
                if not any(a.covers(e.path, s.lines) or a.covers(e.docs_rel or e.path, s.lines) for a in self.cfg.adapters):
                    return "adapter", f"{e.path}:{s.lines[0]}-{s.lines[1]} is adapter text not in the adapter whitelist"
            if it.requirement == "must":
                it.requirement = "should"
                c.log.append("adapter-only: must -> should")
            it.derived_by = "adapter"
            if manual:  # a reviewed item: its weight / log_only are the reviewer's decision (rubric.md lists it with them)
                pass
            elif self.cfg.adapter_weight == 0:
                it.log_only = True
            else:
                it.weight = self.cfg.adapter_weight
            if "adapter-derived" not in (it.note or ""):
                it.note = (it.note + " " if it.note else "") + "adapter-derived"
        # parameters --------------------------------------------------------------------------
        ref_text = self._ref_text(it)
        err = self._params(it, ref_text)
        if err:
            if it.impl_refs:
                return "impl_refs", f"impl_refs may only relax: {err}"
            return "param", err
        # modality ----------------------------------------------------------------------------
        if it.derived_by != "manual" and not manual:
            m, ev, where = "implicit", "", ""
            for s in upstream or grounding:
                if not self._authority(s):
                    continue
                mm, mev = modality(s.quote)
                if strength(mm) > strength(m):
                    m, ev, where = mm, mev, f"{s.doc}:{s.lines[0]}"
            if m == "may":
                res.may_items.append({"id": it.id, "statement": c.statement, "doc": it.sources[0].doc, "lines": list(it.sources[0].lines), "quote": it.sources[0].quote, "reason": f"MAY ('{ev}')"})
                return "modality", f"MAY ('{ev}' at {where}): appendix, no item"
            if m in ("implicit", "should") and it.requirement == "must":
                it.requirement = "should"
                c.log.append(f"{m}: must -> should")
                if m == "implicit":
                    res.implicit_items.append({"id": it.id, "statement": c.statement, "reason": "implicit never must"})
            elif m in ("must", "prohibition") and it.requirement == "should" and not c.downgrade_reason and it.derived_by != "adapter":
                if _INFERRED.search(it.note or ""):
                    c.downgrade_reason = "the model's note says the rule is inferred (P2: never must)"
                    res.implicit_items.append({"id": it.id, "statement": c.statement, "reason": "inferred (model note): kept should"})
                else:
                    it.requirement = "must"
                    c.log.append(f"dictionary {m} ('{ev}'), no downgrade reason: should -> must")
            dict_ev = f"dict {m}" + (f" ('{ev}' at {where})" if ev else "")
            if dict_ev not in it.modality_evidence:
                it.modality_evidence = "; ".join(x for x in (it.modality_evidence, dict_ev) if x)
            if c.downgrade_reason and it.requirement == "should" and c.downgrade_reason not in it.modality_evidence:
                it.modality_evidence += f"; lowered: {c.downgrade_reason}"
        # evaluability ------------------------------------------------------------------------
        for name, pred in (("applies_when", it.applies_when), ("none_allowed.if", it.none_allowed.get("if") if isinstance(it.none_allowed, dict) else None)):
            if pred is not None:
                errs = check_predicate(pred, self.stages, self.artifacts, self.sources)
                if errs:
                    return "applies_when" if name == "applies_when" else "none_allowed", "; ".join(errs[:3])
        if isinstance(it.none_allowed, dict) and set(it.none_allowed) != {"if"}:
            return "none_allowed", f"{it.none_allowed}"
        if not isinstance(it.none_allowed, dict) and it.none_allowed not in ("yes", "no", "unspecified", "-"):
            return "none_allowed", f"{it.none_allowed!r}"
        why = self._semantics(it)
        if why:
            return "semantics", why
        if kind == "cross_ref" and not (is_anchor(it.check.params.get("left")) or is_anchor(it.check.params.get("right"))):
            if it.requirement == "must":
                it.requirement = "should"
            c.log.append("cross_ref without an anchor the agent did not write: should")
            it.note = (it.note + " " if it.note else "") + "unanchored cross_ref"
        it.availability = [a for a in it.availability if a in AVAILABILITY] or ["sandbox_file"]
        return None

    # ------------------------------------------------------------------------------------------
    def _semantics(self, it) -> str:
        """Items a kind cannot mean, whatever the text says (each would fail or pass every run alike)."""
        kind, p = it.check.kind, it.check.params
        if kind == "doc_read_first":
            entry = next((e for e in self.m.entries if e.docs_rel and e.docs_rel == self.m.entry_doc), None)
            if entry is None or p.get("doc") != entry.id:
                return f"doc_read_first checks the run's first action; only the entry document ({entry.id if entry else '?'}) can be read first -- use doc_read for a stage document"
        if kind == "path_match":
            aid = p.get("artifact") or it.target.ref
            locs = (self.model.get("artifacts", {}).get(aid) or {}).get("locations") or []
            names = {*(self.model.get("vars") or {}), "DATE"}
            if locs and not any(f"{{{n}}}" in loc for loc in locs for n in names):
                return f"artifact {aid} has fixed locations {locs}: where it is found already fixes its path (artifact_exists)"
            samples = _path_samples(locs, str(p.get("relative_to") or "artifact"), self.model.get("vars") or {})
            if it.derived_by != "manual" and samples and not any(_path_matches(str(p.get("pattern", "")), s) for s in samples):
                return f"pattern {p.get('pattern')!r} never fully matches a path of {aid} (path_match matches the whole root-relative path, e.g. {samples[0]!r})"
        return ""

    def _authority(self, s: SourceRef) -> bool:
        """Whether a cited line can carry modality: not a template skeleton line (an HTML comment in a template can)."""
        e = self.m.by_id(s.doc)
        if e.role != "template":
            return True
        p = self.parsed.get(e.id)
        return bool(p) and any(a <= s.lines[0] and s.lines[1] <= b for a, b in p.comments)

    def _find(self, e, quote: str) -> str:
        q = ws(quote)
        if not q:
            return ""
        lines = e.lines()
        for a in range(1, len(lines) + 1):
            for b in range(a, min(a + 8, len(lines)) + 1):
                if quote_matches(q, e.text(a, b)):
                    return f"{a}-{b}"
        return ""

    def _ref_text(self, it) -> str:
        parts = [self.m.by_id(s.doc).text(*s.lines) for s in it.sources]
        arts = set()
        if it.target.type == "artifact":
            arts.add(it.target.ref)
        for sel in _selectors(it.check.params):
            for v in sel.values() if isinstance(sel, dict) else []:
                if isinstance(v, dict) and v.get("artifact"):
                    arts.add(v["artifact"])
        for a in arts:
            tpl = self.model.get("artifacts", {}).get(a, {}).get("template")
            e = self.m.by_id(tpl) if tpl else None
            if e:
                parts.append("\n".join(e.lines()))
        return ws("\n".join(parts)).lower()

    def _params(self, it, ref: str) -> str | None:
        kind = it.check.kind
        p = it.check.params
        ks = self.kinds.get(kind)
        if ks is None:
            return None
        for name in ks.literal_params:
            for v in _strings(p.get(name)):
                if ws(v).lower() not in ref:
                    return f"{name}={v!r} not in the cited lines or the template"
        if kind == "frontmatter" and isinstance(p.get("values"), dict):
            for k, v in p["values"].items():
                vals = [v] if not isinstance(v, dict) else []
                frags = regex_literals(str(v["regex"])) if isinstance(v, dict) and "regex" in v else []
                for x in [*_strings(vals), *frags]:
                    if ws(str(x)).lower() not in ref:
                        return f"frontmatter value {k}={x!r} not in the cited lines or the template"
        for name in ks.regex_params:
            for rx in _strings(p.get(name)):
                for frag in regex_literals(rx):
                    if ws(frag).lower() not in ref:
                        return f"{name} literal {frag!r} (from {rx!r}) not in the cited lines or the template"
        for name in ("doc",):
            if name in p:
                if not isinstance(p[name], str) or p[name] not in self.sources:
                    return f"doc {p[name]!r} is not a source id"
                if not self._doc_grounded(p[name], it, ref):
                    return f"doc {p[name]!r} is neither named in the cited lines nor the stage's document"
        if "window" in p:
            errs = check_window(p["window"], self.stages, self.artifacts, self.sources)
            if errs:
                return "; ".join(errs)
        for name in ("chain", "before", "after"):
            raw = p.get(name)
            if any(not isinstance(ev, str) for ev in (raw if isinstance(raw, (list, tuple)) else [raw] if raw is not None else [])):
                return f"{name}: order events are event names (read:<SOURCE>, write:<ARTIFACT>, ...), not fact events"
            for ev in _strings(p.get(name)):
                errs = check_event(ev, self.stages, self.artifacts, self.sources)
                if errs:
                    return "; ".join(errs)
        for name in ("left", "right", "command_in", "selector", "paths_in", "listed_in"):
            if name in p:
                errs = check_selector(p[name], self.stages, self.artifacts, self.sources)
                if errs:
                    return f"{name}: " + "; ".join(errs[:3])
                for lit in _selector_literals(p[name]):
                    if ws(lit).lower() not in ref and ws(lit).lower() not in self._artifact_template_text(p[name]):
                        return f"{name} literal {lit!r} not in the cited lines or the template"
        if "refuted_by" in p:
            errs = check_predicate(p["refuted_by"], self.stages, self.artifacts, self.sources)
            if errs:
                return "refuted_by: " + "; ".join(errs[:3])
        if kind in ("write_discipline", "artifact_exists") and p.get("artifact") and not (isinstance(p["artifact"], str) and p["artifact"] in self.artifacts):
            return f"artifact {p['artifact']!r} undefined (an artifact id)"
        return None

    def _doc_grounded(self, sid: str, it, ref: str) -> bool:
        e = self.m.by_id(sid)
        st = next((s for s in self.model.get("stages", []) if s["id"] == it.stage), None)
        if st and st.get("doc") == sid:
            return True
        names = [x for x in (e.container_path, e.path, e.docs_rel, e.path.rsplit("/", 1)[-1]) if x]
        return any(n.lower() in ref for n in names) or any(s.doc == sid for s in it.sources)

    def _artifact_template_text(self, sel) -> str:
        if isinstance(sel, list):
            return "\n".join(self._artifact_template_text(s) for s in sel)
        if not isinstance(sel, dict):
            return ""
        for v in sel.values():
            if isinstance(v, dict) and v.get("artifact"):
                tpl = self.model.get("artifacts", {}).get(v["artifact"], {}).get("template")
                e = self.m.by_id(tpl) if tpl else None
                if e:
                    return ws("\n".join(e.lines())).lower()
        return ""


# Values a location variable may take, tried in turn against the variable's own regex: kebab-case change and
# feature names, a numbered (spec-kit NNN-name) and a timestamped (YYYYMMDD-HHMMSS-name) feature directory.
_VAR_SAMPLES = ("add-feature", "001-add-feature", "20260101-120000-add-feature", "feature")
_LOC_VAR = re.compile(r"\{([A-Za-z_]\w*)\}")


def _path_samples(locs: list[str], root: str, variables: dict) -> list[str]:
    """One concrete root-relative path per location of an artifact (variables filled with a value their regex
    accepts, ``DATE`` a date): what ``path_match`` compares a pattern with. Locations outside ``root`` and
    variables no sample fits are left out (nothing to judge)."""
    out: list[str] = []
    for loc in locs:
        head = "{" + root + "}/"
        if not isinstance(loc, str) or not loc.startswith(head):
            continue
        rel, ok = loc[len(head) :], True

        def fill(m: re.Match) -> str:
            nonlocal ok
            name = m.group(1)
            if name == "DATE":
                return "2026-01-01"
            rx = str((variables.get(name) or {}).get("regex") or ".+")
            for v in _VAR_SAMPLES:
                try:
                    if re.fullmatch(rx.lstrip("^").rstrip("$"), v):
                        return v
                except re.error:
                    break
            ok = False
            return ""

        s = _LOC_VAR.sub(fill, rel)
        if ok and "{" not in s:
            out.append(s.rstrip("/"))
    return out


def _path_matches(pattern: str, path: str) -> bool:
    try:
        return fnmatch.fnmatchcase(path, pattern[5:]) if pattern.startswith("glob:") else re.fullmatch(pattern, path) is not None
    except re.error:
        return False


def ground(cands: list[I.Cand], cfg: GeneratorConfig, manifest: Manifest, parsed: dict[str, Parsed], model: dict, kinds: dict[str, KindSpec]) -> GroundResult:
    return Grounder(cfg, manifest, parsed, model, kinds).run(cands)


def _strings(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if isinstance(x, (str, int, float))]
    return []


def _selectors(p: dict) -> list:
    return [p[k] for k in ("left", "right", "command_in", "selector", "paths_in", "listed_in") if isinstance(p.get(k), dict)]


def _selector_literals(sel) -> list[str]:
    if isinstance(sel, list):  # a union of selectors (paths_not_in: [A3 Path, A4 Path])
        return [x for s in sel for x in _selector_literals(s)]
    if not isinstance(sel, dict):
        return []
    out = []
    for k, v in sel.items():
        if k in ("field", "field_list", "section_text", "section_lines") and isinstance(v, dict):
            out += [str(v[x]) for x in ("section", "label") if v.get(x)]
        elif k in ("ids", "keyed_ids") and isinstance(v, dict) and v.get("section"):
            out.append(str(v["section"]))
    return out
