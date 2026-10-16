"""Spec Kit plugin kinds: the tasks.md rules and run facts the reference language cannot state as checks.

Vendored verbatim (this paragraph aside) from ``workflows/spec_kit/reward/checks.py`` of the verifier-generation
branch (e19b7236), whose ``spec_kit`` port is not on this branch: ``speckit_sdd`` uses these kinds as they are, and
``speckit_sdd/reward/checks.py`` imports them from here. Keep the two copies in step; never import both into one
process (a kind registers once).

The common kinds cover most of Spec Kit: section and label items for the templates, ``item_format`` for
line grammars (the task checkbox, sequential ``T###`` ids, ``FR-###``), ``no_template_residue`` for
placeholders and the template's sample tasks, ``doc_read`` for the command files and the constitution.
What they cannot say:

* ``speckit.task_lines`` -- rules that depend on *which phase* a task line sits in (tasks.md:157-163:
  ``[USn]`` required in user-story phases and forbidden in Setup / Foundational / Polish; the phase
  order of tasks.md:80-84; tasks.md:157 "[P] ... different files"). One item per rule::

      {rule: story_label}      every task of a "User Story n" phase carries [USn] (ratio)
      {rule: no_story_label}   no task of a Setup / Foundational / Polish phase carries a [USn] label (ratio)
      {rule: story_tasks}      every "User Story n" phase holds at least one task (tasks.md:83 "implementation tasks")
      {rule: phase_order}      Setup, Foundational, the story phases (ascending), Polish -- in that order
      {rule: parallel_files}   two [P] tasks of one phase never name the same file (ratio)

* ``speckit.tasks_done`` -- what the trace says about implement's ``[X]`` marks (implement.md:165)::

      {rule: marked_after_code}  a task of a user-story or Polish phase is ticked only after the run's first
                                 code edit: the replayed tasks.md history gives each box's tick step (ratio)
      {rule: paths_touched}      a ticked task whose action creates / modifies a repository path names a
                                 path the run wrote (ratio; anchored on the trace, never on the agent's text)

* ``speckit.feature_json`` -- ``.specify/feature.json`` parses and its ``feature_directory`` resolves to
  the directory that holds the spec (specify.md:99-105: the actual path, not the literal name).
* ``speckit.read`` -- every listed artifact that exists was read in the window (an editor view, or a
  reading verb naming its path): doc_read covers the workflow's own documents, not the run's artifacts
  (plan.md:60 "Read FEATURE_SPEC", tasks.md:62 / implement.md:87-88 REQUIRED reads).
* ``speckit.holds`` -- a refs predicate as a check: the language has the facts (``exists: {fact:
  exec_of | command | repo_edit | artifact_write}``) but only predicates use them; "the setup script
  ran" or "the checklist was not written during implement" is a fact that must hold.

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import json
import posixpath
import re

from recipe.grpo.qwen3_5.workflow_rubric import facts as F
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

MAX_TEXT = 400_000
_PHASE = re.compile(r"^#{2}\s+(?:\*\*)?Phase\s+(\d+|[A-Z])\b[^:\n]*:\s*(?P<title>.*)$", re.I)
_H2 = re.compile(r"^#{1,2}\s+\S")
_TASK = re.compile(r"^\s*(?:[-*+]\s+)?(?:\[(?P<box>[^\]\n]?)\]\s+)?(?P<id>T\d{3,})\b(?P<rest>.*)$")
_STORY = re.compile(r"\bUser\s+Story\s+(\d+)\b", re.I)
_US = re.compile(r"\[US(\d+)\]")
_P = re.compile(r"\[P\]")
_CODE = re.compile(r"`([^`\n]+)`")
_PATHLIKE = re.compile(r"(?<![\w@:/.-])((?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)+/?|[\w-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?![\w/-])")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_MODIFY = re.compile(
    r"^\s*(?:\[[^\]\n]*\]\s*)*(?:create|add|implement|modify|update|fix|change|edit|refactor|remove|delete|rename|write|extend|rewrite|replace|adjust|correct|handle)\b",
    re.I,
)
# the feature directory's own documents (plan.md:47-56): a task may name them, but they are not repository paths
_FEATURE_DOCS = frozenset({"spec.md", "plan.md", "tasks.md", "research.md", "data-model.md", "quickstart.md", "contracts", "contracts/", "requirements.md"})
_KIND_RANK = {"setup": 0, "foundational": 1, "story": 2, "polish": 3}


# --------------------------------------------------------------------------------------------
# tasks.md parsing
# --------------------------------------------------------------------------------------------
def phase_kind(title: str) -> tuple[str, int | None]:
    """A ``## Phase n: <title>`` heading's kind -- setup | foundational | story (with its number) | polish | other."""
    m = _STORY.search(title)
    if m:
        return "story", int(m.group(1))
    low = title.lower()
    if re.search(r"\bsetup\b", low):
        return "setup", None
    if re.search(r"\bfoundation(?:al)?\b", low):
        return "foundational", None
    if re.search(r"\bpolish\b", low):
        return "polish", None
    return "other", None


