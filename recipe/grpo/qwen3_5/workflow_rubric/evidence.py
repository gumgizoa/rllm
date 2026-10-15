"""Test and build runs in a trace, and what each one's own output proves.

The AI-DLC reward counted a "test run" when the command *mentioned* a runner (``cat tox.ini``,
``echo pytest`` and ``pip install pytest`` all qualified) and missed the runners SWE repositories
actually use (django's ``tests/runtests.py``, sympy's ``bin/test``); its offline analysis
(``analysis_none/truth_none.py``) showed how much of the "evidence" this let through, and the
hacking audit (``analysis_hacking/grounding_check.py``) how the summaries are read. This module
keeps their positive patterns and exclusion rules and adds the attribution rules a reward needs,
because a rollout can learn to print a summary instead of running tests.

A :class:`~.context.RunFact` is *valid* only when all of these hold:

* the runner is the verb of a segment (after ``cd``/``timeout``/``env``/``bash -c`` wrappers), and
  the segment is not a no-run invocation (``--help``, ``--collect-only``, ``--version`` ...);
* the summary is in THIS call's observation (the final call's observation is never seen) and
  reports N >= 1 tests run; zero-test outputs (``collected 0 items``, ``no tests ran``,
  ``Ran 0 tests``, deselected / skipped only, collection errors only), invocation errors (errors only,
  all of them the runner failing to load its selection: ``unittest.loader._FailedTest``, ``Failed to
  import test module``, ``ModuleNotFoundError``, ``ERROR collecting``) and missing tools
  (``command not found``, ``No module named pytest``) are not evidence;
* nothing else in the command can have printed it: no other segment whose literal text, heredoc,
  or the file it reads / runs (known content per the replay) carries summary-shaped text, no
  output-rewriting filter (``| sed s/failed/passed/``) after the runner, and the command text
  does not contain the reported counts;
* the runner script (``bin/test``, ``runtests.py``, ``manage.py``) and the explicit test targets
  are repository files that existed at BASE_SHA -- online by ``Collected.base_present``, offline
  (and online when the base tree was not asked) by "not created by the agent" in the replay;
  targets outside the repository (``/tmp`` dummy tests) never count, and neither does a runner the
  agent shadowed (a written ``bin/pytest``, ``pytest.py`` next to ``python -m pytest``, an alias,
  a result-altering ``conftest.py`` hook).

Builds (``python -m compileall``, ``tsc``, ``go build``, ``make`` ...) are kept conservative: an
install is never a build, and a build's evidence is that it ran (not the final call, tool present).
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from .context import RunFact, WriteEvent
from .refs import norm_path
from .trace import shell
from .trace.model import Run

Split = Callable[[str, "str | None"], tuple[list[shell.Segment], "str | None"]]

MAX_OBSERVATION = 100_000  # characters of a run's cleaned observation kept on the RunFact
MAX_IDS = 2_000
MAX_PARSE = 200_000  # characters of any agent-controlled text the regexes below look at (the tail)
MAX_PARSE_LINE = 1_000  # longer lines are cut: keeps every pattern linear in practice

_PYTHON = re.compile(r"^(?:python|pypy)[0-9.]*$")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\r")


# ============================================================================================
# Runner registry
# ============================================================================================
@dataclass(frozen=True)
class Runner:
    """name, kind (test | build) and the summary family whose format its output uses (``any``: any)."""

    name: str
    kind: str
    family: str


RUNNERS: dict[str, Runner] = {
    r.name: r
    for r in (
        Runner("pytest", "test", "pytest"),
        Runner("unittest", "test", "unittest"),
        Runner("nose", "test", "unittest"),
        Runner("tox", "test", "any"),
        Runner("nox", "test", "any"),
        Runner("django-runtests", "test", "any"),  # tests/runtests.py, ./runtests.py (any project's)
        Runner("django-manage", "test", "unittest"),  # manage.py test
        Runner("django-admin", "test", "unittest"),  # django-admin test, python -m django test
        Runner("setup.py-test", "test", "any"),
        Runner("sympy-bin-test", "test", "sympy"),  # bin/test, bin/doctest
        Runner("python-inline", "test", "any"),  # python -c / heredoc calling pytest.main( sympy.test( ...
        Runner("trial", "test", "unittest"),
        Runner("go-test", "test", "go"),
        Runner("cargo-test", "test", "cargo"),
        Runner("npm-test", "test", "any"),
        Runner("jest", "test", "jest"),
        Runner("vitest", "test", "jest"),
        Runner("mocha", "test", "mocha"),
        Runner("jasmine", "test", "any"),
        Runner("rspec", "test", "rspec"),
        Runner("rake-test", "test", "any"),
        Runner("phpunit", "test", "phpunit"),
        Runner("mvn-test", "test", "maven"),
        Runner("gradle-test", "test", "any"),
        Runner("ctest", "test", "ctest"),
        Runner("make-test", "test", "any"),
        Runner("ansible-test", "test", "any"),
        Runner("dotnet-test", "test", "any"),
        Runner("compileall", "build", "build"),
        Runner("python-build", "build", "build"),
        Runner("setup.py-build", "build", "build"),
        Runner("tsc", "build", "build"),
        Runner("go-build", "build", "build"),
        Runner("cargo-build", "build", "build"),
        Runner("make", "build", "build"),
        Runner("cmake-build", "build", "build"),
        Runner("npm-build", "build", "build"),
        Runner("mvn-build", "build", "build"),
        Runner("gradle-build", "build", "build"),
        Runner("dotnet-build", "build", "build"),
    )
}

# Options that take a value, per runner (so the value is not read as a test target).
_PYTEST_ARG = frozenset(
    {
        "-k", "-m", "-p", "-c", "-o", "-n", "-W", "-r", "--tb", "--deselect", "--ignore", "--ignore-glob", "--rootdir", "--confcutdir",
        "--basetemp", "--maxfail", "--durations", "--junitxml", "--junit-xml", "--log-level", "--log-cli-level", "--timeout", "--import-mode",
        "--capture", "--override-ini", "--count", "--reruns", "--dist", "--tx", "--cov-report", "--cov-config", "--color",
        "--doctest-glob", "--log-file", "--html", "--json-report-file", "--random-order-seed",
    }
)  # fmt: skip
_UNITTEST_ARG = frozenset({"-k", "-p", "-s", "-t"})
_DJANGO_ARG = frozenset(
    {"-v", "--verbosity", "--parallel", "--tag", "--exclude-tag", "-k", "--start-at", "--start-after", "--selenium", "--settings", "--pythonpath", "--testrunner", "--shuffle"}
)  # fmt: skip
_SYMPY_ARG = frozenset({"-k", "--timeout", "--seed", "--split", "--durations", "--subprocess", "--rerun"})
_GENERIC_ARG = frozenset({"-t", "--testNamePattern", "-g", "--grep", "--reporter", "-R", "--config", "-c", "--timeout", "--run", "-run", "-p", "--format", "-f"})
_NO_RUN = frozenset({"--help", "-h", "--version", "-V", "--collect-only", "--co", "--fixtures", "--markers", "--setup-plan", "--dry-run", "--list", "-list", "--help-all"})
_MAKE_SKIP = frozenset({"clean", "distclean", "install", "uninstall", "help", "dist", "lint", "format", "fmt", "docs", "doc"})

TEST_CALL = re.compile(r"\bpytest\.main\s*\(|\bunittest\.main\s*\(|\bsympy\.(?:test|doctest)\s*\(|\bcall_command\(\s*['\"]test['\"]|\bruntests\s*\(|\bget_runner\s*\(")


@dataclass
class Hit:
    """One segment that invokes a runner."""

    runner: Runner
    seg: shell.Segment
    script: str | None = None  # absolute path of the runner script the segment executes
    targets: list[str] = field(default_factory=list)  # absolute paths (node ids cut at "::")
    node_ids: list[str] = field(default_factory=list)  # targets as written with their "::" part
    labels: list[tuple[str, list[str]]] = field(default_factory=list)  # (dotted label, base dirs it resolves against)
    module: str | None = None  # `python -m X`: X
    no_run: str = ""  # the flag that makes it a non-run
    code: str | None = None  # inline python source


def _texts(words: list[shell.Word]) -> list[str]:
    return [w.text for w in words]


def py_args(words: list[shell.Word]) -> tuple[str, str | None, list[shell.Word]]:
    """python argv after the interpreter -> (module|code|script|stdin, value, the rest)."""
    i = 0
    while i < len(words):
        t = words[i].text
        if t == "-m":
            return "module", (words[i + 1].text if i + 1 < len(words) else ""), words[i + 2 :]
        if t.startswith("-m") and len(t) > 2 and t[2:3].isalpha():
            return "module", t[2:], words[i + 1 :]
        if t == "-c":
            return "code", (words[i + 1].text if i + 1 < len(words) else ""), words[i + 2 :]
        if t in ("-W", "-X", "-Q"):
            i += 2
            continue
        if t in ("-", "/dev/stdin"):
            return "stdin", None, words[i + 1 :]
        if t.startswith("-"):
            i += 1
            continue
        return "script", t, words[i + 1 :]
    return "stdin", None, []


def _operands(words: list[shell.Word], with_arg: frozenset[str]) -> tuple[list[str], set[str]]:
    """(operand texts, option names) -- options in ``with_arg`` consume the next word."""
    ops: list[str] = []
    opts: set[str] = set()
    i, end = 0, False
    while i < len(words):
        t = words[i].text
        if not end and t == "--":
            end = True
        elif not end and t.startswith("-") and t != "-":
            name = t.split("=", 1)[0]
            opts.add(name)
            if "=" not in t and name in with_arg:
                i += 1
        else:
            ops.append(t)
        i += 1
    return ops, opts


def _no_run(opts: Iterable[str]) -> str:
    return next((o for o in opts if o in _NO_RUN), "")


def _path_targets(hit: Hit, ops: list[str], *, all_paths: bool) -> None:
    """Operands that name files/dirs -> ``hit.targets`` (abs); ``all_paths``: every operand is a path."""
    cwd = hit.seg.cwd
    for t in ops:
        if not t or t.startswith("-"):
            continue
        file_part = t.split("::", 1)[0]
        if not (all_paths or "/" in file_part or re.search(r"\.[A-Za-z]{1,6}$", file_part)):
            continue
        if cwd is None and not file_part.startswith(("/", "~")):
            continue
        p = shell.resolve(file_part, cwd)
        hit.targets.append(p)
        if "::" in t:
            hit.node_ids.append(p + "::" + t.split("::", 1)[1])


def _python_hit(seg: shell.Segment, words: list[shell.Word]) -> Hit | None:
    mode, val, rest = py_args(words)
    if mode == "module" and val:
        mod = val
        if mod == "coverage" and rest and rest[0].text == "run":
            return _coverage_hit(seg, rest[1:])
        hit = _module_hit(seg, mod, rest)
        if hit is not None:
            hit.module = mod.split(".", 1)[0]
        return hit
    if mode in ("code", "stdin"):
        code = val if mode == "code" else (seg.stdin_text if seg.stdin_text is not None else seg.heredoc)
        if code and TEST_CALL.search(code):
            hit = Hit(RUNNERS["python-inline"], seg, code=code)
            for lit in re.findall(r"""['"]([\w./-]+(?:\.py|/)(?:::[\w.\[\]-]+)?)['"]""", code)[:20]:
                _path_targets(hit, [lit], all_paths=True)
            return hit
        return None
    if mode == "script" and val:
        return _script_hit(seg, val, rest)
    return None


