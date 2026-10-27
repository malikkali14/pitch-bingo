"""The four Agent Framework workflows (spec 8.4), built with WorkflowBuilder.

1. Moment:       Router -> Narrator -> Verifier -> Personalizer -> Publisher, and for a live
                 square the router's second branch: Square writer -> Verifier -> Publisher.
2. Window close: Result -> Rules tutor (normal) or Narrator context (advanced) -> Verifier
                 -> Publisher.
3. Strategy:     Optimizer -> Strategist reason -> Publisher.
4. Recap:        State summary -> Recap -> Verifier -> Publisher.

Agent steps call the shared AgentRunners, so timeouts, the breaker, the one retry with the
verifier's errors and the fallbacks all apply. The Verifier executor is a last deterministic
gate: nothing reaches the Publisher without passing it. A workflow can't run twice at once,
so each run builds a fresh one; the executors are cheap and the agents they call are shared.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from app.agents import narrator, personalizer, recap, square_writer, strategist_reason, tutor
from app.agents.messages import Insight, Recap
from app.game.live import Wording
from app.verify.verifier import LIMITS, verify_line, verify_live_square

if TYPE_CHECKING:
    from app.agents.orchestrator import Orchestrator


# ---- messages between steps (spec 8.5) ---------------------------------------------------

@dataclass
class MomentJob:
    event: dict[str, Any]
    moment: dict[str, Any]
    held: bool
    key: tuple[str, str, str]


@dataclass
class LiveJob:
    pending: dict[str, Any]
    done: Callable[[Wording | None], None]


@dataclass
class Drafted:
    """The narrator's insight and its plain rendering, before the personalizer."""

    job: MomentJob
    insight: Insight
    text: str


@dataclass
class Line:
    job: MomentJob
    text: str


@dataclass
class Worded:
    job: LiveJob
    wording: Wording


@dataclass
class WindowJob:
    square: dict[str, Any]
    mode: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Explained:
    job: WindowJob
    text: str


@dataclass
class StrategyJob:
    advice: dict[str, Any]
    board: dict[str, Any]
    done: Callable[[dict[str, Any]], None]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Reasoned:
    job: StrategyJob
    reason: str


@dataclass
class RecapJob:
    summary: recap.Summary


@dataclass
class Recapped:
    job: RecapJob
    recap: Recap


class Step(Executor):
    def __init__(self, orchestrator: "Orchestrator", id: str) -> None:
        super().__init__(id=id)
        self.o = orchestrator


# ---- 1. moment workflow --------------------------------------------------------------------

class Router(Step):
    """Routes a moment to the narrator (or straight to the publisher when this profile type
    already has the line), and a live square down the square writer's branch."""

    @handler
    async def moment(self, job: MomentJob, ctx: WorkflowContext[MomentJob | Line]) -> None:
        text = personalizer.cached(job.key)
        await ctx.send_message(Line(job, text) if text is not None else job)

    @handler
    async def live(self, job: LiveJob, ctx: WorkflowContext[LiveJob]) -> None:
        await ctx.send_message(job)


class Narrator(Step):
    @handler
    async def narrate(self, job: MomentJob, ctx: WorkflowContext[Drafted, None]) -> None:
        mode = self.o.profile().mode
        limit = LIMITS[mode]
        found: dict[str, Insight] = {}

        def check(insight: Insight) -> tuple[str | None, list[str]]:
            text = narrator.render(insight, limit)
            if text is None:
                return None, [f"the headline must fit in {limit} characters"]
            found["insight"] = insight
            return text, verify_line(text, job.moment, self.o.meta, mode)

        outcome = await self.o.runners["narrator"].run(job.moment, check)
        if outcome.value is None:
            await ctx.yield_output(None)      # the template line stands
            return
        await ctx.send_message(Drafted(job, found["insight"], outcome.value))


class SquareWriter(Step):
    @handler
    async def write(self, job: LiveJob, ctx: WorkflowContext[Worded, None]) -> None:
        pending = job.pending
        outcome = await self.o.runners["square_writer"].run(
            pending, lambda draft: square_writer.check(draft, pending, self.o.meta),
            prompt=square_writer.prompt(pending))
        if outcome.value is None:
            job.done(None)                    # template wording; the window opens anyway
            await ctx.yield_output(None)
            return
        await ctx.send_message(Worded(job, outcome.value))


