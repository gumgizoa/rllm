"""speckit_sdd as the evaluation workflow: the layer (L1 / L1C / L2M / L2F) of every scored item, by the
procedure of 10_handover_templates_layers.md §3.2 -- template default (sdlc_if/templates.yaml eval.layer),
reward in the three training workflows' constraints.yaml (implemented items), opposite-direction training
rules, instance exceptions. Reads sdd_assignment.yaml (sdd_templates.py); writes sdd_layers.yaml.

    python3 sdd_layers.py sdd_assignment.yaml sdd_layers.yaml
"""
import yaml, collections, sys
W = "/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/workflows"
rows = yaml.safe_load(open(sys.argv[1]))
cat = yaml.safe_load(open(f"{W}/../sdlc_if/templates.yaml"))["templates"]
train = collections.defaultdict(collections.Counter)
for wf, lab in [("agentos_v2", "AOS"), ("openspec_ff", "OSF"), ("speckit_bug", "SKB")]:
    for c in yaml.safe_load(open(f"{W}/{wf}/constraints.yaml"))["constraints"]:
        if c["status"] == "implemented": train[str(c["template"])][lab] += 1

# instance exceptions (10 §3.2 step 3 and 5): item id suffix -> (layer, reason)
EXC = {
    "speckit_sdd.converge.tasks.speckit_sdd_tasks.appended": ("L1C", "a converge stage must append a `## Phase N: Convergence` to tasks.md after its report (05-converge.md:17,155); opposite training rules: AOS agentos_v2.global.tasks.later_edits (must; any non-checkbox write of tasks.md after create_tasks fails, _norm_box), OSF openspec_ff.archive.run.paths_written.tasks_after_verify (must; no write of tasks.md after verify.md), SKB order(invalidate=rewrite) + CW:47 'Never rewrite an earlier report'; opposite training docs: AOS CW:63 'leave a file alone once its command is over, except for the checkboxes in tasks.md', OSF CW:105 'do not reopen tasks or apply'"),
    "speckit_sdd.converge_2.tasks.speckit_sdd_tasks.appended": ("L1C", "same as converge.appended"),
    "speckit_sdd.specify.spec.item_format.no_na_section": ("L1C", "spec.md has no bare 'N/A' line (01-specify.md:147 'remove it entirely, don't leave as N/A'); opposite training: AOS implement-tasks.md:279,306 'note \"None\"' as a section body (T-RF2 incomplete_listed / T-RF1 failed_listed reward it), SKB fix 'Previous verification: none' field_literal x9; weaker than the other two (literal None vs N/A, field vs section), kept L1C by the 11 §3 BMAD D40 precedent"),
}
# step 3 direction check: candidates compared with the training rules/docs and found NOT opposite (kept at their step-2 layer).
# Recorded so the check is not mistaken for 'any template match = L1'.
CHECKED = {
    "speckit_sdd.global.run.prohibited_action.git_branch": "no training rule or document asks for a git branch (grep git|branch over AOS/OSF/SKB docs: none); T-PR6 shared with OSF no_init/no_schema_flag/no_skip_validation -> L1, different command",
    "speckit_sdd.tasks.tasks.item_format.unchecked_when_written": "same direction: AOS create_tasks.item_format.unchecked (should, max 0 [x]), OSF ff.tasks.unchecked_at_plan (must)",
    "speckit_sdd.*.run.doc_read.constitution": "AOS CW:32 'there are no separate standards files to open' describes AOS's inline standards, it does not forbid reading an existing file; T-RD5 README/packaging/config reads are the same direction -> L1 (weak habit risk noted)",
    "speckit_sdd.implement_2.run.doc_read.im / converge_2.run.doc_read.cv": "re-reading a stage document in round 2 is what SKB rewards (fix_2/fix_3 doc_read.fx, test_2/test_3 doc_read.ts); the opposite rule (T-OR3 no_return) exists only in aidlc_v4_ifeval, which is not a training workflow -> L1",
    "speckit_sdd.global.run.speckit_holds.at_most_two_rounds": "SKB allows three rounds (CW:20) and rewards no_round_after_verified; the cap differs (2 vs 3) but the direction (stop when the report says done) is the same -> count is instance-level (templates.yaml), L1 '가까운 변형' not conflict",
    "speckit_sdd.global.run.speckit_holds.no_round_after_converged": "same direction as SKB no_round_after_verified; trigger literal differs (converged vs verified)",
    "speckit_sdd.converge.tasks.write_discipline.append_only": "passes when tasks.md is not written at all, so the trained habit (leave it alone) satisfies it; the conflict is carried by tasks.appended -> L1",
    "speckit_sdd.converge*.run.speckit_holds.tasks_unchanged_when_converged": "same direction as AOS later_edits / OSF tasks_after_verify",
    "speckit_sdd.implement.run.speckit_sdd_checks.red_green": "same direction: SKB 03-test.md:43 'passes now after failing before the change', SKB check_scripts.before_change, AOS checks.before_code",
    "speckit_sdd.implement.run.speckit_holds.tests_pass": "no training rule rewards a failing last run; AOS verify(whole_suite) makes a zero-failure last run harder (pre-existing failures) but is not an opposite instruction -> L1, habit risk noted",
    "speckit_sdd.implement.run.exec_evidence.baseline": "same direction as SKB fix.exec_evidence.baseline (window start..first edit) and AOS before_code; SDD's window starts at stage_start:implement, a window value",
    "speckit_sdd.global.run.speckit_sdd_untouched.shipped": "same direction as OSF CW:34 'Never run openspec init again', 00-explore.md:18 'do not hand-create openspec/ files'",
    "speckit_sdd.global.run.prohibited_action.ignore_files": "no training rule or doc touches ignore files; T-PR2 scratch patterns are the same direction (nothing of the workflow lands in /testbed)",
}
# templates without a catalogue default: decided from training reward (step 2)
NO_DEFAULT = {"T-RD5": "L1", "T-OR2": "L1", "T-AW5": "L1", "T-PR4": "L1", "T-PR6": "L1", "T-WD3": "L1", "T-WD4": "L1", "T-PG1": "L1", "T-FM8": "L1",
              "NEW-FM-internal": "L2F"}
