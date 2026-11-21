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
        1.0: per task group -- PHASE 2 is cut where a task group becomes fully ticked (a run that ticks everything in
             one write has one stretch). In every stretch, each failure unit (``results.failure_units``: a test, or a
             file / script when the output names no test) that fails after the stretch's first source change and that
             the documents ask to fix (R2: ``checks.excused_failures``) had at most two attempts -- a failing result, an
             edit of source or a test, and the unit's next result in the stretch -- and passed again in the stretch or
             had at least one attempt (implement-tasks.md 40: fix and run again; after two attempts, ⚠️ and go on)
        outside: 1.0 when a test ran after the first source change and none failed; 0.0 when none ran, or the run
             changed no source
    agentos_bugfix.implement_tasks.penalty.phase2_fail.last_result_pass
        judged: a failing result after the first source change
        1.0: per task-group stretch (as edited_after_fail), every failure unit that failed there and that the documents
             ask to fix (R2) passed again before the stretch ends -- or the task group that ends it carries ⚠️ (A-9
             row 17). A test passes again in a later valid runner run that ran it: the failed test picked out
             (``file::test``, ``-k``) is enough (A-7 row 8), a run that left it out (``--deselect``, ``-k "not ..."``,
             ``--ignore``, ``-m``) is not (A-2). A file whose failed tests the output did not name passes again in a run
             of it, a directory or label above it or the whole suite, not narrowed below what failed; a script by
             running it again (``results.standing_units``)
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
        judged: a failure unit in PHASE 3 that the change causes (A-9 row 22) -- not one the documents leave (R2), and a
                test of the run's own (a check script, a test file it created, a test function it added) or one that a
                valid runner run with the change stashed away ran and passed
        1.0: each such unit is fixed after its first failure, before the report: by a source change (implement-tasks.md
             137 "fix the change"), or for a test of the run's own also by an edit of that test (40). Failures the change
             does not cause, in the same run, are left out
        outside: 1.0 when the final code was tested and nothing failed in PHASE 3 that is the change's to fix (a
             failure the check showed to exist without the change, or one that was never checked, is not this
             item's); 0.0 when it was not
    agentos_bugfix.implement_tasks.penalty.phase3_fail.last_result_pass
        judged: a failing result in PHASE 3 that the documents ask about (R2's aside)
        1.0: every failure unit of it passed again before the report (a run that ran that test, not one that left it
             out: A-2), or -- a failure the change causes (see edited_after_fail) -- it was fixed after its first
             failure and run again after the last fix (implement-tasks.md 137: go back once, fix, carry out PHASE 3
             again; what still fails goes into the report). Which run came last does not matter (A-1)
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
    script_late: set[int] = field(default_factory=set)  # steps of check-script runs that come after a repository write of their own call
    existing_late: set[int] = field(default_factory=set)
    group_ends: list[int] = field(default_factory=list)  # steps at which a task group becomes fully ticked
    group_marked: dict[int, bool] = field(default_factory=dict)  # group end -> a group ending there carries ⚠️
    excused: set = field(default_factory=set)
    test_edits_of: dict[str, list[int]] = field(default_factory=dict)  # test file (repository-relative) or check script -> its edits
    added_tests: set[str] = field(default_factory=set)  # test functions / classes the run added to existing modules (F-2)
    new_test_files: set[str] = field(default_factory=set)  # repository test files the run created  # failure units the documents do not ask the run to fix (R2: ``checks.excused_failures``)
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


def _scripts_after_a_write(ctx: Any, scripts: set[str]) -> set[int]:
    """Steps at which a check script runs after a repository write of its own call: the written path comes before the
    script's path in the command's text (``sed -i ... && python checks/x.py``), as ``facts._same_call_order`` reads a
    runner run."""
    fx, wd = ctx.facts, (ctx.collected.workdir or "").rstrip("/") + "/"
    by_call: dict[tuple[int, Any], set[str]] = {}
    for e in fx.repo_writes:
        if e.ok is not False and e.op != "unknown":
            by_call.setdefault((int(e.step), e.action_index), set()).add(e.path)
    out = set()
    for c in fx.commands:
        paths = by_call.get((int(c.step), c.action_index))
        cmd = c.command or ""
        if not paths:
            continue
        for s in scripts:
            at = cmd.find(s)
            if at < 0:
                continue
            pos = [i for p in paths for i in (cmd.find(wd + p) if cmd.find(wd + p) >= 0 else cmd.find(p),) if i >= 0]
            if pos and min(pos) < at:
                out.add(int(c.step))
    return out


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
            tl.test_edits_of.setdefault(e.path, []).append(int(e.step))

    # the run's check scripts under the spec folder's checks/: a script anywhere else is no test (A-9 row 8)
    cdir = C._expand_dir(ctx, "{artifact}/{SPEC}/checks")
    checks = set(C.check_scripts(ctx, cdir)) if cdir else set()
    for path in checks:
        steps = [int(e.step) for e in fx.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
        tl.test_edits += steps
        tl.test_edits_of[path] = steps
    tl.test_edits.sort()
    for path, runs in C.executions(ctx, checks).items():
        for step, out in runs:
            tl.own_runs.append(int(step))
            if out:
                tl.results.append(Result(int(step), out == "pass", False, (path,)))
    tl.script_late = _scripts_after_a_write(ctx, checks)

    added = {n for _, names in C.module_tests(ctx).values() for n in names}  # test functions the run added to existing modules
    tl.added_tests = added
    tl.new_test_files = {p for p in own_tests if F.is_new_path(ctx, p)}
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
    tl.group_marked = C.group_end_marks(ctx)
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


def _standing(tl: Timeline, results: list[Result]) -> list[tuple[str, str]]:
    """The failure units of ``results`` still failing at their end, R2's aside: a test passes again when a later valid
    runner run ran it -- the failed test picked out (``file::test``, ``-k``) is enough (A-7 row 8), a run that left it
    out (``--deselect``, ``-k "not ..."``, ``--ignore``) is not (A-2); a file the output named no test of, or a script,
    by the rule every workflow shares (``workflow_rubric/results.py``)."""
    return [u for u, _ in R.standing_units(results) if u not in tl.excused]


def own_test(tl: Timeline, unit: tuple[str, str], failing: Result) -> bool:
    """The failure unit is a test of the run's own: a check script, a test file the run created, or a test function /
    class it added to an existing module (F-2)."""
    kind, what = unit
    if not failing.runner:
        return True
    file_part = what.split("::")[0]
    if any(file_part == f or file_part.endswith("/" + f) for f in tl.new_test_files):
        return True
    names = {x.split("[")[0] for x in what.split("::")[1:]} if kind == "test" else set()
    return bool(names & tl.added_tests)


def change_caused(tl: Timeline, unit: tuple[str, str], failing: Result) -> bool:
    """A failure the change causes (A-9 row 22): not one the documents leave (R2), and a test of the run's own (a) or one
    that a valid runner run with the change stashed away ran and passed (b)."""
    if unit in tl.excused:
        return False
    return own_test(tl, unit, failing) or any(outcome_for(s, unit) == "pass" for s in tl.stash_results)


def fix_edits(tl: Timeline, unit: tuple[str, str], failing: Result) -> list[int]:
    """The edits that fix a failure the change causes: a source change (implement-tasks.md 137 "fix the change"); for a
    test of the run's own, also an edit of that test (40: "or that test")."""
    out = list(tl.src)
    if own_test(tl, unit, failing):
        what = unit[1].split("::")[0]
        for path, steps in tl.test_edits_of.items():
            if path == what or what.endswith("/" + path) or path.endswith("/" + what):
                out += steps
    return sorted(out)


def _stretches(tl: Timeline, first: int) -> list[tuple[int, int]]:
    """PHASE 2 cut at the task-group ends: (a, b] stretches from the first source change to PHASE 3."""
    bounds = [b for b in tl.group_ends if first < b <= tl.p2_end]
    if not bounds or bounds[-1] < tl.p2_end:
        bounds.append(tl.p2_end)
    out, a = [], first
    for b in bounds:
        out.append((a, b))
        a = b
    return out


def outcome_for(r: Result, unit: tuple[str, str]) -> str | None:
    """How result ``r`` came out for failure unit ``unit``: ``fail`` (the unit is among its failures, or it ran the unit
    and failed without naming which tests), ``pass`` (it ran the unit and the unit is not among its failures), or None
    (it did not run the unit)."""
    kind, what = unit
    if unit in R.failure_units(r):
        return "fail"
    if kind == "test":
        if not (r.runner and R.runs_test(r, what)):
            return None
        return "pass" if r.passed or r.failed_ids else "fail"
    if R.runs_key(r, what):
        return "pass" if r.passed else "fail"
    return None


def attempts(tl: Timeline, seq: list[tuple[Result, str]], edits: list[int]) -> int:
    """The attempts at a failure unit, over its results ``seq`` (in order): a failing result followed by an edit (a source
    change or a test edit) before the unit's next result -- a run of the same call placed after its write counts as after
    the edit (``RunFact.after_write_same_call``, and the same reading for a check script)."""
    n = 0
    for (r, o), (nxt, _) in zip(seq, seq[1:], strict=False):
        if o != "fail":
            continue
        late = nxt.step in tl.results_late or nxt.step in tl.script_late
        if any(r.step < e < nxt.step for e in edits) or (nxt.step > r.step and nxt.step in edits and late):
            n += 1
    return n


def _passed_or_marked(tl: Timeline, res: list[Result], first: int) -> bool:
    """A-9 row 17: in every task-group stretch, every test that failed there (and that the documents ask to fix) passed
    again before the stretch ends -- or the task group that ends it carries ⚠️ (two attempts did not get it to pass;
    implement-tasks.md 40). A failure left standing while its group is ticked is not undone by a pass in a later group."""
    for a, b in _stretches(tl, first):
        inside = [r for r in res if a < r.step <= b and r.step < tl.p2_end]
        if not _standing(tl, inside) or tl.group_marked.get(b):
            continue
        return False
    return True


def _attempts_ok(tl: Timeline, every: list[Result], first: int, edits: list[int]) -> bool:
    """A-4 / A-9 row 7 (implement-tasks.md 40: "fix the change or that test and run the tests again ... After two attempts
    that do not get it to pass, mark ... ⚠️ ... and go on"): in every task-group stretch, every failure unit that fails
    after the stretch's first source change (a test written first fails before the code it tests: that failure asks for
    no fix) and that the documents ask to fix (R2) was fixed and run again at most twice, and passed again inside the
    stretch or was tried at least once."""
    for a, b in _stretches(tl, first):
        inside = [r for r in every if a < r.step <= b and r.step < tl.p2_end]
        c0 = first if a == first else next((s for s in tl.src if a < s <= b), None)  # the first stretch begins at the first source change
        start = c0 if c0 is not None else a
        after = [r for r in inside if r.step > start or (r.step == start and r.step in tl.results_late)]
        units = {u for r in after if not r.passed for u in R.failure_units(r) if u not in tl.excused}
        standing = {u for u, _ in R.standing_units(after)}
        for u in units:
            seq = [(r, o) for r in after if (o := outcome_for(r, u))]
            n = attempts(tl, seq, edits)
            if n > 2 or not (u not in standing or n >= 1):
                return False
    return True


def _p3_left_right(tl: Timeline, every: list[Result], fails: list[Result], b: int) -> bool:
    """A-1 (with A-2's PHASE 3 side): every failure unit of PHASE 3 that the documents ask about (R2's aside) either passed
    again before the report (``results.clears``: a run that ran the test, not one that left it out), or is one the change
    causes (A-9 row 22) that was fixed once after its first failure and run again after that fix -- what is still
    failing then goes into the report (implement-tasks.md 137). Which run came last does not matter."""
    standing = {u for u, _ in R.standing_units(every)}
    units: dict[tuple[str, str], Result] = {}
    for r in fails:
        for u in R.failure_units(r):
            if u not in tl.excused:
                units.setdefault(u, r)
    for u, first in units.items():
        if u not in standing:
            continue
        if not change_caused(tl, u, first):
            return False
        fixes = [e for e in fix_edits(tl, u, first) if first.step < e < b]
        if not fixes or not any((r.step > fixes[-1] or (r.step == fixes[-1] and r.step in (tl.results_late | tl.script_late))) and outcome_for(r, u) for r in every):
            return False
    return True


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
            every = [r for r in tl.results if first < r.step < tl.p2_end]
            put(P2_EDITED, _attempts_ok(tl, every, first, edits))
            put(P2_LAST, _passed_or_marked(tl, res, first))
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
        if runner_fails:
            put(P3_CAUSE, bool(_between(tl.check_runs, runner_fails[0], b)))
        else:
            outside(P3_CAUSE, ran)
        caused: dict[tuple[str, str], Result] = {}
        for r in fails:
            for u in R.failure_units(r):
                if u not in caused and change_caused(tl, u, r):
                    caused[u] = r
        if caused:  # A-9 row 22: each failure the change causes is fixed after its first failure, the others aside
            put(P3_EDITED, all(any(r.step < e < b for e in fix_edits(tl, u, r)) for u, r in caused.items()))
        else:  # no failure, or none the change's to fix: the tests ran, the item's condition did not arise
            outside(P3_EDITED, ran)
        if fails:
            put(P3_LAST, _p3_left_right(tl, every, fails, b))
        else:
            outside(P3_LAST, ran)
    return out


def measure(ctx: Any) -> dict[str, tuple[float, bool]] | None:
    """The seven items of one run: item -> (value, judged). None when the code root is not known: which writes are
    repository writes and which targets are repository tests cannot be told, so nothing here can be judged."""
    if not ctx.collected.workdir:
        return None
    return judge(timeline(ctx))
