"""The product API (src/product/server.py) end to end, with a fake model and an in-memory MongoDB (no GPU,
no network). Same pattern as tests/test_demo_ui.py; accounts as in tests/test_product_auth.py."""
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

from src.product.auth import Auth, LoginRateLimiter
from src.product.server import create_app, load_scenarios, parse_args
from src.product.sessions import MemorySessions, MongoSessions

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct horse battery"
CHILD_REPLY = "<SILENCE FOR 3 SECONDS> it's a tower"
UNTRAINED_REPLY = "Hello there! As a child, I love blocks."
SCENARIOS = [{"id": "blocks", "title": "Blocks", "scene": "Invented scene.", "opening_line": "What are you making?"}]


class FakeEngine:
    def __init__(self):
        self.cfg = {"base_model": "org/some-base-model", "default_age": 5, "context_turns": 3,
                    "decoding": {"temperature": 0.7, "top_p": 0.9, "max_new_tokens": 60}}
        self.adapters = {4: {"path": Path("x/run-a4/adapter"), "label": "48-59 months"},
                         5: {"path": Path("x/run-a5/adapter"), "label": "60-71 months"}}
        self.device, self.seed, self.calls = "cpu", 0, []

    def reply(self, history, adult_line, age, system):
        self.calls.append({"history": [dict(m) for m in history], "adult": adult_line, "age": age, "system": system})
        return CHILD_REPLY if age else UNTRAINED_REPLY


def make(saving=True, dist=None):
    db = mongomock.MongoClient().simulearn
    auth = Auth(db, limiter=LoginRateLimiter())
    for name in ("ada", "bob"):
        auth.create_user(name, name.title(), PASSWORD)
    engine = FakeEngine()
    store = MongoSessions(db) if saving else MemorySessions()
    app = create_app(engine, auth, store, SCENARIOS, frontend_dist=dist)
    return app, engine, db


