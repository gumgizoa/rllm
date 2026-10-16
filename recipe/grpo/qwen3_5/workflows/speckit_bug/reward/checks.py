"""speckit_bug plugin kinds: the report rules and run facts the common kinds cannot state as checks.

The common kinds cover most of the bug workflow: section and label items for the three report skeletons,
``field_enum`` for Verdict / Severity / Status / Result and the round fields, ``doc_read`` for the stage
documents, ``write_discipline`` for "one write per report", ``prohibited_action`` for the stages that must
not touch the repository, ``exec_evidence`` for the test runs. What they cannot say:

* ``speckit_bug.checks_table`` -- the verification report's **Checks Performed** table (03-test.md:66-73),
  one row per check, ``| Check | Command / Action | Result | Notes |``. One item per rule::

      {rule: results}       every row's Result is one value of the template's ``pass / fail / skipped /
                            not-run`` (a copied ``pass / fail`` choice is none of them) (ratio)
      {rule: commands_run}  every row claiming pass or fail whose Command cell holds a command (a code span)
                            names a command the run executed in the window (ratio; no such row: fail --
                            03-test.md:37 "Capture command, exit status")
      {rule: test_run}      some row claiming pass or fail names a command that is a *valid* test run of the
                            window (evidence.py: runner output in its own observation, base-repo targets --
                            an echoed summary or a dummy test under /tmp is none)
      {rule: consistent}    a verified Result has no row claiming fail (03-test.md:43, :45)
      {rule: unrun}         a verified Result has no ``skipped`` / ``not-run`` row for the reproduction or the
                            fix's checks (03-test.md:44 "partial -- ... one of them was not run", :106); the
                            lint / type-check row is not one of the verdict's conditions

* ``speckit_bug.checks_added`` -- the fix report's record of the checks it set up before the change
  (02-fix.md:30-34, the **Checks Added** table and **Baseline: Existing Tests** of :72-81)::

      {rule: before_run}    every row of Checks Added claims ``fail`` before the change and names a check
                            script that the run executed after its last write and before this round's first
                            repository edit (ratio; no row: fail) -- a recorded "fail" the trace never ran,
                            or an "N/A", is not the check seen failing (:32); ``optional`` (rounds 2 and 3):
                            rows naming no check script are left out, none left: not_applicable
      {rule: baseline_run}  some command (code span) of Baseline: Existing Tests is a valid test run before this
                            round's first repository edit (round 1's baseline stands in rounds 2 and 3, :34);
                            ``optional``: not_applicable when the section names no command

  Whether a check really fails before and passes after is not judged here: that needs the checks re-run in
  the sandbox (porting/later.md), not the trace.

* ``speckit_bug.links`` -- every link a section names (outside code, local addresses aside) is listed on a line
  carrying the ``[UNVERIFIED — not fetched]`` marker (01-assess.md:18-20: "Record each link verbatim ... marked"; the
  quoted issue text may name it unmarked as well); not_applicable when the section names no link.
* ``speckit_bug.read`` -- every listed report that exists was read in the window (an editor view, or a
  reading verb naming its path): ``doc_read`` covers the workflow's own documents, not the run's reports
  (02-fix.md:20-21, 03-test.md:21 "Read ... in full").
* ``speckit_bug.created_files`` -- no file the run created in the repository is a test file or matches a
  pattern (core-workflow.md:45-46 "Never write reports, checks, or scratch files into the repository", :53 "Do
  not add ... test files"): ``prohibited_action`` sees every write, this kind only the files absent at BASE_SHA
  (``django/views/debug.py`` is source, a new ``debug_issue.py`` is scratch).
* ``speckit_bug.check_scripts`` -- the checks under ``BUG_DIR/checks/``: ``written`` (a script written there in
  the window, 02-fix.md:31), ``run`` (one of them executed in the window, 03-test.md:30), ``before_change``
  (every check script first written in ``written_in`` was executed after its last write and before the
  window's first repository edit -- "Run each check now", 02-fix.md:30-34; ratio, ``optional``: not_applicable
  when none was added) and ``unchanged`` (no write, after the first repository edit of ``edit_in``, to a check
  script written before it -- "The checks written before the change stay as they are", 02-fix.md:36). Data
  files under ``checks/`` (``.txt``, ``.log``, ``.json`` ...) are not scripts. The checks live outside every
  artifact, so no artifact item can see them.
* ``speckit_bug.no_fetch`` -- no command fetches a URL (core-workflow.md:33-34, 01-assess.md:18): the kind names
  the fetching commands the documents leave implicit ("do not fetch links").
* ``speckit_bug.holds`` -- a refs predicate as a check: "no round after a verified report"
  (core-workflow.md:24-28) is a fact about which reports exist, not a field of one.

Nothing the agent writes can make these raise: malformed text is a failing rule, never an exception.
"""

