# CLAUDE.md — Child-Speech LLM Fine-Tuning (SimuLearn)

You are working autonomously, inside the guardrails below, on a research prototype. Read this whole file before doing anything. At the start of every session, also read `STATE.md` (see §12) so you can resume where the last session stopped.

The person you are working for is a computer science undergraduate with **little prior experience in LLM fine-tuning**. Do the work, but explain what you did and why in plain language in your reports. Define jargon the first time you use it (LoRA, perplexity, etc.).

---

## 1. Goal (priority order)

1. **Primary goal:** fine-tune a small LLM so that, given a caregiver/adult utterance (plus a few turns of context), it replies **as a child of a specific age would**. Child-likeness is the #1 priority, ahead of fluency, helpfulness, or safety-style polish.
2. Build a reproducible pipeline: download → preprocess → train → evaluate → report.
3. Document everything so the team (Samaree Lewis, Justin Perkins, Dante Lopez; advisor Dr. Daryn Dever, UF College of Education) can reuse it on HiPerGator later.

Context: this model will be the "child" in SimuLearn, a platform where early childhood educators practice with an AI-roleplayed child. Current LLMs write adult-sounding text, so we fine-tune on real child–caregiver transcripts from CHILDES.

**Scope of this file:** supervised fine-tuning (SFT) with LoRA, then QLoRA, plus evaluation. **DPO / GRPO / RL are OUT OF SCOPE for now.** Do not start them.

## 2. Hard constraints (do not violate)

- **Data source / IRB:** the project's IRB exempt determination (Protocol ET00056590) covers *only analysis of publicly available data from CHILDES (talkbank.org/childes)*. Therefore:
  - Use only CHILDES transcripts (and tools derived from them). No other datasets without asking.
  - **No human participants.** Do not design anything that recruits or surveys outside people. Manual review of model outputs is done by the user/team only.
- **Data licensing:** CHILDES is CC BY-NC-SA and TalkBank has ground rules. **Never commit raw or processed CHILDES text to git, never upload it anywhere, never paste large chunks into reports.** `data/` must be in `.gitignore`. Short illustrative snippets (a few lines) in local reports are fine. Cite MacWhinney (2000), *The CHILDES Project*, in any write-up you draft.
- **Never ask for, store, or echo passwords/tokens.** If a step needs the user to log in, tell them to do it themselves (see §5).
- **No pushing to GitHub, no creating remote repos, no spending money (paid APIs, cloud GPUs)** without explicit user approval.
- Work inside the project directory and its virtual environment. Do not modify system-wide Python, drivers, or OS settings.

## 3. Autonomy rules

**GREEN — just do it, and log it:**
- Create/modify code, configs, tests, and docs inside the project.
- Install packages into the project's virtual environment.
- Preprocess data; run unit tests; run smoke tests.
- Run training and evaluation on the local GPU, up to the budgets below.
- Tune hyperparameters **within the grid in §8** (change **one variable at a time** and record why).
- Generate samples and review packets.

**YELLOW — do it only after writing a short entry in `DECISIONS.md` (what, why, evidence), then continue unless the budget says stop:**
- Changing the validation metric set, the context window length, or the silence-token rule.
- Re-running preprocessing with different cleaning rules.
- Adding an extra training run beyond the per-phase budget (max +2).

**RED — stop and ask the user (write the question in `STATE.md` under "Waiting on user", then end the session):**
- **Switching to a different base model** than the ones listed in §8. If results look poor and you believe a different model would help, write a recommendation in `DECISIONS.md` with the evidence (metrics, samples, what you tried) and **wait**.
- Changing the age scope (§4), using any data other than CHILDES, or using audio.
- Installing anything outside the virtual environment; deleting data or experiment results.
- Anything involving git remotes, accounts, logins, API keys, or money.
- Anything that might conflict with the IRB constraints in §2.

