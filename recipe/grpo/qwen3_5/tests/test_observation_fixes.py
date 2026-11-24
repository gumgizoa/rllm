"""Observation fixes of group H (tasks/2026-11-20-agentos-bugfix-reward-fixes/01-H-계획.md): what the scorer reads
off a trace -- which calls ran, which test runs count, what a check script returned, where a write landed -- checked on
small synthetic calls and runs rather than stored episodes.
"""

from __future__ import annotations

import sys
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5.workflow_rubric.trace import openhands  # noqa: E402


# ---- H-1: a call the harness refused did not run -------------------------------------------------------------

MULTI = (
    "[An error occurred during execution.]\n\nCannot execute multiple commands at once.\nPlease run each command separately "
    "OR chain them into a single command via && or ;\nProvided commands:\n(1) echo a\n(2) echo b"
)
STILL_RUNNING = (
    "[An error occurred during execution.]\n\n[Below is the output of the previous command.]\n\n"
    '[Your command "sed -i "s/a/b/" /testbed/x.py" is NOT executed. The previous command is still running - '
    "You CANNOT send new commands until the previous command is completed."
)
INVALID = "Error validating tool 'terminal': 1 validation error for TerminalAction\nview_range\n  Extra inputs are not permitted"


def test_each_refusal_makes_a_call_that_does_nothing():
    for obs in (MULTI, STILL_RUNNING, INVALID, MULTI.split("\n\n", 1)[1]):
        a = openhands.parse("terminal", {"command": "echo hi > /testbed/x.py"}, obs)
        assert a.kind == "other" and a.command is None and a.observation == obs, obs[:40]
    a = openhands.parse("file_editor", {"command": "create", "path": "/testbed/x.py", "file_text": "x"}, "Error validating tool 'file_editor': bad")
    assert a.kind == "other" and a.path is None


def test_a_refusal_with_the_previous_commands_output_before_the_notice():
    obs = (
        "[Below is the output of the previous command.]\n...\ntest_a PASSED\ntest_b PASSED\n\n"
        '[Your command "cat x" is NOT executed. The previous command is still running - You CANNOT send new commands.'
    )
    assert openhands.parse("terminal", {"command": "cat x"}, obs).kind == "other"
    assert openhands.parse("terminal", {"command": "cat x"}, "out\n" + obs).kind == "shell"  # the header must open the observation


def test_the_same_words_inside_a_commands_output_do_not_count():
    for obs in ("ok\nCannot execute multiple commands at once.", "log:\n[Your command \"x\" is NOT executed.", "grep hit: Error validating tool 'x'"):
        a = openhands.parse("terminal", {"command": "grep -r x /testbed"}, obs)
        assert a.kind == "shell" and a.command == "grep -r x /testbed"
    a = openhands.parse("file_editor", {"command": "create", "path": "/testbed/x.py", "file_text": "x"}, "File created successfully at: /testbed/x.py")
    assert a.kind == "create" and a.status == "ok"


# ---- H-2: unittest.TextTestRunner inside python is a test runner ---------------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric import evidence  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

TTR = (
    "cd /testbed && python -c \"import unittest; s = unittest.defaultTestLoader.loadTestsFromName('tests.test_x'); "
    'unittest.TextTestRunner(verbosity=2).run(s)"'
)
TTR_OUT = "test_a (tests.test_x.T) ... ok\ntest_b (tests.test_x.T) ... ok\n\n" + "-" * 70 + "\nRan 2 tests in 0.001s\n\nOK\n[Command finished with exit code 0]"


def _runs(*actions, workdir="/testbed"):
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)] + [Step(len(actions) + 1, [Action("other", "finish")])])
    return evidence.runs_from(run, {}, None, set(), workdir=workdir)


