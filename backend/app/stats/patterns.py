"""The patterns in spec 7.4 to 7.7: control vs. chaos, pressure, rhythm and momentum.

Each pattern updates on every event in O(1) amortized time using rolling windows of match
time, and returns the narration triggers that event caused. A trigger fires when its condition
becomes true and re-arms once it is false again, so a condition that holds does not repeat.
"""

from collections import deque
from typing import Any

from app.stats import pitch
from app.stats.core import RunningStats

Trigger = dict[str, Any]


def trigger(pattern: str, kind: str, t: float, team_id: str | None = None,
            **extra: Any) -> Trigger:
    return {"pattern": pattern, "kind": kind, "t": t, "team_id": team_id, **extra}


def scale(value: float | None, band: list[float]) -> float:
    """Scale to 0-1 between the 10th and 90th percentile; a missing input sits at 0.5."""
    if value is None:
        return 0.5
    lo, hi = band
    if hi <= lo:
        return 0.5
    return min(1.0, max(0.0, (value - lo) / (hi - lo)))


class Rolling:
    """Sums by key over the last `span` seconds of match time.

    Entries that age out pass to `spill`, so a spill with twice the span holds the window
    before this one.
    """

    def __init__(self, span: float, spill: "Rolling | None" = None) -> None:
        self.span = span
        self.spill = spill
        self._entries: deque[tuple[float, Any, float]] = deque()
        self._sums: dict[Any, float] = {}

    def add(self, t: float, key: Any, value: float = 1.0) -> None:
        self._entries.append((t, key, value))
        self._sums[key] = self._sums.get(key, 0.0) + value

    def advance(self, t: float) -> None:
        while self._entries and self._entries[0][0] < t - self.span:
            entry = self._entries.popleft()
            self._sums[entry[1]] -= entry[2]
            if self.spill is not None:
                self.spill.add(*entry)
        if self.spill is not None:
            self.spill.advance(t)

    def get(self, key: Any) -> float:
        return self._sums.get(key, 0.0)


class Edge:
    """Fires once when a condition becomes true, then waits for it to turn false."""

    def __init__(self, armed: bool = True) -> None:
        self.armed = armed

    def __call__(self, condition: bool) -> bool:
        if condition and self.armed:
            self.armed = False
            return True
        if not condition:
            self.armed = True
        return False


# ---- 7.4 control vs. chaos ---------------------------------------------------------------

class Chaos:
    SPAN = 300.0
    WEIGHTS = {"T": 0.4, "D": 0.25, "C": 0.2, "S": 0.15}
    HIGH, LOW, SWING = 65.0, 35.0, 20.0
    REARM = 50.0          # a high or low fires again only after chaos crosses back past 50

    def __init__(self, bands: dict[str, list[float]]) -> None:
        self.bands = bands
        self.window = Rolling(self.SPAN)
        # possession_id -> [team, last event time, passes, completed passes]
        self.possessions: dict[int, list[Any]] = {}
        self.inputs: dict[str, float | None] = dict.fromkeys("TDCS")
        self.value: float | None = None
        self.in_control: str | None = None
        self.history: deque[tuple[float, float]] = deque()
        self._high: Edge | None = None
        self._low: Edge | None = None
        self._last_swing = -float("inf")

    def update(self, event: dict[str, Any], core: RunningStats) -> list[Trigger]:
        t, kind = event["t"], event["type"]
        if kind == "possession_change":
            self.window.add(t, "changes")
        elif kind == "duel":
            self.window.add(t, "duels")
        elif kind == "pass":
            self.window.add(t, "passes")
            self.window.add(t, "completed", event["outcome"] == "complete")
        record = self.possessions.setdefault(event["possession_id"],
                                             [core.owner, t, 0, 0])
        record[0], record[1] = core.owner, t
        if kind == "pass":
            record[2] += 1
            record[3] += event["outcome"] == "complete"
        self.window.advance(t)
        while self.possessions:
            first = next(iter(self.possessions))
            if self.possessions[first][1] >= t - self.SPAN:
                break
            del self.possessions[first]
        self._compute(t)
        return self._triggers(t)

    def _compute(self, t: float) -> None:
        if t < 60:
            return
        minutes = min(t, self.SPAN) / 60
        passes = self.window.get("passes")
        records = list(self.possessions.values())
        self.inputs = {
            "T": self.window.get("changes") / minutes,
            "D": self.window.get("duels") / minutes,
            "C": self.window.get("completed") / passes if passes else None,
            "S": sum(r[2] >= 5 for r in records) / len(records) if records else None,
        }
        s = {k: scale(v, self.bands[k]) for k, v in self.inputs.items()}
        w = self.WEIGHTS
        self.value = 100 * (w["T"] * s["T"] + w["D"] * s["D"] + w["C"] * (1 - s["C"])
                            + w["S"] * (1 - s["S"]))
        built: dict[str, int] = {}
        for team, _, _, completed in records:
            if completed >= 5 and team is not None:
                built[team] = built.get(team, 0) + 1
        ranked = sorted(built.items(), key=lambda kv: -kv[1])
        tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
        self.in_control = ranked[0][0] if ranked and not tie else None

    def _triggers(self, t: float) -> list[Trigger]:
        value = self.value
        if value is None or t < self.SPAN:
            return []
        out = []
        if self._high is None or self._low is None:
            self._high, self._low = Edge(value < self.HIGH), Edge(value >= self.LOW)
        high_band = self.HIGH if self._high.armed else self.REARM
        if self._high(value >= high_band):
            out.append(trigger("chaos", "chaos_high", t, self.in_control, value=round(value, 1)))
        low_band = self.LOW if self._low.armed else self.REARM
        if self._low(value < low_band):
            out.append(trigger("chaos", "chaos_low", t, self.in_control, value=round(value, 1)))
        while self.history and self.history[0][0] < t - self.SPAN:
            self.history.popleft()
        if self.history and t - self._last_swing >= self.SPAN:
            lo = min(v for _, v in self.history)
            hi = max(v for _, v in self.history)
            if max(value - lo, hi - value) >= self.SWING:
                self._last_swing = t
                start = lo if value - lo >= hi - value else hi
                out.append(trigger("chaos", "chaos_swing", t, self.in_control,
                                   value=round(value, 1), change=round(value - start, 1)))
        self.history.append((t, value))
        return out

    def snapshot(self) -> dict[str, Any]:
        return {
            "value": None if self.value is None else round(self.value, 1),
            "in_control": self.in_control,
            "inputs": {k: None if v is None else round(v, 4) for k, v in self.inputs.items()},
        }


