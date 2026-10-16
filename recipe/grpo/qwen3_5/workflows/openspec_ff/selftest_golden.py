"""The G9 golden run for openspec_ff: a synthetic, honest run that follows the package's documents literally.

The self-test (``workflow_rubric/generator/selftest.py``, DESIGN §10 G9) scores a generated rubric on this run and on
mutations of it. For that to test the rubric rather than restate it, the run is written from what the agent sees --
``instruction.md``, ``core-workflow.md``, the four stage documents and what the ``openspec`` CLI prints (the forked
schema's instructions and templates, the project config) -- and never from the rubric's items:

* ``/opsx/core-workflow.md`` first (INS:5, SP:66), then each stage document as its action begins (CW:18-24), one per
  call;
* explore, first (CW:11-12): ``openspec list --json`` (CW:20, EX:113-116) and the project config (EX:131), the code and
  the existing tests read (CW:75-76, EX:5) -- no file written and no code composed (CW:75-78) -- then the "What We
  Figured Out" summary in a ``think`` call (CW:60-63, EX:189-207) before ``01-ff.md`` is opened;
* ff: the project check (``openspec list --json``, FF:3), ``openspec new change "issue"`` (CW:21, FF:22-26), ``openspec
  status --change "issue" --json`` (FF:28-31), the repository inspected read-only (FF:57), then per artifact in
  dependency order ``openspec instructions <id> --change "issue" --json`` (FF:44-46), the completed dependencies
  re-read from disk (FF:56), the file written from the served template (FF:62, FF:100) with only its placeholders
  replaced, ``status`` re-run (FF:67); a delta spec ``## ADDED Requirements`` for a new capability (CW:57-58), and the
  final ``openspec status --change "issue"`` (FF:80-83);
* apply: ``status`` and ``openspec instructions apply`` (AP:26-39), every context file read (AP:72-76), a check script
  under ``/openspec/changes/issue/checks/`` (CW:36-37) run before and after the fix, the source edited, the repository's
  tests run, each task ticked at its line and the apply instructions re-run after it (AP:96-98);
* verify, once (CW:84-87): ``status`` and ``instructions apply`` (VF:26-39), every artifact read (VF:41), the code
  inspected and the checks run without editing anything (VF:43, CW:74), ``verify.md`` in the scorecard format of
  VF:145-188 with no CRITICAL issue, then straight on to the archive (VF:188);
* archive: ``openspec archive issue --yes`` once (CW:93-100), which prints "archived as" and exits 0; then ``finish``,
  whose observation never returns, as in training.

The CLI's own file operations are not in the trace: :func:`golden` returns the ``Collected`` the collector would see
after them -- the change under ``/openspec/changes/archive/<date>-issue/`` (with the ``.openspec.yaml`` that ``new
change`` scaffolded), the merged main spec under ``/openspec/specs/``, the config and the schema setup.sh installed --
and the diff against BASE_SHA (``tinyconf/values.py`` modified). The task is made up (a ``tinyconf`` package whose
``parse_bool`` reads every non-empty string as true); all text is synthetic.

:data:`VARIANTS` are other honest runs the documents allow: ``critical_archived`` -- apply leaves the ValueError task
open with its one-line reason (AP:105, AP:109), verify.md lists it and the requirement it leaves unimplemented as
CRITICAL issues (VF:70-71, VF:163-165, VF:181), and the run moves on to archive with them recorded (CW:86-87, VF:188;
no return to apply, CW:105-106), the CLI archiving with its incomplete-task warning under ``--yes``; ``no_design`` --
design.md skipped as conditional (FF:72, SCHEMA:170); ``heredoc_writes`` -- every artifact written with a shell heredoc
instead of the editor; ``archive_retry`` -- the first archive fails validation on the delta spec (a scenario written
with three hashes), the run corrects only that and runs the same command once more (CW:103-104);
``summary_in_ff_turn`` -- the explore summary's ``think`` call shares the turn that opens ``01-ff.md``, ahead of the read
(EX:191 "before the tool call that opens"); ``explore_runs_tests`` -- explore also runs the existing tests as they are
(CW:75-76, EX:5: read-only); ``summary_lean`` -- the summary holds only the parts that must be stated (EX:189: the problem,
where the change goes).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ...workflow_rubric.generator.mutations import simulate
from ...workflow_rubric.replay import replay
from ...workflow_rubric.trace.model import Action, Run, Step
from . import SPEC as _SPEC

PKG = Path(__file__).resolve().parent
WORKDIR = "/testbed"
BASE_SHA = "7f3c2a9e1b0d4c6a8e5f2b1d3c9a7e6f5d4c3b2a"
C = _SPEC.container_dir.rstrip("/")
ROOT = "/openspec"
CHG = f"{ROOT}/changes/issue"
DATE = "2026-10-14"
ARCH = f"{ROOT}/changes/archive/{DATE}-issue"
CAP = "boolean-parsing"
CHECK = f"{CHG}/checks/check_parse_bool.py"
FORK = "spec-driven-sandbox"
VARIANTS = ("critical_archived", "no_design", "heredoc_writes", "archive_retry", "summary_in_ff_turn", "explore_runs_tests", "summary_lean")
EXIT0 = "\n[The command completed with exit code 0.]\n[Current working directory: /testbed]\n[Command finished with exit code 0]"
EXIT1 = "\n[The command completed with exit code 1.]\n[Current working directory: /testbed]\n[Command finished with exit code 1]"

ISSUE = """tinyconf.parse_bool("false") returns True, and so do "0" and "no": every non-empty string is
read as true. Only "true", "1", "yes" and "on" (any case) should be true, and "false", "0", "no", "off"
false; anything else should raise ValueError naming the text."""

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
HALF_BOOL = '''_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def parse_bool(text):
    """``text`` as a bool: true / 1 / yes / on and false / 0 / no / off, in any case."""
    word = text.strip().lower()
    if word in _FALSE:
        return False
    return word in _TRUE
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

CHECK_PY = '''"""Check for the tinyconf.parse_bool issue: the false words, case and whitespace, and the ValueError."""

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

_FALSE_WORDS = ("false", "0", "no", "off", "FALSE", " No ")
_TRUE_WORDS = ("true", "1", "yes", "on", "TRUE")
TEST_CMD = "python -m pytest tests/test_values.py -q"
CHECK_CMD = f"python {CHECK}"
PYTEST_OK = "...                                                                      [100%]\n3 passed in 0.02s"


def _check_out(stage: str) -> str:
    """The check script's output before the fix (``none``), after the half fix, after the full fix."""
    lines = []
    for w in _FALSE_WORDS:
        good = stage in ("half", "full")
        lines.append(("ok   " if good else "FAIL ") + f"{w!r} is False")
    lines += [f"ok   {w!r} is True" for w in _TRUE_WORDS]
    lines.append(("ok   " if stage == "full" else "FAIL ") + "'maybe' raises ValueError naming it")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# What the agent can read: the documents, and what the CLI prints (from the forked schema and the config)