**Budgets (local machine):**
- Max **~3 hours wall-clock per single training run**. If a run would exceed this, shrink data/sequence length or ask.
- Max **6 training runs per phase** (Phase definitions in §8).
- **Stop condition for a phase:** the phase's exit criteria are met, OR the budget is used, OR **3 consecutive experiments fail to improve** the primary metrics over the current best. Then write a phase report (§11) and stop for user review.

## 4. Scope decisions (already made by the user)

- **Age range:** child age **48–71 months (4;0–5;11)**.
- **Pilot bucket:** start with **ages 5 only = 60–71 months** to get quick, clean iterations. Then repeat for **48–59 months (age 4)** using the identical pipeline. Long-term plan: a **separate model per age bucket**.
  - **Fallback:** if the age-5 bucket yields fewer than ~5,000 training examples after cleaning, tell the user, and (YELLOW→RED, ask) propose training on the full 48–71 range with the age stated in the system prompt instead.
- **Model's role:** the model plays the **child**. Adults (mother, father, investigator, teacher, etc.) are the "user" side of the chat; the child is the "assistant" side.
- **Language:** English transcripts only.
- **Hardware now:** a single **NVIDIA RTX 4070 Ti** (12 GB VRAM; verify with `nvidia-smi` since a Ti Super has 16 GB) on the user's own PC. Later the team moves to HiPerGator (SLURM, bigger GPUs). **Write code so moving to HiPerGator only needs config changes** (paths, model name, batch size), and keep SLURM-specific stuff out of the core code.

## 5. Environment setup

1. Detect the OS and GPU (`nvidia-smi`, Python version). If the OS is Windows, **prefer WSL2 (Ubuntu)** for training because the GPU tooling (bitsandbytes, flash-attn, etc.) is more reliable there. If WSL2 isn't set up, tell the user how to set it up and pause, or fall back to native Windows if everything installs cleanly.
2. Create a virtual environment (`python -m venv .venv` or `uv`). Pin versions in `requirements.txt` / `pyproject.toml` after it works.
3. Install: PyTorch (CUDA build matching the driver), `transformers`, `peft`, `trl`, `datasets`, `accelerate`, `bitsandbytes`, `pylangacq`, `pandas`, `numpy`, `scipy`, `pyyaml`, `pytest`, `tensorboard`. `unsloth` is optional. Only use it if plain PEFT is too slow or too memory-hungry, and log the decision.
4. **Library APIs change quickly (especially `trl` and `pylangacq`).** Read the installed version's docs/source before relying on any function signature recalled from memory. Don't assume.
5. Run a **GPU smoke test**: load Qwen2.5-1.5B-Instruct in bf16, generate a few tokens, report VRAM use.
6. Record the exact environment (`pip freeze`, GPU, driver, CUDA) in `experiments/ENVIRONMENT.md`.

## 6. Data acquisition (CHILDES)

**Verified facts:** as of this writing, CHILDES transcripts require a **free TalkBank account (registration + login)**; access is otherwise open. The CHILDES site also says the repository is "under review for potential modification," so availability may change. Transcripts are in CHAT (`.cha`) format, organized per corpus at `https://childes.talkbank.org/data/` (the per-corpus download pages are reachable from the "Index to Corpora" at `https://talkbank.org/childes/access/index.html`).

**Approach — in this order:**
1. Check whether `pylangacq` can download or read corpora directly (it supports reading CHAT from local files and, in some versions, URLs). Test with one small English corpus.
2. If direct downloads require authentication, **stop and ask the user to do the login step**. Ask them to (a) register/log in at talkbank.org, and (b) either download the chosen corpus transcript zips by hand into `data/raw/` or provide a wget/cookie-based method they are comfortable with. Do not handle their credentials yourself.
3. Keep the manual part small. **Do not ask the user to download everything.** First, write a script that uses corpus-level metadata or a small sample to decide which **English corpora** contain children aged 4;0–5;11, then give the user a short, specific list of corpora to download (corpus name + link), prioritizing the ones with the most children/transcripts in the age range.
4. Whatever method is used, record exactly which corpora and download date were used in `data/DATA_MANIFEST.md` (names only, no content).

