#!/usr/bin/env bash
# Source this on HiPerGator (login node or inside a SLURM job) to get the project environment:
#   source scripts/env_hpg.sh           # load modules, activate the venv, set HF_HOME, cd to the repo
#   source scripts/env_hpg.sh --setup   # first time only: also create the venv and install requirements.txt
# The HiPerGator counterpart of scripts/env_wsl.sh. The core code (src/) does not depend on either.
#
# Everything site-specific comes from scripts/slurm/hpg.env (git-ignored; copy hpg.env.example).
# The venv and the Hugging Face cache go on /blue, because /home is small and slow on HiPerGator.

export PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HPG_ENV_FILE="${HPG_ENV_FILE:-$PROJECT_ROOT/scripts/slurm/hpg.env}"
if [ -f "$HPG_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$HPG_ENV_FILE"
else
  echo "env_hpg.sh: $HPG_ENV_FILE not found; copy scripts/slurm/hpg.env.example to it and fill it in" >&2
fi

# Modules: space-separated list, e.g. "python/3.12 cuda/12.8". Run `module spider python` to see what exists.
if command -v module >/dev/null 2>&1 && [ -n "${HPG_MODULES:-}" ]; then
  module purge
  # shellcheck disable=SC2086
  module load $HPG_MODULES
fi

HPG_BLUE_DIR="${HPG_BLUE_DIR:-/blue/${HPG_GROUP:-YOUR_GROUP}/$USER}"
export SIMULEARN_VENV="${SIMULEARN_VENV:-$HPG_BLUE_DIR/venvs/simulearn}"
export HF_HOME="${HF_HOME:-$HPG_BLUE_DIR/hf_cache}"
export TOKENIZERS_PARALLELISM=false

if [ "${1:-}" = "--setup" ]; then
  mkdir -p "$(dirname "$SIMULEARN_VENV")" "$HF_HOME"
  if [ ! -f "$SIMULEARN_VENV/bin/activate" ]; then
    python3 -m venv "$SIMULEARN_VENV"
  fi
  source "$SIMULEARN_VENV/bin/activate"
  python -m pip install --upgrade pip uv
  # --torch-backend=auto picks the PyTorch CUDA build that matches the node's driver (same as requirements.txt line 2).
  uv pip install -r "$PROJECT_ROOT/requirements.txt" --torch-backend=auto
fi

if [ -f "$SIMULEARN_VENV/bin/activate" ]; then
  source "$SIMULEARN_VENV/bin/activate"
else
  echo "env_hpg.sh: no venv at $SIMULEARN_VENV; run 'source scripts/env_hpg.sh --setup' once" >&2
fi
cd "$PROJECT_ROOT" || return 1 2>/dev/null || exit 1
