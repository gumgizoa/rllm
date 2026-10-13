"""``WorkflowSpec``: what one workflow puts in the sandbox and how its compliance is scored.

Two fields are keyed by harness name (``OpenHandsSdkHarness.name`` etc.), because what they hold
is specific to one agent:

``system_prompt``
    The replacement is the harness's own default prompt with its procedure section rewritten,
    so each (workflow, harness) pair needs its own template.
``scorers``
    A compliance scorer reads the agent's tool calls through a front end for that harness. A
    harness with no entry gets resolve rate only, never a score computed by the wrong parser.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowSpec:
    """One workflow: what to put in the sandbox and how to score compliance.

    docs_dir          documents uploaded to ``container_dir``, all of it (``workflows/<name>/docs``)
    container_dir     absolute path the instruction and the system prompt point at
    entry_doc         a file ``docs_dir`` must hold, checked before any sandbox exists
    instruction_file  joined to the task text (before or after it); ``None`` = task text alone
    system_prompt     harness name -> template replacing that harness's system prompt
    scorers           harness name -> factory of an evaluation policy for ``SandboxTaskHooks``
    reward_signal     the scorers' signal in [0, 1] that train.py folds into the reward
                      (``recipe.workflow.compliance_reward``); the others are logged only
    output_dirs       container paths (directories or files) the workflow has the agent write its
                      reports to, outside the repository; read back into
                      ``episode.artifacts["workflow_outputs"]`` (``run_artifacts.py``)
    """

    docs_dir: Path
    container_dir: str
    entry_doc: str
    instruction_file: Path | None = None
    system_prompt: Mapping[str, Path] = field(default_factory=dict)
    scorers: Mapping[str, Callable[[], Any]] = field(default_factory=dict)
    reward_signal: str | None = None
    output_dirs: tuple[str, ...] = ()

    def fingerprint(self, harness: str) -> str:
        """sha256 over what the agent is given -- documents, instruction, ``harness``'s system prompt.

        Stored with each episode, so a score computed later knows which version of the workflow the
        run followed.
        """
        h = hashlib.sha256()
        files = [(f"docs/{p.relative_to(self.docs_dir).as_posix()}", p) for p in sorted(self.docs_dir.rglob("*")) if p.is_file() and not p.name.startswith(".")]
        for label, path in (("instruction", self.instruction_file), ("system_prompt", self.system_prompt.get(harness))):
            if path is not None:
                files.append((label, path))
        for label, path in files:
            h.update(label.encode() + b"\0" + path.read_bytes() + b"\0")
        return h.hexdigest()
