"""Score saved `rllm eval` AI-DLC episodes with aidlc_v4_ifeval (layers), using the real saved artifacts.

Collected = trace replay, then the artifact root's files replaced by artifacts["workflow_outputs"] (the real
end-of-run files, as harbor's collected_from_artifacts does) and the repo diff parsed from artifacts["patch"].

usage: python score_eval_layers.py <shard_episode_dir> --run NAME --out rows.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import posixpath
import re
import sys
import traceback
from types import SimpleNamespace

REPO = "/vast-ib/MMI/home/kyuminkim/project/if/rllm"
sys.path.insert(0, REPO)

from recipe.grpo.qwen3_5.workflow_rubric import engine, layers as LY  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.context import Collected, EvalContext  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.evaluation import parse_run  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.offline.harbor import collected_from_replay  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.eval import Evaluation as IfEval  # noqa: E402

ART_ROOT = "/tmp/swe-bench-pro"
_HDR = re.compile(r"^diff --git a/(.*?) b/(.*)$", re.M)


def episode_obj(raw: dict):
    trajs = []
    for t in raw.get("trajectories") or []:
        steps = [SimpleNamespace(chat_completions=s.get("chat_completions") or []) for s in t.get("steps") or []]
        trajs.append(SimpleNamespace(name=t.get("name"), steps=steps))
    return SimpleNamespace(trajectories=trajs)


def parse_patch(patch: str | None) -> dict[str, str] | None:
    if not patch:
        return {} if patch == "" else None
    out: dict[str, str] = {}
    blocks = _HDR.split(patch)
    # split -> [pre, a1, b1, body1, a2, b2, body2, ...]
    for i in range(1, len(blocks), 3):
        a, b, body = blocks[i], blocks[i + 1], blocks[i + 2]
        head = body[:400]
        if "new file mode" in head:
            out[b] = "A"
        elif "deleted file mode" in head:
            out[a] = "D"
        elif a != b:
            out[b] = "R"
        else:
            out[b] = "M"
    return out


def with_artifacts(col: Collected, outputs: dict[str, str], diff: dict[str, str] | None) -> Collected:
    files = {p: c for p, c in col.files.items() if not (p == ART_ROOT or p.startswith(ART_ROOT + "/"))}
    dirs = {d for d in col.dirs if not (d == ART_ROOT or d.startswith(ART_ROOT + "/"))}
    dirs.add(ART_ROOT)
    for p, c in outputs.items():
        files[p] = c
        d = posixpath.dirname(p)
        while d and d != "/" and d != ART_ROOT:
            dirs.add(d)
            d = posixpath.dirname(d)
    bp = None
    if diff is not None:
        bp = {p: s in ("M", "D", "R") for p, s in diff.items()}
    return Collected(files=files, truncated=set(col.truncated), dirs=dirs, diff=diff, base_present=bp, workdir=col.workdir, base_sha=None, mode="offline", snapshot=frozenset({ART_ROOT}))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("shard_dir")
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ife = IfEval()
    rubric, layers, prefix = ife.rubric, ife.layers, ife.prefix
    by_id = {it.id: it for it in rubric.items}
    files = sorted(glob.glob(os.path.join(a.shard_dir, "episodes", "episode_*.json")))
    n_ok = 0
    with open(a.out, "w") as out:
        for f in files:
            raw = json.load(open(f))
            art = raw.get("artifacts") or {}
            met = raw.get("metrics") or {}
            task = raw.get("task") or {}
            rec = {
                "run": a.run, "file": os.path.basename(f), "task_id": task.get("id"), "is_correct": bool(raw.get("is_correct")),
                "termination": raw.get("termination_reason"), "steps": met.get("steps_used"),
                "live": {k: v for k, v in met.items() if k.startswith("aidlc/")},
                "n_outputs": len(art.get("workflow_outputs") or {}), "patch_bytes": art.get("patch_bytes"),
            }
            try:
                run = parse_run(episode_obj(raw), str(task.get("id") or ""))
                workdir = task.get("workdir") or "/testbed"
                col = with_artifacts(collected_from_replay(run, rubric, workdir), art.get("workflow_outputs") or {}, parse_patch(art.get("patch")))
                report = engine.evaluate(rubric, run, col)
                sig = dict(engine.signals(report, prefix))
                sig.update(LY.signals(rubric, run, col, report, layers, prefix))
                rec["signals"] = {k: float(v) for k, v in sig.items()}
                ctx = EvalContext(rubric=rubric, run=run, collected=col, facts=report.facts)
                items = {}
                for iid, spec in layers.items():
                    r = report.results.get(iid)
                    if r is None:
                        continue
                    try:
                        when_ok = LY._when(ctx, spec.get("when"))
                        reached = LY._reached(ctx, by_id[iid])
                    except Exception:  # noqa: BLE001
                        when_ok, reached = False, False
                    items[iid] = [r.status, round(float(r.score), 4), int(reached), int(when_ok)]
                rec["items"] = items
                rec["engine_errors"] = report.errors[:5]
                n_ok += 1
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {e}"
                traceback.print_exc(limit=3)
            out.write(json.dumps(rec) + "\n")
    print(f"{a.run} {os.path.basename(a.shard_dir)}: scored {n_ok}/{len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
