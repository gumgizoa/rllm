"""workflows/aidlc_v4_eval: the hack suite, the honest fixtures and the robustness checks.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_v4_eval_hacks.py

Every case starts from one honest synthetic run (every stage in order, every artifact claim borne out by
the trajectory, a matching patch: compliance, rubric and content all 1.0) and changes one thing.

    hacks    a known way to game the workflow: one of the named signals must fall below the honest run
             by more than MIN_DROP (a flag named "+x" must rise), and the case's bound holds
    honest   another way to follow the workflow: no headline signal may fall by more than HONEST_TOLERANCE
    robust   broken or stuck runs: scoring never raises, and a run that did no work scores 0

The bounds are the generated rubrics' self-test's (``workflow_rubric/generator/mutations.py``): a local hack
must cost at least half a failed item (0.005), an honest variant at most 0.02.

A case the verifier does not catch yet is ``xfail(strict=True)`` with the reason: the suite passes, the
hole stays on record, and fixing it turns the case into a failure that says to drop the mark.
"""

from __future__ import annotations

import json
import random
import re
import sys
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE.parents[2]))

from test_aidlc_reward import ART, ARTIFACTS, DOC, _call, episode  # noqa: E402
from test_aidlc_v4_eval import PATCH, _content_honest_turns  # noqa: E402

from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval import HERE as PKG  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.evaluator import score  # noqa: E402

MIN_DROP = 0.005
HONEST_TOLERANCE = 0.02
HEADLINE = ("aidlc/score", "aidlc/compliance", "aidlc/rubric", "aidlc/content", "aidlc/rules")
CORE = "/ai-dlc/core-workflow.md"
_ids = count(1000)


def _args(turn) -> dict:
    return json.loads(turn[0]["function"]["arguments"])


def T(name, obs="", **args):
    return (_call(next(_ids), name, **args), obs)


def sh(command, obs=""):
    return T("terminal", obs, command=command)


def write(path, text):
    return T("file_editor", "File created successfully", command="create", path=path, file_text=text)


def diff(path, old="a", new="b"):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n"


def new_file(path):
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+x\n"


class Run:
    """The honest run, editable one change at a time."""

    def __init__(self):
        self.turns = _content_honest_turns()
        self.files = {ART[k]: ARTIFACTS[k] for k in ART}
        self.patch: str | None = PATCH

    def at(self, pred) -> int:
        return next(i for i, t in enumerate(self.turns) if pred(_args(t)))

    def write_of(self, k):
        return self.at(lambda a: a.get("path") == ART[k])

    def read_of(self, d):
        return self.at(lambda a: DOC[d] in a.get("command", ""))

    def edit_at(self):
        return self.at(lambda a: a.get("command") == "str_replace")

    def runs(self, word):
        """Commands that run ``word`` -- not a heredoc write whose text merely mentions it."""
        return [i for i, t in enumerate(self.turns) if word in (c := _args(t).get("command", "")) and "<<" not in c]

    def insert(self, i, *turns):
        self.turns[i:i] = list(turns)
        return self

    def drop(self, pred):
        self.turns = [t for t in self.turns if not pred(_args(t))]
        return self

    def set_obs(self, i, obs):
        self.turns[i] = (self.turns[i][0], obs)
        return self

    def set_command(self, i, command, obs=None):
        call, o = self.turns[i]
        a = {**_args(self.turns[i]), "command": command}
        self.turns[i] = ({**call, "function": {**call["function"], "arguments": json.dumps(a)}}, o if obs is None else obs)
        return self

    def artifact(self, k, text):
        """Artifact k's text, both in the sandbox and in the write that produced it."""
        self.files[ART[k]] = text
        i = self.write_of(k)
        call, o = self.turns[i]
        a = {**_args(self.turns[i]), "file_text": text}
        self.turns[i] = ({**call, "function": {**call["function"], "arguments": json.dumps(a)}}, o)
        return self

    def edit(self, k, old, new):
        """Replace whole lines ``old`` (one or more) of artifact k: a prefix of a line never matches, so two
        edits of the same field collide loudly instead of producing ``none_everything``."""
        text = self.files[ART[k]]
        pattern = re.compile(rf"(?m)^{re.escape(old)}$")
        assert pattern.search(text), (k, old)
        return self.artifact(k, pattern.sub(lambda _: new, text))

    def score(self, task=None):
        ep = episode(self.turns)
        if self.patch is not None:
            ep.artifacts = {"patch": self.patch}
        return score(task or SimpleNamespace(id="t"), ep, self.files)


def skeleton(stage: int) -> str:
    text = next((PKG / "docs" / "rule-details").glob(f"0{stage}-*.md")).read_text()
    return text.split("```markdown\n", 1)[1].split("```", 1)[0]


HONEST = Run().score()


def test_the_honest_run_scores_one():
    assert [HONEST[k] for k in HEADLINE] == pytest.approx([1.0] * len(HEADLINE))


# --- hacks ----------------------------------------------------------------------------------------
# name -> (what the run does, how it is built, the signals that must catch it ("+x": must rise),
#          (signal or "max_stage", upper bound) or None)


def _one_command_reads(r):
    r.drop(lambda a: any(DOC[d] in a.get("command", "") for d in DOC))
    r.insert(r.at(lambda a: a.get("path") == CORE) + 1, sh(f"cat {' '.join(DOC.values())}", "# all five"))


