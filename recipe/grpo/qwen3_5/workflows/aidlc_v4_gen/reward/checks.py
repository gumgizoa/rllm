"""AI-DLC plugin kind: executions the reference language has no event or fact for.

The refs language (``workflow_rubric.refs``) can say that a *runner* produced valid evidence in a
window (``exec_evidence``), that a recorded value is a command run in a window (``field_type``),
and -- inside predicates only -- that a path was executed (``exists: {fact: exec_of}``). It cannot
say, as a check, that the reproduction script an artifact names was executed (BT:26 "Execute the
reproduction script at the path Code Generation recorded"), nor that several executions happened
in an order (CW:124 "build, run the reproduction script, then re-run the existing covering tests"):
executions are not events. ``aidlc.executed`` is that one missing piece; everything else in the
AI-DLC rubric is common kinds. The same gap holds for reads and writes of a path an artifact names
(RE:35 "Read them" -- the covering tests A1 lists; CG:28 "Write the reproduction script at the path
the plan records"), so those are steps too.

Each step names one execution, by a selector over the agent's artifacts (anchored on the trace:
the step must be *observed*, the artifact only says which path / command to look for)::

    {exec_of: <selector>}            a path the selector names was executed (script or runner target)
    {command_in: <selector>}         a shell command (or one of its segments) equals the value
    {valid_run: {kind?, command_in?}} a valid runner invocation (evidence.py), optionally of that command
    {valid_run: {kind?, same_selection_as: <selector>}}
                                     a valid run selecting the same tests as the recorded command: the
                                     runner's targets / node ids / labels as parsed (output flags such as
                                     -q, -v, --tb=short or a `| tail` do not change a selection; BT:36);
                                     a recorded bare runner (the whole suite) is matched by the same bare
                                     runner from the same directory; when the recorded command parses to
                                     no selection, a valid run of that very command (normalised) counts
    {read_of: <selector>}            every path the selector names was read (an editor view, or a read
                                     verb -- cat, sed -n, head, grep ... -- naming it): one step per path
    {write_of: <selector>}           a path the selector names was written (a successful content write)
    optional_if_none: true           (on a step) skip it when the selector's value is a none token
                                     (A1 "Build: not applicable"); an absent value never skips

``in_order``: the steps are matched greedily at non-decreasing steps in the listed order. The score
is the share of steps found; it passes only when all are. Nothing the agent writes can make it raise:
a malformed value is a step not found.
"""

from __future__ import annotations

import re

from recipe.grpo.qwen3_5.workflow_rubric import evidence, refs
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.facts import executed_paths
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_PATH = re.compile(r"[\w.~/-]*[\w-]/[\w./-]+|[\w-]+\.[A-Za-z0-9]{1,8}\b")
STEP_KEYS = ("exec_of", "command_in", "valid_run", "read_of", "write_of")


def _ws(s: str) -> str:
    return re.sub(r"\s+", lambda m: "\n" if "\n" in m.group() else " ", s)


def _norm_cmd(c: str) -> str:
    return refs.norm_command(_ws(c[:4000]))


def _values(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v]


def _is_none_value(vals: list[str]) -> bool:
    return bool(vals) and all(M.is_none(x) for x in vals)


def _paths(vals: list[str], workdir: str | None) -> set[str]:
    out: set[str] = set()
    for v in vals:
        for piece in [*_CODE_SPAN.findall(v), v]:
            m = _PATH.search(piece.replace("`", " ")[:500])
            if m:
                out.add(refs.norm_path(m.group(0), workdir))
    out.discard("")
    return out


def _commands(vals: list[str]) -> set[str]:
    out: set[str] = set()
    for v in vals:
        for x in [v, *v.splitlines(), *_CODE_SPAN.findall(v)]:
            x = re.sub(r"^\$\s+", "", x.strip())
            if x:
                out.add(_norm_cmd(x))
    out.discard("")
    return out


def selection(command: str, cwd: str | None, workdir: str | None) -> frozenset[str]:
    """The tests a runner command selects: node ids, the target files / dirs without one, labels (empty: none parsed)."""
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    try:
        segs = shell.flat(shell.split(command[:4000], cwd)[0])
    except Exception:  # noqa: BLE001 -- agent text: an unparsable command selects nothing
        return frozenset()
    for seg in segs:
        hit = evidence.classify(seg)
        if hit is None or hit.runner.kind != "test":
            continue
        nodes = {refs.norm_path(n, workdir) for n in hit.node_ids}
        files = {refs.norm_path(t, workdir) for t in hit.targets}
        files = {f for f in files if not any(n.startswith(f + "::") for n in nodes)}
        return frozenset(nodes | files | {lbl for lbl, _ in hit.labels} | {f"runner:{hit.runner.name}"})
    return frozenset()


