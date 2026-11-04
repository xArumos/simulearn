"""Demo chat saving (src/demo/store.py) on an in-memory MongoDB, same pattern as backend/tests."""
import mongomock

from src.demo.store import EMPTY_REPLY, DemoStore


def make_store() -> tuple[DemoStore, object]:
    db = mongomock.MongoClient().simulearn
    return DemoStore(db), db


def test_turns_are_saved_as_versioned_iterations_per_side():
    store, db = make_store()
    conv = store.start("tester-1", 5, ["untrained", "fine-tuned"])
    assert set(conv) == {"untrained", "fine-tuned"} and conv["untrained"] != conv["fine-tuned"]

    meta = {"session": "abc", "side": "fine-tuned", "age": 5, "seed": 1235}
    v1 = store.log_turn(conv["fine-tuned"], "tester-1", "what's that?", "a dog", "age5:run3", meta)
    v2 = store.log_turn(conv["fine-tuned"], "tester-1", "what's his name?", "", "age5:run3", meta)
    assert (v1, v2) == (1, 2)

    transcript = store.transcripts.get_transcript(conv["fine-tuned"], "tester-1", None)
    assert [m.content for m in transcript.messages] == ["what's that?", "a dog", "what's his name?", EMPTY_REPLY]
    doc = db["transcript_iterations"].find_one({"version": 1})
    assert doc["model"] == "age5:run3" and doc["metadata"]["age"] == 5
    assert db["conversations"].find_one({"owner_id": "tester-1", "title": "demo age5 untrained"}) is not None


def test_feedback_is_stored_with_its_turn():
    store, db = make_store()
    conv = store.start("tester-1", 4, ["fine-tuned"])["fine-tuned"]
    v = store.log_turn(conv, "tester-1", "hi", "hi", "age4", {})
    assert store.rate(conv, "tester-1", v, "fine-tuned", True, "hi", note="  sounds right  ")
    row = db["feedback"].find_one()
    assert row["liked"] is True and row["version"] == 1 and row["note"] == "sounds right"


def test_disabled_store_is_a_silent_no_op(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    store = DemoStore.from_env()
    assert not store.enabled
    assert store.start("t", 5, ["untrained"]) == {}
    assert store.log_turn("x", "t", "hi", "hi", "m", {}) is None
    assert store.rate("x", "t", 1, "untrained", True, "hi") is False


def test_unreachable_database_falls_back_to_no_saving(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200")
    assert not DemoStore.from_env().enabled


def test_save_errors_never_break_the_chat():
    store, _ = make_store()
    assert store.log_turn("not-an-object-id", "t", "hi", "hi", "m", {}) is None
    conv = store.start("owner-a", 5, ["untrained"])["untrained"]
    assert store.log_turn(conv, "someone-else", "hi", "hi", "m", {}) is None  # owner scoping from the backend
