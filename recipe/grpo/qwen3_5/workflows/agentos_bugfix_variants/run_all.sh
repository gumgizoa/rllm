#!/bin/bash
# 지침 변형 실험 전체: 워크플로를 하나씩 차례로 돌린다 (각 워크플로는 준 endpoint 전부를 쓴다).
# 순서: 대조(agentos_bugfix 그대로) -> 기준 변형 -> 합친 변형 -> 묶음 1~4. 이미 끝난 shard 는 건너뛴다.
# usage: run_all.sh <run key> <served-model-name> <base-url[,base-url...]> [attempts=3] [workflow ...]
set -uo pipefail
KEY=$1; SERVED=$2; URLS=$3; ATT=${4:-3}; shift 4 2>/dev/null || shift $#
WFS=("$@")
[ ${#WFS[@]} -eq 0 ] && WFS=(agentos_bugfix agentos_bugfix_v0base agentos_bugfix_v5all agentos_bugfix_v1result agentos_bugfix_v2place agentos_bugfix_v3pre agentos_bugfix_v4docs)
D=$(dirname "$(readlink -f "$0")")
for wf in "${WFS[@]}"; do
  bash "$D/run_eval.sh" "$wf" "$KEY" "$SERVED" "$URLS" "$ATT" || echo "[$(date -Is)] $wf stopped with exit $?"
done
