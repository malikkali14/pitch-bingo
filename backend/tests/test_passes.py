"""Tests for the pass completion model in SPEC section 7.2."""

import math

import pytest

from app.stats.passes import pass_completion_probability, pass_difficulty


def logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def pass_event(
    x: float, y: float, end_x: float, end_y: float, **extra: object
) -> dict[str, object]:
    """A pass event shaped like SPEC 6.3/6.4."""
    event: dict[str, object] = {
        "type": "pass",
        "x": x,
        "y": y,
        "end_x": end_x,
        "end_y": end_y,
        "length_m": math.hypot(end_x - x, end_y - y),
        "height": "ground",
        "pass_type": "open_play",
        "outcome": "complete",
        "under_pressure": False,
        "opponents_bypassed": 0,
    }
    event.update(extra)
    return event


# --- Short safe pass -------------------------------------------------------


def test_short_safe_pass() -> None:
    event = pass_event(40.0, 30.0, 48.0, 30.0)  # 8 m forward on the ground
    p = pass_completion_probability(event, attacking_right=True)
    assert p == pytest.approx(logistic(3.2 - 0.045 * 8))  # ~0.945
    assert pass_difficulty(event, attacking_right=True) == 0.6


# --- Long pass under pressure ----------------------------------------------


def test_long_high_pass_under_pressure_bypassing_players() -> None:
    event = pass_event(
        30.0,
        34.0,
        80.0,
        34.0,
        height="high",
        pass_type="long_ball",
        under_pressure=True,
        opponents_bypassed=3,
    )
    p = pass_completion_probability(event, attacking_right=True)
    assert p == pytest.approx(logistic(3.2 - 0.045 * 50 - 0.9 - 0.35 * 3 - 0.4))  # ~0.198
    assert pass_difficulty(event, attacking_right=True) == 8.0


def test_long_pass_under_pressure_is_harder_than_short_safe_pass() -> None:
    short = pass_event(40.0, 30.0, 48.0, 30.0)
    long = pass_event(30.0, 34.0, 80.0, 34.0, height="high", under_pressure=True)
    assert pass_difficulty(long) > pass_difficulty(short)


# --- Individual terms ------------------------------------------------------


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


@pytest.mark.parametrize(
    ("field", "value", "delta"),
    [
        ("under_pressure", True, -0.9),
        ("pass_type", "through_ball", -0.6),
        ("pass_type", "cross", -0.8),
        ("height", "high", -0.4),
        ("height", "low", 0.0),
        ("opponents_bypassed", 2, -0.7),
    ],
)
def test_each_term_shifts_the_logit(field: str, value: object, delta: float) -> None:
    base = pass_event(50.0, 34.0, 70.0, 34.0)
    changed = pass_event(50.0, 34.0, 70.0, 34.0, **{field: value})
    p0 = pass_completion_probability(base, attacking_right=True)
    p1 = pass_completion_probability(changed, attacking_right=True)
    assert _logit(p1) == pytest.approx(_logit(p0) + delta)


def test_backward_pass_adds_point_two_five_when_direction_known() -> None:
    forward = pass_event(50.0, 34.0, 60.0, 34.0)
    backward = pass_event(50.0, 34.0, 40.0, 34.0)
    pf = pass_completion_probability(forward, attacking_right=True)
    pb = pass_completion_probability(backward, attacking_right=True)
    assert _logit(pb) == pytest.approx(_logit(pf) + 0.25)
    # Same passes for a team attacking left: roles swap.
    assert pass_completion_probability(forward, attacking_right=False) == pytest.approx(pb)
    assert pass_completion_probability(backward, attacking_right=False) == pytest.approx(pf)


def test_backward_term_off_when_direction_unknown() -> None:
    backward = pass_event(50.0, 34.0, 40.0, 34.0)
    assert pass_completion_probability(backward) == pytest.approx(logistic(3.2 - 0.045 * 10))


def test_sideways_pass_is_not_backward() -> None:
    sideways = pass_event(50.0, 20.0, 50.0, 40.0)
    assert pass_completion_probability(sideways, attacking_right=True) == pytest.approx(
        logistic(3.2 - 0.045 * 20)
    )


def test_length_falls_back_to_coordinates() -> None:
    event = pass_event(10.0, 10.0, 13.0, 14.0)
    del event["length_m"]
    assert pass_completion_probability(event, attacking_right=True) == pytest.approx(
        logistic(3.2 - 0.045 * 5)
    )


def test_length_m_field_takes_precedence() -> None:
    event = pass_event(10.0, 10.0, 13.0, 14.0, length_m=20.0)
    assert pass_completion_probability(event, attacking_right=True) == pytest.approx(
        logistic(3.2 - 0.045 * 20)
    )


# --- Difficulty shape ------------------------------------------------------


def test_difficulty_is_ten_times_miss_chance_to_one_decimal() -> None:
    event = pass_event(20.0, 5.0, 90.0, 60.0, pass_type="cross", height="high")
    p = pass_completion_probability(event, attacking_right=True)
    d = pass_difficulty(event, attacking_right=True)
    assert d == round(10 * (1 - p), 1)
    assert 0.0 <= d <= 10.0


def test_outcome_does_not_affect_model() -> None:
    complete = pass_event(50.0, 34.0, 70.0, 34.0, outcome="complete")
    missed = pass_event(50.0, 34.0, 70.0, 34.0, outcome="incomplete")
    assert pass_completion_probability(complete) == pass_completion_probability(missed)
