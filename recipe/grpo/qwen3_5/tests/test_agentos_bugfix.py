"""agentos_bugfix: agentos_v2 with the steps a fix does not need cut out (workflows/agentos_bugfix/CHANGES.md).

    AGENT_OS_V2_DIR=/path/to/agent-os-v2.1.1 pytest recipe/grpo/qwen3_5/tests/test_agentos_bugfix.py

The render tests need the same v2.1.1 checkout as test_agentos_v2.py and skip without it.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix import build  # noqa: E402

NAME = "agentos_bugfix"
SPEC = workflows.WORKFLOWS[NAME]
DOCS = SPEC.docs_dir
UPSTREAM = Path(os.environ.get("AGENT_OS_V2_DIR", REPO.parent / "agent-os-v2.1.1"))
needs_upstream = pytest.mark.skipif(
    not (UPSTREAM / build.SOURCES["shape"][0]).is_file() or shutil.which("perl") is None,
    reason=f"no agent-os v2.1.1 checkout at {UPSTREAM} (or no perl)",
)
SECTION = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)
KEPT_STANDARDS = ("global/coding-style", "global/commenting", "global/conventions", "global/error-handling", "global/validation", "testing/test-writing")


def _docs() -> dict[str, str]:
    return {p.relative_to(DOCS).as_posix(): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


@needs_upstream
def test_committed_docs_match_a_fresh_render():
    rendered = build.build(UPSTREAM)
    assert sorted(rendered) == sorted(f"commands/{c}/{c}.md" for c in build.COMMANDS)
    assert build.drift(rendered) == []


@needs_upstream
def test_reworded_source_fails_the_build():
    src = (UPSTREAM / build.SOURCES["impl-3"][0]).read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("impl-3", src.replace("### Step 2: Update roadmap (if applicable)", "### Step 2: Roadmap"))


def test_cut_wording_left_behind_fails_the_build(tmp_path):
    text = (DOCS / "commands/write-spec/write-spec.md").read_text(encoding="utf-8")
    for leftover in ("## User Stories", "Check the visuals folder.", "the issue in `<issue_description>`", "under /testbed"):
        with pytest.raises(ValueError, match="left after conversion"):
            build.finish("write-spec", text + "\n" + leftover + "\n", tmp_path)


def test_the_cut_steps_are_gone_and_the_rest_is_agentos_v2():
    docs = _docs()
    everything = "\n".join(docs.values()) + SPEC.instruction_file.read_text(encoding="utf-8")
    for word in ("visual", "Visual", "roadmap", "Roadmap", "User Stories", "issue_description", "/testbed", "README", "Product Context", "implementation/", "Follow-up", "follow-up"):
        assert word not in everything, word
    shape = docs["commands/shape-spec/shape-spec.md"]
    assert [m for m in re.findall(r"^### (Step \d+)", shape, re.M)] == ["Step 1", "Step 2", "Step 3", "Step 4", "Step 1", "Step 2", "Step 3", "Step 4"]
    assert "### Step 2: Generate First Round of Questions" in shape and shape.count("**Answer:** (assumed)") == 2
    spec = docs["commands/write-spec/write-spec.md"]
    assert re.findall(r"^## (\w[\w ]+)$", spec.split("```markdown")[1].split("```")[0], re.M) == ["Goal", "Specific Requirements", "Existing Code to Leverage", "Out of Scope"]
    tasks = docs["commands/create-tasks/create-tasks.md"]
    assert re.findall(r"^#### (Task Group \d+)", tasks, re.M) == ["Task Group 1", "Task Group 2"]
    assert "never change or remove an existing test line" in tasks
    # T1: while implementing and at the end, the tests written plus the existing tests of the changed code
    assert "Run the 2-8 tests written in 1.1 and the existing tests of the changed code" in tasks and "running ONLY those tests" not in tasks
    assert "Do NOT run the entire test suite at this stage" in tasks
    impl = docs["commands/implement-tasks/implement-tasks.md"]
    assert "## 1. Tasks Verification" in impl and "## 2. Test Suite Results" in impl and "## 3." not in impl
    assert "### Step 2: Run the tests of the changed code" in impl and "### Step 3: Create final verification report" in impl
    assert "and the existing tests of the code you changed, and ensuring they pass" in impl and "Running ONLY the tests" not in impl
    assert "Run the entire tests suite as well only if it finishes within a few minutes." in impl and "so that ALL tests run" not in impl
    # T6: a failure the change causes sends the run back to PHASE 2 once; any other failure is only noted, as upstream
    assert "go back to PHASE 2 once, fix the change, then carry out PHASE 3 again from Step 1" in impl
    assert "`git stash -q && <the test command>; git stash pop -q`" in impl and "Any other failure: DO NOT attempt to fix it." in impl
    # T5: a failing test is fixed before the tick, marked after two attempts
    assert "before you tick the task group's last sub-task" in impl and "or with ⚠️ where a test could not be made to pass" in impl
    # T3: a task the tasks miss is added to tasks.md, then implemented; the one file a later command adds to
    assert "ONLY those task(s) that have been assigned to you" in impl and "add it to `/tmp/agent-os/specs/[this-spec]/tasks.md` first" in impl
    assert "`tasks.md` is the one exception" in docs["core-workflow.md"]
    # T2: the test-writing standard without the three lines that hold tests back
    for gone in ("Write Minimal Tests During Development", "Test Only Core User Flows", "Defer Edge Case Testing"):
        assert gone not in impl, gone
    assert "**Test Behavior, Not Implementation**" in impl and "**Fast Execution**" in impl
    for cmd in build.COMMANDS:
        labels = re.findall(r"^\*\*`agent-os/standards/([\w/-]+)\.md`\*\*$", docs[f"commands/{cmd}/{cmd}.md"], re.M)
        assert labels == (sorted(KEPT_STANDARDS) if cmd == "implement-tasks" else []), (cmd, labels)  # B9: where code is written
        assert ("User Standards & Preferences Compliance" in docs[f"commands/{cmd}/{cmd}.md"]) == (cmd == "implement-tasks")


def test_documents_point_only_at_documents_that_exist():
    docs = _docs()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/agent-os/[\w./-]+\.md", text):
            assert ref.removeprefix("/agent-os/") in docs, f"{name} points at missing {ref}"
    entry = docs["core-workflow.md"]
    for artifact in ("initialization.md", "requirements.md", "spec.md", "tasks.md", "checks/", "verifications/final-verification.md"):
        assert artifact in entry, artifact
    assert "finish" in entry and "task description in the task message" in entry


def test_harness_uploads_every_document_and_the_text_is_its_own():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    assert h._expected_doc_count() == len(_docs()) == 5
    assert SPEC.output_dirs == ("/tmp/agent-os",)
    ours_inst = h.instruction_text()
    ours_sec = SECTION.search(h.system_prompt_file.read_text(encoding="utf-8")).group(0)
    entry = f"{SPEC.container_dir.rstrip('/')}/{SPEC.entry_doc}"
    assert entry in ours_inst and entry in ours_sec
    v2 = workflows.WORKFLOWS["agentos_v2"]
    assert v2.instruction_file.read_text(encoding="utf-8").strip() != ours_inst.strip()
    assert SECTION.search(v2.system_prompt["openhands-sdk"].read_text(encoding="utf-8")).group(0) != ours_sec
    # resolve rate only until reward/rubric.yaml exists, then its scorer
    assert (h.evaluation_policy is None) == (not (RECIPE / "workflows" / NAME / "reward" / "rubric.yaml").is_file())


# ---- the verifier: agentos_v2's rubric without the items of the cut steps (derive_rubric.py)


def test_rubric_is_the_one_derived_from_agentos_v2():
    from recipe.grpo.qwen3_5.workflow_rubric.generator import compile as C
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import derive_rubric as D

    assert D.main(["--check"]) == 0, "rerun derive_rubric.py"
    path = RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"
    assert [p for p in C.check(path, None) if "lock" not in p] == []  # schema, kinds and params; the lock is this workflow's own format
    rub, report = D.derive()
    assert report["items_without_source"] == []
    items = str(rub["items"]) + str(rub["artifacts"]) + str(rub["stages"])
    for word in ("agentos_v2", "visuals", "Roadmap", "User Stories", "implementation_dir"):
        assert word not in items, word
    assert len(rub["items"]) + len(report["dropped_items"]) == 207 + len(D.ADDED) and len(rub["items"]) >= 150  # + the T4, T1 and T5 items
    # a template placeholder whose wording changed here is still a placeholder left in
    residue = next(it for it in rub["items"] if it["id"].endswith("shape_spec.requirements.no_template_residue"))
    assert any("task description or the repository" in x.replace("\\", "") for x in residue["check"]["params"]["patterns"])


def test_adding_a_task_while_implementing_is_allowed_and_rewording_one_is_not():
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward.checks import _only_adds

    assert _only_adds(["a", "b"], ["a", "x", "b", "y"]) and _only_adds(["Total Tasks: 8", "a"], ["Total Tasks: 9", "a", "b"])
    assert not _only_adds(["a", "b"], ["a", "B"]) and not _only_adds(["a", "b"], ["b", "a"]) and not _only_adds(["a", "b"], ["a"])
    rub = G.with_docs(S.load(RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"), RECIPE / "workflows" / NAME)
    assert G.load_plugins(rub) == []
    item = next(it for it in rub.items if it.id.endswith("tasks.later_edits"))
    assert item.check.params.get("additions") is True
    run, col = golden.golden(rub, variant="added_task")
    assert engine.evaluate(rub, run, col).scores.compliance == 1.0
    item.check.params.pop("additions")  # agentos_v2's rule: ticks only
    assert engine.evaluate(rub, run, col).scores.compliance < 1.0


def test_overall_status_must_follow_from_the_section_statuses():
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    impl = (DOCS / "commands/implement-tasks/implement-tasks.md").read_text(encoding="utf-8")
    assert "The **Status** at the top of the report follows from the two sections below it:" in impl  # T4
    rub = G.with_docs(S.load(RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"), RECIPE / "workflows" / NAME)
    assert G.load_plugins(rub) == []
    item = next(it for it in rub.items if it.id.endswith("_report.overall_status"))

    def result(col):
        return engine.evaluate(rub, run, col).results[item.id]

    run, col = golden.golden(rub, variant="suite_failures")  # two failures: Some Failures, Passed with Issues
    assert result(col).status == "pass"
    report = next(p for p in col.files if p.endswith("final-verification.md"))
    col.files[report] = col.files[report].replace("**Status:** ⚠️ Passed with Issues", "**Status:** ✅ Passed", 1)
    assert result(col).status == "fail"  # Passed over a failing suite


def test_one_fix_round_after_a_failing_verification_is_allowed():
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    rub = G.with_docs(S.load(RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"), RECIPE / "workflows" / NAME)
    assert G.load_plugins(rub) == []
    frozen = next(it for it in rub.items if it.id.endswith("_verify.code_frozen"))
    assert frozen.check.params.get("fix_round") is True
    run, col = golden.golden(rub, variant="fix_round")  # failing run, checked against the unchanged code, fixed, run again
    rep = engine.evaluate(rub, run, col)
    assert rep.scores.compliance == 1.0 and rep.results[frozen.id].status == "pass"
    # the same late edit with no failing run before it: PHASE 3 gave no reason to go back
    calm, col2 = golden.golden(rub, variant="fix_round")
    failing = [a for st in calm.steps for a in st.actions if "1 failed, 4 passed" in (a.observation or "")]
    assert len(failing) == 1
    failing[0].observation = failing[0].observation.replace("1 failed, 4 passed", "5 passed").replace("exit code 1", "exit code 0").replace("..F..", ".....")
    res = engine.evaluate(rub, calm, col2).results[frozen.id]
    assert res.status == "fail" and "no failing test run before it" in res.detail
    for it in rub.items:  # agentos_v2's rule: no repository write at all once PHASE 3 has begun
        it.check.params.pop("fix_round", None)
    assert engine.evaluate(rub, run, col).results[frozen.id].status == "fail"


def _scored(variant):
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    rub = G.with_docs(S.load(RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"), RECIPE / "workflows" / NAME)
    assert G.load_plugins(rub) == []
    run, col = golden.golden(rub, variant=variant)
    rep = engine.evaluate(rub, run, col)
    assert not rep.engine_errors, (variant, rep.errors[:2])
    return rub, run, col, rep, {it.id.rsplit(".", 1)[1]: rep.results[it.id] for it in rub.items if it.check.kind.startswith(NAME + ".")}


def test_the_existing_tests_are_run_while_implementing():
    from recipe.grpo.qwen3_5.workflow_rubric import engine

    assert _scored(None)[4]["phase2_run"].status == "pass"
    rub, run, col, rep, res = _scored("no_existing_run")  # the check scripts only; PHASE 3 runs the suite
    assert res["phase2_run"].status == "fail" and res["suite_run"].status == "pass" and rep.scores.compliance < 1.0
    # checking a failure against the unchanged code (git stash, stash pop) is no code change: the runs before it still count
    rub, run, col, rep, res = _scored(None)
    tick = next(n for n, st in enumerate(run.steps) if any(a.kind == "replace" and (a.text or "").startswith("- [x] 2.3 ") for a in st.actions))
    step, action = type(run.steps[0]), type(run.steps[0].actions[0])
    stash = action("shell", "terminal", command="cd /testbed && git stash -q && python -m pytest tests/test_slug.py -q; git stash pop -q", observation=".....\n5 passed in 0.03s\n[Command finished with exit code 0]")
    run.steps.insert(tick, step(0, [stash], ""))
    for n, st in enumerate(run.steps, 1):
        st.n = n
    ids = {it.id.rsplit(".", 1)[1]: it for it in rub.items}
    again = engine.evaluate(rub, run, col).results
    assert again[ids["phase2_run"].id].status == "pass"
    # the same for the check scripts: PHASE 3 of "expected_failure" ends with that check, after the scripts' last runs
    rub, run, col, rep, res = _scored("expected_failure")
    last = next(it for it in rub.items if it.id.endswith("pass_last"))
    assert res["pass_last"].status == "pass"
    last.check.params.pop("fix_round")  # agentos_v2's rule: any repository write makes the earlier runs stale
    assert engine.evaluate(rub, run, col).results[last.id].status == "fail"


def test_a_test_sub_task_is_not_ticked_over_a_failing_test():
    assert _scored(None)[4]["ticked_passing"].status == "pass"
    rub, run, col, rep, res = _scored("tick_failing")  # 2.3 ticked right after the existing tests failed; the report says All Passing
    assert res["ticked_passing"].status == "fail" and "2.3 ticked" in res["ticked_passing"].detail
    # an existing test that asserts the behavior the task changes is left failing and listed in the report
    rub, run, col, rep, res = _scored("expected_failure")
    assert res["ticked_passing"].status == "pass" and "report" in res["ticked_passing"].detail and rep.scores.compliance == 1.0


def test_a_warning_mark_needs_two_failed_attempts():
    assert _scored(None)[4]["warned_after_attempts"].status == "not_applicable"
    assert _scored("warn_task")[4]["warned_after_attempts"].status == "not_applicable"  # PHASE 3's mark on a ticked task is another rule
    rub, run, col, rep, res = _scored("warn_attempts")
    assert res["warned_after_attempts"].status == "pass" and rep.scores.compliance == 1.0
    rub, run, col, rep, res = _scored("warn_no_attempt")  # one failing run, no fix, marked
    assert res["warned_after_attempts"].status == "fail" and "2.3" in res["warned_after_attempts"].detail


def test_a_check_script_left_failing_under_a_warning_mark_is_not_held_against_the_run():
    from recipe.grpo.qwen3_5.workflow_rubric import engine

    rub, run, col, rep, res = _scored("warn_attempts")
    last = next(it for it in rub.items if it.id.endswith("pass_last"))
    assert last.check.params.get("warned") is True and res["pass_last"].status == "pass"
    # the same run with check_sep.py failing from the change on: the mark came after its failing runs
    seen = False
    for st in run.steps:
        for a in st.actions:
            seen = seen or "[^a-z0-9—]+" in (a.text or "")
            if seen and (a.command or "").endswith("checks/check_sep.py"):
                a.observation = "AssertionError: a—b\n[Command finished with exit code 1]"
    marked = engine.evaluate(rub, run, col).results[last.id]
    assert marked.status == "pass", marked.detail
    last.check.params.pop("warned")  # agentos_v2's rule: every script passes at the end
    assert engine.evaluate(rub, run, col).results[last.id].status == "fail"


def test_a_failing_check_script_is_a_failing_test_of_the_change():
    from recipe.grpo.qwen3_5.workflow_rubric import engine

    # the check written for the change fails through two attempts and the one of PHASE 3: ⚠️, Critical Failures, Failed
    rub, run, col, rep, res = _scored("script_failing")
    assert rep.scores.compliance == 1.0
    assert res["suite_status"].status == "pass" and "check script" in res["suite_status"].detail
    assert res["code_frozen"].status == "pass" and res["overall_status"].status == "pass" and res["pass_last"].status == "pass"
    for rule, why in (("_report.suite_status", "has no failure"), ("_verify.code_frozen", "no failing test run before it")):
        it = next(i for i in rub.items if i.id.endswith(rule))
        it.check.params.pop("dir")  # agentos_v2's rule: only the test runner's runs count
        got = engine.evaluate(rub, run, col).results[it.id]
        assert got.status == "fail" and why in got.detail, (rule, got.detail)


def test_golden_run_scores_full_marks():
    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflow_rubric import schema as S
    from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden

    rub = G.with_docs(S.load(RECIPE / "workflows" / NAME / "reward" / "rubric.yaml"), RECIPE / "workflows" / NAME)
    assert G.load_plugins(rub) == []
    for variant in (None, *golden.VARIANTS):
        run, col = golden.golden(rub, variant=variant)
        rep = engine.evaluate(rub, run, col)
        assert not rep.engine_errors, (variant, rep.errors[:2])
        assert rep.scores.compliance >= 0.98, (variant, rep.scores.compliance)



# --------------------------------------------------------------------------------------------
# penalty items (reward/penalty.py): the files tasks.md names, the final patch, the reference fix
# --------------------------------------------------------------------------------------------
def _diff(*paths, new=()):
    out = []
    for p in paths:
        out.append(f"diff --git a/{p} b/{p}\n" + ("new file mode 100644\n" if p in new else "") + f"--- a/{p}\n+++ b/{p}\n@@ -1 +1 @@\n-x\n+y\n")
    return "".join(out)


def _penalty(variant, tmp_path, patch, gold=None):
    """The penalty signals of a golden run whose episode recorded ``patch``, for a task whose reference fix is ``gold``."""
    from types import SimpleNamespace

    from recipe.grpo.qwen3_5.workflow_rubric import engine
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty

    rub, run, col, _rep, _res = _scored(variant)
    if gold is not None:
        (tmp_path / "solution").mkdir(exist_ok=True)
        (tmp_path / "solution" / "gold.patch").write_text(gold, encoding="utf-8")
    col.inputs = penalty.inputs(SimpleNamespace(id="t", task_dir=str(tmp_path), metadata={}), SimpleNamespace(artifacts={"patch": patch}))
    got = penalty.post(engine.evaluate(rub, run, col))
    assert got["penalty_errors"] == 0.0
    return got, {k.rsplit(".", 1)[1]: v for k, v in got.items() if k.startswith(penalty.GROUP + ".")}


def test_penalty_items_pass_on_a_run_that_names_the_files_it_changes(tmp_path):
    got, items = _penalty(None, tmp_path, _diff("textkit/slug.py"), gold=_diff("textkit/slug.py"))
    assert items == {"named": 1.0, "named_equals_patch": 1.0, "named_covers_gold": 1.0, "patch_covers_gold": 1.0}
    assert got["penalty"] == 1.0 and got["penalty_named_files"] == 1.0 and got["penalty_gold_unknown"] == 0.0
    # a task added to tasks.md before its file is edited (implement-tasks PHASE 2) names that file in time
    got, items = _penalty("added_task", tmp_path, _diff("textkit/slug.py", "textkit/__init__.py"), gold=_diff("textkit/slug.py"))
    assert got["penalty_named_files"] == 2.0 and got["penalty_named_late"] == 0.0 and set(items.values()) == {1.0}


def test_penalty_items_against_the_patch_and_the_reference_fix(tmp_path):
    # the patch changes a file no task names; the reference fix is covered all the same (more files are fine)
    got, items = _penalty(None, tmp_path, _diff("textkit/slug.py", "textkit/wrap.py"), gold=_diff("textkit/slug.py"))
    assert items == {"named": 1.0, "named_equals_patch": 0.0, "named_covers_gold": 1.0, "patch_covers_gold": 1.0} and got["penalty"] == 0.75
    # the reference fix changes another file: named and changed as planned, but neither covers it
    got, items = _penalty(None, tmp_path, _diff("textkit/slug.py"), gold=_diff("textkit/slug.py", "textkit/wrap.py"))
    assert items == {"named": 1.0, "named_equals_patch": 1.0, "named_covers_gold": 0.0, "patch_covers_gold": 0.0} and got["penalty"] == 0.5
    # tests, the run's scratch scripts and non-source files are on neither side
    patch = _diff("textkit/slug.py", "tests/test_slug.py", "repro_edges.py", "docs/changes.rst", new=("repro_edges.py",))
    got, items = _penalty(None, tmp_path, patch, gold=_diff("textkit/slug.py", "docs/changes.rst"))
    assert set(items.values()) == {1.0} and got["penalty_patch_files"] == 1.0
    # no code change at all: the named file is not in the patch
    got, items = _penalty(None, tmp_path, "", gold=_diff("textkit/slug.py"))
    assert items == {"named": 1.0, "named_equals_patch": 0.0, "named_covers_gold": 1.0, "patch_covers_gold": 0.0}


def test_penalty_without_a_reference_fix_scores_the_two_items_that_need_none(tmp_path):
    got, items = _penalty(None, tmp_path, _diff("textkit/slug.py"))
    assert items == {"named": 1.0, "named_equals_patch": 1.0} and got["penalty"] == 1.0 and got["penalty_gold_unknown"] == 1.0


def test_named_files_are_collected_over_every_version_of_tasks_md():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty as P

    def tasks(*changes):
        lines = ["#### Task Group 1: Core", "**Dependencies:** None", "", "- [ ] 1.0 Complete the fix", "  - [ ] 1.1 Write 2-8 focused tests for the fix", "    - a check script next to pkg/a.py"]
        lines += [f"  - [ ] 1.{i} {c}" for i, c in enumerate(changes, 2)]
        lines += ["  - [ ] 1.9 Ensure the tests of this group pass", "    - Run tests/test_a.py", "", "**Acceptance Criteria:**", "- pkg/z.py behaves"]
        return "\n".join(lines)

    draft = tasks("Fix the parser in `/testbed/pkg/a.py`\n    - Reuse pattern from: pkg/d.py")
    # only the change tasks count: not the test tasks' files, not what follows a **Label:** line
    assert P.names_in(P.change_text(draft), "/testbed", set()) == {"pkg/a.py", "pkg/d.py"}
    known = {"pkg/a.py", "pkg/b.py", "pkg/d.py"}
    # b.py is added as a task at step 30: before its first edit it is a named file, after it it is not
    added = [(10, draft), (30, tasks("Fix the parser in `/testbed/pkg/a.py`\n    - Reuse pattern from: pkg/d.py", "Update the caller in pkg/b.py"))]
    assert P.named_files(added, {"pkg/a.py": 20, "pkg/b.py": 35}, "/testbed", known) == ({"pkg/a.py", "pkg/d.py", "pkg/b.py"}, set())
    assert P.named_files(added, {"pkg/a.py": 20, "pkg/b.py": 25}, "/testbed", known) == ({"pkg/a.py", "pkg/d.py"}, {"pkg/b.py"})
    # a name removed later stays (d.py: named, never edited), so the plan still differs from the patch
    removed = [(10, draft), (30, tasks("Fix the parser in `/testbed/pkg/a.py`"))]
    named, late = P.named_files(removed, {"pkg/a.py": 20}, "/testbed", known)
    assert named == {"pkg/a.py", "pkg/d.py"} and not late
    assert P.judge(named, ["pkg/a.py"], ["pkg/a.py"], ["pkg/a.py"]) == {"named": 1.0, "named_equals_patch": 0.0, "named_covers_gold": 1.0, "patch_covers_gold": 1.0}
    # a bare file name and a dotted module name denote the file; the run's own check script is not a source file
    text = "- [ ] 1.2 Fix `a.py` (pkg.b.Parser.feed) and rerun check_a.py"
    assert P.names_in(text, "/testbed", known, frozenset({"check_a.py"})) == {"a.py", "pkg/b.py"}
    assert P.match("a.py", "pkg/a.py") and not P.match("a.py", "pkg/ba.py")


def test_a_run_that_names_no_file_fails_the_three_items_about_named_files():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty as P

    assert P.judge(set(), ["pkg/a.py"], ["pkg/a.py"], ["pkg/a.py"]) == {"named": 0.0, "named_equals_patch": 0.0, "named_covers_gold": 0.0, "patch_covers_gold": 1.0}
    assert P.judge(set(), [], [], None) == {"named": 0.0, "named_equals_patch": 0.0, "named_covers_gold": None, "patch_covers_gold": None}


def test_penalty_reads_the_reference_fix_of_both_task_layouts_and_never_raises(tmp_path):
    import json
    from types import SimpleNamespace

    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty as P

    gym, bench = tmp_path / "gym", tmp_path / "bench"
    (gym / "solution").mkdir(parents=True)
    (gym / "solution" / "gold.patch").write_text(_diff("pkg/a.py"), encoding="utf-8")
    (bench / "tests").mkdir(parents=True)
    (bench / "tests" / "config.json").write_text(json.dumps({"patch": _diff("pkg/b.py"), "test_patch": _diff("tests/test_b.py")}), encoding="utf-8")
    assert P.patch_files(P.gold_patch(SimpleNamespace(task_dir=str(gym))))[0] == ["pkg/a.py"]
    assert P.patch_files(P.gold_patch(SimpleNamespace(metadata={"task_path": str(bench)})))[0] == ["pkg/b.py"]
    assert P.gold_patch(SimpleNamespace(metadata={})) is None and P.gold_patch(SimpleNamespace(task_dir=str(tmp_path / "none"))) is None
    # a failure is a full penalty, not a missing signal and not an exception (which would zero compliance with it)
    assert P.post(SimpleNamespace()) == {"penalty": 0.0, "penalty_errors": 1.0}


def test_penalty_is_reported_beside_compliance_and_is_not_the_reward_signal():
    import pickle

    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward.eval import Evaluation

    ev = pickle.loads(pickle.dumps(Evaluation()))  # the policy travels to the Ray actor that scores
    assert ev.inputs is penalty.inputs and ev.post is penalty.post
    assert SPEC.reward_signal == "agentos_bugfix/compliance"
    assert not any(".penalty." in it.id for it in ev.rubric.items)  # the rubric and its compliance are untouched


def _with_spec_path_variable(run, golden):
    """``run`` as an agent that follows shape-spec.md's snippet types it: the spec folder kept in ``$SPEC_PATH``."""
    first = True
    for st in run.steps:
        for a in st.actions:
            if a.kind == "shell" and a.command and golden.S in a.command:
                lines = a.command.split("\n")
                lines[0] = lines[0].replace(golden.S, "$SPEC_PATH")  # the command line; a heredoc's body stays as written
                if first:
                    lines[0], first = f'TODAY=$(date +%Y-%m-%d); SPEC_PATH="/tmp/agent-os/specs/$TODAY-{golden.NAME}"; ' + lines[0], False
                a.command = "\n".join(lines)
    assert not first
    return run


