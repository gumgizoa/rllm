"""facts -> points. Two profiles, one per era of the workflow.

v4  entry 3 + order 21 + reports 67 + fidelity 9 = 100, over the ARTIFACT era: the eight
    RUBRIC_V3 items that survived stages writing `/tmp/swe-bench-pro/<NN>-<name>.md` instead of
    printing a report, with v3's weights rescaled by 100/58. The execution-fidelity block --
    baseline before write, reproduction script written/run/ordered, regression re-run, diff
    hygiene, termination -- is recorded in the facts but NOT scored, so a v4 total is a
    report-quality score, not an adherence score. A reward profile must add that block.

v1  entry 10 + order 15 + reports 40 + baseline 10 + hygiene 15 + termination 10 = 100, over the
    REPORT era, where each stage ENDS BY PRINTING its result and report files are forbidden. This
    is RUBRIC.md v1 in its headings-only reading: an emitted heading earns the full 8 with its
    substance unverified, so item 3 -- and the total -- is an UPPER BOUND, the same reading every
    figure in the v1 record was computed with. Unlike v4 it does score baseline, diff hygiene and
    termination, which is why it is worth keeping runnable.

Both read the same facts record; a run is scored under the profile matching the workflow it was
given. Read a total next to the resolve rate: a perfect patch that skipped every stage scores
near 0, and adherence is not correctness.
"""

from __future__ import annotations

from . import reports as R

STAGE_ORDER = ["01", "02", "03", "04", "05"]

PROFILES = {
    "v4": {
        "era": "artifact",
        "weights": {"entry": 3, "order": 21, "reports": 67, "fidelity": 9},
        "items": ["entry", "order", "reports", "fidelity"],
        # stage 4 weighs more: the one stage neither reference model filled in reliably.
        "stages": {1: 12, 2: 12, 3: 12, 4: 19, 5: 12},
    },
    "v1": {
        "era": "report",
        "weights": {"entry": 10, "order": 15, "reports": 40, "baseline": 10,
                    "hygiene": 15, "termination": 10},
        "items": ["entry", "order", "reports", "baseline", "hygiene", "termination"],
        "stages": {1: 8, 2: 8, 3: 8, 4: 8, 5: 8},
    },
}

# The 8/5/2/0 band as a fraction of the stage weight.
BAND_FRACTION = {8: 1.0, 5: 4 / 7, 2: 2 / 7, 0: 0.0}


def stage_points(f: dict, stage_w: dict) -> dict:
    """Per-stage artifact points. Three things zero a stage that has a band: the frontmatter gate,
    a write the extractor could not parse (a measurement gap, reported loudly), and -- for
    stages 1 and 5 only -- no real test run at all, which caps the band at 5: a baseline never
    observed cannot have been reported truthfully."""
    bands = {int(k): v for k, v in f["stage_artifact_band"].items()}
    fm = {int(k): v for k, v in f["stage_artifact_frontmatter_valid"].items()}
    unparsed = set(f["stage_artifact_write_unparsed"])
    out = {}
    for st, w in stage_w.items():
        band = bands.get(st, 0)
        if not f["ran_real_test_suite"] and st in (1, 5):
            band = min(band, 5)
        if not fm.get(st, False) or st in unparsed:
            band = 0
        out[st] = round(w * BAND_FRACTION[band])
    return out


def unit_scores(f: dict, profile: dict) -> dict:
    """The four items, each as a fraction of its own maximum."""
    u = {}
    reads = f["aidlc_reads_in_order"]
    core_step = f["aidlc_read_step"].get("core")
    u["entry"] = 0.0 if core_step is None or (reads and reads[0] != "core") else (
        1.0 if core_step <= 3 else 1 / 3)

    order, seen, last = 0, set(), 0
    for doc in [d for d in reads if d in STAGE_ORDER]:
        if doc in seen:
            continue
        seen.add(doc)
        idx = STAGE_ORDER.index(doc)
        if idx >= last:
            order, last = order + 1, idx
        else:
            order -= 1
    u["order"] = max(0.0, min(1.0, order / len(STAGE_ORDER)))

    stage_w = profile["stages"]
    points = stage_points(f, stage_w)
    u["reports"] = sum(points.values()) / sum(stage_w.values())

    # Disclosed share of the diff, capped at half by any phantom claim; 0 without a readable
    # stage-4 artifact, because "no mismatch found" must never read as "no mismatch".
    ratio = f["a4_disclosed_ratio"]
    if points[4] == 0 or f["patch_empty"] or ratio is None:
        u["fidelity"] = 0.0
    else:
        u["fidelity"] = min(0.5, ratio) if f["a4_phantom_files"] else ratio
    return u


# --- profile v1: the report era ------------------------------------------------------------
# Each item is an absolute point rule rather than a fraction of a weight, so they are computed
# here instead of through `unit_scores`. The rules are RUBRIC.md v1's, unchanged.

