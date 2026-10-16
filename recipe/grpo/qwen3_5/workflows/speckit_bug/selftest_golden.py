"""The G9 golden run for speckit_bug: a synthetic, honest run that follows the package's documents literally.

The self-test (``workflow_rubric/generator/selftest.py``, DESIGN §10 G9) scores a generated rubric on this
run and on mutations of it. For that to test the rubric rather than restate it, the run is written from what
the agent sees -- ``instruction.md``, ``core-workflow.md`` and the three stage documents -- and never from the
rubric's items:

* read ``/speckit/core-workflow.md`` first (INS:3, SP:65), then each stage document as the first step of its
  stage, one per call (CW:15, INS:5-6);
* assess: the issue's symbols searched and the suspected code read (AS:24-35), ``mkdir -p`` of the report
  directory (CW:44), ``assessment.md`` written once in the skeleton of AS:52-107 with only the ``<...>`` spans
  replaced, the issue's link recorded ``[UNVERIFIED — not fetched]`` (AS:18-20), nothing written to the
  repository (AS:116);
* fix: ``assessment.md`` read in full (FX:20); before any code edit (FX:30-33) the issue's examples and the
  assessment's reproduction copied into a check under ``BUG_DIR/checks/`` (FX:31), the check run and seen
  failing (FX:32), the existing tests of the file to change run as the baseline (FX:33); then the source edited
  in place (FX:35), the check left as it was (FX:36) and run again with the covering tests (FX:41), ``fix.md``
  written once (FX:46-95) with the round's fields (round 1, no previous verification), the check's before /
  after results in Checks Added and the baseline's before / after in Baseline: Existing Tests (FX:72-81);
* test: ``assessment.md`` and the fix report read (TS:21), the reproduction check and the repository tests run
  (TS:28-38), ``git status`` to confirm the change, ``test.md`` written once (TS:50-89) with every command as
  it was run, the repository untouched (TS:104); a ``verified`` Result ends the workflow (CW:25);
* the final call is a ``finish`` whose observation never returns, as in training.

The task is made up (a ``tinyconf`` package whose ``parse_bool`` reads every non-empty string as true); all
text is synthetic. :func:`golden` returns the ``Run`` and the online ``Collected`` the collector would see: the
reports under ``/tmp/speckit/bugs/issue/`` (and the check under ``checks/``), the diff against BASE_SHA
(``tinyconf/values.py`` modified) and the base-tree answers.

:data:`VARIANTS` are other honest runs the documents allow: ``two_rounds`` -- round 1's fix handles only
``"false"``, its verification report says ``failed`` (the check still fails for ``"0"`` / ``"no"``), so round 2
reads 02-fix.md again with the previous reports (FX:21, TS:97-98), fixes the rest and verifies (CW:26-27,
``fix-2.md`` / ``test-2.md``; round 1's check and baseline stand, FX:34); ``round2_check`` -- as ``two_rounds``,
and round 2 adds a check for the ValueError, run and seen failing on round 1's code before round 2's change
(FX:34); ``no_links`` -- an issue without a URL (nothing to mark); ``lint_skipped`` -- the
project has no linter, so the Lint row is ``skipped`` with a reason and no command (TS:38); ``heredoc_writes``
-- every report written with a shell heredoc instead of the editor (the tool is the agent's choice).
"""

from __future__ import annotations

from pathlib import Path

from ...workflow_rubric.generator.mutations import simulate
from ...workflow_rubric.trace.model import Action, Run, Step
from . import SPEC as _SPEC

WORKDIR = "/testbed"
BASE_SHA = "5e2b9d40c1a7f3e8b6d5c4a3f2e1d0c9b8a7f6e5"
C = _SPEC.container_dir.rstrip("/")
BUG = "/tmp/speckit/bugs/issue"
CHECK = f"{BUG}/checks/repro_parse_bool.py"
DATE = "2026-10-14"
VARIANTS = ("two_rounds", "round2_check", "no_links", "lint_skipped", "heredoc_writes")
CHECK2 = f"{BUG}/checks/unknown_word_raises.py"
URL = "https://tracker.example.org/tinyconf/issues/12"

