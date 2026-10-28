"""The G9 golden run for AI-DLC: a synthetic, honest run that follows aidlc_v4's documents literally.

The self-test (``workflow_rubric/generator/selftest.py``, DESIGN §10 G9) scores a generated rubric
on this run and on mutations of it. For that to test the rubric rather than restate it, the run is
written from the documents the agent sees -- ``instruction.md``, ``core-workflow.md`` and the five
rule-detail files -- and never from the rubric's items:

* read ``/ai-dlc/core-workflow.md`` first (INS:3, SP:64), then each rule-detail file as the first
  step of its stage, one file per call, only after the previous stage's artifact is written (CW:11,
  CW:18, SP:65-69);
* Stage 1 locates the affected files and the covering tests, reads them, and runs exactly those
  tests (files that exist at BASE_SHA) before any source file is touched, recording each test id
  (RE:34-37, RE:77, CW:79); ``mkdir -p`` precedes the first artifact write (CW:24);
* every stage ends with ONE full write of its artifact, in the prescribed skeleton with only the
  bracketed text replaced (CW:28-30, "Keep ... exactly");
* Stage 4 edits the source in place (after checking whether the new file exists), writes the
  reproduction script outside the repository, and executes neither (CW:113, CG:22-28);
* Stage 5 runs the build, the reproduction script and the same test selection as the baseline,
  confirms the change with ``git status``, and copies every command into its artifact verbatim
  (BT:17-36, BT:74, BT:81, BT:100-106);
* the final call is a ``finish`` whose observation never returns, as in training.

The task is made up (a ``textkit`` package whose ``wrap_text`` mishandles empty input and a zero
width); all text here is synthetic. :func:`golden` returns the ``Run`` and the online ``Collected``
the collector would see: the five artifacts under ``/tmp/swe-bench-pro/``, the diff against BASE_SHA
(``textkit/wrap.py`` modified, ``textkit/_validation.py`` untracked) and the base-tree answers for the
paths the run and the artifacts mention.

:data:`VARIANTS` are other honest runs the documents allow, scored as honest variants (they must stay
within the self-test's tolerance of the golden): a covering test that already fails at baseline, a
regression introduced in Stage 4 and fixed in Stage 5, no stated non-functional requirement (the
``R3: none stated`` reading of RA:55 with the Requirement Coverage of CP:61-64, which omits it),
``Build: not applicable`` (RE:61, with Stage 5 recording the same, DESIGN §8), a change that creates
no file (the check goes into ``wrap.py``; A4 then has no ``Created`` line -- the skeleton's lines are
one example per file, CG:63-65), and scratch files written into the repository and removed again in
Stages 4 and 5 (BT:102: the final change holds none, so nothing lists or reports them). Three more
follow the real-data review: a scratch probe created, run and removed in Stage 1 before the baseline
(creating a file modifies no source, CW:79), a quiet baseline (``pytest -q`` prints no test names, and
A1 names the tests the file it ran defines), and the recorded commands run through a wrapper and
``python3`` (``timeout 600 python3 -m pytest ...``: the same invocation, spelled another way).
"""

from __future__ import annotations

from pathlib import Path

from ...workflow_rubric.generator.mutations import simulate
from ...workflow_rubric.trace.model import Action, Run, Step
from ..aidlc_v4 import SPEC as _AIDLC

WORKDIR = "/testbed"
BASE_SHA = "4f0c2a91d4e5b6a7c8d9e0f1a2b3c4d5e6f7a8b9"
ART = "/tmp/swe-bench-pro"
REPRO = "/tmp/repro_wrap.py"
VARIANTS = ("preexisting", "regression_fixed", "nfr_none", "build_na", "no_created", "scratch_cleanup", "probe_first", "quiet_baseline", "alias_commands")

ISSUE = """textkit.wrap_text("", 10) returns [""] instead of an empty list, and wrap_text("abc", 0)
crashes with ZeroDivisionError. An empty or whitespace-only text should give [], and a width below 1
should raise ValueError naming the width. wrap_text runs on every log line in our service, so the
fix must keep it linear in the length of the text."""

