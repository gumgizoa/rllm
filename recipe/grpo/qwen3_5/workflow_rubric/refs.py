"""The rubric's small reference language: events, windows, value selectors, predicates.

Every check parameter that points at "something in the run" uses one of these, so the generator
emits data and the engine owns the meaning.

Events -> a step (int), ``None`` (did not happen) or ``UNKNOWN`` (happened, time unknown)::

    start | end
    read:<SOURCE_ID>            first read of a document (DocRead; coverage filter via params)
    write:<ARTIFACT_ID>         the artifact's write event (its ``write_event`` policy)
    first_write:<ARTIFACT_ID>   | last_write:<ARTIFACT_ID>
    first_repo_write | last_repo_write
    last_change_write           last write to a repo path that is part of the final change
                                (``facts.change_paths``: scratch files written and removed again do not count)
    stage_start:<STAGE> | stage_end:<STAGE>
    {first: <fact query>} | {last: <fact query>}
                                the first / last record of an ``exists`` fact query, e.g. the first source edit
                                ``{first: {fact: repo_edit, created: false, paths_not_in: [..]}}`` (a file that existed
                                at BASE_SHA; for repo_edit a matching change the trace does not show -> ``UNKNOWN``)

Windows -> half-open ``[a, b)`` over steps: ``[event, event]`` or ``"stage:<STAGE>"``. An event that
did not happen makes the window empty; ``UNKNOWN`` as an end bound makes it empty too (fail safe:
nothing is "before an unknown edit"). A start bound may be a list of events, ``[[e1, e2], end]``: the
latest of those that happened (``[["stage_start:S", "last_change_write"], "end"]`` = in stage S and
after the last change). An end bound may be a list too, ``[start, [e1, e2]]``: the earliest of those that
happened (``[stage_start:S, [write:A, {first: ...}, end]]`` = before A was written and before the first
source edit, or to the end when neither happened).

Selectors -> a value (str), a list or a set, used by ``cross_ref`` and predicates::

    {field: {artifact, section, label, state?}}           str | None (the label's value)
    {field_list: {artifact, section, label, all?, state?}} list[str] (one item per line / comma; ``all``: of every
                                                           occurrence of a repeated label, not only the first)
    {section_text: {artifact, section, state?}}           str | None
    {section_lines: {artifact, section, state?}}          list[str] (non-empty content lines)
    {ids: {artifact, section?, pattern, group?, state?}}  set[str] (regex matches in the text)
    {headings: {artifact, level, pattern, group?, state?}} list[str]
    {keyed_ids: {artifact, section?, pattern, key?, ids?, item?, state?}}
                                                           set["<key>|<ID>,<ID>"]: per match, the key group (1) with the
                                                           sorted ids (``item`` regex) of the ids group (2) -- a step and its tags
    {fact: diff_paths | diff_test_paths | untracked_paths (minus build/test byproducts) | repo_write_paths | run_commands
           | valid_run_commands | run_ids | base_paths, window?, kind?, final?}
                                                           (``final: true`` on repo_write_paths: only paths in the final change;
                                                           offline ``untracked_paths`` is the replay's files created and still there)
    {literal: [..]}                                        list given in the rubric
  plus ``normalize: path | command | id | text`` on the selector dict, and ``window`` next to a
  ``fact`` selector (same as ``{fact: {name, window}}``).

Predicates -> bool, used by ``applies_when``, ``none_allowed: {if: ...}`` and ``refuted_by``::

    {exists: {fact: <F>, window?, ...filters}}    {absent: {...}}
    {counts: {fact: valid_run, window?, which: first|last|any|all, passed?: n, failed?: n,
              errors?: n, failed_or_errors?: n, collected_min?: n, failures_not_in?: <selector | [selectors]>}}
              (``failures_not_in``: the run has a failing test the selectors' values name nowhere)
    {field_is_none: {artifact, section, label, state?}}   {field_present: {...}}
    {field_matches: {artifact, section, label, pattern, state?}}
    {artifact_exists: <ARTIFACT_ID>}
    {relation: {left: <selector>, right: <selector>, rel: subset|superset|equal|intersects|disjoint}}
    {all: [..]} | {any: [..]} | {not: <predicate>}
    true | false

  Facts for exists/absent: ``valid_run`` (filters: kind, command_in: selector, targets_in: selector),
  ``run_attempt``, ``repo_edit`` (filters: paths_in / paths_not_in: selector or list of selectors, test_paths: bool, final: bool --
  the path is part of the final change, created: bool -- the path is new, not in BASE_SHA),
  ``artifact_write`` (artifact), ``doc_read`` (doc), ``exec_of`` (selector: a path whose execution
  -- as a script or a runner argument -- counts), ``command`` (pattern: regex over commands).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .context import UNKNOWN, EvalContext


class RefError(ValueError):
    """A malformed reference in the rubric (raised at validation time, not at reward time)."""


# --------------------------------------------------------------------------------------------
# Events and windows
# --------------------------------------------------------------------------------------------
def event(ctx: EvalContext, ref, min_coverage: float = 0.0):
    """Resolve an event reference to a step, ``None`` or ``UNKNOWN``."""
    f = ctx.facts
    if isinstance(ref, dict):
        return _fact_event(ctx, ref)
    if ref == "start":
        return 1
    if ref == "end":
        return f.n_steps + 1
    if ref == "first_repo_write":
        return f.first_repo_write
    if ref == "last_repo_write":
        return f.last_repo_write
    if ref == "last_change_write":
        from .facts import last_change_write  # local import: facts depends on refs

        return last_change_write(ctx)
    kind, _, arg = ref.partition(":")
    if kind == "read":
        r = f.first_read(arg, min_coverage)
        return r.step if r else None
    if kind in ("write", "first_write", "last_write"):
        return write_event(ctx, arg, {"write": None, "first_write": "first", "last_write": "last"}[kind])
    if kind in ("stage_start", "stage_end"):
        w = f.windows.get(arg)
        if not w:
            return None
        return w[0] if kind == "stage_start" else (w[1] if w[1] is not None else f.n_steps + 1)
    raise RefError(f"unknown event {ref!r}")


def write_event(ctx: EvalContext, artifact_id: str, policy: str | None = None):
    """The step of an artifact's write event under ``policy`` (default: the artifact's own).

    Only successful writes count (``ok is not False``). ``last_in_window``: the last write inside
    the window of the stage that owns the artifact, falling back to the first write if none is in
    the window. Returns None when the artifact was never written or is absent at the end.
    """
    from .facts import owning_stage  # local import: facts depends on refs

    f = ctx.facts
    art = ctx.rubric.artifacts[artifact_id]
    path = f.artifact_paths.get(artifact_id)
    if not path:
        return None
    evs = _artifact_events(ctx, art, path)
    if not evs:
        return UNKNOWN if f.final_mismatch.get(path) else None
    policy = policy or art.write_event
    if policy == "first":
        return evs[0].step
    if policy == "last":
        return evs[-1].step
    stage = owning_stage(ctx.rubric, artifact_id)
    w = f.windows.get(stage) if stage else None
    if w:
        inside = [e.step for e in evs if in_window(e.step, w)]
        if inside:
            return inside[-1]
    return evs[0].step


def _artifact_events(ctx: EvalContext, art, path: str) -> list:
    """The successful content events of an artifact, in order. An artifact with several locations (OpenSpec:
    active, then archived) is written where it was at the time: its events at every location count, except the
    arrival of a move between two of its own locations (the archive ``mv`` relocates the file, it writes nothing)."""
    f = ctx.facts
    keep = lambda e: e.ok is not False and e.op not in ("delete", "move_out")  # noqa: E731
    if len(art.locations) < 2:
        return [e for e in f.writes.get(path, []) if keep(e)]
    from .facts import location_paths  # local import: facts depends on refs

    paths = location_paths(ctx.rubric, f, ctx.collected, art)
    outs = {(p, e.step, e.action_index) for p in paths for e in f.writes.get(p, []) if e.op == "move_out"}
    evs = []
    for p in paths:
        for e in f.writes.get(p, []):
            if not keep(e):
                continue
            if e.op == "move_in" and any(q != p and (q, e.step, e.action_index) in outs for q in paths):
                continue
            evs.append(e)
    return sorted(evs, key=lambda e: (e.step, e.action_index))


def _fact_event(ctx: EvalContext, spec: dict):
    """``{first: <fact query>}`` / ``{last: <fact query>}``: the step of the first / last record :func:`matching`
    yields for the query (``{fact: repo_edit, created: false, paths_not_in: ...}``, ``{fact: valid_run, kind: test}``);
    None when there is none. For ``repo_edit``, a change the diff shows but the trace does not (and that passes
    the filters) makes the first edit ``UNKNOWN`` -- "before the first source edit" cannot be proven then."""
    if len(spec) != 1 or next(iter(spec)) not in ("first", "last") or not isinstance(next(iter(spec.values())), dict):
        raise RefError(f"event {spec!r}")
    ((which, q),) = spec.items()
    steps = sorted(r[0] if isinstance(r, tuple) else r.step for r in matching(ctx, q))
    if q.get("fact") == "repo_edit" and _unseen_edits(ctx, q):
        return UNKNOWN if which == "first" or not steps else steps[-1]
    if not steps:
        return None
    return steps[0] if which == "first" else steps[-1]


def _unseen_edits(ctx: EvalContext, q: dict) -> list[str]:
    """The repo changes the trace does not show (``Facts.unseen_repo_paths``) that a ``repo_edit`` query's filters admit."""
    from .facts import change_paths, is_new_path, is_test_path

    unseen = list(getattr(ctx.facts, "unseen_repo_paths", None) or [])
    if not unseen:
        return []
    inside = select_union(ctx, q["paths_in"]) if "paths_in" in q else None
    outside = select_union(ctx, q["paths_not_in"]) if "paths_not_in" in q else None
    out = []
    for p in unseen:
        if q.get("test_paths") is not None and is_test_path(p) != bool(q["test_paths"]):
            continue
        if q.get("final") and p not in change_paths(ctx):
            continue
        if q.get("created") is not None and is_new_path(ctx, p) != bool(q["created"]):
            continue
        if (inside is not None and p not in inside) or (outside is not None and p in outside):
            continue
        out.append(p)
    return out


