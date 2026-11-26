"""Instruction variants of agentos_bugfix for the resolve-rate experiment: ``python build.py`` writes ``variants/<name>/``.

Each variant is agentos_bugfix's documents, instruction and system prompt with a set of candidate changes
applied. A candidate is a letter; a variant is a set of letters. Nothing else differs, and no variant has a
compliance scorer (resolve rate only).

Candidates (what they aim at, measured on the SWE-bench Verified runs of 2026-11-24; record in
``tasks/2026-11-24-agentos-bugfix-instruction-variants/``):

    X  write spec files with the file editor (a heredoc followed by another command is rejected by the terminal)
    A  find the existing tests of the code to change and the command that runs them while planning; record both in spec.md
    L  a test command that does not start is not a result: find how the repository runs its tests and run again
    H  tick the last sub-task / write the report only after the existing tests reported counts after the last change
    E  new tests go into the existing repository test module by default; verify/ only where no module covers the code
    K  in PHASE 3 also run the rest of the test directory the changed code's tests belong to
    F  an existing test that asserts the behavior the task changes may be updated (not in the default set)
    B  reproduce the reported behavior by running code during shape-spec; record it in requirements.md
    M  run the x.1 tests before the change and see them fail
    G  quick checks that need no file (python -c) are allowed at any point
    C  smaller planning documents (fewer questions, shorter requirements.md and spec.md)
    I  no Test Review & Gap Analysis task group in the tasks.md example
    D  keep the default system prompt's testing lines next to the pipeline text
    J  verify/ scripts hold test functions and are run with the test runner
    N  the planning documents state what must hold, not the code change; the code change is decided in implement-tasks
       (third round, 2026-11-25: in blind readings the plan's stated fix decided the outcome, 26/32 solved attempts had
       a plan whose fix would pass against 7/32 unsolved ones; this keeps the four documents and their order and moves
       only the decision)

Structure variants (second round, 2026-11-25) change which documents are written and when, not single sentences.
The sentence variants left the resolve rate of the untrained model where it was, so these place steps between
no workflow and agentos_bugfix. All four keep openhands-sdk's default procedure section in the system prompt
(``structure/default-procedure.txt``) and add a paragraph that points to ``/agent-os/overview.md``; their
hand-written texts are in ``structure/<name>/``:

    s1report  solve the usual way, then write the final verification report only (overview.md is the one document)
    s2after   solve the usual way, then carry out the four commands as the written record of the change
    s3tasks   create-tasks and implement-tasks only: one planning document (tasks.md) before the code
    s4prompt  agentos_bugfix as it is, except that the system prompt keeps the default procedure section (and the one
              overview.md sentence that says the pipeline replaces any other procedure says where its steps are carried out)

    none -> s1report -> s3tasks -> s4prompt -> agentos_bugfix adds one thing per step; s2after against s1report
    shows what the three planning documents cost when they come after the change.

Fourth round (2026-11-26): the cost sits in the planning documents written before the code (about 6 points per
document on the trained model, s1report 63.1 -> s3tasks 57.3 -> s4prompt 51.5), and the same four documents written
after the change cost nothing against no workflow (s2after 58.3). That leaves two readings: the planning procedure
costs, or putting the plan on paper does.

    s5think   s4prompt with the three planning commands carried out in the model's reasoning only: the command
              documents are the control's, read in order before any code change, and no planning file is written
              (the final verification report is the one document). Near s1report: writing the plan down is what
              costs. Near s4prompt: the planning procedure costs, written or not.

Fifth round (2026-11-26): where s3tasks loses against s1report. Of the 58 tasks s1report solved and s3tasks did
not, 41 had the defect of the final patch in the text of tasks.md already (one of two functions named, the wrong
place named), the patch followed the plan, and the plan was almost never revised (task lines added after the first
write in 7.2% of all s3tasks runs). Both variants are s3tasks with the listed sentences changed and nothing else;
their texts are not hand-written but derived from ``structure/s3tasks/`` and s3tasks's command documents by
``S6_EDITS`` / ``S7_EDITS``, so that the difference from s3tasks is what those lists hold:

    s6late    tasks.md moves behind the code change: create-tasks only creates the spec folder and studies the
              change; implement-tasks makes the change (tests first), then writes tasks.md of the change that was
              made and ticks it, then verifies. Same two documents, same rules, same tasks.md format.
    s7noplan  tasks.md stays before the code change but holds no code change: a task group is the tests to write,
              "change the code so that the behavior holds" and the test run. No task names a file, function,
              condition or value. Exploration and the implementation steps are s3tasks's.

    Both near s1report: writing the code change down before the code is what costs, and s7noplan keeps a plan.
    s6late only: any document before the code costs. Both near s3tasks: the cost is in implement-tasks's rules.

``--check`` exits 1 when ``variants/`` is not what this file would write.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "agentos_bugfix"
OUT = HERE / "variants"

VARIANTS: dict[str, str] = {
    "agentos_bugfix_v0base": "X",
    "agentos_bugfix_v1result": "XALH",
    "agentos_bugfix_v2place": "XEK",
    "agentos_bugfix_v3pre": "XBMG",
    "agentos_bugfix_v4docs": "XCI",
    "agentos_bugfix_v5all": "XALHEKBMGCIDJ",
    "agentos_bugfix_v2fplace": "XEKF",  # v2place plus F; not in the default run list
    "agentos_bugfix_p1nofix": "N",  # agentos_bugfix with N only (no X), so that it differs from the control in one thing
}
DEFAULT_RUN = ["agentos_bugfix_v0base", "agentos_bugfix_v1result", "agentos_bugfix_v2place", "agentos_bugfix_v3pre", "agentos_bugfix_v4docs", "agentos_bugfix_v5all"]

# name -> (folder under structure/, command documents shipped)
STRUCTURE: dict[str, tuple[str, list[str]]] = {
    "agentos_bugfix_s1report": ("s1report", []),
    "agentos_bugfix_s2after": ("s2after", ["shape", "write", "tasks", "impl"]),
    "agentos_bugfix_s3tasks": ("s3tasks", ["tasks", "impl"]),
    "agentos_bugfix_s4prompt": ("s4prompt", ["shape", "write", "tasks", "impl"]),
    "agentos_bugfix_s5think": ("s5think", ["shape", "write", "tasks", "impl"]),  # fourth round; not in STRUCTURE_RUN
    "agentos_bugfix_s6late": ("s6late", ["tasks", "impl"]),  # fifth round; derived from s3tasks, not in STRUCTURE_RUN
    "agentos_bugfix_s7noplan": ("s7noplan", ["tasks", "impl"]),  # fifth round; derived from s3tasks, not in STRUCTURE_RUN
}
STRUCTURE_RUN = [n for n in STRUCTURE if n not in ("agentos_bugfix_s5think", "agentos_bugfix_s6late", "agentos_bugfix_s7noplan")]

OVERVIEW = "docs/overview.md"
SHAPE = "docs/commands/shape-spec/shape-spec.md"
WRITE = "docs/commands/write-spec/write-spec.md"
TASKS = "docs/commands/create-tasks/create-tasks.md"
IMPL = "docs/commands/implement-tasks/implement-tasks.md"
SYSTEM = "system-prompt.j2"
FILES = [OVERVIEW, SHAPE, WRITE, TASKS, IMPL, "instruction.md", SYSTEM]
V = "/tmp/agent-os/specs/[this-spec]/verify/"


def edits(f: frozenset[str]) -> list[tuple[str, str, str]]:
    """(file, text in agentos_bugfix, replacement) for the candidate set ``f``; every old text occurs exactly once."""
    on = f.__contains__
    out: list[tuple[str, str, str]] = []

    def add(file: str, old: str, new: str) -> None:
        if old != new:
            out.append((file, old, new))

    # ---------------- overview.md ----------------
    if on("X"):
        add(
            OVERVIEW,
            "No command creates `S/verify/`; make it the first time you need it.",
            "No command creates `S/verify/`; make it the first time you need it. Write every file under `S/` with the\n"
            "file editor's `create` command, one file per call: a terminal call that holds a heredoc followed by\n"
            "another command is rejected as several commands, and nothing is written.",
        )
    if on("E"):
        add(
            OVERVIEW,
            "├── verify/                    the task groups' tests that are written as scripts; any scratch file",
            "├── verify/                    check scripts for code no existing test module covers; any scratch file",
        )
    tests_are = (
        "- The tests the task groups call for are new test functions added to the existing repository test module\n"
        "  that covers the changed code, so that they run together with the tests already there; a script in\n"
        "  `S/verify/` is for code no existing test module covers."
        if on("E")
        else "- The tests the task groups call for are scripts in `S/verify/`, or new test functions added to the\n  existing repository test module that covers the changed code."
    )
    existing_line = (
        " An existing test line is changed only where it\n  asserts the behavior the task asks to change, and then only to assert the new behavior; no other existing\n  test line is changed or removed."
        if on("F")
        else " No existing test line in the repository\n  is changed or removed."
    )
    add(
        OVERVIEW,
        "- The tests the task groups call for are scripts in `S/verify/`, or new test functions added to the\n"
        "  existing repository test module that covers the changed code. No existing test line in the repository\n"
        "  is changed or removed.",
        tests_are + existing_line,
    )
    if on("G"):
        add(
            OVERVIEW,
            "  scripts. They go to `S/`, scratch files to `S/verify/`.",
            "  scripts. They go to `S/`, scratch files to `S/verify/`. A quick check that needs no file (a `python -c`\n"
            "  snippet that runs repository code and prints what it does) is fine at any point of any command, as\n"
            "  often as you need it.",
        )
    if on("H"):
        add(
            OVERVIEW,
            "The run ends with implement-tasks PHASE 3. As soon as `S/verifications/final-verification.md` is written,\ncall `finish`.",
            "The run ends with implement-tasks PHASE 3. The report is written only after the existing tests of the\n"
            "changed code have been run after your last code change and have reported how many pass and fail. As soon\n"
            "as `S/verifications/final-verification.md` is written, call `finish`.",
        )

    if on("N"):
        add(
            OVERVIEW,
            '## What "the feature" is\n',
            "## What the planning documents hold\n\n"
            "`requirements.md`, `spec.md` and `tasks.md` describe the behavior the change must produce: what happens\n"
            "now, what must happen instead and for which inputs, what must stay as it is, and which files and\n"
            "functions are involved. They do not state the code change itself, in code or in words (which condition,\n"
            "value or call becomes what). The code change is decided in implement-tasks PHASE 2, with the code open.\n\n"
            '## What "the feature" is\n',
        )

    # ---------------- shape-spec.md ----------------
    if on("N"):
        add(SHAPE, "2. I'm thinking [specific approach]. Should we [alternative]?", "2. I assume [input or situation] should give [result]. Is that correct, or [alternative]?")
        add(
            SHAPE,
            "- Ask about existing similar features to promote code reuse\n",
            "- `requirements.md` states what must hold and which files are involved, not the code change, in code or in words\n"
            "- Ask about existing similar features to promote code reuse\n",
        )
    if on("B"):
        add(
            SHAPE,
            "Read the raw idea from `[spec-path]/planning/initialization.md` to understand what the user wants to build.\n",
            "Read the raw idea from `[spec-path]/planning/initialization.md` to understand what the user wants to build.\n\n"
            "Then see the reported behavior for yourself: run the code the description is about (a short `python -c` snippet, or a script under `[spec-path]/verify/`) and compare what it does with what the description says it should do. Change nothing in the repository. Keep the command and what it printed for `requirements.md`.\n",
        )
        add(
            SHAPE,
            "## Initial Description\n[User's original spec description from initialization.md]\n",
            "## Initial Description\n[User's original spec description from initialization.md]\n\n"
            "## Observed Behavior\n- Command: [what you ran to see the reported behavior]\n- Observed: [what it printed or raised]\n- Expected: [what the description says should happen]\n[If it could not be run, say why]\n",
        )
    if on("C"):
        add(SHAPE, "generate 4-8 targeted, NUMBERED questions", "generate 2-4 targeted, NUMBERED questions")
        add(
            SHAPE,
            "### Reusability Opportunities\n- (assumed) `[path]` — [Components that might exist already, based on your repository search]\n- [Backend patterns to investigate]\n- [Similar features to model after]\n\n",
            "",
        )
        add(
            SHAPE,
            "\n### Technical Considerations\n- [Integration points mentioned]\n- [Existing system constraints]\n- [Technology preferences stated]\n- [Similar code patterns to follow]\n```",
            "```\n\nKeep `requirements.md` short: a few lines per section.",
        )

    # ---------------- write-spec.md ----------------
    if on("A"):
        add(
            WRITE,
            "Document your findings for use in the specification.\n",
            "Document your findings for use in the specification.\n\n"
            "Also find the existing tests of the code the change will touch: the repository test module(s) that cover it, and the command that runs them in this repository. Look at how the repository itself runs its tests (a runner script such as `runtests.py`, `tox.ini`, `setup.cfg`, a `Makefile`, the contributing guide); the test runner you expect may not be installed. Run that command once now, before anything is changed, and note the command and the counts it reports.\n",
        )
        add(
            WRITE,
            "[repeat for up to 5 existing code areas]\n",
            "[repeat for up to 5 existing code areas]\n\n"
            "## Existing Tests\n- Test module(s): [path of each repository test module that covers the code to change]\n- Command: [the exact command that ran them]\n- Result before the change: [passed / failed / error counts, or why it could not be run]\n",
        )
    if on("N"):
        add(
            WRITE,
            "DO NOT write actual code in the spec.md document. Just describe the requirements clearly and concisely.",
            "DO NOT write actual code in the spec.md document, and do not describe the code change in words either (which condition, value or call changes, and to what). "
            "Describe the behavior the change must produce: what happens now, what must happen instead and for which inputs, and what must stay as it is. "
            "The code change is decided later, during implementation.",
        )
        add(
            WRITE,
            "CONCISE sub-bullet points to clarify specific sub-requirements, design or architectual decisions that go into this requirement, or the technical approach to take when implementing this requirement]",
            "CONCISE sub-bullet points to clarify specific sub-requirements: the inputs or situations this requirement covers and the result each must give. No code change and no technical approach]",
        )
        add(
            WRITE,
            "bullets that describe what this existing code does and how it should be re-used or replicated when building this spec]",
            "bullets that describe what this existing code does and how it is involved in the behavior to change]",
        )
        add(
            WRITE,
            "2. **Do NOT write actual code** in the spec\n",
            "2. **Do NOT write actual code** in the spec, **and do not state the code change in words**: the spec says what must hold, not how the code changes\n",
        )
    if on("C"):
        add(WRITE, "- [Up to 8 CONCISE sub-bullet points", "- [Up to 4 CONCISE sub-bullet points")
        add(WRITE, "[repeat for up to a max of 10 specific requirements]", "[repeat for up to a max of 4 specific requirements]")
        add(WRITE, "[repeat for up to 5 existing code areas]", "[repeat for up to 2 existing code areas]")
        add(WRITE, "- [up to 10 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]", "- [up to 3 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]")

    # ---------------- create-tasks.md ----------------
    if on("N"):
        add(
            TASKS,
            "  - [ ] 1.2 [First change to make] in [path of the file to change]\n    - [details]\n    - Reuse pattern from: [existing code if applicable]\n"
            "  - [ ] 1.3 [Next change to make] in [path of the file to change]\n    - [details]\n",
            "  - [ ] 1.2 [First behavior to make hold] in [path of the file to change]\n    - [the inputs or situations it covers and the result each must give]\n    - Related code: [existing code involved, if any]\n"
            "  - [ ] 1.3 [Next behavior to make hold] in [path of the file to change]\n    - [the inputs or situations it covers and the result each must give]\n",
        )
        add(
            TASKS,
            "- **Group related tasks:** For example,",
            "- **State what each task must achieve, not the code change**: a sub-task says which behavior it makes hold, for which inputs, and in which file. "
            "It does not say which condition, value or call changes to what; how the code changes is decided when the task is implemented.\n"
            "- **Group related tasks:** For example,",
        )
    if on("M"):
        add(
            TASKS,
            "    - Skip exhaustive coverage of all methods and edge cases\n  - [ ] 1.2",
            "    - Skip exhaustive coverage of all methods and edge cases\n    - Run them once before the change and see them fail for the reason the task describes\n  - [ ] 1.2",
        )
    ensure = "    - Run the 2-8 tests written in 1.1 and the existing tests of the changed code"
    if on("A"):
        ensure += " (the command recorded under `## Existing Tests` in spec.md)"
    ensure += "\n    - Do NOT run the entire test suite at this stage"
    if on("H"):
        ensure += "\n    - Tick this sub-task only after the existing tests of the changed code have run and reported how many pass and fail; your own tests passing is not enough"
    add(TASKS, "    - Run the 2-8 tests written in 1.1 and the existing tests of the changed code\n    - Do NOT run the entire test suite at this stage", ensure)
    if on("I"):
        start = "### Testing\n\n#### Task Group 2: Test Review & Gap Analysis"
        end = "- Testing focused exclusively on this spec's feature requirements\n\n"
        add(TASKS, "__BLOCK__" + start + "__TO__" + end, "")
        add(TASKS, "1. [Area of the change] (Task Group 1)\n2. Test Review & Gap Analysis (Task Group 2)\n", "1. [Area of the change] (Task Group 1)\n")
        add(
            TASKS,
            "  - If there is a dedicated test coverage group for filling in gaps in test coverage, this group should add only a maximum of 10 additional tests IF NECESSARY to fill critical gaps\n",
            "",
        )
    if on("M"):
        add(
            TASKS,
            "where each task group starts with writing 2-8 tests (x.1 sub-task) and ends",
            "where each task group starts with writing 2-8 tests and running them once to see them fail (x.1 sub-task) and ends",
        )
    who = "(the x.1 sub-task)" if on("I") else "(the x.1 sub-task, and the additional tests of a test-review group)"
    script = f"a script under `{V}`" + (" holding test functions (`test_*`), run with the repository's test runner so that it reports pass/fail counts" if on("J") else ", run on its own")
    module = "a new test function added to the existing repository test module that covers the changed code"
    if on("E"):
        head = "- **Add these tests to the existing test module**"
        where = f"{module}, run through that module with the test runner; only where no existing test module covers that code is it {script}"
    else:
        head = "- **Write these tests as check scripts or as additions to an existing test module**"
        where = f"{script}, or {module}"
    never = (
        "change an existing test line only where it asserts the behavior the task asks to change, and then only to assert the new behavior; never change or remove any other existing test line"
        if on("F")
        else "never change or remove an existing test line"
    )
    add(
        TASKS,
        f"- **Write these tests as check scripts or as additions to an existing test module**: every test a task group writes (the x.1 sub-task, and the additional tests of a test-review group) is a script under `{V}`, run on its own, or a new test function added to the existing repository test module that covers the changed code; never change or remove an existing test line.",
        f"{head}: every test a task group writes {who} is {where}; {never}.",
    )

    # ---------------- implement-tasks.md ----------------
    if on("N"):
        add(
            IMPL,
            "3. Implement the assigned task group according to requirements and standards\n4. Update `/tmp/agent-os/specs/[this-spec]/tasks.md` to update the tasks you've implemented",
            "3. If the task group changes code, decide the code change now: read the code the task names and choose the change that makes the behavior the task and spec.md describe hold. "
            "The planning documents state what must hold, not how the code changes; that is decided here.\n"
            "4. Implement the assigned task group according to requirements and standards\n5. Update `/tmp/agent-os/specs/[this-spec]/tasks.md` to update the tasks you've implemented",
        )
    first = "writes them first" + (" and runs them once before the change to see them fail" if on("M") else "") + ", as its x.1 sub-task"
    scripts = f"check scripts under `{V}`" + (" holding test functions, run with the test runner" if on("J") else "")
    funcs = "test functions you added to " + ("the existing repository test module that covers the changed code" if on("E") else "an existing repository test module") + ", run through that module with the test runner"
    they = f"they are {funcs}, or {scripts} where no existing test module covers that code" if on("E") else f"they are {scripts}, or {funcs}"
    expected = (
        "An existing test that asserts the behavior the task asks to change is expected to fail: update that test so that it asserts the new behavior, and say so under Notes in the final verification report."
        if on("F")
        else "An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test under Failed Tests in the final verification report, noting that it is an expected failure (it asserts the behavior the task asks to change)."
    )
    add(
        IMPL,
        f"- Running the tests you've written (each implementation task group writes them first, as its x.1 sub-task; they are check scripts under `{V}`, or test functions you added to an existing repository test module, run through that module with the test runner) and the existing tests of the code you changed, and ensuring they pass. An existing test that asserts the behavior the task asks to change is expected to fail: leave your change as it is and list that test under Failed Tests in the final verification report, noting that it is an expected failure (it asserts the behavior the task asks to change).",
        f"- Running the tests you've written (each implementation task group {first}; {they}) and the existing tests of the code you changed, and ensuring they pass. {expected}",
    )
    if on("L"):
        add(
            IMPL,
            "Never make a failing test pass by loosening or removing what it checks.\n",
            "Never make a failing test pass by loosening or removing what it checks.\n"
            "- A test command that does not start (the runner is not installed, the path or the test label is wrong, settings are missing, no test is collected) is neither a failure nor a result. Find how this repository runs its tests and run them again until you have pass/fail counts.\n",
        )
    once = "Run the tests of the changed code once more: the test modules that cover the files you changed" + (" (the command recorded under `## Existing Tests` in spec.md)" if on("A") else "") + ", and the tests you wrote."
    if on("K"):
        once += " Then run, once, the rest of the test directory (or test package) those modules belong to, to catch what the change breaks next to them."
    once += " Run the entire tests suite as well only if it finishes within a few minutes.  Verify how many tests are passing and how many have failed or produced errors."
    add(
        IMPL,
        "Run the tests of the changed code once more: the test modules that cover the files you changed, and the tests you wrote. Run the entire tests suite as well only if it finishes within a few minutes.  Verify how many tests are passing and how many have failed or produced errors.",
        once,
    )
    extra = ""
    if on("L"):
        extra += "A test command that does not start is not a result (see PHASE 2): find how this repository runs its tests and run them again.\n\n"
    if on("H"):
        extra += "Do not go on to Step 3 until the existing tests of the changed code have run after your last code change and have reported how many pass and fail. Your own tests passing is not enough.\n\n"
    if extra:
        add(IMPL, "Include these counts and the list of failed tests in your final verification report.\n\n", "Include these counts and the list of failed tests in your final verification report.\n\n" + extra)

    # ---------------- system-prompt.j2 ----------------
    if on("D"):
        add(
            SYSTEM,
            "   includes a tool call, and finish comes once the final verification report\n   has been written.\n",
            "   includes a tool call, and finish comes once the final verification report\n   has been written.\n"
            "4. Inside that pipeline the usual care about testing still holds:\n"
            "   * For bug fixes: Create tests to verify issues before implementing fixes\n"
            "   * Do not use mocks in tests unless strictly necessary and justify their use when they are used. You must always test real code paths in tests, NOT mocks.\n"
            "   * If the environment is set up to run tests, test your implementation thoroughly, including edge cases.\n",
        )
    return out


def render(flags: str) -> dict[str, str]:
    texts = {name: (SRC / name).read_text() for name in FILES}
    for file, old, new in edits(frozenset(flags)):
        _replace(texts, file, old, new)
    return texts


def _replace(texts: dict[str, str], file: str, old: str, new: str) -> None:
    text = texts[file]
    if old.startswith("__BLOCK__"):
        start, end = old[len("__BLOCK__") :].split("__TO__")
        if text.count(start) != 1 or text.count(end) != 1:
            raise SystemExit(f"{file}: block markers not found exactly once")
        i, j = text.index(start), text.index(end) + len(end)
        texts[file] = text[:i] + new + text[j:]
        return
    if text.count(old) != 1:
        raise SystemExit(f"{file}: expected exactly one occurrence, found {text.count(old)}: {old[:90]!r}")
    texts[file] = text.replace(old, new)


# s3tasks: create-tasks and implement-tasks without spec.md / requirements.md; create-tasks makes the spec folder.
S3_EDITS: list[tuple[str, str, str]] = [
    (TASKS, "create a tasks breakdown from a given spec and requirements for a new feature", "create a tasks breakdown from the task description for a new feature"),
    (
        TASKS,
        "__BLOCK__# PHASE 1: Get Spec Requirements__TO__(`/agent-os/commands/write-spec/write-spec.md`) first.\n",
        "# PHASE 1: Initialize the Spec Folder and Study the Change\n\n"
        "The FIRST STEP is to create the spec folder. Determine a kebab-case spec name from the task description, then create the folder:\n\n"
        "```bash\n"
        "# Get today's date in YYYY-MM-DD format\n"
        "TODAY=$(date +%Y-%m-%d)\n\n"
        "# Determine kebab-case spec name from the task description\n"
        'SPEC_NAME="[kebab-case-name]"\n\n'
        "# Store this path for output\n"
        'SPEC_PATH="/tmp/agent-os/specs/${TODAY}-${SPEC_NAME}"\n\n'
        "# Create the spec folder and the folder for its verification report\n"
        "mkdir -p $SPEC_PATH/verifications\n\n"
        'echo "Created spec folder: $SPEC_PATH"\n'
        "```\n\n"
        "Then study the change: read the task description in the task message again and explore the code it is about in the repository, until you know what has to change and where.\n",
    ),
    (TASKS, "Now that you have the spec.md AND/OR requirements.md, please break those down into", "Now that you know what has to change, please break that down into"),
    (
        TASKS,
        "1. **Analyze spec and requirements**: Read and analyze the spec.md and/or requirements.md to inform the tasks list you will create.",
        "1. **Analyze the task description and the code**: Read and analyze the task description and the code it is about to inform the tasks list you will create.",
    ),
    (
        TASKS,
        "### Step 1: Analyze Spec & Requirements\n\nRead each of these files (whichever are available) and analyze them to understand the requirements for this feature implementation:\n"
        "- `/tmp/agent-os/specs/[this-spec]/spec.md`\n- `/tmp/agent-os/specs/[this-spec]/planning/requirements.md`\n\n",
        "### Step 1: Analyze the Task Description & the Code\n\nGo over the task description and the code you studied in PHASE 1 to understand the requirements for this feature implementation.\n\n",
    ),
    (IMPL, "Now that we have a spec and tasks list ready for implementation", "Now that we have a tasks list ready for implementation"),
    (IMPL, "1. Analyze the provided spec.md and requirements.md", "1. Analyze the task description and the current task group in tasks.md"),
]
PROC = "procedure.txt"  # the paragraph a structure variant adds to the system prompt; a key while its edits are applied
TASKS_MD = "`/tmp/agent-os/specs/[this-spec]/tasks.md`"

# s7noplan: s3tasks whose tasks.md holds no code change. What the change has to achieve and its tests stay in the
# list; which file, function, condition or value changes is not written there. Exploration (create-tasks PHASE 1)
# and the implementation steps (implement-tasks PHASE 2) are s3tasks's, word for word.
S7_EDITS: list[tuple[str, str, str]] = [
    (
        OVERVIEW,
        "PHASE 1 creates the spec folder and studies the change. PHASE 2 breaks the change into task groups\n   of checkbox tasks.",
        "PHASE 1 creates the spec folder and studies the change. PHASE 2 writes task groups of checkbox tasks\n"
        "   that say which behavior has to hold and which tests show it. No task states the code change: not the\n"
        "   file, the function, the condition or the value to change.",
    ),
    (
        OVERVIEW,
        "PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 3\n   verifies the result and writes the final verification report.",
        "PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 2 is\n"
        "   where the code change is decided, with the code open. PHASE 3 verifies the result and writes the\n"
        "   final verification report.",
    ),
    (
        PROC,
        "Before any code changes, create-tasks splits the change into task\ngroups; implement-tasks then builds them and verifies the result.",
        "Before any code changes, create-tasks writes what the change has to\n"
        "achieve as task groups, without the code change itself; implement-tasks\n"
        "then decides the code change, builds it and verifies the result.",
    ),
    (TASKS, "Now that you know what has to change, please break that down into", "Now that you know what the change has to achieve, please break that down into"),
    (
        TASKS,
        "  - [ ] 1.2 [First change to make] in [path of the file to change]\n    - [details]\n    - Reuse pattern from: [existing code if applicable]\n"
        "  - [ ] 1.3 [Next change to make] in [path of the file to change]\n    - [details]\n"
        "  - [ ] 1.4 Ensure the tests of this group pass\n",
        "  - [ ] 1.2 Change the code so that [the behavior to change] holds\n  - [ ] 1.3 Ensure the tests of this group pass\n",
    ),
    (
        TASKS,
        "- **Name the file each change is made in**: every sub-task that changes code names, on its task line, the path in the repository of the file it changes. "
        "A task added while implementing does the same, and is added before that file is edited.",
        "- **Leave the code change out of the tasks list**: a task says which behavior has to hold and which tests show it. "
        "No task names the file, function, condition or value to change, in code or in words; the code change is decided in implement-tasks PHASE 2, with the code open.",
    ),
    (IMPL, "(another file to change, a case the tasks miss)", "(a behavior or a case the tasks miss)"),
]

# s6late: s3tasks with tasks.md written after the code change. create-tasks keeps its PHASE 1; its tasks-list
# section moves into implement-tasks as PHASE 2 (see ``_s6_move``), between the change (PHASE 1) and the
# verification (PHASE 3). The x.1 "tests first" rule, which s3tasks carries in tasks.md, is stated in PHASE 1.
S6_MOVE = ("# PHASE 2: Create Tasks List\n", "## Next step\n", "# PHASE 3: Verify Implementation\n")
S6_TICK = (
    "## Tick the tasks list\n\n"
    f"Once {TASKS_MD} is written, go through it task by task. A task the change covers is ticked (`- [x]`) without changing the code again. "
    "A sub-task whose tests could not be made to pass in five attempts is marked with ⚠️ instead of being ticked.\n\n"
    "Once every task is ticked or marked with ⚠️, continue with PHASE 3 below.\n\n"
)
S6_EDITS: list[tuple[str, str, str]] = [
    (
        OVERVIEW,
        "PHASE 1 creates the spec folder and studies the change. PHASE 2 breaks the change into task groups\n   of checkbox tasks.",
        "Creates the spec folder and studies the change. In this run it writes no task list.",
    ),
    (
        OVERVIEW,
        "PHASE 1 and PHASE 2 implement every task group in order, one group per pass of PHASE 2. PHASE 3\n   verifies the result and writes the final verification report.",
        "PHASE 1 implements the change. PHASE 2 writes the task list of the change that was made, as task\n"
        "   groups of checkbox tasks, and ticks it. PHASE 3 verifies the result and writes the final\n"
        "   verification report.",
    ),
    (OVERVIEW, "PHASE 3\nsends you back to PHASE 2 once when a test fails because of your change.", "PHASE 3\nsends you back to PHASE 1 once when a test fails because of your change."),
    (
        OVERVIEW,
        "├── tasks.md                   create-tasks; implement-tasks ticks its checkboxes and may add tasks",
        "├── tasks.md                   implement-tasks PHASE 2, after the code change; ticked there",
    ),
    (
        OVERVIEW,
        "implement-tasks ticks the checkboxes of `tasks.md`, and adds a task when the change\nneeds work no task covers.",
        "implement-tasks writes `tasks.md` only after the change is made, and ticks\nits checkboxes then.",
    ),
    (
        OVERVIEW,
        "- Progress is kept in the files. The checkboxes in `S/tasks.md` are the record of what has been\n"
        "  implemented; the TaskTracker tool may serve as a private scratch list, but it does not replace ticking\n"
        "  `tasks.md`.",
        "- The record is kept in the files. `S/tasks.md`, written after the change, is the record of what has been\n"
        "  implemented; the TaskTracker tool may serve as a private scratch list, but it does not replace\n"
        "  `tasks.md`.",
    ),
    (
        OVERVIEW,
        "- Only implement-tasks PHASE 2 changes the repository. create-tasks reads the repository and may run\n"
        "  commands in it, but changes nothing. implement-tasks PHASE 3 runs tests and writes its report and\n"
        "  changes no code itself; when a test fails because of your change it sends you back to PHASE 2 once,\n"
        "  and that is the only code change after PHASE 3 has begun.",
        "- implement-tasks PHASE 1 changes the repository. create-tasks reads the repository and may run\n"
        "  commands in it, but changes nothing. implement-tasks PHASE 2 writes the task list and changes no\n"
        "  code. PHASE 3 runs tests and writes its report and changes no code itself; when a test fails because\n"
        "  of your change it sends you back to PHASE 1 once, and that is the only code change after PHASE 3 has\n"
        "  begun.",
    ),
    (
        PROC,
        "Before any code changes, create-tasks splits the change into task\ngroups; implement-tasks then builds them and verifies the result.",
        "create-tasks studies the change; implement-tasks then makes it, writes\nthe task list of what was done, and verifies the result.",
    ),
    # create-tasks: PHASE 1 only
    (
        TASKS,
        "I want you to create a tasks breakdown from the task description for a new feature using the following MULTI-PHASE process and instructions.",
        "I want you to prepare the implementation of a new feature from the task description using the following process and instructions.",
    ),
    (
        TASKS,
        f"Once the tasks list has been created at {TASKS_MD}, open `/agent-os/commands/implement-tasks/implement-tasks.md` and continue with that command.",
        "Once you know what has to change and where, open `/agent-os/commands/implement-tasks/implement-tasks.md` and continue with that command. "
        f"In this run no tasks list is written at this point: {TASKS_MD} is written in implement-tasks PHASE 2, after the change is made.",
    ),
    # implement-tasks: PHASE 1 makes the change, PHASE 2 (moved in from create-tasks) writes and ticks the list
    (
        IMPL,
        "Now that we have a tasks list ready for implementation, we will proceed with implementation of this spec by following this multi-phase process:\n\n"
        "PHASE 1: Determine which task group(s) from tasks.md should be implemented\n"
        "PHASE 2: Implement the given task(s)\n"
        "PHASE 3: After ALL task groups have been implemented, produce the final verification report.",
        "Now that the change has been studied, we will proceed with implementation of this spec by following this multi-phase process:\n\n"
        "PHASE 1: Implement the change\n"
        "PHASE 2: After the change is made and tested, write the tasks list of the change and tick it\n"
        "PHASE 3: After the tasks list is written and ticked, produce the final verification report.",
    ),
    (
        IMPL,
        "__BLOCK__# PHASE 1: Determine Tasks__TO__Add lines only: do not reword or remove the tasks that are there.\n",
        "# PHASE 1: Implement the Change\n\n"
        "Implement the change the task description asks for by following these instructions. "
        f"In this run no tasks list exists while you implement: {TASKS_MD} is written in PHASE 2, after the change is made and tested.\n",
    ),
    (
        IMPL,
        "__BLOCK__1. Analyze the task description and the current task group in tasks.md__TO__checked state: `- [x]`\n",
        "1. Analyze the task description and the code you studied in create-tasks\n"
        "2. Analyze patterns in the codebase according to its built-in workflow\n"
        "3. Write 2-8 focused tests for the behavior to change, before you change the code\n"
        "4. Implement the change according to requirements and standards\n",
    ),
    (IMPL, "(each implementation task group writes them first, as its x.1 sub-task; they are", "(you write them first, before you change the code; they are"),
    (
        IMPL,
        "run the tests again before you tick the task group's last sub-task. Make up to five attempts. If it still does not pass, mark that sub-task's checkbox with ⚠️ instead of ticking it, and go on; do not make a sixth attempt.",
        "run the tests again before you go on to PHASE 2. Make up to five attempts. If it still does not pass, go on, and in PHASE 2 mark the task group's last sub-task with ⚠️ instead of ticking it; do not make a sixth attempt.",
    ),
    (
        IMPL,
        "__BLOCK__IF all tasks are now marked as done__TO__repeat PHASE 2 for the next task group with unchecked tasks.\n",
        "When the change is made and its tests have been run, continue with PHASE 2 (after the standards below).\n",
    ),
    (IMPL, "# PHASE 2: Create Tasks List\n", "# PHASE 2: Write the Tasks List\n"),
    (
        IMPL,
        "Now that you know what has to change, please break that down into an actionable tasks list with strategic grouping and ordering, by following these instructions:",
        "Now that the change is made and tested, please write it down as a tasks list with strategic grouping and ordering, by following these instructions. "
        'The instructions are written for a change that is still to be made ("write tests", "change to make"); read them as describing the change you have made: '
        "the tasks are the work the change consisted of, and the tests of an x.1 sub-task are the tests you wrote in PHASE 1.",
    ),
    (IMPL, "Go over the task description and the code you studied in PHASE 1 to understand", "Go over the task description and the change you made in PHASE 1 to understand"),
    (IMPL, "go back to PHASE 2 once, fix the change,", "go back to PHASE 1 once, fix the change,"),
]
# folder -> (folder under structure/ whose hand-written texts it starts from, its edits)
DERIVED: dict[str, tuple[str, list[tuple[str, str, str]]]] = {"s6late": ("s3tasks", S6_EDITS), "s7noplan": ("s3tasks", S7_EDITS)}
_COMMANDS = {"shape": SHAPE, "write": WRITE, "tasks": TASKS, "impl": IMPL}
_SECTION = ("<PROBLEM_SOLVING_WORKFLOW>\n", "</PROBLEM_SOLVING_WORKFLOW>")


def _s6_move(texts: dict[str, str]) -> None:
    """Take create-tasks's tasks-list section out and put it, with the ticking step, in front of implement-tasks PHASE 3."""
    start, end, before = S6_MOVE
    text = texts[TASKS]
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise SystemExit(f"{TASKS}: tasks-list section not found exactly once")
    i, j = text.index(start), text.index(end)
    texts[TASKS] = text[:i] + text[j:]
    _replace(texts, IMPL, before, text[i:j] + S6_TICK + before)


