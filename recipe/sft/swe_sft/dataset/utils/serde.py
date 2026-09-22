"""Decode one parquet row into a validated :class:`swe_sft.schemas.SFTSample`.

There is exactly **one** decode path, used by converters, the filter and the
training dataset alike. An earlier version had a second, validation-free decoder
for the training path; measurement killed it. Full pydantic validation costs
1.3 ms per row against a ~600-800 ms ``__getitem__`` (which evaluates the chat
template ~2 + 2N times for N assistant turns), so skipping it bought 0.1% in
exchange for letting a malformed row reach the trainer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from swe_sft.schemas import COLUMNS, SFTSample


def loads(cell: Any, column: str) -> Any:
    """Decode one column. Rejects the ``""`` / ``"null"`` spellings of absent.

    Tolerating them would let "no tools" and "the JSON value null" mean the same
    thing, and a writer bug that emits ``""`` would look like valid data.
    """
    if cell is None:
        return None
    if not isinstance(cell, str):
        raise TypeError(f"column {column!r} must be a JSON string or null, got {type(cell).__name__}")
    if cell in ("", "null"):
        raise ValueError(f"column {column!r} is {cell!r}; use a real null instead")
    return json.loads(cell)


def parse_row(row: Mapping[str, Any]) -> SFTSample:
    """Strict decode of one contract row."""
    missing = [name for name in COLUMNS if name not in row]
    if missing:
        raise ValueError(f"missing column(s): {missing}")
    return SFTSample(**{name: loads(row[name], name) for name in COLUMNS})
