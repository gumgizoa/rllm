"""workflows/aidlc_v5: aidlc_v4_eval's verifier moved to the v5 documents -- standing on its own, in step with its
documents, and every code-scored method broken and kept by a case.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_v5.py

The honest runs are aidlc_v4_eval's two (test_aidlc_v4_eval_cases ``h1`` / ``h2``) moved to v5 (``to_v5``): the v5
skeleton fields filled in, a whole-repository search in stage 1, a test added to the covering module in stage 4 (and
in the patch, additions only), run with the test runner in stage 5. aidlc_v4_eval's cases are kept where their
method and their edit still exist in v5 (``V4_DROPPED`` names the others and why); ``V5_CASES`` add the methods v5
changes or adds. ``test_every_method_is_broken_and_kept_by_a_case`` is aidlc_v4_eval's gate over v5's rubric.
"""

from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace

import pytest
from test_aidlc_reward import ART
from test_aidlc_v4_eval import _imported_modules
from test_aidlc_v4_eval_cases import BROKEN, Case, blank, empty_section, honest2, move_after
from test_aidlc_v4_eval_cases import CASES as V4_CASES
from test_aidlc_v4_eval_cases import FIELDS as V4_FIELDS
from test_aidlc_v4_eval_hacks import Run, T, _atom_task, diff, episode, sh

from recipe.grpo.qwen3_5.workflow_rubric import schema
from recipe.grpo.qwen3_5.workflows import aidlc_v5, get_workflow
from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward import ruleset
from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward.eval import Evaluation
from recipe.grpo.qwen3_5.workflows.aidlc_v5.reward.methods.form import FIELDS

PKG = aidlc_v5.HERE
_EVAL = aidlc_v5.SPEC.scorers["openhands-sdk"]()

# SPEC.fingerprint: what the agent is given -- the one the v5 evaluation runs recorded (2026-11-08..09,
# eval_results/v5/aidlc_v5-swebv499-...-wf-tcx-step27-run{1,2,3}-full), so they are rescored as run.
FINGERPRINT = "feae110a5caf5995bbc4c342a96b6a959cbda138b7046821e118ad598da6150a"
# legacy/rubric/** + legacy/episode.py: aidlc_v4_eval/legacy's, with the v5 scorer edit of commit 60ddc546 (facts.py,
# score.py), byte-identical to aidlc_v5/reward/rubric at that commit (hashed under reward/ names, as aidlc_v4_eval's pin)
VENDORED = "27185b6eff0adf336007df6320ad23df9978a5979405009cb4519c638cf920f9"


def score(task, ep, files: dict[str, str]) -> dict[str, float]:
    return _EVAL.score(task, ep, _EVAL.from_outputs(files))


# --- standing on its own ---------------------------------------------------------------------------


def test_no_module_imports_another_aidlc_package():
    offending = {str(p.relative_to(PKG)): mods for p in PKG.rglob("*.py") if (mods := [m for m in _imported_modules(p) if any(x.startswith("aidlc_") and x != "aidlc_v5" for x in m.split("."))])}
    assert offending == {}


def test_spec_reads_only_its_own_files():
    spec = aidlc_v5.SPEC
    for path in (spec.docs_dir, spec.instruction_file, *spec.system_prompt.values()):
        assert path.resolve().is_relative_to(PKG), path


def test_registered_and_scored_by_its_own_evaluation():
    spec = get_workflow("aidlc_v5")
    assert spec is aidlc_v5.SPEC and spec.reward_signal == "aidlc/score"
    assert isinstance(spec.scorers["openhands-sdk"](), Evaluation)


def test_workflow_given_to_the_agent_is_pinned():
    assert aidlc_v5.SPEC.fingerprint("openhands-sdk") == FINGERPRINT


def test_vendored_scoring_code_is_pinned():
    files = sorted((PKG / "legacy" / "rubric").rglob("*.py")) + [PKG / "legacy" / "episode.py"]
    h = hashlib.sha256()
    for p in files:
        h.update(("reward/" + p.relative_to(PKG / "legacy").as_posix()).encode() + b"\0" + p.read_bytes() + b"\0")
    assert h.hexdigest() == VENDORED


