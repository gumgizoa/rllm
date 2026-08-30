"""Pre-built CLI agent images for Docker sandbox acceleration.

Bakes a harness install script into a reusable Docker image and mounts it
read-only into each task container via ``type=image`` mounts. One agent
image serves every task base image (e.g. all swebench_pro sweap tags).
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Fixed mount target inside task containers. Harnesses prepend ``bin`` to PATH.
AGENT_MOUNT_TARGET = "/opt/rllm/agent"

_IMAGE_PREFIX = "rllm-agent"

# Harnesses with a dedicated bake recipe + invocation PATH wiring.
SUPPORTED_AGENT_IMAGE_HARNESSES = frozenset({"mini-swe-agent", "opencode", "claude-code"})

# No CLI to bake — ``--agent-image`` is a no-op without warning.
AGENT_IMAGE_SILENT_SKIP_HARNESSES = frozenset({"oracle", "react"})

_WARNED_UNSUPPORTED: set[str] = set()


def agent_image_mode() -> str:
    """``auto`` (default), ``skip``/``off``, or an explicit ``repo:tag``."""
    return os.environ.get("RLLM_AGENT_IMAGE", "auto").strip()


def agent_mount_target() -> str:
    return os.environ.get("RLLM_AGENT_MOUNT_TARGET", AGENT_MOUNT_TARGET)


def _mode_disabled(mode: str) -> bool:
    return mode.lower() in {"", "skip", "0", "false", "no", "off", "none"}


def agent_image_tag(install_script: str) -> str:
    """Content-addressed local tag for *install_script*."""
    digest = hashlib.sha256(install_script.encode("utf-8")).hexdigest()[:12]
    return f"{_IMAGE_PREFIX}-{digest}"


def _image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _mini_swe_agent_dockerfile() -> str:
    """Dockerfile that installs mini-swe-agent under ``/opt/rllm/agent``."""
    return f"""\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq curl ca-certificates git \\
 && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH" \\
    UV_TOOL_DIR={AGENT_MOUNT_TARGET}/tools \\
    UV_TOOL_BIN_DIR={AGENT_MOUNT_TARGET}/bin
RUN mkdir -p {AGENT_MOUNT_TARGET}/bin {AGENT_MOUNT_TARGET}/tools && \\
    uv tool install --python 3.12 mini-swe-agent && \\
    REAL_PY="$(readlink -f {AGENT_MOUNT_TARGET}/tools/mini-swe-agent/bin/python)" && \\
    cp -a "$(dirname "$(dirname "$REAL_PY")")" {AGENT_MOUNT_TARGET}/ && \\
    CPY_NAME="$(basename "$(dirname "$(dirname "$REAL_PY")")")" && \\
    ln -sf "{AGENT_MOUNT_TARGET}/$CPY_NAME/bin/$(basename "$REAL_PY")" \\
        {AGENT_MOUNT_TARGET}/tools/mini-swe-agent/bin/python && \\
    test -x {AGENT_MOUNT_TARGET}/bin/mini-swe-agent && \\
    {AGENT_MOUNT_TARGET}/tools/mini-swe-agent/bin/python -c "import minisweagent"
