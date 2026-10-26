"""Match data ingest (spec 6.10): one EventSource interface, and ReplaySource for seed files.

stream() yields, in time order, raw events (plain dicts, exactly as in events.jsonl) and
position Frames. Between bursts it yields a Tick, ten times per wall second at every speed, so
a consumer knows when to push the latest frame and stats. After a backward jump of the clock
it yields a Rewind and replays from kickoff, so consumers can rebuild their state.
"""

import asyncio
import json
import math
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np

from app.engine.clock import ReplayClock

MATCHES_DIR = Path(__file__).resolve().parents[3] / "data" / "matches"
TICK_S = 0.1
YIELD_EVERY = 2000  # items per catch-up burst before giving the event loop a turn


@dataclass(frozen=True)
class Frame:
    t: float
    index: int
    ball: tuple[float, float, float]  # tracking has no height yet, so z is always 0
    players: list[tuple[str, float, float]]  # sent-off players are left out


@dataclass(frozen=True)
class Tick:
    t: float


@dataclass(frozen=True)
class Rewind:
    t: float


Item = dict[str, Any] | Frame | Tick | Rewind


@runtime_checkable
class EventSource(Protocol):
    def metadata(self) -> dict[str, Any]: ...

    def stream(self) -> AsyncIterator[Item]: ...


@dataclass(frozen=True)
class MatchData:
    meta: dict[str, Any]
    events: list[dict[str, Any]]
    positions: np.ndarray  # int16 (frames, 23, 2) in decimetres
    slot_ids: list[str]
    hz: int


def available_seeds(matches_dir: Path = MATCHES_DIR) -> list[int]:
    return sorted(int(p.name) for p in matches_dir.iterdir()
                  if p.name.isdigit() and (p / "events.jsonl").is_file())


@lru_cache(maxsize=8)
def load_match(folder: Path) -> MatchData:
    if not (folder / "events.jsonl").is_file():
        raise FileNotFoundError(f"no match files in {folder}")
    meta = json.loads((folder / "match.json").read_text())
    with (folder / "events.jsonl").open() as f:
        events = [json.loads(line) for line in f]
    with np.load(folder / "tracking.npz") as tracking:
        positions = tracking["positions"]
        slot_ids = [str(s) for s in tracking["slot_ids"]]
        hz = int(tracking["hz"])
    return MatchData(meta, events, positions, slot_ids, hz)


class ReplaySource:
    """Replays one seed's files at the speed of the given clock."""

    def __init__(self, seed: int, clock: ReplayClock, matches_dir: Path = MATCHES_DIR) -> None:
        self.folder = matches_dir / str(seed)
        self.data = load_match(self.folder)
        self.clock = clock
        self.duration = max(self.data.events[-1]["t"],
                            (len(self.data.positions) - 1) / self.data.hz)
        self.rewind()

    def metadata(self) -> dict[str, Any]:
        return self.data.meta

    def rewind(self) -> None:
        self._event_i = 0
        self._frame_i = 0
        self._slots = list(self.data.slot_ids)
        self._slot_of = {pid: i for i, pid in enumerate(self._slots)}
        self.position = -math.inf  # match time of the last item handed out

    @property
    def done(self) -> bool:
        return (self._event_i >= len(self.data.events)
                and self._frame_i >= len(self.data.positions))

    def next_time(self) -> float:
        times = []
        if self._event_i < len(self.data.events):
            times.append(self.data.events[self._event_i]["t"])
        if self._frame_i < len(self.data.positions):
            times.append(self._frame_i / self.data.hz)
        return min(times, default=math.inf)

    def items_until(self, t: float) -> Iterator[dict[str, Any] | Frame]:
        """Every event and frame up to match time t, in order, without pacing."""
        events, positions, hz = self.data.events, self.data.positions, self.data.hz
        while True:
            event_t = events[self._event_i]["t"] if self._event_i < len(events) else math.inf
            frame_t = self._frame_i / hz if self._frame_i < len(positions) else math.inf
            if min(event_t, frame_t) > t or event_t == frame_t == math.inf:
                return
            if event_t <= frame_t:
                event = events[self._event_i]
                self._event_i += 1
                self.position = event_t
                if event["type"] == "substitution":
                    self._substitute(event["player_off_id"], event["player_on_id"])
                yield event
            else:
                frame = self._frame(self._frame_i)
                self._frame_i += 1
                self.position = frame_t
                yield frame

    def _substitute(self, off: str, on: str) -> None:
        slot = self._slot_of.pop(off, None)
        if slot is not None:
            self._slots[slot] = on
            self._slot_of[on] = slot

    def _frame(self, index: int) -> Frame:
        rows = self.data.positions[index].tolist()
        players = [(pid, x / 10, y / 10) for pid, (x, y) in zip(self._slots, rows, strict=False)
                   if x >= 0]
        bx, by = rows[22]
        return Frame(t=index / self.data.hz, index=index, ball=(bx / 10, by / 10, 0.0),
                     players=players)

    async def stream(self) -> AsyncIterator[Item]:
        generation = self.clock.generation
        next_tick = time.monotonic()
        while True:
            if self.clock.generation != generation:
                generation = self.clock.generation
                if self.clock.t() < self.position:
                    self.rewind()
                    yield Rewind(self.clock.t())
            now = self.clock.t()
            for n, item in enumerate(self.items_until(now), 1):
                yield item
                if n % YIELD_EVERY == 0:
                    await asyncio.sleep(0)
            yield Tick(now)
            if self.done:
                return
            next_tick += TICK_S
            delay = next_tick - time.monotonic()
            if delay < 0:  # fell behind (a long catch-up): don't burst to make up ticks
                next_tick, delay = time.monotonic(), 0.0
            await asyncio.sleep(delay)
