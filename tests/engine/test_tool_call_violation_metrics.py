"""format/* episode metrics from the gateway's tool_call_validation markers."""

from types import SimpleNamespace

from rllm.engine.agentflow_engine import _tool_call_violation_metrics


def _t(meta=None):
    return SimpleNamespace(metadata=meta)


def test_no_validation_no_metrics():
    assert _tool_call_violation_metrics([_t(), _t({"upstream_error": {"kind": "x"}})]) == {}


def test_validated_clean_episode_is_all_zero():
    m = _tool_call_violation_metrics([_t({"tool_call_validation": "drop"})] * 3)
    assert m["format/cut"] == 0.0 and m["format/flagged"] == 0.0 and m["format/flagged_turns"] == 0.0
    assert all(v == 0.0 for k, v in m.items() if k.startswith("format/code/"))


def test_dropped_turn_marks_cut_and_codes():
    v = {"turn": "cumulative", "action": "dropped", "n_calls": 1, "codes": ["A1", "S2"], "violations": []}
    m = _tool_call_violation_metrics([_t({"tool_call_validation": "drop"}), _t({"tool_call_validation": "drop", "tool_call_violation": v})])
    assert m["format/cut"] == 1.0 and m["format/flagged"] == 1.0 and m["format/flagged_turns"] == 1.0
    assert m["format/code/A1"] == 1.0 and m["format/code/S2"] == 1.0 and m["format/code/N2"] == 0.0


def test_log_mode_flags_without_cut():
    v = {"turn": "chat", "action": "logged", "n_calls": 1, "codes": ["N2"], "violations": []}
    m = _tool_call_violation_metrics([_t({"tool_call_validation": "log", "tool_call_violation": v})] * 2)
    assert m["format/cut"] == 0.0 and m["format/flagged"] == 1.0 and m["format/flagged_turns"] == 2.0
