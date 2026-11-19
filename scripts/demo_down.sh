#!/usr/bin/env bash
# End a desktop test session started with scripts/demo_up.sh: stop the tunnel AND the demo (stopping only the
# tunnel leaves the model in VRAM), then stop MongoDB, then show GPU memory in use.
#   bash scripts/demo_down.sh              # tunnel + demo + MongoDB
#   bash scripts/demo_down.sh --keep-db    # leave MongoDB running
# Running it again when everything is already stopped is fine. Never prints secrets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DEMO_UNIT=simulearn-demo
TUNNEL_UNIT=simulearn-tunnel

die() { echo "demo_down.sh: $*" >&2; exit 1; }
say() { echo "demo_down.sh: $*"; }

KEEP_DB=0
for arg in "$@"; do
  case "$arg" in
    --keep-db) KEEP_DB=1 ;;
    -h|--help) sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "usage: bash scripts/demo_down.sh [--keep-db]  (got '$arg')" ;;
  esac
done

status=0

if command -v systemctl >/dev/null 2>&1; then
  # Tunnel first, so testers lose access before the demo goes away; both by name, so the GPU is freed.
  for unit in "$TUNNEL_UNIT" "$DEMO_UNIT"; do
    if [ ! -f "$UNIT_DIR/$unit.service" ]; then
      say "$unit.service is not installed in $UNIT_DIR; nothing to stop"
      continue
    fi
    say "stopping $unit"
    if ! systemctl --user stop "$unit"; then
      echo "demo_down.sh: could not stop $unit. Check: systemctl --user status $unit" >&2
      status=1
    fi
  done
  if systemctl --user is-active --quiet "$DEMO_UNIT"; then
    echo "demo_down.sh: $DEMO_UNIT is still active, so the model may still be in VRAM." >&2
    status=1
  fi
else
  echo "demo_down.sh: systemctl is not on PATH; could not stop the demo units." >&2
  status=1
fi

if [ "$KEEP_DB" = 1 ]; then
  say "--keep-db: leaving MongoDB running"
elif ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "demo_down.sh: docker is missing or not usable by $(id -un), so MongoDB was not stopped. If you were just" \
       "added to the 'docker' group, close and reopen the terminal and run this again." >&2
  status=1
else
  say "stopping MongoDB (docker compose stop)"
  if ! (cd "$ROOT" && docker compose stop); then
    echo "demo_down.sh: docker compose stop failed (see above)." >&2
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

[ "$status" = 0 ] && echo "Demo is down."
exit "$status"
