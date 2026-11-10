"""Layer analysis of base vs step27 scored by aidlc_v4_eval (rule-set verifier), with the draft layer assignment."""
# NOTE: WT/SP point at the session worktree of feat/aidlc-openhands-sdk-recipe (4a6686d3) and its scratchpad; set them to a checkout of that branch and a work dir.
import json, glob, collections, statistics as st, math, sys, yaml
SP = "/tmp/claude-6025/-vast-ib-MMI-home-kyuminkim-project-if-rllm/f07c07ab-b634-40a5-9927-dbb066a1b29d/scratchpad"
OUT = f"{SP}/eval09_out"; OLD = f"{SP}/eval_out"
RUBRIC = f"{SP}/wt_recipe/recipe/grpo/qwen3_5/workflows/aidlc_v4_eval/reward/rubric.yaml"
LAY = yaml.safe_load(open(f"{SP}/aidlc_v4_eval.layers.draft.yaml"))["items"]
METH = yaml.safe_load(open(f"{SP}/eval_method_layers.yaml"))
RU = yaml.safe_load(open(RUBRIC)); ITEMS = {it["id"]: it for it in RU["items"]}
RULES = {r["id"]: r for r in yaml.safe_load(open(f"{SP}/wt_recipe/recipe/grpo/qwen3_5/workflows/aidlc_v4_eval/reward/ruleset.yaml"))["rules"]}
TNAME = yaml.safe_load(open(f"{SP}/templates_branch.yaml"))["templates"]
LAYERS = ["L1", "L1C", "L2M", "L2F"]
CATS = ["P", "F", "E", "C", "R", "Q", "A"]

def load(run, root=OUT):
    d = {}
    for f in glob.glob(f"{root}/{run}_s*of8.jsonl"):
        for l in open(f):
            r = json.loads(l)
            if "items" in r: d[r["task_id"]] = r
    return d
B, S = load("base"), load("step27"); tasks = sorted(set(B) & set(S))
OB, OS = load("base", OLD), load("step27", OLD)  # ifeval scoring from 08
print(f"paired tasks: {len(tasks)} (base {len(B)}, step27 {len(S)}); errors: base {sum('error' in r for r in B.values())} step27 {sum('error' in r for r in S.values())}\n")

def stage_of(iid): return str(ITEMS[iid]["stage"])
def scored(r, iid):
    v = r["items"].get(iid); return v if v and v[0] in ("pass", "fail") else None
def reached(r, iid):
    s = stage_of(iid); return True if s == "global" else bool(r["reached"].get(s))
def layer_vals(r, only_reached=False):
    acc = collections.defaultdict(list)
    for iid, spec in LAY.items():
        L = spec["layer"]
        if L not in LAYERS: continue
        v = scored(r, iid)
        if v is None: continue
        if only_reached and not reached(r, iid): continue
        acc[L].append(v[1])
    return {L: (st.mean(x) if x else float("nan")) for L, x in acc.items()}
def mean(xs):
    xs = [x for x in xs if x is not None and x == x]; return st.mean(xs) if xs else float("nan")
def ci(ds):
    ds = [d for d in ds if d is not None and d == d]; return (st.mean(ds), 1.96 * st.stdev(ds) / math.sqrt(len(ds)), len(ds)) if len(ds) > 1 else (float("nan"), float("nan"), len(ds))

for r in list(B.values()) + list(S.values()):
    r["L"] = layer_vals(r); r["rL"] = layer_vals(r, True)

# ---------- 1. overall ----------
print("=" * 110); print("1. 전체 (n=499): resolve, 옛 v4 compliance(live), 새 평가기 score, 범주, 층"); print("=" * 110)
def row(name, R, ts):
    rs = [R[t] for t in ts]
    g = lambda k: mean([r["signals"].get(k, float("nan")) for r in rs])
    print(f"{name:7s} resolve {mean([float(r['is_correct']) for r in rs]):.3f}  live_v4 {mean([r['live'].get('aidlc/compliance', float('nan')) for r in rs]):.3f}  score {g('aidlc/score'):.3f} | "
          + " ".join(f"{c} {g('aidlc/kind/'+c):.3f}" for c in CATS if c != "Q") + f" | " + " ".join(f"{L} {mean([r['L'].get(L) for r in rs]):.3f}" for L in LAYERS)
          + " | " + " ".join(f"r{L} {mean([r['rL'].get(L) for r in rs]):.3f}" for L in LAYERS) + f" | 5arts {mean([float(r['n_outputs']>=5) for r in rs]):.2f} steps {mean([r['steps'] for r in rs]):.1f}")
