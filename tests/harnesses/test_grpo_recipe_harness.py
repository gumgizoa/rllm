"""recipe/grpo/qwen3_5/train.py: the harness the recipe builds from ``recipe.*``."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from rllm.harnesses.openhands_sdk import OpenHandsSdkHarness

RECIPE = Path(__file__).parents[2] / "recipe/grpo/qwen3_5"


@pytest.fixture(scope="module")
def train():
    spec = importlib.util.spec_from_file_location("qwen3_5_grpo_train", RECIPE / "train.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recipe(**overrides):
    base = OmegaConf.load(RECIPE / "config/config.yaml").recipe
    return OmegaConf.merge(base, OmegaConf.create(overrides))


def test_default_recipe_builds_mini_swe_agent_with_the_turn_budget(train):
    flow = train.make_agent_flow(_recipe(agent_step_limit=40))
    assert isinstance(flow, train.StepLimitedMiniSweAgent)
    assert flow.step_limit == 40


def test_openhands_sdk_recipe_carries_budget_and_tools(train):
    flow = train.make_agent_flow(_recipe(harness="openhands-sdk", agent_step_limit=150))
    assert isinstance(flow, OpenHandsSdkHarness)
    # Same cap the SDK gets (max_iteration_per_run) and the engine reads (step_limit).
    assert flow.max_iterations == 150 and flow.step_limit == 150
    assert flow.include_default_tools == ["FinishTool"]
    # train.py then applies the agent image the same way for either harness.
    assert flow.configure({"agent_image": "auto"}) == {}


def test_unknown_harness_is_refused(train):
    with pytest.raises(SystemExit, match="recipe.harness"):
        train.make_agent_flow(_recipe(harness="swe-agent"))


def test_prompt_and_response_widths_still_fill_the_context_window():
    grpo = OmegaConf.load(RECIPE / "config/rllm_grpo.yaml").rllm.data
    verl = OmegaConf.load(RECIPE / "config/verl_trainer.yaml")
    max_model_len = verl.actor_rollout_ref.rollout.max_model_len
    assert grpo.max_prompt_length + grpo.max_response_length == max_model_len
    # openhands-sdk's system prompt + tool specs measure ~7.2K tokens before the
    # issue statement; the padded prompt is cut from the left when it overruns.
    assert grpo.max_prompt_length >= 16384
