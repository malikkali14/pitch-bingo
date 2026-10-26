"""Speed and distance from tracking frames (spec 7.8)."""

import math
from collections import deque
from typing import Any, Protocol

SPRINT_KMH = 25.2
SPRINT_S = 1.0
SPEED_BADGE_KMH = 32.0
SPEED_BADGE_GAP_S = 300.0
DISTANCE_BADGES_KM = (5, 10)


class FrameLike(Protocol):
    @property
    def t(self) -> float: ...
    @property
    def index(self) -> int: ...
    @property
    def players(self) -> list[tuple[str, float, float]]: ...


class SpeedTracker:
    """Per-player distance, top speed, sprints, and speed and distance badges."""

    def __init__(self, hz: int = 10) -> None:
        self.hz = hz
        self.window = hz // 2           # speed is averaged over 0.5 s
        self.sprint_frames = round(SPRINT_S * hz)
        self._last_index: int | None = None
        self._history: dict[str, deque[tuple[float, float]]] = {}
        self._distance_m: dict[str, float] = {}
        self._top_kmh: dict[str, float] = {}
        self._sprints: dict[str, int] = {}
        self._run: dict[str, int] = {}
        self._speed_badge_t: dict[str, float] = {}
        self._distance_badges: dict[str, int] = {}

    def players(self) -> list[str]:
        return list(self._distance_m)

    def player(self, player_id: str) -> dict[str, Any]:
        return {
            "distance_km": round(self._distance_m.get(player_id, 0.0) / 1000, 3),
            "top_speed_kmh": round(self._top_kmh.get(player_id, 0.0), 1),
            "sprints": self._sprints.get(player_id, 0),
        }

    def on_frame(self, frame: FrameLike) -> list[dict[str, Any]]:
        if self._last_index is None or frame.index != self._last_index + 1:
            self._history.clear()       # not contiguous: no speed across the gap
            self._run.clear()
        self._last_index = frame.index
        badges: list[dict[str, Any]] = []
        for pid, x, y in frame.players:
            history = self._history.get(pid)
            if history is None:
                history = self._history[pid] = deque(maxlen=self.window + 1)
                self._distance_m.setdefault(pid, 0.0)
            elif history:
                lx, ly = history[-1]
                self._distance_m[pid] += math.hypot(x - lx, y - ly)
            history.append((x, y))
            speed = None
            if len(history) > self.window:
                fx, fy = history[0]
                speed = math.hypot(x - fx, y - fy) * self.hz / self.window * 3.6
            self._update_speed(pid, speed, frame.t, badges)
            self._check_distance(pid, frame.t, badges)
        return badges

    def _update_speed(self, pid: str, speed: float | None, t: float,
                      badges: list[dict[str, Any]]) -> None:
        if speed is None:
            self._run[pid] = 0
            return
        if speed > self._top_kmh.get(pid, 0.0):
            self._top_kmh[pid] = speed
        if speed >= SPRINT_KMH:
            self._run[pid] = self._run.get(pid, 0) + 1
            if self._run[pid] == self.sprint_frames:
                self._sprints[pid] = self._sprints.get(pid, 0) + 1
        else:
            self._run[pid] = 0
        if speed >= SPEED_BADGE_KMH:
            last = self._speed_badge_t.get(pid)
            if last is None or t - last >= SPEED_BADGE_GAP_S:
                self._speed_badge_t[pid] = t
                badges.append({"kind": "speed", "player_id": pid, "t": t,
                               "speed_kmh": round(speed, 1)})

    def _check_distance(self, pid: str, t: float, badges: list[dict[str, Any]]) -> None:
        given = self._distance_badges.get(pid, 0)
        if given < len(DISTANCE_BADGES_KM):
            km = DISTANCE_BADGES_KM[given]
            if self._distance_m[pid] >= km * 1000:
                self._distance_badges[pid] = given + 1
                badges.append({"kind": "distance", "player_id": pid, "t": t, "km": km})
