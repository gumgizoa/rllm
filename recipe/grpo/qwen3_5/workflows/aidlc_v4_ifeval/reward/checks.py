"""aidlc_v4_ifeval's own check kind, next to aidlc_v4_gen's (imported here so the snapshot rubric's
``aidlc.*`` items resolve).

``aidlc_ifeval.no_reread`` -- CW "Artifact Rules": "Do not re-read an artifact you can still see. ...
Read an artifact only to recover, when an earlier stage's content is no longer visible because output
was truncated or history was compacted." The openhands-sdk runner builds its ``Agent`` without a
condenser, so nothing the agent saw leaves its context during a run: an artifact is visible from the
first step its content was in the agent's context -- the write itself when the call carried the
content (an editor create, a heredoc, ``printf``, ``tee`` output), otherwise its first read (a ``cp``
or a script that wrote it never showed the content, so that read recovers it). Every read after that
step, or in that step after a write carrying the content, is a re-read of something still visible.
Reads are counted per step (``_read_steps``): two reads of one artifact in one call count as one.
"""

from __future__ import annotations

from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.facts import WRITE_OPS
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item
from recipe.grpo.qwen3_5.workflows.aidlc_v4_gen.reward.checks import _read_steps  # noqa: F401 -- also registers aidlc.*

CONTENT_WRITES = WRITE_OPS - {"move_in"}
SHOWN_MIN = 0.5  # share of the written content's lines the writing call must carry to count as shown


def _shown(ctx: EvalContext, e) -> bool:
    """The write's call carried its content: at least ``SHOWN_MIN`` of the file's non-blank lines appear
    in the tool call (command, text) or in its reply."""
    lines = [ln.strip() for ln in (e.content or "").splitlines() if len(ln.strip()) >= 3]
    if not lines:
        return True  # nothing to recover
    step = next((s for s in ctx.run.steps if s.n == e.step), None)
    acts = step.actions if step is not None else []
    a = acts[e.action_index] if 0 <= getattr(e, "action_index", -1) < len(acts) else None
    seen = "\n".join(x for x in ((a.command, a.text, a.observation) if a is not None else ()) if x)
    return sum(1 for ln in lines if ln in seen) >= SHOWN_MIN * len(lines)


@register("aidlc_ifeval.no_reread", params={"artifacts": False}, availability=("trace",), common=False)
def no_reread(item: Item, ctx: EvalContext) -> Result:
    """No artifact in ``artifacts`` (default: every artifact of the rubric) is read once its content is
    visible; the score is the share of written artifacts never re-read. not_applicable when the run wrote
    none of them."""
    p = item.check.params or {}
    ids = [a for a in (p.get("artifacts") or list(ctx.rubric.artifacts)) if isinstance(a, str)]
    wd = ctx.collected.workdir
    first: dict[str, object] = {}
    for aid in ids:
        path = ctx.facts.artifact_paths.get(aid)
        evs = [e for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in CONTENT_WRITES] if path else []
        if evs:
            first[refs.norm_path(path, wd)] = min(evs, key=lambda e: (e.step, e.action_index))
    if not first:
        return Result.not_applicable(item, "no artifact written")
    hits = _read_steps(ctx, set(first), (0, None))  # the whole run
    reread, clean = [], 0
    for q, e in first.items():
        steps = sorted(s for s in hits.get(q, []) if s >= e.step)
        if not _shown(ctx, e) and steps:
            steps = steps[1:]  # the first read after a write that never showed the content recovers it
        reread += [f"{q} at step {s}" for s in steps]
        clean += not steps
    return Result.ratio(item, clean, len(first), f"re-read: {sorted(reread)[:4]}" if reread else f"{len(first)} artifacts, none re-read")
