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


## Age 6 — CPU build: age6_A_smol360m_cpu (2026-10-27, DECISIONS.md D9)
**Hypothesis:** LoRA SFT on real 6-year-old replies makes SmolLM2-360M child-like for age 6 and beats its untrained baselines.
**Config:** SmolLM2-360M-Instruct, LoRA r=16/alpha 32, lr 2e-4 cosine, 1 epoch, effective batch 16, 6-turn context, `data/processed_all/age6`, **3,200-example random sample** (3,189 used). CPU only (2 cores, 7 GB RAM): fp32, batch 2 x accum 8, gradient checkpointing.
**Cost:** 200 steps at ~54 s/step, ~3 h 15 min of training in two sessions (resumed from checkpoint-98). Peak RAM ~3.5 GB.
**Val loss (200 age-6 examples):** 2.287 (step 49) → 2.168 → 2.143 → **2.139** (step 200).

Standard evaluation: same 1,000-example age-6 validation sample, T=0.7, top-p 0.9, 60 tokens, seed 1234. Full table: `reports/age6/comparison_cpu.md`.

| Metric | Real 6-year-olds | SmolLM2 default prompt | SmolLM2 strong prompt | **Trained (CPU)** |
|---|---|---|---|---|
| Mean / median words | 5.37 / 3 | 8.93 / 6 | 8.27 / 5 | 3.61 / 2 |
| Length KS ↓ | – | 0.249 | 0.186 | **0.152** |
| Degenerate ↓ | 0.1% | 4.2% | 5.5% | **1.9%** |
| Short answers | 15.5% | 8.9% | 10.6% | 33.0% |
| Silence tokens | 12.2% | 6.6% | 8.1% | 7.2% |
| Marker gap ↓ | – | **0.034** | **0.034** | 0.046 |
| distinct-2 | 0.663 | 0.520 | 0.484 | **0.544** |
| Child loss ↓ (ppl) | – | 2.766 (15.9) | 2.753 (15.7) | **2.109 (8.2)** |

Reproducibility: 32 regenerated replies identical. No meta/assistant text (0.0%).
**Verdict: improved over both baselines** on loss, length distribution, degeneration and diversity. **Worse on the child-marker gap**, driven by too many short answers (33% vs 15.5%).
**Read 20 samples:** clearly child-like ("um chocolate.", counting "fourteen. five. six.", "pite?" for a nonce word, silence tokens before replies). Weaknesses: replies too short and generic: "yeah." is the reply 40 times in 300 and "I don't know" 47 per 1,000 vs 27 real; sometimes answers yes/no where the child gave a real answer. The same pattern run 2 showed for SmolLM2 at age 5.
**Next:** this is the working age-6 model until the GPU runs. Run Qwen2.5-1.5B A/B/C on all 20k age-6 examples (`scripts/run_age6.sh`); age-5 results suggest Qwen fixes most of the shortness.


## Age 6 — CPU round 2: age6_A_smol360m_cpu_r2 (2026-10-30, D9)
**Hypothesis:** continuing the round-1 adapter on 3,200 age-6 training examples it has not seen lowers loss and reduces the "yeah."/short-answer overuse.
**Config diff vs round 1:** starts from the round-1 adapter (`model.adapter`); `data.exclude_sample: {n: 3200, seed: 42}` skips round 1's examples; `sample_seed: 43`. Everything else is the same (lr 2e-4 cosine, 1 epoch, 200 steps, CPU).
**Cost:** ~3 h 25 min in two chunks (resumed from checkpoint-98).
**Val loss (200-example sample, seed 43; not the same sample as round 1, so not directly comparable):** 2.032 → 2.010 → 1.981 → **1.978**.

Standard evaluation (same 1,000 age-6 validation contexts and decoding as round 1):

| Metric | Real | Round 1 | **Round 2** |
|---|---|---|---|
| Mean / median words | 5.37 / 3 | 3.61 / 2 | 3.43 / 2 |
| Length KS ↓ | – | **0.152** | 0.165 |
| Degenerate ↓ | 0.1% | 1.9% | **1.6%** |
| Short answers | 15.5% | 33.0% | **31.2%** |
| Rare words | 9.0% | 6.5% | **7.1%** |
| Silence tokens | 12.2% | 7.2% | **8.9%** |
| Marker gap ↓ | – | 0.046 | **0.044** |
| distinct-1 / distinct-2 | 0.194 / 0.663 | 0.180 / 0.544 | **0.189** / 0.544 |
| Child loss ↓ (ppl) | – | 2.109 (8.2) | **2.035 (7.7)** |

