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
