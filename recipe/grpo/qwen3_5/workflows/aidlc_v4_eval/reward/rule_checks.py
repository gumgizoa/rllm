"""Rule checks: did the run keep the workflow's rules, whatever its artifacts say?

The content checks hold each artifact claim to the trajectory, so a violation reported honestly -- a test
file edited and listed as modified, a reproduction script left in the repository and listed as created --
passes them. These checks look at what the run did, against the rules the documents state:

    r_tests_untouched       no existing test file changed: the patch, plus a test edited and put back
                            (01 Step 3, 04, 05 Step 5, core "DO NOT MODIFY: test files")
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

Each is 1 (kept) / 0 (broken) / None (nothing bears on it: no stage-5 test run, no reproduction script, an
unknown patch). ``aidlc/rules`` is their mean. Like the content checks, logged only.
"""

from __future__ import annotations

import re

from . import read as EV
from . import skeleton as A
from . import trace as F
from .read import DUPLICATE, Observed, claimed_paths

CHECKS = ["r_tests_untouched", "r_targeted_tests", "r_no_env_setup", "r_repro_not_in_stage4", "r_artifacts_written_once", "r_repo_clean"]

_MEDIA = re.compile(r"\.(?:png|jpe?g|gif|bmp|pdf|svg|eps)$", re.I)
_ROOT_SCRATCH = re.compile(r"^[^/]+\.(?:py|sh|txt|md|log|json|out|diff|patch)$")


def _scratch(path: str, test_files) -> bool:
    """An added repository file that is no part of a fix: scratch-named, a backup or duplicate, build
    output, a generated image outside the tests, or a loose script or note at the repository root."""
    if EV.is_test_file(path, test_files) and not _MEDIA.search(path):
        return False
    return bool(F.SCRATCH_HINT_RE.search(path) or F.BACKUP_RE.search(path) or F.ARTIFACT_RE.search(path) or DUPLICATE.search(path) or _MEDIA.search(path) or _ROOT_SCRATCH.match(path))


def rule_checks(run, obs: Observed, parsed: dict, read_step: dict, write_step: dict, patch: str | None, test_files=()) -> dict:
    """``read_step``: rule document ("01".."05") -> first read; ``write_step``: stage -> first artifact write."""
    c: dict[str, float | None] = dict.fromkeys(CHECKS)
    final = EV.patch_files(patch)

    # Existing test files changed: still changed in the patch, or edited and put back.
    changed_tests = [p for p in obs.edited if EV.is_test_file(p, test_files) and p not in obs.new_files]
    if final is not None:
        added = set(final[1])
        changed_tests += [p for p in final[0] if p not in added and EV.is_test_file(p, test_files)]
    c["r_tests_untouched"] = 0.0 if changed_tests else 1.0

    # Stage 5's test runs name their targets.
    start5 = write_step.get(4) or read_step.get("05")
    if start5 is not None:
        runs = obs.tests_in(after=start5, before=write_step.get(5))
        if runs:
            untargeted = [cmd for _, cmd, _ in runs if EV.test_targets(cmd) == []]
            c["r_targeted_tests"] = 0.0 if untargeted else 1.0

    c["r_no_env_setup"] = 0.0 if any(EV.is_env_setup(raw) for raw in obs.shell_raw) else 1.0

    repro = next((p for st in (4, 3) if parsed.get(st) for p in claimed_paths(A.field_value(parsed[st]["section_bodies"].get("Reproduction Script") or "", "Path"))), None)
    r4, w4 = read_step.get("04"), write_step.get(4)
    if repro and r4 is not None and w4 is not None:
        c["r_repro_not_in_stage4"] = 0.0 if obs.ran(repro, after=r4, before=w4) else 1.0

    writes = {path: steps for path, steps in obs.writes.items() if path in A.ARTIFACT_PATHS}
    if writes:
        c["r_artifacts_written_once"] = 0.0 if any(len(steps) > 1 for steps in writes.values()) else 1.0

    if final is not None:
        c["r_repo_clean"] = 0.0 if any(_scratch(p, test_files) for p in final[1]) else 1.0

    applicable = [v for v in c.values() if v is not None]
    return {"checks": c, "rules": sum(applicable) / len(applicable) if applicable else None}
