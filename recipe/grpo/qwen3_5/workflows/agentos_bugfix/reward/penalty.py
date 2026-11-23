"""agentos_bugfix penalty items: rubric items outside ``compliance``, each 1.0 (no penalty) or 0.0 (penalty).

They are items of the rubric (``agentos_bugfix.<stage>.penalty.<name>``, kind ``agentos_bugfix.penalty``, ``log_only``:
judged and reported with every run, never part of ``agentos_bugfix/compliance``), as the penalty items of the other
workflows are. Two groups: the files tasks.md names (this module, below), and the test behaviour of implement-tasks
(``penalty_tests.py``: seven items, ``agentos_bugfix.implement_tasks.penalty.*``).

The files tasks.md names, against the files the run changed and the reference fix -- three items:

    agentos_bugfix.global.penalty.plan_files.named               every sub-task that changes code names, on its task
                                                                 line, the path of a file in the repository
    agentos_bugfix.global.penalty.plan_files.named_equals_patch  the source files those lines name are the source files
                                                                 of the final change
    agentos_bugfix.global.penalty.plan_files.named_covers_gold   every source file of the task's reference fix is among
                                                                 the named source files -- unsolved rollouts only

``named_covers_gold`` is judged against the task's reference fix, which the agent cannot see, so a rollout that solved
the task in other files must not pay for it (C-2 of the reward review, 2026-11-21, dropped the item for that reason,
with ``patch_covers_gold``; it is back, 2026-11-21, as an item that only tells failures apart). It is one of
:data:`UNSOLVED_ONLY`: ``agentos_bugfix/penalty`` holds it as judged and ``agentos_bugfix/penalty_solved`` holds it as
1, and ``train.py`` pays a solved rollout by the second (``workflow_rubric/penalty.py``, "Items that only tell failures
apart"). The other nine items cost a solved rollout as they cost an unsolved one. ``patch_covers_gold`` stays out: on
an unsolved rollout it says nearly what this item says.

``agentos_bugfix/penalty`` is made by the rule every workflow shares (``workflow_rubric/penalty.py``): the mean of the
ten items, each always in it -- a test item the run stands outside of is worth 0 when the run never did what the
item is about and 1 when it did and the item's condition did not arise (``penalty_tests.py``) -- with what cannot be
judged left out: ``named_covers_gold`` when the task has no reference fix to read (``penalty_gold_unknown``), the seven
test items when the code root is not known. ``penalty_plan_files`` and ``penalty_tests`` are the means of each group.
A run that names no file fails all three file items. ``train.py`` folds ``agentos_bugfix/penalty`` into the reward when
``compliance_reward.penalty_weight`` is set (``WorkflowSpec.penalty_signal``).

The named files (create-tasks.md: "every sub-task that changes code names, on its task line, the path in the repository of
the file it changes. A task added while implementing does the same, and is added before that file is edited.")
    The sub-tasks that change code are the task lines of tasks.md as the run left it (its last version) numbered
    ``x.y`` (not ``x.0``; a deeper ``x.y.z`` step is part of its ``x.y``) that are no test work -- writing, running or
    reviewing tests, read with the line's file paths taken out, so "Run tests in foo.py" is a test task -- and do not
    begin with a reading or checking verb (``checks.READ_VERB``: analyze, review, locate, ...; and verify, confirm,
    check, ensure, validate, test, run). Their names come from the task line itself -- not the lines under it ("Reuse
    pattern from: ..."), not an ``x.0`` line -- and are repository paths: a token with a ``/`` whose last part has an
    extension, or a bare file name that is a file at the repository's top level (one the run wrote or the final change
    holds). A dotted module name is no path. When a name first appeared is read over every version of tasks.md the
    trace can replay (a write whose content cannot be replayed is skipped; when that is the last write, the file as it
    was collected stands in for it): a name first written after the run had already edited that file does not count.
    ``named`` asks every such line for a path that counts (any extension: a task that changes the README names the
    README); ``named_equals_patch`` compares the source files among the names with the final change.

The final change
    ``facts.change_paths``: the repository diff as the sandbox gave it; for a saved episode, the patch it recorded
    (``evaluation.py`` puts it in ``Collected.diff``); without either, what the trace wrote.

The spec folder as a shell variable
    shape-spec.md has the agent keep the spec folder in ``$SPEC_PATH``. The engine replays such a run with the
    variable's value known (``checks.SHELL_VARS``, ``engine.evaluate``), and the items are judged inside that replay,
    so a ``cat > $SPEC_PATH/tasks.md`` is a version of tasks.md like any other.

A name matches a file when the paths are equal or one is the tail of the other (``facts.same_file``: ``slug.py``
matches ``textkit/slug.py``). Source files only, on every side: test files, generated files and the run's own scripts
(``facts.is_run_script``) are not counted.
"""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any

