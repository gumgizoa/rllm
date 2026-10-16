"""Check kinds about what the agent did: reads, the first action, order, writes, runs, prohibitions.

Each reads :class:`~..context.Facts` only (built by :mod:`..facts`), so a rubric item is a pure
function of the run. The kinds close the AI-DLC reward's process loopholes:

``doc_read``          a document reached the agent inside its stage window with enough coverage
                      (fingerprints in the observation, not the command's wording); optionally not
                      in a multi-read step, and not peeked at before the previous stage closed
``doc_read_first``    the first acting call reads the entry document (``ls``/``pwd``/``cd`` allowed before)
``order``             events (``read:D``, ``write:A``, ...) happen in order; a write counts only once
                      its artifact is substantive (so stubs earn no order), and the rubric may void
                      reads ahead of the chain, reads in multi-read steps and rewritten artifacts
``write_discipline``  once / append_only / no_rewrite over the artifact's whole life; a sandbox file
                      the trace does not explain (``final_mismatch``) always fails
``exec_evidence``     >= N *valid* runs (:mod:`..evidence`) in the window
``prohibited_action`` no run / script execution, repo write, test-file write, install, whole-suite test run
                      (``full_suite``: a runner at the repository root selecting nothing) or matching
                      command in the window; a repo change the trace does not show fails safe

Default artifact: ``item.target.ref``; default window: ``stage:<item.stage>`` (whole run for
``global`` items).
"""

from __future__ import annotations

import re

from .. import aggregate, evidence, refs
from ..context import UNKNOWN, EvalContext, Result
from ..facts import WRITE_OPS, executed_paths, is_new_path, is_test_path, location_paths
from ..schema import Item
from ..trace import shell
from . import register

DEFAULT_ALLOW = r"^\s*(ls|pwd|cd)\b"
CONTENT_WRITES = WRITE_OPS - {"move_in"}  # ops that author content (a move relocates it)
FULL_WRITES = frozenset({"create", "overwrite"})
# the values of each enumerated parameter the kinds below implement (the generator rejects any other)
INVALIDATIONS = ("read_ahead", "multi_read", "rewrite")
WRITE_MODES = ("once", "append_only", "no_rewrite")
RUN_KINDS = ("test", "build")
PROHIBITED_ACTIONS = ("execute", "repo_write", "source_write", "test_file_write", "install", "full_suite", "command")

_INSTALL = re.compile(
    r"""^(?:\S*/)?(?:
        (?:python[0-9.]*\s+-m\s+)?pip[0-9.]*\s+install\b | uv\s+(?:pip\s+install|add|sync)\b | poetry\s+(?:add|install)\b | pipenv\s+install\b
      | pipx\s+install\b | easy_install\b | (?:conda|mamba|micromamba)\s+(?:install|create)\b | apt(?:-get)?\s+install\b
      | (?:yum|dnf|zypper)\s+install\b | apk\s+add\b | brew\s+install\b | npm\s+(?:install|i|ci|add)\b | yarn\s+(?:add|install)\b | yarn\s*$
      | pnpm\s+(?:add|install|i)\b | gem\s+install\b | bundle\s+install\b | cargo\s+(?:install|add)\b | go\s+(?:get|install)\b
      | python[0-9.]*\s+(?:\S+/)?setup\.py\s+(?:install|develop)\b
    )""",
    re.X,
)


def _params(item: Item) -> dict:
    return item.check.params or {}


def _window_spec(item: Item):
    p = _params(item)
    return p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)


def _as_list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _segments(ctx: EvalContext, cmd) -> list[shell.Segment]:
    key = ("segments", cmd.step, cmd.action_index)
    if key not in ctx.cache:
        ctx.cache[key] = shell.flat(shell.split(cmd.command, cmd.cwd)[0])
    return ctx.cache[key]


def _prev_stage(ctx: EvalContext, doc: str, stage: str):
    """The stage before the one ``doc`` governs (or before ``stage``)."""
    ids = [s.id for s in ctx.rubric.stages]
    k = next((i for i, s in enumerate(ctx.rubric.stages) if s.doc == doc), ids.index(stage) if stage in ids else None)
    return ctx.rubric.stages[k - 1] if k else None


def _closing_artifact(st) -> str | None:
    return st.order_artifact or (st.artifacts[0] if st.artifacts else None)