def test_the_verifier_does_not_lean_on_the_legacy_scoring():
    for path in (PKG / "reward").rglob("*.py"):
        assert not any("legacy" in m for m in _imported_modules(path)), path


def test_the_rule_set_documents_and_rubric_are_in_step():
    assert ruleset.check() == {}


def test_the_check_kinds_are_its_own():
    kinds = {it.check.kind for it in schema.load(PKG / "reward" / "rubric.yaml").items}
    assert kinds and all(k.startswith("aidlc_v5.") for k in kinds), kinds


# --- the honest runs, moved to v5 ----------------------------------------------------------------------

ADDED_TEST = "def test_parse_empty(): ..."
TEST_PATCH = f"diff --git a/tests/test_mod.py b/tests/test_mod.py\n--- a/tests/test_mod.py\n+++ b/tests/test_mod.py\n@@ -1 +1,2 @@\n def test_parse(): ...\n+{ADDED_TEST}\n"
GREP = 'cd /testbed && grep -rn "parse" .'
GREP_OUT = "./pkg/mod.py:1:def parse(s): ...\n./tests/test_mod.py:1:def test_parse(): ..."
PYTEST_CMD = "python -m pytest tests/test_mod.py -q"


def _sub(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _last_line(out: str) -> str:
    return out.strip().splitlines()[-1]


FILES_LINE = "- Files in the change: pkg/mod.py"


class V5Run(Run):
    """An honest run scored by aidlc_v5. ``edit`` reads aidlc_v4_eval's cases against the one line ``to_v5`` extends:
    05's Files in the change gains the test module, so an edit of the v4 line that keeps its start keeps it too."""

    def edit(self, k, old, new):
        if k == 5 and old == FILES_LINE:
            old, new = f"{FILES_LINE}, tests/test_mod.py", (f"{new}, tests/test_mod.py" if new.startswith(FILES_LINE) else new)
        return super().edit(k, old, new)

    def score(self, task=None):
        ep = episode(self.turns)
        for i, text in self.messages.items():
            ep.trajectories[0].steps[i].chat_completions[-1]["content"] = text
        if self.patch is not None:
            ep.artifacts = {"patch": self.patch}
        return score(task or SimpleNamespace(id="t"), ep, self.files)


def to_v5(r: Run) -> V5Run:
    """aidlc_v4_eval's honest run, following the v5 documents too."""
    r.__class__ = V5Run
    pytest_runs = r.runs("pytest")
    out5 = r.turns[pytest_runs[-1]][1]
    f = {k: r.files[ART[k]] for k in ART}
    f[1] = _sub(f[1], "- Files: pkg/mod.py\n", "- Files: pkg/mod.py\n- Referencing files left out of scope: none\n")
    f[3] = _sub(f[3], "## Requirement Coverage", "## Added Test\n- Module: tests/test_mod.py\n- Test: test_parse_empty\n\n## Requirement Coverage")
    f[4] = _sub(f[4], "- Executed: no\n", "- Executed: no\n\n## Added Test\n- Module: tests/test_mod.py\n- Test: test_parse_empty\n- Executed: no\n")
    f[4] = _sub(f[4], "- Test files modified: none", "- Existing test lines modified or removed: none\n- Test files with additions: tests/test_mod.py")
    f[5] = _sub(f[5], "- Result: pass\n", "- Result: pass\n- Output: ok\n")
    f[5] = _sub(
        f[5],
        f"## Existing Tests vs Baseline\n- Command: {PYTEST_CMD}\n",
        f"## Added Test\n- Command: {PYTEST_CMD}\n- Result: pass\n\n## Existing Tests vs Baseline\n- Command: {PYTEST_CMD}\n- Output: {_last_line(out5)}\n",
    )
    f[5] = re.sub(r"(?m)^(- Files in the change: .*)$", r"\1, tests/test_mod.py", f[5])
    f[5] = _sub(f[5], "- Test files in the change: none", "- Test files with additions: tests/test_mod.py\n- Existing test lines modified or removed: none")
    for k, text in f.items():
        r.files[ART[k]] = text
        i = r.write_of(k)
        call, o = r.turns[i]
        a = {**json.loads(call["function"]["arguments"]), "file_text": text}
        r.turns[i] = ({**call, "function": {**call["function"], "arguments": json.dumps(a)}}, o)
    r.insert(r.write_of(1), sh(GREP, GREP_OUT))
    r.insert(
        r.write_of(4),
        T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="def test_parse(): ...", new_str=f"def test_parse(): ...\n{ADDED_TEST}"),
    )
    r.patch = (r.patch or "") + TEST_PATCH
    return r


