"""Category scores: every measured rule placed by kind x stage, so a low score says what kind of compliance
fails, and in which stage.

The rule ids are the workflow's atomic rules (one requirement each, every line of the documents
accounted for; the local task record's ``ATOMIC.md``). A rule's score is the mean of the signals measuring
it; a cell's is the mean of its rules'; a kind's is the mean of its cells' (each stage alike); and
``aidlc/score``, the evaluation's total, is the mean of the kinds' (each kind alike, however many rules it
has). Each signal measures one rule, so nothing is counted twice.

A stage the run did not carry out (stages 1..5: its artifact was not collected; the artifact is what
states a stage finished) scores 0 in every cell of it a carried-out stage can have, whatever its rules
measured, except the forbidden-action cell: a prohibition kept by not doing the stage is no credit, so
that cell is left out. A cell no rule measures in a carried-out stage (no regression to report, ...) is
left out too. Stage 0 cells are never filled in.

    kinds   P procedure (when and how documents are read, stages taken in order)
            F artifact form (the file, its skeleton, each field filled)
            E execution (the required actions done: baseline, reproduction, regression runs)
            C consistency across stages (requirements -> plan -> paths -> final change)
            R forbidden actions (test edits, installs, leftovers, ...)
            Q content adequacy (what is written is right and meaningful)
            A accuracy: what an artifact claims holds against what was observed (the "is it true" part
              of a rule of another kind, scored on its own row)
    stages  0 entry and the whole run, 1..5 the stages

Rules that repeat per stage (read the stage's document first, the artifact exists, each skeleton field)
are scored per stage, in that stage's cell. ``aidlc/cat/<kind><stage>`` and ``aidlc/kind/<kind>`` are
emitted for every cell and kind with a score. The solution-leak flags and ``aidlc/patch_empty`` are a
separate ledger and enter no category.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from ._claims import field_value as claims_field_value
from .rubric import artifacts as A

# signal -> (rule, kind, stage). The "A" kind is the accuracy part of the named rule.
SIGNAL_RULES = {
    "aidlc/entry": ("A1", "P", 0),
    "aidlc/check/t1_no_edit_before_write": ("D11b", "P", 1),
    "aidlc/ran_real_test": ("D11a", "E", 1),
    "aidlc/check/t1_baseline_before_write": ("D11a", "E", 1),
    "aidlc/check/t1_baseline_before_edit": ("D11a", "E", 1),
    "aidlc/check/t5_repro_run_after_last_edit": ("H2", "E", 5),
    "aidlc/check/t5_regression_after_last_edit": ("H4b", "E", 5),
    "aidlc/check/c14_scope_changed": ("G2", "C", 4),  # stage 4 changed files inside stage 1's scope
    "aidlc/check/c23_requirements_covered": ("F1a", "C", 3),
    "aidlc/check/c34_targets_changed": ("G2", "C", 4),
    "aidlc/check/c34_repro_path": ("G7a", "C", 4),
    "aidlc/check/c45_final_files": ("H13", "C", 5),
    "aidlc/rule/r_artifacts_written_once": ("B3a", "F", 0),
    "aidlc/rule/r_no_env_setup": ("D9", "R", 0),
    "aidlc/rule/r_tests_untouched": ("D13", "R", 4),
    "aidlc/rule/r_repro_not_in_stage4": ("G7b", "R", 4),
    "aidlc/rule/r_targeted_tests": ("H6", "R", 5),
    "aidlc/rule/r_repo_clean": ("H12", "R", 5),
    # accuracy parts
    "aidlc/check/e1_scope_viewed": ("D1a", "A", 1),
    "aidlc/check/e1_build_command_run": ("D6", "A", 1),
    "aidlc/check/e1_test_command_run": ("D7a", "A", 1),
    "aidlc/check/e1_test_path_seen": ("D10a", "A", 1),
    "aidlc/check/e1_baseline_tests": ("D12a", "A", 1),
    "aidlc/check/e1_baseline_failing": ("D12a", "A", 1),
    "aidlc/check/e1_baseline_none": ("D12a", "A", 1),
    "aidlc/check/c23_tags_exist": ("S3.tag", "A", 3),
    "aidlc/check/c23_exercises_exist": ("S3.exercises", "A", 3),
    "aidlc/check/c23_coverage_refs": ("F5", "A", 3),
    "aidlc/check/t4_repro_written_before_write": ("G7a", "A", 4),
    "aidlc/check/c34_deviations_none": ("G8a", "A", 4),
    "aidlc/check/c34_plan_execution_steps": ("G9", "A", 4),
    "aidlc/check/e4_modified": ("S4.modified", "A", 4),
    "aidlc/check/e4_undisclosed": ("S4.modified", "A", 4),
    "aidlc/fidelity": ("S4.modified", "A", 4),
    "aidlc/check/e4_created": ("S4.created", "A", 4),
    "aidlc/check/e4_duplicates_none": ("S4.checks", "A", 4),
    "aidlc/check/e4_tests_untouched": ("S4.checks", "A", 4),
    "aidlc/check/e5_build_result": ("H1b", "A", 5),
    "aidlc/check/e5_repro_result": ("H2", "A", 5),
    "aidlc/check/e5_command_run": ("H4b", "A", 5),
    "aidlc/check/e5_regressions": ("H5", "A", 5),
    "aidlc/check/c15_preexisting_subset": ("H5", "A", 5),
    "aidlc/check/e5_outstanding_none": ("H11", "A", 5),
    "aidlc/check/e5_unintended_none": ("H12", "A", 5),
    "aidlc/check/e5_final_files_diff": ("H13", "A", 5),
    "aidlc/check/e5_test_files_none": ("H14", "A", 5),
    "aidlc/check/c25_unmet_exist": ("H15c", "A", 5),
}

# Atomic checks (atomic_checks.py): rule -> (kind, stage); a check named <rule>@<k> lands in stage k.
ATOM_KINDS = {
    "B5d": ("F", 0),
    "B6b": ("F", 0),
    "B6c": ("F", 0),
    "D5": ("F", 1),
    "D12b": ("F", 1),
    "E4a": ("F", 2),
    "E8c": ("F", 2),
    "F1b": ("F", 3),
    "F2a": ("F", 3),
    "F2b": ("F", 3),
    "G8b": ("F", 4),
    "S4.tags": ("F", 4),
    "H15a": ("F", 5),
    "H15d": ("F", 5),
    "G3c": ("C", 4),
    "H1a": ("C", 5),
    "H4a": ("C", 5),
    "H15b": ("C", 5),
    "H15c": ("C", 5),
    "H8a": ("E", 5),
    "H8e": ("E", 5),
    "H9a": ("E", 5),
    "B10": ("R", 0),
    "E10a": ("R", 0),
    "C2": ("P", 0),
    "F7": ("R", 3),
    "F8a": ("R", 3),
    "F8b": ("R", 3),
    "G4b": ("R", 4),
    "D1b": ("Q", 1),
    "D4a": ("Q", 1),
    "D7b": ("Q", 1),
    "E7b": ("Q", 2),
    "F4b": ("Q", 3),
    "B8": ("P", 0),
    "E10b": ("P", 0),
    "G3a": ("P", 4),
    "H1c": ("P", 5),
    "H10": ("P", 5),
    "D8": ("E", 1),
    "G1a": ("C", 4),
    "D4b": ("R", 1),
    "H7": ("R", 5),
    "E3a": ("Q", 2),
    "F3": ("Q", 3),
    "F9b": ("Q", 3),
    "H11": ("Q", 5),
}

# judge.QUESTIONS' rules -> (kind, stage); a rule code also judges (D1b, E7b) averages both verdicts
JUDGE_KINDS = {
    **{r: ("Q", 1) for r in ("D1a", "D1b", "D3", "D6")},
    "D10b": ("E", 1),
    **{r: ("Q", 2) for r in ("E1a", "E1b", "E3b", "E6a", "E6b", "E7a", "E7b", "E8a", "E8b", "E9")},
    **{r: ("Q", 3) for r in ("F2d", "F2e", "F4a", "F9a")},
    "G5": ("C", 4),
    "G8a": ("Q", 4),
    "G8c": ("Q", 4),
    "B4b": ("Q", 0),
    **{r: ("Q", 5) for r in ("H3a", "H3b", "H3c", "H8d", "H9b")},
}

# Skeleton fields, one rule each: rule -> (stage, section, label or None for the section's own content, none allowed)
FIELDS = {
    "S1.files": (1, "Affected Scope", "Files", False),
    "S1.module": (1, "Affected Scope", "Owning module", False),
    "S1.lang": (1, "Affected Scope", "Language/framework", False),
    "S1.build": (1, "Build & Test Commands", "Build", True),
    "S1.test": (1, "Build & Test Commands", "Test", False),
    "S1.tpath": (1, "Existing Tests", "Path", False),
    "S1.contract": (1, "Existing Tests", "Contract", False),
    "S1.passing": (1, "Baseline", "Passing", True),
    "S1.failing": (1, "Baseline", "Failing", True),
    "S2.fr": (2, "Functional Requirements", None, False),
    "S2.nfr": (2, "Non-Functional Requirements", None, True),
    "S2.edge": (2, "Edge Cases & Error Handling", None, False),
    "S2.assume": (2, "Assumptions", None, True),
    "S3.rpath": (3, "Reproduction Script", "Path", False),
    "S3.exercises": (3, "Reproduction Script", "Exercises", False),
    "S3.coverage": (3, "Requirement Coverage", None, False),
    "S4.modified": (4, "Changed Files", "Modified", False),
    "S4.created": (4, "Changed Files", "Created", True),
    "S4.rpath": (4, "Reproduction Script", "Path", False),
    "S4.executed": (4, "Reproduction Script", "Executed", False),
    "G9": (4, "Plan Execution", None, False),
    "S4.deviations": (4, "Deviations from Plan", None, True),
    "S4.dupcheck": (4, "Checks", "Duplicate files created", True),
    "S4.testcheck": (4, "Checks", "Test files modified", True),
    "S5.bresult": (5, "Build", "Result", False),
    "S5.bcmd": (5, "Build", "Command", False),
    "S5.rresult": (5, "Reproduction Script", "Result", False),
    "S5.unmet": (5, "Reproduction Script", "Unmet requirements", True),
    "S5.cmd": (5, "Existing Tests vs Baseline", "Command", False),
    "S5.verdict": (5, "Existing Tests vs Baseline", "Verdict", False),
    "S5.regress": (5, "Existing Tests vs Baseline", "Regressions", True),
    "S5.pre": (5, "Existing Tests vs Baseline", "Pre-existing failures", True),
    "S5.fixes": (5, "Fixes Applied", None, True),
    "S5.outstanding": (5, "Outstanding Failures", None, True),
    "S5.final_files": (5, "Final Change", "Files in the change", False),
    "S5.final_unintended": (5, "Final Change", "Unintended files in the repository", True),
    "S5.final_tests": (5, "Final Change", "Test files in the change", True),
}
STEP_FIELDS = {"S3.target": "Target", "S3.change": "Change", "S3.contract": "Contract", "S3.verify": "Verification"}


def _label_filled(body: str | None, label: str, allow_none: bool) -> bool:
    """One ``- Label: value`` field filled in, as the rubric's ``field_present`` reads a single label."""
    if body is None:
        return False
    val = claims_field_value(body, label)
    if val is None:  # `- Path: x — Contract: y` puts two labels on one line
        hit = re.search(rf"{re.escape(label)}\s*:\s*([^\n]*)", body, re.I)
        val = hit.group(1).strip(" *`") if hit else None
        if val is not None and A.PLACEHOLDER.fullmatch(val):
            val = ""
    return bool(val) and (allow_none or not A.NONE_VALUE.fullmatch(val))


