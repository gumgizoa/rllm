"""How every workflow's scorer reads its test behaviour: one function per rule of the 2026-11-24 review
(tasks/2026-11-24-test-reading-consistency/통일-검토.md, rules R1-R7). The workflows keep only what their documents
make different -- which runs are the baseline, which tests are their own -- and pass it in.

R1  the code change is a write to an application source file of the repository (:func:`change_steps`,
    :func:`change_writes`: ``facts.is_change_write``), whether or not the final change keeps it (a reverted edit was a
    modification; 11-25 merge with aidlc's reading, D1). A test file, the run's own scripts and helper files (a new
    ``settings.py`` at the root, a helper app ``test_app/``), files outside the repository, removing a scratch or
    regenerated file and git putting content back are no change. A test of the run's own is held to its own writes
    instead (R4).
R2  where a test run and a write share one shell call, their order in the command's text decides: ``sed -i ... &&
    pytest`` runs after the write, ``pytest ...; sed -i ...`` before it (:class:`Mark`, :func:`after`, :func:`before`).
    A script run that itself edits the source is the change: neither before nor after it (:func:`write_mark`).
R3  a run while the change is put away -- ``git stash`` .. ``pop`` / ``apply``, a ``git checkout`` / ``restore`` of an
    edited file, ``git apply -R`` / ``patch -R`` -- is a run of the unchanged code, not of the change
    (:func:`stashed`, :func:`change_runs`, :func:`stash_runs`, :func:`script_runs`).
R4  a script of the run's own is read by ``results.executions`` / ``results.outcome``; its result counts only from a run
    after its last write before that point (:func:`current_runs`, :func:`last_result`). A run of it is one that opened
    its file under any path it has had (:func:`script_history`): by an interpreter, a ``python -c`` import, a runner
    given the file or a dotted label naming it; a run that never started (no such file, a runner that died before
    loading it) is none. Its result: a failure verdict line over an exit code of 0, a hidden exit code read by the
    output's verdict and summary lines, a runner's by that file's own test lines or its summary, an unfinished run
    failed only by a failure already printed (D2 of the 11-25 merge with aidlc's reading).
R5  failing tests are named by ``evidence.failing_ids`` (``results.run_failed_ids``: all of them or none); a failure
    whose name cannot be matched on both sides counts as new (:func:`same_test`, :func:`new_failures`).
R6  a test that fails after the change was already failing when, in the last baseline run that ran it, it failed by
    name (:func:`preexisting`). Which runs are baseline runs is the workflow's (its documents say).
R7  the existing tests of the changed code ran: a valid run after the change that targets a test file related to a
    changed source file (``Collected.related_tests``, read from the sandbox) or runs the whole suite
    (:func:`related_run`).

Nothing the agent writes can make these raise.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import evidence as E
from . import facts as F
from . import refs
from . import results as R
from .context import EvalContext
from .trace import shell


# --------------------------------------------------------------------------------------------
# R1: the code change
# --------------------------------------------------------------------------------------------
def change_writes(ctx: EvalContext) -> list:
    """The repository writes that are source changes (``facts.source_change_steps`` counts their steps), in order."""
    key = "testread.change_writes"
    if key not in ctx.cache:
        evs = [e for e in ctx.facts.repo_writes if F.is_change_write(ctx, e)]
        ctx.cache[key] = sorted(evs, key=lambda e: (int(e.step), e.action_index))
    return ctx.cache[key]


def git_put_back(ctx: EvalContext, e) -> bool:
    """The repository write ``e`` is git putting content back, not a write the agent authored (R1): a ``git checkout`` /
    ``git restore`` of a path (op ``restore``), or a write of no known content (op ``unknown``) made by a call that runs
    git (``git stash`` / ``pop`` / ``apply``, ``git checkout .``, ``reset --hard``). An ``unknown`` write of any other
    call (``xargs sed -i``, a patch that cannot be read) is the agent's."""
    if e.op == "restore":
        return True
    if e.op != "unknown":
        return False
    cmd = _command(ctx, int(e.step), e.action_index)
    if not cmd:
        return False
    try:
        segs = shell.flat(shell.split(cmd, ctx.collected.workdir)[0])
    except Exception:  # noqa: BLE001 -- agent text
        return False
    return any(s.verb == "git" for s in segs)


