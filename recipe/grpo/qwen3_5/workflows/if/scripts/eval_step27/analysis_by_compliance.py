"""Split the base->step27 comparison by what base already complied with.
A) per (task,item) transitions, paired by task_id: retention P(s27 pass | base pass), gain P(s27 pass | base fail)
B) tasks grouped by base's own compliance (workflow completed / ifeval quartile): step27 outcome per group
"""
import json, glob, collections, statistics as st, sys, yaml
OUT = sys.argv[1] if len(sys.argv) > 1 else "eval_out"  # dir with {base,step27}_s*of8.jsonl from score_eval_layers.py
LY = yaml.safe_load(open("/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/workflows/aidlc_v4_ifeval/reward/layers.yaml"))["items"]
TPL = yaml.safe_load(open("/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/sdlc_if/templates.yaml"))
tname = {}
for t in (TPL.get("templates") or []):
    if isinstance(t, dict) and "id" in t: tname[t["id"]] = (t.get("name") or t.get("rule") or "")[:60]
if not tname and isinstance(TPL.get("templates"), dict):
    for k, v in TPL["templates"].items(): tname[k] = (v.get("name") or v.get("rule") or "")[:60]

def load(run):
    d = {}
    for f in glob.glob(f"{OUT}/{run}_s*of8.jsonl"):
        for l in open(f):
            r = json.loads(l)
            if "items" in r: d[r["task_id"]] = r
    return d
B, S = load("base"), load("step27")
tasks = sorted(set(B) & set(S))
print(f"paired tasks: {len(tasks)}\n")

must = [i for i, s in LY.items() if s["requirement"] == "must"]
def passed(x): return x[0] == "pass"
def applicable(x): return x[0] in ("pass", "fail")

# ---------- A ----------
def trans(filter_reached):
    agg = collections.defaultdict(lambda: collections.Counter())  # key -> {pp,pf,fp,ff}
    for t in tasks:
        bi, si = B[t]["items"], S[t]["items"]
        for i in must:
            if i not in bi or i not in si: continue
            b, s = bi[i], si[i]
            if not (applicable(b) and applicable(s)): continue
            if filter_reached and not (b[2] and s[2] and b[3] and s[3]): continue
            k = ("p" if passed(b) else "f") + ("p" if passed(s) else "f")
            for key in (("ALL", "ALL"), (LY[i]["layer"], "ALL"), (LY[i]["layer"], LY[i]["template"])):
                agg[key][k] += 1
    return agg

def show(agg, title):
    print("=" * 110); print(title); print("=" * 110)
    print(f"{'layer':5s} {'template':9s} {'n':>6s} | {'base✓':>6s} {'유지':>6s} {'퇴보':>6s} | {'base✗':>6s} {'획득':>6s} {'잔류':>6s} | {'base→s27':>13s}  name")
    def row(k, c):
        n = sum(c.values()); bp = c["pp"] + c["pf"]; bf = c["fp"] + c["ff"]
        keep = c["pp"] / bp if bp else float("nan"); gain = c["fp"] / bf if bf else float("nan")
        return f"{k[0]:5s} {k[1]:9s} {n:6d} | {bp:6d} {keep:6.2f} {1-keep if bp else float('nan'):6.2f} | {bf:6d} {gain:6.2f} {1-gain if bf else float('nan'):6.2f} | {bp/n:5.2f} → {(c['pp']+c['fp'])/n:5.2f}  {tname.get(k[1],'')}"
    order = {"L1": 0, "L1C": 1, "L2M": 2, "L2F": 3, "ALL": 9}
    for k in sorted(agg, key=lambda k: (k[1] != "ALL", order.get(k[0], 5), k[1])):
        if k[1] == "ALL": print(row(k, agg[k]))
    print("-" * 110)
    for k in sorted(agg, key=lambda k: (order.get(k[0], 5), -sum(agg[k].values()))):
        if k[1] != "ALL" and sum(agg[k].values()) >= 20: print(row(k, agg[k]))
    print()

show(trans(False), "A1. (task,항목) 전이, must 항목, 두 run 모두 applicable  — 유지=P(s27 pass|base pass), 획득=P(s27 pass|base fail)")
show(trans(True), "A2. 같은 전이, 두 run 모두 해당 단계 도달(reached & when) 한 경우만")

# ---------- B ----------
def g(r, k): return r["signals"].get(f"aidlc_ifeval/{k}", float("nan"))
def summarize(ts, label):
    def m(run, k):
        xs = [g(run[t], k) for t in ts]; xs = [x for x in xs if x == x]
        return st.mean(xs) if xs else float("nan")
    def res(run): return st.mean(float(run[t]["is_correct"]) for t in ts)
    def arts(run): return st.mean(float(run[t]["n_outputs"] >= 5) for t in ts)
    print(f"{label:28s} n={len(ts):3d}")
    for name, run in (("base", B), ("step27", S)):
        print(f"   {name:7s} resolve {res(run):.3f}  5arts {arts(run):.2f}  ifeval {m(run,'compliance'):.3f} | L1 {m(run,'layer/L1'):.3f} L1C {m(run,'layer/L1C'):.3f} L2M {m(run,'layer/L2M'):.3f} L2F {m(run,'layer/L2F'):.3f} | rL1 {m(run,'layer_reached/L1'):.3f} rL1C {m(run,'layer_reached/L1C'):.3f} rL2M {m(run,'layer_reached/L2M'):.3f} rL2F {m(run,'layer_reached/L2F'):.3f}")
print("=" * 110); print("B1. base가 workflow를 완주(5 산출물)했는지로 task 분리"); print("=" * 110)
summarize([t for t in tasks if B[t]["n_outputs"] >= 5], "base 완주")
summarize([t for t in tasks if B[t]["n_outputs"] < 5], "base 미완주")
print(); print("=" * 110); print("B2. base ifeval compliance 사분위로 task 분리"); print("=" * 110)
bc = sorted(tasks, key=lambda t: g(B[t], "compliance"))
q = len(bc) // 4
for i, lab in enumerate(["Q1 base 최저", "Q2", "Q3", "Q4 base 최고"]):
    ts = bc[i*q:(i+1)*q] if i < 3 else bc[3*q:]
    lo, hi = g(B[ts[0]], "compliance"), g(B[ts[-1]], "compliance")
    summarize(ts, f"{lab} [{lo:.2f},{hi:.2f}]")
# within-group resolve change
print(); print("B3. 묶음별 resolve 변화 (base→step27, 전이 수)")
for lab, ts in (("base 완주", [t for t in tasks if B[t]["n_outputs"] >= 5]), ("base 미완주", [t for t in tasks if B[t]["n_outputs"] < 5])):
    c = collections.Counter((bool(B[t]["is_correct"]), bool(S[t]["is_correct"])) for t in ts)
    print(f"   {lab:12s} n={len(ts):3d} both {c[(True,True)]:3d}  only_s27 {c[(False,True)]:3d}  only_base {c[(True,False)]:3d}  neither {c[(False,False)]:3d}  resolve {sum(bool(B[t]['is_correct']) for t in ts)/len(ts):.3f} → {sum(bool(S[t]['is_correct']) for t in ts)/len(ts):.3f}")
