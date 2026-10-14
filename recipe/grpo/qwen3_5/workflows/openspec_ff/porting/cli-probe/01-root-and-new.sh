set -u
export PATH=/opt/opsx/node/bin:$PATH OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 HOME=/root
echo "== ldd node"; ldd /opt/opsx/node/bin/node | sed 's/ (0x.*//'
echo "== pre-create root (harness setup)"; mkdir -p /openspec/specs /openspec/changes/archive && printf 'schema: spec-driven\n' > /openspec/config.yaml
cd /testbed
echo "== version"; time openspec --version
echo "== list --json"; openspec list --json
echo "== new change issue"; openspec new change issue; echo "exit=$?"
echo "== status"; openspec status --change issue --json | head -c 900; echo
echo "== instructions proposal (head)"; openspec instructions proposal --change issue --json | head -c 700; echo
echo "== files"; find /openspec -type f | sort; echo "== repo clean?"; git -C /testbed status --porcelain | head; ls -a /root | head -20; ls -a /root/.config 2>/dev/null