def change_steps(ctx: EvalContext) -> list[int]:
    """Steps of the source changes (R1): ``facts.source_change_steps``."""
    return F.source_change_steps(ctx)


# --------------------------------------------------------------------------------------------
# R2: order inside one call
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Mark:
    """Where something happened: its step, its action in the step, and (a shell call) its place in the command's text
    (None: the call holds it but where cannot be told)."""

    step: int
    action: int = 0
    pos: int | None = 0


def _command(ctx: EvalContext, step: int, action: int) -> str | None:
    """The shell command of action ``action`` of step ``step``; None for an action that is no shell call."""
    key = "testread.commands"
    if key not in ctx.cache:
        ctx.cache[key] = {(int(c.step), c.action_index): c.command or "" for c in getattr(ctx.facts, "commands", None) or []}
    return ctx.cache[key].get((int(step), action))


def _find(cmd: str, what: str) -> int | None:
    i = cmd.find(what) if what else -1
    return i if i >= 0 else None


def _script_write_pos(ctx: EvalContext, cmd: str, step: int, action: int, path: str) -> int | None:
    """Where in ``cmd`` the python run that wrote ``path`` (absolute) starts: the segment whose code writes it
    (``python3 fix.py`` after ``cat > fix.py <<EOF ...``, ``python - <<EOF``), else the call's only python segment; None
    when that cannot be told. The run of a script that edits the source is the change itself (R1 / R2): its mark is the
    run's own place, so a run of that script in the call is neither before nor after it, and a run later in the text
    is after it. The text of a heredoc body is no order of execution."""
    cwd = next((c.cwd for c in getattr(ctx.facts, "commands", None) or [] if int(c.step) == step and c.action_index == action), None)
    try:
        segs = shell.split(cmd[: R.MAX_CMD], cwd)[0]
        ops = shell.write_ops(cmd[: R.MAX_CMD], cwd)
    except Exception:  # noqa: BLE001 -- agent text
        return None
    py = [k for k, s in enumerate(segs) if s.verb and R._INTERPRETER.search(s.verb)]
    own = [op.seg for op in ops if op.source == "python" and posixpath.normpath(op.path or "") == path and 0 <= op.seg < len(segs)]
    k = own[0] if own else (py[0] if len(py) == 1 else None)
    return None if k is None else _find(cmd, segs[k].text or "")


def write_mark(ctx: EvalContext, e) -> Mark:
    """The mark of repository write ``e`` (repo-relative path): in a shell call, where its path first appears in the
    command (absolute, else relative); a write a python script made when it ran, where that run starts
    (:func:`_script_write_pos`); an editor write is its whole action."""
    cmd = _command(ctx, int(e.step), e.action_index)
    if cmd is None:
        return Mark(int(e.step), e.action_index, 0)
    wd = (ctx.collected.workdir or "").rstrip("/")
    path = e.path if e.path.startswith("/") else (wd + "/" + e.path if wd else e.path)
    if e.source == "python":
        return Mark(int(e.step), e.action_index, _script_write_pos(ctx, cmd, int(e.step), e.action_index, path))
    pos = _find(cmd, path)
    return Mark(int(e.step), e.action_index, pos if pos is not None else _find(cmd, e.path))


def path_write_mark(ctx: EvalContext, path: str, e) -> Mark:
    """The mark of a write ``e`` of an absolute path (a check script outside the repository)."""
    cmd = _command(ctx, int(e.step), e.action_index)
    if cmd is None:
        return Mark(int(e.step), e.action_index, 0)
    return Mark(int(e.step), e.action_index, _find(cmd, path) if _find(cmd, path) is not None else _find(cmd, posixpath.basename(path)))