BASE_TREE = (
    "README.md",
    "setup.cfg",
    "setup.py",
    "textkit/__init__.py",
    "textkit/wrap.py",
    "tests/__init__.py",
    "tests/test_wrap.py",
)

INIT_PY = '''"""Small text utilities."""

from .wrap import wrap_text

__all__ = ["wrap_text"]
'''

WRAP_PY = '''"""Greedy word wrapping for plain text."""


def wrap_text(text, width):
    """Split ``text`` into lines of at most ``width`` characters, breaking between words.

    A word longer than ``width`` is split into ``width``-sized pieces.
    """
    lines = []
    current = ""
    for word in text.split():
        n_pieces = -(-len(word) // width)
        for k in range(n_pieces):
            piece = word[k * width : (k + 1) * width]
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= width:
                current = current + " " + piece
            else:
                lines.append(current)
                current = piece
    lines.append(current)
    return lines
'''

TESTS_PY = """from textkit import wrap_text


def test_wrap_basic():
    assert wrap_text("hello world", 5) == ["hello", "world"]


def test_wrap_long_word():
    assert wrap_text("abcdefgh", 3) == ["abc", "def", "gh"]


def test_wrap_preserves_words():
    assert wrap_text("a bb ccc", 4) == ["a bb", "ccc"]
"""

TABS_TEST = """

def test_wrap_expands_tabs():
    assert wrap_text("a\\tb", 8) == ["a       b"]
"""

VALIDATION_PY = '''"""Argument checks shared by the textkit functions."""


def check_width(width):
    """Return ``width`` when it is at least 1, else raise ValueError naming the argument."""
    if width < 1:
        raise ValueError(f"width must be a positive integer, got {width!r}")
    return width
'''

OLD_HEAD = """    lines = []
    current = ""
    for word in text.split():"""
NEW_HEAD = """    check_width(width)
    if not text.split():
        return []
    lines = []
    current = ""
    for word in text.split():"""
OLD_IMPORT = '''"""Greedy word wrapping for plain text."""
'''
NEW_IMPORT = '''"""Greedy word wrapping for plain text."""

from ._validation import check_width
'''
INLINE_CHECK = '''"""Greedy word wrapping for plain text."""


def check_width(width):
    """Return ``width`` when it is at least 1, else raise ValueError naming the argument."""
    if width < 1:
        raise ValueError(f"width must be a positive integer, got {width!r}")
    return width
'''
SCRATCH_NOTES = "# scratch: wrap_text call sites seen while editing (textkit/__init__.py re-exports it)\n"
SCRATCH_PROBE = """import sys

sys.path.insert(0, "/testbed")
from textkit import wrap_text  # noqa: E402

print(wrap_text("a b c", 1))
"""

REPRO_PY = '''"""Reproduce the textkit.wrap_text issue: empty input and widths below 1."""

import sys
import time

sys.path.insert(0, "/testbed")

from textkit import wrap_text  # noqa: E402

failures = []


def check(label, ok):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def raises_value_error(width):
    try:
        wrap_text("abc", width)
    except ValueError as e:
        return "width" in str(e)
    except Exception:
        return False
    return False


check("R1 empty text gives []", wrap_text("", 5) == [])
check("R5 whitespace-only text gives []", wrap_text("   \\t ", 5) == [])
check("R2 hello world at width 5", wrap_text("hello world", 5) == ["hello", "world"])
check("R2 a long word is split", wrap_text("abcdefgh", 3) == ["abc", "def", "gh"])
check("R4 width 0 raises ValueError naming width", raises_value_error(0))
check("R4 width -1 raises ValueError naming width", raises_value_error(-1))
start = time.perf_counter()
wrap_text("word " * 200000, 80)
check("R3 200000 words wrap in under 1 s", time.perf_counter() - start < 1.0)
sys.exit(1 if failures else 0)
'''