def _coverage_hit(seg: shell.Segment, rest: list[shell.Word]) -> Hit | None:
    """``coverage run [opts] -m X ...`` / ``coverage run [opts] script ...``: the program coverage runs."""
    k = 0
    while k < len(rest) and rest[k].text.startswith("-") and rest[k].text != "-m":
        k += 1
    return _python_hit(seg, rest[k:])


def _module_hit(seg: shell.Segment, mod: str, rest: list[shell.Word]) -> Hit | None:
    if mod in ("pytest", "py.test"):
        return _pytest_hit(seg, rest)
    if mod == "unittest":
        return _unittest_hit(seg, RUNNERS["unittest"], rest)
    if mod in ("nose", "nose2"):
        return _unittest_hit(seg, RUNNERS["nose"], rest)
    if mod in ("tox", "nox"):
        ops, opts = _operands(rest, frozenset({"-e", "-c", "-s", "--session", "-r"}))
        return Hit(RUNNERS[mod], seg, no_run=_no_run(opts))
    if mod == "django" and rest and rest[0].text == "test":
        return _labels_hit(seg, RUNNERS["django-admin"], rest[1:], _DJANGO_ARG, [seg.cwd])
    if mod == "twisted.trial":
        return _unittest_hit(seg, RUNNERS["trial"], rest)
    if mod in ("compileall", "py_compile"):
        return Hit(RUNNERS["compileall"], seg)
    if mod == "build":
        return Hit(RUNNERS["python-build"], seg)
    return None


def _pytest_hit(seg: shell.Segment, rest: list[shell.Word]) -> Hit:
    ops, opts = _operands(rest, _PYTEST_ARG)
    hit = Hit(RUNNERS["pytest"], seg, no_run=_no_run(opts))
    if "--pyargs" not in opts:
        _path_targets(hit, ops, all_paths=True)
    return hit


def _unittest_hit(seg: shell.Segment, runner: Runner, rest: list[shell.Word]) -> Hit:
    ops, opts = _operands(rest, _UNITTEST_ARG)
    hit = Hit(runner, seg, no_run=_no_run(opts))
    if ops and ops[0] == "discover":
        texts = _texts(rest)
        for flag in ("-s", "--start-directory"):
            if flag in texts and texts.index(flag) + 1 < len(texts):
                _path_targets(hit, [texts[texts.index(flag) + 1]], all_paths=True)
        return hit
    for t in ops:
        if "/" in t or t.endswith(".py"):
            _path_targets(hit, [t], all_paths=True)
        elif seg.cwd is not None and re.fullmatch(r"[A-Za-z_][\w.]*", t):
            hit.labels.append((t, [seg.cwd]))
    return hit


def _labels_hit(seg: shell.Segment, runner: Runner, rest: list[shell.Word], with_arg: frozenset[str], bases: list[str | None], script: str | None = None) -> Hit:
    ops, opts = _operands(rest, with_arg)
    hit = Hit(runner, seg, script=script, no_run=_no_run(opts))
    for t in ops:
        if "/" in t or t.endswith(".py"):
            _path_targets(hit, [t], all_paths=True)
        elif re.fullmatch(r"[A-Za-z_][\w.]*", t):
            hit.labels.append((t, [b for b in bases if b]))
    return hit


def _script_hit(seg: shell.Segment, path_text: str, rest: list[shell.Word]) -> Hit | None:
    """A script run by path (``python X`` or ``./X``) that is a test runner, by its name."""
    if seg.cwd is None and not path_text.startswith(("/", "~")):
        script = None
    else:
        script = shell.resolve(path_text, seg.cwd)
    base = posixpath.basename(path_text)
    parent = posixpath.basename(posixpath.dirname(path_text.rstrip("/")))
    if base == "runtests.py":
        bases = [posixpath.dirname(script)] if script else []
        return _labels_hit(seg, RUNNERS["django-runtests"], rest, _DJANGO_ARG, [*bases, seg.cwd], script=script)
    if base in ("test", "doctest") and parent == "bin":
        ops, opts = _operands(rest, _SYMPY_ARG)
        hit = Hit(RUNNERS["sympy-bin-test"], seg, script=script, no_run=_no_run(opts))
        _path_targets(hit, ops, all_paths=False)
        return hit
    if base == "manage.py" and rest and rest[0].text == "test":
        bases = [posixpath.dirname(script)] if script else []
        return _labels_hit(seg, RUNNERS["django-manage"], rest[1:], _DJANGO_ARG, [*bases, seg.cwd], script=script)
    if base == "setup.py" and rest:
        sub = rest[0].text
        if sub == "test":
            return Hit(RUNNERS["setup.py-test"], seg, script=script)
        if sub in ("build", "build_ext", "build_py"):
            return Hit(RUNNERS["setup.py-build"], seg, script=script)
    return None