def _bound(ctx: EvalContext, spec, pick):
    """One window bound: an event, or a list of events -> ``pick`` (max for a start, min for an end) of those that happened."""
    if isinstance(spec, (list, tuple)):
        got = [x for x in (event(ctx, e) for e in spec) if x is not None]
        return pick(got) if got else None
    return event(ctx, spec)


def window(ctx: EvalContext, spec) -> tuple[int, int] | None:
    """``[a, b)`` as ints, or None when empty / undefined."""
    if spec is None:
        return (1, ctx.facts.n_steps + 1)
    if isinstance(spec, str):
        if not spec.startswith("stage:"):
            raise RefError(f"window {spec!r}")
        w = ctx.facts.windows.get(spec[6:])
        if not w:
            return None
        return (w[0], w[1] if w[1] is not None else ctx.facts.n_steps + 1)
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        a = _bound(ctx, spec[0], max)  # a start list: the latest of the start events that happened
        b = _bound(ctx, spec[1], min)  # an end list: the earliest of the end events that happened (UNKNOWN first)
        if a is None or b is None or b is UNKNOWN:
            return None
        a = 1 if a is UNKNOWN else a
        return (a, b) if a < b else None
    raise RefError(f"window {spec!r}")


def in_window(step, w) -> bool:
    if w is None or step is None:
        return False
    a, b = w[0], (w[1] if w[1] is not None else 1 << 30)
    return a <= step < b


