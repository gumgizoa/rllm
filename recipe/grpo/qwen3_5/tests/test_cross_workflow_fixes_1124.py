"""The implementation differences between workflows that the 11-24 cross-workflow probe found
(tasks/2026-11-24-test-reading-consistency/워크플로우-간-일치-확인.md, b-1 .. b-5 and 4.3), and the root-script rule
(item 19): each with an input the fix reads differently and one that must keep its reading.

The workflow tests put the probe's shell text into each workflow's golden run at the probe's place (right before the
final verification report; speckit_sdd: right before T006 is ticked) and score it with the workflow's rubric.

pytest recipe/grpo/qwen3_5/tests/test_cross_workflow_fixes_1124.py
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from recipe.grpo.qwen3_5.workflow_rubric import engine  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import facts as F  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import schema as S  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import testread as T  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.checks.artifacts import _command_run  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, EvalContext  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.generator import selftest as G  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.generator.mutations import refresh, simulate  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.replay import replay  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.schema import Rubric  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.trace.model import Action, Run, Step  # noqa: E402

RECIPE = Path(__file__).resolve().parents[1]
WD = "/testbed"
EXIT0 = "[Command finished with exit code 0]"
EXIT1 = "[Command finished with exit code 1]"
OK3 = "...                                                                      [100%]\n3 passed in 0.02s\n" + EXIT0


# --------------------------------------------------------------------------------------------------------------------
# the probe's insertion into a golden run
# --------------------------------------------------------------------------------------------------------------------
def _gold(wf):
    return importlib.import_module(f"recipe.grpo.qwen3_5.workflows.{wf}.selftest_golden")


def _is_write(a, suffix):
    return a.kind in ("create", "replace") and (a.path or "").endswith(suffix)


def _config(wf: str) -> dict:
    g = _gold(wf)
    if wf in ("agentos_bugfix", "agentos_v2"):
        return dict(src="textkit/slug.py", test="tests/test_slug.py", checks=[f"{g.CHECKS}/check_edges.py", f"{g.CHECKS}/check_sep.py"],
                    at=lambda a: _is_write(a, "verifications/final-verification.md"), related={"textkit/slug.py": ["tests/test_slug.py"]})
    if wf == "speckit_bug":
        return dict(src="tinyconf/values.py", test="tests/test_values.py", checks=[g.CHECK], at=lambda a: _is_write(a, f"{g.BUG}/test.md"),
                    related={"tinyconf/values.py": ["tests/test_values.py"]}, inputs={"gold_files": ["tinyconf/values.py"]})
    if wf == "openspec_ff":
        return dict(src="tinyconf/values.py", test="tests/test_values.py", checks=[g.CHECK], at=lambda a: _is_write(a, f"{g.CHG}/verify.md"),
                    related={"tinyconf/values.py": ["tests/test_values.py"]})
    if wf == "speckit_sdd":
        return dict(src="strkit/text.py", test="tests/test_text.py", checks=[f"{g.CHECKS}/test_us1.py"],
                    at=lambda a: a.kind == "replace" and (a.path or "").endswith("/tasks.md") and "- [ ] T006 " in (a.old or ""),
                    related={"strkit/text.py": ["tests/test_text.py"], "strkit/__init__.py": ["tests/test_text.py"]})
    raise ValueError(wf)


_RUBRICS: dict = {}


def _rubric(wf):
    if wf not in _RUBRICS:
        d = RECIPE / "workflows" / wf
        rub = G.with_docs(S.load(d / "reward" / "rubric.yaml"), d)
        assert G.load_plugins(rub) == []
        _RUBRICS[wf] = rub
    return _RUBRICS[wf]


def _fmt(t: str, c: dict) -> str:
    return t.replace("{SRC}", c["src"]).replace("{TEST}", c["test"]).replace("{CHECK}", c["checks"][0])


def _sh(command: str, obs: str = EXIT0) -> Step:
    return Step(0, [Action("shell", "terminal", command=command, observation=obs)], "")


def score(wf: str, steps: list[tuple[str, str]] | None = None, mutate=None):
    """The workflow's golden run with ``steps`` (shell text, observation; ``{SRC}`` ``{TEST}`` ``{CHECK}`` filled in)
    put in at the probe's place, or changed by ``mutate(run, config)``; the engine's results by item id."""
    c = _config(wf)
    rub = _rubric(wf)
    run, col = _gold(wf).golden(rub)
    run = copy.deepcopy(run)
    if steps is not None or mutate is not None:
        if mutate is not None:
            mutate(run, c)
        else:
            at = next(i for i, st in enumerate(run.steps) if any(c["at"](a) for a in st.actions))
            for k, (cmd, obs) in enumerate(steps):
                run.steps.insert(at + k, _sh(_fmt(cmd, c), _fmt(obs, c)))
        for n, st in enumerate(run.steps, 1):
            st.n = n
        meta = run.meta.get("selftest") or {}
        if wf == "openspec_ff":
            g = _gold(wf)
            files = dict(col.files)
            for p, t in replay(run, WD).final.items():
                if t is not None and p.startswith(g.CHG + "/"):
                    files[g.ARCH + p[len(g.CHG):]] = t
            col.files = files
            refresh(run, col)
        else:
            col = simulate(run, workdir=meta["workdir"], base_sha=meta["base_sha"], base_tree=meta["base_tree"], artifact_dirs=meta["artifact_dirs"], base_files=meta.get("base_files"))
    col.related_tests = {k: list(v) for k, v in c["related"].items()}
    if c.get("inputs"):
        col.inputs = {**(col.inputs or {}), **c["inputs"]}
    rep = engine.evaluate(rub, run, col)
    assert rep.engine_errors == 0
    return rep.results


def _st(res, iid):
    r = res[iid]
    return r.status, round(float(r.score), 4)


EDIT = "cd /testbed && sed -i '1s/$/  # edited/' {SRC}"


# --------------------------------------------------------------------------------------------------------------------
# b-1: agentos_bugfix -- a run after the PHASE 3 edit in the same command is after it (R2)
# --------------------------------------------------------------------------------------------------------------------
def test_agentos_bugfix_reads_a_run_after_the_phase3_edit_in_its_call_as_after_it():
    suite = "agentos_bugfix.implement_tasks.run.agentos_bugfix_verify.suite_run"
    p3 = "agentos_bugfix.implement_tasks.penalty.phase3_run.existing_and_own"
    checks = " && ".join(f"python {c}" for c in _config("agentos_bugfix")["checks"])
    # was "no valid test run between the last tick and the report": the run follows the write in its call
    res = score("agentos_bugfix", [(EDIT + " && python -m pytest {TEST} -q && " + checks, OK3)])
    assert _st(res, suite) == ("pass", 1.0)
    assert _st(res, p3) == ("pass", 1.0)
    # must keep: a run before the write in its call is no run after it
    res = score("agentos_bugfix", [("cd /testbed && python -m pytest {TEST} -q && " + checks + "; sed -i '1s/$/  # edited/' {SRC}", OK3)])
    assert res[suite].status == "fail"
    assert _st(res, p3) == ("fail", 0.0)


def test_agentos_v2_fix_round_runs_follow_the_write_in_their_call():
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    c = _config("agentos_bugfix")
    rub = _rubric("agentos_bugfix")
    run, col = _gold("agentos_bugfix").golden(rub)
    at = next(i for i, st in enumerate(run.steps) if any(c["at"](a) for a in st.actions))
    run.steps.insert(at, _sh(_fmt(EDIT + " && python -m pytest {TEST} -q", c), OK3))
    for n, st in enumerate(run.steps, 1):
        st.n = n
    meta = run.meta["selftest"]
    col = simulate(run, workdir=meta["workdir"], base_sha=meta["base_sha"], base_tree=meta["base_tree"], artifact_dirs=meta["artifact_dirs"], base_files=meta.get("base_files"))
    ctx = EvalContext(rubric=rub, run=run, collected=col, facts=F.build(rub, run, col))
    late = C._phase3_edits(ctx)
    assert late and [r.step for r in C._phase3_runs(ctx, after_fix=True)] == [late[-1].step]


# --------------------------------------------------------------------------------------------------------------------
# b-2: speckit_sdd tests_pass -- order in the call, the change put away, the baseline's failures
# --------------------------------------------------------------------------------------------------------------------
SDD_PASS = "speckit_sdd.implement.run.speckit_holds.tests_pass"


def _fail_out(test: str, name: str | None, dots: str) -> str:
    summary = f"=========================== short test summary info ============================\nFAILED {test}::{name} - AssertionError\n" if name else ""
    return f"{dots}                                                                      [100%]\n{summary}1 failed, 2 passed in 0.03s\n{EXIT1}"


def _baseline_fails(before_name, after_name):
    """Every run of the repository test module fails ``before_name`` before the first source change and ``after_name``
    after it (as the probe's S5)."""

    def mutate(run, c):
        first = next(i for i, st in enumerate(run.steps) if any(_is_write(a, c["src"]) for a in st.actions))
        for i, st in enumerate(run.steps):
            for a in st.actions:
                cmd = (a.command or "").strip()
                if a.kind == "shell" and "pytest" in cmd and c["checks"][0] not in cmd and (c["test"] in cmd or cmd.endswith("python -m pytest")):
                    a.observation = _fail_out(c["test"], before_name if i < first else after_name, "F..")

    return mutate


def test_speckit_sdd_tests_pass_reads_the_order_in_a_call_and_leaves_stash_runs_out():
    assert score("speckit_sdd")[SDD_PASS].status == "pass"  # must keep: the golden
    # S2: the only run after the change ran before it, in the same call
    assert score("speckit_sdd", [("cd /testbed && python -m pytest {TEST} -q; sed -i '1s/$/  # edited/' {SRC}", OK3)])[SDD_PASS].status == "fail"
    # S3: the only run after the change ran with it stashed away
    stash = "cd /testbed && git stash && python -m pytest {TEST} -q ; git stash pop"
    assert score("speckit_sdd", [(EDIT, EXIT0), (stash, "Saved working directory\n" + OK3.replace(EXIT0, "") + EXIT0)])[SDD_PASS].status == "fail"
    # must keep: S1, the run after the write in its call
    assert score("speckit_sdd", [(EDIT + " && python -m pytest {TEST} -q", OK3)])[SDD_PASS].status == "pass"


def test_speckit_sdd_tests_pass_leaves_a_failure_the_baseline_already_had():
    # S5c: the same test fails before and after the change -- the baseline's own failure
    assert score("speckit_sdd", mutate=_baseline_fails("test_a", "test_a"))[SDD_PASS].status == "pass"
    # must keep: a new failure (another name), and one the output does not name
    assert score("speckit_sdd", mutate=_baseline_fails("test_a", "test_b"))[SDD_PASS].status == "fail"
    assert score("speckit_sdd", mutate=_baseline_fails(None, None))[SDD_PASS].status == "fail"


# --------------------------------------------------------------------------------------------------------------------
# b-3: openspec_ff -- every check script ran after the last code change and after its own last write
# --------------------------------------------------------------------------------------------------------------------
OS_CHECKS = "openspec_ff.verify.run.openspec_ff_checks.run_after_change"


def test_openspec_ff_asks_every_check_script_to_run_after_the_last_change():
    assert _st(score("openspec_ff"), OS_CHECKS) == ("pass", 1.0)  # must keep: the golden runs its check last
    # S1: a code change after the check's last run, the repository tests run again but not the check
    assert _st(score("openspec_ff", [(EDIT + " && python -m pytest {TEST} -q", OK3)]), OS_CHECKS) == ("fail", 0.0)
    # S6: the check rewritten after its last run
    assert _st(score("openspec_ff", [("cd /testbed && sed -i '1s/$/  # edited/' {CHECK}", EXIT0)]), OS_CHECKS) == ("fail", 0.0)
    # must keep: the check run again after both, in the call of the change after the write (R2)
    res = score("openspec_ff", [(EDIT + " && python -m pytest {TEST} -q && python {CHECK}", OK3)])
    assert _st(res, OS_CHECKS) == ("pass", 1.0)


# --------------------------------------------------------------------------------------------------------------------
# b-4 and 4.3: a test function added to a repository test module is the run's own test (agentos_v2 as agentos_bugfix;
# printf's escapes read)
# --------------------------------------------------------------------------------------------------------------------
APPEND_HEREDOC = "cd /testbed && cat >> {TEST} <<'EOF'\n\n\ndef test_own_case():\n    assert True\nEOF"
APPEND_PRINTF = "cd /testbed && printf '\\n\\ndef test_own_case():\\n    assert True\\n' >> {TEST}"


@pytest.mark.parametrize("wf", ["agentos_v2", "agentos_bugfix"])
@pytest.mark.parametrize("append", [APPEND_HEREDOC, APPEND_PRINTF])
def test_a_test_function_added_after_the_last_run_is_an_own_test_never_run(wf, append):
    item = f"{wf}.implement_tasks.run.{wf}_checks.pass_last"
    assert _st(score(wf), item) == ("pass", 1.0)  # must keep: the golden
    res = score(wf, [(append, EXIT0)])
    assert res[item].status == "fail" and "test_slug.py (never run)" in res[item].detail
    # must keep: the module run after the function was added
    res = score(wf, [(append, EXIT0), ("cd /testbed && python -m pytest {TEST} -q", OK3.replace("...", "...."))])
    assert _st(res, item) == ("pass", 1.0)


def test_added_test_functions_reads_printf_escapes():
    from recipe.grpo.qwen3_5.workflows.agentos_v2.reward import checks as C

    def added(command):
        run = Run("t", [Step(1, [Action("shell", "terminal", command=command, observation="")])])
        ctx = SimpleNamespace(run=run)
        return C.added_test_functions(ctx, SimpleNamespace(step=1, action_index=0, removed_existing=False, op="append", content=None))

    assert added("printf '\\n\\ndef test_x():\\n    assert 1\\n' >> tests/test_a.py") == {"test_x"}
    assert added("cat >> tests/test_a.py <<'EOF'\ndef test_y():\n    pass\nEOF") == {"test_y"}
    # must keep: a definition in the middle of a line is none (``grep 'def test_x'``), escaped or not
    assert added("grep -n 'def test_x' tests/test_a.py >> /tmp/out") == set()
    assert added("printf 'x = 1  # def test_z():\\n' >> tests/test_a.py") == set()


# --------------------------------------------------------------------------------------------------------------------
# b-5: git putting content back is no repository write the agent authored (prohibited_action repo_write)
# --------------------------------------------------------------------------------------------------------------------
STASH_RUN = "cd /testbed && git stash -q && python -m pytest {TEST} -q; git stash pop -q"


@pytest.mark.parametrize(("wf", "item"), [("speckit_bug", "speckit_bug.test.run.prohibited_action.repo_write"),
                                          ("openspec_ff", "openspec_ff.verify.run.prohibited_action.repo_write")])
def test_a_stash_run_is_no_repository_write(wf, item):
    assert score(wf, [(STASH_RUN, OK3)])[item].status == "pass"
    # must keep: an edit the agent makes, also one git does not show by name (``xargs sed -i``)
    assert score(wf, [(EDIT, EXIT0)])[item].status == "fail"
    assert score(wf, [("cd /testbed && ls {SRC} | xargs sed -i '1s/$/  # edited/'", EXIT0)])[item].status == "fail"


def _ctx(actions, base=("pkg/mod.py", "tests/test_mod.py")):
    run = Run("t", [Step(n, [a]) for n, a in enumerate(actions, 1)] + [Step(len(actions) + 1, [Action("other")])])
    rub = Rubric(workflow="", sources=[], roots={}, stages=[], artifacts={}, items=[], scoring={})
    col = Collected(workdir=WD, diff={"pkg/mod.py": "M"}, mode="online", base_present={p: True for p in base})
    return EvalContext(rubric=rub, run=run, collected=col, facts=F.build(rub, run, col))


def _shell(command: str, observation: str = "\n[The command completed with exit code 0.]") -> Action:
    return Action("shell", "terminal", command=command, observation=observation)


EDIT_MOD = Action("replace", "file_editor", path=f"{WD}/pkg/mod.py", old="a = 1", text="a = 2", status="ok", observation="edited")


def test_git_put_back_is_git_only():
    ctx = _ctx([EDIT_MOD, _shell("git stash && python -m pytest tests/test_mod.py; git stash pop"), _shell("git checkout -- pkg/mod.py"),
                _shell("ls pkg/mod.py | xargs sed -i 's/a/b/'")])
    by_step = {}
    for e in ctx.facts.repo_writes:
        by_step.setdefault(int(e.step), []).append(T.git_put_back(ctx, e))
    assert by_step[1] == [False]  # must keep: the agent's edit
    assert by_step[2] and all(by_step[2]) and by_step[3] and all(by_step[3])  # stash / pop, checkout
    assert by_step[4] and not any(by_step[4])  # must keep: a write no command names a path of, made by sed


# --------------------------------------------------------------------------------------------------------------------
# 4.3: a claimed command run before the edit of its call, or with the change stashed, is not a run in a window that
# starts at the change (speckit_bug checks_table.commands_run, the shared _command_run)
# --------------------------------------------------------------------------------------------------------------------
PASS1 = "tests/test_mod.py .\n=========== 1 passed in 0.1s ===========\n[The command completed with exit code 0.]"


def test_command_run_reads_the_order_in_a_call_and_leaves_stash_runs_out():
    item = SimpleNamespace(id="x")
    cmd = "python -m pytest tests/test_mod.py"
    before = _ctx([_shell(f"{cmd}; sed -i 's/a = 1/a = 2/' pkg/mod.py", PASS1)])
    assert _command_run(item, before, cmd, (1, None), None).status == "fail"
    after = _ctx([_shell(f"sed -i 's/a = 1/a = 2/' pkg/mod.py && {cmd}", PASS1)])
    assert _command_run(item, after, cmd, (1, None), None).status == "pass"  # must keep
    stashed = _ctx([EDIT_MOD, _shell(f"git stash && {cmd}; git stash pop", PASS1)])
    assert _command_run(item, stashed, cmd, (1, None), None).status == "fail"
    assert _command_run(item, stashed, cmd, (1, None), "test").status == "fail"
    plain = _ctx([EDIT_MOD, _shell(cmd, PASS1)])
    assert _command_run(item, plain, cmd, (1, None), None).status == "pass"  # must keep
    assert _command_run(item, plain, cmd, (1, None), "test").status == "pass"


# --------------------------------------------------------------------------------------------------------------------
# item 19: a script the run made at the repository root is no repository test file
# --------------------------------------------------------------------------------------------------------------------
def _root_ctx(base_root_test: bool):
    base = ("pkg/mod.py", "tests/test_mod.py") + (("test_requests.py",) if base_root_test else ())
    acts = [Action("create", "file_editor", path=f"{WD}/test_repro.py", text="print('PASS')\n", status="ok", observation="File created"),
            Action("replace", "file_editor", path=f"{WD}/test_requests.py", old="a", text="b", status="ok", observation="edited"),
            Action("create", "file_editor", path=f"{WD}/tests/test_new.py", text="def test_x():\n    pass\n", status="ok", observation="File created")]
    return _ctx(acts, base=base)


def test_a_root_script_the_run_made_is_no_repository_test_file():
    ctx = _root_ctx(base_root_test=True)
    assert F.is_test_path("test_repro.py") and not F.is_repo_test_file(ctx, "test_repro.py")
    # must keep: a root test file that existed at BASE_SHA, and a new test file under tests/
    assert F.is_repo_test_file(ctx, "test_requests.py")
    assert F.is_repo_test_file(ctx, "tests/test_new.py")
    assert not F.is_repo_test_file(ctx, "pkg/mod.py")


def test_repo_edit_test_paths_leaves_root_scripts_out():
    from recipe.grpo.qwen3_5.workflow_rubric import refs

    ctx = _root_ctx(base_root_test=True)
    tests = {e.path for e in refs.matching(ctx, {"fact": "repo_edit", "test_paths": True})}
    others = {e.path for e in refs.matching(ctx, {"fact": "repo_edit", "test_paths": False})}
    assert "test_repro.py" not in tests and "test_repro.py" in others
    assert {"test_requests.py", "tests/test_new.py"} <= tests  # must keep


def test_agentos_bugfix_does_not_take_a_root_script_for_a_test_edit():
    from recipe.grpo.qwen3_5.workflows.agentos_bugfix.reward import penalty_tests as P

    ctx = _root_ctx(base_root_test=True)
    tl = P.timeline(ctx)
    assert "test_repro.py" not in tl.test_edits_of
    assert {"test_requests.py", "tests/test_new.py"} <= set(tl.test_edits_of)  # must keep