from ....workflow_rubric import facts as F
from ....workflow_rubric import patch as PATCH
from ....workflow_rubric import penalty as PEN
from ....workflow_rubric.checks import register
from ....workflow_rubric.context import EvalContext, Result
from ....workflow_rubric.schema import Item
from ...agentos_v2.reward import checks as C
from . import penalty_tests

GROUP = "agentos_bugfix.global.penalty.plan_files"
RULES = ("named", "named_equals_patch", "named_covers_gold")
# judged against the reference fix: a solved rollout is not paid by these (``PEN.post(unsolved_only=...)``)
UNSOLVED_ONLY = ("plan_files.named_covers_gold",)

_EXT = r"(?:py|pyx|pxd|pxi|pyi|c|cc|cpp|h|hpp|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|rb|php)"
_SOURCE = re.compile(rf"\.{_EXT}$")
_PATH = re.compile(rf"(?<![\w/.-])[~./]*(?:[\w.-]+/)*[\w.-]+\.{_EXT}\b")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_TABLES = re.compile(r"(?:^|/)\w*(?:parse|lex)tab\.py$")  # ply's generated tables
# tasks.md: a task line (checkbox and / or number), and what a task about tests says
_HEAD = re.compile(r"^(\s*)[-*+]\s*(?:(\[[ xX]?\]|⚠️|⚠)\s*)?(?:(\d+(?:\.\d+)+)[.:)]?\s+)?(.*)$")
_WRITE_TESTS = re.compile(r"\b(write|add|create|implement|extend|update)\b[^.]*\btests?\b", re.I)
_RUN_TESTS = re.compile(r"\b(run|re-?run|execute|ensure|verify|confirm|check)\b[^.]*\btests?\b|^tests?\b", re.I)
_REVIEW_TESTS = re.compile(r"\b(review|analy[sz]e)\b[^.]*\b(tests?|coverage|gaps?)\b", re.I)


# --------------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------------
def source_file(path: str) -> bool:
    """A source file of the repository: not a test, not generated, with a source extension."""
    return bool(path) and _SOURCE.search(path) is not None and not F.is_test_path(path) and not F.is_generated(path) and not _TABLES.search(path)


def patch_files(patch: str | None) -> list[str]:
    """The paths a patch touches, in the patch's order."""
    files: list[str] = []
    for line in (patch or "").splitlines():
        m = re.match(r"diff --git a/(\S+) b/(\S+)$", line)
        if m and m.group(2) not in files:
            files.append(m.group(2))
    return files


def gold_patch(task: Any) -> str | None:
    """The task's reference fix: ``solution/gold.patch`` (SWE-Gym tasks) or ``tests/config.json``'s ``patch``
    (SWE-bench tasks) in the task directory; None when the task has neither. The agent's sandbox never holds either."""
    task_dir = getattr(task, "task_dir", None)
    if not task_dir:
        meta = getattr(task, "metadata", None)
        task_dir = (meta.get("task_path") or meta.get("task_dir")) if isinstance(meta, dict) else None
    if not task_dir:
        return None
    root = Path(str(task_dir))
    try:
        return (root / "solution" / "gold.patch").read_text(encoding="utf-8")
    except (OSError, ValueError):
        pass
    try:
        patch = json.loads((root / "tests" / "config.json").read_text(encoding="utf-8")).get("patch")
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return patch if isinstance(patch, str) else None


match = F.same_file  # ``name`` (as tasks.md wrote it) denotes repository file ``path``: the rule every workflow shares


