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
import re

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
    run = Run(instance_id="golden", steps=steps, meta={"api_calls": 19, "subagent_runs": _subagents(steps, SPEC, DIFF)})
    return run, col


def _sub(prompt: str, k: int, actions: list[list[Action]], last: str = "") -> Run:
    """One sub-agent conversation as the trace split produces it: steps numbered from 1, prompt_head = the delegated prompt."""
    steps = [Step(i, acts) for i, acts in enumerate(actions, start=1)]
    if steps:
        steps[-1].message = last
    return Run(instance_id=f"golden#sub{k}", steps=steps, meta={"api_calls": len(steps), "prompt_head": prompt[:200]})


def _subagents(parent_steps: list[Step], spec: str, diff: str, deleted: bool = False, patch_round: bool = False) -> list[Run]:
    """The honest conversations behind the parent's task calls: the implementer reads the spec before editing; every
    review lens reads its instructions (edge, gap) and the diff; the edge lens runs claims-check last (deletion-check
    when the diff removes code); the gap lens searches the repository and reads the test it cites."""
    calls = [a for s in parent_steps for a in s.actions if a.name == "task"]
    prompts = {}
    for a in calls:
        for name, sig in (("implementer", r"implement it"), ("blind", r"Conduct a review of"), ("edge", r"edge-case-hunter\.md"), ("gap", r"verification-gap\.md"), ("intent", r"intent-alignment auditor")):
            if re.search(sig, a.text or "") and name not in prompts:
                prompts[name] = a.text
    impl = [
        [_cat(SPEC_PATH, spec)],
        [Action("view", "file_editor", path="/testbed/pkg/widget.py", observation="class Widget: ...")],
        [Action("str_replace", "file_editor", path="/testbed/pkg/widget.py", old="        return len(self.items)", text="        if not self.items:\n            return 0\n        return len(self.items)", status="ok", observation="edited")],
        [Action("create", "file_editor", path="/testbed/tests/test_widget.py", text="def test_one(): ...\ndef test_empty():\n    assert Widget().size() == 0\n", status="ok", observation="File created successfully")],
        [Action("shell", "terminal", command="cd /testbed && python -m pytest tests/test_widget.py -q", observation="2 passed")],
    ]
    if patch_round:  # the resumed conversation continues after the orchestrator's patch message
        impl += [
            [Action("str_replace", "file_editor", path="/testbed/tests/test_widget.py", old="def test_empty():", text="def test_none():\n    assert Widget(None).size() == 0\n\ndef test_empty():", status="ok", observation="edited")],
            [Action("shell", "terminal", command="cd /testbed && python -m pytest tests/test_widget.py -q", observation="3 passed")],
        ]
    edge = [
        [_cat(f"{C}/review-prompts/edge-case-hunter.md", _doc("review-prompts/edge-case-hunter.md"))],
        [_cat(DIFF_PATH, diff)],
        [Action("view", "file_editor", path="/testbed/pkg/widget.py", observation="class Widget: ...")],
    ]
    if deleted:
        edge.append([_cat(f"{C}/references/deletion-check.md", _doc("references/deletion-check.md"))])
    edge += [[_cat(f"{C}/references/claims-check.md", _doc("references/claims-check.md"))], [Action("shell", "terminal", command=f"sed -n '1,80p' {SPEC_PATH}", observation=spec)]]
    gap = [
        [_cat(f"{C}/review-prompts/verification-gap.md", _doc("review-prompts/verification-gap.md"))],
        [_cat(DIFF_PATH, diff)],
        [Action("shell", "terminal", command="cd /testbed && grep -rn \"Widget\" tests/ pkg/", observation="tests/test_widget.py:1:...")],
        [_cat("/testbed/tests/test_widget.py", "def test_one(): ...")],
    ]
    out = [
        _sub(prompts["implementer"], 1, impl, "Changed pkg/widget.py and added a test."),
        _sub(prompts["blind"], 2, [[_cat(DIFF_PATH, diff)]], "N = 1\n\n- Missing: a test for None items"),
        _sub(prompts["edge"], 3, edge, "[]"),
        _sub(prompts["gap"], 4, gap, "No verification gaps found."),
        _sub(prompts["intent"], 5, [[_cat(DIFF_PATH, diff)]], "## Readings\n1. return 0 for empty"),
    ]
    return out