ISSUE = """tinyconf.parse_bool("false") returns True, and so do "0" and "no": every non-empty string is
read as true. Only "true", "1", "yes" and "on" (any case) should be true, and "false", "0", "no", "off"
false; anything else should raise ValueError naming the text. Reported at
https://tracker.example.org/tinyconf/issues/12"""

BASE_TREE = ("README.md", "setup.py", "tinyconf/__init__.py", "tinyconf/values.py", "tests/__init__.py", "tests/test_values.py")

INIT_PY = '''"""Small configuration helpers."""

from .values import parse_bool, parse_int

__all__ = ["parse_bool", "parse_int"]
'''

VALUES_PY = '''"""Typed values read from configuration text."""


def parse_int(text):
    """``text`` as an int, surrounding whitespace ignored."""
    return int(text.strip())


def parse_bool(text):
    """``text`` as a bool."""
    return bool(text)
'''

OLD_BOOL = '''def parse_bool(text):
    """``text`` as a bool."""
    return bool(text)
'''
HALF_BOOL = '''def parse_bool(text):
    """``text`` as a bool."""
    if text == "false":
        return False
    return bool(text)
'''
NEW_BOOL = '''_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def parse_bool(text):
    """``text`` as a bool: true / 1 / yes / on and false / 0 / no / off, in any case; anything else is an error."""
    word = text.strip().lower()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    raise ValueError(f"not a boolean: {text!r}")
'''

TESTS_PY = """from tinyconf import parse_bool, parse_int


def test_parse_int_strips():
    assert parse_int(" 42 ") == 42


def test_parse_bool_true_words():
    assert parse_bool("true") is True
    assert parse_bool("1") is True


def test_parse_bool_yes():
    assert parse_bool("yes") is True
"""

CHECK_PY = '''"""Check for the tinyconf.parse_bool issue: false words, case, and garbage."""

import sys

sys.path.insert(0, "/testbed")

from tinyconf import parse_bool  # noqa: E402

failures = []


def check(label, ok):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def raises(text):
    try:
        parse_bool(text)
    except ValueError as e:
        return repr(text) in str(e)
    return False


for word in ("false", "0", "no", "off", "FALSE", " No "):
    check(f"{word!r} is False", parse_bool(word) is False)
for word in ("true", "1", "yes", "on", "TRUE"):
    check(f"{word!r} is True", parse_bool(word) is True)
check("'maybe' raises ValueError naming it", raises("maybe"))
sys.exit(1 if failures else 0)
'''

CHECK2_PY = '''"""Check for the tinyconf.parse_bool issue: anything else should raise ValueError naming the text."""

import sys

sys.path.insert(0, "/testbed")

from tinyconf import parse_bool  # noqa: E402

try:
    parse_bool("maybe")
except ValueError as e:
    ok = "'maybe'" in str(e)
else:
    ok = False
print(("ok   " if ok else "FAIL ") + "'maybe' raises ValueError naming it")
sys.exit(0 if ok else 1)
'''

_FALSE_WORDS = ("false", "0", "no", "off", "FALSE", " No ")
_TRUE_WORDS = ("true", "1", "yes", "on", "TRUE")


def _check_out(stage: str) -> tuple[str, bool]:
    """The check script's output before the fix, after the half fix, after the full fix."""
    lines, ok = [], True
    for w in _FALSE_WORDS:
        good = stage == "full" or (stage == "half" and w == "false")
        ok &= good
        lines.append(("ok   " if good else "FAIL ") + f"{w!r} is False")
    lines += [f"ok   {w!r} is True" for w in _TRUE_WORDS]
    good = stage == "full"
    ok &= good
    lines.append(("ok   " if good else "FAIL ") + "'maybe' raises ValueError naming it")
    return "\n".join(lines), ok


