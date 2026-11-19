"""openspec_ff penalty items: does verify.md say what actually happened, and was what it found fixed.

The rubric's scored items say whether the workflow's form was followed. These five say whether what the run wrote is
true of what the run did. They are rubric items (``openspec_ff.verify.penalty.<rule>``, kind ``openspec_ff.penalty``)
marked ``log_only``: evaluated and reported with every run, never part of ``openspec_ff/compliance``. The common
``post`` (``workflow_rubric/penalty.py``, shared by every workflow) turns their results into the second score,
``openspec_ff/penalty`` (their mean), next to ``openspec_ff/compliance``.

    rule (item)            1 when
    no_run_after_change    after the last change to the code, the run executed a valid repository test run or a
                           check script it wrote under /openspec/changes/issue/checks/
    false_clean_claim      the report's Final Assessment is true: it does not say "All checks passed" / "Ready for
                           archive" when a run failed, when nothing was run, or when tasks.md held an open task
    task_count_mismatch    the report's "X/Y tasks" is what tasks.md held when the report was written
    critical_missing       when something had to be CRITICAL (a failed run, an open task: 03-verify.md "Issues by
                           Priority"), the report lists a CRITICAL issue instead of "None"
    left_broken            at the end of the run nothing is left broken: no test / check script stands failed since
                           the last code change, and tasks.md holds no open task. Reporting a failure honestly and
                           stopping there passes the three report rules but not this one; going back to apply,
                           fixing and re-running does

The names follow ``<stage>.penalty.<item>``, the naming the workflows share for these items; a value of 1 means the
run did it right (no penalty). How the items make one score is the same for all workflows: every item stays in the
mean, a rule the run stands outside of is worth 0 when the run never did what the rule is about and 1 when it did and
the rule's condition did not arise, and a rule that cannot be read is left out (``workflow_rubric/penalty.py``).

The report is verify.md as it stands at the end and "when the report was written" is its LAST write. A run that
writes the report, goes back to apply, fixes the code and rewrites the report is judged on the rewritten report and
on what was run between the last code change and that rewrite. Only a report left untouched after a later code
change is stale.

    rule                   no report   stale report   otherwise
    no_run_after_change    by the run  by the run     by the run
    left_broken            by the run  by the run     by the run (outside the rule, worth 0, when nothing was run and
                                                      no task is open: a run cannot leave nothing broken by not looking)
    false_clean_claim      0           0              1 unless a run failed / nothing was run / a task was open, and
                                                      the report still says "All checks passed" / "Ready for archive"
    task_count_mismatch    0           0              1 unless the report's count differs from tasks.md, or it says
                                                      every task is done while a box is open (unavailable when
                                                      tasks.md's content at that step is not known)
    critical_missing       0           0              1 unless a run failed or a task was open, and no CRITICAL issue
                                                      is listed. When nothing was due the run stands outside the rule:
                                                      worth 1 when it ran something and nothing failed (a report with
                                                      "None" under CRITICAL is right), 0 when it ran nothing

A failed test stays failed until it passes again, by the rule every workflow shares (``workflow_rubric/results.py``):
a later passing run of the same file, of a directory or dotted label above it, or of the whole suite clears it; one
that passes only after narrowing what it runs (``-k``, ``-m``, ``--deselect``, ``--ignore``, a ``file::test`` id the
failed run did not use) does not. A check script that could not be run (wrong path, import error) is a failed run; one
whose outcome the trace does not show (no exit code, no pass or failure text) ran -- it counts for
``no_run_after_change`` -- and is no passing result.

A run with no code change has nothing to verify: every item is not applicable, worth 0, and ``openspec_ff/penalty``
is 0 (``openspec_ff/penalty_applies.<rule>`` 0).

Everything is read from the engine's facts, so "valid test run" (``RunFact.kind == "test" and RunFact.valid``), "last
change to the code" (``facts.last_change_write``: the last source change, a throwaway script the run left at the
repository root aside), "check script" (a file the trace wrote under the change's checks/
and later executed) mean what they mean to the scored items.

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from recipe.grpo.qwen3_5.workflow_rubric import facts as F
from recipe.grpo.qwen3_5.workflow_rubric import penalty as PEN
from recipe.grpo.qwen3_5.workflow_rubric import results as R
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflows.openspec_ff.reward import checks as CK

ITEM_PREFIX = "openspec_ff.verify.penalty."
# rule (the item's name after ``verify.penalty.``) -> the field of ``Measured`` it reads
RULES = {
    "no_run_after_change": "ran_after_change",
    "false_clean_claim": "report_consistent",
    "task_count_mismatch": "tasks_consistent",
    "critical_missing": "critical_listed",
    "left_broken": "ends_fixed",
}

REPORT = "/changes/issue/verify.md"

# "All checks passed" / "Ready for archive", but not "Not ready for archive"
_CLEAN = re.compile(r"(?i)\ball checks passed\b|(?<!not )\bready for archive\b")
# a CRITICAL label line: "### CRITICAL", "1. **CRITICAL** (Must fix before archive):", "- CRITICAL: ..."
_CRIT_LABEL = re.compile(r"(?im)^[ \t]*(?:#{1,6}[ \t]*|\d+\.[ \t]*|[-*+][ \t]+)?\**[ \t]*CRITICAL\b(?P<tail>[^\n]*)$")
_OTHER_LABEL = re.compile(r"(?i)^[ \t]*(?:#{1,6}[ \t]*|\d+\.[ \t]*|[-*+][ \t]+)?\**[ \t]*(?:WARNINGS?|SUGGESTIONS?|Final Assessment|Next step)\b")
_NONE = re.compile(r"(?i)^\W*(?:none|no\b|n/a|nothing|0\b|zero\b|not applicable)")
# "7/7 tasks", "7 / 8 tasks complete", "7 of 8 tasks"
_TASK_COUNT = re.compile(r"(?i)\b(\d+)\s*(?:/|of|out of)\s*(\d+)\s*\**\s*tasks?\b")
_ALL_TASKS = re.compile(r"(?i)\ball\s+(?:\d+\s+)?tasks?\s+(?:are\s+|were\s+|have been\s+|marked\s+(?:as\s+)?)?(?:complete|completed|done|checked)\b")


@dataclass
class Measured:
    applicable: bool = False             # the run changed code
    outside: dict[str, bool] = field(default_factory=dict)          # rule -> the run did what the rule is about (worth 1), or never did (worth 0)
    unavailable: set[str] = field(default_factory=set)              # rules that cannot be judged
    ran_after_change: bool | None = None
    report_consistent: bool | None = None
    tasks_consistent: bool | None = None
    critical_listed: bool | None = None
    ends_fixed: bool | None = None
    left_broken: list[str] = field(default_factory=list)            # what stands failed / open at the end of the run
    case: str = "no_change"              # no_change | no_report | stale_report | failed | not_run | passed  (what the runs showed)
    last_change: int | None = None       # step of the last code change
    report_step: int | None = None       # step verify.md was last written
    report_writes: int = 0               # how many times verify.md was written
    runs: list[tuple[int, str, str]] = field(default_factory=list)  # (step, what, passed|failed|ran) after the last change
    open_tasks: int = 0                  # open boxes in tasks.md when the report was written
    failed: list[str] = field(default_factory=list)                 # what failed on its last run before the report
    tasks_actual: tuple[int, int] | None = None    # (ticked, total) in tasks.md when the report was written
    tasks_claimed: tuple[int, int] | None = None   # the report's "X/Y tasks"
    claims_clean: bool = False
    lists_critical: bool = False
    must_be_critical: list[str] = field(default_factory=list)       # why a CRITICAL issue was due


def lists_critical(text: str) -> bool:
    """A CRITICAL issue is listed: the rubric's own forms ("N critical issue(s)", "- CRITICAL: ..."), or a CRITICAL
    label whose body -- the rest of its line after ':' or the next non-empty line -- is an item rather than "None"."""
    if CK.lists_critical(text):
        return True
    for m in _CRIT_LABEL.finditer(text):
        tail = re.sub(r"^[^:\n]*?(?::|\s[-–—]\s)", "", m.group("tail"), count=1) if re.search(r":|\s[-–—]\s", m.group("tail")) else ""
        body = tail.strip(" *\t")
        if not body:
            nxt = [ln for ln in text[m.end():].split("\n")[1:6] if ln.strip()]
            body = nxt[0].strip() if nxt else ""
            if _OTHER_LABEL.match(body) or body.startswith("#"):
                body = ""
        if body and not _NONE.match(body.lstrip("-*+ \t")):
            return True
    return False


def _report(ctx: EvalContext) -> tuple[str | None, int | None, int]:
    """(verify.md as it stands at the end, step of its last write, number of writes). Online the sandbox file; offline the replay."""
    evs = [e for path, es in ctx.facts.writes.items() if path.endswith(REPORT) for e in es if e.ok is not False and e.op not in ("delete", "move_out")]
    step = max((e.step for e in evs), default=None)
    text = ctx.artifact_text("verify", "final")
    if text is None:
        known = [e for e in sorted(evs, key=lambda e: (e.step, e.action_index)) if e.content is not None]
        text = known[-1].content if known else None
    return text, step, len({e.step for e in evs})


_TICKED = r"x|done|complete|completed|✓|✔|✅|☑"
_BOX = re.compile(rf"(?i)^\s*[-*+]\s*\[\s*(?:(?P<t>{_TICKED})|todo|pending|open)?\s*\]\s*\S")


def _boxes(text: str) -> tuple[int, int]:
    """(ticked, total) checkbox tasks, read leniently -- "[ x ]", "-[x]", "[DONE]" are ticked, "[TODO]" is open:
    the box's form is the rubric's business, here only what it says counts."""
    hits = [m.group("t") for m in map(_BOX.match, re.sub(r"(?s)<!--.*?-->", "", text).split("\n")) if m]
    return sum(1 for h in hits if h), len(hits)


def _tasks_at(ctx: EvalContext, at: int) -> tuple[int, int] | None:
    """(ticked, total) checkbox tasks in tasks.md as of step ``at``. None when its content at that step is not
    known: never written, written with nothing readable as a checkbox, or last written by an edit the replay could not follow (offline) / written again after
    the report (online, where only the final file is at hand)."""
    evs = CK._content_events(ctx, "tasks")
    before = [e for e in evs if e.step <= at]
    if not before:
        return None
    text = before[-1].content
    if text is None and len(before) == len(evs):
        text = ctx.artifact_text("tasks", "final")
    if text is None:
        return None
    n = _boxes(text)
    return n if n[1] else None  # nothing readable as a checkbox (e.g. a "Status: Done" line per task): nothing to count


_selection = R.selection  # what narrows a test run below its files: the common rule (workflow_rubric/results.py)


def _check_scripts(ctx: EvalContext) -> set[str]:
    """Absolute paths of the files the trace wrote under the change's checks/ directory."""
    d = CK.check_dir(ctx)
    return {posixpath.normpath(path) for path, evs in ctx.facts.writes.items() if path.startswith(d) and any(e.ok is not False and e.op not in ("delete", "move_out") for e in evs)}