"""


def _opencode_dockerfile() -> str:
    """Dockerfile that installs opencode-ai + nvm under ``/opt/rllm/agent``."""
    return f"""\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq curl ca-certificates git bash \\
 && rm -rf /var/lib/apt/lists/*
ENV NVM_DIR={AGENT_MOUNT_TARGET}/nvm
RUN mkdir -p {AGENT_MOUNT_TARGET}/bin {AGENT_MOUNT_TARGET}/nvm && \\
    curl -fsSL -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash && \\
    . "$NVM_DIR/nvm.sh" && nvm install 22 && npm install -g opencode-ai@latest && \\
    ln -sf "$(command -v opencode)" {AGENT_MOUNT_TARGET}/bin/opencode && \\
    opencode --version >/dev/null
"""


def _claude_code_dockerfile() -> str:
    """Dockerfile that installs Claude Code under ``/opt/rllm/agent/home``."""
    return f"""\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq curl ca-certificates bash \\
 && rm -rf /var/lib/apt/lists/*
ENV HOME={AGENT_MOUNT_TARGET}/home
RUN mkdir -p "$HOME" && \\
    curl -fsSL https://claude.ai/install.sh | bash && \\
    test -x "$HOME/.local/bin/claude" && \\
    "$HOME/.local/bin/claude" --version >/dev/null
"""


def dockerfile_for_install(install_script: str, harness_name: str) -> str | None:
    """Return a dedicated bake Dockerfile for *harness_name*, else ``None``."""
    if harness_name == "mini-swe-agent":
        return _mini_swe_agent_dockerfile()
    if harness_name == "opencode":
        return _opencode_dockerfile()
    if harness_name == "claude-code":
        return _claude_code_dockerfile()
    return None


def build_agent_image(install_script: str, harness_name: str, *, force: bool = False) -> str:
    """Build (or reuse) the local agent image; return its tag."""
    if harness_name not in SUPPORTED_AGENT_IMAGE_HARNESSES:
        raise RuntimeError(f"No agent-image bake recipe for harness {harness_name!r}")

    tag = agent_image_tag(install_script)
    if not force and _image_exists(tag):
        logger.info("agent image %s already present — reusing", tag)
        return tag

    dockerfile_text = dockerfile_for_install(install_script, harness_name)
    if dockerfile_text is None:
        raise RuntimeError(f"No agent-image bake recipe for harness {harness_name!r}")

    with tempfile.TemporaryDirectory(prefix="rllm-agent-image-") as tmp:
        context = Path(tmp)
        (context / "Dockerfile").write_text(dockerfile_text, encoding="utf-8")
        logger.info("Building agent image %s for harness %s ...", tag, harness_name)
        result = subprocess.run(
            ["docker", "build", "-t", tag, "--rm", "."],
            cwd=str(context),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Agent image build failed for {tag}:\n{result.stderr[-2000:]}")
    logger.info("Agent image ready: %s", tag)
    return tag


def _harness_name(agent_flow: object) -> str:
    return getattr(agent_flow, "name", type(agent_flow).__name__)


def _warn_unsupported_agent_image(harness_name: str) -> None:
    if harness_name in _WARNED_UNSUPPORTED:
        return
    _WARNED_UNSUPPORTED.add(harness_name)
    logger.warning(
        "Agent image mount is not implemented for harness %r; using per-task install instead. "
        "Supported harnesses: %s.",
        harness_name,
        ", ".join(sorted(SUPPORTED_AGENT_IMAGE_HARNESSES)),
    )


def agent_path_prefix(harness_name: str) -> str:
    """Shell prefix that finds the CLI under the mount *or* a runtime install."""
    root = agent_mount_target()
    if harness_name == "mini-swe-agent":
        return f'export PATH="{root}/bin:$HOME/.local/bin:$PATH"; '
    if harness_name == "opencode":
        return (
            f'. {root}/nvm/nvm.sh 2>/dev/null; '
            f'. "$HOME/.nvm/nvm.sh" 2>/dev/null; '
            f'export PATH="{root}/bin:$PATH"; '
        )
    if harness_name == "claude-code":
        return f'export PATH="{root}/home/.local/bin:$HOME/.local/bin:$PATH"; '
    return ""


def _agent_mount_eligible(agent_flow: object, backend: str, *, warn: bool = True) -> bool:
    """Cheap gate: would we try an agent-image mount (without building)?"""
    mode = agent_image_mode()
    if backend != "docker" or _mode_disabled(mode):
        return False

    name = _harness_name(agent_flow)

    if name in AGENT_IMAGE_SILENT_SKIP_HARNESSES:
        return False

    if name not in SUPPORTED_AGENT_IMAGE_HARNESSES:
        if warn and not _mode_disabled(mode):
            _warn_unsupported_agent_image(name)
        return False

    if not getattr(agent_flow, "use_agent_mount", False):
        return False

    install_fn = getattr(agent_flow, "install_script", None)
    if not callable(install_fn) or not install_fn().strip():
        return False

    return True


def resolve_agent_mount_image(agent_flow: object, backend: str) -> str | None:
    """Return an agent image tag to mount, or ``None`` to use per-task install."""
    if not _agent_mount_eligible(agent_flow, backend):
        return None

    name = _harness_name(agent_flow)
    install_fn = getattr(agent_flow, "install_script", None)
    assert callable(install_fn)
    install_script = install_fn()
    mode = agent_image_mode()

    if mode.lower() != "auto" and ":" in mode:
        tag = mode
        if not _image_exists(tag):
            raise RuntimeError(
                f"RLLM_AGENT_IMAGE={tag!r} was requested but the image is not present locally. "
                f"Build it first or use RLLM_AGENT_IMAGE=auto."
            )
        return tag

    return build_agent_image(install_script, name)


def flow_uses_agent_mount(agent_flow: object, backend: str) -> bool:
    """True when an agent-image mount would be attempted for this flow."""
    return _agent_mount_eligible(agent_flow, backend, warn=False)


def ensure_agent_image(agent_flow: object, *, force: bool = False) -> str | None:
    """Build or reuse the agent image for a supported harness (internal helper)."""
    name = _harness_name(agent_flow)
    if name not in SUPPORTED_AGENT_IMAGE_HARNESSES:
        return None
    install_fn = getattr(agent_flow, "install_script", None)
    if not callable(install_fn):
        return None
    install_script = install_fn()
    if not install_script.strip():
        return None
    return build_agent_image(install_script, name, force=force)


def docker_image_mount(source_tag: str, target: str | None = None) -> dict:
    """Docker Engine mount spec for ``type=image`` (Docker 28+).

    Uses ``ImageOptions.Subpath`` so only the baked agent tree is mounted,
    not the agent image's full root filesystem.
    """
    mount_target = target or agent_mount_target()
    subpath = mount_target.lstrip("/")
    return {
        "type": "image",
        "source": source_tag,
        "target": mount_target,
        "read_only": True,
        "ImageOptions": {"Subpath": subpath},
    }


__all__ = [
    "AGENT_IMAGE_SILENT_SKIP_HARNESSES",
    "AGENT_MOUNT_TARGET",
    "SUPPORTED_AGENT_IMAGE_HARNESSES",
    "agent_image_mode",
    "agent_image_tag",
    "agent_mount_target",
    "agent_path_prefix",
    "build_agent_image",
    "docker_image_mount",
    "ensure_agent_image",
    "flow_uses_agent_mount",
    "resolve_agent_mount_image",
]
