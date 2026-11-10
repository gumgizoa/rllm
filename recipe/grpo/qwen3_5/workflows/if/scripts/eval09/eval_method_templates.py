"""Draft: aidlc_v4_eval method -> sdlc_if template (judging logic). NEW-* = no template in templates.yaml."""
# NOTE: WT/SP point at the session worktree of feat/aidlc-openhands-sdk-recipe (4a6686d3) and its scratchpad; set them to a checkout of that branch and a work dir.
import sys, re, collections, yaml
sys.path.insert(0, "/vast-ib/MMI/home/kyuminkim/project/if/rllm")
from recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.methods import load
M = load()
MAP = {
 # procedure
 "proc/A2":"T-RD2","proc/A3a":"NEW-RD-one-at-a-time","proc/A3b":"T-RD3","proc/B3b":"T-OR1","proc/C1a":"T-OR1","proc/C1b":"T-OR1","run/entry":"T-RD1",
 # rule / run
 "rule/r_tests_untouched":"T-PR1","rule/r_targeted_tests":"T-PR5","rule/r_no_env_setup":"T-PR3","rule/r_repro_not_in_stage4":"T-AW4","rule/r_artifacts_written_once":"T-WD1","rule/r_repo_clean":"T-PR2",
 "run/ran_real_test":"T-AW3","run/fidelity":"T-RF3",
 # form
 "form/B1":"T-FM1","form/B6a":"T-FM5","form/B5b":"T-FM2","form/E3c":"T-FM3","form/E4b":"T-FM3","form/G9":"T-FM6",
 # claims: evidence
 "check/e1_baseline_tests":"T-RF1","check/e1_baseline_failing":"T-RF2","check/e1_baseline_none":"T-RF2","check/e1_baseline_passing":"T-RF1","check/e1_scope_viewed":"T-RF1","check/e1_test_command_run":"T-RF1","check/e1_build_command_run":"T-RF1","check/e1_test_path_seen":"T-RF1",
 "check/e4_modified":"T-RF3","check/e4_created":"T-RF3","check/e4_undisclosed":"T-RF3","check/e4_tests_untouched":"T-RF2","check/e4_duplicates_none":"T-RF2",
 "check/e5_repro_result":"T-RF1","check/e5_build_result":"T-RF1","check/e5_command_run":"T-RF1","check/e5_regressions":"T-RF2","check/e5_outstanding_none":"T-RF2","check/e5_regressions_listed":"T-RF1","check/e5_preexisting_listed":"T-RF1","check/e5_final_files_diff":"T-RF3","check/e5_unintended_none":"T-RF2","check/e5_test_files_none":"T-RF2",
 # claims: temporal
 "check/t1_baseline_before_write":"NEW-RF-record-after-observation","check/t1_baseline_before_edit":"T-AW2","check/t1_no_edit_before_write":"T-AW1","check/t4_repro_written_before_write":"NEW-RF-record-after-observation","check/t5_repro_run_after_last_edit":"T-AW3","check/t5_regression_after_last_edit":"T-AW3",
 # claims: consistency
 "check/c23_tags_exist":"T-TR1","check/c23_requirements_covered":"T-TR1","check/c23_exercises_exist":"T-TR1","check/c23_coverage_refs":"T-TR1","check/c34_repro_path":"T-TR1","check/c34_targets_changed":"T-TR1","check/c34_plan_execution_steps":"T-TR1","check/c34_deviations_none":"T-RF2","check/c34_deviations_recorded":"T-RF3","check/c14_scope_changed":"T-TR1","check/c15_preexisting_subset":"T-TR1","check/c25_unmet_exist":"T-TR1","check/c45_final_files":"T-TR1",
 # atoms
 "atom/B3a":"T-WD1","atom/B4a":"T-WD2","atom/B5d":"T-FM2","atom/B6b":"T-FM2","atom/B6c":"T-FM2","atom/B8":"T-RD6","atom/B10":"T-PR2","atom/B11":"T-WD3","atom/C2":"T-OR3",
 "atom/D1b":"NEW-IS-issue-fidelity","atom/D3b":"NEW-CS-intra-artifact","atom/D4a":"NEW-IS-issue-fidelity","atom/D4b":"T-PR6","atom/D5":"T-FM2","atom/D5b":"T-FM3","atom/D7b":"T-PR5","atom/D8":"NEW-CMD-form","atom/D10a":"T-RD5","atom/D12b":"T-FM3",
 "atom/E3a":"T-FM2","atom/E4a":"T-FM3","atom/E7b":"NEW-IS-issue-fidelity","atom/E8c":"T-FM2","atom/E10a":"T-SR2","atom/E10b":"T-SR2","atom/E10c":"T-SR2",
 "atom/F1b":"T-FM3","atom/F2a":"T-FM2","atom/F2b":"T-FM2","atom/F3":"NEW-IS-issue-fidelity","atom/F4b":"T-TR1","atom/F7":"T-PR1","atom/F8a":"T-RF4","atom/F8b":"T-PR2","atom/F9b":"T-RF4",
 "atom/G1a":"NEW-TR-keyed-order","atom/G3a":"NEW-WD-exists-before","atom/G3c":"T-TR2","atom/G4b":"T-PR1","atom/G5":"NEW-SEM-patch-contract","atom/G7c":"T-AW4","atom/G8b":"T-FM2",
 "atom/H1a":"T-TR2","atom/H1b":"T-TR2","atom/H1c":"T-OR2","atom/H4a":"T-AW6","atom/H7":"T-PR6","atom/H8a":"T-OR2","atom/H8e":"NEW-OUT-outcome","atom/H9a":"T-AW3","atom/H9b":"T-RF2","atom/H10":"T-OR2","atom/H11":"T-RF2",
 "atom/H15a":"T-FM2","atom/H15b":"NEW-CS-intra-artifact","atom/H15c":"NEW-CS-intra-artifact","atom/H15d":"T-FM2","atom/H17":"T-OR2","atom/S4.tags":"T-FM2",
}
# form/S*.<field>  -> T-FM2 (per field)
for k in M:
    if k.startswith("form/S") and k not in MAP: MAP[k] = "T-FM2"
    if k.startswith("judge/"): MAP[k] = "NEW-Q-content (judge)"