def task_lines(text: str | None) -> list[dict]:
    """Every task line of tasks.md (outside fences and comments), with the ``## Phase`` it sits under.

    A task line is a line whose first token (after an optional list marker and checkbox) is a ``T###``
    id -- loose on purpose, so a malformed task (missing box, wrong marker) is still a task line.
    """
    out: list[dict] = []
    if not text:
        return out
    phase: dict | None = None
    for line in M.text_lines(text[:MAX_TEXT]):
        line = line[:2000]
        if _H2.match(line):
            m = _PHASE.match(line.strip())
            if m:
                kind, num = phase_kind(m.group("title"))
                phase = {"title": m.group("title").strip(), "kind": kind, "story": num}
            else:
                phase = None
            continue
        m = _TASK.match(line)
        if not m:
            continue
        rest = m.group("rest")
        out.append(
            {
                "id": m.group("id"),
                "box": m.group("box"),
                "checked": (m.group("box") or "") in ("x", "X"),
                "line": line,
                "rest": rest,
                "us": [int(x) for x in _US.findall(rest)],
                "parallel": bool(_P.search(rest)),
                "phase": phase,
            }
        )
    return out


def phases(text: str | None) -> list[dict]:
    """The ``## Phase`` headings of tasks.md in document order (kind, story number, title)."""
    out = []
    for line in M.text_lines((text or "")[:MAX_TEXT]):
        m = _PHASE.match(line.strip()[:2000]) if _H2.match(line) else None
        if m:
            kind, num = phase_kind(m.group("title"))
            out.append({"title": m.group("title").strip(), "kind": kind, "story": num})
    return out


def description(rest: str) -> str:
    """A task's description: what follows its id, without the [P] / [USn] markers."""
    return re.sub(r"^\s*(?:\[(?:P|US\d+)\]\s*)*", "", rest or "").strip()


def named_paths(desc: str, workdir: str | None) -> set[str]:
    """Repository-relative paths a task description names (code spans first, then bare path tokens)."""
    s = _URL.sub(" ", desc or "")[:2000]
    cands = [*_CODE.findall(s), *(m.group(1) for m in _PATHLIKE.finditer(_CODE.sub(" ", s)))]
    out = set()
    for c in cands:
        c = c.strip().strip(".,;:()'\"")
        if not c or " " in c or c.startswith(("http", "-")):
            continue
        p = refs.norm_path(c, workdir).rstrip("/")
        if not p or posixpath.basename(p) in _FEATURE_DOCS or p.startswith(("specs/", ".specify/", "spec-kit/")):
            continue
        if "/" not in p and not re.search(r"\.[A-Za-z][A-Za-z0-9]{0,7}$", p):
            continue
        out.add(p)
    return out


def _tasks_text(ctx: EvalContext, item: Item) -> str | None:
    aid = (item.check.params or {}).get("artifact") or item.target.ref
    t = ctx.artifact_text(aid, item.target.state)
    return None if t is None else M.strip_fence(t)[0]


