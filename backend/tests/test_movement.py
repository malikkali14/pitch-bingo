"""The movement model (spec 6.6) and its tracking checks (spec 6.9)."""

import math

import numpy as np
import pytest

from app.generator import generate, movement

ON_BALL = {"kickoff", "pass", "carry", "shot", "clearance", "interception", "save", "throw_in",
           "corner", "goal_kick", "free_kick", "duel"}


@pytest.fixture(scope="module")
def match() -> dict:
    return generate(2610)


def positions(match: dict) -> np.ndarray:
    return match["tracking"]["positions"].astype(float) / 10


def slot_owners(match: dict) -> list[dict[str, int]]:
    """Which slot each player is in, event by event (substitutions hand slots over)."""
    slot_of = {str(pid): i for i, pid in enumerate(match["tracking"]["slot_ids"])}
    out = []
    for e in match["events"]:
        if e["type"] == "substitution" and e["player_off_id"] in slot_of:
            slot_of[e["player_on_id"]] = slot_of.pop(e["player_off_id"])
        out.append(dict(slot_of))
    return out


def test_model_is_the_full_one(match: dict) -> None:
    assert movement.MODEL == "full"
    assert match["summary"]["tracking_model"] == "full"


def test_every_event_sits_on_its_player_within_half_a_metre(match: dict) -> None:
    pos = positions(match)
    checked = 0
    for e, slots in zip(match["events"], slot_owners(match), strict=True):
        slot = slots.get(e["player_id"] or "")
        f = min(round(e["t"] * 10), len(pos) - 1)
        if slot is None or pos[f, slot, 0] < 0:
            continue
        checked += 1
        assert math.hypot(e["x"] - pos[f, slot, 0], e["y"] - pos[f, slot, 1]) <= 0.5, e
    assert checked > 1500


def test_the_ball_is_at_the_players_feet_for_on_ball_actions(match: dict) -> None:
    pos = positions(match)
    near = total = 0
    for e, slots in zip(match["events"], slot_owners(match), strict=True):
        slot = slots.get(e["player_id"] or "")
        if e["type"] not in ON_BALL or slot is None:
            continue
        f = min(round(e["t"] * 10), len(pos) - 1)
        total += 1
        near += math.dist(pos[f, slot], pos[f, 22]) <= 1.0
    # The rest are mostly receivers a few metres short when a quick pass reaches them.
    assert near / total >= 0.9


def test_the_ball_rarely_sits_still_while_in_play(match: dict) -> None:
    pos = positions(match)
    still = np.hypot(*np.diff(pos[:, 22], axis=0).T) < 0.01
    in_play = np.zeros(len(still), dtype=bool)
    live, last = False, 0.0
    for e in match["events"]:
        if live:
            in_play[int(last * 10):int(e["t"] * 10)] = True
        if e["type"] in ("goal", "out_of_play", "offside", "period_end") or (
                e["type"] == "foul" and not e["advantage"]):
            live = False
        if e["type"] in ("kickoff", "throw_in", "corner", "goal_kick", "free_kick"):
            live = True
        if e["type"] == "possession_change" and e["cause"] == "keeper":
            live = False   # the keeper holds it until the next action
        last = e["t"]
    assert (still & in_play).sum() / in_play.sum() <= 0.15


def test_players_move_as_individuals_not_a_block(match: dict) -> None:
    pos = positions(match)
    v = np.diff(pos[:, :22], axis=0)
    for team in (slice(0, 11), slice(11, 22)):
        tv = v[:, team]
        common = tv.mean(axis=1, keepdims=True)
        individual = np.linalg.norm(tv - common, axis=2).mean() / np.linalg.norm(tv, axis=2).mean()
        assert individual >= 0.4


def test_players_respect_their_top_speed(match: dict) -> None:
    pos = positions(match)
    players = {p["id"]: p for t in match["match"]["teams"] for p in t["players"]}
    top = np.array([players[str(pid)]["top_speed_kmh"] for pid in match["tracking"]["slot_ids"]])
    moved = np.hypot(*(pos[5:, :22] - pos[:-5, :22]).transpose(2, 0, 1)) / 0.5 * 3.6
    valid = (pos[5:, :22, 0] >= 0) & (pos[:-5, :22, 0] >= 0)
    over = (moved > top * 1.1 + 1.0) & valid
    assert over.sum() / valid.sum() < 0.001


def test_tracking_measures_land_in_the_calibration_ranges(match: dict) -> None:
    summary = match["summary"]
    assert 9 <= summary["distance_per_outfield_km"] <= 12
    assert 30 <= summary["top_speed_kmh"] <= 36


def test_tracking_is_deterministic() -> None:
    a = generate(1107)["tracking"]["positions"]
    b = generate(1107)["tracking"]["positions"]
    assert np.array_equal(a, b)
