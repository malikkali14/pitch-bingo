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

from app.agents import narrator, recap, square_writer, strategist_reason, tutor
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
        self.runners = {
            "narrator": AgentRunner(narrator.SPEC, clients, now),
            "square_writer": AgentRunner(square_writer.SPEC, clients, now),
            "strategist": AgentRunner(strategist_reason.SPEC, clients, now),
            "rules_tutor": AgentRunner(tutor.TUTOR, clients, now),
            "narrator_context": AgentRunner(tutor.CONTEXT, clients, now),
            "recap": AgentRunner(recap.SPEC, clients, now),
        }
        self.in_flight: dict[str, int] = {name: 0 for name in self.runners}
        self.skipped: dict[str, int] = {name: 0 for name in self.runners}
        self.tasks: set[asyncio.Task[None]] = set()
        self.lines: list[tuple[int, str, str]] = []     # (significance, clock, AI line)

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
            self.lines.append((moment["significance"], event["clock"], outcome.value))
            # Replaces the template line in place; a held line stays held until revealed.
            self.publish({"type": "feed.replace", "entry_id": event["event_id"],
                          "text": outcome.value, "ai": True, "clock": event["clock"],
                          "event_type": event["type"], "held": held})

    # ---- live squares (spec 8.4, the moment workflow's second branch) --------------------

    def write_square(self, pending: dict[str, Any],
                     done: Callable[[square_writer.Wording | None], None]) -> None:
        """Word a live square, then call done (with None for the template wording)."""
        if not self.online:
            done(None)
            return

        async def write() -> None:
            wording = None
            try:
                outcome = await self.runners["square_writer"].run(
                    pending, lambda draft: square_writer.check(draft, pending, self.meta),
                    prompt=square_writer.prompt(pending))
                wording = outcome.value
            finally:
                done(wording)       # the square always opens, worded or not

        self._spawn("square_writer", write(), on_skip=lambda: done(None))

    # ---- strategy (spec 8.4, strategy workflow) ------------------------------------------

    def explain_advice(self, advice: dict[str, Any], board: dict[str, Any],
                       done: Callable[[dict[str, Any]], None]) -> None:
        """Send the advice with the agent's reason, or with the template reason."""
        if not self.online or not advice.get("moves"):
            done(advice)
            return
        payload = strategist_reason.build_input(advice, board)

        async def explain() -> None:
            reason = None
            try:
                outcome = await self.runners["strategist"].run(
                    payload, lambda value: strategist_reason.check(value, payload, self.meta))
                reason = outcome.value
            finally:
                done(advice if reason is None else {**advice, "reason": reason})

        self._spawn("strategist", explain(), on_skip=lambda: done(advice))

    # ---- window close (spec 8.4, window-close workflow) -----------------------------------

    def explain_square(self, square: dict[str, Any]) -> None:
        """Normal mode: the rules tutor. Advanced mode: the narrator's tactical context. The
        template explanation is already up; this replaces it if it passes."""
        if not self.online:
            return
        mode = self.profile().mode
        agent = "rules_tutor" if mode == "normal" else "narrator_context"
        payload = tutor.build_input(square)

        async def explain() -> None:
            outcome = await self.runners[agent].run(
                payload, lambda value: tutor.check(value, payload, self.meta, mode))
            if outcome.value is not None:
                self.publish({"type": "square.explanation", "square_id": square["square_id"],
                              "text": outcome.value, "ai": True})

        self._spawn(agent, explain())

    # ---- recaps (spec 8.4, recap workflow) -----------------------------------------------

    def write_recap(self, summary: recap.Summary) -> None:
        """The template recap at once, then the recap agent's version if it passes."""
        fallback = recap.template(summary)
        self.publish({"type": "recap", **fallback.model_dump()})
        if not self.online:
            return

        async def write() -> None:
            outcome = await self.runners["recap"].run(
                summary.payload(), lambda content: recap.check(content, summary, self.meta))
            if outcome.value is not None:
                self.publish({"type": "recap", **outcome.value.model_dump()})

        self._spawn("recap", write())

    def narrator_down(self, on: bool) -> None:
        """The dev panel's failure switch (spec 3, 8.8)."""
        self.runners["narrator"].breaker.force(on)

    # ---- plumbing ------------------------------------------------------------------------

    def _spawn(self, agent: str, work: Coroutine[Any, Any, None],
               on_skip: Callable[[], None] | None = None) -> None:
        if self.in_flight[agent] >= MAX_IN_FLIGHT.get(agent, 4):
            self.skipped[agent] += 1
            work.close()
            if on_skip is not None:
                on_skip()
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

    def top_lines(self, n: int = 3) -> list[str]:
        best = sorted(self.lines, key=lambda x: -x[0])[:n]
        return [f"{clock.split(':')[0]}' {text}" for _, clock, text in best]

    def health(self) -> dict[str, Any]:
        now = self.now()
        return {name: {**runner.health.snapshot(now), "skipped": self.skipped[name]}
                for name, runner in self.runners.items()}
