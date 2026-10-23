"""Re-anchoring a source quote after its document changed: the line range that now holds it.

Used where the study edits a document the rubric quotes (aidlc_v4_ifeval's copy of AI-DLC, the training
workflows' system prompts): the quote stays, its ``lines`` move with the text.
"""

from __future__ import annotations

import re


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
