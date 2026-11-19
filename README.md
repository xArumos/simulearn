# SimuLearn child-speech LLM

Fine-tunes a small LLM to reply the way a 4- or 5-year-old child would, trained on CHILDES child–caregiver transcripts.

Status: setup in progress. See `STATE.md` for the current state, `CLAUDE.md` for the full project spec, and `CONTRIBUTING.md` for how we track work (GitHub Issues, PRs, Claude agents).

Data: CHILDES (MacWhinney, B. (2000). *The CHILDES Project: Tools for Analyzing Talk*. 3rd ed. Lawrence Erlbaum.). The transcripts are CC BY-NC-SA and are **never** committed to this repo.

## Team demo in the browser

The side-by-side chat demo (untrained Qwen vs our fine-tuned child model, one adapter per age) is `src/demo/chat_demo.py`. It runs locally, or hosted on a free Hugging Face Space for advisors. GitHub Pages (`docs/index.html`) is only the landing page with instructions. It can't run a model, so it links to the Space.

**Locally (GPU, inside WSL):** `bash scripts/demo.sh`, then open http://localhost:7860. Optional environment variables:
- `MONGODB_URI` saves chats and ratings (local MongoDB: see "Local MongoDB" below; `.env` is read automatically).
- `DEMO_PASSWORD` adds a password.

Without them, nothing is saved and there is no password. Stop the demo before training, because both together don't fit in 12 GB VRAM.

