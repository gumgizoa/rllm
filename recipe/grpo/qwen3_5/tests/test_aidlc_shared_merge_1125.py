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


# ==== D2: a script of the run's own -- its runs and their results =====================================================
def _read(command: str, observation: str, path: str, cwd: str = WD):
    """(ran, outcome) of ``path`` in one call, as ``testread.script_runs`` reads it: None for no run."""
    from recipe.grpo.qwen3_5.workflow_rubric import results as R
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    segs = shell.flat(shell.split(command, cwd)[0])
    for i, seg in enumerate(segs):
        if path in R.executed_by(seg):
            if not R.started(segs, i, observation, path, command):
                return None
            return R.outcome(segs, i, observation, command, path)
    return None


DJANGO_FAILED = (
    "Found 5 test(s).\n..E..\nERROR: test_xor (reproduce_xor_issue.XorParityTest.test_xor)\nTraceback (most recent call last):\n"
    '  File "/testbed/tests/reproduce_xor_issue.py", line 42\nAttributeError: x\n\nRan 5 tests in 0.001s\n\nFAILED (errors=1)\n'
)


def test_d2_a_django_label_runs_the_script_and_its_summary_is_the_result():
    # D2 case 1 (R1): `runtests.py reproduce_xor_issue` from tests/ runs tests/reproduce_xor_issue.py; `| tail` hides
    # the exit code, the runner's summary says FAILED
    assert _read("cd /testbed/tests && python runtests.py reproduce_xor_issue 2>&1 | tail -20", DJANGO_FAILED + OK, f"{WD}/tests/reproduce_xor_issue.py") == "fail"
    # must keep its reading: a runner of another label does not run the script
    assert _read("cd /testbed/tests && python runtests.py queries 2>&1 | tail -20", "Ran 9 tests in 0.1s\n\nOK\n" + OK, f"{WD}/tests/reproduce_xor_issue.py") is None


def test_d2_a_runner_given_the_script_among_others_is_read_by_its_own_lines():
    # D2 case 6 (R5): pytest of another test and the script; the call fails (exit 1) for the other test only
    out = "testing/test_fixture.py::test_state FAILED [ 50%]\nreproduce_issue.py::test_records PASSED [100%]\n==== 1 failed, 1 passed in 0.04s ====\n"
    cmd = "cd /testbed && python -m pytest testing/test_fixture.py::test_state reproduce_issue.py -v"
    assert _read(cmd, out + BAD, f"{WD}/reproduce_issue.py") == "pass"
    # must keep its reading: the script's own test failing fails it
    assert _read(cmd, out.replace("test_state FAILED", "test_state PASSED").replace("test_records PASSED", "test_records FAILED") + BAD, f"{WD}/reproduce_issue.py") == "fail"


def test_d2_a_run_that_never_started_is_no_run():
    # D2 case 3 / 13 (O1): the file is not there; case 16 (R5): the runner dies in build_suite before loading it
    assert (
        _read(
            "cd /testbed && python test_signature.py",
            "python: can't open file '/testbed/test_signature.py': [Errno 2] No such file or directory\n[The command completed with exit code 2.]",
            f"{WD}/test_signature.py",
        )
        is None
    )
    crash = (
        "Testing against Django installed in '/testbed/django'\nTraceback (most recent call last):\n"
        '  File "tests/runtests.py", line 569, in <module>\n  File "/testbed/django/test/runner.py", line 575, in build_suite\n'
        "TypeError: 'NoneType' object is not iterable\n"
    )
    assert _read("cd /testbed && python tests/runtests.py tests/queries/test_qs_combinators.py -v 2 2>&1 | head -150", crash + OK, f"{WD}/tests/queries/test_qs_combinators.py") is None
    # must keep its reading: a script that ran and reports another file missing failed; a runner whose traceback shows
    # the script's file loaded it (D2 case 11)
    assert _read("cd /testbed && python repro.py", "FileNotFoundError: [Errno 2] No such file or directory: 'data.txt'" + BAD, f"{WD}/repro.py") == "fail"
    loaded = 'Traceback (most recent call last):\n  File "/testbed/tests/test_radio_issue.py", line 3, in <module>\nRuntimeError: Model class doesn\'t declare an explicit app_label\n'
    assert _read("cd /testbed/tests && python runtests.py test_radio_issue", loaded + BAD, f"{WD}/tests/test_radio_issue.py") == "fail"


