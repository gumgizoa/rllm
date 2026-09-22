#!/usr/bin/env python3
"""Per-GPU memory estimate for Qwen3-8B full fine-tuning on verl's FSDP SFT engine, and the
micro-batch / batch-size headroom that follows from it.

Model of the peak (per GPU):

    states      = params * bytes_per_param / world           FSDP-sharded fp32 master params (4),
                                                              fp32 grads (4), AdamW m+v (8) = 16 B
                                                              (-8 with --optimizer-offload, -8 with --param-offload)
    activations = act_mb_per_token * (micro_tokens / sp)     gradient checkpointing + flash-attn +
                                                              fused log-prob head (no logits tensor)
    working     = 2 unsharded decoder layers (bf16) + embed/lm_head (bf16) + comm buffers + fused-CE chunks
    reserve     = CUDA context + allocator fragmentation (fraction of card)

`act_mb_per_token` defaults to 0.55 MB: Qwen3.5-4B measured 0.25-0.35 GB per 1K tokens under
the same settings (recipe/qwen3_5_swe_grpo/README.md); Qwen3-8B has 1.6x the hidden size and
36 vs 32 layers, i.e. ~1.8x. Calibrate with recipe/qwen3_swe_sft/mem_scaling.py on the real
node and pass --act-mb-per-token.

Batch size is *not* what the memory decides: verl packs samples into micro-batches of at most
max_token_len_per_gpu*sp tokens and accumulates gradients across micro-batches, so the global
batch (samples per optimizer step) is free. What memory decides is the token budget per
micro-batch, i.e. how many samples of a given length travel together in one forward/backward.

    python recipe/qwen3_swe_sft/estimate_memory.py --gpus 8 --gpu-mem-gb 141 --seq-len 65536
    python recipe/qwen3_swe_sft/estimate_memory.py --gpus 4 --gpu-mem-gb 96  --seq-len 65536 --sp 1 2 4
"""

from __future__ import annotations

import argparse

GB = 1024**3
MB = 1024**2


def estimate(a, sp: int, micro_tokens: int) -> dict:
    world = a.gpus * a.nnodes
    bytes_per_param = 16.0
    if a.optimizer_offload:
        bytes_per_param -= 8
    if a.param_offload:
        bytes_per_param -= 8
    if a.lora:
        bytes_per_param = 2.0  # frozen bf16 base; adapter states negligible
    states = a.params_b * 1e9 * bytes_per_param / world

    layer_params = (a.params_b * 1e9 - 2 * a.vocab * a.hidden) / a.layers
    working = 2 * layer_params * 2 + 2 * a.vocab * a.hidden * 2 + a.comm_gb * GB + a.fused_chunk_gb * GB
    activations = a.act_mb_per_token * MB * micro_tokens / sp
    reserve = a.reserve_frac * a.gpu_mem_gb * GB + a.context_gb * GB
    total = states + working + activations + reserve
    return {"states": states, "working": working, "activations": activations, "reserve": reserve, "total": total, "free": a.gpu_mem_gb * GB - total}


def max_micro_tokens(a, sp: int) -> int:
    """Largest micro-batch (tokens per SP group) that fits."""
    base = estimate(a, sp, 0)
    room = a.gpu_mem_gb * GB - base["total"]
    if room <= 0:
        return 0
    return int(room / (a.act_mb_per_token * MB) * sp)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gpus", type=int, default=8)
    ap.add_argument("--nnodes", type=int, default=1)
    ap.add_argument("--gpu-mem-gb", type=float, default=141.0, help="H200=141, H100 NVL=96, H100 SXM=80")
    ap.add_argument("--sp", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--seq-len", type=int, default=65536, help="Longest sample (tokens)")
    ap.add_argument("--params-b", type=float, default=8.19)
    ap.add_argument("--hidden", type=int, default=4096)
    ap.add_argument("--layers", type=int, default=36)
    ap.add_argument("--vocab", type=int, default=151936)
    ap.add_argument("--act-mb-per-token", type=float, default=0.55)
    ap.add_argument("--comm-gb", type=float, default=2.0, help="FSDP all-gather/reduce-scatter buffers")
    ap.add_argument("--fused-chunk-gb", type=float, default=2.0)
    ap.add_argument("--context-gb", type=float, default=1.5, help="CUDA context + NCCL")
    ap.add_argument("--reserve-frac", type=float, default=0.10, help="Allocator fragmentation margin")
    ap.add_argument("--optimizer-offload", action="store_true")
    ap.add_argument("--param-offload", action="store_true")
    ap.add_argument("--lora", action="store_true")
    a = ap.parse_args()

    world = a.gpus * a.nnodes
    print(f"Qwen3-8B full FT estimate: {world} GPUs x {a.gpu_mem_gb:.0f} GB, longest sample {a.seq_len} tokens, act {a.act_mb_per_token} MB/token"
          + (", optimizer offload" if a.optimizer_offload else "") + (", param offload" if a.param_offload else "") + (", LoRA" if a.lora else ""))
    print()
    print(f"{'sp':>3} {'dp':>3} {'states':>8} {'working':>8} {'act@1x':>8} {'total':>8} {'free':>8}  {'max micro tokens':>17} {'= longest samples/micro-batch':>30}")
    for sp in a.sp:
        if a.gpus % sp:
            print(f"{sp:>3}  (does not divide gpus={a.gpus})")
            continue
        e = estimate(a, sp, a.seq_len)
        mmt = max_micro_tokens(a, sp)
        fits = "OK" if e["free"] > 0 else "OOM"
        print(f"{sp:>3} {world // sp:>3} {e['states'] / GB:>7.1f}G {e['working'] / GB:>7.1f}G {e['activations'] / GB:>7.1f}G {e['total'] / GB:>7.1f}G {e['free'] / GB:>7.1f}G  {mmt:>17,}  {mmt / a.seq_len:>28.1f}   {fits}")
    print()
    print("act@1x = activations with ONE longest sample per micro-batch (max_token_len_per_gpu = seq_len/sp).")
    print("max micro tokens = largest max_token_len_per_gpu*sp that still fits; samples/micro-batch = that / seq_len.")
    print("Global --batch-size is limited only by divisibility (multiple of dp) and dataset size, not by memory.")


if __name__ == "__main__":
    main()
