"""openspec_ff: the stage documents and the forked schema are what build.py makes of OpenSpec, the
documents point at each other, the agreed fork text is there verbatim, the harness picks the workflow
and its sandbox tooling up, and the hand-written text is this workflow's own.

    pytest recipe/grpo/qwen3_5/tests/test_openspec_ff.py
    OPENSPEC_DIR=/path/to/OpenSpec pytest ...   # the drift checks; default ../OpenSpec beside the repo
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from recipe.grpo.qwen3_5 import workflows  # noqa: E402
from recipe.grpo.qwen3_5.workflow_harness import OpenHandsSdkWorkflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.openspec_ff import build  # noqa: E402

NAME = "openspec_ff"
SPEC = workflows.WORKFLOWS[NAME]
DOCS = SPEC.docs_dir
UPSTREAM = Path(os.environ.get("OPENSPEC_DIR", REPO.parent / "OpenSpec"))
needs_upstream = pytest.mark.skipif(not (UPSTREAM / "schemas" / "spec-driven").is_dir(), reason=f"no OpenSpec checkout at {UPSTREAM}")
SECTION = re.compile(r"<PROBLEM_SOLVING_WORKFLOW>.*?</PROBLEM_SOLVING_WORKFLOW>", re.S)


def _docs() -> dict[str, str]:
    return {p.relative_to(DOCS).as_posix(): p.read_text(encoding="utf-8") for p in DOCS.rglob("*.md")}


def _upstream(port, key: str) -> str:
    return (UPSTREAM / port.sources[key][0]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- build


@needs_upstream
@pytest.mark.parametrize("label", ["stages", "fork"])
def test_committed_outputs_match_a_fresh_build(label):
    port = build.PORTS[label]
    built = build.BUILDERS[label](UPSTREAM)
    for name, text in built.items():
        assert (port.out_dir / name).read_text(encoding="utf-8") == text, f"{label}: {name} drifted; rerun build.py"
    on_disk = sorted(p.relative_to(port.out_dir).as_posix() for p in port.out_dir.rglob("*") if p.is_file())
    assert on_disk == sorted(built), f"{label}: stray or missing files in {port.out_dir}"


@needs_upstream
def test_reworded_upstream_fails_the_build():
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert("apply", _upstream(build.STAGES, "apply").replace("**Pause if:**", "**Pause when:**"))
    with pytest.raises(ValueError, match="anchor occurs 0 times"):
        build.convert_fork("schema", _upstream(build.FORK, "schema").replace("ask the user instead of guessing", "check with the user"))


@needs_upstream
def test_upstream_wording_left_behind_fails_the_build():
    text = _upstream(build.STAGES, "verify").replace("**Verification Heuristics**", "- Ask the user first.\n\n**Verification Heuristics**")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("verify", text)


@needs_upstream
def test_ask_the_user_is_allowed_once_in_explore_only():
    # G4-14: explore:48's "Do not ask the user to repeat facts you can verify." stays verbatim; nothing else may.
    kept = build.FORBIDDEN_ALLOWED["explore"][0]
    assert "ask the user" in kept and "ask the user" in build.FORBIDDEN
    assert kept in build.convert("explore", _upstream(build.STAGES, "explore"))
    ff = _upstream(build.STAGES, "ff").replace("**Guardrails**", f"{kept}\n\n**Guardrails**")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("ff", ff)  # the allowance is per source
    explore = _upstream(build.STAGES, "explore")
    with pytest.raises(ValueError, match="left after conversion"):
        build.convert("explore", explore.replace("## Guardrails", "Otherwise ask the user.\n\n## Guardrails"))
    with pytest.raises(ValueError, match="occurs 2 times"):
        build.convert("explore", explore.replace("## Guardrails", f"{kept}\n\n## Guardrails"))


def test_every_edit_is_tagged_and_cites_its_gap():
    for e in (*build.EDITS, *build.FORK_EDITS):
        assert e.tag in {"env", "semantic"}, e
        assert re.match(r"(G\d+-\d+|D-\d+|Q\d+)\b", e.note), e.note


def test_list_covers_both_outputs(capsys):
    assert build.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "== stages" in out and "== fork" in out and "G9-1/G9-2" in out


# ---------------------------------------------------------------------- documents


def test_documents_point_only_at_documents_that_exist():
    docs = _docs()
    for name, text in docs.items():
        for ref in re.findall(r"(?<![\w/])/opsx/[\w./-]+\.md", text):
            assert ref.removeprefix("/opsx/") in docs, f"{name} points at missing {ref}"
    for stage in build.STAGE_DOCS.values():
        assert stage in docs["core-workflow.md"]
    assert sorted(docs) == ["core-workflow.md", *sorted(f"stages/{out}" for _, out in build.SOURCES.values())]


def test_removed_upstream_wording_is_gone():
    docs = _docs()
    keys = {out: key for key, (_, out) in build.SOURCES.items()}
    for name, text in docs.items():
        if name.startswith("stages/"):
            assert build.forbidden_left(keys[name.removeprefix("stages/")], text) == [], name
    for path in build.FORK_DIR.rglob("*"):
        if path.is_file():
            for bad in build.FORK_FORBIDDEN:
                assert bad not in path.read_text(encoding="utf-8"), (path.name, bad)
    assert not (DOCS / "stages" / "05-archive.md").exists()  # D-5: archive is the CLI


def test_planning_paths_stay_outside_the_repository():
    for name, text in _docs().items():
        assert "/testbed/openspec" not in text, name
        assert "/opsx:" not in text or name == "core-workflow.md", name  # slash commands only in the flow line
    entry = _docs()["core-workflow.md"]
    for needle in ("verify.md", "/openspec/changes/issue/checks/", "openspec archive issue --yes", "--no-validate"):
        assert needle in entry, needle


def test_verify_runs_once_then_archive():
    entry = _docs()["core-workflow.md"]
    verify = _docs()["stages/03-verify.md"]
    assert "Verify runs once" in entry
    assert "**Next step**: go to the archive step" in verify
    for text in (entry, verify):
        assert "verify-2" not in text and not re.search(r"\brounds?\b", text, re.I)


# ---------------------------------------------------------------------- the fork


def test_fork_is_a_valid_schema_carrying_the_agreed_text():
    schema = yaml.safe_load((build.FORK_DIR / "schema.yaml").read_text(encoding="utf-8"))
    assert schema["name"] == build.FORK_NAME == "spec-driven-sandbox"
    assert [a["id"] for a in schema["artifacts"]] == ["proposal", "specs", "design", "tasks"]
    by_id = {a["id"]: a for a in schema["artifacts"]}
    tasks = by_id["tasks"]["instruction"]
    assert build.AGREED_TASKS_ITEM in tasks  # porting/03-decisions.md, verbatim
    for line in build.AGREED_EXAMPLE.values():
        assert line + "\n" in tasks
    for kept in ("- [ ] 1.1 Create new module structure", "- [ ] 2.1 Implement data export function", "Each task MUST state how to verify completion"):
        assert kept in tasks
    assert "New external dependency" in by_id["design"]["instruction"]  # G9-4: condition kept
    assert "**Decisions**" in by_id["design"]["instruction"] and "**Decisions**" in tasks  # G4-3
    assert "plain line" in schema["apply"]["instruction"]  # G4-4
    for t in ("proposal", "spec", "design", "tasks"):
        assert (build.FORK_DIR / "templates" / f"{t}.md").is_file()


def test_agreed_text_matches_the_decisions_record():
    record = (build.HERE / "porting" / "03-decisions.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)```", record, flags=re.S)
    assert blocks[0] == build.AGREED_TASKS_ITEM
    assert blocks[1].splitlines() == list(build.AGREED_EXAMPLE.values())


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


def test_instruction_and_prompt_send_the_agent_to_the_entry_document_first():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    entry = "/opsx/core-workflow.md"
    inst = h.instruction_text()
    prompt = h.system_prompt_file.read_text(encoding="utf-8")
    sec = SECTION.search(prompt).group(0)
    for text in (inst, sec):
        assert entry in text and "first action" in text and "openspec" in text
        assert "root of the filesystem" in text or "top-level directory of the filesystem" in text
    sdk = (RECIPE / "workflows" / "speckit_bug" / "system-prompt.j2").read_text(encoding="utf-8")
    assert SECTION.sub("", prompt) == SECTION.sub("", sdk)  # the other sections are the SDK default


# ---------------------------------------------------------------------- harness and sandbox tooling


def test_harness_picks_up_documents_and_tooling():
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    assert h._expected_doc_count() == len(_docs()) == 5  # core-workflow + explore, ff, apply, verify (D-7: no new stage)
    composed = h.compose_instruction("TASK")
    assert composed.startswith("Solve this task as an OpenSpec change") and composed.endswith("\n\nTASK")
    # resolve rate only until the generated rubric exists (reward/rubric.yaml), then its scorer
    assert (h.evaluation_policy is None) == (not (RECIPE / "workflows" / NAME / "reward" / "rubric.yaml").is_file())
    assert SPEC.output_dirs == ("/openspec",)
    extra = h.agent_image_extra
    assert extra and "@fission-ai/openspec@1.14.1" in extra and "/opt/rllm/agent/node" in extra
    from recipe.grpo.qwen3_5.workflows import openspec_ff

    assert set(SPEC.sandbox_files) == {openspec_ff.FORK_STAGED, openspec_ff.CONFIG_STAGED}  # fork + config (G10-7)
    fork = SPEC.sandbox_files[openspec_ff.FORK_STAGED]
    assert fork == build.FORK_DIR and (fork / "schema.yaml").is_file()
    assert SPEC.sandbox_files[openspec_ff.CONFIG_STAGED].is_file()
    setup = SPEC.setup_script.read_text(encoding="utf-8")
    for remote in SPEC.sandbox_files:
        assert remote in setup  # setup.sh installs what was uploaded
    assert "openspec init --tools none" in setup and '"$REPO/openspec"' in setup and "REPO=/testbed" in setup


def test_setup_script_parses():
    subprocess.run(["bash", "-n", str(SPEC.setup_script)], check=True)


def test_cli_wrapper_is_non_interactive_and_setup_checks_a_tty_run():
    # G10-6: the agent's terminal is a TTY; without CI the CLI's `new change` never exits there.
    setup = (Path(__file__).resolve().parents[1] / "workflows" / "openspec_ff" / "setup.sh").read_text(encoding="utf-8")
    wrapper = next(line for line in setup.splitlines() if "exec /opt/rllm/agent/node/bin/node" in line)
    assert wrapper.startswith("CI=1 ") and "OPENSPEC_TELEMETRY=0" in wrapper and "OPENSPEC_NO_UPDATE_CHECK=1" in wrapper
    assert "script -qec" in setup and "new change setup-tty-probe" in setup


def test_no_new_stage_and_ff_creates_the_change():
    # D-7: the chain starts at ff, whose own step 2 (upstream) runs `openspec new change "issue"`.
    docs = _docs()
    assert sorted(docs) == ["core-workflow.md", "stages/00-explore.md", "stages/01-ff.md", "stages/02-apply.md", "stages/03-verify.md"]
    assert 'openspec new change "issue"' in docs["stages/01-ff.md"]
    assert "/opsx:new" not in docs["core-workflow.md"] and "01-new" not in "".join(docs.values())


def test_project_config_carries_facts_without_operation_guidance():
    # G10-7: upstream's config.yaml channel; facts only, so apply's conflict branches have nothing to fire on.
    import yaml

    from recipe.grpo.qwen3_5.workflows import openspec_ff

    cfg_path = openspec_ff.SPEC.sandbox_files[openspec_ff.CONFIG_STAGED]
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert cfg["schema"] == openspec_ff.FORK_NAME
    assert "operations" not in cfg  # no guidance -> no "explain inapplicable guidance" branch
    assert set(cfg["rules"]) == {"proposal", "specs"} and "/testbed" in cfg["context"]
    assert len(cfg["context"].encode()) < 51_200  # upstream's context limit
    assert "ADDED Requirements" in " ".join(cfg["rules"]["specs"])
    fork = (openspec_ff.SPEC.sandbox_files[openspec_ff.FORK_STAGED] / "schema.yaml").read_text(encoding="utf-8")
    assert "starts empty" not in fork  # G7-5 lives in the rules now, not in the fork


# ---------------------------------------------------------------------- explore (porting/03-decisions.md "Explore extension")


def test_explore_comes_first_and_hands_off_to_ff():
    docs = _docs()
    entry, explore = docs["core-workflow.md"], docs["stages/00-explore.md"]
    assert "/opsx:explore ──► /opsx:ff" in entry  # G3-2: chain line
    assert entry.index("/opsx/stages/00-explore.md") < entry.index("/opsx/stages/01-ff.md")  # actions table order
    assert "What We Figured Out" in entry and "openspec list --json" in entry
    assert explore.count(build.STAGE_DOCS["ff"]) >= 4  # G2-10: every hand-off goes to ff
    assert "/openspec-propose" not in explore and "openspec-apply-change" not in explore
    h = OpenHandsSdkWorkflow(workflow=NAME, instruction_position="prefix")
    sec = SECTION.search(h.system_prompt_file.read_text(encoding="utf-8")).group(0)
    for text in (h.instruction_text(), sec):  # G10-8: explore named before ff, first action unchanged
        assert text.lower().index("explore") < re.search(r"\bff\b", text).start()


def test_explore_writes_nothing_and_composes_no_code():
    explore = _docs()["stages/00-explore.md"]
    entry = _docs()["core-workflow.md"]
    assert "NEVER write code or implement features" in explore and "Never write code or implement features" in explore  # kept
    assert "In this session explore writes nothing" in explore  # G4-13
    assert "python -c" in explore and "python -c" in entry  # G9-5 boundary, in the stage and the entry document
    for gone in ("### When no change exists", "### When a change exists", "Don't manually scaffold", "yes/no", "Want me to"):
        assert gone not in explore, gone  # G4-17, G7-10, G4-13
    assert 'openspec new change "issue"' not in explore  # only ff runs it
    assert "Explore writes none." in entry and "writes no file anywhere" in entry


def test_explore_ends_with_the_summary_ff_builds_on():
    explore = _docs()["stages/00-explore.md"]
    for field in ("**The problem**", "**How the area works**", "**Where the change goes**", "**Assumptions**", "**Open questions**"):
        assert field in explore, field  # G2-12
    assert "There's no required ending" not in explore and "summary is optional" not in explore  # G8-6, G2-12
    assert "inside a tool call (the `think` tool, for example) before the tool call that opens" in explore  # G2-11, G2-14
    assert "heredoc piped to `python3`" in explore  # G9-6: composed code named in the guardrail
    assert "Do not ask the user to repeat facts you can verify." in explore  # G4-14: explore:48 verbatim
    assert "I assume a single-device\ntool (assumption, with that evidence)" in explore  # G4-19
    assert "Is sharing state" not in explore
    for gone in ("User brings a vague idea", "User is stuck mid-implementation", "User wants to compare options"):
        assert gone not in explore  # G4-18, G4-17
    assert "User brings a specific problem" in explore
    ff = _docs()["stages/01-ff.md"]
    assert "reuse findings for later artifacts and inspect more only as needed" in ff  # G2-13: ff verbatim


def test_config_says_checks_start_with_ff():
    from recipe.grpo.qwen3_5.workflows import openspec_ff

    cfg = yaml.safe_load(openspec_ff.SPEC.sandbox_files[openspec_ff.CONFIG_STAGED].read_text(encoding="utf-8"))
    assert "From the ff action on, scripts written to reproduce or check behavior live in /openspec/changes/issue/checks/." in cfg["context"]  # G10-9
