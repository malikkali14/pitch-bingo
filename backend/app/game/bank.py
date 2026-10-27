"""Question bank (spec 4.10) and the code that answers each question from the event log.

Static templates carry their wording, answer type per mode, masks and resolver. The resolver
is a plain function name; resolve.py holds the functions.
"""

from dataclasses import dataclass, field

HALF_S = 2700
FULL_S = 5400
DEFAULT_DEADLINES = (900, 1200, 1800, 2400, 2700, 3300, 3600, 4200, 4800, 5400)


@dataclass(frozen=True)
class Template:
    id: str
    kind: str                      # deadline or first
    text: str                      # English; {m}, {club}, {player} placeholders
    normal: str                    # answer type in normal mode: team, number, yesno, player
    advanced: str
    masks: tuple[str, ...]
    resolver: str
    trigger: dict[str, str] = field(default_factory=dict)  # first-to-happen event filter
    level: bool = False            # team answers that can also be "level"
    min_deadline_s: int = 0        # earliest deadline where the answer isn't a foregone 0
    tailored: str | None = None    # club or focus


DEADLINE = [
    Template("yellow_cards", "deadline", "How many yellow cards by {m}?", "number", "number",
             ("cards",), "count_yellow_cards", min_deadline_s=1200),
    Template("corners", "deadline", "How many corners by {m}?", "number", "number",
             ("corners",), "count_corners"),
    Template("more_shots", "deadline", "Which team has more shots by {m}?", "team", "team",
             ("shots",), "more_shots", level=True),
    Template("goal", "deadline", "Will there be a goal by {m}?", "yesno", "yesno",
             ("goals",), "any_goal"),
    Template("offsides", "deadline", "How many offsides by {m}?", "number", "number",
             ("offsides",), "count_offsides"),
    Template("possession", "deadline", "Who has more possession at {m}?", "team", "team",
             ("possession",), "more_possession"),
    Template("subs", "deadline", "How many substitutions by {m}?", "number", "number",
             ("subs",), "count_subs", min_deadline_s=3600),
    Template("focus_shot", "deadline", "Will {player} have a shot by {m}?", "yesno", "yesno",
             ("shots",), "focus_shot", tailored="focus"),
    Template("club_fouls", "deadline", "How many fouls by {club} by {m}?", "number", "number",
             ("fouls",), "count_club_fouls", tailored="club"),
]

FIRST = [
    Template("first_foul", "first", "Who commits the first foul?", "team", "player",
             ("fouls",), "first_actor", {"type": "foul"}),
    Template("first_corner", "first", "Who wins the first corner?", "team", "team",
             ("corners",), "first_actor", {"type": "corner"}),
    Template("first_shot", "first", "Who takes the first shot?", "team", "player",
             ("shots",), "first_actor", {"type": "shot"}),
    Template("first_on_target", "first", "Who has the first shot on target?", "team", "player",
             ("shots",), "first_actor", {"type": "shot", "outcome": "goal|saved"}),
    Template("first_offside", "first", "Who is first caught offside?", "team", "player",
             ("offsides",), "first_actor", {"type": "offside"}),
    Template("first_booking", "first", "Who is booked first?", "team", "player",
             ("cards",), "first_actor", {"type": "card"}),
    Template("first_sub_off", "first", "Who is subbed off first?", "team", "player",
             ("subs",), "first_sub_off", {"type": "substitution"}),
    Template("first_goal", "first", "Who scores first?", "team", "player",
             ("goals",), "first_scorer", {"type": "goal"}),
    Template("first_free_kick", "first", "Who wins the first free kick?", "team", "team",
             ("fouls",), "first_actor", {"type": "free_kick"}),
    Template("first_throw_in", "first", "Who takes the first throw-in?", "team", "player",
             (), "first_actor", {"type": "throw_in"}),
]

TEMPLATES = {t.id: t for t in DEADLINE + FIRST}
COMMON_DEADLINE = [t for t in DEADLINE if t.tailored is None]

# Tailored slots (spec 4.1, 5.2, 5.3): two club squares and two focus squares at fixed
# minutes. A viewer without a club or focus player gets common squares there instead.
TAILORED_SLOTS = (("club", 1800), ("club", 4200), ("focus", 3600), ("focus", 5400))


def minute_label(deadline_s: int) -> str:
    """70' for most deadlines; 45:00 and 90:00 for the end-of-half readings (spec 4.4)."""
    if deadline_s in (HALF_S, FULL_S):
        return f"{deadline_s // 60}:00"
    return f"{deadline_s // 60}'"