from __future__ import annotations

import posixpath
import re

from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.checks.artifacts import _command_run
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

MAX_TEXT = 400_000
RESULTS = ("pass", "fail", "skipped", "not-run")
_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_CODE = re.compile(r"`([^`\n]+)`")
_URL = re.compile(r"\bhttps?://[^\s<>()\[\]`'\"]+", re.I)
_MARK = re.compile(r"\[\s*UNVERIFIED\s*[—–-]+\s*not fetched\s*\]", re.I)
_WORD = re.compile(r"[a-z][a-z-]*(?:\s+run\b)?")


def _window(item: Item, ctx: EvalContext):
    p = item.check.params or {}
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    return refs.window(ctx, spec)


def _artifact(item: Item) -> str:
    p = item.check.params or {}
    return str(p.get("artifact") or item.target.ref)


def _section(text: str, title: str) -> str | None:
    try:
        return M.section(M.strip_fence(text[:MAX_TEXT])[0], title)
    except Exception:  # noqa: BLE001 -- agent text
        return None


# --------------------------------------------------------------------------------------------
# speckit_bug.checks_table
# --------------------------------------------------------------------------------------------
def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def table_rows(body: str) -> list[dict[str, str]]:
    """The first markdown table of ``body`` as rows {check, command, result, notes}: columns by header name
    (``Command`` / ``Action``, ``Result``), else by position; the separator line and blank cells kept."""
    lines = [ln for ln in body.splitlines()[:2000] if ln.strip().startswith("|")]
    if not lines:
        return []
    head = [c.lower() for c in _cells(lines[0])]

    def col(*names: str, default: int) -> int:
        return next((i for i, h in enumerate(head) if any(n in h for n in names)), default)

    ci, ri, ni = col("command", "action", default=1), col("result", "status", default=2), col("note", default=3)
    rows = []
    for ln in lines[1:]:
        if _SEP.match(ln.strip()):
            continue
        cells = _cells(ln)
        get = lambda k: cells[k] if 0 <= k < len(cells) else ""  # noqa: E731
        rows.append({"check": get(0), "command": get(ci), "result": get(ri), "notes": get(ni)})
    return rows


def result_of(cell: str) -> str | None:
    """The cell's one result value (``pass``, ``fail``, ``skipped``, ``not-run``) or None: emphasis and a
    trailing note are allowed (``**pass** (3 tests)``), a copied choice (``pass / fail``) is not one value."""
    v = re.sub(r"[*_`]", "", cell).strip().lower()
    v = re.sub(r"^[^\w]+", "", v).replace("not run", "not-run")
    words = [w for w in re.findall(r"[a-z]+(?:-[a-z]+)?", v) if w in RESULTS or w in ("passed", "failed")]
    m = _WORD.match(v)
    first = m.group(0).replace("not run", "not-run") if m else ""
    first = {"passed": "pass", "failed": "fail", "not": "not-run"}.get(first, first)
    if first not in RESULTS:
        return None
    if len({({"passed": "pass", "failed": "fail"}.get(w, w)) for w in words}) > 1 and "/" in v:
        return None  # "pass / fail / skipped": the template's choice, not a result
    return first


