# STATE.md — live session handoff

_Last updated: 2026-10-15 (session 1)_

## Current phase and step
Phase 1 (LoRA): 4 of 6 runs done, nothing running. **Waiting on the user's blind ratings** of `reports/phase1/review_packet.md` (real vs strong baseline vs run 3 vs run 4). Phase 1 exit requires it.
Live demo: `bash scripts/demo.sh` in WSL, then open http://localhost:7860 (src/demo/chat_demo.py; base Qwen vs run-3 adapter). Demo stopped after the meeting. Stop the demo before any training (both together exceed 12 GB VRAM).

## Best model so far
**Tie between run 3 and run 4, to be settled by human ratings.**
- Run 3 `20261016-0003_qwen1.5b_lora_ep1` (6-turn context): length KS 0.031 (best), 5.0 words, loss 2.205, "I don't know" 40-49/1,000.
- Run 4 `20261016-1000_qwen1.5b_lora_ep1_ctx10` (10-turn context): loss 2.176 (best), ~25% fewer "I don't know" (30-34/1,000), but shorter replies (4.4-4.5 words, KS ~0.047).
- Noise floor from a second-seed re-eval: marker gap ±0.004, degeneration ±0.5 pts (EXPERIMENT_LOG run 4).

## Phase 0 results (val, 1,000 contexts; full table reports/phase0/comparison.md)
- Real children: mean 5.10 words (median 3); filler 13.9%, repetition 7.0%, non-standard 5.1%, silence 5.7%.
- Qwen default prompt: 26.5 words, lectures, plays the caregiver, 6.8% meta text. Child loss 3.845.
- **Qwen strong prompt = strongest baseline:** 5.8 words, KS 0.056, but adult-polite content and few child markers. Loss 3.476.
- SmolLM2: 8-10 words, incoherent, copies context. Loss can't be compared to Qwen (different tokenizer).

## Phase 1 so far
- Run 1 speed: 1.5 s/step, 1,895 steps/epoch (eff. batch 16), so ~1 h 45 min for 2 epochs. Peak VRAM 10.2 GB. 42 train examples skipped (>512 tokens).
- Smoke (`20261015-2120_qwen1.5b_lora_smoke`): 200 ex, 60 steps, 35 s, peak 6.7 GB. Val loss 2.54 → 2.45. Samples clearly child-like; one "no! no! no!..." loop seen.

## Done so far
- [x] Step 1: Repo layout, `.gitignore`, tracking docs.
- [x] Step 2: Environment. WSL2 Ubuntu 26.04, Python 3.12 venv `~/venvs/simulearn`, torch 2.14.1+cu132. See `experiments/ENVIRONMENT.md`.
- [x] Step 3: Corpus selection (`src/data/select_corpora.py`, `reports/setup/corpus_download_list.md`). Decisions D1 (silence token) and D2 (North American English) are logged.
- [x] Corpora downloaded by the user on 2026-10-15 (7 NA + Fletcher UK, not used). Extracted to `data/raw/extracted/<collection>/<corpus>/`. See `data/DATA_MANIFEST.md`.
- [x] Step 4: Preprocessing library in `src/data/` (parse_chat, clean, silence, child_ids, build_examples, split, preprocess) and `src/train/collator.py` (loss masking). 52 tests pass: cleaning rules, silence, parse/build, split + leakage (synthetic and real), masking on Qwen and SmolLM2 tokenizers.
- [x] Step 5: `python -m src.data.preprocess` (about 25 s, deterministic). Decisions D3 (exclude ASR, so Hall is dropped) and D4 (first-pass rules) are logged.
  - age5: 144 children, 512 transcripts, **30,356 / 3,985 / 3,542** train/val/test examples, 28 golden. Median reply 3 words (mean 5.3). 36% of transcripts timed; 5.8% of targets contain a silence token.
  - age4: 142 children, 500 transcripts, 34,609 / 3,667 / 2,350 examples, 24 golden. 51% timed.
  - The §4 fallback is NOT needed (both buckets far above 5,000).

## How to run things
Inside WSL: `source /mnt/c/Users/justin/dev/simulearn-testing/scripts/env_wsl.sh`, then e.g. `python -m src.data.preprocess`, `python -m pytest -q tests`.
From Claude's Windows shell: write a .sh to the scratchpad, then run `wsl.exe -d Ubuntu -- bash /mnt/c/.../that.sh` (with `MSYS_NO_PATHCONV=1`).

## Age-6 bucket added (2026-10-19, D7, code only, not run yet)
- `python -m src.data.preprocess --config configs/data_default.yaml` now also writes `data/processed/age6/` (72–83 months). age4/age5 output is unchanged (tested).
- To do: run preprocessing, read `age6/stats.md` (enough examples? which corpora?), then `configs/phase0/qwen1.5b_strong_age6.yaml` (baseline) and `configs/phase1/qwen1.5b_lora_ep1_age6.yaml` (LoRA).

## Next planned actions
1. When ratings come back: `python -m src.eval.score_ratings --phase phase1 [--csv one file per rater]` → `reports/phase1/ratings_summary.md`. Pick the best of runs 3/4.
2. Runs 5-6 (one variable from the winner; grid lr 1e-4/5e-4, rank 8/32), if the user wants them. The stop rule counts run 4 as "not improved" (mixed), which is 1 of 3.
3. Phase 1 report `reports/phase1/phase_report.md` (with test-split metrics for the final pick), then Phase 2 (QLoRA 7B).
4. Rebuild the meeting notebook after any new result: `python scripts/build_meeting_notebook.py`.

## Waiting on user
- **Blind ratings:** fill in `reports/phase1/review_ratings.csv` (28 items x 4 replies; 1-5 child-likeness, coherence, age-appropriateness). Each teammate can rate their own copy of the CSV. Don't open `review_key.json` until done. These files contain CHILDES text: local only, git-ignored.
- Decide whether to spend runs 5-6 before or after the ratings.
- Non-blocking: Dr. Dever to confirm Cameron (Eng-AAE) and the HiPerGator allocation.

## Known issues
- Test split is small for some corpora: Cameron has 3 age-5 children (0 in val); Warren has 0 in test; MacWhinney (Ross + Mark, one group) is all in train. Fine for an aggregate evaluation, but per-corpus test numbers would be noisy.
- Golden set is 28 (age5) / 24 (age4) instead of 30, because of the max-2-per-child rule with 14 test children.
- A few targets are very long (max ~300 words, from merged child monologues). The collator drops examples over 512 tokens after trimming context.
- WSL2 gets ~15 GB RAM by default, which may be tight for Phase 2 (7B).
- Desktop apps use ~1.2 GB VRAM. Close them before training.