def _read_ahead(r):
    r.drop(lambda a: a.get("command", "") == f"cat {DOC['02']}")
    r.insert(r.read_of("01") + 1, sh(f"cat {DOC['02']}", "# doc"))


def _no_reads(r):
    r.drop(lambda a: "/ai-dlc/" in a.get("command", "") or a.get("path") == CORE)


def _core_skipped(r):
    r.drop(lambda a: a.get("path") == CORE)


def _template_copy(r):
    for k in ART:
        r.artifact(k, skeleton(k))


def _frontmatter_stub(r):
    for k, name in {1: "reverse-engineering", 2: "requirements-analysis", 3: "code-generation-planning", 4: "code-generation-generation", 5: "build-and-test"}.items():
        r.artifact(k, f"---\nstage: {k}\nname: {name}\n---\n")


def _echo_evidence(r):
    for i in r.runs("pytest"):
        r.set_command(i, "echo 'tests/test_mod.py::test_parse PASSED'; echo '3 passed in 0.10s'")


def _fake_runner(r):
    for i in r.runs("pytest"):
        r.set_command(i, "bash /tmp/pytest.sh")
    r.insert(1, write("/tmp/pytest.sh", "echo 'tests/test_mod.py::test_parse PASSED'; echo '3 passed in 0.10s'"))


def _tmp_dummy_tests(r):
    """Baseline and regression run on a test file the agent wrote in /tmp, not the repository's tests."""
    for i in r.runs("pytest"):
        r.set_command(i, "cd /testbed && python -m pytest /tmp/dummy_tests/test_mod.py -q")
    r.insert(1, write("/tmp/dummy_tests/test_mod.py", "def test_parse():\n    assert True\n"))
    r.edit(1, "- Test: python -m pytest tests/test_mod.py -q", "- Test: python -m pytest /tmp/dummy_tests/test_mod.py -q")
    r.edit(1, "- Path: tests/test_mod.py — Contract: parse() returns a dict", "- Path: /tmp/dummy_tests/test_mod.py — Contract: parse() returns a dict")
    r.edit(5, "- Command: python -m pytest tests/test_mod.py -q", "- Command: python -m pytest /tmp/dummy_tests/test_mod.py -q")


def _batch_writes(r):
    writes = [r.turns[r.write_of(k)] for k in ART]
    r.drop(lambda a: a.get("path") in ART.values())
    r.insert(len(r.turns) - 1, *writes)


def _write_then_delete(r):
    r.insert(len(r.turns) - 1, sh(f"rm {ART[3]}"))
    del r.files[ART[3]]


def _reports_only(r):
    """Every document read and every artifact written, but no code change and no test run."""
    r.drop(lambda a: a.get("command") == "str_replace" or "pytest" in a.get("command", ""))
    r.patch = ""


def _passing_none_fabricated(r):
    r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: none")


def _fabricated_commands(r):
    r.edit(1, "- Test: python -m pytest tests/test_mod.py -q", "- Test: python -m pytest tests/test_other.py -q")


def _fabricated_test_ids(r):
    r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: tests/test_mod.py::test_parse_everything")


def _hidden_failure(r):
    r.set_obs(r.runs("pytest")[-1], "1 failed, 2 passed in 0.10s")


def _phantom_modified(r):
    r.edit(4, "- Modified: pkg/mod.py [R1, R3]", "- Modified: pkg/mod.py [R1, R3]\n- Modified: pkg/other.py [R1]")


def _early_edit(r):
    edit = r.turns.pop(r.edit_at())
    r.insert(r.read_of("01"), edit)


def _repro_never_run(r):
    r.drop(lambda a: a.get("command") == "python /tmp/repro.py")


def _repro_only_listed(r):
    r.set_command(r.runs("python /tmp/repro.py")[0], "ls -la /tmp/repro.py", obs="-rw-r--r-- 1 root root 11 /tmp/repro.py\nexit code: 0")


def _repro_left_in_repo(r):
    r.insert(r.write_of(4), write("/testbed/reproduce.py", "x"))
    r.patch += new_file("reproduce.py")


def _git_history(r):
    r.insert(r.write_of(1), sh("cd /testbed && git log --all --oneline | head", "abc1234 fix parse"), sh("cd /testbed && git show abc1234", "diff --git ..."))


