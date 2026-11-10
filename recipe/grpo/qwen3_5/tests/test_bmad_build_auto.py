"""bmad_build_auto: the documents are what build.py makes of BMAD-METHOD's bmad-build-auto skill, the embedded
customize.toml values are the checkout's, the documents point at each other, the decided changes are in the
text (D-1 no commit, D-2 intent HALTs gone and failure HALTs recorded, D-5 paths outside the repo, D-7 the task
tool), the harness picks the workflow up, and the hand-written text is this workflow's own.

    pytest recipe/grpo/qwen3_5/tests/test_bmad_build_auto.py
    BMAD_METHOD_DIR=/path/to/BMAD-METHOD pytest ...   # the drift checks; default ../BMAD-METHOD beside the repo
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

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.bmad_build_auto import build  # noqa: E402

NAME = "bmad_build_auto"
SPEC = workflows.WORKFLOWS[NAME]
DOCS = SPEC.docs_dir
UPSTREAM = Path(os.environ.get("BMAD_METHOD_DIR", "/vast-ib/MMI/home/kyuminkim/project/if/workflows/BMAD-METHOD"))
if not UPSTREAM.is_dir():
    UPSTREAM = REPO.parent / "BMAD-METHOD"
needs_upstream = pytest.mark.skipif(not (UPSTREAM / build.SKILL_DIR).is_dir(), reason=f"no BMAD-METHOD checkout at {UPSTREAM}")
SECTION = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)
ENTRY = "/bmad-build-auto/core-workflow.md"


def _docs() -> dict[str, str]:
    return {p.relative_to(DOCS).as_posix(): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


def _upstream(key: str) -> str:
    return (UPSTREAM / build.SOURCES[key][0]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- build


@needs_upstream
def test_committed_docs_match_a_fresh_build():
    for name, text in build.build(UPSTREAM).items():
        assert (build.OUT_DIR / name).read_text(encoding="utf-8") == text, f"{name} drifted; rerun build.py"


@needs_upstream
def test_build_check_passes():
    assert build.main(["--upstream", str(UPSTREAM), "--check"]) == 0


@needs_upstream
def test_embedded_customization_is_the_checkouts():
    build.check_customization(UPSTREAM)  # raises on a difference
    assert build.LAYER_IDS == ("blind-hunter", "edge-case-hunter", "verification-gap", "intent-alignment")


@needs_upstream
def test_reworded_upstream_fails_the_build():
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("step02", _upstream("step02").replace("5. If intent gaps exist", "5. When intent gaps exist"))
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("step04", _upstream("step04").replace("Commit any reviewed-diff files", "Commit every reviewed-diff file"))


@needs_upstream
def test_upstream_wording_left_behind_fails_the_build():
    text = _upstream("step03").replace("### Verify\n", "### Verify\n\nIf unsure, HALT with blocking condition `unclear intent`.\n")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("step03", text)


@needs_upstream
def test_missing_upstream_section_fails_the_build():
    with pytest.raises(ValueError, match="sections not found"):
        build.convert("workflow", _upstream("workflow").replace("## On Activation", "## Activation"))


def test_every_edit_is_tagged_and_cites_its_gap_or_decision():
    for e in (*build.SECTIONS, *build.EDITS):
        assert e.tag in {"env", "semantic"}, e
        assert re.match(r"(G\d+|D-\d+)\b", e.note), e.note


def test_no_stray_files_beside_the_build_outputs():
    assert build._strays() == []
    assert set(_docs()) == build.expected_outputs()
    assert len(_docs()) == 10


def test_list_prints_every_tag_and_the_inlined_toml(capsys):
    assert build.main(["--list"]) == 0
    out = capsys.readouterr().out
    for label in ("[env]", "[semantic]", "[substitutions]", "[inlined]", "implementation_handoff -> step-03", "intent-alignment"):
        assert label in out, label


# ---------------------------------------------------------------------- documents


def test_documents_point_only_at_documents_that_exist():
    docs = _docs()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/bmad-build-auto/[\w./-]+\.md", text):
            assert ref.removeprefix("/bmad-build-auto/") in docs, f"{name} points at missing {ref}"
    entry = docs["core-workflow.md"]
    for stage in build.STAGE_DOCS.values():
        assert stage in entry
    assert "/bmad-build-auto/spec-template.md" in docs["stages/step-02-plan.md"]
    for prompt in ("edge-case-hunter", "verification-gap"):
        assert f"/bmad-build-auto/review-prompts/{prompt}.md" in docs["stages/step-04-review.md"]
    for ref in ("claims-check", "deletion-check"):
        assert f"/bmad-build-auto/references/{ref}.md" in docs["review-prompts/edge-case-hunter.md"]


def test_removed_upstream_wording_is_gone():
    for name, text in _docs().items():
        for bad in build.FORBIDDEN:
            assert bad not in text, (name, bad)


def test_artifacts_live_outside_the_repository():
    docs = _docs()
    for name, text in docs.items():
        assert "/testbed/_bmad" not in text and "_bmad-output" not in text, name
        for path in re.findall(r"/tmp/bmad[\w./<>{}-]*", text):
            assert path.startswith((build.IMPLEMENTATION_ARTIFACTS, build.DIFF_DIR)) or path == build.ARTIFACTS_ROOT, (name, path)
    assert SPEC.output_dirs == (build.ARTIFACTS_ROOT,)
    step01 = docs["stages/step-01-clarify-and-route.md"]
    assert f"`spec_file` = `{build.SPEC_FILE}`" in step01 and f"`diff_file` = `{build.DIFF_FILE}`" in step01
    assert build.DIFF_FILE in docs["stages/step-03-implement.md"] and build.DIFF_FILE in docs["stages/step-04-review.md"]
    assert build.RESULT_FILE in docs["core-workflow.md"]


def test_decided_changes_are_in_the_text():
    docs = _docs()
    step01, step02, step03, step04 = (docs[f"stages/{f}"] for f in build.STEP_FILES)
    entry = docs["core-workflow.md"]
    # D-2: the intent HALTs are deleted, not replaced; the sentence before the deleted clause survives
    assert "Do not fantasize or leave open questions.\n" in step01 and "unresolved questions" not in step01
    assert "4. Warning check." in step02 and "defensible readings" not in step02
    assert "## Assumptions" not in step02 and "## Assumptions" not in docs["spec-template.md"]
    assert "intent-alignment" in step04 and "defensible readings of the intent" in step04  # the lens stays
    assert "`[bad_spec|patch|defer|reject]`" in step04 and "The first two are **this story's problem**" in step04
    # D-2 default: the five failure HALTs record status: blocked and continue
    for doc, condition in (
        (step02, "spec failed ready-for-development standard"),
        (step03, "implementation verification failed"),
        (step03, "matrix test audit failed"),
        (step04, "review repair loop exceeded 5 iterations (non-convergence)"),
        (step04, "patch verification failed"),
    ):
        i = doc.index(condition)
        assert "`status: blocked`" in doc[i - 200 : i], condition
        assert "HALT" not in doc[i - 200 : i + len(condition) + 120], condition
    assert step04.count("HALT") == 1  # only the Finalize hand-over to the HALT protocol
    # D-4: the loopback, its revert and the cap of 5 are upstream's
    assert "Revert code changes." in step04 and "If it exceeds 5" in step04 and "review_loop_iteration" in step04
    # D-1: no VCS check, no commit; the working tree is graded
    for bad in ("git add --refresh", "Commit any", "Do not push", "working copy is clean"):
        assert bad not in step01 + step04, bad
    assert "which is what gets graded" in step04 and "Do not commit, stash, reset or clean" in entry
    # D-3: the spec's unit-test task and the Verification Gap patch disposition are upstream's
    assert "include a task to unit-test its edge cases" in docs["spec-template.md"]
    assert "`patch` — name the test to add" in docs["review-prompts/verification-gap.md"]
    # D-5 / G10: language tokens -> English, {project-root} -> /testbed
    assert all("Write files in English." in d for d in (step01, step02, step03, step04))
    assert "`/testbed/`-prefixed paths" in docs["spec-template.md"]


def test_task_tool_is_described_consistently():
    docs = _docs()
    entry, step03, step04 = docs["core-workflow.md"], docs["stages/step-03-implement.md"], docs["stages/step-04-review.md"]
    for needle in ("`task` tool", "`prompt`", "`subagent_type` at `general-purpose`", "`resume`", "Task ID"):
        assert needle in entry, needle
    assert "one `task` call" in step03 and "`subagent_type` = `general-purpose`" in step03 and "`resume` set to its Task ID" in step03
    assert "four `task` calls in one assistant turn" in step04 and "`resume` = that subagent's Task ID" in step04
    for layer in build.LAYER_IDS:
        assert f"(`{layer}`)" in step04, layer
    assert step04.count("Launch a context-free subagent with this prompt:") == 3 and "Launch a subagent with this prompt:" in step04
    for bad in ("delegate", "spawn with", "ids you chose"):
        assert bad not in entry + step03 + step04, bad
    assert SPEC.runner_env == {"OPENHANDS_SDK_EXTRA_TOOLS": "task"}


# ---------------------------------------------------------------------- hand-written text


def _sentences(text: str) -> set[str]:
    flat = re.sub(r"\s+", " ", re.sub(r"[`*|#>]", " ", text)).strip().lower()
    return {s.strip() for s in re.split(r"(?<=[.!?;:])\s+", flat) if len(s.split()) >= 8}


def _hand_written(spec) -> list[str]:
    texts = [(spec.docs_dir / spec.entry_doc).read_text(encoding="utf-8")]
    if spec.instruction_file:
        texts.append(spec.instruction_file.read_text(encoding="utf-8"))
    prompt = spec.system_prompt.get("openhands-sdk")
    if prompt:
        texts.append(SECTION.search(prompt.read_text(encoding="utf-8")).group(0))
    return texts


def test_hand_written_text_is_its_own():
    ours = set().union(*(_sentences(t) for t in _hand_written(SPEC)))
    assert ours
    for other, spec in workflows.WORKFLOWS.items():
        if other == NAME:
            continue
        shared = ours & set().union(*(_sentences(t) for t in _hand_written(spec)))
        assert not shared, (other, sorted(shared)[:3])
        assert spec.instruction_file is None or spec.instruction_file.read_text(encoding="utf-8").strip() != SPEC.instruction_file.read_text(encoding="utf-8").strip()


def test_instruction_and_prompt_send_the_agent_to_the_entry_document_first():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="suffix")
    prompt = h.system_prompt_file.read_text(encoding="utf-8")
    for text in (h.instruction_text(), SECTION.search(prompt).group(0)):
        flat = re.sub(r"\s+", " ", text)
        assert ENTRY in flat
        assert "first action" in flat or "Action one" in flat
        assert "filesystem root" in flat and "not inside it" in flat
    sdk = (RECIPE / "workflows" / "aidlc_v4" / "system-prompt.j2").read_text(encoding="utf-8")
    assert SECTION.sub("", prompt) == SECTION.sub("", sdk)  # the other sections are the SDK default
    assert "task tool" in SECTION.search(prompt).group(0)


# ---------------------------------------------------------------------- harness


def test_harness_picks_up_the_documents():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="suffix")
    assert h._expected_doc_count() == len(_docs()) == 10
    assert sorted(p.name for p in h._doc_entries()) == ["core-workflow.md", "references", "review-prompts", "spec-template.md", "stages"]
    composed = h.compose_instruction("TASK")
    assert composed.startswith("TASK\n\n") and composed.rstrip().endswith("under /bmad-build-auto/stages/.")
    assert type(h.evaluation_policy).__name__ == "Evaluation"  # reward/rubric.yaml (stage 4b) registers the scorer
    assert not SPEC.sandbox_files and SPEC.setup_script is None and not SPEC.agent_image_extra
    from dataclasses import replace

    assert replace(SPEC, runner_env={}).fingerprint("openhands-sdk") != SPEC.fingerprint("openhands-sdk")
