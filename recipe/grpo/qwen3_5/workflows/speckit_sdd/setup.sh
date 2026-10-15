#!/bin/bash
# speckit_sdd sandbox setup (G7-8): colourless jq for the shipped Spec Kit scripts.
#
# The agent's terminal is a PTY, and jq (1.6 in the task images) colours its output on a terminal and
# ignores NO_COLOR, so every script's --json output reached the agent wrapped in escape codes. Spec Kit's
# own setting (an agent app's non-TTY shell) prints plain JSON. A `jq -M` wrapper placed before the real
# jq on PATH restores that without touching the upstream scripts or the stage documents.
set -euo pipefail
WRAPPER=/usr/local/bin/jq
real=$(command -v jq || true)
if [ -z "$real" ]; then
  echo "jq not installed: the scripts use their printf fallback, nothing to wrap"
  exit 0
fi
if [ "$real" = "$WRAPPER" ]; then
  # already a wrapper (warm sandbox) or jq lives here: find the next jq on PATH
  real=$(type -ap jq | grep -vx "$WRAPPER" | head -n 1 || true)
  [ -n "$real" ] || { echo "only $WRAPPER on PATH; leaving it"; exit 0; }
fi
mkdir -p "$(dirname "$WRAPPER")"
printf '#!/bin/sh\nexec %s -M "$@"\n' "$real" > "$WRAPPER"
chmod 755 "$WRAPPER"
echo "jq wrapper: $WRAPPER -> $real -M"
