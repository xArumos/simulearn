"""The SimuLearn product server: the JSON API for the educator app, plus the built frontend.

    python -m src.product.server [--config configs/demo.yaml] [--host 127.0.0.1] [--port 8000] [--device auto|cpu|cuda]

One process loads the child model once (src/demo/engine.py: the base model from the config plus one LoRA
adapter per age), mounts the account routes (src/product/auth.py) and, when `frontend/dist` exists, serves the
built frontend with a fallback to index.html for client-side routes. Every /api route except login needs a
logged-in user (401 otherwise); a user only ever sees their own sessions (404 for anyone else's).

API (types: frontend/src/api.ts):
- GET   /api/config                 ages + labels, practice scenarios (configs/scenarios.yaml), saving on/off
- GET   /api/model-info             base model, adapter run per age, decoding settings, device (all from the config)
- POST  /api/sessions               {age, scenario_id?, compare} -> {id, age, scenario_id, compare}
- POST  /api/sessions/{id}/turns    {adult_line} -> the child's reply {turn, text, rendered, pause_s, secs}
- POST  /api/sessions/{id}/turns/{n}/untrained   the untrained model's reply to turn n (409 when compare is off)
- PATCH /api/sessions/{id}          {compare}: switch the untrained side on or off mid-session

The server keeps no conversation state: each request reads the session's turns back from the store
(src/product/sessions.py) and trims the context exactly like training (`build_messages`, `context_turns` from
the config). The untrained side has its own history, which starts at the turn compare was (last) switched on.
Scenarios only set the scene for the educator; the model's system prompt is always the training one.
Generation runs in FastAPI's threadpool; the engine's lock keeps one generation on the GPU at a time.

Environment (also read from the repo's git-ignored .env, see .env.example):
- MONGODB_URI / MONGODB_DATABASE: required, because accounts live in MongoDB.
- SIMULEARN_SAVE_CHATS=0: keep practice conversations in memory only (gone on restart). Default: saved.
- SIMULEARN_COOKIE_SECURE=0: send the login cookie over plain http, for testing on http://127.0.0.1 only.
  Leave it unset behind the https tunnel.

Behind the cloudflared tunnel every request comes from 127.0.0.1, so the login rate limit takes the client IP
from Cloudflare's CF-Connecting-IP header (trusted only from 127.0.0.1, see auth.py); uvicorn's own proxy-header
rewriting is switched off so the peer address stays the real socket peer.
"""
from __future__ import annotations

import argparse
import os
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.demo.engine import SILENCE_RE, render, system_prompt
from src.product.auth import Auth, current_user
from src.product.auth import router as auth_router
from src.product.sessions import MemorySessions, MongoSessions, history
from src.utils.config import PROJECT_ROOT, load_config, resolve

DEFAULT_CONFIG = "configs/demo.yaml"
DEFAULT_SCENARIOS = "configs/scenarios.yaml"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
MAX_LINE = 2000


# --- request / response shapes (mirrors frontend/src/api.ts) -------------------------------------------------


class SessionIn(BaseModel):
    age: int
    scenario_id: Optional[str] = None
    compare: bool = False


class SessionCreated(BaseModel):
    id: str
    age: int
    scenario_id: Optional[str]
    compare: bool


class SessionState(SessionCreated):
    compare_started_turn: Optional[int]


class TurnIn(BaseModel):
    adult_line: str = Field(min_length=1, max_length=MAX_LINE)


class CompareIn(BaseModel):
    compare: bool


class TurnReply(BaseModel):
    turn: int
    text: str
    rendered: str
    pause_s: Optional[int]
    secs: float


def load_scenarios(path: str | Path) -> list[dict]:
    """[{id, title, scene, opening_line}] from configs/scenarios.yaml."""
    keys = ("id", "title", "scene", "opening_line")
    scenarios = (load_config(path) or {}).get("scenarios") or []
    for s in scenarios:
        missing = [k for k in keys if not s.get(k)]
        if missing:
            raise ValueError(f"scenario {s.get('id')!r} in {path} is missing {missing}")
    if len({s["id"] for s in scenarios}) != len(scenarios):
        raise ValueError(f"duplicate scenario ids in {path}")
    return [{k: str(s[k]) for k in keys} for s in scenarios]