def test_text_test_runner_inside_python_is_a_valid_test_run():
    (r,) = _runs(Action("shell", "terminal", command=TTR, observation=TTR_OUT))
    assert r.runner == "python-inline" and r.valid and r.passed == 2, r.reason
    # the code that prints the summary line itself stays invalid, as with the other inline runners
    fake = TTR.replace('.run(s)"', '.run(s); print(\'Ran 2 tests\')"')
    (r,) = _runs(Action("shell", "terminal", command=fake, observation=TTR_OUT))
    assert not r.valid


# ---- H-3: per-test lines of unittest and sympy stand in for a summary line that was cut --------------------


def test_unittest_and_sympy_per_test_lines_count_when_the_summary_was_cut():
    (s,) = evidence.summaries("test_a (x.T) ... ok\ntest_b (x.T) ... FAIL\ntest_c (x.T) ... skipped 'no db'\n")
    assert (s.family, s.passed, s.failed, s.skipped) == ("unittest", 1, 1, 1)
    (s,) = evidence.summaries("test_one ok\ntest_two F\ntest_three E\n")
    assert (s.family, s.passed, s.failed, s.errors) == ("sympy", 1, 1, 1)
    # progress dots count only next to a unittest failure header or the django runner's first lines
    (s,) = evidence.summaries("Found 5 test(s).\nSystem check identified no issues (0 silenced).\n..F..\n")
    assert (s.passed, s.failed) == (4, 1)
    assert evidence.summaries("..F..\n") == []
    # a lone result word is not a run of one test or more
    assert evidence.summaries("OK\n") == [] and evidence.summaries("FAILED (failures=1)\n") == []
    # an output with a real summary keeps it alone
    (s,) = evidence.summaries("test_a (x.T) ... ok\n\n" + "-" * 70 + "\nRan 3 tests in 0.1s\n\nOK\n")
    assert s.passed == 3


def test_a_command_that_prints_per_test_lines_is_an_output_producer():
    assert evidence.shaped('print("test_a (x.T) ... ok")') and evidence.shaped("echo test_foo ok")
    assert not evidence.shaped("x = 1  # see test_foo ok later") and not evidence.shaped("loading ... okay")
    cmd = "cd /testbed && python -m unittest tests.test_x -v; echo 'test_z (x.T) ... ok'"
    runs = _runs(Action("shell", "terminal", command=cmd, observation="test_a (x.T) ... ok\ntest_z (x.T) ... ok\n"))
    assert runs and not runs[0].valid and "output producer" in runs[0].reason


# ---- H-4: a check script's result is its own exit code when the call shows it -----------------------------------

from recipe.grpo.qwen3_5.workflow_rubric import results  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace import shell  # noqa: E402

CHECK = "python /tmp/agent-os/specs/s/verify/check_fix.py"
PTH = (
    "Error processing line 1 of /opt/conda/lib/python3.9/site-packages/distutils-precedence.pth:\n\n"
    "  Traceback (most recent call last):\n    File \"<frozen site>\", line 186, in addpackage\n  ModuleNotFoundError: No module named '_distutils_hack'\n\n"
    "Remainder of file ignored\n"
)


def _read(cmd, text, code, script=CHECK):
    segs = shell.flat(shell.split(cmd, "/testbed")[0])
    (i,) = [k for k, s in enumerate(segs) if s.text.startswith(script)]
    obs = text + (f"\n[Command finished with exit code {code}]" if code is not None else "")
    return results.outcome(segs, i, obs, cmd)


def test_the_last_segment_is_read_by_its_exit_code():
    assert _read(CHECK, "Error: expected message printed\nAll checks passed", 0) == "pass"
    assert _read("cd /testbed && " + CHECK, "Traceback (most recent call last):\nValueError: expected\nok", 0) == "pass"
    assert _read(CHECK, "all good", 1) == "fail"
    # a verdict line in the script's own output stands against exit code 0
    for verdict in ("FAIL: test_x", "FAILED (failures=1)", "3 passed, 1 failed"):
        assert _read(CHECK, verdict, 0) == "fail", verdict


