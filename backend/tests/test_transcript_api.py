import mongomock
from fastapi.testclient import TestClient

from backend.app.main import MongoTranscriptStore, create_app


def make_client() -> TestClient:
    store = MongoTranscriptStore(mongomock.MongoClient().simulearn)
    return TestClient(create_app(store))


def test_transcripts_are_append_only_and_retrievable_by_version() -> None:
    with make_client() as client:
        created = client.post(
            "/api/v1/conversations",
            json={"owner_id": "learner-1", "title": "First words"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["id"]

        first = client.post(
            f"/api/v1/conversations/{conversation_id}/iterations",
            json={
                "owner_id": "learner-1",
                "model": "simulearn-model",
                "messages": [
                    {"role": "user", "content": "What is this?"},
                    {"role": "assistant", "content": "It is a ball."},
                ],
            },
        )
        second = client.post(
            f"/api/v1/conversations/{conversation_id}/iterations",
            json={
                "owner_id": "learner-1",
                "messages": [
                    {"role": "user", "content": "What color is it?"},
                    {"role": "assistant", "content": "It is red."},
                ],
            },
        )

        assert first.status_code == second.status_code == 201
        assert first.json()["version"] == 1
        assert second.json()["version"] == 2
        conversation = client.get(
            f"/api/v1/conversations/{conversation_id}",
            params={"owner_id": "learner-1"},
        )
        assert conversation.json()["latest_version"] == 2
        assert len(client.get(
            f"/api/v1/conversations/{conversation_id}/iterations",
            params={"owner_id": "learner-1"},
        ).json()) == 2

        earlier = client.get(
            f"/api/v1/conversations/{conversation_id}/transcript",
            params={"owner_id": "learner-1", "version": 1},
        )
        latest = client.get(
            f"/api/v1/conversations/{conversation_id}/transcript",
            params={"owner_id": "learner-1"},
        )

        assert earlier.status_code == latest.status_code == 200
        assert earlier.json()["version"] == 1
        assert [message["content"] for message in earlier.json()["messages"]] == [
            "What is this?",
            "It is a ball.",
        ]
        assert latest.json()["version"] == 2
        assert len(latest.json()["messages"]) == 4
        future = client.get(
            f"/api/v1/conversations/{conversation_id}/transcript",
            params={"owner_id": "learner-1", "version": 3},
        )
        assert future.status_code == 404


def test_conversation_is_scoped_to_its_owner() -> None:
    with make_client() as client:
        created = client.post(
            "/api/v1/conversations",
            json={"owner_id": "learner-1"},
        )
        conversation_id = created.json()["id"]

        response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            params={"owner_id": "learner-2"},
        )
        append = client.post(
            f"/api/v1/conversations/{conversation_id}/iterations",
            json={
                "owner_id": "learner-2",
                "messages": [{"role": "user", "content": "Private message"}],
            },
        )

        assert response.status_code == 404
        assert append.status_code == 404


def test_invalid_conversation_id_returns_not_found() -> None:
    with make_client() as client:
        response = client.get(
            "/api/v1/conversations/not-an-object-id",
            params={"owner_id": "learner-1"},
        )

    assert response.status_code == 404
