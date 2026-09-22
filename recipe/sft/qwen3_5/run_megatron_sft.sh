set -euo pipefail

# ---------------------------------------------------------------------------------
# Environment this script expects
#
#     pip install --break-system-packages --no-deps -e recipe/sft              # swe_sft
#     # verl itself comes from rLLM's own dependencies; this script only needs it importable
#     pip install --break-system-packages flash-linear-attention==0.5.2
#
#     python3 -c "import verl, swe_sft, fla, tilelang; print('ok')"
#
# --break-system-packages: PEP 668 marks the system interpreter externally managed.
#
# NO extras on flash-linear-attention. `flash-linear-attention[tilelang]` looks right,
#   because on Hopper fla does require the tilelang kernel (see CUDA_HOME below) - but
#   tilelang is already in the image, and asking pip for the extra makes it re-resolve
#   tilelang's own dependency tree. Measured result: numpy silently upgraded 1.26.4 ->
#   2.5.2 and nvidia-nccl/-cudnn silently *downgraded* into ~/.local, where they shadow
#   the image's. Install fla bare and let tilelang be the one the image already has.
#
#
# Not installed by any of the above, and needed before the first step:
#   - an ENV_FILE (recipe/sft/qwen3_5/.env, gitignored) - see "From ENV_FILE" below
#   - the model in the HF cache under $HF_HOME  (Qwen/Qwen3.5-4B, ~9 GB)
#   - a container started with --shm-size=32g if you intend to pass NUM_WORKERS > 0
#     (see the NUM_WORKERS block below)
# ---------------------------------------------------------------------------------

if [ -n "${ENV_FILE:-}" ] && [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

export CUDA_DEVICE_MAX_CONNECTIONS=1
export HYDRA_FULL_ERROR=1
export TOKENIZERS_PARALLELISM=false
export TORCH_FR_BUFFER_SIZE=100

# fla refuses its own Triton backward for chunk_gated_delta_rule on Hopper (wrong results
# for 3.4.0 <= triton < 3.7.1) and uses tilelang, which shells out to nvcc. Unset, it picks
# the nvcc in the nvidia/cu13 wheel and compiles against mismatched headers (CCCL check).
export CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
# Micro-batch shapes vary every step, so the allocator fragments into an OOM without this.
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}

TRAIN_ARGS=("$@")

########################### From ENV_FILE ###########################
# What to train on and with. These name a specific dataset and model family, so they belong
# to a run, not to this file - keep them in ENV_FILE and this script stays reusable.
#
#     TRAIN_FILES, VAL_FILES        parquet built by scripts/filter_sft_parquet.py
#     CUSTOM_CLS_PATH, _NAME        the dataset class that renders it for this model family
#     CHAT_TEMPLATE_PATH            optional; omit to use the model's stock template
#     HF_MODEL_PATH, EXP_NAME
#     TRAIN_BATCH_SIZE, MAX_LENGTH, MAX_TOKEN_LEN_PER_GPU, TP, PP, CP, EP
#
# The last two lines have defaults below; the first four do not, and fail here if unset.
: "${TRAIN_FILES:?set TRAIN_FILES in ENV_FILE}"
: "${VAL_FILES:?set VAL_FILES in ENV_FILE}"
: "${CUSTOM_CLS_PATH:?set CUSTOM_CLS_PATH in ENV_FILE}"
: "${CUSTOM_CLS_NAME:?set CUSTOM_CLS_NAME in ENV_FILE}"

########################### Quick Config ###########################

NUM_GPUS=${NUM_GPUS:-8}
MASTER_ADDR=${MASTER_ADDR:-localhost}
MASTER_PORT=${MASTER_PORT:-29500}
NNODES=${NNODES:-1}
NODE_RANK=${NODE_RANK:-0}

# No model parallelism: nothing in a 4.7B model needs splitting on 143 GB cards, and the one
# tensor that did - the logits of a long trajectory - is gone once use_fused_kernels is on.
# So all 8 GPUs go to DP; PP would only add bubbles and cost DP.
TP=${TP:-1}
PP=${PP:-1}
VPP=${VPP:-null}
CP=${CP:-1}
EP=${EP:-1}
ETP=${ETP:-null}

