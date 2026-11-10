"""Score saved `rllm eval` AI-DLC episodes with the aidlc_v4_eval rule-set verifier (recipe branch worktree), offline.
# NOTE: WT/SP point at the session worktree of feat/aidlc-openhands-sdk-recipe (4a6686d3) and its scratchpad; set them to a checkout of that branch and a work dir.
usage: python score_eval09.py <shard_dir> --run NAME --out rows.jsonl"""
from __future__ import annotations
import argparse, glob, json, os, sys, traceback
from types import SimpleNamespace
WT = "/tmp/claude-6025/-vast-ib-MMI-home-kyuminkim-project-if-rllm/f07c07ab-b634-40a5-9927-dbb066a1b29d/scratchpad/wt_recipe"
sys.path.insert(0, WT)
from rllm.types import Episode  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric import engine  # noqa: E402
from recipe.grpo.qwen3_5.workflow_rubric.evaluation import parse_run  # noqa: E402
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.eval import Evaluation  # noqa: E402

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("shard_dir"); ap.add_argument("--run", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ev = Evaluation(); rubric, prefix = ev.rubric, ev.prefix
    stages = [(s.id, s.doc, list(s.artifacts)) for s in rubric.stages]
    files = sorted(glob.glob(os.path.join(a.shard_dir, "episodes", "episode_*.json")))
    n_ok = 0
    with open(a.out, "w") as out:
        for f in files:
            raw = json.load(open(f)); art = raw.get("artifacts") or {}; met = raw.get("metrics") or {}; task = raw.get("task") or {}
            rec = {"run": a.run, "file": os.path.basename(f), "task_id": task.get("id"), "is_correct": bool(raw.get("is_correct")),
                   "termination": raw.get("termination_reason"), "steps": met.get("steps_used"),
                   "live": {k: v for k, v in met.items() if k.startswith("aidlc/")},
                   "n_outputs": len(art.get("workflow_outputs") or {}), "patch_bytes": art.get("patch_bytes")}
            try:
                episode = Episode.from_dict(raw); episode.artifacts = art
                t = SimpleNamespace(id=task.get("id") or "", metadata=task)
                collected, _extra = ev.from_outputs(art.get("workflow_outputs") or {})
                collected.inputs = ev.inputs(t, episode)
                run = parse_run(episode, str(task.get("id") or ""))
                report = engine.evaluate(rubric, run, collected)
                sig = {k: float(v) for k, v in engine.signals(report, prefix).items()}
                if ev.post is not None:
                    for k, v in ev.post(report).items(): sig.setdefault(f"{prefix}/{k}", float(v))
                rec["signals"] = sig
                rec["items"] = {iid: [r.status, round(float(r.score), 4)] for iid, r in report.results.items()}
                reached = {}
                for sid, doc, arts in stages:
                    b1 = report.results.get(f"form/B1@{sid}")
                    reached[sid] = bool((b1 is not None and b1.status == "pass") or (doc and report.facts.doc_reads.get(doc)))
                rec["reached"] = reached
                rec["engine_errors"] = report.errors[:5]
                n_ok += 1
            except Exception as e:  # noqa: BLE001
                rec["error"] = f"{type(e).__name__}: {e}"; traceback.print_exc(limit=3)
            out.write(json.dumps(rec) + "\n")
    print(f"{a.run} {os.path.basename(a.shard_dir)}: scored {n_ok}/{len(files)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
