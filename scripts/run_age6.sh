#!/usr/bin/env bash
# Build the best 6-year-old (DECISIONS.md D8). Run inside WSL from the project root:
#   bash scripts/run_age6.sh            # everything, in order
#   bash scripts/run_age6.sh data       # only rebuild data/processed_all
# Needs the Eng-NA corpora (incl. OCSC) under data/raw/extracted/Eng-NA/. About 3.5-4 h on an RTX 4070 Ti.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env_wsl.sh

step() { echo; echo "=== $1 ($(date +%H:%M))"; }

step "1/6 preprocess all corpora -> data/processed_all (about 2 min)"
python -m src.data.preprocess --config configs/data_all.yaml > /dev/null
grep -h "Fallback" data/processed_all/age6/stats.md
[ "${1:-}" = "data" ] && exit 0

step "2/6 leakage + masking tests"
python -m pytest -q tests

step "3/6 baselines, no training (about 2 min each)"
bash scripts/evaluate.sh configs/age6/00_base_default.yaml configs/age6/01_base_strong.yaml

step "4/6 smoke test (about 1 min) - stop here if loss does not fall or samples are garbage"
bash scripts/train.sh configs/age6/02_lora_smoke.yaml

step "5/6 A: 6-year-olds only (about 30 min)"
bash scripts/train.sh configs/age6/03_A_age6_only.yaml

step "6/6 B: ages 5-6 (about 75 min), then C: ages 4-6 sample (about 110 min)"
bash scripts/train.sh configs/age6/04_B_ages5to6.yaml
bash scripts/train.sh configs/age6/05_C_ages4to6.yaml

step "compare (all on the same age-6 validation sample)"
python -m src.eval.compare experiments/*_age6_* --out reports/age6/comparison.md || \
  echo "compare failed: check src/eval/compare.py usage and run it by hand"
cat reports/age6/comparison.md 2>/dev/null || true
