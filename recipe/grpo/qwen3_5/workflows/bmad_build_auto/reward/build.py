"""Build ``rubric.yaml``, ``layers.yaml`` and ``../constraints.yaml`` for the bmad_build_auto evaluation.

    python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward.build [--check]

Inputs: the port's rule inventory ``porting/rules.yaml`` (every line of the upstream documents as a rule),
the stage-3 decisions encoded in ``workflows/if/scripts/bmad/decided_layers.py`` (which rules are scored,
their template and evaluation layer), and the ``ITEMS`` table below, which says how each scored rule is
judged: a common ``workflow_rubric`` kind, one of this package's ``bmad.*`` kinds (``checks.py``), or
``unimplemented`` (kept in the rubric at weight 0 so the constraint stays visible; judge rules are
``unimplemented`` + ``log_only`` until a judge endpoint is wired).

Every item's sources are re-anchored from the upstream line references to the ported documents by quote
(``sdlc_if.anchor``); a quote the port removed falls back to the setting section of core-workflow.md and
says so in the item's note. ``--check`` fails when the committed files differ from a fresh build.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import re
import sys
from pathlib import Path

import yaml

from recipe.grpo.qwen3_5.sdlc_if.anchor import anchor
from recipe.grpo.qwen3_5.workflow_rubric.layers import rubric_sha256

HERE = Path(__file__).resolve().parent
WF = HERE.parent
WORKFLOWS = WF.parent
RULES = WF / "porting" / "rules.yaml"
DECIDED = WORKFLOWS / "if" / "scripts" / "bmad" / "decided_layers.py"
RUBRIC = HERE / "rubric.yaml"
LAYERS = HERE / "layers.yaml"
CONSTRAINTS = WF / "constraints.yaml"
TEMPLATES = WORKFLOWS.parent / "sdlc_if" / "templates.yaml"

CONTAINER = "/bmad-build-auto"
ARTIFACT_ROOT = "/tmp/bmad"
WORKFLOW = "bmad_build_auto"
P = WORKFLOW + "."

# source id -> (path in the package, role, container path)
DOCS = {
    "CW": ("docs/core-workflow.md", "core", f"{CONTAINER}/core-workflow.md"),
    "S1": ("docs/stages/step-01-clarify-and-route.md", "stage_rule", f"{CONTAINER}/stages/step-01-clarify-and-route.md"),
    "S2": ("docs/stages/step-02-plan.md", "stage_rule", f"{CONTAINER}/stages/step-02-plan.md"),
    "S3": ("docs/stages/step-03-implement.md", "stage_rule", f"{CONTAINER}/stages/step-03-implement.md"),
    "S4": ("docs/stages/step-04-review.md", "stage_rule", f"{CONTAINER}/stages/step-04-review.md"),
    "ST": ("docs/spec-template.md", "template", f"{CONTAINER}/spec-template.md"),
    "EH": ("docs/review-prompts/edge-case-hunter.md", "reference", f"{CONTAINER}/review-prompts/edge-case-hunter.md"),
    "VG": ("docs/review-prompts/verification-gap.md", "reference", f"{CONTAINER}/review-prompts/verification-gap.md"),
    "CC": ("docs/references/claims-check.md", "reference", f"{CONTAINER}/references/claims-check.md"),
    "DC": ("docs/references/deletion-check.md", "reference", f"{CONTAINER}/references/deletion-check.md"),
    "INS": ("instruction.md", "instruction", ""),
    "SP": ("system-prompt.j2", "system_prompt", ""),
}
# upstream source ids of rules.yaml -> the ported document that now holds the text (None: search all)
DOC_MAP = {"WF": "CW", "SK": "CW", "MB": "CW", "MC": "CW", "CT": None}
STAGE_OF = {"0": "global", "1": "step01", "2": "step02", "3": "step03", "4": "step04", "halt": "step04"}
TRACE_KINDS = {"doc_read", "doc_read_first", "order", "prohibited_action", "exec_evidence", "bmad.command", "bmad.task_calls", "bmad.lens_output", "bmad.no_doc_read", "bmad.last_message"}
BOTH_KINDS = {"write_discipline", "bmad.artifact_io", "bmad.paths_read"}
STRUCTURE_KINDS = {"artifact_exists", "path_match", "frontmatter", "section_present", "label_present", "field_literal", "bmad.frontmatter_value", "bmad.spec_count", "bmad.diff_file"}
EVIDENCE_KINDS = TRACE_KINDS | BOTH_KINDS | {"bmad.block_unchanged", "bmad.append_only"}

SPEC_HEADINGS = ["Intent", "Boundaries & Constraints", "I/O & Edge-Case Matrix", "Code Map", "Tasks & Acceptance", "Spec Change Log", "Review Triage Log", "Design Notes", "Verification", "Auto Run Result"]
PLACEHOLDERS = ["ONE_TO_TWO_SENTENCES", "INVARIANT_RULES", "NON_GOALS_AND_FORBIDDEN_APPROACHES", "HAPPY_PATH", "ERROR_CASE", "ROLE_OR_RELEVANCE", r"\bRATIONALE\b", "PRECONDITION", "EXPECTED_RESULT", "SUCCESS_CRITERIA", "WHAT_TO_INSPECT_AND_EXPECTED_STATE", "DESIGN_RATIONALE_AND_EXAMPLES", r"\bTBD\b", r"\{title\}", r"\{date\}"]
ROW = r"^\s*-\s+`\[(high|medium|low|false|maybe-false)\]`\s+`\[(bad_spec|patch|defer|reject)\]`\s+\S.*\s[—–-]+\s\S"
VERDICTS = r"^\s*-\s+verdicts:\s*\d+\s+findings?\s*[—–-]+\s*high\s+\d+,\s*medium\s+\d+,\s*low\s+\d+,\s*false\s+\d+,\s*maybe-false\s+\d+"
DIFF_PATH = r"/tmp/bmad/diff/[^\s`'\"]+\.diff"

# How each scored rule is judged. rule -> list of item specs; a rule absent here becomes ``unimplemented``.
# keys: kind, params, target (spec|diff|result|run), suffix, stage (default: the rule's), requirement, applies_when,
# fidelity (default faithful) + fidelity_note, note, log_only
I = dict
ITEMS: dict[str, list[dict]] = {
    # ---- reading and order (orchestrator trace) ----
    "A2": [I(kind="doc_read_first", params={"doc": "CW"}, target="run", stage="global")],
    "A4": [I(kind="doc_read", params={"doc": "S1", "min_coverage": 0.9}, target="run", stage="step01", suffix="s1")],
    "A14": [I(kind="doc_read", params={"doc": d, "min_coverage": 0.9}, target="run", stage=st, suffix=d.lower()) for d, st in (("S2", "step02"), ("S3", "step03"), ("S4", "step04"))],
    "A12": [I(kind="doc_read", params={"doc": d, "no_read_ahead": True}, target="run", stage=st, suffix=d.lower()) for d, st in (("S2", "step02"), ("S3", "step03"), ("S4", "step04"))],
    "A10": [I(kind="order", params={"chain": ["read:S1", "read:S2", "write:spec", "read:S3", "write:diff", "read:S4"], "invalidate": ["read_ahead"]}, target="run", stage="global")],
    "D6": [I(kind="doc_read", params={"doc": "ST", "min_coverage": 0.9, "window": "stage:step02"}, target="run", stage="step02")],
    "D23": [I(kind="doc_read", params={"doc": "CW", "window": "stage:step02"}, target="run", stage="step02", fidelity="narrower", fidelity_note="any read of core-workflow.md during step 2 counts, not only the one at the READY gate")],
    "D24": [I(kind="bmad.artifact_io", params={"artifact": "spec", "mode": "read", "after_write": True, "window": "stage:step02"}, target="run", stage="step02")],
    "C13": [I(kind="bmad.command", params={"pattern": r"ls\b[^\n|;&]*\/tmp\/bmad\/implementation-artifacts", "window": "stage:step01"}, target="run", stage="step01", fidelity="narrower", fidelity_note="an ls of the artifact directory in step 1")],
    "D5b": [I(kind="bmad.paths_read", params={"artifact": "spec", "section": "Code Map"}, target="run", stage="step02")],
    "E15": [I(kind="bmad.artifact_io", params={"artifact": "diff", "mode": "read", "after_write": True, "window": "stage:step03"}, target="run", stage="step03")],
    "G1": [I(kind="bmad.artifact_io", params={"artifact": "spec", "mode": "read", "window": "stage:step04"}, target="run", stage="step04", fidelity="narrower", fidelity_note="the spec is read during step 4 (the frontmatter field itself is not traced)")],
    "G2": [I(kind="bmad.artifact_io", params={"artifact": "diff", "mode": "write", "window": "stage:step04"}, target="run", stage="step04")],
    "F11": [I(kind="bmad.artifact_io", params={"artifact": "diff", "mode": "write", "window": ["last_change_write", "end"]}, target="run", stage="step04", fidelity="narrower", fidelity_note="the diff file is written after the last change to the code, whatever caused the change")],
    "G5": [I(kind="prohibited_action", params={"action": "command", "pattern": r"(^|[;&|]\s*)git\s+add\b", "window": "stage:step04"}, target="run", stage="step04")],
    "G9": [I(kind="bmad.no_doc_read", params={"docs": ["EH", "VG"]}, target="run", stage="step04")],
    "D1": [I(kind="bmad.last_message", params={}, target="run", stage="global")],
    # ---- the spec file ----
    "C29": [I(kind="artifact_exists", params={"artifact": "spec"}, target="spec", stage="step02")],
    "C27": [I(kind="path_match", params={"pattern": r"^(?:.*/)?spec-[a-z0-9]+(?:-[a-z0-9]+)*\.md$", "artifact": "spec"}, target="spec", stage="step02", fidelity="narrower", fidelity_note="kebab-case file name; whether a tracking id leads it is not checked")],
    "B15": [I(kind="bmad.spec_count", params={"pattern": r"/implementation-artifacts/spec-[^/]+\.md$", "min": 1, "max": 1, "under": f"{ARTIFACT_ROOT}/implementation-artifacts"}, target="spec", stage="global")],
    "B7": [I(kind="frontmatter", params={"keys": ["title", "type", "created", "status", "review_loop_iteration", "followup_review_recommended", "context", "warnings", "deferred"], "exact": False}, target="spec", stage="step02", fidelity="narrower", fidelity_note="the template's keys must be present; step 3 adds baseline_revision, so the set is not exact")],
    "B8": [I(kind="bmad.frontmatter_value", params={"key": "type", "values": ["feature", "bugfix", "refactor", "chore"]}, target="spec", stage="step02")],
    "B9": [I(kind="bmad.frontmatter_value", params={"key": "status", "values": ["draft", "ready-for-dev", "in-progress", "in-review", "done", "blocked"]}, target="spec", stage="step02")],
    "B10": [I(kind="bmad.frontmatter_value", params={"key": "review_loop_iteration", "pattern": r"^\d+$"}, target="spec", stage="step02", suffix="loop"), I(kind="bmad.frontmatter_value", params={"key": "followup_review_recommended", "pattern": r"^(true|false)$"}, target="spec", stage="step02", suffix="followup")],
    "B11": [I(kind="bmad.frontmatter_value", params={"key": "context", "tokens_pattern": r"^/testbed/"}, target="spec", stage="step02", fidelity="narrower", fidelity_note="every context entry starts with /testbed/; brevity is not judged")],
    "B12": [I(kind="bmad.frontmatter_value", params={"key": "warnings", "tokens": ["oversized", "multiple-goals"]}, target="spec", stage="step02")],
    "D7": [I(kind="bmad.frontmatter_value", params={"key": "created", "pattern": r"^\d{4}-\d{2}-\d{2}"}, target="spec", stage="step02", fidelity="narrower", fidelity_note="an ISO date; equality with the system date is not checked")],
    "E1": [I(kind="bmad.frontmatter_value", params={"key": "baseline_revision", "pattern": r"^([0-9a-f]{40}|NO_VCS)$"}, target="spec", stage="step03")],
    "C33": [I(kind="bmad.frontmatter_value", params={"key": "status", "values": ["done", "blocked"]}, target="spec", stage="step04")],
    "G87a": [I(kind="bmad.frontmatter_value", params={"key": "deferred", "required": True}, target="spec", stage="step04", fidelity="narrower", fidelity_note="the key exists once in valid YAML (a duplicate key makes the frontmatter invalid)")],
    "D32": [I(kind="bmad.text_regex", params={"pattern": r"(?s)<intent-contract>.*?## Intent.*?## Boundaries & Constraints.*?</intent-contract>"}, target="spec", stage="step02")],
    "D33": [I(kind="section_present", params={"heading": "Intent", "level": 2}, target="spec", stage="step02", suffix="section"),
            I(kind="label_present", params={"section": "Intent", "label": "Problem"}, target="spec", stage="step02", suffix="problem"),
            I(kind="label_present", params={"section": "Intent", "label": "Approach"}, target="spec", stage="step02", suffix="approach"),
            I(kind="field_filled", params={"section": "Intent", "label": "Problem"}, target="spec", stage="step02", suffix="problem_filled"),
            I(kind="field_filled", params={"section": "Intent", "label": "Approach"}, target="spec", stage="step02", suffix="approach_filled")],
    "D36": [I(kind="section_present", params={"heading": "Boundaries & Constraints", "level": 2}, target="spec", stage="step02", suffix="section"),
            I(kind="label_present", params={"section": "Boundaries & Constraints", "label": "Always"}, target="spec", stage="step02", suffix="always"),
            I(kind="label_present", params={"section": "Boundaries & Constraints", "label": "Never"}, target="spec", stage="step02", suffix="never"),
            I(kind="field_filled", params={"section": "Boundaries & Constraints", "label": "Always"}, target="spec", stage="step02", suffix="always_filled"),
            I(kind="field_filled", params={"section": "Boundaries & Constraints", "label": "Never"}, target="spec", stage="step02", suffix="never_filled")],
    "D38": [I(kind="bmad.text_regex", params={"section": "I/O & Edge-Case Matrix", "pattern": r"^\|(?!\s*Scenario\b)(?!\s*-)(?:[^|\n]*\|){4}\s*$", "min": 1, "optional_section": True}, target="spec", stage="step02", fidelity="narrower", fidelity_note="at least one four-cell row under the header; cell content is not judged")],
    "D39": [I(kind="cross_ref", params={"left": {"headings": {"artifact": "spec", "level": 2, "pattern": r"^(.+?)\s*$", "group": 1}}, "right": {"literal": SPEC_HEADINGS}, "relation": "subset", "normalize": "text"}, target="spec", stage="step02")],
    "D40": [I(kind="bmad.text_regex", params={"pattern": r"(?mi)^\s*(N/A|None)\.?\s*$", "min": 0, "max": 0}, target="spec", stage="step02")],
    "D17": [I(kind="no_template_residue", params={"patterns": PLACEHOLDERS}, target="spec", stage="step02")],
    "D31": [I(kind="bmad.text_regex", params={"pattern": r"<!--", "min": 0, "max": 0}, target="spec", stage="step02")],
    "D8": [I(kind="item_format", params={"section": "Code Map", "pattern": r"^\s*[-*]\s+`[^`]+`\s+--\s+\S", "of_pattern": r"^\s*[-*]\s+", "min": 1}, target="spec", stage="step02")],
    "D9": [I(kind="cross_ref", params={"left": {"ids": {"artifact": "spec", "section": "Code Map", "pattern": r"`([^`\s()]+/[^`\s()]+|[^`\s()/]+\.[a-z]{1,5})`", "group": 1}}, "right": {"fact": "base_paths"}, "relation": "subset", "normalize": "path"}, target="spec", stage="step02", fidelity="narrower", fidelity_note="backticked tokens that look like paths (a slash or a short extension); symbols are not paths")],
    "D44": [I(kind="section_present", params={"heading": "Tasks & Acceptance", "level": 2}, target="spec", stage="step02", suffix="section"),
            I(kind="label_present", params={"section": "Tasks & Acceptance", "label": "Execution"}, target="spec", stage="step02", suffix="execution"),
            I(kind="label_present", params={"section": "Tasks & Acceptance", "label": "Acceptance Criteria"}, target="spec", stage="step02", suffix="acceptance")],
    "D13": [I(kind="item_format", params={"section": "Tasks & Acceptance", "pattern": r"^\s*[-*]\s+`[^`]+`\s+--\s+.+\s+--\s+.+", "of_pattern": r"^\s*[-*]\s+`", "min": 1}, target="spec", stage="step02")],
    "D15": [I(kind="item_format", params={"section": "Tasks & Acceptance", "pattern": r"(?i)^\s*[-*]\s+given\b.*\bwhen\b.*\bthen\b", "of_pattern": r"^\s*[-*]\s+(?!`)\S", "min": 1}, target="spec", stage="step02")],
    "D42": [I(kind="bmad.text_regex", params={"section": "Tasks & Acceptance", "pattern": r"(?i)\b(unit[- ]?test|test(s|ing)?)\b", "min": 1, "requires_section": "I/O & Edge-Case Matrix"}, target="spec", stage="step02", fidelity="narrower", fidelity_note="a task line mentions testing when a matrix exists; which rows it covers is not checked")],
    "D45": [I(kind="section_present", params={"heading": "Spec Change Log", "level": 2}, target="spec", stage="step02", suffix="change_log"),
            I(kind="section_present", params={"heading": "Review Triage Log", "level": 2}, target="spec", stage="step02", suffix="triage_log")],
    "D47": [I(kind="bmad.text_regex", params={"section": "Verification", "pattern": r"^\s*[-*]\s+`[^`]+`\s+--\s+expected:", "min": 1, "optional_section": True}, target="spec", stage="step02")],
    "B5": [I(kind="bmad.text_regex", params={"pattern": r"\]\(/", "min": 0, "max": 0}, target="spec", stage="step03", fidelity="narrower", fidelity_note="no markdown link with an absolute path")],
    "B13": [I(kind="bmad.block_unchanged", params={"open": "<intent-contract>", "close": "</intent-contract>"}, target="spec", stage="global")],
    "B14": [I(kind="bmad.append_only", params={"sections": ["Spec Change Log", "Review Triage Log"]}, target="spec", stage="global")],
    # ---- the diff file ----
    "E14b": [I(kind="artifact_exists", params={"artifact": "diff"}, target="diff", stage="step03")],
    "E14a": [I(kind="bmad.diff_file", params={}, target="diff", stage="step03")],
    # ---- review: triage log and result ----
    "G76": [I(kind="item_format", params={"section": "Review Triage Log", "pattern": r"^###\s+\S.*[—–-]+\s*Review pass", "of_pattern": r"^###", "min": 1}, target="spec", stage="step04", suffix="heading"),
            I(kind="item_format", params={"section": "Review Triage Log", "pattern": VERDICTS, "of_pattern": r"^\s*-\s+verdicts:", "min": 1}, target="spec", stage="step04", suffix="verdicts")],
    "G77": [I(kind="item_format", params={"section": "Review Triage Log", "pattern": ROW, "of_pattern": r"^\s*-\s+`\[", "min": 1}, target="spec", stage="step04")],
    "G78": [I(kind="item_format", params={"section": "Review Triage Log", "pattern": r"^###\s+\d{4}-\d{2}-\d{2}\b", "of_pattern": r"^###", "min": 1}, target="spec", stage="step04", fidelity="narrower", fidelity_note="an ISO date in the heading; equality with the system date is not checked")],
    "G80": [I(kind="bmad.triage_totals", params={"rule": "totals"}, target="spec", stage="step04")],
    "G66": [I(kind="bmad.triage_totals", params={"rule": "false_reject"}, target="spec", stage="step04")],
    "H1": [I(kind="section_present", params={"heading": "Auto Run Result", "level": 2}, target="spec", stage="step04", suffix="section"),
           I(kind="field_filled", params={"section": "Auto Run Result"}, target="spec", stage="step04", suffix="filled", fidelity="narrower", fidelity_note="the section has content; the six parts are not told apart")],
    "H2": [I(kind="cross_ref", params={"left": {"ids": {"artifact": "spec", "section": "Auto Run Result", "pattern": r"`([^`\s]+\.[A-Za-z0-9_]+)`", "group": 1}}, "right": {"fact": "diff_paths"}, "relation": "superset", "normalize": "path"}, target="spec", stage="step04", fidelity="narrower", fidelity_note="every file of the final diff is named (backticked) under Auto Run Result")],
    "H11": [I(kind="artifact_exists", params={"artifact": "result"}, target="result", stage="step04", applies_when={"not": {"artifact_exists": "spec"}})],
    "H12": [I(kind="frontmatter", params={"keys": ["status"], "exact": False}, target="result", stage="step04", applies_when={"not": {"artifact_exists": "spec"}})],
    # ---- sub-agents ----
    "I1": [I(kind="bmad.task_calls", params={"rule": "launched", "min": 1}, target="run", stage="global")],
    "I3": [I(kind="bmad.task_calls", params={"rule": "same_turn", "min": 4, "window": "stage:step04"}, target="run", stage="step04")],
    "G11": [I(kind="bmad.task_calls", params={"rule": "lenses", "window": "stage:step04"}, target="run", stage="step04")],
    "G3": [I(kind="bmad.task_calls", params={"rule": "prompt_pattern", "lens": "review", "pattern": DIFF_PATH, "forbid": r"^(diff --git |@@ )", "window": "stage:step04"}, target="run", stage="step04")],
    "G4": [I(kind="bmad.task_calls", params={"rule": "prompt_pattern", "lens": "edge", "pattern": r"claims_file[^\n]*spec-[^\s`]+\.md", "window": "stage:step04"}, target="run", stage="step04", suffix="edge_has_claims"),
           I(kind="bmad.task_calls", params={"rule": "prompt_pattern", "lens": ["blind", "gap", "intent"], "pattern": r".", "forbid": r"implementation-artifacts/spec-[^\s`]+\.md", "window": "stage:step04"}, target="run", stage="step04", suffix="others_without_claims")],
    "G86a": [I(kind="bmad.task_calls", params={"rule": "resume_for_patch", "window": "stage:step04"}, target="run", stage="step04")],
    "G86b": [I(kind="bmad.task_calls", params={"rule": "resume_prompt", "window": "stage:step04"}, target="run", stage="step04")],
    # ---- lens outputs (the sub-agents' final messages) ----
    "G15": [I(kind="bmad.lens_output", params={"lens": "blind", "rule": "pattern", "pattern": r"N\s*=\s*min\s*\(", "window": "stage:step04"}, target="run", stage="step04")],
    "G16": [I(kind="bmad.lens_output", params={"lens": ["blind", "edge", "gap"], "rule": "no_pattern", "pattern": r"(?i)\b(severity|priority|ranking|confidence)\s*[:=]", "window": "stage:step04"}, target="run", stage="step04", fidelity="narrower", fidelity_note="no severity/priority/ranking/confidence label in the three lenses' output; the deletion check's own confidence field is JSON")],
    "G17": [I(kind="bmad.lens_output", params={"lens": "blind", "rule": "pattern", "pattern": r"(?mi)^\s*[-*]\s+\S|content is empty", "window": "stage:step04"}, target="run", stage="step04")],
    "G29": [I(kind="bmad.lens_output", params={"lens": "edge", "rule": "json_array", "window": "stage:step04"}, target="run", stage="step04")],
    "G30": [I(kind="bmad.lens_output", params={"lens": "edge", "rule": "json_keys", "keys": ["location", "trigger_condition", "guard_snippet", "potential_consequence"], "optional": ["kind", "confidence"], "window": "stage:step04"}, target="run", stage="step04")],
    "G33": [I(kind="bmad.lens_output", params={"lens": "edge", "rule": "json_keys", "keys": ["location", "trigger_condition", "guard_snippet", "potential_consequence", "kind", "confidence"], "where": {"kind": "deletion"}, "window": "stage:step04"}, target="run", stage="step04")],
    "G37": [I(kind="bmad.lens_output", params={"lens": "edge", "rule": "json_keys", "keys": ["location", "trigger_condition", "guard_snippet", "potential_consequence", "kind", "confidence"], "where": {"kind": "claim"}, "window": "stage:step04"}, target="run", stage="step04")],
    "G49": [I(kind="bmad.lens_output", params={"lens": "gap", "rule": "pattern", "pattern": r"(?m)^###\s+\S|No verification gaps found\.", "window": "stage:step04"}, target="run", stage="step04")],
    "G50": [I(kind="bmad.lens_output", params={"lens": "gap", "rule": "pattern", "pattern": r"(?im)^\W*Disposition\W*\s*(patch|defer)\b", "when": r"(?m)^###\s+\S", "window": "stage:step04"}, target="run", stage="step04")],
    "G52": [I(kind="bmad.lens_output", params={"lens": "gap", "rule": "nonempty", "window": "stage:step04"}, target="run", stage="step04", fidelity="narrower", fidelity_note="a non-empty answer; the exact sentence is judged by G49")],
    # ---- recorded commands ----
    "F1": [I(kind="cross_ref", params={"left": {"ids": {"artifact": "spec", "section": "Verification", "pattern": r"^\s*[-*]\s+`([^`]+)`\s+--", "group": 1}}, "right": {"fact": "run_commands", "window": "stage:step03"}, "relation": "subset", "normalize": "command"}, target="spec", stage="step03", fidelity="narrower", fidelity_note="each recorded command ran in step 3; manual checks are not judged")],
}
ITEMS["E11"] = [I(kind="bmad.task_calls", params={"rule": "launched", "min": 1, "pattern": r"implement it", "window": "stage:step03"}, target="run", stage="step03", fidelity="narrower", fidelity_note="the implementation hand-off was launched in step 3; waiting is enforced by the blocking tool")]

# Why a scored rule has no implemented item yet (rule -> class, note). Anything else unlisted: candidate.
UNIMPLEMENTED_NOTE = {
    "A5": ("duplicate", "absolute paths are the reads A4/A14 check"),
    "A11": ("duplicate", "the order chain of A10"),
    "B1": ("candidate", "language detection of the artifacts"),
    "B2": ("candidate", "language detection of the messages"),
    "B4": ("duplicate", "E1 checks the recorded revision"),
    "B6": ("vague", "path notation in conversation text"),
    "C31": ("candidate", "status in-progress before the first code edit: needs the replayed spec at that step"),
    "C32": ("candidate", "status in-review before the review: needs the replayed spec at that step"),
    "C34": ("candidate", "done only on a normal completion: needs the blocking-condition record"),
    "D3": ("vague", "reading the code oneself for narrow tasks"),
    "D4": ("vague", "whether an exploration was deep enough to delegate is a judgement; a narrow task is read directly"),
    "D29": ("vague", "an aim of 900-1600 tokens, not a bound; token counts are tokenizer-specific"),
    "D11": ("duplicate", "C29 checks the spec exists"),
    "D22": ("candidate", "oversized warning when over 1600 tokens"),
    "D26": ("candidate", "status ready-for-dev after the gate: needs the replayed spec at that step"),
    "D28": ("candidate", "the recorded blocking condition when the gate fails twice"),
    "D34": ("vague", "sentence count of Problem and Approach"),
    "E2": ("candidate", "baseline_revision written before the first code edit"),
    "E7": ("candidate", "the implementer sub-agent read the spec: needs the sub-agent run"),
    "F2": ("candidate", "the recorded blocking condition on verification failure"),
    "F3": ("duplicate", "F11 checks the diff rewritten after the last change"),
    "F5": ("candidate", "matrix rows covered by tests that ran and passed"),
    "F6": ("vague", "never editing a test expectation to match the code"),
    "F8": ("candidate", "the recorded blocking condition on matrix audit failure"),
    "F9": ("candidate", "verification re-run after a patch: needs the patch event"),
    "F10": ("candidate", "the recorded blocking condition on patch verification failure"),
    "F12": ("candidate", "the patch sub-agent ran only covering tests: needs the sub-agent run"),
    "G6": ("candidate", "the intent lens prompt carries the task text verbatim: needs the task text"),
    "G8": ("duplicate", "I3 checks the lenses share one turn"),
    "G18": ("candidate", "the edge lens read its instruction file: needs the sub-agent run"),
    "G19": ("candidate", "claims file read only at the claims check: needs the sub-agent run"),
    "G20": ("candidate", "the lens read the diff file: needs the sub-agent run"),
    "G22": ("vague", "what the edge lens inspected"),
    "G24": ("candidate", "the edge lens steps in order: needs the sub-agent run"),
    "G27": ("candidate", "callee declarations read: needs the sub-agent run"),
    "G28": ("candidate", "deletion check read when code was deleted: needs the sub-agent run"),
    "G31": ("candidate", "field formats of the edge findings"),
    "G34": ("candidate", "claims file read at step 5: needs the sub-agent run"),
    "G38": ("candidate", "the gap lens read its instruction file: needs the sub-agent run"),
    "G40": ("candidate", "the gap lens read the tests it cites: needs the sub-agent run"),
    "G41": ("candidate", "repository search before claiming no test: needs the sub-agent run"),
    "G51": ("candidate", "Other findings as bullets"),
    "G53": ("candidate", "the gap lens stops on unreadable content"),
    "G56": ("candidate", "verdicts after every layer reported"),
    "G58": ("candidate", "carried rows on a loopback"),
    "G60": ("vague", "verification of each finding beyond the changed lines"),
    "G62": ("duplicate", "G77 checks the verdict set"),
    "G65": ("candidate", "triage total equals the lenses' finding count: needs finding counting per lens"),
    "G71": ("duplicate", "G77 checks the route set"),
    "G79": ("candidate", "rows in layer order"),
    "G81": ("candidate", "cascade order of the routes"),
    "G82": ("candidate", "review_loop_iteration equals the loopback count"),
    "G83": ("candidate", "the recorded blocking condition after five loopbacks"),
    "G85b": ("candidate", "code reverted before re-derivation"),
    "G85c": ("candidate", "the change log read before amending"),
    "G85d": ("candidate", "change-log entry parts"),
    "G85e": ("candidate", "triage rows name the amendment"),
    "G85f": ("candidate", "step 3 re-read on a loopback"),
    "G86c": ("candidate", "patches applied by the orchestrator when resume fails"),
    "G86d": ("candidate", "patched rows name the fix"),
    "G87b": ("candidate", "existing deferred items preserved"),
    "G87c": ("candidate", "block scalars in deferred items"),
    "G87d": ("candidate", "deferred item fields"),
    "G87e": ("candidate", "frontmatter re-parsed after deferring"),
    "H3": ("candidate", "Auto Run Result counts equal the triage rows"),
    "H4": ("candidate", "follow-up recommendation computed from the patched verdicts"),
    "H5": ("duplicate", "B10 checks the field type; H4 holds the computation"),
    "H6": ("candidate", "recorded verification equals the executed commands"),
    "H14": ("candidate", "nothing after the final write"),
    "H15": ("candidate", "the run ends through HALT"),
    "I2": ("display", "the tool is present: the HALT never fires"),
}


def _decided_rows() -> list[tuple]:
    """(id, stage, measure, template, layer, fate, text) of every scored rule, from decided_layers.py."""
    ns: dict = {}
    src = DECIDED.read_text()
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(src, str(DECIDED), "exec"), ns)  # noqa: S102 -- the study's own script
    return ns["rows"]


def _catalogue() -> dict:
    return yaml.safe_load(TEMPLATES.read_text())["templates"]


def _texts() -> dict[str, list[str]]:
    return {sid: (WF / path).read_text(encoding="utf-8").splitlines() for sid, (path, _, _) in DOCS.items()}


def _parse_ref(ref: str) -> tuple[str, tuple[int, int]]:
    doc, _, rng = ref.partition(":")
    a, _, b = rng.partition("-")
    try:
        lo = int(a)
        hi = int(b) if b else lo
    except ValueError:
        lo, hi = 1, 1
    return doc, (lo, hi)


# The port's token substitutions, applied to an upstream quote before anchoring it in the ported text.
QUOTE_SUBS = [
    (r"\[\[bmad-snapshot:workflow\.md\]\]", f"{CONTAINER}/core-workflow.md"),
    (r"\[\[bmad-snapshot:(step-0\d[^\]]*\.md)\]\]", CONTAINER + r"/stages/\1"),
    (r"\[\[bmad-snapshot:([^\]]+\.md)\]\]", CONTAINER + r"/\1"),
    (r"\{\{\.implementation_artifacts\}\}", f"{ARTIFACT_ROOT}/implementation-artifacts"),
    (r"\{skill-root\}", CONTAINER),
    (r"\{project-root\}", "/testbed"),
]
# Rules whose upstream sentence the port rewrote: rule -> (doc, quote in the ported text).
ANCHOR_OVERRIDE = {
    "A2": ("INS", "Your very first action, ahead of any command in the repository, is to read"),
    "A4": ("CW", "Follow the step files in order. Read one step fully, execute it, then load the next step only when directed"),
    "A14": ("CW", "Follow the step files in order. Read one step fully, execute it, then load the next step only when directed"),
    "A5": ("CW", "Every operational cross-file reference in this workflow is an absolute path under"),
    "B1": ("S1", "Write files in English"),
    "B2": ("CW", "Write documents in English"),
    "B11": ("ST", "`/testbed/`-prefixed paths to project-wide standards/docs"),
    "C13": ("S1", "List files in `/tmp/bmad/implementation-artifacts/`"),
    "C29": ("S1", "Set `spec_file` = `/tmp/bmad/implementation-artifacts/spec-{slug}.md`"),
    "C34": ("S4", "Set `{spec_file}` frontmatter `status: done`"),
    "D6": ("S2", "Read `/bmad-build-auto/spec-template.md` fully"),
    "D23": ("S2", "Re-read `/bmad-build-auto/core-workflow.md`, then re-read `{spec_file}` from disk"),
    "D26": ("S2", "set `{spec_file}` frontmatter status to `ready-for-dev` and continue to step 3"),
    "D28": ("S2", "repair it once, then re-read it from disk and verify again"),
    "E14b": ("S3", "to `{diff_file}` (`/tmp/bmad/diff/{slug}.diff`"),
    "F2": ("S3", "If verification fails and the failure cannot be fixed, set `{spec_file}` frontmatter `status: blocked`"),
    "F8": ("S3", "If the audit cannot otherwise be satisfied, set `{spec_file}` frontmatter `status: blocked`"),
    "F10": ("S4", "if verification fails and the failure cannot be fixed, set `{spec_file}` frontmatter `status: blocked`"),
    "G18": ("S4", "Read `/bmad-build-auto/review-prompts/edge-case-hunter.md` completely and follow it"),
    "G38": ("S4", "Read `/bmad-build-auto/review-prompts/verification-gap.md` completely and follow it"),
    "G77": ("S4", "`[verdict]` `[bad_spec|patch|defer|reject]` <finding summary>"),
    "G81": ("S4", "If bad_spec exists, lower entries are moot since code will be re-derived"),
    "G83": ("S4", "If it exceeds 5, append the triage-log entry for this pass, set `{spec_file}` frontmatter `status: blocked`"),
    "G85f": ("S4", "Read fully and follow `/bmad-build-auto/stages/step-03-implement.md` to re-derive the code"),
    "G86a": ("S4", "Re-engage the step-03 implementation subagent — the same one, addressed by the name or id its launch returned (a `task` call"),
    "H4": ("S4", "`true` if any patched entry was `high`, or if two or more `medium` entries were patched"),
    "H11": ("CW", "create `/tmp/bmad/implementation-artifacts/bmad-build-auto-result-<slug-or-timestamp>.md`"),
    "H14": ("CW", "Stop the workflow. Nothing follows a HALT except ending the session"),
    "I2": ("CW", "Using subagents when instructed is mandatory"),
    "G28": ("EH", "If the diff removed or replaced meaningful code (ignore pure renames and whitespace): load `/bmad-build-auto/references/deletion-check.md` and follow it"),
}


def _sources(rule: dict, texts: dict[str, list[str]]) -> tuple[list[dict], str]:
    """The rule's quote re-anchored in the ported documents; (sources, note)."""
    quote = rule.get("quote") or ""
    if isinstance(quote, list):
        quote = " ... ".join(map(str, quote))
    quote = str(quote).strip()
    for pat, rep in QUOTE_SUBS:
        quote = re.sub(pat, rep, quote)
    refs = [str(r) for r in (rule.get("source") or [])]
    out, note = [], ""
    ov = ANCHOR_OVERRIDE.get(rule["id"])
    if ov is not None:
        got = anchor(texts[ov[0]], ov[1], (1, 1))
        if got is None:
            raise SystemExit(f"{rule['id']}: override quote not found in {ov[0]}: {ov[1][:60]!r}")
        return [{"doc": ov[0], "lines": list(got), "quote": ov[1]}], ""
    for ref in refs:
        up, hint = _parse_ref(ref)
        doc = DOC_MAP.get(up, up)
        order = ([doc] if doc else []) + [d for d in ("S3", "S4", "CW", "S1", "S2", "ST", "EH", "VG", "CC", "DC") if d != doc]
        got = None
        for d in order:
            if d not in texts:
                continue
            got = anchor(texts[d], quote, hint) if quote else None
            if got is not None:
                out.append({"doc": d, "lines": list(got), "quote": quote})
                break
        if got is not None:
            break
    if not out:
        fallback = DOC_MAP.get(_parse_ref(refs[0])[0], _parse_ref(refs[0])[0]) if refs else "CW"
        if fallback not in texts:
            fallback = "CW"
        lines = texts[fallback]
        out.append({"doc": fallback, "lines": [1, max(1, len(lines))], "quote": quote[:200]})
        note = f"quote not anchored in the port (upstream {', '.join(refs) or '?'})"
    return out, note