NOTE = {
    "T-AW5": "the shipped script ran in the window = T-AW5 (OSF cli x18); the argument-set check inside the same item is 11's NEW-S3-command-format (09 puts 명령 형식 in L2F) -- counted L1 by its main logic",
    "T-WD2": "append_only is a variant of OSF's no_rewrite (the earlier content stays a prefix): same comparison, looser polarity",
    "T-RF3": "catalogue default L2M: the SKB subset item is held out of training (relative to the training rubric, 10 §3.3: L1 against the step27 checkpoint)",
    "NEW-FM-internal": "not in the catalogue; no training item compares two parts of one artifact (09: 산출물 내부 일관성 in L2-먼)",
    "T-TR1": "AOS 1 + OSF 2 cross_ref set relations are rewarded now; 01's 'AI-DLC 고유' was the 22 Oct rubric",
    "T-FM6": "AOS 4 + OSF 4 per-block items are rewarded now (01's table predates them)",
}
out = []
for r in rows:
    t = r["template"]
    if t is None: continue
    if r["id"] in EXC:
        L, why = EXC[r["id"]]
    else:
        L = (cat.get(t, {}).get("eval") or {}).get("layer") or NO_DEFAULT[t]
        why = NOTE.get(t, "")
        if L == "L1" and not train.get(t):
            raise SystemExit(f"{t} is L1 but no training item rewards it")
    out.append({**r, "layer": L, "trained_in": dict(train.get(t, {})), "layer_reason": why})
yaml.safe_dump(out, open(sys.argv[2], "w"), sort_keys=False, allow_unicode=True)

def table(items, title):
    lay = collections.defaultdict(lambda: collections.Counter())
    tpl = collections.defaultdict(collections.Counter)
    for r in items:
        lay[r["layer"]][r["requirement"]] += 1; tpl[r["layer"]][r["template"]] += 1
    print(f"\n== {title} ==")
    print("| 층 | 항목 | must | should | 템플릿 (항목 수) |"); print("|---|---|---|---|---|")
    for L in ("L1", "L1C", "L2M", "L2F"):
        c = lay[L]; n = sum(c.values())
        print(f"| {L} | {n} | {c['must']} | {c['should']} | " + ", ".join(f"{t} {k}" for t, k in tpl[L].most_common()) + " |")
    print(f"| 합계 | {len(items)} | {sum(r['requirement']=='must' for r in items)} | {sum(r['requirement']=='should' for r in items)} | |")
table(out, "speckit_sdd as eval: layers (current training constraints)")
# the step27 view: T-RF3 was still rewarded by the old SKB rubric (10 §3.3)
alt = [{**r, "layer": "L1"} if r["template"] == "T-RF3" else r for r in out]
print("\nstep27 (old SKB rubric) view: L2M ->", collections.Counter(r["layer"] for r in alt)["L2M"], ", L1 ->", collections.Counter(r["layer"] for r in alt)["L1"])
