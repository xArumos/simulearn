#!/usr/bin/env bash
# Rebuild every HiPerGator comparison table from the runs' metrics.json files (no GPU needed).
#
#   scripts/hpg_tables.sh                 # chain stamp 20261118-2027
#   scripts/hpg_tables.sh 20261201-0900   # a later chain
#
# Writes:
#   reports/phase0/comparison_hpg.md   Phase 0 baselines on HPG
#   reports/phase1/comparison_hpg.md   strong baseline + Phase 1 LoRA runs on HPG
#   reports/phase2/comparison.md       strong baseline + best Phase 1 LoRA vs Phase 2 QLoRA-7B, all HPG
#   reports/phase3/comparison_hpg.md   age-4 run with its own real-children row, plus age-5 -> age-4 shift
#   reports/hpg/hpg_vs_local.md        same recipe, local RTX 4070 Ti -> HPG, flagged beyond the noise floor
#   reports/hpg/smoke.md               smoke tests (kept out of the main tables)
# Runs without metrics.json are skipped (paired rows say "no metrics yet"), so re-run this once they land.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
S="${1:-20261118-2027}"
E=experiments
PY="${PYTHON:-python}"
cmp() { "$PY" -m src.eval.compare "$@" > /dev/null; }

cmp $E/${S}_qwen1.5b_base-default_hpg $E/${S}_qwen1.5b_base-strong_hpg \
    $E/${S}_smol360m_base-default_hpg $E/${S}_smol360m_base-strong_hpg \
    --out reports/phase0/comparison_hpg.md
cmp $E/${S}_qwen1.5b_base-strong_hpg $E/${S}_smol360m_base-strong_hpg \
    $E/${S}_qwen1.5b_lora_ep1_hpg $E/${S}_qwen1.5b_lora_ep1_ctx10_hpg $E/${S}_smol360m_lora_r16_lr2e-4_hpg \
    --out reports/phase1/comparison_hpg.md
cmp $E/${S}_qwen1.5b_base-strong_hpg \
    $E/${S}_qwen1.5b_lora_ep1_hpg $E/${S}_qwen1.5b_lora_ep1_ctx10_hpg $E/${S}_qwen7b_qlora_ep1_hpg \
    --out reports/phase2/comparison.md
cmp $E/${S}_qwen1.5b_lora_ep1_age4_hpg --out reports/phase3/comparison_hpg.md
cmp --pair $E/${S}_qwen1.5b_lora_ep1_hpg $E/${S}_qwen1.5b_lora_ep1_age4_hpg --with-reference \
    --out reports/phase3/age5_vs_age4_hpg.md
cmp --pair $E/20261015-2102_qwen1.5b_base-default $E/${S}_qwen1.5b_base-default_hpg \
    --pair $E/20261015-2106_qwen1.5b_base-strong $E/${S}_qwen1.5b_base-strong_hpg \
    --pair $E/20261015-2111_smol360m_base-default $E/${S}_smol360m_base-default_hpg \
    --pair $E/20261015-2112_smol360m_base-strong $E/${S}_smol360m_base-strong_hpg \
    --pair $E/20261015-2120_qwen1.5b_lora_smoke $E/${S}_qwen1.5b_lora_smoke_hpg \
    --pair $E/20261016-0003_qwen1.5b_lora_ep1 $E/${S}_qwen1.5b_lora_ep1_hpg \
    --pair $E/20261016-0003_qwen1.5b_lora_ep1_evalseed4321 $E/${S}_qwen1.5b_lora_ep1_hpg \
    --pair $E/20261016-1000_qwen1.5b_lora_ep1_ctx10 $E/${S}_qwen1.5b_lora_ep1_ctx10_hpg \
    --pair $E/20261016-1000_qwen1.5b_lora_ep1_ctx10_evalseed4321 $E/${S}_qwen1.5b_lora_ep1_ctx10_hpg \
    --pair $E/20261015-2300_smol360m_lora_r16_lr2e-4 $E/${S}_smol360m_lora_r16_lr2e-4_hpg \
    --out reports/hpg/hpg_vs_local.md
cmp $E/${S}_qwen1.5b_lora_smoke_hpg $E/${S}_qwen7b_qlora_smoke_hpg --out reports/hpg/smoke.md
echo "tables written under reports/ for chain $S"
