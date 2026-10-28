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
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app import telemetry
from app.agents import narrator, recap
from app.agents.clients import ChatClients, shared_clients
from app.agents.orchestrator import Orchestrator
from app.config import settings
from app.engine.clock import ReplayClock
from app.engine.source import Frame, ReplaySource, Rewind, Tick
from app.game import lang
from app.game.card import Profile
from app.game.fans import FanLeague, leaderboard
from app.game.game import Game
from app.game.scorekeeper import Out
from app.models import (
    AnswerSubmit,
    BoardMove,
    DefinitionRequest,
    DevJump,
    DevNarratorDown,
    DevPause,
    ProfileSet,
    RecapRequest,
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
HEALTH_EVERY_S = 2.0


def planted_segments(folder: Path) -> frozenset[int]:
    """Segments whose planted moment the live-square producer waits for (spec 4.11)."""
    summary = folder / "summary.json"
    if not summary.is_file():
        return frozenset()
    return frozenset(p["segment"] for p in json.loads(summary.read_text()).get("planted", []))


class MatchSession:
    def __init__(self, seed: int, profile: dict[str, Any],
                 clients: ChatClients | None = None) -> None:
        self.id = uuid.uuid4().hex
        self.seed = seed
        self.clock = ReplayClock(running=False)  # kickoff waits for the first socket
        self.source = ReplaySource(seed, self.clock)
        self.meta = self.source.metadata()
        self.profile = Profile.parse(profile, self.meta)   # ValueError for unknown ids
        self.planted = planted_segments(self.source.folder)
        self.stats = StatsEngine(self.meta)
        self.agents = Orchestrator(clients, self.meta, lambda: self.profile, self._publish,
                                   session_id=self.id)
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
        self._health_sent_at = 0.0
        self._event_times: deque[float] = deque(maxlen=2000)

    def _new_game(self) -> None:
        self.game = Game(self.meta, self.profile, planted=self.planted,
                         defer_live=self.agents.online)
        self.fans = FanLeague(self.meta, self.profile.mode, planted=self.planted)
        self._leaderboard_dirty = True

    # ---- called by socket handlers ---------------------------------------------------

    def attach(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for msg in self._opening():
            queue.put_nowait(msg)
        self._queues.add(queue)
        telemetry.instruments().sockets.add(1)
        if not self._started.is_set():
            self.clock.start()
            self._started.set()
        return queue

    def detach(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._queues:
            telemetry.instruments().sockets.add(-1)
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
        elif isinstance(msg, RecapRequest):
            self.agents.write_recap(self._recap_summary(msg.kind))
        elif isinstance(msg, DefinitionRequest):
            if not self.agents.define(msg.term):
                self._send([{"type": "error", "request": "definition.request",
                             "reason": f"no definition for {msg.term!r}"}])
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
            target = msg.t if msg.t is not None else self._minute_t(msg.minute or 0.0)
            self.clock.jump(min(target, self.source.duration))
        elif isinstance(msg, DevNarratorDown):
            self.agents.narrator_down(msg.on)
            self._send_health()

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
            self.agents.cancel()
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
                if live:
                    self._event_times.append(time.monotonic())
                out = self.game.on_event(item, result.significance, live)
                if self.fans.on_event(item, result.significance, live):
                    self._leaderboard_dirty = True
                if live:
                    # Asked after the game took the event, so an event that opens a window
                    # is held by it (spec 4.9).
                    held = self.game.hold(item)
                    self._broadcast(message("event", item["t"], event=item,
                                            significance=result.significance, held=held))
                    self.agents.on_event(
                        item, result.significance, result.triggers, result.milestones,
                        lambda: self.game.redact_stats(self.stats.snapshot()), held,
                        self.stats.core.last_xg if item["type"] == "shot" else None)
                    if item["type"] not in ("period_start", "period_end"):
                        self.agents.focus_update(item["t"], item["clock"], item["period"],
                                                 self.stats.snapshot)
                self._send(out)
                if live and item["type"] == "period_end":
                    self.agents.write_recap(self._recap_summary(
                        "halftime" if item["period"] == 1 else "full_time"))

    def _reset(self, rewound: bool = False) -> None:
        """A jump back replays from kickoff with a fresh card (dev panel only)."""
        if not rewound:
            self.source.rewind()
        self.stats = StatsEngine(self.meta)
        self.position = 0.0
        self._stats_dirty = True
        self.agents.cancel()
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
        if settings.dev_panel and time.monotonic() - self._health_sent_at >= HEALTH_EVERY_S:
            self._send_health()
        if self._leaderboard_dirty and \
                time.monotonic() - self._leaderboard_sent_at >= LEADERBOARD_EVERY_S:
            self._broadcast(self._leaderboard_message())

    def _minute_t(self, minute: float) -> float:
        """Match t for a display-clock minute: second-half minutes start at 45."""
        if minute < 45:
            return minute * 60
        second_half = next((e["t"] for e in self.source.data.events
                            if e["type"] == "period_start" and e["period"] == 2), 2700.0)
        return second_half + (minute - 45) * 60

    def _send_health(self) -> None:
        """Agent status for the dev panel (spec 3, 9.4): latency, calls, breaker state."""
        self._health_sent_at = time.monotonic()
        agents = self.agents.health()
        self._broadcast(message(
            "health", self.position, online=self.agents.online, agents=agents,
            llm_calls_per_minute=sum(a["per_minute"] for a in agents.values()),
            events_per_minute=self._events_per_minute()))

    def _events_per_minute(self) -> int:
        now = time.monotonic()
        return sum(1 for t in self._event_times if now - t <= 60)

    def _wrap(self, msg: dict[str, Any], t: float) -> dict[str, Any]:
        # Keys starting "_" are the session's own bookkeeping and never go to the browser.
        return message(msg["type"], t, **{k: v for k, v in msg.items()
                                          if k != "type" and not k.startswith("_")})

    def _square_context(self, square_id: str, template_text: str) -> dict[str, Any] | None:
        """What the rules tutor or narrator gets when a window closes."""
        sq = self.game.board.get(square_id)
        if sq is None or sq.result is None:
            return None
        if sq.opened_at is not None and sq.closes_at == sq.opened_at:
            return None     # jumped over (dev panel): nobody saw it, the template will do
        names = narrator.Names(self.meta)
        wanted = set(sq.evidence) | set(sq.source_event_ids)
        events = [e for e in self.game.events[-400:] if e["event_id"] in wanted][-6:]
        return {
            "square_id": sq.id, "kind": sq.kind,
            "question": sq.text.get(self.profile.language) or sq.text.get("en", ""),
            "template": sq.template, "answer": self.game.label(sq, sq.correct_answer),
            "answer_key": sq.correct_answer, "result": sq.result["status"],
            "clock": self.game.events[-1]["clock"] if self.game.events else "00:00",
            "half": self.game.events[-1]["period"] if self.game.events else 1,
            "events": [narrator.build_moment(e, 0, {}, [], [], names)["event"] | {
                "clock": e["clock"]} for e in events],
            "template_text": template_text,
        }

    def _recap_summary(self, kind: str) -> recap.Summary:
        """The state summary the recap is written from (spec 8.6), built by code."""
        names = narrator.Names(self.meta)
        snapshot = self.game.redact_stats(self.stats.snapshot())
        clubs = snapshot["clubs"]
        goals = [{"minute": f"{e['clock'].split(':')[0]}'",
                  "scorer": names.player(e.get("scorer_id")) or "an own goal",
                  "club": names.club(e["team_id"])}
                 for e in self.game.events if e["type"] == "goal"]
        players = snapshot["players"]
        standout_id = max(players, key=lambda p: players[p]["touches"], default=None)
        standout = None
        if standout_id is not None:
            best = players[standout_id]
            standout = {"player": names.player(standout_id), "club": names.club(best["team_id"]),
                        "touches": best["touches"]}
        chaos = snapshot["patterns"]["chaos"]
        patterns = [lang.say(self.profile.language, "in_control",
                             club=names.club(chaos["in_control"]))] \
            if chaos.get("in_control") else []
        row = next((r for r in leaderboard(self.viewer_row(), self.fans.rows()) if r["you"]), {})
        focus = self.profile.focus_player_id
        return recap.Summary(
            kind=kind,
            score={names.club(t) or t: n for t, n in snapshot["score"].items()},
            goals=goals,
            stats={names.club(t) or t: {k: v for k, v in c.items()
                                        if k in ("possession", "shots", "shots_on_target", "xg")
                                        and v is not None}
                   for t, c in clubs.items()},
            moments=self.agents.top_lines(),
            patterns=patterns, standout=standout,
            card={"points": self.game.board.points, "correct": self.game.board.correct,
                  "lines": len(self.game.board.scored_lines), "rank": row.get("rank"),
                  "of": len(self.fans.fans) + 1},
            club=names.club(self.profile.club),
            focus=None if focus is None else {
                "player": names.player(focus),
                **{k: v for k, v in players.get(focus, {}).items()
                   if k in ("touches", "passes", "shots") and v is not None}},
        )

    def _write_square(self, pending: dict[str, Any]) -> None:
        game = self.game        # a reset starts a new game; the old square stays closed

        def done(wording: Any) -> None:
            if game is self.game:
                self._send(game.open_live(pending["square_id"], wording))

        self.agents.write_square(pending, done)

    def _publish(self, msg: dict[str, Any]) -> None:
        """Results from the agents, applied on the event loop like everything else."""
        self._broadcast(self._wrap(msg, self.position))

    def _send(self, out: Out) -> None:
        t = self.game.t
        for msg in out:
            if msg["type"] == "live.pending":
                self._write_square(msg)
                continue
            if msg["type"] == "strategy.advice" and self.agents.online and \
                    not msg.get("_explained"):
                self.agents.explain_advice(
                    msg, self.game.board.view(),
                    lambda advice: self._send([{**advice, "_explained": True}]))
                continue
            if msg["type"] in ("square.result", "board.update"):
                self._leaderboard_dirty = True
            self._broadcast(self._wrap(msg, t))
            if msg["type"] == "square.explanation" and self.agents.online:
                context = self._square_context(msg["square_id"], msg["text"])
                if context is not None:
                    self.agents.explain_square(context)

    def viewer_row(self) -> dict[str, Any]:
        board = self.game.board
        times = [s.answer["elapsed_s"] for s in board.squares
                 if s.answer and s.state != "too_early"]
        return {"handle": self.profile.handle, "points": board.points, "correct": board.correct,
                "avg_answer_s": round(sum(times) / len(times), 1) if times else None}

    def _leaderboard_message(self) -> dict[str, Any]:
        self._leaderboard_dirty = False
        self._leaderboard_sent_at = time.monotonic()
        return message("leaderboard", self.game.t, mode=self.profile.mode,
                       rows=leaderboard(self.viewer_row(), self.fans.rows()),
                       total=len(self.fans.fans) + 1)

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
        self.agents.cancel()
        if self.task is not None:
            self.task.cancel()


class SessionRegistry:
    def __init__(self, clients: Callable[[], ChatClients | None] = shared_clients) -> None:
        self._sessions: dict[str, MatchSession] = {}
        self.clients = clients      # tests swap in a fake

    def create(self, seed: int, profile: dict[str, Any]) -> MatchSession:
        session = MatchSession(seed, profile, self.clients())
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
