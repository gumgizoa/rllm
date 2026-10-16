#!/usr/bin/env bash
# G7-9 (2026-10-15): what explore's "Check for context" commands print on the empty planning tree the
# sandbox starts with, through the setup.sh wrapper (CI=1), with and without a TTY (`script -qec`).
# Run in the workflow's agent image (node + CLI under /opt/rllm/agent/node), package sandbox/ mounted at /pkg:
#
#   docker run --rm --network none -v $PKG/sandbox:/pkg:ro -v $PWD/05-list-specs-empty-tree.sh:/p.sh:ro \
#     --entrypoint bash rllm-agent-f268c8df48c7:latest /p.sh
set -u
NODE_HOME=/opt/rllm/agent/node
CLI_JS=$NODE_HOME/lib/node_modules/@fission-ai/openspec/bin/openspec.js
# the wrapper exactly as setup.sh writes it
cat > /usr/local/bin/openspec <<'EOF'
#!/bin/sh
CI=1 OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 exec /opt/rllm/agent/node/bin/node /opt/rllm/agent/node/lib/node_modules/@fission-ai/openspec/bin/openspec.js "$@"
EOF
chmod 755 /usr/local/bin/openspec
# setup.sh steps 3-4: init at /, the fork and the project config installed
(cd / && openspec init --tools none) >/dev/null
mkdir -p /openspec/schemas && cp -r /pkg/schemas/spec-driven-sandbox /openspec/schemas/
cp /pkg/openspec-config.yaml /openspec/config.yaml
mkdir -p /testbed && cd /testbed
echo "== openspec --version: $(openspec --version)"
echo "== tree"; find /openspec -type f -o -type d | sort

for cmd in "openspec list --json" "openspec list --specs" "openspec list --specs --json"; do
  echo; echo "== no TTY: $cmd"; $cmd; echo "[exit=$?]"
done
for cmd in "openspec list --json" "openspec list --specs" "openspec list --specs --json"; do
  echo; echo "== TTY (script -qec, 60 s): $cmd"
  start=$(date +%s%N)
  timeout 60 script -qec "cd /testbed && $cmd" /dev/null; rc=$?
  echo "[exit=$rc, $(( ($(date +%s%N) - start) / 1000000 )) ms]"
done
# For comparison only: the bare CLI (no CI=1) under a TTY, as before G10-6.
for cmd in "list --specs" "list --specs --json"; do
  echo; echo "== TTY without CI=1 (bare node, 20 s): openspec $cmd"
  timeout 20 script -qec "cd /testbed && OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 $NODE_HOME/bin/node $CLI_JS $cmd" /dev/null; rc=$?
  echo "[exit=$rc]"
done
echo; echo "== tree after (nothing written by list)"; find /openspec -type f | sort
