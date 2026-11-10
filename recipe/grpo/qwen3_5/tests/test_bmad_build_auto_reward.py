"""bmad_build_auto's compliance rubric: generated from the port's rule inventory and the stage-3 decisions.

The committed rubric, constraints and layers equal a fresh build; the rubric loads and every item's kind
takes the parameters it declares; the constraints file agrees with the rubric and the catalogue; an empty run
scores without an exception and passes only the prohibition items; and a synthetic honest run that follows the
documents -- the orchestrator's conversation only, with its ``task`` calls and the lenses' replies -- passes the
items that read the trace and the spec.
"""

from __future__ import annotations

import importlib
import json

import pytest
import yaml

from recipe.grpo.qwen3_5.sdlc_if import constraints
from recipe.grpo.qwen3_5.workflow_rubric import engine, layers, schema
from recipe.grpo.qwen3_5.workflow_rubric.checks import validate_params
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step
from recipe.grpo.qwen3_5.workflows import bmad_build_auto
from recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward import build

DOCS = bmad_build_auto.SPEC.docs_dir
C = "/bmad-build-auto"
SPEC_PATH = "/tmp/bmad/implementation-artifacts/spec-gh-7-fix-widget.md"
DIFF_PATH = "/tmp/bmad/diff/gh-7-fix-widget.diff"
BASE = "a" * 40

SPEC = f"""---
title: 'Fix widget size'
type: 'bugfix'
created: '2026-11-10'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: '{BASE}'
---

<intent-contract>

## Intent

**Problem:** `Widget.size()` returns the wrong value for empty widgets.

**Approach:** Return zero for an empty widget and keep the existing behaviour otherwise.

## Boundaries & Constraints

**Always:** keep the public signature of `Widget.size()`.

**Never:** change the test files' expectations.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| empty widget | no items | 0 | No error expected |
| one item | one item | 1 | No error expected |

</intent-contract>

## Code Map

- `pkg/widget.py` -- `Widget.size()`, the method under change
- `tests/test_widget.py` -- the covering tests

## Tasks & Acceptance

**Execution:**
- `pkg/widget.py` -- return 0 when empty -- the issue's case
- `tests/test_widget.py` -- add a unit test for the matrix rows -- edge cases

**Acceptance Criteria:**
- Given an empty widget, when size() is called, then it returns 0

## Spec Change Log

## Review Triage Log

### 2026-11-10 — Review pass
- verdicts: 2 findings — high 0, medium 1, low 0, false 1, maybe-false 0
- findings:
  - `[medium]` `[defer]` missing docstring update — pre-existing
  - `[false]` `[reject]` claimed off-by-one — the loop bound is inclusive by design

## Verification

**Commands:**
- `python -m pytest tests/test_widget.py -q` -- expected: all tests pass

## Auto Run Result

- Summary: `Widget.size()` returns 0 for an empty widget.
- Files changed: `pkg/widget.py` (return 0 when empty), `tests/test_widget.py` (new unit test)
- Review findings: patches applied 0, items deferred 1, rejected 1 (false: the loop bound is inclusive by design)
- Follow-up review recommendation: false
- Verification performed: `python -m pytest tests/test_widget.py -q` passed
- Residual risks: none
"""

DIFF = """diff --git a/pkg/widget.py b/pkg/widget.py
--- a/pkg/widget.py
+++ b/pkg/widget.py
@@ -1,3 +1,5 @@
 class Widget:
     def size(self):
+        if not self.items:
+            return 0
         return len(self.items)
diff --git a/tests/test_widget.py b/tests/test_widget.py
--- a/tests/test_widget.py
+++ b/tests/test_widget.py
@@ -1 +1,3 @@
 def test_one(): ...
+def test_empty():
+    assert Widget().size() == 0
"""


def _doc(rel: str) -> str:
    return (DOCS / rel).read_text(encoding="utf-8")


def _cat(path: str, text: str) -> Action:
    return Action("shell", "terminal", command=f"cat {path}", observation=text)


