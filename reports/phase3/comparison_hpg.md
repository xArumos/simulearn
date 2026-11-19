| Run | mean words | median | >20 words | len KS ↓ | len W1 ↓ | MSTTR | OOV | rare | filler | short ans | repet | nonstd | silence | marker gap ↓ | degen ↓ | meta | other side | dist-1 | dist-2 | loss ↓ | ppl ↓ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **real children** | 4.16 | 3 | 0.7% | – | – | 0.642 | 2.6% | 9.2% | 15.5% | 17.6% | 7.8% | 4.2% | 6.0% | – | 1.1% | 0.1% | 0.0% | 0.214 | 0.712 | – | – |
| 20261118-2027_qwen1.5b_lora_ep1_age4_hpg | 3.58 | 2 | 1.0% | 0.077 | 0.63 | 0.642 | 0.5% | 4.8% | 11.0% | 25.2% | 4.0% | 4.7% | 6.1% | 0.028 | 0.2% | 0.0% | 0.0% | 0.184 | 0.594 | 2.154 | 8.6 |

n = [1000] contexts per run (val split, bucket age4). ↓ = lower is better. Rates without an arrow should be close to the real-children row.