def _runs_after(ctx: EvalContext, last_change) -> tuple[list[R.TestResult], list[tuple[int, str, str]]]:
    """What ran after ``last_change``: the readable results (every valid test run; every run of a check script whose
    outcome the trace shows), and all of it as (step, what, passed | failed | ran). A check script whose outcome
    cannot be read -- no exit code, no pass or failure text, the run's last call -- ran, and is no result."""
    wd = ctx.collected.workdir
    results: list[R.TestResult] = []
    shown: list[tuple[int, str, str]] = []
    for r in ctx.facts.runs:
        if r.kind == "test" and r.valid and r.step > last_change:
            files = R.run_files(r, wd)
            ok = r.failed + r.errors == 0
            results.append(R.TestResult(int(r.step), ok, True, files or (R.WHOLE,), R.selection(r.segment)))
            shown.append((int(r.step), "test " + (" ".join(files) or r.segment[:80]), "passed" if ok else "failed"))
    for path, runs in R.executions(ctx, _check_scripts(ctx)).items():
        for step, out in runs:
            if step <= last_change:
                continue
            if out is not None:
                results.append(R.TestResult(int(step), out == "pass", False, (path,)))
            shown.append((int(step), "check " + path, {"pass": "passed", "fail": "failed"}.get(out or "", "ran")))
    return sorted(results, key=lambda r: (r.step, not r.passed)), sorted(set(shown))