# --------------------------------------------------------------------------------------------
def _docs() -> dict[str, str]:
    root = Path(_SPEC.docs_dir)
    return {f"{C}/{p.relative_to(root).as_posix()}": p.read_text() for p in sorted(root.rglob("*.md"))}


def _schema() -> dict:
    return yaml.safe_load((PKG / "sandbox" / "schemas" / FORK / "schema.yaml").read_text())


def _config_text() -> str:
    return (PKG / "sandbox" / "openspec-config.yaml").read_text()


def _template(name: str) -> str:
    return (PKG / "sandbox" / "schemas" / FORK / "templates" / name).read_text()


def _setup_files() -> dict[str, str]:
    """What setup.sh leaves under /openspec before the agent starts (openspec init + the fork + the config)."""
    out = {f"{ROOT}/config.yaml": _config_text(), f"{ROOT}/changes/archive/.gitkeep": "", f"{ROOT}/specs/.gitkeep": ""}
    base = PKG / "sandbox" / "schemas" / FORK
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out[f"{ROOT}/schemas/{FORK}/{p.relative_to(base).as_posix()}"] = p.read_text()
    return out


_PLANNING_HOME = {"kind": "repo", "root": "/", "changesDir": f"{ROOT}/changes", "defaultSchema": "spec-driven"}
_ROOTREF = {"path": "/", "source": "nearest"}


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def cli_list() -> str:
    return _json({"changes": [], "root": _ROOTREF}) + EXIT0


