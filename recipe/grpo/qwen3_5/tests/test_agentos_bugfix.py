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
    assert "DO NOT attempt to fix any failing tests." in impl  # kept verbatim, as in agentos_v2
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
    assert len(rub["items"]) + len(report["dropped_items"]) == 207 and len(rub["items"]) >= 150


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