TEST_CMD = "python -m pytest tests/test_values.py -q"
CHECK_CMD = f"python {CHECK}"
CHECK2_CMD = f"python {CHECK2}"
PYTEST_OK = "...                                                                      [100%]\n3 passed in 0.02s"
FLAKE = "flake8 tinyconf"


def _docs() -> dict[str, str]:
    """Container path -> text of every document the agent can read."""
    root = Path(_SPEC.docs_dir)
    return {f"{C}/{p.relative_to(root).as_posix()}": p.read_text() for p in sorted(root.rglob("*.md"))}


class _Steps:
    def __init__(self, heredoc: bool = False):
        self.steps: list[Step] = []
        self.heredoc = heredoc

    def add(self, action: Action) -> None:
        self.steps.append(Step(len(self.steps) + 1, [action]))

    def sh(self, command: str, observation: str = "") -> None:
        self.add(Action("shell", "terminal", command=command, observation=observation))

    def create(self, path: str, text: str) -> None:
        self.add(Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}"))

    def report(self, path: str, text: str) -> None:
        if self.heredoc:
            self.sh(f"cat > {path} << 'EOF'\n{text.rstrip(chr(10))}\nEOF", "")
        else:
            self.create(path, text)

    def replace(self, path: str, old: str, new: str) -> None:
        obs = f"The file {path} has been edited. Here's the result of running `cat -n` on a snippet of {path}. Review the changes and make sure they are as expected."
        self.add(Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation=obs))


# --------------------------------------------------------------------------------------------
# The reports, each its stage document's skeleton with only the <...> spans replaced
# --------------------------------------------------------------------------------------------
def _assessment(v: set[str]) -> str:
    link = [] if "no_links" in v else ["", f"- {URL} [UNVERIFIED — not fetched]"]
    return "\n".join(
        [
            "# Bug Assessment: parse_bool reads every non-empty string as true",
            "",
            "- **Slug**: issue",
            f"- **Created**: {DATE}",
            "- **Source**: task issue description",
            "- **Verdict**: valid",
            "- **Severity**: high",
            "",
            "## Report (verbatim or summarized)",
            "",
            '> tinyconf.parse_bool("false") returns True, and so do "0" and "no": every non-empty string is read as true.',
            '> Only "true", "1", "yes" and "on" (any case) should be true, and "false", "0", "no", "off" false; anything',
            "> else should raise ValueError naming the text.",
            *link,
            "",
            "## Symptom",
            "",
            'parse_bool("false"), parse_bool("0") and parse_bool("no") return True; they should return False, and an'
            " unknown word should raise ValueError instead of being read as true.",
            "",
            "## Reproduction",
            "",
            "1. `from tinyconf import parse_bool`",
            '2. Call `parse_bool("false")`, `parse_bool("0")` and `parse_bool("no")`.',
            "3. Each returns True; `parse_bool(\"maybe\")` returns True instead of raising ValueError.",
            "",
            "## Suspected Code Paths",
            "",
            "- `tinyconf/values.py:9` — `parse_bool` returns `bool(text)`, which is True for any non-empty string",
            "- `tinyconf/__init__.py:3` — re-exports `parse_bool`; no logic of its own",
            "",
            "## Root Cause Hypothesis",
            "",
            "parse_bool converts the raw string with bool(), so only the empty string is false. Confidence: high.",
            "",
            "## Proposed Remediation",
            "",
            "**Preferred**: map the stripped, lower-cased text against the two word sets the issue gives (true / 1 / yes /"
            " on and false / 0 / no / off) and raise ValueError naming the text for anything else.",
            "",
            "**Alternatives** (optional):",
            "- Use distutils.util.strtobool: it is deprecated and removed in Python 3.12, so it is not an option.",
            "",
            "**Files likely to change**:",
            "- `tinyconf/values.py`",
            "",
            "**Checks to run**:",
            f"- `{CHECK}`: the false words, case and whitespace, and the ValueError for an unknown word",
            f"- `{TEST_CMD}`: the existing tests of tinyconf/values.py",
            "",
            "## Risks & Considerations",
            "",
            "- Callers that relied on any non-empty string being true (e.g. 'enabled') now get ValueError.",
            "- No performance or security impact.",
            "",
            "## Open Questions",
            "",
            "- none",
            "",
        ]
    )


