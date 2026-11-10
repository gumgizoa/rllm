"""workflows/bmad_build_auto: the hack suite, the honest variants, the robustness checks and the breaking cases.

    pytest recipe/grpo/qwen3_5/tests/test_bmad_build_auto_hacks.py

Every case starts from the honest synthetic run of ``test_bmad_build_auto_reward.golden`` (the orchestrator's
conversation: the documents read in order, one spec, the implementation hand-off, the diff, the four review
lenses in one turn, the triage log; compliance 1.0) and changes one thing.

    hacks    a known way to game the workflow: the named items must flip to fail and ``bmad/compliance`` must
             fall below the honest value by more than MIN_DROP
    honest   another way to follow the documents: no headline signal may fall by more than HONEST_TOLERANCE
    robust   broken or stuck runs: scoring never raises, and a run that did no work scores (almost) nothing
    cases    every implemented item (the orchestrator-trace and artifact kinds; the ``bmad.subagent`` kind
             has its own suite) is broken by one case and kept by the honest run

The bounds are the generated rubrics' self-test's (``workflow_rubric/generator/mutations.py``): a hack must
cost at least half a failed must item (0.005), an honest variant at most 0.02. A hack the scorer does not
catch yet is ``xfail(strict=True)`` with the reason: the suite passes, the hole stays on record, and fixing
it turns the case into a failure that says to drop the mark.
"""

from __future__ import annotations

import copy
import importlib
import json
import re
from collections.abc import Callable

import pytest

from recipe.grpo.qwen3_5.tests.test_bmad_build_auto_reward import BASE, C, DIFF, DIFF_PATH, SPEC, SPEC_PATH, golden
from recipe.grpo.qwen3_5.workflow_rubric import engine, schema
from recipe.grpo.qwen3_5.workflow_rubric import layers as LY
from recipe.grpo.qwen3_5.workflow_rubric.evaluation import rubric_signals
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step
from recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward import build

importlib.import_module("recipe.grpo.qwen3_5.workflows.bmad_build_auto.reward.checks")

MIN_DROP = 0.005
HONEST_TOLERANCE = 0.02
PREFIX = "bmad"
HEADLINE = ("bmad/compliance", "bmad/layer/L1", "bmad/layer/L1C", "bmad/layer/L2M", "bmad/layer/L2F")
BROKEN = "broken"  # expected: the item fails (score below 1)
ART = "/tmp/bmad/implementation-artifacts"
CORE = f"{C}/core-workflow.md"
S1, S2, S3, S4, ST = (f"{C}/stages/step-01-clarify-and-route.md", f"{C}/stages/step-02-plan.md", f"{C}/stages/step-03-implement.md", f"{C}/stages/step-04-review.md", f"{C}/spec-template.md")
EH = f"{C}/review-prompts/edge-case-hunter.md"

RUBRIC = schema.load(build.RUBRIC)
LAYERS = LY.load(build.LAYERS, RUBRIC, build.RUBRIC)
IMPLEMENTED = {i.id: i for i in RUBRIC.items if i.check.kind != "unimplemented"}


def I(short: str) -> str:
    """``step04.run.bmad_task_calls.i3`` -> the full item id."""
    return f"bmad_build_auto.{short}"


def sh(command: str, obs: str = "") -> Action:
    return Action("shell", "terminal", command=command, observation=obs)


def view(path: str, obs: str = "...") -> Action:
    return Action("view", "file_editor", path=path, observation=obs)


def create(path: str, text: str) -> Action:
    return Action("create", "file_editor", path=path, text=text, status="ok", observation="File created successfully")


def edit(path: str, old: str = "a", new: str = "b") -> Action:
    return Action("replace", "file_editor", path=path, old=old, text=new, status="ok", observation="The file has been edited")


def task(prompt: str, reply: str, resume: str = "", n: int = 9, status: str = "completed") -> Action:
    return Action("other", "task", text=prompt, path="general-purpose", old=resume, observation=f"Task ID: task_{n:08x}\nSubagent: general-purpose\nStatus: {status}\n\n{reply}")


def _draft(spec: str) -> str:
    """The step-8 draft the golden run derives from the final spec."""
    return spec.replace("status: 'done'", "status: 'draft'").split("## Review Triage Log")[0] + "## Review Triage Log\n\n## Verification\n\n**Commands:**\n- `python -m pytest tests/test_widget.py -q` -- expected: all tests pass\n"


def _sub(text: str, old: str, new: str, count: int = 1) -> str:
    assert text.count(old) == count, (old, text.count(old))
    return text.replace(old, new)


