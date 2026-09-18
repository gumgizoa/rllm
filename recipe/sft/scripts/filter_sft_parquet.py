#!/usr/bin/env python3
"""Select a training mix out of contract-valid parquet, and split it into train/valid.

Conversion decides *shape*; this decides *selection*. It is dataset-agnostic: all
filters read ``metadata`` keys or measure the sample itself, so the same script
serves any converter that emits the contract.

    # the current Qwen3.5 SWE recipe
    python recipe/sft/scripts/filter_sft_parquet.py recipe/sft/data/swe/raw/data.parquet \\
        --require-reasoning --max-tokens 131072 \\
        --model Qwen/Qwen3.5-4B --chat-template-path recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja

Output goes to a directory named after the filters that produced it, so two mixes
can never be confused::

    recipe/sft/data/swe/solved__reasoning__max131072/
        train.parquet
        valid.parquet
        filter.json        # exact arguments + resulting counts

``--max-tokens`` renders and tokenizes every row, which is the slow part; the other
filters are cheap. Lengths come from ``swe_sft.dataset.utils.render.count_tokens``, the same
function the training dataset renders through, so a row that passes ``--max-tokens``
cannot exceed ``data.max_length`` at step 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from swe_sft.dataset.utils.parquet import BatchWriter, iter_rows
from swe_sft.dataset.utils.render import count_tokens
from swe_sft.dataset.utils.serde import parse_row

_SWE_SFT = Path(__file__).resolve().parents[1]


def git_commit() -> tuple[str | None, bool | None]:
    """The repo's HEAD and whether the tree is dirty, so a mix is traceable to code.

    ``dirty`` matters: these scripts may be uncommitted, in which case the sha alone
    does not identify what produced the output.
    """

    def run(*command: str) -> str | None:
        try:
            result = subprocess.run(["git", "-C", str(_SWE_SFT), *command], capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return None
        return result.stdout.strip()

    commit = run("rev-parse", "HEAD")
    if commit is None:
        return None, None
    status = run("status", "--porcelain")
    return commit, None if status is None else bool(status)


# --------------------------------------------------------------------------- #
# Token counting
# --------------------------------------------------------------------------- #

_WORKER: tuple[Any, str | None] = ()


def _init_worker(model_path: str, chat_template: str | None) -> None:
    global _WORKER
    from transformers import AutoTokenizer

    _WORKER = (AutoTokenizer.from_pretrained(model_path, trust_remote_code=True), chat_template)


def _count_tokens(row: dict[str, str | None]) -> int:
    tokenizer, chat_template = _WORKER
    return count_tokens(tokenizer, parse_row(row), chat_template)


def token_counts(source: Path, n_rows: int, args: argparse.Namespace) -> list[int]:
    """Token count per source row, in source order.

    A count depends on the row, the tokenizer and the chat template, so it is
    recomputed whenever any of them might have changed - i.e. every run.
    """
    template = Path(args.chat_template_path).read_text() if args.chat_template_path else None
    print(f"  tokenizing {n_rows} rows with {args.model} on {args.num_proc} process(es)")
    counts: list[int] = []
    with ProcessPoolExecutor(max_workers=max(1, args.num_proc), initializer=_init_worker, initargs=(args.model, template)) as pool:
        for batch in pq.ParquetFile(source).iter_batches(batch_size=args.batch_size):
            counts.extend(pool.map(_count_tokens, batch.to_pylist(), chunksize=1))
            print(f"    {len(counts)}/{n_rows}", flush=True)
    return counts


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def parse_conditions(pairs: list[str], label: str) -> dict[str, set[str]]:
    conditions: dict[str, set[str]] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--{label} expects key=value, got {pair!r}")
        key, _, value = pair.partition("=")
        conditions.setdefault(key, set()).update(v.strip() for v in value.split(","))
    return conditions


def is_validation(group: str, val_fraction: float, seed: int) -> bool:
    """Group-aware split: every row sharing ``group`` lands on the same side.

    Datasets commonly hold several rollouts of one task, so a row-level split leaks
    near-duplicates into validation.
    """
    digest = hashlib.sha1(f"{seed}:{group}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64) < val_fraction


def output_name(args: argparse.Namespace) -> str:
    """Directory name that states which filters produced the mix."""
    if args.name:
        return args.name
    parts = []
    for key, values in sorted(parse_conditions(args.metadata_eq, "metadata-eq").items()):
        parts.append(f"{key}-{'+'.join(sorted(values))}")
    if args.require_reasoning:
        parts.append("reasoning")
    if args.max_tokens > 0:
        parts.append(f"max{args.max_tokens}")
    return "__".join(parts) if parts else "unfiltered"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="Contract-valid parquet to filter (e.g. .../raw/data.parquet).")
    parser.add_argument(
        "--output-root",
        default=None,
        help="Where the named output directory is created (default: the source's parent's parent).",
    )
    parser.add_argument("--name", default=None, help="Output directory name (default: derived from the filters).")
    parser.add_argument(
        "--metadata-eq",
        action="append",
        default=[],
        metavar="KEY=VALUE[,VALUE]",
        help="Keep rows whose metadata KEY is one of VALUE. Repeatable; conditions AND together.",
    )
    parser.add_argument(
        "--require-reasoning",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=("Drop rows where any assistant turn has no 'reasoning'. Those rows train the model to emit an empty reasoning block, which is only what you want for a non-thinking mix."),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=0,
        help="Drop rows longer than this once rendered. Must match data.max_length under truncation=error.",
    )
    parser.add_argument("--val-fraction", type=float, default=0.01)
    parser.add_argument(
        "--group-key",
        default="instance_id",
        help="Metadata key that groups near-duplicate rows for the split. Empty string to split per row.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--model",
        default=None,
        help="Tokenizer for --max-tokens (e.g. Qwen/Qwen3.5-4B). Required when --max-tokens > 0.",
    )
    parser.add_argument(
        "--chat-template-path",
        default=None,
        help="Template for --max-tokens. Omit to render with the model's own chat template.",
    )
    parser.add_argument("--num-proc", type=int, default=min(32, os.cpu_count() or 8))
    parser.add_argument("--batch-size", type=int, default=512)
    return parser.parse_args()


def percentile(values: list[int], quantile: float) -> int:
    return values[min(len(values) - 1, int(quantile * len(values)))]


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.val_fraction < 1.0:
        raise SystemExit("--val-fraction must be in [0, 1)")
    if args.max_tokens > 0 and not args.model:
        raise SystemExit("--model is required when --max-tokens > 0 (it tokenizes every row to measure length)")

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"not found: {source}")
    n_rows = pq.ParquetFile(source).metadata.num_rows
    print(f"source: {source} ({n_rows} rows)")

    conditions = parse_conditions(args.metadata_eq, "metadata-eq")
    counts = token_counts(source, n_rows, args) if args.max_tokens > 0 else [None] * n_rows

    output_root = Path(args.output_root) if args.output_root else source.parent.parent
    output_dir = output_root / output_name(args)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"train": output_dir / "train.parquet", "valid": output_dir / "valid.parquet"}
    print(f"output: {output_dir}")

    dropped: Counter[str] = Counter()
    kept_tokens: list[int] = []
    writers = {split: BatchWriter(path, batch_size=args.batch_size) for split, path in paths.items()}

    try:
        for position, row in enumerate(iter_rows([str(source)], args.batch_size)):
            n_tokens = counts[position]

            sample = parse_row(row)
            metadata = sample.metadata or {}

            if any(str(metadata.get(key)) not in values for key, values in conditions.items()):
                dropped["metadata condition"] += 1
                continue
            if args.require_reasoning and any(m.reasoning is None for m in sample.messages if m.role == "assistant"):
                dropped["assistant turn without reasoning"] += 1
                continue
            if n_tokens is not None:
                if n_tokens < 0:
                    dropped["chat template error"] += 1
                    continue
                if n_tokens > args.max_tokens:
                    dropped["over --max-tokens"] += 1
                    continue
                kept_tokens.append(n_tokens)
                metadata = {**metadata, "n_tokens": n_tokens}

            group = str(metadata.get(args.group_key, position)) if args.group_key else str(position)
            split = "valid" if is_validation(group, args.val_fraction, args.seed) else "train"
            sample.metadata = metadata
            writers[split].add(sample.to_parquet_row())

            if (position + 1) % args.batch_size == 0:
                total_kept = sum(writer.n_written for writer in writers.values())
                print(f"  read={position + 1} kept~={total_kept} dropped={sum(dropped.values())}", flush=True)
    finally:
        for writer in writers.values():
            writer.close()

    kept = {split: writer.n_written for split, writer in writers.items()}
    commit, dirty = git_commit()
    summary: dict[str, Any] = {
        "commit": commit,
        "commit_dirty": dirty,
        "source": str(source),
        "filters": {
            "metadata_eq": args.metadata_eq,
            "require_reasoning": args.require_reasoning,
            "max_tokens": args.max_tokens,
        },
        "split": {"val_fraction": args.val_fraction, "group_key": args.group_key, "seed": args.seed},
        "tokenizer": {"model": args.model, "chat_template_path": args.chat_template_path} if args.max_tokens else None,
        "rows_in": n_rows,
        "rows_kept": kept,
        "rows_dropped": dict(dropped),
    }
    if kept_tokens:
        kept_tokens.sort()
        summary["tokens"] = {
            "mean": round(sum(kept_tokens) / len(kept_tokens)),
            "p50": percentile(kept_tokens, 0.5),
            "p95": percentile(kept_tokens, 0.95),
            "p99": percentile(kept_tokens, 0.99),
            "max": kept_tokens[-1],
        }
    (output_dir / "filter.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== summary ===")
    print(f"rows in     : {n_rows}")
    for split, path in paths.items():
        print(f"{split:<12}: {kept[split]} -> {path}")
    if dropped:
        print("dropped:")
        for reason, count in dropped.most_common():
            print(f"  {reason:<34} {count}")
    if "tokens" in summary:
        print("tokens: " + "  ".join(f"{k}={v}" for k, v in summary["tokens"].items()))
    print(f"recorded in {output_dir / 'filter.json'}")
    if not kept["valid"]:
        print("WARNING: the validation split is empty; raise --val-fraction", file=sys.stderr)


if __name__ == "__main__":
    main()