def _fix(v: set[str], rnd: int) -> str:
    half = "two_rounds" in v and rnd == 1
    if half:
        summary = 'parse_bool now returns False for the exact word "false"; the other false words are not handled yet.'
        status, change = "partial", 'return False for "false"'
    elif rnd == 2:
        summary = "parse_bool now maps the true and false word sets case-insensitively and raises ValueError for anything else, as round 1's verification report asked."
        status, change = "applied", "word sets, case folding, ValueError for unknown text"
    else:
        summary = "parse_bool now maps the true and false word sets case-insensitively and raises ValueError for anything else."
        status, change = "applied", "word sets, case folding, ValueError for unknown text"
    prev = "none" if rnd == 1 else "./test.md"
    if rnd == 2:
        deviations = [
            "Round 1 handled only the exact word \"false\"; test.md showed \"0\", \"no\", \"off\", case and the ValueError still failing. This round implements the assessment's preferred remediation in full.",
        ]
    else:
        deviations = []
    before = "fail: FAIL 'false' is False" if rnd == 1 else "fail: FAIL '0' is False"
    after = "fail" if half else "pass"
    checks = [
        "| Check | What it pins down | Before the change | After the change |",
        "|-------|-------------------|-------------------|------------------|",
        f"| `checks/{CHECK.rsplit('/', 1)[1]}` | the issue's examples: the false words with case and whitespace, the true words, ValueError for an unknown word | {before} | {after} |",
    ]
    if rnd == 2 and "round2_check" in v:
        checks.append(f"| `checks/{CHECK2.rsplit('/', 1)[1]}` | the issue's ValueError for an unknown word, added this round | fail: FAIL 'maybe' raises ValueError naming it | pass |")
    if rnd == 1:
        baseline = [
            "- Test files: `tests/test_values.py` (imports tinyconf.values)",
            f"- `{TEST_CMD}` before the change: 3 passed, 0 failed; after the change: 3 passed, no new failure",
        ]
    else:
        baseline = [
            "- Test files: `tests/test_values.py` (round 1's baseline stands)",
            f"- `{TEST_CMD}` before the change: 3 passed, 0 failed (round 1); after the change: 3 passed, no new failure",
        ]
    return "\n".join(
        [
            "# Bug Fix: parse_bool reads every non-empty string as true",
            "",
            "- **Slug**: issue",
            f"- **Fixed**: {DATE}",
            "- **Assessment**: ./assessment.md",
            f"- **Round**: {rnd}",
            f"- **Previous verification**: {prev}",
            f"- **Status**: {status}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Changes",
            "",
            "| File | Change | Notes |",
            "|------|--------|-------|",
            f"| `tinyconf/values.py` | modified | {change} |",
            "",
            "## Checks Added",
            "",
            *checks,
            "",
            "## Baseline: Existing Tests",
            "",
            *baseline,
            "",
            "## Local Verification",
            "",
            f"- Commands run: `{CHECK_CMD}` → {'still fails for the other false words' if half else 'all 12 checks ok'}; `{TEST_CMD}` → 3 passed",
            "- Manual checks: none",
            "",
            "## Deviations from Assessment",
            "",
            *deviations,
            *([""] if deviations else []),
            "## Follow-ups",
            "",
            "- Mention the accepted words in the README's configuration section.",
            "",
        ]
    )


