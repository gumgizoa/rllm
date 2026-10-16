"""Markdown the way workflow artifacts are written: frontmatter, headings, sections, labelled fields.

Every artifact check (``checks/artifacts.py``) and every artifact selector in :mod:`.refs` reads text
through these functions, so the reading policy lives in one place:

* Lenient where the templates themselves vary, or where a transcription slip changes nothing that
  was written: one fence around the whole document (the rule files show their skeletons fenced),
  bold labels and headings, a trailing colon, a template annotation such as ``*(mandatory)*``.
* Strict where leniency would let something else pass: a label matches on word boundaries only
  (``Classpath:`` is not ``Path:``), a heading by its normalised title, and text inside fenced code
  or an HTML comment is not structure (a sample heading in a code block is not a section).
* Total: agent text never makes these raise; malformed input gives ``None`` / ``[]`` / ``False``.

Two words decide most content checks (DESIGN §5.2):

* *placeholder* -- the template's stand-in left in place: empty, ``-``, ``...``, ``TBD``, a value that
  is nothing but template brackets (``[test ids or none]``, ``[full path] [requirement tags]``), or
  a regex the rubric adds for its workflow (``NEEDS CLARIFICATION``).
* *none* -- a deliberate "nothing here": the whole value is a none token, or a none token, a
  delimiter and an explanation (``not applicable (no build)``, ``N/A - nothing``). Text that only
  starts with the word is a value (``None values -> raise``, ``Empty list input -> []``), and so is
  one whose explanation carries the field's own structure (an arrow, a path, a command).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

DEFAULT_NONE_VOCAB = ("none", "n/a", "na", "not applicable", "none stated", "nothing", "null", "nil", "empty", "not run", "no tests")

# --------------------------------------------------------------------------------------------
# Line model: which lines are markdown text, code, comments, fences, frontmatter
# --------------------------------------------------------------------------------------------
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?!#)(.*)$")
_HR = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
_TEXT, _CODE, _FENCE, _COMMENT, _FRONT = "text", "code", "fence", "comment", "front"


def _fence_open(line: str) -> tuple[str, str] | None:
    """(fence, language) when ``line`` opens a fenced block (a backtick fence's info has no backtick)."""
    m = _FENCE_OPEN.match(line)
    if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
        return None
    info = m.group(2).split()
    return m.group(1), (info[0].lower() if info else "")


def _is_close(line: str, fence: str) -> bool:
    s = line.strip()
    return len(s) >= len(fence) and set(s) == {fence[0]} and len(line) - len(line.lstrip(" \t")) <= 3


def _doc_fence(lines: list[str]) -> tuple[int, int] | None:
    """(open, close) line indexes when one fence wraps the whole document.

    A ``markdown``/``md`` fence is unwrapped even with inner fences (the language says "this is the
    document"); any other fence only when it is a single block, so a document that merely starts
    and ends with code blocks is left alone.
    """
    idx = [i for i, line in enumerate(lines) if line.strip()]
    if len(idx) < 2:
        return None
    a, b = idx[0], idx[-1]
    opened = _fence_open(lines[a].lstrip("\ufeff"))
    if not opened or not _is_close(lines[b], opened[0]):
        return None
    if opened[1] not in ("markdown", "md") and any(_is_close(lines[i], opened[0]) for i in range(a + 1, b)):
        return None
    return a, b


def _front_span(lines: list[str], lo: int, hi: int) -> tuple[int, int] | None:
    i = lo
    while i < hi and not lines[i].strip():
        i += 1
    if i >= hi or lines[i].strip().lstrip("\ufeff") != "---":
        return None
    for j in range(i + 1, hi):
        if lines[j].strip() in ("---", "..."):
            return i, j
    return None


def _view(text: str | None, unwrap: bool = True, front: bool = True) -> tuple[list[str], list[str], int]:
    """Lines, a kind per line, and the index where content ends (a closing document fence)."""
    lines = (text or "").splitlines()
    kinds = [_TEXT] * len(lines)
    lo, hi = 0, len(lines)
    if unwrap:
        span = _doc_fence(lines)
        if span:
            for i in [*range(0, span[0] + 1), *range(span[1], len(lines))]:
                kinds[i] = _FENCE
            lo, hi = span[0] + 1, span[1]
        fm = _front_span(lines, lo, hi) if front else None
        if fm:
            for i in range(fm[0], fm[1] + 1):
                kinds[i] = _FRONT
            lo = fm[1] + 1
    fence: str | None = None
    in_comment = False
    for i in range(lo, hi):
        line = lines[i]
        if fence:
            if _is_close(line, fence):
                kinds[i], fence = _FENCE, None
            else:
                kinds[i] = _CODE
            continue
        if in_comment:
            kinds[i] = _COMMENT
            in_comment = "-->" not in line
            continue
        opened = _fence_open(line)
        if opened:
            kinds[i], fence = _FENCE, opened[0]
            continue
        visible = strip_comments(line)
        if "<!--" in line and visible != line and line.rfind("<!--") > line.rfind("-->"):
            in_comment = True
        if line.strip() and not visible.strip():
            kinds[i] = _COMMENT
    return lines, kinds, hi


def strip_comments(text: str | None) -> str:
    """``text`` without HTML comments; an unclosed ``<!--`` hides the rest (linear scan)."""
    s = text or ""
    out, i = [], 0
    while True:
        a = s.find("<!--", i)
        if a < 0:
            out.append(s[i:])
            break
        out.append(s[i:a])
        b = s.find("-->", a + 4)
        if b < 0:
            break
        i = b + 3
    return "".join(out)


def strip_fence(text: str | None) -> tuple[str, bool]:
    """Unwrap one fence around the whole document (a copied skeleton's ```markdown fence)."""
    s = text or ""
    lines = s.splitlines()
    span = _doc_fence(lines)
    if not span:
        return s, False
    return "\n".join(lines[span[0] + 1 : span[1]]), True


# --------------------------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------------------------
_FM_KEY = re.compile(r"^([A-Za-z_][\w.-]*)[ \t]*:(?:[ \t](.*))?$")


@dataclass
class FrontMatter:
    present: bool
    valid: bool
    keys: list[str] = field(default_factory=list)  # in order, as written (case kept)
    values: dict[str, str] = field(default_factory=dict)  # unquoted scalar text
    body: str = ""  # the document after the frontmatter (fence-unwrapped)


def _fm_scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    m = re.search(r"[ \t]#", v)  # a YAML comment after a plain scalar
    return v[: m.start()].rstrip() if m else v


def frontmatter(text: str | None) -> FrontMatter:
    """The leading ``---`` block. ``valid``: closed, every line a ``key: value`` (or a continuation of
    one), no duplicate key, and YAML agrees it is a mapping. Never raises."""
    s, _ = strip_fence(text)
    lines = s.splitlines()
    span = _front_span(lines, 0, len(lines))
    if span is None:
        first = next((line for line in lines if line.strip()), "")
        return FrontMatter(first.strip().lstrip("\ufeff") == "---", False, [], {}, s)  # an unclosed block: present, invalid
    start, close = span
    keys: list[str] = []
    values: dict[str, str] = {}
    ok, last = True, None
    for line in lines[start + 1 : close]:
        st = line.strip()
        if not st or st.startswith("#"):
            continue
        if line[:1] in (" ", "\t") or st.startswith("- ") or st == "-":
            if last is None:
                ok = False
            else:
                values[last] = (values[last] + "\n" + st).strip()
            continue
        m = _FM_KEY.match(line)
        if not m:
            ok = False
            continue
        k = m.group(1)
        if k in values:
            ok = False
        else:
            keys.append(k)
        values[k] = _fm_scalar(m.group(2) or "")
        last = k
    block = "\n".join(lines[start + 1 : close])
    if ok and len(block) <= 65536:
        try:
            data = yaml.safe_load(block) if block.strip() else {}
            ok = data is None or isinstance(data, dict)
        except Exception:  # noqa: BLE001 -- agent text: any YAML failure is just "invalid"
            ok = False
    return FrontMatter(True, ok, keys, values, "\n".join(lines[close + 1 :]))


# --------------------------------------------------------------------------------------------
# Headings and sections
# --------------------------------------------------------------------------------------------
_WRAPPERS = ("**", "__", "*", "_")
_ANNOTATION = re.compile(r"\s*(?:[*_]\([^()]*\)[*_]|\((?:mandatory|optional|required)\))\s*$", re.I)


def _clean_title(t: str) -> str:
    t = t.strip()
    closed = t.rstrip("#")  # an ATX closing sequence: `## Title ##`
    if closed != t and (not closed or closed[-1].isspace()):
        t = closed.strip()
    prev = None
    while prev != t:
        prev = t
        t = t.strip().rstrip(":").strip()
        for w in _WRAPPERS:
            if len(t) > 2 * len(w) and t.startswith(w) and t.endswith(w) and w not in t[len(w) : -len(w)]:
                t = t[len(w) : -len(w)]
                break
    return t


def _atx(line: str) -> tuple[int, str] | None:
    m = _ATX.match(line)
    if not m:
        return None
    hashes, rest = m.group(1), m.group(2)
    if rest and not rest[0].isspace() and (len(hashes) == 1 or not (rest[0].isalpha() or rest[0] in "*_")):
        return None
    return len(hashes), _clean_title(rest)


def _heads(lines: list[str], kinds: list[str]) -> list[tuple[int, int, str]]:
    out = []
    for i, line in enumerate(lines):
        if kinds[i] == _TEXT:
            h = _atx(line)
            if h:
                out.append((i, h[0], h[1]))
    return out


def headings(text: str | None) -> list[tuple[int, str]]:
    """(level, title) of every ATX heading outside code and comments; title without #, bold, colon."""
    lines, kinds, _ = _view(text)
    return [(lv, t) for _, lv, t in _heads(lines, kinds)]


def _title_key(t: str) -> str:
    t = _clean_title(re.sub(r"\s+", " ", str(t)).lstrip(" #"))
    t = _ANNOTATION.sub("", t)
    return re.sub(r"\s+", " ", _clean_title(t)).strip().casefold()


def _squash(t: str) -> str:
    return re.sub(r"[\W_]+", "", t.replace("&", "and"))


MATCHES = ("exact_ci", "norm", "prefix", "regex")  # the heading match modes title_matches implements


def title_matches(title: str, heading: str, match: str = "exact_ci") -> bool:
    """``exact_ci``: equal ignoring case, bold, colon, whitespace and a ``*(mandatory)*``-style note;
    ``norm``: also ``&``/``and`` and punctuation; ``prefix``: the title starts with the heading (word
    boundary); ``regex``: ``heading`` searched in the title, case-insensitive."""
    if match == "regex":
        return re.search(heading, title, re.I) is not None
    a, b = _title_key(title), _title_key(heading)
    if match == "norm":
        return _squash(a) == _squash(b)
    if match == "prefix":
        return a == b or (bool(b) and a.startswith(b) and not a[len(b)].isalnum())
    return a == b


def _level(level) -> int | None:
    try:
        return None if level is None else int(level)
    except (TypeError, ValueError):
        return None


def section(text: str | None, heading: str | None, level: int | None = None, match: str = "exact_ci") -> str | None:
    """Body under the first matching heading, up to the next heading of the same or higher level."""
    if text is None or heading is None:
        return None
    lines, kinds, hi = _view(text)
    heads = _heads(lines, kinds)
    want = _level(level)
    for j, (i, lv, title) in enumerate(heads):
        if want is not None and lv != want:
            continue
        if not title_matches(title, heading, match):
            continue
        end = next((i2 for i2, lv2, _ in heads[j + 1 :] if lv2 <= lv), hi)
        return "\n".join(lines[i + 1 : end])
    return None


def subsections(body: str | None, pattern: str | None = None, level: int | None = None) -> list[tuple[str, str]]:
    """(title, body) of every heading inside ``body`` at ``level`` whose title matches ``pattern``
    (regex, case-insensitive): the repeated blocks of a section, e.g. ``### Step n`` under ``## Plan``."""
    if body is None:
        return []
    lines, kinds, hi = _view(body, unwrap=False)
    heads = _heads(lines, kinds)
    want = _level(level)
    out = []
    for j, (i, lv, title) in enumerate(heads):
        if want is not None and lv != want:
            continue
        if pattern and re.search(pattern, title, re.I) is None:
            continue
        end = next((i2 for i2, lv2, _ in heads[j + 1 :] if lv2 <= lv), hi)
        out.append((title, "\n".join(lines[i + 1 : end])))
    return out


def text_lines(body: str | None) -> list[str]:
    """Raw markdown lines of ``body`` outside fenced code, comments and frontmatter (headings kept)."""
    lines, kinds, _ = _view(body, unwrap=False)
    return [line for line, k in zip(lines, kinds, strict=True) if k == _TEXT and line.strip()]


# --------------------------------------------------------------------------------------------
# Labelled fields and lists
# --------------------------------------------------------------------------------------------
_SEP = r"(?:[—–|;]|(?<=\s)-{1,2}(?=\s))\s*"
_PREFIX = r"^\s*(?:(?:[-*+]|\d{1,3}[.)])\s+)?(?:\[[ xX]\]\s+)?"
_ANY_LABEL_LINE = re.compile(_PREFIX + r"(?:\*\*|__|`)?[A-Za-z][\w /&().\[\]-]{0,48}?(?:\*\*|__|`)?\s*:(?:\*\*|__)?(?=\s|$)")
_NEXT_LABEL = re.compile(_SEP + r"(?:\*\*|__|`)?[A-Za-z][\w /&().-]{0,40}?(?:\*\*|__|`)?\s*:(?:\*\*|__)?(?=\s|$)")
_LABEL_CACHE: dict[str, tuple[re.Pattern, re.Pattern]] = {}


def _label_res(label: str) -> tuple[re.Pattern, re.Pattern]:
    rx = _LABEL_CACHE.get(label)
    if rx is None:
        lab = r"\s+".join(re.escape(w) for w in label.split())
        head = rf"(?P<o>\*\*|__|\*|_|`)?{lab}(?(o)(?P=o)?)\s*:(?(o)(?:(?P=o))?)"
        rx = (re.compile(rf"{_PREFIX}{head}[ \t]*(?P<v>.*)$", re.I), re.compile(rf"{_SEP}{head}[ \t]*(?P<v>.*)$", re.I))
        if len(_LABEL_CACHE) < 512:
            _LABEL_CACHE[label] = rx
    return rx


def clean_value(v: str) -> str:
    """Strip whitespace, a trailing ``;`` and matched wrappers (``**``, ``*``, quotes, one code span)."""
    v = v.strip()
    prev = None
    while prev != v:
        prev = v
        v = v.strip().rstrip(";").strip()
        for w in ("**", "__", '"', "*"):
            if len(v) >= 2 * len(w) + 1 and v.startswith(w) and v.endswith(w) and w not in v[len(w) : -len(w)]:
                v = v[len(w) : -len(w)]
        if len(v) >= 2 and v[0] == v[-1] == "`" and "`" not in v[1:-1]:
            v = v[1:-1]
    return v


def strip_list_marker(line: str) -> str:
    """``line`` stripped, without a leading ``-``/``*``/``+``/``1.`` list marker."""
    return _LIST_MARK.sub("", line.strip(), count=1).strip()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _continuation(lines: list[str], kinds: list[str], i: int, attach_code: bool) -> list[str]:
    base, out, j = _indent(lines[i]), [], i + 1
    while j < len(lines):
        line, k = lines[j], kinds[j]
        if k == _COMMENT:
            j += 1
            continue
        if k in (_FENCE, _CODE):
            if not attach_code:
                break
            j += 1 if k == _FENCE else 0
            while j < len(lines) and kinds[j] == _CODE:
                out.append(lines[j].strip())
                j += 1
            if j < len(lines) and kinds[j] == _FENCE:
                j += 1
            continue
        s = line.strip()
        if not s or _atx(line) or _HR.match(line):
            break
        if _indent(line) <= base and _ANY_LABEL_LINE.match(line):
            break
        out.append(_LIST_MARK.sub("", s, count=1).strip())
        j += 1
    return out


def field_value(section_text: str | None, label: str | None, multiline: bool = False) -> str | None:
    """Value of a labelled field: ``- Label: v``, ``* **Label**: v``, ``**Label:** v``, ``Label: v``,
    or a label after a separator on the same line (``- Path: x — Contract: y``, ``a | **Date**: d``).

    Case-insensitive, word-bounded (``Classpath:`` never answers ``Path``); the value stops at the
    next label on its line. ``multiline`` adds the following lines that belong to it -- deeper
    indented lines, same-level non-label list items, a fenced block -- up to a blank line, another
    label line, or a heading. None when the label is absent; "" when present but empty.
    """
    if section_text is None or label is None or not str(label).strip():
        return None
    lines, kinds, _ = _view(section_text, unwrap=False)
    start_rx, inline_rx = _label_res(str(label).strip())
    for i, line in enumerate(lines):
        if kinds[i] != _TEXT:
            continue
        m = start_rx.match(line) or inline_rx.search(line)
        if not m:
            continue
        v = m.group("v")
        nxt = _NEXT_LABEL.search(v)
        parts = [(v[: nxt.start()] if nxt else v).strip()]
        if multiline and not nxt:
            parts += _continuation(lines, kinds, i, attach_code=not parts[0])
        return clean_value("\n".join(p for p in parts if p))
    return None


def _split_top(s: str) -> list[str]:
    parts, buf, depth, tick = [], [], 0, False
    for ch in s:
        if ch == "`":
            tick = not tick
        elif not tick:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch in ",;" and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
        buf.append(ch)
    parts.append("".join(buf))
    return parts


def split_list(value: str | None) -> list[str]:
    """Items of a list value: one per line / ``- `` item, lines split on ``,``/``;`` outside
    backticks, parentheses and brackets; each item cleaned like a field value."""
    if not value:
        return []
    out = []
    for line in str(value).splitlines():
        for part in _split_top(_LIST_MARK.sub("", line.strip(), count=1)):
            p = clean_value(part)
            if p:
                out.append(p)
    return out


def content_lines(body: str | None) -> list[str]:
    """Non-empty lines of ``body`` that carry content: no HTML comments, fence delimiters, headings
    or rules; list markers stripped. Lines inside fenced code count (as written, stripped)."""
    if not body:
        return []
    lines, kinds, _ = _view(body, unwrap=False)
    out = []
    for line, k in zip(lines, kinds, strict=True):
        if k in (_COMMENT, _FENCE, _FRONT):
            continue
        s = strip_comments(line).strip() if k == _TEXT else line.strip()
        if not s:
            continue
        if k == _TEXT:
            if _atx(line) or _HR.match(line):
                continue
            s = _LIST_MARK.sub("", s, count=1).strip()
        if s:
            out.append(s)
    return out


_CHECK = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+\[([ xX])\]\s*(.*)$")


def checkboxes(text: str | None) -> list[tuple[bool, str, int]]:
    """(checked, text, 1-indexed line) for ``- [ ]`` / ``- [x]`` / ``* [X]`` items outside code."""
    lines, kinds, _ = _view(text)
    out = []
    for i, line in enumerate(lines):
        if kinds[i] == _TEXT:
            m = _CHECK.match(line)
            if m:
                out.append((m.group(1) in "xX", m.group(2).strip(), i + 1))
    return out


# --------------------------------------------------------------------------------------------
# Placeholder / none
# --------------------------------------------------------------------------------------------
_PH_WORD = re.compile(r"(?:[-—–]+|_+|\.{2,}|…+|\?+|tbd|tba|todo|fixme|x+|placeholder)[.!:]?", re.I)
_IDLIST = re.compile(r"\s*[A-Za-z]{1,5}-?\d+(?:\s*[,;/]\s*[A-Za-z]{1,5}-?\d+)*\s*")
_GROUPS = (re.compile(r"\[([^\[\]\n]*)\]"), re.compile(r"<([^<>\n]*)>"), re.compile(r"\{([^{}\n]*)\}"))
_ALT = re.compile(r"\([^()|\n]+(?:\|[^()|\n]+)+\)")


def is_placeholder(value: str | None, extra: list[str] | None = None) -> bool:
    """The template's stand-in, not a value: empty, ``-``, ``...``, ``?``, ``TBD``/``TODO``/``FIXME``
    or a run of ``x`` (``x``, ``xxx``: the fill-in-later mark) alone, a value made only of template
    ``[..]``/``<..>``/``{..}`` groups (and punctuation, or a ``(a | b)`` choice left unmade), or a
    match of any regex in ``extra``. A bracketed id list (``[R1, R2]``) is a value; so is a
    one-letter name such as ``C``."""
    if value is None:
        return True
    v = clean_value(str(value))
    if not v or _PH_WORD.fullmatch(v):
        return True
    rest = v
    for rx in _GROUPS:
        rest = rx.sub(lambda m: m.group(0) if _IDLIST.fullmatch(m.group(1)) else " ", rest)
    if rest != v and not re.sub(r"[\W_]+", "", _ALT.sub(" ", rest)):
        return True
    for pat in extra or ():
        try:
            if re.search(pat, v, re.I | re.M):
                return True
        except re.error:
            continue
    return False


_NONE_DELIM = re.compile(r"\s*\(|\s*[—–]|\s+-{1,2}\s|\s*:(?!:)|\s*,|\s*;|\.(?![\w/])")
_CODE_EXT = r"py|pyi|pyx|js|jsx|mjs|cjs|ts|tsx|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|swift|scala|sh|bash|yml|yaml|json|toml|cfg|ini|md|rst|txt|html|css|sql|xml|gradle|lock"
_FILE = re.compile(rf"^[\w.-]+\.(?:{_CODE_EXT})$", re.I)
is_file_name = _FILE.match
_CODE_SPAN = re.compile(r"`([^`\n]*)`")


def _has_structure(text: str) -> bool:
    """An arrow, a path / file name, a test id or a multi-word code span: the shape of a real value."""
    t = text[:4000]
    if any(a in t for a in ("->", "→", "=>", "::")) or any(len(m.group(1).split()) > 1 for m in _CODE_SPAN.finditer(t)):
        return True
    for raw in t.split():
        tok = raw.strip("()[]{}<>,;:'\"`*")
        if "/" in tok and re.search(r"\w", tok):
            if tok.startswith(("/", "./", "../", "~/")) or tok.count("/") >= 2 or re.search(r"\.\w{1,5}$", tok):
                return True
        elif _FILE.match(tok):
            return True
    return False


# A none claim phrased without a delimiter (REVIEW-REAL: 'None recorded (initial state)', 'none identified',
# 'None known', 'None found', 'No deviations'): the token ``none`` followed by one of these words, or ``no`` and
# one of the result nouns. Closed lists: ``None values -> raise`` / ``None input ...`` (a value about None) and
# ``Nothing to fix in X`` stay content, and so does ``None stated in the task`` (the "none stated" vocabulary's own).
_NONE_QUALIFIER = re.compile(
    r"\s+(?:(?:explicitly|specifically|currently|initially|newly|actually|yet)\s+)?"
    r"(?:recorded|identified|identifiable|known|found|observed|detected|noted|reported|seen|expected|required|needed|necessary|confirmed"
    r"|verified|tested|executed|run|introduced|caused|related|remaining|outstanding|pre-?existing|applicable|apparent|present|listed"
    r"|so\s+far|yet|at\s+(?:this|that|the)\s+(?:point|time|stage)|at\s+baseline|in\s+(?:the\s+)?baseline)\b"
)
_NO_CLAIM = re.compile(
    r"no\s+(?:(?:new|additional|further|remaining|known|other|existing|specific|outstanding|unintended|unmet|pre-?existing|test)\s+)*"
    r"(?:deviations?|failures?|failing|regressions?|fix(?:es)?|changes?|modifications?|edits?|issues?|problems?|errors?|tests?|requirements?|files?)\b"
)
_ARROWS = ("->", "→", "=>")


def _none_claim(head: str, toks: list[str], more: str) -> bool:
    """``head`` (case-folded first line) is a none claim without a delimiter: ``none`` + a qualifier word, or ``no`` + a
    result noun -- with no arrow after it (the field's own ``id -> reasoning`` / ``condition -> behaviour`` structure)
    and no structured lines under it (a list of ids or paths is content)."""
    if "none" not in toks:
        return False
    m = _NONE_QUALIFIER.match(head, 4) if head.startswith("none") else None
    m = m or _NO_CLAIM.match(head)
    if not m:
        return False
    rest = head[m.end() :]
    return not any(a in rest for a in _ARROWS) and not (more and _has_structure(more))


def is_none(value: str | None, vocab: list[str] | None = None) -> bool:
    """The value says "nothing here" (DESIGN §5.2): the whole value is a none token, or a none token
    followed by a delimiter (``(``, ``—``, `` - ``, ``:``, ``,``, ``;``, ``.``, a new line) and an
    explanation without the field's own structure. ``vocab`` replaces the default tokens. With ``none``
    among the tokens, a claim phrased without a delimiter is one too: ``none`` and a qualifier
    (``None recorded (initial state)``, ``none identified yet``, ``None known``, ``None found``) or ``no`` and a
    result noun (``No deviations from the plan``, ``No pre-existing failures found``), arrows excepted; and
    so is a whole value in parentheses (``(none)``)."""
    if value is None:
        return False
    v = clean_value(str(value))
    if len(v) > 2 and v[0] == "(" and v[-1] == ")" and "(" not in v[1:-1] and "\n" not in v:
        v = clean_value(v[1:-1])
    if not v:
        return False
    first, _, more = v.partition("\n")
    head = re.sub(r"\s+", " ", clean_value(first).strip("'")).casefold()
    tokens = DEFAULT_NONE_VOCAB if vocab is None else vocab
    toks = sorted({re.sub(r"\s+", " ", str(t)).strip().casefold() for t in tokens if str(t).strip()}, key=len, reverse=True)
    for t in toks:
        if not head.startswith(t):
            continue
        rest = head[len(t) :]
        if not rest.strip(" .!"):
            expl = ""
        else:
            m = _NONE_DELIM.match(rest)
            if not m:
                continue
            expl = rest[m.end() :]
        return not _has_structure(f"{expl}\n{more}" if more else expl)
    return _none_claim(head, toks, more)


__all__ = [
    "DEFAULT_NONE_VOCAB",
    "MATCHES",
    "FrontMatter",
    "checkboxes",
    "clean_value",
    "content_lines",
    "field_value",
    "frontmatter",
    "headings",
    "is_file_name",
    "is_none",
    "is_placeholder",
    "section",
    "split_list",
    "strip_comments",
    "strip_list_marker",
    "strip_fence",
    "subsections",
    "text_lines",
    "title_matches",
]
