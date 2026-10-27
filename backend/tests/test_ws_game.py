"""The game over the API (spec 9.3 to 9.6, 12.1): session.ready, answer.submit,
square.result, board.move, masks, the leaderboard and the HTTP endpoints."""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_ws import of, start

from app.main import app


@pytest.fixture
def client() -> Any:
    with TestClient(app) as c:
        yield c


def until(ws: Any, test: Any, seconds: float = 5.0) -> list[dict[str, Any]]:
    """Receive until a message passes `test`, or fail after `seconds` of wall time."""
    messages = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        msg = ws.receive_json()
        messages.append(msg)
        if test(msg):
            return messages
    raise AssertionError(f"timed out; got {sorted({m['type'] for m in messages})}")


def opening(ws: Any) -> list[dict[str, Any]]:
    return until(ws, lambda m: m["type"] == "leaderboard")


def test_ready_carries_the_card_without_answers(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        messages = opening(ws)
    ready = messages[0]
    card = ready["card"]
    assert ready["type"] == "session.ready" and len(card["squares"]) == 25
    assert sum(s["state"] == "empty_blank" for s in card["squares"]) == 5
    assert all("correct_answer" not in s for s in card["squares"])
    masks = of(messages, "mask.on")
    assert {"fouls", "cards", "shots"} <= {tag for m in masks for tag in m["tags"]}
    board = of(messages, "leaderboard")[0]
    assert board["mode"] == "normal" and any(r["you"] for r in board["rows"])


def test_bad_profile_is_422(client: TestClient) -> None:
    response = client.post("/api/sessions", json={"seed": 2610, "profile": {"club": "XXX"}})
    assert response.status_code == 422


def test_board_move_round_trip(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        card = opening(ws)[0]["card"]
        target = next(s for s in card["squares"] if s["kind"] == "deadline")
        ws.send_json({"type": "board.move", "from_cell": {"row": 0, "col": 0},
                      "to_cell": target["cell"]})
        update = until(ws, lambda m: m["type"] in ("board.update", "error"))[-1]
    assert update["type"] == "board.update"
    moved = {s["id"]: s["cell"] for s in update["squares"]}
    assert moved[target["id"]] == {"row": 0, "col": 0}
    assert moved["bl_1"] == target["cell"]


def test_bad_move_gets_an_error(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        opening(ws)
        ws.send_json({"type": "board.move", "from_cell": [1, 1], "to_cell": [0, 0]})
        error = until(ws, lambda m: m["type"] == "error")[-1]
    assert error["request"] == "board.move"


def test_first_to_happen_answer_before_the_event_is_too_early(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        card = opening(ws)[0]["card"]
        goal = next(s for s in card["squares"] if s["trigger"] == {"type": "goal"})
        ws.send_json({"type": "answer.submit", "square_id": goal["id"], "value": "NBA"})
        result = until(ws, lambda m: m["type"] == "square.result")[-1]
    assert result == {**result, "square_id": goal["id"], "status": "too_early", "points": 0,
                      "correct_answer": None}


def test_deadline_window_answer_and_result(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        card = opening(ws)[0]["card"]
        square = next(s for s in card["squares"] if s["deadline_s"] == 900)
        ws.send_json({"type": "replay.speed", "speed": 10})
        ws.send_json({"type": "dev.jump", "t": 890})
        opened = until(ws, lambda m: m["type"] == "square.window_open", 10)[-1]
        assert opened["square_id"] == square["id"] and opened["closes_at"] > opened["wall"]
        ws.send_json({"type": "answer.submit", "square_id": square["id"],
                      "value": square["options"][0]})
        result = until(ws, lambda m: m["type"] == "square.result" and
                       m["square_id"] == square["id"])[-1]
        assert result["status"] in ("correct", "wrong")
        assert result["correct_answer"] in square["options"]
        assert (result["points"] > 0) == (result["status"] == "correct")
        board = until(ws, lambda m: m["type"] == "board.update")[-1]
        mine = next(s for s in board["squares"] if s["id"] == square["id"])
        assert mine["state"] == result["status"] and mine["answer"]["value"] == \
            square["options"][0]
        ws.send_json({"type": "answer.submit", "square_id": square["id"], "value": "0"})
        assert until(ws, lambda m: m["type"] == "error")[-1]["request"] == "answer.submit"


def test_stats_hide_masked_values_and_events_say_held(client: TestClient) -> None:
    sid = start(client)
    with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
        opening(ws)
        ws.send_json({"type": "replay.speed", "speed": 10})
        messages = until(ws, lambda m: m["type"] == "event" and m["event"]["type"] == "foul",
                         15)
        stats = of(messages, "stats")[-1]
    club = next(iter(stats["clubs"].values()))
    assert club["fouls"] is None and "fouls" in stats["masked"]
    assert all("held" in m for m in of(messages, "event"))
    assert messages[-1]["held"] is True                 # the first foul opens a silent window


def test_http_endpoints(client: TestClient) -> None:
    assert 2610 in client.get("/api/matches").json()["seeds"]
    sid = start(client)
    state = client.get(f"/api/sessions/{sid}/state").json()
    assert state["session_id"] == sid and len(state["board"]["squares"]) == 25
    assert state["live_squares_to_come"] == 5
    assert client.get("/api/sessions/nope/state").status_code == 404
    rows = client.get("/api/leaderboard", params={"mode": "normal"}).json()["rows"]
    assert any(r["handle"] == "You" for r in rows)
    assert client.get("/api/leaderboard", params={"mode": "expert"}).status_code == 422
