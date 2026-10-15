"""Recall against the pilot statement files (``notes/*.statements.jsonl``).

The pilots were written by hand-checked extraction over the same documents; a generated rubric
(or G4's statements) "covers" a pilot statement when something cites the same file and an
overlapping line range. Pilot files name documents by host path (absolute, or relative to an
upstream checkout); a rendered document is matched through its upstream path and line map
(:func:`manifest.from_upstream`), so recall survives rendering that shifts lines.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .manifest import Entry, Manifest, from_upstream


def load_pilot(paths: list[str | Path]) -> list[dict]:
    rows = []
    for p in paths:
        with open(p) as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    d["_pilot"] = Path(p).name
                    rows.append(d)
    return rows


def match_entry(path: str, manifest: Manifest) -> tuple[Entry | None, bool]:
    """(entry, via_upstream) for a pilot ``file`` value; the longest suffix match wins."""
    p = path.replace("\\", "/")
    best: tuple[int, Entry | None, bool] = (0, None, False)
    for e in manifest.entries:
        names = [(e.abs_path, False), (e.path, False), (e.docs_rel, False), (e.container_path, False)]
        up = e.upstream.get("path")
        if up:
            names.append((str(up), True))
        for n, via in names:
            if not n:
                continue
            n = n.replace("\\", "/")
            if p == n or p.endswith("/" + n) or n.endswith("/" + p):
                score = min(len(n), len(p))
                if score > best[0]:
                    best = (score, e, via)
    return best[1], best[2]


def recall(pilot: list[dict], targets: list[tuple[str, int, int]], manifest: Manifest, show: int = 40) -> dict:
    """``targets``: (source id, first, last) cited by what is being measured."""
    by_doc: dict[str, list[tuple[int, int]]] = {}
    for doc, a, b in targets:
        by_doc.setdefault(doc, []).append((a, b))
    total = Counter()
    hit = Counter()
    unmatched = Counter()
    misses = []
    for d in pilot:
        e, via = match_entry(str(d.get("file", "")), manifest)
        if e is None:
            unmatched[str(d.get("file", ""))] += 1
            continue
        a, b = int(d.get("line_start", 0)), int(d.get("line_end", d.get("line_start", 0)))
        if via:
            mapped = [x for x in (from_upstream(e, n) for n in range(a, b + 1)) if x is not None]
            if not mapped:
                unmatched["(dropped by rendering)"] += 1
                continue
            a, b = min(mapped), max(mapped)
        keys = ("all", f"modality:{d.get('modality')}", f"kind:{d.get('kind')}", f"file:{e.path}")
        for k in keys:
            total[k] += 1
        covered = any(not (b < x or y < a) for x, y in by_doc.get(e.id, []))
        if covered:
            for k in keys:
                hit[k] += 1
        elif len(misses) < show:
            misses.append({"id": d.get("id"), "file": e.path, "lines": [a, b], "modality": d.get("modality"), "kind": d.get("kind"), "quote": str(d.get("quote", ""))[:160]})
    rate = {k: round(hit[k] / total[k], 3) for k in sorted(total)}
    return {
        "pilot_statements": len(pilot),
        "matched": total["all"],
        "covered": hit["all"],
        "recall": rate.get("all", 0.0),
        "by": rate,
        "unmatched_files": dict(unmatched.most_common(20)),
        "misses": misses,
    }
