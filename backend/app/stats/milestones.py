"""Milestones from season history and live stats (spec 7.9)."""

from typing import Any

from app.stats.core import ON_TARGET, RunningStats

ROUND_GOALS = (10, 25, 50)
DROUGHT_S = 30 * 60          # "first shot on target in N minutes" needs at least 30
PASS_MILESTONE = 50
PASS_ACCURACY = 0.9
SAVES_MILESTONE = 5
DISTANCE_MILESTONE_KM = 10


def milestone(kind: str, t: float, value: Any, *, player_id: str | None = None,
              team_id: str | None = None, event_id: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "t": t, "value": value, "player_id": player_id, "team_id": team_id,
            "event_id": event_id}


class Milestones:
    def __init__(self, meta: dict[str, Any]) -> None:
        self.season = {p["id"]: p["season"] for team in meta["teams"] for p in team["players"]}
        self.starters = [pid for team in meta["teams"] for pid in team["lineup"]]
        self._kicked_off = False
        self._goals: dict[str, int] = {}
        self._saves: dict[str, int] = {}
        self._last_on_target: dict[str, float] = {}
        self._passes_done: set[str] = set()

    def on_event(self, event: dict[str, Any], core: RunningStats) -> list[dict[str, Any]]:
        t, kind, eid = event["t"], event["type"], event["event_id"]
        found: list[dict[str, Any]] = []
        if kind in ("period_start", "kickoff") and not self._kicked_off:
            self._kicked_off = True
            self._last_on_target = {core.home: t, core.away: t}
            found += [self._hundredth(pid, t, eid) for pid in self.starters
                      if self.season[pid]["appearances"] == 99]
        elif kind == "substitution" and self.season[event["player_on_id"]]["appearances"] == 99:
            found.append(self._hundredth(event["player_on_id"], t, eid))
        elif kind == "goal" and not event["own_goal"]:
            scorer = event["scorer_id"]
            self._goals[scorer] = self._goals.get(scorer, 0) + 1
            total = self.season[scorer]["goals"] + self._goals[scorer]
            if total == 1:
                found.append(milestone("goal_first_season", t, 1, player_id=scorer,
                                       team_id=event["team_id"], event_id=eid))
            elif total in ROUND_GOALS:
                found.append(milestone("goal_round", t, total, player_id=scorer,
                                       team_id=event["team_id"], event_id=eid))
        elif kind == "shot" and event["outcome"] in ON_TARGET:
            team = event["team_id"]
            waited = t - self._last_on_target.get(team, 0.0)
            self._last_on_target[team] = t
            if waited >= DROUGHT_S:
                found.append(milestone("on_target_drought", t, int(waited // 60),
                                       team_id=team, event_id=eid))
        elif kind == "pass" and event["player_id"] not in self._passes_done:
            stats = core.players[event["player_id"]]
            if stats["passes"] >= PASS_MILESTONE and \
                    stats["passes_completed"] >= PASS_ACCURACY * stats["passes"]:
                self._passes_done.add(event["player_id"])
                found.append(milestone("passes_50", t, stats["passes"],
                                       player_id=event["player_id"], team_id=event["team_id"],
                                       event_id=eid))
        elif kind == "save":
            keeper = event["keeper_id"]
            self._saves[keeper] = self._saves.get(keeper, 0) + 1
            if self._saves[keeper] == SAVES_MILESTONE:
                found.append(milestone("saves_5", t, SAVES_MILESTONE, player_id=keeper,
                                       team_id=event["team_id"], event_id=eid))
        return found

    def _hundredth(self, pid: str, t: float, eid: str) -> dict[str, Any]:
        return milestone("appearance_100", t, 100, player_id=pid, event_id=eid)

    @staticmethod
    def on_badge(badge: dict[str, Any], team_id: str | None) -> dict[str, Any] | None:
        if badge["kind"] == "distance" and badge["km"] == DISTANCE_MILESTONE_KM:
            return milestone("distance_10km", badge["t"], DISTANCE_MILESTONE_KM,
                             player_id=badge["player_id"], team_id=team_id)
        return None
