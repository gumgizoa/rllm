"""aidlc_reward: order_v6, the episode adapter, artifact collection, the evaluator wrapper, and
the reward term in train.py's grouping hook.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_reward.py
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE))

from aidlc_reward.compliance import compliance, order_v6  # noqa: E402
from aidlc_reward.episode import episode_to_run  # noqa: E402
from aidlc_reward.evaluator import _MARK, AidlcComplianceEvaluator, parse_collected  # noqa: E402

from rllm.eval.types import EvalOutput, Signal  # noqa: E402

DOC = {
    k: f"/ai-dlc/rule-details/{n}.md"
    for k, n in {"01": "01-reverse-engineering", "02": "02-requirements-analysis", "03": "03-code-generation-planning", "04": "04-code-generation-generation", "05": "05-build-and-test"}.items()
}
ART = {
    k: f"/tmp/swe-bench-pro/{n}.md"
    for k, n in {1: "01-reverse-engineering", 2: "02-requirements-analysis", 3: "03-code-generation-planning", 4: "04-code-generation-generation", 5: "05-build-and-test"}.items()
}

# Complete artifacts in the skeletons the rule detail files prescribe (every graded field filled).
ARTIFACTS = {
    1: """---
stage: 1
name: reverse-engineering
---

## Affected Scope
- Files: pkg/mod.py
- Owning module: pkg
- Language/framework: Python

## Build & Test Commands
- Build: not applicable
- Test: python -m pytest tests/test_mod.py -q

## Existing Tests
- Path: tests/test_mod.py — Contract: parse() returns a dict

## Baseline
Recorded before any source file was modified.
- Passing: tests/test_mod.py::test_parse
- Failing: none
""",
    2: """---
stage: 2
name: requirements-analysis
---

## Functional Requirements
- R1: parse() accepts an empty string

## Non-Functional Requirements
- R2: none stated

## Edge Cases & Error Handling
- R3: None input -> TypeError

## Assumptions
- The empty string maps to an empty dict
""",
    3: """---
stage: 3
name: code-generation-planning
---

## Plan

### Step 1 [satisfies R1, R3]
- Target: pkg/mod.py (modify in place)
- Change: return {} for ""
- Contract: parse(str) -> dict unchanged
- Verification: repro calls parse("")

## Reproduction Script
- Path: /tmp/repro.py
- Exercises: R1, R3

## Requirement Coverage
- R1: Step 1
- R3: Step 1
""",
    4: """---
stage: 4
name: code-generation-generation
---

## Changed Files
- Modified: pkg/mod.py [R1, R3]
- Created: /tmp/repro.py [R1]

## Reproduction Script
- Path: /tmp/repro.py
- Executed: no

## Plan Execution
- Step 1 [R1, R3]: complete

## Deviations from Plan
- none

## Checks
- Duplicate files created: none
- Test files modified: none
""",
    5: """---
stage: 5
name: build-and-test
---

## Build
- Result: success
- Command: python -c "import pkg"

## Reproduction Script
- Result: pass
- Unmet requirements: none

## Existing Tests vs Baseline
- Command: python -m pytest tests/test_mod.py -q
- Verdict: unchanged
- Regressions: none
- Pre-existing failures: none

## Fixes Applied
- none

## Outstanding Failures
- none

## Final Change
- Files in the change: pkg/mod.py
- Unintended files in the repository: none
- Test files in the change: none
""",
}


# --- building gateway-shaped episodes ---------------------------------------------------------


def _call(i, name, **args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def episode(turns: list[tuple[dict, str]]) -> SimpleNamespace:
    """turns: (tool call, its observation). The last turn's result is never sent back, as live."""
    steps, pending = [], []
    for call, obs in turns:
        steps.append(SimpleNamespace(chat_completions=pending + [{"role": "assistant", "content": "", "tool_calls": [call]}]))
        pending = [{"role": "tool", "tool_call_id": call["id"], "content": [{"type": "text", "text": obs}]}]
    return SimpleNamespace(trajectories=[SimpleNamespace(steps=steps)])


