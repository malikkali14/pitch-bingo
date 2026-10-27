"""Resolvers: the code that computes each static square's correct answer (spec 4.2, 4.4).

Deadline resolvers see only the events at or before the deadline, so later events never count.
First-to-happen squares match a trigger against each event and read the answer off the first
match. Answers are plain strings: a team id, a player id, "level", "yes"/"no" or a count.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.game.bank import HALF_S, Template

Event = dict[str, Any]
ON_TARGET = {"goal", "saved"}


@dataclass(frozen=True)
class Context:
    home: str
    away: str
    club: str | None = None
    focus: str | None = None
    possession: dict[str, float] = field(default_factory=dict)  # share per club at the deadline


def deadline_t(deadline_s: int, second_half_t: float | None) -> float | None:
    """Match t for a clock reading. 45:00 is the first-half reading, before stoppage time.
    Second-half deadlines are unknown (None) until the second half kicks off."""
    if deadline_s <= HALF_S:
        return float(deadline_s)
    if second_half_t is None:
        return None
    return second_half_t + deadline_s - HALF_S


def _more(home: float, away: float, ctx: Context) -> str:
    if home == away:
        return "level"
    return ctx.home if home > away else ctx.away


def _more_shots(events: list[Event], ctx: Context) -> str:
    shots = {ctx.home: 0, ctx.away: 0}
    for e in events:
        if e["type"] == "shot":
            shots[e["team_id"]] += 1
    return _more(shots[ctx.home], shots[ctx.away], ctx)


def _more_possession(events: list[Event], ctx: Context) -> str:
    home, away = ctx.possession.get(ctx.home, 50.0), ctx.possession.get(ctx.away, 50.0)
    # A dead heat can't be "level" (it isn't an option); the home club takes it.
    return ctx.home if home >= away else ctx.away


# Counts agree with the stats panel: a second yellow counts as a red there, so here too.
PREDICATES: dict[str, Callable[[Event, Context], bool]] = {
    "count_yellow_cards": lambda e, ctx: e["type"] == "card" and e["card"] == "yellow",
    "count_corners": lambda e, ctx: e["type"] == "corner",
    "count_offsides": lambda e, ctx: e["type"] == "offside",
    "count_subs": lambda e, ctx: e["type"] == "substitution",
    "count_club_fouls": lambda e, ctx: e["type"] == "foul" and e["team_id"] == ctx.club,
    "any_goal": lambda e, ctx: e["type"] == "goal",
    "focus_shot": lambda e, ctx: e["type"] == "shot" and e["player_id"] == ctx.focus,
    "more_shots": lambda e, ctx: e["type"] == "shot",
}
YES_NO = {"any_goal", "focus_shot"}


def _counter(name: str) -> Callable[[list[Event], Context], str]:
    test = PREDICATES[name]

    def resolve(events: list[Event], ctx: Context) -> str:
        n = sum(1 for e in events if test(e, ctx))
        return ("yes" if n else "no") if name in YES_NO else str(n)
    return resolve


DEADLINE_RESOLVERS: dict[str, Callable[[list[Event], Context], str]] = {
    **{name: _counter(name) for name in PREDICATES if name != "more_shots"},
    "more_shots": _more_shots,
    "more_possession": _more_possession,
}


def resolve_deadline(template: Template, events: Iterable[Event], until_t: float,
                     ctx: Context) -> str:
    return DEADLINE_RESOLVERS[template.resolver]([e for e in events if e["t"] <= until_t], ctx)


def matches(trigger: dict[str, str], event: Event) -> bool:
    return all(str(event.get(key)) in value.split("|") for key, value in trigger.items())


def first_answer(template: Template, event: Event, answer_type: str) -> str:
    """The answer a first-to-happen event gives: the club, or the player, it names."""
    if answer_type == "team":
        return str(event["team_id"])
    if template.resolver == "first_sub_off":
        return str(event["player_off_id"])
    if template.resolver == "first_scorer":
        return str(event["scorer_id"])
    return str(event["player_id"])


def evidence(template: Template, events: Iterable[Event], until_t: float,
             ctx: Context) -> list[str]:
    """Event ids that back a deadline answer, for the result record."""
    test = PREDICATES.get(template.resolver)
    if test is None:
        return []
    return [e["event_id"] for e in events if e["t"] <= until_t and test(e, ctx)][:20]
