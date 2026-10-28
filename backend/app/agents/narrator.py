"""The narrator (spec 8.6, 8.10): one language-neutral insight per moment worth a line.

Its input is a Moment built by code: the event with ids turned into names, the score, the
stats a viewer can see (masked values are left out, so a line can't give an answer away),
the pattern triggers and milestones. Coordinates and raw timestamps stay out, since a model
would quote them as if they meant something.
"""

from typing import Any

from app.agents.messages import Insight
from app.agents.runner import AgentSpec
from app.stats.significance import NARRATE

PROMPT = """You explain football moments for a live match viewer.
Use ONLY the facts and numbers in INPUT. Never invent a number or a name.
Return JSON matching the Insight schema.
headline_facts: what happened. why_facts: why it matters right now,
using the pattern data (control vs. chaos, pressure, rhythm, momentum).
No betting language. Neutral tone.
Write each fact as one short sentence, under 100 characters. Name at most two players,
exactly as INPUT spells them. Copy moment_id from INPUT.
Lead with what happened in this event. Bring in match stats such as possession only when they
explain this moment, and never repeat a point from the recent lines you are shown. Mention
timing (early, half-time, late) only if the clock in INPUT supports it."""

SPEC = AgentSpec("narrator", "fast", PROMPT, Insight, budget_s=3.0)

EVENT_FIELDS = ("type", "outcome", "pass_type", "height", "length_m", "ball_speed_kmh",
                "opponents_bypassed", "shot_type", "body_part", "card", "severity", "advantage",
                "duel_type", "cause", "own_goal", "line", "under_pressure")
PERSON_FIELDS = ("player_id", "receiver_id", "scorer_id", "assist_id", "fouled_id",
                 "opponent_id", "player_on_id", "player_off_id", "keeper_id", "target_id")
CLUB_STATS = ("possession", "shots", "shots_on_target", "xg", "corners", "fouls",
              "yellow_cards", "red_cards", "offsides", "pass_accuracy")


def wants_line(significance: int, triggers: list[dict[str, Any]]) -> bool:
    """Spec 7.11 and 8.1: significance 40 or more, or a pattern trigger."""
    return significance >= NARRATE or bool(triggers)


class Names:
    def __init__(self, meta: dict[str, Any]) -> None:
        self.clubs = {t["id"]: t["short_name"] for t in meta["teams"]}
        self.players = {p["id"]: p["full_name"] for t in meta["teams"] for p in t["players"]}
        self.home, self.away = meta["home_team_id"], meta["away_team_id"]

    def club(self, team_id: str | None) -> str | None:
        return self.clubs.get(team_id or "")

    def player(self, player_id: str | None) -> str | None:
        return self.players.get(player_id or "")


def build_moment(event: dict[str, Any], significance: int, stats: dict[str, Any],
                 triggers: list[dict[str, Any]], milestones: list[dict[str, Any]],
                 names: Names, shot_xg: float | None = None) -> dict[str, Any]:
    described: dict[str, Any] = {k: event[k] for k in EVENT_FIELDS if event.get(k) is not None}
    if event.get("team_id"):
        # A foul's club is the one that committed it; say so, or a model reads it as the victim.
        key = "fouling_club" if event["type"] == "foul" else "club"
        described[key] = names.club(event["team_id"])
    for key in PERSON_FIELDS:
        if event.get(key):
            described[key.removesuffix("_id")] = names.player(event[key])
    if event["type"] == "shot" and shot_xg is not None:
        described["xg"] = round(shot_xg, 2)
    score = stats.get("score", {})
    clubs = stats.get("clubs", {})
    patterns = stats.get("patterns", {})
    club_stats = {}
    for team in (names.home, names.away):
        values = clubs.get(team, {})
        club_stats[names.club(team)] = {k: values[k] for k in CLUB_STATS
                                        if values.get(k) is not None}
    chaos = patterns.get("chaos", {})
    momentum = patterns.get("momentum", {}).get("value")
    leader = names.home if (momentum or 0) > 0 else names.away
    pattern_data = {
        "control_vs_chaos": chaos.get("value"),
        "in_control": names.club(chaos.get("in_control")),
        "momentum": None if not momentum else {"club": names.club(leader),
                                               "strength": abs(round(momentum))},
        "tempo": patterns.get("rhythm", {}).get("tempo"),
        "pressure": {names.club(team): {k: v for k, v in p.items()
                                        if k in ("ppda", "high_regains_5min") and v is not None}
                     for team, p in patterns.get("pressure", {}).items()},
    }
    return {
        "moment_id": event["event_id"],
        "clock": event["clock"],
        "half": event["period"],
        "significance": significance,
        "event": described,
        "score": {names.club(team): goals for team, goals in score.items()},
        "stats": club_stats,
        "patterns": {k: v for k, v in pattern_data.items() if v not in (None, {})},
        "pattern_triggers": [_named(t, names) for t in triggers],
        "milestones": [_named(m, names) for m in milestones],
    }


def _named(item: dict[str, Any], names: Names) -> dict[str, Any]:
    out = {}
    for key, value in item.items():
        if key == "t":
            continue
        if key == "team_id":
            out["club"] = names.club(value)
        elif key == "player_id":
            out["player"] = names.player(value)
        else:
            out[key] = value
    return out


def render(insight: Insight, limit: int) -> str | None:
    """Template rendering of an insight (the personalizer's fallback): the headline, plus the
    first reason when both fit the mode's limit."""
    headline = next((h.strip() for h in insight.headline_facts if h.strip()), "")
    why = next((w.strip() for w in insight.why_facts if w.strip()), "")
    for text in (f"{headline} {why}".strip(), headline):
        if text and len(text) <= limit:
            return text
    return None