# ---- 7.5 pressure ------------------------------------------------------------------------

class Pressure:
    SPAN = 600.0
    REGAIN_SPAN = 300.0
    OWN_ZONE_M = 0.6 * 105
    PPDA_ACTIONS = {"tackle", "interception", "foul", "duel"}
    DEFENSIVE = PPDA_ACTIONS | {"pressure", "clearance", "block"}
    PPDA_DROP = 0.6       # PPDA at or below 60% of the previous window
    PPDA_MIN_ACTIONS = 5  # fewer defensive actions than this in a window is too noisy
    TILT_SWING = 20.0
    REGAINS = 3

    def __init__(self, teams: tuple[str, str]) -> None:
        self.teams = teams
        self.window = Rolling(self.SPAN, spill=Rolling(2 * self.SPAN))
        self.high_regains = dict.fromkeys(teams, 0)
        self.regain_times: dict[str, deque[float]] = {team: deque() for team in teams}
        self._ppda_drop = {team: Edge() for team in teams}
        self._regains = {team: Edge() for team in teams}
        self._tilt = Edge()

    def update(self, event: dict[str, Any], core: RunningStats) -> list[Trigger]:
        t, kind, team = event["t"], event["type"], event["team_id"]
        period = event["period"]
        if kind == "pass":
            # A pass in the passer's own 60% counts toward the other club's PPDA.
            if pitch.from_own_goal(event["x"], core.attacks_right(team, period)) \
                    <= self.OWN_ZONE_M:
                self.window.add(t, ("opp_passes", core.other(team)))
            if event["outcome"] == "complete" and pitch.in_final_third(
                    event["end_x"], core.attacks_right(team, period)):
                self.window.add(t, ("tilt", team))
        if kind in self.DEFENSIVE:
            # A duel is logged from the ball carrier's side; the defender is the other club.
            presser = core.other(core.owner) if kind == "duel" and core.owner else team
            if presser in self.teams:
                self._defensive_action(event, presser, core)
        if core.is_high_regain(event):
            self.high_regains[team] += 1
            self.regain_times[team].append(t)
        self.window.advance(t)
        for times in self.regain_times.values():
            while times and times[0] < t - self.REGAIN_SPAN:
                times.popleft()
        return self._triggers(t)

    def _defensive_action(self, event: dict[str, Any], presser: str,
                          core: RunningStats) -> None:
        t, period = event["t"], event["period"]
        right = core.attacks_right(presser, period)
        self.window.add(t, ("height_sum", presser), pitch.from_own_goal(event["x"], right))
        self.window.add(t, ("height_n", presser))
        opponent_right = core.attacks_right(core.other(presser), period)
        if event["type"] in self.PPDA_ACTIONS and \
                pitch.from_own_goal(event["x"], opponent_right) <= self.OWN_ZONE_M:
            self.window.add(t, ("actions", presser))

    @staticmethod
    def _ppda(window: Rolling, team: str, min_actions: float = 1) -> float | None:
        actions = window.get(("actions", team))
        return window.get(("opp_passes", team)) / actions if actions >= min_actions else None

    @staticmethod
    def _tilt_share(window: Rolling, team: str, other: str) -> float | None:
        mine, theirs = window.get(("tilt", team)), window.get(("tilt", other))
        return 100 * mine / (mine + theirs) if mine + theirs else None

    def _triggers(self, t: float) -> list[Trigger]:
        out = []
        prev = self.window.spill
        assert prev is not None
        home, away = self.teams
        for team in self.teams:
            if self._regains[team](len(self.regain_times[team]) >= self.REGAINS):
                out.append(trigger("pressure", "high_regains", t, team,
                                   value=len(self.regain_times[team])))
            if t < 2 * self.SPAN:
                continue
            now = self._ppda(self.window, team, self.PPDA_MIN_ACTIONS)
            before = self._ppda(prev, team, self.PPDA_MIN_ACTIONS)
            dropped = now is not None and before is not None and now <= self.PPDA_DROP * before
            if self._ppda_drop[team](dropped):
                out.append(trigger("pressure", "ppda_drop", t, team, value=round(now or 0, 2),
                                   before=round(before or 0, 2)))
        if t >= 2 * self.SPAN:
            now_tilt = self._tilt_share(self.window, home, away)
            before_tilt = self._tilt_share(prev, home, away)
            swing = (now_tilt - before_tilt
                     if now_tilt is not None and before_tilt is not None else 0.0)
            if self._tilt(abs(swing) >= self.TILT_SWING):
                out.append(trigger("pressure", "tilt_swing", t, home if swing > 0 else away,
                                   value=round(now_tilt or 0, 1), change=round(abs(swing), 1)))
        return out

    def snapshot(self) -> dict[str, Any]:
        out = {}
        for team in self.teams:
            other = self.teams[1] if team == self.teams[0] else self.teams[0]
            ppda = self._ppda(self.window, team)
            n = self.window.get(("height_n", team))
            tilt = self._tilt_share(self.window, team, other)
            out[team] = {
                "ppda": None if ppda is None else round(ppda, 2),
                "pressing_height_m": round(self.window.get(("height_sum", team)) / n, 1)
                if n else None,
                "field_tilt": None if tilt is None else round(tilt, 1),
                "high_regains": self.high_regains[team],
                "high_regains_5min": len(self.regain_times[team]),
            }
        return out


