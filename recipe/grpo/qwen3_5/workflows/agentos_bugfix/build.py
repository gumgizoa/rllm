"""Build ``docs/commands/`` of agentos_bugfix: the agentos_v2 render with the steps a fix does not need cut out.

    python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream /path/to/agent-os-v2.1.1
    python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.agentos_bugfix.build --list                   # the cuts

The pipeline is agentos_v2's (``..agentos_v2.build``: tag tree -> its tagged edits on the pre-render sources ->
upstream's ``project-install.sh`` -> the four compiled command files -> standards written out). On top of
agentos_v2's edits each source gets the :data:`CUTS` below, and eight more standards are not installed
(:data:`REMOVED`). ``--upstream`` is the same v2.1.1 checkout agentos_v2 uses.

What is cut (user decisions 2026-11-13, ``CHANGES.md``):

* B1 product context: shape-spec's "Analyze Product Context" step (README / docs index / packaging metadata);
* B2 visuals: the visuals folder, the mandatory ``ls``, visual follow-ups, the visual sections of
  requirements.md and spec.md, every "reference the visuals" line;
* B3 roadmap: the verification's roadmap step and the report's Roadmap section;
* B4 standards: the frontend and backend standards (web UI, REST, database);
* B5 user stories: the spec.md section;
* B6 the empty ``implementation/`` folder;
* B7 the web-application tasks example (database / API / UI groups) -> one group in the same shape plus the
  test-review group;
* B8 follow-up questions: shape-spec's follow-up step and the Follow-up Questions section of requirements.md
  (4-7% of runs wrote one; nobody answers, so there is nothing to follow up on);
* B9 the standards in shape-spec, write-spec and create-tasks: they are coding standards, kept where code is
  written (implement-tasks).

And one rule is changed rather than cut:

* T1 test scope: "run ONLY the tests you've written" (while implementing) and "run the entire tests suite" (final
  verification) both become the tests written plus the existing tests of the changed code. Upstream's two ends
  left the existing tests unrun while the code changed and asked for a run at the end that seldom happened
  (6.8% of evaluation runs, a third of them timing out).
* T3 tasks found while implementing: a task the change needs and tasks.md lacks is added to tasks.md and then
  implemented. "ONLY the tasks assigned to you" stays; tasks.md is the one file a later command may add to.
* T2 test-writing standard: its three lines that hold tests back ("write minimal tests", "test only core user
  flows", "defer edge case testing") go. A fix is often about one input's edge behavior, and the test that
  reproduces it is such a test.

And the wording that held for one dataset only is made neutral (G: the ``<issue_description>`` tag and "the
issue" -> the task description in the task message). ``docs/core-workflow.md``, ``instruction.md`` and
``system-prompt.j2`` are hand-written copies of agentos_v2's with the same cuts and wording.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..agentos_v2 import build as base

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs"

COMMANDS = base.COMMANDS
# agentos_v2's sources plus the one standard this workflow edits (T2)
SOURCES = {**base.SOURCES, "std/testing/test-writing": (base.PROFILE + "/standards/testing/test-writing.md",) * 2}
UPSTREAM_COMMIT = base.UPSTREAM_COMMIT

_STD = base.PROFILE + "/standards/"
# B4: not installed, so they drop out of every {{standards/*}} list (agentos_v2 already drops tech-stack, G7-6).
REMOVED = base.REMOVED + tuple(
    _STD + name
    for name in (
        "backend/api.md", "backend/migrations.md", "backend/models.md", "backend/queries.md",
        "frontend/accessibility.md", "frontend/components.md", "frontend/css.md", "frontend/responsive.md",
    )
)

# Wording that must not survive in a shipped command document.
FORBIDDEN = ("visual", "Visual", "roadmap", "Roadmap", "User Stories", "issue_description", "/testbed", "README", "implementation/")

_TASKS_EXAMPLE = """\
### [Area of the change]

#### Task Group 1: [Name of the area]
**Dependencies:** None

