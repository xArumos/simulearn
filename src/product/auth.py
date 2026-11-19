"""Invite-only user accounts and cookie login for the SimuLearn product.

There is no sign-up route: an admin creates accounts with `scripts/create_user.py` (outside educators need
Dr. Dever's OK first).

Storage (MongoDB):
- `users`: username (unique, lower-case), display_name, password_hash (argon2id), role ("admin" | "educator"),
  disabled, created_at. Plain passwords are never stored.
- `auth_sessions`: token_hash (sha256 of the random cookie token), user_id, created_at, expires_at. A TTL index
  on expires_at lets MongoDB delete old rows; expiry is also checked on every request, because the TTL sweep
  runs only about once a minute.

HTTP (an APIRouter the product server mounts with `app.include_router(router)`; it reads `app.state.auth`, an
`Auth` instance the server creates at startup):
- POST /api/auth/login {username, password} -> sets the session cookie, returns {username, display_name, role}
- POST /api/auth/logout -> deletes the session and the cookie
- GET  /api/me -> {username, display_name, role}
- POST /api/me/password {current_password, new_password} -> changes the password, signs out other sessions
- `current_user`: a dependency that returns the logged-in user's document or answers 401.

Failed logins are rate-limited in memory, per client IP and per username (5 failures in 10 minutes by default).
The limit lives in one process, so it resets on restart. Behind a proxy or tunnel every request can share one
IP; the per-username limit still holds, and the server should pass the real client IP through if it matters.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

COOKIE_NAME = "simulearn_session"
SESSION_TTL = timedelta(days=7)
ROLES = ("admin", "educator")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 1024  # hashing is deliberately slow; don't let a request make it hash megabytes
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
LOGIN_FAILED = "Invalid username or password"
TOO_MANY = "Too many failed attempts. Try again in a few minutes."

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def _aware(dt: datetime) -> datetime:
    """pymongo hands back naive UTC datetimes unless the client was made with tz_aware=True."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _check_password(password: str) -> None:
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise ValueError(f"password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")


class LoginRateLimiter:
    """Counts failures per key ("ip:..." or "user:...") in a sliding window. In memory, one process."""

    def __init__(self, max_failures: int = 5, window: timedelta = timedelta(minutes=10), clock: Clock = utcnow):
        self.max_failures = max_failures
        self.window = window
        self.clock = clock
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str) -> deque:
        q = self._failures[key]
        cutoff = self.clock() - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            del self._failures[key]
        return q

    def blocked(self, *keys: str) -> bool:
        with self._lock:
            return any(len(self._prune(k)) >= self.max_failures for k in keys)

    def record_failure(self, *keys: str) -> None:
        with self._lock:
            now = self.clock()
            for k in keys:
                self._prune(k)
                self._failures[k].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