def cli_new() -> str:
    return f"- Creating change 'issue' with schema 'spec-driven'...\nCreated change 'issue' at {CHG}/\nSchema: {FORK}\nNext: openspec status --change issue" + EXIT0


def cli_status(done: set[str], as_json: bool = True) -> str:
    sch = _schema()
    arts = []
    for a in sch["artifacts"]:
        req = list(a.get("requires") or [])
        missing = [r for r in req if r not in done]
        st = "done" if a["id"] in done else ("ready" if not missing else "blocked")
        row = {"id": a["id"], "outputPath": a["generates"], "status": st, "requires": req}
        if st == "blocked":
            row["missingDeps"] = missing
        arts.append(row)
    if not as_json:
        marks = {"done": "[x]", "ready": "[ ]", "blocked": "[-]"}
        lines = [f"{marks[a['status']]} {a['id']}" for a in arts]
        return "\n".join(["- Loading change status...", "Change: issue", f"Schema: {FORK}", f"Change root: {CHG}", f"Progress: {len(done)}/4 artifacts complete", "", *lines]) + EXIT0
    body = {
        "changeName": "issue",
        "schemaName": FORK,
        "planningHome": _PLANNING_HOME,
        "changeRoot": CHG,
        "artifactPaths": {a["id"]: {"outputPath": a["generates"], "resolvedOutputPath": f"{CHG}/{a['generates']}", "existingOutputPaths": []} for a in sch["artifacts"]},
        "isPlanningComplete": len(done) == 4,
        "applyRequires": ["tasks"],
        "artifacts": arts,
        "root": _ROOTREF,
    }
    return _json(body) + EXIT0


def _context() -> str:
    return yaml.safe_load(_config_text())["context"]


def cli_instructions(aid: str) -> str:
    sch = _schema()
    a = next(x for x in sch["artifacts"] if x["id"] == aid)
    rules = (yaml.safe_load(_config_text()).get("rules") or {}).get(aid)
    body = {
        "changeName": "issue",
        "artifactId": aid,
        "schemaName": FORK,
        "changeDir": CHG,
        "planningHome": _PLANNING_HOME,
        "outputPath": a["generates"],
        "resolvedOutputPath": f"{CHG}/{a['generates']}",
        "description": a["description"],
        "instruction": a["instruction"],
        "context": _context(),
        **({"rules": rules} if rules else {}),
        "template": _template(a["template"]),
        "dependencies": list(a.get("requires") or []),
        "root": _ROOTREF,
    }
    return _json(body) + EXIT0


def cli_apply(tasks_text: str, design: bool) -> str:
    sch = _schema()
    tasks, n = [], 0
    for i, ln in enumerate(tasks_text.splitlines(), start=1):
        s = ln.strip()
        if s.startswith("- [ ] ") or s.startswith("- [x] "):
            n += 1
            tasks.append({"id": str(n), "description": s[6:], "done": s.startswith("- [x]"), "sourcePath": f"{CHG}/tasks.md", "line": i})
    done = sum(t["done"] for t in tasks)
    ctx_files = {"proposal": [f"{CHG}/proposal.md"], "specs": [f"{CHG}/specs/{CAP}/spec.md"], **({"design": [f"{CHG}/design.md"]} if design else {}), "tasks": [f"{CHG}/tasks.md"]}
    body = {
        "changeName": "issue",
        "changeDir": CHG,
        "schemaName": FORK,
        "contextFiles": ctx_files,
        "progress": {"total": len(tasks), "complete": done, "remaining": len(tasks) - done},
        "tasks": tasks,
        "taskTrackingConfigured": True,
        "state": "all_done" if tasks and done == len(tasks) else "ready",
        "instruction": sch["apply"]["instruction"],
        "context": _context(),
        "root": _ROOTREF,
    }
    return _json(body) + EXIT0


def cli_archive_ok(n_req: int, open_tasks: int = 0, total_tasks: int = 4) -> str:
    status = ["Task status: ✓ Complete"] if not open_tasks else [f"Task status: {total_tasks - open_tasks}/{total_tasks} tasks", f"Warning: {open_tasks} incomplete task(s) found. Continuing due to --yes flag."]
    return "\n".join(
        [*status, "", "Specs to update:", f"  {CAP}: create", f"Applying changes to openspec/specs/{CAP}/spec.md:", f"  + {n_req} added", f"Totals: + {n_req}, ~ 0, - 0, → 0", "Specs updated successfully.", f"Change 'issue' archived as '{DATE}-issue'."]
    ) + EXIT0


