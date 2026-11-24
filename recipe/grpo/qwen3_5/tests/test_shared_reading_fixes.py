"""Shared-layer fixes of the 2026-11-24 test-reading cross-check (tasks/2026-11-24-test-reading-consistency/crosscheck,
수정-목록.md items 1-25): how workflow_rubric reads test runs and repository writes off a trace. Each test is built
from the cross-checked rollout it names: an input the old reading got wrong, and one that must keep its reading.

pytest recipe/grpo/qwen3_5/tests/test_shared_reading_fixes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflow_rubric import evidence as E  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import refs  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import results as R  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, EvalContext  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.replay import replay  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

WD = "/testbed"
DONE0 = "\n[The command completed with exit code 0.]\n[Current working directory: /testbed]"
DONE1 = "\n[The command completed with exit code 1.]\n[Current working directory: /testbed]"


def _summary(counts: str) -> str:
    return f"============================== {counts} in 0.12s ===============================\n"


def _runs(steps, base=None, created=None):
    """RunFacts of shell calls (command, observation), one per step, in /testbed; a final call follows."""
    run = Run("x", [Step(i + 1, [Action("shell", "terminal", command=c, observation=o)]) for i, (c, o) in enumerate(steps)] + [Step(len(steps) + 1, [Action("other")])])
    return E.runs_from(run, {(i + 1, 0): WD for i in range(len(steps))}, base, created or {}, workdir=WD)


def _writes(actions, initial=None):
    """path -> [(step, op, ok, removed_existing)] of a run of actions (one per step), replayed from /testbed."""
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)])
    rep = replay(run, WD, initial or {})
    return {p: [(e.step, e.op, e.ok, e.removed_existing) for e in evs] for p, evs in rep.writes.items()}


def sh(command: str, observation: str = DONE0) -> Action:
    return Action("shell", "terminal", command=command, observation=observation)


def _facts(actions):
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)] + [Step(len(actions) + 1, [Action("other")])])
    rub = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
    col = Collected(workdir=WD, diff=None, mode="offline")
    fx = F.build(rub, run, col)
    return EvalContext(rubric=rub, run=run, collected=col, facts=fx)


SRC = "/testbed/pkg/mod.py"
TEST = "/testbed/tests/test_mod.py"


# ---- 1. a write that failed or changed nothing is no write ----------------------------------------------------
def test_git_apply_that_errors_writes_nothing():
    # matplotlib-20488 s69: `git apply /tmp/fix.patch` -> "error: corrupt patch at line 18", exit code 128
    patch = "--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-a\n+b\n"
    mk = sh(f"cat > /tmp/fix.patch << 'EOF'\n{patch}EOF")
    bad = _writes([mk, sh("cd /testbed && git apply /tmp/fix.patch", "error: corrupt patch at line 18\n" + DONE1.replace("1.", "128."))])
    assert bad[SRC] == [(2, "edit", False, False)]
    ok = _writes([mk, sh("cd /testbed && git apply /tmp/fix.patch", DONE0)])
    assert ok[SRC][0][2] is None  # applied as before


def test_sed_whose_script_sed_refuses_writes_nothing():
    # dvc-3576_4 s105: `sed: -e expression #1, char 27: unknown command: `\'`, exit code 1
    out = "sed: -e expression #1, char 27: unknown command: `\\'\n" + DONE1
    assert _writes([sh("cd /testbed && sed -i 's/a/b\\/' tasks.md", out)])["/testbed/tasks.md"][0][2] is False
    assert _writes([sh("cd /testbed && sed -i 's/a/b/' tasks.md")])["/testbed/tasks.md"][0][2] is None
    # two seds in one call: the message cannot be placed, and the call's exit code is no lone write's
    two = _writes([sh("cd /testbed && sed -i 's/a/b\\/' tasks.md && sed -n 1p tasks.md", out)])
    assert two["/testbed/tasks.md"][0][2] is None


def test_exit_code_of_the_last_segment_fails_a_lone_write_but_not_a_redirect():
    out = "error: pathspec 'pkg/x.py' did not match any file(s) known to git\n" + DONE1
    assert _writes([sh("cd /testbed && git checkout -- pkg/x.py", out)])["/testbed/pkg/x.py"][0][2] is False
    # a redirect writes its file whatever the command's exit code; a segment followed by another has no code of its own
    assert _writes([sh("cd /testbed && python run.py > out.log", DONE1)])["/testbed/out.log"][0][2] is None
    assert _writes([sh("cd /testbed && sed -i 's/a/b/' pkg/mod.py && pytest", DONE1)])[SRC][0][2] is None


def test_a_substitution_that_matches_nothing_on_known_content_changes_nothing():
    init = {SRC: "x = 1\n"}
    assert _writes([sh(f"sed -i 's/y = 2/y = 3/' {SRC}")], init)[SRC] == [(1, "edit", False, False)]
    assert _writes([sh(f"sed -i 's/x = 1/x = 2/' {SRC}")], init)[SRC] == [(1, "edit", None, True)]


_GUARDED = """python3 << 'PYTHON'
with open('/testbed/pkg/mod.py') as f:
    content = f.read()