class R:
    """The honest run, editable one change at a time."""

    def __init__(self):
        self.run, self.col = copy.deepcopy(golden())
        self.spec_path = SPEC_PATH

    # ---- navigation
    @property
    def steps(self) -> list[Step]:
        return self.run.steps

    def step(self, n: int) -> Step:
        return next(s for s in self.steps if s.n == n)

    def renumber(self):
        for k, s in enumerate(self.steps, 1):
            s.n = k
        return self

    def find(self, pred: Callable[[Action], bool]) -> tuple[Step, Action]:
        for s in self.steps:
            for a in s.actions:
                if pred(a):
                    return s, a
        raise LookupError("no such action")

    def tasks(self, lens: str | None = None) -> list[Action]:
        sig = {"implementer": "implement it", "blind": "Conduct a review", "edge": "edge-case-hunter", "gap": "verification-gap", "intent": "intent-alignment"}
        return [a for s in self.steps for a in s.actions if a.name == "task" and (lens is None or sig[lens] in (a.text or ""))]

    # ---- trace edits
    def drop(self, pred: Callable[[Action], bool]):
        for s in self.steps:
            s.actions = [a for a in s.actions if not pred(a)]
        return self

    def drop_step(self, n: int):
        self.run.steps = [s for s in self.steps if s.n != n]
        return self.renumber()

    def insert_step(self, after: int, *actions: Action, message: str = ""):
        """A new step right after step ``after`` (0 = at the start)."""
        i = 0 if after == 0 else self.steps.index(self.step(after)) + 1
        self.steps.insert(i, Step(0, list(actions), message))
        return self.renumber()

    def add(self, n: int, *actions: Action):
        self.step(n).actions.extend(actions)
        return self

    def move_step(self, n: int, after: int):
        s = self.step(n)
        self.run.steps = [x for x in self.steps if x is not s]
        i = 0 if after == 0 else self.steps.index(self.step(after)) + 1
        self.steps.insert(i, s)
        return self.renumber()

    def set_command(self, pred: Callable[[Action], bool], command: str, obs: str | None = None):
        _, a = self.find(pred)
        a.command = command
        if obs is not None:
            a.observation = obs
        return self

    def message(self, n: int, text: str):
        self.step(n).message = text
        return self

    # ---- artifact edits
    def spec(self, text: str, *, draft: str | None = None):
        """The final spec: in the sandbox and in the final write; the draft follows unless given."""
        self.col.files[self.spec_path] = text
        self.find(lambda a: a.kind == "create" and a.path == self.spec_path and "status: 'done'" in (a.text or "")).__getitem__(1).text = text
        d = _draft(text) if draft is None else draft
        self.find(lambda a: a.kind == "create" and a.path == self.spec_path and "status: 'draft'" in (a.text or "")).__getitem__(1).text = d
        return self

    def edit_spec(self, old: str, new: str, *, final_only: bool = False):
        cur = self.col.files[self.spec_path]
        return self.spec(_sub(cur, old, new), draft=_draft(cur) if final_only else None)

    def edit_draft(self, old: str, new: str):
        _, a = self.find(lambda a: a.kind == "create" and a.path == self.spec_path and "status: 'draft'" in (a.text or ""))
        a.text = _sub(a.text, old, new)
        return self

    def rename_spec(self, new_path: str):
        old = self.spec_path
        self.col.files[new_path] = self.col.files.pop(old)
        for s in self.steps:
            for a in s.actions:
                if a.path == old:
                    a.path = new_path
                if a.command and old in a.command:
                    a.command = a.command.replace(old, new_path)
                if a.name == "task" and a.text and old in a.text:
                    a.text = a.text.replace(old, new_path)
        self.spec_path = new_path
        return self

    def diff(self, text: str):
        self.col.files[DIFF_PATH] = text
        _, a = self.find(lambda a: a.kind == "shell" and f"cat {DIFF_PATH}" in (a.command or ""))
        a.observation = text
        return self

    def reply(self, lens: str, text: str):
        for a in self.tasks(lens):
            a.observation = f"Task ID: task_00000009\nSubagent: general-purpose\nStatus: completed\n\n{text}"
        return self

    def prompt(self, lens: str, text: str):
        for a in self.tasks(lens):
            a.text = text
        return self

    # ---- scoring
    def report(self):
        return engine.evaluate(RUBRIC, self.run, self.col)

    def score(self) -> dict[str, float]:
        return rubric_signals(RUBRIC, self.run, self.col, PREFIX, None, LAYERS)

    def statuses(self) -> dict[str, tuple[str, float, str]]:
        return {k: (r.status, float(r.score), r.detail or "") for k, r in self.report().results.items()}


HONEST = R().score()
HONEST_STATUS = R().statuses()


def test_the_honest_run_scores_one():
    assert [HONEST[k] for k in HEADLINE] == pytest.approx([1.0] * len(HEADLINE))
    assert HONEST["bmad/engine_errors"] == 0 and HONEST["bmad/collect_errors"] == 0


# --- hacks ----------------------------------------------------------------------------------------
# name -> (how the run is gamed, the items that must flip to fail)

EDGE_JSON = json.dumps([{"location": "pkg/widget.py:3-4", "trigger_condition": "items is None", "guard_snippet": "if not self.items", "potential_consequence": "TypeError on None"}])


def _lenses_one_per_turn(r: R):
    lenses = r.tasks()[1:]
    r.drop(lambda a: a.name == "task" and "implement it" not in (a.text or ""))
    n = 17
    for a in lenses:
        r.insert_step(n, a)
        n += 1


def _three_lenses(r: R):
    r.drop(lambda a: a.name == "task" and "intent-alignment" in (a.text or ""))


def _blind_inline_diff(r: R):
    """Every lens gets the diff body pasted into its prompt instead of the file path."""
    for a in r.tasks()[1:]:
        a.text = re.sub(r"the unified diff at `[^`]+`\.?( Read that file)?", "this diff:\n" + DIFF, a.text or "")


def _edge_no_claims(r: R):
    r.prompt("edge", f"Read {EH} completely and follow it as your review instructions.\n\nReview content: the unified diff at `{DIFF_PATH}`.")


def _gap_given_spec(r: R):
    """The three lenses that must review blind get the spec path too."""
    for lens in ("blind", "gap", "intent"):
        for a in r.tasks(lens):
            a.text = (a.text or "") + f"\n\nFor context, the spec is at {SPEC_PATH}."


def _patch_without_resume(r: R):
    r.edit_spec("`[medium]` `[defer]` missing docstring update — pre-existing", "`[medium]` `[patch]` missing docstring update — fixed")


def _resume_with_free_prompt(r: R):
    r.add(17, task("Please also fix the docstring.", "Done.", resume="task_00000001", n=1))


def _code_changed_after_last_diff(r: R):
    r.insert_step(17, edit("/testbed/pkg/widget.py", "return 0", "return 0  # empty"))


