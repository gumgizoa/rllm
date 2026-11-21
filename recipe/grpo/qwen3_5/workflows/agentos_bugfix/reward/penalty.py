"""agentos_bugfix penalty items: rubric items outside ``compliance``, each 1.0 (no penalty) or 0.0 (penalty).

They are items of the rubric (``agentos_bugfix.<stage>.penalty.<name>``, kind ``agentos_bugfix.penalty``, ``log_only``:
judged and reported with every run, never part of ``agentos_bugfix/compliance``), as the penalty items of the other
workflows are. Two groups: the files tasks.md names (this module, below), and the test behaviour of implement-tasks
(``penalty_tests.py``: seven items, ``agentos_bugfix.implement_tasks.penalty.*``).

The files tasks.md names, against the files the run changed -- two items:

    agentos_bugfix.global.penalty.plan_files.named               the change tasks of tasks.md name a source file
    agentos_bugfix.global.penalty.plan_files.named_equals_patch  the named files are the source files of the final change

Nothing here reads the task's reference fix: an item judged against a file the agent cannot see would penalise a run
that names and changes the files it found (C-2 of the reward review, 2026-11-21, dropped the two items that did).

``agentos_bugfix/penalty`` is made by the rule every workflow shares (``workflow_rubric/penalty.py``): the mean of the
nine items, each always in it -- a test item the run stands outside of is worth 0 when the run never did what the
item is about and 1 when it did and the item's condition did not arise (``penalty_tests.py``) -- with what cannot be
judged left out: the seven test items when the code root is not known. ``penalty_plan_files`` and ``penalty_tests``
are the means of each group. A run that names no file fails both file items. ``train.py`` folds ``agentos_bugfix/penalty`` into the reward when
``compliance_reward.penalty_weight`` is set (``WorkflowSpec.penalty_signal``).

The named files
    Every version of tasks.md the trace can replay is read (a write whose content cannot be replayed is skipped; when
    that is the last write, the file as it was collected stands in for it). From each, the change tasks -- the
    sub-tasks that are not about tests, with the lines under them -- give file names: path tokens with a source
    extension, and dotted module names that denote a file the run wrote or the final change holds. A name counts from the first version it appears in, and stays once written, removed later or not. One
    name does not count: a file the run had already edited when the name first appeared (written down after the fact).
    A name the run never edited stays -- it is a planned file that was not changed.

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

import posixpath
import re
from typing import Any

from ....workflow_rubric import facts as F
from ....workflow_rubric import penalty as PEN
from ....workflow_rubric.checks import register
from ....workflow_rubric.context import EvalContext, Result
from ....workflow_rubric.schema import Item
from . import penalty_tests

GROUP = "agentos_bugfix.global.penalty.plan_files"
RULES = ("named", "named_equals_patch")

_EXT = r"(?:py|pyx|pxd|pxi|pyi|c|cc|cpp|h|hpp|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|rb|php)"
_SOURCE = re.compile(rf"\.{_EXT}$")
_PATH = re.compile(rf"(?<![\w/.-])[~./]*(?:[\w.-]+/)*[\w.-]+\.{_EXT}\b")
_DOTTED = re.compile(r"(?<![\w./-])[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_TABLES = re.compile(r"(?:^|/)\w*(?:parse|lex)tab\.py$")  # ply's generated tables
# tasks.md: a task line (checkbox and / or number), and what a task about tests says
_HEAD = re.compile(r"^(\s*)[-*+]\s*(?:(\[[ xX]?\]|⚠️|⚠)\s*)?(?:(\d+(?:\.\d+)+)[.:)]?\s+)?(.*)$")
_HEADING = re.compile(r"^#{2,6}\s")
_WRITE_TESTS = re.compile(r"\b(write|add|create|implement|extend|update)\b[^.]*\btests?\b", re.I)
_RUN_TESTS = re.compile(r"\b(run|re-?run|execute|ensure|verify|confirm|check)\b[^.]*\btests?\b|^tests?\b", re.I)
_REVIEW_TESTS = re.compile(r"\b(review|analy[sz]e)\b[^.]*\b(tests?|coverage|gaps?)\b", re.I)


# --------------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------------
def source_file(path: str) -> bool:
    """A source file of the repository: not a test, not generated, with a source extension."""
    return bool(path) and _SOURCE.search(path) is not None and not F.is_test_path(path) and not F.is_generated(path) and not _TABLES.search(path)


match = F.same_file  # ``name`` (as tasks.md wrote it) denotes repository file ``path``: the rule every workflow shares


def _module(path: str) -> str:
    return re.sub(r"^(?:lib|src)\.", "", re.sub(r"\.\w+$", "", path).replace("/", "."))


# --------------------------------------------------------------------------------------------
# tasks.md
# --------------------------------------------------------------------------------------------
def change_text(tasks_md: str) -> str:
    """The text of the change tasks: every task line that is not about tests, with the lines under it. A line that says
    nothing about tests takes the kind of the task it sits under; a group's own ``N.0`` line is a change task."""
    blocks: list[list] = []  # [is a change task, text]
    stack: list[tuple[int, str]] = []
    in_task = False  # a heading or a ``**Label:**`` line ends the task above it: what follows is not that task's detail
    for line in tasks_md.splitlines():
        if _HEADING.match(line):
            stack, in_task = [], False
            continue
        if line.startswith("**"):
            in_task = False
            continue
        m = _HEAD.match(line)
        if m and (m.group(2) or m.group(3)):
            indent, body = len(m.group(1)), m.group(4)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            own = "write" if _WRITE_TESTS.search(body) else "run" if _RUN_TESTS.search(body) else "review" if _REVIEW_TESTS.search(body) else None
            if own is None and m.group(3) and m.group(3).endswith(".0"):
                own = "change"
            kind = own or (stack[-1][1] if stack else "change")
            stack.append((indent, kind))
            blocks.append([kind == "change", line])
            in_task = True
        elif in_task and line.strip():
            blocks[-1][1] += "\n" + line
    return "\n".join(text for change, text in blocks if change)


