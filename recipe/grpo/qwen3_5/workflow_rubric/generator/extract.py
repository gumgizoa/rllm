"""G3-G5: the model-assisted stages, each constrained to an answer the rules can check.

G3 (stage model)  stages, artifacts, roots, vars from the entry / adapter / stage documents. A
                  ``stage_model.fixed`` block in generator.yaml wins key by key; when it is complete
                  no model is asked. Paths are validated against the manifest.
G4 (statements)   the normative sentences of every prose source, chunk by chunk, in the pilot
                  ``notes/*.statements.jsonl`` format so recall can be measured against the pilots.
                  Quotes that do not match their lines are dropped here already.
G5 (mapping)      statement -> items in the closed kind vocabulary (:mod:`.vocab`). Asked
                  ``samples`` times independently; an item survives when a majority of samples
                  proposes it (same kind, target and key parameters); a statement whose samples
                  disagree becomes one ``unimplemented`` item (weight 0, reported).

Nothing here decides acceptance: every candidate goes through G6 (:mod:`.ground`).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field

from ..schema import AVAILABILITY, CLASSES, SourceRef
from . import items as I
from .config import GeneratorConfig, parse_ref
from .llm import LLM, LLMError
from .manifest import Entry, Manifest
from .parse import Parsed
from .vocab import KindSpec, kind_table_text

logger = logging.getLogger(__name__)

PILOT_KINDS = [
    "other", "order", "read_doc", "artifact_exists", "path_name", "tool_or_command", "placeholder_forbidden", "cross_artifact", "structure",
    "frontmatter", "enum", "execution_evidence", "checklist", "section", "field_label", "field_value",
]  # fmt: skip
PILOT_MODALITIES = ["must", "should", "may", "prohibition", "implicit"]
REF_SCHEMA = {
    "type": "object",
    "required": ["path", "lines", "quote"],
    "properties": {"path": {"type": "string"}, "lines": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}, "quote": {"type": "string"}},
}
PROSE_ROLES = ("adapter", "instruction", "core", "stage_rule", "command", "skill", "schema", "system_prompt", "reference")
KEY_PARAMS = ("section", "label", "heading", "doc", "mode", "action", "kind", "type", "relation", "artifact", "chain", "before", "after")

REFS_SUMMARY = """Reference language (the engine evaluates only these):
Events: start | end | read:<SOURCE_ID> | write:<ARTIFACT_ID> | first_write:<ARTIFACT_ID> | last_write:<ARTIFACT_ID> | first_repo_write | last_repo_write
  | last_change_write (last edit of a code/config file that stays in the final change; scratch files written and removed do not count)
  | stage_start:<STAGE> | stage_end:<STAGE>
  | {first: <fact query>} | {last: <fact query>} (first / last record of an exists-query, e.g. the first edit of a file that existed
    at BASE_SHA: {first: {fact: repo_edit, created: false}}; an unseen matching repo change makes it unknown)
