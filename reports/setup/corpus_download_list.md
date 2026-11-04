# CHILDES corpora to download (age 4;0–5;11)

_Made 2026-10-15 from the public CHILDES index tables (`python -m src.data.select_corpora`) plus each corpus's description page. Re-tiered the same day for North American English (DECISIONS.md D2). Full ranked table: `corpus_candidates.md`._

**Why a login is needed:** transcript zips at `talkbank.org/data/childes/...?f=zip` return a TalkBank login prompt. Downloading takes a free TalkBank account, so the user downloads them by hand. Claude never handles the credentials.

**Selection rule:**
- North American English by default (Eng-NA + Eng-AAE), because SimuLearn's users are US educators.
- Children in or near 48–71 months.
- Above all, **child ↔ adult back-and-forth conversation**, because the model needs an adult turn followed by a child reply.

Excluded on purpose: story-retelling or monologue corpora (Gillam, Nicolopoulou), child-only peer play with no adult (Garvey, Sawyer), word-naming tests (Paidologos), and clinical-only samples.

## Tier 1: download these now (7)

| # | Corpus | Collection | Ages | Kids | Setting | Why | Corpus page |
|---|---|---|---|---|---|---|---|
| 1 | **HSLLD** | Eng-NA | 3–5 home visits (to ~6) | 83 | Mother–child mealtime, book reading, toy play at home | Best match: natural caregiver talk with many children at 4 and 5 | https://talkbank.org/childes/access/Eng-NA/HSLLD.html |
| 2 | **OCSC** (Ohio Child Speech) | Eng-NA | 4–9 | 303 | Researcher–child tasks in a science museum lab; robot present in ~half | Largest pool of 4–5-year-olds; audio-linked (timing for silence tokens) | https://talkbank.org/childes/access/Eng-NA/OCSC.html |
| 3 | **Hall** (excluded after download: unchecked ASR, no child/ages, see DECISIONS.md D3) | Eng-NA | 4;6–5;0 | 39 | Conversations at home and school | Very large conversational set; mostly the age-4 bucket | https://talkbank.org/childes/access/Eng-NA/Hall.html |
| 4 | **Gelman** | Eng-NA | 1;6–7;0 (subsets) | ~226 dyads | Mother–child picture-book and gender conversations | Several subsamples fall in 4–6 | https://talkbank.org/childes/access/Eng-NA/Gelman.html |
| 5 | **Cameron** | Eng-AAE | 4–5 | ~40 | Assessor–child interactive activities in early-childhood centers | Same age band as SimuLearn; African American English is a North American variety spoken by many US children | https://talkbank.org/childes/access/Eng-AAE/Cameron.html |
| 6 | **Warren-Leubecker** | Eng-NA | 4;6–6;2 (older group) | 10 (+10 toddlers) | Mother/father–child | Clean parent–child data with 5-year-olds | https://talkbank.org/childes/access/Eng-NA/Warren.html |
| 7 | **MacWhinney** | Eng-NA | 0;7–8;0 | 2 | Family recordings by the father | Dense longitudinal data, many sessions at 4–5 | https://talkbank.org/childes/access/Eng-NA/MacWhinney.html |

## Tier 2: optional North American extras, only if a bucket comes up short

| Corpus | Collection | Ages | Note | Corpus page |
|---|---|---|---|---|
| Gleason | Eng-NA | 2;1–5;2 | Parent–child at dinner and in the lab; adds to the age-4 bucket | https://talkbank.org/childes/access/Eng-NA/Gleason.html |
| Weist | Eng-NA | 2;1–5;0 | Caregiver–child, 6 children | https://talkbank.org/childes/access/Eng-NA/Weist.html |
| EllisWeismer | Clinical-Eng (US) | 2;6–5;6 | 138 kids, examiner/parent–child, **includes late talkers** (needs group filtering) | https://talkbank.org/childes/access/Clinical-Eng/EllisWeismer.html |
| CAPIL | Eng-NA | 5 + adults | Narrative-style, but precise pause timing (useful for silence-token experiments) | https://talkbank.org/childes/access/Eng-NA/CAPIL.html |

## UK fallback tier: only if the age-5 bucket is under ~5,000 examples

Using these teaches British vocabulary, phrasing, and spelling. Log a DECISIONS.md entry before using them.

| Corpus | Collection | Ages | Note | Corpus page |
|---|---|---|---|---|
| Fletcher | Eng-UK | 3, 5, 7 | Adult–child interview, ~24 five-year-olds | https://talkbank.org/childes/access/Eng-UK/Fletcher.html |
| Wells | Eng-UK | 1;6–5;0 | Naturalistic home recordings; age-4 bucket | https://talkbank.org/childes/access/Eng-UK/Wells.html |
| Gathercole/Burns | Eng-UK | 3;0–6;4 | Adult–child structured play; 4 kids at 4, 4 at 5 | https://talkbank.org/childes/access/Eng-UK/Gathburn.html |

Every transcript is tagged with its source collection during preprocessing, so the data can be filtered or compared by dialect later.

Citation reminder: cite MacWhinney (2000) plus each corpus's own reference (listed on its page), and acknowledge CHILDES grant NICHD HD082736.
