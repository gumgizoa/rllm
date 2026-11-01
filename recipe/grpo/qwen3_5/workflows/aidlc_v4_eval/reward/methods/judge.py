"""judge/*: the judge's questions and what it is shown for each (the questions and the asking are ``reward/judge.py``)."""

from __future__ import annotations

from . import question

_ARTIFACTS = ("JUDGE", "ISSUE", "COLLECT")
_SEEN = (*_ARTIFACTS, "SEEN")  # with the existing tests the run read
_RUNS = (*_ARTIFACTS, "SCRIPT", "TEST")  # stage 5: with the test and reproduction runs

for _rule in ("D3", "D6", "D10b"):
    question(_rule, _SEEN)
for _rule in ("E1a", "E1c", "E3b", "E6a", "E6b", "E7a", "E7b", "E8a", "E8b", "E9", "F2d", "F2e", "F2f", "F6", "F9a", "H8g"):
    question(_rule, _ARTIFACTS)
question("G8a", (*_ARTIFACTS, "PATCH"))
for _rule in ("B7", "H3a", "H3b", "H3c", "H8d", "H9b"):
    question(_rule, _RUNS)
