"""Turn CHAT main-tier text into plain text, counting every rule that fires.

Policy: write down what the child actually said, and remove only the transcriber's notation.
- Keep fillers (&-um -> um), repetitions and retracings (the words before [/] and [//] were really said),
  and non-standard child forms (goed, tryin, wanna). Child grammar is never corrected.
- Remove notation: gestures, comments, explanations, overlap markers, pauses, scoping brackets,
  word-form suffixes (@c, @l, ...), lengthening colons, and the "correct form" in [: ...].
- Words marked as omitted (0is) were NOT said, so they are removed.
- Unintelligible / untranscribed material (xxx, yyy, www) is removed from the text, and the
  utterance is flagged so it can be excluded as a training target.
- Utterances marked as another language ([- spa]) or as reading aloud ([+ read]) are flagged.

All behaviour switches are in CleanConfig so they can be changed via YAML (YELLOW change, see CLAUDE.md §3).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Utterance terminators -> plain punctuation. Order matters (longest first).
TERMINATORS = [
    ("+//?", "...?"), ("+/?", "...?"), ("+..?", "...?"), ("+!?", "?!"),
    ("+\"/.", "."), ("+//.", "..."), ("+/.", "..."), ("+...", "..."), ("+\".", "."), ("+.", "."),
]
LINKERS = ["+\"", "+^", "+,", "++", "+<", "+≋", "+≈"]
UNINTELLIGIBLE = re.compile(r"(?<![\w&])(xxx|yyy|www)(@\S*)?(?!\w)")
OTHER_SYMBOLS = re.compile(r"[↑↓⇗↗→↘⇘∞≡∙⁎◉▔▁☺♋°ʔʕˈˌ∆∇⌈⌉⌊⌋≈≋∬Ϋ↫]")


@dataclass
class CleanConfig:
    keep_fragments: bool = False  # &+fr / &~fr partial words
    keep_terminator_punct: bool = True
    target_drop_postcodes: tuple[str, ...] = ("read",)  # [+ read]: reading a book aloud


@dataclass
class CleanResult:
    text: str
    unintelligible: bool = False
    foreign: bool = False
    reading: bool = False
    postcodes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not re.search(r"\w", self.text)

    def target_ok(self) -> bool:
        return not (self.empty or self.unintelligible or self.foreign or self.reading)


def _sub(pattern: str | re.Pattern, repl, text: str, counter: Counter, rule: str, flags=0) -> str:
    new, n = re.subn(pattern, repl, text, flags=flags)
    if n:
        counter[rule] += n
    return new


def clean_utterance(text: str, counter: Counter | None = None, cfg: CleanConfig | None = None) -> CleanResult:
    c = counter if counter is not None else Counter()
    cfg = cfg or CleanConfig()
    res = CleanResult(text="")
    t = " " + text + " "

    # --- utterance-level codes -------------------------------------------------------------
    if re.search(r"\[- [^\]]+\]", t):
        res.foreign = True
        c["lang_precode[-]"] += 1
        t = re.sub(r"\[- [^\]]+\]", " ", t)
    for code in re.findall(r"\[\+ ([^\]]+)\]", t):
        res.postcodes.append(code.strip())
        c["postcode[+]"] += 1
    t = re.sub(r"\[\+ [^\]]+\]", " ", t)
    if any(p.split(":")[0] in cfg.target_drop_postcodes for p in res.postcodes) or re.search(r"\[=! ?read", t):
        res.reading = True
        c["reading_flag"] += 1

    # --- bracketed annotations (remove the annotation, keep the words it points at) ---------
    t = _sub(r"\[::? [^\]]*\]", " ", t, c, "replacement[:]")       # goed [: went] -> goed
    t = _sub(r"\[=! [^\]]*\]", " ", t, c, "paralinguistic[=!]")
    t = _sub(r"\[= [^\]]*\]", " ", t, c, "explanation[=]")
    t = _sub(r"\[% [^\]]*\]", " ", t, c, "comment[%]")
    t = _sub(r"\[\^ [^\]]*\]", " ", t, c, "comment[^]")
    t = _sub(r"\[\* [^\]]*\]|\[\*\]", " ", t, c, "error[*]")
    t = _sub(r"\[///?\]|\[/-\]|\[/\?\]", " ", t, c, "retrace[//]")
    t = _sub(r"\[/\]", " ", t, c, "repetition[/]")
    t = _sub(r"\[[<>]\d?\]", " ", t, c, "overlap[<>]")
    t = _sub(r"\[\?\]", " ", t, c, "uncertain[?]")
    t = _sub(r"\[!!?\]", " ", t, c, "stress[!]")
    t = _sub(r"\[[^\]]*\]", " ", t, c, "other_bracket")
    t = _sub(r"[<>]", " ", t, c, "scope<>")

    # --- & codes ---------------------------------------------------------------------------
    t = _sub(r"&=\S+", " ", t, c, "action&=")
    t = _sub(r"&\*\S+", " ", t, c, "interposed&*")
    t = _sub(r"&-(\S+)", r"\1", t, c, "filler&-")
    if cfg.keep_fragments:
        t = _sub(r"&[+~](\S+)", r"\1", t, c, "fragment&+~kept")
    else:
        t = _sub(r"&[+~]\S+", " ", t, c, "fragment&+~")

    # --- unintelligible --------------------------------------------------------------------
    t, n = UNINTELLIGIBLE.subn(" ", t)
    if n:
        res.unintelligible = True
        c["unintelligible_xxx"] += n

    # --- terminators, linkers, pauses ------------------------------------------------------
    end = ""
    stripped = t.rstrip()
    for code, punct in TERMINATORS:
        if stripped.endswith(code):
            end = punct
            stripped = stripped[: -len(code)]
            c["terminator_incomplete"] += punct.startswith("...")
            break
    else:
        m = re.search(r"\s([.?!])$", stripped)
        if m:
            end = m.group(1)
            stripped = stripped[: m.start()]
    t = " " + stripped + " "
    for code in LINKERS:
        if code in t:
            c["linker"] += t.count(code)
            t = t.replace(code, " ")
    t = _sub(r"\((?:\d*\.\d+|\.+|\d+:\d+(?:\.\d+)?)\)", " ", t, c, "pause(.)")

    # --- word-level notation -----------------------------------------------------------------
    t = _sub(r"(?<!\S)0\S*", " ", t, c, "omitted_word0")             # 0is / bare 0
    t = _sub(r"(\w)@[\w:$-]*", r"\1", t, c, "word_form@")             # word@c -> word
    t = _sub(r"\(\w*\)", "", t, c, "omitted_sounds()")                # goin(g) -> goin
    t = _sub(r"(?<=\w):+", "", t, c, "lengthening:")                  # no:: -> no, o:ne -> one
    t = _sub(r"(?<=\w)\^(?=\w)", "", t, c, "inword_pause^")
    t = _sub(r"(?<=\w)_(?=\w)", " ", t, c, "compound_")
    t = _sub(r"(?<=\w)\+(?=\w)", "", t, c, "compound+")
    t = _sub(r"[‡„]", ",", t, c, "tag_marker")
    t = _sub(OTHER_SYMBOLS, "", t, c, "ca_symbols")
    t = _sub(r"[\x00-\x08\x0b-\x1f]", " ", t, c, "control_chars")

    # --- tidy whitespace and punctuation -------------------------------------------------------
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,;:])", r"\1", t)
    t = re.sub(r"(,\s*)+(?=,|$)", "", t).strip(" ,")
    if cfg.keep_terminator_punct and end and re.search(r"\w", t):
        t = t + end
    res.text = t
    if res.empty:
        c["empty_after_cleaning"] += 1
    return res
