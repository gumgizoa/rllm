"""speckit_sdd plugin kinds: the rules of a run that drives Spec Kit's own scripts and writes its checks first.

The common kinds cover the templates (sections, labels, residue, line grammars), the stage documents' reads,
the repository prohibitions and the test runs; ``workflows/spec_kit``'s ``speckit.*`` kinds -- the tasks.md line
rules by phase (``speckit.task_lines``), the artifact reads (``speckit.read``), a refs predicate as a check
(``speckit.holds``) -- are imported here (vendored as ``speckit_kinds.py``) and used as they are. What neither can say:

* ``speckit_sdd.script`` -- a shipped script (``/tmp/speckit-sdd/.specify/scripts/bash/<name>``) ran *at its
  shipped path* with the flags the stage names, and succeeded by its own call's output: the exit-code line the
  terminal appends (when the script is the command's last segment), else its JSON keys (``FEATURE_DIR`` ...) in the
  observation with no other segment able to print them. An ``echo`` of the JSON, a copy run from elsewhere or a
  failed run is no run.
* ``speckit_sdd.untouched`` -- nothing the trace does writes under the shipped trees (``prefixes``: the scripts,
  templates and constitution, core-workflow.md:18-19); an edited script would fake its own output.
* ``speckit_sdd.checks`` -- the verification scripts under ``FEATURE_DIR/checks/`` against the code change, read off
  each execution's own result (exit code when attributable, else failure / pass text no other segment printed)::

      {rule: written}      a check script written in the window
      {rule: red_green}    each verification script (the ones tasks.md names, else every executed one) ran failing,
                           then -- after a code change and with the script itself unchanged -- passing (ratio)
      {rule: before_code}  a check script ran failing before the window's first code change
      {rule: pass_last}    each verification script's last run in the window passes, after the window's last code
                           change (ratio)

* ``speckit_sdd.tasks`` -- tasks.md rules this port adds or that need the trace::

      {rule: story_tests}        every user-story phase has a ``### Tests for User Story N`` part whose tasks name a
                                 file under ``checks/`` (03-tasks.md:43) (ratio)
      {rule: empty_phases}       the Setup, Foundational and Polish phases are there, each with a task or the line
                                 ``No tasks — <reason>`` (03-tasks.md:28) (ratio)
      {rule: ticked}             share of the task lines ticked when the window ends (``open_at_start``: of those
                                 unticked when it began -- a round-2 implement does the unchecked tasks)
      {rule: ticked_after_work}  every task ticked in the window was ticked inside it, after a write or a run of a
                                 path it names (ratio; a box ticked before the work, or untraceably, fails)
      {rule: later_edits}        every write of tasks.md in the window only ticks boxes or appends (ratio)
      {rule: appended}           a write in the window appends a new ``## Phase N: Convergence`` after ``report``'s
                                 first write
      {rule: convergence_phase}  every Convergence phase is numbered one past the highest phase before it, and no
                                 other phase follows it
      {rule: convergence_lines}  every task of a Convergence phase is ``- [ ] T### <description> per <source-ref>
                                 (<gap-type>)`` (ratio)

* ``speckit_sdd.report`` -- a converge round report (05-converge.md:134-149, 177-181)::

      {rule: findings}        every finding row names one gap type and one severity of the document's sets (ratio)
      {rule: outcome_rows}    ``tasks_appended`` lists a finding; ``converged`` lists none
      {rule: converged_line}  a ``converged`` report's last line is the converged sentence

* ``speckit_sdd.plan_docs`` -- ``{rule: contracts}``: plan.md's Documentation tree lists every contract file
  written, or holds ``contracts/  # N/A — <reason>`` when none is; ``{rule: na_body}``: a Phase 1 file with
  nothing to hold is the one line ``N/A — <reason>`` (02-plan.md:212, 243).
* ``speckit_sdd.feature_json`` -- ``.specify/feature.json`` parses and its ``feature_directory`` resolves, from
  the project root, to the directory holding the spec (01-specify.md:26-32).
* ``speckit_sdd.created_files`` / ``speckit_sdd.paths_written`` / ``speckit_sdd.no_fetch`` / ``speckit_sdd.links``
  -- no test / scratch file created in the repository, no file written at a path ``pattern`` names (a script under
  ``/tmp`` outside the feature directory, core-workflow.md:82-84), no URL fetched, every link the spec names marked
  ``[UNVERIFIED — not fetched]`` (01-specify.md:6).

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import json
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
from . import speckit_kinds as SK  # registers the speckit.* kinds (vendored from the spec_kit port)

MAX_CMD = 20_000
MAX_TEXT = 400_000
SCRIPTS_DIR = "/tmp/speckit-sdd/.specify/scripts/bash"
_EXIT = re.compile(r"\[(?:The command completed with exit code|Command finished with exit code)\s+(-?\d+)\.?\]")
_FAIL_TEXT = re.compile(
    r"Traceback \(most recent call last\)|\bAssertionError\b|^\s*(?:FAIL|FAILED|ERROR)\b|\b\d+ (?:failed|errors?)\b|\bFAILED \(|"
    r"^\s*E\s{2,}\S|\b(?:Error|Exception):\s|\bcommand not found\b|\bNo such file or directory\b|\bcan't open file\b",
    re.M,
)
_PASS_TEXT = re.compile(r"\b\d+ passed\b|^\s*OK\b|\bPASS(?:ED)?\b|\ball (?:checks|tests) pass(?:ed)?\b|\bpassed\b", re.M | re.I)
_MARK_WORDS = re.compile(r"(?i)\b(?:fail\w*|error\w*|pass\w*|ok|traceback|assert\w*)\b")
_SCRIPT_EXT = re.compile(r"\.(?:py|sh|bash|js|mjs|cjs|ts|rb|pl|php)$")
_GAPS = ("missing", "partial", "contradicts", "unrequested")
_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
_CONVERGED = re.compile(r"Converged\s*[—–-]+\s*the implementation satisfies the spec, plan,? and tasks", re.I)
_CONV_PHASE = re.compile(r"^#{2}\s+(?:\*\*)?Phase\s+(\d+)\s*:\s*Convergence\b", re.I)
_ANY_PHASE = re.compile(r"^#{2}\s+(?:\*\*)?Phase\s+(\d+|[A-Z])\b[^:\n]*:", re.I)
_CONV_LINE = re.compile(r"^\s*- \[[ xX]\] T\d{3,} (?!\s).*\bper\s+\S.*\((?:missing|partial|contradicts|unrequested)\)[.\s]*$")
_NO_TASKS = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|_)?No tasks(?:\*\*|_)?\s*[—–-]+\s*\S.{2,}")
_BOX = re.compile(r"^(\s*[-*+]\s+)\[[ xX]\]")


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
    return str(p.get("artifact") or item.target.ref or default or "")


def _text(ctx: EvalContext, aid: str, state: str = "final") -> str | None:
    t = ctx.artifact_text(aid, state)
    return None if t is None else M.strip_fence(t[:MAX_TEXT])[0]


def _feature_dir(ctx: EvalContext) -> str | None:
    """FEATURE_DIR: the directory of the spec's location (``{artifact}/001-issue/spec.md``)."""
    art = ctx.rubric.artifacts.get("spec")
    if art is None or not art.locations:
        return None
    s, left = F.expand(art.locations[0], F.roots_of(ctx.rubric, ctx.collected.workdir), ctx.collected.workdir, ctx.facts.var_bindings)
    return posixpath.dirname(s) if s.startswith("/") and not left else None


