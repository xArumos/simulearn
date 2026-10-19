# Building the 6-year-old (DECISIONS.md D8)

**Goal:** the most child-like 6-year-old (72–83 months) we can train from CHILDES.

## Data: every usable North American corpus (`configs/data_all.yaml` → `data/processed_all/`)

16 corpora: the 6 defaults (HSLLD, OCSC, Gelman, Cameron, Warren, MacWhinney) plus Brown, Kuczaj,
Sachs, Gleason, Weist, Braunwald, Bliss, Hall, VanKleeck, Gathercole. Only adult–child conversation;
story retelling and child-only play are left out. Cameron (Eng-AAE) was not in this download.

| Bucket | Ages | Children | Train / Val / Test examples |
|---|---|---|---|
| age6 | 72–83 months | 103 | 20,251 / 1,586 / 1,563 |
| age5to6 | 60–83 months | 262 | 55,727 / 4,985 / 4,987 |
| age4to6 | 48–83 months | 652 | 170,384 / 14,566 / 14,314 |

In the mixed buckets every example's prompt states that child's real age ("You are a 5-year-old…"),
so the model can learn how speech changes with age. All buckets share one child-level split:
a child is in the same split in every bucket (tested: 0 leaks).

## Experiments (`configs/age6/`), all judged on the same 1,000 age-6 validation contexts

| # | Config | Trains on | Why |
|---|---|---|---|
| 0 | `00_base_default` | nothing | Untrained model, plain prompt |
| 1 | `01_base_strong` | nothing | Untrained, "talk like a child" prompt: the bar to beat |
| 2 | `02_lora_smoke` | 200 examples | Quick check that training works |
| A | `03_A_age6_only` | 6-year-olds (20k) | Justin's best recipe (run 3), 6-year-olds only |
| B | `04_B_ages5to6` | 5- and 6-year-olds (56k) | More child speech, still close in age |
| C | `05_C_ages4to6` | 80k sampled from ages 4–6 | All the data; may sound too young |

Same recipe for A, B, C: Qwen2.5-1.5B-Instruct, LoRA r=16, lr 2e-4, 1 epoch, 6 turns of context.
Only the training data changes. B and C validate and early-stop on age-6 data (`eval_bucket: age6`).

## Run it

```bash
bash scripts/run_age6.sh        # inside WSL, ~3.5–4 h on the RTX 4070 Ti
```

## Pick the winner

The best 6-year-old is the run that is closest to the real-children row in
`reports/age6/comparison.md`: length distribution (len KS ↓), child markers (marker gap ↓),
degeneration ↓, "I don't know" rate, and loss. Then blind-rate the top two with the review packet:
`python -m src.eval.review_packet --bucket age6 --phase age6 ...` (see `scripts/_make_review_packet.sh`).
The test split stays untouched until the winner is chosen.
