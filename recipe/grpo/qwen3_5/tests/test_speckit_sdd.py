"""speckit_sdd: the stage documents, the shipped templates and the verbatim scripts/constitution are what
build.py makes of spec-kit, the documents point at each other and at the shipped files, the round rule
reads the same everywhere, the harness picks the workflow and its sandbox files up, and the hand-written
text is this workflow's own.

    pytest recipe/grpo/qwen3_5/tests/test_speckit_sdd.py
    SPEC_KIT_DIR=/path/to/spec-kit pytest ...   # the drift checks; default ../spec-kit beside the repo
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows._port import copy_build, copy_drift  # noqa: E402
from recipe.grpo.qwen3_5.workflows.speckit_sdd import build  # noqa: E402

NAME = "speckit_sdd"
SPEC = workflows.WORKFLOWS[NAME]
DOCS = SPEC.docs_dir
UPSTREAM = Path(os.environ.get("SPEC_KIT_DIR", REPO.parent / "spec-kit"))
needs_upstream = pytest.mark.skipif(not (UPSTREAM / "templates" / "commands").is_dir(), reason=f"no spec-kit checkout at {UPSTREAM}")
SECTION = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)


def _docs() -> dict[str, str]:
    return {p.relative_to(DOCS).as_posix(): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


def _upstream(port, key: str) -> str:
    return (UPSTREAM / port.sources[key][0]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- build


@needs_upstream
@pytest.mark.parametrize("label", ["stages", "templates"])
def test_committed_outputs_match_a_fresh_build(label):
    port = build.PORTS[label]
    for name, text in build._build(port, UPSTREAM).items():
        assert (port.out_dir / name).read_text(encoding="utf-8") == text, f"{label}: {name} drifted; rerun build.py"


@needs_upstream
@pytest.mark.parametrize("label", ["scripts", "memory"])
def test_shipped_copies_are_upstream_byte_for_byte(label):
    c = build.COPIES[label]
    assert copy_drift(c, copy_build(c, UPSTREAM)) == []
    for src, out in c.files.items():
        assert (c.out_dir / out).read_bytes() == (UPSTREAM / src).read_bytes()


def test_no_stray_files_beside_the_build_outputs():
    assert build._strays() == []
    assert sorted(p.name for p in build.OUT_DIR.iterdir()) == sorted(out for _, out in build.SOURCES.values())


def test_scripts_are_executable_and_parse():
    for out in build.SCRIPTS.files.values():
        path = build.SANDBOX / out
        assert path.stat().st_mode & 0o111, out
        subprocess.run(["bash", "-n", str(path)], check=True)
    assert not (build.SANDBOX / "memory" / "constitution.md").stat().st_mode & 0o111


@needs_upstream
def test_build_check_passes():
    assert build.main(["--upstream", str(UPSTREAM), "--check"]) == 0


@needs_upstream
def test_reworded_upstream_fails_the_build():
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("implement", _upstream(build.STAGES, "implement").replace("Halt execution if any", "Stop if any"))
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert_template("tasks", _upstream(build.TEMPLATES, "tasks").replace("Commit after each task", "Commit after every task"))


@needs_upstream
def test_upstream_wording_left_behind_fails_the_build():
    text = _upstream(build.STAGES, "plan").replace("## Key rules\n", "## Key rules\n\n- Ask the user which stack to use.\n")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("plan", text)


@needs_upstream
def test_missing_upstream_section_or_step_fails_the_build():
    with pytest.raises(ValueError, match="sections not found"):
        build.convert("specify", _upstream(build.STAGES, "specify").replace("## Completion Report", "## Completion"))
    with pytest.raises(ValueError, match="sections not found"):
        build.convert("converge", _upstream(build.STAGES, "converge").replace("### 9. Check for extension hooks", "### 9. Hooks"))


def test_every_edit_is_tagged_and_cites_its_gap():
    items = (*build.SECTIONS, *build.EDITS, *build.TEMPLATE_SECTIONS, *build.TEMPLATE_EDITS)
    for e in items:
        assert e.tag in {"env", "semantic", "loop"}, e
        assert re.match(r"(G\d+-\d+|D-\d+)\b", e.note), e.note


def test_list_covers_every_output(capsys):
    assert build.main(["--list"]) == 0
    out = capsys.readouterr().out
    for label in ("== stages", "== templates", "== scripts", "== memory", "(verbatim, +x)", "step '### 9. Check for extension hooks'"):
        assert label in out, label


# ---------------------------------------------------------------------- documents


def test_documents_point_only_at_documents_that_exist():
    docs = _docs()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/speckit-sdd/[\w./-]+\.md", text):  # not /tmp/speckit-sdd/...
            assert ref.removeprefix("/speckit-sdd/") in docs, f"{name} points at missing {ref}"
    for stage in build.STAGE_DOCS.values():
        assert stage in docs["core-workflow.md"]
    assert sorted(docs) == ["core-workflow.md", *sorted(f"stages/{out}" for _, out in build.SOURCES.values())]


def test_shipped_files_the_documents_name_exist():
    texts = [*_docs().values(), *(p.read_text(encoding="utf-8") for p in (build.SANDBOX / "templates").glob("*.md"))]
    named = {m for t in texts for m in re.findall(r"/tmp/speckit-sdd/\.specify/(?:scripts|templates|memory)/[\w./-]+", t)}
    assert named, "the documents name no shipped file"
    for path in named:
        rel = path.removeprefix("/tmp/speckit-sdd/.specify/").rstrip(".")
        if rel.endswith("/"):
            assert (build.SANDBOX / rel).is_dir(), path
        else:
            assert (build.SANDBOX / rel).is_file(), path


def test_removed_upstream_wording_is_gone():
    for name, text in _docs().items():
        for bad in build.FORBIDDEN:
            assert bad not in text, (name, bad)
    for path in (build.SANDBOX / "templates").glob("*.md"):
        for bad in build.TEMPLATE_FORBIDDEN:
            assert bad not in path.read_text(encoding="utf-8"), (path.name, bad)


def test_artifacts_live_outside_the_repository():
    docs = _docs()
    for name, text in docs.items():
        assert "/testbed/specs" not in text and "/testbed/.specify" not in text, name
        for path in re.findall(r"/tmp/speckit-sdd/[\w./<>-]*", text):
            assert path.startswith((build.FEATURE_DIR, build.SPECIFY_DIR, build.PROJECT_ROOT + "/specs")) or path.rstrip("/.") == build.PROJECT_ROOT, (name, path)
    entry = docs["core-workflow.md"]
    for needle in (build.FEATURE_DIR, f"{build.FEATURE_DIR}/checks/", "convergence.md", "convergence-2.md", ".gitignore"):
        assert needle in entry, needle
    # the outputs the harness collects are the feature tree and feature.json, not the shipped scripts
    assert SPEC.output_dirs == (f"{build.PROJECT_ROOT}/specs", build.FEATURE_JSON)
    assert build.FEATURE_DIR.startswith(SPEC.output_dirs[0] + "/")


def test_round_rule_is_the_same_everywhere():
    docs = _docs()
    entry, implement, converge = docs["core-workflow.md"], docs["stages/04-implement.md"], docs["stages/05-converge.md"]
    assert "at most two rounds" in entry
    assert "at most two\nconverge rounds" in converge
    for text in (entry, converge):
        assert "convergence-2.md" in text and "convergence-3.md" not in text
    assert "Round 2, whatever the outcome" in converge
    assert "**Round 2**" in implement and "only the unchecked tasks" in implement
    assert "- **Round**: 1 | 2" in converge and "- **Outcome**: converged | tasks_appended" in converge


def test_constitution_is_the_unfilled_template_and_plan_has_the_rule():
    constitution = (build.SANDBOX / "memory" / "constitution.md").read_text(encoding="utf-8")
    assert "[PRINCIPLE_1_NAME]" in constitution and "<!-- Example:" in constitution
    plan = _docs()["stages/02-plan.md"]
    assert 'write "skipped — template" in Constitution Check and evaluate no gate' in plan
    assert "If the constitution is an unfilled template" in _docs()["stages/05-converge.md"]  # upstream's own rule, kept


def _template(name: str) -> str:
    return (build.SANDBOX / "templates" / f"{name}-template.md").read_text(encoding="utf-8")


def test_revisions_after_smoke_1():
    docs = _docs()
    entry = docs["core-workflow.md"]
    plan, tasks, implement = (docs[f"stages/{n}"] for n in ("02-plan.md", "03-tasks.md", "04-implement.md"))
    # G9-4 (rev): the Phase 1 files are always written; nothing applicable -> one N/A line
    assert "**Always written**" in plan and "`N/A — <reason>`" in plan and "Phase 1 applies only" not in plan
    assert "record `contracts/  # N/A — <reason>` in plan.md's Documentation tree" in plan and "holds one file" not in plan
    assert _template("plan").count("always, `N/A — <reason>` if nothing applies") == 2
    # G9-6: the contracts tree line is a fill-in slot the plan stage replaces
    assert "<REPLACE in plan.md: one line per contract file you wrote, or `N/A — <reason>` and no file>" in _template("plan")
    assert "replace it in plan.md" in plan
    assert "`N/A — <reason>`" in entry
    # G9-3 (rev): Setup / Foundational / Polish headings stay; an empty one says why
    for text in (tasks, _template("tasks")):
        assert "`No tasks — <reason>`" in text
    assert "no project initialization, dependency installation or tool configuration" in tasks  # scope limits stay
    # G9-1 (rev2): test tasks are written, as verification scripts under FEATURE_DIR/checks/; upstream TDD kept
    tasks_tpl, checks = _template("tasks"), f"{build.FEATURE_DIR}/checks/"
    assert "Here the task message is that request" in tasks and "Here the task message is that request" in tasks_tpl
    assert "`### Tests for User Story N`" in tasks and checks in tasks and checks in tasks_tpl
    assert "> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**" in tasks_tpl
    assert "- Tests (if included) MUST be written and FAIL before implementation" in tasks_tpl
    assert "- Verify tests fail before implementing" in tasks_tpl
    example_paths = re.findall(r"^- \[ \] T\w+ .*?\btests? .* in (\S+)$", tasks_tpl, flags=re.M)
    assert len(example_paths) == 7 and all(p.startswith(checks) for p in example_paths), example_paths
    assert "**Follow TDD approach**: Execute test tasks before their corresponding implementation tasks." in implement
    assert "confirm they fail, implement, then run them again and confirm they pass" in implement
    assert "**Tests before code**: If you need to write tests for contracts, entities, and integration scenarios" in implement
    baseline = "run the existing repository tests related to the change and record the baseline; run them again after"
    assert implement.count(baseline) == 1
    assert "Validate that tests pass: the verification scripts in `FEATURE_DIR/checks/`" in implement
    assert "coverage" not in implement
    for name, text in [*docs.items(), *((f"{t}-template", _template(t)) for t in build.TEMPLATE_SOURCES)]:
        for repo_test_dir in ("tests/contract/", "tests/integration/", "tests/unit/"):
            assert repo_test_dir not in text, (name, repo_test_dir)
    # G5-5 (rev2): checks/ holds the verification scripts and any scratch files; nothing into /testbed
    assert "Verification scripts (the files of the test tasks) and any scratch files" in entry
    assert "No test file is added or changed there" in entry
    # G4-6 (confirmed): Implementation Strategy stays deleted
    assert "## Implementation Strategy" not in _template("tasks")


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
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    entry = "/speckit-sdd/core-workflow.md"
    prompt = h.system_prompt_file.read_text(encoding="utf-8")
    for text in (h.instruction_text(), SECTION.search(prompt).group(0)):
        text = re.sub(r"\s+", " ", text)
        assert entry in text and "first action" in text
        assert "filesystem root" in text and "outside the repository" in text
    sdk = (RECIPE / "workflows" / "speckit_bug" / "system-prompt.j2").read_text(encoding="utf-8")
    assert SECTION.sub("", prompt) == SECTION.sub("", sdk)  # the other sections are the SDK default


# ---------------------------------------------------------------------- harness and sandbox files


def test_harness_picks_up_documents_and_sandbox_files():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    assert h._expected_doc_count() == len(_docs()) == 6
    assert [p.name for p in h._doc_entries()] == ["core-workflow.md", "stages"]
    composed = h.compose_instruction("TASK")
    assert composed.startswith("This task is solved through GitHub Spec Kit") and composed.endswith("\n\nTASK")
    assert h.evaluation_policy is None  # no scorer yet
    assert SPEC.sandbox_files == {build.SPECIFY_DIR: build.SANDBOX}
    assert SPEC.setup_script == DOCS.parent / "setup.sh" and not SPEC.agent_image_extra  # G7-8: jq -M wrapper
    setup = SPEC.setup_script.read_text(encoding="utf-8")
    assert "/usr/local/bin/jq" in setup and '-M "$@"' in setup and "/tmp/speckit-sdd" not in setup
    # the shipped tree is part of what the agent is given, so it is in the fingerprint
    before = SPEC.fingerprint("openhands-sdk")
    from dataclasses import replace

    assert replace(SPEC, sandbox_files={}).fingerprint("openhands-sdk") != before


def test_revision_3_rules_sit_where_the_agent_looks():
    tasks, implement = (DOCS / "stages" / "03-tasks.md").read_text(encoding="utf-8"), (DOCS / "stages" / "04-implement.md").read_text(encoding="utf-8")
    entry = (DOCS / "core-workflow.md").read_text(encoding="utf-8")
    # G9-5 reverted (measurement error): the Polish line and section are upstream again
    assert "- **Final Phase**: Polish & Cross-Cutting Concerns\n" in tasks + "\n"
    assert "Keep this heading" not in _template("tasks")
    # G9-7: the TDD order heads the execution rules and the entry doc's implement row
    rules = implement.split("6. Execute implementation following the task plan:")[1]
    assert rules.index("Each user story starts with its test tasks") < rules.index("Phase-by-phase execution")
    assert "first its verification scripts in `checks/` (run, seen failing)" in entry
    assert "`/tmp/test_x.py`" in entry