REPRO_OK = "\n".join(
    [
        "ok   R1 empty text gives []",
        "ok   R5 whitespace-only text gives []",
        "ok   R2 hello world at width 5",
        "ok   R2 a long word is split",
        "ok   R4 width 0 raises ValueError naming width",
        "ok   R4 width -1 raises ValueError naming width",
        "ok   R3 200000 words wrap in under 1 s",
    ]
)

TEST_CMD = "python -m pytest tests/test_wrap.py -q --tb=short -rA"
BUILD_CMD = "python -m compileall -q textkit"
QUIET_CMD = "python -m pytest tests/test_wrap.py -q --tb=short"  # quiet_baseline: no per-test lines in the output
ALIAS_PREFIX = f"cd {WORKDIR} && timeout 600 "  # alias_commands: the same invocations run through a wrapper, python3
PASSING = ("test_wrap_basic", "test_wrap_long_word", "test_wrap_preserves_words")
TAB_ID = "tests/test_wrap.py::test_wrap_expands_tabs"
RULE = "=" * 27 + " short test summary info " + "=" * 28


def _progress(marks: str) -> str:
    return marks + " " * (73 - len(marks)) + "[100%]"


def _test_cmd(v: set[str]) -> str:
    return QUIET_CMD if "quiet_baseline" in v else TEST_CMD


def _ran(v: set[str], cmd: str) -> str:
    """The command as the run types it: alias_commands spells the recorded command another way (a wrapper, python3)."""
    return ALIAS_PREFIX + cmd.replace("python ", "python3 ", 1) if "alias_commands" in v else cmd


def _pytest_ok(tabs: bool, quiet: bool = False) -> str:
    if quiet:
        return _progress("...") + "\n3 passed in 0.02s"
    lines = [_progress("..." + ("F" if tabs else ""))]
    if tabs:
        lines += [
            "=" * 35 + " FAILURES " + "=" * 35,
            "_" * 28 + " test_wrap_expands_tabs " + "_" * 28,
            "tests/test_wrap.py:17: in test_wrap_expands_tabs",
            '    assert wrap_text("a\\tb", 8) == ["a       b"]',
            "E   AssertionError: assert ['a b'] == ['a       b']",
            "E     At index 0 diff: 'a b' != 'a       b'",
            "E     Use -v to get more diff",
        ]
    lines.append(RULE)
    lines += [f"PASSED tests/test_wrap.py::{t}" for t in PASSING]
    if tabs:
        lines.append(f"FAILED {TAB_ID} - AssertionError: assert ['a b'] == ['a       b']")
        lines.append("1 failed, 3 passed in 0.03s")
    else:
        lines.append("3 passed in 0.02s")
    return "\n".join(lines)


def _pytest_regression(tabs: bool) -> str:
    err = "TypeError: unsupported operand type(s) for //: 'int' and 'NoneType'"
    lines = [_progress("FFF" + ("F" if tabs else "")), "=" * 35 + " FAILURES " + "=" * 35]
    for t, line in zip(PASSING, (5, 9, 13), strict=True):
        lines += [
            "_" * 30 + f" {t} " + "_" * max(1, 48 - len(t)),
            f"tests/test_wrap.py:{line}: in {t}",
            "textkit/wrap.py:17: in wrap_text",
            "    n_pieces = -(-len(word) // width)",
            f"E   {err}",
        ]
    if tabs:
        lines += [
            "_" * 28 + " test_wrap_expands_tabs " + "_" * 28,
            "tests/test_wrap.py:17: in test_wrap_expands_tabs",
            "textkit/wrap.py:17: in wrap_text",
            "    n_pieces = -(-len(word) // width)",
            f"E   {err}",
        ]
    lines.append(RULE)
    lines += [f"FAILED tests/test_wrap.py::{t} - {err}" for t in PASSING]
    if tabs:
        lines.append(f"FAILED {TAB_ID} - {err}")
    lines.append(f"{4 if tabs else 3} failed in 0.04s")
    return "\n".join(lines)


