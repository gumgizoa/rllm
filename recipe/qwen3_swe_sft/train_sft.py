#!/usr/bin/env python3
"""Launch Qwen3-8B SFT on rLLM's verl backend with the knobs the `rllm sft` CLI does not
expose: Ulysses sequence parallel, fused linear+log-prob head, FSDP offload, HF checkpoint
export, logger choice.

It builds an :class:`rllm.trainer.sft.spec.SFTSpec` whose ``overrides`` are deep-merged
into verl 0.8.0's ``sft_trainer_engine`` config by ``VerlSFTBackend.build_config``, then
runs ``AgentSFTTrainer(spec, backend="verl").train()`` (torchrun is spawned for you).

Key verl facts this launcher encodes (verl 0.8.0):
* ``engine.ulysses_sequence_parallel_size`` (sp) needs ``model.use_remove_padding`` (rLLM sets it).
  dp = gpus / sp, and ``data.train_batch_size`` must be divisible by dp.
* Dynamic batching packs samples into micro-batches of at most
  ``data.max_token_len_per_gpu * sp`` tokens; a sample longer than that is a hard assert
  (verl/utils/seqlen_balancing.py::rearrange_micro_batches). Optimizer steps use gradient
  accumulation over micro-batches, so the *global* batch size is not memory bound.
* ``model.use_fused_kernels`` computes log-probs from hidden states in chunks, so the
  [tokens x 151936] logits tensor is never materialized. Without it a 64k-token sample OOMs.
* ``checkpoint.save_contents`` including ``hf_model`` writes a HuggingFace-format model
  under ``<ckpt>/huggingface`` on every save (rank-0, offloaded to CPU).
* ``engine.strategy: fsdp`` (FSDP1) is the default and is what this launcher uses. FSDP2 +
  untied lm_head (Qwen3-8B) + fused kernels + gradient accumulation hits verl issue #7520.

Example (8x H200, one 64k sample per micro-batch, sp=2)::

    python recipe/qwen3_swe_sft/train_sft.py \\
        --train-file data/sft/train.jsonl --val-file data/sft/val.jsonl \\
        --model /vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B \\
        --gpus 8 --sp 2 --max-length 65536 --batch-size 16 --epochs 2 \\
        --experiment qwen3-8b-swe-sft-v1 --output /data/MMI/kyuminkim/rllm-work/sft_runs/v1

Add ``--dry-run`` to print the resolved plan (dp, micro-batch budget, steps, overrides)
without importing rllm/verl.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def count_rows_and_lengths(path: str | None) -> tuple[int, list[int]]:
    """Rows in a jsonl and their `n_tokens` (as written by prepare_sft_jsonl.py --tokenizer)."""
    if not path:
        return 0, []
    n, lens = 0, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            try:
                t = json.loads(line).get("n_tokens")
            except json.JSONDecodeError:
                t = None
            if isinstance(t, int):
                lens.append(t)
    return n, lens


def build_overrides(a: argparse.Namespace, max_token_len_per_gpu: int) -> dict:
    ov: dict = {
        "model": {
            "use_fused_kernels": not a.no_fused_kernels,
            "fused_kernel_options": {"impl_backend": a.fused_backend},
            "enable_gradient_checkpointing": True,
            "enable_activation_offload": a.activation_offload,
            "use_remove_padding": True,
            "trust_remote_code": False,
        },
        "engine": {
            "strategy": a.strategy,
            "ulysses_sequence_parallel_size": a.sp,
            "param_offload": a.param_offload,
            "optimizer_offload": a.optimizer_offload,
            "forward_prefetch": True,
            "use_torch_compile": True,
        },
        "data": {
            "use_dynamic_bsz": True,
            "micro_batch_size_per_gpu": 1,
            "max_token_len_per_gpu": max_token_len_per_gpu,
            "max_length": a.max_length,
            "truncation": "right",
            "num_workers": a.num_workers,
        },
        "optim": {
            "lr_warmup_steps_ratio": a.warmup_ratio,
            "weight_decay": a.weight_decay,
            "clip_grad": a.clip_grad,
            "betas": [0.9, 0.95],
        },
        "trainer": {
            "n_gpus_per_node": a.gpus,
            "nnodes": a.nnodes,
            "logger": ["console"] if a.logger == "console" else ["console", "wandb"],
            "max_ckpt_to_keep": a.max_ckpt_to_keep,
            "resume_mode": a.resume_mode,
        },
        "checkpoint": {
            "save_contents": ["model", "optimizer", "extra"] + (["hf_model"] if not a.no_save_hf else []),
        },
    }
    return ov


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # data / model
    ap.add_argument("--train-file", required=True)
    ap.add_argument("--val-file", default=None)
    ap.add_argument("--model", default="/vast-ib/MMI/home/kyuminkim/weights/Qwen3-8B")
    # topology
    ap.add_argument("--gpus", type=int, default=8, help="GPUs per node")
    ap.add_argument("--nnodes", type=int, default=1)
    ap.add_argument("--sp", type=int, default=1, help="Ulysses sequence-parallel size (divides --gpus)")
    # lengths / batching
    ap.add_argument("--max-length", type=int, default=65536, help="Right-truncate samples to this many tokens")
    ap.add_argument("--max-token-len-per-gpu", type=int, default=None, help="Micro-batch token budget per GPU (default: ceil(max-length / sp), i.e. one longest sample per SP group)")
    ap.add_argument("--batch-size", type=int, default=16, help="Global samples per optimizer step (divisible by gpus*nnodes/sp)")
    # optimization
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--lr-schedule", choices=["constant", "cosine"], default="cosine")
    ap.add_argument("--warmup-ratio", type=float, default=0.03)
    ap.add_argument("--weight-decay", type=float, default=0.0)
    ap.add_argument("--clip-grad", type=float, default=1.0)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lora-rank", type=int, default=0, help="0 = full fine-tuning")
    # memory knobs
    ap.add_argument("--strategy", choices=["fsdp", "fsdp2"], default="fsdp")
    ap.add_argument("--no-fused-kernels", action="store_true", help="Materialize full logits (needs far more memory)")
    ap.add_argument("--fused-backend", choices=["torch", "triton"], default="torch")
    ap.add_argument("--param-offload", action="store_true", help="Offload fp32 params/grads to CPU (host has ~2 TB RAM)")
    ap.add_argument("--optimizer-offload", action="store_true", help="Offload AdamW states to CPU")
    ap.add_argument("--activation-offload", action="store_true")
    ap.add_argument("--num-workers", type=int, default=4)
    # logging / checkpoints
    ap.add_argument("--project", default="qwen3-swe-sft")
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--output", required=True, help="Checkpoint directory")
    ap.add_argument("--save-freq", type=int, default=50, help="Save every N steps (the last step always saves)")
    ap.add_argument("--val-freq", type=int, default=25)
    ap.add_argument("--max-ckpt-to-keep", type=int, default=2)
    ap.add_argument("--no-save-hf", action="store_true", help="Do not write the HF-format model at each save")
    ap.add_argument("--logger", choices=["console", "wandb"], default="console")
    ap.add_argument("--resume-mode", choices=["auto", "disable", "resume_path"], default="auto")
    ap.add_argument("--dry-run", action="store_true", help="Print the plan and exit without importing rllm/verl")
    a = ap.parse_args()

    # ---- topology checks
    world = a.gpus * a.nnodes
    if a.gpus % a.sp != 0:
        sys.exit(f"--sp {a.sp} must divide --gpus {a.gpus}")
    dp = world // a.sp
    if a.batch_size % dp != 0:
        sys.exit(f"--batch-size {a.batch_size} must be divisible by dp = gpus*nnodes/sp = {dp}")
    if a.strategy == "fsdp2" and not a.no_fused_kernels:
        print("[warn] fsdp2 + untied lm_head + fused kernels + gradient accumulation can crash (verl #7520); prefer --strategy fsdp", file=sys.stderr)

    # ---- length checks (from prepare_sft_jsonl.py --tokenizer n_tokens)
    n_train, lens = count_rows_and_lengths(a.train_file)
    n_val, _ = count_rows_and_lengths(a.val_file)
    if n_train == 0:
        sys.exit(f"no rows in {a.train_file}")
    longest = max(lens) if lens else None
    over = sum(1 for t in lens if t > a.max_length)
    max_token_len_per_gpu = a.max_token_len_per_gpu or math.ceil(a.max_length / a.sp)
    budget = max_token_len_per_gpu * a.sp
    effective_longest = min(longest, a.max_length) if longest is not None else a.max_length
    if budget < effective_longest:
        sys.exit(f"micro-batch budget max_token_len_per_gpu*sp = {budget} < longest (truncated) sample {effective_longest}; raise --max-token-len-per-gpu or --sp")
    if n_train < a.batch_size:
        sys.exit(f"train rows ({n_train}) < --batch-size ({a.batch_size}); the sampler uses drop_last and would yield 0 steps")
    steps_per_epoch = n_train // a.batch_size
    total_steps = steps_per_epoch * a.epochs

    overrides = build_overrides(a, max_token_len_per_gpu)

    print("=== plan ===")
    print(f"model                : {a.model}")
    print(f"world / sp / dp      : {world} / {a.sp} / {dp}   strategy={a.strategy} fused_kernels={not a.no_fused_kernels} offload(param/optim)={a.param_offload}/{a.optimizer_offload}")
    print(f"train rows           : {n_train}  (val {n_val})" + (f"  longest={longest} tokens, {over} rows > max_length {a.max_length} (right-truncated)" if longest is not None else "  (no n_tokens field: cannot check lengths)"))
    print(f"micro-batch budget   : {max_token_len_per_gpu} tok/GPU x sp {a.sp} = {budget} tokens per SP group  (~{budget // max(1, effective_longest)} longest sample(s) per micro-batch)")
    print(f"global batch         : {a.batch_size} samples/step = {a.batch_size // dp} per dp rank -> grad accumulation over micro-batches")
    print(f"steps                : {steps_per_epoch}/epoch x {a.epochs} epochs = {total_steps}  (save every {a.save_freq}, val every {a.val_freq})")
    print(f"lr / schedule        : {a.lr} / {a.lr_schedule} (warmup {a.warmup_ratio}), wd {a.weight_decay}, clip {a.clip_grad}, lora_rank {a.lora_rank}")
    print(f"output               : {a.output}  (hf_model export: {not a.no_save_hf})")
    print("overrides            :", json.dumps(overrides, indent=2))
    if a.dry_run:
        return

    # ---- real launch
    from rllm.data import Dataset
    from rllm.trainer.agent_sft_trainer import AgentSFTTrainer
    from rllm.trainer.sft import SFTSpec

    train_ds = Dataset.load_data(a.train_file)
    val_ds = Dataset.load_data(a.val_file) if a.val_file else None

    spec = SFTSpec(
        model=a.model,
        train_dataset=train_ds,
        val_dataset=val_ds,
        lr=a.lr,
        lr_schedule=a.lr_schedule,
        epochs=a.epochs,
        batch_size=a.batch_size,
        max_length=a.max_length,
        tokenize_method="cumulative",
        lora_rank=a.lora_rank,
        save_freq=a.save_freq,
        val_freq=a.val_freq,
        project=a.project,
        experiment=a.experiment,
        output_dir=a.output,
        overrides=overrides,
    )
    Path(a.output).mkdir(parents=True, exist_ok=True)
    AgentSFTTrainer(spec, backend="verl").train()


if __name__ == "__main__":
    main()
