from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from typing import Any, Literal, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError


class TranscriptMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class CreateConversationRequest(BaseModel):
    owner_id: str = Field(min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, max_length=200)


class AppendIterationRequest(BaseModel):
    owner_id: str = Field(min_length=1, max_length=128)
    messages: list[TranscriptMessage] = Field(min_length=1, max_length=128)
    model: Optional[str] = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    owner_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    latest_version: int


class IterationResponse(BaseModel):
    version: int
    messages: list[TranscriptMessage]
    model: Optional[str]
    metadata: dict[str, Any]
    created_at: datetime


class TranscriptResponse(BaseModel):
    conversation_id: str
    version: int
    messages: list[TranscriptMessage]


class MongoTranscriptStore:
    def __init__(self, database: Any) -> None:
        self.conversations = database["conversations"]
        self.iterations = database["transcript_iterations"]
        self.conversations.create_index([("owner_id", ASCENDING), ("updated_at", -1)])
        self.iterations.create_index(
            [("conversation_id", ASCENDING), ("version", ASCENDING)],
            unique=True,
        )

    @staticmethod
    def _object_id(conversation_id: str) -> ObjectId:
        try:
            return ObjectId(conversation_id)
        except (InvalidId, TypeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    @staticmethod
    def _conversation_response(
        document: dict[str, Any],
        latest_version: int,
    ) -> ConversationResponse:
        return ConversationResponse(
            id=str(document["_id"]),
            owner_id=document["owner_id"],
            title=document.get("title"),
            created_at=document["created_at"],
            updated_at=document["updated_at"],
            latest_version=latest_version,
        )

    def _latest_version(self, conversation_id: ObjectId) -> int:
        latest = self.iterations.find_one(
            {"conversation_id": conversation_id},
            sort=[("version", DESCENDING)],
            projection={"version": 1},
        )
        return latest["version"] if latest else 0

    def create_conversation(self, request: CreateConversationRequest) -> ConversationResponse:
        now = datetime.now(timezone.utc)
        document = {
            "owner_id": request.owner_id,
            "title": request.title,
            "created_at": now,
            "updated_at": now,
        }
        result = self.conversations.insert_one(document)
        document["_id"] = result.inserted_id
        return self._conversation_response(document, latest_version=0)

    def list_conversations(self, owner_id: str, limit: int) -> list[ConversationResponse]:
        documents = self.conversations.find({"owner_id": owner_id}).sort("updated_at", -1).limit(limit)
        return [
            self._conversation_response(document, self._latest_version(document["_id"]))
            for document in documents
        ]

    def get_conversation(self, conversation_id: str, owner_id: str) -> Optional[ConversationResponse]:
        document = self.conversations.find_one(
            {"_id": self._object_id(conversation_id), "owner_id": owner_id}
        )
        return (
            self._conversation_response(document, self._latest_version(document["_id"]))
            if document
            else None
        )

    def append_iteration(
        self,
        conversation_id: str,
        request: AppendIterationRequest,
    ) -> Optional[IterationResponse]:
        object_id = self._object_id(conversation_id)
        now = datetime.now(timezone.utc)
        conversation = self.conversations.find_one_and_update(
            {"_id": object_id, "owner_id": request.owner_id},
            {"$set": {"updated_at": now}},
        )
        if conversation is None:
            return None

        for _ in range(10):
            document = {
                "conversation_id": object_id,
                "version": self._latest_version(object_id) + 1,
                "messages": [message.model_dump() for message in request.messages],
                "model": request.model,
                "metadata": request.metadata,
                "created_at": now,
            }
            try:
                self.iterations.insert_one(document)
                return IterationResponse(
                    **{key: value for key, value in document.items() if key != "conversation_id"}
                )
            except DuplicateKeyError:
                continue
        raise HTTPException(status_code=409, detail="Could not allocate a transcript iteration")

    def list_iterations(
        self,
        conversation_id: str,
        owner_id: str,
    ) -> Optional[list[IterationResponse]]:
        object_id = self._object_id(conversation_id)
        if self.conversations.find_one({"_id": object_id, "owner_id": owner_id}) is None:
            return None
        documents = self.iterations.find({"conversation_id": object_id}).sort("version", ASCENDING)
        return [
            IterationResponse(**{key: value for key, value in document.items() if key not in ("_id", "conversation_id")})
            for document in documents
        ]

    def get_transcript(
        self,
        conversation_id: str,
        owner_id: str,
        version: Optional[int],
    ) -> Optional[TranscriptResponse]:
        object_id = self._object_id(conversation_id)
        conversation = self.conversations.find_one({"_id": object_id, "owner_id": owner_id})
        if conversation is None:
            return None

        latest_version = self._latest_version(object_id)
        target_version = latest_version if version is None else version
        if target_version > latest_version:
            return None
        documents = self.iterations.find(
            {"conversation_id": object_id, "version": {"$lte": target_version}}
        ).sort("version", ASCENDING)
        messages = [
            TranscriptMessage(**message)
            for document in documents
            for message in document["messages"]
        ]
        return TranscriptResponse(
            conversation_id=str(object_id),
            version=target_version,
            messages=messages,
        )


def create_app(store: Optional[MongoTranscriptStore] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if store is None:
            client = MongoClient(
                os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                serverSelectionTimeoutMS=5000,
            )
            client.admin.command("ping")
            database = client[os.getenv("MONGODB_DATABASE", "simulearn")]
            app.state.transcript_store = MongoTranscriptStore(database)
            try:
                yield
            finally:
                client.close()
        else:
            app.state.transcript_store = store
            yield

    app = FastAPI(
        title="SimuLearn Transcript API",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/conversations",
        response_model=ConversationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_conversation(
        payload: CreateConversationRequest,
        request: Request,
    ) -> ConversationResponse:
        return request.app.state.transcript_store.create_conversation(payload)

    @app.get("/api/v1/conversations", response_model=list[ConversationResponse])
    def list_conversations(
        request: Request,
        owner_id: str = Query(min_length=1, max_length=128),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[ConversationResponse]:
        return request.app.state.transcript_store.list_conversations(owner_id, limit)

    @app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse)
    def get_conversation(
        conversation_id: str,
        request: Request,
        owner_id: str = Query(min_length=1, max_length=128),
    ) -> ConversationResponse:
        conversation = request.app.state.transcript_store.get_conversation(conversation_id, owner_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    @app.post(
        "/api/v1/conversations/{conversation_id}/iterations",
        response_model=IterationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def append_iteration(
        conversation_id: str,
        payload: AppendIterationRequest,
        request: Request,
    ) -> IterationResponse:
        iteration = request.app.state.transcript_store.append_iteration(conversation_id, payload)
        if iteration is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return iteration

    @app.get(
        "/api/v1/conversations/{conversation_id}/iterations",
        response_model=list[IterationResponse],
    )
    def list_iterations(
        conversation_id: str,
        request: Request,
        owner_id: str = Query(min_length=1, max_length=128),
    ) -> list[IterationResponse]:
        iterations = request.app.state.transcript_store.list_iterations(conversation_id, owner_id)
        if iterations is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return iterations

    @app.get(
        "/api/v1/conversations/{conversation_id}/transcript",
        response_model=TranscriptResponse,
    )
    def get_transcript(
        conversation_id: str,
        request: Request,
        owner_id: str = Query(min_length=1, max_length=128),
        version: Optional[int] = Query(default=None, ge=1),
    ) -> TranscriptResponse:
        transcript = request.app.state.transcript_store.get_transcript(
            conversation_id,
            owner_id,
            version,
        )
        if transcript is None:
            raise HTTPException(status_code=404, detail="Conversation or transcript version not found")
        return transcript

    return app


app = create_app()