def honest_turns() -> list[tuple[dict, str]]:
    t, i = [], iter(range(1000))
    t.append((_call(next(i), "file_editor", command="view", path="/ai-dlc/core-workflow.md"), "# core"))
    t.append((_call(next(i), "terminal", command=f"cat {DOC['01']}"), "# RE"))
    t.append((_call(next(i), "terminal", command="cd /testbed && python -m pytest tests/test_mod.py -q"), "3 passed in 0.10s"))
    t.append((_call(next(i), "file_editor", command="create", path=ART[1], file_text=ARTIFACTS[1]), "File created successfully"))
    for k in (2, 3):
        t.append((_call(next(i), "terminal", command=f"cat {DOC[f'0{k}']}"), "# doc"))
        t.append((_call(next(i), "file_editor", command="create", path=ART[k], file_text=ARTIFACTS[k]), "File created successfully"))
    t.append((_call(next(i), "terminal", command=f"cat {DOC['04']}"), "# doc"))
    t.append((_call(next(i), "file_editor", command="str_replace", path="/testbed/pkg/mod.py", old_str="a", new_str="b"), "The file has been edited"))
    t.append((_call(next(i), "file_editor", command="create", path=ART[4], file_text=ARTIFACTS[4]), "File created successfully"))
    t.append((_call(next(i), "terminal", command=f"cat {DOC['05']}"), "# doc"))
    t.append((_call(next(i), "terminal", command="cd /testbed && python -m pytest tests/test_mod.py -q"), "3 passed in 0.10s"))
    t.append((_call(next(i), "file_editor", command="create", path=ART[5], file_text=ARTIFACTS[5]), "File created successfully"))
    t.append((_call(next(i), "finish", message="done"), ""))
    return t


# --- order_v6 --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "order, prefix",
    [
        (["01", "02", "03"], 3),
        (["02", "01", "03", "04", "05"], 0),
        (["01", "03"], 1),
        (["01", "02", "03", "04", "05"], 5),
    ],
)
def test_prefix_rule(order, prefix):
    reads = {d: i for i, d in enumerate(order, start=1)}
    assert order_v6(reads, {})["prefix"] == prefix


def test_full_chain_is_one():
    reads = {"01": 1, "02": 3, "03": 5, "04": 7, "05": 9}
    writes = {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}
    o = order_v6(reads, writes)
    assert (o["chain"], o["prefix"]) == (9, 5)
    assert o["value"] == pytest.approx(1.0)


def test_read_only_is_capped_at_a_third():
    o = order_v6({"01": 1, "02": 2, "03": 3, "04": 4, "05": 5}, {})
    assert o["value"] == pytest.approx(1 / 3)


def test_one_command_reading_every_doc_earns_nothing():
    o = order_v6({d: 2 for d in ("01", "02", "03", "04", "05")}, {k: 10 + k for k in range(1, 6)})
    assert o["invalid_multi_read"] == ["01", "02", "03", "04", "05"]
    assert o["value"] == 0.0


def test_reading_all_then_writing_all_loses_the_between_stage_links():
    o = order_v6({"01": 1, "02": 2, "03": 3, "04": 4, "05": 5}, {k: 100 + k for k in range(1, 6)})
    assert o["chain"] == 5  # r_k < w_k holds, w_{k-1} < r_k never does
    assert o["value"] * 21 == pytest.approx(14.78, abs=0.01)


# --- episode adapter + full scoring ----------------------------------------------------------


def test_adapter_pairs_calls_with_their_results():
    run = episode_to_run(episode(honest_turns()), {})
    assert run.steps[2].actions[0].kind == "shell"
    assert run.steps[2].actions[0].observation == "3 passed in 0.10s"  # content-part list flattened
    assert run.steps[3].actions[0].kind == "create" and run.steps[3].actions[0].status == "ok"
    assert run.steps[-1].actions[0].observation == ""  # final call: no result sent back