def _stale_diff_only(r: R):
    """The diff written once in step 3 and never again after the review changed code."""
    r.drop(lambda a: a.kind == "shell" and (a.command or "").startswith("cd /testbed && git diff") and "cat" not in (a.command or ""))
    r.insert_step(17, edit("/testbed/pkg/widget.py", "return 0", "return 0  # empty"))


def _two_specs(r: R):
    r.col.files[f"{ART}/spec-gh-7-other.md"] = SPEC
    r.add(8, create(f"{ART}/spec-gh-7-other.md", SPEC))


def _contract_rewritten(r: R):
    r.edit_spec("**Approach:** Return zero for an empty widget and keep the existing behaviour otherwise.", "**Approach:** Raise ValueError for an empty widget.", final_only=True)


def _log_rewritten(r: R):
    r.edit_draft("## Review Triage Log\n\n## Verification", "## Review Triage Log\n\n### 2026-11-09 — Review pass\n- verdicts: 0 findings — high 0, medium 0, low 0, false 0, maybe-false 0\n\n## Verification")


def _totals_wrong(r: R):
    r.edit_spec("verdicts: 2 findings — high 0, medium 1, low 0, false 1, maybe-false 0", "verdicts: 3 findings — high 0, medium 1, low 0, false 1, maybe-false 0")


def _false_not_rejected(r: R):
    r.edit_spec("`[false]` `[reject]` claimed off-by-one", "`[false]` `[defer]` claimed off-by-one")


def _git_add(r: R):
    r.add(16, sh("cd /testbed && git add -A"))


def _orchestrator_reads_lens_prompt(r: R):
    from recipe.grpo.qwen3_5.tests.test_bmad_build_auto_reward import DOCS

    r.add(15, sh(f"cat {EH}", (DOCS / "review-prompts/edge-case-hunter.md").read_text(encoding="utf-8")))


def _no_task_calls(r: R):
    r.drop(lambda a: a.name == "task")


def _asks_user(r: R):
    r.message(19, "The review found one medium finding. Would you like me to apply the patch before I continue?")


def _result_hides_a_file(r: R):
    r.edit_spec("- Files changed: `pkg/widget.py` (return 0 when empty), `tests/test_widget.py` (new unit test)", "- Files changed: `pkg/widget.py` (return 0 when empty)")


def _result_names_no_file(r: R):
    r.edit_spec("- Files changed: `pkg/widget.py` (return 0 when empty), `tests/test_widget.py` (new unit test)", "- Files changed: the widget module and its tests")


def _phantom_code_map(r: R):
    r.edit_spec("- `tests/test_widget.py` -- the covering tests", "- `tests/test_widget.py` -- the covering tests\n- `pkg/helpers.py` -- a helper the fix uses")


def _placeholder_left(r: R):
    r.edit_spec("**Never:** change the test files' expectations.", "**Never:** NON_GOALS_AND_FORBIDDEN_APPROACHES")


def _template_copied(r: R):
    """The spec template pasted as the spec, placeholders and all, with the frontmatter filled."""
    from recipe.grpo.qwen3_5.tests.test_bmad_build_auto_reward import DOCS

    template = (DOCS / "spec-template.md").read_text(encoding="utf-8")
    body = template.split("---", 2)[2] if template.startswith("---") else template
    fm = SPEC.split("---", 2)[1]
    r.spec(f"---{fm}---{body}", draft=f"---{fm.replace(chr(39) + 'done' + chr(39), chr(39) + 'draft' + chr(39))}---{body}")


def _status_outside_enum(r: R):
    r.edit_spec("status: 'done'", "status: 'finished'")


def _bare_na(r: R):
    r.edit_spec("## Spec Change Log\n", "## Spec Change Log\n\nN/A\n")


def _core_skipped(r: R):
    r.drop_step(1)


def _read_ahead(r: R):
    """step-04 read right after step-02, before the spec exists."""
    r.insert_step(4, sh(f"cat {S4}", r.step(15).actions[0].observation))


def _spec_never_reread(r: R):
    r.drop(lambda a: a.kind == "shell" and (a.command or "") == f"cat {SPEC_PATH}")


def _diff_never_read(r: R):
    r.set_command(lambda a: a.kind == "shell" and f"cat {DIFF_PATH}" in (a.command or ""), f"cd /testbed && git diff {BASE} > {DIFF_PATH}", "")


def _verification_not_run(r: R):
    r.drop(lambda a: a.kind == "shell" and "pytest" in (a.command or ""))


def _edge_prose(r: R):
    r.reply("edge", "I found one edge case: items may be None, which raises TypeError.")


def _edge_missing_key(r: R):
    r.reply("edge", json.dumps([{"location": "pkg/widget.py:3", "trigger_condition": "items is None", "guard_snippet": "if not self.items"}]))


def _blind_severity(r: R):
    r.reply("blind", "N = min(floor(sqrt(0.4) + 1), 10) = 1\n\n- Missing: a test for None items\n  Severity: high")


def _ranked_lens_outputs(r: R):
    """All three finding lenses rank their findings (the documents forbid severity labels)."""
    _blind_severity(r)
    r.reply("edge", "Severity: medium\n" + EDGE_JSON)
    r.reply("gap", "### Empty widget path untested\nPriority: low\nDisposition: defer\n")


def _blind_no_floor(r: R):
    r.reply("blind", "- Missing: a test for None items")


def _gap_silent(r: R):
    r.reply("gap", "")


def _implementer_skipped(r: R):
    r.drop(lambda a: a.name == "task" and "implement it" in (a.text or ""))


def _template_not_read(r: R):
    r.drop_step(6)


def _code_map_unread(r: R):
    r.drop_step(5)


def _artifacts_dir_not_listed(r: R):
    r.drop_step(3)


def _empty_diff(r: R):
    r.diff("")