def cli_archive_fail() -> str:
    return "\n".join(
        [
            "",
            "Validation errors in change delta specs:",
            f"  ✗ {CAP}/spec.md: Requirement 'Unknown words are rejected' must have at least one scenario (scenarios use exactly 4 hashtags: '#### Scenario:')",
            "",
            "Validation failed. Please fix the errors before archiving.",
            "To skip validation (not recommended), use --no-validate flag.",
        ]
    ) + EXIT1


# --------------------------------------------------------------------------------------------
# Explore's one output: the "What We Figured Out" summary (EX:193-207), written in a tool call
# --------------------------------------------------------------------------------------------
def _summary(lean: bool = False) -> str:
    if lean:
        return "\n".join(
            [
                "## What We Figured Out",
                "",
                "**The problem**: `parse_bool` returns `bool(text)` (`tinyconf/values.py:9-11`), so every non-empty string,"
                ' "false" included, is True.',
                "",
                "**Where the change goes**: `parse_bool` in `tinyconf/values.py`: compare the stripped, lower-cased text with"
                " the two word sets and raise ValueError otherwise.",
                "",
                "**Next step**: open /opsx/stages/01-ff.md - ff turns this into a change",
            ]
        )
    return "\n".join(
        [
            "## What We Figured Out",
            "",
            "**The problem**: `parse_bool` returns `bool(text)` (`tinyconf/values.py:9-11`), so every non-empty string --"
            ' "false", "0", "no" included -- is True. The existing tests only cover true words (`tests/test_values.py:8-14`,'
            " 3 passed), which is why nothing caught it.",
            "",
            "**How the area works**: `tinyconf/__init__.py:3` re-exports `parse_bool` and `parse_int` from `values.py`;"
            " `parse_int` strips whitespace (`values.py:4-6`), `parse_bool` does not.",
            "",
            "**Where the change goes**: `parse_bool` in `tinyconf/values.py`. Preferred: two module-level word sets compared"
            " against `text.strip().lower()`, ValueError naming the text otherwise -- matches the issue's lists and"
            " `parse_int`'s whitespace handling. Alternative: `distutils.util.strtobool` -- gone in Python 3.12 and accepts"
            " more words (`y`, `t`) than the issue lists.",
            "",
            "**Assumptions**: surrounding whitespace is ignored, as `parse_int` does (the issue does not say).",
            "",
            "**Open questions**: the exact ValueError message -- the issue only says it names the text; ff settles the format.",
            "",
            "**Next step**: open /opsx/stages/01-ff.md - ff turns this into a change",
        ]
    )


# --------------------------------------------------------------------------------------------
# The artifacts, each its served template with only the placeholders replaced
# --------------------------------------------------------------------------------------------
def _proposal() -> str:
    return "\n".join(
        [
            "# Proposal",
            "",
            "## Why",
            "",
            'parse_bool reads every non-empty string as true, so configuration values such as "false", "0" and "no" turn'
            " features on instead of off. The issue asks for the two word sets and an error for anything else.",
            "",
            "## What Changes",
            "",
            '- parse_bool returns True for "true", "1", "yes", "on" and False for "false", "0", "no", "off", in any case and'
            " with surrounding whitespace ignored.",
            "- Any other text raises ValueError naming the text. **BREAKING** for callers that relied on any non-empty"
            " string being true.",
            "- Assumption (from explore): surrounding whitespace is ignored, as `parse_int` does; the issue does not say.",
            "",
            "## Capabilities",
            "",
            "### New Capabilities",
            f"- `{CAP}`: how configuration text is read as a boolean -- the accepted words and the error for anything else",
            "",
            "### Modified Capabilities",
            "",
            "## Impact",
            "",
            "- `tinyconf/values.py` (`parse_bool`); every caller of `tinyconf.parse_bool`.",
            "- No new dependency.",
            "",
        ]
    )


