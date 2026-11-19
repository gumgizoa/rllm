"""agentos_bugfix penalty items: the test behaviour of implement-tasks, in PHASE 2 and in PHASE 3.

Seven items, each 1.0 (no penalty) or 0.0 (penalty), reported with the items of ``penalty.py``. Every run gets all
seven: an item about a failure is 1.0 for a run that saw none (nothing to penalise), an item about running the tests
is 0.0 for a run that never got to the stretch it reads. ``penalty_applies.<item>`` says which of the two it was.

PHASE 2 -- from the first source change to the start of PHASE 3 (every task ticked; without that, the report's first
write; without either, the end of the run)

    agentos_bugfix.implement_tasks.penalty.phase2_run.existing_and_own
        1.0: after the last source change the run has a valid runner run of the repository's tests AND a run of a
             test of its own (a script under checks/, or the runner on a test file it wrote to -- named by its path,
             a directory above it or a dotted label of it, ``utils_tests.test_duration``). One runner run of an
             existing test module the run added tests to is both -- when it comes after the run's first write to that
             module. A run without the change (see the cause check below) is neither
        does not apply (0.0): the run changed no source in PHASE 2
    agentos_bugfix.implement_tasks.penalty.phase2_fail.edited_after_fail
        applies: a failing result after the first source change (else 1.0)
        1.0: per task group -- PHASE 2 is cut where a task group becomes fully ticked; in every stretch that holds a
             failing result, source or a test is edited after the stretch's last failing result and before its tick.
             A run that ticks everything in one write has one stretch
    agentos_bugfix.implement_tasks.penalty.phase2_fail.last_result_pass
        applies: a failing result after the first source change (else 1.0)
        1.0: every test that failed passes at its own last run (a script by its path, a runner run by each target
             it names; a later run of a directory or dotted label above the target, or of the whole suite, is a run
             of that target)

PHASE 3 -- from the write that ticks the last task to the report's first write; it can be placed only when both are
known and in that order

    agentos_bugfix.implement_tasks.penalty.phase3_run.existing_and_own
        1.0: as phase2_run, anywhere in PHASE 3
        does not apply (0.0): PHASE 3 cannot be placed
    agentos_bugfix.implement_tasks.penalty.phase3_fail.cause_checked
        applies: a valid runner run fails in PHASE 3 -- the document asks for the check on an existing test (else 1.0)
        1.0: after that failure and before the report, the runner is invoked with the change stashed away
    agentos_bugfix.implement_tasks.penalty.phase3_fail.edited_after_fail
        applies: a failing result in PHASE 3 that the document says to fix -- only tests of the run's own failed (no
                 runner failure), or the runner passed with the change stashed away (the change causes it). A failure
                 the check showed to exist without the change, or one that was never checked, is not this item's
                 (else 1.0)
        1.0: source or a test is edited after the first failing result, before the report
    agentos_bugfix.implement_tasks.penalty.phase3_fail.last_result_pass
        applies: a failing result in PHASE 3 (else 1.0)
        1.0: the last result before the report passes

A result is a run whose outcome can be read: a script the run wrote (under checks/ or anywhere else) that ran, or a
valid runner run. Two kinds of run are not results:

    the cause check   a runner run while the change is stashed away -- from a ``git stash`` (push) to the next
                      ``git stash pop`` / ``apply``, in one command or over several, or to the run's next edit when
                      the stash is never popped (the change is gone; what follows is a new one). ``git stash list`` /
                      ``show`` / ``drop`` stash nothing away, nor does a ``git stash`` with nothing to save
    a fix script      a script outside checks/ that changes the repository when it runs (it applies an edit; it is no
                      test). Writing it is no test edit either

A source change is a write to a non-test file of the final change -- a new file with a throwaway name (``repro_x.py``,
``check_fix.py``) counts as a script only at the repository root or when the final change does not keep it. A test
edit is a write to a repository test file or to one of the run's scripts. Nothing here reads the task's reference fix
or its test patch: every item is about what the run can know.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Any

from ....workflow_rubric import facts as F
from ....workflow_rubric import refs
from ....workflow_rubric.context import UNKNOWN
from ...agentos_v2.reward import checks as C

STAGE = "agentos_bugfix.implement_tasks.penalty"
P2_RUN = f"{STAGE}.phase2_run.existing_and_own"
P2_EDITED = f"{STAGE}.phase2_fail.edited_after_fail"
P2_LAST = f"{STAGE}.phase2_fail.last_result_pass"
P3_RUN = f"{STAGE}.phase3_run.existing_and_own"
P3_CAUSE = f"{STAGE}.phase3_fail.cause_checked"
P3_EDITED = f"{STAGE}.phase3_fail.edited_after_fail"
P3_LAST = f"{STAGE}.phase3_fail.last_result_pass"
# item -> what a run outside its pool scores: a run item 0.0 (it never got there), a failure item 1.0 (nothing to penalise)
OUTSIDE = {P2_RUN: 0.0, P2_EDITED: 1.0, P2_LAST: 1.0, P3_RUN: 0.0, P3_CAUSE: 1.0, P3_EDITED: 1.0, P3_LAST: 1.0}
ITEMS = tuple(OUTSIDE)

_SCRATCH_NAME = re.compile(r"(?i)(?:^|/)(?:repro|reproduce|reproduction|debug|scratch|tmp|temp|check|verify|test|try|demo|example)[^/]*\.(?:py|sh)$")
_STASH = re.compile(r"\bgit\s+stash\b(?:[ \t]+(?:-\S+[ \t]+)*([a-z]+)\b)?")
_STASH_BACK = frozenset({"pop", "apply"})
_STASH_NOTHING = frozenset({"list", "show", "drop", "clear", "branch", "create", "store"})
_WRITES_FILES = re.compile(r"\.write\(|write_text\(|writelines\(|\bsed\s+-i\b|\bpatch\s")
_WHOLE = "*"  # the key of a runner run that names no file


@dataclass
class Result:
    """One readable test result."""

    step: int
    passed: bool
    runner: bool  # a valid runner run; else a script of the run's own
    keys: tuple[str, ...]  # the script's path, or the test files the runner run names (``_WHOLE`` when none)


@dataclass
class Timeline:
    """What the items read, in steps."""

    src: list[int] = field(default_factory=list)  # source changes
    test_edits: list[int] = field(default_factory=list)  # writes to test files and to the run's scripts
    results: list[Result] = field(default_factory=list)  # readable results; cause checks and fix scripts aside
    stash_results: list[Result] = field(default_factory=list)  # valid runner runs with the change stashed away
    check_runs: list[int] = field(default_factory=list)  # runner invocations with the change stashed away, valid or not
    own_runs: list[int] = field(default_factory=list)  # a checks/ script ran (read or not), or the runner on an own test file
    existing_runs: list[int] = field(default_factory=list)  # valid runner runs of the repository's tests, with the change in place
    group_ends: list[int] = field(default_factory=list)  # steps at which a task group becomes fully ticked
    p2_end: int = 0
    p3: int | None = None  # PHASE 3 start, when it can be placed before the report
    report: int | None = None


def _int(v) -> int | None:
    return None if v is None or v is UNKNOWN else int(v)


def selects(target: str, file: str) -> bool:
    """A runner target selects repository test file ``file``: the file or a test in it, a directory above it, or a
    dotted label of it -- its module (``utils_tests.test_duration``), a class or test in the module, or a package above
    it (``utils_tests``), with or without the leading directories of the path."""
    t = target.split("::")[0].rstrip("/")
    if not t:
        return False
    if "/" in t or t.endswith(".py"):
        return t == file or file.startswith(t + "/")
    stem = file[:-3] if file.endswith(".py") else file
    parts = t.split(".")
    for n in range(len(parts), 0, -1):
        c = "/".join(parts[:n])
        if stem == c or stem.endswith("/" + c):
            return True
        if n == len(parts) and ("/" + c + "/") in ("/" + stem):  # a package label: every module under it
            return True
    return False


def _parts(target: str) -> tuple[list[str], bool]:
    """A runner target as path components, and whether it was written as a path (else a dotted label)."""
    t = target.rstrip("/")
    if "/" in t or t.endswith(".py"):
        return (t[:-3] if t.endswith(".py") else t).split("/"), True
    return t.split("."), False


def reruns(later: str, key: str) -> bool:
    """A runner run that names ``later`` runs what an earlier run named ``key``: the same target, a directory above
    it, or a dotted label above it (``queries`` over ``queries.test_q``). A path and a dotted label name the same test
    when one lines up with the other once the label's missing leading directories are allowed for
    (``tests/queries/test_q.py`` and ``queries.test_q``)."""
    if later == _WHOLE or later == key:
        return True
    if key == _WHOLE:
        return False
    (lp, l_path), (kp, k_path) = _parts(later), _parts(key)
    if l_path == k_path:
        return kp[: len(lp)] == lp
    if any(kp[: len(lp) - i] == lp[i:] for i in range(len(lp))):  # an end of ``later`` begins ``key``
        return True
    return any(kp[j : j + len(lp)] == lp for j in range(len(kp) - len(lp) + 1))  # ``later`` inside ``key``


def stash_marks(command: str) -> list[tuple[int, bool]]:
    """(position, stashed away after it) for every ``git stash`` of a command that moves the change: push forms put it
    away, ``pop`` / ``apply`` bring it back; ``list`` / ``show`` / ``drop`` and the like move nothing."""
    out = []
    for m in _STASH.finditer(command or ""):
        sub = m.group(1)
        if sub in _STASH_NOTHING:
            continue
        out.append((m.start(), sub not in _STASH_BACK))
    return out


def stash_states(commands: list, edit_steps: tuple[int, ...] | list[int] = ()) -> tuple[dict, dict]:
    """Per command ``(step, action_index)``: whether the change is stashed away when it starts, and its marks.

    The change stays away until a ``pop`` / ``apply`` -- or until the run edits the repository again (``edit_steps``):
    a stash that is never popped has thrown the change away, and what the run writes next is a new change, not the
    old code. A ``git stash`` that found nothing to save stashed nothing."""
    before, marks, away, since = {}, {}, False, 0
    edits = sorted(edit_steps)
    for c in sorted(commands, key=lambda c: (c.step, c.action_index)):
        key = (int(c.step), c.action_index)
        if away and any(since < w <= key[0] for w in edits):
            away = False
        ms = stash_marks(c.command)
        if "No local changes to save" in (getattr(c, "observation", "") or ""):
            ms = [m for m in ms if not m[1]]
        before[key], marks[key] = away, ms
        if ms:
            away = ms[-1][1]
            since = key[0]
    return before, marks


def run_stashed(r: Any, before: dict, marks: dict) -> bool:
    """The runner run ``r`` runs with the change stashed away."""
    key = (int(r.step), r.action_index)
    ms = marks.get(key) or []
    state = before.get(key, False)
    if not ms:
        return state
    at = (r.command or "").find(r.segment) if r.segment else -1
    if at < 0:  # cannot place the run in its command: a command that stashes runs it stashed
        return state or any(on for _, on in ms)
    for pos, on in ms:
        if pos < at:
            state = on
    return state


def is_run_script(path: str, new: bool, kept: bool) -> bool:
    """A file the run wrote in the repository is one of its scripts, not source: new, with a script extension, and
    either gone from the final change or a throwaway name at the repository root."""
    return new and C._SCRIPT_EXT.search(path) is not None and (not kept or ("/" not in path and _SCRATCH_NAME.search(path) is not None))


def fix_scripts(runs_of: dict, repo_writes_at: dict, text: dict) -> set[str]:
    """The scripts that change the repository when they run: at a step one runs, the replay shows a repository write
    made from Python, or any repository write while the script's own text writes files."""
    return {
        p
        for p, runs in runs_of.items()
        if any(any(e.source == "python" or _WRITES_FILES.search(text.get(p) or "") for e in repo_writes_at.get(int(st), [])) for st, _ in runs)
    }


