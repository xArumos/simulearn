#!/usr/bin/env bash
# Rebuild data/processed from data/raw/extracted (inside WSL). Usage: scripts/preprocess.sh [configs/data_default.yaml]
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
python -m src.data.preprocess --config "${1:-configs/data_default.yaml}" --verify-ages
python -m pytest -q tests