TRAIN_BATCH_SIZE=${TRAIN_BATCH_SIZE:-128}
# Ignored unless USE_DYNAMIC_BSZ=False; dynamic batching forms micro-batches by token budget.
MICRO_BATCH_SIZE=${MICRO_BATCH_SIZE:-2}
MAX_LENGTH=${MAX_LENGTH:-131072}
USE_DYNAMIC_BSZ=${USE_DYNAMIC_BSZ:-True}
# A sequence is never split, so this is floored by the longest row in the mix or
# `rearrange_micro_batches` asserts. To lower it, re-filter the mix with a smaller
# --max-tokens (scripts/filter_sft_parquet.py) - it is not a free memory knob.
MAX_TOKEN_LEN_PER_GPU=${MAX_TOKEN_LEN_PER_GPU:-${MAX_LENGTH}}
LR=${LR:-2e-5}
MIN_LR=${MIN_LR:-2e-6}
# Adam moments. Single source of truth, because they have to be passed twice - see the
# `override_optimizer_config` lines in ENGINE for why. Keep the two spellings in sync.
BETA1=${BETA1:-0.9}
BETA2=${BETA2:-0.95}

# How many of the 32 layers re-run their forward during the backward pass. Recomputing all of
# them (the `uniform`/1 this replaced) is an extra full forward. The layers above this count keep
# their activations instead, which buys speed with memory - and memory is what we have.
# Swept on this mix at a 64k budget, 8 GPUs, batch 32:
#     32 -> 45.3 s/step,  56 GB      28 -> 40.3 s/step,  85 GB
#     24 -> 39.5 s/step, 124 GB      16 -> OOM
# So each resident layer costs ~8.4 GB per 64k-token micro-batch. 28 takes almost all of the
# available speedup and still leaves ~58 GB of headroom for a worse-packed micro-batch; 24 buys
# a further 1.5% for a margin too thin to run unattended. Raise it if a longer mix overflows.
RECOMPUTE_NUM_LAYERS=${RECOMPUTE_NUM_LAYERS:-28}

# Hand each rank a similar token load instead of every 8th row of a shuffled epoch. All ranks
# meet at the gradient all-reduce, so the longest-loaded rank sets the step time: unbalanced,
# the busiest of 8 carries 1.22x the mean and ~17% of each step is spent waiting. The global
# batch and its row order are unchanged, so this moves work between ranks without touching the
# update - `sft_loss` normalises by the DP-global token count. Needs `n_tokens` in the parquet.
BALANCE_DP_TOKEN=${BALANCE_DP_TOKEN:-True}

# Workers pass batches through /dev/shm, so this is capped by how the container was started.
# On Docker's 64 MB default a 130k-token batch exhausts it: one rank dies on "unable to
# allocate shared memory" and the rest hang in NCCL forever. Check `df -h /dev/shm` first:
# below ~8G this must be 0, which collates in the main process (a few percent of step time).
NUM_WORKERS=${NUM_WORKERS:-4}

DATA_ROOT="${DATA_ROOT:-/workspace/rllm/recipe/sft}"
HF_MODEL_PATH="${HF_MODEL_PATH:-Qwen/Qwen3.5-4B}"

project_name="${PROJECT_NAME:-swe-agent}"
exp_name="${EXP_NAME:-qwen3-5-4b-megatron-swe-sft}"

TOTAL_EPOCHS=${TOTAL_EPOCHS:-5}

# Save several times per epoch, but on a divisor of it, so an epoch boundary is always a
# save point and "the model after N epochs" is a checkpoint you actually have.
TRAIN_ROWS=$(python3 -c "import pyarrow.parquet as pq,sys;print(pq.ParquetFile(sys.argv[1]).metadata.num_rows)" \
    "${TRAIN_FILES}")
