"""The card (spec 4.1 to 4.3, 4.10): square records, the board, and the card builder.

Squares hold their correct answer and window times server-side. view() is what the browser
gets: it never includes the correct answer before the result, and a first-to-happen square in
its silent window still looks like it's waiting.
"""

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.game import ranges
from app.game.bank import (
    COMMON_DEADLINE,
    DEFAULT_DEADLINES,
    FIRST,
    HALF_S,
    TAILORED_SLOTS,
    TEMPLATES,
    Template,
    minute_label,
)

Cell = tuple[int, int]

BLANK_CELLS: tuple[Cell, ...] = ((0, 0), (0, 4), (2, 2), (4, 0), (4, 4))
LINES: dict[str, list[Cell]] = {
    **{f"row:{r}": [(r, c) for c in range(5)] for r in range(5)},
    **{f"col:{c}": [(r, c) for r in range(5)] for c in range(5)},
    "diag:0": [(i, i) for i in range(5)],
    "diag:1": [(i, 4 - i) for i in range(5)],
}
# Dropped first when a card carries 11 or 12 deadline squares: a first goal can be void.
FIRST_DROP_ORDER = ("first_goal", "first_throw_in")
MAX_PER_TEMPLATE = 2
MODES = ("normal", "advanced")
STRATEGIST = ("auto", "suggest", "manual")
RESOLVED = {"correct", "wrong", "too_early", "missed", "void", "wildcard"}
GOOD = {"correct", "void", "wildcard"}   # what counts toward a line (spec 4.8)


@dataclass(frozen=True)
class Profile:
    """The viewer profile fields the game uses (spec 5.7)."""

    mode: str = "normal"
    club: str | None = None
    focus_player_id: str | None = None
    language: str = "en"
    strategist: str = "auto"
    handle: str = "You"

    @classmethod
    def parse(cls, raw: dict[str, Any], meta: dict[str, Any]) -> "Profile":
        mode = raw.get("mode") or "normal"
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        club = raw.get("club")
        club = None if club in (None, "", "neutral") else str(club)
        if club is not None and club not in {t["id"] for t in meta["teams"]}:
            raise ValueError(f"unknown club {club!r}")
        focus = raw.get("focus_player_id") or None
        if focus is not None and focus not in {p["id"] for t in meta["teams"]
                                                for p in t["players"]}:
            raise ValueError(f"unknown player {focus!r}")
        strategist = raw.get("strategist") or ("auto" if mode == "normal" else "suggest")
        if strategist not in STRATEGIST:
            raise ValueError(f"unknown strategist setting {strategist!r}")
        language = raw.get("language") or "en"
        handle = str(raw.get("handle") or "You")[:24]
        return cls(mode, club, focus, language, strategist, handle)

    def public(self) -> dict[str, Any]:
        return {"mode": self.mode, "club": self.club or "neutral",
                "focus_player_id": self.focus_player_id, "language": self.language,
                "strategist": self.strategist, "handle": self.handle}