**About the BEACON dataset (Zheng et al., 2026):** it is an audio-centric, child-utterance-only dataset (timestamp-corrected clips + raw CHAT text). It is **not** needed for this text pipeline, and because it keeps only child turns it lacks the caregiver side we need as context. **Use the original `.cha` transcripts as the primary source. Do not use BEACON data unless the user says so**, because the IRB form lists talkbank.org/childes as the data source and BEACON is a separate release. Ask the user to check with Dr. Dever first.

## 7. Preprocessing specification

Write this as a testable library in `src/` with unit tests in `tests/`.

### 7.1 Filtering
- Parse each `.cha` file. Get the **target child's age per transcript** from the `@ID` header (format like `4;06.00`; verify with the actual files and `pylangacq`'s age helpers).
- Keep a transcript only if language is English and the target child's age in that transcript is in the bucket (pilot: 60–71 months). Age must be evaluated **per transcript**, not per corpus (longitudinal corpora span many ages).
- Keep a stable **child ID** (corpus + participant identifier) for every transcript. You need it for splitting (§7.4).
- Report: number of corpora, children, transcripts, utterances, child turns, and total words kept per bucket, and how many were dropped at each filter step.

### 7.2 Cleaning utterance text
Convert CHAT notation to plain text. At minimum:
- Drop or handle: `xxx`/`yyy`/`www` (unintelligible/untranscribed), `&=` gestures/actions, `[/]`, `[//]`, `[?]`, `+...` markers, `@` word-form markers, `(.)` pause marks, `<...>` scoping, and non-speech events. Keep real words, fillers (`um`, `uh`), and the child's non-standard forms (e.g. "goed", "wanna", "gonna"). **Do not "correct" child grammar.** That's the signal we want to learn.
- Child turns containing unintelligible material (`xxx`, etc.) after cleaning: **drop the turn** from training targets. They may stay as context if they remain readable.
- Remove turns that are empty after cleaning.
- Keep a counter of every rule that fired so we can see what is being thrown away. Print it in the report.
- Write unit tests with real-looking CHAT lines (invent them. Do not copy corpus text into the repo) for each rule.

### 7.3 Silence tokens
- Use the timing information (CHAT time-mark bullets, in ms) where a transcript has it. Many corpora have **no** time marks. Then no silence tokens are inserted for that transcript, and you must report what fraction of transcripts have usable timing.
- If the gap between the end of the previous utterance and the start of the next utterance is **≥ 2.0 s**, insert a token `<SILENCE FOR X SECONDS>` where X is the gap rounded to the nearest whole second, capped at 10.
- Insert it as plain text at the start of the following turn (whichever speaker). Treat it as ordinary text. Do **not** add new special tokens to the tokenizer in the first pass (it requires training new embeddings. Revisit only as a documented experiment).
- Note: the team's notes use `SECONDS`, while the project abstract says `INTERACTIONS`. **Use `SECONDS`** and flag the inconsistency to the user in the first report.
- Also report: mean/median of detected gaps, token frequency. Make the threshold configurable.

### 7.4 Building training examples
- Build chat-formatted examples: `system` + alternating `user` (any adult/other speaker) and `assistant` (the target child). **Merge consecutive turns by the same side.** Multiple adults map to `user`; other children map to `user` too (keep a note of this).
- System prompt (keep it short and fixed per bucket), e.g.: `You are a {age}-year-old child talking with a caregiver. Reply the way a real child of that age would.` Fill `{age}` from the bucket.
- Each example = the previous **N = 6** turns of context (configurable) ending with an adult turn, and the **target = the next child turn**. One example per child turn. Skip targets dropped in §7.2.
- **Loss masking:** compute loss **only on the child (assistant) target tokens**, not on the system prompt or adult turns. Qwen's default chat template does not mark assistant spans for TRL's `assistant_only_loss`, so implement masking explicitly (custom collator or label masking) and **write a unit test that decodes the unmasked label tokens and asserts they equal exactly the child target**.
- Max sequence length: start at **512** tokens.

