"""The speckit_bug workflow: docs/stages is what build.py makes of spec-kit, the documents point at
each other correctly, and the harness picks the workflow up.

    pytest recipe/grpo/qwen3_5/tests/test_speckit_bug.py
    SPEC_KIT_DIR=/path/to/spec-kit pytest ...   # the drift check; default ../spec-kit beside the repo
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows import speckit_bug  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_bug import build  # noqa: E402

WF = Path(speckit_bug.__file__).resolve().parent
DOCS = WF / "docs"
SPEC_KIT = Path(os.environ.get("SPEC_KIT_DIR", REPO.parent / "spec-kit"))
UPSTREAM = SPEC_KIT / "extensions" / "bug" / "commands"
needs_spec_kit = pytest.mark.skipif(not UPSTREAM.is_dir(), reason=f"no spec-kit checkout at {SPEC_KIT}")


def _docs_text() -> dict[str, str]:
    return {str(p.relative_to(DOCS)): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


@needs_spec_kit
def test_committed_stages_match_a_fresh_build():
    built = build.build(SPEC_KIT)
    for name, text in built.items():
        assert (build.OUT_DIR / name).read_text(encoding="utf-8") == text, f"docs/stages/{name} drifted; rerun build.py"
    assert sorted(built) == sorted(p.name for p in build.OUT_DIR.glob("*.md"))


@needs_spec_kit
def test_reworded_upstream_fails_the_build():
    upstream = (UPSTREAM / "speckit.bug.fix.md").read_text(encoding="utf-8")
    reworded = upstream.replace("Do not run destructive or network-dependent suites", "Avoid destructive suites")
    assert reworded != upstream
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("fix", reworded)


@needs_spec_kit
def test_upstream_wording_left_behind_fails_the_build():
    upstream = (UPSTREAM / "speckit.bug.test.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("test", upstream.replace("## Guardrails\n", "## Guardrails\n\n- Ask the user first; ask the user.\n"))


@needs_spec_kit
def test_missing_upstream_section_fails_the_build():
    upstream = (UPSTREAM / "speckit.bug.assess.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="sections not found"):
        build.convert("assess", upstream.replace("## Safety When Fetching URLs", "## URL Safety"))


def test_every_edit_is_tagged():
    assert {s.tag for s in build.SECTIONS} | {e.tag for e in build.EDITS} <= {"env", "loop", "semantic"}


def test_documents_point_only_at_documents_that_exist():
    docs = _docs_text()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/speckit/[\w./-]+\.md", text):  # not /tmp/speckit/...
            assert ref.removeprefix("/speckit/") in docs, f"{name} points at missing {ref}"
    # every stage document is reachable from the entry document
    for stage in build.STAGE_DOCS.values():
        assert stage in docs["core-workflow.md"]


def test_reports_live_outside_the_repository_under_one_directory():
    docs = _docs_text()
    for name, text in docs.items():
        assert ".specify" not in text, name
        for path in re.findall(r"/tmp/speckit/[\w./<>-]*", text):
            assert path.startswith(build.BUG_DIR.rstrip("/")), f"{name}: {path}"
    for report in ("assessment.md", "fix.md", "fix-2.md", "fix-3.md", "test.md", "test-2.md", "test-3.md"):
        assert report in docs["core-workflow.md"]


def test_three_round_limit_is_stated_the_same_everywhere():
    docs = _docs_text()
    assert "at most three" in docs["core-workflow.md"]
    for stage in ("stages/02-fix.md", "stages/03-test.md"):
        assert "at most three" in docs[stage]
        assert "fix-3.md" in docs[stage] and "fix-4.md" not in docs[stage]
    assert "Round 3, any result" in docs["stages/03-test.md"]


def test_checks_fail_before_the_change_and_decide_the_verdict():
    docs = _docs_text()
    fix, test = docs["stages/02-fix.md"], docs["stages/03-test.md"]
    before, change = fix.index("**Before editing any code**"), fix.index("Make the code changes")
    assert before < change  # G9-5: checks and the baseline come before the code change
    assert "verbatim" in fix[before:change] and "baseline" in fix[before:change]
    assert "## Baseline: Existing Tests" in fix and "Before the change" in fix
    assert "only when all three hold" in test  # G8-2
    assert "failing before the change" in test and "baseline" in test


def test_harness_uploads_the_documents_and_swaps_the_procedure_section():
    h = OpenHandsSdkWorkflow(workflow="speckit_bug", instruction_position="prefix")
    assert h._expected_doc_count() == 4
    composed = h.compose_instruction("TASK")
    assert "/speckit/core-workflow.md" in composed and composed.endswith("\n\nTASK")
    assert h.instruction_text() != (WF.parent / "aidlc_v4" / "instruction.md").read_text(encoding="utf-8").replace("/ai-dlc", "/speckit")
    ours = h.system_prompt_file.read_text(encoding="utf-8")
    aidlc = (WF.parent / "aidlc_v4" / "system-prompt.j2").read_text(encoding="utf-8")
    section = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)
    ours_section = section.search(ours).group(0)
    assert "/speckit/core-workflow.md" in ours_section
    assert ours_section != section.search(aidlc).group(0).replace("/ai-dlc", "/speckit")  # reworded, not a path swap
    study = (WF.parent / "aidlc_v4_ifeval" / "system-prompt.j2").read_text(encoding="utf-8")
    assert section.sub("", ours) == section.sub("", study)  # the other sections: the SDLC IF study's shared prompt
    # resolve rate only until the generated rubric exists (reward/rubric.yaml), then its scorer
    assert (h.evaluation_policy is None) == (not (WF / "reward" / "rubric.yaml").is_file())
