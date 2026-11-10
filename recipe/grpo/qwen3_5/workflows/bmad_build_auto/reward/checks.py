"""bmad_build_auto's own check kinds (``bmad.*``), next to the common ones of ``workflow_rubric.checks``.

The parent run is the orchestrator's conversation only: ``trace/episode.py`` splits the sub-agents' LLM
calls off (steps whose request did not carry the ``task`` tool) into ``Run.meta["subagent_runs"]``, so
"the agent read X" here means the orchestrator did. A ``task`` call is an ``other`` action named ``task``
with ``text`` = prompt, ``path`` = subagent_type, ``old`` = resume id and the sub-agent's final message as
observation (``trace/openhands.py``).

Kinds (every one ``scope: specific``):

frontmatter_value   a frontmatter key's scalar: present, in ``values``, matching ``pattern``, or every
                    token in ``tokens`` / matching ``tokens_pattern`` (list values; an empty list passes)
text_regex          ``pattern`` occurs between ``min`` and ``max`` times in the artifact (or its ``section``);
                    ``optional_section``: not_applicable when the section is absent; ``requires_section``:
                    not_applicable unless that section exists (the matrix -> test task rule)
word_count          the artifact body has between ``min`` and ``max`` words
block_unchanged     the text between ``open`` and ``close`` is the same at the end of the owning stage and at
                    the end of the run (the spec's ``<intent-contract>`` is read-only after planning)
append_only         each listed section's stage-end text is a prefix of its final text
spec_count          at most ``max`` files matching ``pattern`` under the artifact root (one spec per run)
diff_file           the diff artifact is a non-empty unified diff
artifact_io         the artifact was read (``mode: read``: view / cat / head / sed / grep ... of its path) or
                    written (``mode: write``) inside ``window``; ``after_write``: reads count only after its
                    first write
paths_read          every repository path named in the artifact section (``pattern`` group 1, backticked
                    by default) was opened in ``window`` (default: before the artifact's write)
command             a shell command matching ``pattern`` ran in ``window`` (``min`` times, default 1)
no_doc_read         none of the ``docs`` (source ids) was read by the orchestrator
task_calls          the sub-agent tool: ``launched`` (``min`` calls in the window, optional ``pattern`` on
                    the prompt), ``same_turn`` (one step holds ``min`` calls), ``lenses`` (share of the four
                    review lenses launched, by prompt signature), ``prompt_pattern`` (share of the ``lens``
                    calls whose prompt matches ``pattern`` and not ``forbid``), ``resume_for_patch`` (a call
                    with ``resume`` when the triage log routed something to patch), ``resume_prompt`` (every
                    resumed call's prompt matches ``pattern``)
lens_output         the final message a lens sub-agent returned: ``pattern`` / ``no_pattern`` (with
                    ``when``), ``json_array``, ``json_keys`` (every object has exactly ``keys`` plus
                    ``optional``; ``where`` restricts to objects with those values)
triage_totals       ``totals``: each Review Triage Log entry's ``<total>`` equals its row count and the sum
                    of its five verdict counts; ``false_reject``: every ``[false]`` row routes to reject
last_message        the run's last message does not ask the user or wait for input
"""

from __future__ import annotations

import json
import posixpath
import re
import shlex

from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

TASK = "task"
LENSES = {
    "implementer": r"Read \S+spec-[^\s`]+\.md fully and implement it",
    "blind": r"Conduct a review of",
    "edge": r"review-prompts/edge-case-hunter\.md",
    "gap": r"review-prompts/verification-gap\.md",
    "intent": r"intent-alignment auditor",
}
REVIEW_LENSES = ("blind", "edge", "gap", "intent")
_READ_VERBS = ("cat", "head", "tail", "sed", "less", "more", "grep", "awk", "wc", "bat", "view", "python", "python3")
_ASKS_USER = re.compile(
    r"(?i)\b(?:would you like(?: me)? to|do you want me to|shall i\b|should i (?:proceed|continue|go ahead|apply|make)|"
    r"please (?:confirm|let me know|advise|clarify|provide|approve)|let me know (?:if|whether|how|which)|"
    r"(?:can|could) you (?:please )?(?:confirm|clarify|provide|approve)|(?:waiting|wait) for (?:your )?(?:input|confirmation|approval)|"
    r"before i (?:proceed|continue)|your (?:approval|confirmation) (?:to|before))"
)


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------
def _p(item: Item) -> dict:
    return item.check.params or {}


