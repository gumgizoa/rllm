"""The verifier's rule set: document lines -> atomic rules -> scoring methods -> judgments, and the rubric built
from it.

    python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.ruleset check    # what is out of step
    python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.ruleset sync     # rewrite what follows

Two things are written by hand; everything else follows from them.

``ruleset.yaml``:

    docs       the documents the agent sees (``DOCS``), each with a path (and the section of a prompt file)
    rubric     the rubric's head: schema, sources (their sha256 is filled in), roots, stages, artifacts, scoring
    rules      each atomic rule: id, primary stage and kind, text, and its ``methods`` -- the scoring methods
               that judge it, each placed in the matrix: ``{kind: F, stage: 1}`` (one judgment) or
               ``{kind: P, stages: [1, 2, 3, 4, 5]}`` (one per stage, items ``<method>@<stage>``), with
               ``log_only: true`` for a diagnostic, ``class`` when not the kind's usual, ``note`` to carry.
               A rule scored by nothing has ``excluded`` with why
    lines      every candidate line of the documents (blank lines and headings outside code blocks left out),
               with its text, and the rules it states (``rules``) or repeats (``dup``), or why neither (``skip``)

The code (``checks.MEASURABLE``, the keys ``measure`` sets; ``materials.METHOD_MATERIALS``, what each method
reads; ``judge.QUESTIONS``): a method key of the set must be measured by the code, and every measured key placed
by the set.

``rubric.yaml`` is generated (``generated_rubric``): one item per method placement and stage, its check kind
and params from the method key, its sources the rule's lines, its appendix the excluded rules. ``ruleset.md``
and ``rubric.md`` are its renders. ``sync`` writes all three (renumbering moved lines first); ``check`` reports:

    moved      a stored line now at another number, text unchanged (``sync`` renumbers it)
    changed    a stored line whose text is gone: its rules need review, then the entry is edited by hand
    new        a document line no entry accounts for: assign it rules, ``skip`` or ``dup``
    links      a broken link: an unknown rule, a rule with no line, a rule with neither methods nor
               ``excluded``, a placement without a kind or stage, a method the code does not measure or
               declares no materials for (or the reverse), a judge method with no question, two scored
               items making one judgment (rule, category, stage)
    stale      rubric.yaml, ruleset.md or rubric.md differ from what ``sync`` writes

The test suite runs ``check`` and fails on any report, so an edited document, a judgment added to the code
without a place in the set, or a placement without code cannot go unnoticed.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
RULESET = HERE / "ruleset.yaml"
RUBRIC = HERE / "rubric.yaml"
KINDS = {"P": "procedure", "F": "artifact form", "E": "execution", "C": "consistency", "R": "forbidden action", "Q": "content", "A": "report accuracy"}
CLASS_OF_KIND = {"F": "structure", "Q": "content"}  # else evidence
METHOD_KEYS = {
    "claim": "check/{check}",
    "rule": "rule/{check}",
    "atom": "atom/{rule}",
    "form": "form/{rule}",
    "procedure": "proc/{rule}",
    "run": "run/{measure}",
    "judge": "judge/{question}",
}  # check kind (aidlc_v4_eval.<kind>) -> method key, from the item's params
CHECK_KIND = {"check": "claim", "rule": "rule", "atom": "atom", "form": "form", "proc": "procedure", "run": "run", "judge": "judge"}  # method prefix -> check kind
TASK = "task"  # a rule's ``source`` when it is a condition of the task, stated on no document line


@dataclass(frozen=True)
class Line:
    doc: str
    n: int
    text: str
    block: bool  # inside a code block (an artifact skeleton, a diagram)

    @property
    def at(self) -> str:
        return f"{self.doc}:{self.n}"


def doc_lines(docs: dict, root: Path = PKG) -> list[Line]:
    """The candidate lines of each document: not blank, not a heading outside a code block, not a fence;
    a document with ``section: TAG`` contributes only the lines inside ``<TAG>...</TAG>``."""
    out = []
    for doc, spec in docs.items():
        tag, inside, block = spec.get("section"), not spec.get("section"), False
        for n, raw in enumerate((root / spec["path"]).read_text().splitlines(), start=1):
            s = raw.strip()
            if tag and s in (f"<{tag}>", f"</{tag}>"):
                inside = s == f"<{tag}>"
                continue
            if not inside:
                continue
            if s.startswith("```"):
                block = not block
                continue
            if s and (block or not s.startswith("#")):
                out.append(Line(doc, n, s, block))
    return out


def method_key(item: dict) -> str:
    """The method an item measures: its check, every stage of a per-stage check alike."""
    kind = item["check"]["kind"].split(".")[-1]
    p = item["check"].get("params") or {}
    return METHOD_KEYS[kind].format(**p)


def load(path: Path = RULESET) -> dict:
    return yaml.safe_load(path.read_text())


def _align(stored: list[dict], current: list[Line]) -> tuple[dict[int, Line], list[int], list[Line]]:
    """Stored entry index -> current line (same text), the stored entries whose text is gone, the
    current lines no stored entry has."""
    by_doc: dict[str, tuple[list[int], list[Line]]] = {}
    for i, e in enumerate(stored):
        by_doc.setdefault(e["at"].split(":")[0], ([], []))[0].append(i)
    for ln in current:
        by_doc.setdefault(ln.doc, ([], []))[1].append(ln)
    match, gone, new = {}, [], []
    for olds, news in by_doc.values():
        sm = difflib.SequenceMatcher(None, [stored[i]["text"] for i in olds], [ln.text for ln in news], autojunk=False)
        seen_old, seen_new = set(), set()
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                match[olds[a + k]] = news[b + k]
                seen_old.add(a + k)
                seen_new.add(b + k)
        gone += [olds[k] for k in range(len(olds)) if k not in seen_old]
        new += [news[k] for k in range(len(news)) if k not in seen_new]
    return match, gone, new


def dups(entry: dict) -> list[str]:
    """The rules a line repeats (``dup``: one id, or a list)."""
    d = entry.get("dup")
    return [] if not d else [d] if isinstance(d, str) else list(d)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(rs: dict, rule: str) -> list[dict]:
    """An item's sources: its rule's lines (the lines that state it, else those that repeat it)."""
    primary = [e for e in rs["lines"] if rule in (e.get("rules") or [])]
    picked = primary or [e for e in rs["lines"] if rule in dups(e)]
    if not picked:
        first = next(e for e in rs["lines"] if e["at"].split(":")[0] == "I")
        picked = [first]  # a task condition (``source: task``): the instruction's first line
    out = []
    for e in sorted(picked, key=lambda e: (e["at"].split(":")[0], int(e["at"].split(":")[1]))):
        doc, n = e["at"].split(":")
        out.append({"doc": doc, "lines": [int(n), int(n)], "quote": e["text"]})
    return out


# --- the rubric, generated ---------------------------------------------------------------------


def placements(rule: dict) -> list[tuple[str, dict, int, bool]]:
    """A rule's judgments: (method key, placement, stage number, per-stage) -- one per stage of ``stages``,
    or one at ``stage``."""
    out = []
    for m, p in (rule.get("methods") or {}).items():
        p = p or {}
        if "stages" in p:
            out += [(m, p, int(k), True) for k in p["stages"]]
        else:
            out.append((m, p, int(p.get("stage", rule.get("stage", 0))), False))
    return out


def item_id(method: str, stage: int, per_stage: bool) -> str:
    """``<method>@<stage>`` for a per-stage check (form and procedure always, an atom placed by ``stages``)."""
    return f"{method}@{stage}" if per_stage or method.split("/")[0] in ("form", "proc") else method


def _check(method: str, stage: int, per_stage: bool) -> dict:
    prefix, name = method.split("/", 1)
    kind = CHECK_KIND[prefix]
    params = {"claim": {"check": name}, "rule": {"check": name}, "atom": {"rule": name}, "form": {"rule": name}, "procedure": {"rule": name}, "run": {"measure": name}, "judge": {"question": name}}[
        kind
    ]
    if kind in ("form", "procedure") or (kind == "atom" and per_stage):
        params["stage"] = stage
    return {"kind": f"aidlc_v4_eval.{kind}", "params": params}


def generated_rubric(rs: dict, root: Path = PKG, questions: dict[str, str] | None = None) -> dict:
    """``rubric.yaml`` from the set: its head (document sha256 filled in), one item per placement and stage,
    the excluded rules as the appendix. ``questions``: judge question id -> text (``judge.QUESTIONS``), the
    note of a judge item."""
    head = dict(rs["rubric"])
    paths = {d: s["path"] for d, s in rs["docs"].items()}
    head["sources"] = [{**s, "sha256": _sha(root / paths[s["id"]])} if s["id"] in paths else dict(s) for s in head["sources"]]
    items = []
    for r in rs["rules"]:
        for m, p, k, per_stage in placements(r):
            prefix = m.split("/")[0]
            kind = p["kind"]
            target = {"type": "artifact", "ref": f"a{k}", "state": "final"} if k and (prefix == "form" or (prefix == "atom" and per_stage)) else {"type": "action", "ref": "run", "state": "final"}
            item = {
                "id": item_id(m, k, per_stage),
                "scope": "specific",
                "class": p.get("class") or CLASS_OF_KIND.get(kind, "evidence"),
                "stage": "global" if k == 0 else str(k),
                "target": target,
                "check": _check(m, k, per_stage),
                "requirement": "must",
                "category": kind,
                "rule": r["id"],
                "availability": ["trace"],
                "derived_by": "manual",
                "sources": sources(rs, r["id"]),
            }
            if p.get("log_only"):
                item["log_only"] = True
            note = p.get("note") or ((questions or {}).get(m.split("/", 1)[1]) if prefix == "judge" else None)
            if note:
                item["note"] = note
            items.append(item)
    groups: dict[str, dict[str, str]] = {}
    for r in rs["rules"]:
        if r.get("excluded"):
            groups.setdefault(r["excluded"]["why"], {})[r["id"]] = r["excluded"].get("detail", "")
    return {**head, "items": items, "appendix": {"rules_without_items": groups}}


def _questions() -> dict[str, str]:
    from .judge import QUESTIONS

    return {qid: text for qs in QUESTIONS.values() for qid, text in qs}


def dump(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)


class _Dumper(yaml.SafeDumper):
    pass


class _Flow(dict):
    pass


class _FlowList(list):
    pass


_Dumper.add_representer(_Flow, lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v, flow_style=True))
_Dumper.add_representer(_FlowList, lambda d, v: d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=True))


def dump_ruleset(rs: dict) -> str:
    """ruleset.yaml's layout: one document line per row, a method's placement on its key's row."""

    def flat(d: dict) -> _Flow:
        return _Flow({k: _FlowList(v) if isinstance(v, list) else v for k, v in d.items()})

    out = {
        **rs,
        "docs": {k: flat(v) for k, v in rs["docs"].items()},
        "rules": [{**r, **({"methods": {m: flat(p or {}) for m, p in r["methods"].items()}} if r.get("methods") else {})} for r in rs["rules"]],
        "lines": [flat(e) for e in rs["lines"]],
    }
    return yaml.dump(out, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10_000)