def test_python_start_up_noise_from_a_pth_file_is_not_read():
    assert _read(CHECK + " | tail -5", PTH + "All tests passed!", 0) == "pass"
    assert _read(CHECK + " | tail -5", "Traceback (most recent call last):\nboom", 0) == "fail"


def test_a_script_followed_only_by_and_shows_its_exit_code_when_the_call_ended_with_zero():
    cmd = CHECK + " && python -m pytest tests/test_x.py | tail -20"
    # the pytest after && printed the failure words; the script itself must have ended with 0
    assert _read(cmd, "ok\nE       AssertionError\n1 failed, 2 passed in 0.1s", 0) == "pass"
    cmd = CHECK + ' && echo "---" && python -m pytest tests/test_x.py | tail -20'
    assert _read(cmd, "ok\n---\nFAILED tests/test_x.py::t\n1 failed in 0.1s", 0) == "pass"
    # a pipe or a ';' after the script hides its exit code: the words decide, as before
    assert _read(CHECK + " | head -150", "E       AssertionError", 0) == "fail"
    assert _read(CHECK + "; echo done", "Traceback (most recent call last):\nx", 0) == "fail"
    # a non-zero call after && may be the script's failure or a later one: not read from the code
    assert results.own_exit_known(shell.flat(shell.split(cmd, "/testbed")[0]), 0, 1) is False
    # with another runner in the call, a verdict line may be the runner's: exit code 0 decides
    assert _read(CHECK + " && python -m pytest tests/test_x.py", "FAILED (failures=1)", 0) == "pass"


# ---- H-5: a run with the change stashed away is not a result of the change ------------------------------------

from types import SimpleNamespace  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric.context import CommandFact, RunFact, WriteEvent  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty_tests as PT  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C  # noqa: E402


def _cmd(step, command):
    return CommandFact(step=step, action_index=0, command=command)


def _test_run(step, command, segment="python -m pytest tests/test_a.py"):
    return RunFact(step=step, action_index=0, command=command, segment=segment, runner="pytest", kind="test", valid=True, passed=1)


def test_the_stash_rule_is_shared_and_the_penalty_keeps_it():
    assert PT.stash_marks is results.stash_marks and PT.stash_states is results.stash_states and PT.run_stashed is results.run_stashed


def test_agentos_rules_read_only_runs_with_the_change_in_place():
    one = "git stash && python -m pytest tests/test_a.py; git stash pop"
    cmds = [_cmd(3, "python -m pytest tests/test_a.py"), _cmd(5, one), _cmd(7, "git stash"), _cmd(8, "python -m pytest tests/test_a.py"),
            _cmd(10, "python -m pytest tests/test_a.py"), _cmd(12, "python -m pytest tests/test_a.py")]
    runs = [_test_run(c.step, c.command) for c in cmds if "pytest" in c.command]
    # the change goes away at step 7 and is never popped; the edit of step 9 is a new change, so step 10 tests it
    writes = [WriteEvent(path="src/a.py", step=2, op="edit"), WriteEvent(path="src/a.py", step=9, op="edit"),
              WriteEvent(path="src/a.py", step=11, op="unknown")]  # git putting content back: no edit of the agent's
    ctx = SimpleNamespace(facts=SimpleNamespace(repo_writes=writes, commands=cmds, runs=runs), cache={})
    assert [r.step for r in C.change_runs(ctx)] == [3, 10, 12]


# ---- H-6: a test run after an edit in the same call is a run after that edit ----------------------------------

import pickle  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Facts  # noqa: E402


def _facts_with(command, *writes, segment="python -m pytest tests/test_a.py"):
    f = Facts(n_steps=10)
    f.runs = [_test_run(5, command, segment)]
    f.repo_writes = [WriteEvent(path=p, step=5, op=op, action_index=0) for p, op in writes]
    F._same_call_order(f, "/testbed")
    return f.runs[0]


