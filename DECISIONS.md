# DECISIONS.md

YELLOW and RED decisions, with what / why / evidence. Newest first.

---

## 2026-10-19 — D7 (RED, approved by Samaree): Add an age-6 bucket (72–83 months)
**Decided by:** Samaree Lewis ("focus on creating the 6 year old"). This changes the §4 age scope, so it is logged as an approved RED item.

**What:**
- New bucket `age6: {min_months: 72, max_months: 83, age_label: 6}` in `configs/data_default.yaml` and `configs/data_ctx10.yaml`.
- New config key `split_extra_age_range: [72, 83]`. `src/data/preprocess.py` (`load_with_extra_range`) splits the 48–71-month children **exactly as before**, so `age4/` and `age5/` (examples, golden set, splits) are byte-identical and runs 0–4 stay comparable. A child already split keeps that split at age 6, and so does any new child linked to one. Children seen only at 72–83 months are split separately with the same 80/10/10 fractions and seed, stratified by corpus.
- Configs: `configs/phase0/qwen1.5b_strong_age6.yaml` (baseline) and `configs/phase1/qwen1.5b_lora_ep1_age6.yaml` (run-3 recipe).
- Tests: `tests/test_age6_bucket.py` (age4/age5 output unchanged, 6-year-old prompt, 72–83 months only, a child keeps one split across buckets, no child/file/group leakage, new-at-6 children split). The real-data leakage test now also covers age6.

**Why:** SimuLearn targets 4–6-year-olds. Several downloaded corpora already contain 6-year-olds (OCSC 4–9, HSLLD visits to ~6, Warren-Leubecker 4;6–6;2, MacWhinney, Gelman), so no new downloads are needed.

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
