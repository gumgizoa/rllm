"""Run + Collected + rubric -> :class:`~.context.Facts`, the only things checks look at.

Checks never parse commands or re-read the sandbox; they ask the facts. :func:`build` derives them
once per episode, in one pass over the trace with one cwd per run (the agent's terminal is a
persistent shell, starting in the task's workdir):

* writes, replayed (:mod:`.replay`), and the repo writes among them (repo-relative, ``.git`` and
  artifact locations excluded). A repo edit the diff shows but no write event touched makes
  ``first_repo_write`` :data:`~.context.UNKNOWN`: something the trace does not show changed the
  repository, so "before the first edit" can no longer be proven;
* which directory a rubric var (a feature dir, a change name) binds to, and where each artifact
  is found -- the first location that holds it; an ``exclusive`` artifact found at several
  locations is recorded (``Facts.location_counts``) so ``artifact_exists`` can fail it;
* ``final_mismatch``: the sandbox file is not what the trace wrote (also written by something the
  trace does not show), which voids its write events for ordering and write discipline;
* document reads (:mod:`.docread`), runner invocations (:mod:`.evidence`), every shell command;
* stage windows, by the rubric's ``scoring.windows``: ``reads`` (default) -- stage k runs from the
  first read of its document to the first read of the next stage's; ``writes`` -- from the write of
  the previous stage's ``order_artifact`` to its own (+1). A bound the run lacks falls back to the
  other mode, else to the start / the end of the run. With ``scoring.next_read: after_start`` a stage
  that ends at the next stage's document takes that document's first read after the stage began: a
  document read ahead does not close the window before it opened (openspec_ff's apply has no artifact).

Beyond the frozen ``Facts`` fields, ``build`` sets ``location_counts`` (artifact id -> how many of
its locations hold it; read by ``checks/artifacts.py``) and private side tables for
``checks/actions.py``: ``_doc_hits`` / ``_doc_fps`` (which fingerprints each step showed),
``_action_docs`` (docs each call read), ``_unseen_repo_paths``, ``_created``, ``_cwd_track``.
Every reader falls back when they are absent (a ``Facts`` built by hand in a test).
"""

from __future__ import annotations

import fnmatch
import functools
import logging
import os
import posixpath
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from . import docread, evidence
from .context import UNKNOWN, Collected, CommandFact, EvalContext, Facts, WriteEvent
from .refs import norm_path
from .replay import Replay, content_at, replay
from .schema import Artifact, Rubric
from .trace import shell
from .trace.model import Run

logger = logging.getLogger(__name__)

WRITE_OPS = frozenset({"create", "overwrite", "append", "edit", "unknown", "move_in"})  # events that put content at a path
DATE_RX = r"\d{4}-\d{2}-\d{2}"
_NAME = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PYTHON = re.compile(r"^(?:python|pypy)[0-9.]*$")
_SCRIPT_VERBS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "node", "deno", "ts-node", "ruby", "perl", "php", "Rscript", "julia", "lua", "source", "."})

_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests|__tests__|spec)/|^/?(?:test|testing)/|(?:^|/)(?:test|testing)/(?!.*\.py$)"
    r"|(?:^|/)test_[^/]*\.py$|(?:^|/)[^/]*_tests?\.py$|(?:^|/)conftest\.py$"
    r"|_test\.go$|\.(?:test|spec)\.[cm]?[jt]sx?$|_(?:spec|test)\.rb$|(?:^|/)test_[^/]*\.(?:rb|php)$"
    r"|(?:^|/)[^/]*Tests?\.(?:java|kt|cs|scala|php)$|_test\.(?:rs|cc|cpp|c|exs?)$"
)
# Untracked paths that running or building a project leaves behind: not an edit the trace hides.
_GENERATED = re.compile(
    r"(?:^|/)(?:__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.hypothesis|\.benchmarks|\.tox|\.nox|\.eggs|\.venv|venv|node_modules|htmlcov|\.coverage[^/]*)(?:/|$)"
    r"|^(?:build|dist)/|\.egg-info(?:/|$)|\.py[cod]$|\.so$|\.o$|\.log$|\.sqlite3?$|\.db$"
)
_CODE_EXT = re.compile(r"\.(?:py|pyx|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|scala|c|cc|cpp|h|hpp|cs|rb|php|swift|m|sh|pl|lua|r|jl|ex|exs|toml|cfg|ini|ya?ml|json)$", re.I)


