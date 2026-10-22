"""The Harbor path clears agent-planted reward files before Harbor's verifier runs."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("harbor")

from harbor.trial.hooks import TrialEvent  # noqa: E402

from rllm.eval.script_evaluator import clear_reward_files_cmd  # noqa: E402
from rllm.integrations.harbor import trial_helper  # noqa: E402


class _FakeEnv:
    def __init__(self, return_code: int = 0, stdout: str = "clean"):
        self.return_code = return_code
        self.stdout = stdout
        self.execs: list[tuple[str, str | None]] = []

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.execs.append((command, user))
        return SimpleNamespace(return_code=self.return_code, stdout=self.stdout, stderr="")


class _FakeTrial:
    def __init__(self, env: _FakeEnv):
        self._environment = env
        self.hooks: dict = {}

    def add_hook(self, event, hook) -> None:
        self.hooks.setdefault(event, []).append(hook)

    async def run(self):
        return "result"


def test_cleanup_runs_as_root_at_verification_start():
    env = _FakeEnv()
    trial = _FakeTrial(env)
    trial_helper._add_reward_file_hooks(trial)

    (hook,) = trial.hooks[TrialEvent.VERIFICATION_START]
    asyncio.run(hook(None))
    assert env.execs == [(clear_reward_files_cmd(), "root")]


@pytest.mark.parametrize("return_code, stdout", [(1, ""), (0, "")])
def test_a_failed_cleanup_fails_the_trial(return_code, stdout):
    trial = _FakeTrial(_FakeEnv(return_code=return_code, stdout=stdout))
    trial_helper._add_reward_file_hooks(trial)

    (hook,) = trial.hooks[TrialEvent.VERIFICATION_START]
    with pytest.raises(RuntimeError, match="could not clear reward files"):
        asyncio.run(hook(None))


def test_every_harbor_trial_gets_the_cleanup(monkeypatch):
    from harbor.trial.trial import Trial

    trial = _FakeTrial(_FakeEnv())

    async def create(_config):
        return trial

    monkeypatch.setattr(Trial, "create", staticmethod(create))
    assert asyncio.run(trial_helper.run_harbor_trial(SimpleNamespace())) == "result"
    assert len(trial.hooks[TrialEvent.VERIFICATION_START]) == 1
