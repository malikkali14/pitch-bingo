from typing import Any

import pytest
from factories import load_events, load_meta

from app.stats.engine import StatsEngine
from app.stats.significance import Context, match_minute, route, significance


def event(type_: str, **fields: Any) -> dict[str, Any]:
    base = {"type": type_, "team_id": "NBA", "player_id": "NBA-09", "x": 52.5, "y": 34.0,
            "tags": []}
    return base | fields


# Default context: early in the match with a two-goal gap, so no bonus applies.
QUIET = {"minute": 10, "goal_gap": 2}

TABLE: list[tuple[str, dict[str, Any], dict[str, Any], int]] = [
    ("goal", event("goal"), {}, 80),
    ("low xG shot", event("shot", ball_speed_kmh=70.0), {"xg": 0.1}, 40),
    ("big chance capped at 70", event("shot", ball_speed_kmh=70.0), {"xg": 0.5}, 70),
    ("shot at 100 km/h", event("shot", ball_speed_kmh=105.0), {"xg": 0.05}, 45),
    ("advantage", event("advantage"), {}, 45),
    ("offside on a through ball", event("offside"), {"after_through_ball": True}, 40),
    ("other offside", event("offside"), {}, 0),
    ("pass of 40 m", event("pass", length_m=42.0), {}, 35),
    ("pass of 39 m", event("pass", length_m=39.0), {}, 0),
    ("tenth pass of a move", event("pass", length_m=12.0), {"passes_in_possession": 10}, 40),
    ("ninth pass of a move", event("pass", length_m=12.0), {"passes_in_possession": 9}, 0),
    ("eleventh pass of a move", event("pass", length_m=12.0), {"passes_in_possession": 11},
     0),
    ("card", event("card", card="yellow"), {}, 35),
    ("keeper outside the box", event("pass", length_m=20.0, x=30.0), {"keeper": True}, 50),
    ("keeper in the box", event("pass", length_m=20.0, x=10.0), {"keeper": True}, 0),
    ("keeper outside the box, second half", event("pass", length_m=20.0, x=75.0),
     {"keeper": True, "attacks_right": False}, 50),
    ("foul in the final third", event("foul", x=20.0), {}, 25),
    ("foul in midfield", event("foul", x=60.0), {}, 0),
    ("planted moment", event("shot", ball_speed_kmh=70.0), {"xg": 0.05, "planted": True}, 90),
    ("pattern trigger", event("pass", length_m=8.0), {"pattern_trigger": True}, 50),
    ("milestone", event("save"), {"milestone": True}, 45),
    ("plain carry", event("carry"), {}, 0),
]


@pytest.mark.parametrize("name, ev, ctx, expected", TABLE, ids=[row[0] for row in TABLE])
def test_base_scores(name: str, ev: dict, ctx: dict, expected: int) -> None:
    assert significance(ev, Context(**(QUIET | ctx))) == expected


@pytest.mark.parametrize("minute, gap, expected", [
    (80, 2, 90), (80, 1, 100), (10, 0, 90), (10, 1, 90), (74, 3, 80), (75, 3, 90),
])
def test_bonuses_after_75_and_close_score(minute: int, gap: int, expected: int) -> None:
    assert significance(event("goal"), Context(minute=minute, goal_gap=gap)) == expected


def test_bonuses_need_a_base_score_and_cap_at_100() -> None:
    assert significance(event("carry"), Context(minute=85, goal_gap=0)) == 0
    assert significance(event("goal"), Context(minute=85, goal_gap=0, planted=True)) == 100


@pytest.mark.parametrize("clock, minute", [
    ("00:04", 0), ("23:15", 23), ("45+2:10", 45), ("75:00", 75), ("90+5:51", 90),
])
def test_match_minute(clock: str, minute: int) -> None:
    assert match_minute(clock) == minute


@pytest.mark.parametrize("score, fits, expected", [
    (65, True, "live_candidate"), (60, True, "live_candidate"), (65, False, "narrator"),
    (59, True, "narrator"), (40, False, "narrator"), (39, False, "template"),
    (0, False, "template"),
])
def test_routing_thresholds(score: int, fits: bool, expected: str) -> None:
    assert route(score, live_template_fits=fits) == expected


def test_demo_match_scores() -> None:
    stats = StatsEngine(load_meta(2610))
    scores = {}
    events = load_events(2610)
    for ev in events:
        scores[ev["event_id"]] = stats.on_event(ev).significance
    assert all(0 <= s <= 100 for s in scores.values())
    goals = [e for e in events if e["type"] == "goal"]
    assert all(scores[g["event_id"]] >= 80 for g in goals)
    # One anchor event per planted moment scores 90 or more.
    planted = {}
    for e in events:
        moment = next((t for t in e["tags"] if t.startswith("moment:")), None)
        if moment and scores[e["event_id"]] >= 90:
            planted.setdefault(moment, []).append(e["type"])
    assert len(planted) == 5
    assert all(len(types) == 1 and types[0] in ("shot", "offside")
               for types in planted.values())
    narrated = sum(1 for s in scores.values() if s >= 40)
    assert 20 <= narrated <= 300