row("base", B, tasks); row("step27", S, tasks)
print("\n-- paired Δ (step27 − base), mean ± 1.96·se --")
for L in LAYERS:
    for key, lab in (("L", "layer"), ("rL", "layer_reached")):
        m, h, n = ci([(S[t][key].get(L) if S[t][key].get(L) is not None else float("nan")) - (B[t][key].get(L) if B[t][key].get(L) is not None else float("nan")) for t in tasks]); print(f"   {lab+'/'+L:22s} n={n:3d}  Δ={m:+.3f} ± {h:.3f}")
m, h, n = ci([S[t]["signals"]["aidlc/score"] - B[t]["signals"]["aidlc/score"] for t in tasks]); print(f"   {'score':22s} n={n:3d}  Δ={m:+.3f} ± {h:.3f}")
for c in CATS:
    if c == "Q": continue
    m, h, n = ci([S[t]["signals"].get("aidlc/kind/"+c, float("nan")) - B[t]["signals"].get("aidlc/kind/"+c, float("nan")) for t in tasks]); print(f"   {'kind/'+c:22s} n={n:3d}  Δ={m:+.3f} ± {h:.3f}")
unav = mean([r["signals"].get("aidlc/unavailable", 0) for r in list(B.values()) + list(S.values())]); print(f"\n   unavailable/run {unav:.1f} (judge 항목; judge 미설정), engine errors: {sum(len(r.get('engine_errors') or []) for r in list(B.values())+list(S.values()))}")

# ---------- 2. per template ----------
print("\n" + "=" * 110); print("2. 템플릿별 통과율 (층, 전체 run / 두 run 모두 도달), method 수, 항목 수"); print("=" * 110)
tpl_items = collections.defaultdict(list)
for iid, spec in LAY.items():
    if spec["layer"] in LAYERS: tpl_items[(spec["layer"], spec["template"])].append(iid)
def rate(R, ids, ts, both_reached=False):
    xs = []
    for t in ts:
        for iid in ids:
            v = scored(R[t], iid)
            if v is None: continue
            if both_reached and not (reached(B[t], iid) and reached(S[t], iid)): continue
            xs.append(v[1])
    return mean(xs), len(xs)
print(f"{'layer':5s} {'template':34s} {'#m':>3s} {'#it':>4s} | {'base':>6s} {'s27':>6s} {'Δ':>7s} | {'r_base':>6s} {'r_s27':>6s} {'Δr':>7s} {'n':>6s}  name")
order = {"L1": 0, "L1C": 1, "L2M": 2, "L2F": 3}
for (L, T), ids in sorted(tpl_items.items(), key=lambda x: (order[x[0][0]], -len(x[0][1]) if False else x[0][1])):
    nm = sum(1 for k, m in METH.items() if m["template"] == T and m["layer"] == L)
    b, _ = rate(B, ids, tasks); s, _ = rate(S, ids, tasks); rb, n = rate(B, ids, tasks, True); rs, _ = rate(S, ids, tasks, True)
    print(f"{L:5s} {T:34s} {nm:3d} {len(ids):4d} | {b:6.3f} {s:6.3f} {s-b:+7.3f} | {rb:6.3f} {rs:6.3f} {rs-rb:+7.3f} {n:6d}  {(TNAME.get(T) or {}).get('name','')[:50]}")

# ---------- 3. per method for L1C / L2M / L2F ----------
print("\n" + "=" * 110); print("3. L1C·L2M·L2F method별 (두 run 모두 도달한 task): base→s27, 유지 P(s27✓|base✓), 획득 P(s27✓|base✗), McNemar b/c"); print("=" * 110)
def by_method(key):
    return [iid for iid in LAY if iid.split("@")[0] == key]
print(f"{'layer':5s} {'template':30s} {'method':38s} {'n':>5s} | {'base':>6s} {'s27':>6s} | {'유지':>5s} {'획득':>5s} | {'b':>4s} {'c':>4s}  rule")
for key, m in sorted(METH.items(), key=lambda x: (order.get(x[1]["layer"], 9), x[1]["template"], x[0])):
    if m["layer"] not in ("L1C", "L2M", "L2F"): continue
    ids = by_method(key); pp = pf = fp = ff = 0; xb = []; xs = []
    for t in tasks:
        for iid in ids:
            vb, vs = scored(B[t], iid), scored(S[t], iid)
            if vb is None or vs is None or not (reached(B[t], iid) and reached(S[t], iid)): continue
            xb.append(vb[1]); xs.append(vs[1]); b1, s1 = vb[0] == "pass", vs[0] == "pass"
            pp += b1 and s1; pf += b1 and not s1; fp += (not b1) and s1; ff += (not b1) and (not s1)
    n = pp + pf + fp + ff
    keep = pp / (pp + pf) if pp + pf else float("nan"); gain = fp / (fp + ff) if fp + ff else float("nan")
    rid = ITEMS[ids[0]].get("rule") if ids else ""
    print(f"{m['layer']:5s} {m['template']:30s} {key:38s} {n:5d} | {mean(xb):6.3f} {mean(xs):6.3f} | {keep:5.2f} {gain:5.2f} | {pf:4d} {fp:4d}  {rid}: {str(RULES.get(rid,{}).get('text',''))[:50]}")