def reply_fields(turn: int, text: str, secs: float) -> TurnReply:
    """A leading <SILENCE FOR X SECONDS> (the child pauses before answering) becomes pause_s = X."""
    m = SILENCE_RE.match(text.strip())
    return TurnReply(turn=turn, text=text, rendered=render(text), pause_s=int(m.group(1)) if m else None,
                     secs=round(secs, 2))


# --- the app ------------------------------------------------------------------------------------------------


def create_app(engine: Any, auth: Auth, store: MongoSessions | MemorySessions, scenarios: list[dict],
               frontend_dist: Optional[Path] = None) -> FastAPI:
    """`engine` is a src.demo.engine.Demo (or a fake with the same .cfg, .adapters, .device, .seed and
    .reply(history, adult_line, age, system))."""
    app = FastAPI(title="SimuLearn", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.auth = auth
    app.include_router(auth_router)
    cfg = engine.cfg
    scenario_ids = {s["id"] for s in scenarios}
    locks: defaultdict[tuple[str, str], threading.Lock] = defaultdict(threading.Lock)
    locks_guard = threading.Lock()

    def side_lock(session_id: str, side: str) -> threading.Lock:
        """Turns of one session and side are numbered in order, so two requests for it can't run at once."""
        with locks_guard:
            return locks[(session_id, side)]

    def owner(user: dict) -> str:
        return str(user["_id"])

    def get_session(session_id: str, user: dict) -> dict:
        s = store.get(session_id, owner(user))
        if s is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
        return s

    def generate(hist: list[dict], adult_line: str, age: Optional[int], system: str) -> tuple[str, float, int]:
        engine.seed += 1
        seed = engine.seed
        t0 = time.time()
        text = engine.reply(hist, adult_line, age, system)
        return text, time.time() - t0, seed

    def meta(session: dict, side: str, turn: int, seed: int, secs: float) -> dict:
        return {"session": session["_id"], "side": side, "turn": turn, "age": session["age"],
                "scenario_id": session["scenario_id"], "seed": seed, "gen_seconds": round(secs, 2),
                "device": engine.device}

    api = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

    @api.get("/config")
    def config() -> dict:
        ages = sorted(engine.adapters)
        return {
            "ages": ages,
            "age_labels": {str(a): engine.adapters[a].get("label", "") for a in ages},
            "default_age": cfg.get("default_age") if cfg.get("default_age") in ages else (ages[0] if ages else None),
            "scenarios": scenarios,
            "saving": store.saving,
            "compare_default": False,
        }

    @api.get("/model-info")
    def model_info() -> dict:
        return {
            "base_model": cfg["base_model"],
            "adapters": {str(a): Path(e["path"]).parent.name for a, e in sorted(engine.adapters.items())},
            "decoding": dict(cfg.get("decoding") or {}),
            "context_turns": cfg["context_turns"],
            "load_in_4bit": bool(cfg.get("load_in_4bit")),
            "device": engine.device,
        }

    @api.post("/sessions", response_model=SessionCreated)
    def start_session(body: SessionIn, user: dict = Depends(current_user)):
        if body.age not in engine.adapters:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No model for age {body.age}")
        if body.scenario_id is not None and body.scenario_id not in scenario_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown scenario {body.scenario_id!r}")
        s = store.create(owner(user), body.age, body.scenario_id, body.compare)
        return SessionCreated(id=s["_id"], age=s["age"], scenario_id=s["scenario_id"], compare=s["compare"])

    @api.patch("/sessions/{session_id}", response_model=SessionState)
    def set_compare(session_id: str, body: CompareIn, user: dict = Depends(current_user)):
        with side_lock(session_id, "child"):  # so "next turn" can't move while we read it
            s = get_session(session_id, user)
            if body.compare and not s["compare"]:
                next_turn = len(store.turns(s, "child")) + 1
                s = store.update(s, compare=True, compare_started_turn=next_turn)
            elif not body.compare and s["compare"]:
                s = store.update(s, compare=False)
        return SessionState(id=s["_id"], age=s["age"], scenario_id=s["scenario_id"], compare=s["compare"],
                            compare_started_turn=s["compare_started_turn"])

    @api.post("/sessions/{session_id}/turns", response_model=TurnReply)
    def child_turn(session_id: str, body: TurnIn, user: dict = Depends(current_user)):
        adult_line = body.adult_line.strip()
        if not adult_line:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "adult_line is empty")
        with side_lock(session_id, "child"):
            s = get_session(session_id, user)
            past = store.turns(s, "child")
            turn = len(past) + 1
            age = s["age"]
            text, secs, seed = generate(history(past), adult_line, age, system_prompt(age))
            adapter_run = Path(engine.adapters[age]["path"]).parent.name
            store.append(s, "child", {"turn": turn, "adult": adult_line, "text": text, "secs": round(secs, 2),
                                      "seed": seed},
                         model=f"age{age}:{adapter_run}", metadata=meta(s, "child", turn, seed, secs))
        return reply_fields(turn, text, secs)

    @api.post("/sessions/{session_id}/turns/{turn}/untrained", response_model=TurnReply)
    def untrained_turn(session_id: str, turn: int, user: dict = Depends(current_user)):
        with side_lock(session_id, "untrained"):
            s = get_session(session_id, user)
            if not s["compare"]:
                raise HTTPException(status.HTTP_409_CONFLICT, "Compare is off for this session")
            child = {t["turn"]: t for t in store.turns(s, "child")}
            if turn not in child:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Turn {turn} not found")
            since = s["compare_started_turn"]
            if turn < since:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Compare was off at turn {turn}")
            done = store.turns(s, "untrained")
            for t in done:  # already answered (e.g. a retried request): same reply, no second generation
                if t["turn"] == turn and t["turn"] >= since:
                    return reply_fields(turn, t["text"], t.get("secs") or 0.0)
            adult_line, age = child[turn]["adult"], s["age"]
            text, secs, seed = generate(history(done, since=since, before=turn), adult_line, None, system_prompt(age))
            store.append(s, "untrained", {"turn": turn, "adult": adult_line, "text": text, "secs": round(secs, 2),
                                          "seed": seed},
                         model=cfg["base_model"], metadata=meta(s, "untrained", turn, seed, secs))
        return reply_fields(turn, text, secs)

    app.include_router(api)

    if frontend_dist is not None and (Path(frontend_dist) / "index.html").is_file():
        dist = Path(frontend_dist).resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path == "api" or path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and target.is_relative_to(dist):
                return FileResponse(target)
            return FileResponse(dist / "index.html")  # client-side routes (/practice, /account, ...)

    return app