BASES = {"h1": lambda: to_v5(Run()), "h2": lambda: to_v5(honest2())}
HONEST_SCORES = {name: build().score(_atom_task(None)) for name, build in BASES.items()}


@pytest.mark.parametrize("base", list(BASES))
def test_each_honest_run_scores_one_everywhere(base):
    s = HONEST_SCORES[base]
    low = {k: v for k, v in s.items() if k.startswith(("aidlc/score", "aidlc/kind/", "aidlc/cat/")) and v < 1.0}
    assert not low, low


@pytest.mark.parametrize("base", list(BASES))
def test_every_v5_judgment_keeps_the_honest_run(base):
    s = HONEST_SCORES[base]
    low = {k: v for k, v in s.items() if re.match(r"aidlc/(?:atom|check|rule|form|proc|run)/", k) and v is not None and v < 1.0}
    assert not low, low


# --- cases -------------------------------------------------------------------------------------------


def edit(k: int, old: str, new: str):
    return lambda r: r.edit(k, old, new)


def _turn_index(r, path: str, command: str = "str_replace") -> int:
    return r.at(lambda a: a.get("path") == path and a.get("command") == command)


def rewrite_test_line(r):
    """The stage-4 edit of the test module rewrites its existing line, and the patch shows it."""
    i = _turn_index(r, "/testbed/tests/test_mod.py")
    r.turns.pop(i)
    r.insert(
        i,
        T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="def test_parse(): ...", new_str=f"def test_parse(): assert True\n{ADDED_TEST}"),
    )
    r.patch = r.patch.replace(" def test_parse(): ...\n+", "-def test_parse(): ...\n+def test_parse(): assert True\n+")


def rewrite_test_line_and_put_back(r):
    """An existing test line rewritten in stage 4 and restored before the end: the patch adds only."""
    r.insert(
        _turn_index(r, "/testbed/tests/test_mod.py"),
        T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="def test_parse(): ...", new_str="def test_parse(): pass"),
    )
    r.insert(
        _turn_index(r, "/testbed/tests/test_mod.py") + 1,
        T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="def test_parse(): pass", new_str="def test_parse(): ..."),
    )


def own_test_corrected(r):
    """The run corrects the test it added (its own lines, not the module's)."""
    r.insert(
        _turn_index(r, "/testbed/tests/test_mod.py") + 1,
        T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str=ADDED_TEST, new_str="def test_parse_empty(): assert parse('') == {}"),
    )


def no_added_test(r):
    """No test added: the stage-4 edit of the test module, its patch block and the artifacts' mentions gone."""
    r.turns.pop(_turn_index(r, "/testbed/tests/test_mod.py"))
    r.patch = r.patch.replace(TEST_PATCH, "")
    r.edit(3, "- Module: tests/test_mod.py", "- Module: none")
    r.edit(3, "- Test: test_parse_empty", "- Test: none")
    text = (
        r.files[ART[4]]
        .replace("- Module: tests/test_mod.py", "- Module: none")
        .replace("- Test: test_parse_empty", "- Test: none")
        .replace("- Test files with additions: tests/test_mod.py", "- Test files with additions: none")
    )
    r.artifact(4, text)
    r.edit(5, "- Test files with additions: tests/test_mod.py", "- Test files with additions: none")


def added_test_not_run(r):
    """The test runs of stage 5 go: the build and the reproduction only."""
    w4 = r.write_of(4)
    for i in sorted((i for i in r.runs("pytest") if i > w4), reverse=True):
        r.turns.pop(i)


def stashed_rebuild(r):
    """Stage 5 stashes the change and reruns the baseline selection: the baseline rebuilt."""
    r.insert(r.write_of(5), sh(f"cd /testbed && git stash && {PYTEST_CMD}; git stash pop", "3 passed in 0.10s"))