def test_d2_an_unfinished_run_fails_only_by_a_failure_already_printed():
    still = (
        "\n[The command has no new output after 30 seconds. You may wait longer to see additional output by sending empty command '', "
        "send other commands to interact with the current process, send keys to interrupt/kill the command, or use the timeout parameter "
        "in execute_bash for future commands.]"
    )
    # D2 case 9 (O3): a pass line so far is no pass
    assert _read("cd /testbed && python test_lock.py", "PASS: lock() returns True on success" + still, f"{WD}/test_lock.py") is None
    # D2 case 19: a failure verdict already printed is a failure
    assert _read("cd /testbed && python test_float.py", "FAIL: Result is a float: 0.999954602131298" + still, f"{WD}/test_float.py") == "fail"


def test_d2_the_exit_code_and_the_verdict_lines():
    # D2 case 7 (O4): `|| true` hides the exit code and the output has no verdict
    assert _read("cd /testbed && timeout 10 python test_x.py || true", "WARNING: Could not find expected output" + OK, f"{WD}/test_x.py") is None
    # D2 case 17 (O4): `> file && cat file` ending with 1 and showing nothing never reached the cat: the script's 1
    assert _read("cd /testbed && python test_reproduction.py > /tmp/test_output.txt 2>&1 && cat /tmp/test_output.txt", BAD, f"{WD}/test_reproduction.py") == "fail"
    # D2 case 4 / 14 (O5): exit 0, but a failure verdict -- contradicting a later pass line -- fails it
    assert _read("cd /testbed && python test_widget.py", "FAIL: Second widget should NOT be checked\nRESULT: Bug is NOT reproducible" + OK, f"{WD}/test_widget.py") == "fail"
    assert _read("cd /testbed && python test_drag.py", "FAILED: Draggable property lost!\nSOME TESTS FAILED: 0/3 passed" + OK, f"{WD}/test_drag.py") == "fail"
    # D2 case 2 (O2): `| head` hides the exit code; the summary says it passed
    assert _read("cd /testbed && python -m pytest test_repro.py 2>&1 | head -60", "test_repro.py .\n==== 1 passed, 7 warnings in 0.2s ====\n" + OK, f"{WD}/test_repro.py") == "pass"
    # must keep its reading: an exit code of 0 with a pass line passes, one of 1 fails
    assert _read("cd /testbed && python test_x.py", "All checks passed" + OK, f"{WD}/test_x.py") == "pass"
    assert _read("cd /testbed && python test_x.py", "done" + BAD, f"{WD}/test_x.py") == "fail"


def test_d2_python_c_runs_a_script_only_by_importing_or_executing_it():
    # D2 case 10 / 20 (R2): a `python -c` that writes the script's text runs nothing of it
    assert _read("cd /testbed && python -c \"open('/testbed/test_translate.py', 'w').write('import os')\"", "File fixed" + OK, f"{WD}/test_translate.py") is None
    # must keep its reading: importing it from the directory it sits in runs it
    assert _read('cd /testbed && python -c "import test_translate; test_translate.main()"', "PASS" + OK, f"{WD}/test_translate.py") == "pass"


