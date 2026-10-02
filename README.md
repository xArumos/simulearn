# SimuLearn

Research notebooks for CHILDES child-language statistics, caregiver-child
conversation dataset construction, SFT preparation, and Qwen LoRA experiments.

## Repository layout

- `notebooks/` — clean, source notebooks. Executed notebook copies are local
  artifacts and are not tracked.
- `data/raw/` — locally supplied corpus archives.
- `data/processed/` — generated analysis tables and training datasets.
- `data/experiments/` — model adapters, checkpoints, and evaluation outputs.

Corpus data, processed data, model files, and notebook execution outputs are
excluded from Git. This keeps the repository mergeable without distributing
corpus archives or committing large/generated artifacts. See
[`data/README.md`](data/README.md) for the local data layout.

## Setup

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

## Notebook workflow

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