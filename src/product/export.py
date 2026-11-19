"""A finished practice session as data: the read-only view (GET /api/sessions/{id}) and the downloads
(GET /api/sessions/{id}/export?format=txt|json). Pure functions over what the session store returns
(src/product/sessions.py), so they are tested without a server.

The detail (`session_detail`) is the JSON export too. The .txt export is for reading: a short header (date,
age, scenario, which model is which), then one block per turn with lines labelled "Adult:", "Child:" and
"Untrained AI:"; a <SILENCE FOR X SECONDS> tag reads "(pauses X s)".
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.demo.engine import SILENCE_RE

LABELS = {"adult": "Adult", "child": "Child", "untrained": "Untrained AI"}
NO_REPLY = "(no reply)"


def iso_utc(when: datetime) -> str:
    """MongoDB hands datetimes back without a timezone; they are UTC."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pause_s(text: str) -> Optional[int]:
    """Seconds of a leading silence tag (the child pauses before answering), else None."""
    m = SILENCE_RE.match(text.strip())
    return int(m.group(1)) if m else None


def summary(session: dict, turns: int, scenario_title: Optional[str]) -> dict:
    """One row of GET /api/sessions (SessionSummary in frontend/src/api.ts)."""
    return {"id": session["_id"], "created_at": iso_utc(session["created_at"]), "age": session["age"],
            "scenario_title": scenario_title, "turns": turns, "compare": bool(session["compare"])}


def _reply(t: dict, rating: Optional[dict]) -> dict:
    return {"text": t["text"], "pause_s": pause_s(t["text"]), "secs": t.get("secs"), "rating": rating}


def session_detail(session: dict, child: list[dict], untrained: list[dict], ratings: dict[tuple[str, int], dict],
                   scenario_title: Optional[str], age_label: str, base_model: str) -> dict:
    """GET /api/sessions/{id} (SessionDetail in frontend/src/api.ts): both sides lined up by turn.

    `models` names what produced each side: the child side's stored model (age<N>:<adapter run>), and the
    untrained side's base model (None when compare was never on)."""
    by_turn = {t["turn"]: t for t in untrained}
    child = sorted(child, key=lambda t: t["turn"])
    exchanges = [{"turn": t["turn"], "adult": t["adult"],
                  "child": _reply(t, ratings.get(("child", t["turn"]))),
                  "untrained": (_reply(by_turn[t["turn"]], ratings.get(("untrained", t["turn"])))
                                if t["turn"] in by_turn else None)}
                 for t in child]
    child_model = next((t.get("model") for t in child if t.get("model")), None)
    untrained_model = next((t.get("model") for t in untrained if t.get("model")), None)
    if untrained_model is None and session.get("compare_started_turn") is not None:
        untrained_model = base_model
    return {**summary(session, len(child), scenario_title),
            "age_label": age_label, "scenario_id": session["scenario_id"],
            "compare_started_turn": session.get("compare_started_turn"),
            "models": {"child": child_model, "untrained": untrained_model},
            "exchanges": exchanges}


def one_line(text: str) -> str:
    return " ".join(text.split())


def plain_reply(text: str) -> str:
    """A reply as readable text: silence tags become "(pauses X s)"."""
    return one_line(SILENCE_RE.sub(lambda m: f"(pauses {m.group(1)} s)", text)) or NO_REPLY


def to_txt(detail: dict) -> str:
    when = datetime.fromisoformat(detail["created_at"].replace("Z", "+00:00"))
    age = f"{detail['age']}" + (f" ({detail['age_label']})" if detail.get("age_label") else "")
    models = detail["models"]
    lines = ["SimuLearn practice session",
             f"Date: {when:%Y-%m-%d %H:%M} UTC",
             f"Child age: {age}",
             f"Scenario: {detail['scenario_title'] or 'free practice (no scenario)'}",
             f"Session: {detail['id']}",
             f"Model for \"{LABELS['child']}\": fine-tuned child model ({models['child'] or 'none yet'})"]
    if models.get("untrained"):
        lines.append(f"Model for \"{LABELS['untrained']}\": the same base model without fine-tuning "
                     f"({models['untrained']})")
    lines += [f"Turns: {detail['turns']}", ""]
    for ex in detail["exchanges"]:
        lines.append(f"{LABELS['adult']}: {one_line(ex['adult'])}")
        lines.append(f"{LABELS['child']}: {plain_reply(ex['child']['text'])}")
        if ex["untrained"] is not None:
            lines.append(f"{LABELS['untrained']}: {plain_reply(ex['untrained']['text'])}")
        lines.append("")
    return "\n".join(lines)


def to_json(detail: dict) -> str:
    return json.dumps(detail, ensure_ascii=False, indent=2) + "\n"


def filename(detail: dict, fmt: str) -> str:
    """e.g. simulearn-20261119-1403-age5-1a2b3c4d.txt (only safe characters, so no header escaping)."""
    when = datetime.fromisoformat(detail["created_at"].replace("Z", "+00:00"))
    sid = re.sub(r"[^A-Za-z0-9]", "", str(detail["id"]))[:8]
    return f"simulearn-{when:%Y%m%d-%H%M}-age{int(detail['age'])}-{sid}.{fmt}"


def export(detail: dict, fmt: str) -> tuple[str, str, str]:
    """(body, media type, filename) for format "txt" or "json"."""
    if fmt == "txt":
        return to_txt(detail), "text/plain; charset=utf-8", filename(detail, "txt")
    if fmt == "json":
        return to_json(detail), "application/json", filename(detail, "json")
    raise ValueError(f"unknown export format {fmt!r}")


def parse_txt(text: str) -> list[dict[str, Any]]:
    """The labelled lines of a .txt export back as [{"adult", "child", "untrained"?}], one per turn
    (used by the round-trip test; also handy for anyone loading exports back)."""
    out: list[dict[str, Any]] = []
    body = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    by_label = {f"{v}: ": k for k, v in LABELS.items()}
    for block in body.strip().split("\n\n"):
        ex: dict[str, Any] = {}
        for line in block.splitlines():
            for prefix, key in by_label.items():
                if line.startswith(prefix):
                    ex[key] = line[len(prefix):]
                    break
        if ex:
            out.append(ex)
    return out