# ============================================================================================
# Helpers refs.py and the checks import
# ============================================================================================
def owning_stage(rubric: Rubric, artifact_id: str) -> str | None:
    """The first stage that lists ``artifact_id`` among its artifacts."""
    return next((st.id for st in rubric.stages if artifact_id in st.artifacts), None)


def is_test_path(path: str) -> bool:
    """A test file or a file under a test directory (``tests/``, ``__tests__/``, ``test_*.py``, ``*_test.go``, ``*.spec.ts`` ...).

    A singular ``test/`` or ``testing/`` directory counts at the repository root (pytest's ``testing/``)
    and for non-Python trees (``src/test/java``); inside a Python package it is the package's own test
    *framework* (``django/test/testcases.py``, ``sympy/testing/runtests.py``): library code, a test only
    when the file itself is named like one."""
    return bool(path) and _TEST_PATH.search(path) is not None


def is_generated(path: str) -> bool:
    """A byproduct of running or building the project (``__pycache__/``, ``*.pyc``, ``.pytest_cache/``, ``*.egg-info`` ...), not a file anyone wrote."""
    return bool(path) and _GENERATED.search(path) is not None


def change_paths(ctx: EvalContext) -> set[str]:
    """Repo-relative paths that are part of the run's final change.

    Online: the diff against BASE_SHA (deletions included, run byproducts aside). Offline: every path
    the trace wrote whose last event leaves content there, plus deleted code files the agent did not
    create -- a removed base file is a change; a scratch file written and removed again is not
    (AI-DLC BT:102 asks for exactly that cleanup, so listing or reporting it cannot be required), and
    neither is the removal of a data file a test run left behind (``rm *.fits``), which the trace never
    showed being written.
    """
    cached = ctx.cache.get("change_paths")
    if cached is not None:
        return cached
    c, f = ctx.collected, ctx.facts
    if c.diff is not None:
        out = {p for p, s in c.diff.items() if not (s == "?" and is_generated(p))}
    else:
        last: dict[str, str] = {}
        for e in f.repo_writes:
            if e.ok is not False:
                last[e.path] = e.op
        out = {p for p, op in last.items() if not is_generated(p) and (op not in ("delete", "move_out") or (not is_new_path(ctx, p) and _CODE_EXT.search(p) is not None))}
    ctx.cache["change_paths"] = out
    return out


def untracked_by_replay(ctx: EvalContext) -> set[str]:
    """Offline stand-in for ``git ls-files --others``: repo-relative paths the run created (:func:`is_new_path`) whose last
    event leaves content there (created minus deleted), run byproducts (``__pycache__``, ``*.pyc`` ...) aside."""
    cached = ctx.cache.get("untracked_by_replay")
    if cached is not None:
        return cached
    last: dict[str, str] = {}
    for e in ctx.facts.repo_writes:
        if e.ok is not False:
            last[e.path] = e.op
    out = {p for p, op in last.items() if op not in ("delete", "move_out") and not is_generated(p) and is_new_path(ctx, p)}
    ctx.cache["untracked_by_replay"] = out
    return out


def is_new_path(ctx: EvalContext, rel: str) -> bool:
    """The repo-relative path did not exist at BASE_SHA: online the diff says added / untracked (modified / deleted:
    it existed); a path the diff does not list -- unchanged, or created and removed again -- is answered by the base
    tree when it was asked, else by the replay (the agent created it: its first write made it and nothing showed it before)."""
    c = ctx.collected
    if c.diff is not None and rel in c.diff:
        return c.diff[rel] in ("A", "?")
    if c.base_present is not None and rel in c.base_present:
        return not c.base_present[rel]
    wd = (c.workdir or "").rstrip("/") + "/"
    return (wd + rel) in (getattr(ctx.facts, "_created", None) or {})


