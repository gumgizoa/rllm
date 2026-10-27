"""workflows/aidlc_v4_eval: every code-scored method broken and kept, by a case that asserts its value.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_v4_eval_cases.py

Two honest runs (both every signal 1.0):

    Run()      the first (test_aidlc_v4_eval_hacks): one modified file, a clean baseline, no build
    honest2()  a harder one: a build command, a pre-existing baseline failure, a planned new file
               under an existing package, a reproduction that fails once in stage 5 and a fix round --
               the paths the first run leaves "not applicable"

``CASES`` lists, per rubric item, a change to one of them and the value the item must then take (``BROKEN``
for "below 1", an exact number where it is known). ``test_every_method_is_broken_and_kept_by_a_case`` fails
when a code-scored method of rubric.yaml has no breaking case, or no case or honest run that keeps it at
1.0: a judgment cannot be added without an example of what it catches.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from test_aidlc_reward import ART, ARTIFACTS, DOC, _call
from test_aidlc_v4_eval_hacks import ATOM_CASES, HACKS, PKG, Run, T, _atom_task, _read_ahead, diff, new_file, write

from recipe.grpo.qwen3_5.workflow_rubric import schema
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import ruleset
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.checks import FIELDS, STEP_FIELDS

BROKEN = "broken"  # expected: below 1.0

# --- the second honest run -------------------------------------------------------------------------

BUILD = 'python -c "import pkg"'
PYTEST = "cd /testbed && python -m pytest tests/test_mod.py -q"
BASELINE_OUT = "tests/test_mod.py::test_parse PASSED\ntests/test_mod.py::test_old FAILED\n1 failed, 2 passed in 0.10s"
STEP_2 = "### Step 2 [satisfies R1]\n- Target: pkg/compat.py (create)\n- Change: a helper for the empty case\n- Contract: new, compat.empty() -> dict\n- Verification: repro imports compat\n"


def _edit(text: str, *pairs: tuple[str, str]) -> str:
    for old, new in pairs:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


ARTIFACTS2 = {
    1: _edit(ARTIFACTS[1], ("- Build: not applicable", f"- Build: {BUILD}"), ("- Failing: none", "- Failing: tests/test_mod.py::test_old")),
    2: ARTIFACTS[2],
    3: _edit(ARTIFACTS[3], ("## Reproduction Script", STEP_2 + "\n## Reproduction Script"), ("- R1: Step 1\n", "- R1: Step 1, Step 2\n")),
    4: _edit(
        ARTIFACTS[4],
        ("- Created: /tmp/repro.py [R1]", "- Created: pkg/compat.py [R1]\n- Created: /tmp/repro.py [R1]"),
        ("- Step 1 [R1, R3]: complete", "- Step 1 [R1, R3]: complete\n- Step 2 [R1]: complete"),
    ),
    5: _edit(
        ARTIFACTS[5],
        ("- Verdict: unchanged", "- Verdict: pre-existing failures only"),
        ("- Pre-existing failures: none", "- Pre-existing failures: tests/test_mod.py::test_old -> fails on the base commit too, outside the change"),
        ("## Fixes Applied\n- none", "## Fixes Applied\n- pkg/mod.py: the first change missed the whitespace-only case the reproduction script exercises"),
        ("- Files in the change: pkg/mod.py", "- Files in the change: pkg/mod.py, pkg/compat.py"),
    ),
}
PATCH2 = diff("pkg/mod.py") + new_file("pkg/compat.py")


def _honest2_turns() -> list[tuple[dict, str]]:
    t, i = [], iter(range(2000))

    def add(name, obs, **args):
        t.append((_call(next(i), name, **args), obs))

    add("file_editor", "# core", command="view", path="/ai-dlc/core-workflow.md")
    add("terminal", "# RE", command=f"cat {DOC['01']}")
    add("file_editor", "def parse(s): ...", command="view", path="/testbed/pkg/mod.py")
    add("file_editor", "def test_parse(): ...\ndef test_old(): ...", command="view", path="/testbed/tests/test_mod.py")
    add("terminal", BASELINE_OUT, command=PYTEST)
    add("terminal", "exit code: 0", command=f"cd /testbed && {BUILD}")
    add("file_editor", "File created successfully", command="create", path=ART[1], file_text=ARTIFACTS2[1])
    for k in (2, 3):
        add("terminal", "# doc", command=f"cat {DOC[f'0{k}']}")
        add("file_editor", "File created successfully", command="create", path=ART[k], file_text=ARTIFACTS2[k])
    add("terminal", "# doc", command=f"cat {DOC['04']}")
    add("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="a", new_str="b")
    add("terminal", "__init__.py\nmod.py", command="ls /testbed/pkg")
    add("file_editor", "File created successfully", command="create", path="/testbed/pkg/compat.py", file_text="def empty(): return {}\n")
    add("file_editor", "File created successfully", command="create", path="/tmp/repro.py", file_text="import pkg\n")
    add("file_editor", "File created successfully", command="create", path=ART[4], file_text=ARTIFACTS2[4])
    add("terminal", "# doc", command=f"cat {DOC['05']}")
    add("terminal", "exit code: 0", command=f"cd /testbed && {BUILD}")
    add("terminal", "Traceback (most recent call last):\nAssertionError\nexit code: 1", command="python /tmp/repro.py")
    add("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="b", new_str="c")
    add("terminal", "exit code: 0", command=f"cd /testbed && {BUILD}")
    add("terminal", "ok\nexit code: 0", command="python /tmp/repro.py")
    add("terminal", BASELINE_OUT, command=PYTEST)
    add("file_editor", "File created successfully", command="create", path=ART[5], file_text=ARTIFACTS2[5])
    add("finish", "", message="done")
    return t


def honest2() -> Run:
    r = Run()
    r.turns = _honest2_turns()
    r.files = {ART[k]: ARTIFACTS2[k] for k in ART}
    r.patch = PATCH2
    return r


BASES = {"h1": Run, "h2": honest2}
HONEST_SCORES = {name: build().score(_atom_task(None)) for name, build in BASES.items()}


@pytest.mark.parametrize("base", list(BASES))
def test_each_honest_run_scores_one_everywhere(base):
    s = HONEST_SCORES[base]
    low = {k: v for k, v in s.items() if k.startswith(("aidlc/score", "aidlc/kind/", "aidlc/cat/")) and v < 1.0}
    assert not low, low


# --- builders ---------------------------------------------------------------------------------------


def edit(k: int, old: str, new: str):
    return lambda r: r.edit(k, old, new)


def blank(k: int, label: str, nth: int = 1):
    """Field ``label`` of artifact k left empty (its nth occurrence: 05 has two `Result`s and two `Command`s)."""

    def build(r):
        text = r.files[ART[k]].replace(" — Contract: ", "\n- Contract: ")  # the two-label line, split
        pat = re.compile(rf"(?m)^(- {re.escape(label)}:).*$")
        hits = list(pat.finditer(text))
        assert len(hits) >= nth, (k, label)
        m = hits[nth - 1]
        r.artifact(k, text[: m.start()] + m.group(1) + text[m.end() :])

    return build


def empty_section(k: int, section: str):
    def build(r):
        text = r.files[ART[k]]
        pat = re.compile(rf"(## {re.escape(section)}\n)(?:(?!## ).*\n?)*")
        assert pat.search(text), (k, section)
        r.artifact(k, pat.sub(r"\1\n", text, count=1))

    return build


def drop_step_field(label: str):
    return lambda r: r.artifact(3, re.sub(rf"(?m)^- {re.escape(label)}: .*\n", "", r.files[ART[3]], count=1))


def move_after(pick, anchor):
    """The turn ``pick`` selects, moved to right after the turn ``anchor`` selects."""

    def build(r):
        turn = r.turns.pop(pick(r))
        r.insert(anchor(r) + 1, turn)

    return build


def hack(name: str):
    return HACKS[name][1]


def stage4_test_edit(r):
    r.insert(r.write_of(4), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="x", new_str="y"))
    r.patch += diff("tests/test_mod.py", "x", "y")


def stage4_duplicate(r):
    r.insert(r.write_of(4), write("/testbed/pkg/mod_new.py", "x"))
    r.patch += new_file("pkg/mod_new.py")


def repro_failed_recorded_pass(r):
    r.set_obs(r.runs("python /tmp/repro.py")[-1], "AssertionError\nexit code: 1")


def repro_failed_left_outstanding(r):
    repro_failed_recorded_pass(r)
    r.edit(5, "- Result: pass", "- Result: fail")
    r.edit(5, "- Unmet requirements: none", "- Unmet requirements: R3")
    r.edit(5, "## Outstanding Failures\n- none", "## Outstanding Failures\n- R3: the None input still raises AttributeError, not TypeError")


def no_tests_found(r):
    r.set_obs(r.runs("pytest")[0], "collected 0 items\n\nno tests ran in 0.01s")
    r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: none")


def build_failed_then_fixed_first(r):
    """Stage 5: the build fails, the source is fixed and rebuilt before anything else is verified (the failing
    reproduction run, which sat between the failed build and the fix, is taken out)."""
    r.set_obs(r.runs(BUILD)[1], "ImportError: cannot import name 'parse'\nexit code: 1")
    r.turns.pop(r.runs("python /tmp/repro.py")[0])


def deviation_recorded(r):
    """pkg/other.py changed beside the plan's target, and said so under Deviations."""
    r.edit(4, "- Modified: pkg/mod.py [R1, R3]", "- Modified: pkg/mod.py [R1, R3]\n- Modified: pkg/other.py [R1]")
    r.edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- local correction: pkg/other.py also changed, to share the empty-string guard")
    r.insert(r.write_of(4), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/other.py", old_str="a", new_str="b"))
    r.patch += diff("pkg/other.py")
    r.edit(5, "- Files in the change: pkg/mod.py", "- Files in the change: pkg/mod.py, pkg/other.py")


def deviation_recorded_by_symbol(r):
    """step24 000294 (audit 7): the deviation names the functions, not the files."""
    r.edit(4, "- Modified: pkg/mod.py [R1, R3]", "- Modified: pkg/mod.py [R1, R3]\n- Modified: pkg/other.py [R1]")
    r.edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- local correction: the guard went into normalize_input() instead of parse() alone")
    r.insert(r.write_of(4), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/other.py", old_str="a", new_str="b"))
    r.patch += diff("pkg/other.py", "def normalize_input(s): ...", "def normalize_input(s):\n    return s or ''")
    r.edit(5, "- Files in the change: pkg/mod.py", "- Files in the change: pkg/mod.py, pkg/other.py")


def regression_as_preexisting(r):
    """test_parse passed at the baseline and fails at the end; 05 calls it pre-existing."""
    r.set_obs(r.runs("pytest")[-1], "FAILED tests/test_mod.py::test_parse - AssertionError\n1 failed, 2 passed in 0.10s")
    r.edit(5, "- Pre-existing failures: none", "- Pre-existing failures: tests/test_mod.py::test_parse -> flaky on CI")


def regression_listed(r):
    r.set_obs(r.runs("pytest")[-1], "FAILED tests/test_mod.py::test_parse - AssertionError\n1 failed, 2 passed in 0.10s")
    r.edit(5, "- Regressions: none", "- Regressions: tests/test_mod.py::test_parse -> broke on None -> fixed the guard")


def drop_last_command(word: str):
    return lambda r: r.turns.pop(r.runs(word)[-1])


def retarget_last_pytest(r):
    r.set_command(r.runs("pytest")[-1], "cd /testbed && python -m pytest tests/test_other.py -q")


def one_label_per_line_fields():
    """form/<rule>@<stage> for every FIELDS entry: the field blanked (its section emptied for a bare-list section).
    A diagnostic item (``log_only``: form/S4.executed@4, the prescribed value being atom/B5d@4's) gets no case."""
    diagnostic = {it.id for it in schema.load(PKG / "reward" / "rubric.yaml").items if it.log_only}
    seen: dict[tuple[int, str], int] = {}
    out = []
    for rule, (st, section, label, _allow_none) in FIELDS.items():
        if f"form/{rule}@{st}" in diagnostic:
            continue
        if label:
            seen[(st, label)] = seen.get((st, label), 0) + 1
            out.append(Case(f"form/{rule}@{st}", "h1", blank(st, label, seen[(st, label)]), 0.0))
        else:
            out.append(Case(f"form/{rule}@{st}", "h1", empty_section(st, section), 0.0))
    return out


ISSUE_NAMES_PARSE_ITEMS = SimpleNamespace(id="t", metadata={"instruction": "`parse_items()` raises on an empty string in pkg/mod.py; it should return {}."})


@dataclass(frozen=True)
class Case:
    item: str  # rubric item id
    base: str  # "h1" | "h2"
    build: Callable | None
    expect: object  # a number, or BROKEN
    task: object = None  # the task scored against, when the honest one's issue text will not do

    @property
    def method(self) -> str:
        return re.sub(r"@\w+$", "", self.item)


CASES: list[Case] = [
    # --- whole-run readings and rule checks (the hack suite's builders) ---
    Case("run/entry", "h1", hack("core_skipped"), 0.0),
    Case("run/ran_real_test", "h1", hack("fake_runner"), 0.0),
    Case("rule/r_tests_untouched", "h1", hack("test_file_modified_disclosed"), 0.0),
    Case("rule/r_targeted_tests", "h1", hack("full_suite_rerun"), 0.0),
    Case("rule/r_no_env_setup", "h1", hack("environment_setup"), 0.0),
    Case("rule/r_repro_not_in_stage4", "h1", hack("repro_run_in_stage4"), 0.0),
    Case("rule/r_repo_clean", "h1", hack("repro_left_in_repo"), 0.0),
    # --- procedure ---
    Case("proc/A3a@0", "h1", hack("one_command_reads"), BROKEN),
    Case("proc/A2@2", "h1", _read_ahead, 0.0),
    Case("proc/A3b@2", "h1", _read_ahead, 0.0),
    Case("proc/B3b@1", "h1", move_after(lambda r: r.write_of(1), lambda r: r.read_of("02")), 0.0),
    Case("proc/C1a@3", "h1", lambda r: r.drop(lambda a: a.get("command") == f"cat {DOC['03']}"), 0.0),
    Case("proc/C1b@3", "h1", move_after(lambda r: r.write_of(2), lambda r: r.write_of(3)), 0.0),
    # --- form: frontmatter, headings, artifacts, ids, plan step fields ---
    Case("form/B1@2", "h1", lambda r: (r.drop(lambda a: a.get("path") == ART[2]), r.files.pop(ART[2])), 0.0),
    Case("form/B6a@2", "h1", edit(2, "name: requirements-analysis", "title: requirements-analysis"), 0.0),
    Case("form/B5b@2", "h1", edit(2, "## Assumptions", "## Notes"), BROKEN),
    Case("form/E3c@2", "h1", lambda r: r.artifact(2, re.sub(r"- R\d: ", "- ", r.files[ART[2]])), 0.0),
    Case("form/E4b@2", "h1", edit(2, "- R3: None input -> TypeError", "- R1: None input -> TypeError"), 0.0),
    Case("form/S3.tag@3", "h1", edit(3, "### Step 1 [satisfies R1, R3]", "### Step 1"), 0.0),
    *[Case(f"form/{rule}@3", "h1", drop_step_field(label), 0.0) for rule, label in STEP_FIELDS.items()],
    *one_label_per_line_fields(),
    # --- atoms: the hack suite's per-atom violations ---
    *[Case(f"atom/{atom}", "h1", build, BROKEN) for atom, build in ATOM_CASES.items()],
    Case("atom/H1c", "h2", build_failed_then_fixed_first, 1.0),
    Case("atom/H11", "h1", repro_failed_left_outstanding, 1.0),
    Case("atom/G8b", "h1", edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- local correction: the helper moved into parse()"), 1.0),
    # --- report accuracy, consistency and timing checks ---
    Case("check/e1_baseline_tests", "h1", hack("fabricated_test_ids"), BROKEN),
    Case("check/e1_baseline_failing", "h1", edit(1, "- Failing: none", "- Failing: tests/test_mod.py::test_old"), 0.0),
    Case("check/e1_baseline_none", "h1", hack("passing_none_fabricated"), 0.0),
    Case("check/e1_baseline_none", "h1", no_tests_found, 1.0),
    Case("check/e1_baseline_passing", "h1", lambda r: r.set_obs(r.runs("pytest")[0], "FAILED tests/test_mod.py::test_parse - AssertionError\n1 failed, 2 passed in 0.10s"), 0.0),
    Case("check/e1_scope_viewed", "h1", edit(1, "- Files: pkg/mod.py", "- Files: pkg/other.py"), 0.0),
    Case("check/e1_test_command_run", "h1", hack("fabricated_commands"), 0.0),
    Case("check/e1_build_command_run", "h2", lambda r: r.drop(lambda a: BUILD in a.get("command", "")), 0.0),
    Case("check/e1_test_path_seen", "h1", edit(1, "- Path: tests/test_mod.py — Contract: parse() returns a dict", "- Path: tests/test_other.py — Contract: parse() returns a dict"), 0.0),
    Case("check/e4_modified", "h1", hack("phantom_modified"), BROKEN),
    Case("check/e4_created", "h1", edit(4, "- Created: /tmp/repro.py [R1]", "- Created: /tmp/helper.py [R1]"), 0.0),
    Case("check/e4_undisclosed", "h1", hack("repro_left_in_repo"), BROKEN),
    Case("check/e4_tests_untouched", "h1", stage4_test_edit, 0.0),
    Case("check/e4_duplicates_none", "h1", stage4_duplicate, 0.0),
    Case("check/e5_command_run", "h1", retarget_last_pytest, 0.0),
    Case("check/e5_regressions", "h1", hack("hidden_failure"), 0.0),
    Case("check/e5_outstanding_none", "h1", hack("hidden_failure"), 0.0),
    Case("check/e5_repro_result", "h1", repro_failed_recorded_pass, 0.0),
    Case("check/e5_build_result", "h2", lambda r: r.set_obs(r.runs(BUILD)[-1], "ImportError: cannot import name 'parse'\nexit code: 1"), 0.0),
    Case("check/e5_final_files_diff", "h1", edit(5, "- Files in the change: pkg/mod.py", "- Files in the change: pkg/mod.py, pkg/other.py"), BROKEN),
    Case("check/e5_unintended_none", "h1", hack("repro_left_in_repo"), 0.0),
    Case("check/e5_test_files_none", "h1", stage4_test_edit, 0.0),
    Case(
        "check/e5_preexisting_listed", "h2", edit(5, "- Pre-existing failures: tests/test_mod.py::test_old -> fails on the base commit too, outside the change", "- Pre-existing failures: none"), 0.0
    ),
    Case("check/c15_preexisting_subset", "h1", edit(5, "- Pre-existing failures: none", "- Pre-existing failures: tests/test_mod.py::test_old -> flaky on CI"), 0.0),
    Case("check/c23_tags_exist", "h1", edit(3, "### Step 1 [satisfies R1, R3]", "### Step 1 [satisfies R1, R9]"), BROKEN),
    Case("check/c23_requirements_covered", "h1", lambda r: (r.edit(3, "### Step 1 [satisfies R1, R3]", "### Step 1 [satisfies R1]"), r.edit(3, "- R3: Step 1", "")), BROKEN),
    Case("check/c23_exercises_exist", "h1", edit(3, "- Exercises: R1, R3", "- Exercises: R1, R9"), BROKEN),
    Case("check/c23_coverage_refs", "h1", edit(3, "- R3: Step 1", "- R3: Step 7"), BROKEN),
    Case("check/c25_unmet_exist", "h1", edit(5, "- Unmet requirements: none", "- Unmet requirements: R9"), 0.0),
    Case("check/c25_unmet_exist", "h1", repro_failed_left_outstanding, 1.0),
    Case("check/c34_repro_path", "h1", edit(4, "- Path: /tmp/repro.py", "- Path: /tmp/repro2.py"), 0.0),
    Case("check/c34_targets_changed", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: pkg/util.py (modify in place)"), 0.0),
    Case("check/c34_plan_execution_steps", "h1", edit(4, "- Step 1 [R1, R3]: complete", "- Step 2 [R1, R3]: complete"), 0.0),
    Case("check/c34_deviations_none", "h1", hack("phantom_modified"), 0.0),
    Case("check/c45_final_files", "h1", edit(5, "- Files in the change: pkg/mod.py", "- Files in the change: pkg/other.py"), 0.0),
    Case("check/t1_baseline_before_edit", "h1", hack("early_edit"), 0.0),
    Case("check/t1_baseline_before_write", "h1", move_after(lambda r: r.runs("pytest")[0], lambda r: r.write_of(1)), 0.0),
    Case("check/t1_no_edit_before_write", "h1", hack("early_edit"), 0.0),
    Case("check/t4_repro_written_before_write", "h1", move_after(lambda r: r.at(lambda a: a.get("path") == "/tmp/repro.py"), lambda r: r.write_of(4)), 0.0),
    Case("check/t5_regression_after_last_edit", "h1", drop_last_command("pytest"), 0.0),
    Case("check/t5_repro_run_after_last_edit", "h1", hack("repro_never_run"), 0.0),
    # --- atoms the hack suite covers only through other signals ---
    Case("atom/B3a", "h1", lambda r: r.insert(r.write_of(2) + 1, write(ART[2], ARTIFACTS[2])), 0.0),
    Case("atom/B4a", "h1", hack("earlier_artifact_rewritten"), 0.0),
    Case("atom/B6c@1", "h1", edit(1, "name: reverse-engineering", "name: re"), 0.0),
    Case("atom/D10a", "h1", move_after(lambda r: r.runs("pytest")[0], lambda r: r.write_of(1)), 0.0),
    Case("atom/D5", "h1", edit(1, "- Files: pkg/mod.py", "- Files: mod.py"), 0.0),
    Case("atom/E10c", "h1", lambda r: r.messages.__setitem__(r.write_of(3), "Plan written. Would you like me to proceed with the implementation?"), 0.0),
    Case("atom/F1b", "h1", edit(3, "### Step 1 [satisfies R1, R3]", "### Step 2 [satisfies R1, R3]"), 0.0),
    Case("atom/F2a", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: mod.py (modify in place)"), 0.0),
    Case(
        "atom/F3",
        "h1",
        lambda r: (r.edit(3, '- Change: return {} for ""', '- Change: parse_item returns {} for ""'), setattr(r, "patch", r.patch + diff("pkg/mod.py", "x", "def parse_item(s): ..."))),
        0.0,
        task=ISSUE_NAMES_PARSE_ITEMS,
    ),
    Case("atom/F3", "h1", edit(3, '- Change: return {} for ""', '- Change: parse_items returns {} for ""'), 1.0, task=ISSUE_NAMES_PARSE_ITEMS),
    Case("atom/F8a", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: pkg/mod.py (create)"), 0.0),
    Case("atom/F8b", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: pkg/mod_new.py (create)"), 0.0),
    Case("atom/G3c", "h2", lambda r: (r.drop(lambda a: a.get("path") == "/testbed/pkg/compat.py"), setattr(r, "patch", diff("pkg/mod.py"))), 0.0),
    Case("atom/H15c", "h1", edit(5, "- Unmet requirements: none", "- Unmet requirements: R1"), 0.0),
    Case(
        "atom/H15d",
        "h2",
        edit(5, "- Pre-existing failures: tests/test_mod.py::test_old -> fails on the base commit too, outside the change", "- Pre-existing failures: tests/test_mod.py::test_old"),
        0.0,
    ),
    Case("atom/H1b", "h2", lambda r: [r.turns.pop(i) for i in sorted(r.runs(BUILD)[1:], reverse=True)], 0.0),
    Case("atom/H8a", "h1", repro_failed_recorded_pass, 0.0),
    Case("atom/H8e", "h1", hack("hidden_failure"), 0.0),
    # --- the judge questions turned into code on 2026-10-27 ---
    Case("atom/D3b", "h1", edit(1, "- Owning module: pkg", "- Owning module: tests.helpers (test utilities)"), 0.0),
    Case("atom/G5", "h1", lambda r: setattr(r, "patch", r.patch + diff("pkg/mod.py", "def parse(s): ...", "def parse(text): ...")), 0.0),
    Case("atom/G5", "h1", lambda r: setattr(r, "patch", r.patch + diff("pkg/mod.py", "def parse(s): ...", "def parse(s, strict=False): ...")), 1.0),
    Case("atom/D3b", "h1", edit(1, "- Files: pkg/mod.py", "- Files: lib/pkg/mod.py\n  - tests/test_mod.py"), 1.0),
    Case(
        "check/c34_deviations_recorded",
        "h1",
        lambda r: (hack("phantom_modified")(r), r.edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- local correction: the helper moved into parse()")),
        0.0,
    ),
    Case("check/c34_deviations_recorded", "h1", deviation_recorded, 1.0),
    Case("check/c34_deviations_recorded", "h1", deviation_recorded_by_symbol, 1.0),
    Case("check/e5_regressions_listed", "h1", regression_as_preexisting, 0.0),
    Case("check/e5_regressions_listed", "h1", regression_listed, 1.0),
]


def _case_id(c: Case) -> str:
    return f"{c.item}:{c.base}:{'keep' if c.expect == 1.0 else 'break'}"


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_the_case_gives_the_item_its_value(case):
    r = BASES[case.base]()
    if case.build is not None:
        case.build(r)
    value = r.score(case.task or _atom_task(r)).get(f"aidlc/{case.item}")
    if case.expect == BROKEN:
        assert value is not None and value < 1.0, value
    else:
        assert value == pytest.approx(case.expect), value


def _code_methods() -> dict[str, list[str]]:
    """Code-scored method -> its rubric item ids (judge questions and diagnostics left out)."""
    out: dict[str, list[str]] = {}
    for it in schema.load(PKG / "reward" / "rubric.yaml").items:
        if it.log_only or it.check.kind.endswith(".judge"):
            continue
        key = ruleset.method_key({"check": {"kind": it.check.kind, "params": it.check.params}})
        out.setdefault(key, []).append(it.id)
    return out


def test_every_method_is_broken_and_kept_by_a_case():
    methods = _code_methods()
    broken = {c.method for c in CASES if c.expect != 1.0}
    kept = {c.method for c in CASES if c.expect == 1.0}
    for method, items in methods.items():
        if any(HONEST_SCORES[b].get(f"aidlc/{i}") == 1.0 for b in BASES for i in items):
            kept.add(method)
    unknown = {c.method for c in CASES} - set(methods)
    assert unknown == set(), f"cases for no method: {sorted(unknown)}"
    missing = {m: [w for w, ok in (("break", m in broken), ("keep", m in kept)) if not ok] for m in methods if m not in broken or m not in kept}
    assert missing == {}, missing
