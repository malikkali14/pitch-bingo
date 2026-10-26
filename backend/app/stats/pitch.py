"""Pitch geometry shared by the stats modules. Coordinates are absolute metres (spec 6.3)."""

import math

from app.stats.xg import PITCH_LENGTH_M, PITCH_WIDTH_M

BOX_DEPTH_M = 16.5
BOX_HALF_WIDTH_M = 20.16
FINAL_THIRD_M = 35.0


def from_own_goal(x: float, attack_right: bool) -> float:
    """Distance up the pitch from the goal line a club defends."""
    return x if attack_right else PITCH_LENGTH_M - x


def to_goal_line(x: float, attack_right: bool) -> float:
    """Distance to the goal line a club attacks."""
    return PITCH_LENGTH_M - x if attack_right else x


def to_goal(x: float, y: float, attack_right: bool) -> float:
    """Straight-line distance to the centre of the goal a club attacks."""
    return math.hypot(to_goal_line(x, attack_right), y - PITCH_WIDTH_M / 2)


def in_final_third(x: float, attack_right: bool) -> bool:
    return to_goal_line(x, attack_right) <= FINAL_THIRD_M


def in_box(x: float, y: float, attack_right: bool) -> bool:
    """Inside the penalty area a club attacks."""
    return (to_goal_line(x, attack_right) <= BOX_DEPTH_M
            and abs(y - PITCH_WIDTH_M / 2) <= BOX_HALF_WIDTH_M)


def in_own_box(x: float, y: float, attack_right: bool) -> bool:
    return in_box(x, y, not attack_right)
