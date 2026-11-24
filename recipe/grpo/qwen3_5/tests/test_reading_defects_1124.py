"""Three misreadings found when the test-behaviour tally of six runs was redone through this reading (2026-11-24).

pytest recipe/grpo/qwen3_5/tests/test_reading_defects_1124.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.rollout_metrics import test_evidence  # noqa: E402
from recipe.grpo.qwen3_5.tests.test_rollout_metrics import PASSED, PATCH, PYTEST, SRC, _sh, _traced  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.results import selects  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.openhands import rejected  # noqa: E402

test_evidence.__test__ = False  # a metric, not a test

NOT_FOUND = "Tool 'str_replace' not found. Available: ['terminal', 'file_editor', 'task_tracker', 'finish']"
MISSING = ("str_replace", {"path": "/testbed/pkg/mod.py", "old_str": "a", "new_str": "b"}, NOT_FOUND)


def test_a_call_to_a_tool_the_harness_does_not_have_is_refused():
    assert rejected(NOT_FOUND)
    assert not rejected("3 passed\nTool 'x' not found")  # the same words later in an output are a command's own


def test_an_edit_sent_to_a_missing_tool_is_no_source_change():
    # the test ran before the only edit that happened: nothing ran after the change
    m = test_evidence(_traced([MISSING, PYTEST, SRC]))
    assert m["rollout/test_after_last_edit"] == 0.0
    # and a refused edit after the last run does not hide the run
    m = test_evidence(_traced([SRC, PYTEST, MISSING]))
    assert m["rollout/test_after_last_edit"] == 1.0 and m["rollout/test_valid_after_last_edit"] == 1.0


def test_a_label_from_the_first_directory_names_one_file():
    f = "tests/aggregation/tests.py"
    for target in ("tests.aggregation.tests", "tests.aggregation.tests.AggregateTestCase.test_count", "tests.aggregation", "tests", "aggregation.tests", "aggregation"):
        assert selects(target, f), target
    for target in ("tests.annotations.tests", "tests.annotations.tests.NonAggregateAnnotationTestCase", "tests.annotations", "annotations.tests"):
        assert not selects(target, f), target


def test_a_file_under_an_unresolved_shell_variable_is_no_repository_test():
    m = test_evidence(
        _traced(
            [
                _sh("python $SPEC_PATH/verify/test_fix.py", "all checks passed"),  # the run's own script: no runner run
                _sh("pytest $SPEC_PATH/verify/test_fix.py -q", PASSED),  # a runner run, but of a file no one can place
                PYTEST,
            ],
            patch=None,
        )
    )
    assert m == {"rollout/test_runs": 2.0, "rollout/test_runs_valid": 1.0}
