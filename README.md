# SimuLearn child-speech LLM

Fine-tunes a small LLM to reply the way a 4- or 5-year-old child would, trained on CHILDES child–caregiver transcripts.

Status: setup in progress. See `STATE.md` for the current state, `CLAUDE.md` for the full project spec, and `CONTRIBUTING.md` for how we track work (GitHub Issues, PRs, Claude agents).

Data: CHILDES (MacWhinney, B. (2000). *The CHILDES Project: Tools for Analyzing Talk*. 3rd ed. Lawrence Erlbaum.). The transcripts are CC BY-NC-SA and are **never** committed to this repo.

## Team demo in the browser

The side-by-side chat demo (untrained Qwen vs our fine-tuned child model, one adapter per age) is `src/demo/chat_demo.py`. Testers reach it in this order:
1. **Desktop demo (main path):** the demo runs on Justin's PC during test sessions and is shared at https://simulearn-demo.arumos.dev through a named Cloudflare Tunnel, behind the demo password. It is **on demand**: started with `bash scripts/demo_up.sh` and stopped with `bash scripts/demo_down.sh`, so the model doesn't hold GPU memory between sessions. While it's off, the URL shows a Cloudflare "tunnel offline" error (HTTP 530).
2. **Hugging Face Space (fallback):** the same demo on a free ZeroGPU Space, for when the desktop demo is off. See "Fallback: Hugging Face Space" below.

GitHub Pages (`docs/index.html`) is only the landing page with instructions. It can't run a model, so it links to the desktop demo first and to the Space as the backup.

**Locally (GPU, inside WSL):** `bash scripts/demo.sh`, then open http://localhost:7860. Optional environment variables:
- `MONGODB_URI` saves chats and ratings (local MongoDB: see "Local MongoDB" below; `.env` is read automatically).
- `DEMO_PASSWORD` adds a password.

Without them, nothing is saved and there is no password. Stop the demo before training, because both together don't fit in 12 GB VRAM.

### Desktop demo (main way to try the model, DECISIONS.md D10)

`bash scripts/serve_demo.sh` runs the same demo as a service:
- reads `.env` (see "Local MongoDB" below) and **refuses to start if `DEMO_PASSWORD` is empty**;
- loads every age adapter listed in `configs/demo.yaml` whose folder exists under `experiments/`;
- listens on `127.0.0.1:7860` only. A tunnel exposes it to testers; other machines on the LAN can't reach it. Windows browsers on the same PC still open http://localhost:7860 through WSL's localhost forwarding;
- uses the GPU when one is visible (about 3 GiB VRAM), else the CPU (fine-tuned reply ~2 s, untrained ~17 s). `CUDA_VISIBLE_DEVICES="" bash scripts/serve_demo.sh` forces the CPU;
- starts even when MongoDB is down, and prints `saving OFF` (chats are then not saved).

Optional settings: `DEMO_PORT`, `DEMO_HOST`, `DEMO_DEVICE` (`auto`/`cpu`/`cuda`), `DEMO_CONFIG`. Extra arguments go to `src/demo/chat_demo.py`, e.g. `bash scripts/serve_demo.sh --selftest`.

**4-bit models:** `load_in_4bit: true` in `configs/demo.yaml` loads the base model in 4-bit NF4 straight onto the GPU, the same form a QLoRA adapter was trained on (Llama-3.1-8B, `DECISIONS.md` D11), so an 8B model fits in the desktop's 12 GB. It needs a CUDA GPU: the demo refuses to start with it on the CPU or on the ZeroGPU Space. Leave it `false` for bf16 models (1B/3B), which is the default. `--selftest` prints the peak VRAM.

**Install as a systemd user service (one time, inside WSL, done by you):**
1. Turn on systemd in WSL: `sudo nano /etc/wsl.conf` and add
   ```ini
   [boot]
   systemd=true
   ```
   then in Windows PowerShell run `wsl --shutdown` and open Ubuntu again. Check with `systemctl --user status` (no error = working).
