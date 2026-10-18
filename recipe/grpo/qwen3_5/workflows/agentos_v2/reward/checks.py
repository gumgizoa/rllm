"""agentos_v2 plugin kinds: the rules of an Agent OS run that the common kinds and the reference language cannot state.

The common kinds cover the skeletons (sections, labels, residue, line grammars), the command documents' reads, the
repository prohibitions and the test runs. What they cannot say:

* ``agentos_v2.holds`` -- a refs predicate as a check: the language has the facts (``exists: {fact: command |
  repo_edit | artifact_write}``) but only predicates use them; "the visuals folder was listed" or "requirements.md
  was not written after shape-spec" is a fact that must hold.
* ``agentos_v2.read`` -- every listed artifact that exists was read in the window (an editor view, or a reading verb
  naming its path): doc_read covers the workflow's own documents, not the run's artifacts.
* ``agentos_v2.repo_read`` -- a repository file whose repo-relative path fully matches one of ``patterns`` was read
  in the window (shape-spec Step 2: the README, the packaging metadata, the documentation index), by an editor view
  or a reading verb whose call showed content.
* ``agentos_v2.spec_folder`` -- exactly one spec folder under the artifact root (core-workflow.md: "shape-spec
  creates the spec folder once").
* ``agentos_v2.requirements`` -- requirements.md::

      {rule: answers}              every **Qn:** / **Follow-up n:** has its ``**Answer:** (assumed) <answer> —
                                   <basis>`` line (ratio)
      {rule: initial_description}  the Initial Description section holds initialization.md's text (ratio of its lines)

* ``agentos_v2.blocks`` -- a spec.md section of bold-named blocks (``**Specific requirement name**`` + bullets):
  between ``min_blocks`` and ``max_blocks`` blocks, each with 1 .. ``max_bullets`` bullets (ratio over blocks).
* ``agentos_v2.tasks`` -- tasks.md in Agent OS's shape (``#### Task Group N: <name>``, ``- [ ] N.M <task>``)::

      {rule: group_parts}        every task group has its **Dependencies:** and **Acceptance Criteria:** (ratio)
      {rule: test_first}         every task group but a test-review one starts with a test-writing sub-task (x.1) and
                                 ends with a sub-task that runs those tests (ratio)
      {rule: total}              ``Total Tasks: N`` counts the task lines (all, the sub-tasks or the groups)
      {rule: ticked}             share of the task lines ticked ``[x]`` (or marked ⚠️) when the window ends
      {rule: ticked_after_work}  every task ticked in the window was ticked inside it, after a write or a run of a
                                 path it names (ratio; a box ticked untraceably fails)
      {rule: groups_in_order}    the groups are ticked in order: group k's last tick is not after group k+1's first
                                 (ratio over adjacent pairs)
      {rule: later_edits}        every write of tasks.md in the window only ticks boxes or adds ⚠️ marks (ratio)

* ``agentos_v2.checks`` -- the check scripts under ``S/checks/`` (``dir``)::

      {rule: written}    a check script written in the window
      {rule: pass_last}  each check script run in the window last ran passing, after the window's last code change
                         (ratio; read off each execution's own result)

* ``agentos_v2.verify`` -- implement-tasks PHASE 3, which begins once every task is ticked (or marked ⚠️): the first
  write of tasks.md after which no task line is open (else the report's first write)::

      {rule: code_frozen}  no repository write after that point ("the code change is complete before PHASE 3")
      {rule: suite_run}    a valid test run between that point and the report's first write
      {rule: whole_suite}  one of those runs is the whole suite (a runner at the repository root selecting nothing,
                           or only top-level test directories)

* ``agentos_v2.report`` -- final-verification.md against tasks.md and the PHASE 3 runs::

      {rule: test_counts}        the Test Summary's Passing / Failing / Errors (and Total) are a PHASE 3 run's counts
      {rule: failed_listed}      every failing test that run names appears in the report (ratio)
      {rule: suite_status}       the Test Suite Results Status agrees with that run: All Passing only without failures
      {rule: tasks_status}       the Tasks Verification Status agrees with tasks.md: All Complete only when every task
                                 is ticked and none is marked ⚠️
      {rule: incomplete_listed}  a task marked ⚠️ in tasks.md is listed under Incomplete or Issues (not "None")
      {rule: spec_name}          the **Spec:** field names the spec folder

* ``agentos_v2.created_files`` / ``agentos_v2.paths_written`` -- no test / scratch file created in the repository;
  no file written at a path ``pattern`` names.

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import posixpath
import re

from recipe.grpo.qwen3_5.workflow_rubric import evidence as E
from recipe.grpo.qwen3_5.workflow_rubric import facts as F
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.replay import content_at
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

MAX_CMD = 20_000
MAX_TEXT = 400_000
_EXIT = re.compile(r"\[(?:The command completed with exit code|Command finished with exit code)\s+(-?\d+)\.?\]")
_FAIL_TEXT = re.compile(
    r"Traceback \(most recent call last\)|\bAssertionError\b|^\s*(?:FAIL|FAILED|ERROR)\b|\b\d+ (?:failed|errors?)\b|\bFAILED \(|"
    r"^\s*E\s{2,}\S|\b(?:Error|Exception):\s|\bcommand not found\b|\bNo such file or directory\b|\bcan't open file\b",
    re.M,
)
_PASS_TEXT = re.compile(r"\b\d+ passed\b|^\s*OK\b|\bPASS(?:ED)?\b|\ball (?:checks|tests) pass(?:ed)?\b|\bpassed\b", re.M | re.I)
_MARK_WORDS = re.compile(r"(?i)\b(?:fail\w*|error\w*|pass\w*|ok|traceback|assert\w*)\b")
_SCRIPT_EXT = re.compile(r"\.(?:py|sh|bash|js|mjs|cjs|ts|rb|pl|php)$")
_NOT_READ = re.compile(r"No such file or directory|cannot open|Is a directory|not found", re.I)
_WARN = "⚠"
# a task group heading (create-tasks.md:54 ``#### Task Group 1: Data Models and Migrations``)
_GROUP = re.compile(r"^#{2,6}\s+(?:\*\*)?Task\s+Group\s+(\d+)\b\s*[:.\-—–]?\s*(?P<title>.*?)(?:\*\*)?\s*$", re.I)
_HEAD = re.compile(r"^#{1,6}\s+\S")
# a task line: ``- [ ] 1.0 Complete database layer`` / ``  - [x] 1.1 Write 2-8 focused tests``; a ⚠️ mark in or after the box
_TASK = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?:\[(?P<box>[^\]\n]{0,4})\]\s*)?(?P<warn>(?:⚠️?|:warning:)\s*)?(?P<id>\d+(?:\.\d+)+)\b(?P<rest>.*)$")
_BOX = re.compile(r"^(\s*[-*+]\s+)\[[^\]\n]{0,4}\]")
_TEST_WORD = re.compile(r"(?i)\b(?:tests?|checks?|check\s+scripts?)\b")
_WRITE_WORD = re.compile(r"(?i)\b(?:write|add|create|author|draft)\b")
_RUN_WORD = re.compile(r"(?i)\b(?:run|ensure|verify|execute|confirm|re-?run)\b")
_REVIEW_GROUP = re.compile(r"(?i)\btest(?:s|ing)?\b.*\b(?:review|gap|coverage)\b|\b(?:review|gap|coverage)\b.*\btest")
_Q = re.compile(r"^\s*(?:[-*+]\s+)?\*\*\s*(?P<q>Q\s*\d+|Follow-?up\s*\d+)\s*:?\s*\*\*\s*:?", re.I)
_ANSWER = re.compile(r"^\s*(?:[-*+]\s+)?\*\*\s*Answer\s*:?\s*\*\*\s*:?\s*(?P<v>.*)$", re.I)
_ANSWER_OK = re.compile(r"^\(assumed\)\s+\S.*?\s(?:—|–|--?)\s+\S", re.I)
_BLOCK = re.compile(r"^\s*\*\*(?P<name>[^*\n]{1,200})\*\*\s*:?\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+\S")
_INT = re.compile(r"\d[\d,]*")
_PATHLIKE = re.compile(r"(?<![\w@:/.-])((?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)+/?|[\w-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?![\w/-])")
_CODE = re.compile(r"`([^`\n]+)`")
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
_SPEC_DOCS = frozenset({"spec.md", "tasks.md", "requirements.md", "initialization.md", "final-verification.md"})


# --------------------------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------------------------
def _window(item: Item, ctx: EvalContext):
    p = item.check.params or {}
    if "window" in p:
        return refs.window(ctx, p["window"])
    if item.stage == "global":
        return (1, ctx.facts.n_steps + 2)
    return refs.window(ctx, f"stage:{item.stage}")


def _artifact(item: Item, default: str | None = None) -> str:
    p = item.check.params or {}
    return str(p.get("artifact") or (item.target.ref if item.target.type == "artifact" else "") or default or "")


def _text(ctx: EvalContext, aid: str, state: str = "final") -> str | None:
    t = ctx.artifact_text(aid, state)
    return None if t is None else M.strip_fence(t[:MAX_TEXT])[0]


def _expand_dir(ctx: EvalContext, template: str) -> str | None:
    s, left = F.expand(template, F.roots_of(ctx.rubric, ctx.collected.workdir), ctx.collected.workdir, ctx.facts.var_bindings)
    return posixpath.normpath(s) if s.startswith("/") and not left else None


def _segments(ctx: EvalContext, c) -> list[shell.Segment]:
    key = ("agentos_v2.segments", c.step, c.action_index)
    if key not in ctx.cache:
        try:
            ctx.cache[key] = shell.flat(shell.split((c.command or "")[:MAX_CMD], c.cwd)[0])
        except Exception:  # noqa: BLE001 -- agent text: an unparsable command runs nothing we can attribute
            ctx.cache[key] = []
    return ctx.cache[key]


def _executed_by(seg: shell.Segment) -> set[str]:
    """Absolute paths the segment executes: a script it runs (``python x.py``, ``bash x.sh``, ``./x``) or a runner target."""
    out: set[str] = set()
    try:
        out |= {posixpath.normpath(p) for p in F._executed(seg) if p}
        hit = E.classify(seg)
        if hit is not None:
            out |= {posixpath.normpath(shell.resolve(t, seg.cwd)) for t in hit.targets if t}
    except Exception:  # noqa: BLE001 -- agent text
        pass
    return out


def _others_print(segs: list[shell.Segment], i: int, rx: re.Pattern) -> bool:
    """Could a segment other than ``i`` have printed text ``rx`` matches (its literal words, heredoc, stdin)?"""
    for j, s in enumerate(segs):
        if j == i:
            continue
        blob = " ".join(s.argv or []) + "\n" + (s.heredoc or "") + "\n" + (s.stdin_text or "")
        if rx.search(blob[:MAX_CMD]):
            return True
    return False


def _exit_code(observation: str) -> int | None:
    m = _EXIT.findall((observation or "")[-2000:])
    try:
        return int(m[-1]) if m else None
    except ValueError:
        return None


def outcome(segs: list[shell.Segment], i: int, observation: str, command: str = "") -> str | None:
    """``pass`` / ``fail`` / None (cannot tell) for segment ``i``'s run, by its call's own output: the exit code when the
    segment is the command's last, failure or pass text when no other segment could have printed such words."""
    obs = E.clean_observation(observation or "", command)
    body = _EXIT.sub("", obs)[-MAX_TEXT:]
    code = _exit_code(obs) if i == len(segs) - 1 else None
    foreign = _others_print(segs, i, _MARK_WORDS)
    failed_text = bool(_FAIL_TEXT.search(body)) and not foreign
    if code is not None:
        return "fail" if code != 0 or failed_text else "pass"
    if failed_text:
        return "fail"
    if not foreign and _PASS_TEXT.search(body) and not _FAIL_TEXT.search(body):
        return "pass"
    return None


