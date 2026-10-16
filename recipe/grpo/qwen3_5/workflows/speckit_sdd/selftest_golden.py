"""The G9 golden run for speckit_sdd: a synthetic, honest run that follows the workflow's documents literally.

The self-test (``workflow_rubric/generator/selftest.py``, DESIGN §10 G9) scores a generated rubric on this run and on
mutations of it. For that to test the rubric rather than restate it, the run is written from what the agent sees --
``instruction.md``, ``core-workflow.md``, the five stage documents and the Spec Kit project shipped at
``/tmp/speckit-sdd/.specify`` (scripts, templates, constitution) -- and never from the rubric's items:

* open ``/speckit-sdd/core-workflow.md`` first (instruction.md:4), then each stage document as its stage begins
  (core-workflow.md:32-33), specify -> plan -> tasks -> implement -> converge (core-workflow.md:37-43);
* specify: ``mkdir -p`` the fixed feature directory, copy the spec template to ``spec.md``, persist
  ``.specify/feature.json`` (01-specify.md:20-32), load the copied template and the constitution, write the spec in
  the template's structure, then the quality checklist, validate, tick it (01-specify.md:67-130);
* plan: run ``setup-plan.sh --json`` (its real stderr and JSON: the plan template copied to IMPL_PLAN), read the spec,
  the constitution and the copy, write research.md, plan.md (Constitution Check "skipped — template", the
  contract file listed in the Documentation tree), data-model.md, contracts/, quickstart.md (02-plan.md);
* tasks: run ``setup-tasks.sh --json`` (its JSON carries the tasks template), read plan.md and spec.md (and the
  optional documents, the constitution), write tasks.md: Setup, Foundational (``No tasks — <reason>``), one phase per
  story with its ``### Tests for User Story N`` verification scripts under ``checks/``, Polish (03-tasks.md);
* implement: run ``check-prerequisites.sh --json --require-tasks --include-tasks``, scan the checklist, read the
  context, run the existing tests (baseline), then per story write its check script, run it and see it fail (the
  terminal's exit-code line), edit the code, run it again and see it pass, ticking each task ``[X]`` once done; run
  the existing tests and both checks again (04-implement.md);
* converge: run ``check-prerequisites.sh --json --require-spec --require-tasks --include-tasks``, read spec, plan and
  tasks, inspect the code, write ``convergence.md`` (converged, the converged sentence last, tasks.md untouched)
  (05-converge.md); the final call is a ``finish`` whose observation never returns, as in training.

The task is made up (a ``strkit`` package gains ``truncate``); all text here is synthetic. :func:`golden` returns the
``Run`` and the online ``Collected`` the collector would see: the files under ``/tmp/speckit-sdd/specs`` and
``.specify/feature.json``, the diff against BASE_SHA (``strkit/text.py``, ``strkit/__init__.py`` modified) and the
base-tree answers.

:data:`VARIANTS` are other honest runs the documents allow: ``two_rounds`` (round 1's converge finds a partial gap,
appends ``## Phase 6: Convergence``; round 2 re-opens 04-implement.md for the unchecked task and 05-converge.md for
``convergence-2.md``, core-workflow.md:38-43), ``no_contracts`` (no contract file, ``contracts/  # N/A — <reason>``
in the tree, 02-plan.md:54), ``na_data_model`` (data-model.md's whole body ``N/A — <reason>``, 02-plan.md:43),
``editor_plan`` (plan.md filled by editing the script's copy in place: the collector, not the trace, holds its text),
``pytest_checks`` (the check scripts run with pytest), ``lowercase_x`` (``[x]`` ticks, 04-implement.md:10-11) and
``sed_ticks`` (each box ticked with ``sed -i``).
"""

from __future__ import annotations

import json
from pathlib import Path

from ...workflow_rubric.generator.mutations import simulate
from ...workflow_rubric.trace.model import Action, Run, Step
from . import SPEC as _SDD

WORKDIR = "/testbed"
BASE_SHA = "4d1c0e9b7a6f5e4d3c2b1a09f8e7d6c5b4a39281"
C = _SDD.container_dir.rstrip("/")  # /speckit-sdd
PROJECT = "/tmp/speckit-sdd"
SPECIFY = f"{PROJECT}/.specify"
SCRIPTS = f"{SPECIFY}/scripts/bash"
SPECS = f"{PROJECT}/specs"
FEATURE_DIR = f"{SPECS}/001-issue"
CHECKS = f"{FEATURE_DIR}/checks"
FEATURE_JSON = f"{SPECIFY}/feature.json"
VARIANTS = ("two_rounds", "no_contracts", "na_data_model", "editor_plan", "pytest_checks", "lowercase_x", "sed_ticks")

ISSUE = """Add a truncate(text, width) function to strkit. Long titles overflow our table cells: text longer than
width characters should be cut so that the result, ellipsis included, is exactly width characters, and end
with "...". Text that already fits is returned unchanged. Callers should be able to pass another ellipsis,
e.g. truncate(title, 20, ellipsis="…")."""

