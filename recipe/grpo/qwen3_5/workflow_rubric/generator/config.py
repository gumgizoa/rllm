"""``workflows/<name>/generator.yaml``: everything the generator cannot read off the documents.

The documents say what the agent must do; they do not say which file is an adapter we wrote, which
lines of a template are literal, which sentence makes a skeleton binding, or which source wins a
contradiction. Those decisions are written down here, each with the line it rests on (a ``DocRef``:
a path relative to the workflow package, a line range, and the quoted text), so a reviewer can
check them against the same files the agent sees. Validation collects every problem and raises one
:class:`ConfigError`; a malformed config is an infrastructure error, never something to guess past.

Top-level keys (all optional except ``workflow``)::

    workflow        registry name; SPEC from recipe.grpo.qwen3_5.workflows.<workflow>
    spec            "module:ATTR" override of the SPEC import
    prefix          signal prefix for eval.py (default: workflow)
    harness         system_prompt keys to include (default: all)
    ids             {path: SOURCE_ID} overrides of generated source ids
    extra_sources   [{path, container}] files the agent sees that live outside ``docs_dir``: a package-relative file
                    or directory, and the container path it has (or holds its files under) when the agent reads it --
                    e.g. a schema the sandbox setup installs and a CLI serves (openspec_ff); sources like any other
    roles           [{glob: role}] first match wins (paths relative to the package or to docs/)
    system_prompt   {sections: {SECTION: workflow|harness_generic, "*": ...}}
    adapter_roles   roles whose text we wrote (default adapter, instruction, system_prompt)
    precedence      [{order: [role|SOURCE_ID|"system_prompt:<section role>"], applies_to, authority}]
    adapters        [{path, lines, type, replaces: [DocRef|"path:a-b"|{statement: id}|{upstream: "path:n", quote}]}]
    adapter_map     path (relative to this file) of an ``adapter-map/1`` file whose statements are added to ``adapters``
    classify        {rules_name: {placeholder, exemplar, literal, legit, markers, sample_marker, none_tokens}}
    templates       [{id, path, block, artifact, stage, state, binding, rules, sections, ...}]
    none_vocab      {"Section/Label" | "Label": [tokens]}
    content_required [{artifact, section, label, sources: [DocRef]}] template fields the template offers no none
                    alternative for and whose prose demands content ("Record every path"): none_allowed "no"
                    instead of the silent default (DESIGN §5.2 "no: 원문이 내용을 요구할 때만"), with those lines cited
    overrides       [{pattern, path, action: drop|replace, adapter, reason}]
    stage_model     {hints: [str], fixed: {roots, vars, stages, artifacts}}
    scoring         copied verbatim into the rubric
    gates           {kind | item-id glob: {zero_stage: true} | {cap_stage: x}}
    manual          [item dicts, sources by path; derived_by manual, or adapter for an item resting only on our adapter
                    text (P1a: G6 keeps it at most should and lists it among the adapter-derived items; its weight and
                    log_only stay the reviewer's)]
    exclude         [{statement: G4/G7 id (glob), kind?, stage?, reason, merge_into?}] extracted items dropped on review
                    (listed in rubric.md); merge_into (a statement id glob, or "template") names the item a duplicate
                    is folded into: it gains the duplicate's cited lines
    conflicts       [{description, sources: [DocRef], resolution, items?}] documented contradictions / gaps (P3), copied to the rubric
    parse           {template_comments: bool, example_markers: [regex]}
    llm             {backend, model, claude_bin, samples, max_budget_usd (per call), max_total_usd (per run), cache_dir, batch, chunk_lines, max_rounds, parallel}
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..schema import REQUIREMENTS, SOURCE_ROLES, STATES

ADAPTER_TYPES = ("path_map", "cli_substitute", "noninteractive_default", "stage_list", "entry_read")
SP_SECTION_ROLES = ("workflow", "harness_generic")
OVERRIDE_ACTIONS = ("drop", "replace")
MARKERS = ("mandatory", "optional", "conditional")
APPLIES_TO = ("all", "content", "procedure")
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_NONE_TOKENS = ["none", "n/a", "not applicable", "none stated", "nothing", "not run", "no tests"]


class ConfigError(ValueError):
    """generator.yaml is malformed (infrastructure error)."""


@dataclass
class DocRef:
    """A line range of a workflow file, by path relative to the workflow package."""

    path: str
    lines: tuple[int, int]
    quote: str = ""

    def to_dict(self) -> dict:
        return {"path": self.path, "lines": [self.lines[0], self.lines[1]], "quote": self.quote}


@dataclass
class AdapterRule:
    path: str
    lines: tuple[int, int]
    type: str
    replaces: list[Any] = field(default_factory=list)  # DocRef | {"statement": id}
    note: str = ""

    def covers(self, path: str, lines: tuple[int, int]) -> bool:
        return _same_path(self.path, path) and self.lines[0] <= lines[0] and lines[1] <= self.lines[1]


@dataclass
class PrecedenceRule:
    order: list[str]
    applies_to: str = "all"
    authority: DocRef | None = None


@dataclass
class ClassifyRules:
    """How template lines are classified. Regexes are validated (compiled) at load time."""

    brackets: bool = True  # outermost balanced [...] spans are placeholders (nesting-aware), unless legit
    placeholder: list[str] = field(default_factory=lambda: [r"<!--.*?-->", r"\$ARGUMENTS", r"<[A-Za-z][^<>\n]*>"])
    exemplar: list[str] = field(default_factory=list)
    literal: list[str] = field(default_factory=list)
    legit: list[str] = field(default_factory=lambda: [r"\[[ xX]\]", r"\[P\]", r"\[US\d+\]", r"\[(?:satisfies\s+)?R\d+(?:,\s*R\d+)*\]", r"\[[^\[\]\n]+\]\([^)\s]+\)"])
    markers: dict[str, list[str]] = field(
        default_factory=lambda: {
            "mandatory": [r"\*\(mandatory\)\*", r"\(mandatory\)"],
            "optional": [r"\*\(optional\)\*", r"\(OPTIONAL[^)]*\)", r"\[REMOVE IF UNUSED\]"],
            "conditional": [r"\*\(include if [^)]*\)\*", r"\*\(if [^)]*\)\*", r"^>\s*\*\*Fill ONLY if"],
        }
    )
    sample_marker: list[str] = field(default_factory=lambda: [r"(?i)\bdo not keep\b[^\n]*\bsample", r"(?i)\bsample (?:tasks|items)\b[^\n]*\bmust\b[^\n]*\breplace"])
    none_tokens: list[str] = field(default_factory=lambda: list(DEFAULT_NONE_TOKENS))

    def rx(self, name: str) -> list[re.Pattern]:
        return [re.compile(p) for p in getattr(self, name)]

    def marker_rx(self) -> dict[str, list[re.Pattern]]:
        return {k: [re.compile(p) for p in v] for k, v in self.markers.items()}


@dataclass
class TemplateSpec:
    """One skeleton: a whole template file, or a fenced block inside a document (AI-DLC).

    block       None (whole file) | {fence: lang, index: n} | {after: regex} | {lines: [a, b]}
    binding     the sentence that makes the skeleton binding; its modality sets the base requirement
    sections    {title: {requirement: must|should|skip, authority: DocRef}} per-section decisions
    literals    "all": every unbracketed line is literal output; "patterns": only ClassifyRules.literal
    """

    id: str
    path: str
    block: dict | None = None
    artifact: str | None = None
    stage: str | None = None
    state: str = "final"
    binding: DocRef | None = None
    binding_requirement: str | None = None
    rules: str = "default"
    frontmatter_exact: bool | None = None
    frontmatter_values: bool | None = None  # None: follow ``literals`` (values are literal output only when literals == "all")
    headings: bool = True
    labels: bool = True
    literals: str = "all"
    sections: dict[str, dict] = field(default_factory=dict)
    none_vocab: dict[str, list[str]] = field(default_factory=dict)
    not_copy: list[dict] = field(default_factory=list)
    infer_sequence: bool = False


@dataclass
class OverrideRule:
    pattern: str
    action: str
    path: str | None = None
    adapter: DocRef | None = None
    reason: str = ""

    def matches(self, path: str, text: str) -> bool:
        if self.path and not (fnmatch.fnmatch(path, self.path) or _same_path(self.path, path)):
            return False
        return re.search(self.pattern, text) is not None


@dataclass
class LLMConfig:
    backend: str = "claude-cli"
    model: str = DEFAULT_MODEL
    claude_bin: str | None = None
    samples: int = 3
    max_budget_usd: float | None = None
    max_total_usd: float | None = None  # stop asking the model once this much was spent in one generator run (cache hits are free)
    cache_dir: str | None = None
    batch: int = 12
    chunk_lines: int = 80
    max_rounds: int = 6
    timeout: int = 900
    retries: int = 2
    parallel: int = 1  # independent model calls in flight (G4 chunks, G5 batch x sample); answers and cache keys do not depend on it


@dataclass
class GeneratorConfig:
    workflow: str
    spec: str = ""
    prefix: str = ""
    harness: list[str] | None = None
    ids: dict[str, str] = field(default_factory=dict)
    extra_sources: list[dict[str, str]] = field(default_factory=list)
    roles: list[tuple[str, str]] = field(default_factory=list)
    sp_sections: dict[str, str] = field(default_factory=lambda: {"PROBLEM_SOLVING_WORKFLOW": "workflow", "*": "harness_generic"})
    adapter_roles: list[str] = field(default_factory=lambda: ["adapter", "instruction", "system_prompt"])
    precedence: list[PrecedenceRule] = field(default_factory=list)
    adapters: list[AdapterRule] = field(default_factory=list)
    classify: dict[str, ClassifyRules] = field(default_factory=lambda: {"default": ClassifyRules()})
    templates: list[TemplateSpec] = field(default_factory=list)
    none_vocab: dict[str, list[str]] = field(default_factory=dict)
    content_required: list[dict] = field(default_factory=list)
    overrides: list[OverrideRule] = field(default_factory=list)
    stage_model: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, dict] = field(default_factory=dict)
    manual: list[dict] = field(default_factory=list)
    exclude: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    adapter_weight: float = 0.0
    parse: dict[str, Any] = field(default_factory=dict)
    upstream_map: str = "upstream-map.json"
    llm: LLMConfig = field(default_factory=LLMConfig)
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def spec_import(self) -> str:
        return self.spec or f"recipe.grpo.qwen3_5.workflows.{self.workflow}:SPEC"

    @property
    def signal_prefix(self) -> str:
        return self.prefix or self.workflow

    def rules(self, name: str) -> ClassifyRules:
        return self.classify.get(name) or self.classify["default"]


# ----------------------------------------------------------------------------------------------
def load(path: str | Path) -> GeneratorConfig:
    p = Path(path)
    try:
        d = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError(f"{p}: {e}") from None
    return from_dict(d or {}, path=p)


def from_dict(d: dict, path: Path | None = None) -> GeneratorConfig:
    errs: list[str] = []
    if not isinstance(d, dict):
        raise ConfigError("generator.yaml must be a mapping")
    known = {
        "workflow", "spec", "prefix", "harness", "ids", "roles", "system_prompt", "adapter_roles", "precedence", "adapters", "classify",
        "templates", "none_vocab", "overrides", "stage_model", "scoring", "gates", "manual", "adapter_weight", "parse", "upstream_map", "llm",
        "adapter_map", "exclude", "conflicts", "content_required", "extra_sources",
    }  # fmt: skip
    for k in d:
        if k not in known:
            errs.append(f"unknown key {k!r}")
    wf = d.get("workflow")
    if not isinstance(wf, str) or not re.fullmatch(r"[A-Za-z_][\w]*", wf or ""):
        errs.append(f"workflow: {wf!r} is not a python identifier")
        wf = str(wf)
    cfg = GeneratorConfig(workflow=wf, path=path, raw=d)
    cfg.spec = _str(d.get("spec", ""), "spec", errs)
    if cfg.spec and ":" not in cfg.spec:
        errs.append("spec: expected 'module:ATTR'")
    cfg.prefix = _str(d.get("prefix", ""), "prefix", errs)
    if d.get("harness") is not None:
        cfg.harness = [str(h) for h in _list(d["harness"], "harness", errs)]
    cfg.ids = {str(k): str(v) for k, v in _dict(d.get("ids"), "ids", errs).items()}
    for sid in cfg.ids.values():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", sid):
            errs.append(f"ids: {sid!r} must be UPPER_SNAKE")
    for i, x in enumerate(_list(d.get("extra_sources"), "extra_sources", errs)):
        where = f"extra_sources[{i}]"
        if not isinstance(x, dict) or set(x) != {"path", "container"} or not all(isinstance(v, str) and v.strip() for v in x.values()):
            errs.append(f"{where}: expected {{path, container}} (a package-relative path and its container path)")
            continue
        if not x["container"].startswith("/") or norm_rel(x["path"]).startswith(("/", "../")):
            errs.append(f"{where}: container must be absolute and path relative to the package")
            continue
        cfg.extra_sources.append({"path": norm_rel(x["path"]).rstrip("/"), "container": x["container"].rstrip("/") or "/"})
    for i, r in enumerate(_list(d.get("roles"), "roles", errs)):
        if not isinstance(r, dict) or len(r) != 1:
            errs.append(f"roles[{i}]: expected {{glob: role}}")
            continue
        ((g, role),) = r.items()
        if role not in SOURCE_ROLES:
            errs.append(f"roles[{i}]: role {role!r} not in {SOURCE_ROLES}")
        cfg.roles.append((str(g), str(role)))
    sp = _dict(d.get("system_prompt"), "system_prompt", errs)
    if "sections" in sp:
        secs = _dict(sp["sections"], "system_prompt.sections", errs)
        for k, v in secs.items():
            if v not in SP_SECTION_ROLES:
                errs.append(f"system_prompt.sections.{k}: {v!r} not in {SP_SECTION_ROLES}")
        cfg.sp_sections = {str(k): str(v) for k, v in secs.items()}
        cfg.sp_sections.setdefault("*", "harness_generic")
    if "adapter_roles" in d:
        cfg.adapter_roles = [str(r) for r in _list(d["adapter_roles"], "adapter_roles", errs)]
        for r in cfg.adapter_roles:
            if r not in SOURCE_ROLES:
                errs.append(f"adapter_roles: {r!r} not a source role")
    for i, r in enumerate(_list(d.get("precedence"), "precedence", errs)):
        where = f"precedence[{i}]"
        if not isinstance(r, dict) or not isinstance(r.get("order"), list) or not r["order"]:
            errs.append(f"{where}: needs a non-empty 'order' list")
            continue
        ap = r.get("applies_to", "all")
        if ap not in APPLIES_TO:
            errs.append(f"{where}.applies_to: {ap!r} not in {APPLIES_TO}")
        auth = _docref(r.get("authority"), f"{where}.authority", errs, need_quote=True) if r.get("authority") is not None else None
        if auth is None:
            errs.append(f"{where}: an authority quote is required (the sentence that sets this precedence)")
        cfg.precedence.append(PrecedenceRule(order=[str(x) for x in r["order"]], applies_to=ap, authority=auth))
    for i, a in enumerate(_list(d.get("adapters"), "adapters", errs)):
        where = f"adapters[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where}: expected a mapping")
            continue
        ref = _docref({"path": a.get("path"), "lines": a.get("lines")}, where, errs)
        if a.get("type") not in ADAPTER_TYPES:
            errs.append(f"{where}.type: {a.get('type')!r} not in {ADAPTER_TYPES}")
        reps = []
        for j, rep in enumerate(_list(a.get("replaces"), f"{where}.replaces", errs)):
            if isinstance(rep, dict) and "statement" in rep:
                reps.append({"statement": str(rep["statement"])})
            elif isinstance(rep, dict) and "upstream" in rep and not rep.get("path"):
                reps.append({"upstream": str(rep["upstream"]), "quote": str(rep.get("quote", ""))})  # an upstream file the agent does not see
            else:
                r2 = _docref(rep, f"{where}.replaces[{j}]", errs)
                if r2:
                    reps.append(r2)
        if not reps and a.get("type") != "entry_read":
            errs.append(f"{where}: 'replaces' must name the upstream statement(s) this adapter text stands in for")
        if ref:
            cfg.adapters.append(AdapterRule(path=ref.path, lines=ref.lines, type=str(a.get("type")), replaces=reps, note=str(a.get("note", ""))))
    if d.get("adapter_map"):
        cfg.adapters += _adapter_map(d["adapter_map"], path, errs)
    cls_raw = _dict(d.get("classify"), "classify", errs)
    for name, rr in cls_raw.items():
        cfg.classify[str(name)] = _classify(rr, f"classify.{name}", errs)
    cfg.classify.setdefault("default", ClassifyRules())
    for i, t in enumerate(_list(d.get("templates"), "templates", errs)):
        ts = _template(t, f"templates[{i}]", errs)
        if ts:
            if ts.rules not in cfg.classify:
                errs.append(f"templates[{i}].rules: {ts.rules!r} not defined under classify")
            cfg.templates.append(ts)
    tids = [t.id for t in cfg.templates]
    if len(set(tids)) != len(tids):
        errs.append("templates: duplicate ids")
    cfg.none_vocab = {str(k): [str(x) for x in _list(v, f"none_vocab.{k}", errs)] for k, v in _dict(d.get("none_vocab"), "none_vocab", errs).items()}
    for i, x in enumerate(_list(d.get("content_required"), "content_required", errs)):
        where = f"content_required[{i}]"
        if not isinstance(x, dict) or not x.get("artifact") or not x.get("section") or not x.get("label") or not x.get("sources") or not set(x) <= {"artifact", "section", "label", "sources"}:
            errs.append(f"{where}: needs artifact, section, label and sources")
            continue
        refs_ = [_docref(r, f"{where}.sources[{j}]", errs, need_quote=True) for j, r in enumerate(x["sources"])]
        cfg.content_required.append({"artifact": str(x["artifact"]), "section": str(x["section"]), "label": str(x["label"]), "sources": [r.to_dict() for r in refs_ if r]})
    for i, o in enumerate(_list(d.get("overrides"), "overrides", errs)):
        where = f"overrides[{i}]"
        if not isinstance(o, dict) or not o.get("pattern"):
            errs.append(f"{where}: needs 'pattern'")
            continue
        _regex(o["pattern"], f"{where}.pattern", errs)
        act = o.get("action")
        if act not in OVERRIDE_ACTIONS:
            errs.append(f"{where}.action: {act!r} not in {OVERRIDE_ACTIONS}")
        ad = _docref(o.get("adapter"), f"{where}.adapter", errs) if o.get("adapter") is not None else None
        if act == "replace" and ad is None:
            errs.append(f"{where}: action replace needs 'adapter' (the adapter line that replaces the statement)")
        if not o.get("reason"):
            errs.append(f"{where}: 'reason' is required")
        cfg.overrides.append(OverrideRule(pattern=str(o["pattern"]), action=str(act), path=o.get("path"), adapter=ad, reason=str(o.get("reason", ""))))
    sm = _dict(d.get("stage_model"), "stage_model", errs)
    for k in sm:
        if k not in ("hints", "fixed"):
            errs.append(f"stage_model.{k}: unknown key")
    if "fixed" in sm:
        _fixed_stage_model(sm["fixed"], errs)
    cfg.stage_model = dict(sm)
    cfg.scoring = _dict(d.get("scoring"), "scoring", errs)
    cfg.gates = {}
    for k, g in _dict(d.get("gates"), "gates", errs).items():
        if not isinstance(g, dict) or not set(g) <= {"zero_stage", "cap_stage"} or not g:
            errs.append(f"gates.{k}: expected {{zero_stage: true}} or {{cap_stage: x}}")
        else:
            cfg.gates[str(k)] = dict(g)
    for i, m in enumerate(_list(d.get("manual"), "manual", errs)):
        where = f"manual[{i}]"
        if not isinstance(m, dict) or not m.get("id") or not m.get("check") or not m.get("sources"):
            errs.append(f"{where}: needs id, check and sources")
            continue
        for j, s in enumerate(m["sources"]):
            _docref(s, f"{where}.sources[{j}]", errs, need_quote=True)
        if m.get("requirement", "should") not in REQUIREMENTS:
            errs.append(f"{where}.requirement: {m.get('requirement')!r}")
        if m.get("derived_by", "manual") not in ("manual", "adapter"):
            errs.append(f"{where}.derived_by: {m.get('derived_by')!r} (manual | adapter)")
        cfg.manual.append(dict(m))
    for i, x in enumerate(_list(d.get("exclude"), "exclude", errs)):
        if not isinstance(x, dict) or not x.get("statement") or not str(x.get("reason") or "").strip() or not set(x) <= {"statement", "kind", "stage", "reason", "merge_into"}:
            errs.append(f"exclude[{i}]: needs statement and reason (optional kind, stage, merge_into)")
            continue
        cfg.exclude.append({k: str(v) for k, v in x.items()})
    for i, x in enumerate(_list(d.get("conflicts"), "conflicts", errs)):
        if not isinstance(x, dict) or not str(x.get("description") or "").strip() or not x.get("sources") or not str(x.get("resolution") or "").strip():
            errs.append(f"conflicts[{i}]: needs description, sources and resolution")
            continue
        refs_ = [_docref(r, f"conflicts[{i}].sources[{j}]", errs, need_quote=True) for j, r in enumerate(x["sources"])]
        cfg.conflicts.append({"description": str(x["description"]), "resolution": str(x["resolution"]), "items": [str(v) for v in x.get("items") or []], "sources": [r.to_dict() for r in refs_ if r]})
    try:
        cfg.adapter_weight = float(d.get("adapter_weight", 0.0))
    except (TypeError, ValueError):
        errs.append("adapter_weight: not a number")
    cfg.parse = _dict(d.get("parse"), "parse", errs)
    for p in cfg.parse.get("example_markers", []) or []:
        _regex(p, "parse.example_markers", errs)
    cfg.upstream_map = _str(d.get("upstream_map", "upstream-map.json"), "upstream_map", errs)
    cfg.llm = _llm(_dict(d.get("llm"), "llm", errs), errs)
    if errs:
        raise ConfigError(f"{path or 'generator.yaml'}: " + "; ".join(errs[:30]) + (f" (+{len(errs) - 30} more)" if len(errs) > 30 else ""))
    return cfg


# ----------------------------------------------------------------------------------------------
def parse_ref(obj: Any, where: str = "ref") -> DocRef:
    """``{path, lines, quote}`` or ``"path:a-b"`` -> DocRef (raises ConfigError)."""
    errs: list[str] = []
    r = _docref(obj, where, errs)
    if errs or r is None:
        raise ConfigError("; ".join(errs) or f"{where}: bad reference")
    return r


def _docref(obj: Any, where: str, errs: list[str], need_quote: bool = False) -> DocRef | None:
    if isinstance(obj, str):
        m = re.fullmatch(r"(.+?):(\d+)(?:-(\d+))?", obj.strip())
        if not m:
            errs.append(f"{where}: {obj!r} is not 'path:a-b'")
            return None
        a = int(m.group(2))
        b = int(m.group(3) or a)
        obj = {"path": m.group(1), "lines": [a, b]}
    if not isinstance(obj, dict) or not obj.get("path"):
        errs.append(f"{where}: needs 'path'")
        return None
    lines = obj.get("lines")
    if isinstance(lines, int):
        lines = [lines, lines]
    if not (isinstance(lines, (list, tuple)) and len(lines) in (1, 2) and all(isinstance(x, int) and x >= 1 for x in lines)):
        errs.append(f"{where}.lines: expected [a, b] (1-based)")
        return None
    a, b = int(lines[0]), int(lines[-1])
    if b < a:
        errs.append(f"{where}.lines: {a} > {b}")
        return None
    quote = str(obj.get("quote", obj.get("text", "")) or "")
    if need_quote and not quote.strip():
        errs.append(f"{where}: 'quote' is required")
    return DocRef(path=str(obj["path"]), lines=(a, b), quote=quote)


_MAP_TYPES = {"path_mapping": "path_map", "cli_substitution": "cli_substitute", "noninteractive_default": "noninteractive_default", "stage_list": "stage_list", "entry_doc": "entry_read"}


def _adapter_map(rel: Any, cfg_path: Path | None, errs: list[str]) -> list[AdapterRule]:
    """Statements of an ``adapter-map/1`` file (written next to the package's adapter) as adapter whitelist rules."""
    p = Path(str(rel))
    if not p.is_absolute():
        if cfg_path is None:
            errs.append("adapter_map: a relative path needs the config file's location")
            return []
        p = cfg_path.parent / p
    try:
        d = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError) as e:
        errs.append(f"adapter_map: {e}")
        return []
    if not isinstance(d, dict) or d.get("schema") != "adapter-map/1":
        errs.append(f"adapter_map: {p} is not an adapter-map/1 file")
        return []
    out = []
    for f in d.get("files") or []:
        for st in f.get("statements") or []:
            where = f"adapter_map {f.get('path')}:{st.get('id')}"
            ref = _docref({"path": f.get("path"), "lines": st.get("lines")}, where, errs)
            typ = _MAP_TYPES.get(str(st.get("type")))
            if typ is None:
                errs.append(f"{where}: type {st.get('type')!r}")
                continue
            reps: list[Any] = []
            for sub in st.get("substitutes") or []:
                if sub.get("doc"):
                    r = _docref({"path": sub["doc"], "lines": sub.get("lines"), "quote": sub.get("quote", "")}, f"{where}.substitutes", errs)
                    if r:
                        reps.append(r)
                else:
                    reps.append({"upstream": str(sub.get("upstream", "")), "quote": str(sub.get("quote", ""))})
            if ref:
                out.append(AdapterRule(path=ref.path, lines=ref.lines, type=typ, replaces=reps, note=f"{st.get('id', '')} {st.get('note', '')}".strip()))
    return out


