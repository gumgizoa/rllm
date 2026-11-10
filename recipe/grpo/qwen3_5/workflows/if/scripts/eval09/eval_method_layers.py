"""aidlc_v4_eval: method -> template -> evaluation layer; distribution; draft layers.yaml (scratchpad only)."""
# NOTE: WT/SP point at the session worktree of feat/aidlc-openhands-sdk-recipe (4a6686d3) and its scratchpad; set them to a checkout of that branch and a work dir.
import sys, collections, hashlib, yaml
sys.path.insert(0, "/vast-ib/MMI/home/kyuminkim/project/if/rllm")
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.methods import load
SP = "/tmp/claude-6025/-vast-ib-MMI-home-kyuminkim-project-if-rllm/f07c07ab-b634-40a5-9927-dbb066a1b29d/scratchpad"
RUBRIC = "/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/workflows/aidlc_v4_eval/reward/rubric.yaml"
M = load()
TPL = yaml.safe_load(open(f"{SP}/templates_branch.yaml"))["templates"]
MAP = yaml.safe_load(open(f"{SP}/eval_method_templates.yaml"))
MAP["atom/H8e"] = "T-AW3"   # 'no regression left' = checks(pass_last), a T-AW3 kind in training (SKB local_verification)

# instance-level layer overrides (template default otherwise); reason strings for the record
OVERRIDE = {
 "rule/r_targeted_tests": ("L1C", "stage-5 runs must name targets = no whole suite; AOS verify requires the whole suite (must)"),
 "atom/D7b": ("L1", "shape of the recorded test command; training conflicts only on running the whole suite (ifeval test_selection)"),
 "check/t5_repro_run_after_last_edit": ("L2M", "runs the script at the path A4 recorded; training rewards that element only per tick (ifeval reproduction_script_execution)"),
 "atom/H8e": ("L1", "outcome form checks(pass_last): SKB local_verification requires the checks to pass at the last run"),
 "atom/H1c": ("L2M", "order among verifications (build failure before tests); extends T-OR2 branch-on-result, no training item orders verifications"),
 "atom/H10": ("L1", "retry cap: OSF archive retries / SKB rounds cap (T-OR2)"),
 "atom/H8a": ("L1", "branch on a failed result: SKB 'if a check fails, another fix round' (T-OR2)"),
 "atom/H17": ("L1", "branch on a passed result: SKB/OSF proceed when checks pass (T-OR2)"),
 "atom/D4b": ("L1", "a prohibited command class (survey listings); T-PR6 is rewarded in OSF/SKB with other commands"),
 "atom/H7": ("L1", "a prohibited command (stash / reverse-apply); T-PR6"),
 "atom/D10a": ("L1", "read the covering test files: T-RD5 in all three training workflows"),
 "atom/B11": ("L1", "one artifact per stage at the designated location: T-WD3 in all three training workflows"),
}
NEW_LAYER = {
 "NEW-RF-record-after-observation": ("L2M", "training writes each report once at stage end after running its checks (SKB CW:47, FX:31-33): the timing is shown, never rewarded; extends T-RF1"),
 "NEW-CS-intra-artifact": ("L2F", "no training item compares two fields of one artifact"),
 "NEW-IS-issue-fidelity": ("L2F", "no training item compares an artifact with the issue text"),
 "NEW-TR-keyed-order": ("L2M", "edits in plan-step order; AOS groups_in_order rewards ordered work units (NEW-PG-unit) on ticks, not edits"),
 "NEW-SEM-patch-contract": ("L2F", "signature preservation judged on the patch: no training item"),
 "NEW-CMD-form": ("L2F", "required command flags: no training item (OSF cli kinds check which command runs, not its flags)"),
 "NEW-RD-one-at-a-time": ("L2F", "one rule document per read call: no training item or document"),
 "NEW-WD-exists-before": ("L2F", "existence check before a write: AI-DLC only (01: unimplemented candidate)"),
}
ISSUE_F3 = ("L2M", "quoting the issue's names verbatim: SKB FX:31 'copy every example the issue gives verbatim' shows it, no training item")

def layer_of(key):
    t = MAP[key]
    if key.startswith("judge/"): return "J", "LLM judge on content adequacy; no training workflow rewards or shows a judged content rule; kept on its own axis"
    if key in OVERRIDE: return OVERRIDE[key]
    if key == "atom/F3": return ISSUE_F3
    if t in NEW_LAYER: return NEW_LAYER[t]
    ev = TPL.get(t, {}).get("eval")
    if ev: return ev["layer"], f"template default ({TPL[t].get('eval',{}).get('reason','') or 'trained template'})"
    raise RuntimeError(f"no layer for {key} ({t})")