def _name(key: str) -> str:
    return "the whole suite" if key == R.WHOLE else key


def measure(ctx: EvalContext) -> Measured:
    q = Measured()
    last = F.last_change_write(ctx)
    if last is None:
        return q
    q.applicable = True
    q.last_change = None if last is UNKNOWN else int(last)
    results, q.runs = _runs_after(ctx, last)
    q.ran_after_change = bool(q.runs)
    q.left_broken = [_name(k) for k in R.standing_failures(results)]
    at_end = _tasks_at(ctx, 10**9)
    if at_end and at_end[1] > at_end[0]:
        q.left_broken.append(f"{at_end[1] - at_end[0]} open task(s)")
    q.ends_fixed = not q.left_broken
    if q.ends_fixed and not q.runs:  # nothing left failed because nothing was run: the run stands outside the rule
        q.outside["left_broken"] = False

    text, at, q.report_writes = _report(ctx)
    q.report_step = at
    if text is None or at is None:
        q.case = "no_report"
        q.report_consistent = q.tasks_consistent = q.critical_listed = False
        return q
    q.claims_clean = bool(_CLEAN.search(text))
    q.lists_critical = lists_critical(text)
    m = _TASK_COUNT.search(text)
    q.tasks_claimed = (int(m.group(1)), int(m.group(2))) if m else None
    q.tasks_actual = _tasks_at(ctx, at)
    if last is not UNKNOWN and at < last:  # the code changed after the report's last write: the report describes other code
        q.case = "stale_report"
        q.report_consistent = q.tasks_consistent = q.critical_listed = False
        return q

    # what the runs between the last code change and the report showed, and what tasks.md held
    q.failed = [_name(k) for k in R.standing_failures(results, at)]
    read = [r for r in results if r.step <= at]
    q.case = "failed" if q.failed else "passed" if read else "not_run"
    q.open_tasks = q.tasks_actual[1] - q.tasks_actual[0] if q.tasks_actual else 0
    q.report_consistent = not (q.claims_clean and (q.case in ("failed", "not_run") or q.open_tasks))

    # the report's task count against tasks.md at that moment
    if q.tasks_actual is None:  # what tasks.md held then is not known: the count cannot be judged
        q.unavailable.add("task_count_mismatch")
    elif q.tasks_claimed is not None:
        q.tasks_consistent = q.tasks_claimed == q.tasks_actual
    else:  # no count in the report: wrong only when it says every task is done while a box is open
        q.tasks_consistent = not (q.open_tasks and _ALL_TASKS.search(text))

    # what had to be CRITICAL
    if q.failed:
        q.must_be_critical.append(f"{len(q.failed)} failed run(s)")
    if q.open_tasks:
        q.must_be_critical.append(f"{q.open_tasks} open task(s)")
    if q.must_be_critical:
        q.critical_listed = q.lists_critical
    else:  # nothing was due: worth 1 to a run that ran something before the report (nothing failed), 0 to one that ran nothing
        q.critical_listed = True
        q.outside["critical_missing"] = any(step <= at for step, _, _ in q.runs)
    return q


