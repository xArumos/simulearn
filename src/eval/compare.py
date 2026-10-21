"""Build a comparison table across runs (metrics.json files) with the real-child reference row.

    python -m src.eval.compare experiments/2026*_* --out reports/phase0/comparison.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COLS = [
    ("mean words", lambda m, g: g["mean_words"], "{:.2f}"),
    ("median", lambda m, g: g["median_words"], "{:.0f}"),
    (">20 words", lambda m, g: g["over_20_words_rate"], "{:.1%}"),
    ("len KS ↓", lambda m, g: m.get("length_ks"), "{:.3f}"),
    ("len W1 ↓", lambda m, g: m.get("length_wasserstein"), "{:.2f}"),
    ("MSTTR", lambda m, g: g["msttr_100"], "{:.3f}"),
    ("OOV", lambda m, g: g.get("oov_rate"), "{:.1%}"),
    ("rare", lambda m, g: g.get("rare_word_rate"), "{:.1%}"),
    ("filler", lambda m, g: g["filler_rate"], "{:.1%}"),
    ("short ans", lambda m, g: g["short_answer_rate"], "{:.1%}"),
    ("repet", lambda m, g: g["repetition_rate"], "{:.1%}"),
    ("nonstd", lambda m, g: g["nonstandard_rate"], "{:.1%}"),
    ("silence", lambda m, g: g["silence_rate"], "{:.1%}"),
    ("marker gap ↓", lambda m, g: m.get("child_marker_gap"), "{:.3f}"),
    ("degen ↓", lambda m, g: g["degenerate_rate"], "{:.1%}"),
    ("meta", lambda m, g: g["meta_rate"], "{:.1%}"),
    ("other side", lambda m, g: g["continues_other_side_rate"], "{:.1%}"),
    ("dist-1", lambda m, g: g["distinct_1"], "{:.3f}"),
    ("dist-2", lambda m, g: g["distinct_2"], "{:.3f}"),
    ("loss ↓", lambda m, g: m.get("target_loss", {}).get("loss"), "{:.3f}"),
    ("ppl ↓", lambda m, g: m.get("target_loss", {}).get("perplexity"), "{:.1f}"),
]


def fmt(v, f):
    return "–" if v is None else f.format(v)


def table(runs: list[Path]) -> str:
    rows, ref = [], None
    for r in runs:
        p = r / "metrics.json"
        if not p.exists():
            continue
        m = json.loads(p.read_text())
        ref = ref or m
        rows.append((m["run"]["run_id"], m))
    if not rows:
        return "(no runs)\n"
    head = "| Run | " + " | ".join(c for c, _, _ in COLS) + " |"
    lines = [head, "|---|" + "---|" * len(COLS)]
    r = ref["reference"]
    lines.append("| **real children** | " + " | ".join(
        fmt(None if c in ("len KS ↓", "len W1 ↓", "marker gap ↓", "loss ↓", "ppl ↓") else fn(ref, r), f) for c, fn, f in COLS) + " |")
    for run_id, m in rows:
        lines.append(f"| {run_id} | " + " | ".join(fmt(fn(m, m["generated"]), f) for _, fn, f in COLS) + " |")
    n = {m["n"] for _, m in rows}
    return ("\n".join(lines) + f"\n\nn = {sorted(n)} contexts per run ({rows[0][1]['run']['split']} split, bucket {rows[0][1]['run']['bucket']}). "
            "↓ = lower is better. Rates without an arrow should be close to the real-children row.\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    t = table(sorted(Path(x) for x in a.runs))
    print(t)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(t, encoding="utf-8")


if __name__ == "__main__":
    main()