@pytest.mark.parametrize("variant", [None, "heredoc_writes", "sed_ticks", "added_task"])
def test_a_run_that_keeps_the_spec_folder_in_a_shell_variable_scores_like_one_that_types_the_path(variant):
    from recipe.grpo.qwen3_5.workflow_rubric import checks, engine
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty

    rub, run, col, typed, _res = _scored(variant)
    tasks = typed.facts.artifact_paths["tasks"]
    run = _with_spec_path_variable(run, golden)
    rep = engine.evaluate(rub, run, col)
    assert not rep.engine_errors and rep.scores.compliance == typed.scores.compliance == 1.0
    assert [(e.step, e.op, e.content) for e in rep.facts.writes[tasks]] == [(e.step, e.op, e.content) for e in typed.facts.writes[tasks]]
    assert not shell.KNOWN_VARS.get()  # set for the one evaluation only
    assert penalty.versions(rep.facts, col) == penalty.versions(typed.facts, col)
    # without the workflow's variables the replay cannot place those commands, and the honest run loses marks
    fn = checks.SHELL_VARS.pop(NAME)
    try:
        blind = engine.evaluate(rub, run, col)
    finally:
        checks.SHELL_VARS[NAME] = fn
    assert blind.scores.compliance < 0.95


def test_shell_variables_known_from_outside_keep_the_shells_own_rules():
    from recipe.grpo.qwen3_5.workflow_rubric import checks, engine
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix import selftest_golden as golden
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward.checks import spec_folder_vars

    assert checks.SHELL_VARS[NAME] is checks.SHELL_VARS["agentos_v2"] is spec_folder_vars
    rub, run, _col, rep, _res = _scored(None)
    assert spec_folder_vars(rep.facts) == {"SPEC_PATH": golden.S, "DATED_SPEC_NAME": f"{golden.TODAY}-{golden.NAME}", "TODAY": golden.TODAY, "SPEC_NAME": golden.NAME}
    assert engine.known_shell_vars(rub, run, rep.facts) == {}  # the golden run types the path: nothing to replay again
    cmd = "cat > $SPEC_PATH/tasks.md <<EOF\nin ${SPEC_PATH}\nEOF"
    assert [(o.path, o.variable) for o in shell.write_ops(cmd, "/testbed")] == [("", True)]
    token = shell.KNOWN_VARS.set({"SPEC_PATH": "/tmp/agent-os/specs/2026-10-16-x"})
    try:
        (op,) = shell.write_ops(cmd, "/testbed")
        assert (op.path, op.variable, op.body) == ("/tmp/agent-os/specs/2026-10-16-x/tasks.md", False, "in /tmp/agent-os/specs/2026-10-16-x\n")
        # a literal value the command itself gives wins; single quotes and a quoted heredoc are not expanded
        ops = shell.write_ops("SPEC_PATH=/elsewhere; echo hi > $SPEC_PATH/a.txt; cat > '$SPEC_PATH/lit' <<'E'\n$SPEC_PATH\nE", "/testbed")
        assert [o.path for o in ops] == ["/elsewhere/a.txt", "/testbed/$SPEC_PATH/lit"] and ops[1].body == "$SPEC_PATH\n"
        # a value the command line does not show (the snippet's ``$(date ...)``) falls back to the known one
        (op,) = shell.write_ops('TODAY=$(date +%F); SPEC_PATH="/tmp/agent-os/specs/$TODAY-x"; mkdir -p $SPEC_PATH/planning', "/testbed")
        assert op.path == "/tmp/agent-os/specs/2026-10-16-x/planning"
    finally:
        shell.KNOWN_VARS.reset(token)