BASE_TREE = (
    "README.md",
    "setup.cfg",
    "setup.py",
    "strkit/__init__.py",
    "strkit/text.py",
    "tests/__init__.py",
    "tests/test_text.py",
)

INIT_PY = '''"""Small string helpers."""

from .text import normalize_spaces

__all__ = ["normalize_spaces"]
'''

TEXT_PY = '''"""Text helpers."""

import re

_SPACES = re.compile(r"\\s+")


def normalize_spaces(text):
    """Collapse every run of whitespace into one space and strip both ends."""
    return _SPACES.sub(" ", text).strip()
'''

TESTS_PY = """from strkit import normalize_spaces


def test_collapse():
    assert normalize_spaces("a  b") == "a b"


def test_strip():
    assert normalize_spaces("  a ") == "a"


def test_empty():
    assert normalize_spaces("") == ""
"""

OLD_EXPORT = 'from .text import normalize_spaces\n\n__all__ = ["normalize_spaces"]'
NEW_EXPORT = 'from .text import normalize_spaces, truncate\n\n__all__ = ["normalize_spaces", "truncate"]'
OLD_END = '    return _SPACES.sub(" ", text).strip()'
US1_GUARDED = '''    return _SPACES.sub(" ", text).strip()


def truncate(text, width):
    """``text`` cut to ``width`` characters, ``...`` included; unchanged when it fits."""
    ellipsis = "..."
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return ellipsis[:width]
    return text[: width - len(ellipsis)] + ellipsis'''
US1_PARTIAL = '''    return _SPACES.sub(" ", text).strip()


def truncate(text, width):
    """``text`` cut to ``width`` characters, ``...`` included; unchanged when it fits."""
    ellipsis = "..."
    if len(text) <= width:
        return text
    return text[: width - len(ellipsis)] + ellipsis'''
US2_OLD = '''def truncate(text, width):
    """``text`` cut to ``width`` characters, ``...`` included; unchanged when it fits."""
    ellipsis = "..."'''
US2_NEW = '''def truncate(text, width, ellipsis="..."):
    """``text`` cut to ``width`` characters, ``ellipsis`` included; unchanged when it fits."""'''
R2_OLD = '''        return text
    return text[: width - len(ellipsis)] + ellipsis'''
R2_NEW = '''        return text
    if width <= len(ellipsis):
        return ellipsis[:width]
    return text[: width - len(ellipsis)] + ellipsis'''

CHECK_US1 = f"""\"\"\"US1: a long text is cut to the width, the ellipsis included (FR-001, FR-002).\"\"\"
import sys

sys.path.insert(0, "{WORKDIR}")
from strkit import truncate

assert truncate("Hello, World", 8) == "Hello...", truncate("Hello, World", 8)
assert truncate("Hi", 8) == "Hi"
assert truncate("Hello", 2) == ".."
print("PASS: US1 long text is cut to the width")
"""

# round 1 of the two-round run: the small-width case (FR-004) is missed by the check and the code alike
CHECK_US1_PARTIAL = CHECK_US1.replace('assert truncate("Hello", 2) == ".."\n', "")

CHECK_US2 = f"""\"\"\"US2: the caller chooses the ellipsis (FR-003).\"\"\"
import sys

sys.path.insert(0, "{WORKDIR}")
from strkit import truncate

assert truncate("Hello, World", 8, ellipsis="…") == "Hello, …"
assert truncate("Hello, World", 8, ellipsis="") == "Hello, W"
print("PASS: US2 a custom ellipsis is used")
"""

TEST_CMD = f"cd {WORKDIR} && python -m pytest tests/test_text.py"
PYTEST_OK = "\n".join(
    [
        "============================= test session starts ==============================",
        "platform linux -- Python 3.11.4, pytest-7.4.0, pluggy-1.2.0",
        "rootdir: /testbed",
        "configfile: setup.cfg",
        "collected 3 items",
        "",
        "tests/test_text.py ...                                                   [100%]",
        "",
        "============================== 3 passed in 0.02s ===============================",
    ]
)


def _exit(code: int) -> str:
    return f"[Command finished with exit code {code}]"


def _traceback(script: str, line: int, code: str, error: str) -> str:
    return "\n".join(["Traceback (most recent call last):", f'  File "{script}", line {line}, in <module>', f"    {code}", error])


# --------------------------------------------------------------------------------------------
# The documents and what the scripts print
# --------------------------------------------------------------------------------------------
def _docs() -> dict[str, str]:
    """Container path -> text of every file the agent can read: docs/ at /speckit-sdd, sandbox/specify at .specify."""
    root = Path(_SDD.docs_dir)
    out = {f"{C}/{p.relative_to(root).as_posix()}": p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}
    for remote, local in _SDD.sandbox_files.items():
        for p in sorted(Path(local).rglob("*")):
            if p.is_file():
                out[f"{remote}/{p.relative_to(local).as_posix()}"] = p.read_text()
    return out