Windows: "stage:<STAGE>" | [<start>, <end>] (half-open) | omitted (= the item's stage window, or the whole run for global items).
  A start may be a list [[e1, e2], end]: the LATEST of those that happened; an end may be a list [start, [e1, e2, end]]: the EARLIEST
  of those that happened (e.g. [stage_start:S, [write:A, {first: {...}}]] = in stage S, before A was written and before the first edit).
  An event that did not happen makes a plain bound empty.
Selectors (one key, optional normalize: path|command|id|text; command compares spellings of one invocation as equal --
  python -m pytest == pytest, python3 == python, /testbed/ prefixes, timeout/env wrappers, `cd X &&`, `| tail`):
  {field: {artifact, section, label, state?}} {field_list: {...}} {section_text: {artifact, section}} {section_lines: {artifact, section}}
  {ids: {artifact, section?, pattern, group?}} {headings: {artifact, level, pattern, group?}}
  {keyed_ids: {artifact, section?, pattern, key?=1, ids?=2, item?}} (one "key|ID,ID" per match: compares e.g. a step number WITH its tags)
  {fact: diff_paths|diff_test_paths|untracked_paths|repo_write_paths|run_commands|valid_run_commands|run_ids|base_paths} or
  {fact: {name, window?, kind?, final?}} (final: true on repo_write_paths = only paths still in the final change)
  {literal: [..]}
  state: final (default, the sandbox file) | stage_end (the artifact as it was when its stage ended)
  Where a filter takes a selector (paths_in, paths_not_in, failures_not_in) a LIST of selectors is their union.
Predicates (applies_when, none_allowed {if: P}, field_literal.refuted_by):
  {exists|absent: {fact: valid_run|run_attempt|repo_edit|artifact_write|doc_read|exec_of|command, window?, filters}}
     filters: valid_run/run_attempt: kind, command_in (selector), targets_in (selector);
     repo_edit: paths_in, paths_not_in (selectors), test_paths (bool), final (bool: the path is part of the final change),
       created (bool: the path is new, not in BASE_SHA);
     artifact_write: artifact; doc_read: doc, min_coverage; exec_of: selector; command: pattern (regex)
  {counts: {fact: valid_run, window?, which: first|last|any|all, passed?, failed?, errors?, failed_or_errors?, collected_min?,
     failures_not_in? (selector or list: the run has a failing test those values name nowhere)}}
  {field_is_none|field_present: {artifact, section, label}} {field_matches: {artifact, section, label, pattern}} {artifact_exists: <ARTIFACT_ID>}
  {relation: {left: <selector>, right: <selector>, rel: subset|superset|equal|intersects|disjoint}} {all: [..]} {any: [..]} {not: P} true false
A valid run (exec_evidence, valid_run, field_type run_kind) is a runner invocation whose own output reports >= 1 test run, on targets
the repository had at BASE_SHA: echo/printf summaries, /tmp dummy tests, agent-written runners, zero-test runs and runs that only failed
to load their selection (import / collection errors) are not.
A none value: the whole value is a none word, a none word + a delimiter + an explanation, or a none claim without a delimiter
("None recorded", "none identified", "No deviations"); values with the field's own structure (an arrow) are content."""

RULES_SUMMARY = """Rules every item must satisfy (a rule checker rejects items that break them):
1. sources: cite the line range (path as given, [first, last]) and a quote copied VERBATIM from those lines (whitespace may differ; use "..." to elide).
2. Every literal parameter (heading, section, label, text, enum values, frontmatter keys/values, literal parts of regexes) must appear
   character for character in the cited lines or in the artifact's template. Do not invent regexes beyond what the document's own examples need.
3. requirement: "must" only if the cited sentence carries MUST/required/mandatory/NEVER/do not/an imperative; SHOULD/prefer -> "should";
   MAY/optional/if applicable -> no item (list it under unitemized); implicit (inferred, not stated) -> at most "should".
   You may lower must to should only with a downgrade_reason.
4. Items resting only on adapter/instruction text (documents written for this harness, not the workflow's own) are at most should,
   and may not be frontmatter/section_present/field_literal/field_enum/prohibited_action.
5. none_allowed (field items only): "yes" if the document offers a none alternative, "no" only if it explicitly demands content,
   "unspecified" if silent, {"if": <predicate>} when the document ties "none" to something observable; "-" for non-field items.
6. cross_ref must involve at least one side the agent did not write (a fact selector or a literal), else it will be downgraded.
7. applies_when must be a predicate from the reference language; conditions you cannot express -> leave the statement unitemized.
8. Use kind "unimplemented" when no kind can check the statement but it is checkable in principle.
9. Content examples (sample artifact text) are not requirements: do not turn example lines into items.
10. The template skeletons are already compiled into items (see TEMPLATE SECTIONS / LABELS): every heading, label, frontmatter key,
   fixed line, placeholder residue and the plain "this label's value is filled" check. Do not emit those again. For a template field emit
   an item only when the statement adds a rule the skeleton alone does not: a value tied to the run (field_type), "none" allowed only
   under an observable condition (none_allowed {"if": ...}), a cross-reference between artifacts or to the run (cross_ref), a fixed phrase
   the run can refute (field_literal with refuted_by). Most statements yield 0-2 items.
11. "statement" (in items and unitemized) is the bracketed id of the statement, e.g. "re-007".
12. A value the run must back is judged on what had happened when the agent wrote it: end its window at the artifact's write
   (write:<ARTIFACT>, alone or in an end list). "Before any source change" is the first edit of a file that existed at BASE_SHA
   ({first: {fact: repo_edit, created: false}}), not the first repo write (a new scratch or reproduction file changes no source);
   add "end" to the end list when the run may make no edit at all. A recorded command is checked against a VALID run (run_kind),
   recorded failures against failing tests (failed_test_id), a step and its tags as a pair (keyed_ids), files left behind against
   untracked_paths."""


@dataclass
class Statement:
    id: str
    file: str
    line_start: int
    line_end: int
    quote: str
    modality: str
    kind: str
    stage: str
    target: str
    checkable_by_rule: str
    none_allowed: str
    notes: str
    source: str = ""
    path: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)


