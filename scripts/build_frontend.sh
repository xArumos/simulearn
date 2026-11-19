#!/usr/bin/env bash
# Build the product frontend (React + Vite) into frontend/dist, which the product server serves.
#   bash scripts/build_frontend.sh
#
# Needs Node.js 26 (issue #56: nvm in WSL). Installs the exact versions in frontend/package-lock.json
# (npm ci), type-checks, builds, then checks that the built app makes no requests to other hosts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# nvm puts node on PATH only in interactive shells; load it here when node is missing.
if ! command -v node >/dev/null 2>&1; then
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1091
    source "$NVM_DIR/nvm.sh"
  fi
fi
if ! command -v node >/dev/null 2>&1; then
  echo "build_frontend: node not found. Install Node.js 26 (see issue #56) and try again." >&2
  exit 1
fi

major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$major" -lt 26 ]]; then
  echo "build_frontend: warning: Node $(node --version) found; CI uses Node 26." >&2
fi

cd "$ROOT/frontend"
npm ci --no-audit --no-fund
npm run build
npm run check:dist
echo "build_frontend: done -> $ROOT/frontend/dist"
