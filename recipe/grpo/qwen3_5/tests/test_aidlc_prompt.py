"""The AI-DLC arm's prompt: the task template without SkyRL's six steps, and where the
AI-DLC instruction sits in the user message.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_prompt.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prepare = _load("prepare_swegym_under_test", RECIPE / "scripts" / "prepare_swegym.py")
INST = {"problem_statement": "  Widget.frob() returns None  ", "base_commit": "0123abcd"}


def test_aidlc_template_drops_skyrl_procedure_but_keeps_task_facts():
    skyrl = prepare.render_instruction(INST, "skyrl")
    aidlc = prepare.render_instruction(INST, "aidlc")
    for marker in ("Follow these steps", "1. EXPLORATION", "6. FINAL REVIEW", "Be thorough in your exploration", INST["base_commit"]):
        assert marker in skyrl
        assert marker not in aidlc
    for kept in ("<uploaded_files>\n/testbed\n</uploaded_files>", "<issue_description>\nWidget.frob() returns None\n</issue_description>", "DON'T have to modify the testing logic", "already set up for you", "minimal changes to non-test files in the /testbed directory"):
        assert kept in aidlc
    assert prepare.render_instruction(INST) == skyrl  # default is the control arm's prompt


def test_templates_are_registered_by_style():
    assert set(prepare.INSTRUCTION_TEMPLATES) == {"skyrl", "aidlc"}
    with pytest.raises(KeyError):
        prepare.render_instruction(INST, "v1")


@pytest.fixture
def harness_cls():
    from aidlc_flow import AidlcOpenHandsSdkHarness

    return AidlcOpenHandsSdkHarness


def test_instruction_prefix_and_suffix(harness_cls):
    task = "TASK TEXT\n"
    pre = harness_cls(instruction_position="prefix")
    suf = harness_cls(instruction_position="suffix")
    text = pre.instruction_text()
    assert text and "/ai-dlc/core-workflow.md" in text
    assert pre.compose_instruction(task) == f"{text}\n\nTASK TEXT"
    assert suf.compose_instruction(task) == f"TASK TEXT\n\n{text}"
    assert harness_cls().instruction_position == "suffix"  # code default; config.yaml chooses prefix


def test_instruction_off_leaves_task_alone(harness_cls):
    h = harness_cls(instruction_file=None, instruction_position="prefix")
    assert h.compose_instruction("TASK") == "TASK"


def test_bad_position_rejected(harness_cls):
    with pytest.raises(ValueError, match="instruction_position"):
        harness_cls(instruction_position="middle")


def test_configure_applies_agent_kwargs(harness_cls):
    h = harness_cls()
    left = h.configure({"sandbox_backend": "docker", "hide_git_history": True, "agent_kwargs": {"step_limit": "15", "instruction_position": "prefix"}})
    assert h.step_limit == 15 and h.instruction_position == "prefix"
    assert left == {"hide_git_history": True}  # sandbox keys consumed, agent_kwargs consumed
    with pytest.raises(ValueError, match="no attribute"):
        h.configure({"agent_kwargs": {"turn_budget": 3}})
    with pytest.raises(ValueError, match="instruction_position"):
        h.configure({"agent_kwargs": {"instruction_position": "middle"}})