@dataclass
class MapResult:
    cands: list[I.Cand] = field(default_factory=list)
    unitemized: list[dict] = field(default_factory=list)
    log: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------------------------
# G3
# ----------------------------------------------------------------------------------------------
STAGE_PROMPT = """You read the documents of a software-engineering workflow that an agent follows inside a sandbox and extract its stage model:
the ordered stages, the document that governs each stage, the files (artifacts) each stage writes, where they live, and path variables.
Use ids that are short snake_case. Locations are path templates using {root} placeholders: {artifact} for the artifact root, {code} for the
repository root ({WORKDIR} at run time), and {VAR} for variables (a directory name the run chooses, bound from a regex). Cite for every stage
and artifact the line that names it (path, [first, last], verbatim quote). Doc and template fields are file paths exactly as listed.
Follow the hints if any; do not invent stages the documents do not describe."""


def stage_schema() -> dict:
    return {
        "type": "object",
        "required": ["roots", "vars", "stages", "artifacts"],
        "properties": {
            "roots": {"type": "object", "required": ["artifact"], "properties": {"artifact": {"type": "string"}, "code": {"type": "string"}}},
            "vars": {
                "type": "array",
                "items": {"type": "object", "required": ["name", "under", "regex"], "properties": {"name": {"type": "string"}, "under": {"type": "string"}, "regex": {"type": "string"}}},
            },
            "stages": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["id", "doc", "artifacts", "source"],
                    "properties": {
                        "id": {"type": "string"},
                        "doc": {"type": "string"},
                        "artifacts": {"type": "array", "items": {"type": "string"}},
                        "order_artifact": {"type": "string"},
                        "requires": {"type": "array", "items": {"type": "string"}},
                        "source": REF_SCHEMA,
                    },
                },
            },
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "locations", "source"],
                    "properties": {
                        "id": {"type": "string"},
                        "locations": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "template": {"type": "string"},
                        "exclusive": {"type": "boolean"},
                        "optional": {"type": "boolean"},
                        "kind": {"type": "string", "enum": ["markdown", "yaml", "json", "text", "dir"]},
                        "source": REF_SCHEMA,
                    },
                },
            },
        },
    }


def stage_model(cfg: GeneratorConfig, manifest: Manifest, llm: LLM | None) -> tuple[dict, list[str]]:
    """The stage model in rubric form (source ids), with ``origin`` and per-stage/artifact ``sources``."""
    log: list[str] = []
    fixed = cfg.stage_model.get("fixed") or {}
    complete = bool(fixed.get("stages")) and bool(fixed.get("artifacts")) and bool(fixed.get("roots"))
    raw: dict = {}
    origin = "fixed"
    if not complete:
        if llm is None or not llm.enabled:
            raise LLMError("stage_model.fixed is incomplete and no LLM backend is available (G3)")
        docs = [e for e in manifest.entries if e.role in ("core", "adapter", "instruction", "stage_rule", "command", "skill", "schema") or (e.role == "system_prompt")]
        user = "HINTS:\n" + "\n".join(f"- {h}" for h in cfg.stage_model.get("hints", []) or ["(none)"]) + "\n\nTEMPLATE FILES: " + ", ".join(e.path for e in manifest.entries if e.role == "template")
        user += "\n\n" + "\n\n".join(numbered(e, sp_workflow_only=True) for e in docs)
        ans = llm.ask(STAGE_PROMPT, user, stage_schema())
        raw = {
            "roots": ans.get("roots", {}),
            "vars": {v["name"]: {k: v[k] for k in ("under", "regex", "bind", "exclude") if k in v} for v in ans.get("vars", [])},
            "stages": ans.get("stages", []),
            "artifacts": {a["id"]: {k: v for k, v in a.items() if k != "id"} for a in ans.get("artifacts", [])},
        }
        origin = "llm" if not fixed else "merged"
    model = {**raw}
    for k in ("roots", "vars"):
        if k in fixed:
            model[k] = fixed[k]
    if fixed.get("stages"):
        model["stages"] = fixed["stages"]
    if fixed.get("artifacts"):
        model["artifacts"] = {**(raw.get("artifacts") or {}), **fixed["artifacts"]}
    return _normalize_stage_model(model, manifest, origin, log), log


