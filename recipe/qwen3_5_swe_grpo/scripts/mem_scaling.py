#!/usr/bin/env python3
"""Activation-memory scaling for one Qwen3.5-4B sequence, fwd+bwd.

Mirrors the recipe's training-side settings: bf16, gradient checkpointing,
flash-attention-2, and verl's FusedLinearForPPO head (so no full logits
tensor). One sequence per forward, which is what ppo_micro_batch_size_per_gpu=1
gives us.

Caveat: single GPU, so parameters/grads/optimizer are NOT FSDP-sharded or
CPU-offloaded here. In the real 8-GPU run those cost ~0.9 GB/GPU (sharded) and
are offloaded, so subtract the reported `params+grads` figure to estimate the
per-GPU peak of the real setup.
"""
import gc, sys, torch
from transformers import AutoModelForCausalLM
from verl.utils.experimental.torch_functional import FusedLinearForPPO

MODEL = "Qwen/Qwen3.5-4B"
LENGTHS = [int(x) for x in (sys.argv[1:] or ["16384", "32768", "49152", "65536", "98304", "131072"])]
# Usage: CUDA_VISIBLE_DEVICES=0 python scripts/mem_scaling.py [seq_len ...]

model = AutoModelForCausalLM.from_pretrained(
    MODEL, dtype=torch.bfloat16, attn_implementation="flash_attention_2"
).cuda()
model.gradient_checkpointing_enable()
model.train()
lm = getattr(model.model, "language_model", model.model)

param_gb = sum(p.numel() * p.element_size() for p in model.parameters()) / 2**30
print(f"model params (bf16, unsharded): {param_gb:.1f} GB")
print(f"{'seq_len':>9} {'peak_GB':>9} {'act_GB':>9} {'GB/1K tok':>10}  status")

fused = FusedLinearForPPO()
for T in LENGTHS:
    torch.cuda.empty_cache(); gc.collect(); torch.cuda.reset_peak_memory_stats()
    try:
        ids = torch.randint(1000, 200000, (1, T), device="cuda")
        hs = lm(input_ids=ids).last_hidden_state
        w = model.lm_head.weight
        lp, ent = fused.forward(hidden_states=hs.to(w.dtype), vocab_weights=w,
                                input_ids=torch.roll(ids, -1, dims=-1), temperature=1.0)
        (lp.mean() + ent.mean()).backward()
        peak = torch.cuda.max_memory_allocated() / 2**30
        # params + grads live on GPU here; the real run shards+offloads them
        grads = sum(p.grad.numel() * p.grad.element_size() for p in model.parameters() if p.grad is not None) / 2**30
        act = peak - param_gb - grads
        print(f"{T:>9} {peak:>9.1f} {act:>9.1f} {act/(T/1024):>10.3f}  OK")
        del ids, hs, lp, ent
    except torch.OutOfMemoryError:
        print(f"{T:>9} {'-':>9} {'-':>9} {'-':>10}  OOM")
    model.zero_grad(set_to_none=True)
