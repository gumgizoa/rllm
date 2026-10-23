"""Artifact check kinds: does the file a stage produced exist where it should, in its template's
shape, with values that are really filled in -- and, where the run can say, true?

Each kind reads the artifact through ``ctx.artifact_text(id, state)`` (the sandbox file for
``final``, the trace replay at the end of the owning stage's window for ``stage_end``) and parses it
with :mod:`..markdown` only. An absent artifact, a missing section or a broken frontmatter is a
``fail`` with a reason, never an exception: the agent controls all of it.

The content kinds close the gaps DESIGN §12 lists for the hand-written AI-DLC reward:

* a value counts only when it is neither a placeholder nor -- unless the item's ``none_allowed``
  says so -- a none value; a none word outside the field's own vocabulary (``none_vocab``) is not
  an allowed none, and ``R1: [statement]`` / ``R1: none`` are judged by what follows the id;
* a value the run can contradict is checked against facts the agent did not write
  (``field_type``: the command was run, the path exists in the repo, the test id appears in a valid
  run's output; ``field_literal.refuted_by``; ``cross_ref`` against diff / base tree / run facts).

Parameters are exactly those of CONTRACT §2.9. ``section`` may also be ``null``/``""``/``"*"`` (the
whole document below the frontmatter: spec-kit's ``**Created**:`` sits under a title that varies)
or ``{heading, level, match}``.
"""

from __future__ import annotations

import fnmatch
import re

from .. import evidence, refs
from .. import markdown as M
from ..context import EvalContext, Result
from ..refs import NORMALIZERS, RELATIONS
from ..schema import Artifact, Item
from . import register

_ONLINE_FACTS = ("diff_paths", "diff_test_paths", "untracked_paths", "base_paths")
# the values of each enumerated parameter the kinds below implement (the generator rejects any other)
FIELD_TYPES = ("command_run", "repo_path", "test_id", "failed_test_id", "test_selection")
RUN_KINDS = ("test", "build")


# --------------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------------
def _params(item: Item) -> dict:
    return item.check.params or {}


def _artifact_id(item: Item) -> str:
    return _params(item).get("artifact") or item.target.ref


def _text(item: Item, ctx: EvalContext) -> str | None:
    t = ctx.artifact_text(_artifact_id(item), item.target.state)
    return None if t is None else M.strip_fence(t)[0]


def _scope(text: str, section) -> str | None:
    if section is None or (isinstance(section, str) and section.strip() in ("", "*")):
        return M.frontmatter(text).body
    if isinstance(section, dict):
        return M.section(text, section.get("heading"), section.get("level"), section.get("match", "exact_ci"))
    return M.section(text, str(section))


def _body(item: Item, ctx: EvalContext, section) -> tuple[str | None, Result | None]:
    text = _text(item, ctx)
    if text is None:
        return None, Result.no(item, f"artifact {_artifact_id(item)} absent")
    body = _scope(text, section)
    if body is None:
        return None, Result.no(item, f"section {section!r} absent")
    return body, None


def _window(item: Item, ctx: EvalContext):
    p = _params(item)
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    return refs.window(ctx, spec)


def _owning_stage(ctx: EvalContext, artifact_id: str) -> str | None:
    return next((st.id for st in ctx.rubric.stages if artifact_id in st.artifacts), None)


def _norm_text(s: str) -> str:
    s = re.sub(r"[*`]", "", M.strip_list_marker(str(s)))
    return re.sub(r"\s+", " ", s).strip().rstrip(".").strip().casefold()


def _short(v: str, n: int = 60) -> str:
    v = v.replace("\n", " / ")
    return v if len(v) <= n else v[: n - 3] + "..."


# --------------------------------------------------------------------------------------------
# Location templates (roots, vars) -> concrete paths / regexes
# --------------------------------------------------------------------------------------------
_NAME = re.compile(r"\{([A-Za-z_]\w*)\}")


def _value_of(ctx: EvalContext, name: str, depth: int = 0) -> str | None:
    c = ctx.collected
    if name == "WORKDIR":
        return c.workdir
    if name == "BASE_SHA":
        return c.base_sha
    if name in ctx.rubric.roots and depth < 4:
        return _expand(ctx, ctx.rubric.roots[name], depth + 1)
    if name == "code":
        return c.workdir
    return ctx.facts.var_bindings.get(name)


def _expand(ctx: EvalContext, template: str, depth: int = 0) -> str:
    """Substitute roots, ``WORKDIR``/``BASE_SHA`` and bound vars; unresolved names stay ``{NAME}``."""

    def rep(m: re.Match) -> str:
        v = _value_of(ctx, m.group(1), depth)
        return v if v is not None else m.group(0)

    return _NAME.sub(rep, template)


def _root(ctx: EvalContext, name: str) -> str | None:
    v = _value_of(ctx, name)
    return None if v is None or _NAME.search(v) else v.rstrip("/")


def _location_regex(ctx: EvalContext, template: str) -> re.Pattern:
    parts, pos, s = [], 0, _expand(ctx, template)
    for m in _NAME.finditer(s):
        parts.append(re.escape(s[pos : m.start()]))
        parts.append(r"\d{4}-\d{2}-\d{2}" if m.group(1) == "DATE" else r"[^/]+")
        pos = m.end()
    parts.append(re.escape(s[pos:]))
    return re.compile("".join(parts).rstrip("/") + "/?")


def _locations_found(ctx: EvalContext, art: Artifact) -> int:
    """How many of the artifact's locations hold it at the end (exclusive artifacts need exactly one)."""
    for attr in ("location_counts", "_location_counts"):  # if facts recorded the count itself
        d = getattr(ctx.facts, attr, None)
        if isinstance(d, dict) and art.id in d:
            return int(d[art.id])
    pool = ctx.collected.dirs if art.kind == "dir" else ctx.collected.files.keys()
    pool = list(pool)
    return sum(1 for loc in art.locations if any(_location_regex(ctx, loc).fullmatch(p) for p in pool))


