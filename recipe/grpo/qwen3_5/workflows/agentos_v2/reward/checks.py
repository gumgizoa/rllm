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
      {rule: total}              ``Total Tasks: N`` counts the task lines (all, the sub-tasks or the groups); with ``impl_counts``
                                 also those three counted over the groups that are not test-review groups
      {rule: group_subtasks}     every task group has a sub-task line (``N.M``, M > 0) (ratio over the groups)
      {rule: ticked}             share of the task lines ticked ``[x]`` (or marked ⚠️) when the window ends
      {rule: ticked_after_work}  every task ticked in the window was ticked inside it, after a write or a run of a
                                 path it names (ratio; a box ticked untraceably fails); with ``name_files`` only names
                                 with a file extension are files, matched by path suffix, a reading task (Review ...)
                                 by its reads, a task naming no file by any work in the window before the tick, and a
                                 tick after unreplayable writes at the earliest step it can have been made; with
                                 ``not_done_out`` a task whose ⚠️ marks it found not done (:func:`found_not_done`) is left out
      {rule: groups_in_order}    the groups are ticked in order: group k's last tick is not after group k+1's first
                                 (ratio over adjacent pairs); with ``work_between`` there is also some work (a repository or
                                 checks write, a test or script run) between group k's last tick and group k+1's last
                                 ``[x]`` tick
      {rule: later_edits}        every write of tasks.md in the window only ticks boxes or adds ⚠️ marks (ratio);
                                 with ``additions: true`` a write may also add lines (new tasks) and change the
                                 ``Total Tasks`` line, as long as every earlier line is still there, in order; the added
                                 lines are task lines, Task Group headings with the lines under them, or Execution
                                 Order items -- not notes or status sections
      {rule: ticked_passing}     no task group's test sub-task (the one that runs its tests) is ticked ``[x]`` while
                                 the last test result since the code last changed is a failure, unless the report's
                                 test results show a failure (ratio over the groups with such a result; a workflow
                                 whose documents say to fix a failing test before the tick); a sub-task that says it runs the
                                 tests and is ticked with no test result since the last code change before the tick
                                 counts against the rule too
      {rule: warned_after_attempts}  a test sub-task marked ⚠️ instead of ticked has, in its group's stretch, two failing
                                 test results after the group's first code change with a code change or a check-script edit between them
                                 (ratio; same workflows)