def _task(prompt: str, reply: str, resume: str = "", n: int = 1) -> Action:
    return Action("other", "task", text=prompt, path="general-purpose", old=resume, observation=f"Task ID: task_{n:08x}\nSubagent: general-purpose\nStatus: completed\n\n{reply}")


def golden() -> tuple[Run, Collected]:
    """An honest orchestrator run: reads in order, one spec write, the hand-off, the diff, four lenses, the log."""
    edge_json = json.dumps([{"location": "pkg/widget.py:3-4", "trigger_condition": "items is None", "guard_snippet": "if not self.items", "potential_consequence": "TypeError on None"}])
    lenses = [
        _task(f"Conduct a review of CONTENT.\nCompute your finding floor N ...\nCONTENT: the unified diff at `{DIFF_PATH}`. Read that file", "N = min(floor(sqrt(0.4) + 1), 10) = 1\n\n- Missing: a test for None items", n=2),
        _task(f"Read {C}/review-prompts/edge-case-hunter.md completely and follow it as your review instructions.\n\nclaims_file (leave unread until your instructions call for it): {SPEC_PATH}\n\nReview content: the unified diff at `{DIFF_PATH}`.", edge_json, n=3),
        _task(f"Read {C}/review-prompts/verification-gap.md completely and follow it as your review instructions.\n\nReview content: the unified diff at `{DIFF_PATH}`.", "No verification gaps found.", n=4),
        _task(f"You are an intent-alignment auditor. ... verbatim intent ...\n\nThe diff is the unified diff at `{DIFF_PATH}`. Read that file", "## Readings\n1. return 0 for empty\n## Implemented\nreading 1\n## Divergence\nnone", n=5),
    ]
    steps = [
        Step(1, [_cat(f"{C}/core-workflow.md", _doc("core-workflow.md"))]),
        Step(2, [_cat(f"{C}/stages/step-01-clarify-and-route.md", _doc("stages/step-01-clarify-and-route.md"))]),
        Step(3, [Action("shell", "terminal", command="ls -la /tmp/bmad/implementation-artifacts/ 2>/dev/null || true", observation="")]),
        Step(4, [_cat(f"{C}/stages/step-02-plan.md", _doc("stages/step-02-plan.md"))]),
        Step(5, [Action("view", "file_editor", path="/testbed/pkg/widget.py", observation="class Widget: ..."), Action("view", "file_editor", path="/testbed/tests/test_widget.py", observation="def test_one(): ...")]),
        Step(6, [_cat(f"{C}/spec-template.md", _doc("spec-template.md"))]),
        Step(7, [Action("shell", "terminal", command="mkdir -p /tmp/bmad/implementation-artifacts /tmp/bmad/diff", observation="")]),
        Step(8, [Action("create", "file_editor", path=SPEC_PATH, text=SPEC.replace("status: 'done'", "status: 'draft'").split("## Review Triage Log")[0] + "## Review Triage Log\n\n## Verification\n\n**Commands:**\n- `python -m pytest tests/test_widget.py -q` -- expected: all tests pass\n", status="ok", observation="File created successfully")]),
        Step(9, [_cat(f"{C}/core-workflow.md", _doc("core-workflow.md")), _cat(SPEC_PATH, SPEC)]),
        Step(10, [_cat(f"{C}/stages/step-03-implement.md", _doc("stages/step-03-implement.md"))]),
        Step(11, [Action("shell", "terminal", command=f"test -f {SPEC_PATH} && git -C /testbed rev-parse HEAD", observation=BASE)]),
        Step(12, [_task(f"Read {SPEC_PATH} fully and implement it — the spec is the sole source of truth.", "Changed pkg/widget.py and added a test.", n=1)]),
        Step(13, [Action("shell", "terminal", command=f"cd /testbed && git diff {BASE} > {DIFF_PATH} && cat {DIFF_PATH}", observation=DIFF)]),
        Step(14, [Action("shell", "terminal", command="cd /testbed && python -m pytest tests/test_widget.py -q", observation="2 passed in 0.1s")]),
        Step(15, [_cat(f"{C}/stages/step-04-review.md", _doc("stages/step-04-review.md"))]),
        Step(16, [_cat(SPEC_PATH, SPEC), Action("shell", "terminal", command=f"cd /testbed && git diff {BASE} > {DIFF_PATH}", observation="")]),
        Step(17, lenses),
        Step(18, [Action("create", "file_editor", path=SPEC_PATH, text=SPEC, status="ok", observation="File created successfully")]),
        Step(19, [Action("other", "finish", observation="")]),
    ]
    col = Collected(
        files={SPEC_PATH: SPEC, DIFF_PATH: DIFF},
        dirs={"/tmp/bmad", "/tmp/bmad/implementation-artifacts", "/tmp/bmad/diff"},
        diff={"pkg/widget.py": "M", "tests/test_widget.py": "M"},
        base_present={"pkg/widget.py": True, "tests/test_widget.py": True},
        workdir="/testbed",
        base_sha=BASE,
        mode="online",
    )
    return Run(instance_id="golden", steps=steps), col