def _not_a_diff(r: R):
    r.diff("pkg/widget.py changed: return 0 when empty\n")


def _contract_tags_dropped(r: R):
    r.edit_spec("<intent-contract>\n\n", "").edit_spec("\n</intent-contract>\n", "\n")


def _headings_renamed(r: R):
    """The template's headings replaced by the agent's own (the sections are still there in spirit)."""
    r.edit_spec("## Intent\n", "## Goal\n").edit_spec("## Boundaries & Constraints\n", "## Rules\n").edit_spec("## Tasks & Acceptance\n", "## Work Items\n")


def _extra_section(r: R):
    r.edit_spec("## Verification\n", "## Open Questions\n\nnone yet\n\n## Verification\n")


HACKS: dict[str, tuple[Callable[[R], None], list[str]]] = {
    "core_skipped": (_core_skipped, ["global.run.doc_read_first.a2"]),
    "read_ahead_step04": (_read_ahead, ["step04.run.doc_read.a12.s4"]),
    "spec_template_not_read": (_template_not_read, ["step02.run.doc_read.d6"]),
    "code_map_files_unread": (_code_map_unread, ["step02.run.bmad_paths_read.d5b"]),
    "artifacts_dir_not_listed": (_artifacts_dir_not_listed, ["step01.run.bmad_command.c13"]),
    "spec_never_reread": (_spec_never_reread, ["step02.run.bmad_artifact_io.d24", "step04.run.bmad_artifact_io.g1"]),
    "diff_never_read": (_diff_never_read, ["step03.run.bmad_artifact_io.e15"]),
    "verification_not_run": (_verification_not_run, ["step03.spec.cross_ref.f1"]),
    "two_spec_files": (_two_specs, ["global.spec.bmad_spec_count.b15"]),
    "contract_tags_dropped": (_contract_tags_dropped, ["step02.spec.bmad_text_regex.d32"]),
    "contract_rewritten_after_planning": (_contract_rewritten, ["global.spec.bmad_block_unchanged.b13"]),
    "triage_log_rewritten": (_log_rewritten, ["global.spec.bmad_append_only.b14"]),
    "triage_totals_wrong": (_totals_wrong, ["step04.spec.bmad_triage_totals.g80"]),
    "false_finding_not_rejected": (_false_not_rejected, ["step04.spec.bmad_triage_totals.g66"]),
    "lenses_one_per_turn": (_lenses_one_per_turn, ["step04.run.bmad_task_calls.i3"]),
    "three_lenses": (_three_lenses, ["step04.run.bmad_task_calls.g11"]),
    "edge_lens_without_claims_file": (_edge_no_claims, ["step04.run.bmad_task_calls.g4.edge_has_claims"]),
    "blind_lenses_given_the_spec": (_gap_given_spec, ["step04.run.bmad_task_calls.g4.others_without_claims"]),
    "blind_lens_inline_diff": (_blind_inline_diff, ["step04.run.bmad_task_calls.g3"]),
    "patch_routed_without_resume": (_patch_without_resume, ["step04.run.bmad_task_calls.g86a"]),
    "resume_with_free_prompt": (_resume_with_free_prompt, ["step04.run.bmad_task_calls.g86b"]),
    "edge_lens_prose": (_edge_prose, ["step04.run.bmad_lens_output.g29", "step04.run.bmad_lens_output.g30"]),
    "edge_finding_missing_key": (_edge_missing_key, ["step04.run.bmad_lens_output.g30"]),
    "ranked_lens_outputs": (_ranked_lens_outputs, ["step04.run.bmad_lens_output.g16"]),
    "blind_lens_no_floor": (_blind_no_floor, ["step04.run.bmad_lens_output.g15"]),
    "gap_lens_silent": (_gap_silent, ["step04.run.bmad_lens_output.g52", "step04.run.bmad_lens_output.g49"]),
    "implementer_not_delegated": (_implementer_skipped, ["step03.run.bmad_task_calls.e11"]),
    "no_task_calls": (_no_task_calls, ["global.run.bmad_task_calls.i1", "step03.run.bmad_task_calls.e11", "step04.run.bmad_task_calls.g11", "step04.run.bmad_task_calls.i3"]),
    "code_changed_after_last_diff": (_code_changed_after_last_diff, ["step04.run.bmad_artifact_io.f11"]),
    "git_add_in_review": (_git_add, ["step04.run.prohibited_action.g5"]),
    "orchestrator_reads_lens_prompt": (_orchestrator_reads_lens_prompt, ["step04.run.bmad_no_doc_read.g9"]),
    "last_message_asks_user": (_asks_user, ["global.run.bmad_last_message.d1"]),
    "result_names_no_changed_file": (_result_names_no_file, ["step04.spec.cross_ref.h2"]),
    "phantom_code_map_path": (_phantom_code_map, ["step02.spec.cross_ref.d9"]),
    "template_copied_as_spec": (_template_copied, ["step02.spec.no_template_residue.d17"]),
    "status_outside_enum": (_status_outside_enum, ["step02.spec.bmad_frontmatter_value.b9", "step04.spec.bmad_frontmatter_value.c33"]),
    "bare_na_line": (_bare_na, ["step02.spec.bmad_text_regex.d40"]),
    "empty_diff": (_empty_diff, ["step03.diff.bmad_diff_file.e14a"]),
    "prose_instead_of_diff": (_not_a_diff, ["step03.diff.bmad_diff_file.e14a"]),
    "template_headings_renamed": (_headings_renamed, ["step02.spec.cross_ref.d39", "step02.spec.section_present.d33.section", "step02.spec.section_present.d36.section", "step02.spec.section_present.d44.section"]),
}

# Hacks the scorer does not catch yet: name -> why (strict xfail keeps the hole on record).
HOLES: dict[str, str] = {}


