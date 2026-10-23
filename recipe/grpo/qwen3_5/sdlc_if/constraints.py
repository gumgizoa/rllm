"""Constraints of the SDLC instruction-following study: what each workflow's documents ask, apart from how
the rubric scores it.

    python -m recipe.grpo.qwen3_5.sdlc_if.constraints [WORKFLOW ...]    # check; no argument = all four

``templates.yaml`` (this directory) is the catalogue: template id -> skill, judging logic, typical kinds,
default evaluation layer. ``workflows/<wf>/constraints.yaml`` holds one constraint per rubric item, keyed
by the item id::

    id           the rubric item id
    template     a catalogue id (T-*, NEW-*), or null for a rule that is no checkable constraint
    status       implemented | unimplemented (the item's kind is ``unimplemented``)
    requirement  must | should, as the rubric weighs it in training reward
    rule         the document's rule in one line, with DOC:line references
    source       {doc, lines, quote}: one of the item's sources
    fidelity     implemented: faithful | narrower | broader | different (the check against the rule),
                 with fidelity_note unless faithful
    class        unimplemented: duplicate | candidate | domain_specific | display | vague (class_note)
    eval         evaluation workflow, implemented items: {layer: L1 | L1C | L2M | L2F, requirement,
                 when?, layer_reason?} -- layer_reason is required where the layer differs from the
                 template's default

The rubric is the implementation (``reward/rubric.yaml``); :func:`check` keeps the two in step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WORKFLOWS = HERE.parent / "workflows"
DEFAULT = ("agentos_v2", "openspec_ff", "speckit_bug", "aidlc_v4_ifeval")
LAYERS = ("L1", "L1C", "L2M", "L2F")
FIDELITY = ("faithful", "narrower", "broader", "different")
CLASSES = ("duplicate", "candidate", "domain_specific", "display", "vague")


def templates() -> dict[str, dict]:
    return yaml.safe_load((HERE / "templates.yaml").read_text())["templates"]


def load(workflow: str) -> dict:
    return yaml.safe_load((WORKFLOWS / workflow / "constraints.yaml").read_text())


def check(workflow: str) -> list[str]:
    """Problems in ``workflow``'s constraints.yaml, against its rubric and the catalogue."""
    cat = templates()
    doc = load(workflow)
    rubric = yaml.safe_load((WORKFLOWS / workflow / doc["rubric"]).read_text())
    items = {it["id"]: it for it in rubric["items"]}
    out = []
    seen = set()
    for c in doc["constraints"]:
        cid = c["id"]
        where = f"{workflow}: {cid}"
        if cid in seen:
            out.append(f"{where}: duplicate")
        seen.add(cid)
        it = items.get(cid)
        if it is None:
            out.append(f"{where}: no rubric item")
            continue
        impl = it["check"]["kind"] != "unimplemented"
        t = c.get("template")
        if t is not None and t not in cat:
            out.append(f"{where}: template {t!r} not in the catalogue")
        if t is None and impl:
            out.append(f"{where}: implemented without a template")
        if c.get("status") != ("implemented" if impl else "unimplemented"):
            out.append(f"{where}: status {c.get('status')!r}, kind {it['check']['kind']!r}")
        if c.get("requirement") != it["requirement"]:
            out.append(f"{where}: requirement {c.get('requirement')!r}, rubric {it['requirement']!r}")
        src = c.get("source")
        if src and not any(s.get("doc") == src.get("doc") and list(s.get("lines") or []) == list(src.get("lines") or []) and s.get("quote") == src.get("quote") for s in it.get("sources") or []):
            out.append(f"{where}: source is none of the item's sources")
        if impl:
            if c.get("fidelity") not in FIDELITY:
                out.append(f"{where}: fidelity {c.get('fidelity')!r}")
        elif c.get("class") not in CLASSES:
            out.append(f"{where}: class {c.get('class')!r}")
        if doc.get("role") == "eval" and impl:
            ev = c.get("eval") or {}
            if ev.get("layer") not in LAYERS or ev.get("requirement") not in ("must", "should"):
                out.append(f"{where}: eval {ev!r}")
            default = ((cat.get(t) or {}).get("eval") or {}).get("layer")
            if ev.get("layer") != default and not ev.get("layer_reason"):
                out.append(f"{where}: layer {ev.get('layer')} differs from {t}'s {default} without layer_reason")
    out += [f"{workflow}: {i}: rubric item without a constraint" for i in items if i not in seen]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workflows", nargs="*", default=list(DEFAULT))
    a = ap.parse_args(argv)
    problems = [p for wf in a.workflows for p in check(wf)]
    for p in problems:
        print(p, file=sys.stderr)
    print(f"{len(problems)} problem(s) in {', '.join(a.workflows)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