def bare_runner(command: str, cwd: str | None, workdir: str | None) -> tuple[str, str] | None:
    """(runner name, cwd) when the command's first test-runner invocation selects nothing (a bare ``pytest``,
    ``tests/runtests.py`` without labels): the whole suite under that cwd; None otherwise."""
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    try:
        segs = shell.flat(shell.split(command[:4000], cwd)[0])
    except Exception:  # noqa: BLE001 -- agent text
        return None
    for seg in segs:
        hit = evidence.classify(seg)
        if hit is None or hit.runner.kind != "test":
            continue
        if hit.targets or hit.node_ids or hit.labels or evidence.selects(hit, workdir) is not False:
            return None
        return hit.runner.name, (seg.cwd or "").rstrip("/")
    return None


def _same_selection(ctx: EvalContext, spec: dict, vals: list[str], w) -> list[int]:
    wd = ctx.collected.workdir
    texts = [re.sub(r"^\$\s+", "", x.strip()) for v in vals for x in [v, *_CODE_SPAN.findall(v)] if x.strip()]
    want = {selection(x, wd, wd) for x in texts}
    want = {x for x in want if len(x) > 1}  # a bare runner (whole suite) is not a recorded selection of tests
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    bare = {b for x in texts if (b := bare_runner(x, wd, wd))}
    if not want and bare:
        # the recorded command is the bare runner: the same runner, bare, from the same directory is the same selection
        # (REVIEW-RED; whether a bare runner may be recorded at all is the A1 Test item's question, RE:27, and running the
        # whole suite in Stage 5 the full_suite prohibition's, BT:39)
        steps = [
            r.step
            for r in ctx.facts.runs
            if r.valid and refs.in_window(r.step, w) and (not spec.get("kind") or r.kind == spec["kind"]) and bare_runner(r.command, cwd_track.get((r.step, r.action_index), wd), wd) in bare
        ]
        if steps:
            return steps
    if not want:
        # nothing parsed as a selection: the same command, run again, is the same selection (BT:36);
        # whether the command targets the covering tests at all is the A1 Test item's question (RE:27)
        cmds = _commands(vals)
        q = {"fact": "valid_run", "command_in": {"literal": sorted(cmds)}, **({"kind": spec["kind"]} if spec.get("kind") else {})}
        return [r.step for r in refs.matching(ctx, q) if refs.in_window(r.step, w)] if cmds else []
    out = []
    for r in ctx.facts.runs:
        if not r.valid or not refs.in_window(r.step, w) or (spec.get("kind") and r.kind != spec["kind"]):
            continue
        if selection(r.segment or r.command, cwd_track.get((r.step, r.action_index), wd), wd) in want:
            out.append(r.step)
    return out


def _read_steps(ctx: EvalContext, want: set[str], w) -> dict[str, list[int]]:
    """Normalised path -> steps (in the window) at which it (or, for a directory, a file under it) was
    read: an editor ``view``, or a reading verb of a shell segment naming it (cwd resolved)."""
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    wd = ctx.collected.workdir
    out: dict[str, list[int]] = {p: [] for p in want}
    if not want:
        return out
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    known = sorted({p if p.startswith("/") else f"{(wd or '').rstrip('/')}/{p}" for p in want})
    for step in ctx.run.steps:
        if not refs.in_window(step.n, w):
            continue
        for idx, a in enumerate(step.actions):
            hits: list[str] = []
            if a.kind == "view" and a.path:
                hits = [shell.resolve(a.path, cwd_track.get((step.n, idx), wd))]
            elif a.kind == "shell" and a.command:
                try:
                    segs = shell.flat(shell.split(a.command[:20000], cwd_track.get((step.n, idx), wd))[0])
                except Exception:  # noqa: BLE001 -- agent text
                    continue
                hits = [t for seg in segs for t in shell.read_targets(seg, known)]
            for h in hits:
                n = refs.norm_path(h, wd)
                for p in want:  # a covering-test directory is read through the files under it
                    if (n == p or n.startswith(p.rstrip("/") + "/")) and step.n not in out[p]:
                        out[p].append(step.n)
    return out


def _write_steps(ctx: EvalContext, want: set[str], w) -> list[int]:
    wd = ctx.collected.workdir
    steps = []
    for path, evs in ctx.facts.writes.items():
        if refs.norm_path(path, wd) not in want:
            continue
        steps += [e.step for e in evs if e.ok is not False and e.op not in ("delete", "move_out") and refs.in_window(e.step, w)]
    return sorted(set(steps))