def names_in(text: str, workdir: str | None, known: set[str], own_scripts: frozenset[str] = frozenset()) -> set[str]:
    """The source files ``text`` names: path tokens (repository-relative), and the files of ``known`` a dotted module
    name denotes (``pkg.mod`` or ``pkg.mod.attr`` for ``pkg/mod.py``). A token that is the name of one of the run's own
    scripts (``own_scripts``: check scripts, scratch files) and of no file in ``known`` is that script, not a source file."""
    wd = (workdir or "").strip("/")
    text = _URL.sub(" ", text)
    out: set[str] = set()
    for tok in _PATH.findall(text):
        p = tok.strip("`'\"()[],:;").lstrip("~./")
        if wd and p.startswith(wd + "/"):
            p = p[len(wd) + 1 :]
        if not p or p.startswith(("tmp/", "agent-os/")) or "/checks/" in "/" + p or not source_file(p):
            continue
        if posixpath.basename(p) in own_scripts and not any(match(p, f) for f in known):
            continue
        out.add(p)
    if known:
        mods = {_module(f): f for f in known}
        for tok in _DOTTED.findall(text):
            for mod, f in mods.items():
                if tok == mod or tok.startswith(mod + "."):
                    out.add(f)
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


def named_files(vers: list[tuple[int, str]], edits: dict[str, int], workdir: str | None, known: set[str], own_scripts: frozenset[str] = frozenset()) -> tuple[set[str], set[str]]:
    """(the named files, the names left out because the run had edited the file before writing it down)."""
    first: dict[str, int] = {}
    for step, text in vers:
        for name in names_in(change_text(text), workdir, known, own_scripts):
            first.setdefault(name, step)
    kept, late = set(), set()
    for name, step in first.items():
        edited = [s for f, s in edits.items() if match(name, f)]
        (late if edited and not any(step < s for s in edited) else kept).add(name)
    return kept, late


# --------------------------------------------------------------------------------------------
# The items
# --------------------------------------------------------------------------------------------
def judge(named: set[str], patch: list[str]) -> dict[str, float]:
    """The two items, 1.0 / 0.0. ``patch``: the source files of the final patch without the run's scratch scripts."""
    covers = all(any(match(n, f) for n in named) for f in patch)
    return {
        "named": float(bool(named)),
        "named_equals_patch": float(bool(named) and all(any(match(n, f) for f in patch) for n in named) and covers),
    }


