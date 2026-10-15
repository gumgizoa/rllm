"""G2: template skeletons -> structure and content items, by rule (DESIGN §10 G2, §2 P1-P2).

A skeleton is the part of a document that shows what an artifact must look like: a whole template
file (spec-kit ``plan-template.md``, OpenSpec ``templates/*.md``) or a fenced block inside a rule
document (AI-DLC "Keep the frontmatter keys, the ``##`` headings, and the field prefixes exactly as
given"). Compiling it needs no model, only a decision per line, made by the workflow's
``classify`` rules:

    literal       text that must appear as written (headings, ``- Executed: no``)
    placeholder   text to replace (``[full path]``, ``<!-- ... -->``, ``$ARGUMENTS``)
    exemplar      sample content (repeated id lines ``- R1:``/``- R2:``, sample task lists, inner fences)

Lines become items: headings -> ``section_present``; label lines -> ``label_present`` plus the
value's item (``field_literal`` for a literal value, ``field_enum`` for ``[a | b]`` token
alternatives, ``field_filled`` otherwise, with ``none_allowed: yes`` only when the template itself
offers a none alternative such as ``[x | none]``, ``unspecified`` when it offers none); repeated id
lines -> one ``item_format``; placeholders -> one ``no_template_residue`` whose patterns are the
template's own placeholder texts (never a generic ``\\[...\\]``, which would hit ``[P]``,
``[US1]``, ``[satisfies R1]`` or ``[x]``). How binding an item is comes from the workflow's binding
sentence for the skeleton and the section's marker: a binding "must" sentence makes items must, a
marker alone (``*(mandatory)*``) or nothing makes them should, optional/conditional sections yield
no items (appendix). Every item cites the exact template lines it comes from, verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schema import SourceRef
from . import items as I
from .config import ClassifyRules, DocRef, GeneratorConfig, TemplateSpec
from .manifest import Entry, Manifest
from .parse import modality, structure

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LEAD = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)")
_BOX = re.compile(r"^\[[ xX]\]\s+")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_LABELS = (
    re.compile(r"^(?P<lead>\s*(?:[-*+]\s+)?)\*\*(?P<label>[^*\n\[\]<>]{1,60}?)\*\*\s*:\s*(?P<value>.*)$"),
    re.compile(r"^(?P<lead>\s*(?:[-*+]\s+)?)\*\*(?P<label>[^*\n\[\]<>]{1,60}?):\*\*\s*(?P<value>.*)$"),
    re.compile(r"^(?P<lead>\s*[-*+]\s+)(?P<label>[A-Za-z][\w /&()'.,-]{0,60}?)\s*:(?:\s+(?P<value>.*)|\s*$)"),
)
_ID = re.compile(r"^(?P<bold>\*\*)?(?:(?P<prefix>[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*)(?P<sep>[- ]?))?(?P<num>\d+)(?P<sub>(?:\.\d+)*)(?P<dot>\.(?!\d))?(?P<bold2>\*\*)?(?P<colon>:)?(?=\s|$|\[)")
_ID_LABEL = re.compile(r"[A-Z]{1,5}-?\d+")
_PAREN_ALTS = re.compile(r"\(([^()|\n]+(?:\s+\|\s+[^()|\n]+)+)\)")
_DESCRIPTIVE = re.compile(r"\b(?:e\.g|etc|which|what|how|the|full|verbatim|path|paths|command|description|statement|reasoning|one per line)\b", re.I)


@dataclass
class TLine:
    n: int
    raw: str
    kind: str = "text"  # blank | fm | heading | label | text | comment | exemplar | rule
    level: int = 0
    title: str = ""
    marker: str = ""
    addressable: bool = True
    label: str = ""
    value: str = ""
    group: int | None = None  # id group index
    parent: int | None = None  # index of the nearest heading line in the TLine list


@dataclass
class TemplateResult:
    cands: list[I.Cand] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    may_items: list[dict] = field(default_factory=list)


# ----------------------------------------------------------------------------------------------
def compile_all(cfg: GeneratorConfig, manifest: Manifest, stage_model: dict) -> TemplateResult:
    out = TemplateResult()
    for ts in cfg.templates:
        entry = manifest.resolve(ts.path)
        if entry is None:
            out.log.append(f"template {ts.id}: {ts.path} is not in the manifest")
            continue
        art = ts.artifact or next((a for a, d in (stage_model.get("artifacts") or {}).items() if d.get("template") == entry.id), None)
        if not art or art not in (stage_model.get("artifacts") or {}):
            out.log.append(f"template {ts.id}: no artifact (set templates[].artifact or the artifact's template)")
            continue
        stage = ts.stage or next((s["id"] for s in stage_model.get("stages", []) if art in (s.get("artifacts") or [])), "global")
        res = compile_template(ts, entry, manifest, cfg.rules(ts.rules), cfg.workflow, art, stage, cfg.none_vocab)
        out.cands += res.cands
        out.log += res.log
        out.may_items += res.may_items
    return out


def compile_template(
    ts: TemplateSpec,
    entry: Entry,
    manifest: Manifest,
    rules: ClassifyRules,
    workflow: str,
    artifact: str,
    stage: str,
    none_vocab: dict[str, list[str]] | None = None,
) -> TemplateResult:
    """Compile one skeleton into candidate items (see module docstring)."""
    res = TemplateResult()
    sk = skeleton(entry, ts)
    if not sk:
        res.log.append(f"template {ts.id}: skeleton block not found in {entry.path}")
        return res
    c = _Compiler(ts, entry, manifest, rules, workflow, artifact, stage, none_vocab or {}, res)
    c.run(sk)
    return res


def skeleton(entry: Entry, ts: TemplateSpec) -> list[tuple[int, str]]:
    """The skeleton's lines as (line number, text)."""
    lines = entry.lines()
    blk = ts.block
    if not blk:
        return list(enumerate(lines, start=1))
    if "lines" in blk:
        a, b = int(blk["lines"][0]), int(blk["lines"][-1])
        return [(k, lines[k - 1]) for k in range(max(a, 1), min(b, len(lines)) + 1)]
    _, fences, _, _ = structure(lines)
    if "after" in blk:
        rx = re.compile(str(blk["after"]))
        at = next((k for k, ln in enumerate(lines, start=1) if rx.search(ln)), None)
        fences = [f for f in fences if at is not None and f[0] > at]
        pick = fences[0] if fences else None
    else:
        lang = blk.get("fence")
        cands = [f for f in fences if lang is None or f[2] == lang]
        idx = int(blk.get("index", 0))
        pick = cands[idx] if 0 <= idx < len(cands) else None
    if pick is None:
        return []
    # a fence inside a list item ("6. **Write ...**" then an indented ```markdown block, speckit_bug's stage
    # documents) indents its content by the fence's own indentation: the artifact's lines are the content with
    # that indentation removed (CommonMark), or no heading / label line of the skeleton is recognised
    fence = lines[pick[0] - 1]
    indent = len(fence) - len(fence.lstrip(" "))
    return [(k, _dedent(lines[k - 1], indent)) for k in range(pick[0] + 1, pick[1])]


