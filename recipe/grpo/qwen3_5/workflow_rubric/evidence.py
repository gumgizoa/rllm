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
* the summary is in THIS call's observation -- or, for a command the terminal left running, in the output of the
  empty commands sent right after it (``_continued``) -- (the final call's observation is never seen); for one
  pytest session the last pytest summary it printed (not one of a session run inside its tests, ``inner_sessions``),
  and
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
from typing import Any

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
        Runner("test-file", "test", "any"),  # a repository test file run directly: python tests/test_x.py, node test/x.test.js
        Runner("node-test", "test", "tap"),  # node --test
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
        Runner("go-vet", "build", "build"),
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
# go test: the flags that take a value (``-run X`` or ``-run=X``; one dash or two)
_GO_VALUE = frozenset(
    "run skip count tags mod modfile timeout p parallel cpu bench benchtime blockprofile blockprofilerate coverprofile covermode coverpkg cpuprofile memprofile "
    "memprofilerate mutexprofile mutexprofilefraction outputdir trace o exec ldflags gcflags asmflags gccgoflags shuffle vet list fuzz fuzztime fuzzminimizetime "
    "overlay pkgdir toolexec C installsuffix buildmode compiler buildvcs".split()
)  # fmt: skip
# jest / vitest / mocha: the options that take a value (the next word, unless written ``--opt=value``)
_JS_COMMON = frozenset({"--config", "-c", "--reporter", "--reporters", "--outputFile", "--testTimeout", "--maxWorkers", "--shard", "--testNamePattern", "-t"})
_JEST_VALUE = _JS_COMMON | frozenset(
    {"--testPathPattern", "--testPathPatterns", "--testPathIgnorePatterns", "--testRegex", "--testMatch", "--rootDir", "--roots", "--coverageDirectory", "--coverageReporters",
     "--collectCoverageFrom", "--coverageThreshold", "--cacheDirectory", "--env", "--testEnvironment", "--selectProjects", "--ignoreProjects", "--projects", "--changedSince",
     "--maxConcurrency", "--seed", "--setupFiles", "--setupFilesAfterEnv", "--transform", "--globals", "--moduleDirectories", "-w", "--testSequencer", "--runner", "--testRunner", "--filter"}
)  # fmt: skip
_VITEST_VALUE = _JS_COMMON | frozenset({"--root", "-r", "--dir", "--project", "--pool", "--environment", "--mode", "--hookTimeout", "--retry", "--exclude", "--minWorkers", "--api"})
_MOCHA_VALUE = frozenset(
    {"-g", "--grep", "-f", "--fgrep", "-t", "--timeout", "-R", "--reporter", "-r", "--require", "--config", "-s", "--slow", "--spec", "--extension", "--ui", "-u", "--file", "--ignore",
     "--exclude", "-O", "--reporter-option", "--loader", "--import", "-j", "--jobs", "--retries"}
)  # fmt: skip
_JS_VALUE = {"jest": _JEST_VALUE, "vitest": _VITEST_VALUE, "mocha": _MOCHA_VALUE, "jasmine": frozenset({"--config", "--filter", "--reporter", "--seed"})}
_PM_VALUE = _JEST_VALUE | _VITEST_VALUE  # behind ``npm test --``: the runner is not known
_JS_NAME = frozenset({"-t", "--testNamePattern"})  # a test name pattern (mocha: -g / -f)
_JS_PATH = frozenset({"--testPathPattern", "--testPathPatterns", "--testRegex", "--testMatch", "--spec"})
_JS_ONLY = frozenset({"-o", "--onlyChanged", "--changed", "--changedSince", "--lastCommit", "--onlyFailures", "--findRelatedTests", "--selectProjects", "--project", "--filter"})
_JS_NO_RUN = frozenset({"--listTests", "--showConfig", "--init", "--clearCache"})
_NODE_RUNNER = {"jest": "jest", "jest.js": "jest", "vitest": "vitest", "vitest.mjs": "vitest", "vitest.js": "vitest", "mocha": "mocha", "_mocha": "mocha", "mocha.js": "mocha", "jasmine": "jasmine", "jasmine.js": "jasmine"}  # fmt: skip
# a package script that runs tests, by its name: ``test``, ``test:unit``, ``unit-test``, ``jest``, ``spec``
_TEST_SCRIPT = re.compile(r"^test|^(?:t|tst)$|(?:^|[:._-])(?:tests?|jest|vitest|mocha|jasmine|specs?|unit)(?:$|[:._-])")
_PLAIN_SCRIPT = frozenset({"test", "t", "tst", "tests"})
_PM_DIR = frozenset({"--prefix", "--cwd", "-C", "--dir"})  # npm / yarn / pnpm: run in another directory
_PM_SCOPE = frozenset({"--filter", "-F", "-w", "--workspace"})  # ... or for some packages of the workspace
_NO_RUN = frozenset({"--help", "-h", "--version", "-V", "--collect-only", "--co", "--fixtures", "--markers", "--setup-plan", "--dry-run", "--list", "-list", "--help-all"})
_JS_RUNNERS = frozenset({"jest", "vitest", "mocha", "jasmine"})
_MAKE_SKIP = frozenset({"clean", "distclean", "install", "uninstall", "help", "dist", "lint", "format", "fmt", "docs", "doc"})

TEST_CALL = re.compile(r"\bpytest\.main\s*\(|\bunittest\.main\s*\(|\bsympy\.(?:test|doctest)\s*\(|\bcall_command\(\s*['\"]test['\"]|\bruntests\s*\(|\bget_runner\s*\(|\bTextTestRunner\s*\(")


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
    loose: list[str] = field(default_factory=list)  # relative path targets written under a cwd the trace does not know
    code: str | None = None  # inline python source
    # go test / jest / vitest / a package script: what narrows the run without naming a path the trace can resolve --
    # ``-run X`` / ``-skip X`` (go), ``-t X`` (a test name pattern), ``--testPathPattern X``, ``path X`` (a positional
    # file-name pattern), ``pkg X`` (a Go import path), ``script X`` (a package script other than ``test``)
    narrow: list[str] = field(default_factory=list)
    flat: list[str] = field(default_factory=list)  # go: targets that are one package (``./pkg``), not a tree (``./pkg/...``)


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


_UNSET = object()


def _path_targets(hit: Hit, ops: list[str], *, all_paths: bool, cwd: Any = _UNSET, patterns: bool = False) -> None:
    """Operands that name files/dirs -> ``hit.targets`` (abs); ``all_paths``: every operand is a path. ``cwd``: the
    directory they are relative to, when it is not the segment's (``yarn --cwd pkg test``). ``patterns``: an operand
    that is no path is a file-name pattern the runner filters by (``jest slug``) -> ``hit.narrow``."""
    cwd = hit.seg.cwd if cwd is _UNSET else cwd
    for t in ops:
        if not t or t.startswith("-"):
            continue
        file_part = t.split("::", 1)[0]
        if not (all_paths or "/" in file_part or re.search(r"\.[A-Za-z]{1,6}$", file_part)):
            if patterns:
                hit.narrow.append(f"path {t}")
            continue
        if cwd is None and not file_part.startswith(("/", "~")):
            hit.loose.append(file_part)
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
    if base in ("django-admin.py", "django-admin") and rest and rest[0].text == "test":
        return _labels_hit(seg, RUNNERS["django-admin"], rest[1:], _DJANGO_ARG, [seg.cwd], script=script)
    if base == "setup.py" and rest:
        sub = rest[0].text
        if sub == "test":
            return Hit(RUNNERS["setup.py-test"], seg, script=script)
        if sub in ("build", "build_ext", "build_py"):
            return Hit(RUNNERS["setup.py-build"], seg, script=script)
        return None
    return _test_file_hit(seg, script, path_text)


def _test_file_hit(seg: shell.Segment, script: str | None, path_text: str) -> Hit | None:
    """A test file run by path (``python tests/test_x.py``, ``node test/x.test.js``): a test run when it is a repository
    test file that was there before the run (:func:`_own_script` drops the others), read by its output like any runner."""
    from .facts import is_test_path  # facts builds on this module

    if script is None or not is_test_path(path_text):
        return None
    return Hit(RUNNERS["test-file"], seg, script=script)


def _inner(seg: shell.Segment, words: list[shell.Word], verb: str) -> shell.Segment:
    """``seg`` from ``words`` on, run as ``verb``: the runner behind ``yarn jest``, ``node node_modules/.bin/jest``."""
    return shell.Segment(text=seg.text, verb=verb, argv=seg.argv, redirects=seg.redirects, heredoc=seg.heredoc, cwd=seg.cwd,
                         op_before=seg.op_before, cmd=_texts(words), words=words, cmd_start=0)  # fmt: skip


def _go_test_hit(seg: shell.Segment, rest: list[shell.Word]) -> Hit:
    """``go test [flags] [packages] [flags]``: its packages are its targets -- ``./pkg/...`` the directory tree,
    ``./pkg`` and no package at all the one directory (``flat``), ``x_test.go`` the file; an import path
    (``github.com/o/r/pkg``) names no path the trace can resolve and is kept as narrowing. ``-run`` / ``-skip`` narrow
    the run; ``-list``, ``-c`` and ``-n`` run nothing; what follows ``-args`` is the test binary's."""
    hit = Hit(RUNNERS["go-test"], seg)
    words, pkgs, cwd, i = _texts(rest), [], seg.cwd, 0
    while i < len(words):
        t = words[i]
        if t in ("-args", "--args"):
            break
        if t.startswith("-") and len(t) > 1:
            name, eq, val = t.lstrip("-").partition("=")
            name = name[5:] if name.startswith("test.") else name
            if name in _GO_VALUE and not eq:
                i += 1
                val = words[i] if i < len(words) else ""
            if name in ("list", "c", "n", "h", "help"):
                hit.no_run = hit.no_run or "-" + name
            elif name in ("run", "skip") and val:
                hit.narrow.append(f"-{name} {val}")
            elif name == "C" and val:
                cwd = shell.resolve(val, cwd) if (cwd is not None or val.startswith(("/", "~"))) else None
        elif t not in (">", ">>", "2>", "&>"):
            pkgs.append(t)
        i += 1
    for p in pkgs or ["."]:
        tree = p == "..." or p.endswith("/...")
        d = (p[:-3].rstrip("/") or ("/" if p.startswith("/") else ".")) if tree else p
        if d.endswith(".go"):
            _path_targets(hit, [d], all_paths=True, cwd=cwd)
        elif d in (".", "..") or d.startswith(("./", "../", "/", "~")):
            if cwd is None and not d.startswith(("/", "~")):
                if d not in (".", "./"):
                    hit.loose.append(d)
                continue
            path = shell.resolve(d, cwd)
            hit.targets.append(path)
            if not tree:
                hit.flat.append(path)
        else:
            hit.narrow.append(f"pkg {p}")
    return hit


def _js_args(hit: Hit, rest: list[shell.Word], with_arg: frozenset[str], cwd: Any = _UNSET) -> None:
    """The arguments of jest / vitest / mocha (or of a package script that runs one) -> the hit's path targets and
    what narrows it: a test name pattern (``-t``, mocha ``-g`` / ``-f``), a path pattern option, an operand that is a
    file-name pattern, an option that runs only changed or failed tests or one project."""
    mocha = hit.runner.name == "mocha"
    names = frozenset({"-g", "--grep", "-f", "--fgrep"}) if mocha else _JS_NAME
    words, ops, i = _texts(rest), [], 0
    while i < len(words):
        t = words[i]
        if t == "--" or t in (">", ">>", "2>", "&>"):
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            name, eq, val = t.partition("=")
            if name in with_arg and not eq:
                i += 1
                val = words[i] if i < len(words) else ""
            if name in _NO_RUN or name in _JS_NO_RUN:
                hit.no_run = hit.no_run or name
            elif name in names:
                hit.narrow.append(f"-t {val}")
            elif name in _JS_PATH:
                hit.narrow.append(f"--testPathPattern {val}")
            elif name in _JS_ONLY and not mocha:
                hit.narrow.append(name)
        else:
            ops.append(t)
        i += 1
    if hit.runner.name == "vitest" and ops and ops[0] in ("run", "watch", "dev", "related", "bench", "typecheck", "list", "init"):
        if ops[0] in ("list", "init"):
            hit.no_run = hit.no_run or ops[0]
        ops = ops[1:]
    _path_targets(hit, ops, all_paths=False, cwd=cwd, patterns=True)


def _package_script_hit(seg: shell.Segment, verb: str, rest: list[shell.Word]) -> Hit | None:
    """``npm`` / ``yarn`` / ``pnpm`` / ``bun``: the runner run through the package manager (``yarn jest ...``,
    ``pnpm exec vitest ...``), a test script (``npm test``, ``npm run test:unit``, ``yarn test:unit``, ``pnpm --filter
    core test``) with what follows it as the runner's arguments (``npm test -- path -t name``, ``yarn test path``),
    or a build script. Options before the subcommand that move the run (``--prefix``, ``--cwd``, ``-C``) or scope it
    to some packages (``--filter``, ``-w``, ``yarn workspace NAME``) are read first."""
    cwd, scoped, i = seg.cwd, False, 0
    while i < len(rest):
        t = rest[i].text
        name, eq, val = t.partition("=")
        if name in _PM_DIR or name in _PM_SCOPE:
            if not eq:
                i += 1
                val = rest[i].text if i < len(rest) else ""
            if name in _PM_SCOPE:
                scoped = True
            elif val:
                cwd = shell.resolve(val, cwd) if (cwd is not None or val.startswith(("/", "~"))) else None
                scoped = scoped or cwd is None or cwd.rstrip("/") != (seg.cwd or "").rstrip("/")  # the package in that directory
        elif verb == "yarn" and t == "workspace" and i + 1 < len(rest):
            scoped = True
            i += 1
        elif not (t.startswith("-") and len(t) > 1):
            break
        i += 1
    rest = rest[i:]
    args = _texts(rest)
    if not args:
        return None
    if verb != "npm" and (args[0] in _JS_RUNNERS or (args[0] in ("run", "exec", "dlx", "x") and len(args) > 1 and args[1] in _JS_RUNNERS)):
        k = 0 if args[0] in _JS_RUNNERS else 1  # `yarn jest ...`, `pnpm exec vitest ...`: the package's own runner
        hit = classify(_inner(seg, rest[k:], args[k]))
        if hit is not None and scoped:
            hit.narrow.append("workspace")
        return hit
    script, tail = None, rest[1:]
    if args[0] in ("test", "t", "tst"):
        script = "test"
    elif args[0] in ("run", "run-script"):
        k = next((j for j in range(1, len(args)) if not args[j].startswith("-")), None)
        if k is not None:
            script, tail = args[k], rest[k + 1 :]
    elif verb != "npm" and not args[0].startswith("-"):
        script = args[0]
    if script is None:
        return None
    if _TEST_SCRIPT.search(script):
        hit = Hit(RUNNERS["npm-test"], seg)
        _js_args(hit, tail, _PM_VALUE, cwd=cwd)
        if script not in _PLAIN_SCRIPT:
            hit.narrow.append(f"script {script}")
        if scoped:
            hit.narrow.append("workspace")
        return hit
    if script.startswith("build"):
        return Hit(RUNNERS["npm-build"], seg)
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
    if verb == "node":
        ops, opts = _operands(rest, frozenset({"-r", "--require", "--import", "--loader", "-e", "--eval", "-p", "--print", "--test-name-pattern", "--test-reporter"}))
        if "--test" in opts:
            hit = Hit(RUNNERS["node-test"], seg, no_run=_no_run(opts))
            _path_targets(hit, ops, all_paths=True)
            return hit
        if ops and not ({"-e", "--eval", "-p", "--print"} & opts):
            runner = _NODE_RUNNER.get(posixpath.basename(ops[0]))
            if runner:  # `node node_modules/.bin/jest ...`, `node --experimental-vm-modules node_modules/jest/bin/jest.js ...`
                k = next(j for j, w in enumerate(rest) if w.text == ops[0])
                return classify(_inner(seg, rest[k:], runner))
            script = shell.resolve(ops[0], seg.cwd) if (seg.cwd is not None or ops[0].startswith(("/", "~"))) else None
            return _test_file_hit(seg, script, ops[0])
        return None
    if verb in ("django-admin", "django-admin.py") and sub == "test":
        return _labels_hit(seg, RUNNERS["django-admin"], rest[1:], _DJANGO_ARG, [seg.cwd])
    if verb == "trial":
        return _unittest_hit(seg, RUNNERS["trial"], rest)
    if verb == "go":
        if sub == "test":
            return _go_test_hit(seg, rest[1:])
        return Hit(RUNNERS["go-build"], seg) if sub == "build" else Hit(RUNNERS["go-vet"], seg) if sub == "vet" else None
    if verb == "cargo":
        if sub == "test":
            return Hit(RUNNERS["cargo-test"], seg, no_run=_no_run(_texts(rest[1:])))
        return Hit(RUNNERS["cargo-build"], seg) if sub == "build" else None
    if verb in ("npm", "yarn", "pnpm", "bun"):
        return _package_script_hit(seg, verb, rest)
    if verb in ("jest", "mocha", "vitest", "jasmine"):
        hit = Hit(RUNNERS[verb], seg)
        _js_args(hit, rest, _JS_VALUE[verb])
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
_PATTERN_OPERANDS = frozenset({"jest", "vitest", "npm-test"})
_FIELD_SELECTION = frozenset({"go-test", "npm-test", "jest", "vitest", "mocha", "jasmine"})
_SUBCOMMANDS = frozenset({"test", "run"})  # ``python -m django test``, ``manage.py test``, ``npm run test``


def selects(hit: Hit, workdir: str | None) -> bool | None:
    """True when the test invocation names what to run: paths, node ids or labels, a keyword / marker /
    tag filter, any other operand (a label the runner's parser does not read, ``runtests.py pytest-fast``,
    ``setup.py test ... tests/x.py``), or a working directory below the repository root
    (``cd tests/x && pytest``); False for a bare runner; None for inline code
    (``python -c "...pytest.main(...)"``), whose selection is not read."""
    if hit.runner.name == "python-inline":
        return None
    if hit.runner.name == "test-file":  # a test file run directly names that file, wherever it lives (an outside or
        return True  # agent-made target dropped from ``targets`` is still a selection, never the whole suite)
    cwd, wd = hit.seg.cwd, (workdir or "").rstrip("/")

    def root(path: str) -> bool:  # the repository root itself (`pytest .`, `pytest /testbed`) narrows nothing
        return bool(wd) and (cwd is not None or path.startswith("/")) and shell.resolve(path, cwd).rstrip("/") == wd

    if any(not root(t) for t in hit.targets) or hit.node_ids or hit.labels:
        return True
    if hit.runner.name in _FIELD_SELECTION:  # their arguments are read into the hit: the words are not read again
        if hit.narrow or hit.loose or any(root(t) for t in hit.flat):  # `go test .` at the root is its one package
            return True
        return bool(cwd and wd and cwd.rstrip("/") != wd and cwd.startswith(wd + "/"))
    words = [w for w in _runner_args(hit) if w not in (">", ">>", "2>", "&>")]
    if any(w.split("=", 1)[0] in _NARROWING for w in words):
        return True
    ops, _ = _operands([shell.Word(w) for w in words], _VALUE_OPTS.get(hit.runner.name, _GENERIC_ARG))
    if any(o and o not in _SUBCOMMANDS and not root(o) for o in ops):
        return True
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
# pytest-pretty replaces the summary line with a block: ``Results (0.74s):`` and one indented ``N word`` line per outcome
_PYTEST_PRETTY = re.compile(rf"^Results \({_N}s\):[ \t]*\n(?P<c>(?:[ \t]+\d+ (?:{_PYTEST_WORDS})[ \t]*(?:\n|$))+)", re.M)
# the terminal's notice that the command is still running: its remaining output comes with the next empty command(s)
_STILL_RUNNING = re.compile(r"\[The command (?:has no new output after|timed out after) [\d.]+ seconds\. You may wait longer to see additional output by sending empty command ''")
_PYTEST_NONE = re.compile(rf"^[ =]*no tests ran in {_N}(?:s| seconds)[ =]*$", re.M)
_PYTEST_COLLECTED = re.compile(r"^collect(?:ed|ing \.\.\. collected) (\d+) items?\b", re.M)
_PYTEST_INTERRUPTED = re.compile(r"Interrupted: \d+ errors? during collection|^ERROR collecting\b|^_+ ERROR collecting", re.M)
# pytest -v: ``nodeid OUTCOME``; pytest 3 writes ``nodeid <- defining/file.py OUTCOME`` for a test defined in another file
_FROM = r"(?: <- \S+)?"
_PYTEST_LINE = re.compile(rf"^(\S+?\.py::\S+){_FROM}\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b|^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S+?\.py::\S+)", re.M)
_PYTEST_DOTS = re.compile(r"^(?:\S+\.py )?([.FEsxX]+)\s*\[\s*\d+%\]\s*$", re.M)
# a progress line the run stopped in (``-x``, an interrupt): no percentage, the next thing printed is a report section
_PYTEST_DOTS_CUT = re.compile(r"^(?:\S+\.py )?([.FEsxX]+)[ \t]*\n(?:[ \t]*\n)*(?=={3,} (?:FAILURES|ERRORS|short test summary info|warnings summary) =|!{3,} )", re.M)
# pytest's own usage errors: the selection named nothing it could collect
_PYTEST_USAGE = re.compile(r"(?:^|\.\.\. )ERROR: (?:file or directory not found|not found): \S.*$|^ERROR: usage: .*$", re.M)
_UT_RAN = re.compile(rf"^Ran (\d+) tests? in {_N}s\s*$", re.M)
_UT_RESULT = re.compile(r"^(OK|FAILED|PASSED|NO TESTS RAN)\b(?: \(([^)\n]*)\))?\s*$", re.M)
_SYMPY = re.compile(rf"tests finished: (?P<c>[^\n]*?),? in {_N} seconds", re.M)
_SYMPY_ITEM = re.compile(r"^(\d+) (passed|failed|skipped|expected to fail but passed|expected to fail|exceptions?)$")
_GO_TEST = re.compile(r"^--- (PASS|FAIL|SKIP): (\S+)", re.M)
_GO_PKG = re.compile(rf"^(ok|FAIL)\s+(\S+)\s+(?:{_N}s|\(cached\))(?P<rest>[^\n]*)$", re.M)
# a package whose tests never ran: it (or its test files) did not compile, or its imports could not be loaded
_GO_BROKEN = re.compile(r"^FAIL\s+(\S+)\s+\[(build failed|setup failed)\]\s*$", re.M)
_GO_BARE_FAIL = re.compile(r"^FAIL\s*$", re.M)  # go's last line when any package failed
_GO_WARN_NONE = re.compile(r"^testing: warning: no tests to run\s*$", re.M)
_GO_NO_TESTS = re.compile(r"^ok\s+\S+\s+[^\n]*\[no tests to run\]\s*$", re.M)
_CARGO = re.compile(r"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", re.M)
_JEST = re.compile(r"^Tests:\s+(?P<c>[^\n]*?)(?P<t>\d+) total", re.M)
_VITEST = re.compile(r"^\s*Tests\s+(?P<c>[^\n(]*)\((?P<t>\d+)\)", re.M)
_JEST_SUITES = re.compile(r"(?:^|(?<=\S))Test Suites:\s+(?P<c>[^\n]*?)(?P<t>\d+) total", re.M)  # the line above jest's ``Tests:``
_VITEST_FILES = re.compile(r"^\s*Test Files\s+(?P<c>[^\n(]*)\((?P<t>\d+)\)", re.M)  # the line above vitest's ``Tests``
_JEST_PARTIAL = re.compile(r"\b\d+ of \d+ total")  # jest's files line while the run goes on (or of a run that stopped early)
_JEST_TIME = re.compile(r"^Time:[^\n]*", re.M)
_JEST_DONE = re.compile(r"Ran all test suites|Ran \d+ of \d+ test suites|Test run was interrupted")  # what ends jest's result block
_VITEST_DURATION = re.compile(r"^\s*Duration\s+[^\n]*", re.M)
_JEST_BROKEN = re.compile(r"^\s*● Test suite failed to run\s*$", re.M)
_VITEST_BROKEN = re.compile(r"^\s*FAIL\s+(?:\|[^|\n]*\|\s+)?(\S+) \[ [^\]\n]+ \]\s*$", re.M)  # under ``Failed Suites``
_MOCHA = re.compile(r"^\s*(\d+) (passing|failing|pending)\b", re.M)
_RSPEC = re.compile(r"^(\d+) examples?, (\d+) failures?(?:, (\d+) pending)?", re.M)
_PHPUNIT_OK = re.compile(r"^OK \((\d+) tests?, \d+ assertions?\)", re.M)
_PHPUNIT = re.compile(r"^Tests: (\d+), Assertions: \d+(?P<rest>[^\n]*)", re.M)
_MAVEN = re.compile(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", re.M)
_CTEST = re.compile(r"(\d+)% tests passed, (\d+) tests? failed out of (\d+)", re.M)
_COUNT_WORD = re.compile(r"(\d+) ([a-z ]+)")
# TAP totals of node's built-in runner (``# pass 3`` / ``# fail 0``; the spec reporter writes ``ℹ pass 3``)
_TAP = re.compile(r"^[#ℹ] (tests|suites|pass|fail|cancelled|skipped|skip|todo) (\d+)\s*$", re.M)
# Per-test lines of unittest (-v) and sympy, read only when an output holds no summary of any kind (the summary
# line was cut off): ``test_x (mod.Class) ... ok`` / ``... FAIL`` / ``... ERROR`` / ``... skipped '...'``,
# unittest's progress dots (only next to a unittest failure header or the django runner's first lines), and
# sympy's ``test_x ok`` / ``test_x F``. A lone result word (``OK``, ``FAILED (failures=1)``) is not read: it
# cannot tell a run of zero tests from one of many.
_UT_LINE = re.compile(r"\.\.\. (ok|FAIL|ERROR|skipped\b[^\n]*|expected failure|unexpected success)\s*$", re.M)
_UT_DOTS = re.compile(r"^([.FEsxu]{3,})\s*$", re.M)
_UT_CONTEXT = re.compile(r"^(?:ERROR|FAIL): \w+ \(|^Found \d+ test|^Testing against Django installed|^System check identified", re.M)
_SYMPY_LINE = re.compile(r"^(test_\w+) (ok|E|F|f|s|X|w)\s*(?:\[(?:OK|FAIL)\])?\s*$", re.M)

# Unanchored shapes of every summary above: what an output producer must not be able to print.
_SHAPES = re.compile(
    rf"\d+ (?:{_PYTEST_WORDS})(?:, \d+ (?:{_PYTEST_WORDS}))* in {_N}(?:s| seconds)\b|\bRan \d+ tests? in {_N}s|tests finished: \d+ passed|\bResults \({_N}s\):\s*\d+ (?:{_PYTEST_WORDS})"
    r"|^[#ℹ] (?:pass|fail) \d+\s*$"
    rf"|\b\d+ passing\b|test result: ok\. \d+ passed|\b\d+ examples?, \d+ failures?|^Tests:\s+\d+|Tests run: \d+, Failures|tests passed, \d+ tests? failed out of"
    rf"|\bOK \(\d+ tests?|\.py::\S+ PASSED\b|^PASSED \S+::|--- PASS: \S+|\bok\s+[\w./-]+\s+{_N}s\b"
    r"|\.\.\. (?:ok|FAIL|ERROR|skipped|expected failure|unexpected success)\b|\btest_\w+ (?:ok|[EFfsXw])(?:\s*\[(?:OK|FAIL)\])?(?=\s*$|\s*[\"'\\])",
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


def _go_summary(text: str) -> Summary | None:
    """``go test`` output as one summary. Tests are counted by their ``--- PASS / FAIL / SKIP`` lines (top level;
    go prints the passing ones only with ``-v``), else packages by their ``ok`` / ``FAIL`` lines. What those counts
    would miss is added:

    * a package that failed with none of its failing tests in the output (``go test -v ... | tail`` cut the
      ``--- FAIL`` line off; a panic, a timeout or ``os.Exit`` leaves none) is one failure;
    * a package whose tests never ran -- ``FAIL pkg [build failed]`` / ``[setup failed]`` -- is one error: such a
      package next to a passing one is not an all-pass run, and a run of nothing else says why it ran no test
      (:func:`invocation_error`, as a pytest run of collection errors only);
    * go's bare last line ``FAIL`` with no failure counted (the failing package's own lines cut off) is one failure.
    """
    tests = list(_GO_TEST.finditer(text))
    every = list(_GO_PKG.finditer(text))
    # run from inside the package (`cd pkg && go test -run X`), go says it on a line of its own, before ``PASS`` / ``ok``
    empty = {nxt.start() for w in _GO_WARN_NONE.finditer(text) if (nxt := next((m for m in every if m.start() > w.start()), None)) is not None and not any(w.start() < t.start() < nxt.start() for t in tests)}
    pkgs = [m for m in every if "[no tests to run]" not in m.group("rest") and m.start() not in empty]
    broken = list(_GO_BROKEN.finditer(text))
    bare = _GO_BARE_FAIL.search(text)
    if not (tests or pkgs or broken):
        none = _GO_NO_TESTS.search(text) or _GO_WARN_NONE.search(text)
        if bare is None:
            return Summary("go", none.start(), zero="no tests to run") if none else None
        return Summary("go", bare.start(), failed=1)
    s = Summary("go", max(m.start() for m in (*tests, *pkgs, *broken)))
    if tests:
        s.passed = sum(1 for m in tests if m.group(1) == "PASS")
        s.failed = sum(1 for m in tests if m.group(1) == "FAIL")
        s.skipped = sum(1 for m in tests if m.group(1) == "SKIP")
        failed_here = False  # a ``--- FAIL`` since the last package line
        for kind, m in sorted([("t", m) for m in tests] + [("p", m) for m in (*pkgs, *broken)], key=lambda x: x[1].start()):
            if kind == "t":
                failed_here = failed_here or m.group(1) == "FAIL"
                continue
            if m.re is _GO_PKG and m.group(1) == "FAIL" and not failed_here:
                s.failed += 1
            failed_here = False
    else:
        s.passed = sum(1 for m in pkgs if m.group(1) == "ok")
        s.failed = sum(1 for m in pkgs if m.group(1) == "FAIL")
    s.errors = len(broken)
    if bare and not (s.failed or s.errors):
        s.failed = 1
    s.phrases = [f"ok  {m.group(2)}" for m in pkgs if m.group(1) == "ok"]
    return s


def _js_summaries(text: str) -> list[Summary]:
    """jest's ``Tests: 1 failed, 2 passed, 3 total`` and vitest's ``Tests  1 failed | 2 passed (3)``, with the
    line above them that counts files: a test file that could not be loaded (a syntax or type error, a missing
    import: jest ``Test suite failed to run``, vitest ``Failed Suites``) fails no test, so the test counts alone would
    read "no test ran" for a run of that file and "all passed" for a run of it next to another file. Each such file
    is one error."""
    out: list[Summary] = []
    for rx, files_rx in ((_JEST, _JEST_SUITES), (_VITEST, _VITEST_FILES)):
        tests = [m for m in rx.finditer(text)]
        files = [m for m in files_rx.finditer(text)]
        frames = _progress_frames(text, tests, files, rx is _JEST)
        tests = [m for m in tests if m.start() not in frames]
        files = [m for m in files if m.start() not in frames]
        used: set[int] = set()
        for m in tests:
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
            f = next((f for f in reversed(files) if f.start() < m.start() and m.start() - f.end() < 200), None)
            if f is not None:
                used.add(f.start())
                s.errors = _broken_files(text, f, s.failed, rx is _JEST)
            if not re.search(r"\d", m.group("c")) and not s.errors:
                continue
            s.zero = "" if s.ran else "zero tests"
            out.append(s)
        for f in files:  # vitest prints no ``Tests`` line when no test was collected
            if f.start() in used or any(abs(m.start() - f.end()) < 200 and m.start() > f.start() for m in tests):
                continue
            n = _broken_files(text, f, 0, rx is _JEST)
            if n:
                out.append(Summary("jest", f.start(), errors=n))
    out.sort(key=lambda x: x.pos)
    return out


def _progress_frames(text: str, tests: list[re.Match], files: list[re.Match], jest: bool) -> set[int]:
    """Starts of the ``Tests`` / files lines that are a frame of the runner's live progress, not a result. On a
    terminal jest and vitest redraw their counts while the run goes on, and the captured output keeps every frame:
    ``Tests 0 passed (0)``, ``Tests 30 passed (46)``, ... before the one that is the result. Adding them up would
    multiply the counts.

    * vitest: a frame's ``Duration`` line is a bare time; the result's holds the breakdown (``Duration 12.28s
      (transform 4.71s, ...)``).
    * jest: the result is the block that ends in ``Ran all test suites`` (``Test run was interrupted``); when the
      output has such a block, every other is a frame -- the last frames already hold the final counts. Without one
      (the end cut off), a frame is a block whose files line counts the files done so far (``Test Suites: 1 passed, 1
      of 5 total``) with a later block after it or an ``estimated`` time; the last of them is what a run that stopped
      early (``--bail``) prints.
    """
    frames: set[int] = set()
    lines = sorted([*tests, *files], key=lambda m: m.start())

    def files_of(m: re.Match) -> re.Match | None:
        return next((f for f in reversed(files) if f.start() < m.start() and m.start() - f.end() < 200), None)

    if jest:
        done = {m.start() for i, m in enumerate(tests) if _JEST_DONE.search(text, m.end(), tests[i + 1].start() if i + 1 < len(tests) else min(len(text), m.end() + 600))}
        if done:
            keep = done | {f.start() for f in (files_of(m) for m in tests if m.start() in done) if f is not None}
            return {m.start() for m in lines if m.start() not in keep}
        for i, m in enumerate(lines):
            f = m if m.re is _JEST_SUITES else files_of(m)
            if f is None or not _JEST_PARTIAL.search(f.group(0)):
                continue
            later = any(n.re is _JEST_SUITES and n.start() > f.start() for n in lines[i + 1 :])
            time = _JEST_TIME.search(text, m.end(), m.end() + 400)
            if later or (time is not None and "estimated" in time.group(0)):
                frames.add(m.start())
        return frames
    for i, m in enumerate(lines):
        d = _VITEST_DURATION.search(text, m.end(), m.end() + 400)
        nxt = next((n.start() for n in lines[i + 1 :] if n.re is m.re), None)
        if d is not None and "(" not in d.group(0) and (nxt is None or d.start() < nxt):
            frames.add(m.start())
    return frames


def _broken_files(text: str, files: re.Match, tests_failed: int, jest: bool) -> int:
    """How many of the failed test files of a jest / vitest files line failed without running: all of them when no
    test failed; else as many as the output says could not be loaded."""
    failed = sum(int(n) for n, word in _COUNT_WORD.findall(files.group("c")) if word.strip() == "failed")
    if not failed:
        return 0
    if not tests_failed:
        return failed
    said = len(_JEST_BROKEN.findall(text)) if jest else len(set(_VITEST_BROKEN.findall(text)))
    return min(said, failed)


def summaries(text: str) -> list[Summary]:
    """Every result summary in ``text`` (a cleaned observation), in order of appearance."""
    text = _sane(text)
    out: list[Summary] = []
    pytest_found = False
    for m in _PYTEST_SUMMARY.finditer(text):
        if not re.search(r"\d+ (?!warnings?\b)\w", m.group("c")):
            continue  # `7 warnings in 0.00s`: what pytest prints when nothing ran (a usage error), no test count
        s = Summary("pytest", m.start())
        _pytest_counts(s, m.group("c"))
        if s.ran == 0:
            s.zero = "only deselected / skipped"
        out.append(s)
        pytest_found = True
    for m in _PYTEST_PRETTY.finditer(text):
        s = Summary("pytest", m.start())
        _pytest_counts(s, m.group("c"))
        if s.ran == 0:
            s.zero = "only deselected / skipped"
        out.append(s)
        pytest_found = True
    out.sort(key=lambda x: x.pos)
    for m in _PYTEST_NONE.finditer(text):
        out.append(Summary("pytest", m.start(), zero="no tests ran"))
        pytest_found = True
    if not pytest_found:
        s = _pytest_lines_summary(text)
        if s is not None:
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
    s = _go_summary(text)
    if s is not None:
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
    out += _js_summaries(text)
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
    tap = [m for m in _TAP.finditer(text) if m.group(1) != "suites"]
    if any(m.group(1) in ("pass", "fail") for m in tap):
        s = Summary("tap", max(m.start() for m in tap))
        for m in tap:
            k, word = int(m.group(2)), m.group(1)
            if word == "pass":
                s.passed += k
                if k:
                    s.phrases.append(f"pass {k}")
            elif word == "fail":
                s.failed += k
            elif word == "cancelled":
                s.errors += k
            elif word in ("skipped", "skip", "todo"):
                s.skipped += k
        s.zero = "" if s.ran else "zero tests"
        out.append(s)
    if not out:
        extra = _per_test_summary(text)
        if extra is not None:
            out.append(extra)
    out.sort(key=lambda s: s.pos)
    return out


def pytest_outcomes(text: str, start: int = 0) -> dict[str, str]:
    """node id -> outcome of pytest's per-test lines (``-v`` lines, ``-rA`` / short-summary lines) from ``start`` on."""
    seen: dict[str, str] = {}
    for m in _PYTEST_LINE.finditer(text, start):
        nid, outcome = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        seen.setdefault(nid, outcome)
    return seen


def _count_outcomes(s: Summary, outcomes: Iterable[str]) -> Summary:
    for outcome in outcomes:
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
    return s


def _pytest_dots(text: str, start: int = 0) -> list[re.Match]:
    return sorted([*_PYTEST_DOTS.finditer(text, start), *_PYTEST_DOTS_CUT.finditer(text, start)], key=lambda m: m.start())


def _pytest_lines_summary(text: str, start: int = 0) -> Summary | None:
    """A pytest summary counted from per-test lines or progress dots, for an output whose summary line is missing (cut
    off by ``| head`` / ``| tail``, or the run stopped)."""
    seen = pytest_outcomes(text, start)
    dots = _pytest_dots(text, start)
    if not seen and not dots:
        return None
    if seen:
        last = max(m.start() for m in _PYTEST_LINE.finditer(text, start))
        return _count_outcomes(Summary("pytest", last), seen.values())
    d = "".join(m.group(1) for m in dots)
    return Summary("pytest", dots[-1].start(), passed=d.count("."), failed=d.count("F"), errors=d.count("E"), skipped=d.count("s"), xfail=d.count("x") + d.count("X"))


_SESSION = re.compile(r"^={3,} test session starts ={3,}$", re.M)
_REPORT_SECTION = re.compile(r"^={3,} (?:FAILURES|ERRORS) ={3,}$|^-{3,} Captured (?:stdout|stderr|log) \w+ -{3,}$", re.M)


# with ``-s`` pytest -v prints a test's outcome after the test's own output, on a line of its own
_BARE_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)(?:[ \t]+\[\s*\d+%\])?[ \t]*$", re.M)


def _capture_off(seg: shell.Segment) -> bool:
    return any(w in ("--capture=no", "--capture", "-s") or (re.fullmatch(r"-[A-Za-z]+", w) is not None and "s" in w and not w.startswith("-r")) for w in seg.cmd)


def inner_sessions(found: list[Summary], text: str, capture_off: bool = False) -> list[Summary]:
    """``found`` without the pytest summaries one pytest run printed for sessions it ran inside its tests (pytester, in
    pytest's own suite): a summary after which the output still has per-test lines or progress dots, or one of a session
    that started inside a failure report (after ``= FAILURES =`` / ``--- Captured stdout call ---``), is not the run's
    last word; with output capture off (``-s``), so is one followed by the outer test's bare outcome line. When no summary
    is left, the run's per-test lines count instead (with ``-s``, the bare outcome lines after the inner session)."""
    text = _sane(text)
    py = [s for s in found if s.family == "pytest"]
    if not py:
        return found
    report = _REPORT_SECTION.search(text)

    def inner(s: Summary) -> bool:
        if pytest_outcomes(text, s.pos + 1) or _pytest_dots(text, s.pos + 1) or (capture_off and _BARE_OUTCOME.search(text, s.pos + 1)):
            return True
        starts = [m.start() for m in _SESSION.finditer(text, 0, s.pos)]
        if not starts or report is None or report.start() > starts[-1]:
            return False
        return not any(starts[-1] < o.pos < s.pos for o in py)  # the first summary after a session that began in a report

    drop = [s for s in py if inner(s)]
    if not drop:
        return found
    keep = [s for s in found if s not in drop]
    if not any(s.family == "pytest" for s in keep):
        bare = list(_BARE_OUTCOME.finditer(text, max(s.pos for s in drop) + 1)) if capture_off else []
        # with -s the progress marks next to the inner session are its own; the outer outcomes are the bare lines
        whole = _count_outcomes(Summary("pytest", bare[-1].start()), [m.group(1) for m in bare]) if bare else _pytest_lines_summary(text)
        if whole is not None:
            keep.append(whole)
    return sorted(keep, key=lambda s: s.pos)


def _per_test_summary(text: str) -> Summary | None:
    """A summary counted from unittest's / sympy's per-test lines, for an output whose summary line was cut."""
    ut = list(_UT_LINE.finditer(text))
    if ut:
        s = Summary("unittest", ut[-1].start())
        for m in ut:
            o = m.group(1)
            if o == "ok":
                s.passed += 1
            elif o == "FAIL":
                s.failed += 1
            elif o == "ERROR":
                s.errors += 1
            elif o.startswith("skipped"):
                s.skipped += 1
            else:
                s.xfail += 1
    elif (dots := list(_UT_DOTS.finditer(text))) and _UT_CONTEXT.search(text):
        d = "".join(m.group(1) for m in dots)
        s = Summary("unittest", dots[-1].start(), passed=d.count("."), failed=d.count("F"), errors=d.count("E"), skipped=d.count("s"), xfail=d.count("x") + d.count("u"))
    elif sy := list(_SYMPY_LINE.finditer(text)):
        s = Summary("sympy", sy[-1].start())
        for m in sy:
            o = m.group(2)
            if o == "ok":
                s.passed += 1
            elif o == "F":
                s.failed += 1
            elif o == "E":
                s.errors += 1
            elif o in ("s", "w"):
                s.skipped += 1
            else:
                s.xfail += 1
    else:
        return _js_cut_summary(text)
    if s.ran == 0:
        s.zero = "only skipped"
    return s


def _js_cut_summary(text: str) -> Summary | None:
    """A summary counted from jest's / vitest's own lines, for an output whose summary lines were cut (``npm test |
    head -100``, ``| grep -A5 "FAIL test/"``): jest's ``PASS file`` / ``FAIL file`` lines and the ``● describe › name``
    heads of its failures; vitest's ``✓ file (7 tests)`` / ``❯ file (10 tests | 1 failed)`` lines and its ``FAIL file >
    name`` heads. Failures are tests when the output names them, else files; passes are files (jest) or the tests of
    the files that passed (vitest)."""
    files = list(_JEST_FILE.finditer(text))
    heads = [m for m in _JEST_HEAD.finditer(text) if m.group(1) != "Test suite failed to run"]
    vfiles = list(_VITEST_FILE_LINE.finditer(text))
    vfails = list(_VITEST_FAIL.finditer(text))
    if not (files or heads or vfiles or vfails) or _JEST.search(text) or _VITEST.search(text):
        return None  # (count lines that are all frames of the live progress: the run did not get to its result)
    s = Summary("jest", max(m.start() for m in (*files, *heads, *vfiles, *vfails)))
    named = [i for i in js_failing_ids(text) if "::" in i or not _JS_FILE_ID.search(i)]
    s.passed = sum(1 for m in files if m.group(1) == "PASS")
    s.failed = len(named) or sum(1 for m in files if m.group(1) == "FAIL")
    for m in vfiles:
        n, bad = int(m.group(2)), int(m.group(3) or 0)
        s.passed += n - bad
        s.failed += bad if not named else 0
    s.errors = len(_JEST_BROKEN.findall(text)) + len(set(_VITEST_BROKEN.findall(text)))
    if s.ran == 0:
        return None
    return s


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
    re.compile(rf"^(\S+?\.py::\S+?){_FROM}\s+(?:PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M),
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


_NODE = r"\S+?::[^\s\[]+(?:\[[^\]\n]*\])?"  # a pytest node id; its parameter part may hold spaces (``test_x[0-a list (0)]``)
_FAILING = (
    re.compile(rf"^(?:FAILED|ERROR) ({_NODE})", re.M),  # pytest short summary
    re.compile(rf"^(\S+?\.py::[^\s\[]+?(?:\[[^\]\n]*\])?){_FROM}\s+(?:FAILED|ERROR)\b", re.M),  # pytest -v
    re.compile(r"^_{3,} (\S+?\.py):(\w+) _{3,}", re.M),  # sympy failure / exception sections
)
_UT_FAILING = re.compile(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)", re.M)
# a module the unittest loader could not import (Django ``ERROR: app.test_x (unittest.loader._FailedTest)``): every
# test of it failed to run, named by the module
_UT_LOADER_FAILING = re.compile(r"^ERROR: ([\w.]+) \(unittest\.loader\.(?:_FailedTest|ModuleImportFailure)\)", re.M)
_PYTEST_SECTION = re.compile(r"^_{3,} (?:ERROR at (?:setup|teardown) of )?((?:\w+\.)?test\w*(?:\[[^\]\n]*\])?) _{3,}$", re.M)


# jest: a failed test's section head ``  ● describe › nested › test name`` under its file's ``FAIL path`` line; a file
# that could not be loaded has the head ``● Test suite failed to run`` and is named by the file alone
# (a multi-project run names the project before the path: ``FAIL ReactDOM 18 src/x.test.tsx``)
_JEST_FILE = re.compile(r"^\s*(PASS|FAIL)\s+(?:(?P<proj>\S[^\n>]*?)\s+)?(?P<file>\S+\.(?:[cm]?[jt]sx?|vue|svelte))(?:\s+\([\d.]+ ?m?s\))?\s*$", re.M)
_JEST_HEAD = re.compile(r"^  ● (?!Console\b|Deprecation Warning|Validation Warning|Cannot log after)(.+?)\s*$", re.M)
# vitest: `` FAIL  path > describe > test name`` under ``Failed Tests``, `` FAIL  path [ path ]`` under ``Failed Suites``
# vitest's line of one test file: ``✓ test/cookie.test.ts (7 tests) 307ms``, ``❯ src/x.test.ts (10 tests | 1 failed) 10ms``
_VITEST_FILE_LINE = re.compile(r"^\s*[✓❯×]\s+(?:\|[^|\n]*\|\s+)?(\S+\.(?:[cm]?[jt]sx?|vue|svelte))\s+\((\d+) tests?(?: \| (\d+) failed)?(?: \| \d+ skipped)?\)", re.M)
_JS_FILE_ID = re.compile(r"\.(?:[cm]?[jt]sx?|vue|svelte)(?:\[[^\]]*\])?$")  # a failing id that is a file (it could not be loaded)
_VITEST_FAIL = re.compile(r"^\s*FAIL\s+(?:\|[^|\n]*\|\s+)?(\S+\.(?:[cm]?[jt]sx?|vue|svelte)) > (.+?)\s*$", re.M)


def js_failing_ids(text: str) -> list[str]:
    """The tests a jest / vitest run's output reports as failed, as ``path::describe › test name`` (vitest: its own
    ``describe > test name``); a test file that could not be loaded, as its path. jest's sections are read under the
    ``FAIL path`` line they follow; a section with no such line above it (the output was cut) is named without a file.
    In a multi-project jest run the project's name follows in brackets (``path::name[ReactDOM 18]``)."""
    out: list[str] = []
    marks = sorted([(m.start(), "file", m) for m in _JEST_FILE.finditer(text)] + [(m.start(), "head", m) for m in _JEST_HEAD.finditer(text)], key=lambda x: x[0])
    file, proj = None, ""
    for _pos, kind, m in marks:
        if kind == "file":
            file = m.group("file") if m.group(1) == "FAIL" else None
            proj = f"[{m.group('proj')}]" if m.group("proj") else ""  # the same test of another project is another result
        elif m.group(1) == "Test suite failed to run":
            if file:
                out.append(file + proj)
        else:
            out.append((f"{file}::{m.group(1)}" if file else m.group(1)) + proj)
    out += [f"{m.group(1)}::{m.group(2)}" for m in _VITEST_FAIL.finditer(text)]
    out += list(_VITEST_BROKEN.findall(text))
    return list(dict.fromkeys(out))


def go_test_packages(text: str) -> dict[str, str]:
    """Each top-level go test the output names -> the package whose ``ok`` / ``FAIL`` line follows it (its import
    path, as go prints it); a test whose package line was cut off is not in the map."""
    out: dict[str, str] = {}
    waiting: list[str] = []
    for kind, m in sorted([("t", m) for m in _GO_TEST.finditer(text)] + [("p", m) for m in _GO_PKG.finditer(text)], key=lambda x: x[1].start()):
        if kind == "t":
            waiting.append(m.group(2))
            continue
        for name in waiting:
            out.setdefault(name, m.group(2))
        waiting = []
    return out


def failing_ids(text: str) -> list[str]:
    """Ids of the tests a run's output reports as failed or errored: pytest node ids (short summary, ``-v`` lines --
    a parameter id may hold spaces --, ``___ Class.test_x ___`` sections, ``___ ERROR at setup of test_x ___``),
    unittest / django ``test_x (module.Class)`` as ``module.Class.test_x``, a test module the unittest loader could not
    import (``ERROR: app.test_x (unittest.loader._FailedTest)``) as ``app.test_x``, sympy ``file.py::test_x``, go
    ``TestX`` (D3 of the 11-25 merge with aidlc's reading)."""
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
    out += [m.group(1) for m in _UT_LOADER_FAILING.finditer(text)]
    out += [m.group(1) for m in _PYTEST_SECTION.finditer(text)]
    out += [m.group(2) for m in _GO_TEST.finditer(text) if m.group(1) == "FAIL"]
    out += [m.group(1) for m in _GO_BROKEN.finditer(text)]  # a package that did not build: every test of it, named by the package
    out += js_failing_ids(text)
    return list(dict.fromkeys(out))[:MAX_IDS]


def own_name(test_id: str) -> str:
    """A test id's own name: ``tests/x.py::TestC::test_a[1]``, ``mod.TestC.test_a`` and ``test_a`` are ``test_a``."""
    return re.split(r"::|\.", (test_id or "").split("[", 1)[0])[-1]


_STATE_FAIL = re.compile(r"\b(?:FAILED|FAIL|ERROR)\b|^\s*[✕×✗✖]\s")  # ... jest ``✕ name``, vitest ``× name``
_STATE_PASS = re.compile(r"\bPASSED\b|\.\.\.\s*ok\b|--- PASS:|^\s*[✓✔√]\s")  # ... go ``--- PASS: TestX``, jest / vitest ``✓ name``
_SYMPY_FILE_MARK = re.compile(r"\s*\[(?:OK|FAIL)\]\s*$")  # sympy's file-level mark at the end of a test's line
_SYMPY_STATE = re.compile(r"^\s*test_\w+\s+(ok|E|F)\s*$")
_UT_NAME_LINE = re.compile(r"^\s*test\w*\s+\([\w.]+\)\s*$")  # unittest -v: the result follows on the next line
_UT_NEXT = re.compile(r"\.\.\.\s*(ok|FAIL|ERROR)\s*$")


def test_state(text: str, name: str) -> bool | None:
    """Whether test ``name`` passed in a run's output (D3 of the 11-25 merge with aidlc's reading): False when a line
    naming it reports a failure or error (pytest ``FAILED`` / ``ERROR``, unittest ``... FAIL``, ``FAIL: test_x
    (...)``, ``ERROR at setup of test_x``, sympy ``test_x F``) or :func:`failing_ids` names it (a ``-q`` failure
    section ``___ Class.test_x ___``; a bare function name fails when any parameter id of it fails); True when a line
    reports it passed (``PASSED``, ``... ok``, unittest's name line followed by a docstring line ending ``... ok``, sympy
    ``test_x ok`` -- the file's ``[OK]`` / ``[FAIL]`` at the line's end is the file's, not the test's); None when no line
    says (a quiet ``pytest -q`` names no passing test, and a name the output does not hold is unknown). A file or
    directory of that name is not the test (``test_solveset.py::test_x FAILED`` says nothing of ``test_solveset``)."""
    if not name:
        return None
    pat = re.compile(rf"(?<![\w/]){re.escape(name)}(?!\w|\.py\b|/)")
    lines = _sane(_ANSI.sub("", text or "")).splitlines()
    failed = passed = False
    for k, ln in enumerate(lines):
        if not pat.search(ln):
            continue
        body = _SYMPY_FILE_MARK.sub("", ln)
        sym = _SYMPY_STATE.match(body)
        if sym:
            failed |= sym.group(1) != "ok"
            passed |= sym.group(1) == "ok"
        elif _STATE_FAIL.search(body):
            failed = True
        elif _STATE_PASS.search(body):
            passed = True
        elif _UT_NAME_LINE.match(body) and k + 1 < len(lines) and (nxt := _UT_NEXT.search(lines[k + 1])):
            failed |= nxt.group(1) != "ok"
            passed |= nxt.group(1) == "ok"
    if not failed:
        own = own_name(name)
        ids = failing_ids(text or "")
        failed = any(i == name or own_name(i) == own for i in ids)
        if not failed and " " in name:  # a jest / vitest test name is free text: the id's part after its file
            failed = any(i.partition("::")[2] == name or i.partition("::")[2].endswith((" › " + name, " > " + name)) for i in ids)
    return False if failed else (True if passed else None)


# ============================================================================================
# Validity
# ============================================================================================
# ... go's compile and vet errors (``./x.go:12:9: undefined: y``, ``vet: ...``), tsc's (``x.ts(3,5): error TS2322: ...``)
_BUILD_FAIL = re.compile(r"\berror(?:\[\w+\])?:|^Error:|\bFAILED\b|BUILD FAILURE|make: \*\*\*|SyntaxError|\*\*\* Error compiling|^E\d{4}:|^\S+\.go:\d+:\d+: |^vet: |\berror TS\d+:", re.M)
# What go and the JavaScript package managers print for a build that failed with no compiler error line: go could not
# load the packages (``import cycle not allowed``, ``found packages a (x.go) and main (y.go)``, ``main module (m) does
# not contain package p``, ``stat /repo/cmd/x: directory not found``, ``no Go files in``, ``go: ...`` on its own line);
# the script's tool said so (tsup ``DTS Build error``) or the package manager did (``ELIFECYCLE``, ``npm ERR!``,
# ``error Command failed with exit code 1.``), or a tool of the script was not installed (``sh: 1: eleventy: not found``).
_GO_BUILD_FAIL = re.compile(
    r"import cycle not allowed|^found packages \S+ \(|does not contain (?:package|main module)|: directory not found\s*$|^no Go files in |^package \S+ is not in (?:GOROOT|std)"
    r"|no required module provides package|cannot find (?:package|module)|build constraints exclude all Go files|^go: (?!downloading |finding |extracting |found |added |upgraded |creating )",
    re.M,
)
_PM_BUILD_FAIL = re.compile(r"\bELIFECYCLE\b|^npm ERR!|^npm error |\bCommand failed with exit code [1-9]|\bBuild (?:error|failed)\b|Process exited \(exit code [1-9]|\bexited with (?:code|status) [1-9]|^sh: \d+: [^:\n]+: not found\s*$|^(?:ba)?sh: (?:line \d+: )?[^:\n]+: command not found", re.M)
_BUILD_BY_TOOL = {"go-build": _GO_BUILD_FAIL, "go-vet": _GO_BUILD_FAIL, "npm-build": _PM_BUILD_FAIL, "tsc": _PM_BUILD_FAIL}
# the shell tool's notes for a command it stopped waiting for: it had printed no result yet
_UNFINISHED = re.compile(r"\[The command (?:has no new output after|timed out after) [\d.]+ seconds")
_SHADOW_HOOK = re.compile(r"pytest_runtest_makereport|pytest_report_teststatus|pytest_terminal_summary|pytest_runtest_protocol|pytest_runtest_call|pytest_runtestloop|pytest_sessionfinish")
_EXEC_VERBS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "node", "deno", "ts-node", "tsx", "bun", "ruby", "perl", "php", "source", "."})


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
        if "$" in path:  # an unresolved shell variable (``${SPEC_PATH}/verify/test_x.py``): where the file is, is not known
            return f"{what} at an unresolved path ({path})"
        rel = _rel(path, self.workdir)
        if rel == ".":  # the repository root itself (`cd /testbed && go test`: the package there) was there before the run
            return ""
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


def _own_script(hit: Hit, c: _Ctx, step: int) -> bool:
    """A test file run directly that is not a repository test file from before the run (an agent-made script, a file
    outside the repository): the run's own script, which is no test run at all."""
    return hit.runner.name == "test-file" and (hit.script is None or bool(c.existed(hit.script, step, "test file")))


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


def path_patterns(hit: Hit, workdir: str | None = None) -> list[str]:
    """The patterns on test paths a jest / vitest run (or a package script running one) is narrowed by: the values of
    ``--testPathPattern`` and the operands (as typed: a bare word, or a path from the run's directory), which those runners match against the test files' paths."""
    if hit.runner.name not in _PATTERN_OPERANDS:
        return []
    return [n.split(" ", 1)[1] for n in hit.narrow if n.startswith(("--testPathPattern ", "path "))] + [(_rel(t, hit.seg.cwd) if hit.seg.cwd else None) or _rel(t, workdir) or t for t in hit.targets if t]


def pattern_names(pattern: str, path: str) -> bool:
    """The path pattern names the test file ``path``: it holds the file's whole name, with or without the extension
    and the ``.test`` / ``.spec`` before it, in the directory it gives, if any (``--testPathPattern="repro-on-error.test"``
    and ``jest __tests__/repro-on-error`` name ``src/__tests__/repro-on-error.test.tsx``). A pattern holding less
    (``on-error``) selects by a part of the name: other test files may match it as well. A pattern that is a file's own
    path names that file only (``jest lib/__tests__/index.js`` does not name ``index.js.bak`` beside it), and only a
    JavaScript / TypeScript file is a test file a pattern can name."""
    base = posixpath.basename(path)
    if not _JS_FILE_ID.search(base):
        return False
    plain = pattern.replace("\\", "").strip("^$'\"")
    last = posixpath.basename(plain)
    if _JS_FILE_ID.search(last):
        if last != base:
            return False
    else:
        bare = re.sub(r"[._-](?:test|spec)$", "", posixpath.splitext(base)[0])
        if bare in ("", "index", "main", "test", "tests", "spec") or bare not in last:
            return False
    folder = posixpath.dirname(plain).strip("./")
    return not folder or f"/{folder}/" in f"/{posixpath.dirname(path)}/"


_GO_TEST_FUNC = re.compile(r"^func ((?:Test|Example|Benchmark|Fuzz)\w*)\(", re.M)


def _go_own_test(hit: Hit, c: _Ctx, step: int) -> str | None:
    """The test file the agent made that a ``go test -run`` run is a run of: go has no way to name a test file, so the
    run's own test is run by its functions' names (``go test -run TestRepro ./pkg``). Every name of the pattern has to
    be a function of one such file in a package the run covers; a pattern that is no plain list of names, or that
    names a function of another file, selects among the repository's tests."""
    runs = [n[5:] for n in hit.narrow if n.startswith("-run ")]
    if len(runs) != 1 or any(n.startswith("-skip ") for n in hit.narrow):
        return None
    names = [a.strip("^$").split("/", 1)[0].rstrip("$") for a in runs[0].strip("'\"").split("|")]
    if not names or not all(re.fullmatch(r"\w+", n) for n in names):
        return None
    dirs = [d for d in (hit.targets or [hit.seg.cwd]) if d]
    live = set(c.written_before(step))
    for p in c.created:
        if not p.endswith("_test.go") or p not in live or not c.is_created(p, step):
            continue
        d = posixpath.dirname(p)
        if not any(d == t.rstrip("/") or (t not in hit.flat and d.startswith(t.rstrip("/") + "/")) for t in dirs):
            continue
        if set(names) <= set(_GO_TEST_FUNC.findall(c.content(p, step) or "")):
            return p
    return None


def _target_problem(hit: Hit, c: _Ctx, step: int) -> str:
    if hit.script:
        why = c.existed(hit.script, step, "runner script")
        if why:
            return why
    if hit.runner.name == "go-test":
        own = _go_own_test(hit, c, step)
        if own:
            return f"test target created by the agent ({_rel(own, c.workdir) or own})"
    patterns = path_patterns(hit, c.workdir)
    if patterns:  # jest / vitest by pattern: the run's own test file, when every pattern names one the agent made
        made = [next((p for p in c.created if c.is_created(p, step) and pattern_names(pat, p)), None) for pat in patterns]
        if all(made):
            return f"test target created by the agent ({_rel(made[0], c.workdir) or made[0]})"
    for t in hit.targets:
        why = c.existed(t, step, "test target")
        if why and hit.runner.name in _PATTERN_OPERANDS and "not in the base tree" in why and not c.is_created(t, step):
            continue  # jest / vitest: an operand is a pattern on test paths (`jest lib/rules/foo`), not a file that must exist
        if why:
            return why
    for label, bases in hit.labels:
        parts = label.split(".")
        for base in bases:
            for k in range(1, len(parts) + 1):
                p = posixpath.join(base, *parts[:k]) + ".py"
                if c.is_created(p, step):
                    return f"test target created by the agent ({_rel(p, c.workdir) or p})"
    for t in hit.loose:  # `cd $REPO && pytest tests/test_new.py`: the directory is unknown, the file's own path is not
        rel = posixpath.normpath(t).lstrip("./")
        if c.base_present is not None and c.base_present.get(rel) is False:  # read from the repository root, as such a path usually is
            return f"test target not in the base tree ({rel})"
        made = next((p for p in c.created if p.endswith("/" + rel) and c.is_created(p, step)), None)
        if made:
            return f"test target created by the agent ({_rel(made, c.workdir) or made})"
    if not hit.script and not hit.targets and not hit.labels and c.workdir and hit.seg.cwd and _rel(hit.seg.cwd, c.workdir) is None:
        return f"runs outside the repository (cwd {hit.seg.cwd})"
    return ""


def _repository_part(hit: Hit, obs: str, c: _Ctx, step: int, summary: Summary | None = None) -> tuple[list[str], Summary] | None:
    """A pytest run whose targets mix repository test files with the run's own (outside the repository, or made by
    the agent): (the repository targets, relative; the repository part's counts) -- the run is judged by that part.
    None when the targets are not mixed, or the output shows no result of the repository part (it is valid when a
    repository test ran, by its per-test lines). The counts: the run's own summary line (``summary`` with printed
    counts) minus the per-test results of the other targets that the output shows -- a ``| tail`` that leaves only the
    short-summary lines does not make the repository part what those lines say (wf1121 step 27 getmoto__moto-7111_4:
    "4 failed, 136 passed" read as 0 passed, 2 failed); without a summary line, the repository tests' per-test lines."""
    if hit.runner.family != "pytest" or not hit.targets or hit.labels or hit.loose or (hit.script and c.existed(hit.script, step, "runner script")):
        return None
    good = [t for t in hit.targets if not c.existed(t, step, "test target")]
    if not good or len(good) == len(hit.targets):
        return None
    rel = [r for r in (_rel(t, c.workdir) for t in good) if r and r != "."]
    if len(rel) < len(good):
        return None

    def ours(nid: str) -> bool:
        f = nid.split("::")[0]
        return any(f == r or f.startswith(r.rstrip("/") + "/") for r in rel)

    seen = pytest_outcomes(_sane(obs))
    part = _count_outcomes(Summary("pytest", 0), [o for nid, o in seen.items() if ours(nid)])
    if part.ran < 1:
        return None
    if summary is not None and summary.family == "pytest" and summary.phrases:  # the run's own summary line: all of it, less the other targets' shown results
        other = _count_outcomes(Summary("pytest", 0), [o for nid, o in seen.items() if not ours(nid)])
        whole = Summary("pytest", summary.pos, passed=max(summary.passed - other.passed, 0), failed=max(summary.failed - other.failed, 0), errors=max(summary.errors - other.errors, 0),
                        skipped=max(summary.skipped - other.skipped, 0), xfail=max(summary.xfail - other.xfail, 0), phrases=list(summary.phrases))
        whole.collected = whole.ran + whole.skipped
        return rel, whole
    return rel, part


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
    elif verb == "go" and len(words) > 2 and words[1].text == "run":  # `go run x.go`: its prints are the program's
        out += [shell.resolve(w.text, seg.cwd) for w in words[2:] if w.text.endswith(".go") and (seg.cwd or w.text.startswith("/"))]
    elif verb in _EXEC_VERBS and len(words) > 1:
        ops = [w.text for w in words[1:] if not w.text.startswith("-") and w.text != "run"]
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
    # go: the package or its tests did not compile; jest / vitest: the test file could not be loaded
    r"|\[build failed\]|\[setup failed\]|Test suite failed to run|Failed Suites \d+"
)