@dataclass
class Square:
    id: str
    kind: str                                  # deadline, first or live
    template: str
    text: dict[str, str]
    answer_type: str
    options: list[str]
    option_labels: dict[str, list[str]]
    deadline_s: int | None
    trigger: dict[str, str] | None
    resolver: str
    masks: list[str]
    cell: Cell
    state: str
    club: str | None = None                    # tailored squares
    focus: str | None = None
    answer: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    source_event_ids: list[str] = field(default_factory=list)
    # Server-side only.
    correct_answer: str | None = None
    evidence: list[str] = field(default_factory=list)
    opened_at: float | None = None             # window clock, seconds
    closes_at: float | None = None
    closes_wall_ms: int | None = None          # for the browser's countdown
    open_t: float | None = None                # match t when the window opened
    trigger_event_id: str | None = None

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    @property
    def announced(self) -> bool:
        """Deadline and live windows announce themselves; first-to-happen windows are silent."""
        return self.kind != "first"

    @property
    def is_blank_like(self) -> bool:
        return self.state in ("empty_blank", "wildcard")

    def view(self) -> dict[str, Any]:
        silent = self.kind == "first" and self.state == "open"
        return {
            "id": self.id,
            "kind": self.kind,
            "text": dict(self.text),
            "answer_type": self.answer_type,
            "options": list(self.options),
            "option_labels": {k: list(v) for k, v in self.option_labels.items()},
            "deadline_s": self.deadline_s,
            "trigger": dict(self.trigger) if self.trigger else None,
            "resolver": self.resolver,
            "masks": list(self.masks),
            "cell": {"row": self.cell[0], "col": self.cell[1]},
            "state": "waiting" if silent else self.state,
            "answer": dict(self.answer) if self.answer else None,
            "result": dict(self.result) if self.result else None,
            "source_event_ids": list(self.source_event_ids),
            "closes_at": None if silent else self.closes_wall_ms,
        }


@dataclass
class Board:
    squares: list[Square]
    scored_lines: list[str] = field(default_factory=list)
    points: int = 0
    bonus_points: int = 0
    full_card: bool = False

    def at(self, cell: Cell) -> Square:
        return next(s for s in self.squares if s.cell == cell)

    def get(self, square_id: str) -> Square | None:
        return next((s for s in self.squares if s.id == square_id), None)

    def locked(self, square: Square) -> bool:
        return any(square.cell in LINES[line] for line in self.scored_lines)

    @property
    def correct(self) -> int:
        return sum(1 for s in self.squares if s.result and s.result["status"] == "correct")

    def view(self) -> dict[str, Any]:
        return {
            "squares": [s.view() for s in self.squares],
            "scored_lines": list(self.scored_lines),
            "points": self.points,
            "correct": self.correct,
            "bingos": len(self.scored_lines),
            "full_card": self.full_card,
        }


def validate_deadlines(deadlines: Sequence[int]) -> None:
    """Spec 4.1: 10 to 12 deadlines (so 8 to 10 first-to-happen squares), none before 10',
    at least 4 in the first half, at most 2 sharing a minute."""
    if not 20 - len(FIRST) <= len(deadlines) <= 12:
        raise ValueError(f"a card takes {20 - len(FIRST)} to 12 deadline squares")
    for d in deadlines:
        if d % 60 or not 600 <= d <= 2 * HALF_S:
            raise ValueError(f"deadline {d} must be a whole minute from 10' to 90:00")
    if sum(1 for d in deadlines if d <= HALF_S) < 4:
        raise ValueError("at least 4 deadlines must fall in the first half")
    if max(Counter(deadlines).values()) > 2:
        raise ValueError("at most 2 squares can share a deadline minute")