def _read_ahead(ctx: EvalContext, doc: str, stage: str) -> str:
    """Why ``doc``'s first sight (any coverage, any time) came before the previous stage closed ('' if it did not)."""
    reads = ctx.facts.doc_reads.get(doc) or []
    prev = _prev_stage(ctx, doc, stage)
    aid = _closing_artifact(prev) if prev else None
    if not reads or not aid:
        return ""
    w = refs.write_event(ctx, aid)
    if w is None:
        return f"{doc} read at step {reads[0].step}, but {aid} (closing {prev.id}) was never written"
    if w is UNKNOWN:
        return f"{aid} (closing {prev.id}) written at an unknown time"
    if reads[0].step < w:
        return f"{doc} first seen at step {reads[0].step}, before {aid} was written (step {w})"
    return ""


# ============================================================================================
# Reads
# ============================================================================================
@register("doc_read", params={"doc": True, "window": False, "min_coverage": False, "single_doc": False, "no_read_ahead": False}, availability=("trace",))
def doc_read(item: Item, ctx: EvalContext) -> Result:
    """A read of ``doc`` inside the window whose coverage (best single read, or the window's reads
    together -- a document read in chunks) reaches ``min_coverage`` (0.3). ``single_doc``: reads in
    multi-read steps do not count. ``no_read_ahead``: the document's first sight must not precede
    the write that closes the previous stage."""
    from .. import docread

    p = _params(item)
    doc = str(p["doc"])
    f = ctx.facts
    if p.get("no_read_ahead"):
        why = _read_ahead(ctx, doc, item.stage)
        if why:
            return Result.no(item, why)
    w = refs.window(ctx, _window_spec(item))
    if w is None:
        return Result.no(item, "window empty")
    reads = [r for r in f.doc_reads.get(doc, []) if refs.in_window(r.step, w)]
    if p.get("single_doc"):
        reads = [r for r in reads if r.step not in f.multi_read_steps]
    if not reads:
        return Result.no(item, f"{doc} not read in {list(w)}")
    best = max(reads, key=lambda r: r.coverage)
    cov = best.coverage
    hits, fps = getattr(f, "_doc_hits", None), getattr(f, "_doc_fps", None)
    if hits is not None and fps is not None:
        cov = max(cov, docread.union_coverage(hits, fps, doc, {r.step for r in reads}))
    need = float(p.get("min_coverage", 0.3))
    if cov >= need:
        return Result.ok(item, f"{doc} read at step {best.step} ({best.via}), coverage {cov:.2f}")
    return Result.no(item, f"{doc} coverage {cov:.2f} < {need:g}")


def _allowed(ctx: EvalContext, step: int, idx: int, a, allow: list[re.Pattern]) -> bool:
    if a.kind == "view":
        listing = re.search(r"files and directories", a.observation or "") is not None
        return listing and any(rx.match(f"ls {a.path}") for rx in allow)
    if a.kind != "shell" or not a.command:
        return False
    cwd = (getattr(ctx.facts, "_cwd_track", None) or {}).get((step, idx))
    segs = shell.flat(shell.split(a.command, cwd)[0])
    texts = [s.text for s in segs] or [a.command]
    return all(any(rx.match(t) for rx in allow) for t in texts)


@register("doc_read_first", params={"doc": True, "allow": False}, availability=("trace",))
def doc_read_first(item: Item, ctx: EvalContext) -> Result:
    """The first acting call that is not purely an ``allow`` command (default ``ls``/``pwd``/``cd``,
    every segment) reads ``doc`` -- by command, or with its fingerprints in that call's output."""
    p = _params(item)
    doc = str(p["doc"])
    raw = p.get("allow")
    allow = [re.compile(x) for x in (_as_list(raw) if raw is not None else [DEFAULT_ALLOW])]
    action_docs = getattr(ctx.facts, "_action_docs", None)
    for step in ctx.run.steps:
        for idx, a in enumerate(step.actions):
            if not a.acts:
                continue
            if action_docs is not None:
                read = doc in action_docs.get((step.n, idx), ())
            else:
                read = any(r.step == step.n for r in ctx.facts.doc_reads.get(doc, []))
            if read:
                return Result.ok(item, f"step {step.n}")
            if _allowed(ctx, step.n, idx, a, allow):
                continue
            what = (a.command or "").strip().splitlines()[0][:60] if a.kind == "shell" and a.command else f"{a.kind} {a.path or ''}"
            return Result.no(item, f"first action (step {step.n}) does not read {doc}: {what}")
    return Result.no(item, "no acting call")


