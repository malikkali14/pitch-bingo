"""Replay clock (spec 9.2): match time t = t0 + (now - wall0) x speed."""

import time
from collections.abc import Callable

SPEEDS = (1, 5, 10)


class ReplayClock:
    """Maps wall time to match seconds. Speed changes, pauses and jumps re-anchor t0 and wall0."""

    def __init__(self, speed: float = 1, now: Callable[[], float] = time.monotonic,
                 running: bool = True, t: float = 0.0) -> None:
        self._check_speed(speed)
        self._now = now
        self.speed = speed
        self.paused = not running
        self.generation = 0  # bumped on every jump, so a stream knows to resync
        self._t0 = t
        self._wall0 = now()

    @staticmethod
    def _check_speed(speed: float) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}, got {speed}")

    def t(self) -> float:
        if self.paused:
            return self._t0
        return self._t0 + (self._now() - self._wall0) * self.speed

    def _anchor(self, t: float) -> None:
        self._t0 = t
        self._wall0 = self._now()

    def set_speed(self, speed: float) -> None:
        self._check_speed(speed)
        self._anchor(self.t())
        self.speed = speed

    def pause(self, on: bool) -> None:
        self._anchor(self.t())
        self.paused = on

    def start(self) -> None:
        self.pause(False)

    def jump(self, t: float) -> None:
        if t < 0:
            raise ValueError("cannot jump before kickoff")
        self._anchor(t)
        self.generation += 1

    def wall_delay(self, match_t: float) -> float | None:
        """Wall seconds until the clock reaches match_t, or None while paused."""
        if self.paused:
            return None
        return max(0.0, (match_t - self.t()) / self.speed)
