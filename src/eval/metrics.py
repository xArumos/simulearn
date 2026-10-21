"""Child-likeness metrics (CLAUDE.md §9.1). Generated replies are always compared to the REAL child
replies for the same contexts; no single number decides anything.

All functions take plain lists of reply strings. Words = [A-Za-z0-9'] runs, with silence tokens
removed first (silence is scored separately).
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
from scipy import stats

SILENCE_RE = re.compile(r"<SILENCE FOR (\d+) SECONDS>")
SILENCE_LIKE = re.compile(r"<\s*SILENCE[^>]*>?", re.I)
WORD_RE = re.compile(r"[a-z0-9']+")

FILLERS = {"um", "uh", "er", "erm", "hm", "hmm", "mm", "mhm", "uhm", "eh", "ah", "oh"}
SHORT_ANSWERS = {"yeah", "yes", "no", "nope", "yep", "okay", "ok", "mhm", "uhhuh", "uh-huh", "uhuh", "nah", "yup", "huh", "what", "why", "maybe"}
# Informal / non-standard forms typical of young children's speech in CHILDES transcripts.
NONSTANDARD = {
    "goed", "comed", "runned", "eated", "falled", "maked", "buyed", "bringed", "catched", "drawed", "throwed", "teached",
    "thinked", "sitted", "swimmed", "readed", "hitted", "breaked", "taked", "gived", "telled", "knowed", "growed", "blowed",
    "mines", "hisself", "theirself", "foots", "mouses", "mans", "childs", "gooder", "bestest", "funner", "badder",
    "wanna", "gonna", "gotta", "hafta", "hasta", "lemme", "gimme", "dunno", "ain't", "lookit", "cause", "'cause", "nothin",
    "somethin", "goin", "doin", "havin", "lookin", "playin", "makin", "comin", "tryin", "gettin", "sayin", "kinda", "sorta",
}
META_PATTERNS = [
    r"\bas an? (ai|assistant|language model|child|kid|\d+[- ]year[- ]old)\b",
    r"\bi('m| am) (an? )?(ai|assistant|language model)\b",
    r"\bi('m| am) (a |an )?(five|four|5|4)[- ]year[- ]old\b",
    r"^\s*(sure|certainly|of course|absolutely|great question)\b[!,.]",
    r"\b(i'd be happy to|how can i (help|assist)|here('s| is) (a|an|the|my) (response|reply|answer))\b",
    r"\*[^*]{2,40}\*",                      # *giggles* roleplay stage directions
    r"\((laughs|giggles|smiles|excitedly|in a [^)]*voice)[^)]*\)",
    r"[\U0001F300-\U0001FAFF☀-➿]",  # emoji
]
META_RE = re.compile("|".join(META_PATTERNS), re.I)
ROLE_LABEL_RE = re.compile(r"(^|\n)\s*(user|assistant|caregiver|mom|mommy|mother|dad|teacher|adult|child|kid|parent|me|you)\s*:", re.I)
SPECIAL_TOKEN_RE = re.compile(r"<\|[^|]+\|>")


def words(text: str) -> list[str]:
    return WORD_RE.findall(SILENCE_RE.sub(" ", text).lower())


def msttr(replies: list[str], segment: int = 100) -> float:
    """Mean segmental type-token ratio over consecutive 100-word segments (fixed sample size)."""
    toks = [w for r in replies for w in words(r)]
    segs = [toks[i:i + segment] for i in range(0, len(toks) - segment + 1, segment)]
    return float(np.mean([len(set(s)) / segment for s in segs])) if segs else float("nan")


def distinct_n(replies: list[str], n: int) -> float:
    grams, total = set(), 0
    for r in replies:
        w = words(r)
        g = list(zip(*[w[i:] for i in range(n)]))
        grams.update(g)
        total += len(g)
    return len(grams) / total if total else float("nan")


def has_repetition(w: list[str]) -> bool:
    """A word or two-word phrase immediately repeated ("I I want", "the dog the dog")."""
    if any(a == b for a, b in zip(w, w[1:])):
        return True
    return any(w[i:i + 2] == w[i + 2:i + 4] for i in range(len(w) - 3))


def is_loop(w: list[str]) -> bool:
    """Degenerate looping: some 3-gram occurs 3+ times, or the same word 4+ times in a row."""
    tri = Counter(zip(w, w[1:], w[2:]))
    if tri and max(tri.values()) >= 3:
        return True
    run = 1
    for a, b in zip(w, w[1:]):
        run = run + 1 if a == b else 1
        if run >= 4:
            return True
    return False


def reply_flags(text: str) -> dict[str, bool]:
    w = words(text)
    sil_like = bool(SILENCE_LIKE.search(text))
    return {
        "empty": len(w) == 0 and not SILENCE_RE.search(text),
        "loop": is_loop(w),
        "meta": bool(META_RE.search(text)),
        "continues_other_side": bool(ROLE_LABEL_RE.search(text) or SPECIAL_TOKEN_RE.search(text)),
        "multiline": "\n" in text.strip(),
        "filler": any(x in FILLERS for x in w),
        "short_answer": 0 < len(w) <= 2 and all(x in SHORT_ANSWERS or x in FILLERS for x in w),
        "repetition": has_repetition(w),
        "nonstandard": any(x in NONSTANDARD for x in w),
        "silence": bool(SILENCE_RE.search(text)),
        "silence_malformed": sil_like and not SILENCE_RE.search(text),
        "over_20_words": len(w) > 20,
    }


def compute_metrics(generated: list[str], reference: list[str], train_vocab: Counter | None = None, top_n: int = 1000) -> dict:
    """Metrics for one system, plus the same descriptive metrics for the real replies."""
    out = {"n": len(generated), "generated": describe(generated, train_vocab, top_n),
           "reference": describe(reference, train_vocab, top_n)}
    g_len = [len(words(r)) for r in generated]
    r_len = [len(words(r)) for r in reference]
    out["length_ks"] = float(stats.ks_2samp(g_len, r_len).statistic)
    out["length_wasserstein"] = float(stats.wasserstein_distance(g_len, r_len))
    g, r = out["generated"], out["reference"]
    # One summary of "how far from real children" across the descriptive rates (lower = closer).
    keys = ["filler_rate", "short_answer_rate", "repetition_rate", "nonstandard_rate", "over_20_words_rate", "silence_rate"]
    out["child_marker_gap"] = float(np.mean([abs(g[k] - r[k]) for k in keys]))
    out["degeneration_rate"] = g["degenerate_rate"]
    return out


def describe(replies: list[str], train_vocab: Counter | None, top_n: int) -> dict:
    n = max(len(replies), 1)
    lens = [len(words(r)) for r in replies]
    flags = [reply_flags(r) for r in replies]
    rate = lambda k: sum(f[k] for f in flags) / n  # noqa: E731
    d = {
        "mean_words": float(np.mean(lens)) if lens else 0.0,
        "median_words": float(np.median(lens)) if lens else 0.0,
        "p90_words": float(np.percentile(lens, 90)) if lens else 0.0,
        "msttr_100": msttr(replies),
        "distinct_1": distinct_n(replies, 1),
        "distinct_2": distinct_n(replies, 2),
    }
    for k in ["empty", "loop", "meta", "continues_other_side", "multiline", "filler", "short_answer", "repetition",
              "nonstandard", "silence", "silence_malformed", "over_20_words"]:
        d[f"{k}_rate"] = rate(k)
    d["degenerate_rate"] = sum(f["empty"] or f["loop"] or f["meta"] or f["continues_other_side"] for f in flags) / n
    sil = Counter(int(x) for r in replies for x in SILENCE_RE.findall(r))
    d["silence_tokens_by_seconds"] = dict(sorted(sil.items()))
    if train_vocab:
        top = {w for w, _ in train_vocab.most_common(top_n)}
        toks = [w for r in replies for w in words(r)]
        d["oov_rate"] = sum(w not in train_vocab for w in toks) / max(len(toks), 1)
        d["rare_word_rate"] = sum(w not in top for w in toks) / max(len(toks), 1)
    return d


def vocab_from_replies(replies: list[str]) -> Counter:
    return Counter(w for r in replies for w in words(r))