def test_honest_run_scores_one_on_every_signal():
    files = {ART[k]: ARTIFACTS[k] for k in ART}
    c = compliance(episode_to_run(episode(honest_turns()), files))
    assert c["signals"] == pytest.approx({"order": 1.0, "s1": 1.0, "s2": 1.0, "s3": 1.0, "s4": 1.0, "s5": 1.0})
    assert c["mean"] == pytest.approx(1.0)


def test_no_real_test_caps_stages_1_and_5():
    turns = [t for t in honest_turns() if "pytest" not in json.loads(t[0]["function"]["arguments"]).get("command", "")]
    c = compliance(episode_to_run(episode(turns), {ART[k]: ARTIFACTS[k] for k in ART}))
    assert c["signals"]["s1"] == pytest.approx(4 / 7) and c["signals"]["s5"] == pytest.approx(4 / 7)
    assert c["signals"]["s2"] == pytest.approx(1.0)


def test_an_artifact_gone_by_the_end_earns_no_chain_credit():
    files = {ART[k]: ARTIFACTS[k] for k in ART if k != 3}
    c = compliance(episode_to_run(episode(honest_turns()), files))
    assert c["signals"]["s3"] == 0.0
    assert c["order"]["chain"] == 7  # w3 missing breaks two links


# --- artifact collection + evaluator wrapper -------------------------------------------------


def _collected(files: dict[str, str]) -> str:
    return "".join(f"{_MARK}{p}\n{base64.b64encode(t.encode()).decode()}\n" for p, t in files.items())


def test_parse_collected_roundtrips_and_ignores_foreign_paths():
    out = _collected({ART[1]: ARTIFACTS[1], "/tmp/swe-bench-pro/notes.md": "x"}) + f"{_MARK}{ART[2]}\n\n"
    assert parse_collected(out) == {ART[1]: ARTIFACTS[1], ART[2]: ""}


class _Sandbox:
    def __init__(self, output=None, fail=False):
        self.output, self.fail, self.calls = output, fail, []

    def exec(self, command, timeout=None, user=None):
        self.calls.append(command)
        if self.fail:
            raise RuntimeError("sandbox gone")
        return self.output


class _Verifier:
    def __init__(self, sandbox):
        self.sandbox, self.collected_before = sandbox, None

    def evaluate(self, task, episode):
        self.collected_before = len(self.sandbox.calls)
        return EvalOutput(reward=1.0, is_correct=True, signals=[Signal("accuracy", 1.0)], metadata={"termination_reason": "verifier_timeout"})


def test_evaluator_adds_signals_and_leaves_the_verifier_output_alone():
    sb = _Sandbox(_collected({ART[k]: ARTIFACTS[k] for k in ART}))
    inner = _Verifier(sb)
    out = AidlcComplianceEvaluator(inner, sb).evaluate(SimpleNamespace(id="t"), episode(honest_turns()))
    assert inner.collected_before == 1  # artifacts read before the verifier ran
    assert (out.reward, out.is_correct, out.metadata) == (1.0, True, {"termination_reason": "verifier_timeout"})
    sig = {s.name: s.value for s in out.signals}
    assert sig["accuracy"] == 1.0 and sig["aidlc/compliance"] == pytest.approx(1.0)
    assert sig["aidlc/artifacts_written"] == 5.0 and sig["aidlc/ran_real_test"] == 1.0


def test_evaluator_falls_back_to_the_verifier_when_collection_fails():
    sb = _Sandbox(fail=True)
    out = AidlcComplianceEvaluator(_Verifier(sb), sb).evaluate(SimpleNamespace(id="t"), episode(honest_turns()))
    assert [s.name for s in out.signals] == ["accuracy"]


