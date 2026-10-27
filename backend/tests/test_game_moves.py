"""Moving blanks and wildcards (spec 4.7, with silent windows per the 4.7 amendment)."""

import pytest
from game_helpers import kickoff, new_game, of, types

from app.game.card import LINES

BLANK = (0, 0)
OTHER_BLANK = (4, 4)


def setup(from_state="empty_blank", to=None):
    """A game with the square at BLANK and the target square forced into given states.
    `to` is (kind, state) for the square at the target cell."""
    game, clock, log = new_game()
    kickoff(game, log)
    board = game.board
    source = board.at(BLANK)
    _set(source, "live", from_state)
    target = next(s for s in board.squares if s.kind == "deadline")
    if to is not None:
        kind, state = to
        if kind == "live":
            target = board.at(OTHER_BLANK)
        elif kind == "first":
            target = next(s for s in board.squares if s.kind == "first")
        _set(target, kind, state)
    return game, clock, source, target


def _set(sq, kind, state):
    sq.kind, sq.state = kind, state
    if state in ("correct", "wrong", "missed", "void", "too_early", "wildcard"):
        sq.result = {"status": "correct" if state == "wildcard" else state, "points": 0,
                     "explanation": "", "evidence_event_ids": []}
    if state == "open":
        sq.window = True


def cell(c):
    return {"row": c[0], "col": c[1]}


@pytest.mark.parametrize("from_state,allowed", [
    ("empty_blank", True),
    ("wildcard", True),
    ("wrong", False),      # a wrong live square stays put
    ("missed", False),
    ("waiting", False),    # nothing else can be picked up
])
def test_what_can_be_picked_up(from_state, allowed):
    game, clock, source, target = setup(from_state)
    if from_state == "waiting":
        source.kind = "deadline"
    out = game.move(cell(source.cell), cell(target.cell))
    assert (types(out) != ["error"]) == allowed


def test_a_static_can_never_be_picked_up():
    game, clock, source, target = setup()
    out = game.move(cell(target.cell), cell(source.cell))
    assert types(out) == ["error"]


@pytest.mark.parametrize("to,allowed", [
    (("deadline", "waiting"), True),
    (("first", "waiting"), True),
    (("first", "open"), True),          # silent window: still looks waiting, may be swapped
    (("live", "empty_blank"), True),
    (("live", "wildcard"), True),
    (("deadline", "correct"), False),   # resolved statics never move
    (("deadline", "wrong"), False),
    (("deadline", "missed"), False),
    (("first", "void"), False),
    (("first", "too_early"), False),
    (("live", "wrong"), False),
    (("live", "missed"), False),
])
def test_allowed_and_blocked_targets(to, allowed):
    game, clock, source, target = setup(to=to)
    source_cell, target_cell = source.cell, target.cell
    out = game.move(cell(source_cell), cell(target_cell))
    if allowed:
        assert of(out, "board.update")
        assert source.cell == target_cell and target.cell == source_cell
    else:
        assert types(out) == ["error"]
        assert source.cell == source_cell and target.cell == target_cell


def test_open_announced_window_blocks_every_move():
    game, clock, source, target = setup()
    other = next(s for s in game.board.squares if s.kind == "deadline" and s is not target)
    _set(other, "deadline", "open")
    assert types(game.move(cell(source.cell), cell(target.cell))) == ["error"]
    other.window, other.state = False, "missed"
    assert of(game.move(cell(source.cell), cell(target.cell)), "board.update")


def test_silent_window_elsewhere_does_not_block():
    game, clock, source, target = setup()
    first = next(s for s in game.board.squares if s.kind == "first")
    _set(first, "first", "open")
    assert of(game.move(cell(source.cell), cell(target.cell)), "board.update")


def test_open_live_square_cannot_be_moved():
    game, clock, source, target = setup("open")
    assert types(game.move(cell(source.cell), cell(target.cell))) == ["error"]


def test_swap_keeps_question_and_deadline():
    game, clock, source, target = setup()
    before = (target.id, target.text, target.deadline_s, target.state)
    game.move(cell(source.cell), cell(target.cell))
    assert (target.id, target.text, target.deadline_s, target.state) == before


def test_moves_are_unlimited():
    game, clock, source, target = setup()
    for _ in range(10):
        assert of(game.move(cell(source.cell), cell(target.cell)), "board.update")


def test_same_cell_and_off_board_are_rejected():
    game, clock, source, target = setup()
    assert types(game.move(cell(source.cell), cell(source.cell))) == ["error"]
    assert types(game.move(cell(source.cell), {"row": 5, "col": 0})) == ["error"]
    assert types(game.move("nonsense", cell(target.cell))) == ["error"]


def test_cells_may_be_pairs():
    game, clock, source, target = setup()
    assert of(game.move(list(source.cell), list(target.cell)), "board.update")


def complete_except(game, line, cell_left):
    for c in LINES[line]:
        if c != cell_left:
            _set(game.board.at(c), game.board.at(c).kind, "correct")


def test_a_move_can_complete_a_line_which_then_freezes():
    game, clock, source, target = setup("wildcard")
    row = target.cell[0]
    complete_except(game, f"row:{row}", target.cell)
    out = game.move(cell(source.cell), cell(target.cell))
    assert of(out, "board.line")[0]["line"] == f"row:{row}"
    assert game.board.locked(source)
    # The wildcard is now frozen in that line, wherever it could go next.
    blank = next(s for s in game.board.squares if s.state == "empty_blank")
    assert types(game.move(cell(source.cell), cell(blank.cell))) == ["error"]


def test_locked_squares_are_blocked_targets():
    game, clock, source, target = setup()
    other = game.board.at(OTHER_BLANK)
    _set(other, "live", "wildcard")
    complete_except(game, "row:4", OTHER_BLANK)
    game.keeper.board_changed()
    assert "row:4" in game.board.scored_lines
    assert types(game.move(cell(source.cell), cell(OTHER_BLANK))) == ["error"]


def test_a_locked_wildcard_still_counts_for_its_other_lines():
    game, clock, source, target = setup("wildcard")
    complete_except(game, "row:0", BLANK)
    game.keeper.board_changed()
    assert game.board.scored_lines == ["row:0"]
    complete_except(game, "col:0", BLANK)
    out = game.keeper.board_changed()
    assert of(out, "board.line")[0]["line"] == "col:0"
