"""Telemetry (spec 10.5, 12.2): Agent Framework spans, a producer.route span per routed
moment, and Azure Monitor export when a connection string is set.

ENABLE_INSTRUMENTATION turns on Agent Framework's invoke_agent, chat and execute_tool spans.
APPLICATIONINSIGHTS_CONNECTION_STRING (Azure only) sends them to Application Insights.
ENABLE_SENSITIVE_DATA puts prompts and replies on spans: only ever on your own machine.
"""

import json
import logging
import sys
from typing import Any

from opentelemetry import metrics, trace

from app.config import Settings, settings

log = logging.getLogger(__name__)
TRACER_NAME = "pitch_bingo.producer"
_configured = False


def setup(config: Settings = settings) -> bool:
    """Configure once at startup. Returns whether instrumentation is on."""
    global _configured
    if _configured or not config.enable_instrumentation:
        return _configured
    if config.applicationinsights_connection_string:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=config.applicationinsights_connection_string)
    from agent_framework.observability import enable_instrumentation

    enable_instrumentation(enable_sensitive_data=config.enable_sensitive_data)
    _configured = True
    log.info("telemetry on%s", " (Application Insights)"
             if config.applicationinsights_connection_string else "")
    return True


def moment_log() -> logging.Logger:
    """One JSON line per routed moment on stdout (spec 12.2), which Container Apps collects.
    It says what ran and whether it was AI or a fallback; never prompts or replies (12.3)."""
    logger = logging.getLogger("pitch_bingo.moments")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_moment(**fields: Any) -> None:
    moment_log().info(json.dumps({"log": "producer.route", **fields}, default=str))


def tracer() -> Any:
    return trace.get_tracer(TRACER_NAME)


class Metrics:
    """The metrics in spec 12.2. Calls per minute is the rate of llm.calls."""

    def __init__(self, meter: Any) -> None:
        self.latency = meter.create_histogram(
            "agent.latency", unit="ms", description="Time to a verified agent reply")
        self.calls = meter.create_counter("llm.calls", description="LLM calls, retries included")
        self.verifier_failures = meter.create_counter(
            "verifier.failures", description="Agent outputs that failed the verifier twice")
        self.fallbacks = meter.create_counter("agent.fallbacks",
                                              description="Template used instead of AI")
        self.breaker_trips = meter.create_counter("breaker.trips",
                                                  description="Circuit breakers opened")
        self.sockets = meter.create_up_down_counter("sockets.connected",
                                                    description="Open viewer WebSockets")


_metrics: Metrics | None = None


def instruments() -> Metrics:
    global _metrics
    if _metrics is None:
        _metrics = Metrics(metrics.get_meter(TRACER_NAME))
    return _metrics
