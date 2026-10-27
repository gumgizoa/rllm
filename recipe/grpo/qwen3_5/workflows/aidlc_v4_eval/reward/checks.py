"""aidlc_v4_eval's check kinds for ``rubric.yaml`` (the ``aidlc_v4_eval.*`` plugin kinds).

Every item reads one measurement of the run; the run is measured once (:func:`measure`, cached on the
evaluation context) from the task, the recorded episode and the collected artifacts, by the readings in
``read.py`` and the checks in ``claims.py`` / ``rules.py`` / ``judge.py``:

    aidlc_v4_eval.claim      a content check: an artifact's claim against the trajectory (claims.py)
    aidlc_v4_eval.rule       a rule check: what the run did, whatever its artifacts claim (rules.py)
    aidlc_v4_eval.atom       an atomic rule the other checks leave unscored (rules.py)
    aidlc_v4_eval.form       an artifact's form: present, frontmatter, headings, each skeleton field
    aidlc_v4_eval.procedure  a stage's procedure: its document read first, alone, before its artifact
    aidlc_v4_eval.run        a whole-run reading: entry, a real test run, the diff's disclosure (fidelity)
    aidlc_v4_eval.judge      an LLM's yes / no on a content rule code cannot decide (judge.py)

A measurement that does not apply (nothing bears on it) is ``not_applicable``; the judge's items are
``unavailable`` when no judge is configured, so their cells are no part of the matrix then.
"""

from __future__ import annotations

import re

from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

from . import read as EV
from . import skeleton as A
from .claims import CHECKS, content_checks
from .judge import judge_checks
from .read import artifact_write_steps, first_write_steps, observe, parsed_artifacts
from .read import field_value as claims_field_value
from .rules import ATOMIC, RULE_CHECKS, atomic_checks, rule_checks
from .trace import episode_to_run

# Skeleton fields, one rule each: rule -> (stage, section, label or None for the section's own content, none allowed)
FIELDS = {
    "S1.files": (1, "Affected Scope", "Files", False),
    "S1.module": (1, "Affected Scope", "Owning module", False),
    "S1.lang": (1, "Affected Scope", "Language/framework", False),
    "S1.build": (1, "Build & Test Commands", "Build", True),
    "S1.test": (1, "Build & Test Commands", "Test", False),
    "S1.tpath": (1, "Existing Tests", "Path", False),
    "S1.contract": (1, "Existing Tests", "Contract", False),
    "S1.passing": (1, "Baseline", "Passing", True),
    "S1.failing": (1, "Baseline", "Failing", True),
    "S2.fr": (2, "Functional Requirements", None, False),
    "S2.nfr": (2, "Non-Functional Requirements", None, True),
    "S2.edge": (2, "Edge Cases & Error Handling", None, False),
    "S2.assume": (2, "Assumptions", None, True),
    "S3.rpath": (3, "Reproduction Script", "Path", False),
    "S3.exercises": (3, "Reproduction Script", "Exercises", False),
    "S3.coverage": (3, "Requirement Coverage", None, False),
    "S4.modified": (4, "Changed Files", "Modified", False),
    "S4.created": (4, "Changed Files", "Created", True),
    "S4.rpath": (4, "Reproduction Script", "Path", False),
    "S4.executed": (4, "Reproduction Script", "Executed", False),
    "G9": (4, "Plan Execution", None, False),
    "S4.deviations": (4, "Deviations from Plan", None, True),
    "S4.dupcheck": (4, "Checks", "Duplicate files created", True),
    "S4.testcheck": (4, "Checks", "Test files modified", True),
    "S5.bresult": (5, "Build", "Result", False),
    "S5.bcmd": (5, "Build", "Command", False),
    "S5.rresult": (5, "Reproduction Script", "Result", False),
    "S5.unmet": (5, "Reproduction Script", "Unmet requirements", True),
    "S5.cmd": (5, "Existing Tests vs Baseline", "Command", False),
    "S5.verdict": (5, "Existing Tests vs Baseline", "Verdict", False),
    "S5.regress": (5, "Existing Tests vs Baseline", "Regressions", True),
    "S5.pre": (5, "Existing Tests vs Baseline", "Pre-existing failures", True),
    "S5.fixes": (5, "Fixes Applied", None, True),
    "S5.outstanding": (5, "Outstanding Failures", None, True),
    "S5.final_files": (5, "Final Change", "Files in the change", False),
    "S5.final_unintended": (5, "Final Change", "Unintended files in the repository", True),
    "S5.final_tests": (5, "Final Change", "Test files in the change", True),
}