def last_change_write(ctx: EvalContext):
    """Step of the last repo write to a non-test code or config file in the final change (:func:`change_paths`):
    the last change to the code the tests verify (a test file the agent wrote or edited is judged by the
    test-file items, and does not make an earlier run stale, nor does a README / requirements text; a git
    stash / checkout restoring content is no edit);
    ``UNKNOWN`` when the diff shows changes the trace does not and no known write is one; None without
    any change."""
    keep = {p for p in change_paths(ctx) if not is_test_path(p) and _CODE_EXT.search(p) is not None}
    # an "unknown" write is git putting content back (stash / checkout / apply), not an edit the agent authored
    steps = [e.step for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and e.path in keep]
    if steps:
        return max(steps)
    return UNKNOWN if ctx.facts.unseen_repo_paths else None


def executed_paths(ctx: EvalContext) -> list[tuple[int, str]]:
    """(step, normalised path) of every script the run executed -- ``python x.py``, ``bash x.sh``,
    ``./x``, ``node x.js``, ``source x`` -- and every runner target; paths as ``refs.norm_path`` gives them."""
    cached = ctx.cache.get("executed_paths")
    if cached is not None:
        return cached
    wd = ctx.collected.workdir
    out: list[tuple[int, str]] = []
    for c in ctx.facts.commands:
        for seg in shell.flat(shell.split(c.command, c.cwd)[0]):
            out.extend((c.step, norm_path(p, wd)) for p in _executed(seg))
    for r in ctx.facts.runs:
        out.extend((r.step, t) for t in r.targets)
    out = sorted(dict.fromkeys(out), key=lambda x: x[0])
    ctx.cache["executed_paths"] = out
    return out


def _executed(seg: shell.Segment) -> list[str]:
    words = seg.cmd_words
    if not words or seg.verb is None:
        return []
    head, verb = words[0].text, seg.verb

    def path(t: str) -> list[str]:
        if not t or t.startswith("-") or (seg.cwd is None and not t.startswith(("/", "~"))):
            return []
        return [shell.resolve(t, seg.cwd)]

    if _PYTHON.match(verb):
        mode, val, _ = evidence.py_args(words[1:])
        return path(val or "") if mode == "script" else []
    if verb in _SCRIPT_VERBS:
        ops = [w.text for w in words[1:] if not w.text.startswith("-")]
        if verb in ("bash", "sh", "zsh", "dash", "ksh") and any(w.text.startswith("-") and "c" in w.text[1:] for w in words[1:2]):
            return []
        return path(ops[0]) if ops else []
    if "/" in head:
        return path(head)
    return []


def artifact_text(ctx: EvalContext, artifact_id: str, state: str = "final") -> str | None:
    """The artifact's raw text: ``final`` from the sandbox, ``stage_end`` replayed at the end of its stage window.

    stage_end: when the trace explains the final file (no ``final_mismatch``) and nothing wrote
    it after the window (an open window ends with the run), the final text is the stage-end text;
    otherwise the replayed content at the window's last step, at whichever of the artifact's
    locations held it then (an OpenSpec change is archived later). None when absent, a directory,
    or not replayable -- a file only something outside the trace wrote has no stage-end text.
    """
    key = ("artifact_text", artifact_id, state)
    if key in ctx.cache:
        return ctx.cache[key]
    val = _artifact_text(ctx, artifact_id, state)
    ctx.cache[key] = val
    return val


def _artifact_text(ctx: EvalContext, aid: str, state: str) -> str | None:
    f, c = ctx.facts, ctx.collected
    art = ctx.rubric.artifacts.get(aid)
    if art is None or art.kind == "dir":
        return None
    path = f.artifact_paths.get(aid)
    if state != "stage_end":
        return c.files.get(path) if path else None
    stage = owning_stage(ctx.rubric, aid)
    w = f.windows.get(stage) if stage else None
    if not w:
        return None
    end = w[1] if w[1] is not None else f.n_steps + 1
    if path and path in c.files and not f.final_mismatch.get(path) and f.writes.get(path) and all(e.step < end for e in f.writes[path]):
        return c.files[path]
    best: tuple[int, str] | None = None
    for p in location_paths(ctx.rubric, f, c, art):
        evs = [e for e in f.writes.get(p, []) if e.step < end]
        if not evs:
            continue
        text = content_at(evs, end - 1)
        if text is not None and (best is None or evs[-1].step > best[0]):
            best = (evs[-1].step, text)
    return best[1] if best else None


