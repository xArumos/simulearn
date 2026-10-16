"""Unblind and average human ratings from a review packet (CLAUDE.md §9.3).

    python -m src.eval.score_ratings --phase phase1 [--csv reports/phase1/review_ratings.csv ...]

Several raters: pass several CSVs (one per person, same packet). Writes reports/<phase>/ratings_summary.md
(averages only, no transcript text).
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from src.utils.config import resolve

DIMS = ["child_likeness_1to5", "coherence_1to5", "age_appropriateness_1to5"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--csv", nargs="+", default=None)
    a = ap.parse_args()
    out = resolve("reports") / a.phase
    key = json.loads((out / "review_key.json").read_text())
    scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    wins: dict[str, int] = defaultdict(int)
    n_rows = 0
    for path in a.csv or [str(out / "review_ratings.csv")]:
        best_per_item: dict[tuple, tuple] = {}
        for r in csv.DictReader(open(path, encoding="utf-8")):
            system = key[r["example_id"]][r["reply"]]
            for d in DIMS:
                if r[d].strip():
                    scores[system][d].append(float(r[d]))
                    n_rows += 1
            cl = r["child_likeness_1to5"].strip()
            if cl:
                k = (path, r["example_id"])
                if k not in best_per_item or float(cl) > best_per_item[k][0]:
                    best_per_item[k] = (float(cl), system)
        for _, system in best_per_item.values():
            wins[system] += 1
    if not n_rows:
        raise SystemExit("No ratings filled in yet.")
    lines = [f"# Human ratings: {a.phase}", "", f"Rating files: {len(a.csv or [1])}. Scores 1-5 (higher is better); mean ± SD (n).", "",
             "| System | Child-likeness | Coherence | Age-appropriateness | Most child-like on # items |", "|---|---|---|---|---|"]
    for system in sorted(scores, key=lambda s: -st.mean(scores[s]["child_likeness_1to5"] or [0])):
        cells = []
        for d in DIMS:
            v = scores[system][d]
            cells.append(f"{st.mean(v):.2f} ± {st.pstdev(v):.2f} ({len(v)})" if v else "–")
        lines.append(f"| {system} | " + " | ".join(cells) + f" | {wins[system]} |")
    lines += ["", "Ties for 'most child-like' go to the first system seen. `real` = the real child's reply (the ceiling to aim for)."]
    (out / "ratings_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
