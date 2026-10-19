# DECISIONS.md

YELLOW and RED decisions, with what / why / evidence. Newest first.

---

## 2026-10-19 — D8 (approved by Samaree): Best 6-year-old from all usable North American data
**Decided by:** Samaree Lewis ("make the best 6 year old we can ... use all the data").

**What:**
- `configs/data_all.yaml` → `data/processed_all/` (the default `data/processed/` and runs 0–4 are untouched). Corpora: the 6 defaults plus Brown, Kuczaj, Sachs, Gleason, Weist, Braunwald, Bliss, Hall, VanKleeck, Gathercole.
- **Left out:** Hicks, PetersonMcCabe, Gopnik, Nicolopoulou (story retelling or narrative tasks), Garvey and Evans (child–child play, 0–1% adult speech), PLAY and Sprott (no usable 4–6 transcripts in this release).
- **Hall is back in:** the Eng-NA MOR release has human transcripts with a target child and ages (0 files flagged as ASR), unlike the unchecked ASR files behind D3. `exclude_asr: true` still applies.
- **New child-ID rule `dir`** (one folder per child: Brown, Weist). Single-child corpora use `participant_code` (Kuczaj, Sachs, Braunwald), Gleason/VanKleeck use file-name regexes, and Gathercole (several children per file, same children across sessions) uses participant codes. Over-linking is harmless; under-linking leaks.
- **Mixed-age buckets** `age5to6` and `age4to6` with `age_label: auto`: each example's system prompt states that child's own age in years.
- **`data.eval_bucket`** in training/eval configs: train on a mixed bucket, but validate, early-stop and evaluate on `age6`.
- **Experiments** in `configs/age6/`: baselines (default, strong), smoke, then A (age6 only, 20,251 train), B (ages 5–6, 55,727), C (ages 4–6, 80,000 sampled of 170,384). One variable changes: the training data. Run all with `bash scripts/run_age6.sh`.

