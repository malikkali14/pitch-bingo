"""The game for one viewer (spec 4): card, windows, answers, lines and points.

The session feeds it every event and tick in order and sends whatever messages come back.
It keeps its own event log and running stats, so a deadline answer only ever sees events at
or before the deadline. Nothing here waits on an LLM.
"""

import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from app.game import ranges
from app.game.bank import TEMPLATES
from app.game.card import Board, Cell, Profile, Square, build_card
from app.game.live import LiveProducer, Moment, build_live
from app.game.masks import Masks
from app.game.resolve import Context, deadline_t, first_answer, matches, resolve_deadline
from app.game.resolve import evidence as deadline_evidence
from app.game.scorekeeper import Out, Scorekeeper, WindowClock, error
from app.models import wall_ms as server_wall_ms
from app.stats.core import RunningStats

CATCH_UP_S = 3.0   # a window this far behind the clock was jumped over (dev panel)


def parse_cell(raw: Any) -> Cell | None:
    """A cell from the browser: {"row": r, "col": c} or [r, c]."""
    try:
        row, col = (raw["row"], raw["col"]) if isinstance(raw, dict) else raw
        row, col = int(row), int(col)
    except (TypeError, ValueError, KeyError):
        return None
    return (row, col) if 0 <= row < 5 and 0 <= col < 5 else None


class Game:
    def __init__(self, meta: dict[str, Any], profile: Profile,
                 now: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = server_wall_ms,
                 board: Board | None = None, planted: frozenset[int] = frozenset()) -> None:
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
        self.live = LiveProducer(meta["home_team_id"], meta["away_team_id"], planted)
        self.live_used: Counter[str] = Counter()
        self.masks = Masks()
        for sq in self._kickoff_masked():
            self.masks.on(sq.id, sq.masks)

    # ---- input from the session ----------------------------------------------------------

    def on_event(self, event: dict[str, Any], significance: int = 0, live: bool = True) -> Out:
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
        moment = self.live.on_event(event, significance, self.stats)
        if moment is not None:
            out += self._add_live(moment, live)
        if event["type"] == "period_end" and event["period"] == 2:
            out += self._full_time()
        return self._apply(out + self.keeper.tick())

    def on_tick(self, t: float) -> Out:
        self.t = max(self.t, t)
        return self._apply(self._deadlines(t, strict=False, live=None) + self.keeper.tick())

    def answer(self, square_id: str, value: Any) -> Out:
        return self._apply(self.keeper.answer(square_id, value, self.t))

    def move(self, from_cell: Any, to_cell: Any) -> Out:
        cells = parse_cell(from_cell), parse_cell(to_cell)
        if cells[0] is None or cells[1] is None:
            return [error("board.move", "cells are {row, col} from 0 to 4")]
        return self._apply(self.keeper.move(cells[0], cells[1]))

    def pause(self, on: bool) -> None:
        self.clock.pause(on)

    # ---- masks and hold-backs (spec 4.9) -------------------------------------------------

    def _kickoff_masked(self) -> list[Square]:
        return [s for s in self.board.squares if s.kind == "first" and s.masks]

    def initial_messages(self) -> Out:
        """Sent after session.ready: first-to-happen squares mask their tags from kickoff."""
        return [{"type": "mask.on", "square_id": sq.id, "tags": list(sq.masks)}
                for sq in self._kickoff_masked() if sq.id in self.masks.by_square]

    def hold(self, event: dict[str, Any]) -> bool:
        """Whether this event's feed entry waits for a window to close. Ask after on_event,
        so an event that opens a window is held by it."""
        return self.masks.hold(event["event_id"], event.get("tags") or [])

    def redact_stats(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self.masks.redact(snapshot)

    def _apply(self, out: Out) -> Out:
        """Track mask messages, and reveal held entries once nothing masks them."""
        extra: Out = []
        for msg in out:
            if msg["type"] == "mask.on":
                self.masks.on(msg["square_id"], msg["tags"])
            elif msg["type"] == "mask.off":
                released = self.masks.off(msg["square_id"])
                if released:
                    extra.append({"type": "feed.reveal", "entry_ids": released})
        return out + extra

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

    def _add_live(self, moment: Moment, live: bool) -> Out:
        spec = build_live(moment, self.profile.mode, self.live_used, self.meta)
        sq = self._blank_for_live()
        sq.template, sq.text = spec.template, {"en": spec.text}
        sq.answer_type, sq.options = "choice", spec.options
        sq.option_labels = {"en": spec.labels}
        sq.masks, sq.source_event_ids = spec.masks, spec.source_event_ids
        sq.resolver, sq.state = f"live_{spec.template}", "waiting"
        self.live.segment_of[sq.id] = moment.segment
        out: Out = [{"type": "square.added", "square": sq.view()}]
        out += self.keeper.open(sq, spec.correct, spec.source_event_ids, self.t, skip=not live)
        out[0]["square"] = sq.view()
        return out + self.keeper.board_changed()

    def _blank_for_live(self) -> Square:
        """The empty blank a new live square lands in (spec 4.7)."""
        return next(s for s in self.board.squares if s.state == "empty_blank")

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