def runs_own_test(step: int, files: tuple[str, ...], whole: bool, own_tests: dict[str, int]) -> bool:
    """A runner run at ``step`` runs a test of the run's own: it names (or, as the whole suite, includes) a test file
    the run had already written to."""
    return any(first < step and (whole or any(selects(t, f) for t in files)) for f, first in own_tests.items())


def _group_ends(ctx: Any) -> list[int]:
    """The steps at which a task group of the final tasks.md has its last sub-task ticked or marked."""
    if not ctx.facts.artifact_paths.get("tasks"):
        return []
    text = C._text(ctx, "tasks")
    lines = C.task_lines(text)
    ticks = C.tick_steps(ctx, "tasks")
    ends = set()
    for g, _ in C.groups(text):
        steps = [_int(ticks.get(t["id"])) for t in lines if t["group"] and t["group"]["heading"] == g["heading"] and not t["id"].endswith(".0")]
        steps = [s for s in steps if s is not None]
        if steps:
            ends.add(max(steps))
    return sorted(ends)


def timeline(ctx: Any) -> Timeline:
    fx = ctx.facts
    wd = ctx.collected.workdir or "/testbed"
    pre = wd.rstrip("/") + "/"
    tl = Timeline()

    # repository writes: source changes, test files, scripts left in the repository
    keep = F.change_paths(ctx)
    own_tests: dict[str, int] = {}  # repository test file -> the run's first write to it
    repo_scripts: dict[str, list[int]] = {}
    repo_write_steps: dict[int, list] = {}
    for e in fx.repo_writes:
        if e.ok is False or e.op == "unknown" or F.is_generated(e.path):
            continue
        repo_write_steps.setdefault(int(e.step), []).append(e)
        if F.is_test_path(e.path):
            own_tests.setdefault(e.path, int(e.step))
            tl.test_edits.append(int(e.step))
        elif is_run_script(e.path, F.is_new_path(ctx, e.path), e.path in keep):
            repo_scripts.setdefault(posixpath.join(wd, e.path), []).append(int(e.step))
        elif e.path in keep:
            tl.src.append(int(e.step))
    tl.src.sort()

    # the run's scripts: under checks/, and anywhere else (outside the repository, or left in it)
    cdir = C._expand_dir(ctx, "{artifact}/{SPEC}/checks")
    checks = set(C.check_scripts(ctx, cdir)) if cdir else set()
    others: dict[str, list[int]] = dict(repo_scripts)
    text: dict[str, str] = {}
    for path, evs in fx.writes.items():
        if not C._SCRIPT_EXT.search(path) or "__pycache__" in path or path.startswith(pre):
            continue
        steps = [int(e.step) for e in evs if e.ok is not False and e.op in F.WRITE_OPS]
        if not steps:
            continue
        text[path] = next((e.content for e in reversed(evs) if e.ok is not False and e.content), "") or ""
        if path in checks:
            tl.test_edits += steps
        else:
            others[path] = steps
    runs_of = C.executions(ctx, checks | set(others))
    # a script outside checks/ that changes the repository when it runs applies an edit: no test, and no test edit
    fixers = fix_scripts({p: runs_of.get(p, []) for p in others}, repo_write_steps, text)
    for path, steps in others.items():
        if path not in fixers:
            tl.test_edits += steps
    tl.test_edits.sort()
    for path, runs in runs_of.items():
        if path in fixers:
            continue
        for step, out in runs:
            if path in checks:
                tl.own_runs.append(int(step))
            if out:
                tl.results.append(Result(int(step), out == "pass", False, (path,)))

    before, marks = stash_states(fx.commands, sorted({*tl.src, *tl.test_edits}))  # where the change is stashed away
    for r in fx.runs:
        if r.kind != "test":
            continue
        away_now = run_stashed(r, before, marks)
        if away_now:
            tl.check_runs.append(int(r.step))
        if not r.valid:
            continue
        rel = [refs.norm_path(t, wd) for t in (r.targets or [])]
        rel = [t[len(pre) :] if t.startswith(pre) else t for t in rel]
        files = tuple(sorted({t.split("::")[0] for t in rel if t.split("::")[0]}))
        whole = bool(C._whole(r, wd))
        res = Result(int(r.step), not (r.failed + r.errors), True, files if files and not whole else (_WHOLE,))
        if away_now:
            tl.stash_results.append(res)
            continue
        tl.results.append(res)
        tl.existing_runs.append(res.step)
        # a test of the run's own: a test file it had already written to when this run named it
        if runs_own_test(res.step, files, whole, own_tests):
            tl.own_runs.append(res.step)
    tl.results.sort(key=lambda x: (x.step, not x.passed))  # at one step, a failing result is read last

    # phases
    has_tasks = bool(fx.artifact_paths.get("tasks"))
    all_done = C.all_done_step(ctx) if has_tasks else None
    start = _int(C.phase3_start(ctx))
    tl.report = _int(refs.event(ctx, "first_write:final_verification")) if "final_verification" in ctx.rubric.artifacts else None
    tl.p2_end = start if start is not None else (tl.report if tl.report is not None else fx.n_steps + 1)
    if start is not None and tl.report is not None and _int(all_done) == start and start < tl.report:
        tl.p3 = start
    tl.group_ends = _group_ends(ctx)
    return tl