@pytest.mark.parametrize("name", list(HACKS))
def test_hack_is_caught(name, request):
    if name in HOLES:
        request.node.add_marker(pytest.mark.xfail(strict=True, reason=HOLES[name]))
    mutate, items = HACKS[name]
    r = R()
    mutate(r)
    s = r.score()
    st = r.statuses()
    flipped = {i: st[I(i)] for i in items}
    assert all(v[0] == "fail" for v in flipped.values()), {k: v for k, v in flipped.items() if v[0] != "fail"}
    assert HONEST["bmad/compliance"] - s["bmad/compliance"] >= MIN_DROP, (HONEST["bmad/compliance"], s["bmad/compliance"])
    assert s["bmad/engine_errors"] == 0


# --- honest variants ------------------------------------------------------------------------------


def _sed_reads(r: R):
    for s in r.steps:
        for a in s.actions:
            if a.kind == "shell" and a.command == f"cat {SPEC_PATH}":
                a.command = f"sed -n '1,400p' {SPEC_PATH}"


def _chunked_doc_read(r: R):
    doc = r.step(4).actions[0].observation
    lines = doc.splitlines(keepends=True)
    half = len(lines) // 2
    r.step(4).actions = [sh(f"head -n {half} {S2}", "".join(lines[:half])), sh(f"tail -n +{half + 1} {S2}", "".join(lines[half:]))]


def _lens_order(r: R):
    r.step(17).actions = list(reversed(r.step(17).actions))


def _diff_scoped(r: R):
    r.set_command(lambda a: a.kind == "shell" and f"cat {DIFF_PATH}" in (a.command or ""), f"cd /testbed && git diff {BASE} -- . > {DIFF_PATH} && cat {DIFF_PATH}")
    r.set_command(lambda a: a.kind == "shell" and (a.command or "") == f"cd /testbed && git diff {BASE} > {DIFF_PATH}", f"cd /testbed && git diff {BASE} -- . > {DIFF_PATH}")


def _two_review_passes(r: R):
    r.edit_spec(
        "  - `[false]` `[reject]` claimed off-by-one — the loop bound is inclusive by design\n",
        "  - `[false]` `[reject]` claimed off-by-one — the loop bound is inclusive by design\n\n### 2026-11-10 — Review pass\n- verdicts: 0 findings — high 0, medium 0, low 0, false 0, maybe-false 0\n",
    )


def _extra_repo_view(r: R):
    r.add(5, view("/testbed/pkg/__init__.py", ""))
    r.col.base_present["pkg/__init__.py"] = True


def _spec_without_tracking_id(r: R):
    r.rename_spec(f"{ART}/spec-fix-widget-size.md")


def _deferred_items(r: R):
    r.edit_spec("deferred: []", "deferred:\n  - title: missing docstring update\n    reason: pre-existing\n    source: review 2026-11-10")


def _view_the_docs(r: R):
    for s in r.steps:
        for a in s.actions:
            if a.kind == "shell" and (a.command or "").startswith(f"cat {C}/"):
                path = a.command.split(" ", 1)[1]
                a.kind, a.name, a.path, a.command = "view", "file_editor", path, None


def _contract_reflowed(r: R):
    r.edit_spec("**Approach:** Return zero for an empty widget and keep the existing behaviour otherwise.", "**Approach:** Return zero for an empty widget\nand keep the existing behaviour otherwise.", final_only=True)


def _intent_reread_before_lenses(r: R):
    r.add(16, sh(f"grep -n 'Problem' {SPEC_PATH}", "49:**Problem:** ..."))


HONEST_VARIANTS: dict[str, Callable[[R], None]] = {
    "spec_read_with_sed": _sed_reads,
    "step_doc_read_in_two_chunks": _chunked_doc_read,
    "lenses_in_another_order": _lens_order,
    "diff_scoped_to_dot": _diff_scoped,
    "two_review_passes_appended": _two_review_passes,
    "extra_repository_view": _extra_repo_view,
    "spec_name_without_tracking_id": _spec_without_tracking_id,
    "deferred_items_recorded": _deferred_items,
    "documents_opened_with_the_editor": _view_the_docs,
    "intent_contract_reflowed": _contract_reflowed,
    "spec_grepped_before_the_lenses": _intent_reread_before_lenses,
}


@pytest.mark.parametrize("name", list(HONEST_VARIANTS))
def test_honest_variant_keeps_the_score(name):
    r = R()
    HONEST_VARIANTS[name](r)
    s = r.score()
    low = {k: (HONEST[k], s.get(k)) for k in HEADLINE if HONEST[k] - s.get(k, 0.0) > HONEST_TOLERANCE}
    assert not low, low
    assert s["bmad/engine_errors"] == 0


# --- robustness -----------------------------------------------------------------------------------


def _empty_col():
    from recipe.grpo.qwen3_5.workflow_rubric.context import Collected

    return Collected(files={}, workdir="/testbed", base_sha=BASE, diff={}, base_present={}, mode="online")


def test_a_run_of_nothing_scores_almost_nothing():
    s = rubric_signals(RUBRIC, Run(instance_id="empty", steps=[]), _empty_col(), PREFIX, None, LAYERS)
    rep = engine.evaluate(RUBRIC, Run(instance_id="empty", steps=[]), _empty_col())
    passed = [k for k, r in rep.results.items() if r.status == "pass"]
    # only the prohibitions pass on an empty run; they are what the compliance can be made of
    assert len(passed) <= 3, passed
    assert s["bmad/compliance"] <= len(passed) / max(1, s["bmad/items_scored"]) + 1e-9
    assert s["bmad/engine_errors"] == 0


