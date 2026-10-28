"""Recaps at half-time and full time (spec 3, 8.4 recap workflow, 8.6).

Code builds the state summary (score, goals, top moments, patterns, a standout player, the
viewer's card, their club and focus player). The recap agent (quality model) writes from it,
and a template recap from the same summary posts first, so there is always a recap.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.messages import Recap, RecapContent
from app.agents.runner import AgentSpec
from app.game import lang
from app.verify.verifier import verify_line

PROMPT = """You write a short football match recap for a fan following a live match.
Use ONLY the facts and numbers in INPUT. Never invent a number, a name or an event.
headline: one line. paragraphs: three to five short paragraphs on the score, the goals, how
the match has gone (control, pressure, momentum) and the standout player. talking_points:
exactly three short bullets a broadcaster could use. If INPUT has a club or a focus player,
add club_paragraph or player_paragraph about them. bingo_summary: one line on the viewer's
card. No betting language. Return JSON matching the RecapContent schema."""

SPEC = AgentSpec("recap", "quality", PROMPT, RecapContent, budget_s=20.0)
PARAGRAPH_LIMIT = 400


@dataclass
class Summary:
    kind: str                                        # halftime or full_time
    score: dict[str, int]                            # club short name -> goals
    goals: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    moments: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    standout: dict[str, Any] | None = None
    card: dict[str, Any] = field(default_factory=dict)
    club: str | None = None
    focus: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, [], {})}


def template(s: Summary, language: str = "en") -> Recap:
    """The template recap, in the viewer's language (spec 5.4), with the club and focus-player
    paragraphs (spec 5.2, 5.3) when the profile has them."""
    language = lang.normalize(language)

    def say(key: str, **values: Any) -> str:
        return lang.say(language, key, **values)

    (home, home_goals), (away, away_goals) = list(s.score.items())
    score = f"{home} {home_goals}–{away_goals} {away}"
    label = say(f"recap_{s.kind}") if f"recap_{s.kind}" in lang.LINES["en"] else say("recap_other")
    headline = say("headline", label=label, score=score)
    paragraphs = []
    if s.goals:
        paragraphs.append(say("goals", list="; ".join(
            f"{g['scorer']} ({g['club']}, {g['minute']})" for g in s.goals)))
    else:
        paragraphs.append(say("no_goals"))
    h, a = s.stats.get(home, {}), s.stats.get(away, {})
    if h.get("possession") is not None and a.get("possession") is not None:
        paragraphs.append(say("possession", home=home, share=f"{h['possession']:.0f}",
                              hs=h.get("shots", 0), as_=a.get("shots", 0)))
    paragraphs += s.moments[:2]
    if s.standout:
        paragraphs.append(say("standout", **s.standout))
    points = [score]
    points.append(s.moments[0] if s.moments else say(
        "shots_point", home=home, hs=h.get("shots", 0), away=away, as_=a.get("shots", 0)))
    points.append(s.patterns[0] if s.patterns else
                  (say("standout_point", player=s.standout["player"]) if s.standout
                   else say("open_point")))
    card = s.card
    bingo = (say("bingo", points=card.get("points", 0), correct=card.get("correct", 0),
                 lines=card.get("lines", 0)) if card else None)
    club = None
    if s.club in s.score:
        mine, theirs = s.score[s.club], next(n for c, n in s.score.items() if c != s.club)
        state = "club_ahead" if mine > theirs else "club_behind" if mine < theirs else "club_level"
        club = say("club_paragraph", club=s.club, situation=say(state, score=f"{mine}–{theirs}"))
    player = None
    if s.focus:
        player = say("player_paragraph", player=s.focus["player"],
                     touches=s.focus.get("touches", 0), passes=s.focus.get("passes", 0),
                     shots=s.focus.get("shots", 0))
    return Recap(kind=s.kind, content=RecapContent(
        headline=headline, paragraphs=paragraphs, talking_points=points[:3],
        club_paragraph=club, player_paragraph=player, bingo_summary=bingo))


def check(content: RecapContent, summary: Summary, meta: dict[str, Any]
          ) -> tuple[Recap | None, list[str]]:
    payload = summary.payload()
    errors = []
    if not 1 <= len(content.paragraphs) <= 6:
        errors.append("write three to five paragraphs")
    if len(content.talking_points) != 3:
        errors.append("write exactly three talking points")
    recap = Recap(kind=summary.kind, content=content, ai=True)
    for part in recap.text_parts():
        for error in verify_line(part, payload, meta, "advanced"):
            if "too long" in error and len(part) <= PARAGRAPH_LIMIT:
                continue                              # paragraphs may run past a feed line
            errors.append(f"{error} (in: {part[:60]})")
    return (None, errors) if errors else (recap, [])