# ---- 7.6 rhythm --------------------------------------------------------------------------

class Rhythm:
    SPAN = 600.0
    LABELS = ("Slow", "Steady", "Frantic")
    HOLD_S = 180.0
    LONG_SPELL_S = 240.0

    def __init__(self, terciles: list[float]) -> None:
        self.terciles = terciles
        self.window = Rolling(self.SPAN)
        self.values: dict[str, Any] = {"events_per_min": None, "passes_per_min": None,
                                       "since_stoppage_s": 0.0, "in_play_share": None,
                                       "tempo": None}
        self._announced: str | None = None
        self._candidate: tuple[str, float] | None = None
        self._spell_fired_for: float | None = None

    def label(self, events_per_min: float) -> str:
        lo, hi = self.terciles
        return self.LABELS[0] if events_per_min < lo else \
            self.LABELS[1] if events_per_min < hi else self.LABELS[2]

    def update(self, event: dict[str, Any], core: RunningStats) -> list[Trigger]:
        t = event["t"]
        self.window.add(t, "events")
        self.window.add(t, "in_play", core.in_play_dt)
        if event["type"] == "pass":
            self.window.add(t, "passes")
        self.window.advance(t)
        span = min(t, self.SPAN)
        in_play = self.window.get("in_play")
        epm = self.window.get("events") / (in_play / 60) if in_play >= 1 else None
        self.values = {
            "events_per_min": epm,
            "passes_per_min": self.window.get("passes") / (span / 60) if span else None,
            "since_stoppage_s": t - core.restart_t if core.live else 0.0,
            "in_play_share": 100 * in_play / span if span else None,
            "tempo": self.label(epm) if epm is not None and t >= 60 else None,
        }
        return self._triggers(t, core)

    def _triggers(self, t: float, core: RunningStats) -> list[Trigger]:
        out = []
        if core.live and t - core.restart_t >= self.LONG_SPELL_S \
                and self._spell_fired_for != core.restart_t:
            self._spell_fired_for = core.restart_t
            out.append(trigger("rhythm", "long_spell", t, core.owner,
                               value=round(t - core.restart_t)))
        tempo = self.values["tempo"]
        if t < self.SPAN or tempo is None:
            return out
        if self._announced is None:
            self._announced = tempo
        elif tempo == self._announced:
            self._candidate = None
        elif self._candidate is None or self._candidate[0] != tempo:
            self._candidate = (tempo, t)
        elif t - self._candidate[1] >= self.HOLD_S:
            self._announced, self._candidate = tempo, None
            out.append(trigger("rhythm", "tempo_change", t, value=tempo))
        return out

    def snapshot(self) -> dict[str, Any]:
        v = self.values
        return {
            "events_per_min": None if v["events_per_min"] is None
            else round(v["events_per_min"], 1),
            "passes_per_min": None if v["passes_per_min"] is None
            else round(v["passes_per_min"], 1),
            "since_stoppage_s": round(v["since_stoppage_s"], 1),
            "in_play_share": None if v["in_play_share"] is None else round(v["in_play_share"], 1),
            "tempo": v["tempo"],
        }


