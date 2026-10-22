"""Atomic checks: the workflow's atomic rules the other checks left unscored, where code can judge them.

Each check is named after the atomic rule it judges (``categories.ATOM_KINDS`` places it) and is 1 (kept)
/ 0 (broken) / None (nothing bears on it). Rules that hold per artifact are scored per stage, as
``<rule>@<stage>``. Emitted as ``aidlc/atom/<rule>[@<stage>]``; logged only, like the content checks.

    form         B5d skeleton sentences kept, B6b/B6c frontmatter values, D5/F2a full paths, D12b one test id
                 per line, E4a one sequence R1..Rn, E8c edge items "condition -> behaviour", F1b steps 1..n,
                 F2b "(modify in place | create)", G8b deviations classified, S4.tags requirement tags, H15a
                 allowed values, H15d "test id -> ..." items
    consistency  G3c planned creations made, H1a/H4a stage 5 reruns stage 1's build and test selection,
                 H15b verdict vs regressions, H15c unmet requirements vs the reproduction result
    execution    H8a a failing reproduction is followed by a source fix, H8e no regression left unfixed,
                 H9a a stage-5 fix is re-verified
    forbidden    B10 no design/report document, E10a no question file, F7 no step on a test file, F8a/F8b
                 no create over an existing file or duplicate variant, G4b no new test file in the
                 repository, C2 no stage document re-read after its stage closed
    content      D1b files the issue names are in scope, D4a language
                 matches the files, D7b the test command names targets, E7b no non-functional requirement
                 the task does not state, F4b the reproduction exercises the edge-case requirements
"""

from __future__ import annotations

import re

from . import evidence as EV
from ._claims import DUPLICATE, Observed, bullets, claimed_paths, command_core, failures, is_none, norm_path, r_ids, same_file, task_text
from ._claims import field_value as claims_field_value
from .rubric import artifacts as A
from .rubric import facts as F

_LITERALS = {1: ["Recorded before any source file was modified."], 4: ["- Executed: no"]}
_TEST_LIKE = re.compile(r"::|\btest_\w+|\w+ \([\w.]+\)|\.[Tt]est\w*\b")
_ARROW = re.compile(r"->|→")
_R_LINE = re.compile(r"^\s*[-*+]\s*\*{0,2}(R\d+)\*{0,2}\s*:\s*(.*)$", re.M)
_ISSUE_PATH = re.compile(r"(?<![\w/.-])((?:[\w-]+/)+[\w.-]+\.(?:py|pyi|js|ts|go|rs|java|rb|c|h|cpp|cfg|toml|ini))\b")
_PERF = re.compile(r"\b(?:performance|slow(?:er|ly)?|fast(?:er)?|speed|memory|complexity|efficien\w*|latency|O\(|quadratic|linear time|time-?out)\b", re.I)
_LANG = {"py": "python", "pyi": "python", "js": "javascript", "ts": "typescript", "go": "go", "rs": "rust", "java": "java", "rb": "ruby", "c": "c", "h": "c", "cpp": "c++"}
_DOC = re.compile(r"\.(?:md|rst)$|(?:^|/)[^/]*(?:plan|summary|report|notes|design)[^/]*\.(?:md|txt|rst)$", re.I)


def _field(p, section, label):
    return claims_field_value((p or {}).get("section_bodies", {}).get(section) or "", label) or None


def _lines(value: str) -> list[str]:
    """A field's items, one per line (a field value's continuation lines are joined by spaces, so a
    multi-item value reads as one line: "one per line" is then not kept)."""
    return [x.strip(" -*`") for x in re.split(r"\n+", value or "") if x.strip(" -*`")]


