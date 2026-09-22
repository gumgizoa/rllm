#!/usr/bin/env bash
# Apply the eval recipe's Harbor patches to the installed harbor package.
#
# rLLM pins harbor==0.3.0 and does not vendor its sources, so a fix that only
# exists in a later Harbor release (or not yet upstream at all) has to be
# patched into site-packages rather than picked up by upgrading -- 0.22.0
# reshuffled the Trial API that `rllm/integrations/harbor` builds on.
#
# Idempotent: a patch already applied is detected and skipped.
#
#   bash recipe/eval/scripts/apply_harbor_patches.sh          # apply
#   bash recipe/eval/scripts/apply_harbor_patches.sh --revert # undo
#   bash recipe/eval/scripts/apply_harbor_patches.sh --check  # report only

set -euo pipefail

RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH_DIR="${RECIPE_DIR}/patches"
MODE="${1:-apply}"

HARBOR_ROOT="$(python - <<'PY'
import os, harbor
print(os.path.dirname(os.path.dirname(harbor.__file__)))
PY
)"
echo "harbor root: ${HARBOR_ROOT}"
python -c "import importlib.metadata as m; print('harbor version:', m.version('harbor'))"

shopt -s nullglob
for patch_file in "${PATCH_DIR}"/*.patch; do
    name="$(basename "${patch_file}")"
    applied=0
    patch -p1 -R --dry-run --force -s -i "${patch_file}" -d "${HARBOR_ROOT}" >/dev/null 2>&1 && applied=1

    case "${MODE}" in
        --check)
            echo "  ${name}: $([ "${applied}" = 1 ] && echo APPLIED || echo "NOT APPLIED")"
            ;;
        --revert)
            if [ "${applied}" = 1 ]; then
                patch -p1 -R -s -i "${patch_file}" -d "${HARBOR_ROOT}"
                echo "  ${name}: reverted"
            else
                echo "  ${name}: not applied, nothing to revert"
            fi
            ;;
        apply)
            if [ "${applied}" = 1 ]; then
                echo "  ${name}: already applied"
            elif patch -p1 --dry-run --force -s -i "${patch_file}" -d "${HARBOR_ROOT}" >/dev/null 2>&1; then
                patch -p1 -s -i "${patch_file}" -d "${HARBOR_ROOT}"
                echo "  ${name}: applied"
            else
                echo "  ${name}: FAILED to apply -- harbor version probably moved. Inspect with:"
                echo "      patch -p1 --dry-run -i ${patch_file} -d ${HARBOR_ROOT}"
                exit 1
            fi
            ;;
        *)
            echo "usage: $0 [apply|--revert|--check]" >&2; exit 2 ;;
    esac
done

if [ "${MODE}" = "apply" ]; then
    python - <<'PY'
from harbor.agents.factory import AgentFactory
from harbor.models.agent.name import AgentName

agent = AgentFactory._AGENT_MAP[AgentName.OPENHANDS_SDK]
print("import check OK:", agent.__name__, "python_version knob:",
      "python_version" in agent.__init__.__code__.co_varnames)
PY
fi
