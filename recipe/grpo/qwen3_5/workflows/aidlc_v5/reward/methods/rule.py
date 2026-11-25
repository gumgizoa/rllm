"""rule/*: what the run did against the rules the documents state, whatever its artifacts claim.

The claims (``claim.py``) hold each artifact claim to the trajectory, so a violation reported honestly -- a test file
edited and listed as modified, a reproduction script left in the repository and listed as created -- passes them.
These look at what the run did:

    r_test_lines_kept       no existing line of a test file changed or removed: in the patch, or in the
                            trajectory and put back (01 Step 3, 03, 04, 05 Step 5, core "ADD ONLY, in test files",
                            "DO NOT MODIFY OR REMOVE: any existing line of a test file"); a test added to a test
                            module, or a new test module, keeps it (v5; aidlc_v4_eval's r_tests_untouched took
                            any changed test file)
    r_targeted_tests        every test run of stage 5 names its targets (05 Step 3: "Do NOT run the full
                            repository test suite"); ``-k`` selects too
    r_no_env_setup          nothing installed (01 Step 2, 05 Step 1, core "Do not spend effort on
                            environment setup")
    r_repro_not_in_stage4   the reproduction script not run in stage 4 (04 Step 2: "do not execute it in
                            this stage")
    r_artifacts_written_once  each artifact written once, never rewritten later (core "One write, full
                            content", "Never rewrite an earlier stage's artifact")
    r_repo_clean            no scratch, backup, duplicate or generated file added to the repository (05
                            Step 7); the reproduction script belongs outside it
"""

from __future__ import annotations

import re

from .. import read as EV
from .. import skeleton as A
from .. import trace as F
from ..read import DUPLICATE, claimed_paths
from . import method

_MEDIA = re.compile(r"\.(?:png|jpe?g|gif|bmp|pdf|svg|eps)$", re.I)

_ROOT_SCRATCH = re.compile(r"^[^/]+\.(?:py|sh|txt|md|log|json|out|diff|patch)$")


def _scratch(path: str, test_files) -> bool:
    """An added repository file that is no part of a fix: scratch-named, a backup or duplicate, build
    output, a generated image outside the tests, or a loose script or note at the repository root."""
    if _ROOT_SCRATCH.match(path) and path not in test_files:
        return True
    if EV.is_test_file(path, test_files) and not _MEDIA.search(path):
        return False
    return bool(F.SCRATCH_HINT_RE.search(path) or F.BACKUP_RE.search(path) or F.ARTIFACT_RE.search(path) or DUPLICATE.search(path) or _MEDIA.search(path) or _ROOT_SCRATCH.match(path))


@method("rule/r_test_lines_kept", materials=("EDIT", "PATCH", "TESTFILE"))
def r_test_lines_kept(m):
    """No existing test line changed or removed: the patch removes no line of a test file, and no trajectory edit
    changed one (``read.test_line_changes``: an edit put back by the end is still a change). Lines added to a test
    file, or a new test module, keep the rule."""
    removed = [p for p in (EV.removed_line_files(m.whole_patch) or []) if EV.is_test_file(p, m.tests)]
    return 0.0 if removed or m.test_line_changes else 1.0


@method("rule/r_targeted_tests", materials=("TEST", "TARGET", "DOC", "WRITE"))
def r_targeted_tests(m):
    """Stage 5's test runs name their targets: none runs the whole suite (``evidence.full_suite``)."""
    start5 = m.w.get(4) or m.read_step.get("05")
    if start5 is None:
        return None
    runs = m.obs.tests_in(after=start5, before=m.w.get(5))
    if not runs:
        return None
    return 0.0 if any(m.obs.whole_suite(r) for r in runs) else 1.0


@method("rule/r_no_env_setup", materials=("SHELLCLS",))
def r_no_env_setup(m):
    return 0.0 if any(EV.is_env_setup(raw) for raw in m.obs.shell_raw) else 1.0


@method("rule/r_repro_not_in_stage4", materials=("AP", "COLLECT", "PATH", "SCRIPT", "DOC", "WRITE"))
def r_repro_not_in_stage4(m):
    # (the path read with the skeleton's own field reader, as the milestone-1 rule did)
    repro = next((p for st in (4, 3) if m.parsed.get(st) for p in claimed_paths(A.field_value(m.parsed[st]["section_bodies"].get("Reproduction Script") or "", "Path"))), None)
    r4, w4 = m.read_step.get("04"), m.w.get(4)
    if not (repro and r4 is not None and w4 is not None):
        return None
    return 0.0 if m.obs.ran(repro, after=r4, before=w4) else 1.0


@method("rule/r_artifacts_written_once", materials=("WRITE",))
def r_artifacts_written_once(m):
    writes = {path: steps for path, steps in m.obs.writes.items() if path in A.ARTIFACT_PATHS}
    if not writes:
        return None
    return 0.0 if any(len(steps) > 1 for steps in writes.values()) else 1.0


@method("rule/r_repo_clean", materials=("PATCH", "TESTFILE"))
def r_repo_clean(m):
    if m.final is None:
        return None
    return 0.0 if any(_scratch(p, m.tests) for p in m.final[1]) else 1.0