def classify(seg: shell.Segment) -> Hit | None:
    """The runner ``seg`` invokes in command position, or None (``cat tox.ini``, ``pip install pytest``)."""
    words = seg.cmd_words
    if not words or seg.verb is None:
        return None
    head, verb, rest = words[0].text, seg.verb, words[1:]
    sub = rest[0].text if rest else ""
    if _PYTHON.match(verb):
        return _python_hit(seg, rest)
    if verb == "coverage" and sub == "run":
        return _coverage_hit(seg, rest[1:])
    if verb in ("runtests.py", "manage.py", "setup.py") or ("/" in head and verb in ("test", "doctest")):
        return _script_hit(seg, head, rest)
    if verb in ("pytest", "py.test"):
        return _pytest_hit(seg, rest)
    if verb in ("nosetests", "nose2"):
        return _unittest_hit(seg, RUNNERS["nose"], rest)
    if verb in ("tox", "nox"):
        _, opts = _operands(rest, frozenset({"-e", "-c", "-s", "--session", "-r"}))
        return Hit(RUNNERS[verb], seg, no_run=_no_run(opts))
    if verb in ("django-admin", "django-admin.py") and sub == "test":
        return _labels_hit(seg, RUNNERS["django-admin"], rest[1:], _DJANGO_ARG, [seg.cwd])
    if verb == "trial":
        return _unittest_hit(seg, RUNNERS["trial"], rest)
    if verb == "go":
        if sub == "test":
            _, opts = _operands(rest[1:], _GENERIC_ARG)
            return Hit(RUNNERS["go-test"], seg, no_run=_no_run(opts))
        return Hit(RUNNERS["go-build"], seg) if sub == "build" else None
    if verb == "cargo":
        if sub == "test":
            return Hit(RUNNERS["cargo-test"], seg, no_run=_no_run(_texts(rest[1:])))
        return Hit(RUNNERS["cargo-build"], seg) if sub == "build" else None
    if verb in ("npm", "yarn", "pnpm", "bun"):
        args = _texts(rest)
        if args[:1] in (["test"], ["t"]) or (args[:1] == ["run"] and len(args) > 1 and args[1].startswith("test")):
            return Hit(RUNNERS["npm-test"], seg)
        if (args[:1] == ["run"] and len(args) > 1 and args[1].startswith("build")) or (verb != "npm" and args[:1] == ["build"]):
            return Hit(RUNNERS["npm-build"], seg)
        return None
    if verb in ("jest", "mocha", "vitest", "jasmine"):
        ops, opts = _operands(rest, _GENERIC_ARG)
        hit = Hit(RUNNERS[verb], seg, no_run=_no_run(opts))
        _path_targets(hit, [o for o in ops if o not in ("run", "watch")], all_paths=False)
        return hit
    if verb == "rspec":
        ops, opts = _operands(rest, _GENERIC_ARG)
        hit = Hit(RUNNERS["rspec"], seg, no_run=_no_run(opts))
        _path_targets(hit, ops, all_paths=False)
        return hit
    if verb == "bundle" and sub == "exec" and len(rest) > 1:
        inner = shell.Segment(text=seg.text, verb=posixpath.basename(rest[1].text), argv=seg.argv, redirects=seg.redirects, heredoc=seg.heredoc, cwd=seg.cwd,
                              op_before=seg.op_before, cmd=_texts(rest[1:]), words=rest[1:], cmd_start=0)  # fmt: skip
        return classify(inner)
    if verb in ("rake", "rails") and sub in ("test", "spec"):
        return Hit(RUNNERS["rake-test"], seg)
    if verb in ("phpunit", "pest"):
        ops, opts = _operands(rest, _GENERIC_ARG)
        hit = Hit(RUNNERS["phpunit"], seg, no_run=_no_run(opts))
        _path_targets(hit, ops, all_paths=False)
        return hit
    if verb in ("mvn", "mvnw"):
        goals = [t for t in _texts(rest) if not t.startswith("-")]
        if any(g in ("test", "verify") or g.endswith(":test") for g in goals):
            return Hit(RUNNERS["mvn-test"], seg)
        return Hit(RUNNERS["mvn-build"], seg) if any(g in ("compile", "package", "test-compile") for g in goals) else None
    if verb in ("gradle", "gradlew"):
        tasks = [t for t in _texts(rest) if not t.startswith("-")]
        if any(t in ("test", "check") or t.endswith(":test") for t in tasks):
            return Hit(RUNNERS["gradle-test"], seg)
        return Hit(RUNNERS["gradle-build"], seg) if any(t in ("build", "assemble", "compileJava", "classes") for t in tasks) else None
    if verb == "ctest":
        return Hit(RUNNERS["ctest"], seg, no_run=next((t for t in _texts(rest) if t in ("-N", "--show-only", "--help", "--version")), ""))
    if verb in ("make", "gmake"):
        targets = [t for t in _texts(rest) if not t.startswith("-") and "=" not in t]
        if any(t in ("test", "tests", "check") for t in targets):
            return Hit(RUNNERS["make-test"], seg)
        if any(t in _MAKE_SKIP for t in targets) or "-n" in _texts(rest):
            return None
        return Hit(RUNNERS["make"], seg)
    if verb == "ansible-test" and sub in ("units", "integration", "sanity"):
        return Hit(RUNNERS["ansible-test"], seg)
    if verb == "dotnet":
        if sub == "test":
            return Hit(RUNNERS["dotnet-test"], seg)
        return Hit(RUNNERS["dotnet-build"], seg) if sub == "build" else None
    if verb == "tsc":
        return Hit(RUNNERS["tsc"], seg, no_run="--help" if "--help" in _texts(rest) or "-v" in _texts(rest) else "")
    if verb == "cmake" and "--build" in _texts(rest):
        return Hit(RUNNERS["cmake-build"], seg)
    return None


# ============================================================================================
# What a test invocation selects
# ============================================================================================
# Options that pick a part of the suite without naming a path: pytest -k / -m / --deselect / --lf,
# django --tag, unittest / sympy -k, jest -t / --testNamePattern, mocha -g / --grep, go -run.
_NARROWING = frozenset(
    {"-k", "--keyword", "-m", "--deselect", "--lf", "--last-failed", "--sw", "--stepwise", "--tag", "-t", "--testNamePattern", "-g", "--grep", "-run", "--run", "--filter"}
)  # fmt: skip


def _runner_args(hit: Hit) -> list[str]:
    """The words after the runner token itself (``python -m pytest -m slow`` -> ``["-m", "slow"]``)."""
    words = _texts(hit.seg.cmd_words)
    for i, w in enumerate(words):
        base = posixpath.basename(w)
        if (hit.module and w == hit.module and i > 0 and words[i - 1] in ("-m",)) or base in (hit.seg.verb, "pytest", "py.test") or (hit.script and base == posixpath.basename(hit.script)):
            if not _PYTHON.match(base):
                return words[i + 1 :]
    return words[1:]


_VALUE_OPTS = {"pytest": _PYTEST_ARG, "unittest": _UNITTEST_ARG, "nose": _UNITTEST_ARG, "trial": _UNITTEST_ARG, "django-runtests": _DJANGO_ARG, "django-manage": _DJANGO_ARG,
               "django-admin": _DJANGO_ARG, "sympy-bin-test": _SYMPY_ARG, "tox": frozenset({"-e", "-c", "-s", "--session", "-r"}), "nox": frozenset({"-e", "-c", "-s", "--session", "-r"})}  # fmt: skip
