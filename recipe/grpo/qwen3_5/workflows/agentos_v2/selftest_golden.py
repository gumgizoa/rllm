"""The G9 golden run for agentos_v2: a synthetic, honest run that follows the workflow's documents literally.

The self-test (``workflow_rubric/generator/selftest.py``, DESIGN §10 G9) scores a generated rubric on this run and on
mutations of it. For that to test the rubric rather than restate it, the run is written from what the agent sees --
``instruction.md``, ``core-workflow.md`` and the four command documents -- and never from the rubric's items:

* open ``/agent-os/core-workflow.md`` first (instruction.md:4), then each command document when its command begins
  (core-workflow.md:14), shape-spec -> write-spec -> create-tasks -> implement-tasks, each once (core-workflow.md:27-28);
* shape-spec PHASE 1: ``date``, ``mkdir -p`` of the dated spec folder with ``planning/visuals``, ``implementation/``
  and ``verifications/`` (shape-spec.md:29-57), the issue written to ``planning/initialization.md`` as given
  (shape-spec.md:61); PHASE 2: initialization.md read (shape-spec.md:90), the README, the docs index and the packaging
  metadata read (shape-spec.md:94-111), the repository searched for similar code (shape-spec.md:175), the mandatory
  visuals ``ls`` (shape-spec.md:160-167), then ``requirements.md`` in the structure of shape-spec.md:212-288 with five
  numbered questions, each answered ``(assumed) <answer> — <basis>`` (core-workflow.md:70-72), the exclusions question
  last, "No visual assets provided.";
* write-spec: requirements.md and the visuals folder checked (write-spec.md:16-22), the repository searched for code
  to reuse (write-spec.md:30-47), ``spec.md`` in the structure of write-spec.md:59-93 without code;
* create-tasks: spec.md and requirements.md read (create-tasks.md:32-34), ``tasks.md`` in the example format of
  create-tasks.md:44-198 adapted to the change: two task groups, each starting with check scripts under ``checks/``
  (x.1) and ending with running only those (create-tasks.md:214-215), dependencies and acceptance criteria;
* implement-tasks: tasks.md read (implement-tasks.md:19), each task group in order: its check script written under
  ``S/checks/`` and run (failing), the code edited, the check run again (passing), each sub-task ticked ``- [x]`` once
  done (implement-tasks.md:25-45); PHASE 3: tasks.md checked (implement-tasks.md:222), no roadmap
  (implement-tasks.md:235), the entire test suite run once (implement-tasks.md:239), ``final-verification.md`` in the
  structure of implement-tasks.md:251-310 with the run's counts; the final call is a ``finish`` whose observation never
  returns, as in training (core-workflow.md:91-92).

The task is made up (a ``textkit`` package whose ``slugify`` leaves edge hyphens and has no separator option); all text
is synthetic. :func:`golden` returns the ``Run`` and the online ``Collected`` the collector would see: the spec folder
under ``/tmp/agent-os/specs``, the diff against BASE_SHA (``textkit/slug.py`` modified) and the base-tree answers.

:data:`VARIANTS` are other honest runs the documents allow: ``review_group`` (a third task group, Test Review & Gap
Analysis, create-tasks.md:158-189, that reviews the two checks and adds one more), ``followups`` (one follow-up
question, shape-spec.md:179-204), ``suite_failures`` (the whole suite shows two failures the change did not touch:
noted, not fixed, implement-tasks.md:241-243, Status ⚠️ Some Failures), ``sed_ticks`` (each box ticked with
``sed -i``), ``heredoc_writes`` (every spec file written with a shell heredoc instead of the editor) and ``warn_task``
(one sub-task found not done in PHASE 3 Step 1 is marked ⚠️ and listed under Incomplete or Issues,
implement-tasks.md:229).
"""

from __future__ import annotations

from pathlib import Path

from ...workflow_rubric.generator.mutations import simulate
from ...workflow_rubric.trace.model import Action, Run, Step
from . import SPEC as _AOS

WORKDIR = "/testbed"
BASE_SHA = "7c3a9e1f5b2d8c4a6e0f1b3d5c7a9e2f4b6d8c0a"
C = _AOS.container_dir.rstrip("/")  # /agent-os
SPECS = "/tmp/agent-os/specs"
TODAY = "2026-10-16"
NAME = "slugify-edge-hyphens"
S = f"{SPECS}/{TODAY}-{NAME}"
CHECKS = f"{S}/checks"
VARIANTS = ("review_group", "followups", "suite_failures", "sed_ticks", "heredoc_writes", "warn_task")

