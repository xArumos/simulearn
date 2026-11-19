| Run | mean words | median | >20 words | len KS ↓ | len W1 ↓ | MSTTR | OOV | rare | filler | short ans | repet | nonstd | silence | marker gap ↓ | degen ↓ | meta | other side | dist-1 | dist-2 | loss ↓ | ppl ↓ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **real children** | 5.38 | 4 | 2.0% | – | – | 0.686 | 1.7% | 7.6% | 14.0% | 18.0% | 6.0% | 6.0% | 7.0% | – | 0.0% | 0.0% | 0.0% | 0.431 | 0.890 | – | – |
| 20261118-2027_qwen1.5b_lora_smoke_hpg | 5.70 | 3 | 4.0% | 0.080 | 0.78 | 0.630 | 0.7% | 5.1% | 8.0% | 16.0% | 5.0% | 1.0% | 0.0% | 0.038 | 1.0% | 0.0% | 0.0% | 0.375 | 0.749 | 2.476 | 11.9 |
| 20261118-2027_qwen7b_qlora_smoke_hpg | 3.98 | 2 | 2.0% | 0.190 | 1.70 | 0.620 | 0.5% | 4.3% | 13.0% | 25.0% | 2.0% | 5.0% | 0.0% | 0.033 | 2.0% | 0.0% | 0.0% | 0.397 | 0.708 | 2.407 | 11.1 |

n = [100] contexts per run (val split, bucket age5). ↓ = lower is better. Rates without an arrow should be close to the real-children row.