def _classify(rr: Any, where: str, errs: list[str]) -> ClassifyRules:
    out = ClassifyRules()
    if not isinstance(rr, dict):
        errs.append(f"{where}: expected a mapping")
        return out
    for k, v in rr.items():
        if k in ("placeholder", "exemplar", "literal", "legit", "sample_marker"):
            vals = [str(x) for x in _list(v, f"{where}.{k}", errs)]
            for p in vals:
                _regex(p, f"{where}.{k}", errs)
            setattr(out, k, vals)
        elif k == "extra_placeholder":
            vals = [str(x) for x in _list(v, f"{where}.{k}", errs)]
            for p in vals:
                _regex(p, f"{where}.{k}", errs)
            out.placeholder = [*out.placeholder, *vals]
        elif k == "extra_legit":
            vals = [str(x) for x in _list(v, f"{where}.{k}", errs)]
            for p in vals:
                _regex(p, f"{where}.{k}", errs)
            out.legit = [*out.legit, *vals]
        elif k == "markers":
            m = _dict(v, f"{where}.markers", errs)
            for mk, pats in m.items():
                if mk not in MARKERS:
                    errs.append(f"{where}.markers.{mk}: not in {MARKERS}")
                for p in _list(pats, f"{where}.markers.{mk}", errs):
                    _regex(str(p), f"{where}.markers.{mk}", errs)
            out.markers = {**out.markers, **{str(mk): [str(p) for p in pats] for mk, pats in m.items()}}
        elif k == "brackets":
            out.brackets = bool(v)
        elif k == "none_tokens":
            out.none_tokens = [str(x).lower() for x in _list(v, f"{where}.none_tokens", errs)]
        else:
            errs.append(f"{where}.{k}: unknown key")
    return out