def _test(v: set[str], rnd: int) -> str:
    failed = "two_rounds" in v and rnd == 1
    fix_ref = "./fix.md" if rnd == 1 else "./fix-2.md"
    lint = (
        "| Lint / type-check | none configured | skipped | the project has no linter or type checker configured |"
        if "lint_skipped" in v
        else f"| Lint / type-check | `{FLAKE}` | pass | no findings |"
    )
    if failed:
        summary = 'The bug still reproduces for "0", "no", "off", mixed case and unknown words; only "false" is fixed. The existing tests pass.'
        repro = f"| Reproduction (post-fix) | `{CHECK_CMD}` | fail | 6 of 12 checks fail |"
        fromfix = f"| Checks from the fix | `{CHECK_CMD}` | fail | the same script: the false words other than \"false\" and the ValueError fail |"
        excerpt = _check_out("half")[0].splitlines()[1]
        recommendation = "Reopen — symptom still reproduces; the next round's fix must handle every false word, case and whitespace, and raise ValueError for unknown text."
        risks = ["- Only the exact lower-case word is handled."]
    else:
        summary = "The bug no longer reproduces: every false word returns False and unknown text raises ValueError. The existing tests pass; no regression."
        repro = f"| Reproduction (post-fix) | `{CHECK_CMD}` | pass | all 12 checks ok |"
        fromfix = f"| Checks from the fix | `{CHECK_CMD}` | pass | the check added in the fix |"
        excerpt = "ok   'maybe' raises ValueError naming it"
        recommendation = "Close the bug — verified end-to-end."
        risks = ["- Callers passing words outside the two sets now get ValueError (intended by the issue)."]
    return "\n".join(
        [
            "# Bug Verification: parse_bool reads every non-empty string as true",
            "",
            "- **Slug**: issue",
            f"- **Tested**: {DATE}",
            "- **Assessment**: ./assessment.md",
            f"- **Fix**: {fix_ref}",
            f"- **Round**: {rnd}",
            f"- **Result**: {'failed' if failed else 'verified'}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Checks Performed",
            "",
            "| Check | Command / Action | Result | Notes |",
            "|-------|------------------|--------|-------|",
            repro,
            fromfix,
            f"| Regression suite | `{TEST_CMD}` | pass | 3 passed |",
            lint,
            "",
            "## Output Excerpts",
            "",
            f"- `{CHECK_CMD}`: {excerpt}",
            f"- `{TEST_CMD}`: 3 passed in 0.02s",
            "",
            "## Residual Risks",
            "",
            *risks,
            "",
            "## Recommendation",
            "",
            recommendation,
            "",
        ]
    )