def test_a_run_placed_after_a_write_of_its_own_call_is_marked():
    edit_then_test = "sed -i 's/a/b/' src/a.py && python -m pytest tests/test_a.py"
    assert _facts_with(edit_then_test, ("src/a.py", "edit")).after_write_same_call
    assert _facts_with("sed -i 's/a/b/' /testbed/src/a.py && python -m pytest tests/test_a.py", ("src/a.py", "edit")).after_write_same_call
    # the run comes first, the write is git putting content back, or the write is another call's: not marked
    assert not _facts_with("python -m pytest tests/test_a.py && sed -i 's/a/b/' src/a.py", ("src/a.py", "edit")).after_write_same_call
    assert not _facts_with("git checkout src/a.py && python -m pytest tests/test_a.py", ("src/a.py", "unknown")).after_write_same_call
    assert not _facts_with(edit_then_test).after_write_same_call
    # the field has a default, so a RunFact pickled before it existed still loads with it
    r = pickle.loads(pickle.dumps(_test_run(1, "x")))
    assert r.after_write_same_call is False


def test_the_penalty_counts_a_same_call_run_after_the_last_source_change():
    tl = PT.Timeline(src=[5], existing_runs=[5], own_runs=[5], results=[results.TestResult(5, True, True, ("tests/test_a.py",))], p2_end=9)
    got = PT.judge(tl)
    assert got[PT.P2_RUN] == (0.0, True)  # same step, order unknown: not after the change
    tl.existing_late, tl.own_late, tl.results_late = {5}, {5}, {5}
    got = PT.judge(tl)
    assert got[PT.P2_RUN] == (1.0, True)
    # the run of the change's own call also tested the final code: PHASE 3's failure items keep their outside value
    assert got[PT.P3_LAST] == (1.0, False)


# ---- H-7: a repository change the trace shows no write of gets the time of the first command naming it ----------

from recipe.grpo.qwen3_5.workflow_rubric.context import Collected  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward.eval import Evaluation as BugfixEvaluation  # noqa: E402


def _repo_facts(commands, diff):
    f = Facts(n_steps=20)
    f.commands = [CommandFact(step=s, action_index=0, command=c, cwd="/testbed") for s, c in commands]
    rubric = BugfixEvaluation().rubric
    F._repo_writes(f, rubric, Collected(diff=diff, workdir="/testbed"), F.roots_of(rubric, "/testbed"), "/testbed")
    return f


def test_a_side_effect_file_is_dated_to_the_first_command_naming_it():
    f = _repo_facts(
        [(3, "cat setup.cfg"), (12, "python -c \"open('out.fits', 'w').write('x')\""), (14, "ls out.fits")],
        {"out.fits": "A", "src/a.py.orig": "A", "src/a.py.rej": "A"},
    )
    # patch's .orig / .rej are no edit; the data file is a write of step 12, content unknown
    assert f.unseen_repo_paths == [] and f.first_repo_write == 12
    (e,) = f.repo_writes
    assert (e.path, e.step, e.op, e.content) == ("out.fits", 12, "create", None)


def test_a_change_that_cannot_be_dated_stays_outside_the_trace():
    # the first command naming it only reads it (it was there already), or no command names it
    f = _repo_facts([(5, "cat data/old.txt"), (9, "python gen.py > data/old.txt")], {"data/old.txt": "M", "lib/b.py": "M"})
    assert f.unseen_repo_paths == ["data/old.txt", "lib/b.py"] and f.repo_writes == []
    assert f.first_repo_write is UNKNOWN_STEP and any("outside the trace" in n for n in f.notes)
    # an existing file the change modified is named by reading commands first; even a command that writes it is not
    # taken as its time (speckit_bug django__django-11239: a find -exec cat dated a modified client.py)
    f = _repo_facts([(14, "find /testbed -name client.py -exec cat {} \\;"), (20, "python fix.py client.py")], {"pg/client.py": "M"})
    assert f.unseen_repo_paths == ["pg/client.py"] and f.repo_writes == [] and f.first_repo_write is UNKNOWN_STEP


from recipe.grpo.qwen3_5.workflow_rubric.context import UNKNOWN as UNKNOWN_STEP  # noqa: E402


