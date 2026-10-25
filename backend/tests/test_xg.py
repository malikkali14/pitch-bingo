"""Tests for the xG model in SPEC section 7.3."""

import math

import pytest

from app.stats.xg import PENALTY_XG, goal_angle, xg

PITCH_LENGTH = 105.0
CENTER_Y = 34.0


def logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def shot(x: float, y: float, **extra: object) -> dict[str, object]:
    """A shot event shaped like SPEC 6.3/6.4, attacking the x = 105 goal by default."""
    event: dict[str, object] = {
        "type": "shot",
        "x": x,
        "y": y,
        "under_pressure": False,
        "shot_type": "open_play",
        "body_part": "right_foot",
        "outcome": "saved",
    }
    event.update(extra)
    return event


# --- Sanity checks listed in 7.3 -------------------------------------------


@pytest.mark.parametrize(
    ("distance", "expected"),
    [(6.0, 0.47), (11.0, 0.20), (25.0, 0.03)],
)
def test_spec_sanity_checks_central(distance: float, expected: float) -> None:
    assert xg(shot(PITCH_LENGTH - distance, CENTER_Y)) == pytest.approx(expected, abs=0.01)


# --- Penalty spot ----------------------------------------------------------


def test_penalty_is_fixed_regardless_of_modifiers() -> None:
    event = shot(PITCH_LENGTH - 11.0, CENTER_Y, shot_type="penalty", under_pressure=True)
    assert xg(event) == PENALTY_XG == 0.78
    assert xg(event, assisted_chance=True) == 0.78


def test_open_play_shot_from_penalty_spot_uses_the_formula() -> None:
    # dx = 11, dy = 0: a = atan2(80.52, 107.6), d = 11
    a = math.atan2(7.32 * 11, 11**2 - 13.4)
    expected = logistic(-1.2 + 1.6 * a - 0.11 * 11)
    assert xg(shot(PITCH_LENGTH - 11.0, CENTER_Y)) == pytest.approx(expected)
    assert expected < PENALTY_XG


# --- Near the touchline ----------------------------------------------------


def test_shot_from_near_touchline_is_tiny() -> None:
    # 1 m from the goal line, 2 m from the touchline: almost no angle to aim at.
    value = xg(shot(104.0, 2.0))
    a = math.atan2(7.32 * 1, 1 + 32**2 - 13.4)
    d = math.hypot(1, 32)
    assert value == pytest.approx(logistic(-1.2 + 1.6 * a - 0.11 * d))
    assert value < 0.01


def test_shot_from_goal_line_wide_of_post_has_zero_angle() -> None:
    assert goal_angle(0.0, 10.0) == pytest.approx(0.0)
    value = xg(shot(PITCH_LENGTH, CENTER_Y + 10.0))
    assert value == pytest.approx(logistic(-1.2 - 0.11 * 10))


def test_angle_is_widest_on_the_goal_line_between_the_posts() -> None:
    assert goal_angle(0.0, 0.0) == pytest.approx(math.pi)


def test_wider_shot_has_lower_xg_than_central_at_same_depth() -> None:
    assert xg(shot(95.0, 10.0)) < xg(shot(95.0, 25.0)) < xg(shot(95.0, CENTER_Y))


# --- Headers and other modifiers -------------------------------------------


def test_header_subtracts_point_eight_from_logit() -> None:
    foot = xg(shot(99.0, CENTER_Y))
    header = xg(shot(99.0, CENTER_Y, shot_type="header", body_part="head"))
    assert math.log(header / (1 - header)) == pytest.approx(math.log(foot / (1 - foot)) - 0.8)
    assert header < foot


def test_head_body_part_counts_as_header() -> None:
    by_type = xg(shot(99.0, CENTER_Y, shot_type="header"))
    by_body = xg(shot(99.0, CENTER_Y, body_part="head"))
    assert by_type == pytest.approx(by_body)


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def test_pressure_subtracts_point_three() -> None:
    base = xg(shot(94.0, 30.0))
    pressed = xg(shot(94.0, 30.0, under_pressure=True))
    assert _logit(pressed) == pytest.approx(_logit(base) - 0.3)


def test_assisted_chance_adds_point_four() -> None:
    base = xg(shot(94.0, 30.0))
    assisted = xg(shot(94.0, 30.0), assisted_chance=True)
    assert _logit(assisted) == pytest.approx(_logit(base) + 0.4)


def test_direct_free_kick_subtracts_point_six() -> None:
    base = xg(shot(83.0, CENTER_Y))
    free_kick = xg(shot(83.0, CENTER_Y, shot_type="free_kick"))
    assert _logit(free_kick) == pytest.approx(_logit(base) - 0.6)


# --- Attacking direction ---------------------------------------------------


def test_nearer_goal_used_when_direction_unknown() -> None:
    right = xg(shot(PITCH_LENGTH - 11.0, CENTER_Y))
    left = xg(shot(11.0, CENTER_Y))
    assert left == pytest.approx(right)


def test_attacking_right_overrides_nearer_goal() -> None:
    # Shot at x = 11 aimed at the far (x = 105) goal: a 94 m effort.
    far = xg(shot(11.0, CENTER_Y), attacking_right=True)
    near = xg(shot(11.0, CENTER_Y), attacking_right=False)
    assert near == pytest.approx(xg(shot(11.0, CENTER_Y)))
    assert far < 0.001


def test_result_is_a_probability() -> None:
    for x in (0.0, 30.0, 52.5, 80.0, 105.0):
        for y in (0.0, 20.0, 34.0, 68.0):
            value = xg(shot(x, y))
            assert 0.0 < value < 1.0
            assert isinstance(value, float)