# ---- 7.7 momentum ------------------------------------------------------------------------

class Momentum:
    HALF_LIFE_S = 180.0
    SIDE_HOLD_S = 120.0
    DOMINANT = 40.0           # 70% of the threat is +/-40 on the bar
    DOMINANT_HOLD_S = 300.0
    POINTS = {"box_entry": 1.0, "final_third_pass": 0.3, "corner": 1.5, "high_regain": 1.0}

    def __init__(self, home: str, away: str) -> None:
        self.home, self.away = home, away
        self.threat = {home: 0.0, away: 0.0}
        self.value = 0.0
        self._last_t = 0.0
        self._announced: str | None = None
        self._candidate: tuple[str, float] | None = None
        self._dominant: tuple[str | None, float] = (None, 0.0)
        self._dominant_fired = False

    def update(self, event: dict[str, Any], core: RunningStats) -> list[Trigger]:
        t, team = event["t"], event["team_id"]
        decay = 0.5 ** ((t - self._last_t) / self.HALF_LIFE_S)
        for key in self.threat:
            self.threat[key] *= decay
        self._last_t = t
        if team in self.threat:
            self.threat[team] += self._points(event, core)
        total = sum(self.threat.values())
        self.value = 100 * (self.threat[self.home] - self.threat[self.away]) / total \
            if total > 1e-9 else 0.0
        return self._triggers(t)

    def _points(self, event: dict[str, Any], core: RunningStats) -> float:
        kind = event["type"]
        if kind == "shot":
            return 10 * (core.last_xg or 0.0)
        if kind == "corner":
            return self.POINTS["corner"]
        if core.is_high_regain(event):
            return self.POINTS["high_regain"]
        points = 0.0
        if kind in ("pass", "carry"):
            if kind == "pass" and event["outcome"] != "complete":
                return 0.0
            right = core.attacks_right(event["team_id"], event["period"])
            if kind == "pass" and pitch.in_final_third(event["end_x"], right):
                points += self.POINTS["final_third_pass"]
            if pitch.in_box(event["end_x"], event["end_y"], right) \
                    and not pitch.in_box(event["x"], event["y"], right):
                points += self.POINTS["box_entry"]
        return points

    def _triggers(self, t: float) -> list[Trigger]:
        out = []
        side = self.home if self.value > 0 else self.away if self.value < 0 else None
        if side is not None:
            if self._announced is None:
                self._announced = side
            elif side == self._announced:
                self._candidate = None
            elif self._candidate is None or self._candidate[0] != side:
                self._candidate = (side, t)
            elif t - self._candidate[1] >= self.SIDE_HOLD_S:
                self._announced, self._candidate = side, None
                out.append(trigger("momentum", "momentum_side", t, side,
                                   value=round(self.value)))
        dominant = side if abs(self.value) > self.DOMINANT else None
        if dominant != self._dominant[0]:
            self._dominant, self._dominant_fired = (dominant, t), False
        elif dominant is not None and not self._dominant_fired \
                and t - self._dominant[1] >= self.DOMINANT_HOLD_S:
            self._dominant_fired = True
            out.append(trigger("momentum", "momentum_hold", t, dominant,
                               value=round(self.value)))
        return out

    def snapshot(self) -> dict[str, Any]:
        return {"value": round(self.value, 1),
                "threat": {k: round(v, 2) for k, v in self.threat.items()}}
