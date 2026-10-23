"""aidlc_v4_ifeval's own check kinds, next to aidlc_v4_gen's (imported here so the snapshot rubric's
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

``aidlc_ifeval.no_return`` -- CW:71 "No stage returns to an earlier stage" (BT:58, CG:34 "Do not return
to Planning"): no stage's rule-detail document is read again once a later stage's document has been
read. A document read is the facts' (``docread``: a command naming it, or its text in an observation).

``aidlc_ifeval.no_asking`` -- CW:132 "No user interaction. Never generate a question file, never ask for
approval, never wait for input." ``rule: file``: no file the run wrote is named as a question file;
``rule: message``: the run does not end on a message that asks the user or waits for input (in the
openhands-sdk a turn without a tool call ends the run, so a request for input is the last message;
the ``finish`` tool's own message is not in the trace).
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

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


@register("aidlc_ifeval.no_return", params={}, availability=("trace",), common=False)
def no_return(item: Item, ctx: EvalContext) -> Result:
    """No stage document is read after a later stage's document was first read; the score is the share
    of the earlier stages' documents never returned to. not_applicable before a second stage was read."""
    docs = [s.doc for s in ctx.rubric.stages if s.doc]
    first = {d: min((r.step for r in ctx.facts.doc_reads.get(d) or []), default=None) for d in docs}
    opened = [(k, first[d]) for k, d in enumerate(docs) if first[d] is not None]
    if len(opened) < 2:
        return Result.not_applicable(item, "fewer than two stage documents read")
    back, checked = [], 0
    for j, d in enumerate(docs[:-1]):
        later = [s for k, s in opened if k > j]
        if first[d] is None or not later:
            continue
        checked += 1
        start = min(later)
        again = sorted(r.step for r in ctx.facts.doc_reads.get(d) or [] if r.step > start)
        if again:
            back.append(f"{d} at step {again[0]} (after a later stage's document at step {start})")
    if not checked:
        return Result.not_applicable(item, "no stage followed by a later one")
    return Result.ratio(item, checked - len(back), checked, f"returned to: {back[:3]}" if back else f"{checked} stages never returned to")


_QUESTION_FILE = re.compile(r"(?i)(?:^|[._-])(?:questions?|clarifications?|clarifying|q-?and-?a|qna)(?:[._-]|$)")
_ASKS_USER = re.compile(
    r"(?i)\b(?:would you like(?: me)? to|do you want me to|shall i\b|should i (?:proceed|continue|go ahead|apply|make)|"
    r"please (?:confirm|let me know|advise|clarify|provide|approve)|let me know (?:if|whether|how|which)|"
    r"(?:can|could) you (?:please )?(?:confirm|clarify|provide|approve)|(?:waiting|wait) for (?:your )?(?:input|confirmation|approval)|"
    r"before i (?:proceed|continue)|your (?:approval|confirmation) (?:to|before))"
)


@register("aidlc_ifeval.no_asking", params={"rule": True}, availability=("trace",), common=False, choices={"rule": ("file", "message")})
def no_asking(item: Item, ctx: EvalContext) -> Result:
    """rule: file -- no file the run wrote is named as a question file; message -- the run's last message
    does not ask the user or wait for input."""
    rule = str((item.check.params or {}).get("rule"))
    if rule == "file":
        named = sorted(p for p, evs in ctx.facts.writes.items() if _QUESTION_FILE.search(PurePosixPath(p).stem) and any(e.ok is not False for e in evs))
        return Result.no(item, f"question file written: {named[:3]}") if named else Result.ok(item, "no question file")
    last = next((s.message for s in reversed(ctx.run.steps) if (s.message or "").strip()), "")
    m = _ASKS_USER.search(last)
    return Result.no(item, f"last message asks the user: {m.group(0)!r}") if m else Result.ok(item, "no request for input")
