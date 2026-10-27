"""Windows and answers (spec 4.4, 4.5)."""

import pytest
from factories import AWAY, HOME
from game_helpers import kickoff, new_game, of, second_half, square, types


def set_template(game, square_id, template_id):
    """Pin a known deadline template on a square so tests don't depend on the card draw."""
    from app.game.bank import TEMPLATES
    from app.game.card import make_static
    old = game.board.get(square_id)
    new = make_static(old.id, TEMPLATES[template_id], game.profile.mode, old.cell, game.meta,
                      deadline_s=old.deadline_s)
    game.board.squares[game.board.squares.index(old)] = new
    return new


def deadline_square(game, deadline_s, template_id="corners"):
    sq = next(s for s in game.board.squares if s.deadline_s == deadline_s)
    return set_template(game, sq.id, template_id)


# ---- deadline windows ---------------------------------------------------------------------

def test_deadline_window_opens_when_the_clock_reaches_it():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    assert not of(game.on_tick(899.9), "square.window_open")
    out = game.on_tick(900.0)
    opened = of(out, "square.window_open")
    assert opened == [{"type": "square.window_open", "square_id": sq.id,
                       "closes_at": clock.wall_ms() + 20_000}]
    assert of(out, "mask.on") == [{"type": "mask.on", "square_id": sq.id, "tags": ["corners"]}]
    assert sq.state == "open" and sq.view()["closes_at"] == clock.wall_ms() + 20_000


@pytest.mark.parametrize("corner_times,expected", [
    ((100.0, 899.0, 900.0), "3"),        # at or before the deadline second counts
    ((100.0, 900.01, 950.0), "1"),       # after it never counts
    ((), "0"),
])
def test_deadline_count_ignores_events_after_the_deadline(corner_times, expected):
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    for t in corner_times:
        game.on_event(log.add("corner", t, team=HOME, tags=("corners",)))
    game.on_tick(960.0)
    assert sq.correct_answer == expected


def test_event_past_the_deadline_opens_the_window_before_it_counts():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    out = game.on_event(log.add("corner", 901.0, team=HOME, tags=("corners",)))
    assert of(out, "square.window_open") and sq.correct_answer == "0"


def test_second_half_deadlines_use_the_clock_reading():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 3300)                  # 55:00
    second_half(game, log, t=2880.0)                  # 3 minutes of first-half stoppage
    assert not of(game.on_tick(3300.0), "square.window_open")
    assert of(game.on_tick(2880.0 + 600.0), "square.window_open")
    assert sq.state == "open"


def test_first_half_deadline_at_45_is_before_stoppage():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 2700)
    assert of(game.on_tick(2700.0), "square.window_open") and sq.state == "open"


@pytest.mark.parametrize("speed", [1, 5, 10])
def test_window_lasts_20_wall_seconds_at_any_speed(speed):
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    t = 900.0
    for _ in range(199):                             # 19.9 s of wall time
        clock.advance(0.1)
        t += 0.1 * speed
        assert not of(game.on_tick(t), "square.result")
    assert sq.state == "open"
    clock.advance(0.1)
    out = game.on_tick(t + 0.1 * speed)
    assert of(out, "square.result")[0]["status"] == "missed"
    assert sq.state == "missed"


def test_dev_pause_freezes_open_windows():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    clock.advance(10)
    game.pause(True)
    clock.advance(300)
    assert not of(game.on_tick(900.0), "square.result")
    game.pause(False)
    clock.advance(9.9)
    assert sq.state == "open"
    assert not of(game.on_tick(900.0), "square.result")
    clock.advance(0.1)
    assert of(game.on_tick(900.0), "square.result")


def test_answer_before_a_deadline_window_is_rejected():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    out = game.answer(sq.id, "2")
    assert types(out) == ["error"] and sq.answer is None and sq.state == "waiting"


# ---- first-to-happen windows ---------------------------------------------------------------

def test_first_to_happen_window_is_silent():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = square(game, "first_foul")
    out = game.on_event(log.add("foul", 60.0, team=AWAY, player="KVL-04", tags=("fouls",),
                                fouled_id="NBA-08", severity=0.2, advantage=False))
    assert not [m for m in out if m.get("square_id") == sq.id]
    assert sq.state == "open"
    assert sq.view()["state"] == "waiting" and sq.view()["closes_at"] is None


def test_answer_before_the_first_event_is_too_early():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = square(game, "first_foul")
    out = game.answer(sq.id, "KVL-04")
    result = of(out, "square.result")
    assert result == [{"type": "square.result", "square_id": sq.id, "status": "too_early",
                       "points": 0, "correct_answer": None}]
    assert sq.state == "too_early"
    # The foul still happens later; the guess is gone.
    game.on_event(log.add("foul", 60.0, team=AWAY, player="KVL-04", tags=("fouls",),
                          fouled_id="NBA-08", severity=0.2, advantage=False))
    assert sq.state == "too_early"
    assert types(game.answer(sq.id, "KVL-04")) == ["error"]


@pytest.mark.parametrize("value,status", [("KVL-04", "correct"), ("KVL-05", "wrong")])
def test_answer_inside_the_first_window(value, status):
    game, clock, log = new_game()
    kickoff(game, log)
    sq = square(game, "first_foul")
    game.on_event(log.add("foul", 60.0, team=AWAY, player="KVL-04", tags=("fouls",),
                          fouled_id="NBA-08", severity=0.2, advantage=False))
    clock.advance(2)
    out = game.answer(sq.id, value)
    result = of(out, "square.result")[0]
    assert result["status"] == status and result["correct_answer"] == "KVL-04"
    assert (result["points"] > 0) == (status == "correct")
    assert sq.state == status


