"""Simulated fans for the leaderboard (spec 3, 8.1).

Twenty fans per mode. Each has an accuracy, a typical answer time and a chance of noticing a
silent first-to-happen window, and plays a neutral card through its own scorekeeper. One
reference game (a neutral viewer in that mode) decides when windows open and what the right
answers are, so fans see exactly the windows a real viewer sees. A fan's answer is decided
when its window opens, so its points land then rather than a few seconds later.
"""

import copy
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.game.card import Board, Profile, Square
from app.game.game import Game
from app.game.scorekeeper import WINDOW_S, Scorekeeper, WindowClock
from app.models import wall_ms as server_wall_ms

FAN_COUNT = 20
ANSWER_RATE = 0.95            # announced windows: fans nearly always answer
FIRST = ["Blue", "Red", "Green", "Golden", "Silver", "North", "Kestrel", "River", "Iron",
         "Stand", "Terrace", "Old", "Loyal", "Lucky", "Proud", "Quiet", "Wild", "Early"]
SECOND = ["Scarf", "Bench", "Whistle", "Corner", "Header", "Volley", "Keeper", "Winger",
          "Striker", "Chant", "Season", "Flag", "Boot", "Pitch", "Net", "Derby"]
LIVE_FIELDS = ("template", "text", "answer_type", "options", "option_labels", "masks",
               "source_event_ids", "resolver", "kind")


class FanClock(WindowClock):
    """Window seconds a fan's scorekeeper reads: set by hand, since answers are simulated."""

    def __init__(self) -> None:
        super().__init__()
        self.now_s = 0.0

    def t(self) -> float:
        return self.now_s


@dataclass
class Fan:
    handle: str
    accuracy: float
    answer_s: float           # typical answer time
    notice: float             # chance of spotting a silent first-to-happen window
    board: Board
    keeper: Scorekeeper
    clock: FanClock

    def row(self) -> dict[str, Any]:
        times = [s.answer["elapsed_s"] for s in self.board.squares if s.answer]
        return {"handle": self.handle, "points": self.board.points, "correct": self.board.correct,
                "avg_answer_s": round(sum(times) / len(times), 1) if times else None}


class FanLeague:
    def __init__(self, meta: dict[str, Any], mode: str,
                 now: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = server_wall_ms,
                 planted: frozenset[int] = frozenset()) -> None:
        self.mode = mode
        self.reference = Game(meta, Profile(mode=mode, strategist="manual"), now=now,
                              wall_ms=wall_ms, planted=planted)
        self.players = sorted(self.reference.players)
        self.rng = random.Random(f"fans:{meta['seed']}:{mode}")
        handles: list[str] = []
        while len(handles) < FAN_COUNT:
            handle = (f"{self.rng.choice(FIRST)}{self.rng.choice(SECOND)}_"
                      f"{self.rng.randint(10, 99)}")
            if handle not in handles:
                handles.append(handle)
        self.fans = [self._fan(handle, wall_ms) for handle in handles]
        self.opened: set[str] = set()
        self.voided: set[str] = set()

    def _fan(self, handle: str, wall_ms: Callable[[], int]) -> Fan:
        board = copy.deepcopy(self.reference.board)
        clock = FanClock()
        keeper = Scorekeeper(board, clock, wall_ms, set(self.players),
                             lambda sq, value: str(value))
        return Fan(handle, round(self.rng.uniform(0.35, 0.8), 2),
                   round(self.rng.uniform(3.0, 12.0), 1), round(self.rng.uniform(0.3, 0.9), 2),
                   board, keeper, clock)

    # ---- driven by the session, alongside the viewer's game -------------------------------

    def on_event(self, event: dict[str, Any], significance: int = 0, live: bool = True) -> bool:
        self.reference.on_event(event, significance, live)
        return self._mirror()

    def on_tick(self, t: float) -> bool:
        self.reference.on_tick(t)
        return self._mirror()

    def pause(self, on: bool) -> None:
        self.reference.pause(on)

    def _mirror(self) -> bool:
        """Play every window the reference game opened since last time. True if any fan's
        board changed."""
        changed = False
        for sq in self.reference.board.squares:
            if sq.state == "void" and sq.id not in self.voided:
                self.voided.add(sq.id)
                for fan in self.fans:
                    fan.keeper.void(fan.board.get(sq.id) or sq)
                changed = True
            if sq.opened_at is None or sq.id in self.opened or sq.correct_answer is None:
                continue
            self.opened.add(sq.id)
            skipped = sq.closes_at == sq.opened_at
            for fan in self.fans:
                mine = fan.board.get(sq.id)
                assert mine is not None
                if sq.kind == "live" and mine.state == "empty_blank":
                    for name in LIVE_FIELDS:
                        setattr(mine, name, copy.deepcopy(getattr(sq, name)))
                    mine.state = "waiting"
                self._play(fan, mine, sq.correct_answer, skipped)
            changed = True
        return changed

    def _play(self, fan: Fan, sq: Square, correct: str, skipped: bool) -> None:
        fan.clock.now_s = 0.0
        fan.keeper.open(sq, correct, [], 0.0)
        rate = fan.notice if sq.kind == "first" else ANSWER_RATE
        if not skipped and self.rng.random() < rate:
            delay = min(19.5, max(0.5, self.rng.lognormvariate(0, 0.45) * fan.answer_s))
            right = self.rng.random() < fan.accuracy
            fan.clock.now_s = delay
            fan.keeper.answer(sq.id, correct if right else self._wrong(sq, correct), 0.0)
        fan.clock.now_s = WINDOW_S
        fan.keeper.tick()

    def _wrong(self, sq: Square, correct: str) -> str:
        if sq.options:
            return self.rng.choice([o for o in sq.options if o != correct])
        if sq.answer_type == "player":
            return self.rng.choice([p for p in self.players if p != correct])
        guesses = [n for n in range(int(correct) - 2, int(correct) + 3) if n >= 0 and
                   str(n) != correct]
        return str(self.rng.choice(guesses))

    def rows(self) -> list[dict[str, Any]]:
        return sorted((fan.row() for fan in self.fans),
                      key=lambda r: (-r["points"], -r["correct"], r["handle"]))


def leaderboard(you: dict[str, Any], fans: list[dict[str, Any]], top: int = 5
                ) -> list[dict[str, Any]]:
    """Top five plus your row (spec 3), ranked by points, then correct answers."""
    rows = [{**row, "you": False} for row in fans] + [{**you, "you": True}]
    rows.sort(key=lambda r: (-r["points"], -r["correct"], not r["you"]))
    ranked = [{**row, "rank": i + 1} for i, row in enumerate(rows)]
    shown = ranked[:top]
    mine = next(r for r in ranked if r["you"])
    return shown if mine in shown else shown + [mine]