2. Set `DEMO_PASSWORD` in `.env` (`cp .env.example .env` first if you haven't).
3. If the repo is not at `~/dev/simulearn`, edit the two paths in `scripts/systemd/simulearn-demo.service`.
4. Install it (without `enable`, so it only runs when you start it):
   ```bash
   mkdir -p ~/.config/systemd/user
   cp scripts/systemd/simulearn-demo.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   ```
5. Start it with `bash scripts/demo_up.sh` (see "Test sessions on the desktop" below) or `systemctl --user start simulearn-demo`. Check: `systemctl --user status simulearn-demo` and `journalctl --user -u simulearn-demo -f` (look for `Demo: ages [...] on cuda` and `serving http://127.0.0.1:7860`).

**Optional, not recommended: start it with WSL.** `systemctl --user enable --now simulearn-demo` plus `sudo loginctl enable-linger "$USER"` keeps the demo running whenever WSL is up. That keeps the model loaded in VRAM all the time (about 3 GiB, and local training no longer fits), so we start it per test session instead. `systemctl --user disable --now simulearn-demo` undoes it.

**Day to day:**
- `systemctl --user restart simulearn-demo` after pulling new demo code, a new adapter or a `.env` change.
- `systemctl --user stop simulearn-demo` before any local GPU job (both don't fit in 12 GB); `start` it afterwards.
- `systemctl --user disable --now simulearn-demo` to turn it off for good; `rm ~/.config/systemd/user/simulearn-demo.service` to remove it.
- It restarts by itself after a crash (`Restart=on-failure`), but gives up after 5 failed starts in 10 minutes (for example a missing password). Fix the cause, then `systemctl --user reset-failed simulearn-demo` and `start` it.

**Limits:** the demo is only up while the PC is on and WSL is running. WSL stops when Windows sleeps or shuts down, and may stop the Ubuntu VM when no WSL window is open, so disable sleep on the desktop and keep a WSL terminal open during a test session. When the desktop demo is off, testers use the Hugging Face Space (see "Fallback: Hugging Face Space" below).

### Share the demo with a Cloudflare Tunnel (issue #15)

A Cloudflare Tunnel gives testers an `https://` link to the desktop demo without opening router ports: the `cloudflared` program on the desktop makes an outgoing connection to Cloudflare, and Cloudflare forwards visitors through it to `127.0.0.1:7860`. It's free. Anyone with the link reaches the password page, so `bash scripts/tunnel.sh` **refuses to start if `DEMO_PASSWORD` is empty** (shell first, then `.env`) or if nothing is listening on `127.0.0.1:7860` (start the demo first).

There are two modes:
- **Quick** (`bash scripts/tunnel.sh`): no Cloudflare account. Prints a random `https://<words>.trycloudflare.com` URL that **changes every time the tunnel restarts**. Good for a meeting or a test session.
- **Named** (`bash scripts/tunnel.sh named`): a fixed hostname such as `demo.<your-domain>`. Needs a free Cloudflare account and a domain whose DNS is on Cloudflare.

**Install `cloudflared` (one time, inside WSL, done by you).** It is a system program, not a Python package, so it goes outside the venv. Use Cloudflare's apt repository (check the current steps at developers.cloudflare.com → Cloudflare Tunnel → Downloads):
```bash
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install cloudflared
cloudflared --version
```
(Or download `cloudflared-linux-amd64.deb` from the GitHub releases page of `cloudflare/cloudflared` and `sudo dpkg -i` it.) `apt upgrade` keeps it current; the script passes `--no-autoupdate`.

**Quick mode:**
1. Make sure the demo runs with a password (`systemctl --user status simulearn-demo`, or `bash scripts/serve_demo.sh` in another terminal).
2. `bash scripts/tunnel.sh`. After a few seconds `cloudflared` prints a box with `https://<words>.trycloudflare.com`. Open it, log in with any username and `DEMO_PASSWORD`, and send that link to testers. Ctrl+C closes the tunnel.

**Named mode (one-time setup, done by you; Claude never handles Cloudflare logins or credentials):**
1. Create a free account at dash.cloudflare.com and add a domain you own (its DNS must be managed by Cloudflare).
2. `cloudflared tunnel login`: opens a browser, you pick the domain. It saves `~/.cloudflared/cert.pem` (outside the repo).
3. `cloudflared tunnel create simulearn-demo`: prints the tunnel ID and writes `~/.cloudflared/<TUNNEL-ID>.json`. This file is the tunnel's password; never copy it into the repo or a chat.
4. `cloudflared tunnel route dns simulearn-demo demo.<your-domain>`.
5. `cp scripts/cloudflared/config.yml.example scripts/cloudflared/config.yml` and fill in the tunnel ID, the full path of the `.json` file and the hostname. `scripts/cloudflared/` is git-ignored except the example.
6. `bash scripts/tunnel.sh named`, then open `https://demo.<your-domain>`.

**As a systemd unit (after the demo service above works):**
```bash
cp scripts/systemd/simulearn-tunnel.service ~/.config/systemd/user/
# named mode: edit ExecStart in the copied file to end in "tunnel.sh named"
systemctl --user daemon-reload
```
The tunnel unit starts the demo unit too and waits up to 10 minutes for it to listen. Start and stop both with the two scripts below. `systemctl --user stop simulearn-tunnel` alone takes the demo off the internet but **keeps the model in VRAM**. Quick mode URLs change after every restart (`journalctl --user -u simulearn-tunnel | grep trycloudflare` shows the current one), so resend the link, or use named mode. `systemctl --user enable --now simulearn-tunnel` would also start the tunnel and the demo with WSL; that is optional and not recommended, for the VRAM reason above.

Settings: `DEMO_PORT` (default 7860; in named mode also change `service:` in `config.yml`), `TUNNEL_CONFIG` (default `scripts/cloudflared/config.yml`), `TUNNEL_WAIT_SECONDS` (default 0 by hand, 600 in the unit).

### Test sessions on the desktop (issue #30)

The model should only be loaded while people are testing, so a session is started and ended by hand:
```bash
bash scripts/demo_up.sh      # before the session
bash scripts/demo_down.sh    # after the session: frees the GPU
```
`demo_up.sh` starts MongoDB (`docker compose up -d`), then the tunnel and demo units, waits until the demo listens on `127.0.0.1:7860` (loading the model takes a minute or more), and prints the public URL (each `hostname:` in `scripts/cloudflared/config.yml`; in quick mode the `trycloudflare.com` URL from the journal) and `Demo: saving on` or `Demo: saving OFF (...)`. It stops with a clear message, before starting anything, if the two units aren't in `~/.config/systemd/user/`, `DEMO_PASSWORD` is empty (shell, then `.env`), or Docker isn't usable (if you were just added to the `docker` group, close and reopen the terminal). `--no-db` skips MongoDB, so chats are not saved.

`demo_down.sh` stops `simulearn-tunnel` **and** `simulearn-demo`, then `docker compose stop` (skip that with `--keep-db`), and prints the GPU memory still in use (`nvidia-smi`). Both scripts are safe to run twice and never print the password or `MONGODB_URI`.

Settings: `DEMO_PORT`, `TUNNEL_CONFIG`, `DEMO_UP_WAIT_SECONDS` (wait for the demo to listen, default 600), `DEMO_UP_TUNNEL_WAIT_SECONDS` (wait for the tunnel unit, the quick URL and the saving line, default 30).

### Fallback: Hugging Face Space

Use this when the desktop demo is off. It runs the same demo on a free ZeroGPU Space (slower first load, a daily GPU quota per visitor, see "ZeroGPU limits" below), with chats saved to MongoDB Atlas instead of the local MongoDB.

**One-time setup, done by you; never paste tokens or passwords into a chat or into git:**
1. Dr. Dever's OK: done 2026-11-03 (DECISIONS.md D9).
2. **Hugging Face:** create an account, then in WSL run `hf auth login`.
3. **Adapters:** run `bash scripts/upload_adapters.sh <hf-user>/simulearn-adapters`. This creates a **private** model repo with `age4/`, `age5/`, … and uploads only the adapter files.
4. **Space:** on huggingface.co, create a Space `<hf-user>/simulearn-demo` (SDK: Gradio, hardware: **ZeroGPU**). Free accounts can't host Gradio Spaces on CPU basic any more (it needs PRO), but they can host up to 2 ZeroGPU Spaces. Make it public: the `DEMO_PASSWORD` protects it, and advisors then don't need HF accounts.
5. **Space settings:**
   - Variable `ADAPTER_REPO=<hf-user>/simulearn-adapters`.
   - Secret `HF_TOKEN`: a read-only token from huggingface.co/settings/tokens.
   - Secret `DEMO_PASSWORD`.
   - Secret `MONGODB_URI`.
6. **MongoDB Atlas:**
   - Create a free M0 cluster and a database user.
   - Under Network Access, allow `0.0.0.0/0` (Spaces have no fixed IP).
   - Copy the `mongodb+srv://…` connection string into the `MONGODB_URI` secret.
7. **Deploy:** run `bash scripts/deploy_space.sh <hf-user>/simulearn-demo`. Re-run it after any change to the demo code. Add `--dry-run` to only build `build/space/` and see the file list.
8. **GitHub Pages** (done; live at https://xarumos.github.io/simulearn/, served from `main` `/docs`):
   - The main button in `docs/index.html` points at the desktop demo (https://simulearn-demo.arumos.dev) and says it works during test sessions.
   - The backup button points at `https://huggingface.co/spaces/<hf-user>/simulearn-demo` (not the `hf.space` address, so visitors' HF login counts for their ZeroGPU quota), with the HF account steps.
   - Settings → Pages: "Deploy from a branch", `main`, `/docs`. Changes to `docs/index.html` go live once merged to `main`.

**What gets saved (MongoDB, database `simulearn`):**
- `conversations` holds one per tester session and side (`untrained` / `fine-tuned`).
- `transcript_iterations` holds one per turn: the adult line and that side's reply, with the model, age, seed and timing in `metadata`.
- `feedback` holds 👍/👎 ratings and notes, linked by `conversation_id` and `version`.

**ZeroGPU limits:** a GPU is borrowed only while a reply is generated (`@spaces.GPU` in `space/app.py`). Each visitor has a daily GPU quota (about 2 min if not logged in to HF, 5 min with a free HF account). One reply uses a few seconds of it, so expect a few dozen turns per tester per day. The first visit after the Space sleeps (48 h without use) takes a few minutes to wake up.

<!-- BEGIN HiPerGator section (issue #9) -->
## Training on HiPerGator

> **Before running anything on HiPerGator, read `POLICIES.md`.** UF prohibits LLMs from countries of concern on HiPerGator, **Qwen included**, and that covers fine-tunes and LoRA adapters too. The chain below uses only Meta's Llama models (`DECISIONS.md` D11). The Qwen and SmolLM2 configs still in `configs/hpg/` are the record of past runs: they are not in the chain, `--only` refuses them, and the Qwen ones must never be submitted by hand. UF also prohibits leaving an allocated GPU idle.

HiPerGator is UF's computing cluster. You don't run jobs on it directly: you log in to a *login node*, then hand jobs to **SLURM**, the queue system, which runs them on a GPU node when one is free. These scripts queue the whole D11 run chain (baselines, fine-tuning and evaluation for three Llama models on both age buckets) with one command. The Python code is the same as on the local PC; only `scripts/env_hpg.sh` and `scripts/slurm/` are HiPerGator-specific.

| File | What it does |
|---|---|
| `scripts/env_hpg.sh` | Loads modules, activates the venv on `/blue`, sets `HF_HOME` (model cache) and `PROJECT_ROOT`. The HiPerGator version of `scripts/env_wsl.sh`. |
| `scripts/slurm/hpg.env.example` | Template for your account, QOS, partition, GPU type and time limits. Copy it to `hpg.env`, which git ignores. |
| `scripts/slurm/train.sbatch` | One training job: `python -m src.train.sft_lora --config <cfg> --run-id <id> --no-eval --resume`. |
| `scripts/slurm/evaluate.sbatch` | One evaluation job: `python -m src.eval.evaluate --config <cfg> --run-id <id> [--adapter <dir>]`. |
| `scripts/slurm/submit_all.sh` | Queues the full chain below. `--dry-run` prints it, `--smoke-only` queues only the smoke tests, `--only <run_name>` queues one run on its own. |
| `configs/hpg/` | The configs for every job. The `llama*` files are the chain; each copies the run-3 recipe and changes only the model, the batch split and the bucket. |

**The models** (`DECISIONS.md` D11): `meta-llama/Llama-3.2-1B-Instruct` and `meta-llama/Llama-3.2-3B-Instruct`, trained with LoRA in bf16, and `meta-llama/Llama-3.1-8B-Instruct`, trained with QLoRA (the base model loaded in 4-bit) and evaluated in 4-bit, the way it will be served. Every run uses the run-3 recipe: LoRA rank 16, alpha 32, learning rate 2e-4 with a cosine schedule, 1 epoch, 6 context turns, max length 512, seed 42, and an effective batch of 16 (per-device batch x gradient accumulation).

**The chain.** Two smoke tests run first: Llama-1B LoRA and Llama-8B QLoRA, each a 60-step training job followed by an evaluation job. When both pass (SLURM's `--dependency=afterok`), everything else is queued at once: six Phase 0 baselines (evaluation only: 1B, 3B and 8B-in-4-bit, each with the default and the strong system prompt), then six training runs, each followed by its own evaluation: 1B LoRA, 3B LoRA and 8B QLoRA on the age-5 bucket (Phases 1 and 2) and the same three on the age-4 bucket, 48–59 months (Phase 3). That is 22 jobs in all. Each training job is followed by its own evaluation job. If a job fails, the jobs waiting on it are cancelled instead of sitting in the queue. Each run writes to `experiments/<YYYYMMDD-HHMM>_<run_name>/`, SLURM's own logs (`slurm-train-<jobid>.out`, `slurm-eval-<jobid>.out`) included.

**Step by step (first time):**

1. Log in: `ssh <gatorlink>@hpg.rc.ufl.edu` (you type your own password and Duo, nobody else does).
2. Clone the repo into your group's `/blue` space, which is larger and faster than home:
   `cd /blue/<group>/<gatorlink> && git clone https://github.com/xArumos/simulearn.git && cd simulearn`
3. Fill in the settings: `cp scripts/slurm/hpg.env.example scripts/slurm/hpg.env`, then edit `hpg.env`. `sacctmgr show assoc user=$USER format=account,qos` shows your account and QOS; `module spider python` and `module spider cuda` show module names. Never commit `hpg.env`.
4. Create the environment once (installs `requirements.txt`, takes a while): `source scripts/env_hpg.sh --setup`
5. Get the data. CHILDES text is never in git, so it has to be fetched again on HiPerGator. Download the corpora listed in `data/DATA_MANIFEST.md` from TalkBank yourself (your own login) and unzip them into `data/raw/extracted/`, as on the local PC, then rebuild both processed folders:
   `python -m src.data.preprocess --config configs/data_default.yaml --verify-ages` and the same with `configs/data_ctx10.yaml`. Keep the data inside `/blue/<group>`, which only your group can read.
6. Get access to the models. The Llama repos are *gated*: on huggingface.co, open each of `meta-llama/Llama-3.2-1B-Instruct`, `meta-llama/Llama-3.2-3B-Instruct` and `meta-llama/Llama-3.1-8B-Instruct` and accept Meta's license (approval usually takes minutes to hours). Then log in on the login node yourself, after `source scripts/env_hpg.sh` so the login is saved in the project's `HF_HOME`: `hf auth login` (paste your own read token; never put it in a file in the repo). Download the three models there so the jobs don't wait for it: `hf download meta-llama/Llama-3.2-1B-Instruct`, and the same for the other two.
7. Check the plan without submitting: `scripts/slurm/submit_all.sh --dry-run`. Each line is one `sbatch` command; `JOB_n` stands in for the job id SLURM will assign.
8. Run the smoke tests alone the first time: `scripts/slurm/submit_all.sh --smoke-only`. Watch with `squeue -u $USER`, and read `experiments/*_smoke_hpg/slurm-*.out` when they end. Loss should fall and `metrics.json` should appear.
9. Queue everything: `scripts/slurm/submit_all.sh` (it repeats the two smoke tests as the gate, about an hour of GPU time). You can log out; the jobs keep running. `scancel <jobid>` cancels a job, `sacct -u $USER` lists finished ones.

**One run on its own.** `--only <run_name>` queues just that config, without the smoke gate: a training config becomes a train job plus an eval job that waits for it, a Phase 0 baseline a single eval job. The `run_name` is the one at the top of the config file. For example, to re-run the 1B age-4 adapter on its own (`data/processed/age4/` must be in place first):

    scripts/slurm/submit_all.sh --only llama1b_lora_ep1_age4_hpg --dry-run   # check
    scripts/slurm/submit_all.sh --only llama1b_lora_ep1_age4_hpg

It writes to `experiments/<YYYYMMDD-HHMM>_llama1b_lora_ep1_age4_hpg/`. Add `--stamp <YYYYMMDD-HHMM>` to file it under an earlier chain's stamp.

A single job can also go in by hand, e.g. `sbatch --account <acct> --qos <qos> --partition <part> --gpus <type>:1 --time 04:00:00 scripts/slurm/evaluate.sbatch configs/hpg/phase0/llama1b_base-default_hpg.yaml my_run_id`.
<!-- END HiPerGator section (issue #9) -->

## Adult-target Gleason pilot

This separate pilot prepares SFT examples whose targets are turns from the adult roles in
`src/data/roles.py` or participants with a recorded age of at least 18 years. Child and other
non-adult turns may appear as context, but are never training targets. Splits are grouped by child
so that the same child cannot appear in more than one split.

Place an authorized `Gleason.zip` at `data/raw/Gleason.zip`, then build the local dataset and
inspect the counts-only role and split summary:

```powershell
python -m src.data.preprocess_adult --config configs/data_gleason_adult.yaml
```

The processed JSONL and split manifest are written under the git-ignored
`data/processed/gleason_adult/`. After reviewing `stats.json`, the configured one-epoch LoRA
pilot can be started with:

```powershell
python -m src.train.sft_lora --config configs/phase1/qwen1.5b_lora_gleason_adult.yaml --run-id gleason-adult-pilot
```

This training command is intentionally not run during preprocessing setup. The local source
archive and processed transcript text must not be committed.

## Notebooks (Gleason child–caregiver workflow)

The notebooks are a separate, notebook-based workflow with their own dependencies. Executed copies are local artifacts and are not tracked; see [`data/README.md`](data/README.md) for their local data layout.

Run commands from the repository root. Create an environment and install the
dependencies for the notebooks you plan to use:

```powershell
python -m pip install jupyter pandas matplotlib pylangacq
```

For notebook 04, install a PyTorch build appropriate for your hardware, then:

```powershell
python -m pip install "transformers==4.57.4" datasets peft accelerate sentencepiece
```

Place the authorized `Gleason.zip` and (for notebook 01) any other CHAT corpus
archives in `data/raw/`. The notebook path configuration is repository-relative
and also works when Jupyter is launched from `notebooks/`.

1. `notebooks/01_childes_age_statistics.ipynb` — summarize CHILDES transcripts
   for children aged 4–6.
2. `notebooks/02_build_child_caregiver_dataset.ipynb` — build the Gleason
   child-caregiver dataset.
3. `notebooks/03_prepare_sft_and_baseline.ipynb` — prepare SFT splits and the
   frozen baseline benchmark.
4. `notebooks/04_baseline_and_lora.ipynb` — run baseline inference, LoRA
   fine-tuning, and evaluation. This step downloads the configured base model
   and can take substantial time and GPU memory.

Outputs are written beneath `data/processed/` and `data/experiments/`; they are
local artifacts and are not committed.

## Local MongoDB

Demo chats, ratings and the transcript API can be stored in a MongoDB on the desktop (instead of Atlas). It runs in Docker, listens on `127.0.0.1:27017` only (nothing outside the PC can reach it, so it has no password), and keeps its data in the Docker volume `simulearn-mongo-data`, outside the repo.

**One-time setup (inside WSL):**
1. Install Docker: Docker Desktop for Windows with "WSL integration" turned on for Ubuntu, or Docker Engine inside WSL. Check with `docker compose version`.
2. `cp .env.example .env`. The defaults point at the local database (`MONGODB_URI=mongodb://127.0.0.1:27017`, `MONGODB_DATABASE=simulearn`). Set `DEMO_PASSWORD` there if you want one. `.env` is git-ignored; never commit it.

**Start / stop:**
```bash
docker compose up -d       # start; restarts by itself with Docker until stopped
docker compose ps          # "healthy" means it's ready
docker compose stop        # stop (data is kept)
docker compose down        # remove the container (data is still kept in the volume)
```
`docker compose down -v` deletes the volume, which is **all saved chats**. Back up first.

**Use it:** `bash scripts/demo.sh` and `python -m uvicorn backend.app.main:app` both read `.env` (via `backend/app/env.py`; variables already set in the shell win). With `MONGODB_URI` empty or unset, the demo saves nothing and still works. The backend always needs a database and falls back to `mongodb://127.0.0.1:27017`.

**Backups:** `bash scripts/db_backup.sh` writes one gzipped dump, `~/simulearn-backups/simulearn-YYYYMMDD-HHMMSS.archive.gz` (change the folder with `SIMULEARN_BACKUP_DIR`; it refuses folders inside the repo, because dumps contain chat text). It uses `mongodump` if installed, otherwise the copy inside the container. Restore with either:
```bash
docker exec -i simulearn-mongo mongorestore --gzip --archive < ~/simulearn-backups/simulearn-YYYYMMDD-HHMMSS.archive.gz
mongorestore --uri=mongodb://127.0.0.1:27017 --gzip --archive="$HOME"/simulearn-backups/simulearn-YYYYMMDD-HHMMSS.archive.gz
```
Add `--drop` to replace collections that already exist instead of adding to them. To check a backup, restore it into a scratch database: add `--nsFrom='simulearn.*' --nsTo='restorecheck.*'`, look at the counts in `mongosh`, then drop `restorecheck`.

**Without Docker:** install MongoDB Community Server in WSL (Ubuntu packages from mongodb.com), keep `bindIp: 127.0.0.1` in `/etc/mongod.conf`, and start it with `sudo systemctl start mongod`. The same `.env` and backup script work, using the host `mongodump` from the MongoDB Database Tools.

The hosted Space (above) has no access to this PC, so it keeps using Atlas unless the `MONGODB_URI` secret is removed.

## Transcript API

The optional `backend/` service stores conversations and append-only transcript
iterations in MongoDB. Each LLM interaction can be saved as a new iteration,
and clients can retrieve either the latest reconstructed transcript or the
transcript as of a specific iteration. The service stores messages after the
LLM call; it does not invoke a model.

Start the local MongoDB (see "Local MongoDB" above), then from the repository root run:

```powershell
python -m pip install -r backend\requirements.txt
$env:MONGODB_URI = "mongodb://localhost:27017"
$env:MONGODB_DATABASE = "simulearn"
python -m uvicorn backend.app.main:app --reload
```

The API is available at `http://localhost:8000` and its interactive docs at
`http://localhost:8000/docs`. Create a conversation with
`POST /api/v1/conversations` using `{"owner_id":"learner-1","title":"Session"}`.
Append an iteration with
`POST /api/v1/conversations/{id}/iterations`, supplying the same `owner_id`
and the interaction's `messages` array (for example, one user message and one
assistant response). Fetch all iterations from
`GET /api/v1/conversations/{id}/iterations?owner_id=learner-1`, or a
reconstructed transcript from
`GET /api/v1/conversations/{id}/transcript?owner_id=learner-1&version=1`.

The `owner_id` must be derived from the application's authenticated user by a
trusted caller; it is not an authentication mechanism. Do not expose this
service publicly until it is connected to the app's authentication layer.
Configure `MONGODB_URI` for a MongoDB deployment and keep credentials out of
source control.

Run backend tests with:

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pytest backend\tests
```