def _artifact_rules(parsed: dict) -> list[tuple[str, str, int, float]]:
    """Per-stage form rules from the collected artifacts: the frontmatter, the headings, every field."""
    out = []
    for st in A.STAGE_FILES:
        p = parsed.get(st)
        out.append(("B1", "F", st, 1.0 if p is not None else 0.0))
        if p is None:
            continue
        out.append(("B6a", "F", st, 1.0 if p["frontmatter"]["valid"] else 0.0))
        want = A.SECTIONS[st]["graded"] + A.SECTIONS[st]["extra"]
        out.append(("B5b", "F", st, sum(w in p["section_bodies"] for w in want) / len(want)))
    for rule, (st, section, label, allow_none) in FIELDS.items():
        p = parsed.get(st)
        if p is None:
            value = 0.0
        else:
            body = p["section_bodies"].get(section)
            value = float(_label_filled(body, label, allow_none) if label else (body is not None and A._section_has_content(body, allow_none)))
        out.append((rule, "F", st, value))
    p3 = parsed.get(3)
    steps = p3.get("steps", []) if p3 else []
    for rule, label in STEP_FIELDS.items():
        out.append((rule, "F", 3, float(bool(steps) and all(s["fields"].get(label) for s in steps))))
    out.append(("S3.tag", "F", 3, float(bool(steps) and all(s["tags"] for s in steps))))
    p2 = parsed.get(2)
    ids = p2.get("r_ids", []) if p2 else []
    out.append(("E3c", "F", 2, float(bool(ids))))
    out.append(("E4b", "F", 2, float(bool(ids) and len(set(ids)) == len(ids))))
    return out