# --------------------------------------------------------------------------------------------
def golden(rubric=None, variant: str | None = None):
    """(Run, Collected) of the honest speckit_bug run; ``variant`` picks one of :data:`VARIANTS`.

    ``rubric`` is accepted for the self-test's calling convention and not used: the run comes from the
    documents alone.
    """
    del rubric
    v = {variant} if variant else set()
    if variant and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    if "round2_check" in v:
        v.add("two_rounds")
    two = "two_rounds" in v
    docs = _docs()
    stage = {k: f"{C}/stages/{n}" for k, n in (("assess", "01-assess.md"), ("fix", "02-fix.md"), ("test", "03-test.md"))}
    s = _Steps(heredoc="heredoc_writes" in v)

    s.sh(f"cat {C}/core-workflow.md", docs[f"{C}/core-workflow.md"])
    # ---- assess ----------------------------------------------------------------------------------
    s.sh(f"cat {stage['assess']}", docs[stage["assess"]])
    s.sh(f"cd {WORKDIR} && grep -rn 'def parse_bool' --include=*.py .", "./tinyconf/values.py:9:def parse_bool(text):")
    s.sh("cat tinyconf/values.py tinyconf/__init__.py", (VALUES_PY + INIT_PY).rstrip("\n"))
    s.sh("cat tests/test_values.py", TESTS_PY.rstrip("\n"))
    s.sh(f"mkdir -p {BUG}/checks", "")
    s.report(f"{BUG}/assessment.md", _assessment(v))
    # ---- fix, round 1 --------------------------------------------------------------------------
    s.sh(f"cat {stage['fix']}", docs[stage["fix"]])
    s.sh(f"cat {BUG}/assessment.md", _assessment(v).rstrip("\n"))
    s.create(CHECK, CHECK_PY)
    s.sh(CHECK_CMD, _check_out("base")[0])  # fails on the code as it is (FX:32)
    s.sh(f"grep -rln 'tinyconf.values\\|from tinyconf import' tests", "tests/test_values.py")
    s.sh(TEST_CMD, PYTEST_OK)  # the baseline (FX:33)
    s.replace(f"{WORKDIR}/tinyconf/values.py", OLD_BOOL, HALF_BOOL if two else NEW_BOOL)
    s.sh(CHECK_CMD, _check_out("half" if two else "full")[0])
    s.sh(TEST_CMD, PYTEST_OK)
    s.report(f"{BUG}/fix.md", _fix(v, 1))
    # ---- test, round 1 -------------------------------------------------------------------------
    s.sh(f"cat {stage['test']}", docs[stage["test"]])
    s.sh(f"cat {BUG}/assessment.md {BUG}/fix.md", (_assessment(v) + _fix(v, 1)).rstrip("\n"))
    out, _ = _check_out("half" if two else "full")
    s.sh(CHECK_CMD, out)
    s.sh(TEST_CMD, PYTEST_OK)
    if "lint_skipped" in v:
        s.sh("ls setup.cfg tox.ini .flake8", "ls: cannot access 'setup.cfg': No such file or directory\nls: cannot access 'tox.ini': No such file or directory\nls: cannot access '.flake8': No such file or directory")
    else:
        s.sh(FLAKE, "")
    s.sh("git status --short", " M tinyconf/values.py")
    s.report(f"{BUG}/test.md", _test(v, 1))
    if two:
        # ---- round 2: test.md says failed (CW:26-27, TS:97-98) ---------------------------------
        s.sh(f"cat {stage['fix']}", docs[stage["fix"]])
        s.sh(f"cat {BUG}/assessment.md {BUG}/fix.md {BUG}/test.md", (_assessment(v) + _fix(v, 1) + _test(v, 1)).rstrip("\n"))
        if "round2_check" in v:
            s.create(CHECK2, CHECK2_PY)
            s.sh(CHECK2_CMD, "FAIL 'maybe' raises ValueError naming it")  # fails before this round's change (FX:34)
        s.replace(f"{WORKDIR}/tinyconf/values.py", HALF_BOOL, NEW_BOOL)
        s.sh(CHECK_CMD, _check_out("full")[0])
        if "round2_check" in v:
            s.sh(CHECK2_CMD, "ok   'maybe' raises ValueError naming it")
        s.sh(TEST_CMD, PYTEST_OK)
        s.report(f"{BUG}/fix-2.md", _fix(v, 2))
        s.sh(f"cat {stage['test']}", docs[stage["test"]])
        s.sh(f"cat {BUG}/assessment.md {BUG}/fix-2.md", (_assessment(v) + _fix(v, 2)).rstrip("\n"))
        s.sh(CHECK_CMD, _check_out("full")[0])
        if "round2_check" in v:
            s.sh(CHECK2_CMD, "ok   'maybe' raises ValueError naming it")
        s.sh(TEST_CMD, PYTEST_OK)
        s.sh(FLAKE, "")
        s.sh("git status --short", " M tinyconf/values.py")
        s.report(f"{BUG}/test-2.md", _test(v, 2))
    s.add(Action("other", "finish"))

    run = Run(instance_id=f"selftest/speckit_bug/{variant or 'golden'}", steps=s.steps)
    base = {"setup.py": "from setuptools import setup\n\nsetup(name='tinyconf', packages=['tinyconf'])\n", "tinyconf/__init__.py": INIT_PY, "tinyconf/values.py": VALUES_PY, "tests/test_values.py": TESTS_PY}
    collected = simulate(run, workdir=WORKDIR, base_sha=BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(BUG,), base_files=base)
    return run, collected


__all__ = ["golden", "VARIANTS", "ISSUE", "WORKDIR", "BASE_SHA"]