rows = {}
for k in sorted(M):
    L, why = layer_of(k)
    rows[k] = {"template": MAP[k], "layer": L, "reason": why, "stages": list(M[k].stages) if M[k].stages else None}
yaml.safe_dump(rows, open(f"{SP}/eval_method_layers.yaml", "w"), allow_unicode=True, sort_keys=True, width=160)

# items (stage-expanded) from rubric.yaml, with category / log_only
R = yaml.safe_load(open(RUBRIC)); items = R["items"]
by_item = {}
for it in items:
    iid = it["id"]; key = iid.split("@")[0]
    if key not in rows: raise RuntimeError(f"item {iid} has no method row")
    by_item[iid] = {"key": key, "cat": it.get("category"), "log_only": bool(it.get("log_only")), "rule": it.get("rule")}
# draft layers.yaml for the engine (scored items only; judge items too, under J)
sha = hashlib.sha256(open(RUBRIC, "rb").read()).hexdigest()
ly = {"rubric_sha256": sha, "source": "scratchpad eval_method_layers.py (draft)", "items": {}}
for iid, m in by_item.items():
    if m["log_only"]: continue
    r = rows[m["key"]]
    ly["items"][iid] = {"layer": r["layer"], "requirement": "must", "template": r["template"]}
yaml.safe_dump(ly, open(f"{SP}/aidlc_v4_eval.layers.draft.yaml", "w"), sort_keys=False)

# ---- distribution ----
order = ["L1", "L1C", "L2M", "L2F", "J"]
def show(title, counter, cols=order):
    print(title); print("  " + "  ".join(f"{c:>5s}" for c in cols) + "   total")
    tot = sum(counter.values()); print("  " + "  ".join(f"{counter.get(c,0):5d}" for c in cols) + f"   {tot}")
print(f"methods {len(rows)}, rubric items {len(items)} (scored {sum(1 for m in by_item.values() if not m['log_only'])}, diagnostic {sum(1 for m in by_item.values() if m['log_only'])})\n")
show("A. methods per layer", collections.Counter(r["layer"] for r in rows.values()))
show("\nB. scored items (method@stage) per layer", collections.Counter(rows[m["key"]]["layer"] for m in by_item.values() if not m["log_only"]))
tpl_by_layer = collections.defaultdict(set)
for r in rows.values(): tpl_by_layer[r["layer"]].add(r["template"])
show("\nC. distinct templates per layer (the k that matters)", collections.Counter({L: len(s) for L, s in tpl_by_layer.items()}))
print("\nD. templates per layer:")
for L in order:
    ts = sorted(tpl_by_layer[L]); 
    print(f"  {L:4s} ({len(ts)}): " + ", ".join(f"{t}×{sum(1 for r in rows.values() if r['template']==t and r['layer']==L)}" for t in ts))
print("\nE. scored items: layer × category")
cats = ["P","F","E","C","R","Q","A"]
cross = collections.Counter((rows[m["key"]]["layer"], m["cat"]) for m in by_item.values() if not m["log_only"])
print("  " + "layer".ljust(5) + "".join(f"{c:>5s}" for c in cats) + "  total")
for L in order:
    print("  " + L.ljust(5) + "".join(f"{cross.get((L,c),0):5d}" for c in cats) + f"  {sum(v for (l,c),v in cross.items() if l==L):5d}")
print("\nF. scored items: layer × stage")
stages = ["global","1","2","3","4","5"]
st = collections.Counter((rows[m["key"]]["layer"], str(next(i for i in items if i['id']==iid)['stage'])) for iid, m in by_item.items() if not m["log_only"])
print("  " + "layer".ljust(5) + "".join(f"{s:>7s}" for s in stages))
for L in order:
    print("  " + L.ljust(5) + "".join(f"{st.get((L,s),0):7d}" for s in stages))
print("\nG. L1C / L2M / L2F / new-template methods in full:")
for L in ("L1C","L2M","L2F"):
    for k, r in sorted(rows.items(), key=lambda x: (x[1]["template"], x[0])):
        if r["layer"] == L: print(f"  {L:4s} {r['template']:34s} {k:40s} {r['reason'][:95]}")