def _procedure_rules(read_step: dict, write_step: dict, invalid: set) -> list[tuple[str, str, int, float]]:
    """Per-stage procedure rules from the first reads of the rule documents and the first artifact writes."""
    out = []
    read = {k: read_step.get(f"0{k}") if f"0{k}" not in invalid else None for k in range(1, 6)}
    if any(f"0{k}" in read_step for k in range(1, 6)):
        out.append(("A3a", "P", 0, 1 - len(invalid) / 5))
    for k in range(1, 6):
        w, r, wprev = write_step.get(k), read[k], write_step.get(k - 1)
        # The stage was carried out: its document read (however) before its artifact, the artifacts in order.
        doc_read = read_step.get(f"0{k}") is not None and w is not None and read_step[f"0{k}"] < w
        out.append(("C1", "P", k, 1.0 if doc_read and (k == 1 or (wprev is not None and wprev < w)) else 0.0))
        if w is not None:  # the stage was done: was its document its first step?
            out.append(("A2", "P", k, 1.0 if r is not None and r < w and (wprev is None or r > wprev) else 0.0))
        if k > 1 and r is not None:  # no reading ahead of the previous stage's artifact
            out.append(("A3b", "P", k, 1.0 if wprev is not None and r > wprev else 0.0))
        if k < 5 and w is not None and read[k + 1] is not None:  # the artifact closes the stage
            out.append(("B3b", "P", k, 1.0 if w < read[k + 1] else 0.0))
    return out


