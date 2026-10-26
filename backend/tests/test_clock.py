import pytest

from app.engine.clock import ReplayClock


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("speed", [1, 5, 10])
def test_match_time_runs_at_speed(speed: int) -> None:
    wall = FakeTime()
    clock = ReplayClock(speed=speed, now=wall)
    wall.now += 2.0
    assert clock.t() == pytest.approx(2.0 * speed)


def test_speed_change_reanchors() -> None:
    wall = FakeTime()
    clock = ReplayClock(now=wall)
    wall.now += 10
    clock.set_speed(10)
    assert clock.t() == pytest.approx(10)
    wall.now += 1
    assert clock.t() == pytest.approx(20)
    clock.set_speed(5)
    wall.now += 2
    assert clock.t() == pytest.approx(30)


@pytest.mark.parametrize("speed", [0, 2, 3.5, -1])
def test_only_1_5_and_10_are_allowed(speed: float) -> None:
    with pytest.raises(ValueError):
        ReplayClock(speed=speed)
    with pytest.raises(ValueError):
        ReplayClock().set_speed(speed)


def test_pause_freezes_and_resume_continues() -> None:
    wall = FakeTime()
    clock = ReplayClock(speed=5, now=wall)
    wall.now += 1
    clock.pause(True)
    wall.now += 30
    assert clock.t() == pytest.approx(5)
    assert clock.paused
    clock.pause(False)
    wall.now += 1
    assert clock.t() == pytest.approx(10)


def test_speed_change_while_paused_keeps_time_frozen() -> None:
    wall = FakeTime()
    clock = ReplayClock(now=wall)
    wall.now += 4
    clock.pause(True)
    clock.set_speed(10)
    wall.now += 5
    assert clock.t() == pytest.approx(4)
    clock.pause(False)
    wall.now += 1
    assert clock.t() == pytest.approx(14)


def test_jump_moves_time_and_bumps_generation() -> None:
    wall = FakeTime()
    clock = ReplayClock(speed=10, now=wall)
    generation = clock.generation
    clock.jump(1200)
    assert clock.t() == pytest.approx(1200)
    assert clock.generation == generation + 1
    wall.now += 1
    assert clock.t() == pytest.approx(1210)
    with pytest.raises(ValueError):
        clock.jump(-1)


def test_clock_can_start_stopped() -> None:
    wall = FakeTime()
    clock = ReplayClock(now=wall, running=False)
    wall.now += 5
    assert clock.t() == 0
    clock.start()
    wall.now += 5
    assert clock.t() == pytest.approx(5)


def test_wall_delay_until_a_match_time() -> None:
    wall = FakeTime()
    clock = ReplayClock(speed=5, now=wall)
    assert clock.wall_delay(10) == pytest.approx(2)
    assert clock.wall_delay(-5) == 0
    clock.pause(True)
    assert clock.wall_delay(10) is None
