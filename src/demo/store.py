"""Saves demo chats and feedback to MongoDB, reusing the team's transcript store (backend/app/main.py).

Set MONGODB_URI (and optionally MONGODB_DATABASE, default "simulearn") to turn saving on. Without it, or if
the database can't be reached, every call is a no-op and the demo still works. Saving never breaks a chat:
errors are logged and swallowed.

Each side of the side-by-side demo (untrained / fine-tuned) is its own conversation in `conversations` +
`transcript_iterations`, one iteration per turn (the adult line + that side's reply), linked by
metadata.session. Ratings go to a separate `feedback` collection, because transcript iterations are append-only.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)
EMPTY_REPLY = "(no reply)"  # the backend rejects empty messages; an empty model reply is stored as this marker


class DemoStore:
    def __init__(self, database: Any = None):
        self.transcripts = None
        self.feedback = None
        if database is not None:
            from backend.app.main import MongoTranscriptStore

            self.transcripts = MongoTranscriptStore(database)
            self.feedback = database["feedback"]
            self.feedback.create_index("conversation_id")

    @classmethod
    def from_env(cls) -> "DemoStore":
        uri = os.getenv("MONGODB_URI")
        if not uri:
            return cls()
        try:
            from pymongo import MongoClient

            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            return cls(client[os.getenv("MONGODB_DATABASE", "simulearn")])
        except Exception as e:  # bad URI, network, auth: run without saving rather than not at all
            log.error("MongoDB unavailable, chats will not be saved: %s", e)
            return cls()

    @property
    def enabled(self) -> bool:
        return self.transcripts is not None

    def start(self, owner_id: str, age: int, sides: list[str]) -> dict[str, str]:
        """Create one conversation per side; returns {side: conversation_id} ({} when disabled)."""
        if not self.enabled:
            return {}
        from backend.app.main import CreateConversationRequest

        try:
            return {side: self.transcripts.create_conversation(
                        CreateConversationRequest(owner_id=owner_id, title=f"demo age{age} {side}")).id
                    for side in sides}
        except Exception as e:
            log.error("could not start conversation: %s", e)
            return {}

    def log_turn(self, conversation_id: Optional[str], owner_id: str, adult: str, reply: str,
                 model: str, metadata: dict[str, Any]) -> Optional[int]:
        """Append one turn; returns its version number (None when disabled or on error)."""
        if not self.enabled or not conversation_id:
            return None
        from backend.app.main import AppendIterationRequest, TranscriptMessage

        try:
            it = self.transcripts.append_iteration(conversation_id, AppendIterationRequest(
                owner_id=owner_id, model=model, metadata=metadata,
                messages=[TranscriptMessage(role="user", content=adult),
                          TranscriptMessage(role="assistant", content=reply or EMPTY_REPLY)]))
            return it.version if it else None
        except Exception as e:
            log.error("could not save turn: %s", e)
            return None

    def rate(self, conversation_id: Optional[str], owner_id: str, version: int, side: str,
             liked: bool, reply: str, note: str = "") -> bool:
        if not self.enabled or not conversation_id:
            return False
        try:
            self.feedback.insert_one({
                "conversation_id": conversation_id, "version": version, "side": side, "owner_id": owner_id,
                "liked": bool(liked), "reply": reply, "note": note.strip(),
                "created_at": datetime.now(timezone.utc)})
            return True
        except Exception as e:
            log.error("could not save feedback: %s", e)
            return False


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
