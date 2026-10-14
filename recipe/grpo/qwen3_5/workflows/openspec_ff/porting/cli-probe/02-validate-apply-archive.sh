set -u
export PATH=/opt/opsx/node/bin:$PATH OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1
mkdir -p /openspec/specs /openspec/changes/archive && printf 'schema: spec-driven\n' > /openspec/config.yaml
cd /testbed && openspec new change issue >/dev/null
C=/openspec/changes/issue
printf '## Why\nDecimal ADD loses precision in moto DynamoDB update_item.\n\n## What Changes\n- Use Decimal arithmetic for ADD.\n\n## Capabilities\n### New Capabilities\n- `dynamodb-update-add`: precise numeric ADD\n\n## Impact\n- moto/dynamodb/models/dynamo_type.py\n' > $C/proposal.md
mkdir -p $C/specs/dynamodb-update-add
printf '## ADDED Requirements\n\n### Requirement: Precise numeric ADD\nThe update_item ADD action SHALL add numbers without floating-point error.\n\n#### Scenario: decimal add\n- **WHEN** 100 is ADDed by 0.00001\n- **THEN** the stored value is exactly 100.00001\n' > $C/specs/dynamodb-update-add/spec.md
printf '## 1. Fix\n\n- [ ] 1.1 Use decimal.Decimal in DynamoType.__add__ (verify: run tests/test_dynamodb)\n' > $C/tasks.md
echo "== status after artifacts"; openspec status --change issue --json | python3 -c "import json,sys;d=json.load(sys.stdin);print({a['id']:a['status'] for a in d.get('artifacts',[])}, d.get('isComplete'), d.get('applyRequires'))"
echo "== validate"; openspec validate issue --strict; echo "exit=$?"
echo "== apply instructions"; openspec instructions apply --change issue --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('state',d.get('state'),'progress',d.get('progress'));print('instruction:',str(d.get('instruction'))[:300]);print('guidance:',json.dumps(d.get('operationGuidance') or d.get('context'))[:500])"
sed -i 's/- \[ \] 1.1/- [x] 1.1/' $C/tasks.md
echo "== apply after check"; openspec instructions apply --change issue --json | python3 -c "import json,sys;d=json.load(sys.stdin);print('state',d.get('state'),'progress',d.get('progress'))"
echo "== archive --yes"; openspec archive issue --yes </dev/null; echo "exit=$?"
echo "== tree"; find /openspec -type f | sort; git -C /testbed status --porcelain | head -3; echo "repo-status-lines=$(git -C /testbed status --porcelain | wc -l)"
