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
    stage bands      an artifact that is the skeleton verbatim, or has nothing under its frontmatter but
                     headings, earns band 0 (the rubric gives it 2 of 8, so copying the five skeletons scored
                     0.45); real content under renamed headings keeps 2; ``Assumptions: none`` fills its
                     section when no ambiguity needed resolving
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .rubric import artifacts as A
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


_TEST_TARGET = re.compile(r"(\S+\.py)(?:::\S*)?$")
_RUNNER_PROGRAMS = {"runtests.py", "manage.py", "setup.py"}


def _only_agent_tests(segment: str, agent_files) -> bool:
    """Every test file the runner is pointed at is one the agent wrote (``pytest /tmp/dummy_tests/test_x.py``):
    its own tests, not the repository's covering ones."""
    head = _PIPE.split(segment, maxsplit=1)[0]
    targets = [m.group(1) for t in head.split() if (m := _TEST_TARGET.match(t)) and m.group(1).rsplit("/", 1)[-1] not in _RUNNER_PROGRAMS]
    names = {str(p).rsplit("/", 1)[-1] for p in agent_files}
    return bool(targets) and all(t.rsplit("/", 1)[-1] in names for t in targets)


# Asking a runner about itself runs no test.
_NO_RUN_FLAGS = re.compile(r"\s(?:--help|-h|--collect-only|--co|--version|--fixtures|--markers)(?:\s|$)")
# The runner script or a test module could not be found: nothing ran (beyond the rubric's TOOL_MISSING_RE).
_NOT_STARTED = re.compile(r"can't open file|No such file or directory: '[^']*(?:runtests|manage)\.py'|ERROR: file or directory not found|ERROR: not found:", re.I)


def started(a) -> bool:
    """A test attempt that ran tests: not one the rubric sees failing to start (``ran_something``), not one
    whose runner or target was missing, and not a ``--help`` / ``--collect-only`` query."""
    return F.ran_something(a) and not _NOT_STARTED.search(a.observation or "") and not any(_NO_RUN_FLAGS.search(s) for s in segments(a.command or ""))


def is_test_attempt(command: str, agent_files=()) -> bool:
    """A shell command that invokes a test runner on the repository's tests: some segment runs one, is not
    a lookup, is not a runner script the agent wrote, and is not pointed only at test files the agent wrote
    (``agent_files``: paths the run created before this command)."""
    return any(_runner_in(s) and not is_lookup(s) and not _agent_script(s, agent_files) and not _only_agent_tests(s, agent_files) for s in segments(command))


def command_has_tokens(command: str, tokens) -> bool:
    """Every token of a recorded command (test paths, node ids, labels) appears in ``command``, reading a
    path written from the repository root against the directory the command ``cd``'d into first:
    ``tests/runtests.py`` is in ``cd tests && python runtests.py``."""
    if not tokens:
        return False
    cwd = ""
    for seg in _SEGMENT.split(command or ""):
        m = re.match(r"^\s*cd\s+(\S+)\s*$", seg)
        if m:
            cwd = m.group(1).rstrip("/").removeprefix("/testbed").lstrip("/")

    def found(t: str) -> bool:
        t = t.removeprefix("/testbed/")
        return t in command or bool(cwd) and t.startswith(cwd + "/") and t[len(cwd) + 1 :] in command

    return all(found(t) for t in tokens)


INSTALL = re.compile(
    r"^(?:sudo\s+)?(?:(?:pip3?|python[0-9.]*\s+-m\s+pip|uv\s+pip|conda|mamba|micromamba|gem|cargo)\s+install|(?:apt|apt-get|yum|dnf|apk)\s+(?:install|add)|(?:npm|pnpm)\s+(?:install|i|add)|yarn\s+add|python[0-9.]*\s+setup\.py\s+(?:install|develop))\b"
)


def is_env_setup(command: str) -> bool:
    """The command installs a dependency or sets up the environment (01 / 05: the environment can already
    build and test the project)."""
    return any(INSTALL.match(s) for s in segments(command))


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


def agent_written(a) -> list[str]:
    """Files this action brought into being: an editor ``create`` that succeeded (the editor refuses an
    existing file), or a shell write outside the repository. A shell write inside it may be an existing
    file rewritten (``cat > tests/test_x.py``), so it is not counted as the agent's own."""
    if a.kind == "create":
        return [a.path] if a.path and a.status != "fail" else []
    if a.kind == "shell" and a.status != "fail":
        return [t for t in F.write_targets(a) if F.OUTSIDE_REPO_RE.match(t) and not t.startswith("/dev/")]
    return []


