"""Build chat-format training examples from one transcript and one target child.

Roles: the target child is `assistant`; everyone else (mother, investigator, siblings, other
children) is `user`. Speakers listed in `break_speakers` (e.g. the Jibo robot in OCSC) are removed
and act as a conversation break: context never crosses them, and the child turn right after
one is not used as a target (the child was talking to the robot).

Steps per transcript:
1. Clean every utterance (clean.py). Drop empty ones (counted).
2. Compute silence gaps over all utterances that contain speech, then prefix the token to
   that utterance if it is kept.
3. Merge consecutive utterances of the same side into one turn.
4. One example per valid child turn: system + up to N previous turns (stopping at a break),
   ending with a `user` turn, then the child turn as the target. The context may start with a
   child turn; that is valid chat format and keeps exactly N turns.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .clean import CleanConfig, CleanResult, clean_utterance
from .parse_chat import Transcript
from .silence import SilenceConfig, gaps_ms, is_timed, silence_token

BREAK = "break"


@dataclass
class Turn:
    role: str  # "user" | "assistant" | "break"
    texts: list[str] = field(default_factory=list)
    target_ok: bool = True
    n_silence: int = 0

    @property
    def text(self) -> str:
        return " ".join(self.texts)


@dataclass
class BuildConfig:
    context_turns: int = 6
    system_prompt: str = "You are a {age}-year-old child talking with a caregiver. Reply the way a real child of that age would."
    break_speakers: dict[str, list[str]] = field(default_factory=dict)  # corpus -> speaker codes
    break_roles: tuple[str, ...] = ("Media",)
    # An utterance that is ONLY unintelligible (e.g. "xxx .") still shows someone spoke. Keeping a
    # placeholder preserves turn-taking (otherwise the adult turns around it would be merged).
    # It is never a training target. Set to "" to drop such utterances instead.
    unintelligible_placeholder: str = "(unintelligible)"
    clean: CleanConfig = field(default_factory=CleanConfig)
    silence: SilenceConfig = field(default_factory=SilenceConfig)


def build_turns(t: Transcript, target: str | set[str], cfg: BuildConfig, counter: Counter) -> tuple[list[Turn], dict]:
    breaks = set(cfg.break_speakers.get(t.corpus, []))
    breaks |= {code for code, p in t.participants.items() if p.role in cfg.break_roles}
    target_speakers = {target} if isinstance(target, str) else target

    cleaned: list[tuple[str, CleanResult, tuple]] = []
    for u in t.utterances:
        side = BREAK if u.speaker in breaks else ("assistant" if u.speaker in target_speakers else "user")
        r = clean_utterance(u.text, counter, cfg.clean)
        cleaned.append((side, r, (u.start_ms, u.end_ms)))

    # Silence gaps over every utterance that had any speech (even if unintelligible).
    speech_idx = [i for i, (_, r, _) in enumerate(cleaned) if not r.empty or r.unintelligible]
    times = [cleaned[i][2] for i in speech_idx]
    timed = is_timed(times, cfg.silence)
    gap_by_idx = dict(zip(speech_idx, gaps_ms(times))) if timed else {}

    turns: list[Turn] = []
    gaps_seen: list[int] = []
    for i, (side, r, _) in enumerate(cleaned):
        if side == BREAK:
            counter["break_speaker_utts"] += 1
            if not turns or turns[-1].role != BREAK:
                turns.append(Turn(BREAK))
            continue
        if r.foreign:
            counter["dropped_foreign_utts"] += 1
            continue
        text = r.text
        if r.empty:
            if not (r.unintelligible and cfg.unintelligible_placeholder):
                continue
            text = cfg.unintelligible_placeholder
            counter["unintelligible_placeholder"] += 1
        gap = gap_by_idx.get(i)
        tok = silence_token(gap, cfg.silence)
        if gap is not None and gap >= cfg.silence.threshold_s * 1000:
            gaps_seen.append(gap)
        if tok:
            text = f"{tok} {text}"
        if turns and turns[-1].role == side:
            turns[-1].texts.append(text)
            counter[f"merged_{side}_utts"] += 1
        else:
            turns.append(Turn(side, [text]))
        turns[-1].n_silence += bool(tok)
        if side == "assistant" and not r.target_ok():
            turns[-1].target_ok = False
    info = {"timed": timed, "silence_gaps_ms": gaps_seen}
    return turns, info


def examples_from_turns(
    turns: list[Turn],
    system: str,
    n_context: int,
    counter: Counter,
    target_label: str = "child",
) -> list[tuple[int, list[dict]]]:
    """Return (turn_index, messages) pairs."""
    out = []
    context_label = "adult" if target_label == "child" else "child"
    for i, turn in enumerate(turns):
        if turn.role != "assistant":
            continue
        counter[f"{target_label}_turns"] += 1
        if not turn.target_ok:
            counter["target_dropped_unusable"] += 1
            continue
        if i == 0 or turns[i - 1].role != "user":
            counter[f"target_dropped_no_{context_label}_before"] += 1
            continue
        ctx: list[Turn] = []
        for prev in reversed(turns[max(0, i - n_context):i]):
            if prev.role == BREAK:
                break
            ctx.insert(0, prev)
        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": c.role, "content": c.text} for c in ctx]
        msgs.append({"role": "assistant", "content": turn.text})
        out.append((i, msgs))
    return out