# ---- H-8: a second mv onto the same file is not a move into a directory --------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.replay import replay  # noqa: E402


def _replayed(*commands):
    run = Run("t", [Step(n, [Action("shell", "terminal", command=c)]) for n, c in enumerate(commands, 1)])
    return replay(run, "/testbed")


def test_moving_onto_the_same_file_twice_lands_on_the_file():
    spec = "/tmp/agent-os/specs/s"
    rep = _replayed(f"mkdir -p {spec}", f"echo a > /tmp/x.md && mv /tmp/x.md {spec}/tasks.md", f"echo b > /tmp/x.md && mv /tmp/x.md {spec}/tasks.md")
    assert rep.final[f"{spec}/tasks.md"] == "b\n" and f"{spec}/tasks.md/x.md" not in rep.writes
    assert [e.step for e in rep.writes[f"{spec}/tasks.md"] if e.op == "move_in"] == [2, 3]
    # a file the replay cannot see being written (python made it) is moved onto the same path twice as well
    py = "python -c \"open('/tmp/y.md', 'w').write('x')\""
    rep = _replayed(f"mkdir -p {spec}", f"{py} && mv /tmp/y.md {spec}/tasks.md", f"{py} && mv /tmp/y.md {spec}/tasks.md")
    assert f"{spec}/tasks.md/y.md" not in rep.writes and [e.step for e in rep.writes[f"{spec}/tasks.md"]] == [2, 3]


def test_moving_a_directory_still_makes_a_directory():
    rep = _replayed("mkdir -p /tmp/d && echo a > /tmp/d/f.txt", "mv /tmp/d /tmp/e", "echo b > /tmp/g.txt && mv /tmp/g.txt /tmp/e")
    assert rep.final["/tmp/e/f.txt"] == "a\n" and rep.final["/tmp/e/g.txt"] == "b\n"


# ---- H-9: a tasks.md write of unknown content is not a rewrite of the tasks -------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.replay import Replay  # noqa: E402

TASKS = "/tmp/agent-os/specs/s/tasks.md"
OPEN = "## Tasks\n\n#### Task Group 1: Fix\n- [ ] 1.0 Fix it\n  - [ ] 1.1 Write tests\n  - [ ] 1.2 Change code\n"
DONE = OPEN.replace("[ ]", "[x]")


def test_the_last_unknown_write_takes_the_sandbox_content():
    rep = Replay()
    rep.writes = {TASKS: [WriteEvent(TASKS, 3, "create", content=OPEN), WriteEvent(TASKS, 9, "move_in", content=None)],
                  "/x/cut.md": [WriteEvent("/x/cut.md", 4, "create", content=None)]}
    rep.final = {TASKS: None, "/x/cut.md": None}
    F._fill_last_write(Collected(files={TASKS: DONE, "/x/cut.md": "a"}, truncated={"/x/cut.md"}), rep)
    assert rep.writes[TASKS][-1].content == DONE and rep.final[TASKS] == DONE
    assert rep.writes["/x/cut.md"][-1].content is None  # a file the sandbox copy cut short stays unknown


def test_all_done_is_the_first_known_done_write_even_after_an_unknown_one():
    evs = [WriteEvent(TASKS, 3, "create", content=OPEN), WriteEvent(TASKS, 5, "edit", content=None), WriteEvent(TASKS, 8, "edit", content=DONE)]
    ctx = SimpleNamespace(facts=SimpleNamespace(artifact_paths={"tasks": TASKS}, writes={TASKS: evs}, final_mismatch={}), cache={})
    assert C.all_done_step(ctx) == 8
    # the content before a known write is the last known one: an unknown write between is passed over
    assert C._known_before(evs, evs[2]) == OPEN and C._known_before(evs, evs[0]) is None


# ---- H-10: a call the harness runs under another tool name ------------------------------------------------------
# openhands-sdk rewrites these before it runs them (agent/utils.py normalize_tool_call); the episode keeps the call as
# the model wrote it, so the parser reads the name and the sub-command the same way.

