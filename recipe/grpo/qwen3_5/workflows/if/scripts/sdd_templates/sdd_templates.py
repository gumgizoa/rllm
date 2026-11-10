"""speckit_sdd rubric items -> sdlc_if templates (T-*), the way 01_template_layer.md classified the four
study workflows: template = kind + logic-selecting params (+ window anchor). Common kinds follow the
signature dictionary of the four constraints.yaml files; speckit_sdd's own kinds (speckit_sdd.*, speckit.*)
are assigned per rule from their judging logic (reward/checks.py, reward/speckit_kinds.py).

    python3 sdd_templates.py sdd_assignment.yaml      # writes the per-item assignment; prints the SDD vs SKB table
"""
import yaml, collections, re, sys
W = "/vast-ib/MMI/home/kyuminkim/project/if/rllm/recipe/grpo/qwen3_5/workflows"
sdd = yaml.safe_load(open(f"{W}/speckit_sdd/reward/rubric.yaml"))["items"]
cat = yaml.safe_load(open(f"{W}/../sdlc_if/templates.yaml"))["templates"]

def assign(it):
    """(template, basis). basis: 'dict' = the four workflows' signature dictionary decides;
    'rule' = assigned from the kind's judging logic; 'heur' = item_format single-line vs repeated-item."""
    k = it["check"]["kind"]; p = it["check"].get("params") or {}; i = it["id"]
    if k == "unimplemented": return None, "unimplemented"
    # --- common kinds, unambiguous in the dictionary
    if k == "artifact_exists": return "T-FM1", "dict"
    if k in ("section_present", "label_present", "field_enum"): return "T-FM2", "dict"
    if k == "no_template_residue": return "T-FM4", "dict"
    if k == "doc_read_first": return "T-RD1", "dict"
    if k == "field_filled":
        if "per_block" in p: return "T-FM6", "dict"
        return "T-FM2", "dict"          # none_vocab=['N/A'] on Storage is an allowed value, not a run-refutable claim
    if k == "doc_read":
        return ("T-RD2", "dict") if p.get("single_doc") else ("T-RD5", "dict")   # stage document vs constitution/template file
    if k == "speckit.read": return "T-RD4", "dict"
    if k == "prohibited_action":
        a = p.get("action")
        if a == "repo_write": return ("T-PR2", "dict") if "pattern" in p else ("T-AW1", "dict")
        return {"command": "T-PR6", "install": "T-PR3", "test_file_write": "T-PR1"}[a], "dict"
    if k == "speckit_sdd.created_files": return ("T-PR1", "dict") if p.get("test_paths") else ("T-PR2", "dict")
    if k == "speckit_sdd.paths_written": return "T-WD3", "dict"
    if k == "speckit_sdd.no_fetch": return "T-PR4", "dict"
    if k == "speckit_sdd.links": return "T-FM8", "dict"
    if k == "exec_evidence":
        return ("T-AW2", "dict") if i.endswith("baseline") else ("T-AW3", "dict")
    if k == "order": return "T-OR1", "dict"      # round_1 also carries invalidate=read_ahead (T-RD3, counted as '(order)')
    if k == "write_discipline": return "T-WD2", "rule"   # mode=append_only: no rewrite of the earlier artifact (variant of no_rewrite)
    if k == "cross_ref": return "T-TR1", "dict"  # set relation between two artifacts' ids
    # --- speckit_sdd's own kinds, by judging logic
    if k == "speckit.holds":
        n = i.rsplit(".", 1)[1]
        if n in ("code_change",): return "T-AW1", "rule"                       # an edit inside the allowed stage (polarity is instance-level)
        if n == "tests_pass": return "T-AW3", "rule"                            # the last test run after the last edit has no failure
        if n in ("at_most_two_rounds", "no_round_after_converged"): return "T-OR2", "rule"
        return "T-WD4", "rule"   # no_tasks_yet, *_written_by_*, report_written_once_per_round, tasks_unchanged_when_converged: no write to an artifact outside its stage
    if k == "speckit_sdd.script": return "T-AW5", "rule"   # the shipped CLI script ran, with its args, inside the window
    if k == "speckit_sdd.untouched": return "T-WD3", "rule" # no write lands under the shipped trees (same logic as paths_written)
    if k == "speckit_sdd.feature_json": return "T-RF4", "rule"   # the recorded feature_directory resolves to the real spec directory
    if k == "speckit_sdd.plan_docs":
        return ("T-RF3", "rule") if p["rule"] == "contracts" else ("T-FM2", "rule")   # tree lists the files written | 'N/A — reason' body
    if k == "speckit.task_lines":
        r = p["rule"]
        if r in ("story_label", "no_story_label", "parallel_files"): return "NEW-FM-internal", "rule"  # a line's label/file against its own phase
        if r == "story_tasks": return "T-FM6", "rule"
        if r == "phase_order": return "T-FM3", "rule"
    if k == "speckit_sdd.tasks":
        r = p["rule"]
        if r in ("ticked", "ticked_after_work"): return "T-PG1", "rule"
        if r == "later_edits": return "T-WD4", "rule"
        if r == "appended": return "T-OR1", "rule"          # the Convergence phase is appended after the round report is written
        if r == "convergence_phase": return "NEW-FM-internal", "rule"   # phase number = highest + 1
        if r == "convergence_lines": return "T-FM3", "rule"
        if r == "story_tests": return "T-FM6", "rule"
        if r == "empty_phases": return "T-FM2", "rule"
    if k == "speckit_sdd.report":
        r = p["rule"]
        if r == "findings": return "T-FM6", "rule"
        if r == "outcome_rows": return "NEW-FM-internal", "rule"   # Outcome value against the findings table of the same report
        if r == "converged_line": return "T-FM2", "rule"
    if k == "speckit_sdd.checks":
        r = p["rule"]
        if r == "written": return "T-WD3", "rule"
        if r in ("before_code", "red_green"): return "T-AW2", "rule"   # red_green: seen failing before the first code edit (and passing after)
        if r == "pass_last": return "T-AW3", "rule"
    if k == "item_format":
        if i.endswith("clarifications_resolved"): return "T-FM4", "heur"     # no [NEEDS CLARIFICATION] left
        if i.endswith("unchecked_when_written"): return "T-PG1", "heur"      # no box ticked when tasks.md is written
        if "of_pattern" in p or "sequence" in p or p.get("min", 1) > 1 or p.get("max") == 0: return "T-FM3", "heur"
        return "T-FM2", "heur"
    return "UNMAPPED", "none"

