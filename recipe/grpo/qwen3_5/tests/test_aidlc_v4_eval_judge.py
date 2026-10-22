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
from test_aidlc_v4_eval_hacks import Run, sh  # noqa: E402

from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward import judge as J  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.content_checks import parsed_artifacts  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.episode import episode_to_run  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.evaluator import score  # noqa: E402

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
        1: ["D1a", "D1b", "D3", "D6"],
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


def test_a_verdict_stands_only_on_a_quote_from_the_material(judge_on, monkeypatch):
    special = {
        "E6b": ("no", "## Functional Requirements"),
        "D3": ("yes", "Owning module: the whole repository"),  # not in the material
        "E8b": ("n/a", ""),
    }
    monkeypatch.setattr(J, "ask", lambda text, seed=None: _reply(text, special))
    s = Run().score()
    assert s["aidlc/judge/D1a"] == 1.0 and s["aidlc/judge/E6b"] == 0.0
    assert "aidlc/judge/D3" not in s and "aidlc/judge/E8b" not in s
    assert s["aidlc/judge_calls"] == 5.0
    assert s["aidlc/judge_void"] == pytest.approx(1 / 19)  # 20 asked, one n/a, one quote not found
    assert s["aidlc/cat/Q2"] < 1.0 and s["aidlc/cat/Q3"] == 1.0


@pytest.mark.parametrize("reply", ["no JSON here", '{"answers": "yes"}', '{"answers": [{"id": "D1a", "answer": "maybe", "quote": "Files: pkg/mod.py"}]}'])
def test_a_malformed_reply_judges_nothing(judge_on, monkeypatch, reply):
    monkeypatch.setattr(J, "ask", lambda text, seed=None: reply)
    s = Run().score()
    assert not [k for k in s if k.startswith("aidlc/judge/")] and "aidlc/judge_void" not in s


def test_a_failed_call_leaves_its_stage_unjudged(judge_on, monkeypatch):
    def ask(text, seed=None):
        if "stage 2 artifact" in text:
            raise TimeoutError("judge down")
        return _reply(text)

    monkeypatch.setattr(J, "ask", ask)
    s = Run().score()
    assert "aidlc/judge/E1a" not in s and s["aidlc/judge/D1a"] == 1.0


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
    J.ask("q", seed=1)  # another sample is another request
    assert len(calls) == 2


def test_every_question_has_a_category():
    from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.categories import JUDGE_KINDS

    assert {r for qs in J.QUESTIONS.values() for r, _ in qs} == set(JUDGE_KINDS)


def test_the_issue_is_material_for_stages_1_to_3(judge_on, monkeypatch):
    """The issue is material for stages 1-3 only; stage 4 and 5 are judged against the artifacts and extracts."""
    seen = {}
    monkeypatch.setattr(J, "ask", lambda text, seed=None: seen.setdefault(int(re.search(r"stage (\d)", text).group(1)), text) and _reply(text))
    from types import SimpleNamespace

    score(SimpleNamespace(id="t", metadata={"instruction": "ISSUE-TEXT-MARK parse() fails"}), episode(Run().turns), Run().files)
    assert all(("ISSUE-TEXT-MARK" in seen[st]) == (st <= 3) for st in seen)
