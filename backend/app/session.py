"""MatchSession (spec 8.3, 9.3): one replay per viewer, owned by a single asyncio task.

The task reads the ReplaySource stream, feeds the stats engine and the game, and pushes
frame, event, stats and card messages to every attached socket. Socket handlers only call
attach, detach and command, which run synchronously on the event loop, so nothing else writes
session state mid-update.
"""

import asyncio
import dataclasses
import json
import logging
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.engine.clock import ReplayClock
from app.engine.source import Frame, ReplaySource, Rewind, Tick
from app.game.card import Profile
from app.game.fans import FanLeague, leaderboard
from app.game.game import Game
from app.game.scorekeeper import Out
from app.models import (
    AnswerSubmit,
    BoardMove,
    DevJump,
    DevPause,
    ProfileSet,
    ReplaySpeed,
    StrategyApply,
    client_message,
    message,
)
from app.stats.engine import StatsEngine

log = logging.getLogger(__name__)

IDLE_CLOSE_S = 600.0     # close a session with no socket for 10 minutes
STATS_EVERY_S = 1.0      # stats go out on change, and at least once a second
CATCH_UP_S = 3.0         # events further behind the clock than this were jumped over
END_POLL_S = 0.25
LEADERBOARD_EVERY_S = 1.0


def planted_segments(folder: Path) -> frozenset[int]:
    """Segments whose planted moment the live-square producer waits for (spec 4.11)."""
    summary = folder / "summary.json"
    if not summary.is_file():
        return frozenset()
    return frozenset(p["segment"] for p in json.loads(summary.read_text()).get("planted", []))