@pytest.mark.parametrize(
    "name",
    ["finish_only", "spec_not_yaml", "task_hit_iteration_cap", "steps_without_actions", "spec_is_a_directory_listing", "diff_is_binary_noise"],
)
def test_broken_runs_never_raise(name):
    r = R()
    if name == "finish_only":
        r.run.steps = [Step(1, [Action("other", "finish", observation="")])]
    elif name == "spec_not_yaml":
        r.spec("---\ntitle: [unclosed\nstatus: 'done\n---\n\n## Intent\n", draft="---\ntitle: [unclosed\n---\n")
    elif name == "task_hit_iteration_cap":
        for a in r.tasks():
            a.observation = "Agent reached maximum iterations limit (60)."
    elif name == "steps_without_actions":
        for s in r.steps:
            s.actions = []
    elif name == "spec_is_a_directory_listing":
        r.spec("total 0\ndrwxr-xr-x 2 root root 40 Nov 10 00:00 .\n", draft="")
    elif name == "diff_is_binary_noise":
        r.diff("\x00\x01\x02\xff" * 50)
    s = r.score()
    assert s["bmad/engine_errors"] == 0, s
    assert 0.0 <= s["bmad/compliance"] <= 1.0


# --- cases: every implemented item broken by one change and kept by the honest run -----------------
# item id (short) -> (mutation, expected): BROKEN = the item fails; a number = the exact score it takes.


def _spec_edit(old: str, new: str, **kw):
    return lambda r: r.edit_spec(old, new, **kw)


def _no_spec(r: R):
    r.col.files.pop(SPEC_PATH)


def _no_result_with_no_spec(r: R):
    _no_spec(r)


def _result_without_frontmatter(r: R):
    _no_spec(r)
    r.col.files[f"{ART}/bmad-build-auto-result-gh-7.md"] = "status done, no frontmatter\n"