def _template(t: Any, where: str, errs: list[str]) -> TemplateSpec | None:
    if not isinstance(t, dict):
        errs.append(f"{where}: expected a mapping")
        return None
    known = {"id", "path", "block", "artifact", "stage", "state", "binding", "binding_requirement", "rules", "frontmatter_exact", "frontmatter_values",
             "headings", "labels", "literals", "sections", "none_vocab", "not_copy", "infer_sequence"}  # fmt: skip
    for k in t:
        if k not in known:
            errs.append(f"{where}.{k}: unknown key")
    if not t.get("id") or not t.get("path"):
        errs.append(f"{where}: needs id and path")
        return None
    ts = TemplateSpec(id=str(t["id"]), path=str(t["path"]))
    blk = t.get("block")
    if blk is not None:
        if not isinstance(blk, dict) or not ({"fence", "index", "after", "lines"} & set(blk)):
            errs.append(f"{where}.block: expected {{fence, index}} | {{after: regex}} | {{lines: [a, b]}}")
        elif "after" in blk:
            _regex(str(blk["after"]), f"{where}.block.after", errs)
        ts.block = dict(blk) if isinstance(blk, dict) else None
    ts.artifact = t.get("artifact")
    ts.stage = t.get("stage")
    ts.state = str(t.get("state", "final"))
    if ts.state not in STATES:
        errs.append(f"{where}.state: {ts.state!r} not in {STATES}")
    if t.get("binding") is not None:
        ts.binding = _docref(t["binding"], f"{where}.binding", errs, need_quote=True)
    br = t.get("binding_requirement")
    if br is not None and br not in REQUIREMENTS:
        errs.append(f"{where}.binding_requirement: {br!r} not in {REQUIREMENTS}")
    ts.binding_requirement = br
    ts.rules = str(t.get("rules", "default"))
    ts.frontmatter_exact = t.get("frontmatter_exact")
    ts.frontmatter_values = None if t.get("frontmatter_values") is None else bool(t["frontmatter_values"])
    ts.headings = bool(t.get("headings", True))
    ts.labels = bool(t.get("labels", True))
    ts.literals = str(t.get("literals", "all"))
    if ts.literals not in ("all", "patterns"):
        errs.append(f"{where}.literals: expected all|patterns")
    for title, sd in _dict(t.get("sections"), f"{where}.sections", errs).items():
        if not isinstance(sd, dict):
            errs.append(f"{where}.sections.{title}: expected a mapping")
            continue
        if sd.get("requirement") not in (*REQUIREMENTS, "skip"):
            errs.append(f"{where}.sections.{title}.requirement: expected must|should|skip")
        if sd.get("authority") is None:
            errs.append(f"{where}.sections.{title}: 'authority' (the line that decides it) is required")
        else:
            sd = {**sd, "authority": _docref(sd["authority"], f"{where}.sections.{title}.authority", errs, need_quote=True)}
        ts.sections[str(title)] = sd
    ts.none_vocab = {str(k): [str(x) for x in _list(v, f"{where}.none_vocab.{k}", errs)] for k, v in _dict(t.get("none_vocab"), f"{where}.none_vocab", errs).items()}
    for j, nc in enumerate(_list(t.get("not_copy"), f"{where}.not_copy", errs)):
        if not isinstance(nc, dict) or not nc.get("section") or nc.get("authority") is None:
            errs.append(f"{where}.not_copy[{j}]: needs section and authority")
            continue
        ts.not_copy.append({"section": str(nc["section"]), "authority": _docref(nc["authority"], f"{where}.not_copy[{j}].authority", errs, need_quote=True)})
    ts.infer_sequence = bool(t.get("infer_sequence", False))
    return ts