def _aid(item: Item) -> str:
    return _p(item).get("artifact") or item.target.ref


def _text(item: Item, ctx: EvalContext, state: str | None = None) -> str | None:
    t = ctx.artifact_text(_aid(item), state or item.target.state)
    return None if t is None else M.strip_fence(t)[0]


def _window(item: Item, ctx: EvalContext):
    p = _p(item)
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    return refs.window(ctx, spec)


def _rx(pattern) -> re.Pattern:
    return re.compile(str(pattern), re.M)


def _task_calls(ctx: EvalContext, w=None) -> list[tuple[int, object]]:
    out = []
    for s in ctx.run.steps:
        if w is not None and not refs.in_window(s.n, w):
            continue
        out.extend((s.n, a) for a in s.actions if a.name == TASK)
    return out


def _lens_of(prompt: str) -> str | None:
    for name, sig in LENSES.items():
        if re.search(sig, prompt or ""):
            return name
    return None


def _lens_calls(ctx: EvalContext, lens, w=None) -> list[tuple[int, object]]:
    want = set(REVIEW_LENSES) if lens in (None, "review", "all_lenses") else set(lens if isinstance(lens, (list, tuple)) else [lens])
    return [(n, a) for n, a in _task_calls(ctx, w) if _lens_of(a.text or "") in want]


def _result_text(observation: str) -> str:
    """The sub-agent's final message: the observation after the ``Task ID / Subagent / Status`` header."""
    lines = (observation or "").splitlines()
    i = 0
    while i < len(lines) and re.match(r"^\s*(Task ID|Subagent|Status)\s*:", lines[i]):
        i += 1
    return "\n".join(lines[i:]).strip()


def _tokens(value: str) -> list[str]:
    v = re.sub(r"^\[|\]$", "", value.strip())
    return [t.strip().strip("'\"") for t in re.split(r"[,\n]|\s-\s|^-\s", v) if t.strip().strip("'\"- ")]


def _command_mentions(cmd: str, path: str) -> bool:
    return bool(path) and path in (cmd or "")


def _ratio(item: Item, good: int, total: int, detail: str) -> Result:
    return Result.ratio(item, good, total, detail)