def run_mark(r: Any) -> Mark:
    """The mark of a runner run (``RunFact``): its segment's place in its command."""
    cmd = r.command or ""
    return Mark(int(r.step), r.action_index, _find(cmd, r.segment or "") if r.segment else None)


def after(m: Mark, w: Mark) -> bool:
    """``m`` comes after ``w``: a later step or action, or later in the same call's text (an unknown place: not after)."""
    if (m.step, m.action) != (w.step, w.action):
        return (m.step, m.action) > (w.step, w.action)
    return m.pos is not None and w.pos is not None and w.pos < m.pos


def before(m: Mark, w: Mark) -> bool:
    """``m`` comes before ``w`` (the mirror of :func:`after`; an unknown place: not before)."""
    if (m.step, m.action) != (w.step, w.action):
        return (m.step, m.action) < (w.step, w.action)
    return m.pos is not None and w.pos is not None and m.pos < w.pos


def after_all(m: Mark, writes: Iterable[Mark]) -> bool:
    return all(after(m, w) for w in writes)


def before_all(m: Mark, writes: Iterable[Mark]) -> bool:
    return all(before(m, w) for w in writes)


def change_marks(ctx: EvalContext, w=None) -> list[Mark]:
    """The marks of the source changes (R1), in the step window ``w`` when given."""
    return [write_mark(ctx, e) for e in change_writes(ctx) if w is None or refs.in_window(e.step, w)]


def after_change(ctx: EvalContext, m: Mark, w=None, upto: int | None = None) -> bool:
    """``m`` comes after every source change (of the window ``w``, at or before step ``upto``)."""
    return after_all(m, [c for c in change_marks(ctx, w) if upto is None or c.step <= upto])


def before_change(ctx: EvalContext, m: Mark, w=None) -> bool:
    """``m`` comes before every source change (of the window ``w``)."""
    return before_all(m, change_marks(ctx, w))


def in_step_window(ctx: EvalContext, m: Mark, w) -> bool:
    """Mark ``m`` lies in the step window ``w`` (``refs.window``: [a, b)), its bounds read by R2: at the window's first
    step only after the source changes made there, at its (open) end step only before the source changes made there
    (``sed -i ... && pytest`` runs after the change, ``pytest ...; sed -i ...`` before it)."""
    if w is None:
        return False
    if refs.in_window(m.step, w):
        return m.step != w[0] or after_all(m, [c for c in change_marks(ctx) if c.step == w[0]])
    if w[1] is not None and m.step == w[1]:
        at = [c for c in change_marks(ctx) if c.step == w[1]]
        return bool(at) and before_all(m, at)
    return False


# --------------------------------------------------------------------------------------------
# R3: the change put away
# --------------------------------------------------------------------------------------------
def edited_files(ctx: EvalContext) -> set[str]:
    """Repository files other than tests the run edited itself (not git putting content back): the files a
    ``git checkout`` / ``git restore`` can put the change of away."""
    return {e.path for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_test_path(e.path) and not F.is_generated(e.path)}


def authored_steps(ctx: EvalContext) -> list[int]:
    """Steps of the repository writes the run authored (not git putting content back, not run byproducts): what ends a
    put-away change that was never brought back."""
    return sorted({int(e.step) for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_generated(e.path)})


def _stash_view(ctx: EvalContext) -> tuple[dict, dict]:
    key = "testread.stash"
    if key not in ctx.cache:
        ctx.cache[key] = R.stash_states(ctx.facts.commands, authored_steps(ctx), edited_files(ctx))
    return ctx.cache[key]