def _spec(v: set[str], broken: bool = False) -> str:
    unknown_head = "### Scenario: Unknown word" if broken else "#### Scenario: Unknown word"
    return "\n".join(
        [
            "# Spec Delta",
            "",
            "## Purpose",
            "",
            "Defines how configuration text is read as a boolean: which words mean true, which mean false, and what"
            " happens with any other text.",
            "",
            "## ADDED Requirements",
            "",
            "### Requirement: Boolean words are recognised",
            'The system SHALL read "true", "1", "yes" and "on" as true and "false", "0", "no" and "off" as false,'
            " ignoring case and surrounding whitespace.",
            "",
            "#### Scenario: False word",
            '- **WHEN** parse_bool is given "false", "0", "no" or "off" in any case',
            "- **THEN** it returns False",
            "",
            "#### Scenario: True word",
            '- **WHEN** parse_bool is given "TRUE" or " yes "',
            "- **THEN** it returns True",
            "",
            "### Requirement: Unknown words are rejected",
            "The system SHALL raise ValueError naming the text for any input that is not one of the boolean words.",
            "",
            unknown_head,
            '- **WHEN** parse_bool is given "maybe"',
            "- **THEN** it raises ValueError whose message contains 'maybe'",
            "",
        ]
    )


N_REQ = 2


def _design() -> str:
    return "\n".join(
        [
            "# Design",
            "",
            "## Context",
            "",
            "`parse_bool` in `tinyconf/values.py` returns `bool(text)`; see proposal.md - Why. Callers pass raw"
            " configuration strings.",
            "",
            "## Goals / Non-Goals",
            "",
            "**Goals:**",
            "- Map the two word sets case-insensitively and reject anything else.",
            "",
            "**Non-Goals:**",
            "- Accepting other spellings (`enabled`, `y`) or non-string input.",
            "",
            "## Decisions",
            "",
            "- Two module-level sets, `_TRUE` and `_FALSE`, compared against `text.strip().lower()`: simplest, and the"
            " sets document the accepted words. Alternative: `distutils.util.strtobool` -- removed in Python 3.12 and it"
            " accepts more words than the issue lists.",
            "- ValueError carries `repr(text)` so the caller sees the offending value.",
            "",
            "## Risks / Trade-offs",
            "",
            "- [Callers relying on any non-empty string being true now get ValueError] → named in the proposal as"
            " BREAKING; the error message names the text.",
            "",
        ]
    )


REASON = "  Not done: the error message format is undecided; recorded for verify."


def _tasks(ticked: set[str], open_reason: bool = False) -> str:
    def box(tid: str) -> str:
        return "[x]" if tid in ticked else "[ ]"

    lines = [
        "# Tasks",
        "",
        "## 1. Reproduce",
        "",
        f"- {box('1.1')} 1.1 Write the check script {CHECK} for the false words, case and the ValueError, and verify it fails against the current code",
        "",
        "## 2. Word sets and errors",
        "",
        f"- {box('2.1')} 2.1 Map the true and false word sets case-insensitively in tinyconf/values.py and verify the false-word checks of check_parse_bool.py pass",
        f"- {box('2.2')} 2.2 Raise ValueError naming the text for any other input and verify check_parse_bool.py passes in full",
    ]
    if open_reason and "2.2" not in ticked:
        lines.append(REASON)
    lines += [
        f"- {box('2.3')} 2.3 Run `{TEST_CMD}` and verify no existing test regresses",
        "",
        "## Workflow follow-up",
        "",
        "- Archive the change with `openspec archive issue --yes` once verify.md is written.",
        "",
    ]
    return "\n".join(lines)


