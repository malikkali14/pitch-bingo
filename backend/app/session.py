"""MatchSession (spec 8.3, 9.3): one replay per viewer, owned by a single asyncio task.

The task reads the ReplaySource stream, feeds the stats engine, and pushes frame, event and
stats messages to every attached socket. Socket handlers only call attach, detach and command,
which run synchronously on the event loop, so nothing else writes session state mid-update.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.engine.clock import ReplayClock
from app.engine.source import Frame, ReplaySource, Rewind, Tick
from app.models import DevJump, DevPause, ReplaySpeed, client_message, message
from app.stats.engine import StatsEngine

log = logging.getLogger(__name__)

IDLE_CLOSE_S = 600.0     # close a session with no socket for 10 minutes
STATS_EVERY_S = 1.0      # stats go out on change, and at least once a second
CATCH_UP_S = 3.0         # events further behind the clock than this were jumped over
END_POLL_S = 0.25


class MatchSession:
    def __init__(self, seed: int, profile: dict[str, Any]) -> None:
        self.id = uuid.uuid4().hex
        self.seed = seed
        self.profile = profile
        self.clock = ReplayClock(running=False)  # kickoff waits for the first socket
        self.source = ReplaySource(seed, self.clock)
        self.meta = self.source.metadata()
        self.stats = StatsEngine(self.meta)
        self.position = 0.0
        self.task: asyncio.Task[None] | None = None
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._started = asyncio.Event()
        self._last_socket = time.monotonic()
        self._frame: Frame | None = None
        self._frame_sent = True
        self._stats_dirty = True
        self._stats_sent_at = 0.0

    # ---- called by socket handlers ---------------------------------------------------

    def attach(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        queue.put_nowait(self.ready())
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
                       profile=self.profile, card=None, speed=self.clock.speed,
                       paused=self.clock.paused and self._started.is_set(),
                       duration=self.source.duration)

    def command(self, raw: Any) -> None:
        try:
            msg = client_message.validate_python(raw)
        except ValidationError as error:
            log.warning("session %s ignored a message: %s", self.id, error.errors()[:1])
            return
        if isinstance(msg, ReplaySpeed):
            self.clock.set_speed(msg.speed)
        elif not settings.dev_panel:
            log.warning("session %s ignored %s: the dev panel is off", self.id, msg.type)
        elif isinstance(msg, DevPause):
            self.clock.pause(msg.on)
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
                # Full time: keep the session for a dev jump back, until it goes idle.
                generation = self.clock.generation
                while self.clock.generation == generation and not self._idle():
                    await asyncio.sleep(END_POLL_S)
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
                if item["t"] >= self.clock.t() - CATCH_UP_S:
                    self._broadcast(message("event", item["t"], event=item,
                                            significance=result.significance))

    def _reset(self, rewound: bool = False) -> None:
        if not rewound:
            self.source.rewind()
        self.stats = StatsEngine(self.meta)
        self.position = 0.0
        self._stats_dirty = True

    def _tick(self) -> None:
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
        self._broadcast(message("stats", self.position, **self.stats.snapshot()))

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

    def close_all(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()


sessions = SessionRegistry()
