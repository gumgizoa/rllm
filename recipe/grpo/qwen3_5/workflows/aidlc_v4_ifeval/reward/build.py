"""Build ``rubric.yaml`` and ``layers.yaml`` for the AI-DLC instruction-following evaluation.

    python -m recipe.grpo.qwen3_5.workflows.aidlc_v4_ifeval.reward.build [--check]

``rubric.yaml`` is aidlc_v4_gen's generated rubric moved onto this workflow's copy of the documents:

* every source points at the copy (path and sha256), and every quote is re-anchored to the line
  range it now occupies; a quote of a line the copy rewrote takes its new text from ``QUOTES``, and the
  build fails on any other quote it cannot find;
* the documented conflicts are re-anchored the same way, and the ones the copy's edits remove say so
  (``RESOLVED``); free-text line references in ``modality_evidence`` and ``note`` keep aidlc_v4's
  numbering;
* ``PATCHES`` fixes judging defects found in the item audit (study doc ``06_item_template_audit.md``
  section 5.1): repeated labels read in full (``all``), a no-test-target regex that matched anything;
* one ``log_only`` item for the no-re-read rule (``aidlc_ifeval.no_reread``) is added, so
  ``aidlc_ifeval/compliance`` is aidlc_v4_gen's scoring of the copy and the new item only feeds a layer.

``layers.yaml`` comes from ``../constraints.yaml`` (layer, evaluation requirement and gate per item,
reasoned against the training workflows in the study docs) for every implemented item;
``workflow_rubric/layers.py`` turns it into the ``aidlc_ifeval/layer*/<L>`` signals.
``--check`` fails when the committed files differ from a fresh build.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import re
import sys
from pathlib import Path

import yaml

from recipe.grpo.qwen3_5.workflow_rubric.layers import rubric_sha256

HERE = Path(__file__).resolve().parent
WF = HERE.parent
GEN = WF.parent / "aidlc_v4_gen" / "reward" / "rubric.yaml"
RUBRIC = HERE / "rubric.yaml"
LAYERS = HERE / "layers.yaml"
CONSTRAINTS = WF / "constraints.yaml"

NO_REREAD = "aidlc_v4_ifeval.global.run.no_reread"
G = "aidlc_v4_gen."

# Repeated labels: ``M.field_value`` answers a label's first line only, and AI-DLC repeats these labels
# once per entry (``- Path:`` per covering test, ``- Target:`` per plan step, ``- Modified:``/``- Created:``
# per file), so the first entry stood for all of them.
ALL_ENTRIES = [
    "reverse_engineering.a1.field_type.path",
    "reverse_engineering.a1.cross_ref",
    "code_generation_planning.a3.field_type.target",
    "code_generation_planning.a3.cross_ref.3",
    "code_generation_generation.a3.cross_ref",
    "code_generation_generation.a4.cross_ref",
    "code_generation_generation.a4.cross_ref.2",
    "code_generation_generation.a4.cross_ref.3",
    "code_generation_generation.a4.cross_ref.4",
    "code_generation_generation.a4.cross_ref.5",
]
# ``[\s*`]*`` could backtrack to zero characters, so the lookahead ran at the space before the path and
# every Target passed; the group-and-backreference makes the prefix atomic (Python 3.10 has no ``*+``), and
# the lookahead covers the Python test-file shapes of ``facts.is_test_path`` (test_*.py, *_test.py,
# conftest.py, tests/ and __tests__/ directories).
NO_TEST_TARGET = (
    r"^\s*[-*+]\s+\**Target\**:(?=([\s*`]*))\1(?![^\s`*]*?(?:(?<![^/\s`*:])(?:tests|__tests__)/"
    r"|(?<![^/\s`*:])test_[^/\s`*]*\.py\b|_tests?\.py\b|(?<![^/\s`*:])conftest\.py\b))"
)

# Quotes of lines the copy rewrote: (item id, old quote) -> new quote.
QUOTES: dict[tuple[str, str], str] = {
    (G + "build_and_test.a5.field_filled.outstanding", "Unresolved work goes under Outstanding Failures in the Stage 5 artifact, and nowhere else."):
        "Unresolved work goes under Outstanding Failures in the Stage 5 artifact, not in an earlier stage's artifact.",
    (G + "build_and_test.a5.field_filled.outstanding", "Outstanding Failures is the only place unresolved work is recorded. When Step 5 stopped short, it names what remains and why; it is never left as `none` to make the run look clean."):
        "Outstanding Failures lists all unresolved work, including any unmet requirement or regression left unresolved. When Step 5 stopped short, it names what remains and why; it is never left as `none` to make the run look clean.",
    **{
        (G + i, "Confirm the files in the change are exactly those Code Generation listed as modified or created"):
            "Confirm the files in the change are exactly those Code Generation listed as modified or created, plus any file a Step 5 fix changed"
        for i in ("build_and_test.a5.field_filled.files_in_the_change", "build_and_test.a5.cross_ref")
    },
}
# Documented conflicts the copy's edits remove: description prefix -> what the copy changed.
RESOLVED = {
    "Whether the reproduction script is listed under A4 Created": "the copy's CG:54 records the script under Reproduction Script, not Changed Files",
    "Stage-5 fixes may touch files Stage 4 did not list": "the copy's BT Step 6 confirms the change against A4's list plus the files a Step 5 fix changed",
    "Step 7 (confirm the final change) comes after Step 6 writes": "the copy confirms the final change (Step 6) before the single write (Step 7)",
    "'Unresolved work goes under Outstanding Failures ... and nowhere else'": "the copy's CW:40 and BT:106 keep Outstanding Failures as the full list, next to Unmet requirements and Regressions",
    "The generic system prompt asks to keep AGENTS.md in the repository": "the copy's system prompt drops <ENVIRONMENT_SETUP> (install); the AGENTS.md instruction remains",
    "The generic system prompt asks to confirm a new plan with the user": "the copy's system prompt drops 'confirm with the user'; 'combine commands' remains",
    "The generic system prompt asks to 'first thoroughly understand the codebase": "the copy's system prompt drops the instruction",
}


def _local(path: str) -> str:
    """aidlc_v4_gen's path of an aidlc_v4 file -> the copy's path in this workflow."""
    return path.removeprefix("../aidlc_v4/")


def _norm(s: str) -> str:
    return " ".join(s.replace("**", "").replace("`", "").replace("—", "-").replace("–", "-").split())


def _frags(quote: str) -> list[str]:
    return [f for f in (_norm(x) for x in re.split(r"\.\.\.|…", quote)) if len(f) >= 8]


def anchor(lines: list[str], quote: str, hint: tuple[int, int]) -> tuple[int, int] | None:
    """The line range holding every fragment of ``quote`` (split on ellipses): the hint when it still
    does, else the hint moved by the nearest offset that does (text shifted by an edit above it), else
    the shortest range starting nearest the hint. None when a fragment is gone."""
    frags = _frags(quote)
    if not frags:
        return hint
    a, b = hint

    def holds(i: int, j: int) -> bool:
        return 1 <= i <= j <= len(lines) and all(f in _norm(" ".join(lines[i - 1 : j])) for f in frags)

    for d in sorted(range(-len(lines), len(lines) + 1), key=abs):
        if holds(a + d, b + d):
            return (a + d, b + d)
    best = None
    for i in sorted(range(len(lines)), key=lambda i: abs(i + 1 - a)):
        for j in range(i + 1, min(i + 40, len(lines)) + 1):
            if all(f in _norm(" ".join(lines[i:j])) for f in frags):
                if best is None or (j - i, abs(i + 1 - a)) < (best[1] - best[0] + 1, abs(best[0] - a)):
                    best = (i + 1, j)
                break
        if best is not None and abs(i + 1 - a) > abs(best[0] - a) + 40:
            break
    return best


def _patch(it: dict) -> None:
    iid = it["id"].removeprefix(G)
    p = it["check"].get("params") or {}
    if iid in ALL_ENTRIES:
        if it["check"]["kind"] == "field_type":
            p["all"] = True
        for side in ("left", "right"):
            sel = p.get(side)
            if isinstance(sel, dict) and "field_list" in sel:
                sel["field_list"]["all"] = True
    if iid == "code_generation_planning.a3.item_format.no_test_target":
        p["pattern"] = NO_TEST_TARGET


def no_reread_item(texts: dict[str, list[str]]) -> dict:
    quote = "**Do not re-read an artifact you can still see.** ... **Read an artifact only to recover**, when an earlier stage's content is no longer visible because output was truncated or history was compacted"
    lines = anchor(texts["CW"], quote, (42, 43))
    return {
        "id": NO_REREAD,
        "scope": "specific",
        "class": "evidence",
        "stage": "global",
        "target": {"type": "action", "ref": "run", "state": "final"},
        "check": {"kind": "aidlc_ifeval.no_reread", "params": {}},
        "requirement": "must",
        "modality_evidence": "CW 'Do not re-read an artifact you can still see' (bold rule in Artifact Rules)",
        "none_allowed": "-",
        "applies_when": None,
        "weight": 1.0,
        "gate": None,
        "availability": ["trace"],
        "sources": [{"doc": "CW", "lines": list(lines), "quote": quote}],
        "impl_refs": [],
        "derived_by": "manual",
        "template": "",
        "log_only": True,
        "note": "SDLC IF study (T-RD6): log_only so that compliance stays aidlc_v4_gen's scoring; feeds layer L1C",
    }


def build_rubric() -> dict:
    gen = yaml.safe_load(GEN.read_text())
    rubric = copy.deepcopy(gen)
    rubric["workflow"] = "aidlc_v4_ifeval"
    texts, paths = {}, {}
    for s in rubric["sources"]:
        s["path"] = _local(s["path"])
        f = WF / s["path"]
        s["sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
        texts[s["id"]] = f.read_text().splitlines()
        paths[s["path"]] = s["id"]
        if s["id"] == "SP" and "sections" in s:
            s["sections"] = {k: v for k, v in s["sections"].items() if f"<{k}>" in f.read_text()}
    missing = []
    for it in rubric["items"]:
        _patch(it)
        kept = []
        for src in it.get("sources") or []:
            q = QUOTES.get((it["id"], src.get("quote", "")), src.get("quote", ""))
            got = anchor(texts[src["doc"]], q, tuple(src["lines"]))
            if got is None:
                missing.append(f"{it['id']}: {src['doc']} {src['lines']} {q[:70]!r}")
                continue
            kept.append({**src, "lines": list(got), "quote": q})
        it["sources"] = kept
    if missing:
        raise SystemExit("quotes not found in the copy:\n  " + "\n  ".join(missing))
    for cf in rubric.get("conflicts") or []:
        note = next((v for k, v in RESOLVED.items() if cf.get("description", "").startswith(k)), None)
        if note:
            cf["resolved_in_copy"] = note
        for src in cf.get("sources") or []:
            src["path"] = _local(src["path"])
            sid = paths.get(src["path"])
            got = anchor(texts[sid], src.get("quote", ""), tuple(src["lines"])) if sid and src.get("lines") else None
            if got is not None:
                src["lines"] = list(got)
            elif sid:
                src["removed_in_copy"] = True
    rubric["items"].append(no_reread_item(texts))
    return rubric


def build_layers(rubric: dict) -> dict:
    cons = {c["id"]: c for c in yaml.safe_load(CONSTRAINTS.read_text())["constraints"]}
    items, problems = {}, []
    for it in rubric["items"]:
        c = cons.get(it["id"])
        if c is None:
            problems.append(f"{it['id']}: no constraint")
            continue
        if it["check"]["kind"] == "unimplemented":
            continue
        ev = c.get("eval") or {}
        if "layer" not in ev:
            problems.append(f"{it['id']}: no eval layer")
            continue
        spec = {"layer": ev["layer"], "requirement": ev.get("requirement", it["requirement"]), "template": c["template"]}
        if ev.get("when"):
            spec["when"] = ev["when"]
        items[it["id"]] = spec
    extra = sorted(set(cons) - {it["id"] for it in rubric["items"]})
    problems += [f"{i}: constraint without a rubric item" for i in extra]
    if problems:
        raise SystemExit("constraints.yaml does not match the rubric:\n  " + "\n  ".join(problems))
    return items


def _dump(obj) -> str:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=1 << 16)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed files differ from a fresh build")
    ap.add_argument("--rubric-only", action="store_true", help="write rubric.yaml only (to seed constraints.yaml)")
    a = ap.parse_args(argv)
    rubric = build_rubric()
    rubric_text = _dump(rubric)
    if a.rubric_only:
        RUBRIC.write_text(rubric_text)
        print(f"wrote {RUBRIC.name} ({len(rubric['items'])} items)")
        return 0
    items = build_layers(rubric)
    header = "# Generated by reward/build.py from ../constraints.yaml -- do not edit; see its docstring.\n"
    sha = hashlib.sha256(rubric_text.encode()).hexdigest()
    layers_text = header + _dump({"rubric_sha256": sha, "source": "constraints.yaml", "items": items})
    if a.check:
        stale = [p.name for p, want in ((RUBRIC, rubric_text), (LAYERS, layers_text)) if not p.is_file() or p.read_text() != want]
        if stale:
            print(f"stale: {stale}; run the build", file=sys.stderr)
            return 1
        return 0
    RUBRIC.write_text(rubric_text)
    assert rubric_sha256(RUBRIC) == sha
    LAYERS.write_text(layers_text)
    print(f"wrote {RUBRIC.name} ({len(rubric['items'])} items) and {LAYERS.name} ({len(items)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
