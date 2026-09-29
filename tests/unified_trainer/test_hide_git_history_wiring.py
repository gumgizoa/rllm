"""AgentTrainer hands hide_git_history to the sandbox hooks it auto-wires."""

import sys
from types import ModuleType

import pytest
from omegaconf import OmegaConf

from rllm.hooks import SandboxTaskHooks
from rllm.trainer.unified_trainer import AgentTrainer


class _SandboxFlow:
    needs_env = True

    def run(self, task, config):  # pragma: no cover - never rolled out here
        raise AssertionError


@pytest.fixture
def launched(monkeypatch):
    """Capture the kwargs AgentTrainer passes to the verl launcher, without launching it."""
    captured = {}

    class _Launcher:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    module = ModuleType("rllm.trainer.verl.verl_launcher")
    module.VerlTrainerLauncher = _Launcher
    monkeypatch.setitem(sys.modules, "rllm.trainer.verl.verl_launcher", module)
    return captured


def _train(**kwargs):
    config = OmegaConf.create({"rllm": {"gateway": {}, "remote_runtime": {"enabled": False}}})
    return AgentTrainer(config=config, backend="verl", agent_flow=_SandboxFlow(), train_dataset=None, **kwargs)


@pytest.mark.parametrize("value", [True, False])
def test_flag_reaches_auto_wired_hooks(launched, value):
    _train(sandbox_backend="docker", hide_git_history=value)
    hooks = launched["hooks"]
    assert isinstance(hooks, SandboxTaskHooks)
    assert hooks.hide_git_history is value


def test_off_by_default(launched):
    _train(sandbox_backend="docker")
    assert launched["hooks"].hide_git_history is False


def test_non_docker_backend_fails_at_startup(launched):
    # Per rollout it would be an ERROR episode that compact_filtering drops.
    with pytest.raises(ValueError, match="docker"):
        _train(sandbox_backend="modal", hide_git_history=True)


def test_caller_built_hooks_without_the_flag_are_refused(launched):
    with pytest.raises(ValueError, match="auto-wired"):
        _train(hooks=SandboxTaskHooks(sandbox_backend="docker", hide_git_history=False), hide_git_history=True)


def test_caller_built_hooks_with_the_flag_are_kept(launched):
    hooks = SandboxTaskHooks(sandbox_backend="docker", hide_git_history=True)
    _train(hooks=hooks, hide_git_history=True)
    assert launched["hooks"] is hooks