def _availability(kind: str) -> list[str]:
    if kind in TRACE_KINDS:
        return ["trace"]
    if kind in BOTH_KINDS:
        return ["trace", "sandbox_file"]
    return ["sandbox_file"]


def _cls(kind: str) -> str:
    if kind in EVIDENCE_KINDS:
        return "evidence"
    if kind in STRUCTURE_KINDS:
        return "structure"
    return "content"


def build() -> tuple[dict, dict, dict]:
    rules = {r["id"]: r for r in yaml.safe_load(RULES.read_text())["rules"]}
    rows = _decided_rows()
    cat = _catalogue()
    texts = _texts()
    rubric: dict = {
        "schema": "wfrubric/1",
        "workflow": WORKFLOW,
        "generated": {"tool": "bmad_build_auto.reward.build", "at": dt.date.today().isoformat(), "kinds": "registry+plugin", "stage_model": "fixed", "rules": str(RULES.relative_to(WF)), "decisions": "workflows/if/scripts/bmad/decided_layers.py"},
        "sources": [],
        "roots": {"artifact": ARTIFACT_ROOT, "code": "{WORKDIR}"},
        "vars": {
            "SPECFILE": {"under": "{artifact}/implementation-artifacts", "regex": r"spec-[^/]+\.md", "bind": "single"},
            "DIFFFILE": {"under": "{artifact}/diff", "regex": r"[^/]+\.diff", "bind": "single"},
            "RESULTFILE": {"under": "{artifact}/implementation-artifacts", "regex": r"bmad-build-auto-result-[^/]+\.md", "bind": "single"},
        },
        "stages": [
            {"id": "step01", "doc": "S1", "artifacts": []},
            {"id": "step02", "doc": "S2", "artifacts": ["spec"], "order_artifact": "spec"},
            {"id": "step03", "doc": "S3", "artifacts": ["diff"], "order_artifact": "diff", "requires": ["spec"]},
            {"id": "step04", "doc": "S4", "artifacts": [], "requires": ["spec", "diff"]},
        ],
        "artifacts": {
            "spec": {"locations": ["{artifact}/implementation-artifacts/{SPECFILE}"], "exclusive": False, "template": "ST", "write_event": "last_in_window", "optional": False, "kind": "markdown"},
            "diff": {"locations": ["{artifact}/diff/{DIFFFILE}"], "exclusive": False, "template": None, "write_event": "last_in_window", "optional": False, "kind": "text"},
            "result": {"locations": ["{artifact}/implementation-artifacts/{RESULTFILE}"], "exclusive": False, "template": None, "write_event": "last_in_window", "optional": True, "kind": "markdown"},
        },
        "items": [],
        "scoring": {"item_weight": {"must": 1.0, "should": 0.25}, "stage": {"formula": "sigma_kappa"}, "substantive_threshold": 0.5, "windows": "reads", "next_read": "after_start", "signals": ["order", "process", "stage:*"], "process_scale": "stage_mean", "compliance": "mean"},
        "conflicts": [],
        "appendix": {"note": "evaluation workflow of the SDLC instruction-following study; judge rules are unimplemented + log_only until a judge endpoint is wired"},
    }
    sp_text = (WF / "system-prompt.j2").read_text(encoding="utf-8")
    for sid, (path, role, cpath) in DOCS.items():
        src = {"id": sid, "path": path, "role": role, "sha256": hashlib.sha256((WF / path).read_bytes()).hexdigest()}
        if cpath:
            src["container_path"] = cpath
        if sid == "SP":
            src["sections"] = {tag: ("workflow" if tag == "PROBLEM_SOLVING_WORKFLOW" else "harness_generic") for tag in re.findall(r"^<([A-Z_]+)>$", sp_text, re.M)}
        rubric["sources"].append(src)

    constraints: list[dict] = []
    seen_ids: set[str] = set()
    for (rid, stage, measure, template, layer, fate, text) in rows:
        rule = rules[rid]
        sources, src_note = _sources(rule, texts)
        stage_id = STAGE_OF.get(str(stage), "global")
        specs = ITEMS.get(rid) if measure == "code" else None
        default_layer = ((cat.get(template) or {}).get("eval") or {}).get("layer")
        upstream_refs = ", ".join(str(r) for r in (rule.get("source") or []))
        if specs:
            for k, spec in enumerate(specs):
                kind = spec["kind"]
                st = spec.get("stage", stage_id)
                target = spec.get("target", "run")
                kname = kind.replace(".", "_")
                suffix = spec.get("suffix")
                iid = P + ".".join(x for x in (st, target, kname, rid.lower(), suffix) if x)
                assert iid not in seen_ids, iid
                seen_ids.add(iid)
                req = spec.get("requirement", "must")
                note = "; ".join(x for x in (spec.get("note", ""), src_note) if x)
                item = {
                    "id": iid,
                    "scope": "specific" if kind.startswith("bmad.") else "common",
                    "class": _cls(kind),
                    "stage": st,
                    "target": {"type": "action" if target == "run" else "artifact", "ref": target, "state": "final"},
                    "check": {"kind": kind, "params": spec.get("params", {})},
                    "requirement": req,
                    "modality_evidence": f"rules.yaml {rid} ({upstream_refs}); decided {fate}, {template} {layer}",
                    "none_allowed": "-",
                    "applies_when": spec.get("applies_when"),
                    "weight": 1.0,
                    "gate": None,
                    "availability": _availability(kind),
                    "sources": sources,
                    "impl_refs": [],
                    "derived_by": "manual",
                    "template": "",
                    "log_only": bool(spec.get("log_only", False)),
                    "note": "; ".join(x for x in (f"study template {template} ({layer})", note) if x),
                }
                rubric["items"].append(item)
                c = {
                    "id": iid,
                    "template": template,
                    "status": "implemented",
                    "requirement": req,
                    "rule": f"{text} ({upstream_refs})",
                    "source": sources[0],
                    "fidelity": spec.get("fidelity", "faithful"),
                }
                if c["fidelity"] != "faithful":
                    c["fidelity_note"] = spec.get("fidelity_note", "")
                ev = {"layer": layer, "requirement": req}
                if layer != default_layer:
                    ev["layer_reason"] = f"decided_layers.py ({fate}): {template} has {'no catalogue default' if default_layer is None else 'default ' + default_layer}; see porting/03-decisions.md"
                c["eval"] = ev
                constraints.append(c)
        else:
            cls_, why = UNIMPLEMENTED_NOTE.get(rid, ("candidate", "no implemented check yet"))
            if measure == "judge":
                cls_, why = "candidate", "judge rule (LLM judgement); log_only until a judge endpoint is wired"
            iid = P + ".".join((stage_id, "run", "unimplemented", rid.lower()))
            assert iid not in seen_ids, iid
            seen_ids.add(iid)
            rubric["items"].append({
                "id": iid,
                "scope": "specific",
                "class": "content",
                "stage": stage_id,
                "target": {"type": "action", "ref": "unimplemented", "state": "final"},
                "check": {"kind": "unimplemented", "params": {}},
                "requirement": "should",
                "modality_evidence": f"rules.yaml {rid} ({upstream_refs}); decided {fate}, {template} {layer}; measure {measure}",
                "none_allowed": "-",
                "applies_when": None,
                "weight": 0.0,
                "gate": None,
                "availability": ["sandbox_file"],
                "sources": sources,
                "impl_refs": [],
                "derived_by": "manual",
                "template": "",
                "log_only": measure == "judge",
                "note": "; ".join(x for x in (f"{measure}: {why}", src_note) if x),
            })
            constraints.append({
                "id": iid,
                "template": template,
                "status": "unimplemented",
                "requirement": "should",
                "rule": f"{text} ({upstream_refs})",
                "source": sources[0],
                "class": cls_,
                "class_note": why,
                "eval": {"layer": layer, "requirement": "must"},
            })
    cons_doc = {
        "schema": "sdlc_if.constraints/1",
        "workflow": WORKFLOW,
        "role": "eval",
        "templates": "../../sdlc_if/templates.yaml",
        "rubric": "reward/rubric.yaml",
        "constraints": constraints,
    }
    layers = {}
    for it in rubric["items"]:
        if it["check"]["kind"] == "unimplemented":
            continue
        c = next(c for c in constraints if c["id"] == it["id"])
        layers[it["id"]] = {"layer": c["eval"]["layer"], "requirement": c["eval"]["requirement"], "template": c["template"]}
    return rubric, cons_doc, layers


def _dump(obj) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=1 << 16)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    rubric, cons, layers = build()
    rubric_text = _dump(rubric)
    cons_text = "# Generated by reward/build.py from porting/rules.yaml + decided_layers.py + the ITEMS table -- do not edit.\n" + _dump(cons)
    sha = hashlib.sha256(rubric_text.encode()).hexdigest()
    layers_text = "# Generated by reward/build.py -- do not edit; see its docstring.\n" + _dump({"rubric_sha256": sha, "source": "constraints.yaml", "items": layers})
    want = ((RUBRIC, rubric_text), (CONSTRAINTS, cons_text), (LAYERS, layers_text))
    if a.check:
        stale = [p.name for p, t in want if not p.is_file() or p.read_text() != t]
        if stale:
            print(f"stale: {stale}; run the build", file=sys.stderr)
            return 1
        return 0
    for p, t in want:
        p.write_text(t)
    assert rubric_sha256(RUBRIC) == sha
    n_impl = sum(1 for it in rubric["items"] if it["check"]["kind"] != "unimplemented")
    print(f"wrote rubric.yaml ({len(rubric['items'])} items, {n_impl} implemented), constraints.yaml ({len(cons['constraints'])}), layers.yaml ({len(layers)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
