"""agentos_bugfix penalty items: the test behaviour of implement-tasks, in PHASE 2 and in PHASE 3.

Seven items, each 1.0 (no penalty) or 0.0 (penalty), rubric items of kind ``agentos_bugfix.penalty`` like the four of
``penalty.py``. Every run gets all seven. A run an item stands outside of gets what the rule every workflow shares
gives (``workflow_rubric/penalty.py``): 0.0 when it never did what the item is about -- it changed no source, it ran
no test where the item reads -- and 1.0 when it ran its tests and the item's condition, a failure, did not arise.
So a run cannot keep an item about failures by not running the tests.
``penalty_applies.<item>`` says whether the item was judged on the run.

PHASE 2 -- from the first source change to the start of PHASE 3 (every task ticked; without that, the report's first
write; without either, the end of the run)

    agentos_bugfix.implement_tasks.penalty.phase2_run.existing_and_own
        1.0: after the last source change the run has a valid runner run of the repository's tests AND a run of a
             test of its own (a script under checks/, or the runner on a test file it wrote to -- named by its path,
             a directory above it or a dotted label of it, ``utils_tests.test_duration``). One runner run of an
             existing test module the run added tests to is both -- when it comes after the run's first write to that
             module. A run without the change (see the cause check below) is neither, and a run that selects only
             tests the run wrote itself -- ``file::name`` ids of test functions it added, or test files it created --
             is no run of the repository's tests (A-9 row 20)
        outside (0.0): the run changed no source in PHASE 2
    agentos_bugfix.implement_tasks.penalty.phase2_fail.edited_after_fail
        judged: a failing result after the first source change
        1.0: per task group -- PHASE 2 is cut where a task group becomes fully ticked; in every stretch that holds a
             failing result, source or a test is edited after the stretch's last failing result and before its tick.
             A run that ticks everything in one write has one stretch
        outside: 1.0 when a test ran after the first source change and none failed; 0.0 when none ran, or the run
             changed no source
    agentos_bugfix.implement_tasks.penalty.phase2_fail.last_result_pass
        judged: a failing result after the first source change
        1.0: every test that failed passed again -- a later passing run of the same file, of a directory or dotted
             label above it, or of the whole suite; not one narrowed below what failed (``-k``, ``-m``,
             ``--deselect``, ``--ignore``, a ``file::test`` id the failing run did not use). A script is rerun by
             running that script. The rule is the common one (``workflow_rubric/results.py``)
        outside: as edited_after_fail

PHASE 3 -- from the write that ticks the last task to the report's first write; it can be placed only when both are
known and in that order. The three failure items ask what the run did about a failure it saw in PHASE 3. A run that
saw none there keeps them when its final code was tested: a test ran in PHASE 3, or -- PHASE 3 placed or not -- after
the last source change and before the report (the end of the run without one). Running the tests once more would then
have shown nothing the run had not seen, and not running them costs the run item alone. A run whose final code was
never tested loses all four.

    agentos_bugfix.implement_tasks.penalty.phase3_run.existing_and_own
        1.0: as phase2_run, anywhere in PHASE 3
        outside (0.0): PHASE 3 cannot be placed
    agentos_bugfix.implement_tasks.penalty.phase3_fail.cause_checked
        judged: a valid runner run fails in PHASE 3 -- the document asks for the check on an existing test
        1.0: after that failure and before the report, the runner is invoked with the change stashed away
        outside: 1.0 when the final code was tested and no runner run failed in PHASE 3; 0.0 when it was not
    agentos_bugfix.implement_tasks.penalty.phase3_fail.edited_after_fail
        judged: a failing result in PHASE 3 that the document says to fix -- only tests of the run's own failed (no
                runner failure), or the runner passed with the change stashed away (the change causes it)
        1.0: source or a test is edited after the first failing result, before the report
        outside: 1.0 when the final code was tested and nothing failed in PHASE 3 that is the change's to fix (a
             failure the check showed to exist without the change, or one that was never checked, is not this
             item's); 0.0 when it was not
    agentos_bugfix.implement_tasks.penalty.phase3_fail.last_result_pass
        judged: a failing result in PHASE 3
        1.0: the last result before the report passes
        outside: 1.0 when the final code was tested and no result failed in PHASE 3; 0.0 when it was not

A result is a run whose outcome can be read: a script under the spec folder's checks/ that ran, or a valid runner run.
The run's own tests are check scripts or test functions in the repository's test modules (core-workflow.md 85-89,
create-tasks.md 127): a script elsewhere -- at the repository root, under /tmp -- is no test, its run no result and
writing it no test edit (A-9 row 8 of the reward review). A check-script run whose outcome cannot be read ran (it counts
for the run items, and as "a test ran") and is no result. The cause check is no result either: a runner run while the
change is stashed away -- from a ``git stash`` (push) to the next ``git stash pop`` / ``apply``, in one command or over
several, or after a ``git checkout`` of an edited source file. ``git stash list`` / ``show`` / ``drop`` stash nothing away.

A source change is what every workflow means by it (``facts.source_change_steps``): a write to a non-test code or
config file of the final change, one of the run's own scripts aside (``facts.is_run_script``: a new script file that
the final change does not keep, or one with a throwaway name -- ``repro_x.py``, ``check_fix.py`` -- at the repository
root) and git putting content back aside. A test edit is a write to a repository test file or to one of the run's
scripts under checks/. Nothing here reads the task's reference fix or its test patch: every item is about what the run
can know.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....workflow_rubric import facts as F
from ....workflow_rubric import refs
from ....workflow_rubric import results as R
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
ITEMS = (P2_RUN, P2_EDITED, P2_LAST, P3_RUN, P3_CAUSE, P3_EDITED, P3_LAST)

_WHOLE = R.WHOLE  # the key of a runner run that names no file
_NEVER = 10**9  # a step no run reaches: the end of a stretch whose closing event did not happen


Result = R.TestResult  # one readable test result (step, passed, runner, keys, selection)


@dataclass
class Timeline:
    """What the items read, in steps."""

    src: list[int] = field(default_factory=list)  # source changes
    test_edits: list[int] = field(default_factory=list)  # writes to repository test files and to the check scripts
    results: list[Result] = field(default_factory=list)  # readable results (check scripts, valid runner runs); cause checks aside
    stash_results: list[Result] = field(default_factory=list)  # valid runner runs with the change stashed away
    check_runs: list[int] = field(default_factory=list)  # runner invocations with the change stashed away, valid or not
    own_runs: list[int] = field(default_factory=list)  # a checks/ script ran (read or not), or the runner on an own test file
    existing_runs: list[int] = field(default_factory=list)  # valid runner runs of the repository's tests, with the change in place (not only the run's own tests)
    # steps of the runs above that come after a repository write of their own call (``sed -i ... && pytest``): at the step
    # of the last source change they still ran after it (``RunFact.after_write_same_call``)
    results_late: set[int] = field(default_factory=set)
    own_late: set[int] = field(default_factory=set)
    existing_late: set[int] = field(default_factory=set)
    group_ends: list[int] = field(default_factory=list)  # steps at which a task group becomes fully ticked
    excused: set = field(default_factory=set)  # failure units the documents do not ask the run to fix (R2: ``checks.excused_failures``)
    p2_end: int = 0
    p3: int | None = None  # PHASE 3 start, when it can be placed before the report
    report: int | None = None


def _int(v) -> int | None:
    return None if v is None or v is UNKNOWN else int(v)


selects, reruns = R.selects, R.reruns  # which test a runner target names, and when a later run reruns it: the common rule


# where the change is stashed away (``git stash`` ... ``pop``): the common rule, moved to ``workflow_rubric/results.py``
stash_marks, stash_states, run_stashed = R.stash_marks, R.stash_states, R.run_stashed


def runs_own_test(step: int, files: tuple[str, ...], whole: bool, own_tests: dict[str, int]) -> bool:
    """A runner run at ``step`` runs a test of the run's own: it names (or, as the whole suite, includes) a test file
    the run had already written to."""
    return any(first < step and (whole or any(selects(t, f) for t in files)) for f, first in own_tests.items())


def only_own_tests(ctx: Any, r: Any, files: tuple[str, ...], whole: bool, added: set[str]) -> bool:
    """The runner run ``r`` selects only tests the run wrote itself (A-9 row 20): every target is a ``file::name`` id of a
    test function or class the run added to an existing module (``added``, F-2's reading), or every file it names is a
    test file the run created. Such a run is a run of the run's own tests, not of the repository's existing ones."""
    if whole or not files:
        return False
    ids = [s for s in R.selection(getattr(r, "segment", "") or "") if "::" in s and not s.startswith("-")]
    named = {s.split("::")[0].lstrip("./") for s in ids}
    # every file it names is named through ids (``file::name``), and every id names a test the run added
    by_ids = bool(ids) and all(any(n == f or n.endswith("/" + f) or f.endswith("/" + n) for n in named) for f in files)
    if by_ids and all(any(part.split("[")[0] in added for part in s.split("::")[1:]) for s in ids):
        return True
    return all(F.is_test_path(f) and F.is_new_path(ctx, f) for f in files)


def _group_ends(ctx: Any) -> list[int]:
    """The steps at which a task group of the final tasks.md has its last sub-task ticked or marked: the rule
    ``before_code``'s task-group stretches use too (``agentos_v2.reward.checks.group_end_steps``)."""
    return C.group_end_steps(ctx)


def timeline(ctx: Any) -> Timeline:
    fx = ctx.facts
    wd = ctx.collected.workdir  # known: ``measure`` does not come here without it
    tl = Timeline()

    # repository writes: source changes (the definition every workflow shares) and test files
    tl.src = list(F.source_change_steps(ctx))
    own_tests: dict[str, int] = {}  # repository test file -> the run's first write to it
    for e in fx.repo_writes:
        if e.ok is False or e.op == "unknown" or F.is_generated(e.path):
            continue
        if F.is_test_path(e.path):
            own_tests.setdefault(e.path, int(e.step))
            tl.test_edits.append(int(e.step))

    # the run's check scripts under the spec folder's checks/: a script anywhere else is no test (A-9 row 8)
    cdir = C._expand_dir(ctx, "{artifact}/{SPEC}/checks")
    checks = set(C.check_scripts(ctx, cdir)) if cdir else set()
    for path in checks:
        tl.test_edits += [int(e.step) for e in fx.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
    tl.test_edits.sort()
    for path, runs in C.executions(ctx, checks).items():
        for step, out in runs:
            tl.own_runs.append(int(step))
            if out:
                tl.results.append(Result(int(step), out == "pass", False, (path,)))

    added = {n for _, names in C.module_tests(ctx).values() for n in names}  # test functions the run added to existing modules
    before, marks = stash_states(fx.commands, sorted({*tl.src, *tl.test_edits}), C.edited_sources(ctx))  # where the change is put away (git stash, or a checkout of an edited source file)
    for r in fx.runs:
        if r.kind != "test":
            continue
        away_now = run_stashed(r, before, marks)
        if away_now:
            tl.check_runs.append(int(r.step))
        if not r.valid:
            continue
        files = R.run_files(r, wd)
        whole = bool(C._whole(r, wd))
        res = C.runner_result(r, wd)  # with the ids of its failed tests when the output names them all
        if away_now:
            tl.stash_results.append(res)
            continue
        tl.results.append(res)
        existing = not only_own_tests(ctx, r, files, whole, added)
        if existing:
            tl.existing_runs.append(res.step)
        late = bool(getattr(r, "after_write_same_call", False))
        if late:
            tl.results_late.add(res.step)
            if existing:
                tl.existing_late.add(res.step)
        # a test of the run's own: a test file it had already written to when this run named it
        if runs_own_test(res.step, files, whole, own_tests):
            tl.own_runs.append(res.step)
            if late:
                tl.own_late.add(res.step)
    tl.results.sort(key=lambda x: (x.step, not x.passed))  # at one step, a failing result is read last
    # the failures the documents do not ask the run to fix (R2): left out of the failure items
    tl.excused = C.excused_failures(ctx, [(u, r) for r in tl.results if not r.passed for u in R.failure_units(r)])

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


def _after(xs: list[int], late: set[int], a: int, b: int) -> list[int]:
    """The steps of ``xs`` after a change at step ``a`` and before ``b``: later steps, and runs of the change's own call
    that come after a write in it (``late``)."""
    return [x for x in xs if a < x < b or (x == a < b and x in late)]


def _ran(tl: Timeline, a: int, b: int, after_change: bool = False) -> bool:
    """existing_and_own over the open stretch (a, b); ``after_change``: ``a`` is a source change, and a run of its own
    call that comes after the write counts."""
    if after_change:
        return bool(_after(tl.existing_runs, tl.existing_late, a, b)) and bool(_after(tl.own_runs, tl.own_late, a, b))
    return bool(_between(tl.existing_runs, a, b)) and bool(_between(tl.own_runs, a, b))


def _last_of_each_failed_test_passes(results: list[Result]) -> bool:
    """Every test that failed passed again, by the rule every workflow shares (``workflow_rubric/results.py``): a later
    passing run of the same file, of a directory or label above it, or of the whole suite -- not one narrowed below
    what failed (``-k``, a ``file::test`` id the failing run did not use)."""
    return not R.standing_failures(results)


def judge(tl: Timeline) -> dict[str, tuple[float, bool]]:
    """Item -> (value, whether the item was judged on the run). A run an item stands outside of gets what the common
    rule gives (``workflow_rubric/penalty.py``): 0 when it never did what the item is about -- it changed no source,
    it ran no test in the stretch -- and 1 when it ran its tests there and the item's condition, a failure, did not
    arise. For the failure items of PHASE 3 a test run after the last source change counts as well, in whichever
    phase it ran."""
    out: dict[str, tuple[float, bool]] = {}
    edits = sorted(tl.src + tl.test_edits)

    def bad(r: Result) -> bool:
        """A failing result the failure items ask about: one with a failure unit the documents ask the run to fix (R2)."""
        return not r.passed and not all(u in tl.excused for u in R.failure_units(r))

    def put(name: str, ok: bool) -> None:
        out[name] = (float(ok), True)

    def outside(name: str, premise: bool) -> None:
        out[name] = (1.0 if premise else 0.0, False)

    # PHASE 2
    src2 = [s for s in tl.src if s < tl.p2_end]
    if not src2:
        for name in (P2_RUN, P2_EDITED, P2_LAST):
            outside(name, False)
    else:
        first, last = src2[0], src2[-1]
        put(P2_RUN, _ran(tl, last, tl.p2_end, after_change=True))
        res = [r for r in tl.results if first < r.step < tl.p2_end and (r.passed or bad(r))]  # an excused failure is no failure here
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
        else:
            ran = bool(res) or bool(_between(tl.own_runs, first, tl.p2_end))
            outside(P2_EDITED, ran)
            outside(P2_LAST, ran)

    # PHASE 3. A run that ran no test there keeps the three failure items when its final code was tested all the
    # same -- a test ran after its last source change, before the report: running the tests once more would have
    # shown no failure the run had not seen. The run item is what it loses for not running them again.
    end = tl.report if tl.report is not None else _NEVER
    src = [s for s in tl.src if s < end]
    tested = bool(src) and (bool(_after([r.step for r in tl.results], tl.results_late, src[-1], end)) or bool(_after(tl.own_runs, tl.own_late, src[-1], end)))
    if tl.p3 is None or tl.report is None:
        outside(P3_RUN, False)
        for name in (P3_CAUSE, P3_EDITED, P3_LAST):
            outside(name, tested)
    else:
        a, b = tl.p3, tl.report
        put(P3_RUN, _ran(tl, a, b))
        every = [r for r in tl.results if a < r.step < b]
        res = [r for r in every if r.passed or bad(r)]  # an excused failure is no failure for the fix items
        fails = [r for r in res if not r.passed]
        ran = bool(every) or bool(_between(tl.own_runs, a, b)) or tested
        runner_fails = [r.step for r in every if not r.passed and r.runner]  # the cause check is asked of every runner failure
        checked = [r.passed for r in tl.stash_results if a < r.step < b]
        if runner_fails:
            put(P3_CAUSE, bool(_between(tl.check_runs, runner_fails[0], b)))
        else:
            outside(P3_CAUSE, ran)
        if fails and (not any(r.runner for r in fails) or (checked and all(checked))):
            put(P3_EDITED, bool(_between(edits, fails[0].step, b)))
        else:  # no failure, or one that is not the change's to fix: the tests ran, the item's condition did not arise
            outside(P3_EDITED, ran)
        if fails:
            put(P3_LAST, res[-1].passed)
        else:
            outside(P3_LAST, ran)
    return out


def measure(ctx: Any) -> dict[str, tuple[float, bool]] | None:
    """The seven items of one run: item -> (value, judged). None when the code root is not known: which writes are
    repository writes and which targets are repository tests cannot be told, so nothing here can be judged."""
    if not ctx.collected.workdir:
        return None
    return judge(timeline(ctx))