def _normalize_stage_model(m: dict, manifest: Manifest, origin: str, log: list[str]) -> dict:
    out = {"roots": {str(k): str(v) for k, v in (m.get("roots") or {}).items()}, "vars": {}, "stages": [], "artifacts": {}, "origin": origin}
    for name, v in (m.get("vars") or {}).items():
        if not isinstance(v, dict) or not v.get("under"):
            log.append(f"stage model: var {name} dropped (no 'under')")
            continue
        out["vars"][str(name)] = {k: v[k] for k in ("under", "regex", "bind", "exclude") if k in v}
    for aid, a in (m.get("artifacts") or {}).items():
        locs = [str(x) for x in a.get("locations") or []]
        bad = [x for x in locs if not (x.startswith("/") or x.startswith("{"))]
        if not locs or bad:
            log.append(f"stage model: artifact {aid} dropped (locations {locs})")
            continue
        art = {"locations": locs}
        if a.get("template"):
            e = manifest.resolve(str(a["template"]))
            if e is None:
                log.append(f"stage model: artifact {aid}: template {a['template']} not in the manifest (dropped the template)")
            else:
                art["template"] = e.id
        for k in ("exclusive", "optional"):
            if a.get(k):
                art[k] = bool(a[k])
        if a.get("kind") and a["kind"] != "markdown":
            art["kind"] = a["kind"]
        if a.get("write_event"):
            art["write_event"] = a["write_event"]
        art["sources"] = _refs(a.get("source") or a.get("sources"), manifest, log, f"artifact {aid}")
        out["artifacts"][str(aid)] = art
    for s in m.get("stages") or []:
        sid = str(s.get("id"))
        st = {"id": sid, "artifacts": [a for a in s.get("artifacts") or [] if a in out["artifacts"]], "requires": [a for a in s.get("requires") or [] if a in out["artifacts"]]}
        if s.get("doc"):
            e = manifest.resolve(str(s["doc"]))
            if e is None:
                log.append(f"stage model: stage {sid}: doc {s['doc']} not in the manifest")
            else:
                st["doc"] = e.id
        oa = s.get("order_artifact")
        if oa and oa in out["artifacts"]:
            st["order_artifact"] = oa
        st["sources"] = _refs(s.get("source") or s.get("sources"), manifest, log, f"stage {sid}")
        out["stages"].append(st)
    return out


def _refs(obj, manifest: Manifest, log: list[str], where: str) -> list[dict]:
    if obj is None:
        return []
    out = []
    for r in obj if isinstance(obj, list) else [obj]:
        try:
            ref = parse_ref(r, where)
        except ValueError as e:
            log.append(f"stage model: {e}")
            continue
        e = manifest.resolve(ref.path)
        if e is None:
            log.append(f"stage model: {where}: {ref.path} not in the manifest")
            continue
        out.append({"doc": e.id, "lines": [ref.lines[0], ref.lines[1]], "quote": ref.quote or e.text(*ref.lines).strip()})
    return out


# ----------------------------------------------------------------------------------------------
# G4
# ----------------------------------------------------------------------------------------------
STATEMENT_PROMPT = """You extract normative statements from one chunk of a workflow document that an AI agent must follow.
A normative statement says what the agent must, should, may or must not do, or what an artifact must contain. Return one statement per
requirement (split compound sentences), each with the line range and a quote copied verbatim from those lines (use "..." to elide).
modality: must | should | may | prohibition | implicit (inferred, not stated). Lines prefixed with "f" are inside fenced blocks
(skeletons/examples): do not extract statements from them. The candidate list (modal sentences found by a dictionary) is a floor, not a
ceiling: also extract imperative instructions and requirements stated as facts. stage: one of the given stage ids, or "global"."""


