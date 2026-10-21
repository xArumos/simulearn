#!/usr/bin/env bash
source "$(dirname "$0")/env_wsl.sh"
python -m src.eval.evaluate --config configs/phase0/qwen1.5b_strong.yaml --check-repro 32 --run-id 20261015-2106_qwen1.5b_base-strong 2>&1 | grep -v -i "warning\|it/s\]"
bash scripts/evaluate.sh configs/phase0/smol360m_default.yaml configs/phase0/smol360m_strong.yaml
