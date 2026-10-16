"""openspec_ff plugin kinds: the rules of a run that drives the real ``openspec`` CLI.

Unlike the ``openspec`` port, the CLI runs in the sandbox: ``openspec new change`` scaffolds the change,
``openspec instructions <artifact> --json`` serves each artifact's instruction and template, and ``openspec
archive`` validates the change, merges its delta specs into ``/openspec/specs/`` and moves it to
``/openspec/changes/archive/<date>-issue/`` -- file operations the trace does not show, only the command and
what it printed. The OpenSpec format rules over the change's files (delta specs, the proposal's capabilities,
the main specs, the task list, which files were read) are the ``openspec.*`` kinds of the ``openspec`` port,
vendored as ``openspec_kinds.py`` (that port is not on this branch) and used as they are. What they cannot say:

* ``openspec_ff.cli`` -- the CLI calls themselves. Every shell segment whose command is ``openspec`` (or
  ``npx openspec``, ``node .../openspec.js``) is one invocation; ``sub`` is a regex over its arguments
  (``^instructions\\s+apply\\b``, quotes removed) or over the segment as typed (``openspec new change "issue"``). ``{rule: ran}`` -- one ran in the window (with ``ok``: and
  succeeded), ``{rule: absent}`` -- none ran in the window (``openspec init``, ``--schema``, ``--no-validate``).
  Success is read off the call's own observation: the exit-code line the terminal tool appends when there is
  one, else the CLI's failure text (``Error``, ``Aborted``, ``Validation failed``).
* ``openspec_ff.archive`` -- the archive step (core-workflow.md:89-106)::

      {rule: succeeded}      an ``openspec archive`` call printed "archived as" (or exited 0 without failure text)
      {rule: retries}        at most two archive calls, the second only after a failed first, none after a success
      {rule: after}          the first archive call comes after ``event`` (a refs event: the verify report's write)
      {rule: by_cli}         the trace itself writes or moves nothing into the archive directory or the main specs
                             (``roots``): the CLI did the archive, not ``mv`` / ``cp`` / a hand-written main spec
      {rule: specs_only}     after the first archive call the trace writes nothing but the change's delta specs
                             (``allow``: path prefixes) -- no code, no tasks, no other artifact

* ``openspec_ff.delta`` -- ``{rule: added_only}``: every delta section of every delta spec is ``## ADDED
  Requirements`` (``/openspec/specs/`` starts empty, core-workflow.md:69-70; the project rules).
* ``openspec_ff.evidence`` -- ``{rule: test_or_check}``: in the window, a valid run of the repository's tests
  (``evidence.py``) or the execution of a script the run wrote under the change's ``checks/`` directory
  (schema.yaml tasks instruction: "run the existing repository tests ... or write a check script ... and run it").
* ``openspec_ff.tasks`` -- the task list's history across its two locations (active, archived):
  ``{rule: written}`` -- a content write of it in the window; ``{rule: rerun_after_tick}`` -- each write that
  ticks a box is followed by an ``openspec instructions apply`` call before the next ticking write (or the end
  of the window) (ratio; 02-apply.md:98); ``{rule: done_or_reasoned}`` -- at the end every task is ticked or
  carries a plain line under it, its one-line reason (02-apply.md:105, 109) (ratio).
* ``openspec_ff.verify`` -- ``{rule: open_tasks_critical}``: when tasks.md held open boxes as the report was
  written, the report lists a CRITICAL issue (03-verify.md:70-71).
* ``openspec_ff.created_files`` / ``openspec_ff.no_fetch`` / ``openspec_ff.holds`` -- as in speckit_bug: no
  test / scratch file created in the repository, no URL fetched, a refs predicate as a check.
* ``openspec_ff.paths_written`` -- no file the trace wrote matches ``pattern`` (a script under /tmp: checks belong
  in the change's checks/, core-workflow.md:36-37; any file at all while exploring, core-workflow.md:77-78).
* ``openspec_ff.note`` -- one tool call in the window (a ``think`` thought, a command as typed, a write's text)
  holds every regex of ``patterns``: a note the documents ask to be written inside a tool call, such as explore's
  "What We Figured Out" summary before the call that opens 01-ff.md (00-explore.md:189-191, core-workflow.md:60-63).
  The window's end step counts too, so the note may share the turn that opens the next stage's document.

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import posixpath
import re

from recipe.grpo.qwen3_5.workflow_rubric import facts as F
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell
from recipe.grpo.qwen3_5.workflows.openspec_ff.reward import openspec_kinds as OS  # registers the openspec.* kinds

MAX_CMD = 20_000
MAX_TEXT = 400_000
_EXIT = re.compile(r"\[(?:The command completed with exit code|Command finished with exit code)\s+(-?\d+)\.?\]")
_FAIL = re.compile(r"(?im)^\s*(?:error\b|✗|✖|aborted\b|validation failed\b)|\bAborted\. No files were changed\b|\bValidation failed\b")
_ARCHIVED = re.compile(r"\barchived as\s+['\"]?[\w.-]+")
_OPENSPEC_JS = re.compile(r"(?:^|/)openspec(?:\.js)?$")


# --------------------------------------------------------------------------------------------
# Invocations of the CLI
# --------------------------------------------------------------------------------------------
def _window(item: Item, ctx: EvalContext):
    p = item.check.params or {}
    if "window" in p:
        return refs.window(ctx, p["window"])
    if item.stage == "global":
        return (1, ctx.facts.n_steps + 2)
    return refs.window(ctx, f"stage:{item.stage}")


def _args_of(seg: shell.Segment) -> list[str] | None:
    """The arguments after ``openspec`` when the segment invokes the CLI, else None."""
    cmd = list(seg.cmd or [])
    if not cmd:
        return None
    head = posixpath.basename(cmd[0])
    if head == "openspec":
        return cmd[1:]
    if head in ("npx", "pnpx", "bunx") and len(cmd) > 1 and posixpath.basename(cmd[1]).split("@")[0] in ("openspec", "@fission-ai/openspec"):
        return cmd[2:]
    if head in ("node", "nodejs") and len(cmd) > 1 and _OPENSPEC_JS.search(cmd[1]):
        return cmd[2:]
    return None


def invocations(ctx: EvalContext) -> list[tuple[int, int, str, str]]:
    """(step, action index, the argument string (quotes removed), the call's observation, the segment as typed) of every
    ``openspec`` invocation, in order."""
    key = "openspec_ff.invocations"
    if key in ctx.cache:
        return ctx.cache[key]
    out = []
    for c in ctx.facts.commands:
        try:
            segs = shell.flat(shell.split(c.command[:MAX_CMD], c.cwd)[0])
        except Exception:  # noqa: BLE001 -- agent text: an unparsable command invokes nothing
            continue
        for seg in segs:
            args = _args_of(seg)
            if args is not None:
                out.append((c.step, c.action_index, " ".join(a.strip() for a in args if a.strip()), c.observation or "", seg.text or ""))
    ctx.cache[key] = out
    return out


def succeeded(observation: str) -> bool | None:
    """Did the call succeed, by its own observation: failure text -> False; else the exit-code line; else
    None (the trace does not say -- harbor's openhands-sdk records no exit code)."""
    obs = (observation or "")[-MAX_TEXT:]
    if _FAIL.search(obs):
        return False
    m = _EXIT.findall(obs)
    if m:
        return all(int(x) == 0 for x in m)
    return None


def _archive_ok(observation: str) -> bool:
    if _ARCHIVED.search(observation or ""):
        return True
    return succeeded(observation) is True


def _sub(p: dict) -> re.Pattern:
    return re.compile(str(p.get("sub") or "."))


@register("openspec_ff.cli", params={"rule": True, "sub": True, "window": False, "ok": False}, availability=("trace",), common=False, choices={"rule": ("ran", "absent")})
def cli(item: Item, ctx: EvalContext) -> Result:
    """rule: ran | absent -- an ``openspec`` call whose arguments match ``sub`` ran in the window (``ok``: and succeeded) / none ran."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    w = _window(item, ctx)
    rx = _sub(p)
    hits = [(s, a, o) for s, _, a, o, t in invocations(ctx) if refs.in_window(s, w) and (rx.search(a) or rx.search(t))]
    if rule == "absent":
        if w is None:
            return Result.ok(item, "window empty")
        return Result.no(item, f"step {hits[0][0]}: openspec {hits[0][1][:60]}") if hits else Result.ok(item, f"no 'openspec {rx.pattern}' in the window")
    if rule != "ran":
        return Result.no(item, f"unknown rule {rule!r}")
    if w is None:
        return Result.no(item, "window empty")
    if not hits:
        return Result.no(item, f"no 'openspec {rx.pattern}' in {list(w)}")
    if p.get("ok"):
        good = [s for s, a, o in hits if succeeded(o) is not False]
        if not good:
            return Result.no(item, f"{len(hits)} call(s), none succeeded (step {hits[0][0]})")
        return Result.ok(item, f"step {good[0]}: succeeded")
    return Result.ok(item, f"step {hits[0][0]}: openspec {hits[0][1][:60]}")


# --------------------------------------------------------------------------------------------
# openspec_ff.archive
# --------------------------------------------------------------------------------------------
_ARCHIVE_SUB = re.compile(r"^archive\b")


def archive_calls(ctx: EvalContext) -> list[tuple[int, str, str]]:
    return [(s, a, o) for s, _, a, o, _t in invocations(ctx) if _ARCHIVE_SUB.search(a)]


def _roots(ctx: EvalContext, specs) -> list[str]:
    roots = F.roots_of(ctx.rubric, ctx.collected.workdir)
    out = []
    for t in specs or []:
        s, left = F.expand(str(t), roots, ctx.collected.workdir, ctx.facts.var_bindings)
        if s.startswith("/") and not left:
            out.append(posixpath.normpath(s))
    return out


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path == d or path.startswith(d.rstrip("/") + "/") for d in prefixes)


ARCHIVE_RULES = ("succeeded", "retries", "after", "by_cli", "specs_only")


@register("openspec_ff.archive", params={"rule": True, "event": False, "roots": False, "allow": False}, availability=("trace",), common=False, choices={"rule": ARCHIVE_RULES})
def archive(item: Item, ctx: EvalContext) -> Result:
    """rule: succeeded | retries | after | by_cli | specs_only -- the ``openspec archive`` calls: one succeeded; at most one retry, only after a failure; the first after ``event``; no hand-made archive under ``roots``; after the first call only ``allow`` paths written."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    calls = archive_calls(ctx)
    if rule == "succeeded":
        good = [s for s, _, o in calls if _archive_ok(o)]
        if good:
            return Result.ok(item, f"archived at step {good[0]}")
        return Result.no(item, f"{len(calls)} archive call(s), none succeeded" if calls else "openspec archive never ran")
    if rule == "retries":
        if not calls:
            return Result.not_applicable(item, "openspec archive never ran")
        if len(calls) > 2:
            return Result.no(item, f"{len(calls)} archive calls (steps {[s for s, _, _ in calls][:6]})")
        if len(calls) == 2 and _archive_ok(calls[0][2]):
            return Result.no(item, f"archived at step {calls[0][0]} and called again at step {calls[1][0]}")
        return Result.ok(item, f"{len(calls)} archive call(s)")
    if rule == "after":
        if not calls:
            return Result.not_applicable(item, "openspec archive never ran")
        ev = refs.event(ctx, p.get("event") or "start")
        if ev is None or ev is UNKNOWN:
            return Result.no(item, f"first archive call at step {calls[0][0]}, {p.get('event')} {'unknown' if ev is UNKNOWN else 'never happened'}")
        return Result.ok(item, f"{p.get('event')} at step {ev}, archive at step {calls[0][0]}") if ev < calls[0][0] else Result.no(item, f"archive at step {calls[0][0]}, before {p.get('event')} (step {ev})")
    if rule == "by_cli":
        prefixes = _roots(ctx, p.get("roots"))
        if not prefixes:
            return Result.no(item, "roots unresolved")
        hits = [(e.step, e.op, path) for path, evs in ctx.facts.writes.items() if _under(path, prefixes) for e in evs if e.ok is not False]
        if hits:
            s, op, path = sorted(hits)[0]
            return Result.no(item, f"step {s}: {op} {path} by the agent, not the CLI")
        return Result.ok(item, "nothing written into the archive or the main specs by the trace")
    if rule == "specs_only":
        if not calls:
            return Result.not_applicable(item, "openspec archive never ran")
        first = calls[0][0]
        allow = _roots(ctx, p.get("allow"))
        hits = sorted((e.step, path) for path, evs in ctx.facts.writes.items() for e in evs if e.ok is not False and e.step > first and not _under(path, allow) and not path.startswith("/tmp/"))
        hits += sorted((e.step, e.path) for e in ctx.facts.repo_writes if e.ok is not False and e.step > first)
        if hits:
            return Result.no(item, f"step {hits[0][0]}: wrote {hits[0][1]} after the first archive call (step {first})")
        return Result.ok(item, f"after step {first} only the delta specs were written")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# openspec_ff.delta
# --------------------------------------------------------------------------------------------
@register("openspec_ff.delta", params={"rule": True, "change": False}, availability=("sandbox_file",), common=False, choices={"rule": ("added_only",)})
def delta(item: Item, ctx: EvalContext) -> Result:
    """rule ``added_only``: every delta section of every delta spec of the change is ``## ADDED Requirements`` (ratio over files)."""
    p = item.check.params or {}
    if str(p.get("rule")) != "added_only":
        return Result.no(item, f"unknown rule {p.get('rule')!r}")
    final, deltas = OS._deltas(ctx, str(p.get("change") or "change"))
    if final is None:
        return Result.no(item, "change directory absent")
    if not deltas:
        return Result.no(item, "no delta spec")
    good, bad = [], []
    for cap, _, text in deltas:
        ops = {op for _, op in OS.parse_spec(text).sections if op}
        (good if ops and ops <= {"ADDED"} else bad).append(cap)
    return OS._ratio(item, good, bad, "delta specs with ADDED sections only")


# --------------------------------------------------------------------------------------------
# openspec_ff.evidence
# --------------------------------------------------------------------------------------------
def check_dir(ctx: EvalContext, change: str = "/changes/issue") -> str:
    root = (ctx.rubric.roots or {}).get("artifact") or ""
    return posixpath.normpath(root + change) + "/checks/"


def written_checks(ctx: EvalContext, w=None) -> set[str]:
    """Normalised paths of the files the trace wrote under the change's checks/ directory (in the window)."""
    d = check_dir(ctx)
    wd = ctx.collected.workdir
    out = set()
    for path, evs in ctx.facts.writes.items():
        if path.startswith(d) and any(e.ok is not False and e.op not in ("delete", "move_out") and (w is None or refs.in_window(e.step, w)) for e in evs):
            out.add(refs.norm_path(path, wd))
    return out


@register("openspec_ff.evidence", params={"rule": True, "window": False}, availability=("trace",), common=False, choices={"rule": ("test_or_check",)})
def evidence(item: Item, ctx: EvalContext) -> Result:
    """rule ``test_or_check``: a valid repository test run, or the execution of a check script written under the change's checks/, in the window."""
    p = item.check.params or {}
    if str(p.get("rule")) != "test_or_check":
        return Result.no(item, f"unknown rule {p.get('rule')!r}")
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    runs = [r for r in ctx.facts.runs if r.kind == "test" and r.valid and refs.in_window(r.step, w)]
    if runs:
        return Result.ok(item, f"valid test run at step {runs[0].step}")
    scripts = written_checks(ctx)
    ran = sorted({path for step, path in F.executed_paths(ctx) if refs.in_window(step, w) and path in scripts})
    if ran:
        return Result.ok(item, f"ran {ran[0]}")
    return Result.no(item, f"no valid test run and no check script executed in {list(w)}")


# --------------------------------------------------------------------------------------------
# openspec_ff.tasks
# --------------------------------------------------------------------------------------------
def _content_events(ctx: EvalContext, aid: str) -> list:
    art = ctx.rubric.artifacts.get(aid)
    if art is None:
        return []
    evs = [e for path in F.location_paths(ctx.rubric, ctx.facts, ctx.collected, art) for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
    return sorted(evs, key=lambda e: (e.step, e.action_index))


_BOX = re.compile(r"^\s*[-*+]\s+\[([^\]]?)\s*([xX]?)\s*\]")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")


def open_without_reason(text: str | None) -> tuple[int, list[str]]:
    """(tasks, the open ones with no plain line under them): a reason is a non-empty line that is no checkbox and no
    heading, between the open task and the next checkbox or heading (02-apply.md:105)."""
    lines = (text or "")[:MAX_TEXT].split("\n")
    total, bad = 0, []
    for i, ln in enumerate(lines):
        m = _BOX.match(ln)
        if not m:
            continue
        total += 1
        if "x" in (m.group(1) + m.group(2)).lower():
            continue
        reason = False
        for nxt in lines[i + 1 : i + 20]:
            if _BOX.match(nxt) or _HEADING.match(nxt):
                break
            if nxt.strip() and not nxt.strip().startswith("<!--"):
                reason = True
                break
        if not reason:
            bad.append(ln.strip()[:60])
    return total, bad


@register("openspec_ff.tasks", params={"rule": True, "artifact": False, "window": False}, availability=("sandbox_file", "trace"), common=False, choices={"rule": ("written", "rerun_after_tick", "done_or_reasoned")})
def tasks(item: Item, ctx: EvalContext) -> Result:
    """rule: written | rerun_after_tick | done_or_reasoned -- the task list written in the window (any location); each ticking write followed by ``openspec instructions apply``; at the end each task ticked or with its one-line reason."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = str(p.get("artifact") or item.target.ref or "tasks")
    if rule == "done_or_reasoned":
        text = ctx.artifact_text(aid, "final")
        if text is None:
            return Result.no(item, "task list absent")
        total, bad = open_without_reason(text)
        if not total:
            return Result.no(item, "no checkbox task")
        return Result.ratio(item, total - len(bad), total, f"open without a reason: {bad[:2]}" if bad else f"{total} tasks done or reasoned")
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    evs = _content_events(ctx, aid)
    if rule == "written":
        inside = [e.step for e in evs if refs.in_window(e.step, w)]
        return Result.ok(item, f"written at step {inside[0]}") if inside else Result.no(item, f"{aid} not written in {list(w)}")
    if rule != "rerun_after_tick":
        return Result.no(item, f"unknown rule {rule!r}")
    ticks, prev = [], None
    for e in evs:
        if e.content is None:
            continue
        n = sum(1 for c, _ in OS._tasks(e.content) if c)
        if prev is not None and n > prev and refs.in_window(e.step, w):
            ticks.append(e.step)
        prev = n
    if not ticks:
        return Result.not_applicable(item, "no task ticked in the window")
    reruns = [s for s, _, a, _o, _t in invocations(ctx) if re.search(r"^instructions\s+apply\b", a)]
    good = 0
    for i, t in enumerate(ticks):
        nxt = ticks[i + 1] if i + 1 < len(ticks) else w[1]
        if any(t < s <= nxt for s in reruns):
            good += 1
    return Result.ratio(item, good, len(ticks), f"{good}/{len(ticks)} ticking writes followed by 'openspec instructions apply'")


# --------------------------------------------------------------------------------------------
# openspec_ff.verify
# --------------------------------------------------------------------------------------------
_CRIT = re.compile(r"(?i)\b(?:[1-9]\d*)\s+critical\s+issues?\b|\bcritical\s+issues?\s*(?:\(|:)\s*[1-9]")
_CRIT_ITEM = re.compile(r"(?im)^\s*[-*+]\s+(?:\*\*)?CRITICAL\b(?:\*\*)?\s*[:\-—]")


def lists_critical(text: str | None) -> bool:
    """The report lists a CRITICAL issue: "N critical issue(s)" with N >= 1, or a ``- CRITICAL:`` item."""
    t = (text or "")[:MAX_TEXT]
    return bool(_CRIT.search(t) or _CRIT_ITEM.search(t))


@register("openspec_ff.verify", params={"rule": True, "artifact": False, "tasks": False}, availability=("sandbox_file", "trace"), common=False, choices={"rule": ("open_tasks_critical",)})
def verify(item: Item, ctx: EvalContext) -> Result:
    """rule ``open_tasks_critical``: when the task list held an open box as the report was written, the report lists a CRITICAL issue."""
    p = item.check.params or {}
    if str(p.get("rule")) != "open_tasks_critical":
        return Result.no(item, f"unknown rule {p.get('rule')!r}")
    aid = str(p.get("artifact") or item.target.ref)
    text = ctx.artifact_text(aid, "final")
    if text is None:
        return Result.no(item, "report absent")
    at = refs.write_event(ctx, aid, "first")
    if at is None or at is UNKNOWN:
        return Result.not_applicable(item, "the report's write is not in the trace")
    evs = [e for e in _content_events(ctx, str(p.get("tasks") or "tasks")) if e.step <= at and e.content is not None]
    if not evs:
        return Result.not_applicable(item, "task list not in the trace before the report")
    open_ = [d for c, d in OS._tasks(evs[-1].content) if not c]
    if not open_:
        return Result.not_applicable(item, "every task ticked when the report was written")
    return Result.ok(item, f"{len(open_)} open task(s), CRITICAL listed") if lists_critical(text) else Result.no(item, f"{len(open_)} open task(s) ({open_[0][:40]!r}) and no CRITICAL issue")


# --------------------------------------------------------------------------------------------
# openspec_ff.created_files / no_fetch / holds (as speckit_bug's)
# --------------------------------------------------------------------------------------------
@register("openspec_ff.created_files", params={"pattern": False, "test_paths": False, "window": False}, availability=("trace",), common=False)
def created_files(item: Item, ctx: EvalContext) -> Result:
    """No file the run created in the repository (absent at BASE_SHA) is a test file (``test_paths``) or matches ``pattern``, written in the window."""
    from recipe.grpo.qwen3_5.workflow_rubric.facts import is_new_path, is_test_path

    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"])) if p.get("pattern") else None
    want_test = p.get("test_paths")
    hits = []
    for e in ctx.facts.repo_writes:
        if e.ok is False or not refs.in_window(e.step, w) or not is_new_path(ctx, e.path):
            continue
        if want_test is not None and is_test_path(e.path) != bool(want_test):
            continue
        if rx is not None and not rx.search(e.path):
            continue
        hits.append(f"step {e.step}: {e.op} {e.path}")
    return Result.no(item, f"{len(hits)} created: {hits[0]}") if hits else Result.ok(item, "none created")


_FETCH = re.compile(
    r"(?i)(?:\b(?:curl|wget|lynx|w3m|aria2c)\b[^\n|;&]*\bhttps?://"
    r"|\b(?:urlopen|urlretrieve|requests\.(?:get|post|head|request)|httpx\.(?:get|post|head|stream))\s*\(\s*[rbuf]?['\"]https?://"
    r"|\bgit\s+clone\b[^\n|;&]*\bhttps?://)"
)


@register("openspec_ff.no_fetch", params={"window": False}, availability=("trace",), common=False)
def no_fetch(item: Item, ctx: EvalContext) -> Result:
    """No command fetches a URL: curl / wget / a text browser on a URL, a Python urlopen / requests / httpx call on a URL literal, a git clone of a URL."""
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    for c in ctx.facts.commands:
        if refs.in_window(c.step, w) and _FETCH.search(c.command[:MAX_CMD] or ""):
            return Result.no(item, f"step {c.step}: {c.command.strip()[:60]}")
    return Result.ok(item, "no URL fetched")


@register("openspec_ff.paths_written", params={"pattern": True, "window": False}, availability=("trace",), common=False)
def paths_written(item: Item, ctx: EvalContext) -> Result:
    """No file the trace wrote (any tool, absolute path) matches ``pattern`` in the window: e.g. a script written to /tmp instead of the change's checks/."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"]))
    hits = sorted((e.step, path) for path, evs in ctx.facts.writes.items() if rx.search(path) for e in evs if e.ok is not False and e.op not in ("delete", "move_out") and refs.in_window(e.step, w))
    return Result.no(item, f"step {hits[0][0]}: wrote {hits[0][1]}") if hits else Result.ok(item, "no such file written")


@register("openspec_ff.note", params={"patterns": True, "window": False}, availability=("trace",), common=False)
def note(item: Item, ctx: EvalContext) -> Result:
    """One tool call in the window holds every pattern of ``patterns`` (regexes over the call's own text: a ``think``
    thought, a command as typed, the text a write puts in a file); the window's end step counts too."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    try:
        rxs = [re.compile(str(x)) for x in (p.get("patterns") or [])]
    except re.error as e:
        return Result.no(item, f"bad pattern: {e}")
    if not rxs:
        return Result.no(item, "no pattern")
    a, b = w
    best = 0
    for st in ctx.run.steps:
        if st.n < a or (b is not None and st.n > b):
            continue
        for act in st.actions:
            text = "\n".join(x for x in (act.text, act.command) if isinstance(x, str) and x)[:MAX_TEXT]
            if not text:
                continue
            n = sum(1 for rx in rxs if rx.search(text))
            if n == len(rxs):
                return Result.ok(item, f"step {st.n}: {act.name or act.kind}")
            best = max(best, n)
    return Result.no(item, f"no tool call in the window holds the note ({best}/{len(rxs)} parts at best)")


@register("openspec_ff.holds", params={"predicate": True}, availability=("trace", "sandbox_file"), common=False)
def holds(item: Item, ctx: EvalContext) -> Result:
    """The refs predicate holds for the run (``artifact_exists`` / ``field_matches`` / ``relation`` / ``all`` ...)."""
    pred = (item.check.params or {}).get("predicate")
    return Result.ok(item, "holds") if refs.predicate(ctx, pred) else Result.no(item, "does not hold")


__all__ = ["cli", "archive", "delta", "evidence", "tasks", "verify", "created_files", "no_fetch", "holds", "paths_written", "note", "invocations", "succeeded", "lists_critical", "archive_calls", "open_without_reason"]
