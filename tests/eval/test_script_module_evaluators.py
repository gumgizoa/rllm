"""Unit tests for ShellScriptEvaluator and PythonModuleEvaluator.

ShellScriptEvaluator runs a verifier inside a sandbox and reads a
reward file. We use a tiny in-memory sandbox stub to drive its file
operations and parsing logic without spinning up Docker.

PythonModuleEvaluator imports a verifier from a benchmark dir and
adapts to whichever signature the user wrote.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rllm.eval.module_evaluator import PythonModuleEvaluator, _coerce_eval_result
from rllm.eval.script_evaluator import _REWARD_PATHS, ShellScriptEvaluator, clear_reward_files_cmd
from rllm.eval.types import EvalOutput, Signal
from rllm.sandbox.backends.local import LocalSandbox
from rllm.types import Episode, Step, Task, Trajectory

# ---------------------------------------------------------------------------
# In-memory sandbox stub
# ---------------------------------------------------------------------------


class _FakeSandbox:
    """Pretends to be a Sandbox by routing reads/writes through a dict.

    ``files`` are what the verifier script writes when it runs; ``planted``
    are there before it (left by the agent) and are dropped by the
    reward-file cleanup unless ``clear_fails``. Both are visible to the
    ``test -f``/``cat`` shell commands the evaluator runs.
    """

    def __init__(self, files: dict[str, str] | None = None, planted: dict[str, str] | None = None, clear_fails: bool = False):
        self.verifier_writes: dict[str, str] = dict(files or {})
        self.files: dict[str, str] = dict(planted or {})
        self.clear_fails = clear_fails
        self.execs: list[tuple[str, str | None]] = []
        self.uploads: list[tuple[str, str]] = []

    def exec(self, cmd: str, timeout: float | None = None, user: str | None = None) -> str:
        self.execs.append((cmd, user))
        # ``test -f X && echo yes || echo no``
        if cmd.startswith("test -f "):
            path = cmd.split()[2]
            return "yes" if path in self.files else "no"
        # ``cat X``
        if cmd.startswith("cat "):
            return self.files[cmd.split()[1]]
        # reward-file cleanup before the verifier
        if cmd == clear_reward_files_cmd():
            if self.clear_fails:
                return ""
            self.files = {p: v for p, v in self.files.items() if p not in _REWARD_PATHS}
            return "clean"
        # the verifier script
        if cmd.startswith("chmod +x /tests/"):
            self.files.update(self.verifier_writes)
        # mkdir — no-op
        return ""

    def upload_dir(self, src: str, dst: str) -> None:
        self.uploads.append((src, dst))


def _episode() -> Episode:
    """A minimal episode that the script evaluator can score."""
    traj = Trajectory(uid="t", name="x", task="0", steps=[Step(id="s0", input="", output="ans")], output="ans")
    return Episode(id="0", task="0", trajectories=[traj])


def _bench(tmp_path: Path) -> Path:
    bench = tmp_path / "bench"
    bench.mkdir()
    tests = bench / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text("#!/bin/sh\necho ok\n")
    return bench


# ---------------------------------------------------------------------------
# ShellScriptEvaluator
# ---------------------------------------------------------------------------


class TestShellScriptEvaluator:
    def test_reads_reward_txt(self, tmp_path):
        bench = _bench(tmp_path)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        # Partial score: not correct
        sb = _FakeSandbox(files={"/logs/verifier/reward.txt": "0.75"})
        out = ShellScriptEvaluator(sandbox=sb).evaluate(task, _episode())
        assert out.reward == 0.75
        assert out.is_correct is False  # 0.75 < 1.0
        # The evaluator copies tests/ to /tests in the sandbox
        assert any(dst == "/tests" for _, dst in sb.uploads)

        # Full score: correct
        sb = _FakeSandbox(files={"/logs/verifier/reward.txt": "1.0"})
        out = ShellScriptEvaluator(sandbox=sb).evaluate(task, _episode())
        assert out.reward == 1.0
        assert out.is_correct is True

    def test_reads_reward_json(self, tmp_path):
        bench = _bench(tmp_path)
        sb = _FakeSandbox(
            files={
                "/logs/verifier/reward.json": '{"reward": 0.5, "is_correct": false, "signals": {"acc": 0.5}}',
            }
        )
        ev = ShellScriptEvaluator(sandbox=sb)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ev.evaluate(task, _episode())
        assert out.reward == 0.5
        assert out.is_correct is False
        assert any(s.name == "acc" and s.value == 0.5 for s in out.signals)

    def test_harbor_rewards_dict_averaged(self, tmp_path):
        """Harbor-style ``{"rewards": {...}}`` — values averaged."""
        bench = _bench(tmp_path)
        sb = _FakeSandbox(
            files={"/logs/verifier/reward.json": '{"rewards": {"a": 1.0, "b": 0.0}}'},
        )
        ev = ShellScriptEvaluator(sandbox=sb)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ev.evaluate(task, _episode())
        assert out.reward == 0.5

    def test_search_order_prefers_tmp_rllm(self, tmp_path):
        """``/tmp/rllm/reward.json`` wins over ``/logs/verifier/*``."""
        bench = _bench(tmp_path)
        sb = _FakeSandbox(
            files={
                "/tmp/rllm/reward.json": '{"reward": 1.0}',
                "/logs/verifier/reward.txt": "0.0",
            }
        )
        ev = ShellScriptEvaluator(sandbox=sb)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ev.evaluate(task, _episode())
        assert out.reward == 1.0

    def test_no_reward_file_returns_zero(self, tmp_path):
        bench = _bench(tmp_path)
        sb = _FakeSandbox(files={})  # nothing written
        ev = ShellScriptEvaluator(sandbox=sb)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ev.evaluate(task, _episode())
        assert out.reward == 0.0
        assert out.is_correct is False
        assert "no reward file" in out.metadata.get("error", "")

    def test_planted_reward_is_cleared_before_the_verifier(self, tmp_path):
        """An agent-planted ``/tmp/rllm/reward.json`` would win over the verifier's ``reward.txt``."""
        bench = _bench(tmp_path)
        sb = _FakeSandbox(files={"/logs/verifier/reward.txt": "0.0"}, planted={"/tmp/rllm/reward.json": '{"reward": 1.0}'})
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ShellScriptEvaluator(sandbox=sb).evaluate(task, _episode())
        assert out.reward == 0.0
        cmds = [cmd for cmd, _ in sb.execs]
        clear = cmds.index(clear_reward_files_cmd())
        assert sb.execs[clear][1] == "root"
        assert clear < next(i for i, cmd in enumerate(cmds) if cmd.startswith("chmod +x /tests/"))

    def test_reward_is_not_graded_when_cleanup_fails(self, tmp_path):
        bench = _bench(tmp_path)
        sb = _FakeSandbox(files={"/logs/verifier/reward.txt": "1.0"}, planted={"/tmp/rllm/reward.json": '{"reward": 1.0}'}, clear_fails=True)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ShellScriptEvaluator(sandbox=sb).evaluate(task, _episode())
        assert out.reward == 0.0
        assert out.metadata["termination_reason"] == "error"  # dropped, not trained on as 0
        assert not any(cmd.startswith("chmod +x /tests/") for cmd, _ in sb.execs)

    def test_local_backend_skips_the_cleanup(self, tmp_path):
        """The local backend runs on the host; the cleanup must not touch the host's /tests or /logs."""

        class _FakeLocalSandbox(_FakeSandbox, LocalSandbox):
            pass

        bench = _bench(tmp_path)
        sb = _FakeLocalSandbox(files={"/logs/verifier/reward.txt": "1.0"})
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ShellScriptEvaluator(sandbox=sb).evaluate(task, _episode())
        assert out.reward == 1.0
        assert clear_reward_files_cmd() not in [cmd for cmd, _ in sb.execs]

    def test_missing_tests_dir_short_circuits(self, tmp_path):
        bench = tmp_path / "bench-no-tests"
        bench.mkdir()
        sb = _FakeSandbox()
        ev = ShellScriptEvaluator(sandbox=sb)
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        out = ev.evaluate(task, _episode())
        assert out.reward == 0.0
        assert "no" in out.metadata.get("error", "")


# ---------------------------------------------------------------------------
# PythonModuleEvaluator
# ---------------------------------------------------------------------------


def _verifier_dir(tmp_path: Path, body: str) -> Path:
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "tests").mkdir()
    (bench / "tests" / "evaluate.py").write_text(body)
    return bench


class TestPythonModuleEvaluator:
    def test_task_episode_signature(self, tmp_path):
        bench = _verifier_dir(
            tmp_path,
            """
def evaluate(task, episode):
    expected = task.metadata.get("ground_truth", "")
    answer = episode.trajectories[-1].output if episode.trajectories else ""
    return 1.0 if expected == answer else 0.0
""",
        )
        ev = PythonModuleEvaluator.from_module(bench)
        task = Task(id="0", instruction="", metadata={"ground_truth": "yes"}, dataset_dir=bench)
        traj = Trajectory(uid="t", name="x", task="0", output="yes")
        ep = Episode(trajectories=[traj])

        out = ev.evaluate(task, ep)
        assert out.reward == 1.0
        assert out.is_correct is True

    def test_metadata_trajectory_signature(self, tmp_path):
        bench = _verifier_dir(
            tmp_path,
            """
def evaluate(metadata, trajectory):
    return {"reward": 1.0 if metadata.get("ok") else 0.0, "is_correct": metadata.get("ok", False)}
""",
        )
        ev = PythonModuleEvaluator.from_module(bench)
        task = Task(id="0", instruction="", metadata={"ok": True}, dataset_dir=bench)
        ep = Episode(trajectories=[Trajectory(uid="t", name="x", task="0", output="yes")])

        out = ev.evaluate(task, ep)
        assert out.reward == 1.0
        assert out.is_correct is True

    def test_dotted_and_path_like_module_paths(self, tmp_path):
        """Both module-path forms — dotted and file-path-like — load the verifier."""
        bench = _verifier_dir(
            tmp_path,
            "def evaluate(task, episode): return 0.5\n",
        )
        task = Task(id="0", instruction="", metadata={}, dataset_dir=bench)

        ev = PythonModuleEvaluator.from_module(bench, module_path="tests.evaluate")
        assert ev.evaluate(task, Episode()).reward == 0.5

        ev = PythonModuleEvaluator.from_module(bench, module_path="tests/evaluate.py")
        assert ev.evaluate(task, Episode()).reward == 0.5

    def test_alternate_function_name(self, tmp_path):
        bench = _verifier_dir(
            tmp_path,
            "def grade(task, episode): return True\n",
        )
        ev = PythonModuleEvaluator.from_module(bench, function="grade")
        out = ev.evaluate(Task(id="0", instruction="", metadata={}, dataset_dir=bench), Episode())
        assert out.reward == 1.0
        assert out.is_correct is True

    def test_missing_file_raises(self, tmp_path):
        bench = tmp_path / "empty"
        bench.mkdir()

        with pytest.raises(FileNotFoundError):
            PythonModuleEvaluator.from_module(bench)

    def test_verifier_exception_returns_zero(self, tmp_path):
        bench = _verifier_dir(
            tmp_path,
            "def evaluate(task, episode):\n    raise RuntimeError('boom')\n",
        )
        ev = PythonModuleEvaluator.from_module(bench)
        out = ev.evaluate(Task(id="0", instruction="", metadata={}, dataset_dir=bench), Episode())
        assert out.reward == 0.0
        assert out.is_correct is False
        assert "boom" in out.metadata["error"]


# ---------------------------------------------------------------------------
# _coerce_eval_result
# ---------------------------------------------------------------------------


class TestCoerceEvalResult:
    def test_eval_output_passthrough(self):
        original = EvalOutput(reward=0.42, is_correct=True)
        assert _coerce_eval_result(original) is original

    @pytest.mark.parametrize(
        ("raw", "reward", "is_correct"),
        [
            (True, 1.0, True),
            (False, 0.0, False),
            (0.5, 0.5, False),
            (1.0, 1.0, True),
            ((0.5, True), 0.5, True),
        ],
        ids=["bool-true", "bool-false", "float-partial", "float-one", "tuple"],
    )
    def test_coercion_table(self, raw, reward, is_correct):
        out = _coerce_eval_result(raw)
        assert out.reward == reward
        assert out.is_correct is is_correct

    def test_dict_with_signals(self):
        out = _coerce_eval_result({"reward": 0.7, "is_correct": True, "signals": {"acc": 0.7}})
        assert out.reward == 0.7
        assert out.is_correct is True
        assert any(isinstance(s, Signal) and s.name == "acc" for s in out.signals)

    def test_unknown_type_returns_zero(self):
        out = _coerce_eval_result(object())
        assert out.reward == 0.0
        assert "Cannot coerce" in out.metadata["error"]