def stashed(ctx: EvalContext, step: int, action: int, segment: str | None, command: str | None = None) -> bool:
    """The run of ``segment`` (in the call at ``step`` / ``action``) ran with the change put away (R3)."""
    before_, marks = _stash_view(ctx)
    r = _At(int(step), action, command if command is not None else (_command(ctx, step, action) or ""), segment or "")
    return R.run_stashed(r, before_, marks)


@dataclass
class _At:
    step: int
    action_index: int
    command: str
    segment: str


def stash_flags(command: str, segments: list[str], away: bool = False) -> tuple[list[bool], bool]:
    """For a scorer that reads a command as plain segments (aidlc): per segment, whether the change is put away when it
    runs, by the shared marks (``results.stash_marks``: ``git stash`` .. ``pop`` / ``apply``, ``git apply -R`` /
    ``patch -R`` and back), starting from ``away``; and the state after the command. A segment's place is found in the
    command's text in order."""
    marks = R.stash_marks(command or "")
    flags, at = [], 0
    for seg in segments:
        i = (command or "").find(seg, at)
        pos = i if i >= 0 else at
        state = away
        for mp, on in marks:
            if mp < pos:
                state = on
        flags.append(state)
        at = pos + max(len(seg), 1) if i >= 0 else at
    return flags, (marks[-1][1] if marks else away)


def run_stashed(ctx: EvalContext, r: Any) -> bool:
    """The runner run ``r`` ran with the change put away."""
    return stashed(ctx, r.step, r.action_index, r.segment, r.command)


def change_runs(ctx: EvalContext) -> list:
    """The valid test runs made with the change in place (R3), in order."""
    key = "testread.change_runs"
    if key not in ctx.cache:
        ctx.cache[key] = [r for r in ctx.facts.runs if r.valid and r.kind == "test" and not run_stashed(ctx, r)]
    return ctx.cache[key]


def stash_runs(ctx: EvalContext) -> list:
    """The valid test runs made with the change put away (the complement of :func:`change_runs`)."""
    key = "testread.stash_runs"
    if key not in ctx.cache:
        ctx.cache[key] = [r for r in ctx.facts.runs if r.valid and r.kind == "test" and run_stashed(ctx, r)]
    return ctx.cache[key]


# --------------------------------------------------------------------------------------------
# R4: a script of the run's own
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ScriptRun:
    """One run of a script of the run's own: where, how it came out (``pass`` / ``fail`` / None), and whether the
    change was put away while it ran."""

    mark: Mark
    outcome: str | None
    stashed: bool = False

    @property
    def step(self) -> int:
        return self.mark.step


def script_runs(ctx: EvalContext, paths: set[str], keep_stashed: bool = False) -> dict[str, list[ScriptRun]]:
    """Absolute path -> every run of it, in order (``results.executions`` / ``results.outcome``, R4), with its mark; a
    run with the change put away (R3) left out unless ``keep_stashed``."""
    out: dict[str, list[ScriptRun]] = {p: [] for p in paths}
    if not paths:
        return out
    for c in ctx.facts.commands:
        segs = R.segments(ctx, c)
        cmd = c.command or ""
        for i, seg in enumerate(segs):
            hit = R.executed_by(seg) & paths
            if not hit:
                continue
            m = Mark(int(c.step), c.action_index, _find(cmd, seg.text or ""))
            away = stashed(ctx, c.step, c.action_index, seg.text, cmd)
            if away and not keep_stashed:
                continue
            last = c.step >= ctx.facts.n_steps  # the final call's observation is empty
            for p in sorted(hit):
                if not last and not R.started(segs, i, c.observation or "", p, cmd):
                    continue  # the file was not there, or the runner died before loading it: no run
                out[p].append(ScriptRun(m, None if last else R.outcome(segs, i, c.observation or "", cmd, p), away))
    return out


