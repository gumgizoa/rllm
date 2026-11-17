"""proc/*: a stage's procedure, from the first reads of the rule documents and the first artifact writes.

``w`` here is ``Measures.w_collected`` (an artifact counts when its file was collected); a document first read by one
command together with another (``Measures.multi_read``) counts as not read alone, so A2 / A3b / B3b see it unread.
"""

from __future__ import annotations

from . import STAGES, method


def _read(m, k: int) -> int | None:
    """Stage ``k``'s document read on its own: its first read, unless shared with another document's."""
    return m.read_step.get(f"0{k}") if f"0{k}" not in m.multi_read else None


@method("proc/A3a", materials=("DOC",), stages=(0,))
def a3a(m, st):
    """The stage documents are read one at a time: the share not read together with another."""
    if any(f"0{k}" in m.read_step for k in STAGES):
        return 1 - len(m.multi_read) / 5
    return None


@method("proc/C1a", materials=("DOC", "WRITE"), stages=STAGES)
def c1a(m, k):
    """The stage was carried out, its document read (however) before its artifact."""
    w, r = m.w_collected.get(k), m.read_step.get(f"0{k}")
    return 1.0 if r is not None and w is not None and r < w else 0.0


@method("proc/C1b", materials=("WRITE",), stages=(2, 3, 4, 5))
def c1b(m, k):
    """In order: the artifact written after the previous stage's (both written: a stage left out is C1a's)."""
    w, wprev = m.w_collected.get(k), m.w_collected.get(k - 1)
    if w is None or wprev is None:
        return None
    return 1.0 if wprev < w else 0.0


@method("proc/A2", materials=("DOC", "WRITE"), stages=STAGES)
def a2(m, k):
    """The stage was done: its document was its first step (read alone, after the previous artifact, before its own)."""
    w, r, wprev = m.w_collected.get(k), _read(m, k), m.w_collected.get(k - 1)
    if w is None:
        return None
    return 1.0 if r is not None and r < w and (wprev is None or r > wprev) else 0.0


@method("proc/A3b", materials=("DOC", "WRITE"), stages=(2, 3, 4, 5))
def a3b(m, k):
    """No reading ahead: the stage's document read after the previous stage's artifact."""
    r, wprev = _read(m, k), m.w_collected.get(k - 1)
    if r is None:
        return None
    return 1.0 if wprev is not None and r > wprev else 0.0


@method("proc/B3b", materials=("DOC", "WRITE"), stages=(1, 2, 3, 4))
def b3b(m, k):
    """The artifact closes the stage: written before the next stage's document is read."""
    w, rnext = m.w_collected.get(k), _read(m, k + 1)
    if w is None or rnext is None:
        return None
    return 1.0 if w < rnext else 0.0
