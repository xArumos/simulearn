#!/usr/bin/env bash
#SBATCH --job-name=simulearn-eval
#SBATCH --nodes=1
#SBATCH --ntasks=1
# Evaluate one config on one GPU: generate replies and compute the CLAUDE.md §9.1 metrics.
# Account, QOS, partition, GPUs, CPUs, memory and time come from scripts/slurm/hpg.env and are passed
# on the sbatch command line by scripts/slurm/submit_all.sh, so nothing site-specific is hard-coded here.
#
# Usage (normally via submit_all.sh):
#   sbatch [...] --output experiments/<run_id>/slurm-eval-%j.out \
#          scripts/slurm/evaluate.sbatch CONFIG RUN_ID [ADAPTER_DIR]
# ADAPTER_DIR is the trained adapter (experiments/<run_id>/adapter) for a fine-tuned run; omit it for a baseline.
set -euo pipefail
CONFIG="${1:?usage: evaluate.sbatch CONFIG RUN_ID [ADAPTER_DIR]}"
RUN_ID="${2:?usage: evaluate.sbatch CONFIG RUN_ID [ADAPTER_DIR]}"
ADAPTER="${3:-}"

export PROJECT_ROOT="${PROJECT_ROOT:-$SLURM_SUBMIT_DIR}"
source "$PROJECT_ROOT/scripts/env_hpg.sh"

echo "job ${SLURM_JOB_ID:-?} on $(hostname) at $(date): evaluate $CONFIG -> experiments/$RUN_ID ${ADAPTER:+(adapter $ADAPTER)}"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true

# Same entry point as scripts/evaluate.sh.
python -m src.eval.evaluate --config "$CONFIG" --run-id "$RUN_ID" --check-repro 32 ${ADAPTER:+--adapter "$ADAPTER"}
