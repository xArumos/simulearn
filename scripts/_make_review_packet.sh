#!/usr/bin/env bash
# Phase 1 blinded review packet: real vs best untrained vs run 3 vs run 4 (golden set, age 5, test split).
source "$(dirname "$0")/env_wsl.sh"
python -m src.eval.review_packet --bucket age5 --phase phase1 \
  --system baseline=configs/phase0/qwen1.5b_strong.yaml \
  --system run3=configs/phase1/qwen1.5b_lora_ep1.yaml:experiments/20261016-0003_qwen1.5b_lora_ep1/adapter \
  --system run4=configs/phase1/qwen1.5b_lora_ep1_ctx10.yaml:experiments/20261016-1000_qwen1.5b_lora_ep1_ctx10/adapter \
  2>&1 | grep -v -i "warning\|loading weights"