**Hosted (one-time setup, done by you; never paste tokens or passwords into a chat or into git):**
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
   - The demo link in `docs/index.html` points at `https://huggingface.co/spaces/<hf-user>/simulearn-demo` (not the `hf.space` address, so visitors' HF login counts for their ZeroGPU quota).
   - Settings → Pages: "Deploy from a branch", `main`, `/docs`. Changes to `docs/index.html` go live once merged to `main`.

**What gets saved (MongoDB, database `simulearn`):**
- `conversations` holds one per tester session and side (`untrained` / `fine-tuned`).
- `transcript_iterations` holds one per turn: the adult line and that side's reply, with the model, age, seed and timing in `metadata`.
- `feedback` holds 👍/👎 ratings and notes, linked by `conversation_id` and `version`.

**ZeroGPU limits:** a GPU is borrowed only while a reply is generated (`@spaces.GPU` in `space/app.py`). Each visitor has a daily GPU quota (about 2 min if not logged in to HF, 5 min with a free HF account). One reply uses a few seconds of it, so expect a few dozen turns per tester per day. The first visit after the Space sleeps (48 h without use) takes a few minutes to wake up.

<!-- BEGIN HiPerGator section (issue #9) -->
## Training on HiPerGator

HiPerGator is UF's computing cluster. You don't run jobs on it directly: you log in to a *login node*, then hand jobs to **SLURM**, the queue system, which runs them on a GPU node when one is free. These scripts queue the whole re-run of Phases 0–2, plus the Phase 3 age-4 adapter, with one command. The Python code is the same as on the local PC; only `scripts/env_hpg.sh` and `scripts/slurm/` are HiPerGator-specific.

| File | What it does |
|---|---|
| `scripts/env_hpg.sh` | Loads modules, activates the venv on `/blue`, sets `HF_HOME` (model cache) and `PROJECT_ROOT`. The HiPerGator version of `scripts/env_wsl.sh`. |
| `scripts/slurm/hpg.env.example` | Template for your account, QOS, partition, GPU type and time limits. Copy it to `hpg.env`, which git ignores. |
| `scripts/slurm/train.sbatch` | One training job: `python -m src.train.sft_lora --config <cfg> --run-id <id> --no-eval --resume`. |
| `scripts/slurm/evaluate.sbatch` | One evaluation job: `python -m src.eval.evaluate --config <cfg> --run-id <id> [--adapter <dir>]`. |
| `scripts/slurm/submit_all.sh` | Queues the full chain below. `--dry-run` prints it, `--smoke-only` queues only the smoke tests, `--only <run_name>` queues one run on its own. |
| `configs/hpg/` | The configs for every job, copies of the local Phase 0–3 configs. |

**The chain.** Two smoke tests run first: Qwen-1.5B LoRA and Qwen-7B QLoRA, each a 60-step training job followed by an evaluation job. When both pass (SLURM's `--dependency=afterok`), everything else is queued at once: the four Phase 0 baselines (evaluation only), Phase 1 (Qwen-1.5B LoRA 1 epoch, the same with 10 context turns, SmolLM2-360M LoRA), Phase 2 (Qwen-7B QLoRA) and Phase 3 (the run-3 recipe on the age-4 bucket, 48–59 months, which gives the demo its second age). Each training job is followed by its own evaluation job. If a job fails, the jobs waiting on it are cancelled instead of sitting in the queue. Each run writes to `experiments/<YYYYMMDD-HHMM>_<run_name>/`, SLURM's own logs (`slurm-train-<jobid>.out`, `slurm-eval-<jobid>.out`) included.

**Step by step (first time):**

1. Log in: `ssh <gatorlink>@hpg.rc.ufl.edu` (you type your own password and Duo, nobody else does).
2. Clone the repo into your group's `/blue` space, which is larger and faster than home:
   `cd /blue/<group>/<gatorlink> && git clone https://github.com/xArumos/simulearn.git && cd simulearn`
3. Fill in the settings: `cp scripts/slurm/hpg.env.example scripts/slurm/hpg.env`, then edit `hpg.env`. `sacctmgr show assoc user=$USER format=account,qos` shows your account and QOS; `module spider python` and `module spider cuda` show module names. Never commit `hpg.env`.
4. Create the environment once (installs `requirements.txt`, takes a while): `source scripts/env_hpg.sh --setup`
5. Get the data. CHILDES text is never in git, so it has to be fetched again on HiPerGator. Download the corpora listed in `data/DATA_MANIFEST.md` from TalkBank yourself (your own login) and unzip them into `data/raw/extracted/`, as on the local PC, then rebuild both processed folders:
   `python -m src.data.preprocess --config configs/data_default.yaml --verify-ages` and the same with `configs/data_ctx10.yaml`. Keep the data inside `/blue/<group>`, which only your group can read.
6. Optional but faster: download the models on the login node so jobs don't wait for it: `hf download Qwen/Qwen2.5-1.5B-Instruct`, and the same for `Qwen/Qwen2.5-7B-Instruct` and `HuggingFaceTB/SmolLM2-360M-Instruct`. These models are public; no Hugging Face login is needed.
7. Check the plan without submitting: `scripts/slurm/submit_all.sh --dry-run`. Each line is one `sbatch` command; `JOB_n` stands in for the job id SLURM will assign.
8. Run the smoke tests alone the first time: `scripts/slurm/submit_all.sh --smoke-only`. Watch with `squeue -u $USER`, and read `experiments/*_smoke_hpg/slurm-*.out` when they end. Loss should fall and `metrics.json` should appear.
9. Queue everything: `scripts/slurm/submit_all.sh` (it repeats the two smoke tests as the gate, about an hour of GPU time). You can log out; the jobs keep running. `scancel <jobid>` cancels a job, `sacct -u $USER` lists finished ones.

**One run on its own.** `--only <run_name>` queues just that config, without the smoke gate: a training config becomes a train job plus an eval job that waits for it, a Phase 0 baseline a single eval job. The `run_name` is the one at the top of the config file. For example, to add the age-4 adapter after a chain that was queued without it (`data/processed/age4/` must be on `/blue` first):

    scripts/slurm/submit_all.sh --only qwen1.5b_lora_ep1_age4_hpg --dry-run   # check
    scripts/slurm/submit_all.sh --only qwen1.5b_lora_ep1_age4_hpg

It writes to `experiments/<YYYYMMDD-HHMM>_qwen1.5b_lora_ep1_age4_hpg/`. Add `--stamp <YYYYMMDD-HHMM>` to file it under an earlier chain's stamp.

A single job can also go in by hand, e.g. `sbatch --account <acct> --qos <qos> --partition <part> --gpus <type>:1 --time 04:00:00 scripts/slurm/evaluate.sbatch configs/hpg/phase0/qwen1.5b_base-default_hpg.yaml my_run_id`.
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
