#!/usr/bin/env bash
# Start a desktop test session: MongoDB, then the demo and the Cloudflare Tunnel (systemd user units), then print
# the public URL and whether chats are saved. End the session with scripts/demo_down.sh, which frees the GPU.
#   bash scripts/demo_up.sh            # MongoDB + demo + tunnel
#   bash scripts/demo_up.sh --no-db    # skip MongoDB (the demo then runs with saving off, unless it is already up)
# Running it again while everything is up is fine: it only re-checks and re-prints.
#
# Needs (one-time setup, README.md "Test sessions on the desktop"): simulearn-demo.service and
# simulearn-tunnel.service copied into ~/.config/systemd/user/, DEMO_PASSWORD in .env, Docker usable without sudo.
# Never prints DEMO_PASSWORD, MONGODB_URI or Cloudflare credentials.
#
# Settings (environment variables, all optional):
#   DEMO_PORT                    default 7860
#   DEMO_UP_WAIT_SECONDS         wait this long for the demo to listen (model loading), default 600
#   DEMO_UP_TUNNEL_WAIT_SECONDS  then wait this long for the tunnel unit / quick URL / saving line, default 30
#   TUNNEL_CONFIG                named tunnel config, default scripts/cloudflared/config.yml (git-ignored)
#   SIMULEARN_ENV_FILE           default <repo>/.env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DEMO_PORT:-7860}"
ENV_FILE="${SIMULEARN_ENV_FILE:-$ROOT/.env}"
WAIT="${DEMO_UP_WAIT_SECONDS:-600}"
TUNNEL_WAIT="${DEMO_UP_TUNNEL_WAIT_SECONDS:-30}"
CONFIG="${TUNNEL_CONFIG:-$ROOT/scripts/cloudflared/config.yml}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DEMO_UNIT=simulearn-demo
TUNNEL_UNIT=simulearn-tunnel

die() { echo "demo_up.sh: $*" >&2; exit 1; }
say() { echo "demo_up.sh: $*"; }

USE_DB=1
for arg in "$@"; do
  case "$arg" in
    --no-db) USE_DB=0 ;;
    -h|--help) sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "usage: bash scripts/demo_up.sh [--no-db]  (got '$arg')" ;;
  esac
done

# shellcheck source=scripts/_demo_env.sh
. "$ROOT/scripts/_demo_env.sh"

# --- checks before anything starts --------------------------------------------------------------------------------
for unit in "$DEMO_UNIT" "$TUNNEL_UNIT"; do
  [ -f "$UNIT_DIR/$unit.service" ] || die "$unit.service is not installed in $UNIT_DIR. Copy it from scripts/systemd/" \
    "and run 'systemctl --user daemon-reload' (README.md, \"Test sessions on the desktop\")."
done
command -v systemctl >/dev/null 2>&1 || die "systemctl is not on PATH. Turn on systemd in WSL (README.md)."

demo_password_set "$ENV_FILE" \
  || die "DEMO_PASSWORD is empty. Set it in .env before putting the demo on the internet."

if [ "$USE_DB" = 1 ]; then
  command -v docker >/dev/null 2>&1 \
    || die "docker is not on PATH. Install Docker (README.md, \"Local MongoDB\") or run with --no-db."
  docker info >/dev/null 2>&1 \
    || die "docker is installed but not usable by $(id -un). Is the Docker engine running, and are you in the" \
           "'docker' group? After 'sudo usermod -aG docker \$USER', close and reopen the terminal. Or run with --no-db."
  docker compose version >/dev/null 2>&1 \
    || die "'docker compose' is missing. Install the Docker Compose plugin, or run with --no-db."
fi

# --- start ---------------------------------------------------------------------------------------------------------
if [ "$USE_DB" = 1 ]; then
  say "starting MongoDB (docker compose up -d)"
  (cd "$ROOT" && docker compose up -d) || die "docker compose up -d failed (see above)."
else
  say "--no-db: not starting MongoDB"
fi

demo_was_active=0; tunnel_was_active=0
systemctl --user is-active --quiet "$DEMO_UNIT" && demo_was_active=1
systemctl --user is-active --quiet "$TUNNEL_UNIT" && tunnel_was_active=1
START="$(date '+%Y-%m-%d %H:%M:%S')"