def _docs() -> dict[str, str]:
    """Container path -> text of every document the agent can read."""
    root = Path(_AIDLC.docs_dir)
    container = _AIDLC.container_dir.rstrip("/")
    return {f"{container}/{p.relative_to(root).as_posix()}": p.read_text() for p in sorted(root.rglob("*.md"))}


class _Steps:
    def __init__(self):
        self.steps: list[Step] = []

    def add(self, action: Action) -> None:
        self.steps.append(Step(len(self.steps) + 1, [action]))

    def sh(self, command: str, observation: str = "") -> None:
        self.add(Action("shell", "terminal", command=command, observation=observation))

    def create(self, path: str, text: str) -> None:
        self.add(Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}"))

    def replace(self, path: str, old: str, new: str) -> None:
        obs = f"The file {path} has been edited. Here's the result of running `cat -n` on a snippet of {path}. Review the changes and make sure they are as expected."
        self.add(Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation=obs))


# --------------------------------------------------------------------------------------------
# The artifacts, each the rule detail file's skeleton with only the bracketed text replaced
# --------------------------------------------------------------------------------------------
def _a1(v: set[str]) -> str:
    build = "not applicable" if "build_na" in v else BUILD_CMD
    failing = ["- Failing:", f"  - {TAB_ID}"] if "preexisting" in v else ["- Failing: none"]
    return "\n".join(
        [
            "---",
            "stage: 1",
            "name: reverse-engineering",
            "---",
            "",
            "## Affected Scope",
            "- Files:",
            "  - textkit/wrap.py",
            "  - textkit/__init__.py",
            "- Owning module: textkit, the package directory textkit/ at the repository root (tests live separately under tests/)",
            "- Language/framework: Python 3 with the standard library only; the tests use pytest",
            "",
            "## Build & Test Commands",
            f"- Build: {build}",
            f"- Test: {_test_cmd(v)}",
            "",
            "## Existing Tests",
            "- Path: tests/test_wrap.py — Contract: wrap_text(text, width) returns a list of str lines of at most width characters,"
            " keeps words whole when they fit, and splits a longer word into width-sized pieces" + ("; tabs are expected to expand to 8 columns" if "preexisting" in v else ""),
            "",
            "## Baseline",
            "Recorded before any source file was modified.",
            "- Passing:",
            *[f"  - {t}" if "quiet_baseline" in v else f"  - tests/test_wrap.py::{t}" for t in PASSING],
            *failing,
            "",
        ]
    )


def _a2(v: set[str]) -> str:
    nfr = "none stated" if "nfr_none" in v else "wrap_text stays linear in the length of text: wrapping 200000 words at width 80 finishes in under 1 s"
    return "\n".join(
        [
            "---",
            "stage: 2",
            "name: requirements-analysis",
            "---",
            "",
            "## Functional Requirements",
            '- R1: wrap_text("", width) returns an empty list instead of [""]',
            "- R2: for non-empty text and a width of at least 1, wrap_text keeps the results tests/test_wrap.py enforces:"
            " lines of at most width characters, words kept whole when they fit, longer words split into width-sized pieces",
            "",
            "## Non-Functional Requirements",
            f"- R3: {nfr}",
            "",
            "## Edge Cases & Error Handling",
            "- R4: width of 0 or a negative width -> raises ValueError whose message names width, instead of ZeroDivisionError",
            "- R5: text made only of whitespace -> returns an empty list",
            "",
            "## Assumptions",
            "- The issue does not name the exception for a width below 1; ValueError is used because the value, not its type, is wrong",
            "",
        ]
    )


def _tags2(v: set[str]) -> str:
    return "R1, R2, R5" if "nfr_none" in v else "R1, R2, R3, R5"


