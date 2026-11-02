"""form/*: an artifact's form -- present, its frontmatter, its headings, each skeleton field filled in.

The fields (``FIELDS``, ``STEP_FIELDS``) are one rule each, measured by one function from their table row.
"""

from __future__ import annotations

import re
from functools import partial

from .. import skeleton as A
from ..read import field_value
from . import STAGES, method

AP = ("AP", "COLLECT")

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

# The plan's per-step fields: rule -> label, kept when every step fills it in
STEP_FIELDS = {"S3.target": "Target", "S3.change": "Change", "S3.contract": "Contract", "S3.verify": "Verification"}


def _label_filled(body: str | None, label: str, allow_none: bool) -> bool:
    """One ``- Label: value`` field filled in, as the rubric's ``field_present`` reads a single label."""
    if body is None:
        return False
    val = field_value(body, label)
    if val is None:  # `- Path: x — Contract: y` puts two labels on one line
        hit = re.search(rf"{re.escape(label)}\s*:\s*([^\n]*)", body, re.I)
        val = hit.group(1).strip(" *`") if hit else None
        if val is not None and A.PLACEHOLDER.fullmatch(val):
            val = ""
    return bool(val) and (allow_none or not A.NONE_VALUE.fullmatch(val))


@method("form/B1", materials=AP, stages=STAGES)
def b1(m, st):
    """The stage's artifact exists (collected): the stage was carried out."""
    return 1.0 if m.parsed.get(st) is not None else 0.0


@method("form/B6a", materials=AP, stages=STAGES)
def b6a(m, st):
    """The artifact's frontmatter is valid."""
    p = m.parsed.get(st)
    return None if p is None else (1.0 if p["frontmatter"]["valid"] else 0.0)


@method("form/B5b", materials=AP, stages=STAGES)
def b5b(m, st):
    """The share of the skeleton's headings the artifact has."""
    p = m.parsed.get(st)
    if p is None:
        return None
    want = A.SECTIONS[st]["graded"] + A.SECTIONS[st]["extra"]
    return sum(w in p["section_bodies"] for w in want) / len(want)


def _field_filled(rule: str, m, st):
    """The field's table row (``FIELDS``): its label filled in, or its bare-list section has content; 0 without the
    artifact."""
    _, section, label, allow_none = FIELDS[rule]
    p = m.parsed.get(st)
    if p is None:
        return 0.0
    body = p["section_bodies"].get(section)
    return float(_label_filled(body, label, allow_none) if label else (body is not None and A._section_has_content(body, allow_none)))


for _rule, (_st, *_) in FIELDS.items():
    method(f"form/{_rule}", materials=AP, stages=(_st,))(partial(_field_filled, _rule))


def _step_field(label: str, m, st):
    """Every plan step fills in ``label``."""
    return float(bool(m.steps) and all(s["fields"].get(label) for s in m.steps))


for _rule, _label in STEP_FIELDS.items():
    method(f"form/{_rule}", materials=AP, stages=(3,))(partial(_step_field, _label))


@method("form/S3.tag", materials=AP, stages=(3,))
def s3_tag(m, st):
    """Every plan step tags a requirement."""
    return float(bool(m.steps) and all(s["tags"] for s in m.steps))


@method("form/E3c", materials=AP, stages=(2,))
def e3c(m, st):
    """Artifact 02 numbers its requirements (R ids)."""
    ids = m.p2.get("r_ids", []) if m.p2 else []
    return float(bool(ids))


@method("form/E4b", materials=AP, stages=(2,))
def e4b(m, st):
    """Artifact 02's R ids are unique; with none there is nothing to repeat (E3c scores their absence; this scored it
    a second time until 2026-11-02)."""
    ids = m.p2.get("r_ids", []) if m.p2 else []
    if not ids:
        return None
    return float(len(set(ids)) == len(ids))