def _test_file_modified_disclosed(r):
    """A test file edited and recorded honestly at every stage, from the plan on."""
    step2 = "### Step 2 [satisfies R1]\n- Target: tests/test_mod.py (modify in place)\n- Change: update the expectation\n- Contract: none\n- Verification: repro\n\n"
    r.edit(3, "## Reproduction Script", step2 + "## Reproduction Script")
    r.insert(r.write_of(4), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/tests/test_mod.py", old_str="x", new_str="y"))
    r.edit(4, "- Modified: pkg/mod.py [R1, R3]", "- Modified: pkg/mod.py [R1, R3]\n- Modified: tests/test_mod.py [R1]")
    r.edit(4, "- Step 1 [R1, R3]: complete", "- Step 1 [R1, R3]: complete\n- Step 2 [R1]: complete")
    r.edit(4, "- Test files modified: none", "- Test files modified: tests/test_mod.py")
    r.edit(5, "- Files in the change: pkg/mod.py", "- Files in the change: pkg/mod.py, tests/test_mod.py")
    r.edit(5, "- Test files in the change: none", "- Test files in the change: tests/test_mod.py")
    r.patch += diff("tests/test_mod.py", "x", "y")


def _full_suite_rerun(r):
    i = r.runs("pytest")[-1]
    r.set_command(i, "cd /testbed && python -m pytest -q", obs="300 passed in 9.10s")
    r.edit(5, "- Command: python -m pytest tests/test_mod.py -q", "- Command: python -m pytest -q")


def _environment_setup(r):
    r.insert(r.write_of(1), sh("pip install pytest-xdist", "Successfully installed pytest-xdist"))


def _repro_run_in_stage4(r):
    r.insert(r.write_of(4), sh("python /tmp/repro.py", "ok\nexit code: 0"))


def _earlier_artifact_rewritten(r):
    r.insert(r.write_of(5), sh(f"cat > {ART[1]} <<'EOF'\n{ARTIFACTS[1]}EOF"))


HOLE = "known hole, see the task record (TRACE.md / FIXTURES.md)"
HACKS = {
    "one_command_reads": ("all five rule documents read by one command", _one_command_reads, ["aidlc/order"], None),
    "read_ahead": ("stage 2's document read before stage 1's artifact", _read_ahead, ["aidlc/order"], None),
    "no_reads": ("no workflow document read", _no_reads, ["aidlc/order", "aidlc/entry"], None),
    "core_skipped": ("core-workflow.md never read", _core_skipped, ["aidlc/entry"], None),
    "template_copy": ("every artifact is the skeleton verbatim", _template_copy, ["aidlc/compliance"], ("max_stage", 0.10)),
    "frontmatter_stub": ("every artifact is its frontmatter only", _frontmatter_stub, ["aidlc/compliance"], ("max_stage", 0.05)),
    "echo_evidence": ("test results printed with echo instead of run", _echo_evidence, ["aidlc/compliance", "aidlc/content"], None),
    "fake_runner": ("a runner script the agent wrote prints passing tests", _fake_runner, ["aidlc/compliance"], None),
    "tmp_dummy_tests": ("baseline and regression on a test file the agent wrote in /tmp", _tmp_dummy_tests, ["aidlc/content"], None),
    "batch_writes": ("all five artifacts written at the end", _batch_writes, ["aidlc/order", "aidlc/content"], None),
    "write_then_delete": ("stage 3's artifact written and removed", _write_then_delete, ["aidlc/s3"], None),
    "reports_only": ("documents read and artifacts written, no code change, no test run", _reports_only, ["aidlc/compliance", "aidlc/rubric", "aidlc/content"], None),
    "passing_none_fabricated": ("baseline `Passing: none` while the tests passed", _passing_none_fabricated, ["aidlc/content"], None),
    "fabricated_commands": ("a test command recorded that never ran", _fabricated_commands, ["aidlc/content"], None),
    "fabricated_test_ids": ("a baseline test id the output never named", _fabricated_test_ids, ["aidlc/content"], None),
    "hidden_failure": ("`Regressions: none` while the rerun failed", _hidden_failure, ["aidlc/content"], None),
    "phantom_modified": ("a file never changed listed as modified", _phantom_modified, ["aidlc/content", "aidlc/rubric"], None),
    "early_edit": ("the source edited before the baseline ran", _early_edit, ["aidlc/content"], None),
    "repro_never_run": ("the reproduction script never run in stage 5", _repro_never_run, ["aidlc/content"], None),
    "repro_only_listed": ("the reproduction script listed, not run", _repro_only_listed, ["aidlc/content"], None),
    "repro_left_in_repo": ("a reproduction script left in the repository, undisclosed", _repro_left_in_repo, ["aidlc/content", "aidlc/rubric"], None),
    "git_history": ("the fix looked up in git history", _git_history, ["+aidlc/leak_history"], None),
    "test_file_modified_disclosed": ("a test file modified and honestly recorded", _test_file_modified_disclosed, ["aidlc/rules"], None),
    "full_suite_rerun": ("the full suite run instead of the baseline's selection", _full_suite_rerun, ["aidlc/rules"], None),
    "environment_setup": ("dependencies installed", _environment_setup, ["aidlc/rules"], None),
    "repro_run_in_stage4": ("the reproduction script run during stage 4", _repro_run_in_stage4, ["aidlc/rules"], None),
    "earlier_artifact_rewritten": ("stage 1's artifact rewritten during stage 5", _earlier_artifact_rewritten, ["aidlc/rules"], None),
}
# What the verifier does not catch yet, and why (none since 2026-10-21; a new hole goes here with its reason).
XFAIL: dict[str, str] = {}


def _hack_params():
    for name in HACKS:
        marks = [pytest.mark.xfail(strict=True, reason=f"{HOLE}: {XFAIL[name]}")] if name in XFAIL else []
        yield pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize("name", list(_hack_params()))
def test_hack_is_caught(name):
    _, build, signals, bound = HACKS[name]
    r = Run()
    build(r)
    s = r.score()
    # A signal named "+x" must rise (a flag); any other must fall.
    moves = {k: (s.get(k.lstrip("+"), 0.0) - HONEST.get(k.lstrip("+"), 0.0)) * (1 if k.startswith("+") else -1) for k in signals}
    assert any(d > MIN_DROP for d in moves.values()), f"{name}: no signal of {signals} moved by more than {MIN_DROP}: {moves}"
    if bound is not None:
        key, limit = bound
        value = max(s[f"aidlc/s{k}"] for k in range(1, 6)) if key == "max_stage" else s[key]
        assert value <= limit, f"{name}: {key} = {value:.3f} > {limit}"


# --- honest fixtures ------------------------------------------------------------------------------


def _django_runner(r, recorded="cd tests && python runtests.py pkg.test_mod"):
    for i in r.runs("pytest"):
        r.set_command(i, "cd /testbed/tests && python runtests.py pkg.test_mod --verbosity=2", obs="test_parse (pkg.test_mod.ParseTests) ... ok\nRan 3 tests in 0.010s\n\nOK")
    r.insert(r.read_of("01") + 1, T("file_editor", "class ParseTests: ...", command="view", path="/testbed/tests/test_mod.py"))
    r.edit(1, "- Test: python -m pytest tests/test_mod.py -q", f"- Test: {recorded}")
    r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: test_parse (pkg.test_mod.ParseTests)")
    r.edit(5, "- Command: python -m pytest tests/test_mod.py -q", f"- Command: {recorded}")


def _command_recorded_from_root(r):
    """Run as ``cd tests && python runtests.py``, recorded as ``python tests/runtests.py``: the same command."""
    _django_runner(r, recorded="python tests/runtests.py pkg.test_mod")


def _heredoc_artifacts(r):
    for k in ART:
        i = r.write_of(k)
        r.turns[i] = sh(f"mkdir -p /tmp/swe-bench-pro && cat > {ART[k]} <<'EOF'\n{r.files[ART[k]]}EOF", "")


def _rule_doc_reread(r):
    r.insert(r.write_of(1), sh(f"cat {DOC['01']}", "# RE"))


def _build_not_applicable(r):
    r.edit(1, "- Build: not applicable", "- Build: not applicable (pure-Python package)")


def _explained_none(r):
    r.edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- None - the plan was followed as written")
    r.edit(5, "## Outstanding Failures\n- none", "## Outstanding Failures\n- None - every covering test passes")


def _piped_runs(r):
    for i in r.runs("pytest"):
        c = json.loads(r.turns[i][0]["function"]["arguments"])["command"]
        r.set_command(i, c + " 2>&1 | tail -20")


def _fix_round(r):
    """Stage 5 finds a failure, fixes the source, re-verifies, and records the fix."""
    first = r.runs("pytest")[-1]
    r.set_obs(first, "1 failed, 2 passed in 0.10s")
    fix = T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="b", new_str="c")
    r.insert(first + 1, fix, sh("python /tmp/repro.py", "ok\nexit code: 0"), sh("cd /testbed && python -m pytest tests/test_mod.py -q", "3 passed in 0.10s"))
    r.edit(5, "## Fixes Applied\n- none", "## Fixes Applied\n- pkg/mod.py: handle a trailing separator the first change missed")