STEP_FIELDS = {"S3.target": "Target", "S3.change": "Change", "S3.contract": "Contract", "S3.verify": "Verification"}


def _label_filled(body: str | None, label: str, allow_none: bool) -> bool:
    """One ``- Label: value`` field filled in, as the rubric's ``field_present`` reads a single label."""
    if body is None:
        return False
    val = claims_field_value(body, label)
    if val is None:  # `- Path: x — Contract: y` puts two labels on one line
        hit = re.search(rf"{re.escape(label)}\s*:\s*([^\n]*)", body, re.I)
        val = hit.group(1).strip(" *`") if hit else None
        if val is not None and A.PLACEHOLDER.fullmatch(val):
            val = ""
    return bool(val) and (allow_none or not A.NONE_VALUE.fullmatch(val))


def form_rules(parsed: dict) -> list[tuple[str, str, int, float]]:
    """Per-stage form rules from the collected artifacts: the frontmatter, the headings, every field."""
    out = []
    for st in A.STAGE_FILES:
        p = parsed.get(st)
        out.append(("B1", "F", st, 1.0 if p is not None else 0.0))
        if p is None:
            continue
        out.append(("B6a", "F", st, 1.0 if p["frontmatter"]["valid"] else 0.0))
        want = A.SECTIONS[st]["graded"] + A.SECTIONS[st]["extra"]
        out.append(("B5b", "F", st, sum(w in p["section_bodies"] for w in want) / len(want)))
    for rule, (st, section, label, allow_none) in FIELDS.items():
        p = parsed.get(st)
        if p is None:
            value = 0.0
        else:
            body = p["section_bodies"].get(section)
            value = float(_label_filled(body, label, allow_none) if label else (body is not None and A._section_has_content(body, allow_none)))
        out.append((rule, "F", st, value))
    p3 = parsed.get(3)
    steps = p3.get("steps", []) if p3 else []
    for rule, label in STEP_FIELDS.items():
        out.append((rule, "F", 3, float(bool(steps) and all(s["fields"].get(label) for s in steps))))
    out.append(("S3.tag", "F", 3, float(bool(steps) and all(s["tags"] for s in steps))))
    p2 = parsed.get(2)
    ids = p2.get("r_ids", []) if p2 else []
    out.append(("E3c", "F", 2, float(bool(ids))))
    out.append(("E4b", "F", 2, float(bool(ids) and len(set(ids)) == len(ids))))
    return out


def procedure_rules(read_step: dict, write_step: dict, invalid: set) -> list[tuple[str, str, int, float]]:
    """Per-stage procedure rules from the first reads of the rule documents and the first artifact writes."""
    out = []
    read = {k: read_step.get(f"0{k}") if f"0{k}" not in invalid else None for k in range(1, 6)}
    if any(f"0{k}" in read_step for k in range(1, 6)):
        out.append(("A3a", "P", 0, 1 - len(invalid) / 5))
    for k in range(1, 6):
        w, r, wprev = write_step.get(k), read[k], write_step.get(k - 1)
        # C1a: the stage was carried out, its document read (however) before its artifact; C1b: in order, its
        # artifact after the previous stage's (both written: a stage left out is C1a's)
        doc_read = read_step.get(f"0{k}") is not None and w is not None and read_step[f"0{k}"] < w
        out.append(("C1a", "P", k, 1.0 if doc_read else 0.0))
        if k > 1 and w is not None and wprev is not None:
            out.append(("C1b", "P", k, 1.0 if wprev < w else 0.0))
        if w is not None:  # the stage was done: was its document its first step?
            out.append(("A2", "P", k, 1.0 if r is not None and r < w and (wprev is None or r > wprev) else 0.0))
        if k > 1 and r is not None:  # no reading ahead of the previous stage's artifact
            out.append(("A3b", "P", k, 1.0 if wprev is not None and r > wprev else 0.0))
        if k < 5 and w is not None and read[k + 1] is not None:  # the artifact closes the stage
            out.append(("B3b", "P", k, 1.0 if w < read[k + 1] else 0.0))
    return out