# --------------------------------------------------------------------------------------------
# tasks.md
# --------------------------------------------------------------------------------------------
# a reading or checking verb (B-1's list, and the verbs of a sub-task that checks instead of changing)
_CHECK_VERB = re.compile(r"(?i)^\s*(?:\*\*)?\s*(?:verify|confirm|check|ensure|validate|test|run)\b")
# a path of any extension: a token with a ``/`` (its last part with an extension), or a bare ``name.ext``
_ANYPATH = re.compile(r"(?<![\w/.-])[~./]*(?:[\w.-]+/)+[\w.-]*\w\.[A-Za-z0-9]{1,8}\b|(?<![\w/.-])[\w-][\w.-]*\.[A-Za-z][A-Za-z0-9]{0,7}\b")


def change_lines(tasks_md: str) -> list[str]:
    """The task lines of the sub-tasks that change code: numbered ``x.y`` (``y`` not 0), no test work (read with the
    line's file paths taken out: a dot in ``foo.py`` would end the phrase), not begun with a reading or checking verb."""
    out: list[str] = []
    for line in tasks_md.splitlines():
        m = _HEAD.match(re.sub(r"\*\*(\d+(?:\.\d+)+)\*\*", r"\1", line))  # ``**1.2**`` is the number 1.2
        if not m or not m.group(3):
            continue
        parts = m.group(3).split(".")
        if len(parts) != 2 or parts[1] == "0":
            continue
        body = _ANYPATH.sub(" ", _URL.sub(" ", m.group(4)))
        if _WRITE_TESTS.search(body) or _RUN_TESTS.search(body) or _REVIEW_TESTS.search(body):
            continue
        lead = body.lstrip("*`_ ")
        if C.READ_VERB.match(lead) or _CHECK_VERB.match(lead):
            continue
        out.append(m.group(4))
    return out


def line_paths(line: str, workdir: str | None, top: set[str]) -> set[str]:
    """The repository paths a task line names (repository-relative): tokens with a ``/`` whose last part has an
    extension, and bare file names of ``top`` (files at the repository's top level). Paths under /tmp, the agent-os
    folder or a verify/ folder (the spec folder's test scripts) are the run's own, not the repository's."""
    wd = (workdir or "").strip("/")
    out: set[str] = set()
    for tok in _ANYPATH.findall(_URL.sub(" ", line)):
        p = tok.strip("`'\"()[],:;").lstrip("~./")
        if wd and p.startswith(wd + "/"):
            p = p[len(wd) + 1 :]
        if not p or p.startswith(("tmp/", "agent-os/")) or "/verify/" in "/" + p:
            continue
        if "/" in p or p in top:
            out.add(p)
    return out


