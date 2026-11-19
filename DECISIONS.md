# DECISIONS.md

YELLOW and RED decisions, with what / why / evidence. Newest first.

---

## 2026-11-19 — D12 (YELLOW): Serve the educator product on simulearn.arumos.dev (issue #63)
**What:**
- The educator product (React SPA in `frontend/` + FastAPI API in `src/product/server.py`, issues #58-#61) is served from the desktop at `https://simulearn.arumos.dev`, on demand: `scripts/product_up.sh` / `scripts/product_down.sh`, systemd user unit `simulearn-product.service` (not enabled at boot), server on `127.0.0.1:8000` only.
- **Same tunnel, second hostname.** The existing named tunnel `simulearn-demo` carries both hostnames (demo on `:7860`, product on `:8000`); no second tunnel or credentials file. `tunnel.sh named` now checks every ingress port: it refuses only when none is listening and warns for the ones that are down, so either app can run alone. `DEMO_PASSWORD` is still required whenever the tunnel reaches the demo port.
- **Invite-only accounts** in MongoDB (`scripts/create_user.py`, no sign-up page). `serve_product.sh` refuses to start without an active admin account (`create_user.py has-admin`, which prints no accounts), without the built frontend, or while the demo is running. `product_up.sh` refuses `SIMULEARN_COOKIE_SECURE=0` (plain-http testing only).
- **MongoDB always runs with the product**, because accounts live there. "Saving off" is `product_up.sh --no-save` (`SIMULEARN_SAVE_CHATS=0`: accounts in MongoDB, conversations in memory), not `--no-db`.
- **One GPU app at a time.** `serve_product.sh` and `product_up.sh` refuse while the demo runs; `demo_up.sh` refuses while the product runs. The tunnel unit no longer has `Wants=simulearn-demo.service`, so starting it for the product does not load the demo (the installed copy must be replaced; `product_up.sh` detects an old one).
- **Team only** until issue #57 (Dr. Dever, IRB: educators outside the team) is answered. Accounts are created only for team members.

**Why:** the team needs to try the product the way educators would, from a browser, without a second machine or paid hosting. Reusing the tunnel keeps one set of Cloudflare credentials (outside the repo). Each app loads its own copy of the model, and with the planned 8B 4-bit model (~6 GB, D11) two copies plus generation do not fit in 12 GB, so we don't support running both.

**Evidence:** `tests/test_product_service.py` and `tests/test_tunnel.py` (stub `systemctl`, `docker`, `journalctl`, `cloudflared`, `python`; nothing real is started): start order, `--no-save`, every refusal, the tunnel with one backend down, and the parser for ingress rules. No live run in this PR; Justin's first `product_up.sh` is the end-to-end check.

**Trade-offs:** the product is up only while the desktop and WSL are on. The demo and the product can't be shown at the same time; switching costs a model load (a minute or so).

---

## 2026-11-19 — D11 (RED, proposed; waiting on Justin and Dr. Dever): Replace Qwen; base models from outside countries of concern
**Why:** UF prohibits LLMs developed by organizations in or controlled by a foreign country of concern on any UF computing resource, fine-tunes and LoRA adapters included, with no exceptions (`POLICIES.md` §1). Qwen is developed by Alibaba Cloud (China). Justin found the rule on 2026-11-19, after the HiPerGator chain `20261118-2027` had run.

**What was affected (facts, for the conversation with Dr. Dever and UF Research Computing):**
- HiPerGator, chain `20261118-2027` (2026-11-18): 8 of 11 runs used Qwen. These were the Qwen-1.5B baselines, LoRA runs and age-4 run, and the Qwen-7B smoke and QLoRA runs. The Qwen weights are in the Hugging Face cache on the group's blue storage, next to the trained adapters. The 3 SmolLM2 runs are not affected. Nothing is running or queued.
- Outside UF resources: earlier local runs on Justin's own PC (Phases 0-3), the desktop demo (D10) and the Hugging Face Space (D9) all use Qwen. Whether the rule reaches these (it also covers "processing of any university data") is for Dr. Dever / UFIT to say. The safe course is to switch them too.
- The summit paper names Qwen.
- **Not decided here (needs a human):** whether to delete the Qwen files on HiPerGator, and whether to report the use to UF Research Computing proactively. Recommended: tell Dr. Dever now and open a ticket at https://support.rc.ufl.edu asking what to do with the existing files. Do not delete anything before that answer.

**Proposed replacements.** The criteria: a developer outside the countries of concern, preferably a model family that UF Research Computing itself provides on HiPerGator (its AI models page lists Llama, Gemma and Mistral); a real system role in the chat template (our prompt is a system message); and a size that works for the demo (below).

| Role | Was | Proposed | Developer | Notes |
|---|---|---|---|---|
| Main model (Phase 1 recipe) | Qwen2.5-1.5B-Instruct | **`meta-llama/Llama-3.2-1B-Instruct`** and **`meta-llama/Llama-3.2-3B-Instruct`** | Meta (US) | Run both: 1B is the closest size to the old model, 3B is the likely winner. Gated: Justin accepts the Llama 3.2 license on Hugging Face and logs in himself. Shared adapters must say "Built with Llama". |
| Larger model (Phase 2) | Qwen2.5-7B-Instruct, QLoRA | **`meta-llama/Llama-3.1-8B-Instruct`**, QLoRA | Meta (US) | Same license steps (Llama 3.1). Can be served on the desktop in 4-bit (below). |
| Small comparison | SmolLM2-360M-Instruct | **dropped, not re-run** | Hugging Face (US/France) | Allowed, and its existing Phase 0/1 HiPerGator runs stay valid. Its job (testing whether a much smaller model is enough) is done: it was not. Llama-3.2-1B is now the small end of the comparison. |
| Backups if Llama does not work out | | `google/gemma-3-1b-it` / `gemma-3-4b-it` / `gemma-3-12b-it` (Google, US); `microsoft/Phi-4-mini-instruct` (3.8B, Microsoft, US, MIT, not gated); `mistralai/Mistral-7B-Instruct-v0.3` (Mistral AI, France, Apache 2.0) | | Gemma's template has no separate system role (it is folded into the first user turn), so Llama is the better first choice. |

**Can we go bigger now that we train on HiPerGator?** Training is no longer the limit: the RTX PRO 6000 (96 GB) can do LoRA on an 8B model in bf16, and QLoRA well beyond that. The limit is **serving the demo on the RTX 4070 Ti (12 GB)**. Running a model needs far less memory than training it (no gradients, no optimizer state, short replies), but the weights still have to fit. The demo loads one base model and switches age adapters on and off (`src/demo/chat_demo.py`), so VRAM is roughly the size of one model plus about 1 GB:
- bf16 (2 bytes per parameter): 1B ~2.5 GB, 3B ~6.5 GB → fit. 8B ~16 GB → does not fit in bf16 (it does in 4-bit, next line).
- 4-bit (~0.6 bytes per parameter): 8B ~5.5-6 GB → fits. 12-14B ~8-9 GB → tight but possible. 27B and up, including 70B → do not fit; they would need a server GPU (not HiPerGator for an always-on demo, see `POLICIES.md` §2).
- 8-bit (~1 byte per parameter): 8B ~8.5-9 GB → fits only just, and bitsandbytes 8-bit inference is slow. Not recommended.
- Rough estimates; to be measured.
- **Precision plan:** 1B and 3B: plain LoRA in bf16, served in bf16. 8B: **train with QLoRA (4-bit NF4 base), serve in the same 4-bit** (~6 GB). The adapter then runs under the conditions it was trained in, and the eval (which already loads QLoRA runs in 4-bit) measures exactly what the demo serves. Serving in 4-bit needs a small change to `chat_demo.py` (it loads bf16 today).
- **Bigger is not automatically more child-like.** In Phase 2 the 7B QLoRA had the best loss but replies that were too short (`reports/phase2/phase2_report.md`). So the plan is to train 1B, 3B and 8B with the same recipe and let the metrics and the blind ratings choose. Practical ceiling for the demo: about 8B.

**Plan once approved (to become issues):** new `configs/hpg/` for Llama 1B/3B/8B (run-3 recipe) and a masking test for the Llama tokenizer; re-run Phase 0-3 on HiPerGator with them; 4-bit loading option in the demo, then switch the demo and the Space; retire the Qwen configs and adapters; update CLAUDE.md §5/§8 and the paper. The pipeline keeps the model in the config, so preprocessing, splits and evaluation do not change.

---

## 2026-11-18 — D10 (YELLOW): Self-host the demo and its database on the desktop
**What:** The always-on demo now runs on Justin's desktop (RTX 4070 Ti, WSL2) as a systemd user service (`scripts/serve_demo.sh`, `scripts/systemd/simulearn-demo.service`), and saves chats to the local MongoDB from issue #13 (`docker-compose.yml`) instead of MongoDB Atlas. This replaces the Hugging Face Space as the main way for the team to try the model.
- It binds `127.0.0.1:7860` only; a tunnel exposes it to testers, the LAN cannot reach it.
- It refuses to start without `DEMO_PASSWORD` (new `--require-password` flag in `chat_demo.py`), because the tunnel makes it reachable from outside.
- It loads every age adapter in `configs/demo.yaml` that exists under `experiments/`, uses the GPU when one is visible and the CPU otherwise (new `--device auto|cpu|cuda`).
- If MongoDB is down it still starts and prints `saving OFF`, as before.

**Why:**
- On the Space's ZeroGPU, the per-visitor GPU quota let a tester without an HF account send only about one message (D9, quota update). Asking every tester to make an HF account is friction we don't need.
- Training has moved to HiPerGator (issue #9), so the desktop GPU is free most of the time.
- Atlas is not needed when the demo runs next to a local MongoDB; chats then stay on the team's own machine.

**Evidence (2026-11-18, age-5 adapter, invented test lines):**
- GPU: `serve_demo.sh --selftest` ran on cuda, fine-tuned reply 0.2-0.3 s, untrained 1.2-2.2 s, peak VRAM 2.97 GiB.
- CPU (`CUDA_VISIBLE_DEVICES=""`, simulating a machine without a GPU): ran on cpu, fine-tuned 1.5-1.9 s, untrained ~17 s.
- Service mode on CPU with MongoDB not running: listened on `127.0.0.1` only, printed `saving OFF`, `/config` returned 401 before login. Without `DEMO_PASSWORD` it exits with code 1 and a clear message.

**Trade-offs / fallback:** the demo is up only while the desktop is on and WSL is running (WSL stops when Windows sleeps), and the service must be stopped before any local GPU job (12 GB VRAM). The HF Space and its Atlas database stay deployed as a fallback; nothing in D9 is removed. Same D9 limits apply: team testing only, no educators or outside users until the IRB question is settled.

---

## 2026-11-03 — D9 (RED, approved by Justin and by Dr. Dever): Hosted team demo (D7-D8 are on the age6-bucket branch)
**What:** A browser demo for the team and advisors.
- **App:** the existing Gradio side-by-side (`src/demo/chat_demo.py`), now with an age picker and 👍/👎 ratings, runs on a free Hugging Face Space (CPU).
- **Adapters:** kept in a **private** HF model repo. The page is behind a shared password.
- **Saving:** chats and ratings go to MongoDB Atlas (free M0) through Dante's `MongoTranscriptStore` (`backend/app/main.py`, unchanged), plus a new `feedback` collection.
- **Landing page:** GitHub Pages (`docs/index.html`) links advisors to the Space.

**Why:** Advisors need to try the model without installing anything, and the local demo only runs on Justin's PC.

**Constraints and open items:**
- **Approved by Dr. Dever (reported by Justin, 2026-11-03).** The approval covers the demo as described here. The two items that needed sign-off were:
  - Hosting a CHILDES-derived adapter, even privately (CC BY-NC-SA). The adapter contains no transcript text, but it is a derivative.
  - Storing team test chats. They are team members testing a tool, not participants. **Educators or anyone outside the team must not use it until the IRB question is settled** (Protocol ET00056590 covers only CHILDES analysis).
- No CHILDES text is shipped. `scripts/build_space.py` copies an explicit allowlist of code files and refuses data-like files (tested). `scripts/upload_adapters.sh` uploads only `adapter_*` files.
- Dante's REST routes are **not** exposed on the Space. They have no auth (`owner_id` comes from the client), so anyone could read chats.

**Evidence:**
- CPU timing with 2 threads, mimicking the Space's 2 vCPUs: fine-tuned reply ~2.5 s; untrained reply 22-49 s, because it writes all 60 tokens. Peak RAM 9.9 GB (the Space has 16 GB).
- Change made because of this: the child reply is generated and shown first, and the untrained column fills in afterwards.

**Update (2026-11-03): ZeroGPU instead of CPU basic.** HF now requires PRO to host Gradio Spaces on free cpu-basic (`create_repo` returned 402). Free accounts can host up to 2 ZeroGPU Spaces, so the Space runs on ZeroGPU: `space/app.py` wraps generation in `@spaces.GPU` and moves the model to cuda at startup; `Demo` takes an explicit `device`. torch is pinned to 2.13.0 on the Space (newest on ZeroGPU's supported list); training stays on 2.14.1. Trade-off: each visitor has a small daily GPU quota (~2 min unauthenticated). Checked locally on CPU (decorator is a no-op there): the built Space loads the adapter from the private repo and answers. Deployed 2026-11-03: two startup fixes were needed on ZeroGPU: (1) pin pydantic 2.12.5 (HF installs gradio[mcp]); (2) load the PEFT adapters on the CPU (`torch_device="cpu"`) before moving the model to cuda. The Space reaches RUNNING and the password gate returns 401 without login. Justin verified a real turn on ZeroGPU.

**Update (2026-11-03): quota.** A teammate without an HF account could send only one message. Changes: both columns now come from **one** `@spaces.GPU(duration=15)` call per turn (`build_ui(..., reply_both=...)`; was two calls of 30 s), and the landing page asks testers to sign in to a free HF account (5 min/day instead of ~2) and links the huggingface.co Space page, since that page is what passes the visitor's HF login to ZeroGPU (our understanding; not verified with a second account). Not yet measured how many turns this allows. Pages is served from `justin/demo-hosting` `/docs` until the branch is merged to `main`.

**Also:** an age-4 training run was started for the picker and then stopped by the user, because hosting comes first. The demo launches with age 5 only. Ages 4 and 6 appear automatically once their adapters exist.

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
