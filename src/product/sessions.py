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

A turn record is {"turn", "adult", "text", "secs", "seed"}; read back it also has "version" (its place in
that side's conversation: iteration version in MongoDB, 1, 2, ... in memory) and "model".

Ratings (POST /api/feedback): `MongoSessions` writes them with `DemoStore.rate` to the `feedback` collection
(conversation_id = that side's conversation ObjectId, version = the rated iteration, plus session_id and turn);
`MemorySessions` keeps them in memory and reports them as not saved. Later ratings of the same reply win.
"""
from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.demo.store import EMPTY_REPLY, DemoStore

SIDES = ("child", "untrained")
SESSIONS_COLLECTION = "practice_sessions"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def latest_ratings(rows: list[dict]) -> dict[tuple[str, int], dict]:
    """{(side, turn): {"liked", "note"}} from rating rows in the order they were made (the last one wins)."""
    return {(r["side"], r["turn"]): {"liked": bool(r["liked"]), "note": r.get("note") or ""} for r in rows}


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
        self._ratings: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def create(self, owner_id: str, age: int, scenario_id: Optional[str], compare: bool) -> dict:
        s = new_session(owner_id, age, scenario_id, compare)
        with self._lock:
            self._sessions[s["_id"]] = s
            self._turns[s["_id"]] = {side: [] for side in SIDES}
            self._ratings[s["_id"]] = []
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
            done = self._turns[session["_id"]][side]
            done.append({**turn, "version": len(done) + 1, "model": model})

    def recent(self, owner_id: str, limit: int) -> list[dict]:
        """The owner's sessions of this process, newest first, each with "turns" = number of child turns."""
        with self._lock:
            mine = [s for s in self._sessions.values() if s["owner_id"] == owner_id][::-1]  # newest created last
            mine.sort(key=lambda s: s["created_at"], reverse=True)  # stable: same timestamp keeps newest first
            return [{**copy.deepcopy(s), "turns": len(self._turns[s["_id"]]["child"])} for s in mine[:limit]]

    def rate(self, session: dict, side: str, turn: dict, liked: bool, note: str) -> bool:
        """Kept for this process only, so the answer is False: not saved."""
        with self._lock:
            self._ratings[session["_id"]].append({"side": side, "turn": turn["turn"], "liked": liked,
                                                  "note": note.strip()})
        return False

    def ratings(self, session: dict) -> dict[tuple[str, int], dict]:
        with self._lock:
            return latest_ratings(copy.deepcopy(self._ratings[session["_id"]]))


class MongoSessions:
    """Saving on: metadata in `practice_sessions`, turns in the transcript store (one conversation per side)."""

    saving = True

    def __init__(self, database: Any):
        from backend.app.main import MongoTranscriptStore

        self.transcripts = MongoTranscriptStore(database)
        self.sessions = database[SESSIONS_COLLECTION]
        self.sessions.create_index([("owner_id", 1), ("created_at", -1)])
        self.feedback_store = DemoStore(database)
        self.feedback = self.feedback_store.feedback
        self.feedback.create_index([("session_id", 1), ("created_at", 1)])

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
                        "secs": it.metadata.get("gen_seconds"), "seed": it.metadata.get("seed"),
                        "version": it.version, "model": it.model})
        return out

    def append(self, session: dict, side: str, turn: dict, model: str, metadata: dict) -> None:
        from backend.app.main import AppendIterationRequest, TranscriptMessage

        saved = self.transcripts.append_iteration(session["conversations"][side], AppendIterationRequest(
            owner_id=session["owner_id"], model=model, metadata=metadata,
            messages=[TranscriptMessage(role="user", content=turn["adult"]),
                      TranscriptMessage(role="assistant", content=turn["text"] or EMPTY_REPLY)]))
        if saved is None:
            raise RuntimeError("conversation not found while saving a turn")

    def recent(self, owner_id: str, limit: int) -> list[dict]:
        """The owner's saved sessions, newest first, each with "turns" = number of child turns."""
        out = []
        for s in self.sessions.find({"owner_id": owner_id}).sort("created_at", -1).limit(limit):
            cid = s["conversations"].get("child")
            n = self.transcripts.iterations.count_documents(
                {"conversation_id": self.transcripts._object_id(cid)}) if cid else 0
            out.append({**s, "turns": n})
        return out

    def rate(self, session: dict, side: str, turn: dict, liked: bool, note: str) -> bool:
        """One row in `feedback`; True when it was stored."""
        return self.feedback_store.rate(session["conversations"][side], session["owner_id"], turn["version"],
                                        side, liked, turn["text"], note,
                                        extra={"session_id": session["_id"], "turn": turn["turn"]})

    def ratings(self, session: dict) -> dict[tuple[str, int], dict]:
        rows = self.feedback.find({"session_id": session["_id"], "owner_id": session["owner_id"]})
        return latest_ratings(list(rows.sort([("created_at", 1), ("_id", 1)])))


def history(turns: list[dict], since: int = 1, before: Optional[int] = None) -> list[dict]:
    """Chat messages (user/assistant) for the turns numbered since <= turn < before, in order."""
    msgs = []
    for t in sorted(turns, key=lambda t: t["turn"]):
        if t["turn"] >= since and (before is None or t["turn"] < before):
            msgs += [{"role": "user", "content": t["adult"]}, {"role": "assistant", "content": t["text"]}]
    return msgs