def executions(ctx: EvalContext, paths: set[str]) -> dict[str, list[tuple[int, str | None]]]:
    """Absolute path -> [(step, outcome)] of every run of it, in order (the final call's observation is empty: None)."""
    out: dict[str, list[tuple[int, str | None]]] = {p: [] for p in paths}
    if not paths:
        return out
    for c in ctx.facts.commands:
        segs = _segments(ctx, c)
        for i, seg in enumerate(segs):
            hit = _executed_by(seg) & paths
            if not hit:
                continue
            res = outcome(segs, i, c.observation or "", c.command or "") if c.step < ctx.facts.n_steps else None
            for p in sorted(hit):
                out[p].append((c.step, res))
    return out


def _content_events(ctx: EvalContext, path: str) -> list:
    return [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]


def _change_steps(ctx: EvalContext, w) -> list[int]:
    """Steps of the writes to repository files that are part of the final change (run byproducts aside), in the window."""
    keep = F.change_paths(ctx)
    return sorted({e.step for e in ctx.facts.repo_writes if e.ok is not False and e.path in keep and not F.is_generated(e.path) and refs.in_window(e.step, w)})


def read_steps(ctx: EvalContext, paths: list[str], w) -> dict[str, list[int]]:
    """Absolute path -> steps in the window that read it: an editor view of it, or a reading verb of a shell segment
    naming it (cwd, globs and loops resolved against the paths)."""
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
                    segs = shell.flat(shell.split(a.command[:MAX_CMD], cwd_track.get((step.n, idx), wd))[0])
                    hits = [t for seg in segs for t in shell.read_targets(seg, known)]
            except Exception:  # noqa: BLE001 -- agent text: an unparsable command reads nothing
                hits = []
            for h in hits:
                h = posixpath.normpath(h)
                if h in out and step.n not in out[h]:
                    out[h].append(step.n)
    return out