def test_normal_mode_first_squares_take_the_team():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    sq = square(game, "first_sub_off")
    game.on_event(log.add("substitution", 3500.0, team=HOME, player="NBA-17", period=2,
                          tags=("subs",), player_off_id="NBA-09", player_on_id="NBA-17"))
    assert sq.correct_answer == HOME


def test_first_scorer_and_sub_off_read_their_own_fields():
    game, clock, log = new_game("advanced")
    kickoff(game, log)
    game.on_event(log.add("goal", 100.0, team=HOME, player="NBA-08", tags=("goals",),
                          scorer_id="NBA-08", assist_id=None, shot_event_id="e1",
                          own_goal=False))
    game.on_event(log.add("substitution", 3500.0, team=HOME, player="NBA-17", period=2,
                          tags=("subs",), player_off_id="NBA-09", player_on_id="NBA-17"))
    assert square(game, "first_goal").correct_answer == "NBA-08"
    assert square(game, "first_sub_off").correct_answer == "NBA-09"


def test_first_on_target_ignores_shots_off_target():
    game, clock, log = new_game("advanced")
    kickoff(game, log)
    sq = square(game, "first_on_target")
    game.on_event(log.add("shot", 50.0, team=HOME, player="NBA-09", outcome="off_target",
                          tags=("shots",), shot_type="open_play", body_part="right_foot",
                          ball_speed_kmh=80.0, goal_y=30.0, goal_z=1.0))
    assert sq.state == "waiting"
    game.on_event(log.add("shot", 70.0, team=AWAY, player="KVL-09", outcome="saved",
                          tags=("shots",), shot_type="open_play", body_part="right_foot",
                          ball_speed_kmh=80.0, goal_y=34.0, goal_z=1.0))
    assert sq.state == "open" and sq.correct_answer == "KVL-09"


def test_windows_can_overlap():
    game, clock, log = new_game()
    kickoff(game, log)
    game.on_event(log.add("foul", 60.0, team=AWAY, player="KVL-04", tags=("fouls",),
                          fouled_id="NBA-08", severity=0.8, advantage=False))
    game.on_event(log.add("card", 60.0, team=AWAY, player="KVL-04", tags=("cards",),
                          card="yellow", foul_event_id="e000003"))
    assert square(game, "first_foul").state == "open"
    assert square(game, "first_booking").state == "open"


# ---- results ----------------------------------------------------------------------------

def test_one_answer_per_square():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    first = game.answer(sq.id, "5")
    assert of(first, "square.result")[0]["status"] == "wrong"
    assert types(game.answer(sq.id, "0")) == ["error"]
    assert sq.state == "wrong" and sq.answer["value"] == "5"


def test_invalid_values_are_rejected_without_using_the_guess():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    assert types(game.answer(sq.id, "seven")) == ["error"]
    assert sq.answer is None
    assert of(game.answer(sq.id, sq.options[0]), "square.result")


def test_normal_mode_range_answers():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    assert sq.correct_answer == sq.options[0]       # no corners: the lowest range
    assert of(game.answer(sq.id, sq.options[0]), "square.result")[0]["status"] == "correct"


def test_result_at_once_explanation_at_close():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    out = game.answer(sq.id, "0")
    assert of(out, "square.result") and not of(out, "square.explanation")
    clock.advance(20)
    out = game.on_tick(910.0)
    assert of(out, "square.explanation")[0]["square_id"] == sq.id
    assert not of(out, "square.result")              # already resolved
    assert of(out, "mask.off") == [{"type": "mask.off", "square_id": sq.id, "tags": ["corners"]}]


def test_no_answer_is_missed():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    clock.advance(20)
    out = game.on_tick(905.0)
    assert of(out, "square.result") == [{"type": "square.result", "square_id": sq.id,
                                          "status": "missed", "points": 0,
                                          "correct_answer": "0"}]
    assert types(game.answer(sq.id, "0")) == ["error"]


def test_window_open_at_full_time_keeps_running():
    game, clock, log = new_game()
    kickoff(game, log)
    second_half(game, log)
    sq = square(game, "first_foul")
    game.on_event(log.add("foul", 5900.0, team=AWAY, player="KVL-04", period=2,
                          tags=("fouls",), fouled_id="NBA-08", severity=0.2, advantage=False))
    game.on_event(log.add("period_end", 5901.0, team=None, period=2, stoppage_added_s=300))
    clock.advance(10)
    game.on_tick(5901.0)
    assert sq.state == "open"
    assert of(game.answer(sq.id, "KVL-04"), "square.result")[0]["status"] == "correct"


def test_first_events_that_never_happen_are_void():
    game, clock, log = new_game()
    kickoff(game, log)
    second_half(game, log)
    out = game.on_event(log.add("period_end", 5800.0, team=None, period=2, stoppage_added_s=300))
    goal = square(game, "first_goal")
    assert goal.state == "void"
    assert {"type": "square.result", "square_id": goal.id, "status": "void", "points": 0,
            "correct_answer": None} in out


def test_jumped_over_windows_are_skipped():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    foul = square(game, "first_foul")
    game.on_event(log.add("foul", 60.0, team=AWAY, player="KVL-04", tags=("fouls",),
                          fouled_id="NBA-08", severity=0.2, advantage=False), live=False)
    assert foul.state == "missed"
    out = game.on_tick(1500.0)                        # the clock jumped past 15'
    assert sq.state == "missed" and not of(out, "square.window_open")