def _verify(critical: bool, design: bool = True) -> str:
    if critical:
        completeness = "3/4 tasks, 2 reqs"
        correctness = "1/2 reqs covered"
        crit = ["- Incomplete task 2.2 (Raise ValueError naming the text): `tinyconf/values.py:12` still returns False for unknown words."
                " Recommendation: Complete task: raise ValueError naming the text for any other input.",
                "- Requirement not found: Unknown words are rejected. Recommendation: Implement requirement Unknown words are rejected."]
        final = "2 critical issue(s) found. Fix before archiving."
        nxt = "Go to the archive step in `/opsx/core-workflow.md`. Task 2.2 and the requirement Unknown words are rejected stay open, recorded above."
    else:
        completeness = "4/4 tasks, 2 reqs"
        correctness = "2/2 reqs covered"
        crit = ["- None."]
        final = "All checks passed. Ready for archive." if design else "No critical issues found in the checks that ran. Design Adherence not verified: no design.md (optional, not created)."
        nxt = "Go to the archive step in `/opsx/core-workflow.md`."
    return "\n".join(
        [
            "## Verification Report: issue",
            "",
            "### Summary",
            "| Dimension    | Status            |",
            "|--------------|-------------------|",
            f"| Completeness | {completeness} |",
            f"| Correctness  | {correctness}  |",
            "| Coherence    | Followed          |" if design else "| Coherence    | Design Adherence: Not verified (no design.md); patterns consistent |",
            "",
            "### Issues by Priority",
            "",
            "1. **CRITICAL** (Must fix before archive):",
            *[f"   {c}" for c in crit],
            "2. **WARNING** (Should fix):",
            "   - None.",
            "3. **SUGGESTION** (Nice to fix):",
            "   - None.",
            "",
            "### Final Assessment",
            "",
            final,
            "",
            "### Evidence",
            "",
            f"- `{CHECK_CMD}`: {'12/12' if not critical else '11/12'} checks ok; `{TEST_CMD}`: 3 passed.",
            f"- Scenario coverage: False word, True word{', Unknown word' if not critical else ''} -- covered by `check_parse_bool.py`.",
            "- Design adherence: the `_TRUE` / `_FALSE` sets of design.md Decisions are in `tinyconf/values.py:1`." if design else "- Design Adherence: not verified -- the change has no design.md (optional, not created).",
            "- Code pattern consistency: `parse_bool` keeps the module's one-function-per-value style (`tinyconf/values.py:9`).",
            "",
            "### Next step",
            "",
            nxt,
            "",
        ]
    )


def _main_spec() -> str:
    """What `openspec archive` writes for a new capability: the delta's Purpose and its ADDED requirements."""
    delta = _spec(set())
    body = delta.split("## ADDED Requirements", 1)[1].strip("\n")
    purpose = delta.split("## Purpose", 1)[1].split("## ADDED Requirements", 1)[0].strip()
    return f"# {CAP} Specification\n\n## Purpose\n{purpose}\n\n## Requirements\n\n{body}\n"


# --------------------------------------------------------------------------------------------
class _Steps:
    def __init__(self, heredoc: bool = False):
        self.steps: list[Step] = []
        self.heredoc = heredoc

    def add(self, action: Action, *more: Action) -> None:
        self.steps.append(Step(len(self.steps) + 1, [action, *more]))

    def sh(self, command: str, observation: str = "") -> None:
        self.add(Action("shell", "terminal", command=command, observation=observation))

    def write(self, path: str, text: str) -> None:
        if self.heredoc:
            self.sh(f"cat > {path} << 'EOF'\n{text.rstrip(chr(10))}\nEOF", "")
        else:
            self.add(Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}"))

    def replace(self, path: str, old: str, new: str) -> None:
        obs = f"The file {path} has been edited. Here's the result of running `cat -n` on a snippet of {path}. Review the changes and make sure they are as expected."
        self.add(Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation=obs))


