"""Helpers for game tests: a fake wall clock and a game built on seed 2610's metadata."""

from typing import Any

from factories import HOME, Log, load_meta

from app.game.card import Profile, Square
from app.game.game import Game

META = load_meta()


class FakeTime:
    def __init__(self) -> None:
        self.s = 0.0

    def now(self) -> float:
        return self.s

    def wall_ms(self) -> int:
        return 1_000_000 + round(self.s * 1000)

    def advance(self, seconds: float) -> None:
        self.s += seconds


def new_game(mode: str = "advanced", **profile: Any) -> tuple[Game, FakeTime, Log]:
    clock = FakeTime()
    game = Game(META, Profile.parse({"mode": mode, **profile}, META), now=clock.now,
                wall_ms=clock.wall_ms)
    return game, clock, Log()


def square(game: Game, template: str) -> Square:
    return next(s for s in game.board.squares if s.template == template)


def types(out: list[dict[str, Any]]) -> list[str]:
    return [m["type"] for m in out]


def of(out: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    return [m for m in out if m["type"] == type_]


def kickoff(game: Game, log: Log) -> list[dict[str, Any]]:
    out = game.on_event(log.add("period_start", 0.0, team=None))
    return out + game.on_event(log.add("kickoff", 0.0, team=HOME))


def second_half(game: Game, log: Log, t: float = 2880.0) -> None:
    game.on_event(log.add("period_end", t, team=None, stoppage_added_s=int(t - 2700)))
    game.on_event(log.add("period_start", t, team=None, period=2, clock="45:00"))
