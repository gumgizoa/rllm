"""run/*: whole-run readings (the milestone-1 rubric's definitions, read in ``read.py``)."""

from __future__ import annotations

from .. import read as EV
from . import method


@method("run/entry", materials=("DOC",))
def entry(m):
    """core-workflow.md read before any other document: 1 by step 3, 1/3 later, 0 otherwise."""
    return EV.entry(m.run)


@method("run/ran_real_test", materials=("TEST",))
def ran_real_test(m):
    """Some step ran the repository's tests."""
    return float(EV.ran_real_test(m.run))


@method("run/fidelity", materials=("AP", "COLLECT", "PATH", "PATCH"))
def fidelity(m):
    """The share of the final diff artifact 04 discloses; not measured without a recorded patch."""
    return EV.fidelity(m.run) if m.patch is not None else None