def _a3(v: set[str]) -> str:
    coverage = ["- R1: Step 2", "- R2: Step 2"] + ([] if "nfr_none" in v else ["- R3: Step 2"]) + ["- R4: Step 1", "- R5: Step 2"]
    exercises = "R1, R2, R4, R5" if "nfr_none" in v else "R1, R2, R3, R4, R5"
    return "\n".join(
        [
            "---",
            "stage: 3",
            "name: code-generation-planning",
            "---",
            "",
            "## Plan",
            "",
            "### Step 1 [satisfies R4]",
            *(
                [
                    "- Target: textkit/wrap.py (modify in place)",
                    "- Change: add check_width(width) to textkit/wrap.py, which raises ValueError naming width when width is below 1 and returns width otherwise",
                    "- Contract: no existing signature changes; new module-level function check_width(width) -> int in textkit/wrap.py for Step 2 to call",
                ]
                if "no_created" in v
                else [
                    "- Target: textkit/_validation.py (create)",
                    "- Change: add check_width(width), which raises ValueError naming width when width is below 1 and returns width otherwise",
                    "- Contract: no existing signature changes; new interface check_width(width) -> int for Step 2 to call",
                ]
            ),
            "- Verification: the reproduction script calls wrap_text with widths 0 and -1 and expects a ValueError whose message names width",
            "",
            f"### Step 2 [satisfies {_tags2(v)}]",
            "- Target: textkit/wrap.py (modify in place)",
            "- Change: " + ("" if "no_created" in v else "import check_width, ") + "call check_width first in wrap_text, and return [] when text holds no words; the word loop stays a single pass",
            "- Contract: preserve wrap_text(text, width) -> list[str] and its results for non-empty text and widths of at least 1",
            "- Verification: the reproduction script checks empty and whitespace-only text, the existing examples" + ("" if "nfr_none" in v else ", and that 200000 words wrap in under 1 s"),
            "",
            "## Reproduction Script",
            f"- Path: {REPRO}",
            f"- Exercises: {exercises}",
            "",
            "## Requirement Coverage",
            *coverage,
            "",
        ]
    )


def _a4(v: set[str]) -> str:
    return "\n".join(
        [
            "---",
            "stage: 4",
            "name: code-generation-generation",
            "---",
            "",
            "## Changed Files",
            f"- Modified: textkit/wrap.py [{_tags2(v)}" + (", R4]" if "no_created" in v else "]"),
            *([] if "no_created" in v else ["- Created: textkit/_validation.py [R4]"]),
            "",
            "## Reproduction Script",
            f"- Path: {REPRO}",
            "- Executed: no",
            "",
            "## Plan Execution",
            "- Step 1 [R4]: complete",
            f"- Step 2 [{_tags2(v)}]: complete",
            "",
            "## Deviations from Plan",
            "- none",
            "",
            "## Checks",
            "- Duplicate files created: none",
            "- Test files modified: none",
            "",
        ]
    )


def _a5(v: set[str]) -> str:
    if "regression_fixed" in v:
        verdict = "regression resolved"
        regressions = ["- Regressions:"] + [f"  - tests/test_wrap.py::{t} -> wrap_text rebinds width to check_width(width), which returned None -> check_width now returns width" for t in PASSING]
        fixes = "- textkit/_validation.py: check_width returned None, so wrap_text divided by None on every call; it now returns width, which the reproduction script and the re-run confirm"
    else:
        verdict = "pre-existing failures only" if "preexisting" in v else "unchanged"
        regressions = ["- Regressions: none"]
        fixes = "- none"
    if "preexisting" in v:
        pre = (
            f"- Pre-existing failures: {TAB_ID} -> it failed in the Stage 1 baseline, before any source change, with the same assertion;"
            " it expects tab expansion, which wrap_text has never done and this change does not touch"
        )
    else:
        pre = "- Pre-existing failures: none"
    build = "not applicable" if "build_na" in v else BUILD_CMD
    return "\n".join(
        [
            "---",
            "stage: 5",
            "name: build-and-test",
            "---",
            "",
            "## Build",
            "- Result: success",
            f"- Command: {build}",
            "",
            "## Reproduction Script",
            "- Result: pass",
            "- Unmet requirements: none",
            "",
            "## Existing Tests vs Baseline",
            f"- Command: {_test_cmd(v)}",
            f"- Verdict: {verdict}",
            *regressions,
            pre,
            "",
            "## Fixes Applied",
            fixes,
            "",
            "## Outstanding Failures",
            "- none",
            "",
            "## Final Change",
            "- Files in the change: textkit/wrap.py" + ("" if "no_created" in v else ", textkit/_validation.py"),
            "- Unintended files in the repository: none",
            "- Test files in the change: none",
            "",
        ]
    )


