"""The evaluation verifier's own evidence readers, where the vendored rubric's misjudge real runs.

``rubric/`` stays byte-identical to the offline scorer it was vendored from; what the evaluation
verifier reads differently is here, and ``compliance.py``, ``_claims.py``, ``content_checks.py`` and
``evaluator.py`` call it. Each fix was measured on swebv100 (Qwen3.5-9B, aidlc_v4, SWE-bench Verified
100; ``tasks/2026-10-21-aidlc-v4-eval-verifier/EVIDENCE.md`` in the local task record):

    test runs        one runner list for every check -- the rubric's plus Django's ``runtests.py`` /
                     ``manage.py test`` (270 commands the stage gate missed, 19 runs capped at 4/7) --
                     and neither a lookup that names a runner (``cat tox.ini``, ``grep .. runtests.py``:
                     117 of 652 attempts) nor a runner script the agent wrote itself (``bash /tmp/pytest.sh``)
    script runs      a script is run by an interpreter, a test runner, ``./path`` or ``/abs/path`` at the
                     start of a command segment, or a ``python -c`` import -- not by ``ls -la path``
                     (250 of 447 reproduction-script "runs")
    exit codes       the last ``exit code N`` of a command, unless a pipe without ``pipefail`` made it the
                     exit code of the pipe's last command (``python repro.py | tail``)
    final changes    what the run changed is the patch (``git diff`` against the start, collected before
                     the verifier), not the trajectory's writes (22 of 96 runs disagree)
    test files       the task's ``test_patch`` files as well as the path pattern (which misses pytest's
                     ``testing/`` and ``sphinx/testing/``)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .rubric import facts as F

# Django's runner and nose / ward, which the rubric's TEST_RUN_PATTERNS do not know.
EXTRA_RUNNERS = re.compile(r"\bruntests\.py\b|\bmanage\.py\s+test\b|\bnosetests?\b|\bward\b")
# A command segment led by a verb that reads or lists a file, not one that runs it.
LOOKUP = re.compile(
    r"^\s*(?:sudo\s+)?(?:grep|egrep|fgrep|rg|cat|head|tail|sed|awk|less|more|ls|find|wc|echo|printf|test|\[|stat|file|which|type|whereis|nl|diff|cmp|realpath|readlink|du|tree|pip3?\s+show|git\s+(?:log|show|diff|status|grep|blame))\b"
)
_SEGMENT = re.compile(r"\s*(?:&&|\|\||;|\n)\s*")
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")
_EXIT = re.compile(r"exit code[:\s]+(\d+)")
_CD = re.compile(r"^\s*cd\s+\S+\s*$")
_ENV = re.compile(r"^(?:\w+=\S*\s+)+")
_SCRIPT_ARG = re.compile(r"^(?:bash|sh|zsh|python[0-9.]*|\./|/)\s*(\S+)")


def segments(command: str) -> list[str]:
    """The command's executable parts: heredoc bodies and quoted strings blanked (``F.command_skeleton``),
    split on ``&&`` / ``||`` / ``;`` / newlines, with leading ``cd dir`` segments and ``VAR=value``
    prefixes dropped. A pipe stays inside its segment: ``a | b`` runs ``a``."""
    out = []
    for seg in _SEGMENT.split(F.command_skeleton(command or "")):
        seg = _ENV.sub("", seg.strip())
        if seg and not _CD.match(seg):
            out.append(seg)
    return out


def is_lookup(segment: str) -> bool:
    """A segment that reads or lists rather than runs: its first command (before any pipe) is a lookup verb."""
    return bool(LOOKUP.match(_PIPE.split(segment, maxsplit=1)[0]))


def _runner_in(segment: str) -> bool:
    head = _PIPE.split(segment, maxsplit=1)[0]
    return F.matches_any(head, F.TEST_RUN_PATTERNS) or EXTRA_RUNNERS.search(head) is not None


def _agent_script(segment: str, agent_files) -> bool:
    """The segment's program is a file the agent wrote itself (``bash /tmp/pytest.sh``)."""
    m = _SCRIPT_ARG.match(_PIPE.split(segment, maxsplit=1)[0].strip())
    if not m:
        return False
    target = m.group(1) if not m.group(0).startswith(("./", "/")) else m.group(0).split()[0]
    name = target.rsplit("/", 1)[-1]
    return bool(name) and any(str(p).rsplit("/", 1)[-1] == name for p in agent_files)


