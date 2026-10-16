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


def episode_to_run(episode: Any, instance_id: str = "") -> Run:
    """The episode as a ``Run``; ``ValueError`` when no front end knows its harness."""
    parse = frontend_for(episode).parse
    steps = _steps(episode)
    results = _tool_results(steps)
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
    return Run(instance_id=instance_id, steps=run_steps, meta={"api_calls": len(steps)})
