"""The demo's Gradio handlers end to end, with a fake model and an in-memory MongoDB (no GPU, no network)."""
from pathlib import Path
from types import SimpleNamespace

import gradio as gr
import mongomock

from src.demo.chat_demo import build_ui
from src.demo.store import DemoStore


class FakeDemo:
    def __init__(self):
        self.cfg = {"base_model": "base", "default_age": 5, "context_turns": 6}
        self.adapters = {4: {"path": Path("x/run-a4/adapter"), "label": "a4"}, 5: {"path": Path("x/run-a5/adapter"), "label": "a5"}}
        self.device, self.seed, self.calls = "cpu", 0, []

    def reply(self, history, adult_line, age, system):
        self.calls.append((age, len(history), system))
        return "<SILENCE FOR 2 SECONDS> no" if age else "Hello there! As a child, I love blocks."


def handler(ui, name):
    return next(f.fn for f in ui.fns.values() if getattr(f.fn, "__name__", "") == name)


def test_turns_are_saved_and_ratings_point_at_the_right_turn(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    demo, db = FakeDemo(), mongomock.MongoClient().simulearn
    ui = build_ui(demo, DemoStore(db))
    respond, rate = handler(ui, "respond"), [f.fn for f in ui.fns.values() if f.fn.__name__ == "rate"]
    # Gradio only passes the 👍/👎 event if it can resolve the gr.LikeData type hint
    assert all(f.collects_event_data for f in ui.fns.values() if f.fn.__name__ == "rate")

    state = ("", [], [], [], [], {"id": None, "conv": {}, "versions": {"untrained": [], "fine-tuned": []}})
    for line in ["what's that?", "is it big?"]:
        steps = list(respond(line, "tester", 4, state[1], state[2], state[3], state[4], False, True, state[5]))
        assert steps[0][0]["interactive"] is False and steps[-1][0]["interactive"] is True
        assert steps[-2][3][-1]["content"] == "*(writing…)*"  # untrained column still writing when the child shows
        state = steps[-1]
    _, base_raw, ft_raw, base_chat, ft_chat, session = state

    assert [c[0] for c in demo.calls] == [4, None, 4, None]  # child reply first, each turn
    assert demo.calls[2][1] == 2 and "4-year-old" in demo.calls[2][2]
    assert ft_chat[-1]["content"] == "*(…pauses 2 s…)* no"
    assert session["versions"] == {"untrained": [1, 2], "fine-tuned": [1, 2]}
    assert db["conversations"].count_documents({"owner_id": "tester"}) == 2
    it = db["transcript_iterations"].find_one({"model": "age4:run-a4", "version": 2})
    assert it["messages"][0]["content"] == "is it big?" and it["metadata"]["age"] == 4

    rate_ft = rate[1]  # second .like() registered = fine-tuned column
    note, shown = rate_ft(SimpleNamespace(index=3, liked=False), "tester", "too short", ft_raw, session)
    row = db["feedback"].find_one()
    assert (row["version"], row["side"], row["liked"], row["note"]) == (2, "fine-tuned", False, "too short")
    assert note == "" and "saved" in shown["value"]


def test_without_database_the_chat_still_works():
    demo = FakeDemo()
    ui = build_ui(demo, DemoStore())
    respond = handler(ui, "respond")
    *_, last = respond("hi", "", 5, [], [], [], [], False, False, {"id": None, "conv": {}, "versions": {"untrained": [], "fine-tuned": []}})
    assert last[4][-1]["content"].endswith("no") and last[5]["versions"]["fine-tuned"] == [None]
    assert isinstance(ui, gr.Blocks)