def golden(rubric=None, variant: str | None = None):
    """(Run, Collected) of the honest openspec_ff run; ``variant`` picks one of :data:`VARIANTS`.

    ``rubric`` is accepted for the self-test's calling convention and not used: the run comes from the documents alone.
    """
    del rubric
    if variant and variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; known: {VARIANTS}")
    v = {variant} if variant else set()
    crit = "critical_archived" in v
    design = "no_design" not in v
    docs = _docs()
    stage = {k: f"{C}/stages/{n}" for k, n in (("explore", "00-explore.md"), ("ff", "01-ff.md"), ("apply", "02-apply.md"), ("verify", "03-verify.md"))}
    s = _Steps(heredoc="heredoc_writes" in v)
    spec_path = f"{CHG}/specs/{CAP}/spec.md"
    lean = "summary_lean" in v

    s.sh(f"cat {C}/core-workflow.md", docs[f"{C}/core-workflow.md"])
    # ---- explore: read and run what exists, write nothing (CW:60-63, CW:75-78) -----------------------
    s.sh(f"cat {stage['explore']}", docs[stage["explore"]])
    s.sh("cd /testbed && openspec list --json", cli_list())
    s.sh(f"cat {ROOT}/config.yaml", _config_text().rstrip("\n"))
    s.sh("grep -rn 'def parse_bool' --include=*.py .", "./tinyconf/values.py:9:def parse_bool(text):")
    s.sh("cat tinyconf/values.py tinyconf/__init__.py", (VALUES_PY + INIT_PY).rstrip("\n"))
    s.sh("cat tests/test_values.py", TESTS_PY.rstrip("\n"))
    if "explore_runs_tests" in v:
        s.sh(TEST_CMD, PYTEST_OK + EXIT0)  # the existing tests, run as they are (EX:5)
    think = Action("other", "think", text=_summary(lean), observation="Your thought has been logged.")
    read_ff = Action("shell", "terminal", command=f"cat {stage['ff']}", observation=docs[stage["ff"]])
    # ---- ff ----------------------------------------------------------------------------------------
    if "summary_in_ff_turn" in v:
        s.add(think, read_ff)  # the summary's call ahead of the call that opens 01-ff.md, in one turn (EX:191)
    else:
        s.add(think)
        s.add(read_ff)
    s.sh("cd /testbed && openspec list --json", cli_list())
    s.sh('openspec new change "issue"', cli_new())
    s.sh('openspec status --change "issue" --json', cli_status(set()))
    s.sh("grep -rn 'def parse_bool' --include=*.py .", "./tinyconf/values.py:9:def parse_bool(text):")
    s.sh("cat tinyconf/values.py tinyconf/__init__.py", (VALUES_PY + INIT_PY).rstrip("\n"))
    s.sh("cat tests/test_values.py", TESTS_PY.rstrip("\n"))
    s.sh('openspec instructions proposal --change "issue" --json', cli_instructions("proposal"))
    s.write(f"{CHG}/proposal.md", _proposal())
    s.sh('openspec status --change "issue" --json', cli_status({"proposal"}))
    s.sh('openspec instructions specs --change "issue" --json', cli_instructions("specs"))
    s.sh(f"cat {CHG}/proposal.md", _proposal().rstrip("\n"))
    s.sh(f"mkdir -p {CHG}/specs/{CAP}", "")
    broken = "archive_retry" in v
    s.write(spec_path, _spec(v, broken=broken))
    done = {"proposal", "specs"}
    s.sh('openspec status --change "issue" --json', cli_status(done))
    if design:
        s.sh('openspec instructions design --change "issue" --json', cli_instructions("design"))
        s.sh(f"cat {CHG}/proposal.md", _proposal().rstrip("\n"))
        s.write(f"{CHG}/design.md", _design())
        done = done | {"design"}
        s.sh('openspec status --change "issue" --json', cli_status(done))
    else:
        s.sh('openspec instructions design --change "issue" --json', cli_instructions("design"))  # conditional: "create only if any apply"
    s.sh('openspec instructions tasks --change "issue" --json', cli_instructions("tasks"))
    deps = [spec_path, *([f"{CHG}/design.md"] if design else [])]
    s.sh("cat " + " ".join(deps), (_spec(v, broken=broken) + (_design() if design else "")).rstrip("\n"))
    tasks0 = _tasks(set())
    s.write(f"{CHG}/tasks.md", tasks0)
    done = done | {"tasks", "design"}
    s.sh('openspec status --change "issue"', cli_status(done, as_json=False))
    # ---- apply ---------------------------------------------------------------------------------------
    s.sh(f"cat {stage['apply']}", docs[stage["apply"]])
    s.sh('openspec status --change "issue" --json', cli_status(done))
    s.sh('openspec instructions apply --change "issue" --json', cli_apply(tasks0, design))
    ctx = [f"{CHG}/proposal.md", spec_path, *([f"{CHG}/design.md"] if design else []), f"{CHG}/tasks.md"]
    s.sh("cat " + " ".join(ctx), (_proposal() + _spec(v, broken=broken) + (_design() if design else "") + tasks0).rstrip("\n"))
    s.sh(f"mkdir -p {CHG}/checks", "")
    s.write(CHECK, CHECK_PY)
    s.sh(CHECK_CMD, _check_out("none") + EXIT1)
    ticked: set[str] = set()

    def tick(tid: str, reason: bool = False) -> None:
        before = _tasks(ticked, open_reason=reason)
        ticked.add(tid)
        after = _tasks(ticked, open_reason=reason)
        old = next(a for a, b in zip(before.splitlines(), after.splitlines()) if a != b)
        s.replace(f"{CHG}/tasks.md", old + "\n", old.replace("- [ ]", "- [x]", 1) + "\n")
        s.sh('openspec instructions apply --change "issue" --json', cli_apply(_tasks(ticked, open_reason=reason), design))

    tick("1.1")
    s.replace(f"{WORKDIR}/tinyconf/values.py", OLD_BOOL, HALF_BOOL if crit else NEW_BOOL)
    s.sh(CHECK_CMD, _check_out("half" if crit else "full") + (EXIT1 if crit else EXIT0))
    tick("2.1")
    if crit:
        # the task stays impossible here: unchecked, with its one-line reason under it (AP:105)
        s.replace(f"{CHG}/tasks.md", "- [ ] 2.2 Raise ValueError naming the text for any other input and verify check_parse_bool.py passes in full\n",
                  "- [ ] 2.2 Raise ValueError naming the text for any other input and verify check_parse_bool.py passes in full\n" + REASON + "\n")
    else:
        tick("2.2")
    s.sh(TEST_CMD, PYTEST_OK + EXIT0)
    tick("2.3", reason=crit)
    # ---- verify, once (CW:68-71) ---------------------------------------------------------------------
    s.sh(f"cat {stage['verify']}", docs[stage["verify"]])
    s.sh('openspec status --change "issue" --json', cli_status(done))
    cur_tasks = _tasks(ticked, open_reason=crit)
    s.sh('openspec instructions apply --change "issue" --json', cli_apply(cur_tasks, design))
    s.sh("cat " + " ".join(ctx), (_proposal() + _spec(v, broken=broken) + (_design() if design else "") + cur_tasks).rstrip("\n"))
    s.sh("git diff --stat", " tinyconf/values.py | 12 ++++++++++--\n 1 file changed, 10 insertions(+), 2 deletions(-)")
    s.sh(CHECK_CMD, _check_out("half" if crit else "full") + (EXIT1 if crit else EXIT0))
    s.sh(TEST_CMD, PYTEST_OK + EXIT0)
    # whatever the report finds, the next step is the archive (CW:70-71, VF:188): a CRITICAL issue stays recorded
    s.write(f"{CHG}/verify.md", _verify(critical=crit, design=design))
    # ---- archive ---------------------------------------------------------------------------------------
    if broken:
        s.sh("openspec archive issue --yes", cli_archive_fail())
        s.replace(spec_path, "### Scenario: Unknown word\n", "#### Scenario: Unknown word\n")
    s.sh("openspec archive issue --yes", cli_archive_ok(N_REQ, open_tasks=1 if crit else 0))
    s.add(Action("other", "finish"))

    run = Run(instance_id=f"selftest/openspec_ff/{variant or 'golden'}", steps=s.steps)
    rep = replay(run, WORKDIR)
    files = dict(_setup_files())
    for p, t in rep.final.items():
        if t is None or not p.startswith(CHG + "/"):
            continue
        files[ARCH + p[len(CHG) :]] = t
    files[f"{ARCH}/.openspec.yaml"] = f"schema: {FORK}\ncreated: {DATE}\n"
    files[f"{ROOT}/specs/{CAP}/spec.md"] = _main_spec()
    base = {"setup.py": "from setuptools import setup\n\nsetup(name='tinyconf', packages=['tinyconf'])\n", "tinyconf/__init__.py": INIT_PY, "tinyconf/values.py": VALUES_PY, "tests/test_values.py": TESTS_PY}
    collected = simulate(run, workdir=WORKDIR, base_sha=BASE_SHA, base_tree=BASE_TREE, artifact_dirs=(ROOT,), files=files, base_files=base, opaque_commands=True)
    return run, collected


__all__ = ["golden", "VARIANTS", "ISSUE", "WORKDIR", "BASE_SHA", "cli_list", "cli_new", "cli_status", "cli_instructions", "cli_apply", "cli_archive_ok", "cli_archive_fail"]
