"""Planted moments (spec 6.7): one scripted scenario per live-square segment.

Each scenario runs on the club currently on the ball. It first moves the ball to its starting
spot with a completed pass, so the replay has no jumps, then plays out the scripted moment.
Every event a scenario emits is tagged "planted", "moment:<name>" and "segment:<n>".
"""

from collections.abc import Callable

from app.generator.sim import Sim

DEFAULT_PLANTS = [
    "advantage_then_shot",
    "offside_through_ball",
    "long_range_tip_over",
    "thirteen_pass_block",
    "switch_then_wide",
]


def advantage_then_shot(sim: Sim, tags: list[str]) -> None:
    """Foul with advantage played, then a shot. Asks: advantage / xG of the shot."""
    sim.bridge(64, sim.rng.uniform(24, 44))
    sim.foul(by_attacker=False, advantage=True, severity=0.2)
    sim.pass_ball(forced=("open_play", sim.rng.uniform(87, 92), sim.rng.uniform(26, 42)),
                  outcome="complete")
    sim.shoot(shot_type="open_play")


def offside_through_ball(sim: Sim, tags: list[str]) -> None:
    """Through ball with the receiver just offside. Asks: offside / pass length."""
    sim.bridge(56, sim.rng.uniform(26, 42))
    sim.pass_ball(forced=("through_ball", sim.u + sim.rng.uniform(24, 30),
                          sim.v + sim.rng.uniform(-6, 6)), outcome="offside")


def long_range_tip_over(sim: Sim, tags: list[str]) -> None:
    """30 m strike tipped over the bar. Asks: corner / shot speed."""
    sim.bridge(75, sim.rng.uniform(31, 37))
    sim.shoot(shot_type="open_play", outcome="saved", speed=sim.rng.uniform(104, 116),
              rebound="corner")


def thirteen_pass_block(sim: Sim, tags: list[str]) -> None:
    """13-pass move ending in a blocked shot. Asks: restart / number of passes."""
    sim.bridge(28, sim.rng.uniform(20, 48))
    # The move counts every pass of this possession, including any before the scenario.
    remaining = 13 - sim.passes_in_possession()
    start_u = sim.u
    for i in range(remaining):
        u = start_u + (i + 1) * (90 - start_u) / remaining
        v = 34 + (14 if i % 2 else -14) * (0.4 + 0.6 * sim.rng.random())
        if i == remaining - 1:
            v = sim.rng.uniform(28, 40)
        sim.pass_ball(forced=("open_play", u, v), outcome="complete")
    sim.shoot(shot_type="open_play", outcome="blocked", rebound="corner")


def switch_then_wide(sim: Sim, tags: list[str]) -> None:
    """45 m switch, then a shot that goes wide. Asks: goal kick / pass length."""
    start_v = sim.rng.uniform(7, 11)
    sim.bridge(58, start_v)
    sim.pass_ball(forced=("switch", 68, start_v + 44), outcome="complete")
    sim.pass_ball(forced=("open_play", sim.rng.uniform(83, 87), sim.rng.uniform(38, 46)),
                  outcome="complete")
    sim.shoot(shot_type="open_play", outcome="off_target")


SCENARIOS: dict[str, Callable[[Sim, list[str]], None]] = {
    f.__name__: f
    for f in (
        advantage_then_shot,
        offside_through_ball,
        long_range_tip_over,
        thirteen_pass_block,
        switch_then_wide,
    )
}
