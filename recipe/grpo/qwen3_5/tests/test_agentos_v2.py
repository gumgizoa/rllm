"""agentos_v2: docs/commands is what build.py renders from Agent OS v2.1.1, the documents point at each other
and keep the spec folder outside the repository, the harness picks the workflow up, and its hand-written
text is its own.

    pytest recipe/grpo/qwen3_5/tests/test_agentos_v2.py
    AGENT_OS_V2_DIR=/path/to/agent-os-v2.1.1 pytest ...   # the render tests; default ../agent-os-v2.1.1 beside the repo

The render tests need a checkout of tag v2.1.1 (build.py's docstring shows the ``git worktree`` command),
bash and perl; they are skipped without the checkout.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_v2 import build  # noqa: E402

NAME = "agentos_v2"
SPEC = workflows.WORKFLOWS[NAME]
DOCS = SPEC.docs_dir
UPSTREAM = Path(os.environ.get("AGENT_OS_V2_DIR", REPO.parent / "agent-os-v2.1.1"))
needs_upstream = pytest.mark.skipif(
    not (UPSTREAM / build.SOURCES["shape"][0]).is_file() or shutil.which("perl") is None,
    reason=f"no agent-os v2.1.1 checkout at {UPSTREAM} (or no perl)",
)
SECTION = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)
GLOBAL_STANDARDS = ("coding-style", "commenting", "conventions", "error-handling", "validation")


def _docs() -> dict[str, str]:
    return {p.relative_to(DOCS).as_posix(): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


def _upstream(key: str) -> str:
    return (UPSTREAM / build.SOURCES[key][0]).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered() -> dict[str, str]:
    return build.build(UPSTREAM)


# ---- the render


@needs_upstream
def test_committed_docs_match_a_fresh_render(rendered):
    assert sorted(rendered) == sorted(f"commands/{c}/{c}.md" for c in build.COMMANDS)
    for name, text in rendered.items():
        assert (build.OUT_DIR / name).read_text(encoding="utf-8") == text, f"docs/{name} drifted; rerun build.py"
    assert build.drift(rendered) == []


@needs_upstream
def test_reworded_upstream_fails_the_build():
    for e in build.EDITS:
        reworded = _upstream(e.source).replace(e.old, e.old[::-1])
        with pytest.raises(ValueError, match="anchor occurs 0 times"):
            build.convert(e.source, reworded)


@needs_upstream
def test_unresolved_template_fails_the_build(tmp_path):
    # the missing-section case of this port: a {{workflows/...}} reference upstream no longer satisfies
    up = tmp_path / "up"
    shutil.copytree(UPSTREAM, up, ignore=shutil.ignore_patterns(".git"))
    src = up / build.SOURCES["write"][0]
    src.write_text(src.read_text(encoding="utf-8").replace("{{workflows/specification/write-spec}}", "{{workflows/specification/write-the-spec}}"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="did not resolve"):
        build.build(up)


def test_upstream_wording_left_behind_fails_the_build(tmp_path):
    text = (DOCS / "commands/write-spec/write-spec.md").read_text(encoding="utf-8")
    for leftover in ("Return the spec path to the orchestrator.", "See also @agent-os/standards/global/tech-stack.md", "Then STOP and wait."):
        with pytest.raises(ValueError, match="left after conversion"):
            build.finish("write-spec", text + "\n" + leftover + "\n", tmp_path)


def test_every_edit_is_tagged_and_cites_its_gap():
    assert {e.tag for e in build.EDITS} <= set(build.PORT.tags) == {"env", "semantic"}
    for e in build.EDITS:
        assert re.match(r"G\d+-\d+", e.note), e.note


def test_standards_are_inlined_with_the_decided_deletions():
    docs = _docs()
    for cmd in build.COMMANDS:
        text = docs[f"commands/{cmd}/{cmd}.md"]
        labels = re.findall(r"^\*\*`agent-os/standards/([\w/-]+)\.md`\*\*$", text, re.M)
        if cmd == "shape-spec":
            assert labels == [f"global/{s}" for s in GLOBAL_STANDARDS], labels  # {{standards/global/*}}
        else:
            assert len(labels) == 14 and len(set(labels)) == 14, (cmd, labels)  # {{standards/*}} without tech-stack
        assert "tech-stack" not in text  # G7-6
        assert "Consistent Project Structure" in text and "Environment Configuration" in text  # G9-2 keeps
        assert "Consistent Indentation" in text  # G9-3 keeps lines 1-7
        assert text.index("User Standards & Preferences Compliance") < text.index("agent-os/standards/global/coding-style.md")


# ---- the documents


def test_documents_point_only_at_documents_that_exist():
    docs = _docs()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/agent-os/[\w./-]+\.md", text):  # not /tmp/agent-os/...
            assert ref.removeprefix("/agent-os/") in docs, f"{name} points at missing {ref}"
    for doc in build.COMMAND_DOCS.values():
        assert doc in docs["core-workflow.md"]
    # each command hands over to the next one (G2-2); implement-tasks continues into its own PHASE 3
    for cmd, nxt in zip(build.COMMANDS, build.COMMANDS[1:]):
        text = docs[f"commands/{cmd}/{cmd}.md"]
        assert f"open `{build.COMMAND_DOCS[nxt]}` and continue" in text, cmd
    assert "continue with PHASE 3 below" in docs["commands/implement-tasks/implement-tasks.md"]


def test_spec_folder_lives_outside_the_repository():
    docs = _docs()
    for name, text in docs.items():
        assert not re.search(r"(?<![\w/])agent-os/specs/", text), f"{name}: relative spec path"
        for path in re.findall(r"/tmp/agent-os/[\w./<>\[\]$-]*", text):
            assert path.startswith(build.SPECS_DIR), f"{name}: {path}"
        if name.startswith("commands/"):
            assert "/testbed" not in text, name
    entry = docs["core-workflow.md"]
    for artifact in ("initialization.md", "requirements.md", "spec.md", "tasks.md", "checks/", "verifications/final-verification.md"):
        assert artifact in entry, artifact
    assert "/tmp/agent-os/specs/<YYYY-MM-DD>-<name>/" in entry
    assert "finish" in entry and "TaskTracker" in entry and "<issue_description>" in entry


def test_decided_behaviors_are_in_the_commands():
    docs = _docs()
    shape = docs["commands/shape-spec/shape-spec.md"]
    impl = docs["commands/implement-tasks/implement-tasks.md"]
    tasks = docs["commands/create-tasks/create-tasks.md"]
    assert "planning/initialization.md` exactly as given" in shape  # G1-2
    assert "`$SPEC_PATH/verifications/`" in shape  # G5-5
    assert shape.count("**Answer:** (assumed)") == 3 and "(assumed) <path> — <basis>" in shape  # G4-1, G4-2
    assert "DATED_SPEC_NAME" in shape and "Always use dated folder names" in shape  # G5-2 kept
    assert "No visual files found" in shape  # G4-3: the mandatory ls stays
    assert "/checks/" in tasks and "do not add or change test files in the repository" in tasks  # G9-1
    assert "repeat PHASE 2 for the next task group with unchecked tasks" in impl  # G4-5
    assert "proceed with implementation of all task groups in tasks.md, in order" in impl  # G4-4
    assert "⚠️ No Updates Needed` with that reason" in impl  # G7-8
    assert "Run the entire tests suite for the application so that ALL tests run." in impl  # G8-2 verbatim
    assert "DO NOT attempt to fix any failing tests." in impl  # G8-3 verbatim
    assert "## 2. Documentation Verification" not in impl and "## 3. Roadmap Updates" in impl  # G5-6


# ---- the harness and the hand-written text


def test_hand_written_text_is_its_own():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    entry = f"{SPEC.container_dir.rstrip('/')}/{SPEC.entry_doc}"
    ours_inst = h.instruction_text()
    prompt = h.system_prompt_file.read_text(encoding="utf-8")
    ours_sec = SECTION.search(prompt).group(0)
    assert entry in ours_inst and entry in ours_sec
    for text in (ours_inst, ours_sec):
        assert "first" in text and "/testbed" in text  # first action; /agent-os is outside the repository
    for other, spec in workflows.WORKFLOWS.items():
        if other == NAME:
            continue
        if spec.instruction_file:
            theirs = spec.instruction_file.read_text(encoding="utf-8").replace(spec.container_dir, SPEC.container_dir)
            assert theirs.strip() != ours_inst.strip(), other
        theirs_prompt = spec.system_prompt.get("openhands-sdk")
        if theirs_prompt:
            text = theirs_prompt.read_text(encoding="utf-8")
            assert SECTION.sub("", text) == SECTION.sub("", prompt), other  # the other 15 sections are the SDK's
            assert SECTION.search(text).group(0).replace(spec.container_dir, SPEC.container_dir) != ours_sec, other


def test_harness_uploads_every_document():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    assert h._expected_doc_count() == len(_docs()) == 5
    composed = h.compose_instruction("TASK")
    assert composed.startswith(h.instruction_text().strip()) and composed.endswith("\n\nTASK")
    assert SPEC.output_dirs == ("/tmp/agent-os",)
    # resolve rate only until the generated rubric exists (reward/rubric.yaml), then its scorer
    assert (h.evaluation_policy is None) == (not (RECIPE / "workflows" / NAME / "reward" / "rubric.yaml").is_file())
