"""Pass completion model and pass difficulty (SPEC section 7.2).

The generator samples pass outcomes from this same model, so keep it pure.
"""

import math
from collections.abc import Mapping
from typing import Any

# Starting coefficients from 7.2. Tune INTERCEPT so average completion lands near 82%.
INTERCEPT = 3.2
LENGTH_COEF = -0.045
PRESSURE_COEF = -0.9
BYPASSED_COEF = -0.35
THROUGH_BALL_COEF = -0.6
CROSS_COEF = -0.8
HIGH_COEF = -0.4
BACKWARD_COEF = 0.25


def _is_backward(pass_event: Mapping[str, Any], attacking_right: bool | None) -> bool:
    # Without a known attacking direction there is no reliable way to tell, so the
    # backward bonus is left off.
    if attacking_right is None:
        return False
    dx = float(pass_event["end_x"]) - float(pass_event["x"])
    return dx < 0 if attacking_right else dx > 0


def pass_completion_probability(
    pass_event: Mapping[str, Any], *, attacking_right: bool | None = None
) -> float:
    """Chance p that the pass is completed.

    attacking_right says whether the passer's team attacks the x = 105 goal; it is
    needed only for the backward-pass term, which is skipped when it is None.
    """
    length = pass_event.get("length_m")
    if length is None:
        length = math.hypot(
            float(pass_event["end_x"]) - float(pass_event["x"]),
            float(pass_event["end_y"]) - float(pass_event["y"]),
        )
    pass_type = pass_event.get("pass_type")
    logit = (
        INTERCEPT
        + LENGTH_COEF * float(length)
        + PRESSURE_COEF * bool(pass_event.get("under_pressure", False))
        + BYPASSED_COEF * float(pass_event.get("opponents_bypassed", 0))
        + THROUGH_BALL_COEF * (pass_type == "through_ball")
        + CROSS_COEF * (pass_type == "cross")
        + HIGH_COEF * (pass_event.get("height") == "high")
        + BACKWARD_COEF * _is_backward(pass_event, attacking_right)
    )
    return 1.0 / (1.0 + math.exp(-logit))


def pass_difficulty(pass_event: Mapping[str, Any], *, attacking_right: bool | None = None) -> float:
    """Difficulty from 0 to 10: 10 x (1 - p), to one decimal."""
    p = pass_completion_probability(pass_event, attacking_right=attacking_right)
    return round(10.0 * (1.0 - p), 1)