# --------------------------------------------------------------------------------------------
# speckit.task_lines
# --------------------------------------------------------------------------------------------
@register(
    "speckit.task_lines",
    params={"rule": True, "artifact": False},
    availability=("sandbox_file",),
    common=False,
    choices={"rule": ("story_label", "no_story_label", "story_tasks", "phase_order", "parallel_files")},
)
def task_lines_check(item: Item, ctx: EvalContext) -> Result:
    """rule: story_label | no_story_label | story_tasks | phase_order | parallel_files over the task lines of tasks.md
    (by the ``## Phase`` they sit under); not_applicable when the rule has nothing to judge."""
    rule = str((item.check.params or {}).get("rule"))
    text = _tasks_text(ctx, item)
    if text is None:
        return Result.no(item, "tasks.md absent")
    tasks = task_lines(text)
    if rule == "story_label":
        pool = [t for t in tasks if t["phase"] and t["phase"]["kind"] == "story"]
        if not pool:
            return Result.not_applicable(item, "no task in a user-story phase")
        bad = [t["id"] for t in pool if t["phase"]["story"] not in t["us"]]
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"without their story's [USn]: {bad[:5]}" if bad else f"{len(pool)} story tasks labelled")
    if rule == "no_story_label":
        pool = [t for t in tasks if t["phase"] and t["phase"]["kind"] in ("setup", "foundational", "polish")]
        if not pool:
            return Result.not_applicable(item, "no task in a Setup / Foundational / Polish phase")
        bad = [t["id"] for t in pool if t["us"]]
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"story label outside story phases: {bad[:5]}" if bad else f"{len(pool)} tasks unlabelled")
    if rule == "story_tasks":
        ph = [p for p in phases(text) if p["kind"] == "story"]
        if not ph:
            return Result.not_applicable(item, "no user-story phase")
        have = {(t["phase"]["title"], t["phase"]["story"]) for t in tasks if t["phase"] and t["phase"]["kind"] == "story"}
        empty = [f"US{p['story']}" for p in ph if (p["title"], p["story"]) not in have]
        return Result.ratio(item, len(ph) - len(empty), len(ph), f"story phases without a task: {empty[:5]}" if empty else f"{len(ph)} story phases with tasks")
    if rule == "phase_order":
        ph = [p for p in phases(text) if p["kind"] != "other"]
        if len(ph) < 2:
            return Result.not_applicable(item, "fewer than two recognised phases")
        keys = [(_KIND_RANK[p["kind"]], p["story"] or 0) for p in ph]
        if keys == sorted(keys):
            return Result.ok(item, " < ".join(p["kind"] + (str(p["story"]) if p["story"] else "") for p in ph))
        return Result.no(item, "out of order: " + ", ".join(p["kind"] + (str(p["story"]) if p["story"] else "") for p in ph))
    if rule == "parallel_files":
        wd = ctx.collected.workdir
        par = [t for t in tasks if t["parallel"]]
        if not par:
            return Result.not_applicable(item, "no [P] task")
        bad = []
        for t in par:
            mine = named_paths(description(t["rest"]), wd)
            if mine and any(o is not t and o["phase"] is t["phase"] and mine & named_paths(description(o["rest"]), wd) for o in par):
                bad.append(t["id"])
        return Result.ratio(item, len(par) - len(bad), len(par), f"[P] tasks sharing a file: {bad[:5]}" if bad else f"{len(par)} [P] tasks on distinct files")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit.tasks_done
# --------------------------------------------------------------------------------------------
def tick_steps(ctx: EvalContext, aid: str) -> dict[str, int | None]:
    """Task id -> the step of the write after which its box is first ticked (None: never seen ticked in the
    replayed history; ``UNKNOWN``: a write whose content cannot be replayed precedes the first seen tick)."""
    path = ctx.facts.artifact_paths.get(aid)
    out: dict[str, int | None] = {}
    if not path:
        return out
    blind = False
    for e in ctx.facts.writes.get(path, []):
        if e.ok is False or e.op in ("delete", "move_out"):
            continue
        if e.content is None:
            blind = True
            continue
        for t in task_lines(e.content):
            if t["checked"] and t["id"] not in out:
                out[t["id"]] = UNKNOWN if blind else e.step
    return out