def is_test_attempt(command: str, agent_files=()) -> bool:
    """A shell command that invokes a test runner: some segment runs one, is not a lookup, and is not a
    script the agent wrote (``agent_files``: paths the run created before this command)."""
    return any(_runner_in(s) and not is_lookup(s) and not _agent_script(s, agent_files) for s in segments(command))


def runs_script(command: str, path: str) -> bool:
    """``command`` executes the script at ``path``: an interpreter or test runner with it as an argument,
    ``./path`` / ``/abs/path`` as the program, or ``python -c`` importing it as a module."""
    name = (path or "").strip().rsplit("/", 1)[-1]
    if not name:
        return False
    base, module = re.escape(name), re.escape(name.rsplit(".", 1)[0])
    interp = re.compile(rf"^(?:{F.RUNNER}|pytest|py\.test|python[0-9.]*\s+-m\s+pytest|timeout\s+\d+\s+{F.RUNNER})\s+(?:-\S+\s+)*\S*{base}(?:\s|$|::)")
    direct = re.compile(rf"^\.?/\S*{base}(?:\s|$)")
    for seg in (s for s in segments(command) if not is_lookup(s)):
        head = _PIPE.split(seg, maxsplit=1)[0].strip()
        if interp.search(head) or direct.search(head):
            return True
    return bool(re.search(rf"\bpython[0-9.]*\s+-c\s+\S*(?:import\s+{module}\b|from\s+{module}\s+import)", command or ""))


def exit_code(command: str, output: str) -> int | None:
    """The command's exit code as the terminal reported it, or None when a pipe without ``pipefail``
    makes the reported code the pipe's last command's, or none was reported."""
    if any(_PIPE.search(s) for s in segments(command)) and "pipefail" not in (command or ""):
        return None
    codes = _EXIT.findall(output or "")
    return int(codes[-1]) if codes else None


def ran_real_test(run) -> bool:
    """Any test-runner invocation in the run that did not fail to start (the rubric's ``ran_something``)."""
    agent_files: set[str] = set()
    for step in run.steps:
        for a in step.actions:
            if a.kind == "shell" and is_test_attempt(a.command or "", agent_files) and F.ran_something(a):
                return True
            agent_files.update(t for t in (F.write_targets(a) if a.kind == "shell" else [a.path or ""] if a.kind == "create" else []) if t)
    return False


# --- final changes ----------------------------------------------------------------------------


def patch_files(patch: str | None) -> tuple[list[str], list[str]] | None:
    """(changed, added) repository paths of the run's patch, or None when the patch is unknown."""
    if patch is None:
        return None
    return F.diff_files(patch)


def task_test_files(task) -> set[str]:
    """Paths the task's ``test_patch`` touches (``<task dir>/tests/config.json``), empty when unknown."""
    task_dir = getattr(task, "task_dir", None)
    if task_dir is None:
        meta = getattr(task, "metadata", None) or {}
        task_dir = meta.get("task_path") if isinstance(meta, dict) else None
    if not task_dir:
        return set()
    try:
        cfg = json.loads((Path(task_dir) / "tests" / "config.json").read_text())
    except (OSError, ValueError, TypeError):
        return set()
    return set(re.findall(r"^diff --git a/(\S+)", cfg.get("test_patch") or "", re.M))


def is_test_file(path: str, test_files=()) -> bool:
    return F.TEST_PATH_RE.search(path) is not None or path in test_files