def ran_real_test(run) -> bool:
    """Any test-runner invocation in the run that did not fail to start (the rubric's ``ran_something``)."""
    agent_files: set[str] = set()
    for step in run.steps:
        for a in step.actions:
            agent_files.update(agent_written(a))
            if a.kind == "shell" and is_test_attempt(a.command or "", agent_files) and started(a):
                return True
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


_TEST_NAME = re.compile(r"(?:^|/)(?:test_[^/]*|[^/]*_test\.\w+|tests?\.py|conftest\.py)$")
_TESTS_DIR = re.compile(r"(?:^|/)(?:tests|__tests__|testing)/")


def is_test_file(path: str, test_files=()) -> bool:
    """A test file: one the task's test_patch touches, a test-named file (``test_x.py``, ``x_test.py``,
    ``tests.py``, ``conftest.py``), or a file under a ``tests/`` / ``testing/`` directory. Not the
    rubric's pattern, which also takes a library's own ``test`` package (``django/test/utils.py``) for
    tests (TRACE X14)."""
    return path in test_files or bool(_TEST_NAME.search(path)) or bool(_TESTS_DIR.search(path))


_FLAGS_WITH_VALUE = {"-k", "-m", "--settings", "--parallel", "-p", "--tb", "--verbosity", "-v", "--timeout", "-n", "-c", "--rootdir", "-o"}


def test_targets(command: str) -> list[str] | None:
    """The targets a test command names -- paths, node ids, dotted module or label names, a ``-k``
    expression -- or None when it runs no test runner. ``[]``: a runner with no target (the full suite)."""
    for seg in segments(command or ""):
        head = _PIPE.split(seg, maxsplit=1)[0].strip()
        if not _runner_in(head) or is_lookup(head):
            continue
        toks = head.split()
        # Django's runner, unittest and nose take bare labels (``runtests.py middleware_exceptions``); pytest's
        # bare word may be a whole-suite directory, so only paths and node ids count there.
        labels = re.search(r"runtests\.py|manage\.py\s+test|-m\s+django\s+test|\bunittest\b|\bnosetests?\b", head) is not None
        out, skip = [], False
        for i, t in enumerate(toks):
            if skip:
                skip = False
                if toks[i - 1] == "-k":
                    out.append(f"-k {t}")
                continue
            if t in _FLAGS_WITH_VALUE:
                skip = True
                continue
            if t.startswith("-") or "=" in t:
                continue
            name = t.rsplit("/", 1)[-1]
            if name in _RUNNER_PROGRAMS or re.fullmatch(r"python[0-9.]*|pytest|py\.test|unittest|django|test|manage\.py|nosetests?|tox|timeout|\d+", name):
                continue
            if "/" in t or "." in t or "::" in t or (labels and re.fullmatch(r"[\w.]+", t)):
                out.append(t.removeprefix("/testbed/"))
        return out
    return None


# --- stage bands ------------------------------------------------------------------------------

_DOCS = Path(__file__).resolve().parents[1] / "docs" / "rule-details"


def _content_lines(text: str) -> list[str]:
    body, _ = A.strip_fence(text or "")
    body = A.FRONTMATTER.sub("", body, count=1)
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def skeleton(stage: int) -> str:
    """The artifact skeleton stage ``stage``'s rule document prescribes (its fenced markdown block)."""
    text = next(_DOCS.glob(f"0{stage}-*.md")).read_text()
    return text.split("```markdown\n", 1)[1].split("```", 1)[0]


def is_template_copy(stage: int, text: str) -> bool:
    """Every line under the headings is a line of the skeleton: nothing was filled in."""
    lines = _content_lines(text)
    return bool(lines) and set(lines) <= set(_content_lines(skeleton(stage)))


def stage_band(stage: int, text: str) -> int:
    """The rubric's 8/5/2 band for one artifact (all graded fields / one missing / more), except that an
    artifact with nothing of its own -- the skeleton verbatim, or nothing under its frontmatter but
    headings -- earns 0, and ``Assumptions: none`` counts as filled. An artifact with real content under
    renamed headings keeps the rubric's 2 (the skeleton was not kept, but the stage was worked)."""
    parsed = A.parse(stage, text)
    missing = list(A.grade(stage, parsed)["missing"])
    if stage == 2 and "assumptions" in missing:
        body = parsed["section_bodies"].get("Assumptions")
        if body is not None and A._section_has_content(body, True):
            missing.remove("assumptions")
    if not _content_lines(text) or is_template_copy(stage, text):
        return 0
    return 8 if not missing else 5 if len(missing) == 1 else 2