def _dedent(line: str, n: int) -> str:
    """``line`` without up to ``n`` leading spaces."""
    if n <= 0:
        return line
    k = len(line) - len(line.lstrip(" "))
    return line[min(k, n) :]


# ----------------------------------------------------------------------------------------------
class _Compiler:
    def __init__(self, ts, entry, manifest, rules, workflow, artifact, stage, none_vocab, res):
        self.ts: TemplateSpec = ts
        self.entry: Entry = entry
        self.manifest: Manifest = manifest
        self.rules: ClassifyRules = rules
        self.wf = workflow
        self.art = artifact
        self.stage = stage
        self.none_vocab = {**none_vocab, **ts.none_vocab}
        self.res: TemplateResult = res
        self.ph = rules.rx("placeholder")
        self.legit = rules.rx("legit")
        self.exemplar = rules.rx("exemplar")
        self.literal = rules.rx("literal")
        self.markers = rules.marker_rx()
        self.samples = rules.rx("sample_marker")
        self.none_tokens = {t.lower() for t in rules.none_tokens}
        self.binding = self._ref(ts.binding) if ts.binding else None
        self.base, self.base_ev = self._base_requirement()
        self.seen: dict[str, I.Cand] = {}

    # -- requirement ---------------------------------------------------------------------------
    def _ref(self, r: DocRef) -> SourceRef | None:
        e = self.manifest.resolve(r.path)
        if e is None:
            self.res.log.append(f"template {self.ts.id}: reference {r.path} not in the manifest")
            return None
        quote = r.quote or e.text(*r.lines).strip()
        return SourceRef(doc=e.id, lines=r.lines, quote=quote)

    def _base_requirement(self) -> tuple[str | None, str]:
        if not self.binding:
            return None, ""
        m, ev = modality(self.binding.quote)
        req = self.ts.binding_requirement or {"must": "must", "prohibition": "must", "should": "should"}.get(m)
        where = f"{self.manifest.by_id(self.binding.doc).path if self.manifest.by_id(self.binding.doc) else self.binding.doc}:{self.binding.lines[0]}-{self.binding.lines[1]}"
        return req, f"binding {where} '{_clip(self.binding.quote)}' ({m}: {ev or '-'})"

    def _requirement(self, sec: TLine | None) -> tuple[str | None, str, str, list[SourceRef]]:
        """(requirement or None to skip, modality_evidence, downgrade_reason, extra sources) for a line in ``sec``."""
        extra: list[SourceRef] = []
        chain = self._chain(sec)
        for h in chain:
            ov = _match_section(self.ts.sections, h.title)
            if ov:
                ref = self._ref(ov["authority"]) if isinstance(ov.get("authority"), DocRef) else None
                if ref:
                    extra.append(ref)
                if ov["requirement"] == "skip":
                    return None, f"section '{h.title}' skipped by config", "", extra
                req = ov["requirement"]
                return req, f"section '{h.title}' -> {req} ({ref.doc + ':' + str(ref.lines[0]) if ref else 'config'})", "", extra
        marks = [h.marker for h in chain if h.marker]
        if "optional" in marks or "conditional" in marks:
            return None, f"section marked {'optional' if 'optional' in marks else 'conditional'}", "", extra
        if self.base is None:
            ev = "mandatory marker only" if "mandatory" in marks else "no binding sentence"
            return "should", f"implicit ({ev})", f"implicit: {ev}", extra
        return self.base, self.base_ev + (" x marker mandatory" if "mandatory" in marks else ""), "", extra

    # -- classification ------------------------------------------------------------------------
    def run(self, sk: list[tuple[int, str]]) -> None:
        lines = [TLine(n, raw) for n, raw in sk]
        self.lines = lines
        self._classify(lines)
        self._groups(lines)
        self._frontmatter(lines)
        self._headings(lines)
        self._body(lines)
        self._residue(lines)
        self._not_copy(lines)

    def _classify(self, lines: list[TLine]) -> None:
        i = 0
        while i < len(lines) and not lines[i].raw.strip():
            lines[i].kind = "blank"
            i += 1
        if i < len(lines) and lines[i].raw.strip() == "---":
            j = i + 1
            while j < len(lines) and lines[j].raw.strip() != "---":
                j += 1
            if j < len(lines):
                for k in range(i, j + 1):
                    lines[k].kind = "fm"
                i = j + 1
        in_fence, in_comment, last_heading, first_after = None, False, None, False
        for idx in range(i, len(lines)):
            t = lines[idx]
            s = t.raw.strip()
            t.parent = last_heading
            if in_fence:
                t.kind = "exemplar"
                if _FENCE.match(t.raw) and s.startswith(in_fence):
                    in_fence = None
                continue
            if in_comment:
                t.kind = "comment"
                if "-->" in s:
                    in_comment = False
                continue
            if not s:
                t.kind = "blank"
                continue
            f = _FENCE.match(t.raw)
            if f:
                in_fence = f.group(1)[0] * 3
                t.kind = "exemplar"
                continue
            if s.startswith("<!--"):
                t.kind = "comment"
                in_comment = "-->" not in s
                continue
            if re.fullmatch(r"[-*_]{3,}", s) or re.fullmatch(r"\|?[\s:|-]+\|?", s) and "|" in s and "-" in s:
                t.kind = "rule"
                continue
            h = _HEADING.match(t.raw)
            if h:
                t.kind, t.level = "heading", len(h.group(1))
                title = h.group(2)
                for mk, rxs in self.markers.items():
                    for rx in rxs:
                        if rx.search(title):
                            t.marker = t.marker or mk
                            title = rx.sub("", title)
                t.title = _clean_title(title)
                t.addressable = not self._spans(t.title)[0]
                last_heading, first_after = idx, True
                t.parent = None
                continue
            if first_after and last_heading is not None and not lines[last_heading].marker:
                for mk, rxs in self.markers.items():
                    if any(rx.search(s) for rx in rxs):
                        lines[last_heading].marker = mk  # a marker line right under a heading ("> **Fill ONLY if ...**")
            first_after = False
            if any(rx.search(t.raw) for rx in self.exemplar):
                t.kind = "exemplar"
                continue
            if self.ts.labels:
                for rx in _LABELS:
                    m = rx.match(t.raw)
                    if m and not self._spans(m.group("label"))[0]:
                        t.kind, t.label, t.value = "label", m.group("label").strip(), (m.group("value") or "").strip()
                        break

    def _spans(self, text: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
        """(placeholder spans, legit spans) in ``text``; a placeholder inside a legit span is not one."""
        legit = [(m.start(), m.end(), rx.pattern) for rx in self.legit for m in rx.finditer(text)]
        ph = []
        if self.rules.brackets:
            for a, b in _brackets(text):  # outermost [...]: "[e.g., "by [action]"]" is one placeholder
                if not any(x <= a and b <= y for x, y, _ in legit):
                    ph.append((a, b, text[a:b]))
        for rx in self.ph:
            for m in rx.finditer(text):
                if any(a <= m.start() and m.end() <= b for a, b, _ in legit):
                    continue
                if any(not (m.end() <= a or b <= m.start()) for a, b, _ in ph):
                    continue
                ph.append((m.start(), m.end(), m.group(0)))
        return sorted(ph), sorted(legit)

    def _groups(self, lines: list[TLine]) -> None:
        """Repeated id lines (``- R1:``/``- R2:``, ``### Step 1``/``### Step 2``, ``- [ ] T001``) -> exemplar groups."""
        sigs: dict[tuple, list[int]] = {}
        for idx, t in enumerate(lines):
            if t.kind not in ("text", "label", "heading", "exemplar") or (t.kind == "exemplar" and not t.raw.lstrip().startswith(("-", "*", "+"))):
                continue
            sig = self._id_signature(t)
            if sig:
                sigs.setdefault((t.parent if t.kind != "heading" else self._parent_heading(lines, idx), *sig), []).append(idx)
        self.groups: list[list[int]] = []
        jobs: list[tuple] = []
        for key, idxs in sigs.items():
            if len(idxs) >= 2:
                jobs.append(("id", idxs, key))
        for _kind, idxs, _ in jobs:
            for idx in idxs:
                lines[idx].group = len(self.groups)
            self.groups.append(idxs)
        titles: dict[tuple[int, str], list[int]] = {}
        for idx, t in enumerate(lines):
            if t.kind == "heading" and t.group is None and re.search(r"\d", t.title):
                titles.setdefault((t.level, self._title_rx(t.title)), []).append(idx)
        for (level, rx), idxs in titles.items():
            if len(idxs) >= 2:
                for idx in idxs:
                    lines[idx].group = len(self.groups)
                self.groups.append(idxs)
                jobs.append(("title", idxs, rf"^#{{{level}}}\s+" + rx))
        for kind, idxs, key in jobs:  # every group is known before any item is scoped to a heading
            if kind == "id":
                self._group_item(lines, idxs, key)
            else:
                self._title_group_item(lines, idxs, key)

    def _title_rx(self, title: str) -> str:
        """A heading title with its numbers generalised (``Implementation for User Story 1`` -> ``... Story <digits>``)."""
        return re.sub(r"(?<!\\)\d+", r"\\d+", self._shape(title, anchor=False))

    def _title_group_item(self, lines: list[TLine], idxs: list[int], pattern: str) -> None:
        if not all(_fits(pattern, lines[i].raw) for i in idxs):
            self.res.log.append(f"template {self.ts.id}: heading pattern {pattern!r} does not match its own examples; skipped")
            return
        parents = {self._parent_heading(lines, i) for i in idxs}
        parent = parents.pop() if len(parents) == 1 else None
        sec = lines[parent] if parent is not None and lines[parent].addressable and lines[parent].group is None else None
        req, ev, why, extra = self._requirement(lines[parent] if parent is not None else None)
        if req is None:
            self._may(lines[idxs[0]], ev)
            return
        params: dict = {"pattern": pattern, "min": 1, **({"section": sec.title} if sec is not None else {})}
        self._emit("item_format", params, f"heading.{_slug(lines[idxs[0]].title)}", [lines[i] for i in idxs], req, ev, why, extra, cls="structure")

    def _id_signature(self, t: TLine) -> tuple | None:
        if t.kind == "heading":
            body, lead, box = t.title, f"h{t.level}", False
        else:
            m = _LEAD.match(t.raw)
            if not m:
                return None
            lead = "ol" if m.group(1).strip()[0].isdigit() else "ul"
            body = t.raw[m.end() :]
            box = bool(_BOX.match(body))
            body = _BOX.sub("", body, count=1)
        m = _ID.match(body)
        if not m or not (m.group("prefix") or m.group("sub") or m.group("dot")):
            return None
        width = len(m.group("num")) if m.group("num").startswith("0") else 0
        bold = (bool(m.group("bold")), bool(m.group("bold2")))
        return (lead, box, bold, m.group("prefix") or "", m.group("sep") or "", bool(m.group("sub")), bool(m.group("dot")), bool(m.group("colon")), width)

    @staticmethod
    def _parent_heading(lines: list[TLine], idx: int) -> int | None:
        lvl = lines[idx].level
        for j in range(idx - 1, -1, -1):
            if lines[j].kind == "heading" and lines[j].level < lvl:
                return j
        return None

    def _group_item(self, lines: list[TLine], idxs: list[int], key: tuple) -> None:
        parent, lead, box, bold, prefix, sep, sub, dot, colon, width = key
        first = lines[idxs[0]]
        num = rf"(\d{{{width}}})" if width else r"(\d+)"
        sep_rx = r"[-\s]?" if sep else ""
        core = ("\\*\\*" if bold[0] else "") + (re.escape(prefix).replace("\\ ", r"\s+") + sep_rx if prefix else "") + num
        core += r"(?:\.\d+)+" if sub else ""
        core += r"\." if dot else ""
        core += ("\\*\\*" if bold[1] else "") + (":" if colon else "") + r"(?=\s|$|\[|:)"
        if lead.startswith("h"):
            pattern = rf"^#{{{first.level}}}\s+" + core
        else:
            pattern = r"^\s*" + (r"\d+[.)]" if lead == "ol" else r"[-*+]") + r"\s+" + (r"\[[ xX]\]\s+" if box else "") + core
        examples = [lines[i].raw for i in idxs]
        if not all(re.search(pattern, ex) for ex in examples):
            self.res.log.append(f"template {self.ts.id}: id pattern {pattern!r} does not match its own examples; skipped")
            return
        sec = lines[parent] if parent is not None else None
        if sec is not None and (sec.kind != "heading" or not sec.addressable or sec.group is not None):
            sec = None  # a repeated heading ("Implementation for User Story 1") does not name one section
        req, ev, why, extra = self._requirement(lines[parent] if parent is not None else None)
        if req is None:
            self._may(first, ev)
            return
        params: dict = {"pattern": pattern, "min": 1}
        if sec is not None:
            params["section"] = sec.title
        if self.ts.infer_sequence:
            nums = [int(re.search(pattern, ex).group(1)) for ex in examples]
            if nums == list(range(nums[0], nums[0] + len(nums))):
                params["sequence"] = {"group": 1, "start": nums[0]}
        what = "heading" if lead.startswith("h") else "line"
        self._emit("item_format", params, f"format.{_slug(prefix or 'id')}-{what}", [lines[i] for i in idxs], req, ev, why, extra, cls="content" if not lead.startswith("h") else "structure")

    # -- items ---------------------------------------------------------------------------------
    def _frontmatter(self, lines: list[TLine]) -> None:
        fm = [t for t in lines if t.kind == "fm"]
        if not fm:
            return
        keys, values = [], {}
        for t in fm[1:-1]:
            m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", t.raw.strip())
            if not m:
                continue
            keys.append(m.group(1))
            v = m.group(2).strip().strip("\"'")
            if v and not self._spans(v)[0] and not re.fullmatch(r"<[^>]*>", v):
                values[m.group(1)] = v
        if not keys:
            return
        req, ev, why, extra = self._requirement(None)
        if req is None:
            return
        exact = self.ts.frontmatter_exact
        if exact is None:
            exact = bool(self.binding and re.search(r"\bexactly\b", self.binding.quote))
        params: dict = {"keys": keys, "exact": bool(exact)}
        keep_values = self.ts.frontmatter_values if self.ts.frontmatter_values is not None else self.ts.literals == "all"
        if values and keep_values:
            params["values"] = values
        self._emit("frontmatter", params, "frontmatter", fm, req, ev, why, extra, cls="structure")

    def _headings(self, lines: list[TLine]) -> None:
        if not self.ts.headings:
            return
        for idx, t in enumerate(lines):
            if t.kind != "heading" or t.group is not None:
                continue
            req, ev, why, extra = self._requirement(t)
            if req is None:
                self._may(t, ev)
                continue
            if t.addressable:
                self._emit("section_present", {"heading": t.title, "level": t.level}, f"section.{_slug(t.title)}", [t], req, ev, why, extra, cls="structure")
            else:
                pat = rf"^#{{{t.level}}}\s+" + self._shape(t.title, anchor=False)
                if _fits(pat, t.raw):
                    self._emit("item_format", {"pattern": pat, "min": 1}, f"heading.{_slug(t.title)}", [t], req, ev, why, extra, cls="structure")

    def _body(self, lines: list[TLine]) -> None:
        for idx, t in enumerate(lines):
            if t.kind not in ("label", "text") or t.group is not None:
                continue
            sec, block = self._section_for(lines, idx)
            req, ev, why, extra = self._requirement(lines[t.parent] if t.parent is not None else None)
            if req is None:
                if t.parent is not None:
                    self._may(lines[t.parent], ev)
                continue
            if sec is None:
                self._fallback(t, req, ev, why, extra)
                continue
            base = {"section": sec}
            if t.kind == "label":
                self._label(t, base, block, req, ev, why, extra)
            else:
                self._text(t, base, block, req, ev, why, extra)

    def _section_for(self, lines: list[TLine], idx: int) -> tuple[str | None, dict | None]:
        """The section title a line is addressed by, and a ``per_block`` spec when it sits under an id-group heading."""
        p = lines[idx].parent
        if p is None:
            return None, None
        h = lines[p]
        if h.group is not None:
            gp = self._parent_heading(lines, p)
            if gp is None or not lines[gp].addressable:
                return None, None
            title_rx = self._group_title_rx(lines, h)
            return lines[gp].title, {"heading_pattern": title_rx, "level": h.level}
        return (h.title, None) if h.addressable else (None, None)

    def _group_title_rx(self, lines: list[TLine], h: TLine) -> str:
        m = _ID.match(h.title)
        prefix = (m.group("prefix") or "") if m else ""
        return "^" + (re.escape(prefix).replace("\\ ", r"\s+") + r"[-\s]?" if prefix else "") + r"\d+"

    def _label(self, t: TLine, base: dict, block: dict | None, req, ev, why, extra) -> None:
        label = t.label
        if _ID_LABEL.fullmatch(label):
            return self._text(t, base, block, req, ev, why, extra, body=t.value)  # "- R3: [...]": an id, not a stable label
        self._emit("label_present", {**base, "label": label}, f"label.{_slug(base['section'])}.{_slug(label)}", [t], req, ev, why, extra, cls="structure", block=block)
        value = t.value.strip().strip("`").strip()
        if not value:
            if self._list_after_blank(t):
                return  # "**Acceptance Scenarios**:", a blank line, then the list: no label value to fill, the list lines' own items judge it
            self._emit("field_filled", {**base, "label": label}, f"field.{_slug(base['section'])}.{_slug(label)}", [t], req, ev, why, extra, cls="content", none="unspecified", block=block)
            return
        ph, legit = self._spans(value)
        if not ph:
            if self.ts.literals == "all" or any(rx.search(t.raw) for rx in self.literal):
                self._emit("field_literal", {**base, "label": label, "text": value}, f"literal.{_slug(base['section'])}.{_slug(label)}", [t], req, ev, why, extra, cls="structure", block=block)
            return
        only = _only_placeholders(value, ph)
        alts = self._alternatives(ph[0][2]) if only and len(ph) == 1 else []
        kinds = [self._alt_kind(a) for a in alts]
        stem = f"{_slug(base['section'])}.{_slug(label)}"
        if alts and all(k in ("token", "none", "prefix") for k, _ in kinds) and sum(k != "none" for k, _ in kinds) >= 2:
            prefix_ok = any(k == "prefix" for k, _ in kinds)
            values = [v for _, v in kinds]
            self._emit("field_enum", {**base, "label": label, "values": values, **({"prefix_ok": True} if prefix_ok else {})}, f"enum.{stem}", [t], req, ev, why, extra, cls="content", block=block)
            return
        none, vocab = self._none_policy(base["section"], label, kinds)
        params = {**base, "label": label, **({"none_vocab": vocab} if vocab else {})}
        self._emit("field_filled", params, f"field.{stem}", [t], req, ev, why, extra, cls="content", none=none, block=block)
        if not only:
            pat = self._shape(t.raw)
            of = r"^\s*(?:[-*+]\s+)?" + _BOLD + re.escape(label) + _BOLD + r"\s*:"
            if _fits(pat, t.raw):
                self._emit("item_format", {**base, "pattern": pat, "of_pattern": of}, f"shape.{stem}", [t], req, ev, why, extra, cls="content")

    def _list_after_blank(self, t: TLine) -> bool:
        """The template puts the label's content as a list after a blank line, which markdown.field_value (a value
        ends at a blank line) never reads as the label's value."""
        lines = self.lines
        i = next((k for k, x in enumerate(lines) if x is t), None)
        if i is None or i + 1 >= len(lines) or lines[i + 1].kind != "blank":
            return False
        nxt = next((x for x in lines[i + 1 :] if x.kind != "blank"), None)
        return nxt is not None and nxt.parent == t.parent and nxt.kind in ("text", "label", "exemplar") and bool(_LEAD.match(nxt.raw))

    def _text(self, t: TLine, base: dict, block: dict | None, req, ev, why, extra, body: str | None = None) -> None:
        body = _LEAD.sub("", t.raw, count=1).strip() if body is None else body.strip()
        ph, _ = self._spans(body)
        stem = _slug(base["section"])
        if not ph:
            if self.ts.literals == "all" or any(rx.search(t.raw) for rx in self.literal):
                self._emit("field_literal", {**base, "text": body}, f"literal.{stem}.{_slug(body)[:40]}", [t], req, ev, why, extra, cls="structure", block=block)
            return
        if _only_placeholders(body, ph) and len(ph) == 1:
            alts = self._alternatives(ph[0][2])
            kinds = [self._alt_kind(a) for a in alts]
            if all(k in ("token", "none", "prefix") for k, _ in kinds) and sum(k != "none" for k, _ in kinds) >= 2:
                lead = r"^\s*(?:[-*+]|\d+[.)])\s+" if _LEAD.match(t.raw) else r"^\s*"
                # the alternatives are words, not a case (markdown.is_none reads "None" as none too)
                pat = lead + "(?i:" + "|".join(_esc_words(v) for _, v in kinds) + ")"
                self._emit("item_format", {**base, "pattern": pat, "min": 1}, f"choice.{stem}", [t], req, ev, why, extra, cls="content")
                return
            none, vocab = self._none_policy(base["section"], "", kinds)
            self._emit("field_filled", {**base, **({"none_vocab": vocab} if vocab else {})}, f"field.{stem}", [t], req, ev, why, extra, cls="content", none=none, block=block)
            return
        if _only_placeholders(body, ph):
            self._emit("field_filled", dict(base), f"field.{stem}", [t], req, ev, why, extra, cls="content", none="unspecified", block=block)
            return
        pat = self._shape(t.raw)
        if _fits(pat, t.raw):
            self._emit("item_format", {**base, "pattern": pat, "min": 1}, f"shape.{stem}", [t], req, ev, why, extra, cls="content")

    def _fallback(self, t: TLine, req, ev, why, extra) -> None:
        """A line under a heading we cannot address (its title is a placeholder): its shape over the whole text."""
        if t.kind == "label" and not self._spans(t.value)[0] and self.ts.literals != "all" and not any(rx.search(t.raw) for rx in self.literal):
            return
        if t.kind == "text" and not self._spans(t.raw)[0] and self.ts.literals != "all" and not any(rx.search(t.raw) for rx in self.literal):
            return
        pat = self._shape(t.raw)
        if _fits(pat, t.raw):
            cls = "structure" if not self._spans(t.raw)[0] else "content"
            self._emit("item_format", {"pattern": pat, "min": 1}, f"shape.top.{_slug(t.label or t.raw)[:40]}", [t], req, ev, why, extra, cls=cls)

    def _residue(self, lines: list[TLine]) -> None:
        found: dict[str, list[TLine]] = {}
        for t in lines:
            if t.kind in ("comment", "blank", "rule", "fm"):
                continue
            for _a, _b, txt in self._spans(t.raw)[0]:
                if txt.startswith("<!--"):
                    continue
                inner = txt.strip("[]<>").strip()
                if len(inner) < 3 or re.fullmatch(r"[A-Z]{0,5}-?\d+", inner) or re.fullmatch(r"[xX ]", inner):
                    continue
                found.setdefault(txt, []).append(t)
        if not found:
            return
        req, ev, why, extra = self._requirement(None)
        if req is None:
            return
        if self.binding and re.search(r"(?i)\b(?:replace|placeholder|bracket)", self.binding.quote):
            ev += " (placeholders)"
        src_lines = sorted({t.n: t for ts in found.values() for t in ts}.values(), key=lambda t: t.n)
        pats = [re.escape(txt) for txt in found]
        self._emit("no_template_residue", {"patterns": pats}, "residue", src_lines, req, ev, why, extra, cls="content")

    def _not_copy(self, lines: list[TLine]) -> None:
        heads = [(i, t) for i, t in enumerate(lines) if t.kind == "heading"]
        jobs: list[tuple[str, list[TLine], SourceRef | TLine]] = []
        for nc in self.ts.not_copy:
            hit = [(i, t) for i, t in heads if t.title.lower() == nc["section"].lower()]
            ref = self._ref(nc["authority"]) if isinstance(nc["authority"], DocRef) else None
            if hit and ref:
                jobs.append((hit[0][1].title, self._content(lines, hit[0][0]), ref))
        for ci, t in enumerate(lines):
            if t.kind != "comment" or not any(rx.search(t.raw) for rx in self.samples):
                continue
            start = ci
            while start > 0 and lines[start - 1].kind == "comment":
                start -= 1
            enclosing = lines[t.parent] if t.parent is not None else None
            level = enclosing.level if enclosing else 1
            for i, h in heads:
                if i > ci and h.addressable and h.level == level:
                    content = self._content(lines, i)
                    if any(x.group is not None or x.kind == "exemplar" for x in content):
                        jobs.append((h.title, content, t))
        for title, content, auth in jobs:
            content = [x for x in content if x.kind in ("text", "label", "exemplar") and x.raw.strip() and not _FENCE.match(x.raw)]
            fp = [_LEAD.sub("", x.raw, count=1).strip() for x in content]
            if not fp:
                continue
            if isinstance(auth, TLine):
                m, mev = modality(auth.raw)
                req = "must" if m in ("must", "prohibition") else "should"
                ev, extra, why, cited = f"template comment line {auth.n} ({m}: {mev or '-'})", [], "" if req == "must" else "implicit", [auth, *content]
            else:
                m, mev = modality(auth.quote)
                req = "must" if m in ("must", "prohibition") else "should"
                ev, extra, why, cited = f"not_copy authority ({m}: {mev or '-'})", [auth], "", content
            self._emit("not_template_copy", {"section": title, "fingerprint": fp}, f"notcopy.{_slug(title)}", cited, req, ev, why, extra, cls="content")

    @staticmethod
    def _content(lines: list[TLine], hi: int) -> list[TLine]:
        lvl = lines[hi].level
        out = []
        for t in lines[hi + 1 :]:
            if t.kind == "heading" and t.level <= lvl:
                break
            out.append(t)
        return out

    # -- helpers -------------------------------------------------------------------------------
    def _alternatives(self, ph: str) -> list[str]:
        inner = ph[1:-1] if ph.startswith("[") and ph.endswith("]") else ph
        alts = [a.strip() for a in re.split(r"\s+\|\s+", inner) if a.strip()]
        m = re.search(r"""otherwise\s+["“']([^"”']+)["”']""", inner)
        if m:
            alts.append(m.group(1))
        m = re.search(r"\bor\s+(N/A|n/a)\s*$", inner)
        if m:
            alts.append(m.group(1))
        return alts if len(alts) >= 2 else []

    def _alt_kind(self, a: str) -> tuple[str, str]:
        s = a.strip().strip("\"'`“”")
        if s.lower() in self.none_tokens:
            return "none", s
        m = re.match(r"^([a-z][a-z \-]{1,40}):\s+\S", s)
        if m:
            return "prefix", m.group(1) + ":"
        if re.fullmatch(r"[A-Za-z][\w\-]*(?: [\w\-]+){0,3}", s) and not _DESCRIPTIVE.search(s):
            return "token", s
        return "descriptive", s

    def _none_policy(self, section: str, label: str, kinds: list[tuple[str, str]]) -> tuple[str, list[str]]:
        derived = [v for k, v in kinds if k == "none"]
        if not derived:
            return "unspecified", []
        vocab = self.none_vocab.get(f"{section}/{label}") or self.none_vocab.get(label) or derived
        return "yes", list(vocab)

    def _shape(self, text: str, anchor: bool = True) -> str:
        """A regex for a line: literals as written (whitespace-tolerant), placeholders as ``.+?``, legit syntax by its rule."""
        ph, legit = self._spans(text)
        spans = sorted([(a, b, "ph", "") for a, b, _ in ph] + [(a, b, "legit", p) for a, b, p in legit])
        out, pos = [], 0
        lead = _LEAD.match(text) if anchor else None
        if lead:
            out.append(r"\s*(?:[-*+]|\d+[.)])\s+")
            pos = lead.end()
            box = _BOX.match(text[pos:])
            if box:
                out.append(r"\[[ xX]\]\s+")
                pos += box.end()
        for a, b, kind, pat in spans:
            if a < pos:
                continue
            out.append(_lit(text[pos:a]))
            out.append(".+?" if kind == "ph" else f"(?:{pat})")
            pos = b
        out.append(_lit(text[pos:].rstrip()))
        body = "".join(out)
        return ("^" + body) if anchor else body.lstrip()

    def _chain(self, sec: TLine | None) -> list[TLine]:
        out = []
        cur = sec
        lines = self.lines
        while cur is not None:
            out.append(cur)
            idx = lines.index(cur)
            p = self._parent_heading(lines, idx) if cur.kind == "heading" else cur.parent
            cur = lines[p] if p is not None else None
        return out

    def _may(self, t: TLine, why: str) -> None:
        key = f"{t.n}:{why}"
        if any(m.get("_key") == key for m in self.res.may_items):
            return
        self.res.may_items.append({"_key": key, "doc": self.entry.id, "lines": [t.n, t.n], "quote": t.raw.strip(), "reason": why, "template": self.ts.id})

    def _emit(self, kind, params, stem, tlines, req, ev, why, extra, cls, none="-", block=None) -> None:
        if block is not None and kind in ("field_filled",):
            params = {**params, "per_block": block}
        elif block is not None and kind in ("label_present", "field_literal", "field_enum"):
            pass  # these kinds take no per_block; the first block's label is checked
        srcs = [SourceRef(doc=self.entry.id, lines=(t.n, t.n), quote=t.raw.strip()) for t in tlines if isinstance(t, TLine) and t.raw.strip()]
        srcs += [r for r in tlines if isinstance(r, SourceRef)]
        if self.binding and req == self.base and not why:
            srcs.append(self.binding)
        srcs += [r for r in extra if r not in srcs]
        iid = f"{self.wf}.{self.stage}.{self.art}.{stem}"
        c = I.make(
            iid,
            kind,
            params,
            stage=self.stage,
            target=("artifact", self.art, self.ts.state),
            requirement=req,
            sources=_dedup_sources(srcs),
            cls=cls,
            origin="template",
            derived_by="template_compiler",
            none_allowed=none,
            modality_evidence=ev,
            downgrade_reason=why,
            note=f"template {self.ts.id}",
        )
        k = c.key()
        if k in self.seen:
            prev = self.seen[k]
            prev.item.sources = _dedup_sources(prev.item.sources + c.item.sources)
            return
        self.seen[k] = c
        self.res.cands.append(c)


def _match_section(sections: dict[str, dict], title: str) -> dict | None:
    for k, v in sections.items():
        if k.lower() == title.lower() or (k.startswith("^") and re.search(k, title)):
            return v
    return None


def _brackets(text: str) -> list[tuple[int, int]]:
    """Outermost balanced ``[...]`` spans; an unclosed bracket is not a span."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0 and i > start + 1:
                out.append((start, i + 1))
    return out


def _instances(raw: str) -> list[str]:
    """The template line as the agent would write it: each ``(a | b)`` notation replaced by each alternative."""
    m = _PAREN_ALTS.search(raw)
    if not m:
        return [raw]
    out = []
    for alt in re.split(r"\s+\|\s+", m.group(1)):
        out += _instances(raw[: m.start()] + "(" + alt.strip() + ")" + raw[m.end() :])
    return out


def _fits(pattern: str, raw: str) -> bool:
    """A derived regex must accept every instance of its own template line (minimal-constraint check)."""
    return all(re.search(pattern, x) for x in _instances(raw))


def _only_placeholders(text: str, ph: list[tuple[int, int, str]]) -> bool:
    rest, pos = [], 0
    for a, b, _ in ph:
        rest.append(text[pos:a])
        pos = b
    rest.append(text[pos:])
    return not re.sub(r"[\s`*_\"'.,;:()-]", "", "".join(rest))


def _lit(s: str) -> str:
    if not s:
        return ""
    out = []
    pos = 0
    for m in _PAREN_ALTS.finditer(s):
        out.append(_esc_labels(s[pos : m.start()]))
        out.append(r"\((?:" + "|".join(_esc_words(a.strip()) for a in re.split(r"\s+\|\s+", m.group(1))) + r")\)")
        pos = m.end()
    out.append(_esc_labels(s[pos:]))
    return "".join(out)


_LABEL_TOK = re.compile(r"(?:^|(?<=\s))([A-Za-z][\w/&'.-]*(?:[ \t]+[\w/&'.-]+){0,5}?):(?=\s|$)")
_BOLD = r"(?:\*\*|__)?"


def _esc_labels(s: str) -> str:
    """``_esc_ws`` with each ``Label:`` token emphasis-tolerant (``**Label**:``, ``**Label:**``), as
    :func:`..markdown.field_value` reads labels: bold markup is not a different prefix."""
    out, pos = [], 0
    for m in _LABEL_TOK.finditer(s):
        out.append(_esc_ws(s[pos : m.start()]))
        out.append(_BOLD + _esc_ws(m.group(1)) + _BOLD + r"\s*:" + _BOLD)
        pos = m.end()
    out.append(_esc_ws(s[pos:]))
    return "".join(out)


_DASH = r"(?:—|–|-{1,2}|\|)"  # a spaced dash between two fields: a separator, not a prefix the template binds


def _esc_ws(s: str) -> str:
    if not s:
        return ""
    parts = re.split(r"(\s+)", s)
    lit = lambda i, p: _DASH if p in ("—", "–") and 0 < i < len(parts) - 1 else re.escape(p)  # noqa: E731
    return "".join((r"\s*" if p.strip() == "" and (i == 0 or i == len(parts) - 1) else r"\s+") if p and not p.strip() else lit(i, p) for i, p in enumerate(parts))


def _esc_words(s: str) -> str:
    return r"\s+".join(re.escape(w) for w in s.split())


def _clean_title(t: str) -> str:
    t = re.sub(r"^\*\*(.*)\*\*$", r"\1", t.strip())
    return t.strip().rstrip(":").strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "x"


def _clip(s: str, n: int = 90) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


def _dedup_sources(srcs: list[SourceRef]) -> list[SourceRef]:
    out, seen = [], set()
    for s in srcs:
        k = (s.doc, s.lines, s.quote)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out
