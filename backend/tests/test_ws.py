import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def collect(ws: Any, seconds: float) -> list[dict[str, Any]]:
    """Receive messages for about `seconds` of wall time (frames arrive 10 times a second)."""
    messages = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        msg = ws.receive_json()
        msg["_received"] = time.monotonic()
        messages.append(msg)
    return messages


def of(messages: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    return [m for m in messages if m["type"] == type_]


@pytest.fixture
def client() -> Any:
    with TestClient(app) as c:
        yield c


def start(client: TestClient, seed: int = 2610) -> str:
    response = client.post("/api/sessions", json={"seed": seed, "profile": {"mode": "normal"}})
    assert response.status_code == 200
    return str(response.json()["session_id"])


def test_unknown_seed_is_404(client: TestClient) -> None:
    assert client.post("/api/sessions", json={"seed": 1}).status_code == 404


def test_unknown_session_is_refused(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as info:
        with client.websocket_connect("/ws/sessions/nope") as ws:
            ws.receive_json()
    assert info.value.code == 4404


def test_session_ready_comes_first(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ready = ws.receive_json()
    assert ready["type"] == "session.ready"
    assert ready["session_id"] == sid
    assert ready["match"]["match_id"] == "syn-2610"
    assert ready["profile"] == {"mode": "normal"}
    assert ready["card"] is None
    assert ready["speed"] == 1
    assert {"t", "wall"} <= ready.keys()


@pytest.mark.parametrize("speed", [1, 5, 10])
def test_frames_events_and_stats_at_each_speed(client: TestClient, speed: int) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        assert ws.receive_json()["type"] == "session.ready"
        ws.send_json({"type": "replay.speed", "speed": speed})
        messages = collect(ws, 2.0)

    for msg in messages:
        assert isinstance(msg["t"], float | int) and isinstance(msg["wall"], int)
    frames, events, stats = of(messages, "frame"), of(messages, "event"), of(messages, "stats")
    assert frames and events and stats

    # About 10 frames per wall second, whatever the speed.
    assert 12 <= len(frames) <= 26
    frame = frames[-1]
    assert len(frame["ball"]) == 3
    assert len(frame["players"]) == 22
    assert all(len(p) == 3 and isinstance(p[0], str) for p in frame["players"])

    # Match time runs at the chosen speed (measured after the speed change lands).
    late = [f for f in frames if f["_received"] - frames[0]["_received"] > 0.5]
    rate = (late[-1]["t"] - late[0]["t"]) / (late[-1]["_received"] - late[0]["_received"])
    assert rate == pytest.approx(speed, rel=0.35)

    # Events arrive in order with none skipped.
    seqs = [m["event"]["seq"] for m in events]
    assert seqs == list(range(1, len(seqs) + 1))
    assert all(0 <= m["significance"] <= 100 for m in events)

    snap = stats[-1]
    assert set(snap["clubs"]) == {"NBA", "KVL"}
    assert {"chaos", "pressure", "rhythm", "momentum"} <= snap["patterns"].keys()
    assert snap["players"]


def test_dev_pause_freezes_and_jump_moves(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.send_json({"type": "dev.jump", "t": 1200})
        jumped = collect(ws, 0.6)
        ws.send_json({"type": "dev.pause", "on": True})
        collect(ws, 0.3)
        paused = collect(ws, 1.3)
        ws.send_json({"type": "dev.jump", "t": 100})
        ws.send_json({"type": "dev.pause", "on": False})
        rewound = collect(ws, 0.6)

    assert of(jumped, "frame")[-1]["t"] >= 1200
    jumped_stats = of(jumped, "stats")[-1]
    assert sum(c["passes"] for c in jumped_stats["clubs"].values()) > 150
    # Events jumped over are not replayed to the pitch (kickoff ones went out before the jump).
    assert not [m for m in of(jumped, "event") if 5 < m["event"]["t"] < 1195]
    assert [m for m in of(jumped, "event") if m["event"]["t"] >= 1195]

    assert not of(paused, "frame")
    assert len({m["t"] for m in of(paused, "stats")}) == 1   # heartbeat only

    rewound_stats = of(rewound, "stats")[-1]
    assert 100 <= rewound_stats["t"] < 200
    assert sum(c["passes"] for c in rewound_stats["clubs"].values()) < 100


def test_bad_messages_are_ignored(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        ws.receive_json()
        ws.send_json({"type": "replay.speed", "speed": 3})
        ws.send_json({"type": "no.such.thing"})
        ws.send_text("not json")
        messages = collect(ws, 0.6)
    frames = of(messages, "frame")
    assert frames and frames[-1]["t"] < 2