# --- the keys a measurement can have -------------------------------------------------------------


def _measurable() -> frozenset[str]:
    """Every key :func:`measure` can set outside the judge's: an item naming another is a broken link,
    a measurement setting another is one no item reads. (Both raise: a missing key must not read as
    "not applicable" and drop out of every mean unnoticed.)"""
    stages = range(1, 6)
    form = [f"form/{r}@{k}" for r in ("B1", "B6a", "B5b") for k in stages]
    form += [f"form/{rule}@{st}" for rule, (st, *_) in FIELDS.items()] + [f"form/{rule}@3" for rule in [*STEP_FIELDS, "S3.tag"]]
    form += ["form/E3c@2", "form/E4b@2"]
    proc = ["proc/A3a@0", *(f"proc/{r}@{k}" for r in ("C1a", "A2") for k in stages), *(f"proc/{r}@{k}" for r in ("A3b", "C1b") for k in range(2, 6)), *(f"proc/B3b@{k}" for k in range(1, 5))]
    return frozenset([*(f"check/{k}" for k in CHECKS), *(f"rule/{k}" for k in RULE_CHECKS), *(f"atom/{k}" for k in ATOMIC), *form, *proc, "run/entry", "run/ran_real_test", "run/fidelity"])


MEASURABLE = _measurable()


# --- the run, measured once --------------------------------------------------------------------


def inputs(task, episode) -> dict:
    """``Collected.inputs``: what the checks read besides the sandbox."""
    return {"task": task, "episode": episode}


def measure(ctx: EvalContext) -> dict:
    """Every measurement of the run, keyed as the items name them (``check/<name>``, ``rule/<name>``,
    ``atom/<rule>[@<stage>]``, ``form/<rule>@<stage>``, ``proc/<rule>@<stage>``, ``run/<name>``,
    ``judge/<rule>``), plus the diagnostics ``post`` reports. Computed on first use, cached on ``ctx``."""
    if "aidlc" in ctx.cache:
        return ctx.cache["aidlc"]
    task, episode = ctx.collected.inputs["task"], ctx.collected.inputs["episode"]
    files = {p: t for p, t in ctx.collected.files.items() if p in A.ARTIFACT_PATHS}
    run = episode_to_run(episode, files, instance_id=str(getattr(task, "id", "") or ""))
    recorded = getattr(episode, "artifacts", None) or {}
    patch = recorded.get("patch")
    run.patch = patch or ""
    whole_patch = None if recorded.get("patch_truncated") else patch
    tests = EV.task_test_files(task)
    parsed = parsed_artifacts(run, collected=True)
    obs = observe(run)
    _, read_step = EV.doc_reads(run)
    writes = first_write_steps(run)
    cc = content_checks(run, parsed, obs=obs, patch=whole_patch, test_files=tests)
    rc = rule_checks(run, obs, parsed, read_step, writes, whole_patch, tests)
    # (what the artifact directory held at the end, beside the five artifacts: B11)
    art_dir = sorted(p for p in ctx.collected.files if p.startswith(A.ARTIFACT_DIR + "/"))
    ac = atomic_checks(run, obs, parsed, read_step, writes, {"art_dir_files": art_dir}, whole_patch, task, tests, final_words=EV.final_words(episode))
    history, applied = EV.leaks(run)
    m: dict[str, float | None] = {f"check/{k}": v for k, v in cc["checks"].items()}
    m |= {f"rule/{k}": v for k, v in rc["checks"].items()}
    m |= {f"atom/{k}": v for k, v in ac.items()}
    m |= {"run/entry": EV.entry(run), "run/ran_real_test": float(EV.ran_real_test(run))}
    if patch is not None:
        m["run/fidelity"] = EV.fidelity(run)
    for rule, _, stage, value in form_rules(parsed):
        m[f"form/{rule}@{stage}"] = value
    for rule, _, stage, value in procedure_rules(read_step, artifact_write_steps(run), set(EV.multi_read(read_step))):
        m[f"proc/{rule}@{stage}"] = value
    if unknown := sorted(set(m) - MEASURABLE):
        raise ValueError(f"measurements no rubric key declares: {unknown}")
    judged = judge_checks(run, obs, parsed, whole_patch, task)
    m |= {k.removeprefix("aidlc/"): v for k, v in judged.items() if k.startswith("aidlc/judge/")}
    diag = {
        **({"content": cc["content"]} if cc["content"] is not None else {}),
        **{f"content_{fam}": v for fam, v in cc["families"].items() if v is not None},
        "content_contradictions": float(cc["contradictions"]),
        **({"rules": float(rc["rules"])} if rc["rules"] is not None else {}),
        "leak_history": float(bool(history)),
        "leak_apply": float(bool(applied)),
        **({"patch_empty": float(not patch.strip())} if patch is not None else {}),
        **{k.removeprefix("aidlc/"): v for k, v in judged.items() if not k.startswith("aidlc/judge/")},
    }
    ctx.cache["aidlc"] = {"measure": m, "diagnostics": diag, "judged": bool(judged)}
    return ctx.cache["aidlc"]


