#!/usr/bin/env bash
# Re-evaluate run 3 and run 4 adapters with a second sampling seed to measure noise.
source "$(dirname "$0")/env_wsl.sh"
for pair in "qwen1.5b_lora_ep1:20261016-0003_qwen1.5b_lora_ep1" "qwen1.5b_lora_ep1_ctx10:20261016-1000_qwen1.5b_lora_ep1_ctx10"; do
  cfg=${pair%%:*}; run=${pair#*:}
  python -m src.eval.evaluate --config configs/phase1/$cfg.yaml --adapter experiments/$run/adapter --seed 4321 \
    --run-id ${run}_evalseed4321 2>&1 | grep -E "mean_words|Error|Traceback"
done
