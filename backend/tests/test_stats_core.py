import math

import numpy as np
import pytest
from factories import AWAY, HOME, SEEDS, Log, load_events, load_meta, load_summary

from app.engine.clock import ReplayClock
from app.engine.source import Frame, ReplaySource
from app.generator import movement
from app.stats.engine import StatsEngine
from app.stats.speed import SpeedTracker
from app.stats.xg import shot_offsets, shot_xg


def run(events: list[dict], seed: int = 2610) -> StatsEngine:
    engine = StatsEngine(load_meta(seed))
    for event in events:
        engine.on_event(event)
    return engine


# ---- hand-built logs ---------------------------------------------------------------------

def test_possession_is_share_of_in_play_time() -> None:
    log = Log()
    log.add("period_start", 0, HOME, stoppage_added_s=None)
    log.add("kickoff", 0, HOME, "NBA-09")
    log.pass_(0)
    log.change(30, AWAY)                       # NBA on the ball 0-30
    log.add("out_of_play", 40, AWAY, last_touch_team_id=AWAY)   # KVL 30-40
    log.change(40, HOME, cause="out_of_play")
    log.add("throw_in", 55, HOME, "NBA-02", side="left")        # 40-55 dead
    log.pass_(65)                              # NBA 55-65
    log.change(70, AWAY)                       # NBA 65-70
    log.pass_(80, AWAY, "KVL-08")              # KVL 70-80
    clubs = run(log.events).snapshot()["clubs"]
    assert clubs[HOME]["possession"] == pytest.approx(100 * 45 / 65, abs=0.1)
    assert clubs[AWAY]["possession"] == pytest.approx(100 * 20 / 65, abs=0.1)
    assert run(log.events).snapshot()["ball_in_play_s"] == pytest.approx(65)


def test_keeper_holding_after_a_save_is_not_in_play() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.add("shot", 10, HOME, "NBA-09", x=90, y=34, shot_type="open_play",
            body_part="right_foot", outcome="saved", ball_speed_kmh=80.0, goal_y=34.0,
            goal_z=1.0)
    log.add("save", 11, AWAY, "KVL-01", keeper_id="KVL-01", shot_event_id="e000002")
    log.change(11, AWAY, cause="keeper", player="KVL-01")
    log.pass_(19, AWAY, "KVL-01")              # 11-19 the keeper holds it
    log.pass_(25, AWAY, "KVL-04")
    snap = run(log.events).snapshot()
    assert snap["ball_in_play_s"] == pytest.approx(17)
    assert snap["clubs"][AWAY]["possession"] == pytest.approx(100 * 6 / 17, abs=0.1)


def test_club_counts() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.pass_(1, outcome="complete")
    log.pass_(2, outcome="incomplete")
    log.pass_(3, outcome="out")
    log.pass_(4, outcome="complete")
    for i, outcome in enumerate(["goal", "saved", "off_target", "blocked", "post"]):
        log.add("shot", 10 + i, HOME, "NBA-09", x=90, y=34, shot_type="open_play",
                body_part="head", outcome=outcome, ball_speed_kmh=70.0, goal_y=34.0,
                goal_z=1.0)
    log.add("goal", 10, HOME, "NBA-09", scorer_id="NBA-09", assist_id=None,
            shot_event_id="e000006", own_goal=False)
    log.add("corner", 20, HOME, "NBA-07", side="left")
    log.add("foul", 21, AWAY, "KVL-04", fouled_id="NBA-09", severity=0.5, advantage=False)
    log.add("card", 21, AWAY, "KVL-04", card="yellow", foul_event_id="e000013")
    log.add("card", 22, AWAY, "KVL-04", card="second_yellow", foul_event_id="e000013")
    log.add("card", 23, HOME, "NBA-05", card="red", foul_event_id="e000013")
    log.add("offside", 24, HOME, "NBA-09")
    log.add("tackle", 25, AWAY, "KVL-05", opponent_id="NBA-09", outcome="won")
    log.add("tackle", 26, AWAY, "KVL-05", opponent_id="NBA-09", outcome="lost")
    log.add("interception", 27, AWAY, "KVL-06")
    log.add("duel", 28, HOME, "NBA-09", duel_type="ground", opponent_id="KVL-05", outcome="won")
    log.add("duel", 29, HOME, "NBA-09", duel_type="ground", opponent_id="KVL-05",
            outcome="lost")
    clubs = run(log.events).snapshot()["clubs"]
    home, away = clubs[HOME], clubs[AWAY]
    assert home["passes"] == 4 and home["passes_completed"] == 2
    assert home["pass_accuracy"] == 50.0
    assert home["shots"] == 5 and home["shots_on_target"] == 2
    assert home["corners"] == 1 and home["offsides"] == 1
    assert away["fouls"] == 1 and home["fouls"] == 0
    assert away["yellow_cards"] == 1 and away["red_cards"] == 1 and home["red_cards"] == 1
    assert away["tackles_won"] == 1 and away["interceptions"] == 1
    assert home["duels_won"] == 1 and away["duels_won"] == 1
    assert run(log.events).snapshot()["score"] == {HOME: 1, AWAY: 0}