if old_code in content:
    content = content.replace(old_code, new_code)
    with open('/testbed/pkg/mod.py', 'w') as f:
        f.write(content)
    print("Fix applied successfully")
else:
    print("ERROR: Could not find the code to replace")
PYTHON"""


def test_a_python_write_in_the_branch_the_script_did_not_take():
    # matplotlib-20488 s70 / dvc-3576_6 s76: the else branch printed its message, the write's branch printed nothing
    echo = '    print("ERROR: Could not find the code to replace")\n'  # the terminal echoes the script: not output
    miss = _writes([sh(_GUARDED, echo + "ERROR: Could not find the code to replace\n" + DONE0)])
    assert miss[SRC][0][2] is False
    hit = _writes([sh(_GUARDED, echo + "Fix applied successfully\n" + DONE0)])
    assert hit[SRC][0][2] is None
    assert _writes([sh(_GUARDED, DONE0)])[SRC][0][2] is None  # nothing printed: cannot tell


def test_a_python_write_after_a_guard_that_exited():
    # pylint-8898 s55: `if target is None: print("ERROR: Could not find target code"); exit(1)` before the write
    script = """python3 << 'EOF'
lines = open('/testbed/pkg/mod.py').readlines()
target = None
if target is None:
    print("ERROR: Could not find target code")
    exit(1)
with open('/testbed/pkg/mod.py', 'w') as f:
    f.writelines(lines)
print("Successfully patched mod.py")
EOF"""
    assert _writes([sh(script, "ERROR: Could not find target code\n" + DONE1)])[SRC][0][2] is False
    assert _writes([sh(script, "Successfully patched mod.py\n" + DONE0)])[SRC][0][2] is None


def test_a_list_the_script_appends_to_is_not_its_literal():
    # django-15957 s56-87: `new_lines = []` filled by `.append` in a loop was written as "" and every later rewrite
    # of the file looked like it changed nothing
    script = """python3 << 'EOF'
lines = open('/testbed/pkg/mod.py').readlines()
new_lines = []
for line in lines:
    new_lines.append(line)
with open('/testbed/pkg/mod.py', 'w') as f:
    f.writelines(new_lines)
