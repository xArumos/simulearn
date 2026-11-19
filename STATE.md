# STATE.md — live session handoff

_Last updated: 2026-11-19 (session 7, synced after PRs #70, #71, #72, #75)_

**Active work is tracked in GitHub Issues** (https://github.com/xArumos/simulearn/issues). This file is the handoff summary; `/sync-issues` keeps it current. Workflow: `CONTRIBUTING.md`, CLAUDE.md §14.

## Session 7 (2026-11-19): demo online at a fixed URL
- #16 done (closed): `cloudflared` installed in WSL; named tunnel `simulearn-demo` → **https://simulearn-demo.arumos.dev** (config in git-ignored `scripts/cloudflared/config.yml`, credentials in `~/.cloudflared`). Plan: product later on `simulearn.arumos.dev` in the same tunnel (one level below the domain only; free certs don't cover `a.b.arumos.dev`). Gradio stays as an internal model-testing tool once the product exists.
- Services are **installed but deliberately not enabled**: the demo holds ~3 GB VRAM while up, so it runs on demand only. Docker Engine installed inside WSL (not Docker Desktop); MongoDB 7 runs via `docker compose`.
- External test passed (Justin, phone off Wi-Fi): 3 chats / 5 turns / 3 ratings saved. A friend tested earlier while Mongo was down, so nothing of theirs was saved. Get Dr. Dever's OK before saving chats from people outside the team.
- PR #32 (#31): `DemoStore.rate()` stores `feedback.conversation_id` as ObjectId (was str, so ratings didn't join to chats); invalid ids logged + return False; 2 tests. One-off `mongosh` migration for old string-id rows is in the `src/demo/store.py` docstring (not yet run).
- PR #33 (#30): `scripts/demo_up.sh [--no-db]` (checks units/DEMO_PASSWORD/docker, starts Mongo + tunnel + demo, waits for the port, prints URL(s) from the tunnel config and saving on/off) and `scripts/demo_down.sh [--keep-db]` (stops tunnel + demo by name, then Mongo, shows GPU memory). Shared checks moved to `scripts/_demo_env.sh` (sourced by `tunnel.sh`). README uses them; `enable` not recommended. 28 stub tests; 166 pass. Not yet run against the real services.
- PR #35 (#17): GitHub Pages main button → https://simulearn-demo.arumos.dev (note: works during test sessions; a Cloudflare 530/1033 page means it's off), HF Space is the outlined "backup demo" button with its account steps. README: desktop demo first, HF Space under "Fallback: Hugging Face Space".
- PR #37 (#36): missing-cloudflared test runs with a tools-only PATH (never runs a real `cloudflared`; runs instead of skipping on the desktop); header comments in `tunnel.sh`, `serve_demo.sh` and both systemd units describe the on-demand flow (`enable` not recommended). 169 pass.

## Session 7b (2026-11-19): Qwen is prohibited; switch to Llama
- **UF/Florida rule:** no LLMs from countries of concern on UF resources or with UF data, fine-tunes and LoRA adapters included; no idle GPUs on HiPerGator. Qwen (Alibaba) is affected. PR #39: `POLICIES.md` (rules, sources, penalties), CLAUDE.md §2 hard constraints + §8 banner, CONTRIBUTING/README notes, issue/PR template checkbox, **DECISIONS D11 approved** (Dr. Dever's general approval, relayed by Justin; recorded on #40): Llama-3.2-1B / 3B (LoRA, bf16) and Llama-3.1-8B (QLoRA, served in 4-bit, ~6 GB on the 4070 Ti); SmolLM2-360M dropped from new runs; 6-turn context only.
- **HiPerGator cleanup (Justin, 2026-11-19):** all Qwen weights (whole HF cache), adapters, checkpoints and run outputs deleted; removal list kept for the Research Computing ticket. Llama 3.1 + 3.2 licenses approved; all three Llama models downloaded to the HiPerGator cache (~24 GB). Desktop/this PC still hold Qwen files (not UF hardware; #48 with Dr. Dever). The cached Qwen tokenizer was loaded on this PC by the old masking test before #41 removed it (disclosed in PR #50).
- PR #50 (#41): 14 Llama configs under `configs/hpg/` (2 smoke, 6 baselines incl. 8B in 4-bit, 6 train runs: 1B/3B LoRA + 8B QLoRA on age5 and age4; run-3 recipe, effective batch 16); `src/utils/chat_template.py` pins the template date (`26 Jul 2024`) for training, eval and demo; masking test on Llama 1B/3B/8B + SmolLM2 (13 pass locally with real tokenizers); `submit_all.sh` chain = 22 Llama jobs, `--only` refuses old configs.
- PR #52 (#42): `src/utils/model_policy.py` guard (banned orgs + name patterns + adapter base check) runs before any load in `load_tokenizer`/`load_model`, `scripts/gpu_smoke_test.py` (now Llama-3.2-1B) and `submit_all.sh`; CLI `python -m src.utils.model_policy NAME`. 232 tests pass. **The desktop demo now refuses to start** (demo.yaml still names Qwen) until #46.
- PR #51 (#45): `load_in_4bit` option in `configs/demo.yaml` (default false); loads base + adapters straight onto cuda; refused on CPU and ZeroGPU. Real 4-bit load not yet run (no GPU here; #46 measures it).

## Session 7c (2026-11-19): educator product frontend (tracking #65)
- Plan: educator-facing product at **https://simulearn.arumos.dev**: React + Vite SPA served by a FastAPI backend that holds the model, with invite-only accounts and an optional side-by-side "untrained AI" comparison (off by default). It also has scenario starters, history + export, a model info panel and 👍/👎 ratings. Gradio stays as the internal testing tool. Same tunnel `simulearn-demo` (one tunnel, two hostnames; product on 127.0.0.1:8000). **Team-only until #57 (IRB question for Dr. Dever) is answered.** Issues #54-#64.
- #56 done: Node v26.13.1 / npm 11.20.0 via nvm v0.40.3 in `~/.nvm` (Justin approved the install outside the venv). Justin ran the DNS route for `simulearn.arumos.dev` (step 2 of #64).
- PR #66 (#54): model code moved to Gradio-free `src/demo/engine.py`; `chat_demo.py` re-exports it. Fixed the Space allowlist (`engine.py`, plus `chat_template.py` and `model_policy.py`, which were missing, so a built Space couldn't import the demo).
- PR #67 (#55): `src/product/auth.py`: argon2 password hashes, sha256-hashed session tokens, httpOnly/Secure/SameSite=Lax cookie (7 days), the same 401 for unknown user, wrong password and disabled account, and a rate limit (5 failures / 10 min per IP or username). Routes `/api/auth/login|logout`, `/api/me`, `/api/me/password`; mount with `app.state.auth = Auth(db); app.include_router(router)`. `scripts/create_user.py` (create/disable/enable/reset/list, password via getpass only). `argon2-cffi==25.1.0` pinned. 260 tests pass.
- PR #68 (#60): `frontend/`: React 19 + Vite 8 + TS, Tailwind 4 tokens, light/dark, Radix UI components, self-hosted Inter. Login, app shell, account page; Practice/History are placeholders (#61/#62). Typed API client `frontend/src/api.ts`. `MOCK_API=1 npm run dev` gives a fake API (`demo` / `practice-only`, mock only). `scripts/build_frontend.sh`; CI frontend job on Node 26 (typecheck, vitest, build, `check:dist` that refuses external hosts). Not yet checked: login against the real #55 routes, and phone width / both themes by eye.
- Accounts `justin` and `admin` created (both admin). Real `scripts/cloudflared/config.yml` now has `simulearn.arumos.dev → 127.0.0.1:8000` (cloudflared `ingress validate` OK); new product unit + changed tunnel unit installed in `~/.config/systemd/user/`.
- PR #70 (#58): `src/product/server.py` (config, model-info, sessions, child turn, separate untrained turn, PATCH compare; serves `frontend/dist` with SPA fallback; CLI `python -m src.product.server --host 127.0.0.1 --port 8000 --device ...`), `src/product/sessions.py` (`practice_sessions` collection, or memory when saving is off; untrained history starts at `compare_started_turn`), `configs/scenarios.yaml` (7 invented scenes). The login rate limit trusts `CF-Connecting-IP` only from 127.0.0.1/::1. The server **needs MongoDB** (accounts); `SIMULEARN_SAVE_CHATS=0` = saving off; `SIMULEARN_COOKIE_SECURE=0` for local http only.
- PR #71 (#61): practice view: age picker, compare switch (off by default; untrained called only after the child and only while on), scene picker, pause chips + thinking delay (max 5 s), 👍/👎 + note, model info sheet, toasts. `api.ts` + mock match #70. 45 frontend tests.
- PR #72 (#63): `serve_product.sh` (refuses without `frontend/dist`, with the demo running, or with no active admin via `create_user.py has-admin`), `product_up.sh [--no-save]` / `product_down.sh [--keep-db]`, `simulearn-product.service`; `tunnel.sh` checks every ingress port and only warns when one app is down; the tunnel unit no longer pulls in the demo; `demo_up.sh` refuses while the product runs. README "Run the product", DECISIONS D12.
- PR #75 (#46, other session): demo (and so the product) now on `meta-llama/Llama-3.2-3B-Instruct` bf16 with the HiPerGator age-4/age-5 3B adapters; selftest peak VRAM 6.20 GiB, 0.2-0.4 s per fine-tuned reply. Verified after merge: guard passes for base + both adapters, 328 Python tests and 45 frontend tests pass, build + `check:dist` OK. PR #76 (open) sets the age labels back to plain month ranges (the model name ended up inside "5 years (...)").

## Session 6 (2026-11-18): issue-driven workflow
- Added `CONTRIBUTING.md`, issue/PR templates, CI (`.github/workflows/tests.yml` + `requirements-ci.txt`, CPU-only; 75 tests pass in a fresh venv), workflow labels, and `.claude/` (agent `issue-worker`; skills `/plan-issues`, `/work-issue`, `/sync-issues`; project permissions). CLAUDE.md §14.
- PR #20 (#9): HiPerGator SLURM. `scripts/env_hpg.sh`, `scripts/slurm/{train,evaluate}.sbatch`, `submit_all.sh` (smoke → Phase 0/1/2 chain, `--dry-run`/`--smoke-only`), settings in git-ignored `scripts/slurm/hpg.env` (placeholders in `.example` until #8). New `configs/hpg/phase1/qwen1.5b_lora_smoke_hpg.yaml`.
- #8 done (closed): HiPerGator set up (group account/QOS in git-ignored `hpg.env`, partition `hpg-rtx6000`, RTX PRO 6000 96 GB, repo+venv+hf_cache+data on the group's blue storage); Dr. Dever approved CHILDES data on HiPerGator (verbal, team meeting). Smoke jobs all COMPLETED (1.5B LoRA val loss 2.447, 6.7 GB; 7B QLoRA 2.384, 12.9 GB; repro identical). **Full chain submitted, stamp `20261118-2027`** (#11).
- PR #23 (#10): `configs/hpg/phase3/qwen1.5b_lora_ep1_age4_hpg.yaml` (run-3 recipe on age4), added to `submit_all.sh` after smoke; new `--only <run_name>` flag queues one config's train+eval alone (age-4 was not in the running chain).
- PR #24 (#14): `scripts/serve_demo.sh` (127.0.0.1:7860, cuda if visible else cpu, needs `DEMO_PASSWORD`, starts with saving OFF if Mongo down), `scripts/systemd/simulearn-demo.service` (user unit, restart-on-failure), `chat_demo.py` `--host/--device/--require-password`, DECISIONS D10, README steps. GPU selftest 0.2-0.3 s/reply, 3 GB VRAM. 107 tests pass.
- PR #26 (#15): `scripts/tunnel.sh` (quick mode = temporary trycloudflare URL; named mode = `scripts/cloudflared/config.yml`), refuses without DEMO_PASSWORD / listening demo / cloudflared; `config.yml.example`; optional `scripts/systemd/simulearn-tunnel.service` (after the demo unit); real config + credentials git-ignored; README "Share the demo with a Cloudflare Tunnel". Tested with a stub cloudflared only (132 tests pass); live check not yet done.
- PR #21 (#13): local MongoDB. `docker-compose.yml` (Mongo 7 on 127.0.0.1:27017, named volume), `.env.example`, `backend/app/env.py` loads `.env` for demo + backend, `scripts/db_backup.sh` (backups to `~/simulearn-backups`), README "Local MongoDB". Backup only tested with a stand-in `mongodump`; Docker not installed on the desktop yet.
- #11 done: all 16 jobs of chain `20261118-2027` COMPLETED, exit 0 (age-4 queued alone via `--only`); job IDs commented on #11.
- PR #28 (#12): HPG results. Records (README/config/metrics/train.log/train_stats, repo-relative paths) for all 11 runs; `scripts/hpg_tables.sh` rebuilds every comparison table (`reports/phase{0,1,3}/comparison_hpg.md`, `reports/phase2/comparison.md`, `reports/phase3/age5_vs_age4_hpg.md`, `reports/hpg/{hpg_vs_local,smoke}.md`); `src/eval/compare.py` refuses mixed buckets/splits, adds a paired table flagging changes beyond the noise floor; EXPERIMENT_LOG HPG section, `reports/phase2/phase2_report.md`, `reports/phase3/phase3_findings.md`. 141 tests pass. Findings: all gates pass; HPG matches local (loss within 0.004, no ranking changes); 7B QLoRA mixed (best loss 2.110, low degeneration, but too short: median 2 words vs 3 real, KS 0.142) → keep 1.5B run-3 recipe as default, add 7B to the blind review packet; age-4 replies shorter than age-5 in the right direction but overshoot (-1.34 words vs -0.94 real).
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
- Helped revise the summit paper's "AI Development and Technical Approach" paragraph (text lives in the team's Google Doc, not here). The paper states that QLoRA of Qwen2.5-7B has been run and compared, and that all runs were done on HiPerGator. **Both are now true (PR #28).** The paper should describe the 7B result as mixed (best loss, replies too short), not a clear win.
- The user now has HiPerGator access and wants **all** runs (Phase 0 baselines, Phase 1 LoRA runs 2/3/4, Phase 2 QLoRA) re-done there for a same-hardware comparison. Paused until the user says they're ready.
- Created `configs/hpg/{phase0,phase1,phase2}/*.yaml` (9 files): copies of the local run configs with an `_hpg` run_name, plus 7B QLoRA smoke and full configs (based on run 3). Still to do: `scripts/env_hpg.sh` and `scripts/slurm/*.sbatch`. The core code needs no changes (paths are relative to the project root).
- Liu & Fourtassi (2025, SemDial) supports "LLMs approximate child speech per utterance but diverge over multi-turn interaction (less diverse, over-aligned)". It does NOT support "adult-like". That claim comes from our own Phase 0 baselines.

## Current phase and step
**Switching to Llama (D11, tracking #49).** Next: #43 Llama chain on HiPerGator (Justin). The Qwen results below are the historical record only; Qwen may not be run again. Earlier: HiPerGator re-runs done (Phase 0/1/2 + Phase 3 age-4, PR #28). Phase 2 (7B QLoRA) and Phase 3 (age-4) have reports. Phase 1 (LoRA): 4 of 6 local runs done. **Waiting on the user's blind ratings** of `reports/phase1/review_packet.md` (real vs strong baseline vs run 3 vs run 4). Phase 1 exit requires it.
Live demo: **refuses to start until #46** switches it to Llama (the guard blocks Qwen). Then (on demand): `bash scripts/demo_up.sh` → https://simulearn-demo.arumos.dev (base Qwen vs run-3 adapter, password-protected); `bash scripts/demo_down.sh` afterwards to free the GPU. Locally, `bash scripts/demo.sh` → http://localhost:7860. Stop the demo before any training (both together exceed 12 GB VRAM).

## Best model so far
**No permitted model trained yet** (Llama chain #43 pending). Historical Qwen record: tie between run 3 and run 4.
- Run 3 `20261016-0003_qwen1.5b_lora_ep1` (6-turn context): length KS 0.031 (best), 5.0 words, loss 2.205, "I don't know" 40-49/1,000.
- Run 4 `20261016-1000_qwen1.5b_lora_ep1_ctx10` (10-turn context): loss 2.176 (best), ~25% fewer "I don't know" (30-34/1,000), but shorter replies (4.4-4.5 words, KS ~0.047).
- HPG re-runs confirm the tie (`reports/hpg/hpg_vs_local.md`). 7B QLoRA `20261118-2027_qwen7b_qlora_ep1_hpg` has the best loss (2.110) but replies too short; not the new best (`reports/phase2/phase2_report.md`).
- Age-4 adapter: `20261118-2027_qwen1.5b_lora_ep1_age4_hpg` (loss 2.154, 3.58 words vs 4.16 real, KS 0.077), local only, not uploaded.
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
Task list lives on GitHub; tracking issues #49 (Llama switch) and #18 (done).
0. **Llama switch (#49):** #41, #42, #45 done → #43 run the chain on HiPerGator (Justin: `git pull`, `submit_all.sh --dry-run`, `--smoke-only`, then full) → #44 collect results + pick demo model + new review packet → #46 demo switch (measure 4-bit VRAM) and #47 docs → #48 Space / HF adapter repo / paper (Justin + Dr. Dever). #40 open for the Research Computing ticket.
1. Track A (HiPerGator, Qwen era): #8-#12 done; superseded by the Llama switch.
2. Track B (self-hosted demo): #13-#17, #30, #31, #36 all done.
2b. **Product frontend (#65):** #54-#56, #58, #60, #61, #63 done → **#59** feedback/history/export API (ready; frontend expects `{ok, saved}` from `/api/feedback`, see its comment) → #62 history view → #64 live test (Justin, can start now).
3. Still open, not yet issues: Phase 1 ratings → pick run 3 vs 4 (`python -m src.eval.score_ratings --phase phase1`), optional runs 5-6, Phase 1 report. Rebuild the meeting notebook after new results (`python scripts/build_meeting_notebook.py`).

## Waiting on user
- First real run of `bash scripts/demo_up.sh` / `demo_down.sh` on the desktop (only stub-tested so far).
- Optional: run the `mongosh` migration in the `src/demo/store.py` docstring so the 3 old ratings join to their chats.
- Run `scripts/db_backup.sh` once to verify backups for real (#13 follow-up; Docker + Mongo are now up).
- **#57:** ask Dr. Dever whether educators outside the team may use the product and whether their chats may be saved (IRB).
- **#64:** first real run of the product: merge #76, `bash scripts/build_frontend.sh`, `bash scripts/product_up.sh`, log in at https://simulearn.arumos.dev from a phone off Wi-Fi, run a session with compare off and on, `bash scripts/product_down.sh`. This also checks the frontend login against the real routes (#60 follow-up). DNS route, ingress, units and accounts are done.
- **#43:** run the Llama chain on HiPerGator (smoke first).
- **#40:** report the Qwen cleanup in a UF Research Computing ticket (attach the removal list).
- **#48 (later):** with Dr. Dever: Qwen files on the desktop / HF adapter repo, the public Space, and the summit paper (names Qwen).
- **Blind ratings** (Qwen packet; now mainly informs the 6- vs 10-turn question, a new Llama packet comes from #44): fill in `reports/phase1/review_ratings.csv` (28 items x 4 replies; 1-5 child-likeness, coherence, age-appropriateness). Each teammate can rate their own copy. Don't open `review_key.json` until done. Local only, git-ignored (CHILDES text).
- Decide whether to spend runs 5-6 before or after the ratings.
- Non-blocking: Dr. Dever to confirm Cameron (Eng-AAE). Ask Dante to delete the public `Dante7162-patch-1` branch (contains `Gleason.zip`).

## Known issues
- Test split is small for some corpora: Cameron has 3 age-5 children (0 in val); Warren has 0 in test; MacWhinney (Ross + Mark, one group) is all in train. Fine for an aggregate evaluation, but per-corpus test numbers would be noisy.
- Golden set is 28 (age5) / 24 (age4) instead of 30, because of the max-2-per-child rule with 14 test children.
- A few targets are very long (max ~300 words, from merged child monologues). The collator drops examples over 512 tokens after trimming context.
- WSL2 gets ~15 GB RAM by default, which may be tight for Phase 2 (7B).
- Desktop apps use ~1.2 GB VRAM. Close them before training.
- `test_backup_script_explains_missing_mongodump` fails on the desktop **and runs a real mongodump** into pytest's tmp folder (`/tmp/pytest-of-justin`); deselect it locally until fixed, because it assumes `mongodump` isn't installed, and it is there. It passes in CI. The test should hide `mongodump` from PATH, as the cloudflared test does.
