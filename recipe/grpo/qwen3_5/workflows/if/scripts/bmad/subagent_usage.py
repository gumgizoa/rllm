"""How the agent used the SDK's sub-agent tool (`task`) in a set of rllm episodes.

    python -I subagent_usage.py <episodes_dir_or_results.json> [more ...] [--per-episode]

Reads every episode_*.json under the given directories (the layout `rllm eval --episodes-dir` writes).
A step is a gateway-captured LLM call. Parent steps are those whose request carried the `task` tool
(`metadata.request_tools`); steps without it belong to sub-agent conversations (the general-purpose
sub-agent has terminal, file_editor, task_tracker only). Nothing here needs the SDK.

Per episode: parent steps, sub-agent steps, `task` calls (new / resume), calls whose observation reports an
error, distinct sub-agent types, whether the run solved the task and how it ended. Totals and the share of
episodes that never called `task` are printed at the end.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

TASK = "task"


def _tool_names(step: dict) -> set[str]:
    tools = (step.get("metadata") or {}).get("request_tools") or []
    return {t.get("function", {}).get("name") for t in tools if isinstance(t, dict)}


def _assistant_calls(step: dict) -> list[dict]:
    cc = step.get("chat_completions") or []
    if not cc:
        return []
    last = cc[-1]
    if last.get("role") != "assistant":
        return []
    return [c for c in (last.get("tool_calls") or []) if c.get("function", {}).get("name") == TASK]


def _tool_results(step: dict) -> list[str]:
    """Tool-role message texts in this step's prompt (the observations of the previous turn's calls)."""
    out = []
    for m in step.get("chat_completions") or []:
        if m.get("role") == "tool":
            c = m.get("content")
            out.append(c if isinstance(c, str) else json.dumps(c))
    return out


def analyse(ep: dict) -> dict:
    traj = (ep.get("trajectories") or [{}])[0]
    steps = traj.get("steps") or []
    parent = [s for s in steps if TASK in _tool_names(s)]
    sub = [s for s in steps if TASK not in _tool_names(s)]
    if not parent:  # a run without the tool at all: every step is the parent's
        parent, sub = steps, []
    calls, resumes, types, bad_args = 0, 0, collections.Counter(), 0
    for s in parent:
        for c in _assistant_calls(s):
            calls += 1
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                bad_args += 1
                continue
            if args.get("resume"):
                resumes += 1
            types[args.get("subagent_type", "general-purpose")] += 1
    errors = 0
    seen: set[str] = set()
    for s in parent:
        for text in _tool_results(s):
            if text in seen or "Task ID:" not in text:
                continue
            seen.add(text)
            if "Status: error" in text or "Failed to execute task" in text or "Status: ERROR" in text:
                errors += 1
    return {
        "id": ep.get("id"),
        "solved": bool(ep.get("is_correct")),
        "ended": ep.get("termination_reason"),
        "steps": len(steps),
        "parent_steps": len(parent),
        "sub_steps": len(sub),
        "task_calls": calls,
        "resume_calls": resumes,
        "bad_json_args": bad_args,
        "task_errors": errors,
        "types": dict(types),
    }


def main(argv: list[str]) -> int:
    per_episode = "--per-episode" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")]
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("episode_*.json")) if p.is_dir() else [p])
    rows = [analyse(json.load(open(f))) for f in files]
    if not rows:
        print("no episodes found", file=sys.stderr)
        return 1
    if per_episode:
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
    n = len(rows)
    used = [r for r in rows if r["task_calls"]]
    tot = lambda k: sum(r[k] for r in rows)  # noqa: E731
    print(f"episodes {n}; used `task` in {len(used)} ({100*len(used)/n:.0f}%); solved {sum(r['solved'] for r in rows)}")
    print(f"task calls {tot('task_calls')} (resume {tot('resume_calls')}, bad json {tot('bad_json_args')}, errors {tot('task_errors')})")
    print(f"steps parent {tot('parent_steps')} / sub-agent {tot('sub_steps')}; mean per episode {tot('parent_steps')/n:.1f} / {tot('sub_steps')/n:.1f}")
    types = collections.Counter()
    for r in rows:
        types.update(r["types"])
    print("sub-agent types:", dict(types))
    ends = collections.Counter(r["ended"] for r in rows)
    print("endings:", dict(ends))
    if used:
        print(f"calls per using episode: median {sorted(r['task_calls'] for r in used)[len(used)//2]}, max {max(r['task_calls'] for r in used)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
