"""Item-rule and document fixes of groups B and F (tasks/2026-11-20-agentos-bugfix-reward-fixes/04-B-F-계획.md) and the
deferred D-6 rows 12 and 21, checked on small synthetic artifacts and runs. Every new parameter of shared code is also
shown to leave the default behaviour as it was.
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
from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C  # noqa: E402

WF = RECIPE / "workflows" / "agentos_bugfix"
RUBRIC = yaml.safe_load((WF / "reward" / "rubric.yaml").read_text(encoding="utf-8"))
ITEMS = {it["id"].removeprefix("agentos_bugfix."): it for it in RUBRIC["items"]}


def _item_params(suffix: str) -> dict:
    return next(it["check"]["params"] for i, it in ITEMS.items() if i.endswith(suffix))


def _item(params: dict, ref: str = "tasks", state: str = "final", iid: str = "x", stage: str = "implement_tasks"):
    return SimpleNamespace(id=iid, stage=stage, check=SimpleNamespace(params=params), target=SimpleNamespace(ref=ref, state=state, type="artifact"))


# ---- F-1: the implement-tasks read of spec.md and requirements.md is not scored -----------------------------------


def test_the_implement_stage_spec_read_is_dropped():
    assert "implement_tasks.run.agentos_bugfix_read.spec_inputs" not in ITEMS
    assert "create_tasks.run.agentos_bugfix_read.spec_inputs" in ITEMS


# ---- F-3, decision 1: implement-tasks no longer says a task group may write no tests ------------------------------


def test_implement_tasks_says_every_implementation_group_writes_its_tests_first():
    it = (WF / "docs" / "commands" / "implement-tasks" / "implement-tasks.md").read_text(encoding="utf-8")
    assert "(if any" not in it.split("## Self-verify")[1].split("## Next step")[0]
    assert "each implementation task group writes them first, as its x.1 sub-task;" in it
    src = next(s for s in ITEMS["implement_tasks.run.agentos_bugfix_checks.pass_last"]["sources"] if "Running the tests" in s["quote"])
    assert "each implementation task group writes them first" in src["quote"]


# ---- B-6 row 5: create-tasks says tasks.md keeps its three sections ----------------------------------------------


def test_create_tasks_says_the_sections_stay_and_the_section_item_cites_it():
    ct = (WF / "docs" / "commands" / "create-tasks" / "create-tasks.md").read_text(encoding="utf-8")
    assert "every tasks.md keeps the example's three sections" in ct
    quotes = [s["quote"] for s in ITEMS["create_tasks.tasks.section_present.execution_order"]["sources"]]
    assert D.KEEP_SECTIONS_QUOTE in quotes
