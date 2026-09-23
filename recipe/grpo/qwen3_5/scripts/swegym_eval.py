"""SWE-Gym verifier synthesis: swegym's ``eval_script`` without the ``swegym`` package.

SkyRL-v0 graded its SWE-Gym rollouts with ``swegym.harness.test_spec.make_test_spec(...)
.eval_script`` (a fork of SWE-bench's harness, github.com/SWE-Gym/SWE-Bench-Package) and
``swegym.harness.grading.get_eval_report``. This module reproduces the eval script from the
same per-repo specs, vendored into ``swegym_specs.json`` (the 17 repos / 104 repo-version
pairs that ``SkyRL-v0-293-data`` touches), so the training venv does not need ``swegym``
and its dependency tree (datasets, docker, bs4, ...).

Parity with the original ``eval_script`` is checked byte-for-byte for all 316 instances;
see README ("Verifier parity").
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SPECS_PATH = Path(__file__).with_name("swegym_specs.json")

# swegym.harness.test_spec
DIFF_MODIFIED_FILE_REGEX = r"--- a/(.*)"
HEREDOC_DELIMITER = "EOF_114329324912"
ENV_NAME = "testbed"
REPO_DIRECTORY = f"/{ENV_NAME}"


def load_specs() -> dict[str, Any]:
    return json.loads(SPECS_PATH.read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[str]:
    """F2P/P2P are lists in the train parquet and JSON strings in validation."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [str(v) for v in json.loads(value)] if value else []
    return [str(v) for v in value]


def get_test_directives(instance: dict, non_test_exts: list[str]) -> list[str]:
    """swegym.harness.utils.get_test_directives (django/humaneval branches dropped)."""
    directives = re.findall(r"diff --git a/.* b/(.*)", instance["test_patch"])
    return [d for d in directives if not any(d.endswith(ext) for ext in non_test_exts)]


def make_test_command(instance: dict, specs: dict[str, Any]) -> str:
    repo = instance["repo"].lower()
    spec = specs["specs"][repo][instance["version"]]
    if repo == "python/mypy":
        test_keys = re.findall(r"\[case ([^\]]+)\]", instance["test_patch"])
        return spec["test_cmd"] + " " + f'"{" or ".join(test_keys)}"'
    return " ".join([spec["test_cmd"], *get_test_directives(instance, specs["non_test_exts"])])


def make_eval_script(instance: dict, specs: dict[str, Any] | None = None) -> str:
    """Return the swegym ``eval_script`` for *instance* (``#!/bin/bash`` + ``set -xo pipefail``).

    No ``set -e`` on purpose (swegym: "Don't exit early because we need to revert tests
    at the end"), so a failing ``install`` step still runs the tests.
    """
    specs = specs or load_specs()
    repo = instance["repo"].lower()
    spec = specs["specs"][repo][instance["version"]]
    base_commit = instance["base_commit"]
    test_patch = instance["test_patch"]

    test_files = re.findall(DIFF_MODIFIED_FILE_REGEX, test_patch)
    reset_tests_command = f"git checkout {base_commit} {' '.join(test_files)}"
    apply_test_patch_command = f"git apply -v - <<'{HEREDOC_DELIMITER}'\n{test_patch}\n{HEREDOC_DELIMITER}"

    commands = [
        "source /opt/miniconda3/bin/activate",
        f"conda activate {ENV_NAME}",
        f"cd {REPO_DIRECTORY}",
    ]
    commands += list(spec.get("eval_commands", []))
    commands += [
        f"git config --global --add safe.directory {REPO_DIRECTORY}",
        f"cd {REPO_DIRECTORY}",
        "git status",
        "git show",
        f"git diff {base_commit}",
        "source /opt/miniconda3/bin/activate",
        f"conda activate {ENV_NAME}",
    ]
    if "install" in spec:
        commands.append(spec["install"])
    commands += [
        reset_tests_command,
        apply_test_patch_command,
        make_test_command(instance, specs),
        reset_tests_command,
    ]
    return "\n".join(["#!/bin/bash", "set -xo pipefail"] + commands) + "\n"


def parser_name(repo: str, specs: dict[str, Any] | None = None) -> str:
    specs = specs or load_specs()
    return specs["parsers"][repo.lower()]


def instance_json(instance: dict, specs: dict[str, Any] | None = None) -> dict[str, Any]:
    """What ``tests/grade.py`` needs: the gold test lists and which log parser to use."""
    specs = specs or load_specs()
    return {
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "version": instance["version"],
        "base_commit": instance["base_commit"],
        "FAIL_TO_PASS": _as_list(instance["FAIL_TO_PASS"]),
        "PASS_TO_PASS": _as_list(instance["PASS_TO_PASS"]),
        "log_parser": parser_name(instance["repo"], specs),
    }