class Auth:
    """Accounts and sessions on a MongoDB database (a pymongo or mongomock Database)."""

    def __init__(self, database: Any, *, clock: Clock = utcnow, limiter: Optional[LoginRateLimiter] = None,
                 hasher: Optional[PasswordHasher] = None, session_ttl: timedelta = SESSION_TTL,
                 cookie_secure: bool = True):
        self.users = database["users"]
        self.sessions = database["auth_sessions"]
        self.users.create_index("username", unique=True)
        self.sessions.create_index("token_hash", unique=True)
        self.sessions.create_index("user_id")
        self.sessions.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
        self.clock = clock
        self.limiter = limiter or LoginRateLimiter(clock=clock)
        self.hasher = hasher or PasswordHasher()
        self.session_ttl = session_ttl
        self.cookie_secure = cookie_secure  # only for local http testing; keep True anywhere real
        self._dummy_hash: Optional[str] = None

    # --- accounts ---

    def create_user(self, username: str, display_name: str, password: str, role: str = "educator") -> dict:
        username = normalize_username(username)
        if not USERNAME_RE.match(username):
            raise ValueError("username must be 2-64 characters: a-z, 0-9, '.', '_' or '-'")
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        _check_password(password)
        doc = {
            "username": username,
            "display_name": display_name.strip() or username,
            "password_hash": self.hasher.hash(password),
            "role": role,
            "disabled": False,
            "created_at": self.clock(),
        }
        try:
            doc["_id"] = self.users.insert_one(doc).inserted_id
        except DuplicateKeyError:
            raise ValueError(f"user {username!r} already exists") from None
        return doc

    def get_user(self, username: str) -> Optional[dict]:
        return self.users.find_one({"username": normalize_username(username)})

    def list_users(self) -> list[dict]:
        return list(self.users.find({}, {"password_hash": 0}).sort("username", ASCENDING))

    def set_disabled(self, username: str, disabled: bool) -> bool:
        user = self.get_user(username)
        if user is None:
            return False
        self.users.update_one({"_id": user["_id"]}, {"$set": {"disabled": disabled}})
        if disabled:
            self.sessions.delete_many({"user_id": user["_id"]})
        return True

    def set_password(self, username: str, password: str, keep_token_hash: Optional[str] = None) -> bool:
        """Set a new password and sign out every session except `keep_token_hash` (the one that changed it)."""
        _check_password(password)
        user = self.get_user(username)
        if user is None:
            return False
        self.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": self.hasher.hash(password)}})
        self.sessions.delete_many({"user_id": user["_id"], "token_hash": {"$ne": keep_token_hash}})
        return True

    def _verify(self, user: Optional[dict], password: str) -> bool:
        if user is None:
            # Hash anyway so an unknown username takes as long as a wrong password.
            if self._dummy_hash is None:
                self._dummy_hash = self.hasher.hash(secrets.token_urlsafe(16))
            try:
                self.hasher.verify(self._dummy_hash, password)
            except VerificationError:
                pass
            return False
        try:
            self.hasher.verify(user["password_hash"], password)
        except (VerificationError, InvalidHashError):
            return False
        if self.hasher.check_needs_rehash(user["password_hash"]):
            self.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": self.hasher.hash(password)}})
        return True

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """The user if the password is right and the account is enabled, else None (no reason given)."""
        user = self.get_user(username)
        ok = self._verify(user, password)
        if not ok or user is None or user.get("disabled"):
            return None
        return user

    # --- sessions ---

    def create_session(self, user_id: Any) -> str:
        """Store a new session and return its raw token (for the cookie only; the database keeps its hash)."""
        token = secrets.token_urlsafe(32)
        now = self.clock()
        self.sessions.insert_one({
            "token_hash": hash_token(token),
            "user_id": user_id,
            "created_at": now,
            "expires_at": now + self.session_ttl,
        })
        return token

    def user_for_token(self, token: Optional[str]) -> Optional[dict]:
        if not token:
            return None
        session = self.sessions.find_one({"token_hash": hash_token(token)})
        if session is None:
            return None
        if _aware(session["expires_at"]) <= self.clock():
            self.sessions.delete_one({"_id": session["_id"]})
            return None
        user = self.users.find_one({"_id": session["user_id"]})
        if user is None or user.get("disabled"):
            return None
        return user

    def delete_session(self, token: Optional[str]) -> None:
        if token:
            self.sessions.delete_one({"token_hash": hash_token(token)})


# --- HTTP ---------------------------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    username: str
    display_name: str
    role: Literal["admin", "educator"]


def _public(user: dict) -> UserResponse:
    return UserResponse(username=user["username"], display_name=user["display_name"], role=user["role"])


def get_auth(request: Request) -> Auth:
    return request.app.state.auth


def current_user(request: Request, auth: Auth = Depends(get_auth)) -> dict:
    """FastAPI dependency: the logged-in user's document (no password hash), or 401."""
    user = auth.user_for_token(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    return {k: v for k, v in user.items() if k != "password_hash"}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


router = APIRouter()


@router.post("/api/auth/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, response: Response, auth: Auth = Depends(get_auth)):
    ip_key, user_key = f"ip:{_client_ip(request)}", f"user:{normalize_username(payload.username)}"
    if auth.limiter.blocked(ip_key, user_key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=TOO_MANY)
    user = auth.authenticate(payload.username, payload.password)
    if user is None:
        auth.limiter.record_failure(ip_key, user_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=LOGIN_FAILED)
    auth.limiter.reset(user_key)
    token = auth.create_session(user["_id"])
    response.set_cookie(
        COOKIE_NAME, token, max_age=int(auth.session_ttl.total_seconds()), path="/",
        httponly=True, secure=auth.cookie_secure, samesite="lax",
    )
    return _public(user)


@router.post("/api/auth/logout")
def logout(request: Request, response: Response, auth: Auth = Depends(get_auth)) -> dict:
    auth.delete_session(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=auth.cookie_secure, samesite="lax")
    return {"ok": True}


@router.get("/api/me", response_model=UserResponse)
def me(user: dict = Depends(current_user)):
    return _public(user)


@router.post("/api/me/password")
def change_password(payload: ChangePasswordRequest, request: Request, user: dict = Depends(current_user),
                    auth: Auth = Depends(get_auth)) -> dict:
    user_key = f"user:{user['username']}"
    if auth.limiter.blocked(user_key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=TOO_MANY)
    if auth.authenticate(user["username"], payload.current_password) is None:
        auth.limiter.record_failure(user_key)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is wrong")
    auth.set_password(user["username"], payload.new_password,
                      keep_token_hash=hash_token(request.cookies.get(COOKIE_NAME, "")))
    return {"ok": True}
