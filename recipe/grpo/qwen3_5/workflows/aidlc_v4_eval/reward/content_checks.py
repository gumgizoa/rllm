"""Content checks: are the stage artifacts' claims borne out by the run that wrote them?

The rubric's bands grade FORM: a field counts when it is filled in, and ``none`` is a filled-in
value for the fields that allow it. These checks grade the CLAIMS the fields make against what
the trajectory shows the run observed and did. Three families:

    evidence     a claim names something the run must have seen or done: the tests in the baseline,
                 the files modified, the commands run, the reproduction script's result
    temporal     an observation must precede the claim that reports it: the baseline run before the
                 stage-1 artifact, the reproduction and regression runs after the last edit and
                 before the stage-5 one
    consistency  the stages must agree with each other: plan steps tag requirements that exist, the
                 reproduction script keeps one path from plan to execution, the plan's targets are the
                 files the run changed

Each check resolves to one of

    1.0   supported      the claim matches the evidence
    0.5   partial        part of it matches (some of the named files, some of the named tests)
    0.0   contradicted   the evidence says otherwise
    None  not applicable the stage was not written, the field is empty, or nothing observable bears
                         on the claim -- the check is left out of every mean

Verdicts come only from what the trajectory shows. A claim nothing bears on is not applicable, never
contradicted, so a run cannot lose for a measurement gap (a quiet ``pytest -q`` names no tests; a
``git apply`` changes files it does not name). A stage that was never written makes no claims, so a
missing artifact costs nothing here -- the band already scores it 0.

``none`` is a claim too. ``Passing: none / Failing: none`` says the run looked for tests and found
nothing to run, ``Regressions: none`` says the suite ran clean after the change, ``Deviations: none``
says the plan's targets are the files changed. Each is held to the evidence that would make it true.

Not checked: whether the requirements describe the issue, whether a plan's ``Change`` is the right
change. No rule can tell. These checks only make fabrication and filler cost what honest reporting
earns.

Deliberately not checked: stage 4's ``Executed: no``. The skeleton prescribes that value, so a run
that did run its script in stage 4 writes a false ``no`` by instruction, not by choice.

The trajectory index, the report readers and the verdict reductions are ``reward/_claims.py``,
shared with the other workflows' content checks; this file holds what is AI-DLC's: the stage
skeleton's fields and the claims they make.
"""

from __future__ import annotations

import re
from statistics import mean

from ._claims import (
    CONTRADICTED,
    PARTIAL,
    SUPPORTED,
    Observed,
    claimed_paths,
    norm_path,
    same_file,
)
from ._claims import (
    DUPLICATE as _DUPLICATE,
)
from ._claims import (
    NO_TESTS as _NO_TESTS,
)
from ._claims import (
    TEST_ID as _TEST_ID,
)
from ._claims import (
    both_ways as _both_ways,
)
from ._claims import (
    command_core as _command_core,
)
from ._claims import (
    failures as _failures,
)
from ._claims import (
    is_none as _none,
)
from ._claims import (
    last_exit as _last_exit,
)
from ._claims import (
    membership as _membership,
)
from ._claims import (
    names_test_ids as _names_test_ids,
)
from ._claims import observe as _observe
from ._claims import (
    passes as _passes,
)
from ._claims import (
    r_ids as _ids,
)
from ._claims import (
    section_none as _body_none,
)
from ._claims import (
    test_command_tokens as _command_tokens,
)
from .rubric import artifacts as A
from .rubric import facts as F
from .rubric.model import Run