**Read 20 samples:** child-like, with somewhat more content than round 1 ("um I like... I like to play with little stuffed animals.", "I put the food in their mouth.", "well I just build blocks."). Bare "yeah." / "I can." / "me." still common.
**Verdict: improved (mostly).** Better on loss, degeneration, short answers, vocabulary, silence rate and marker gap; worse on the length distribution (replies a bit shorter, KS +0.013, larger than the ~±0.005 seed noise). Round 2 becomes the working 6-year-old.
**Next:** round 3, same recipe on another 3,200 unseen examples (`exclude_sample` now takes a list so rounds 1 and 2 are both skipped).


## Age 6 — CPU round 3: age6_A_smol360m_cpu_r3 (2026-10-31, D9)
**Hypothesis:** continuing the round-2 adapter on another 3,200 unseen age-6 examples lowers loss further without making replies shorter.
**Config diff vs round 2:** starts from the round-2 adapter; `exclude_sample` is a list (rounds 1 and 2) so all 3,190 examples are new; `sample_seed: 44`. ~3 h 20 min in two chunks.

| Metric (same 1,000 val contexts) | Real | Round 2 (best) | Round 3 |
|---|---|---|---|
| Mean / median words | 5.37 / 3 | 3.43 / 2 | 3.47 / 2 |
| Length KS ↓ | – | 0.165 | **0.159** |
| Degenerate ↓ | 0.1% | 1.6% | **1.2%** |
| Short answers | 15.5% | **31.2%** | 32.1% |
| Rare words | 9.0% | **7.1%** | 5.4% |
| Silence tokens | 12.2% | **8.9%** | 5.8% |
| Marker gap ↓ | – | **0.044** | 0.049 |
| Child loss ↓ (ppl) | – | 2.035 (7.7) | **2.003 (7.4)** |

**Read 20 samples:** child-like and short ("two bags.", "the lake.", "he's a prince."); more bare "okay."/"um." and one "um, um, um..." loop.
**Verdict: mixed → counted as not improved (1 of 3).** Better loss, degeneration and length; worse vocabulary, silence rate and marker gap. Gains are shrinking (loss −0.074 in round 2, −0.032 in round 3). Round 2 stays the working model.
**Next:** round 4 = round 2 + another unseen chunk at lr 1e-4 (one change: learning rate).


## Age 6 — CPU round 4: age6_A_smol360m_cpu_r4_lr1e-4 (2026-10-31, D9)
**Hypothesis:** continuing the round-2 adapter on 3,200 unseen examples at a lower learning rate (1e-4) keeps round 3's lower loss without losing silence tokens, rare words and child markers.
**Config diff vs round 3:** starts from round 2 (the best), `lr: 1e-4`, rounds 1-3 excluded (9,600 seen), `sample_seed: 45`. ~3 h 20 min; best checkpoint at step 147 (val loss 2.000 on its own 200-example sample).

| Metric (same 1,000 val contexts) | Real | Round 2 (best) | Round 3 | Round 4 |
|---|---|---|---|---|
| Mean words | 5.37 | 3.43 | 3.47 | 3.32 |
| Length KS ↓ | – | 0.165 | **0.159** | 0.162 |
| Degenerate ↓ | 0.1% | 1.6% | **1.2%** | 1.3% |
| Short answers | 15.5% | 31.2% | 32.1% | **29.6%** |
| Rare words | 9.0% | **7.1%** | 5.4% | 5.1% |
| Out-of-vocabulary | 2.4% | **2.2%** | 2.1% | 1.2% |
| Silence tokens | 12.2% | **8.9%** | 5.8% | 8.3% |
| Marker gap ↓ | – | **0.044** | 0.049 | **0.044** |
| Child loss ↓ | – | 2.035 | **2.003** | 2.010 |

**Read 20 samples:** the most content-rich of the CPU runs ("and I play with the animals that are in the zoo.", "um. I put it in a bowl and I put it in a cup.", "I like pink ones."); no loops in the 20. Still many one-word replies.
**Verdict: mixed → not improved (2 of 3).** The lower learning rate kept silence tokens and the marker gap where round 2 had them (fixing round 3's losses there), with lower loss and fewer short answers, but replies got slightly shorter and the vocabulary narrower.
**Decision: stop the CPU rounds here** (DECISIONS D9). Four rounds moved loss 2.109 → ~2.00 but reply length never moved (~3.4 words vs 5.4 real). The 360M model looks like the limit. Round 2 stays the working 6-year-old; the real upgrade is Qwen2.5-1.5B on a GPU (`bash scripts/run_age6.sh`), which fixed reply length at age 5.
