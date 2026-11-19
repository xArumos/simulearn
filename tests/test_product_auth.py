"""User accounts and login (src/product/auth.py, scripts/create_user.py) on an in-memory MongoDB.

Same pattern as tests/test_demo_store.py: mongomock stands in for MongoDB. The router is mounted on a tiny test
app here; the product server mounts the same router.
"""
import hashlib
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.product.auth import (
    COOKIE_NAME,
    Auth,
    LoginRateLimiter,
    current_user,
    router,
)

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct horse battery"


class Clock:
    """A settable clock so expiry and the rate-limit window can be tested without sleeping."""

    def __init__(self):
        self.now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def make_auth(clock=None):
    db = mongomock.MongoClient().simulearn
    clock = clock or Clock()
    auth = Auth(db, clock=clock, limiter=LoginRateLimiter(clock=clock))
    return auth, db, clock


def make_client(auth):
    app = FastAPI()
    app.state.auth = auth
    app.include_router(router)

    @app.get("/api/protected")
    def protected(user=Depends(current_user)):
        return {"who": user["username"]}

    # Secure cookies are only sent back over https, so the test client talks "https" to the in-process app.
    return TestClient(app, base_url="https://testserver")


def login(client, username="ada", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# --- storage -----------------------------------------------------------------------------------------------


def test_password_is_stored_only_as_an_argon2_hash():
    auth, db, _ = make_auth()
    auth.create_user("ada", "Ada L.", PASSWORD, role="educator")
    doc = db["users"].find_one({"username": "ada"})
    assert doc["password_hash"].startswith("$argon2id$")
    assert PASSWORD not in str(doc)
    assert set(doc) >= {"username", "display_name", "password_hash", "role", "disabled", "created_at"}
    assert doc["disabled"] is False and doc["role"] == "educator"


def test_usernames_are_unique_and_normalised():
    auth, _, _ = make_auth()
    auth.create_user("Ada", "Ada", PASSWORD)
    with pytest.raises(ValueError, match="exists"):
        auth.create_user(" ada ", "Other", PASSWORD)


def test_bad_role_short_password_and_bad_username_are_rejected():
    auth, _, _ = make_auth()
    with pytest.raises(ValueError):
        auth.create_user("ada", "Ada", PASSWORD, role="superuser")
    with pytest.raises(ValueError):
        auth.create_user("ada", "Ada", "short")
    with pytest.raises(ValueError):
        auth.create_user("a d a", "Ada", PASSWORD)


def test_session_token_is_stored_only_as_a_sha256_hash():
    auth, db, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    r = login(client)
    assert r.status_code == 200
    token = r.cookies.get(COOKIE_NAME) or client.cookies.get(COOKIE_NAME)
    assert token
    row = db["auth_sessions"].find_one()
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in str(row)


def test_sessions_have_a_ttl_index_on_expires_at():
    auth, db, _ = make_auth()
    info = db["auth_sessions"].index_information()
    ttl = [v for v in info.values() if v.get("key") == [("expires_at", 1)]]
    assert ttl and ttl[0].get("expireAfterSeconds") == 0


# --- HTTP routes -------------------------------------------------------------------------------------------


def test_login_sets_a_hardened_cookie_and_returns_the_user():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada L.", PASSWORD, role="admin")
    client = make_client(auth)
    r = login(client)
    assert r.status_code == 200
    assert r.json() == {"username": "ada", "display_name": "Ada L.", "role": "admin"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert f"max-age={7 * 24 * 3600}" in cookie


def test_me_needs_a_session_and_returns_the_user():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada L.", PASSWORD)
    client = make_client(auth)
    assert client.get("/api/me").status_code == 401
    login(client)
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.json() == {"username": "ada", "display_name": "Ada L.", "role": "educator"}
    assert client.get("/api/protected").json() == {"who": "ada"}


def test_unknown_user_and_wrong_password_fail_identically():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    wrong = login(client, password="not the password")
    unknown = login(client, username="nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert COOKIE_NAME not in wrong.cookies and COOKIE_NAME not in unknown.cookies


def test_disabled_user_cannot_log_in_and_loses_open_sessions():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    login(client)
    assert client.get("/api/me").status_code == 200
    auth.set_disabled("ada", True)
    assert client.get("/api/me").status_code == 401
    fresh = make_client(auth)
    r = login(fresh)
    assert r.status_code == 401
    assert r.json() == login(fresh, password="wrong one!").json()  # same answer as a bad password
    auth.set_disabled("ada", False)
    assert login(make_client(auth)).status_code == 200


def test_expired_session_is_rejected():
    auth, _, clock = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    login(client)
    clock.advance(days=6, hours=23)
    assert client.get("/api/me").status_code == 200
    clock.advance(hours=2)
    assert client.get("/api/me").status_code == 401


def test_expiry_works_with_naive_datetimes_from_mongo():
    """pymongo returns naive UTC datetimes unless tz_aware=True; expiry must still compare correctly."""
    auth, db, clock = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    user = db["users"].find_one({"username": "ada"})
    token = auth.create_session(user["_id"])
    db["auth_sessions"].update_one({}, {"$set": {"expires_at": (clock.now - timedelta(seconds=1)).replace(tzinfo=None)}})
    assert auth.user_for_token(token) is None


def test_logout_deletes_the_session():
    auth, db, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    login(client)
    token = client.cookies.get(COOKIE_NAME)
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert db["auth_sessions"].count_documents({}) == 0
    assert auth.user_for_token(token) is None
    assert make_client(auth).post("/api/auth/logout").status_code == 200  # logging out twice is harmless


def test_change_password_checks_the_current_one():
    auth, db, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    login(client)
    bad = client.post("/api/me/password", json={"current_password": "nope nope", "new_password": "a new long one"})
    assert bad.status_code == 400
    short = client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 422
    ok = client.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "a new long one"})
    assert ok.status_code == 200
    assert client.get("/api/me").status_code == 200  # the session that changed it stays logged in
    assert login(make_client(auth)).status_code == 401
    assert login(make_client(auth), password="a new long one").status_code == 200
    assert "a new long one" not in str(db["users"].find_one())


def test_change_password_signs_out_other_sessions():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    laptop, phone = make_client(auth), make_client(auth)
    login(laptop)
    login(phone)
    laptop.post("/api/me/password", json={"current_password": PASSWORD, "new_password": "a new long one"})
    assert laptop.get("/api/me").status_code == 200
    assert phone.get("/api/me").status_code == 401


def test_change_password_needs_a_session():
    auth, _, _ = make_auth()
    r = make_client(auth).post("/api/me/password", json={"current_password": "x", "new_password": "a new long one"})
    assert r.status_code == 401


# --- rate limit --------------------------------------------------------------------------------------------


def test_rate_limit_per_username_blocks_even_the_right_password():
    auth, _, clock = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    for _ in range(5):
        assert login(client, password="wrong password").status_code == 401
    assert login(client).status_code == 429
    clock.advance(minutes=10, seconds=1)
    assert login(client).status_code == 200


def test_rate_limit_per_ip_across_usernames():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    client = make_client(auth)
    for i in range(5):
        assert login(client, username=f"guess{i}").status_code == 401
    assert login(client).status_code == 429


def test_success_resets_the_username_counter():
    auth, _, _ = make_auth()
    auth.create_user("ada", "Ada", PASSWORD)
    for _ in range(4):
        login(make_client(auth), password="wrong password")
    assert login(make_client(auth)).status_code == 200
    limiter = auth.limiter
    assert not limiter.blocked("user:ada")


def test_limiter_window_slides():
    clock = Clock()
    limiter = LoginRateLimiter(max_failures=2, window=timedelta(minutes=10), clock=clock)
    limiter.record_failure("k")
    clock.advance(minutes=6)
    limiter.record_failure("k")
    assert limiter.blocked("k")
    clock.advance(minutes=5)  # the first failure has left the window
    assert not limiter.blocked("k")


# --- scripts/create_user.py --------------------------------------------------------------------------------


def load_cli():
    spec = importlib.util.spec_from_file_location("create_user", ROOT / "scripts" / "create_user.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_never_takes_a_password_argument():
    cli = load_cli()
    parser = cli.build_parser()
    options = {opt for action in parser._actions for opt in action.option_strings}
    sub = next(a for a in parser._actions if a.choices)
    for p in sub.choices.values():
        options |= {opt for action in p._actions for opt in action.option_strings}
        options |= {action.dest for action in p._actions}
    assert not any("pass" in o.lower() for o in options)
    with pytest.raises(SystemExit):
        parser.parse_args(["create", "ada", "--password", "x"])


def test_cli_create_disable_enable_reset_and_list(monkeypatch, capsys):
    cli = load_cli()
    auth, db, _ = make_auth()
    answers = iter([PASSWORD, PASSWORD, "a new long one", "a new long one"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))

    assert cli.main(["create", "ada", "--name", "Ada L.", "--role", "admin"], auth=auth) == 0
    assert db["users"].find_one({"username": "ada"})["role"] == "admin"
    assert cli.main(["disable", "ada"], auth=auth) == 0
    assert db["users"].find_one({"username": "ada"})["disabled"] is True
    assert cli.main(["enable", "ada"], auth=auth) == 0
    assert cli.main(["reset-password", "ada"], auth=auth) == 0
    assert auth.authenticate("ada", "a new long one") is not None
    capsys.readouterr()
    assert cli.main(["list"], auth=auth) == 0
    out = capsys.readouterr().out
    assert "ada" in out and "admin" in out and "$argon2" not in out


def test_cli_rejects_mismatched_passwords(monkeypatch):
    cli = load_cli()
    auth, db, _ = make_auth()
    answers = iter([PASSWORD, "something else"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create", "ada"], auth=auth) != 0
    assert db["users"].count_documents({}) == 0


def test_cli_unknown_user_is_an_error(monkeypatch):
    cli = load_cli()
    auth, _, _ = make_auth()
    assert cli.main(["disable", "ghost"], auth=auth) != 0
