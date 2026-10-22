"""workflows/aidlc_v4_eval: the evaluation verifier stands on its own, stays fixed, and scores
aidlc_v4's signals plus the content checks.

    pytest recipe/grpo/qwen3_5/tests/test_aidlc_v4_eval.py

The pinned hashes are the point of the package: aidlc_v4 (the training workflow) may change, this one
must not follow it. A failing pin means a file of the evaluation verifier changed -- if that is
intended, it is a new verifier version, and numbers measured before it are not comparable.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RECIPE = Path(__file__).resolve().parents[1]
REPO = RECIPE.parents[2]
sys.path.insert(0, str(REPO))

from test_aidlc_reward import ART, ARTIFACTS, DOC, _call, _collected, _Sandbox, _Verifier, episode  # noqa: E402

from recipe.grpo.qwen3_5.workflows import aidlc_v4_eval, get_workflow  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.evaluator import AidlcEvalComplianceEvaluator, AidlcEvalEvaluation, score  # noqa: E402

PKG = aidlc_v4_eval.HERE

# SPEC.fingerprint: what the agent is given. Equal to aidlc_v4's when copied (4c3ee52c), and to the
# one recorded by the aidlc_v4 runs it rescores (swebv100_aidlcv4_262k-150_think_t1_prefix).
FINGERPRINT = "b9c317de1dd1b28db28d5d960763b85ef63d8d272e687fe1a6103852b0ca14b6"
# The vendored scoring code, byte-identical to aidlc_v4's: legacy/rubric/** and legacy/episode.py (hashed under
# their original reward/ names, so the pin is the one taken when they were copied). This verifier's own
# readings are in reward/ (read.py, trace.py, skeleton.py), tested by behaviour below.
VENDORED = "f15db1ff24a6495d55705f23af62362828b7562253cb06414977590b862d51d4"


def _content_honest_turns() -> list[tuple[dict, str]]:
    """Every stage in order, and every claim the ARTIFACTS make borne out by the trajectory: the
    scope file viewed, baseline and build run before artifact 1, the repro script written before
    artifact 4, build / repro / tests run after the last edit and before artifact 5."""
    t, i = [], iter(range(1000))

    def add(name, obs, **args):
        t.append((_call(next(i), name, **args), obs))

    add("file_editor", "# core", command="view", path="/ai-dlc/core-workflow.md")
    add("terminal", "# RE", command=f"cat {DOC['01']}")
    add("file_editor", "def parse(s): ...", command="view", path="/testbed/pkg/mod.py")
    add("terminal", "tests/test_mod.py::test_parse PASSED\n3 passed in 0.10s", command="cd /testbed && python -m pytest tests/test_mod.py -q")
    add("terminal", "exit code: 0", command='cd /testbed && python -c "import pkg"')
    add("file_editor", "File created successfully", command="create", path=ART[1], file_text=ARTIFACTS[1])
    for k in (2, 3):
        add("terminal", "# doc", command=f"cat {DOC[f'0{k}']}")
        add("file_editor", "File created successfully", command="create", path=ART[k], file_text=ARTIFACTS[k])
    add("terminal", "# doc", command=f"cat {DOC['04']}")
    add("file_editor", "The file has been edited", command="str_replace", path="/testbed/pkg/mod.py", old_str="a", new_str="b")
    add("file_editor", "File created successfully", command="create", path="/tmp/repro.py", file_text="import pkg\n")
    add("file_editor", "File created successfully", command="create", path=ART[4], file_text=ARTIFACTS[4])
    add("terminal", "# doc", command=f"cat {DOC['05']}")
    add("terminal", "exit code: 0", command='cd /testbed && python -c "import pkg"')
    add("terminal", "ok\nexit code: 0", command="python /tmp/repro.py")
    add("terminal", "3 passed in 0.10s", command="cd /testbed && python -m pytest tests/test_mod.py -q")
    add("file_editor", "File created successfully", command="create", path=ART[5], file_text=ARTIFACTS[5])
    add("finish", "", message="done")
    return t


FILES = {ART[k]: ARTIFACTS[k] for k in ART}


# --- standing on its own ---------------------------------------------------------------------


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            out.append("." * node.level + (node.module or ""))
    return out


def test_no_module_imports_aidlc_v4():
    offending = {str(p.relative_to(PKG)): mods for p in PKG.rglob("*.py") if (mods := [m for m in _imported_modules(p) if "aidlc_v4" in m.replace("aidlc_v4_eval", "").split(".")])}
    assert offending == {}


def test_spec_reads_only_its_own_files():
    spec = aidlc_v4_eval.SPEC
    for path in (spec.docs_dir, spec.instruction_file, *spec.system_prompt.values()):
        assert path.resolve().is_relative_to(PKG), path


def test_registered_and_scored_by_its_own_evaluation():
    spec = get_workflow("aidlc_v4_eval")
    assert spec is aidlc_v4_eval.SPEC and spec.reward_signal == "aidlc/score"
    assert isinstance(spec.scorers["openhands-sdk"](), AidlcEvalEvaluation)


# --- fixed -----------------------------------------------------------------------------------


def test_workflow_given_to_the_agent_is_pinned():
    assert aidlc_v4_eval.SPEC.fingerprint("openhands-sdk") == FINGERPRINT


def test_vendored_scoring_code_is_pinned():
    files = sorted((PKG / "legacy" / "rubric").rglob("*.py")) + [PKG / "legacy" / "episode.py"]
    h = hashlib.sha256()
    for p in files:
        name = "reward/" + p.relative_to(PKG / "legacy").as_posix()
        h.update(name.encode() + b"\0" + p.read_bytes() + b"\0")
    assert h.hexdigest() == VENDORED


# --- scoring ---------------------------------------------------------------------------------


def test_content_honest_run_scores_one_everywhere():
    s = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
    assert s["aidlc/compliance"] == pytest.approx(1.0)
    assert [s[f"aidlc/{k}"] for k in ("order", "s1", "s2", "s3", "s4", "s5")] == pytest.approx([1.0] * 6)
    checks = {k: v for k, v in s.items() if k.startswith("aidlc/check/")}
    assert len(checks) == 35 and set(checks.values()) == {1.0}
    assert s["aidlc/content"] == pytest.approx(1.0) and s["aidlc/content_contradictions"] == 0.0


def test_claims_without_the_runs_behind_them_cost_content_not_form():
    """Same artifacts, no test run anywhere: the bands only cap stages 1 and 5, the content checks
    catch every claim that rested on a run."""
    turns = [t for t in _content_honest_turns() if "pytest" not in json.loads(t[0]["function"]["arguments"]).get("command", "")]
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/s1"] == pytest.approx(4 / 7) and s["aidlc/s2"] == pytest.approx(1.0)
    assert s["aidlc/content"] < 1.0 and s["aidlc/content_contradictions"] > 0
    for name in ("e1_test_command_run", "t1_baseline_before_write", "e5_command_run", "t5_regression_after_last_edit"):
        assert s[f"aidlc/check/{name}"] == 0.0, name


def test_a_stage_never_written_makes_no_claims():
    turns = [t for t in _content_honest_turns() if json.loads(t[0]["function"]["arguments"]).get("path") != ART[5]]
    files = {p: t for p, t in FILES.items() if p != ART[5]}
    s = score(SimpleNamespace(id="t"), episode(turns), files)
    assert s["aidlc/s5"] == 0.0
    assert not any(k.startswith(("aidlc/check/e5_", "aidlc/check/t5_")) for k in s)


# --- milestone-1 evaluation rubric items -----------------------------------------------------

PATCH = "diff --git a/pkg/mod.py b/pkg/mod.py\n--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@ -1 +1 @@\n-a\n+b\n"
PATCH_OTHER = "diff --git a/pkg/other.py b/pkg/other.py\n--- a/pkg/other.py\n+++ b/pkg/other.py\n@@ -1 +1 @@\n-a\n+b\n"


def _with_patch(turns, patch):
    ep = episode(turns)
    ep.artifacts = {"patch": patch}
    return ep


def _is_core_read(turn) -> bool:
    return json.loads(turn[0]["function"]["arguments"]).get("path") == "/ai-dlc/core-workflow.md"


def test_honest_run_with_its_patch_scores_one_on_the_rubric():
    s = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), PATCH), FILES)
    assert [s[f"aidlc/{k}"] for k in ("entry", "reports", "fidelity", "rubric")] == pytest.approx([1.0] * 4)


@pytest.mark.parametrize(("where", "entry"), [("never", 0.0), ("after_stage_docs", 0.0), ("first_but_late", 1 / 3)])
def test_entry_scores_when_core_workflow_was_read(where, entry):
    """order_v6 sees only the stage documents, so skipping core-workflow.md, reading it after a stage
    document, or reading it first but after other work costs aidlc/entry and nothing else."""
    honest = _content_honest_turns()
    core = [t for t in honest if _is_core_read(t)]
    turns = [t for t in honest if not _is_core_read(t)]
    if where == "after_stage_docs":
        turns = turns[:-1] + core + turns[-1:]
    elif where == "first_but_late":  # three repository looks, then core-workflow.md at step 4
        looks = [(_call(800 + i, "terminal", command=f"ls /testbed/pkg{i}"), "") for i in range(3)]
        turns = looks + core + turns
    s = score(SimpleNamespace(id="t"), _with_patch(turns, PATCH), FILES)
    assert s["aidlc/entry"] == pytest.approx(entry)
    assert s["aidlc/compliance"] == pytest.approx(1.0) and s["aidlc/rubric"] == pytest.approx(1 - 3 * (1 - entry) / 100)


def test_fidelity_is_the_disclosed_share_of_the_diff():
    both = PATCH + PATCH_OTHER  # stage 4 names pkg/mod.py only
    s = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), both), FILES)
    assert s["aidlc/fidelity"] == pytest.approx(0.5)
    empty = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), ""), FILES)
    assert empty["aidlc/fidelity"] == 0.0  # no change at all: nothing disclosed


def test_an_episode_without_a_recorded_patch_gets_no_fidelity():
    s = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
    assert "aidlc/fidelity" not in s and "aidlc/rubric" not in s
    assert s["aidlc/entry"] == 1.0 and s["aidlc/reports"] == pytest.approx(1.0)


def test_the_patch_moves_no_compliance_signal():
    without = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
    with_patch = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), PATCH + PATCH_OTHER), FILES)
    keys = ["aidlc/compliance", "aidlc/order", *(f"aidlc/s{k}" for k in range(1, 6)), "aidlc/entry", "aidlc/reports"]
    assert {k: with_patch[k] for k in keys} == {k: without[k] for k in keys}


def test_the_patch_matching_the_trajectory_keeps_every_check():
    s = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), PATCH), FILES)
    checks = {k: v for k, v in s.items() if k.startswith("aidlc/check/")}
    assert len(checks) == 35 and set(checks.values()) == {1.0}


def test_final_changes_are_read_from_the_patch():
    """pkg/other.py is in the patch but no trajectory write shows it (a python script, say): it is an
    undisclosed change, and since its edit time is unknown the checks timed by edits are left out."""
    s = score(SimpleNamespace(id="t"), _with_patch(_content_honest_turns(), PATCH + PATCH_OTHER), FILES)
    assert s["aidlc/check/e4_undisclosed"] == 0.5 and s["aidlc/check/e5_final_files_diff"] == 0.5
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.claims import TIMED_BY_EDITS

    assert not any(f"aidlc/check/{k}" in s for k in TIMED_BY_EDITS)


def test_a_change_put_back_is_not_a_final_change():
    """Edited in the trajectory, absent from the patch: reverted (``git checkout -- f``), not changed."""
    turns = _content_honest_turns()
    turns.insert(-2, (_call(700, "file_editor", command="str_replace", path="/testbed/pkg/util.py", old_str="a", new_str="b"), "The file has been edited"))
    s = score(SimpleNamespace(id="t"), _with_patch(turns, PATCH), FILES)
    assert s["aidlc/check/e4_undisclosed"] == 1.0 and s["aidlc/check/e5_final_files_diff"] == 1.0


# --- the evaluation verifier's own evidence readings (evidence.py) ----------------------------


def _replace_command(turns, old, new, obs=None):
    out = []
    for call, o in turns:
        a = json.loads(call["function"]["arguments"])
        if old in a.get("command", ""):
            a["command"] = a["command"].replace(old, new)
            call = {**call, "function": {**call["function"], "arguments": json.dumps(a)}}
            o = o if obs is None else obs
        out.append((call, o))
    return out


@pytest.mark.parametrize(
    ("command", "test_run"),
    [
        ("cd /testbed && python -m pytest tests/test_mod.py -q", True),
        ("cd /testbed/tests && python runtests.py queries.test_qs 2>&1 | head -50", True),
        ("cd /testbed && DJANGO_SETTINGS_MODULE=x python manage.py test app", True),
        ("cat /testbed/tox.ini", False),
        ("grep -n settings /testbed/tests/runtests.py | head -20", False),
        ("head -50 /testbed/tests/runtests.py", False),
        ("echo 'pytest tests/test_mod.py'", False),
        ("bash /tmp/pytest.sh", False),  # the agent wrote it (agent_files below)
    ],
)
def test_what_counts_as_a_test_run(command, test_run):
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import read as EV

    assert EV.is_test_attempt(command, agent_files=["/tmp/pytest.sh"]) is test_run


@pytest.mark.parametrize(
    ("command", "runs"),
    [
        ("python /tmp/repro.py", True),
        ("cd /testbed && timeout 60 python /tmp/repro.py 2>&1 | tail -5", True),
        ("/tmp/repro.py", True),
        ("cat > /tmp/repro.py <<'EOF'\nprint(1)\nEOF\npython /tmp/repro.py", True),
        ("python -c 'import repro'", True),
        ("ls -la /tmp/repro.py", False),
        ("cat /tmp/repro.py", False),
        ("ls -la /tmp/repro.py && echo found", False),
    ],
)
def test_what_counts_as_running_the_script(command, runs):
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import read as EV

    assert EV.runs_script(command, "/tmp/repro.py") is runs


def test_django_runner_passes_the_stage_gate():
    turns = _replace_command(_content_honest_turns(), "python -m pytest tests/test_mod.py -q", "cd tests && python runtests.py pkg.test_mod")
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/ran_real_test"] == 1.0 and s["aidlc/s1"] == 1.0 and s["aidlc/s5"] == 1.0


def test_a_lookup_naming_a_runner_is_not_a_test_run():
    turns = _replace_command(_content_honest_turns(), "cd /testbed && python -m pytest tests/test_mod.py -q", "cat /testbed/tox.ini", obs="[tox]\nenvlist = py3")
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/ran_real_test"] == 0.0 and s["aidlc/s1"] == pytest.approx(4 / 7)
    assert s["aidlc/check/t1_baseline_before_write"] == 0.0


def test_a_runner_script_the_agent_wrote_is_not_a_test_run():
    turns = _replace_command(_content_honest_turns(), "cd /testbed && python -m pytest tests/test_mod.py -q", "bash /tmp/pytest.sh")
    turns.insert(1, (_call(701, "file_editor", command="create", path="/tmp/pytest.sh", file_text="echo '3 passed in 0.10s'"), "File created successfully"))
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/ran_real_test"] == 0.0


def test_listing_the_script_is_not_running_it():
    turns = _replace_command(_content_honest_turns(), "python /tmp/repro.py", "ls -la /tmp/repro.py", obs="-rw-r--r-- 1 root root 11 /tmp/repro.py\nexit code: 0")
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/check/t5_repro_run_after_last_edit"] == 0.0


def test_a_piped_exit_code_decides_nothing():
    turns = _replace_command(_content_honest_turns(), "python /tmp/repro.py", "python /tmp/repro.py 2>&1 | tail -5")
    s = score(SimpleNamespace(id="t"), episode(turns), FILES)
    assert s["aidlc/check/t5_repro_run_after_last_edit"] == 1.0 and "aidlc/check/e5_repro_result" not in s


def test_an_explained_none_is_held_to_the_evidence():
    """``- None - all tests pass.`` is a none claim; with the tests failing after the change it is false."""
    turns = _content_honest_turns()
    last = max(i for i, t in enumerate(turns) if "pytest" in json.loads(t[0]["function"]["arguments"]).get("command", ""))
    turns[last] = (turns[last][0], "1 failed, 2 passed in 0.10s")
    files = {**FILES, ART[5]: FILES[ART[5]].replace("## Outstanding Failures\n- none", "## Outstanding Failures\n- None - all tests pass.")}
    s = score(SimpleNamespace(id="t"), episode(turns), files)
    assert s["aidlc/check/e5_outstanding_none"] == 0.0


def test_a_requirement_about_python_none_is_a_requirement():
    """``R3: None input -> TypeError`` is a requirement, not ``none stated``: dropping it from the plan
    leaves it uncovered."""
    files = dict(FILES)
    files[ART[3]] = files[ART[3]].replace("### Step 1 [satisfies R1, R3]", "### Step 1 [satisfies R1]").replace("- R3: Step 1\n", "")
    s = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), files)
    assert s["aidlc/check/c23_requirements_covered"] == 0.5


def test_the_tasks_test_patch_names_test_files(tmp_path):
    """A test module the path pattern cannot tell from source (``pkg/regress_cases.py``) is a test file
    when the task's test_patch names it."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "config.json").write_text(json.dumps({"test_patch": "diff --git a/pkg/regress_cases.py b/pkg/regress_cases.py\n"}))
    turns = _content_honest_turns()
    turns.insert(-2, (_call(702, "file_editor", command="str_replace", path="/testbed/pkg/regress_cases.py", old_str="a", new_str="b"), "The file has been edited"))
    patch = PATCH + "diff --git a/pkg/regress_cases.py b/pkg/regress_cases.py\n--- a/pkg/regress_cases.py\n+++ b/pkg/regress_cases.py\n@@ -1 +1 @@\n-a\n+b\n"
    task = SimpleNamespace(id="t", metadata={"task_path": str(tmp_path)})
    assert score(task, _with_patch(turns, patch), FILES)["aidlc/check/e5_test_files_none"] == 0.0
    assert score(SimpleNamespace(id="t"), _with_patch(turns, patch), FILES)["aidlc/check/e5_test_files_none"] == 1.0