STEPS_PER_EPOCH=$(( TRAIN_ROWS / TRAIN_BATCH_SIZE ))
SAVE_FREQ=${SAVE_FREQ:-$(( STEPS_PER_EPOCH / 4 ))}
# Validate exactly where we save. SAVE_FREQ is a divisor of the epoch, so this makes every
# epoch boundary a validation point and gives every checkpoint we keep a val number measured
# at that very step - no interpolation, no phase error.
#
# A fixed stride (this was 50 for one run) does not divide the epoch, and the cost is not
# cosmetic: with stride 50 the last val point inside each epoch sits 4, 8, 12, 16, 20 steps
# before the boundary on a 404-step epoch and 48, 46, 44, 42, 40 on a 448-step one. The offset
# *moves* each epoch, and since val falls steadily within an epoch, that biases later epochs
# to look worse than they are - i.e. toward stopping early. On the 9B run the two epochs being
# compared were measured 4 and 8 steps from their boundaries, and the resulting "regression"
# was +0.000086, the same order as the bias itself. Any epoch-over-epoch rule needs the
# boundary itself, which is what aligning to SAVE_FREQ guarantees.
#
# The trade-off is resolution: 4 points per epoch, not 8. If you want 8 and keep the guarantee,
# use a divisor of STEPS_PER_EPOCH (448 -> 56 works; 404 = 2^2 x 101 has none near 50, which is
# exactly why a fixed stride was wrong), or validate at the stride *and* at every save point.
TEST_FREQ=${TEST_FREQ:-${SAVE_FREQ}}

########################### Parameter Arrays ###########################
ENGINE=(
    engine=megatron
    optim=megatron
    optim.lr=${LR}
    optim.min_lr=${MIN_LR}
    optim.lr_warmup_steps_ratio=0.03
    optim.weight_decay=0.1
    optim.betas="[${BETA1},${BETA2}]"
    # `optim.betas` alone is silently dropped on the Megatron path: init_megatron_optim_config()
    # (verl/utils/megatron/optimizer.py) builds optim_args from optimizer/lr/min_lr/clip_grad/
    # weight_decay only, and reads `betas` nowhere except the Muon branch - while Megatron's
    # OptimizerConfig has no `betas` field at all, just adam_beta1/adam_beta2 defaulting to
    # 0.9/0.999. So a run that asked for beta2=0.95 trained with 0.999 and logged it, which is
    # what happened to the 4B and 9B runs here. override_optimizer_config is merged into
    # optim_args last, so restating them under the names Megatron actually reads is what makes
    # them take effect. Do not delete these as redundant: `optim.betas` above is the intent that
    # the config records (and the Muon path reads), these two are what reach the optimizer.
    +optim.override_optimizer_config.adam_beta1=${BETA1}
    +optim.override_optimizer_config.adam_beta2=${BETA2}
    optim.clip_grad=1.0
    optim.lr_warmup_init=0
    optim.lr_decay_style=cosine
    engine.tensor_model_parallel_size=${TP}
    engine.pipeline_model_parallel_size=${PP}
    engine.virtual_pipeline_model_parallel_size=${VPP}
    engine.context_parallel_size=${CP}
    engine.expert_model_parallel_size=${EP}
    engine.expert_tensor_parallel_size=${ETP}
    # megatron-bridge needs `modelopt`, absent here; vanilla mbridge does not, and it is the
    # one carrying the `qwen3_5` bridge.
    engine.use_mbridge=True
    engine.vanilla_mbridge=True
    engine.dtype=bfloat16
    # THD. GDN in megatron-core 0.18 does accept packed_seq_params, so the "Qwen3.5 cannot
    # pack" note in the Ascend guide (written against Megatron-LM 0.16) no longer applies.
    engine.use_remove_padding=True
    engine.override_transformer_config.attention_backend=auto
)

# `block` recomputes only the first RECOMPUTE_NUM_LAYERS layers of the stage and keeps the rest
# resident, which is the knob `uniform` does not give you: under `uniform`, num_layers is the
# chunk size, so every layer is recomputed whatever it is set to. At 0 the overrides are left
# off entirely, which leaves mcore's `recompute_granularity=null` - no recompute at all.
if [ "${RECOMPUTE_NUM_LAYERS}" -gt 0 ]; then
    ENGINE+=(
        +engine.override_transformer_config.recompute_method=block
        +engine.override_transformer_config.recompute_granularity=full
        +engine.override_transformer_config.recompute_num_layers=${RECOMPUTE_NUM_LAYERS}
    )
fi

DATA=(
    data.train_files="${TRAIN_FILES}"
    data.val_files="${VAL_FILES}"
    data.custom_cls.path="${CUSTOM_CLS_PATH}"
    data.custom_cls.name="${CUSTOM_CLS_NAME}"
    data.train_batch_size=${TRAIN_BATCH_SIZE}
    data.micro_batch_size_per_gpu=${MICRO_BATCH_SIZE}
    data.max_length=${MAX_LENGTH}
    # The only mode the engine forward path implements; `right`/`left_right` assert.
    data.pad_mode=no_padding
    data.truncation='error'
    data.use_dynamic_bsz=${USE_DYNAMIC_BSZ}
    data.max_token_len_per_gpu=${MAX_TOKEN_LEN_PER_GPU}
    data.messages_key=messages
    data.tools_key=tools
    data.num_workers=${NUM_WORKERS}
    data.balance_dp_token=${BALANCE_DP_TOKEN}
)