rows = []
for it in sdd:
    t, b = assign(it)
    rows.append({"id": it["id"], "kind": it["check"]["kind"], "requirement": it["requirement"], "stage": it["stage"], "template": t, "basis": b})
yaml.safe_dump(rows, open(sys.argv[1], "w"), sort_keys=False, allow_unicode=True)

sdd_n = collections.Counter(r["template"] for r in rows if r["template"])
sdd_req = collections.defaultdict(collections.Counter)
for r in rows:
    if r["template"]: sdd_req[r["template"]][r["requirement"]] += 1
skb = collections.Counter(str(c["template"]) for c in yaml.safe_load(open(f"{W}/speckit_bug/constraints.yaml"))["constraints"] if c["status"] == "implemented")
order = [t for t in cat] + ["NEW-FM-internal", "UNMAPPED"]
skill = {t: cat[t]["skill"] for t in cat}; skill["NEW-FM-internal"] = "S10"
print("| 기술 | 템플릿 | 내용 | SDD | SDD must/should | SKB |")
print("|---|---|---|---|---|---|")
tot_s = tot_b = 0
for t in order:
    if not (sdd_n.get(t) or skb.get(t)): continue
    name = cat.get(t, {}).get("name", "artifact-internal consistency (11 문서 NEW-FM-internal)")
    ms = sdd_req[t]
    print(f"| {skill.get(t,'')} | {t} | {name} | {sdd_n.get(t,0) or ''} | {ms['must']}/{ms['should']} | {skb.get(t,0) or ''} |")
    tot_s += sdd_n.get(t, 0); tot_b += skb.get(t, 0)
print(f"| | | **합계 (구현된 항목)** | **{tot_s}** | | **{tot_b}** |")
print("\nbasis:", dict(collections.Counter(r["basis"] for r in rows)))
un = [r for r in rows if r["basis"] == "unimplemented"]
print("unimplemented:", len(un))
