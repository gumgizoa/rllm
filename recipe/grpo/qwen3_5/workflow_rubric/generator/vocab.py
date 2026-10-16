"""The closed vocabulary the generator may emit: check kinds, and the refs language.

G5 maps statements only onto kinds that exist, with exactly the parameters each accepts, and G6
rejects predicates the engine could not evaluate. The truth is the check registry
(:mod:`..checks`, plus a workflow's plugin kinds); while those modules are not importable (the
engine is built in parallel) the static table below -- CONTRACT §2.9 verbatim -- stands in, so
the generator never invents a kind or a parameter.

``COMMON_TEMPLATE`` maps a common kind to the common-rubric template (DESIGN §7, C-A*/C-F*) it
instantiates; G8's scope rule reads it.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KindSpec:
    name: str
    params: dict[str, bool]
    availability: tuple[str, ...] = ("sandbox_file",)
    cls: str = "content"
    common: bool = True
    doc: str = ""
    literal_params: tuple[str, ...] = field(default=())  # params whose text must appear in the cited lines / template
    regex_params: tuple[str, ...] = field(default=())  # params whose literal fragments must appear
    choices: tuple[tuple[str, tuple[str, ...]], ...] = field(default=())  # (param, values the kind implements): any other is rejected


# (params, availability, class, doc, literal params, regex params) -- CONTRACT §2.9
_STATIC: dict[str, tuple] = {
    "doc_read": ({"doc": True, "window": False, "min_coverage": False, "single_doc": False, "no_read_ahead": False}, ("trace",), "evidence",
                 "a read of doc in the window with coverage >= min_coverage", (), ()),
    "doc_read_first": ({"doc": True, "allow": False}, ("trace",), "evidence", "the first acting action (not matching allow) reads doc", (), ()),
    "order": ({"chain": False, "before": False, "after": False, "invalidate": False, "substantive": False}, ("trace",), "evidence",
              "events (read:<SOURCE>, write:<ARTIFACT>, ...) happen in this order", (), ()),
    "write_discipline": ({"mode": True, "artifact": False, "window": False}, ("trace", "sandbox_file"), "evidence",
                         "mode once | append_only | no_rewrite for an artifact", (), ()),
    "exec_evidence": ({"kind": False, "window": False, "command_in": False, "min_count": False}, ("trace",), "evidence",
                      ">= min_count valid runs of kind (test|build) in the window (valid: runner verb, own summary with N>=1 tests, base-repo targets; "
                      "echo/printf summaries, /tmp dummies, agent-made runners, zero-test and load-error-only runs are void)", (), ()),
    "prohibited_action": ({"action": True, "window": False, "pattern": False, "selector": False, "paths_in": False}, ("trace",), "evidence",
                          "no action of class execute (a test run, or running the path `selector` names) | repo_write | source_write (a file that "
                          "existed at BASE_SHA, edited in place; new files are not) | test_file_write (an existing test file) | install | full_suite "
                          "(a test runner at the repo root selecting nothing) | command (pattern) in the window; pattern also filters paths / commands",
                          (), ("pattern",)),
    "artifact_exists": ({"artifact": False}, ("sandbox_file",), "structure", "the artifact exists (final / stage_end)", (), ()),
    "path_match": ({"pattern": True, "artifact": False, "relative_to": False}, ("sandbox_file",), "structure", "the resolved path matches pattern", (), ("pattern",)),
    "frontmatter": ({"keys": False, "exact": False, "values": False}, ("sandbox_file",), "structure", "frontmatter keys (exact set if exact) and values", ("keys",), ()),
    "section_present": ({"heading": True, "level": False, "match": False}, ("sandbox_file",), "structure", "a heading exists", ("heading",), ()),
    "label_present": ({"section": True, "label": True}, ("sandbox_file",), "structure", "a label line exists in the section", ("section", "label"), ()),
    "field_literal": ({"section": True, "text": True, "label": False, "refuted_by": False}, ("sandbox_file",), "structure",
                      "the label value (or a section line) equals text; refuted_by predicate false", ("section", "text", "label"), ()),
    "field_filled": ({"section": True, "label": False, "placeholders": False, "none_vocab": False, "per_block": False, "min_items": False}, ("sandbox_file",), "content",
                     "value present and not a placeholder; none handled by none_allowed", ("section", "label", "none_vocab"), ()),
    "field_enum": ({"section": True, "label": True, "values": True, "prefix_ok": False}, ("sandbox_file",), "content", "value is one of values", ("section", "label", "values"), ()),
    "field_type": ({"section": True, "label": True, "type": True, "window": False, "run_kind": False, "listed_in": False}, ("sandbox_file", "trace"), "content",
                   "value backed by the run: command_run (a command run in the window; with run_kind a VALID run of that kind; "
                   "spellings of one invocation compare equal) | repo_path (exists at BASE_SHA or in the diff) | test_id (each id in a valid "
                   "run's output/targets, or a file/label it ran, or a test name a base file it ran defines) | failed_test_id (each id failed "
                   "in a valid run of the window, or is listed in the listed_in selector) | test_selection (a test command selecting tests, "
                   "not the whole suite); none values are skipped", ("section", "label"), ()),
    "item_format": ({"pattern": True, "section": False, "min": False, "max": False, "sequence": False, "unique": False, "of_pattern": False}, ("sandbox_file",), "content",
                    "lines matching pattern: count, sequence, uniqueness", ("section",), ("pattern", "of_pattern")),
    "cross_ref": ({"left": True, "right": True, "relation": True, "normalize": False, "allow_empty": False}, ("sandbox_file",), "content",
                  "relation (subset|superset|equal|intersects|disjoint) between two selectors", (), ()),
    "no_template_residue": ({"patterns": True, "section": False}, ("sandbox_file",), "content", "no residue pattern occurs", ("section",), ("patterns",)),
    "not_template_copy": ({"section": True, "fingerprint": True, "threshold": False}, ("sandbox_file",), "content",
                          "the section is not (mostly) the template's sample lines", ("section", "fingerprint"), ()),
}  # fmt: skip

COMMON_TEMPLATE = {
    "doc_read_first": "C-A1",
    "doc_read": "C-A2",
    "order": "C-A3",
    "write_discipline": "C-A5",
    "prohibited_action": "C-A6",
    "artifact_exists": "C-F1",
    "path_match": "C-F2",
    "frontmatter": "C-F3",
    "section_present": "C-F4",
    "label_present": "C-F5",
    "field_filled": "C-F6",
    "field_enum": "C-F7",
    "field_literal": "C-F7",
    "no_template_residue": "C-F8",
    "not_template_copy": "C-F9",
    "item_format": "C-F10",
    "cross_ref": "C-F11",
}
ADAPTER_FORBIDDEN = frozenset({"frontmatter", "section_present", "field_literal", "field_enum", "prohibited_action"})

PREDICATE_OPS = ("all", "any", "not", "exists", "absent", "counts", "field_is_none", "field_present", "field_matches", "artifact_exists", "relation")
PREDICATE_FACTS = {
    "valid_run": {"window", "kind", "command_in", "targets_in"},
    "run_attempt": {"window", "kind", "command_in", "targets_in"},
    "repo_edit": {"window", "paths_in", "paths_not_in", "test_paths", "final", "created"},
    "artifact_write": {"window", "artifact"},
    "doc_read": {"window", "doc", "min_coverage"},
    "exec_of": {"window", "selector"},
    "command": {"window", "pattern"},
}
COUNT_KEYS = {"fact", "window", "which", "passed", "failed", "errors", "failed_or_errors", "collected_min", "kind", "command_in", "targets_in", "failures_not_in"}
SELECTOR_KEYS = ("field", "field_list", "section_text", "section_lines", "ids", "headings", "keyed_ids", "fact", "literal")
FACT_SELECTORS = ("diff_paths", "diff_test_paths", "untracked_paths", "repo_write_paths", "run_commands", "valid_run_commands", "run_ids", "base_paths")
NORMALIZE = ("path", "command", "id", "text")
RELATIONS = ("subset", "superset", "equal", "intersects", "disjoint")
EVENT_FIXED = ("start", "end", "first_repo_write", "last_repo_write", "last_change_write")
EVENT_KINDS = ("read", "write", "first_write", "last_write", "stage_start", "stage_end")
FIELD_TYPES = ("command_run", "repo_path", "test_id", "failed_test_id", "test_selection")
PROHIBITED_ACTIONS = ("execute", "repo_write", "source_write", "test_file_write", "install", "full_suite", "command")
MATCHES = ("exact_ci", "norm", "prefix", "regex")
RUN_KINDS = ("test", "build")
# the enumerated parameters of the common kinds (the registry's ``choices``; this copy serves the static table)
_STATIC_CHOICES: dict[str, dict[str, tuple[str, ...]]] = {
    "order": {"invalidate": ("read_ahead", "multi_read", "rewrite")},
    "write_discipline": {"mode": ("once", "append_only", "no_rewrite")},
    "exec_evidence": {"kind": RUN_KINDS},
    "prohibited_action": {"action": PROHIBITED_ACTIONS},
    "section_present": {"match": MATCHES},
    "field_type": {"type": FIELD_TYPES, "run_kind": RUN_KINDS},
    "cross_ref": {"relation": RELATIONS, "normalize": NORMALIZE},
}


def static_kinds() -> dict[str, KindSpec]:
    return {k: KindSpec(k, dict(p), tuple(a), c, True, d, tuple(lp), tuple(rp), _choices(_STATIC_CHOICES.get(k))) for k, (p, a, c, d, lp, rp) in _STATIC.items()}


def _choices(d: dict | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(sorted((str(k), tuple(v)) for k, v in (d or {}).items()))


def kinds(workflow: str | None = None) -> tuple[dict[str, KindSpec], str]:
    """The kind table and where it came from (``registry`` or ``static``).

    Registry kinds keep the static class/doc/literal hints when they share a name; plugin kinds
    (``<wf>.<name>``) come from ``workflows/<wf>/reward/checks.py`` when it imports.
    """
    table = static_kinds()
    try:
        from .. import checks

        checks.load_common()
        if workflow:
            try:
                importlib.import_module(f"recipe.grpo.qwen3_5.workflows.{workflow}.reward.checks")
            except ImportError:
                pass
        out: dict[str, KindSpec] = {}
        for name, k in checks.REGISTRY.items():
            base = table.get(name)
            out[name] = KindSpec(
                name,
                dict(k.params),
                tuple(k.availability),
                base.cls if base else "content",
                bool(k.common),
                base.doc if base else (k.doc.splitlines()[0] if k.doc else ""),
                base.literal_params if base else (),
                base.regex_params if base else (),
                _choices(getattr(k, "choices", None)) or (base.choices if base else ()),
            )
        if out:
            return out, "registry"
    except Exception as e:  # noqa: BLE001 -- the registry modules may not exist yet
        logger.info("check registry unavailable (%s); using the static CONTRACT table", type(e).__name__)
    return table, "static"


def check_params(kind: str, params: dict, table: dict[str, KindSpec]) -> list[str]:
    if kind == "unimplemented":
        return []
    k = table.get(kind)
    if k is None:
        return [f"unknown kind {kind!r}"]
    if not isinstance(params, dict):
        return ["params is not a mapping"]
    errs = [f"missing param {p!r}" for p, req in k.params.items() if req and p not in params]
    errs += [f"unexpected param {p!r}" for p in params if p not in k.params]
    for p in k.regex_params:
        for rx in _as_list(params.get(p)):
            try:
                re.compile(str(rx))
            except re.error as e:
                errs.append(f"param {p}: bad regex {rx!r}: {e}")
    for p, allowed in k.choices:  # an enumerated value the kind does not implement fails every run alike
        bad = [v for v in _as_list(params.get(p)) if not isinstance(v, str) or v not in allowed]
        if p in params and params[p] is not None and bad:
            errs.append(f"{kind} {p} {bad[0]!r} not in {allowed}")
    sec = params.get("section")
    if isinstance(sec, dict) and "match" in sec and sec["match"] not in MATCHES:
        errs.append(f"section match {sec['match']!r} not in {MATCHES}")
    return errs


# ----------------------------------------------------------------------------------------------
# refs language (mirrors refs.py; the engine raises RefError on anything else)
# ----------------------------------------------------------------------------------------------
def check_event(ev, stages: set[str], artifacts: set[str], sources: set[str]) -> list[str]:
    if isinstance(ev, dict):  # {first: <fact query>} | {last: <fact query>}
        if len(ev) != 1 or next(iter(ev)) not in ("first", "last") or not isinstance(next(iter(ev.values())), dict):
            return [f"event {ev!r}: a fact event is {{first|last: {{fact: ..., filters}}}}"]
        q = next(iter(ev.values()))
        if not _member(q.get("fact"), PREDICATE_FACTS):
            return [f"event {ev!r}: fact must be one of {sorted(PREDICATE_FACTS)}"]
        return _fact_filter_errors(q, PREDICATE_FACTS[q["fact"]], stages, artifacts, sources)
    if not isinstance(ev, str):
        return [f"event {ev!r} is not a string"]
    if ev in EVENT_FIXED:
        return []
    kind, _, arg = ev.partition(":")
    if kind == "read":
        return [] if arg in sources else [f"event {ev!r}: unknown source"]
    if kind in ("write", "first_write", "last_write"):
        return [] if arg in artifacts else [f"event {ev!r}: unknown artifact"]
    if kind in ("stage_start", "stage_end"):
        return [] if arg in stages else [f"event {ev!r}: unknown stage"]
    return [f"unknown event {ev!r}"]


def check_window(w, stages: set[str], artifacts: set[str], sources: set[str]) -> list[str]:
    if w is None:
        return []
    if isinstance(w, str):
        if w.startswith("stage:") and w[6:] in stages:
            return []
        return [f"window {w!r}"]
    if isinstance(w, (list, tuple)) and len(w) == 2:
        starts = list(w[0]) if isinstance(w[0], (list, tuple)) else [w[0]]  # a start may be the latest of several events
        ends = list(w[1]) if isinstance(w[1], (list, tuple)) else [w[1]]  # an end the earliest of several
        if not starts or not ends:
            return [f"window {w!r}: empty start or end list"]
        return [e for ev in starts + ends for e in check_event(ev, stages, artifacts, sources)]
    return [f"window {w!r}"]


def check_selector(s, stages: set[str], artifacts: set[str], sources: set[str]) -> list[str]:
    if isinstance(s, list) and s:  # paths_in / paths_not_in / failures_not_in: a union of selectors
        return [e for x in s for e in check_selector(x, stages, artifacts, sources)]
    if not isinstance(s, dict):
        return [f"selector {s!r} is not a mapping"]
    keys = [k for k in s if k != "normalize"]  # refs.select: one key besides normalize (a window goes inside {fact: {...}})
    if len(keys) != 1 or keys[0] not in SELECTOR_KEYS:
        return [f"selector {s!r}: exactly one of {SELECTOR_KEYS}"]
    errs = []
    if s.get("normalize") is not None and s["normalize"] not in NORMALIZE:
        errs.append(f"selector normalize {s['normalize']!r}")
    key, arg = keys[0], s[keys[0]]
    if key in ("field", "field_list", "section_text", "section_lines", "ids", "headings", "keyed_ids"):
        if not isinstance(arg, dict) or not _member(arg.get("artifact"), artifacts):
            return errs + [f"selector {key}: unknown artifact"]
        need = {
            "field": ("section", "label"),
            "field_list": ("section", "label"),
            "section_text": ("section",),
            "section_lines": ("section",),
            "ids": ("pattern",),
            "headings": ("level", "pattern"),
            "keyed_ids": ("pattern",),
        }[key]
        errs += [f"selector {key}: missing {n}" for n in need if n not in arg]
        if key in ("ids", "headings", "keyed_ids") and "pattern" in arg:
            try:
                re.compile(str(arg["pattern"]))
            except re.error as e:
                errs.append(f"selector {key}: bad regex: {e}")
    elif key == "fact":
        name = arg if isinstance(arg, str) else (arg.get("name") or arg.get("fact") if isinstance(arg, dict) else None)
        if name not in FACT_SELECTORS:
            errs.append(f"fact selector {name!r}")
        if isinstance(arg, dict):
            errs += check_window(arg.get("window"), stages, artifacts, sources)
    elif key == "literal":
        if not isinstance(arg, list):
            errs.append("literal selector must be a list")
    return errs


def check_predicate(p, stages: set[str], artifacts: set[str], sources: set[str]) -> list[str]:
    """Errors that would make ``refs.predicate`` raise (empty = evaluable)."""
    if p is None or p is True or p is False:
        return []
    if not isinstance(p, dict) or len(p) != 1:
        return [f"predicate {p!r}: a single-key mapping"]
    ((op, arg),) = p.items()
    if op not in PREDICATE_OPS:
        return [f"predicate op {op!r} not in {PREDICATE_OPS}"]
    if op in ("all", "any"):
        if not isinstance(arg, list):
            return [f"{op}: expected a list"]
        return [e for q in arg for e in check_predicate(q, stages, artifacts, sources)]
    if op == "not":
        return check_predicate(arg, stages, artifacts, sources)
    if op in ("exists", "absent"):
        if not isinstance(arg, dict) or not _member(arg.get("fact"), PREDICATE_FACTS):
            return [f"{op}: fact must be one of {sorted(PREDICATE_FACTS)}"]
        return _fact_filter_errors(arg, PREDICATE_FACTS[arg["fact"]], stages, artifacts, sources)
    if op == "counts":
        if not isinstance(arg, dict):
            return ["counts: expected a mapping"]
        errs = [f"counts: unexpected key {k!r}" for k in arg if k not in COUNT_KEYS]
        if arg.get("fact", "valid_run") not in ("valid_run", "run_attempt"):
            errs.append("counts: fact must be valid_run or run_attempt")
        if arg.get("which", "any") not in ("first", "last", "any", "all"):
            errs.append("counts: which")
        errs += _fact_filter_errors({k: v for k, v in arg.items() if k in ("window", "command_in", "targets_in")}, {"window", "command_in", "targets_in"}, stages, artifacts, sources)
        if "failures_not_in" in arg:
            errs += check_selector(arg["failures_not_in"], stages, artifacts, sources)
        return errs
    if op in ("field_is_none", "field_present", "field_matches"):
        if not isinstance(arg, dict) or not _member(arg.get("artifact"), artifacts):
            return [f"{op}: unknown artifact"]
        errs = [f"{op}: missing {n}" for n in ("section", "label") if n not in arg]
        if op == "field_matches":
            try:
                re.compile(str(arg.get("pattern", "")))
            except re.error as e:
                errs.append(f"{op}: bad regex: {e}")
            if "pattern" not in arg:
                errs.append(f"{op}: missing pattern")
        return errs
    if op == "artifact_exists":
        return [] if _member(arg, artifacts) else [f"artifact_exists: unknown artifact {arg!r}"]
    # relation
    if not isinstance(arg, dict) or arg.get("rel") not in RELATIONS:
        return [f"relation: rel must be one of {RELATIONS}"]
    return check_selector(arg.get("left"), stages, artifacts, sources) + check_selector(arg.get("right"), stages, artifacts, sources)


def _fact_filter_errors(arg: dict, allowed: set[str], stages, artifacts, sources) -> list[str]:
    errs = [f"unexpected filter {k!r}" for k in arg if k != "fact" and k not in allowed]
    errs += check_window(arg.get("window"), stages, artifacts, sources)
    for k in ("command_in", "targets_in", "paths_in", "paths_not_in", "selector"):
        if k in arg:
            errs += check_selector(arg[k], stages, artifacts, sources)
    if "artifact" in arg and not _member(arg["artifact"], artifacts):
        errs.append(f"unknown artifact {arg['artifact']!r}")
    if "doc" in arg and not _member(arg["doc"], sources):
        errs.append(f"unknown doc {arg['doc']!r}")
    if "pattern" in arg:
        try:
            re.compile(str(arg["pattern"]))
        except re.error as e:
            errs.append(f"bad regex: {e}")
    return errs


def _member(x, ids) -> bool:
    """``x in ids`` for a value a model wrote: ids are strings, so a mapping or list is never one (and no TypeError)."""
    return isinstance(x, str) and x in ids


def is_anchor(selector) -> bool:
    """A selector the agent did not write: trace / diff / base-tree facts, or literals from the rubric."""
    return isinstance(selector, dict) and ("fact" in selector or "literal" in selector)


def _as_list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def kind_table_text(table: dict[str, KindSpec]) -> str:
    """The kind vocabulary as prompt text: one line per kind, required params starred."""
    rows = []
    for name in sorted(table):
        k = table[name]
        ps = ", ".join(f"{p}*" if req else p for p, req in k.params.items())
        rows.append(f"- {name} [{k.cls}{'' if k.common else ', plugin'}] ({ps}): {k.doc}")
    rows.append("- unimplemented [content] (): no kind expresses the statement (weight 0, reported)")
    return "\n".join(rows)