# ============================================================================================
# Templates: roots, vars, locations
# ============================================================================================
def roots_of(rubric: Rubric, workdir: str | None) -> dict[str, str | None]:
    """Root name -> absolute directory (``code`` defaults to the workdir); None when it needs an unknown value."""
    raw = dict(rubric.roots)
    raw.setdefault("code", "{WORKDIR}")
    out: dict[str, str | None] = {}

    def expand(name: str, depth: int) -> str | None:
        if name in out:
            return out[name]
        v = raw.get(name)
        if v is None or depth > 8:
            return None
        missing = False

        def sub(m: re.Match) -> str:
            nonlocal missing
            key = m.group(1)
            if key in ("WORKDIR", "workdir"):
                if workdir:
                    return workdir
            elif key in raw and key != name:
                r = expand(key, depth + 1)
                if r is not None:
                    return r
            missing = True
            return m.group(0)

        s = _NAME.sub(sub, v)
        res = None if missing or not s.startswith("/") else posixpath.normpath(s)
        out[name] = res
        return res

    for name in raw:
        expand(name, 0)
    return out


def expand(template: str, roots: Mapping[str, str | None], workdir: str | None, bindings: Mapping[str, str | None]) -> tuple[str, list[str]]:
    """``template`` with roots, ``WORKDIR`` and bound vars substituted; the names left unresolved."""
    left: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        v = roots.get(key) if key in roots else (workdir if key in ("WORKDIR", "workdir") else bindings.get(key))
        if v:
            return v
        left.append(key)
        return m.group(0)

    s = _NAME.sub(sub, template)
    return (posixpath.normpath(s) if s else s), left


def template_regex(expanded: str, capture: str | None = None) -> re.Pattern | None:
    """A regex for an expanded template: ``{DATE}`` -> a date, ``{capture}`` -> group ``cap``, other names -> one component."""
    parts: list[str] = []
    pos = 0
    captured = False
    for m in _NAME.finditer(expanded):
        parts.append(re.escape(expanded[pos : m.start()]))
        key = m.group(1)
        if key == capture:
            parts.append(r"(?P=cap)" if captured else r"(?P<cap>[^/]+)")
            captured = True
        elif key == "DATE":
            parts.append(DATE_RX)
        else:
            parts.append(r"[^/]+")
        pos = m.end()
    parts.append(re.escape(expanded[pos:]))
    try:
        return re.compile("".join(parts).rstrip("/"))
    except re.error:
        return None


def _parents(paths) -> set[str]:
    out: set[str] = set()
    for p in paths:
        d = posixpath.dirname(p)
        while d and d != "/" and d not in out:
            out.add(d)
            d = posixpath.dirname(d)
    return out


def _pool(art: Artifact, c: Collected) -> list[str]:
    return sorted(set(c.dirs) | _parents(c.files)) if art.kind == "dir" else sorted(c.files)


def _last_write(writes: Mapping[str, list[WriteEvent]], paths) -> int:
    return max((e.step for p in paths for e in writes.get(p, []) if e.ok is not False), default=0)


def _locate(art: Artifact, loc: str, roots, c: Collected, bindings, var_names, writes) -> str | None:
    s, left = expand(loc, roots, c.workdir, bindings)
    if not s.startswith("/") or any(n in var_names or n in roots or n in ("WORKDIR", "workdir") for n in left):
        return None
    pool = _pool(art, c)
    if not left:
        return s if s in set(pool) else None
    rx = template_regex(s)
    hits = [p for p in pool if rx is not None and rx.fullmatch(p)]
    if not hits:
        return None
    return sorted(hits, key=lambda p: (-_last_write(writes, [p]), p))[0]


def location_paths(rubric: Rubric, f: Facts, c: Collected, art: Artifact) -> list[str]:
    """Every path the artifact's locations name, final path first: literal ones, and pattern ones
    matched against what the trace wrote and the sandbox holds (for replaying moved artifacts)."""
    roots = roots_of(rubric, c.workdir)
    final = f.artifact_paths.get(art.id)
    out: list[str] = [final] if final else []
    known = set(f.writes) | set(c.files)
    for loc in art.locations:
        s, left = expand(loc, roots, c.workdir, f.var_bindings)
        if not s.startswith("/"):
            continue
        if not left:
            out.append(s)
            continue
        rx = template_regex(s)
        if rx is not None:
            out.extend(sorted(p for p in known if rx.fullmatch(p)))
    return list(dict.fromkeys(out))


