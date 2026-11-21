"""Item-rule and document fixes of groups A and C (tasks/2026-11-20-agentos-bugfix-reward-fixes/05-A-C-계획.md): how a
failing test is handled, and the files tasks.md plans to change. Checked on small synthetic artifacts and runs; every new
parameter of shared code is also shown to leave the default behaviour as it was.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from recipe.grpo.qwen3_5.workflows.agentos_bugfix import derive_rubric as D  # noqa: E402

WF = RECIPE / "workflows" / "agentos_bugfix"
RUBRIC = yaml.safe_load((WF / "reward" / "rubric.yaml").read_text(encoding="utf-8"))
ITEMS = {it["id"].removeprefix("agentos_bugfix."): it for it in RUBRIC["items"]}
IT_DOC = (WF / "docs" / "commands" / "implement-tasks" / "implement-tasks.md").read_text(encoding="utf-8")


def _item_params(suffix: str) -> dict:
    return next(it["check"]["params"] for i, it in ITEMS.items() if i.endswith(suffix))


def _item(params: dict, ref: str = "tasks", state: str = "final", iid: str = "x", stage: str = "implement_tasks"):
    return SimpleNamespace(id=iid, stage=stage, check=SimpleNamespace(params=params), target=SimpleNamespace(ref=ref, state=state, type="artifact"))


# ---- A-6: a test the run wrote is corrected, never loosened -----------------------------------------------------------


def test_implement_tasks_says_a_test_you_wrote_is_corrected_not_loosened():
    line = next(ln for ln in IT_DOC.splitlines() if "instead of ticking it, and go on." in ln)
    assert line.endswith("A test you wrote is wrong only when it checks something the task does not ask for: then correct what it checks. "
                         "Never make a failing test pass by loosening or removing what it checks.")
    # the T5 quotes of the derived items are still found in that line
    assert D._T5_FIX in line and D._T5_WARN in line