FAMILIES = {
    "evidence": [
        "e1_baseline_tests",
        "e1_baseline_failing",
        "e1_baseline_none",
        "e1_scope_viewed",
        "e1_test_command_run",
        "e1_build_command_run",
        "e1_test_path_seen",
        "e4_modified",
        "e4_created",
        "e4_undisclosed",
        "e4_tests_untouched",
        "e4_duplicates_none",
        "e5_command_run",
        "e5_regressions",
        "e5_outstanding_none",
        "e5_repro_result",
        "e5_build_result",
        "e5_final_files_diff",
        "e5_unintended_none",
        "e5_test_files_none",
    ],
    "temporal": [
        "t1_baseline_before_write",
        "t1_baseline_before_edit",
        "t1_no_edit_before_write",
        "t4_repro_written_before_write",
        "t5_repro_run_after_last_edit",
        "t5_regression_after_last_edit",
    ],
    "consistency": [
        "c23_tags_exist",
        "c23_requirements_covered",
        "c23_exercises_exist",
        "c23_coverage_refs",
        "c34_repro_path",
        "c34_targets_changed",
        "c34_plan_execution_steps",
        "c34_deviations_none",
        "c14_scope_changed",
        "c15_preexisting_subset",
        "c25_unmet_exist",
        "c45_final_files",
    ],
}
CHECKS = [c for fam in FAMILIES.values() for c in fam]

_STEP_REF = re.compile(r"\bStep\s+(\d+)", re.I)


def observe(run: Run) -> Observed:
    """The shared trajectory index, with the five artifact paths watched (their writes are the
    stage write steps, not repository edits)."""
    return _observe(run, watch=A.ARTIFACT_PATHS)


def _section_none(parsed: dict | None, section: str) -> bool | None:
    """A bare-list section (``## Deviations from Plan``, ``## Outstanding Failures``): True when every
    line says none, False when it has content, None when the section is absent."""
    return None if parsed is None else _body_none(parsed["section_bodies"].get(section))


def _field(parsed: dict | None, section: str, label: str) -> str | None:
    """A field value, or None when the stage, the section or the field is missing or empty."""
    if parsed is None:
        return None
    body = parsed["section_bodies"].get(section)
    if body is None:
        return None
    return A.field_value(body, label) or None


def first_write_steps(run: Run) -> dict[int, int | None]:
    """Stage -> the first step that successfully wrote its artifact's path, whether or not the
    text could be recovered and whether or not the file survived. ``None`` when never written."""
    first: dict[int, int] = {}
    for step in run.steps:
        for a in step.actions:
            if a.status == "fail":
                continue
            targets = F.write_targets(a) if a.kind == "shell" else ([a.path] if F.is_write(a) else [])
            for t in targets:
                st = A.ARTIFACT_PATHS.get(t)
                if st is not None and not (a.kind == "shell" and F._rm_matches(a.command or "", t)):
                    first.setdefault(st, step.n)
    return {st: first.get(st) for st in A.STAGE_FILES}


# --- the checks ---------------------------------------------------------------------------


def _repro_path(p3: dict | None, p4: dict | None) -> str | None:
    for parsed in (p4, p3):
        for cand in claimed_paths(_field(parsed, "Reproduction Script", "Path")):
            return cand
    return None