# --------------------------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------------------------
_WS = re.compile(r"\s+")
_QUOTES = re.compile(r"^['\"`]+|['\"`]+$")


_ANNOTATION = re.compile(r"\s+(?:[\[(]|[—–]\s|-\s).*$", re.S)  # "src/x.py [R1, R2]", "src/x.py (modify in place)", "src/x.py — why"


def norm_path(p: str, workdir: str | None = None) -> str:
    # an artifact's path value carries the template's own annotations (AI-DLC "[full path] [requirement tags]",
    # "[full path] (modify in place | create)"): the path is what precedes them
    p = _ANNOTATION.sub("", p.strip()[:1000]).strip().strip("`'\"").rstrip(",;.")
    if workdir:
        wd = workdir.rstrip("/") + "/"
        if p.startswith(wd):
            p = p[len(wd) :]
    for prefix in ("/app/", "/testbed/", "./"):
        if p.startswith(prefix):
            p = p[len(prefix) :]
    return p.lstrip("/") if not p.startswith("/tmp/") else p


def norm_command(c: str) -> str:
    # collapse whitespace runs first: the anchored patterns below are otherwise tried at every
    # position of a long blank run (quadratic on agent text)
    c = re.sub(r"\s+", lambda m: "\n" if "\n" in m.group() else " ", c)
    c = c.strip().strip("`")
    c = re.sub(r"\s*\([^)]*\)\s*$", "", c)  # trailing parenthetical prose
    c = re.sub(r"^cd\s+\S+\s*&&\s*", "", c)
    c = re.sub(r"\s*2>&1.*$|\s*\|\s*(?:tail|head)\b.*$", "", c)  # output plumbing
    return _canon_invocation(_WS.sub(" ", c).strip())