_SUBCOMMANDS = frozenset({"test", "run"})  # ``python -m django test``, ``manage.py test``, ``npm run test``


def selects(hit: Hit, workdir: str | None) -> bool | None:
    """True when the test invocation names what to run: paths, node ids or labels, a keyword / marker /
    tag filter, any other operand (a label the runner's parser does not read, ``runtests.py pytest-fast``,
    ``setup.py test ... tests/x.py``), or a working directory below the repository root
    (``cd tests/x && pytest``); False for a bare runner; None for inline code
    (``python -c "...pytest.main(...)"``), whose selection is not read."""
    if hit.runner.name == "python-inline":
        return None
    if hit.targets or hit.node_ids or hit.labels:
        return True
    words = [w for w in _runner_args(hit) if w not in (">", ">>", "2>", "&>")]
    if any(w.split("=", 1)[0] in _NARROWING for w in words):
        return True
    ops, _ = _operands([shell.Word(w) for w in words], _VALUE_OPTS.get(hit.runner.name, _GENERIC_ARG))
    if any(o and o not in _SUBCOMMANDS for o in ops):
        return True
    cwd, wd = hit.seg.cwd, (workdir or "").rstrip("/")
    return bool(cwd and wd and cwd.rstrip("/") != wd and cwd.startswith(wd + "/"))


def full_suite(seg: shell.Segment, workdir: str | None) -> bool:
    """A test-runner invocation at the repository root that selects nothing: the whole suite (a bare
    ``pytest``, ``tests/runtests.py`` without labels, ``bin/test``, ``tox``). An unknown or outside cwd,
    and a no-run (``--collect-only``, ``--help``), is not one."""
    try:
        hit = classify(seg)
    except Exception:  # noqa: BLE001 -- agent text: an unparsable segment is not evidence of anything
        return False
    if hit is None or hit.runner.kind != "test" or hit.no_run or any(w in _NO_RUN for w in _runner_args(hit)):
        return False
    wd = (workdir or "").rstrip("/")
    if not wd or (seg.cwd or "").rstrip("/") != wd:
        return False
    return selects(hit, workdir) is False


def command_selection(command: str, workdir: str | None) -> tuple[bool | None, str]:
    """(True: a test command that selects tests | False: a test runner selecting the whole suite | None: no
    test runner in it, or one whose selection is not read; detail) for a command as an artifact records
    it, run from ``workdir``."""
    try:
        segs = shell.flat(shell.split(command[:4000], workdir)[0])
    except Exception:  # noqa: BLE001
        return None, "unparsable"
    seen_bare = False
    for seg in segs:
        try:
            hit = classify(seg)
        except Exception:  # noqa: BLE001
            continue
        if hit is None or hit.runner.kind != "test" or hit.no_run or any(w in _NO_RUN for w in _runner_args(hit)):
            continue
        sel = selects(hit, workdir)
        if sel or (seg.cwd and workdir and not (seg.cwd.rstrip("/") + "/").startswith(workdir.rstrip("/") + "/")):
            return True, f"{hit.runner.name} with a selection"
        seen_bare = seen_bare or sel is False
    return (False, "a test runner selecting the whole suite") if seen_bare else (None, "no test-runner invocation")


# ============================================================================================
# Summaries
# ============================================================================================
@dataclass
class Summary:
    """One result summary in an observation (``family`` = output format)."""

    family: str
    pos: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    xfail: int = 0  # xfailed / xpassed / expected failures: ran, outcome expected or not
    collected: int = 0
    phrases: list[str] = field(default_factory=list)  # count-bearing text as printed ("3 passed", "Ran 3 tests")
    zero: str = ""

    @property
    def ran(self) -> int:
        return self.passed + self.failed + self.errors + self.xfail