def _checks_dir(item: Item, ctx: EvalContext) -> str | None:
    p = item.check.params or {}
    if p.get("dir"):
        s, left = F.expand(str(p["dir"]), F.roots_of(ctx.rubric, ctx.collected.workdir), ctx.collected.workdir, ctx.facts.var_bindings)
        return posixpath.normpath(s) if s.startswith("/") and not left else None
    fd = _feature_dir(ctx)
    return posixpath.join(fd, "checks") if fd else None


def _segments(ctx: EvalContext, c) -> list[shell.Segment]:
    key = ("speckit_sdd.segments", c.step, c.action_index)
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
            out |= {posixpath.normpath(t) for t in hit.targets if t}
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
    """``pass`` / ``fail`` / None (cannot tell) for segment ``i``'s run, by its call's own output.

    The exit code counts when the segment is the command's last (a ``| tail`` or ``; echo`` after it owns the code);
    failure or pass text counts when no other segment of the command could have printed such words."""
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


# --------------------------------------------------------------------------------------------
# speckit_sdd.script / speckit_sdd.untouched
# --------------------------------------------------------------------------------------------
@register("speckit_sdd.script", params={"name": True, "args": False, "keys": False, "window": False}, availability=("trace",), common=False)
def script(item: Item, ctx: EvalContext) -> Result:
    """The shipped Spec Kit script ``name`` ran at its shipped path with ``args`` and succeeded by its own call's output, in the window."""
    p = item.check.params or {}
    name = str(p["name"])
    path = posixpath.join(SCRIPTS_DIR, name)
    flags = [str(a) for a in (p.get("args") or [])]
    keys = [str(k) for k in (p.get("keys") or ["FEATURE_DIR"])]
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    seen = []
    for c in ctx.facts.commands:
        if not refs.in_window(c.step, w):
            continue
        segs = _segments(ctx, c)
        for i, seg in enumerate(segs):
            if path not in _executed_by(seg):
                continue
            words = [x for x in (seg.argv or [])]
            if any(f not in words for f in flags):
                seen.append(f"step {c.step}: without {[f for f in flags if f not in words]}")
                continue
            obs = E.clean_observation(c.observation or "", c.command or "")
            code = _exit_code(obs) if i == len(segs) - 1 else None
            key_rx = re.compile("|".join(re.escape(f'"{k}"') for k in keys))
            has_keys = all(f'"{k}"' in obs for k in keys) and not _others_print(segs, i, key_rx)
            error = re.search(r"(?m)^ERROR:", obs) is not None
            if code == 0 or (code is None and has_keys and not error):
                return Result.ok(item, f"step {c.step}: {name} ran" + (" (exit 0)" if code == 0 else " (its JSON)"))
            seen.append(f"step {c.step}: " + (f"exit {code}" if code is not None else "no output of its own"))
    return Result.no(item, f"{name}: " + ("; ".join(seen[:2]) if seen else f"not run at {path} in the window"))


