"""Strategist optimizer (spec 4.12) and how the game uses it."""

import pytest
from factories import HOME
from game_helpers import kickoff, new_game, of, types
from test_game_moves import _set

from app.game.card import LINES
from app.game.strategist import Accuracy, rank_blanks, suggest, win_chance


def hopeless(game):
    """Every static wrong and every blank empty, with no live squares to come."""
    for sq in game.board.squares:
        if sq.kind == "live":
            _set(sq, "live", "empty_blank")
        else:
            _set(sq, sq.kind, "wrong")
    game.live.needed.clear()


def near_line(game):
    """Row 1 has four correct squares and one waiting static at (1, 2); a wildcard at (0, 0)."""
    hopeless(game)
    for c in LINES["row:1"]:
        sq = game.board.at(c)
        if c == (1, 2):
            sq.state, sq.result = "waiting", None
        else:
            _set(sq, sq.kind, "correct")
    _set(game.board.at((0, 0)), "live", "wildcard")


def test_accuracy_starts_at_half_and_updates():
    acc = Accuracy()
    assert acc.of("deadline") == acc.of("first") == acc.of("live") == 0.5
    acc.record("deadline", True)
    assert acc.of("deadline") == pytest.approx(2 / 3)
    acc.record("deadline", False)
    acc.record("live", False)
    assert acc.of("deadline") == 0.5 and acc.of("live") == pytest.approx(1 / 3)


def test_win_chance_bounds():
    game, clock, log = new_game()
    near_line(game)
    assert win_chance(game.board, Accuracy(), 0) == pytest.approx(0.5, abs=0.04)
    hopeless(game)
    assert win_chance(game.board, Accuracy(), 0) == 0.0


def test_suggests_the_move_that_raises_the_chance():
    game, clock, log = new_game()
    near_line(game)
    advice = suggest(game.board, Accuracy(), 0)
    assert advice is not None
    assert [(m["from_cell"], m["to_cell"]) for m in advice.moves] == \
        [({"row": 0, "col": 0}, {"row": 1, "col": 2})]
    assert advice.before == pytest.approx(0.5, abs=0.04) and advice.after == 1.0
    assert 0 < len(advice.reason) <= 120


def test_only_suggests_gains_of_3_points_or_more():
    game, clock, log = new_game()
    near_line(game)
    assert suggest(game.board, Accuracy(), 0, min_gain=0.6) is None
    hopeless(game)
    assert suggest(game.board, Accuracy(), 0) is None


def test_never_touches_locked_squares():
    game, clock, log = new_game()
    near_line(game)
    for c in LINES["row:0"]:
        if c != (0, 0):
            _set(game.board.at(c), game.board.at(c).kind, "correct")
    game.keeper.board_changed()
    assert "row:0" in game.board.scored_lines
    assert suggest(game.board, Accuracy(), 0) is None     # the only wildcard is frozen


def test_considers_pairs_of_swaps():
    game, clock, log = new_game()
    hopeless(game)
    # Two wildcards; row 3 needs two more squares, both waiting statics at (3, 1), (3, 3).
    for c in LINES["row:3"]:
        sq = game.board.at(c)
        if c in ((3, 1), (3, 3)):
            sq.state, sq.result = "waiting", None
        else:
            _set(sq, sq.kind, "correct")
    _set(game.board.at((0, 0)), "live", "wildcard")
    _set(game.board.at((0, 4)), "live", "wildcard")
    advice = suggest(game.board, Accuracy(), 0)
    assert advice is not None and len(advice.moves) == 2 and advice.after == 1.0


def test_deterministic():
    game, clock, log = new_game()
    near_line(game)
    a, b = suggest(game.board, Accuracy(), 0), suggest(game.board, Accuracy(), 0)
    assert a is not None and b is not None and (a.moves, a.before) == (b.moves, b.before)


def test_live_square_lands_in_the_best_blank():
    game, clock, log = new_game()
    hopeless(game)
    for c in LINES["col:4"]:
        if c != (4, 4):
            _set(game.board.at(c), game.board.at(c).kind, "correct")
    game.live.needed = {0, 1}
    best = rank_blanks(game.board, Accuracy(), 2)
    assert best.cell == (4, 4)


# ---- the game uses it --------------------------------------------------------------------

def offside(game, log, t=600.0):
    log.pass_(t - 2, HOME, "NBA-08", outcome="offside", pass_type="through_ball")
    game.on_event(log.events[-1])
    return game.on_event(log.add("offside", t, team=HOME, player="NBA-09",
                                 tags=("offsides",)), significance=60)


@pytest.mark.parametrize("setting,expect", [
    ("suggest", "advice"), ("auto", "applied"), ("manual", None)])
def test_strategist_settings(setting, expect):
    game, clock, log = new_game(strategist=setting)
    kickoff(game, log)
    near_line(game)
    game.strategy_due = True
    out = game.on_tick(10.0)
    advice = of(out, "strategy.advice")
    if expect is None:
        assert not advice
        return
    assert len(advice) == 1 and advice[0]["applied"] == (expect == "applied")
    assert set(advice[0]) >= {"advice_id", "moves", "before", "after", "reason"}
    moved = game.board.at((1, 2)).state == "wildcard"
    assert moved == (expect == "applied")
    if expect == "applied":
        assert of(out, "board.line")


def test_strategist_waits_for_announced_windows():
    game, clock, log = new_game(strategist="suggest")
    kickoff(game, log)
    near_line(game)
    deadline = next(s for s in game.board.squares if s.kind == "deadline" and s.state == "wrong")
    deadline.state, deadline.result, deadline.window = "open", None, True
    deadline.closes_at = 20.0
    game.strategy_due = True
    assert not of(game.on_tick(10.0), "strategy.advice")
    clock.advance(20)
    assert of(game.on_tick(20.0), "strategy.advice")


def test_apply_suggested_advice():
    game, clock, log = new_game(strategist="suggest")
    kickoff(game, log)
    near_line(game)
    game.strategy_due = True
    advice = of(game.on_tick(10.0), "strategy.advice")[0]
    out = game.apply_advice(advice["advice_id"])
    assert of(out, "board.line") and game.board.at((1, 2)).state == "wildcard"
    assert types(game.apply_advice(advice["advice_id"])) == ["error"]   # used up


def test_stale_advice_is_rejected():
    game, clock, log = new_game(strategist="suggest")
    kickoff(game, log)
    near_line(game)
    game.strategy_due = True
    advice = of(game.on_tick(10.0), "strategy.advice")[0]
    blank = next(s for s in game.board.squares if s.state == "empty_blank")
    game.move({"row": 0, "col": 0}, {"row": blank.cell[0], "col": blank.cell[1]})
    assert types(game.apply_advice(advice["advice_id"])) == ["error"]


def test_results_update_the_viewer_accuracy():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = next(s for s in game.board.squares if s.deadline_s == 900)
    game.on_tick(900.0)
    game.answer(sq.id, sq.correct_answer)
    assert game.accuracy.of("deadline") == pytest.approx(2 / 3)
    assert game.strategy_due
