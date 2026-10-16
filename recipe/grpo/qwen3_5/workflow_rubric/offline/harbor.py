"""harbor trials (ATIF-v1.5 ``agent/trajectory.json``) -> ``trace.model.Run``, and a ``Collected`` rebuilt from the replay.

Offline only: comparison and regression runs over finished harbor jobs (e.g. the AI-DLC v4 runs in
``harbor-extension-aidlc/jobs``); nothing at reward time imports this. It is self-contained -- no
evalv1 import -- so the same engine scores a harbor trial and a training episode from the same
``Run`` shape.

Trial layout read here: ``agent/trajectory.json`` (``steps[]`` with ``source`` system|user|agent;
agent steps carry ``tool_calls[{tool_call_id, function_name, arguments}]`` and
``observation.results[{source_call_id, content}]``), ``verifier/reward.txt`` (1/0) and
``result.json`` (``task_name``, ``exception_info``).

Parity with training (``trace/episode.py``): one agent step is one LLM call, and the final call's
tool results were never sent back to the model, so the observations of the LAST agent step's tool
calls are blanked here too -- harbor recorded them, training never sees them. A trailing step
without tool calls (a plain reply) blanks nothing: the previous call's results did reach the model.

Runs without an ``artifacts:`` job entry keep no files (the container is deleted and
``/logs/artifacts`` is empty), so :func:`collected_from_replay` stands in for ``collect.py``: the
final replayed content of every path under the rubric roots, with ``mode="offline"``. A job that
listed the artifact roots under ``artifacts:`` (harbor copies them to ``<trial>/artifacts/<abs path>``
after the agent, before the verifier) is read by :func:`collected_from_artifacts` instead: the real
files for those roots, the replay for the rest.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..context import Collected
from ..replay import replay
from ..trace import openhands
from ..trace.model import Run, Step

if TYPE_CHECKING:
    from ..schema import Rubric

AGENTS = {name: mod for mod in (openhands,) for name in mod.NAMES}

# Mirrors collect.py's online limits, so an offline Collected never holds more than an online one could.
MAX_FILES = 500
MAX_BYTES = 256 * 1024


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


def _observation(step: dict, call_id: Any, n_calls: int) -> str:
    results = [r for r in ((step.get("observation") or {}).get("results") or []) if isinstance(r, dict)]
    for r in results:
        if call_id is not None and r.get("source_call_id") == call_id:
            return _text(r.get("content"))
    if n_calls == 1 and not any(r.get("source_call_id") for r in results):
        return "\n".join(_text(r.get("content")) for r in results)
    return ""


def _read_json(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _reward(trial_dir: Path) -> float | None:
    try:
        return float((trial_dir / "verifier" / "reward.txt").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def iter_trials(job_dir: Path) -> Iterator[Path]:
    """Trial directories (``<task>__<suffix>/`` holding ``agent/trajectory.json``) under a harbor job or run dir."""
    job_dir = Path(job_dir)
    for p in sorted(job_dir.rglob("agent/trajectory.json")):
        yield p.parent.parent


def load_trial(trial_dir: Path) -> tuple[Run, dict]:
    """(Run, meta) of one trial; meta = {instance_id, resolved, reward, exception, n_steps, agent}.

    Raises ``OSError`` without a trajectory and ``ValueError`` for an unreadable one or an agent
    without a tool profile (infra errors: a silent fallback would score every trial 0).
    """
    trial_dir = Path(trial_dir)
    traj = json.loads((trial_dir / "agent" / "trajectory.json").read_text(encoding="utf-8"))
    if not isinstance(traj, dict):
        raise ValueError(f"{trial_dir}: trajectory is not an object")
    agent = (traj.get("agent") or {}).get("name") or ""
    frontend = AGENTS.get(agent)
    if frontend is None:
        raise ValueError(f"{trial_dir}: no tool profile for agent {agent!r}; known: {sorted(AGENTS)}")
    agent_steps = [s for s in traj.get("steps") or [] if isinstance(s, dict) and s.get("source") == "agent"]
    steps: list[Step] = []
    for n, s in enumerate(agent_steps, start=1):
        step = Step(n, message=_text(s.get("message")))
        calls = [tc for tc in s.get("tool_calls") or [] if isinstance(tc, dict)]
        for tc in calls:
            obs = "" if n == len(agent_steps) else _observation(s, tc.get("tool_call_id"), len(calls))
            step.actions.append(frontend.parse(tc.get("function_name") or "", _args(tc.get("arguments")), obs))
        steps.append(step)
    result = _read_json(trial_dir / "result.json")
    exc = result.get("exception_info") or {}
    reward = _reward(trial_dir)
    meta = {
        "instance_id": result.get("task_name") or trial_dir.name.rsplit("__", 1)[0],
        "resolved": None if reward is None else reward >= 1.0,
        "reward": reward,
        "exception": exc.get("exception_type") if isinstance(exc, dict) else None,
        "n_steps": len(steps),
        "agent": agent,
    }
    run = Run(instance_id=meta["instance_id"], steps=steps, meta={**meta, "api_calls": len(steps), "trial": trial_dir.name})
    return run, meta


# --------------------------------------------------------------------------------------------
# Collected from the replay
# --------------------------------------------------------------------------------------------
_TEMPLATE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _roots(rubric: Rubric, workdir: str) -> dict[str, str]:
    raw = dict(rubric.roots)
    raw.setdefault("code", workdir)
    out: dict[str, str] = {}

    def expand(name: str, seen: frozenset[str]) -> str:
        if name in out:
            return out[name]
        v = raw.get(name, "")

        def sub(m: re.Match) -> str:
            key = m.group(1)
            if key in ("WORKDIR", "workdir"):
                return workdir
            if key in raw and key not in seen:
                return expand(key, seen | {key})
            return m.group(0)

        return posixpath.normpath(_TEMPLATE.sub(sub, v)) if v else ""

    for name in raw:
        out[name] = expand(name, frozenset({name}))
    return {k: v for k, v in out.items() if v.startswith("/")}


def _location_rx(template: str, roots: dict[str, str], workdir: str) -> re.Pattern | None:
    parts: list[str] = []
    pos = 0
    for m in _TEMPLATE.finditer(template):
        parts.append(re.escape(template[pos : m.start()]))
        key = m.group(1)
        if key in roots:
            parts.append(re.escape(roots[key]))
        elif key in ("WORKDIR", "workdir"):
            parts.append(re.escape(workdir))
        elif key == "DATE":
            parts.append(r"\d{4}-\d{2}-\d{2}")
        else:
            parts.append(r"[^/]+")
        pos = m.end()
    parts.append(re.escape(template[pos:]))
    try:
        return re.compile("".join(parts).rstrip("/") + r"(?:/.*)?")
    except re.error:
        return None


def collected_from_replay(run: Run, rubric: Rubric, workdir: str = "/testbed", initial: Mapping[str, str] | None = None) -> Collected:
    """What ``collect.py`` would have read, rebuilt from the trace (``mode="offline"``).

    files: final replayed content of every path under a rubric root that exists at the end; a path
    whose final content could not be replayed is absent. Under the code root only artifact locations
    count (online collection does not read the repository wholesale either). dirs: parents of those
    files up to their root, plus directories the run made under a root. No diff, no base tree.
    ``initial``: files the sandbox held before the run (e.g. a workflow's templates under an artifact root).
    """
    rep = replay(run, workdir, initial=initial)
    roots = _roots(rubric, workdir)
    code_roots = {v for k, v in roots.items() if k == "code" or v == workdir}
    locs = [rx for a in rubric.artifacts.values() for t in a.locations if (rx := _location_rx(t, roots, workdir)) is not None]

    def root_of(path: str) -> list[str]:
        return [r for r in roots.values() if path == r or path.startswith(r.rstrip("/") + "/")]

    files: dict[str, str] = {}
    truncated: set[str] = set()
    for path in sorted(rep.final):
        content = rep.final[path]
        if content is None or "/.git/" in path:
            continue
        under = root_of(path)
        if not under:
            continue
        if all(r in code_roots for r in under) and not any(rx.fullmatch(path) for rx in locs):
            continue
        if len(files) >= MAX_FILES:
            break
        data = content.encode("utf-8", errors="replace")
        if len(data) > MAX_BYTES:
            content = data[:MAX_BYTES].decode("utf-8", errors="ignore")
            truncated.add(path)
        files[path] = content
    dirs: set[str] = set()
    for path in files:
        tops = root_of(path)
        d = posixpath.dirname(path)
        while d and d != "/":
            dirs.add(d)
            if d in tops:
                break
            d = posixpath.dirname(d)
    for d in rep.dirs:
        under = root_of(d)
        if under and (not all(r in code_roots for r in under) or any(rx.fullmatch(d) for rx in locs)):
            dirs.add(d)
    return Collected(files=files, truncated=truncated, dirs=dirs, diff=None, base_present=None, workdir=workdir, base_sha=None, mode="offline")


PRUNE = (".git", "node_modules", "__pycache__")  # collect.py's


def collected_from_artifacts(run: Run, rubric: Rubric, trial_dir: Path, workdir: str = "/testbed") -> Collected:
    """``collected_from_replay``, with every rubric root harbor collected replaced by its real files.

    A root counts as collected when ``<trial>/artifacts/<root>`` exists (an empty directory included:
    the agent wrote nothing there). Same limits and pruning as ``collect.py``; still ``offline`` (no
    diff or base tree), with those roots in ``snapshot`` so the engine judges them as it would online.
    """
    col = collected_from_replay(run, rubric, workdir)
    base = Path(trial_dir) / "artifacts"
    snap = {r for r in _roots(rubric, workdir).values() if r != workdir and (base / r.lstrip("/")).is_dir()}
    if not snap:
        return col

    def under(path: str) -> bool:
        return any(path == r or path.startswith(r.rstrip("/") + "/") for r in snap)

    files = {p: c for p, c in col.files.items() if not under(p)}
    truncated = {p for p in col.truncated if not under(p)}
    dirs = {d for d in col.dirs if not under(d)}
    for root in sorted(snap):
        host = base / root.lstrip("/")
        dirs.add(root)
        for p in sorted(host.rglob("*")):
            rel = p.relative_to(host)
            if any(part in PRUNE for part in rel.parts) or len(rel.parts) > 8:
                continue
            path = posixpath.join(root, rel.as_posix())
            if p.is_dir() and not p.is_symlink():
                dirs.add(path)
            elif p.is_file() and not p.is_symlink() and len(files) < MAX_FILES:
                raw = p.read_bytes()
                files[path] = raw[:MAX_BYTES].decode("utf-8", errors="replace")
                if len(raw) > MAX_BYTES:
                    truncated.add(path)
    return Collected(
        files=files, truncated=truncated, dirs=dirs, diff=None, base_present=None, workdir=workdir, base_sha=None, mode="offline", snapshot=frozenset(snap)
    )