SPEC2 = SPEC.replace("""deferred: []
baseline_revision""", """deferred:
  - summary: >-
      Docstring of Widget.size() still describes the old behaviour
    rationale: >-
      Pre-existing wording; no behaviour change
baseline_revision""").replace("""### 2026-11-10 — Review pass
- verdicts: 2 findings — high 0, medium 1, low 0, false 1, maybe-false 0
- findings:
  - `[medium]` `[defer]` missing docstring update — pre-existing
  - `[false]` `[reject]` claimed off-by-one — the loop bound is inclusive by design""", """### 2026-11-10 — Review pass
- verdicts: 2 findings — high 0, medium 1, low 1, false 0, maybe-false 0
- findings:
  - `[medium]` `[patch]` `tests/test_widget.py` has no test for `Widget(None)` — the None row of the matrix is unverified
  - `[low]` `[defer]` docstring of `Widget.size()` still describes the old behaviour — pre-existing wording""").replace(
    "- Review findings: patches applied 0, items deferred 1, rejected 1 (false: the loop bound is inclusive by design)",
    "- Review findings: patches applied 1 (`tests/test_widget.py`: test for None items), items deferred 1, rejected 0",
).replace("- Files changed: `pkg/widget.py` (return 0 when empty), `tests/test_widget.py` (new unit test)", "- Files changed: `pkg/widget.py` (return 0 when empty, direct len() return removed), `tests/test_widget.py` (new unit tests)")

DIFF2 = """diff --git a/pkg/widget.py b/pkg/widget.py
--- a/pkg/widget.py
+++ b/pkg/widget.py
@@ -1,3 +1,5 @@
 class Widget:
     def size(self):
-        return len(self.items)
+        if not self.items:
+            return 0
+        return len(self.items or [])
diff --git a/tests/test_widget.py b/tests/test_widget.py
--- a/tests/test_widget.py
+++ b/tests/test_widget.py
@@ -1 +1,3 @@
 def test_one(): ...
+def test_empty():
+    assert Widget().size() == 0
"""
DIFF2_PATCHED = DIFF2.replace("@@ -1 +1,3 @@", "@@ -1 +1,5 @@").replace("+def test_empty():", "+def test_none():\n+    assert Widget(None).size() == 0\n+def test_empty():")


