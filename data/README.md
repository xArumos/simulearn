# Data layout

Keep inputs, generated datasets, and model artifacts in separate locations:

- `raw/` — locally supplied corpus archives such as `Gleason.zip` and
  `HSLLD.zip`.
- `processed/childes_statistics/` — age-statistics CSVs.
- `processed/gleason/` — transcript, conversation, and child-caregiver SFT
  exports.
- `processed/sft_baseline/` — train/validation/test splits and frozen
  benchmark.
- `experiments/qwen_lora/` — baseline generations, LoRA adapter, checkpoints,
  and evaluation results.

All of these data/artifact directories are ignored by Git. Obtain and place
corpus archives in `raw/` according to their applicable access and license
terms. Run the notebooks in order from the repository root; outputs are
written to the locations above.