# ============================================================================================
# build
# ============================================================================================
def build(rubric: Rubric, run: Run, collected: Collected, *, docs: Mapping[str, str] | None = None) -> Facts:
    """Every fact the rubric's checks may read, for one run. ``docs``: source id -> text, overriding the package files."""
    workdir = _normdir(collected.workdir)
    f = Facts(n_steps=max([len(run.steps)] + [s.n for s in run.steps]))
    cache: dict[tuple[str, str | None], tuple] = {}

    def split(command: str, cwd: str | None):
        key = (command, cwd)
        if key not in cache:
            cache[key] = shell.split(command, cwd)
        return cache[key]

    start = workdir or "/"
    cwd_track, f.commands = _track(run, start, split)
    rep = replay(run, start)
    f.writes = rep.writes
    roots = roots_of(rubric, workdir)
    _bind_vars(f, rubric, collected, roots, rep)
    _resolve_artifacts(f, rubric, collected, roots, rep)
    _final_mismatch(f, collected, rep)
    _repo_writes(f, rubric, collected, roots, workdir)
    _doc_reads(f, rubric, run, cwd_track, split, docs)
    created = _created(run, rep, cwd_track, split)
    f.runs = evidence.runs_from(run, cwd_track, collected.base_present, created, workdir=workdir, writes=rep.writes, split=split)
    _windows(f, rubric, collected)
    f._created = created  # type: ignore[attr-defined]
    f._cwd_track = cwd_track  # type: ignore[attr-defined]
    return f


def _normdir(p: str | None) -> str | None:
    if not p or not p.startswith("/"):
        return None
    return posixpath.normpath(p)


def _track(run: Run, start: str, split) -> tuple[dict[tuple[int, int], str | None], list[CommandFact]]:
    """cwd before every action (the terminal persists across calls), and every shell command."""
    cwd: str | None = start
    track: dict[tuple[int, int], str | None] = {}
    cmds: list[CommandFact] = []
    for step in run.steps:
        for idx, a in enumerate(step.actions):
            track[(step.n, idx)] = cwd
            if a.kind == "shell" and a.command:
                segs, after = split(a.command, cwd)
                cmds.append(CommandFact(step.n, idx, a.command, [s.text for s in shell.flat(segs)], cwd, a.observation or ""))
                cwd = after
    return track, cmds


def _var_ok(name: str, rx: re.Pattern | None, exclude: list[str]) -> bool:
    if not name or rx is None or not rx.fullmatch(name):
        return False
    return not any(name == e or fnmatch.fnmatchcase(name, e) for e in exclude)


def _bind_vars(f: Facts, rubric: Rubric, c: Collected, roots, rep: Replay) -> None:
    files, dirs = list(c.files), set(c.dirs) | _parents(c.files)
    for name, var in rubric.vars.items():
        pattern = DATE_RX if name == "DATE" and var.regex in ("", ".+") else var.regex
        try:
            rx = re.compile(pattern)
        except re.error:
            f.notes.append(f"var {name}: bad regex {pattern!r}")
            f.var_bindings[name] = None
            continue
        cands: set[str] = set()
        under, left = expand(var.under, roots, c.workdir, f.var_bindings)
        under_ok = under.startswith("/") and not left
        if under_ok:
            pre = under.rstrip("/") + "/"
            for p in [*files, *dirs]:
                if p.startswith(pre):
                    head, _, rest = p[len(pre) :].partition("/")
                    if rest or p in dirs:
                        cands.add(head)
        for art in rubric.artifacts.values():
            for loc in art.locations:
                if "{" + name + "}" not in loc:
                    continue
                s, _ = expand(loc, roots, c.workdir, {k: v for k, v in f.var_bindings.items() if k != name})
                rx2 = template_regex(s, capture=name) if s.startswith("/") else None
                for p in _pool(art, c) if rx2 is not None else []:
                    m = rx2.fullmatch(p)
                    if m:
                        cands.add(m.group("cap"))
        cands = {x for x in cands if _var_ok(x, rx, var.exclude)}
        if not cands:
            f.var_bindings[name] = None
            continue
        if len(cands) == 1:
            f.var_bindings[name] = cands.pop()
            continue

        ranked = _rank(cands, name, rubric, c, roots, f.var_bindings, rep.writes, under if under_ok else None)
        f.var_bindings[name] = ranked[0]
        if var.bind == "single":
            f.var_ambiguous.add(name)
            f.notes.append(f"var {name}: {len(cands)} candidates {ranked[:5]}, bound {ranked[0]!r}")