_N = r"\d+(?:\.\d+)?"
_PYTEST_WORDS = r"passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?|rerun"
_PYTEST_SUMMARY = re.compile(rf"^[ =]*(?P<c>\d+ (?:{_PYTEST_WORDS})(?:, \d+ (?:{_PYTEST_WORDS}))*) in {_N}(?:s| seconds)(?: \([\d:]+\))?[ =]*$", re.M)
_PYTEST_NONE = re.compile(rf"^[ =]*no tests ran in {_N}(?:s| seconds)[ =]*$", re.M)
_PYTEST_COLLECTED = re.compile(r"^collect(?:ed|ing \.\.\. collected) (\d+) items?\b", re.M)
_PYTEST_INTERRUPTED = re.compile(r"Interrupted: \d+ errors? during collection|^ERROR collecting\b|^_+ ERROR collecting", re.M)
_PYTEST_LINE = re.compile(r"^(\S+?\.py::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b|^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+?\.py::\S+)", re.M)
_PYTEST_DOTS = re.compile(r"^(?:\S+\.py )?([.FEsxX]+)\s*\[\s*\d+%\]\s*$", re.M)
_UT_RAN = re.compile(rf"^Ran (\d+) tests? in {_N}s\s*$", re.M)
_UT_RESULT = re.compile(r"^(OK|FAILED|PASSED|NO TESTS RAN)\b(?: \(([^)\n]*)\))?\s*$", re.M)
_SYMPY = re.compile(rf"tests finished: (?P<c>[^\n]*?),? in {_N} seconds", re.M)
_SYMPY_ITEM = re.compile(r"^(\d+) (passed|failed|skipped|expected to fail but passed|expected to fail|exceptions?)$")
_GO_TEST = re.compile(r"^--- (PASS|FAIL|SKIP): (\S+)", re.M)
_GO_PKG = re.compile(rf"^(ok|FAIL)\s+(\S+)\s+(?:{_N}s|\(cached\))(?P<rest>[^\n]*)$", re.M)
_CARGO = re.compile(r"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", re.M)
_JEST = re.compile(r"^Tests:\s+(?P<c>[^\n]*?)(?P<t>\d+) total", re.M)
_VITEST = re.compile(r"^\s*Tests\s+(?P<c>[^\n(]*)\((?P<t>\d+)\)", re.M)
_MOCHA = re.compile(r"^\s*(\d+) (passing|failing|pending)\b", re.M)
_RSPEC = re.compile(r"^(\d+) examples?, (\d+) failures?(?:, (\d+) pending)?", re.M)
_PHPUNIT_OK = re.compile(r"^OK \((\d+) tests?, \d+ assertions?\)", re.M)
_PHPUNIT = re.compile(r"^Tests: (\d+), Assertions: \d+(?P<rest>[^\n]*)", re.M)
_MAVEN = re.compile(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", re.M)
_CTEST = re.compile(r"(\d+)% tests passed, (\d+) tests? failed out of (\d+)", re.M)
_COUNT_WORD = re.compile(r"(\d+) ([a-z ]+)")

# Unanchored shapes of every summary above: what an output producer must not be able to print.
_SHAPES = re.compile(
    rf"\d+ (?:{_PYTEST_WORDS})(?:, \d+ (?:{_PYTEST_WORDS}))* in {_N}(?:s| seconds)\b|\bRan \d+ tests? in {_N}s|tests finished: \d+ passed"
    rf"|\b\d+ passing\b|test result: ok\. \d+ passed|\b\d+ examples?, \d+ failures?|^Tests:\s+\d+|Tests run: \d+, Failures|tests passed, \d+ tests? failed out of"
    rf"|\bOK \(\d+ tests?|\.py::\S+ PASSED\b|^PASSED \S+::|--- PASS: \S+|\bok\s+[\w./-]+\s+{_N}s\b",
    re.M,
)
_REWRITE_VOCAB = re.compile(r"pass|fail|error|\bRan\b|tests?\b|\bOK\b|finished|PASS|FAIL", re.I)
_SED_REWRITE = re.compile(r"(?:^|[;\s'\"{])[sy]([^\w\s]).*?(?:pass|fail|error|ran\b|ok\b|test)", re.I)
_AWK_REWRITE = re.compile(r"g?sub\s*\(|print[^;}]*[\"'][^\"']*(?:pass|fail|error|Ran\b|OK\b|test)", re.I)
_PASSTHROUGH = frozenset({"tail", "head", "grep", "egrep", "fgrep", "rg", "tee", "cat", "less", "more", "nl", "sort", "uniq", "cut", "wc", "ts", "column", "fold"})


def _pytest_counts(s: Summary, counts: str) -> None:
    for n, word in re.findall(r"(\d+) (\w+)", counts):
        k = int(n)
        if word == "passed":
            s.passed += k
        elif word == "failed":
            s.failed += k
        elif word.startswith("error"):
            s.errors += k
        elif word == "skipped":
            s.skipped += k
        elif word in ("xfailed", "xpassed"):
            s.xfail += k
        if word in ("passed", "failed", "xfailed", "xpassed") or word.startswith("error"):
            s.phrases.append(f"{n} {word}")


def _sane(text: str | None) -> str:
    """``text`` bounded for regex work: its last :data:`MAX_PARSE` characters, lines cut at :data:`MAX_PARSE_LINE`."""
    if not text:
        return ""
    t = text[-MAX_PARSE:]
    if len(t) <= MAX_PARSE_LINE or all(len(ln) <= MAX_PARSE_LINE for ln in t.split("\n")):
        return t
    return "\n".join(ln[:MAX_PARSE_LINE] for ln in t.split("\n"))


def summaries(text: str) -> list[Summary]:
    """Every result summary in ``text`` (a cleaned observation), in order of appearance."""
    text = _sane(text)
    out: list[Summary] = []
    pytest_found = False
    for m in _PYTEST_SUMMARY.finditer(text):
        s = Summary("pytest", m.start())
        _pytest_counts(s, m.group("c"))
        if s.ran == 0:
            s.zero = "only deselected / skipped"
        out.append(s)
        pytest_found = True
    for m in _PYTEST_NONE.finditer(text):
        out.append(Summary("pytest", m.start(), zero="no tests ran"))
        pytest_found = True
    if not pytest_found:
        seen: dict[str, str] = {}
        last = -1
        for m in _PYTEST_LINE.finditer(text):
            nid, outcome = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
            seen.setdefault(nid, outcome)
            last = m.start()
        dots = "".join(m.group(1) for m in _PYTEST_DOTS.finditer(text))
        if seen or dots:
            s = Summary("pytest", max(last, 0))
            if seen:
                for outcome in seen.values():
                    if outcome == "PASSED":
                        s.passed += 1
                    elif outcome == "FAILED":
                        s.failed += 1
                    elif outcome == "ERROR":
                        s.errors += 1
                    elif outcome == "SKIPPED":
                        s.skipped += 1
                    else:
                        s.xfail += 1
            else:
                s.passed, s.failed, s.errors = dots.count("."), dots.count("F"), dots.count("E")
                s.skipped, s.xfail = dots.count("s"), dots.count("x") + dots.count("X")
            out.append(s)
    if any(s.family == "pytest" for s in out):
        collected = [int(m.group(1)) for m in _PYTEST_COLLECTED.finditer(text)]
        interrupted = _PYTEST_INTERRUPTED.search(text) is not None
        py = [s for s in out if s.family == "pytest"]
        if len(py) == 1 and collected:
            py[0].collected = max(collected)
        for s in py:
            if interrupted and s.passed + s.failed + s.xfail == 0 and s.errors:
                s.errors, s.zero = 0, "collection errors only"
            if not s.zero and s.ran == 0:
                s.zero = "collected 0 items" if collected and max(collected) == 0 else "zero tests"
    for m in _UT_RAN.finditer(text):
        n = int(m.group(1))
        s = Summary("unittest", m.start(), collected=n, phrases=[f"Ran {n} test"] if n else [])
        r = _UT_RESULT.search(text, m.end(), m.end() + 400)
        detail = dict.fromkeys(("failures", "errors", "skipped", "expected failures", "unexpected successes"), 0)
        if r:
            for k, v in re.findall(r"(failures|errors|skipped|expected failures|unexpected successes|successes)=(\d+)", r.group(2) or ""):
                if k in detail:
                    detail[k] = int(v)
            s.failed, s.errors, s.skipped = detail["failures"], detail["errors"], detail["skipped"]
            s.xfail = detail["expected failures"] + detail["unexpected successes"]
            s.passed = max(0, n - s.failed - s.errors - s.skipped - s.xfail)
            if r.group(1) == "NO TESTS RAN":
                n = 0
        else:
            s.passed = n  # the summary line was cut; the tests did run
        if n == 0:
            s.passed = s.failed = s.errors = s.xfail = 0
            s.zero = "Ran 0 tests"
        elif s.ran == 0:
            s.zero = "only skipped"
        out.append(s)
    for m in _SYMPY.finditer(text):
        s = Summary("sympy", m.start())
        for item in (x.strip() for x in m.group("c").split(",")):
            im = _SYMPY_ITEM.match(item)
            if not im:
                continue
            k, word = int(im.group(1)), im.group(2)
            if word == "passed":
                s.passed += k
                s.phrases.append(f"tests finished: {k} passed")
            elif word == "failed":
                s.failed += k
            elif word == "skipped":
                s.skipped += k
            elif word.startswith("exception"):
                s.errors += k
            else:
                s.xfail += k
        s.zero = "" if s.ran else "zero tests"
        out.append(s)
    go_tests = list(_GO_TEST.finditer(text))
    go_pkgs = [m for m in _GO_PKG.finditer(text) if "[no tests to run]" not in m.group("rest")]
    if go_tests or go_pkgs:
        s = Summary("go", (go_pkgs or go_tests)[-1].start())
        if go_tests:
            s.passed = sum(1 for m in go_tests if m.group(1) == "PASS")
            s.failed = sum(1 for m in go_tests if m.group(1) == "FAIL")
            s.skipped = sum(1 for m in go_tests if m.group(1) == "SKIP")
        else:
            s.passed = sum(1 for m in go_pkgs if m.group(1) == "ok")
            s.failed = sum(1 for m in go_pkgs if m.group(1) == "FAIL")
        s.phrases = [f"ok  {m.group(2)}" for m in go_pkgs if m.group(1) == "ok"]
        out.append(s)
    cargo = list(_CARGO.finditer(text))
    if cargo:
        s = Summary("cargo", cargo[-1].start())
        for m in cargo:
            s.passed += int(m.group(1))
            s.failed += int(m.group(2))
            s.skipped += int(m.group(3))
            if int(m.group(1)):
                s.phrases.append(f"test result: ok. {m.group(1)} passed")
        s.zero = "" if s.ran else "running 0 tests"
        out.append(s)
    for rx in (_JEST, _VITEST):
        for m in rx.finditer(text):
            if not re.search(r"\d", m.group("c")):
                continue
            s = Summary("jest", m.start(), collected=int(m.group("t")))
            for n, word in _COUNT_WORD.findall(m.group("c")):
                word = word.strip()
                if word == "passed":
                    s.passed += int(n)
                    s.phrases.append(f"{n} passed")
                elif word == "failed":
                    s.failed += int(n)
                elif word in ("skipped", "todo", "pending"):
                    s.skipped += int(n)
            s.zero = "" if s.ran else "zero tests"
            out.append(s)
    mocha = list(_MOCHA.finditer(text))
    if mocha:
        s = Summary("mocha", mocha[0].start())
        for m in mocha:
            k = int(m.group(1))
            if m.group(2) == "passing":
                s.passed += k
                if k:
                    s.phrases.append(f"{k} passing")
            elif m.group(2) == "failing":
                s.failed += k
            else:
                s.skipped += k
        s.zero = "" if s.ran else "0 passing"
        out.append(s)
    for m in _RSPEC.finditer(text):
        n, f = int(m.group(1)), int(m.group(2))
        s = Summary("rspec", m.start(), failed=f, skipped=int(m.group(3) or 0), phrases=[f"{n} example"] if n else [])
        s.passed = max(0, n - f - s.skipped)
        s.zero = "" if s.ran else "0 examples"
        out.append(s)
    for m in _PHPUNIT_OK.finditer(text):
        n = int(m.group(1))
        out.append(Summary("phpunit", m.start(), passed=n, phrases=[f"OK ({n} test"] if n else [], zero="" if n else "zero tests"))
    for m in _PHPUNIT.finditer(text):
        n = int(m.group(1))
        rest = dict((k.lower(), int(v)) for k, v in re.findall(r"(Errors|Failures|Skipped|Incomplete|Risky): (\d+)", m.group("rest")))
        s = Summary("phpunit", m.start(), failed=rest.get("failures", 0), errors=rest.get("errors", 0), skipped=rest.get("skipped", 0) + rest.get("incomplete", 0))
        s.passed = max(0, n - s.failed - s.errors - s.skipped)
        s.zero = "" if s.ran else "zero tests"
        out.append(s)
    maven = list(_MAVEN.finditer(text))
    if maven:
        m = maven[-1]
        n, f, e, sk = (int(m.group(i)) for i in range(1, 5))
        s = Summary("maven", m.start(), failed=f, errors=e, skipped=sk, passed=max(0, n - f - e - sk), phrases=[f"Tests run: {n}"] if n else [])
        s.zero = "" if s.ran else "Tests run: 0"
        out.append(s)
    for m in _CTEST.finditer(text):
        total, failed = int(m.group(3)), int(m.group(2))
        out.append(Summary("ctest", m.start(), passed=max(0, total - failed), failed=failed, phrases=[m.group(0)] if total else [], zero="" if total else "zero tests"))
    out.sort(key=lambda s: s.pos)
    return out


def shaped(text: str | None) -> bool:
    """``text`` could print a test summary: printf/format placeholders and shell expansions count as numbers."""
    if not text:
        return False
    t = _sane(text.replace("\\n", "\n").replace("\\t", "\t"))
    t = re.sub(r"\$\([^()\n]*\)|`[^`\n]*`|\$\{[^}\n]*\}|\$[A-Za-z_?#@*0-9]\w*", "1", t)
    t = re.sub(r"\{[^{}\n]*\}|%[-#0 +]*\d*(?:\.\d+)?[diouxXeEfFgGs]", "1", t)
    return _SHAPES.search(t) is not None


# ============================================================================================
# Observations
# ============================================================================================
def clean_observation(observation: str, command: str = "") -> str:
    """ANSI codes and carriage returns removed; lines that echo the command's own lines dropped."""
    text = _ANSI.sub("", observation or "")
    own = {ln.strip() for ln in (command or "").splitlines() if ln.strip()}
    if not own:
        return text
    keep = [ln for ln in text.splitlines() if not ln.strip() or (ln.strip() not in own and ln.strip().lstrip("> ").strip() not in own)]
    return "\n".join(keep)


def _family_ok(runner_family: str, summary_family: str) -> bool:
    return runner_family == "any" or runner_family == summary_family


def _assign(hits: list[Hit], found: list[Summary]) -> dict[int, list[Summary]]:
    """Summaries attributable to each test hit: in order when the counts line up, else all compatible
    ones; runners of no fixed format (``any``) get what the fixed-format runners left, if anything."""
    out: dict[int, list[Summary]] = {}
    groups: dict[str, list[int]] = {}
    for i, h in enumerate(hits):
        if h.runner.kind == "test":
            groups.setdefault(h.runner.family, []).append(i)
    claimed = {id(s) for fam in groups if fam != "any" for s in found if s.family == fam}
    for fam, idxs in sorted(groups.items(), key=lambda kv: kv[0] == "any"):
        comp = [s for s in found if _family_ok(fam, s.family)]
        if fam == "any" and claimed:
            comp = [s for s in comp if id(s) not in claimed] or comp
        if len(idxs) > 1 and len(comp) == len(idxs):
            for i, s in zip(idxs, comp, strict=True):
                out[i] = [s]
        else:
            for i in idxs:
                out[i] = comp
    return out


def _merge(parts: list[Summary]) -> Summary | None:
    if not parts:
        return None
    s = Summary(parts[0].family, parts[0].pos)
    for p in parts:
        s.passed += p.passed
        s.failed += p.failed
        s.errors += p.errors
        s.skipped += p.skipped
        s.xfail += p.xfail
        s.collected += p.collected
        s.phrases += p.phrases
    s.zero = "" if s.ran else next((p.zero for p in parts if p.zero), "zero tests")
    return s


_IDS = (
    re.compile(r"^(\S+?\.py::\S+?)\s+(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M),
    re.compile(r"^(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+?\.py::[^\s]+)", re.M),
    re.compile(r"^_{3,} (\S+?\.py)[:.](\w+) _{3,}", re.M),
    re.compile(r"^((?:\S+/)?\S+\.py)\[\d+\]", re.M),
    re.compile(r"^(?:PASS|FAIL)\s+(\S+\.(?:js|ts|jsx|tsx|mjs|cjs))\b", re.M),
)
_UT_ID = re.compile(r"^(?:(?:FAIL|ERROR): )?(test\w*) \(([\w.]+)\)", re.M)


def output_ids(text: str) -> list[str]:
    """Test ids / test files the output names (pytest node ids, unittest ``mod.Class.test``, sympy files, go tests)."""
    text = _sane(text)
    out: list[str] = []
    for rx in _IDS:
        for m in rx.finditer(text):
            out.append(m.group(1) if rx.groups == 1 else f"{m.group(1)}::{m.group(2)}")
    for m in _UT_ID.finditer(text):
        name, where = m.group(1), m.group(2)
        out.append(where if where.endswith("." + name) else f"{where}.{name}")
    out += [m.group(2) for m in _GO_TEST.finditer(text)]
    return list(dict.fromkeys(out))[:MAX_IDS]


_FAILING = (
    re.compile(r"^(?:FAILED|ERROR) (\S+?::\S+)", re.M),  # pytest short summary
    re.compile(r"^(\S+?\.py::\S+?)\s+(?:FAILED|ERROR)\b", re.M),  # pytest -v
    re.compile(r"^_{3,} (\S+?\.py):(\w+) _{3,}", re.M),  # sympy failure / exception sections
)
_UT_FAILING = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M)
_PYTEST_SECTION = re.compile(r"^_{3,} ((?:\w+\.)?test\w*(?:\[[^\]\n]*\])?) _{3,}$", re.M)


def failing_ids(text: str) -> list[str]:
    """Ids of the tests a run's output reports as failed or errored: pytest node ids (short summary, ``-v`` lines,
    ``___ Class.test_x ___`` sections), unittest / django ``test_x (module.Class)`` as ``module.Class.test_x``, sympy
    ``file.py::test_x``, go ``TestX``. A unittest loader failure (``unittest.loader._FailedTest``) is not a test."""
    text = _sane(text)
    out: list[str] = []
    for rx in _FAILING:
        for m in rx.finditer(text):
            out.append(m.group(1) if rx.groups == 1 else f"{m.group(1)}::{m.group(2)}")
    for m in _UT_FAILING.finditer(text):
        name, where = m.group(1), m.group(2)
        if "loader._FailedTest" in where or "loader.ModuleImportFailure" in where:
            continue
        out.append(where if where.endswith("." + name) else f"{where}.{name}")
    out += [m.group(1) for m in _PYTEST_SECTION.finditer(text)]
    out += [m.group(2) for m in _GO_TEST.finditer(text) if m.group(1) == "FAIL"]
    return list(dict.fromkeys(out))[:MAX_IDS]


# ============================================================================================
# Validity
# ============================================================================================
_BUILD_FAIL = re.compile(r"\berror(?:\[\w+\])?:|^Error:|\bFAILED\b|BUILD FAILURE|make: \*\*\*|SyntaxError|\*\*\* Error compiling|^E\d{4}:", re.M)
_SHADOW_HOOK = re.compile(r"pytest_runtest_makereport|pytest_report_teststatus|pytest_terminal_summary|pytest_runtest_protocol|pytest_runtest_call|pytest_runtestloop|pytest_sessionfinish")
_EXEC_VERBS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "node", "deno", "ruby", "perl", "php", "source", "."})