def _moves(ctx: EvalContext) -> list[tuple[str, str]]:
    """(source, destination) of every move the trace shows (``mv old new``): a ``move_out`` and a ``move_in`` of one
    call, paired one to one or by file name."""
    key = "testread.moves"
    if key not in ctx.cache:
        calls: dict[tuple[int, int], tuple[list[str], list[str]]] = {}
        for path, evs in (getattr(ctx.facts, "writes", None) or {}).items():
            for e in evs:
                if e.op in ("move_out", "move_in") and e.ok is not False:
                    calls.setdefault((int(e.step), e.action_index), ([], []))[e.op == "move_in"].append(path)
        out = []
        for srcs, dsts in calls.values():
            if len(srcs) == 1 and len(dsts) == 1:
                out.append((srcs[0], dsts[0]))
            else:
                out += [(a, b) for a in srcs for b in dsts if posixpath.basename(a) == posixpath.basename(b)]
        ctx.cache[key] = out
    return ctx.cache[key]


def script_history(ctx: EvalContext, recorded: Iterable[str]) -> set[str]:
    """Every absolute path a script of the run's own has had (D2 of the 11-25 merge): each path recorded for it (read
    against the repository root; a bare file name also names every file of that name the run wrote) and, through every
    move of one of them (``mv old new``), both ends. A run of the script under any of them is a run of it (a script
    moved into the test tree, an artifact that recorded the path the script had then)."""
    wd = ctx.collected.workdir or "/"
    written = set(getattr(ctx.facts, "writes", None) or {})
    out: set[str] = set()
    for p in recorded:
        p = (p or "").strip()
        if not p:
            continue
        if "/" not in p:
            out |= {w for w in written if posixpath.basename(w) == p}
        out.add(posixpath.normpath(p if p.startswith("/") else posixpath.join(wd, p)))
    grew = True
    while grew:
        grew = False
        for a, b in _moves(ctx):
            if (a in out) != (b in out):
                out |= {a, b}
                grew = True
    return out


