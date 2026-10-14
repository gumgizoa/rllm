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

    Tools a workflow needs in the sandbox (all optional; a workflow without them is unaffected):

    agent_image_extra Dockerfile lines appended to the harness's agent-image bake recipe
                      (``rllm/sandbox/agent_image.py``); what they install must land under the
                      mount target (``/opt/rllm/agent``). The image tag covers them, so a workflow
                      with extras gets its own image and the others keep theirs
    sandbox_files     container path -> local file or directory, uploaded after the documents and
                      kept apart from them (the agent is not pointed at these)
    setup_script      a bash script run as root after the uploads and before the agent starts;
                      it must exit 0, or the rollout stops
    """

    docs_dir: Path
    container_dir: str
    entry_doc: str
    instruction_file: Path | None = None
    system_prompt: Mapping[str, Path] = field(default_factory=dict)
    scorers: Mapping[str, Callable[[], Any]] = field(default_factory=dict)
    reward_signal: str | None = None
    output_dirs: tuple[str, ...] = ()
    agent_image_extra: str = ""
    sandbox_files: Mapping[str, Path] = field(default_factory=dict)
    setup_script: Path | None = None

    def fingerprint(self, harness: str) -> str:
        """sha256 over what the agent is given -- documents, instruction, ``harness``'s system prompt,
        and the sandbox tooling when the workflow has any.

        Stored with each episode, so a score computed later knows which version of the workflow the
        run followed. A workflow without sandbox tooling hashes exactly as before those fields existed.
        """
        h = hashlib.sha256()
        files = [(f"docs/{p.relative_to(self.docs_dir).as_posix()}", p) for p in sorted(self.docs_dir.rglob("*")) if p.is_file() and not p.name.startswith(".")]
        for label, path in (("instruction", self.instruction_file), ("system_prompt", self.system_prompt.get(harness))):
            if path is not None:
                files.append((label, path))
        for remote, local in sorted(self.sandbox_files.items()):
            entries = [local] if local.is_file() else sorted(p for p in local.rglob("*") if p.is_file() and not p.name.startswith("."))
            files.extend((f"sandbox:{remote}/{p.relative_to(local).as_posix()}" if local.is_dir() else f"sandbox:{remote}", p) for p in entries)
        if self.setup_script is not None:
            files.append(("setup_script", self.setup_script))
        for label, path in files:
            h.update(label.encode() + b"\0" + path.read_bytes() + b"\0")
        if self.agent_image_extra:
            h.update(b"agent_image_extra\0" + self.agent_image_extra.encode() + b"\0")
        return h.hexdigest()
