#!/usr/bin/env bash
# Cloudflare Tunnel to the always-on desktop demo (scripts/serve_demo.sh on 127.0.0.1:7860). No router ports opened.
#   bash scripts/tunnel.sh          # quick mode: random https://<words>.trycloudflare.com URL, new on every restart
#   bash scripts/tunnel.sh named    # named mode: your own hostname, from scripts/cloudflared/config.yml
# Run by scripts/systemd/simulearn-tunnel.service, or by hand. Install and login steps: README.md, "Share the demo
# with a Cloudflare Tunnel". cloudflared is installed system-wide by you (not in the venv); this script never
# touches Cloudflare credentials, it only starts cloudflared.
#
# Refuses to start when
#   - DEMO_PASSWORD is empty (shell first, then the repo's .env), because the tunnel puts the page on the internet;
#   - nothing is listening on 127.0.0.1:$DEMO_PORT (start the demo first);
#   - named mode and the config file is missing.
#
# Settings (environment variables, all optional):
#   DEMO_PORT            default 7860
#   TUNNEL_CONFIG        named mode config, default scripts/cloudflared/config.yml (git-ignored)
#   TUNNEL_WAIT_SECONDS  wait up to this long for the demo to start listening, default 0 (the systemd unit uses 600)
#   SIMULEARN_ENV_FILE   default <repo>/.env
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-quick}"
PORT="${DEMO_PORT:-7860}"
LOCAL_URL="http://127.0.0.1:${PORT}"
ENV_FILE="${SIMULEARN_ENV_FILE:-$ROOT/.env}"
WAIT="${TUNNEL_WAIT_SECONDS:-0}"

die() { echo "tunnel.sh: $*" >&2; exit 1; }

case "$MODE" in
  quick|named) ;;
  *) die "usage: bash scripts/tunnel.sh [quick|named]  (got '$MODE')" ;;
esac

command -v cloudflared >/dev/null 2>&1 \
  || die "cloudflared is not on PATH. Install it as described in README.md (\"Share the demo with a Cloudflare Tunnel\")."

# DEMO_PASSWORD: a shell variable wins over .env, even when empty (same rule as backend/app/env.py).
# shellcheck source=scripts/_demo_env.sh
. "$ROOT/scripts/_demo_env.sh"
demo_password_set "$ENV_FILE" \
  || die "DEMO_PASSWORD is empty. Set it in .env (and restart the demo) before putting the demo on the internet."

waited=0
until demo_listening "$PORT"; do
  if [ "$waited" -ge "$WAIT" ]; then
    if [ "$WAIT" -gt 0 ]; then
      die "nothing is listening on ${LOCAL_URL} after waiting ${WAIT} s. Is the demo running? (systemctl --user status simulearn-demo)"
    fi
    die "nothing is listening on ${LOCAL_URL}. Start the demo first: bash scripts/serve_demo.sh (or systemctl --user start simulearn-demo)."
  fi
  sleep 1
  waited=$((waited + 1))
done

if [ "$MODE" = quick ]; then
  echo "tunnel.sh: quick tunnel to ${LOCAL_URL}. Look for the https://...trycloudflare.com line below;" \
       "it changes every time the tunnel restarts. Ctrl+C stops it." >&2
  exec cloudflared tunnel --no-autoupdate --url "$LOCAL_URL"
fi

CONFIG="${TUNNEL_CONFIG:-$ROOT/scripts/cloudflared/config.yml}"
[ -f "$CONFIG" ] || die "named mode needs $CONFIG. Copy scripts/cloudflared/config.yml.example there and fill it in (README.md)."
echo "tunnel.sh: named tunnel from ${CONFIG} to ${LOCAL_URL}. Ctrl+C stops it." >&2
exec cloudflared tunnel --no-autoupdate --config "$CONFIG" run