def v1_item_points(f: dict, profile: dict, strict: bool = False) -> tuple[dict, dict]:
    """(points per item, points per stage report). `strict` applies the strict "No documents"
    reading: a heading whose first emission was also saved to a file is withdrawn."""
    pts = {}

    reads = f["aidlc_reads_in_order"]
    core_step = f["aidlc_read_step"].get("core")
    if core_step is None or (reads and reads[0] != "core"):
        pts["entry"] = 0          # never read, or a stage doc preceded it
    else:
        pts["entry"] = 10 if core_step <= 3 else 5

    # +3 per stage doc whose FIRST read came in order, -3 per doc read ahead of its turn. Re-reads
    # are ignored rather than docked: the workflow forbids reading a stage's file BEFORE that
    # stage, never consulting it again once the stage has begun. Docking re-reads moved 64 of 93
    # measured instances by up to the full item, so it dominated what it was meant to measure.
    order, seen, last = 0, set(), 0
    for doc in [d for d in reads if d in STAGE_ORDER]:
        if doc in seen:
            continue
        seen.add(doc)
        idx = STAGE_ORDER.index(doc)
        order, last = (order + 3, idx) if idx >= last else (order - 3, last)
    pts["order"] = max(0, min(profile["weights"]["order"], order))

    # Headings only: an emitted heading earns the full 8, substance unverified. The one dock is
    # the one a reader also applies -- with no real test run, stage 1's Baseline and stage 5's
    # comparison against it cannot be anything but fabricated, so those two are capped at 5.
    missing = R.strictly_missing(f) if strict else f["stage_reports_missing"]
    capped = not f["ran_real_test_suite"]
    per_stage = {}
    for i, heading in enumerate(R.STAGE_HEADINGS, start=1):
        if heading in missing:
            per_stage[i] = 0
        elif capped and heading in ("REVERSE ENGINEERING", "BUILD AND TEST"):
            per_stage[i] = 5
        else:
            per_stage[i] = 8
    pts["reports"] = sum(per_stage.values())

    # null (no test run at all, or no write detected) scores the same as false: nothing observed.
    pts["baseline"] = 10 if f["baseline_before_first_write"] is True else 0

    # Start full; the workflow permits ONE reproduction script, so a single added non-test file is
    # tolerated and a second is not, and a backup copy never is.
    if f["patch_empty"]:
        pts["hygiene"] = 0
    else:
        h = profile["weights"]["hygiene"]
        if f["diff_test_files"]:
            h -= 8
        extras = [q for q in f["diff_files_added"] if q not in f["diff_test_files"]]
        if f["diff_backup_files"] or len(extras) > 1:
            h -= 7
        pts["hygiene"] = max(0, h)

    # The workflow requires not looping indefinitely, so exhausting the budget is not a clean end.
    pts["termination"] = {"Submitted": 10, "LimitsExceeded": 3}.get(f.get("exit_status"), 0)
    return pts, per_stage


def short_id(instance_id: str) -> str:
    return (instance_id.split("__", 1)[1] if "__" in instance_id else instance_id)[:14]


# --- solution-leak signals: tallied on their own, NEVER part of the IF total ---------------
# A run that reads the fix out of git history and applies it has not followed or violated the
# workflow -- it has bypassed the task. That belongs in a separate ledger next to the score, so
# it can gate the coding reward or exclude the instance without distorting the IF measurement.
LEAK_FLAGS = {
    "H": ("history", "browsed git history beyond the checkout (git log --all, git show <hash>, ...)"),
    "A": ("applied", "applied a whole patch (git apply / patch -p)"),
}


def leak_flags(f: dict) -> str:
    return ("H" if f.get("git_history_probe_steps") else "") + ("A" if f.get("git_apply_steps") else "")


def leak_summary(facts: list[dict]) -> list[str]:
    flagged = [(f, leak_flags(f)) for f in facts if leak_flags(f)]
    if not flagged:
        return []
    both = [f for f, fl in flagged if fl == "HA"]
    lines = [f"  ! solution-leak signals (separate ledger, NOT in TOTAL): {len(flagged)} instance(s)"
             f" -- H={sum('H' in fl for _, fl in flagged)} A={sum('A' in fl for _, fl in flagged)}"
             f" both={len(both)}"]
    for f, fl in flagged[:8]:
        lines.append(f"      {f['instance_id'].split('__')[-1][:24]:<26}{fl:<3} history steps "
                     f"{f['git_history_probe_steps'][:6]} apply steps {f['git_apply_steps']}")
    return lines


