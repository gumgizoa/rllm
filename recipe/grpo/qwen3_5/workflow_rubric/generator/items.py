"""Candidate items: a ``schema.Item`` plus what the generator knows about where it came from.

Every stage that proposes items (G2 templates, G5 mapping, G7 coverage, manual config, the stage
model) yields :class:`Cand`; G6 accepts or rejects them and G8 turns the survivors into rubric
items. The extra fields never reach ``rubric.yaml`` except through ``note``/``modality_evidence``:
they exist so a rejection or a dedup decision can be explained in the generator's logs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..schema import Check, Item, SourceRef, Target

ORIGINS = ("template", "llm", "critic", "manual", "stage")


@dataclass
class Cand:
    item: Item
    origin: str
    statement: str = ""  # G4 statement id this came from
    downgrade_reason: str = ""  # why the requirement is below the dictionary modality (G2 marker, model reason)
    log: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.item.id

    def key(self) -> str:
        """Identity for exact dedup: kind, target, params, none policy, condition."""
        it = self.item
        own = self.statement if it.check.kind == "unimplemented" else ""  # each unimplemented statement is reported on its own
        return json.dumps([it.check.kind, it.target.type, it.target.ref, it.target.state, it.stage, it.check.params, it.none_allowed, it.applies_when, own], sort_keys=True, default=str)

    def subject(self) -> tuple[str, str] | None:
        p = self.item.check.params
        sec = p.get("section") or p.get("heading")
        if sec is None:
            return None
        return (str(sec).strip().lower(), str(p.get("label", "")).strip().lower())

    def lines(self) -> set[tuple[str, int]]:
        return {(s.doc, n) for s in self.item.sources for n in range(s.lines[0], s.lines[1] + 1)}

    def to_json(self) -> dict:
        return {"item": self.item.to_dict(), "origin": self.origin, "statement": self.statement, "downgrade_reason": self.downgrade_reason, "log": list(self.log)}

    @classmethod
    def from_json(cls, d: dict) -> Cand:
        return cls(item=Item.from_dict(d["item"]), origin=d["origin"], statement=d.get("statement", ""), downgrade_reason=d.get("downgrade_reason", ""), log=list(d.get("log", [])))


def make(
    id: str,
    kind: str,
    params: dict,
    *,
    stage: str,
    target: tuple[str, str, str],
    requirement: str,
    sources: list[SourceRef],
    cls: str,
    origin: str,
    derived_by: str,
    none_allowed="-",
    applies_when=None,
    modality_evidence: str = "",
    availability: list[str] | None = None,
    note: str = "",
    statement: str = "",
    downgrade_reason: str = "",
    impl_refs: list[str] | None = None,
) -> Cand:
    it = Item(
        id=id,
        scope="common",
        cls=cls,
        stage=stage,
        target=Target(type=target[0], ref=target[1], state=target[2]),
        check=Check(kind=kind, params=dict(params)),
        requirement=requirement,
        sources=list(sources),
        modality_evidence=modality_evidence,
        none_allowed=none_allowed,
        applies_when=applies_when,
        availability=list(availability or ["sandbox_file"]),
        derived_by=derived_by,
        note=note,
        impl_refs=list(impl_refs or []),
    )
    return Cand(item=it, origin=origin, statement=statement, downgrade_reason=downgrade_reason)


def dump(cands: list[Cand]) -> list[dict]:
    return [c.to_json() for c in cands]


def load(rows: list[dict]) -> list[Cand]:
    return [Cand.from_json(r) for r in rows]
