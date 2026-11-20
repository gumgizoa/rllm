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
FAIL_TEXT = re.compile(
    r"Traceback \(most recent call last\)|\bAssertionError\b|^\s*(?:FAIL|FAILED|ERROR)\b|\b[1-9]\d* (?:failed|errors?)\b|\bFAILED \(|"
    r"^\s*E\s{2,}\S|\b(?:Error|Exception):\s|\bcommand not found\b|\bNo such file or directory\b|\bcan't open file\b",
    re.M,
)
# A verdict line a script prints about itself: read against an exit code of 0 only when the output is the script's alone.
VERDICT_TEXT = re.compile(r"^\s*(?:FAIL|FAILED)\b|\b[1-9]\d* failed\b|\bFAILED \(", re.M)
# What python prints at start-up when the environment holds a broken .pth file: the environment's, not the script's.
PTH_NOISE = re.compile(r"Error processing line \d+ of [^\n]*\.pth:\n.*?Remainder of file ignored\n?", re.S)
PASS_TEXT = re.compile(r"\b\d+ passed\b|^\s*OK\b|\bPASS(?:ED)?\b|\ball (?:checks|tests) pass(?:ed)?\b|\bpassed\b", re.M | re.I)
MARK_WORDS = re.compile(r"(?i)\b(?:fail\w*|error\w*|pass\w*|ok|traceback|assert\w*)\b")
WHOLE = "*"  # the key of a runner run that names no file

_NARROW_OPT = re.compile(r"^(?:-k|-m|--deselect|--ignore|--ignore-glob)(?:=(?P<v>.*))?$")


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


def executed_by(seg: shell.Segment) -> set[str]:
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


def own_exit_known(segs: list[shell.Segment], i: int, code: int | None) -> bool:
    """The call's exit code ``code`` is segment ``i``'s own: ``i`` is the command's last segment, or the call ended with
    0 and every list operator after ``i`` is ``&&`` (had ``i`` failed, nothing after it would have run and the call
    could not end with 0). A segment that feeds a pipe, or is followed by ``;`` / ``||`` / a new line, has no known
    code of its own."""
    if code is None:
        return False
    if i == len(segs) - 1:
        return True
    if code != 0 or segs[i + 1].op_before == "|":
        return False
    return all(s.op_before in ("&&", "|") for s in segs[i + 1 :])


def runs_something(seg: shell.Segment) -> bool:
    """The segment invokes a test runner or executes a script."""
    try:
        return E.classify(seg) is not None or any(F._executed(seg))
    except Exception:  # noqa: BLE001 -- agent text
        return False


def outcome(segs: list[shell.Segment], i: int, observation: str, command: str = "") -> str | None:
    """``pass`` / ``fail`` / None (cannot tell) for segment ``i``'s run, by its call's own output.

    When the call's exit code is the segment's own (:func:`own_exit_known`) it decides: not 0 is a failure, 0 a pass --
    unless the output is the segment's alone (no other runner or script in the call, no other segment that could print
    such words) and holds a verdict line (``FAIL...`` / ``N failed`` / ``FAILED (``). Otherwise the output's words are
    read: failure text when no other segment could have printed such words, pass text when there is no failure text.
    The start-up errors python prints for a broken ``.pth`` file in the environment are not read."""
    obs = E.clean_observation(observation or "", command)
    body = PTH_NOISE.sub("", EXIT.sub("", obs))[-MAX_TEXT:]
    code = exit_code(obs)
    foreign = others_print(segs, i, MARK_WORDS)
    if own_exit_known(segs, i, code):
        if code != 0:
            return "fail"
        alone = not foreign and not any(runs_something(s) for j, s in enumerate(segs) if j != i)
        return "fail" if alone and VERDICT_TEXT.search(body) else "pass"
    failed_text = bool(FAIL_TEXT.search(body)) and not foreign
    if failed_text:
        return "fail"
    if not foreign and PASS_TEXT.search(body) and not FAIL_TEXT.search(body):
        return "pass"
    return None


def executions(ctx: EvalContext, paths: set[str]) -> dict[str, list[tuple[int, str | None]]]:
    """Absolute path -> [(step, outcome)] of every run of it, in order (the final call's observation is empty: None)."""
    out: dict[str, list[tuple[int, str | None]]] = {p: [] for p in paths}
    if not paths:
        return out
    for c in ctx.facts.commands:
        segs = segments(ctx, c)
        for i, seg in enumerate(segs):
            hit = executed_by(seg) & paths
            if not hit:
                continue
            res = outcome(segs, i, c.observation or "", c.command or "") if c.step < ctx.facts.n_steps else None
            for p in sorted(hit):
                out[p].append((c.step, res))
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


def selection(segment: str) -> tuple[str, ...]:
    """What narrows a test run below its target files: ``-k``/``-m``/``--deselect``/``--ignore`` with their values,
    and ``file::test`` ids. Empty for a run of whole files or directories."""
    try:
        toks = shlex.split(segment or "")
    except ValueError:
        toks = (segment or "").split()
    sel, i = [], 0
    while i < len(toks):
        t = toks[i]
        m = _NARROW_OPT.match(t)
        if m and t == "-m" and i and re.search(r"(?:^|/)python[\d.]*$", toks[i - 1]):  # `python -m pytest`: the module, not a marker
            m = None
        if m:
            v = m.group("v")
            if v is None and i + 1 < len(toks):
                i += 1
                v = toks[i]
            sel.append(f"{t.split('=')[0]} {v}")
        elif "::" in t:
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
    it (``utils_tests``), with or without the leading directories of the path."""
    t = target.split("::")[0].rstrip("/")
    if not t:
        return False
    if "/" in t or t.endswith(".py"):
        return t == file or file.startswith(t + "/")
    stem = file[:-3] if file.endswith(".py") else file
    parts = t.split(".")
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
]
