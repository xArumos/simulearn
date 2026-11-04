#!/usr/bin/env bash
# Evaluate one or more configs (inside WSL). Usage: scripts/evaluate.sh configs/phase0/*.yaml
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
for c in "$@"; do
  echo "=== $c ($(date))"
  python -m src.eval.evaluate --config "$c" --check-repro 32 2>&1 | grep -v -i "warning\|it/s\]"
done
