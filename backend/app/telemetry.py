"""Telemetry (spec 10.5, 12.2): Agent Framework spans, a producer.route span per routed
moment, and Azure Monitor export when a connection string is set.

ENABLE_INSTRUMENTATION turns on Agent Framework's invoke_agent, chat and execute_tool spans.
APPLICATIONINSIGHTS_CONNECTION_STRING (Azure only) sends them to Application Insights.
ENABLE_SENSITIVE_DATA puts prompts and replies on spans: only ever on your own machine.
"""

import logging
from typing import Any

from opentelemetry import trace

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


def tracer() -> Any:
    return trace.get_tracer(TRACER_NAME)