class MatchSession:
    def __init__(self, seed: int, profile: dict[str, Any]) -> None:
        self.id = uuid.uuid4().hex
        self.seed = seed
        self.clock = ReplayClock(running=False)  # kickoff waits for the first socket
        self.source = ReplaySource(seed, self.clock)
        self.meta = self.source.metadata()
        self.profile = Profile.parse(profile, self.meta)   # ValueError for unknown ids
        self.planted = planted_segments(self.source.folder)
        self.stats = StatsEngine(self.meta)
        self._new_game()
        self.position = 0.0
        self.task: asyncio.Task[None] | None = None
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._started = asyncio.Event()
        self._last_socket = time.monotonic()
        self._frame: Frame | None = None
        self._frame_sent = True
        self._stats_dirty = True
        self._stats_sent_at = 0.0
        self._leaderboard_sent_at = 0.0

    def _new_game(self) -> None:
        self.game = Game(self.meta, self.profile, planted=self.planted)
        self.fans = FanLeague(self.meta, self.profile.mode, planted=self.planted)
        self._leaderboard_dirty = True

    # ---- called by socket handlers ---------------------------------------------------

    def attach(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for msg in self._opening():
            queue.put_nowait(msg)
        self._queues.add(queue)
        if not self._started.is_set():
            self.clock.start()
            self._started.set()
        return queue

    def detach(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)
        self._last_socket = time.monotonic()

    def ready(self) -> dict[str, Any]:
        return message("session.ready", self.clock.t(), session_id=self.id, match=self.meta,
                       profile=self.profile.public(), card=self.game.board.view(),
                       speed=self.clock.speed, paused=self.clock.paused and self._started.is_set(),
                       duration=self.source.duration)

    def _opening(self) -> list[dict[str, Any]]:
        """session.ready, then the masks that run from kickoff and the leaderboard."""
        t = self.clock.t()
        return [self.ready(), *(self._wrap(m, t) for m in self.game.initial_messages()),
                self._leaderboard_message()]

    def command(self, raw: Any) -> None:
        try:
            msg = client_message.validate_python(raw)
        except ValidationError as error:
            log.warning("session %s ignored a message: %s", self.id, error.errors()[:1])
            return
        if isinstance(msg, ReplaySpeed):
            self.clock.set_speed(msg.speed)
        elif isinstance(msg, AnswerSubmit):
            self._send(self.game.answer(msg.square_id, msg.value))
        elif isinstance(msg, BoardMove):
            self._send(self.game.move(msg.from_cell, msg.to_cell))
        elif isinstance(msg, StrategyApply):
            self._send(self.game.apply_advice(msg.advice_id))
        elif isinstance(msg, ProfileSet):
            changes = {k: v for k, v in msg.model_dump(exclude={"type"}).items() if v is not None}
            self.profile = dataclasses.replace(self.profile, **changes)
            self.game.profile = self.profile
            self._leaderboard_dirty = True
        elif not settings.dev_panel:
            log.warning("session %s ignored %s: the dev panel is off", self.id, msg.type)
        elif isinstance(msg, DevPause):
            self.clock.pause(msg.on)
            self.game.pause(msg.on)
            self.fans.pause(msg.on)
        elif isinstance(msg, DevJump):
            self.clock.jump(min(msg.t, self.source.duration))

    # ---- the session task ------------------------------------------------------------

    def start(self, on_close: "Callable[[MatchSession], object] | None" = None) -> None:
        self.task = asyncio.create_task(self._run(on_close))

    async def _run(self, on_close: "Callable[[MatchSession], object] | None") -> None:
        try:
            await asyncio.wait_for(self._started.wait(), IDLE_CLOSE_S)
            while not self._idle():
                await self._replay()
                self._send_stats()
                # Full time: keep the session for a dev jump back, until it goes idle. Windows
                # still open at full time run to their 20 seconds (spec 4.4).
                generation = self.clock.generation
                while self.clock.generation == generation and not self._idle():
                    await asyncio.sleep(END_POLL_S)
                    self._tick_game()
                if self.clock.t() < self.position:
                    self._reset()
        except TimeoutError:
            pass
        finally:
            if on_close is not None:
                on_close(self)

    async def _replay(self) -> None:
        async for item in self.source.stream():
            if isinstance(item, Tick):
                self._tick()
                if self._idle():
                    return
            elif isinstance(item, Rewind):
                self._reset(rewound=True)
            elif isinstance(item, Frame):
                self.stats.on_frame(item)
                self.position = item.t
                self._frame, self._frame_sent = item, False
            else:
                result = self.stats.on_event(item)
                self.position = item["t"]
                self._stats_dirty = True
                live = item["t"] >= self.clock.t() - CATCH_UP_S
                out = self.game.on_event(item, result.significance, live)
                if self.fans.on_event(item, result.significance, live):
                    self._leaderboard_dirty = True
                if live:
                    # Asked after the game took the event, so an event that opens a window
                    # is held by it (spec 4.9).
                    held = self.game.hold(item)
                    self._broadcast(message("event", item["t"], event=item,
                                            significance=result.significance, held=held))
                self._send(out)

    def _reset(self, rewound: bool = False) -> None:
        """A jump back replays from kickoff with a fresh card (dev panel only)."""
        if not rewound:
            self.source.rewind()
        self.stats = StatsEngine(self.meta)
        self.position = 0.0
        self._stats_dirty = True
        self._new_game()
        if self.clock.paused:
            self.game.pause(True)
            self.fans.pause(True)
        for msg in self._opening():
            self._broadcast(msg)

    def _tick(self) -> None:
        self._tick_game()
        frame = self._frame
        if frame is not None and not self._frame_sent:
            self._frame_sent = True
            self._broadcast(message(
                "frame", frame.t, ball=list(frame.ball),
                players=[[pid, round(x, 2), round(y, 2)] for pid, x, y in frame.players]))
        if self._stats_dirty or time.monotonic() - self._stats_sent_at >= STATS_EVERY_S:
            self._send_stats()

    def _send_stats(self) -> None:
        self._stats_dirty = False
        self._stats_sent_at = time.monotonic()
        snapshot = self.game.redact_stats(self.stats.snapshot())
        self._broadcast(message("stats", self.position, **snapshot))

    # ---- the game ------------------------------------------------------------------------

    def _tick_game(self) -> None:
        t = max(self.position, min(self.clock.t(), self.source.duration))
        self._send(self.game.on_tick(t))
        if self.fans.on_tick(t):
            self._leaderboard_dirty = True
        if self._leaderboard_dirty and \
                time.monotonic() - self._leaderboard_sent_at >= LEADERBOARD_EVERY_S:
            self._broadcast(self._leaderboard_message())

    def _wrap(self, msg: dict[str, Any], t: float) -> dict[str, Any]:
        return message(msg["type"], t, **{k: v for k, v in msg.items() if k != "type"})

    def _send(self, out: Out) -> None:
        t = self.game.t
        for msg in out:
            if msg["type"] in ("square.result", "board.update"):
                self._leaderboard_dirty = True
            self._broadcast(self._wrap(msg, t))

    def viewer_row(self) -> dict[str, Any]:
        board = self.game.board
        times = [s.answer["elapsed_s"] for s in board.squares if s.answer]
        return {"handle": self.profile.handle, "points": board.points, "correct": board.correct,
                "avg_answer_s": round(sum(times) / len(times), 1) if times else None}

    def _leaderboard_message(self) -> dict[str, Any]:
        self._leaderboard_dirty = False
        self._leaderboard_sent_at = time.monotonic()
        return message("leaderboard", self.game.t, mode=self.profile.mode,
                       rows=leaderboard(self.viewer_row(), self.fans.rows()))

    def state(self) -> dict[str, Any]:
        """Debug snapshot (GET /api/sessions/{id}/state). No correct answers before results."""
        return {"session_id": self.id, "seed": self.seed, "t": round(self.clock.t(), 2),
                "speed": self.clock.speed, "paused": self.clock.paused,
                "profile": self.profile.public(), "board": self.game.board.view(),
                "masked": sorted(self.game.masks.tags()), "full_time": self.game.full_time,
                "live_squares_to_come": len(self.game.live.needed),
                "leaderboard": leaderboard(self.viewer_row(), self.fans.rows())}

    def _broadcast(self, msg: dict[str, Any]) -> None:
        for queue in self._queues:
            queue.put_nowait(msg)

    def _idle(self) -> bool:
        return not self._queues and time.monotonic() - self._last_socket >= IDLE_CLOSE_S

    def close(self) -> None:
        if self.task is not None:
            self.task.cancel()


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, MatchSession] = {}

    def create(self, seed: int, profile: dict[str, Any]) -> MatchSession:
        session = MatchSession(seed, profile)
        self._sessions[session.id] = session
        session.start(on_close=lambda s: self._sessions.pop(s.id, None))
        return session

    def get(self, session_id: str) -> MatchSession | None:
        return self._sessions.get(session_id)

    def leaderboard(self, mode: str) -> list[dict[str, Any]]:
        """One row per real session in a mode (spec 9.7); simulated fans stay per session."""
        rows = [{**s.viewer_row(), "match_id": s.meta["match_id"]}
                for s in self._sessions.values() if s.profile.mode == mode]
        rows.sort(key=lambda r: (-r["points"], -r["correct"]))
        return [{**row, "rank": i + 1} for i, row in enumerate(rows)]

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()


sessions = SessionRegistry()
