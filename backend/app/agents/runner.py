"""Running one agent safely (spec 8.7, 8.8).

Every call: send the input, take JSON that validates against the agent's output model, run the
verifier, and on any failure retry once with the error list added to the prompt. A second
failure, a timeout or an exception returns no value, and the caller keeps its template.
"""

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agent_framework import Agent
from pydantic import BaseModel, ValidationError

from app import telemetry
from app.agents.breaker import Breaker
from app.agents.clients import ChatClients, Tier

log = logging.getLogger(__name__)

R = TypeVar("R")
Check = Callable[[Any], tuple[R | None, list[str]]]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    tier: Tier
    instructions: str
    output: type[BaseModel]
    budget_s: float             # time budget and timeout per attempt (spec 8.1, 8.8)


@dataclass
class Outcome[R]:
    value: R | None
    reason: str                 # ok, offline, breaker, timeout, error, verifier
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    latency_ms: float = 0.0

    @property
    def ai(self) -> bool:
        return self.value is not None


@dataclass
class Health:
    """Counters for the dev panel and telemetry (spec 3, 12.2)."""

    calls: int = 0
    ai: int = 0
    fallbacks: int = 0
    timeouts: int = 0
    errors: int = 0
    verifier_failures: int = 0
    latency_ms: float | None = None
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    breaker: Breaker | None = None

    def record_call(self, now: float) -> None:
        self.calls += 1
        self.recent.append(now)

    def record_latency(self, ms: float) -> None:
        self.latency_ms = ms if self.latency_ms is None else 0.8 * self.latency_ms + 0.2 * ms

    def per_minute(self, now: float) -> int:
        return sum(1 for t in self.recent if now - t <= 60)

    def snapshot(self, now: float) -> dict[str, Any]:
        return {"calls": self.calls, "ai": self.ai, "fallbacks": self.fallbacks,
                "timeouts": self.timeouts, "errors": self.errors,
                "verifier_failures": self.verifier_failures, "per_minute": self.per_minute(now),
                "latency_ms": None if self.latency_ms is None else round(self.latency_ms),
                "breaker": self.breaker.state if self.breaker else "closed",
                "trips": self.breaker.trips if self.breaker else 0}


def with_limit(payload: Any, rule: str) -> str:
    """A prompt that states a length rule before the input. The rule stays outside INPUT, so
    its number never counts as a fact the verifier accepts."""
    return f"{rule}\nINPUT: " + json.dumps(payload, ensure_ascii=False, default=str)


def retry_prompt(prompt: str, errors: list[str]) -> str:
    listed = "\n".join(f"- {e}" for e in errors)
    return (f"{prompt}\n\nYour last answer was rejected:\n{listed}\n"
            "Answer again with the same JSON shape, fixing every problem.")


class AgentRunner:
    def __init__(self, spec: AgentSpec, clients: ChatClients | None,
                 now: Callable[[], float] = time.monotonic) -> None:
        self.spec = spec
        self.now = now
        self.breaker = Breaker(now)
        self.health = Health(breaker=self.breaker)
        self.agent = None if clients is None else Agent(
            client=clients.for_tier(spec.tier), name=spec.name, instructions=spec.instructions)

    async def run(self, payload: Any, check: Check[R], prompt: str | None = None
                  ) -> Outcome[R]:
        """`check` turns the model's output into the final value plus verifier errors.
        The prompt is "INPUT: " and the payload as JSON, unless one is given."""
        if self.agent is None:
            return self._fallback(Outcome(None, "offline"))
        if not self.breaker.allow():
            return self._fallback(Outcome(None, "breaker"))
        if prompt is None:
            prompt = "INPUT: " + (payload if isinstance(payload, str) else
                                  json.dumps(payload, ensure_ascii=False, default=str))
        started = self.now()
        errors: list[str] = []
        tags = {"agent": self.spec.name}
        for attempt in (1, 2):
            self.health.record_call(self.now())
            telemetry.instruments().calls.add(1, tags)
            try:
                response = await asyncio.wait_for(
                    self.agent.run(prompt if attempt == 1 else retry_prompt(prompt, errors),
                                   options={"response_format": self.spec.output}),
                    self.spec.budget_s)
            except TimeoutError:
                self.health.timeouts += 1
                return self._fail(Outcome(None, "timeout", attempts=attempt))
            except Exception as error:  # the network, auth, quota, a content filter...
                log.warning("agent %s failed: %s", self.spec.name, error)
                self.health.errors += 1
                return self._fail(Outcome(None, "error", [str(error)], attempt))
            output = self._parse(response)
            if output is None:
                errors = [f"the reply is not valid JSON for {self.spec.output.__name__}"]
                continue
            value, errors = check(output)
            if value is not None and not errors:
                latency = (self.now() - started) * 1000
                self.health.ai += 1
                self.health.record_latency(latency)
                telemetry.instruments().latency.record(latency, tags)
                self.breaker.record(True)
                return Outcome(value, "ok", [], attempt, latency)
        self.health.verifier_failures += 1
        telemetry.instruments().verifier_failures.add(1, tags)
        log.info("agent %s fell back after verifier errors: %s", self.spec.name, errors)
        return self._fail(Outcome(None, "verifier", errors, 2))

    def _parse(self, response: Any) -> BaseModel | None:
        try:
            value = response.value
        except (ValidationError, ValueError):
            value = None
        if isinstance(value, self.spec.output):
            return value
        try:
            return self.spec.output.model_validate_json(response.text)
        except (ValidationError, ValueError):
            return None

    def _fail(self, outcome: Outcome[R]) -> Outcome[R]:
        trips = self.breaker.trips
        self.breaker.record(False)
        if self.breaker.trips > trips:
            telemetry.instruments().breaker_trips.add(1, {"agent": self.spec.name})
        return self._fallback(outcome)

    def _fallback(self, outcome: Outcome[R]) -> Outcome[R]:
        self.health.fallbacks += 1
        telemetry.instruments().fallbacks.add(1, {"agent": self.spec.name,
                                                  "reason": outcome.reason})
        return outcome
