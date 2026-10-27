"""Scoring, lines and bingo (spec 4.6, 4.8)."""

import pytest
from game_helpers import META, kickoff, new_game, of
from test_game_windows import deadline_square

from app.game.card import BLANK_CELLS, LINES, Profile, build_card
from app.game.scoring import check_lines, speed_points


@pytest.mark.parametrize("base,seconds,points", [
    (100, 0.0, 100), (100, 3.0, 100), (100, 11.5, 65), (100, 20.0, 30), (100, 25.0, 30),
    (150, 0.0, 150), (150, 3.0, 150), (150, 20.0, 45),
])
def test_speed_points(base, seconds, points):
    assert speed_points(base, seconds) == points


@pytest.mark.parametrize("base", [100, 150])
def test_points_never_rise_with_time(base):
    values = [speed_points(base, i / 10) for i in range(0, 250)]
    assert all(a >= b for a, b in zip(values, values[1:], strict=False))


def board():
    return build_card(META, Profile.parse({}, META))


def mark(b, cells, state="correct", points=100):
    for cell in cells:
        sq = b.at(cell)
        sq.state = state
        sq.result = {"status": "correct" if state == "wildcard" else state, "points": points,
                     "explanation": "", "evidence_event_ids": []}


@pytest.mark.parametrize("line", sorted(LINES))
def test_every_line_is_detected(line):
    b = board()
    mark(b, LINES[line])
    found, full = check_lines(b)
    assert [f.line for f in found] == [line] and full == 0
    assert b.scored_lines == [line]


@pytest.mark.parametrize("states,scores", [
    (["correct"] * 5, True),
    (["correct", "correct", "void", "correct", "correct"], True),       # void counts
    (["correct", "wildcard", "void", "correct", "correct"], True),
    (["correct", "correct", "wrong", "correct", "correct"], False),
    (["correct", "correct", "too_early", "correct", "correct"], False),
    (["correct", "correct", "missed", "correct", "correct"], False),
    (["correct", "correct", "waiting", "correct", "correct"], False),
    (["correct", "correct", "open", "correct", "correct"], False),
    (["correct", "correct", "empty_blank", "correct", "correct"], False),
])
def test_what_completes_a_line(states, scores):
    b = board()
    for cell, state in zip(LINES["row:1"], states, strict=True):
        mark(b, [cell], state)
    found, _ = check_lines(b)
    assert bool(found) == scores


def test_a_line_scores_only_once():
    b = board()
    mark(b, LINES["row:1"])
    assert len(check_lines(b)[0]) == 1
    assert check_lines(b)[0] == []
    assert b.bonus_points == 500


def test_first_line_then_further_lines():
    b = board()
    mark(b, LINES["row:1"])
    first, _ = check_lines(b)
    mark(b, LINES["row:3"])
    second, _ = check_lines(b)
    mark(b, LINES["col:1"] + LINES["col:3"])
    more, _ = check_lines(b)
    assert [f.points for f in first + second + more] == [500, 250, 250, 250]
    assert b.bonus_points == 1250


def test_two_lines_at_once_pay_first_then_further():
    b = board()
    mark(b, LINES["row:1"] + LINES["col:1"])
    found, _ = check_lines(b)
    assert sorted(f.points for f in found) == [250, 500]


def test_blank_slate_bonus():
    b = board()
    diag = LINES["diag:0"]
    # Line up blanks on the main diagonal: corners and centre already sit on it except two.
    for cell in diag:
        sq = b.at(cell)
        sq.kind = "live"
        mark(b, [cell], "wildcard", 150)
    found, _ = check_lines(b)
    assert [(f.line, f.points, f.blank_slate) for f in found] == [("diag:0", 800, True)]


def test_full_card_bonus_once():
    b = board()
    mark(b, [(r, c) for r in range(5) for c in range(5)])
    found, full = check_lines(b)
    assert len(found) == 12 and full == 2000
    assert check_lines(b) == ([], 0)
    assert b.points == 500 + 11 * 250 + 2000 + 25 * 100


def test_full_card_counts_void():
    b = board()
    mark(b, [(r, c) for r in range(5) for c in range(5)])
    mark(b, [(1, 1), (2, 3)], "void", 0)
    assert check_lines(b)[1] == 2000


def test_blank_cells_sit_on_the_most_lines():
    counts = {(r, c): sum((r, c) in cells for cells in LINES.values())
              for r in range(5) for c in range(5)}
    assert max(counts.values()) == counts[(2, 2)] == 4
    assert all(counts[cell] == 3 for cell in BLANK_CELLS if cell != (2, 2))


def test_points_through_the_game():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    game.on_tick(900.0)
    clock.advance(11.5)
    out = game.answer(sq.id, "0")
    assert of(out, "square.result")[0]["points"] == 65
    assert of(out, "board.update")[0]["points"] == 65


def test_scoring_a_line_through_the_game_sends_the_bonus():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900)
    row = LINES[f"row:{sq.cell[0]}"]
    for cell in row:
        other = game.board.at(cell)
        if other is not sq:
            mark(game.board, [cell], "void", 0)
    game.on_tick(900.0)
    out = game.answer(sq.id, "0")
    assert of(out, "board.line") == [{"type": "board.line", "line": f"row:{sq.cell[0]}",
                                      "points": 500, "blank_slate": False}]
    update = of(out, "board.update")[0]
    assert update["bingos"] == 1 and update["points"] == 600
    assert update["scored_lines"] == [f"row:{sq.cell[0]}"]