def client_for(app, username=None, **kw):
    c = TestClient(app, base_url="https://testserver", **kw)
    if username:
        assert c.post("/api/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200
    return c


def start(c, age=5, compare=False, scenario_id=None):
    r = c.post("/api/sessions", json={"age": age, "compare": compare, "scenario_id": scenario_id})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def say(c, sid, line):
    r = c.post(f"/api/sessions/{sid}/turns", json={"adult_line": line})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(params=[True, False], ids=["saving", "memory"])
def setup(request):
    app, engine, db = make(saving=request.param)
    return client_for(app, "ada"), engine, db, request.param


def test_unauthenticated_api_is_401():
    app, engine, _ = make()
    c = client_for(app)
    for method, path, body in [("GET", "/api/config", None), ("GET", "/api/model-info", None),
                               ("POST", "/api/sessions", {"age": 5, "compare": False}),
                               ("POST", "/api/sessions/abc/turns", {"adult_line": "hi"}),
                               ("POST", "/api/sessions/abc/turns/1/untrained", None),
                               ("PATCH", "/api/sessions/abc", {"compare": True})]:
        assert c.request(method, path, json=body).status_code == 401, path
    assert engine.calls == []


def test_config_and_model_info_come_from_the_config(setup):
    c, engine, _, saving = setup
    cfg = c.get("/api/config").json()
    assert cfg["ages"] == [4, 5] and cfg["age_labels"] == {"4": "48-59 months", "5": "60-71 months"}
    assert cfg["saving"] is saving and cfg["compare_default"] is False and cfg["scenarios"] == SCENARIOS
    info = c.get("/api/model-info").json()
    assert info["base_model"] == "org/some-base-model"
    assert info["adapters"] == {"4": "run-a4", "5": "run-a5"}
    assert info["decoding"] == engine.cfg["decoding"] and info["device"] == "cpu"


def test_child_reply_is_the_engine_output_with_pause_parsed(setup):
    c, engine, db, saving = setup
    sid = start(c, scenario_id="blocks")
    r = say(c, sid, "  what are you building?  ")
    assert r["turn"] == 1 and r["text"] == CHILD_REPLY
    assert r["pause_s"] == 3 and r["rendered"] == "*(…pauses 3 s…)* it's a tower"
    assert isinstance(r["secs"], float)
    assert engine.calls[0]["age"] == 5 and "5-year-old" in engine.calls[0]["system"]
    assert engine.calls[0]["adult"] == "what are you building?"
    if saving:
        it = db["transcript_iterations"].find_one({"version": 1})
        assert it["messages"][1]["content"] == CHILD_REPLY and it["model"] == "age5:run-a5"
        assert it["metadata"]["turn"] == 1 and it["metadata"]["scenario_id"] == "blocks"
        assert db["practice_sessions"].find_one({"_id": sid})["age"] == 5


def test_reply_without_silence_has_no_pause(setup):
    c, engine, _, _ = setup
    engine.reply = lambda *a: "yeah"
    r = say(c, start(c), "hi")
    assert r["pause_s"] is None and r["rendered"] == "yeah"


def test_history_is_rebuilt_and_trimmed_like_training(setup):
    c, engine, _, _ = setup
    sid = start(c)
    for line in ["one", "two", "three"]:
        say(c, sid, line)
    # context_turns = 3: the last 2 history messages plus the new adult line
    hist = [m["content"] for m in engine.calls[2]["history"]]
    assert hist == ["one", CHILD_REPLY, "two", CHILD_REPLY]
    from src.demo.engine import build_messages
    msgs = build_messages("sys", engine.calls[2]["history"], "three", 3)
    assert [m["content"] for m in msgs] == ["sys", "two", CHILD_REPLY, "three"]


def test_with_compare_off_the_untrained_model_is_never_called(setup):
    c, engine, _, _ = setup
    sid = start(c, compare=False)
    say(c, sid, "hi")
    say(c, sid, "what's that?")
    r = c.post(f"/api/sessions/{sid}/turns/1/untrained")
    assert r.status_code == 409
    assert [call["age"] for call in engine.calls] == [5, 5]


def test_compare_on_gives_untrained_replies_with_their_own_history(setup):
    c, engine, _, _ = setup
    sid = start(c, compare=True, age=4)
    for n, line in enumerate(["hi", "big tower!"], start=1):
        assert say(c, sid, line)["turn"] == n
        r = c.post(f"/api/sessions/{sid}/turns/{n}/untrained").json()
        assert r == {**r, "turn": n, "text": UNTRAINED_REPLY, "pause_s": None}
    untrained = [call for call in engine.calls if call["age"] is None]
    assert len(untrained) == 2 and "4-year-old" in untrained[1]["system"]
    assert [m["content"] for m in untrained[1]["history"]] == ["hi", UNTRAINED_REPLY]
    # retrying the same turn returns the stored reply without generating again
    assert c.post(f"/api/sessions/{sid}/turns/2/untrained").json()["text"] == UNTRAINED_REPLY
    assert len([call for call in engine.calls if call["age"] is None]) == 2
    assert c.post(f"/api/sessions/{sid}/turns/9/untrained").status_code == 404


def test_toggling_compare_mid_session_starts_untrained_history_at_next_turn(setup):
    c, engine, db, saving = setup
    sid = start(c, compare=False)
    say(c, sid, "one")
    say(c, sid, "two")
    r = c.patch(f"/api/sessions/{sid}", json={"compare": True}).json()
    assert r["compare"] is True and r["compare_started_turn"] == 3
    assert c.post(f"/api/sessions/{sid}/turns/2/untrained").status_code == 409  # before compare was on
    say(c, sid, "three")
    assert c.post(f"/api/sessions/{sid}/turns/3/untrained").status_code == 200
    say(c, sid, "four")
    c.post(f"/api/sessions/{sid}/turns/4/untrained")
    untrained = [call for call in engine.calls if call["age"] is None]
    assert untrained[0]["history"] == []
    assert [m["content"] for m in untrained[1]["history"]] == ["three", UNTRAINED_REPLY]
    if saving:
        doc = db["practice_sessions"].find_one({"_id": sid})
        assert doc["compare_started_turn"] == 3 and "untrained" in doc["conversations"]

    # off, then on again: the untrained history restarts
    assert c.patch(f"/api/sessions/{sid}", json={"compare": False}).json()["compare"] is False
    assert c.post(f"/api/sessions/{sid}/turns/4/untrained").status_code == 409
    say(c, sid, "five")
    assert c.patch(f"/api/sessions/{sid}", json={"compare": True}).json()["compare_started_turn"] == 6
    say(c, sid, "six")
    c.post(f"/api/sessions/{sid}/turns/6/untrained")
    assert [call for call in engine.calls if call["age"] is None][-1]["history"] == []


def test_a_user_cannot_read_or_post_to_another_users_session(setup):
    c, engine, _, _ = setup
    sid = start(c, compare=True)
    say(c, sid, "hi")
    other = client_for(c.app, "bob")
    n = len(engine.calls)
    assert other.post(f"/api/sessions/{sid}/turns", json={"adult_line": "hey"}).status_code == 404
    assert other.post(f"/api/sessions/{sid}/turns/1/untrained").status_code == 404
    assert other.patch(f"/api/sessions/{sid}", json={"compare": False}).status_code == 404
    assert c.post("/api/sessions/not-a-session/turns", json={"adult_line": "hey"}).status_code == 404
    assert len(engine.calls) == n


def test_bad_session_requests_are_rejected(setup):
    c, engine, _, _ = setup
    assert c.post("/api/sessions", json={"age": 9, "compare": False}).status_code == 422
    assert c.post("/api/sessions", json={"age": 5, "compare": False, "scenario_id": "nope"}).status_code == 422
    sid = start(c)
    assert c.post(f"/api/sessions/{sid}/turns", json={"adult_line": "   "}).status_code == 422
    assert engine.calls == []


def test_memory_sessions_do_not_touch_mongo():
    app, _, db = make(saving=False)
    c = client_for(app, "ada")
    say(c, start(c, compare=True), "hi")
    assert db["conversations"].count_documents({}) == 0 and db["practice_sessions"].count_documents({}) == 0


def test_login_rate_limit_uses_cf_connecting_ip_only_from_loopback():
    app, _, _ = make()
    bad = {"username": "ada", "password": "wrong password"}

    def fails(c, ip, n, username="ada"):
        for _ in range(n):
            c.post("/api/auth/login", json={**bad, "username": username}, headers={"CF-Connecting-IP": ip})

    tunnel = client_for(app, client=("127.0.0.1", 40000))
    fails(tunnel, "198.51.100.7", 5)
    auth = app.state.auth
    assert auth.limiter.blocked("ip:198.51.100.7") and not auth.limiter.blocked("ip:127.0.0.1")
    # from anywhere but loopback the header is ignored (anyone could send it)
    direct = client_for(app, client=("203.0.113.9", 40000))
    fails(direct, "198.51.100.99", 1, username="bob")  # ada is blocked by now
    assert not auth.limiter.blocked("ip:198.51.100.99")
    assert len(auth.limiter._failures["ip:203.0.113.9"]) == 1


def test_frontend_is_served_with_spa_fallback(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("no")
    app, _, _ = make(dist=tmp_path)
    c = client_for(app)
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/practice/123").text == "<html>app</html>"
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/../secret.txt").text != "no"
    assert c.get("/api/nothing-here").status_code == 404
    assert c.get("/api/config").status_code == 401


def test_without_frontend_dist_only_the_api_is_served(tmp_path):
    app, _, _ = make(dist=tmp_path)  # no index.html
    assert client_for(app).get("/").status_code == 404


def test_scenarios_file_is_valid_and_the_cli_matches_the_serving_scripts():
    scenarios = load_scenarios(ROOT / "configs" / "scenarios.yaml")
    assert 5 <= len(scenarios) <= 8
    assert all(s["opening_line"] and s["title"] and s["scene"] for s in scenarios)
    a = parse_args([])
    assert (a.config, a.host, a.port, a.device) == ("configs/demo.yaml", "127.0.0.1", 8000, "auto")
    a = parse_args(["--config", "c.yaml", "--host", "0.0.0.0", "--port", "9000", "--device", "cpu"])
    assert (a.config, a.host, a.port, a.device) == ("c.yaml", "0.0.0.0", 9000, "cpu")


def test_no_model_name_is_hard_coded_in_the_product_server():
    for f in ["server.py", "sessions.py", "export.py"]:
        text = (ROOT / "src" / "product" / f).read_text().lower()
        for name in ["qwen", "llama", "smollm", "mistral", "gemma"]:
            assert name not in text, (f, name)


# --- feedback, history and export (#59) ---------------------------------------------------------------------


def rate(c, sid, turn=1, side="child", liked=True, note=""):
    return c.post("/api/feedback", json={"session_id": sid, "turn": turn, "side": side, "liked": liked,
                                         "note": note})


def test_feedback_rows_join_to_their_conversation_by_objectid_with_the_right_version():
    from bson import ObjectId

    app, _, db = make(saving=True)
    c = client_for(app, "ada")
    sid = start(c, compare=False)
    say(c, sid, "one")
    say(c, sid, "two")
    c.patch(f"/api/sessions/{sid}", json={"compare": True})
    say(c, sid, "three")
    c.post(f"/api/sessions/{sid}/turns/3/untrained")  # the untrained side's first iteration (version 1)

    assert rate(c, sid, turn=2, note="  nice  ").json() == {"ok": True, "saved": True}
    assert rate(c, sid, turn=3, side="untrained", liked=False).json() == {"ok": True, "saved": True}
    convs = db["practice_sessions"].find_one({"_id": sid})["conversations"]
    child = db["feedback"].find_one({"side": "child"})
    assert isinstance(child["conversation_id"], ObjectId) and child["conversation_id"] == ObjectId(convs["child"])
    assert child["version"] == 2 and child["turn"] == 2 and child["session_id"] == sid
    assert child["note"] == "nice" and child["liked"] is True and child["reply"] == CHILD_REPLY
    assert db["conversations"].find_one({"_id": child["conversation_id"]}) is not None
    it = db["transcript_iterations"].find_one({"conversation_id": child["conversation_id"], "version": 2})
    assert it["messages"][0]["content"] == "two"
    untrained = db["feedback"].find_one({"side": "untrained"})
    assert untrained["conversation_id"] == ObjectId(convs["untrained"])
    assert untrained["version"] == 1 and untrained["turn"] == 3 and untrained["liked"] is False


def test_feedback_with_saving_off_is_acknowledged_but_not_saved():
    app, _, db = make(saving=False)
    c = client_for(app, "ada")
    sid = start(c)
    say(c, sid, "hi")
    assert rate(c, sid).json() == {"ok": True, "saved": False}
    assert db["feedback"].count_documents({}) == 0
    # kept for this process, so the reopened session shows it
    assert c.get(f"/api/sessions/{sid}").json()["exchanges"][0]["child"]["rating"] == {"liked": True, "note": ""}


def test_feedback_that_fails_to_save_is_not_ok(monkeypatch):
    app, _, db = make(saving=True)
    c = client_for(app, "ada")
    sid = start(c)
    say(c, sid, "hi")

    def broken(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(db["feedback"], "insert_one", broken)
    assert rate(c, sid).json() == {"ok": False, "saved": False}


def test_feedback_for_a_missing_turn_or_side_is_rejected(setup):
    c, _, _, _ = setup
    sid = start(c)
    say(c, sid, "hi")
    assert rate(c, sid, turn=2).status_code == 404
    assert rate(c, sid, side="untrained").status_code == 404  # compare was never on
    assert rate(c, sid, side="adult").status_code == 422
    assert rate(c, "not-a-session").status_code == 404


def test_history_lists_own_sessions_newest_first(setup):
    c, _, _, _ = setup
    first = start(c, age=4, scenario_id="blocks")
    say(c, first, "one")
    say(c, first, "two")
    second = start(c, compare=True)
    other = client_for(c.app, "bob")
    start(other)
    rows = c.get("/api/sessions").json()
    assert [r["id"] for r in rows] == [second, first]
    assert rows[1] == {**rows[1], "age": 4, "scenario_title": "Blocks", "turns": 2, "compare": False}
    assert rows[0] == {**rows[0], "age": 5, "scenario_title": None, "turns": 0, "compare": True}
    assert rows[0]["created_at"].endswith("Z")
    assert [r["id"] for r in c.get("/api/sessions?limit=1").json()] == [second]
    assert c.get("/api/sessions?limit=0").status_code == 422
    assert len(other.get("/api/sessions").json()) == 1


def test_history_with_saving_off_lists_only_this_process():
    app, _, db = make(saving=False)
    # a session saved by an earlier, saving run is not listed by a process that isn't saving
    saved_app = create_app(FakeEngine(), app.state.auth, MongoSessions(db), SCENARIOS)
    start(client_for(saved_app, "ada"))
    assert db["practice_sessions"].count_documents({}) == 1
    c = client_for(app, "ada")
    sid = start(c)
    assert [r["id"] for r in c.get("/api/sessions").json()] == [sid]


def test_session_detail_lines_up_both_sides_with_ratings(setup):
    c, _, _, _ = setup
    sid = start(c, compare=False, scenario_id="blocks")
    say(c, sid, "one")
    c.patch(f"/api/sessions/{sid}", json={"compare": True})
    say(c, sid, "two")
    c.post(f"/api/sessions/{sid}/turns/2/untrained")
    rate(c, sid, turn=2, liked=True)
    rate(c, sid, turn=2, liked=False, note="changed my mind")  # the later rating wins
    d = c.get(f"/api/sessions/{sid}").json()
    assert d["id"] == sid and d["turns"] == 2 and d["compare"] is True and d["compare_started_turn"] == 2
    assert d["age_label"] == "60-71 months" and d["scenario_id"] == "blocks" and d["scenario_title"] == "Blocks"
    assert d["models"] == {"child": "age5:run-a5", "untrained": "org/some-base-model"}
    one, two = d["exchanges"]
    assert one["adult"] == "one" and one["untrained"] is None and one["child"]["rating"] is None
    assert one["child"] == {**one["child"], "text": CHILD_REPLY, "pause_s": 3}
    assert two["untrained"]["text"] == UNTRAINED_REPLY and two["untrained"]["pause_s"] is None
    assert two["child"]["rating"] == {"liked": False, "note": "changed my mind"}


def test_users_only_see_and_export_their_own_sessions(setup):
    c, _, _, _ = setup
    sid = start(c)
    say(c, sid, "hi")
    other = client_for(c.app, "bob")
    assert other.get(f"/api/sessions/{sid}").status_code == 404
    for fmt in ("txt", "json"):
        assert other.get(f"/api/sessions/{sid}/export?format={fmt}").status_code == 404
    assert rate(other, sid).status_code == 404
    assert c.get("/api/sessions/nope").status_code == 404
    assert c.get(f"/api/sessions/{sid}/export?format=pdf").status_code == 422
    anon = client_for(c.app)
    for path in ["/api/sessions", f"/api/sessions/{sid}", f"/api/sessions/{sid}/export"]:
        assert anon.get(path).status_code == 401
    assert anon.post("/api/feedback", json={}).status_code == 401


def test_export_round_trips_in_both_formats(setup):
    from src.product.export import parse_txt

    c, engine, _, _ = setup
    replies = iter(["<SILENCE FOR 4 SECONDS> my dog", "", "yeah <SILENCE FOR 2 SECONDS> big"])
    engine.reply = lambda history, adult, age, system: next(replies) if age else UNTRAINED_REPLY
    sid = start(c, compare=True, scenario_id="blocks")
    for n, line in enumerate(["what's that?", "tell me more", "how big?"], start=1):
        say(c, sid, line)
        if n != 2:
            c.post(f"/api/sessions/{sid}/turns/{n}/untrained")
    rate(c, sid, turn=1, note="sounds real")
    full = c.get(f"/api/sessions/{sid}").json()

    r = c.get(f"/api/sessions/{sid}/export?format=json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json() == full
    disp = r.headers["content-disposition"]
    assert disp.startswith('attachment; filename="simulearn-') and disp.endswith(f'-age5-{sid[:8]}.json"')

    r = c.get(f"/api/sessions/{sid}/export?format=txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"].endswith('.txt"')
    head = r.text.split("\n\n")[0]
    assert "Child age: 5 (60-71 months)" in head and "Scenario: Blocks" in head
    assert 'Model for "Child": fine-tuned child model (age5:run-a5)' in head
    assert 'Model for "Untrained AI": the same base model without fine-tuning (org/some-base-model)' in head
    assert "Date: " in head and " UTC" in head
    assert parse_txt(r.text) == [
        {"adult": "what's that?", "child": "(pauses 4 s) my dog", "untrained": UNTRAINED_REPLY},
        {"adult": "tell me more", "child": "(no reply)"},
        {"adult": "how big?", "child": "yeah (pauses 2 s) big", "untrained": UNTRAINED_REPLY},
    ]
    assert c.get(f"/api/sessions/{sid}/export").headers["content-disposition"].endswith('.txt"')  # default


def test_export_of_a_session_without_scenario_or_compare(setup):
    c, _, _, _ = setup
    sid = start(c)
    say(c, sid, "hi")
    text = c.get(f"/api/sessions/{sid}/export?format=txt").text
    assert "Scenario: free practice (no scenario)" in text and "Untrained AI" not in text
    assert c.get(f"/api/sessions/{sid}").json()["models"]["untrained"] is None
