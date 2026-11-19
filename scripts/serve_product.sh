#!/usr/bin/env bash
# The educator product (React frontend + FastAPI API, src/product/server.py) on the desktop (WSL2), run on demand.
# Run by scripts/systemd/simulearn-product.service, or by hand:
#   bash scripts/serve_product.sh [extra src.product.server args]
# For a session use scripts/product_up.sh (MongoDB, this unit and the tunnel) and end it with
# scripts/product_down.sh, which frees the GPU. https://simulearn.arumos.dev reaches it through the named tunnel.
#
# Refuses to start when
#   - frontend/dist/index.html is missing (build it: bash scripts/build_frontend.sh);
#   - the Gradio demo is running (simulearn-demo unit active, or something on 127.0.0.1:$DEMO_PORT): both on the
#     12 GB GPU is not supported, so stop it first (bash scripts/demo_down.sh --keep-db);
#   - there is no active admin account in MongoDB (scripts/create_user.py has-admin; accounts are not printed).
# The server itself also refuses to start without MONGODB_URI or a reachable MongoDB (accounts live there).
#
# - Reads the repo's git-ignored .env (MONGODB_URI, MONGODB_DATABASE, SIMULEARN_SAVE_CHATS, SIMULEARN_COOKIE_SECURE).
# - Binds 127.0.0.1 only; the tunnel reaches it, the LAN does not.
#
# Settings (environment variables, all optional):
#   PRODUCT_HOST     default 127.0.0.1
#   PRODUCT_PORT     default 8000
#   PRODUCT_DEVICE   auto | cpu | cuda, default auto
#   PRODUCT_CONFIG   model config passed as --config (default: the server's own default)
#   DEMO_PORT        the demo's port to check, default 7860
#   SIMULEARN_FRONTEND_DIST  where to look for the built frontend, default <repo>/frontend/dist (for tests)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env_wsl.sh"   # venv, HF cache, cd to the repo
# shellcheck source=scripts/_demo_env.sh
. "$PROJECT_ROOT/scripts/_demo_env.sh"
export PYTHONUNBUFFERED=1                              # log lines reach journalctl right away

die() { echo "serve_product.sh: $*" >&2; exit 1; }

DIST="${SIMULEARN_FRONTEND_DIST:-$PROJECT_ROOT/frontend/dist}"
[ -f "$DIST/index.html" ] \
  || die "the frontend is not built ($DIST/index.html is missing). Run: bash scripts/build_frontend.sh"

demo_port="${DEMO_PORT:-7860}"
if { command -v systemctl >/dev/null 2>&1 && systemctl --user is-active --quiet simulearn-demo; } \
   || demo_listening "$demo_port"; then
  die "the Gradio demo is running (simulearn-demo, or something on 127.0.0.1:${demo_port}). The demo and the" \
      "product don't fit on the GPU together. Stop it first: bash scripts/demo_down.sh --keep-db"
fi

python scripts/create_user.py has-admin \
  || die "no active admin account, so nobody could log in and invite educators. Create one first (MongoDB must" \
         "be up): python scripts/create_user.py create <username> --role admin"

config_args=()
[ -n "${PRODUCT_CONFIG:-}" ] && config_args=(--config "$PRODUCT_CONFIG")

exec python -m src.product.server \
  ${config_args[@]+"${config_args[@]}"} \
  --host "${PRODUCT_HOST:-127.0.0.1}" \
  --port "${PRODUCT_PORT:-8000}" \
  --device "${PRODUCT_DEVICE:-auto}" \
  "$@"