**Evidence (counts only, Samaree's Eng-NA + OCSC download, 2026-10-19):** age6 103 children, 20,251 / 1,586 / 1,563; age5to6 262 children, 55,727 / 4,985 / 4,987; age4to6 652 children, 170,384 / 14,566 / 14,314. Cross-bucket leakage check: 0 children, files or groups in two splits. 56 tests pass (4 skipped: tokenizer download).

**Note:** the extra corpora change the random split order, so `data/processed_all/` splits are not the same as `data/processed/`. Compare A/B/C with each other and with the age6 baselines in `configs/age6/`, not with runs 0–4.

**Why:** more child speech should give more varied, less generic replies, the main weakness of runs 1–4 ("I don't know" ~5× the real rate). B and C test whether older-but-not-6 children help or blur the age.

---

## 2026-10-19 — D7 (RED, approved by Samaree): Add an age-6 bucket (72–83 months)
**Decided by:** Samaree Lewis ("focus on creating the 6 year old"). This changes the §4 age scope, so it is logged as an approved RED item.

**What:**
- New bucket `age6: {min_months: 72, max_months: 83, age_label: 6}` in `configs/data_default.yaml` and `configs/data_ctx10.yaml`.
- New config key `split_extra_age_range: [72, 83]`. `src/data/preprocess.py` (`load_with_extra_range`) splits the 48–71-month children **exactly as before**, so `age4/` and `age5/` (examples, golden set, splits) are byte-identical and runs 0–4 stay comparable. A child already split keeps that split at age 6, and so does any new child linked to one. Children seen only at 72–83 months are split separately with the same 80/10/10 fractions and seed, stratified by corpus.
- Configs: `configs/phase0/qwen1.5b_strong_age6.yaml` (baseline) and `configs/phase1/qwen1.5b_lora_ep1_age6.yaml` (run-3 recipe).
- Tests: `tests/test_age6_bucket.py` (age4/age5 output unchanged, 6-year-old prompt, 72–83 months only, a child keeps one split across buckets, no child/file/group leakage, new-at-6 children split). The real-data leakage test now also covers age6.

**Why:** SimuLearn targets 4–6-year-olds. Several downloaded corpora already contain 6-year-olds (OCSC 4–9, HSLLD visits to ~6, Warren-Leubecker 4;6–6;2, MacWhinney, Gelman), so no new downloads are needed.

**First real-data check (2026-10-19, Samaree's Eng-NA download only: no OCSC, no Cameron):**
- age6: 38 children, 123 transcripts, **7,894 / 499 / 360** train/val/test examples (above the ~5,000 threshold). Median reply 3 words (mean 4.8).
- Per corpus (train examples): MacWhinney 4,242 (**1 child, 54% of train**), Gelman 2,361, HSLLD 818, Warren 473. Val/test come only from Gelman and HSLLD (5 children).
- age4/age5 outputs were byte-identical with and without the age6 bucket on this real data too.
- Not added: Hicks and PetersonMcCabe (narratives), Evans (child-child play), per the D2/D4 selection rule.
- **Risk:** one child (MacWhinney's Ross) dominates age6 training. Re-run with Justin's full download (OCSC has many 6-year-olds) before training; if one child still exceeds ~25% of train, cap examples per child (YELLOW).

**With OCSC added (2026-10-19, Samaree's Eng-NA + OCSC; still no Cameron):**
- age6: **99 children, 184 transcripts, 19,361 / 1,773 / 1,563** train/val/test examples. Median reply 3 words (mean 5.6).
- Train by corpus: OCSC 11,467 (59%), MacWhinney 4,242 (**21.9%**, down from 54%, now under the 25% line), Gelman 2,361, HSLLD 818, Warren 473. Val/test: 19 children (OCSC 12, Gelman 4, HSLLD 3).
- "I don't know" in real age-6 training targets: 20.5 per 1,000 (OCSC 24.9, Gelman 27.5, HSLLD 12.2). OCSC is not unusually high, so it is not the main source of run 1-4's over-use.
- Real-data leakage test passes for age4/age5/age6. No per-child cap needed for now.

**Open questions:** how many age-6 training examples there are (check `data/processed/age6/stats.md`; the §4 ~5,000 rule applies). OCSC may dominate this bucket (lab tasks with a researcher), which could make the "I don't know" problem worse. Check the per-corpus counts before training.

---

## 2026-10-16 — D6 (YELLOW): Try a 10-turn context window (Phase 1 run 4)
**What:** One experiment with `build.context_turns: 10` (grid value from §8) instead of 6. The data is built into a separate folder, `data/processed_ctx10/` (config `configs/data_ctx10.yaml`), so the default 6-turn data and its splits stay as they are. The splits are identical (same children, same seed), because only the context length changes.
**Why:** Run 1's main weakness is generic "safe" replies ("I don't know" ~5x more than real children; distinct-2 0.64 vs 0.73), and some replies ignore the adult's last turn. **Hypothesis:** more context gives the model more to anchor a specific reply to.
**Evidence so far:** run 1 metrics and samples (EXPERIMENT_LOG.md). The default stays at 6 unless run 4 clearly wins on the primary metrics.
**Outcome (2026-10-16):** mixed. Loss 2.176 vs 2.205 and ~25% fewer "I don't know", but replies are shorter (length KS 0.047 vs 0.031, stable across two seeds). **The default stays at 6 turns for now.** Runs 3 and 4 are both in the blinded review; if raters prefer run 4, switch the default to 10 with a new entry here.

---

## 2026-10-15 — D5: Training and evaluation setup choices
**Decided by:** Claude (GREEN implementation choices; logged for transparency).
- **transformers `Trainer` + our own collator instead of TRL `SFTTrainer`.** The loss masking must be exactly the unit-tested code in `src/train/collator.py`. TRL's arguments change often (CLAUDE.md §5.4); in the installed transformers 5.20, `warmup_ratio`, `logging_dir` and `group_by_length` are already gone. TRL stays installed but unused.
- **Evaluation sample:** every Phase 0/1 run is scored on the same deterministic 1,000-example sample of the validation split (seed 42), so runs are directly comparable and an eval takes about 1 minute. Test is untouched until the end of the phase.
- **Checkpointing:** eval + checkpoint every 1/4 epoch rather than once per epoch, so early stopping on validation loss has something to act on. The best checkpoint by val loss becomes the saved adapter. This meets "save each epoch" more often than required.
- **Loss across model families:** child-token loss is only compared within one tokenizer (Qwen vs Qwen). SmolLM2 uses a different tokenizer, so its loss isn't comparable to Qwen's.

---

## 2026-10-15 — D4: First-pass preprocessing rules (data inspection findings)
**Decided by:** Claude while building the first preprocessing pass. These are the initial rules, not a re-run with changed rules. They are logged so later changes have a baseline.

**What and why:**
- **Our own CHAT reader instead of pylangacq for parsing.** pylangacq 0.23 (rustling backend) stops reading an entire corpus at the first malformed word (it hit `word@c>` in one HSLLD file). `src/data/parse_chat.py` reads headers, main tiers, and time bullets line by line and never fails a whole corpus.
- **Age = completed months from the target child's `@ID`** (`4;09.30` → 57). Cross-checked against pylangacq: every disagreement (11 files in 48–71 months) is pylangacq rounding 30 days up to an extra month. There are no other mismatches.
- **Robot speaker (`OTH`, the Jibo robot in OCSC) and `Media` role = conversation break.** Their turns are removed, the context never crosses them, and a child turn directly after the robot is not a target.
- **Cleaning keeps what the child actually said:** fillers, repetitions `[/]`, retracings `[//]`, and non-standard forms (goed, hafta). Removed: transcriber notation, `[: correct form]`, omitted words (`0is`), partial-word fragments (`&+`, `&~`; configurable), and in-utterance pauses `(.)` (see the D1 future experiment).
- **Child targets dropped** if the turn contains unintelligible material (xxx/yyy/www), is reading aloud (`[+ read]`), or is another language (`[- spa]`). An utterance that is *only* unintelligible stays in context as `(unintelligible)` so turn-taking isn't distorted (otherwise the adult turns on both sides would be merged into one).
- **Context = exactly the previous N=6 turns** (or fewer at the start of a transcript or after a break). It may begin with a child turn; trimming it to begin with an adult turn would have silently made N=5.
- **Child IDs and leakage groups:** HSLLD uses 3-letter child codes. Codes appearing together in one filename (`cal_jak…`) or sharing an exact birth date + sex are put in the same group, because the birth dates show some children have two codes. MacWhinney uses participant codes (CHI = Ross, MAR = Mark), and the brothers form one group because they share files. Cameron uses the child number in the filename. The others have one child per file.
- **Splits are computed once over all children aged 48–71 months**, so a child seen at both 4 and 5 stays in the same split for both buckets.

**Evidence:** `data/processed/age5/stats.md` and `age4/stats.md`; 52 unit tests pass, including leakage on the real data and the masking test on both tokenizers.

---

## 2026-10-15 — D3: Exclude unchecked ASR transcripts (all of Hall, MacWhinney `0older-ASR`/`0young-ASR`)
**Decided by:** Claude (data-quality filter); flagged to the user.

**What:** Files whose header says `Unchecked output of ASR model` are excluded (`exclude_asr: true`). That covers all 40 Hall files and 122 MacWhinney files. Hall is removed from the default corpus list.

**Why:** These are automatic speech-recognition transcripts nobody checked. Speakers are only `PAR0`/`PAR1`, with no target child and no ages, so the child can't be identified and the age-per-transcript rule (§7.1) can't be applied. ASR errors are also not real child speech. Hall was recommended in Tier 1 from its corpus page ("conversational interactions, 4;6–5;0"), but the current release no longer has the human transcripts. Its loss doesn't threaten the bucket sizes (age 5: 30,356 training examples; age 4: 34,609).

---

## 2026-10-15 — D2: Default to North American English corpora (Eng-NA + Eng-AAE)
**Decided by:** the team in a side discussion; relayed by Justin.

**What:**
- The default corpus set is Eng-NA plus Eng-AAE. Download now (7): HSLLD, OCSC, Hall, Gelman, Cameron (Eng-AAE), Warren-Leubecker, MacWhinney.
- Fletcher is out of Tier 1. Fletcher, Wells, and Gathercole/Burns (all Eng-UK) become a **UK fallback tier**. Use them only if the age-5 bucket falls short of ~5,000 training examples (§4). If that happens, log a new entry here before using them.
- Keep Cameron. African American English is a North American variety spoken by many US children. Dr. Dever can still confirm, but this is not a blocker.
- Preprocessing tags every transcript with its source collection (`Eng-NA` / `Eng-AAE` / `Eng-UK`), so the data can be filtered or compared by dialect later.

**Why:** SimuLearn's users are US educators (UF). UK transcripts would teach British vocabulary, phrasing, and spelling ("mum", "have you got", "colour").

**Changes made:** `reports/setup/corpus_download_list.md` re-tiered. `src/data/select_corpora.py` defaults to `Eng-NA Eng-AAE`; pass `--collections Eng-NA Eng-AAE Eng-UK` to include the UK.

---

## 2026-10-15 — D1: Silence token format is `<SILENCE FOR X SECONDS>`
**Decided by:** the team in a side discussion; relayed by Justin.

**What:** The final format is `<SILENCE FOR X SECONDS>`. The "INTERACTIONS" wording from the abstract is dropped entirely. The §7.3 plan is unchanged:
- Insert the token when the gap between utterances is **≥ 2.0 s** (configurable).
- X = the gap rounded to the nearest whole second, capped at 10.
- Insert it as plain text at the start of the following turn, whichever speaker it is.
- No new special tokens in the tokenizer in the first pass.

**Note for the platform side (later, not this repo's job yet):**
- The model can't actually pause; it just writes the tag. SimuLearn should detect the tag, strip it from the displayed text, and either wait X seconds or show a "thinking…" indicator.
- SimuLearn may also insert silence tags into the educator's turns based on how long they actually waited ("wait time"). That matches the training format, where the tag starts whichever turn follows the gap.

**Possible future experiment (not now):** turn in-utterance pauses like `(.)` into `...` instead of dropping them. This is a cleaning-rule change (YELLOW), so it needs its own entry here first.