def render_structure(name: str) -> dict[str, str]:
    """A structure variant's files: agentos_bugfix's, with ``structure/<folder>/`` texts in place of its own."""
    folder, commands = STRUCTURE[name]
    base, derived = DERIVED.get(folder, (folder, []))
    own = HERE / "structure" / base
    texts = {_COMMANDS[c]: (SRC / _COMMANDS[c]).read_text() for c in commands}
    if base == "s3tasks":
        for file, old, new in S3_EDITS:
            _replace(texts, file, old, new)
    for rel, src in ((OVERVIEW, own / "overview.md"), ("instruction.md", own / "instruction.md")):
        texts[rel] = (src if src.is_file() else SRC / rel).read_text()
    if folder == "s4prompt":
        # The control's overview revokes "any procedure you would otherwise follow"; with the default steps kept in
        # the system prompt that sentence would take them back again, so it says where they are carried out instead.
        _replace(texts, OVERVIEW, "it replaces any procedure you would otherwise follow.", "the steps of the procedure in your system prompt are carried out inside it.")
    texts[PROC] = (own / "procedure.txt").read_text()
    if folder == "s6late":
        _s6_move(texts)
    for file, old, new in derived:
        _replace(texts, file, old, new)
    system = (SRC / SYSTEM).read_text()
    a, b = _SECTION
    if system.count(a) != 1 or system.count(b) != 1:
        raise SystemExit(f"{SYSTEM}: procedure section markers not found exactly once")
    i, j = system.index(a) + len(a), system.index(b)
    texts[SYSTEM] = system[:i] + (HERE / "structure" / "default-procedure.txt").read_text() + texts.pop(PROC) + system[j:]
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when variants/ differs from what would be written")
    ap.add_argument("--list", action="store_true", help="print each variant with its candidates and the number of edits")
    args = ap.parse_args()
    stale = []
    for name in [*VARIANTS, *STRUCTURE]:
        flags = VARIANTS.get(name)
        texts = render(flags) if flags is not None else render_structure(name)
        if args.list:
            if flags is not None:
                print(f"{name:28s} {flags:14s} {len(edits(frozenset(flags)))} edits")
            else:
                print(f"{name:28s} {'structure':14s} {len(texts)} files, commands: {', '.join(STRUCTURE[name][1]) or 'none'}")
            continue
        have = {str(q.relative_to(OUT / name)) for q in (OUT / name).rglob("*") if q.is_file()} if (OUT / name).is_dir() else set()
        for extra in sorted(have - set(texts) - {"LICENSE-agent-os"}):
            if args.check:
                stale.append(f"variants/{name}/{extra} (not generated)")
            else:
                (OUT / name / extra).unlink()
        for rel, text in texts.items():
            path = OUT / name / rel
            if args.check:
                if not path.is_file() or path.read_text() != text:
                    stale.append(str(path.relative_to(HERE)))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if not args.check:
            shutil.copyfile(SRC / "LICENSE-agent-os", OUT / name / "LICENSE-agent-os")
    if stale:
        print("stale:\n  " + "\n  ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
