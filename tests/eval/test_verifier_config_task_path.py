"""``[verifier]`` in a per-task ``task.toml`` must be honoured for every per-task shape.

The loader's ``task_path`` rows (``DatasetRegistry.load_dataset(..., as_tasks=True)``)
root a Task at its own directory: ``dataset_dir`` *is* the task dir and ``sub_dir`` is
``None``. ``_read_verifier_config`` used to consult ``dataset_dir / sub_dir / task.toml``
only when ``sub_dir`` was set, so that shape never saw its own ``[verifier]`` table and an
explicit ``module = "tests.evaluate"`` lost to the auto-detected ``tests/test.sh`` beside it.
"""

from __future__ import annotations

from pathlib import Path

from rllm.eval._resolution import _detect_verifier
from rllm.types import Task

TASK_TOML = """\
[environment]
docker_image = "python:3.11-slim"

[verifier]
timeout_sec = 60.0
{extra}
"""


def _make_task_dir(root: Path, *, module: bool) -> Path:
    task_dir = root / "some_task"
    (task_dir / "tests").mkdir(parents=True)
    (task_dir / "tests" / "test.sh").write_text("#!/bin/bash\necho 1\n")
    (task_dir / "tests" / "evaluate.py").write_text("def evaluate(task, episode, sandbox):\n    return 1.0\n")
    (task_dir / "task.toml").write_text(TASK_TOML.format(extra='module = "tests.evaluate"' if module else ""))
    return task_dir


def test_task_path_shape_reads_module_from_task_toml(tmp_path: Path) -> None:
    task_dir = _make_task_dir(tmp_path, module=True)
    task = Task(id="t", instruction="", metadata={}, dataset_dir=task_dir, sub_dir=None)
    kind, config = _detect_verifier(task)
    assert kind == "python-host"
    assert config["module"] == "tests.evaluate"


def test_task_path_shape_without_module_autodetects_test_sh(tmp_path: Path) -> None:
    task_dir = _make_task_dir(tmp_path, module=False)
    task = Task(id="t", instruction="", metadata={}, dataset_dir=task_dir, sub_dir=None)
    kind, config = _detect_verifier(task)
    assert kind == "sandbox-shell"
    assert config == {"script": "tests/test.sh"}


def test_sub_dir_shape_still_reads_task_toml(tmp_path: Path) -> None:
    task_dir = _make_task_dir(tmp_path, module=True)
    task = Task(id="t", instruction="", metadata={}, dataset_dir=tmp_path, sub_dir=task_dir.name)
    kind, config = _detect_verifier(task)
    assert kind == "python-host"
    assert config["module"] == "tests.evaluate"