# --------------------------------------------------------------------------------------------
# Existence and paths
# --------------------------------------------------------------------------------------------
@register("artifact_exists", params={"artifact": False})
def artifact_exists(item: Item, ctx: EvalContext) -> Result:
    """final: the artifact resolved in the sandbox (an exclusive one at exactly one location);
    stage_end: the replay holds non-empty content at the end of its stage."""
    aid = _artifact_id(item)
    art = ctx.rubric.artifacts.get(aid)
    if art is None:
        return Result.no(item, f"artifact {aid!r} undefined")
    path = ctx.facts.artifact_paths.get(aid)
    if item.target.state == "stage_end":
        if art.kind == "dir":
            return _dir_at_stage_end(item, ctx, art, path)
        t = ctx.artifact_text(aid, "stage_end")
        return Result.ok(item, "written by stage end") if t and t.strip() else Result.no(item, "absent or empty at stage end")
    if not path:
        return Result.no(item, "absent")
    if art.exclusive:
        n = _locations_found(ctx, art)
        if n > 1:
            return Result.no(item, f"found at {n} locations (must be one)")
    return Result.ok(item, path)


def _dir_at_stage_end(item: Item, ctx: EvalContext, art: Artifact, path: str | None) -> Result:
    if not path:
        return Result.no(item, "absent")
    # a directory that later moved (an OpenSpec change, archived) was written where it was at the time
    from ..facts import location_paths

    prefixes = tuple(dict.fromkeys(p.rstrip("/") + "/" for p in [path, *location_paths(ctx.rubric, ctx.facts, ctx.collected, art)] if p))
    steps = [e.step for p, evs in ctx.facts.writes.items() if p.startswith(prefixes) for e in evs if e.ok is not False and e.op not in ("delete", "move_out")]
    w = ctx.facts.windows.get(_owning_stage(ctx, art.id) or "")
    end = w[1] if w else None
    if not steps or end is None or any(s < end for s in steps):
        return Result.ok(item, path)
    return Result.no(item, "only written after its stage")


@register("path_match", params={"pattern": True, "artifact": False, "relative_to": False})
def path_match(item: Item, ctx: EvalContext) -> Result:
    """The resolved path, relative to root ``relative_to`` (default ``artifact``), fully matches
    ``pattern`` (a regex; ``glob:<pattern>`` for a glob)."""
    p = _params(item)
    path = ctx.facts.artifact_paths.get(_artifact_id(item))
    if not path:
        return Result.no(item, "absent")
    base = _root(ctx, p.get("relative_to", "artifact"))
    rel = path[len(base) + 1 :] if base and path.startswith(base + "/") else path
    pat = str(p["pattern"])
    ok = fnmatch.fnmatchcase(rel, pat[5:]) if pat.startswith("glob:") else re.fullmatch(pat, rel) is not None
    return Result.ok(item, rel) if ok else Result.no(item, f"{rel} does not match")


# --------------------------------------------------------------------------------------------
# Structure: frontmatter, sections, labels
# --------------------------------------------------------------------------------------------
def _fm_value_ok(got: str, want) -> bool:
    got = got.strip()
    if isinstance(want, dict) and "regex" in want:
        return re.fullmatch(str(want["regex"]), got) is not None
    if isinstance(want, bool):
        return got.casefold() == str(want).casefold()
    w = str(want).strip()
    if got == w:
        return True
    try:
        return int(got) == int(w)
    except ValueError:
        return False


