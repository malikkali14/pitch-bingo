"""Strategist optimizer (spec 4.12): which swaps make a line most likely.

Each unresolved square succeeds with the viewer's accuracy for its kind; an empty blank must
also get one of the live squares still to come. 2,000 simulated endings are drawn once per
call and shared by every arrangement, so arrangements are compared on the same luck.
"""

import itertools
import uuid
from dataclasses import dataclass, field

import numpy as np

from app.game.card import GOOD, LINES, Board, Cell, Square
from app.game.scorekeeper import Scorekeeper

SIMULATIONS = 2000
MIN_GAIN = 0.03
PAIR_FROM = 6           # pairs are built from the best single swaps
LOST = {"wrong", "missed", "too_early"}
LINE_CELLS = {line: [r * 5 + c for r, c in cells] for line, cells in LINES.items()}


@dataclass
class Accuracy:
    """The viewer's accuracy per square kind: 50% to start, then (correct + 1) / (n + 2)."""

    correct: dict[str, int] = field(default_factory=dict)
    answered: dict[str, int] = field(default_factory=dict)

    def of(self, kind: str) -> float:
        return (self.correct.get(kind, 0) + 1) / (self.answered.get(kind, 0) + 2)

    def record(self, kind: str, correct: bool) -> None:
        self.answered[kind] = self.answered.get(kind, 0) + 1
        self.correct[kind] = self.correct.get(kind, 0) + int(correct)


@dataclass
class Advice:
    advice_id: str
    moves: list[dict[str, dict[str, int]]]
    before: float
    after: float
    reason: str
    signature: tuple[tuple[str, Cell, str], ...]


def _probability(sq: Square, accuracy: Accuracy, fill: float) -> float:
    if sq.state in GOOD:
        return 1.0
    if sq.state in LOST:
        return 0.0
    if sq.state == "empty_blank":
        return fill * accuracy.of("live")
    return accuracy.of(sq.kind)


class _Sim:
    def __init__(self, board: Board, accuracy: Accuracy, lives_to_come: int) -> None:
        self.board = board
        self.squares = board.squares
        empty = sum(1 for s in self.squares if s.state == "empty_blank")
        fill = min(1.0, lives_to_come / empty) if empty else 0.0
        p = np.array([_probability(s, accuracy, fill) for s in self.squares])
        rng = np.random.default_rng(len(board.scored_lines) * 7919 + 2610)
        self.success = rng.random((SIMULATIONS, len(self.squares))) < p
        self.open_lines = np.array([LINE_CELLS[line] for line in LINES
                                    if line not in board.scored_lines]).reshape(-1, 5)
        self.index = {s.id: i for i, s in enumerate(self.squares)}

    def arrangement(self) -> np.ndarray:
        at = np.zeros(25, dtype=int)
        for i, s in enumerate(self.squares):
            at[s.cell[0] * 5 + s.cell[1]] = i
        return at

    def chance(self, at: np.ndarray) -> float:
        if not len(self.open_lines):
            return 0.0
        by_cell = self.success[:, at]
        return float(by_cell[:, self.open_lines].all(axis=2).any(axis=1).mean())


def _legal_swaps(board: Board, at: np.ndarray) -> list[tuple[int, int]]:
    """(from cell index, to cell index) pairs a viewer could make right now."""
    squares = board.squares
    swaps = []
    for a in range(25):
        source = squares[at[a]]
        if not source.is_blank_like or _locked(board, a):
            continue
        for b in range(25):
            target = squares[at[b]]
            if b != a and not _locked(board, b) and Scorekeeper.can_take(target):
                swaps.append((a, b))
    return swaps


def _locked(board: Board, cell_index: int) -> bool:
    return any(cell_index in LINE_CELLS[line] for line in board.scored_lines)


def _swap(at: np.ndarray, a: int, b: int) -> np.ndarray:
    out = at.copy()
    out[a], out[b] = at[b], at[a]
    return out


def win_chance(board: Board, accuracy: Accuracy, lives_to_come: int) -> float:
    sim = _Sim(board, accuracy, lives_to_come)
    return sim.chance(sim.arrangement())


def suggest(board: Board, accuracy: Accuracy, lives_to_come: int,
            min_gain: float = MIN_GAIN) -> Advice | None:
    """Try every single swap and the best pairs; return the best if it gains enough."""
    sim = _Sim(board, accuracy, lives_to_come)
    start = sim.arrangement()
    before = sim.chance(start)
    singles = sorted(((sim.chance(_swap(start, a, b)), (a, b))
                      for a, b in _legal_swaps(board, start)), key=lambda x: -x[0])
    best_chance, best_moves = before, []
    if singles and singles[0][0] > best_chance:
        best_chance, best_moves = singles[0][0], [singles[0][1]]
    for (_, first), (_, second) in itertools.combinations(singles[:PAIR_FROM], 2):
        if first[0] in second or first[1] in second:
            continue                                   # pairs move two different squares
        chance = sim.chance(_swap(_swap(start, *first), *second))
        if chance > best_chance + 1e-9:
            best_chance, best_moves = chance, [first, second]
    if best_chance - before < min_gain - 1e-9:
        return None
    moves = [{"from_cell": _cell(a), "to_cell": _cell(b)} for a, b in best_moves]
    return Advice(uuid.uuid4().hex[:12], moves, round(before, 3), round(best_chance, 3),
                  _reason(board, start, best_moves, sim), signature(board))


def rank_blanks(board: Board, accuracy: Accuracy, lives_to_come: int) -> Square:
    """The empty blank where a new live square raises the win chance most (spec 4.7)."""
    empty = [s for s in board.squares if s.state == "empty_blank"]
    best, best_chance = empty[0], -1.0
    for sq in empty:
        sq.state = "open"
        chance = win_chance(board, accuracy, lives_to_come - 1)
        sq.state = "empty_blank"
        if chance > best_chance + 1e-9:
            best, best_chance = sq, chance
    return best


def signature(board: Board) -> tuple[tuple[str, Cell, str], ...]:
    return tuple((s.id, s.cell, s.state) for s in board.squares)


def _cell(index: int) -> dict[str, int]:
    return {"row": index // 5, "col": index % 5}


LINE_NAMES = {"row": "row {n}", "col": "column {n}"}


def _line_name(line: str) -> str:
    kind, n = line.split(":")
    if kind == "diag":
        return "the diagonal" if n == "0" else "the other diagonal"
    return LINE_NAMES[kind].format(n=int(n) + 1)


def _reason(board: Board, start: np.ndarray, moves: list[tuple[int, int]], sim: _Sim) -> str:
    """Template reason; the strategist agent writes the real one in phase 6."""
    at = start
    for a, b in moves:
        at = _swap(at, a, b)
    landing = moves[0][1]
    moved = board.squares[start[moves[0][0]]]
    lines = [line for line, cells in LINE_CELLS.items()
             if landing in cells and line not in board.scored_lines]
    if not lines:
        return "Moved a square to raise your chance of a line."
    best = max(lines, key=lambda line: sum(board.squares[at[c]].state in GOOD
                                           for c in LINE_CELLS[line]))
    good = sum(board.squares[at[c]].state in GOOD for c in LINE_CELLS[best])
    what = "wildcard" if moved.state == "wildcard" else "blank"
    if good == 5:
        return f"Moved a {what} into {_line_name(best)} to complete it."
    if good == 0:
        return f"Moved a {what} into {_line_name(best)}, a line with nothing lost yet."
    return f"Moved a {what} into {_line_name(best)}: {good} of its 5 squares are already correct."
