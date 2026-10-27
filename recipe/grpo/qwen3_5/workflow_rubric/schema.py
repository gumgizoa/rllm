"""The rubric format (``wfrubric/1``): identical for every workflow.

A rubric is the list of things the workflow's documents tell the agent to do, each one a checkable
:class:`Item` that cites the lines it comes from. What differs between workflows is data -- the
stages, the artifacts and where they live, the items -- and the ``scoring`` block, which the engine
interprets (:mod:`.aggregate`). The item schema itself never changes per workflow.

Item fields (the ones every workflow shares):

    id                unique, ``<wf>.<stage>.<target>.<check>[.<n>]``
    scope             ``common``: an instance of a common-rubric template (C-A*/C-F*) with only its
                      parameters set; ``specific``: a plugin kind (``<wf>.<name>``) or a requirement
                      no common template expresses (execution evidence, trace-bound none policies)
    cls               ``structure`` (a multiplier on the stage score, never credit by itself),
                      ``content`` or ``evidence`` (what earns the score); YAML key ``class``
    stage             a stage id, or ``global``
    target            ``{type: artifact|action, ref, state: stage_end|final}``
    check             ``{kind, params}``; kinds are registered in :mod:`.checks`
    requirement       ``must`` | ``should``
    modality_evidence the word or rule that made it must/should
    none_allowed      ``yes`` | ``no`` | ``unspecified`` | ``{if: <predicate>}`` | ``-`` (not a field)
    applies_when      a predicate (:mod:`.refs`) the engine can evaluate, or ``None``
    weight            relative weight inside its stage
    gate              ``None`` | ``{zero_stage: true}`` | ``{cap_stage: <float>}``
    availability      inputs the check needs: ``sandbox_file``, ``diff``, ``base_tree``, ``trace``
    sources           ``[{doc, lines: [a, b], quote}]`` -- ``doc`` is a source id from ``sources``
    impl_refs         references the agent cannot see (never evidence; may only relax a check)
    derived_by        ``template_compiler`` | ``llm_extract`` | ``adapter`` | ``manual``
    template          the common-rubric template it instantiates (``C-A1`` .. ``C-F11``), empty for specific
    log_only          evaluated and reported, never scored (adapter-derived items by default)
    category          optional, for the ``kind_matrix`` aggregate: ``P`` procedure, ``F`` artifact form,
                      ``E`` execution, ``C`` consistency across stages, ``R`` forbidden action, ``Q``
                      content adequacy, ``A`` report accuracy
    rule              optional, the atomic rule the item measures; items of one rule average into it
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "wfrubric/1"

SCOPES = ("common", "specific")
CLASSES = ("structure", "content", "evidence")
REQUIREMENTS = ("must", "should")
TARGET_TYPES = ("artifact", "action")
STATES = ("stage_end", "final")
NONE_ALLOWED = ("yes", "no", "unspecified", "-")
AVAILABILITY = ("sandbox_file", "diff", "base_tree", "trace")
DERIVED_BY = ("template_compiler", "llm_extract", "adapter", "manual")
SOURCE_ROLES = ("adapter", "instruction", "core", "stage_rule", "command", "skill", "template", "schema", "script", "system_prompt", "reference")
WRITE_EVENTS = ("first", "last", "last_in_window")
PROCESS_SCALES = (None, "stage_mean")  # scoring.process_scale (see aggregate)
MATRIX_KINDS = (None, "cells", "rules")  # scoring.matrix.kind (see aggregate.kind_matrix)
CATEGORIES = ("", "P", "F", "E", "C", "R", "Q", "A")  # Item.category (see aggregate.kind_matrix)
AGGREGATES = (None, "stages", "kind_matrix")  # scoring.aggregate


class RubricError(ValueError):
    """The rubric file is malformed: an infrastructure error, raised at load time only."""


@dataclass
class SourceRef:
    doc: str
    lines: tuple[int, int]
    quote: str

    @classmethod
    def from_dict(cls, d: dict) -> SourceRef:
        lines = d.get("lines") or [0, 0]
        if isinstance(lines, int):
            lines = [lines, lines]
        return cls(doc=str(d["doc"]), lines=(int(lines[0]), int(lines[-1])), quote=str(d.get("quote", "")))

    def to_dict(self) -> dict:
        return {"doc": self.doc, "lines": [self.lines[0], self.lines[1]], "quote": self.quote}


@dataclass
class Source:
    """One file the agent sees. ``path`` is relative to the workflow package directory."""

    id: str
    path: str
    role: str
    sha256: str = ""
    container_path: str = ""  # where the agent sees it, e.g. /ai-dlc/core-workflow.md
    sections: dict[str, str] = field(default_factory=dict)  # system prompt: section -> workflow|harness_generic
    upstream: dict[str, Any] = field(default_factory=dict)  # {repo, commit, path, line_map}


@dataclass
class Var:
    """A path component the run chooses (a feature directory, a change name), bound from the sandbox.

    ``under`` is a directory template; the var binds to the name of a direct child matching
    ``regex`` and not in ``exclude``. ``bind: single`` means exactly one such child is expected;
    with several, the one holding the most located artifacts wins and the binding is flagged.
    """

    name: str
    under: str
    regex: str = ".+"
    bind: str = "single"
    exclude: list[str] = field(default_factory=list)


@dataclass
class Stage:
    id: str
    doc: str | None = None  # source id of the stage's governing document
    artifacts: list[str] = field(default_factory=list)
    order_artifact: str | None = None  # the artifact whose write closes the stage in the order chain
    requires: list[str] = field(default_factory=list)  # artifact ids that must exist before this stage writes


@dataclass
class Artifact:
    """A file a stage produces. ``locations`` are path templates (``{root}``, ``{VAR}``) tried in order.

    ``exclusive``: the artifact must be found at exactly one location (OpenSpec: active XOR archived).
    ``template``: the source id of its template, for residue/copy fingerprints.
    ``write_event``: which write of the artifact is "the" write for ordering.
    """

    id: str
    locations: list[str]
    exclusive: bool = False
    template: str | None = None
    write_event: str = "last_in_window"
    optional: bool = False
    kind: str = "markdown"  # markdown | yaml | json | text | dir


@dataclass
class Check:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Target:
    type: str
    ref: str
    state: str = "final"


@dataclass
class Item:
    id: str
    scope: str
    cls: str
    stage: str
    target: Target
    check: Check
    requirement: str
    sources: list[SourceRef]
    modality_evidence: str = ""
    none_allowed: Any = "-"
    applies_when: Any = None
    weight: float = 1.0
    gate: dict[str, Any] | None = None
    availability: list[str] = field(default_factory=lambda: ["sandbox_file"])
    impl_refs: list[str] = field(default_factory=list)
    derived_by: str = "manual"
    template: str = ""
    log_only: bool = False
    note: str = ""
    category: str = ""
    rule: str = ""

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "scope": self.scope,
            "class": self.cls,
            "stage": self.stage,
            "target": asdict(self.target),
            "check": {"kind": self.check.kind, "params": self.check.params},
            "requirement": self.requirement,
            "modality_evidence": self.modality_evidence,
            "none_allowed": self.none_allowed,
            "applies_when": self.applies_when,
            "weight": self.weight,
            "gate": self.gate,
            "availability": list(self.availability),
            "sources": [s.to_dict() for s in self.sources],
            "impl_refs": list(self.impl_refs),
            "derived_by": self.derived_by,
            "template": self.template,
            "log_only": self.log_only,
            "note": self.note,
        }
        if self.category:
            d["category"] = self.category
        if self.rule:
            d["rule"] = self.rule
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Item:
        try:
            t = d["target"]
            c = d["check"]
            return cls(
                id=str(d["id"]),
                scope=str(d["scope"]),
                cls=str(d.get("class", d.get("cls"))),
                stage=str(d["stage"]),
                target=Target(type=str(t["type"]), ref=str(t["ref"]), state=str(t.get("state", "final"))),
                check=Check(kind=str(c["kind"]), params=dict(c.get("params") or {})),
                requirement=str(d["requirement"]),
                sources=[SourceRef.from_dict(s) for s in d.get("sources") or []],
                modality_evidence=str(d.get("modality_evidence", "")),
                none_allowed=d.get("none_allowed", "-"),
                applies_when=d.get("applies_when"),
                weight=float(d.get("weight", 1.0)),
                gate=d.get("gate"),
                availability=list(d.get("availability") or ["sandbox_file"]),
                impl_refs=list(d.get("impl_refs") or []),
                derived_by=str(d.get("derived_by", "manual")),
                template=str(d.get("template") or ""),
                log_only=bool(d.get("log_only", False)),
                note=str(d.get("note", "")),
                category=str(d.get("category") or ""),
                rule=str(d.get("rule") or ""),
            )
        except (KeyError, TypeError) as e:
            raise RubricError(f"item {d.get('id', '?')}: {e!r}") from None


@dataclass
class Rubric:
    workflow: str
    sources: list[Source]
    roots: dict[str, str]
    stages: list[Stage]
    artifacts: dict[str, Artifact]
    items: list[Item]
    scoring: dict[str, Any]
    vars: dict[str, Var] = field(default_factory=dict)
    generated: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)
    appendix: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA_VERSION
    path: Path | None = None  # where it was loaded from; package dir = path.parent.parent

    # -- lookups -------------------------------------------------------------------------------
    def source(self, sid: str) -> Source:
        for s in self.sources:
            if s.id == sid:
                return s
        raise KeyError(sid)

    def stage(self, sid: str) -> Stage:
        for s in self.stages:
            if s.id == sid:
                return s
        raise KeyError(sid)

    @property
    def stage_ids(self) -> list[str]:
        return [s.id for s in self.stages]

    def items_for(self, stage: str) -> list[Item]:
        return [i for i in self.items if i.stage == stage]

    # -- (de)serialisation ---------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "workflow": self.workflow,
            "generated": self.generated,
            "sources": [_drop_empty(asdict(s)) for s in self.sources],
            "roots": self.roots,
            "vars": {k: _drop_empty({kk: vv for kk, vv in asdict(v).items() if kk != "name"}) for k, v in self.vars.items()},
            "stages": [_drop_empty(asdict(s)) for s in self.stages],
            "artifacts": {k: _drop_empty({kk: vv for kk, vv in asdict(a).items() if kk != "id"}) for k, a in self.artifacts.items()},
            "items": [i.to_dict() for i in self.items],
            "scoring": self.scoring,
            "conflicts": self.conflicts,
            "appendix": self.appendix,
        }

    def dump(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True, width=120))

    @classmethod
    def from_dict(cls, d: dict, path: Path | None = None) -> Rubric:
        if d.get("schema") != SCHEMA_VERSION:
            raise RubricError(f"schema {d.get('schema')!r} is not {SCHEMA_VERSION}")
        try:
            r = cls(
                schema=d["schema"],
                workflow=str(d["workflow"]),
                generated=dict(d.get("generated") or {}),
                sources=[Source(**s) for s in d.get("sources") or []],
                roots={str(k): str(v) for k, v in (d.get("roots") or {}).items()},
                vars={k: Var(name=k, **v) for k, v in (d.get("vars") or {}).items()},
                stages=[Stage(**s) for s in d.get("stages") or []],
                artifacts={k: Artifact(id=k, **a) for k, a in (d.get("artifacts") or {}).items()},
                items=[Item.from_dict(i) for i in d.get("items") or []],
                scoring=dict(d.get("scoring") or {}),
                conflicts=list(d.get("conflicts") or []),
                appendix=dict(d.get("appendix") or {}),
                path=path,
            )
        except TypeError as e:
            raise RubricError(str(e)) from None
        validate(r)
        return r


def _drop_empty(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def load(path: str | Path) -> Rubric:
    p = Path(path)
    try:
        d = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise RubricError(f"{p}: {e}") from None
    return Rubric.from_dict(d, path=p)


def validate(r: Rubric) -> None:
    """Structural checks that need no workflow files. Kind parameters are checked by the registry."""
    errors: list[str] = []
    sids = [s.id for s in r.sources]
    if len(set(sids)) != len(sids):
        errors.append("duplicate source ids")
    for s in r.sources:
        if s.role not in SOURCE_ROLES:
            errors.append(f"source {s.id}: role {s.role!r}")
    stage_ids = [s.id for s in r.stages]
    if len(set(stage_ids)) != len(stage_ids) or "global" in stage_ids:
        errors.append("stage ids must be unique and not 'global'")
    for st in r.stages:
        if st.doc and st.doc not in sids:
            errors.append(f"stage {st.id}: doc {st.doc!r} not a source")
        for a in [*st.artifacts, *st.requires, *([st.order_artifact] if st.order_artifact else [])]:
            if a not in r.artifacts:
                errors.append(f"stage {st.id}: artifact {a!r} undefined")
    for a in r.artifacts.values():
        if not a.locations:
            errors.append(f"artifact {a.id}: no locations")
        if a.write_event not in WRITE_EVENTS:
            errors.append(f"artifact {a.id}: write_event {a.write_event!r}")
        if a.template and a.template not in sids:
            errors.append(f"artifact {a.id}: template {a.template!r} not a source")
    ids = [i.id for i in r.items]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        errors.append(f"duplicate item ids: {dup[:5]}")
    for i in r.items:
        where = f"item {i.id}"
        if i.scope not in SCOPES:
            errors.append(f"{where}: scope {i.scope!r}")
        if i.cls not in CLASSES:
            errors.append(f"{where}: class {i.cls!r}")
        if i.requirement not in REQUIREMENTS:
            errors.append(f"{where}: requirement {i.requirement!r}")
        if i.stage != "global" and i.stage not in stage_ids:
            errors.append(f"{where}: stage {i.stage!r}")
        if i.target.type not in TARGET_TYPES or i.target.state not in STATES:
            errors.append(f"{where}: target {i.target}")
        if i.target.type == "artifact" and i.target.ref not in r.artifacts:
            errors.append(f"{where}: artifact {i.target.ref!r} undefined")
        if not (isinstance(i.none_allowed, dict) and "if" in i.none_allowed) and i.none_allowed not in NONE_ALLOWED:
            errors.append(f"{where}: none_allowed {i.none_allowed!r}")
        if any(a not in AVAILABILITY for a in i.availability):
            errors.append(f"{where}: availability {i.availability}")
        if i.derived_by not in DERIVED_BY:
            errors.append(f"{where}: derived_by {i.derived_by!r}")
        if not i.sources:
            errors.append(f"{where}: no sources")
        for s in i.sources:
            if s.doc not in sids:
                errors.append(f"{where}: source doc {s.doc!r} not in sources")
        if i.template and not re.fullmatch(r"C-[AF]\d+", i.template):
            errors.append(f"{where}: template {i.template!r}")
        if i.gate and not set(i.gate) <= {"zero_stage", "cap_stage"}:
            errors.append(f"{where}: gate {i.gate}")
        if i.category not in CATEGORIES:
            errors.append(f"{where}: category {i.category!r}")
    if (r.scoring or {}).get("aggregate") not in AGGREGATES:
        errors.append(f"scoring.aggregate {(r.scoring or {}).get('aggregate')!r} (one of {AGGREGATES[1:]})")
    if (r.scoring or {}).get("aggregate") == "kind_matrix" and any(not i.category for i in r.items if not i.log_only):
        errors.append("scoring.aggregate kind_matrix: every scored item needs a category")
    kind = ((r.scoring or {}).get("matrix") or {}).get("kind")
    if kind not in MATRIX_KINDS:
        errors.append(f"scoring.matrix.kind {kind!r} (one of {MATRIX_KINDS[1:]})")
    scale = (r.scoring or {}).get("process_scale")
    if scale not in PROCESS_SCALES:
        errors.append(f"scoring.process_scale {scale!r} (one of {PROCESS_SCALES[1:]})")
    if errors:
        raise RubricError("; ".join(errors[:20]) + (f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""))