def test_evaluator_falls_back_to_the_verifier_when_scoring_fails():
    sb = _Sandbox(_collected({}))
    broken = SimpleNamespace(trajectories=None)  # adapter will raise
    out = AidlcComplianceEvaluator(_Verifier(sb), sb).evaluate(SimpleNamespace(id="t"), broken)
    assert [s.name for s in out.signals] == ["accuracy"]


# --- the reward term in train.py -------------------------------------------------------------


@pytest.fixture
def train_module(monkeypatch):
    """Import train.py with its heavy dependencies (hydra, the verl trainer, datasets) stubbed."""
    stub = types.ModuleType
    hydra = stub("hydra")
    hydra.main = lambda **_: lambda f: f
    mods = {"hydra": hydra}
    for name, attr in [
        ("rllm.data", None),
        ("rllm.data.dataset", "DatasetRegistry"),
        ("rllm.harnesses", None),
        ("rllm.harnesses.mini_swe_agent", "MiniSweAgentHarness"),
        ("rllm.trainer", "AgentTrainer"),
        ("rllm.trainer.algorithms", None),
        ("rllm.trainer.algorithms.transform", "_default_traj_grouping_hook"),
    ]:
        m = stub(name)
        if attr == "_default_traj_grouping_hook":
            m._default_traj_grouping_hook = lambda episodes, *_a, **_k: episodes
        elif attr:
            setattr(m, attr, type(attr, (), {}))
        mods[name] = m
    for name, m in mods.items():
        monkeypatch.setitem(sys.modules, name, m)
    monkeypatch.setenv("RLLM_RUN_ID", "test")
    spec = importlib.util.spec_from_file_location("qwen3_5_train_under_test", RECIPE / "train.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _episodes(reason, verifier, compliance_value):
    signals = {} if compliance_value is None else {"aidlc/compliance": compliance_value}
    traj = SimpleNamespace(reward=verifier, signals=signals)
    return [SimpleNamespace(termination_reason=reason, trajectories=[traj])], traj


def test_hook_adds_lam_times_compliance(train_module):
    from rllm.workflows.workflow import TerminationReason as TR

    eps, traj = _episodes(TR.ENV_DONE, 1.0, 0.5)
    train_module.make_budget_scaled_grouping_hook(0.5, 0.2)(eps, None)
    assert traj.reward == pytest.approx(1.1)


def test_hook_budget_scale_applies_to_the_sum(train_module):
    from rllm.workflows.workflow import TerminationReason as TR

    eps, traj = _episodes(TR.MAX_TURNS_EXCEEDED, 1.0, 0.5)
    train_module.make_budget_scaled_grouping_hook(0.5, 0.2)(eps, None)
    assert traj.reward == pytest.approx(0.55)


def test_hook_without_the_signal_or_with_lam_zero_is_the_verifier_reward(train_module):
    from rllm.workflows.workflow import TerminationReason as TR

    eps, traj = _episodes(TR.ENV_DONE, 1.0, None)
    train_module.make_budget_scaled_grouping_hook(0.5, 0.2)(eps, None)
    assert traj.reward == 1.0
    eps, traj = _episodes(TR.ENV_DONE, 0.0, 0.9)
    train_module.make_budget_scaled_grouping_hook(0.5, 0.0)(eps, None)
    assert traj.reward == 0.0


def test_compliance_settings(train_module):
    from omegaconf import OmegaConf

    s = train_module._compliance_settings
    assert s(OmegaConf.create({"aidlc": {"enable": False, "reward": {"enable": True, "lam": 0.2}}})) == (False, 0.0)
    assert s(OmegaConf.create({"aidlc": {"enable": True, "reward": {"enable": False, "lam": 0.2}}})) == (True, 0.0)
    assert s(OmegaConf.create({"aidlc": {"enable": True, "reward": {"enable": True, "lam": 0.2}}})) == (True, 0.2)
