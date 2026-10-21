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
