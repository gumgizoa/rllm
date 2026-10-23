"""aidlc_v4_eval's LLM judge (``reward/judge.py``) with the model faked: which questions are asked, how a
reply becomes verdicts, what a quote that is not in the material does, and the plumbing (cache, failures).

    uv run --no-sync --with pytest python -m pytest -q recipe/grpo/qwen3_5/tests/test_aidlc_v4_eval_judge.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_aidlc_reward import episode  # noqa: E402
from test_aidlc_v4_eval import score  # noqa: E402
from test_aidlc_v4_eval_hacks import Run, sh, write  # noqa: E402

from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import judge as J  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.read import parsed_artifacts  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.trace import episode_to_run  # noqa: E402

# a line of each stage's artifact, to quote
QUOTE = {1: "Files: pkg/mod.py", 2: "R1: parse() accepts an empty string", 3: "Target: pkg/mod.py (modify in place)", 4: "Modified: pkg/mod.py [R1, R3]", 5: "Result: pass"}


@pytest.fixture
def judge_on(monkeypatch):
    monkeypatch.setenv("AIDLC_JUDGE_BASE_URL", "http://judge.invalid/v1")
    monkeypatch.setenv("AIDLC_JUDGE_MODEL", "fake")
    monkeypatch.delenv("AIDLC_JUDGE_CACHE", raising=False)


def _reply(text: str, special: dict[str, tuple[str, str]] | None = None) -> str:
    """Every asked id answered yes with a quote from its stage's artifact, unless ``special`` says otherwise."""
    stage = int(re.search(r"stage (\d) artifact", text).group(1))
    ids = re.findall(r"^- (\w+): ", text.split("=== QUESTIONS", 1)[1], re.M)
    special = special or {}
    return json.dumps({"answers": [{"id": i, "answer": special.get(i, ("yes", QUOTE[stage]))[0], "quote": special.get(i, ("yes", QUOTE[stage]))[1], "reason": "r"} for i in ids]})


def _requests(r: Run):
    run = episode_to_run(episode(r.turns), r.files)
    return J.stage_requests(run, parsed_artifacts(run, collected=True), r.patch, None)


def test_no_judge_signals_without_a_model(monkeypatch):
    monkeypatch.delenv("AIDLC_JUDGE_MODEL", raising=False)
    assert not [k for k in Run().score() if k.startswith("aidlc/judge")]


def test_the_questions_follow_what_the_artifacts_hold():
    asked = {st: [r for r, _ in qs] for st, (qs, _) in _requests(Run()).items()}
    # no test file read (D10b), non-functional none (E7a, E7b, H3c), no deviations (G8a, G8c), no
    # pre-existing failures (H8d), no fixes (H9b): not asked
    assert asked == {
        1: ["D3", "D6"],
        2: ["E1a", "E1b", "E3b", "E6a", "E6b", "E8a", "E8b", "E9"],
        3: ["F2d", "F2e", "F4a", "F9a"],
        4: ["G5", "B4b"],
        5: ["H3a", "H3b"],
    }


def test_material_holds_the_script_and_the_test_code_the_run_read():
    r = Run()
    r.insert(r.write_of(1), sh("cat /testbed/tests/test_mod.py", "def test_parse():\n    assert parse('a=1') == {'a': '1'}"))
    r.insert(r.write_of(5), sh("rm /tmp/repro.py", ""))  # the cleanup the workflow asks for keeps the text
    req = _requests(r)
    assert "D10b" in [q for q, _ in req[1][0]] and "parse('a=1')" in req[1][1]["EXISTING TEST CODE THE AGENT READ"]
    assert req[5][1]["REPRODUCTION SCRIPT"] == "import pkg\n"
    assert set(req[4][1]) == {"ARTIFACT 03", "ARTIFACT 04", "FINAL PATCH"}  # the plan, its execution and the patch