ISSUE = """slugify() leaves hyphens at the edges: slugify("Hello, World!") returns "hello-world-" and
slugify("  --Draft-- ") returns "-draft-". A slug should never start or end with a hyphen.

It would also help to choose the separator, e.g. slugify("Hello World", sep="_") == "hello_world"."""

BASE_TREE = (
    "README.md",
    "docs/index.rst",
    "docs/usage.rst",
    "setup.cfg",
    "setup.py",
    "textkit/__init__.py",
    "textkit/slug.py",
    "textkit/wrap.py",
    "tests/__init__.py",
    "tests/test_slug.py",
    "tests/test_wrap.py",
)

README = """# textkit

Small text helpers for page titles and file names: `slugify` turns a title into a URL slug and `wrap` folds long
lines. Used by the site generator to name pages.
"""

DOCS_INDEX = """textkit
=======

.. toctree::

   usage
"""

SETUP_CFG = """[metadata]
name = textkit
version = 0.4.0

[options]
packages = textkit
python_requires = >=3.8

[tool:pytest]
testpaths = tests
"""

INIT_PY = '''"""Small text helpers."""

from .slug import slugify
from .wrap import wrap

__all__ = ["slugify", "wrap"]
'''

SLUG_PY = '''"""URL slugs."""

import re

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text):
    """``text`` lower-cased, every run of other characters replaced by one hyphen."""
    return _NON_WORD.sub("-", text.lower())
'''

OLD_BODY = '''def slugify(text):
    """``text`` lower-cased, every run of other characters replaced by one hyphen."""
    return _NON_WORD.sub("-", text.lower())'''
G1_BODY = '''def slugify(text):
    """``text`` lower-cased, every run of other characters replaced by one hyphen, none at either end."""
    return _NON_WORD.sub("-", text.lower()).strip("-")'''
G2_BODY = '''def slugify(text, sep="-"):
    """``text`` lower-cased, every run of other characters replaced by one ``sep``, none at either end."""
    return _NON_WORD.sub(sep, text.lower()).strip(sep)'''

CHECK_EDGES = f"""\"\"\"Task 1.1: a slug never starts or ends with a hyphen.\"\"\"
import sys

sys.path.insert(0, "{WORKDIR}")
from textkit import slugify

assert slugify("Hello, World!") == "hello-world", slugify("Hello, World!")
assert slugify("  --Draft-- ") == "draft", slugify("  --Draft-- ")
assert slugify("plain title") == "plain-title"
print("PASS: no hyphen at either end")
"""

CHECK_SEP = f"""\"\"\"Task 2.1: the caller chooses the separator.\"\"\"
import sys

sys.path.insert(0, "{WORKDIR}")
from textkit import slugify

assert slugify("Hello World", sep="_") == "hello_world"
assert slugify("Hello, World!", sep="_") == "hello_world"
assert slugify("Hello World") == "hello-world"
print("PASS: the separator is the caller's")
"""

CHECK_REVIEW = f"""\"\"\"Task 3.3: an all-punctuation title gives an empty slug with either separator.\"\"\"
import sys

sys.path.insert(0, "{WORKDIR}")
from textkit import slugify

assert slugify("!!!") == ""
assert slugify("!!!", sep="_") == ""
print("PASS: punctuation only gives an empty slug")
"""

PYTEST_HEAD = [
    "============================= test session starts ==============================",
    "platform linux -- Python 3.11.4, pytest-7.4.0, pluggy-1.2.0",
    "rootdir: /testbed",
    "configfile: setup.cfg",
    "testpaths: tests",
]


def pytest_ok() -> str:
    return "\n".join(
        [
            *PYTEST_HEAD,
            "collected 9 items",
            "",
            "tests/test_slug.py ....                                                  [ 44%]",
            "tests/test_wrap.py .....                                                 [100%]",
            "",
            "============================== 9 passed in 0.05s ===============================",
        ]
    )


