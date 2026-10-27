"""Circuit breaker, timeouts and the failure switch (spec 8.8)."""

import dataclasses
import json
from typing import Any

import pytest
from factories import load_meta
from test_agents_narrator import STATS, shot_event

from app.agents import narrator
from app.agents.breaker import Breaker
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.agents.runner import AgentRunner
from app.game.card import Profile

META = load_meta()
GOOD = json.dumps({"moment_id": "m", "headline_facts": ["A big moment in this match."],
                   "why_facts": [],
                   "tags": [], "evidence_ids": [], "numbers": []})


class Clock:
    def __init__(self) -> None:
        self.s = 1000.0

    def __call__(self) -> float:
        return self.s


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_three_failures_in_60_seconds_open_it(clock):
    b = Breaker(now=clock)
    for _ in range(2):
        b.record(False)
        clock.s += 20
    assert b.state == "closed" and b.allow()
    b.record(False)
    assert b.state == "open" and not b.allow()


def test_failures_spread_over_more_than_60_seconds_dont(clock):
    b = Breaker(now=clock)
    for _ in range(3):
        b.record(False)
        clock.s += 31
    assert b.state == "closed"


def test_after_60_seconds_one_trial_call_decides(clock):
    b = Breaker(now=clock)
    for _ in range(3):
        b.record(False)
    clock.s += 59
    assert not b.allow()
    clock.s += 1
    assert b.state == "half_open"
    assert b.allow() and not b.allow()            # only one trial at a time
    b.record(True)
    assert b.state == "closed" and b.allow()


def test_a_failed_trial_opens_it_again(clock):
    b = Breaker(now=clock)
    for _ in range(3):
        b.record(False)
    clock.s += 60
    assert b.allow()
    b.record(False)
    assert b.state == "open"
    clock.s += 30
    assert not b.allow()


def test_the_failure_switch_forces_it_open(clock):
    b = Breaker(now=clock)
    b.force(True)
    assert b.state == "forced" and not b.allow()
    clock.s += 3600
    assert not b.allow()
    b.force(False)
    assert b.state == "closed" and b.allow()


def runner(replies: Any, clock: Clock, budget: float = 2.0, delay: float = 0.0
           ) -> tuple[AgentRunner, FakeChatClient]:
    fake = FakeChatClient(replies, delay=delay)
    spec = dataclasses.replace(narrator.SPEC, budget_s=budget)
    return AgentRunner(spec, ChatClients(fake, fake, "f", "f"), now=clock), fake


def accept(insight: Any) -> tuple[str, list[str]]:
    return insight.headline_facts[0], []


async def test_a_call_over_budget_times_out(clock):
    r, fake = runner([GOOD], clock, budget=0.02, delay=0.2)
    outcome = await r.run({"x": 1}, accept)
    assert outcome.value is None and outcome.reason == "timeout"
    assert r.health.timeouts == 1 and r.health.fallbacks == 1


async def test_three_failures_send_work_to_the_fallback(clock):
    r, fake = runner([RuntimeError("503")], clock)
    for _ in range(3):
        assert (await r.run({"x": 1}, accept)).reason == "error"
    outcome = await r.run({"x": 1}, accept)
    assert outcome.reason == "breaker" and len(fake.calls) == 3
    assert r.health.snapshot(clock())["breaker"] == "open"
    clock.s += 60
    fake.script = [GOOD]
    assert (await r.run({"x": 1}, accept)).value == "A big moment in this match."
    assert r.breaker.state == "closed"


async def test_verifier_failures_count_toward_the_breaker(clock):
    r, fake = runner([GOOD], clock)

    def reject(insight: Any) -> tuple[str, list[str]]:
        return "x", ["nope"]
    for _ in range(3):
        await r.run({"x": 1}, reject)
    assert r.breaker.state == "open"


async def test_failure_switch_keeps_template_lines(clock):
    fake = FakeChatClient([GOOD])
    published: list[dict[str, Any]] = []
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: Profile(),
                        published.append, now=clock)
    orch.narrator_down(True)
    orch.on_event(shot_event(), 80, [], [], lambda: STATS, False)
    await orch.drain()
    assert published == [] and fake.calls == []
    assert orch.health()["narrator"]["breaker"] == "forced"
    orch.narrator_down(False)
    orch.on_event(shot_event(), 80, [], [], lambda: STATS, False)
    await orch.drain()
    assert len(published) == 1
