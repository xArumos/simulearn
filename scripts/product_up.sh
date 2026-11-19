#!/usr/bin/env bash
# Start the educator product on the desktop: MongoDB, then the product (systemd user unit simulearn-product), then
# the named Cloudflare Tunnel, then print the product URL(s) and whether practice conversations are saved. End it
# with scripts/product_down.sh, which frees the GPU.
#   bash scripts/product_up.sh             # MongoDB + product + tunnel, conversations saved to MongoDB
#   bash scripts/product_up.sh --no-save   # the same, but conversations stay in memory (SIMULEARN_SAVE_CHATS=0)
# MongoDB always starts: accounts live there, so the product can't run without it.
# Running it again while everything is up is fine: it only re-checks and re-prints.
#
# Needs (one-time setup, README.md "Run the product"): simulearn-product.service and simulearn-tunnel.service (named
# mode) in ~/.config/systemd/user/, a product hostname in scripts/cloudflared/config.yml, Docker usable without sudo,
# the built frontend and an admin account (scripts/serve_product.sh checks those two). Never prints MONGODB_URI,
# passwords or Cloudflare credentials.
#
# Settings (environment variables, all optional):
#   PRODUCT_PORT                   default 8000
#   DEMO_PORT                      the demo's port, checked so both don't share the GPU, default 7860
#   PRODUCT_UP_WAIT_SECONDS        wait this long for the product to listen (model loading), default 600
#   PRODUCT_UP_TUNNEL_WAIT_SECONDS then wait this long for the tunnel unit / saving line, default 30
#   TUNNEL_CONFIG                  named tunnel config, default scripts/cloudflared/config.yml (git-ignored)
#   SIMULEARN_ENV_FILE             default <repo>/.env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PRODUCT_PORT:-8000}"
DEMO_PORT_="${DEMO_PORT:-7860}"
ENV_FILE="${SIMULEARN_ENV_FILE:-$ROOT/.env}"
WAIT="${PRODUCT_UP_WAIT_SECONDS:-600}"
TUNNEL_WAIT="${PRODUCT_UP_TUNNEL_WAIT_SECONDS:-30}"
CONFIG="${TUNNEL_CONFIG:-$ROOT/scripts/cloudflared/config.yml}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PRODUCT_UNIT=simulearn-product
TUNNEL_UNIT=simulearn-tunnel
DEMO_UNIT=simulearn-demo

die() { echo "product_up.sh: $*" >&2; exit 1; }
say() { echo "product_up.sh: $*"; }

SAVE=1
for arg in "$@"; do
  case "$arg" in
    --no-save) SAVE=0 ;;
    -h|--help) sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "usage: bash scripts/product_up.sh [--no-save]  (got '$arg')" ;;
  esac
done

# shellcheck source=scripts/_demo_env.sh
. "$ROOT/scripts/_demo_env.sh"

# --- checks before anything starts --------------------------------------------------------------------------------
for unit in "$PRODUCT_UNIT" "$TUNNEL_UNIT"; do
  [ -f "$UNIT_DIR/$unit.service" ] || die "$unit.service is not installed in $UNIT_DIR. Copy it from scripts/systemd/" \
    "and run 'systemctl --user daemon-reload' (README.md, \"Run the product\")."
done
command -v systemctl >/dev/null 2>&1 || die "systemctl is not on PATH. Turn on systemd in WSL (README.md)."

grep -Eq '^[[:space:]]*ExecStart=.*tunnel\.sh[[:space:]]+named' "$UNIT_DIR/$TUNNEL_UNIT.service" \
  || die "$TUNNEL_UNIT.service runs a quick tunnel, which only reaches the demo. Make its ExecStart end in" \
         "'tunnel.sh named' and run 'systemctl --user daemon-reload' (README.md, \"Run the product\")."
if grep -Eq '^[[:space:]]*(Wants|Requires|BindsTo)=.*simulearn-demo' "$UNIT_DIR/$TUNNEL_UNIT.service"; then
  die "the installed $TUNNEL_UNIT.service still starts the demo too (Wants=simulearn-demo.service), and the demo" \
      "and the product don't fit on the GPU together. Copy the new scripts/systemd/$TUNNEL_UNIT.service to" \
      "$UNIT_DIR/, put 'named' back at the end of ExecStart, and run 'systemctl --user daemon-reload'."
fi

[ -f "$CONFIG" ] || die "$CONFIG is missing. Set up the named tunnel first (README.md, \"Share the demo with a" \
  "Cloudflare Tunnel\")."
urls=()
while read -r host port; do
  if [ "$port" = "$PORT" ] && [ "$host" != "*" ]; then urls+=("https://$host"); fi
done < <(ingress_routes "$CONFIG")
[ "${#urls[@]}" -gt 0 ] || die "no ingress rule in $CONFIG sends a hostname to http://127.0.0.1:${PORT}. Add one" \
  "above the http_status:404 catch-all (see scripts/cloudflared/config.yml.example and README.md, \"Run the product\")."

if env_flag_off SIMULEARN_COOKIE_SECURE "$ENV_FILE"; then
  die "SIMULEARN_COOKIE_SECURE is off (shell or .env). That is for testing on http://127.0.0.1 only; behind the" \
      "tunnel the login cookie must stay secure. Remove it from .env (and the shell) and run this again."
fi

