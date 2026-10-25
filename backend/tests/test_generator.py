import json
from collections import Counter
from pathlib import Path

import jsonschema
import pytest

from app.generator import generate, write_match
from app.generator.planted import SCENARIOS
from app.generator.sim import SEGMENTS
from app.generator.validate import RANGES, run

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
EVENT_TYPES = {
    "period_start", "period_end", "kickoff", "pass", "carry", "shot", "goal", "save", "tackle",
    "interception", "clearance", "block", "pressure", "duel", "foul", "advantage", "card",
    "offside", "throw_in", "corner", "goal_kick", "free_kick", "out_of_play", "substitution",
    "possession_change",
}


@pytest.fixture(scope="module")
def demo() -> dict:
    return generate(2610, with_tracking=False)


def test_same_seed_gives_byte_identical_files(tmp_path: Path) -> None:
    a = write_match(generate(1107), tmp_path / "a")
    b = write_match(generate(1107), tmp_path / "b")
    for name in ("match.json", "events.jsonl", "summary.json", "tracking.npz"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_events_validate_against_schema(demo: dict) -> None:
    schema = json.loads((SCHEMAS / "event.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    for event in demo["events"]:
        validator.validate(event)


def test_match_validates_against_schema(demo: dict) -> None:
    schema = json.loads((SCHEMAS / "match.schema.json").read_text())
    jsonschema.validate(demo["match"], schema)


def test_every_event_type_appears(demo: dict) -> None:
    assert {e["type"] for e in demo["events"]} == EVENT_TYPES


def test_events_are_in_time_order_with_increasing_seq(demo: dict) -> None:
    events = demo["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(a["t"] <= b["t"] for a, b in zip(events, events[1:], strict=False))


def test_possession_change_at_every_change(demo: dict) -> None:
    events = demo["events"]
    for prev, event in zip(events, events[1:], strict=False):
        if event["possession_id"] != prev["possession_id"]:
            assert event["type"] == "possession_change"
            assert event["possession_id"] == prev["possession_id"] + 1


def test_five_planted_moments_one_per_segment(demo: dict) -> None:
    planted = demo["summary"]["planted"]
    assert [p["segment"] for p in planted] == [0, 1, 2, 3, 4]
    for p in planted:
        start, end = SEGMENTS[p["segment"]]
        moment = [e for e in demo["events"] if f"segment:{p['segment'] + 1}" in e["tags"]]
        assert moment, p
        first = moment[0]
        minute = first["t"] / 60 if first["period"] == 1 else None
        if minute is not None:
            assert start <= minute < end


def test_planted_moments_have_their_answers(demo: dict) -> None:
    def moment(name: str) -> list[dict]:
        return [e for e in demo["events"] if f"moment:{name}" in e["tags"]]

    types = Counter(e["type"] for e in moment("advantage_then_shot"))
    assert types["advantage"] == 1 and types["shot"] == 1
    assert any(e["type"] == "offside" for e in moment("offside_through_ball"))
    tip = moment("long_range_tip_over")
    shot = next(e for e in tip if e["type"] == "shot")
    assert shot["outcome"] == "saved" and tip[-1]["type"] == "corner"
    move = moment("thirteen_pass_block")
    shot = next(e for e in move if e["type"] == "shot")
    passes = [e for e in demo["events"] if e["type"] == "pass"
              and e["possession_id"] == shot["possession_id"] and e["seq"] < shot["seq"]]
    assert len(passes) == 13 and shot["outcome"] == "blocked" and move[-1]["type"] == "corner"
    wide = moment("switch_then_wide")
    switch = next(e for e in wide if e["type"] == "pass" and e["pass_type"] == "switch")
    assert 43 <= switch["length_m"] <= 48
    assert wide[-1]["type"] == "goal_kick"


def test_plant_swaps_a_scenario() -> None:
    result = generate(2610, plants={0: "long_range_tip_over"}, with_tracking=False)
    assert result["summary"]["planted"][0]["scenario"] == "long_range_tip_over"
    with pytest.raises(ValueError):
        generate(2610, plants={0: "bicycle_kick"}, with_tracking=False)
    assert len(SCENARIOS) == 5


def test_fifty_seed_means_sit_inside_targets() -> None:
    samples, failures = run(50)
    assert not failures, failures
    assert set(samples) == set(RANGES)
