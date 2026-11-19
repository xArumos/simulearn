#!/usr/bin/env bash
# End a product session started with scripts/product_up.sh: stop the tunnel AND the product (stopping only the
# tunnel leaves the model in VRAM), clear the --no-save setting, then stop MongoDB, then show GPU memory in use.
#   bash scripts/product_down.sh              # tunnel + product + MongoDB
#   bash scripts/product_down.sh --keep-db    # leave MongoDB running (e.g. to run scripts/create_user.py)
# Running it again when everything is already stopped is fine. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PRODUCT_UNIT=simulearn-product
TUNNEL_UNIT=simulearn-tunnel

die() { echo "product_down.sh: $*" >&2; exit 1; }
say() { echo "product_down.sh: $*"; }

KEEP_DB=0
for arg in "$@"; do
  case "$arg" in
    --keep-db) KEEP_DB=1 ;;
    -h|--help) sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "usage: bash scripts/product_down.sh [--keep-db]  (got '$arg')" ;;
  esac
done

status=0

if command -v systemctl >/dev/null 2>&1; then
  # Tunnel first, so visitors lose access before the product goes away; both by name, so the GPU is freed.
  for unit in "$TUNNEL_UNIT" "$PRODUCT_UNIT"; do
    if [ ! -f "$UNIT_DIR/$unit.service" ]; then
      say "$unit.service is not installed in $UNIT_DIR; nothing to stop"
      continue
    fi
    say "stopping $unit"
    if ! systemctl --user stop "$unit"; then
      echo "product_down.sh: could not stop $unit. Check: systemctl --user status $unit" >&2
      status=1
    fi
  done
  systemctl --user unset-environment SIMULEARN_SAVE_CHATS || true
  if systemctl --user is-active --quiet "$PRODUCT_UNIT"; then
    echo "product_down.sh: $PRODUCT_UNIT is still active, so the model may still be in VRAM." >&2
    status=1
  fi
else
  echo "product_down.sh: systemctl is not on PATH; could not stop the product units." >&2
  status=1
fi

if [ "$KEEP_DB" = 1 ]; then
  say "--keep-db: leaving MongoDB running"
elif ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "product_down.sh: docker is missing or not usable by $(id -un), so MongoDB was not stopped. If you were just" \
       "added to the 'docker' group, close and reopen the terminal and run this again." >&2
  status=1
else
  say "stopping MongoDB (docker compose stop)"
  if ! (cd "$ROOT" && docker compose stop); then
    echo "product_down.sh: docker compose stop failed (see above)." >&2
    status=1
  fi
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU memory in use now:"
  nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader \
    || echo "  (nvidia-smi failed)"
else
  echo "GPU memory: nvidia-smi not found, not checked"
fi

[ "$status" = 0 ] && echo "Product is down."
exit "$status"