# --------------------------------------------------------------------------------------------
# agentos_v2.holds / read / repo_read / spec_folder
# --------------------------------------------------------------------------------------------
@register("agentos_v2.holds", params={"predicate": True}, availability=("trace",), common=False)
def holds(item: Item, ctx: EvalContext) -> Result:
    """The refs predicate holds for the run (``exists`` / ``absent`` / ``counts`` / ``all`` ...)."""
    pred = (item.check.params or {}).get("predicate")
    return Result.ok(item, "holds") if refs.predicate(ctx, pred) else Result.no(item, "does not hold")


@register("agentos_v2.read", params={"artifacts": True, "window": False}, availability=("trace", "sandbox_file"), common=False)
def read(item: Item, ctx: EvalContext) -> Result:
    """Every listed artifact that exists at the end was read in the window (default: the item's stage).

    not_applicable when none of them exists."""
    p = item.check.params or {}
    w = _window(item, ctx)
    want = {a: ctx.facts.artifact_paths.get(a) for a in (p.get("artifacts") or []) if isinstance(a, str)}
    want = {a: q for a, q in want.items() if q}
    if not want:
        return Result.not_applicable(item, "none of the artifacts exists")
    if w is None:
        return Result.no(item, "window empty")
    hits = read_steps(ctx, sorted(set(want.values())), w)
    missing = [a for a, q in want.items() if not hits.get(q)]
    return Result.ratio(item, len(want) - len(missing), len(want), f"not read: {missing}" if missing else f"read: {sorted(want)}")


def _repo_reads(ctx: EvalContext, w) -> list[tuple[int, str]]:
    """(step, repo-relative path) of every repository file an editor view or a reading verb opened in the window, when
    that call's output was not a 'no such file' error."""
    wd = (ctx.collected.workdir or "").rstrip("/")
    if not wd:
        return []
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    out: list[tuple[int, str]] = []
    for step in ctx.run.steps:
        if not refs.in_window(step.n, w):
            continue
        for idx, a in enumerate(step.actions):
            targets: list[str] = []
            try:
                cwd = cwd_track.get((step.n, idx), wd)
                if a.kind == "view" and a.path:
                    targets = [shell.resolve(a.path, cwd)]
                elif a.kind == "shell" and a.command:
                    for seg in shell.flat(shell.split(a.command[:MAX_CMD], cwd)[0]):
                        if seg.verb in ("cat", "head", "tail", "less", "more", "nl", "bat", "sed", "awk", "view"):
                            for wd_ in seg.cmd_words[1:]:
                                t = wd_.text
                                if t and not t.startswith("-") and "/" not in t[:1] or (t and t.startswith("/")):
                                    targets.append(shell.resolve(t, seg.cwd or cwd))
            except Exception:  # noqa: BLE001 -- agent text
                targets = []
            obs = a.observation or ""
            if not obs.strip() or (_NOT_READ.search(obs[:300]) and len(obs) < 400):
                continue
            for t in targets:
                t = posixpath.normpath(t)
                if t.startswith(wd + "/"):
                    out.append((step.n, t[len(wd) + 1 :]))
    return out


@register("agentos_v2.repo_read", params={"patterns": True, "window": False}, availability=("trace",), common=False)
def repo_read(item: Item, ctx: EvalContext) -> Result:
    """For each regex of ``patterns``, a repository file whose repo-relative path fully matches it was read in the window.

    Case-insensitive; ratio over the patterns."""
    p = item.check.params or {}
    pats = [p["patterns"]] if isinstance(p["patterns"], str) else list(p["patterns"])
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    reads = _repo_reads(ctx, w)
    got, miss = 0, []
    for pat in pats:
        rx = re.compile(str(pat), re.I)
        hit = next(((s, q) for s, q in reads if rx.fullmatch(q)), None)
        if hit:
            got += 1
        else:
            miss.append(str(pat))
    return Result.ratio(item, got, len(pats), f"not read: {miss[:3]}" if miss else f"{got} read")


