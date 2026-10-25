"""Pass completion model and difficulty (spec 7.2). The generator samples from it too."""

import math

# Tuned so the generator's average completion lands near 82%.
BASE_LOGIT = 2.95


def completion_probability(
    length_m: float,
    *,
    under_pressure: bool = False,
    opponents_bypassed: int = 0,
    through_ball: bool = False,
    cross: bool = False,
    high: bool = False,
    backward: bool = False,
    base: float = BASE_LOGIT,
) -> float:
    logit = (
        base
        - 0.045 * length_m
        - 0.9 * under_pressure
        - 0.35 * opponents_bypassed
        - 0.6 * through_ball
        - 0.8 * cross
        - 0.4 * high
        + 0.25 * backward
    )
    return 1.0 / (1.0 + math.exp(-logit))


def difficulty(p: float) -> float:
    """Pass difficulty from 0 (trivial) to 10 (near impossible), one decimal."""
    return round(10 * (1 - p), 1)


def pass_difficulty(event: dict, attack_right: bool) -> float:
    """Difficulty of a pass event as stored in events.jsonl."""
    end_x = event["end_x"]
    backward = end_x < event["x"] if attack_right else end_x > event["x"]
    p = completion_probability(
        event["length_m"],
        under_pressure=event.get("under_pressure", False),
        opponents_bypassed=event.get("opponents_bypassed", 0),
        through_ball=event["pass_type"] == "through_ball",
        cross=event["pass_type"] == "cross",
        high=event["height"] == "high",
        backward=backward,
    )
    return difficulty(p)
