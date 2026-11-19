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

## Phase 1 — Run 3: 20261016-0003_qwen1.5b_lora_ep1
**Hypothesis:** one epoch matches two (run 1's val loss at 1.0 ep was 2.2045 vs 2.2015 best), at half the cost.
**Config diff vs run 1:** `train.epochs: 2 → 1`.
**Cost:** 40 min train + 1 min eval, peak VRAM 10.5 GB.
**Val loss:** 2.3135 → 2.2487 → 2.214 → **2.2040 (1.0 ep)**. Train loss 2.40.

| Metric | Real | Run 1 | Run 3 |
|---|---|---|---|
| Mean words | 5.10 | 4.45 | **5.01** |
| Length KS ↓ | – | 0.032 | **0.031** |
| Filler / short / repet / nonstd / silence | 13.9 / 15.6 / 7.0 / 5.1 / 5.7% | 11.7 / 20.9 / 3.5 / 6.8 / 4.5% | 13.0 / 21.6 / 4.5 / 6.5 / 5.7% |
| Marker gap ↓ | – | 0.025 | **0.018** |
| Degenerate ↓ | 0.8% | 0.2% | 0.5% |
| Rare words / distinct-2 | 9.0% / 0.726 | 4.7% / 0.638 | 5.7% / 0.611 |
| Child loss ↓ | – | **2.199** | 2.205 |

**Verdict: improved, so run 3 is the new best.** It is closer to the real data on length and child markers, and loss is within 0.3% (treated as "no worse"), at half the cost. Diversity is slightly lower (distinct-2 0.611 vs 0.638).
**Read 20 samples:** about the same quality as run 1, with some nicer matches ("I need pushed." → "pushed."; "what if I don't like them?"). "I don't know" is still overused: 40 vs 38 (run 1) vs 8 (real). Not fixed by fewer epochs.
**Ops note:** the run finished at ~00:45, but the watcher never reported. Its `pgrep -f` pattern matched its own command line, so it waited forever. GPU idle time 00:45–09:59 is not a training problem. Fix: run the training command itself as the background task (as for runs 1–2).
**Next:** run 4 = run 3 + context 10 turns (D6).

## Phase 1 — Run 4: 20261016-1000_qwen1.5b_lora_ep1_ctx10
**Hypothesis (D6, YELLOW):** 10 context turns instead of 6 give the model more to anchor on, so fewer generic replies ("I don't know", "yeah"), with loss no worse.
**Config diff vs run 3:** `data.processed_dir: data/processed_ctx10`, `context_turns: 10` (same children, same splits, same 1,000 eval IDs; 217 vs 149 mean tokens).
**Cost:** 38 min train (paused 10:14–12:13 at checkpoint-473 for the meeting demo, then resumed cleanly) + 1 min eval.
**Val loss:** 2.2708 (0.25 ep) → 2.213 → 2.179 → **2.1692 (1.0 ep)**, vs run 3's 2.2040. Loss is better at every checkpoint.

**Noise check (new):** both run 3 and run 4 were re-evaluated with a second sampling seed (4321), as separate runs `*_evalseed4321`.

| Metric | Real | Run 3 (seed A / B) | Run 4 (seed A / B) |
|---|---|---|---|
| Mean words | 5.10 | 5.01 / 4.85 | 4.51 / 4.39 |
| Length KS ↓ | – | **0.031 / 0.032** | 0.048 / 0.046 |
| Marker gap ↓ | – | 0.018 / 0.022 | 0.021 / 0.022 |
| Degenerate ↓ | 0.8% | 0.5% / 0.9% | 0.8% / 0.2% |
| "I don't know" per 1,000 | 8 | 40 / 49 | **34 / 30** |
| Unique replies per 1,000 | 842 | 741 / 722 | 740 / 747 |
| Child loss ↓ | – | 2.205 | **2.176** |

**Reading:** the marker gap and degeneration differences flip between seeds, so they're noise (about ±0.004 and ±0.5 pts). The length gap (KS ~0.047 vs ~0.031) and "I don't know" (~25% fewer) hold on both seeds.
**Verdict: mixed.** Run 4 is better on loss and on the targeted weakness ("I don't know"), and its replies engage a bit more ("what's that?" → "a fishy."; "what kind of frosting?" → "um chocolate."). Run 3 is better on the length distribution. Run 4 also shows some new disengaged replies ("I don't want to talk. I'm tired."). Neither dominates on the §9.1 definition of "better", so **both go into the blinded review packet** and the human ratings break the tie. Run 3 stays the default "best" until then.
**Next:** review packet (real vs strong baseline vs run 3 vs run 4); runs 5–6 after the user decides.

## Adult-target Gleason pilot — gleason-adult-pilot (2026-10-20)

**Purpose:** separate adult-response pilot, not directly comparable to the child-target Phase 1 runs.
**Data:** 10,898 training examples from 20 child groups; 1,238 validation examples from 2 groups; 1,178 held-out test examples from 2 groups. Child and non-adult turns are context only. Training and generation evaluation used 1,000 deterministic validation examples; the test split was not evaluated.
**Config:** Qwen2.5-1.5B-Instruct, 4-bit NF4 + FP16 LoRA (r=16, alpha=32, all-linear), one epoch, effective batch 16.
**Cost:** 5.26 hours training, peak allocated GPU memory 3.19 GiB. Best checkpoint at step 510.
**Loss:** training 2.4402; best validation loss during training 2.3078; post-training validation target loss 2.5179 (perplexity 12.40).
**Validation generation:** mean 7.63 words (reference 7.58), length Wasserstein 0.683, degeneration 0.1%; reproducibility passed on 32 examples. See `gleason-adult-pilot/metrics.json` for aggregate metrics. Generated samples, adapters, checkpoints, and transcript text are excluded from Git.

---

## HiPerGator re-run — chain 20261118-2027 (2026-11-18)

**What:** the whole Phase 0–2 pipeline plus the Phase 3 age-4 run, re-run on HiPerGator (one RTX PRO 6000 Blackwell, 96 GB) with the same configs, data and decoding as the local runs. All 16 SLURM jobs exited 0. Purpose: one same-hardware comparison for the team and the paper, and the first Phase 2 (7B QLoRA) and Phase 3 (age 4) results.
**Tables:** `reports/phase0/comparison_hpg.md`, `reports/phase1/comparison_hpg.md`, `reports/phase2/comparison.md`, `reports/phase3/`, `reports/hpg/hpg_vs_local.md`, `reports/hpg/smoke.md`. Rebuild all of them with `scripts/hpg_tables.sh` (no GPU).
**Same data:** train 30,314 examples (42 skipped >512 tokens), val 1,000 examples with 8,899 child tokens, identical to the local runs.
**Gates (§9.2), every run below:** pytest green (141 tests, including the real-data leakage test for both buckets and the masking tests); reproducibility 32/32 identical replies for all 11 runs; train loss ≥ val loss and no near-zero loss (train/val: run 3 2.40/2.205, run 4 2.37/2.176, SmolLM2 2.39/2.269, 7B 2.31/2.110, age 4 2.36/2.160). **All pass.**
**"I don't know" counter** used below: replies that *contain* "I don't know" per 1,000 (a looser count than the one in the run 3/4 entries; local runs recounted the same way for comparison). Real children: 15 (age 5).

### Smoke tests (not in the main tables, not counted in the budget)
- `20261118-2027_qwen1.5b_lora_smoke_hpg`: 200 ex, 60 steps, 14 s, peak 6.7 GB. Val loss 2.447 (local 2.45). **Pass.**
- `20261118-2027_qwen7b_qlora_smoke_hpg`: 200 ex, 60 steps, 26 s, peak 12.9 GB. Val loss 2.384. **Pass**, so the 7B run went ahead.

### Phase 0 baselines on HPG
`*_qwen1.5b_base-default_hpg`, `*_qwen1.5b_base-strong_hpg`, `*_smol360m_base-default_hpg`, `*_smol360m_base-strong_hpg`.
Loss matches local to ±0.001 for all four. Ranking unchanged: Qwen + strong prompt is still the strongest baseline (mean words 5.73, len KS 0.043, marker gap 0.032, degenerate 2.7%, loss 3.476).

### Phase 1 on HPG
| Run (HPG) | Local counterpart | Mean words (real 5.10) | Len KS ↓ | Marker gap ↓ | Degen ↓ | dist-2 | "I don't know" | Child loss ↓ | Train time / peak VRAM |
|---|---|---|---|---|---|---|---|---|---|
| `*_qwen1.5b_lora_ep1_hpg` | run 3 | 4.92 | **0.027** | 0.024 | 0.5% | 0.586 | 70 (local 56 / 70) | 2.205 | 10 min / 10.5 GB |
| `*_qwen1.5b_lora_ep1_ctx10_hpg` | run 4 | 4.60 | 0.046 | **0.022** | 0.8% | 0.599 | 59 (local 56 / 45) | **2.176** | 13 min / 10.5 GB |
| `*_smol360m_lora_r16_lr2e-4_hpg` | run 2 | 3.12 | 0.172 | 0.042 | 0.5% | 0.600 | 55 (local 52) | 2.270* | 19 min / 3.4 GB |

\*SmolLM2 loss uses a different tokenizer and can't be compared with Qwen's.
**Verdict: reproduced.** Run 3 vs run 4 is the same trade-off as locally: run 3 has the better length distribution and run 4 the lower loss. The tie still goes to the human ratings. SmolLM2 is still clearly worse on length.
**HPG vs local** (`reports/hpg/hpg_vs_local.md`): child loss matches to ≤0.004 on every run. Hardware (GPU numerics) changes which tokens get sampled, so the generation metrics move like a new sampling seed. Most differences are inside the noise floor or only just outside it (run 3 marker gap +0.005 vs a ±0.004 floor; dist-2 −0.021 to −0.025 vs ±0.02). The one larger shift: SmolLM2 LoRA distinct-2 rose 0.532 → 0.600 while unique replies stayed the same (652 → 647). It does not change any conclusion. Baseline degeneration moved by up to 1.2 pts; at a ~6% rate on 1,000 replies, that is within one binomial standard error (~1.1 pts). The ±0.5 pt floor was measured on fine-tuned runs with ~0.5% degeneration and is too tight for baselines.
**Read 20 samples** (run 3 HPG): same character as locally. Short, child-like, sometimes mirrors the adult's words, some counting and alphabet runs.

### Phase 2 — 20261118-2027_qwen7b_qlora_ep1_hpg
**Hypothesis:** a 4x larger base model (Qwen2.5-7B, 4-bit NF4 QLoRA) with the run 3 recipe is more child-like than LoRA on 1.5B.
**Config diff vs run 3:** `model.name: Qwen/Qwen2.5-7B-Instruct`, `load_in_4bit: true` (eval batch 32 instead of 64).
**Cost:** 36 min train, peak 17.5 GB at batch 8 × accum 2 (would not fit the local 12 GB card at this batch size; not tested locally). Eval 33 s.
**Val loss:** 2.226 (0.25 ep) → 2.160 → 2.124 → **2.110 (1.0 ep)**, below run 3 at every checkpoint (run 3: 2.3135 → 2.2487 → 2.214 → 2.204). Same tokenizer family as Qwen-1.5B, so this is directly comparable: 4.3% lower than run 3 (2.205) and 3.0% lower than run 4 (2.176).

| Metric | Real | Strong baseline (HPG) | Run 3 (HPG) | Run 4 (HPG) | 7B QLoRA |
|---|---|---|---|---|---|
| Mean / median words | 5.10 / 3 | 5.73 / 3 | 4.92 / 3 | 4.60 / 3 | 3.41 / 2 |
| >20 words | 2.4% | 4.3% | 2.7% | 2.1% | 0.9% |
| Len KS ↓ | – | 0.043 | **0.027** | 0.046 | 0.142 |
| Short answers | 15.6% | 16.3% | 22.0% | 24.1% | 26.6% |
| Marker gap ↓ | – | 0.032 | 0.024 | **0.022** | 0.036 |
| Degenerate ↓ | 0.8% | 2.7% | 0.5% | 0.8% | **0.3%** |
| dist-1 / dist-2 | 0.200 / 0.726 | 0.200 / 0.731 | 0.148 / 0.586 | 0.161 / 0.599 | **0.194 / 0.629** |
| "I don't know" / bare "yeah"/"yes" per 1,000 | 15 / 56 | 3 / 44 | 70 / 79 | 59 / 80 | **46** / 105 |
| Child loss ↓ | – | 3.476 | 2.205 | 2.176 | **2.110** |

**Verdict: mixed. Not a new best on the §9.1 definition.** The 7B model is best on loss, degeneration, diversity and the "I don't know" habit. It is clearly worse on the length distribution (KS 0.142, worse than even the strong baseline) and on child markers (gap 0.036). Its replies are too short: median 2 words, more bare "yeah"/"yes" replies (105 vs 56 real), and it almost never produces the longer multi-sentence turns that real 5-year-olds sometimes do.
**Read 22 samples** (side by side with run 3): coherent and on-topic, more often a direct answer to the adult's question than the 1.5B model gives, but clipped to two or three words. Fewer off-topic or disengaged replies than run 3.
**Next:** see the Phase 2 recommendation in `reports/phase2/phase2_report.md`. Add the 7B model to the blinded review packet alongside runs 3 and 4.

### Phase 3 — 20261118-2027_qwen1.5b_lora_ep1_age4_hpg
**Hypothesis:** the run 3 recipe on the age-4 bucket (48–59 months) produces replies that differ from the age-5 model the way real 4-year-olds differ from 5-year-olds.
**Config diff vs run 3:** `data.bucket: age4`, `age_label: 4` (system prompt says 4-year-old). 34,565 train examples (44 skipped >512 tokens), 999 val.
**Cost:** 12 min train, peak 10.5 GB. **Val loss:** 2.274 → 2.208 → 2.169 → **2.160 (1.0 ep)**. Train 2.36. Loss uses a different val set than age 5, so it can't be compared across buckets.

| Shift age 5 → age 4 | Real children | Model (run 3 recipe) |
|---|---|---|
| Mean words | 5.10 → 4.16 (−0.94) | 4.92 → 3.58 (−1.34) |
| Short answers | 15.6% → 17.6% (+2.0 pts) | 22.0% → 25.2% (+3.2 pts) |
| Degenerate | 0.8% → 1.1% | 0.5% → 0.2% |
| dist-2 | 0.726 → 0.712 | 0.586 → 0.594 |
| "I don't know" per 1,000 | 15 → 19 | 70 → 43 |

Within its own bucket the age-4 model has len KS 0.077 (age 5: 0.027), marker gap 0.028 and degeneration 0.2%.
**Finding (report only, no per-bucket tuning):** the age-4 outputs are measurably different from the age-5 outputs, in the same direction as real children (shorter, more short answers). The model overshoots: it drops 1.34 words where children drop 0.94, so its length fit is worse than at age 5. Gates pass (above).
**Adapters:** all on HiPerGator and in the main checkout, not in git. Upload with `scripts/upload_adapters.sh` only after Justin approves.
