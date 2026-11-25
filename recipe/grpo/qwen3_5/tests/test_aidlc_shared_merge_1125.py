"""aidlc's own test-behaviour readings merged into the shared layer (tasks/2026-11-24-test-reading-consistency/
aidlc-vs-shared/판정.md, D1 D2 D3 D5): per difference, the more accurate side of each judged pattern, with an input
the merge reads differently (from a judged case) and one that must keep its reading.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_shared_merge_1125.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import testread as T  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, EvalContext  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import read as RD4  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward import read as RD5  # noqa: E402

WD = "/testbed"
OK = "\n[The command completed with exit code 0.]"
BAD = "\n[The command completed with exit code 1.]"
PASS = "tests/test_mod.py .\n============================== 1 passed in 0.12s ===============================\n"


def sh(command: str, observation: str = OK) -> Action:
    return Action("shell", "terminal", command=command, observation=observation)


def edit(path: str) -> Action:
    return Action("replace", "file_editor", path=path, old="a = 1", text="a = 2", status="ok", observation=f"The file {path} has been edited.")


def create(path: str, text: str = "x = 1\n") -> Action:
    return Action("create", "file_editor", path=path, text=text, status="ok", observation=f"File created successfully at: {path}")


def _ctx(actions, diff, base=("pkg/mod.py", "tests/test_mod.py")):
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)] + [Step(len(actions) + 1, [Action("other")])])
    rub = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
    col = Collected(workdir=WD, diff=diff, mode="online", base_present={p: True for p in base})
    return EvalContext(rubric=rub, run=run, collected=col, facts=F.build(rub, run, col))


def _run(ctx, step):
    return next(r for r in ctx.facts.runs if r.step == step)


# ==== D1: the code change is a write to an application source file ====================================================
def test_d1_a_reverted_source_edit_is_a_change():
    # D1 case 14 (AI1): deletion.py edited, then put back -- the final patch does not hold it; a run after the edit is
    # not a run before the first change (core-workflow.md:79 "before any source file is modified")
    ctx = _ctx([edit(f"{WD}/pkg/mod.py"), sh(f"git checkout {WD}/pkg/mod.py"), sh("python -m pytest tests/test_mod.py", PASS + OK)], diff={})
    assert F.source_change_steps(ctx)[0] == 1
    assert not T.before_change(ctx, T.run_mark(_run(ctx, 3)))
    # must keep its reading: a run before any edit is before the change
    keep = _ctx([sh("python -m pytest tests/test_mod.py", PASS + OK), edit(f"{WD}/pkg/mod.py")], diff={"pkg/mod.py": "M"})
    assert T.before_change(keep, T.run_mark(_run(keep, 1)))


def test_d1_helper_files_the_run_made_are_no_change():
    # D1 case 3 (AI1): a helper app test_app/ made to reproduce (not in the final patch); case 9 (SH1): settings.py made
    # at the root and left in the patch. Neither is application source: a run after the real edit is after the change.
    ctx = _ctx(
        [edit(f"{WD}/pkg/mod.py"), create(f"{WD}/test_app/__init__.py"), create(f"{WD}/test_app/models.py"), create(f"{WD}/settings.py"), sh("python -m pytest tests/test_mod.py", PASS + OK)],
        diff={"pkg/mod.py": "M", "settings.py": "?"},
    )
    assert F.source_change_steps(ctx) == [1]
    assert T.after_change(ctx, T.run_mark(_run(ctx, 5)))
    # must keep its reading: a new module the final change keeps inside the package is a change
    keep = _ctx([edit(f"{WD}/pkg/mod.py"), sh("python -m pytest tests/test_mod.py", PASS + OK), create(f"{WD}/pkg/compat.py")], diff={"pkg/mod.py": "M", "pkg/compat.py": "A"})
    assert F.source_change_steps(keep) == [1, 3]
    assert not T.after_change(keep, T.run_mark(_run(keep, 2)))


def test_d1_removing_a_scratch_or_regenerated_file_is_no_change():
    # D1 case 18 (SH4): rm of the run's own reproduction scripts; case 7: rm of ply's parser table, which the final
    # patch holds as regenerated (M), not removed
    ctx = _ctx(
        [edit(f"{WD}/pkg/mod.py"), create(f"{WD}/reproduce_issue.py"), sh(f"rm -f {WD}/reproduce_issue.py {WD}/pkg/parsetab.py"), sh("python -m pytest tests/test_mod.py", PASS + OK)],
        diff={"pkg/mod.py": "M", "pkg/parsetab.py": "M"},
        base=("pkg/mod.py", "pkg/parsetab.py", "tests/test_mod.py"),
    )
    assert F.source_change_steps(ctx) == [1]
    assert T.after_change(ctx, T.run_mark(_run(ctx, 4)))
    # must keep its reading: removing a source file of the repository that the final change removes is a change
    keep = _ctx([sh(f"rm {WD}/pkg/old.py"), sh("python -m pytest tests/test_mod.py", PASS + OK)], diff={"pkg/old.py": "D"}, base=("pkg/old.py", "tests/test_mod.py"))
    assert F.source_change_steps(keep) == [1]


def test_d1_a_script_that_edits_the_source_is_the_change_itself():
    # D1 case 11 (OR5): the check script written by the heredoc and run in the same call rewrites the source; its run
    # is the first change -- not a run before it (the heredoc body's text is no order of execution)
    script = (
        "cat > /openspec/fix.py << 'EOF' && python3 /openspec/fix.py\n"
        "with open('/testbed/pkg/mod.py') as f:\n    s = f.read()\n"
        "with open('/testbed/pkg/mod.py', 'w') as f:\n    f.write(s.replace('a', 'b'))\n"
        "print('Successfully modified')\nEOF"
    )
    ctx = _ctx([sh(script, "Successfully modified" + OK), sh("python -m pytest tests/test_mod.py", PASS + OK)], diff={"pkg/mod.py": "M"})
    (w,) = T.change_marks(ctx)
    runs = T.script_runs(ctx, {"/openspec/fix.py"})["/openspec/fix.py"]
    assert runs and not T.before(runs[0].mark, w) and not T.after(runs[0].mark, w)
    assert T.after_change(ctx, T.run_mark(_run(ctx, 2)))
    # must keep its reading: a sed write before the runner in one call is before it (R2)
    keep = _ctx([sh(f"sed -i 's/a/b/' {WD}/pkg/mod.py && python -m pytest tests/test_mod.py", PASS + OK)], diff={"pkg/mod.py": "M"})
    assert T.after_change(keep, T.run_mark(_run(keep, 1)))


def test_d1_writes_outside_the_repository_are_no_change():
    # D1 case 2 / 13 (AI6): check scripts under /openspec are no source change; must keep: a sed write is one (SH3)
    ctx = _ctx(
        [sh("mkdir -p /openspec/checks && cat > /openspec/checks/c.py << 'EOF'\nprint(1)\nEOF"), sh("python -m pytest tests/test_mod.py", PASS + OK), sh(f"sed -i 's/a/b/' {WD}/pkg/mod.py")],
        diff={"pkg/mod.py": "M"},
    )
    assert F.source_change_steps(ctx) == [3]
    assert T.before_change(ctx, T.run_mark(_run(ctx, 2)))


def _aidlc_run(actions):
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import Action as AAction
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import Run as ARun
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import Step as AStep

    return ARun("t", [AStep(n, [a]) for n, a in enumerate(actions, 1)] + [AStep(len(actions) + 1, [AAction("other")])])


def test_d1_aidlc_reads_the_shared_change():
    # D1 case 5 (SH3): a sed write aidlc's own trace did not see; case 6 / 17 (AI7): a `python -c` whose text holds `/`
    # read as a write target; case 2 (AI6): a check script under /openspec counted as a source edit
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import Action as AAction

    acts = [
        AAction("shell", "terminal", command="cat > /openspec/checks/c.py << 'EOF'\nprint(1)\nEOF", observation=OK),
        AAction("shell", "terminal", command="python -m pytest tests/test_mod.py", observation=PASS + OK),
        AAction("shell", "terminal", command=f"sed -i 's/a/b/' {WD}/pkg/mod.py", observation=OK),
        AAction("shell", "terminal", command="python -c \"import re; print(re.sub('/b/', '/', 'a/b/c'))\" > /dev/null", observation=OK),
    ]
    for rd in (RD4, RD5):
        obs = rd.observe(_aidlc_run(acts), workdir=WD, ctx=rd.bare_context(_aidlc_run(acts), WD, {"pkg/mod.py": "M"}))
        assert obs.source_steps == {"pkg/mod.py": [3]}
        assert (obs.first_edit, obs.last_edit) == (3, 3)
