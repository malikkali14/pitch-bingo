"""Scorekeeper (spec 4.4 to 4.8): windows, answers, results, lines and points for one card.

Windows run on wall-clock time (WindowClock), whatever the replay speed; the dev pause
freezes them. Every public method returns the messages to send, as dicts with a type and a
payload; the game adds t and wall.
"""

import time
from collections.abc import Callable
from typing import Any

from app.game.card import Board, Square
from app.game.scoring import LIVE_BASE, STATIC_BASE, check_lines, speed_points

WINDOW_S = 20.0
Out = list[dict[str, Any]]


class WindowClock:
    """Wall seconds that stand still while the dev panel pauses the match."""

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._paused_at: float | None = None
        self._offset = 0.0

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def t(self) -> float:
        base = self._paused_at if self._paused_at is not None else self._now()
        return base - self._offset

    def pause(self, on: bool) -> None:
        if on and self._paused_at is None:
            self._paused_at = self._now()
        elif not on and self._paused_at is not None:
            self._offset += self._now() - self._paused_at
            self._paused_at = None


def error(request: str, reason: str) -> dict[str, Any]:
    return {"type": "error", "request": request, "reason": reason}


class Scorekeeper:
    def __init__(self, board: Board, clock: WindowClock, wall_ms: Callable[[], int],
                 valid_players: set[str], label: Callable[[Square, str | None], str]) -> None:
        self.board = board
        self.clock = clock
        self.wall_ms = wall_ms
        self.valid_players = valid_players
        self.label = label
        self.lines_scored: list[dict[str, Any]] = []
        self.on_result: list[Callable[[Square], None]] = []   # e.g. the strategist's accuracy

    # ---- windows -----------------------------------------------------------------------

    def open(self, sq: Square, correct: str, evidence: list[str], t: float,
             skip: bool = False) -> Out:
        sq.correct_answer, sq.evidence, sq.open_t = correct, evidence, t
        if sq.state != "waiting":
            # A first-to-happen square answered too early: no window to answer in, but its
            # masks still run their 20 seconds from the event (spec 4.9).
            self._start(sq, skip)
            return self.tick() if skip else []
        sq.state = "open"
        self._start(sq, skip)
        if skip:
            return self.tick()                     # jumping skips windows: straight to missed
        out: Out = []
        if sq.announced:
            out.append({"type": "square.window_open", "square_id": sq.id,
                        "closes_at": sq.closes_wall_ms})
            if sq.masks:
                out.append({"type": "mask.on", "square_id": sq.id, "tags": list(sq.masks)})
        return out

    def _start(self, sq: Square, skip: bool) -> None:
        now = self.clock.t()
        sq.window = True
        sq.opened_at = now
        sq.closes_at = now if skip else now + WINDOW_S
        sq.closes_wall_ms = self.wall_ms() + (0 if skip else round(WINDOW_S * 1000))

    def tick(self) -> Out:
        out: Out = []
        now = self.clock.t()
        for sq in self.board.squares:
            if sq.window and sq.closes_at is not None and now >= sq.closes_at:
                out += self._close(sq)
        return out

    def _close(self, sq: Square) -> Out:
        sq.window = False
        sq.closes_wall_ms = None
        out: Out = []
        if sq.state == "open":
            sq.state = "missed"
            sq.result = {"status": "missed", "points": 0, "explanation": "",
                         "evidence_event_ids": list(sq.evidence)}
            out.append(self._result_message(sq))
        if sq.masks:
            out.append({"type": "mask.off", "square_id": sq.id, "tags": list(sq.masks)})
        text = self.explanation(sq)
        if sq.result is not None:
            sq.result["explanation"] = text
        out.append({"type": "square.explanation", "square_id": sq.id, "text": text})
        if sq.state == "missed":
            out += self._after_change(sq)
        return out

    def explanation(self, sq: Square) -> str:
        """Template explanation; the rules tutor or narrator replaces it in phase 6."""
        answer = self.label(sq, sq.correct_answer)
        return f"{sq.text.get('en', '')} Answer: {answer}."

    def void(self, sq: Square) -> Out:
        """A first-to-happen event that never happened by full time (spec 4.3)."""
        sq.state = "void"
        sq.result = {"status": "void", "points": 0,
                     "explanation": "It didn't happen this match.", "evidence_event_ids": []}
        out = [self._result_message(sq)]
        if sq.masks:
            out.append({"type": "mask.off", "square_id": sq.id, "tags": list(sq.masks)})
        return out + self._after_change(sq)

    # ---- answers -----------------------------------------------------------------------

    def normalize(self, sq: Square, value: Any) -> str | None:
        text = str(value).strip()
        if sq.answer_type == "player":
            return text if text in self.valid_players else None
        if sq.answer_type == "yesno":
            text = text.lower()
        if sq.options:
            return text if text in sq.options else None
        if sq.answer_type == "number":
            try:
                number = int(text)
            except ValueError:
                return None
            return str(number) if number >= 0 else None
        return None

    def answer(self, square_id: str, value: Any, t: float) -> Out:
        sq = self.board.get(square_id)
        if sq is None or sq.state == "empty_blank":
            return [error("answer.submit", "no such square")]
        if sq.answer is not None:
            return [error("answer.submit", "already answered")]
        normalized = self.normalize(sq, value)
        if normalized is None:
            return [error("answer.submit", "not a valid answer for this square")]
        if sq.state == "waiting" and sq.kind == "first":
            return self._judge(sq, normalized, t, too_early=True)
        if sq.state != "open":
            reason = "window not open yet" if sq.state == "waiting" else "window closed"
            return [error("answer.submit", reason)]
        return self._judge(sq, normalized, t)

    def _judge(self, sq: Square, value: str, t: float, too_early: bool = False) -> Out:
        now = self.clock.t()
        elapsed = 0.0 if too_early or sq.opened_at is None else max(0.0, now - sq.opened_at)
        sq.answer = {"value": value, "wall_ms": self.wall_ms(), "t": round(t, 2),
                     "elapsed_s": round(elapsed, 2)}
        if too_early:
            status, points = "too_early", 0
        elif value == sq.correct_answer:
            status = "correct"
            points = speed_points(LIVE_BASE if sq.kind == "live" else STATIC_BASE, elapsed)
        else:
            status, points = "wrong", 0
        sq.state = "wildcard" if status == "correct" and sq.kind == "live" else status
        sq.result = {"status": status, "points": points, "explanation": "",
                     "evidence_event_ids": list(sq.evidence)}
        return [self._result_message(sq)] + self._after_change(sq)

    def _result_message(self, sq: Square) -> dict[str, Any]:
        assert sq.result is not None
        reveal = sq.result["status"] not in ("too_early", "void")
        return {"type": "square.result", "square_id": sq.id, "status": sq.result["status"],
                "points": sq.result["points"],
                "correct_answer": sq.correct_answer if reveal else None}

    # ---- lines ---------------------------------------------------------------------------

    def _after_change(self, sq: Square | None = None) -> Out:
        if sq is not None:
            for hook in self.on_result:
                hook(sq)
        return self.board_changed()

    def board_changed(self) -> Out:
        lines, full = check_lines(self.board)
        out: Out = []
        for line in lines:
            row = {"line": line.line, "points": line.points, "blank_slate": line.blank_slate}
            self.lines_scored.append(row)
            out.append({"type": "board.line", **row})
        if full:
            out.append({"type": "board.full_card", "points": full})
        out.append({"type": "board.update", **self.board.view()})
        return out

    # ---- queries -------------------------------------------------------------------------

    def announced_open(self) -> bool:
        return any(s.window and s.announced for s in self.board.squares)
