"""Sub-agent conversations in a gateway episode (openhands-tools ``task`` tool) are split off the parent run.

A step whose request carried the ``task`` tool is the parent's; the others are sub-agent steps, grouped by
the conversation's first user message. An episode without the tool converts exactly as before.
"""

from __future__ import annotations

from types import SimpleNamespace

from recipe.grpo.qwen3_5.workflow_rubric.trace import episode as E


def _step(tools, user, tool_calls=(), results=()):
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": [{"type": "text", "text": user}]}]
    for cid, text in results:
        msgs.append({"role": "tool", "tool_call_id": cid, "content": text})
    msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": cid, "function": {"name": n, "arguments": a}} for cid, n, a in tool_calls]})
    return SimpleNamespace(chat_completions=msgs, metadata={"request_tools": [{"function": {"name": t}} for t in tools]})


PARENT = ("terminal", "file_editor", "task_tracker", "task", "finish")
CHILD = ("terminal", "file_editor", "task_tracker", "finish")


def _episode(steps):
    return SimpleNamespace(trajectories=[SimpleNamespace(name="openhands-sdk", steps=steps)])


def test_parent_keeps_its_steps_and_subagents_go_to_meta():
    steps = [
        _step(PARENT, "issue", [("c1", "task", '{"prompt": "implement it", "subagent_type": "general-purpose"}')]),
        _step(CHILD, "implement it", [("s1", "terminal", '{"command": "ls"}')]),
        _step(CHILD, "implement it", [("s2", "file_editor", '{"command": "view", "path": "/testbed/a.py"}')], [("s1", "a.py")]),
        _step(PARENT, "issue", [("c2", "task", '{"prompt": "review it", "resume": "task_00000001"}')], [("c1", "Task ID: task_00000001\nStatus: completed\ndone")]),
        _step(CHILD, "review it", [("r1", "terminal", '{"command": "cat diff"}')]),
    ]
    run = E.episode_to_run(_episode(steps), "t")
    assert [s.n for s in run.steps] == [1, 2]
    assert run.meta["api_calls"] == 5 and run.meta["subagent_steps"] == 3
    task = run.steps[0].actions[0]
    assert task.name == "task" and task.text == "implement it" and task.path == "general-purpose" and task.old == ""
    assert "task_00000001" in task.observation
    assert run.steps[1].actions[0].old == "task_00000001"
    subs = run.meta["subagent_runs"]
    assert [r.meta["prompt_head"] for r in subs] == ["implement it", "review it"]
    assert [len(r.steps) for r in subs] == [2, 1]
    assert subs[0].steps[1].actions[0].kind == "view"


def test_without_the_tool_nothing_changes():
    steps = [_step(CHILD, "issue", [("c1", "terminal", '{"command": "ls"}')]), _step(CHILD, "issue", [("c2", "finish", "{}")], [("c1", "ok")])]
    run = E.episode_to_run(_episode(steps), "t")
    assert [s.n for s in run.steps] == [1, 2] and "subagent_runs" not in run.meta and run.meta["api_calls"] == 2
