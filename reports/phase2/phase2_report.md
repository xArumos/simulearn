# Phase 2 report: QLoRA on a 7B model vs LoRA on 1.5B

All runs here ran on HiPerGator (one RTX PRO 6000 Blackwell GPU, chain `20261118-2027`) with the same data, prompts and decoding, so the numbers compare directly. Full tables: `reports/phase2/comparison.md` (regenerate with `scripts/hpg_tables.sh`). Run details: `experiments/EXPERIMENT_LOG.md`, section "HiPerGator re-run".

## What was done

Phase 1 trained small LoRA adapters on Qwen2.5-1.5B. A LoRA adapter is a small set of extra weights trained on top of a frozen model. Phase 2 asked whether a model about 5x bigger (Qwen2.5-7B) gives more child-like replies. To make 7B fit in less memory we used QLoRA: the base model is stored in 4-bit precision, and only the LoRA adapter trains, in 16-bit. The recipe was otherwise run 3's: rank 16, learning rate 2e-4, 1 epoch, 6 context turns. We then generated one reply for each of the same 1,000 validation contexts and scored them against the real 5-year-olds' replies. All runs passed the sanity gates in CLAUDE.md §9.2. The unit, leakage and masking tests are green, sampling reproduced the same replies on 32 out of 32 rechecks, and no loss is suspiciously low.

## Results

| Metric | Real 5-year-olds | Strong-prompt baseline | Run 3 (1.5B LoRA, 6 turns) | Run 4 (1.5B LoRA, 10 turns) | 7B QLoRA |
|---|---|---|---|---|---|
| Mean / median words per reply | 5.10 / 3 | 5.73 / 3 | 4.92 / 3 | 4.60 / 3 | 3.41 / 2 |
| Length distribution gap (KS, lower is better) | – | 0.043 | **0.027** | 0.046 | 0.142 |
| Child-marker gap (lower is better) | – | 0.032 | 0.024 | **0.022** | 0.036 |
| Degenerate replies | 0.8% | 2.7% | 0.5% | 0.8% | **0.3%** |
| Distinct-2 (variety of word pairs) | 0.726 | 0.731 | 0.586 | 0.599 | **0.629** |
| Replies containing "I don't know", per 1,000 | 15 | 3 | 70 | 59 | **46** |
| Bare "yeah"/"yes" replies, per 1,000 | 56 | 44 | 79 | 80 | 105 |
| Child-reply loss (lower is better) | – | 3.476 | 2.205 | 2.176 | **2.110** |
| Training time / peak GPU memory | – | – | 10 min / 10.5 GB | 13 min / 10.5 GB | 36 min / 17.5 GB |

Loss measures how surprised the model is by the real child's reply; lower means it predicts real children better. Qwen 1.5B and 7B share a tokenizer, so their losses compare directly. KS measures how far apart the reply-length distributions of the model and the real children are.

## What it means

- **The 7B model predicts real children best.** It has the lowest loss at every checkpoint, the fewest broken replies, the most varied wording of the fine-tuned models, and a third fewer "I don't know" replies than run 3.
- **But its replies are too short.** The median is 2 words against the children's 3. It gives almost twice as many bare "yeah"/"yes" answers, and it rarely produces the longer multi-sentence turns real 5-year-olds sometimes do. On length it is further from the children than even the untrained strong-prompt baseline.
- So on the CLAUDE.md §9.1 definition of "better" (closer on length and vocabulary, less degeneration, loss no worse), **it is mixed, not a clear win.** Run 3 and run 4 remain tied for best pending the human ratings.
- Reading samples side by side, the 7B replies are coherent and answer the adult's question more directly than run 3, but they are clipped.

## Comparison: LoRA small vs QLoRA large

| | 1.5B LoRA (run 3 / run 4) | 7B QLoRA |
|---|---|---|
| Wins on | length distribution (run 3), child markers | loss, degeneration, diversity, fewer "I don't know" |
| Loses on | generic replies, diversity | length (too short), child markers |
| Cost on HPG | 10–13 min, 10.5 GB | 36 min, 17.5 GB |
| Fits the local 12 GB card? | yes (ran locally) | not at this batch size (untested with a smaller batch) |

## Recommendation for HiPerGator

1. **Keep the 1.5B LoRA (run 3 recipe) as the default** for the age buckets and the demo until the human ratings say otherwise. It is the best match on reply length, cheap, and fits the local GPU.
2. **Add the 7B QLoRA adapter to the blinded review packet** next to runs 3 and 4. Its lower loss and fewer generic replies may matter more to raters than its shorter length. The ratings should decide, not one metric.
3. If the 7B model rates well, the next step on HiPerGator is one in-grid change to address its short replies. The context-10 variant is the natural candidate, since it reduced generic replies on 1.5B. HiPerGator has room for bf16 LoRA on 7B (no 4-bit), which would also remove quantization as a variable. That is a new experiment and needs the user's go-ahead.
4. Do not try 70B locally (CLAUDE.md §8). On HiPerGator it would only be worth it if the 7B model clearly beats 1.5B in the human ratings.

## For the team deck

- Re-ran the whole pipeline on HiPerGator: 16 jobs, all successful. Fine-tuned results match the local runs (loss agrees to within 0.004).
- Phase 2: a 7B model fine-tuned with 4-bit QLoRA predicts real 5-year-olds best (loss 2.11 vs 2.21) and gives fewer generic "I don't know" replies.
- But the 7B replies are too short (median 2 words vs 3 for real children), so it isn't a clear win yet. Human ratings will break the tie.
- Phase 3: the age-4 model talks measurably shorter than the age-5 model, the same direction as real children, though it overshoots.

## Caveats

- One training run and one sampling seed per configuration. Differences near the noise floor (about ±0.004 marker gap, ±0.5 pts degeneration) are not meaningful.
- All numbers are on the validation split. The test split stays untouched until the end.

Data: CHILDES (MacWhinney, B. (2000). *The CHILDES Project: Tools for Analyzing Talk*. Mahwah, NJ: Lawrence Erlbaum).