def test_the_baseline_tests_code_is_gathered_from_every_read():
    """swebv100-step24 000362: the run grepped the baseline tests and sed-read another; the judge got the sed
    excerpt only. Every read counts now, and only the baseline tests' code is shown."""
    r = Run()
    grep = "12:def test_parse():\n13:    assert parse('a=1') == {'a': '1'}\n19:    assert parse('') == {}\n[The command completed with exit code 0.]"
    sed = "def test_other():\n    assert other() is None\n"
    r.insert(r.write_of(1), sh("grep -n parse /testbed/tests/test_mod.py", grep), sh("sed -n '40,41p' /testbed/tests/test_mod.py", sed))
    text = _requests(r)[1][1]["EXISTING TEST CODE THE AGENT READ"]
    assert text == "def test_parse():\n    assert parse('a=1') == {'a': '1'}\n    ...\n    assert parse('') == {}"


def test_a_baseline_test_never_read_is_named_and_none_read_is_not_asked():
    r = Run()
    r.edit(1, "- Passing: tests/test_mod.py::test_parse", "- Passing: tests/test_mod.py::test_parse\n  tests/test_mod.py::test_empty")
    r.insert(r.write_of(1), sh("cat -n /testbed/tests/test_mod.py", "     1\tdef test_parse():\n     2\t    assert parse('') == {}"))
    assert _requests(r)[1][1]["EXISTING TEST CODE THE AGENT READ"].endswith("(not read by the run: test_empty)")
    r = Run()
    r.insert(r.write_of(1), sh("cat /testbed/tests/test_mod.py", "def test_unrelated():\n    pass"))
    assert "D10b" not in [q for q, _ in _requests(r)[1][0]]


def test_the_reproduction_script_shown_is_the_one_that_ran():
    r = Run()
    r.insert(r.write_of(5), write("/tmp/repro.py", "import pkg  # rewritten after the run\n"))
    assert _requests(r)[5][1]["REPRODUCTION SCRIPT"] == "import pkg\n"


def test_a_pre_existing_failure_comes_with_the_last_stage_5_test_output():
    r = Run()
    r.edit(5, "- Pre-existing failures: none", "- Pre-existing failures: test_old -> fails at baseline -> unrelated")
    r.set_obs(r.runs("pytest")[1], "\x1b[31m1 failed\x1b[0m, 2 passed in 0.10s\n[Command finished with exit code 1]")
    qs, mat = _requests(r)[5]
    assert "H8d" in [q for q, _ in qs]
    assert mat["STAGE 5 TEST RUN (the last one, output tail)"] == "$ cd /testbed && python -m pytest tests/test_mod.py -q\n1 failed, 2 passed in 0.10s"


def test_a_verdict_stands_only_on_a_quote_from_the_material(judge_on, monkeypatch):
    special = {
        "E6b": ("no", "## Functional Requirements"),
        "D3": ("yes", "Owning module: the whole repository"),  # not in the material
        "E8b": ("n/a", ""),
    }
    monkeypatch.setattr(J, "ask", lambda text, seed=None: _reply(text, special))
    s = Run().score()
    assert s["aidlc/judge/D6"] == 1.0 and s["aidlc/judge/E6b"] == 0.0
    assert "aidlc/judge/D3" not in s and "aidlc/judge/E8b" not in s
    assert s["aidlc/judge_calls"] == 5.0
    assert s["aidlc/judge_void"] == pytest.approx(1 / 17)  # 18 asked, one n/a, one quote not found
    assert s["aidlc/cat/Q2"] < 1.0 and s["aidlc/cat/Q3"] == 1.0