@register("agentos_v2.spec_folder", params={"root": False}, availability=("sandbox_file",), common=False)
def spec_folder(item: Item, ctx: EvalContext) -> Result:
    """Exactly one directory directly under the artifact root (``root``, default ``{artifact}``) at the end of the run."""
    root = _expand_dir(ctx, str((item.check.params or {}).get("root") or "{artifact}"))
    if not root:
        return Result.no(item, "no artifact root")
    pool = set(ctx.collected.dirs) | {posixpath.dirname(q) for q in ctx.collected.files}
    pre = root.rstrip("/") + "/"
    found = sorted({pre + d[len(pre) :].split("/", 1)[0] for d in pool if d.startswith(pre) and d[len(pre) :]})
    names = [posixpath.basename(d) for d in found]
    if len(found) == 1:
        return Result.ok(item, names[0])
    return Result.no(item, f"{len(found)} spec folders: {names[:5]}")


# --------------------------------------------------------------------------------------------
# agentos_v2.requirements / blocks
# --------------------------------------------------------------------------------------------
def _norm_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", ln).strip() for ln in (text or "").splitlines() if ln.strip()]


@register("agentos_v2.requirements", params={"rule": True, "artifact": False}, availability=("sandbox_file",), common=False, choices={"rule": ("answers", "initial_description")})
def requirements(item: Item, ctx: EvalContext) -> Result:
    """rule: answers | initial_description -- each question's assumed answer with its basis; the raw idea quoted."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    text = _text(ctx, _artifact(item, "requirements"))
    if text is None:
        return Result.no(item, "requirements.md absent")
    if rule == "answers":
        lines = M.text_lines(text)
        qs: list[tuple[str, str | None]] = []
        for ln in lines:
            m = _Q.match(ln)
            if m:
                qs.append((re.sub(r"\s+", "", m.group("q")), None))
                continue
            if _HEAD.match(ln):
                if qs and qs[-1][1] is None:
                    qs[-1] = (qs[-1][0], "")
                continue
            a = _ANSWER.match(ln)
            if a and qs and qs[-1][1] is None:
                qs[-1] = (qs[-1][0], M.clean_value(a.group("v")) if a.group("v") else a.group("v"))
        if not qs:
            return Result.no(item, "no **Qn:** question")
        bad = [q for q, v in qs if not v or not _ANSWER_OK.match(v.strip())]
        return Result.ratio(item, len(qs) - len(bad), len(qs), f"without '(assumed) <answer> — <basis>': {bad[:5]}" if bad else f"{len(qs)} answers assumed with a basis")
    if rule == "initial_description":
        init = _text(ctx, "initialization")
        if init is None or not init.strip():
            return Result.no(item, "initialization.md absent or empty")
        sec = M.section(text, "Initial Description")
        if sec is None:
            return Result.no(item, "no Initial Description section")
        want = _norm_lines(init)
        hay = " ".join(_norm_lines(sec))
        got = [ln for ln in want if ln in hay]
        return Result.ratio(item, len(got), len(want), f"{len(got)}/{len(want)} lines of initialization.md")
    return Result.no(item, f"unknown rule {rule!r}")


@register("agentos_v2.blocks", params={"section": True, "artifact": False, "min_blocks": False, "max_blocks": False, "max_bullets": False}, availability=("sandbox_file",), common=False)
def blocks(item: Item, ctx: EvalContext) -> Result:
    """The section's bold-named blocks (a ``**name**`` line, then bullets) number min_blocks (1) .. max_blocks, each with 1 .. max_bullets bullets.

    Ratio over the blocks; a block count out of range fails."""
    p = item.check.params or {}
    text = _text(ctx, _artifact(item))
    if text is None:
        return Result.no(item, "artifact absent")
    sec = M.section(text, str(p["section"]))
    if sec is None:
        return Result.no(item, f"no {p['section']!r} section")
    found: list[tuple[str, int]] = []
    for ln in M.text_lines(sec):
        m = _BLOCK.match(ln)
        if m:
            found.append((m.group("name").strip(), 0))
        elif _BULLET.match(ln) and found:
            found[-1] = (found[-1][0], found[-1][1] + 1)
    lo, hi = int(p.get("min_blocks", 1)), p.get("max_blocks")
    if len(found) < lo:
        return Result.no(item, f"{len(found)} blocks < {lo}")
    if hi is not None and len(found) > int(hi):
        return Result.no(item, f"{len(found)} blocks > {hi}")
    mb = p.get("max_bullets")
    bad = [n for n, k in found if k < 1 or (mb is not None and k > int(mb))]
    if not found:
        return Result.ok(item, "no block (none required)")
    return Result.ratio(item, len(found) - len(bad), len(found), f"blocks without 1..{mb} bullets: {[b[:30] for b in bad[:3]]}" if bad else f"{len(found)} blocks")


# --------------------------------------------------------------------------------------------
# tasks.md
# --------------------------------------------------------------------------------------------
def task_lines(text: str | None) -> list[dict]:
    """Every task line of tasks.md (outside fences and comments), with the task group it sits under."""
    out: list[dict] = []
    if not text:
        return out
    group: dict | None = None
    for line in M.text_lines(text[:MAX_TEXT]):
        line = line[:2000]
        if _HEAD.match(line):
            m = _GROUP.match(line.strip())
            group = {"n": int(m.group(1)), "title": (m.group("title") or "").strip(), "heading": line.strip()} if m else None
            continue
        m = _TASK.match(line)
        if not m:
            continue
        box = m.group("box")
        warned = _WARN in (box or "") or bool(m.group("warn")) or _WARN in m.group("rest")[:8]
        out.append(
            {
                "id": m.group("id"),
                "box": box,
                "checked": (box or "").strip() in ("x", "X"),
                "warned": warned,
                "line": line,
                "rest": m.group("rest"),
                "group": group,
            }
        )
    return out


def groups(text: str | None) -> list[tuple[dict, list[str]]]:
    """(group, its body lines) for every task group heading of tasks.md, in order."""
    out: list[tuple[dict, list[str]]] = []
    cur: list[str] | None = None
    for line in M.text_lines((text or "")[:MAX_TEXT]):
        line = line[:2000]
        if _HEAD.match(line):
            m = _GROUP.match(line.strip())
            if m:
                cur = []
                out.append(({"n": int(m.group(1)), "title": (m.group("title") or "").strip(), "heading": line.strip()}, cur))
            elif re.match(r"^#{1,3}\s", line):
                cur = None
            continue
        if cur is not None:
            cur.append(line)
    return out


def _done(t: dict) -> bool:
    return t["checked"] or t["warned"]


def tick_steps(ctx: EvalContext, aid: str) -> dict[str, int | None]:
    """Task id -> the step of the write after which its box is first ticked or marked (``UNKNOWN``: a write whose content
    cannot be replayed precedes the first seen tick)."""
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
            if _done(t) and t["id"] not in out:
                out[t["id"]] = UNKNOWN if blind else e.step
    return out


def all_done_step(ctx: EvalContext, aid: str = "tasks"):
    """The first write of tasks.md after which it has task lines and every one is ticked or marked ⚠️ (None: never;
    ``UNKNOWN``: a write that cannot be replayed comes first)."""
    path = ctx.facts.artifact_paths.get(aid)
    if not path:
        return None
    blind = False
    for e in ctx.facts.writes.get(path, []):
        if e.ok is False or e.op in ("delete", "move_out"):
            continue
        if e.content is None:
            blind = True
            continue
        ts = task_lines(e.content)
        if ts and all(_done(t) for t in ts):
            return UNKNOWN if blind else e.step
    if ctx.facts.final_mismatch.get(path):
        ts = task_lines(_text(ctx, aid))
        if ts and all(_done(t) for t in ts):
            return UNKNOWN
    return None


def _text_at(ctx: EvalContext, path: str | None, step: int) -> str | None:
    if not path:
        return None
    return content_at([e for e in ctx.facts.writes.get(path, []) if e.ok is not False], step)


def _window_end_text(ctx: EvalContext, aid: str, w) -> str | None:
    """tasks.md at the end of the window: replayed, or the final file when nothing wrote it later."""
    path = ctx.facts.artifact_paths.get(aid)
    if not path:
        return None
    end = (w[1] if w[1] is not None else ctx.facts.n_steps + 2) - 1
    evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False]
    if not any(e.step > end for e in evs) and not ctx.facts.final_mismatch.get(path):
        return _text(ctx, aid)
    t = content_at(evs, end)
    return None if t is None else M.strip_fence(t[:MAX_TEXT])[0]


def named_paths(desc: str, workdir: str | None) -> set[str]:
    """Paths a task names: repository-relative ones (code spans first, then bare path tokens) and absolute ``/tmp`` ones."""
    s = _URL.sub(" ", desc or "")[:2000]
    cands = [*_CODE.findall(s), *(m.group(1) for m in _PATHLIKE.finditer(_CODE.sub(" ", s)))]
    out = set()
    for c in cands:
        c = c.strip().strip(".,;:()'\"")
        if not c or " " in c or c.startswith(("http", "-")):
            continue
        if c.startswith("/tmp/"):
            out.add(posixpath.normpath(c))
            continue
        q = refs.norm_path(c, workdir).rstrip("/")
        if not q or posixpath.basename(q) in _SPEC_DOCS or q.startswith(("agent-os/", "tmp/")):
            continue
        if "/" not in q and not re.search(r"\.[A-Za-z][A-Za-z0-9]{0,7}$", q):
            continue
        out.add(q)
    return out


def _evidence_steps(ctx: EvalContext, paths: set[str], checks_dir: str | None) -> list[int]:
    """Steps that wrote or ran one of ``paths`` (repository-relative, absolute, or ``checks/<name>`` under the checks dir)."""
    wd = (ctx.collected.workdir or "").rstrip("/")
    absolute = set()
    for q in paths:
        if q.startswith("/"):
            absolute.add(q)
        elif checks_dir and q.startswith("checks/"):
            absolute.add(posixpath.join(posixpath.dirname(checks_dir), q))
        else:
            absolute.add(f"{wd}/{q}")
    steps = [e.step for q in absolute for e in ctx.facts.writes.get(q, []) if e.ok is not False]
    steps += [e.step for e in ctx.facts.repo_writes if e.ok is not False and e.path in paths]
    steps += [st for st, path in F.executed_paths(ctx) if path in paths or path in absolute or (wd and f"{wd}/{path}" in absolute)]
    return steps


def _norm_box(text: str) -> list[str]:
    out = []
    for ln in (text or "").replace("\r\n", "\n").rstrip().split("\n"):
        ln = _BOX.sub(r"\1[ ]", ln.rstrip())
        ln = re.sub(r"\s*(?:⚠️?|:warning:)\s*", " ", ln).rstrip()
        out.append(ln)
    return out


def _prior(ctx: EvalContext, path: str, e) -> str | None:
    prev = None
    for x in ctx.facts.writes.get(path, []):
        if x.ok is False:
            continue
        if x is e:
            break
        prev = x
    return None if prev is None else prev.content


@register(
    "agentos_v2.tasks",
    params={"rule": True, "artifact": False, "window": False, "dir": False},
    availability=("sandbox_file", "trace"),
    common=False,
    choices={"rule": ("group_parts", "test_first", "total", "ticked", "ticked_after_work", "groups_in_order", "later_edits")},
)
def tasks(item: Item, ctx: EvalContext) -> Result:
    """rule: group_parts | test_first | total | ticked | ticked_after_work | groups_in_order | later_edits -- tasks.md's task groups, test sub-tasks, count, and its ticks against the work."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = _artifact(item, "tasks")
    if rule in ("group_parts", "test_first", "total"):
        text = _text(ctx, aid, item.target.state or "final")
        if text is None:
            return Result.no(item, "tasks.md absent")
        gs = groups(text)
        if rule == "group_parts":
            if not gs:
                return Result.no(item, "no '#### Task Group N:' heading")
            have = 0
            miss = []
            for g, body in gs:
                blob = "\n".join(body)
                for lab in ("Dependencies", "Acceptance Criteria"):
                    if M.field_value(blob, lab) is not None or re.search(rf"(?im)^\s*\*\*{lab}:?\*\*", blob):
                        have += 1
                    else:
                        miss.append(f"{g['n']}:{lab}")
            return Result.ratio(item, have, 2 * len(gs), f"missing {miss[:4]}" if miss else f"{len(gs)} groups with Dependencies and Acceptance Criteria")
        if rule == "test_first":
            ts = task_lines(text)
            pool = [(g, [t for t in ts if t["group"] and t["group"]["heading"] == g["heading"] and not t["id"].endswith(".0")]) for g, _ in gs]
            pool = [(g, subs) for g, subs in pool if not _REVIEW_GROUP.search(g["title"])]
            if not pool:
                return Result.no(item, "no implementation task group")
            good, bad = 0, []
            for g, subs in pool:
                first_ok = bool(subs) and bool(_TEST_WORD.search(subs[0]["rest"])) and bool(_WRITE_WORD.search(subs[0]["rest"]))
                last_ok = len(subs) >= 2 and bool(_TEST_WORD.search(subs[-1]["rest"])) and bool(_RUN_WORD.search(subs[-1]["rest"]))
                good += first_ok + last_ok
                if not first_ok:
                    bad.append(f"group {g['n']}: first sub-task writes no tests")
                if not last_ok:
                    bad.append(f"group {g['n']}: last sub-task runs no tests")
            return Result.ratio(item, good, 2 * len(pool), "; ".join(bad[:2]) if bad else f"{len(pool)} groups test first, run last")
        ts = task_lines(text)
        m = re.search(r"(?im)^\s*(?:[-*+]\s+)?(?:\*\*)?Total\s+Tasks(?:\*\*)?\s*:?\s*(?:\*\*)?\s*(\d+)", text)
        if not m:
            return Result.no(item, "no 'Total Tasks: N' line")
        n = int(m.group(1))
        counts = {len(ts), len([t for t in ts if not t["id"].endswith(".0")]), len(gs)}
        return Result.ok(item, f"Total Tasks {n}") if n in counts and n > 0 else Result.no(item, f"Total Tasks {n} counts none of {sorted(counts)}")
    w = _window(item, ctx)
    path = ctx.facts.artifact_paths.get(aid)
    if path is None:
        return Result.no(item, "tasks.md absent")
    if w is None:
        return Result.no(item, "window empty")
    if rule == "ticked":
        text = _window_end_text(ctx, aid, w)
        if text is None:
            return Result.no(item, "tasks.md unknown at the end of the window")
        ts = task_lines(text)
        if not ts:
            return Result.no(item, "no task line")
        done = sum(1 for t in ts if _done(t))
        return Result.ratio(item, done, len(ts), f"{done}/{len(ts)} ticked or marked")
    if rule in ("ticked_after_work", "groups_in_order"):
        text = _window_end_text(ctx, aid, w)
        if text is None:
            return Result.no(item, "tasks.md unknown at the end of the window")
        before = _text_at(ctx, path, w[0] - 1) or ""
        was = {t["id"] for t in task_lines(before) if _done(t)}
        pool = [t for t in task_lines(text) if _done(t) and t["id"] not in was]
        if not pool:
            return Result.not_applicable(item, "no task ticked in the window")
        when = tick_steps(ctx, aid)
        if rule == "groups_in_order":
            by: dict[int, list[int]] = {}
            for t in pool:
                s = when.get(t["id"])
                if t["group"] and s is not None and s is not UNKNOWN:
                    by.setdefault(t["group"]["n"], []).append(s)
            ns = sorted(by)
            if len(ns) < 2:
                return Result.not_applicable(item, "fewer than two groups ticked")
            pairs = list(zip(ns, ns[1:], strict=False))
            good = [a for a, b in pairs if max(by[a]) <= min(by[b]) and (max(by[a]) < min(by[b]) or len(by[a]) + len(by[b]) <= 2)]
            return Result.ratio(item, len(good), len(pairs), f"{len(good)}/{len(pairs)} adjacent groups ticked in order")
        d = _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None
        bad = []
        for t in pool:
            s = when.get(t["id"])
            if s is None or s is UNKNOWN or not refs.in_window(s, w):
                bad.append(t["id"])
                continue
            named = named_paths(t["rest"], ctx.collected.workdir)
            if named and not any(w[0] <= x <= s for x in _evidence_steps(ctx, named, d)):
                bad.append(t["id"])
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"ticked before (or without) the work it names: {bad[:5]}" if bad else f"{len(pool)} ticks after their work")
    if rule == "later_edits":
        evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
        edits = [e for e in evs if refs.in_window(e.step, w) and e is not evs[0]]
        if not edits:
            return Result.ok(item, "tasks.md not edited in the window")
        good, bad = 0, []
        for e in edits:
            prev, new = _prior(ctx, path, e), e.content
            if prev is None or new is None:
                bad.append(f"step {e.step}: content unknown")
                continue
            if _norm_box(prev) == _norm_box(new):
                good += 1
            else:
                bad.append(f"step {e.step}: {e.op} changes the tasks")
        return Result.ratio(item, good, len(edits), "; ".join(bad[:2]) if bad else f"{good} write(s): ticks only")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# agentos_v2.checks
