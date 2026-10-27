"""Simulated fans and the leaderboard (spec 3, 8.1)."""

import re
import statistics

import pytest
from game_helpers import FakeTime

from app.engine.source import MATCHES_DIR, load_match
from app.game.fans import FAN_COUNT, FanLeague, leaderboard
from app.stats.engine import StatsEngine

DATA = load_match(MATCHES_DIR / "2610")


def play(mode="normal", seed=2610):
    clock = FakeTime()
    league = FanLeague(DATA.meta, mode, now=clock.now, wall_ms=clock.wall_ms,
                       planted=frozenset(range(5)))
    stats = StatsEngine(DATA.meta)
    for e in DATA.events:
        league.on_event(e, stats.on_event(e).significance)
        clock.advance(0.5)
        league.on_tick(e["t"])
    clock.advance(30)
    league.on_tick(DATA.events[-1]["t"])
    return league


@pytest.fixture(scope="module")
def normal():
    return play("normal")


def test_twenty_fans_with_made_up_handles(normal):
    handles = [f.handle for f in normal.fans]
    assert len(handles) == FAN_COUNT == 20 and len(set(handles)) == 20
    assert all(re.fullmatch(r"[A-Z][a-z]+[A-Z][a-z]+_\d{2}", h) for h in handles)


def test_fans_answer_every_window(normal):
    for fan in normal.fans:
        states = {s.state for s in fan.board.squares}
        assert not states & {"waiting", "open", "empty_blank"}, (fan.handle, states)
        lives = [s for s in fan.board.squares if s.kind == "live"]
        assert all(s.template for s in lives)


def test_fan_points_follow_the_scoring_rules(normal):
    for fan in normal.fans:
        board = fan.board
        assert board.points == board.bonus_points + sum(
            s.result["points"] for s in board.squares if s.result)
        assert board.points >= 0
    assert any(fan.board.scored_lines for fan in normal.fans)


def test_fan_accuracy_shows_in_results(normal):
    rates, accuracies = [], []
    for fan in normal.fans:
        judged = [s for s in fan.board.squares
                  if s.result and s.result["status"] in ("correct", "wrong")]
        rates.append(sum(s.result["status"] == "correct" for s in judged) / len(judged))
        accuracies.append(fan.accuracy)
    assert abs(statistics.fmean(rates) - statistics.fmean(accuracies)) < 0.1


def test_answer_times_are_inside_the_window(normal):
    for fan in normal.fans:
        times = [s.answer["elapsed_s"] for s in fan.board.squares if s.answer]
        assert times and all(0.5 <= t <= 19.5 for t in times)


def test_same_match_and_mode_same_fans(normal):
    again = play("normal")
    assert [r for r in again.rows()] == [r for r in normal.rows()]


def test_modes_have_their_own_fans(normal):
    advanced = FanLeague(DATA.meta, "advanced")
    assert any(s.answer_type == "player" for s in advanced.fans[0].board.squares)
    assert not any(s.answer_type == "player" for s in normal.fans[0].board.squares)


@pytest.mark.parametrize("viewer_points,rank,rows", [(10**6, 1, 5), (-1, 21, 6)])
def test_leaderboard_top_five_plus_you(normal, viewer_points, rank, rows):
    you = {"handle": "You", "points": viewer_points, "correct": 0, "avg_answer_s": None}
    board = leaderboard(you, normal.rows())
    assert len(board) == rows
    mine = [r for r in board if r["you"]]
    assert len(mine) == 1 and mine[0]["rank"] == rank
    top = [r for r in board if not r["you"]] if rank > 5 else board
    assert [r["rank"] for r in top[:5]] == sorted(r["rank"] for r in top[:5])
    assert set(board[0]) >= {"rank", "handle", "points", "correct", "avg_answer_s", "you"}