def pytest_two_failures() -> str:
    return "\n".join(
        [
            *PYTEST_HEAD,
            "collected 9 items",
            "",
            "tests/test_slug.py ....                                                  [ 44%]",
            "tests/test_wrap.py ...FF                                                 [100%]",
            "",
            "=================================== FAILURES ===================================",
            "____________________________ test_wrap_wide_chars _____________________________",
            "E       AssertionError: assert 3 == 2",
            "__________________________ test_wrap_keeps_newlines ___________________________",
            "E       AssertionError: assert 'a b' == 'a\\nb'",
            "=========================== short test summary info ============================",
            "FAILED tests/test_wrap.py::test_wrap_wide_chars - AssertionError: assert 3 == 2",
            "FAILED tests/test_wrap.py::test_wrap_keeps_newlines - AssertionError: assert 'a b' == 'a\\nb'",
            "========================= 2 failed, 7 passed in 0.07s ==========================",
        ]
    )


def _exit(code: int) -> str:
    return f"[Command finished with exit code {code}]"


def _traceback(script: str, line: int, code: str, error: str) -> str:
    return "\n".join(["Traceback (most recent call last):", f'  File "{script}", line {line}, in <module>', f"    {code}", error])


# --------------------------------------------------------------------------------------------
# The documents
# --------------------------------------------------------------------------------------------
def _docs() -> dict[str, str]:
    """Container path -> text of every file the agent can read: docs/ at /agent-os."""
    root = Path(_AOS.docs_dir)
    return {f"{C}/{p.relative_to(root).as_posix()}": p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


class _Steps:
    def __init__(self, heredoc: bool = False):
        self.steps: list[Step] = []
        self.heredoc = heredoc

    def add(self, action: Action, message: str = "") -> None:
        self.steps.append(Step(len(self.steps) + 1, [action], message))

    def sh(self, command: str, observation: str = "", code: int | None = 0) -> None:
        obs = observation if code is None else (observation + ("\n" if observation else "") + _exit(code))
        self.add(Action("shell", "terminal", command=command, observation=obs))

    def cat(self, path: str, text: str) -> None:
        self.sh(f"cat {path}", text.rstrip("\n"))

    def create(self, path: str, text: str) -> None:
        if self.heredoc:
            self.sh(f"cat > {path} <<'EOF'\n{text.rstrip(chr(10))}\nEOF", "")
            return
        self.add(Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}"))

    def replace(self, path: str, old: str, new: str) -> None:
        obs = f"The file {path} has been edited. Here's the result of running `cat -n` on a snippet of {path}. Review the changes and make sure they are as expected."
        self.add(Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation=obs))


# --------------------------------------------------------------------------------------------
# The spec folder's files: each in its document's structure, the placeholders replaced
# --------------------------------------------------------------------------------------------
QUESTIONS = [
    (
        "I assume the fix belongs in `slugify` itself (strip the separator from both ends of the result) rather than in its callers. Is that correct, or should callers trim the slug?",
        "slugify itself strips both ends — the issue asks that a slug never start or end with a hyphen, and textkit/slug.py is the one place slugs are built",
    ),
    (
        "I'm thinking the separator becomes a keyword argument `sep` with `-` as its default. Should we instead add a separate function such as `slugify_with`?",
        'a keyword argument `sep="-"` — the issue\'s example is `slugify("Hello World", sep="_")`, and the default keeps every existing call unchanged',
    ),
    (
        "I assume runs of punctuation and spaces still collapse into a single separator, as today. Is that correct?",
        'yes, one separator per run — README.md describes slugs built that way and tests/test_slug.py checks `slugify("a  b") == "a-b"`',
    ),
    (
        "I assume a title made only of punctuation gives an empty slug rather than raising. Is that correct, or should it raise ValueError?",
        "an empty slug — the issue asks for no edge hyphens and says nothing about errors; slugify raises nothing today",
    ),
    (
        "Is there anything that should be left out of this change, for example transliterating accented letters or limiting the slug's length?",
        "both stay out — the issue names only the edge hyphens and the separator",
    ),
]


