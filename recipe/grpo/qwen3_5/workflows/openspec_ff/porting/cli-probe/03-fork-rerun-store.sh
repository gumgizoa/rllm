set -u
export PATH=/opt/opsx/node/bin:$PATH OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1
cd / && openspec init --tools none >/dev/null 2>&1
echo "== config.yaml"; grep -v '^\s*#' /openspec/config.yaml | sed '/^$/d'
echo "== schema fork"; openspec schema fork spec-driven swe-driven; echo "exit=$?"; find /openspec/schemas -type f | sort
sed -i 's/^schema: spec-driven/schema: swe-driven/' /openspec/config.yaml
sed -i 's/ask the user instead of guessing/MARKER_FORK_EDIT/' /openspec/schemas/swe-driven/schema.yaml; grep -c MARKER_FORK_EDIT /openspec/schemas/swe-driven/schema.yaml
cd /testbed
echo "== new change (no --schema)"; openspec new change issue; cat /openspec/changes/issue/.openspec.yaml
echo "== design instruction from fork"; openspec instructions design --change issue --json | grep -o 'MARKER_FORK_EDIT' | head -1
echo "== new change again (ff re-run)"; openspec new change issue; echo "exit=$?"
echo "== store list"; openspec store list --json; echo "exit=$?"
echo "== list (one change)"; openspec list --json | tr -d '\n ' | head -c 300; echo
echo "== repo"; git -C /testbed status --porcelain | wc -l