def test_an_artifact_the_sandbox_did_not_hold_makes_no_claims():
    """Written in the trajectory, gone from the sandbox with no ``rm`` the rubric reads: no claims, as
    the compliance signals see it (s5 = 0)."""
    files = {p: t for p, t in FILES.items() if p != ART[5]}
    s = score(SimpleNamespace(id="t"), episode(_content_honest_turns()), files)
    assert s["aidlc/s5"] == 0.0 and not any(k.startswith(("aidlc/check/e5_", "aidlc/check/t5_", "aidlc/check/c45_")) for k in s)


# --- evaluator wrapper -----------------------------------------------------------------------


def test_evaluator_adds_signals_and_leaves_the_verifier_output_alone():
    sb = _Sandbox(_collected(FILES))
    inner = _Verifier(sb)
    out = AidlcEvalComplianceEvaluator(inner, sb).evaluate(SimpleNamespace(id="t"), episode(_content_honest_turns()))
    assert inner.collected_before == 1  # artifacts read before the verifier ran
    assert (out.reward, out.is_correct, out.metadata) == (1.0, True, {"termination_reason": "verifier_timeout"})
    sig = {s.name: s.value for s in out.signals}
    assert sig["accuracy"] == 1.0 and sig["aidlc/compliance"] == pytest.approx(1.0) and sig["aidlc/content"] == pytest.approx(1.0)


def test_evaluator_falls_back_to_the_verifier_when_collection_fails():
    sb = _Sandbox(fail=True)
    out = AidlcEvalComplianceEvaluator(_Verifier(sb), sb).evaluate(SimpleNamespace(id="t"), episode(_content_honest_turns()))
    assert [s.name for s in out.signals] == ["accuracy"]


def test_evaluation_survives_pickling():
    """Training pickles the policy into the Ray actor; the unpickled one scores the same."""
    ev = pickle.loads(pickle.dumps(AidlcEvalEvaluation()))
    data = ev.from_outputs({**FILES, "/tmp/swe-bench-pro/notes.md": "x"})
    assert data == FILES
    assert ev.score(SimpleNamespace(id="t"), episode(_content_honest_turns()), data) == score(SimpleNamespace(id="t"), episode(_content_honest_turns()), FILES)