def post(report) -> dict[str, float]:
    """The diagnostics beside the matrix: content-check family means and contradictions, the rule checks'
    mean, the solution-leak flags, an empty patch, the judge's calls and dropped answers."""
    return dict((report.cache.get("aidlc") or {}).get("diagnostics") or {})


def _result(item: Item, value: float | None, detail: str = "") -> Result:
    if value is None:
        return Result.not_applicable(item, detail or "nothing bears on it")
    v = float(value)
    return Result(item.id, "pass" if v >= 1.0 else "fail", v, detail)


def _lookup(key: str):
    def fn(item: Item, ctx: EvalContext) -> Result:
        k = key(item.check.params)
        if k not in MEASURABLE:
            raise KeyError(f"{item.id}: no measurement is named {k!r}")
        return _result(item, measure(ctx)["measure"].get(k))

    return fn


def _at(p: dict) -> str:
    return f"@{p['stage']}" if p.get("stage") not in (None, "") else ""


register("aidlc_v4_eval.claim", params={"check": True}, availability=("trace",), common=False)(_lookup(lambda p: f"check/{p['check']}"))
register("aidlc_v4_eval.rule", params={"check": True}, availability=("trace",), common=False)(_lookup(lambda p: f"rule/{p['check']}"))
register("aidlc_v4_eval.atom", params={"rule": True, "stage": False}, availability=("trace",), common=False)(_lookup(lambda p: f"atom/{p['rule']}{_at(p)}"))
register("aidlc_v4_eval.form", params={"rule": True, "stage": True}, availability=("trace",), common=False)(_lookup(lambda p: f"form/{p['rule']}{_at(p)}"))
register("aidlc_v4_eval.procedure", params={"rule": True, "stage": True}, availability=("trace",), common=False)(_lookup(lambda p: f"proc/{p['rule']}{_at(p)}"))
register("aidlc_v4_eval.run", params={"measure": True}, availability=("trace",), common=False, choices={"measure": ("entry", "ran_real_test", "fidelity")})(_lookup(lambda p: f"run/{p['measure']}"))


@register("aidlc_v4_eval.judge", params={"question": True}, availability=("trace",), common=False)
def judge(item: Item, ctx: EvalContext) -> Result:
    """The judge's yes / no on ``question`` (a rule id of ``judge.QUESTIONS``): unavailable with no judge
    configured or nothing to ask, not applicable when the question was not asked or its answer dropped."""
    got = measure(ctx)
    if not got["judged"]:
        return Result.unavailable(item, "no judge configured, or no artifact to ask about")
    return _result(item, got["measure"].get(f"judge/{item.check.params['question']}"), "not asked, or the answer was dropped")