# --------------------------------------------------------------------------------------------
# artifact content
# --------------------------------------------------------------------------------------------
@register("bmad.frontmatter_value", params={"key": True, "artifact": False, "values": False, "pattern": False, "tokens": False, "tokens_pattern": False, "required": False}, common=False)
def frontmatter_value(item: Item, ctx: EvalContext) -> Result:
    """A frontmatter scalar's value against an enumeration, a regex or an allowed token set."""
    p = _p(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    fm = M.frontmatter(text)
    key = str(p["key"])
    if not fm.present or key not in fm.values:
        return Result.no(item, f"no frontmatter key {key!r}")
    if not fm.valid:
        return Result.no(item, "frontmatter is not valid YAML")
    v = fm.values[key]
    if "values" in p and v not in [str(x) for x in p["values"]]:
        return Result.no(item, f"{key}={v!r} not in {list(p['values'])}")
    if "pattern" in p and not re.search(str(p["pattern"]), v, re.S):
        return Result.no(item, f"{key}={v[:60]!r} does not match")
    if "tokens" in p or "tokens_pattern" in p:
        toks = _tokens(v)
        allowed = set(map(str, p.get("tokens") or []))
        rx = re.compile(str(p["tokens_pattern"])) if "tokens_pattern" in p else None
        bad = [t for t in toks if (allowed and t not in allowed) or (rx is not None and not rx.search(t))]
        if bad:
            return Result.no(item, f"{key} has {bad[:3]}")
    return Result.ok(item, f"{key}={v[:40]!r}")


@register("bmad.text_regex", params={"pattern": True, "artifact": False, "section": False, "min": False, "max": False, "optional_section": False, "requires_section": False}, common=False)
def text_regex(item: Item, ctx: EvalContext) -> Result:
    """``pattern`` occurs between ``min`` (default 1) and ``max`` times in the artifact body or ``section``."""
    p = _p(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    if p.get("requires_section") and M.section(text, str(p["requires_section"])) is None:
        return Result.not_applicable(item, f"no section {p['requires_section']!r}")
    body = M.frontmatter(text).body if not p.get("section") else M.section(text, str(p["section"]))
    if body is None:
        if p.get("optional_section"):
            return Result.not_applicable(item, f"no section {p['section']!r}")
        return Result.no(item, f"section {p['section']!r} absent")
    n = len(_rx(p["pattern"]).findall(body))
    lo, hi = int(p.get("min", 1)), p.get("max")
    if n < lo or (hi is not None and n > int(hi)):
        return Result.no(item, f"{n} match(es), want {lo}..{hi if hi is not None else '∞'}")
    return Result.ok(item, f"{n} match(es)")


@register("bmad.word_count", params={"min": False, "max": False, "artifact": False}, common=False)
def word_count(item: Item, ctx: EvalContext) -> Result:
    """The artifact body holds between ``min`` and ``max`` words."""
    p = _p(item)
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    n = len(M.frontmatter(text).body.split())
    lo, hi = int(p.get("min", 0)), p.get("max")
    ok = n >= lo and (hi is None or n <= int(hi))
    return Result.ok(item, f"{n} words") if ok else Result.no(item, f"{n} words, want {lo}..{hi}")


@register("bmad.block_unchanged", params={"open": True, "close": True, "artifact": False}, common=False)
def block_unchanged(item: Item, ctx: EvalContext) -> Result:
    """The text between ``open`` and ``close`` at the owning stage's end equals the final text's."""
    p = _p(item)

    def block(t):
        if t is None:
            return None
        m = re.search(re.escape(str(p["open"])) + r"(.*?)" + re.escape(str(p["close"])), t, re.S)
        return None if m is None else re.sub(r"\s+", " ", m.group(1)).strip()

    final = block(_text(item, ctx, "final"))
    if final is None:
        return Result.no(item, "block absent in the final artifact")
    earlier = block(_text(item, ctx, "stage_end"))
    if earlier is None:
        return Result.not_applicable(item, "no stage-end text to compare")
    return Result.ok(item, "unchanged") if earlier == final else Result.no(item, "block differs from its stage-end text")


@register("bmad.append_only", params={"sections": True, "artifact": False}, common=False)
def append_only(item: Item, ctx: EvalContext) -> Result:
    """Each section's stage-end text is a prefix of its final text (normalised whitespace)."""
    p = _p(item)
    final, earlier = _text(item, ctx, "final"), _text(item, ctx, "stage_end")
    if final is None:
        return Result.no(item, "artifact absent")
    if earlier is None:
        return Result.not_applicable(item, "no stage-end text to compare")
    bad = []
    for sec in p["sections"]:
        a = re.sub(r"\s+", " ", M.section(earlier, str(sec)) or "").strip()
        b = re.sub(r"\s+", " ", M.section(final, str(sec)) or "").strip()
        if not b.startswith(a):
            bad.append(str(sec))
    return Result.no(item, f"rewritten: {bad}") if bad else Result.ok(item, "append-only")


@register("bmad.spec_count", params={"pattern": True, "min": False, "max": False, "under": False}, availability=("sandbox_file",), common=False)
def spec_count(item: Item, ctx: EvalContext) -> Result:
    """Between ``min`` (default 0) and ``max`` (default 1) collected files match ``pattern`` (under ``under`` if given)."""
    p = _p(item)
    rx = re.compile(str(p["pattern"]))
    under = str(p.get("under") or "")
    hits = [f for f in ctx.collected.files if rx.search(f) and (not under or f.startswith(under))]
    lo, hi = int(p.get("min", 0)), int(p.get("max", 1))
    ok = lo <= len(hits) <= hi
    return Result.ok(item, f"{len(hits)} file(s)") if ok else Result.no(item, f"{len(hits)} files, want {lo}..{hi}: {sorted(hits)[:3]}")


@register("bmad.diff_file", params={"artifact": False}, common=False)
def diff_file(item: Item, ctx: EvalContext) -> Result:
    """The diff artifact exists and is a unified diff."""
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "diff file absent")
    if not text.strip():
        return Result.no(item, "diff file empty")
    if re.search(r"^diff --git |^--- \S", text, re.M) and re.search(r"^\+\+\+ \S", text, re.M):
        return Result.ok(item, f"{len(text.splitlines())} lines")
    return Result.no(item, "not a unified diff")


# --------------------------------------------------------------------------------------------
# trace: reads, writes, commands
# --------------------------------------------------------------------------------------------
def _reads_of(ctx: EvalContext, path: str) -> list[int]:
    steps = []
    for s in ctx.run.steps:
        for a in s.actions:
            if a.kind == "view" and a.path and posixpath.normpath(a.path) == posixpath.normpath(path):
                steps.append(s.n)
            elif a.kind == "shell" and a.command and _command_mentions(a.command, path):
                # per segment: a read verb and the path, and the path is not the segment's redirect target
                for seg in re.split(r"&&|\|\||;|\|", a.command.replace("\n", " ")):
                    if path not in seg or re.search(r">\s*" + re.escape(path), seg):
                        continue
                    try:
                        words = shlex.split(seg)
                    except ValueError:
                        words = seg.split()
                    if any(w in _READ_VERBS for w in words):
                        steps.append(s.n)
                        break
    return steps


@register("bmad.artifact_io", params={"artifact": True, "mode": True, "window": False, "after_write": False}, availability=("trace", "sandbox_file"), common=False, choices={"mode": ("read", "write")})
def artifact_io(item: Item, ctx: EvalContext) -> Result:
    """The artifact was read or written inside the window."""
    p = _p(item)
    aid = str(p["artifact"])
    path = ctx.facts.artifact_paths.get(aid)
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    if not path:
        return Result.no(item, f"artifact {aid} not found")
    if p["mode"] == "write":
        steps = [e.step for e in ctx.facts.writes.get(path, []) if e.ok is not False and refs.in_window(e.step, w)]
        return Result.ok(item, f"written at {steps[:3]}") if steps else Result.no(item, f"no write of {aid} in {list(w)}")
    first = min((e.step for e in ctx.facts.writes.get(path, []) if e.ok is not False), default=None)
    steps = [n for n in _reads_of(ctx, path) if refs.in_window(n, w) and (not p.get("after_write") or (first is not None and n >= first))]
    return Result.ok(item, f"read at {steps[:3]}") if steps else Result.no(item, f"no read of {aid} in {list(w)}")


@register("bmad.paths_read", params={"artifact": True, "section": True, "pattern": False, "window": False}, availability=("trace", "sandbox_file"), common=False)
def paths_read(item: Item, ctx: EvalContext) -> Result:
    """Every repo path named in the section was opened in the window (default: before the artifact's write)."""
    p = _p(item)
    aid = str(p["artifact"])
    text = ctx.artifact_text(aid, "final")
    if text is None:
        return Result.no(item, "artifact absent")
    body = M.section(text, str(p["section"]))
    if body is None:
        return Result.no(item, f"section {p['section']!r} absent")
    rx = re.compile(str(p.get("pattern") or r"`([^`\s()]+/[^`\s()]+|[^`\s()/]+\.[a-z]{1,5})`"))
    paths = sorted({m.group(1) for m in rx.finditer(body)})
    if not paths:
        return Result.not_applicable(item, "no paths named")
    w = refs.window(ctx, p["window"]) if "window" in p else refs.window(ctx, ["start", f"write:{aid}"])
    if w is None:
        return Result.no(item, "window empty")
    wd = ctx.collected.workdir or ""
    seen = set()
    for s in ctx.run.steps:
        if not refs.in_window(s.n, w):
            continue
        for a in s.actions:
            blob = " ".join(x for x in (a.path, a.command) if x)
            for q in paths:
                rel = q[len(wd) + 1 :] if wd and q.startswith(wd + "/") else q
                if rel in blob or q in blob:
                    seen.add(q)
    missing = [q for q in paths if q not in seen]
    return _ratio(item, len(paths) - len(missing), len(paths), f"not opened: {missing[:3]}" if missing else f"{len(paths)} paths opened")


@register("bmad.command", params={"pattern": True, "window": False, "min": False}, availability=("trace",), common=False)
def command(item: Item, ctx: EvalContext) -> Result:
    """At least ``min`` shell commands matching ``pattern`` ran in the window."""
    p = _p(item)
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    rx = re.compile(str(p["pattern"]), re.S)
    hits = [c.step for c in ctx.facts.commands if refs.in_window(c.step, w) and rx.search(c.command)]
    need = int(p.get("min", 1))
    return Result.ok(item, f"at {hits[:3]}") if len(hits) >= need else Result.no(item, f"{len(hits)} match(es) in {list(w)}, want {need}")


@register("bmad.no_doc_read", params={"docs": True}, availability=("trace",), common=False)
def no_doc_read(item: Item, ctx: EvalContext) -> Result:
    """None of the documents was read by the orchestrator (the reviewer prompts are for the sub-agents)."""
    read = [d for d in _p(item)["docs"] if ctx.facts.doc_reads.get(str(d))]
    return Result.no(item, f"read by the orchestrator: {read}") if read else Result.ok(item, "not read")


# --------------------------------------------------------------------------------------------
# sub-agents
# --------------------------------------------------------------------------------------------
_TASK_RULES = ("launched", "same_turn", "lenses", "prompt_pattern", "resume_for_patch", "resume_prompt", "all_type")


@register("bmad.task_calls", params={"rule": True, "window": False, "min": False, "pattern": False, "forbid": False, "lens": False, "type": False}, availability=("trace", "sandbox_file"), common=False, choices={"rule": _TASK_RULES})
def task_calls(item: Item, ctx: EvalContext) -> Result:
    """How the orchestrator used the ``task`` tool (see the module docstring)."""
    p = _p(item)
    rule = str(p["rule"])
    w = _window(item, ctx)
    if w is None:
        return Result.no(item, "window empty")
    calls = _task_calls(ctx, w)
    if rule == "launched":
        rx = re.compile(str(p["pattern"]), re.S) if p.get("pattern") else None
        hits = [n for n, a in calls if rx is None or rx.search(a.text or "")]
        need = int(p.get("min", 1))
        return Result.ok(item, f"{len(hits)} call(s) at {hits[:4]}") if len(hits) >= need else Result.no(item, f"{len(hits)} task call(s) in {list(w)}, want {need}")
    if rule == "same_turn":
        need = int(p.get("min", 4))
        per_step: dict[int, int] = {}
        for n, a in _lens_calls(ctx, p.get("lens"), w):
            per_step[n] = per_step.get(n, 0) + 1
        best = max(per_step.values(), default=0)
        return Result.ok(item, f"{best} in one turn") if best >= need else Result.no(item, f"at most {best} lens call(s) per turn, want {need}; turns {sorted(per_step)}")
    if rule == "lenses":
        found = {_lens_of(a.text or "") for _, a in calls} & set(REVIEW_LENSES)
        return _ratio(item, len(found), len(REVIEW_LENSES), f"launched: {sorted(found)}")
    if rule == "prompt_pattern":
        sel = _lens_calls(ctx, p.get("lens"), w)
        if not sel:
            return Result.no(item, "no such lens call")
        rx = re.compile(str(p["pattern"]), re.S) if p.get("pattern") else None
        fb = re.compile(str(p["forbid"]), re.M) if p.get("forbid") else None
        good = [n for n, a in sel if (rx is None or rx.search(a.text or "")) and (fb is None or not fb.search(a.text or ""))]
        return _ratio(item, len(good), len(sel), f"{len(good)}/{len(sel)} prompts")
    if rule == "all_type":
        if not calls:
            return Result.not_applicable(item, "no task call")
        want = str(p.get("type") or "general-purpose")
        good = [n for n, a in calls if (a.path or "general-purpose") == want]
        return _ratio(item, len(good), len(calls), f"{len(good)}/{len(calls)} {want}")
    if rule in ("resume_for_patch", "resume_prompt"):
        spec = ctx.artifact_text("spec", "final") or ""
        log = M.section(spec, "Review Triage Log") or ""
        patched = re.search(r"`\[patch\]`", log) is not None
        resumed = [(n, a) for n, a in calls if a.old]
        if rule == "resume_for_patch":
            if not patched:
                return Result.not_applicable(item, "no patch route in the triage log")
            return Result.ok(item, f"resumed at {[n for n, _ in resumed][:3]}") if resumed else Result.no(item, "patch routed but no task call used resume")
        if not resumed:
            return Result.not_applicable(item, "no resumed call")
        rx = re.compile(str(p.get("pattern") or r"^Review of your implementation found problems"), re.S)
        good = [n for n, a in resumed if rx.search((a.text or "").strip())]
        return _ratio(item, len(good), len(resumed), f"{len(good)}/{len(resumed)} resumed prompts")
    return Result.no(item, f"unknown rule {rule!r}")


def _json_array(text: str):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        v = json.loads(t)
    except Exception:  # noqa: BLE001 -- agent text
        return None
    return v if isinstance(v, list) else None


_LENS_RULES = ("pattern", "no_pattern", "json_array", "json_keys", "nonempty")


@register("bmad.lens_output", params={"lens": True, "rule": True, "pattern": False, "when": False, "keys": False, "optional": False, "where": False, "window": False}, availability=("trace",), common=False, choices={"rule": _LENS_RULES})
def lens_output(item: Item, ctx: EvalContext) -> Result:
    """The final message of a review lens sub-agent, per launch (share of launches that satisfy the rule)."""
    p = _p(item)
    rule = str(p["rule"])
    w = _window(item, ctx)
    sel = _lens_calls(ctx, p.get("lens"), w)
    if not sel:
        return Result.not_applicable(item, "lens not launched")
    outs = [_result_text(a.observation) for _, a in sel]
    outs = [o for o in outs if o]
    if not outs:
        return Result.no(item, "lens returned nothing")
    when = re.compile(str(p["when"]), re.M | re.S) if p.get("when") else None
    good, total = 0, 0
    for o in outs:
        if when is not None and not when.search(o):
            continue
        total += 1
        if rule == "nonempty":
            good += bool(o.strip())
        elif rule == "pattern":
            good += re.search(str(p["pattern"]), o, re.M | re.S) is not None
        elif rule == "no_pattern":
            good += re.search(str(p["pattern"]), o, re.M | re.S) is None
        elif rule == "json_array":
            good += _json_array(o) is not None
        elif rule == "json_keys":
            arr = _json_array(o)
            if arr is None:
                continue
            keys, opt, where = set(map(str, p.get("keys") or [])), set(map(str, p.get("optional") or [])), dict(p.get("where") or {})
            objs = [x for x in arr if isinstance(x, dict) and all(str(x.get(k)) == str(v) for k, v in where.items())]
            if not objs:
                total -= 1
                continue
            good += all(keys <= set(x) <= keys | opt for x in objs)
    if total == 0:
        return Result.not_applicable(item, "no output the rule applies to")
    return _ratio(item, good, total, f"{good}/{total} outputs")


_ROW = re.compile(r"^\s*-\s+`\[(high|medium|low|false|maybe-false)\]`\s+`\[(bad_spec|patch|defer|reject)\]`", re.M)
_VERDICTS = re.compile(r"^\s*-\s+verdicts:\s*(\d+)\s+findings?\s*[—–-]+\s*high\s+(\d+),\s*medium\s+(\d+),\s*low\s+(\d+),\s*false\s+(\d+),\s*maybe-false\s+(\d+)", re.M)


@register("bmad.triage_totals", params={"rule": True, "artifact": False}, common=False, choices={"rule": ("totals", "false_reject")})
def triage_totals(item: Item, ctx: EvalContext) -> Result:
    """Internal consistency of the Review Triage Log entries."""
    text = _text(item, ctx)
    if text is None:
        return Result.no(item, "artifact absent")
    log = M.section(text, "Review Triage Log")
    if log is None:
        return Result.no(item, "no Review Triage Log section")
    entries = re.split(r"(?m)^###\s+", log)[1:]
    if not entries:
        return Result.not_applicable(item, "no review pass logged")
    rule = str(_p(item)["rule"])
    good = 0
    for e in entries:
        rows = _ROW.findall(e)
        if rule == "false_reject":
            bad = [r for r in rows if r[0] == "false" and r[1] != "reject"]
            good += not bad
            continue
        m = _VERDICTS.search(e)
        if m is None:
            continue
        total, counts = int(m.group(1)), [int(x) for x in m.groups()[1:]]
        good += total == len(rows) == sum(counts)
    return _ratio(item, good, len(entries), f"{good}/{len(entries)} entries consistent")


@register("bmad.last_message", params={}, availability=("trace",), common=False)
def last_message(item: Item, ctx: EvalContext) -> Result:
    """The run's last message does not ask the user or wait for input."""
    last = next((s.message for s in reversed(ctx.run.steps) if (s.message or "").strip()), "")
    m = _ASKS_USER.search(last)
    return Result.no(item, f"last message asks the user: {m.group(0)!r}") if m else Result.ok(item, "no request for input")
