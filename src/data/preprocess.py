"""One-command preprocessing: raw .cha -> chat-format train/val/test JSONL per age bucket.

    python -m src.data.preprocess --config configs/data_default.yaml [--buckets age5 age4 age6] [--verify-ages]

Deterministic: files are read in sorted order and the only randomness is seeded.
Outputs (never committed; data/ is git-ignored):
    data/processed/splits.json                 child IDs per split (shared by all buckets)
    data/processed/<bucket>/{train,val,test}.jsonl, golden_review.jsonl, splits.json, stats.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.utils.config import load_config, resolve

from .build_examples import BuildConfig, build_turns, examples_from_turns
from .child_ids import UnionFind, child_id, linked_ids
from .clean import CleanConfig
from .parse_chat import Transcript, parse_file
from .silence import SilenceConfig
from .split import check_no_leakage, pick_golden, split_groups

SILENCE_RE = re.compile(r"<SILENCE FOR (\d+) SECONDS>")
WORD_RE = re.compile(r"[A-Za-z0-9']+")
ADULT_ROLES = {"Mother", "Father", "Investigator", "Adult", "Teacher", "Grandmother", "Grandfather",
               "Relative", "Aunt", "Uncle", "Caretaker", "Babysitter", "Visitor", "Observer", "Environment", "Unidentified"}


def n_words(text: str) -> int:
    return len(WORD_RE.findall(SILENCE_RE.sub(" ", text)))


@dataclass
class View:
    """One (transcript, target child) pair that passed the filters."""
    transcript: Transcript
    code: str
    age_months: int
    child_id: str


def build_config(cfg: dict) -> BuildConfig:
    b = cfg.get("build", {})
    return BuildConfig(
        context_turns=b.get("context_turns", 6),
        system_prompt=b.get("system_prompt", BuildConfig.system_prompt),
        break_speakers=b.get("break_speakers", {}) or {},
        break_roles=tuple(b.get("break_roles", ["Media"])),
        unintelligible_placeholder=b.get("unintelligible_placeholder", "(unintelligible)"),
        clean=CleanConfig(**{k: tuple(v) if isinstance(v, list) else v for k, v in cfg.get("clean", {}).items()}),
        silence=SilenceConfig(**cfg.get("silence", {})),
    )


def load_views(cfg: dict, filt: Counter, lo: int | None = None, hi: int | None = None) -> tuple[list[View], UnionFind]:
    """Views (file, target child) with age in [lo, hi] months (default: split_age_range)."""
    root = resolve(cfg["raw_dir"])
    if lo is None or hi is None:
        lo, hi = cfg["split_age_range"]
    rules = cfg.get("child_id_rules", {}) or {}
    views: list[View] = []
    uf = UnionFind()
    birth_key: dict[tuple, str] = {}
    for col in cfg["collections"]:
        for corpus in cfg["corpora"]:
            cdir = root / col / corpus
            if not cdir.is_dir():
                continue
            rule = rules.get(corpus)
            for path in sorted(cdir.rglob("*.cha")):
                filt["files_total"] += 1
                t = parse_file(path, root, col, corpus)
                if cfg.get("exclude_asr", True) and t.is_asr:
                    filt["files_dropped_asr_unchecked"] += 1
                    continue
                if t.primary_language != cfg.get("language", "eng"):
                    filt["files_dropped_language"] += 1
                    continue
                targets = t.target_children
                if not targets:
                    filt["files_dropped_no_target_child"] += 1
                    continue
                file_ids = []
                for p in targets:
                    cid = child_id(corpus, t.path, p.code, rule)
                    file_ids.append(cid)
                    if p.age_months is None:
                        filt["views_dropped_no_age"] += 1
                        continue
                    if not lo <= p.age_months <= hi:
                        filt[f"views_dropped_age_out_of_{lo}_{hi}"] += 1
                        continue
                    filt[f"views_kept_{lo}_{hi}"] += 1
                    uf.find(cid)
                    views.append(View(t, p.code, p.age_months, cid))
                    if rule and rule.get("link_by_birth") and p.birth:
                        key = (corpus, p.birth, p.sex)
                        if key in birth_key:
                            uf.union(cid, birth_key[key])
                        birth_key[key] = cid
                    for other in linked_ids(corpus, t.path, rule):
                        uf.union(cid, other)
                for a, b in zip(file_ids, file_ids[1:]):  # several target children in one file
                    uf.union(a, b)
    return views, uf


def verify_ages(views: list[View], root: Path, limit: int = 300) -> dict:
    """Cross-check our @ID age parsing against pylangacq on files it can parse."""
    import pylangacq

    checked = mismatched = failed = 0
    for v in views[:limit]:
        if v.code != "CHI":
            continue
        try:
            ages = pylangacq.read_chat(str(root / v.transcript.path)).ages()
        except Exception:
            failed += 1
            continue
        if not ages or ages[0] is None:
            continue
        checked += 1
        mismatched += int(ages[0].in_months()) != v.age_months
    return {"checked": checked, "mismatched": mismatched, "pylangacq_failed_to_parse": failed}


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def run(cfg: dict, buckets: list[str], verify: bool) -> None:
    out_root = resolve(cfg["processed_dir"])
    out_root.mkdir(parents=True, exist_ok=True)
    filt: Counter = Counter()
    s = cfg.get("split", {})
    fractions, seed = tuple(s.get("fractions", (0.8, 0.1, 0.1))), s.get("seed", 42)
    if cfg.get("split_extra_age_range"):
        views, group_of, splits = load_with_extra_range(cfg, filt, fractions, seed)
    else:
        views, uf = load_views(cfg, filt)
        group_of = uf.groups()
        splits = split_groups(group_of, fractions, seed)
    files_by_child: dict[str, set[str]] = defaultdict(set)
    for v in views:
        files_by_child[v.child_id].add(v.transcript.path)
    check_no_leakage(splits, files_by_child)
    split_of = {cid: name for name, kids in splits.items() for cid in kids}
    groups_json = defaultdict(list)
    for cid, g in sorted(group_of.items()):
        groups_json[g].append(cid)
    (out_root / "splits.json").write_text(json.dumps(
        {"seed": s.get("seed", 42), "fractions": s.get("fractions"), "age_range_months": cfg["split_age_range"],
         "extra_age_range_months": cfg.get("split_extra_age_range"),
         **splits, "groups": {g: m for g, m in groups_json.items() if len(m) > 1}}, indent=1))

    age_check = verify_ages(views, resolve(cfg["raw_dir"])) if verify else None
    bcfg = build_config(cfg)
    for bname in buckets:
        b = cfg["buckets"][bname]
        bviews = [v for v in views if b["min_months"] <= v.age_months <= b["max_months"]]
        write_bucket(bname, b, bviews, bcfg, split_of, group_of, splits, filt, cfg, out_root, age_check)


def load_with_extra_range(cfg: dict, filt: Counter, fractions, seed):
    """Add older (or younger) children without changing the existing splits.

    1. Children seen in ``split_age_range`` (48-71 months) are split exactly as before, so the
       age4/age5 data and splits stay byte-identical and earlier runs remain comparable.
    2. Views in ``split_extra_age_range`` (e.g. 72-83 months for age6) are added. A child already
       split keeps its split; so does any new child linked to one (same family/file/birth date).
    3. Children that only appear in the extra range are split separately with the same
       fractions and seed (stratified by corpus).
    """
    anchor_views, anchor_uf = load_views(cfg, Counter())
    anchor_groups = anchor_uf.groups()
    anchor_splits = split_groups(anchor_groups, fractions, seed)
    split_of = {cid: name for name, kids in anchor_splits.items() for cid in kids}

    lo = min(cfg["split_age_range"][0], cfg["split_extra_age_range"][0])
    hi = max(cfg["split_age_range"][1], cfg["split_extra_age_range"][1])
    views, uf = load_views(cfg, filt, lo, hi)
    full_groups = uf.groups()

    members: dict[str, list[str]] = defaultdict(list)
    for cid, g in full_groups.items():
        members[g].append(cid)
    inherited: dict[str, str] = {}
    new_group_of: dict[str, str] = {}
    for g, kids in members.items():
        known = {split_of[c] for c in kids if c in split_of}
        if len(known) > 1:
            raise AssertionError(f"group {g} links children already in different splits: {sorted(known)}")
        for c in kids:
            if c in split_of:
                continue
            if known:
                inherited[c] = next(iter(known))
            else:
                new_group_of[c] = g
    extra_splits = split_groups(new_group_of, fractions, seed)

    splits = {name: sorted(set(anchor_splits[name])
                           | {c for c, n in inherited.items() if n == name}
                           | set(extra_splits[name]))
              for name in ("train", "val", "test")}
    # Keep the original group IDs for already-split children so age4/age5 output is unchanged.
    group_of = {**{c: full_groups[c] for c in full_groups}, **anchor_groups}
    filt["children_inherited_split_via_link"] += len(inherited)
    filt["children_new_in_extra_range"] += len(new_group_of)
    return views, group_of, splits


def write_bucket(bname, b, bviews, bcfg, split_of, group_of, splits, filt, cfg, out_root, age_check) -> None:
    out = out_root / bname
    out.mkdir(parents=True, exist_ok=True)
    # age_label: auto -> each example's prompt states that child's own age in years (mixed-age buckets).
    auto_age = str(b["age_label"]).lower() == "auto"
    system = None if auto_age else bcfg.system_prompt.format(age=b["age_label"])
    rules: Counter = Counter()
    build: Counter = Counter()
    rows: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    per_corpus = defaultdict(Counter)
    kids_per = defaultdict(lambda: defaultdict(set))
    timed_files, gaps, tok_x = 0, [], Counter()
    other_child_utts = Counter()
    collection_of = {}

    for v in bviews:
        t = v.transcript
        collection_of[t.corpus] = t.collection
        turns, info = build_turns(t, v.code, bcfg, rules)
        timed_files += info["timed"]
        gaps += info["silence_gaps_ms"]
        for u in t.utterances:
            role = t.participants.get(u.speaker)
            if u.speaker != v.code and role and role.role not in ADULT_ROLES:
                other_child_utts[role.role] += 1
        for turn in turns:
            for x in SILENCE_RE.findall(turn.text):
                tok_x[int(x)] += 1
        v_system = bcfg.system_prompt.format(age=v.age_months // 12) if auto_age else system
        exs = examples_from_turns(turns, v_system, bcfg.context_turns, build)
        sp = split_of[v.child_id]
        pc = per_corpus[t.corpus]
        pc["transcripts"] += 1
        pc["utterances_raw"] += len(t.utterances)
        pc["child_turns"] += sum(1 for x in turns if x.role == "assistant")
        pc["examples"] += len(exs)
        kids_per[t.corpus]["all"].add(v.child_id)
        kids_per[t.corpus][sp].add(v.child_id)
        stem = t.path.rsplit(".", 1)[0]
        for idx, msgs in exs:
            pc["target_words"] += n_words(msgs[-1]["content"])
            pc[f"examples_{sp}"] += 1
            rows[sp].append({
                "id": f"{stem}:{v.code}:{idx}",
                "messages": msgs,
                "meta": {
                    "child_id": v.child_id, "group_id": group_of[v.child_id], "corpus": t.corpus,
                    "collection": t.collection, "file": t.path, "age_months": v.age_months,
                    "types": t.types, "turn_index": idx, "n_context_turns": len(msgs) - 2,
                    "timed": info["timed"],
                },
            })

    for name, r in rows.items():
        r.sort(key=lambda e: e["id"])
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for e in r:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    g = cfg.get("golden", {})
    golden = pick_golden(rows["test"], g.get("n", 30), g.get("per_child", 2), g.get("min_context_turns", 2), cfg["split"]["seed"])
    with open(out / "golden_review.jsonl", "w", encoding="utf-8") as f:
        for e in golden:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    bucket_kids = {cid for v in bviews for cid in [v.child_id]}
    (out / "splits.json").write_text(json.dumps(
        {name: [c for c in kids if c in bucket_kids] for name, kids in splits.items()}
        | {"golden_ids": [e["id"] for e in golden]}, indent=1))

    stats = render_stats(bname, b, bviews, filt, rules, build, rows, per_corpus, kids_per, collection_of,
                         timed_files, gaps, tok_x, other_child_utts, golden, age_check, cfg)
    (out / "stats.md").write_text(stats, encoding="utf-8")
    print(stats)


def render_stats(bname, b, bviews, filt, rules, build, rows, per_corpus, kids_per, collection_of,
                 timed_files, gaps, tok_x, other_child_utts, golden, age_check, cfg) -> str:
    L = [f"# Preprocessing stats: {bname} ({b['min_months']}-{b['max_months']} months)", ""]
    L += ["Generated by `python -m src.data.preprocess`. Counts only, no transcript text.", ""]
    L += ["## Filters (all corpora, before bucketing)", "", "| Step | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in filt.items()]
    L += ["", f"Transcript views in this bucket: **{len(bviews)}**. A view is one (file, target child) pair;"
          " a file with two target children can give two views.", ""]
    if age_check:
        L += [f"Age cross-check vs pylangacq: {age_check}", ""]

    L += ["## Per corpus", "", "| Corpus | Collection | Children | Transcripts | Raw utterances | Child turns (merged) | Examples | Train / Val / Test examples | Children train / val / test | Target words |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for corpus in sorted(per_corpus):
        pc, kp = per_corpus[corpus], kids_per[corpus]
        tot.update(pc)
        L.append(f"| {corpus} | {collection_of[corpus]} | {len(kp['all'])} | {pc['transcripts']} | {pc['utterances_raw']} | {pc['child_turns']} | {pc['examples']} | "
                 f"{pc['examples_train']} / {pc['examples_val']} / {pc['examples_test']} | {len(kp['train'])} / {len(kp['val'])} / {len(kp['test'])} | {pc['target_words']} |")
    nk = sum(len(kids_per[c]["all"]) for c in kids_per)
    L.append(f"| **Total** | | {nk} | {tot['transcripts']} | {tot['utterances_raw']} | {tot['child_turns']} | {tot['examples']} | "
             f"{tot['examples_train']} / {tot['examples_val']} / {tot['examples_test']} | | {tot['target_words']} |")
    n_train = len(rows["train"])
    L += ["", f"Fallback check (§4): train examples = **{n_train}** (threshold ~5,000) -> "
          + ("OK." if n_train >= 5000 else "**BELOW threshold, ask the user.**"), ""]

    L += ["## Example building", "", "| Counter | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(build.items())]
    tl = [n_words(e["messages"][-1]["content"]) for r in rows.values() for e in r]
    ctx = Counter(e["meta"]["n_context_turns"] for r in rows.values() for e in r)
    if tl:
        L += ["", "### Target (child reply) length in words", "",
              f"mean {statistics.mean(tl):.2f}, median {statistics.median(tl)}, p90 {pct(tl, .9)}, p99 {pct(tl, .99)}, max {max(tl)}", ""]
        hist = Counter(min(x, 20) for x in tl)
        L += ["| Words | 0 | 1 | 2 | 3 | 4 | 5 | 6-10 | 11-20+ |", "|---|---|---|---|---|---|---|---|---|",
              f"| Share | " + " | ".join(f"{100 * c / len(tl):.1f}%" for c in
                                       [hist[0], hist[1], hist[2], hist[3], hist[4], hist[5],
                                        sum(hist[i] for i in range(6, 11)), sum(hist[i] for i in range(11, 21))]) + " |"]
        L += ["", "Context turns per example: " + ", ".join(f"{k}: {v}" for k, v in sorted(ctx.items()))]
    L += ["", "Other non-adult speakers mapped to `user` (utterances): " + (", ".join(f"{k}: {v}" for k, v in other_child_utts.most_common()) or "none")]

    L += ["", "## Silence tokens", ""]
    thr = cfg.get("silence", {}).get("threshold_s", 2.0)
    L += [f"Transcripts with usable timing: **{timed_files} / {len(bviews)}** ({100 * timed_files / max(len(bviews), 1):.1f}%)."]
    if gaps:
        L += [f"Gaps >= {thr}s: n={len(gaps)}, mean {statistics.mean(gaps) / 1000:.2f}s, median {statistics.median(gaps) / 1000:.2f}s."]
    L += ["", "| X seconds | " + " | ".join(str(k) for k in sorted(tok_x)) + " |", "|---|" + "---|" * len(tok_x),
          "| Tokens | " + " | ".join(str(tok_x[k]) for k in sorted(tok_x)) + " |"]
    tgt_sil = sum(1 for r in rows.values() for e in r if SILENCE_RE.search(e["messages"][-1]["content"]))
    L += ["", f"Targets containing a silence token: {tgt_sil} / {len(tl)} ({100 * tgt_sil / max(len(tl), 1):.1f}%)."]

    L += ["", "## Cleaning rules fired (all utterances in bucket transcripts)", "", "| Rule | Count |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in rules.most_common()]
    L += ["", f"## Golden review set: {len(golden)} test examples", ""]
    L += [", ".join(sorted(Counter(e['meta']['corpus'] for e in golden).elements()))] if golden else []
    return "\n".join(L) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/data_default.yaml")
    p.add_argument("--buckets", nargs="+", default=None)
    p.add_argument("--verify-ages", action="store_true")
    a = p.parse_args()
    cfg = load_config(resolve(a.config))
    run(cfg, a.buckets or list(cfg["buckets"]), a.verify_ages)


if __name__ == "__main__":
    main()
