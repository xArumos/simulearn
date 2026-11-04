#!/usr/bin/env bash
# Live demo (inside WSL). Then open http://localhost:7860 in a Windows browser.
# Usage: bash scripts/demo.sh [--adapter experiments/<run>/adapter] [--port 7860]
set -euo pipefail
source "$(dirname "$0")/env_wsl.sh"
python -m src.demo.chat_demo "$@" 2>&1 | grep --line-buffered -v -i "warning"