# Spellings of one invocation (REVIEW-REAL: 'pytest' vs 'python -m pytest', '/testbed/' paths, 'timeout N' / env
# wrappers): each segment start loses its wrappers, the interpreter its version, the runner its module form.
_SEG_START = r"(?:^|(?<=&&)|(?<=;)|(?<=\|\|))\s*"
_WRAPPERS = re.compile(
    _SEG_START + r"(?:timeout\s+(?:-[sk]\s+\S+\s+|--?[\w-]+(?:=\S+)?\s+)*\d+(?:\.\d+)?[smhd]?\s+"  # timeout [opts] N
    r"|env\s+(?:-\S+\s+)*(?:\w+=\S*\s+)*|(?:\w+=\S*\s+)+|time\s+|nice\s+(?:-n\s*-?\d+\s+)?)"  # env / K=V / time / nice
)
_INTERP = re.compile(r"(?<![\w./-])(?:/usr/bin/|/usr/local/bin/|/opt/\S+/bin/)?python3(?:\.\d+)?(?![\w.-])")
_PYTEST_MOD = re.compile(r"(?<![\w./-])(?:python\s+-m\s+(?:pytest|py\.test)|py\.test)(?![\w.-])")
_WORKDIR_PREFIX = re.compile(r"(?<![\w./-])/testbed/")
_DOT_SLASH = re.compile(r"(?<![\w./-])\./(?=[\w-])")
_PY_SCRIPT = re.compile(_SEG_START + r"python\s+(?=[\w./-]+\.py(?:\s|$))")


def _canon_invocation(c: str) -> str:
    if len(c) > 4000:
        return c
    prev = None
    while prev != c:
        prev = c
        c = _WRAPPERS.sub(" ", c).strip()
    c = _INTERP.sub("python", c)
    c = _PYTEST_MOD.sub("pytest", c)
    c = _WORKDIR_PREFIX.sub("", c)
    c = _DOT_SLASH.sub("", c)
    c = _PY_SCRIPT.sub(" ", c)
    return _WS.sub(" ", c).strip()


RELATIONS = ("subset", "superset", "equal", "intersects", "disjoint")
NORMALIZERS = ("path", "command", "id", "text")


def normalize(values, how: str | None, ctx: EvalContext):
    if how is None:
        return values
    fn = {
        "path": lambda v: norm_path(v, ctx.collected.workdir),
        "command": norm_command,
        "id": lambda v: v.strip().strip("`[]()").upper(),
        "text": lambda v: _WS.sub(" ", v).strip().lower(),
    }[how]
    if values is None:
        return None
    if isinstance(values, str):
        return fn(values)
    if isinstance(values, set):
        return {fn(v) for v in values}
    return [fn(v) for v in values]


# --------------------------------------------------------------------------------------------
# Selectors
# --------------------------------------------------------------------------------------------
def section_of(text: str | None, section) -> str | None:
    """The part of an artifact a field selector / predicate reads, addressed as the checks address it
    (``checks/artifacts._scope``): ``None`` / ``""`` / ``"*"`` = the document below its frontmatter (a field of a
    report's header block, under a title heading that names the run's own subject), a ``{heading, level, match}``
    dict = that section, else the section of that title."""
    from . import markdown as M

    if text is None:
        return None
    if section is None or (isinstance(section, str) and section.strip() in ("", "*")):
        return M.frontmatter(text).body
    if isinstance(section, dict):
        return M.section(text, section.get("heading"), section.get("level"), section.get("match", "exact_ci"))
    return M.section(text, str(section))


