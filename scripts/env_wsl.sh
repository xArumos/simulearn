#!/usr/bin/env bash
# Source this inside WSL (Ubuntu) to get the project environment:
#   source /mnt/c/Users/justin/dev/simulearn-testing/scripts/env_wsl.sh
# The venv and model cache live on the Linux filesystem because /mnt/c is slow.
# On HiPerGator, use a different env script; the core code does not depend on this one.
export PATH="$HOME/.local/bin:$PATH"
export SIMULEARN_VENV="${SIMULEARN_VENV:-$HOME/venvs/simulearn}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$SIMULEARN_VENV/bin/activate" ]; then
  source "$SIMULEARN_VENV/bin/activate"
fi
cd "$PROJECT_ROOT"