def statement_schema(stages: list[str]) -> dict:
    item = {
        "type": "object",
        "required": ["line_start", "line_end", "quote", "modality", "kind", "stage", "target", "checkable_by_rule", "none_allowed", "notes"],
        "properties": {
            "line_start": {"type": "integer"},
            "line_end": {"type": "integer"},
            "quote": {"type": "string"},
            "modality": {"type": "string", "enum": PILOT_MODALITIES},
            "kind": {"type": "string", "enum": PILOT_KINDS},
            "stage": {"type": "string", "enum": [*stages, "global"]},
            "target": {"type": "string"},
            "checkable_by_rule": {"type": "string", "enum": ["yes", "partial", "no"]},
            "none_allowed": {"type": "string", "enum": ["yes", "no", "unspecified", "-"]},
            "notes": {"type": "string"},
        },
    }
    return {"type": "object", "required": ["statements"], "properties": {"statements": {"type": "array", "items": item}}}


def statements(cfg: GeneratorConfig, manifest: Manifest, parsed: dict[str, Parsed], model: dict, llm: LLM) -> tuple[list[Statement], list[str]]:
    from .ground import quote_matches

    log: list[str] = []
    out: list[Statement] = []
    stages = [s["id"] for s in model.get("stages", [])]
    schema = statement_schema(stages)
    jobs: list[tuple[Entry, int, int]] = []
    asks: list[tuple[str, str, dict, str]] = []
    for e in manifest.entries:
        if e.role not in PROSE_ROLES or e.binary:
            continue
        p = parsed.get(e.id)
        for a, b in chunks(e, p, cfg.llm.chunk_lines):
            cands = [c for c in (p.candidates if p else []) if a <= c.line_start <= b]
            user = (
                f"STAGES: {', '.join(stages)}\n\n"
                + numbered(e, a, b, p)
                + "\n\nCANDIDATES:\n"
                + ("\n".join(f"- {c.line_start}-{c.line_end} {c.modality} ({c.modality_evidence}): {c.text}" for c in cands) or "(none)")
            )
            jobs.append((e, a, b))
            asks.append((STATEMENT_PROMPT, user, schema, ""))
    counts: dict[str, int] = {}
    for (e, a, b), ans in zip(jobs, llm.ask_many(asks, cfg.llm.parallel), strict=True):
        if isinstance(ans, LLMError):
            log.append(f"G4 {e.path}:{a}-{b}: {ans}")
            continue
        for s in ans.get("statements", []):
            la, lb = int(s["line_start"]), int(s["line_end"])
            if not (a <= la <= lb <= b) or not quote_matches(s["quote"], e.text(la, lb)):
                log.append(f"G4 {e.path}:{la}-{lb}: quote does not match its lines; dropped: {s['quote'][:80]!r}")
                continue
            n = counts[e.id] = counts.get(e.id, 0) + 1
            out.append(
                Statement(
                    id=f"{e.id.lower()}-{n:03d}",
                    file=e.abs_path,
                    source=e.id,
                    path=e.path,
                    **{k: s[k] for k in ("line_start", "line_end", "quote", "modality", "kind", "stage", "target", "checkable_by_rule", "none_allowed", "notes")},
                )
            )
    return out, log


def chunks(e: Entry, p: Parsed | None, size: int) -> list[tuple[int, int]]:
    """Line ranges of about ``size`` lines, cut at headings where possible; system prompts: workflow sections only."""
    n = len(e.lines())
    if e.role == "system_prompt":
        rng = [tuple(v) for k, v in e.section_lines.items() if e.sections.get(k) == "workflow"]
        return [(a, b) for a, b in rng if b >= a]
    cuts = sorted({h[0] for h in (p.headings if p else [])} | {1})
    out, start = [], 1
    for c in cuts[1:] + [n + 1]:
        if c - start >= size:
            out.append((start, c - 1))
            start = c
    if start <= n:
        out.append((start, n))
    final = []
    for a, b in out:  # a section longer than size is split at size
        while b - a + 1 > size * 2:
            final.append((a, a + size - 1))
            a += size
        final.append((a, b))
    return final


def numbered(e: Entry, a: int = 1, b: int | None = None, p: Parsed | None = None, sp_workflow_only: bool = False) -> str:
    lines = e.lines()
    b = len(lines) if b is None else b
    fenced = {k for f in (p.fences if p else []) for k in range(f[0], f[1] + 1)}
    head = f"FILE {e.path} (role {e.role}" + (f", seen at {e.container_path}" if e.container_path else "") + f") lines {a}-{b}:"
    rows = []
    for k in range(a, b + 1):
        if sp_workflow_only and e.role == "system_prompt" and e.section_role(k) != "workflow":
            continue
        rows.append(f"{'f' if k in fenced else ' '}{k:4d}| {lines[k - 1]}")
    return head + "\n" + "\n".join(rows)