def versions(facts: Any, collected: Any) -> tuple[list[tuple[int, str]], bool]:
    """(step, text) of every replayable write of tasks.md, in order, and whether a write had to be skipped."""
    path = facts.artifact_paths.get("tasks")
    if not path:
        return [], False
    evs = [e for e in facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
    out = [(int(e.step), e.content) for e in evs if e.content is not None]
    skipped = len(out) < len(evs)
    final = (collected.files or {}).get(path)
    if final is not None and (not evs or evs[-1].content is None):
        # the file as it was collected stands in for the last write (or for a file the trace never wrote)
        out.append((int(evs[-1].step) if evs else int(facts.n_steps) + 1, final))
    return out, skipped


def first_edits(facts: Any, workdir: str | None) -> dict[str, int]:
    """Repository-relative path -> the step of the first write to it, for every repository file the trace wrote."""
    if not workdir:
        return {}
    pre = workdir.rstrip("/") + "/"
    out: dict[str, int] = {}
    for path, evs in facts.writes.items():
        if not path.startswith(pre):
            continue
        steps = [int(e.step) for e in evs if e.ok is not False]
        if steps:
            out[path[len(pre) :]] = min(steps)
    return out


def named_files(vers: list[tuple[int, str]], edits: dict[str, int], workdir: str | None, top: set[str]) -> tuple[list[set[str]], set[str]]:
    """Per sub-task that changes code in the last version of tasks.md, the paths its line names that count; and the
    names left out because the run had edited the file before first writing the name down (on such a line, in any
    version)."""
    first: dict[str, int] = {}
    for step, text in vers:
        for line in change_lines(text):
            for name in line_paths(line, workdir, top):
                first.setdefault(name, step)
    late = {name for name, step in first.items() if (edited := [s for f, s in edits.items() if match(name, f)]) and not any(step < s for s in edited)}
    lines = [line_paths(line, workdir, top) - late for line in change_lines(vers[-1][1])] if vers else []
    return lines, late


# --------------------------------------------------------------------------------------------
# The items
# --------------------------------------------------------------------------------------------
def judge(lines: list[set[str]], named: set[str], patch: list[str], gold: list[str] | None = None) -> dict[str, float | None]:
    """The three items, 1.0 / 0.0; ``named_covers_gold`` is None when the reference fix is unknown. ``lines``: per
    sub-task that changes code, the paths its line names; ``named``: the source files among them; ``patch``: the source
    files of the final patch without the run's scratch scripts; ``gold``: the source files of the reference fix."""

    def covers(files: list[str]) -> bool:
        return all(any(match(n, f) for n in named) for f in files)

    return {
        "named": float(bool(lines) and all(lines)),
        "named_equals_patch": float(bool(named) and all(any(match(n, f) for f in patch) for n in named) and covers(patch)),
        "named_covers_gold": float(bool(named) and covers(gold)) if gold else None,
    }


FILES = "agentos_bugfix.penalty.files"  # ``ctx.cache`` keys of the two measurements, one per run
TESTS = "agentos_bugfix.penalty.tests"
# the kind's ``rule``: an item's name after ``.penalty.``
FILE_RULES = tuple(f"plan_files.{r}" for r in RULES)
TEST_RULES = tuple(name.split(".penalty.", 1)[1] for name in penalty_tests.ITEMS)


def measure(ctx: EvalContext) -> dict[str, Any]:
    """The three file items of one run (``items``: rule -> 1.0 / 0.0, or None for ``named_covers_gold`` when the task
    has no reference fix to read) and what they were judged on."""
    c, facts = ctx.collected, ctx.facts
    workdir = c.workdir
    patch_all = sorted(F.change_paths(ctx))
    patch = [p for p in patch_all if source_file(p) and not F.is_run_script(ctx, p)]
    gold_text = gold_patch((c.inputs or {}).get("task"))
    gold = [p for p in patch_files(gold_text) if source_file(p)] if gold_text is not None else None
    edits = first_edits(facts, workdir)
    # the run's own scripts: what it wrote outside the repository (check scripts), and inside it the script files the
    # final change does not keep or that carry a throwaway name at the repository root
    pre = (workdir.rstrip("/") + "/") if workdir else None
    left_repo = {f for f in edits if F.is_run_script(ctx, f)}
    outside = {p for p in facts.writes if _SOURCE.search(p) and not (pre and p.startswith(pre))}
    own_scripts = frozenset(posixpath.basename(p) for p in (*left_repo, *outside))
    known = {f for f in (*edits, *patch) if source_file(f) and f not in left_repo}
    # files at the repository's top level (the reference fix's too: a bare name of one is a path the plan named)
    top = {f for f in (*edits, *patch_all, *(gold or ())) if "/" not in f and f not in left_repo}
    vers, skipped = versions(facts, c)
    lines, late = named_files(vers, edits, workdir, top)
    # the source files among the names; one that is the name of one of the run's own scripts and of no known file is that script
    named = {n for ps in lines for n in ps if source_file(n) and not (posixpath.basename(n) in own_scripts and not any(match(n, f) for f in known))}
    bare = sum(1 for ps in lines if not ps)
    return {
        "items": judge(lines, named, patch, gold),
        "detail": f"{len(lines)} change sub-task(s), {bare} naming no path; named {sorted(named)[:4]}; final change {patch[:4]}; reference fix {'unknown' if not gold else gold[:4]}",
        "gold_unknown": not gold,
        "patch_unknown": c.diff is None,
        "skipped": skipped,
        "named": len(named),
        "late": len(late),
        "patch": len(patch),
    }


@register("agentos_bugfix.penalty", params={"rule": True}, availability=("trace",), common=False, choices={"rule": (*FILE_RULES, *TEST_RULES)})
def penalty(item: Item, ctx: EvalContext) -> Result:
    """rule: plan_files.<named | named_equals_patch | named_covers_gold>, or a test item of
    implement-tasks (phase2_run.existing_and_own, phase2_fail.<...>, phase2_own.reproduced, phase3_fail.<...>) --
    passes when the run did it right (see this module's docstring and ``penalty_tests.py``). A test item the run
    stands outside of is not applicable, worth 0 when the run never did what the item is about and 1 when it did and
    the item's condition did not arise; ``named_covers_gold`` without a reference fix to read, and a test item without
    a known code root, is unavailable."""
    rule = str((item.check.params or {}).get("rule"))
    if rule in FILE_RULES:
        m = ctx.cache.get(FILES)
        if m is None:
            m = ctx.cache[FILES] = measure(ctx)
        v = m["items"][rule.split(".", 1)[1]]
        if v is None:
            return Result.unavailable(item, "the task has no reference fix to read")
        return Result.ok(item, m["detail"]) if v else Result.no(item, m["detail"])
    if rule not in TEST_RULES:
        return Result.no(item, f"unknown rule {rule!r}")
    if TESTS not in ctx.cache:
        ctx.cache[TESTS] = penalty_tests.measure(ctx)
    tests = ctx.cache[TESTS]
    if tests is None:
        return Result.unavailable(item, "the code root is not known")
    value, judged = tests[f"{penalty_tests.STAGE}.{rule}"]
    if not judged:
        why = "the run ran its tests there and the item's condition did not arise" if value else "the run never did what the item is about"
        return PEN.outside(item, why, premise=bool(value))
    return Result.ok(item) if value else Result.no(item)


# --------------------------------------------------------------------------------------------
# Hooks of the evaluation policy (``RubricEvaluation(inputs=..., post=...)``)
# --------------------------------------------------------------------------------------------
def inputs(task: Any, episode: Any) -> dict[str, Any]:
    """``Collected.inputs``: the task, for its description (``task_text.py``) and its reference fix
    (``named_covers_gold``, which only an unsolved rollout is paid by), and the test-file sections of the
    patch the harness recorded at the end of the run (``episode.artifacts["patch"]``, live and offline alike), for
    ``global.run.prohibited_action.test_file_write`` (``final_patch``; ``workflow_rubric/patch.py``). No patch
    recorded: no ``test_patch`` (the item is judged as before)."""
    out: dict[str, Any] = {"task": task}
    art = getattr(episode, "artifacts", None)
    if isinstance(art, dict):
        tp = PATCH.test_sections(art.get("patch"), art.get("patch_bytes"))
        if tp is not None:
            out["test_patch"] = tp
    return out


def post(report: Any) -> dict[str, float]:
    """The penalty signals of a finished report: the common ones (``workflow_rubric/penalty.py``: ``penalty``, each
    item, ``penalty_applies.<item>``, ``penalty_unavailable``; ``penalty_solved``, the mean with ``named_covers_gold``
    worth 1, which a solved rollout is paid by), the mean of each group, what the file items were judged on, and (N-3,
    logged only) how many failures the report calls expected and how many existing test files had a line changed."""
    out = PEN.post(report, unsolved_only=UNSOLVED_ONLY)
    for name, prefix in (("penalty_plan_files", "global.penalty.plan_files."), ("penalty_tests", "implement_tasks.penalty.")):
        values = [v for k, v in out.items() if k.startswith(prefix)]
        if values:
            out[name] = sum(values) / len(values)
    t = (getattr(report, "cache", None) or {}).get(penalty_tests.FACTS)
    if t is not None:  # N-3 (2026-11-23), logged only: expected-failure claims the report makes, and existing test files edited
        out["penalty_expected_failure_claims"] = t["expected_failure_claims"]
        out["penalty_loosened_test_files"] = t["loosened_test_files"]
    m = (getattr(report, "cache", None) or {}).get(FILES)
    if m is not None:
        out.update(
            {
                "penalty_gold_unknown": float(m["gold_unknown"]),
                "penalty_patch_unknown": float(m["patch_unknown"]),
                "penalty_tasks_write_skipped": float(m["skipped"]),
                "penalty_named_files": float(m["named"]),
                "penalty_named_late": float(m["late"]),
                "penalty_patch_files": float(m["patch"]),
            }
        )
    return out