def _names(meta: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    clubs = {t["id"]: t["short_name"] for t in meta["teams"]}
    surnames = {p["id"]: p["surname"] for t in meta["teams"] for p in t["players"]}
    return clubs, surnames


def _options(template: Template, answer_type: str, deadline_s: int | None,
             meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    clubs, _ = _names(meta)
    home, away = meta["home_team_id"], meta["away_team_id"]
    if answer_type == "team":
        keys = [home, away] + (["level"] if template.level else [])
        return keys, [clubs.get(k, "Level") for k in keys]
    if answer_type == "yesno":
        return ["yes", "no"], ["Yes", "No"]
    if answer_type == "number" and deadline_s is not None:
        keys = ranges.option_keys(ranges.cuts_for(template.id, deadline_s))
        return keys, [ranges.label(k) for k in keys]
    return [], []


def make_static(square_id: str, template: Template, mode: str, cell: Cell,
                meta: dict[str, Any], deadline_s: int | None = None,
                club: str | None = None, focus: str | None = None) -> Square:
    clubs, surnames = _names(meta)
    answer_type = template.normal if mode == "normal" else template.advanced
    exact_number = answer_type == "number" and mode == "advanced"
    options, labels = _options(template, answer_type,
                               None if exact_number else deadline_s, meta)
    text = template.text.format(m=minute_label(deadline_s) if deadline_s is not None else "",
                                club=clubs.get(club or "", ""),
                                player=surnames.get(focus or "", ""))
    return Square(
        id=square_id, kind=template.kind, template=template.id, text={"en": text},
        answer_type=answer_type, options=options, option_labels={"en": labels} if labels else {},
        deadline_s=deadline_s, trigger=dict(template.trigger) or None,
        resolver=template.resolver, masks=list(template.masks), cell=cell, state="waiting",
        club=club, focus=focus)


def blank(index: int, cell: Cell) -> Square:
    return Square(id=f"bl_{index}", kind="live", template="", text={}, answer_type="choice",
                  options=[], option_labels={}, deadline_s=None, trigger=None, resolver="",
                  masks=[], cell=cell, state="empty_blank")


def _pick(rng: random.Random, minute: int, uses: Counter[str]) -> Template:
    eligible = [t for t in COMMON_DEADLINE
                if t.min_deadline_s <= minute and uses[t.id] < MAX_PER_TEMPLATE]
    fewest = min(uses[t.id] for t in eligible)
    choice = rng.choice([t for t in eligible if uses[t.id] == fewest])
    uses[choice.id] += 1
    return choice


def _tailored_indices(deadlines: Sequence[int]) -> list[int]:
    """The deadline index each tailored slot takes: its minute, or the nearest free one."""
    taken: list[int] = []
    for _, minute in TAILORED_SLOTS:
        free = [i for i in range(len(deadlines)) if i not in taken]
        taken.append(min(free, key=lambda i: (abs(deadlines[i] - minute), i)))
    return taken


def build_card(meta: dict[str, Any], profile: Profile,
               deadlines: Iterable[int] = DEFAULT_DEADLINES) -> Board:
    """20 statics plus 5 blanks. Everything except the tailored squares depends only on the
    match seed and the mode, so viewers in a mode share at least 16 statics."""
    deadlines = sorted(deadlines)
    validate_deadlines(deadlines)
    rng = random.Random(f"card:{meta['seed']}:{profile.mode}")

    firsts = list(FIRST)
    for drop in FIRST_DROP_ORDER[:len(deadlines) - 10]:
        firsts = [t for t in firsts if t.id != drop]

    # Common deadline squares first, then fillers for the tailored slots, so the draw order
    # (and so every common square) is the same whatever the profile.
    tailored_at = _tailored_indices(deadlines)
    uses: Counter[str] = Counter()
    common: dict[int, Template] = {}
    for i, minute in enumerate(deadlines):
        if i not in tailored_at:
            common[i] = _pick(rng, minute, uses)
    for i in tailored_at:
        common[i] = _pick(rng, deadlines[i], uses)

    cells = [(r, c) for r in range(5) for c in range(5) if (r, c) not in BLANK_CELLS]
    rng.shuffle(cells)

    squares: list[Square] = []
    for n, template in enumerate(firsts):
        squares.append(make_static(f"sq_{n + 1:02d}", template, profile.mode, cells[n], meta))
    for i, minute in enumerate(deadlines):
        n = len(firsts) + i
        template, club, focus = common[i], None, None
        if i in tailored_at:
            slot = TAILORED_SLOTS[tailored_at.index(i)][0]
            if slot == "club" and profile.club:
                template, club = TEMPLATES["club_fouls"], profile.club
            elif slot == "focus" and profile.focus_player_id:
                template, focus = TEMPLATES["focus_shot"], profile.focus_player_id
        squares.append(make_static(f"sq_{n + 1:02d}", template, profile.mode, cells[n], meta,
                                   deadline_s=minute, club=club, focus=focus))
    squares += [blank(i + 1, cell) for i, cell in enumerate(BLANK_CELLS)]
    return Board(squares)
