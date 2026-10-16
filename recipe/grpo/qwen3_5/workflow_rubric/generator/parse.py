"""G1: markdown structure and modal-sentence candidates, by rule.

Two things later stages need without a model: where things are (headings, fenced blocks,
comments, frontmatter, with 1-based line numbers) and which sentences carry a requirement. The
second is a fixed modality dictionary (DESIGN §2 P2) so that "must" vs "should" is decided by the
words in the document, not by a model's reading of it -- G6 re-applies the same dictionary to
every item's quote, and a model may only *lower* a requirement, with a reason.

    must         MUST / SHALL / required / mandatory / CRITICAL / ALWAYS, "Keep|Follow ... exactly",
                 an imperative verb opening the sentence, a "- [ ]" checklist item
    prohibition  MUST NOT / NEVER / do not / don't / sentence-initial "No <noun>"
    should       SHOULD / recommended / prefer / ideally / avoid / when possible
    may          MAY / optional / if applicable
    implicit     none of the above

Template-role files, fenced blocks and example blocks never yield candidates (templates are G2's;
examples show artifact content, not requirements). In the system prompt only sections mapped to
``workflow`` yield candidates; modal sentences of the generic harness sections are listed apart so
the rubric can say why they were not itemized (DESIGN §10.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .manifest import Entry, Manifest

MODALITIES = ("must", "prohibition", "should", "may", "implicit")
_STRENGTH = {"prohibition": 4, "must": 4, "should": 2, "may": 1, "implicit": 0}

_CODE = re.compile(r"`[^`\n]*`")
_PROHIBITION = re.compile(r"\b(?:MUST NOT|[Mm]ust not|SHALL NOT|[Ss]hall not|NEVER|[Nn]ever|DO NOT|Do NOT|[Dd]o not|DON'T|[Dd]on't|[Nn]ot allowed|[Ff]orbidden|[Pp]rohibited|[Mm]ay not)\b")
_NO_NOUN = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)?(?:\[[ xX]\]\s+)?(?:\*\*)?No\s+[a-z]")
_MUST = re.compile(r"\b(?:MUST|[Mm]ust|SHALL|[Ss]hall|REQUIRED|[Rr]equired|MANDATORY|[Mm]andatory|CRITICAL|ALWAYS|[Aa]lways|[Nn]eeds? to|[Hh]as to|[Hh]ave to)\b")
_EXACTLY = re.compile(r"\b(?:Keep|keep|Follow|follow|Use|use|Preserve|preserve)\b[^.]*\bexactly\b")
_SHOULD = re.compile(r"\b(?:SHOULD|[Ss]hould|RECOMMENDED|[Rr]ecommended|[Pp]refer(?:red|ably)?|[Ii]deally|[Ww]hen possible|[Ww]here possible|[Ii]f possible|[Ss]uggested|[Aa]void)\b")
_MAY = re.compile(r"\b(?:MAY|[Mm]ay|OPTIONAL|[Oo]ptional(?:ly)?|[Ii]f applicable|[Ii]f needed|[Ii]f relevant)\b")
_LEAD = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\[[ xX]\]\s+)?(?:\*\*[^*]{0,40}\*\*:?\s*)?(?:Step\s+\d+[:.]\s*)?[*_]*")
_CHECKBOX = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+")
IMPERATIVE_VERBS = frozenset(
    """add analyze append apply archive ask assign begin build call capture check choose classify collect combine commit compare complete
    configure confirm continue convert copy correct create define delete describe derive detect determine document draft edit ensure enumerate
    evaluate execute expand explain express extend extract fill finish fix follow generate group identify implement include initialize insert
    install keep label leave list load locate log map mark merge modify move name note number open order organize output parse pause place plan
    populate preserve print proceed produce prompt propose provide put quote re-run read record reference remove rename replace report reproduce
    request resolve restate return review rewrite run save scan search select set show skip sort split start state stop summarize sync tag tick
    track treat update use validate verify wait work write""".split()
)
_EXAMPLE_MARKER = re.compile(r"^\s*[*_]*(?:Examples?|For example|e\.g\.)\b[^:\n]{0,60}:[*_]*\s*$", re.I)
_EXAMPLE_HEADING = re.compile(r"^examples?\b", re.I)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")
_LIST_START = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TAG_LINE = re.compile(r"^\s*</?[A-Za-z][\w-]*>\s*$")  # <SECTION> lines of a system prompt separate paragraphs
_BLOCK_SCALAR = re.compile(r"^(\s*)(?:-\s+)?[\w.-]+:\s*[|>][-+]?\s*$")


@dataclass
class Candidate:
    line_start: int
    line_end: int
    text: str
    modality: str
    modality_evidence: str
    heading: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Parsed:
    id: str
    headings: list[list] = field(default_factory=list)  # [line, level, title]
    fences: list[list] = field(default_factory=list)  # [open_line, close_line, lang]
    comments: list[list[int]] = field(default_factory=list)  # [first, last]
    frontmatter: list[int] | None = None
    candidates: list[Candidate] = field(default_factory=list)
    excluded: list[list] = field(default_factory=list)  # [first, last, reason]
    sp_generic: list[Candidate] = field(default_factory=list)

    def to_json(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("candidates", "sp_generic")}
        d["candidates"] = [c.to_json() for c in self.candidates]
        d["sp_generic"] = [c.to_json() for c in self.sp_generic]
        return d

    @classmethod
    def from_json(cls, d: dict) -> Parsed:
        p = cls(**{k: v for k, v in d.items() if k not in ("candidates", "sp_generic")})
        p.candidates = [Candidate(**c) for c in d.get("candidates", [])]
        p.sp_generic = [Candidate(**c) for c in d.get("sp_generic", [])]
        return p


# ----------------------------------------------------------------------------------------------
def strength(m: str) -> int:
    return _STRENGTH.get(m, 0)


def modality(text: str, checkbox: bool = False) -> tuple[str, str]:
    """The dictionary modality of one sentence and the word that decided it."""
    t = _CODE.sub(" ", text or "")
    m = _PROHIBITION.search(t)
    if m:
        return "prohibition", m.group(0)
    if _NO_NOUN.match(t):
        return "prohibition", "No <noun>"
    m = _MUST.search(t)
    if m:
        return "must", m.group(0)
    m = _EXACTLY.search(t)
    if m:
        return "must", "exactly"
    m = _SHOULD.search(t)
    if m:
        return "should", m.group(0)
    m = _MAY.search(t)
    if m:
        return "may", m.group(0)
    lead = _LEAD.sub("", t, count=1).strip()
    w = re.match(r"([A-Za-z][A-Za-z-]*)", lead)
    if w and w.group(1)[0].isupper() and w.group(1).lower() in IMPERATIVE_VERBS:
        return "must", f"imperative:{w.group(1)}"
    if checkbox or _CHECKBOX.match(text or ""):
        return "must", "checkbox"
    return "implicit", ""


def strongest(texts: list[str]) -> tuple[str, str]:
    best = ("implicit", "")
    for t in texts:
        m = modality(t)
        if strength(m[0]) > strength(best[0]) or (strength(m[0]) == strength(best[0]) and m[0] == "prohibition" and best[0] == "must"):
            best = m
    return best


def structure(lines: list[str]) -> tuple[list[list], list[list], list[list[int]], list[int] | None]:
    """(headings, fences, comments, frontmatter) of a markdown text; headings inside fences are ignored."""
    headings: list[list] = []
    fences: list[list] = []
    comments: list[list[int]] = []
    fm = None
    i, n = 0, len(lines)
    if n and lines[0].strip() == "---":
        for j in range(1, min(n, 80)):
            if lines[j].strip() == "---":
                fm = [1, j + 1]
                i = j + 1
                break
    while i < n:
        ln = lines[i]
        f = _FENCE.match(ln)
        if f:
            mark = f.group(1)
            j = i + 1
            while j < n and not (lines[j].strip().startswith(mark[0] * len(mark)) and set(lines[j].strip()) <= {mark[0]}):
                j += 1
            fences.append([i + 1, min(j, n - 1) + 1, f.group(2)])
            i = j + 1
            continue
        pos = ln.find("<!--")
        if pos >= 0 and "-->" not in ln[pos + 4 :]:
            j = i + 1
            while j < n and "-->" not in lines[j]:
                j += 1
            comments.append([i + 1, min(j, n - 1) + 1])
            i = j + 1
            continue
        if pos >= 0:
            comments.append([i + 1, i + 1])  # one-line comment; the line may still be a heading
        h = _HEADING.match(ln)
        if h:
            headings.append([i + 1, len(h.group(1)), h.group(2).strip()])
        i += 1
    return headings, fences, comments, fm


def parse_entry(entry: Entry, template_comments: bool = False, example_markers: list[str] | None = None) -> Parsed:
    lines = entry.lines()
    out = Parsed(id=entry.id)
    if entry.binary:
        out.excluded.append([1, 1, "binary"])
        return out
    out.headings, out.fences, out.comments, out.frontmatter = structure(lines)
    if entry.role == "script":
        out.excluded.append([1, max(len(lines), 1), "script"])
        return out
    skip: dict[int, str] = {}
    for a, b, _ in out.fences:
        for k in range(a, b + 1):
            skip[k] = "fenced block"
    if out.frontmatter:
        for k in range(out.frontmatter[0], out.frontmatter[1] + 1):
            skip[k] = "frontmatter"
    allowed: set[int] | None = None
    if entry.role == "template":
        allowed = set()
        if template_comments:
            for a, b in out.comments:
                allowed.update(range(a, b + 1))
        for k in range(1, len(lines) + 1):
            if k not in allowed:
                skip.setdefault(k, "template (compiled by G2)")
    if entry.role == "schema":
        allowed = _block_scalar_lines(lines)
        for k in range(1, len(lines) + 1):
            if k not in allowed:
                skip.setdefault(k, "schema structure")
    for k in _example_lines(lines, out.headings, [re.compile(p) for p in (example_markers or [])]):
        skip.setdefault(k, "example block")
    for k, reason in sorted(skip.items()):
        if out.excluded and out.excluded[-1][2] == reason and out.excluded[-1][1] == k - 1:
            out.excluded[-1][1] = k
        else:
            out.excluded.append([k, k, reason])
    heading_at = _heading_context(out.headings, len(lines))
    for a, b in _units(lines, skip):
        unit = [(k, _strip_comment_markup(lines[k - 1]) if entry.role == "template" else lines[k - 1]) for k in range(a, b + 1)]
        box = bool(_CHECKBOX.match(unit[0][1]))
        for s_a, s_b, sent in _sentences(unit):
            m, ev = modality(sent, checkbox=box and s_a == a)
            if m == "implicit":
                continue
            c = Candidate(s_a, s_b, sent, m, ev, heading_at.get(s_a, ""))
            if entry.role == "system_prompt" and entry.section_role(s_a) != "workflow":
                out.sp_generic.append(c)
            else:
                out.candidates.append(c)
    return out


def parse_manifest(manifest: Manifest, template_comments: bool = False, example_markers: list[str] | None = None) -> dict[str, Parsed]:
    return {e.id: parse_entry(e, template_comments, example_markers) for e in manifest.entries}


# ----------------------------------------------------------------------------------------------
def _strip_comment_markup(s: str) -> str:
    return s.replace("<!--", " ").replace("-->", " ")


def _block_scalar_lines(lines: list[str]) -> set[int]:
    """Lines inside YAML block scalars (``key: |``): the prose of a schema file."""
    out: set[int] = set()
    indent = None
    for i, ln in enumerate(lines, start=1):
        if indent is not None:
            if not ln.strip():
                out.add(i)
                continue
            if len(ln) - len(ln.lstrip()) > indent:
                out.add(i)
                continue
            indent = None
        m = _BLOCK_SCALAR.match(ln)
        if m:
            indent = len(m.group(1))
    return out


def _example_lines(lines: list[str], headings: list[list], extra: list[re.Pattern]) -> set[int]:
    out: set[int] = set()
    for idx, (line, level, title) in enumerate(headings):
        if _EXAMPLE_HEADING.match(title):
            end = next((h[0] - 1 for h in headings[idx + 1 :] if h[1] <= level), len(lines))
            out.update(range(line + 1, end + 1))
    for i, ln in enumerate(lines, start=1):
        if _EXAMPLE_MARKER.match(ln) or any(r.search(ln) for r in extra):
            j = i + 1
            while j <= len(lines) and not lines[j - 1].strip():
                j += 1
            while j <= len(lines) and lines[j - 1].strip():
                out.add(j)
                j += 1
    return out


def _heading_context(headings: list[list], n: int) -> dict[int, str]:
    out: dict[int, str] = {}
    stack: list[tuple[int, str]] = []
    hi = 0
    for k in range(1, n + 1):
        while hi < len(headings) and headings[hi][0] <= k:
            _, level, title = headings[hi]
            stack = [s for s in stack if s[0] < level] + [(level, title)]
            hi += 1
        out[k] = " > ".join(t for _, t in stack)
    return out


def _units(lines: list[str], skip: dict[int, str]) -> list[tuple[int, int]]:
    """Paragraphs, list items (with continuation lines), headings and table rows as line ranges."""
    units: list[tuple[int, int]] = []
    cur: list[int] | None = None
    for k in range(1, len(lines) + 1):
        ln = lines[k - 1]
        if k in skip or not ln.strip() or _TAG_LINE.match(ln):
            if cur:
                units.append((cur[0], cur[1]))
            cur = None
            continue
        if _HEADING.match(ln) or ln.lstrip().startswith("|"):
            if cur:
                units.append((cur[0], cur[1]))
            units.append((k, k))
            cur = None
            continue
        if _LIST_START.match(ln):
            if cur:
                units.append((cur[0], cur[1]))
            cur = [k, k]
            continue
        if cur is None:
            cur = [k, k]
        else:
            cur[1] = k
    if cur:
        units.append((cur[0], cur[1]))
    return units


_SPLIT = re.compile(r"(?<=[.!?])[\"')\]*]*\s+(?=[A-Z*`\"(\[_])")


def _sentences(unit: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Split a unit into sentences, keeping the line range each one spans."""
    text, owner = "", []
    for k, ln in unit:
        piece = ln.strip()
        if text:
            text += " "
            owner.append(k)
        text += piece
        owner.extend([k] * len(piece))
    out = []
    bounds = [0, *(m.end() for m in _SPLIT.finditer(text)), len(text)]
    for start, end in zip(bounds, bounds[1:], strict=False):
        raw = text[start:end]
        seg = raw.strip()
        if not seg:
            continue
        a = start + (len(raw) - len(raw.lstrip()))
        b = a + len(seg) - 1
        out.append((owner[a], owner[b], seg))
    return out