# ---------- 4. transitions per layer ----------
print("\n" + "=" * 110); print("4. 층별 전이 (두 run 모두 도달): 유지 / 획득"); print("=" * 110)
for L in LAYERS:
    c = collections.Counter()
    for iid, spec in LAY.items():
        if spec["layer"] != L: continue
        for t in tasks:
            vb, vs = scored(B[t], iid), scored(S[t], iid)
            if vb is None or vs is None or not (reached(B[t], iid) and reached(S[t], iid)): continue
            c[("p" if vb[0] == "pass" else "f") + ("p" if vs[0] == "pass" else "f")] += 1
    n = sum(c.values()); bp = c["pp"] + c["pf"]; bf = c["fp"] + c["ff"]
    print(f"   {L:4s} 쌍 {n:6d}  base✓ {bp:6d} 유지 {c['pp']/bp if bp else float('nan'):.2f}  base✗ {bf:6d} 획득 {c['fp']/bf if bf else float('nan'):.2f}   통과율 {bp/n if n else float('nan'):.2f} → {(c['pp']+c['fp'])/n if n else float('nan'):.2f}")

# ---------- 5. resolve groups ----------
print("\n" + "=" * 110); print("5. 해결 묶음별 (전체 run 기준)"); print("=" * 110)
groups = {"both": [t for t in tasks if B[t]["is_correct"] and S[t]["is_correct"]], "only_s27": [t for t in tasks if not B[t]["is_correct"] and S[t]["is_correct"]],
          "only_base": [t for t in tasks if B[t]["is_correct"] and not S[t]["is_correct"]], "neither": [t for t in tasks if not B[t]["is_correct"] and not S[t]["is_correct"]]}
for g, ts in groups.items():
    print(f"-- {g} n={len(ts)}"); row("base", B, ts); row("step27", S, ts)

# ---------- 6. entry / completion ----------
print("\n" + "=" * 110); print("6. 진입·완주 run만"); print("=" * 110)
for title, cond in (("진입 (산출물 ≥1)", lambda r: r["n_outputs"] >= 1), ("완주 (산출물 = 5)", lambda r: r["n_outputs"] >= 5)):
    print(f"-- {title}"); 
    tb = [t for t in tasks if cond(B[t])]; ts_ = [t for t in tasks if cond(S[t])]
    row("base", B, tb); row("step27", S, ts_)
both = [t for t in tasks if B[t]["n_outputs"] >= 5 and S[t]["n_outputs"] >= 5]
print(f"-- 둘 다 완주, 같은 task n={len(both)}"); row("base", B, both); row("step27", S, both)
m, h, n = ci([S[t]["signals"]["aidlc/score"] - B[t]["signals"]["aidlc/score"] for t in both]); print(f"   paired Δ score = {m:+.3f} ± {h:.3f}")

# ---------- 7. vs ifeval (08) ----------
print("\n" + "=" * 110); print("7. 같은 task, 08(ifeval) 채점과 비교"); print("=" * 110)
common = [t for t in tasks if t in OB and t in OS and "signals" in OB[t] and "signals" in OS[t]]
def o(R, t, k): return R[t]["signals"].get(f"aidlc_ifeval/{k}", float("nan"))
print(f"{'':8s} {'ifeval':>8s} {'new score':>9s} | " + " ".join(f"{'if '+L:>8s} {'new '+L:>8s}" for L in LAYERS))
for name, R, OR in (("base", B, OB), ("step27", S, OS)):
    print(f"{name:8s} {mean([o(OR,t,'compliance') for t in common]):8.3f} {mean([R[t]['signals']['aidlc/score'] for t in common]):9.3f} | " + " ".join(f"{mean([o(OR,t,'layer/'+L) for t in common]):8.3f} {mean([R[t]['L'].get(L) for t in common]):8.3f}" for L in LAYERS))
def corr(xs, ys):
    p = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and x == x and y == y]; xs, ys = zip(*p); mx, my = st.mean(xs), st.mean(ys)
    sx, sy = st.pstdev(xs), st.pstdev(ys); return sum((x-mx)*(y-my) for x, y in p) / (len(p)*sx*sy) if sx and sy else float("nan")
