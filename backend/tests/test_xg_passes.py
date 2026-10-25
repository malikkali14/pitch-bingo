import pytest

from app.stats.passes import completion_probability, difficulty
from app.stats.xg import shot_xg


@pytest.mark.parametrize("distance, expected", [(6, 0.47), (11, 0.20), (25, 0.03)])
def test_central_xg_matches_spec(distance: float, expected: float) -> None:
    assert shot_xg(distance, 0) == pytest.approx(expected, abs=0.03)


def test_penalty_is_fixed() -> None:
    assert shot_xg(11, 0, shot_type="penalty") == 0.78


def test_header_free_kick_and_pressure_lower_xg() -> None:
    base = shot_xg(12, 3)
    assert shot_xg(12, 3, header=True) < base
    assert shot_xg(12, 3, pressure=True) < base
    assert shot_xg(12, 3, shot_type="free_kick") < base
    assert shot_xg(12, 3, assisted_chance=True) > base


def test_wider_angle_lowers_xg() -> None:
    assert shot_xg(12, 15) < shot_xg(12, 0)


def test_difficulty_rises_with_length_and_pressure() -> None:
    short = difficulty(completion_probability(10))
    long = difficulty(completion_probability(40))
    pressured = difficulty(completion_probability(10, under_pressure=True))
    assert short < long
    assert short < pressured
    assert 0 <= short <= 10 and 0 <= long <= 10


def test_backward_passes_are_easier() -> None:
    assert completion_probability(15, backward=True) > completion_probability(15)
