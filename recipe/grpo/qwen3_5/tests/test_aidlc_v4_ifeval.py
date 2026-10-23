"""aidlc_v4_ifeval: aidlc_v4_gen's rubric on a copy of AI-DLC's documents, with evaluation layers
(``workflow_rubric/layers.py``) taken from the workflow's constraints (``sdlc_if/constraints.py``).

On aidlc_v4_gen's golden run (an honest run that follows the documents literally), reading the copy's
documents, every layer passes; a re-read of a written artifact fails only the conflict layer; a run that
stops after Stage 2 keeps its reached-stage rates apart from the unconditional ones; and a recorded plan
deviation takes the plan-adherence items out of their layer. The judging fixes of the build (repeated
labels read in full, the no-test-target pattern) and the strict no-re-read rule are checked on edits of
that run.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import re

import pytest
import yaml

from recipe.grpo.qwen3_5.sdlc_if import constraints
from recipe.grpo.qwen3_5.workflow_rubric import engine, layers, schema
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric.checks import validate_params
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action
from recipe.grpo.qwen3_5.workflows import aidlc_v4, aidlc_v4_ifeval
from recipe.grpo.qwen3_5.workflows.aidlc_v4_gen.selftest_golden import golden as gen_golden
from recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward import build

PREFIX = "aidlc_ifeval"
G = "aidlc_v4_gen."


def golden(rubric):
    """aidlc_v4_gen's golden run with every document read answered by the copy's text."""
    run, col = gen_golden(rubric)
    root, container = aidlc_v4_ifeval.SPEC.docs_dir, aidlc_v4_ifeval.SPEC.container_dir
    for s in run.steps:
        for a in s.actions:
            m = re.fullmatch(rf"cat ({re.escape(container)}/\S+\.md)", a.command or "")
            if m:
                a.observation = (root / m.group(1)[len(container) + 1 :]).read_text()
    return run, col


@pytest.fixture(scope="module")
def setup():
    importlib.import_module("recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.checks")
    rubric = schema.load(build.RUBRIC)
    validate_params(rubric)
    lay = layers.load(build.LAYERS, rubric, build.RUBRIC)
    return rubric, lay


def _signals(rubric, lay, run, col):
    report = engine.evaluate(rubric, run, col)
    return report, layers.signals(rubric, run, col, report, lay, PREFIX)


def test_committed_files_match_a_fresh_build():
    assert build.main(["--check"]) == 0


def test_constraints_match_the_rubric_and_the_catalogue():
    assert constraints.check("aidlc_v4_ifeval") == []


def test_the_workflow_runs_on_its_copy():
    spec = aidlc_v4_ifeval.SPEC
    assert spec.docs_dir != aidlc_v4.SPEC.docs_dir and spec.docs_dir.is_dir()
    assert spec.container_dir == aidlc_v4.SPEC.container_dir and spec.output_dirs == aidlc_v4.SPEC.output_dirs
    sp = spec.system_prompt["openhands-sdk"].read_text()
    assert "<ENVIRONMENT_SETUP>" not in sp and "confirm with the user" not in sp and "thoroughly understand the codebase" not in sp
    assert "Re-read the requirement" not in (spec.docs_dir / "rule-details/05-build-and-test.md").read_text()


def test_every_source_quote_is_at_its_lines_in_the_copy():
    rubric = yaml.safe_load(build.RUBRIC.read_text())
    texts = {s["id"]: (build.WF / s["path"]).read_text().splitlines() for s in rubric["sources"]}
    bad = [
        (it["id"], src["lines"])
        for it in rubric["items"]
        for src in it["sources"]
        if build.anchor(texts[src["doc"]], src["quote"], tuple(src["lines"])) != tuple(src["lines"])
    ]
    assert bad == []


def test_every_layer_and_the_new_item(setup):
    rubric, lay = setup
    got = {spec["layer"] for spec in lay.values()}
    assert got == {"L1", "L1C", "L2F", "L2M"}
    assert lay[build.NO_REREAD]["layer"] == "L1C"
    assert next(i for i in rubric.items if i.id == build.NO_REREAD).log_only


def test_golden_passes_every_layer(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    report, sig = _signals(rubric, lay, run, col)
    assert report.results[build.NO_REREAD].status == "pass"
    for name in ("L1", "L1C", "L2F", "L2M"):
        assert sig[f"{PREFIX}/layer/{name}"] == 1.0
        assert sig[f"{PREFIX}/layer_reached/{name}"] == 1.0
    assert report.scores.compliance == pytest.approx(1.0)


def test_rereading_a_written_artifact_fails_only_the_conflict_layer(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    a1 = engine.evaluate(rubric, run, col).facts.artifact_paths["a1"]
    later = run.steps[-3]  # a Stage 5 call, well after a1 was written
    later.actions.insert(0, Action(kind="view", path=a1, status="ok", observation=col.files.get(a1, "")))
    report, sig = _signals(rubric, lay, run, col)
    assert report.results[build.NO_REREAD].status == "fail", report.results[build.NO_REREAD].detail
    assert sig[f"{PREFIX}/layer/L1C"] < 1.0
    assert sig[f"{PREFIX}/layer/L2F"] == sig[f"{PREFIX}/layer/L2M"] == 1.0


def _write_step(run, path):
    return next(s for s in run.steps if any(a.path == path and a.kind == "create" for a in s.actions))


def test_a_read_in_the_writing_call_is_a_re_read(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    a2 = engine.evaluate(rubric, run, col).facts.artifact_paths["a2"]
    s = _write_step(run, a2)
    s.actions.append(Action(kind="shell", name="terminal", command=f"cat {a2}", observation=col.files[a2]))
    report, _ = _signals(rubric, lay, run, col)
    assert report.results[build.NO_REREAD].status == "fail"


def test_the_first_read_of_an_artifact_written_unseen_recovers_it(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    a2 = engine.evaluate(rubric, run, col).facts.artifact_paths["a2"]
    s = _write_step(run, a2)
    i = next(k for k, a in enumerate(s.actions) if a.path == a2 and a.kind == "create")
    text = s.actions[i].text
    # the agent drafts the file elsewhere and copies it: the copy's call never shows the content
    s.actions[i : i + 1] = [
        Action(kind="create", name="file_editor", path="/tmp/draft.md", text=text, status="ok", observation="File created successfully at: /tmp/draft.md"),
        Action(kind="shell", name="terminal", command=f"cp /tmp/draft.md {a2}"),
    ]
    later = run.steps[run.steps.index(s) + 1]
    later.actions.insert(0, Action(kind="shell", name="terminal", command=f"cat {a2}", observation=text))
    report, _ = _signals(rubric, lay, run, col)
    assert report.results[build.NO_REREAD].status == "pass", report.results[build.NO_REREAD].detail
    after = run.steps[run.steps.index(s) + 2]
    after.actions.insert(0, Action(kind="shell", name="terminal", command=f"head {a2}", observation=text[:200]))
    report, _ = _signals(rubric, lay, run, col)
    assert report.results[build.NO_REREAD].status == "fail"


def test_repeated_labels_are_read_in_full(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    a3 = engine.evaluate(rubric, run, col).facts.artifact_paths["a3"]
    text = col.files[a3]
    assert len(M.field_values(M.section(text, "Plan"), "Target")) >= 2, "the golden plan has one step; the test needs two"
    # the last step's Target becomes a test file: only a reader of every Target sees it
    last = [m for m in re.finditer(r"(?m)^- Target: .*$", text)][-1]
    col.files[a3] = text[: last.start()] + "- Target: tests/test_textkit.py (modify in place)" + text[last.end() :]
    report = engine.evaluate(rubric, run, col)
    for iid in ("code_generation_planning.a3.item_format.no_test_target", "code_generation_planning.a3.field_type.target"):
        assert report.results[G + iid].score < 1.0, (iid, report.results[G + iid].detail)


def test_no_test_target_pattern():
    p = re.compile(build.NO_TEST_TARGET)
    for line in ("- Target: tests/test_a.py (modify in place)", "- **Target**: pkg/test_x.py (create)", "- Target: `pkg/x_test.py`", "- Target: conftest.py"):
        assert not p.match(line), line
    for line in ("- Target: src/a.py (modify in place)", "- Target: django/test/testcases.py", "- Target: src/contest.py"):
        assert p.match(line), line


def test_a_run_stopped_after_stage_2_separates_reached_from_unconditional(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    paths = engine.evaluate(rubric, run, col).facts.artifact_paths
    a2 = paths["a2"]
    cut = next(s.n for s in run.steps if any(a.path == a2 and a.kind in ("create", "replace", "insert") for a in s.actions) or any(a2 in (a.command or "") for a in s.actions))
    short = dataclasses.replace(run, steps=[s for s in run.steps if s.n <= cut])
    late = {p for k, p in paths.items() if k in ("a3", "a4", "a5")}
    col2 = copy.copy(col)
    col2.files = {p: t for p, t in col.files.items() if p not in late}
    _, sig = _signals(rubric, lay, short, col2)
    assert sig[f"{PREFIX}/layer/L2F"] < sig[f"{PREFIX}/layer_reached/L2F"] == 1.0


def test_a_recorded_deviation_takes_plan_adherence_out_of_its_layer(setup):
    rubric, lay = setup
    run, col = golden(rubric)
    report = engine.evaluate(rubric, run, col)
    a4 = report.facts.artifact_paths["a4"]
    gated = [i for i, spec in lay.items() if spec.get("when")]
    assert gated
    ctx = engine.EvalContext(rubric=rubric, run=run, collected=col, facts=report.facts)
    assert all(layers._when(ctx, lay[i]["when"]) for i in gated)
    text = col.files[a4]
    head, _, tail = text.partition("## Deviations from Plan")
    body, sep, rest = tail.partition("\n## ")
    col.files[a4] = head + "## Deviations from Plan\n- local correction: the helper lives in textkit/util.py, not the planned file\n" + sep + rest
    report = engine.evaluate(rubric, run, col)
    ctx = engine.EvalContext(rubric=rubric, run=run, collected=col, facts=report.facts)
    assert not any(layers._when(ctx, lay[i]["when"]) for i in gated)


def test_evaluation_policy_loads_the_layers():
    pytest.importorskip("rllm")
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.eval import Evaluation

    ev = Evaluation()
    assert ev.layers and build.NO_REREAD in ev.layers
