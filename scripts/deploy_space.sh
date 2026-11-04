#!/usr/bin/env bash
# Build the Space folder from the allowlist (scripts/build_space.py) and upload it.
# Log in yourself first:  hf auth login
# Usage (inside WSL): bash scripts/deploy_space.sh <hf-user>/simulearn-demo [--dry-run]
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
REPO="${1:?usage: deploy_space.sh <hf-user>/simulearn-demo [--dry-run]}"
python scripts/build_space.py --out build/space
if [ "${2:-}" = "--dry-run" ]; then
  echo "Dry run: nothing uploaded."
  exit 0
fi
hf upload "$REPO" build/space . --repo-type space --commit-message "Deploy demo from $(git rev-parse --short HEAD)"
