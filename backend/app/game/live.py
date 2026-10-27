"""Live squares (spec 4.11): exactly five per match, one per segment, answered by code.

The producer watches the event stream and picks five moments. Picking never depends on the
viewer, so every viewer gets the same moments; only the question differs by mode. A moment
becomes a square at a call (a foul, an advantage, an offside, or the ball going out), and the
normal question is about the call while the advanced one is about the move before it.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.stats.core import RunningStats

Event = dict[str, Any]

# Segments in display-clock seconds: 5-20', 20-38', 38-60', 60-75', 75-88'.
SEGMENTS = ((300, 1200), (1200, 2280), (2280, 3600), (3600, 4500), (4500, 5280))
FALLBACK_AT = 0.85
CANDIDATE = 60
LONG_PASS_M = 35.0
MOVE_PASSES = 10
RESTARTS = {"kickoff", "throw_in", "corner", "goal_kick", "free_kick"}

# What each planted scenario (spec 6.7) asks, and the event it becomes a square at.
SCENARIOS = {
    "advantage_then_shot": ("shot", "referee", "shot_xg"),
    "offside_through_ball": ("offside", "referee", "pass_length"),
    "long_range_tip_over": ("out_of_play", "restart", "shot_speed"),
    "thirteen_pass_block": ("out_of_play", "restart", "move_passes"),
    "switch_then_wide": ("out_of_play", "restart", "pass_length"),
}


@dataclass(frozen=True)
class LiveTemplate:
    id: str
    mode: str
    text: str
    options: tuple[str, ...]
    labels: tuple[str, ...]
    masks: tuple[str, ...]
    edges: tuple[float, ...] = ()           # bucket edges for measured values


LIVE_TEMPLATES = {t.id: t for t in [
    LiveTemplate("referee", "normal", "What did the referee just give?",
                 ("foul", "offside", "advantage", "no_call"),
                 ("Foul", "Offside", "Advantage played", "No call"), ("fouls", "offsides")),
    LiveTemplate("restart", "normal", "How does play restart?",
                 ("corner", "goal_kick", "throw_in"), ("Corner", "Goal kick", "Throw-in"),
                 ("corners",)),
    LiveTemplate("throw_team", "normal", "Which team gets the throw-in?", (), (), ()),
    LiveTemplate("shot_xg", "advanced", "Estimate the xG of that shot",
                 ("0-0.05", "0.05-0.15", "0.15-0.35", "0.35+"),
                 ("under 0.05", "0.05–0.15", "0.15–0.35", "over 0.35"), ("shots",),
                 (0.05, 0.15, 0.35)),
    LiveTemplate("pass_length", "advanced", "How long was that pass?",
                 ("0-20", "20-35", "35-50", "50+"),
                 ("under 20 m", "20–35 m", "35–50 m", "over 50 m"), (), (20, 35, 50)),
    LiveTemplate("shot_speed", "advanced", "How fast was that shot?",
                 ("0-70", "70-90", "90-110", "110+"),
                 ("under 70 km/h", "70–90 km/h", "90–110 km/h", "over 110 km/h"), ("shots",),
                 (70, 90, 110)),
    LiveTemplate("move_passes", "advanced", "How many passes in that move?",
                 ("1-3", "4-7", "8-12", "13+"), ("1–3", "4–7", "8–12", "13+"), (),
                 (4, 8, 13)),
]}
ADVANCED_ORDER = ("shot_xg", "pass_length", "shot_speed", "move_passes")


def clock_seconds(clock: str) -> int:
    """Display clock to seconds: "45+2:10" is 2830, "67:30" is 4050."""
    minute, second = clock.split(":")
    base, _, extra = minute.partition("+")
    return (int(base) + int(extra or 0)) * 60 + int(second)


def segment_at(seconds: int) -> int | None:
    return next((i for i, (a, b) in enumerate(SEGMENTS) if a <= seconds < b), None)


def restart_after(event: Event, home: str, away: str) -> tuple[str, str]:
    """How play restarts after the ball goes out, and for which club (Laws 15 to 17).
    Over the end line it is a corner if the defending club touched it last, else a goal kick;
    the event's club is the one that was attacking that end."""
    last = event["last_touch_team_id"]
    attacking = event["team_id"]
    other = {home: away, away: home}
    if event.get("line") != "end":
        return "throw_in", other[last]
    if last == attacking:
        return "goal_kick", other[attacking]
    return "corner", attacking


def bucket(template: LiveTemplate, value: float) -> str:
    index = sum(1 for edge in template.edges if value >= edge)
    return template.options[index]


@dataclass
class Moment:
    segment: int
    call: Event
    phase: list[Event]
    scenario: str | None
    xg: dict[str, float]
    passes: int                          # passes in the move before the call
    fallback: bool = False


@dataclass
class LiveSpec:
    template: str
    text: str
    options: list[str]
    labels: list[str]
    correct: str
    masks: list[str]
    source_event_ids: list[str]