for name, R, OR in (("base", B, OB), ("step27", S, OS)):
    print(f"   {name}: task별 상관 ifeval compliance vs new score r={corr([o(OR,t,'compliance') for t in common],[R[t]['signals']['aidlc/score'] for t in common]):.3f}; " + "; ".join(f"{L} r={corr([o(OR,t,'layer/'+L) for t in common],[R[t]['L'].get(L) for t in common]):.3f}" for L in LAYERS))

# per-task csv
with open(f"{OUT}/per_task.csv", "w") as f:
    f.write("run,task_id,is_correct,steps,n_outputs,live_v4,score," + ",".join("layer/"+L for L in LAYERS) + "," + ",".join("layer_reached/"+L for L in LAYERS) + "\n")
    for name, R in (("base", B), ("step27", S)):
        for t in tasks:
            r = R[t]; f.write(f"{name},{t},{int(r['is_correct'])},{r['steps']},{r['n_outputs']},{r['live'].get('aidlc/compliance','')},{r['signals']['aidlc/score']}," + ",".join(str(r["L"].get(L, "")) for L in LAYERS) + "," + ",".join(str(r["rL"].get(L, "")) for L in LAYERS) + "\n")

# ---------- 8. shared templates: ifeval vs new, reached-only pass rates ----------
print("\n" + "=" * 110); print("8. 공유 템플릿: ifeval(08) 항목 vs 새 평가기 method, 도달 기준 통과율 (base → s27)"); print("=" * 110)
IFC = yaml.safe_load(open(f"{SP}/ifeval_constraints.yaml")); IFC = IFC.get("constraints") or IFC.get("items")
if_tpl = collections.defaultdict(list)
for it in IFC:
    if it.get("status") == "implemented" and (it.get("eval") or {}).get("requirement", "must") == "must": if_tpl[it["template"]].append(it["id"])
def if_rate(R, ids, ts):
    xs = []
    for t in ts:
        if t not in R or "items" not in R[t]: continue
        for iid in ids:
            v = R[t]["items"].get(iid)
            if v and v[0] in ("pass", "fail") and v[2]: xs.append(v[1])
    return mean(xs), len(xs)
new_tpl = collections.defaultdict(list)
for iid, spec in LAY.items(): new_tpl[spec["template"]].append(iid)
def new_rate(R, ids, ts):
    xs = []
    for t in ts:
        for iid in ids:
            v = scored(R[t], iid)
            if v is not None and reached(R[t], iid): xs.append(v[1])
    return mean(xs), len(xs)
print(f"{'template':10s} | {'ifeval base':>11s} {'ifeval s27':>10s} {'Δ':>6s} {'#it':>4s} | {'new base':>9s} {'new s27':>8s} {'Δ':>6s} {'#it':>4s}  name")
for T in sorted(set(if_tpl) | set(new_tpl), key=lambda t: (t not in if_tpl or t not in new_tpl, t)):
    a = if_rate(OB, if_tpl.get(T, []), common); b = if_rate(OS, if_tpl.get(T, []), common)
    c = new_rate(B, new_tpl.get(T, []), common); d = new_rate(S, new_tpl.get(T, []), common)
    fa = lambda x: f"{x:.3f}" if x == x else "   -  "
    print(f"{T:10s} | {fa(a[0]):>11s} {fa(b[0]):>10s} {(b[0]-a[0]) if a[0]==a[0] else float('nan'):+6.2f} {len(if_tpl.get(T,[])):4d} | {fa(c[0]):>9s} {fa(d[0]):>8s} {(d[0]-c[0]) if c[0]==c[0] else float('nan'):+6.2f} {len(new_tpl.get(T,[])):4d}  {(TNAME.get(T) or {}).get('name','')[:45]}")

# ---------- 9. informative methods per layer ----------
print("\n" + "=" * 110); print("9. 층별 '정보 있는' method 수 (두 run 모두 도달 n≥50, base 통과율 0.1~0.9)"); print("=" * 110)
for L in LAYERS:
    tot = inf = 0; names = []
    for key, m in METH.items():
        if m["layer"] != L: continue
        ids = by_method(key); xb = []
        for t in tasks:
            for iid in ids:
                vb, vs = scored(B[t], iid), scored(S[t], iid)
                if vb is None or vs is None or not (reached(B[t], iid) and reached(S[t], iid)): continue
                xb.append(vb[0] == "pass")
        tot += 1
        if len(xb) >= 50 and 0.1 <= st.mean(xb) <= 0.9: inf += 1; names.append(f"{key}({st.mean(xb):.2f},n={len(xb)})")
    tpls = {METH[k.split('(')[0]]['template'] for k in names}
    print(f"   {L:4s} methods {tot:3d}, informative {inf:3d}, informative templates {len(tpls):2d}: " + ", ".join(sorted(tpls)))
    if L != "L1": print("        " + "; ".join(names))
