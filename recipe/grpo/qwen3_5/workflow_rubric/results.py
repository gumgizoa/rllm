"""Test results a run can be judged by, read the same way for every workflow.

Two things live here, both asked of the facts and never of the sandbox:

* the outcome of running a script the agent wrote (:func:`outcome`, :func:`executions`): ``pass`` / ``fail`` by the
  call's own output, or None when the trace does not say. A run whose outcome cannot be read was run -- it is no
  passing result;
* whether a test that failed passed again (:func:`standing_failures`): a failure stands until a later passing
  result runs the same test -- the same file, a directory or dotted label above it, or the whole suite
  (:func:`reruns`) -- and is not narrower than the run that failed (:func:`selection`: ``-k``, ``-m``,
  ``--deselect``, ``--ignore``, a ``file::test`` id the failing run did not use).

What counts as a result, and over which stretch of the run they are read, is each workflow's business: it builds
the :class:`TestResult` list and asks here what is left failing.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass
from typing import Any

from . import evidence as E
from . import facts as F
from . import refs
from .context import EvalContext
from .trace import shell

MAX_CMD = 20_000
MAX_TEXT = 400_000
EXIT = re.compile(r"\[(?:The command completed with exit code|Command finished with exit code)\s+(-?\d+)\.?\]")
# a script's own lower-case verdict (``check_x failed``, ``❌ ... failed``): not ``0 failed``, ``no ... failed``, ``if failed``
_FAILED_WORD = r"(?<![\w-])(?<!\b0 )(?<!\bno )(?<!\bnot )(?<!\bif )(?<!\bno tests )(?<!\bnothing )failed\b(?![-_(])(?!\s*[:=]\s*0\b)"
FAIL_TEXT = re.compile(
    r"Traceback \(most recent call last\)|\bAssertionError\b|^\s*(?:FAIL|FAILED|ERROR)\b|\b[1-9]\d* (?:failed|errors?)\b|\bFAILED \(|"
    r"^\s*E\s{2,}\S|\b(?:Error|Exception):\s|\bcommand not found\b|\bNo such file or directory\b|\bcan't open file\b|❌|" + _FAILED_WORD,
    re.M,
)
# A verdict line a script prints about itself: read against an exit code of 0 only when the output is the script's alone.
VERDICT_TEXT = re.compile(r"^\s*(?:FAIL|FAILED)\b|\b[1-9]\d* failed\b|\bFAILED \(|❌|" + _FAILED_WORD, re.M)
# What python prints at start-up when the environment holds a broken .pth file: the environment's, not the script's.
PTH_NOISE = re.compile(r"Error processing line \d+ of [^\n]*\.pth:\n.*?Remainder of file ignored\n?", re.S)
# A line a logger or python's warnings print (``WARNING: ...``, ``x.py:3: UserWarning: ...``): no verdict of the script's.
WARNING_LINE = re.compile(r"^[ \t]*(?:\[?WARNING\]?\b|[^\n]*\b\w*Warning:)[^\n]*$", re.M)
PASS_TEXT = re.compile(r"\b\d+ passed\b|^\s*OK\b|\bPASS(?:ED)?\b|\ball (?:checks|tests) pass(?:ed)?\b|\bpassed\b|✅", re.M | re.I)
MARK_WORDS = re.compile(r"(?i)\b(?:fail\w*|error\w*|pass\w*|ok|traceback|assert\w*)\b|[✅❌]")
WHOLE = "*"  # the key of a runner run that names no file

_NARROW_OPT = re.compile(r"^(?:-k|-m|--deselect|--ignore|--ignore-glob)(?:=(?P<v>.*))?$")
_NARROW_ATTACHED = re.compile(r"^-(?P<o>[km])(?P<v>[^=-].*)$")  # `-kfoo`, `-mslow`: the value written onto the option
_INTERPRETER = re.compile(r"(?:^|/)(?:python|pypy)[\d.]*$")
_GIT_OPTS = r"(?:(?:-[Cc]|--git-dir|--work-tree)\s+\S+\s+|--[\w-]+(?:=\S+)?\s+)*"  # `git -C /testbed stash`


def _module_flag(toks: list[str], i: int) -> bool:
    """``toks[i]`` (``-m`` or ``-mNAME``) is the interpreter's module option, not a marker filter: it follows the
    interpreter, with nothing but interpreter options between them (``python -u -W ignore -m pytest``)."""
    j = i - 1
    while j >= 0 and (toks[j].startswith("-") or (j > 0 and toks[j - 1] in ("-W", "-X"))):
        j -= 1
    return j >= 0 and _INTERPRETER.search(toks[j]) is not None


# --------------------------------------------------------------------------------------------
# The outcome of a script run
# --------------------------------------------------------------------------------------------
def segments(ctx: EvalContext, c) -> list[shell.Segment]:
    """The command of ``c`` (a ``CommandFact``) as flat shell segments; empty when it cannot be parsed."""
    key = ("results.segments", c.step, c.action_index)
    if key not in ctx.cache:
        try:
            ctx.cache[key] = shell.flat(shell.split((c.command or "")[:MAX_CMD], c.cwd)[0])
        except Exception:  # noqa: BLE001 -- agent text: an unparsable command runs nothing we can attribute
            ctx.cache[key] = []
    return ctx.cache[key]


def label_files(label: str, bases: list[str]) -> set[str]:
    """The files a dotted runner label can name, read against each base directory: ``a.b.C.test_x`` from ``tests/`` is
    ``tests/a/b/C/test_x.py``, ``tests/a/b/C.py``, ``tests/a/b.py`` or ``tests/a.py`` (Django's ``runtests.py``,
    ``manage.py test``, unittest)."""
    parts = [x for x in label.split(".") if x]
    return {posixpath.normpath(posixpath.join(b, *parts[:k]) + ".py") for b in bases if b for k in range(len(parts), 0, -1)}


_PY_IMPORT = re.compile(r"(?:^|[;\n(]|\s)(?:import[ \t]+([A-Za-z_]\w*)\b|from[ \t]+([A-Za-z_]\w*)[ \t]+import\b)")
_PY_PATH_RUN = re.compile(r"""\bexec\s*\(\s*open\s*\(\s*(['"])([^'"\n]+)\1|\brunpy\.run_path\s*\(\s*(['"])([^'"\n]+)\3|spec_from_file_location\s*\([^,()]*,\s*(['"])([^'"\n]+)\5""")
_SYS_PATH = re.compile(r"""sys\.path\.(?:insert\s*\(\s*-?\d+\s*,|append\s*\()\s*(['"])([^'"\n]+)\1""")


def inline_runs(seg: shell.Segment) -> set[str]:
    """Absolute paths of the scripts a ``python -c`` / ``python - <<EOF`` segment runs by importing them
    (``import repro``, ``from repro import main``: the module beside the directory it starts in or one it puts on
    ``sys.path``) or by executing their file (``exec(open('x.py').read())``, ``runpy.run_path('x.py')``). A file name in
    the code's text is no run (a code that writes the script runs nothing of it)."""
    words = seg.cmd_words
    if not words or not seg.verb or not _INTERPRETER.search(seg.verb) or seg.cwd is None:
        return set()
    mode, val, _ = E.py_args(words[1:])
    code = val if mode == "code" else (seg.stdin_text if mode == "stdin" else None)
    if not code:
        return set()
    code = code[:MAX_CMD]
    dirs = [seg.cwd] + [shell.resolve(m.group(2), seg.cwd) for m in _SYS_PATH.finditer(code)]
    out = {posixpath.normpath(posixpath.join(d, (m.group(1) or m.group(2)) + ".py")) for m in _PY_IMPORT.finditer(code) for d in dirs}
    out |= {posixpath.normpath(shell.resolve(m.group(2) or m.group(4) or m.group(6), seg.cwd)) for m in _PY_PATH_RUN.finditer(code)}
    return out


def executed_by(seg: shell.Segment) -> set[str]:
    """Absolute paths the segment executes: a script it runs (``python x.py``, ``bash x.sh``, ``./x``), one a
    ``python -c`` imports or executes (:func:`inline_runs`), or a runner target -- a file, or the files a dotted label
    names (:func:`label_files`: ``runtests.py repro_issue`` from ``tests/`` runs ``tests/repro_issue.py``)."""
    out: set[str] = set()
    try:
        out |= {posixpath.normpath(p) for p in F._executed(seg) if p}
        hit = E.classify(seg)
        if hit is not None:
            out |= {posixpath.normpath(shell.resolve(t, seg.cwd)) for t in hit.targets if t}
            for label, bases in hit.labels:
                out |= label_files(label, bases)
        out |= inline_runs(seg)
    except Exception:  # noqa: BLE001 -- agent text
        pass
    return out


def _direct(seg: shell.Segment) -> set[str]:
    """Paths the segment executes itself (an interpreter's script, ``./x``, a ``python -c`` import), not as a runner's
    target."""
    try:
        return {posixpath.normpath(p) for p in F._executed(seg) if p} | inline_runs(seg)
    except Exception:  # noqa: BLE001 -- agent text
        return set()


_NOT_FOUND = re.compile(r"can't open file|No such file or directory|ERROR: file or directory not found|ERROR: not found:", re.I)


def started(segs: list[shell.Segment], i: int, observation: str, path: str, command: str = "") -> bool:
    """Segment ``i``'s run of ``path`` started: not a file that was not there (``can't open file``, ``No such file or
    directory``, pytest's ``file or directory not found`` naming it), and for a runner given it as a target or label,
    not a runner that died before it loaded the file (no result summary, and the output never names the file:
    ``runtests.py tests/x.py`` stopping in ``build_suite``). A run that did not start has no result."""
    obs = E.clean_observation(observation or "", command)[-MAX_TEXT:]
    base = posixpath.basename(path)
    if any(_NOT_FOUND.search(ln) and base in ln for ln in obs.splitlines()):
        return False
    if path in _direct(segs[i]):
        return True
    stem = posixpath.splitext(base)[0]
    try:
        found = E.summaries(obs)
    except Exception:  # noqa: BLE001 -- agent text
        found = []
    return bool(found) or base in obs or re.search(r"(?<![\w])" + re.escape(stem) + r"(?![\w])", obs) is not None


def _file_outcomes(obs: str, path: str) -> list[str]:
    """pytest's per-test outcomes of the tests in ``path`` (``x.py::test_a PASSED``), by the node ids' file part."""
    out = []
    for nid, res in E.pytest_outcomes(obs).items():
        f = nid.split("::", 1)[0]
        if f and (path == f or path.endswith("/" + f.lstrip("./"))):
            out.append(res)
    return out


def others_print(segs: list[shell.Segment], i: int, rx: re.Pattern) -> bool:
    """Could a segment other than ``i`` have printed text ``rx`` matches (its literal words, heredoc, stdin)?"""
    for j, s in enumerate(segs):
        if j == i:
            continue
        blob = " ".join(s.argv or []) + "\n" + (s.heredoc or "") + "\n" + (s.stdin_text or "")
        if rx.search(blob[:MAX_CMD]):
            return True
    return False


def exit_code(observation: str) -> int | None:
    m = EXIT.findall((observation or "")[-2000:])
    try:
        return int(m[-1]) if m else None
    except ValueError:
        return None


_SHOW_VERBS = frozenset({"cat", "echo", "printf", "head", "tail", "ls", "true", "wc", "sed", "grep"})


def own_exit_known(segs: list[shell.Segment], i: int, code: int | None, shown: bool = True) -> bool:
    """The call's exit code ``code`` is segment ``i``'s own: ``i`` is the command's last segment, or the call ended with
    0 and every list operator after ``i`` is ``&&`` (had ``i`` failed, nothing after it would have run and the call
    could not end with 0). A segment that feeds a pipe, or is followed by ``;`` / ``||`` / a new line, has no known
    code of its own (``|| true`` hides it). A code other than 0 is ``i``'s when only ``&&`` follows it, its output went
    to a file and what follows only shows text that nothing shows (``shown`` False): ``python x.py > out.txt && cat
    out.txt`` ending with 1 and printing nothing never reached the ``cat``."""
    if code is None:
        return False
    if i == len(segs) - 1:
        return True
    if segs[i + 1].op_before == "|":
        return False
    if code != 0:
        return (
            not shown
            and any(o in (">", ">>", "&>", "&>>") for o, _ in segs[i].redirects)
            and all(s.op_before == "&&" and s.verb in _SHOW_VERBS for s in segs[i + 1 :])
        )
    return all(s.op_before in ("&&", "|") for s in segs[i + 1 :])


def runs_something(seg: shell.Segment) -> bool:
    """The segment invokes a test runner or executes a script."""
    try:
        return E.classify(seg) is not None or any(F._executed(seg))
    except Exception:  # noqa: BLE001 -- agent text
        return False


def outcome(segs: list[shell.Segment], i: int, observation: str, command: str = "", path: str | None = None) -> str | None:
    """``pass`` / ``fail`` / None (cannot tell) for segment ``i``'s run (of ``path``, when given), by its call's own
    output. A run that did not start (:func:`started`) is no run at all; the callers leave it out.

    A runner given the script as one target of several (``pytest a.py repro.py``) is read by that file's own test lines;
    a runner given only it, by its result summary (``FAILED (errors=1)``, ``1 passed``). A run that had not finished
    when the output stopped (``no new output after 30 seconds``) failed when a failure verdict was already printed, and
    cannot be told otherwise (a pass line so far is no pass).

    When the call's exit code is the segment's own (:func:`own_exit_known`) it decides: not 0 is a failure, 0 a pass --
    unless the output is the segment's alone (no other runner or script in the call, no other segment that could print
    such words) and holds a verdict line (``FAIL...`` / ``N failed`` / ``FAILED (``): a failure line wins over a pass
    line the same script prints. Otherwise the output's words are read: failure text when no other segment could have
    printed such words, pass text when there is no failure text. The start-up errors python prints for a broken
    ``.pth`` file in the environment are not read."""
    obs = E.clean_observation(observation or "", command)
    body = PTH_NOISE.sub("", EXIT.sub("", obs))[-MAX_TEXT:]
    code = exit_code(obs)
    foreign = others_print(segs, i, MARK_WORDS)
    if path is not None and path not in _direct(segs[i]):
        lines = _file_outcomes(body, path)
        if lines:
            return "fail" if any(x in ("FAILED", "ERROR") for x in lines) else ("pass" if "PASSED" in lines else None)
        hit = E.classify(segs[i])
        named = {posixpath.normpath(shell.resolve(t, segs[i].cwd)) for t in (hit.targets if hit else []) if t}
        if hit is not None and named <= {path} and len(hit.labels) <= 1:
            found = E.summaries(body)
            if found:
                failed = sum(x.failed + x.errors for x in found)
                return "fail" if failed else ("pass" if sum(x.passed for x in found) else None)
        if hit is not None and (len(named | {path}) > 1 or len(hit.labels) > 1):
            return None  # other targets' results are no result of this file
    said = WARNING_LINE.sub("", body)  # a logged warning (``IERSWarning: failed to download``) is no verdict
    if E._STILL_RUNNING.search(observation or ""):
        return "fail" if not foreign and (VERDICT_TEXT.search(said) or FAIL_TEXT.search(said)) else None
    if own_exit_known(segs, i, code, shown=bool(body.strip())):
        if code != 0:
            return "fail"
        alone = not foreign and not any(runs_something(s) for j, s in enumerate(segs) if j != i)
        return "fail" if alone and VERDICT_TEXT.search(said) else "pass"
    failed_text = bool(FAIL_TEXT.search(said)) and not foreign
    if failed_text:
        return "fail"
    if not foreign and PASS_TEXT.search(body) and not FAIL_TEXT.search(said):
        return "pass"
    return None


# --------------------------------------------------------------------------------------------
# Runs with the change stashed away
# --------------------------------------------------------------------------------------------
_STASH = re.compile(r"\bgit\s+" + _GIT_OPTS + r"stash\b(?:[ \t]+(?:-\S+[ \t]+)*([a-z]+)\b)?")
_STASH_BACK = frozenset({"pop", "apply"})
_STASH_NOTHING = frozenset({"list", "show", "drop", "clear", "branch", "create", "store"})


_CHECKOUT = re.compile(r"\bgit\s+" + _GIT_OPTS + r"(checkout|restore)\b([^;&|\n]*)")
_BRANCHING = frozenset({"-b", "-B", "--orphan", "--detach", "-"})


def _checkout_moves(sub: str, args: str, paths: set[str]) -> bool:
    """``git checkout [<rev>] [--] <paths>`` / ``git restore [--source=<rev>] <paths>`` that names a path of ``paths``
    (or ``.``): it puts the working copy of a changed file back to an older version. A branch switch moves nothing here."""
    words = [w.strip("'\"") for w in args.split()]
    if any(w in _BRANCHING for w in words):
        return False
    if sub == "restore" and any(w in ("--staged", "-S") for w in words) and not any(w in ("--worktree", "-W") for w in words):
        return False  # unstages only: the working copy keeps the change
    if "--" in words:
        words = words[words.index("--") + 1 :]
    targets = [w for w in words if w and not w.startswith("-")]
    for t in targets:
        t = t[2:] if t.startswith("./") else t
        t = t.rstrip("/")
        if t in (".", "") or any(q == t or q.endswith("/" + t) or t.endswith("/" + q) or q.startswith(t + "/") for q in paths):
            return True
    return False


# a patch applied in reverse puts the change away (aidlc's reading, now every workflow's: 통일-검토.md R3); applied
# forwards again it is back. ``git apply --check`` / ``--stat`` / ``--numstat`` / ``--summary`` change nothing.
_APPLY = re.compile(r"(?:\bgit\s+" + _GIT_OPTS + r"apply\b|(?<![\w./-])patch\b)([^;&|\n]*)")
_REVERSE = re.compile(r"(?:^|\s)(?:-R|--reverse|-[A-Za-z]*R[A-Za-z]*)(?=\s|$)")
_APPLY_NOTHING = re.compile(r"(?:^|\s)(?:--check|--stat|--numstat|--summary|--dry-run)(?=\s|$)")


def stash_marks(command: str, checkout_paths: set[str] | None = None) -> list[tuple[int, bool]]:
    """(position, stashed away after it) for every command that moves the change: ``git stash`` push forms put it
    away, ``pop`` / ``apply`` bring it back (``list`` / ``show`` / ``drop`` and the like move nothing); ``git apply -R``
    / ``patch -R`` put it away and the same applied forwards brings it back. With ``checkout_paths`` (the repository
    files other than tests the run edited itself), a ``git checkout`` / ``git restore`` of one of them puts the change
    away too (implement-tasks.md 135 names ``git stash`` as an example of running a test without the change)."""
    out = []
    for m in _STASH.finditer(command or ""):
        sub = m.group(1)
        if sub in _STASH_NOTHING:
            continue
        out.append((m.start(), sub not in _STASH_BACK))
    for m in _APPLY.finditer(command or ""):
        args = m.group(1) or ""
        if command[: m.start()].rstrip().endswith(("which", "command -v", "type")) or _APPLY_NOTHING.search(args):
            continue
        if m.group(0).lstrip().startswith("patch") and not re.search(r"(?:^|\s)(?:-p\d|-i|<|-R|--reverse|-[A-Za-z]*R)", args):
            continue  # ``patch`` with nothing of a patch run (a word in prose, ``patch.object``) moves nothing
        out.append((m.start(), bool(_REVERSE.search(args))))
    if checkout_paths:
        out += [(m.start(), True) for m in _CHECKOUT.finditer(command or "") if _checkout_moves(m.group(1), m.group(2), checkout_paths)]
    out.sort()
    return out


def stash_states(commands: list, edit_steps: tuple[int, ...] | list[int] = (), checkout_paths: set[str] | None = None) -> tuple[dict, dict]:
    """Per command ``(step, action_index)``: whether the change is stashed away when it starts, and its marks.

    The change stays away until a ``pop`` / ``apply`` -- or until the run edits the repository again (``edit_steps``):
    a stash that is never popped has thrown the change away, and what the run writes next is a new change, not the
    old code. A ``git stash`` that found nothing to save stashed nothing."""
    before, marks, away, since = {}, {}, False, 0
    edits = sorted(edit_steps)
    for c in sorted(commands, key=lambda c: (c.step, c.action_index)):
        key = (int(c.step), c.action_index)
        if away and any(since < w <= key[0] for w in edits):
            away = False
        ms = stash_marks(c.command, checkout_paths)
        if "No local changes to save" in (getattr(c, "observation", "") or ""):
            ms = [m for m in ms if not m[1]]
        before[key], marks[key] = away, ms
        if ms:
            away = ms[-1][1]
            since = key[0]
    return before, marks


def run_stashed(r: Any, before: dict, marks: dict) -> bool:
    """The runner run ``r`` runs with the change stashed away."""
    key = (int(r.step), r.action_index)
    ms = marks.get(key) or []
    state = before.get(key, False)
    if not ms:
        return state
    at = (r.command or "").find(r.segment) if r.segment else -1
    if at < 0:  # cannot place the run in its command: a command that stashes runs it stashed
        return state or any(on for _, on in ms)
    for pos, on in ms:
        if pos < at:
            state = on
    return state


def executions(ctx: EvalContext, paths: set[str]) -> dict[str, list[tuple[int, str | None]]]:
    """Absolute path -> [(step, outcome)] of every run of it, in order (the final call's observation is empty: None)."""
    out: dict[str, list[tuple[int, str | None]]] = {p: [] for p in paths}
    if not paths:
        return out
    for c in ctx.facts.commands:
        segs = segments(ctx, c)
        for i, seg in enumerate(segs):
            hit = executed_by(seg) & paths
            for p in sorted(hit):
                if c.step < ctx.facts.n_steps and not started(segs, i, c.observation or "", p, c.command or ""):
                    continue
                out[p].append((c.step, outcome(segs, i, c.observation or "", c.command or "", p) if c.step < ctx.facts.n_steps else None))
    return out


# --------------------------------------------------------------------------------------------
# A failed test that passes again
# --------------------------------------------------------------------------------------------
@dataclass
class TestResult:
    """One readable test result."""

    __test__ = False  # not a pytest class

    step: int
    passed: bool
    runner: bool  # a valid runner run; else a script of the run's own
    keys: tuple[str, ...]  # the script's path, or the test files the runner run names (``WHOLE`` when none)
    selection: tuple[str, ...] = ()  # what narrows a runner run below its files (:func:`selection`)
    failed_ids: tuple[str, ...] = ()  # a failing valid runner run: the ids of its failed tests, when its output names them all (:func:`run_failed_ids`)


# options whose value is no test selection (``-W ignore::DeprecationWarning``, ``-p no:cacheprovider``, ``-o k=v``): the
# runner's value-taking options and the interpreter's ``-W`` / ``-X``, the selecting ones (above) and ``-c`` (inline code) aside
_VALUE_OPTS = (E._PYTEST_ARG | {"-W", "-X"}) - {"-k", "-m", "--deselect", "--ignore", "--ignore-glob", "-c"}


def selection(segment: str) -> tuple[str, ...]:
    """What narrows a test run below its target files: ``-k``/``-m``/``--deselect``/``--ignore`` with their values,
    and ``file::test`` ids. Empty for a run of whole files or directories. The value of another option
    (``-W ignore::DeprecationWarning``) selects nothing."""
    try:
        toks = shlex.split(segment or "")
    except ValueError:
        toks = (segment or "").split()
    sel, i = [], 0
    while i < len(toks):
        t = toks[i]
        m = _NARROW_OPT.match(t)
        attached = _NARROW_ATTACHED.match(t) if m is None else None
        if (m and t == "-m" or attached and attached.group("o") == "m") and _module_flag(toks, i):  # `python -m pytest`: the module, not a marker
            m = attached = None
        if attached:
            sel.append(f"-{attached.group('o')} {attached.group('v')}")
        elif m:
            v = m.group("v")
            if v is None and i + 1 < len(toks):
                i += 1
                v = toks[i]
            sel.append(f"{t.split('=')[0]} {v}")
        elif t in _VALUE_OPTS:
            i += 1  # its value
        elif "::" in t and not t.startswith("-"):
            sel.append(t)
        i += 1
    return tuple(sorted(sel))


def run_files(run: Any, workdir: str | None) -> tuple[str, ...]:
    """The repository-relative test files (or directories, or dotted labels) a runner run names, a ``file::test``
    id counted as its file; empty for a run that names none."""
    pre = (workdir.rstrip("/") + "/") if workdir else None
    rel = [refs.norm_path(t, workdir) for t in (run.targets or [])]
    rel = [t[len(pre) :] if pre and t.startswith(pre) else t for t in rel]
    return tuple(sorted({t.split("::")[0] for t in rel if t.split("::")[0]}))


def selects(target: str, file: str) -> bool:
    """A runner target selects repository test file ``file``: the file or a test in it, a directory above it, or a
    dotted label of it -- its module (``utils_tests.test_duration``), a class or test in the module, or a package above
    it (``utils_tests``), with or without the leading directories of the path. A label that starts at the path's first
    directory follows the path from there: ``tests.annotations.tests`` names ``tests/annotations/tests.py`` and no other
    app's ``tests.py``, although its first component is the file name of every one of them."""
    t = target.split("::")[0].rstrip("/")
    if not t:
        return False
    if "/" in t or t.endswith(".py"):
        return t == file or file.startswith(t + "/")
    stem = file[:-3] if file.endswith(".py") else file
    parts = t.split(".")
    dirs = stem.split("/")
    if len(dirs) > 1 and parts[0] == dirs[0]:
        n = min(len(parts), len(dirs))
        return parts[:n] == dirs[:n]
    for n in range(len(parts), 0, -1):
        c = "/".join(parts[:n])
        if stem == c or stem.endswith("/" + c):
            return True
        if n == len(parts) and ("/" + c + "/") in ("/" + stem):  # a package label: every module under it
            return True
    return False


def _parts(target: str) -> tuple[list[str], bool]:
    """A runner target as path components, and whether it was written as a path (else a dotted label)."""
    t = target.rstrip("/")
    if "/" in t or t.endswith(".py"):
        return (t[:-3] if t.endswith(".py") else t).split("/"), True
    return t.split("."), False


def reruns(later: str, key: str) -> bool:
    """A runner run that names ``later`` runs what an earlier run named ``key``: the same target, a directory above
    it, or a dotted label above it (``queries`` over ``queries.test_q``). A path and a dotted label name the same test
    when one lines up with the other once the label's missing leading directories are allowed for
    (``tests/queries/test_q.py`` and ``queries.test_q``)."""
    if later == WHOLE or later == key:
        return True
    if key == WHOLE:
        return False
    (lp, l_path), (kp, k_path) = _parts(later), _parts(key)
    if l_path == k_path:
        return kp[: len(lp)] == lp
    if any(kp[: len(lp) - i] == lp[i:] for i in range(len(lp))):  # an end of ``later`` begins ``key``
        return True
    return any(kp[j : j + len(lp)] == lp for j in range(len(kp) - len(lp) + 1))  # ``later`` inside ``key``


def runs_key(result: TestResult, key: str) -> bool:
    """``result`` ran what ``key`` names: the very key, or -- a runner run over a repository test -- a target above it.
    A script (an absolute path) is rerun only by running that script."""
    if key in result.keys:
        return True
    if not result.runner or key == WHOLE or key.startswith("/"):
        return False
    return any(reruns(k, key) for k in result.keys)


def standing_failures(results: list[TestResult], until: int | None = None) -> list[str]:
    """The keys that failed and have not passed again, as things stand after the results at or before ``until``.

    A failure is cleared by a later passing result that runs the same key (:func:`runs_key`) and is not narrower than
    the run that failed: it selects nothing below its files, or the very selection that failed. At one step a
    failing result is read last, so a call that both passes and fails a key leaves it failed."""
    failed: dict[str, tuple[str, ...]] = {}
    for r in sorted((r for r in results if until is None or r.step <= until), key=lambda x: (x.step, not x.passed)):
        if not r.passed:
            for k in r.keys:
                failed[k] = r.selection
            continue
        for k in [k for k, sel in failed.items() if runs_key(r, k) and (not r.selection or r.selection == sel)]:
            del failed[k]
    return sorted(failed)


# --------------------------------------------------------------------------------------------
# Failure units: what a failing result leaves to pass again, test by test where the output says
# --------------------------------------------------------------------------------------------
def _same_file(a: str, b: str) -> bool:
    """Two test paths name the same file: equal, or one is the tail of the other (``tests/x.py``, ``/testbed/tests/x.py``)."""
    a, b = a.lstrip("./"), b.lstrip("./")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def _under(tid: str, sel: str) -> bool:
    """Test ``tid`` is ``sel`` or below it: the same file (a path tail) and, when ``sel`` names a test, the same test or
    one of its parametrisations or methods (``sel::``, ``sel[``)."""
    tf, _, tr = tid.partition("::")
    sf, _, sr = sel.partition("::")
    if not _same_file(tf, sf):
        return False
    return not sr or tr == sr or tr.startswith(sr + "::") or tr.startswith(sr + "[")


def run_failed_ids(failed: int, errors: int, observation: str) -> tuple[str, ...]:
    """The ids of the tests a failing valid runner run failed, when its output names at least as many as it counts
    (``failed + errors``); else empty (the run is judged by its files). A bare name from a pytest failure section's
    header (``test_x[png]``, ``Class.test_x``) is the same test as a full id with that name at its end and is dropped."""
    n = failed + errors
    if n <= 0:
        return ()
    ids = E.failing_ids(observation or "")
    full = [i for i in ids if "::" in i]
    out = []
    for i in ids:
        if "::" not in i:
            tail = i.replace(".", "::")
            if any(f.endswith("::" + tail) or f.endswith("::" + i) for f in full) or any(o != i and o.endswith("." + i) for o in ids if "::" not in o):
                continue
        out.append(i)
    return tuple(out) if len(out) >= n else ()


def failure_units(result: TestResult) -> list[tuple[str, str]]:
    """What a failing result leaves to pass again: ``("test", id)`` for every failed test of a valid runner run whose
    output names them all (:attr:`TestResult.failed_ids`); else ``("key", k)`` for every file it names (``WHOLE`` when
    none), and for a script, its path."""
    if result.passed:
        return []
    if result.runner and result.failed_ids:
        return [("test", i) for i in result.failed_ids]
    return [("key", k) for k in result.keys]


_K_WORD = re.compile(r"\s*(\(|\)|and\b|or\b|not\b|[^\s()]+)")


def _k_matches(expr: str, tid: str) -> bool | None:
    """pytest's ``-k expr`` on test ``tid``: every word stands for "the word is in the id" (case ignored), joined by
    ``and`` / ``or`` / ``not`` and brackets. None when the expression cannot be read."""
    toks, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = _K_WORD.match(expr, pos)
        if not m or not m.group(1):
            return None
        pos = m.end()
        w = m.group(1)
        if w in ("(", ")", "and", "or", "not"):
            toks.append(w)
        elif re.fullmatch(r"[\w.\[\]-]+", w):
            toks.append("True" if w.lower() in tid.lower() else "False")
        else:
            return None
    if not toks:
        return None
    try:
        return bool(eval(" ".join(toks), {"__builtins__": {}}, {}))  # noqa: S307 -- only True / False / and / or / not / brackets
    except Exception:  # noqa: BLE001
        return None


def runs_test(result: TestResult, test_id: str) -> bool:
    """The valid runner run ``result`` ran test ``test_id``: its targets cover the test (the same file, a directory or
    dotted label above it, the whole suite) and nothing it selects leaves the test out -- a ``file::test`` id it names is
    the test or above it; ``-k`` holds for it; ``--deselect`` / ``--ignore`` do not name it or its file; ``-m`` (marks
    cannot be read) and a ``-k`` that cannot be read leave it out."""
    if not result.runner:
        return False
    file_part = test_id.split("::")[0]
    if not any(k == WHOLE or reruns(k, file_part) or reruns(k, test_id) for k in result.keys):
        return False
    ids = [s for s in result.selection if not s.startswith("-")]
    if ids and not any(_under(test_id, s) for s in ids):
        return False
    for s in result.selection:
        if not s.startswith("-"):
            continue
        opt, _, val = s.partition(" ")
        if opt == "-m":
            return False
        if opt == "-k":
            if not _k_matches(val, test_id):
                return False
        elif opt == "--deselect":
            if _under(test_id, val):
                return False
        elif opt in ("--ignore", "--ignore-glob"):
            v = val.rstrip("/").lstrip("./")
            f = file_part.lstrip("./")
            if v and (f == v or f.startswith(v + "/") or ("/" + f).endswith("/" + v) or ("/" + v + "/") in ("/" + f) or posixpath.basename(f) == v):
                return False
    return True


def clears(passing: TestResult, unit: tuple[str, str], failing: TestResult) -> bool:
    """The passing result ``passing`` makes failure unit ``unit`` (left by ``failing``) pass again: a test unit, when it
    is a valid runner run that ran the test (:func:`runs_test`); a file or script unit, by :func:`standing_failures`' rule
    -- it runs that key and is not narrower than the run that failed."""
    if not passing.passed:
        return False
    kind, what = unit
    if kind == "test":
        return runs_test(passing, what)
    return runs_key(passing, what) and (not passing.selection or passing.selection == failing.selection)


def standing_units(results: list[TestResult], until: int | None = None) -> list[tuple[tuple[str, str], TestResult]]:
    """The failure units left failing after the results at or before ``until``, each with the last result that failed
    it. Results are read in step order, a failing one last within a step; a unit stands until a later passing result
    :func:`clears` every failing run of it (a file that failed whole and then narrowed needs a pass that is not narrower
    than the whole failure)."""
    failed: dict[tuple[str, str], list[TestResult]] = {}
    for r in sorted((r for r in results if until is None or r.step <= until), key=lambda x: (x.step, not x.passed)):
        if not r.passed:
            for u in failure_units(r):
                failed.setdefault(u, []).append(r)
            continue
        for u in list(failed):
            left = [f for f in failed[u] if not clears(r, u, f)]
            if left:
                failed[u] = left
            else:
                del failed[u]
    return sorted(((u, fs[-1]) for u, fs in failed.items()), key=lambda x: (x[0], x[1].step))


__all__ = [
    "EXIT",
    "FAIL_TEXT",
    "PASS_TEXT",
    "VERDICT_TEXT",
    "PTH_NOISE",
    "MARK_WORDS",
    "WHOLE",
    "TestResult",
    "segments",
    "executed_by",
    "others_print",
    "exit_code",
    "own_exit_known",
    "runs_something",
    "outcome",
    "executions",
    "selection",
    "run_files",
    "selects",
    "reruns",
    "runs_key",
    "standing_failures",
    "run_failed_ids",
    "failure_units",
    "runs_test",
    "clears",
    "standing_units",
    "stash_marks",
    "stash_states",
    "run_stashed",
]
