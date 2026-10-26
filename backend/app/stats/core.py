"""Running club and player stats from events (spec 7.1), updated one event at a time.

Ball-in-play time is rebuilt from the event log: play stops at a goal, the ball going out, an
offside, a foul without advantage or the end of a period, and restarts at a kickoff or a set
piece. A keeper holding the ball after a save is dead time too. This matches the generator's
own in-play clock exactly, so possession (share of in-play time on the ball) agrees with
summary.json.
"""

from typing import Any

from app.stats import pitch
from app.stats.xg import attacks_right, shot_offsets, shot_xg

STOPS = {"goal", "out_of_play", "offside", "period_end"}
RESTARTS = {"kickoff", "throw_in", "corner", "goal_kick", "free_kick"}
TOUCHES = {"pass", "carry", "shot", "clearance", "interception", "block", "save"}
ON_TARGET = {"goal", "saved"}
ASSISTED_PASSES = {"through_ball", "cutback"}
REGAIN_CAUSES = {"tackle", "interception"}
HIGH_REGAIN_M = 40.0

CLUB_COUNTERS = ("shots", "shots_on_target", "passes", "passes_completed", "corners", "fouls",
                 "yellow_cards", "red_cards", "offsides", "tackles_won", "interceptions",
                 "duels_won")
PLAYER_COUNTERS = ("touches", "passes", "passes_completed", "shots", "tackles", "duels_won")


def pct(part: float, whole: float, digits: int = 1) -> float | None:
    return round(100 * part / whole, digits) if whole else None