def _fixed_stage_model(fx: Any, errs: list[str]) -> None:
    if not isinstance(fx, dict):
        errs.append("stage_model.fixed: expected a mapping")
        return
    for k in fx:
        if k not in ("roots", "vars", "stages", "artifacts"):
            errs.append(f"stage_model.fixed.{k}: unknown key")
    stages = fx.get("stages") or []
    arts = fx.get("artifacts") or {}
    if not isinstance(stages, list) or not isinstance(arts, dict):
        errs.append("stage_model.fixed: stages must be a list and artifacts a mapping")
        return
    ids = []
    for i, s in enumerate(stages):
        if not isinstance(s, dict) or not s.get("id"):
            errs.append(f"stage_model.fixed.stages[{i}]: needs id")
            continue
        ids.append(s["id"])
        for a in [*(s.get("artifacts") or []), *(s.get("requires") or []), *([s["order_artifact"]] if s.get("order_artifact") else [])]:
            if a not in arts:
                errs.append(f"stage_model.fixed.stages[{i}]: artifact {a!r} undefined")
    if len(set(ids)) != len(ids) or "global" in ids:
        errs.append("stage_model.fixed: stage ids must be unique and not 'global'")
    for aid, a in arts.items():
        if not isinstance(a, dict) or not a.get("locations"):
            errs.append(f"stage_model.fixed.artifacts.{aid}: needs locations")


