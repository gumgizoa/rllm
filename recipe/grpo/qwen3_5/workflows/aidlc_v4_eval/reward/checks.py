"""aidlc_v4_eval's check kinds for ``rubric.yaml`` (the ``aidlc_v4_eval.*`` plugin kinds).

Every item reads one measurement of the run: the method registered under its id (``methods/``), computed from the
run's shared readings (:class:`~.measures.Measures`, one per evaluation, kept on the context) when the item asks:

    aidlc_v4_eval.claim      check/*  an artifact's claim against the trajectory (methods/claim.py)
    aidlc_v4_eval.rule       rule/*   what the run did, whatever its artifacts claim (methods/rule.py)
    aidlc_v4_eval.atom       atom/*   an atomic rule the other kinds leave unscored (methods/atom.py)
    aidlc_v4_eval.form       form/*   an artifact's form: present, frontmatter, headings, each skeleton field
    aidlc_v4_eval.procedure  proc/*   a stage's procedure: its document read first, alone, before its artifact
    aidlc_v4_eval.run        run/*    a whole-run reading: entry, a real test run, the diff's disclosure (fidelity)
    aidlc_v4_eval.judge      judge/*  an LLM's yes / no on a content rule code cannot decide (judge.py)

A measurement that does not apply (nothing bears on it) is ``not_applicable``; a method that raises is that item's
engine error alone. The judge's items are ``unavailable`` when no judge is configured, so their cells are no part of
the matrix then.
"""

from __future__ import annotations

from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

from .measures import Measures
from .methods import measurements

# Every key a method measures: an item naming another is a broken link (it raises: a missing key must not read as
# "not applicable" and drop out of every mean unnoticed).
MEASURABLE = frozenset(measurements())


def inputs(task, episode) -> dict:
    """``Collected.inputs``: what the checks read besides the sandbox."""
    return {"task": task, "episode": episode}


def measures(ctx: EvalContext) -> Measures:
    """The run's readings, one per evaluation (kept on the context)."""
    if "aidlc" not in ctx.cache:
        ctx.cache["aidlc"] = Measures(ctx.collected.inputs["task"], ctx.collected.inputs["episode"], ctx.collected.files)
    return ctx.cache["aidlc"]


def post(report) -> dict[str, float]:
    """The diagnostics beside the matrix (``Measures.diagnostics``)."""
    m = report.cache.get("aidlc")
    return m.diagnostics() if m is not None else {}


def _result(item: Item, value: float | None, detail: str = "") -> Result:
    if value is None:
        return Result.not_applicable(item, detail or "nothing bears on it")
    v = float(value)
    return Result(item.id, "pass" if v >= 1.0 else "fail", v, detail)


def _lookup(key):
    def fn(item: Item, ctx: EvalContext) -> Result:
        k = key(item.check.params)
        if k not in MEASURABLE:
            raise KeyError(f"{item.id}: no measurement is named {k!r}")
        return _result(item, measures(ctx).value(k))

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
    judged = measures(ctx).judged
    if not judged:
        return Result.unavailable(item, "no judge configured, or no artifact to ask about")
    return _result(item, judged.get(f"aidlc/judge/{item.check.params['question']}"), "not asked, or the answer was dropped")