# ============================================================================================
# Order
# ============================================================================================
def _content_writes(ctx: EvalContext, aid: str) -> list:
    art = ctx.rubric.artifacts.get(aid)
    if art is None:
        return []
    evs = [e for p in location_paths(ctx.rubric, ctx.facts, ctx.collected, art) for e in ctx.facts.writes.get(p, []) if e.ok is not False and e.op in CONTENT_WRITES]
    return sorted(evs, key=lambda e: (e.step, e.action_index))


def _has_quality(ctx: EvalContext, aid: str) -> bool:
    return any(i.target.type == "artifact" and i.target.ref == aid and i.check.kind != "order" and i.cls != "evidence" for i in ctx.rubric.items)


def _event(ctx: EvalContext, ev: str, inv: set[str], substantive: float, prev_write):
    """(resolved step or None, raw step for read-ahead purposes, why it was voided)."""
    f = ctx.facts
    kind, _, arg = ev.partition(":")
    if kind in ("write", "first_write", "last_write"):
        if arg not in ctx.rubric.artifacts:
            raise refs.RefError(f"order: unknown artifact {arg!r}")
        raw = refs.event(ctx, ev)
        if raw is None or raw is UNKNOWN:
            return raw, raw, "" if raw is None else f"{arg} written at an unknown time"
        if _has_quality(ctx, arg) and ctx.quality.get(arg, 0.0) < substantive:
            return None, raw, f"{arg} not substantive ({ctx.quality.get(arg, 0.0):.2f})"
        if "rewrite" in inv:
            path = f.artifact_paths.get(arg)
            n = len(_content_writes(ctx, arg))
            if n > 1 or (path and f.final_mismatch.get(path)):
                return None, raw, f"{arg} rewritten ({n} writes)" if n > 1 else f"{arg} differs from the trace"
        return raw, raw, ""
    if kind == "read":
        reads = f.doc_reads.get(arg) or []
        if not reads:
            return None, None, ""
        if "multi_read" in inv:
            r = next((r for r in reads if r.step not in f.multi_read_steps), None)
            step = r.step if r else None
            why = "" if r else f"{arg} only read in multi-read steps"
        else:
            step, why = reads[0].step, ""
        if "read_ahead" in inv and prev_write is not None and (prev_write is UNKNOWN or reads[0].step < prev_write):
            return None, step, f"{arg} first seen at step {reads[0].step}, before the previous write"
        return step, step, why
    step = refs.event(ctx, ev)
    return step, step, ""


@register("order", params={"chain": False, "before": False, "after": False, "invalidate": False, "substantive": False}, availability=("trace",), choices={"invalidate": INVALIDATIONS})
def order(item: Item, ctx: EvalContext) -> Result:
    """Share of adjacent ``chain`` pairs (or ``before`` x ``after`` pairs) with both events resolved,
    neither at an unknown time, the first strictly earlier. ``write:A`` resolves only when A is
    substantive (``ctx.quality`` >= ``substantive``; artifacts no item grades are exempt) and, with
    ``invalidate: [rewrite]``, written once and matching the sandbox. ``invalidate: [multi_read]``
    skips reads in multi-read steps; ``[read_ahead]`` voids a read first seen before the previous write."""
    p = _params(item)
    if p.get("chain"):
        seq = [str(e) for e in p["chain"]]
        pairs = [(i, i + 1) for i in range(len(seq) - 1)]
    elif p.get("before") and p.get("after"):
        before, after = [str(e) for e in _as_list(p["before"])], [str(e) for e in _as_list(p["after"])]
        seq = before + after
        pairs = [(i, len(before) + j) for i in range(len(before)) for j in range(len(after))]
    else:
        return Result.no(item, "order needs chain or before/after")
    if not pairs:
        return Result.no(item, "nothing to order")
    inv = {str(x) for x in _as_list(p.get("invalidate"))}
    sub = float(p.get("substantive", aggregate.scoring_of(ctx.rubric).get("substantive_threshold", 0.5)))
    steps: list = []
    notes: list[str] = []
    prev_write = None
    for ev in seq:
        step, raw, why = _event(ctx, ev, inv, sub, prev_write)
        steps.append(step)
        if why:
            notes.append(why)
        if ev.partition(":")[0] in ("write", "first_write", "last_write"):
            prev_write = raw
    good = [(a, b) for a, b in pairs if steps[a] is not None and steps[b] is not None and steps[a] is not UNKNOWN and steps[b] is not UNKNOWN and steps[a] < steps[b]]
    shown = ", ".join(f"{seq[i]}={'?' if s is UNKNOWN else s}" for i, s in enumerate(steps))
    detail = f"{len(good)}/{len(pairs)}: {shown}" + (f" ({'; '.join(notes[:3])})" if notes else "")
    return Result.ratio(item, len(good), len(pairs), detail[:400])