# --- CLI ----------------------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="SimuLearn product server (API + built frontend)")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = this machine only (the tunnel connects here)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto", help="auto = cuda if available")
    return ap.parse_args(argv)


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value not in ("0", "false", "no", "off")


def connect_mongo() -> Any:
    """The product needs MongoDB for accounts, so it refuses to start without it (the demo can run without)."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise SystemExit("MONGODB_URI is empty. Accounts live in MongoDB: set it in the repo's .env "
                         "(template: .env.example; local MongoDB: docker-compose.yml).")
    from pymongo import MongoClient

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as e:
        raise SystemExit(f"Can't reach MongoDB ({type(e).__name__}). Is it running? See docker-compose.yml.") from None
    return client[os.getenv("MONGODB_DATABASE", "simulearn")]


def main(argv: list[str] | None = None) -> None:
    from backend.app.env import load_env_file

    a = parse_args(argv)
    load_env_file()
    cfg = load_config(resolve(a.config))
    scenarios = load_scenarios(resolve(DEFAULT_SCENARIOS))
    db = connect_mongo()
    saving = env_flag("SIMULEARN_SAVE_CHATS", True)
    store = MongoSessions(db) if saving else MemorySessions()
    auth = Auth(db, cookie_secure=env_flag("SIMULEARN_COOKIE_SECURE", True))

    from src.demo.engine import Demo, find_adapters, pick_device

    adapters = find_adapters(cfg)
    device = pick_device(a.device)
    print(f"SimuLearn: {cfg['base_model']} with ages {sorted(adapters)} on {device}", flush=True)
    engine = Demo(cfg, adapters, device=device)
    app = create_app(engine, auth, store, scenarios, frontend_dist=FRONTEND_DIST)
    print(f"SimuLearn: saving {'on' if saving else 'OFF (SIMULEARN_SAVE_CHATS=0)'}; frontend "
          f"{'served from frontend/dist' if (FRONTEND_DIST / 'index.html').is_file() else 'not built (API only)'}; "
          f"http://{a.host}:{a.port}", flush=True)
    import uvicorn

    # proxy_headers=False: request.client stays the socket peer, so auth.py can tell tunnel traffic (127.0.0.1)
    # and read CF-Connecting-IP from it only.
    uvicorn.run(app, host=a.host, port=a.port, proxy_headers=False, log_level="info")


if __name__ == "__main__":
    main()