missing = [k for k in M if k not in MAP]; extra = [k for k in MAP if k not in M]
print("methods", len(M), "mapped", len([k for k in M if k in MAP]), "missing", missing, "extra", extra)
T = yaml.safe_load(open("/tmp/claude-6025/-vast-ib-MMI-home-kyuminkim-project-if-rllm/f07c07ab-b634-40a5-9927-dbb066a1b29d/scratchpad/templates_branch.yaml"))["templates"]
def grp(t):
    if t.startswith("NEW-Q"): return "judge (Q)"
    if t.startswith("NEW"): return "new template needed"
    return "existing, with eval layer" if "eval" in T.get(t,{}) else "existing, no eval layer"
# count by method and by judgment (per-stage keys)
cm=collections.Counter(); cj=collections.Counter(); per=collections.defaultdict(list)
for k,m in M.items():
    t=MAP[k]; g=grp(t); cm[g]+=1; cj[g]+=len(m.keys()); per[(g,t)].append(k)
print("\nby method:", dict(cm)); print("by judgment (stage-expanded):", dict(cj))
print()
for (g,t),ks in sorted(per.items(), key=lambda x:(x[0][0],x[0][1])):
    layer=(T.get(t,{}).get("eval") or {}).get("layer","-")
    print(f"{g:28s} {t:34s} L={layer:4s} n={len(ks):3d}  {', '.join(sorted(ks))[:150]}")
yaml.safe_dump({k:MAP[k] for k in sorted(MAP)}, open("eval_method_templates.yaml","w"), allow_unicode=True, sort_keys=True)
