"""OpenSpec plugin kinds: the spec-driven rules that span several files or a file's history.

Vendored verbatim (this paragraph aside) from ``workflows/openspec/reward/checks.py`` of the verifier-generation
branch (e19b7236), whose ``openspec`` port is not on this branch: ``openspec_ff`` uses these kinds as they are, and
``openspec_ff/reward/checks.py`` imports them from here. Keep the two copies in step; never import both into one
process (a kind registers once).

The common kinds read one artifact at one path. OpenSpec's change holds one delta spec per
capability (``specs/<capability-path>/spec.md``, schema.yaml:62-66), each merged into its own main
spec at archive time (sync-specs SKILL:92-149), and the change directory moves from
``openspec/changes/<name>`` to ``openspec/changes/archive/YYYY-MM-DD-<name>`` (archive-change
SKILL:129-144). These kinds read every delta / main spec of the run's change, wherever the change
ended up, and the trace where a rule is about *when* (a task ticked before any code was written, a
main spec written after the change was moved). Each kind takes a ``rule``: one rubric item per rule,
each citing its own lines (DESIGN §4 plugin rule) -- the kinds are parsers, the rubric decides::

    openspec.delta        rule: layout | delta_sections | requirement_blocks | requirement_text | shall_must | scenario
                                | scenario_heading | when_then | removed_reason_migration | renamed_from_to | purpose_new
                                | no_purpose_existing | kebab
    openspec.capabilities rule: declared | listed_have_specs | specs_listed
    openspec.main_spec    rule: exists | requirements_section | no_delta_headers | purpose | purpose_copied | scenarios
                                | when_then | title | synced
    openspec.archive      rule: sync_before_move
    openspec.tasks        rule: has_tasks | described | verification | unchecked_at_plan | all_checked | checked_after_edit
    openspec.read_files   artifacts: [ids], deltas: bool -- each file was read in the window

Format rules follow the schema's instruction text, which the documents call the authoritative guidance
(ff-change SKILL:98); the CLI validator's own regexes (``openspec validate``, not in the sandbox) are
implementation references only and never tighten a rule. Everything the agent writes is parsed
tolerantly: a malformed file is a failing unit, never an exception.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from recipe.grpo.qwen3_5.workflow_rubric import facts as F
from recipe.grpo.qwen3_5.workflow_rubric import markdown as M
from recipe.grpo.qwen3_5.workflow_rubric import refs
from recipe.grpo.qwen3_5.workflow_rubric.checks import register
from recipe.grpo.qwen3_5.workflow_rubric.context import EvalContext, Result
from recipe.grpo.qwen3_5.workflow_rubric.schema import Item

MAX_FILES = 200
MAX_TEXT = 200_000
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_HEAD = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
_OPS = ("ADDED", "MODIFIED", "REMOVED", "RENAMED")
_OP_TITLE = re.compile(r"^(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements$", re.I)
_REQ_TITLE = re.compile(r"^Requirement:\s*(.*)$", re.I)
_REQ_BULLET = re.compile(r"^\s*[-*+]\s*`?###\s*Requirement:\s*(.+?)`?\s*$", re.I)
_SCEN_TITLE = re.compile(r"^Scenario:\s*(.*)$", re.I)
_SCEN_LIKE = re.compile(r"^\s*(?:#{1,6}[ \t]*|[-*+][ \t]+(?:\*\*|__)?)Scenario\b", re.I)
_FROM = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*|__)?FROM(?:\*\*|__)?\s*:(?:\*\*|__)?\s*(.*\S)\s*$", re.I)
_TO = re.compile(r"^\s*(?:[-*+]\s*)?(?:\*\*|__)?TO(?:\*\*|__)?\s*:(?:\*\*|__)?\s*(.*\S)\s*$", re.I)
_KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TASK = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s*(.*)$")
_TASK_ID = re.compile(r"^\d+(?:\.\d+)+\.?(?=\s|$)")
_VERIFY = re.compile(r"\b(?:verif(?:y|ies|ied|ication)|tests?|passe?s?|passing|check(?:s|ed)?|confirm(?:s|ed)?|assert(?:s|ed)?|run(?:s|ning)?)\b", re.I)
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(.*)$")
_CODE = re.compile(r"`([^`\n]+)`")


# --------------------------------------------------------------------------------------------
# Parsing (tolerant; nothing here raises on agent text)
# --------------------------------------------------------------------------------------------
def _clip(text: str | None) -> str:
    return (text or "")[:MAX_TEXT]


def _lines(text: str | None) -> list[tuple[str, bool]]:
    """(line, inside a fenced block) of the text with HTML comments removed (template guidance left in place is no content)."""
    body = M.strip_comments(M.strip_fence(_clip(text))[0])
    out, fence = [], None
    for ln in body.split("\n"):
        f = _FENCE.match(ln)
        if f:
            if fence is None:
                fence = f.group(1)[0] * 3
            elif ln.strip().startswith(fence):
                fence = None
            out.append((ln, True))
            continue
        out.append((ln, fence is not None))
    return out


def _heading(ln: str) -> tuple[int, str] | None:
    m = _HEAD.match(ln)
    if not m:
        return None
    return len(m.group(1)), re.sub(r"^\*\*(.*)\*\*$", r"\1", (m.group(2) or "").strip()).strip()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


@dataclass
class Scenario:
    name: str
    body: str


@dataclass
class Requirement:
    op: str
    name: str
    description: str
    body: str
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class Spec:
    """One spec file: its level-2 sections, requirement blocks (with the delta operation they sit under), Purpose."""

    sections: list[tuple[str, str]] = field(default_factory=list)  # (title, op or "")
    requirements: list[Requirement] = field(default_factory=list)
    purpose: str | None = None
    renamed: list[tuple[str | None, str | None]] = field(default_factory=list)  # (from, to) per RENAMED pair
    scenario_like: list[str] = field(default_factory=list)
    h1: list[str] = field(default_factory=list)
    req_outside: int = 0  # ``### Requirement:`` headings outside any delta / Requirements section


def parse_spec(text: str | None) -> Spec:
    out = Spec()
    lines = _lines(text)
    sec_title, sec_op = None, ""
    req: Requirement | None = None
    scen: Scenario | None = None
    purpose: list[str] | None = None
    renamed_from: str | None = None

    def close_scen():
        nonlocal scen
        if scen is not None and req is not None:
            scen.body = scen.body.strip("\n")
            req.scenarios.append(scen)
        scen = None

    def close_req():
        nonlocal req
        close_scen()
        if req is not None:
            req.body = req.body.strip("\n")
            out.requirements.append(req)
        req = None

    for ln, fenced in lines:
        h = None if fenced else _heading(ln)
        if not fenced and _SCEN_LIKE.match(ln):
            out.scenario_like.append(ln.strip())
        if h is not None:
            level, title = h
            if level <= 2:
                close_req()
                if purpose is not None:
                    out.purpose = "\n".join(purpose).strip()
                    purpose = None
                if level == 1:
                    out.h1.append(title)
                    sec_title, sec_op = None, ""
                    continue
                m = _OP_TITLE.match(_norm(title))
                sec_title, sec_op = title, (m.group(1).upper() if m else "")
                out.sections.append((title, sec_op))
                if _norm(title).lower() == "purpose":
                    purpose = []
                continue
            if level == 3:
                close_req()
                m = _REQ_TITLE.match(title)
                if m:
                    if sec_op == "" and (sec_title or "").strip().lower() != "requirements":
                        out.req_outside += 1
                    req = Requirement(op=sec_op, name=_norm(m.group(1)), description="", body="")
                continue
            if level == 4 and req is not None:
                close_scen()
                m = _SCEN_TITLE.match(title)
                if m:
                    scen = Scenario(name=_norm(m.group(1)), body="")
                continue
            if level >= 5 and req is not None:
                close_scen()
                continue
        if purpose is not None and not fenced:
            purpose.append(ln)
        if sec_op == "REMOVED" and req is None and not fenced:
            m = _REQ_BULLET.match(ln)
            if m:
                out.requirements.append(Requirement(op="REMOVED", name=_norm(m.group(1)), description="", body=""))
                continue
        if sec_op == "RENAMED" and not fenced:
            fm, tm = _FROM.match(ln), _TO.match(ln)
            if fm:
                renamed_from = _req_name(fm.group(1))
                out.renamed.append((renamed_from, None))
            elif tm:
                if out.renamed and out.renamed[-1][1] is None:
                    out.renamed[-1] = (out.renamed[-1][0], _req_name(tm.group(1)))
                else:
                    out.renamed.append((None, _req_name(tm.group(1))))
        if req is not None:
            if scen is not None:
                scen.body += ln + "\n"
            else:
                req.body += ln + "\n"
                if not req.scenarios and ln.strip() and not fenced:
                    req.description += ln.strip() + "\n"
    close_req()
    if purpose is not None:
        out.purpose = "\n".join(purpose).strip()
    return out


def _req_name(v: str) -> str:
    v = v.strip().strip("`").strip()
    v = re.sub(r"^#{1,6}\s*", "", v)
    v = re.sub(r"^Requirement:\s*", "", v, flags=re.I)
    return _norm(v.strip("`"))


def _has_keyword(body: str, word: str) -> bool:
    """WHEN/THEN as a word: in capitals anywhere, or leading a line in any case (``- **WHEN**``, ``When``); markup not required."""
    if re.search(rf"\b{word}\b", body):
        return True
    return re.search(rf"(?im)^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*|__|\*|_)?{word}\b", body) is not None


# --------------------------------------------------------------------------------------------
# Locating the change, its delta specs and their main specs
# --------------------------------------------------------------------------------------------
def _dirs(ctx: EvalContext, change: str) -> tuple[str | None, list[str]]:
    """(the change directory at the end, every location the change directory had), absolute."""
    art = ctx.rubric.artifacts.get(change)
    if art is None:
        return None, []
    roots = F.roots_of(ctx.rubric, ctx.collected.workdir)
    locs = []
    for loc in art.locations:
        s, left = F.expand(loc, roots, ctx.collected.workdir, ctx.facts.var_bindings)
        if s.startswith("/") and not left:
            locs.append(s.rstrip("/"))
    final = ctx.facts.artifact_paths.get(change)
    return (final.rstrip("/") if final else None), locs


def _files_under(ctx: EvalContext, d: str) -> list[str]:
    pre = d.rstrip("/") + "/"
    return sorted(p for p in ctx.collected.files if p.startswith(pre))[:MAX_FILES]


def _deltas(ctx: EvalContext, change: str) -> tuple[str | None, list[tuple[str, str, str]]]:
    """(change dir, [(capability path, absolute path, text)]) of the delta specs: files named ``spec.md`` at
    depth >= 1 under the change's ``specs/`` (schema.yaml:62-66)."""
    final, _ = _dirs(ctx, change)
    if not final:
        return None, []
    out = []
    pre = final + "/specs/"
    for p in _files_under(ctx, final + "/specs"):
        rel = p[len(pre) :]
        if rel.endswith("/spec.md") and not any(part.startswith(".") for part in rel.split("/")):
            out.append((rel[: -len("/spec.md")], p, ctx.collected.files.get(p) or ""))
    return final, out


