"""G7: critique the grounded items -- coverage, refutation, conflicts (DESIGN §10 G7).

(a) coverage   modal sentences (G1) and statements (G4) that no accepted item cites are shown to the
               model, which may return new statements; they go through G5 and G6 like any other.
               The loop stops after two consecutive rounds that add no accepted item (or ``max_rounds``).
(b) refute     each model-derived item is shown with its cited lines: is the check stricter than the
               text, or is the cited line an example of artifact content rather than a requirement?
               ``drop`` rejects it, ``downgrade`` lowers it to should (both logged with the reason).
(c) conflicts  pairs of items that cannot both hold; G8 resolves them by the workflow's precedence.

Template-compiled and manual items are not refuted here (they are rules / human decisions); they
still count for coverage and conflicts.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field

from . import items as I
from .config import GeneratorConfig
from .extract import Statement, map_items, statement_schema, statements_from_rows
from .ground import Grounder, GroundResult
from .llm import LLM, LLMError
from .manifest import Manifest
from .parse import Parsed
from .vocab import KindSpec

COVERAGE_PROMPT = """You review a rubric generated from a workflow's documents. Below are sentences no rubric item cites yet.
For each one that is a normative requirement the agent's behaviour or artifacts could be checked against, return a statement
(line range and verbatim quote from the given lines). Skip sentences that are explanations, examples, or already covered in substance."""
REFUTE_PROMPT = """You audit rubric items derived from a workflow's documents. For each item decide:
keep      the check follows from the cited text;
downgrade the text supports it only weakly (implicit, advisory, or stricter than written) -> should;
drop      the cited line is an example of artifact content, not a requirement, or the check contradicts the text.
Give a one-sentence reason quoting the decisive words."""
CONFLICT_PROMPT = """You audit rubric items derived from a workflow's documents. List pairs (or groups) of items that cannot both be
satisfied by one honest run (contradictory values, incompatible orders, a prohibition against a requirement). Do not list items that merely
overlap. Explain each conflict in one sentence."""

REFUTE_SCHEMA = {
    "type": "object",
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "verdict", "reason"],
                "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": ["keep", "downgrade", "drop"]}, "reason": {"type": "string"}},
            },
        }
    },
}
CONFLICT_SCHEMA = {
    "type": "object",
    "required": ["conflicts"],
    "properties": {
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["items", "description"],
                "properties": {"items": {"type": "array", "items": {"type": "string"}, "minItems": 2}, "description": {"type": "string"}},
            },
        }
    },
}


@dataclass
class CriticResult:
    added: list[I.Cand] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    may_items: list[dict] = field(default_factory=list)
    implicit_items: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    rounds: int = 0
    log: list[str] = field(default_factory=list)


def uncovered(accepted: list[I.Cand], parsed: dict[str, Parsed], stmts: list[Statement], manifest: Manifest, handled: set[tuple[str, int]]) -> list[dict]:
    """Modal candidates and statements no accepted item cites (by doc + line overlap), minus ``handled`` lines."""
    cited = {ln for c in accepted for ln in c.lines()}
    out: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for sid, p in parsed.items():
        for cd in p.candidates:
            if cd.modality == "may":
                continue
            span = {(sid, n) for n in range(cd.line_start, cd.line_end + 1)}
            if span & cited or span & handled:
                continue
            k = (sid, cd.line_start, cd.line_end)
            if k not in seen:
                seen.add(k)
                out.append({"doc": sid, "line_start": cd.line_start, "line_end": cd.line_end, "text": cd.text, "modality": cd.modality})
    for s in stmts:
        if s.modality == "may" or s.checkable_by_rule == "no":
            continue
        span = {(s.source, n) for n in range(int(s.line_start), int(s.line_end) + 1)}
        if span & cited or span & handled:
            continue
        k = (s.source, int(s.line_start), int(s.line_end))
        if k not in seen:
            seen.add(k)
            out.append({"doc": s.source, "line_start": int(s.line_start), "line_end": int(s.line_end), "text": s.quote, "modality": s.modality})
    return out


def run(
    accepted: list[I.Cand],
    stmts: list[Statement],
    cfg: GeneratorConfig,
    manifest: Manifest,
    parsed: dict[str, Parsed],
    model: dict,
    kinds: dict[str, KindSpec],
    llm: LLM,
    template_cands: list[I.Cand],
    handled: set[tuple[str, int]] | None = None,
) -> CriticResult:
    """G7 over the accepted items; returns what to add, reject, and the conflicts found."""
    res = CriticResult()
    grounder = Grounder(cfg, manifest, parsed, model, kinds)
    current = list(accepted)
    handled = set(handled or ())
    stages = [s["id"] for s in model.get("stages", [])]
    dry, rnd, n_new = 0, 0, 0
    while dry < 2 and rnd < cfg.llm.max_rounds:
        rnd += 1
        todo = uncovered(current, parsed, stmts + res.statements, manifest, handled)
        if not todo:
            res.log.append(f"G7 round {rnd}: nothing uncovered")
            break
        new_stmts: list[Statement] = []
        for i in range(0, len(todo), 40):
            batch = todo[i : i + 40]
            user = f"STAGES: {', '.join(stages)}\n\nUNCOVERED SENTENCES:\n" + "\n".join(
                f"- {manifest.by_id(t['doc']).path}:{t['line_start']}-{t['line_end']} ({t['modality']}): {t['text']}" for t in batch
            )
            try:
                ans = llm.ask(COVERAGE_PROMPT, user, _coverage_schema(stages), salt=f"round{rnd}")
            except LLMError as e:
                res.log.append(f"G7 coverage round {rnd}: {e}")
                continue
            rows = []
            for k, s in enumerate(ans.get("statements", [])):
                n_new += 1
                rows.append({**s, "id": f"critic-{rnd}-{n_new:03d}-{k}"})
            new_stmts += statements_from_rows(rows, manifest)
        res.statements += new_stmts
        mapped = map_items(new_stmts, cfg, manifest, model, kinds, llm, template_cands, salt=f"critic{rnd}")
        for c in mapped.cands:
            c.origin = "critic"
        g: GroundResult = grounder.run(mapped.cands)
        res.added += g.accepted
        res.rejected += g.rejected
        res.may_items += g.may_items
        res.implicit_items += g.implicit_items
        current += g.accepted
        res.log.append(f"G7 round {rnd}: {len(todo)} uncovered, {len(new_stmts)} statements, {len(g.accepted)} accepted")
        dry = dry + 1 if not g.accepted else 0
    res.rounds = rnd
    _refute(current, manifest, llm, res, cfg.llm.parallel, cfg)
    _conflicts(current, llm, res)
    return res


def _coverage_schema(stages: list[str]) -> dict:
    s = statement_schema(stages)
    s["properties"]["statements"]["items"]["required"] = ["path", *s["properties"]["statements"]["items"]["required"]]
    s["properties"]["statements"]["items"]["properties"]["path"] = {"type": "string"}
    return s


def _refute(current: list[I.Cand], manifest: Manifest, llm: LLM, res: CriticResult, parallel: int = 1, cfg: GeneratorConfig | None = None) -> None:
    excluded = [x["statement"] for x in getattr(cfg, "exclude", []) or []]
    targets = [
        c for c in current if c.origin in ("llm", "critic") and c.item.check.kind != "unimplemented" and not any(fnmatch.fnmatch(c.statement, pat) for pat in excluded)
    ]  # a weight-0 placeholder or an item already dropped on review needs no refutation
    by_id = {c.id: c for c in targets}
    batches = [targets[i : i + 20] for i in range(0, len(targets), 20)]
    asks = [(REFUTE_PROMPT, "ITEMS:\n" + "\n\n".join(_item_block(c, manifest) for c in batch), REFUTE_SCHEMA, "") for batch in batches]
    for ans in llm.ask_many(asks, parallel):
        if isinstance(ans, LLMError):
            res.log.append(f"G7 refute: {ans}")
            continue
        for v in ans.get("verdicts", []):
            c = by_id.get(v.get("id"))
            if c is None or v.get("verdict") == "keep":
                continue
            if v["verdict"] == "drop":
                res.rejected.append({"id": c.id, "origin": c.origin, "statement": c.statement, "kind": c.item.check.kind, "reason": "critic refute", "detail": v.get("reason", "")})
                c.log.append(f"critic drop: {v.get('reason', '')}")
            elif c.item.requirement == "must":
                c.item.requirement = "should"
                c.downgrade_reason = f"critic: {v.get('reason', '')}"
                c.item.modality_evidence += f"; lowered by critic: {v.get('reason', '')}"
                c.log.append(f"critic downgrade: {v.get('reason', '')}")


def _conflicts(current: list[I.Cand], llm: LLM, res: CriticResult) -> None:
    dropped = {r["id"] for r in res.rejected}
    live = [c for c in current if c.id not in dropped]
    if len(live) < 2:
        return
    rows = [
        json.dumps({"id": c.id, "kind": c.item.check.kind, "target": c.item.target.ref, "stage": c.item.stage, "params": c.item.check.params, "requirement": c.item.requirement}, default=str)
        for c in live
    ]
    for i in range(0, len(rows), 150):
        try:
            ans = llm.ask(CONFLICT_PROMPT, "ITEMS:\n" + "\n".join(rows[i : i + 150]), CONFLICT_SCHEMA)
        except LLMError as e:
            res.log.append(f"G7 conflicts: {e}")
            continue
        ids = {c.id for c in live}
        for cf in ans.get("conflicts", []):
            its = [x for x in cf.get("items", []) if x in ids]
            if len(its) >= 2:
                res.conflicts.append({"type": "critic", "items": its, "description": cf.get("description", "")})


def _item_block(c: I.Cand, manifest: Manifest) -> str:
    it = c.item
    cites = "\n".join(f"  {manifest.by_id(s.doc).path if manifest.by_id(s.doc) else s.doc}:{s.lines[0]}-{s.lines[1]}: {s.quote}" for s in it.sources)
    return f"[{it.id}] {it.requirement} {it.check.kind} {json.dumps(it.check.params, default=str)} target={it.target.ref} none_allowed={it.none_allowed} applies_when={it.applies_when}\n{cites}"