# Optional, and a `+` key, so it has to be appended rather than left empty: passing
# `+data.chat_template_path=` would set it to the empty string instead of leaving it unset.
# A training template keeps the <think> block of every assistant turn, so every turn is
# supervisable; serving must then use the same one - see recipe/sft/README.md section 2b.
if [ -n "${CHAT_TEMPLATE_PATH:-}" ]; then
    DATA+=( +data.chat_template_path="${CHAT_TEMPLATE_PATH}" )
fi

MODEL=(
    model.path="${HF_MODEL_PATH}"
    # TrainingWorker copies both of these over the engine's values
    # (verl/workers/engine_workers.py:112-113), so the `model.` spelling is the one that wins.
    model.use_remove_padding=True
    # Chunked linear+cross-entropy instead of a materialised [tokens, 248320] logit tensor
    # that Float16Module then upcasts to fp32 - 1.5 MB/token, the actual OOM cause. Megatron
    # only enables it when use_remove_padding=True.
    model.use_fused_kernels=True
    model.trust_remote_code=True
)

TRAINER=(
    trainer.logger='["console","wandb"]'
    trainer.project_name=${project_name}
    trainer.experiment_name=${exp_name}
    trainer.n_gpus_per_node=${NUM_GPUS}
    trainer.nnodes=${NNODES}
    # Epochs run for hours; pick up from the last checkpoint instead of restarting.
    trainer.resume_mode=auto
    trainer.save_freq=${SAVE_FREQ}
    trainer.test_freq=${TEST_FREQ}
    # Keep every checkpoint (~75 GB each). 5 epochs over 58k trajectories will likely overfit,
    # so the one you want is early - a rolling window would have deleted it by then.
    trainer.max_ckpt_to_keep=null
    trainer.total_epochs=${TOTAL_EPOCHS}
    trainer.default_local_dir="${DATA_ROOT}/checkpoints/${exp_name}"
)

########################### Launch ###########################

echo "=================================================="
echo " Qwen3.5 SWE SFT Training (Megatron)"
echo "  Model  : ${HF_MODEL_PATH}"
echo "  GPUs   : ${NUM_GPUS} per node"
echo "  Nodes  : ${NNODES} (rank ${NODE_RANK})"
echo "  Master : ${MASTER_ADDR}:${MASTER_PORT}"
echo "  TP=${TP}  PP=${PP}  VPP=${VPP}  CP=${CP}  EP=${EP}  ETP=${ETP}"
echo "  DP     : $(( NUM_GPUS * NNODES / (TP * PP * CP) ))"
echo "  tokens : ${MAX_TOKEN_LEN_PER_GPU} per GPU per micro-batch"
echo "  recomp : ${RECOMPUTE_NUM_LAYERS}/32 layers recomputed  |  dp token balancing: ${BALANCE_DP_TOKEN}"
echo "  steps  : ${STEPS_PER_EPOCH}/epoch x ${TOTAL_EPOCHS} epochs over ${TRAIN_ROWS} rows (save every ${SAVE_FREQ})"
echo "  data   : ${TRAIN_FILES}"
echo "  render : ${CUSTOM_CLS_NAME} + ${CHAT_TEMPLATE_PATH:-<stock template>}"
echo "  output : ${DATA_ROOT}/checkpoints/${exp_name}"
echo "=================================================="

mkdir -p "${DATA_ROOT}/checkpoints/${exp_name}"

PYTHONUNBUFFERED=1 torchrun \
    --nproc_per_node=${NUM_GPUS} \
    --nnodes=${NNODES} \
    --node_rank=${NODE_RANK} \
    --master_addr=${MASTER_ADDR} \
    --master_port=${MASTER_PORT} \
    -m verl.trainer.sft_trainer \
    "${DATA[@]}" \
    "${MODEL[@]}" \
    "${ENGINE[@]}" \
    "${TRAINER[@]}" \
    "${TRAIN_ARGS[@]}" 2>&1 | tee -a "${DATA_ROOT}/checkpoints/${exp_name}/train.log"