* ``agentos_v2.checks`` -- the check scripts under ``S/checks/`` (``dir``)::

      {rule: written}    a check script written in the window
      {rule: pass_last}  each check script run in the window last ran passing, after the window's last code change
                         (ratio; read off each execution's own result); with ``warned: true`` a script left failing
                         counts when a ⚠️ mark that ``warned_after_attempts`` accepts follows a failing run of it; with
                         ``fix_round: true`` git putting content back (stash, checkout) is no code change

* ``agentos_v2.verify`` -- implement-tasks PHASE 3, which begins once every task is ticked (or marked ⚠️): the first
  write of tasks.md after which no task line is open (else the report's first write)::

      {rule: code_frozen}  no repository write after that point ("the code change is complete before PHASE 3");
                           with ``fix_round: true`` writes are accepted when a failing test run of PHASE 3 precedes
                           them and a test run follows them (one return to PHASE 2), and ``suite_run`` and the
                           report rules then read the runs after those writes; with ``dir`` a check script under it
                           that ran failing in PHASE 3 is such a failing run, and its re-run such a run
      {rule: suite_run}    a valid test run between that point and the report's first write
      {rule: whole_suite}  one of those runs is the whole suite (a runner at the repository root selecting nothing,
                           or only top-level test directories)
      {rule: phase2_run}   before that point, a valid test run of the repository's tests after the last code change
                           (a workflow whose documents have the existing tests of the changed code run while
                           implementing; not applicable without a code change)

* ``agentos_v2.report`` -- final-verification.md against tasks.md and the PHASE 3 runs::

      {rule: test_counts}        the Test Summary's Passing / Failing / Errors (and Total) are a PHASE 3 run's counts
      {rule: failed_listed}      every failing test that run names appears in the report (ratio)
      {rule: suite_status}       the Test Suite Results Status agrees with that run: All Passing only without failures;
                                 with ``dir``, Critical Failures is also right when a check script under it last ran
                                 failing (a workflow whose documents give that Status to a failing test the agent wrote)
      {rule: tasks_status}       the Tasks Verification Status agrees with tasks.md: All Complete only when every task
                                 is ticked and none is marked ⚠️; with ``open_tasks`` only a checkbox line left unticked
                                 (or a line marked ⚠️) is an open task
      {rule: incomplete_listed}  a task marked ⚠️ in tasks.md is listed under Incomplete or Issues (not "None"); with
                                 ``open_tasks`` a task left unticked (a checkbox line) too
      {rule: spec_name}          the **Spec:** field names the spec folder
      {rule: overall_status}     the Status at the top follows from the two section Statuses: Failed with Critical
                                 Failures, Passed with Issues with Issues Found or Some Failures, Passed with All
                                 Complete and All Passing (a workflow whose documents give that rule)

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
from recipe.grpo.qwen3_5.workflow_rubric import results as R
from recipe.grpo.qwen3_5.workflow_rubric.checks import register, register_shell_vars
from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN, EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.replay import content_at
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

MAX_CMD = 20_000
MAX_TEXT = 400_000
# the outcome of a script run is read by the common rule (workflow_rubric/results.py), shared with the other workflows
_EXIT, _FAIL_TEXT, _PASS_TEXT, _MARK_WORDS = R.EXIT, R.FAIL_TEXT, R.PASS_TEXT, R.MARK_WORDS
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
# the wider reading of tasks.md's test sub-tasks (``wide_words``, the reward review's B-3): create-tasks.md 58, 67 and 77
# give example wordings only and 111 has the structure adapted, so a test-review or verification group, a documentation
# group (122: "Each implementation task group"), "Test that ..." / "Extend test ..." and a run named in the details count
_CHECK_GROUP = re.compile(
    r"(?i)\btest(?:s|ing)?\b.*\b(?:review|gaps?|coverage|verif\w*|validat\w*)\b|\b(?:review|gaps?|coverage|verif\w*|validat\w*)\b.*\btest"
    r"|^\s*(?:final\s+)?(?:verif\w*|validat\w*)\b"
)
_DOCS_GROUP = re.compile(r"(?i)\b(?:documentation|docs?|changelog|release\s+notes?|docstrings?)\b")
_CODE_GROUP = re.compile(r"(?i)\b(?:fix\w*|implement\w*|change|modify)\b")
_TEST_NOUN = re.compile(r"(?i)\b(?:tests?|check\s+scripts?|checks)\b")  # "check" alone is code: "Add check for db_table"
_WRITE_WIDE = re.compile(r"(?i)\b(?:write|add|create|author|draft|extend|update)\b")
_STARTS_TEST = re.compile(r"(?i)^\s*(?:\*\*)?tests?\b")
_CHECK_TITLE = re.compile(r"(?i)\b(?:tests?|testing|verif\w*)\b")  # a group title that names a check (wide reading)
_CHECK_TASK = re.compile(r"(?i)^\s*(?:\*\*)?(?:verify|confirm|review)\b")  # a task line that leads with checking
_CODE_VERB = re.compile(r"(?i)\b(?:fix|implement|change|modify|patch|edit|refactor)\b")  # ... unless it also changes code


def check_group(title: str, wide: bool = False, tasks: list[str] | tuple[str, ...] = ()) -> bool:
    """A task group that checks tests rather than implements: a test-review group (and, ``wide``, a verification group).

    ``wide`` also reads the group's task lines (``tasks``, every one of them, the ``N.0`` line included): a title that
    names tests or verification anywhere ("Basic Functionality Verification", "Integration Test for ...") over task
    lines that are all test work -- writing or running tests, or verifying / confirming / reviewing -- is a verification
    group too (11-23 table row 13). A title alone is not enough there ("Input Validation" implements), nor are test
    lines under a title that names no check."""
    if (_CHECK_GROUP if wide else _REVIEW_GROUP).search(title or ""):
        return True
    return wide and bool(tasks) and bool(_CHECK_TITLE.search(title or "")) and all(test_work(t) for t in tasks)


def implementation_group(title: str, wide: bool = False, tasks: list[str] | tuple[str, ...] = ()) -> bool:
    """A task group the test-first rule applies to: not a test-review group (``wide``: nor a verification group, nor a
    documentation group that names no code change)."""
    if check_group(title, wide, tasks):
        return False
    return not (wide and _DOCS_GROUP.search(title or "") and not _CODE_GROUP.search(title or ""))


def test_work(text: str) -> bool:
    """A task line that checks rather than changes code (the wide reading): it writes or runs tests, or it leads with
    verifying, confirming or reviewing and changes no code ("Verify the bug is fixed", "Review existing tests in tests/";
    not "Verify and fix the parser")."""
    return writes_tests(text, True) or runs_tests(text, wide=True) or (bool(_CHECK_TASK.match(text or "")) and not _CODE_VERB.search(text or ""))


def writes_tests(text: str, wide: bool = False) -> bool:
    """A sub-task text that writes tests."""
    if not wide:
        return bool(_TEST_WORD.search(text)) and bool(_WRITE_WORD.search(text))
    return (bool(_TEST_NOUN.search(text)) and bool(_WRITE_WIDE.search(text))) or bool(_STARTS_TEST.match(text))


def runs_tests(text: str, details: list[str] = (), wide: bool = False) -> bool:
    """A sub-task text that runs tests (``wide``: also "Test the ..." and a detail line under it that runs them)."""
    if _TEST_WORD.search(text) and _RUN_WORD.search(text):
        return True
    return wide and (bool(_STARTS_TEST.match(text)) or any(_TEST_WORD.search(d) and _RUN_WORD.search(d) for d in details))


def task_details(text: str | None) -> dict[str, list[str]]:
    """Task id -> the lines under its task line up to the next task line or heading (first occurrence of an id)."""
    out: dict[str, list[str]] = {}
    cur: list[str] | None = None
    for line in M.text_lines((text or "")[:MAX_TEXT]):
        line = line[:2000]
        if _HEAD.match(line):
            cur = None
            continue
        m = _TASK.match(line)
        if m:
            cur = None if m.group("id") in out else out.setdefault(m.group("id"), [])
            continue
        if cur is not None and line.strip():
            cur.append(line)
    return out


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


def spec_folder_vars(facts) -> dict[str, str | None]:
    """shape-spec.md's shell variables for the spec folder (``TODAY``, ``SPEC_NAME``, ``DATED_SPEC_NAME``, ``SPEC_PATH``),
    read off the folder the run left in the sandbox. The agent's shell keeps them for the whole session; the replay
    sees one command at a time, so without them ``cat > $SPEC_PATH/tasks.md`` is a write to an unknown path."""
    spec_dir = (facts.artifact_paths.get("spec_dir") or "").rstrip("/")
    if not spec_dir:
        return {}
    name = posixpath.basename(spec_dir)
    out: dict[str, str | None] = {"SPEC_PATH": spec_dir, "DATED_SPEC_NAME": name}
    m = re.fullmatch(rf"({F.DATE_RX})-(.+)", name)
    if m:
        out.update(TODAY=m.group(1), SPEC_NAME=m.group(2))
    return out


register_shell_vars("agentos_v2", spec_folder_vars)


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


# the folder of the check scripts under the spec folder, where a rule names it without a ``dir`` parameter (``report``'s
# ``scripts_dir`` overrides it: agentos_bugfix calls the folder ``verify/``)
SCRIPTS_DIR = "{artifact}/{SPEC}/checks"


def _expand_dir(ctx: EvalContext, template: str) -> str | None:
    s, left = F.expand(template, F.roots_of(ctx.rubric, ctx.collected.workdir), ctx.collected.workdir, ctx.facts.var_bindings)
    return posixpath.normpath(s) if s.startswith("/") and not left else None


# the shell segments of a command, what a segment executes and how its run came out: the common rule
_segments, _executed_by, _others_print, _exit_code = R.segments, R.executed_by, R.others_print, R.exit_code
outcome, executions = R.outcome, R.executions


def edited_sources(ctx: EvalContext) -> set[str]:
    """Repository files other than tests the run edited itself (not git putting content back): the files a
    ``git checkout`` / ``git restore`` can put the change of away (``results.stash_marks``)."""
    return {e.path for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_test_path(e.path) and not F.is_generated(e.path)}


def authored_write_steps(ctx: EvalContext) -> list[int]:
    """Steps of the repository writes the run authored (not git putting content back, not run byproducts): the writes
    that end a stash or a checkout of an edited file (``results.stash_states``), whatever file they write -- the file a
    checkout put back included, so writing it again is a change in place again."""
    return sorted({int(e.step) for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_generated(e.path)})


def change_runs(ctx: EvalContext) -> list:
    """The valid test runs made with the change in place: a run while the change is stashed away (from a ``git stash``
    to the next ``pop`` / ``apply``, or to the next repository write the agent authors) tested the old code, and says
    nothing of the code the report, the ticks and the PHASE 2 / 3 checks are about (the common rule,
    ``results.stash_states``)."""
    key = "agentos_v2.change_runs"
    if key not in ctx.cache:
        fx = ctx.facts
        before, marks = R.stash_states(fx.commands, authored_write_steps(ctx), edited_sources(ctx))  # a checkout of an edited source file too (F-3)
        ctx.cache[key] = [r for r in fx.runs if r.valid and r.kind == "test" and not R.run_stashed(r, before, marks)]
    return ctx.cache[key]


def _content_events(ctx: EvalContext, path: str) -> list:
    return [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]


def _change_steps(ctx: EvalContext, w, authored: bool = False) -> list[int]:
    """Steps of the writes to repository files that are part of the final change (run byproducts aside), in the window;
    ``authored``: without git putting content back (``git stash`` / ``stash pop`` / ``checkout``), which edits nothing."""
    keep = F.change_paths(ctx)
    return sorted(
        {e.step for e in ctx.facts.repo_writes if e.ok is not False and e.path in keep and not F.is_generated(e.path) and refs.in_window(e.step, w) and not (authored and e.op == "unknown")}
    )


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


@register("agentos_v2.read", params={"artifacts": True, "window": False, "absent_unread": False, "written_before": False}, availability=("trace", "sandbox_file"), common=False)
def read(item: Item, ctx: EvalContext) -> Result:
    """Every listed artifact that exists at the end was read in the window (default: the item's stage).

    not_applicable when none of them exists. ``absent_unread``: an artifact absent at the end counts as not read (a run
    that never wrote the file has not read it), so the ratio is over every listed artifact and none existing fails.
    ``written_before``: an artifact the run itself wrote before the window counts as read -- it is in the conversation
    (create-tasks.md 13: read the files only if they are not in the current conversation)."""
    p = item.check.params or {}
    w = _window(item, ctx)
    listed = {a: ctx.facts.artifact_paths.get(a) for a in (p.get("artifacts") or []) if isinstance(a, str)}
    want = {a: q for a, q in listed.items() if q}
    absent = [a for a, q in listed.items() if not q] if p.get("absent_unread") else []
    if not want:
        return Result.no(item, f"absent, so not read: {absent}") if absent else Result.not_applicable(item, "none of the artifacts exists")
    if w is None:
        return Result.no(item, "window empty")
    hits = read_steps(ctx, sorted(set(want.values())), w)
    missing = [a for a, q in want.items() if not hits.get(q)]
    if p.get("written_before") and w[0] is not None:
        missing = [a for a in missing if not any(e.step < w[0] for e in _content_events(ctx, want[a]))]
    missing += absent
    total = len(want) + len(absent)
    return Result.ratio(item, total - len(missing), total, f"not read: {missing}" if missing else f"read: {sorted(want)}")


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


# a basis that names no source: a path, a code span, an identifier or a word for the task or the repository would be one
_SOURCE_WORD = re.compile(r"(?i)\b(?:task|issue|description|repository|repo|codebase|grep|search|traceback|error|test|docs?)\b")
_CODEISH = re.compile(r"`[^`]+`|[\w.]*\w/[\w./-]+|\b\w+\.\w+\b|\b\w+_\w+\b|\w+\(\)")
_GENERIC = re.compile(
    r"(?i)^(?:(?:standard|common|best|general|generic|usual|typical|comprehensive)\b[\w\s-]{0,30}?\b(?:practices?|approach|patterns?|conventions?|testing)"
    r"|(?:correct|yes|no|n/?a|none|needed|assumed|obvious(?:ly)?|i think so|makes sense|reasonable|need to verify)(?: [\w-]+){0,3})\.?$"
)


def _no_basis(value: str) -> bool:
    """An answer's basis (after the dash) names nothing in the task description or the repository: no path, code span,
    identifier or source word, and three words or fewer or a generic phrase only ("Standard testing practice")."""
    basis = re.split(r"\s(?:—|–|--?)\s", value, maxsplit=1)[-1].strip()
    if _SOURCE_WORD.search(basis) or _CODEISH.search(basis):
        return False
    return len(re.findall(r"[\w'/.()-]+", basis)) <= 3 or _GENERIC.match(basis) is not None


@register("agentos_v2.requirements", params={"rule": True, "artifact": False, "basis_check": False}, availability=("sandbox_file",), common=False, choices={"rule": ("answers", "initial_description")})
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
        bad = [q for q, v in qs if not v or not _ANSWER_OK.match(v.strip()) or (p.get("basis_check") and _no_basis(v.strip()))]
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


@register("agentos_v2.blocks", params={"section": True, "artifact": False, "min_blocks": False, "max_blocks": False, "max_bullets": False, "top_level": False}, availability=("sandbox_file",), common=False)
def blocks(item: Item, ctx: EvalContext) -> Result:
    """The section's bold-named blocks (a ``**name**`` line, then bullets) number min_blocks (1) .. max_blocks, each with 1 .. max_bullets bullets.

    Ratio over the blocks; a block count out of range fails. ``top_level``: a bullet indented deeper than its block's
    first bullet is a sub-bullet and not counted, and bullets before the first name, in a section that has named
    blocks, are a block of their own (a workflow whose documents count "bullets" of a block, not their sub-bullets)."""
    p = item.check.params or {}
    text = _text(ctx, _artifact(item))
    if text is None:
        return Result.no(item, "artifact absent")
    sec = M.section(text, str(p["section"]))
    if sec is None:
        return Result.no(item, f"no {p['section']!r} section")
    found: list[tuple[str, int]] = []
    lines = M.text_lines(sec)
    top = bool(p.get("top_level"))
    lead = top and any(_BLOCK.match(ln) for ln in lines)
    indent: list[int | None] = []
    for ln in lines:
        m = _BLOCK.match(ln)
        if m:
            found.append((m.group("name").strip(), 0))
            indent.append(None)
            continue
        if not _BULLET.match(ln):
            continue
        if not found:
            if not lead:
                continue
            found.append(("(bullets before the first name)", 0))
            indent.append(None)
        if top:
            ind = len(ln) - len(ln.lstrip())
            if indent[-1] is None:
                indent[-1] = ind
            elif ind > indent[-1]:
                continue
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
def _group_task_texts(ts: list[dict]) -> dict[str, list[str]]:
    """Task group heading -> the text of every task line under it (the ``N.0`` line included), for :func:`check_group`."""
    out: dict[str, list[str]] = {}
    for t in ts:
        if t["group"]:
            out.setdefault(t["group"]["heading"], []).append(t["rest"])
    return out


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


def tick_bounds(ctx: EvalContext, aid: str) -> dict[str, tuple[int, int]]:
    """Task id -> (earliest, latest) step its box can have been first ticked or marked at. The latest is the write after
    which it is first seen done; the earliest is the same write, or -- when writes whose content cannot be replayed come
    between it and the last known content -- the first of those writes (:func:`tick_steps` gives ``UNKNOWN`` there)."""
    path = ctx.facts.artifact_paths.get(aid)
    out: dict[str, tuple[int, int]] = {}
    if not path:
        return out
    blind_from = None
    for e in ctx.facts.writes.get(path, []):
        if e.ok is False or e.op in ("delete", "move_out"):
            continue
        if e.content is None:
            blind_from = e.step if blind_from is None else blind_from
            continue
        for t in task_lines(e.content):
            if _done(t) and t["id"] not in out:
                out[t["id"]] = (blind_from if blind_from is not None else e.step, e.step)
        blind_from = None
    return out


def all_done_step(ctx: EvalContext, aid: str = "tasks"):
    """The first write of tasks.md after which it has task lines and every one is ticked or marked ⚠️ (None: never;
    ``UNKNOWN``: only the sandbox's final file shows it). A write whose content cannot be replayed is passed over: the
    first write whose known content has every task done gives the step, even when such a write comes before it."""
    path = ctx.facts.artifact_paths.get(aid)
    if not path:
        return None
    for e in ctx.facts.writes.get(path, []):
        if e.ok is False or e.op in ("delete", "move_out") or e.content is None:
            continue
        ts = task_lines(e.content)
        if ts and all(_done(t) for t in ts):
            return e.step
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


# what a task line names as a file (``name_files``, the reward review's B-1): the last part of the name ends with one of
# these extensions -- ``subprocess.run``, ``content_type.save``, ``wspace/hspace`` are code, not files
FILE_EXT = re.compile(r"\.(?:py|pyx|pyi|c|h|cpp|js|ts|txt|rst|md|cfg|toml|ini|json|ya?ml|html|css|sh|in|po|mo|csv|xml|tex)$", re.I)
# a task whose work is reading: its text starts with one of these verbs (Review tests from Task Group 1, Analyze ...)
READ_VERB = re.compile(r"(?i)^\s*(?:\*\*)?\s*(?:analy[sz]e|review|investigate|identify|locate|examine|inspect|understand|read|study|explore|find|look|trace)\b")
_INTERPRETERS = re.compile(r"^(?:python[0-9.]*|bash|sh|node)$")


def named_files(desc: str, workdir: str | None) -> set[str]:
    """The paths of :func:`named_paths` that name a file: the last part ends with a known extension (:data:`FILE_EXT`)."""
    return {q for q in named_paths(desc, workdir) if "@" not in q and FILE_EXT.search(posixpath.basename(q.rstrip("/")))}


def _same_file(name: str, path: str) -> bool:
    """``path`` (repository-relative or absolute) is the file ``name`` names: the same, or it ends with ``/`` + name."""
    name = name.strip("/")
    path = path.rstrip("/")
    return bool(name) and (path == name or path.endswith("/" + name))


def file_evidence_steps(ctx: EvalContext, names: set[str], w, reads: bool = False) -> list[int]:
    """Steps that wrote or ran a file a task names, matched by :func:`_same_file` (``table.py`` is
    ``astropy/table/table.py``); with ``reads`` also steps that read it in the window."""
    steps = [e.step for path, evs in ctx.facts.writes.items() if any(_same_file(n, path) for n in names) for e in evs if e.ok is not False]
    steps += [e.step for e in ctx.facts.repo_writes if e.ok is not False and any(_same_file(n, e.path) for n in names)]
    steps += [st for st, path in F.executed_paths(ctx) if any(_same_file(n, path) for n in names)]
    if reads:
        steps += [st for st, rel in _repo_reads(ctx, w) if any(_same_file(n, rel) for n in names)]
    return steps


def work_steps(ctx: EvalContext, d: str | None) -> list[int]:
    """Steps that did some work: a repository write, a write under the checks folder ``d``, a test-runner call (valid or
    not), a script run, an interpreter call (python, bash, sh, node in command position)."""
    key = ("agentos_v2.work_steps", d)
    if key in ctx.cache:
        return ctx.cache[key]
    out = {int(e.step) for e in ctx.facts.repo_writes if e.ok is not False}
    if d:
        pre = d.rstrip("/") + "/"
        out |= {int(e.step) for path, evs in ctx.facts.writes.items() if path.startswith(pre) for e in evs if e.ok is not False}
    out |= {int(r.step) for r in ctx.facts.runs}
    out |= {int(st) for st, _ in F.executed_paths(ctx)}
    for c in ctx.facts.commands:
        try:
            segs = shell.flat(shell.split((c.command or "")[:MAX_CMD], c.cwd)[0])
        except Exception:  # noqa: BLE001 -- agent text
            continue
        if any(seg.verb and _INTERPRETERS.match(seg.verb) for seg in segs):
            out.add(int(c.step))
    ctx.cache[key] = sorted(out)
    return ctx.cache[key]


def _evidence_steps(ctx: EvalContext, paths: set[str], checks_dir: str | None) -> list[int]:
    """Steps that wrote or ran one of ``paths`` (repository-relative, absolute, or ``checks/<name>`` under the checks dir).
    The relative form is the checks dir's own folder name (``checks`` here; a workflow that names the folder otherwise
    passes that folder as ``checks_dir``)."""
    wd = (ctx.collected.workdir or "").rstrip("/")
    own = posixpath.basename(checks_dir.rstrip("/")) + "/" if checks_dir else None
    absolute = set()
    for q in paths:
        if q.startswith("/"):
            absolute.add(q)
        elif own and q.startswith(own):
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


_TOTAL_LINE = re.compile(r"(?i)^\s*(?:[-*+]\s+)?(?:\*\*)?Total\s+Tasks")


def _only_adds(prev: list[str], new: list[str]) -> bool:
    """``new`` is ``prev`` with lines added (the ``Total Tasks`` line may differ): no earlier line gone or reworded."""
    it = iter(ln for ln in new if not _TOTAL_LINE.match(ln))
    return all(any(ln == x for x in it) for ln in prev if not _TOTAL_LINE.match(ln))


_ORDER_ITEM = re.compile(r"^\s*\d+[.)]\s+\S")


def added_lines_ok(prev: list[str], new: list[str]) -> list[str]:
    """The lines ``new`` adds to ``prev`` (:func:`_only_adds` holds) that are not task-list lines: what implement-tasks.md 25
    lets a run add is a new sub-task or a new task group at the end. Allowed: a blank line, the ``Total Tasks`` line, a
    task line, a ``Task Group`` heading, the lines that follow an added task line or heading without an earlier line
    between (its details, Dependencies, Acceptance Criteria), and a numbered line of the Execution Order section."""
    bad, j, block, section = [], 0, False, ""
    keep = [ln for ln in prev if not _TOTAL_LINE.match(ln)]
    for ln in new:
        if _HEAD.match(ln):
            section = ln
        if j < len(keep) and ln == keep[j]:
            j += 1
            block = False
            continue
        if not ln.strip() or _TOTAL_LINE.match(ln):
            continue
        if _TASK.match(ln) or _GROUP.match(ln.strip()):
            block = True
            continue
        if _HEAD.match(ln):
            block = False  # another added heading (Implementation Notes, Status) is no task
        if block or (re.search(r"(?i)execution\s+order", section) and _ORDER_ITEM.match(ln)):
            continue
        bad.append(ln.strip()[:60])
    return bad


def _known_before(evs: list, e) -> str | None:
    """The last known content among the events of ``evs`` before ``e`` (None when none is known)."""
    prev = None
    for x in evs:
        if x is e:
            break
        if x.content is not None:
            prev = x.content
    return prev


def _test_results(ctx: EvalContext, d: str | None) -> list[tuple[int, str]]:
    """(step, ``pass`` | ``fail``) of every test result the trace shows, in order: a check script's run whose outcome can
    be read, a valid test run by its counts. Within one step a failure comes last."""
    out = _script_results(ctx, d)
    out += [(r.step, "fail" if r.failed + r.errors > 0 else "pass") for r in change_runs(ctx)]
    return sorted(out, key=lambda x: (x[0], x[1] == "fail"))


def timed_results(ctx: EvalContext, d: str | None) -> list[tuple[int, str, bool]]:
    """:func:`_test_results` with, per result, whether its run came after a repository write of its own call
    (``RunFact.after_write_same_call``: ``sed -i ... && pytest``). Within one step a failure comes last."""
    out = [(st, o, False) for st, o in _script_results(ctx, d)]
    out += [(r.step, "fail" if r.failed + r.errors > 0 else "pass", bool(getattr(r, "after_write_same_call", False))) for r in change_runs(ctx)]
    return sorted(out, key=lambda x: (x[0], x[1] == "fail"))


def _script_results(ctx: EvalContext, d: str | None) -> list[tuple[int, str]]:
    """(step, ``pass`` | ``fail``) of every run of a check script under ``d`` whose outcome can be read."""
    if not d:
        return []
    return [(st, o) for rs in executions(ctx, set(check_scripts(ctx, d))).values() for st, o in rs if o in ("pass", "fail")]


def _failing_results_at(ctx: EvalContext, d: str | None, step: int) -> list[R.TestResult]:
    """The failing results of ``step`` (as :func:`timed_results` reads them): valid runner runs with the change in place,
    and check-script runs under ``d``."""
    out = [runner_result(r, ctx.collected.workdir, ctx) for r in change_runs(ctx) if r.step == step and r.failed + r.errors > 0]
    if d:
        out += [R.TestResult(step, False, False, (s_,)) for s_, rs in executions(ctx, set(check_scripts(ctx, d))).items() if any(st == step and o == "fail" for st, o in rs)]
    return out


def _test_subtasks(ts: list[dict]) -> list[dict]:
    """Per task group, in order, the sub-task that runs its tests: the last one whose text says so, else its last sub-task."""
    by: dict[int, list[dict]] = {}
    for t in ts:
        if t["group"] and not t["id"].endswith(".0"):
            by.setdefault(t["group"]["n"], []).append(t)
    out = []
    for n in sorted(by):
        runs = [t for t in by[n] if _TEST_WORD.search(t["rest"]) and _RUN_WORD.search(t["rest"])]
        out.append((runs or by[n])[-1])
    return out


def _warn_steps(ctx: EvalContext, aid: str) -> dict[str, int | None]:
    """Task id -> the step of the write after which its line first carries ⚠️ (``UNKNOWN`` as in :func:`tick_steps`)."""
    out: dict[str, int | None] = {}
    blind = False
    for e in ctx.facts.writes.get(ctx.facts.artifact_paths.get(aid) or "", []):
        if e.ok is False or e.op in ("delete", "move_out"):
            continue
        if e.content is None:
            blind = True
            continue
        for t in task_lines(e.content):
            if t["warned"] and t["id"] not in out:
                out[t["id"]] = UNKNOWN if blind else e.step
    return out


def _group_ends(ctx: EvalContext, aid: str, text: str, w, d: str | None) -> list[dict]:
    """Per task group of ``text``, in order: its test sub-task, the step that sub-task was ticked or marked at (None when
    it was not, or untraceably), and the test results and code changes of the group's own stretch -- from the previous
    group's end (the window's start for the first) up to that step."""
    when = tick_steps(ctx, aid)
    results = _test_results(ctx, d)
    changes = _change_steps(ctx, w, authored=True)
    out, start = [], w[0]
    for t in _test_subtasks(task_lines(text)):
        s = when.get(t["id"])
        if not _done(t) or s is None or s is UNKNOWN or not refs.in_window(s, w):
            out.append({"task": t, "step": None, "results": [], "changes": []})
            continue
        out.append({"task": t, "step": s, "results": [x for x in results if start <= x[0] < s], "changes": [c for c in changes if start <= c < s]})
        start = max(start, s)
    return out


def _phase3_opening(ctx: EvalContext, aid: str, d: str | None):
    """The step PHASE 3 opens at for a ⚠️ mark: :func:`phase3_start`, moved back over the tasks.md writes that come right
    before the write at which every task first appears done, with no work step (:func:`work_steps`) between them. A run
    that ticks or marks its last lines one edit at a time opens PHASE 3 with the first of those edits, as one write of
    all the lines would; a tasks.md write with work after it and before the next one is not part of that opening."""
    start = phase3_start(ctx)
    done = all_done_step(ctx, aid)
    if done is None or done is UNKNOWN or start is None or start is UNKNOWN:
        return start
    work = work_steps(ctx, d)
    first = start
    steps = {e.step for e in ctx.facts.writes.get(ctx.facts.artifact_paths.get(aid) or "", []) if e.ok is not False and isinstance(e.step, int)}
    for st in sorted((x for x in steps if x < start), reverse=True):
        if any(st < x < first for x in work):
            break
        first = st
    return first


def _marked_in_phase3(ctx: EvalContext, warn_step, aid: str = "tasks", d: str | None = None) -> bool:
    """B-5 (user decision 2026-11-21): whether a ⚠️ first seen at ``warn_step`` can be PHASE 3 Step 1's mark (a task found
    not done, implement-tasks.md 127): it first appears at or after PHASE 3's opening (:func:`_phase3_opening`: the write
    at which every task first appears ticked or marked, with the tasks.md writes right before it that no work separates
    from it; else the report's first write). A mark first seen before that is PHASE 2's (implement-tasks.md 40: a test the
    attempts did not get to pass). When either step is unknown (a write whose content cannot be replayed) the mark is
    given the benefit of the doubt; with no PHASE 3 start at all it is PHASE 2's."""
    if warn_step is None or warn_step is UNKNOWN:
        return True
    start = _phase3_opening(ctx, aid, d)
    if start is UNKNOWN:
        return True
    return start is not None and warn_step >= start


def found_not_done(ctx: EvalContext, aid: str, w, d: str | None) -> set[str]:
    """B-5: the ids of the task lines whose ⚠️ is PHASE 3 Step 1's "task found not done" mark (implement-tasks.md 127):
    the line was first seen done with ⚠️ (marked, not ticked first), (a) its task group's stretch holds no failing test
    result after the group's first code change, and (b) the mark first appears in PHASE 3 or at the write that starts it
    (:func:`_marked_in_phase3`). A group whose test sub-task was never traceably ticked or marked has no stretch: its
    lines are not counted here."""
    text = _window_end_text(ctx, aid, w)
    if text is None:
        return set()
    first_done, first_warn = tick_steps(ctx, aid), _warn_steps(ctx, aid)
    clean = {g["task"]["group"]["heading"] for g in _group_ends(ctx, aid, text, w, d)
             if g["step"] is not None and g["task"]["group"] and not [st for st, o in g["results"] if o == "fail" and g["changes"] and st > g["changes"][0]]}
    return {t["id"] for t in task_lines(text)
            if t["warned"] and first_warn.get(t["id"]) == first_done.get(t["id"]) and t["group"] and t["group"]["heading"] in clean
            and _marked_in_phase3(ctx, first_warn.get(t["id"]), aid, d)}


def warned_groups(ctx: EvalContext, aid: str, w, d: str | None) -> list[tuple[dict, bool]]:
    """(group end, attempts shown) for every test sub-task marked ⚠️ instead of ticked: two failing test results after
    the group's first code change, with an attempt between the first and the last of them -- a code change, or an edit
    of a check script under ``d`` (the failing test may be the thing to fix). A mark is a task found not done (PHASE 3
    Step 1, implement-tasks.md 127), not this rule's, only when (a) its group's stretch holds no failing result after the
    group's first code change and (b) it first appears in PHASE 3 or at the write that starts it (B-5, user decision
    2026-11-21: :func:`_marked_in_phase3`); a mark made earlier without a failing result shows no attempt."""
    text = _window_end_text(ctx, aid, w)
    if text is None:
        return []
    first_done, first_warn = tick_steps(ctx, aid), _warn_steps(ctx, aid)
    script_edits = sorted({e.step for p in (check_scripts(ctx, d) if d else []) for e in _content_events(ctx, p)})
    out = []
    for g in _group_ends(ctx, aid, text, w, d):
        t = g["task"]
        if not t["warned"] or first_warn.get(t["id"]) != first_done.get(t["id"]):
            continue  # ticked first and marked later is PHASE 3's mark (a task found incomplete), not this rule's
        fails = [st for st, o in g["results"] if o == "fail" and g["changes"] and st > g["changes"][0]]
        if not fails:
            if _marked_in_phase3(ctx, first_warn.get(t["id"]), aid, d):
                continue  # no failing result to mark, marked in PHASE 3: a task found not done (127), not a test left failing (40)
            out.append((g, False))  # marked while implementing with no failing result behind it: no attempt shown (40)
            continue
        out.append((g, len(fails) >= 2 and any(fails[0] < c < fails[-1] for c in (*g["changes"], *script_edits))))
    return out


# --------------------------------------------------------------------------------------------
# Failures the documents do not ask the run to fix (R2 of the agentos_bugfix reward review; agentos_v2's rubric uses none)
# --------------------------------------------------------------------------------------------
# how a report says that a failing test asserts the behavior the task changes (implement-tasks.md of agentos_bugfix, T1:
# "list that test under Failed Tests ..., noting that it is an expected failure")
EXPECTED_WORDS = (
    re.compile(r"(?i)\b(?:asserts?|expects?|checks?|tests?|encodes?)\b[^.\n]{0,120}\b(?:old|previous|prior|former|original|buggy|legacy)\s+behaviou?r"),
    re.compile(r"(?i)\b(?:asserts?|expects?|checks?)\b[^.\n]{0,120}\b(?:this|the)\s+(?:task|change|fix|issue)\s+(?:removes|changes|fixes|asks)"),
    re.compile(r"(?i)\bexpected\s+(?:to\s+fail|failure)\b"),
    re.compile(r"(?i)\btest\s+(?:should|needs?\s+to)\s+be\s+updated\b"),
)
_BULLET_START = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def runner_result(r, workdir: str | None, ctx: EvalContext | None = None) -> R.TestResult:
    """A valid runner run as a :class:`results.TestResult`: its files (``WHOLE`` for the whole suite), what narrows it,
    and the ids of its failed tests when its output names them all."""
    files = R.run_files(r, workdir)
    whole = bool(_whole(r, workdir, ctx))
    return R.TestResult(int(r.step), not (r.failed + r.errors), True, files if files and not whole else (R.WHOLE,), R.selection(r.segment), R.run_failed_ids(r.failed, r.errors, r.observation or ""))


def stashed_results(ctx: EvalContext) -> list[R.TestResult]:
    """The valid runner runs made with the change stashed away (the complement of :func:`change_runs`), as results."""
    key = "agentos_v2.stashed_results"
    if key not in ctx.cache:
        fx = ctx.facts
        before, marks = R.stash_states(fx.commands, authored_write_steps(ctx), edited_sources(ctx))
        ctx.cache[key] = [runner_result(r, ctx.collected.workdir, ctx) for r in fx.runs if r.valid and r.kind == "test" and R.run_stashed(r, before, marks)]
    return ctx.cache[key]


def _paragraphs(text: str) -> list[str]:
    """Blocks of ``text`` split at blank lines and at the start of a bullet or numbered item."""
    out, cur = [], []
    for ln in text.splitlines():
        if not ln.strip() or _BULLET_START.match(ln):
            if cur:
                out.append("\n".join(cur))
            cur = [ln] if ln.strip() else []
        else:
            cur.append(ln)
    if cur:
        out.append("\n".join(cur))
    return out


def _entries(section: str, forms: set[str]) -> list[str]:
    """Each entry of a list section that names one of ``forms``: the line with the name and the lines under it that are
    indented deeper (a reason on the next line, ``- **Reason:** ...`` sub-bullets), up to the next line at the same or a
    shallower indent."""
    lines = section.splitlines()
    out = []
    for i, ln in enumerate(lines):
        if not any(f in ln for f in forms):
            continue
        ind = len(ln) - len(ln.lstrip())
        block = [ln]
        for nxt in lines[i + 1 :]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= ind:
                break
            block.append(nxt)
        out.append("\n".join(block))
    return out


def _test_names_of(test_id: str) -> set[str]:
    """The function / class names of a test id (``file::Class::test_x[1]`` -> Class, test_x; ``mod.Class.test_x`` too)."""
    parts = test_id.split("::")[1:] if "::" in test_id else test_id.split(".")[-2:]
    return {p.split("[")[0] for p in parts if p}


def reported_as_expected(ctx: EvalContext, test_id: str) -> bool:
    """The final report lists ``test_id`` under Failed Tests, and that entry (its line and the lines indented under it)
    -- or a paragraph of Notes that names the test or its file -- says it asserts the behavior the task changes
    (:data:`EXPECTED_WORDS`)."""
    text = _text(ctx, "final_verification") if "final_verification" in ctx.rubric.artifacts else None
    if not text:
        return False
    forms = refs.id_forms(test_id)
    failed = M.section(text, "Failed Tests", match="prefix") or ""
    lines = _entries(failed, forms)
    if not lines:
        return False
    file_part = test_id.split("::")[0] if "::" in test_id else None
    notes = M.section(text, "Notes", match="prefix") or ""
    paras = [b for b in _paragraphs(notes) if any(f in b for f in forms) or (file_part and file_part.lstrip("./") in b)]
    return any(rx.search(x) for x in (*lines, *paras) for rx in EXPECTED_WORDS)


def excused_failures(ctx: EvalContext, units) -> set:
    """Of ``units`` -- (failure unit, the result that failed it), as :func:`results.standing_units` gives them -- the ones
    the documents do not ask the run to fix (implement-tasks.md of agentos_bugfix 39, 135-138):

    * an existing test that asserts the behavior the task asks to change: a test unit of a runner run, in a test file the
      run did not create, not a test function the run added (F-2's reading), that the final report lists under Failed
      Tests and says asserts the old behavior (:func:`reported_as_expected`);
    * a failure that is there without the change: a valid runner run with the change stashed away ran the unit and
      failed it -- the test among its failed ids, or (a file unit) a run of that file that failed. When the check was made
      does not matter: it is what the run itself found out.
    """
    out = set()
    stashed = [s for s in stashed_results(ctx) if not s.passed]
    added = None
    wd = (ctx.collected.workdir or "").rstrip("/") + "/"
    for unit, failing in units:
        kind, what = unit
        if kind == "test":
            if any(any(R._under(what, i) and R._under(i, what) for i in s.failed_ids) for s in stashed):
                out.add(unit)
                continue
            if not failing.runner:
                continue
            if added is None:
                added = {n for _, names in module_tests(ctx).values() for n in names}
            rel = what.split("::")[0].removeprefix(wd).lstrip("./") if "::" in what else None
            if rel and F.is_new_path(ctx, rel):
                continue
            if _test_names_of(what) & added:
                continue
            if reported_as_expected(ctx, what):
                out.add(unit)
        elif any(R.runs_key(s, what) for s in stashed):
            out.add(unit)
    return out


@register(
    "agentos_v2.tasks",
    params={"rule": True, "artifact": False, "window": False, "dir": False, "additions": False, "suite_section": False, "wide_words": False, "impl_counts": False, "name_files": False, "work_between": False, "not_done_out": False},
    availability=("sandbox_file", "trace"),
    common=False,
    choices={"rule": ("group_parts", "test_first", "total", "ticked", "ticked_after_work", "groups_in_order", "later_edits", "ticked_passing", "warned_after_attempts", "group_subtasks")},
)
def tasks(item: Item, ctx: EvalContext) -> Result:
    """rule: group_parts | test_first | total | ticked | ticked_after_work | groups_in_order | later_edits | ticked_passing | warned_after_attempts -- tasks.md's task groups, test sub-tasks, count, and its ticks and ⚠️ marks against the work and the test results."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = _artifact(item, "tasks")
    if rule in ("group_parts", "test_first", "total", "group_subtasks"):
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
        if rule == "group_subtasks":  # every task group has a sub-task (create-tasks.md 26: "groups with sub-tasks")
            if not gs:
                return Result.no(item, "no '#### Task Group N:' heading")
            ts = task_lines(text)
            empty = [g["n"] for g, _ in gs if not any(t["group"] and t["group"]["heading"] == g["heading"] and not t["id"].endswith(".0") for t in ts)]
            return Result.ratio(item, len(gs) - len(empty), len(gs), f"task groups without a sub-task: {empty[:4]}" if empty else f"{len(gs)} groups with sub-tasks")
        if rule == "test_first":
            ts = task_lines(text)
            wide = bool(p.get("wide_words"))
            details = task_details(text) if wide else {}
            pool = [(g, [t for t in ts if t["group"] and t["group"]["heading"] == g["heading"] and not t["id"].endswith(".0")]) for g, _ in gs]
            lines = _group_task_texts(ts)
            pool = [(g, subs) for g, subs in pool if implementation_group(g["title"], wide, lines.get(g["heading"], []))]
            if not pool:
                return Result.no(item, "no implementation task group")
            good, bad = 0, []
            for g, subs in pool:
                first_ok = bool(subs) and writes_tests(subs[0]["rest"], wide)
                last_ok = len(subs) >= 2 and runs_tests(subs[-1]["rest"], details.get(subs[-1]["id"], []), wide)
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
        if p.get("impl_counts"):  # the same three counts over the implementation groups (the test-review group left out)
            wide = bool(p.get("wide_words"))
            lines = _group_task_texts(ts)
            impl = [t for t in ts if t["group"] and not check_group(t["group"]["title"], wide, lines.get(t["group"]["heading"], []))]
            counts |= {len(impl), len([t for t in impl if not t["id"].endswith(".0")]), len([g for g, _ in gs if not check_group(g["title"], wide, lines.get(g["heading"], []))])}
        return Result.ok(item, f"Total Tasks {n}") if n in counts and n > 0 else Result.no(item, f"Total Tasks {n} counts none of {sorted(counts)}")
    w = _window(item, ctx)
    path = ctx.facts.artifact_paths.get(aid)
    if path is None:
        return Result.not_applicable(item, "tasks.md absent: nothing marked ⚠️") if rule == "warned_after_attempts" else Result.no(item, "tasks.md absent")
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
        if rule == "ticked_after_work" and p.get("not_done_out") and pool:  # B-5: a task marked found not done claims no work
            out = found_not_done(ctx, aid, w, _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None)
            pool = [t for t in pool if t["id"] not in out]
            if not pool:
                return Result.not_applicable(item, "no task ticked in the window (only tasks marked ⚠️ as found not done)")
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
            if p.get("work_between"):  # one task group per pass of PHASE 2: some work between a group's last tick and the next one's
                ws = work_steps(ctx, _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None)
                done: dict[int, list[int]] = {}  # [x] ticks only: a group marked ⚠️ throughout says it was not implemented
                for t in pool:
                    s_ = when.get(t["id"])
                    if t["group"] and t["checked"] and s_ is not None and s_ is not UNKNOWN:
                        done.setdefault(t["group"]["n"], []).append(s_)
                good = [a for a, b in pairs if a in good and (b not in done or any(max(by[a]) < x <= max(done[b]) for x in ws))]
            return Result.ratio(item, len(good), len(pairs), f"{len(good)}/{len(pairs)} adjacent groups ticked in order")
        d = _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None
        nf = bool(p.get("name_files"))
        bounds = tick_bounds(ctx, aid) if nf else {}
        bad = []
        for t in pool:
            s = when.get(t["id"])
            if nf and s is UNKNOWN and t["id"] in bounds:
                s = bounds[t["id"]][0]  # evidence before the earliest step the tick can have been made at
            if s is None or s is UNKNOWN or not refs.in_window(s, w):
                bad.append(t["id"])
                continue
            if nf:  # B-1 / B-8 row 2: files by name and path suffix, reading tasks by their reads, other tasks by any work
                files = named_files(t["rest"], ctx.collected.workdir)
                steps = file_evidence_steps(ctx, files, w, reads=bool(READ_VERB.match(t["rest"]))) if files else work_steps(ctx, d)
                if not any(w[0] <= x <= s for x in steps):
                    bad.append(t["id"])
                continue
            named = named_paths(t["rest"], ctx.collected.workdir)
            if named and not any(w[0] <= x <= s for x in _evidence_steps(ctx, named, d)):
                bad.append(t["id"])
        return Result.ratio(item, len(pool) - len(bad), len(pool), f"ticked before (or without) the work it names: {bad[:5]}" if bad else f"{len(pool)} ticks after their work")
    if rule == "ticked_passing":
        text = _window_end_text(ctx, aid, w)
        if text is None:
            return Result.no(item, "tasks.md unknown at the end of the window")
        d = _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None
        changes = sorted(x for x in F.source_change_steps(ctx) if refs.in_window(x, w))  # source, not a byproduct of a run (.fits)
        results = timed_results(ctx, d)
        details = task_details(text)
        pool, bad, untested, left = 0, [], [], 0
        for g in _group_ends(ctx, aid, text, w, d):
            t = g["task"]
            if g["step"] is None or not t["checked"] or t["warned"]:
                continue
            # the results of the code as it was at the tick: after the last code change before it (anywhere in the window; a
            # run of the same call placed after its write counts), up to the tick
            last = max((c for c in changes if c < g["step"]), default=None)
            rs = [x for x in results if w[0] <= x[0] < g["step"] and (last is None or x[0] > last or (x[0] == last and x[2]))]
            if not rs:
                # a sub-task that says it runs the tests (implement-tasks.md 40), ticked with no result of the code it ticks
                if runs_tests(t["rest"], details.get(t["id"], []), wide=True):
                    pool += 1
                    untested.append(f"{t['id']} ticked at step {g['step']} with no test result since the code change of step {last}")
                continue
            pool += 1
            if rs[-1][1] == "fail":
                # A-5: a tick over a failure the documents do not ask to fix (R2: an existing test of the old behavior,
                # reported as such; a failure there without the change) is right; over any other failure it is not,
                # whatever the report says
                units = [(u, r) for r in _failing_results_at(ctx, d, rs[-1][0]) for u in R.failure_units(r)]
                if not units or excused_failures(ctx, units) != {u for u, _ in units}:
                    bad.append(f"{t['id']} ticked at step {g['step']} after the failing result of step {rs[-1][0]}")
                else:
                    left += 1
        if not pool:
            return Result.not_applicable(item, "no test result between a code change and a test sub-task's tick")
        bad = untested + bad
        why = f"{pool} test sub-task(s) ticked over a passing result" + (f" or ({left}) a failure the documents do not ask to fix" if left else "")
        return Result.ratio(item, pool - len(bad), pool, "; ".join(bad[:2]) if bad else why)
    if rule == "warned_after_attempts":
        d = _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None
        marks = warned_groups(ctx, aid, w, d)
        if not marks:
            return Result.not_applicable(item, "no test sub-task marked ⚠️ instead of ticked")
        bad = [g["task"]["id"] for g, ok in marks if not ok]
        return Result.ratio(item, len(marks) - len(bad), len(marks), f"marked ⚠️ without two failing results and a code or check-script change between them: {bad[:3]}" if bad else f"{len(marks)} mark(s) after two failed attempts")
    if rule == "later_edits":
        evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS]
        edits = [e for e in evs if refs.in_window(e.step, w) and e is not evs[0]]
        if not edits:
            return Result.ok(item, "tasks.md not edited in the window")
        # a write whose content the replay does not know is passed over: the next known content is compared with the
        # last known one before it, so a change the unknown write made shows there. Only unknown writes: as before, a fail.
        known = [e for e in edits if e.content is not None]
        if not known:
            return Result.ratio(item, 0, len(edits), "; ".join(f"step {e.step}: content unknown" for e in edits[:2]))
        good, bad = 0, []
        for e in known:
            prev, new = _known_before(evs, e), e.content
            if prev is None:
                bad.append(f"step {e.step}: content before it unknown")
                continue
            if _norm_box(prev) == _norm_box(new):
                good += 1
            elif p.get("additions") and _only_adds(_norm_box(prev), _norm_box(new)):
                extra = added_lines_ok(_norm_box(prev), _norm_box(new))  # B-8 row 13: only tasks are added, no notes
                if extra:
                    bad.append(f"step {e.step}: adds lines that are no task: {extra[:2]}")
                else:
                    good += 1
            else:
                bad.append(f"step {e.step}: {e.op} changes the tasks")
        return Result.ratio(item, good, len(known), "; ".join(bad[:2]) if bad else f"{good} write(s): ticks only" + (" or added tasks" if p.get("additions") else ""))
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# agentos_v2.checks
# --------------------------------------------------------------------------------------------
# a test function or class definition (create-tasks.md 127: "a new test function added to the existing repository test
# module that covers the changed code")
_TEST_DEF = re.compile(r"(?m)^\s*(?:async\s+)?def\s+(test\w*)\s*\(|^\s*class\s+(Test\w*)\b")


def test_names(text: str | None) -> set[str]:
    """The test functions and classes ``text`` defines."""
    return {a or b for a, b in _TEST_DEF.findall(text or "")}


def _action_of(ctx: EvalContext, step: int, index: int | None):
    for st in ctx.run.steps:
        if st.n == step:
            acts = st.actions
            if index is not None and 0 <= index < len(acts):
                return acts[index]
            return acts[0] if len(acts) == 1 else None
    return None


def added_test_functions(ctx: EvalContext, e) -> set[str]:
    """The test functions / classes a repository write ``e`` adds: named in the text its call put into the file and not in
    the text it replaced (an editor replace or insert, a created file, a shell command such as ``cat >> f <<EOF``). A
    write that changed or removed an existing line (``removed_existing``) adds none: the documents never change an
    existing test line."""
    if getattr(e, "removed_existing", None):
        return set()
    a = _action_of(ctx, int(e.step), getattr(e, "action_index", None))
    if a is None:
        return test_names(e.content) if e.op == "create" else set()
    if a.kind in ("replace", "insert", "create", "write"):
        return test_names(a.text) - test_names(a.old)
    if a.kind == "shell":
        return test_names(a.command)
    return set()


def module_tests(ctx: EvalContext, w=None) -> dict[str, tuple[int, set[str]]]:
    """Repository test modules that existed at BASE_SHA and to which a write in the window added a test function:
    repo-relative path -> (step of the first such write, the names added). The run's own tests besides its check scripts
    (create-tasks.md 127, core-workflow.md 85)."""
    out: dict[str, tuple[int, set[str]]] = {}
    for e in ctx.facts.repo_writes:
        if e.ok is False or (w is not None and not refs.in_window(e.step, w)) or not F.is_test_path(e.path) or F.is_new_path(ctx, e.path):
            continue
        names = added_test_functions(ctx, e)
        if not names:
            continue
        first, have = out.get(e.path, (int(e.step), set()))
        out[e.path] = (min(first, int(e.step)), have | names)
    return out


def _module_results(ctx: EvalContext, mods: dict[str, tuple[int, set[str]]], w) -> dict[str, list[tuple[int, str]]]:
    """Per module of :func:`module_tests`: (step, pass | fail) of the valid runs with the change in place that select it
    (its path, a directory or label above it, or the whole suite) after the first added function. A run fails it when it
    has failures and a failing test id names one of the added functions (or, the ids unknown, when it has failures)."""
    wd = ctx.collected.workdir
    out: dict[str, list[tuple[int, str]]] = {}
    for r in change_runs(ctx):
        if not refs.in_window(r.step, w):
            continue
        files = R.run_files(r, wd)
        whole = bool(_whole(r, wd, ctx))
        bad = r.failed + r.errors > 0
        ids = E.failing_ids(r.observation or "") if bad else []
        for m, (first, names) in mods.items():
            if r.step <= first or not (whole or any(R.selects(t, m) for t in files)):
                continue
            fails = bad and (not ids or any(n in i for i in ids for n in names))
            out.setdefault(m, []).append((int(r.step), "fail" if fails else "pass"))
    return out


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


def group_end_steps(ctx: EvalContext, aid: str = "tasks") -> list[int]:
    """The steps at which a task group of the final tasks.md has its last sub-task ticked or marked (the ticks
    :func:`tick_steps` can place; a group with none placed has no end). Shared with the penalty items (PHASE 2 stretches)."""
    if not ctx.facts.artifact_paths.get(aid):
        return []
    text = _text(ctx, aid)
    lines = task_lines(text)
    ticks = tick_steps(ctx, aid)
    ends = set()
    for g, _ in groups(text):
        steps = [ticks.get(t["id"]) for t in lines if t["group"] and t["group"]["heading"] == g["heading"] and not t["id"].endswith(".0")]
        steps = [x for x in steps if x is not None and x is not UNKNOWN]
        if steps:
            ends.add(max(steps))
    return sorted(ends)


def group_end_marks(ctx: EvalContext, aid: str = "tasks") -> dict[int, bool]:
    """For every step of :func:`group_end_steps`: whether a task group ending there carries ⚠️ on one of its task lines
    (in the final tasks.md) -- a test that the attempts did not get to pass, marked and left (agentos_bugfix's implement-tasks.md 40)."""
    if not ctx.facts.artifact_paths.get(aid):
        return {}
    text = _text(ctx, aid)
    lines = task_lines(text)
    ticks = tick_steps(ctx, aid)
    out: dict[int, bool] = {}
    for g, _ in groups(text):
        mine = [t for t in lines if t["group"] and t["group"]["heading"] == g["heading"]]
        steps = [ticks.get(t["id"]) for t in mine if not t["id"].endswith(".0")]
        steps = [x for x in steps if x is not None and x is not UNKNOWN]
        if steps:
            out[max(steps)] = out.get(max(steps), False) or any(t["warned"] for t in mine)
    return out


# what makes a script a test (D-6 row 21): it can come out failing -- an assertion, a raise, an exit status, a test
# framework, or a printed verdict; a script that only prints what it finds explores
_VERDICT = re.compile(r"\bassert\b|\braise\b|\bsys\.exit\(|\bexit\(\s*[1-9]|\bunittest\b|\bpytest\b|\bdef\s+test_|\b(?:PASS(?:ED)?|FAIL(?:ED|URE)?|OK)\b")


def has_verdict(ctx: EvalContext, script: str) -> bool:
    """The script's last known content has a verdict construct (:data:`_VERDICT`); a script whose content is not known counts."""
    text = next((e.content for e in reversed(_content_events(ctx, script)) if e.content is not None), None)
    return text is None or bool(_VERDICT.search(text))


def own_test_first_writes(ctx: EvalContext, d: str, w=None, modules: bool = True, verdict: bool = False) -> list[int]:
    """Steps at which the run first wrote one of its own tests: a check script under ``d`` (its first write; ``verdict``:
    one that has a verdict, :func:`has_verdict`), or (``modules``) a test function added in the window to an existing
    repository test module (as :func:`module_tests` finds them) -- each function is a test of its own, so every write
    that adds a name not added before counts, not only the module's first."""
    out = [min(e.step for e in _content_events(ctx, s_)) for s_ in check_scripts(ctx, d) if _content_events(ctx, s_) and (not verdict or has_verdict(ctx, s_))]
    if modules:
        mods = module_tests(ctx, w)
        seen: dict[str, set[str]] = {}
        for e in sorted(ctx.facts.repo_writes, key=lambda e: int(e.step)):
            if e.path not in mods or e.ok is False or (w is not None and not refs.in_window(e.step, w)):
                continue
            new = added_test_functions(ctx, e) - seen.setdefault(e.path, set())
            if new:
                seen[e.path] |= new
                out.append(int(e.step))
    return sorted(out)


@register("agentos_v2.checks", params={"rule": True, "window": False, "dir": True, "warned": False, "fix_round": False, "module_tests": False, "per_group": False, "verdict": False, "unrun": False}, availability=("trace",), common=False, choices={"rule": ("written", "pass_last")})
def checks(item: Item, ctx: EvalContext) -> Result:
    """rule: written | pass_last -- the check scripts under ``dir``: written in the window; each one run in the window last ran passing, after the window's last code change.

    ``module_tests``: a test function added to a repository test module that existed at BASE_SHA (:func:`module_tests`) is
    a test of the run's own as well: it counts as written, and its module's last run with the change in place
    (:func:`_module_results`) is judged like a script's last run."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    d = _expand_dir(ctx, str(p["dir"]))
    w = _window(item, ctx)
    if d is None:
        return Result.no(item, "no checks directory (spec folder unbound)")
    if w is None:
        return Result.no(item, "window empty")
    end = w[1] if w[1] is not None else ctx.facts.n_steps + 2
    mods = module_tests(ctx, w) if p.get("module_tests") else {}
    if rule == "written":
        got = [s for s in check_scripts(ctx, d) if any(refs.in_window(e.step, w) for e in _content_events(ctx, s)) and (not p.get("verdict") or has_verdict(ctx, s))] + sorted(mods)
        if not got:
            return Result.no(item, f"no script written under {d}/ in the window")
        if p.get("per_group"):  # D-6 row 12: every task group that changes code writes its tests first (create-tasks.md 126)
            late = _groups_coding_first(ctx, d, bool(p.get("module_tests")), bool(p.get("verdict")))
            if late:
                return Result.no(item, late)
        return Result.ok(item, f"{len(got)} written: {[posixpath.basename(s) for s in got][:3]}")
    scripts = check_scripts(ctx, d, upto=end - 1)
    runs = executions(ctx, set(scripts))
    runs = {s: [(st, o) for st, o in r if refs.in_window(st, w)] for s, r in runs.items()}
    runs.update(_module_results(ctx, mods, w))
    pool = [s for s in scripts if runs.get(s)] + [m for m in sorted(mods) if runs.get(m)]
    unrun: list[str] = []
    if p.get("unrun"):  # A-9 row 19: a test written in the window and never run is a test that did not pass
        ever = executions(ctx, set(scripts))
        gone = {s for s in scripts if [e.op for e in ctx.facts.writes.get(s, []) if e.ok is not False][-1:] in (["delete"], ["move_out"])}
        # a script moved or removed afterwards (``head ... > x_fixed.py && mv x_fixed.py x.py``) is not left unrun
        unrun = [s for s in scripts if s not in gone and not ever.get(s) and any(refs.in_window(e.step, w) for e in _content_events(ctx, s)) and has_verdict(ctx, s)]
        unrun += [m for m in sorted(mods) if not runs.get(m)]  # a module whose added tests no run selected afterwards
    if not pool and not unrun:
        return Result.no(item, f"no check script under {d}/ run in the window")
    changes = _change_steps(ctx, w, authored=bool(p.get("fix_round")))  # the documents' check of a failure against the unchanged code is a stash and a pop
    last_change = changes[-1] if changes else w[0]
    # the documents' way out of a test that cannot be made to pass: its sub-task is marked ⚠️ after the attempts (at least one)
    acks = [g["step"] for g, shown in warned_groups(ctx, "tasks", w, d) if shown] if p.get("warned") else []
    good, bad = 0, []
    for s in pool:
        rs = runs[s]
        ok = rs[-1][1] == "pass" and rs[-1][0] > last_change
        ok = ok or (rs[-1][1] == "fail" and any(m > st for st, o in rs if o == "fail" for m in acks))
        good += ok
        if not ok:
            bad.append(posixpath.basename(s))
    bad += [f"{posixpath.basename(s)} (never run)" for s in unrun]
    return Result.ratio(item, good, len(pool) + len(unrun), f"not passing after the last code change (step {last_change}): {bad[:3]}" if bad else f"{good} script(s) pass after step {last_change}")


# --------------------------------------------------------------------------------------------
# agentos_v2.verify / report (implement-tasks PHASE 3)
# --------------------------------------------------------------------------------------------
def _groups_coding_first(ctx: EvalContext, d: str, modules: bool, verdict: bool = False) -> str | None:
    """The first task-group stretch of implement-tasks -- from the previous group's end (the stage's start for the first)
    to this group's end, :func:`group_end_steps`; nothing after the last end -- that changes source and has no test of the
    run's own first written inside it before its first source change. None when every such stretch has, or when no group
    end can be placed (the stage-wide rule alone then)."""
    w = refs.window(ctx, "stage:implement_tasks")
    ends = group_end_steps(ctx)
    if w is None or not ends:
        return None
    edits = sorted({x for x in F.source_change_steps(ctx) if refs.in_window(x, w)})
    firsts = own_test_first_writes(ctx, d, w=w, modules=modules, verdict=verdict)
    a = w[0] - 1
    for b in ends:
        inside = [x for x in edits if a < x <= b]
        if inside and not any(a < f < inside[0] for f in firsts):
            return f"task group ending at step {b}: code changed at step {inside[0]} before a test of its own was written in its stretch ({a}, {b}]"
        a = b
    return None


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


def _phase3_edits(ctx: EvalContext) -> list:
    """Repository writes the agent authored after PHASE 3 began (git putting content back -- stash, checkout -- is none)."""
    start = phase3_start(ctx)
    if start is None:
        return []
    s = 1 if start is UNKNOWN else start
    keep = F.change_paths(ctx)
    # removing a file the run made that the final change does not keep is clean-up (core-workflow.md 88-89: nothing of the
    # workflow stays in the repository), no code change (F-3, 1-4 row 16)
    return [e for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and e.step > s and not F.is_generated(e.path)
            and not (e.op in ("delete", "move_out") and F.is_new_path(ctx, e.path) and e.path not in keep)]


def _phase3_runs(ctx: EvalContext, after_fix: bool = False) -> list:
    """Valid test runs of PHASE 3; ``after_fix``: only those after its last repository write (a fix round's re-run)."""
    w = phase3_window(ctx)
    runs = [r for r in change_runs(ctx) if refs.in_window(r.step, w)] if w else []
    late = _phase3_edits(ctx) if after_fix else []
    return [r for r in runs if r.step > max(e.step for e in late)] if late else runs


def fallback_window(ctx: EvalContext):
    """Where a run's verification stands when PHASE 3 cannot be placed (no write leaves every task ticked before the
    report: a box left open, or the report written first): from the step after the later of the last code change and the
    last write of tasks.md, both before the report's first write, to that write (the end of the run without a report).
    None without a code change. The run is held to what a run that ticked every task is held to: a test run after both."""
    b = refs.event(ctx, "first_write:final_verification") if "final_verification" in ctx.rubric.artifacts else None
    if b is None or b is UNKNOWN:
        b = ctx.facts.n_steps + 1
    changes = _change_steps(ctx, (1, b), authored=True)
    if not changes:
        return None
    path = ctx.facts.artifact_paths.get("tasks")
    ticks = [int(e.step) for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.step < b] if path else []
    a = max([changes[-1], *ticks]) + 1
    return (a, b) if a < b else None


def comparison_window(ctx: EvalContext, fallback: bool = False):
    """The stretch whose test runs the report and ``suite_run`` are compared with: PHASE 3 (:func:`phase3_window`), or with
    ``fallback`` and no PHASE 3, :func:`fallback_window`."""
    w = phase3_window(ctx)
    if w is None and fallback:
        return fallback_window(ctx)
    return w


def comparison_runs(ctx: EvalContext, after_fix: bool = False, fallback: bool = False) -> list:
    """The valid test runs (change in place) in :func:`comparison_window`; ``after_fix`` as :func:`_phase3_runs`. In the
    fallback window no code change comes after its start, so there is no fix round to skip."""
    if phase3_window(ctx) is not None or not fallback:
        return _phase3_runs(ctx, after_fix=after_fix)
    w = fallback_window(ctx)
    return [r for r in change_runs(ctx) if refs.in_window(r.step, w)] if w else []


def comparison_script_results(ctx: EvalContext, d: str | None, fallback: bool = False) -> dict[str, str]:
    """Check script (absolute path) -> the outcome (``pass`` / ``fail``) of its last readable run in
    :func:`comparison_window`: what a report about a verification that ran only the run's own scripts is checked against."""
    w = comparison_window(ctx, fallback)
    if not d or w is None:
        return {}
    last: dict[str, str] = {}
    for s_, rs in executions(ctx, set(check_scripts(ctx, d))).items():
        known = [o for st, o in rs if o in ("pass", "fail") and refs.in_window(st, w)]
        if known:
            last[s_] = known[-1]
    return last


def _whole(r, workdir: str | None, ctx: EvalContext | None = None) -> bool:
    """The run is of the whole suite, by the one rule the prohibition of it reads too (``evidence.full_suite``, the
    common ``prohibited_action`` ``full_suite``): a runner at the repository root that selects nothing. The run's
    command is split from the directory it started in (``ctx``: the tracked one; without it the repository root), so a
    ``cd`` of the command or of an earlier call counts: ``cd pkg && pytest`` runs one package. A target (``pytest
    tests/``) or a filter (``-k``) is a selection, as it is for the prohibition."""
    start = getattr(getattr(ctx, "facts", None), "_cwd_track", {}).get((getattr(r, "step", None), getattr(r, "action_index", None)))
    try:
        segs = shell.flat(shell.split(r.command or r.segment, start or workdir)[0])
    except Exception:  # noqa: BLE001
        return False
    want = (r.segment or "").strip()
    return any(E.full_suite(s, workdir) for s in segs if not want or (s.text or "").strip() == want)


@register("agentos_v2.verify", params={"rule": True, "fix_round": False, "dir": False, "phase3_fallback": False}, availability=("trace",), common=False, choices={"rule": ("code_frozen", "suite_run", "whole_suite", "phase2_run")})
def verify(item: Item, ctx: EvalContext) -> Result:
    """rule: code_frozen | suite_run | whole_suite | phase2_run -- PHASE 3 (from every task ticked to the report): no repository write after it begins; a valid test run in it; one of them the whole suite; a valid test run before it, after the last code change."""
    rule = str((item.check.params or {}).get("rule"))
    fix_round = bool((item.check.params or {}).get("fix_round"))  # the documents allow one return to PHASE 2 after a failing run
    start = phase3_start(ctx)
    if rule == "phase2_run":
        w = _window(item, ctx)
        if w is None:
            return Result.no(item, "window empty")
        end = start
        if end is None or end is UNKNOWN:  # the ticks cannot be placed: the run only has to precede the report
            end = refs.event(ctx, "first_write:final_verification") if "final_verification" in ctx.rubric.artifacts else None
        if end is None or end is UNKNOWN:
            end = w[1] if w[1] is not None else ctx.facts.n_steps + 2
        changes = [c for c in _change_steps(ctx, w, authored=True) if c < end]
        if not changes:
            return Result.not_applicable(item, "no code change before PHASE 3")
        # a run of the same call as the last change counts when the change comes first in the command (``sed -i ... && pytest``)
        runs = [r for r in change_runs(ctx) if (changes[-1] < r.step or (changes[-1] == r.step and r.after_write_same_call)) and r.step < end]
        if not runs:
            return Result.no(item, f"no valid test run between the code change of step {changes[-1]} and PHASE 3 (step {end})")
        # A-9 row 9: every task group that changes code is tested before the next group's code (implement-tasks.md 39-40:
        # each group's last sub-task runs the tests). The stretches are cut at the group ends (``group_end_steps``)
        ends = [e for e in group_end_steps(ctx) if e < end] + [end]
        coded, a = [], (w[0] - 1 if w[0] is not None else 0)
        for b in ends:
            inside = [c for c in changes if a < c <= b]
            if inside:
                coded.append((inside[0], inside[-1]))
            a = b
        if len(coded) <= 1:
            return Result.ok(item, f"{len(runs)} valid test run(s) after the code change of step {changes[-1]}, first at step {runs[0].step}")
        every = change_runs(ctx)
        good, bad = 0, []
        for i, (_, last) in enumerate(coded):
            until = coded[i + 1][0] if i + 1 < len(coded) else end
            if any((last < r.step or (last == r.step and r.after_write_same_call)) and r.step < until for r in every):
                good += 1
            else:
                bad.append(f"code changed at step {last}, next group's code at step {until} with no valid test run between")
        return Result.ratio(item, good, len(coded), "; ".join(bad[:2]) if bad else f"{len(coded)} task groups that change code, each tested before the next")
    if start is None:
        return Result.no(item, "PHASE 3 never began (tasks not all ticked, no report)")
    if rule == "code_frozen" and fix_round:
        if ctx.facts.unseen_repo_paths:
            return Result.no(item, "a repository change the trace does not show: its time is unknown")
        late = _phase3_edits(ctx)
        if not late:
            return Result.ok(item, "no repository write after PHASE 3 began")
        runs = _phase3_runs(ctx)
        failed_before = any(r.step < late[0].step and r.failed + r.errors > 0 for r in runs)
        rerun_after = any(r.step > late[-1].step for r in runs)
        p = item.check.params or {}
        w3 = phase3_window(ctx)
        if p.get("dir") and w3:  # a test the agent wrote is a check script: its failing run sends back as well
            scripts = [(st, o) for st, o in _script_results(ctx, _expand_dir(ctx, str(p["dir"]))) if refs.in_window(st, w3)]
            failed_before = failed_before or any(st < late[0].step and o == "fail" for st, o in scripts)
            rerun_after = rerun_after or any(st > late[-1].step for st, _ in scripts)
        if failed_before and rerun_after:
            # A-9 row 14: one return to PHASE 2 (implement-tasks.md 137 "Go back once only"): the PHASE 3 writes are one
            # batch, not split by a test result (a valid run with the change in place, or a check-script run)
            split = [r.step for r in runs if late[0].step < r.step < late[-1].step]
            d3 = _expand_dir(ctx, str(p["dir"])) if p.get("dir") else None
            if d3 and w3:
                split += [st for rs in executions(ctx, set(check_scripts(ctx, d3))).values() for st, _o in rs if refs.in_window(st, w3) and late[0].step < st < late[-1].step]
            if split:
                return Result.no(item, f"fix round in more than one batch: PHASE 3 writes at steps {late[0].step} and {late[-1].step}, a test result at step {min(split)} between them")
            return Result.ok(item, f"fix round: a failing run before step {late[0].step}, a run after step {late[-1].step}")
        return Result.no(item, f"step {late[0].step}: {late[0].op} {late[0].path} after PHASE 3 began, " + ("no failing test run before it" if not failed_before else "no test run after it"))
    if rule == "code_frozen":
        if ctx.facts.unseen_repo_paths:
            return Result.no(item, "a repository change the trace does not show: its time is unknown")
        s = 1 if start is UNKNOWN else start
        late = [e for e in ctx.facts.repo_writes if e.ok is not False and e.step > s and not F.is_generated(e.path)]
        return Result.no(item, f"step {late[0].step}: {late[0].op} {late[0].path} after PHASE 3 began (step {s})") if late else Result.ok(item, f"no repository write after step {s}")
    runs = comparison_runs(ctx, after_fix=fix_round, fallback=bool((item.check.params or {}).get("phase3_fallback")))
    if rule == "suite_run":
        return Result.ok(item, f"{len(runs)} valid test run(s) in PHASE 3, first at step {runs[0].step}") if runs else Result.no(item, "no valid test run between the last tick and the report")
    if rule == "whole_suite":
        wd = ctx.collected.workdir
        whole = [r for r in runs if _whole(r, wd, ctx)]
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


def _left_unfixed(ctx: EvalContext, results: list, scripts_dir: str = SCRIPTS_DIR) -> list:
    """The failure units of ``results`` (R1) the report has to list: each with its last failing result, unless a later
    passing result ran it again *after a fix* -- a repository write or a check-script write between the failure and the
    pass. A test that fails and then passes the same run again with nothing changed was not fixed: it failed (a flaky
    test), and the report lists it. Failures fixed and run passing again are not listed (implement-tasks.md 133: the
    failed tests of the verification). ``scripts_dir``: the folder of the check scripts (its last name is matched)."""
    own = "/" + posixpath.basename(scripts_dir.rstrip("/")) + "/"
    edits = sorted({int(e.step) for e in ctx.facts.repo_writes if e.ok is not False and e.op != "unknown" and not F.is_generated(e.path)}
                   | {int(e.step) for evs in ctx.facts.writes.values() for e in evs if e.ok is not False and e.op in F.WRITE_OPS and own in (e.path or "")})
    last: dict = {}
    for r in sorted(results, key=lambda x: (x.step, not x.passed)):
        if not r.passed:
            for u in R.failure_units(r):
                last[u] = r
    out = []
    for u, f in sorted(last.items(), key=lambda x: (x[0], x[1].step)):
        fixed = any(p_.step > f.step and R.clears(p_, u, f) and any(f.step < e <= p_.step for e in edits) for p_ in results)
        if not fixed:
            out.append((u, f))
    return out


def _report_on_scripts(item: Item, rule: str, text: str, suite: str, scripts: dict[str, str]) -> Result:
    """``test_counts`` / ``suite_status`` / ``failed_listed`` against the run's own check scripts' last outcomes, for a
    verification that ran no repository test: the Status and whether Failing + Errors is 0 agree with "every script
    passed" (Total and Passing are not checked: a script prints no standard count); every failing script is named."""
    failing = sorted(posixpath.basename(s_) for s_, o in scripts.items() if o == "fail")
    if rule == "suite_status":
        st = _status(text, suite)
        if re.search(r"(?i)all\s+passing", st):
            return Result.ok(item, "All Passing, every check script passed") if not failing else Result.no(item, f"All Passing, but check script(s) failed: {failing[:3]}")
        if re.search(r"(?i)some\s+failures|critical\s+failures", st):
            return Result.ok(item, f"{st[:30]}: check script(s) failed: {failing[:3]}") if failing else Result.no(item, f"{st[:30]}, but every check script passed")
        return Result.no(item, f"Status {st[:40]!r} is none of the three" if st else "no Test Suite Results Status")
    if rule == "test_counts":
        summ = M.section(text, "Test Summary") or M.section(text, suite, match="prefix") or text
        f_, e_ = _num(M.field_value(summ, "Failing")), _num(M.field_value(summ, "Errors"))
        if f_ is None and e_ is None:
            return Result.no(item, "no Failing / Errors counts")
        bad = (f_ or 0) + (e_ or 0)
        ok = (bad > 0) == bool(failing)
        return Result.ok(item, f"Failing + Errors {bad}, as the check scripts give") if ok else Result.no(item, f"Failing + Errors {bad}, but check script(s) failing: {failing[:3]}")
    if not failing:
        return Result.not_applicable(item, "no failing check script")
    good = [x for x in failing if x in text]
    return Result.ratio(item, len(good), len(failing), f"{len(good)}/{len(failing)} failing check scripts named")


@register(
    "agentos_v2.report",
    params={"rule": True, "artifact": False, "suite_section": False, "fix_round": False, "dir": False, "issues_listed": False, "phase3_fallback": False, "script_results": False, "open_tasks": False, "standing": False, "in_section": False, "scripts_dir": False},
    availability=("sandbox_file", "trace"),
    common=False,
    choices={"rule": ("test_counts", "failed_listed", "suite_status", "tasks_status", "incomplete_listed", "spec_name", "overall_status")},
)
def report(item: Item, ctx: EvalContext) -> Result:
    """rule: test_counts | failed_listed | suite_status | tasks_status | incomplete_listed | spec_name | overall_status -- final-verification.md against the PHASE 3 runs, tasks.md, the spec folder and itself."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    suite = str(p.get("suite_section") or "3. Test Suite Results")  # the report section of the test results, as numbered in the template
    text = _text(ctx, _artifact(item, "final_verification"))
    if text is None:
        return Result.no(item, "final-verification.md absent")
    if rule == "overall_status":
        head = M.clean_value(M.field_value(re.split(r"(?m)^##\s", text, maxsplit=1)[0], "Status") or "")
        tasks_st, suite_st = _status(text, "1. Tasks Verification"), _status(text, suite)
        if not head:
            return Result.no(item, "no Status at the top of the report")
        if re.search(r"(?i)critical\s+failures", suite_st) and re.search(r"(?i)issues\s+found", tasks_st):
            want = ("Failed", "Passed with Issues")  # both rules of the documents hold; they do not say which wins
        elif re.search(r"(?i)critical\s+failures", suite_st):
            want = "Failed"
        elif re.search(r"(?i)issues\s+found", tasks_st) or re.search(r"(?i)some\s+failures", suite_st):
            want = "Passed with Issues"
        elif re.search(r"(?i)all\s+complete", tasks_st) and re.search(r"(?i)all\s+passing", suite_st):
            want = "Passed"
        else:
            return Result.no(item, f"section Statuses {tasks_st[:30]!r} / {suite_st[:30]!r} give no overall Status")
        got = "Passed with Issues" if re.search(r"(?i)with\s+issues", head) else "Failed" if re.search(r"(?i)fail", head) else "Passed" if re.search(r"(?i)pass", head) else head[:30]
        return Result.ok(item, f"Status {got}, as the sections give") if got in ((want,) if isinstance(want, str) else want) else Result.no(item, f"Status {got!r}, but the sections give {want!r}")
    if rule in ("test_counts", "failed_listed", "suite_status"):
        fallback = bool(p.get("phase3_fallback"))
        runs = comparison_runs(ctx, after_fix=bool(p.get("fix_round")), fallback=fallback)  # after a fix round the report is about the re-run
        if not runs and p.get("script_results"):
            scripts = comparison_script_results(ctx, _expand_dir(ctx, str(p.get("scripts_dir") or SCRIPTS_DIR)), fallback)
            if scripts:
                return _report_on_scripts(item, rule, text, suite, scripts)
        if not runs:
            return Result.no(item, "no valid PHASE 3 test run to compare with")
        summ = M.section(text, "Test Summary") or M.section(text, suite, match="prefix") or text
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
            st = _status(text, suite)
            if not st:
                return Result.no(item, "no Test Suite Results Status")
            bad = best.failed + best.errors
            if re.search(r"(?i)all\s+passing", st):
                if bad:
                    return Result.no(item, f"All Passing, but step {best.step} has {bad} failures / errors")
                if p.get("standing"):  # A-2: no failure of the verification left standing -- a run that left the test out does not clear it
                    left = R.standing_units([runner_result(r, ctx.collected.workdir, ctx) for r in runs])
                    if left:
                        (kind, what), f = left[0]
                        return Result.no(item, f"All Passing, but {what} failed at step {f.step} and no later run ran it passing ({len(left)} left)")
                return Result.ok(item, "All Passing, no failure")
            if re.search(r"(?i)some\s+failures|critical\s+failures", st):
                if bad > 0:
                    return Result.ok(item, f"{st[:30]}: {bad} failures / errors")
                if p.get("dir") and re.search(r"(?i)critical\s+failures", st):  # the Status of a failing test the agent wrote
                    last: dict[str, str] = {}
                    d = _expand_dir(ctx, str(p["dir"]))
                    for s_, rs in executions(ctx, set(check_scripts(ctx, d)) if d else set()).items():
                        known = [o for _, o in rs if o in ("pass", "fail")]
                        if known:
                            last[s_] = known[-1]
                    failing = sorted(posixpath.basename(s_) for s_, o in last.items() if o == "fail")
                    if failing:
                        return Result.ok(item, f"{st[:30]}: check script(s) last ran failing: {failing[:3]}")
                return Result.no(item, f"{st[:30]}, but step {best.step} has no failure")
            return Result.no(item, f"Status {st[:40]!r} is none of the three")
        # A-8 (``in_section``): a failing test counts as named only inside the Failed Tests section (the Test Suite Results
        # section when the report has none), not in Notes or elsewhere
        hay = ((M.section(text, "Failed Tests", match="prefix") or M.section(text, suite, match="prefix") or "") if p.get("in_section") else text)
        if p.get("standing"):  # A-7 row 7: every failure left standing at the end of the verification, over all its runs
            left = _left_unfixed(ctx, [runner_result(r, ctx.collected.workdir, ctx) for r in runs], str(p.get("scripts_dir") or SCRIPTS_DIR))
            if not left:
                return Result.not_applicable(item, "no failure left standing in the PHASE 3 runs")
            want = [what for (kind, what), _ in left if kind == "test"]
            if not want:  # the outputs name no failed test: Failed Tests has to list something
                sec = M.section(text, "Failed Tests") or ""
                listed = [ln for ln in M.content_lines(sec) if ln.strip() and not M.is_none(ln.strip("-* "))]
                return Result.ok(item, "failures named in the report") if listed else Result.no(item, f"{left[0][0][1]} failed at step {left[0][1].step}, Failed Tests lists nothing")
            good = [i for i in want if any(form in hay for form in refs.id_forms(i))]
            return Result.ratio(item, len(good), len(want), f"{len(good)}/{len(want)} failing tests left standing named" + (" in Failed Tests" if p.get("in_section") else ""))
        fails = [r for r in runs if r.failed + r.errors > 0]
        if not fails:
            return Result.not_applicable(item, "no failing test in the PHASE 3 runs")
        r = max(fails, key=lambda x: x.step)
        ids = E.failing_ids(r.observation or "")
        if not ids:
            sec = M.section(text, "Failed Tests") or ""
            listed = [ln for ln in M.content_lines(sec) if ln.strip() and not M.is_none(ln.strip("-* "))]
            return Result.ok(item, "failures named in the report") if listed else Result.no(item, f"step {r.step} failed, Failed Tests lists nothing")
        good = [i for i in ids if any(form in hay for form in refs.id_forms(i))]
        return Result.ratio(item, len(good), len(ids), f"{len(good)}/{len(ids)} failing tests named")
    if rule in ("tasks_status", "incomplete_listed"):
        ts = task_lines(_text(ctx, "tasks"))
        if not ts:
            return Result.no(item, "tasks.md absent or without task lines")
        open_ = [t["id"] for t in ts if not t["checked"] or t["warned"]]
        if p.get("open_tasks"):  # B-5 addition: as incomplete_listed, a line without a checkbox is no task left open
            open_ = [t["id"] for t in ts if t["warned"] or (not t["checked"] and t["box"] is not None)]
        if rule == "tasks_status":
            st = _status(text, "1. Tasks Verification")
            if re.search(r"(?i)all\s+complete", st):
                return Result.ok(item, "All Complete, every task ticked") if not open_ else Result.no(item, f"All Complete, but open / marked: {open_[:4]}")
            if re.search(r"(?i)issues\s+found", st):
                if open_:
                    return Result.ok(item, "Issues Found")
                if p.get("issues_listed"):  # the template's Incomplete or Issues lists tasks that "have issues" too
                    sec = M.section(text, "Incomplete or Issues")
                    if [ln for ln in M.content_lines(sec or "") if ln.strip() and not M.is_none(ln.strip("-* \"'"))]:
                        return Result.ok(item, "Issues Found, with issues listed")
                return Result.no(item, "Issues Found, but every task is ticked")
            return Result.no(item, f"Status {st[:40]!r} is neither All Complete nor Issues Found")
        warned = [t["id"] for t in ts if t["warned"]]
        if p.get("open_tasks"):  # a task left open is as incomplete as one marked ⚠️ (implement-tasks.md 127); a line
            # without a checkbox ("- 0.009125 formats as ...") has nothing to tick and is not left open
            warned = [t["id"] for t in ts if t["warned"] or (not t["checked"] and t["box"] is not None)]
        if not warned:
            return Result.not_applicable(item, "no task marked ⚠️")
        sec = M.section(text, "Incomplete or Issues")
        lines = [ln for ln in M.content_lines(sec or "") if ln.strip() and not M.is_none(ln.strip("-* \"'"))]
        return Result.ok(item, f"{len(lines)} line(s) listed") if lines else Result.no(item, f"tasks open or marked ⚠️ {warned[:3]}, but Incomplete or Issues lists none")
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
@register("agentos_v2.created_files", params={"pattern": False, "test_paths": False, "window": False, "scratch": False}, availability=("trace",), common=False)
def created_files(item: Item, ctx: EvalContext) -> Result:
    """No file the run created in the repository (absent at BASE_SHA) is a test file (``test_paths``) or matches ``pattern``, written in the window.
    ``scratch``: besides ``pattern``, a created file that is one of the run's own scripts (``facts.is_run_script``) or that
    the run's own last write removed (made and removed again: ``rm``, ``mv`` away) counts too."""
    p = item.check.params or {}
    w = _window(item, ctx)
    if w is None:
        return Result.ok(item, "window empty")
    rx = re.compile(str(p["pattern"])) if p.get("pattern") else None
    removed: dict[str, bool] = {}  # path -> the run's own last write removed it (made and removed again)
    for e in ctx.facts.repo_writes:
        if e.ok is not False:
            removed[e.path] = e.op in ("delete", "move_out")
    hits = []
    for e in ctx.facts.repo_writes:
        if e.ok is False or not refs.in_window(e.step, w) or not F.is_new_path(ctx, e.path):
            continue
        if p.get("test_paths") is not None and F.is_test_path(e.path) != bool(p["test_paths"]):
            continue
        scratch = bool(p.get("scratch")) and not F.is_generated(e.path) and (F.is_run_script(ctx, e.path) or removed.get(e.path, False))
        if rx is not None and not rx.search(e.path) and not scratch:
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
    "found_not_done",
    "phase3_window",
    "outcome",
    "executions",
]