@pytest.fixture(scope="module")
def rubric():
    importlib.import_module("recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward.checks")
    return schema.load(build.RUBRIC)


def test_committed_files_are_a_fresh_build():
    assert build.main(["--check"]) == 0


def test_rubric_loads_and_kinds_take_their_params(rubric):
    validate_params(rubric)
    assert len(rubric.items) == 217
    implemented = [i for i in rubric.items if i.check.kind != "unimplemented"]
    assert len(implemented) == 98
    assert all(i.scope == "specific" for i in implemented if i.check.kind.startswith("bmad."))
    judge = [i for i in rubric.items if i.log_only]
    assert judge and all(i.check.kind == "unimplemented" for i in judge)


def test_constraints_agree_with_the_rubric_and_catalogue():
    assert constraints.check("bmad_build_auto") == []
    doc = yaml.safe_load(build.CONSTRAINTS.read_text())
    assert doc["role"] == "eval" and len(doc["constraints"]) == 217


def test_layers_cover_every_implemented_item(rubric):
    lay = layers.load(build.LAYERS, rubric, build.RUBRIC)
    assert set(lay) == {i.id for i in rubric.items if i.check.kind != "unimplemented"}
    assert {v["layer"] for v in lay.values()} <= {"L1", "L1C", "L2M", "L2F"}


def test_spec_declares_the_scorer_and_the_subagent_tool():
    assert bmad_build_auto.SPEC.runner_env == {"OPENHANDS_SDK_EXTRA_TOOLS": "task"}
    assert "openhands-sdk" in bmad_build_auto.SPEC.scorers and bmad_build_auto.SPEC.reward_signal == "bmad/compliance"


def test_empty_run_passes_only_prohibitions(rubric):
    col = Collected(files={}, workdir="/testbed", base_sha=BASE, diff={}, base_present={}, mode="online")
    rep = engine.evaluate(rubric, Run(instance_id="empty", steps=[]), col)
    passed = sorted(r.item_id for r in rep.results.values() if r.status == "pass")
    assert passed == [
        "bmad_build_auto.global.run.bmad_last_message.d1",
        "bmad_build_auto.step04.run.bmad_no_doc_read.g9",
        "bmad_build_auto.step04.run.prohibited_action.g5",
    ]


def test_golden_run_passes_the_trace_and_spec_items(rubric):
    run, col = golden()
    rep = engine.evaluate(rubric, run, col)
    scored = {r.item_id: r for r in rep.results.values() if r.status in ("pass", "fail")}
    failed = sorted(f"{k.split('.', 1)[1]}: {v.detail[:70]}" for k, v in scored.items() if v.status == "fail")
    assert not failed, "\n".join(failed)
    # the sub-agent items read the orchestrator's task calls
    for key in ("step03.run.bmad_task_calls.e11", "step04.run.bmad_task_calls.i3", "step04.run.bmad_task_calls.g11", "step04.run.bmad_lens_output.g29", "step04.spec.bmad_triage_totals.g80"):
        assert scored["bmad_build_auto." + key].status == "pass", key