def _between(xs: list[int], a: int, b: int) -> list[int]:
    return [x for x in xs if a < x < b]


def _ran(tl: Timeline, a: int, b: int) -> bool:
    """existing_and_own over the open stretch (a, b)."""
    return bool(_between(tl.existing_runs, a, b)) and bool(_between(tl.own_runs, a, b))


def _last_of_each_failed_test_passes(results: list[Result]) -> bool:
    """Every key that failed passes at the last result that runs it."""
    failed = {k for r in results if not r.passed for k in r.keys}

    def runs(r: Result, key: str) -> bool:
        if key in r.keys:
            return True
        if not r.runner or key == _WHOLE or key.startswith("/"):
            return False
        return any(reruns(k, key) for k in r.keys)

    for key in failed:
        last = [r for r in results if runs(r, key)][-1]
        if not last.passed or any(not r.passed and r.step == last.step and runs(r, key) for r in results):
            return False
    return True


def judge(tl: Timeline) -> dict[str, tuple[float, bool]]:
    """Item -> (score, whether the item applies to the run); outside its pool an item scores :data:`OUTSIDE`."""
    out = {name: (score, False) for name, score in OUTSIDE.items()}
    edits = sorted(tl.src + tl.test_edits)

    def put(name: str, ok: bool) -> None:
        out[name] = (float(ok), True)

    # PHASE 2
    src2 = [s for s in tl.src if s < tl.p2_end]
    if src2:
        first, last = src2[0], src2[-1]
        put(P2_RUN, _ran(tl, last, tl.p2_end))
        res = [r for r in tl.results if first < r.step < tl.p2_end]
        fails = [r.step for r in res if not r.passed]
        if fails:
            bounds = [b for b in tl.group_ends if b <= tl.p2_end]
            if not bounds or bounds[-1] < tl.p2_end:
                bounds.append(tl.p2_end)
            handled, a = True, first
            for b in bounds:
                inside = [s for s in fails if a < s <= b]
                if inside and not any(inside[-1] < x <= b and x < tl.p2_end for x in edits):
                    handled = False
                a = b
            put(P2_EDITED, handled)
            put(P2_LAST, _last_of_each_failed_test_passes(res))

    # PHASE 3
    if tl.p3 is not None and tl.report is not None:
        a, b = tl.p3, tl.report
        put(P3_RUN, _ran(tl, a, b))
        res = [r for r in tl.results if a < r.step < b]
        fails = [r for r in res if not r.passed]
        if fails:
            runner_fails = [r.step for r in fails if r.runner]
            checked = [r.passed for r in tl.stash_results if a < r.step < b]
            if runner_fails:
                put(P3_CAUSE, bool(_between(tl.check_runs, runner_fails[0], b)))
            if not runner_fails or (checked and all(checked)):
                put(P3_EDITED, bool(_between(edits, fails[0].step, b)))
            put(P3_LAST, res[-1].passed)
    return out


def measure(ctx: Any) -> dict[str, tuple[float, bool]]:
    """The seven items of one run: item -> (score, applies)."""
    return judge(timeline(ctx))
