"""Parquet plumbing: find the inputs, stream rows in, stream rows out, check the result.

Converters and the filter all move millions of messages through a few hundred
megabytes of parquet, so everything here streams. Nothing holds a whole file.
"""

from __future__ import annotations

import glob
import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from swe_sft.dataset.utils.serde import parse_row
from swe_sft.schemas import COLUMNS, PARQUET_SCHEMA


def resolve_input_files(
    *,
    input_dir: str | None = None,
    repo_id: str | None = None,
    config: str | None = None,
    split: str | None = None,
    allow_download: bool = False,
) -> list[str]:
    """The ``*.parquet`` shards to read, from a local directory or the HF cache.

    ``allow_download=False`` (the default) resolves against the local cache only, so
    a converter run can never silently start a multi-gigabyte download.
    """
    if input_dir:
        files = sorted(glob.glob(os.path.join(input_dir, "*.parquet")))
        if not files:
            raise SystemExit(f"no parquet files under {input_dir}")
        return files

    if not repo_id:
        raise SystemExit("pass either input_dir or repo_id")

    from huggingface_hub import snapshot_download

    relative = "/".join(part for part in (config, split) if part)
    pattern = f"{relative}/*.parquet" if relative else "*.parquet"
    snapshot = snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        allow_patterns=[pattern],
        local_files_only=not allow_download,
    )
    files = sorted(glob.glob(os.path.join(snapshot, relative, "*.parquet")))
    if not files:
        raise SystemExit(f"no parquet files matching {pattern!r} under {snapshot}")
    return files


def iter_rows(files: list[str], batch_size: int = 512) -> Iterator[dict[str, Any]]:
    """Every row of every shard, in order, without loading a whole shard."""
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
            yield from batch.to_pylist()


class BatchWriter:
    """Buffered :class:`pyarrow.parquet.ParquetWriter`.

    Use as a context manager; :meth:`add` flushes on its own every ``batch_size``
    rows. Writing row by row would produce one row group per row, which makes the
    file both larger and slower to read back.
    """

    def __init__(
        self,
        path: Path | str,
        schema: pa.Schema = PARQUET_SCHEMA,
        batch_size: int = 512,
        compression: str = "zstd",
    ) -> None:
        self.path = Path(path)
        self.schema = schema
        self.batch_size = batch_size
        self.n_written = 0
        self._buffer: list[dict[str, str | None]] = []
        self._writer = pq.ParquetWriter(self.path, schema, compression=compression)

    def add(self, row: dict[str, str | None]) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        self._writer.write_table(pa.Table.from_pylist(self._buffer, schema=self.schema))
        self.n_written += len(self._buffer)
        self._buffer.clear()

    def close(self) -> None:
        try:
            self.flush()
        finally:
            self._writer.close()

    def __enter__(self) -> BatchWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def check_contract(path: Path | str, max_errors: int = 10, batch_size: int = 512) -> tuple[list[str], Counter]:
    """Read a written parquet back and validate it. Returns ``(problems, stats)``.

    Worth running even when the writer validated every sample in memory: this is
    the only check that sees what actually landed on disk, so it catches column
    drift and the ``""``-instead-of-null class of writer bug.
    """
    problems: list[str] = []
    stats: Counter = Counter()

    schema = pq.ParquetFile(path).schema_arrow
    if list(schema.names) != list(COLUMNS):
        problems.append(f"columns are {list(schema.names)}, expected {list(COLUMNS)}")
        return problems, stats
    for name in COLUMNS:
        if schema.field(name).type != PARQUET_SCHEMA.field(name).type:
            problems.append(f"column {name!r} is {schema.field(name).type}, expected string")
    if problems:
        return problems, stats

    for index, row in enumerate(iter_rows([str(path)], batch_size)):
        stats["rows"] += 1
        try:
            sample = parse_row(row)
        except Exception as exc:
            stats["invalid"] += 1
            if len(problems) < max_errors:
                problems.append(f"row {index}: {str(exc).splitlines()[0]}")
            continue
        stats["assistant_turns"] += sum(1 for m in sample.messages if m.role == "assistant")
        stats["turns_without_reasoning"] += sum(1 for m in sample.messages if m.role == "assistant" and m.reasoning is None)
        stats["rows_with_tools"] += bool(sample.tools)
        stats["rows_non_thinking"] += (sample.apply_chat_template_kwargs or {}).get("enable_thinking") is False

    if stats["invalid"] > len(problems):
        problems.append(f"... {stats['invalid'] - len(problems)} more invalid row(s)")
    return problems, stats
