"""Child-level train/val/test splits (never by utterance) and the golden review set.

Splitting unit = a *group* of linked child IDs (see child_ids.py). Groups are shuffled with a
fixed seed and assigned per corpus, so every corpus with enough children appears in every split.
Fractions are applied to the number of children, not examples.
"""
from __future__ import annotations

import random
from collections import defaultdict


def split_groups(
    group_of: dict[str, str],
    fractions: tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 42,
) -> dict[str, list[str]]:
    """group_of maps child_id -> group_id. Returns {"train"|"val"|"test": sorted child_ids}."""
    members: dict[str, list[str]] = defaultdict(list)
    for cid, g in group_of.items():
        members[g].append(cid)
    by_corpus: dict[str, list[str]] = defaultdict(list)
    for g in sorted(members):
        by_corpus[g.split("/", 1)[0]].append(g)

    rng = random.Random(seed)
    out: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for corpus in sorted(by_corpus):
        groups = by_corpus[corpus]
        rng.shuffle(groups)
        n_kids = sum(len(members[g]) for g in groups)
        want_val, want_test = round(n_kids * fractions[1]), round(n_kids * fractions[2])
        got = {"val": 0, "test": 0}
        for g in groups:
            size = len(members[g])
            # Fill test, then val, without overshooting; everything else goes to train.
            if got["test"] + size <= want_test:
                name = "test"
            elif got["val"] + size <= want_val:
                name = "val"
            else:
                name = "train"
            got[name] = got.get(name, 0) + size
            out[name].extend(members[g])
    return {k: sorted(v) for k, v in out.items()}


def check_no_leakage(splits: dict[str, list[str]], files_by_child: dict[str, set[str]]) -> None:
    """Raise if a child ID or a transcript file is in more than one split."""
    seen_child: dict[str, str] = {}
    seen_file: dict[str, str] = {}
    for name, kids in splits.items():
        for cid in kids:
            if cid in seen_child:
                raise AssertionError(f"child {cid} in both {seen_child[cid]} and {name}")
            seen_child[cid] = name
            for f in files_by_child.get(cid, ()):
                if f in seen_file and seen_file[f] != name:
                    raise AssertionError(f"file {f} in both {seen_file[f]} and {name}")
                seen_file[f] = name


def pick_golden(test_examples: list[dict], n: int = 30, per_child: int = 2, min_context: int = 2, seed: int = 42) -> list[dict]:
    """~n test examples with some context, at most `per_child` per child, spread across corpora."""
    rng = random.Random(seed)
    pool = [e for e in test_examples if len(e["messages"]) - 2 >= min_context]
    rng.shuffle(pool)
    by_corpus: dict[str, list[dict]] = defaultdict(list)
    for e in pool:
        by_corpus[e["meta"]["corpus"]].append(e)
    picked, per = [], defaultdict(int)
    # Round-robin over corpora so no single corpus dominates the review packet.
    while len(picked) < n and any(by_corpus.values()):
        for corpus in sorted(by_corpus):
            while by_corpus[corpus]:
                e = by_corpus[corpus].pop()
                if per[e["meta"]["child_id"]] < per_child:
                    picked.append(e)
                    per[e["meta"]["child_id"]] += 1
                    break
            if len(picked) >= n:
                break
    return sorted(picked, key=lambda e: e["id"])