def requirements_md(followups: bool = False) -> str:
    qa = []
    for i, (q, a) in enumerate(QUESTIONS, 1):
        qa += [f"**Q{i}:** {q}", f"**Answer:** (assumed) {a}", ""]
    follow = (
        [
            "### Follow-up Questions",
            "",
            "**Follow-up 1:** Should `sep` accept more than one character, such as `--`?",
            "**Answer:** (assumed) yes, any string — the issue's example uses one character but names no limit, and `str.strip` takes a string",
            "",
        ]
        if followups
        else []
    )
    return (
        "\n".join(
            [
                "# Spec Requirements: Slugify edge hyphens",
                "",
                "## Initial Description",
                ISSUE,
                "",
                "## Requirements Discussion",
                "",
                "### First Round Questions",
                "",
                *qa,
                "### Existing Code to Reference",
                "",
                "**Similar Features Identified:**",
                "- Feature: slugify - Path: (assumed) `textkit/slug.py` — the function the issue names; its regex already collapses runs",
                "- Components to potentially reuse: the module-level `_NON_WORD` pattern in textkit/slug.py",
                "- Backend logic to reference: `wrap` in textkit/wrap.py takes its options as keyword arguments with defaults",
                "",
                *follow,
                "## Visual Assets",
                "",
                "No visual assets provided.",
                "",
                "## Requirements Summary",
                "",
                "### Functional Requirements",
                "- A slug never starts or ends with the separator",
                "- Callers choose the separator with a `sep` keyword argument; the default stays `-`",
                "- Runs of other characters still collapse into one separator",
                "",
                "### Reusability Opportunities",
                "- (assumed) `textkit/slug.py` — `_NON_WORD` and the existing substitution stay; only the ends are trimmed",
                "- The keyword-with-default style of `wrap` in textkit/wrap.py",
                "",
                "### Scope Boundaries",
                "**In Scope:**",
                "- Trimming the separator at both ends of the slug",
                "- The `sep` keyword argument",
                "",
                "**Out of Scope:**",
                "- Transliterating accented letters",
                "- Limiting the slug's length",
                "",
                "### Technical Considerations",
                "- slugify is exported from textkit/__init__.py; its signature only gains a keyword argument",
                "- Python >= 3.8 (setup.cfg), standard library only",
                "- Follow the module-level compiled pattern already used in textkit/slug.py",
            ]
        )
        + "\n"
    )


SPEC_MD = """# Specification: Slugify edge hyphens

## Goal
Make `slugify` return slugs that never start or end with the separator, and let callers choose that separator.

## User Stories
- As a site author, I want to turn a title such as "Hello, World!" into a clean slug so that page URLs do not end with a stray hyphen
- As a developer, I want to pass the separator to slugify so that file names can use underscores

## Specific Requirements

**No separator at either end**
- The slug is trimmed of the separator on both ends after the substitution
- Inner runs of other characters still become one separator
- A title made only of punctuation gives an empty slug

**Caller-chosen separator**
- slugify takes a keyword argument `sep`, default `-`
- The same separator is used inside the slug and trimmed from its ends
- Existing calls without `sep` keep their results

## Existing Code to Leverage

**slugify in textkit/slug.py**
- Lower-cases the text and replaces every run of non-alphanumerics with a hyphen through `_NON_WORD`
- The change trims the result and parameterises the replacement instead of adding a new function

**wrap in textkit/wrap.py**
- Takes its options as keyword arguments with defaults; `sep` follows the same style

## Out of Scope
- Transliterating accented or non-Latin letters
- Limiting the slug's length
- Changing `wrap`
"""