def _rank(cands: set[str], name: str, rubric: Rubric, c: Collected, roots, bindings, writes, under: str | None) -> list[str]:
    """Candidates for var ``name``, best first: most artifacts found under it, then most recently written, then by name."""

    def held(value: str) -> int:
        b = {**bindings, name: value}
        free = set(rubric.vars) - {name} - set(b)
        return sum(1 for art in rubric.artifacts.values() if any(_locate(art, loc, roots, c, b, free, writes) for loc in art.locations if "{" + name + "}" in loc))

    def recent(value: str) -> int:
        if under is None:
            return 0
        pre = under.rstrip("/") + "/" + value
        return _last_write(writes, [p for p in writes if p == pre or p.startswith(pre + "/")])

    return sorted(cands, key=lambda v: (-held(v), -recent(v), v))


def _resolve_artifacts(f: Facts, rubric: Rubric, c: Collected, roots, rep: Replay) -> None:
    var_names = set(rubric.vars)
    counts: dict[str, int] = {}
    for aid, art in rubric.artifacts.items():
        found = [(i, p) for i, loc in enumerate(art.locations) if (p := _locate(art, loc, roots, c, f.var_bindings, var_names, rep.writes))]
        f.artifact_paths[aid] = found[0][1] if found else None
        f.artifact_location[aid] = found[0][0] if found else None
        counts[aid] = len({p for _, p in found})
        if art.exclusive and counts[aid] > 1:
            f.notes.append(f"artifact {aid}: found at {counts[aid]} locations {[p for _, p in found]}")
    f.location_counts = counts


def _norm_text(s: str) -> str:
    return "\n".join(ln.rstrip() for ln in s.replace("\r\n", "\n").split("\n")).rstrip()


def _final_mismatch(f: Facts, c: Collected, rep: Replay) -> None:
    for path, text in c.files.items():
        evs = rep.writes.get(path)
        if not evs or path not in rep.final:
            f.final_mismatch[path] = True
            continue
        replayed = rep.final[path]
        if replayed is None:
            f.final_mismatch[path] = False
        elif path in c.truncated:
            cut = _norm_text(text)
            f.final_mismatch[path] = not _norm_text(replayed).startswith(cut[: max(0, len(cut) - 4)])  # the cut may split a character
        else:
            f.final_mismatch[path] = _norm_text(replayed) != _norm_text(text)


def _artifact_regexes(rubric: Rubric, roots, workdir: str | None) -> list[tuple[re.Pattern, bool]]:
    """(regex, is a directory artifact) for every artifact location (vars as one component)."""
    out = []
    for art in rubric.artifacts.values():
        for loc in art.locations:
            s, _ = expand(loc, roots, workdir, {})
            rx = template_regex(s) if s.startswith("/") else None
            if rx is not None:
                out.append((rx, art.kind == "dir"))
    return out


def _status_paths(pre_status: str | None) -> list[str]:
    """Paths in a ``git status --porcelain=v1 -z`` record (renames: both sides)."""
    out, toks, i = [], (pre_status or "").split("\x00"), 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if len(t) < 4:
            continue
        out.append(t[3:])
        if "R" in t[:2] or "C" in t[:2]:
            if i < len(toks) and toks[i]:
                out.append(toks[i])
            i += 1
    return out


def _counts_as_edit(rel: str, status: str) -> bool:
    if rel == ".git" or rel.startswith(".git/"):
        return False
    if status != "?":
        return True
    return _CODE_EXT.search(rel) is not None and _GENERATED.search(rel) is None


