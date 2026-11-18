"""agentos_bugfix penalty items: the files tasks.md names, against the files the run changed and the reference fix.

Four items, each 1.0 (no penalty) or 0.0 (penalty), reported beside the rubric and outside ``compliance``:

    agentos_bugfix.global.penalty.plan_files.named               the change tasks of tasks.md name a source file
    agentos_bugfix.global.penalty.plan_files.named_equals_patch  the named files are the source files of the final patch
    agentos_bugfix.global.penalty.plan_files.named_covers_gold   every source file of the reference fix is named
    agentos_bugfix.global.penalty.plan_files.patch_covers_gold   every source file of the reference fix is in the final
                                                                 patch (more files are fine)

``agentos_bugfix/penalty`` is the mean of the items that apply. A run that names no file fails the first three. The two
gold items do not apply -- and drop out of the mean -- when the task has no reference fix to read
(``penalty_gold_unknown``). Nothing here enters the reward: ``WorkflowSpec.reward_signal`` is still ``compliance``.

The named files
    Every version of tasks.md the trace can replay is read (a write whose content cannot be replayed is skipped; when
    that is the last write, the file as it was collected stands in for it). From each, the change tasks -- the
    sub-tasks that are not about tests, with the lines under them -- give file names: path tokens with a source
    extension, and dotted module names that denote a file the run wrote, the patch changed or the reference fix changes.
    A name counts from the first version it appears in, and stays once written, removed later or not. One name does
    not count: a file the run had already edited when the name first appeared (written down after the fact). A name
    the run never edited stays -- it is a planned file that was not changed.

The spec folder as a shell variable
    shape-spec.md has the agent keep the spec folder in ``$SPEC_PATH``. The engine replays such a run with the
    variable's value known (``checks.SHELL_VARS``, ``engine.evaluate``), so a ``cat > $SPEC_PATH/tasks.md`` is a
    version of tasks.md like any other in the facts this module reads.

A name matches a file when the paths are equal or one is the tail of the other (``slug.py`` matches
``textkit/slug.py``). Source files only, on every side: test files, generated files and the scratch scripts a run
leaves in the repository are not counted.
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
from pathlib import Path
from typing import Any

from ....workflow_rubric import facts as F

logger = logging.getLogger(__name__)

GROUP = "agentos_bugfix.global.penalty.plan_files"
RULES = ("named", "named_equals_patch", "named_covers_gold", "patch_covers_gold")

_EXT = r"(?:py|pyx|pxd|pxi|pyi|c|cc|cpp|h|hpp|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|rb|php)"
_SOURCE = re.compile(rf"\.{_EXT}$")
_PATH = re.compile(rf"(?<![\w/.-])[~./]*(?:[\w.-]+/)*[\w.-]+\.{_EXT}\b")
_DOTTED = re.compile(r"(?<![\w./-])[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_TABLES = re.compile(r"(?:^|/)\w*(?:parse|lex)tab\.py$")  # ply's generated tables
_SCRATCH = re.compile(r"^(?:test|tests|repro|reproduce|check|verify|debug|demo|tmp|scratch|run|try|example|issue|bug|fix)[_\-.\d]", re.I)
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


def scratch(path: str) -> bool:
    """A script the run left in the repository: a Python file at its root, or one named like a throwaway (``repro_x.py``)."""
    return path.endswith(".py") and ("/" not in path or _SCRATCH.match(posixpath.basename(path)) is not None)


def patch_files(patch: str | None) -> tuple[list[str], set[str]]:
    """(paths a patch touches, those it adds), in the patch's order."""
    files: list[str] = []
    new: set[str] = set()
    cur: str | None = None
    for line in (patch or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)$", line)
            cur = m.group(2) if m else None
            if cur is not None and cur not in files:
                files.append(cur)
        elif cur is not None and line.startswith("new file mode"):
            new.add(cur)
    return files, new


def match(name: str, path: str) -> bool:
    """``name`` (as tasks.md wrote it) denotes repository file ``path``."""
    return name == path or path.endswith("/" + name) or name.endswith("/" + path)