- [ ] 1.0 Complete [the change in this area]
  - [ ] 1.1 Write 2-8 focused tests for [the behavior to change]
    - Limit to 2-8 highly focused tests maximum
    - Test only critical behaviors
    - Skip exhaustive coverage of all methods and edge cases
  - [ ] 1.2 [First change to make]
    - [details]
    - Reuse pattern from: [existing code if applicable]
  - [ ] 1.3 [Next change to make]
    - [details]
  - [ ] 1.4 Ensure the tests of this group pass
    - Run the 2-8 tests written in 1.1 and the existing tests of the changed code
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 and the existing tests of the changed code pass
- [what works once this group is done]

### Testing

#### Task Group 2: Test Review & Gap Analysis
**Dependencies:** Task Group 1

- [ ] 2.0 Review existing tests and fill critical gaps only
  - [ ] 2.1 Review tests from Task Group 1
    - Review the 2-8 tests written in Task 1.1
  - [ ] 2.2 Analyze test coverage gaps for THIS feature only
    - Identify critical user workflows that lack test coverage
    - Focus ONLY on gaps related to this spec's feature requirements
    - Do NOT assess entire application test coverage
    - Prioritize end-to-end workflows over unit test gaps
  - [ ] 2.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new tests to fill identified critical gaps
    - Focus on integration points and end-to-end workflows
    - Do NOT write comprehensive coverage for all scenarios
    - Skip edge cases and performance tests unless business-critical
  - [ ] 2.4 Run feature-specific tests only
    - Run ONLY tests related to this spec's feature (tests from 1.1 and 2.3, and the existing tests of the changed code)
    - Do NOT run the entire application test suite
    - Verify critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass
- Critical user workflows for this feature are covered
- No more than 10 additional tests added when filling in testing gaps
- Testing focused exclusively on this spec's feature requirements

## Execution Order

