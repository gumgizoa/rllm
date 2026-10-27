"""The verifier's rule set: document lines -> atomic rules -> scoring methods -> rubric items.

    python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.ruleset check    # what is out of step
    python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_eval.reward.ruleset sync     # fix what follows

``ruleset.yaml`` holds the links written by hand:

    lines      every candidate line of what the agent sees (``DOCS``: blank lines and headings outside code
               blocks left out), with its text, and the rules it states -- or why it states none
               (``skip: <why>``, or ``dup: <rule>`` for a rule stated elsewhere first)
    rules      each atomic rule's primary stage and kind, and the methods that score it: rubric item keys
               (``method_key``; one key covers every stage of a per-stage check) with the materials each
               reads; or, scored by nothing, ``excluded`` with why
    materials  the shared readings a method may rest on (``read.py``, ``skeleton.py``, the judge)

``rubric.yaml``'s items are the last link: each item's key is one rule's method, and its ``category`` and
``stage`` place that method in the matrix. The rest of the rubric follows from the set: each item's
``sources`` are its rule's lines, ``sources[].sha256`` the documents', the appendix the excluded rules
(``sync`` writes them, and renders ``ruleset.md`` and ``rubric.md``).

``check`` aligns the stored lines with the documents by text (a diff, so a repeated line is no problem)
and reports, by kind:

    moved      a stored line now at another number, text unchanged (``sync`` renumbers it)
    changed    a stored line whose text is gone: its rules need review, then the entry is edited by hand
    new        a document line no entry accounts for: assign it rules, ``skip`` or ``dup``
    links      a broken link: an unknown rule or material, a rule with no line, a rule with neither
               methods nor ``excluded``, a method with no item of its rule, an item its rule does not
               list (one check may score two rules, in different stages: ``atom/B5d``)
    stale      what ``sync`` rewrites differs from the files (sources, sha256, appendix, the two renders)

The test suite runs ``check`` and fails on any report, so an edited document cannot go unnoticed.
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
METHOD_KEYS = {
    "claim": "check/{check}",
    "rule": "rule/{check}",
    "atom": "atom/{rule}",
    "form": "form/{rule}",
    "procedure": "proc/{rule}",
    "run": "run/{measure}",
    "judge": "judge/{question}",
}  # check kind (aidlc_v4_eval.<kind>) -> method key, from the item's params
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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(rs: dict, rule: str) -> list[dict]:
    """An item's sources: its rule's lines (the lines that state it, else those that repeat it)."""
    primary = [e for e in rs["lines"] if rule in (e.get("rules") or [])]
    picked = primary or [e for e in rs["lines"] if e.get("dup") == rule]
    if not picked:
        first = next(e for e in rs["lines"] if e["at"].split(":")[0] == "I")
        picked = [first]  # a task condition (``source: task``): the instruction's first line
    out = []
    for e in sorted(picked, key=lambda e: (e["at"].split(":")[0], int(e["at"].split(":")[1]))):
        doc, n = e["at"].split(":")
        out.append({"doc": doc, "lines": [int(n), int(n)], "quote": e["text"]})
    return out


def synced_rubric(rs: dict, rubric: dict, root: Path = PKG) -> dict:
    """The rubric with what follows from the set rewritten: item sources, document sha256, appendix."""
    out = dict(rubric)
    out["items"] = [{**it, "sources": sources(rs, it["rule"])} for it in rubric["items"]]
    paths = {d: s["path"] for d, s in rs["docs"].items()}
    out["sources"] = [{**s, "sha256": _sha(root / paths[s["id"]])} if s["id"] in paths else s for s in rubric["sources"]]
    groups: dict[str, dict[str, str]] = {}
    for r in rs["rules"]:
        if r.get("excluded"):
            groups.setdefault(r["excluded"]["why"], {})[r["id"]] = r["excluded"].get("detail", "")
    out["appendix"] = {**(rubric.get("appendix") or {}), "rules_without_items": groups}
    return out


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
    """ruleset.yaml's layout: one document line per row, a method's materials on its key's row."""

    def flat(d: dict) -> _Flow:
        return _Flow({k: _FlowList(v) if isinstance(v, list) else v for k, v in d.items()})

    out = {
        **rs,
        "docs": {k: flat(v) for k, v in rs["docs"].items()},
        "rules": [{**r, **({"methods": {m: _FlowList(x) for m, x in r["methods"].items()}} if r.get("methods") else {})} for r in rs["rules"]],
        "lines": [flat(e) for e in rs["lines"]],
    }
    return yaml.dump(out, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10_000)