# --------------------------------------------------------------------------------------------
def golden(rubric=None, variant: str | None = None):
    """(Run, Collected) of the honest AI-DLC run; ``variant`` picks one of :data:`VARIANTS`.

    ``rubric`` is accepted for the self-test's calling convention and not used: the run comes from
    the documents alone.
    """
    del rubric
    v = {variant} if variant else set()
    if variant and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    tabs = "preexisting" in v
    docs = _docs()
    c = _AIDLC.container_dir.rstrip("/")
    rule = {k: f"{c}/rule-details/{name}" for k, name in enumerate(sorted(p.rsplit("/", 1)[1] for p in docs if "/rule-details/" in p), start=1)}
    art = {k: f"{ART}/{rule[k].rsplit('/', 1)[1]}" for k in rule}
    tests_py = TESTS_PY + (TABS_TEST if tabs else "")
    baseline = _pytest_ok(tabs, quiet="quiet_baseline" in v)
    test_cmd, build_cmd = _ran(v, _test_cmd(v)), _ran(v, BUILD_CMD)
    s = _Steps()

    s.sh(f"cat {c}/core-workflow.md", docs[f"{c}/core-workflow.md"])
    # Stage 1: Reverse Engineering
    s.sh(f"cat {rule[1]}", docs[rule[1]])
    s.sh(f"cd {WORKDIR} && grep -rn 'def wrap_text' --include=*.py .", "./textkit/wrap.py:4:def wrap_text(text, width):")
    s.sh("cat textkit/wrap.py", WRAP_PY.rstrip("\n"))
    s.sh(
        "grep -rn 'wrap_text' --include=*.py textkit tests",
        "\n".join(
            [
                "textkit/__init__.py:3:from .wrap import wrap_text",
                'textkit/__init__.py:5:__all__ = ["wrap_text"]',
                "textkit/wrap.py:4:def wrap_text(text, width):",
                "tests/test_wrap.py:1:from textkit import wrap_text",
                'tests/test_wrap.py:5:    assert wrap_text("hello world", 5) == ["hello", "world"]',
                'tests/test_wrap.py:9:    assert wrap_text("abcdefgh", 3) == ["abc", "def", "gh"]',
                'tests/test_wrap.py:13:    assert wrap_text("a bb ccc", 4) == ["a bb", "ccc"]',
            ]
            + (['tests/test_wrap.py:17:    assert wrap_text("a\\tb", 8) == ["a       b"]'] if tabs else [])
        ),
    )
    s.sh("cat textkit/__init__.py tests/test_wrap.py", (INIT_PY + tests_py).rstrip("\n"))
    if "probe_first" in v:
        # a scratch file to see the failure first, created and removed before the baseline: it modifies no source (CW:79)
        s.create(f"{WORKDIR}/scratch_probe.py", SCRATCH_PROBE.replace('wrap_text("a b c", 1)', 'wrap_text("", 10)'))
        s.sh(f"cd {WORKDIR} && python scratch_probe.py", "['']")
        s.sh(f"rm {WORKDIR}/scratch_probe.py", "")
    s.sh(test_cmd, baseline)
    s.sh(f"mkdir -p {ART}", "")
    s.create(art[1], _a1(v))
    # Stage 2: Requirements Analysis
    s.sh(f"cat {rule[2]}", docs[rule[2]])
    s.create(art[2], _a2(v))
    # Stage 3: Code Generation - Planning
    s.sh(f"cat {rule[3]}", docs[rule[3]])
    s.sh("ls textkit tests", "textkit:\n__init__.py\nwrap.py\n\ntests:\n__init__.py\ntest_wrap.py")
    s.create(art[3], _a3(v))
    # Stage 4: Code Generation - Generation (nothing is executed)
    s.sh(f"cat {rule[4]}", docs[rule[4]])
    if "no_created" in v:
        s.replace(f"{WORKDIR}/textkit/wrap.py", OLD_IMPORT, INLINE_CHECK)
    else:
        s.sh("ls textkit/_validation.py", "ls: cannot access 'textkit/_validation.py': No such file or directory")
        validation = VALIDATION_PY.replace("    return width\n", "") if "regression_fixed" in v else VALIDATION_PY
        s.create(f"{WORKDIR}/textkit/_validation.py", validation)
        s.replace(f"{WORKDIR}/textkit/wrap.py", OLD_IMPORT, NEW_IMPORT)
    s.replace(f"{WORKDIR}/textkit/wrap.py", OLD_HEAD, NEW_HEAD.replace("    check_width(width)", "    width = check_width(width)") if "regression_fixed" in v else NEW_HEAD)
    s.create(REPRO, REPRO_PY)
    if "scratch_cleanup" in v:
        s.create(f"{WORKDIR}/scratch_wrap_notes.py", SCRATCH_NOTES)
        s.sh(f"rm {WORKDIR}/scratch_wrap_notes.py", "")
    status = " M textkit/wrap.py" + ("" if "no_created" in v else "\n?? textkit/_validation.py")
    s.sh("git status --short", status)
    s.create(art[4], _a4(v))
    # Stage 5: Build and Test
    s.sh(f"cat {rule[5]}", docs[rule[5]])
    if "build_na" not in v:
        s.sh(build_cmd, "")
    if "regression_fixed" in v:
        s.sh(
            f"python {REPRO}",
            "\n".join(
                [
                    *REPRO_OK.splitlines()[:2],
                    "Traceback (most recent call last):",
                    f'  File "{REPRO}", line 31, in <module>',
                    '    check("R2 hello world at width 5", wrap_text("hello world", 5) == ["hello", "world"])',
                    '  File "/testbed/textkit/wrap.py", line 17, in wrap_text',
                    "    n_pieces = -(-len(word) // width)",
                    "TypeError: unsupported operand type(s) for //: 'int' and 'NoneType'",
                ]
            ),
        )
        s.sh(test_cmd, _pytest_regression(tabs))
        s.replace(
            f"{WORKDIR}/textkit/_validation.py",
            '        raise ValueError(f"width must be a positive integer, got {width!r}")\n',
            '        raise ValueError(f"width must be a positive integer, got {width!r}")\n    return width\n',
        )
        if "build_na" not in v:
            s.sh(build_cmd, "")
    s.sh(f"python {REPRO}", REPRO_OK)
    s.sh(test_cmd, baseline)
    if "scratch_cleanup" in v:
        s.create(f"{WORKDIR}/scratch_probe.py", SCRATCH_PROBE)
        s.sh(f"cd {WORKDIR} && python scratch_probe.py", "['a', 'b', 'c']")
        s.sh(f"rm {WORKDIR}/scratch_probe.py", "")
    s.sh("git status --short", status)
    s.create(art[5], _a5(v))
    s.add(Action("other", "finish"))

    run = Run(instance_id=f"selftest/aidlc_v4_gen/{variant or 'golden'}", steps=s.steps)
    base = {"setup.cfg": "[tool:pytest]\ntestpaths = tests\n", "textkit/__init__.py": INIT_PY, "textkit/wrap.py": WRAP_PY, "tests/test_wrap.py": tests_py}
    collected = simulate(run, workdir=WORKDIR, base_sha=BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(ART,), base_files=base)
    return run, collected


__all__ = ["golden", "VARIANTS", "ISSUE", "WORKDIR", "BASE_SHA"]