def write_jsonl(path, rows: list[Statement]) -> None:
    with open(path, "w") as f:
        for s in rows:
            f.write(json.dumps(s.to_json(), ensure_ascii=False) + "\n")


def read_jsonl(path) -> list[Statement]:
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                out.append(Statement(**{k: d.get(k, "") for k in Statement.__dataclass_fields__}))
    return out


# ----------------------------------------------------------------------------------------------
# G5
# ----------------------------------------------------------------------------------------------
MAP_PROMPT = """You turn normative statements of a workflow into checkable rubric items for a deterministic rule engine.
Each item uses exactly one kind from the closed vocabulary below, with only the parameters that kind accepts (* = required).
A statement may yield several items (one per checkable sub-rule) or none (list it under unitemized with the reason).

{kinds}

{refs}

{rules}"""


def map_schema(kinds: dict[str, KindSpec], stages: list[str], artifacts: list[str], ids: list[str] | None = None) -> dict:
    sid = {"type": "string", **({"enum": list(ids)} if ids else {})}  # the batch's statement ids: votes are counted per id
    item = {
        "type": "object",
        "required": ["statement", "kind", "params", "requirement", "class", "stage", "target", "sources"],
        "properties": {
            "statement": sid,
            "kind": {"type": "string", "enum": [*sorted(kinds), "unimplemented"]},
            "params": {"type": "object"},
            "requirement": {"type": "string", "enum": ["must", "should"]},
            "downgrade_reason": {"type": "string"},
            "none_allowed": {},
            "applies_when": {},
            "class": {"type": "string", "enum": list(CLASSES)},
            "stage": {"type": "string", "enum": [*stages, "global"]},
            "target": {
                "type": "object",
                "required": ["type", "ref"],
                "properties": {"type": {"type": "string", "enum": ["artifact", "action"]}, "ref": {"type": "string"}, "state": {"type": "string", "enum": ["stage_end", "final"]}},
            },
            "sources": {"type": "array", "minItems": 1, "items": REF_SCHEMA},
            "availability": {"type": "array", "items": {"type": "string", "enum": list(AVAILABILITY)}},
            "impl_refs": {"type": "array", "items": {"type": "string"}},
            "note": {"type": "string"},
        },
    }
    un = {"type": "object", "required": ["statement", "reason"], "properties": {"statement": sid, "reason": {"type": "string"}}}
    return {"type": "object", "required": ["items", "unitemized"], "properties": {"items": {"type": "array", "items": item}, "unitemized": {"type": "array", "items": un}}}


def model_context(model: dict, manifest: Manifest, template_cands: list[I.Cand]) -> str:
    rows = ["STAGES (in order):"]
    for s in model.get("stages", []):
        doc = manifest.by_id(s.get("doc", "")) if s.get("doc") else None
        rows.append(f"- {s['id']}: doc {s.get('doc', '-')} ({doc.container_path or doc.path if doc else '-'}), writes {s.get('artifacts', [])}, order_artifact {s.get('order_artifact', '-')}")
    rows.append("ARTIFACTS:")
    for aid, a in model.get("artifacts", {}).items():
        rows.append(f"- {aid}: {a['locations']} template {a.get('template', '-')}")
    rows.append("SOURCES (id: path, container path, role):")
    rows += [f"- {e.id}: {e.path} {e.container_path} {e.role}" for e in manifest.entries]
    secs: dict[str, set[str]] = {}
    for c in template_cands:
        p = c.item.check.params
        if c.item.target.type == "artifact" and p.get("section"):
            secs.setdefault(c.item.target.ref, set()).add(f"{p['section']}" + (f" / {p['label']}" if p.get("label") else ""))
    if secs:
        rows.append("TEMPLATE SECTIONS / LABELS already compiled from skeletons (use these exact strings):")
        rows += [f"- {aid}: " + "; ".join(sorted(v)) for aid, v in secs.items()]
    return "\n".join(rows)


