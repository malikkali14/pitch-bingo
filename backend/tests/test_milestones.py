import copy
from typing import Any

import pytest
from factories import AWAY, HOME, Log, load_meta

from app.engine.source import Frame
from app.stats.engine import StatsEngine


def meta_with(player_id: str, **season: int) -> dict[str, Any]:
    meta = copy.deepcopy(load_meta(2610))
    for team in meta["teams"]:
        for player in team["players"]:
            if player["id"] == player_id:
                player["season"].update(season)
    return meta


def milestones(meta: dict[str, Any], events: list[dict]) -> list[dict]:
    stats = StatsEngine(meta)
    found: list[dict] = []
    for event in events:
        found += stats.on_event(event).milestones
    return found


def goal(log: Log, t: float, scorer: str = "NBA-09") -> None:
    shot = log.add("shot", t, HOME, scorer, x=95, y=34, shot_type="open_play",
                   body_part="right_foot", outcome="goal", ball_speed_kmh=80.0, goal_y=34.0,
                   goal_z=1.0)
    log.add("goal", t, HOME, scorer, x=105, y=34, scorer_id=scorer, assist_id=None,
            shot_event_id=shot["event_id"], own_goal=False)


def kinds(found: list[dict]) -> list[str]:
    return [m["kind"] for m in found]


def test_hundredth_appearance_for_a_starter_on_99() -> None:
    starter = load_meta(2610)["teams"][0]["lineup"][3]
    log = Log()
    log.add("period_start", 0, HOME, stoppage_added_s=None)
    log.add("kickoff", 0, HOME, "NBA-09")
    found = milestones(meta_with(starter, appearances=99), log.events)
    assert kinds(found) == ["appearance_100"]
    assert found[0]["player_id"] == starter


def test_no_appearance_milestone_otherwise() -> None:
    starter = load_meta(2610)["teams"][0]["lineup"][3]
    log = Log()
    log.add("period_start", 0, HOME, stoppage_added_s=None)
    log.add("kickoff", 0, HOME, "NBA-09")
    assert milestones(meta_with(starter, appearances=40), log.events) == []


def test_substitute_on_99_reaches_100_when_coming_on() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.add("substitution", 3600, HOME, "NBA-15", player_off_id="NBA-09",
            player_on_id="NBA-15")
    assert kinds(milestones(meta_with("NBA-15", appearances=99), log.events)) == [
        "appearance_100"]


def test_first_goal_of_the_season() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    goal(log, 100)
    goal(log, 200)
    found = milestones(meta_with("NBA-09", goals=0), log.events)
    assert [m["kind"] for m in found if m["kind"].startswith("goal")] == ["goal_first_season"]


@pytest.mark.parametrize("before, expected", [(9, 10), (24, 25), (49, 50)])
def test_round_number_of_goals(before: int, expected: int) -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    goal(log, 100)
    found = [m for m in milestones(meta_with("NBA-09", goals=before), log.events)
             if m["kind"] == "goal_round"]
    assert len(found) == 1 and found[0]["value"] == expected


def test_no_goal_milestone_for_ordinary_totals() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    goal(log, 100)
    assert not [m for m in milestones(meta_with("NBA-09", goals=4), log.events)
                if m["kind"].startswith("goal")]


def test_first_shot_on_target_after_a_long_wait() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t, outcome in [(300, "saved"), (600, "off_target"), (2700, "saved"), (2800, "saved")]:
        log.add("shot", t, HOME, "NBA-09", x=90, y=34, shot_type="open_play",
                body_part="right_foot", outcome=outcome, ball_speed_kmh=80.0, goal_y=34.0,
                goal_z=1.0)
    found = [m for m in milestones(load_meta(2610), log.events)
             if m["kind"] == "on_target_drought"]
    assert len(found) == 1
    assert found[0]["team_id"] == HOME and found[0]["value"] == 40


def test_fifty_passes_at_90_percent() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for i in range(60):
        log.pass_(1 + i, player="NBA-08", outcome="incomplete" if i in (3, 17, 40) else
                  "complete")
    found = [m for m in milestones(load_meta(2610), log.events) if m["kind"] == "passes_50"]
    assert len(found) == 1 and found[0]["player_id"] == "NBA-08"
    assert found[0]["t"] == 50


def test_no_pass_milestone_under_90_percent() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for i in range(60):
        log.pass_(1 + i, player="NBA-08", outcome="incomplete" if i % 5 == 0 else "complete")
    assert not [m for m in milestones(load_meta(2610), log.events)
                if m["kind"] == "passes_50"]


def test_keepers_fifth_save() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for i in range(6):
        log.add("save", 100 + i, AWAY, "KVL-01", keeper_id="KVL-01",
                shot_event_id="e000001")
    found = [m for m in milestones(load_meta(2610), log.events) if m["kind"] == "saves_5"]
    assert len(found) == 1 and found[0]["player_id"] == "KVL-01" and found[0]["t"] == 104


def test_ten_kilometres_is_a_milestone() -> None:
    stats = StatsEngine(load_meta(2610))
    found: list[dict] = []
    for i in range(1102):          # 10 m per frame, back and forth: 11 km
        x = (i * 10) % 200
        x = x if x <= 100 else 200 - x
        found += stats.on_frame(Frame(t=i / 10, index=i, ball=(0.0, 0.0, 0.0),
                                      players=[("NBA-09", float(x), 34.0)])).milestones
    assert kinds(found) == ["distance_10km"]
    assert stats.snapshot()["recent"]["milestones"][-1]["kind"] == "distance_10km"
