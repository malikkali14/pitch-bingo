"""Scoring and lines (spec 4.6, 4.8)."""

from dataclasses import dataclass

from app.game.card import GOOD, LINES, Board

STATIC_BASE = 100
LIVE_BASE = 150
FULL_S_AT, FLOOR, DROP, GRACE_S = 20.0, 0.3, 0.7, 3.0
FIRST_LINE, NEXT_LINE, BLANK_SLATE, FULL_CARD = 500, 250, 300, 2000


def speed_points(base: int, seconds: float) -> int:
    """Full base inside 3 seconds, falling linearly to 30% at 20 seconds."""
    factor = 1 - DROP * max(0.0, seconds - GRACE_S) / (FULL_S_AT - GRACE_S)
    return round(base * max(FLOOR, factor))


@dataclass(frozen=True)
class LineScore:
    line: str
    points: int
    blank_slate: bool


def check_lines(board: Board) -> tuple[list[LineScore], int]:
    """Score every newly completed line once, then the full card. Returns the new lines and
    the full-card bonus (0 if not newly earned). The caller freezes the scored lines."""
    found: list[LineScore] = []
    for line, cells in LINES.items():
        if line in board.scored_lines:
            continue
        squares = [board.at(cell) for cell in cells]
        if all(s.state in GOOD for s in squares):
            first = not board.scored_lines and not found
            blank_slate = all(s.kind == "live" for s in squares)
            points = (FIRST_LINE if first else NEXT_LINE) + (BLANK_SLATE if blank_slate else 0)
            found.append(LineScore(line, points, blank_slate))
            board.scored_lines.append(line)
            board.bonus_points += points
    full = 0
    if not board.full_card and all(s.state in GOOD for s in board.squares):
        board.full_card = True
        full = FULL_CARD
        board.bonus_points += full
    board.points = board.bonus_points + sum(
        s.result["points"] for s in board.squares if s.result)
    return found, full
