#!/usr/bin/env bash
# Train + evaluate one config (inside WSL). Usage: scripts/train.sh configs/phase1/<run>.yaml [--resume --run-id ID]
# Runs in the background-friendly way: all output also goes to experiments/<run_id>/train.log (JSON lines).
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
python -m src.train.sft_lora --config "$@" 2>&1 | grep --line-buffered -v -i "warning\|it/s\]\|s/it\]"
