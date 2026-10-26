"""The stats engine (spec 7): running stats, patterns, milestones and significance.

Feed it every event and every tracking frame in time order. Each call does a bounded amount of
work, so the engine keeps up at any replay speed; snapshot() is what the stats message sends.
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.stats.core import RunningStats
from app.stats.milestones import Milestones
from app.stats.patterns import Chaos, Momentum, Pressure, Rhythm
from app.stats.significance import Context, match_minute, significance
from app.stats.speed import FrameLike, SpeedTracker

CALIBRATION_PATH = Path(__file__).with_name("calibration.json")
RECENT = 10
PLANTED_ANCHORS = {"shot", "offside"}


def load_calibration(path: Path = CALIBRATION_PATH) -> dict[str, Any]:
    return dict(json.loads(path.read_text()))


@dataclass
class EventResult:
    significance: int
    triggers: list[dict[str, Any]] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FrameResult:
    badges: list[dict[str, Any]] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)


class StatsEngine:
    def __init__(self, meta: dict[str, Any], calibration: dict[str, Any] | None = None,
                 hz: int = 10) -> None:
        calibration = calibration or load_calibration()
        self.core = RunningStats(meta)
        self.speed = SpeedTracker(hz)
        self.chaos = Chaos(calibration["chaos"])
        self.pressure = Pressure((self.core.home, self.core.away))
        self.rhythm = Rhythm(calibration["tempo_terciles"])
        self.momentum = Momentum(self.core.home, self.core.away)
        self.milestones = Milestones(meta)
        self.t = 0.0
        self.recent: dict[str, deque[dict[str, Any]]] = {
            key: deque(maxlen=RECENT) for key in ("triggers", "milestones", "badges")}
        self._moments_seen: set[str] = set()

    def on_event(self, event: dict[str, Any]) -> EventResult:
        self.t = event["t"]
        core = self.core
        core.update(event)
        triggers = []
        for pattern in (self.chaos, self.pressure, self.rhythm, self.momentum):
            triggers += pattern.update(event, core)
        found = self.milestones.on_event(event, core)
        score = significance(event, self._context(event, bool(triggers), bool(found)))
        self.recent["triggers"].extend(triggers)
        self.recent["milestones"].extend(found)
        return EventResult(score, triggers, found)

    def on_frame(self, frame: FrameLike) -> FrameResult:
        self.t = frame.t
        badges = self.speed.on_frame(frame)
        found = []
        for badge in badges:
            reached = Milestones.on_badge(badge, self.core.team_of(badge["player_id"]))
            if reached is not None:
                found.append(reached)
        self.recent["badges"].extend(badges)
        self.recent["milestones"].extend(found)
        return FrameResult(badges, found)

    def _context(self, event: dict[str, Any], triggered: bool, milestone: bool) -> Context:
        core = self.core
        team = event["team_id"]
        home, away = core.score[core.home], core.score[core.away]
        last_pass = core.last_pass
        return Context(
            minute=match_minute(event["clock"]),
            goal_gap=abs(home - away),
            attacks_right=core.attacks_right(team, event["period"]) if team else True,
            xg=core.last_xg,
            after_through_ball=(event["type"] == "offside" and last_pass is not None
                                and last_pass["pass_type"] == "through_ball"
                                and last_pass["outcome"] == "offside"),
            passes_in_possession=core.passes_in_possession.get(event["possession_id"], 0)
            if event["type"] == "pass" else 0,
            planted=self._planted_anchor(event),
            keeper=core.position_of(event["player_id"]) == "GK",
            pattern_trigger=triggered,
            milestone=milestone,
        )

    def _planted_anchor(self, event: dict[str, Any]) -> bool:
        """The first shot or offside of each planted moment carries the moment's score."""
        if "planted" not in event["tags"] or event["type"] not in PLANTED_ANCHORS:
            return False
        key = " ".join(sorted(tag for tag in event["tags"]
                              if tag.startswith(("moment:", "segment:"))))
        if key in self._moments_seen:
            return False
        self._moments_seen.add(key)
        return True

    def snapshot(self) -> dict[str, Any]:
        core = self.core
        players = {}
        for pid in {*core.players, *self.speed.players()}:
            stats = dict(core.players.get(pid) or core.player(pid))
            stats["xg"] = round(stats["xg"], 3)
            players[pid] = stats | self.speed.player(pid)
        return {
            "score": dict(core.score),
            "ball_in_play_s": round(core.in_play_s, 2),
            "clubs": core.club_snapshot(),
            "players": players,
            "patterns": {
                "chaos": self.chaos.snapshot(),
                "pressure": self.pressure.snapshot(),
                "rhythm": self.rhythm.snapshot(),
                "momentum": self.momentum.snapshot(),
            },
            "recent": {key: list(items) for key, items in self.recent.items()},
        }