def _repo_writes(f: Facts, rubric: Rubric, c: Collected, roots, workdir: str | None) -> None:
    if not workdir:
        if c.diff:
            f.notes.append("no workdir: repo writes unknown")
        return
    pre = workdir.rstrip("/") + "/"
    arts = _artifact_regexes(rubric, roots, workdir)
    resolved = set(filter(None, f.artifact_paths.values()))

    def is_artifact(p: str) -> bool:
        if p in resolved:
            return True
        for rx, is_dir in arts:
            m = rx.fullmatch(p) or (rx.match(p) if is_dir else None)
            if m and (m.end() == len(p) or p[m.end()] == "/"):
                return True
        return False

    repo: list[WriteEvent] = []
    for path, evs in f.writes.items():
        if not path.startswith(pre):
            continue
        rel = path[len(pre) :]
        if rel == ".git" or rel.startswith(".git/") or is_artifact(path):
            continue
        repo.extend(replace(e, path=rel) for e in evs)
    repo.sort(key=lambda e: (e.step, e.action_index))
    f.repo_writes = repo
    ok = [e for e in repo if e.ok is not False]
    for e in ok:
        steps = f.edits_by_path.setdefault(e.path, [])
        if not steps or steps[-1] != e.step:
            steps.append(e.step)
    f.first_repo_write = ok[0].step if ok else None
    f.last_repo_write = ok[-1].step if ok else None
    unseen: list[str] = []
    if c.diff is not None:
        touched = {e.path for e in ok}
        dirty_before = set(_status_paths(c.pre_status))  # setup leftovers, not the agent's edits
        unseen = sorted(p for p, st in c.diff.items() if p not in touched and p not in dirty_before and _counts_as_edit(p, st) and not is_artifact(pre + p))
        if unseen:
            f.first_repo_write = UNKNOWN
            if not ok:
                f.last_repo_write = UNKNOWN
            f.notes.append(f"repo changed outside the trace: {unseen[:5]}" + (f" (+{len(unseen) - 5})" if len(unseen) > 5 else ""))
    f.unseen_repo_paths = unseen
    f._unseen_repo_paths = unseen  # type: ignore[attr-defined]  -- legacy name


# -- documents ---------------------------------------------------------------------------------
@functools.lru_cache(maxsize=256)
def _read_file(path: str, mtime_ns: int, size: int) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _source_text(rubric: Rubric, rel: str) -> str | None:
    if rubric.path is None or not rel:
        return None
    p = (Path(rubric.path).parent.parent / rel).resolve()
    try:
        st = os.stat(p)
    except OSError:
        return None
    return _read_file(str(p), st.st_mtime_ns, st.st_size)


@functools.lru_cache(maxsize=64)
def _fingerprints(items: tuple[tuple[str, str | None], ...], extra: tuple[str | None, ...]) -> dict[str, list[str]]:
    texts = dict(items)
    return {sid: docread.fingerprints(t, docread.K, [o for s2, o in items if s2 != sid] + list(extra)) for sid, t in texts.items()}


def _doc_reads(f: Facts, rubric: Rubric, run: Run, cwd_track, split, override: Mapping[str, str] | None) -> None:
    docs: dict[str, tuple[str, str | None]] = {}
    others: list[str | None] = []
    for s in rubric.sources:
        text = override[s.id] if override and s.id in override else _source_text(rubric, s.path)
        if s.container_path:
            docs[s.id] = (s.container_path, text)
            if text is None:
                f.notes.append(f"doc {s.id}: text unavailable; reads by command only")
        else:
            others.append(text)
    if not docs:
        return
    fps = _fingerprints(tuple((sid, t) for sid, (_, t) in docs.items()), tuple(others))
    stage_docs = {st.doc for st in rubric.stages if st.doc}
    sc = docread.scan(run, docs, cwd_track, stage_docs=stage_docs, split=split, fps=fps)
    f.doc_reads = sc.reads
    f.multi_read_steps = sc.multi
    f._doc_hits = sc.hits  # type: ignore[attr-defined]
    f._doc_fps = sc.fps  # type: ignore[attr-defined]
    f._action_docs = sc.action_docs  # type: ignore[attr-defined]


# -- what the agent created ------------------------------------------------------------------
_NOFILE = re.compile(r"No such file or directory|does not exist|cannot access|can't open file|Invalid `path`", re.I)