def _json(d: dict) -> str:
    """What ``jq -cn`` prints for the scripts' JSON (compact, non-ASCII kept as is)."""
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


def setup_plan_output() -> str:
    """setup-plan.sh --json with no plan yet: the template-copy notice (stderr), then the paths (setup-plan.sh:38-75)."""
    paths = {"FEATURE_SPEC": f"{FEATURE_DIR}/spec.md", "IMPL_PLAN": f"{FEATURE_DIR}/plan.md", "FEATURE_DIR": FEATURE_DIR, "BRANCH": "001-issue"}
    return f"Copied plan template to {FEATURE_DIR}/plan.md\n" + _json(paths) + "\n" + _exit(0)


def setup_tasks_output(docs: list[str], template: str) -> str:
    """setup-tasks.sh --json: the feature dir, the documents present and the tasks template (setup-tasks.sh:62-75)."""
    return _json({"FEATURE_DIR": FEATURE_DIR, "AVAILABLE_DOCS": docs, "TASKS_TEMPLATE": f"{SPECIFY}/templates/tasks-template.md", "TASKS_TEMPLATE_CONTENT": template}) + "\n" + _exit(0)


def check_prerequisites_output(docs: list[str]) -> str:
    """check-prerequisites.sh --json [--require-spec] --require-tasks --include-tasks (check-prerequisites.sh:198-218)."""
    return _json({"FEATURE_DIR": FEATURE_DIR, "AVAILABLE_DOCS": docs}) + "\n" + _exit(0)


class _Steps:
    def __init__(self):
        self.steps: list[Step] = []

    def add(self, action: Action, message: str = "") -> None:
        self.steps.append(Step(len(self.steps) + 1, [action], message))

    def sh(self, command: str, observation: str = "", code: int | None = 0) -> None:
        obs = observation if code is None else (observation + ("\n" if observation else "") + _exit(code))
        self.add(Action("shell", "terminal", command=command, observation=obs))

    def cat(self, path: str, text: str) -> None:
        self.sh(f"cat {path}", text.rstrip("\n"))

    def write(self, path: str, text: str) -> None:
        """A full write through the shell (the editor's create refuses a file the scripts already made)."""
        self.sh(f"cat > {path} <<'EOF'\n{text.rstrip(chr(10))}\nEOF", "")

    def create(self, path: str, text: str) -> None:
        self.add(Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}"))

    def replace(self, path: str, old: str, new: str) -> None:
        obs = f"The file {path} has been edited. Here's the result of running `cat -n` on a snippet of {path}. Review the changes and make sure they are as expected."
        self.add(Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation=obs))


# --------------------------------------------------------------------------------------------
# The artifacts: each its template's structure with the placeholders replaced
# --------------------------------------------------------------------------------------------
SPEC_MD = """# Feature Specification: Truncate long text

**Feature Branch**: `001-issue`

**Created**: 2026-10-15

**Status**: Draft

**Input**: the issue in the task message

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shorten long text to a width (Priority: P1)

A caller who shows titles in fixed-width cells passes a title and a width and gets text that fits the cell,
with an ellipsis showing that something was cut.

**Why this priority**: Overflowing titles are the reported problem; every caller needs this.

**Independent Test**: Can be fully tested by shortening "Hello, World" to 8 characters and delivers "Hello...".

**Acceptance Scenarios**:

1. **Given** the text "Hello, World", **When** it is shortened to 8 characters, **Then** the result is "Hello..."
2. **Given** the text "Hi", **When** it is shortened to 8 characters, **Then** the result is "Hi" unchanged

---

### User Story 2 - Choose the ellipsis (Priority: P2)

A caller whose cells use another marker passes that marker and sees it at the end of shortened text.

**Why this priority**: Some screens use a single "…" character; the default marker would look out of place.

**Independent Test**: Can be fully tested by shortening "Hello, World" to 8 characters with the marker "…" and delivers "Hello, …".

**Acceptance Scenarios**:

1. **Given** the text "Hello, World" and the marker "…", **When** it is shortened to 8 characters, **Then** the result is "Hello, …"

---

### Edge Cases

- What happens when the width is smaller than the ellipsis? The result is the ellipsis cut to the width.
- How does the system handle an empty marker? Long text is cut to the width with nothing appended.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST shorten text longer than the requested width to exactly that width, ending with the ellipsis
- **FR-002**: System MUST return text that fits within the width unchanged
- **FR-003**: Users MUST be able to choose the ellipsis marker; the default is three dots
- **FR-004**: System MUST return the ellipsis cut to the width when the width is smaller than the ellipsis

### Key Entities

- **Text**: the words a caller wants to show, of any length
- **Width**: the number of characters the shown text may take

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the acceptance scenarios produce the expected text
- **SC-002**: Shortened text never exceeds the requested width, for any text and width
- **SC-003**: Callers can change the marker without any other change to how they shorten text

## Assumptions

- Width counts characters, not display columns; wide characters are out of scope.
- A negative width is treated like zero by callers today and is not part of this feature.
"""


