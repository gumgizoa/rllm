"""agentos_bugfix kinds for the ``three_signals`` aggregate: was a stage carried out, and was a document read ahead.

A stage is one command document and the product it asks for:

    shape_spec        shape-spec.md        requirements.md
    write_spec        write-spec.md        spec.md
    create_tasks      create-tasks.md      tasks.md
    implement_tasks   implement-tasks.md   the first write to the repository

``agentos_bugfix.stage_done`` passes when all three hold (``aggregate.three_signals`` gives every item of a stage whose
item did not pass a 0):

* made -- the product is there at the end and holds at least ``min_words`` (50) words of its own (:func:`own_words`:
  what is left after the headings, the lines of the command document, its bracketed placeholders, the bold labels and
  the lines that hold only a fill-in mark are taken out), so a copy of the template, a file of headings and a file
  filled with ``x`` are none of them a product. A file the trace wrote but whose content the offline replay cannot
  rebuild counts as made (the live scorer reads the file). For implement_tasks: the repository was written to;
* read -- the stage's command document was read at a step before the product's first write;
* ordered -- every earlier stage's product that was written at all was first written before this one. An earlier
  product that was never written does not void the stage: each stage is judged on its own document and product.

Reading a document ahead voids nothing. ``agentos_bugfix.read_ahead`` is an ordinary item for it: the share of the
documents in ``pairs`` that were not first read before the product of the stage before them was written (the same
test, on the same write event, that ``order``'s ``invalidate: [read_ahead]`` makes).
"""

from __future__ import annotations

import re
from pathlib import Path

from ....workflow_rubric import refs
from ....workflow_rubric.checks import register
from ....workflow_rubric.context import UNKNOWN, EvalContext, Result
from ....workflow_rubric.schema import Item

HERE = Path(__file__).resolve().parent.parent
MIN_WORDS = 50
_MARK = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?")
_FILL = re.compile(r"^(?:x+|\.{2,}|…+|\?+|n/?a|tbd|todo|none)?$", re.I)
_HOLE = re.compile(r"\[[^\]\n]{2,}\]")
_LABEL = re.compile(r"\*\*[^*\n]{1,60}?:\*\*:?|\*\*[^*\n]{1,60}?\*\*:")
_templates: dict[str, tuple[frozenset[str], frozenset[str]]] = {}


def _norm(line: str) -> str:
    s = re.sub(r"[*_`]+", "", _MARK.sub("", line.strip()))
    return re.sub(r"\s+", " ", s).strip().lower()


def _template(ctx: EvalContext, doc: str) -> tuple[frozenset[str], frozenset[str]]:
    """(the command document's lines, its bracketed placeholders), both normalised; empty when the document is not found."""
    src = next((s for s in ctx.rubric.sources if s.id == doc), None)
    key = f"{doc}:{getattr(src, 'sha256', '')}"
    if key not in _templates:
        try:
            text = (HERE / src.path).read_text(encoding="utf-8") if src is not None else ""
        except OSError:
            text = ""
        _templates[key] = (frozenset(n for n in map(_norm, text.splitlines()) if n), frozenset(m.lower() for m in _HOLE.findall(text)))
    return _templates[key]


def own_words(text: str, lines: frozenset[str], holes: frozenset[str]) -> int:
    """Words (two or more letters or digits) of ``text`` that do not come from the template."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    n = 0
    for line in text.splitlines():
        if line.lstrip().startswith("#") or _norm(line) in lines:
            continue
        s = _HOLE.sub(lambda m: " " if m.group(0).lower() in holes else m.group(0), line)
        s = _MARK.sub("", _LABEL.sub(" ", s).strip())
        if _FILL.match(re.sub(r"[*_`\s]+", "", s)):
            continue
        n += len(re.findall(r"[A-Za-z0-9]{2,}", s))
    return n


def _first_write(ctx: EvalContext, artifact: str | None):
    """The step of the product's first successful write: an int, or None (never written / not there at the end)."""
    f = ctx.facts
    if artifact is None:
        return f.first_repo_write if isinstance(f.first_repo_write, int) else None
    path = f.artifact_paths.get(artifact)
    steps = [e.step for e in (f.writes.get(path, []) if path else []) if isinstance(e.step, int) and e.ok is not False and e.op not in ("delete", "move_out")]
    return min(steps) if steps else None


@register("agentos_bugfix.stage_done", params={"doc": True, "artifact": False, "earlier": False, "min_words": False}, availability=("trace",), common=False)
def stage_done(item: Item, ctx: EvalContext) -> Result:
    """The stage was carried out: its product was made (``artifact`` with ``min_words`` words of its own; without
    ``artifact``, a write to the repository), ``doc`` was read before the product's first write, and every product
    in ``earlier`` that was written was first written before it."""
    p = item.check.params or {}
    doc, artifact = str(p["doc"]), p.get("artifact")
    f = ctx.facts
    w = _first_write(ctx, artifact)
    if artifact is None:
        made, how = w is not None, "repository written" if w is not None else "repository never written"
    else:
        path = f.artifact_paths.get(artifact)
        text = ctx.collected.files.get(path) if path else None
        if text is None:
            made = bool(path and f.writes.get(path))
            how = "content not replayable, written" if made else "absent"
        else:
            n = own_words(text, *_template(ctx, doc))
            made, how = n >= int(p.get("min_words", MIN_WORDS)), f"{n} own words"
    reads = [r.step for r in (f.doc_reads.get(doc) or [])]
    read = w is not None and any(s < w for s in reads)
    earlier = {a: _first_write(ctx, a) for a in (p.get("earlier") or [])}
    late = [a for a, s in earlier.items() if s is not None and (w is None or not s < w)]
    ordered = w is not None and not late
    detail = f"made {made} ({how}); read {read} ({doc} at {reads[:3] or 'no step'}, first write {w}); ordered {ordered}" + (f" (after it: {', '.join(late)})" if late else "")
    return Result.ok(item, detail) if made and read and ordered else Result.no(item, detail)


@register("agentos_bugfix.read_ahead", params={"pairs": True}, availability=("trace",), common=False)
def read_ahead(item: Item, ctx: EvalContext) -> Result:
    """Share of the ``pairs`` (document, product of the stage before it) whose document was not first read before
    that product was written. A document never read, or one whose earlier product was never written, is not ahead."""
    pairs = [(str(d), str(a)) for d, a in (item.check.params or {})["pairs"]]
    ahead = []
    for doc, artifact in pairs:
        reads = ctx.facts.doc_reads.get(doc) or []
        prev = refs.event(ctx, f"write:{artifact}")
        if reads and prev is not None and (prev is UNKNOWN or reads[0].step < prev):
            ahead.append(f"{doc} first read at step {reads[0].step}, {artifact} written at {'an unknown step' if prev is UNKNOWN else prev}")
    return Result.ratio(item, len(pairs) - len(ahead), len(pairs), "; ".join(ahead) or "no document read ahead")