def content_checks(run: Run, parsed: dict[int, dict | None], obs: Observed | None = None) -> dict:
    """Every check for one run.

    ``parsed`` is stage -> ``artifacts.parse`` of the artifact's final text, or None for a stage
    with no artifact (``facts.trace_artifacts`` provides both). Returns ``checks`` (name -> value or
    None), ``families`` (family -> mean of its applicable checks or None), ``content`` (mean of the
    applicable family means), and ``contradictions`` (how many checks came out 0).
    """
    obs = obs or observe(run)
    w = first_write_steps(run)
    p1, p2, p3, p4, p5 = (parsed.get(st) for st in (1, 2, 3, 4, 5))
    c: dict[str, float | None] = dict.fromkeys(CHECKS)

    # -- stage 1: scope, commands, baseline -------------------------------------------------
    failing1: str | None = None
    if p1 is not None:
        scope = claimed_paths(_field(p1, "Affected Scope", "Files"))
        c["e1_scope_viewed"] = _membership(scope, [obs.seen(p, before=w[1]) for p in scope])
        c["e1_test_command_run"] = SUPPORTED if obs.command_run(tok := _command_tokens(_field(p1, "Build & Test Commands", "Test"))) else (CONTRADICTED if tok else None)
        build = _field(p1, "Build & Test Commands", "Build")
        if build and not _none(build) and _command_core(build):
            c["e1_build_command_run"] = SUPPORTED if obs.command_runs(build) else CONTRADICTED
        tpaths = claimed_paths(_field(p1, "Existing Tests", "Path"))
        c["e1_test_path_seen"] = _membership(tpaths, [obs.seen(p) or obs.mentioned_in_shell(p) for p in tpaths])

        passing, failing1 = _field(p1, "Baseline", "Passing"), _field(p1, "Baseline", "Failing")
        both_none = _none(passing) and _none(failing1)
        baseline_runs = obs.tests_in(before=obs.first_edit)
        # A baseline is observed by running the tests before writing it down. `none / none` may
        # instead rest on an attempt that found nothing to run.
        looked = obs.tests_in(before=w[1]) or (both_none and any(_NO_TESTS.search(o) for _, _, o in obs.attempts_in(before=w[1])))
        c["t1_baseline_before_write"] = SUPPORTED if looked else CONTRADICTED
        if obs.first_edit is not None:
            c["t1_baseline_before_edit"] = SUPPORTED if baseline_runs else CONTRADICTED
            if w[1] is not None:
                c["t1_no_edit_before_write"] = SUPPORTED if obs.first_edit > w[1] else CONTRADICTED
        if baseline_runs:
            out = "\n".join(o for _, _, o in baseline_runs)
            names = sorted({*_TEST_ID.findall(passing or ""), *_TEST_ID.findall(failing1 or "")})
            if names and _names_test_ids(out):
                c["e1_baseline_tests"] = _membership(names, [n in out for n in names])
            fails = _failures(out)
            if both_none:
                c["e1_baseline_none"] = CONTRADICTED if (fails or _passes(out) or _names_test_ids(out)) else SUPPORTED
            if _none(failing1):
                c["e1_baseline_failing"] = CONTRADICTED if fails else SUPPORTED
            elif failing1:
                c["e1_baseline_failing"] = SUPPORTED if fails or any(n in out for n in _TEST_ID.findall(failing1)) else CONTRADICTED

    # -- stage 2 <-> 3: requirements and the plan --------------------------------------------
    r_ids = list(dict.fromkeys(p2["r_ids"])) if p2 else []
    step_nums = sorted({s["n"] for s in p3["steps"]}) if p3 else []
    if p3 is not None:
        tags = sorted({t for s in p3["steps"] for t in s["tags"]})
        if tags and r_ids:
            c["c23_tags_exist"] = _membership(tags, [t in r_ids for t in tags])
        if r_ids:
            body2 = p2["body"]
            real = [r for r in r_ids if not re.search(rf"^\s*[-*+]\s*\*{{0,2}}{r}\*{{0,2}}\s*:\s*(?:none stated|none|n/?a|not applicable)\b", body2, re.I | re.M)]
            covered = set(tags) | set(p3.get("coverage_ids", []))
            c["c23_requirements_covered"] = _membership(real, [r in covered for r in real])
            exercises = _ids(_field(p3, "Reproduction Script", "Exercises"))
            c["c23_exercises_exist"] = _membership(exercises, [r in r_ids for r in exercises])
            coverage = p3["section_bodies"].get("Requirement Coverage")
            if coverage:
                refs = [(m.group(1), _STEP_REF.findall(m.group(2))) for m in A.COVERAGE_LINE.finditer(coverage)]
                claims = [r for r, _ in refs] + [f"Step {s}" for _, steps in refs for s in steps]
                found = [r in r_ids for r, _ in refs] + [int(s) in step_nums for _, steps in refs for s in steps]
                c["c23_coverage_refs"] = _membership(claims, found)

    # -- stage 4: changed files, the reproduction script ------------------------------------
    repro = _repro_path(p3, p4)
    mod: list[str] = []
    cre: list[str] = []
    if p4 is not None:
        mod = [m for m in (norm_path(x) for x in p4["claims"]["modified"]) if m]
        cre = [k for k in (norm_path(x) for x in p4["claims"]["created"]) if k]
        if mod:
            found = [obs.changed(m) for m in mod]
            c["e4_modified"] = None if (obs.edits_unknown and not all(found)) else _membership(mod, found)
        if cre:
            c["e4_created"] = _membership(cre, [obs.written(k) is not None for k in cre])
        if obs.edited and not obs.edits_unknown:
            named = [any(same_file(p, q) for q in claimed_paths(p4["body"])) or p.rsplit("/", 1)[-1] in p4["body"] for p in obs.edited]
            c["e4_undisclosed"] = _membership(list(obs.edited), named)
        if _none(_field(p4, "Checks", "Test files modified")):
            touched = [p for p in obs.edited if F.TEST_PATH_RE.search(p) and p not in obs.new_files]
            c["e4_tests_untouched"] = CONTRADICTED if touched else SUPPORTED
        if _none(_field(p4, "Checks", "Duplicate files created")):
            dupes = [p for p in obs.remaining if p in obs.new_files and (_DUPLICATE.search(p) or F.BACKUP_RE.search(p))]
            c["e4_duplicates_none"] = CONTRADICTED if dupes else SUPPORTED
        if repro:
            wrote = obs.written(repro)
            c["t4_repro_written_before_write"] = SUPPORTED if wrote is not None and (w[4] is None or wrote <= w[4]) else CONTRADICTED

    targets: list[str] = []
    if p3 is not None and p4 is not None:
        p3_path, p4_path = (claimed_paths(_field(p, "Reproduction Script", "Path")) for p in (p3, p4))
        if p3_path and p4_path:
            c["c34_repro_path"] = SUPPORTED if same_file(p3_path[0], p4_path[0]) else CONTRADICTED
        targets = list(dict.fromkeys(t for s in p3["steps"] for t in claimed_paths(s["fields"].get("Target"))))
        changed_claims = p4["claims"]["modified"] + p4["claims"]["created"]
        if targets and changed_claims:
            c["c34_targets_changed"] = _membership(targets, [any(same_file(t, q) for q in changed_claims) for t in targets])
        execution = p4["section_bodies"].get("Plan Execution")
        if execution and step_nums:
            listed = sorted({int(s) for s in _STEP_REF.findall(execution)})
            if listed:
                value = _membership(listed, [s in step_nums for s in listed])
                c["c34_plan_execution_steps"] = PARTIAL if value == SUPPORTED and set(step_nums) - set(listed) else value
        if _section_none(p4, "Deviations from Plan") and targets and (mod or cre):
            # The reproduction script has its own section in both stages; a plan may or may not
            # give it a step, so it is left out of the comparison on both sides.
            not_repro = lambda xs: [x for x in xs if not (repro and same_file(x, repro))]  # noqa: E731
            c["c34_deviations_none"] = SUPPORTED if _both_ways(not_repro(targets), not_repro(mod + cre)) == SUPPORTED else CONTRADICTED
    if p1 is not None and p4 is not None:
        scope = claimed_paths(_field(p1, "Affected Scope", "Files"))
        if scope and mod:
            c["c14_scope_changed"] = SUPPORTED if any(same_file(s, m) for s in scope for m in mod) else CONTRADICTED

    # -- stage 5: what was run after the change ---------------------------------------------
    if p5 is not None:
        if repro:
            # The run the report rests on: after the last change to the source, before the report.
            runs = obs.ran(repro, after=obs.last_edit if obs.last_edit is not None else w[4], before=w[5])
            if runs:
                c["t5_repro_run_after_last_edit"] = SUPPORTED
                result = (_field(p5, "Reproduction Script", "Result") or "").lower()
                code = _last_exit(runs[-1][2])
                if code is not None and result:
                    failed = code != 0
                    if result.startswith("pass"):
                        c["e5_repro_result"] = CONTRADICTED if failed else SUPPORTED
                    elif result.startswith("fail"):
                        c["e5_repro_result"] = SUPPORTED if failed else CONTRADICTED
            else:
                c["t5_repro_run_after_last_edit"] = CONTRADICTED
        build_cmd, build_result = _field(p5, "Build", "Command"), (_field(p5, "Build", "Result") or "").lower()
        if build_cmd and not _none(build_cmd) and _command_core(build_cmd):
            builds = obs.command_runs(build_cmd, after=obs.last_edit)
            if not builds:
                c["e5_build_result"] = CONTRADICTED
            elif (code := _last_exit(builds[-1][2])) is not None and build_result:
                ok = build_result.startswith(("success", "pass", "ok"))
                c["e5_build_result"] = SUPPORTED if ok == (code == 0) else CONTRADICTED
        command = _field(p5, "Existing Tests vs Baseline", "Command")
        tokens = _command_tokens(command)
        post = obs.tests_in(after=obs.last_edit, before=w[5]) or []
        if obs.source_edits:
            c["t5_regression_after_last_edit"] = SUPPORTED if post else CONTRADICTED
        if tokens:
            c["e5_command_run"] = SUPPORTED if obs.command_run(tokens, after=obs.last_edit) else CONTRADICTED
        regressions = _field(p5, "Existing Tests vs Baseline", "Regressions")
        verdict = (_field(p5, "Existing Tests vs Baseline", "Verdict") or "").lower()
        if post and (_none(regressions) or verdict.startswith("unchanged")):
            c["e5_regressions"] = CONTRADICTED if _failures(post[-1][2]) else SUPPORTED
        if post and _section_none(p5, "Outstanding Failures"):
            c["e5_outstanding_none"] = CONTRADICTED if _failures(post[-1][2]) else SUPPORTED
        pre = _field(p5, "Existing Tests vs Baseline", "Pre-existing failures")
        if pre and p1 is not None:
            if _none(pre):
                named = _TEST_ID.findall(failing1 or "")
                c["c15_preexisting_subset"] = SUPPORTED if (failing1 is None or _none(failing1)) else (CONTRADICTED if named else None)
            else:
                base_ids = _TEST_ID.findall(failing1 or "")
                pre_ids = _TEST_ID.findall(pre)
                if pre_ids:
                    c["c15_preexisting_subset"] = CONTRADICTED if _none(failing1) or not failing1 else _membership(pre_ids, [t in base_ids for t in pre_ids])
        unmet = _ids(_field(p5, "Reproduction Script", "Unmet requirements"))
        if unmet and r_ids:
            c["c25_unmet_exist"] = _membership(unmet, [r in r_ids for r in unmet])
        final = claimed_paths(_field(p5, "Final Change", "Files in the change"))
        if final and p4 is not None and (p4["claims"]["modified"] or p4["claims"]["created"]):
            stage4 = p4["claims"]["modified"] + p4["claims"]["created"]
            c["c45_final_files"] = _membership(final, [any(same_file(f, q) for q in stage4) for f in final])
        if not obs.edits_unknown:
            remaining = list(obs.remaining)
            unintended = _field(p5, "Final Change", "Unintended files in the repository")
            disclosed = claimed_paths(unintended)
            actual = [p for p in remaining if not any(same_file(p, u) for u in disclosed)]
            if final or actual:
                c["e5_final_files_diff"] = _both_ways(final, actual)
            if _none(unintended):
                stray = [p for p in remaining if p in obs.new_files and not any(same_file(p, f) for f in final)]
                c["e5_unintended_none"] = CONTRADICTED if stray else SUPPORTED
            if _none(_field(p5, "Final Change", "Test files in the change")):
                c["e5_test_files_none"] = CONTRADICTED if any(F.TEST_PATH_RE.search(p) and p not in obs.new_files for p in remaining) else SUPPORTED

    families = {fam: (mean(v) if (v := [c[k] for k in names if c[k] is not None]) else None) for fam, names in FAMILIES.items()}
    applicable = [v for v in families.values() if v is not None]
    return {
        "checks": c,
        "families": families,
        "content": mean(applicable) if applicable else None,
        "contradictions": sum(1 for v in c.values() if v == CONTRADICTED),
    }


def parsed_artifacts(run: Run) -> dict[int, dict | None]:
    """Stage -> parsed final artifact, from the collected files when the run has them, else from
    the writes in the trajectory (``facts.trace_artifacts``)."""
    traces = F.trace_artifacts(run)
    return {st: (A.parse(st, t.content) if t.content is not None else None) for st, t in traces.items()}