def _main_root(ctx: EvalContext, root: str) -> str | None:
    roots = F.roots_of(ctx.rubric, ctx.collected.workdir)
    s, left = F.expand(root, roots, ctx.collected.workdir, ctx.facts.var_bindings)
    return s.rstrip("/") if s.startswith("/") and not left else None


def _proposal_caps(ctx: EvalContext, proposal: str) -> tuple[list[str], list[str]] | None:
    """(new, modified) capability paths the proposal lists (``- `<capability-path>`: ...``); None when absent."""
    text = ctx.artifact_text(proposal, "final")
    if text is None:
        return None
    text = M.strip_comments(M.strip_fence(_clip(text))[0])
    out = []
    for title in ("New Capabilities", "Modified Capabilities"):
        body = M.section(text, title) or ""
        caps = []
        for ln in body.split("\n"):
            m = _LIST_ITEM.match(ln)
            if not m:
                continue
            v = m.group(1).strip()
            c = _CODE.match(v)
            cap = c.group(1) if c else re.split(r"\s*(?::|—|–|\s-\s)\s*", v, maxsplit=1)[0]
            cap = cap.strip().strip("*_`").strip().strip("/")
            if cap.startswith("specs/"):
                cap = cap[len("specs/") :]
            if cap.endswith("/spec.md"):
                cap = cap[: -len("/spec.md")]
            if not cap or M.is_none(cap) or M.is_placeholder(cap) or "<" in cap:
                continue
            caps.append(cap)
        out.append(caps)
    return out[0], out[1]


