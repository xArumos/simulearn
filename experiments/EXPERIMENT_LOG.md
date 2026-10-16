# Experiment log

One entry per run: hypothesis, config diff, metrics, observations, next step.
All Phase 0/1 evaluations use the same 1,000-example deterministic sample of the age-5 **validation** split. Decoding: T=0.7, top-p 0.9, 60 new tokens, seed 1234. Full table: `reports/phase0/comparison.md`.

---

## Phase 0 — Baselines (2026-10-15)

| Run | Mean words (real 5.10) | Len KS ↓ | Marker gap ↓ | Degenerate ↓ | Child loss ↓ |
|---|---|---|---|---|---|
| 20261015-2102_qwen1.5b_base-default | 26.51 | 0.749 | 0.156 | 6.8% | 3.845 |
| 20261015-2106_qwen1.5b_base-strong | 5.80 | 0.056 | 0.031 | 3.3% | 3.476 |
| 20261015-2111_smol360m_base-default | 10.07 | 0.287 | 0.047 | 6.4% | 3.123 |
| 20261015-2112_smol360m_base-strong | 8.44 | 0.212 | 0.037 | 4.5% | 3.117 |

**Hypothesis:** untrained instruct models reply longer and more adult-like than real 5-year-olds. **Confirmed, with a caveat.**

**Observations (read 20+ samples per system):**
- **Qwen default prompt:** lectures like a teacher ("Elephants are herbivores, which means..."), plays the caregiver role ("what games do you want to play? maybe we can build a fort"), and gives assistant-style answers. 6.8% meta text, including an absurd "as an AI language model, I cannot discuss..." in reply to a question about tigers.
- **Qwen strong prompt:** length is almost right (median 3, the same as the real replies), so the length metrics look good. The content is still a polite adult in miniature: "Hi Chi! How's it going?", "How about you?", stage directions like "(opens mouth wide)". Child markers are too rare: repetition 2.1% vs 7.0% real, non-standard forms 0.8% vs 5.1%, silence 0.1% vs 5.7%. **This is the strongest baseline.** The fine-tuned model must beat it on loss and child markers, not just on length.
- **SmolLM2:** less assistant-like, but often incoherent ("you can't be arrested, but you can be told to go home and do your homework") and copies context text. It copies the silence-token format from the context, sometimes broken ("SECOND"). Lower loss than Qwen, but that compares different tokenizers, so loss can't be compared across model families.
- Reproducibility gate passed for all four (32 regenerated replies identical).

**Issue fixed:** the first batch run crashed with `CUDA error: device not ready` while computing loss. Converting the full logits to float32 needed several GB and made the Windows (WDDM) driver spill to system RAM and reset. Now only the reply positions are converted, with loss batch size 4. The result is mathematically identical.

**Next:** Phase 1 smoke test (Qwen2.5-1.5B LoRA, 200 examples, 60 steps).

---

## Phase 1 — Run 0 (smoke): 20261015-2120_qwen1.5b_lora_smoke
200 train examples, 60 steps, 35 s, peak 6.7 GB. Val loss (100 ex) 2.54 → 2.45. Masking OK (6.5% of tokens labeled). Samples already child-like; one "no! no! no!..." loop. **Pass**, so the real run went ahead. (Smoke test isn't counted toward the 6-run budget.)

## Phase 1 — Run 1: 20261015-2125_qwen1.5b_lora_r16_lr2e-4
**Hypothesis:** LoRA SFT on age-5 replies makes Qwen2.5-1.5B child-like and beats the baselines.
**Config:** starting config from CLAUDE.md §8 (r=16, alpha=32, dropout 0.05, all-linear, lr 2e-4 cosine, warmup 3%, 2 epochs, eff. batch 16, max len 512, context 6). 30,314 train examples (42 skipped >512 tokens).
**Cost:** 86 min train + 1 min eval, peak VRAM 10.2 GB.
**Val loss** (1,000 ex): 2.325 (0.25 ep) → 2.261 → 2.232 → 2.2045 (1.0 ep) → 2.211 → 2.208 → **2.2015 (1.75 ep, best)** → 2.2035. Epoch 2 adds only ~0.003. Train loss 2.22 ≈ val, so no sign of memorization or leakage.

| Metric | Real | Strong baseline | Run 1 |
|---|---|---|---|
| Mean / median words | 5.10 / 3 | 5.80 / 3 | 4.45 / 3 |
| Length KS ↓ | – | 0.056 | **0.032** |
| Marker gap ↓ | – | 0.031 | **0.025** |
| Degenerate ↓ | 0.8% | 3.3% | **0.2%** |
| Filler / short / repet / nonstd / silence | 13.9 / 15.6 / 7.0 / 5.1 / 5.7% | 12.1 / 16.2 / 2.1 / 0.8 / 0.1% | 11.7 / 20.9 / 3.5 / 6.8 / 4.5% |
| Rare words / distinct-2 | 9.0% / 0.726 | 13.6% / 0.721 | 4.7% / 0.638 |
| Child loss ↓ (ppl) | – | 3.476 (32.3) | **2.199 (9.0)** |

**Verdict: improved** over every baseline on the primary metrics (length distribution, markers, degeneration, loss).
**Read 20 samples:** clearly child-like ("mm nope. <SILENCE FOR 3 SECONDS> mm I can't really tell what these are.", "I gotta call somebody.", "one bri. two bri." mirroring a nonce-word game). The long replies are book retellings and counting, not loops.
**Weaknesses:** too safe and generic. "I don't know" appears 38 times per 1,000 vs 8 real (~5x); short answers 20.9% vs 15.6%; less diverse (distinct-2 0.64 vs 0.73); under-uses rare words (4.7% vs 9.0%); some replies ignore what the adult just said.
**Next:** Run 2 = the same recipe on SmolLM2-360M (model comparison, §8). Then candidates for one-variable changes: epochs 1 (epoch 2 barely helped, and this halves the cost), and context 10 turns (YELLOW; may make replies more specific and less "I don't know").

## Phase 1 — Run 2: 20261015-2300_smol360m_lora_r16_lr2e-4
**Hypothesis:** the same LoRA recipe on the 4x smaller SmolLM2-360M is enough for child-likeness.
**Config diff vs run 1:** model only (HuggingFaceTB/SmolLM2-360M-Instruct).
**Cost:** 43 min train, peak VRAM 3.3 GB.
**Val loss:** 2.401 → 2.292 (1 ep) → **2.2696 (2 ep, best)**, still slowly falling. This can't be compared with Qwen's loss (different tokenizer).

| Metric | Real | Run 1 (Qwen) | Run 2 (SmolLM2) |
|---|---|---|---|
| Mean words | 5.10 | 4.45 | 3.35 |
| Length KS ↓ | – | **0.032** | 0.165 |
| Short answers | 15.6% | 20.9% | 28.8% |
| Repetition / nonstd / silence | 7.0 / 5.1 / 5.7% | 3.5 / 6.8 / 4.5% | 2.9 / 4.4 / 5.7% |
| Marker gap ↓ | – | **0.025** | 0.038 |
| Degenerate ↓ | 0.8% | 0.2% | 0.8% |

**Verdict: worse than run 1.** Run 1 stays the best.
**Read 20 samples:** child-like in tone ("um a toy plane.", "see what you messed up."), but even shorter and safer than Qwen. "yeah" is the reply 114 times per 1,000 (real: 44); "I don't know" 38 (real: 8). It often echoes the adult's last words ("he's getting little.", "on a leaf.") instead of answering.
**Next:** paused at the user's request (GitHub setup). When resuming: Qwen epochs=1, then context 10 turns (YELLOW).
