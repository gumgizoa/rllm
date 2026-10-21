"""workflows/aidlc_v4_eval: the evaluation verifier stands on its own, stays fixed, and scores
aidlc_v4's signals plus the content checks.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_v4_eval.py

The pinned hashes are the point of the package: aidlc_v4 (the training workflow) may change, this one
must not follow it. A failing pin means a file of the evaluation verifier changed -- if that is
intended, it is a new verifier version, and numbers measured before it are not comparable.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from test_aidlc_reward import ART, ARTIFACTS, DOC, _call, _collected, _Sandbox, _Verifier, episode  # noqa: E402

from recipe.grpo.qwen3_5.workflows import aidlc_v4_eval, get_workflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.evaluator import AidlcEvalComplianceEvaluator, AidlcEvalEvaluation, score  # noqa: E402

PKG = aidlc_v4_eval.HERE

# SPEC.fingerprint: what the agent is given. Equal to aidlc_v4's when copied (4c3ee52c), and to the
# one recorded by the aidlc_v4 runs it rescores (swebv100_aidlcv4_262k-150_think_t1_prefix).
FINGERPRINT = "b9c317de1dd1b28db28d5d960763b85ef63d8d272e687fe1a6103852b0ca14b6"
# The copied scoring code: reward/rubric/**, compliance.py, episode.py.
SCORING_COPY = "c9766d596ba200a4785781bb37c8dc00612e9f872f90a8c8c63c27d2952b027b"


def _content_honest_turns() -> list[tuple[dict, str]]:
    """Every stage in order, and every claim the ARTIFACTS make borne out by the trajectory: the
    scope file viewed, baseline and build run before artifact 1, the repro script written before
    artifact 4, build / repro / tests run after the last edit and before artifact 5."""
    t, i = [], iter(range(1000))

    def add(name, obs, **args):
        t.append((_call(next(i), name, **args), obs))

    add("file_editor", "# core", command="view", path="/ai-dlc/core-workflow.md")
    add("terminal", "# RE", command=f"cat {DOC['01']}")
    add("file_editor", "def parse(s): ...", command="view", path="/testbed/pkg/mod.py")
    add("terminal", "tests/test_mod.py::test_parse PASSED\n3 passed in 0.10s", command="cd /testbed && python -m pytest tests/test_mod.py -q")
    add("terminal", "exit code: 0", command='cd /testbed && python -c "import pkg"')
    add("file_editor", "File created successfully", command="create", path=ART[1], file_text=ARTIFACTS[1])
    for k in (2, 3):
        add("terminal", "# doc", command=f"cat {DOC[f'0{k}']}")
        add("file_editor", "File created successfully", command="create", path=ART[k], file_text=ARTIFACTS[k])
    add("terminal", "# doc", command=f"cat {DOC['04']}")
    add("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="a", new_str="b")
    add("file_editor", "File created successfully", command="create", path="/tmp/repro.py", file_text="import pkg\n")
    add("file_editor", "File created successfully", command="create", path=ART[4], file_text=ARTIFACTS[4])
    add("terminal", "# doc", command=f"cat {DOC['05']}")
    add("terminal", "exit code: 0", command='cd /testbed && python -c "import pkg"')
    add("terminal", "ok\nexit code: 0", command="python /tmp/repro.py")
    add("terminal", "3 passed in 0.10s", command="cd /testbed && python -m pytest tests/test_mod.py -q")
    add("file_editor", "File created successfully", command="create", path=ART[5], file_text=ARTIFACTS[5])
    add("finish", "", message="done")
    return t


FILES = {ART[k]: ARTIFACTS[k] for k in ART}


# --- standing on its own ---------------------------------------------------------------------


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append("." * node.level + (node.module or ""))
    return out


def test_no_module_imports_aidlc_v4():
    offending = {str(p.relative_to(PKG)): mods for p in PKG.rglob("*.py") if (mods := [m for m in _imported_modules(p) if "aidlc_v4" in m.replace("aidlc_v4_eval", "").split(".")])}
    assert offending == {}


def test_spec_reads_only_its_own_files():
    spec = aidlc_v4_eval.SPEC
    for path in (spec.docs_dir, spec.instruction_file, *spec.system_prompt.values()):
        assert path.resolve().is_relative_to(PKG), path


def test_registered_and_scored_by_its_own_evaluation():
    spec = get_workflow("aidlc_v4_eval")
    assert spec is aidlc_v4_eval.SPEC and spec.reward_signal == "aidlc/compliance"
    assert isinstance(spec.scorers["openhands-sdk"](), AidlcEvalEvaluation)


# --- fixed -----------------------------------------------------------------------------------


def test_workflow_given_to_the_agent_is_pinned():
    assert aidlc_v4_eval.SPEC.fingerprint("openhands-sdk") == FINGERPRINT


def test_copied_scoring_code_is_pinned():
    files = sorted((PKG / "reward" / "rubric").rglob("*.py")) + [PKG / "reward" / "compliance.py", PKG / "reward" / "episode.py"]
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(PKG).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    assert h.hexdigest() == SCORING_COPY


# --- scoring ---------------------------------------------------------------------------------


def test_content_honest_run_scores_one_everywhere():
    s = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
    assert s["aidlc/compliance"] == pytest.approx(1.0)
    assert [s[f"aidlc/{k}"] for k in ("order", "s1", "s2", "s3", "s4", "s5")] == pytest.approx([1.0] * 6)
    checks = {k: v for k, v in s.items() if k.startswith("aidlc/check/")}
    assert len(checks) == 35 and set(checks.values()) == {1.0}
    assert s["aidlc/content"] == pytest.approx(1.0) and s["aidlc/content_contradictions"] == 0.0


def test_claims_without_the_runs_behind_them_cost_content_not_form():
    """Same artifacts, no test run anywhere: the bands only cap stages 1 and 5, the content checks
    catch every claim that rested on a run."""
    turns = [t for t in _content_honest_turns() if "pytest" not in json.loads(t[0]["function"]["arguments"]).get("command", "")]
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/s1"] == pytest.approx(4 / 7) and s["aidlc/s2"] == pytest.approx(1.0)
    assert s["aidlc/content"] < 1.0 and s["aidlc/content_contradictions"] > 0
    for name in ("e1_test_command_run", "t1_baseline_before_write", "e5_command_run", "t5_regression_after_last_edit"):
        assert s[f"aidlc/check/{name}"] == 0.0, name


def test_a_stage_never_written_makes_no_claims():
    turns = [t for t in _content_honest_turns() if json.loads(t[0]["function"]["arguments"]).get("path") != ART[5]]
    files = {p: t for p, t in FILES.items() if p != ART[5]}
    s = score(SimpleNamespace(id="t"), episode(turns), files)
    assert s["aidlc/s5"] == 0.0
    assert not any(k.startswith(("aidlc/check/e5_", "aidlc/check/t5_")) for k in s)


# --- evaluator wrapper -----------------------------------------------------------------------


def test_evaluator_adds_signals_and_leaves_the_verifier_output_alone():
    sb = _Sandbox(_collected(FILES))
    inner = _Verifier(sb)
    out = AidlcEvalComplianceEvaluator(inner, sb).evaluate(SimpleNamespace(id="t"), episode(_content_honest_turns()))
    assert inner.collected_before == 1  # artifacts read before the verifier ran
    assert (out.reward, out.is_correct, out.metadata) == (1.0, True, {"termination_reason": "verifier_timeout"})
    sig = {s.name: s.value for s in out.signals}
    assert sig["accuracy"] == 1.0 and sig["aidlc/compliance"] == pytest.approx(1.0) and sig["aidlc/content"] == pytest.approx(1.0)


def test_evaluator_falls_back_to_the_verifier_when_collection_fails():
    sb = _Sandbox(fail=True)
    out = AidlcEvalComplianceEvaluator(_Verifier(sb), sb).evaluate(SimpleNamespace(id="t"), episode(_content_honest_turns()))
    assert [s.name for s in out.signals] == ["accuracy"]


def test_evaluation_survives_pickling():
    """Training pickles the policy into the Ray actor; the unpickled one scores the same."""
    ev = pickle.loads(pickle.dumps(AidlcEvalEvaluation()))
    data = ev.from_outputs({**FILES, "/tmp/swe-bench-pro/notes.md": "x"})
    assert data == FILES
    assert ev.score(SimpleNamespace(id="t"), episode(_content_honest_turns()), data) == score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
