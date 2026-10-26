import pytest
from factories import AWAY, HOME, SEEDS, Log, load_events, load_meta

from app.stats.engine import StatsEngine

CALIBRATION = {
    "chaos": {"T": [0.0, 2.0], "D": [0.0, 2.0], "C": [0.5, 1.0], "S": [0.0, 1.0]},
    "tempo_terciles": [10.0, 20.0],
}


def engine(calibration: dict | None = CALIBRATION) -> StatsEngine:
    return StatsEngine(load_meta(2610), calibration=calibration)


def feed(events: list[dict], calibration: dict | None = CALIBRATION) -> tuple[StatsEngine,
                                                                               list[dict]]:
    stats = engine(calibration)
    triggers: list[dict] = []
    for event in events:
        triggers += stats.on_event(event).triggers
    return stats, triggers


# ---- 7.4 control vs. chaos ---------------------------------------------------------------

def test_chaos_hand_worked() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t in (10, 20, 30, 40, 50, 60):                 # possession 0: six completed passes
        log.pass_(t)
    log.change(70, AWAY)
    log.pass_(80, AWAY, "KVL-08")
    log.pass_(90, AWAY, "KVL-08", outcome="incomplete")
    log.change(100, HOME, cause="interception")
    log.pass_(110, outcome="incomplete")
    log.change(120, AWAY)
    log.add("duel", 130, AWAY, "KVL-09", duel_type="ground", opponent_id="NBA-04",
            outcome="won")
    log.add("duel", 140, AWAY, "KVL-09", duel_type="ground", opponent_id="NBA-04",
            outcome="won")
    log.change(150, HOME)
    log.pass_(290)
    log.add("carry", 300, HOME, "NBA-08", end_x=60.0, end_y=34.0, duration_s=2.0)
    stats, _ = feed(log.events)
    chaos = stats.snapshot()["patterns"]["chaos"]
    # T = 4 changes / 5 min = 0.8 -> 0.4; D = 0.4 -> 0.2; C = 8/10 -> 0.6; S = 1/5 -> 0.2
    assert chaos["inputs"] == pytest.approx({"T": 0.8, "D": 0.4, "C": 0.8, "S": 0.2})
    assert chaos["value"] == pytest.approx(100 * (0.4 * 0.4 + 0.25 * 0.2 + 0.2 * 0.4
                                                  + 0.15 * 0.8))
    assert chaos["in_control"] == HOME