EOF"""
    (op,) = shell.write_ops(script, WD, {SRC: "a\n"})
    assert op.body is None
    assert [e[2] for e in _writes([sh(script), sh(script)], {SRC: "a\n"})[SRC]] == [None, None]
    (op,) = shell.write_ops("python3 -c \"open('/testbed/pkg/mod.py', 'w').writelines(['x\\n'])\"", WD)
    assert op.body == "x\n"


def test_failed_writes_are_no_source_change_step():
    ctx = _facts([sh(f"sed -i 's/a/b/' {SRC}"), sh(_GUARDED, "ERROR: Could not find the code to replace\n" + DONE0)])
    assert F.source_change_steps(ctx) == [1]


# ---- 2. git checkout / restore of a path is a restore ---------------------------------------------------------
def test_a_git_checkout_of_a_file_is_a_restore_and_of_an_unchanged_file_no_change():
    # matplotlib-24177 s78: the file was changed before, the restore changes it back (a source change)
    edit = sh(f"sed -i 's/a/b/' {SRC}")
    assert _writes([edit, sh("git -C /testbed checkout pkg/mod.py", "Updated 1 path from the index\n" + DONE0)])[SRC][1] == (2, "restore", None, False)
    # django-16631 s44: `git checkout HEAD -- f` of a file nothing had changed: no write
    assert _writes([sh("git -C /testbed checkout HEAD -- pkg/mod.py")])[SRC] == [(1, "restore", False, False)]
    ctx = _facts([sh("git -C /testbed checkout HEAD -- pkg/mod.py"), edit])
    assert F.source_change_steps(ctx) == [2]
    # another revision changes even an unchanged file
    assert _writes([sh("cd /testbed && git checkout HEAD~1 -- pkg/mod.py")])[SRC][0][:3] == (1, "restore", None)
    # a restore brings back the content the replay knew before the run
    assert _writes([edit, sh(f"cd /testbed && git restore pkg/mod.py && cat {SRC}")], {SRC: "a\n"})[SRC][1][1] == "restore"
    rep = replay(Run("t", [Step(1, [edit]), Step(2, [sh("cd /testbed && git checkout -- pkg/mod.py")])]), WD, {SRC: "a\n"})
    assert rep.final[SRC] == "a\n"


# ---- 3. a segment the shell skipped wrote nothing -------------------------------------------------------------
def test_the_or_branch_after_a_write_did_not_run():
    # sphinx-8721 s28: `sed -i ... viewcode.py 2>/dev/null || sed -i ... openspec/changes/issue/tasks.md`
    cmd = f"sed -i 's/x/y/' {SRC} 2>/dev/null || sed -i 's/x/y/' /testbed/openspec/tasks.md"
    w = _writes([sh(cmd)])
    assert SRC in w and "/testbed/openspec/tasks.md" not in w
    # the first write failed: the fallback ran
    w = _writes([sh(cmd, f"sed: can't read {SRC}: No such file or directory\n" + DONE0)])
    assert w[SRC][0][2] is False and w["/testbed/openspec/tasks.md"][0][2] is None
    # `&&` after a failed write: skipped; after a non-writing test: unknown, kept
    assert "/testbed/b.py" not in _writes([sh(f"sed -i 's/x/y/' {SRC} && cp {SRC} /testbed/b.py", f"sed: can't read {SRC}: No such file or directory\n" + DONE1)])
    assert "/testbed/b.py" in _writes([sh(f"grep -q x {SRC} || echo x >> /testbed/b.py")])


# ---- 4 / 5. git stash with options; a plain stash leaves untracked files alone --------------------------------
def test_git_stash_with_options_is_a_stash():
    # bokeh-13636 s66: `git stash -q && pytest ...`
    w = _writes([sh(f"sed -i 's/a/b/' {SRC}"), sh("cd /testbed && git stash -q && python -m pytest tests/test_a.py")])
    assert [e[1] for e in w[SRC]] == ["edit", "unknown"]
    assert len(_writes([sh(f"sed -i 's/a/b/' {SRC}"), sh("cd /testbed && git stash list")])[SRC]) == 1


def test_a_plain_stash_keeps_the_runs_own_untracked_files():
    # pylint-8898 s51 / sphinx-8593 s71: reproduce_issue.py was the agent's, untracked
    new = Action("create", "file_editor", path="/testbed/reproduce_issue.py", text="print(1)\n", status="ok")
    acts = [new, sh(f"sed -i 's/a/b/' {SRC}"), sh("cd /testbed && git stash"), sh("cd /testbed && git stash pop")]
    w = _writes(acts)
    assert [e[1] for e in w["/testbed/reproduce_issue.py"]] == ["create"]
    assert [e[1] for e in w[SRC]] == ["edit", "unknown", "unknown"]
    w = _writes(acts[:2] + [sh("cd /testbed && git stash -u")])
    assert [e[1] for e in w["/testbed/reproduce_issue.py"]] == ["create", "unknown"]
    # pytest-5787 s97: nothing to pop
    w = _writes(acts[:2] + [sh("cd /testbed && git stash pop", "No stash entries found.\n" + DONE1)])
    assert w[SRC][-1][1:3] == ("unknown", False)


# ---- 6. removed_existing of files the replay had not seen; own files; mv over a file ---------------------------
def test_first_edit_of_an_unseen_file_is_judged_by_its_own_text():
    # django-15741 s30: an editor replace of the import line of a base file
    rep = Action("replace", "file_editor", path=SRC, old="from a import b\nfrom c import d", text="from a import b\nfrom c import d, e", status="ok")
    assert _writes([rep])[SRC] == [(1, "edit", True, True)]
    add = Action("replace", "file_editor", path=SRC, old="    return x\n", text="    return x\n\n\ndef test_new():\n    pass\n", status="ok")
    assert _writes([add])[SRC][0][3] is False
    assert _writes([sh(f"echo 'x' >> {SRC}")])[SRC][0][3] is False  # an append adds only
    assert _writes([sh(f"sed -i 's/a/b/' {SRC}")])[SRC][0][3] is None  # unknown, no longer False
    assert _writes([sh(f"cat > {TEST} << 'EOF'\nimport x\nEOF")])[TEST][0][3] is None  # an existing test file rewritten?
    assert _writes([Action("create", "file_editor", path=TEST, text="x\n", status="ok")])[TEST][0][3] is False


def test_deleting_the_runs_own_file_removes_no_existing_line():
    # sphinx-8593 s39 / s76: rm of test files this rollout created
    made = sh(f"cat > {TEST} << 'EOF'\ndef test_a():\n    pass\nEOF")
    assert _writes([made, sh(f"rm -f {TEST}")])[TEST][-1] == (2, "delete", None, False)
    assert _writes([sh(f"rm -f {TEST}")], {TEST: "def test_old():\n    pass\n"})[TEST][-1][3] is True
    # re-created after the run removed it: nothing of the file's to lose
    assert _writes([made, sh(f"rm -f {TEST} && echo 'x = 1' > {TEST}")])[TEST][-1][3] is False


def test_a_move_over_a_known_file_is_compared_with_what_it_replaced():
    # django-12125 s133: `head -n -40 f > /tmp/c && mv /tmp/c f`
    init = {TEST: "def test_a():\n    assert 1\ndef test_b():\n    assert 2\n"}
    cut = sh(f"printf 'def test_a():\\n    assert 1\\n' > /tmp/c.py && mv /tmp/c.py {TEST}")
    assert _writes([cut], init)[TEST][-1][1:] == ("move_in", None, True)
    keep = sh(f"cp {TEST} /tmp/c.py && echo '# x' >> /tmp/c.py && mv /tmp/c.py {TEST}")
    assert _writes([keep], init)[TEST][-1][3] is False


_SESSION = "============================= test session starts ==============================\n"


# ---- 8. a pytest session's summary is its last one, not a pytester session's inside it ------------------------
def test_inner_pytester_sessions_are_not_the_runs_summary():
    # pytest-5787 s61: inner "1 failed, 1 passed" under Captured stdout, outer "1 failed"
    inner = "=== FAILURES ===\n____ test_x ____\n----- Captured stdout call -----\n" + _SESSION + "collected 2 items\n\n" + _summary("1 failed, 1 passed")
    out = "collected 1 item\n\ntesting/test_r.py::test_x FAILED [100%]\n\n" + inner + "=== short test summary info ===\nFAILED testing/test_r.py::test_x\n" + _summary("1 failed")
    (r,) = _runs([("cd /testbed && python -m pytest testing/test_r.py::test_x -v", out)])
    assert (r.valid, r.passed, r.failed) == (True, 0, 1)
    # s59: the outer summary was cut by `| head`: the outer -v lines count
    lines = "".join(f"testing/test_r.py::test_{k} {'FAILED' if k < 3 else 'PASSED'} [ {k}%]\n" for k in range(14))
    (r,) = _runs([("cd /testbed && python -m pytest testing/test_r.py -v | head -100", "collected 14 items\n\n" + lines + "\n" + inner)])
    assert (r.valid, r.passed, r.failed) == (True, 11, 3)
    # s72: with -s the inner session prints inline and the outer outcome follows on a line of its own
    s_out = "collected 1 item\n\ntesting/test_r.py::test_x " + _SESSION + "collected 2 items\n\ntest_x.py .F\n\n=== FAILURES ===\n"
    s_out += _summary("1 failed, 1 passed") + "FAILED\n"
    (r,) = _runs([("cd /testbed && python -m pytest testing/test_r.py::test_x -v -s | head -50", s_out)])
    assert (r.valid, r.passed, r.failed) == (True, 0, 1)
    # two summaries of two sessions the shell ran: still one each
    both = _runs([("pytest tests/test_a.py; pytest tests/test_b.py", _summary("1 failed") + _summary("2 passed"))])
    assert [(r.failed, r.passed) for r in both] == [(1, 0), (0, 2)]
    # a session run in a loop prints one summary per round: they add up
    (r,) = _runs([("for f in tests/test_a.py tests/test_b.py; do pytest $f; done", _summary("1 failed") + _summary("2 passed"))])
    assert (r.failed, r.passed) == (1, 2)


# ---- 9. `N warnings in Xs` alone is no test count --------------------------------------------------------------
def test_a_warnings_only_line_is_no_zero_test_summary():
    # sphinx-8595 s85 / dvc-1782 s62
    (r,) = _runs([("cd /testbed && python -m pytest tests/test_autodoc.py", "ERROR: file or directory not found: tests/test_autodoc.py\n\n" + _summary("7 warnings"))])
    assert not r.valid and r.reason == "test target not found (ERROR: file or directory not found: tests/test_autodoc.py)"
    (r,) = _runs([("cd /testbed && python -m pytest tests/t.py::C", "collecting ... ERROR: not found: /testbed/tests/t.py::C\ncollected 0 items\n" + _summary("12 warnings"))])
    assert not r.valid and r.reason.startswith("test target not found (ERROR: not found:")
    usage = "ERROR: usage: __main__.py [options] [file_or_dir] [file_or_dir] [...]\n__main__.py: error: unrecognized arguments: --bad\n"
    (r,) = _runs([("cd /testbed && python -m pytest tests/t.py --bad", usage)])
    assert not r.valid and r.reason.startswith("pytest usage error (ERROR: usage:")
    (r,) = _runs([("cd /testbed && python -m pytest tests/t.py -k nothing", _summary("5 deselected, 2 warnings"))])
    assert not r.valid and r.reason == "zero tests (only deselected / skipped)"
    (r,) = _runs([("cd /testbed && python -m pytest tests/t.py", _summary("3 passed, 2 warnings"))])
    assert r.valid and r.passed == 3


# ---- 10. a progress line the run stopped in ---------------------------------------------------------------------
def test_progress_dots_without_a_percentage_before_the_failure_report():
    # sphinx-8595 s87: `-x -q | head -50`, the line stops at the failing test
    out = "." * 64 + "F\n\n=================================== FAILURES ===================================\n___ test_x ___\n"
    (r,) = _runs([("cd /testbed && python -m pytest tests/test_ext_autodoc.py -x -q 2>&1 | head -50", out)])
    assert (r.valid, r.passed, r.failed) == (True, 64, 1)
    (r,) = _runs([("cd /testbed && python -m pytest tests/test_ext_autodoc.py | head -3", "......\nsome other text\n")])
    assert not r.valid  # a row of dots with nothing pytest-like after it


# ---- 11. the value of an option is no selection -------------------------------------------------------------------
def test_option_values_are_not_node_ids():
    # sphinx-8595 s88
    assert R.selection("python -m pytest tests/test_ext_autodoc.py -x -q --no-header -W ignore::DeprecationWarning") == ()
    assert R.selection("pytest -p no:cacheprovider -o python_classes=A::B tests/a.py") == ()
    assert R.selection("pytest -Wignore::X tests/a.py::test_b") == ("tests/a.py::test_b",)


# ---- 12. python django-admin.py test -------------------------------------------------------------------------------
def test_django_admin_script_run_by_python_is_a_test_run():
    # django-12125 s33
    out = "django.core.exceptions.ImproperlyConfigured: settings are not configured\n"
    (r,) = _runs([("cd /testbed && python3 django/bin/django-admin.py test tests.test_writer.WriterTests 2>&1 | head -30", out)])
    assert r.runner == "django-admin" and r.targets == ["tests.test_writer.WriterTests"] and not r.valid
    assert _runs([("cd /testbed && python3 django/bin/django-admin.py check", "ok\n")]) == []


# ---- 13. repository tests run together with the run's own --------------------------------------------------------
def test_the_repository_part_of_a_mixed_run_counts():
    # bokeh-13636 s75: a /tmp verify dir and a repository test file in one pytest call
    cmd = "cd /testbed && python3 -m pytest /tmp/agent-os/specs/x/verify/ tests/unit/test_elements.py -v 2>&1 | tail -25"
    out = ("test_unique_ids.py::test_a PASSED [ 50%]\ntests/unit/test_elements.py::Test_div::test_render PASSED [100%]\n\n" + _summary("2 passed"))
    (r,) = _runs([(cmd, out)])
    assert (r.valid, r.passed, r.targets) == (True, 1, ["tests/unit/test_elements.py"])
    # the repository part failed: so does the run
    (r,) = _runs([(cmd, out.replace("test_render PASSED", "test_render FAILED").replace("2 passed", "1 failed, 1 passed"))])
    assert (r.valid, r.passed, r.failed) == (True, 0, 1)
    # s73: the output shows no result of the repository part (cut by tail): not readable, invalid as before
    (r,) = _runs([(cmd, "FAILED test_unique_ids.py::test_a - x\n" + _summary("1 failed, 4 passed"))])
    assert not r.valid and "outside the repository" in r.reason
    # only the run's own targets: invalid
    (r,) = _runs([("cd /testbed && python3 -m pytest /tmp/agent-os/specs/x/verify/ -v", "test_unique_ids.py::test_a PASSED [100%]\n" + _summary("1 passed"))])
    assert not r.valid



def test_a_mixed_run_cut_by_tail_counts_from_its_summary_line():
    # wf1121 step 27 getmoto__moto-7111_4 step 53: an own test under the spec folder and a repository module in one
    # pytest call, `| tail -60` leaving only the FAILED short-summary lines and the summary line
    cmd = ("cd /testbed && python -m pytest /tmp/agent-os/specs/s/verify/test_package_type_default.py tests/test_awslambda/test_lambda.py "
           "tests/test_awslambda/test_lambda.py -v 2>&1 | tail -60")
    out = ("=========================== short test summary info ============================\n"
           "FAILED tests/test_awslambda/test_lambda.py::test_a - AssertionError\n"
           "FAILED tests/test_awslambda/test_lambda.py::test_b - AssertionError\n" + _summary("4 failed, 136 passed"))
    (r,) = _runs([(cmd, out)])
    # was (0 passed, 2 failed): what the visible lines say; the summary line is the run's
    assert (r.valid, r.passed, r.failed, r.targets) == (True, 136, 4, ["tests/test_awslambda/test_lambda.py"])
    # the own target's results the output shows are taken off the summary
    shown = "/tmp/agent-os/specs/s/verify/test_package_type_default.py::test_own FAILED [  1%]\n" + out
    (r,) = _runs([(cmd, shown)])
    assert (r.valid, r.passed, r.failed) == (True, 136, 3)
    # no summary line (cut off): the repository tests' per-test lines, as before
    (r,) = _runs([(cmd, out.split("============================== ")[0])])
    assert (r.valid, r.passed, r.failed) == (True, 0, 2)

# ---- 14. pytest-pretty; output that arrives after the terminal's wait (ported from 96099612) -------------------------
_WAIT = (
    "\n[The command has no new output after 30 seconds. You may wait longer to see additional output by sending empty command '', send other commands to "
    'interact with the current process, send keys ("C-c", "C-z", "C-d") to interrupt/kill the previous command before sending your new command, or use the '
    "timeout parameter in terminal for future commands.]"
)


def _shell_runs(*calls):
    """RunFacts of shell calls given as (command, observation); a call that sends no command is kind "other"."""
    steps = [Step(n=n, actions=[Action(kind="shell" if c else "other", name="bash", command=c, observation=o)]) for n, (c, o) in enumerate(calls, start=1)]
    steps.append(Step(n=len(steps) + 1, actions=[Action(kind="shell", name="bash", command="true", observation="")]))
    return E.runs_from(Run(instance_id="t", steps=steps), {(s.n, 0): WD for s in steps}, None, {}, workdir=WD)


def test_a_pytest_pretty_results_block_is_the_summary():
    out = "tests/test_a.py::test_x PASSED [ 50%]\ntests/test_a.py::test_y FAILED [100%]\nResults (6.46s):\n         1 failed\n      1191 passed\n        52 skipped\n         1 xfailed\n" + DONE1
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py -v 2>&1 | tail -30", out))
    assert (r.valid, r.passed, r.failed, r.skipped) == (True, 1191, 1, 53)
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py -k nothing", "Results (0.21s):\n       158 deselected\n" + DONE1))
    assert not r.valid and "zero tests" in r.reason
    assert E.shaped("echo 'Results (0.21s):\n       5 passed'")
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py; printf 'Results (0.2s):\\n   5 passed\\n'", "Results (0.2s):\n   5 passed\n" + DONE1))
    assert not r.valid


def test_the_output_of_a_run_the_terminal_left_running_is_read_from_the_calls_without_a_command_after_it():
    cmd = "cd /testbed && python -m pytest tests/test_slow.py"
    summary = "============ 3 failed, 40 passed in 95.10s ============" + DONE1
    r, *rest = _shell_runs((cmd, "collected 43 items\n" + _WAIT), (None, "tests/test_slow.py ....\n" + _WAIT), (None, summary))
    assert rest == [] and (r.step, r.valid, r.passed, r.failed) == (1, True, 40, 3)
    (r,) = _shell_runs((cmd, "collected 43 items\n" + _WAIT), (None, "!!!!!! KeyboardInterrupt !!!!!!\n============ 2 passed in 31.00s ============" + DONE1))
    assert not r.valid and "no test summary" in r.reason
    r, other = _shell_runs((cmd, "collected 43 items\n" + _WAIT), ("cd /testbed && python -m pytest tests/test_a.py", summary))
    assert not r.valid and other.valid
    (r,) = _shell_runs((cmd, "collected 43 items\n" + DONE1), (None, summary))
    assert not r.valid


# ---- 15. a check script's own verdict: lower-case failed, ❌ / ✅ -------------------------------------------------------
def test_lower_case_failed_and_marks_are_a_scripts_verdict():
    segs = shell.flat(shell.split("python /tmp/check.py", WD)[0])
    assert R.outcome(segs, 0, "❌ slug check failed\n" + DONE0) == "fail"
    assert R.outcome(segs, 0, "check_slug: failed\n" + DONE0) == "fail"
    assert R.outcome(segs, 0, "✅ all slugs unique\n") == "pass"
    assert R.outcome(segs, 0, "3 passed, 0 failed\n" + DONE0) == "pass"
    assert R.outcome(segs, 0, "no tests failed\n" + DONE0) == "pass"


# ---- 16. a repository test file run directly; node --test ---------------------------------------------------------
def test_a_repository_test_file_run_directly_is_a_test_run():
    ran = "test_a (tests.test_mod.T) ... ok\n\n----------------------------------------------------------------------\nRan 3 tests in 0.01s\n\nOK\n"
    (r,) = _runs([("cd /testbed && python tests/test_mod.py", ran)])
    assert (r.runner, r.valid, r.passed) == ("test-file", True, 3)
    (r,) = _runs([("cd /testbed && python tests/test_mod.py", "done\n")])
    assert not r.valid and r.reason == "no test summary in the output"
    # the run's own script (made by the agent, or outside the repository) is no test run at all
    assert _runs([("cd /testbed && python3 test_repro.py", ran)], created={"/testbed/test_repro.py": 0}) == []
    assert _runs([("python3 /tmp/test_check.py", ran)]) == []
    assert _runs([("cd /testbed && python pkg/mod.py", ran)]) == []  # not a test file
    (r,) = _runs([("cd /testbed && node test/slug.test.js", "# tests 4\n# suites 1\n# pass 4\n# fail 0\n")])
    assert (r.runner, r.valid, r.passed) == ("test-file", True, 4)


def test_node_builtin_runner_and_its_tap_totals():
    (r,) = _runs([("cd /testbed && node --test test/", "ok 1 - a\n1..3\n# tests 3\n# pass 2\n# fail 1\n# skipped 0\n")])
    assert (r.runner, r.valid, r.passed, r.failed) == ("node-test", True, 2, 1)
    (r,) = _runs([("cd /testbed && node --test", "ℹ tests 0\nℹ pass 0\nℹ fail 0\n")])
    assert not r.valid
    assert _runs([("cd /testbed && node scripts/build.js", "# pass 3\n")]) == []


# ---- 17. yarn / pnpm / npm exec runners; go vet ------------------------------------------------------------------
def test_package_manager_runner_forms_and_go_vet():
    jest = "Tests:       2 passed, 2 total\n"
    for cmd in ("yarn jest src/a.test.js", "pnpm exec vitest run", "npm exec -- jest", "npx jest", "yarn run mocha"):
        hit = E.classify(shell.flat(shell.split("cd /testbed && " + cmd, WD)[0])[-1])
        assert hit is not None and hit.runner.name in ("jest", "vitest", "mocha"), cmd
    (r,) = _runs([("cd /testbed && yarn jest src/a.test.js", jest)])
    assert r.valid and r.passed == 2
    assert E.classify(shell.flat(shell.split("yarn install", WD)[0])[0]) is None
    assert E.classify(shell.flat(shell.split("npm test", WD)[0])[0]).runner.name == "npm-test"
    assert E.classify(shell.flat(shell.split("go vet ./...", WD)[0])[0]).runner.kind == "build"


# ---- 18. mypy's test files -----------------------------------------------------------------------------------------
def test_mypy_test_data_and_test_modules_are_test_files():
    for path in ("test-data/unit/check-classes.test", "mypy/test/teststubgen.py", "mypy/test/testcheck.py"):
        assert F.is_test_path(path), path
    for path in ("django/test/testcases.py", "mypy/test/helpers.py", "mypy/test/data.py", "sympy/testing/runtests.py", "pkg/testing.py"):
        assert not F.is_test_path(path), path


# ---- 22. pytest 3's `nodeid <- defining file OUTCOME` lines -----------------------------------------------------
def test_pytest3_inherited_test_lines_are_read():
    # astropy-7336 (swebv100 episode 000002): `pytest ... -v | head -60`, summary cut
    line = "astropy/units/tests/test_quantity_decorator.py::test_args3[u.arcsec-u.arcsec] <- astropy/units/tests/py3_test_quantity_annotations.py PASSED [  0%]\n"
    fail = "astropy/units/tests/test_quantity_decorator.py::test_args4 <- astropy/units/tests/py3_test_quantity_annotations.py FAILED [  1%]\n"
    (r,) = _runs([("cd /testbed && python -m pytest astropy/units/tests/test_quantity_decorator.py -v | head -60", "collected 339 items\n\n" + line + fail)])
    assert (r.valid, r.passed, r.failed) == (True, 1, 1)
    assert "astropy/units/tests/test_quantity_decorator.py::test_args4" in E.failing_ids(fail)
    plain = "astropy/units/tests/test_q.py::test_a PASSED [ 50%]\n"
    assert E.pytest_outcomes(plain) == {"astropy/units/tests/test_q.py::test_a": "PASSED"}


# ---- 24. a command pattern is matched against the commands, not a heredoc body ----------------------------------
def _command_facts(command: str):
    run = Run("t", [Step(1, [sh(command)]), Step(2, [Action("other")])])
    rub = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
    col = Collected(workdir=WD, diff=None, mode="offline")
    return EvalContext(rubric=rub, run=run, collected=col, facts=F.build(rub, run, col))


_SEARCH = r"(?:^|[\s;&|(])(?:grep|egrep|rg|ag|ack|git\s+grep|find)\s"


def test_words_inside_a_heredoc_body_are_no_search_command():
    # moto-7365_6 turn 5: the issue text written into initialization.md mentions `| grep -e boto`
    doc = "cat > /tmp/agent-os/specs/x/initialization.md << 'EOF'\n## Issue\nRun `pip list | grep -e boto` to see versions\nEOF"
    assert list(refs.matching(_command_facts(doc), {"fact": "command", "pattern": _SEARCH})) == []
    for cmd in ("grep -rn 'def mock' moto/", "cd /testbed && find . -name '*.py' | head", "git grep -n boto3", "cat a.txt | grep foo"):
        assert len(list(refs.matching(_command_facts(cmd), {"fact": "command", "pattern": _SEARCH}))) == 1, cmd


# ---- 25. a path with a symbol or line after it --------------------------------------------------------------------
def test_a_symbol_or_line_suffix_is_cut_from_a_path():
    for p in ("/testbed/monai/transforms/transform.py:apply_transform", "monai/transforms/transform.py:12", "monai/transforms/transform.py:12:5"):
        assert refs.norm_path(p, WD) == "monai/transforms/transform.py", p
    assert refs.norm_path("tests/test_a.py::TestX::test_y", WD) == "tests/test_a.py::TestX::test_y"
    assert refs.norm_path("/testbed/tests/test_a.py::test_y", WD) == "tests/test_a.py::test_y"
    assert refs.norm_path("docs/a:b", WD) == "docs/a:b"