### 7.5 Train / validation / test splits — prevent leakage
- **Split by child (and therefore by transcript), never by random utterance.** The same child across sessions repeats words, family names, routines; random splitting would inflate results.
- Default: **80% / 10% / 10% of children**, fixed random seed (42), saved to `data/processed/splits.json` as lists of child IDs.
- If a corpus has very few children, keep the split at the child level anyway and report counts.
- Add an automated **leakage test**: assert no child ID appears in more than one split, and no transcript file appears in more than one split.
- Additionally, set aside a small **"golden review set"** from the test split: ~30 conversation openings (context + the real child reply) used for human review (§9.3). Record their IDs.
- *(Clarification for the user's idea of "train on 50 transcripts, hold out 3–5": same spirit, but we hold out whole **children**, with a validation split for tuning plus a test split touched only at the end of a phase. Our actual numbers will be much larger than 50.)*

### 7.6 Outputs
- `data/processed/{bucket}/train.jsonl`, `val.jsonl`, `test.jsonl` (chat format), `golden_review.jsonl`, `splits.json`, and `data/processed/{bucket}/stats.md` (counts, length distributions, silence-token stats, rule counters).
- Make preprocessing deterministic and re-runnable with one command.

## 8. Training plan

### Phase 0 — Baselines (no training)
- Models: `Qwen/Qwen2.5-1.5B-Instruct` and `HuggingFaceTB/SmolLM2-360M-Instruct`.
- Prompt each with the same system prompt used for training (and a second variant with a stronger "talk like a young child" instruction). Generate replies for the validation/test contexts.
- Evaluate with §9. This is the bar every fine-tuned model must beat.
- **Exit:** baseline metrics saved for both models.

### Phase 1 — LoRA on the small models (local GPU)
- Start with **Qwen2.5-1.5B-Instruct, bf16, LoRA**. Then **SmolLM2-360M-Instruct** as the comparison.
- Starting config: `r=16, lora_alpha=32, lora_dropout=0.05`, target all linear projection layers, learning rate `2e-4` (cosine, warmup ~3%), **1–3 epochs**, effective batch size 16–32 via gradient accumulation, gradient checkpointing on, max length 512, seed 42, save checkpoint each epoch, early stop on validation loss.
- **Allowed tuning grid (GREEN):** learning rate {1e-4, 2e-4, 5e-4}, rank {8, 16, 32}, epochs {1, 2, 3}, context turns {3, 6, 10}. Change one variable at a time.
- **First run must be a smoke test:** ~200 examples, ~50–100 steps. Verify loss decreases, masking is right, no OOM, samples are not garbage. Only then run the real job.
- **Exit:** best LoRA model beats baseline on the primary metrics in §9.1 and has been through a manual review packet (§9.3), OR the stop condition fires.

### Phase 2 — QLoRA on a larger model (local GPU, 4-bit)
- Goal: see whether a bigger model + 4-bit quantization improves child-likeness. Candidate that should fit in 12 GB with short sequences and gradient checkpointing: **`Qwen/Qwen2.5-7B-Instruct`** (4-bit NF4, double quant, bf16 compute). If it will not fit, try **3B**. Record VRAM, speed, and results.
- Reuse the best Phase 1 hyperparameters as the starting point. Compare to the best LoRA result and to baselines.
- **Note:** the 70B model in the team's notes is for HiPerGator only. Do not try it locally.
- **Exit:** a documented comparison table (LoRA small vs QLoRA large) and a recommendation for what to run on HiPerGator.

### Phase 3 — Repeat for the second age bucket
- Run the best configuration on 48–59 months. Compare buckets (are the age-4 outputs measurably different from age-5 outputs?). Report findings only; do not start per-bucket tuning without asking.

## 9. Evaluation and verification

Child-likeness is the target, so verify it from several angles. **Never report a result from a single metric.**

### 9.1 Automatic metrics (computed on the held-out **test** children; use **validation** for tuning decisions)
For every model (baselines and fine-tuned), generate one reply per context with fixed decoding settings (temperature 0.7, top-p 0.9, max 60 new tokens, seed fixed) and compare the generated replies against the **real child replies** from the same age bucket:
1. **Validation loss / perplexity** on child target tokens (fine-tuned models only).
2. **Utterance length**: mean words per reply (an MLU-like proxy; note it counts words, not morphemes), and the **distribution** (compare to the real distribution with a KS statistic or Wasserstein distance). Generated replies that are much longer than real ones are the classic failure.
3. **Vocabulary**: type-token ratio over a fixed sample size; fraction of generated words not in the training child vocabulary; average word rarity (e.g., share of words outside the top-N most frequent child words).
4. **Disfluency / child markers**: rate of fillers (um, uh), short answers ("yeah", "no"), repetitions, non-standard forms vs real.
5. **Degeneration checks**: empty replies, repeated loops, replies containing meta text ("As a child", "I am a 5-year-old", "Sure!", assistant-style phrasing), replies that continue the adult's side of the conversation.
6. **Silence-token behavior**: does the model emit `<SILENCE FOR X SECONDS>` in plausible places and rates?
7. **Diversity**: distinct-1 / distinct-2 across replies.

Save all of these to `experiments/<run_id>/metrics.json` plus a comparison table across runs. Treat the numeric thresholds as **relative to baseline and to the real held-out data**. There are no fixed pass marks yet. Define "better" as: closer to the real-data distribution on length/vocabulary, lower degeneration rate, and no worse validation loss.

### 9.2 Automated sanity gates (must pass before any run is reported)
- Unit tests pass (`pytest`).
- Leakage test passes (§7.5).
- Label-masking test passes (§7.4).
- Decoding is reproducible (same seed → same outputs).
- Train and validation metrics are plausible (e.g., no near-zero loss, which usually signals leakage or a masking bug).

### 9.3 Manual review packet (the user will do the rating)
For each completed phase, generate `reports/<phase>/review_packet.md` (and a `.csv` for rating) with **30 items** from the golden review set. Each item shows: context, the **real child reply**, and the model replies (baseline, best LoRA, etc.) in **randomized, blinded order** (keep the key in a separate file). Include rating columns: child-likeness (1–5), coherence (1–5), age-appropriateness (1–5), and free-text notes. When the user returns ratings, compute averages per system and report them alongside the automatic metrics.

*(Optional, off by default: an LLM-as-judge pass. Do it only if the user provides an API key and approves the budget.)*

### 9.4 The verification loop (run this for every experiment)
1. **Hypothesis:** write one sentence in `experiments/<run_id>/README.md` (e.g., "Lower LR reduces over-long replies").
2. **Config:** one YAML file in `configs/`; change **one** thing from the current best.
3. **Smoke test → real run**, logging to `experiments/<run_id>/train.log` with TensorBoard.
4. **Evaluate** (§9.1) and run the gates (§9.2).
5. **Inspect 20 generated samples yourself** (read them, don't just trust numbers) and note what you see.
6. **Compare** to the current best and to the baseline in a table. Record: improved / same / worse.
7. **Log** an entry in `experiments/EXPERIMENT_LOG.md` (hypothesis, config diff, metrics, observations, next step).
8. **Decide** the next experiment, or stop per §3. If results are poor and you suspect the model is the limiting factor, write the RED recommendation and stop.

## 10. Recommended repository layout

```
child-llm/
├── CLAUDE.md                # this file
├── STATE.md                 # live handoff between sessions (§12)
├── DECISIONS.md             # YELLOW/RED decisions with evidence
├── README.md                # how to reproduce, in plain language
├── requirements.txt         # pinned after it works
├── .gitignore               # data/, experiments/*/checkpoints/, .venv/, *.safetensors
├── configs/                 # one YAML per experiment (model, data, lora, train, eval)
├── data/                    # NEVER committed
│   ├── raw/                 # downloaded .cha files
│   ├── interim/
│   ├── processed/{bucket}/  # train/val/test .jsonl, splits.json, stats.md
│   └── DATA_MANIFEST.md     # which corpora, when (names only)
├── src/
│   ├── data/                # parse_chat.py, clean.py, silence.py, build_examples.py, split.py
│   ├── train/               # sft_lora.py, sft_qlora.py, collator.py (loss masking)
│   ├── eval/                # generate.py, metrics.py, review_packet.py
│   └── utils/               # seeding, logging, config loading
├── scripts/                 # thin CLI wrappers: preprocess.sh, train.sh, evaluate.sh (+ slurm/ later)
├── tests/                   # cleaning rules, leakage, masking, silence logic
├── experiments/
│   ├── ENVIRONMENT.md
│   ├── EXPERIMENT_LOG.md
│   └── <run_id>/            # config.yaml, README.md, train.log, metrics.json, samples.jsonl, checkpoints/ (ignored)
└── reports/<phase>/         # phase_report.md, review_packet.md/.csv, comparison tables
```

Conventions: `run_id = YYYYMMDD-HHMM_<model>_<short-change>`. Everything is configured via YAML (no hard-coded paths) so the same code can run on HiPerGator by swapping the config. Experiment tracking is plain files + TensorBoard. Do **not** use Weights & Biases or any online service unless the user asks.

## 11. Reporting

At the end of each phase (and when stopping early), write `reports/<phase>/phase_report.md` for a non-expert reader:
- What was done, in 5–10 plain sentences.
- A table of all runs: config differences, key metrics, verdict.
- Best model, where its adapter is saved, how to reproduce it with one command.
- 5–10 representative samples (real vs baseline vs fine-tuned), kept short.
- Problems found, what you tried, what you recommend next (flag any RED item).
- A **"for the team deck"** paragraph (3–5 bullets) the user can paste into progress slides.
- Be honest about uncertainty. If results are weak or something looks wrong, say so plainly instead of dressing it up.

## 12. Session hygiene (you lose memory between sessions)

Keep `STATE.md` updated at every meaningful step, and always before ending a session. Contents:
- **Current phase and step**
- **Done so far** (short list)
- **Best model so far** (run_id, key metrics)
- **Next planned actions** (ordered)
- **Waiting on user** (questions/blockers, e.g., "need login + corpus downloads", "need review ratings")
- **Known issues**

Run long jobs in the background with logs and checkpoints so they can be resumed if the PC sleeps or the session ends. Ask the user to disable sleep during training if it is a problem.

## 13. First session checklist (do these in order)

1. Read this file; create the repo layout in §10, `.gitignore`, and `STATE.md`.
2. Environment setup and GPU smoke test (§5).
3. Write the corpus-selection script and the short list of corpora for the user to download (§6). **Then pause and ask the user to download them** (or confirm an authenticated method). Do this early, because it is the user-blocking step. While waiting, continue with steps 4–5 using synthetic sample CHAT lines (invented, not copied).
4. Implement and unit-test cleaning, silence tokens, example building, masking, and splitting (§7).
5. When real data arrives: run preprocessing, produce `stats.md`, and report counts. Check the §4 fallback (is the 5-year-old bucket big enough?).
6. Phase 0 baselines → Phase 1 LoRA smoke test → first real run.
7. Update `STATE.md`; give the user a short summary of where things stand and what they need to do next.