class Verifier(Step):
    """The last gate before anything is published (spec 8.7)."""

    @handler
    async def line(self, item: Drafted, ctx: WorkflowContext[Drafted, None]) -> None:
        mode = self.o.profile().mode
        if verify_line(item.text, item.job.moment, self.o.meta, mode):
            await ctx.yield_output(None)
            return
        await ctx.send_message(item)

    @handler
    async def square(self, item: Worded, ctx: WorkflowContext[Worded, None]) -> None:
        pending, w = item.job.pending, item.wording
        if verify_live_square(w.text, w.options, pending["correct"], pending["options"]):
            item.job.done(None)
            await ctx.yield_output(None)
            return
        await ctx.send_message(item)

    @handler
    async def explanation(self, item: Explained, ctx: WorkflowContext[Explained, None]) -> None:
        if verify_line(item.text, item.job.payload, self.o.meta, item.job.mode):
            await ctx.yield_output(None)
            return
        await ctx.send_message(item)

    @handler
    async def recap(self, item: Recapped, ctx: WorkflowContext[Recapped, None]) -> None:
        if recap.check(item.recap.content, item.job.summary, self.o.meta)[1]:
            await ctx.yield_output(None)
            return
        await ctx.send_message(item)


class Personalizer(Step):
    @handler
    async def personalize(self, item: Drafted, ctx: WorkflowContext[Line]) -> None:
        profile = self.o.profile()
        payload = personalizer.build_input(item.insight, profile, self.o.names)
        outcome = await self.o.runners["personalizer"].run(
            payload, lambda value: personalizer.check(value, item.job.moment, payload,
                                                      self.o.meta, profile.mode))
        await ctx.send_message(Line(item.job, outcome.value or item.text))


class Publisher(Step):
    """Writes to the session and so to the viewer's WebSocket (spec 8.4)."""

    @handler
    async def line(self, item: Line, ctx: WorkflowContext[None, str]) -> None:
        job = item.job
        personalizer.remember(job.key, item.text)
        self.o.lines.append((job.moment["significance"], job.event["clock"], item.text))
        # Replaces the template line in place; a held line stays held until revealed.
        self.o.publish({"type": "feed.replace", "entry_id": job.event["event_id"],
                        "text": item.text, "ai": True, "clock": job.event["clock"],
                        "event_type": job.event["type"], "held": job.held})
        await ctx.yield_output(item.text)

    @handler
    async def square(self, item: Worded, ctx: WorkflowContext[None, str]) -> None:
        item.job.done(item.wording)
        await ctx.yield_output(item.wording.text)

    @handler
    async def explanation(self, item: Explained, ctx: WorkflowContext[None, str]) -> None:
        self.o.publish({"type": "square.explanation", "square_id": item.job.square["square_id"],
                        "text": item.text, "ai": True})
        await ctx.yield_output(item.text)

    @handler
    async def reason(self, item: Reasoned, ctx: WorkflowContext[None, str]) -> None:
        item.job.done({**item.job.advice, "reason": item.reason})
        await ctx.yield_output(item.reason)

    @handler
    async def recap(self, item: Recapped, ctx: WorkflowContext[None, str]) -> None:
        self.o.publish({"type": "recap", **item.recap.model_dump()})
        await ctx.yield_output(item.recap.content.headline)


def moment_workflow(o: "Orchestrator") -> Workflow:
    router, narr = Router(o, "router"), Narrator(o, "narrator")
    writer, verifier = SquareWriter(o, "square_writer"), Verifier(o, "verifier")
    personal, publisher = Personalizer(o, "personalizer"), Publisher(o, "publisher")
    return (WorkflowBuilder(name="moment", start_executor=router)
            .add_edge(router, narr, condition=lambda m: isinstance(m, MomentJob))
            .add_edge(router, publisher, condition=lambda m: isinstance(m, Line))
            .add_edge(router, writer, condition=lambda m: isinstance(m, LiveJob))
            .add_edge(narr, verifier)
            .add_edge(writer, verifier)
            .add_edge(verifier, personal, condition=lambda m: isinstance(m, Drafted))
            .add_edge(verifier, publisher, condition=lambda m: isinstance(m, Worded))
            .add_edge(personal, publisher)
            .build())


