#!/usr/bin/env python3
"""Why is ppo_micro_batch_size_per_gpu=2 twice as slow per token?

Times fwd+bwd of the real model under the four layouts that matter:

  A  one sequence of 2T, no cu_seqlens          (pre-patch batched path)
  B  one sequence of 2T, cu_seqlens=[0,2T]      (post-patch, micro=1)
  C  two sequences of T packed, [0,T,2T]        (post-patch, micro=2)
  D  two separate forwards of T                 (what micro=1 actually does)

C vs D is the question: is packing two rows into one micro-batch slower than
running them as two micro-batches? A vs B isolates the cost of merely turning
on the varlen path.
"""
import time, torch
from transformers import AutoModelForCausalLM
from verl.utils.experimental.torch_functional import FusedLinearForPPO

MODEL, T, REPS = "Qwen/Qwen3.5-4B", 8192, 3
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                             attn_implementation="flash_attention_2").cuda()
model.gradient_checkpointing_enable(); model.train()
lm = getattr(model.model, "language_model", model.model)
fused = FusedLinearForPPO()

def step(seqs, cu):
    """seqs: list of lengths packed into one row (or a single length)."""
    total = sum(seqs)
    ids = torch.randint(1000, 200000, (1, total), device="cuda")
    pos = torch.cat([torch.arange(n, device="cuda") for n in seqs]).unsqueeze(0)
    kw = {"position_ids": pos}
    if cu is not None:
        kw["cu_seqlens"] = torch.tensor([0, *torch.tensor(seqs).cumsum(0).tolist()],
                                        device="cuda", dtype=torch.long)
        kw["cu_seqlens_cpu"] = kw["cu_seqlens"].cpu()
    hs = lm(input_ids=ids, **kw).last_hidden_state   # cu_seqlens flows to layers via **kwargs
    w = model.lm_head.weight
    lp, ent = fused.forward(hidden_states=hs.to(w.dtype), vocab_weights=w,
                            input_ids=torch.roll(ids, -1, dims=-1), temperature=1.0)
    (lp.mean() + ent.mean()).backward()
    model.zero_grad(set_to_none=True)

def timeit(label, fn, tokens):
    fn(); torch.cuda.synchronize()                      # warmup
    torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()
    t0 = time.perf_counter()
    for _ in range(REPS): fn()
    torch.cuda.synchronize()
    dt = (time.perf_counter() - t0) / REPS
    print(f"  {label:44s} {dt:7.3f} s   {dt/tokens*1e6:7.1f} us/tok   "
          f"peak {torch.cuda.max_memory_allocated()/2**30:5.1f} GB")
    return dt

print(f"T={T}, fwd+bwd, mean of {REPS}\n")
a = timeit("A  one seq 2T, no cu_seqlens",      lambda: step([2*T], None),  2*T)
b = timeit("B  one seq 2T, cu_seqlens=[0,2T]",  lambda: step([2*T], True),  2*T)
c = timeit("C  two seqs T packed [0,T,2T]",     lambda: step([T, T], True), 2*T)
d = timeit("D  two separate forwards of T",     lambda: (step([T], True), step([T], True)), 2*T)
print(f"\n  C/D = {c/d:.2f}x   (>1 means packing two rows costs more than two passes)")
print(f"  B/A = {b/a:.2f}x   (cost of the varlen path alone)")
print(f"  A vs 2x(one seq T): quadratic check")
e = timeit("E  one seq T", lambda: step([T], True), T)
print(f"  A/(2*E) = {a/(2*e):.2f}x   (>1 => attention is quadratic across the packed row)")
