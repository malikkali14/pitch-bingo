"""Expected goals model (SPEC section 7.3).

The generator samples shot outcomes from this same function, so keep it pure.
"""

import math
from collections.abc import Mapping
from typing import Any

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
GOAL_WIDTH_M = 7.32
# (GOAL_WIDTH_M / 2) ** 2, rounded as in the spec.
HALF_GOAL_WIDTH_SQ = 13.4

PENALTY_XG = 0.78

# Starting coefficients from 7.3; tune with the validation script.
INTERCEPT = -1.2
ANGLE_COEF = 1.6
DISTANCE_COEF = -0.11
HEADER_COEF = -0.8
ASSISTED_COEF = 0.4
PRESSURE_COEF = -0.3
FREE_KICK_COEF = -0.6


def goal_angle(dx: float, dy: float) -> float:
    """Angle in radians subtended by the goal mouth.

    dx is the distance from the goal line, dy the offset from the goal's center.
    """
    return math.atan2(GOAL_WIDTH_M * dx, dx * dx + dy * dy - HALF_GOAL_WIDTH_SQ)


def xg(
    shot_event: Mapping[str, Any],
    *,
    assisted_chance: bool = False,
    attacking_right: bool | None = None,
) -> float:
    """Chance that a shot becomes a goal.

    assisted_chance is True when the shot follows a through ball or cutback; the caller
    works it out from the event stream. attacking_right says whether the shooter's team
    attacks the x = 105 goal; when None, the goal nearer the shot is used.
    """
    if shot_event.get("shot_type") == "penalty":
        return PENALTY_XG

    x = float(shot_event["x"])
    y = float(shot_event["y"])
    if attacking_right is None:
        attacking_right = x >= PITCH_LENGTH_M / 2
    dx = PITCH_LENGTH_M - x if attacking_right else x
    dy = abs(y - PITCH_WIDTH_M / 2)

    header = shot_event.get("shot_type") == "header" or shot_event.get("body_part") == "head"
    logit = (
        INTERCEPT
        + ANGLE_COEF * goal_angle(dx, dy)
        + DISTANCE_COEF * math.hypot(dx, dy)
        + HEADER_COEF * header
        + ASSISTED_COEF * assisted_chance
        + PRESSURE_COEF * bool(shot_event.get("under_pressure", False))
    )
    if shot_event.get("shot_type") == "free_kick":
        logit += FREE_KICK_COEF
    return 1.0 / (1.0 + math.exp(-logit))
