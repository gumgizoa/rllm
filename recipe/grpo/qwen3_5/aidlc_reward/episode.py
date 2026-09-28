"""rLLM Episode (gateway traces) -> rubric ``Run``.

Plays the role the rubric's harbor front-end plays for ATIF files: numbered steps, each holding
the ``Action``s the agent took and what came back.

One LLM call is one step, as in harbor's openhands-sdk trajectories, so step numbers mean the
same thing to the rubric in both places. Each training ``Step`` carries the request messages
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

from .rubric.frontends import openhands
from .rubric.model import Run, Step


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
            if m.get("role") == "tool" and m.get("tool_call_id"):
                out.setdefault(m["tool_call_id"], _text(m.get("content")))
    return out


def episode_to_run(episode: Any, artifact_files: dict[str, str], instance_id: str = "") -> Run:
    """``artifact_files`` maps ``/tmp/swe-bench-pro/NN-*.md`` to the content read from the sandbox."""
    steps = _steps(episode)
    results = _tool_results(steps)
    run_steps: list[Step] = []
    for i, s in enumerate(steps, start=1):
        response = (s.chat_completions or [{}])[-1] or {}
        step = Step(i, message=_text(response.get("content")))
        for tc in response.get("tool_calls") or []:
            fn = tc.get("function") or {}
            step.actions.append(openhands.parse(fn.get("name") or "", _args(fn.get("arguments")), results.get(tc.get("id") or "", "")))
        run_steps.append(step)
    return Run(instance_id=instance_id, steps=run_steps, artifact_files=dict(artifact_files), meta={"api_calls": len(steps)})