def test_player_counts() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.pass_(1, player="NBA-08", outcome="complete")
    log.pass_(2, player="NBA-08", outcome="incomplete")
    log.add("carry", 3, HOME, "NBA-08", end_x=60.0, end_y=30.0, duration_s=2.0)
    log.add("shot", 5, HOME, "NBA-08", x=94, y=34, shot_type="open_play",
            body_part="left_foot", outcome="saved", ball_speed_kmh=90.0, goal_y=34.0,
            goal_z=1.0)
    log.add("save", 5, AWAY, "KVL-01", keeper_id="KVL-01", shot_event_id="e000005")
    log.add("tackle", 8, AWAY, "KVL-05", opponent_id="NBA-08", outcome="lost")
    log.add("duel", 9, HOME, "NBA-08", duel_type="ground", opponent_id="KVL-05",
            outcome="lost")
    players = run(log.events).snapshot()["players"]
    p = players["NBA-08"]
    assert p["touches"] == 4    # two passes, a carry and a shot
    assert p["passes"] == 2 and p["passes_completed"] == 1
    assert p["shots"] == 1
    assert p["xg"] == pytest.approx(shot_xg(11, 0), abs=0.001)
    assert players["KVL-05"]["tackles"] == 1
    assert players["KVL-05"]["duels_won"] == 1
    assert players["KVL-01"]["touches"] == 1
    assert p["team_id"] == HOME


def test_xg_uses_assisted_chance_from_a_through_ball_in_the_same_possession() -> None:
    def shot(log: Log, t: float) -> None:
        log.add("shot", t, HOME, "NBA-09", x=93, y=30, shot_type="open_play",
                body_part="right_foot", outcome="off_target", ball_speed_kmh=80.0,
                goal_y=40.0, goal_z=1.0)

    dx, dy = shot_offsets(93, 30, True)
    assisted = Log()
    assisted.add("kickoff", 0, HOME, "NBA-09")
    assisted.pass_(1, pass_type="through_ball")
    assisted.add("carry", 2, HOME, "NBA-09", end_x=93.0, end_y=30.0, duration_s=1.0)
    shot(assisted, 3)
    assert run(assisted.events).snapshot()["clubs"][HOME]["xg"] == pytest.approx(
        shot_xg(dx, dy, assisted_chance=True), abs=0.005)

    other_possession = Log()
    other_possession.add("kickoff", 0, HOME, "NBA-09")
    other_possession.pass_(1, pass_type="through_ball")
    other_possession.change(2, AWAY)
    other_possession.change(3, HOME)
    shot(other_possession, 4)
    assert run(other_possession.events).snapshot()["clubs"][HOME]["xg"] == pytest.approx(
        shot_xg(dx, dy), abs=0.005)


def test_second_half_shots_use_the_switched_ends() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09", period=2)
    log.add("shot", 1, HOME, "NBA-09", x=11, y=34, period=2, shot_type="open_play",
            body_part="right_foot", outcome="off_target", ball_speed_kmh=80.0, goal_y=40.0,
            goal_z=1.0)
    assert run(log.events).snapshot()["clubs"][HOME]["xg"] == pytest.approx(
        shot_xg(11, 0), abs=0.005)


