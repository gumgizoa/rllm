#!/usr/bin/env python3
"""Show what a dataset actually supervises, so a bad loss mask is visible rather than
inferred from a loss curve.

Loads ``--data`` through ``--dataset-name`` exactly as the trainer does, then prints the
decoded sample with supervised (``loss_mask == 1``) regions highlighted. Nothing here is
specific to a model or a dataset: everything it needs is a class that returns
``input_ids`` and ``loss_mask``.

    python recipe/sft/scripts/inspect_loss_mask.py \\
        --data recipe/sft/data/swe/solved__reasoning__max131072/valid.parquet \\
        --model Qwen/Qwen3.5-4B \\
        --dataset-path recipe/sft/qwen3_5/dataset.py \\
        --dataset-name Qwen3_5_SFTDataset \\
        --chat-template-path recipe/sft/qwen3_5/chat_templates/qwen3_5_train.jinja

With no ``--index`` it loops: type a row number to render it, ``mask`` / ``target`` to
switch mode, empty line or ``q`` or Ctrl-C to leave. The tokenizer and dataset load once,
which is the point - a long trajectory takes ~0.6 s to render, so relaunching per row
costs more in startup than in work.

    --index 0             one row, then exit
    --mode target         supervised text only
    --mode stats          numbers over --num-samples rows, no text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [path for path in (str(REPO_ROOT),) if path not in sys.path]

from swe_sft.dataset.utils.render import mask_spans  # noqa: E402
from verl.utils import hf_processor, hf_tokenizer  # noqa: E402
from verl.utils.import_utils import load_extern_object  # noqa: E402

# Inspection never truncates and never pads: an over-long row must still be viewable,
# and a screenful of pad tokens tells nobody anything.
INSPECT_CONFIG = {
    "max_length": 1 << 22,
    "truncation": "error",
    "pad_mode": "no_padding",
    "apply_chat_template_kwargs": {},
    "shuffle": False,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="Parquet file to inspect.")
    parser.add_argument("--model", required=True, help="HF model/tokenizer path.")
    parser.add_argument("--dataset-path", required=True, help="File holding the dataset class.")
    parser.add_argument("--dataset-name", required=True, help="Dataset class name in that file.")
    parser.add_argument(
        "--chat-template-path",
        default=None,
        help="Jinja template to render with. Omit to use the model's own template.",
    )
    parser.add_argument("--index", type=int, default=None, help="Row to inspect. Omit to be prompted for rows.")
    parser.add_argument(
        "--mode",
        default="mask",
        choices=["mask", "target", "stats"],
        help="mask: full text with highlights; target: supervised text only; stats: numbers only.",
    )
    parser.add_argument("--num-samples", type=int, default=20, help="Rows to cover in --mode stats.")
    return parser.parse_args()


def build_dataset(args: argparse.Namespace) -> Any:
    """The dataset under inspection, loaded the way ``data.custom_cls`` loads it."""
    config = OmegaConf.create({**INSPECT_CONFIG, "chat_template_path": args.chat_template_path})
    cls = load_extern_object(args.dataset_path, args.dataset_name)
    return cls(
        [args.data],
        hf_tokenizer(args.model, trust_remote_code=True),
        config,
        processor=hf_processor(args.model, trust_remote_code=True),
        max_samples=-1,
    )


def sample_of(dataset, index: int) -> tuple[list[int], list[int]]:
    item = dataset[index]
    return item["input_ids"].tolist(), [int(value) for value in item["loss_mask"].tolist()]


def summarize(input_ids: list[int], loss_mask: list[int]) -> dict[str, float]:
    supervised = sum(loss_mask)
    return {
        "tokens": len(input_ids),
        "supervised": supervised,
        "ratio": supervised / max(1, len(input_ids)),
        "spans": len(mask_spans(loss_mask)),
    }


def iter_mask_runs(input_ids: list[int], loss_mask: list[int]):
    """Yield (mask_value, token_ids) for each maximal run of equal mask values."""
    if not input_ids:
        return
    start, current = 0, int(loss_mask[0])
    for index, value in enumerate(loss_mask[1:], start=1):
        value = int(value)
        if value != current:
            yield current, input_ids[start:index]
            start, current = index, value
    yield current, input_ids[start:]


def render_segments(tokenizer, input_ids: list[int], loss_mask: list[int]) -> None:
    try:
        from rich.console import Console
        from rich.text import Text
    except ImportError:
        for mask, ids in iter_mask_runs(input_ids, loss_mask):
            print(f"\n--- {'LOSS=1' if mask else 'LOSS=0'}, tokens={len(ids)} ---")
            print(tokenizer.decode(ids))
        return

    text = Text()
    for mask, ids in iter_mask_runs(input_ids, loss_mask):
        text.append(tokenizer.decode(ids), style="bold cyan" if mask else "dim white")
    # soft_wrap keeps the terminal in charge of wrapping; rich's own wrapping reflows
    # source code and makes indentation unreadable.
    Console(soft_wrap=True).print(text)
    print("\nLegend: bold cyan = loss_mask 1 (supervised), dim = loss_mask 0 (context)")


def show_row(args: argparse.Namespace, dataset, index: int) -> None:
    input_ids, loss_mask = sample_of(dataset, index)
    stats = summarize(input_ids, loss_mask)
    print(f"row {index}: tokens={stats['tokens']} supervised={stats['supervised']} ({stats['ratio']:.1%}) spans={stats['spans']}")

    if args.mode == "target":
        supervised_ids = [token for token, mask in zip(input_ids, loss_mask, strict=True) if mask]
        print("\n================ supervised target only ================")
        print(dataset.tokenizer.decode(supervised_ids))
        return

    print("\n================ loss mask visualization ================")
    render_segments(dataset.tokenizer, input_ids, loss_mask)


def show_stats(args: argparse.Namespace, dataset) -> None:
    count = min(args.num_samples, len(dataset))
    rows = []
    for index in range(count):
        rows.append(summarize(*sample_of(dataset, index)))
        print(
            f"[{index:>4}] tokens={rows[-1]['tokens']:>7} supervised={rows[-1]['supervised']:>7} ({rows[-1]['ratio']:.1%}) spans={rows[-1]['spans']:>4}",
            flush=True,
        )
    total_tokens = sum(row["tokens"] for row in rows)
    total_supervised = sum(row["supervised"] for row in rows)
    print(f"\n{count} samples: {total_tokens} tokens, {total_supervised} supervised ({total_supervised / max(1, total_tokens):.1%}), {sum(row['spans'] for row in rows)} spans")
    if any(row["supervised"] == 0 for row in rows):
        print("WARNING: at least one sample has an all-zero loss mask", file=sys.stderr)


def prompt_loop(args: argparse.Namespace, dataset) -> None:
    print(f"\n{len(dataset)} rows (0..{len(dataset) - 1}), mode={args.mode}.")
    print("Enter a row index. 'mask' / 'target' switches mode. Empty line, 'q' or Ctrl-C quits.")
    while True:
        try:
            answer = input("\nindex> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("", "q", "quit", "exit"):
            return
        if answer in ("mask", "target"):
            args.mode = answer
            print(f"mode={args.mode}")
            continue
        try:
            index = int(answer)
        except ValueError:
            print(f"not a row index: {answer!r} (try a number, 'mask', 'target' or 'q')")
            continue
        if not 0 <= index < len(dataset):
            print(f"out of range: 0..{len(dataset) - 1}")
            continue
        try:
            show_row(args, dataset, index)
        except KeyboardInterrupt:
            # Ctrl-C while a 50k-token render scrolls should stop that render, not the
            # session.
            print("\ninterrupted")


def main() -> None:
    args = parse_args()
    for label, value in (("--data", args.data), ("--dataset-path", args.dataset_path)):
        if not Path(value).expanduser().exists():
            raise FileNotFoundError(f"{label}: {value}")
    args.data = str(Path(args.data).expanduser().resolve())

    dataset = build_dataset(args)

    if args.mode == "stats":
        show_stats(args, dataset)
    elif args.index is not None:
        if not 0 <= args.index < len(dataset):
            raise IndexError(f"--index {args.index} out of range for {len(dataset)} rows")
        show_row(args, dataset, args.index)
    else:
        prompt_loop(args, dataset)


if __name__ == "__main__":
    main()