def checklist_md(ticked: bool) -> str:
    b = "x" if ticked else " "
    items = {
        "Content Quality": ["No implementation details (languages, frameworks, APIs)", "Focused on user value and business needs", "Written for non-technical stakeholders", "All mandatory sections completed"],
        "Requirement Completeness": [
            "No [NEEDS CLARIFICATION] markers remain",
            "Requirements are testable and unambiguous",
            "Success criteria are measurable",
            "Success criteria are technology-agnostic (no implementation details)",
            "All acceptance scenarios are defined",
            "Edge cases are identified",
            "Scope is clearly bounded",
            "Dependencies and assumptions identified",
        ],
        "Feature Readiness": [
            "All functional requirements have clear acceptance criteria",
            "User scenarios cover primary flows",
            "Feature meets measurable outcomes defined in Success Criteria",
            "No implementation details leak into specification",
        ],
    }
    out = [
        "# Specification Quality Checklist: Truncate long text",
        "",
        "**Purpose**: Validate specification completeness and quality before proceeding to planning",
        "**Created**: 2026-10-15",
        "**Feature**: [spec.md](../spec.md)",
        "",
    ]
    for sec, lines in items.items():
        out += [f"## {sec}", "", *[f"- [{b}] {x}" for x in lines], ""]
    out += ["## Notes", "", "- Items marked incomplete require spec updates before the plan stage"]
    if ticked:
        out.append("- Validation passed on the first iteration; no item needed a spec update.")
    return "\n".join(out) + "\n"


RESEARCH_MD = """# Research: Truncate long text

## Where the function lives

- Decision: add truncate to strkit/text.py next to normalize_spaces and export it from strkit/__init__.py
- Rationale: the package keeps its text helpers in one module and exports each from the package root
- Alternatives considered: a new module strkit/truncate.py (one function does not justify a module)

## Small widths

- Decision: when the width is not larger than the ellipsis, return the ellipsis cut to the width
- Rationale: the result must never exceed the width (SC-002), and the marker still shows that text was cut
- Alternatives considered: raising ValueError (callers size cells dynamically and would need a guard everywhere)
"""


def plan_md(contracts: bool = True) -> str:
    contract_lines = "├── contracts/           # Phase 1 output (plan stage)\n│   └── truncate.md      # the truncate function's contract" if contracts else "├── contracts/           # N/A — strkit is used only from inside this repository's own scripts, no outside interface"
    return f"""# Implementation Plan: Truncate long text

**Branch**: `001-issue` | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/tmp/speckit-sdd/specs/001-issue/spec.md`

**Note**: This template is filled in by the plan stage; its stage document (`/speckit-sdd/stages/02-plan.md`) describes the execution workflow.

## Summary

Callers need text cut to a width with an ellipsis, the ellipsis selectable; a truncate(text, width, ellipsis)
function in strkit/text.py, exported from the package, does it with plain slicing.

## Technical Context

**Language/Version**: Python 3.11 (setup.cfg python_requires >= 3.8)

**Primary Dependencies**: standard library only

**Storage**: N/A

**Testing**: pytest (tests/test_text.py)

**Target Platform**: any platform running CPython 3

**Project Type**: library

**Performance Goals**: linear in the length of the text

**Constraints**: the result never exceeds the width; normalize_spaces stays as it is

**Scale/Scope**: one function in one module

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

skipped — template: `.specify/memory/constitution.md` is the unfilled template and holds no principle, so no gate
is evaluated, before Phase 0 or after the Phase 1 design.

## Project Structure

### Documentation (this feature)

```text
/tmp/speckit-sdd/specs/001-issue/
├── plan.md              # This file (plan stage output)
├── research.md          # Phase 0 output (plan stage)
├── data-model.md        # Phase 1 output (plan stage; always, `N/A — <reason>` if nothing applies)
├── quickstart.md        # Phase 1 output (plan stage; always, `N/A — <reason>` if nothing applies)
{contract_lines}
└── tasks.md             # Phase 2 output (tasks stage - NOT created by the plan stage)
```

### Source Code (repository root)

```text
strkit/
├── __init__.py          # exports truncate
└── text.py              # truncate added next to normalize_spaces
```

**Structure Decision**: the existing single package strkit/; the change edits strkit/text.py and
strkit/__init__.py and adds no module.

## Complexity Tracking

No Constitution Check violation needs a justification.
"""


DATA_MODEL_MD = """# Data Model: Truncate long text

## Text

- Fields: the string a caller passes, any length
- Validation: none; every string is accepted

## Shortened text

- Fields: the shown characters of the text followed by the ellipsis
- Validation: at most width characters; equal to the text when the text fits; the ellipsis cut to the width when the width is smaller than it
- Relationships: derived from one Text, one width and one ellipsis
"""

DATA_MODEL_NA = "N/A — the change adds one function over plain strings; it stores and models no data\n"

