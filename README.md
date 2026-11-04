# SimuLearn child-speech LLM

Fine-tunes a small LLM to reply the way a 4- or 5-year-old child would, trained on CHILDES child–caregiver transcripts.

Status: setup in progress. See `STATE.md` for the current state and `CLAUDE.md` for the full project spec.

Data: CHILDES (MacWhinney, B. (2000). *The CHILDES Project: Tools for Analyzing Talk*. 3rd ed. Lawrence Erlbaum.). The transcripts are CC BY-NC-SA and are **never** committed to this repo.

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

## Transcript API

The optional `backend/` service stores conversations and append-only transcript
iterations in MongoDB. Each LLM interaction can be saved as a new iteration,
and clients can retrieve either the latest reconstructed transcript or the
transcript as of a specific iteration. The service stores messages after the
LLM call; it does not invoke a model.

Install and start a local MongoDB instance, then from the repository root run:

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
