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
             existing test module the run added tests to is both
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
        1.0: a ``git stash`` command after that failure, before the report
    agentos_bugfix.implement_tasks.penalty.phase3_fail.edited_after_fail
        applies: a failing result in PHASE 3 that the document says to fix -- only tests of the run's own failed (no
                 runner failure), or the runner under ``git stash`` passed (the change causes the failure). A failure
                 the check showed to exist without the change, or one that was never checked, is not this item's
                 (else 1.0)
        1.0: source or a test is edited after the first failing result, before the report
    agentos_bugfix.implement_tasks.penalty.phase3_fail.last_result_pass
        applies: a failing result in PHASE 3 (else 1.0)
        1.0: the last result before the report passes

A result is a run whose outcome can be read: a script the run wrote (under checks/ or anywhere else) that ran, or a
valid runner run. A runner run inside a ``git stash`` command is the cause check, not a result. A source change is a
write to a non-test file of the final change; a test edit is a write to a repository test file or to one of the run's
scripts. Nothing here reads the task's reference fix or its test patch: every item is about what the run can know.
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
ITEMS = (
    f"{STAGE}.phase2_run.existing_and_own",
    f"{STAGE}.phase2_fail.edited_after_fail",
    f"{STAGE}.phase2_fail.last_result_pass",
    f"{STAGE}.phase3_run.existing_and_own",
    f"{STAGE}.phase3_fail.cause_checked",
    f"{STAGE}.phase3_fail.edited_after_fail",
    f"{STAGE}.phase3_fail.last_result_pass",
)

_SCRATCH_NAME = re.compile(r"(?i)(?:^|/)(?:repro|reproduce|reproduction|debug|scratch|tmp|temp|check|verify|test|try|demo|example)[^/]*\.(?:py|sh)$")
_STASH = re.compile(r"\bgit\s+stash\b")
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
    results: list[Result] = field(default_factory=list)  # readable results, runs inside a stash command aside
    stash_results: list[Result] = field(default_factory=list)  # valid runner runs inside a stash command
    own_runs: list[int] = field(default_factory=list)  # a checks/ script ran (read or not), or the runner on an own test file
    existing_runs: list[int] = field(default_factory=list)  # valid runner runs of the repository's tests
    stash: list[int] = field(default_factory=list)  # ``git stash`` commands
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


def reruns(later: str, key: str) -> bool:
    """A runner run that names ``later`` runs what an earlier run named ``key``: the same target, a directory above
    it, or a dotted label above it (``queries`` over ``queries.test_q``)."""
    if later == _WHOLE or later == key:
        return True
    later = later.rstrip("/")
    return key.startswith(later + "/") or ("/" not in later and not later.endswith(".py") and key.startswith(later + "."))


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
    own_tests: set[str] = set()
    repo_scripts: set[str] = set()
    for e in fx.repo_writes:
        if e.ok is False or e.op == "unknown" or F.is_generated(e.path):
            continue
        if F.is_test_path(e.path):
            own_tests.add(e.path)
            tl.test_edits.append(int(e.step))
        elif F.is_new_path(ctx, e.path) and (_SCRATCH_NAME.search(e.path) or e.path not in keep) and C._SCRIPT_EXT.search(e.path):
            repo_scripts.add(posixpath.join(wd, e.path))
            tl.test_edits.append(int(e.step))
        elif e.path in keep:
            tl.src.append(int(e.step))
    tl.src.sort()

    # the run's scripts outside the repository: under checks/, and anywhere else
    cdir = C._expand_dir(ctx, "{artifact}/{SPEC}/checks")
    checks = set(C.check_scripts(ctx, cdir)) if cdir else set()
    others = set(repo_scripts)
    for path, evs in fx.writes.items():
        if not C._SCRIPT_EXT.search(path) or "__pycache__" in path or path.startswith(pre):
            continue
        steps = [int(e.step) for e in evs if e.ok is not False and e.op in F.WRITE_OPS]
        if steps:
            tl.test_edits += steps
            if path not in checks:
                others.add(path)
    tl.test_edits.sort()

    tl.stash = sorted({int(c.step) for c in fx.commands if _STASH.search(c.command or "")})
    stash = set(tl.stash)
    for path, runs in C.executions(ctx, checks | others).items():
        for step, out in runs:
            if path in checks:
                tl.own_runs.append(int(step))
            if out:
                tl.results.append(Result(int(step), out == "pass", False, (path,)))
    for r in fx.runs:
        if r.kind != "test" or not r.valid:
            continue
        rel = [refs.norm_path(t, wd) for t in (r.targets or [])]
        rel = [t[len(pre) :] if t.startswith(pre) else t for t in rel]
        files = tuple(sorted({t.split("::")[0] for t in rel if t.split("::")[0]}))
        whole = bool(C._whole(r, wd))
        res = Result(int(r.step), not (r.failed + r.errors), True, files if files and not whole else (_WHOLE,))
        (tl.stash_results if res.step in stash else tl.results).append(res)
        tl.existing_runs.append(res.step)
        if own_tests and (whole or any(selects(t, f) for t in files for f in own_tests)):
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


def _ran(tl: Timeline, a: int, b: int) -> float:
    """existing_and_own over the open stretch (a, b)."""
    return float(bool(_between(tl.existing_runs, a, b)) and bool(_between(tl.own_runs, a, b)))


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
    """Item -> (score, whether the item applies to the run). Out of its pool a run item is 0.0, a failure item 1.0."""
    out = {name: ((0.0, False) if ".phase2_run." in name or ".phase3_run." in name else (1.0, False)) for name in ITEMS}
    edits = sorted(tl.src + tl.test_edits)

    def put(i: int, ok: bool) -> None:
        out[ITEMS[i]] = (float(ok), True)

    # PHASE 2
    src2 = [s for s in tl.src if s < tl.p2_end]
    if src2:
        first, last = src2[0], src2[-1]
        put(0, bool(_ran(tl, last, tl.p2_end)))
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
            put(1, handled)
            put(2, _last_of_each_failed_test_passes(res))

    # PHASE 3
    if tl.p3 is not None and tl.report is not None:
        a, b = tl.p3, tl.report
        put(3, bool(_ran(tl, a, b)))
        res = [r for r in tl.results if a < r.step < b]
        fails = [r for r in res if not r.passed]
        if fails:
            runner_fails = [r.step for r in fails if r.runner]
            checked = [r.passed for r in tl.stash_results if a < r.step < b]
            if runner_fails:
                put(4, bool(_between(tl.stash, runner_fails[0], b)))
            if not runner_fails or (checked and all(checked)):
                put(5, bool(_between(edits, fails[0].step, b)))
            put(6, res[-1].passed)
    return out


def measure(ctx: Any) -> dict[str, tuple[float, bool]]:
    """The seven items of one run: item -> (score, applies)."""
    return judge(timeline(ctx))
