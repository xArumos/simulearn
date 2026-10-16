"""Blinded human-review packet (CLAUDE.md §9.3) for the golden review set.

    python -m src.eval.review_packet --bucket age5 --phase phase1 \
        --system baseline=configs/phase0/qwen1.5b_default.yaml \
        --system lora=configs/phase1/qwen1.5b_lora_base.yaml:experiments/<run>/adapter

For each golden item: the context, then the real child reply and each system's reply as A, B, C, ...
in a per-item random order. The key (which letter is which system) goes in a separate file.
Outputs (git-ignored, they contain CHILDES text): reports/<phase>/review_packet.md, review_ratings.csv,
review_key.json. The user/team does the rating; no outside participants (IRB).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import string

from src.eval.evaluate import STRONG_PROMPT, read_jsonl, with_system
from src.eval.generate import generate_replies
from src.utils.config import load_config, resolve
from src.utils.modeling import load_model, load_tokenizer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="age5")
    ap.add_argument("--phase", required=True)
    ap.add_argument("--system", action="append", required=True, help="name=config.yaml[:adapter_path]")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()

    golden = read_jsonl(resolve("data/processed") / a.bucket / "golden_review.jsonl")
    replies: dict[str, list[str]] = {"real": [e["messages"][-1]["content"] for e in golden]}
    for spec in a.system:
        name, rest = spec.split("=", 1)
        cfg_path, _, adapter = rest.partition(":")
        cfg = load_config(resolve(cfg_path))
        cfg["model"]["adapter"] = adapter or cfg["model"].get("adapter")
        tok = load_tokenizer(cfg["model"]["name"])
        model = load_model(cfg["model"])
        ev = cfg["eval"]
        items = golden
        if ev.get("prompt_variant", "default") == "strong":
            items = with_system(golden, STRONG_PROMPT.format(age=cfg.get("age_label", 5)))
        replies[name] = generate_replies(model, tok, items, temperature=ev["temperature"], top_p=ev["top_p"],
                                         max_new_tokens=ev["max_new_tokens"], seed=ev["seed"], batch_size=16,
                                         max_length=ev["max_length"])
        del model

    out = resolve("reports") / a.phase
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)
    systems = list(replies)
    key, md = {}, [f"# Review packet ({a.bucket}, {len(golden)} items)", "",
                   "For each item, read the conversation, then rate **every** reply (A, B, C, ...) in `review_ratings.csv`:",
                   "child-likeness, coherence, age-appropriateness (1 = poor, 5 = excellent), plus notes.",
                   "One of the replies is what the real child said. Do not look at `review_key.json` until you are done.", ""]
    rows = []
    for i, e in enumerate(golden, 1):
        order = systems[:]
        rng.shuffle(order)
        letters = dict(zip(string.ascii_uppercase, order))
        key[e["id"]] = letters
        md.append(f"## Item {i}")
        md.append("")
        for m in e["messages"][1:-1]:
            who = "Child" if m["role"] == "assistant" else "Adult"
            md.append(f"> **{who}:** {m['content']}  ")
        md.append("")
        for L, sysname in letters.items():
            md.append(f"- **{L}:** {replies[sysname][i - 1] or '(empty)'}")
            rows.append({"item": i, "example_id": e["id"], "reply": L, "child_likeness_1to5": "", "coherence_1to5": "",
                         "age_appropriateness_1to5": "", "notes": ""})
        md.append("")
    (out / "review_packet.md").write_text("\n".join(md), encoding="utf-8")
    with open(out / "review_ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "review_key.json").write_text(json.dumps(key, indent=1))
    print(f"wrote {out / 'review_packet.md'} ({len(golden)} items, systems: {systems})")


if __name__ == "__main__":
    main()
