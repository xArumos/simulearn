# DECISIONS.md

YELLOW and RED decisions, with what / why / evidence. Newest first.

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