# the rows the verdict rests on (03-test.md:43-44): the reproduction / the issue's examples and the fix's checks;
# the lint / type-check row (:34 "if the project uses them") is not one of them
_VERDICT_ROW = re.compile(r"(?i)reproduc|\bchecks?\b|example|symptom|\bissue\b")
_LINT_ROW = re.compile(r"(?i)\blint|type[ -]?check|\bformat")


def _commands(cell: str) -> list[str]:
    return [c.strip() for c in _CODE.findall(cell) if c.strip()]


@register("speckit_bug.checks_table", params={"rule": True, "artifact": False, "window": False}, availability=("sandbox_file", "trace"), common=False, choices={"rule": ("results", "commands_run", "test_run", "consistent", "unrun")})
def checks_table(item: Item, ctx: EvalContext) -> Result:
    """rule: results | commands_run | test_run | consistent | unrun -- the Checks Performed table: one result value per row; claimed commands were run; a valid test run among them; no failed row (consistent) and no skipped / not-run reproduction or fix-check row (unrun) under a verified Result."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    text = ctx.artifact_text(_artifact(item), getattr(item.target, "state", "final") or "final")
    if text is None:
        return Result.no(item, "artifact absent")
    body = _section(text, "Checks Performed")
    if body is None:
        return Result.no(item, "no Checks Performed section")
    rows = table_rows(body)
    if not rows:
        return Result.no(item, "no table rows")
    if rule == "results":
        good = sum(1 for r in rows if result_of(r["result"]) is not None)
        return Result.ratio(item, good, len(rows), f"{good}/{len(rows)} rows with one result value")
    if rule in ("consistent", "unrun"):
        verdict = M.field_value(M.frontmatter(M.strip_fence(text[:MAX_TEXT])[0]).body, "Result") or ""
        if not re.match(r"^\W*verified\b", M.clean_value(verdict), re.I):
            return Result.not_applicable(item, "Result is not verified")
        if rule == "unrun":
            unrun = [r["check"][:40] for r in rows if _VERDICT_ROW.search(r["check"]) and not _LINT_ROW.search(r["check"]) and result_of(r["result"]) in ("skipped", "not-run")]
            return Result.no(item, f"verified with checks not run: {unrun[:3]}") if unrun else Result.ok(item, "every reproduction / fix-check row was run")
        failed = [r["check"][:40] for r in rows if result_of(r["result"]) == "fail"]
        return Result.no(item, f"verified with failed checks: {failed[:3]}") if failed else Result.ok(item, "no failed check")
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    judged = [r for r in rows if result_of(r["result"]) in ("pass", "fail") and _commands(r["command"])]
    if not judged:
        return Result.no(item, "no row claims pass / fail with a command")
    if rule == "commands_run":
        good = 0
        for r in judged:
            if any(_command_run(item, ctx, c, w, None).status == "pass" for c in _commands(r["command"])):
                good += 1
        return Result.ratio(item, good, len(judged), f"{good}/{len(judged)} claimed commands were run")
    if rule == "test_run":
        for r in judged:
            if any(_command_run(item, ctx, c, w, "test").status == "pass" for c in _commands(r["command"])):
                return Result.ok(item, f"valid test run: {r['check'][:40]}")
        return Result.no(item, "no claimed command is a valid test run in the window")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit_bug.links
# --------------------------------------------------------------------------------------------
_FENCED = re.compile(r"^\s*(`{3,}|~{3,}).*?^\s*\1[ \t]*$", re.M | re.S)
_LOCAL = re.compile(r"^https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?:[:/]|$)", re.I)


def issue_links(body: str) -> set[str]:
    """The distinct URLs of a section outside code (fenced blocks, code spans) and other than a local address, trailing
    punctuation stripped: the links an issue names, not a URL in a quoted code sample or a local server."""
    text = _FENCED.sub("", body[:MAX_TEXT])
    text = _CODE.sub(" ", text)
    out = set()
    for m in _URL.finditer(text):
        u = m.group(0).rstrip(".,;:!?*_")
        if not _LOCAL.match(u):
            out.add(u)
    return out


@register("speckit_bug.links", params={"section": True, "artifact": False}, availability=("sandbox_file",), common=False)
def links(item: Item, ctx: EvalContext) -> Result:
    """Every link the section names is listed on a line carrying the [UNVERIFIED — not fetched] marker (ratio); not_applicable without a link."""
    p = item.check.params or {}
    text = ctx.artifact_text(_artifact(item), getattr(item.target, "state", "final") or "final")
    if text is None:
        return Result.no(item, "artifact absent")
    body = _section(text, str(p["section"]))
    if body is None:
        return Result.no(item, f"no {p['section']!r} section")
    urls = issue_links(body)
    if not urls:
        return Result.not_applicable(item, "no link in the section")
    marked = [ln for ln in body.splitlines()[:5000] if _MARK.search(ln)]
    good = sorted(u for u in urls if any(u in ln for ln in marked))
    missing = sorted(urls - set(good))
    return Result.ratio(item, len(good), len(urls), f"unmarked: {missing[:2]}" if missing else f"{len(good)} link(s) marked")


# --------------------------------------------------------------------------------------------
# speckit_bug.read
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


@register("speckit_bug.read", params={"artifacts": True, "window": False}, availability=("trace", "sandbox_file"), common=False)
def read(item: Item, ctx: EvalContext) -> Result:
    """Every listed report that exists at the end was read in the window (default: the item's stage); not_applicable when none exists."""
    p = item.check.params or {}
    w = _window(item, ctx)
    want = {a: ctx.facts.artifact_paths.get(a) for a in (p.get("artifacts") or []) if isinstance(a, str)}
    want = {a: q for a, q in want.items() if q}
    if not want:
        return Result.not_applicable(item, "none of the reports exists")
    if w is None:
        return Result.no(item, "window empty")
    hits = read_steps(ctx, sorted(set(want.values())), w)
    missing = [a for a, q in want.items() if not hits.get(q)]
    return Result.ratio(item, len(want) - len(missing), len(want), f"not read: {missing}" if missing else f"read: {sorted(want)}")


# --------------------------------------------------------------------------------------------
# speckit_bug.created_files
# --------------------------------------------------------------------------------------------
@register("speckit_bug.created_files", params={"pattern": False, "test_paths": False, "window": False}, availability=("trace",), common=False)
def created_files(item: Item, ctx: EvalContext) -> Result:
    """No file the run created in the repository (absent at BASE_SHA) is a test file (``test_paths``) or matches ``pattern``, written in the window."""
    from recipe.grpo.qwen3_5.workflow_rubric.facts import is_new_path, is_test_path

    p = item.check.params or {}
    w = _window(item, ctx) if ("window" in p or item.stage != "global") else (1, ctx.facts.n_steps + 2)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"])) if p.get("pattern") else None
    want_test = p.get("test_paths")
    hits = []
    for e in ctx.facts.repo_writes:
        if e.ok is False or not refs.in_window(e.step, w) or not is_new_path(ctx, e.path):
            continue
        if want_test is not None and is_test_path(e.path) != bool(want_test):
            continue
        if rx is not None and not rx.search(e.path):
            continue
        hits.append(f"step {e.step}: {e.op} {e.path}")
    if hits:
        return Result.no(item, f"{len(hits)} created: {hits[0]}")
    return Result.ok(item, "none created")


# --------------------------------------------------------------------------------------------
# speckit_bug.check_scripts
# --------------------------------------------------------------------------------------------
def check_dir(ctx: EvalContext) -> str:
    root = (ctx.rubric.roots or {}).get("artifact") or ""
    return posixpath.normpath(root) + "/checks/" if root else "/checks/"


def written_checks(ctx: EvalContext, w) -> list[str]:
    """Files under BUG_DIR/checks/ the trace wrote (with content) in the window, in order."""
    d = check_dir(ctx)
    out = []
    for path, evs in ctx.facts.writes.items():
        if not path.startswith(d):
            continue
        if any(e.ok is not False and e.op not in ("delete", "move_out") and refs.in_window(e.step, w) for e in evs):
            out.append(path)
    return sorted(out)


# files a check run leaves or the agent keeps next to its checks (output, notes, data): not check scripts
_DATA_FILE = re.compile(r"(?i)\.(?:txt|log|md|rst|json|out|err|diff|patch|csv|tsv|ya?ml|html?|xml|ini|cfg|toml|pyc|pkl|bin|dat)$")


def check_writes(ctx: EvalContext) -> dict[str, list[int]]:
    """Check script under BUG_DIR/checks/ -> the steps of its writes (with content), data files left out."""
    d = check_dir(ctx)
    out: dict[str, list[int]] = {}
    for path, evs in ctx.facts.writes.items():
        if not path.startswith(d) or _DATA_FILE.search(path):
            continue
        steps = sorted({e.step for e in evs if e.ok is not False and e.op not in ("delete", "move_out")})
        if steps:
            out[path] = steps
    return out


def first_edit(ctx: EvalContext, w) -> int | None:
    """The step of the first repository write in the window (None: no write there)."""
    steps = [e.step for e in ctx.facts.repo_writes if e.ok is not False and refs.in_window(e.step, w)]
    return min(steps) if steps else None


def seen_before(ctx: EvalContext, path: str, writes: list[int], end: int) -> bool:
    """The script was executed after its last write before ``end`` and before ``end``: the version that
    stood when the code was still unchanged was run on it (a write and its run in one command count)."""
    from recipe.grpo.qwen3_5.workflow_rubric.facts import executed_paths

    last = max((s for s in writes if s < end), default=None)
    if last is None:
        return False
    return any(p == path and last <= step < end for step, p in executed_paths(ctx))


def _edit_bound(item: Item, ctx: EvalContext, w) -> int:
    """This round's change starts at the first repository write of ``edit_in`` (default: the item's window);
    without one, the window's end bounds 'before the change'."""
    p = item.check.params or {}
    ew = refs.window(ctx, p["edit_in"]) if "edit_in" in p else w
    e = first_edit(ctx, ew) if ew is not None else None
    return e if e is not None else w[1]


@register("speckit_bug.check_scripts", params={"rule": True, "window": False, "written_in": False, "edit_in": False, "optional": False}, availability=("trace",), common=False, choices={"rule": ("written", "run", "before_change", "unchanged")})
def check_scripts(item: Item, ctx: EvalContext) -> Result:
    """rule: written | run | before_change | unchanged -- a check script written under BUG_DIR/checks/ in the window; one of them (written in ``written_in``) executed in the window; every check first written in ``written_in`` run before the window's first repository edit; no check written before that edit rewritten after it."""
    from recipe.grpo.qwen3_5.workflow_rubric.facts import executed_paths

    p = item.check.params or {}
    rule = str(p.get("rule"))
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    if rule == "written":
        got = written_checks(ctx, w)
        return Result.ok(item, f"{len(got)} written: {got[:2]}") if got else Result.no(item, f"nothing written under {check_dir(ctx)}")
    if rule == "run":
        src = refs.window(ctx, p["written_in"]) if "written_in" in p else (1, ctx.facts.n_steps + 2)
        scripts = set(written_checks(ctx, src)) if src is not None else set()
        if not scripts:
            return Result.no(item, f"no check script under {check_dir(ctx)}")
        ran = sorted({path for step, path in executed_paths(ctx) if refs.in_window(step, w) and path in scripts})
        return Result.ok(item, f"ran {ran[:2]}") if ran else Result.no(item, f"none of {sorted(scripts)[:2]} executed in the window")
    if rule == "before_change":
        end = _edit_bound(item, ctx, w)
        src = refs.window(ctx, p["written_in"]) if "written_in" in p else w
        writes = check_writes(ctx)
        new = sorted(q for q, steps in writes.items() if src is not None and refs.in_window(steps[0], src))
        if not new:
            if p.get("optional"):
                return Result.not_applicable(item, "no check added in the window")
            return Result.no(item, f"no check script under {check_dir(ctx)}")
        good = [q for q in new if seen_before(ctx, q, writes[q], end)]
        bad = sorted(set(new) - set(good))
        return Result.ratio(item, len(good), len(new), f"not run before the change (step {end}): {[posixpath.basename(q) for q in bad[:2]]}" if bad else f"{len(good)} check(s) run before the change (step {end})")
    if rule == "unchanged":
        ew = refs.window(ctx, p["edit_in"]) if "edit_in" in p else refs.window(ctx, f"stage:{item.stage}")
        edit = first_edit(ctx, ew) if ew is not None else None
        if edit is None:
            return Result.not_applicable(item, "no repository edit: no change to keep the checks across")
        writes = check_writes(ctx)
        later = sorted((s, q) for q, steps in writes.items() if steps[0] < edit for s in steps if s > edit and refs.in_window(s, w))
        if later:
            return Result.no(item, f"step {later[0][0]}: {posixpath.basename(later[0][1])} rewritten after the change (step {edit})")
        return Result.ok(item, f"checks written before the change (step {edit}) kept as they were")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit_bug.checks_added
# --------------------------------------------------------------------------------------------
_PATHISH = re.compile(r"[\w./-]*[\w-]\.[A-Za-z]{1,5}\b|[\w./-]+/[\w.-]+")
_FAIL = re.compile(r"^\W*fail(?:ed|s|ure|ing)?\b", re.I)


def _added_rows(body: str) -> list[dict[str, str]]:
    """The Checks Added table's rows as {check, before}: the Before column by its header, else the third."""
    lines = [ln for ln in body.splitlines()[:2000] if ln.strip().startswith("|")]
    if not lines:
        return []
    head = [c.lower() for c in _cells(lines[0])]
    bi = next((i for i, h in enumerate(head) if "before" in h), 2)
    rows = []
    for ln in lines[1:]:
        if _SEP.match(ln.strip()):
            continue
        cells = _cells(ln)
        rows.append({"check": cells[0] if cells else "", "before": cells[bi] if bi < len(cells) else ""})
    return rows


def _resolve_check(cell: str, scripts: list[str]) -> str | None:
    """The check script a row names: a code span or path-like word matched by its path suffix, else by basename."""
    words = [w.strip("`*_ ") for w in (_commands(cell) + _PATHISH.findall(cell))]
    for w in words:
        if not w:
            continue
        for q in scripts:
            if q == w or q.endswith("/" + w.lstrip("./")):
                return q
    names = {posixpath.basename(w) for w in words if w}
    return next((q for q in scripts if posixpath.basename(q) in names), None)


@register("speckit_bug.checks_added", params={"rule": True, "artifact": False, "window": False, "edit_in": False, "optional": False}, availability=("trace", "sandbox_file"), common=False, choices={"rule": ("before_run", "baseline_run")})
def checks_added(item: Item, ctx: EvalContext) -> Result:
    """rule: before_run | baseline_run -- the fix report's Checks Added rows claim fail before the change for a check the run executed before this round's first repository edit; its Baseline: Existing Tests names a valid test run made before that edit."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    text = ctx.artifact_text(_artifact(item), getattr(item.target, "state", "final") or "final")
    if text is None:
        return Result.no(item, "artifact absent")
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    end = _edit_bound(item, ctx, w)
    before = (1, end)  # round 1's code is unchanged from the start; a later round's from the previous change
    if rule == "before_run":
        body = _section(text, "Checks Added")
        if body is None:
            return Result.no(item, "no Checks Added section")
        rows = _added_rows(body)
        if not rows:
            return Result.no(item, "no table rows")
        writes = check_writes(ctx)
        scripts = sorted(writes)
        good, n, why = 0, 0, []
        for r in rows:
            q = _resolve_check(r["check"], scripts)
            if q is None and p.get("optional"):
                continue  # a later round's row for no check script ("none added this round")
            n += 1
            if not _FAIL.match(re.sub(r"[*_`]", "", r["before"]).strip()):
                why.append(f"{r['check'][:30]}: before is {r['before'][:20]!r}")
            elif q is None:
                why.append(f"{r['check'][:30]}: no such check script written")
            elif not seen_before(ctx, q, writes[q], end):
                why.append(f"{posixpath.basename(q)}: not run before the change (step {end})")
            else:
                good += 1
        if not n:
            return Result.not_applicable(item, "no row names a check script")
        return Result.ratio(item, good, n, "; ".join(why[:2]) if why else f"{good} row(s) seen failing before the change")
    if rule == "baseline_run":
        body = _section(text, "Baseline: Existing Tests")
        if body is None:
            return Result.no(item, "no Baseline: Existing Tests section")
        cmds = _commands(body)
        if not cmds:
            if p.get("optional"):
                return Result.not_applicable(item, "the section names no command")
            return Result.no(item, "the section names no command")
        for c in cmds:
            if _command_run(item, ctx, c, before, "test").status == "pass":
                return Result.ok(item, f"baseline {c[:50]!r} run before the change (step {end})")
        return Result.no(item, f"no recorded command is a valid test run before the change (step {end})")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# speckit_bug.no_fetch
# --------------------------------------------------------------------------------------------
_FETCH = re.compile(
    r"(?i)(?:\b(?:curl|wget|lynx|w3m|aria2c)\b[^\n|;&]*\bhttps?://"
    r"|\b(?:urlopen|urlretrieve|requests\.(?:get|post|head|request)|httpx\.(?:get|post|head|stream))\s*\(\s*[rbuf]?['\"]https?://"
    r"|\bgit\s+clone\b[^\n|;&]*\bhttps?://)"
)


@register("speckit_bug.no_fetch", params={"window": False}, availability=("trace",), common=False)
def no_fetch(item: Item, ctx: EvalContext) -> Result:
    """No command fetches a URL: curl / wget / a text browser on a URL, a Python urlopen / requests / httpx call on a URL literal, a git clone of a URL."""
    p = item.check.params or {}
    w = _window(item, ctx) if ("window" in p or item.stage != "global") else (1, ctx.facts.n_steps + 2)
    if w is None:
        return Result.ok(item, "window empty")
    for c in ctx.facts.commands:
        if refs.in_window(c.step, w) and _FETCH.search(c.command[:20000] or ""):
            return Result.no(item, f"step {c.step}: {c.command.strip()[:60]}")
    return Result.ok(item, "no URL fetched")


# --------------------------------------------------------------------------------------------
# speckit_bug.holds
# --------------------------------------------------------------------------------------------
@register("speckit_bug.holds", params={"predicate": True}, availability=("trace", "sandbox_file"), common=False)
def holds(item: Item, ctx: EvalContext) -> Result:
    """The refs predicate holds for the run (``artifact_exists`` / ``field_matches`` / ``exists`` / ``all`` ...)."""
    pred = (item.check.params or {}).get("predicate")
    return Result.ok(item, "holds") if refs.predicate(ctx, pred) else Result.no(item, "does not hold")


__all__ = ["checks_table", "checks_added", "links", "read", "created_files", "check_scripts", "no_fetch", "holds", "table_rows", "result_of", "read_steps", "written_checks", "check_writes", "first_edit", "seen_before"]
