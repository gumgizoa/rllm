#!/usr/bin/env python
"""Score a finished run's workflow compliance from its saved episodes, without a sandbox.

``rllm eval`` keeps each rollout's trajectory in the episode JSON and, through
``WorkflowMixin.collect_patch``, what the workflow left in the sandbox (``artifacts``, see
``run_artifacts.py``). That is everything a workflow's scorer reads, so the scorer registered for
the workflow runs here on the saved episode exactly as it ran against the live sandbox:
``score(task, episode, from_outputs(artifacts["workflow_outputs"]))``.

Usage:
    python recipe/grpo/qwen3_5/scripts/rescore_compliance.py <episodes_dir> [--workflow NAME]
        [--harness openhands-sdk] [--out scores.jsonl] [--compare]

``--workflow`` defaults to the one the episodes record (``artifacts["workflow"]["name"]``); an
episode recorded under another workflow, or another version of it (``sha256``), is reported and
scored anyway, since an older run is often the point. ``--compare`` checks the result against the
signals the live scorer stored in the same episode, the test that the saved artifacts are enough.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipe.grpo.qwen3_5.workflows import get_workflow  # noqa: E402
from rllm.types import Episode  # noqa: E402


def load_episode(path: Path) -> tuple[Episode, dict]:
    raw = json.loads(path.read_text())
    episode = Episode.from_dict(raw)
    episode.artifacts = raw.get("artifacts") or {}  # from_dict leaves them out
    return episode, raw


def live_signals(raw: dict, prefix: str) -> dict[str, float]:
    """The signals the live scorer stored with this episode (trajectory first, then metrics)."""
    for traj in raw.get("trajectories") or []:
        sig = {k: v for k, v in (traj.get("signals") or {}).items() if k.startswith(prefix)}
        if sig:
            return sig
    return {k: v for k, v in (raw.get("metrics") or {}).items() if k.startswith(prefix)}


def rescore(paths: list[Path], workflow: str | None, harness: str, compare: bool):
    """Yield one record per episode: its scores, or why it has none."""
    for path in paths:
        episode, raw = load_episode(path)
        art = episode.artifacts or {}
        recorded = art.get("workflow") or {}
        name = workflow or recorded.get("name")
        rec: dict = {"episode": path.name, "task_id": (raw.get("task") or {}).get("id"), "is_correct": raw.get("is_correct"), "workflow": name}
        if not name:
            rec["skipped"] = "episode records no workflow; pass --workflow"
            yield rec
            continue
        spec = get_workflow(name)
        factory = spec.scorers.get(harness)
        policy = factory() if factory is not None else None
        if policy is None or getattr(policy, "from_outputs", None) is None:
            rec["skipped"] = f"workflow {name!r} has no offline scorer for {harness!r}"
            yield rec
            continue
        if "workflow_outputs" not in art:
            rec["skipped"] = "episode has no artifacts['workflow_outputs'] (run without collect_patch?)"
            yield rec
            continue
        fingerprint = spec.fingerprint(harness)
        if recorded.get("name") != name or recorded.get("sha256") != fingerprint:
            rec["version_mismatch"] = {"recorded": recorded, "scoring_with": {"name": name, "sha256": fingerprint}}
        task = SimpleNamespace(id=rec["task_id"] or "", metadata=raw.get("task") or {})
        signals = policy.score(task, episode, policy.from_outputs(art["workflow_outputs"]))
        rec["signals"] = {k: float(v) for k, v in signals.items()}
        if compare:
            prefix = next(iter(signals), "").split("/", 1)[0] + "/"
            live = live_signals(raw, prefix)
            rec["live_diff"] = {k: rec["signals"][k] - float(live[k]) for k in rec["signals"] if k in live and abs(rec["signals"][k] - float(live[k])) > 1e-9}
            rec["live_missing"] = not live
        yield rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes_dir", type=Path)
    ap.add_argument("--workflow", default=None)
    ap.add_argument("--harness", default="openhands-sdk")
    ap.add_argument("--out", type=Path, default=None, help="per-episode records as JSONL")
    ap.add_argument("--compare", action="store_true", help="check against the signals stored by the live scorer")
    args = ap.parse_args()

    paths = sorted(args.episodes_dir.glob("*.json"))
    if not paths:
        print(f"no episode JSON under {args.episodes_dir}", file=sys.stderr)
        return 1
    out = args.out.open("w") if args.out else None
    sums: Counter = Counter()
    scored, skipped, mismatched, differing, no_live = 0, Counter(), 0, 0, 0
    for rec in rescore(paths, args.workflow, args.harness, args.compare):
        if out:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if "skipped" in rec:
            skipped[rec["skipped"]] += 1
            continue
        scored += 1
        sums.update(rec["signals"])
        mismatched += "version_mismatch" in rec
        if args.compare:
            differing += bool(rec["live_diff"])
            no_live += rec["live_missing"]
    if out:
        out.close()

    print(f"episodes {len(paths)}  scored {scored}  skipped {sum(skipped.values())}  workflow-version mismatch {mismatched}")
    for reason, n in skipped.items():
        print(f"  skipped {n}: {reason}")
    for k in sorted(sums):
        print(f"  {k:28s} {sums[k] / scored:.3f}")
    if args.compare:
        print(f"compare with live scores: {scored - differing - no_live} identical, {differing} differ, {no_live} without live scores")
        return 1 if differing else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