EDITED = "The file /testbed/x.py has been edited. Here's the result of running `cat -n` on a snippet of /testbed/x.py:\n     1\tb\n"
REPLACE = {"path": "/testbed/x.py", "old_str": "a", "new_str": "b"}


def test_the_editor_sub_command_used_as_the_tool_name_is_an_editor_call():
    for name in ("str_replace", "str_replace_editor", "str_replace </parameter", "file_editor</function>"):
        a = openhands.parse(name, dict(REPLACE, command="str_replace"), EDITED)
        assert (a.kind, a.path, a.old, a.text, a.status) == ("replace", "/testbed/x.py", "a", "b", "ok"), name
    # the name says nothing about the sub-command: the call's own `command` decides
    a = openhands.parse("str_replace", {"command": "create", "path": "/testbed/y.py", "file_text": "x"}, "File created successfully at: /testbed/y.py")
    assert (a.kind, a.text, a.status) == ("create", "x", "ok")
    assert openhands.parse("str_replace", {"command": "view", "path": "/testbed/x.py"}, "1\ta").kind == "view"


def test_an_editor_call_without_command_gets_it_from_its_arguments():
    cases = (
        (REPLACE, "replace"),
        ({"path": "/testbed/x.py", "insert_line": 3, "new_str": "b"}, "insert"),
        ({"path": "/testbed/x.py", "file_text": "x"}, "create"),
        ({"path": "/testbed/x.py"}, "view"),
        ({"path": "/testbed/x.py", "view_range": [1, 9]}, "view"),
        (dict(REPLACE, file_text="x", insert_line=1), "replace"),  # old_str is looked at first, as in the harness
        (dict(REPLACE, command=None), "replace"),  # the harness drops a null argument before it looks
    )
    for name in ("file_editor", "str_replace"):
        for args, kind in cases:
            assert openhands.parse(name, args, EDITED).kind == kind, (name, args)
    a = openhands.parse("str_replace", {"path": "/testbed/x.py", "insert_line": 3, "new_str": "b"}, "The file /testbed/x.py has been edited.")
    assert (a.kind, a.line, a.text) == ("insert", 3, "b")
    # nothing to infer from, or a sub-command the editor does not have: no action
    assert openhands.parse("str_replace", {"old_str": "a", "new_str": "b"}, "").kind == "other"
    assert openhands.parse("str_replace", dict(REPLACE, command="replace"), "").kind == "other"
    assert openhands.parse("file_editor", dict(REPLACE, command=["str_replace"]), "").kind == "other"


def test_a_refused_call_under_another_name_did_not_run():
    obs = "Error validating tool 'str_replace': 1 validation error for FileEditorAction\nold_str\n  Field required"
    assert openhands.parse("str_replace", dict(REPLACE, command="str_replace"), obs).kind == "other"
    obs = "Error validating tool 'file_editor': Cannot infer 'command' for tool 'file_editor' from empty arguments {}."
    assert openhands.parse("str_replace", {"path": "/testbed/x.py"}, obs).kind == "other"
    # an edit the editor tried and could not make is still an edit attempt, with a failed status
    obs = "[An error occurred during execution.]\n\nNo replacement was performed, old_str `a` did not appear verbatim in /testbed/x.py."
    a = openhands.parse("str_replace", REPLACE, obs)
    assert (a.kind, a.status) == ("replace", "fail")


def test_a_broken_terminal_name_is_read_by_its_leading_identifier():
    a = openhands.parse("terminal</function>", {"command": "ls /testbed"}, "x.py")
    assert (a.kind, a.command) == ("shell", "ls /testbed")


def test_names_the_harness_does_not_run_as_the_editor_stay_no_action():
    args = {"command": "create", "path": "/testbed/x.py", "file_text": "x", "old_str": "a", "new_str": "b"}
    for name in ("write", "view", "python", "tool_call", "tool_editor", "command", "editor", "str_replaced", ""):
        assert openhands.parse(name, args, f"Tool '{name}' not found. Available: ['terminal', 'file_editor']").kind == "other", name