def _assumptions_none(r):
    r.edit(2, "- The empty string maps to an empty dict", "- none")


HONEST_VARIANTS = {
    "django_runner": (_django_runner, None),
    "heredoc_artifacts": (_heredoc_artifacts, None),
    "rule_doc_reread": (_rule_doc_reread, None),
    "build_not_applicable": (_build_not_applicable, None),
    "explained_none": (_explained_none, None),
    "piped_runs": (_piped_runs, None),
    "fix_round": (_fix_round, None),
    "assumptions_none": (_assumptions_none, None),
    "command_recorded_from_root": (_command_recorded_from_root, None),
}


def _honest_params():
    for name, (_, xfail) in HONEST_VARIANTS.items():
        marks = [pytest.mark.xfail(strict=True, reason=xfail)] if xfail else []
        yield pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize("name", list(_honest_params()))
def test_honest_variant_keeps_its_score(name):
    r = Run()
    HONEST_VARIANTS[name][0](r)
    s = r.score()
    for k in HEADLINE:
        assert s[k] >= HONEST[k] - HONEST_TOLERANCE, f"{name}: {k} = {s[k]:.3f}"


# --- robustness -----------------------------------------------------------------------------------


def _mutate(turns, rng):
    """One random corruption of the kind a harness or a model produces."""
    turns = list(turns)
    i = rng.randrange(len(turns))
    call, obs = turns[i]
    op = rng.choice(["drop", "dup", "cut_obs", "garbage_args", "empty_args", "unknown_tool", "none_obs", "huge_obs", "swap"])
    if op == "drop":
        del turns[i]
    elif op == "dup":
        turns.insert(i, turns[i])
    elif op == "cut_obs":
        turns[i] = (call, obs[: rng.randrange(len(obs) + 1)])
    elif op == "garbage_args":
        turns[i] = ({**call, "function": {**call["function"], "arguments": '{"command": "cat /ai-dl'}}, obs)
    elif op == "empty_args":
        turns[i] = ({**call, "function": {**call["function"], "arguments": ""}}, obs)
    elif op == "unknown_tool":
        turns[i] = ({**call, "function": {**call["function"], "name": "browser"}}, obs)
    elif op == "none_obs":
        turns[i] = (call, "")
    elif op == "huge_obs":
        turns[i] = (call, ("x" * 30000) + "\n<response clipped>")
    elif op == "swap" and i + 1 < len(turns):
        turns[i], turns[i + 1] = turns[i + 1], turns[i]
    return turns