def test_chaos_window_is_five_minutes() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t in range(10, 100, 10):
        log.change(t, AWAY if (t // 10) % 2 else HOME)
    log.pass_(500)
    stats, _ = feed(log.events)
    assert stats.snapshot()["patterns"]["chaos"]["inputs"]["T"] == 0.0


@pytest.mark.parametrize("seed", SEEDS)
def test_chaos_stays_within_0_and_100_and_moves(seed: int) -> None:
    stats = StatsEngine(load_meta(seed))
    values = []
    for event in load_events(seed):
        stats.on_event(event)
        value = stats.snapshot()["patterns"]["chaos"]["value"]
        if value is not None:
            values.append(value)
    assert values and all(0 <= v <= 100 for v in values)
    assert max(values) - min(values) > 20


# ---- 7.5 pressure ------------------------------------------------------------------------

def test_ppda_and_pressing_height_hand_worked() -> None:
    # First half: NBA attacks x = 105, so KVL's own 60% is x >= 42.
    log = Log()
    log.add("kickoff", 0, AWAY, "KVL-09")
    for t in range(10, 70, 10):                        # six KVL passes inside the zone
        log.pass_(t, AWAY, "KVL-04", x=80, end_x=70)
    log.pass_(70, AWAY, "KVL-04", x=30, end_x=20)      # two outside it
    log.pass_(80, AWAY, "KVL-04", x=30, end_x=20)
    log.add("tackle", 90, HOME, "NBA-09", x=70, opponent_id="KVL-04", outcome="lost")
    log.add("interception", 100, HOME, "NBA-08", x=60)
    log.add("foul", 110, HOME, "NBA-08", x=50, fouled_id="KVL-04", severity=0.1,
            advantage=True)
    log.add("foul", 120, HOME, "NBA-04", x=20, fouled_id="KVL-09", severity=0.1,
            advantage=True)
    log.add("duel", 130, AWAY, "KVL-09", x=75, duel_type="ground", opponent_id="NBA-04",
            outcome="won")
    stats, _ = feed(log.events)
    pressure = stats.snapshot()["patterns"]["pressure"][HOME]
    assert pressure["ppda"] == pytest.approx(6 / 4)
    assert pressure["pressing_height_m"] == pytest.approx((70 + 60 + 50 + 20 + 75) / 5)


def test_field_tilt_hand_worked() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t in (10, 20, 30):
        log.pass_(t, HOME, x=60, end_x=80)             # into NBA's final third (x >= 70)
    log.pass_(40, HOME, x=60, end_x=80, outcome="incomplete")
    log.pass_(50, HOME, x=40, end_x=60)
    log.change(60, AWAY)
    log.pass_(70, AWAY, "KVL-08", x=50, end_x=30)      # into KVL's final third (x <= 35)
    stats, _ = feed(log.events)
    pressure = stats.snapshot()["patterns"]["pressure"]
    assert pressure[HOME]["field_tilt"] == pytest.approx(75.0)
    assert pressure[AWAY]["field_tilt"] == pytest.approx(25.0)


def test_three_high_regains_in_five_minutes_triggers_once() -> None:
    log = Log()
    log.add("kickoff", 0, AWAY, "KVL-09")
    for t in (100, 200, 300, 350):
        log.change(t, HOME, cause="tackle", x=90)      # 15 m from KVL's goal at x = 105
        log.change(t + 5, AWAY, cause="out_of_play")
    stats, triggers = feed(log.events)
    regains = [t for t in triggers if t["kind"] == "high_regains"]
    assert len(regains) == 1 and regains[0]["team_id"] == HOME
    assert stats.snapshot()["patterns"]["pressure"][HOME]["high_regains"] == 4


def test_low_regains_do_not_count() -> None:
    log = Log()
    log.add("kickoff", 0, AWAY, "KVL-09")
    for t in (100, 200, 300):
        log.change(t, HOME, cause="tackle", x=30)
        log.change(t + 5, AWAY, cause="out_of_play")
    stats, triggers = feed(log.events)
    assert not [t for t in triggers if t["kind"] == "high_regains"]


def test_ppda_drop_of_40_percent_triggers() -> None:
    log = Log()
    log.add("kickoff", 0, AWAY, "KVL-09")
    for t in range(10, 510, 10):                       # first 10 min: 50 passes, 5 actions
        log.pass_(t, AWAY, "KVL-04", x=80, end_x=70)
    for t in range(515, 565, 10):
        log.add("interception", t, HOME, "NBA-08", x=70)
    for t in range(610, 1110, 50):                     # next 10 min: 10 passes, 5 actions
        log.pass_(t, AWAY, "KVL-04", x=80, end_x=70)
    for t in range(1115, 1165, 10):
        log.add("interception", t, HOME, "NBA-08", x=70)
    log.add("carry", 1200, AWAY, "KVL-04", end_x=70.0, end_y=34.0, duration_s=1.0)
    _, triggers = feed(log.events)
    drops = [t for t in triggers if t["kind"] == "ppda_drop"]
    assert len(drops) == 1 and drops[0]["team_id"] == HOME


# ---- 7.6 rhythm --------------------------------------------------------------------------

def test_four_minutes_without_a_stoppage_triggers_once_per_spell() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t in range(10, 300, 10):
        log.pass_(t)
    log.add("out_of_play", 300, HOME, last_touch_team_id=HOME)
    log.change(300, AWAY, cause="out_of_play")
    log.add("throw_in", 310, AWAY, "KVL-02", side="left")
    for t in range(320, 500, 10):
        log.pass_(t, AWAY, "KVL-08")
    stats, triggers = feed(log.events)
    spells = [t for t in triggers if t["kind"] == "long_spell"]
    assert len(spells) == 1 and spells[0]["t"] == 240
    assert stats.snapshot()["patterns"]["rhythm"]["since_stoppage_s"] == pytest.approx(180)


def test_rhythm_rates_and_tempo_label() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    for t in range(5, 605, 5):                          # 120 passes in 10 minutes
        log.pass_(t)
    stats, _ = feed(log.events)
    rhythm = stats.snapshot()["patterns"]["rhythm"]
    assert rhythm["passes_per_min"] == pytest.approx(12.0)
    assert rhythm["events_per_min"] == pytest.approx(12.1, abs=0.05)
    assert rhythm["in_play_share"] == pytest.approx(100.0)
    assert rhythm["tempo"] == "Steady"


def test_tempo_change_must_hold_three_minutes() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    t = 0.0
    while t < 600:                                      # 6 a minute: Slow
        t += 10
        log.pass_(t)
    while t < 1500:                                     # 30 a minute: Frantic
        t += 2
        log.pass_(t)
    _, triggers = feed(log.events)
    changes = [x for x in triggers if x["kind"] == "tempo_change"]
    assert changes and changes[0]["value"] in ("Steady", "Frantic")
    assert all(b["t"] - a["t"] >= 180 for a, b in zip(changes, changes[1:], strict=False))


# ---- 7.7 momentum ------------------------------------------------------------------------

def test_threat_decays_with_a_three_minute_half_life() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.add("corner", 0, HOME, "NBA-07", side="left")
    log.add("corner", 180, AWAY, "KVL-07", side="left")
    stats, _ = feed(log.events)
    momentum = stats.snapshot()["patterns"]["momentum"]
    assert momentum["threat"][HOME] == pytest.approx(0.75)
    assert momentum["threat"][AWAY] == pytest.approx(1.5)
    assert momentum["value"] == pytest.approx(100 * (0.75 - 1.5) / 2.25, abs=0.1)


def test_threat_points() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.pass_(0, x=60, end_x=80, end_y=34)              # final third: 0.3
    log.pass_(0, x=80, end_x=95, end_y=34)              # final third 0.3 and box entry 1
    log.pass_(0, x=96, end_x=100, end_y=34)             # already in the box: 0.3
    log.pass_(0, x=60, end_x=80, outcome="incomplete")  # nothing
    log.change(0, HOME, cause="tackle", x=90)           # high regain: 1
    stats, _ = feed(log.events)
    assert stats.snapshot()["patterns"]["momentum"]["threat"][HOME] == pytest.approx(2.9)


def test_momentum_side_change_must_hold_two_minutes() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.add("corner", 0, HOME, "NBA-07", side="left")
    log.add("corner", 10, AWAY, "KVL-07", side="left")
    log.add("corner", 10, AWAY, "KVL-07", side="left")
    log.pass_(60, AWAY, "KVL-08")                       # held 50 s: no trigger yet
    log.pass_(140, AWAY, "KVL-08")                      # held 130 s: trigger
    _, triggers = feed(log.events)
    sides = [t for t in triggers if t["kind"] == "momentum_side"]
    assert len(sides) == 1 and sides[0]["team_id"] == AWAY and sides[0]["t"] == 140


def test_seventy_percent_for_five_minutes_triggers() -> None:
    log = Log()
    log.add("kickoff", 0, HOME, "NBA-09")
    log.add("corner", 0, HOME, "NBA-07", side="left")
    for t in range(30, 400, 30):
        log.pass_(t)
    _, triggers = feed(log.events)
    holds = [t for t in triggers if t["kind"] == "momentum_hold"]
    assert len(holds) == 1 and holds[0]["team_id"] == HOME and holds[0]["t"] == 300


# ---- whole matches -----------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_real_matches_trigger_patterns_without_spamming(seed: int) -> None:
    stats = StatsEngine(load_meta(seed))
    triggers: list[dict] = []
    for event in load_events(seed):
        triggers += stats.on_event(event).triggers
    # The spec thresholds give about 70 a match today (chaos swings fire at their
    # once-per-5-minutes ceiling). This bound catches regressions; tuning is still open.
    assert 3 <= len(triggers) <= 90
    assert all(t["pattern"] in ("chaos", "pressure", "rhythm", "momentum") for t in triggers)