@dataclass
class LiveProducer:
    home: str
    away: str
    planted: frozenset[int] = frozenset()
    needed: set[int] = field(default_factory=lambda: set(range(len(SEGMENTS))))
    phase: list[Event] = field(default_factory=list)
    xg: dict[str, float] = field(default_factory=dict)
    passes: dict[str, int] = field(default_factory=dict)     # pass event id -> count in move
    hot: bool = False
    segment_of: dict[str, int] = field(default_factory=dict)   # square id -> segment

    def on_event(self, event: Event, significance: int, stats: RunningStats) -> Moment | None:
        """Call after the stats have taken the event."""
        kind = event["type"]
        if kind in RESTARTS:
            self.phase, self.hot = [], False
        self.phase.append(event)
        if kind == "shot":
            self.xg[event["event_id"]] = float(stats.last_xg or 0.0)
        elif kind == "pass":
            self.passes[event["event_id"]] = stats.passes_in_possession.get(
                event["possession_id"], 0)

        seconds = clock_seconds(event["clock"])
        overdue = sorted(s for s in self.needed
                         if seconds >= SEGMENTS[s][0] + FALLBACK_AT * (SEGMENTS[s][1] -
                                                                         SEGMENTS[s][0]))
        if overdue and self._is_call(event):
            moment = self._moment(overdue[0], event, None, fallback=True)
            if moment is not None:
                return moment
        segment = segment_at(seconds)
        if segment is None or segment not in self.needed:
            return None
        if segment in self.planted:
            scenario = self._scenario(event, segment)
            if scenario and kind == SCENARIOS[scenario][0]:
                return self._moment(segment, event, scenario)
            return None
        if significance >= CANDIDATE and self._fits(event):
            self.hot = True
        if self.hot and (self._is_call(event) or (kind == "shot" and self._advantage())):
            return self._moment(segment, event, None)
        return None

    @staticmethod
    def _scenario(event: Event, segment: int) -> str | None:
        tags = event["tags"]
        if "planted" not in tags or f"segment:{segment + 1}" not in tags:
            return None
        return next((t.split(":", 1)[1] for t in tags if t.startswith("moment:")), None)

    @staticmethod
    def _is_call(event: Event) -> bool:
        kind = event["type"]
        return kind in ("advantage", "offside", "out_of_play") or (
            kind == "foul" and not event.get("advantage"))

    def _advantage(self) -> Event | None:
        return next((e for e in reversed(self.phase) if e["type"] == "advantage"), None)

    def _fits(self, event: Event) -> bool:
        kind = event["type"]
        return kind in ("shot", "advantage", "offside") or (kind == "pass" and (
            event["length_m"] >= LONG_PASS_M
            or self.passes.get(event["event_id"], 0) >= MOVE_PASSES))

    def _moment(self, segment: int, event: Event, scenario: str | None,
                fallback: bool = False) -> Moment | None:
        call = event
        if event["type"] == "shot":
            advantage = self._advantage()
            if advantage is None:
                return None
            call = advantage
        last_pass = next((e for e in reversed(self.phase) if e["type"] == "pass"), None)
        passes = self.passes.get(last_pass["event_id"], 0) if last_pass else 0
        moment = Moment(segment, call, list(self.phase), scenario, dict(self.xg), passes,
                        fallback)
        # Every viewer gets this moment, so both modes need a question for it.
        if normal_for(moment, Counter()) is None or advanced_for(moment, Counter()) is None:
            return None
        self.needed.discard(segment)
        self.hot = False
        return moment


def normal_for(moment: Moment, used: Counter[str]) -> str | None:
    if moment.scenario:
        return SCENARIOS[moment.scenario][1]
    kind = moment.call["type"]
    if kind in ("foul", "advantage", "offside"):
        return "referee"
    if kind == "out_of_play":
        if moment.call.get("line") != "end":
            return min(("restart", "throw_team"), key=lambda t: used[t])
        return "restart"
    return None


def _shot(moment: Moment) -> Event | None:
    return next((e for e in reversed(moment.phase) if e["type"] == "shot"), None)


def _pass(moment: Moment) -> Event | None:
    passes = [e for e in moment.phase if e["type"] == "pass"]
    if not passes:
        return None
    if moment.call["type"] == "offside":
        offside = [e for e in passes if e["outcome"] == "offside"]
        if offside:
            return offside[-1]
    return max(passes, key=lambda e: e["length_m"])


def advanced_for(moment: Moment, used: Counter[str]) -> str | None:
    if moment.scenario:
        return SCENARIOS[moment.scenario][2]
    fits = []
    if _shot(moment) is not None:
        fits += ["shot_xg", "shot_speed"]
    if _pass(moment) is not None:
        fits.append("pass_length")
    if moment.passes > 0:
        fits.append("move_passes")
    if not fits:
        return None
    return min(fits, key=lambda t: (used[t], ADVANCED_ORDER.index(t)))


def build_live(moment: Moment, mode: str, used: Counter[str], meta: dict[str, Any]) -> LiveSpec:
    """The question for a mode, with its answer computed here, never by a model."""
    home, away = meta["home_team_id"], meta["away_team_id"]
    template_id = normal_for(moment, used) if mode == "normal" else advanced_for(moment, used)
    assert template_id is not None
    template = LIVE_TEMPLATES[template_id]
    call = moment.call
    options, labels = list(template.options), list(template.labels)
    sources = [call["event_id"]]
    if template_id == "referee":
        correct = "foul" if call["type"] == "foul" else call["type"]
    elif template_id in ("restart", "throw_team"):
        kind, team = restart_after(call, home, away)
        if template_id == "restart":
            correct = kind
        else:
            clubs = {t["id"]: t["short_name"] for t in meta["teams"]}
            options, labels, correct = [home, away], [clubs[home], clubs[away]], team
    elif template_id in ("shot_xg", "shot_speed"):
        shot = _shot(moment)
        assert shot is not None
        value = moment.xg.get(shot["event_id"], 0.0) if template_id == "shot_xg" \
            else shot["ball_speed_kmh"]
        correct = bucket(template, value)
        sources.insert(0, shot["event_id"])
    elif template_id == "pass_length":
        pass_ = _pass(moment)
        assert pass_ is not None
        correct = bucket(template, pass_["length_m"])
        sources.insert(0, pass_["event_id"])
    else:
        correct = bucket(template, moment.passes)
        sources = [e["event_id"] for e in moment.phase if e["type"] == "pass"][-20:] + sources
    used[template_id] += 1
    return LiveSpec(template_id, template.text, options, labels, correct,
                    list(template.masks), sources)