Recommended implementation sequence:
1. [Area of the change] (Task Group 1)
2. Test Review & Gap Analysis (Task Group 2)
"""

# source key -> cuts applied after agentos_v2's edits, in order. ("sub", old, new, note): ``old`` occurs exactly
# once ("all": every occurrence). ("span", start, end, new, note): the text from ``start`` up to (not including)
# ``end`` (``"$"``: the end of the source) -> ``new``.
CUTS: dict[str, tuple[tuple, ...]] = {
    "wf/initialize-spec": (
        ("sub", "Take it from the issue in `<issue_description>`", "Take it from the task description in the task message", "G: dataset-neutral input"),
        ("sub", "4. **Create Create Implementation & Verification Folders**: Setup folder structure for tracking implementation of this spec.",
         "4. **Create Verification Folder**: Set up the folder for this spec's verification report.", "B6: no implementation/ folder"),
        ("sub", "the issue in `<issue_description>` of the task message", "the task description in the task message", "G: dataset-neutral input"),
        ("sub", "mkdir -p $SPEC_PATH/planning/visuals\n", "", "B2: no visuals folder"),
        ("span", "### Step 3: Create Implementation Folder", "### Step 4: Save Raw Idea",
         "### Step 3: Create Verification Folder\n\nCreate the folder `$SPEC_PATH/verifications/`.\n\nLeave this folder empty, for now.\n\n", "B6: only verifications/ is created"),
        ("sub", "Write the issue text from `<issue_description>` to", "Write the task description from the task message to", "G: dataset-neutral input"),
        ("sub", "- Implementation folder should be empty, for now\n", "- Verification folder should be empty, for now\n", "B6"),
    ),
    "wf/research-spec": (
        ("sub", "2. **Analyze Product Context**: Understand product mission, roadmap, and how this feature fits\n", "", "B1: responsibility line"),
        ("sub", "3. **Ask Clarifying Questions**", "2. **Ask Clarifying Questions**", "B1: renumbered"),
        ("sub", "4. **Process Answers**: Analyze responses and any provided visuals", "3. **Process Answers**: Analyze responses", "B1 renumbered; B2"),
        ("sub", "5. **Ask Follow-ups**: Based on answers and visual analysis if needed", "4. **Ask Follow-ups**: Based on answers if needed", "B1 renumbered; B2"),
        ("sub", "6. **Save Requirements**", "5. **Save Requirements**", "B1: renumbered"),
        ("span", "### Step 2: Analyze Product Context", "### Step 3: Generate First Round of Questions", "", "B1: the product-context step"),
        ("sub", "### Step 3: Generate First Round of Questions", "### Step 2: Generate First Round of Questions", "B1: renumbered"),
        ("sub", "reading of the issue and the repository", "reading of the task description and the repository", "G: dataset-neutral input"),
        ("sub", "by looking in the repository yourself (Step 4).", "by looking in the repository yourself (Step 3).", "B1: renumbered"),
        ("sub", "### Step 4: Process Answers and MANDATORY Visual Check", "### Step 3: Process Answers", "B1 renumbered; B2"),
        ("span", "2. **MANDATORY: Check for visual assets regardless of user's response:**", "4. Answer the reusability question by looking in the repository", "", "B2: the mandatory ls and the visual analysis"),
        ("sub", "4. Answer the reusability question by looking in the repository", "2. Answer the reusability question by looking in the repository", "B2: renumbered"),
        ("sub", "### Step 5: Generate Follow-up Questions (if needed)", "### Step 4: Generate Follow-up Questions (if needed)", "B1: renumbered"),
        ("span", "**Visual-triggered follow-ups:**", "**User's Answers-triggered follow-ups:**", "", "B2: visual follow-ups"),
        ("sub", "Based on your answers [and the visual files I found], I have", "Based on your answers, I have", "B2"),
        ("sub", "### Step 6: Save Complete Requirements", "### Step 5: Save Complete Requirements", "B1: renumbered"),
        ("all", "[its basis in the issue or the repository]", "[its basis in the task description or the repository]", "G: dataset-neutral input"),
        ("span", "## Visual Assets", "## Requirements Summary", "", "B2: the Visual Assets section of requirements.md"),
        ("sub", "- **MANDATORY**: Always run bash command to check visuals folder after answering the questions\n", "", "B2"),
        ("sub", "- Visual check is based on actual file(s) found via bash, NOT user statements\n", "", "B2"),
        ("sub", "- Check filenames for low-fidelity indicators and clarify design intent if found\n", "", "B2"),
        ("sub", "- Document all visual findings including fidelity level\n", "", "B2"),
        ("sub", "4. **Ask Follow-ups**: Based on answers if needed\n", "", "B8: responsibility line"),
        ("sub", "5. **Save Requirements**", "4. **Save Requirements**", "B8: renumbered"),
        ("span", "### Step 4: Generate Follow-up Questions (if needed)", "### Step 5: Save Complete Requirements", "", "B8: the follow-up step"),
        ("sub", "### Step 5: Save Complete Requirements", "### Step 4: Save Complete Requirements", "B8: renumbered"),
        ("span", "### Follow-up Questions", "## Requirements Summary", "", "B8: the Follow-up Questions section of requirements.md"),
        ("sub", "- Keep follow-ups minimal (1-3 questions max)\n", "", "B8"),
    ),
    "shape-2": (("span", "{{UNLESS standards_as_claude_code_skills}}", "$", "", "B9: no standards in shape-spec"),),
    "write": (("span", "{{UNLESS standards_as_claude_code_skills}}", "$", "", "B9: no standards in write-spec"),),
    "tasks-2": (("span", "{{UNLESS standards_as_claude_code_skills}}", "$", "", "B9: no standards in create-tasks"),),
    "wf/write-spec": (
        ("sub", "Load and analyze requirements and visual assets thoroughly", "Load and analyze requirements thoroughly", "B2"),
        ("span", "\n# Check for visual assets\n", "```\n\nParse and analyze:", "", "B2: the visuals ls"),
        ("sub", "- Visual mockups or screenshots (if present)\n", "", "B2"),
        ("span", "## User Stories", "## Specific Requirements", "", "B5: the User Stories section of spec.md"),
        ("span", "## Visual Design", "## Existing Code to Leverage", "", "B2: the Visual Design section of spec.md"),
        ("sub", "2. **Reference visual assets** when available\n", "", "B2"),
        ("sub", "3. **Do NOT write actual code** in the spec", "2. **Do NOT write actual code** in the spec", "B2: renumbered"),
        ("sub", "4. **Keep each section short**", "3. **Keep each section short**", "B2: renumbered"),
        ("sub", "5. **Do NOT deviate from the template above**", "4. **Do NOT deviate from the template above**", "B2: renumbered"),
    ),
    "wf/create-tasks-list": (
        ("span", "### Database Layer", "```\n\n**Note**: Adapt this structure", _TASKS_EXAMPLE, "B7: one group in the upstream shape plus the test-review group"),
        ("sub", "  - Each task group (1-3) should write 2-8 focused tests maximum", "  - Each implementation task group should write 2-8 focused tests maximum", "B7: the example has one such group"),
        ("sub", "- **Reference visual assets** if visuals are available\n", "", "B2"),
        ("sub", "  - Test verification should run ONLY the newly written tests, not the entire suite",
         "  - Test verification should run the newly written tests and the existing tests of the changed code, not the entire suite", "T1: test scope"),
        ("sub", "and ends with running ONLY those tests (final sub-task)", "and ends with running those tests and the existing tests of the changed code (final sub-task)", "T1: test scope"),
    ),
    "std/testing/test-writing": (
        ("span", "- **Write Minimal Tests During Development**", "- **Test Behavior, Not Implementation**", "", "T2: the three lines that hold tests back"),
    ),
    "wf/run-all-tests": (
        ("sub", "Run the entire tests suite for the application so that ALL tests run.",
         "Run the tests of the changed code once more: the test modules that cover the files you changed, and the tests you wrote. "
         "Run the entire tests suite as well only if it finishes within a few minutes.", "T1: test scope of the final verification"),
    ),
    "wf/implement-tasks": (
        ("sub", "1. Analyze the provided spec.md, requirements.md, and visuals (if any)", "1. Analyze the provided spec.md and requirements.md", "B2"),
        ("sub", "one task group per pass of PHASE 2.",
         "one task group per pass of PHASE 2. If, while implementing, you find work the change needs that no task covers (another file to change, a case the tasks miss), "
         "add it to `agent-os/specs/[this-spec]/tasks.md` first, as a new sub-task of the current task group or as a new task group at the end, and implement it as an assigned task. "
         "Add lines only: do not reword or remove the tasks that are there.", "T3: a missing task is added to tasks.md, then implemented"),
        ("sub", "- Running ONLY the tests you've written (if any;", "- Running the tests you've written (if any;", "T1: test scope"),
        ("sub", "run through that module with the test runner) and ensuring those tests pass.",
         "run through that module with the test runner) and the existing tests of the code you changed, and ensuring they pass. "
         "An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test in the final verification report.",
         "T1: test scope; an existing test of the old behavior is not a reason to undo the change"),
    ),
    "impl-3": (
        ("span", "### Step 2: Update roadmap (if applicable)", "### Step 3: Run entire tests suite", "", "B3: the roadmap step"),
        ("sub", "### Step 3: Run entire tests suite", "### Step 2: Run the tests of the changed code", "B3: renumbered; T1: test scope"),
        ("sub", "### Step 4: Create final verification report", "### Step 3: Create final verification report", "B3: renumbered"),
    ),
    "wf/verification-report": (
        ("span", "## 2. Roadmap Updates", "## 3. Test Suite Results", "", "B3: the report's Roadmap section"),
        ("sub", "## 3. Test Suite Results", "## 2. Test Suite Results", "B3: renumbered"),
    ),
}


def _once(key: str, text: str, needle: str) -> int:
    n = text.count(needle)
    if n != 1:
        raise ValueError(f"{key}: anchor occurs {n} times (want 1): {needle[:80]!r}")
    return text.index(needle)


def convert(key: str, upstream: str) -> str:
    """One pre-render source with agentos_v2's edits, then this workflow's cuts."""
    text = base.convert(key, upstream)
    for cut in CUTS.get(key, ()):
        if cut[0] in ("sub", "all"):
            _, old, new, _note = cut
            if cut[0] == "sub":
                _once(key, text, old)
            elif old not in text:
                raise ValueError(f"{key}: anchor not found: {old[:80]!r}")
            text = text.replace(old, new)
        else:
            _, start, end, new, _note = cut
            a = _once(key, text, start)
            b = len(text) if end == "$" else text.index(end, a + len(start))
            text = text[:a] + new + text[b:]
    return text


def finish(name: str, text: str, standards: Path) -> str:
    text = base.finish(name, text, standards)
    left = [w for w in FORBIDDEN if w in text]
    if left:
        raise ValueError(f"{name}: cut wording left after conversion: {left}")
    return text


def install(upstream: Path, home: Path, project: Path) -> Path:
    """agentos_v2's install with this workflow's sources and removals; returns the project's ``agent-os/`` folder."""
    root = home / "agent-os"
    shutil.copytree(upstream, root, ignore=shutil.ignore_patterns(".git"))
    for key, (src, dest) in SOURCES.items():
        (root / dest).write_text(convert(key, (upstream / src).read_text(encoding="utf-8")), encoding="utf-8")
    for rel in REMOVED:
        (root / rel).unlink()
    cfg = root / "config.yml"
    text = cfg.read_text(encoding="utf-8")
    for old, new in base.CONFIG:
        if text.count(old) != 1:
            raise ValueError(f"config.yml: {old.strip()!r} occurs {text.count(old)} times (want 1)")
        text = text.replace(old, new)
    cfg.write_text(text, encoding="utf-8")
    project.mkdir(parents=True)
    run = subprocess.run(
        ["bash", str(root / "scripts" / "project-install.sh")],
        cwd=project, env={**os.environ, "HOME": str(home)}, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    if run.returncode != 0:
        raise RuntimeError(f"project-install.sh exited {run.returncode}:\n{run.stdout}\n{run.stderr}")
    if "⚠️ This workflow file was not found" in "".join(
        p.read_text(encoding="utf-8") for p in (project / "agent-os" / "commands").rglob("*.md")
    ):
        raise RuntimeError("project-install.sh: a {{workflows/...}} reference did not resolve")
    return project / "agent-os"


def build(upstream: Path) -> dict[str, str]:
    """Output path (relative to ``docs/``) -> text of the four shipped command documents."""
    with tempfile.TemporaryDirectory(prefix="agentos_bugfix-build-") as tmp:
        installed = install(upstream, Path(tmp) / "home", Path(tmp) / "project")
        out = {}
        for cmd in COMMANDS:
            name = f"commands/{cmd}/{cmd}.md"
            out[name] = finish(name, (installed / name).read_text(encoding="utf-8"), installed / "standards")
        return out


def drift(built: dict[str, str]) -> list[str]:
    """Shipped documents that differ from ``built``, plus any stray file under ``docs/commands/``."""
    bad = [name for name, text in built.items() if not (OUT_DIR / name).is_file() or (OUT_DIR / name).read_text(encoding="utf-8") != text]
    shipped = {p.relative_to(OUT_DIR).as_posix() for p in (OUT_DIR / "commands").rglob("*") if p.is_file()}
    return bad + sorted(shipped - set(built))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", type=Path, help="checkout of agent-os at tag v2.1.1")
    ap.add_argument("--check", action="store_true", help="compare a fresh render with the committed docs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the cuts on top of agentos_v2's edits")
    args = ap.parse_args(argv)
    if args.list:
        for key, cuts in CUTS.items():
            for cut in cuts:
                print(f"  {key:<22} {cut[0]:<4} {cut[-1]}")
        print(f"  removed    {', '.join(r.removeprefix(_STD) for r in REMOVED)}: B4 / G7-6")
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    built = build(args.upstream)
    if args.check:
        bad = drift(built)
        for name in bad:
            print(f"drift: docs/{name}", file=sys.stderr)
        return 1 if bad else 0
    for name, text in built.items():
        dest = OUT_DIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"wrote {dest.relative_to(HERE)} ({text.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