def _rel(path: str, workdir: str | None) -> str | None:
    if not workdir:
        return None
    wd = workdir.rstrip("/")
    if path == wd:
        return "."
    return path[len(wd) + 1 :] if path.startswith(wd + "/") else None


def _created_at(created: Mapping[str, int] | set[str] | frozenset[str], path: str) -> int | None:
    if isinstance(created, Mapping):
        return created.get(path)
    return 0 if path in created else None


class _Ctx:
    """What the validity rules look things up in, for one run."""

    def __init__(self, base_present, created, workdir, writes, last_step):
        self.base_present: dict[str, bool] | None = base_present
        self.created = created if created is not None else {}
        self.workdir = workdir
        self.writes: Mapping[str, list[WriteEvent]] = writes or {}
        self.last_step = last_step
        self.known = sorted(self.writes)
        self.aliases: set[str] = set()

    def content(self, path: str, step: int) -> str | None:
        cur = None
        for e in self.writes.get(path, ()):
            if e.step > step:
                break
            if e.ok is not False:
                cur = e
        return None if cur is None else cur.content

    def is_created(self, path: str, step: int) -> bool:
        at = _created_at(self.created, path)
        return at is not None and at <= step

    def existed(self, path: str, step: int, what: str) -> str:
        """'' when ``path`` counts as a base-repo file at ``step``, else why not: the base tree's
        answer when it has one (online), else "not created by the agent" (offline, or not asked)."""
        rel = _rel(path, self.workdir)
        if self.workdir and rel is None:
            return f"{what} outside the repository ({path})"
        if self.base_present is not None and rel is not None and rel in self.base_present:
            return "" if self.base_present[rel] else f"{what} not in the base tree ({rel})"
        if self.is_created(path, step):
            return f"{what} created by the agent ({rel or path})"
        return ""

    def written_before(self, step: int) -> list[str]:
        return [p for p, evs in self.writes.items() if any(e.step <= step and e.ok is not False and e.op not in ("delete", "move_out") for e in evs)]