# --------------------------------------------------------------------------------------------
# The kind; the second score is the common ``post`` over these items
# --------------------------------------------------------------------------------------------
def _detail(q: Measured, rule: str) -> str:
    if rule == "no_run_after_change":
        return f"{len(q.runs)} run(s) after the last code change (step {q.last_change})"
    if rule == "left_broken":
        if q.left_broken:
            return "left: " + "; ".join(q.left_broken)[:160]
        return "nothing left failed or open" if q.runs else "nothing was run after the last code change"
    if q.case in ("no_report", "stale_report"):
        return "no verify.md" if q.case == "no_report" else f"verify.md (step {q.report_step}) predates the last code change (step {q.last_change})"
    if rule == "false_clean_claim":
        return f"runs {q.case}, {q.open_tasks} open task(s), report {'claims' if q.claims_clean else 'does not claim'} all passed / ready"
    if rule == "task_count_mismatch":
        return f"tasks.md {q.tasks_actual if q.tasks_actual is not None else 'not known at that step'}, report {q.tasks_claimed}"
    return (f"due: {'; '.join(q.must_be_critical)}; " if q.must_be_critical else f"nothing had to be CRITICAL (runs {q.case}); ") + f"CRITICAL {'listed' if q.lists_critical else 'not listed'}"


@register("openspec_ff.penalty", params={"rule": True}, availability=("trace",), common=False, choices={"rule": tuple(RULES)})
def penalty(item: Item, ctx: EvalContext) -> Result:
    """rule: no_run_after_change | false_clean_claim | task_count_mismatch | critical_missing | left_broken -- passes
    when the run did it right (see the module docstring). A run the rule stands outside of is not applicable, worth 0
    when it never did what the rule is about (it changed no code, it ran nothing) and 1 when it did and the rule's
    condition did not arise; what cannot be read is unavailable."""
    rule = str((item.check.params or {}).get("rule"))
    if rule not in RULES:
        return Result.no(item, f"unknown rule {rule!r}")
    q = ctx.cache.get("openspec_ff.penalty")
    if q is None:
        q = ctx.cache["openspec_ff.penalty"] = measure(ctx)
    if not q.applicable:
        return PEN.outside(item, "the run changed no code", premise=False)
    if rule in q.unavailable:
        return Result.unavailable(item, _detail(q, rule))
    if rule in q.outside:
        return PEN.outside(item, _detail(q, rule), premise=q.outside[rule])
    return Result.ok(item, _detail(q, rule)) if getattr(q, RULES[rule]) else Result.no(item, _detail(q, rule))


post = PEN.post  # openspec_ff/penalty and its item signals: the rule every workflow shares