def test_d2_a_script_is_run_under_every_path_it_has_had():
    # D2 case 5 (R3): the script recorded at tests/model_formsets_regress/test_can_add.py, moved to tests/, run there
    old, new = f"{WD}/tests/model_formsets_regress/test_can_add.py", f"{WD}/tests/test_can_add.py"
    ctx = _ctx([create(old), sh(f"mv {old} {new}"), sh(f"cd {WD} && python {new}", "ModuleNotFoundError: No module named 'x'" + BAD)], diff={})
    hist = T.script_history(ctx, ["tests/model_formsets_regress/test_can_add.py"])
    assert {old, new} <= hist
    assert [(x.step, x.outcome) for rs in T.script_runs(ctx, hist).values() for x in rs] == [(3, "fail")]
    # must keep its reading: a file of the same name elsewhere that the run never moved is another script
    assert f"{WD}/other/test_can_add.py" not in hist
    # a bare file name names every file of that name the run wrote
    assert old in T.script_history(ctx, ["test_can_add.py"])


def test_d2_aidlc_reads_the_reproduction_runs_by_the_shared_reading():
    # D2 case 1 / 11 (R1): aidlc's own reading found the label run but not its result (`| tail`): the summary gives it
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import Action as AAction

    acts = [
        AAction("create", "file_editor", path=f"{WD}/tests/repro_issue.py", text="import unittest\n", status="ok", observation="File created successfully"),
        AAction("shell", "terminal", command="cd /testbed/tests && python runtests.py repro_issue 2>&1 | tail -20", observation=DJANGO_FAILED + OK),
        AAction("shell", "terminal", command="cd /testbed && python missing_repro.py", observation="python: can't open file '/testbed/missing_repro.py': [Errno 2] No such file or directory" + OK),
    ]
    for rd in (RD4, RD5):
        obs = rd.observe(_aidlc_run(acts), workdir=WD, ctx=rd.bare_context(_aidlc_run(acts), WD, {}))
        assert [(r[0], r.outcome) for r in obs.ran("tests/repro_issue.py")] == [(2, "fail")]
        assert obs.ran("missing_repro.py") == []  # (O1) never started: no run


def test_d2_a_logged_warning_is_no_verdict():
    # v5run1 000003: exit 0, "All tests PASSED!", and astropy's `IERSWarning: failed to download ...` on the way
    out = "WARNING: IERSWarning: failed to download https://x/finals2000A.all [astropy.utils.iers.iers]\n  PASSED\nAll tests PASSED!\n"
    assert _read("cd /testbed && python reproduce_issue.py 2>&1", out + OK, f"{WD}/reproduce_issue.py") == "pass"
    # must keep its reading: the script's own lower-case verdict still fails it
    assert _read("cd /testbed && python reproduce_issue.py 2>&1", "check_slug: failed\n" + OK, f"{WD}/reproduce_issue.py") == "fail"


# ==== D3: one test's state in a run's output ==========================================================================
def test_d3_a_passed_line_says_the_test_passed():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence as E

    # D3 case 1 / 2 / 8 (P1, P2): aidlc's passed-name reader, now the shared one -- whatever else failed in the run
    out = "sklearn/svm/tests/test_sparse.py::test_linearsvc_iris PASSED\nsklearn/svm/tests/test_sparse.py::test_other FAILED\n==== 1 failed, 1 passed in 1.0s ===="
    assert E.test_state(out, "test_linearsvc_iris") is True
    assert E.test_state("test_trunc_time_func (db_functions.datetime.test_extract_trunc.DateFunctionTests) ... ok\n", "test_trunc_time_func") is True
    # must keep its reading: a name the output does not hold is unknown (a quiet run names no passing test)
    assert E.test_state("..F\n==== 1 failed, 2 passed in 0.1s ====", "test_linearsvc_iris") is None


def test_d3_unittest_s_two_line_form():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence as E

    # D3 case 3 / 16 (P4): unittest -v prints the name, then the docstring line ending with the result
    out = "test_far_expiration (tests.responses.test_cookie.SetCookieTests)\nCookie will expire when a distant expiration time is provided. ... ok\n\nRan 11 tests in 0.01s\n\nOK\n"
    assert E.test_state(out, "test_far_expiration") is True
    assert E.test_state(out.replace("provided. ... ok", "provided. ... FAIL"), "test_far_expiration") is False
    # must keep its reading: a name line whose next line is no result says nothing
    assert E.test_state("test_far_expiration (tests.responses.test_cookie.SetCookieTests)\nsome log line\n", "test_far_expiration") is None


