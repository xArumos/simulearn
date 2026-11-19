#!/usr/bin/env bash
# Cloudflare Tunnel to the desktop apps. No router ports opened.
#   bash scripts/tunnel.sh          # quick mode: a random https://<words>.trycloudflare.com URL to the demo
#                                   # (127.0.0.1:$DEMO_PORT), new on every restart
#   bash scripts/tunnel.sh named    # named mode: your own hostnames, from scripts/cloudflared/config.yml. One tunnel
#                                   # carries both: the demo (127.0.0.1:7860) and the product (127.0.0.1:8000).
# The apps run on demand: scripts/demo_up.sh or scripts/product_up.sh starts one of them plus this tunnel (through
# scripts/systemd/simulearn-tunnel.service), and scripts/demo_down.sh / scripts/product_down.sh stop them. Enabling
# the units to start at boot is optional and not recommended (it keeps the model in VRAM). You can also run this
# script by hand. Install and login steps: README.md, "Share the demo with a Cloudflare Tunnel". cloudflared is
# installed system-wide by you (not in the venv); this script never touches Cloudflare credentials, it only starts
# cloudflared.
#
# Refuses to start when
#   - DEMO_PASSWORD is empty (shell first, then the repo's .env) and the tunnel reaches the demo's port (quick mode
#     always; named mode when an ingress rule points at 127.0.0.1:$DEMO_PORT), because the tunnel puts the demo page
#     on the internet;
#   - quick mode and nothing is listening on 127.0.0.1:$DEMO_PORT (start the demo first);
#   - named mode and the config file is missing, or has no http://127.0.0.1:PORT service;
#   - named mode and NONE of the ingress ports is listening. When at least one is, each one that is down only gets a
#     warning, so the demo or the product can each run alone behind the same tunnel (the other hostname shows a
#     Cloudflare error page until its app starts).
#
# Settings (environment variables, all optional):
#   DEMO_PORT            the demo's port, default 7860
#   TUNNEL_CONFIG        named mode config, default scripts/cloudflared/config.yml (git-ignored)
#   TUNNEL_WAIT_SECONDS  wait up to this long for a backend to start listening, default 0 (the systemd unit uses 600)
#   SIMULEARN_ENV_FILE   default <repo>/.env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-quick}"
PORT="${DEMO_PORT:-7860}"
ENV_FILE="${SIMULEARN_ENV_FILE:-$ROOT/.env}"
WAIT="${TUNNEL_WAIT_SECONDS:-0}"

die() { echo "tunnel.sh: $*" >&2; exit 1; }

case "$MODE" in
  quick|named) ;;
  *) die "usage: bash scripts/tunnel.sh [quick|named]  (got '$MODE')" ;;
esac

command -v cloudflared >/dev/null 2>&1 \
  || die "cloudflared is not on PATH. Install it as described in README.md (\"Share the demo with a Cloudflare Tunnel\")."

# shellcheck source=scripts/_demo_env.sh
. "$ROOT/scripts/_demo_env.sh"

# --- which local ports this tunnel reaches -------------------------------------------------------------------------
hosts=(); ports=()
if [ "$MODE" = quick ]; then
  hosts=("the quick tunnel"); ports=("$PORT")
else
  CONFIG="${TUNNEL_CONFIG:-$ROOT/scripts/cloudflared/config.yml}"
  [ -f "$CONFIG" ] \
    || die "named mode needs $CONFIG. Copy scripts/cloudflared/config.yml.example there and fill it in (README.md)."
  while read -r host port; do
    hosts+=("$host"); ports+=("$port")
  done < <(ingress_routes "$CONFIG")
  [ "${#ports[@]}" -gt 0 ] || die "no ingress rule in $CONFIG has a service like http://127.0.0.1:PORT." \
    "Compare it with scripts/cloudflared/config.yml.example."
fi

# DEMO_PASSWORD: a shell variable wins over .env, even when empty (same rule as backend/app/env.py).
for p in "${ports[@]}"; do
  if [ "$p" = "$PORT" ]; then
    demo_password_set "$ENV_FILE" \
      || die "DEMO_PASSWORD is empty. Set it in .env (and restart the demo) before putting the demo on the internet."
    break
  fi
done

# --- wait until at least one backend listens -----------------------------------------------------------------------
any_listening() {
  local p
  for p in "${ports[@]}"; do
    if demo_listening "$p"; then return 0; fi
  done
  return 1
}

waited=0
until any_listening; do
  if [ "$waited" -ge "$WAIT" ]; then
    if [ "$MODE" = quick ]; then
      if [ "$WAIT" -gt 0 ]; then
        die "nothing is listening on http://127.0.0.1:${PORT} after waiting ${WAIT} s. Is the demo running?" \
            "(systemctl --user status simulearn-demo)"
      fi
      die "nothing is listening on http://127.0.0.1:${PORT}. Start the demo first: bash scripts/serve_demo.sh" \
          "(or systemctl --user start simulearn-demo)."
    fi
    die "nothing is listening on any port in $CONFIG (${ports[*]}) after waiting ${WAIT} s. Start the demo" \
        "(scripts/demo_up.sh) or the product (scripts/product_up.sh) first."
  fi
  sleep 1
  waited=$((waited + 1))
done

if [ "$MODE" = quick ]; then
  echo "tunnel.sh: quick tunnel to http://127.0.0.1:${PORT}. Look for the https://...trycloudflare.com line below;" \
       "it changes every time the tunnel restarts. Ctrl+C stops it." >&2
  exec cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${PORT}"
fi

for i in "${!ports[@]}"; do
  if demo_listening "${ports[$i]}"; then
    echo "tunnel.sh: ${hosts[$i]} -> http://127.0.0.1:${ports[$i]} (up)" >&2
  else
    echo "tunnel.sh: WARNING: nothing is listening on 127.0.0.1:${ports[$i]}, so ${hosts[$i]} shows an error page" \
         "until that app starts." >&2
  fi
done
echo "tunnel.sh: named tunnel from ${CONFIG}. Ctrl+C stops it." >&2
exec cloudflared tunnel --no-autoupdate --config "$CONFIG" run
