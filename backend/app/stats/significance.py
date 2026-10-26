"""Significance score and routing (spec 7.10 and 7.11)."""

from dataclasses import dataclass
from typing import Any

from app.stats import pitch

GOAL = 80
PLANTED = 90
SHOT_BASE, SHOT_PER_XG, SHOT_CAP = 30, 100, 70
FAST_SHOT_KMH, FAST_SHOT = 100.0, 45
ADVANTAGE = 45
OFFSIDE_THROUGH_BALL = 40
LONG_PASS_M, LONG_PASS = 40.0, 35
MOVE_PASSES, MOVE = 10, 40
CARD = 35
KEEPER_OUT = 50
FINAL_THIRD_FOUL = 25
PATTERN = 50
MILESTONE = 45
LATE_MINUTE, LATE_BONUS = 75, 10
CLOSE_GAP, CLOSE_BONUS = 1, 10

LIVE_CANDIDATE, NARRATE = 60, 40
KEEPER_ACTIONS = {"pass", "carry", "clearance", "duel", "tackle", "interception", "block",
                  "foul"}


@dataclass(frozen=True)
class Context:
    """What the stats engine knows about an event beyond its own fields."""

    minute: int = 0
    goal_gap: int = 0
    attacks_right: bool = True          # direction of the event's club
    xg: float | None = None
    after_through_ball: bool = False    # an offside straight after a through ball
    passes_in_possession: int = 0       # including this pass
    planted: bool = False
    keeper: bool = False
    pattern_trigger: bool = False
    milestone: bool = False


def match_minute(clock: str) -> int:
    """Minute on the display clock: "45+2:10" is 45, "67:30" is 67."""
    return int(clock.split(":")[0].split("+")[0])


def significance(event: dict[str, Any], ctx: Context) -> int:
    kind = event["type"]
    scores = [0.0]
    if kind == "goal":
        scores.append(GOAL)
    if ctx.planted:
        scores.append(PLANTED)
    if kind == "shot":
        scores.append(min(SHOT_CAP, SHOT_BASE + SHOT_PER_XG * (ctx.xg or 0.0)))
        if event.get("ball_speed_kmh", 0.0) >= FAST_SHOT_KMH:
            scores.append(FAST_SHOT)
    if kind == "advantage":
        scores.append(ADVANTAGE)
    if kind == "offside" and ctx.after_through_ball:
        scores.append(OFFSIDE_THROUGH_BALL)
    if kind == "pass":
        if event["length_m"] >= LONG_PASS_M:
            scores.append(LONG_PASS)
        if ctx.passes_in_possession == MOVE_PASSES:
            scores.append(MOVE)
    if kind == "card":
        scores.append(CARD)
    if ctx.keeper and kind in KEEPER_ACTIONS and \
            not pitch.in_own_box(event["x"], event["y"], ctx.attacks_right):
        scores.append(KEEPER_OUT)
    if kind == "foul" and pitch.in_final_third(event["x"], not ctx.attacks_right):
        scores.append(FINAL_THIRD_FOUL)   # in the fouling club's own third
    if ctx.pattern_trigger:
        scores.append(PATTERN)
    if ctx.milestone:
        scores.append(MILESTONE)
    base = max(scores)
    if base == 0:
        return 0
    if ctx.minute >= LATE_MINUTE:
        base += LATE_BONUS
    if ctx.goal_gap <= CLOSE_GAP:
        base += CLOSE_BONUS
    return min(100, round(base))


def route(score: int, live_template_fits: bool = False) -> str:
    """live_candidate (if its segment still needs one), narrator, or template."""
    if score >= LIVE_CANDIDATE and live_template_fits:
        return "live_candidate"
    if score >= NARRATE:
        return "narrator"
    return "template"
