"""sdlc_if: every workflow's constraints.yaml matches its rubric and the template catalogue, and the
check finds what it is for; the opt-in ``all`` reading of repeated labels (``markdown.field_values``)."""

from __future__ import annotations

import copy

import pytest

from recipe.grpo.qwen3_5.sdlc_if import constraints
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M


@pytest.mark.parametrize("workflow", constraints.DEFAULT)
def test_constraints_match_rubric_and_catalogue(workflow):
    assert constraints.check(workflow) == []


def test_check_reports_drift(monkeypatch):
    doc = constraints.load("aidlc_v4_ifeval")
    bad = copy.deepcopy(doc)
    c = next(c for c in bad["constraints"] if c["template"] == "T-FM5")
    c["eval"]["layer"] = "L1"  # T-FM5's default is L2F: a different layer needs a reason
    c2 = next(c for c in bad["constraints"] if c["status"] == "implemented" and c is not bad["constraints"][0])
    c2["requirement"] = "should" if c2["requirement"] == "must" else "must"
    bad["constraints"].pop(0)
    monkeypatch.setattr(constraints, "load", lambda wf: bad)
    got = "\n".join(constraints.check("aidlc_v4_ifeval"))
    assert "without layer_reason" in got and "requirement" in got and "rubric item without a constraint" in got


def test_template_catalogue_skills():
    cat = constraints.templates()
    assert all(t["skill"] in {f"S{i}" for i in range(1, 11)} for t in cat.values())


def test_field_values_reads_every_occurrence():
    plan = "### Step 1\n- Target: a.py (modify in place)\n- Change: x\n\n### Step 2\n- Target: b.py, c.py (create)\n"
    assert M.field_value(plan, "Target") == "a.py (modify in place)"
    assert M.field_values(plan, "Target") == ["a.py (modify in place)", "b.py, c.py (create)"]
    tests = "- Path: tests/t1.py — Contract: foo\n- Path: tests/t2.py — Contract: bar\n"
    assert M.field_values(tests, "Path", multiline=True) == ["tests/t1.py", "tests/t2.py"]
    assert M.field_values(None, "Path") == [] and M.field_value("x", "Path") is None