def select(ctx: EvalContext, spec: dict):
    from . import markdown as M  # local: markdown is a leaf module, imported lazily for clarity

    keys = [k for k in spec if k not in ("normalize", "window")] if isinstance(spec, dict) else []
    if len(keys) != 1:
        raise RefError(f"selector {spec!r}")
    how = spec.get("normalize")
    (key,) = keys
    arg = spec[key]
    val: Any
    if key in ("field", "field_list", "section_text", "section_lines", "ids", "headings", "keyed_ids"):
        text = ctx.artifact_text(arg["artifact"], arg.get("state", "final"))
        if text is None:
            return None
        if key == "field":
            val = M.field_value(section_of(text, arg["section"]), arg["label"])
        elif key == "field_list":
            body = section_of(text, arg["section"])
            if arg.get("all"):
                vs = M.field_values(body, arg["label"], multiline=True)
                val = [x for v in vs for x in M.split_list(v)] if vs else None
            else:
                v = M.field_value(body, arg["label"], multiline=True)
                val = M.split_list(v) if v is not None else None
        elif key == "section_text":
            val = M.section(text, arg["section"])
        elif key == "section_lines":
            body = M.section(text, arg["section"])
            val = M.content_lines(body) if body is not None else None
        elif key == "ids":
            scope = M.section(text, arg["section"]) if arg.get("section") else text
            if scope is None:
                return None
            g = arg.get("group", 0)
            val = {m.group(g) for m in re.finditer(arg["pattern"], scope, re.M)}
        elif key == "keyed_ids":
            scope = M.section(text, arg["section"]) if arg.get("section") else text
            if scope is None:
                return None
            val = _keyed_ids(scope, arg)
        else:  # headings
            g = arg.get("group", 0)
            val = []
            for level, title in M.headings(text):
                if level == int(arg["level"]):
                    m = re.search(arg["pattern"], title)
                    if m:
                        val.append(m.group(g))
    elif key == "fact":
        val = _fact_values(ctx, arg if isinstance(arg, dict) else {"name": arg}, spec)
    elif key == "literal":
        val = list(arg)
    else:
        raise RefError(f"selector kind {key!r}")
    return normalize(val, how, ctx)


def _keyed_ids(scope: str, arg: dict) -> set[str]:
    """``keyed_ids``: one ``"<key>|<ID>,<ID>"`` string per match of ``pattern`` -- the ``key`` group (default 1; a
    number loses its leading zeros) and the ids (``item`` regex, default ``[A-Za-z]+-?\\d+``, upper-cased, sorted,
    unique) found in the ``ids`` group (default 2). Compares a step's tags as a pair (AI-DLC Plan Execution
    ``- Step 2 [R2, R4]: complete`` against the plan's ``### Step 2 [satisfies R2, R4]``), not as one id pool."""
    kg, ig = arg.get("key", 1), arg.get("ids", 2)
    item = re.compile(str(arg.get("item") or r"[A-Za-z]+-?\d+"))
    out: set[str] = set()
    for m in re.finditer(arg["pattern"], scope, re.M):
        try:
            k, body = (m.group(kg) or "").strip(), m.group(ig) or ""
        except (IndexError, re.error):
            continue
        k = str(int(k)) if k.isdigit() else k.casefold()
        ids = sorted({x.upper() for x in item.findall(body)})
        out.add(f"{k}|{','.join(ids)}")
    return out


