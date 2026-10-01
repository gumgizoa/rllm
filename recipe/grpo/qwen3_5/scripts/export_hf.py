#!/usr/bin/env python3
"""Bake a verl FSDP checkpoint of this recipe into a vLLM-loadable Hugging Face directory.

    python recipe/grpo/qwen3_5/scripts/export_hf.py \
        --ckpt $RLLM_ARTIFACT_DIR/checkpoints/qwen3_5-swe-grpo/<experiment>/<run_id>/global_step_24 \
        --out  $RLLM_ARTIFACT_DIR/hf/<name>-step24          # --base defaults to $MODEL_PATH

Two steps, CPU only (no GPU needed; ~2 min and ~40 GB RAM for the 9B):

1. ``python -m verl.model_merger merge --backend fsdp`` on ``<global_step_N>/actor`` -> a raw
   single-file safetensors checkpoint in ``<out>.raw/``.
2. Make it look exactly like the base model, which is what vLLM already loads:
   * verl saves the vision tower under ``model.language_model.visual.*``; the base (and vLLM's
     Qwen3.5 loader) use ``model.visual.*`` -- renamed;
   * verl does not train the MTP head, so ``mtp.*`` (15 tensors) is absent -- copied from the
     base model so the key set matches (only used for speculative decoding);
   * every tensor is checked against the base index for shape and dtype, then re-sharded into
     the base model's file layout; ``config.json``, tokenizer and preprocessor files are copied
     from the base model (the merger's config says ``mtp_num_hidden_layers: 0`` and carries
     transformers-5 normalisations the base does not).
   A ``PROVENANCE.md`` records the source checkpoint. ``<out>.raw`` is removed unless ``--keep-raw``.

Verified on verl 0.8.0 / transformers 5.5.4 for Qwen3.5-9B (2026-10-01); a different base model
may need a different key rename, which the key check will report rather than silently pass.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RENAMES = [("model.language_model.visual.", "model.visual.")]
BASE_FILES = ["config.json", "chat_template.jinja", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "preprocessor_config.json", "video_preprocessor_config.json", "processor_config.json", "generation_config.json"]
TORCH_DTYPE = {"BF16": "bfloat16", "F16": "float16", "F32": "float32"}


def merge(actor_dir: Path, raw_dir: Path) -> None:
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    cmd = [sys.executable, "-m", "verl.model_merger", "merge", "--backend", "fsdp", "--local_dir", str(actor_dir), "--target_dir", str(raw_dir), "--use_cpu_initialization"]
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)


def fix(raw: Path, base: Path, out: Path) -> dict:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    base_idx = json.load(open(base / "model.safetensors.index.json"))["weight_map"]
    base_meta = {}
    for f in sorted(set(base_idx.values())):
        with safe_open(base / f, "pt") as sf:
            for k in sf.keys():
                sl = sf.get_slice(k)
                base_meta[k] = (tuple(sl.get_shape()), sl.get_dtype())

    tensors, renamed = {}, 0
    for f in sorted(raw.glob("*.safetensors")):
        with safe_open(f, "pt") as sf:
            for k in sf.keys():
                nk = k
                for old, new in RENAMES:
                    if k.startswith(old):
                        nk = new + k[len(old):]
                        renamed += 1
                tensors[nk] = sf.get_tensor(k)

    extra = sorted(k for k in tensors if k not in base_meta)
    missing = sorted(k for k in base_meta if k not in tensors)
    copied = [k for k in missing if k.startswith("mtp.")]
    if extra or len(copied) != len(missing):
        sys.exit(f"key mismatch vs base: extra={extra[:5]} missing(non-mtp)={[k for k in missing if k not in copied][:5]}")
    for k in copied:
        with safe_open(base / base_idx[k], "pt") as sf:
            tensors[k] = sf.get_tensor(k)

    for k, (shape, dtype) in base_meta.items():
        t = tensors[k]
        if tuple(t.shape) != shape:
            sys.exit(f"shape mismatch {k}: {tuple(t.shape)} vs base {shape}")
        want = getattr(torch, TORCH_DTYPE[dtype])
        if t.dtype != want:
            tensors[k] = t.to(want)

    out.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, dict] = {}
    for k, f in base_idx.items():
        by_file.setdefault(f, {})[k] = tensors[k].contiguous()
    for f, d in by_file.items():
        save_file(d, out / f, metadata={"format": "pt"})
    total = sum(t.numel() * t.element_size() for t in tensors.values())
    json.dump({"metadata": {"total_size": total}, "weight_map": dict(base_idx)}, open(out / "model.safetensors.index.json", "w"), indent=2)
    for name in BASE_FILES:
        if (base / name).exists():
            shutil.copy2(base / name, out / name)
    return {"tensors": len(tensors), "renamed": renamed, "copied_from_base": copied, "bytes": total}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True, help="<run>/global_step_N (or its actor/ subdir)")
    ap.add_argument("--out", required=True, help="Output HF directory")
    ap.add_argument("--base", default=os.environ.get("MODEL_PATH"), help="Base model dir (default: $MODEL_PATH)")
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--skip-merge", action="store_true", help="<out>.raw already exists; only post-process")
    args = ap.parse_args()
    if not args.base:
        sys.exit("--base or $MODEL_PATH is required")
    ckpt = Path(args.ckpt).resolve()
    actor = ckpt if ckpt.name == "actor" else ckpt / "actor"
    if not (actor / "fsdp_config.json").exists():
        sys.exit(f"not an FSDP actor checkpoint: {actor}")
    base, out = Path(args.base).resolve(), Path(args.out).resolve()
    raw = out.with_name(out.name + ".raw")
    if not args.skip_merge:
        merge(actor, raw)
    info = fix(raw, base, out)
    (out / "PROVENANCE.md").write_text(
        f"# {out.name}\n\n- Source: `{actor}`\n- Base model: `{base}`\n- Built by `recipe/grpo/qwen3_5/scripts/export_hf.py` "
        f"(verl.model_merger fsdp + rename {RENAMES} + {len(info['copied_from_base'])} `mtp.*` tensors copied from the base; "
        f"{info['tensors']} tensors, {info['bytes'] / 1e9:.1f} GB, re-sharded and configured like the base model).\n"
        f"- Serve like the base: `vllm serve {out} --dtype bfloat16 --max-model-len 131072 --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_xml`\n",
        encoding="utf-8",
    )
    if not args.keep_raw:
        shutil.rmtree(raw, ignore_errors=True)
    print(json.dumps({"out": str(out), **{k: v for k, v in info.items() if k != "copied_from_base"}, "mtp_copied": len(info["copied_from_base"])}))


if __name__ == "__main__":
    main()