# ---- 2. window-close workflow ---------------------------------------------------------------

class Result(Step):
    """The scorekeeper's result: route to the rules tutor or the narrator's context."""

    @handler
    async def route(self, job: WindowJob, ctx: WorkflowContext[WindowJob]) -> None:
        job.payload = tutor.build_input(job.square)
        await ctx.send_message(job)


class Explainer(Step):
    def __init__(self, orchestrator: "Orchestrator", id: str, agent: str) -> None:
        super().__init__(orchestrator, id)
        self.agent = agent

    @handler
    async def explain(self, job: WindowJob, ctx: WorkflowContext[Explained, None]) -> None:
        outcome = await self.o.runners[self.agent].run(
            job.payload, lambda value: tutor.check(value, job.payload, self.o.meta, job.mode))
        if outcome.value is None:
            await ctx.yield_output(None)      # the template explanation stands
            return
        await ctx.send_message(Explained(job, outcome.value))


def window_workflow(o: "Orchestrator") -> Workflow:
    result = Result(o, "scorekeeper_result")
    rules = Explainer(o, "rules_tutor", "rules_tutor")
    context = Explainer(o, "narrator_context", "narrator_context")
    verifier, publisher = Verifier(o, "verifier"), Publisher(o, "publisher")
    return (WorkflowBuilder(name="window_close", start_executor=result)
            .add_edge(result, rules, condition=lambda job: job.mode == "normal")
            .add_edge(result, context, condition=lambda job: job.mode != "normal")
            .add_edge(rules, verifier)
            .add_edge(context, verifier)
            .add_edge(verifier, publisher)
            .build())


# ---- 3. strategy workflow --------------------------------------------------------------------

class Optimizer(Step):
    """The optimizer already chose the moves in code (game/strategist.py); this step turns
    its choice into the strategist's input."""

    @handler
    async def describe(self, job: StrategyJob, ctx: WorkflowContext[StrategyJob]) -> None:
        job.payload = strategist_reason.build_input(job.advice, job.board)
        await ctx.send_message(job)


class Strategist(Step):
    @handler
    async def explain(self, job: StrategyJob, ctx: WorkflowContext[Reasoned, None]) -> None:
        outcome = await self.o.runners["strategist"].run(
            job.payload, lambda value: strategist_reason.check(value, job.payload, self.o.meta))
        if outcome.value is None:
            job.done(job.advice)              # the template reason
            await ctx.yield_output(None)
            return
        await ctx.send_message(Reasoned(job, outcome.value))


def strategy_workflow(o: "Orchestrator") -> Workflow:
    optimizer, strategist = Optimizer(o, "optimizer"), Strategist(o, "strategist")
    publisher = Publisher(o, "publisher")
    return (WorkflowBuilder(name="strategy", start_executor=optimizer)
            .add_edge(optimizer, strategist)
            .add_edge(strategist, publisher)
            .build())


# ---- 4. recap workflow -------------------------------------------------------------------------

class StateSummary(Step):
    """The summary is built by code; the template recap posts first."""

    @handler
    async def summarize(self, job: RecapJob, ctx: WorkflowContext[RecapJob]) -> None:
        await ctx.send_message(job)


class Recapper(Step):
    @handler
    async def write(self, job: RecapJob, ctx: WorkflowContext[Recapped, None]) -> None:
        summary = job.summary
        outcome = await self.o.runners["recap"].run(
            summary.payload(), lambda content: recap.check(content, summary, self.o.meta))
        if outcome.value is None:
            await ctx.yield_output(None)      # the template recap stands
            return
        await ctx.send_message(Recapped(job, outcome.value))


def recap_workflow(o: "Orchestrator") -> Workflow:
    summary, writer = StateSummary(o, "state_summary"), Recapper(o, "recap")
    verifier, publisher = Verifier(o, "verifier"), Publisher(o, "publisher")
    return (WorkflowBuilder(name="recap", start_executor=summary)
            .add_edge(summary, writer)
            .add_edge(writer, verifier)
            .add_edge(verifier, publisher)
            .build())
