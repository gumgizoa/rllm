#!/usr/bin/env bash
# Check that an rLLM image (recipe/docker/Dockerfile) has what training and evaluation need.
#
#   rllm-smoke-test            # inside a container started with --gpus all and the docker socket
#   rllm-smoke-test --no-gpu   # at build time (no GPU, no docker socket)
#
# Runs against the checkout at /workspace/rllm (the baked one or a mounted one).
# Exits non-zero on the first missing piece.
set -euo pipefail
cd "${RLLM_DIR:-/workspace/rllm}"
NO_GPU=0
[ "${1:-}" = "--no-gpu" ] && NO_GPU=1

echo "== checkout: $(git log -1 --format='%h %s' 2>/dev/null || echo 'not a git checkout')"
echo "== python: $(command -v python) ($(python --version))"
[ "$(command -v python)" = /opt/venv/bin/python ] || { echo "python is not the image venv (/opt/venv)" >&2; exit 1; }

echo "== python packages"
python - <<'PY'
import importlib.metadata as m
import sys

want = {
    "torch": "2.11.0", "vllm": "0.22.1", "verl": "0.8.0", "transformers": "5.5.3",
    "flash-attn": "2.8.3", "flash-linear-attention": "0.5.2", "litellm": "1.83.0",
}
bad = []
for pkg, ver in want.items():
    got = m.version(pkg)
    print(f"  {pkg} {got}")
    if not got.startswith(ver):
        bad.append(f"{pkg} {got} (want {ver})")
for pkg in ("rllm", "rllm-model-gateway", "harbor", "ray", "docker"):
    print(f"  {pkg} {m.version(pkg)}")
import torch

print(f"  torch cuda {torch.version.cuda}")
import flash_attn  # noqa: F401  compiled extension loads
import fla  # noqa: F401
import rllm  # noqa: F401
import rllm_model_gateway  # noqa: F401
import verl  # noqa: F401
import vllm  # noqa: F401

if bad:
    sys.exit("version mismatch: " + ", ".join(bad))
PY

echo "== patches"
for script in recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh recipe/eval/scripts/apply_harbor_patches.sh; do
    check=$(bash "$script" --check)
    echo "$check" | sed 's/^/  /'
    if echo "$check" | grep -q "NOT APPLIED"; then
        echo "patch missing ($script)" >&2
        exit 1
    fi
done

echo "== CLIs"
rllm --help >/dev/null && echo "  rllm ok"
docker --version | sed 's/^/  /'
docker compose version | sed 's/^/  /'
aws --version | sed 's/^/  /'

if [ "$NO_GPU" = 0 ]; then
    echo "== runtime"
    python -c "import torch; assert torch.cuda.is_available(), 'no GPU visible'; print('  GPUs:', torch.cuda.device_count(), torch.cuda.get_device_name(0))"
    docker info --format '  docker daemon {{.ServerVersion}}' || { echo "docker daemon unreachable: mount /var/run/docker.sock" >&2; exit 1; }
fi
echo "OK"