@register("speckit_sdd.untouched", params={"prefixes": True}, availability=("trace",), common=False)
def untouched(item: Item, ctx: EvalContext) -> Result:
    """No write of the trace (any kind, a failed one aside) lands under the shipped trees ``prefixes``."""
    pre = [str(x).rstrip("/") + "/" for x in ((item.check.params or {}).get("prefixes") or [])]
    hits = [f"step {e.step}: {e.op} {path}" for path, evs in ctx.facts.writes.items() if any(path.startswith(q) for q in pre) for e in evs if e.ok is not False]
    return Result.no(item, f"{len(hits)} write(s): {sorted(hits)[0]}") if hits else Result.ok(item, "shipped files untouched")


# --------------------------------------------------------------------------------------------
# speckit_sdd.checks
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


def _named_in_tasks(ctx: EvalContext, scripts: list[str]) -> list[str]:
    text = _text(ctx, "tasks") or ""
    return [s for s in scripts if posixpath.basename(s) in text]


@register("speckit_sdd.checks", params={"rule": True, "window": False, "dir": False}, availability=("trace",), common=False, choices={"rule": ("written", "red_green", "before_code", "pass_last")})
def checks(item: Item, ctx: EvalContext) -> Result:
    """rule: written | red_green | before_code | pass_last -- the verification scripts under FEATURE_DIR/checks/: written; run failing, then passing after the code change; failing before the first code change; passing after the last."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    d = _checks_dir(item, ctx)
    w = _window(item, ctx)
    if d is None:
        return Result.no(item, "no checks directory")
    if w is None:
        return Result.no(item, "window empty")
    end = w[1] if w[1] is not None else ctx.facts.n_steps + 2
    if rule == "written":
        got = [s for s in check_scripts(ctx, d) if any(refs.in_window(e.step, w) for e in _content_events(ctx, s))]
        return Result.ok(item, f"{len(got)} written: {[posixpath.basename(s) for s in got][:3]}") if got else Result.no(item, f"no script written under {d}/ in the window")
    scripts = check_scripts(ctx, d, upto=end - 1)
    runs = executions(ctx, set(scripts))
    runs = {s: [(st, o) for st, o in r if refs.in_window(st, w)] for s, r in runs.items()}
    pool = _named_in_tasks(ctx, scripts) or [s for s in scripts if runs.get(s)]
    changes = _change_steps(ctx, w)
    if rule == "before_code":
        if not changes:
            return Result.no(item, "no code change in the window")
        first = changes[0]
        if getattr(ctx.facts, "unseen_repo_paths", None):
            return Result.no(item, "a repository change the trace does not show: its time is unknown")
        reds = [(st, posixpath.basename(s)) for s in scripts for st, o in runs.get(s, []) if o == "fail" and st < first]
        return Result.ok(item, f"{reds[0][1]} failed at step {reds[0][0]}, before the first code change (step {first})") if reds else Result.no(item, f"no check script ran failing before the first code change (step {first})")
    if not pool:
        return Result.no(item, f"no verification script under {d}/")
    good, bad = 0, []
    if rule == "red_green":
        for s in pool:
            rs = runs.get(s, [])
            writes = [e.step for e in _content_events(ctx, s)]
            ok = any(
                fo == "fail" and po == "pass" and fs < ps and any(fs < c < ps for c in changes) and not any(fs < x < ps for x in writes)
                for fs, fo in rs
                for ps, po in rs
            )
            good += ok
            if not ok:
                bad.append(posixpath.basename(s))
        return Result.ratio(item, good, len(pool), f"not seen failing, then passing after a code change: {bad[:3]}" if bad else f"{good} script(s) red, then green")
    if rule == "pass_last":
        last_change = changes[-1] if changes else w[0]
        for s in pool:
            rs = runs.get(s, [])
            ok = bool(rs) and rs[-1][1] == "pass" and rs[-1][0] > last_change
            good += ok
            if not ok:
                bad.append(posixpath.basename(s))
        return Result.ratio(item, good, len(pool), f"not passing after the last code change (step {last_change}): {bad[:3]}" if bad else f"{good} script(s) pass after step {last_change}")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit_sdd.tasks
# --------------------------------------------------------------------------------------------
def _tasks_path(ctx: EvalContext, aid: str) -> str | None:
    return ctx.facts.artifact_paths.get(aid)


def _text_at(ctx: EvalContext, path: str | None, step: int) -> str | None:
    """The replayed content of ``path`` after step ``step`` (None: unknown or not yet written)."""
    if not path:
        return None
    evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False]
    return content_at(evs, step)


def _window_end_text(ctx: EvalContext, aid: str, w) -> str | None:
    """tasks.md at the end of the window: replayed, or the final file when nothing wrote it later."""
    path = _tasks_path(ctx, aid)
    if not path:
        return None
    end = (w[1] if w[1] is not None else ctx.facts.n_steps + 2) - 1
    evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False]
    if not any(e.step > end for e in evs) and not ctx.facts.final_mismatch.get(path):
        return _text(ctx, aid)
    t = content_at(evs, end)
    return None if t is None else M.strip_fence(t[:MAX_TEXT])[0]


def _phase_bodies(text: str) -> list[tuple[dict, list[str]]]:
    """(phase, its lines) for every ``## Phase`` heading of tasks.md, in order."""
    out: list[tuple[dict, list[str]]] = []
    cur: list[str] | None = None
    for line in M.text_lines(text[:MAX_TEXT]):
        line = line[:2000]
        if re.match(r"^#{1,2}\s+\S", line):
            m = SK._PHASE.match(line.strip())
            if m:
                kind, num = SK.phase_kind(m.group("title"))
                cur = []
                out.append(({"title": m.group("title").strip(), "kind": kind, "story": num, "number": m.group(1), "heading": line.strip()}, cur))
            else:
                cur = None
            continue
        if cur is not None:
            cur.append(line)
    return out