def first_code_edit(ctx: EvalContext):
    """The first successful write to a repository file that is not a run byproduct (``UNKNOWN`` when the diff
    shows a change the trace does not)."""
    steps = [e.step for e in ctx.facts.repo_writes if e.ok is not False and not F.is_generated(e.path)]
    if getattr(ctx.facts, "unseen_repo_paths", None):
        return UNKNOWN
    return min(steps) if steps else None


@register("speckit.tasks_done", params={"rule": True, "artifact": False}, availability=("sandbox_file", "trace"), common=False, choices={"rule": ("marked_after_code", "paths_touched")})
def tasks_done(item: Item, ctx: EvalContext) -> Result:
    """rule: marked_after_code | paths_touched -- the ticked tasks of the final tasks.md against the trace."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = p.get("artifact") or item.target.ref
    text = _tasks_text(ctx, item)
    if text is None:
        return Result.no(item, "tasks.md absent")
    ticked = [t for t in task_lines(text) if t["checked"]]
    if rule == "marked_after_code":
        pool = [t for t in ticked if t["phase"] and t["phase"]["kind"] in ("story", "polish")]
        if not pool:
            return Result.not_applicable(item, "no ticked user-story / Polish task")
        first = first_code_edit(ctx)
        if first is None:
            return Result.no(item, "ticked, but the run never edited the code")
        when = tick_steps(ctx, aid)
        bad = []
        for t in pool:
            s = when.get(t["id"])
            if s is None or s is UNKNOWN or (first is not UNKNOWN and s <= first):
                bad.append(t["id"])
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"ticked before any code edit (or untraceable): {bad[:5]}" if bad else f"{len(pool)} ticks after step {first}")
    if rule == "paths_touched":
        wd = ctx.collected.workdir
        written = {e.path for e in ctx.facts.repo_writes if e.ok is not False}
        if ctx.collected.diff is not None:
            written |= {q for q, s in ctx.collected.diff.items() if s != "?" or not F.is_generated(q)}
        claims = [(t["id"], named_paths(description(t["rest"]), wd)) for t in ticked if _MODIFY.search(description(t["rest"]))]
        claims = [(i, ps) for i, ps in claims if ps]
        if not claims:
            return Result.not_applicable(item, "no ticked task creates or modifies a named path")
        bad = [i for i, ps in claims if not ps & written]
        return Result.ratio(item, len(claims) - len(bad), len(claims), f"named path never written: {bad[:5]}" if bad else f"{len(claims)} tasks' paths written")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit.feature_json
# --------------------------------------------------------------------------------------------
def feature_dirs(ctx: EvalContext) -> list[str]:
    """The directories directly under ``{artifact}/specs`` at the end of the run (collected dirs and file parents)."""
    root = F.roots_of(ctx.rubric, ctx.collected.workdir).get("artifact") or ""
    specs = posixpath.join(root, "specs") if root else ""
    if not specs:
        return []
    pool = set(ctx.collected.dirs) | {posixpath.dirname(q) for q in ctx.collected.files}
    out = set()
    for d in pool:
        if d.startswith(specs + "/"):
            out.add(specs + "/" + d[len(specs) + 1 :].split("/", 1)[0])
    return sorted(out)


@register("speckit.feature_json", params={"rule": True, "artifact": False, "feature_of": False}, availability=("sandbox_file",), common=False, choices={"rule": ("consistent", "single")})
def feature_json(item: Item, ctx: EvalContext) -> Result:
    """rule: consistent -- the file parses, ``feature_directory`` is a string that resolves (absolute, or
    relative to the project root) to the directory holding the ``feature_of`` artifact (default ``spec``);
    rule: single -- exactly one feature directory exists under ``specs/`` (one feature per specify run)."""
    p = item.check.params or {}
    if str(p.get("rule")) == "single":
        dirs = feature_dirs(ctx)
        if len(dirs) == 1:
            return Result.ok(item, dirs[0])
        return Result.no(item, f"{len(dirs)} feature directories: {[posixpath.basename(d) for d in dirs][:5]}")
    if str(p.get("rule")) != "consistent":
        return Result.no(item, f"unknown rule {p.get('rule')!r}")
    aid = p.get("artifact") or item.target.ref
    raw = ctx.artifact_text(aid, item.target.state)
    if raw is None:
        return Result.no(item, "feature.json absent")
    try:
        d = json.loads(M.strip_fence(raw[:MAX_TEXT])[0])
    except (ValueError, RecursionError):
        return Result.no(item, "not valid JSON")
    v = d.get("feature_directory") if isinstance(d, dict) else None
    if not isinstance(v, str) or not v.strip():
        return Result.no(item, "no feature_directory string")
    spec_path = ctx.facts.artifact_paths.get(str(p.get("feature_of") or "spec"))
    if not spec_path:
        return Result.no(item, "no feature directory to compare with (spec absent)")
    root = F.roots_of(ctx.rubric, ctx.collected.workdir).get("artifact") or "/"
    got = posixpath.normpath(v.strip() if v.strip().startswith("/") else posixpath.join(root, v.strip()))
    want = posixpath.dirname(spec_path)
    return Result.ok(item, got) if got == want else Result.no(item, f"{v.strip()[:80]!r} is not {want}")


# --------------------------------------------------------------------------------------------
# speckit.read
# --------------------------------------------------------------------------------------------
def read_steps(ctx: EvalContext, paths: list[str], w) -> dict[str, list[int]]:
    """Absolute path -> steps in the window that read it: an editor view of it, or a reading verb of a shell
    segment naming it (cwd, globs and loops resolved against the paths)."""
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    out: dict[str, list[int]] = {q: [] for q in paths}
    if not paths:
        return out
    wd = ctx.collected.workdir
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    known = sorted(paths)
    for step in ctx.run.steps:
        if not refs.in_window(step.n, w):
            continue
        for idx, a in enumerate(step.actions):
            hits: list[str] = []
            try:
                if a.kind == "view" and a.path:
                    hits = [shell.resolve(a.path, cwd_track.get((step.n, idx), wd))]
                elif a.kind == "shell" and a.command:
                    segs = shell.flat(shell.split(a.command[:20000], cwd_track.get((step.n, idx), wd))[0])
                    hits = [t for seg in segs for t in shell.read_targets(seg, known)]
            except Exception:  # noqa: BLE001 -- agent text: an unparsable command reads nothing
                hits = []
            for h in hits:
                h = posixpath.normpath(h)
                if h in out and step.n not in out[h]:
                    out[h].append(step.n)
    return out


@register("speckit.read", params={"artifacts": True, "window": False}, availability=("trace", "sandbox_file"), common=False)
def read(item: Item, ctx: EvalContext) -> Result:
    """Every listed artifact that exists at the end was read in the window (default: the item's stage);
    not_applicable when none of them exists."""
    p = item.check.params or {}
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    w = refs.window(ctx, spec)
    want = {a: ctx.facts.artifact_paths.get(a) for a in (p.get("artifacts") or []) if isinstance(a, str)}
    want = {a: q for a, q in want.items() if q}
    if not want:
        return Result.not_applicable(item, "none of the artifacts exists")
    if w is None:
        return Result.no(item, "window empty")
    hits = read_steps(ctx, sorted(set(want.values())), w)
    missing = [a for a, q in want.items() if not hits.get(q)]
    return Result.ratio(item, len(want) - len(missing), len(want), f"not read: {missing}" if missing else f"read: {sorted(want)}")


# --------------------------------------------------------------------------------------------
# speckit.holds
# --------------------------------------------------------------------------------------------
@register("speckit.holds", params={"predicate": True}, availability=("trace",), common=False)
def holds(item: Item, ctx: EvalContext) -> Result:
    """The refs predicate holds for the run (``exists`` / ``absent`` / ``counts`` / ``all`` ...)."""
    pred = (item.check.params or {}).get("predicate")
    return Result.ok(item, "holds") if refs.predicate(ctx, pred) else Result.no(item, "does not hold")


__all__ = ["task_lines_check", "tasks_done", "feature_json", "read", "holds", "task_lines", "phases", "named_paths", "tick_steps"]
