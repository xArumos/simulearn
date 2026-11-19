#!/usr/bin/env bash
# Demo server for the desktop (WSL2), run on demand. Run by scripts/systemd/simulearn-demo.service, or by hand:
#   bash scripts/serve_demo.sh [extra chat_demo args, e.g. --selftest]
# For a test session use scripts/demo_up.sh (starts this unit, the tunnel and MongoDB) and end it with
# scripts/demo_down.sh, which frees the GPU. Enabling the unit to start at boot is optional and not recommended
# (it keeps the model in VRAM).
#
# - Reads the repo's git-ignored .env (DEMO_PASSWORD, MONGODB_URI, MONGODB_DATABASE) through backend/app/env.py.
# - Refuses to start without DEMO_PASSWORD, because the tunnel makes the page reachable from outside.
# - Loads every age adapter in configs/demo.yaml whose folder exists under experiments/.
# - Binds 127.0.0.1 only (the tunnel reaches it; the LAN does not). Windows browsers on the same PC still reach
#   http://localhost:7860 through WSL's localhost forwarding.
# - Uses the GPU when one is visible, else the CPU (CUDA_VISIBLE_DEVICES="" forces the CPU).
# - Starts without MongoDB (prints that saving is OFF), like scripts/demo.sh.
#
# Settings (environment variables, all optional):
#   DEMO_HOST    default 127.0.0.1
#   DEMO_PORT    default 7860
#   DEMO_DEVICE  auto | cpu | cuda, default auto
#   DEMO_CONFIG  default configs/demo.yaml
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env_wsl.sh"   # venv, HF cache, cd to the repo
export PYTHONUNBUFFERED=1                              # log lines reach journalctl right away

exec python -m src.demo.chat_demo \
  --config "${DEMO_CONFIG:-configs/demo.yaml}" \
  --host "${DEMO_HOST:-127.0.0.1}" \
  --port "${DEMO_PORT:-7860}" \
  --device "${DEMO_DEVICE:-auto}" \
  --require-password \
  "$@"