@pytest.mark.parametrize(
    ("quote", "found"),
    [
        ("Deviations from Plan: none", True),  # a heading joined to its item
        ("R6: Q objects keep kwargs R7: other objects use args", True),  # two list items in one quote
        ("R6: Q objects ... use args", True),  # an ellipsis
        ("Step 1 Verification: repro calls parse", True),  # where it quotes from, then the field
        ("assert parse('') == {}\\nassert parse(None)", True),  # code lines, one skipped, newline written out
        ("Owning module: the whole repository", False),  # words the material does not have
        ("none", False),  # too short to rest on
    ],
)
def test_a_quote_is_the_materials_words_in_order(quote, found):
    material = [
        "## Deviations from Plan\n- none",
        "- R6: Q objects keep kwargs\n- R7: other objects use args",
        "### Step 1 [satisfies R1]\n- Verification: repro calls parse",
        "assert parse('') == {}\nx = 1\nassert parse(None)",
    ]
    shown = J._norm("\n".join(material))
    assert J.quote_found(quote, shown) is found


@pytest.mark.parametrize("reply", ["no JSON here", '{"answers": "yes"}', '{"answers": [{"id": "D3", "answer": "maybe", "quote": "Files: pkg/mod.py"}]}'])
def test_a_malformed_reply_judges_nothing(judge_on, monkeypatch, reply):
    monkeypatch.setattr(J, "ask", lambda text, seed=None: reply)
    s = Run().score()
    assert not [k for k in s if k.startswith("aidlc/judge/")] and "aidlc/judge_void" not in s


def test_a_reply_broken_after_its_answers_keeps_them(judge_on, monkeypatch):
    """Nemotron once left a reason unquoted: the id / answer / quote triples before it still count."""

    def ask(text, seed=None):
        good = json.loads(_reply(text))["answers"]
        return '{"answers": [' + ", ".join(f'{{"id": "{a["id"]}", "answer": "{a["answer"]}", "quote": {json.dumps(a["quote"])}, "reason": unquoted text}}' for a in good) + "]}"

    monkeypatch.setattr(J, "ask", ask)
    s = Run().score()
    assert s["aidlc/judge/D3"] == 1.0 and s["aidlc/judge/H3a"] == 1.0


def test_a_failed_call_leaves_its_stage_unjudged(judge_on, monkeypatch):
    def ask(text, seed=None):
        if "stage 2 artifact" in text:
            raise TimeoutError("judge down")
        return _reply(text)

    monkeypatch.setattr(J, "ask", ask)
    s = Run().score()
    assert "aidlc/judge/E1a" not in s and s["aidlc/judge/D3"] == 1.0


def test_the_cache_asks_once(judge_on, monkeypatch, tmp_path):
    import httpx

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"answers": []}'}}]}

    monkeypatch.setenv("AIDLC_JUDGE_CACHE", str(tmp_path))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: calls.append(k["json"]) or Response())
    assert J.ask("q") == J.ask("q") == '{"answers": []}'
    assert len(calls) == 1 and calls[0]["model"] == "fake" and calls[0]["messages"][0]["content"] == J.SYSTEM
    assert calls[0]["response_format"] == {"type": "json_object"}
    J.ask("q", seed=1)  # another sample is another request
    assert len(calls) == 2


def test_every_question_has_a_category():
    from test_aidlc_v4_eval import _EVAL

    judged = {i.check.params["question"] for i in _EVAL.rubric.items if i.check.kind == "aidlc_v4_eval.judge"}
    assert {r for qs in J.QUESTIONS.values() for r, _ in qs} == judged


def test_the_issue_is_material_for_stages_1_to_3(judge_on, monkeypatch):
    """The issue is material for stages 1-3 only; stage 4 and 5 are judged against the artifacts and extracts."""
    seen = {}
    monkeypatch.setattr(J, "ask", lambda text, seed=None: seen.setdefault(int(re.search(r"stage (\d)", text).group(1)), text) and _reply(text))
    from types import SimpleNamespace

    score(SimpleNamespace(id="t", metadata={"instruction": "ISSUE-TEXT-MARK parse() fails"}), episode(Run().turns), Run().files)
    assert all(("ISSUE-TEXT-MARK" in seen[st]) == (st <= 3) for st in seen)