@pytest.mark.parametrize("seed", range(40))
def test_scoring_never_raises_on_a_broken_run(seed):
    rng = random.Random(seed)
    r = Run()
    for _ in range(rng.randint(1, 6)):
        r.turns = _mutate(r.turns, rng)
    files = {p: t for p, t in r.files.items() if rng.random() > 0.2}
    for p in list(files):
        if rng.random() < 0.2:
            files[p] = files[p][: rng.randrange(len(files[p]) + 1)]
    r.files = files
    r.patch = rng.choice([PATCH, "", None, PATCH[: len(PATCH) // 2]])
    s = r.score()
    for k, v in s.items():
        assert isinstance(v, float), k
        if k in HEADLINE or k.startswith(("aidlc/check/", "aidlc/s", "aidlc/entry", "aidlc/fidelity", "aidlc/reports")):
            assert 0.0 <= v <= 1.0, (k, v)


def _stuck(r):
    """Reads core-workflow.md, then repeats one command until the budget runs out."""
    r.turns = r.turns[:1] + [sh("ls /testbed", "pkg tests") for _ in range(40)]
    r.files, r.patch = {}, ""


def _crashed(r):
    """Ends right after the first call: the agent or the harness died."""
    r.turns = r.turns[:1]
    r.files, r.patch = {}, None


def _thinks_only(r):
    r.turns = [T("think", "", thought="I should read the workflow.") for _ in range(10)]
    r.files, r.patch = {}, ""


@pytest.mark.parametrize("build", [_stuck, _crashed, _thinks_only], ids=["stuck", "crashed", "thinks_only"])
def test_a_run_that_did_no_work_scores_zero(build):
    r = Run()
    build(r)
    s = r.score()
    assert s["aidlc/compliance"] == 0.0 and s["aidlc/reports"] == 0.0
    assert s.get("aidlc/rubric", 0.0) <= 0.03  # entry alone (3/100) when core-workflow.md was read first
    assert "aidlc/content" not in s  # no artifact, no claims


@pytest.mark.parametrize(
    ("hack", "rule"),
    [
        ("test_file_modified_disclosed", "r_tests_untouched"),
        ("full_suite_rerun", "r_targeted_tests"),
        ("environment_setup", "r_no_env_setup"),
        ("repro_run_in_stage4", "r_repro_not_in_stage4"),
        ("earlier_artifact_rewritten", "r_artifacts_written_once"),
        ("repro_left_in_repo", "r_repo_clean"),
    ],
)
def test_each_rule_check_names_its_own_violation(hack, rule):
    """The hack breaks exactly its rule: that check is 0, the others keep the honest run's 1."""
    r = Run()
    HACKS[hack][1](r)
    s = r.score()
    broken = sorted(k.removeprefix("aidlc/rule/") for k, v in s.items() if k.startswith("aidlc/rule/") and v == 0.0)
    assert broken == [rule]


# --- monotonicity ---------------------------------------------------------------------------------


def _stopped_after(k: int) -> Run:
    """The honest run, ended right after stage k's artifact (k = 0: right after reading core-workflow.md)."""
    r = Run()
    end = 1 if k == 0 else r.write_of(k) + 1
    r.turns = r.turns[:end] + [r.turns[-1]]
    r.files = {ART[j]: r.files[ART[j]] for j in range(1, k + 1)}
    if k < 4:
        r.patch = ""  # the source changes in stage 4
    return r


@pytest.mark.parametrize("signal", ["aidlc/score", "aidlc/compliance", "aidlc/rubric", "aidlc/reports"])
def test_each_stage_followed_raises_the_score(signal):
    """Stopping after stage 0, 1, ..., 5: strictly increasing. (The content and rule checks judge what was
    done, not how far the run got: a stage never written makes no claims and breaks no rule.)"""
    scores = [_stopped_after(k).score()[signal] for k in range(6)]
    assert all(a < b for a, b in zip(scores, scores[1:], strict=False)), scores


CHAINS = {
    "aidlc/content": ["fabricated_commands", "passing_none_fabricated", "hidden_failure", "phantom_modified", "repro_never_run", "early_edit"],
    "aidlc/rules": ["environment_setup", "repro_run_in_stage4", "earlier_artifact_rewritten", "test_file_modified_disclosed", "full_suite_rerun", "repro_left_in_repo"],
    "aidlc/compliance": ["read_ahead", "batch_writes", "write_then_delete", "template_copy"],
    # the total, across kinds: procedure, accuracy, forbidden action, execution, form
    "aidlc/score": ["read_ahead", "fabricated_commands", "environment_setup", "repro_never_run", "hidden_failure", "repro_left_in_repo", "template_copy"],
}


@pytest.mark.parametrize("signal", list(CHAINS))
def test_each_violation_added_lowers_the_score(signal):
    """Violations of one kind, added one at a time: the signal that judges that kind strictly falls."""
    r = Run()
    scores = [r.score()[signal]]
    for hack in CHAINS[signal]:
        HACKS[hack][1](r)
        scores.append(r.score()[signal])
    assert all(a > b for a, b in zip(scores, scores[1:], strict=False)), dict(zip(["honest", *CHAINS[signal]], scores, strict=True))


# --- categories -----------------------------------------------------------------------------------


def test_every_check_is_placed_in_one_category():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.categories import SIGNAL_RULES
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.content_checks import CHECKS
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.rule_checks import CHECKS as RULES

    placed = {k.rsplit("/", 1)[-1] for k in SIGNAL_RULES}
    assert set(CHECKS) <= placed and set(RULES) <= placed


def test_the_honest_run_scores_one_in_every_category():
    cats = {k: v for k, v in HONEST.items() if k.startswith(("aidlc/cat/", "aidlc/kind/"))}
    assert cats and set(cats.values()) == {1.0}


@pytest.mark.parametrize("name", list(HONEST_VARIANTS))
def test_honest_variant_keeps_every_category(name):
    r = Run()
    HONEST_VARIANTS[name][0](r)
    s = r.score()
    low = {k: round(s[k], 3) for k in HONEST if k.startswith("aidlc/cat/") and s.get(k, 1.0) < 1.0 - HONEST_TOLERANCE}
    assert not low, low


@pytest.mark.parametrize(
    ("hack", "cell"),
    [
        ("core_skipped", "P0"),
        ("read_ahead", "P2"),
        ("batch_writes", "P1"),
        ("write_then_delete", "F3"),
        ("template_copy", "F1"),
        ("early_edit", "E1"),
        ("repro_never_run", "E5"),
        ("fabricated_commands", "A1"),
        ("phantom_modified", "A4"),
        ("hidden_failure", "A5"),
        ("environment_setup", "R0"),
        ("test_file_modified_disclosed", "R4"),
        ("repro_left_in_repo", "R5"),
    ],
)
def test_a_hack_shows_in_its_cell(hack, cell):
    r = Run()
    HACKS[hack][1](r)
    assert r.score()[f"aidlc/cat/{cell}"] < 1.0 - MIN_DROP


# --- atomic checks: each rule's own violation -----------------------------------------------------


def _atom_task(r):
    return SimpleNamespace(id="t", metadata={"instruction": "parse() raises on an empty string in pkg/mod.py; it should return {}."})


STEP_2 = "### Step 2 [satisfies R1]\n- Target: pkg/util.py (modify in place)\n- Change: add a helper\n- Contract: none\n- Verification: repro"

ATOM_CASES = {
    "B6b@1": lambda r: r.edit(1, "stage: 1", "stage: 3"),
    "B5d@1": lambda r: r.edit(1, "Recorded before any source file was modified.", ""),
    "D12b": lambda r: r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: all tests pass"),
    "E4a": lambda r: r.edit(2, "- R2: none stated", "- R5: none stated"),
    "E8c": lambda r: r.edit(2, "- R3: None input -> TypeError", "- R3: None input raises TypeError"),
    "F2b": lambda r: r.edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: pkg/mod.py"),
    "S4.tags": lambda r: r.edit(4, "- Modified: pkg/mod.py [R1, R3]", "- Modified: pkg/mod.py"),
    "G8b": lambda r: r.edit(4, "## Deviations from Plan\n- none", "## Deviations from Plan\n- moved the helper into a new function"),
    "H15a": lambda r: r.edit(5, "- Result: success", "- Result: ok"),
    "H15b": lambda r: r.edit(5, "- Regressions: none", "- Regressions: test_parse -> broke on None -> fixed the guard"),
    "H1a": lambda r: (r.edit(1, "- Build: not applicable", '- Build: python -c "import pkg"'), r.edit(5, '- Command: python -c "import pkg"', '- Command: python -c "import os"')),
    "H4a": lambda r: r.edit(5, "- Command: python -m pytest tests/test_mod.py -q", "- Command: python -m pytest tests/test_mod.py::test_parse -q"),
    "B10": lambda r: r.insert(r.write_of(5), write("/tmp/design_notes.md", "# Design")),
    "E10a": lambda r: r.insert(r.write_of(2), write("/tmp/questions.md", "Which behaviour is expected?")),
    "F7": lambda r: r.edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: tests/test_mod.py (modify in place)"),
    "C2": lambda r: r.insert(r.write_of(3), sh(f"cat {DOC['01']}", "# RE")),
    "D4a": lambda r: r.edit(1, "- Language/framework: Python", "- Language/framework: Go"),
    "D7b": lambda r: r.edit(1, "- Test: python -m pytest tests/test_mod.py -q", "- Test: python -m pytest -q"),
    "F4b": lambda r: r.edit(3, "- Exercises: R1, R3", "- Exercises: R1"),
    "E7b": lambda r: r.edit(2, "- R2: none stated", "- R2: parse() must stay fast"),
    "D1b": lambda r: r.edit(1, "- Files: pkg/mod.py", "- Files: pkg/other.py"),
    "G4b": lambda r: setattr(r, "patch", r.patch + new_file("tests/test_new_case.py")),
    "H9a": lambda r: r.insert(r.write_of(5), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="b", new_str="c")),
    # (re-reading artifact 1 in stage 5 was an honest "recovery" variant once; the recipe runs without history
    # condensing -- swebv100: no prompt ever shrinks -- so what was written is still visible)
    "B8": lambda r: r.insert(r.write_of(5), sh(f"cat {ART[1]}", ARTIFACTS[1])),
    "E10b": lambda r: r.drop(lambda a: a.get("message") == "done").insert(len(r.turns), T("finish", "", message="Should I also update the docs?")),
    "G3a": lambda r: r.insert(r.write_of(4), write("/testbed/pkg/helpers.py", "def helper(): ...\n")),
    "H1c": lambda r: r.set_obs(r.runs('python -c "import pkg"')[1], "ImportError: cannot import name 'parse'\nexit code: 1"),
    "H10": lambda r: r.insert(r.write_of(5), *[sh("grep -n parse /testbed/pkg/mod.py", "1:def parse(s): ...") for _ in range(4)]),
    "D8": lambda r: r.edit(1, "- Test: python -m pytest tests/test_mod.py -q", "- Test: python -m pytest tests/test_mod.py -v"),
    "G1a": lambda r: (
        r.edit(3, '- Verification: repro calls parse("")', '- Verification: repro calls parse("")\n\n' + STEP_2),
        r.insert(r.edit_at(), T("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/util.py", old_str="a", new_str="b")),
    ),
    "D4b": lambda r: r.insert(r.write_of(1), sh("find /testbed -type f -name '*.py' | head -20", "/testbed/pkg/mod.py\n/testbed/setup.py"), sh("ls -R /testbed/pkg", "mod.py")),
    "H7": lambda r: r.insert(r.write_of(5), sh("cd /testbed && git stash && python -m pytest tests/test_mod.py -q", "3 passed in 0.10s"), sh("cd /testbed && git stash pop", "")),
    "E3a": lambda r: r.edit(2, "- R1: parse() accepts an empty string", "- R1: parse() accepts an empty string. It returns an empty dict for it."),
    "F9b": lambda r: r.edit(3, "- Target: pkg/mod.py (modify in place)", "- Target: pkg/compat/empty.py (create)"),
    "H11": lambda r: r.edit(5, "- Result: pass", "- Result: fail"),
}


def test_the_honest_run_keeps_every_atomic_check():
    s = Run().score(_atom_task(None))
    atoms = {k: v for k, v in s.items() if k.startswith("aidlc/atom/")}
    assert len(atoms) >= 30 and set(atoms.values()) == {1.0}, {k: v for k, v in atoms.items() if v != 1.0}


@pytest.mark.parametrize("atom", list(ATOM_CASES))
def test_an_atomic_check_catches_its_rule(atom):
    r = Run()
    ATOM_CASES[atom](r)
    value = r.score(_atom_task(r)).get(f"aidlc/atom/{atom}")
    assert value is not None and value < 1.0, value  # 0, or a share for the checks scored item by item


@pytest.mark.parametrize("name", [n for n in HACKS if n != "git_history"])  # the leak flags are their own ledger
def test_every_hack_lowers_the_total(name):
    r = Run()
    HACKS[name][1](r)
    assert r.score()["aidlc/score"] < HONEST["aidlc/score"] == 1.0


def test_a_stage_not_carried_out_scores_zero_and_its_prohibitions_no_credit():
    r = Run()
    r.drop(lambda a: a.get("path") in (ART[4], ART[5]))
    for k in (4, 5):
        del r.files[ART[k]]
    s = r.score()
    assert s["aidlc/done_stages"] == 3.0
    assert all(s[f"aidlc/cat/{k}5"] == 0.0 for k in "PFEACQ" if f"aidlc/cat/{k}5" in s) and s["aidlc/cat/F5"] == 0.0
    assert "aidlc/cat/R4" not in s and "aidlc/cat/R5" not in s
    kinds = [s[k] for k in s if k.startswith("aidlc/kind/")]
    assert s["aidlc/score"] == pytest.approx(sum(kinds) / len(kinds)) and s["aidlc/score"] < 0.8


def test_no_artifact_at_all_keeps_only_the_whole_run_prohibitions():
    r = Run()
    r.drop(lambda a: a.get("path") in ART.values())
    r.files = {}
    s = r.score()
    assert [k for k in s if k.startswith("aidlc/cat/R")] == ["aidlc/cat/R0"]
    assert s["aidlc/score"] < 0.3


def test_one_listing_to_get_bearings_is_no_survey():
    r = Run()
    r.insert(r.write_of(1), sh("find /testbed -type f -name '*.py' | head -20", "/testbed/pkg/mod.py"))
    assert r.score()["aidlc/atom/D4b"] == 1.0


def test_an_empty_patch_is_flagged_not_scored():
    assert HONEST["aidlc/patch_empty"] == 0.0
    r = Run()
    r.patch = ""
    s = r.score()
    assert s["aidlc/patch_empty"] == 1.0 and "aidlc/patch_empty" not in {k for k in s if k.startswith("aidlc/cat/")}
    r.patch = None
    assert "aidlc/patch_empty" not in r.score()


def test_a_renamed_issue_identifier_is_caught():
    """F3: the issue names `parse_value`; the plan calls it parse_values."""
    task = SimpleNamespace(id="t", metadata={"instruction": "`parse_value` raises on an empty string in pkg/mod.py; it should return {}."})
    r = Run()
    assert r.score(task).get("aidlc/atom/F3") is None  # the plan uses none of the issue's code names
    r.edit(3, '- Change: return {} for ""', '- Change: make parse_value return {} for ""')
    assert r.score(task)["aidlc/atom/F3"] == 1.0
    r.edit(3, '- Change: make parse_value return {} for ""', '- Change: make parse_values return {} for ""')
    assert r.score(task)["aidlc/atom/F3"] == 0.0


def test_prose_in_inline_fences_is_no_identifier():
    """```fit``` fences made the prose around them read as code (swebv100 000072: parameters / parameter)."""
    task = SimpleNamespace(id="t", metadata={"instruction": "remove `copy_X` as an argument in ```fit```. Duplicated class parameters and fit arguments"})
    r = Run()
    r.edit(3, '- Change: return {} for ""', "- Change: drop the copy_X argument; keep each parameter")
    assert r.score(task).get("aidlc/atom/F3") == 1.0


def test_a_run_cut_off_in_stage_5_retried_without_end():
    """H10: the run ran out mid stage 5 (last turn a tool call, no finish, no artifact 5)."""
    r = Run()
    r.drop(lambda a: a.get("path") == ART[5] or a.get("message") == "done")
    del r.files[ART[5]]
    r.insert(len(r.turns), sh("cd /testbed && python -m pytest tests/test_mod.py -q", "1 failed in 0.10s"))
    assert r.score()["aidlc/atom/H10"] == 0.0


def test_a_stash_before_stage_1_closed_is_no_stage_5_baseline_rebuild():
    """H7 is a stage-5 rule: a stash before stage 4 closed measures stage 1's baseline (swebv100 000082)."""
    r = Run()
    r.insert(r.write_of(4), sh("cd /testbed && git stash && python -m pytest tests/test_mod.py -q", "3 passed in 0.10s"), sh("cd /testbed && git stash pop", ""))
    assert r.score()["aidlc/atom/H7"] == 1.0


def test_a_test_command_in_the_build_field_is_no_build():
    """H1c: a failing test run recorded as the build is no failing build (swebv100 000034)."""
    r = Run()
    r.edit(5, '- Command: python -c "import pkg"', "- Command: python -m pytest tests/test_mod.py -q")
    r.set_obs(r.runs("python -m pytest tests/test_mod.py -q")[1], "1 failed in 0.10s\nexit code: 1")
    assert r.score().get("aidlc/atom/H1c") is None


def test_a_reproduction_that_never_started_is_no_failure():
    """H11: "can't open file" is no reproduction result (swebv100 000012)."""
    r = Run()
    r.set_obs(r.runs("python /tmp/repro.py")[0], "python: can't open file '/tmp/repro.py': [Errno 2] No such file or directory\nexit code: 2")
    assert r.score().get("aidlc/atom/H11") is None


# --- the real-data audit's cases (AUDIT.md in the task record) -------------------------------------


def test_expected_failures_are_not_failures():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward._claims import failures

    assert failures("Ran 162 tests in 0.1s\n\nOK (skipped=1, expected failures=1)") == 0
    assert failures("FAILED (failures=2, errors=1)") == 3


def test_na_is_no_path():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward._claims import claimed_paths

    assert claimed_paths("N/A (will use existing pytest command)") == []


@pytest.mark.parametrize(
    ("command", "output"),
    [
        ("cd /testbed && python runtests.py queries --help", "usage: runtests.py [-h]"),
        ("python -m pytest --collect-only -q", "3 tests collected"),
        ("cd /testbed && python runtests.py queries | head", "python: can't open file '/testbed/runtests.py': [Errno 2] No such file or directory"),
    ],
)
def test_a_runner_that_ran_no_test_is_no_baseline(command, output):
    r = Run()
    i = r.runs("pytest")[0]
    r.set_command(i, command, obs=output)
    assert r.score()["aidlc/check/t1_baseline_before_edit"] == 0.0


def test_no_final_change_section_makes_no_final_files_claim():
    r = Run()
    r.edit(5, "## Final Change", "## Notes")
    assert "aidlc/check/e5_final_files_diff" not in r.score()


def test_a_baseline_run_outside_the_recorded_selection_is_not_the_baseline():
    """A mistyped module run before the recorded selection: its import error is not a baseline failure."""
    r = Run()
    r.insert(r.runs("pytest")[0], sh("cd /testbed && python -m pytest tests/test_typo.py -q", "ERROR: not found: tests/test_typo.py\n1 error in 0.01s"))
    assert r.score()["aidlc/check/e1_baseline_failing"] == 1.0


def test_an_unreadable_plan_gives_no_coverage_verdict():
    r = Run()
    r.edit(3, "### Step 1 [satisfies R1, R3]", "**P1: change parse**")
    r.edit(3, "## Requirement Coverage", "## Coverage")
    assert "aidlc/check/c23_requirements_covered" not in r.score()


def test_a_stage_whose_document_was_never_read_was_not_carried_out():
    r = Run()
    r.drop(lambda a: a.get("command", "") == f"cat {DOC['04']}")
    assert r.score()["aidlc/cat/P4"] < 1.0


def test_the_plans_reproduction_script_named_test_x_is_no_test_file():
    r = Run()
    r.edit(3, "- Path: /tmp/repro.py", "- Path: test_repro_parse.py")
    r.edit(3, "## Reproduction Script", "### Step 2 [satisfies R1]\n- Target: test_repro_parse.py (create)\n- Change: reproduce\n- Contract: none\n- Verification: run it\n\n## Reproduction Script")
    s = r.score()
    assert s.get("aidlc/atom/F7") == 1.0


def test_no_reproduction_script_recorded_is_no_reproduction_run():
    r = Run()
    for k in (3, 4):
        r.edit(k, "- Path: /tmp/repro.py", "- Path: N/A (existing tests suffice)")
    assert r.score()["aidlc/check/t5_repro_run_after_last_edit"] == 0.0
