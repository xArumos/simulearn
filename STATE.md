# STATE.md — live session handoff

_Last updated: 2026-10-15 (session 1)_

## Current phase and step
Phase 1 (LoRA): 2 of 6 runs done. **Paused, nothing running.** The user is connecting the project to their GitHub repo as an orphan branch. Resume with the next planned actions below once they say go.

## Best model so far
**Run 1 `20261015-2125_qwen1.5b_lora_r16_lr2e-4`** (adapter in `experiments/<run>/adapter/`). Val: mean 4.45 words (real 5.10), length KS 0.032, marker gap 0.025, degenerate 0.2%, child loss 2.199 (ppl 9.0). Beats all baselines. Main weakness: overuses "I don't know" (~5x real) and short answers; less diverse than real.

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

## Next planned actions
1. Run 2 done: SmolLM2 LoRA is worse than Qwen LoRA (3.35 words, KS 0.165, 'yeah' 114/1000). Qwen stays the base model for Phase 1.
2. One-variable runs from the best: epochs=1 (cheaper; epoch 2 gave ~0.003 val loss), then context 10 turns (YELLOW: DECISIONS entry + re-preprocess with build.context_turns=10).
3. Review packet with the best LoRA vs the strong baseline vs real (`python -m src.eval.review_packet ...`), then a user rating round. Phase 1 exit requires it.

## Waiting on user
- Non-blocking: Dr. Dever may still confirm Cameron (Eng-AAE).

## Known issues
- Test split is small for some corpora: Cameron has 3 age-5 children (0 in val); Warren has 0 in test; MacWhinney (Ross + Mark, one group) is all in train. Fine for an aggregate evaluation, but per-corpus test numbers would be noisy.
- Golden set is 28 (age5) / 24 (age4) instead of 30, because of the max-2-per-child rule with 14 test children.
- A few targets are very long (max ~300 words, from merged child monologues). The collator drops examples over 512 tokens after trimming context.
- WSL2 gets ~15 GB RAM by default, which may be tight for Phase 2 (7B).
- Desktop apps use ~1.2 GB VRAM. Close them before training.