# ============================================================================================
# Writes
# ============================================================================================
@register("write_discipline", params={"mode": True, "artifact": False, "window": False}, availability=("trace", "sandbox_file"), choices={"mode": WRITE_MODES})
def write_discipline(item: Item, ctx: EvalContext) -> Result:
    """``once``: exactly one successful write over the artifact's life, a full create/overwrite,
    inside the window (default: its stage); ``append_only``: every later write keeps the earlier
    content as its prefix; ``no_rewrite``: no full write after the first. A sandbox file the trace
    does not explain fails every mode. For the last two an explicit ``window`` limits where
    violations are looked for; by default it is the whole run."""
    p = _params(item)
    mode = str(p["mode"])
    aid = str(p.get("artifact") or item.target.ref)
    f = ctx.facts
    if aid not in ctx.rubric.artifacts:
        return Result.no(item, f"artifact {aid!r} undefined")
    path = f.artifact_paths.get(aid)
    if not path:
        return Result.no(item, "absent")
    if f.final_mismatch.get(path):
        return Result.no(item, "the final file is not what the trace wrote")
    evs = _content_writes(ctx, aid)
    explicit = refs.window(ctx, p["window"]) if "window" in p else None
    if "window" in p and explicit is None:
        return Result.no(item, "window empty")
    if mode == "once":
        if len(evs) != 1:
            return Result.no(item, f"{len(evs)} writes (steps {[e.step for e in evs][:8]})")
        e = evs[0]
        if e.op not in FULL_WRITES:
            return Result.no(item, f"written by {e.op}, not one full write")
        w = explicit if "window" in p else refs.window(ctx, _window_spec(item))
        if w is None or not refs.in_window(e.step, w):
            return Result.no(item, f"written at step {e.step}, outside {list(w) if w else 'an empty window'}")
        return Result.ok(item, f"one write at step {e.step}")
    if mode == "append_only":
        for prev, cur in zip(evs, evs[1:], strict=False):
            if explicit is not None and not refs.in_window(cur.step, explicit):
                continue
            if prev.content is None or cur.content is None:
                return Result.no(item, f"content unknown at step {cur.step}")
            if not cur.content.startswith(prev.content.rstrip()):
                return Result.no(item, f"step {cur.step} changed earlier content ({cur.op})")
        return Result.ok(item, f"{len(evs)} writes, append only")
    if mode == "no_rewrite":
        first = next((k for k, e in enumerate(evs) if e.op in FULL_WRITES), None)
        if first is None:
            return Result.ok(item, "never fully written") if evs else Result.no(item, "no write in the trace")
        later = [e for e in evs[first + 1 :] if e.op in FULL_WRITES | {"unknown"} and (explicit is None or refs.in_window(e.step, explicit))]
        if later:
            return Result.no(item, f"rewritten at step {later[0].step} ({later[0].op})")
        return Result.ok(item, f"first written at step {evs[first].step}, not rewritten")
    return Result.no(item, f"unknown mode {mode!r}")


# ============================================================================================
# Runs and prohibitions
# ============================================================================================
@register("exec_evidence", params={"kind": False, "window": False, "command_in": False, "min_count": False}, availability=("trace",), choices={"kind": RUN_KINDS})
def exec_evidence(item: Item, ctx: EvalContext) -> Result:
    """At least ``min_count`` (1) valid runs of ``kind`` (test) in the window, matching ``command_in``
    (a selector of commands) when given; the score is the share of ``min_count`` found."""
    p = _params(item)
    kind = str(p.get("kind", "test"))
    need = max(1, int(p.get("min_count", 1)))
    spec = _window_spec(item)
    w = refs.window(ctx, spec)
    if w is None:
        return Result.no(item, "window empty")
    q = {"fact": "valid_run", "kind": kind, **({"window": spec} if spec is not None else {}), **({"command_in": p["command_in"]} if "command_in" in p else {})}
    runs = list(refs.matching(ctx, q))
    if len(runs) >= need:
        return Result.ok(item, f"{len(runs)} valid {kind} run(s), first at step {runs[0].step}")
    tried = [r for r in ctx.facts.runs if r.kind == kind and refs.in_window(r.step, w)]
    why = "; ".join(dict.fromkeys(f"step {r.step}: {r.reason}" for r in tried if r.reason))[:300]
    detail = f"{len(runs)}/{need} valid {kind} runs in {list(w)}" + (f" ({why})" if why else "")
    return Result.ratio(item, len(runs), need, detail)


