"""Practice sessions for the product API (src/product/server.py): where the turns of a conversation live.

A session is one practice conversation of an educator with the child model at one age. It has up to two
sides, each its own conversation:
- "child": the fine-tuned model for that age (always on);
- "untrained": the same base model with the LoRA add-on switched off, only while "compare" is on.

The server keeps no conversation state between requests: every request reads the session and its turns back
from a store and rebuilds the model's history from them.

Two stores with the same interface:
- `MongoSessions` (saving on): session metadata in the `practice_sessions` collection; the turns go through the
  team's transcript store (`MongoTranscriptStore`: `conversations` + `transcript_iterations`, one iteration per
  turn: the adult line + that side's reply), owner_id = the user's id. On the child side, iteration version ==
  turn number; every iteration also records its turn in metadata.turn.
- `MemorySessions` (saving off, no MongoDB): the same data in a dict, for the life of the process.

A turn record is {"turn", "adult", "text", "secs", "seed"}.
"""
from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.demo.store import EMPTY_REPLY

SIDES = ("child", "untrained")
SESSIONS_COLLECTION = "practice_sessions"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_session(owner_id: str, age: int, scenario_id: Optional[str], compare: bool) -> dict:
    return {
        "_id": uuid.uuid4().hex,
        "owner_id": owner_id,
        "age": age,
        "scenario_id": scenario_id,
        "compare": compare,
        # the first turn the untrained side answers (its history starts there); None = compare never on
        "compare_started_turn": 1 if compare else None,
        "conversations": {},
        "created_at": utcnow(),
    }


class MemorySessions:
    """Saving off: sessions live in this process only and are gone after a restart."""

    saving = False

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._turns: dict[str, dict[str, list[dict]]] = {}
        self._lock = threading.Lock()

    def create(self, owner_id: str, age: int, scenario_id: Optional[str], compare: bool) -> dict:
        s = new_session(owner_id, age, scenario_id, compare)
        with self._lock:
            self._sessions[s["_id"]] = s
            self._turns[s["_id"]] = {side: [] for side in SIDES}
        return copy.deepcopy(s)

    def get(self, session_id: str, owner_id: str) -> Optional[dict]:
        s = self._sessions.get(session_id)
        return copy.deepcopy(s) if s is not None and s["owner_id"] == owner_id else None

    def update(self, session: dict, **fields: Any) -> dict:
        with self._lock:
            self._sessions[session["_id"]].update(copy.deepcopy(fields))
            return copy.deepcopy(self._sessions[session["_id"]])

    def turns(self, session: dict, side: str) -> list[dict]:
        return copy.deepcopy(self._turns[session["_id"]][side])

    def append(self, session: dict, side: str, turn: dict, model: str, metadata: dict) -> None:
        with self._lock:
            self._turns[session["_id"]][side].append(dict(turn))


class MongoSessions:
    """Saving on: metadata in `practice_sessions`, turns in the transcript store (one conversation per side)."""

    saving = True

    def __init__(self, database: Any):
        from backend.app.main import MongoTranscriptStore

        self.transcripts = MongoTranscriptStore(database)
        self.sessions = database[SESSIONS_COLLECTION]
        self.sessions.create_index([("owner_id", 1), ("created_at", -1)])

    def create(self, owner_id: str, age: int, scenario_id: Optional[str], compare: bool) -> dict:
        s = new_session(owner_id, age, scenario_id, compare)
        s["conversations"] = {"child": self._new_conversation(s, "child")}
        if compare:
            s["conversations"]["untrained"] = self._new_conversation(s, "untrained")
        self.sessions.insert_one(s)
        return s

    def _new_conversation(self, session: dict, side: str) -> str:
        from backend.app.main import CreateConversationRequest

        return self.transcripts.create_conversation(CreateConversationRequest(
            owner_id=session["owner_id"], title=f"practice age{session['age']} {side}")).id

    def get(self, session_id: str, owner_id: str) -> Optional[dict]:
        return self.sessions.find_one({"_id": session_id, "owner_id": owner_id})

    def update(self, session: dict, **fields: Any) -> dict:
        if fields.get("compare") and "untrained" not in session["conversations"]:
            fields["conversations"] = {**session["conversations"], "untrained": self._new_conversation(session, "untrained")}
        self.sessions.update_one({"_id": session["_id"]}, {"$set": fields})
        return {**session, **fields}

    def turns(self, session: dict, side: str) -> list[dict]:
        cid = session["conversations"].get(side)
        if not cid:
            return []
        out = []
        for it in self.transcripts.list_iterations(cid, session["owner_id"]) or []:
            adult, reply = it.messages[0].content, it.messages[1].content
            out.append({"turn": it.metadata.get("turn", it.version), "adult": adult,
                        "text": "" if reply == EMPTY_REPLY else reply,
                        "secs": it.metadata.get("gen_seconds"), "seed": it.metadata.get("seed")})
        return out

    def append(self, session: dict, side: str, turn: dict, model: str, metadata: dict) -> None:
        from backend.app.main import AppendIterationRequest, TranscriptMessage

        saved = self.transcripts.append_iteration(session["conversations"][side], AppendIterationRequest(
            owner_id=session["owner_id"], model=model, metadata=metadata,
            messages=[TranscriptMessage(role="user", content=turn["adult"]),
                      TranscriptMessage(role="assistant", content=turn["text"] or EMPTY_REPLY)]))
        if saved is None:
            raise RuntimeError("conversation not found while saving a turn")


def history(turns: list[dict], since: int = 1, before: Optional[int] = None) -> list[dict]:
    """Chat messages (user/assistant) for the turns numbered since <= turn < before, in order."""
    msgs = []
    for t in sorted(turns, key=lambda t: t["turn"]):
        if t["turn"] >= since and (before is None or t["turn"] < before):
            msgs += [{"role": "user", "content": t["adult"]}, {"role": "assistant", "content": t["text"]}]
    return msgs
