import asyncio
import math
import time

import pytest
from factories import load_events, load_meta

from app.engine.clock import ReplayClock
from app.engine.source import EventSource, Frame, ReplaySource, Rewind, Tick, available_seeds


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def item_t(item: object) -> float:
    return item["t"] if isinstance(item, dict) else item.t  # type: ignore[index, attr-defined]


@pytest.fixture(scope="module")
def everything() -> list[object]:
    source = ReplaySource(2610, ReplayClock())
    return list(source.items_until(math.inf))


def test_shipped_seeds_are_available() -> None:
    assert {2610, 1107, 4242, 9001} <= set(available_seeds())


def test_unknown_seed_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ReplaySource(1, ReplayClock())


def test_replay_source_is_an_event_source() -> None:
    source = ReplaySource(2610, ReplayClock())
    assert isinstance(source, EventSource)
    assert source.metadata() == load_meta(2610)


def test_every_event_and_frame_comes_out_in_time_order(everything: list[object]) -> None:
    events = [i for i in everything if isinstance(i, dict)]
    frames = [i for i in everything if isinstance(i, Frame)]
    assert events == load_events(2610)
    assert [f.index for f in frames] == list(range(len(frames)))
    assert frames[-1].t >= events[-1]["t"] - 0.1
    times = [item_t(i) for i in everything]
    assert times == sorted(times)


def test_events_come_before_a_frame_at_the_same_time(everything: list[object]) -> None:
    # The first three events sit at t = 0 and must precede frame 0.
    assert [type(i) for i in everything[:4]] == [dict, dict, dict, Frame]


def test_frame_shape(everything: list[object]) -> None:
    frame = next(i for i in everything if isinstance(i, Frame) and i.index == 600)
    assert frame.t == pytest.approx(60.0)
    assert len(frame.ball) == 3 and frame.ball[2] == 0.0
    assert len(frame.players) == 22
    ids = [p[0] for p in frame.players]
    assert len(set(ids)) == 22
    for _, x, y in frame.players:
        assert 0 <= x <= 105 and 0 <= y <= 68


def test_substitution_hands_the_slot_to_the_player_coming_on(everything: list[object]) -> None:
    sub = next(i for i in everything if isinstance(i, dict) and i["type"] == "substitution")
    before = [i for i in everything if isinstance(i, Frame) and i.t < sub["t"]][-1]
    after = next(i for i in everything if isinstance(i, Frame) and i.t > sub["t"])
    ids_before = {p[0] for p in before.players}
    ids_after = {p[0] for p in after.players}
    assert sub["player_off_id"] in ids_before and sub["player_on_id"] not in ids_before
    assert sub["player_on_id"] in ids_after and sub["player_off_id"] not in ids_after


def test_a_sent_off_player_leaves_the_frames(everything: list[object]) -> None:
    red = next(i for i in everything if isinstance(i, dict) and i["type"] == "card"
               and i["card"] in ("red", "second_yellow"))
    later = next(i for i in everything if isinstance(i, Frame) and i.t > red["t"] + 1)
    assert red["player_id"] not in {p[0] for p in later.players}
    assert len(later.players) == 21


async def test_stream_rewinds_after_a_backward_jump() -> None:
    wall = FakeTime()
    clock = ReplayClock(now=wall)
    source = ReplaySource(2610, clock)
    stream = source.stream()
    clock.jump(30)
    seen: list[object] = []
    async for item in stream:
        seen.append(item)
        if isinstance(item, Tick):
            break
    frames = [i for i in seen if isinstance(i, Frame)]
    assert frames[-1].t == pytest.approx(30.0)
    clock.jump(10)
    after: list[object] = []
    async for item in stream:
        after.append(item)
        if isinstance(item, Tick):
            break
    assert isinstance(after[0], Rewind)
    assert [f.t for f in after if isinstance(f, Frame)][0] == 0.0
    assert [f for f in after if isinstance(f, Frame)][-1].t == pytest.approx(10.0)
    await stream.aclose()


@pytest.mark.parametrize("speed", [1, 5, 10])
async def test_stream_is_paced_by_the_clock(speed: int) -> None:
    clock = ReplayClock(speed=speed)
    source = ReplaySource(2610, clock)
    ticks = 0
    last_frame = 0.0
    start = time.monotonic()
    async for item in source.stream():
        if isinstance(item, Frame):
            last_frame = item.t
        if isinstance(item, Tick):
            ticks += 1
        if time.monotonic() - start >= 0.6:
            break
    wall = time.monotonic() - start
    assert last_frame == pytest.approx(wall * speed, abs=0.15 * speed + 0.1)
    # One tick per tenth of a second of wall time, whatever the speed.
    assert 4 <= ticks <= 9
    await asyncio.sleep(0)