def render(rs: dict, rubric: dict) -> str:
    """``ruleset.md``: rule -> lines -> methods (category, stages, materials), and the excluded rules."""
    place: dict[str, list[tuple[str, str]]] = {}
    for it in rubric["items"]:
        place.setdefault(method_key(it), []).append((it["category"], it["stage"]))
    lines_of: dict[str, list[str]] = {}
    for e in rs["lines"]:
        for r in e.get("rules") or []:
            lines_of.setdefault(r, []).append(e["at"])
    n_methods = sum(len(r.get("methods") or {}) for r in rs["rules"])
    out = [
        "# aidlc_v4_eval rule set",
        "",
        "Rendered from ruleset.yaml by `reward/ruleset.py sync`; edit the yaml, not this file.",
        f"{len(rs['lines'])} document lines -> {len(rs['rules'])} atomic rules -> {n_methods} methods -> {len(rubric['items'])} rubric items.",
        "A method's category and stages are its items' (`rubric.yaml`); `global` is stage 0.",
        "",
        "Materials: " + "; ".join(f"`{k}` {v}" for k, v in rs["materials"].items()),
        "",
        "| rule | stage | kind | rule text | lines | methods (category: stages; materials) |",
        "|---|---|---|---|---|---|",
    ]
    for r in rs["rules"]:
        methods = []
        for m, mats in (r.get("methods") or {}).items():
            cats: dict[str, list[str]] = {}
            for c, s in place.get(m, []):
                cats.setdefault(c, []).append("0" if s == "global" else s)
            where = ", ".join(f"{c}: {' '.join(sorted(set(ss)))}" for c, ss in cats.items())
            methods.append(f"`{m}` ({where}; {' '.join(mats)})")
        if r.get("excluded"):
            methods.append(f"none: {r['excluded']['why']}" + (f" ({r['excluded']['detail']})" if r["excluded"].get("detail") else ""))
        if r.get("note"):
            methods.append(f"note: {r['note']}")
        src = TASK if r.get("source") == TASK else ", ".join(lines_of.get(r["id"], []))
        text = r["text"].replace("|", "\\|")
        out.append(f"| {r['id']} | {r['stage']} | {r['kind']} | {text} | {src} | {'<br>'.join(methods)} |")
    return "\n".join(out) + "\n"


