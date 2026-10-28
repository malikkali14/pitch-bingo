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

from agent_framework import Workflow

from app import telemetry
from app.agents import (
    narrator,
    personalizer,
    recap,
    square_writer,
    strategist_reason,
    tutor,
    workflows,
)
from app.agents.clients import ChatClients
from app.agents.runner import AgentRunner, with_limit
from app.game import lang
from app.game.card import Profile
from app.game.live import Wording

log = logging.getLogger(__name__)

Publish = Callable[[dict[str, Any]], None]
DEFINITION_CACHE: dict[tuple[str, str], str] = {}   # (term, language) -> the tutor's line
FOCUS_EVERY_S = 600.0
MAX_IN_FLIGHT = {"narrator": 3}   # past this, a moment keeps its template line


def once(fn: Callable[[Any], None], default: Any) -> Callable[..., None]:
    """fn, called at most once; called with no argument it passes the default."""
    called = False

    def call(*args: Any) -> None:
        nonlocal called
        if not called:
            called = True
            fn(args[0] if args else default)
    return call


class Orchestrator:
    def __init__(self, clients: ChatClients | None, meta: dict[str, Any],
                 profile: Callable[[], Profile], publish: Publish,
                 now: Callable[[], float] = time.monotonic, session_id: str = "") -> None:
        self.clients = clients
        self.session_id = session_id
        self.meta = meta
        self.profile = profile
        self.publish = publish
        self.now = now
        self.names = narrator.Names(meta)
        self.runners = {
            "narrator": AgentRunner(narrator.SPEC, clients, now),
            "personalizer": AgentRunner(personalizer.SPEC, clients, now),
            "square_writer": AgentRunner(square_writer.SPEC, clients, now),
            "strategist": AgentRunner(strategist_reason.SPEC, clients, now),
            "rules_tutor": AgentRunner(tutor.TUTOR, clients, now),
            "narrator_context": AgentRunner(tutor.CONTEXT, clients, now),
            "recap": AgentRunner(recap.SPEC, clients, now),
            "definitions": AgentRunner(tutor.DEFINE, clients, now),
        }
        self.in_flight: dict[str, int] = {name: 0 for name in self.runners}
        self.skipped: dict[str, int] = {name: 0 for name in self.runners}
        self.tasks: set[asyncio.Task[None]] = set()
        self.lines: list[tuple[int, str, str]] = []     # (significance, clock, AI line)
        self.focus_said_at = 0.0       # the first focus line comes at 10', not at kickoff

    @property
    def online(self) -> bool:
        return self.clients is not None

    # ---- moments (spec 8.4, moment workflow) ---------------------------------------------

    def on_event(self, event: dict[str, Any], significance: int,
                 triggers: list[dict[str, Any]], milestones: list[dict[str, Any]],
                 stats: Callable[[], dict[str, Any]], held: bool,
                 shot_xg: float | None = None) -> None:
        self._focus_milestones(event, milestones, held)
        if not self.online or not narrator.wants_line(significance, triggers):
            return
        if self.runners["narrator"].breaker.forced:
            return              # the failure switch: template lines only, cached ones too
        moment = narrator.build_moment(event, significance, stats(), triggers, milestones,
                                       self.names, shot_xg)
        if self.profile().units == "imperial":
            narrator.add_imperial(moment)
        key = (self.meta["match_id"], event["event_id"],
               personalizer.profile_hash(self.profile()))
        job = workflows.MomentJob(event, moment, held, key,
                                  [text for _, _, text in self.lines[-3:]])
        self._spawn("narrator", self._run(
            workflows.moment_workflow(self), job, "moment",
            {"moment_id": event["event_id"], "significance": significance,
             "agent": "narrator"}))

    # ---- focus player (spec 5.3) -------------------------------------------------------

    def _focus_milestones(self, event: dict[str, Any], milestones: list[dict[str, Any]],
                          held: bool) -> None:
        """The focus player's milestones are always announced, Foundry or not."""
        focus = self.profile().focus_player_id
        language = lang.normalize(self.profile().language)
        for found in milestones:
            if focus is None or found.get("player_id") != focus:
                continue
            what = lang.MILESTONES[language].get(found["kind"], found["kind"]).format(**found)
            self.publish({"type": "feed.replace", "held": held, "ai": False,
                          "entry_id": f"milestone:{event['event_id']}:{found['kind']}",
                          "text": lang.say(language, "milestone",
                                           player=self.names.player(focus), what=what),
                          "clock": event["clock"], "event_type": "milestone"})

    def focus_update(self, t: float, clock: str, period: int,
                     stats: Callable[[], dict[str, Any]]) -> None:
        """A line about the focus player at least every 10 match minutes (spec 5.3)."""
        focus = self.profile().focus_player_id
        if focus is None or t - self.focus_said_at < FOCUS_EVERY_S:
            return
        self.focus_said_at = t
        player = stats().get("players", {}).get(focus, {})
        language = lang.normalize(self.profile().language)
        self.publish({"type": "feed.replace", "held": False, "ai": False,
                      "entry_id": f"focus:{round(t)}", "clock": clock, "event_type": "focus",
                      "text": lang.say(language, "focus_line", player=self.names.player(focus),
                                       touches=player.get("touches", 0),
                                       passes=player.get("passes", 0),
                                       shots=player.get("shots") or 0)})

    # ---- live squares (spec 8.4, the moment workflow's second branch) --------------------

    def write_square(self, pending: dict[str, Any],
                     done: Callable[[Wording | None], None]) -> None:
        """Word a live square, then call done (with None for the template wording)."""
        if not self.online:
            done(None)
            return
        finish = once(done, None)
        job = workflows.LiveJob(pending, finish)
        self._spawn("square_writer", self._run(
            workflows.moment_workflow(self), job, "moment",
            {"square_id": pending["square_id"], "agent": "square_writer"}, finish),
            on_skip=finish)

    # ---- strategy (spec 8.4, strategy workflow) ------------------------------------------

    def explain_advice(self, advice: dict[str, Any], board: dict[str, Any],
                       done: Callable[[dict[str, Any]], None]) -> None:
        """Send the advice with the agent's reason, or with the template reason."""
        if not self.online or not advice.get("moves"):
            done(advice)
            return
        finish = once(done, advice)
        job = workflows.StrategyJob(advice, board, finish)
        self._spawn("strategist", self._run(
            workflows.strategy_workflow(self), job, "strategy",
            {"advice_id": advice["advice_id"], "agent": "strategist"}, finish),
            on_skip=finish)

    # ---- window close (spec 8.4, window-close workflow) -----------------------------------

    def explain_square(self, square: dict[str, Any]) -> None:
        """Normal mode: the rules tutor. Advanced mode: the narrator's tactical context. The
        template explanation is already up; this replaces it if it passes."""
        if not self.online:
            return
        mode = self.profile().mode
        agent = "rules_tutor" if mode == "normal" else "narrator_context"
        job = workflows.WindowJob(square, mode)
        self._spawn(agent, self._run(workflows.window_workflow(self), job, "window_close",
                                     {"square_id": square["square_id"], "agent": agent}))

    # ---- recaps (spec 8.4, recap workflow) -----------------------------------------------

    def write_recap(self, summary: recap.Summary) -> None:
        """The template recap at once, then the recap agent's version if it passes."""
        fallback = recap.template(summary, self.profile().language)
        self.publish({"type": "recap", **fallback.model_dump()})
        if not self.online:
            return
        self._spawn("recap", self._run(workflows.recap_workflow(self),
                                       workflows.RecapJob(summary), "recap",
                                       {"recap_kind": summary.kind, "agent": "recap"}))

    async def _run(self, workflow: Workflow, job: Any, name: str, attributes: dict[str, Any],
                   finish: Callable[..., None] | None = None) -> None:
        """One workflow run inside a producer.route span (spec 12.2), so a single event can be
        followed from the producer through the Agent Framework spans to the screen."""
        with telemetry.tracer().start_as_current_span("producer.route") as span:
            span.set_attribute("session_id", self.session_id)
            span.set_attribute("workflow", name)
            for key, value in attributes.items():
                span.set_attribute(key, value)
            agent = attributes.get("agent", "")
            before = self.runners[agent].health.verifier_failures if agent in self.runners else 0
            started = self.now()
            outputs: list[Any] = []
            try:
                result = await workflow.run(job)
                outputs = [o for o in result.get_outputs() if o is not None]
            finally:
                if finish is not None:
                    finish()            # no-op if the workflow already answered
            after = self.runners[agent].health.verifier_failures if agent in self.runners else 0
            span.set_attribute("fallback_used", not outputs)
            span.set_attribute("verifier_errors", after - before)
            telemetry.log_moment(session_id=self.session_id, workflow=name, ai=bool(outputs),
                                 verifier_errors=after - before,
                                 latency_ms=round((self.now() - started) * 1000), **attributes)

    # ---- definitions (spec 5.1) -------------------------------------------------------

    def define(self, term: str) -> bool:
        """The stored definition at once; the rules tutor's version after, cached for every
        viewer. False for an unknown term."""
        language = lang.normalize(self.profile().language)
        stored = tutor.definition(term, language)
        if stored is None:
            return False
        cached = DEFINITION_CACHE.get((term, language))
        self.publish({"type": "definition", "term": term, "text": cached or stored,
                      "ai": cached is not None})
        if cached is not None or not self.online:
            return True
        payload = {"term": term.replace("_", " "), "stored_definition": stored}

        async def explain() -> None:
            with telemetry.tracer().start_as_current_span("producer.route") as span:
                span.set_attribute("session_id", self.session_id)
                span.set_attribute("agent", "definitions")
                span.set_attribute("term", term)
                outcome = await self.runners["definitions"].run(
                    payload, lambda v: tutor.check_definition(v, payload, self.meta),
                    prompt=with_limit(payload, "Length: the text must be under 140 characters."
                                      + tutor.language_rule(language)))
                span.set_attribute("fallback_used", outcome.value is None)
            if outcome.value is not None:
                DEFINITION_CACHE[(term, language)] = outcome.value
                self.publish({"type": "definition", "term": term, "text": outcome.value,
                              "ai": True})

        self._spawn("definitions", explain())
        return True

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