# ---- whole matches against the generator's own summary ----------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_full_match_matches_summary(seed: int) -> None:
    summary = load_summary(seed)
    snap = run(load_events(seed), seed).snapshot()
    clubs = snap["clubs"]
    assert snap["score"] == summary["score"]
    assert sum(c["passes"] for c in clubs.values()) == summary["passes"]
    completed = sum(c["passes_completed"] for c in clubs.values())
    assert completed / summary["passes"] == pytest.approx(summary["pass_completion"], abs=1e-4)
    assert sum(c["shots"] for c in clubs.values()) == summary["shots"]
    on_target = sum(c["shots_on_target"] for c in clubs.values())
    assert on_target / summary["shots"] == pytest.approx(summary["shots_on_target_pct"],
                                                         abs=1e-4)
    for team, xg in summary["xg"].items():
        assert clubs[team]["xg"] == pytest.approx(xg, abs=0.006)
        assert clubs[team]["possession"] == pytest.approx(100 * summary["possession"][team],
                                                          abs=0.02)
    for key, measure in [("fouls", "fouls"), ("yellow_cards", "yellow_cards"),
                         ("red_cards", "red_cards"), ("corners", "corners"),
                         ("offsides", "offsides"), ("interceptions", "interceptions")]:
        assert sum(c[key] for c in clubs.values()) == summary[measure], key
    assert snap["ball_in_play_s"] / 60 == pytest.approx(summary["ball_in_play_min"], abs=0.01)


# ---- tracking: speed, distance, sprints --------------------------------------------------

def frame(i: int, players: list[tuple[str, float, float]]) -> Frame:
    return Frame(t=i / 10, index=i, ball=(52.5, 34.0, 0.0), players=players)


def run_straight(tracker: SpeedTracker, mps: float, frames: int, start: int = 0,
                 x0: float = 0.0) -> list[dict]:
    badges = []
    for i in range(frames):
        badges += tracker.on_frame(frame(start + i, [("NBA-09", x0 + mps * i / 10, 34.0)]))
    return badges


def test_speed_is_averaged_over_half_a_second() -> None:
    tracker = SpeedTracker()
    run_straight(tracker, 7.0, 30)
    stats = tracker.player("NBA-09")
    assert stats["top_speed_kmh"] == pytest.approx(7.0 * 3.6, abs=0.05)
    assert stats["distance_km"] == pytest.approx(7.0 * 2.9 / 1000, abs=5e-4)


@pytest.mark.parametrize("mps, frames, sprints", [
    (8.0, 16, 1),     # 28.8 km/h for 1.5 s
    (6.5, 30, 0),     # 23.4 km/h: too slow
    (8.0, 12, 0),     # fast enough, but under a second at sprint speed
])
def test_sprint_needs_25_2_kmh_for_a_second(mps: float, frames: int, sprints: int) -> None:
    tracker = SpeedTracker()
    run_straight(tracker, mps, frames)
    assert tracker.player("NBA-09")["sprints"] == sprints


def test_one_long_run_is_one_sprint() -> None:
    tracker = SpeedTracker()
    run_straight(tracker, 8.0, 100)
    assert tracker.player("NBA-09")["sprints"] == 1


def test_speed_badge_at_most_once_per_player_per_five_minutes() -> None:
    tracker = SpeedTracker()
    first = run_straight(tracker, 9.0, 20)
    again = run_straight(tracker, 9.0, 20, start=1200, x0=50)       # 2 minutes later
    later = run_straight(tracker, 9.0, 20, start=3100, x0=0)       # 5+ minutes later
    assert [b["kind"] for b in first] == ["speed"]
    assert first[0]["speed_kmh"] >= 32
    assert again == []
    assert [b["kind"] for b in later] == ["speed"]


def test_distance_badges_at_5_and_10_km() -> None:
    tracker = SpeedTracker()
    badges = []
    x = 0.0
    for i in range(2101):          # 10 m per frame, back and forth, 21 km
        x = (i * 10) % 200
        x = x if x <= 100 else 200 - x
        badges += tracker.on_frame(frame(i, [("NBA-09", x, 34.0)]))
    distance = [b for b in badges if b["kind"] == "distance"]
    assert [b["km"] for b in distance] == [5, 10]


def test_tracking_matches_the_generator() -> None:
    source = ReplaySource(2610, ReplayClock())
    tracker = SpeedTracker()
    for item in source.items_until(math.inf):
        if isinstance(item, Frame):
            tracker.on_frame(item)
    data = np.load(source.folder / "tracking.npz")
    tracking = {k: data[k] for k in data.files}
    expected_km = float(movement.player_distances_km(tracking).sum())
    total_km = sum(tracker.player(p)["distance_km"] for p in tracker.players())
    assert total_km == pytest.approx(expected_km, rel=1e-3)
    top = max(tracker.player(p)["top_speed_kmh"] for p in tracker.players())
    assert top == pytest.approx(movement.top_speed_kmh(tracking), abs=0.5)