def _named(desc: str, ctx: EvalContext, d: str | None) -> set[str]:
    """Paths a task names: repository-relative (``speckit.*``'s reading) and absolute ones under the feature directory."""
    out = set(SK.named_paths(desc, ctx.collected.workdir))
    fd = _feature_dir(ctx) or ""
    for m in re.finditer(r"(?:/tmp/speckit-sdd/specs/001-issue/|(?<![\w/])checks/)[\w./-]+", desc or ""):
        tok = m.group(0).rstrip(".,;:)")
        out.add(tok if tok.startswith("/") else posixpath.join(fd, tok))
    return out


def _evidence_steps(ctx: EvalContext, paths: set[str]) -> list[int]:
    """Steps that wrote or ran one of ``paths`` (repository-relative or absolute)."""
    wd = (ctx.collected.workdir or "").rstrip("/")
    absolute = {q if q.startswith("/") else f"{wd}/{q}" for q in paths}
    steps = [e.step for q in absolute for e in ctx.facts.writes.get(q, []) if e.ok is not False]
    steps += [st for st, path in F.executed_paths(ctx) if path in paths or path in absolute or (wd and f"{wd}/{path}" in absolute)]
    return steps


@register(
    "speckit_sdd.tasks",
    params={"rule": True, "artifact": False, "window": False, "report": False, "open_at_start": False, "dir": False},
    availability=("sandbox_file", "trace"),
    common=False,
    choices={"rule": ("story_tests", "empty_phases", "ticked", "ticked_after_work", "later_edits", "appended", "convergence_phase", "convergence_lines")},
)
def tasks(item: Item, ctx: EvalContext) -> Result:
    """rule: story_tests | empty_phases | ticked | ticked_after_work | later_edits | appended | convergence_phase | convergence_lines -- tasks.md's test parts, kept phases, ticks against the work, and converge's appended phase."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = _artifact(item, "tasks")
    if rule in ("story_tests", "empty_phases", "convergence_phase", "convergence_lines"):
        text = _text(ctx, aid, getattr(item.target, "state", "final") or "final")
        if text is None:
            return Result.no(item, "tasks.md absent")
        bodies = _phase_bodies(text)
        if rule == "story_tests":
            stories = [(ph, lines) for ph, lines in bodies if ph["kind"] == "story"]
            if not stories:
                return Result.not_applicable(item, "no user-story phase")
            bad = []
            for ph, lines in stories:
                part, ok = None, False
                for ln in lines:
                    h = re.match(r"^#{3,}\s+(.*)$", ln.strip())
                    if h:
                        part = h.group(1)
                        continue
                    if part and re.match(r"(?i)Tests for User Story\s+%d\b" % ph["story"], part) and SK._TASK.match(ln) and "checks/" in ln:
                        ok = True
                if not ok:
                    bad.append(f"US{ph['story']}")
            return Result.ratio(item, len(stories) - len(bad), len(stories), f"no Tests part naming checks/: {bad[:4]}" if bad else f"{len(stories)} stories with checks")
        if rule == "empty_phases":
            want = {"setup": "Setup", "foundational": "Foundational", "polish": "Polish"}
            good, miss = 0, []
            for kind, label in want.items():
                found = [lines for ph, lines in bodies if ph["kind"] == kind]
                if found and any(SK._TASK.match(ln) or _NO_TASKS.match(ln) for ln in found[0]):
                    good += 1
                else:
                    miss.append(label + ("" if found else " (no heading)"))
            return Result.ratio(item, good, len(want), f"empty or missing: {miss}" if miss else "Setup, Foundational and Polish kept")
        convs = [(k, ph, lines) for k, (ph, lines) in enumerate(bodies) if _CONV_PHASE.match(ph["heading"])]
        if not convs:
            return Result.not_applicable(item, "no Convergence phase")
        if rule == "convergence_phase":
            for k, ph, _ in convs:
                nums = [int(b[0]["number"]) for b in bodies[:k] if b[0]["number"].isdigit()]
                want_n = (max(nums) + 1) if nums else None
                if want_n is not None and int(ph["number"]) != want_n:
                    return Result.no(item, f"{ph['heading'][:50]!r}: expected Phase {want_n}")
            first = convs[0][0]
            later = [b[0]["heading"] for b in bodies[first:] if not _CONV_PHASE.match(b[0]["heading"])]
            if later:
                return Result.no(item, f"a phase after the Convergence phase: {later[0][:50]!r}")
            return Result.ok(item, f"{len(convs)} Convergence phase(s), numbered in sequence, at the end")
        lines = [ln for _, _, ls in convs for ln in ls if SK._TASK.match(ln)]
        if not lines:
            return Result.no(item, "a Convergence phase without tasks")
        good = sum(1 for ln in lines if _CONV_LINE.match(ln))
        return Result.ratio(item, good, len(lines), f"{good}/{len(lines)} '- [ ] T### ... per <ref> (<gap>)'")
    w = _window(item, ctx)
    path = _tasks_path(ctx, aid)
    if path is None:
        return Result.no(item, "tasks.md absent")
    if w is None:
        return Result.no(item, "window empty")
    evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
    if rule == "ticked":
        text = _window_end_text(ctx, aid, w)
        if text is None:
            return Result.no(item, "tasks.md unknown at the end of the window")
        lines = SK.task_lines(text)
        if p.get("open_at_start"):
            before = _text_at(ctx, path, w[0] - 1)
            if before is None:
                return Result.no(item, "tasks.md unknown when the window began")
            open_ids = {t["id"] for t in SK.task_lines(before) if not t["checked"]}
            lines = [t for t in lines if t["id"] in open_ids]
        if not lines:
            return Result.not_applicable(item, "no task to tick")
        done = sum(1 for t in lines if t["checked"])
        return Result.ratio(item, done, len(lines), f"{done}/{len(lines)} ticked")
    if rule == "ticked_after_work":
        text = _window_end_text(ctx, aid, w)
        if text is None:
            return Result.no(item, "tasks.md unknown at the end of the window")
        before = _text_at(ctx, path, w[0] - 1) or ""
        was = {t["id"] for t in SK.task_lines(before) if t["checked"]}
        pool = [t for t in SK.task_lines(text) if t["checked"] and t["id"] not in was]
        if not pool:
            return Result.not_applicable(item, "no task ticked in the window")
        when = SK.tick_steps(ctx, aid)
        d = _checks_dir(item, ctx)
        bad = []
        for t in pool:
            s = when.get(t["id"])
            if s is None or s is UNKNOWN or not refs.in_window(s, w):
                bad.append(t["id"])
                continue
            named = _named(SK.description(t["rest"]), ctx, d)
            if named and not any(w[0] <= x <= s for x in _evidence_steps(ctx, named)):
                bad.append(t["id"])
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"ticked before (or without) the work it names: {bad[:5]}" if bad else f"{len(pool)} ticks after their work")
    inside = [e for e in evs if refs.in_window(e.step, w)]
    if rule == "later_edits":
        edits = [e for e in inside if e is not evs[0]]  # the write that made tasks.md is the tasks stage's, no later edit
        if not edits:
            return Result.ok(item, "tasks.md not edited in the window")
        good, bad = 0, []
        for e in edits:
            prev, new = _prior(ctx, path, e), e.content
            if prev is None or new is None:
                bad.append(f"step {e.step}: content unknown")
                continue
            if _ticks_only(prev, new) or _appends_only(prev, new):
                good += 1
            else:
                bad.append(f"step {e.step}: {e.op} changes earlier tasks")
        return Result.ratio(item, good, len(edits), "; ".join(bad[:2]) if bad else f"{good} write(s): ticks or appends")
    if rule == "appended":
        rep = p.get("report")
        after = refs.event(ctx, f"first_write:{rep}") if rep else None
        for e in inside:
            prev = _prior(ctx, path, e)
            new = e.content
            if prev is None or new is None or not _appends_only(prev, new):
                continue
            added = new[len(prev.rstrip()) :]
            if any(_CONV_PHASE.match(ln.strip()) for ln in added.splitlines()):
                if rep and (after is None or after is UNKNOWN or after >= e.step):
                    return Result.no(item, f"step {e.step}: appended before the round report was written")
                return Result.ok(item, f"step {e.step}: Convergence phase appended")
        return Result.no(item, "no Convergence phase appended to tasks.md in the window")
    return Result.no(item, f"unknown rule {rule!r}")


def _prior(ctx: EvalContext, path: str, e) -> str | None:
    """The content of ``path`` just before write ``e`` (the previous event's)."""
    evs = [x for x in ctx.facts.writes.get(path, []) if x.ok is not False]
    prev = None
    for x in evs:
        if x is e:
            break
        prev = x
    return None if prev is None else prev.content


def _norm_box(text: str) -> list[str]:
    return [_BOX.sub(r"\1[ ]", ln.rstrip()) for ln in (text or "").replace("\r\n", "\n").rstrip().split("\n")]


def _ticks_only(prev: str, new: str) -> bool:
    return _norm_box(prev) == _norm_box(new)


def _appends_only(prev: str, new: str) -> bool:
    a, b = (prev or "").replace("\r\n", "\n").rstrip(), (new or "").replace("\r\n", "\n").rstrip()
    return len(b) > len(a) and b.startswith(a)


# --------------------------------------------------------------------------------------------
# speckit_sdd.report
# --------------------------------------------------------------------------------------------
def _cells(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def finding_rows(text: str) -> list[dict[str, str]]:
    """The findings table of a round report (the first table whose header names Gap Type): one dict per row."""
    lines = [ln for ln in (text or "").splitlines()[:4000] if ln.strip().startswith("|")]
    head, rows = None, []
    for ln in lines:
        cells = _cells(ln)
        if head is None:
            low = [c.lower() for c in cells]
            if any("gap" in c for c in low):
                head = low
            continue
        if re.match(r"^\|?\s*:?-{2,}", ln.strip()):
            continue
        get = lambda name, k: next((cells[i] for i, h in enumerate(head) if name in h and i < len(cells)), cells[k] if k < len(cells) else "")  # noqa: E731
        rows.append({"id": get("id", 0), "gap": get("gap", 1), "severity": get("severity", 2), "source": get("source", 3)})
    return rows


def _plain(cell: str) -> str:
    return re.sub(r"[*_`]", "", cell or "").strip()


def outcome_of(text: str | None) -> str | None:
    v = M.field_value(text or "", "Outcome") if text else None
    if not v:
        return None
    m = re.match(r"^\W*(converged|tasks_appended)\b", M.clean_value(v), re.I)
    return m.group(1).lower() if m else None


@register("speckit_sdd.report", params={"rule": True, "artifact": False}, availability=("sandbox_file",), common=False, choices={"rule": ("findings", "outcome_rows", "converged_line")})
def report(item: Item, ctx: EvalContext) -> Result:
    """rule: findings | outcome_rows | converged_line -- a converge round report: each finding one gap type and severity; tasks_appended lists findings, converged none; converged ends with its sentence."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    text = _text(ctx, _artifact(item))
    if text is None:
        return Result.no(item, "report absent")
    rows = finding_rows(text)
    if rule == "findings":
        if not rows:
            return Result.not_applicable(item, "no finding row")
        good = [r for r in rows if _plain(r["gap"]).lower() in _GAPS and _plain(r["severity"]).upper() in _SEVERITIES]
        return Result.ratio(item, len(good), len(rows), f"{len(good)}/{len(rows)} rows with one gap type and one severity")
    out = outcome_of(text)
    if rule == "outcome_rows":
        if out == "tasks_appended":
            return Result.ok(item, f"{len(rows)} finding(s)") if rows else Result.no(item, "tasks_appended without a finding row")
        if out == "converged":
            return Result.ok(item, "converged, no finding") if not rows else Result.no(item, f"converged with {len(rows)} finding row(s)")
        return Result.no(item, "no Outcome value")
    if rule == "converged_line":
        if out != "converged":
            return Result.not_applicable(item, "Outcome is not converged")
        last = next((ln for ln in reversed(text.rstrip().splitlines()) if ln.strip()), "")
        return Result.ok(item, "ends with the converged sentence") if _CONVERGED.search(last) else Result.no(item, f"last line {last.strip()[:60]!r}")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit_sdd.plan_docs / speckit_sdd.feature_json
# --------------------------------------------------------------------------------------------
_NA_CONTRACTS = re.compile(r"contracts/\s*(?:#|<!--)?\s*N/?A\s*[—–-]+\s*\S{2,}", re.I)


@register("speckit_sdd.plan_docs", params={"rule": True, "artifact": False}, availability=("sandbox_file",), common=False, choices={"rule": ("contracts", "na_body")})
def plan_docs(item: Item, ctx: EvalContext) -> Result:
    """rule: contracts | na_body -- plan.md's tree lists the contract files written (or 'contracts/  # N/A — <reason>'); a Phase 1 file with nothing to hold is one 'N/A — <reason>' line."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = _artifact(item)
    text = _text(ctx, aid)
    if text is None:
        return Result.no(item, f"{aid} absent")
    if rule == "contracts":
        tree = M.section(text, "Documentation (this feature)") or ""
        fd = _feature_dir(ctx) or ""
        pre = posixpath.join(fd, "contracts") + "/"
        files = sorted(q for q in ctx.collected.files if q.startswith(pre))
        if "<REPLACE" in tree:
            return Result.no(item, "the template's contracts line is still there")
        if files:
            missing = [posixpath.basename(q) for q in files if posixpath.basename(q) not in tree]
            if _NA_CONTRACTS.search(tree):
                return Result.no(item, "contract files written, but the tree says N/A")
            return Result.no(item, f"contract files not listed: {missing[:3]}") if missing else Result.ok(item, f"{len(files)} contract file(s) listed")
        return Result.ok(item, "no contract file; the tree says why") if _NA_CONTRACTS.search(tree) else Result.no(item, "no contract file and no 'contracts/  # N/A — <reason>' line")
    if rule == "na_body":
        body = [ln.strip() for ln in M.text_lines(text) if ln.strip() and not re.match(r"^#{1,6}\s", ln.strip())]
        if not body:
            return Result.no(item, "empty")
        if len(body) == 1 and re.match(r"(?i)^\W*N/?A\b", body[0]):
            return Result.ok(item, "N/A with its reason") if re.match(r"(?i)^\W*N/?A\W*\s*[—–-]+\s*\S{2,}", body[0]) else Result.no(item, f"N/A without a reason: {body[0][:40]!r}")
        if any(re.match(r"(?i)^\W*N/?A\W*$", ln) for ln in body):
            return Result.no(item, "a bare N/A line next to other text")
        return Result.ok(item, f"{len(body)} line(s) of content")
    return Result.no(item, f"unknown rule {rule!r}")


@register("speckit_sdd.feature_json", params={"artifact": False, "feature_of": False}, availability=("sandbox_file",), common=False)
def feature_json(item: Item, ctx: EvalContext) -> Result:
    """The file parses and ``feature_directory`` resolves, relative to the project root (the parent of .specify/) or absolute, to the directory holding ``feature_of`` (spec)."""
    p = item.check.params or {}
    aid = _artifact(item, "feature_json")
    raw = ctx.artifact_text(aid, "final")
    path = ctx.facts.artifact_paths.get(aid)
    if raw is None or not path:
        return Result.no(item, "feature.json absent")
    try:
        d = json.loads(M.strip_fence(raw[:MAX_TEXT])[0])
    except (ValueError, RecursionError):
        return Result.no(item, "not valid JSON")
    v = d.get("feature_directory") if isinstance(d, dict) else None
    if not isinstance(v, str) or not v.strip():
        return Result.no(item, "no feature_directory string")
    target = ctx.facts.artifact_paths.get(str(p.get("feature_of") or "spec"))
    if not target:
        return Result.no(item, "no spec to compare with")
    root = posixpath.dirname(posixpath.dirname(path))
    got = posixpath.normpath(v.strip() if v.strip().startswith("/") else posixpath.join(root, v.strip()))
    want = posixpath.dirname(target)
    return Result.ok(item, f"{v.strip()} -> {got}") if got == want else Result.no(item, f"{v.strip()[:80]!r} resolves to {got}, not {want}")


# --------------------------------------------------------------------------------------------
# speckit_sdd.created_files / paths_written / no_fetch / links
# --------------------------------------------------------------------------------------------
@register("speckit_sdd.created_files", params={"pattern": False, "test_paths": False, "window": False}, availability=("trace",), common=False)
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


@register("speckit_sdd.paths_written", params={"pattern": True, "window": False}, availability=("trace",), common=False)
def paths_written(item: Item, ctx: EvalContext) -> Result:
    """No content write of the trace in the window lands at an absolute path ``pattern`` matches."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"]))
    hits = [f"step {e.step}: {e.op} {path}" for path, evs in ctx.facts.writes.items() if rx.search(path) for e in evs if e.ok is not False and e.op in F.WRITE_OPS and refs.in_window(e.step, w)]
    return Result.no(item, f"{len(hits)} write(s): {sorted(hits)[0]}") if hits else Result.ok(item, "none written")


_FETCH = re.compile(
    r"(?i)(?:\b(?:curl|wget|lynx|w3m|aria2c)\b[^\n|;&]*\bhttps?://"
    r"|\b(?:urlopen|urlretrieve|requests\.(?:get|post|head|request)|httpx\.(?:get|post|head|stream))\s*\(\s*[rbuf]?['\"]https?://"
    r"|\bgit\s+clone\b[^\n|;&]*\bhttps?://)"
)


@register("speckit_sdd.no_fetch", params={"window": False}, availability=("trace",), common=False)
def no_fetch(item: Item, ctx: EvalContext) -> Result:
    """No command fetches a URL: curl / wget / a text browser on a URL, a Python urlopen / requests / httpx call on a URL literal, a git clone of a URL."""
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    for c in ctx.facts.commands:
        if refs.in_window(c.step, w) and _FETCH.search((c.command or "")[:MAX_CMD]):
            return Result.no(item, f"step {c.step}: {c.command.strip()[:60]}")
    return Result.ok(item, "no URL fetched")


_URL = re.compile(r"\bhttps?://[^\s<>()\[\]`'\"]+", re.I)
_MARK = re.compile(r"\[\s*UNVERIFIED\s*[—–-]+\s*not fetched\s*\]", re.I)
_FENCED = re.compile(r"^\s*(`{3,}|~{3,}).*?^\s*\1[ \t]*$", re.M | re.S)
_LOCAL = re.compile(r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?:[:/]|$)", re.I)


@register("speckit_sdd.links", params={"section": False, "artifact": False}, availability=("sandbox_file",), common=False)
def links(item: Item, ctx: EvalContext) -> Result:
    """Every link the artifact (or ``section``) names outside code is on a line marked [UNVERIFIED — not fetched] (ratio); not_applicable without a link."""
    p = item.check.params or {}
    text = _text(ctx, _artifact(item))
    if text is None:
        return Result.no(item, "artifact absent")
    body = refs.section_of(text, p.get("section")) if p.get("section") else text
    if body is None:
        return Result.no(item, f"no {p.get('section')!r} section")
    plain = re.sub(r"`[^`\n]+`", " ", _FENCED.sub("", body[:MAX_TEXT]))
    urls = {m.group(0).rstrip(".,;:!?*_") for m in _URL.finditer(plain)}
    urls = {u for u in urls if not _LOCAL.match(u)}
    if not urls:
        return Result.not_applicable(item, "no link")
    marked = [ln for ln in body.splitlines()[:5000] if _MARK.search(ln)]
    good = sorted(u for u in urls if any(u in ln for ln in marked))
    return Result.ratio(item, len(good), len(urls), f"unmarked: {sorted(urls - set(good))[:2]}" if len(good) < len(urls) else f"{len(good)} link(s) marked")


__all__ = [
    "script",
    "untouched",
    "checks",
    "tasks",
    "report",
    "plan_docs",
    "feature_json",
    "created_files",
    "paths_written",
    "no_fetch",
    "links",
    "outcome",
    "executions",
    "finding_rows",
    "outcome_of",
]