def check(rs: dict | None = None, rubric: dict | None = None, root: Path = PKG) -> dict[str, list[str]]:
    """Every way the set, the documents and the rubric are out of step (see the module docstring)."""
    rs = rs if rs is not None else load()
    rubric = rubric if rubric is not None else yaml.safe_load(RUBRIC.read_text())
    report: dict[str, list[str]] = {"moved": [], "changed": [], "new": [], "links": [], "stale": []}
    match, gone, new = _align(rs["lines"], doc_lines(rs["docs"], root))
    for i, ln in sorted(match.items()):
        if rs["lines"][i]["at"] != ln.at:
            report["moved"].append(f"{rs['lines'][i]['at']} -> {ln.at}: {ln.text[:80]}")
    for i in gone:
        e = rs["lines"][i]
        report["changed"].append(f"{e['at']} ({', '.join(e.get('rules') or []) or e.get('skip') or 'dup:' + str(e.get('dup'))}): {e['text'][:80]}")
    report["new"] += [f"{ln.at}: {ln.text[:80]}" for ln in new]

    links = report["links"]
    ids = [r["id"] for r in rs["rules"]]
    known = set(ids)
    links += [f"rule {r} listed twice" for r in sorted({r for r in ids if ids.count(r) > 1})]
    for e in rs["lines"]:
        kinds = [k for k in ("rules", "skip", "dup") if e.get(k)]
        if len(kinds) != 1:
            links.append(f"line {e['at']}: needs exactly one of rules / skip / dup, has {kinds}")
        links += [f"line {e['at']}: unknown rule {r}" for r in (e.get("rules") or []) + ([e["dup"]] if e.get("dup") else []) if r not in known]
    stated = {r for e in rs["lines"] for r in e.get("rules") or []}
    listed: set[tuple[str, str]] = set()  # (method, rule): one check may score two rules, in different stages
    for r in rs["rules"]:
        if r["kind"] not in KINDS:
            links.append(f"rule {r['id']}: kind {r['kind']!r}")
        if r["id"] not in stated and r.get("source") != TASK:
            links.append(f"rule {r['id']}: no document line states it")
        if bool(r.get("methods")) == bool(r.get("excluded")):
            links.append(f"rule {r['id']}: needs methods or excluded (exactly one)")
        for m, mats in (r.get("methods") or {}).items():
            listed.add((m, r["id"]))
            links += [f"method {m}: unknown material {x}" for x in mats if x not in rs["materials"]]
            if not mats:
                links.append(f"method {m}: no material")
    scored = {(method_key(it), it["rule"]) for it in rubric["items"]}
    links += [f"item {it['id']}: rule {it['rule']} lists no method {method_key(it)}" for it in rubric["items"] if (method_key(it), it["rule"]) not in listed]
    links += [f"method {m} ({r}): no rubric item of that rule" for m, r in sorted(listed - scored)]

    if not (report["moved"] or report["changed"] or report["new"]):
        synced = synced_rubric(rs, rubric, root)
        for key in ("sources", "appendix"):
            if synced[key] != rubric.get(key):
                report["stale"].append(f"rubric.yaml {key}")
        report["stale"] += [f"item {a['id']}: sources" for a, b in zip(synced["items"], rubric["items"], strict=True) if a["sources"] != b.get("sources")][:20]
        if root == PKG and not report["stale"]:
            from recipe.grpo.qwen3_5.scripts.render_rubric_md import render as render_rubric
            from recipe.grpo.qwen3_5.workflow_rubric import schema

            if (HERE / "ruleset.md").read_text() != render(rs, rubric):
                report["stale"].append("ruleset.md")
            if (HERE / "rubric.md").read_text() != render_rubric(schema.load(RUBRIC)):
                report["stale"].append("rubric.md")
    return {k: v for k, v in report.items() if v}


def sync(rs_path: Path = RULESET, rubric_path: Path = RUBRIC, root: Path = PKG) -> dict:
    """Renumber moved lines, then rewrite what follows from the set; returns the remaining ``check`` report."""
    rs = yaml.safe_load(rs_path.read_text())
    match, _, _ = _align(rs["lines"], doc_lines(rs["docs"], root))
    for i, ln in match.items():
        rs["lines"][i]["at"] = ln.at
    rs["lines"].sort(key=lambda e: (list(rs["docs"]).index(e["at"].split(":")[0]), int(e["at"].split(":")[1])))
    rs_path.write_text(_header(rs_path) + dump_ruleset(rs))
    rubric = synced_rubric(rs, yaml.safe_load(rubric_path.read_text()), root)
    rubric_path.write_text(dump(rubric))
    if rubric_path == RUBRIC:
        from recipe.grpo.qwen3_5.scripts.render_rubric_md import render as render_rubric
        from recipe.grpo.qwen3_5.workflow_rubric import schema

        (HERE / "rubric.md").write_text(render_rubric(schema.load(RUBRIC)))
        (HERE / "ruleset.md").write_text(render(rs, rubric))
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