def _fact_values(ctx: EvalContext, arg: dict, spec: dict):
    from .facts import change_paths, is_generated, is_test_path

    f, c = ctx.facts, ctx.collected
    name = arg.get("name") or arg.get("fact")
    w = window(ctx, spec.get("window") or arg.get("window"))
    if name == "untracked_paths" and c.diff is None and c.mode == "offline":
        # offline the diff is approximated by the replay: files the run created under the code root that are still
        # there at the end (created minus deleted), build / test byproducts aside -- what `git status` would list as untracked
        from .facts import untracked_by_replay

        return untracked_by_replay(ctx)
    if name in ("diff_paths", "diff_test_paths", "untracked_paths"):
        if c.diff is None:
            return None
        # an untracked test-run byproduct (__pycache__, .pytest_cache ...) is nobody's file and not part of the change
        if name == "untracked_paths":
            return {p for p, s in c.diff.items() if s == "?" and not is_generated(p)}
        paths = {p for p, s in c.diff.items() if s != "D" and not (s == "?" and is_generated(p))}
        return {p for p in paths if is_test_path(p)} if name == "diff_test_paths" else paths
    if name == "repo_write_paths":
        paths = {e.path for e in f.repo_writes if in_window(e.step, w) and e.ok is not False}
        return paths & change_paths(ctx) if arg.get("final") else paths
    if name in ("run_commands", "valid_run_commands"):
        kind = arg.get("kind")
        return [r.command for r in f.runs if in_window(r.step, w) and (r.valid or name == "run_commands") and (kind is None or r.kind == kind)]
    if name == "run_ids":
        return {i for r in f.runs if r.valid and in_window(r.step, w) for i in r.ids}
    if name == "base_paths":
        return {p for p, ok in (c.base_present or {}).items() if ok} if c.base_present is not None else None
    raise RefError(f"fact selector {name!r}")


def select_union(ctx: EvalContext, spec) -> set:
    """The values of a selector as a set, or the union over a list of selectors (``paths_not_in: [A3 Path, A4 Path]``)."""
    if isinstance(spec, list):
        return set().union(*(as_set(select(ctx, s)) for s in spec)) if spec else set()
    return as_set(select(ctx, spec))


def as_set(v) -> set:
    if v is None:
        return set()
    if isinstance(v, str):
        return {v}
    return set(v)


def relate(left, right, rel: str) -> bool:
    L, R = as_set(left), as_set(right)
    if rel == "subset":
        return L <= R
    if rel == "superset":
        return L >= R
    if rel == "equal":
        return L == R
    if rel == "intersects":
        return bool(L & R)
    if rel == "disjoint":
        return not (L & R)
    raise RefError(f"relation {rel!r}")


# --------------------------------------------------------------------------------------------
# Predicates
# --------------------------------------------------------------------------------------------
def predicate(ctx: EvalContext, p) -> bool:
    from . import markdown as M

    if p is None or p is True:
        return True
    if p is False:
        return False
    if not isinstance(p, dict) or len(p) != 1:
        raise RefError(f"predicate {p!r}")
    ((op, arg),) = p.items()
    if op == "all":
        return all(predicate(ctx, q) for q in arg)
    if op == "any":
        return any(predicate(ctx, q) for q in arg)
    if op == "not":
        return not predicate(ctx, arg)
    if op in ("exists", "absent"):
        found = bool(list(matching(ctx, arg)))
        return found if op == "exists" else not found
    if op == "counts":
        runs = list(matching(ctx, {**arg, "fact": arg.get("fact", "valid_run")}))
        if not runs:
            return False
        which = arg.get("which", "any")
        pick = {"first": runs[:1], "last": runs[-1:], "any": runs, "all": runs}[which]
        recorded = _recorded_text(ctx, arg["failures_not_in"]) if "failures_not_in" in arg else None
        ok = [_counts_ok(r, arg) and (recorded is None or _unrecorded_failure(r, recorded)) for r in pick]
        return all(ok) if which == "all" else any(ok)
    if op in ("field_is_none", "field_present", "field_matches"):
        text = ctx.artifact_text(arg["artifact"], arg.get("state", "final"))
        if text is None:
            return False
        v = M.field_value(section_of(text, arg["section"]), arg["label"], multiline=True)
        if op == "field_present":
            return v is not None and not M.is_placeholder(v)
        if op == "field_is_none":
            return v is not None and M.is_none(v, arg.get("vocab"))
        return v is not None and re.search(arg["pattern"], v, re.I | re.M) is not None
    if op == "artifact_exists":
        return bool(ctx.facts.artifact_paths.get(arg))
    if op == "relation":
        return relate(select(ctx, arg["left"]), select(ctx, arg["right"]), arg["rel"])
    raise RefError(f"predicate op {op!r}")


def _counts_ok(r, arg: dict) -> bool:
    for k in ("passed", "failed", "errors"):
        if k in arg and getattr(r, k) != int(arg[k]):
            return False
    if "failed_or_errors" in arg and (r.failed + r.errors) != int(arg["failed_or_errors"]):
        return False
    if "collected_min" in arg and max(r.collected, r.passed + r.failed + r.errors) < int(arg["collected_min"]):
        return False
    return True