# --------------------------------------------------------------------------------------------
def check_scripts(ctx: EvalContext, d: str, upto: int | None = None) -> list[str]:
    """Script files under ``d`` the trace wrote (a content write at or before ``upto``)."""
    pre = d.rstrip("/") + "/"
    out = []
    for path, evs in ctx.facts.writes.items():
        if not path.startswith(pre) or not _SCRIPT_EXT.search(path) or "__pycache__" in path:
            continue
        if any(e.ok is not False and e.op in F.WRITE_OPS and (upto is None or e.step <= upto) for e in evs):
            out.append(path)
    return sorted(out)


@register("agentos_v2.checks", params={"rule": True, "window": False, "dir": True}, availability=("trace",), common=False, choices={"rule": ("written", "pass_last")})
def checks(item: Item, ctx: EvalContext) -> Result:
    """rule: written | pass_last -- the check scripts under ``dir``: written in the window; each one run in the window last ran passing, after the window's last code change."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    d = _expand_dir(ctx, str(p["dir"]))
    w = _window(item, ctx)
    if d is None:
        return Result.no(item, "no checks directory (spec folder unbound)")
    if w is None:
        return Result.no(item, "window empty")
    end = w[1] if w[1] is not None else ctx.facts.n_steps + 2
    if rule == "written":
        got = [s for s in check_scripts(ctx, d) if any(refs.in_window(e.step, w) for e in _content_events(ctx, s))]
        return Result.ok(item, f"{len(got)} written: {[posixpath.basename(s) for s in got][:3]}") if got else Result.no(item, f"no script written under {d}/ in the window")
    scripts = check_scripts(ctx, d, upto=end - 1)
    runs = executions(ctx, set(scripts))
    runs = {s: [(st, o) for st, o in r if refs.in_window(st, w)] for s, r in runs.items()}
    pool = [s for s in scripts if runs.get(s)]
    if not pool:
        return Result.no(item, f"no check script under {d}/ run in the window")
    changes = _change_steps(ctx, w)
    last_change = changes[-1] if changes else w[0]
    good, bad = 0, []
    for s in pool:
        rs = runs[s]
        ok = rs[-1][1] == "pass" and rs[-1][0] > last_change
        good += ok
        if not ok:
            bad.append(posixpath.basename(s))
    return Result.ratio(item, good, len(pool), f"not passing after the last code change (step {last_change}): {bad[:3]}" if bad else f"{good} script(s) pass after step {last_change}")


# --------------------------------------------------------------------------------------------
# agentos_v2.verify / report (implement-tasks PHASE 3)
# --------------------------------------------------------------------------------------------
def phase3_start(ctx: EvalContext):
    """Where PHASE 3 begins: every task ticked or marked (else the report's first write; None without either)."""
    s = all_done_step(ctx)
    if s is not None:
        return s
    return refs.event(ctx, "first_write:final_verification") if "final_verification" in ctx.rubric.artifacts else None


def phase3_window(ctx: EvalContext):
    """[PHASE 3 start, the report's first write) -- to the end of the run when the report was never written."""
    a = phase3_start(ctx)
    if a is None:
        return None
    a = 1 if a is UNKNOWN else a
    b = refs.event(ctx, "first_write:final_verification") if "final_verification" in ctx.rubric.artifacts else None
    if b is None or b is UNKNOWN:
        b = ctx.facts.n_steps + 1
    return (a, b) if a < b else None


def _phase3_runs(ctx: EvalContext) -> list:
    w = phase3_window(ctx)
    return [r for r in ctx.facts.runs if r.valid and r.kind == "test" and refs.in_window(r.step, w)] if w else []


def _whole(r, workdir: str | None) -> bool:
    try:
        segs = shell.flat(shell.split(r.segment or r.command, workdir)[0])
    except Exception:  # noqa: BLE001
        segs = []
    if any(E.full_suite(s, workdir) for s in segs):
        return True
    ts = [refs.norm_path(t, workdir).rstrip("/") for t in (r.targets or [])]
    return bool(ts) and all("/" not in t and "::" not in t and "." not in t and re.match(r"(?i)^(?:tests?|testing|t)$", t) for t in ts)


@register("agentos_v2.verify", params={"rule": True}, availability=("trace",), common=False, choices={"rule": ("code_frozen", "suite_run", "whole_suite")})
def verify(item: Item, ctx: EvalContext) -> Result:
    """rule: code_frozen | suite_run | whole_suite -- PHASE 3 (from every task ticked to the report): no repository write after it begins; a valid test run in it; one of them the whole suite."""
    rule = str((item.check.params or {}).get("rule"))
    start = phase3_start(ctx)
    if start is None:
        return Result.no(item, "PHASE 3 never began (tasks not all ticked, no report)")
    if rule == "code_frozen":
        if ctx.facts.unseen_repo_paths:
            return Result.no(item, "a repository change the trace does not show: its time is unknown")
        s = 1 if start is UNKNOWN else start
        late = [e for e in ctx.facts.repo_writes if e.ok is not False and e.step > s and not F.is_generated(e.path)]
        return Result.no(item, f"step {late[0].step}: {late[0].op} {late[0].path} after PHASE 3 began (step {s})") if late else Result.ok(item, f"no repository write after step {s}")
    runs = _phase3_runs(ctx)
    if rule == "suite_run":
        return Result.ok(item, f"{len(runs)} valid test run(s) in PHASE 3, first at step {runs[0].step}") if runs else Result.no(item, "no valid test run between the last tick and the report")
    if rule == "whole_suite":
        wd = ctx.collected.workdir
        whole = [r for r in runs if _whole(r, wd)]
        return Result.ok(item, f"step {whole[0].step}: {whole[0].segment[:60]}") if whole else Result.no(item, f"{len(runs)} PHASE 3 run(s), none of the whole suite")
    return Result.no(item, f"unknown rule {rule!r}")


def _num(v: str | None) -> int | None:
    if v is None:
        return None
    m = _INT.search(M.clean_value(v))
    try:
        return int(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


def _status(text: str, section: str) -> str:
    body = M.section(text, section, match="prefix") if section else text
    v = M.field_value(body or "", "Status") if body is not None else None
    return M.clean_value(v or "")


@register(
    "agentos_v2.report",
    params={"rule": True, "artifact": False},
    availability=("sandbox_file", "trace"),
    common=False,
    choices={"rule": ("test_counts", "failed_listed", "suite_status", "tasks_status", "incomplete_listed", "spec_name")},
)
def report(item: Item, ctx: EvalContext) -> Result:
    """rule: test_counts | failed_listed | suite_status | tasks_status | incomplete_listed | spec_name -- final-verification.md against the PHASE 3 runs, tasks.md and the spec folder."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    text = _text(ctx, _artifact(item, "final_verification"))
    if text is None:
        return Result.no(item, "final-verification.md absent")
    if rule in ("test_counts", "failed_listed", "suite_status"):
        runs = _phase3_runs(ctx)
        if not runs:
            return Result.no(item, "no valid PHASE 3 test run to compare with")
        summ = M.section(text, "Test Summary") or M.section(text, "4. Test Suite Results", match="prefix") or text
        got = {k: _num(M.field_value(summ, k)) for k in ("Total Tests", "Passing", "Failing", "Errors")}

        def score(r) -> int:
            tot = {r.passed + r.failed + r.errors, r.passed + r.failed + r.errors + r.skipped, max(r.collected, 0)}
            return sum([got["Passing"] == r.passed, got["Failing"] == r.failed, got["Errors"] == r.errors, got["Total Tests"] in tot])

        best = max(runs, key=lambda r: (score(r), r.step))
        if rule == "test_counts":
            if all(v is None for v in got.values()):
                return Result.no(item, "no Total Tests / Passing / Failing / Errors counts")
            k = score(best)
            return Result.ratio(item, k, 4, f"step {best.step}: {best.passed} passed / {best.failed} failed / {best.errors} errors vs {got}")
        if rule == "suite_status":
            st = _status(text, "4. Test Suite Results")
            if not st:
                return Result.no(item, "no Test Suite Results Status")
            bad = best.failed + best.errors
            if re.search(r"(?i)all\s+passing", st):
                return Result.ok(item, "All Passing, no failure") if bad == 0 else Result.no(item, f"All Passing, but step {best.step} has {bad} failures / errors")
            if re.search(r"(?i)some\s+failures|critical\s+failures", st):
                return Result.ok(item, f"{st[:30]}: {bad} failures / errors") if bad > 0 else Result.no(item, f"{st[:30]}, but step {best.step} has no failure")
            return Result.no(item, f"Status {st[:40]!r} is none of the three")
        fails = [r for r in runs if r.failed + r.errors > 0]
        if not fails:
            return Result.not_applicable(item, "no failing test in the PHASE 3 runs")
        r = max(fails, key=lambda x: x.step)
        ids = E.failing_ids(r.observation or "")
        if not ids:
            sec = M.section(text, "Failed Tests") or ""
            listed = [ln for ln in M.content_lines(sec) if ln.strip() and not M.is_none(ln.strip("-* "))]
            return Result.ok(item, "failures named in the report") if listed else Result.no(item, f"step {r.step} failed, Failed Tests lists nothing")
        good = [i for i in ids if any(form in text for form in refs.id_forms(i))]
        return Result.ratio(item, len(good), len(ids), f"{len(good)}/{len(ids)} failing tests named")
    if rule in ("tasks_status", "incomplete_listed"):
        ts = task_lines(_text(ctx, "tasks"))
        if not ts:
            return Result.no(item, "tasks.md absent or without task lines")
        open_ = [t["id"] for t in ts if not t["checked"] or t["warned"]]
        if rule == "tasks_status":
            st = _status(text, "1. Tasks Verification")
            if re.search(r"(?i)all\s+complete", st):
                return Result.ok(item, "All Complete, every task ticked") if not open_ else Result.no(item, f"All Complete, but open / marked: {open_[:4]}")
            if re.search(r"(?i)issues\s+found", st):
                return Result.ok(item, "Issues Found") if open_ else Result.no(item, "Issues Found, but every task is ticked")
            return Result.no(item, f"Status {st[:40]!r} is neither All Complete nor Issues Found")
        warned = [t["id"] for t in ts if t["warned"]]
        if not warned:
            return Result.not_applicable(item, "no task marked ⚠️")
        sec = M.section(text, "Incomplete or Issues")
        lines = [ln for ln in M.content_lines(sec or "") if ln.strip() and not M.is_none(ln.strip("-* \"'"))]
        return Result.ok(item, f"{len(lines)} line(s) listed") if lines else Result.no(item, f"tasks marked ⚠️ {warned[:3]}, but Incomplete or Issues lists none")
    if rule == "spec_name":
        path = ctx.facts.artifact_paths.get("spec_dir") or ""
        name = posixpath.basename(path.rstrip("/"))
        v = M.field_value(text, "Spec")
        if not name:
            return Result.no(item, "no spec folder")
        if v is None:
            return Result.no(item, "no **Spec:** field")
        short = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
        return Result.ok(item, v[:60]) if name in v or (short and short in v) else Result.no(item, f"{v[:60]!r} does not name {name}")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# agentos_v2.created_files / paths_written
# --------------------------------------------------------------------------------------------
@register("agentos_v2.created_files", params={"pattern": False, "test_paths": False, "window": False}, availability=("trace",), common=False)
def created_files(item: Item, ctx: EvalContext) -> Result:
    """No file the run created in the repository (absent at BASE_SHA) is a test file (``test_paths``) or matches ``pattern``, written in the window."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"])) if p.get("pattern") else None
    hits = []
    for e in ctx.facts.repo_writes:
        if e.ok is False or not refs.in_window(e.step, w) or not F.is_new_path(ctx, e.path):
            continue
        if p.get("test_paths") is not None and F.is_test_path(e.path) != bool(p["test_paths"]):
            continue
        if rx is not None and not rx.search(e.path):
            continue
        hits.append(f"step {e.step}: {e.op} {e.path}")
    return Result.no(item, f"{len(hits)} created: {hits[0]}") if hits else Result.ok(item, "none created")


@register("agentos_v2.paths_written", params={"pattern": True, "window": False}, availability=("trace",), common=False)
def paths_written(item: Item, ctx: EvalContext) -> Result:
    """No content write of the trace in the window lands at an absolute path ``pattern`` matches."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"]))
    hits = [f"step {e.step}: {e.op} {path}" for path, evs in ctx.facts.writes.items() if rx.search(path) for e in evs if e.ok is not False and e.op in F.WRITE_OPS and refs.in_window(e.step, w)]
    return Result.no(item, f"{len(hits)} write(s): {sorted(hits)[0]}") if hits else Result.ok(item, "none written")


__all__ = [
    "holds",
    "read",
    "repo_read",
    "spec_folder",
    "requirements",
    "blocks",
    "tasks",
    "checks",
    "verify",
    "report",
    "created_files",
    "paths_written",
    "task_lines",
    "groups",
    "tick_steps",
    "all_done_step",
    "phase3_window",
    "outcome",
    "executions",
]