class RunningStats:
    """Score, possession, ball-in-play time and the per-club and per-player counts."""

    def __init__(self, meta: dict[str, Any]) -> None:
        self.home: str = meta["home_team_id"]
        self.away: str = meta["away_team_id"]
        self.roster = {p["id"]: (team["id"], p) for team in meta["teams"]
                       for p in team["players"]}
        self.score = {self.home: 0, self.away: 0}
        self.clubs: dict[str, dict[str, Any]] = {
            team: {**dict.fromkeys(CLUB_COUNTERS, 0), "xg": 0.0}
            for team in (self.home, self.away)}
        self.players: dict[str, dict[str, Any]] = {}
        self.owner: str | None = None   # club on the ball
        self.period = 1
        self.live = False
        self.holding = False            # keeper holding the ball after a save
        self.last_t = 0.0
        self.restart_t = 0.0            # when play last restarted
        self.in_play_s = 0.0
        self.on_ball_s = {self.home: 0.0, self.away: 0.0}
        self.in_play_dt = 0.0           # in-play seconds credited by the latest event
        self.last_xg: float | None = None
        self.last_pass: dict[str, Any] | None = None
        self.passes_in_possession: dict[int, int] = {}
        self._last_pass_type: dict[int, str] = {}

    # ---- helpers ---------------------------------------------------------------------

    def other(self, team: str) -> str:
        return self.away if team == self.home else self.home

    def attacks_right(self, team: str, period: int | None = None) -> bool:
        return attacks_right(team, period or self.period, self.home)

    def team_of(self, player_id: str) -> str | None:
        entry = self.roster.get(player_id)
        return entry[0] if entry else None

    def position_of(self, player_id: str | None) -> str | None:
        entry = self.roster.get(player_id or "")
        return str(entry[1]["position"]) if entry else None

    def player(self, player_id: str) -> dict[str, Any]:
        stats = self.players.get(player_id)
        if stats is None:
            stats = {"team_id": self.team_of(player_id), **dict.fromkeys(PLAYER_COUNTERS, 0),
                     "xg": 0.0}
            self.players[player_id] = stats
        return stats

    def is_high_regain(self, event: dict[str, Any]) -> bool:
        if event["type"] != "possession_change" or event["cause"] not in REGAIN_CAUSES:
            return False
        right = self.attacks_right(event["to_team_id"], event["period"])
        return pitch.to_goal(event["x"], event["y"], right) <= HIGH_REGAIN_M

    # ---- the update ------------------------------------------------------------------

    def update(self, event: dict[str, Any]) -> None:
        t, kind = event["t"], event["type"]
        self.period = event["period"]
        self._advance_time(t, kind)
        team = event["team_id"]
        player = event["player_id"]
        self.last_xg = None

        if kind in STOPS or (kind == "foul" and not event["advantage"]):
            self.live = False
        elif kind in RESTARTS:
            self.live = True
            self.restart_t = t
        if kind == "kickoff":
            self.owner = team
        elif kind == "possession_change":
            self.owner = event["to_team_id"]
            self.holding = event["cause"] == "keeper"

        if player and kind in TOUCHES:
            self.player(player)["touches"] += 1
        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(event, team, player)

    def _advance_time(self, t: float, kind: str) -> None:
        dt = max(0.0, t - self.last_t)
        self.in_play_dt = 0.0
        if self.live and not self.holding and kind not in RESTARTS:
            self.in_play_dt = dt
            self.in_play_s += dt
            if self.owner is not None:
                self.on_ball_s[self.owner] += dt
        self.holding = False
        self.last_t = t

    def _on_pass(self, event: dict[str, Any], team: str, player: str) -> None:
        completed = event["outcome"] == "complete"
        club, stats = self.clubs[team], self.player(player)
        club["passes"] += 1
        stats["passes"] += 1
        if completed:
            club["passes_completed"] += 1
            stats["passes_completed"] += 1
        pid = event["possession_id"]
        self.passes_in_possession[pid] = self.passes_in_possession.get(pid, 0) + 1
        self._last_pass_type[pid] = event["pass_type"]
        self.last_pass = event

    def _on_shot(self, event: dict[str, Any], team: str, player: str) -> None:
        assisted = self._last_pass_type.get(event["possession_id"]) in ASSISTED_PASSES
        dx, dy = shot_offsets(event["x"], event["y"], self.attacks_right(team, event["period"]))
        xg = shot_xg(dx, dy, header=event["shot_type"] == "header", assisted_chance=assisted,
                     pressure=event["under_pressure"], shot_type=event["shot_type"])
        self.last_xg = xg
        club, stats = self.clubs[team], self.player(player)
        club["shots"] += 1
        club["xg"] += xg
        stats["shots"] += 1
        stats["xg"] += xg
        if event["outcome"] in ON_TARGET:
            club["shots_on_target"] += 1

    def _on_goal(self, event: dict[str, Any], team: str, player: str | None) -> None:
        self.score[team] += 1

    def _on_corner(self, event: dict[str, Any], team: str, player: str | None) -> None:
        self.clubs[team]["corners"] += 1

    def _on_foul(self, event: dict[str, Any], team: str, player: str | None) -> None:
        self.clubs[team]["fouls"] += 1

    def _on_card(self, event: dict[str, Any], team: str, player: str | None) -> None:
        key = "yellow_cards" if event["card"] == "yellow" else "red_cards"
        self.clubs[team][key] += 1

    def _on_offside(self, event: dict[str, Any], team: str, player: str | None) -> None:
        self.clubs[team]["offsides"] += 1

    def _on_tackle(self, event: dict[str, Any], team: str, player: str) -> None:
        self.player(player)["tackles"] += 1
        if event["outcome"] == "won":
            self.clubs[team]["tackles_won"] += 1

    def _on_interception(self, event: dict[str, Any], team: str, player: str | None) -> None:
        self.clubs[team]["interceptions"] += 1

    def _on_duel(self, event: dict[str, Any], team: str, player: str) -> None:
        # The outcome is from player_id's side; a lost duel is won by the opponent.
        winner = player if event["outcome"] == "won" else event["opponent_id"]
        winner_team = team if event["outcome"] == "won" else self.other(team)
        self.clubs[winner_team]["duels_won"] += 1
        self.player(winner)["duels_won"] += 1

    # ---- output ----------------------------------------------------------------------

    def club_snapshot(self) -> dict[str, dict[str, Any]]:
        total = sum(self.on_ball_s.values())
        out = {}
        for team, club in self.clubs.items():
            share = pct(self.on_ball_s[team], total, 2)
            out[team] = {
                "possession": 50.0 if share is None else share,
                **club,
                "xg": round(club["xg"], 3),
                "pass_accuracy": pct(club["passes_completed"], club["passes"]),
            }
        return out