def map_items(
    stmts: list[Statement],
    cfg: GeneratorConfig,
    manifest: Manifest,
    model: dict,
    kinds: dict[str, KindSpec],
    llm: LLM,
    template_cands: list[I.Cand],
    salt: str = "",
) -> MapResult:
    res = MapResult()
    if not stmts:
        return res
    stages = [s["id"] for s in model.get("stages", [])]
    prompt = MAP_PROMPT.format(kinds=kind_table_text(kinds), refs=REFS_SUMMARY, rules=RULES_SUMMARY)
    ctx = model_context(model, manifest, template_cands)
    by_id = {s.id: s for s in stmts}
    todo = []
    for s in stmts:
        if str(s.checkable_by_rule).lower() == "no":  # G7's coverage skips these too: nothing a rule could check
            why = f"G4: not checkable by rule ({s.notes[:120]})"
            res.unitemized.append({"statement": s.id, "doc": s.source, "lines": [s.line_start, s.line_end], "quote": s.quote, "modality": s.modality, "reason": why})
        else:
            todo.append(s)
    batches = [todo[i : i + max(1, cfg.llm.batch)] for i in range(0, len(todo), max(1, cfg.llm.batch))]
    asks = []
    for batch in batches:
        user = ctx + "\n\nSTATEMENTS:\n" + "\n\n".join(_statement_block(s, manifest) for s in batch)
        bschema = map_schema(kinds, stages, list(model.get("artifacts", {})), [s.id for s in batch])
        asks += [(prompt, user, bschema, f"{salt}sample{k}") for k in range(cfg.llm.samples)]
    answers = llm.ask_many(asks, cfg.llm.parallel)
    for bi, batch in enumerate(batches):
        samples: list[dict] = []
        for k in range(cfg.llm.samples):
            ans = answers[bi * cfg.llm.samples + k]
            if isinstance(ans, LLMError):
                res.log.append(f"G5 batch {batch[0].id}..: sample {k}: {ans}")
            else:
                samples.append(ans)
        if not samples:
            continue
        for s in batch:
            _vote(s, samples, cfg.llm.samples, manifest, kinds, res, by_id)
    return res


def _statement_block(s: Statement, manifest: Manifest) -> str:
    e = manifest.by_id(s.source) or manifest.by_path(s.path or s.file)
    ctx = ""
    if e is not None:
        a, b = max(1, s.line_start - 2), min(len(e.lines()), s.line_end + 2)
        ctx = "\n".join(f"  {k:4d}| {e.lines()[k - 1]}" for k in range(a, b + 1))
    return f"[{s.id}] {s.path or s.file}:{s.line_start}-{s.line_end} modality={s.modality} kind={s.kind} stage={s.stage} target={s.target}\n  quote: {s.quote}\n  notes: {s.notes}\n{ctx}"


def _key(it: dict) -> str:
    p = it.get("params") or {}
    t = it.get("target") or {}
    return json.dumps([it.get("kind"), t.get("type"), t.get("ref"), it.get("stage"), {k: p.get(k) for k in KEY_PARAMS if k in p}], sort_keys=True, default=str)


def _full(it: dict) -> str:
    return json.dumps([it.get("params"), it.get("none_allowed", "-"), it.get("applies_when"), (it.get("target") or {}).get("state", "final")], sort_keys=True, default=str)


def _vote(s: Statement, samples: list[dict], n_samples: int, manifest: Manifest, kinds: dict[str, KindSpec], res: MapResult, by_id: dict) -> None:
    need = n_samples // 2 + 1  # a strict majority: 2 of 3, both of 2
    per_sample = [[it for it in (smp.get("items") or []) if it.get("statement") == s.id] for smp in samples]
    unit = [u for smp in samples for u in (smp.get("unitemized") or []) if u.get("statement") == s.id]
    counts: Counter = Counter()
    members: dict[str, list[dict]] = {}
    for its in per_sample:
        seen = set()
        for it in its:
            k = _key(it)
            members.setdefault(k, []).append(it)
            if k not in seen:
                counts[k] += 1
                seen.add(k)
    accepted = [k for k, c in counts.items() if c >= need]
    if not accepted:
        if any(per_sample):
            variants = sorted({json.loads(k)[0] for k in counts})
            res.cands.append(_unimplemented(s, manifest, f"no majority among {len(samples)} samples (kinds {variants})"))
        elif unit:
            res.unitemized.append({"statement": s.id, "doc": s.source, "lines": [s.line_start, s.line_end], "quote": s.quote, "modality": s.modality, "reason": unit[0].get("reason", "")})
        return
    for n, k in enumerate(sorted(accepted, key=lambda x: -counts[x])):
        group = members[k]
        full = Counter(_full(it) for it in group)
        top = full.most_common(1)[0][1]
        rep = next(it for it in group if full[_full(it)] == top)
        reqs = Counter(it.get("requirement", "should") for it in group)
        req = "must" if reqs["must"] > reqs["should"] else "should"
        reason = rep.get("downgrade_reason", "") if req == "should" else ""
        if req == "should" and not reason and reqs["must"] == reqs["should"]:
            reason = "samples split must/should"
        res.cands.append(_cand(s, rep, req, reason, n, manifest, kinds, f"votes {counts[k]}/{len(samples)}"))