OTHER_OUT = "tests/test_other.py::test_misc FAILED\n1 failed in 0.05s"


def outside_failure_classified(r):
    """A covering module outside the baseline fails; run on the stashed source it fails too: pre-existing."""
    r.insert(r.write_of(5), sh("cd /testbed && python -m pytest tests/test_other.py -q", OTHER_OUT))
    r.insert(r.write_of(5), sh("cd /testbed && git stash && python -m pytest tests/test_other.py -q; git stash pop", OTHER_OUT))
    r.edit(5, "- Pre-existing failures: none", "- Pre-existing failures: tests/test_other.py::test_misc -> fails on the unchanged source too")


def outside_failure_unclassified(r):
    """The same failure recorded as pre-existing with no run on the unchanged source."""
    r.insert(r.write_of(5), sh("cd /testbed && python -m pytest tests/test_other.py -q", OTHER_OUT))
    r.edit(5, "- Pre-existing failures: none", "- Pre-existing failures: tests/test_other.py::test_misc -> unrelated to the change")


def rebuild_then_preexisting(r):
    """Stage 5 reruns the baseline selection on stashed source, sees test_parse fail and records it as pre-existing:
    a rebuilt baseline, not the classification of a module outside it."""
    r.insert(r.write_of(5), sh(f"cd /testbed && git stash && {PYTEST_CMD}; git stash pop", "tests/test_mod.py::test_parse FAILED\n1 failed in 0.10s"))
    r.edit(5, "- Pre-existing failures: none", "- Pre-existing failures: tests/test_mod.py::test_parse -> fails on the unchanged source")


def no_repo_search(r):
    r.turns.pop(r.at(lambda a: a.get("command") == GREP))


def search_one_dir(r):
    """The search reads one directory, not the repository."""
    i = r.at(lambda a: a.get("command") == GREP)
    r.set_command(i, 'cd /testbed && grep -rn "parse" pkg/', "pkg/mod.py:1:def parse(s): ...")


def search_finds_another_file(r):
    """The search hits a second source file that 01 neither scopes nor leaves out."""
    i = r.at(lambda a: a.get("command") == GREP)
    r.set_obs(i, GREP_OUT + "\n./pkg/cli.py:3:from pkg.mod import parse")


def heredoc_artifact(r):
    """Artifact 02 written with a shell heredoc."""
    i = r.write_of(2)
    r.turns[i] = sh(f"cat > {ART[2]} <<'EOF'\n{r.files[ART[2]]}EOF", "")


