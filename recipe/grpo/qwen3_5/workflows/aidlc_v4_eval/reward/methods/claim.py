"""check/*: are the stage artifacts' claims borne out by the run that wrote them?

The form methods grade FORM: a field counts when it is filled in, and ``none`` is a filled-in value for the fields that
allow it. These grade the CLAIMS the fields make against what the trajectory shows the run observed and did. Three
families (``family``):

    evidence     a claim names something the run must have seen or done: the tests in the baseline,
                 the files modified, the commands run, the reproduction script's result
    temporal     an observation must precede the claim that reports it: the baseline run before the
                 stage-1 artifact, the reproduction and regression runs after the last edit and
                 before the stage-5 one
    consistency  the stages must agree with each other: plan steps tag requirements that exist, the
                 reproduction script keeps one path from plan to execution, the plan's targets are the
                 files the run changed

Each resolves to 1.0 supported, 0.5 partial (some of the named files or tests), 0.0 contradicted, or None (the stage
was not written, the field is empty, or nothing observable bears on the claim -- left out of every mean). Verdicts
come only from what the trajectory shows: a claim nothing bears on is not applicable, never contradicted, so a run
cannot lose for a measurement gap (a quiet ``pytest -q`` names no tests; a ``git apply`` changes files it does not
name). A stage that was never written makes no claims, so a missing artifact costs nothing here -- form already
scores it 0.

``none`` is a claim too. ``Passing: none / Failing: none`` says the run looked for tests and found nothing to run,
``Regressions: none`` says the suite ran clean after the change, ``Deviations: none`` says the plan's targets are the
files changed. Each is held to the evidence that would make it true.

Not checked: whether the requirements describe the issue, whether a plan's ``Change`` is the right change (the
judge's). Deliberately not checked: stage 4's ``Executed: no`` -- the skeleton prescribes that value.

``timed_by_edits``: a claim placed against the first or last source edit, left out when the patch changed a source
file the trajectory never shows being edited (``Measures.timing_unknown``).
"""

from __future__ import annotations

import re

from .. import read as EV
from .. import skeleton as A
from .. import trace as F
from ..measures import test_names
from ..read import (
    CONTRADICTED,
    DUPLICATE,
    NO_TESTS,
    PARTIAL,
    R_LINE,
    SUPPORTED,
    TEST_ID,
    _field,
    _section_none,
    both_ways,
    claimed_paths,
    command_core,
    failures,
    is_none,
    membership,
    names_test_ids,
    norm_path,
    passes,
    r_ids,
    same_file,
    test_command_tokens,
)
from . import method

E, T, C = "evidence", "temporal", "consistency"

_STEP_REF = re.compile(r"\bStep\s+(\d+)", re.I)

_SYMBOL = re.compile(r"`([\w.]+)`|\b([A-Za-z_]\w{3,})\s*\(")
_PATCH_DEF = re.compile(r"^(?:[-+ ]\s*|@@[^@]*@@\s*)(?:async\s+)?(?:def|class)\s+(\w+)", re.M)  # changed, context and hunk-header lines

_CODE_NAME = re.compile(r"(?<![\w.])((?:_*[a-z]+(?:_[a-z0-9]+)+|[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+)\w*)")  # snake_case or CamelCase, code-like


def _symbols(text: str) -> set[str]:
    """Identifiers a plan step names: in backticks, or called (`to_native_string(`)."""
    return {a or b for a, b in _SYMBOL.findall(text or "")} - {"none"}