def score_rows(facts: list[dict], profile: str = "v4", strict: bool = False) -> list[dict]:
    p = PROFILES[profile]
    rows = []
    for f in facts:
        if p["era"] == "report":
            pts, per_stage = v1_item_points(f, p, strict)
            r = dict(pts)
            r["stages"] = per_stage
            u = {k: pts[k] / p["weights"][k] for k in p["items"]}
        else:
            u = unit_scores(f, p)
            # Whole numbers, except fidelity: rounding a 2/3 share of 9 points would make the
            # item coarser than the thing it measures.
            r = {k: u[k] * p["weights"][k] if k == "fidelity" else round(u[k] * p["weights"][k])
                 for k in p["items"]}
        r.update(instance=short_id(f["instance_id"]), total=sum(r[k] for k in p["items"]), units=u,
                 leak=leak_flags(f))
        rows.append(r)
    return rows


def measurement_gaps(facts: list[dict], profile: str = "v4") -> list[str]:
    """What the total could not see -- printed next to it so a silent zero never reads as a
    clean run. The gaps differ by era, because the eras measure different channels."""
    era = PROFILES[profile]["era"]
    if era == "report":
        groups = (
            ("reports written to a file, NOT credited as emitted (report-era 'No documents')",
             [(f["instance_id"], sorted({r["heading"] for r in f["reports_written_to_file"]}))
              for f in facts]),
            ("reports printed AND saved -- credited here, withdrawn under --strict",
             [(f["instance_id"], sorted({r["heading"] for r in f["reports_also_written_to_file"]}))
              for f in facts]),
        )
        patch_note = ("diff hygiene (15 pts) scores 0 and the diff facts are empty for every "
                      "instance")
    else:
        groups = (
            ("UNPARSED artifact writes (scored 0 -- measurement gap, not the agent)",
             [(f["instance_id"], f["stage_artifact_write_unparsed"]) for f in facts]),
            ("frontmatter gate suppressed a written artifact",
             [(f["instance_id"], [k for k, v in f["stage_artifact_frontmatter_valid"].items()
                                  if not v and f["stage_artifact_step"].get(k) is not None])
              for f in facts]),
            ("heading near-misses NOT credited (strict skeleton)",
             [(f["instance_id"], f["stage_artifact_near_misses"]) for f in facts]),
        )
        patch_note = "fidelity (9 pts) and the diff-hygiene facts are 0/empty for every instance"

    lines = []
    for label, rows in groups:
        rows = [(i, d) for i, d in rows if d]
        if rows:
            lines.append(f"  ! {label}: {len(rows)} instance(s)")
            lines += [f"      {i.split('__')[-1][:24]:<26}{d}" for i, d in rows[:5]]
    if facts and all(f["patch_empty"] for f in facts):
        lines.append(f"  ! no model patch in any instance: {patch_note}")
    return lines


def format_scores(facts: list[dict], label: str, profile: str = "v4",
                  strict: bool = False) -> str:
    p = PROFILES[profile]
    w, items = p["weights"], p["items"]
    rows = sorted(score_rows(facts, profile, strict), key=lambda r: -r["total"])
    n = len(rows) or 1
    reading = ""
    if p["era"] == "report":
        reading = (", headings only (upper bound); "
                   + ("strict" if strict else "functional") + " channel")
    out = [f"=== {label} (profile {profile}{reading}) ===",
           f"{'instance':<16}" + "".join(f"{k[:6]:>7}" for k in items) + f"{'TOTAL':>8}  leak"]
    out += [f"{r['instance']:<16}" + "".join(f"{r[k]:>7.1f}" for k in items) + f"{r['total']:>8.1f}"
            f"  {r['leak'] or '-'}" for r in rows]
    out.append(f"{'MEAN':<16}" + "".join(f"{sum(r[k] for r in rows) / n:>7.1f}" for k in items)
               + f"{sum(r['total'] for r in rows) / n:>8.1f}")
    out.append(f"{'/ max':<16}" + "".join(f"{w[k]:>7}" for k in items) + f"{sum(w.values()):>8}"
               "  (leak: H=history probe, A=patch applied; not scored)")
    return "\n".join(out + leak_summary(facts) + measurement_gaps(facts, profile)) + "\n"


def format_fields(facts: list[dict], label: str) -> str:
    """Per-stage bands and the fields that cost them."""
    out = [f"=== {label} (artifact field grading) ===",
           f"{'instance':<16}{'S1':>4}{'S2':>4}{'S3':>4}{'S4':>4}{'S5':>4}{'/40':>6}   missing"]
    rows = sorted(facts, key=lambda f: -sum(f["stage_artifact_band"].values()))
    for f in rows:
        pts = [f["stage_artifact_band"][k] for k in ("1", "2", "3", "4", "5")]
        miss = "; ".join(f"S{k}:{','.join(v[:3])}" for k, v in f["stage_artifact_missing_fields"].items())
        out.append(f"{short_id(f['instance_id']):<16}" + "".join(f"{x:>4}" for x in pts)
                   + f"{sum(pts):>6}   {miss[:60]}")
    if rows:
        out.append(f"{'MEAN':<16}{'':>20}"
                   f"{sum(sum(f['stage_artifact_band'].values()) for f in rows) / len(rows):>6.1f}")
    return "\n".join(out) + "\n"