def _ratio(item: Item, good: list[str], bad: list[str], what: str) -> Result:
    if not good and not bad:
        return Result.not_applicable(item, f"no {what}")
    detail = f"{len(good)}/{len(good) + len(bad)} {what}" + (f"; failing: {', '.join(bad[:3])}" if bad else "")
    return Result.ratio(item, len(good), len(good) + len(bad), detail[:300])


# --------------------------------------------------------------------------------------------
# openspec.delta
# --------------------------------------------------------------------------------------------
CONDITIONAL_DELTA_RULES = ("scenario_heading", "removed_reason_migration", "renamed_from_to", "no_purpose_existing")
DELTA_RULES = (
    "layout", "delta_sections", "requirement_blocks", "requirement_text", "shall_must", "scenario", "scenario_heading", "when_then",
    "removed_reason_migration", "renamed_from_to", "purpose_new", "no_purpose_existing", "kebab",
)  # fmt: skip


@register("openspec.delta", params={"rule": True, "change": False, "proposal": False}, availability=("sandbox_file",), common=False, choices={"rule": DELTA_RULES})
def delta(item: Item, ctx: EvalContext) -> Result:
    """rule: one format rule of the change's delta specs (``specs/<capability-path>/spec.md``), scored as the share of
    files / sections / requirements / scenarios that keep it; ``layout`` and ``delta_sections`` fail when there is no delta."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    change = str(p.get("change") or "change")
    final, deltas = _deltas(ctx, change)
    if final is None:
        return Result.no(item, "change directory absent")
    if rule not in DELTA_RULES:
        return Result.no(item, f"unknown rule {rule!r}")
    if rule == "layout":
        md = [q for q in _files_under(ctx, final + "/specs") if q.endswith(".md")]
        if not md:
            return Result.no(item, "no delta spec under specs/")
        pre = final + "/specs/"
        good = [q[len(pre) :] for q in md if re.fullmatch(r"(?:[^/]+/)+spec\.md", q[len(pre) :])]
        bad = [q[len(pre) :] for q in md if q[len(pre) :] not in good]
        return _ratio(item, good, bad, "spec files at specs/<capability-path>/spec.md")
    if not deltas:
        # DESIGN D5: a change without a delta spec (skip_specs or none written) keeps the spec rules in the
        # denominator and fails them; only the rules about optional operations have nothing to judge
        return Result.not_applicable(item, "no delta spec") if rule in CONDITIONAL_DELTA_RULES else Result.no(item, "no delta spec")
    parsed = [(cap, parse_spec(text)) for cap, _, text in deltas]
    good: list[str] = []
    bad: list[str] = []
    if rule == "delta_sections":
        for cap, sp in parsed:
            (good if any(op for _, op in sp.sections) else bad).append(cap)
        return _ratio(item, good, bad, "delta specs with an ADDED/MODIFIED/REMOVED/RENAMED Requirements section")
    if rule == "kebab":
        # "Any path segment newly introduced in the proposal must be kebab-case"; a modified capability keeps its existing path
        listed = _proposal_caps(ctx, str(p.get("proposal") or "proposal"))
        modified = set(listed[1]) if listed else set()
        for cap, _ in parsed:
            if cap not in modified:
                (good if all(_KEBAB.fullmatch(seg) for seg in cap.split("/")) else bad).append(cap)
        return _ratio(item, good, bad, "kebab-case capability paths")
    if rule in ("purpose_new", "no_purpose_existing"):
        listed = _proposal_caps(ctx, str(p.get("proposal") or "proposal"))
        modified = set(listed[1]) if listed else set()
        for cap, sp in parsed:
            if rule == "purpose_new" and cap not in modified:
                ok = sp.purpose is not None and len(_norm(sp.purpose)) >= 50
                (good if ok else bad).append(cap)
            elif rule == "no_purpose_existing" and cap in modified:
                (good if sp.purpose is None else bad).append(cap)
        what = "new-capability deltas opening with a Purpose of 50+ characters" if rule == "purpose_new" else "existing-capability deltas without a Purpose"
        return _ratio(item, good, bad, what)
    if rule == "requirement_blocks":
        for cap, sp in parsed:
            for title, op in sp.sections:
                if op not in ("ADDED", "MODIFIED"):
                    continue
                named = [r for r in sp.requirements if r.op == op and r.name]
                (good if named else bad).append(f"{cap}:{title}")
        return _ratio(item, good, bad, "ADDED/MODIFIED sections with ### Requirement: blocks")
    if rule == "renamed_from_to":
        for cap, sp in parsed:
            if not any(op == "RENAMED" for _, op in sp.sections):
                continue
            pairs = sp.renamed
            ok = bool(pairs) and all(a and b for a, b in pairs)
            (good if ok else bad).append(cap)
        return _ratio(item, good, bad, "RENAMED sections in FROM:/TO: pairs")
    if rule == "removed_reason_migration":
        for cap, sp in parsed:
            for r in sp.requirements:
                if r.op != "REMOVED":
                    continue
                reason, migration = M.field_value(r.body, "Reason"), M.field_value(r.body, "Migration")
                ok = bool(reason and reason.strip() and not M.is_placeholder(reason)) and bool(migration and migration.strip() and not M.is_placeholder(migration))
                (good if ok else bad).append(f"{cap}:{r.name or '?'}")
        return _ratio(item, good, bad, "REMOVED requirements with Reason and Migration")
    if rule == "scenario_heading":
        for cap, sp in parsed:
            for ln in sp.scenario_like:
                (good if re.match(r"^####(?!#)[ \t]*Scenario:", ln, re.I) else bad).append(f"{cap}:{ln[:40]}")
        return _ratio(item, good, bad, "scenarios written as '#### Scenario:' headings")
    reqs = [(cap, r) for cap, sp in parsed for r in sp.requirements if r.op in ("ADDED", "MODIFIED")]
    if rule == "requirement_text":
        for cap, r in reqs:
            (good if r.description.strip() and not M.is_placeholder(r.description.strip()) else bad).append(f"{cap}:{r.name or '?'}")
        return _ratio(item, good, bad, "ADDED/MODIFIED requirements with a description")
    if rule == "shall_must":
        for cap, r in reqs:
            (good if re.search(r"\b(?:SHALL|MUST)\b", r.description) else bad).append(f"{cap}:{r.name or '?'}")
        return _ratio(item, good, bad, "requirements stating SHALL/MUST")
    if rule == "scenario":
        for cap, r in reqs:
            (good if r.scenarios else bad).append(f"{cap}:{r.name or '?'}")
        return _ratio(item, good, bad, "requirements with a '#### Scenario:'")
    # when_then
    for cap, r in reqs:
        for s in r.scenarios:
            (good if _has_keyword(s.body, "WHEN") and _has_keyword(s.body, "THEN") else bad).append(f"{cap}:{s.name or '?'}")
    return _ratio(item, good, bad, "scenarios with WHEN and THEN")


# --------------------------------------------------------------------------------------------
# openspec.capabilities
# --------------------------------------------------------------------------------------------
CAPABILITY_RULES = ("declared", "listed_have_specs", "specs_listed")


@register("openspec.capabilities", params={"rule": True, "change": False, "proposal": False}, availability=("sandbox_file",), common=False, choices={"rule": CAPABILITY_RULES})
def capabilities(item: Item, ctx: EvalContext) -> Result:
    """rule ``declared``: the proposal lists at least one capability; ``listed_have_specs``: every listed capability has
    its delta spec ``specs/<capability-path>/spec.md``; ``specs_listed``: every delta spec is a listed capability."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    listed = _proposal_caps(ctx, str(p.get("proposal") or "proposal"))
    if listed is None:
        return Result.no(item, "proposal absent")
    caps = list(dict.fromkeys([*listed[0], *listed[1]]))
    if rule == "declared":
        return Result.ok(item, f"{len(caps)} capabilities") if caps else Result.no(item, "no capability listed")
    final, deltas = _deltas(ctx, str(p.get("change") or "change"))
    have = {cap for cap, _, _ in deltas}
    if rule == "listed_have_specs":
        if not caps:
            return Result.no(item, "no capability listed")
        return _ratio(item, [c for c in caps if c in have], [c for c in caps if c not in have], "listed capabilities with a delta spec")
    if rule == "specs_listed":
        return _ratio(item, [c for c in sorted(have) if c in caps], [c for c in sorted(have) if c not in caps], "delta specs the proposal lists")
    return Result.no(item, f"unknown rule {rule!r}")


