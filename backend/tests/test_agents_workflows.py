"""The four workflows (spec 8.4) and telemetry (spec 12.2), with a fake client."""

import json
from typing import Any

import pytest
from agent_framework import Workflow
from factories import load_meta
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_agents_narrator import STATS, shot_event

from app import telemetry
from app.agents import personalizer, workflows
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.config import Settings
from app.game.card import Profile

META = load_meta()
INSIGHT = json.dumps({"moment_id": "e000001", "headline_facts": ["A save from close range."],
                      "why_facts": [],
                      "tags": [], "evidence_ids": [], "numbers": []})


def orch(replies: Any = (INSIGHT,)) -> tuple[Orchestrator, list[dict[str, Any]]]:
    fake = FakeChatClient(list(replies))
    published: list[dict[str, Any]] = []
    return Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: Profile(),
                        published.append, session_id="s1"), published


@pytest.mark.parametrize("build,name,steps", [
    (workflows.moment_workflow, "moment",
     {"router", "narrator", "verifier", "personalizer", "publisher", "square_writer"}),
    (workflows.window_workflow, "window_close",
     {"scorekeeper_result", "rules_tutor", "narrator_context", "verifier", "personalizer",
      "publisher"}),
    (workflows.strategy_workflow, "strategy", {"optimizer", "strategist", "publisher"}),
    (workflows.recap_workflow, "recap",
     {"state_summary", "recap", "verifier", "personalizer", "publisher"}),
])
def test_each_workflow_is_built_with_workflow_builder(build, name, steps):
    o, _ = orch()
    workflow = build(o)
    assert isinstance(workflow, Workflow) and workflow.name == name
    assert {e.id for e in workflow.get_executors_list()} == steps
    assert workflow.get_start_executor().id in {"router", "scorekeeper_result", "optimizer",
                                                "state_summary"}


async def test_the_moment_workflow_publishes_through_every_step():
    o, published = orch()
    job = workflows.MomentJob(shot_event(), {"significance": 70, "event": {}}, False,
                              ("m", "e1", "p"))
    result = await workflows.moment_workflow(o).run(job)
    assert result.get_outputs() == ["A save from close range."]
    assert published[0]["type"] == "feed.replace"


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "tracer", lambda: provider.get_tracer("test"))
    return exporter


async def test_each_routed_moment_gets_a_producer_span(spans):
    o, published = orch()
    o.on_event(shot_event(), 72, [], [], lambda: STATS, False)
    await o.drain()
    span = next(s for s in spans.get_finished_spans() if s.name == "producer.route")
    attrs = dict(span.attributes or {})
    assert attrs["session_id"] == "s1" and attrs["workflow"] == "moment"
    assert attrs["moment_id"] == "e000001" and attrs["significance"] == 72
    assert attrs["agent"] == "narrator" and attrs["fallback_used"] is False


async def test_a_fallback_is_marked_on_the_span(spans):
    o, published = orch(["Zlatanovic scores 7."])
    o.on_event(shot_event(), 72, [], [], lambda: STATS, False)
    await o.drain()
    span = next(s for s in spans.get_finished_spans() if s.name == "producer.route")
    assert span.attributes["fallback_used"] is True and published == []


def test_setup_turns_on_agent_framework_instrumentation(monkeypatch):
    import agent_framework.observability as observability
    calls: list[Any] = []
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(observability, "enable_instrumentation",
                        lambda **kw: calls.append(("instrument", kw)))
    assert telemetry.setup(Settings(enable_instrumentation=False)) is False
    assert calls == []
    assert telemetry.setup(Settings(enable_instrumentation=True)) is True
    assert calls == [("instrument", {"enable_sensitive_data": False})]
    monkeypatch.setattr(telemetry, "_configured", False)


async def test_metrics_for_calls_latency_fallbacks_and_breaker(monkeypatch):
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(telemetry, "_metrics", telemetry.Metrics(provider.get_meter("test")))
    o, _ = orch([INSIGHT])
    o.on_event(shot_event(), 72, [], [], lambda: STATS, False)
    await o.drain()
    bad, _ = orch([RuntimeError("503")])
    for _ in range(3):
        personalizer.CACHE.clear()          # or the first line answers from the cache
        bad.on_event(shot_event(), 72, [], [], lambda: STATS, False)
        await bad.drain()
    names: dict[str, float] = {}
    for rm in reader.get_metrics_data().resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                for point in metric.data.data_points:
                    names[metric.name] = names.get(metric.name, 0) + getattr(
                        point, "value", getattr(point, "count", 0))
    assert names["llm.calls"] >= 4 and names["agent.latency"] >= 1
    assert names["agent.fallbacks"] >= 3 and names["breaker.trips"] == 1
