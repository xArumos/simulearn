# STATE.md — live session handoff

_Last updated: 2026-11-18 (session 6, synced after PRs #20, #21)_

**Active work is tracked in GitHub Issues** (https://github.com/xArumos/simulearn/issues). This file is the handoff summary; `/sync-issues` keeps it current. Workflow: `CONTRIBUTING.md`, CLAUDE.md §14.

## Session 6 (2026-11-18): issue-driven workflow
- Added `CONTRIBUTING.md`, issue/PR templates, CI (`.github/workflows/tests.yml` + `requirements-ci.txt`, CPU-only; 75 tests pass in a fresh venv), workflow labels, and `.claude/` (agent `issue-worker`; skills `/plan-issues`, `/work-issue`, `/sync-issues`; project permissions). CLAUDE.md §14.
- PR #20 (#9): HiPerGator SLURM. `scripts/env_hpg.sh`, `scripts/slurm/{train,evaluate}.sbatch`, `submit_all.sh` (smoke → Phase 0/1/2 chain, `--dry-run`/`--smoke-only`), settings in git-ignored `scripts/slurm/hpg.env` (placeholders in `.example` until #8). New `configs/hpg/phase1/qwen1.5b_lora_smoke_hpg.yaml`. Not yet run on HiPerGator.
- PR #21 (#13): local MongoDB. `docker-compose.yml` (Mongo 7 on 127.0.0.1:27017, named volume), `.env.example`, `backend/app/env.py` loads `.env` for demo + backend, `scripts/db_backup.sh` (backups to `~/simulearn-backups`), README "Local MongoDB". Backup only tested with a stand-in `mongodump`; Docker not installed on the desktop yet.
- Merged as PR #7. Planned as issues #8-#18 (tracking issue #18). **Change of plans:** training moves to HiPerGator (Track A, first), and the demo + MongoDB move from the HF Space/Atlas to Justin's desktop behind a Cloudflare Tunnel, with the Space kept as a fallback (Track B).

## Session 5 (2026-11-03) — everything merged into `main`
- Branch `justin/merge-to-main` (from `main`): merges Dante's PR #4 (`integrate/child-llm-main`: our Phase 1 snapshot + Gleason adult-target pilot), fixes its `warmup_ratio` bug (transformers 5.20 has no such argument; `warmup_steps` < 1 is a fraction), then applies our hosted-demo and ZeroGPU commits. README combines our guide, Dante's Gleason section, main's notebook workflow and Transcript API; `.gitignore` is the union. 75 tests pass.
- **Work from `main` from now on.** `justin/demo-hosting` and `integrate/child-llm-main` are fully contained in it.

## Session 4 (2026-11-03) — moved to a second machine (native Linux, CachyOS)
- Repo at `/home/justin/dev/simulearn`, venv `~/venvs/simulearn` (CPU-only torch; no NVIDIA GPU here, so no training on this machine). `scripts/env_wsl.sh` works unchanged on native Linux.
- Age-5 adapter (run 3) is present here. 72 tests pass. `deploy_space.sh --dry-run` builds `build/space/` fine. Not logged in to HF yet.
- Adapter uploaded: `xArumos/simulearn-adapters` (private; only age5/adapter_* files). Verified.
- **HF policy blocker:** Gradio Spaces on free cpu-basic now need PRO (create returned 402). Space `xArumos/simulearn-demo` exists as private ZeroGPU (zero-a10g), variable ADAPTER_REPO set, no code yet. User chose ZeroGPU: demo ported (D9 update), 73 tests pass, built Space smoke-tested locally on CPU. Secrets HF_TOKEN + DEMO_PASSWORD set by user; deployed; Space RUNNING on ZeroGPU (private), password gate verified. User verified a real turn on ZeroGPU (2026-11-03). User made the Space public. Quota fix: one `@spaces.GPU(duration=15)` call per turn; landing page tells testers to sign in to a free HF account and links huggingface.co/spaces/xArumos/simulearn-demo. GitHub Pages live at https://xarumos.github.io/simulearn/, served from `main` `/docs`. Next: have a signed-in teammate count how many turns they get. MongoDB Atlas later (saving is off until MONGODB_URI is set).
- Dr. Dever approved the hosted demo (D9 updated). Remaining hosting steps are user-only (HF login onward; see "Waiting on user").

## Session 3 (2026-11-03) — hosted team demo (branch `justin/demo-hosting`)
- Fetched all remote branches. Dante's MongoDB transcript API is on `main` (`backend/`), and I copied it here unchanged. No teammate frontend exists in the repo.
- **Demo:**
  - `src/demo/chat_demo.py` now has an age picker (one adapter per age, from `configs/demo.yaml`) and runs on CPU or GPU.
  - The child reply shows first, and the untrained column fills in afterwards.
  - Tester name, 👍/👎 + note.
  - The context window now matches training: 6 turns including the new adult line. Before, it was 7.
- **Saving:** `src/demo/store.py` wraps Dante's `MongoTranscriptStore` and adds a `feedback` collection. It's a no-op without `MONGODB_URI`.
- **Hosting:**
  - `space/` + `scripts/build_space.py` (allowlist; refuses data files) + `scripts/deploy_space.sh` + `scripts/upload_adapters.sh` (private repo, adapter files only).
  - `docs/index.html` is the GitHub Pages landing page. It uses a button, not an iframe: the password cookie can be blocked in iframes.
  - README has the step-by-step guide. DECISIONS D9.
- Tests: 72 pass (`tests` + `backend/tests`), including an end-to-end UI test with a fake model and mongomock.
- Age-4 run `20261103-1936_qwen1.5b_lora_ep1_age4` (`configs/phase3/qwen1.5b_lora_ep1_age4.yaml`) was **stopped by the user at ~step 150 of ~2,160**, because hosting comes first. There's no adapter yet, so the demo shows age 5 only. The partial run folder is kept and does not count as a finished Phase 3 run.
- **Flag for the team:** public branch `Dante7162-patch-1` contains `Gleason.zip` (likely raw CHILDES) plus executed notebooks. Ask Dante to delete that branch (TalkBank no-redistribution rule).

## Session 2 (2026-10-31 / 11-01) — summit paper + HiPerGator prep
- Helped revise the summit paper's "AI Development and Technical Approach" paragraph (text lives in the team's Google Doc, not here). **The paper states that QLoRA of Qwen2.5-7B has been run and compared, and that all runs were done on HiPerGator. Neither is true yet. Phase 2 must run before the final submission.**
- The user now has HiPerGator access and wants **all** runs (Phase 0 baselines, Phase 1 LoRA runs 2/3/4, Phase 2 QLoRA) re-done there for a same-hardware comparison. Paused until the user says they're ready.
- Created `configs/hpg/{phase0,phase1,phase2}/*.yaml` (9 files): copies of the local run configs with an `_hpg` run_name, plus 7B QLoRA smoke and full configs (based on run 3). Still to do: `scripts/env_hpg.sh` and `scripts/slurm/*.sbatch`. The core code needs no changes (paths are relative to the project root).
- Liu & Fourtassi (2025, SemDial) supports "LLMs approximate child speech per utterance but diverge over multi-turn interaction (less diverse, over-aligned)". It does NOT support "adult-like". That claim comes from our own Phase 0 baselines.

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
Native Linux (current machine, no GPU): `source ~/venvs/simulearn/bin/activate` in the repo, then e.g. `python -m pytest -q tests backend/tests`.
Old Windows/WSL machine (GPU):
Inside WSL: `source /mnt/c/Users/justin/dev/simulearn-testing/scripts/env_wsl.sh`, then e.g. `python -m src.data.preprocess`, `python -m pytest -q tests`.
From Claude's Windows shell: write a .sh to the scratchpad, then run `wsl.exe -d Ubuntu -- bash /mnt/c/.../that.sh` (with `MSYS_NO_PATHCONV=1`).

## Next planned actions
Task list lives on GitHub; tracking issue #18.
1. Track A (HiPerGator, do first): #9 done (PR #20) → #10 age-4 config (agent-ready) → #11 submit runs (Justin; needs #8, #9, #10) → #12 collect results.
2. Track B (self-hosted demo): #13 done (PR #21) → #14 demo service (agent-ready) + D10 → #15 tunnel scripts → #16 Cloudflare + external test (Justin) → #17 Pages + README.
3. Still open, not yet issues: Phase 1 ratings → pick run 3 vs 4 (`python -m src.eval.score_ratings --phase phase1`), optional runs 5-6, Phase 1 report. Rebuild the meeting notebook after new results (`python scripts/build_meeting_notebook.py`).

## Waiting on user
- **#8 HiPerGator one-time setup** (blocks #11): log in, clone, build venv, copy `data/processed*/` to `/blue`, Dr. Dever OK for CHILDES data on HiPerGator, then comment account / QOS / partition / GPU type on the issue.
- **#11** submit smoke jobs, then the full chain (after #8, #10; #9 done).
- Install Docker in WSL, `docker compose up -d`, then run `scripts/db_backup.sh` once to verify backups for real (#13 follow-up).
- **#16** Cloudflare account + tunnel on the desktop, external test (after #14, #15).
- **Blind ratings:** fill in `reports/phase1/review_ratings.csv` (28 items x 4 replies; 1-5 child-likeness, coherence, age-appropriateness). Each teammate can rate their own copy. Don't open `review_key.json` until done. Local only, git-ignored (CHILDES text).
- Decide whether to spend runs 5-6 before or after the ratings.
- Non-blocking: Dr. Dever to confirm Cameron (Eng-AAE). Ask Dante to delete the public `Dante7162-patch-1` branch (contains `Gleason.zip`).

## Known issues
- Test split is small for some corpora: Cameron has 3 age-5 children (0 in val); Warren has 0 in test; MacWhinney (Ross + Mark, one group) is all in train. Fine for an aggregate evaluation, but per-corpus test numbers would be noisy.
- Golden set is 28 (age5) / 24 (age4) instead of 30, because of the max-2-per-child rule with 14 test children.
- A few targets are very long (max ~300 words, from merged child monologues). The collator drops examples over 512 tokens after trimming context.
- WSL2 gets ~15 GB RAM by default, which may be tight for Phase 2 (7B).
- Desktop apps use ~1.2 GB VRAM. Close them before training.
