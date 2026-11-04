"""Rank English CHILDES corpora by how many children likely fall in an age range.

Uses only the public, corpus-level index tables at talkbank.org/childes/access/<collection>/
(columns: Corpus, Age Range, N, Media, Comments). No transcripts are downloaded. Downloading
transcripts needs a TalkBank login, which the user does by hand.

The "estimated children in range" number is a rough heuristic: N * (fraction of the corpus's
age span that overlaps the target range). It assumes ages are spread evenly, which is often
false, so it is only good for ranking. The real per-transcript age filter runs after download (§7.1).
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from html import unescape
from pathlib import Path

BASE = "https://talkbank.org/childes/access/"
# North American English by default (DECISIONS.md D2). Add "Eng-UK" via --collections for the UK fallback tier.
DEFAULT_COLLECTIONS = ["Eng-NA", "Eng-AAE"]

_YM = re.compile(r"(\d+);(\d+)(?:\.\d+)?")
_NUM = re.compile(r"\d+")


@dataclass
class Corpus:
    collection: str
    name: str
    page_url: str
    age_text: str
    n_text: str
    media: str
    comments: str
    lo_months: int | None = None
    hi_months: int | None = None
    n_children: int | None = None
    est_in_range: dict[str, float] = field(default_factory=dict)


def parse_age_range(text: str) -> tuple[int | None, int | None]:
    """Turn an index-table age string into (lo, hi) months, inclusive.

    Handles "1;6-5;1", "2;6, 3;6, 4;6, 5;6", "3-10" (bare years), "5 and adult",
    "6, 9, 12 months". Returns (None, None) when nothing parseable is present ("-", "--").
    """
    t = text.lower()
    ym = [(int(y), int(m)) for y, m in _YM.findall(t) if int(m) <= 11]
    if ym:
        months = [y * 12 + m for y, m in ym]
        return min(months), max(months)
    nums = [int(x) for x in _NUM.findall(t)]
    if not nums:
        return None, None
    if "month" in t:
        return min(nums), max(nums)
    # Bare numbers are years: a child "aged 5" spans 60-71 months.
    return min(nums) * 12, max(nums) * 12 + 11


def parse_n(text: str) -> int | None:
    nums = [int(x) for x in _NUM.findall(text)]
    return sum(nums) if nums else None


def overlap_fraction(lo: int, hi: int, a: int, b: int) -> float:
    ov = min(hi, b) - max(lo, a) + 1
    return max(ov, 0) / (hi - lo + 1)


def _cells(row_html: str) -> list[tuple[str, str | None]]:
    """Split a <tr> chunk into (text, first href) per <td>. The tables omit closing tags."""
    out = []
    for chunk in re.split(r"<td", row_html, flags=re.I)[1:]:
        chunk = re.sub(r"^[^>]*>", "", chunk)
        href = re.search(r"href\s*=\s*\"?([^\"\s>]+)", chunk, flags=re.I)
        text = unescape(re.sub(r"<[^>]+>", " ", chunk))
        out.append((re.sub(r"\s+", " ", text).strip(), href.group(1) if href else None))
    return out


def parse_index(html: str, collection: str) -> list[Corpus]:
    corpora = []
    for row in re.split(r"<tr", html, flags=re.I):
        cells = _cells(row)
        if len(cells) < 4 or not cells[0][1]:
            continue
        (name, href), (age, _), (n, _), (media, _) = cells[:4]
        if not href.endswith(".html") or name.lower().startswith("corpus"):
            continue
        comments = cells[4][0] if len(cells) > 4 else ""
        url = urllib.request.urljoin(f"{BASE}{collection}/index.html", href)
        c = Corpus(collection, name, url, age, n, media, comments)
        c.lo_months, c.hi_months = parse_age_range(age)
        c.n_children = parse_n(n)
        corpora.append(c)
    return corpora


def score(corpora: list[Corpus], buckets: dict[str, tuple[int, int]]) -> None:
    for c in corpora:
        for label, (a, b) in buckets.items():
            if c.lo_months is None or c.n_children is None:
                continue
            c.est_in_range[label] = round(c.n_children * overlap_fraction(c.lo_months, c.hi_months, a, b), 1)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "simulearn-corpus-selection/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fmt_months(m: int | None) -> str:
    return "?" if m is None else f"{m // 12};{m % 12:02d}"


def to_markdown(corpora: list[Corpus], buckets: dict[str, tuple[int, int]]) -> str:
    keys = list(buckets)
    lines = [
        "# CHILDES corpus candidates (from public index metadata only)",
        "",
        "Estimated children in range = N x (share of the corpus's age span inside the range). Rough, for ranking only.",
        "",
        "| Collection | Corpus | Age range (index) | Parsed months | N | Media | " + " | ".join(f"est. {k}" for k in keys) + " | Comments |",
        "|---|---|---|---|---|---|" + "---|" * len(keys) + "---|",
    ]
    for c in corpora:
        ests = " | ".join(str(c.est_in_range.get(k, "?")) for k in keys)
        lines.append(
            f"| {c.collection} | [{c.name}]({c.page_url}) | {c.age_text} | {fmt_months(c.lo_months)}-{fmt_months(c.hi_months)} "
            f"| {c.n_text} | {c.media} | {ests} | {c.comments} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--collections", nargs="+", default=DEFAULT_COLLECTIONS)
    p.add_argument("--out-dir", default="reports/setup")
    args = p.parse_args()

    buckets = {"48-71": (48, 71), "60-71": (60, 71), "48-59": (48, 59)}
    corpora: list[Corpus] = []
    seen: set[str] = set()
    for col in args.collections:
        for c in parse_index(fetch(f"{BASE}{col}/index.html"), col):
            # Some collections link to the same corpus page (e.g. Eng-AAE lists Eng-NA/Hall).
            if c.page_url not in seen:
                seen.add(c.page_url)
                corpora.append(c)
    score(corpora, buckets)
    in_range = [c for c in corpora if c.est_in_range.get("48-71", 0) > 0]
    unknown = [c for c in corpora if not c.est_in_range]
    in_range.sort(key=lambda c: c.est_in_range["60-71"], reverse=True)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "corpus_candidates.json").write_text(json.dumps([asdict(c) for c in corpora], indent=2))
    (out / "corpus_candidates.md").write_text(
        to_markdown(in_range, buckets) + "\n## Age range not listed in index (check page by hand)\n\n"
        + "\n".join(f"- {c.collection}/{c.name}: N={c.n_text} ({c.page_url})" for c in unknown) + "\n"
    )
    print(f"{len(corpora)} corpora parsed, {len(in_range)} overlap 48-71 months, {len(unknown)} with unknown ages.")
    for c in in_range:
        print(f"{c.collection:8s} {c.name:22s} {c.age_text:22s} N={c.n_text:12s} est60-71={c.est_in_range['60-71']:6} est48-59={c.est_in_range['48-59']:6} media={c.media}")


if __name__ == "__main__":
    main()
