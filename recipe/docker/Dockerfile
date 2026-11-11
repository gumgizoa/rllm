# syntax=docker/dockerfile:1.7
#
# rLLM image for both training (recipe/grpo/qwen3_5: verl + vLLM + FSDP2) and evaluation
# (rllm eval, native harnesses in Docker sandboxes). The build context is this directory:
#
#   docker build -t rllm:latest docker/
#
# The repo is cloned from GitHub into /workspace/rllm and the dependencies are installed from it
# into /opt/venv. Users mount their own checkout over /workspace/rllm; the editable install then
# runs their code with the dependencies baked here. See docker/README.md.

# The same base the training and evaluation containers run on (recipe/eval/README.md 0.1), with
# the same setup on top: a uv venv with its own torch. The image's system torch (2.12.1) is not
# used: vllm 0.22.1 pins torch 2.11.0, which on PyPI is the cu130 build, and flash-attn is compiled
# here against it with the image's CUDA 13.0 nvcc. Use the venv's python (first on PATH), not
# /usr/bin/python or the image's own environment.
ARG BASE_IMAGE=pytorch/pytorch:2.12.1-cuda13.0-cudnn9-devel
ARG UV_VERSION=0.13.7

# `COPY --from` cannot expand a build arg, so the uv image is a named stage.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ${BASE_IMAGE}

# Source to clone. A branch name is re-resolved on every build (a new commit invalidates the
# cache); pass a commit SHA to pin.
ARG RLLM_REPO=https://github.com/gumgizoa/rllm.git
ARG RLLM_REF=main
ARG PYTHON_VERSION=3.12
# pyproject extras: verl = training stack (verl, vllm, flash-attn), harbor = Harbor Registry
# dataset client (`rllm dataset pull harbor:...`, also used by native eval).
ARG RLLM_EXTRAS="verl harbor"
# Qwen3.5 linear-attention kernels (recipe/grpo/qwen3_5/README.md, step 3).
ARG FLA_VERSION=0.5.2
# flash-attn is built from source against the venv's torch. Building for H100/H200 (sm90)
# only keeps the build to minutes; add arches for other GPUs, e.g. "80;90".
ARG FLASH_ATTN_CUDA_ARCHS=90
ARG MAX_JOBS=32
ARG AWSCLI_VERSION=2.39.3

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CUDA_HOME=/usr/local/cuda

# System packages.
# - docker.io / docker-buildx / docker-compose-v2: the Docker CLI. Sandboxes, task images and the
#   agent image are built and run through the host daemon (mount /var/run/docker.sock); the image
#   does not run its own daemon. Without buildx, `docker build` under docker 29 refuses to run.
# - git: the repo is a git checkout; patch: recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh.
# - build-essential, ninja: flash-attn build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git patch unzip jq less vim-tiny tmux procps iproute2 rsync \
        build-essential ninja-build \
        docker.io docker-buildx docker-compose-v2 \
    && rm -rf /var/lib/apt/lists/*

# AWS CLI v2 (S3 for datasets, checkpoints, image backups).
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWSCLI_VERSION}.zip" -o /tmp/awscli.zip \
    && unzip -q /tmp/awscli.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscli.zip \
    && aws --version

# uv, a uv-managed CPython and the venv, all outside /workspace/rllm (which users mount over)
# and outside /root (which some setups mount).
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN uv python install "${PYTHON_VERSION}" \
    && uv venv --python "${PYTHON_VERSION}" /opt/venv

# The repo, with its .git so the checkout can be updated or switched in the container.
ADD --keep-git-dir=true ${RLLM_REPO}#${RLLM_REF} /workspace/rllm
WORKDIR /workspace/rllm
# A checkout mounted over /workspace/rllm is usually owned by another uid; let git use it anyway.
RUN git config --system --add safe.directory /workspace/rllm

# Dependencies, as recipe/grpo/qwen3_5/README.md installs them: rllm and rllm-model-gateway
# editable at /workspace/rllm (the repo's [tool.uv] sources and overrides apply), flash-attn
# compiled against the venv's torch ([tool.uv.extra-build-dependencies]). The uv cache mount keeps
# the built flash-attn wheel, so a rebuild for a new commit does not compile it again.
RUN --mount=type=cache,target=/root/.cache/uv \
    FLASH_ATTN_CUDA_ARCHS="${FLASH_ATTN_CUDA_ARCHS}" MAX_JOBS="${MAX_JOBS}" NVCC_THREADS=2 \
    uv pip install -e ".[$(echo ${RLLM_EXTRAS} | tr ' ' ',')]" \
    && uv pip install "flash-linear-attention==${FLA_VERSION}" \
    && bash recipe/grpo/qwen3_5/scripts/apply_verl_patches.sh \
    && ln -sfn /opt/venv /workspace/rllm/.venv \
    && git -C /workspace/rllm log -1 --format='rllm %H %s' > /opt/rllm-build-commit.txt

# Fail the build here rather than in the first training step.
COPY smoke_test.sh /usr/local/bin/rllm-smoke-test
RUN chmod +x /usr/local/bin/rllm-smoke-test && rllm-smoke-test --no-gpu

CMD ["/bin/bash"]