def tasks_md(ticked: set[str], review: bool = False, warned: set[str] = frozenset()) -> str:
    def t(tid: str, text: str, indent: str = "  ") -> str:
        if tid in warned:
            box = "⚠️"
        else:
            box = "x" if tid in ticked else " "
        return f"{indent}- [{box}] {tid} {text}"

    g1 = [
        "### Core Function",
        "",
        "#### Task Group 1: Edge separators",
        "**Dependencies:** None",
        "",
        t("1.0", "Complete the edge trimming", indent=""),
        t("1.1", f"Write 2-3 focused tests as a check script {CHECKS}/check_edges.py"),
        "    - Titles ending or starting with punctuation give no edge hyphen",
        t("1.2", "Trim the separator from both ends of the slug in textkit/slug.py"),
        t("1.3", "Ensure the edge tests pass"),
        "    - Run ONLY checks/check_edges.py",
        "",
        "**Acceptance Criteria:**",
        "- check_edges.py passes",
        '- slugify("Hello, World!") returns "hello-world"',
        "",
    ]
    g2 = [
        "#### Task Group 2: Separator option",
        "**Dependencies:** Task Group 1",
        "",
        t("2.0", "Complete the separator option", indent=""),
        t("2.1", f"Write 2-3 focused tests as a check script {CHECKS}/check_sep.py"),
        "    - A custom separator is used inside and trimmed at the ends",
        t("2.2", "Add the sep keyword argument to slugify in textkit/slug.py"),
        t("2.3", "Ensure the separator tests pass"),
        "    - Run ONLY checks/check_sep.py",
        "",
        "**Acceptance Criteria:**",
        "- check_sep.py passes",
        '- slugify("Hello World", sep="_") returns "hello_world"',
        "",
    ]
    g3 = (
        [
            "### Testing",
            "",
            "#### Task Group 3: Test Review & Gap Analysis",
            "**Dependencies:** Task Groups 1-2",
            "",
            t("3.0", "Review existing tests and fill critical gaps only", indent=""),
            t("3.1", "Review the tests written in 1.1 and 2.1"),
            t("3.2", "Analyze test coverage gaps for this change only"),
            t("3.3", f"Write up to 2 additional strategic tests in {CHECKS}/check_review.py"),
            t("3.4", "Run the feature-specific checks only"),
            "",
            "**Acceptance Criteria:**",
            "- All feature-specific checks pass",
            "",
        ]
        if review
        else []
    )
    n = 14 if review else 8
    order = ["1. Core Function (Task Group 1)", "2. Core Function (Task Group 2)"] + (["3. Testing (Task Group 3)"] if review else [])
    return (
        "\n".join(
            [
                "# Task Breakdown: Slugify edge hyphens",
                "",
                "## Overview",
                f"Total Tasks: {n}",
                "",
                "## Task List",
                "",
                *g1,
                *g2,
                *g3,
                "## Execution Order",
                "",
                "Recommended implementation sequence:",
                *order,
            ]
        )
        + "\n"
    )


def report_md(*, failures: bool = False, review: bool = False, warned: bool = False) -> str:
    groups = ["- [x] Task Group 1: Edge separators", "  - [x] 1.1 check_edges.py", "  - [x] 1.2 trim in slugify", "  - [x] 1.3 edge checks pass"]
    groups += ["- [x] Task Group 2: Separator option", "  - [x] 2.1 check_sep.py", "  - [x] 2.2 sep argument", "  - [x] 2.3 separator checks pass"]
    if review:
        groups += ["- [x] Task Group 3: Test Review & Gap Analysis", "  - [x] 3.1-3.4 reviewed, check_review.py added and passing"]
    if warned:
        groups[6] = "  - ⚠️ 2.2 sep argument (see below)"
    issues = "- ⚠️ 2.2: the spot check found the README still documents slugify without sep; left marked, not fixed in PHASE 3" if warned else "None"
    status = "⚠️ Passed with Issues" if (failures or warned) else "✅ Passed"
    t_status = "⚠️ Issues Found" if warned else "✅ All Complete"
    if failures:
        summary = ["- **Total Tests:** 9", "- **Passing:** 7", "- **Failing:** 2", "- **Errors:** 0"]
        failed = [
            "- tests/test_wrap.py::test_wrap_wide_chars - assert 3 == 2 (wide characters counted as one column)",
            "- tests/test_wrap.py::test_wrap_keeps_newlines - newlines folded into spaces",
        ]
        notes = "Both failures are in tests/test_wrap.py, which this change did not touch; they were noted, not fixed."
        s_status = "⚠️ Some Failures"
    else:
        summary = ["- **Total Tests:** 9", "- **Passing:** 9", "- **Failing:** 0", "- **Errors:** 0"]
        failed = ["None - all tests passing"]
        notes = "The whole suite (tests/test_slug.py, tests/test_wrap.py) passes after the change."
        s_status = "✅ All Passing"
    return (
        "\n".join(
            [
                "# Verification Report: Slugify edge hyphens",
                "",
                f"**Spec:** `{TODAY}-{NAME}`",
                f"**Date:** {TODAY}",
                "**Verifier:** implementation-verifier",
                f"**Status:** {status}",
                "",
                "---",
                "",
                "## Executive Summary",
                "",
                "slugify now trims the separator from both ends and takes a `sep` keyword argument. The check scripts of both "
                "task groups pass" + (" and the whole test suite was run once." if not failures else "; the whole suite shows two failures in wrap, outside this change."),
                "",
                "---",
                "",
                "## 1. Tasks Verification",
                "",
                f"**Status:** {t_status}",
                "",
                "### Completed Tasks",
                *groups,
                "",
                "### Incomplete or Issues",
                issues,
                "",
                "---",
                "",
                "## 2. Roadmap Updates",
                "",
                "**Status:** ⚠️ No Updates Needed",
                "",
                "### Notes",
                "This project has no agent-os/product/roadmap.md (plan-product is not part of this workflow), so no roadmap item was updated.",
                "",
                "---",
                "",
                "## 3. Test Suite Results",
                "",
                f"**Status:** {s_status}",
                "",
                "### Test Summary",
                *summary,
                "",
                "### Failed Tests",
                *failed,
                "",
                "### Notes",
                notes,
            ]
        )
        + "\n"
    )


