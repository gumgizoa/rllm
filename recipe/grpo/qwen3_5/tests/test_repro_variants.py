"""speckit_bug_repro / aidlc_v5_repro: the originals with the reproduction run moved in front of the plan.

    pytest recipe/grpo/qwen3_5/tests/test_repro_variants.py

A variant is its original's ``SPEC`` with another ``docs_dir``. These tests hold the copy to the original
everywhere the variant does not mean to differ, so an edit to the original that is not carried over shows up.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE.parents[2]))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward import skeleton  # noqa: E402

# variant -> (original, the documents it edits)
VARIANTS = {
    "speckit_bug_repro": ("speckit_bug", {"stages/01-assess.md"}),
    "aidlc_v5_repro": ("aidlc_v5", {"core-workflow.md", "rule-details/01-reverse-engineering.md", "rule-details/03-code-generation-planning.md"}),
}


def _docs(name: str) -> dict[str, bytes]:
    root = workflows.WORKFLOWS[name].docs_dir
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _fenced(text: str) -> str:
    """The report / artifact template of a stage document: its ```markdown block, indentation removed."""
    m = re.search(r"^( *)```markdown\n(.*?)^\1```", text, re.S | re.M)
    assert m
    return "\n".join(line[len(m.group(1)):] for line in m.group(2).split("\n"))


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_variant_is_the_original_with_other_documents(name):
    original, edited = VARIANTS[name]
    spec, base = workflows.WORKFLOWS[name], workflows.WORKFLOWS[original]
    assert spec == dataclasses.replace(base, docs_dir=spec.docs_dir)
    assert spec.docs_dir != base.docs_dir
    ours, theirs = _docs(name), _docs(original)
    assert sorted(ours) == sorted(theirs)
    assert {p for p in ours if ours[p] != theirs[p]} == edited
    assert spec.fingerprint("openhands-sdk") != base.fingerprint("openhands-sdk")


@pytest.mark.parametrize("name", sorted(VARIANTS))
def test_harness_takes_the_variant(name):
    original, _ = VARIANTS[name]
    h, base = OpenHandsSdkWorkflow(workflow=name, instruction_position="prefix"), OpenHandsSdkWorkflow(workflow=original, instruction_position="prefix")
    assert h._expected_doc_count() == base._expected_doc_count()
    assert h.compose_instruction("TASK") == base.compose_instruction("TASK")
    assert h.system_prompt_file == base.system_prompt_file
    assert h.workflow_fingerprint != base.workflow_fingerprint


def test_speckit_assessment_keeps_the_structure_the_rubric_reads():
    ours = _docs("speckit_bug_repro")["stages/01-assess.md"].decode()
    theirs = _docs("speckit_bug")["stages/01-assess.md"].decode()
    structure = lambda t: [line for line in _fenced(t).split("\n") if re.match(r"#{1,2} |- \*\*[^*]+\*\*:|\*\*[^*]+\*\*", line)]  # noqa: E731
    assert structure(ours) == structure(theirs)
    # the Reproduction section is still a numbered list, and the run comes before the remediation
    assert re.search(r"^## Reproduction\n\n1\. <", _fenced(ours), re.M)
    assert ours.index("**Reproduce the symptom**") < ours.index("**Propose a remediation**")
    assert "python -c" in ours and "python -c" not in theirs


def test_aidlc_stage1_artifact_grades_as_the_original_does():
    ours = _fenced(_docs("aidlc_v5_repro")["rule-details/01-reverse-engineering.md"].decode())
    theirs = _fenced(_docs("aidlc_v5")["rule-details/01-reverse-engineering.md"].decode())
    a, b = skeleton.parse(1, ours), skeleton.parse(1, theirs)
    assert a["unknown_sections"] == ["Observed Behavior"] and b["unknown_sections"] == []
    assert a["sections"] == b["sections"] and a["frontmatter"] == b["frontmatter"]
    ga, gb = skeleton.grade(1, a), skeleton.grade(1, b)
    assert (ga["points"], ga["missing"], ga["near_misses"]) == (gb["points"], gb["missing"], gb["near_misses"])


def test_aidlc_stage1_steps_are_numbered_in_order_and_the_run_precedes_the_baseline():
    text = _docs("aidlc_v5_repro")["rule-details/01-reverse-engineering.md"].decode()
    assert re.findall(r"^### Step (\d+):", text, re.M) == ["1", "2", "3", "4", "5"]
    assert text.index("### Step 2: Observe the Reported Behavior") < text.index("Record Baseline")
    plan = _docs("aidlc_v5_repro")["rule-details/03-code-generation-planning.md"].decode()
    assert "Observed Behavior recorded in Stage 1" in plan