CONTRACT_MD = """# Contract: strkit.truncate

- Signature: `truncate(text: str, width: int, ellipsis: str = "...") -> str`, exported by `strkit`
- Returns text unchanged when `len(text) <= width`, else `width` characters ending with `ellipsis`
- See data-model.md for the small-width rule
"""

QUICKSTART_MD = """# Quickstart: Truncate long text

## Prerequisites

- The repository at /testbed with pytest available

## Validate

1. Existing tests: `python -m pytest tests/test_text.py` -- expected: 3 passed
2. Verification scripts: `python /tmp/speckit-sdd/specs/001-issue/checks/test_us1.py` and `test_us2.py` -- expected: each prints PASS

See contracts/truncate.md for the behaviour and data-model.md for the rules.
"""


def tasks_md(ticked: set[str], box: str = "X", convergence: bool = False) -> str:
    def t(tid: str, text: str) -> str:
        return f"- [{box if tid in ticked else ' '}] {tid} {text}"

    lines = [
        "# Tasks: Truncate long text",
        "",
        "**Input**: Design documents from `/tmp/speckit-sdd/specs/001-issue/`",
        "",
        "**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/",
        "",
        "**Tests**: every user story gets its test tasks; their files are verification scripts under `/tmp/speckit-sdd/specs/001-issue/checks/`, never test files in the repository.",
        "",
        "**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.",
        "",
        "## Phase 1: Setup (Shared Infrastructure)",
        "",
        "**Purpose**: Record the behaviour before the change",
        "",
        t("T001", "Run the existing tests in tests/test_text.py to record the baseline"),
        "",
        "---",
        "",
        "## Phase 2: Foundational (Blocking Prerequisites)",
        "",
        "No tasks — both stories extend the one module strkit/text.py and share no groundwork",
        "",
        "---",
        "",
        "## Phase 3: User Story 1 - Shorten long text to a width (Priority: P1) 🎯 MVP",
        "",
        "**Goal**: Text longer than the width is cut to the width, ending with \"...\"",
        "",
        '**Independent Test**: truncate("Hello, World", 8) returns "Hello..."',
        "",
        "### Tests for User Story 1",
        "",
        t("T002", "[US1] Write the verification script /tmp/speckit-sdd/specs/001-issue/checks/test_us1.py for FR-001, FR-002 and FR-004"),
        "",
        "### Implementation for User Story 1",
        "",
        t("T003", "[US1] Add truncate(text, width) to strkit/text.py and export it from strkit/__init__.py"),
        "",
        "**Checkpoint**: User Story 1 is fully functional and testable independently",
        "",
        "---",
        "",
        "## Phase 4: User Story 2 - Choose the ellipsis (Priority: P2)",
        "",
        "**Goal**: The caller passes the ellipsis marker",
        "",
        '**Independent Test**: truncate("Hello, World", 8, ellipsis="…") returns "Hello, …"',
        "",
        "### Tests for User Story 2",
        "",
        t("T004", "[US2] Write the verification script /tmp/speckit-sdd/specs/001-issue/checks/test_us2.py for FR-003"),
        "",
        "### Implementation for User Story 2",
        "",
        t("T005", "[US2] Add the ellipsis parameter to truncate in strkit/text.py"),
        "",
        "**Checkpoint**: User Stories 1 AND 2 both work independently",
        "",
        "---",
        "",
        "## Phase 5: Polish & Cross-Cutting Concerns",
        "",
        "**Purpose**: Validate the whole change",
        "",
        t("T006", "Run tests/test_text.py and both verification scripts in /tmp/speckit-sdd/specs/001-issue/checks/"),
        "",
        "---",
        "",
        "## Dependencies & Execution Order",
        "",
        "### Phase Dependencies",
        "",
        "- **Setup (Phase 1)**: No dependencies - can start immediately",
        "- **Foundational (Phase 2)**: No tasks",
        "- **User Stories (Phase 3+)**: Depend on Setup",
        "- **Polish (Final Phase)**: Depends on both user stories being complete",
        "",
        "### User Story Dependencies",
        "",
        "- **User Story 1 (P1)**: Can start after Setup - No dependencies on other stories",
        "- **User Story 2 (P2)**: Can start after User Story 1 - both edit truncate in strkit/text.py",
        "",
        "### Within Each User Story",
        "",
        "- The verification script is written and seen failing before the implementation",
        "",
        "### Parallel Opportunities",
        "",
        "- None: every task edits or checks strkit/text.py, so the tasks run in order",
    ]
    text = "\n".join(lines) + "\n"
    if convergence:
        text += "\n" + CONVERGENCE_PHASE(ticked, box)
    return text


def CONVERGENCE_PHASE(ticked: set[str], box: str = "X") -> str:  # noqa: N802 -- reads as the appended text
    b = box if "T007" in ticked else " "
    return f"## Phase 6: Convergence\n\n- [{b}] T007 Return the ellipsis cut to the width when the width is smaller than it in strkit/text.py per FR-004 (partial)\n"


