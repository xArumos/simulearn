| Pair (A → B) | mean words | len KS ↓ | short ans | marker gap ↓ | degen ↓ | dist-2 | loss ↓ |
|---|---|---|---|---|---|---|---|
| 20261118-2027_qwen1.5b_lora_ep1_hpg → 20261118-2027_qwen1.5b_lora_ep1_age4_hpg | 4.92 → 3.58 (−1.34) **!** | 0.027 → 0.077 (+0.050) **!** | 22.0% → 25.2% (+3.2 pts) **!** | 0.024 → 0.028 (+0.004) **!** | 0.5% → 0.2% (−0.3 pts) | 0.586 → 0.594 (+0.008) | 2.205 → 2.154 (−0.051) **!** |
| real children (age5 → age4) | 5.10 → 4.16 (−0.94) | – → – | 15.6% → 17.6% (+2.0 pts) | – → – | 0.8% → 1.1% (+0.3 pts) | 0.726 → 0.712 (−0.014) | – → – |

Each cell: A → B (B − A). **!** = the difference is larger than the noise floor (mean words ±0.2, len KS ↓ ±0.005, short ans ±0.015, marker gap ↓ ±0.004, degen ↓ ±0.005, dist-2 ±0.02, loss ↓ ±0.005; rates are fractions, so 0.005 = 0.5 pts). Floors come from re-sampling the same adapter with a second seed (EXPERIMENT_LOG.md, run 4 noise check).
