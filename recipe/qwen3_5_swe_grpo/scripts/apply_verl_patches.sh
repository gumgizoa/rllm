#!/usr/bin/env bash
# Apply the recipe's verl patches to the installed verl package.
#
# rLLM pins verl==0.8.0 (upstream rllm-org/rllm does too), so fixes that landed
# in verl v0.9.0 have to be backported rather than picked up by upgrading --
# v0.9.0 makes the V1 PPO trainer the default, which collides with the verl
# internals rLLM imports.
#
# Idempotent: a patch already applied is detected and skipped.
#
#   bash recipe/qwen3_5_swe_grpo/scripts/apply_verl_patches.sh          # apply
#   bash recipe/qwen3_5_swe_grpo/scripts/apply_verl_patches.sh --revert # undo
#   bash recipe/qwen3_5_swe_grpo/scripts/apply_verl_patches.sh --check  # report only

set -euo pipefail

RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_DIR="${RECIPE_DIR}/patches"
MODE="${1:-apply}"

VERL_ROOT="$(python - <<'PY'
import os, verl
print(os.path.dirname(os.path.dirname(verl.__file__)))
PY
)"
echo "verl root: ${VERL_ROOT}"
python -c "import importlib.metadata as m; print('verl version:', m.version('verl'))"

shopt -s nullglob
for patch_file in "${PATCH_DIR}"/*.patch; do
    name="$(basename "${patch_file}")"
    applied=0
    patch -p1 -R --dry-run --force -s -i "${patch_file}" -d "${VERL_ROOT}" >/dev/null 2>&1 && applied=1

    case "${MODE}" in
        --check)
            echo "  ${name}: $([ "${applied}" = 1 ] && echo APPLIED || echo "NOT APPLIED")"
            ;;
        --revert)
            if [ "${applied}" = 1 ]; then
                patch -p1 -R -s -i "${patch_file}" -d "${VERL_ROOT}"
                echo "  ${name}: reverted"
            else
                echo "  ${name}: not applied, nothing to revert"
            fi
            ;;
        apply)
            if [ "${applied}" = 1 ]; then
                echo "  ${name}: already applied"
            elif patch -p1 --dry-run --force -s -i "${patch_file}" -d "${VERL_ROOT}" >/dev/null 2>&1; then
                patch -p1 -s -i "${patch_file}" -d "${VERL_ROOT}"
                echo "  ${name}: applied"
            else
                echo "  ${name}: FAILED to apply -- verl version probably moved. Inspect with:"
                echo "      patch -p1 --dry-run -i ${patch_file} -d ${VERL_ROOT}"
                exit 1
            fi
            ;;
        *)
            echo "usage: $0 [apply|--revert|--check]" >&2; exit 2 ;;
    esac
done

if [ "${MODE}" = "apply" ]; then
    python -c "import verl.models.transformers.qwen3_5, verl.models.transformers.monkey_patch; print('import check OK')"
fi
