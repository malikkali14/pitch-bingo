"""Agents in a live session, with a fake client (spec 8.8, 9.4)."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_ws_game import until

from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.main import app
from app.session import sessions

LINE = json.dumps({"moment_id": "m", "headline_facts": ["A big moment in this match."],
                   "why_facts": [], "tags": [], "evidence_ids": [], "numbers": {}})


@pytest.fixture
def fake() -> Iterator[FakeChatClient]:
    client = FakeChatClient([LINE])
    sessions.clients = lambda: ChatClients(client, client, "fake", "fake")
    try:
        yield client
    finally:
        sessions.clients = lambda: None


def play_to(ws: Any, t: float) -> None:
    until(ws, lambda m: m["type"] == "leaderboard")
    ws.send_json({"type": "replay.speed", "speed": 10})
    ws.send_json({"type": "dev.jump", "t": t})


def test_ai_lines_replace_template_lines(fake: FakeChatClient) -> None:
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"seed": 2610}).json()["session_id"]
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            play_to(ws, 618)                          # just before the planted shot at 10:25
            replace = until(ws, lambda m: m["type"] == "feed.replace", 10)[-1]
    assert replace["text"] == "A big moment in this match." and replace["ai"] is True
    assert replace["entry_id"].startswith("e") and {"clock", "held", "t", "wall"} <= replace.keys()
    assert fake.calls


def test_without_foundry_the_template_stands() -> None:
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"seed": 2610}).json()["session_id"]
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            play_to(ws, 618)
            messages = until(ws, lambda m: m["type"] == "event" and m["t"] > 640, 10)
    assert not [m for m in messages if m["type"] == "feed.replace"]