def render(rs: dict, rubric: dict, materials: dict[str, str], method_materials: dict[str, tuple[str, ...]]) -> str:
    """``ruleset.md``: rule -> lines -> methods (category, stages, materials), and the excluded rules."""
    place: dict[tuple[str, str], list[tuple[str, str, bool]]] = {}
    for it in rubric["items"]:
        place.setdefault((method_key(it), it["rule"]), []).append((it["category"], it["stage"], bool(it.get("log_only"))))
    judgments = sum(1 for it in rubric["items"] if not it.get("log_only"))
    lines_of: dict[str, list[str]] = {}
    for e in rs["lines"]:
        for r in e.get("rules") or []:
            lines_of.setdefault(r, []).append(e["at"])
    n_methods = sum(len(r.get("methods") or {}) for r in rs["rules"])
    out = [
        "# aidlc_v4_eval rule set",
        "",
        "Rendered from ruleset.yaml by `reward/ruleset.py sync`; edit the yaml, not this file.",
        f"{len(rs['lines'])} document lines -> {len(rs['rules'])} atomic rules -> {n_methods} methods -> {judgments} judgments"
        f" (scored rubric items; {len(rubric['items']) - judgments} more are diagnostics).",
        "A method's category and stages are its placement in ruleset.yaml; `global` is stage 0. Its materials are declared in the code (reward/materials.py).",
        "",
        "Materials: " + "; ".join(f"`{k}` {v}" for k, v in materials.items()),
        "",
        "| rule | stage | kind | rule text | lines | methods (category: stages; materials) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rs["rules"]:
        methods = []
        for m in r.get("methods") or {}:
            cats: dict[str, list[str]] = {}
            its = place.get((m, r["id"]), [])
            for c, s, _ in its:
                cats.setdefault(c, []).append("0" if s == "global" else str(s))
            where = ", ".join(f"{c}: {' '.join(sorted(set(ss)))}" for c, ss in cats.items())
            diag = ", diagnostic" if its and all(lo for *_, lo in its) else ""
            methods.append(f"`{m}` ({where}; {' '.join(method_materials.get(m, ()))}{diag})")
        if r.get("excluded"):
            methods.append(f"none: {r['excluded']['why']}" + (f" ({r['excluded']['detail']})" if r["excluded"].get("detail") else ""))
        if r.get("note"):
            methods.append(f"note: {r['note']}")
        src = TASK if r.get("source") == TASK else ", ".join(lines_of.get(r["id"], []))
        text = r["text"].replace("|", "\\|")
        out.append(f"| {r['id']} | {r['stage']} | {r['kind']} | {text} | {src} | {'<br>'.join(methods)} |")
    return "\n".join(out) + "\n"


def _code() -> tuple[frozenset[str], dict[str, str], dict[str, tuple[str, ...]], dict[str, str]]:
    """What the code declares: the measured keys, the materials and each method's, the judge questions."""
    from .checks import MEASURABLE
    from .materials import MATERIALS, METHOD_MATERIALS

    return MEASURABLE, MATERIALS, METHOD_MATERIALS, _questions()


def check(rs: dict | None = None, rubric: dict | None = None, root: Path = PKG) -> dict[str, list[str]]:
    """Every way the set, the documents, the code and the rubric are out of step (see the module docstring)."""
    rs = rs if rs is not None else load()
    rubric = rubric if rubric is not None else yaml.safe_load(RUBRIC.read_text())
    report: dict[str, list[str]] = {"moved": [], "changed": [], "new": [], "links": [], "stale": []}
    match, gone, new = _align(rs["lines"], doc_lines(rs["docs"], root))
    for i, ln in sorted(match.items()):
        if rs["lines"][i]["at"] != ln.at:
            report["moved"].append(f"{rs['lines'][i]['at']} -> {ln.at}: {ln.text[:80]}")
    for i in gone:
        e = rs["lines"][i]
        report["changed"].append(f"{e['at']} ({', '.join([*(e.get('rules') or []), *(f'dup:{d}' for d in dups(e))]) or e.get('skip')}): {e['text'][:80]}")
    report["new"] += [f"{ln.at}: {ln.text[:80]}" for ln in new]

    links = report["links"]
    ids = [r["id"] for r in rs["rules"]]
    known = set(ids)
    links += [f"rule {r} listed twice" for r in sorted({r for r in ids if ids.count(r) > 1})]
    for e in rs["lines"]:
        if bool(e.get("skip")) == bool(e.get("rules") or e.get("dup")):
            links.append(f"line {e['at']}: needs rules and/or dup, or else skip")
        links += [f"line {e['at']}: unknown rule {r}" for r in (e.get("rules") or []) + dups(e) if r not in known]
        links += [f"line {e['at']}: {r} both stated and repeated" for r in set(e.get("rules") or []) & set(dups(e))]
    stated = {r for e in rs["lines"] for r in e.get("rules") or []}
    measurable, materials, method_materials, questions = _code()
    placed: set[str] = set()
    for r in rs["rules"]:
        if r["kind"] not in KINDS:
            links.append(f"rule {r['id']}: kind {r['kind']!r}")
        if r["id"] not in stated and r.get("source") != TASK:
            links.append(f"rule {r['id']}: no document line states it")
        if bool(r.get("methods")) == bool(r.get("excluded")):
            links.append(f"rule {r['id']}: needs methods or excluded (exactly one)")
        for m, p in (r.get("methods") or {}).items():
            p = p or {}
            placed.add(m)
            if p.get("kind") not in KINDS or ("stage" not in p and "stages" not in p):
                links.append(f"method {m} ({r['id']}): placement needs kind and stage or stages, has {p}")
            if m.split("/")[0] not in CHECK_KIND:
                links.append(f"method {m} ({r['id']}): unknown prefix")
            links += [f"method {m}: unknown material {x}" for x in method_materials.get(m, ()) if x not in materials]
            if m.split("/")[0] == "judge" and m.split("/", 1)[1] not in questions:
                links.append(f"method {m}: no judge question")
    links += [f"method {m}: no materials declared (materials.METHOD_MATERIALS)" for m in sorted(placed - set(method_materials))]
    links += [f"method {m}: materials declared, placed by no rule" for m in sorted(set(method_materials) - placed)]
    try:
        gen = generated_rubric(rs, root, questions)
    except (KeyError, TypeError, ValueError) as e:  # a placement the generator cannot read: reported above
        links.append(f"rubric cannot be generated from the set: {type(e).__name__} {e}")
        gen = None
    if gen is not None:
        code_keys = {it["id"] for it in gen["items"] if not it["id"].startswith("judge/")}
        links += [f"item {k}: the code measures no such key" for k in sorted(code_keys - measurable)]
        links += [f"measurement {k}: no rule places it" for k in sorted(measurable - code_keys)]
        judged: dict[tuple[str, str, str], list[str]] = {}
        for it in gen["items"]:
            if not it.get("log_only"):
                judged.setdefault((it["rule"], it["category"], it["stage"]), []).append(it["id"])
        links += [f"judgment {r} {c}@{st}: scored items {', '.join(v)} (one per judgment)" for (r, c, st), v in sorted(judged.items()) if len(v) > 1]

    if gen is not None and not (report["moved"] or report["changed"] or report["new"]):
        if gen != rubric:
            report["stale"].append("rubric.yaml (run sync)")
        if root == PKG and not report["stale"]:
            from recipe.grpo.qwen3_5.scripts.render_rubric_md import render as render_rubric
            from recipe.grpo.qwen3_5.workflow_rubric import schema

            if (HERE / "ruleset.md").read_text() != render(rs, rubric, materials, method_materials):
                report["stale"].append("ruleset.md")
            if (HERE / "rubric.md").read_text() != render_rubric(schema.load(RUBRIC)):
                report["stale"].append("rubric.md")
    return {k: v for k, v in report.items() if v}


def sync(rs_path: Path = RULESET, rubric_path: Path = RUBRIC, root: Path = PKG) -> dict:
    """Renumber moved lines, then write the rubric and the renders; returns the remaining ``check`` report."""
    rs = yaml.safe_load(rs_path.read_text())
    match, _, _ = _align(rs["lines"], doc_lines(rs["docs"], root))
    for i, ln in match.items():
        rs["lines"][i]["at"] = ln.at
    rs["lines"].sort(key=lambda e: (list(rs["docs"]).index(e["at"].split(":")[0]), int(e["at"].split(":")[1])))
    rs_path.write_text(_header(rs_path) + dump_ruleset(rs))
    _, materials, method_materials, questions = _code()
    rubric = generated_rubric(rs, root, questions)
    rubric_path.write_text(dump(rubric))
    if rubric_path == RUBRIC:
        from recipe.grpo.qwen3_5.scripts.render_rubric_md import render as render_rubric
        from recipe.grpo.qwen3_5.workflow_rubric import schema

        (HERE / "rubric.md").write_text(render_rubric(schema.load(RUBRIC)))
        (HERE / "ruleset.md").write_text(render(rs, rubric, materials, method_materials))
    return check(rs, rubric, root)


def _header(path: Path) -> str:
    """The comment block that opens ruleset.yaml, kept through a rewrite."""
    text = path.read_text() if path.exists() else ""
    head = re.match(r"(?:#[^\n]*\n)*", text).group(0)
    return head


def main(argv: list[str]) -> int:
    if argv[1:] not in (["check"], ["sync"]):
        print(__doc__)
        return 2
    report = sync() if argv[1] == "sync" else check()
    for kind, rows in report.items():
        print(f"{kind} ({len(rows)})")
        for row in rows:
            print(f"  {row}")
    print("in step" if not report else "")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