@register("frontmatter", params={"keys": False, "exact": False, "values": False})
def frontmatter(item: Item, ctx: EvalContext) -> Result:
    """A valid frontmatter with ``keys`` (exactly these, in order, with ``exact``) and ``values``."""
    p = _params(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    fm = M.frontmatter(text)
    if not fm.present:
        return Result.no(item, "no frontmatter")
    if not fm.valid:
        return Result.no(item, "frontmatter does not parse")
    keys = [str(k) for k in p.get("keys") or []]
    if keys and p.get("exact") and fm.keys != keys:
        return Result.no(item, f"keys {fm.keys} != {keys}")
    missing = [k for k in keys if k not in fm.keys]
    if missing:
        return Result.no(item, f"missing keys {missing}")
    for k, want in (p.get("values") or {}).items():
        got = fm.values.get(str(k))
        if got is None:
            return Result.no(item, f"no value for {k}")
        if not _fm_value_ok(got, want):
            return Result.no(item, f"{k}: {_short(got)!r}")
    return Result.ok(item, ",".join(fm.keys))


@register("section_present", params={"heading": True, "level": False, "match": False}, choices={"match": M.MATCHES})
def section_present(item: Item, ctx: EvalContext) -> Result:
    """The heading exists (at ``level`` if given), matched by ``match`` (exact_ci | norm | prefix | regex)."""
    p = _params(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    found = M.section(text, str(p["heading"]), p.get("level"), p.get("match", "exact_ci")) is not None
    return Result.ok(item) if found else Result.no(item, f"no heading {p['heading']!r}")


@register("label_present", params={"section": True, "label": True})
def label_present(item: Item, ctx: EvalContext) -> Result:
    """A ``label:`` line (word-bounded) exists in the section."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    return Result.ok(item) if M.field_value(body, str(p["label"])) is not None else Result.no(item, f"no label {p['label']!r}")


# --------------------------------------------------------------------------------------------
# Field values
# --------------------------------------------------------------------------------------------
@register("field_literal", params={"section": True, "text": True, "label": False, "refuted_by": False})
def field_literal(item: Item, ctx: EvalContext) -> Result:
    """The label's value (or, without a label, some line of the section) equals ``text`` (whitespace,
    case, emphasis and list marker ignored), and the run does not refute it (``refuted_by``)."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    texts = p["text"] if isinstance(p["text"], (list, tuple)) else [p["text"]]
    want = {_norm_text(t) for t in texts}
    if p.get("label"):
        v = M.field_value(body, str(p["label"]))
        if v is None:
            return Result.no(item, f"no label {p['label']!r}")
        if _norm_text(v) not in want:
            return Result.no(item, f"{p['label']}: {_short(v)!r}")
    elif not any(_norm_text(line) in want for line in M.content_lines(body)):
        return Result.no(item, "text not found")
    if p.get("refuted_by") is not None and refs.predicate(ctx, p["refuted_by"]):
        return Result.no(item, "refuted by the run")
    return Result.ok(item)


_LINE_LABEL = re.compile(r"^(?:\*\*|__)?[A-Za-z][\w /&().\[\]-]{0,48}?(?:\*\*|__)?\s*:(?:\*\*|__)?\s+(?=\S)")
_LABEL_ONLY = re.compile(r"^(?:\*\*|__)?[A-Za-z][\w /&().\[\]-]{0,48}?(?:\*\*|__)?\s*:(?:\*\*|__)?\s*$")


def _none_kind(v: str, vocab) -> str | None:
    """``none``: a none value under the field's vocabulary; ``foreign``: none-like only under the
    default vocabulary -- not a none the field allows (DESIGN §5.2: per-field vocabularies)."""
    if M.is_none(v, vocab):
        return "none"
    if vocab is not None and M.is_none(v):
        return "foreign"
    return None


def _fill_state(body: str, p: dict) -> tuple[str, str]:
    """(content | none | foreign | placeholder | empty | absent | few, detail) for one scope."""
    label, extra, vocab, min_items = p.get("label"), p.get("placeholders"), p.get("none_vocab"), p.get("min_items")
    if label:
        v = M.field_value(body, str(label), multiline=True)
        if v is None:
            return "absent", f"no label {label!r}"
        if M.is_placeholder(v, extra):
            return "placeholder", f"{label}: placeholder {_short(v)!r}"
        kind = _none_kind(v, vocab)
        if kind:
            return kind, f"{label}: {_short(v)!r}"
        items = [x for x in M.split_list(v) if not M.is_placeholder(x, extra) and not _none_kind(x, vocab)]
    else:
        items, nones = [], []
        for line in M.content_lines(body):
            if _LABEL_ONLY.match(line):
                continue
            core = _LINE_LABEL.sub("", line, count=1)
            if M.is_placeholder(line, extra) or M.is_placeholder(core, extra):
                continue
            kind = _none_kind(core, vocab) or _none_kind(line, vocab)
            if kind:
                nones.append(kind)
            else:
                items.append(line)
        if not items:
            if not nones:
                return "empty", "no content"
            return ("foreign" if "foreign" in nones else "none"), "none"
    if min_items is not None and len(items) < int(min_items):
        return "few", f"{len(items)} items < {min_items}"
    return "content", f"{len(items)} items"


def _none_policy(item: Item, ctx: EvalContext) -> tuple[bool, str]:
    na = item.none_allowed
    if isinstance(na, dict) and "if" in na:
        ok = refs.predicate(ctx, na["if"])
        return ok, "none, consistent with the run" if ok else "none, contradicted by the run"
    if na == "no":
        return False, "none not allowed"
    return True, "none allowed"


def _filled(item: Item, ctx: EvalContext, body: str, p: dict) -> tuple[bool, str]:
    state, detail = _fill_state(body, p)
    if state == "content":
        return True, detail
    if state == "none":
        ok, why = _none_policy(item, ctx)
        return ok, f"{detail}: {why}"
    if state == "foreign":
        return False, f"{detail}: not a none this field allows"
    return False, detail


@register("field_filled", params={"section": True, "label": False, "placeholders": False, "none_vocab": False, "per_block": False, "min_items": False})
def field_filled(item: Item, ctx: EvalContext) -> Result:
    """The label's value (or the section's content) is present and not a placeholder; a none value
    is judged by ``item.none_allowed``. ``per_block``: every block under matching headings (ratio)."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    pb = p.get("per_block")
    if not pb:
        ok, detail = _filled(item, ctx, body, p)
        return Result.ok(item, detail) if ok else Result.no(item, detail)
    blocks = M.subsections(body, pb.get("heading_pattern"), pb.get("level")) if isinstance(pb, dict) else M.subsections(body)
    if not blocks:
        return Result.no(item, "no blocks")
    bad = []
    for title, b in blocks:
        ok, detail = _filled(item, ctx, b, p)
        if not ok:
            bad.append(f"{_short(title, 30)}: {detail}")
    return Result.ratio(item, len(blocks) - len(bad), len(blocks), "; ".join(bad[:3]) or f"{len(blocks)} blocks")


def _norm_enum(v: str) -> str:
    return re.sub(r"\s+", " ", M.clean_value(v)).strip().rstrip(".").strip().casefold()


@register("field_enum", params={"section": True, "label": True, "values": True, "prefix_ok": False})
def field_enum(item: Item, ctx: EvalContext) -> Result:
    """The value is one of ``values`` (case-insensitive); ``prefix_ok``: starts with one at a word
    boundary (``failure (missing module)``) -- a copied ``a | b`` choice never passes."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    label = str(p["label"])
    v = M.field_value(body, label)
    if v == "":
        v = (M.field_value(body, label, multiline=True) or "").split("\n")[0]
    if v is None:
        return Result.no(item, f"no label {label!r}")
    nv = _norm_enum(v)
    vals = [_norm_enum(str(x)) for x in p["values"]]
    if nv in vals:
        return Result.ok(item, nv)
    if p.get("prefix_ok"):
        present = [x for x in vals if x and re.search(rf"(?<!\w){re.escape(x)}(?!\w)", nv)]
        starts = [x for x in vals if x and nv.startswith(x) and (len(nv) == len(x) or not nv[len(x)].isalnum())]
        if starts and not ("|" in nv and len(present) > 1):
            return Result.ok(item, nv)
    return Result.no(item, f"{label}: {_short(v)!r}")


# --------------------------------------------------------------------------------------------
# Typed values, checked against the run
# --------------------------------------------------------------------------------------------
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_PATH_TOKEN = re.compile(r"[\w.~/-]*[\w-]/[\w./-]+|[\w-]+\.[A-Za-z0-9]{1,8}\b")


def _ws_runs(s: str) -> str:
    """Each whitespace run as one space (one newline if it held one): what ``refs.norm_command`` keeps
    anyway, and its ``\\s*`` patterns stay linear on agent text with huge runs."""
    return re.sub(r"\s+", lambda m: "\n" if "\n" in m.group() else " ", s)


def _norm_cmd(c: str) -> str:
    return refs.norm_command(_ws_runs(c))


def _command_candidates(v: str) -> set[str]:
    raw = [v, *v.splitlines(), *_CODE_SPAN.findall(v)]
    out = {_norm_cmd(re.sub(r"^\$\s+", "", x.strip())) for x in raw if x.strip()}
    out.discard("")
    return out


def _command_run(item: Item, ctx: EvalContext, v: str, w, run_kind) -> Result:
    """Without ``run_kind`` any command (or segment) run in the window; with it, a *valid* run of that kind
    (evidence.py): the recorded test command is the one that produced the evidence, not one whose run was
    void (no summary, runner missing, zero tests). Spellings of one invocation compare equal (refs.norm_command)."""
    known: set[str] = set()
    if run_kind is None:
        for c in ctx.facts.commands:
            if refs.in_window(c.step, w):
                known |= {_norm_cmd(x) for x in (c.command, *c.segments) if x}
    void = False
    for r in ctx.facts.runs:
        if refs.in_window(r.step, w) and (run_kind is None or r.kind == run_kind):
            forms = {_norm_cmd(x) for x in (r.command, r.segment) if x}
            if run_kind is not None and not r.valid:
                void = void or bool(_command_candidates(v) & forms)
                continue
            known |= forms
    known.discard("")
    if _command_candidates(v) & known:
        return Result.ok(item, "command was run")
    if void:
        return Result.no(item, f"{_short(v)!r} was run in the window, but no such run is valid {run_kind} evidence")
    return Result.no(item, f"{_short(v)!r} not run in the window")


def _test_selection(item: Item, ctx: EvalContext, v: str) -> Result:
    """Some form of the value (whole, a line, a code span) is a test command that selects tests rather
    than the whole suite (paths, ids, labels, a keyword filter, a subdirectory cwd; from the code root).
    A value with no test runner we can read is not this check's to judge (``command_run`` and the
    execution items are): ``not_applicable``."""
    raw = [v, *v.splitlines(), *_CODE_SPAN.findall(v)]
    verdicts = [evidence.command_selection(re.sub(r"^\$\s+", "", x.strip()), ctx.collected.workdir) for x in raw if x.strip()]
    if any(ok for ok, _ in verdicts):
        return Result.ok(item, "a targeted test command")
    if any(ok is False for ok, _ in verdicts):
        return Result.no(item, f"{_short(v)!r}: a test runner selecting the whole suite")
    return Result.not_applicable(item, "no test-runner invocation whose selection is read")


def _path_of(entry: str, workdir: str | None) -> str:
    s = entry.replace("`", "").strip()[:500]
    m = _PATH_TOKEN.search(s)
    tok = m.group(0) if m else s
    tok = re.sub(r"::.*$", "", tok)
    tok = re.sub(r":\d+(?::\d+)?$", "", tok)
    return refs.norm_path(tok, workdir)


def _path_known(p: str, known: set[str]) -> bool:
    if p in known:
        return True
    d = p.rstrip("/") + "/"
    return any(k.startswith(d) for k in known)


def _repo_path(item: Item, ctx: EvalContext, entries: list[str]) -> Result:
    c, f = ctx.collected, ctx.facts
    paths = [_path_of(x, c.workdir) for x in entries]
    base = {p for p, ok in c.base_present.items() if ok} if c.base_present is not None else None
    diff = set(c.diff) if c.diff is not None else None
    known = (base or set()) | (diff or set())
    if ctx.mode == "offline":
        known |= {e.path for e in f.repo_writes if e.ok is not False} | set(f.edits_by_path)
    elif base is None and diff is None:
        return Result.no(item, "no base tree or diff online")
    hits = [p for p in paths if p and _path_known(p, known)]
    if ctx.mode == "offline" and base is None and len(hits) < len(paths):
        return Result.unavailable(item, "offline: paths the agent did not write cannot be checked")
    misses = [p for p in paths if p not in hits]
    return Result.ratio(item, len(hits), len(paths), f"{len(hits)}/{len(paths)} paths in the repo" + (f"; not: {misses[:3]}" if misses else ""))


_ID_LIKE = re.compile(r"\S*(?:[_./:\d]|test|Test)\S*")


def _id_keys(entry: str) -> set[str]:
    """Loose keys for one test id (DESIGN §5.2: file / module level): the id, its file part, its last
    component, django's ``name (module.Class)`` pieces -- only tokens shaped like test ids, so prose
    ("all tests passed") matches nothing."""
    s = re.sub(r"\s+", " ", entry[:500]).strip().strip("`*")
    s = re.split(r"\s+(?:—|–|-{1,2}>?|→)\s+|:\s", s, maxsplit=1)[0].strip()
    first = s.split()[0] if s.split() else s
    keys = {s, first}
    m = re.match(r"([\w.\[\]-]+)\s*\(([\w.]+)\)", s)
    if m:
        keys |= {m.group(1), m.group(2), f"{m.group(2)}.{m.group(1)}"}
    if "::" in first:
        parts = first.split("::")
        keys |= {parts[0], parts[-1]}
    elif "." in first and "/" not in first and not M.is_file_name(first):  # mod.tests.Class.test_x
        keys |= set(first.rsplit(".", 1))
    keys = {k.strip("`*,;()") for k in keys}
    return {k for k in keys if len(k) >= 4 and " " not in k and _ID_LIKE.fullmatch(k)} | ({s} if " " in s and _ID_LIKE.search(s) and "(" in s else set())


def _dotted(path: str) -> list[str]:
    """Dotted module forms of a repo path or node id (``tests/delete/tests.py`` -> ``tests.delete.tests``, ``delete.tests``):
    how django / unittest labels name the same file (runtests.py resolves labels against ``tests/``)."""
    p = path.split("::", 1)[0].strip().strip("/")
    if p.endswith(".py"):
        p = p[:-3]
    if not p or not re.fullmatch(r"[\w./-]+", p):
        return []
    d = p.replace("/", ".").strip(".")
    out = [d]
    if d.startswith("tests."):
        out.append(d[len("tests.") :])
    return [x for x in out if x]


def _entry_parts(entry: str) -> tuple[str | None, str | None]:
    """(module / file part as dotted, test name) of one recorded test id; either may be None.

    ``tests/a.py::TestX::test_y`` -> (``tests.a``, ``test_y``); ``test_y (delete.tests.T)`` -> (``delete.tests.T``, ``test_y``);
    ``delete.tests.T.test_y`` -> (``delete.tests.T``, ``test_y``); ``tests/a.py`` / ``delete.tests`` -> (module, None)."""
    s = re.sub(r"\s+", " ", entry[:500]).strip().strip("`*")
    s = re.split(r"\s+(?:—|–|-{1,2}>?|→)\s+|:\s", s, maxsplit=1)[0].strip()
    m = re.match(r"(\w+)(?:\[[^\]]*\])?\s*\(([\w.]+)\)", s)
    if m:
        return m.group(2), m.group(1)
    tok = s.split(" ")[0] if s else ""
    if "::" in tok:
        parts = tok.split("::")
        mods = _dotted(parts[0])
        return (mods[0] if mods else None), (parts[-1].split("[")[0] or None)
    if "/" in tok or tok.endswith(".py"):
        mods = _dotted(tok)
        return (mods[0] if mods else None), None
    tok = re.sub(r"\[[^\]]*\]$", "", tok)  # a parametrised name: test_x[1]
    if re.fullmatch(r"[A-Za-z_][\w.]*", tok or "-"):
        head, _, last = tok.rpartition(".")
        if last.lower().startswith("test") and not last[:1].isupper():
            return (head or None), last
        return tok, None
    return None, None


def _under(mod: str, prefix: str) -> bool:
    """``mod`` is ``prefix`` or inside it; the empty prefix (a run that selected nothing: the whole suite) holds everything."""
    return prefix == "" or mod == prefix or mod.startswith(prefix + ".")


_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)\s*\(", re.M)
_GREP_LINE = re.compile(r"^(\S+?\.py)[:-]\d+[:-]")
_LINE_NO = re.compile(r"^\s*\d+(?:\t|[:-])")  # an editor view / `cat -n` / `grep -n` line number


def _observed_defs(ctx: EvalContext) -> dict[str, set[str]]:
    """Test function name -> dotted forms of the base-repo files whose observed source (an editor view, ``cat`` /
    ``sed -n`` / ``grep -n`` output) defines it -- before the run wrote that file; files the run created never count."""
    cached = ctx.cache.get("observed_defs")
    if cached is not None:
        return cached
    from ..facts import is_new_path
    from ..trace import shell

    wd = ctx.collected.workdir or ""
    first_write: dict[str, int] = {}
    for e in ctx.facts.repo_writes:
        first_write.setdefault(e.path, e.step)
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    out: dict[str, set[str]] = {}

    def add(rel: str, text: str, step: int) -> None:
        if not rel.endswith(".py") or rel.startswith("/") or is_new_path(ctx, rel) or first_write.get(rel, 1 << 30) <= step:
            return
        for name in _DEF.findall(text[:400_000]):
            out.setdefault(name, set()).update(_dotted(rel))

    for st in ctx.run.steps:
        for idx, a in enumerate(st.actions):
            obs = a.observation or ""
            if "def test" not in obs:
                continue
            cwd = cwd_track.get((st.n, idx), wd)
            targets: list[str] = []
            if a.kind == "view" and a.path:
                targets = [shell.resolve(a.path, cwd)]
            elif a.kind == "shell" and a.command:
                try:
                    targets = [t for seg in shell.flat(shell.split(a.command[:20000], cwd)[0]) for t in shell.read_targets(seg, [])]
                except Exception:  # noqa: BLE001 -- agent text
                    targets = []
            # a line names its file (grep -n / -H output) or belongs to the file(s) the action read: with several
            # (`cat a.py tests/test_a.py`) a definition is credited to each -- only `def test*` names are taken
            read = [refs.norm_path(t, wd) for t in targets[:20]]
            by_file: dict[str, list[str]] = {}
            for line in obs.splitlines()[:20000]:
                m = _GREP_LINE.match(line)
                for rel in [refs.norm_path(shell.resolve(m.group(1), cwd), wd)] if m else read:
                    if rel:
                        by_file.setdefault(rel, []).append(line[m.end() :] if m else _LINE_NO.sub("", line, count=1))
            for rel, lines in by_file.items():
                add(rel, "\n".join(lines), st.n)
    ctx.cache["observed_defs"] = out
    return out


def _run_scopes(ctx: EvalContext, runs) -> set[str]:
    """Dotted forms of what the runs selected: their path targets and labels; a run that names none selects its cwd
    (``cd tests/unit && pytest``), the whole repository at the root (``""``: everything)."""
    wd = (ctx.collected.workdir or "").rstrip("/")
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    out: set[str] = set()
    for r in runs:
        if r.runner == "python-inline":
            continue
        for t in r.targets:
            out.update(_dotted(t) if ("/" in t or t.endswith(".py")) else [t.strip(".")])
        if not r.targets:
            cwd = (cwd_track.get((r.step, r.action_index)) or wd).rstrip("/")
            if wd and cwd == wd:
                out.add("")
            elif wd and cwd.startswith(wd + "/"):
                out.update(_dotted(cwd[len(wd) + 1 :]))
    return out


def _overlap(a: str, b: str) -> bool:
    """One dotted module inside or around the other, ``tests.`` prefix aside (django labels resolve under ``tests/``)."""
    fa = {a, a[6:]} if a.startswith("tests.") else {a}
    fb = {b, b[6:]} if b.startswith("tests.") else {b}
    return any(x and y and (_under(x, y) or _under(y, x)) for x in fa for y in fb)


def _anchored(entry: str, scopes: set[str], defs: dict[str, set[str]]) -> bool:
    """An id the output does not print, anchored on what the run selected and the source it showed: a file / module
    entry the runs selected (it, or a scope above or below it); a test entry whose name a base file under a run's
    selection defines (``def test_y``), in the module the entry names if it names one. Prose has no such shape."""
    mod, name = _entry_parts(entry)
    if name is None:
        # a file / module entry: path- or dotted-shaped (or a label a run named), inside or around what a run named --
        # the whole-suite scope does not vouch for a file it never named ("tests/test_ghost.py", "all tests")
        tok = re.sub(r"\s+", " ", entry[:500]).strip().strip("`*").split(" ")[0]
        shaped = bool(mod) and (re.search(r"[./]", tok) is not None or mod in scopes)
        return shaped and any(s and _overlap(mod, s) for s in scopes)
    files = defs.get(name) or set()
    files = {f for f in files if any(s == "" or _overlap(f, s) for s in scopes)}
    if not files:
        return False
    if not mod:
        return True
    return any(_overlap(mod, f) or _overlap(mod.rsplit(".", 1)[0], f) for f in files)


def _same_test(entry: str, pool: list[str]) -> bool:
    """``entry`` names a test of ``pool`` (ids as runs print them, or as an artifact lists them): the same test name in an
    overlapping module, or -- for a file / module entry -- some test of it."""
    mod, name = _entry_parts(entry)
    if mod is None and name is None:
        return False
    for other in pool:
        omod, oname = _entry_parts(other)
        if name is not None:
            if oname == name and (not mod or not omod or _overlap(mod, omod) or _overlap(mod.rsplit(".", 1)[0], omod)):
                return True
        elif omod and _overlap(mod, omod):
            return True
    return False


def _test_id(item: Item, ctx: EvalContext, entries: list[str], w, run_kind) -> Result:
    runs = [r for r in ctx.facts.runs if r.valid and refs.in_window(r.step, w) and (run_kind is None or r.kind == run_kind)]
    hay = "\n".join(h for r in runs for h in (*r.ids, *r.targets, r.command, r.segment, r.observation) if h)
    scopes = _run_scopes(ctx, runs)
    hits = [x for x in entries if any(k in hay for k in _id_keys(x)) or (runs and _anchored(x, scopes, _observed_defs(ctx)))]
    misses = [x for x in entries if x not in hits]
    return Result.ratio(item, len(hits), len(entries), f"{len(hits)}/{len(entries)} ids in valid runs" + (f"; not: {misses[:3]}" if misses else ""))


def _failed_test_id(item: Item, ctx: EvalContext, entries: list[str], w, run_kind, listed) -> Result:
    """Each id failed or errored in a valid run of the window (its output names it as failing: the same test, not just
    its class), or is listed in the ``listed_in`` selector's values (AI-DLC BT:49: a pre-existing failure is one that
    also failed in the baseline)."""
    runs = [r for r in ctx.facts.runs if r.valid and refs.in_window(r.step, w) and (run_kind is None or r.kind == run_kind) and r.failed + r.errors > 0]
    failing: list[str] = []
    unnamed: list[str] = []  # runs that failed without naming the failures (output cut by `| tail`): their ids / output, loosely
    for r in runs:
        ids = evidence.failing_ids(r.observation or "")
        failing += ids
        if not ids:
            unnamed += [h for h in (*r.ids, *r.targets, r.observation) if h]
    hay = "\n".join(unnamed)
    listed_ids: list[str] = []
    if listed is not None:
        v = refs.select(ctx, listed)
        vals = [v] if isinstance(v, str) else [str(x) for x in (v or [])]
        listed_ids = [x for val in vals for x in M.split_list(_subjects(val)) if not M.is_none(x) and not M.is_placeholder(x)]
    hits = [x for x in entries if _same_test(x, failing) or _same_test(x, listed_ids) or (hay and any(k in hay for k in _id_keys(x)))]
    misses = [x for x in entries if x not in hits]
    return Result.ratio(item, len(hits), len(entries), f"{len(hits)}/{len(entries)} ids failed in a valid run or listed" + (f"; not: {misses[:3]}" if misses else ""))


_ARROW = re.compile(r"\s*(?:->|→|=>)\s*")


def _subjects(value: str) -> str:
    """Each line cut at its first arrow: in a ``<id> -> <reasoning>`` entry (AI-DLC's Regressions and
    Pre-existing failures) the id is what is typed; the prose after the arrow, commas and all, is not."""
    return "\n".join(_ARROW.split(line, maxsplit=1)[0] for line in value.splitlines())


@register(
    "field_type",
    params={"section": True, "label": True, "type": True, "window": False, "run_kind": False, "listed_in": False, "all": False},
    availability=("sandbox_file", "trace"),
    choices={"type": FIELD_TYPES, "run_kind": RUN_KINDS},
)
def field_type(item: Item, ctx: EvalContext) -> Result:
    """``command_run``: the value is a command run in the window (with ``run_kind``: a *valid* run of that
    kind); ``repo_path``: every path exists at BASE_SHA or is in the diff; ``test_id``: every id appears in a
    valid run in the window -- in its output, ids or targets, or anchored on what it selected (a file / module /
    label it ran, a test name a base file it selected defines as ``def test_x``, path <-> dotted label) (ratio);
    ``failed_test_id``: every id failed or errored in a valid run of the window, or is listed in ``listed_in``
    (a selector) (ratio); ``test_selection``: the value is a test command that selects tests, not the whole
    suite (its shape only, no window). None values are skipped (``not_applicable``): the none policy is
    ``field_filled``'s. ``all``: the entries of every occurrence of a repeated label, not only the first."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    vs = M.field_values(body, str(p["label"]), multiline=True)
    if not p.get("all"):
        vs = vs[:1]
    if not vs:
        return Result.no(item, f"no label {p['label']!r}")
    if any(M.is_placeholder(x) for x in vs):
        return Result.no(item, "placeholder")
    vs = [x for x in vs if not M.is_none(x)]
    if not vs:
        return Result.not_applicable(item, "none value")
    v = "\n".join(vs)
    kind, w = p["type"], _window(item, ctx)
    if kind == "command_run":
        return _command_run(item, ctx, v, w, p.get("run_kind"))
    if kind == "test_selection":
        return _test_selection(item, ctx, v)
    entries = [x for x in M.split_list(_subjects(v)) if not M.is_placeholder(x) and not M.is_none(x)]
    if not entries:
        return Result.not_applicable(item, "no entries")
    if kind == "repo_path":
        return _repo_path(item, ctx, entries)
    if kind == "test_id":
        return _test_id(item, ctx, entries, w, p.get("run_kind"))
    if kind == "failed_test_id":
        return _failed_test_id(item, ctx, entries, w, p.get("run_kind"), p.get("listed_in"))
    raise ValueError(f"field_type: unknown type {kind!r}")


# --------------------------------------------------------------------------------------------
# Repeated items, cross references, template residue
# --------------------------------------------------------------------------------------------
@register("item_format", params={"pattern": True, "section": False, "min": False, "max": False, "sequence": False, "unique": False, "of_pattern": False})
def item_format(item: Item, ctx: EvalContext) -> Result:
    """Lines matching ``pattern`` in the section (or document): ``min``/``max`` count (default min 1
    unless ``max``/``of_pattern`` is given), ``sequence`` (captured ints +1 from ``start``),
    ``unique`` (captured group), ``of_pattern`` (ratio of those lines also in ``pattern``). A line
    matches ``pattern`` as written or with its ``**``/``__`` emphasis removed: bold is markup, not another
    format (``- **Step 1 [R4]**: complete`` is the template's ``- Step 1 [R4]: complete``). The
    ``of_pattern`` population is read as written (a bold legend line such as ``- **[P]**: parallel`` is
    no task line for being bold)."""
    p = _params(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    scope = _scope(text, p.get("section"))
    if scope is None:
        return Result.no(item, f"section {p.get('section')!r} absent")
    lines = M.text_lines(scope)
    rx = re.compile(str(p["pattern"]))
    hits = [m for m in (_line_search(rx, line) for line in lines) if m]
    lo = p.get("min")
    lo = int(lo) if lo is not None else (0 if p.get("max") is not None or p.get("of_pattern") else 1)
    if len(hits) < lo:
        return Result.no(item, f"{len(hits)} items < {lo}")
    if p.get("max") is not None and len(hits) > int(p["max"]):
        return Result.no(item, f"{len(hits)} items > {p['max']}")
    seq = p.get("sequence")
    if seq:
        g, start = (seq.get("group", 1), int(seq.get("start", 1))) if isinstance(seq, dict) else (1, 1)
        try:
            nums = [int(m.group(g)) for m in hits]
        except (IndexError, TypeError, ValueError):
            return Result.no(item, "sequence: non-numeric ids")
        if nums != list(range(start, start + len(nums))):
            return Result.no(item, f"sequence {nums[:8]} not +1 from {start}")
    uq = p.get("unique")
    if uq is not None and uq is not False:
        g = (1 if rx.groups else 0) if uq is True else uq
        try:
            vals = [m.group(g) for m in hits]
        except (IndexError, TypeError):
            return Result.no(item, "unique: no such group")
        dup = sorted({str(x) for x in vals if vals.count(x) > 1})
        if dup:
            return Result.no(item, f"duplicates {dup[:5]}")
    if p.get("of_pattern"):
        orx = re.compile(str(p["of_pattern"]))
        base = [line for line in lines if orx.search(line)]
        good = sum(1 for line in base if _line_search(rx, line))
        return Result.ratio(item, good, len(base), f"{good}/{len(base)} lines in format")
    return Result.ok(item, f"{len(hits)} items")


_EMPHASIS = re.compile(r"\*\*|__")


def _line_search(rx: re.Pattern, line: str) -> re.Match | None:
    """``rx`` in the line as written, else in the line without bold markup."""
    return rx.search(line) or (rx.search(_EMPHASIS.sub("", line)) if "**" in line or "__" in line else None)


def _needs_online(spec) -> bool:
    if not isinstance(spec, dict) or "fact" not in spec:
        return False
    arg = spec["fact"]
    name = (arg.get("name") or arg.get("fact")) if isinstance(arg, dict) else arg
    return name in _ONLINE_FACTS


_ARTIFACT_SELECTORS = ("field", "field_list", "section_text", "section_lines", "ids", "headings", "keyed_ids")


def _artifact_of(spec) -> tuple[str, str] | None:
    """(artifact id, state) a selector reads, or None for a fact / literal selector."""
    if not isinstance(spec, dict):
        return None
    for k in _ARTIFACT_SELECTORS:
        if isinstance(spec.get(k), dict) and spec[k].get("artifact"):
            return str(spec[k]["artifact"]), str(spec[k].get("state", "final"))
    return None


def _relation_score(L: set, R: set, rel: str, ok: bool) -> float:
    inter = len(L & R)
    if rel == "subset":
        return inter / len(L) if L else 1.0
    if rel == "superset":
        return inter / len(R) if R else 1.0
    if rel == "equal":
        return inter / len(L | R) if L | R else 1.0
    return 1.0 if ok else 0.0


@register("cross_ref", params={"left": True, "right": True, "relation": True, "normalize": False, "allow_empty": False}, availability=(), choices={"relation": RELATIONS, "normalize": NORMALIZERS})
def cross_ref(item: Item, ctx: EvalContext) -> Result:
    """``relation`` (subset | superset | equal | intersects | disjoint) holds between the two
    selectors (refs), both normalised by ``normalize``; an empty left side fails unless
    ``allow_empty``, which also reads an absent field or section of an artifact that exists as empty
    (no ``Created:`` line = nothing created). Ratio score for subset / superset / equal."""
    p = _params(item)
    sides = {}
    for side in ("left", "right"):
        val = refs.select(ctx, p[side])
        if val is None:
            if ctx.mode == "offline" and _needs_online(p[side]):
                return Result.unavailable(item, f"{side}: needs diff / base tree")
            art = _artifact_of(p[side])
            if not (p.get("allow_empty") and art is not None and ctx.artifact_text(*art) is not None):
                return Result.no(item, f"{side} side absent")
            val = set()
        if p.get("normalize") == "command":
            val = _ws_runs(val) if isinstance(val, str) else [_ws_runs(str(x)) for x in val]
        sides[side] = refs.as_set(refs.normalize(val, p.get("normalize"), ctx))
    L, R = sides["left"], sides["right"]
    if not L and not p.get("allow_empty"):
        return Result.no(item, "left side empty")
    rel = str(p["relation"])
    ok = refs.relate(L, R, rel)
    detail = "" if ok else f"{rel} fails; left-only {sorted(map(str, L - R))[:3]}, right-only {sorted(map(str, R - L))[:3]}"
    return Result(item.id, "pass" if ok else "fail", _relation_score(L, R, rel, ok), detail or rel)


@register("no_template_residue", params={"patterns": True, "section": False})
def no_template_residue(item: Item, ctx: EvalContext) -> Result:
    """None of the residue regexes occur in the section (or document), HTML comments excepted;
    score = fraction of patterns absent. A missing section fails (deleting it hides nothing)."""
    p = _params(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    scope = _scope(text, p.get("section"))
    if scope is None:
        return Result.no(item, f"section {p.get('section')!r} absent")
    scope = M.strip_comments(scope)
    pats = [p["patterns"]] if isinstance(p["patterns"], str) else list(p["patterns"])
    found = [pat for pat in pats if re.search(str(pat), scope, re.M)]
    if not pats:
        return Result.ok(item, "no patterns")
    return Result.ratio(item, len(pats) - len(found), len(pats), f"residue: {found[:3]}" if found else "no residue")


def _norm_line(s: str) -> str:
    return re.sub(r"^\[[ xX]\]\s*", "[ ] ", _norm_text(s))


@register("not_template_copy", params={"section": True, "fingerprint": True, "threshold": False})
def not_template_copy(item: Item, ctx: EvalContext) -> Result:
    """Less than ``threshold`` (0.9) of the section's content lines are template sample lines
    (emphasis, list markers, checkbox state and case ignored). An empty section fails."""
    p = _params(item)
    body, err = _body(item, ctx, p["section"])
    if err:
        return err
    lines = [x for x in (_norm_line(line) for line in M.content_lines(body)) if x]
    if not lines:
        return Result.no(item, "empty section")
    fp = p["fingerprint"]
    fps = {_norm_line(x) for x in (fp.splitlines() if isinstance(fp, str) else fp) if str(x).strip()}
    same = sum(1 for line in lines if line in fps)
    frac, thr = same / len(lines), float(p.get("threshold", 0.9))
    detail = f"{same}/{len(lines)} lines from the template"
    return Result.ok(item, detail) if frac < thr else Result.no(item, detail)


__all__ = [
    "artifact_exists",
    "cross_ref",
    "field_enum",
    "field_filled",
    "field_literal",
    "field_type",
    "frontmatter",
    "item_format",
    "label_present",
    "no_template_residue",
    "not_template_copy",
    "path_match",
    "section_present",
]
