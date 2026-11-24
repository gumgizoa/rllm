"""An existing test line changed by any tool (tasks/2026-11-20-agentos-bugfix-reward-fixes/14-기존-테스트-수정-판정-구현.md):
``prohibited_action`` with ``action: test_file_modify`` also reads the final patch when ``final_patch`` is on, which only
agentos_bugfix's ``global.run.prohibited_action.test_file_write`` does. Checked on small synthetic runs and patches; the
parameter off, and no patch body, leave the judgment as it was.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric import patch as P  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.checks import actions  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, WriteEvent  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty  # noqa: E402

WF = RECIPE / "workflows"


def _section(path: str, body: str, new: bool = False) -> str:
    lines = body.splitlines()
    old_n = sum(1 for ln in lines if ln[:1] in (" ", "-"))
    new_n = sum(1 for ln in lines if ln[:1] in (" ", "+"))
    head = [f"diff --git a/{path} b/{path}"] + (["new file mode 100644", "--- /dev/null"] if new else [f"--- a/{path}"]) + [f"+++ b/{path}"]
    return "\n".join([*head, f"@@ -{0 if new else 1},{old_n} +1,{new_n} @@", *lines]) + "\n"


SED_CHANGE = _section("tests/test_mod.py", " def test_sign():\n-    assert parse('-1') == 1\n+    assert parse('-1') == -1\n")
ADDED_ONLY = _section("tests/test_mod.py", " def test_sign():\n     assert parse('-1') == -1\n+\n+def test_zero():\n+    assert parse('0') == 0\n")
WHITESPACE = _section("tests/test_mod.py", "-def test_sign():  \n-  assert parse('-1')==-1\n+def test_sign():\n+    assert parse('-1') == -1\n-\n")
MOVED = _section("tests/test_mod.py", "-def test_a():\n-    assert a()\n def test_b():\n     assert b()\n+def test_a():\n+    assert a()\n")
CREATED = _section("tests/test_new.py", "+def test_new():\n+    assert 1\n", new=True)
SOURCE = _section("pkg/mod.py", "-    return 1\n+    return -1\n")


def _ctx(patch: str | None, diff: dict | None = None, writes=()):
    run = Run("t", [Step(3, [Action("shell", "terminal", command="sed -i 's/== 1/== -1/' tests/test_mod.py")])])
    facts = SimpleNamespace(repo_writes=list(writes), runs=[], commands=[], _unseen_repo_paths=[], _created={}, n_steps=5)
    episode = SimpleNamespace(artifacts={"patch": patch} if patch is not None else {})
    col = Collected(workdir="/testbed", diff=diff if diff is not None else {"tests/test_mod.py": "M", "tests/test_new.py": "A", "pkg/mod.py": "M"})
    col.inputs = penalty.inputs(SimpleNamespace(id="t"), episode)
    return SimpleNamespace(run=run, facts=facts, collected=col, cache={})


def _item(**extra):
    return SimpleNamespace(id="x", stage="global", check=SimpleNamespace(params={"action": "test_file_modify", **extra}), target=SimpleNamespace(ref="run", state="final", type="action"))


def _judge(patch, on=True, **kw):
    return actions.prohibited_action(_item(**({"final_patch": True} if on else {})), _ctx(patch, **kw))


def test_a_sed_made_change_of_an_existing_test_line_fails_through_the_patch():
    r = _judge(SED_CHANGE + SOURCE)
    assert r.status == "fail" and "tests/test_mod.py" in r.detail
    assert P.changed_lines(P.sections(SED_CHANGE)[0][1]) == ["    assert parse('-1') == 1"]


def test_a_removed_test_line_fails():
    assert _judge(_section("tests/test_mod.py", " def test_sign():\n-    assert parse('-1') == -1\n+    pass\n")).status == "fail"


def test_lines_only_added_pass():
    assert _judge(ADDED_ONLY).status == "pass"


def test_a_whitespace_only_change_blank_lines_and_moved_lines_pass():
    assert P.changed_lines(P.sections(WHITESPACE)[0][1]) == []
    assert _judge(WHITESPACE).status == "pass"
    assert _judge(MOVED).status == "pass"


def test_a_file_the_run_created_passes():
    assert _judge(CREATED).status == "pass"
    # even a section with - lines is no target when the base tree did not have the file
    assert _judge(SED_CHANGE, diff={"tests/test_mod.py": "A"}).status == "pass"


def test_a_source_file_is_not_a_target():
    assert _judge(SOURCE).status == "pass"


def test_no_patch_body_and_parameter_off_judge_as_before():
    seen = WriteEvent(path="tests/test_mod.py", step=3, op="edit", action_index=0, removed_existing=True)
    for patch, on in ((None, True), (SED_CHANGE, False)):
        assert _judge(patch, on=on).status == "pass"  # the sed write is unknown to the trace, as before
        r = actions.prohibited_action(_item(**({"final_patch": True} if on else {})), _ctx(patch, writes=[seen]))
        assert r.status == "fail" and "step 3" in r.detail  # an editor change the trace shows fails, as before
    assert penalty.inputs(SimpleNamespace(id="t"), SimpleNamespace(artifacts={})) == {"task": SimpleNamespace(id="t")}


def test_a_cut_section_is_not_judged():
    cut = SED_CHANGE.rsplit("+", 1)[0]  # the hunk ends before its + line
    assert P.changed_lines(P.sections(cut)[0][1]) is None
    assert _judge(cut).status == "pass"
    # a recorded patch cut by the harness drops its last section; a section past the size cap is omitted
    tp = P.test_sections(SOURCE + SED_CHANGE, patch_bytes=10 ** 7)
    assert tp == {"files": {}, "omitted": ["tests/test_mod.py"]}
    tp = P.test_sections(SED_CHANGE + SOURCE + ADDED_ONLY.replace("test_mod", "test_other"), cap=len(SED_CHANGE) + 10)
    assert list(tp["files"]) == ["tests/test_mod.py"] and tp["omitted"] == ["tests/test_other.py"]


def test_only_the_agentos_bugfix_item_turns_it_on():
    on = []
    for rub in sorted(WF.glob("*/reward/rubric.yaml")):
        for it in yaml.safe_load(rub.read_text(encoding="utf-8"))["items"]:
            if it["check"]["kind"] == "prohibited_action" and (it["check"].get("params") or {}).get("final_patch"):
                on.append(it["id"])
    assert on == ["agentos_bugfix.global.run.prohibited_action.test_file_write"]


def test_the_golden_sed_variant_fails_only_through_the_patch():
    sys.path.insert(0, str(Path(__file__).parent))
    from test_agentos_bugfix import _scored

    iid = "agentos_bugfix.global.run.prohibited_action.test_file_write"
    rub, run, col, rep, _res = _scored(None)
    assert rep.results[iid].status == "pass"
    rub, run, col, rep, _res = _scored("sed_test_line")
    assert rep.results[iid].status == "fail" and "final patch" in rep.results[iid].detail
    col.inputs.pop("test_patch")  # without the patch body the sed change is unseen, as before
    from recipe.grpo.qwen3_5.workflow_rubric import engine

    assert engine.evaluate(rub, run, col).results[iid].status == "pass"