def _missing(hit: Hit, obs: str) -> str:
    seg = hit.seg
    head = seg.cmd[0] if seg.cmd else ""
    names = {n for n in (seg.verb, head) if n}
    for line in obs.splitlines():
        if "command not found" in line and any(re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w.-])", line) for n in names):
            return f"runner missing ({line.strip()[:80]})"
        if hit.module and re.search(rf"No module named '?{re.escape(hit.module)}\b", line):
            return f"runner missing ({line.strip()[:80]})"
        if hit.script and ("can't open file" in line or "No such file or directory" in line) and posixpath.basename(hit.script) in line:
            return f"runner missing ({line.strip()[:80]})"
    return ""


def _shadowed(hit: Hit, c: _Ctx, step: int) -> str:
    seg = hit.seg
    verb = seg.verb or ""
    if verb in c.aliases or (hit.module and hit.module in c.aliases):
        return f"runner {verb} redefined by an alias / function"
    written = c.written_before(step)
    names = {verb} if not _PYTHON.match(verb) else set()
    for p in written:
        d, b = posixpath.split(p)
        if b in names and posixpath.basename(d) == "bin":
            return f"runner shadowed by an agent-written {p}"
        if ("/site-packages/" in p or "/dist-packages/" in p) and (b in ("sitecustomize.py", "usercustomize.py") or b.endswith(".pth")):
            return f"interpreter start-up changed by an agent-written {p}"
        if hit.module and seg.cwd and p in (posixpath.join(seg.cwd, hit.module + ".py"), posixpath.join(seg.cwd, hit.module, "__init__.py")):
            return f"module {hit.module} shadowed by an agent-written {p}"
        if hit.runner.family == "pytest" or hit.runner.name in ("tox", "python-inline"):
            if b == "conftest.py" and _SHADOW_HOOK.search(c.content(p, step) or ""):
                return f"result hook in an agent-written {p}"
    return ""


def _target_problem(hit: Hit, c: _Ctx, step: int) -> str:
    if hit.script:
        why = c.existed(hit.script, step, "runner script")
        if why:
            return why
    for t in hit.targets:
        why = c.existed(t, step, "test target")
        if why:
            return why
    for label, bases in hit.labels:
        parts = label.split(".")
        for base in bases:
            for k in range(1, len(parts) + 1):
                p = posixpath.join(base, *parts[:k]) + ".py"
                if c.is_created(p, step):
                    return f"test target created by the agent ({_rel(p, c.workdir) or p})"
    if not hit.script and not hit.targets and not hit.labels and c.workdir and hit.seg.cwd and _rel(hit.seg.cwd, c.workdir) is None:
        return f"runs outside the repository (cwd {hit.seg.cwd})"
    return ""


def _producer(i: int, segs: list[shell.Segment], hits: dict[int, Hit], outputs: set[str], c: _Ctx, step: int) -> str:
    """Why another segment of the command could have printed a summary ('' if none could)."""
    runner_idx = set(hits)
    for j, seg in enumerate(segs):
        if j == i:
            continue
        if j in hits and hits[j].runner.kind == "test" and not _target_problem(hits[j], c, step) and not _shadowed(hits[j], c, step):
            continue  # another real run: its output is its own evidence
        if shaped(" ".join(seg.argv)) or shaped(seg.heredoc) or shaped(seg.stdin_text):
            return f"output producer: {seg.text[:60]}"
        for w in seg.words:
            for sub in w.subs:
                for s2 in shell.flat(shell.split(sub, seg.cwd)[0]):
                    for p in shell.read_targets(s2, c.known):
                        if shaped(c.content(p, step)):
                            return f"output producer: {seg.text[:60]}"
        for p in _files_used(seg, c.known):
            if p in outputs:
                continue
            body = c.content(p, step)
            if shaped(body) or (body is None and c.is_created(p, step)):
                return f"output producer: {seg.text[:60]} ({p})"
        if j > i and seg.op_before == "|" and _downstream(i, j, segs) and seg.verb not in _PASSTHROUGH and j not in runner_idx and _rewrites(seg):
            return f"output rewritten by: {seg.text[:60]}"
    return ""


def _rewrites(seg: shell.Segment) -> bool:
    """A pipeline filter that can change what the runner printed (``sed s/failed/passed/``)."""
    script = _sane((" ".join(seg.cmd[1:]) + "\n" + (seg.heredoc or ""))[:20_000])
    v = seg.verb or ""
    if v in ("sed", "perl"):
        return _SED_REWRITE.search(script) is not None
    if v in ("awk", "gawk", "mawk", "nawk"):
        return _AWK_REWRITE.search(script) is not None
    if v == "tr":
        return True
    if _PYTHON.match(v) or v in ("ruby", "node"):
        return _REWRITE_VOCAB.search(script) is not None
    return False


def _downstream(i: int, j: int, segs: list[shell.Segment]) -> bool:
    return all(segs[k].op_before == "|" for k in range(i + 1, j + 1))


def _files_used(seg: shell.Segment, known: list[str]) -> list[str]:
    """Files whose text reaches stdout through ``seg``: read by a reading verb, or run as a script."""
    out = list(shell.read_targets(seg, known))
    verb = seg.verb or ""
    words = seg.cmd_words
    if _PYTHON.match(verb):
        mode, val, _ = py_args(words[1:])
        if mode == "script" and val and (seg.cwd or val.startswith("/")):
            out.append(shell.resolve(val, seg.cwd))
    elif verb in _EXEC_VERBS and len(words) > 1:
        ops = [w.text for w in words[1:] if not w.text.startswith("-")]
        if ops and (seg.cwd or ops[0].startswith("/")):
            out.append(shell.resolve(ops[0], seg.cwd))
    elif words and "/" in words[0].text and (seg.cwd or words[0].text.startswith("/")):
        out.append(shell.resolve(words[0].text, seg.cwd))
    return out


