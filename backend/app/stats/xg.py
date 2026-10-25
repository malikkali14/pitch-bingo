"""Expected goals model (spec 7.3). The generator and the stats engine share it."""

import math

GOAL_WIDTH_M = 7.32
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
PENALTY_XG = 0.78
FREE_KICK_PENALTY = 0.6


def goal_angle(dx: float, dy: float) -> float:
    """Goal-mouth angle in radians seen from dx metres off the goal line, dy off centre."""
    return math.atan2(GOAL_WIDTH_M * dx, dx * dx + dy * dy - 13.4)


def shot_xg(
    dx: float,
    dy: float,
    *,
    header: bool = False,
    assisted_chance: bool = False,
    pressure: bool = False,
    shot_type: str = "open_play",
) -> float:
    """Chance that a shot from (dx, dy) is scored.

    dx is the distance from the goal line being attacked, dy the offset from the centre line.
    """
    if shot_type == "penalty":
        return PENALTY_XG
    d = math.hypot(dx, dy)
    logit = (
        -1.2
        + 1.6 * goal_angle(dx, dy)
        - 0.11 * d
        - 0.8 * header
        + 0.4 * assisted_chance
        - 0.3 * pressure
    )
    if shot_type == "free_kick":
        logit -= FREE_KICK_PENALTY
    return 1.0 / (1.0 + math.exp(-logit))


def attacks_right(team_id: str, period: int, home_team_id: str) -> bool:
    """The home club attacks x = 105 in the first half and x = 0 in the second."""
    return (team_id == home_team_id) == (period == 1)


def shot_offsets(x: float, y: float, right: bool) -> tuple[float, float]:
    """Turn an absolute shot location into (dx, dy) relative to the goal being attacked."""
    dx = PITCH_LENGTH_M - x if right else x
    return max(dx, 0.1), y - PITCH_WIDTH_M / 2