def _expand(ctx: EvalContext, steps: list[dict]) -> list[dict]:
    """A ``read_of`` step is one step per path its selector names (every covering test is read)."""
    out = []
    for s in steps:
        if "read_of" not in s:
            out.append(s)
            continue
        try:
            vals = _values(refs.select(ctx, s["read_of"]))
        except Exception:  # noqa: BLE001 -- a malformed artifact selects nothing
            vals = []
        if s.get("optional_if_none") and _is_none_value(vals):
            out.append({**s, "_paths": None})
            continue
        paths = sorted(_paths([x for x in vals if not M.is_none(x)], ctx.collected.workdir))
        out += [{**s, "_paths": {p}} for p in paths] or [{**s, "_paths": None, "_why": "no path recorded"}]  # the format items judge a missing path
    return out


def _occurrences(ctx: EvalContext, step: dict, w) -> tuple[list[int] | None, str]:
    """Steps (in the window) at which the execution happened; None = skipped (an allowed none value)."""
    key = next((k for k in STEP_KEYS if k in step), None)
    if key == "read_of":
        want = step.get("_paths")
        if want is None:
            return None, step.get("_why", "none value")
        hits = _read_steps(ctx, want, w)
        return sorted({s for v in hits.values() for s in v}), f"read of {sorted(want)[:1]}"
    if key == "valid_run":
        spec = dict(step["valid_run"] or {})
        if "same_selection_as" in spec:
            vals = _values(refs.select(ctx, spec["same_selection_as"]))
            if step.get("optional_if_none") and _is_none_value(vals):
                return None, "none value"
            return _same_selection(ctx, spec, vals, w), "valid run of the recorded selection"
        q = {"fact": "valid_run", **({"kind": spec["kind"]} if spec.get("kind") else {})}
        if "command_in" in spec:
            vals = _values(refs.select(ctx, spec["command_in"]))
            if step.get("optional_if_none") and _is_none_value(vals):
                return None, "none value"
            q["command_in"] = {"literal": sorted(_commands(vals))}
        runs = [r.step for r in refs.matching(ctx, q) if refs.in_window(r.step, w)]
        return runs, "valid run"
    vals = _values(refs.select(ctx, step[key]))
    if step.get("optional_if_none") and _is_none_value(vals):
        return None, "none value"
    if key == "exec_of":
        want = _paths(vals, ctx.collected.workdir)
        return [s for s, p in executed_paths(ctx) if p in want and refs.in_window(s, w)], f"exec of {sorted(want)[:2]}"
    if key == "write_of":
        want = _paths(vals, ctx.collected.workdir)
        return _write_steps(ctx, want, w), f"write of {sorted(want)[:2]}"
    want = _commands(vals)
    hits = []
    for c in ctx.facts.commands:
        if refs.in_window(c.step, w) and want & {_norm_cmd(x) for x in (c.command, *c.segments) if x}:
            hits.append(c.step)
    return hits, f"command {sorted(want)[:1]}"


@register("aidlc.executed", params={"steps": True, "window": False, "in_order": False}, availability=("trace",), common=False)
def executed(item: Item, ctx: EvalContext) -> Result:
    """steps: [{exec_of: <selector>} | {command_in: <selector>} | {valid_run: {kind?, command_in? | same_selection_as?: <selector>}} \
| {read_of: <selector>} | {write_of: <selector>}, + optional_if_none], each observed in the window (listed order with in_order).

    ``exec_of``: a path the selector names was executed; ``command_in``: a shell command equals the
    selector's value; ``valid_run``: a valid runner invocation; ``read_of``: each path the selector
    names was read; ``write_of``: a path it names was written. A step with ``optional_if_none`` is
    skipped when its recorded value is a none token; the score is the share of steps found."""
    p = item.check.params or {}
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    w = refs.window(ctx, spec)
    if w is None:
        return Result.no(item, "window empty")
    steps = _expand(ctx, [s for s in (p.get("steps") or []) if isinstance(s, dict)])
    t, found, need, notes = w[0], 0, 0, []
    for s in steps:
        occ, what = _occurrences(ctx, s, w)
        if occ is None:
            notes.append(f"skipped ({what})")
            continue
        need += 1
        later = sorted(x for x in occ if not p.get("in_order") or x >= t)
        if later:
            found += 1
            if p.get("in_order"):
                t = later[0]
            notes.append(f"{what} at {later[0]}")
        else:
            notes.append(f"{what}: not observed" + (f" after step {t}" if p.get("in_order") else ""))
    if need == 0:
        return Result.not_applicable(item, "; ".join(notes) or "no steps")
    return Result.ratio(item, found, need, "; ".join(notes)[:300])


__all__ = ["executed"]
