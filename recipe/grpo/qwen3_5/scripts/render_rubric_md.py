"""Render a workflow's ``reward/rubric.yaml`` as ``reward/rubric.md``, the human review surface: one line per
item -- what the documents ask (the first source line, quoted), how it is checked, where it comes from.

    uv run --no-sync python recipe/grpo/qwen3_5/scripts/render_rubric_md.py <workflow> [--check]

``--check`` exits 1 when the committed ``rubric.md`` differs from what the rubric renders to (the tests run
it for the hand-written rubrics, whose ``rubric.md`` the generator does not write).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RECIPE.parents[2]))

from recipe.grpo.qwen3_5.workflow_rubric import schema  # noqa: E402

CATEGORY_NAMES = {"P": "procedure", "F": "artifact form", "E": "execution", "C": "consistency across stages", "R": "forbidden action", "Q": "content adequacy", "A": "report accuracy"}
QUOTE_CHARS = 180


def _where(rub: schema.Rubric, ref: schema.SourceRef) -> str:
    src = rub.source(ref.doc)
    name = src.container_path or src.path
    a, b = ref.lines
    return f"{name}:{a}" if a == b else f"{name}:{a}-{b}"


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= QUOTE_CHARS else text[: QUOTE_CHARS - 1].rstrip() + "…"


def _line(rub: schema.Rubric, it: schema.Item) -> str:
    params = json.dumps(it.check.params, ensure_ascii=False, sort_keys=True) if it.check.params else ""
    head = f"[{it.category}] **{it.rule}**" if it.category or it.rule else f"[{it.requirement}]"
    asked = it.note if it.check.kind.endswith(".judge") and it.note else _quote(it.sources[0].quote) if it.sources and it.sources[0].quote else ""
    where = "; ".join(_where(rub, s) for s in it.sources[:3]) + (f" (+{len(it.sources) - 3})" if len(it.sources) > 3 else "")
    tail = " _(diagnostic, not scored)_" if it.log_only else ""
    return f"- {head} {asked} — `{it.check.kind}` {params} (`{it.id}`) — {where}{tail}".replace("  ", " ")


def render(rub: schema.Rubric) -> str:
    out = [f"# {rub.workflow}: rubric (what the agent is asked to do)", ""]
    s = rub.scoring or {}
    gen = rub.generated or {}
    out.append(f"{gen.get('tool', 'hand-written')}. Rendered from rubric.yaml by `scripts/render_rubric_md.py`; edit the yaml, not this file.")
    kinds = Counter(i.check.kind for i in rub.items)
    out.append(f"{len(rub.items)} items | check kinds {dict(sorted(kinds.items()))}" + (f" | aggregate {s['aggregate']}" if s.get("aggregate") else ""))
    out.append("")
    numbered = {st.id: k for k, st in enumerate(rub.stages, start=1)} | {"global": 0}
    if s.get("aggregate") == "kind_matrix":
        cats = [c for c in CATEGORY_NAMES if any(i.category == c for i in rub.items)]
        done = (s.get("matrix") or {}).get("done_rule", "")
        out += [
            "Each item measures one atomic rule (`rule`) of one category in one stage.",
            "A rule's items average into it, a cell (category x stage) is the mean of its rules, a category the mean of its cells,"
            f" and the total (`{s.get('total') or 'score'}`) the mean of the categories.",
            f"A stage whose `{done}` item fails (its artifact was not collected) scores 0 in its cells, its forbidden-action cell left out.",
            "",
            "Items per cell (scored / diagnostic):",
            "",
            "| category | " + " | ".join(["0 (whole run)"] + [st.id if st.id == str(numbered[st.id]) else f"{numbered[st.id]} {st.id}" for st in rub.stages]) + " |",
            "|---" * (len(rub.stages) + 2) + "|",
        ]
        for c in cats:
            row = []
            for sid in ["global", *[st.id for st in rub.stages]]:
                its = [i for i in rub.items if i.category == c and i.stage == sid]
                scored, diag = sum(not i.log_only for i in its), sum(i.log_only for i in its)
                row.append("—" if not its else f"{scored}" + (f" / {diag}" if diag else ""))
            out.append(f"| {c} {CATEGORY_NAMES[c]} | " + " | ".join(row) + " |")
        out.append("")
    for sid in ["global", *[st.id for st in rub.stages]]:
        its = [i for i in rub.items if i.stage == sid]
        if not its:
            continue
        if sid == "global":
            out.append("## global — the whole run")
        else:
            st = rub.stage(sid)
            doc = rub.source(st.doc) if st.doc else None
            out.append(f"## {sid} — governed by {(doc.container_path or doc.path) if doc else '(no document)'}")
        out.append("")
        order = {c: k for k, c in enumerate(CATEGORY_NAMES)}
        out += [_line(rub, i) for i in sorted(its, key=lambda i: (order.get(i.category, 9), i.rule, i.id))]
        out.append("")
    rest = (rub.appendix or {}).get("rules_without_items")
    if rest:
        out += ["## Rules without items", ""]
        for why, rules in rest.items():
            out.append(f"- {why}: " + "; ".join(f"**{r}** {d}".strip() for r, d in rules.items()))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workflow")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    reward = RECIPE / "workflows" / args.workflow / "reward"
    text = render(schema.load(reward / "rubric.yaml"))
    target = reward / "rubric.md"
    if args.check:
        if not target.exists() or target.read_text() != text:
            print(f"{target} is stale: run {Path(__file__).name} {args.workflow}", file=sys.stderr)
            return 1
        return 0
    target.write_text(text)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