def _patch_symbols(patch: str | None) -> dict[str, set[str]]:
    """Repository path -> the names a deviation could call that file's change by: the defs and classes its hunks touch
    (changed, context and header lines) and the code-like names on its changed lines (`_encode_params` when the
    def itself lies outside the hunk: step24 000294)."""
    out: dict[str, set[str]] = {}
    for section in re.split(r"(?m)^diff --git ", patch or "")[1:]:
        m = re.match(r"a/(\S+) b/(\S+)", section)
        if not m:
            continue
        changed = "\n".join(ln[1:] for ln in section.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---")))
        out[norm_path(m.group(2))] = set(_PATCH_DEF.findall(section)) | {n for n in _CODE_NAME.findall(changed) if len(n) >= 6}
    return out


def _names_in(text: str, path: str, symbols: set[str], shared: set[str] = frozenset()) -> bool:
    """``text`` names the file (its name or stem), one of ``symbols``, or -- qualified, `IdentityOperator.__mul__` --
    one of ``shared`` (a symbol the patch also touches in a planned file, which unqualified would name that file's
    change: step24 000271 `set_gid()` vs 000471 `IdentityOperator.__mul__`)."""
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if name in text or re.search(rf"(?<![\w.]){re.escape(stem)}(?![\w])", text):
        return True
    if any(re.search(rf"(?<!\w){re.escape(sy)}(?!\w)", text) for sy in symbols if len(sy) >= 4):
        return True
    return any(re.search(rf"\w+\.{re.escape(sy)}(?!\w)", text) for sy in shared if len(sy) >= 4)


def _named_in(field: str | None, test: str) -> bool:
    return bool(field) and re.search(rf"(?<!\w){re.escape(test)}(?!\w)", field) is not None


# -- stage 1: scope, commands, baseline ---------------------------------------------------------------


@method("check/e1_baseline_tests", materials=("AP", "COLLECT", "TEST", "EDIT", "TARGET"), family=E, timed_by_edits=True)
def e1_baseline_tests(m):
    """The tests 01's Baseline names appear in the baseline run's output."""
    if m.p1 is None or not m.evidence_runs:
        return None
    names = sorted({*TEST_ID.findall(m.passing1 or ""), *TEST_ID.findall(m.failing1 or "")})
    if names and names_test_ids(m.evidence_out):
        return membership(names, [n in m.evidence_out for n in names])
    return None


@method("check/e1_baseline_failing", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT", "TARGET"), family=E, timed_by_edits=True)
def e1_baseline_failing(m):
    """``Failing: none`` when the baseline failed nothing; a Failing list when it failed something it names."""
    if m.p1 is None or not m.evidence_runs:
        return None
    fails = failures(m.evidence_out)
    if is_none(m.failing1):
        return CONTRADICTED if fails else SUPPORTED
    if m.failing1:
        # (test names, not the file's: `tests/test_mod.py::test_old` names test_old only)
        return SUPPORTED if fails or any(n in m.evidence_out for n in test_names(m.failing1)) else CONTRADICTED
    return None


@method("check/e1_baseline_none", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT"), family=E, timed_by_edits=True)
def e1_baseline_none(m):
    """``Passing: none / Failing: none``: the baseline ran no test, or found nothing to run (`collected 0 items`)."""
    if m.p1 is None or not m.both_none:
        return None
    obs, w1 = m.obs, m.w[1]
    if not m.evidence_runs:
        if any(NO_TESTS.search(o) for _, _, o in obs.attempts_in(before=w1 if w1 is not None else obs.first_edit)):
            return SUPPORTED
        return None
    out = m.evidence_out
    return CONTRADICTED if (failures(out) or passes(out) or names_test_ids(out)) else SUPPORTED


@method("check/e1_baseline_passing", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT"), family=E, timed_by_edits=True)
def e1_baseline_passing(m):
    """Passing names tests the baseline run passed: none it reports failed (judged on the tests whose state the output
    shows -- a verbose run's PASSED / ... ok, any run's FAILED lines)."""
    passing = m.passing1
    if m.p1 is None or not m.evidence_runs or not passing or is_none(passing):
        return None
    named = test_names(passing)
    states: dict[str, bool] = {}
    for _, _, o in reversed(m.evidence_runs):
        # the latest run that says how each test went (an earlier attempt may not have loaded it:
        # `test_has_key (unittest.loader._FailedTest) ... ERROR`, step24 000193)
        here = {t: st for t in named if t not in states and (st := EV.test_state(o, t)) is not None}
        # a run that names only its failures (dots, -q): the rest of the Passing tests passed in it when
        # its summary counts at least that many passes (step24 000167, `.....FF.`)
        rest = [t for t in named if t not in states and t not in here]
        if False in here.values() and rest and (EV.passed_count(o) or 0) >= len(rest):
            here |= dict.fromkeys(rest, True)
        states |= here
    return membership(list(states), list(states.values())) if states else None


@method("check/e1_scope_viewed", materials=("AP", "COLLECT", "PATH", "SEEN", "WRITE"), family=E)
def e1_scope_viewed(m):
    """The files 01's Affected Scope names were opened before 01 was written."""
    if m.p1 is None:
        return None
    scope = claimed_paths(_field(m.p1, "Affected Scope", "Files"))
    return membership(scope, [m.obs.seen(p, before=m.w[1]) for p in scope])


@method("check/e1_test_command_run", materials=("AP", "COLLECT", "CMDMATCH", "TARGET"), family=E)
def e1_test_command_run(m):
    """The recorded test command ran tests (one that only failed to start -- `No module named pytest` in a Django
    checkout -- establishes nothing: step24 004741 000241). When it ran is the baseline claims' concern (t1_*)."""
    if m.p1 is None:
        return None
    tok = test_command_tokens(_field(m.p1, "Build & Test Commands", "Test"))
    return SUPPORTED if m.obs.command_run(tok, started=True) else (CONTRADICTED if tok else None)


@method("check/e1_build_command_run", materials=("AP", "COLLECT", "NONE", "CMDMATCH"), family=E)
def e1_build_command_run(m):
    """The recorded build command was run."""
    if m.p1 is None:
        return None
    build = _field(m.p1, "Build & Test Commands", "Build")
    if build and not is_none(build) and command_core(build):
        return SUPPORTED if m.obs.command_runs(build) else CONTRADICTED
    return None


@method("check/e1_test_path_seen", materials=("AP", "COLLECT", "PATH", "SEEN"), family=E)
def e1_test_path_seen(m):
    """The test files 01's Existing Tests names were opened or named in a command."""
    if m.p1 is None:
        return None
    tpaths = claimed_paths(_field(m.p1, "Existing Tests", "Path"))
    return membership(tpaths, [m.obs.seen(p) or m.obs.mentioned_in_shell(p) for p in tpaths])


@method("check/t1_baseline_before_write", materials=("AP", "COLLECT", "NONE", "TEST", "WRITE"), family=T)
def t1_baseline_before_write(m):
    """A baseline is observed by running the tests before writing it down; `none / none` may instead rest on an
    attempt that found nothing to run."""
    if m.p1 is None:
        return None
    obs, w1 = m.obs, m.w[1]
    looked = obs.tests_in(before=w1) or (m.both_none and any(NO_TESTS.search(o) for _, _, o in obs.attempts_in(before=w1)))
    return SUPPORTED if looked else CONTRADICTED


@method("check/t1_baseline_before_edit", materials=("TEST", "EDIT"), family=T, timed_by_edits=True)
def t1_baseline_before_edit(m):
    """Tests ran before the first source edit."""
    if m.p1 is None or m.obs.first_edit is None:
        return None
    return SUPPORTED if m.baseline_runs else CONTRADICTED


@method("check/t1_no_edit_before_write", materials=("EDIT", "WRITE"), family=T, timed_by_edits=True)
def t1_no_edit_before_write(m):
    """No source edit before 01 was written."""
    if m.p1 is None or m.obs.first_edit is None or m.w[1] is None:
        return None
    return SUPPORTED if m.obs.first_edit > m.w[1] else CONTRADICTED


# -- stage 2 <-> 3: requirements and the plan ---------------------------------------------------------


@method("check/c23_tags_exist", materials=("AP", "COLLECT"), family=C)
def c23_tags_exist(m):
    """The requirement tags of the plan's steps are requirements 02 states."""
    if m.p3 is None or not (m.tags and m.r_ids):
        return None
    return membership(m.tags, [t in m.r_ids for t in m.tags])


@method("check/c23_requirements_covered", materials=("AP", "COLLECT", "NONE"), family=C)
def c23_requirements_covered(m):
    """Every requirement is tagged by a step or listed in Requirement Coverage. A requirement line whose value says
    none (``R3: none stated``) is no requirement; one that merely starts with the word (``R3: None input ->
    TypeError``) is. A plan whose steps and coverage cannot be read at all (form broken, scored under F) says nothing."""
    p3 = m.p3
    if p3 is None or not m.r_ids:
        return None
    values = [(x.group(1), x.group(2)) for x in R_LINE.finditer(m.p2["body"])]
    real = [r for r in m.r_ids if not any(rid == r and is_none(v) for rid, v in values)]
    covered = set(m.tags) | set(p3.get("coverage_ids", []))
    if p3["steps"] or p3.get("coverage_ids"):
        return membership(real, [r in covered for r in real])
    return None


@method("check/c23_exercises_exist", materials=("AP", "COLLECT"), family=C)
def c23_exercises_exist(m):
    """The requirements the reproduction script exercises are requirements 02 states."""
    if m.p3 is None or not m.r_ids:
        return None
    exercises = r_ids(_field(m.p3, "Reproduction Script", "Exercises"))
    return membership(exercises, [r in m.r_ids for r in exercises])


@method("check/c23_coverage_refs", materials=("AP", "COLLECT"), family=C)
def c23_coverage_refs(m):
    """Requirement Coverage names requirements and steps that exist."""
    if m.p3 is None or not m.r_ids:
        return None
    coverage = m.p3["section_bodies"].get("Requirement Coverage")
    if not coverage:
        return None
    refs = [(x.group(1), _STEP_REF.findall(x.group(2))) for x in A.COVERAGE_LINE.finditer(coverage)]
    claims = [r for r, _ in refs] + [f"Step {s}" for _, steps in refs for s in steps]
    found = [r in m.r_ids for r, _ in refs] + [int(s) in m.step_nums for _, steps in refs for s in steps]
    return membership(claims, found)


# -- stage 4: changed files, the reproduction script ----------------------------------------------------


@method("check/e4_modified", materials=("AP", "COLLECT", "PATH", "PATCH"), family=E)
def e4_modified(m):
    """The files 04 says it modified were changed."""
    if m.p4 is None or not m.mod:
        return None
    found = [m.changed(x) for x in m.mod]
    return None if (m.edits_unknown and not all(found)) else membership(m.mod, found)


@method("check/e4_created", materials=("AP", "COLLECT", "PATH", "EDIT", "PATCH"), family=E)
def e4_created(m):
    """The files 04 says it created were written."""
    if m.p4 is None or not m.cre:
        return None
    return membership(m.cre, [m.obs.written(k) is not None or m.changed(k) for k in m.cre])


@method("check/e4_undisclosed", materials=("AP", "COLLECT", "PATH", "PATCH"), family=E)
def e4_undisclosed(m):
    """Every file changed by stage 4 is named in 04 (a file first changed after 04 was written is stage 5's to report:
    step24 004741 000236)."""
    p4, obs, w4 = m.p4, m.obs, m.w[4]
    edited = m.edited4
    if p4 is None or not edited or m.edits_unknown:
        return None
    stage4 = [p for p in edited if not ((n := obs.written(p)) is not None and w4 is not None and n > w4)]
    named = [any(same_file(p, q) for q in claimed_paths(p4["body"])) or p.rsplit("/", 1)[-1] in p4["body"] for p in stage4]
    return membership(stage4, named)


@method("check/e4_tests_untouched", materials=("AP", "COLLECT", "NONE", "PATCH", "EDIT", "TESTFILE"), family=E)
def e4_tests_untouched(m):
    """``Test files modified: none``: the patch has no test file still changed, and the trajectory none changed and
    put back."""
    if m.p4 is None or not is_none(_field(m.p4, "Checks", "Test files modified")):
        return None
    obs = m.obs
    touched = [p for p in [*m.edited4, *obs.edited] if EV.is_test_file(p, m.tests) and p not in m.new_now and p not in obs.new_files]
    return CONTRADICTED if touched else SUPPORTED


@method("check/e4_duplicates_none", materials=("AP", "COLLECT", "NONE", "PATCH"), family=E)
def e4_duplicates_none(m):
    """``Duplicate files created: none``: no duplicate or backup file added."""
    if m.p4 is None or not is_none(_field(m.p4, "Checks", "Duplicate files created")):
        return None
    dupes = [p for p in m.changed_now if p in m.new_now and (DUPLICATE.search(p) or F.BACKUP_RE.search(p))]
    return CONTRADICTED if dupes else SUPPORTED


@method("check/t4_repro_written_before_write", materials=("AP", "COLLECT", "PATH", "EDIT", "WRITE"), family=T)
def t4_repro_written_before_write(m):
    """The reproduction script was written before the 04 that is scored, its last write (an early 04 written again is
    B4a's: step24 000440)."""
    if m.p4 is None or not m.repro:
        return None
    wrote, w4_last = m.obs.written(m.repro), (m.obs.writes.get(A.artifact_path(4)) or [m.w[4]])[-1]
    return SUPPORTED if wrote is not None and (w4_last is None or wrote <= w4_last) else CONTRADICTED


@method("check/c34_repro_path", materials=("AP", "COLLECT", "PATH"), family=C)
def c34_repro_path(m):
    """03 and 04 record one reproduction script path."""
    if m.p3 is None or m.p4 is None:
        return None
    p3_path, p4_path = (claimed_paths(_field(p, "Reproduction Script", "Path")) for p in (m.p3, m.p4))
    if not (p3_path and p4_path):
        return None
    return SUPPORTED if same_file(p3_path[0], p4_path[0]) else CONTRADICTED


@method("check/c34_targets_changed", materials=("AP", "COLLECT", "PATH"), family=C)
def c34_targets_changed(m):
    """The plan's targets are among the files 04 says it changed."""
    if m.p3 is None or m.p4 is None:
        return None
    targets, changed_claims = m.plan_targets, m.p4["claims"]["modified"] + m.p4["claims"]["created"]
    if not (targets and changed_claims):
        return None
    return membership(targets, [any(same_file(t, q) for q in changed_claims) for t in targets])


@method("check/c34_plan_execution_steps", materials=("AP", "COLLECT"), family=C)
def c34_plan_execution_steps(m):
    """Plan Execution lists steps the plan has (all of them, or partial)."""
    if m.p3 is None or m.p4 is None:
        return None
    execution = m.p4["section_bodies"].get("Plan Execution")
    if not (execution and m.step_nums):
        return None
    listed = sorted({int(s) for s in _STEP_REF.findall(execution)})
    if not listed:
        return None
    value = membership(listed, [s in m.step_nums for s in listed])
    return PARTIAL if value == SUPPORTED and set(m.step_nums) - set(listed) else value


@method("check/c34_deviations_none", materials=("AP", "COLLECT", "NONE", "PATH"), family=C)
def c34_deviations_none(m):
    """``Deviations from Plan: none``: the plan's targets are the files changed (the reproduction script left out on
    both sides)."""
    if m.p3 is None or m.p4 is None:
        return None
    if not (_section_none(m.p4, "Deviations from Plan") and m.plan_targets and (m.mod or m.cre)):
        return None
    return SUPPORTED if both_ways(m.not_repro(m.plan_targets), m.not_repro(m.mod + m.cre)) == SUPPORTED else CONTRADICTED


@method("check/c34_deviations_recorded", materials=("AP", "COLLECT", "NONE", "PATH", "PATCH"), family=C)
def c34_deviations_recorded(m):
    """Deviations recorded: every changed file the plan does not name, and every planned target not changed, is named
    there (B4b: a contradiction with an earlier stage is recorded as a deviation). What the entries say is the
    judge's (G8a). Replaced the judge question 2026-10-27."""
    p3, p4 = m.p3, m.p4
    if p3 is None or p4 is None:
        return None
    dev = p4["section_bodies"].get("Deviations from Plan")
    targets = m.not_repro(m.plan_targets)
    if not (dev and _section_none(p4, "Deviations from Plan") is False and m.plan_targets and (m.mod or m.cre)):
        return None
    changed_files = m.not_repro(m.mod + m.cre)
    unplanned = [q for q in changed_files if not any(same_file(q, t) for t in targets)]
    unexecuted = [t for t in targets if not any(same_file(q, t) for q in changed_files)]
    if not (unplanned or unexecuted):
        return None
    # named by the file, or by a symbol: a def / class the patch touches in that file, or one the plan step for
    # that target names (step24 000294 wrote "applied in `_encode_params` instead of `to_native_string`")
    touched = _patch_symbols(m.whole_patch)
    # a symbol the patch also touches in a planned file names the planned change, not the unplanned file (step24
    # 000271: `set_gid()` added in the planned offsetbox.py and in image.py)
    in_planned = {sy for t in targets for sy in touched.get(norm_path(t), set())}
    step_syms: dict[str, set[str]] = {}
    for s in p3["steps"]:
        for t in claimed_paths(s["fields"].get("Target")):
            step_syms.setdefault(t, set()).update(_symbols(" ".join(str(s["fields"].get(k) or "") for k in ("Target", "Change", "Contract"))))
    found = [_names_in(dev, q, touched.get(norm_path(q), set()) - in_planned, touched.get(norm_path(q), set()) & in_planned) for q in unplanned]
    found += [_names_in(dev, t, step_syms.get(t, set())) for t in unexecuted]
    return membership(unplanned + unexecuted, found)


@method("check/c14_scope_changed", materials=("AP", "COLLECT", "PATH"), family=C)
def c14_scope_changed(m):
    """Some file 04 modified is in 01's Affected Scope."""
    if m.p1 is None or m.p4 is None:
        return None
    scope = claimed_paths(_field(m.p1, "Affected Scope", "Files"))
    if not (scope and m.mod):
        return None
    return SUPPORTED if any(same_file(s, x) for s in scope for x in m.mod) else CONTRADICTED


# -- stage 5: what was run after the change ---------------------------------------------------------------


def _repro_runs(m) -> list:
    """The reproduction script's runs the report rests on: after the last change to the source, before 05."""
    return m.obs.ran(m.repro, after=m.obs.last_edit if m.obs.last_edit is not None else m.w[4], before=m.w[5])


@method("check/t5_repro_run_after_last_edit", materials=("AP", "COLLECT", "PATH", "SCRIPT", "EDIT", "WRITE"), family=T, timed_by_edits=True)
def t5_repro_run_after_last_edit(m):
    """The reproduction script ran after the last source edit, before 05; no stage recorded one (``Path: N/A``):
    stage 5 cannot have run one."""
    if m.p5 is None:
        return None
    if m.repro is None:
        return CONTRADICTED if (m.p3 is not None or m.p4 is not None) else None
    return SUPPORTED if _repro_runs(m) else CONTRADICTED


@method("check/e5_repro_result", materials=("AP", "COLLECT", "PATH", "SCRIPT", "EXIT", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_repro_result(m):
    """05's reproduction Result (pass / fail) matches the exit code of that run."""
    if m.p5 is None or not m.repro:
        return None
    runs = _repro_runs(m)
    if not runs:
        return None
    result = (_field(m.p5, "Reproduction Script", "Result") or "").lower()
    code = EV.exit_code(runs[-1][1], runs[-1][2])
    if code is None or not result:
        return None
    failed = code != 0
    if result.startswith("pass"):
        return CONTRADICTED if failed else SUPPORTED
    if result.startswith("fail"):
        return SUPPORTED if failed else CONTRADICTED
    return None


@method("check/e5_build_result", materials=("AP", "COLLECT", "NONE", "CMDMATCH", "EXIT", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_build_result(m):
    """05's build Result matches the build on the final code; failing that, stage 5's own build (05 Step 1), which a
    fix made later in the stage re-verifies through the tests, not a rebuild (05 Step 5)."""
    if m.p5 is None:
        return None
    build_cmd, build_result = _field(m.p5, "Build", "Command"), (_field(m.p5, "Build", "Result") or "").lower()
    if not (build_cmd and not is_none(build_cmd) and command_core(build_cmd)):
        return None
    obs = m.obs
    builds = obs.command_runs(build_cmd, after=obs.last_edit) or obs.command_runs(build_cmd, after=m.w[4], before=m.w[5])
    if not builds:
        return CONTRADICTED
    if (code := EV.exit_code(builds[-1][1], builds[-1][2])) is not None and build_result:
        ok = build_result.startswith(("success", "pass", "ok"))
        return SUPPORTED if ok == (code == 0) else CONTRADICTED
    return None


@method("check/t5_regression_after_last_edit", materials=("TEST", "EDIT", "WRITE"), family=T, timed_by_edits=True)
def t5_regression_after_last_edit(m):
    """Tests ran after the last source edit, before 05."""
    if m.p5 is None or not m.obs.source_edits:
        return None
    return SUPPORTED if m.post else CONTRADICTED


@method("check/e5_command_run", materials=("AP", "COLLECT", "CMDMATCH", "TARGET", "EDIT"), family=E, timed_by_edits=True)
def e5_command_run(m):
    """05's test Command ran after the last source edit."""
    if m.p5 is None:
        return None
    tokens = test_command_tokens(_field(m.p5, "Existing Tests vs Baseline", "Command"))
    if not tokens:
        return None
    return SUPPORTED if m.obs.command_run(tokens, after=m.obs.last_edit) else CONTRADICTED


@method("check/e5_regressions", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_regressions(m):
    """``Regressions: none`` (or Verdict unchanged) when the described run fails no test the baseline did not. A
    failure the baseline already had (01 Failing, or failing in the baseline run) is no regression: named failures
    compare by name, a quiet run (a count only) by count against the baseline's."""
    if m.p5 is None:
        return None
    regressions = _field(m.p5, "Existing Tests vs Baseline", "Regressions")
    verdict = (_field(m.p5, "Existing Tests vs Baseline", "Verdict") or "").lower()
    if m.regressed is not None and (is_none(regressions) or verdict.startswith("unchanged")):
        return CONTRADICTED if m.regressed else SUPPORTED
    return None


@method("check/e5_outstanding_none", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_outstanding_none(m):
    """``Outstanding Failures: none`` when the described run fails no test the baseline did not."""
    if m.p5 is None:
        return None
    if m.regressed is not None and _section_none(m.p5, "Outstanding Failures"):
        return CONTRADICTED if m.regressed else SUPPORTED
    return None


@method("check/e5_regressions_listed", materials=("AP", "COLLECT", "TEST", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_regressions_listed(m):
    """A test that passed at the baseline and fails in the described stage-5 run is a regression: 05 lists it under
    Regressions, not Pre-existing failures (05 Step 3 table). Replaced the judge question 2026-10-27."""
    if m.p5 is None or not m.described or m.p1 is None:
        return None
    regressions = _field(m.p5, "Existing Tests vs Baseline", "Regressions")
    pre = _field(m.p5, "Existing Tests vs Baseline", "Pre-existing failures")
    base_out = m.evidence_out
    failing_now = EV.failed_tests(m.described[-1][2])
    passed_then = set(test_names(m.passing1)) | {t for t in failing_now if EV.test_state(base_out, t) is True}
    regressed_names = [t for t in failing_now if t in passed_then and EV.test_state(base_out, t) is not False]
    if not regressed_names:
        return None
    return membership(regressed_names, [_named_in(regressions, t) and not _named_in(pre, t) for t in regressed_names])


@method("check/e5_preexisting_listed", materials=("AP", "COLLECT", "NONE", "TEST", "EDIT", "WRITE"), family=E, timed_by_edits=True)
def e5_preexisting_listed(m):
    """Every baseline failure the last run still fails is recorded as pre-existing (05 Step 3 table: "Record the
    reasoning that identifies it as pre-existing"; whether the reasoning holds is the judge's)."""
    failing1 = m.failing1
    if m.p5 is None or not m.post or not failing1 or is_none(failing1):
        return None
    pre = _field(m.p5, "Existing Tests vs Baseline", "Pre-existing failures")
    still = [t for t in test_names(failing1) if EV.test_state(m.described[-1][2], t) is False]
    if not still:
        return None
    return membership(still, [bool(pre) and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", pre) is not None for t in still])


@method("check/c15_preexisting_subset", materials=("AP", "COLLECT", "NONE", "TARGET"), family=C)
def c15_preexisting_subset(m):
    """05's Pre-existing failures are among 01's Failing."""
    if m.p5 is None or m.p1 is None:
        return None
    pre, failing1 = _field(m.p5, "Existing Tests vs Baseline", "Pre-existing failures"), m.failing1
    if not pre:
        return None
    if is_none(pre):
        named = TEST_ID.findall(failing1 or "")
        return SUPPORTED if (failing1 is None or is_none(failing1)) else (CONTRADICTED if named else None)
    base_ids, pre_ids = TEST_ID.findall(failing1 or ""), TEST_ID.findall(pre)
    if not pre_ids:
        return None
    return CONTRADICTED if is_none(failing1) or not failing1 else membership(pre_ids, [t in base_ids for t in pre_ids])


@method("check/c25_unmet_exist", materials=("AP", "COLLECT"), family=C)
def c25_unmet_exist(m):
    """05's Unmet requirements are requirements 02 states."""
    if m.p5 is None:
        return None
    unmet = r_ids(_field(m.p5, "Reproduction Script", "Unmet requirements"))
    if not (unmet and m.r_ids):
        return None
    return membership(unmet, [r in m.r_ids for r in unmet])


@method("check/c45_final_files", materials=("AP", "COLLECT", "PATH"), family=C)
def c45_final_files(m):
    """05's Files in the change are files 04 says it changed."""
    if m.p5 is None:
        return None
    final = claimed_paths(_field(m.p5, "Final Change", "Files in the change"))
    if not (final and m.p4 is not None and (m.p4["claims"]["modified"] or m.p4["claims"]["created"])):
        return None
    stage4 = m.p4["claims"]["modified"] + m.p4["claims"]["created"]
    return membership(final, [any(same_file(f, q) for q in stage4) for f in final])


def _final_and_actual(m) -> tuple[list[str], list[str]]:
    """05's Files in the change, and the files changed that Unintended files does not disclose."""
    final = claimed_paths(_field(m.p5, "Final Change", "Files in the change"))
    disclosed = claimed_paths(_field(m.p5, "Final Change", "Unintended files in the repository"))
    return final, [p for p in m.changed_now if not any(same_file(p, u) for u in disclosed)]


@method("check/e5_final_files_diff", materials=("AP", "COLLECT", "PATH", "PATCH"), family=E)
def e5_final_files_diff(m):
    """05's Files in the change are the files changed, both ways (the disclosed unintended files left out)."""
    if m.p5 is None or m.edits_unknown:
        return None
    final, actual = _final_and_actual(m)
    if _field(m.p5, "Final Change", "Files in the change") is not None and (final or actual):
        return both_ways(final, actual)
    return None


@method("check/e5_unintended_none", materials=("AP", "COLLECT", "NONE", "PATH", "PATCH"), family=E)
def e5_unintended_none(m):
    """``Unintended files in the repository: none``: every file added is in Files in the change."""
    if m.p5 is None or m.edits_unknown or not is_none(_field(m.p5, "Final Change", "Unintended files in the repository")):
        return None
    final, _ = _final_and_actual(m)
    stray = [p for p in m.changed_now if p in m.new_now and not any(same_file(p, f) for f in final)]
    return CONTRADICTED if stray else SUPPORTED


@method("check/e5_test_files_none", materials=("AP", "COLLECT", "NONE", "PATCH", "TESTFILE"), family=E)
def e5_test_files_none(m):
    """``Test files in the change: none``: no existing test file is changed."""
    if m.p5 is None or m.edits_unknown or not is_none(_field(m.p5, "Final Change", "Test files in the change")):
        return None
    return CONTRADICTED if any(EV.is_test_file(p, m.tests) and p not in m.new_now for p in m.changed_now) else SUPPORTED
