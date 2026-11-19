"""Build a comparison table across runs (metrics.json files) with the real-child reference row.

    python -m src.eval.compare experiments/2026*_* --out reports/phase0/comparison.md

Or a paired table (e.g. the same recipe on two machines), flagging differences beyond the noise floor:

    python -m src.eval.compare --pair experiments/<local_run> experiments/<hpg_run> --out reports/hpg/hpg_vs_local.md
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


def load(run: Path) -> dict | None:
    p = Path(run) / "metrics.json"
    return json.loads(p.read_text()) if p.exists() else None


def table(runs: list[Path]) -> str:
    rows, ref = [], None
    for r in runs:
        m = load(r)
        if m is None:
            continue
        ref = ref or m
        rows.append((m["run"]["run_id"], m))
    if not rows:
        return "(no runs)\n"
    # The real-children row is taken from the first run, so every run must share its bucket and split.
    for key in ("bucket", "split"):
        seen = sorted({m["run"][key] for _, m in rows})
        if len(seen) > 1:
            raise ValueError(f"runs mix {key}s {seen}; build one table per {key}")
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


# Paired comparison (same recipe, two runs). A difference counts as real only when it is larger than the
# noise floor: the spread seen when the same adapter is re-sampled with a second seed (runs 3 and 4,
# *_evalseed4321 in EXPERIMENT_LOG.md), rounded up. Loss involves no sampling, so its floor only covers
# numeric differences between GPUs.
FLAG = "**!**"
DELTA_COLS = [  # (column name in COLS, noise floor)
    ("mean words", 0.2),
    ("len KS ↓", 0.005),
    ("short ans", 0.015),
    ("marker gap ↓", 0.004),
    ("degen ↓", 0.005),
    ("dist-2", 0.02),
    ("loss ↓", 0.005),
]


def _delta_cell(fn, f, noise, a, b) -> str:
    va, vb = fn(a, a["generated"]), fn(b, b["generated"])
    if va is None or vb is None:
        return f"{fmt(va, f)} → {fmt(vb, f)}"
    d = vb - va
    sign = "+" if d >= 0 else "−"
    if "%" in f:  # rates: show the change in percentage points
        diff = f"{abs(d) * 100:.1f} pts"
    else:
        diff = f.format(abs(d))
    flag = f" {FLAG}" if abs(d) > noise + 1e-12 else ""
    return f"{fmt(va, f)} → {fmt(vb, f)} ({sign}{diff}){flag}"


def delta_table(pairs: list[tuple[Path, Path]], with_reference: bool = False) -> str:
    """One row per pair A → B. with_reference adds, under each pair, the same shift in the real-child
    replies (useful when A and B are different age buckets: does the model move the way children do?)."""
    cols = {c: (fn, f) for c, fn, f in COLS}
    head = "| Pair (A → B) | " + " | ".join(c for c, _ in DELTA_COLS) + " |"
    lines = [head, "|---|" + "---|" * len(DELTA_COLS)]
    for a_dir, b_dir in pairs:
        a, b = load(a_dir), load(b_dir)
        label = f"{Path(a_dir).name} → {Path(b_dir).name}"
        if a is None or b is None:
            cells = ["no metrics yet"] + ["–"] * (len(DELTA_COLS) - 1)
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
            continue
        cells = [_delta_cell(*cols[c], noise, a, b) for c, noise in DELTA_COLS]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
        if with_reference:
            ra, rb = {"generated": a["reference"]}, {"generated": b["reference"]}
            cells = [_delta_cell(*cols[c], float("inf"), ra, rb) for c, _ in DELTA_COLS]
            lines.append(f"| real children ({a['run']['bucket']} → {b['run']['bucket']}) | " + " | ".join(cells) + " |")
    floors = ", ".join(f"{c} ±{n:g}" for c, n in DELTA_COLS)
    return ("\n".join(lines) + f"\n\nEach cell: A → B (B − A). {FLAG} = the difference is larger than the noise floor "
            f"({floors}; rates are fractions, so 0.005 = 0.5 pts). Floors come from re-sampling the same adapter "
            "with a second seed (EXPERIMENT_LOG.md, run 4 noise check).\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--pair", nargs=2, action="append", metavar=("A", "B"), default=[],
                    help="paired comparison A → B; repeat for more pairs")
    ap.add_argument("--with-reference", action="store_true",
                    help="with --pair: add the real-child shift under each pair")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not a.runs and not a.pair:
        ap.error("give run directories or at least one --pair")
    t = delta_table([(Path(x), Path(y)) for x, y in a.pair], a.with_reference) if a.pair else table(sorted(Path(x) for x in a.runs))
    print(t)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(t, encoding="utf-8")


if __name__ == "__main__":
    main()