say "starting $TUNNEL_UNIT (it starts $DEMO_UNIT too)"
systemctl --user start "$TUNNEL_UNIT" "$DEMO_UNIT" \
  || die "systemctl --user start failed. See: systemctl --user status $DEMO_UNIT $TUNNEL_UNIT"

say "waiting up to ${WAIT} s for the demo to load the model and listen on 127.0.0.1:${PORT}"
waited=0
until demo_listening "$PORT"; do
  if [ "$waited" -ge "$WAIT" ]; then
    die "nothing is listening on 127.0.0.1:${PORT} after ${WAIT} s. Check: journalctl --user -u $DEMO_UNIT -n 50" \
        "(raise DEMO_UP_WAIT_SECONDS if the model is still loading)."
  fi
  sleep 1
  waited=$((waited + 1))
done
systemctl --user is-active --quiet "$DEMO_UNIT" \
  || die "something is listening on 127.0.0.1:${PORT}, but $DEMO_UNIT is not running. Stop whatever holds the port" \
         "(e.g. a demo started by hand) and run this again."

waited=0
until systemctl --user is-active --quiet "$TUNNEL_UNIT"; do
  if [ "$waited" -ge "$TUNNEL_WAIT" ]; then
    die "$TUNNEL_UNIT is not active. Check: journalctl --user -u $TUNNEL_UNIT -n 50"
  fi
  sleep 1
  waited=$((waited + 1))
done

# --- report --------------------------------------------------------------------------------------------------------
# journal UNIT WAS_ACTIVE: the latest lines of a unit that was already running; only this start's lines otherwise
# (so an old quick-tunnel URL or an old saving line is never reported as current).
journal() {
  if [ "$2" = 1 ]; then
    journalctl --user -u "$1" -o cat --no-pager -n 500 2>/dev/null || true
  else
    journalctl --user -u "$1" -o cat --no-pager --since "$START" 2>/dev/null || true
  fi
}

saving=""
waited=0
while :; do
  saving="$(journal "$DEMO_UNIT" "$demo_was_active" | grep -o 'Demo: saving [^;]*' | tail -n 1 || true)"
  if [ -n "$saving" ] || [ "$waited" -ge "$TUNNEL_WAIT" ]; then break; fi
  sleep 1
  waited=$((waited + 1))
done

urls=()
if grep -Eq '^[[:space:]]*ExecStart=.*tunnel\.sh[[:space:]]+named' "$UNIT_DIR/$TUNNEL_UNIT.service"; then
  if [ -f "$CONFIG" ]; then
    while IFS= read -r host; do
      [ -n "$host" ] && urls+=("https://$host")
    done < <(sed -nE 's/^[[:space:]]*(-[[:space:]]*)?hostname:[[:space:]]*["'"'"']?([^"'"'"'[:space:]#]+).*/\2/p' "$CONFIG")
    [ "${#urls[@]}" -gt 0 ] || say "WARNING: no 'hostname:' entries in $CONFIG"
  else
    say "WARNING: the tunnel runs in named mode but $CONFIG is missing"
  fi
else
  waited=0
  while :; do
    url="$(journal "$TUNNEL_UNIT" "$tunnel_was_active" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
           | tail -n 1 || true)"
    if [ -n "$url" ]; then urls+=("$url"); break; fi
    [ "$waited" -ge "$TUNNEL_WAIT" ] && { say "WARNING: no trycloudflare URL in the journal yet. Try:" \
      "journalctl --user -u $TUNNEL_UNIT | grep trycloudflare"; break; }
    sleep 1
    waited=$((waited + 1))
  done
fi

echo
echo "Demo is up (local: http://127.0.0.1:${PORT})"
for u in ${urls[@]+"${urls[@]}"}; do
  echo "Public URL: $u"
done
if [ -n "$saving" ]; then
  echo "$saving"
else
  echo "Demo: saving unknown (no 'Demo: saving' line yet; check journalctl --user -u $DEMO_UNIT)"
fi
echo "When the session is over: bash scripts/demo_down.sh (frees the GPU)"