def _llm(d: dict, errs: list[str]) -> LLMConfig:
    out = LLMConfig()
    for k, v in d.items():
        if not hasattr(out, k):
            errs.append(f"llm.{k}: unknown key")
            continue
        cur = getattr(out, k)
        try:
            if isinstance(cur, bool) or cur is None or isinstance(cur, str):
                setattr(out, k, v if v is None else (float(v) if k in ("max_budget_usd", "max_total_usd") else str(v)))
            elif isinstance(cur, int):
                setattr(out, k, int(v))
            else:
                setattr(out, k, v)
        except (TypeError, ValueError):
            errs.append(f"llm.{k}: bad value {v!r}")
    if out.samples < 1:
        errs.append("llm.samples: must be >= 1")
    return out


def _regex(p: Any, where: str, errs: list[str]) -> None:
    try:
        re.compile(str(p))
    except re.error as e:
        errs.append(f"{where}: bad regex {p!r}: {e}")


def _str(v: Any, where: str, errs: list[str]) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        errs.append(f"{where}: expected a string")
        return str(v)
    return v


def _list(v: Any, where: str, errs: list[str]) -> list:
    if v is None:
        return []
    if not isinstance(v, list):
        errs.append(f"{where}: expected a list")
        return []
    return v


def _dict(v: Any, where: str, errs: list[str]) -> dict:
    if v is None:
        return {}
    if not isinstance(v, dict):
        errs.append(f"{where}: expected a mapping")
        return {}
    return v


def norm_rel(p: str) -> str:
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _same_path(a: str, b: str) -> bool:
    a, b = norm_rel(a), norm_rel(b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)
