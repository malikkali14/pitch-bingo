"""Helpers for hand-built event logs in stats tests."""

import json
from pathlib import Path
from typing import Any

MATCHES = Path(__file__).resolve().parents[2] / "data" / "matches"
SEEDS = (2610, 1107, 4242, 9001)
HOME, AWAY = "NBA", "KVL"


def load_meta(seed: int = 2610) -> dict[str, Any]:
    return json.loads((MATCHES / str(seed) / "match.json").read_text())


def load_events(seed: int = 2610) -> list[dict[str, Any]]:
    with (MATCHES / str(seed) / "events.jsonl").open() as f:
        return [json.loads(line) for line in f]


def load_summary(seed: int = 2610) -> dict[str, Any]:
    return json.loads((MATCHES / str(seed) / "summary.json").read_text())


class Log:
    """Builds events with seq, event_id and possession_id filled in, like the generator."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.possession_id = 0

    def add(self, type_: str, t: float, team: str | None = HOME, player: str | None = None,
            x: float = 52.5, y: float = 34.0, period: int = 1, tags: tuple[str, ...] = (),
            under_pressure: bool = False, clock: str | None = None,
            **extra: Any) -> dict[str, Any]:
        if type_ == "possession_change":
            self.possession_id += 1
        seq = len(self.events) + 1
        minute, second = divmod(int(t), 60)
        event = {
            "event_id": f"e{seq:06d}", "seq": seq, "t": t, "period": period,
            "clock": clock or f"{minute:02d}:{second:02d}", "type": type_, "team_id": team,
            "player_id": player, "x": x, "y": y, "possession_id": self.possession_id,
            "under_pressure": under_pressure, "tags": list(tags), **extra,
        }
        self.events.append(event)
        return event

    def pass_(self, t: float, team: str = HOME, player: str = "NBA-08", *,
              outcome: str = "complete", x: float = 52.5, y: float = 34.0,
              end_x: float = 60.0, end_y: float = 34.0, length_m: float = 10.0,
              pass_type: str = "open_play", **extra: Any) -> dict[str, Any]:
        return self.add("pass", t, team, player, x=x, y=y, receiver_id=None, end_x=end_x,
                        end_y=end_y, length_m=length_m, height="ground", pass_type=pass_type,
                        outcome=outcome, ball_speed_kmh=50.0, opponents_bypassed=0, **extra)

    def change(self, t: float, to: str, cause: str = "tackle", x: float = 52.5,
               y: float = 34.0, player: str | None = None) -> dict[str, Any]:
        other = AWAY if to == HOME else HOME
        return self.add("possession_change", t, to, player, x=x, y=y, from_team_id=other,
                        to_team_id=to, cause=cause)