command -v docker >/dev/null 2>&1 \
  || die "docker is not on PATH. Install Docker (README.md, \"Local MongoDB\"); the product needs MongoDB for accounts."
docker info >/dev/null 2>&1 \
  || die "docker is installed but not usable by $(id -un). Is the Docker engine running, and are you in the" \
         "'docker' group? After 'sudo usermod -aG docker \$USER', close and reopen the terminal."
docker compose version >/dev/null 2>&1 || die "'docker compose' is missing. Install the Docker Compose plugin."

if systemctl --user is-active --quiet "$DEMO_UNIT" || demo_listening "$DEMO_PORT_"; then
  die "the Gradio demo is running ($DEMO_UNIT, or something on 127.0.0.1:${DEMO_PORT_}). The demo and the product" \
      "don't fit on the GPU together. Stop it first: bash scripts/demo_down.sh --keep-db"
fi

# --- start ---------------------------------------------------------------------------------------------------------
say "starting MongoDB (docker compose up -d)"
(cd "$ROOT" && docker compose up -d) || die "docker compose up -d failed (see above)."

product_was_active=0; tunnel_was_active=0
systemctl --user is-active --quiet "$PRODUCT_UNIT" && product_was_active=1
systemctl --user is-active --quiet "$TUNNEL_UNIT" && tunnel_was_active=1

# The unit reads SIMULEARN_SAVE_CHATS from the user manager's environment (it wins over .env); clear it otherwise,
# so .env decides.
if [ "$SAVE" = 0 ]; then
  systemctl --user set-environment SIMULEARN_SAVE_CHATS=0
else
  systemctl --user unset-environment SIMULEARN_SAVE_CHATS
fi
if [ "$product_was_active" = 1 ]; then
  say "$PRODUCT_UNIT was already running; it keeps its saving setting until restarted (product_down.sh, then" \
      "product_up.sh)"
fi
START="$(date '+%Y-%m-%d %H:%M:%S')"

say "starting $PRODUCT_UNIT"
systemctl --user start "$PRODUCT_UNIT" \
  || die "systemctl --user start $PRODUCT_UNIT failed. See: systemctl --user status $PRODUCT_UNIT"

# journal UNIT WAS_ACTIVE: the latest lines of a unit that was already running; only this start's lines otherwise
# (so an old saving line or an old refusal is never reported as current).
journal() {
  if [ "$2" = 1 ]; then
    journalctl --user -u "$1" -o cat --no-pager -n 500 2>/dev/null || true
  else
    journalctl --user -u "$1" -o cat --no-pager --since "$START" 2>/dev/null || true
  fi
}

say "waiting up to ${WAIT} s for the product to load the model and listen on 127.0.0.1:${PORT}"
waited=0
until demo_listening "$PORT"; do
  # serve_product.sh explains every refusal on one 'serve_product.sh: ...' line; show it instead of waiting.
  refusal="$(journal "$PRODUCT_UNIT" 0 | grep -m 1 '^serve_product\.sh: ' || true)"
  if [ -n "$refusal" ]; then
    systemctl --user stop "$PRODUCT_UNIT" >/dev/null 2>&1 || true
    die "$PRODUCT_UNIT refused to start. ${refusal}"
  fi
  if [ "$waited" -ge "$WAIT" ]; then
    die "nothing is listening on 127.0.0.1:${PORT} after ${WAIT} s. Check: journalctl --user -u $PRODUCT_UNIT -n 50" \
        "(raise PRODUCT_UP_WAIT_SECONDS if the model is still loading)."
  fi
  sleep 1
  waited=$((waited + 1))
done
systemctl --user is-active --quiet "$PRODUCT_UNIT" \
  || die "something is listening on 127.0.0.1:${PORT}, but $PRODUCT_UNIT is not running. Stop whatever holds the" \
         "port (e.g. a server started by hand) and run this again."

say "starting $TUNNEL_UNIT"
systemctl --user start "$TUNNEL_UNIT" \
  || die "systemctl --user start $TUNNEL_UNIT failed. See: systemctl --user status $TUNNEL_UNIT"
waited=0
until systemctl --user is-active --quiet "$TUNNEL_UNIT"; do
  if [ "$waited" -ge "$TUNNEL_WAIT" ]; then
    die "$TUNNEL_UNIT is not active. Check: journalctl --user -u $TUNNEL_UNIT -n 50"
  fi
  sleep 1
  waited=$((waited + 1))
done

# --- report --------------------------------------------------------------------------------------------------------
saving=""
waited=0
while :; do
  saving="$(journal "$PRODUCT_UNIT" "$product_was_active" | grep -o 'SimuLearn: saving [^;]*' | tail -n 1 || true)"
  if [ -n "$saving" ] || [ "$waited" -ge "$TUNNEL_WAIT" ]; then break; fi
  sleep 1
  waited=$((waited + 1))
done

echo
echo "Product is up (local: http://127.0.0.1:${PORT})"
for u in "${urls[@]}"; do
  echo "Public URL: $u"
done
if [ -n "$saving" ]; then
  echo "$saving"
else
  echo "SimuLearn: saving unknown (no 'SimuLearn: saving' line yet; check journalctl --user -u $PRODUCT_UNIT)"
fi
[ "$tunnel_was_active" = 1 ] && echo "(The tunnel was already running; it serves every hostname in $CONFIG.)"
echo "Team only for now (DECISIONS.md D12). When the session is over: bash scripts/product_down.sh (frees the GPU)"