def _created(run: Run, rep: Replay, cwd_track, split) -> dict[str, int]:
    """Absolute path -> step the agent created it: its first successful write made it (create, a
    move/copy in, an append to a fresh /tmp path) and nothing showed it existing before."""
    cand: dict[str, int] = {}
    for path, evs in rep.writes.items():
        first = next((e for e in evs if e.ok is not False), None)
        if first is None:
            continue
        if first.op in ("create", "move_in") or (first.op == "append" and path.startswith("/tmp/")):
            cand[path] = first.step
    if not cand:
        return cand
    names = {posixpath.basename(p) for p in cand}
    known = sorted(cand)
    for step in run.steps:
        for idx, a in enumerate(step.actions):
            if a.kind == "view" and a.path:
                p = shell.resolve(a.path, cwd_track.get((step.n, idx)))
                if p in cand and step.n < cand[p] and not _NOFILE.search(a.observation or ""):
                    del cand[p]
            elif a.kind == "shell" and a.command and any(n in a.command for n in names):
                cwd = cwd_track.get((step.n, idx))
                used = [p for seg in shell.flat(split(a.command, cwd)[0]) for p in shell.read_targets(seg, known)]
                used += [op.src for op in shell.write_ops(a.command, cwd) if op.op in ("copy", "move") and op.src]  # `cp f backup` shows f existed
                for p in used:
                    if p in cand and step.n < cand[p] and not _missing_in(a.observation or "", p):
                        del cand[p]
    return cand


def _missing_in(observation: str, path: str) -> bool:
    base = posixpath.basename(path)
    return any(_NOFILE.search(ln) and base in ln for ln in observation.splitlines())


# -- windows -------------------------------------------------------------------------------------
def _first_write(f: Facts, rubric: Rubric, c: Collected, aid: str | None, after: int) -> int | None:
    """Step of the artifact's first successful content write at or after ``after`` (else its first at all)."""
    if not aid or aid not in rubric.artifacts:
        return None
    steps = sorted(e.step for p in location_paths(rubric, f, c, rubric.artifacts[aid]) for e in f.writes.get(p, []) if e.ok is not False and e.op in WRITE_OPS and e.op != "move_in")
    if not steps:
        return None
    return next((s for s in steps if s >= after), steps[0])


def _windows(f: Facts, rubric: Rubric, c: Collected) -> None:
    mode = str((rubric.scoring or {}).get("windows", "reads"))
    after_start = (rubric.scoring or {}).get("next_read") == "after_start"
    stages = rubric.stages
    n = len(stages)
    if not n:
        return

    def oa(k: int) -> str | None:
        st = stages[k]
        return st.order_artifact or (st.artifacts[0] if st.artifacts else None)

    reads_start: list[int | None] = []
    for st in stages:
        r = f.first_read(st.doc) if st.doc else None
        reads_start.append(r.step if r else None)
    writes_start: list[int | None] = [1] + [_first_write(f, rubric, c, oa(k - 1), 1) for k in range(1, n)]
    first, second = (writes_start, reads_start) if mode == "writes" else (reads_start, writes_start)
    starts = [first[k] if first[k] is not None else second[k] for k in range(n)]
    for k, st in enumerate(stages):
        if starts[k] is None:
            # neither bound exists: the stage's document was never read and the previous stage's artifact never
            # written -- the stage has no window (not the whole run, where earlier stages' runs and edits would
            # stand in for this stage's own: a Stage-1 baseline run is no Stage-5 re-run)
            f.notes.append(f"stage {st.id}: no window (document never read, previous artifact never written)")
            continue
        w = _first_write(f, rubric, c, oa(k), starts[k])
        writes_end = w + 1 if w is not None else None
        reads_end = reads_start[k + 1] if k + 1 < n else None
        if after_start and k + 1 < n and stages[k + 1].doc and reads_end is not None and reads_end < starts[k]:
            # the next document was read ahead: the next stage begins at its first read after this one began
            later = [r.step for r in f.doc_reads.get(stages[k + 1].doc, []) if r.step >= starts[k]]
            reads_end = min(later) if later else None
        if mode == "writes":
            end = writes_end if writes_end is not None else (reads_end if k + 1 < n else None)
        else:
            end = reads_end if (reads_end is not None or k + 1 == n) else writes_end
        if end is not None and end < starts[k]:
            end = starts[k]
        f.windows[st.id] = (starts[k], end)


__all__ = [
    "build",
    "artifact_text",
    "owning_stage",
    "is_test_path",
    "is_generated",
    "change_paths",
    "untracked_by_replay",
    "is_new_path",
    "last_change_write",
    "executed_paths",
    "roots_of",
    "expand",
    "template_regex",
    "location_paths",
    "WRITE_OPS",
]