# --------------------------------------------------------------------------------------------
# openspec.main_spec
# --------------------------------------------------------------------------------------------
MAIN_RULES = ("exists", "requirements_section", "no_delta_headers", "purpose", "purpose_copied", "scenarios", "when_then", "title", "synced")


@register("openspec.main_spec", params={"rule": True, "change": False, "root": True}, availability=("sandbox_file",), common=False, choices={"rule": MAIN_RULES})
def main_spec(item: Item, ctx: EvalContext) -> Result:
    """rule: one rule of the main specs the change's deltas merge into (``<root>/<capability-path>/spec.md``):
    ``exists``, ``requirements_section`` (one ``## Requirements`` holding every requirement), ``no_delta_headers``,
    ``purpose`` / ``purpose_copied`` (the new capability's delta Purpose, verbatim), ``scenarios``, ``when_then``,
    ``title`` (``# <capability> Specification``), ``synced`` (ADDED / MODIFIED present with their scenarios,
    REMOVED gone, RENAMED under the new name only)."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    if rule not in MAIN_RULES:
        return Result.no(item, f"unknown rule {rule!r}")
    root = _main_root(ctx, str(p.get("root")))
    final, deltas = _deltas(ctx, str(p.get("change") or "change"))
    if root is None:
        return Result.no(item, "main spec root unresolved")
    if final is None:
        return Result.no(item, "change directory absent")
    if not deltas:
        return Result.no(item, "no delta spec to merge (DESIGN D5)")
    good: list[str] = []
    bad: list[str] = []
    mains = []
    for cap, _, text in deltas:
        d = parse_spec(text)
        path = f"{root}/{cap}/spec.md"
        mt = ctx.collected.files.get(path)
        mains.append((cap, d, mt, parse_spec(mt) if mt is not None else None))
    if rule == "exists":
        for cap, d, mt, _ in mains:
            if not any(r.op in ("ADDED", "MODIFIED") for r in d.requirements) and not any(b for _, b in d.renamed):
                continue  # a delta that only removes may retire its capability (sync-specs SKILL:114-131)
            (good if mt is not None else bad).append(cap)
        return _ratio(item, good, bad, "main specs for the delta capabilities") if good or bad else Result.no(item, "the deltas add no requirement")
    if rule == "synced":
        for cap, d, mt, m in mains:
            names = {r.name for r in m.requirements} if m else set()
            by = {r.name: r for r in m.requirements} if m else {}
            for r in d.requirements:
                if r.op == "ADDED":
                    (good if r.name and r.name in names else bad).append(f"{cap}: ADDED {r.name}")
                elif r.op == "MODIFIED":
                    ok = bool(r.name) and r.name in by and {s.name for s in r.scenarios} <= {s.name for s in by[r.name].scenarios}
                    (good if ok else bad).append(f"{cap}: MODIFIED {r.name}")
                elif r.op == "REMOVED":
                    (good if r.name and r.name not in names else bad).append(f"{cap}: REMOVED {r.name}")
            for a, b in d.renamed:
                ok = bool(a and b) and b in names and a not in names
                (good if ok else bad).append(f"{cap}: RENAMED {a} -> {b}")
        return _ratio(item, good, bad, "delta operations reflected in the main specs") if good or bad else Result.no(item, "the deltas hold no operation to sync")
    present = [(cap, d, m) for cap, d, mt, m in mains if m is not None]
    if not present:
        return Result.no(item, "no main spec written")
    for cap, d, m in present:
        if rule == "requirements_section":
            n = sum(1 for t, _ in m.sections if _norm(t).lower() == "requirements")
            ok = n == 1 and m.req_outside == 0 and all(r.op == "" for r in m.requirements)
            (good if ok else bad).append(cap)
        elif rule == "no_delta_headers":
            (good if not any(op for _, op in m.sections) else bad).append(cap)
        elif rule == "purpose":
            (good if m.purpose and not M.is_placeholder(m.purpose) else bad).append(cap)
        elif rule == "purpose_copied":
            if d.purpose is None:
                continue
            (good if m.purpose is not None and _norm(m.purpose) == _norm(d.purpose) else bad).append(cap)
        elif rule == "title":
            (good if any(re.fullmatch(r".+\s+Specification", _norm(t), re.I) for t in m.h1) else bad).append(cap)
        elif rule == "scenarios":
            for r in m.requirements:
                (good if r.scenarios else bad).append(f"{cap}:{r.name or '?'}")
        else:  # when_then
            for r in m.requirements:
                for s in r.scenarios:
                    (good if _has_keyword(s.body, "WHEN") and _has_keyword(s.body, "THEN") else bad).append(f"{cap}:{s.name or '?'}")
    return _ratio(item, good, bad, f"main specs keeping '{rule}'")


# --------------------------------------------------------------------------------------------
# openspec.archive
# --------------------------------------------------------------------------------------------
@register("openspec.archive", params={"rule": True, "change": False, "root": True}, availability=("trace",), common=False, choices={"rule": ("sync_before_move",)})
def archive(item: Item, ctx: EvalContext) -> Result:
    """rule ``sync_before_move``: every main-spec write of the change's capabilities happens before the change
    directory leaves its active location (the archive ``mv``); not applicable when it never moved or nothing synced."""
    p = item.check.params or {}
    if str(p.get("rule")) != "sync_before_move":
        return Result.no(item, f"unknown rule {p.get('rule')!r}")
    final, locs = _dirs(ctx, str(p.get("change") or "change"))
    root = _main_root(ctx, str(p.get("root")))
    if not locs or root is None:
        return Result.no(item, "change or main spec root unresolved")
    active = locs[0] + "/"
    left = sorted(e.step for path, evs in ctx.facts.writes.items() if path.startswith(active) for e in evs if e.op in ("move_out", "delete") and e.ok is not False)
    if not left:
        return Result.not_applicable(item, "the change never left its active location")
    move = left[0]
    _, deltas = _deltas(ctx, str(p.get("change") or "change"))
    mains = {f"{root}/{cap}/spec.md" for cap, _, _ in deltas}
    writes = sorted(e.step for path in mains for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.op in F.WRITE_OPS)
    if not writes:
        return Result.not_applicable(item, "no main spec written")
    late = [s for s in writes if s >= move]
    if late:
        return Result.no(item, f"main spec written at step {late[0]}, after the change moved at step {move}")
    return Result.ok(item, f"main specs written by step {writes[-1]}, change moved at step {move}")


# --------------------------------------------------------------------------------------------
# openspec.tasks
# --------------------------------------------------------------------------------------------
def _tasks(text: str | None) -> list[tuple[bool, str]]:
    """(checked, description without its X.Y id) of every checkbox task, HTML comments removed."""
    out = []
    for ln, _ in _lines(text):
        m = _TASK.match(ln)
        if m:
            out.append((m.group(1) in "xX", _TASK_ID.sub("", m.group(2).strip(), count=1).strip()))
    return out


def _described(desc: str) -> bool:
    return bool(desc) and not M.is_placeholder(desc)


TASK_RULES = ("has_tasks", "described", "verification", "unchecked_at_plan", "all_checked", "checked_after_edit", "verified")


@register("openspec.tasks", params={"rule": True, "artifact": False}, availability=("sandbox_file", "trace"), common=False, choices={"rule": TASK_RULES})
def tasks(item: Item, ctx: EvalContext) -> Result:
    """rule: ``has_tasks`` (a checkbox task with a description: apply is not blocked), ``described`` / ``verification``
    (each task says what to do and how to verify it), ``unchecked_at_plan`` (as the planning stage left it, every task
    is ``- [ ]``), ``all_checked`` (at the end every task is ``- [x]``), ``checked_after_edit`` (no task is ticked
    before the first code change of the final change), ``verified`` (a task whose description names a test command is
    ticked only after a valid run of that command, made after the task's last code change)."""
    p = item.check.params or {}
    rule = str(p.get("rule"))
    aid = str(p.get("artifact") or item.target.ref)
    if rule not in TASK_RULES:
        return Result.no(item, f"unknown rule {rule!r}")
    if rule == "unchecked_at_plan":
        ts = _tasks(ctx.artifact_text(aid, "stage_end"))
        if not ts:
            return Result.no(item, "no checkbox task when planning ended")
        done = [d for c, d in ts if c]
        return Result.no(item, f"{len(done)}/{len(ts)} tasks already ticked when planning ended") if done else Result.ok(item, f"{len(ts)} open tasks")
    if rule == "checked_after_edit":
        return _checked_after_edit(item, ctx, aid)
    if rule == "verified":
        return _verified(item, ctx, aid)
    text = ctx.artifact_text(aid, "final")
    if text is None:
        return Result.no(item, "tasks absent")
    ts = _tasks(text)
    if rule == "has_tasks":
        n = sum(1 for _, d in ts if _described(d))
        return Result.ok(item, f"{n} tasks") if n else Result.no(item, "no checkbox task with a description")
    if not ts:
        return Result.no(item, "no checkbox task")
    if rule == "all_checked":
        open_ = [d for c, d in ts if not c]
        return Result.no(item, f"{len(open_)}/{len(ts)} tasks open: {open_[0][:40]!r}") if open_ else Result.ok(item, f"{len(ts)} tasks done")
    if rule == "described":
        return _ratio(item, [d for _, d in ts if _described(d)], [d or "?" for _, d in ts if not _described(d)], "tasks with a description")
    return _ratio(item, [d for _, d in ts if _VERIFY.search(d)], [d[:40] or "?" for _, d in ts if not _VERIFY.search(d)], "tasks stating how to verify them")


def _checked_after_edit(item: Item, ctx: EvalContext, aid: str) -> Result:
    art = ctx.rubric.artifacts.get(aid)
    if art is None:
        return Result.no(item, f"artifact {aid!r} undefined")
    evs = sorted(
        (e for path in F.location_paths(ctx.rubric, ctx.facts, ctx.collected, art) for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.content is not None),
        key=lambda e: (e.step, e.action_index),
    )
    prev, first_tick = 0, None
    for e in evs:
        n = sum(1 for c, _ in _tasks(e.content) if c)
        if n > prev and first_tick is None:
            first_tick = e.step
        prev = n
    if first_tick is None:
        return Result.not_applicable(item, "no task ticked in the trace")
    change = F.change_paths(ctx)
    edits = [e.step for e in ctx.facts.repo_writes if e.ok is not False and e.path in change]
    if not edits:
        return Result.no(item, f"task ticked at step {first_tick} with no code change in the final change")
    if first_tick < min(edits):
        return Result.no(item, f"task ticked at step {first_tick}, before the first code change (step {min(edits)})")
    return Result.ok(item, f"first tick at step {first_tick}, first code change at step {min(edits)}")


def _entries(text: str | None) -> list[tuple[bool, str, str]]:
    """(checked, key, description) per checkbox task: the key is its X.Y id, else its description."""
    out = []
    for ln, _ in _lines(text):
        m = _TASK.match(ln)
        if m:
            body = m.group(2).strip()
            tid = _TASK_ID.match(body)
            desc = _TASK_ID.sub("", body, count=1).strip()
            out.append((m.group(1) in "xX", tid.group(0).rstrip(".") if tid else _norm(desc).lower(), desc))
    return out


def _runner_spans(desc: str, workdir: str | None) -> list[tuple[str, str, frozenset[str]]]:
    """(normalised command, runner name, normalised targets) of each code span of the description that runs tests."""
    from recipe.grpo.qwen3_5.workflow_rubric import evidence
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    out = []
    for span in _CODE.findall(desc or "")[:20]:
        try:
            segs = shell.flat(shell.split(span[:2000], workdir)[0])
        except Exception:  # noqa: BLE001 -- agent text
            continue
        for seg in segs:
            hit = evidence.classify(seg)
            if hit is not None and hit.runner.kind == "test":
                tg = frozenset(refs.norm_path(t, workdir) for t in (*hit.targets, *hit.node_ids))
                out.append((refs.norm_command(_norm(span)), hit.runner.name, tg))
                break
    return out


def _verified(item: Item, ctx: EvalContext, aid: str) -> Result:
    art = ctx.rubric.artifacts.get(aid)
    if art is None:
        return Result.no(item, f"artifact {aid!r} undefined")
    evs = sorted(
        (e for path in F.location_paths(ctx.rubric, ctx.facts, ctx.collected, art) for e in ctx.facts.writes.get(path, []) if e.ok is not False and e.content is not None),
        key=lambda e: (e.step, e.action_index),
    )
    ticks: dict[str, int] = {}
    desc: dict[str, str] = {}
    prev: set[str] = set()
    for e in evs:
        ents = _entries(e.content)
        cur = {k for c, k, _ in ents if c}
        for k in cur - prev:
            ticks.setdefault(k, e.step)
        desc.update({k: d for _, k, d in ents})
        prev = cur
    wd = ctx.collected.workdir
    good, bad = [], []
    for k, step in sorted(ticks.items(), key=lambda kv: kv[1]):
        want = _runner_spans(desc.get(k, ""), wd)
        if not want:
            continue
        edits = [e.step for e in ctx.facts.repo_writes if e.ok is not False and e.step < step]
        after = max(edits) if edits else 0
        cmds = {w[0] for w in want}
        sels = {(w[1], w[2]) for w in want if w[2]}
        ok = any(
            r.valid
            and r.kind == "test"
            and after < r.step < step
            and (refs.norm_command(_norm(r.command)) in cmds or refs.norm_command(_norm(r.segment)) in cmds or (r.runner, frozenset(refs.norm_path(t, wd) for t in r.targets)) in sels)
            for r in ctx.facts.runs
        )
        (good if ok else bad).append(k)
    return _ratio(item, good, bad, "ticked tasks verified by a valid run of their command after their last code change")


# --------------------------------------------------------------------------------------------
# openspec.read_files
# --------------------------------------------------------------------------------------------
def _read_paths(ctx: EvalContext, want: set[str], w) -> set[str]:
    """The paths of ``want`` read (an editor view, or a reading verb of a shell segment naming them) inside the window."""
    from recipe.grpo.qwen3_5.workflow_rubric.trace import shell

    got: set[str] = set()
    if not want:
        return got
    wd = ctx.collected.workdir
    cwd_track = getattr(ctx.facts, "_cwd_track", None) or {}
    known = sorted(want)
    for step in ctx.run.steps:
        if not refs.in_window(step.n, w):
            continue
        for idx, a in enumerate(step.actions):
            cwd = cwd_track.get((step.n, idx), wd)
            if a.kind == "view" and a.path:
                hits = [shell.resolve(a.path, cwd)]
            elif a.kind == "shell" and a.command:
                try:
                    segs = shell.flat(shell.split(a.command[:20000], cwd)[0])
                    hits = [t for seg in segs for t in shell.read_targets(seg, known)]
                except Exception:  # noqa: BLE001 -- agent text: an unparsable command reads nothing
                    hits = []
            else:
                hits = []
            for h in hits:
                h = posixpath.normpath(h)
                got |= {x for x in want if x == h or x.startswith(h.rstrip("/") + "/")}
    return got


@register("openspec.read_files", params={"artifacts": False, "deltas": False, "change": False, "window": False}, availability=("trace",), common=False)
def read_files(item: Item, ctx: EvalContext) -> Result:
    """Each existing artifact of ``artifacts`` (and, with ``deltas``, each delta spec of the change) was read in the
    window -- at any of the locations it had; score the share read; not applicable when none of them exists."""
    p = item.check.params or {}
    spec = p["window"] if "window" in p else (f"stage:{item.stage}" if item.stage != "global" else None)
    w = refs.window(ctx, spec)
    if w is None:
        return Result.no(item, "window empty")
    groups: dict[str, set[str]] = {}
    for aid in p.get("artifacts") or []:
        art = ctx.rubric.artifacts.get(str(aid))
        if art is None or not ctx.facts.artifact_paths.get(str(aid)):
            continue
        groups[str(aid)] = set(F.location_paths(ctx.rubric, ctx.facts, ctx.collected, art))
    if p.get("deltas"):
        change = str(p.get("change") or "change")
        final, locs = _dirs(ctx, change)
        _, ds = _deltas(ctx, change)
        for cap, path, _ in ds:
            rel = path[len(final) + 1 :] if final else ""
            groups[f"specs/{cap}"] = {f"{d}/{rel}" for d in locs} | {path}
    if not groups:
        return Result.not_applicable(item, "none of the files exists")
    seen = _read_paths(ctx, set().union(*groups.values()), w)
    good = [k for k, paths in groups.items() if paths & seen]
    bad = [k for k in groups if k not in good]
    return _ratio(item, good, bad, "files read in the window")


__all__ = ["delta", "capabilities", "main_spec", "archive", "tasks", "read_files", "parse_spec"]
