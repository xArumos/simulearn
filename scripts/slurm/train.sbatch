#!/usr/bin/env bash
#SBATCH --job-name=simulearn-train
#SBATCH --nodes=1
#SBATCH --ntasks=1
# Train one LoRA/QLoRA config on one GPU (no generation eval; evaluate.sbatch does that as a follow-up job).
# Account, QOS, partition, GPUs, CPUs, memory and time come from scripts/slurm/hpg.env and are passed
# on the sbatch command line by scripts/slurm/submit_all.sh, so nothing site-specific is hard-coded here.
#
# Usage (normally via submit_all.sh):
#   sbatch [--account ... --qos ... --partition ... --gpus ... --time ...] \
#          --output experiments/<run_id>/slurm-train-%j.out \
#          scripts/slurm/train.sbatch configs/hpg/phase1/<run>.yaml <run_id>
set -euo pipefail
CONFIG="${1:?usage: train.sbatch CONFIG RUN_ID}"
RUN_ID="${2:?usage: train.sbatch CONFIG RUN_ID}"

# SLURM runs a copy of this file, so locate the repo from the submit directory, not from $0.
export PROJECT_ROOT="${PROJECT_ROOT:-$SLURM_SUBMIT_DIR}"
source "$PROJECT_ROOT/scripts/env_hpg.sh"

echo "job ${SLURM_JOB_ID:-?} on $(hostname) at $(date): train $CONFIG -> experiments/$RUN_ID"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true

# Same entry point as scripts/train.sh. --resume picks up the last checkpoint if this job is requeued.
python -m src.train.sft_lora --config "$CONFIG" --run-id "$RUN_ID" --no-eval --resume