FILES = "agentos_bugfix.penalty.files"  # ``ctx.cache`` keys of the two measurements, one per run
TESTS = "agentos_bugfix.penalty.tests"
# the kind's ``rule``: an item's name after ``.penalty.``
FILE_RULES = tuple(f"plan_files.{r}" for r in RULES)
TEST_RULES = tuple(name.split(".penalty.", 1)[1] for name in penalty_tests.ITEMS)


def measure(ctx: EvalContext) -> dict[str, Any]:
    """The two file items of one run (``items``: rule -> 1.0 / 0.0) and what they were judged on."""
    c, facts = ctx.collected, ctx.facts
    workdir = c.workdir
    patch_all = sorted(F.change_paths(ctx))
    patch = [p for p in patch_all if source_file(p) and not F.is_run_script(ctx, p)]
    edits = first_edits(facts, workdir)
    # the run's own scripts: what it wrote outside the repository (check scripts), and inside it the script files the
    # final change does not keep or that carry a throwaway name at the repository root
    pre = (workdir.rstrip("/") + "/") if workdir else None
    left_repo = {f for f in edits if F.is_run_script(ctx, f)}
    outside = {p for p in facts.writes if _SOURCE.search(p) and not (pre and p.startswith(pre))}
    own_scripts = frozenset(posixpath.basename(p) for p in (*left_repo, *outside))
    known = {f for f in (*edits, *patch) if source_file(f) and f not in left_repo}
    vers, skipped = versions(facts, c)
    named, late = named_files(vers, edits, workdir, known, own_scripts)
    return {
        "items": judge(named, patch),
        "detail": f"named {sorted(named)[:4]}; final change {patch[:4]}",
        "patch_unknown": c.diff is None,
        "skipped": skipped,
        "named": len(named),
        "late": len(late),
        "patch": len(patch),
    }


@register("agentos_bugfix.penalty", params={"rule": True}, availability=("trace",), common=False, choices={"rule": (*FILE_RULES, *TEST_RULES)})
def penalty(item: Item, ctx: EvalContext) -> Result:
    """rule: plan_files.<named | named_equals_patch>, or a test item of
    implement-tasks (phase2_run.existing_and_own, phase2_fail.<...>, phase3_run.existing_and_own, phase3_fail.<...>) --
    passes when the run did it right (see this module's docstring and ``penalty_tests.py``). A test item the run
    stands outside of is not applicable, worth 0 when the run never did what the item is about and 1 when it did and
    the item's condition did not arise; a test item without a known code root is unavailable."""
    rule = str((item.check.params or {}).get("rule"))
    if rule in FILE_RULES:
        m = ctx.cache.get(FILES)
        if m is None:
            m = ctx.cache[FILES] = measure(ctx)
        v = m["items"][rule.split(".", 1)[1]]
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
    """``Collected.inputs``: the task, for its description (``task_text.py``). Nothing reads its reference fix."""
    return {"task": task}


def post(report: Any) -> dict[str, float]:
    """The penalty signals of a finished report: the common ones (``workflow_rubric/penalty.py``: ``penalty``, each
    item, ``penalty_applies.<item>``, ``penalty_unavailable``), the mean of each group, and what the file items were
    judged on."""
    out = PEN.post(report)
    for name, prefix in (("penalty_plan_files", "global.penalty.plan_files."), ("penalty_tests", "implement_tasks.penalty.")):
        values = [v for k, v in out.items() if k.startswith(prefix)]
        if values:
            out[name] = sum(values) / len(values)
    m = (getattr(report, "cache", None) or {}).get(FILES)
    if m is not None:
        out.update(
            {
                "penalty_patch_unknown": float(m["patch_unknown"]),
                "penalty_tasks_write_skipped": float(m["skipped"]),
                "penalty_named_files": float(m["named"]),
                "penalty_named_late": float(m["late"]),
                "penalty_patch_files": float(m["patch"]),
            }
        )
    return out