def _frac(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None


def atomic_checks(run, obs: Observed, parsed: dict, read_step: dict, write_step: dict, facts: dict, patch: str | None, task=None, test_files=()) -> dict[str, float | None]:
    c: dict[str, float | None] = {}
    final = EV.patch_files(patch)
    known = {norm_path(p) for p in [*obs.viewed, *obs.edited, *obs.created, *(final[0] if final else [])]}
    p1, p2, p3, p4, p5 = (parsed.get(k) for k in range(1, 6))

    def full_paths(paths: list[str]) -> float | None:
        verdicts = []
        for p in paths:
            q = norm_path(p)
            if q in known:
                verdicts.append(True)
            elif "/" not in q and any(k.rsplit("/", 1)[-1] == q and "/" in k for k in known):
                verdicts.append(False)
        return _frac(verdicts)

    repro = next((p for st in (4, 3) if parsed.get(st) for p in claimed_paths(_field(parsed[st], "Reproduction Script", "Path"))), None)
    repro_paths = [p for st in (3, 4) if parsed.get(st) for p in claimed_paths(_field(parsed[st], "Reproduction Script", "Path"))]

    def is_repro(path: str) -> bool:
        return any(same_file(path, q) for q in repro_paths)

    # -- form, per artifact ---------------------------------------------------------------
    for st, p in parsed.items():
        if p is None:
            continue
        fm = p["frontmatter"]
        if fm["present"]:
            c[f"B6b@{st}"] = float((fm["stage"] or "").strip() == str(st))
            c[f"B6c@{st}"] = float((fm["name"] or "").strip() == A.STAGE_FILES[st][1])
        if st in _LITERALS:
            c[f"B5d@{st}"] = float(all(lit in p["body"] for lit in _LITERALS[st]))
    if p1:
        c["D5"] = full_paths(claimed_paths(_field(p1, "Affected Scope", "Files")) + claimed_paths(_field(p1, "Existing Tests", "Path")))
        ids = [x for k in ("Passing", "Failing") if (v := _field(p1, "Baseline", k)) and not is_none(v) for x in _lines(v)]
        c["D12b"] = float(all(_TEST_LIKE.search(x) for x in ids)) if ids else None
    if p2:
        seq = list(dict.fromkeys(p2.get("r_ids", [])))
        c["E4a"] = float(seq == [f"R{i}" for i in range(1, len(seq) + 1)]) if seq else None
        edge = p2["section_bodies"].get("Edge Cases & Error Handling") or ""
        lines = [v for _, v in _R_LINE.findall(edge) if not is_none(v)]
        c["E8c"] = _frac([bool(_ARROW.search(v)) for v in lines])
    steps = (p3 or {}).get("steps", [])
    if steps:
        c["F1b"] = float([s["n"] for s in steps] == list(range(1, len(steps) + 1)))
        targets = [s["fields"].get("Target") or "" for s in steps]
        c["F2a"] = full_paths([t for v in targets for t in claimed_paths(v)])
        c["F2b"] = _frac([bool(re.search(r"\(\s*(?:modify in place|create)\s*\)", v, re.I)) for v in targets])
    if p4:
        dev = [x for x in bullets(p4["section_bodies"].get("Deviations from Plan")) if not is_none(x)]
        c["G8b"] = _frac([bool(re.match(r"(?:local correction|structural invalidation)\b", x, re.I)) for x in dev])
        claims = [m.group(2) for m in re.finditer(r"^\s*[-*+]\s*\*{0,2}(Modified|Created)\*{0,2}\s*:\s*(.*)$", p4["section_bodies"].get("Changed Files") or "", re.M | re.I)]
        c["S4.tags"] = _frac([bool(re.search(r"\[\s*R\d+", v)) for v in claims if v.strip() and not is_none(v) and not A.PLACEHOLDER.fullmatch(v.strip())])
    if p5:
        allowed = {
            ("Build", "Result"): ("success", "failure"),
            ("Reproduction Script", "Result"): ("pass", "fail"),
            ("Existing Tests vs Baseline", "Verdict"): ("unchanged", "regression resolved", "pre-existing failures only"),
        }
        vals = [(v.lower().strip(" .`*"), ok) for (sec, lab), ok in allowed.items() if (v := _field(p5, sec, lab))]
        c["H15a"] = _frac([v.startswith(ok) for v, ok in vals])
        entries = [v for k in ("Regressions", "Pre-existing failures") if (v := _field(p5, "Existing Tests vs Baseline", k)) and not is_none(v)]
        c["H15d"] = _frac([bool(_ARROW.search(v)) for v in entries])

    # -- consistency ----------------------------------------------------------------------
    if steps and final is not None:
        made = {norm_path(p) for p in final[1]} | {norm_path(p) for p in obs.created}
        planned = [t for s in steps if re.search(r"\(\s*create\s*\)", s["fields"].get("Target") or "", re.I) for t in claimed_paths(s["fields"].get("Target"))]
        c["G3c"] = _frac([any(same_file(t, m) for m in made) for t in planned])
    if p1 and p5:
        b1, b5 = _field(p1, "Build & Test Commands", "Build"), _field(p5, "Build", "Command")
        if b1 and b5 and not is_none(b1) and not is_none(b5):
            c["H1a"] = float(command_core(b1) == command_core(b5))
        t1, t5 = EV.test_targets(_field(p1, "Build & Test Commands", "Test") or ""), EV.test_targets(_field(p5, "Existing Tests vs Baseline", "Command") or "")
        if t1 and t5:
            # The baseline's selection rerun: every stage-1 target is covered by a stage-5 one (the same, or
            # a file / class / module that holds it). A narrower rerun is not comparable to the baseline.
            def covered(t: str) -> bool:
                return any(t == u or t.startswith(u.rstrip("/") + sep) for u in t5 for sep in ("::", ".", "/"))

            c["H4a"] = float(all(covered(t) for t in t1))
    if p5:
        verdict = (_field(p5, "Existing Tests vs Baseline", "Verdict") or "").lower()
        reg, pre = _field(p5, "Existing Tests vs Baseline", "Regressions"), _field(p5, "Existing Tests vs Baseline", "Pre-existing failures")
        if verdict:
            if verdict.startswith("unchanged"):
                # unchanged from a baseline that may itself have failed: only a regression contradicts it
                c["H15b"] = float(is_none(reg)) if reg else None
            elif verdict.startswith("pre-existing"):
                c["H15b"] = float(bool(pre) and not is_none(pre) and (not reg or is_none(reg)))
            elif verdict.startswith("regression"):
                c["H15b"] = float(bool(reg) and not is_none(reg))
        result, unmet = (_field(p5, "Reproduction Script", "Result") or "").lower(), _field(p5, "Reproduction Script", "Unmet requirements")
        if result and unmet:
            c["H15c"] = float(is_none(unmet)) if result.startswith("pass") else float(not is_none(unmet)) if result.startswith("fail") else None

    # -- execution in stage 5 -------------------------------------------------------------
    w4, w5 = write_step.get(4), write_step.get(5)
    edits_unseen = final is not None and any(
        q not in set(final[1]) and not EV.is_test_file(q, test_files) and re.search(r"\.(?:py|pyx|js|ts|go|rs|java|rb|c|h|cpp)$", q) and not any(same_file(q, e) for e in obs.edited) for q in final[0]
    )
    if repro and w4 is not None and not edits_unseen:
        runs = obs.ran(repro, after=w4, before=w5)
        failing = [n for n, cmd, out in runs if (code := EV.exit_code(cmd, out)) is not None and code != 0]
        if failing:
            # A failed reproduction is acted on: the source (or the script) changed and it ran again, or the
            # run closed. Moving on to the artifact with nothing done is what the rule forbids.
            acted = [n for p in [*obs.source_edits, repro] for n in obs.edit_steps.get(norm_path(p), []) + ([obs.written(repro)] if p == repro and obs.written(repro) else []) if n > failing[-1]]
            later_runs = [n for n, _, _ in runs if n > failing[-1]]
            c["H8a"] = float(bool(acted) or bool(later_runs))
    baseline = obs.tests_in(before=obs.first_edit) if obs.first_edit is not None else []
    post = obs.tests_in(after=obs.last_edit, before=w5) if obs.last_edit is not None else []
    if baseline and post:
        clean = all(failures(o) == 0 for _, _, o in baseline)
        c["H8e"] = 0.0 if clean and failures(post[-1][2]) > 0 else 1.0
    if w4 is not None:
        fixes = [n for p in obs.source_edits for n in obs.edit_steps.get(p, []) if n > w4 and (w5 is None or n < w5)]
        if fixes:
            last = max(fixes)
            rerun = obs.tests_in(after=last, before=w5) or (obs.ran(repro, after=last, before=w5) if repro else [])
            c["H9a"] = float(bool(rerun))

    # -- forbidden ------------------------------------------------------------------------
    c["B10"] = 0.0 if any(_DOC.search(p) and not p.startswith(A.ARTIFACT_DIR) for p in obs.created) else 1.0
    c["E10a"] = 0.0 if any(re.search(r"question", p.rsplit("/", 1)[-1], re.I) for p in obs.created) else 1.0
    if steps:
        # The plan's own reproduction script is no test file even when named test_*.py (left in the
        # repository, r_repo_clean catches it).
        targets = [t for s in steps for t in claimed_paths(s["fields"].get("Target")) if not is_repro(t)]
        if targets:
            c["F7"] = 0.0 if any(EV.is_test_file(norm_path(t), test_files) for t in targets) else 1.0
            c["F8b"] = 0.0 if any(DUPLICATE.search(t) or F.BACKUP_RE.search(t) for t in targets) else 1.0
        creates = [t for s in steps if re.search(r"\(\s*create\s*\)", s["fields"].get("Target") or "", re.I) for t in claimed_paths(s["fields"].get("Target"))]
        w3 = write_step.get(3)
        if creates:
            c["F8a"] = 0.0 if any(obs.seen(t, before=w3) for t in creates) else 1.0
    if final is not None:
        c["G4b"] = 0.0 if any(EV.is_test_file(norm_path(p), test_files) and not is_repro(p) for p in final[1]) else 1.0
    if any(write_step.values()):
        # A stage's rule document read again after the stage's artifact was written: the run went back.
        reread = [step.n for step in run.steps for a in step.actions for d in F.doc_reads(a) if d != "core" and write_step.get(int(d)) is not None and step.n > write_step[int(d)]]
        c["C2"] = 0.0 if reread else 1.0

    # -- content --------------------------------------------------------------------------
    issue = task_text(task) if task is not None else ""
    if p1:
        files = claimed_paths(_field(p1, "Affected Scope", "Files"))
        named = [p for p in dict.fromkeys(_ISSUE_PATH.findall(issue)) if norm_path(p) in known]
        c["D1b"] = _frac([any(same_file(p, f) for f in files) for p in named])
        # D3 (the owning module matches the files) is left to the judge: a name match is either too loose
        # (`django` passes any file) or too strict ("Django ORM", "matplotlib.widgets" for
        # lib/matplotlib/widgets.py fail), both seen on swebv100.
        exts = [f.rsplit(".", 1)[-1].lower() for f in files if "." in f.rsplit("/", 1)[-1]]
        langs = {_LANG[e] for e in exts if e in _LANG}
        lang = (_field(p1, "Affected Scope", "Language/framework") or "").lower()
        if langs and lang:
            c["D4a"] = float(any(re.search(rf"(?<![\w+]){re.escape(x)}(?![\w+])", lang) for x in langs))
        test = _field(p1, "Build & Test Commands", "Test")
        if test and not is_none(test) and (targets := EV.test_targets(test)) is not None:
            c["D7b"] = float(bool(targets))
    if p2:
        nfr = p2["section_bodies"].get("Non-Functional Requirements")
        if nfr is not None and issue:
            r_lines = _R_LINE.findall(nfr)
            stated = [v for _, v in r_lines if not is_none(v)] if r_lines else [x for x in bullets(nfr) if not is_none(x)]
            c["E7b"] = 1.0 if not stated else (None if _PERF.search(issue) else 0.0)
        edge_ids = r_ids(p2["section_bodies"].get("Edge Cases & Error Handling"))
        real = [r for r in edge_ids if not any(rid == r and is_none(v) for rid, v in _R_LINE.findall(p2["body"]))]
        exercises = r_ids(_field(p3, "Reproduction Script", "Exercises")) if p3 else []
        if real and p3:
            c["F4b"] = _frac([r in exercises for r in real])
    return c
