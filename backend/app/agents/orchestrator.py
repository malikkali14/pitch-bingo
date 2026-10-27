"""Runs a session's agents in the background and hands results back to the session.

Nothing here blocks the match: each LLM call is its own task, and its result reaches the
viewer through `publish`, which the session applies on the event loop (spec 8.3). With no
Foundry client every agent is offline and the templates stand.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from app.agents import narrator
from app.agents.clients import ChatClients
from app.agents.messages import Insight
from app.agents.runner import AgentRunner
from app.game.card import Profile
from app.verify.verifier import LIMITS, verify_line

log = logging.getLogger(__name__)

Publish = Callable[[dict[str, Any]], None]
MAX_IN_FLIGHT = {"narrator": 3}   # past this, a moment keeps its template line


class Orchestrator:
    def __init__(self, clients: ChatClients | None, meta: dict[str, Any],
                 profile: Callable[[], Profile], publish: Publish,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.clients = clients
        self.meta = meta
        self.profile = profile
        self.publish = publish
        self.now = now
        self.names = narrator.Names(meta)
        self.runners = {"narrator": AgentRunner(narrator.SPEC, clients, now)}
        self.in_flight: dict[str, int] = {name: 0 for name in self.runners}
        self.skipped: dict[str, int] = {name: 0 for name in self.runners}
        self.tasks: set[asyncio.Task[None]] = set()

    @property
    def online(self) -> bool:
        return self.clients is not None

    # ---- moments (spec 8.4, moment workflow) ---------------------------------------------

    def on_event(self, event: dict[str, Any], significance: int,
                 triggers: list[dict[str, Any]], milestones: list[dict[str, Any]],
                 stats: Callable[[], dict[str, Any]], held: bool,
                 shot_xg: float | None = None) -> None:
        if not self.online or not narrator.wants_line(significance, triggers):
            return
        moment = narrator.build_moment(event, significance, stats(), triggers, milestones,
                                       self.names, shot_xg)
        self._spawn("narrator", self._narrate(event, moment, held))

    async def _narrate(self, event: dict[str, Any], moment: dict[str, Any], held: bool) -> None:
        mode = self.profile().mode
        limit = LIMITS[mode]

        def check(insight: Insight) -> tuple[str | None, list[str]]:
            text = narrator.render(insight, limit)
            if text is None:
                return None, [f"the headline must fit in {limit} characters"]
            return text, verify_line(text, moment, self.meta, mode)

        outcome = await self.runners["narrator"].run(moment, check)
        if outcome.value is not None:
            # Replaces the template line in place; a held line stays held until revealed.
            self.publish({"type": "feed.replace", "entry_id": event["event_id"],
                          "text": outcome.value, "ai": True, "clock": event["clock"],
                          "event_type": event["type"], "held": held})

    # ---- plumbing ------------------------------------------------------------------------

    def _spawn(self, agent: str, work: Coroutine[Any, Any, None]) -> None:
        if self.in_flight[agent] >= MAX_IN_FLIGHT.get(agent, 4):
            self.skipped[agent] += 1
            work.close()
            return
        self.in_flight[agent] += 1

        async def run() -> None:
            try:
                await work
            except Exception:
                log.exception("agent %s task failed", agent)
            finally:
                self.in_flight[agent] -= 1

        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def drain(self) -> None:
        """Wait for every running call (tests, and a clean shutdown)."""
        while self.tasks:
            await asyncio.gather(*list(self.tasks))

    def cancel(self) -> None:
        for task in list(self.tasks):
            task.cancel()

    def health(self) -> dict[str, Any]:
        now = self.now()
        return {name: {**runner.health.snapshot(now), "skipped": self.skipped[name]}
                for name, runner in self.runners.items()}
