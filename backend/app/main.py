"""FastAPI app: API routes, the session WebSocket and the built frontend."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app import telemetry
from app.config import settings
from app.engine.source import MATCHES_DIR, available_seeds, load_match
from app.models import CreateSession, SessionCreated
from app.session import sessions


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telemetry.setup()
    yield
    sessions.close_all()


app = FastAPI(title="Pitch Bingo", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions")
async def create_session(body: CreateSession) -> SessionCreated:
    seed = settings.default_seed if body.seed is None else body.seed
    try:
        session = sessions.create(seed, body.profile)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"no match for seed {seed}") from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return SessionCreated(session_id=session.id)


@app.get("/api/matches")
async def matches() -> dict[str, Any]:
    return {"seeds": available_seeds(), "default": settings.default_seed}


@app.get("/api/matches/{seed}")
async def match_metadata(seed: int) -> dict[str, Any]:
    """Clubs and players for the setup screen, before a session exists."""
    try:
        return load_match(MATCHES_DIR / str(seed)).meta
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"no match for seed {seed}") from None


@app.get("/api/sessions/{session_id}/state")
async def session_state(session_id: str) -> dict[str, Any]:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="no such session")
    return session.state()


@app.get("/api/leaderboard")
async def leaderboard(mode: Literal["normal", "advanced"] = "normal") -> dict[str, Any]:
    return {"mode": mode, "rows": sessions.leaderboard(mode)}


@app.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    session = sessions.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = session.attach()

    async def pump() -> None:
        while True:
            await websocket.send_json(await queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data: Any = json.loads(text)
            except ValueError:
                continue
            session.command(data)
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        session.detach(queue)


# The Dockerfile copies the built frontend here (spec 11.6).
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