CONVERGED = "✅ Converged — the implementation satisfies the spec, plan, and tasks."


def convergence_md(round_: int, converged: bool) -> str:
    head = ["## Convergence Findings", "", f"- **Round**: {round_}", f"- **Outcome**: {'converged' if converged else 'tasks_appended'}", ""]
    table = ["| ID | Gap Type | Severity | Source | Evidence | Remaining Work |", "|----|----------|----------|--------|----------|----------------|"]
    if not converged:
        table.append('| F1 | partial | HIGH | FR-004 | strkit/text.py: truncate("Hello", 2) returns "He..." (5 characters) | Return the ellipsis cut to the width |')
    metrics = [
        "",
        "**Summary metrics:**",
        "",
        "- Requirements / acceptance criteria checked: 4 functional requirements, 3 success criteria, 3 acceptance scenarios",
        "- Plan decisions checked: 2",
        '- Constitution principles checked: skipped — template',
        f"- Findings by gap type: missing 0 / partial {0 if converged else 1} / contradicts 0 / unrequested 0",
        f"- Findings by severity: CRITICAL 0 / HIGH {0 if converged else 1} / MEDIUM 0 / LOW 0",
    ]
    body = head + table + metrics
    if converged:
        body += ["", CONVERGED]
    return "\n".join(body) + "\n"


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
    docs = _docs()
    tpl = {k: docs[f"{SPECIFY}/templates/{k}-template.md"] for k in ("spec", "plan", "tasks")}
    constitution = docs[f"{SPECIFY}/memory/constitution.md"]
    two = "two_rounds" in v
    contracts = "no_contracts" not in v
    box = "x" if "lowercase_x" in v else "X"
    data_model = DATA_MODEL_NA if "na_data_model" in v else DATA_MODEL_MD
    plan = plan_md(contracts)
    s = _Steps()

    s.cat(f"{C}/core-workflow.md", docs[f"{C}/core-workflow.md"])
    # ---------------------------------------------------------------- specify
    s.cat(f"{C}/stages/01-specify.md", docs[f"{C}/stages/01-specify.md"])
    s.sh(f"cd {WORKDIR} && ls strkit tests && cat strkit/__init__.py strkit/text.py", "__init__.py\ntext.py\n__init__.py\ntest_text.py\n" + (INIT_PY + TEXT_PY).rstrip("\n"))
    s.sh(f"mkdir -p {FEATURE_DIR}")
    s.sh(f"cp {SPECIFY}/templates/spec-template.md {FEATURE_DIR}/spec.md")
    s.write(FEATURE_JSON, json.dumps({"feature_directory": "specs/001-issue"}, indent=2))
    s.cat(f"{FEATURE_DIR}/spec.md", tpl["spec"])
    s.cat(f"{SPECIFY}/memory/constitution.md", constitution)
    s.write(f"{FEATURE_DIR}/spec.md", SPEC_MD)
    s.sh(f"mkdir -p {FEATURE_DIR}/checklists")
    s.create(f"{FEATURE_DIR}/checklists/requirements.md", checklist_md(False))
    s.cat(f"{FEATURE_DIR}/spec.md", SPEC_MD)  # validation against each checklist item
    s.write(f"{FEATURE_DIR}/checklists/requirements.md", checklist_md(True))
    # ---------------------------------------------------------------- plan
    s.cat(f"{C}/stages/02-plan.md", docs[f"{C}/stages/02-plan.md"])
    s.sh(f"{SCRIPTS}/setup-plan.sh --json", setup_plan_output(), code=None)
    s.cat(f"{FEATURE_DIR}/spec.md", SPEC_MD)
    s.cat(f"{SPECIFY}/memory/constitution.md", constitution)
    s.cat(f"{FEATURE_DIR}/plan.md", tpl["plan"])
    s.sh(f"cd {WORKDIR} && cat setup.cfg && python --version", "[metadata]\nname = strkit\n\n[options]\npython_requires = >=3.8\n\n[tool:pytest]\ntestpaths = tests\nPython 3.11.4")
    s.create(f"{FEATURE_DIR}/research.md", RESEARCH_MD)
    if "editor_plan" in v:
        _edit_plan(s, tpl["plan"], plan)
    else:
        s.write(f"{FEATURE_DIR}/plan.md", plan)
    s.create(f"{FEATURE_DIR}/data-model.md", data_model)
    if contracts:
        s.sh(f"mkdir -p {FEATURE_DIR}/contracts")
        s.create(f"{FEATURE_DIR}/contracts/truncate.md", CONTRACT_MD)
    s.create(f"{FEATURE_DIR}/quickstart.md", QUICKSTART_MD)
    # ---------------------------------------------------------------- tasks
    s.cat(f"{C}/stages/03-tasks.md", docs[f"{C}/stages/03-tasks.md"])
    avail = ["research.md", "data-model.md", *(["contracts/"] if contracts else []), "quickstart.md"]
    s.sh(f"{SCRIPTS}/setup-tasks.sh --json", setup_tasks_output(avail, tpl["tasks"]), code=None)
    s.cat(f"{FEATURE_DIR}/plan.md", plan)
    s.cat(f"{FEATURE_DIR}/spec.md", SPEC_MD)
    opt = [f"{FEATURE_DIR}/research.md", f"{FEATURE_DIR}/data-model.md", *([f"{FEATURE_DIR}/contracts/truncate.md"] if contracts else []), f"{FEATURE_DIR}/quickstart.md"]
    s.sh("cat " + " ".join(opt), (RESEARCH_MD + data_model + (CONTRACT_MD if contracts else "") + QUICKSTART_MD).rstrip("\n"))
    s.cat(f"{SPECIFY}/memory/constitution.md", constitution)
    s.create(f"{FEATURE_DIR}/tasks.md", tasks_md(set()))
    # ---------------------------------------------------------------- implement (round 1)
    tasks_path = f"{FEATURE_DIR}/tasks.md"
    done: set[str] = set()

    def tick(tid: str) -> None:
        done.add(tid)
        if "sed_ticks" in v:
            s.sh(f"sed -i 's/^- \\[ \\] {tid} /- [{box}] {tid} /' {tasks_path}")
        else:
            s.replace(tasks_path, f"- [ ] {tid} ", f"- [{box}] {tid} ")

    def run_check(name: str, ok: bool, fail_obs: str = "") -> None:
        script = f"{CHECKS}/{name}"
        if "pytest_checks" in v:
            out = f"collected 1 item\n\n{script} {'.' if ok else 'F'}\n\n{'1 passed' if ok else '1 failed'} in 0.03s"
            s.sh(f"cd {WORKDIR} && python -m pytest -q {script}", out if ok else out.replace("collected 1 item", "collected 1 item\n" + fail_obs), code=0 if ok else 1)
        else:
            s.sh(f"cd {WORKDIR} && python {script}", (f"PASS: {'US1 long text is cut to the width' if 'us1' in name else 'US2 a custom ellipsis is used'}" if ok else fail_obs), code=0 if ok else 1)

    s.cat(f"{C}/stages/04-implement.md", docs[f"{C}/stages/04-implement.md"])
    s.sh(f"{SCRIPTS}/check-prerequisites.sh --json --require-tasks --include-tasks", check_prerequisites_output([*avail, "tasks.md"]), code=None)
    s.sh(f"grep -c -E '^- \\[(x|X)\\]' {FEATURE_DIR}/checklists/requirements.md; grep -c -E '^- \\[ \\]' {FEATURE_DIR}/checklists/requirements.md", "16\n0")
    s.cat(tasks_path, tasks_md(set()))
    s.cat(f"{FEATURE_DIR}/plan.md", plan)
    s.sh("cat " + " ".join(opt), (RESEARCH_MD + data_model + (CONTRACT_MD if contracts else "") + QUICKSTART_MD).rstrip("\n"))
    s.cat(f"{SPECIFY}/memory/constitution.md", constitution)
    s.sh(TEST_CMD, PYTEST_OK)  # T001: the baseline
    tick("T001")
    s.sh(f"mkdir -p {CHECKS}")
    s.create(f"{CHECKS}/test_us1.py", CHECK_US1_PARTIAL if two else CHECK_US1)  # T002
    run_check("test_us1.py", False, _traceback(f"{CHECKS}/test_us1.py", 5, "from strkit import truncate", "ImportError: cannot import name 'truncate' from 'strkit' (/testbed/strkit/__init__.py)"))
    tick("T002")
    s.replace(f"{WORKDIR}/strkit/text.py", OLD_END, US1_PARTIAL if two else US1_GUARDED)  # T003
    s.replace(f"{WORKDIR}/strkit/__init__.py", OLD_EXPORT, NEW_EXPORT)
    run_check("test_us1.py", True)
    tick("T003")
    s.create(f"{CHECKS}/test_us2.py", CHECK_US2)  # T004
    run_check("test_us2.py", False, _traceback(f"{CHECKS}/test_us2.py", 7, 'assert truncate("Hello, World", 8, ellipsis="…") == "Hello, …"', "TypeError: truncate() got an unexpected keyword argument 'ellipsis'"))
    tick("T004")
    s.replace(f"{WORKDIR}/strkit/text.py", US2_OLD, US2_NEW)  # T005
    run_check("test_us2.py", True)
    tick("T005")
    s.sh(TEST_CMD, PYTEST_OK)  # T006: completion validation
    run_check("test_us1.py", True)
    run_check("test_us2.py", True)
    tick("T006")
    # ---------------------------------------------------------------- converge (round 1)
    s.cat(f"{C}/stages/05-converge.md", docs[f"{C}/stages/05-converge.md"])
    s.sh(f"{SCRIPTS}/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks", check_prerequisites_output([*avail, "tasks.md"]), code=None)
    s.cat(f"{FEATURE_DIR}/spec.md", SPEC_MD)
    s.cat(f"{FEATURE_DIR}/plan.md", plan)
    s.cat(tasks_path, tasks_md(done, box))
    final_text = _final_text(two, round_=1)
    s.sh(f"cd {WORKDIR} && cat strkit/text.py strkit/__init__.py", (final_text + INIT_PY.replace(OLD_EXPORT, NEW_EXPORT)).rstrip("\n"))
    if not two:
        s.create(f"{FEATURE_DIR}/convergence.md", convergence_md(1, converged=True))
    else:
        s.sh(f"cd {WORKDIR} && python -c \"from strkit import truncate; print(repr(truncate('Hello', 2)))\"", "'He...'")
        s.create(f"{FEATURE_DIR}/convergence.md", convergence_md(1, converged=False))
        s.sh(f"cat >> {tasks_path} <<'EOF'\n\n{CONVERGENCE_PHASE(set()).rstrip(chr(10))}\nEOF", "")
        # ------------------------------------------------------------ implement (round 2): the unchecked task only
        s.cat(f"{C}/stages/04-implement.md", docs[f"{C}/stages/04-implement.md"])
        s.sh(f"{SCRIPTS}/check-prerequisites.sh --json --require-tasks --include-tasks", check_prerequisites_output([*avail, "tasks.md"]), code=None)
        s.cat(tasks_path, tasks_md(done, box, convergence=True))
        s.replace(f"{WORKDIR}/strkit/text.py", R2_OLD, R2_NEW)  # T007
        run_check("test_us1.py", True)
        run_check("test_us2.py", True)
        s.sh(TEST_CMD, PYTEST_OK)
        tick("T007")
        # ------------------------------------------------------------ converge (round 2)
        s.cat(f"{C}/stages/05-converge.md", docs[f"{C}/stages/05-converge.md"])
        s.sh(f"{SCRIPTS}/check-prerequisites.sh --json --require-spec --require-tasks --include-tasks", check_prerequisites_output([*avail, "tasks.md"]), code=None)
        s.cat(f"{FEATURE_DIR}/spec.md", SPEC_MD)
        s.cat(f"{FEATURE_DIR}/plan.md", plan)
        s.cat(tasks_path, tasks_md(done, box, convergence=True))
        s.sh(f"cd {WORKDIR} && cat strkit/text.py", _final_text(True, round_=2).rstrip("\n"))
        s.create(f"{FEATURE_DIR}/convergence-2.md", convergence_md(2, converged=True))
    s.sh(f"cd {WORKDIR} && git status --short", " M strkit/__init__.py\n M strkit/text.py")
    s.add(Action("other", "finish"), "The chain is complete: converged.")

    run = Run(instance_id=f"selftest/speckit_sdd/{variant or 'golden'}", steps=s.steps)
    base = {"setup.cfg": "[metadata]\nname = strkit\n", "strkit/__init__.py": INIT_PY, "strkit/text.py": TEXT_PY, "tests/test_text.py": TESTS_PY}
    files = _final_files(run, plan) if "editor_plan" in v else None
    collected = simulate(run, workdir=WORKDIR, base_sha=BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(SPECS, FEATURE_JSON), files=files, base_files=base)
    return run, collected