# --------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------
def golden(rubric=None, variant: str | None = None) -> tuple[Run, object]:
    """The honest run (or one of :data:`VARIANTS`) and the online ``Collected`` for it.

    ``rubric`` is accepted for the self-test's calling convention and not used: the run comes from the documents alone.
    """
    del rubric
    if variant and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    v = {variant} if variant else set()
    review, follow, failures, warn = "review_group" in v, "followups" in v, "suite_failures" in v, "warn_task" in v
    docs = _docs()
    s = _Steps(heredoc="heredoc_writes" in v)
    tasks_path = f"{S}/tasks.md"
    done: set[str] = set()

    s.cat(f"{C}/core-workflow.md", docs[f"{C}/core-workflow.md"])
    # ---------------------------------------------------------------- shape-spec
    s.cat(f"{C}/commands/shape-spec/shape-spec.md", docs[f"{C}/commands/shape-spec/shape-spec.md"])
    s.sh("date +%Y-%m-%d", TODAY)
    s.sh(f'mkdir -p {S}/planning/visuals {S}/implementation {S}/verifications && echo "Created spec folder: {S}"', f"Created spec folder: {S}")
    s.create(f"{S}/planning/initialization.md", ISSUE + "\n")
    s.cat(f"{S}/planning/initialization.md", ISSUE)
    s.sh(f"cd {WORKDIR} && cat README.md && cat docs/index.rst && cat setup.cfg", (README + DOCS_INDEX + SETUP_CFG).rstrip("\n"))
    s.sh(
        f"cd {WORKDIR} && grep -rn 'slugify\\|def wrap' --include=*.py textkit tests",
        "\n".join(
            [
                "textkit/__init__.py:3:from .slug import slugify",
                "textkit/slug.py:8:def slugify(text):",
                'textkit/wrap.py:4:def wrap(text, width=72, indent=""):',
                "tests/test_slug.py:1:from textkit import slugify",
            ]
        ),
    )
    s.cat(f"{WORKDIR}/textkit/slug.py", SLUG_PY)
    s.sh(f"ls -la {S}/planning/visuals/ 2>/dev/null | grep -E '\\.(png|jpg|jpeg|gif|svg|pdf)$' || echo \"No visual files found\"", "No visual files found")
    s.create(f"{S}/planning/requirements.md", requirements_md(follow))
    # ---------------------------------------------------------------- write-spec
    s.cat(f"{C}/commands/write-spec/write-spec.md", docs[f"{C}/commands/write-spec/write-spec.md"])
    s.cat(f"{S}/planning/requirements.md", requirements_md(follow))
    s.sh(f'ls -la {S}/planning/visuals/ 2>/dev/null | grep -v "^total" | grep -v "^d"', "", code=1)
    s.sh(
        f"cd {WORKDIR} && grep -rn 'def \\|_NON_WORD' textkit/slug.py textkit/wrap.py",
        "\n".join(['textkit/slug.py:5:_NON_WORD = re.compile(r"[^a-z0-9]+")', "textkit/slug.py:8:def slugify(text):", 'textkit/wrap.py:4:def wrap(text, width=72, indent=""):']),
    )
    s.create(f"{S}/spec.md", SPEC_MD)
    # ---------------------------------------------------------------- create-tasks
    s.cat(f"{C}/commands/create-tasks/create-tasks.md", docs[f"{C}/commands/create-tasks/create-tasks.md"])
    s.sh(f"cat {S}/spec.md {S}/planning/requirements.md", (SPEC_MD + requirements_md(follow)).rstrip("\n"))
    s.create(tasks_path, tasks_md(set(), review))
    # ---------------------------------------------------------------- implement-tasks
    s.cat(f"{C}/commands/implement-tasks/implement-tasks.md", docs[f"{C}/commands/implement-tasks/implement-tasks.md"])
    s.cat(tasks_path, tasks_md(set(), review))
    s.sh(f"cat {S}/spec.md {S}/planning/requirements.md", (SPEC_MD + requirements_md(follow)).rstrip("\n"))

    def tick(*tids: str) -> None:
        for tid in tids:
            done.add(tid)
            if "sed_ticks" in v:
                s.sh(f"sed -i 's/^\\(\\s*\\)- \\[ \\] {tid} /\\1- [x] {tid} /' {tasks_path}")
            else:
                s.replace(tasks_path, f"- [ ] {tid} ", f"- [x] {tid} ")

    def run_check(name: str, ok: bool, fail_obs: str = "", pass_obs: str = "") -> None:
        s.sh(f"cd {WORKDIR} && python {CHECKS}/{name}", pass_obs if ok else fail_obs, code=0 if ok else 1)

    # Task Group 1
    s.sh(f"mkdir -p {CHECKS}")
    s.create(f"{CHECKS}/check_edges.py", CHECK_EDGES)
    run_check("check_edges.py", False, _traceback(f"{CHECKS}/check_edges.py", 7, 'assert slugify("Hello, World!") == "hello-world", slugify("Hello, World!")', "AssertionError: hello-world-"))
    tick("1.1")
    s.replace(f"{WORKDIR}/textkit/slug.py", OLD_BODY, G1_BODY)
    tick("1.2")
    run_check("check_edges.py", True, pass_obs="PASS: no hyphen at either end")
    tick("1.3", "1.0")
    # Task Group 2
    s.create(f"{CHECKS}/check_sep.py", CHECK_SEP)
    run_check(
        "check_sep.py", False, _traceback(f"{CHECKS}/check_sep.py", 7, 'assert slugify("Hello World", sep="_") == "hello_world"', "TypeError: slugify() got an unexpected keyword argument 'sep'")
    )
    tick("2.1")
    s.replace(f"{WORKDIR}/textkit/slug.py", G1_BODY, G2_BODY)
    tick("2.2")
    run_check("check_sep.py", True, pass_obs="PASS: the separator is the caller's")
    run_check("check_edges.py", True, pass_obs="PASS: no hyphen at either end")  # the tests written so far, on the changed code
    tick("2.3", "2.0")
    if review:
        s.sh(f"cat {CHECKS}/check_edges.py {CHECKS}/check_sep.py", (CHECK_EDGES + CHECK_SEP).rstrip("\n"))
        tick("3.1", "3.2")
        s.create(f"{CHECKS}/check_review.py", CHECK_REVIEW)
        tick("3.3")
        run_check("check_review.py", True, pass_obs="PASS: punctuation only gives an empty slug")
        run_check("check_edges.py", True, pass_obs="PASS: no hyphen at either end")
        run_check("check_sep.py", True, pass_obs="PASS: the separator is the caller's")
        tick("3.4", "3.0")
    # ---------------------------------------------------------------- PHASE 3
    final_tasks = tasks_md(done, review)
    s.cat(tasks_path, final_tasks)
    if warn:
        # Step 1's spot check: the README still documents slugify without sep, so 2.2 is found incomplete and marked
        s.replace(tasks_path, "- [x] 2.2 ", "- [⚠️] 2.2 ")
    s.sh(f"cd {WORKDIR} && python -m pytest", pytest_two_failures() if failures else pytest_ok(), code=1 if failures else 0)
    s.create(f"{S}/verifications/final-verification.md", report_md(failures=failures, review=review, warned=warn))
    s.add(Action("other", "finish"), "Final verification report written.")

    run = Run(instance_id=f"selftest/agentos_v2/{variant or 'golden'}", steps=s.steps)
    base = {"README.md": README, "setup.cfg": SETUP_CFG, "docs/index.rst": DOCS_INDEX, "textkit/__init__.py": INIT_PY, "textkit/slug.py": SLUG_PY}
    collected = simulate(run, workdir=WORKDIR, base_sha=BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(SPECS,), base_files=base)
    return run, collected


__all__ = ["golden", "VARIANTS", "ISSUE", "WORKDIR", "BASE_SHA", "BASE_TREE", "S", "CHECKS", "requirements_md", "tasks_md", "report_md", "SPEC_MD"]
