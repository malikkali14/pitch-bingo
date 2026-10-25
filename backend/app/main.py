"""FastAPI app: API routes now, WebSocket and game routes in later phases."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Pitch Bingo")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# The Dockerfile copies the built frontend here (spec 11.6).
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