def _module(path: str) -> str:
    return re.sub(r"^(?:lib|src)\.", "", re.sub(r"\.\w+$", "", path).replace("/", "."))


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
def judge(named: set[str], patch: list[str], patch_all: list[str], gold: list[str] | None) -> dict[str, float | None]:
    """The four items: 1.0 / 0.0, or None for a gold item when the reference fix is unknown.

    ``patch``: the source files of the final patch without the run's scratch scripts; ``patch_all``: every file of it."""

    def covers(files: list[str]) -> bool:
        return all(any(match(n, f) for n in named) for f in files)

    out: dict[str, float | None] = {
        "named": float(bool(named)),
        "named_equals_patch": float(bool(named) and all(any(match(n, f) for f in patch) for n in named) and covers(patch)),
        "named_covers_gold": None,
        "patch_covers_gold": None,
    }
    if gold:
        out["named_covers_gold"] = float(bool(named) and covers(gold))
        out["patch_covers_gold"] = float(all(g in patch_all for g in gold))
    return out


def measure(facts: Any, collected: Any, task: Any, episode: Any) -> dict[str, float]:
    """The penalty signals of one run (names without the ``agentos_bugfix/`` prefix)."""
    meta = getattr(task, "metadata", None)
    workdir = collected.workdir or (meta.get("workdir") if isinstance(meta, dict) else None)
    art = getattr(episode, "artifacts", None) or {}
    patch_unknown = 0.0
    if isinstance(art.get("patch"), str):
        patch_all, new = patch_files(art["patch"])
    elif collected.diff is not None:
        patch_all, new = sorted(collected.diff), {p for p, st in collected.diff.items() if st in ("A", "?")}
    else:
        patch_all, new, patch_unknown = [], set(), 1.0
    patch = [p for p in patch_all if source_file(p) and not (p in new and scratch(p))]
    gold_text = gold_patch(task)
    gold = [p for p in patch_files(gold_text)[0] if source_file(p)] if gold_text is not None else None
    edits = first_edits(facts, workdir)
    # the run's own scripts: what it wrote outside the repository (check scripts), and inside it the scratch files the
    # patch adds and the root-level scripts that are gone again by the end
    pre = (workdir.rstrip("/") + "/") if workdir else None
    left_repo = {f for f in edits if (f in new and scratch(f)) or (f not in patch_all and f.endswith(".py") and "/" not in f)}
    outside = {p for p in facts.writes if _SOURCE.search(p) and not (pre and p.startswith(pre))}
    own_scripts = frozenset(posixpath.basename(p) for p in (*left_repo, *outside))
    known = {f for f in (*edits, *patch, *(gold or ())) if source_file(f) and f not in left_repo}
    vers, skipped = versions(facts, collected)
    named, late = named_files(vers, edits, workdir, known, own_scripts)
    items = judge(named, patch, patch_all, gold)
    scored = [v for v in items.values() if v is not None]
    out = {f"{GROUP}.{rule}": v for rule, v in items.items() if v is not None}
    out.update(
        {
            "penalty": sum(scored) / len(scored),
            "penalty_errors": 0.0,
            "penalty_gold_unknown": float(not gold),
            "penalty_patch_unknown": patch_unknown,
            "penalty_tasks_write_skipped": float(skipped),
            "penalty_named_files": float(len(named)),
            "penalty_named_late": float(len(late)),
            "penalty_patch_files": float(len(patch)),
        }
    )
    return out


# --------------------------------------------------------------------------------------------
# Hooks of the evaluation policy (``RubricEvaluation(inputs=..., post=...)``)
# --------------------------------------------------------------------------------------------
def inputs(task: Any, episode: Any) -> dict[str, Any]:
    """``Collected.inputs``: the task (for its reference fix) and the episode (for its recorded patch)."""
    return {"task": task, "episode": episode}


def post(report: Any) -> dict[str, float]:
    """The penalty signals from a finished report. A failure here is a full penalty, never a missing signal -- and
    never an exception, which would zero the rubric's score with it."""
    try:
        collected = report.collected
        given = collected.inputs or {}
        return measure(report.facts, collected, given.get("task"), given.get("episode"))
    except Exception:  # noqa: BLE001
        logger.warning("agentos_bugfix penalty: scoring failed; penalty 0", exc_info=True)
        return {"penalty": 0.0, "penalty_errors": 1.0}