def _recorded_text(ctx: EvalContext, spec) -> list[str]:
    """The values of one selector or a list of them (what the artifacts record about failures); absent ones left out."""
    specs = spec if isinstance(spec, list) else [spec]
    parts: list[str] = []
    for s in specs:
        v = select(ctx, s)
        if v is None:
            continue
        parts += [v] if isinstance(v, str) else [str(x) for x in v]
    return [p[:20_000] for p in parts[:500]]


def id_forms(test_id: str) -> set[str]:
    """How an artifact may name a failing test: the id, its file / module part, its test name, django's ``name (module.Class)``."""
    out = {test_id}
    if "::" in test_id:
        parts = test_id.split("::")
        out |= {parts[0] + "::" + parts[-1], parts[-1].split("[")[0]}
    elif "." in test_id:
        mod, _, name = test_id.rpartition(".")
        out |= {name, f"{name} ({mod})"}
    return {x for x in out if len(x) >= 4}


def _unrecorded_failure(r, recorded: list[str]) -> bool:
    """The run failed and some failing test is named nowhere in ``recorded``; when the output names no failing test,
    a failure counts as unrecorded only if the artifacts record no failure at all (every value none or empty)."""
    from . import markdown as M
    from .evidence import failing_ids

    if r.failed + r.errors <= 0:
        return False
    ids = failing_ids(r.observation or "")
    if not ids:
        return all(not v.strip() or M.is_none(v) or M.is_placeholder(v) for v in recorded)
    hay = "\n".join(recorded)
    return any(not any(form in hay for form in id_forms(i)) for i in ids)


def matching(ctx: EvalContext, arg: dict) -> Iterable:
    """The fact records a predicate's ``exists``/``absent``/``counts`` ranges over."""
    from .facts import change_paths, executed_paths, is_new_path, is_test_path

    f = ctx.facts
    name = arg["fact"]
    w = window(ctx, arg.get("window"))
    if name in ("valid_run", "run_attempt"):
        cmds = as_set(normalize(select(ctx, arg["command_in"]), "command", ctx)) if "command_in" in arg else None
        tgts = as_set(select(ctx, arg["targets_in"])) if "targets_in" in arg else None
        for r in f.runs:
            if not in_window(r.step, w) or (name == "valid_run" and not r.valid):
                continue
            if arg.get("kind") and r.kind != arg["kind"]:
                continue
            if cmds is not None and norm_command(r.command) not in cmds and norm_command(r.segment) not in cmds:
                continue
            if tgts is not None and not (set(r.targets) & tgts):
                continue
            yield r
    elif name == "repo_edit":
        inside = select_union(ctx, arg["paths_in"]) if "paths_in" in arg else None
        outside = select_union(ctx, arg["paths_not_in"]) if "paths_not_in" in arg else None
        for e in f.repo_writes:
            if e.ok is False or not in_window(e.step, w):
                continue
            if arg.get("test_paths") is not None and is_test_path(e.path) != bool(arg["test_paths"]):
                continue
            if arg.get("final") and e.path not in change_paths(ctx):
                continue
            if arg.get("created") is not None and is_new_path(ctx, e.path) != bool(arg["created"]):
                continue
            if inside is not None and e.path not in inside:
                continue
            if outside is not None and e.path in outside:
                continue
            yield e
    elif name == "artifact_write":
        path = f.artifact_paths.get(arg["artifact"])
        for e in f.writes.get(path, []) if path else []:
            if e.ok is not False and in_window(e.step, w):
                yield e
    elif name == "doc_read":
        for r in f.doc_reads.get(arg["doc"], []):
            if in_window(r.step, w) and r.coverage >= float(arg.get("min_coverage", 0.0)):
                yield r
    elif name == "exec_of":
        targets = as_set(normalize(select(ctx, arg["selector"]), "path", ctx))
        for step, path in executed_paths(ctx):
            if in_window(step, w) and path in targets:
                yield (step, path)
    elif name == "command":
        rx = re.compile(arg["pattern"])
        for c in f.commands:
            if in_window(c.step, w) and rx.search(c.command):
                yield c
    else:
        raise RefError(f"fact {name!r}")
