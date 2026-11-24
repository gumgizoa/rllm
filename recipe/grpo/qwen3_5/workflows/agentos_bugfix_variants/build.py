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
}
DEFAULT_RUN = ["agentos_bugfix_v0base", "agentos_bugfix_v1result", "agentos_bugfix_v2place", "agentos_bugfix_v3pre", "agentos_bugfix_v4docs", "agentos_bugfix_v5all"]

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

    # ---------------- shape-spec.md ----------------
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
    if on("C"):
        add(WRITE, "- [Up to 8 CONCISE sub-bullet points", "- [Up to 4 CONCISE sub-bullet points")
        add(WRITE, "[repeat for up to a max of 10 specific requirements]", "[repeat for up to a max of 4 specific requirements]")
        add(WRITE, "[repeat for up to 5 existing code areas]", "[repeat for up to 2 existing code areas]")
        add(WRITE, "- [up to 10 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]", "- [up to 3 concise descriptions of specific features that are out of scope and MUST NOT be built in this spec]")

    # ---------------- create-tasks.md ----------------
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
        text = texts[file]
        if old.startswith("__BLOCK__"):
            start, end = old[len("__BLOCK__") :].split("__TO__")
            if text.count(start) != 1 or text.count(end) != 1:
                raise SystemExit(f"{file}: block markers not found exactly once")
            i, j = text.index(start), text.index(end) + len(end)
            texts[file] = text[:i] + new + text[j:]
            continue
        if text.count(old) != 1:
            raise SystemExit(f"{file}: expected exactly one occurrence, found {text.count(old)}: {old[:90]!r}")
        texts[file] = text.replace(old, new)
    return texts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when variants/ differs from what would be written")
    ap.add_argument("--list", action="store_true", help="print each variant with its candidates and the number of edits")
    args = ap.parse_args()
    stale = []
    for name, flags in VARIANTS.items():
        texts = render(flags)
        if args.list:
            print(f"{name:28s} {flags:14s} {len(edits(frozenset(flags)))} edits")
            continue
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
