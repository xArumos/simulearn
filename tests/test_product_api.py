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
    for f in ["server.py", "sessions.py"]:
        text = (ROOT / "src" / "product" / f).read_text().lower()
        for name in ["qwen", "llama", "smollm", "mistral", "gemma"]:
            assert name not in text, (f, name)
