# rLLM Docker image

One image for both **training** (`recipe/grpo/qwen3_5`: verl + vLLM + FSDP2, 8 x H200) and
**evaluation** (`rllm eval` with native harnesses in Docker sandboxes, `recipe/eval`).

How it is put together:

1. Base: `pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel`, the image the training and evaluation
   containers already run on.
2. `https://github.com/gumgizoa/rllm` (`main`) is cloned into **`/workspace/rllm`**.
3. The dependencies are installed from that checkout into a uv venv at **`/opt/venv`**, the same
   way `recipe/grpo/qwen3_5/README.md` installs them: `uv pip install -e ".[verl,harbor]"`,
   flash-linear-attention, the verl and harbor patches.
4. Users **mount their own rllm checkout over `/workspace/rllm`**. rllm and rllm-model-gateway are
   installed editable at that path, so the mounted code is what runs, on the baked dependencies.

## Build

The build context is `recipe/docker/` (the source comes from GitHub, not from the context):

```bash
docker build -t rllm:latest recipe/docker/
```

| Build arg | Default | What it sets |
| --- | --- | --- |
| `RLLM_REPO` | `https://github.com/gumgizoa/rllm.git` | Repository cloned into `/workspace/rllm` |
| `RLLM_REF` | `main` | Branch, tag or commit. A branch is re-resolved on every build, so a new commit rebuilds from the clone on; pass a commit SHA to pin |
| `BASE_IMAGE` | `pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel` | Base image |
| `PYTHON_VERSION` | `3.12` | uv-managed CPython for the venv |
| `RLLM_EXTRAS` | `verl harbor` | pyproject extras. `verl`: training stack. `harbor`: the Harbor Registry dataset client (`rllm dataset pull harbor:...`) |
| `FLASH_ATTN_CUDA_ARCHS` | `90` | GPU architectures flash-attn is compiled for. `90` = H100/H200; e.g. `"80;90"` adds A100 (longer build) |
| `MAX_JOBS` | `32` | Parallel compile jobs for flash-attn |
| `FLA_VERSION` | `0.5.2` | flash-linear-attention (Qwen3.5 linear-attention kernels) |
| `AWSCLI_VERSION` | `2.39.3` | AWS CLI v2 |
| `UV_VERSION` | `0.13.7` | uv |

- BuildKit is required (`docker buildx`; on Ubuntu `apt-get install docker-buildx`). The uv cache is
  a BuildKit cache mount, which keeps the compiled flash-attn wheel: rebuilding for a new commit
  reinstalls the dependencies from the cache instead of compiling flash-attn again.
- The build ends with `rllm-smoke-test --no-gpu`: a missing package, a version drift or an
  unapplied verl patch fails the build instead of the first training step.
- `/opt/rllm-build-commit.txt` records the commit the image was built from.

## What is in it

| Piece | Where | Notes |
| --- | --- | --- |
| Python venv | `/opt/venv` (first on `PATH`, `VIRTUAL_ENV` set) | torch 2.11.0 (cu130), vllm 0.22.1, verl 0.8.0, transformers 5.5.3, flash-attn 2.8.3, flash-linear-attention 0.5.2, litellm 1.83.0, harbor |
| rLLM checkout | `/workspace/rllm` (with `.git`) | rllm and rllm-model-gateway installed editable. `/workspace/rllm/.venv` links to `/opt/venv` |
| verl patch | applied in `/opt/venv` | `recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh` (`patches/verl-pr6660-qwen3_5-ulysses-sp.patch`, verl PR #6660 backport) |
| harbor patch | applied in `/opt/venv` | `recipe/eval/scripts/apply_harbor_patches.sh` (`patches/harbor-0.3.0-openhands-sdk.patch`). Only `--agent harbor:openhands-sdk` (deprecated Harbor path) uses it |
| Docker CLI, buildx, compose | `docker` | Talks to the **host** daemon through the mounted socket; no daemon in the image |
| AWS CLI v2 | `aws` | No credentials baked in |
| Smoke test | `rllm-smoke-test` | Packages, versions, verl and harbor patches, CLIs; with a GPU and the socket, also CUDA and the daemon |

The base image's own python and torch 2.12.1 stay in the image but are not used: vllm 0.22.1
pins torch 2.11.0, so the venv has its own. `python` on `PATH` is `/opt/venv/bin/python`;
`rllm-smoke-test` fails if it is not.

Nothing secret is in the image: no `.env`, no AWS keys, HF token or W&B key.

## Run

```bash
docker run -d --name rllm \
  --gpus all \
  --network host \
  --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/your/rllm:/workspace/rllm \
  -v /opt/dlami/nvme:/opt/dlami/nvme \
  rllm:latest sleep infinity
docker exec -it rllm bash

# inside
rllm-smoke-test          # your checkout, GPUs visible, docker daemon reachable
```

| Option | Why |
| --- | --- |
| `-v /path/to/your/rllm:/workspace/rllm` | Your checkout replaces the baked one. Without it, the image runs the commit it was built from |
| `-v /var/run/docker.sock:...` | Required. Task sandboxes, task images (`rllm-task-*`) and the agent image (`rllm-agent-*`) are built and run by the host daemon (docker out of docker) |
| `--gpus all` | Training (8 GPUs) and vLLM serving for evaluation |
| `--network host` | Sandboxes reach the rLLM model gateway at `host.docker.internal`, and the gateway binds inside this container; on a bridge network the sandboxes cannot reach it. Also lets `--base-url http://127.0.0.1:8000/v1` reach a vLLM server on the host |
| `--ipc=host`, `--ulimit memlock=-1` | Ray, NCCL and vLLM need a large `/dev/shm` and pinned memory (or use `--shm-size 64g`) |
| `-v <data>:<same path>` | Datasets (`RLLM_HOME`), HF cache (`HF_HOME`), checkpoints (`RLLM_CKPT_DIR`): put them on the large local disk, not the container's writable layer. Mount at the **same path as on the host**: the native path does not need it, but Harbor (deprecated) bind-mounts `$RLLM_HOME` paths that the host daemon resolves |

**Your checkout and the baked dependencies.**
- The editable install points at `/workspace/rllm`, so code changes in your checkout take effect
  without reinstalling.
- If your checkout changes dependencies (`pyproject.toml`, `rllm-model-gateway/pyproject.toml`) or
  the verl patches, update the venv inside the container:
  `uv pip install -e ".[verl,harbor]" && bash recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh && bash recipe/eval/scripts/apply_harbor_patches.sh`.
  That change lives in the container's writable layer; rebuild the image to keep it.
- Your checkout hides the baked `.venv` link. `VIRTUAL_ENV` and `PATH` still point at `/opt/venv`,
  which is what `train_verl.sh` checks. If your checkout has its own `.venv`, it is ignored as long
  as you do not activate it.

**Credentials.** Pass them at run time, e.g. `--env-file recipe/grpo/qwen3_5/.env` (HF_TOKEN,
WANDB_API_KEY, RLLM_HOME, HF_HOME, ...), and for S3 an instance role or `-v ~/.aws:/root/.aws:ro`.
With docker out of docker, `-v` source paths are resolved on the host.

## Training and evaluation

Inside the container, follow the recipes as written; the environment steps they list (venv, extras,
flash-linear-attention, verl and harbor patches) are already done:

- Training: `recipe/grpo/qwen3_5/README.md` from step 2 (`.env`, datasets), then
  `bash recipe/grpo/qwen3_5/train_verl.sh`.
- Evaluation: `recipe/eval/README.md` (pre-evaluation checklist in section 1). Serve the model with
  `vllm serve ...` in the same container or another one on the host network.
