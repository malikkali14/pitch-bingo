"""FastAPI app: API routes, the session WebSocket and the built frontend."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import CreateSession, SessionCreated
from app.session import sessions


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    return SessionCreated(session_id=session.id)


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
