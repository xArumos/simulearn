"""Minimal, forgiving CHAT (.cha) reader.

Why not pylangacq for this step: pylangacq 0.23 (rustling backend) raises on the first malformed
word in a corpus (e.g. a typo like `word@c>`), which aborts the whole directory. Real CHILDES data
has such typos, so we read the raw lines ourselves, keep the original main-tier text for our own
cleaning rules (src/data/clean.py), and never fail a whole transcript because of one bad word.

What is read:
- headers: @Languages, @Participants, @ID, @Types, @Comment, @Birth of XXX
- main tiers (*SPK:) with continuation lines joined, and the time-mark bullet (\x15start_end\x15, ms)
Dependent tiers (%mor, %wor, ...) are skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BULLET = re.compile("\x15(\\d+)_(\\d+)\x15")
_AGE = re.compile(r"^\s*(\d+);(\d*)(?:\.(\d*))?")
ASR_MARKER = "Unchecked output of ASR"


def age_to_months(age: str) -> int | None:
    """'4;06.12' -> 54, '3;11.' -> 47, '5;' -> 60, '' -> None. Days are ignored (floor)."""
    m = _AGE.match(age or "")
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2) or 0)


@dataclass
class Participant:
    code: str
    role: str
    age_months: int | None = None
    sex: str = ""
    group: str = ""
    birth: str = ""


@dataclass
class Utterance:
    speaker: str
    text: str  # main-tier text with time bullets removed, otherwise raw CHAT
    start_ms: int | None = None
    end_ms: int | None = None
    line_no: int = 0


@dataclass
class Transcript:
    path: str  # relative to the extracted root, posix-style
    corpus: str
    collection: str
    languages: list[str] = field(default_factory=list)
    participants: dict[str, Participant] = field(default_factory=dict)
    types: str = ""
    is_asr: bool = False
    utterances: list[Utterance] = field(default_factory=list)

    @property
    def target_children(self) -> list[Participant]:
        return [p for p in self.participants.values() if p.role == "Target_Child"]

    @property
    def primary_language(self) -> str:
        return self.languages[0] if self.languages else ""


def _logical_lines(raw: str) -> list[tuple[int, str]]:
    """Join CHAT continuation lines (lines starting with a tab) onto the previous line."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        if line.startswith("\t") and out:
            n, prev = out[-1]
            out[-1] = (n, prev + " " + line.strip())
        else:
            out.append((i, line.rstrip("\r")))
    return out


def parse_text(raw: str, path: str = "", corpus: str = "", collection: str = "") -> Transcript:
    t = Transcript(path=path, corpus=corpus, collection=collection)
    roles_from_participants: dict[str, str] = {}
    for line_no, line in _logical_lines(raw):
        if line.startswith("@"):
            key, _, val = line.partition(":")
            val = val.strip()
            if key == "@Languages":
                t.languages = [x.strip() for x in val.split(",") if x.strip()]
            elif key == "@Participants":
                for entry in val.split(","):
                    bits = entry.split()
                    if len(bits) >= 2:
                        roles_from_participants[bits[0]] = bits[-1]
            elif key == "@ID":
                f = val.split("|")
                if len(f) >= 8:
                    code = f[2].strip()
                    t.participants[code] = Participant(
                        code=code, role=f[7].strip(), age_months=age_to_months(f[3]),
                        sex=f[4].strip(), group=f[5].strip(),
                    )
            elif key == "@Types":
                t.types = val
            elif key == "@Comment" and ASR_MARKER in val:
                t.is_asr = True
            elif key.startswith("@Birth of "):
                code = key[len("@Birth of "):].strip()
                t.participants.setdefault(code, Participant(code=code, role=roles_from_participants.get(code, "")))
                t.participants[code].birth = val
        elif line.startswith("*"):
            spk, _, text = line[1:].partition(":")
            marks = BULLET.findall(text)
            start = int(marks[0][0]) if marks else None
            end = int(marks[-1][1]) if marks else None
            text = BULLET.sub(" ", text).strip()
            t.utterances.append(Utterance(spk.strip(), text, start, end, line_no))
    # Speakers listed in @Participants but missing an @ID line
    for code, role in roles_from_participants.items():
        t.participants.setdefault(code, Participant(code=code, role=role))
    return t


def parse_file(path: Path, root: Path, collection: str, corpus: str) -> Transcript:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return parse_text(raw, path.relative_to(root).as_posix(), corpus, collection)
