#!/usr/bin/env bash
# openspec_ff sandbox setup (porting/03-decisions.md D-1, D-4, G10-5). Run as root after the documents
# and the forked schema are uploaded, before the agent starts; a non-zero exit stops the rollout.
#
#   1. refuse a repository that carries its own openspec/ (it would be found before /openspec)
#   2. /usr/local/bin/openspec: the CLI from the agent image, non-interactive (CI=1: the agent's terminal
#      is a TTY, and in interactive mode `new change` never exits, gap G10-6), telemetry and update check off
#   3. `cd / && openspec init --tools none` -> /openspec/{config.yaml,specs/,changes/archive/}
#   4. the fork -> /openspec/schemas/spec-driven-sandbox/; config.yaml -> the package's openspec-config.yaml
#      (selects the fork, carries the project context and per-artifact rules, gap G10-7)
#   5. check what the agent will see: root "/" from the repository, the fork listed and valid
set -euo pipefail

REPO=/testbed
NODE_HOME=/opt/rllm/agent/node
CLI_JS=$NODE_HOME/lib/node_modules/@fission-ai/openspec/bin/openspec.js
FORK=spec-driven-sandbox
FORK_STAGED=/opt/rllm/openspec_ff/spec-driven-sandbox   # WorkflowSpec.sandbox_files targets
CONFIG_STAGED=/opt/rllm/openspec_ff/config.yaml
ROOT=/openspec

die() { echo "openspec_ff setup: $*" >&2; exit 1; }

[ -e "$REPO/openspec" ] && die "$REPO/openspec exists: the repository's own OpenSpec root would shadow $ROOT"
[ -x "$NODE_HOME/bin/node" ] || die "no node at $NODE_HOME/bin/node (agent image built without the openspec_ff extra?)"
[ -f "$CLI_JS" ] || die "no openspec CLI at $CLI_JS"
[ -f "$FORK_STAGED/schema.yaml" ] || die "forked schema not uploaded to $FORK_STAGED"
[ -f "$CONFIG_STAGED" ] || die "project config not uploaded to $CONFIG_STAGED"

cat > /usr/local/bin/openspec <<'EOF'
#!/bin/sh
CI=1 OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 exec /opt/rllm/agent/node/bin/node /opt/rllm/agent/node/lib/node_modules/@fission-ai/openspec/bin/openspec.js "$@"
EOF
chmod 755 /usr/local/bin/openspec
version=$(openspec --version) || die "openspec --version failed"

# A reused sandbox must not hand the agent a previous planning tree.
rm -rf "$ROOT"
(cd / && openspec init --tools none) >/dev/null || die "openspec init --tools none failed at /"
[ -f "$ROOT/config.yaml" ] || die "openspec init left no $ROOT/config.yaml"

mkdir -p "$ROOT/schemas"
cp -r "$FORK_STAGED" "$ROOT/schemas/$FORK"
cp "$CONFIG_STAGED" "$ROOT/config.yaml"
rm -rf /opt/rllm/openspec_ff
grep -qx "schema: $FORK" "$ROOT/config.yaml" || die "could not select $FORK in $ROOT/config.yaml"

json() {  # json <js expression over j> : read JSON on stdin, print the expression
  "$NODE_HOME/bin/node" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const j=JSON.parse(s);console.log(eval(process.argv[1]))})' "$1"
}
from=$REPO; [ -d "$from" ] || from=/tmp
root=$(cd "$from" && openspec list --json | json 'j.root && j.root.path') || die "openspec list --json failed from $from"
[ "$root" = "/" ] || die "openspec root from $from is '$root', want '/'"
src=$(cd "$from" && openspec schemas --json | json "(j.find(x => x.name === '$FORK') || {}).source") || die "openspec schemas --json failed"
[ "$src" = "project" ] || die "$FORK not listed as a project schema (got '$src')"
(cd / && openspec schema validate "$FORK" --json) >/dev/null 2>&1 || die "openspec schema validate $FORK failed"
# The agent runs commands in a TTY; a CLI call there must return (G10-6). `script` gives the call a TTY.
if command -v script >/dev/null 2>&1; then
  timeout 60 script -qec "cd $from && openspec new change setup-tty-probe" /dev/null >/dev/null 2>&1 \
    || die "openspec new change did not return under a TTY within 60 s"
  rm -rf "$ROOT/changes/setup-tty-probe"
fi

echo "openspec_ff setup: openspec $version, root /, schema $FORK"