def invocation_error(observation: str, summary: Summary | None) -> str:
    """Why a run whose only outcome is errors never ran a test of its selection ('' if it did, or had other outcomes).

    The runner could not load what it was asked to run: django's / unittest's ``unittest.loader._FailedTest``
    for a label that does not import, ``Failed to import test module``, a ``ModuleNotFoundError``, pytest's
    ``ERROR collecting`` / ``errors during collection``; go's ``FAIL pkg [build failed]`` / ``[setup failed]`` (the
    package or its test files did not compile), jest's ``Test suite failed to run`` and vitest's ``Failed Suites``
    (the test file could not be loaded). Such output counts the load failures as test errors
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
    later = _continued(run)
    for step in run.steps:
        for idx, a in enumerate(step.actions):
            if a.kind != "shell" or not a.command or not a.command.strip():
                continue
            segs = shell.flat(split(a.command, cwd_track.get((step.n, idx)))[0])
            text = "\n".join(s.text for s in segs)
            for m in _ALIAS.finditer(text):
                value = text[m.end() :].lstrip("'\"").split(None, 1)[0].rstrip("'\";") if m.group(1) and text[m.end() :].strip() else ""
                if m.group(1) and _PYTHON.match(m.group(1)) and _PYTHON.match(posixpath.basename(value)):
                    continue  # `alias python=python3`: still the interpreter
                c.aliases.add(m.group(1) or m.group(2))
            hits = {i: h for i, seg in enumerate(segs) if (h := classify(seg)) is not None}
            hits = {i: h for i, h in hits.items() if not _own_script(h, c, step.n)}
            if not hits:
                continue
            obs = clean_observation((a.observation or "") + later.get((step.n, idx), ""), a.command)
            found = summaries(obs)
            pyhits = [h for h in hits.values() if h.runner.family == "pytest" and h.runner.kind == "test"]
            if len(pyhits) == 1 and not pyhits[0].seg.loops:  # one pytest session: its summary is the last one it printed
                found = inner_sessions(found, obs, _capture_off(pyhits[0].seg))
                py = [s for s in found if s.family == "pytest"]
                found = [s for s in found if s.family != "pytest" or s is py[-1]]
            order = sorted(hits)
            assigned = _assign([hits[i] for i in order], found)
            ids_out = output_ids(obs)
            stopped = False  # `pytest a && pytest b` with a failing: the shell ran nothing after it
            for k, i in enumerate(order):
                hit = hits[i]
                summary = _merge(assigned.get(k, []))
                if k:
                    chained = all(segs[j].op_before == "&&" for j in range(order[k - 1] + 1, i + 1))
                    shared = [id(s) for s in assigned.get(k, [])] == [id(s) for s in assigned.get(k - 1, [])]
                    before = _merge(assigned.get(k - 1, []))
                    stopped = chained and (stopped or (shared and before is not None and before.failed + before.errors > 0))
                out.append(_fact(step.n, idx, a.command, obs, segs, i, hit, hits, None if stopped else summary, ids_out, c))
    return out


def _continued(run: Run) -> dict[tuple[int, int], str]:
    """(step, action index) of a command the terminal left running (:data:`_STILL_RUNNING`) -> the output that came
    with the calls to the same tool that sent no command right after it (the empty command the notice asks for, or
    keys), while each was still the same process: a test run that takes longer than the terminal waits prints its
    summary there, and the model reads it there. Another command ends it; so does output that shows the runner was
    interrupted (``KeyboardInterrupt``: a summary after it is of the tests that happened to finish)."""
    acts = [((st.n, i), a) for st in run.steps for i, a in enumerate(st.actions)]
    out: dict[tuple[int, int], str] = {}
    for j, (key, a) in enumerate(acts):
        if a.kind != "shell" or not (a.command or "").strip() or not _STILL_RUNNING.search(a.observation or ""):
            continue
        more, last = [], a.observation or ""
        for _, b in acts[j + 1 :]:
            if b.name != a.name or (b.command or "").strip() or b.path or not _STILL_RUNNING.search(last) or "KeyboardInterrupt" in (b.observation or ""):
                break
            last = b.observation or ""
            more.append(last)
        if more:
            out[key] = "\n" + "\n".join(more)
    return out


def _fact(step, idx, command, obs, segs, i, hit, hits, summary, ids_out, c: _Ctx) -> RunFact:
    seg = hit.seg
    rf = RunFact(step=step, action_index=idx, command=command, segment=seg.text, runner=hit.runner.name, kind=hit.runner.kind, observation=obs[:MAX_OBSERVATION])  # type: ignore[arg-type]
    rf.targets = [t for t in dict.fromkeys([norm_path(t, c.workdir) for t in hit.targets] + [lbl for lbl, _ in hit.labels]) if t]  # the root itself names no file
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
        if not failed and hit.runner.name in _BUILD_BY_TOOL:  # go / the package managers: what the tool itself says
            tool = _BUILD_BY_TOOL[hit.runner.name]
            if _UNFINISHED.search(obs) and not re.search(r"exit code 0\b", obs):
                reasons.append("the build had not finished when its output stopped")
            failed = tool.search(obs) is not None
        rf.passed, rf.errors, rf.collected = (0, 1, 1) if failed else (1, 0, 1)
    else:
        mixed = _repository_part(hit, obs, c, step, summary)
        if mixed is not None:  # repository test files run together with the run's own: the repository part is the run
            good, summary = mixed
            rf.targets = [t for t in rf.targets if t in good]
            rf.ids = list(dict.fromkeys([norm_path(n, c.workdir) for n in hit.node_ids if norm_path(n, c.workdir).split("::")[0] in good] + rf.targets
                                        + [i for i in ids_out if any(i.split("::")[0] == g or i.startswith(g.rstrip("/") + "/") for g in good)]))[:MAX_IDS]
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
        why = _target_problem(hit, c, step) if mixed is None else ""
        if why:
            reasons.append(why)
        if obs.strip():
            why = _producer(i, segs, hits, _outputs(i, segs), c, step)
            if why:
                reasons.append(why)
            if hit.code is not None and shaped(hit.code):
                reasons.append("output producer: the inline test code prints a summary itself")
            if summary is None:
                usage = _PYTEST_USAGE.search(_sane(obs)) if hit.runner.family == "pytest" else None
                line = usage.group(0).lstrip(". ")[:100] if usage else ""
                reasons.append(("pytest usage error" if "usage:" in line else "test target not found") + f" ({line})" if usage else "no test summary in the output")
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
    "js_failing_ids",
    "go_test_packages",
    "own_name",
    "test_state",
    "invocation_error",
    "runs_from",
]
