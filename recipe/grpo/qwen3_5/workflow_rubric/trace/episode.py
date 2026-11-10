"""rLLM Episode (gateway traces) -> ``trace.model.Run``.

Ported from the AI-DLC rubric (``workflows/aidlc_v4/reward/episode.py``) so the generic engine reads
training episodes the same way, without importing a workflow package. It plays the role
``offline/harbor.py`` plays for ATIF files: numbered steps, each holding the ``Action``s the agent
took and what came back.

One LLM call is one step, as in harbor's openhands-sdk trajectories, so step numbers mean the
same thing to the engine in both places. Each training ``Step`` carries the request messages
plus the response message in ``chat_completions``:

* the step's tool calls are read off the **raw** response message (``chat_completions[-1]``),
  not ``Step.model_output.tool_calls``, because the parsed form drops the ``id`` that pairs a
  call with its result;
* a call's observation is the ``role: "tool"`` message with the same ``tool_call_id``, which
  appears in the request of a *later* call. Results are collected across every step's request
  rather than read off the last one, so a condensed history still yields the recent results.
  The final call's results were never sent back to the model, so they stay empty -- that call
  is almost always ``finish``.

Message bodies may be a content-part list (``[{"type": "text", "text": ...}]``) -- openhands-sdk
sends every body that way -- and are flattened with ``"\\n"`` as the gateway does.

Sub-agents (openhands-tools ``task`` tool): the gateway captures a sub-agent's LLM calls as steps of the
same episode, interleaved with the parent's. A step belongs to the parent when its request carried the
``task`` tool (``Step.metadata["request_tools"]``, ``trace_converter.REQUEST_TOOLS_KEY``); the
general-purpose sub-agent has terminal, file_editor and task_tracker only. When any step carries it, the
``Run`` holds the parent's steps (renumbered) and ``Run.meta["subagent_runs"]`` the sub-agents' steps as
one ``Run`` per conversation, keyed by the conversation's first user message (the delegated prompt), in
order of first appearance. A run without the tool is unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from . import openhands
from .model import Run, Step

# Tool profiles, each naming the harnesses whose tool calls it parses (``NAMES``).
FRONTENDS = (openhands,)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def _args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"command": raw}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _steps(episode: Any) -> list[Any]:
    return [s for traj in episode.trajectories for s in traj.steps]


def _tool_results(steps: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in steps:
        for m in (s.chat_completions or [])[:-1]:
            if isinstance(m, dict) and m.get("role") == "tool" and m.get("tool_call_id"):
                out.setdefault(m["tool_call_id"], _text(m.get("content")))
    return out


def frontend_for(episode: Any):
    """The tool profile for the harness that produced ``episode``, by its trajectories' ``name``.

    A tool call means something only to its own harness's profile (openhands' ``terminal`` /
    ``file_editor`` are not another agent's tools), so a harness without one is an error -- the
    scorer logs it and leaves the verifier's output alone -- never a score from the wrong parser.
    """
    names = {getattr(t, "name", None) for t in episode.trajectories}
    for frontend in FRONTENDS:
        if names & frontend.NAMES:
            return frontend
    known = sorted(n for frontend in FRONTENDS for n in frontend.NAMES)
    raise ValueError(f"no rubric front end for harness {sorted(map(str, names))}; known: {known}")


SUBAGENT_TOOL = "task"
REQUEST_TOOLS_KEY = "request_tools"


def _request_tool_names(step: Any) -> set[str]:
    md = getattr(step, "metadata", None) or {}
    tools = md.get(REQUEST_TOOLS_KEY) if isinstance(md, dict) else None
    out = set()
    for t in tools or []:
        if isinstance(t, dict):
            name = (t.get("function") or {}).get("name") or t.get("name")
            if isinstance(name, str):
                out.add(name)
    return out


def _first_user_text(step: Any) -> str:
    for m in step.chat_completions or []:
        if isinstance(m, dict) and m.get("role") == "user":
            return _text(m.get("content"))
    return ""


def _convert(steps: list[Any], parse, results: dict[str, str]) -> list[Step]:
    run_steps: list[Step] = []
    for i, s in enumerate(steps, start=1):
        response = (s.chat_completions or [{}])[-1] or {}
        if not isinstance(response, dict):
            response = {}
        step = Step(i, message=_text(response.get("content")))
        for tc in response.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            step.actions.append(parse(fn.get("name") or "", _args(fn.get("arguments")), results.get(tc.get("id") or "", "")))
        run_steps.append(step)
    return run_steps


def split_subagents(steps: list[Any]) -> tuple[list[Any], list[tuple[str, list[Any]]]]:
    """(parent steps, [(conversation key, steps)]) -- or (all steps, []) when no step carried the sub-agent tool."""
    if not any(SUBAGENT_TOOL in _request_tool_names(s) for s in steps):
        return steps, []
    parent, subs = [], {}
    for s in steps:
        if SUBAGENT_TOOL in _request_tool_names(s):
            parent.append(s)
        else:
            subs.setdefault(_first_user_text(s), []).append(s)
    return parent, list(subs.items())


def episode_to_run(episode: Any, instance_id: str = "") -> Run:
    """The episode as a ``Run``; ``ValueError`` when no front end knows its harness."""
    parse = frontend_for(episode).parse
    steps = _steps(episode)
    results = _tool_results(steps)
    parent, subs = split_subagents(steps)
    meta: dict[str, Any] = {"api_calls": len(steps)}
    if subs:
        meta["subagent_steps"] = sum(len(ss) for _, ss in subs)
        meta["subagent_runs"] = [
            Run(instance_id=f"{instance_id}#sub{k}", steps=_convert(ss, parse, results), meta={"api_calls": len(ss), "prompt_head": key[:200]})
            for k, (key, ss) in enumerate(subs, start=1)
        ]
    return Run(instance_id=instance_id, steps=_convert(parent, parse, results), meta=meta)