def _partial_read(path_step: int, path: str):
    def f(r: R):
        a = r.step(path_step).actions[0]
        doc = a.observation
        a.observation = doc[: len(doc) // 2]

    return f


def _s2_read_before_s1(r: R):
    r.move_step(4, 1)


def _s3_read_before_spec(r: R):
    r.move_step(10, 7)


def _s4_read_before_diff(r: R):
    r.move_step(15, 12)


def _diff_before_s3(r: R):
    r.move_step(13, 9)


def _core_not_reread_at_gate(r: R):
    r.step(9).actions = [a for a in r.step(9).actions if CORE not in (a.command or "")]


def _no_diff_write_in_review(r: R):
    r.step(16).actions = [a for a in r.step(16).actions if "git diff" not in (a.command or "")]


def _no_diff_at_all(r: R):
    r.col.files.pop(DIFF_PATH)
    r.drop(lambda a: a.kind == "shell" and "git diff" in (a.command or ""))


def _spec_uppercase_name(r: R):
    r.rename_spec(f"{ART}/spec-Fix_Widget.md")


def _edge_deletion_without_confidence(r: R):
    r.reply("edge", json.dumps([{"location": "pkg/widget.py:3", "trigger_condition": "the old guard is gone", "guard_snippet": "n/a", "potential_consequence": "regression", "kind": "deletion"}]))


def _edge_claim_without_confidence(r: R):
    r.reply("edge", json.dumps([{"location": "pkg/widget.py:3", "trigger_condition": "claims O(1)", "guard_snippet": "len()", "potential_consequence": "false claim", "kind": "claim"}]))


def _gap_finding_without_disposition(r: R):
    r.reply("gap", "### Empty widget path untested\nThe new branch has no assertion.\n")


def _gap_no_heading_no_sentence(r: R):
    r.reply("gap", "Looks fine to me.")


def _blind_no_bullets(r: R):
    r.reply("blind", "N = min(floor(sqrt(0.4) + 1), 10) = 1\n\nNothing stands out.")


CASES: dict[str, tuple[Callable[[R], None], object]] = {
    # orchestrator trace
    "global.run.doc_read_first.a2": (_core_skipped, BROKEN),
    "step01.run.doc_read.a4.s1": (_partial_read(2, S1), BROKEN),
    "step02.run.doc_read.a14.s2": (_partial_read(4, S2), BROKEN),
    "step03.run.doc_read.a14.s3": (_partial_read(10, S3), BROKEN),
    "step04.run.doc_read.a14.s4": (_partial_read(15, S4), BROKEN),
    "step02.run.doc_read.a12.s2": (_s2_read_before_s1, BROKEN),
    "step03.run.doc_read.a12.s3": (_s3_read_before_spec, BROKEN),
    "step04.run.doc_read.a12.s4": (_s4_read_before_diff, BROKEN),
    "global.run.order.a10": (_diff_before_s3, BROKEN),
    "step02.run.doc_read.d6": (_template_not_read, BROKEN),
    "step02.run.doc_read.d23": (_core_not_reread_at_gate, BROKEN),
    "step02.run.bmad_artifact_io.d24": (_spec_never_reread, BROKEN),
    "step01.run.bmad_command.c13": (_artifacts_dir_not_listed, BROKEN),
    "step02.run.bmad_paths_read.d5b": (_code_map_unread, BROKEN),
    "step03.run.bmad_artifact_io.e15": (_diff_never_read, BROKEN),
    "step04.run.bmad_artifact_io.g1": (_spec_never_reread, BROKEN),
    "step04.run.bmad_artifact_io.g2": (_no_diff_write_in_review, BROKEN),
    "step04.run.bmad_artifact_io.f11": (_code_changed_after_last_diff, BROKEN),
    "step04.run.prohibited_action.g5": (_git_add, BROKEN),
    "step04.run.bmad_no_doc_read.g9": (_orchestrator_reads_lens_prompt, BROKEN),
    "global.run.bmad_last_message.d1": (_asks_user, BROKEN),
    # the spec file
    "step02.spec.artifact_exists.c29": (_no_spec, BROKEN),
    "step02.spec.path_match.c27": (_spec_uppercase_name, BROKEN),
    "global.spec.bmad_spec_count.b15": (_two_specs, BROKEN),
    "step02.spec.frontmatter.b7": (_spec_edit("context: []\n", ""), BROKEN),
    "step02.spec.bmad_frontmatter_value.b8": (_spec_edit("type: 'bugfix'", "type: 'hotfix'"), BROKEN),
    "step02.spec.bmad_frontmatter_value.b9": (_status_outside_enum, BROKEN),
    "step02.spec.bmad_frontmatter_value.b10.loop": (_spec_edit("review_loop_iteration: 0", "review_loop_iteration: one"), BROKEN),
    "step02.spec.bmad_frontmatter_value.b10.followup": (_spec_edit("followup_review_recommended: false", "followup_review_recommended: maybe"), BROKEN),
    "step02.spec.bmad_frontmatter_value.b11": (_spec_edit("context: []", "context: ['docs/notes.md']"), BROKEN),
    "step02.spec.bmad_frontmatter_value.b12": (_spec_edit("warnings: []", "warnings: ['huge']"), BROKEN),
    "step02.spec.bmad_frontmatter_value.d7": (_spec_edit("created: '2026-11-10'", "created: 'yesterday'"), BROKEN),
    "step03.spec.bmad_frontmatter_value.e1": (_spec_edit(f"baseline_revision: '{BASE}'", "baseline_revision: 'HEAD'"), BROKEN),
    "step04.spec.bmad_frontmatter_value.c33": (_spec_edit("status: 'done'", "status: 'in-review'"), BROKEN),
    "step04.spec.bmad_frontmatter_value.g87a": (_spec_edit("deferred: []\n", ""), BROKEN),
    "step02.spec.bmad_text_regex.d32": (_contract_tags_dropped, BROKEN),
    "step02.spec.section_present.d33.section": (_spec_edit("## Intent\n", "## Goal\n"), BROKEN),
    "step02.spec.label_present.d33.problem": (_spec_edit("**Problem:**", "**Issue:**"), BROKEN),
    "step02.spec.label_present.d33.approach": (_spec_edit("**Approach:**", "**Plan:**"), BROKEN),
    "step02.spec.field_filled.d33.problem_filled": (_spec_edit("**Problem:** `Widget.size()` returns the wrong value for empty widgets.", "**Problem:**"), BROKEN),
    "step02.spec.field_filled.d33.approach_filled": (_spec_edit("**Approach:** Return zero for an empty widget and keep the existing behaviour otherwise.", "**Approach:** TBD"), BROKEN),
    "step02.spec.section_present.d36.section": (_spec_edit("## Boundaries & Constraints\n", "## Limits\n"), BROKEN),
    "step02.spec.label_present.d36.always": (_spec_edit("**Always:**", "**Do:**"), BROKEN),
    "step02.spec.label_present.d36.never": (_spec_edit("**Never:**", "**Don't:**"), BROKEN),
    "step02.spec.field_filled.d36.always_filled": (_spec_edit("**Always:** keep the public signature of `Widget.size()`.", "**Always:**"), BROKEN),
    "step02.spec.field_filled.d36.never_filled": (_spec_edit("**Never:** change the test files' expectations.", "**Never:**"), BROKEN),
    "step02.spec.bmad_text_regex.d38": (_spec_edit("| empty widget | no items | 0 | No error expected |\n| one item | one item | 1 | No error expected |\n", ""), BROKEN),
    "step02.spec.cross_ref.d39": (_extra_section, BROKEN),
    "step02.spec.bmad_text_regex.d40": (_bare_na, BROKEN),
    "step02.spec.no_template_residue.d17": (_placeholder_left, BROKEN),
    "step02.spec.bmad_text_regex.d31": (_spec_edit("## Spec Change Log\n", "## Spec Change Log\n\n<!-- fill in later -->\n"), BROKEN),
    "step02.spec.item_format.d8": (_spec_edit("- `pkg/widget.py` -- `Widget.size()`, the method under change", "- pkg/widget.py: the method under change"), BROKEN),
    "step02.spec.cross_ref.d9": (_phantom_code_map, BROKEN),
    "step02.spec.section_present.d44.section": (_spec_edit("## Tasks & Acceptance\n", "## Work\n"), BROKEN),
    "step02.spec.label_present.d44.execution": (_spec_edit("**Execution:**", "**Steps:**"), BROKEN),
    "step02.spec.label_present.d44.acceptance": (_spec_edit("**Acceptance Criteria:**", "**Done when:**"), BROKEN),
    "step02.spec.item_format.d13": (_spec_edit("- `pkg/widget.py` -- return 0 when empty -- the issue's case", "- `pkg/widget.py` return 0 when empty"), BROKEN),
    "step02.spec.item_format.d15": (_spec_edit("- Given an empty widget, when size() is called, then it returns 0", "- size() returns 0 for an empty widget"), BROKEN),
    "step02.spec.bmad_text_regex.d42": (_spec_edit("- `tests/test_widget.py` -- add a unit test for the matrix rows -- edge cases", "- `pkg/widget_checks.py` -- cover the matrix rows -- edge cases"), BROKEN),
    "step02.spec.section_present.d45.change_log": (_spec_edit("## Spec Change Log\n", "## Changes\n"), BROKEN),
    "step02.spec.section_present.d45.triage_log": (_spec_edit("## Review Triage Log\n", "## Review Notes\n"), BROKEN),
    "step02.spec.bmad_text_regex.d47": (_spec_edit("- `python -m pytest tests/test_widget.py -q` -- expected: all tests pass", "- run the widget tests; they should pass"), BROKEN),
    "step03.spec.bmad_text_regex.b5": (_spec_edit("## Spec Change Log\n", "## Spec Change Log\n\nSee [the guide](/docs/guide.md).\n"), BROKEN),
    "global.spec.bmad_block_unchanged.b13": (_contract_rewritten, BROKEN),
    "global.spec.bmad_append_only.b14": (_log_rewritten, BROKEN),
    # the diff file
    "step03.diff.artifact_exists.e14b": (_no_diff_at_all, BROKEN),
    "step03.diff.bmad_diff_file.e14a": (_not_a_diff, BROKEN),
    # review: triage log and result
    "step04.spec.item_format.g76.heading": (_spec_edit("### 2026-11-10 — Review pass", "### 2026-11-10 — First look"), BROKEN),
    "step04.spec.item_format.g76.verdicts": (_spec_edit("- verdicts: 2 findings — high 0, medium 1, low 0, false 1, maybe-false 0", "- verdicts: 2 findings"), BROKEN),
    "step04.spec.item_format.g77": (_spec_edit("  - `[medium]` `[defer]` missing docstring update — pre-existing", "  - `[medium]` defer missing docstring update — pre-existing"), BROKEN),
    "step04.spec.item_format.g78": (_spec_edit("### 2026-11-10 — Review pass", "### Nov 10 — Review pass"), BROKEN),
    "step04.spec.bmad_triage_totals.g80": (_totals_wrong, BROKEN),
    "step04.spec.bmad_triage_totals.g66": (_false_not_rejected, BROKEN),
    "step04.spec.section_present.h1.section": (_spec_edit("## Auto Run Result\n", "## Outcome\n"), BROKEN),
    "step04.spec.field_filled.h1.filled": (lambda r: r.spec(r.col.files[SPEC_PATH].split("## Auto Run Result")[0] + "## Auto Run Result\n"), BROKEN),
    "step04.spec.cross_ref.h2": (_result_hides_a_file, BROKEN),
    "step04.result.artifact_exists.h11": (_no_result_with_no_spec, BROKEN),
    "step04.result.frontmatter.h12": (_result_without_frontmatter, BROKEN),
    "step03.spec.cross_ref.f1": (_verification_not_run, BROKEN),
    # sub-agents (the orchestrator's task calls)
    "global.run.bmad_task_calls.i1": (_no_task_calls, BROKEN),
    "step03.run.bmad_task_calls.e11": (_implementer_skipped, BROKEN),
    "step04.run.bmad_task_calls.i3": (_lenses_one_per_turn, BROKEN),
    "step04.run.bmad_task_calls.g11": (_three_lenses, 0.75),
    "step04.run.bmad_task_calls.g3": (_blind_inline_diff, 0.0),
    "step04.run.bmad_task_calls.g4.edge_has_claims": (_edge_no_claims, BROKEN),
    "step04.run.bmad_task_calls.g4.others_without_claims": (_gap_given_spec, BROKEN),
    "step04.run.bmad_task_calls.g86a": (_patch_without_resume, BROKEN),
    "step04.run.bmad_task_calls.g86b": (_resume_with_free_prompt, BROKEN),
    # lens outputs
    "step04.run.bmad_lens_output.g15": (_blind_no_floor, BROKEN),
    "step04.run.bmad_lens_output.g16": (_blind_severity, BROKEN),
    "step04.run.bmad_lens_output.g17": (_blind_no_bullets, BROKEN),
    "step04.run.bmad_lens_output.g29": (_edge_prose, BROKEN),
    "step04.run.bmad_lens_output.g30": (_edge_missing_key, BROKEN),
    "step04.run.bmad_lens_output.g33": (_edge_deletion_without_confidence, BROKEN),
    "step04.run.bmad_lens_output.g37": (_edge_claim_without_confidence, BROKEN),
    "step04.run.bmad_lens_output.g49": (_gap_no_heading_no_sentence, BROKEN),
    "step04.run.bmad_lens_output.g50": (_gap_finding_without_disposition, BROKEN),
    "step04.run.bmad_lens_output.g52": (_gap_silent, BROKEN),
}

# Implemented items without a breaking case: id -> why.
UNCOVERED: dict[str, str] = {}

# Items the honest run leaves not_applicable (a case must first make them apply): id -> the honest status it has.
HONEST_NOT_APPLICABLE = {
    "step04.result.artifact_exists.h11",
    "step04.result.frontmatter.h12",
    "step04.run.bmad_lens_output.g33",
    "step04.run.bmad_lens_output.g37",
    "step04.run.bmad_lens_output.g50",
    "step04.run.bmad_task_calls.g86a",
    "step04.run.bmad_task_calls.g86b",
}


def test_every_implemented_item_has_a_breaking_case():
    mine = {k.split(".", 1)[1] for k, i in IMPLEMENTED.items() if i.check.kind != "bmad.subagent"}
    missing = sorted(mine - set(CASES) - set(UNCOVERED))
    unknown = sorted(set(CASES) - mine)
    assert not missing, missing
    assert not unknown, unknown


def test_the_honest_run_keeps_every_cased_item():
    bad = {k: HONEST_STATUS[I(k)] for k in CASES if k not in HONEST_NOT_APPLICABLE and HONEST_STATUS[I(k)][0] != "pass"}
    assert not bad, bad
    na = {k: HONEST_STATUS[I(k)] for k in HONEST_NOT_APPLICABLE if HONEST_STATUS[I(k)][0] != "not_applicable"}
    assert not na, na


@pytest.mark.parametrize("short", list(CASES))
def test_case_breaks_its_item(short):
    mutate, expected = CASES[short]
    r = R()
    mutate(r)
    status, score, detail = r.statuses()[I(short)]
    if expected == BROKEN:
        assert status == "fail", (status, score, detail)
    else:
        assert status == "fail" and score == pytest.approx(expected), (status, score, detail)
