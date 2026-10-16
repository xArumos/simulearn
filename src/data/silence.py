"""Silence tokens from CHAT time marks (DECISIONS.md D1).

If the gap between the end of the previous utterance and the start of the next one is >= threshold
seconds, the next utterance gets the plain-text prefix `<SILENCE FOR X SECONDS>`, where X is the gap
rounded to the nearest whole second and capped. No tokenizer changes; it is ordinary text.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SilenceConfig:
    enabled: bool = True
    threshold_s: float = 2.0
    cap_s: int = 10
    template: str = "<SILENCE FOR {x} SECONDS>"
    # A transcript counts as "timed" if at least this share of its utterances has both time marks.
    min_timed_fraction: float = 0.5


def silence_token(gap_ms: int | None, cfg: SilenceConfig) -> str | None:
    if not cfg.enabled or gap_ms is None or gap_ms < cfg.threshold_s * 1000:
        return None
    # Round half up (2.5 s -> 3), not Python's banker's rounding.
    x = min(int(gap_ms / 1000 + 0.5), cfg.cap_s)
    return cfg.template.format(x=x)


def gaps_ms(times: list[tuple[int | None, int | None]]) -> list[int | None]:
    """Gap before each utterance: start[i] - end[i-1]. None if unknown or the speech overlaps.

    `times` holds (start_ms, end_ms) for the utterances that count as speech, in transcript order.
    """
    out: list[int | None] = [None]
    for (_, prev_end), (start, _) in zip(times, times[1:]):
        if prev_end is None or start is None or start < prev_end:
            out.append(None)
        else:
            out.append(start - prev_end)
    return out


def is_timed(times: list[tuple[int | None, int | None]], cfg: SilenceConfig) -> bool:
    if not times:
        return False
    both = sum(1 for s, e in times if s is not None and e is not None)
    return both / len(times) >= cfg.min_timed_fraction