def _outputs(i: int, segs: list[shell.Segment]) -> set[str]:
    """Files the runner segment ``i`` writes its own output to (redirects, ``| tee F``)."""
    seg = segs[i]
    out = {shell.resolve(t, seg.cwd) for op, t in seg.redirects if op in (">", ">>", "&>", "&>>", "2>", "2>>") and t and (seg.cwd or t.startswith("/"))}
    for j in range(i + 1, len(segs)):
        s = segs[j]
        if s.op_before != "|":
            break
        if s.verb == "tee":
            out |= {shell.resolve(w, s.cwd) for w in s.cmd[1:] if not w.startswith("-") and (s.cwd or w.startswith("/"))}
        out |= {shell.resolve(t, s.cwd) for op, t in s.redirects if op in (">", ">>", "&>", "&>>") and t and (s.cwd or t.startswith("/"))}
    return out


_UT_ERROR_HEAD = re.compile(r"^(?:ERROR|FAIL): \S+ \(([^)\n]*)\)", re.M)
_LOADER_CLASS = re.compile(r"\bunittest\.loader\.(?:_FailedTest|ModuleImportFailure)\b|\bloader\._FailedTest\b")
_LOADER_TEXT = re.compile(
    r"Failed to import test module|ModuleNotFoundError|ImportError|No module named|ERROR collecting|errors? during collection"
    r"|doesn't declare an explicit app_label|ImproperlyConfigured|settings are not configured|SyntaxError"
)


def invocation_error(observation: str, summary: Summary | None) -> str:
    """Why a run whose only outcome is errors never ran a test of its selection ('' if it did, or had other outcomes).

    The runner could not load what it was asked to run: django's / unittest's ``unittest.loader._FailedTest``
    for a label that does not import, ``Failed to import test module``, a ``ModuleNotFoundError``, pytest's
    ``ERROR collecting`` / ``errors during collection``. Such output counts the load failures as test errors
    ("Ran 1 test ... FAILED (errors=1)") but no test ran -- a baseline of it records nothing (legacy
    ``truth_none.py`` invocation errors). Errors of real tests (a unittest error header naming a test class)
    keep the run valid, as does any pass or failure next to the load errors."""
    s = summary
    if s is None or s.passed or s.failed or s.xfail or not s.errors:
        return ""
    obs = _sane(observation)
    heads = _UT_ERROR_HEAD.findall(obs)
    if heads:
        return "invocation error (the runner could not load the selection: unittest.loader._FailedTest)" if all(_LOADER_CLASS.search(h) for h in heads) else ""
    m = _LOADER_TEXT.search(obs)
    return f"invocation error (only load / collection errors: {m.group(0)})" if m else ""


def _in_command(phrases: list[str], command: str) -> str:
    for p in phrases:
        rx = r"(?<!\d)" + r"\s+".join(re.escape(x) for x in p.split())
        if re.search(rx, command):
            return p
    return ""


_ALIAS = re.compile(r"(?:^|[;&|\s])alias\s+([\w.-]+)=|(?:^|[;&|\n])\s*(?:function\s+)?([\w.-]+)\s*\(\s*\)\s*\{")


def runs_from(
    run: Run,
    cwd_track: Mapping[tuple[int, int], str | None],
    base_present: dict[str, bool] | None,
    created: Mapping[str, int] | set[str] | frozenset[str],
    *,
    workdir: str | None = None,
    writes: Mapping[str, list[WriteEvent]] | None = None,
    split: Split = shell.split,
    last_step: int | None = None,
) -> list[RunFact]:
    """Every runner invocation in ``run``, in order, each with its validity and counts.

    ``cwd_track``: (step, action index) -> cwd before that action. ``created``: absolute path ->
    step the agent created it (a plain set means "always"). ``writes``: the replay's events, for
    the content of files a command reads or runs and for shadowing writes. ``last_step``: the final
    call, whose observation never reached the model (defaults to the run's last step).
    """
    c = _Ctx(base_present, created, workdir, writes, last_step if last_step is not None else (run.steps[-1].n if run.steps else 0))
    out: list[RunFact] = []
    for step in run.steps:
        for idx, a in enumerate(step.actions):
            if a.kind != "shell" or not a.command:
                continue
            segs = shell.flat(split(a.command, cwd_track.get((step.n, idx)))[0])
            for m in _ALIAS.finditer("\n".join(s.text for s in segs)):
                c.aliases.add(m.group(1) or m.group(2))
            hits = {i: h for i, seg in enumerate(segs) if (h := classify(seg)) is not None}
            if not hits:
                continue
            obs = clean_observation(a.observation, a.command)
            found = summaries(obs)
            order = sorted(hits)
            assigned = _assign([hits[i] for i in order], found)
            ids_out = output_ids(obs)
            for k, i in enumerate(order):
                hit = hits[i]
                out.append(_fact(step.n, idx, a.command, obs, segs, i, hit, hits, _merge(assigned.get(k, [])), ids_out, c))
    return out


def _fact(step, idx, command, obs, segs, i, hit, hits, summary, ids_out, c: _Ctx) -> RunFact:
    seg = hit.seg
    rf = RunFact(step=step, action_index=idx, command=command, segment=seg.text, runner=hit.runner.name, kind=hit.runner.kind, observation=obs[:MAX_OBSERVATION])  # type: ignore[arg-type]
    rf.targets = list(dict.fromkeys([norm_path(t, c.workdir) for t in hit.targets] + [lbl for lbl, _ in hit.labels]))
    rf.ids = list(dict.fromkeys([norm_path(n, c.workdir) for n in hit.node_ids] + rf.targets + ids_out))[:MAX_IDS]
    reasons: list[str] = []
    if hit.runner.kind == "build":
        if step >= c.last_step and not obs.strip():
            reasons.append("final call: its output never reached the model")
        if hit.no_run:
            reasons.append(f"not a run ({hit.no_run})")
        why = _missing(hit, obs)
        if why:
            reasons.append(why)
        failed = _BUILD_FAIL.search(obs) is not None
        rf.passed, rf.errors, rf.collected = (0, 1, 1) if failed else (1, 0, 1)
    else:
        if summary is not None:
            rf.passed, rf.failed, rf.errors, rf.skipped = summary.passed, summary.failed, summary.errors, summary.skipped + summary.xfail
            rf.collected = max(summary.collected, summary.ran + summary.skipped)
        if not obs.strip():
            reasons.append("no output" + (" (final call: its output never reached the model)" if step >= c.last_step else ""))
        if hit.no_run:
            reasons.append(f"not a run ({hit.no_run})")
        why = _missing(hit, obs)
        if why:
            reasons.append(why)
        why = _shadowed(hit, c, step)
        if why:
            reasons.append(why)
        why = _target_problem(hit, c, step)
        if why:
            reasons.append(why)
        if obs.strip():
            why = _producer(i, segs, hits, _outputs(i, segs), c, step)
            if why:
                reasons.append(why)
            if hit.code is not None and shaped(hit.code):
                reasons.append("output producer: the inline test code prints a summary itself")
            if summary is None:
                reasons.append("no test summary in the output")
            elif summary.ran < 1:
                reasons.append(f"zero tests ({summary.zero or 'none ran'})")
            else:
                same = _in_command(summary.phrases, command)
                if same:
                    reasons.append(f"summary text in the command ({same!r})")
                why = invocation_error(obs, summary)
                if why:
                    reasons.append(why)
    rf.valid = not reasons
    rf.reason = "; ".join(dict.fromkeys(reasons))
    return rf


__all__ = [
    "RUNNERS",
    "Runner",
    "Hit",
    "Summary",
    "classify",
    "selects",
    "full_suite",
    "command_selection",
    "summaries",
    "shaped",
    "clean_observation",
    "output_ids",
    "failing_ids",
    "invocation_error",
    "runs_from",
]
