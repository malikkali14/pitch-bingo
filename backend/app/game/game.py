"""The game for one viewer (spec 4): card, windows, answers, lines and points.

The session feeds it every event and tick in order and sends whatever messages come back.
It keeps its own event log and running stats, so a deadline answer only ever sees events at
or before the deadline. Nothing here waits on an LLM.
"""

import time
from collections.abc import Callable
from typing import Any

from app.game import ranges
from app.game.bank import TEMPLATES
from app.game.card import Board, Profile, Square, build_card
from app.game.resolve import Context, deadline_t, first_answer, matches, resolve_deadline
from app.game.resolve import evidence as deadline_evidence
from app.game.scorekeeper import Out, Scorekeeper, WindowClock
from app.models import wall_ms as server_wall_ms
from app.stats.core import RunningStats

CATCH_UP_S = 3.0   # a window this far behind the clock was jumped over (dev panel)


class Game:
    def __init__(self, meta: dict[str, Any], profile: Profile,
                 now: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = server_wall_ms,
                 board: Board | None = None) -> None:
        self.meta = meta
        self.profile = profile
        self.board = board or build_card(meta, profile)
        self.clock = WindowClock(now)
        self.clubs = {t["id"]: t["short_name"] for t in meta["teams"]}
        self.players = {p["id"]: p for t in meta["teams"] for p in t["players"]}
        self.keeper = Scorekeeper(self.board, self.clock, wall_ms, set(self.players), self.label)
        self.events: list[dict[str, Any]] = []
        self.stats = RunningStats(meta)
        self.second_half_t: float | None = None
        self.t = 0.0
        self.full_time = False

    # ---- input from the session ----------------------------------------------------------

    def on_event(self, event: dict[str, Any], live: bool = True) -> Out:
        t = event["t"]
        # A deadline this event steps past opens on the state before the event, so the
        # event itself (later than the deadline second) never counts.
        out = self._deadlines(t, strict=True, live=live)
        self.t = max(self.t, t)
        self.events.append(event)
        self.stats.update(event)
        if event["type"] == "period_start" and event["period"] == 2:
            self.second_half_t = t
        out += self._first_to_happen(event, live)
        if event["type"] == "period_end" and event["period"] == 2:
            out += self._full_time()
        return out + self.keeper.tick()

    def on_tick(self, t: float) -> Out:
        self.t = max(self.t, t)
        return self._deadlines(t, strict=False, live=None) + self.keeper.tick()

    def answer(self, square_id: str, value: Any) -> Out:
        return self.keeper.answer(square_id, value, self.t)

    def pause(self, on: bool) -> None:
        self.clock.pause(on)

    # ---- windows -------------------------------------------------------------------------

    def _deadlines(self, t: float, strict: bool, live: bool | None) -> Out:
        out: Out = []
        for sq in self.board.squares:
            if sq.kind != "deadline" or sq.state != "waiting" or sq.deadline_s is None:
                continue
            until = deadline_t(sq.deadline_s, self.second_half_t)
            if until is None or (t <= until if strict else t < until):
                continue
            skip = (not live) if live is not None else t - until > CATCH_UP_S
            out += self.keeper.open(sq, self._resolve(sq, until),
                                    deadline_evidence(TEMPLATES[sq.template], self.events,
                                                      until, self._context(sq)),
                                    t, skip=skip)
        return out

    def _context(self, sq: Square) -> Context:
        possession = {k: v["possession"] for k, v in self.stats.club_snapshot().items()}
        return Context(self.meta["home_team_id"], self.meta["away_team_id"], club=sq.club,
                       focus=sq.focus, possession=possession)

    def _resolve(self, sq: Square, until: float) -> str:
        answer = resolve_deadline(TEMPLATES[sq.template], self.events, until, self._context(sq))
        if sq.answer_type == "number" and sq.options:
            return ranges.range_of(sq.options, int(answer))
        return answer

    def _first_to_happen(self, event: dict[str, Any], live: bool) -> Out:
        out: Out = []
        for sq in self.board.squares:
            if sq.kind != "first" or sq.trigger is None or sq.trigger_event_id is not None:
                continue
            if sq.state not in ("waiting", "too_early") or not matches(sq.trigger, event):
                continue
            sq.trigger_event_id = event["event_id"]
            answer = first_answer(TEMPLATES[sq.template], event, sq.answer_type)
            out += self.keeper.open(sq, answer, [event["event_id"]], event["t"], skip=not live)
        return out

    def _full_time(self) -> Out:
        self.full_time = True
        out: Out = []
        for sq in self.board.squares:
            if sq.kind == "first" and sq.trigger_event_id is None:
                if sq.state == "waiting":
                    out += self.keeper.void(sq)
                elif sq.masks:
                    out.append({"type": "mask.off", "square_id": sq.id, "tags": list(sq.masks)})
        return out

    # ---- wording -------------------------------------------------------------------------

    def label(self, sq: Square, value: str | None) -> str:
        if value is None:
            return "none"
        if value in self.clubs:
            return self.clubs[value]
        if value in self.players:
            return str(self.players[value]["full_name"])
        if value in sq.options and sq.option_labels.get("en"):
            return sq.option_labels["en"][sq.options.index(value)]
        return {"level": "Level", "yes": "Yes", "no": "No"}.get(value, value)