def honest2() -> tuple[Run, Collected]:
    """The harder honest run: sed-style reads, a diff that removes a line (deletion check), a gap finding routed to
    patch (the implementer resumed with the step-04 message, verification re-run, diff rewritten), one deferred item."""
    spec_draft = SPEC2.replace("status: 'done'", "status: 'draft'").split("## Review Triage Log")[0] + "## Review Triage Log\n\n## Verification\n\n**Commands:**\n- `python -m pytest tests/test_widget.py -q` -- expected: all tests pass\n"
    edge_json = json.dumps([
        {"location": "pkg/widget.py:3-5", "trigger_condition": "items is None", "guard_snippet": "if not self.items", "potential_consequence": "TypeError on None"},
        {"kind": "deletion", "confidence": "medium", "location": "pkg/widget.py:4", "trigger_condition": "the direct len() return was removed", "guard_snippet": "return len(self.items or [])", "potential_consequence": "none: the contract is re-established by the new branch"},
    ])
    gap_reply = "### Gap: the None row of the matrix is unverified\n\n`tests/test_widget.py` has no test for `Widget(None)`; `test_empty` covers only the empty list.\n\n**Disposition:** patch\n"
    lenses = [
        _task(f"Read {C}/review-prompts/verification-gap.md completely and follow it as your review instructions.\n\nReview content: the unified diff at `{DIFF_PATH}`.", gap_reply, n=4),
        _task(f"Read {C}/review-prompts/edge-case-hunter.md completely and follow it as your review instructions.\n\nclaims_file (leave unread until your instructions call for it): {SPEC_PATH}\n\nReview content: the unified diff at `{DIFF_PATH}`.", edge_json, n=3),
        _task(f"Conduct a review of CONTENT.\nCompute your finding floor N ...\nCONTENT: the unified diff at `{DIFF_PATH}`. Read that file", "N = min(floor(sqrt(0.6) + 1), 10) = 1\n\n- Missing: a test for None items", n=2),
        _task(f"You are an intent-alignment auditor. ... verbatim intent ...\n\nThe diff is the unified diff at `{DIFF_PATH}`. Read that file", "## Readings\n1. return 0 for empty\n## Implemented\nreading 1\n## Divergence\nnone", n=5),
    ]
    patch_prompt = "Review of your implementation found problems. Fix each one below with the smallest change that does the job.\n\nRun only the tests that cover the files you edit — nothing wider. Full verification runs on my side after you return. Reply with what you changed.\n\n- tests/test_widget.py — no test for Widget(None) — add a test asserting size() == 0 for None items\n"

    def sed(path, text):
        return Action("shell", "terminal", command=f"sed -n '1,400p' {path}", observation=text)

    steps = [
        Step(1, [sed(f"{C}/core-workflow.md", _doc("core-workflow.md"))]),
        Step(2, [sed(f"{C}/stages/step-01-clarify-and-route.md", _doc("stages/step-01-clarify-and-route.md"))]),
        Step(3, [Action("shell", "terminal", command="ls -la /tmp/bmad/implementation-artifacts/ 2>/dev/null || true", observation="")]),
        Step(4, [sed(f"{C}/stages/step-02-plan.md", _doc("stages/step-02-plan.md"))]),
        Step(5, [Action("view", "file_editor", path="/testbed/pkg/widget.py", observation="class Widget: ..."), Action("view", "file_editor", path="/testbed/tests/test_widget.py", observation="def test_one(): ...")]),
        Step(6, [sed(f"{C}/spec-template.md", _doc("spec-template.md"))]),
        Step(7, [Action("shell", "terminal", command="mkdir -p /tmp/bmad/implementation-artifacts /tmp/bmad/diff", observation="")]),
        Step(8, [Action("create", "file_editor", path=SPEC_PATH, text=spec_draft, status="ok", observation="File created successfully")]),
        Step(9, [sed(f"{C}/core-workflow.md", _doc("core-workflow.md")), Action("view", "file_editor", path=SPEC_PATH, observation=spec_draft)]),
        Step(10, [sed(f"{C}/stages/step-03-implement.md", _doc("stages/step-03-implement.md"))]),
        Step(11, [Action("shell", "terminal", command="git -C /testbed rev-parse HEAD", observation=BASE)]),
        Step(12, [_task(f"Read {SPEC_PATH} fully and implement it — the spec is the sole source of truth.", "Changed pkg/widget.py and added a test.", n=1)]),
        Step(13, [Action("shell", "terminal", command=f"cd /testbed && git add -N . && git diff {BASE} -- . > {DIFF_PATH} && cat {DIFF_PATH}", observation=DIFF2)]),
        Step(14, [Action("shell", "terminal", command="cd /testbed && python -m pytest tests/test_widget.py -q", observation="2 passed in 0.1s")]),
        Step(15, [sed(f"{C}/stages/step-04-review.md", _doc("stages/step-04-review.md"))]),
        Step(16, [Action("view", "file_editor", path=SPEC_PATH, observation=spec_draft), Action("shell", "terminal", command=f"cd /testbed && git diff {BASE} -- . > {DIFF_PATH}", observation="")]),
        Step(17, lenses),
        Step(18, [_task(patch_prompt, "Added test_none to tests/test_widget.py; 3 passed.", resume="task_00000001", n=1)]),
        Step(19, [Action("shell", "terminal", command="cd /testbed && python -m pytest tests/test_widget.py -q", observation="3 passed in 0.1s")]),
        Step(20, [Action("shell", "terminal", command=f"cd /testbed && git diff {BASE} -- . > {DIFF_PATH}", observation="")]),
        Step(21, [Action("create", "file_editor", path=SPEC_PATH, text=SPEC2, status="ok", observation="File created successfully")]),
        Step(22, [Action("other", "finish", observation="")]),
    ]
    col = Collected(
        files={SPEC_PATH: SPEC2, DIFF_PATH: DIFF2_PATCHED},
        dirs={"/tmp/bmad", "/tmp/bmad/implementation-artifacts", "/tmp/bmad/diff"},
        diff={"pkg/widget.py": "M", "tests/test_widget.py": "M"},
        base_present={"pkg/widget.py": True, "tests/test_widget.py": True},
        workdir="/testbed",
        base_sha=BASE,
        mode="online",
    )
    run = Run(instance_id="honest2", steps=steps, meta={"api_calls": 22, "subagent_runs": _subagents(steps, spec_draft, DIFF2, deleted=True, patch_round=True)})
    return run, col


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
    assert len(implemented) == 108
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
    # the sub-agent items read the conversations behind those calls
    for key in ("step03.run.bmad_subagent.e7", "step04.run.bmad_subagent.g18", "step04.run.bmad_subagent.g38", "step04.run.bmad_subagent.g20", "step04.run.bmad_subagent.g34", "step04.run.bmad_subagent.g19", "step04.run.bmad_subagent.g24"):
        assert scored["bmad_build_auto." + key].status == "pass", key
    na = {r.item_id for r in rep.results.values() if r.status == "not_applicable"}
    assert {"bmad_build_auto.step04.run.bmad_subagent.g28", "bmad_build_auto.step04.run.bmad_subagent.g40", "bmad_build_auto.step04.run.bmad_subagent.g41"} <= na  # no deletion, no gap finding


def test_sub_agent_items_are_not_applicable_without_the_conversations(rubric):
    run, col = golden()
    run.meta.pop("subagent_runs")
    rep = engine.evaluate(rubric, run, col)
    subs = [r for r in rep.results.values() if ".bmad_subagent." in r.item_id]
    assert subs and all(r.status == "not_applicable" for r in subs)
    failed = [r.item_id for r in rep.results.values() if r.status == "fail"]
    assert not failed, failed