def own_writes(ctx: EvalContext, path: str) -> list[Mark]:
    """The marks of the content writes of a test of the run's own: an absolute path (a check script), or a repository
    test file (repo-relative)."""
    if path.startswith("/"):
        return [path_write_mark(ctx, path, e) for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
    return [write_mark(ctx, e) for e in ctx.facts.repo_writes if e.path == path and e.ok is not False and e.op != "unknown"]


def current(m: Mark, writes: list[Mark], upto: Mark | None = None) -> bool:
    """A run at ``m`` ran the version of the test that stood last -- of every write, or of those before ``upto``: it
    comes after each of them (R4)."""
    return after_all(m, [w for w in writes if upto is None or before(w, upto)])


def current_runs(runs: list[ScriptRun], writes: list[Mark]) -> list[ScriptRun]:
    """The runs of a test of the run's own made after its last write (R4): the results of the test as it stands."""
    return [r for r in runs if current(r.mark, writes)]


def last_result(runs: list[ScriptRun], writes: list[Mark]) -> ScriptRun | None:
    """The last run of the test as it stands (:func:`current_runs`), None when it never ran after its last write."""
    cur = current_runs(runs, writes)
    return cur[-1] if cur else None


# --------------------------------------------------------------------------------------------
# R5 / R6: failing tests and the baseline
# --------------------------------------------------------------------------------------------
_PARAM = re.compile(r"^(?P<base>[^\[]*)(?P<param>\[.*\])?$", re.S)
Name = tuple[tuple[str, ...], str]


def name_of(tid: str) -> Name:
    """One name for a test however a runner printed it: ``tests/test_io.py::TestA::test_x``, the pytest section
    ``TestA.test_x`` and unittest's ``tests.test_io.TestA.test_x`` are all ``(("tests", "test_io"), "TestA.test_x")``
    (the section form, which names no file, has an empty module)."""
    m = _PARAM.match((tid or "").strip())
    base, param = (m.group("base"), m.group("param") or "") if m else ((tid or "").strip(), "")
    if "::" in base:
        head, *rest = base.split("::")
        mod = [c for c in (head[:-3] if head.endswith(".py") else head).split("/") if c and c != "."]
    else:
        rest = base.split(".")
        mod, rest = rest[:-2], rest[-2:]
    return tuple(mod), ".".join(rest[-2:]) + param


def same_test(a: str, b: str) -> bool:
    """Two printed test ids name the same test: the same name, in the same module where both name one (one path may
    be the tail of the other)."""
    x, y = name_of(a), name_of(b)
    if x[1] != y[1]:
        return False
    n = min(len(x[0]), len(y[0]))
    return n == 0 or x[0][-n:] == y[0][-n:]


def failed_names(r: Any) -> tuple[str, ...] | None:
    """The tests a valid runner run failed, by name, when its output names every one of them (R5); () for a run with
    no failure; None when it fails tests it does not name."""
    n = int(r.failed or 0) + int(r.errors or 0)
    if n <= 0:
        return ()
    ids = R.run_failed_ids(int(r.failed or 0), int(r.errors or 0), r.observation or "")
    return ids or None


def as_result(ctx: EvalContext, r: Any) -> R.TestResult:
    """A valid runner run as a :class:`results.TestResult`: its files (``WHOLE`` for the whole suite), what narrows it,
    and the ids of its failed tests when its output names them all."""
    files = R.run_files(r, ctx.collected.workdir)
    whole = whole_suite(ctx, r)
    n_failed, n_errors = int(r.failed or 0), int(r.errors or 0)
    keys = files if files and not whole else (R.WHOLE,)
    return R.TestResult(int(r.step), not (n_failed + n_errors), True, keys, R.selection(r.segment), R.run_failed_ids(n_failed, n_errors, r.observation or ""))


def ran_test(b: R.TestResult, tid: str) -> bool:
    """Baseline result ``b`` ran test ``tid``: it names the test among its failures, or its targets and selection cover
    the test (``results.runs_test``)."""
    if any(same_test(tid, i) for i in b.failed_ids):
        return True
    try:
        return bool(b.runner) and R.runs_test(b, tid)
    except Exception:  # noqa: BLE001 -- agent text
        return False


def preexisting(tid: str, baselines: list[R.TestResult]) -> bool:
    """Test ``tid`` (failing after the change) was already failing (R6): in the last baseline result that ran it, it
    failed by name. A baseline run that failed without naming its failures names nothing (R5)."""
    last = None
    for b in sorted(baselines, key=lambda x: x.step):
        if ran_test(b, tid):
            last = b
    return last is not None and not last.passed and any(same_test(tid, i) for i in last.failed_ids)


def new_failures(names: tuple[str, ...] | None, baselines: list[R.TestResult]) -> list[str] | None:
    """The failures of a run after the change that the baseline does not explain (R5 / R6): ``names`` are the run's
    failed tests (:func:`failed_names`). None when the run fails tests it does not name -- every failure of it is new."""
    if names is None:
        return None
    return [t for t in names if not preexisting(t, baselines)]


# --------------------------------------------------------------------------------------------
# R7: the existing tests of the changed code
# --------------------------------------------------------------------------------------------
def whole_suite(ctx: EvalContext, r: Any) -> bool:
    """The runner run is of the whole suite (``evidence.full_suite``: a runner at the repository root that selects
    nothing), its command split from the directory it started in."""
    wd = ctx.collected.workdir
    start = getattr(ctx.facts, "_cwd_track", {}).get((getattr(r, "step", None), getattr(r, "action_index", None)))
    try:
        segs = shell.flat(shell.split(r.command or r.segment, start or wd)[0])
    except Exception:  # noqa: BLE001
        return False
    want = (r.segment or "").strip()
    return any(E.full_suite(s, wd) for s in segs if not want or (s.text or "").strip() == want)


def _rel(path: str, workdir: str | None) -> str:
    if workdir and path.startswith(workdir.rstrip("/") + "/"):
        return path[len(workdir.rstrip("/")) + 1 :]
    return path


def mentions_test_file(r: Any, path: str, workdir: str | None) -> bool:
    """The run targeted ``path`` (repo-relative test file): the path or its stem in the command / targets / ids, or for
    Django's runner the dotted label of the module (``tests/forms_tests/tests/test_forms.py`` -> ``forms_tests``...)."""
    text = " ".join([r.command or "", *(r.targets or []), *(r.ids or [])])
    rel = _rel(path, workdir)
    if rel in text or ("/" + rel) in text:
        return True
    stem = posixpath.splitext(posixpath.basename(rel))[0]
    if stem not in ("tests", "test", "__init__") and re.search(r"(?<![\w/])" + re.escape(stem) + r"(?![\w])", text):
        return True
    if re.search(r"runtests\.py|manage\.py\s+test", r.command or ""):
        parts = [x for x in rel.split("/")[:-1] if x not in ("tests", "test", "testing")]
        label = ".".join(parts + [stem])
        if parts and re.search(r"(?<![\w.])" + re.escape(parts[0]) + r"(?![\w])", r.command or ""):
            return True
        if label and label in (r.command or ""):
            return True
    return False


def targets_dir_of(r: Any, path: str, workdir: str | None) -> bool:
    """The run's target is a directory holding ``path`` (``pytest tests/queries``, ``pytest tests/``)."""
    rel = _rel(path, workdir)
    for t in r.targets or []:
        t = _rel(t.strip(), workdir).lstrip("./").rstrip("/")
        if t and not posixpath.splitext(t)[1] and rel.startswith(t + "/"):
            return True
    return False


def related_tests(ctx: EvalContext) -> list[str] | None:
    """The repository test files related to the changed source files (``Collected.related_tests``); None when not
    collected (offline, or the sandbox step failed)."""
    rel = ctx.collected.related_tests
    if rel is None:
        return None
    return sorted({t for ts in rel.values() for t in ts})


def runs_related(ctx: EvalContext, r: Any, tests: list[str]) -> bool:
    """The valid run ``r`` ran tests of the changed code: the whole suite, or a target naming one of ``tests`` (the file,
    its stem, a directory holding it, Django's label)."""
    wd = ctx.collected.workdir
    return whole_suite(ctx, r) or any(mentions_test_file(r, t, wd) or targets_dir_of(r, t, wd) for t in tests)


def related_run(ctx: EvalContext, runs: list) -> tuple[str, Any]:
    """R7 over ``runs`` (valid runs already chosen by when they ran): ``("unavailable", None)`` when the related tests
    were not collected; ``("none", None)`` when the repository has no test related to the change; ``("hit", run)`` for
    the first run that ran tests of the changed code; ``("miss", None)`` otherwise."""
    tests = related_tests(ctx)
    if tests is None:
        return "unavailable", None
    if not tests:
        return "none", None
    for r in runs:
        if runs_related(ctx, r, tests):
            return "hit", r
    return "miss", None


__all__ = [
    "Mark",
    "Name",
    "ScriptRun",
    "after",
    "after_all",
    "after_change",
    "as_result",
    "authored_steps",
    "before",
    "before_all",
    "before_change",
    "change_marks",
    "change_runs",
    "change_steps",
    "change_writes",
    "current",
    "current_runs",
    "edited_files",
    "failed_names",
    "git_put_back",
    "in_step_window",
    "last_result",
    "mentions_test_file",
    "name_of",
    "new_failures",
    "own_writes",
    "path_write_mark",
    "preexisting",
    "ran_test",
    "related_run",
    "related_tests",
    "run_mark",
    "run_stashed",
    "runs_related",
    "same_test",
    "script_history",
    "script_runs",
    "stash_flags",
    "stash_runs",
    "stashed",
    "targets_dir_of",
    "whole_suite",
    "write_mark",
]