def _final_text(two: bool, round_: int) -> str:
    """strkit/text.py as the run leaves it after round ``round_``."""
    body = TEXT_PY.replace(OLD_END, US1_PARTIAL if two else US1_GUARDED).replace(US2_OLD, US2_NEW)
    return body.replace(R2_OLD, R2_NEW) if (two and round_ == 2) else body


def _edit_plan(s: _Steps, template: str, plan: str) -> None:
    """plan.md filled by editing the copy setup-plan.sh made, in two str_replace edits: the replay cannot know the
    copy's text, the collector holds the result."""
    path = f"{FEATURE_DIR}/plan.md"
    head_old, head_new = template.split("## Summary", 1)[0], plan.split("## Summary", 1)[0]
    s.replace(path, head_old.rstrip("\n"), head_new.rstrip("\n"))
    body_old = "## Summary" + template.split("## Summary", 1)[1]
    body_new = "## Summary" + plan.split("## Summary", 1)[1]
    s.replace(path, body_old.rstrip("\n"), body_new.rstrip("\n"))


def _final_files(run: Run, plan: str) -> dict[str, str]:
    """The collected files at the end: the replayed ones, plus the plan the editor produced."""
    from ...workflow_rubric.replay import replay

    rep = replay(run, WORKDIR)
    out = {p: t for p, t in rep.final.items() if t is not None and (p.startswith(SPECS + "/") or p == FEATURE_JSON)}
    out[f"{FEATURE_DIR}/plan.md"] = plan
    return out


__all__ = ["golden", "VARIANTS", "ISSUE", "WORKDIR", "BASE_SHA", "BASE_TREE", "FEATURE_DIR", "CHECKS", "setup_plan_output", "setup_tasks_output", "check_prerequisites_output", "tasks_md", "convergence_md"]