def _install(seg: shell.Segment) -> bool:
    return bool(seg.cmd) and _INSTALL.match(" ".join(seg.cmd)) is not None


@register("prohibited_action", params={"action": True, "window": False, "pattern": False, "selector": False, "paths_in": False}, availability=("trace",), choices={"action": PROHIBITED_ACTIONS})
def prohibited_action(item: Item, ctx: EvalContext) -> Result:
    """No action of class ``action`` in the window: ``execute`` (a test-runner invocation, or running
    a path ``selector`` names), ``repo_write`` / ``test_file_write`` (an existing test file: one at
    BASE_SHA, not created by the run) / ``source_write`` (any file that existed at BASE_SHA, modified in
    place; a file the run creates is not one) -- restricted to ``paths_in``; a change the diff shows but
    the trace does not counts --, ``install`` (pip/npm/apt ... install),
    ``full_suite`` (a test runner at the repository root that selects no path, id, label or filter),
    ``command`` (any command matching ``pattern``). ``pattern`` also filters the other classes
    (commands for execute/install/full_suite, repo paths for writes)."""
    p = _params(item)
    action = str(p["action"])
    f = ctx.facts
    w = refs.window(ctx, _window_spec(item))
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"])) if p.get("pattern") else None
    hits: list[str] = []
    if action == "execute":
        hits += [f"step {r.step}: {r.segment[:60]}" for r in f.runs if r.kind == "test" and refs.in_window(r.step, w) and (rx is None or rx.search(r.command))]
        if "selector" in p:
            targets = refs.as_set(refs.normalize(refs.select(ctx, p["selector"]), "path", ctx))
            hits += [f"step {s}: runs {path}" for s, path in executed_paths(ctx) if refs.in_window(s, w) and path in targets]
    elif action in ("repo_write", "test_file_write", "source_write"):
        inside = refs.as_set(refs.normalize(refs.select(ctx, p["paths_in"]), "path", ctx)) if "paths_in" in p else None

        def wanted(path: str) -> bool:
            # test_file_write: an existing test file (edited, overwritten, removed) -- a new file the run adds is
            # no edit of the tests; whether it may stay in the change is the change's own check.
            # source_write: any file that existed at BASE_SHA, modified in place (a file the run creates is not one)
            if action == "repo_write":
                kind_ok = True
            elif action == "test_file_write":
                kind_ok = is_test_path(path) and not is_new_path(ctx, path)
            else:
                kind_ok = not is_new_path(ctx, path)
            return kind_ok and (inside is None or path in inside) and (rx is None or rx.search(path) is not None)

        hits += [f"step {e.step}: {e.op} {e.path}" for e in f.repo_writes if e.ok is not False and refs.in_window(e.step, w) and wanted(e.path)]
        hits += [f"changed outside the trace: {path}" for path in getattr(f, "_unseen_repo_paths", []) if wanted(path)]
    elif action == "install":
        for c in f.commands:
            if refs.in_window(c.step, w) and (rx is None or rx.search(c.command)):
                seg = next((s for s in _segments(ctx, c) if _install(s)), None)
                if seg is not None:
                    hits.append(f"step {c.step}: {seg.text[:60]}")
    elif action == "full_suite":
        for c in f.commands:
            if refs.in_window(c.step, w) and (rx is None or rx.search(c.command)):
                seg = next((s for s in _segments(ctx, c) if evidence.full_suite(s, ctx.collected.workdir)), None)
                if seg is not None:
                    hits.append(f"step {c.step}: {seg.text[:60]}")
    elif action == "command":
        if rx is None:
            return Result.no(item, "action command needs a pattern")
        hits += [f"step {c.step}: {c.command.strip()[:60]}" for c in f.commands if refs.in_window(c.step, w) and rx.search(c.command)]
    else:
        return Result.no(item, f"unknown action {action!r}")
    if hits:
        return Result.no(item, f"{len(hits)} in window: {hits[0]}")
    return Result.ok(item, f"no {action} in {list(w)}")


__all__ = ["doc_read", "doc_read_first", "order", "write_discipline", "exec_evidence", "prohibited_action"]