def category_scores(signals: dict[str, float], parsed: dict, read_step: dict, write_step: dict, invalid_reads) -> dict[str, float]:
    """``aidlc/cat/<kind><stage>`` and ``aidlc/kind/<kind>`` from the episode's signals and its artifacts."""
    per_rule: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for key, value in signals.items():
        if key in SIGNAL_RULES:
            rule, kind, stage = SIGNAL_RULES[key]
            per_rule[(rule, kind, stage)].append(value)
        elif key.startswith("aidlc/atom/"):
            rule, _, at = key.removeprefix("aidlc/atom/").partition("@")
            kind, stage = ATOM_KINDS[rule]
            per_rule[(rule, kind, int(at) if at else stage)].append(value)
        elif key.startswith("aidlc/judge/"):
            rule = key.removeprefix("aidlc/judge/")
            kind, stage = JUDGE_KINDS[rule]
            per_rule[(rule, kind, stage)].append(value)
    for rule, kind, stage, value in _artifact_rules(parsed) + _procedure_rules(read_step, write_step, set(invalid_reads)):
        per_rule[(rule, kind, stage)].append(value)
    done = {st for st in range(1, 6) if parsed.get(st) is not None}
    rules: dict[tuple[str, int], list[float]] = defaultdict(list)
    for (_, kind, stage), values in per_rule.items():
        if stage == 0 or stage in done or kind != "R":
            rules[(kind, stage)].append(mean(values))
    cells = {(kind, stage): mean(v) for (kind, stage), v in rules.items()}
    for kind, stage in expected_cells(judged="aidlc/judge_calls" in signals):
        if stage not in done and kind != "R":
            cells[(kind, stage)] = 0.0
    kinds = {kind: mean(v for (k, _), v in cells.items() if k == kind) for kind in sorted({k for k, _ in cells})}
    return {
        **{f"aidlc/cat/{kind}{stage}": v for (kind, stage), v in sorted(cells.items())},
        **{f"aidlc/kind/{kind}": v for kind, v in kinds.items()},
        **({"aidlc/score": mean(kinds.values())} if kinds else {}),
        "aidlc/done_stages": float(len(done)),
    }


def expected_cells(judged: bool = False) -> set[tuple[str, int]]:
    """The (kind, stage) cells of stages 1..5 some rule can score in a carried-out stage: what a stage not
    carried out is missing. The judge's cells count only when the judge ran."""
    placed = [(k, s) for _, k, s in SIGNAL_RULES.values()] + list(ATOM_KINDS.values()) + (list(JUDGE_KINDS.values()) if judged else [])
    placed += [(k, s) for k in ("F", "P") for s in range(1, 6)]  # the artifact, its fields, its document
    return {(k, s) for k, s in placed if s >= 1}