def _cand(s: Statement, it: dict, req: str, reason: str, n: int, manifest: Manifest, kinds: dict[str, KindSpec], note: str) -> I.Cand:
    srcs = []
    for r in it.get("sources") or []:
        e = manifest.resolve(str(r.get("path", "")))
        lines = r.get("lines") or [s.line_start, s.line_end]
        srcs.append(SourceRef(doc=e.id if e else str(r.get("path", "")), lines=(int(lines[0]), int(lines[-1])), quote=str(r.get("quote", ""))))
    kind = str(it.get("kind"))
    ks = kinds.get(kind)
    t = it.get("target") or {}
    c = I.make(
        f"g5.{s.id}.{n}",
        kind,
        dict(it.get("params") or {}),
        stage=str(it.get("stage") or s.stage or "global"),
        target=(str(t.get("type", "action")), str(t.get("ref", "")), str(t.get("state", "final"))),
        requirement=req,
        sources=srcs,
        cls=str(it.get("class") or (ks.cls if ks else "content")),
        origin="llm",
        derived_by="llm_extract",
        none_allowed=it.get("none_allowed", "-") if it.get("none_allowed") not in (None, "") else "-",
        applies_when=_condition(it.get("applies_when")),
        modality_evidence=f"statement {s.id} ({s.modality})",
        availability=list(it.get("availability") or (ks.availability if ks else ["sandbox_file"])),
        note=" ".join(x for x in (str(it.get("note", "")), note) if x),
        statement=s.id,
        downgrade_reason=reason,
        impl_refs=[str(x) for x in it.get("impl_refs") or []],
    )
    return c


_NO_CONDITION = ("", "-", "none", "null", "always", "true")


def _condition(v):
    """A model's ``applies_when``: a predicate, or one of the ways it says "unconditional" ("-", "none", {}, ...)."""
    if v is None or v is True or (isinstance(v, str) and v.strip().lower() in _NO_CONDITION) or (isinstance(v, (dict, list)) and not v):
        return None
    return v


def _unimplemented(s: Statement, manifest: Manifest, why: str) -> I.Cand:
    e = manifest.by_id(s.source)
    c = I.make(
        f"g5.{s.id}.u",
        "unimplemented",
        {},
        stage=s.stage or "global",
        target=("action", "unimplemented", "final"),
        requirement="should",
        sources=[SourceRef(doc=e.id if e else s.source, lines=(s.line_start, s.line_end), quote=s.quote)],
        cls="content",
        origin="llm",
        derived_by="llm_extract",
        modality_evidence=f"statement {s.id} ({s.modality})",
        availability=["sandbox_file"],
        note=why,
        statement=s.id,
        downgrade_reason="unimplemented",
    )
    c.item.weight = 0.0
    return c


def statements_from_rows(rows: list[dict], manifest: Manifest) -> list[Statement]:
    """Pilot-format dicts (e.g. G7 coverage answers) -> Statements with source ids."""
    out = []
    for d in rows:
        e = manifest.resolve(str(d.get("path") or d.get("file") or ""))
        out.append(
            Statement(
                id=str(d["id"]),
                file=e.abs_path if e else str(d.get("file", "")),
                source=e.id if e else "",
                path=e.path if e else str(d.get("path", "")),
                **{k: d.get(k, "") for k in ("line_start", "line_end", "quote", "modality", "kind", "stage", "target", "checkable_by_rule", "none_allowed", "notes")},
            )
        )
    return out