def covering_module_unrun(r):
    """The change also touches pkg/util.py, whose module tests/test_util.py the run has seen; stage 5 runs only
    tests/test_mod.py."""
    r.insert(r.write_of(1), T("file_editor", "def test_util(): ...", command="view", path="/testbed/tests/test_util.py"))
    r.patch += diff("pkg/util.py")
    r.insert(_turn_index(r, "/testbed/tests/test_mod.py"), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/util.py", old_str="a", new_str="b"))


def covering_module_run(r):
    covering_module_unrun(r)
    i = r.runs("pytest")[-1]
    r.set_command(i, "cd /testbed && python -m pytest tests/test_mod.py tests/test_util.py -q")


def regressions_none_unrun(r):
    """``Regressions: none`` with no Output and no test run after the last edit."""
    added_test_not_run(r)
    text = re.sub(r"(?m)^(## Existing Tests vs Baseline\n- Command: [^\n]*\n)- Output: [^\n]*\n", r"\1- Output: \n", r.files[ART[5]])
    r.artifact(5, text)


V4_DROPPED = {  # aidlc_v4_eval's methods v5 has no more
    "atom/D4b": "v5 drops the line (no repository survey); stage 1 searches the whole repository (D1c)",
    "atom/G4b": "v5 reverses it: a test may be added (F10, G10, H18)",
    "rule/r_tests_untouched": "rule/r_test_lines_kept: only an existing test line changed or removed breaks it",
    "check/e4_tests_untouched": "check/e4_test_lines_kept, on 04's new field",
    "check/e5_test_files_none": "check/e5_test_lines_none, on 05's new field",
}
V4_FORM_FIELDS = {f"form/{rule}" for rule in V4_FIELDS}  # regenerated from v5's FIELDS (``field_cases``)


def _only(item: str, expect) -> Case:
    hits = [c for c in V4_CASES if c.item == item and c.expect == expect]
    assert len(hits) == 1, (item, expect, hits)
    return hits[0]


V4_REPLACED = {  # aidlc_v4_eval's cases whose verdict the v5 fixture moves, each replaced in V5_CASES
    id(_only("atom/F7", BROKEN)): "its step on tests/test_mod.py is the plan's Added Test module in v5",
    id(_only("atom/D10a", 0.0)): "stage 1's repository search shows the test file; replaced with the search dropped too",
    id(_only("atom/D5", 0.0)): "the search shows tests/test_mod.py, so Existing Tests' path is judged too (one of two)",
}


def _v4_case_kept(c: Case) -> bool:
    return c.method not in V4_DROPPED and c.method not in V4_FORM_FIELDS and id(c) not in V4_REPLACED


def field_cases() -> list[Case]:
    """form/<rule>@<stage> for every v5 FIELDS entry, as aidlc_v4_eval's ``one_label_per_line_fields``."""
    diagnostic = {it.id for it in schema.load(PKG / "reward" / "rubric.yaml").items if it.log_only}
    seen: dict[tuple[int, str], int] = {}
    out = []
    for rule, (st, section, label, _allow_none) in FIELDS.items():
        if f"form/{rule}@{st}" in diagnostic:
            continue
        if label:
            seen[(st, label)] = seen.get((st, label), 0) + 1
            out.append(Case(f"form/{rule}@{st}", "h1", blank(st, label, seen[(st, label)]), 0.0))
        else:
            out.append(Case(f"form/{rule}@{st}", "h1", empty_section(st, section), 0.0))
    return out


V5_CASES: list[Case] = [
    # test files: add only
    Case("rule/r_test_lines_kept", "h1", rewrite_test_line, 0.0),
    Case("rule/r_test_lines_kept", "h1", rewrite_test_line_and_put_back, 0.0),
    Case("rule/r_test_lines_kept", "h1", own_test_corrected, 1.0),
    Case("check/e4_test_lines_kept", "h1", rewrite_test_line, 0.0),
    Case("check/e4_test_lines_kept", "h1", own_test_corrected, 1.0),
    Case("check/e5_test_lines_none", "h1", rewrite_test_line, 0.0),
    Case("check/e5_test_lines_none", "h1", own_test_corrected, 1.0),
    Case("check/e5_test_additions", "h1", edit(5, "- Test files with additions: tests/test_mod.py", "- Test files with additions: none"), 0.0),
    Case("check/e5_test_additions", "h1", no_added_test, 1.0),
    Case("atom/F7", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: tests/test_other.py (modify in place)"), 0.0),
    Case("atom/F7", "h1", edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: tests/test_mod.py (modify in place)"), 1.0),
    # the added test: planned, added, run
    Case("atom/F10", "h1", no_added_test, 0.0),
    Case("atom/G10", "h1", lambda r: (r.turns.pop(_turn_index(r, "/testbed/tests/test_mod.py")), setattr(r, "patch", r.patch.replace(TEST_PATCH, ""))), 0.0),
    Case("atom/H18", "h1", added_test_not_run, 0.0),
    Case("atom/H18", "h1", lambda r: r.set_command(r.runs("pytest")[-1], "cd /testbed && python tests/test_mod.py"), 0.0),
    # stage 5: the covering modules, the unchanged source, Output
    Case("atom/H4c", "h1", covering_module_unrun, 0.5),
    Case("atom/H4c", "h1", covering_module_run, 1.0),
    Case("atom/H7", "h1", stashed_rebuild, 0.0),
    Case("atom/H7", "h1", outside_failure_classified, 1.0),
    Case("atom/H8h", "h1", outside_failure_unclassified, 0.0),
    Case("atom/H8h", "h1", outside_failure_classified, 1.0),
    Case("check/c15_preexisting_subset", "h1", outside_failure_unclassified, 0.0),
    Case("check/c15_preexisting_subset", "h1", outside_failure_classified, 1.0),
    Case("check/c15_preexisting_subset", "h1", rebuild_then_preexisting, 0.0),
    Case("atom/H8h", "h1", rebuild_then_preexisting, 0.0),
    Case("atom/H5c", "h1", regressions_none_unrun, 0.0),
    Case("atom/H5c", "h1", edit(5, "- Regressions: none", "- Regressions: test_parse -> broke on None -> fixed the guard"), None),
    Case("atom/H5d", "h1", edit(5, "- Output: ok", "- Output: all good, 3 of 3 cases fine"), 0.5),
    # stage 1: the whole-repository search
    Case("atom/D1c", "h1", no_repo_search, 0.0),
    Case("atom/D1c", "h1", search_one_dir, 0.0),
    Case("atom/D1e", "h1", search_finds_another_file, 0.5),
    Case(
        "atom/D1e",
        "h1",
        lambda r: (search_finds_another_file(r), r.edit(1, "- Referencing files left out of scope: none", "- Referencing files left out of scope: pkg/cli.py — only imports parse")),
        1.0,
    ),
    # core: artifacts with the file-editing tool; 04's Executed fields
    Case("atom/B12", "h1", heredoc_artifact, 0.0),
    Case("atom/B5d@4", "h1", edit(4, "- Test: test_parse_empty\n- Executed: no", "- Test: test_parse_empty\n- Executed: yes"), 0.0),
    # aidlc_v4_eval's cases replaced (V4_REPLACED)
    Case("atom/D10a", "h1", lambda r: (no_repo_search(r), move_after(lambda r: r.runs("pytest")[0], lambda r: r.write_of(1))(r)), 0.0),
    Case("atom/D5", "h1", edit(1, "- Files: pkg/mod.py", "- Files: mod.py"), 0.5),
    *field_cases(),
]

CASES: list[Case] = [c for c in V4_CASES if _v4_case_kept(c)] + V5_CASES


def _case_id(c: Case) -> str:
    return f"{c.item}:{c.base}:{'keep' if c.expect == 1.0 else 'break'}:{CASES.index(c)}"


@pytest.mark.parametrize("case", CASES, ids=[_case_id(c) for c in CASES])
def test_the_case_gives_the_item_its_value(case):
    r = BASES[case.base]()
    if case.build is not None:
        case.build(r)
    s = r.score(case.task or _atom_task(r))
    value = s.get(f"aidlc/{case.item}")
    if case.expect is None:
        assert value is None, value
    elif case.expect == BROKEN:
        assert value is not None and value < 1.0, value
    else:
        assert value == pytest.approx(case.expect), value


def _code_methods() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for it in schema.load(PKG / "reward" / "rubric.yaml").items:
        if it.log_only or it.check.kind.endswith(".judge"):
            continue
        out.setdefault(ruleset.method_key({"check": {"kind": it.check.kind, "params": it.check.params}}), []).append(it.id)
    return out


def test_every_method_is_broken_and_kept_by_a_case():
    methods = _code_methods()
    broken = {c.method for c in CASES if c.expect not in (1.0, None)}
    kept = {c.method for c in CASES if c.expect == 1.0}
    for method, items in methods.items():
        if any(HONEST_SCORES[b].get(f"aidlc/{i}") == 1.0 for b in BASES for i in items):
            kept.add(method)
    unknown = {c.method for c in CASES} - set(methods)
    assert unknown == set(), f"cases for no method: {sorted(unknown)}"
    missing = {m: [w for w, ok in (("break", m in broken), ("keep", m in kept)) if not ok] for m in methods if m not in broken or m not in kept}
    assert missing == {}, missing


def test_a_v4_task_run_still_scores():
    """A run that follows aidlc_v4 (no v5 fields, no added test) is scored without error, and loses on what v5 adds."""
    r = Run()
    r.__class__ = V5Run
    out = r.score(_atom_task(r))
    assert 0.0 < out["aidlc/score"] < 1.0
    assert out["aidlc/atom/D1c"] == 0.0 and out["aidlc/form/S5.output@5"] == 0.0
