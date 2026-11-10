import json, glob, statistics as st, collections, sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "eval_out"  # dir with {base,step27}_s*of8.jsonl from score_eval_layers.py
def load(run):
    d = {}
    for f in glob.glob(f"{OUT}/{run}_s*of8.jsonl"):
        for l in open(f):
            r = json.loads(l)
            if "items" in r: d[r["task_id"]] = r
    return d
B, S = load("base"), load("step27")
tasks = sorted(set(B) & set(S))
def g(r, k): return r["signals"].get(f"aidlc_ifeval/{k}", float("nan"))
def live(r): return r["live"].get("aidlc/compliance", float("nan"))
def mean(xs):
    xs = [x for x in xs if x == x]; return st.mean(xs) if xs else float("nan")
def line(name, rs):
    if not rs: print(f"   {name:7s} n=  0"); return
    print(f"   {name:7s} n={len(rs):3d}  resolve {mean([float(r['is_correct']) for r in rs]):.3f}  live_v4 {mean([live(r) for r in rs]):.3f}  ifeval {mean([g(r,'compliance') for r in rs]):.3f} | "
          f"L1 {mean([g(r,'layer/L1') for r in rs]):.3f} L1C {mean([g(r,'layer/L1C') for r in rs]):.3f} L2M {mean([g(r,'layer/L2M') for r in rs]):.3f} L2F {mean([g(r,'layer/L2F') for r in rs]):.3f} | "
          f"rL1 {mean([g(r,'layer_reached/L1') for r in rs]):.3f} rL1C {mean([g(r,'layer_reached/L1C') for r in rs]):.3f} rL2M {mean([g(r,'layer_reached/L2M') for r in rs]):.3f} rL2F {mean([g(r,'layer_reached/L2F') for r in rs]):.3f} | steps {mean([r['steps'] for r in rs]):.1f}")
print("산출물 수 분포 (n_outputs): base", sorted(collections.Counter(B[t]['n_outputs'] for t in tasks).items()), " step27", sorted(collections.Counter(S[t]['n_outputs'] for t in tasks).items()))
print()
for title, cond in (("1. 전체 run", lambda r: True), ("2. 진입한 run (산출물 ≥1)", lambda r: r["n_outputs"] >= 1), ("3. 완주한 run (산출물 = 5)", lambda r: r["n_outputs"] >= 5), ("4. 미완주 run (1 ≤ 산출물 < 5)", lambda r: 1 <= r["n_outputs"] < 5)):
    print(title)
    line("base", [B[t] for t in tasks if cond(B[t])]); line("step27", [S[t] for t in tasks if cond(S[t])])
    print()
print("5. 같은 task, 두 모델 모두 완주 (paired)")
both = [t for t in tasks if B[t]["n_outputs"] >= 5 and S[t]["n_outputs"] >= 5]
line("base", [B[t] for t in both]); line("step27", [S[t] for t in both])
d = [g(S[t], "compliance") - g(B[t], "compliance") for t in both]
print(f"   paired Δ ifeval = {st.mean(d):+.3f} ± {1.96*st.stdev(d)/len(d)**0.5:.3f}")
print()
print("6. 완주 run의 ifeval compliance 분포")
for name, R in (("base", B), ("step27", S)):
    xs = sorted(g(R[t], "compliance") for t in tasks if R[t]["n_outputs"] >= 5)
    q = lambda p: xs[int(p*(len(xs)-1))]
    print(f"   {name:7s} n={len(xs):3d}  p10 {q(.1):.2f}  p25 {q(.25):.2f}  median {q(.5):.2f}  p75 {q(.75):.2f}  p90 {q(.9):.2f}   ≥0.8: {sum(x>=0.8 for x in xs)/len(xs):.2f}  ≥0.9: {sum(x>=0.9 for x in xs)/len(xs):.2f}")