def test_d3_sympy_s_file_mark_is_the_file_s():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence as E

    # D3 case 7 (F1): `[FAIL]` at the end is the file's mark; the test's own word is `ok`
    assert E.test_state("test_issue_10156 ok                                                       [FAIL]\n", "test_issue_10156") is True
    # must keep its reading: the test's own F fails it
    assert E.test_state("test_issue_10157 F                                                        [FAIL]\n", "test_issue_10157") is False


def test_d3_failing_ids_the_shared_reader_missed():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence as E

    # D3 case 18 (F2): a parameter id holding spaces
    out = "sklearn/model_selection/tests/test_search.py::test_validate_parameter_grid_input[0-TypeError-Parameter grid is not a dict or a list (0)] FAILED\n"
    assert "sklearn/model_selection/tests/test_search.py::test_validate_parameter_grid_input[0-TypeError-Parameter grid is not a dict or a list (0)]" in E.failing_ids(out)
    assert E.test_state(out, "test_validate_parameter_grid_input") is False  # a bare name fails when a parameter of it fails
    # D3 case 13 (F2): a setup error's section
    setup = "____________ ERROR at setup of test_plot_tree_gini ____________\n==== 1 passed, 2 errors in 0.5s ===="
    assert "test_plot_tree_gini" in E.failing_ids(setup) and E.test_state(setup, "test_plot_tree_gini") is False
    # D3 case 6 (F2): a test module Django's loader could not import
    loader = "ERROR: messages_tests.test_mixins (unittest.loader._FailedTest)\nImportError: Failed to import test module: messages_tests.test_mixins\n"
    assert "messages_tests.test_mixins" in E.failing_ids(loader) and E.test_state(loader, "test_mixins") is False
    # must keep its reading: a plain short-summary id
    assert E.failing_ids("FAILED tests/test_a.py::test_b - assert 1 == 2\n") == ["tests/test_a.py::test_b"]


def test_d3_a_quiet_run_s_failure_section_fails_the_test():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence as E

    # D3 case 5 / 12 (F4): `-q` prints the failure only as its section's header
    out = (
        "F\n=================================== FAILURES ===================================\n"
        "____________ RequestsTestCase.test_BASICAUTH_TUPLE_HTTP_200_OK_GET _____________\nE   TypeError: x\n==== 1 failed in 0.3s ===="
    )
    assert E.test_state(out, "test_BASICAUTH_TUPLE_HTTP_200_OK_GET") is False
    for rd in (RD4, RD5):  # aidlc reads it by the shared function
        assert rd.test_state(out, "test_BASICAUTH_TUPLE_HTTP_200_OK_GET") is False


def test_d3_a_run_stopped_at_its_first_failure_did_not_run_what_it_covers():
    # D3 case 10 (P4): `pytest -x -q` stopped at the first failure; the test it covers but never names is not known
    # to have run, so it cannot be "already failing" or "passing" by that run
    out = "F\n____ test_a ____\nE   assert 0\n!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!\n==== 1 failed in 0.1s ====\n"
    ctx = _ctx([sh("cd /testbed && python -m pytest -x -q tests/test_mod.py", out + BAD)], diff={})
    b = T.as_result(ctx, ctx.facts.runs[0])
    assert b.stopped and not T.ran_test(b, "tests/test_mod.py::test_b")
    assert T.ran_test(b, "tests/test_mod.py::test_a")  # the one it names failed
    # must keep its reading: the same run without -x went through the file
    out2 = out.replace("!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!\n", "")
    ctx2 = _ctx([sh("cd /testbed && python -m pytest -q tests/test_mod.py", out2 + BAD)], diff={})
    b2 = T.as_result(ctx2, ctx2.facts.runs[0])
    assert not b2.stopped and T.ran_test(b2, "tests/test_mod.py::test_b")
