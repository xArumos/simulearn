# Phase 3 findings: age 4 vs age 5 (findings only)

Run: `20261118-2027_qwen1.5b_lora_ep1_age4_hpg`, the run 3 recipe (Qwen2.5-1.5B LoRA, 1 epoch, 6 context turns) trained on the 48–59-month bucket on HiPerGator. It is compared with `20261118-2027_qwen1.5b_lora_ep1_hpg`, the same recipe on age 5 and the same hardware. Tables: `comparison_hpg.md` (age 4 against real 4-year-olds) and `age5_vs_age4_hpg.md` (the shift between buckets). Regenerate with `scripts/hpg_tables.sh`.

| Shift from age 5 to age 4 | Real children | Model |
|---|---|---|
| Mean words per reply | 5.10 → 4.16 (−0.94) | 4.92 → 3.58 (−1.34) |
| Short answers | 15.6% → 17.6% (+2.0 pts) | 22.0% → 25.2% (+3.2 pts) |
| Distinct-2 | 0.726 → 0.712 | 0.586 → 0.594 |
| Replies containing "I don't know", per 1,000 | 15 → 19 | 70 → 43 |

- **Yes, the age-4 outputs are measurably different**, in the same direction as real children: shorter replies and more short answers.
- **The model overshoots.** It drops 1.34 words where the children drop 0.94. Its length fit within its own bucket (KS 0.077) is worse than the age-5 model's (0.027).
- Other within-bucket numbers: child-marker gap 0.028, degeneration 0.2% (real 1.1%), loss 2.160. Loss is on a different validation set from age 5, so it can't be compared across buckets.
- Gates pass: tests green including the age-4 leakage test, 32/32 reproducible replies, train loss 2.36 vs val 2.16 (no sign of leakage).
- Per CLAUDE.md §8, no per-bucket tuning was started. Whether to tune the age-4 model is the user's call.
