"""Item-rule fixes of groups D and E (tasks/2026-11-20-agentos-bugfix-reward-fixes/03-D-E-G-계획.md), checked on small
synthetic artifacts and runs. Every new parameter of shared code is also shown to leave the default behaviour as it was.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric.checks import artifacts as A  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix import derive_rubric as D  # noqa: E402

RUBRIC = yaml.safe_load((RECIPE / "workflows" / "agentos_bugfix" / "reward" / "rubric.yaml").read_text(encoding="utf-8"))


def _item_params(suffix: str) -> dict:
    return next(it["check"]["params"] for it in RUBRIC["items"] if it["id"].endswith(suffix))


def _item(params: dict, ref: str = "requirements", state: str = "final", iid: str = "x"):
    return SimpleNamespace(id=iid, check=SimpleNamespace(params=params), target=SimpleNamespace(ref=ref, state=state, type="artifact"))


def _ctx(text: str | None, **kw):
    return SimpleNamespace(artifact_text=lambda aid, state="final": text, **kw)


# ---- D-2: the order item's quality threshold -----------------------------------------------------------------------


def test_order_item_counts_a_write_capped_by_one_must_item():
    assert _item_params("global.run.order.commands")["substantive"] == D.ORDER_SUBSTANTIVE == 0.1


# ---- E-2 / E-4 row 4: the (assumed) notations and every Feature line ---------------------------------------------


def _reuse(lines: str):
    p = _item_params("shape_spec.requirements.item_format.reusability_opportunities")
    return A.item_format(_item(p), _ctx("## Requirements Summary\n\n### Reusability Opportunities\n" + lines + "\n"))


def test_reusability_accepts_both_documented_notations_and_a_none_line():
    for ok in ("- (assumed) `src/a.py` — has the parser", "- (assumed) src/a.py — has the parser",
               "No similar existing features identified for reference.", "- None found", "- No similar features identified"):
        assert _reuse(ok).status == "pass", ok
    for bad in ("- src/a.py has the parser", "- Similar patterns may exist elsewhere"):
        assert _reuse(bad).status == "fail", bad


def _existing(lines: str, params: dict | None = None):
    p = params or _item_params("shape_spec.requirements.item_format.existing_code")
    return A.item_format(_item(p), _ctx("## Requirements Discussion\n\n### Existing Code to Reference\n" + lines + "\n"))


def test_existing_code_accepts_the_notation_without_backticks():
    assert _existing("- Feature: lexer - Path: (assumed) src/c.py — reads y").status == "pass"
    assert _existing("No similar existing features identified for reference.").status == "pass"


def test_reusability_keeps_a_backtick_path_followed_by_more_code():
    assert _reuse("- (assumed) `sympy/core/mul.py`'s `as_coeff_Mul` — the pattern to follow").status == "pass"


def test_the_assumed_notation_copied_as_one_code_span_counts():
    assert _existing("- Feature: x - Path: `(assumed) /testbed/src/a.py` — reads x").status == "pass"
    assert _existing("- Feature: x - Path: `(assumed)` `/testbed/src/a.py` — reads x").status == "pass"
    assert _reuse("- `(assumed) src/a.py` — has the parser").status == "pass"
    assert _existing("- Feature: x - Path: /testbed/src/a.py — reads x").status == "fail"  # no (assumed)


def test_every_feature_line_of_existing_code_is_in_the_assumed_notation():
    good = "- Feature: parser - Path: (assumed) `src/a.py` — reads x\n- Components to potentially reuse: the tokenizer in src/b.py"
    assert _existing(good).status == "pass"
    r = _existing(good + "\n- Feature: lexer - Path: src/c.py")
    assert r.status == "fail" and r.score == 0.5
    assert _existing("No similar existing features identified for reference.").status == "pass"


def test_each_of_off_keeps_item_format_as_it_was():
    p = {"pattern": r"\(assumed\)\s+`[^`\n]+`\s+—\s+\S", "section": "Existing Code to Reference"}
    half = "- Feature: parser - Path: (assumed) `src/a.py` — reads x\n- Feature: lexer - Path: src/c.py"
    assert _existing(half, p).status == "pass"  # one matching line is enough without each_of


# ---- E-4 row 5: the documents' folder placeholders and question frame ------------------------------------------


def test_document_placeholders_are_template_residue():
    for suffix, ref in (("create_tasks.tasks.no_template_residue", "tasks"), ("write_spec.spec.no_template_residue", "spec"),
                        ("shape_spec.requirements.no_template_residue", "requirements"), ("implement_tasks.final_verification.no_template_residue", "final_verification")):
        p = _item_params(suffix)
        assert A.no_template_residue(_item(p, ref=ref), _ctx("- [x] 1.1 Create `/tmp/agent-os/specs/[spec-path]/checks/t.py`\n")).status == "fail", suffix
    p = _item_params("shape_spec.requirements.no_template_residue")
    assert A.no_template_residue(_item(p), _ctx("**Q6:** x\n[Last numbered question about exclusions]\n")).status == "fail"


# ---- E-1: a fill-in mark that is a line of the task description -------------------------------------------------

from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import task_text as TT  # noqa: E402

TRACEBACK = "e.subs fails\n    >>> print(e.subs(x, 2))\n    ...\n    NameError: name 'cotm' is not defined\n"


def _with_task(text, task):
    return SimpleNamespace(artifact_text=lambda aid, state="final": text, collected=SimpleNamespace(inputs={"task": task}))


def test_a_fill_mark_line_copied_from_the_task_is_not_a_blank():
    p = _item_params("shape_spec.initialization.no_template_residue.fill_marks")
    item = _item(p, ref="initialization")
    live = SimpleNamespace(instruction=TRACEBACK)  # rllm Task: the text is its instruction
    offline = SimpleNamespace(metadata={"instruction": TRACEBACK})  # a stored episode's task row
    for task in (live, offline):
        assert TT.task_residue(item, _with_task(TRACEBACK, task)).status == "pass"
    assert TT.task_residue(item, _with_task(TRACEBACK + "- ...\n", live)).status == "pass"  # the same line under a list marker
    assert TT.task_residue(item, _with_task(TRACEBACK + "- Notes: xxx\n", live)).status == "fail"  # a blank the task lacks
    # no task handed in: the common rule, which reads the traceback's "..." as a blank
    assert TT.task_residue(item, _with_task(TRACEBACK, None)).status == "fail"
    assert TT.task_residue(item, _with_task(TRACEBACK, None)).score == A.no_template_residue(item, _ctx(TRACEBACK)).score


def test_the_task_description_is_the_issue_inside_its_tags():
    wrapped = "<uploaded_files>\n/testbed\n</uploaded_files>\n<issue_description>\nthe bug\n...\n</issue_description>\nPlease fix."
    ctx = _with_task("", SimpleNamespace(instruction=wrapped))
    assert TT.task_description(ctx) == "the bug\n..."


# ---- E-4 row 2: initialization.md holds the task description, not a summary -------------------------------------


def test_initialization_holds_the_task_description():
    p = _item_params("shape_spec.initialization.item_format.text")
    item = _item(p, ref="initialization")
    task = SimpleNamespace(instruction="The parser drops the last token when the input ends with a comma, so a, b, becomes a, b.")
    assert TT.task_text(item, _with_task(task.instruction, task)).status == "pass"
    r = TT.task_text(item, _with_task("Parser drops a token.", task))
    assert r.status == "fail" and 0 < r.score < 1  # a summary: failed, scored by how much of the text is there
    # without a task description: the common rule (some text)
    assert TT.task_text(item, _with_task("Parser drops a token.", None)).status == "pass"


# ---- E-3: report statuses, an optional Notes section, top-level bullets ---------------------------------------

from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C  # noqa: E402

TICKED = "#### Task Group 1: Fix\n- [x] 1.0 Fix\n  - [x] 1.1 Write tests\n  - [x] 1.2 Change src/a.py\n"


def _report(rule: str, report: str, tasks: str = TICKED, **extra):
    texts = {"final_verification": report, "tasks": tasks}
    ctx = SimpleNamespace(artifact_text=lambda aid, state="final": texts.get(aid))
    return C.report(_item({"rule": rule, "suite_section": "2. Test Suite Results", **extra}, ref="final_verification"), ctx)


ISSUES = "# R\n**Status:** ⚠️ Passed with Issues\n## 1. Tasks Verification\n**Status:** ⚠️ Issues Found\n### Incomplete or Issues\n{}\n## 2. Test Suite Results\n**Status:** {}\n"


def test_issues_found_with_every_task_ticked_needs_a_listed_issue():
    listed = ISSUES.format("- The fix of query.py does not work for joins", "✅ All Passing")
    assert _report("tasks_status", listed, issues_listed=True).status == "pass"
    assert _report("tasks_status", ISSUES.format("None", "✅ All Passing"), issues_listed=True).status == "fail"
    assert _report("tasks_status", listed).status == "fail"  # without the parameter, as before


def test_overall_status_takes_either_value_when_both_rules_hold():
    both = ISSUES.format("- x", "❌ Critical Failures")
    assert _report("overall_status", both).status == "pass"
    assert _report("overall_status", both.replace("⚠️ Passed with Issues", "❌ Failed")).status == "pass"
    assert _report("overall_status", both.replace("⚠️ Passed with Issues", "✅ Passed")).status == "fail"


def test_notes_may_be_left_out_when_optional():
    p = {"heading": "Notes", "level": 3}
    no_notes, wrong_level = "## 2. Test Suite Results\n### Failed Tests\nNone\n", "## 2. Test Suite Results\n## Notes\nx\n"
    assert A.section_present(_item({**p, "optional": True}, ref="final_verification"), _ctx(no_notes)).status == "not_applicable"
    assert A.section_present(_item({**p, "optional": True}, ref="final_verification"), _ctx(wrong_level)).status == "fail"
    numbered = "## 2. Test Suite Results\n## 3. Notes\nx\n"
    assert A.section_present(_item({**p, "optional": True}, ref="final_verification"), _ctx(numbered)).status == "fail"
    assert A.section_present(_item(p, ref="final_verification"), _ctx(no_notes)).status == "fail"


def _blocks(section: str, **extra):
    p = {"section": "Existing Code to Leverage", "min_blocks": 0, "max_blocks": 5, "max_bullets": 5, **extra}
    return C.blocks(_item(p, ref="spec"), _ctx("## Existing Code to Leverage\n" + section))


def test_blocks_count_top_level_bullets_and_leading_ones():
    nested = "**Timezone**\n- a\n- b\n  - b1\n  - b2\n  - b3\n- c\n"
    assert _blocks(nested, top_level=True).status == "pass"  # 3 top-level bullets
    assert _blocks(nested).status == "fail"  # as before: 6 bullets
    leading = "".join(f"- point {i}\n" for i in range(10)) + "**Search**\n- a\n"
    assert _blocks(leading, top_level=True).status == "fail"  # the 10 bullets before the first name are a block
    assert _blocks(leading).status == "pass"
    unnamed = "".join(f"- point {i}\n" for i in range(10))
    assert _blocks(unnamed, top_level=True).status == "pass"  # no named block at all: as before


# ---- E-4 row 14: a Status that mixes two values or adds a failure -----------------------------------------------


def _status(value: str, **extra):
    p = {"section": "2. Test Suite Results", "label": "Status", "values": ["✅ All Passing", "⚠️ Some Failures", "❌ Critical Failures"], "prefix_ok": True, **extra}
    return A.field_enum(_item(p, ref="final_verification"), _ctx(f"## 2. Test Suite Results\n**Status:** {value}\n"))


def test_strict_prefix_rejects_mixed_and_contradicted_values():
    for bad in ("✅ All Passing (excluding pre-existing failures)", "✅ All Passing (except 2 pre-existing failures unrelated)"):
        assert _status(bad, strict_prefix=True).status == "fail", bad
        assert _status(bad).status == "pass", bad  # without the parameter, as before
    for ok in ("✅ All Passing", "✅ All Passing (for feature-specific tests)", "✅ All Passing (no failures)", "⚠️ Some Failures (pre-existing issues)"):
        assert _status(ok, strict_prefix=True).status == "pass", ok
    p = {"section": "*", "label": "Status", "values": ["✅ Passed", "⚠️ Passed with Issues", "❌ Failed"], "prefix_ok": True, "strict_prefix": True}
    assert A.field_enum(_item(p, ref="final_verification"), _ctx("# R\n**Status:** ✅ Passed with Issues\n")).status == "fail"




# ---- E-4 row 6: an answer whose basis names no source -----------------------------------------------------------


def _answers(lines: str, **extra):
    return C.requirements(_item({"rule": "answers", **extra}), _ctx("## Requirements Discussion\n" + lines))


def test_an_answer_needs_a_basis_that_names_a_source():
    good = "**Q1:** Fix x?\n**Answer:** (assumed) Yes — the traceback in the task description shows it\n"
    bad = "**Q2:** Tests?\n**Answer:** (assumed) Add regression tests — Standard testing practice.\n"
    path = "**Q3:** Where?\n**Answer:** (assumed) In the parser — `src/parse.py` line 40\n"
    r = _answers(good + bad + path, basis_check=True)
    assert r.status == "fail" and abs(r.score - 2 / 3) < 1e-9
    assert _answers(good + bad + path).status == "pass"  # without the parameter, as before




# ---- E-4 row 8: ### sections of requirements.md outside the template ------------------------------------------


def test_level_three_headings_outside_the_task_text_are_checked():
    p = _item_params("shape_spec.requirements.cross_ref.2")
    text = ("# Spec Requirements: x\n## Initial Description\nissue\n### Expected behavior\nquoted from the task\n"
            "## Requirements Discussion\n### First Round Questions\n### Existing Code to Reference\n"
            "## Requirements Summary\n### Functional Requirements\n### Reusability Opportunities\n### Scope Boundaries\n### Technical Considerations\n")
    ctx = SimpleNamespace(artifact_text=lambda aid, state="final": text, collected=SimpleNamespace(workdir="/testbed"))
    assert A.cross_ref(_item(p), ctx).status == "pass"
    ctx2 = SimpleNamespace(artifact_text=lambda aid, state="final": text + "### Research Findings\n", collected=SimpleNamespace(workdir="/testbed"))
    assert A.cross_ref(_item(p), ctx2).status == "fail"


# ---- E-4 row 7: the spec folder's date is the run's date ------------------------------------------------------

import datetime  # noqa: E402
import pickle  # noqa: E402
import subprocess  # noqa: E402

from recipe.grpo.qwen3_5.workflow_rubric import collect as COL  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, WriteEvent  # noqa: E402


def test_the_task_info_script_reports_the_sandbox_date(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    out = subprocess.run(["bash", "-c", COL._task_info_script(str(tmp_path))], capture_output=True, text=True, check=True).stdout
    info = COL.parse_task_info(out, str(tmp_path))
    assert info.today == datetime.date.today().isoformat() and info.base_sha and not info.errors
    # an output without the record (an older script) still parses, without a date
    old = "\n".join(ln for ln in out.splitlines() if " DATE " not in ln)
    assert COL.parse_task_info(old, str(tmp_path)).today is None and COL.parse_task_info(old, str(tmp_path)).base_sha == info.base_sha
    # a Collected pickled before the field existed loads with today None (the dataclass default)
    assert pickle.loads(pickle.dumps(Collected())).today is None


def test_the_spec_folder_date_is_the_runs_when_known(monkeypatch):
    monkeypatch.setattr(A, "_root", lambda c, name: "/tmp/agent-os/specs")
    p = {"pattern": r"\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*"}

    def judge(name, date, **extra):
        ctx = SimpleNamespace(facts=SimpleNamespace(artifact_paths={"spec_dir": f"/tmp/agent-os/specs/{name}"}), collected=SimpleNamespace(today=date))
        return A.path_match(_item({**p, **extra}, ref="spec_dir"), ctx).status

    assert judge("2026-11-13-fix-x", "2026-11-13", today=True) == "pass"
    assert judge("2026-11-14-fix-x", "2026-11-13", today=True) == "pass"  # past midnight
    assert judge("2024-01-01-fix-x", "2026-11-13", today=True) == "fail"
    assert judge("2024-01-01-fix-x", None, today=True) == "pass"  # offline: the shape only
    assert judge("2024-01-01-fix-x", "2026-11-13") == "pass"  # without the parameter, as before




# ---- E-4 row 9: verifications/ made during shape-spec --------------------------------------------------------

from recipe.grpo.qwen3_5.workflow_rubric.replay import replay  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

SPEC = "/tmp/agent-os/specs/2026-11-13-x"


def test_the_replay_records_when_a_directory_appeared():
    run = Run("t", [Step(1, [Action("shell", "terminal", command=f"mkdir -p {SPEC}/planning")]),
                    Step(2, [Action("shell", "terminal", command=f"mkdir -p {SPEC}/verifications")]),
                    Step(9, [Action("shell", "terminal", command=f"echo x > {SPEC}/checks/t.py")])])
    rep = replay(run, "/testbed")
    assert rep.dir_steps[SPEC + "/verifications"] == 2 and rep.dir_steps[SPEC + "/planning"] == 1 and rep.dir_steps[SPEC + "/checks"] == 9


def test_a_directory_made_after_its_stage_fails_at_stage_end(monkeypatch):
    from recipe.grpo.qwen3_5.workflow_rubric import facts as FF  # noqa: PLC0415

    monkeypatch.setattr(FF, "location_paths", lambda *a: [])
    art = SimpleNamespace(id="verifications_dir", kind="dir", locations=[])
    item = _item({}, ref="verifications_dir", state="stage_end")

    def judge(made, writes=(), commands=()):
        facts = SimpleNamespace(dir_steps={SPEC + "/verifications": made} if made else {}, writes={SPEC + "/verifications/r.md": [WriteEvent(path="", step=s, op="create") for s in writes]},
                                windows={"shape_spec": (2, 10)}, artifact_paths={"verifications_dir": SPEC + "/verifications"}, commands=commands)
        ctx = SimpleNamespace(facts=facts, rubric=SimpleNamespace(stages=[SimpleNamespace(id="shape_spec", artifacts=["verifications_dir"])], artifacts={"verifications_dir": art}),
                              collected=SimpleNamespace(workdir="/testbed", files={}))
        return A._dir_at_stage_end(item, ctx, art, SPEC + "/verifications").status

    assert judge(4, writes=(50,)) == "pass"  # made in shape-spec, the report written later
    assert judge(50, writes=(50,)) == "fail"  # first made with the report
    # a mkdir the replay could not expand ($(date ...)) still dates the directory
    made_by_date = [SimpleNamespace(step=6, command="mkdir -p /tmp/agent-os/specs/$(date +%Y-%m-%d)-x/verifications")]
    assert judge(None, writes=(50,), commands=made_by_date) == "pass"


# ---- E-5: scratch files outside checks/, temporary files in the repository, a change without a source file -------

from recipe.grpo.qwen3_5.workflow_rubric import refs as REFS  # noqa: E402


def test_scratch_files_anywhere_under_tmp_outside_the_spec_folder():
    rx = re.compile(_item_params("global.run.agentos_bugfix_paths_written.scratch_outside_checks")["pattern"])
    for bad in ("/tmp/questions.txt", "/tmp/fix_mod.patch", "/tmp/repro.py", f"{SPEC}/notes.py"):
        assert rx.search(bad), bad
    for ok in (f"{SPEC}/checks/test_a.py", f"{SPEC}/checks/notes.txt", f"{SPEC}/planning/requirements.md", f"{SPEC}/spec.md"):
        assert not rx.search(ok), ok


def _repo_ctx(diff, writes, created=()):
    facts = SimpleNamespace(repo_writes=writes, n_steps=20, _created={"/testbed/" + p: 1 for p in created}, windows={})
    return SimpleNamespace(facts=facts, collected=Collected(diff=diff, workdir="/testbed"), cache={}, rubric=SimpleNamespace(artifacts={}))


def test_temporary_repository_files_count_with_scratch():
    writes = [WriteEvent(path="fix_test.py", step=3, op="create"), WriteEvent(path="tests/tmp_x.py", step=4, op="create"),
              WriteEvent(path="tests/tmp_x.py", step=6, op="delete"), WriteEvent(path="src/a.py", step=5, op="edit")]
    ctx = _repo_ctx({"fix_test.py": "?", "src/a.py": "M"}, writes, created=["tests/tmp_x.py"])
    item = SimpleNamespace(id="x", stage="global", check=SimpleNamespace(params={"pattern": r"(?:^|/)repro[^/]*\.py$"}), target=SimpleNamespace(type="action"))
    assert C.created_files(item, ctx).status == "pass"  # as before: neither name matches the pattern
    item.check.params["scratch"] = True
    r = C.created_files(item, ctx)
    assert r.status == "fail" and r.detail.startswith("3 created")  # fix_test.py (a top-level throwaway), tests/tmp_x.py (made and removed)


def test_code_change_needs_a_source_file_of_the_final_change():
    writes = [WriteEvent(path="tests/test_a.py", step=3, op="edit"), WriteEvent(path="src/a.py.bak", step=4, op="create")]
    ctx = _repo_ctx({"tests/test_a.py": "M", "src/a.py.bak": "?"}, writes)
    assert list(REFS.matching(ctx, {"fact": "repo_edit", "final": True}))  # as before: any final repository edit
    assert not list(REFS.matching(ctx, {"fact": "repo_edit", "final": True, "source": True}))
    ctx = _repo_ctx({"src/a.py": "M"}, [WriteEvent(path="src/a.py", step=5, op="edit")])
    assert list(REFS.matching(ctx, {"fact": "repo_edit", "final": True, "source": True}))


# ---- D-4: a file the run never wrote is not read ------------------------------------------------------------


def test_an_absent_artifact_counts_as_not_read():
    ctx = SimpleNamespace(facts=SimpleNamespace(artifact_paths={}, n_steps=10), run=SimpleNamespace(steps=[]), collected=SimpleNamespace(workdir="/testbed"))
    item = SimpleNamespace(id="x", stage="global", check=SimpleNamespace(params={"artifacts": ["requirements"]}), target=SimpleNamespace(type="action", ref="run"))
    assert C.read(item, ctx).status == "not_applicable"  # as before
    item.check.params["absent_unread"] = True
    assert C.read(item, ctx).status == "fail"


def test_the_create_tasks_read_item_keeps_the_old_reading_of_an_absent_artifact():
    """User decision 2026-11-21: D-4 is on for every read item but the create-tasks one."""
    reads = {it["id"]: it["check"]["params"] for it in RUBRIC["items"] if it["check"]["kind"] == "agentos_bugfix.read"}
    assert len(reads) == 5
    assert [i for i, p in reads.items() if not p.get("absent_unread")] == ["agentos_bugfix.create_tasks.run.agentos_bugfix_read.spec_inputs"]
    p = reads["agentos_bugfix.create_tasks.run.agentos_bugfix_read.spec_inputs"]
    assert p.get("written_before") is True and p["artifacts"] == ["spec", "requirements"]
    # the rule under those parameters: an artifact that was never written leaves the list, none written is not applicable
    spec = "/tmp/agent-os/specs/s/spec.md"
    f = SimpleNamespace(artifact_paths={"spec": spec, "requirements": None}, writes={spec: [WriteEvent(path=spec, step=12, op="create", content="x")]}, n_steps=50)
    ctx = SimpleNamespace(facts=f, run=SimpleNamespace(steps=[]), collected=SimpleNamespace(workdir="/testbed"))
    item = SimpleNamespace(id="x", stage="create_tasks", check=SimpleNamespace(params={"artifacts": ["spec", "requirements"], "written_before": True, "window": [30, 40]}), target=SimpleNamespace(type="action", ref="run"))
    old = C._window
    C._window = lambda item, ctx: (30, 40)
    try:
        r = C.read(item, ctx)
        assert r.status == "pass" and r.score == 1.0  # spec.md is in the conversation; requirements.md is not asked for
        f.artifact_paths = {"spec": None, "requirements": None}
        assert C.read(item, ctx).status == "not_applicable"
    finally:
        C._window = old




# ---- D-5: a run with no repository write is judged on the rest of the order chain -----------------------------

from recipe.grpo.qwen3_5.workflow_rubric.checks import actions as ACT  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import DocRead, Facts  # noqa: E402


def test_an_absent_first_repository_write_leaves_the_chain():
    f = Facts(n_steps=20)
    f.doc_reads = {"IT": [DocRead(doc="IT", step=3, via="command", coverage=1.0)]}
    rubric = SimpleNamespace(artifacts={}, scoring={}, items=[])
    ctx = SimpleNamespace(facts=f, rubric=rubric, quality={}, cache={}, collected=Collected(workdir="/testbed"))
    p = {"chain": ["read:IT", "first_repo_write", "read:IT"]}
    assert ACT.order(_item(dict(p)), ctx).score == 0.0
    r = ACT.order(_item({**p, "skip_if_absent": ["first_repo_write"]}), ctx)
    assert r.score == 0.0 and r.detail.startswith("0/1")  # one pair left (read:IT, read:IT), not two


# ---- D-3: reading the next document early does not close a stage before its file is written --------------------

from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, DocRead, Facts, WriteEvent  # noqa: E402
from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward.eval import Evaluation as BugfixEvaluation  # noqa: E402

SPEC = "/tmp/agent-os/specs/2026-11-13-x"


def _windows(close: bool):
    rubric = BugfixEvaluation().rubric
    if not close:
        rubric = SimpleNamespace(**{**vars(rubric), "scoring": {k: v for k, v in rubric.scoring.items() if k != "close_on_artifact"}})
    f = Facts(n_steps=60)
    w = lambda path, step, op="create": WriteEvent(path=SPEC + path, step=step, op=op, content="x")  # noqa: E731
    f.writes = {SPEC + "/planning/initialization.md": [w("/planning/initialization.md", 5)],
                SPEC + "/planning/requirements.md": [w("/planning/requirements.md", 8), w("/planning/requirements.md", 9, "append"), w("/planning/requirements.md", 20, "edit")],
                SPEC + "/spec.md": [w("/spec.md", 26)], SPEC + "/tasks.md": [w("/tasks.md", 30)]}
    f.doc_reads = {d: [DocRead(doc=d, step=s, via="command", coverage=1.0)] for d, s in (("SS", 2), ("WS", 7), ("CT", 28), ("IT", 31))}
    f.repo_writes = [WriteEvent(path="src/a.py", step=35, op="edit")]
    F._windows(f, rubric, Collected(workdir="/testbed"))
    return f.windows


def test_a_stage_whose_next_document_was_read_early_ends_after_its_file():
    assert _windows(close=False)["shape_spec"] == (2, 7)  # as before: closed by the early read of write-spec
    w = _windows(close=True)
    assert w["shape_spec"] == (2, 21)  # the writes of requirements.md up to spec.md's first write belong to shape-spec
    assert w["write_spec"][0] == 7  # write-spec keeps its start: the early read is the order item's to count
    assert w["create_tasks"] == _windows(close=False)["create_tasks"]




# ---- D-1: the runs a report is compared with when PHASE 3 cannot be placed --------------------------------------


def test_the_fallback_window_starts_after_the_last_code_change_and_tasks_write(monkeypatch):
    tasks = "/tmp/agent-os/specs/s/tasks.md"
    monkeypatch.setattr(C.refs, "event", lambda ctx, ev: 40)  # the report's first write
    monkeypatch.setattr(C, "_change_steps", lambda ctx, w, authored=False: [12, 20])
    ctx = SimpleNamespace(facts=SimpleNamespace(artifact_paths={"tasks": tasks}, writes={tasks: [WriteEvent(path=tasks, step=s, op="edit") for s in (25, 30, 45)]}, n_steps=50),
                          rubric=SimpleNamespace(artifacts={"final_verification": None}))
    assert C.fallback_window(ctx) == (31, 40)  # after the last tasks.md write before the report (30), not the code change (20)
    monkeypatch.setattr(C, "_change_steps", lambda ctx, w, authored=False: [])
    assert C.fallback_window(ctx) is None


def test_a_report_on_check_scripts_is_read_against_their_last_results():
    rep = "## 2. Test Suite Results\n**Status:** {}\n### Test Summary\n- **Total Tests:** 3 test groups\n- **Passing:** 3\n- **Failing:** {}\n- **Errors:** 0\n"
    item = lambda rule: _item({"rule": rule}, ref="final_verification")  # noqa: E731
    passed = {"/s/checks/test_a.py": "pass"}
    failed = {"/s/checks/test_a.py": "fail"}
    assert C._report_on_scripts(item("suite_status"), "suite_status", rep.format("✅ All Passing", 0), "2. Test Suite Results", passed).status == "pass"
    assert C._report_on_scripts(item("suite_status"), "suite_status", rep.format("✅ All Passing", 0), "2. Test Suite Results", failed).status == "fail"
    assert C._report_on_scripts(item("test_counts"), "test_counts", rep.format("✅ All Passing", 0), "2. Test Suite Results", passed).status == "pass"
    assert C._report_on_scripts(item("test_counts"), "test_counts", rep.format("❌ Critical Failures", 0), "2. Test Suite Results", failed).status == "fail"
    assert C._report_on_scripts(item("failed_listed"), "failed_listed", rep.format("✅ All Passing", 0), "2. Test Suite Results", passed).status == "not_applicable"
    assert C._report_on_scripts(item("failed_listed"), "failed_listed", rep.format("❌ Critical Failures", 1) + "test_a.py fails\n", "2. Test Suite Results", failed).status == "pass"