# -- 2026-11-24: two outputs of a test run the scorer did not read (accuracy review of wf1121 step 27) -------------------
def _shell_runs(*calls):
    """RunFacts of shell calls given as (command, observation), one per step, in /testbed."""
    from recipe.grpo.qwen3_5.workflow_rubric import evidence
    from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step

    # a call that sends no command (the empty command, keys) is recorded without one, as kind "other"
    steps = [Step(n=n, actions=[Action(kind="shell" if c else "other", name="bash", command=c, observation=o)]) for n, (c, o) in enumerate(calls, start=1)]
    steps.append(Step(n=len(steps) + 1, actions=[Action(kind="shell", name="bash", command="true", observation="")]))  # a final call's output is never seen
    run = Run(instance_id="t", steps=steps)
    return evidence.runs_from(run, {(s.n, 0): "/testbed" for s in steps}, None, {}, workdir="/testbed")


_DONE = "\n[The command completed with exit code 1.]\n[Current working directory: /testbed]"
_WAIT = "\n[The command has no new output after 30 seconds. You may wait longer to see additional output by sending empty command '', send other commands to interact with the current process, send keys (\"C-c\", \"C-z\", \"C-d\") to interrupt/kill the previous command before sending your new command, or use the timeout parameter in terminal for future commands.]"


def test_a_pytest_pretty_results_block_is_the_summary():
    from recipe.grpo.qwen3_5.workflow_rubric import evidence

    out = "tests/test_a.py::test_x PASSED [ 50%]\ntests/test_a.py::test_y FAILED [100%]\nResults (6.46s):\n         1 failed\n      1191 passed\n        52 skipped\n         1 xfailed\n" + _DONE
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py -v 2>&1 | tail -30", out))
    assert (r.valid, r.passed, r.failed, r.skipped) == (True, 1191, 1, 53)  # not the two test lines the tail left
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py", "Results (0.21s):\n         3 failed\n" + _DONE))
    assert (r.valid, r.passed, r.failed) == (True, 0, 3)
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py -k nothing", "Results (0.21s):\n       158 deselected\n" + _DONE))
    assert not r.valid and "zero tests" in r.reason
    # a command that prints such a block itself is no evidence
    assert evidence.shaped("echo 'Results (0.21s):\n       5 passed'")
    (r,) = _shell_runs(("cd /testbed && python -m pytest tests/test_a.py; printf 'Results (0.2s):\\n   5 passed\\n'", "Results (0.2s):\n   5 passed\n" + _DONE))
    assert not r.valid


def test_the_output_of_a_run_the_terminal_left_running_is_read_from_the_calls_without_a_command_after_it():
    cmd = "cd /testbed && python -m pytest tests/test_slow.py"
    summary = "============ 3 failed, 40 passed in 95.10s ============" + _DONE
    r, *rest = _shell_runs((cmd, "collected 43 items\n" + _WAIT), (None, "tests/test_slow.py ....\n" + _WAIT), (None, summary))
    assert rest == [] and (r.step, r.valid, r.passed, r.failed) == (1, True, 40, 3)
    # the runner was interrupted: the summary is of the tests that happened to finish
    (r,) = _shell_runs((cmd, "collected 43 items\n" + _WAIT), (None, "!!!!!! KeyboardInterrupt !!!!!!\n============ 2 passed in 31.00s ============" + _DONE))
    assert not r.valid and "no test summary" in r.reason
    # another command sent in between: what comes later is not this run's output
    r, other = _shell_runs((cmd, "collected 43 items\n" + _WAIT), ("cd /testbed && python -m pytest tests/test_a.py", summary))
    assert not r.valid and other.valid
    # a command that finished: the next call's output is not its output
    (r,) = _shell_runs((cmd, "collected 43 items\n" + _DONE), (None, summary))
    assert not r.valid