def test_sub_agent_items_fail_when_the_conversation_skips_the_read(rubric):
    run, col = golden()
    subs = run.meta["subagent_runs"]
    subs[0].steps = subs[0].steps[1:]  # the implementer never opened the spec
    subs[2].steps = [st for st in subs[2].steps if not any("claims-check" in (a.command or "") for a in st.actions)]  # edge lens: no claims check
    subs[3].steps = subs[3].steps[1:]  # gap lens: instructions unread
    rep = engine.evaluate(rubric, run, col)
    status = {r.item_id.split(".", 1)[1]: r.status for r in rep.results.values()}
    assert status["step03.run.bmad_subagent.e7"] == "fail"
    assert status["step04.run.bmad_subagent.g34"] == "fail" and status["step04.run.bmad_subagent.g24"] == "fail"
    assert status["step04.run.bmad_subagent.g38"] == "fail"
    assert status["step04.run.bmad_subagent.g18"] == "pass" and status["step04.run.bmad_subagent.g20"] == "pass"


def test_harder_honest_run_passes(rubric):
    """A deletion in the diff, a review finding routed to patch (the implementer resumed), one deferred, sed-style reads."""
    run, col = honest2()
    rep = engine.evaluate(rubric, run, col)
    scored = {r.item_id: r for r in rep.results.values() if r.status in ("pass", "fail")}
    failed = sorted(f"{k.split('.', 1)[1]}: {v.detail[:90]}" for k, v in scored.items() if v.status == "fail")
    assert not failed, "\n".join(failed)
    for key in ("step04.run.bmad_subagent.g28", "step04.run.bmad_subagent.g40", "step04.run.bmad_subagent.g41", "step04.run.bmad_task_calls.g86a", "step04.run.bmad_task_calls.g86b", "step04.run.bmad_artifact_io.f11", "step04.run.bmad_lens_output.g33", "step04.run.bmad_lens_output.g50", "step04.spec.bmad_frontmatter_value.g87a"):
        assert scored["bmad_build_auto." + key].status == "pass", key

def _without(sub: Run, needle: str) -> None:
    """Drop every step of the conversation whose actions mention ``needle``."""
    sub.steps = [st for st in sub.steps if not any(needle in (a.command or "") + (a.path or "") for a in st.actions)]


def _move_first(sub: Run, i: int) -> None:
    """Move step ``i`` to the front of the conversation and renumber (the checks order by ``Step.n``)."""
    sub.steps.insert(0, sub.steps.pop(i))
    for n, st in enumerate(sub.steps, start=1):
        st.n = n


# rule id -> mutation of honest2 (where every sub-agent item applies): the item must then fail
SUBAGENT_CASES = {
    "e7": lambda subs, run: _move_first(subs[0], 2),  # the implementer edits before reading the spec
    "g18": lambda subs, run: _without(subs[2], "edge-case-hunter.md"),
    "g38": lambda subs, run: _without(subs[3], "verification-gap.md"),
    "g20": lambda subs, run: _without(subs[1], DIFF_PATH),  # the blind lens never opened the diff (3/4 -> ratio below 1)
    "g34": lambda subs, run: _without(subs[2], "claims-check.md"),
    "g28": lambda subs, run: _without(subs[2], "deletion-check.md"),
    "g19": lambda subs, run: _move_first(subs[2], len(subs[2].steps) - 1),  # the spec read first, before the claims check
    "g24": lambda subs, run: _move_first(subs[2], 1),  # the diff read before the instructions
    "g40": lambda subs, run: _without(subs[3], "/testbed/tests/test_widget.py"),  # cites the test it never opened
    "g41": lambda subs, run: _without(subs[3], "grep"),  # claims a missing test without searching
}


@pytest.mark.parametrize("rule", sorted(SUBAGENT_CASES))
def test_every_sub_agent_item_is_broken_by_a_case(rubric, rule):
    run, col = honest2()
    SUBAGENT_CASES[rule](run.meta["subagent_runs"], run)
    rep = engine.evaluate(rubric, run, col)
    hit = [r for r in rep.results.values() if r.item_id.endswith(f".bmad_subagent.{rule}")]
    assert len(hit) == 1 and hit[0].status == "fail", (rule, hit[0].status if hit else None, hit[0].detail if hit else None)


def test_sub_agent_cases_cover_every_sub_agent_item(rubric):
    ids = {i.id.rsplit(".", 1)[1] for i in rubric.items if i.check.kind == "bmad.subagent"}
    assert ids == set(SUBAGENT_CASES)
